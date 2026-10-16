"""Чтение /etc/xgw/config.toml (tomllib). У всех полей есть значения по
умолчанию; неизвестный ключ или неверный тип — предупреждение в лог, не падение."""

from __future__ import annotations

import ipaddress
import os
import re
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import managed as managed_file


class ConfigError(Exception):
    """Конфиг не читается или это битый TOML."""


# Файл пробы по умолчанию — неизменяемая версия пакета на CDN jsDelivr, 57 620 байт.
# Выбран шрифт WOFF, а не текст: проба самого Xray (burstObservatory) отправляет
# `Accept-Encoding: gzip`, и текстовый файл того же размера пришёл бы сжатым втрое
# (проверено: moment.min.js — 58 103 байта без сжатия и 18 514 со сжатием). Тело
# короче ~20 КБ «заморозку» не ловит: соединение замирает как раз после 8–20 КБ.
# Прежний адрес (speed.cloudflare.com/__down) отдавал 403 запросам без браузерного
# User-Agent — проверено на живой машине, отчёт docs/TEST-REPORT-2026-10-14.md.
DEFAULT_PROBE_URL = (
    "https://cdn.jsdelivr.net/npm/material-design-icons@3.0.1/iconfont/MaterialIcons-Regular.woff"
)
DEFAULT_PROBE_SIZE = 57_620
# User-Agent собственных проб XGW (скан, сквозная проверка, diag). Браузерный: часть
# CDN и WAF отвечает 403 всему, что на браузер не похоже. Пробы самого Xray и так
# ходят с заголовками Chrome — на них эта настройка не влияет.
DEFAULT_PROBE_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


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

    @property
    def ipv6_proxy(self) -> bool:
        """IPv6 самой машины идёт через Xray. Любое значение, кроме «proxy», — «off»:
        неизвестное слово не должно молча включать IPv6 мимо перехвата."""
        return self.ipv6.strip().lower() == "proxy"


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
    # Как трафик самой машины попадает в Xray: tproxy | tun.
    method: str = "tproxy"
    tun_name: str = "xgwtun0"
    tun_route_table: int = 101  # своя таблица маршрутов в TUN (route_table занят TPROXY LAN)
    # Трафик контейнеров Docker (мосты docker0 и br-*) — тоже через Xray: по метке
    # mark_containers он уходит в TUN-интерфейс tun_name (см. net/nft.py).
    containers: bool = True
    mark_containers: int = 3

    @property
    def tun(self) -> bool:
        """Трафик самой машины идёт в Xray через TUN. Неизвестное слово — tproxy."""
        return self.method.strip().lower() == "tun"



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
    url: str = DEFAULT_PROBE_URL
    user_agent: str = DEFAULT_PROBE_UA
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


# Версия Xray-core по умолчанию — та, на которой XGW проверен целиком (юнит-тесты, все
# стенды, «одноразовая машина»). 26.10.10 — предварительный выпуск (pre-release): последний
# стабильный на 16.10.2026 — 26.3.27, и на нём XGW тоже проверен (ASSUMPTIONS, п. 181).
# "latest" в конфиге — последний стабильный релиз GitHub.
XRAY_VERSION = "26.10.10"


@dataclass
class XraySection:
    version: str = XRAY_VERSION
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
    # Бот отвечает на команды из своего чата (/status, /enable…); false — только
    # уведомления. Адрес API меняют для собственного сервера Bot API.
    commands: bool = True
    telegram_api: str = "https://api.telegram.org"


@dataclass
class PanelConf:
    enabled: bool = True
    port: int = 8781


@dataclass
class Managed:
    """Что пришло не из config.toml, а из panel.json (добавлено кнопкой в панели)."""

    subscriptions: list[str] = field(default_factory=list)  # имена подписок
    links: list[str] = field(default_factory=list)
    # Отпечатки серверов, которые в конфиг Xray не попадают: отключённые остаются
    # в списке панели, убранные из него исчезают.
    disabled: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    # MAC устройств, пущенных мимо VPN в панели: аренда и bypass_hosts добавлены
    # из panel.json. Устройства, заданные в config.toml, сюда не попадают.
    devices: list[str] = field(default_factory=list)
    # Токен бота и чат подключены в панели (а не вписаны в config.toml).
    telegram: bool = False
    # Приоритет серверов: отпечаток → "high" или "low"; остальные — средние (priority.py).
    priority: dict[str, str] = field(default_factory=dict)


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
    panel: PanelConf = field(default_factory=PanelConf)
    managed: Managed = field(default_factory=Managed)


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
    "panel": PanelConf,
}


def load(path: Path | str) -> tuple[Config, list[str]]:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"конфиг не найден: {path}") from exc
    except PermissionError as exc:
        # В конфиге подписка, поэтому его права — 0600 root (в Windows sudo нет).
        advice = "" if os.name == "nt" else " — запустите команду через sudo"
        raise ConfigError(f"нет доступа к {path}{advice}") from exc
    except OSError as exc:
        raise ConfigError(f"конфиг не читается: {path}: {exc}") from exc
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"ошибка чтения TOML: {path}: {exc}") from exc

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
    warnings.extend(_merge_managed(config, managed_file.path_for(path)))
    warnings.extend(_validate(config))
    return config, warnings


def _merge_managed(cfg: Config, path: Path) -> list[str]:
    """Дополняет конфиг тем, что добавлено из панели (panel.json рядом с config.toml)."""
    data, error = managed_file.load(path)
    warnings = [error] if error else []
    names = {sub.name for sub in cfg.subscriptions}
    for item in data["subscriptions"]:
        if item["name"] in names:
            warnings.append(
                f"подписка «{item['name']}» из панели пропущена: такое имя уже есть в config.toml"
            )
            continue
        names.add(item["name"])
        cfg.subscriptions.append(Subscription(
            name=item["name"], url=item["url"], user_agent=item["user_agent"],
            refresh_minutes=item["refresh_minutes"],
        ))
        cfg.managed.subscriptions.append(item["name"])
    for link in data["links"]:
        if link not in cfg.manual.links:
            cfg.manual.links.append(link)
            cfg.managed.links.append(link)
    cfg.managed.disabled = list(data["disabled"])
    cfg.managed.removed = list(data["removed"])
    cfg.managed.priority = dict(data["priority"])
    warnings.extend(_merge_devices(cfg, data["devices"]))
    bot = data["telegram"]
    if bot["token"]:
        if cfg.notify.telegram_bot_token:
            warnings.append("бот Telegram из панели пропущен: бот уже задан в config.toml")
        else:
            cfg.notify.telegram_bot_token = bot["token"]
            cfg.notify.telegram_chat_id = bot["chat_id"]
            cfg.managed.telegram = True
    return warnings


def _merge_devices(cfg: Config, devices: list[dict]) -> list[str]:
    """Устройства мимо VPN из панели: статическая аренда и запись в bypass_hosts.

    То, что уже есть в config.toml, главнее: совпадающую аренду не дублируем, а
    конфликтующую (тот же MAC с другим адресом или тот же адрес у другого MAC)
    пропускаем с предупреждением.
    """
    warnings: list[str] = []
    lease_ip: dict[str, str] = {}
    for entry in cfg.network.static_leases:
        parts = [part.strip() for part in entry.split(",")]
        if len(parts) > 1:
            lease_ip[parts[0].lower().replace("-", ":")] = parts[1]
    listed = {host.strip().lower().replace("-", ":") for host in cfg.network.bypass_hosts}
    for device in devices:
        mac, ip, name = device["mac"], device["ip"], device["name"]
        if mac in listed:
            continue  # уже мимо VPN по config.toml — панель этим не управляет
        if lease_ip.get(mac, ip) != ip or any(
            other != mac and taken == ip for other, taken in lease_ip.items()
        ):
            warnings.append(
                f"устройство {mac} из панели пропущено: MAC или адрес {ip} уже заняты "
                "в network.static_leases"
            )
            continue
        if mac not in lease_ip:
            cfg.network.static_leases.append(f"{mac},{ip}" + (f",{name}" if name else ""))
            lease_ip[mac] = ip
        cfg.network.bypass_hosts.append(mac)
        listed.add(mac)
        cfg.managed.devices.append(mac)
    return warnings


def probe_bytes(url: str) -> int | None:
    """Размер пробы в байтах, если он известен заранее: записан в URL (…?bytes=65536)
    либо это файл по умолчанию. Для прочих адресов размер узнаёт сквозная проверка."""
    if url == DEFAULT_PROBE_URL:
        return DEFAULT_PROBE_SIZE
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
    if cfg.network.ipv6.strip().lower() not in ("off", "proxy"):
        warnings.append(f'network.ipv6={cfg.network.ipv6!r}: допустимо off или proxy; принято off')
    elif cfg.network.ipv6_proxy and not cfg.capture.local:
        warnings.append(
            "network.ipv6 = proxy действует только при capture.local = true: "
            "IPv6 устройств в Wi-Fi шлюз не выдаёт и не пропускает"
        )
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
    for name in ("mark_proxy", "mark_bypass", "mark_containers"):
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
    if cfg.capture.mark_containers in (cfg.capture.mark_proxy, cfg.capture.mark_bypass):
        warnings.append(
            "capture.mark_containers совпадает с mark_proxy или mark_bypass — используется "
            f"{Capture().mark_containers}"
        )
        cfg.capture.mark_containers = Capture().mark_containers
    if (
        not 1 <= cfg.capture.tun_route_table <= 0x7FFFFFFF
        or cfg.capture.tun_route_table in (253, 254, 255, cfg.capture.route_table)
    ):
        warnings.append(
            f"capture.tun_route_table={cfg.capture.tun_route_table}: нужен номер своей таблицы, "
            f"не 253–255 и не route_table — используется {Capture().tun_route_table}"
        )
        cfg.capture.tun_route_table = Capture().tun_route_table
    if cfg.capture.method.strip().lower() not in ("tproxy", "tun"):
        warnings.append(
            f"capture.method={cfg.capture.method!r}: допустимо tproxy или tun; принято tproxy"
        )
    elif cfg.capture.tun and not cfg.capture.local:
        warnings.append(
            "capture.method = tun относится к трафику самой машины: при capture.local = false "
            "он ни на что не влияет (сеть Wi-Fi всегда перехватывается через TPROXY)"
        )
    others = {cfg.network.lan_if.strip(), cfg.network.wan_if.strip()} - {""}
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,15}", cfg.capture.tun_name) or (
        cfg.capture.tun_name in others
    ):
        warnings.append(
            f"capture.tun_name={cfg.capture.tun_name!r}: нужно своё имя интерфейса (до 15 "
            f"символов, не карта LAN или WAN) — используется {Capture().tun_name}"
        )
        cfg.capture.tun_name = Capture().tun_name
    if not cfg.probe.user_agent.strip() or not cfg.probe.user_agent.isprintable():
        if cfg.probe.user_agent.strip():
            warnings.append("probe.user_agent: недопустимые символы — используется значение "
                            "по умолчанию")
        cfg.probe.user_agent = DEFAULT_PROBE_UA
    for name in ("interval", "timeout"):
        if not re.fullmatch(r"\d+[smh]", getattr(cfg.probe, name)):
            warnings.append(f"probe.{name}={getattr(cfg.probe, name)}: ожидается, например, 30s")
    listening = {
        "tproxy": cfg.capture.tproxy_port,
        "api": cfg.xray.api_port,
        "metrics": cfg.xray.metrics_port,
        "socks": cfg.xray.socks_port,
        "http": cfg.xray.http_port,
        "panel": cfg.panel.port,
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
    # Бот из панели без чата — это ожидание подключения, а не ошибка настройки.
    waiting = cfg.managed.telegram
    if cfg.notify.telegram_bot_token and not cfg.notify.telegram_chat_id and not waiting:
        warnings.append("задан telegram_bot_token, но не задан telegram_chat_id")
    if not re.fullmatch(r"https?://[^\s/]+/?", cfg.notify.telegram_api):
        warnings.append(
            f"notify.telegram_api={cfg.notify.telegram_api}: ожидается http(s)://адрес — "
            f"используется {Notify().telegram_api}"
        )
        cfg.notify.telegram_api = Notify().telegram_api
    cfg.notify.telegram_api = cfg.notify.telegram_api.rstrip("/")
    return warnings
