"""Профили обхода блокировок: каким ядром и как шлюз ведёт сервер.

Пять профилей, от лёгкого к тяжёлому:

    xray:default           Xray, обычное соединение (ClientHello как у Chrome)
    xray:fragment          Xray, ClientHello режется на части (generator/fragment.py)
    singbox:default        sing-box, обычное соединение (другая реализация TLS и UDP)
    singbox:tls_fragment   sing-box, ClientHello режется на TCP-сегменты и записи TLS
    singbox:mux_padded     sing-box, мультиплексирование h2mux с паддингом поверх записей TLS

Серверы, которые умеет только sing-box (hysteria2, TUIC, AnyTLS, WireGuard, Shadowsocks с
плагином), работают на singbox:*; остальные — на xray:*, пока блокировка не заставит их
переехать. Профиль сервера в работающем ядре виден по применённому конфигу Xray (какой у него
outbound — прямой, через дробление или мост к sing-box), поэтому он переживает перезапуск
демона и обновление подписки, как состав участников (generator/builder.py).

Лестница при блокировке (ступень выбирает вердикт скана, daemon.py):
  «заморозка» (FROZEN, STALL_BEFORE_BODY): xray:fragment → singbox:default →
  singbox:tls_fragment → singbox:mux_padded;
  отказ в соединении (CONNECT_FAIL, TIMEOUT): по одной попытке xray:fragment, singbox:default и
  singbox:tls_fragment.
У серверов, которые умеет только sing-box, singbox:default — база, и лестница начинается с
singbox:tls_fragment.

Обычный sing-box у сервера с базой Xray (0.1.13) — тоже выученный профиль, но тот же профиль
дают и настройки: закрепление ядра sing-box (`xgw core`) и [core] mode = "sing-box". По конфигу
Xray их не различить, поэтому при каждой применённой сборке в базу пишется снимок настроек ядра
(core_settings, engine.persist): singbox:default сохраняется, только если ядро сервера в
настройках с прошлой сборки не менялось. После `xgw core … auto` и возврата mode = "auto"
сервер возвращается на базу, а не остаётся на sing-box.
"""

from __future__ import annotations

from collections.abc import Collection

from ..config import Config
from ..model import ServerNode
from . import fragment as fragmenting

XRAY_DEFAULT = "xray:default"
XRAY_FRAGMENT = "xray:fragment"
SB_DEFAULT = "singbox:default"
SB_FRAGMENT = "singbox:tls_fragment"
SB_MUX = "singbox:mux_padded"
ALL = (XRAY_DEFAULT, XRAY_FRAGMENT, SB_DEFAULT, SB_FRAGMENT, SB_MUX)

# Буква варианта в тегах и логине моста (generator/singbox.py).
LETTERS = {SB_DEFAULT: "d", SB_FRAGMENT: "f", SB_MUX: "m"}
PROFILE_OF_LETTER = {letter: profile for profile, letter in LETTERS.items()}

# Короткая отметка в `xgw servers` и панели.
LABELS = {
    XRAY_DEFAULT: "xray", XRAY_FRAGMENT: "xray+frag", SB_DEFAULT: "sb",
    SB_FRAGMENT: "sb+frag", SB_MUX: "sb+mux",
}
NAMES = {
    XRAY_DEFAULT: "Xray",
    XRAY_FRAGMENT: "Xray с дроблением ClientHello",
    SB_DEFAULT: "sing-box",
    SB_FRAGMENT: "sing-box с дроблением TLS",
    SB_MUX: "sing-box с мультиплексированием и паддингом",
}
# Профили, которым сервер обучается блокировкой: они сохраняются между сборками. Остальные —
# выбор настроек (база), поэтому следуют за настройками. Обычный sing-box у сервера с базой
# Xray — тоже выученный, но с условием (resolve, pin_unchanged).
LEARNED = (XRAY_FRAGMENT, SB_FRAGMENT, SB_MUX)
# Снимок настроек ядра, по которым собран применённый конфиг (ключ meta в базе состояния).
CORE_META = "core_settings"

FROZEN_VERDICTS = ("FROZEN", "STALL_BEFORE_BODY")
REFUSED_VERDICTS = ("CONNECT_FAIL", "TIMEOUT")
TRIGGER_VERDICTS = FROZEN_VERDICTS + REFUSED_VERDICTS


def core_of(profile: str) -> str:
    return "sing-box" if profile.startswith("singbox:") else "xray"


def label(profile: str) -> str:
    return LABELS.get(profile, profile)


def _pin(mode: object, pins: object, fingerprint: str) -> str:
    pinned = pins.get(fingerprint) if isinstance(pins, dict) else None
    if pinned in ("xray", "sing-box"):
        return pinned  # type: ignore[return-value]
    return "sing-box" if mode == "sing-box" else "auto"


def pin_of(cfg: Config, fingerprint: str) -> str:
    """Ядро, закреплённое за сервером: xray, sing-box или auto (выбирает шлюз)."""
    return _pin(cfg.core.mode, cfg.managed.core, fingerprint)


def core_settings(cfg: Config) -> dict:
    """Снимок настроек ядра для базы состояния (CORE_META)."""
    return {"mode": cfg.core.mode, "pins": dict(cfg.managed.core)}


def pin_unchanged(cfg: Config, saved: object, fingerprint: str) -> bool:
    """Ядро сервера в настройках то же, что при сборке применённого конфига. saved — снимок
    core_settings из базы; нет его (первая сборка, обновление с 0.1.12) — False."""
    if not isinstance(saved, dict):
        return False
    return _pin(saved.get("mode"), saved.get("pins"), fingerprint) == pin_of(cfg, fingerprint)


def available(node: ServerNode, cfg: Config, bridged: Collection[str]) -> list[str]:
    """Профили, в которых сервер может работать сейчас.

    bridged — буквы вариантов sing-box, заведённых для него в работающем sing-box
    (generator/singbox.py); без них профилей sing-box нет."""
    pin = pin_of(cfg, node.fingerprint)
    sb = [profile for profile, letter in LETTERS.items() if letter in bridged]
    if cfg.fragment.mode == "off":
        sb = [profile for profile in sb if profile != SB_FRAGMENT]
    xr: list[str] = []
    if node.outbound:
        xr.append(XRAY_DEFAULT)
        if cfg.fragment.mode != "off" and fragmenting.eligible(node.outbound):
            xr.append(XRAY_FRAGMENT)
    if pin == "sing-box" and sb:
        xr = []
    elif pin == "xray" and xr:
        sb = []
    return xr + sb


def base(cfg: Config, avail: list[str]) -> str:
    """Профиль по настройкам, без обучения блокировкой."""
    if XRAY_DEFAULT in avail:
        if cfg.fragment.mode == "always" and XRAY_FRAGMENT in avail:
            return XRAY_FRAGMENT
        return XRAY_DEFAULT
    if cfg.fragment.mode == "always" and SB_FRAGMENT in avail:
        return SB_FRAGMENT
    if SB_DEFAULT in avail:
        return SB_DEFAULT
    return avail[0] if avail else XRAY_DEFAULT


def resolve(
    node: ServerNode, cfg: Config, bridged: Collection[str],
    current: str | None = None, override: str | None = None, same_pin: bool = True,
) -> str:
    """Профиль, в котором сервер будет в новом конфиге.

    override — решение демона (проба профиля, возврат); current — профиль в применённом
    конфиге: обученный блокировкой сохраняется, пока он допустим настройками. Обычный sing-box
    у сервера с базой Xray — только при same_pin: ядро сервера в настройках не менялось с
    прошлой сборки (иначе этот профиль дало закрепление, а не блокировка)."""
    avail = available(node, cfg, bridged)
    default = base(cfg, avail)
    if override is not None:
        return override if override in avail else default
    if current in avail and (
        current in LEARNED
        or (current == SB_DEFAULT and same_pin and core_of(default) == "xray")
    ):
        return current  # type: ignore[return-value]
    return default


def ladder(verdict: str, current: str, default: str, avail: list[str]) -> list[str]:
    """Профили, которые стоит проверить серверу с таким вердиктом, по порядку.

    Сначала возврат на базу (если сервер на обученном профиле и перестал отвечать — может,
    сломал его самый профиль), затем ступени лестницы после нынешней. Обычный sing-box стоит
    раньше дробления в sing-box: тот же TLS, но без лишней задержки рукопожатия."""
    frozen = verdict in FROZEN_VERDICTS
    order = [XRAY_FRAGMENT, SB_DEFAULT, SB_FRAGMENT] + ([SB_MUX] if frozen else [])
    steps: list[str] = []
    if current != default and default in avail:
        steps.append(default)
    start = order.index(current) + 1 if current in order else 0
    steps += [
        profile for profile in order[start:]
        if profile in avail and profile not in (default, current) and profile not in steps
    ]
    return steps
