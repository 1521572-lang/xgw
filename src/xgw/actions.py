"""Действия, общие для команд CLI и панели управления.

Кнопка в панели делает ровно то же, что команда в терминале: `xgw enable` и
«Включить», `xgw pin` и «Закрепить» — один и тот же код с теми же проверками.
Функции ничего не печатают: возвращают итог, а показывает его вызывающий.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from dataclasses import dataclass

from . import config, engine
from .generator import builder, validate
from .generator.builder import BALANCER_TAG
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


def root_problem() -> str | None:
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


def disable(cfg: config.Config, paths: Paths, capture: Capture) -> Outcome:
    paths.ensure()
    try:
        capture.disable()
    except CaptureError as exc:
        return Outcome(1, f"перехват не снят: {exc}")
    text = "перехват снят: трафик идёт напрямую, мимо VPN"
    if capture.lan_if:
        text += f"; шлюз остаётся роутером для сети {capture.lan_if}"
    with open_store(paths) as store:
        store.add_event("capture", text)
    return Outcome(0, text, hints=("вернуть перехват: sudo xgw enable",))


# --- ручное закрепление --------------------------------------------------------


def pin(cfg: config.Config, paths: Paths, tag: str, ttl_text: str) -> Outcome:
    xray_bin = validate.find_xray(None, paths)
    if xray_bin is None:
        return Outcome(1, f"xray не найден (ожидается {paths.xray_bin} либо XGW_XRAY_BIN)")
    ttl = config.parse_seconds(ttl_text)
    if ttl is None or not 0 < ttl <= MAX_PIN_SECONDS:
        return Outcome(2, "--ttl: ожидается срок вида 30s, 10m или 2h, не больше 24h")
    members = [
        info.tag
        for info in builder.applied_nodes(engine.read_json(paths.xray_config_file))
        if info.role == "proxy"
    ]
    if tag not in members:
        return Outcome(
            2, f"{tag} — не участник балансировщика; участники: {', '.join(members) or 'нет'}"
        )
    try:
        engine.make_api(cfg, xray_bin).pin(BALANCER_TAG, tag)
    except ApiError as exc:
        return Outcome(1, str(exc))
    until = time.time() + ttl
    with open_store(paths) as store:
        store.set_meta("pin", json.dumps({"tag": tag, "until": until}))
        store.add_event("pin", f"{tag} закреплён вручную на {ttl_text}")
    notes: tuple[str, ...] = ()
    if status.read_status(paths, max(3.0 * cfg.watchdog.interval_s, 180.0)) is None:
        notes = ("внимание: демон XGW не запущен — по истечении срока снимите закрепление сами",)
    return Outcome(
        0,
        f"{tag} закреплён на {ttl_text}. Автопереключение на это время отключено: "
        "если узел «заморозят», трафик встанет",
        notes,
        ("снять раньше: xgw unpin",),
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
        store.set_meta("pin", "")
        store.add_event("pin", "закрепление снято вручную")
    return Outcome(0, "закрепление снято, выбором узла снова управляет Xray")
