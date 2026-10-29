"""`xgw diag` — проверки машины с вердиктом OK, WARN или FAIL и советом (раздел 6.9).

Ничего не меняет в системе. Правила nftables проверяются в отдельном сетевом
пространстве имён (`unshare -n`): ядро принимает их по-настоящему, а сеть
машины при этом не затрагивается. FAIL — установку начинать нельзя.

Перед установкой (preinstall) состояние уже установленного XGW — службы, загруженные
правила, интерфейс TUN — не FAIL, а WARN: это установка и исправит (перезапустит службы,
загрузит правила заново). Иначе обновление на версию с новой службой или цепочкой правил
требовало бы --force.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from . import cores, engine, fetch, log, masking, tray
from . import tailscale as ts
from .config import SINGBOX_VERSION, XRAY_VERSION, Config, probe_bytes
from .generator import builder, validate
from .generator import singbox as singboxing
from .generator.builder import BALANCER_TAG
from .install import SINGBOX_UNIT, UNITS
from .net import cmd, dnsmasq, lan, nft, nm, sleep, sysctl, ufw
from .net.capture import Capture
from .paths import Paths
from .sbcore import binary as sbbinary
from .store import Store
from .watch import checks as probes
from .watch import hosts as probehosts
from .watch import resolvers as resolving
from .watch import scan, status, target
from .xraycore import binary, metrics

OK, WARN, FAIL = "OK", "WARN", "FAIL"
STATUS_PAGE_PORT = 8780
OS_RELEASE = Path("/etc/os-release")
# Где XGW проверен: 24.04 — настоящая машина (все отчёты с неё), 26.04 — стенды.
TESTED_UBUNTU = ("24.04", "26.04")
DEV_TUN = Path("/dev/net/tun")
PROC = Path("/proc")
CHRONY_DIR = Path("/etc/chrony")
# Пользователь службы времени → её юнит (chrony в 26.04, systemd-timesyncd в 24.04).
TIME_UNITS = {"_chrony": "chrony", "systemd-timesync": "systemd-timesyncd"}


@dataclass(frozen=True)
class Check:
    name: str
    level: str
    text: str
    advice: str = ""


def render(checks: Sequence[Check]) -> str:
    lines: list[str] = []
    for check in checks:
        lines.append(f"{check.level:<4}  {check.name}: {check.text}")
        if check.advice:
            lines.append(f"      → {check.advice}")
    counts = {level: sum(1 for check in checks if check.level == level)
              for level in (OK, WARN, FAIL)}
    lines.append(f"Итог: OK — {counts[OK]}, WARN — {counts[WARN]}, FAIL — {counts[FAIL]}")
    return "\n".join(lines)


def can_bind(port: int) -> bool:
    """Свободен ли TCP-порт на 127.0.0.1."""
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


class Diag:
    def __init__(
        self,
        cfg: Config,
        paths: Paths,
        *,
        runner: cmd.Runner = cmd.run,
        logger=None,
        net: bool = True,
        config_error: str = "",
        config_warnings: Sequence[str] = (),
        which: Callable[[str], str | None] = shutil.which,
        is_root: bool | None = None,
        os_release: Path = OS_RELEASE,
        port_free: Callable[[int], bool] = can_bind,
        proc_sys: Path = sysctl.PROC_SYS,
        dev_tun: Path = DEV_TUN,
        preinstall: bool = False,
        proc: Path = PROC,
    ) -> None:
        self.proc_sys = proc_sys
        self.proc = proc
        self.preinstall = preinstall
        self.dev_tun = dev_tun
        self.cfg = cfg
        self.paths = paths
        self.runner = runner
        self.log = logger or log.get_logger("diag")
        self.net = net
        self.config_error = config_error
        self.config_warnings = list(config_warnings)
        self.which = which
        if is_root is None:
            is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        self.root = is_root
        self.os_release = os_release
        self.port_free = port_free
        self.lan_if = lan.lan_interface(cfg)
        self.installed = (paths.systemd_dir / "xgw.service").exists()
        self.xray_bin = validate.find_xray(None, paths)
        self._xray_up: bool | None = None

    def run(self) -> list[Check]:
        groups: list[tuple[str, Callable[[], list[Check]]]] = [
            ("Система", self._system),
            ("Конфиг", self._config),
            ("Программы", self._programs),
            ("Xray", self._xray),
            ("Ядро", self._kernel),
            ("TUN", self._tun),
            ("Путь LAN", self._lan_path),
            ("Файрвол", self._firewall),
            ("NetworkManager", self._nm),
            ("Подсеть LAN", self._lan_subnet_conflict),
            ("Порты", self._ports),
            ("Xray API", self._xray_api),
            ("sing-box", self._singbox),
            ("Время", self._time),
            ("Сон", self._sleep),
            ("IPv6", self._ipv6),
            ("Службы", self._services),
            ("Журнал", self._journal),
            ("Панель", self._panel_login),
            ("Трафик проверок", self._budget),
            ("Tailscale", self._tailscale),
            ("Бесплатный пул", self._free_pool),
        ]
        groups += [
            ("QUIC", self._quic),
            ("Мимо Xray", self._kernel_direct),
            ("Проверочные хосты", self._probe_hosts),
            ("Значок в трее", self._tray),
        ]
        if self.net:
            groups += [("probe.url", self._probe), ("bootstrap DNS", self._bootstrap)]
        result: list[Check] = []
        for name, group in groups:
            try:
                result.extend(group())
            except Exception as exc:  # одна проверка не должна ронять остальные
                self.log.error("diag, проверка «%s»: %s", name, exc)
                result.append(Check(name, WARN, f"проверка не выполнена: {exc}"))
        return result

    # --- система и конфиг -------------------------------------------------------

    def _system(self) -> list[Check]:
        if not sys.platform.startswith("linux"):
            return [Check("Система", FAIL, "XGW работает только в Linux (Ubuntu 24.04 или 26.04)")]
        release: dict[str, str] = {}
        try:
            for line in self.os_release.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.partition("=")
                if sep:
                    release[key] = value.strip().strip('"')
        except OSError:
            pass
        name = release.get("PRETTY_NAME") or "неизвестная система"
        python = f"Python {sys.version_info.major}.{sys.version_info.minor}"
        result: list[Check] = []
        if release.get("ID") == "ubuntu" and release.get("VERSION_ID") in TESTED_UBUNTU:
            result.append(Check("Система", OK, f"{name}, {python}"))
        else:
            result.append(Check(
                "Система", WARN,
                f"{name}, {python} — XGW проверялся только на Ubuntu 24.04 и 26.04",
            ))
        if not self.root:
            result.append(Check(
                "Права", WARN, "запущено без root — проверки ядра, файрвола и портов пропущены",
                "sudo xgw diag",
            ))
        return result

    def _config(self) -> list[Check]:
        path = self.paths.config_file
        if self.config_error:
            return [Check(
                "Конфиг", FAIL, self.config_error,
                f"sudo xgw install создаст {path} из примера; подписку можно добавить "
                "после установки в панели",
            )]
        result: list[Check] = []
        try:
            if path.stat().st_mode & 0o077:
                result.append(Check(
                    "Конфиг", WARN, f"{path} доступен другим пользователям, а в нём подписка",
                    f"sudo chmod 600 {path}",
                ))
        except OSError:
            pass
        if self.config_warnings:
            result.append(Check("Конфиг", WARN, "; ".join(self.config_warnings)))
        if self.cfg.capture.fail_mode == "open":
            result.append(Check(
                "Конфиг", WARN,
                "capture.fail_mode = open: когда API Xray не отвечает, через минуту перехват "
                "снимается и трафик идёт напрямую, мимо VPN",
                'fail_mode = "closed" в [capture] — без Xray интернета нет, но и утечки нет',
            ))
        plain = [sub.name for sub in self.cfg.subscriptions
                 if sub.url.startswith("http://") and not _local_url(sub.url)]
        if plain:
            result.append(Check(
                "Конфиг", WARN,
                f"подписка по http ({', '.join(plain)}): по дороге её ответ можно подменить "
                "своими серверами",
                "адрес подписки с https:// — его даёт провайдер",
            ))
        if not result:
            mode = f"сеть {self.lan_if} и эта машина" if self.lan_if else "только эта машина"
            result.append(Check("Конфиг", OK, f"{path} читается; режим — {mode}"))
        return result

    def _programs(self) -> list[Check]:
        required = ["ip", "systemctl"]
        if self.lan_if:
            required.append("nmcli")
        missing = [name for name in required if self.which(name) is None]
        later = [] if self.which("nft") is not None else ["nftables"]
        # DHCP раздаёт своя служба xgw-dhcp: нужна только программа из dnsmasq-base.
        if self.lan_if and self.which("dnsmasq") is None:
            later.append(dnsmasq.PACKAGE)
        if missing:
            return [Check(
                "Программы", FAIL, "не найдены: " + ", ".join(missing),
                "XGW рассчитан на Ubuntu Desktop с NetworkManager и systemd",
            )]
        if later:
            return [Check(
                "Программы", WARN, "пакеты " + ", ".join(later) + " не установлены",
                "sudo xgw install поставит их из apt",
            )]
        return [Check("Программы", OK, "nft, ip, systemctl" + (
            ", nmcli, dnsmasq" if self.lan_if else "") + " на месте")]

    # --- Xray -------------------------------------------------------------------

    def _xray(self) -> list[Check]:
        if self.xray_bin is None:
            return [Check(
                "Xray", WARN, f"не установлен ({self.paths.xray_bin})",
                "sudo xgw install загрузит его с GitHub и сверит SHA-256",
            )]
        version = binary.installed_version(self.xray_bin)
        if version is None:
            return [Check("Xray", FAIL, f"{self.xray_bin} не запускается", "sudo xgw update-xray")]
        text = ".".join(map(str, version))
        if version < binary.MIN_VERSION:
            return [Check(
                "Xray", FAIL,
                f"версия {text} ниже {binary.min_version_text()}: поля httpMethod в ней нет, "
                "серверы проверялись бы HEAD-запросом и «заморозка» осталась бы незамеченной",
                "sudo xgw update-xray",
            )]
        if not binary.has_string(self.xray_bin, b"httpMethod"):
            return [Check(
                "Xray", FAIL, f"версия {text}, но поля httpMethod в бинарнике нет",
                "sudo xgw update-xray",
            )]
        if version != binary.parse_version(XRAY_VERSION):
            if cores.allowed(self.paths, "xray", version):
                # Новее проверенной, но обновлена из панели и прошла проверку на этом шлюзе.
                return [Check("Xray", OK, (
                    f"версия {text} — обновлена из панели и проверена шлюзом (XGW проверен на "
                    f"{XRAY_VERSION}), GET-проверка (httpMethod) поддерживается"
                ))]
            # Другую версию XGW не использует (config.XRAY_VERSION); перед установкой это
            # не ошибка — установка поставит нужную.
            return [Check(
                "Xray", WARN if self.preinstall else FAIL,
                f"версия {text}, а XGW работает только с Xray {XRAY_VERSION} или с версией, "
                "принятой шлюзом после обновления из панели",
                "установка поставит нужную версию" if self.preinstall
                else "sudo xgw update-xray",
            )]
        return [Check("Xray", OK, f"версия {text}, GET-проверка (httpMethod) поддерживается")]

    # --- sing-box (второе ядро) ---------------------------------------------------

    def _singbox(self) -> list[Check]:
        """Бинарник нужной версии, конфиг, который он принимает, и отсутствие ошибок в его
        журнале. Выключенный (`core.mode = "xray"`) или не нужный подпискам — не ошибка."""
        if self.cfg.core.mode == "xray":
            return [Check("sing-box", OK, "выключен в [core] (mode = xray)")]
        path = singboxing.find_binary(None, self.paths)
        if path is None:
            return [Check(
                "sing-box", WARN,
                f"не установлен ({self.paths.singbox_bin}): серверы hysteria2, TUIC, AnyTLS и "
                "WireGuard пропускаются",
                "sudo xgw install или sudo xgw update-singbox",
            )]
        version = singboxing.installed_version(path)
        if version is None:
            return [Check("sing-box", FAIL, f"{path} не запускается", "sudo xgw update-singbox")]
        text = ".".join(map(str, version))
        note = ""
        if version != sbbinary.parse_version(SINGBOX_VERSION):
            if not cores.allowed(self.paths, "sing-box", version):
                return [Check(
                    "sing-box", WARN if self.preinstall else FAIL,
                    f"версия {text}, а XGW работает только с sing-box {SINGBOX_VERSION} или с "
                    "версией, принятой шлюзом после обновления из панели",
                    "установка поставит нужную версию" if self.preinstall
                    else "sudo xgw update-singbox",
                )]
            note = f" — обновлена из панели и проверена шлюзом (XGW проверен на {SINGBOX_VERSION})"
        result = [Check("sing-box", OK, f"версия {text}{note}")]
        if not self.paths.singbox_config_file.exists():
            return result  # серверов для sing-box нет: служба не запущена, и это нормально
        applied = engine.read_json(self.paths.singbox_config_file)
        if applied is None:
            result.append(Check(
                "sing-box: конфиг", FAIL, f"{self.paths.singbox_config_file} не читается",
                "sudo xgw apply --now (конфиг соберётся заново)",
            ))
            return result
        ok, output = singboxing.validate_config(applied, path)
        lines = [line for line in output.splitlines() if line.strip()]
        if ok is False:
            result.append(Check(
                "sing-box: конфиг", FAIL,
                f"sing-box check не принял {self.paths.singbox_config_file}: "
                + (lines[-1] if lines else "ошибка"),
                "sudo xgw apply --now (конфиг соберётся заново)",
            ))
        else:
            bridges = len(singboxing.bridge_ports(applied))
            result.append(Check(
                "sing-box: конфиг", OK, f"принят sing-box check, мостов: {bridges}",
            ))
        if self.installed and self.root:
            errors = self.runner(
                ["journalctl", "-u", "xgw-singbox", "-p", "err", "-n", "20", "--no-pager",
                 "-o", "cat"], check=False,
            ).strip().splitlines()
            errors = [line for line in errors if line.strip() and not line.startswith("--")]
            if errors:
                result.append(Check(
                    "sing-box: журнал", WARN,
                    f"в журнале службы есть ошибки ({len(errors)}), последняя: "
                    + masking.mask_text(errors[-1])[:200],
                    "sudo journalctl -u xgw-singbox -p err -n 20",
                ))
        return result

    def xray_up(self) -> bool:
        if self._xray_up is None:
            try:
                metrics.fetch_metrics(self.cfg.xray.metrics_port)
                self._xray_up = True
            except Exception:
                self._xray_up = False
        return self._xray_up

    def _xray_api(self) -> list[Check]:
        if self.xray_bin is None or not (self.installed or self.xray_up()):
            return []  # до установки проверять нечего
        try:
            observatory = metrics.parse_observatory(
                metrics.fetch_metrics(self.cfg.xray.metrics_port)
            )
        except Exception as exc:
            return [Check(
                "Xray API", FAIL, f"метрики не отвечают: {exc}",
                "sudo systemctl status xgw-xray; sudo journalctl -u xgw-xray -n 30",
            )]
        if not self.root:
            # Сокет API Xray открыт только группе xray (ASSUMPTIONS п. 253): без sudo отказ —
            # не неисправность.
            return [Check(
                "Xray API", WARN, "метрики отвечают; API проверяется только с sudo",
                "sudo xgw diag",
            )]
        try:
            engine.make_api(self.paths, self.xray_bin).balancer_info(BALANCER_TAG)
        except Exception as exc:
            return [Check("Xray API", FAIL, f"API не отвечает: {exc}",
                          "sudo journalctl -u xgw-xray -n 30")]
        members = {tag: entry for tag, entry in observatory.items() if tag.startswith("proxy-")}
        alive = sum(1 for entry in members.values() if entry["alive"])
        level = OK if alive or not members else WARN
        return [Check(
            "Xray API", level,
            f"API и метрики отвечают; живых участников {alive} из {len(members)}",
            "" if level == OK else "sudo xgw probe --all покажет, что с серверами",
        )]

    # --- ядро и файрвол ---------------------------------------------------------

    def _kernel(self) -> list[Check]:
        if not self.root:
            return []
        if self.which("nft") is None:
            return [Check("Ядро", WARN, "nft не установлен — правила проверить нечем",
                          "sudo xgw install поставит nftables")]
        rules, _warnings = nft.build_rules(self.cfg, capture=True)
        if rules.empty:
            return [Check("Ядро", OK, "перехват выключен в конфиге — правила не нужны")]
        text = nft.render(rules) + nft.render6(rules)
        if self.which("unshare") is None:
            try:
                self.runner(["nft", "-c", "-f", "-"], input=text)
            except cmd.CommandError as exc:
                return [Check("Ядро", FAIL, f"nft не принимает правила: {_first_line(exc)}")]
            return [Check("Ядро", WARN, "синтаксис правил верен; ядро не проверено (нет unshare)")]
        try:
            # Отдельное пространство имён: правила загружаются по-настоящему
            # (нужные модули ядро подгружает само) и исчезают вместе с ним.
            self.runner(["unshare", "-n", "nft", "-f", "-"], input=text, timeout=30.0)
        except cmd.CommandError as exc:
            return [Check(
                "Ядро", FAIL, f"ядро не принимает правила перехвата: {_first_line(exc)}",
                "нужны модули nft_tproxy, nft_fib, nft_ct, nft_masq (пакет linux-modules-extra)",
            )]
        return [Check("Ядро", OK, "ядро принимает правила TPROXY (tproxy, fib, ct, masquerade)")]

    def _tun(self) -> list[Check]:
        """Интерфейс TUN — для трафика машины (capture.method = tun) или контейнеров Docker:
        нужен /dev/net/tun, на интерфейсе — адрес XGW, и ответы Xray не должен резать
        rp_filter."""
        cap = self.cfg.capture
        machine = cap.tun and cap.local
        if not (machine or engine.containers_tun(self.cfg)):
            return []
        result: list[Check] = []
        if not self.dev_tun.exists():
            return [Check(
                "TUN", FAIL, f"нет {self.dev_tun}: в ядре нет TUN, Xray не создаст интерфейс",
                "sudo modprobe tun (и добавьте tun в /etc/modules-load.d/xgw.conf)",
            )]
        whom = "" if machine else " — для контейнеров Docker"
        if self.root and self.installed:
            capture = Capture(
                self.cfg, self.paths, runner=self.runner, logger=self.log, proc_sys=self.proc_sys
            )
            problem = capture.tun_problem() if capture.mode() == "on" else ""
            if problem:
                result.append(Check(
                    "TUN", WARN if self.preinstall else FAIL, problem,
                    "установка подготовит интерфейс заново" if self.preinstall
                    else "sudo xgw net up",
                ))
        if not result:
            result.append(Check("TUN", OK, f"{self.dev_tun} есть; интерфейс {cap.tun_name}{whom}"))
        # Действует наибольшее из общего значения (conf.all) и значения интерфейса; самому
        # TUN XGW ставит 2 (net/tun.py), мостам Docker, созданным позже, достаётся
        # conf.default. Строгая проверка — когда наибольшее из двух равно 1.
        def value(where: str) -> int:
            text = sysctl.read(f"net/ipv4/conf/{where}/rp_filter", self.proc_sys) or "0"
            return int(text) if text.isdigit() else 0

        common = value("all")
        if max(common, value(cap.tun_name)) == 1:
            result.append(Check(
                "TUN", WARN,
                f"обратная проверка пути (rp_filter) у {cap.tun_name} строгая: ядро отбросит "
                "ответы Xray из TUN, и трафик зависнет",
                "sudo xgw net up — XGW поставит интерфейсу мягкую проверку (rp_filter=2); "
                "умолчание Ubuntu — 2",
            ))
        if engine.containers_tun(self.cfg):
            bridges = [*lan.container_links(nft.CONTAINER_IFS), "default"]
            strict = [name for name in bridges if max(common, value(name)) == 1]
            if strict:
                where = ", ".join(
                    "новых мостов (conf.default)" if name == "default" else name
                    for name in strict
                )
                result.append(Check(
                    "TUN", WARN,
                    f"строгая обратная проверка пути (rp_filter) у {where}: при "
                    "src_valid_mark = 1 (его ставит Tailscale) ядро отбросит пакеты контейнеров",
                    "sudo xgw install — поставит net.ipv4.conf.all и default.rp_filter = 2 "
                    "(умолчание Ubuntu)",
                ))
        return result

    def _lan_path(self) -> list[Check]:
        """Помеченный пакет клиента LAN доставляется в TPROXY: `ip route get <внешний адрес>
        from <адрес LAN> iif <LAN> mark <mark_proxy>` должен дать local. Ловит весь класс
        «пакеты LAN гибнут после перехвата» — и когда в сети ещё нет ни одного клиента."""
        if not self.installed:
            return []
        capture = Capture(
            self.cfg, self.paths, runner=self.runner, logger=self.log, proc_sys=self.proc_sys
        )
        rules = capture.rules("on")
        if capture.mode() != "on" or not (rules.capture_lan and rules.lan_if):
            return []
        problem = capture.lan_path()
        if problem:
            return [Check(
                "Путь LAN", FAIL, problem,
                "sudo xgw net up — загрузит маршрут throw для подсети LAN; не помогло — "
                "sudo sysctl -w net.ipv4.conf.all.src_valid_mark=0 и пришлите вывод xgw diag",
            )]
        return [Check(
            "Путь LAN", OK, f"пакеты устройств сети {rules.lan_if} доходят до Xray (TPROXY)"
        )]

    def firewall(self) -> list[Check]:
        """Чужие правила фаервола — и для проверки сети (netcheck.py)."""
        return self._firewall()

    def _firewall(self) -> list[Check]:
        if not self.root or self.which("nft") is None:
            return []
        result: list[Check] = []
        try:
            ruleset = json.loads(self.runner(["nft", "-j", "list", "ruleset"], timeout=30.0))
        except (cmd.CommandError, json.JSONDecodeError) as exc:
            return [Check("Файрвол", WARN, f"правила nftables не прочитаны: {_first_line(exc)}")]
        dropping: dict[str, list[str]] = {"forward": [], "input": []}
        docker = False
        flowtables: list[str] = []
        for item in ruleset.get("nftables", []) if isinstance(ruleset, dict) else []:
            flow = item.get("flowtable") if isinstance(item, dict) else None
            if isinstance(flow, dict) and flow.get("table") not in (nft.TABLE, nft.TABLE6):
                flowtables.append(f"{flow.get('family')} {flow.get('table')} {flow.get('name')}")
            chain = item.get("chain") if isinstance(item, dict) else None
            if not chain or chain.get("table") in (nft.TABLE, nft.TABLE6):
                continue
            if str(chain.get("name", "")).startswith("ts-"):
                continue  # цепочки Tailscale: с ним XGW уживается сам (раздел «Tailscale»)
            if str(chain.get("name", "")).startswith("DOCKER"):
                docker = True
            if chain.get("hook") in dropping and chain.get("policy") == "drop":
                dropping[chain["hook"]].append(f"{chain.get('family')} {chain.get('table')}")
        if flowtables:
            # Разгрузка (flow offload) пропускает пакеты уже установленных соединений мимо
            # цепочек — и мимо перехвата XGW (пятый аудит; kernel.org nf_flowtable).
            result.append(Check(
                "Файрвол", WARN,
                f"чужая flowtable ({', '.join(sorted(set(flowtables)))}): соединения из неё идут "
                "мимо цепочек перехвата XGW — трафик может уйти мимо VPN",
                "уберите разгрузку (flow add) для интерфейсов, трафик которых идёт через XGW",
            ))
        ufw_on = self.which("ufw") is not None and ufw.active(self.runner)
        wan_if = lan.effective_wan(self.cfg, self.runner)
        if ufw_on and self.lan_if:
            result.append(self._ufw(wan_if))
        elif ufw_on:
            result.append(Check("ufw", OK, "включён; трафику самой машины не мешает"))
        if docker and dropping["forward"] and self.lan_if:
            result.append(Check(
                "Docker", WARN,
                "ставит политику drop в FORWARD: устройства в обход VPN, ICMP и режим "
                "`xgw disable` не пройдут через шлюз",
                f"sudo iptables -I DOCKER-USER -i {self.lan_if} -j ACCEPT; "
                f"sudo iptables -I DOCKER-USER -o {self.lan_if} -m conntrack "
                "--ctstate RELATED,ESTABLISHED -j ACCEPT",
            ))
        elif dropping["forward"] and self.lan_if and not ufw_on:
            tables = ", ".join(sorted(set(dropping["forward"])))
            result.append(Check(
                "Файрвол", WARN,
                f"чужая цепочка forward с политикой drop ({tables}): форвардинг для устройств "
                "в обход VPN и ICMP может не пройти",
                f"разрешите в ней трафик с интерфейса {self.lan_if}",
            ))
        if dropping["input"] and self.lan_if and not ufw_on:
            tables = ", ".join(sorted(set(dropping["input"])))
            result.append(Check(
                "Файрвол", WARN,
                f"чужая цепочка input с политикой drop ({tables}): перехваченный трафик "
                f"устройств приходит в Xray как входящий с {self.lan_if}",
                f"разрешите в ней входящие с интерфейса {self.lan_if}",
            ))
        if self.runner(["systemctl", "is-enabled", "nftables.service"],
                       check=False).strip() == "enabled":
            result.append(Check(
                "nftables.service", WARN,
                "включена, а её конфиг начинается с flush ruleset: при её перезапуске правила "
                "XGW пропадут, пока демон не вернёт их (до одного шага watchdog)",
                "если своих правил в /etc/nftables.conf нет: sudo systemctl disable nftables",
            ))
        containers = self.cfg.capture.containers and (
            self.cfg.capture.lan or self.cfg.capture.local)
        has_docker = docker or bool(lan.container_links(nft.CONTAINER_IFS))
        if has_docker and not containers and (self.cfg.capture.lan or self.cfg.capture.local):
            result.append(Check(
                "Docker", WARN,
                "контейнеры выходят в интернет мимо VPN: capture.containers = false",
                "впишите capture.containers = true в /etc/xgw/config.toml",
            ))
        if not result:
            text = "ufw и Docker перехвату не мешают"
            if has_docker and containers:
                text += "; контейнеры Docker — через VPN"
            result.append(Check("Файрвол", OK, text))
        return result

    def _ufw(self, wan_if: str) -> Check:
        """ufw включён, есть LAN: хватает ли правил, чтобы устройства вышли в сеть."""
        listed = self.runner(["ufw", "status"], timeout=20.0, check=False)
        before = ufw.before_rules(self.paths.root)
        mark = self.cfg.capture.mark_proxy
        missing: list[str] = []
        if f"on {self.lan_if}" not in listed:
            missing += ["sudo ufw " + " ".join(rule) for rule in ufw.wanted(self.lan_if, wan_if)]
        if self.cfg.capture.lan and not ufw.has_tproxy_rule(before, self.lan_if, mark):
            missing.append(
                f"в {before} перед строкой «{ufw.ANCHOR}» — "
                f"«{ufw.tproxy_rule(self.lan_if, mark)}», затем sudo ufw reload"
            )
        if not missing:
            return Check("ufw", OK, f"включён, правила для {self.lan_if} есть")
        text = (
            f"включён и запрещает входящие: устройства за {self.lan_if} останутся без "
            "интернета (перехваченные пакеты ufw отбрасывает в ufw-not-local)"
        )
        if self.installed:
            return Check("ufw", FAIL, text, "; ".join(missing))
        return Check("ufw", WARN, text, "sudo xgw install добавит правила (спросит): "
                     + "; ".join(missing))

    # --- NetworkManager ---------------------------------------------------------

    def _nm(self) -> list[Check]:
        if self.which("nmcli") is None:
            if self.lan_if:
                return []  # уже FAIL в «Программах»
            return [Check("NetworkManager", OK, "не установлен; для режима «только эта машина» "
                          "он не нужен")]
        manager = nm.Nm(self.runner)
        if not manager.running():
            level = FAIL if self.lan_if else WARN
            return [Check("NetworkManager", level, "не запущен",
                          "sudo systemctl enable --now NetworkManager")]
        devices = manager.devices()
        wan_if = lan.effective_wan(self.cfg, self.runner)
        result: list[Check] = []
        if not wan_if:
            result.append(Check("WAN", WARN, "маршрута по умолчанию нет — интернет не подключён?"))
        elif not self.lan_if:
            result.append(Check("NetworkManager", OK, f"запущен; WAN — {wan_if}"))
        if not self.lan_if:
            return result
        if self.lan_if == wan_if:
            return [Check(
                "LAN", FAIL, f"network.lan_if = {self.lan_if} — это интерфейс выхода в интернет",
                "LAN — вторая сетевая карта, к которой подключён Wi-Fi-роутер",
            )]
        device = devices.get(self.lan_if)
        if device is None:
            names = ", ".join(sorted(name for name in devices if name != "lo")) or "нет"
            return [Check("LAN", FAIL, f"интерфейса {self.lan_if} нет; есть: {names}",
                          "исправьте network.lan_if в config.toml")]
        if device.state == "unmanaged":
            return [Check(
                "LAN", FAIL, f"NetworkManager не управляет {self.lan_if} (unmanaged)",
                "в Ubuntu Server сетью управляет networkd: задайте в /etc/netplan/*.yaml "
                "renderer: NetworkManager и выполните sudo netplan apply",
            )]
        if device.type != "ethernet":
            result.append(Check("LAN", WARN, f"{self.lan_if} — не Ethernet ({device.type}); "
                                "XGW рассчитан на проводную карту к роутеру"))
        shared = [profile.name for profile, info in nm.bound_profiles(manager, self.lan_if)
                  if info.get("ipv4.method") == "shared"
                  and info.get("connection.autoconnect") != "no"]
        if shared:
            result.append(Check(
                "LAN", WARN,
                "профиль " + ", ".join(shared) + " в режиме shared: NetworkManager поднимает "
                "свой dnsmasq и NAT, они конфликтуют с XGW",
                "установка лишит такой профиль автоподключения",
            ))
        if device.connection == nm.PROFILE:
            result.append(Check("LAN", OK, f"{self.lan_if}: профиль {nm.PROFILE} активен"))
        elif any(profile.name == nm.PROFILE for profile in manager.profiles()):
            result.append(Check(
                "LAN", WARN, f"профиль {nm.PROFILE} есть, но на {self.lan_if} активен "
                f"«{device.connection or 'никакой'}» ({device.state})",
                "проверьте кабель к роутеру; sudo nmcli connection up xgw-lan",
            ))
        else:
            result.append(Check("LAN", OK, f"{self.lan_if} управляется NetworkManager "
                                f"({device.state}); профиль {nm.PROFILE} создаст установка"))
        return result

    def _lan_subnet_conflict(self) -> list[Check]:
        """network.lan_address не должен пересекаться с сетью провайдера и любой другой
        сетью машины: иначе у шлюза два интерфейса в одной подсети."""
        if not self.lan_if or self.which("ip") is None:
            return []
        conflicts = lan.subnet_conflicts(self.cfg, self.runner)
        if not conflicts:
            address = lan.gateway(self.cfg)
            network = address.network if address is not None else self.cfg.network.lan_address
            return [Check(
                "Подсеть LAN", OK, f"{network} не пересекается с другими сетями машины"
            )]
        return [Check(
            "Подсеть LAN", FAIL,
            lan.conflict_text(
                self.cfg, conflicts, self.paths.config_file,
                lan.free_lan_address(self.cfg, self.runner),
            ),
        )]

    # --- порты, время, сон, IPv6 ------------------------------------------------

    def _ports(self) -> list[Check]:
        if not sys.platform.startswith("linux"):
            return []
        ports = {
            "tproxy": self.cfg.capture.tproxy_port,
            "metrics": self.cfg.xray.metrics_port, "socks": self.cfg.xray.socks_port,
            "http": self.cfg.xray.http_port,
        }
        busy = [f"{name} {port}" for name, port in ports.items() if not self.port_free(port)]
        if not busy:
            return [Check("Порты", OK, "служебные порты Xray свободны")]
        if self.xray_up():
            return [Check("Порты", OK, "служебные порты заняты работающим Xray")]
        pattern = "|".join(str(port) for port in ports.values())
        return [Check(
            "Порты", FAIL, "заняты другой программой: " + ", ".join(busy),
            f"sudo ss -ltnp | grep -E ':({pattern})\\b' — освободите порт или смените его "
            "в [xray] / [capture]",
        )]

    def _time(self) -> list[Check]:
        if self.which("timedatectl") is None:
            return []
        synced = self.runner(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"], check=False
        ).strip()
        users = [name for name in nft.TIME_USERS if _user_exists(name)]
        notes = [f"служба времени — {users[0]}"] if users else []
        unit = TIME_UNITS.get(users[0], "chrony") if users else "chrony"
        if _chrony_uses_nts():
            notes.append(f"chrony использует NTS (TCP {nft.NTS_KE_PORT} идёт мимо перехвата)")
        result: list[Check] = []
        if synced == "yes":
            result.append(Check("Время", OK, "; ".join(["часы синхронизированы", *notes])))
        else:
            result.append(Check(
                "Время", WARN,
                "; ".join(["часы не синхронизированы: Reality не подключится при расхождении "
                           "времени", *notes]),
                f"timedatectl status; sudo systemctl restart {unit}",
            ))
        if not users and self.cfg.capture.local:
            result.append(Check(
                "Время", WARN,
                "не найден пользователь службы времени (" + ", ".join(nft.TIME_USERS) + "): её "
                "запросы попадут в перехват и без VPN время не синхронизируется",
            ))
        return result

    def _sleep(self) -> list[Check]:
        if not self.cfg.network.disable_sleep:
            return [Check("Сон", OK, "disable_sleep = false — сон оставлен на ваше усмотрение")]
        if not sleep.wanted(self.cfg):
            return [Check("Сон", OK, "роутера нет (network.lan_if пуст) — сон не трогается")]
        awake = sleep.unmasked(self.paths.systemd_dir)
        if not awake:
            return [Check("Сон", OK, "цели сна замаскированы")]
        text = "не замаскированы: " + ", ".join(awake) + " — уснувший шлюз оставит дом без сети"
        advice = "sudo xgw install замаскирует их" if not self.installed else (
            "sudo systemctl mask " + " ".join(awake))
        return [Check("Сон", WARN, text, advice + f"; GNOME: {sleep.GNOME_HINT}")]

    def _ipv6_proxy(self) -> list[Check]:
        """network.ipv6 = proxy: IPv6 самой машины должен идти через Xray."""
        if not self.cfg.capture.local:
            return [Check(
                "IPv6", WARN,
                "network.ipv6 = proxy, но capture.local = false: IPv6 машины не перехватывается",
                "включите capture.local или верните network.ipv6 = off",
            )]
        if not sysctl.ipv6_usable():
            return [Check("IPv6", OK, "IPv6 в ядре выключен — проксировать нечего")]
        if not self.installed or not self.root:
            return [Check("IPv6", OK, "IPv6 машины пойдёт через Xray (network.ipv6 = proxy)")]
        info = Capture(
            self.cfg, self.paths, runner=self.runner, logger=self.log, proc_sys=self.proc_sys
        ).describe()
        if info["mode"] != "on":
            return [Check(
                "IPv6", WARN, "перехват снят — IPv6 идёт напрямую, мимо VPN", "sudo xgw enable"
            )]
        if (info["loaded"] is False and not info.get("tun_problem")) or not info["ipv6"]:
            if self.preinstall:
                return [Check("IPv6", WARN, "IPv6 проксируется, но его правила не загружены",
                              "установка загрузит их заново")]
            return [Check(
                "IPv6", FAIL, "IPv6 проксируется, но его правила не загружены", "sudo xgw net up"
            )]
        return [Check("IPv6", OK, "IPv6 самой машины идёт через Xray")]

    def _ipv6(self) -> list[Check]:
        if self.cfg.network.ipv6_proxy:
            return self._ipv6_proxy()
        if self.which("ip") is None:
            return []
        try:
            entries = json.loads(
                self.runner(["ip", "-j", "-6", "addr", "show", "scope", "global"]) or "[]"
            )
        except (cmd.CommandError, json.JSONDecodeError):
            return []
        devices = sorted({
            entry.get("ifname", "") for entry in entries
            if isinstance(entry, dict) and entry.get("addr_info")
        } - {""})
        if not devices:
            return [Check("IPv6", OK, "глобальных IPv6-адресов нет — мимо перехвата идти нечему")]
        where = "глобальный IPv6-адрес на " + ", ".join(devices)
        text = where + ": по IPv6 трафик идёт мимо VPN"
        if not self.installed:
            return [Check("IPv6", WARN, text, "sudo xgw install отключит IPv6 на WAN")]
        if self.cfg.capture.local and self.root:
            # IPv6 машины держит фаервол (v6_guard), а не только настройка NetworkManager.
            chains6 = nft.loaded_chains(self.runner, "ip6", nft.TABLE6)
            if chains6 is not None and "v6_guard" in chains6:
                return [Check("IPv6", OK, where + ": наружу IPv6 машины не выпускает фаервол "
                              "(v6_guard)")]
            if chains6 is not None:
                return [Check(
                    "IPv6", FAIL, text + " — защита IPv6 (v6_guard) не загружена",
                    "sudo xgw net up — загрузит её; отключить IPv6 на WAN заново: sudo xgw install",
                )]
        # Не «nmcli connection modify»: у профиля из netplan это сбрасывает привязку к
        # карте (nm.netplan_defined). Установка выбирает безопасный способ сама.
        return [Check(
            "IPv6", FAIL, text,
            "sudo xgw install — отключит IPv6 на WAN заново и скажет, если не сможет",
        )]

    def _panel_login(self) -> list[Check]:
        """Пункт «Войти заново» у ярлыка «XGW» спрашивает пароль через pkexec. Без него
        войти в панель заново можно только ссылкой из `sudo xgw panel`. Смотрится там,
        где есть рабочий стол (xdg-open): на сервере ярлык открывать некому."""
        if not sys.platform.startswith("linux") or not self.cfg.panel.enabled:
            return []
        if self.which("xdg-open") is None:
            return []
        if self.which("pkexec") is None:
            return [Check(
                "Панель", WARN,
                "нет pkexec: «Войти заново» у ярлыка «XGW» не спросит пароль, войти в панель "
                "заново можно будет только ссылкой из sudo xgw panel",
                "sudo apt install pkexec",
            )]
        return [Check(
            "Панель", OK, "войти заново — правая кнопка по ярлыку «XGW», «Войти заново»",
        )]

    # --- службы и бюджет --------------------------------------------------------

    def _services(self) -> list[Check]:
        if not self.installed:
            return []
        # Служба sing-box запускается, только когда есть его конфиг (ConditionPathExists).
        units = [
            unit for unit in UNITS
            if unit != SINGBOX_UNIT or self.paths.singbox_config_file.exists()
        ] + ([dnsmasq.UNIT] if self.lan_if else [])
        down = [
            unit for unit in units
            if self.runner(["systemctl", "is-active", unit], check=False).strip() != "active"
        ]
        result: list[Check] = []
        if down and self.preinstall:
            result.append(Check(
                "Службы", WARN, "не работают: " + ", ".join(down),
                "установка запустит их заново",
            ))
        elif down:
            result.append(Check(
                "Службы", FAIL, "не работают: " + ", ".join(down),
                "sudo systemctl status " + " ".join(down),
            ))
        else:
            result.append(Check("Службы", OK, ", ".join(
                unit.removesuffix(".service") for unit in units) + " работают"))
        if self.root:
            capture = Capture(
                self.cfg, self.paths, runner=self.runner, logger=self.log, proc_sys=self.proc_sys
            )
            info = capture.describe()
            # Не готов только интерфейс TUN — правила на месте: об этом строка «TUN».
            missing = info["loaded"] is False and not info.get("tun_problem")
            if info["mode"] == "on" and missing and self.preinstall:
                result.append(Check("Перехват", WARN, "включён, но правила не загружены",
                                    "установка загрузит их заново"))
            elif info["mode"] == "on" and missing:
                result.append(Check("Перехват", FAIL, "включён, но правила не загружены",
                                    "sudo xgw net up"))
            elif info["mode"] in ("off", "open"):
                result.append(Check("Перехват", WARN, "снят — трафик идёт напрямую, мимо VPN",
                                    "sudo xgw enable"))
            elif info["mode"] == "on" and info.get("inbound_missing"):
                held = ("трафик заблокирован, мимо VPN ничего не уходит" if info.get("blocked")
                        else "трафик идёт напрямую, мимо VPN")
                result.append(Check(
                    "Перехват", WARN,
                    f"включён, но ждёт inbound в Xray: {info['inbound_missing']} — {held}",
                    "sudo xgw apply --now",
                ))
            elif info["mode"] == "on":
                result.append(Check("Перехват", OK, "включён, правила загружены"))
        return result

    def _journal(self) -> list[Check]:
        """Уровни записей демона в журнале systemd (log.py): предупреждения должны
        находиться по `journalctl -u xgw -p warning`. Префикс уровня демон ставит, только
        когда его stderr — тот самый поток журнала, чей номер systemd кладёт в
        JOURNAL_STREAM (log.journal_stream). Проверка смотрит и это условие у работающей
        службы, и сами записи: строки с WARNING и ERROR, сохранённые с уровнем info."""
        if not self.installed or not self.root:
            return []
        pid = self.runner(["systemctl", "show", "xgw", "-p", "MainPID", "--value"],
                          check=False).strip()
        if not pid.isdigit() or pid == "0":
            return []  # служба не работает — об этом строка «Службы»
        environ = (self.proc / pid / "environ").read_bytes().split(b"\0")
        stream = next((item.split(b"=", 1)[1].decode("ascii", "replace") for item in environ
                       if item.startswith(b"JOURNAL_STREAM=")), "")
        info = os.stat(self.proc / pid / "fd" / "2")
        actual = f"{info.st_dev}:{info.st_ino}"
        output = self.runner(["journalctl", "-u", "xgw", "-n", "500", "-o", "json", "--no-pager"],
                             check=False)
        wrong = 0
        for line in output.splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = record.get("MESSAGE")
            if (isinstance(message, str) and record.get("_TRANSPORT") == "stdout"
                    and record.get("PRIORITY") == "6"
                    and (" WARNING " in message or " ERROR " in message)):
                wrong += 1
        details = f"JOURNAL_STREAM={stream or 'нет'}, stderr демона {actual}"
        if wrong:
            return [Check(
                "Журнал", WARN,
                f"{wrong} предупреждений и ошибок демона записаны с уровнем info — "
                f"`journalctl -p warning` их не найдёт ({details})",
                "пришлите эту строку разработчику; перезапуск: sudo systemctl restart xgw",
            )]
        if stream != actual:
            return [Check("Журнал", WARN, f"stderr демона — не поток журнала ({details}): "
                                          "предупреждения запишутся с уровнем info")]
        return [Check("Журнал", OK, "предупреждения демона — с уровнем warning "
                                    "(journalctl -u xgw -p warning)")]

    def _budget(self) -> list[Check]:
        members, spares = self.cfg.filters.max_members, 0
        quotas: dict = {}
        size: int | None = None
        nodes: list[dict] = []
        if self.paths.db_file.exists():
            try:
                store = Store(self.paths.db_file)
                try:
                    nodes = store.all_nodes()
                    quotas = json.loads(store.get_meta("quota") or "{}")
                    size = status.measured_probe_size(store, self.cfg.probe.url)
                finally:
                    store.close()
                if nodes:
                    members = sum(1 for node in nodes if node["role"] == "proxy")
                    spares = len(nodes) - members
            except Exception as exc:
                self.log.debug("состояние не прочитано: %s", exc)
        quotas = quotas if isinstance(quotas, dict) else {}
        spend: dict[str, int] | None = None
        if nodes:
            # Как демон проверяет серверы: лимитированные запасные — коротким запросом,
            # кандидаты в резервный выход — изредка; расход квоты — с множителями.
            reserve = builder.reserve_tag(engine.read_json(self.paths.xray_config_file))
            plan = status.scan_plan(
                self.cfg, *status.node_entries(self.cfg, nodes, quotas, reserve)
            )
            budget = status.probe_budget(
                self.cfg, members, len(plan.full), size,
                cheap=len(plan.cheap), candidates=len(plan.candidates),
                speed_mb=status.speed_daily_mb(
                    self.cfg, plan.members, [*plan.full, *plan.cheap, *plan.candidates]
                ),
            )
            spend = status.quota_spend(self.cfg, plan, budget.size, budget.scan_minutes)
        else:
            budget = status.probe_budget(
                self.cfg, members, spares, size,
                speed_mb=status.speed_daily_mb(self.cfg, [{}] * members, [{}] * spares),
            )
        month = budget.everything * status.MONTH_DAYS / status.GB
        text = (
            f"~{budget.total / status.MB:.0f} МБ в сутки при {members} участниках и "
            f"{spares} запасных (лимит {self.cfg.probe.max_daily_probe_mb} МБ); вместе со "
            f"сквозной проверкой{' и замером скорости' if budget.speed else ''} — "
            f"~{budget.everything / status.MB:.0f} МБ в сутки, "
            f"~{month:.0f} ГБ в месяц (проба {budget.size} Б, "
            f"{'измерено' if budget.measured else 'по оценке'})"
        )
        if budget.guessed:
            text += (
                "; размер пробы пока неизвестен — probe.url ещё не ответил ни разу, цифра "
                "уточнится после первой удачной проверки"
            )
        for name, share in status.quota_share(budget, quotas, spend).items():
            text += f"; за месяц это ~{share:.0f} % квоты подписки «{name}»"
            if spend is not None:
                text += " (с множителями серверов)"
        warnings = status.budget_warnings(self.cfg, budget, quotas, spend)
        if warnings:
            return [Check("Трафик проверок", WARN, "; ".join(warnings) + f". Сейчас: {text}")]
        return [Check("Трафик проверок", OK, text)]

    # --- сеть -------------------------------------------------------------------

    # --- Tailscale (Т1) ----------------------------------------------------------

    def _tailscale(self) -> list[Check]:
        """Tailscale рядом с XGW: служба, исключения в правилах (К1–К4), как он выходит в
        интернет и две ловушки, которые XGW исправить не может, — адрес провайдера из
        100.64.0.0/10 (К5) и «Override local DNS» в tailnet (К6)."""
        name = "Tailscale"
        cli = self.which("tailscale") is not None
        if not ts.present(self.paths):
            text = "установлен, но tailscaled не запущен" if cli else "не установлен"
            return [Check(name, OK, text + " — не используется")]
        result: list[Check] = []
        state = ts.status(self.runner) if cli else None
        if state is None:
            result.append(Check(name, WARN, "tailscaled работает, но tailscale status не ответил",
                                "sudo tailscale status"))
        elif state.backend == "Running":
            result.append(Check(name, OK, "tailscaled работает, вход выполнен"))
        elif state.backend == "NeedsLogin":
            result.append(Check(
                name, WARN, "tailscaled работает, но нужен вход в tailnet",
                f"откройте ссылку входа: {state.auth_url}" if state.auth_url
                else "sudo tailscale up",
            ))
        else:
            result.append(Check(
                name, WARN, f"tailscaled работает, состояние — {state.backend or 'неизвестно'}",
                "sudo tailscale up",
            ))
        result += self._tailscale_rules()
        if self.net and state is not None and state.backend == "Running":
            result += self._tailscale_path()
        result += self._tailscale_cgnat()
        result += self._tailscale_dns()
        return result

    def _tailscale_rules(self) -> list[Check]:
        """Исключения Tailscale в правилах XGW загружены (как v6_guard в Ф1)."""
        name = "Tailscale: правила"
        if not (self.installed and self.root and self.cfg.capture.local):
            return []
        loaded = Capture(
            self.cfg, self.paths, runner=self.runner, logger=self.log, proc_sys=self.proc_sys
        ).tailscale_loaded()
        if loaded is None:
            return []
        if not loaded:
            text = ("Tailscale работает, а исключений для него в правилах XGW нет: его "
                    "соединения уходят в Xray, имена MagicDNS не разрешаются, в режиме "
                    "blocked и по IPv6 он отрезан")
            if self.preinstall:
                return [Check(name, WARN, text, "установка загрузит правила заново")]
            return [Check(name, FAIL, text, "sudo xgw net up")]
        route = ("напрямую, мимо Xray" if self.cfg.tailscale.route == "direct"
                 else "через Xray, пока он отвечает (tailscale.route = vpn)")
        return [Check(name, OK, "tailnet, MagicDNS и tailscale0 — мимо перехвата и блокировок; "
                      f"сам Tailscale ходит {route}")]

    def _tailscale_path(self) -> list[Check]:
        """`tailscale netcheck`: есть ли UDP (прямые соединения) и ближайший DERP."""
        name = "Tailscale: связь"
        found = ts.netcheck(self.runner)
        if found is None or found.udp is None:
            return [Check(name, WARN, "tailscale netcheck не ответил", "sudo tailscale netcheck")]
        derp = found.derp or "неизвестен"
        if found.latency_ms is not None:
            derp += f", {found.latency_ms:g} мс"
        if not found.udp:
            return [Check(
                name, WARN, f"нет UDP — соединения только через ретранслятор DERP ({derp})",
                "провайдер или роутер режет UDP; Tailscale работает, но медленнее",
            )]
        return [Check(name, OK, f"UDP есть; ближайший DERP: {derp}")]

    def _tailscale_cgnat(self) -> list[Check]:
        """К5: Tailscale (ts-input) отбрасывает пакеты с адресов 100.64.0.0/10, пришедшие не
        через tailscale0. Если провайдер выдаёт адрес, шлюз или DNS оттуда (CGNAT), сеть
        провайдера у машины ломается."""
        if self.which("nft") is None or not self.root:
            return []
        try:
            ruleset = json.loads(self.runner(["nft", "-j", "list", "ruleset"], timeout=30.0))
        except (cmd.CommandError, json.JSONDecodeError):
            return []
        items = ruleset.get("nftables", []) if isinstance(ruleset, dict) else []
        if not any(
            isinstance(item, dict) and isinstance(item.get("chain"), dict)
            and item["chain"].get("name") == "ts-input" for item in items
        ):
            return []  # фаервол Tailscale выключен (netfilter-mode=off) — отбрасывать некому
        found = ts.provider_cgnat(self.cfg, self.runner, skip=(self.lan_if,))
        if not found:
            return [Check("Tailscale: CGNAT", OK, "адреса провайдера вне 100.64.0.0/10")]
        return [Check(
            "Tailscale: CGNAT", WARN,
            "провайдер выдаёт адреса CGNAT (" + ", ".join(found) + "): Tailscale отбросит "
            "его пакеты",
            "sudo tailscale set --netfilter-mode=off — фаервол держит XGW",
        )]

    def _tailscale_dns(self) -> list[Check]:
        """К6: «Override local DNS» в консоли tailnet делает tailscale0 DNS по умолчанию, и
        tailscaled пересылает запросы машины сам, своей меткой — мимо VPN."""
        if self.which("resolvectl") is None:
            return []
        default = ts.override_dns(self.runner)
        if default is None:
            return []
        if default:
            return [Check(
                "Tailscale: DNS", WARN,
                "Override local DNS включён: DNS-запросы шлюза идут через Tailscale мимо VPN",
                "выключите его в консоли tailnet (DNS) или sudo tailscale set --accept-dns=false",
            )]
        return [Check("Tailscale: DNS", OK, "через tailscale0 — только имена tailnet")]

    # --- 0.1.18 --------------------------------------------------------------------

    def _meta(self, key: str) -> str | None:
        """Запись демона из базы состояния (только чтение); None — базы или записи нет."""
        try:
            store = Store(self.paths.db_file)
        except Exception as exc:
            self.log.debug("база состояния не открыта: %s", exc)
            return None
        try:
            return store.get_meta(key)
        finally:
            store.close()

    def _quic(self) -> list[Check]:
        """ТЗ R2: правило против QUIC (UDP/443) загружено ровно тогда, когда оно нужно."""
        capture = Capture(self.cfg, self.paths, runner=self.runner, logger=self.log)
        if capture.mode() != "on":
            return []
        rules = capture.rules("on")
        text = nft.listing(self.runner, terse=True)
        if text is None:
            return [Check("QUIC", WARN, "правила не прочитать — запустите через sudo")]
        loaded = nft.quic_loaded(text)
        if not self.cfg.network.block_quic:
            return [Check("QUIC", OK, "не отбивается (network.block_quic = false)")]
        if not rules.quic:
            return []
        if loaded:
            return [Check("QUIC", OK, "UDP/443 устройств и машины отбивается — браузеры идут по "
                                      "TCP, где действует дробление ClientHello")]
        return [Check("QUIC", WARN, "правило против QUIC не загружено",
                      "демон загрузит правила заново сам; иначе — sudo systemctl restart xgw")]

    def _free_pool(self) -> list[Check]:
        return [*self._free_pool_backend(), *self._pool_traffic()]

    def _pool_traffic(self) -> list[Check]:
        """Устройства через бесплатный пул (М2б.1): их правило в рабочем конфиге ведёт в
        балансировщик «pool» из серверов пула или в block (закрыто), но не в подписку; в
        балансировщике подписки серверов пула нет."""
        from .freepool import traffic as fptraffic

        devices = fptraffic.pool_devices(self.cfg)
        if not devices:
            return []
        name = "Устройства через бесплатный пул"
        who = ", ".join(devices)
        applied = engine.read_json(self.paths.xray_config_file) or {}
        routing = applied.get("routing") or {}
        rules = [rule for rule in routing.get("rules") or []
                 if isinstance(rule, dict) and set(devices) <= set(rule.get("source") or [])]
        pool = builder.applied_pool(applied)
        auto = next((item for item in routing.get("balancers") or []
                     if isinstance(item, dict) and item.get("tag") == BALANCER_TAG), {})
        if any(str(prefix).startswith(builder.POOL_PREFIX)
               for prefix in auto.get("selector") or []):
            return [Check(name, FAIL, "серверы пула попали в балансировщик подписки",
                          "sudo systemctl restart xgw")]
        if not rules:
            return [Check(name, FAIL, f"{who}: правила в рабочем конфиге нет — устройство идёт "
                                      "через подписку", "подождите минуту и повторите; снова "
                                      "так — sudo systemctl restart xgw")]
        rule = rules[0]
        if rule.get("outboundTag") == "block":
            why = ("наблюдение выключено" if self.cfg.free_pool.mode == "off"
                   else "допущенных серверов нет")
            return [Check(name, WARN, f"{who}: закрыто — {why}",
                          "вернуть на подписку — «Сервер: авто» в списке устройств панели")]
        if rule.get("balancerTag") != builder.POOL_BALANCER or not pool:
            return [Check(name, FAIL, f"{who}: правило ведёт не в бесплатный пул",
                          "sudo systemctl restart xgw")]
        return [Check(name, OK, f"{who}: через бесплатный пул, серверов в «pool»: {len(pool)}")]

    def _free_pool_backend(self) -> list[Check]:
        """Бесплатный пул (docs/FREEPOOL-PLAN.md): режим и годится ли бэкенд OpenVPN — без
        него серверы OpenVPN проверяются только доступностью адреса; при включённом ufw — есть
        ли правило для veth поколений (fpv+), иначе ufw отбросит их соединения."""
        from .freepool import backend as fpbackend

        name = "Бесплатный пул"
        mode = self.cfg.free_pool.mode
        if mode == "off":
            return [Check(name, OK, "выключен — режим подписок")]
        if not self.root:
            return [Check(name, WARN, f"режим {mode}; бэкенд OpenVPN без sudo не проверить",
                          "sudo xgw diag")]
        problem = fpbackend.unavailable(self.paths, self.runner, proc_sys=self.proc_sys)
        if problem:
            return [Check(name, WARN, f"режим {mode}; серверы OpenVPN проверяются только "
                                      f"доступностью адреса: {problem}")]
        result = [Check(name, OK, f"режим {mode}; бэкенд OpenVPN готов (openvpn, пользователи "
                                  "xgw-ovpn и xgw-fps, служба xgw-fp@, набор fp_peers)")]
        if self.which("ufw") is not None and ufw.active(self.runner):
            listed = self.runner(["ufw", "status"], timeout=20.0, check=False)
            if "fpv+" not in listed:
                wan = lan.effective_wan(self.cfg, self.runner)
                rule = ufw.wanted(self.lan_if or "lan", wan)[-1]  # правило пула — последнее
                result.append(Check(
                    name, FAIL, "ufw включён, а правила для туннелей OpenVPN (fpv+) нет: их "
                                "соединения ufw отбросит", "sudo ufw " + " ".join(rule)))
        return result

    def _kernel_direct(self) -> list[Check]:
        """Ф6: российские адреса ядром мимо Xray — у кого включено, сколько сетей, загружен ли
        набор direct4."""
        name = "Российские адреса мимо Xray"
        devices = len(self.cfg.managed.kernel_devices)
        if not self.cfg.routing.kernel_direct and not devices:
            return [Check(name, OK, "выключено: они идут через Xray (выход direct)")]
        reason = nft.kernel_direct_reason(self.cfg)
        if reason:
            return [Check(name, WARN, f"включено, но не действует: {reason}",
                          "уберите домены из routing.proxy_domains или выключите разгрузку "
                          "в панели")]
        who = ", ".join(
            (["этот компьютер и контейнеры"] if self.cfg.routing.kernel_direct else [])
            + ([f"устройств сети: {devices}"] if devices else []))
        capture = Capture(self.cfg, self.paths, runner=self.runner, logger=self.log)
        if capture.mode() != "on":
            return []
        rules = capture.rules("on")
        if not rules.direct4:
            return [Check(name, WARN, "сетей нет: geoip.dat не прочитан или в direct_ips нечего "
                                      "передать ядру — идут через Xray",
                          "sudo journalctl -u xgw | grep 'мимо Xray'")]
        text = nft.listing(self.runner, terse=True)
        if text is None:
            return [Check(name, WARN, "правила не прочитать — запустите через sudo")]
        if not nft.has_set(text, nft.DIRECT_SET):
            return [Check(name, WARN, "набор direct4 не загружен",
                          "демон загрузит правила заново сам; иначе — sudo systemctl restart xgw")]
        return [Check(name, OK, f"{len(rules.direct4)} сетей — напрямую ядром ({who}); DNS — "
                                "через Xray")]

    def _probe_hosts(self) -> list[Check]:
        """ТЗ R3: активный проверочный хост и ошибки по каждому — со слов демона."""
        try:
            saved = json.loads(self._meta(probehosts.META) or "{}")
        except ValueError:
            saved = {}
        lines = probehosts.describe(saved if isinstance(saved, dict) else {})
        if not lines:
            return [Check("Проверочные хосты", OK,
                          f"{len(probehosts.all_urls(self.cfg))}: демон их ещё не пробовал")]
        level = WARN if any("пропускается" in line for line in lines) else OK
        return [Check("Проверочные хосты", level, "; ".join(lines))]

    def _tray(self) -> list[Check]:
        """ТЗ R9: автозапуск значка и графический фреймворк для него."""
        autostart = self.paths.root / tray.AUTOSTART
        if not self.cfg.tray.enabled:
            return [Check("Значок в трее", OK, "выключен (tray.enabled = false)")]
        if not autostart.exists():
            return [Check("Значок в трее", WARN, "автозапуск не установлен",
                          "переустановите XGW из графического сеанса: sudo xgw install")]
        if not any(importlib.util.find_spec(name) for name in ("PyQt6", "PyQt5")):
            return [Check("Значок в трее", WARN, "нет PyQt6 и PyQt5 — значок не запустится",
                          f"sudo apt install {tray.QT_PACKAGE}")]
        return [Check("Значок в трее", OK, "запускается при входе в сеанс")]

    def _mark(self) -> int | None:
        return engine.bypass_mark(self.cfg, self.log)

    def _probe(self) -> list[Check]:
        url = self.cfg.probe.url
        agent = self.cfg.probe.user_agent
        expected = probe_bytes(url)
        mark = self._mark()
        result: list[Check] = []
        started = time.monotonic()
        try:
            reply = fetch.fetch_url(
                url, mark=mark, timeout=15.0, retries=0,
                bootstrap=self.cfg.dns.resolvers if mark is not None else None,
                headers={"User-Agent": agent},
            )
        except fetch.FetchError as exc:
            result.append(Check(
                "probe.url", WARN, f"напрямую не скачивается: {exc}",
                "не страшно, если скачивается через серверы: sudo xgw probe --all",
            ))
        else:
            size, seconds = len(reply.body), time.monotonic() - started
            if reply.status != 200 or (expected and size < expected):
                result.append(Check(
                    "probe.url", WARN,
                    f"напрямую: HTTP {reply.status}, {size} Б" + (
                        f" из {expected}" if expected else ""),
                    "не страшно, если через серверы файл скачивается целиком; иначе "
                    + target.ADVICE,
                ))
            else:
                result.append(Check("probe.url", OK, f"напрямую: {size} Б за {seconds:.1f} с"))
        if engine.healthy_http_in(self.cfg) is not None:
            started = time.monotonic()
            download = probes.http_get_via_proxy(
                "127.0.0.1", self.cfg.xray.http_port, url, silence=5.0, max_total=30.0,
                user_agent=agent,
            )
            if download.ok:
                result.append(Check(
                    "probe.url", OK,
                    f"через Xray: {download.downloaded} Б за "
                    f"{time.monotonic() - started:.1f} с",
                ))
            else:
                result.append(Check(
                    "probe.url", FAIL, f"через Xray не скачивается: {download.error}",
                    "sudo xgw probe --all покажет серверы по одному",
                ))
                result.extend(self._probe_target(mark))
        return result

    def _probe_target(self, mark: int | None) -> list[Check]:
        """Через Xray probe.url не скачивается. Серверы это или сам адрес пробы? Та же
        проверка, что у демона (watch/target.py): участники и несколько запасных
        опрашиваются собственной пробой; одинаковая ошибка у всех плюс контрольные
        запросы — значит, не отвечает адрес, и серверы ни при чём."""
        applied = engine.read_json(self.paths.xray_config_file)
        password, _ports = builder.probe_state(applied)
        verdicts: dict[str, str] = {}
        try:
            store = Store(self.paths.db_file)
            try:
                verdicts = {tag: entry["verdict"] for tag, entry in store.scans().items()}
            finally:
                store.close()
        except Exception as exc:
            self.log.debug("сканы не прочитаны: %s", exc)
        nodes = target.sample(builder.applied_nodes(applied), verdicts)
        if not password or not nodes:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(nodes))) as pool:
            results = list(pool.map(
                lambda info: scan.scan_node(info, self.cfg, probe_pass=password), nodes
            ))
        diagnosis = target.diagnose(
            results,
            base_ping=lambda: target.base_ping(self.cfg),
            direct=lambda: target.direct_signature(self.cfg, mark),
        )
        if not diagnosis.down:
            return []
        return [Check("probe.url", FAIL, diagnosis.text, target.ADVICE)]

    def _bootstrap(self) -> list[Check]:
        name = _domain_to_resolve(self.cfg)
        if not name:
            return []
        mark = self._mark()
        good: list[str] = []
        bad: list[str] = []
        for resolver in self.cfg.dns.resolvers:
            try:
                fetch.resolve_domain(name, [resolver], mark=mark)
                good.append(resolver)
            except Exception as exc:
                bad.append(f"{resolver} ({exc})")
        total = len(self.cfg.dns.resolvers)
        watched = resolving.loads(self._meta(resolving.META))
        if watched.get("results"):
            dead = [item["entry"] for item in watched["results"] if not item.get("ok")]
            note = (f"демон проверял {_ago_text(watched.get('ts'))}: "
                    + (f"не отвечали {', '.join(dead)}" if dead else "отвечали все"))
        else:
            note = ""
        if not good:
            return [Check(
                "bootstrap DNS", FAIL,
                "ни один резолвер не отвечает: домены серверов не разрешить — " + "; ".join(bad),
                "проверьте dns.bootstrap: DoH (https://<IP>/dns-query) или DoT (tls://<IP>); "
                "обычный DNS провайдера (udp://<адрес>) домены подписок не разрешает",
            )]
        tail = f" ({note})" if note else ""
        if bad:
            text = f"отвечают {len(good)} из {total}; не отвечают: " + "; ".join(bad) + tail
            return [Check("bootstrap DNS", WARN, text)]
        return [Check("bootstrap DNS", OK, f"отвечают все {total}{tail}")]


def _ago_text(ts: object) -> str:
    if not isinstance(ts, (int, float)):
        return "недавно"
    minutes = max(0, int((time.time() - ts) // 60))
    return f"{minutes} мин назад" if minutes < 120 else f"{minutes // 60} ч назад"



def _local_url(url: str) -> bool:
    """Адрес подписки в своей сети (локальный конвертер, NAS): http там допустим."""
    import ipaddress

    host = (urlsplit(url).hostname or "").lower()
    if host == "localhost" or host.endswith((".local", ".lan", ".home.arpa", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback

def _first_line(exc: Exception) -> str:
    lines = [line for line in str(exc).splitlines() if line.strip()]
    return lines[0] if lines else type(exc).__name__


def _user_exists(name: str) -> bool:
    try:
        import pwd
    except ImportError:
        return False
    try:
        pwd.getpwnam(name)
    except KeyError:
        return False
    return True


def _chrony_uses_nts(directory: Path = CHRONY_DIR) -> bool:
    """Есть ли в конфиге chrony источник с ключом nts."""
    try:
        files = [path for path in directory.rglob("*") if path.is_file()]
    except OSError:
        return False
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            words = line.split("#", 1)[0].split()
            if words[:1] and words[0] in ("server", "pool", "peer") and "nts" in words[2:]:
                return True
    return False


def _domain_to_resolve(cfg: Config) -> str:
    """Имя для проверки резолверов — из URL конфигурации: лишних запросов XGW не делает."""
    candidates = [cfg.probe.url, *(sub.url for sub in cfg.subscriptions)]
    for url in candidates:
        host = urlsplit(url).hostname or ""
        if host and not host.replace(".", "").isdigit() and ":" not in host:
            return host
    return ""
