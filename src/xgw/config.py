"""Чтение /etc/xgw/config.toml (tomllib). У всех полей есть значения по
умолчанию; неизвестный ключ или неверный тип — предупреждение в лог, не падение."""

from __future__ import annotations

import ipaddress
import re
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class ConfigError(Exception):
    """Конфиг не читается или это битый TOML."""


@dataclass
class Network:
    wan_if: str = ""
    lan_if: str = ""
    lan_address: str = "192.168.50.1/24"
    router_mode: str = "ap"
    dhcp_range: str = "192.168.50.100,192.168.50.200,12h"
    router_mac: str = ""
    static_leases: list[str] = field(default_factory=list)
    bypass_hosts: list[str] = field(default_factory=list)
    ipv6: str = "off"
    disable_sleep: bool = True


@dataclass
class Capture:
    lan: bool = True
    local: bool = True
    fail_mode: str = "closed"
    forward_icmp: bool = True
    exclude_cidrs: list[str] = field(default_factory=list)
    tproxy_port: int = 12345
    mark_proxy: int = 1
    mark_bypass: int = 2
    route_table: int = 100


@dataclass
class Subscription:
    name: str = "main"
    url: str = ""
    user_agent: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    refresh_minutes: int = 60


@dataclass
class Manual:
    links: list[str] = field(default_factory=list)


@dataclass
class Filters:
    include_regex: str = ""
    exclude_regex: str = "(?i)(истека|осталось|трафик|expire)"
    max_members: int = 5
    rotate_after_min: int = 15


@dataclass
class Probe:
    url: str = "https://speed.cloudflare.com/__down?bytes=65536"
    url_fallback: str = ""
    trace_url: str = "https://www.cloudflare.com/cdn-cgi/trace"
    interval: str = "30s"
    sampling: int = 2
    timeout: str = "8s"
    scan_spares_minutes: int = 60
    max_daily_probe_mb: int = 1024


@dataclass
class Routing:
    direct_domains: list[str] = field(
        default_factory=lambda: ["domain:ru", "domain:su", "domain:xn--p1ai"]
    )
    direct_ips: list[str] = field(default_factory=lambda: ["geoip:ru"])
    proxy_domains: list[str] = field(default_factory=list)
    conn_idle_s: int = 120
    home_country: str = "RU"


@dataclass
class Dns:
    proxy_servers: list[str] = field(default_factory=lambda: ["1.1.1.1", "8.8.8.8"])
    direct_servers: list[str] = field(default_factory=lambda: ["77.88.8.8"])
    bootstrap: list[str] = field(
        default_factory=lambda: [
            "https://1.1.1.1/dns-query",
            "https://8.8.8.8/dns-query",
            "udp://77.88.8.8",
        ]
    )


@dataclass
class XraySection:
    version: str = "latest"
    api_port: int = 10085
    metrics_port: int = 10086
    socks_port: int = 10808
    http_port: int = 10809
    probe_port_base: int = 20001


@dataclass
class Apply:
    restart_window: str = "04:00-05:00"


@dataclass
class Watchdog:
    interval_s: int = 20
    fail_threshold: int = 3
    wan_check: str = "ya.ru:443"


@dataclass
class StatusConf:
    lan_page: bool = False
    token: str = ""


@dataclass
class Notify:
    desktop: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    min_interval_min: int = 10


@dataclass
class Config:
    network: Network = field(default_factory=Network)
    capture: Capture = field(default_factory=Capture)
    subscriptions: list[Subscription] = field(default_factory=list)
    manual: Manual = field(default_factory=Manual)
    filters: Filters = field(default_factory=Filters)
    probe: Probe = field(default_factory=Probe)
    routing: Routing = field(default_factory=Routing)
    dns: Dns = field(default_factory=Dns)
    xray: XraySection = field(default_factory=XraySection)
    apply: Apply = field(default_factory=Apply)
    watchdog: Watchdog = field(default_factory=Watchdog)
    status: StatusConf = field(default_factory=StatusConf)
    notify: Notify = field(default_factory=Notify)


_SECTIONS = {
    "network": Network,
    "capture": Capture,
    "manual": Manual,
    "filters": Filters,
    "probe": Probe,
    "routing": Routing,
    "dns": Dns,
    "xray": XraySection,
    "apply": Apply,
    "watchdog": Watchdog,
    "status": StatusConf,
    "notify": Notify,
}


def load(path: Path | str) -> tuple[Config, list[str]]:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"конфиг не найден: {path}") from exc
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"ошибка чтения TOML: {exc}") from exc

    warnings: list[str] = []
    kwargs: dict[str, object] = {}
    for key, value in data.items():
        if key == "subscriptions":
            subs: list[Subscription] = []
            if isinstance(value, list):
                for item in value:
                    subs.append(_build_section(Subscription, item, "subscriptions", warnings))
            else:
                warnings.append("subscriptions должен быть массивом таблиц [[subscriptions]]")
            kwargs["subscriptions"] = subs
        elif key in _SECTIONS:
            kwargs[key] = _build_section(_SECTIONS[key], value, key, warnings)
        else:
            warnings.append(f"неизвестная секция [{key}] проигнорирована")
    config = Config(**kwargs)  # type: ignore[arg-type]
    warnings.extend(_validate(config))
    return config, warnings


def probe_bytes(url: str) -> int | None:
    """Размер пробы в байтах, если он есть в URL (…?bytes=65536)."""
    values = parse_qs(urlsplit(url).query).get("bytes")
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


def _build_section(cls, data: object, section: str, warnings: list[str]):
    if not isinstance(data, dict):
        warnings.append(f"секция [{section}] не является таблицей — значения по умолчанию")
        return cls()
    defaults = cls()
    known = {f.name for f in fields(cls)}
    values: dict[str, object] = {}
    for name, value in data.items():
        if name not in known:
            warnings.append(f"неизвестный ключ {section}.{name} проигнорирован")
            continue
        if _type_ok(value, getattr(defaults, name)):
            values[name] = value
        else:
            warnings.append(f"{section}.{name}: неверный тип — оставлено значение по умолчанию")
    return cls(**values)


def _type_ok(value: object, default: object) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(default, list):  # все списки в конфиге — списки строк
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if isinstance(default, dict):  # headers: строка → строка
        return isinstance(value, dict) and all(isinstance(item, str) for item in value.values())
    return True


def parse_seconds(value: str) -> int | None:
    """«30s», «10m», «1h» → секунды; None — не разобрать."""
    match = re.fullmatch(r"(\d+)([smh])", value)
    if not match:
        return None
    return int(match.group(1)) * {"s": 1, "m": 60, "h": 3600}[match.group(2)]


def _validate(cfg: Config) -> list[str]:
    """Проверяет значения; опасные для работы исправляет на значения по умолчанию."""
    warnings: list[str] = []
    for name in ("include_regex", "exclude_regex"):
        try:
            re.compile(getattr(cfg.filters, name))
        except re.error as exc:
            default = getattr(Filters(), name)
            warnings.append(f"filters.{name}: неверное регулярное выражение ({exc}) — сброшено")
            setattr(cfg.filters, name, default)
    if cfg.filters.max_members < 1:
        warnings.append("filters.max_members должен быть не меньше 1 — используется 1")
        cfg.filters.max_members = 1
    if cfg.probe.sampling < 1:
        warnings.append("probe.sampling должен быть не меньше 1 — используется 2")
        cfg.probe.sampling = Probe().sampling
    interval = parse_seconds(cfg.probe.interval)
    if interval is not None and interval < 10:
        warnings.append("probe.interval меньше 10s — Xray не принимает интервал короче")
    if not re.fullmatch(
        r"\s*([01]\d|2[0-3]):[0-5]\d\s*-\s*([01]\d|2[0-3]):[0-5]\d\s*", cfg.apply.restart_window
    ):
        warnings.append(
            f"apply.restart_window={cfg.apply.restart_window}: ожидается ЧЧ:ММ-ЧЧ:ММ — "
            f"используется {Apply().restart_window}"
        )
        cfg.apply.restart_window = Apply().restart_window
    for sub in cfg.subscriptions:
        if not sub.url:
            warnings.append(f"подписка «{sub.name}»: не задан url")
    if cfg.network.router_mode not in ("ap", "router"):
        warnings.append(f"network.router_mode={cfg.network.router_mode}: допустимо ap или router")
    if cfg.network.ipv6 != "off":
        warnings.append('поддерживается только network.ipv6 = "off" (проксирование IPv6 — этап 5)')
    if cfg.capture.fail_mode not in ("closed", "open"):
        warnings.append(f"capture.fail_mode={cfg.capture.fail_mode}: допустимо closed или open")
    for name in ("lan_if", "wan_if"):
        value = getattr(cfg.network, name)
        if value and not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", value):
            warnings.append(f"network.{name}={value!r}: недопустимое имя интерфейса")
    try:
        ipaddress.IPv4Interface(cfg.network.lan_address)
    except ValueError:
        warnings.append(
            f"network.lan_address={cfg.network.lan_address}: ожидается адрес/префикс — "
            f"используется {Network().lan_address}"
        )
        cfg.network.lan_address = Network().lan_address
    for name in ("mark_proxy", "mark_bypass"):
        # Метка 0 — это «без метки»: правила перехвата с ней не работают.
        if not 1 <= getattr(cfg.capture, name) <= 0xFFFFFFFF:
            default = getattr(Capture(), name)
            warnings.append(
                f"capture.{name} должен быть от 1 до 4294967295 — используется {default}"
            )
            setattr(cfg.capture, name, default)
    # 253–255 — системные таблицы default, main и local: маршрут перехвата в main
    # оставил бы машину без сети.
    if not 1 <= cfg.capture.route_table <= 0x7FFFFFFF or cfg.capture.route_table in (253, 254, 255):
        warnings.append(
            f"capture.route_table={cfg.capture.route_table}: нужен номер своей таблицы, "
            f"не 253–255 — используется {Capture().route_table}"
        )
        cfg.capture.route_table = Capture().route_table
    if cfg.capture.mark_proxy == cfg.capture.mark_bypass:
        warnings.append("capture.mark_proxy и capture.mark_bypass совпадают")
    for name in ("interval", "timeout"):
        if not re.fullmatch(r"\d+[smh]", getattr(cfg.probe, name)):
            warnings.append(f"probe.{name}={getattr(cfg.probe, name)}: ожидается, например, 30s")
    listening = {
        "tproxy": cfg.capture.tproxy_port,
        "api": cfg.xray.api_port,
        "metrics": cfg.xray.metrics_port,
        "socks": cfg.xray.socks_port,
        "http": cfg.xray.http_port,
    }
    ports = list(listening.values()) + [
        cfg.xray.probe_port_base + i for i in range(cfg.filters.max_members + 8)
    ]
    if len(set(ports)) != len(ports):
        warnings.append("служебные порты и probe-порты пересекаются — проверьте [xray] и [capture]")
    for name, port in {**listening, "probe_port_base": cfg.xray.probe_port_base}.items():
        if not 1 <= port <= 65535:
            warnings.append(f"порт {name}={port} вне диапазона 1–65535")
    if cfg.xray.version != "latest" and not re.fullmatch(r"\d+(\.\d+){0,2}", cfg.xray.version):
        warnings.append('xray.version: "latest" или версия цифрами, например 25.7.23')
    if cfg.notify.telegram_bot_token and not cfg.notify.telegram_chat_id:
        warnings.append("задан telegram_bot_token, но не задан telegram_chat_id")
    return warnings
