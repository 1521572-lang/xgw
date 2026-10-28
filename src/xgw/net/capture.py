"""Перехват трафика целиком: правила nftables, маршрутизация по меткам, форвардинг.

Режимы:
  on   — перехват включён: LAN и (или) сама машина ходят через Xray;
  off  — снят командой `xgw disable`: сеть работает напрямую, шлюз остаётся роутером;
  open — снят демоном на время: Xray недоступен, а в конфиге fail_mode = "open";
  none — в конфиге перехват выключен (capture.lan = capture.local = false).
Пока в применённом конфиге Xray нет inbound'а перехвата, «on» загружается как blocked
(capture.hold = "block": перехвата нет, и мимо VPN не уходит ничего) или как «off»
(hold = "direct"); см. effective_mode и hold_mode.

Трафик самой машины попадает в Xray либо через TPROXY на lo (по умолчанию), либо
через постоянный TUN-интерфейс (capture.method = "tun", см. net/tun.py); сеть LAN
всегда через TPROXY. Интерфейс создаётся при включении перехвата и убирается командой
`net down`: `xgw disable` и fail_mode = open снимают лишь правило и маршрут, иначе Xray
остался бы с оборванным интерфейсом и потребовал перезапуска. Ещё он убирается сам, когда
стал не нужен: capture.method больше не "tun", и Xray запущен без inbound'а TUN — то есть
интерфейс не нужен и контейнерам (tidy).

Контейнеры Docker (capture.containers) — всегда через тот же TUN-интерфейс, по своей
метке: TPROXY с мостами Docker не работает (net/nft.py). Интерфейс для них появляется,
только когда Docker на машине есть (engine.containers_tun): тогда в конфиге Xray есть
inbound TUN, и интерфейс создаёт XGW — Applier перед запуском Xray, а при загрузке
xgw-net.service (_prepare_tun). Без интерфейса маршрут контейнеров ведёт в чёрную дыру —
они закрыты, а не идут мимо VPN. Интерфейс без адреса (его создал сам Xray) — тоже
сбой: ответы Xray ядро отбросит; loaded() это видит, и демон загружает правила заново.

Выбор «включён/снят» хранится в /var/lib/xgw и переживает перезагрузку: по нему
правила загружает xgw-net.service. Временное снятие (open) — метка в /run.
Все операции идемпотентны и идут под файловой блокировкой.

Путь LAN (lan_path): помеченный пакет клиента LAN должен доставляться локально, в TPROXY.
Так бывает не всегда — например, при net.ipv4.conf.all.src_valid_mark = 1 без маршрута throw
для подсети LAN (iprule.py) ядро молча отбрасывает такие пакеты, а машина и контейнеры при
этом работают. Демон проверяет это на каждом шаге (`ip route get … iif <LAN> mark …`).

Tailscale (Т1): исключения для tailscaled в правилах есть, только пока он работает
(tailscale.present). Он запустился или остановился — правила уже не те (loaded), и демон
загружает их заново. При tailscale.route = "vpn" демон отмечает в /run, что Xray не
отвечает (tailscale_direct): тогда сокеты tailscaled идут мимо Xray.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import time
from collections.abc import Callable
from pathlib import Path

from .. import log
from .. import tailscale as ts
from ..config import Config
from ..paths import Paths, atomic_write_json, file_lock
from . import cmd, iprule, lan, nft, sysctl, tun


class CaptureError(Exception):
    """Правила не загружены: нет прав, nft или ip, либо ядро их не приняло."""


# Теги inbound'ов перехвата в конфиге Xray (их пишет генератор, builder.py): TPROXY для
# IPv4 и IPv6 и TUN для трафика самой машины.
TPROXY_TAG = "tproxy-in"
TPROXY6_TAG = "tproxy-in6"
# Куда «идёт» пакет проверки пути LAN: любой внешний адрес (ip route get его не трогает).
LAN_PROBE_TARGET = "1.1.1.1"
TUN_TAG = "tun-in"
CAPTURE_TAGS = (TPROXY_TAG, TPROXY6_TAG, TUN_TAG)


def capture_inbounds(config: dict | None) -> list[str]:
    """Inbound'ы перехвата конфига Xray в каноническом виде — то, от чего зависят
    правила сети.

    Пока применённый конфиг и правила расходятся (правила ведут пакеты на порт или в
    интерфейс, которых у работающего Xray нет), трафик уходит в никуда. Поэтому любое
    отличие — inbound появился, исчез или изменился хоть один его параметр — применяется
    перезапуском Xray сразу, а не в окне apply.restart_window.
    """
    inbounds = config.get("inbounds") if isinstance(config, dict) else None
    if not isinstance(inbounds, list):
        return []
    found = []
    for inbound in inbounds:
        if not isinstance(inbound, dict):
            continue
        if str(inbound.get("tag", "")) in CAPTURE_TAGS or inbound.get("protocol") == "tun":
            found.append(json.dumps(inbound, sort_keys=True, ensure_ascii=False))
    return sorted(found)


def capture_for(cfg: Config, paths: Paths, **kwargs) -> Capture:
    """Управление перехватом: правила ядра (nftables, ip rule)."""
    return Capture(cfg, paths, **kwargs)


def _fp_peers(paths: Paths) -> tuple[str, ...]:
    """Серверы бесплатного пула, к которым сейчас есть поколения (freepool/backend.py)."""
    from ..freepool.backend import peer_elements

    return peer_elements(paths)


class Capture:
    reloaded_text = "правила сети не были загружены — загружены заново"
    # До этого момента (time.monotonic()) события `nft monitor` о таблицах XGW вызваны
    # своей загрузкой, и демон по ним не просыпается (watch/events.py). Общее для всех
    # экземпляров процесса: панель включает и снимает перехват своим экземпляром, а
    # события слушает демон. Пока идёт `nft -f`, окно открыто (inf): события netlink
    # приходят асинхронно и могут опередить возврат из nft.
    ignore_rules_until: float = 0.0
    RULES_QUIET = 1.0  # сколько ещё ждать своих событий после загрузки

    def __init__(
        self,
        cfg: Config,
        paths: Paths,
        *,
        runner: cmd.Runner = cmd.run,
        logger=None,
        proc_sys: Path = sysctl.PROC_SYS,
        time_uids: tuple[int, ...] | None = None,
        generation: Callable[[], int | None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.runner = runner
        # Проверки правил (loaded, tailscale_loaded) читают таблицы через кэш по поколению
        # правил ядра (nft.Listings): пока правила никто не менял, nft не запускается (отчёт
        # 0.2.0: 3,5 с на каждом шаге демона с nft 1.0.9). Поколение говорит о настоящем nft,
        # поэтому кэш — только у cmd.run; у подставного runner тестов свои правила, и кэш у
        # него — только если тест передал generation сам.
        if generation is None and runner is cmd.run:
            generation = nft.generation
        self.lister: cmd.Runner = (
            nft.Listings(runner, generation) if generation is not None else runner)
        self.log = logger or log.get_logger("net")
        self.proc_sys = proc_sys
        self.time_uids = time_uids
        self.state_file = paths.var / "capture.json"
        self.open_marker = paths.run / "capture-open"
        # tailscale.route = "vpn", а Xray не отвечает: сокеты tailscaled — мимо Xray.
        self.ts_marker = paths.run / "tailscale-direct"
        # tailscale.route = "direct", а DERP напрямую не отвечает (ТЗ R4b): tailscaled временно
        # идёт через Xray.
        self.ts_fallback_marker = paths.run / "tailscale-via-vpn"
        self.sys_net: Path | None = None  # где искать мосты Docker; None — lan.SYS_NET
        self._warned: set[str] = set()
        # Почему последняя загрузка вместо перехвата оставила сеть напрямую: в применённом
        # конфиге Xray нет нужного inbound'а либо нет TUN-интерфейса (см. _load). Пусто —
        # такого не было.
        self.held = ""

    # --- что настроено ----------------------------------------------------------

    @property
    def lan_if(self) -> str:
        return lan.lan_interface(self.cfg)

    @property
    def capturing(self) -> bool:
        """В конфиге есть что перехватывать."""
        return self.cfg.capture.local or (self.cfg.capture.lan and bool(self.lan_if))

    @property
    def configured(self) -> bool:
        """Есть что загружать: перехват либо хотя бы LAN (шлюз как роутер)."""
        return self.capturing or bool(self.lan_if)

    # --- состояние --------------------------------------------------------------

    def _state(self) -> dict:
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return state if isinstance(state, dict) else {}

    def _save(self, **changes: object) -> None:
        state = self._state()
        for key, value in changes.items():
            if value is None:
                state.pop(key, None)
            else:
                state[key] = value
        atomic_write_json(self.state_file, state, mode=0o644)

    def choice(self) -> bool | None:
        """Явный выбор пользователя; None — ни enable, ни disable ещё не выполнялись."""
        value = self._state().get("enabled")
        return value if isinstance(value, bool) else None

    def wanted(self) -> bool:
        """Выбор пользователя: `xgw enable` (по умолчанию) или `xgw disable`."""
        return bool(self._state().get("enabled", True))

    def mode(self) -> str:
        if not self.capturing:
            return "none"
        if not self.wanted():
            return "off"
        return "open" if self.open_marker.exists() else "on"

    def ipv6_usable(self) -> bool:
        return sysctl.ipv6_usable(self.proc_sys)

    def rules(self, mode: str | None = None) -> nft.Rules:
        """Параметры правил для режима (по умолчанию — текущего)."""
        mode = mode or self.mode()
        tailnet = ts.present(self.paths, self.sys_net)
        rules, warnings = nft.build_rules(
            self.cfg, capture=mode == "on", blocked=mode == "blocked", time_uids=self.time_uids,
            tailscale=self.cfg.capture.local and tailnet,
            xray_down=self.ts_marker.exists(), tailnet=tailnet,
            ts_fallback=self.ts_fallback_marker.exists(),
            geoip=self.paths.xray_dir / "geoip.dat",
            fp_peers=_fp_peers(self.paths),
        )
        if rules.capture6 and not self.ipv6_usable():
            # Нечего перехватывать: утечки через IPv6 быть не может, а команды ip -6
            # и таблица ip6 в таком ядре не работают и сломали бы загрузку IPv4.
            rules = dataclasses.replace(rules, capture6=False)
            warnings.append("network.ipv6 = proxy, но IPv6 в ядре выключен: проксировать нечего")
        if rules.v6_guard and not self.ipv6_usable():
            rules = dataclasses.replace(rules, v6_guard=False)  # закрывать нечего
        for warning in warnings:
            if warning not in self._warned:  # демон собирает правила на каждом шаге
                self._warned.add(warning)
                self.log.warning("%s", warning)
        return rules

    # --- действия ---------------------------------------------------------------

    def _lock(self):
        return file_lock(self.paths.run / "net.lock", timeout=30.0)

    @contextlib.contextmanager
    def _own_rules(self):
        """Загрузка своих правил: события о них демона не будят (ignore_rules_until)."""
        Capture.ignore_rules_until = float("inf")
        try:
            yield
        finally:
            Capture.ignore_rules_until = time.monotonic() + self.RULES_QUIET

    @staticmethod
    def rules_quiet() -> bool:
        """Сейчас события правил — от своей загрузки."""
        return time.monotonic() < Capture.ignore_rules_until

    def _families(self) -> tuple[int, ...]:
        return (4, 6) if self.ipv6_usable() else (4,)

    def _throws(self, rules: nft.Rules, family: int) -> tuple[str, ...]:
        """Подсети, для которых в таблице TPROXY нужен маршрут throw: подсеть LAN, пока её
        трафик перехватывается, и tailnet, пока шлюз — выходной узел (iprule.py: проверка
        источника с учётом метки; tailscaled сам ставит src_valid_mark = 1)."""
        if family != 4:
            return ()
        throws: list[str] = []
        gateway = lan.gateway(self.cfg)
        if rules.capture_lan and rules.lan_if and gateway is not None:
            throws.append(str(gateway.network))
        if rules.ts_exit:
            throws.append(str(ts.CGNAT))
        return tuple(throws)

    @staticmethod
    def _wanted(rules: nft.Rules, family: int) -> tuple[bool, bool]:
        """(локальная доставка для TPROXY, маршрут в TUN) для семейства адресов."""
        tproxy = rules.tproxy if family == 4 else rules.prerouting6
        return tproxy, rules.tun and (family == 4 or rules.capture6)

    def _tun_dev(self, rules: nft.Rules) -> str | None:
        """Интерфейс TUN, если он есть в системе (для маршрута контейнеров)."""
        try:
            return rules.tun_name if tun.present(rules.tun_name, self.runner) else None
        except cmd.CommandError as exc:
            self.log.debug("интерфейс %s не проверен: %s", rules.tun_name, exc)
            return None

    def _routes_up(self, rules: nft.Rules) -> None:
        """Правила `ip rule` и маршруты, которые нужны текущим правилам. Интерфейс TUN к
        этому времени уже создан: см. _prepare_tun."""
        cap = self.cfg.capture
        for family in self._families():
            tproxy, via_tun = self._wanted(rules, family)
            if tproxy:
                iprule.ensure(
                    cap.mark_proxy, cap.route_table, self.runner, family,
                    self._throws(rules, family),
                )
            if via_tun:
                iprule.ensure_tun(
                    cap.mark_proxy, cap.tun_route_table, self.runner, family, rules.tun_name
                )
        if rules.containers:
            iprule.ensure_containers(
                cap.mark_containers, cap.tun_route_table, self.runner, self._tun_dev(rules)
            )

    def _routes_down(self, rules: nft.Rules) -> None:
        """Правила `ip rule` и маршруты, которые текущим правилам не нужны (остались от
        другого режима, от ipv6 = proxy или от снятого перехвата)."""
        cap = self.cfg.capture
        for family in self._families():
            tproxy, via_tun = self._wanted(rules, family)
            if not tproxy:
                iprule.remove(cap.mark_proxy, cap.route_table, self.runner, family)
            if not via_tun:
                # Маршруты таблицы TUN остаются, пока они нужны контейнерам (только IPv4).
                iprule.remove_tun(
                    cap.mark_proxy, cap.tun_route_table, self.runner, family, cap.tun_name,
                    keep_routes=family == 4 and bool(rules.containers),
                )
        if not rules.containers:
            iprule.remove_containers(
                cap.mark_containers, cap.tun_route_table, self.runner, cap.tun_name,
                keep_routes=rules.tun,
            )

    def _applied(self) -> dict | None:
        """Применённый конфиг Xray — тот, с которым ядро запущено или запустится."""
        try:
            config = json.loads(self.paths.xray_config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return config if isinstance(config, dict) else None

    def inbound_problem(self) -> str:
        """Почему перехват включать нельзя: какого inbound'а нет в применённом конфиге
        Xray. Пусто — всё, на что ссылаются правила, в конфиге есть.

        Смотрим именно применённый конфиг (`paths.xray_config_file`), а не собранный:
        правила отправляют пакеты на `capture.tproxy_port` или в интерфейс TUN, а
        принимает их только тот Xray, который запущен с этим конфигом. Нет inbound'а —
        пакеты уходят в никуда, и при fail_mode = "closed" машина остаётся без интернета.
        IPv6 (tproxy-in6) здесь не проверяется намеренно: без него закрыт только IPv6, и
        программы переходят на IPv4, а снять из-за этого весь перехват было бы хуже.
        """
        rules = self.rules("on")
        if not rules.capture:
            return ""
        config = self._applied()
        if config is None:
            return f"рабочего конфига Xray ещё нет ({self.paths.xray_config_file})"
        listed = config.get("inbounds")
        inbounds = [item for item in listed if isinstance(item, dict)] if isinstance(
            listed, list) else []
        if rules.tproxy:
            # Порт обязан совпадать: правила отправляют пакеты именно на него.
            port = self.cfg.capture.tproxy_port
            if not any(
                item.get("tag") == TPROXY_TAG and item.get("port") == port for item in inbounds
            ):
                return f"в применённом конфиге Xray нет inbound {TPROXY_TAG} на порту {port}"
        if rules.tun:
            # Имя обязано совпадать: маршрут ведёт пакеты именно в этот интерфейс.
            names = {
                item["settings"].get("name")
                for item in inbounds
                if item.get("protocol") == "tun" and isinstance(item.get("settings"), dict)
            }
            if rules.tun_name not in names:
                return (
                    f"в применённом конфиге Xray нет inbound {TUN_TAG} "
                    f"для интерфейса {rules.tun_name}"
                )
        return ""

    def effective_mode(self) -> str:
        """Режим, который на самом деле загружается: «on» без нужного inbound'а в Xray
        становится «blocked» (capture.hold = "block": мимо VPN ничего, пока конфиг не
        применён) или «off» (hold = "direct": сеть напрямую)."""
        mode = self.mode()
        return self.hold_mode() if mode == "on" and self.inbound_problem() else mode

    def hold_mode(self) -> str:
        """Чем заменить «on», пока перехват включить нельзя. Рабочего конфига Xray нет вовсе
        (первая установка, подписки ещё нет) — VPN ещё нечем включать, и закрыть сеть значило
        бы оставить машину без интернета, пока человек ищет подписку: тогда «off» и при
        hold = "block". Конфиг есть, но без нужного inbound'а — это минуты до перезапуска
        Xray, и тогда hold решает."""
        if self.cfg.capture.hold_blocks and self._applied() is not None:
            return "blocked"
        return "off"

    def _containers_tun(self, rules: nft.Rules) -> bool:
        """Интерфейс TUN нужен контейнерам: их перехват включён, и применённый конфиг Xray
        с inbound'ом TUN (он там, только когда Docker на машине есть)."""
        if not rules.containers:
            return False
        applied = self._applied()
        return applied is not None and tun.inbound_name(applied) == rules.tun_name

    def _prepare_tun(self) -> str:
        """Создаёт интерфейс TUN для режима «on» и убеждается, что он есть в системе.
        Пусто — есть (или не нужен), иначе причина: без интерфейса маршрут помеченных
        пакетов вёл бы в никуда. Отказ самой команды создания — ошибка (CommandError):
        её исправляет человек (нет /dev/net/tun, имя занято), сама она не пройдёт."""
        rules = self.rules("on")
        if rules.tun:
            tun.ensure(rules.tun_name, self.runner, self.proc_sys)
            if tun.present(rules.tun_name, self.runner):
                return ""
            return f"TUN-интерфейса {rules.tun_name} нет в системе"
        if self._containers_tun(rules):
            # Интерфейс нужен только контейнерам. Без XGW его создал бы сам Xray — без
            # адреса, и контейнеры остались бы без интернета (так было после перезагрузки).
            # Неудача перехват не держит: машина и LAN идут через TPROXY, а контейнеры без
            # интерфейса закрыты чёрной дырой.
            try:
                tun.ensure(rules.tun_name, self.runner, self.proc_sys)
            except (cmd.CommandError, OSError) as exc:
                self.log.warning("интерфейс %s для контейнеров не подготовлен: %s",
                                 rules.tun_name, exc)
        return ""

    def _tun_problem(self, rules: nft.Rules) -> str:
        """Что не так с интерфейсом TUN, который нужен машине или контейнерам; пусто — всё
        в порядке либо он не нужен. Контейнерам интерфейса может и не быть: пока его нет,
        они закрыты чёрной дырой (Xray не запущен)."""
        name = rules.tun_name
        if not (rules.tun or self._containers_tun(rules)):
            return ""
        if not tun.present(name, self.runner):
            return f"интерфейса {name} нет" if rules.tun else ""
        if not tun.ready(name, self.runner):
            return (f"у интерфейса {name} нет адреса {tun.ADDRESS} или он не поднят: "
                    "ответы Xray ядро отбрасывает")
        return ""

    def tun_problem(self) -> str:
        """То же для текущего режима — для `xgw diag`."""
        try:
            return self._tun_problem(self.rules(self.effective_mode()))
        except cmd.CommandError as exc:
            self.log.debug("интерфейс TUN не проверен: %s", exc)
            return ""

    def _load(self, mode: str) -> str:
        self.held = ""
        if mode == "on":
            # Правила перехвата отправляют пакеты на tproxy_port или в TUN. Если в
            # применённом конфиге Xray такого inbound'а нет (изменение настроек ещё не
            # применено, откат на прежний конфиг) либо нет самого интерфейса, включать
            # перехват нельзя: трафик ушёл бы в никуда. Загружаем режим blocked (мимо VPN
            # ничего, capture.hold = "block") или «снят» (напрямую, hold = "direct"), а
            # перехват включится сам, как только Xray перезапустится с нужным inbound'ом
            # (за этим следит демон).
            try:
                reason = self.inbound_problem() or self._prepare_tun()
            except (cmd.CommandError, OSError) as exc:
                raise CaptureError(str(exc)) from exc
            if reason:
                self.held = reason
                mode = self.hold_mode()
                self.log.error(
                    "перехват не включён: %s — трафик ушёл бы в никуда. %s; перехват "
                    "включится после перезапуска Xray с новым конфигом",
                    reason,
                    "Трафик заблокирован, мимо VPN ничего не уходит" if mode == "blocked"
                    else "Сеть работает напрямую",
                )
        rules = self.rules(mode)
        try:
            if rules.lan_if:
                self._forwarding_on()
            self._congestion()
            if rules.capture:
                # Сначала маршрут для помеченных пакетов (интерфейс TUN уже подготовлен),
                # потом правила, которые метят; ненужное убирается уже после них.
                self._routes_up(rules)
                with self._own_rules():
                    warnings = nft.apply(rules, self.runner)
                self._routes_down(rules)
            else:
                with self._own_rules():
                    warnings = nft.apply(rules, self.runner)
                self._routes_down(rules)
            # Какой набор direct4 загружен (Ф6): loaded() сверяет отпечаток, а не тысячи сетей.
            digest = nft.direct_digest(rules.direct4, rules.direct_local) if rules.direct4 else None
            if self._state().get("direct4") != digest:
                self._save(direct4=digest)
        except (cmd.CommandError, OSError) as exc:
            raise CaptureError(str(exc)) from exc
        for warning in warnings:
            self.log.warning("%s", warning)
        self.tidy()
        # Отпечаток только что загруженных таблиц — для loaded(). Прочитать нельзя — отпечатка
        # нет, и loaded() сверяет как раньше (по цепочкам), а не загружает правила по кругу.
        self._save(tables=self._tables_digest())
        return mode

    def _tables_digest(self, text: str | None = None) -> str | None:
        """Отпечаток таблиц `ip xgw` и `ip6 xgw6` (nft.tables_digest); text — уже прочитанный
        краткий вывод `ip xgw`. None — прочитать нельзя."""
        if text is None:
            text = nft.listing(self.lister, terse=True)
            if text is None:
                return None
        text6 = ""
        if self.ipv6_usable():
            text6 = nft.listing(self.lister, "ip6", nft.TABLE6, terse=True)
            if text6 is None:
                return None
        return nft.tables_digest(
            nft.structure(text, "ip", nft.TABLE), nft.structure(text6, "ip6", nft.TABLE6))

    def tidy(self) -> str:
        """Убирает интерфейс TUN, который больше не нужен: в конфиге не capture.method =
        "tun", а работающий Xray запущен без inbound'а TUN (иначе он держит интерфейс
        открытым). Возвращает, что сделано; пусто — убирать нечего."""
        name = self.cfg.capture.tun_name
        if not name or (self.cfg.capture.local and self.cfg.capture.tun):
            return ""
        applied = self._applied()
        if applied is not None and tun.inbound_name(applied) == name:
            return ""  # Xray ещё не перезапущен с новым конфигом
        try:
            if not tun.present(name, self.runner):
                return ""
            tun.remove(name, self.runner)
        except cmd.CommandError as exc:
            self.log.error("интерфейс %s не убран: %s", name, exc)
            return ""
        text = f"интерфейс {name} убран: он больше не нужен ни этой машине, ни контейнерам"
        self.log.info("%s", text)
        return text

    def restore_tun(self) -> str:
        """После запуска Xray: интерфейс TUN поднят, с адресом, и маршруты в него на месте.

        Xray новее 26.3.27 при остановке выключает интерфейс (ip link set down), и ядро
        удаляет маршруты через него. Запустившись снова, Xray интерфейс поднимает, а
        маршрута уже нет: трафик машины (capture.method = "tun") и контейнеров уходил бы в
        чёрную дыру до ближайшего шага демона. Поэтому xgw-xray.service после каждого
        запуска вызывает `xgw net tun`. Правила nftables здесь не загружаются: перехват
        снят или ещё не загружен — делать нечего. Возвращает, что сделано; пусто — ничего
        не понадобилось."""
        with self._lock():
            if self.effective_mode() != "on":
                return ""
            rules = self.rules("on")
            if not (rules.tun or self._containers_tun(rules)):
                return ""
            try:
                chains = nft.loaded_chains(self.runner) or set()
                if not chains & {"output", "containers"}:
                    return ""
                tun.ensure(rules.tun_name, self.runner, self.proc_sys)
                self._routes_up(rules)
            except (cmd.CommandError, OSError) as exc:
                raise CaptureError(str(exc)) from exc
            return f"интерфейс {rules.tun_name} поднят, маршруты в него на месте"

    def tailscale_direct(self, xray_down: bool) -> str:
        """tailscale.route = "vpn": пока Xray не отвечает, сокеты tailscaled идут напрямую —
        иначе удалённый доступ пропал бы вместе с VPN. Метка в наборе ts_direct меняется
        без перезагрузки таблиц (соединения не рвутся), а отметка в /run нужна, чтобы и
        загрузка правил заново (loaded, xgw-net) собрала набор таким же. Возвращает, что
        сделано; пусто — менять нечего."""
        vpn = self.cfg.tailscale.route == "vpn" or self.ts_fallback_marker.exists()
        wanted = xray_down and vpn
        if wanted == self.ts_marker.exists():
            return ""
        if not vpn:
            # route сменили на "direct": отметка не нужна, набор соберёт загрузка правил.
            self.ts_marker.unlink(missing_ok=True)
            return ""
        with self._lock():
            if wanted:
                self.ts_marker.parent.mkdir(parents=True, exist_ok=True)
                self.ts_marker.touch()
            else:
                self.ts_marker.unlink(missing_ok=True)
            rules = self.rules(self.effective_mode())
            text = nft.ts_elements(rules) if rules.capture else ""
            if text:
                try:
                    with self._own_rules():
                        self.runner(["nft", "-f", "-"], input=text)
                except (cmd.CommandError, OSError) as exc:
                    # Правила сверит loaded() на этом же шаге и загрузит заново.
                    self.log.warning("набор %s не изменён: %s", nft.TS_SET, exc)
        if not text:
            return ""
        return ("Xray не отвечает — Tailscale идёт напрямую, мимо VPN" if wanted
                else "Xray отвечает — Tailscale снова идёт через VPN")

    def tailscale_fallback(self, on: bool) -> str:
        """tailscale.route = "direct", а серверы DERP напрямую не отвечают (ТЗ R4b): сокеты
        tailscaled временно идут через Xray (on) — или снова напрямую. Как tailscale_direct:
        набор ts_direct меняется без перезагрузки таблиц, отметка в /run — для xgw-net.
        Возвращает, что сделано; пусто — менять нечего."""
        wanted = on and self.cfg.tailscale.route == "direct"
        if wanted == self.ts_fallback_marker.exists():
            return ""
        with self._lock():
            if wanted:
                self.ts_fallback_marker.parent.mkdir(parents=True, exist_ok=True)
                self.ts_fallback_marker.touch()
            else:
                self.ts_fallback_marker.unlink(missing_ok=True)
            rules = self.rules(self.effective_mode())
            text = nft.ts_elements(rules) if rules.capture else ""
            if text:
                try:
                    with self._own_rules():
                        self.runner(["nft", "-f", "-"], input=text)
                except (cmd.CommandError, OSError) as exc:
                    # Правила сверит loaded() на этом же шаге и загрузит заново.
                    self.log.warning("набор %s не изменён: %s", nft.TS_SET, exc)
        if wanted:
            return ("серверы DERP Tailscale напрямую не отвечают — tailscaled временно идёт "
                    "через VPN")
        return "серверы DERP Tailscale снова отвечают напрямую — tailscaled идёт напрямую"

    def tailscale_via_vpn(self) -> bool:
        """tailscaled сейчас идёт через VPN по аварийному маршруту (ТЗ R4b)."""
        return self.ts_fallback_marker.exists()

    def up(self) -> str:
        """Загружает правила текущего режима (после перезагрузки, после сбоя)."""
        with self._lock():
            return self._load(self.mode())

    def enable(self) -> str:
        with self._lock():
            mode = self._load("on" if self.capturing else "none")
            # Выбор запоминается, только когда правила действительно загружены.
            self._save(enabled=True)
            self.open_marker.unlink(missing_ok=True)
            return mode

    def disable(self) -> str:
        """Снимает перехват (prerouting, output, ip rule); форвардинг с
        маскарадингом остаётся — сеть работает напрямую."""
        with self._lock():
            mode = self._load("off" if self.capturing else "none")
            self._save(enabled=False)
            self.open_marker.unlink(missing_ok=True)
            return mode

    def open(self) -> str:
        """fail_mode = "open": временно снять перехват, выбор пользователя не трогая."""
        with self._lock():
            self.open_marker.parent.mkdir(parents=True, exist_ok=True)
            self.open_marker.touch()
            return self._load(self.mode())

    def close(self) -> str:
        """Вернуть перехват после временного снятия."""
        with self._lock():
            self.open_marker.unlink(missing_ok=True)
            return self._load(self.mode())

    def down(self, *, remove_tun: bool = False) -> None:
        """Убирает всё, что XGW добавил в сеть: таблицы, правило, маршрут, форвардинг.

        TUN-интерфейс остаётся, если не сказано иное: его держит открытым работающий
        Xray, и без интерфейса его inbound пришлось бы перезапускать. Удаление
        (`xgw uninstall`) вызывает это уже после остановки служб."""
        with self._lock():
            try:
                with self._own_rules():
                    nft.delete(self.runner)
                self._save(tables=None)  # таблиц нет — сверять loaded() не с чем
                self._routes_down(self.rules("off"))  # перехвата нет: убирается всё
                if remove_tun:
                    tun.remove(self.cfg.capture.tun_name, self.runner)
                self.ts_marker.unlink(missing_ok=True)
                self.ts_fallback_marker.unlink(missing_ok=True)
                self._forwarding_restore()
                self._congestion_restore()
            except (cmd.CommandError, OSError) as exc:
                raise CaptureError(str(exc)) from exc
            self.open_marker.unlink(missing_ok=True)

    def _forwarding_on(self) -> None:
        before = sysctl.read(sysctl.IP_FORWARD, self.proc_sys)
        if before == "1":
            return
        if "ip_forward_before" not in self._state():
            self._save(ip_forward_before=before or "0")
        sysctl.write(sysctl.IP_FORWARD, "1", self.proc_sys)

    def _forwarding_restore(self) -> None:
        before = self._state().get("ip_forward_before")
        if before is None:
            return
        sysctl.write(sysctl.IP_FORWARD, str(before), self.proc_sys)
        self._save(ip_forward_before=None)

    def _congestion(self) -> None:
        """TCP BBR (network.tcp_bbr) для соединений самой машины, в том числе с серверами
        VPN: на канале с потерями и большой задержкой он держит скорость лучше прежнего
        алгоритма. Прежний запоминается и возвращается в down(). Ядро без BBR — не сбой:
        остаётся прежний алгоритм. Модуль tcp_bbr ядро подгружает само, когда процессу с
        CAP_NET_ADMIN нужен этот алгоритм (проверено на ядре 6.18)."""
        if not self.cfg.network.tcp_bbr:
            self._congestion_restore()  # ключ выключили — вернуть, что было до XGW
            return
        current = sysctl.read(sysctl.TCP_CONGESTION, self.proc_sys)
        if current is None or current == "bbr":
            return  # ключа нет (не Linux) или BBR уже включён — XGW его не ставил
        saved = "tcp_congestion_before" in self._state()
        if not saved:
            self._save(tcp_congestion_before=current)
        try:
            sysctl.write(sysctl.TCP_CONGESTION, "bbr", self.proc_sys)
        except OSError as exc:
            if not saved:
                self._save(tcp_congestion_before=None)
            if "bbr" not in self._warned:
                self._warned.add("bbr")
                self.log.info("TCP BBR не включён: ядро его не знает (%s) — остаётся %s",
                              exc, current)

    def _congestion_restore(self) -> None:
        before = self._state().get("tcp_congestion_before")
        if before is None:
            return
        try:
            sysctl.write(sysctl.TCP_CONGESTION, str(before), self.proc_sys)
        except OSError as exc:
            self.log.warning("алгоритм TCP %s не возвращён: %s", before, exc)
            return
        self._save(tcp_congestion_before=None)

    # --- проверка ---------------------------------------------------------------

    def loaded(self, *, tun: bool = True) -> bool | None:
        """Соответствует ли ядро текущему режиму. None — узнать нельзя (нет прав).
        tun=False — без проверки интерфейса TUN: на месте ли сами правила и маршруты."""
        rules = self.rules(self.effective_mode())
        text = nft.listing(self.lister, terse=True, sets=nft.CHECKED_SETS)
        if text is None:
            return None
        listed = nft.parse_chains(text)
        chains = set(listed)
        # Цепочка на месте, а правил в ней нет — её опустошил чужой flush table / flush
        # chain: нужная такая цепочка — всё равно что пропавшая.
        empty = {name for name, filled in listed.items() if not filled}
        guard = self._v6_guard_loaded(rules)
        if guard is not True:
            return guard
        loaded_digest = self._state().get("tables")
        if loaded_digest is not None:
            current = self._tables_digest(text)
            if current is None:
                return None
            if current != loaded_digest:
                return False  # правило убрали или изменили, хотя цепочки на месте
        if not self._ts_loaded(rules, text, rules.ts4, rules.ts4 and rules.capture_local):
            return False  # tailscaled запустился или остановился, набор не тот
        if nft.ts_exit_state(text) != rules.ts_forward:
            return False  # выходной узел: tailscaled запустился или остановился
        if not rules.blocked and nft.quic_loaded(text) != rules.quic:
            return False  # network.block_quic переключили
        if nft.has_set(text, nft.DIRECT_SET) != bool(rules.direct4) or (
                rules.direct4 and self._state().get("direct4")
                != nft.direct_digest(rules.direct4, rules.direct_local)):
            return False  # разгрузку переключили, сменились geoip.dat или direct_ips
        if nft.has_set(text, nft.DIRECT_LAN_SET) != bool(rules.direct_lan) or (
                rules.direct_lan
                and nft.set_elements(text, nft.DIRECT_LAN_SET) != set(rules.direct_lan)):
            return False  # разгрузку устройства включили или выключили
        if rules.ts_forward and nft.set_elements(text, nft.TS_EXIT_SET) != set(
                rules.ts_exit_direct):
            return False  # устройство tailnet пустили напрямую или вернули в Xray
        if nft.has_set(text, nft.FP_SET) != (rules.free_pool and not rules.empty):
            return False  # бесплатный пул включили или выключили (free_pool.mode)
        if rules.blocked:
            wanted: set[str] = set()
            if rules.block_local:
                wanted.add("block_output")
            if rules.lan_if or rules.block_containers:
                wanted.add("forward")
            if rules.lan_if:
                wanted.add("postrouting")
            return wanted <= chains - empty and not chains & {
                "prerouting", "output", "loopback_guard", "containers"}
        if "block_output" in chains:
            return False  # осталась блокировка, а inbound в Xray уже есть
        expected: set[str] = set()
        if rules.capture:
            expected.add("loopback_guard")
        if rules.prerouting:
            expected.add("prerouting")
        if rules.containers:
            expected.add("containers")
        if rules.capture_local:
            expected.add("output")
        if rules.lan_if:
            expected |= {"forward", "postrouting"}
        if not expected <= chains - empty:
            return False
        if not rules.capture:
            return not chains & {"prerouting", "output", "loopback_guard"}
        if not rules.prerouting and "prerouting" in chains:
            return False  # остался TPROXY самой машины от capture.method = "tproxy"
        if not rules.containers and "containers" in chains:
            return False  # capture.containers выключили
        if rules.capture6 or self.ipv6_usable():
            listed6 = nft.chain_rules(self.lister, "ip6", nft.TABLE6)
            if listed6 is None:
                return None
            chains6 = set(listed6)
            captured6 = {"output", "loopback_guard"}
            if rules.prerouting6:
                captured6.add("prerouting")
            filled6 = {name for name, filled in listed6.items() if filled}
            if rules.capture6 and not captured6 <= filled6:
                return False
            if not rules.capture6 and chains6 & {"prerouting", "output", "loopback_guard"}:
                return False  # остались правила от ipv6 = proxy
            if rules.capture6 and not rules.prerouting6 and "prerouting" in chains6:
                return False
        cap = self.cfg.capture
        with contextlib.suppress(cmd.CommandError):
            if tun and self._tun_problem(rules):
                return False
            for family in self._families():
                tproxy, via_tun = self._wanted(rules, family)
                if tproxy and not iprule.present(
                    cap.mark_proxy, cap.route_table, self.runner, family,
                    self._throws(rules, family),
                ):
                    return False
                if via_tun and not iprule.present_tun(
                    cap.mark_proxy, cap.tun_route_table, self.runner, family, rules.tun_name
                ):
                    return False
                # Лишнее от другого режима: правило TUN после возврата на tproxy и наоборот.
                if not via_tun and iprule.has_rule(
                    cap.mark_proxy, cap.tun_route_table, self.runner, family, "lo"
                ):
                    return False
                if not tproxy and iprule.has_rule(
                    cap.mark_proxy, cap.route_table, self.runner, family
                ):
                    return False
            if rules.containers and not iprule.present_containers(
                cap.mark_containers, cap.tun_route_table, self.runner, self._tun_dev(rules)
            ):
                return False  # маршрут контейнеров пропал либо появился интерфейс TUN
            # Лишнее: маршрут контейнеров остался, хотя capture.containers выключили.
            return bool(rules.containers) or not iprule.has_rule(
                cap.mark_containers, cap.tun_route_table, self.runner
            )
        return None

    def _v6_guard_loaded(self, rules: nft.Rules) -> bool | None:
        """v6_guard (и исключения Tailscale в `ip6 xgw6`) в ядре ровно тогда, когда нужны;
        None — узнать нельзя."""
        if not self.ipv6_usable():
            return True  # таблицы ip6 в таком ядре нет, закрывать нечего
        text6 = nft.listing(self.lister, "ip6", nft.TABLE6)
        if text6 is None:
            return None
        listed6 = nft.parse_chains(text6)
        if not self._ts_loaded(rules, text6, rules.ts6, rules.ts6):
            return False
        if rules.v6_guard:
            return bool(listed6.get("v6_guard"))  # и пустой (flush) — не загружен
        return "v6_guard" not in listed6

    @staticmethod
    def _ts_loaded(rules: nft.Rules, text: str, wanted: bool, with_set: bool) -> bool:
        """Исключения Tailscale в таблице есть ровно тогда, когда нужны, а метка в наборе
        ts_direct — та, что нужна сейчас."""
        has, direct = nft.ts_state(text)
        if has != wanted:
            return False
        return direct == rules.ts_direct if with_set else direct is None

    def tailscale_loaded(self) -> bool | None:
        """Для `xgw diag`: исключения Tailscale загружены (или не нужны); None — узнать
        нельзя."""
        rules = self.rules(self.effective_mode())
        text = nft.listing(self.lister, terse=True, sets=(nft.TS_SET,))
        if text is None:
            return None
        if not self._ts_loaded(rules, text, rules.ts4, rules.ts4 and rules.capture_local):
            return False
        if not self.ipv6_usable():
            return True
        text6 = nft.listing(self.lister, "ip6", nft.TABLE6, terse=True, sets=(nft.TS_SET,))
        if text6 is None:
            return None
        return self._ts_loaded(rules, text6, rules.ts6, rules.ts6)

    def lan_path(self) -> str:
        """Доходит ли помеченный пакет клиента LAN до TPROXY: '' — да (или проверять нечего:
        LAN не перехватывается, перехват не включён, интерфейс LAN выключен); иначе —
        причина для журнала, панели и `xgw diag`."""
        if self.mode() != "on":
            return ""
        rules = self.rules("on")
        gateway = lan.gateway(self.cfg)
        if not (rules.capture_lan and rules.lan_if and rules.tproxy) or gateway is None:
            return ""
        try:
            links = json.loads(self.runner(["ip", "-j", "link", "show", "dev", rules.lan_if]))
        except (cmd.CommandError, json.JSONDecodeError):
            return ""  # интерфейса нет — об этом говорят другие проверки
        if not links or "UP" not in (links[0].get("flags") or []):
            return ""  # интерфейс выключен: ядро отвечает на проверку ошибкой и без сбоя
        host = next(
            (str(item) for item in gateway.network.hosts() if item != gateway.ip), ""
        )
        if not host:
            return ""
        argv = ["ip", "-j", "route", "get", LAN_PROBE_TARGET, "from", host,
                "iif", rules.lan_if, "mark", str(self.cfg.capture.mark_proxy)]
        try:
            routes = json.loads(self.runner(argv) or "[]")
        except cmd.CommandError as exc:
            mark = sysctl.read(sysctl.SRC_VALID_MARK, self.proc_sys)
            why = (
                f" (net.ipv4.conf.all.src_valid_mark = {mark}: ядро проверяет источник с "
                "учётом метки)" if mark == "1" else ""
            )
            return (
                f"пакеты устройств сети {rules.lan_if} не доходят до Xray: ядро их "
                f"отбрасывает{why} — {str(exc).strip().splitlines()[-1]}"
            )
        except json.JSONDecodeError:
            return ""
        route = routes[0] if routes and isinstance(routes[0], dict) else {}
        if route.get("type") == "local":
            return ""
        where = route.get("dev") or "?"
        return (
            f"пакеты устройств сети {rules.lan_if} не доходят до Xray: ядро ведёт их "
            f"{route.get('type') or 'unicast'} через {where}, а не в TPROXY"
        )

    def describe(self, *, check: bool = True) -> dict:
        """Сведения для `xgw status`."""
        rules = self.rules("on")
        loaded = self.loaded() if check else None
        # Правила на месте, не готов только интерфейс TUN (нет адреса): это не «правила не
        # загружены» — у `xgw diag` на это своя строка, а `xgw status` называет причину.
        tun_only = ""
        if loaded is False:
            problem = self.tun_problem()
            if problem and self.loaded(tun=False) is True:
                tun_only = problem
        missing = (self.inbound_problem() or self.held) if self.mode() == "on" else ""
        return {
            "mode": self.mode(),
            "lan_if": rules.lan_if,
            "lan": rules.capture_lan,
            "local": rules.capture_local,
            "bypass": list(rules.bypass),
            "ipv6": rules.capture6,
            "tun": rules.tun,
            "containers": bool(rules.containers),
            # Сколько сетей идёт ядром мимо Xray (routing.kernel_direct, Ф6); 0 — нисколько.
            "direct4": len(rules.direct4),
            # Docker на машине есть (его мост уже создан): только тогда о контейнерах
            # стоит говорить в статусе.
            "docker": bool(lan.container_links(rules.containers, self.sys_net)),
            "fail_mode": self.cfg.capture.fail_mode,
            "hold": "block" if self.cfg.capture.hold_blocks else "direct",
            "loaded": loaded,
            "tun_problem": tun_only,
            # Перехват включён, но Xray работает без нужного inbound'а: вместо правил
            # перехвата загружен режим blocked или «снят» (см. _load). Здесь — чего не
            # хватает; пусто — всё на месте.
            # (или не появился интерфейс TUN — это помнит сам объект после загрузки).
            "inbound_missing": missing,
            # При этом трафик закрыт (hold = "block"), а не идёт напрямую.
            "blocked": bool(missing) and self.hold_mode() == "blocked",
        }
