"""Состояния, которыми бэкенд описывает окну происходящее. Qt здесь не нужен."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace

AUTO_ID = "auto"  # «самый быстрый сервер»: выбор оставлен бэкенду

GROUP_COUNTRIES = "countries"
GROUP_PROFILES = "profiles"
GROUP_GATEWAYS = "gateways"

FEATURES = ("kill_switch", "split_tunneling", "custom_dns", "lan_bypass")
PROTOCOLS = ("xray", "sing-box", "wireguard", "openvpn")


class ConnectionState(enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass(frozen=True)
class ServerNode:
    """Сервер, профиль или шлюз в левой панели.

    `features` — метки для фильтров («fast», «p2p», «stream»); `load` — проценты 0–100.
    """

    id: str
    name: str
    country_code: str = ""
    country_name: str = ""
    city: str = ""
    protocol: str = "xray"
    ping_ms: int | None = None
    load: int | None = None
    features: frozenset[str] = frozenset()
    group: str = GROUP_COUNTRIES
    available: bool = True


@dataclass(frozen=True)
class TrafficStats:
    down_bps: float = 0.0
    up_bps: float = 0.0
    total_down: int = 0
    total_up: int = 0
    ping_ms: int = 0
    client_ip: str = ""


@dataclass(frozen=True)
class FeaturesState:
    kill_switch: bool = False
    split_tunneling: bool = False
    custom_dns: bool = False
    lan_bypass: bool = True

    def with_feature(self, name: str, enabled: bool) -> FeaturesState:
        if name not in FEATURES:
            raise KeyError(name)
        return replace(self, **{name: bool(enabled)})

    def enabled(self, name: str) -> bool:
        if name not in FEATURES:
            raise KeyError(name)
        return bool(getattr(self, name))


@dataclass(frozen=True)
class LocationInfo:
    """Что видно снаружи, пока VPN выключен (нижняя полоса окна)."""

    ip: str = ""
    country: str = ""
    provider: str = ""
    country_code: str = ""  # для отметки на карте


@dataclass(frozen=True)
class ConnectionSnapshot:
    """Состояние подключения целиком: его получают все панели одним сообщением."""

    state: ConnectionState = ConnectionState.DISCONNECTED
    server_id: str = AUTO_ID
    detail: str = ""


@dataclass
class UiSettings:
    protocol: str = "xray"
    theme: str = "dark"
    auto_connect: bool = False
    routing: str = "all"  # all | blocked
    interface: str = "auto"
    dns_address: str = ""
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        data = {"protocol": self.protocol, "theme": self.theme, "auto_connect": self.auto_connect,
                "routing": self.routing, "interface": self.interface,
                "dns_address": self.dns_address}
        data.update(self.extra)
        return data


def format_speed(bps: float) -> str:
    """Скорость в битах в секунду → короткая строка («12,4 Мбит/с»)."""
    value = max(0.0, float(bps))
    for unit in ("бит/с", "Кбит/с", "Мбит/с", "Гбит/с"):
        if value < 1000 or unit == "Гбит/с":
            text = f"{value:.0f}" if value >= 100 or unit == "бит/с" else f"{value:.1f}"
            return f"{text.replace('.', ',')} {unit}"
        value /= 1000
    raise AssertionError("unreachable")


def format_bytes(count: int) -> str:
    value = float(max(0, int(count)))
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if value < 1024 or unit == "ТБ":
            text = f"{value:.0f}" if value >= 100 or unit == "Б" else f"{value:.1f}"
            return f"{text.replace('.', ',')} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def best_node(nodes: list[ServerNode]) -> ServerNode | None:
    """Самый отзывчивый из доступных: узлы без замера идут последними."""
    usable = [node for node in nodes if node.available]
    if not usable:
        return None
    return min(usable, key=lambda node: (node.ping_ms is None, node.ping_ms or 0, node.name))
