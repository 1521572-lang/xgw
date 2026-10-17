"""Действия, общие для команд CLI и панели управления.

Кнопка в панели делает ровно то же, что команда в терминале: `xgw enable` и
«Включить», `xgw pin` и «Закрепить» — один и тот же код с теми же проверками.
Функции ничего не печатают: возвращают итог, а показывает его вызывающий.
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from . import config, engine
from . import pin as pinning
from .generator import builder, validate
from .generator.builder import BALANCER_TAG
from .net import cmd, dnsmasq
from .net.capture import Capture, CaptureError
from .paths import Paths
from .store import Store
from .watch import status
from .xraycore.api import ApiError

MAX_PIN_SECONDS = 24 * 3600


@dataclass(frozen=True)
class Outcome:
    code: int  # 0 — выполнено; иначе код возврата команды
    text: str  # что произошло либо почему не получилось
    notes: tuple[str, ...] = ()  # что ещё стоит знать (печатается следом)
    hints: tuple[str, ...] = ()  # подсказки с командами терминала: панель их не показывает

    @property
    def ok(self) -> bool:
        return self.code == 0


def root_problem(cfg: config.Config | None = None) -> str | None:
    """Почему сетью управлять нельзя; None — можно."""
    if not sys.platform.startswith("linux"):
        return "управление сетью работает только в Linux"
    if os.geteuid() != 0:
        return "нужны права root: sudo xgw …"
    return None


@contextlib.contextmanager
def open_store(paths: Paths):
    store = Store(paths.db_file)
    try:
        yield store
    finally:
        store.close()


def scope(info: dict) -> str:
    parts = [f"сеть {info['lan_if']}"] if info["lan"] else []
    if info["local"]:
        parts.append("эта машина")
    return " и ".join(parts)


# --- перехват ------------------------------------------------------------------


def enable(cfg: config.Config, paths: Paths, capture: Capture) -> Outcome:
    if not capture.capturing:
        return Outcome(
            2,
            "в конфиге нечего перехватывать: capture.local = false, а для capture.lan "
            "нужен network.lan_if",
        )
    paths.ensure()
    try:
        capture.enable()
    except CaptureError as exc:
        return Outcome(1, f"перехват не включён: {exc}")
    held = str(getattr(capture, "held", "") or "")
    if held:
        # Перехват не загружен: в применённом конфиге Xray нет нужного inbound'а
        # (изменение настроек ещё не применено) либо нет интерфейса TUN. Включить его
        # сейчас — значит оставить машину без интернета: правила отправят пакеты в
        # никуда. Выбор «включено» запомнен: демон загрузит правила, как только Xray
        # перезапустится с новым конфигом.
        return Outcome(
            1,
            f"перехват пока не включён: {held} — правила отправили бы трафик в никуда. "
            "Трафик идёт напрямую; перехват включится сам, когда Xray перезапустится с "
            "новым конфигом",
            hints=("применить сейчас: sudo xgw apply --now", "проверить: sudo xgw status"),
        )
    info = capture.describe(check=False)
    text = f"перехват включён: {scope(info)} — через Xray"
    if info["bypass"]:
        text += "; мимо VPN: " + ", ".join(info["bypass"])
    with open_store(paths) as store:
        store.add_event("capture", text)
    if engine.healthy_http_in(cfg) is None:
        return Outcome(
            0, text,
            ("внимание: Xray не отвечает — пока он не запущен, перехваченный трафик "
             "никуда не уходит",),
            ("вернуть прямой интернет: sudo xgw disable",),
        )
    return Outcome(0, text)


def enable_checked(cfg: config.Config, paths: Paths, capture: Capture) -> Outcome:
    """Включение для тех, кто не видит терминала (панель, бот): пока Xray не отвечает,
    не включает — с fail-closed машина осталась бы без интернета, а человек без
    возможности вернуть его. Команда `xgw enable` включает и предупреждает."""
    if engine.healthy_http_in(cfg) is None:
        return Outcome(
            1, "Xray не отвечает — VPN не включён: иначе машина осталась бы без интернета. "
               "Проверьте подписку и серверы",
        )
    return enable(cfg, paths, capture)


def disable(cfg: config.Config, paths: Paths, capture: Capture) -> Outcome:
    paths.ensure()
    try:
        capture.disable()
    except CaptureError as exc:
        return Outcome(1, f"перехват не снят: {exc}")
    text = "перехват снят: трафик идёт напрямую, мимо VPN"
    hints = ("вернуть перехват: sudo xgw enable",)
    if capture.lan_if:
        text += f"; шлюз остаётся роутером для сети {capture.lan_if}"
    with open_store(paths) as store:
        store.add_event("capture", text)
    return Outcome(0, text, hints=hints)


# --- сеть после изменения настроек ---------------------------------------------


def apply_network(
    cfg: config.Config, paths: Paths, capture: Capture, *, logger,
    runner: Callable[..., str] = cmd.run,
) -> tuple[list[str], list[str]]:
    """Доводит до конфига правила nftables (bypass_hosts, exclude_cidrs) и DHCP
    (dhcp_range, static_leases). Возвращает (что сделано, что не удалось): сбой одного
    шага не отменяет другой. Правила nft перед загрузкой проверяются `nft -c` и
    заменяются целиком одной транзакцией."""
    done: list[str] = []
    problems: list[str] = []
    if capture.configured:
        try:
            capture.up()
        except CaptureError as exc:
            problems.append(f"правила сети не обновлены: {exc}")
    if not capture.lan_if:
        return done, problems
    changed, warnings = dnsmasq.write_conf(cfg, paths)
    for warning in warnings:
        logger.warning("%s", warning)
    if changed:
        try:
            runner(["systemctl", "restart", dnsmasq.UNIT], timeout=60.0)
            done.append("dnsmasq: настройки DHCP обновлены")
        except cmd.CommandError as exc:
            problems.append(f"dnsmasq не перезапущен: {exc}")
    return done, problems


# --- ручное закрепление --------------------------------------------------------


def pin(cfg: config.Config, paths: Paths, tag: str, ttl_text: str) -> Outcome:
    """Ручной выбор сервера (pinning.py): участника или запасного, на срок или бессрочно
    (ttl_text = pinning.FOREVER). Перестанет отвечать — трафик временно ведёт автовыбор, а
    когда ответит — снова он (демон, _manual_step)."""
    xray_bin = validate.find_xray(None, paths)
    if xray_bin is None:
        return Outcome(1, f"xray не найден (ожидается {paths.xray_bin} либо XGW_XRAY_BIN)")
    forever = ttl_text == pinning.FOREVER
    ttl = None if forever else config.parse_seconds(ttl_text)
    if not forever and (ttl is None or not 0 < ttl <= MAX_PIN_SECONDS):
        return Outcome(
            2, "--ttl: ожидается срок вида 30s, 10m или 2h, не больше 24h, или forever — "
            "бессрочно",
        )
    view = builder.applied_nodes(engine.read_json(paths.xray_config_file))
    if not any(info.tag == tag for info in view):
        members = [info.tag for info in view if info.role == "proxy"]
        return Outcome(
            2, f"{tag} — такого сервера нет ни в работе, ни среди запасных; в работе: "
            f"{', '.join(members) or 'нет'} (все — xgw servers)",
        )
    try:
        engine.make_api(cfg, xray_bin).pin(BALANCER_TAG, tag)
    except ApiError as exc:
        return Outcome(1, str(exc))
    now = time.time()
    with open_store(paths) as store:
        name = next((row["name"] for row in store.all_nodes() if row["tag"] == tag), "") or tag
        record = {
            "tag": tag, "name": name, "until": None if forever else now + (ttl or 0),
            "since": now, "down": None,
        }
        store.set_meta(pinning.META, pinning.dumps(record))
        store.add_event(
            "pin", f"«{name}» выбран вручную" + ("" if forever else f" на {ttl_text}")
        )
    daemon_up = status.read_status(paths, max(3.0 * cfg.watchdog.interval_s, 180.0)) is not None
    notes: tuple[str, ...] = ()
    if not daemon_up:
        notes = (
            "внимание: демон XGW не запущен — если сервер перестанет отвечать, трафик встанет"
            + ("" if forever else "; по истечении срока снимите выбор сами"),
        )
    head = f"«{name}» выбран вручную" + (
        ": весь трафик идёт через него, пока не вернёте автовыбор" if forever
        else f" на {ttl_text}: весь трафик идёт через него"
    )
    return Outcome(
        0,
        head + ". Перестанет отвечать — трафик временно поведёт автовыбор, а когда он "
        "снова ответит, — опять он",
        notes,
        ("вернуть автовыбор: xgw unpin",),
    )


def unpin(cfg: config.Config, paths: Paths) -> Outcome:
    xray_bin = validate.find_xray(None, paths)
    if xray_bin is None:
        return Outcome(1, f"xray не найден (ожидается {paths.xray_bin} либо XGW_XRAY_BIN)")
    try:
        engine.make_api(cfg, xray_bin).unpin(BALANCER_TAG)
    except ApiError as exc:
        return Outcome(1, str(exc))
    with open_store(paths) as store:
        store.set_meta(pinning.META, "")
        store.add_event("pin", "автовыбор: ручной выбор сервера снят")
    if cfg.speed.sticky:
        return Outcome(
            0, "автовыбор: через минуту шлюз снова закрепит основной сервер — самый быстрый "
            "из серверов в работе",
        )
    return Outcome(0, "автовыбор: сервер снова выбирает Xray")
