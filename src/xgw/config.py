"""Чтение /etc/xgw/config.toml (tomllib). У всех полей есть значения по
умолчанию; неизвестный ключ или неверный тип — предупреждение в лог, не падение."""

from __future__ import annotations

import ipaddress
import re
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import cost
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
# Ещё три проверочных хоста (0.1.18, ТЗ R3): разные домены и разные CDN — Fastly, Akamai,
# Google; probe.url (jsDelivr, через Cloudflare или Fastly) остаётся первым. Файлы 45–70 КБ,
# неизменяемые (версия в пути), отдаются без входа; ответ 200 и размер проверены 24.10.2026.
# ТСПУ, «придушивающий» соединение после 16–32 КБ, на них заметен так же, как на 57 КБ.
DEFAULT_PROBE_HOSTS = (
    "https://code.jquery.com/jquery-3.7.1.slim.min.js",
    "https://ajax.aspnetcdn.com/ajax/bootstrap/3.4.1/fonts/glyphicons-halflings-regular.ttf",
    "https://ajax.googleapis.com/ajax/libs/jquery/3.7.1/jquery.slim.min.js",
)
# Известные размеры файлов проверок: без них размер узнаёт сквозная проверка.
KNOWN_PROBE_SIZES = {
    DEFAULT_PROBE_URL: DEFAULT_PROBE_SIZE,
    DEFAULT_PROBE_HOSTS[0]: 70_264,
    DEFAULT_PROBE_HOSTS[1]: 45_404,
    DEFAULT_PROBE_HOSTS[2]: 70_264,
}
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
    # Алгоритм управления перегрузкой TCP — BBR (net.ipv4.tcp_congestion_control): быстрее
    # на канале с потерями и большой задержкой. Ставит xgw-net, прежний возвращает
    # `xgw net down` и удаление; false — XGW алгоритм не трогает.
    tcp_bbr: bool = True
    # QUIC (HTTP/3, UDP/443) устройств сети и самой машины отбивается сразу (ICMP «порт
    # недоступен»): браузеры уходят на TCP/443, где действует дробление ClientHello, а QUIC
    # дробление не берёт (0.1.18, ТЗ R2). Собственные соединения шлюза с серверами VPN,
    # Tailscale и локальные сети не затрагиваются. false — правило не ставится.
    block_quic: bool = True

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
    # Что делать, пока в применённом конфиге Xray нет inbound'а перехвата (настройки ещё
    # не применены, откат): "block" — мимо VPN не уходит ничего; "direct" — сеть напрямую.
    hold: str = "block"
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

    @property
    def hold_blocks(self) -> bool:
        """Без inbound'а перехвата трафик закрыт (hold = "block"). При fail_mode = "open"
        человек выбрал связь важнее VPN — тогда всегда напрямую. Неизвестное слово — block:
        опечатка не должна молча пускать трафик мимо VPN."""
        return self.fail_mode != "open" and self.hold.strip().lower() != "direct"


@dataclass
class TailscaleConf:
    # Как ходят соединения самого tailscaled (WireGuard, DERP, управление), если он стоит
    # на машине: "direct" — напрямую, мимо Xray, всегда; "vpn" — через Xray, пока он
    # отвечает, а когда не отвечает или правила в режиме blocked — напрямую.
    route: str = "direct"
    # При route = "direct": сервер DERP напрямую не отвечает derp_fails проверок подряд —
    # tailscaled временно идёт через VPN (как при "vpn"), а когда DERP снова отвечает
    # напрямую — обратно (0.1.18, ТЗ R4b). false — не переключать.
    derp_fallback: bool = True
    derp_fails: int = 3


@dataclass
class TrayConf:
    # Значок XGW в трее рабочего стола (0.1.18, ТЗ R9): ставится установкой и запускается при
    # входе в сеанс. false — установка его не ставит (и убирает поставленный).
    enabled: bool = True


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
    # Множитель расхода трафика в имени сервера («x10 Германия»): первая группа — число.
    # Пусто — множители не ищутся, все серверы x1 (cost.py).
    multiplier_regex: str = cost.DEFAULT_MULTIPLIER_REGEX


@dataclass
class Probe:
    url: str = DEFAULT_PROBE_URL
    user_agent: str = DEFAULT_PROBE_UA
    url_fallback: str = ""
    # Ещё проверочные хосты (0.1.18, ТЗ R3): собственные пробы шлюза ходят по кругу —
    # probe.url, затем эти. Хост, который не ответил, когда другой ответил, пропускается
    # host_pause_minutes; «не отвечает адрес проверки» — только когда не отвечают все.
    urls: list[str] = field(default_factory=lambda: list(DEFAULT_PROBE_HOSTS))
    host_pause_minutes: int = 30
    trace_url: str = "https://www.cloudflare.com/cdn-cgi/trace"
    interval: str = "30s"
    sampling: int = 2
    timeout: str = "8s"
    scan_spares_minutes: int = 60
    max_daily_probe_mb: int = 1024


# Замер скорости (watch/speed.py). Тестовый адрес Cloudflare отдаёт ровно столько байт,
# сколько запрошено, без сжатия; запасной — неизменяемый файл на jsDelivr (тот же CDN,
# что у probe.url), 9 020 995 байт: на случай, если Cloudflare откажет выходу сервера.
# Оба проверены 16.10.2026 тем же стеком, что у проб XGW (Python ssl, браузерный
# User-Agent, без Accept-Encoding): ответ 200, тело целиком (ASSUMPTIONS, п. 185).
DEFAULT_SPEED_URL = "https://speed.cloudflare.com/__down?bytes=10000000"
DEFAULT_SPEED_FALLBACK = "https://cdn.jsdelivr.net/npm/typescript@5.3.3/lib/typescript.js"


@dataclass
class Speed:
    # Основной сервер: весь трафик — через один сервер в работе, самый быстрый по замеру;
    # остальные наготове. false — как до 0.1.9: ядро само берёт сервер с наименьшей
    # задержкой и меняет выбор после каждой пробы, если задержки близки.
    sticky: bool = True
    url: str = DEFAULT_SPEED_URL
    url_fallback: str = DEFAULT_SPEED_FALLBACK
    max_mb: int = 10  # замер качает не больше…
    max_seconds: int = 8  # …и не дольше
    # Как часто замерять фоном каждый живой сервер (ASSUMPTIONS п. 224; с 0.1.18 — реже, решение
    # заказчика 24.10.2026): безлимитные — раз в unlimited_hours, лимитированные — раз в
    # limited_hours (меньшей загрузкой, speed.size_mb); запасные — не чаще раза в spare_hours
    # (0 — как серверы в работе). 0 в unlimited_hours и limited_hours — не замерять (основной
    # выбирается по задержке). Основной между замерами оценивается по своему трафику, а при его
    # падении или «придушивании» замеряются кандидаты на замену (watch/guard.py).
    unlimited_hours: int = 6
    limited_hours: int = 6
    spare_hours: int = 24
    spare_mb: int = 3  # запасные качают не больше: их десятки
    # Прежний ключ (до 0.1.18), один срок для серверов в работе: 0 по-прежнему выключает
    # замеры, другие значения не действуют (-1 — ключа нет).
    every_hours: int = -1
    gain_pct: int = 30  # сменить основной, только если другой быстрее на столько процентов
    hold_minutes: int = 60  # и основной продержался не меньше
    # Контроль скорости участников (0.1.18, ТЗ R5–R8; watch/guard.py). Раз в passive_seconds
    # демон считает скорость реального трафика каждого участника по счётчикам Xray; не меньше
    # passive_mbps — участник исправен, активный замер не нужен.
    guard: bool = True
    passive_seconds: int = 90
    passive_mbps: int = 10
    # «Придушен»: low_count суммарных оценок подряд (замер плюс трафик клиентов через тот же
    # сервер) ниже low_mbps за low_minutes минут.
    low_mbps: int = 10
    low_count: int = 3
    low_minutes: int = 10
    # Уход с придушенного: до candidates кандидатов по одному; первый не медленнее switch_mbps —
    # сразу, иначе лучший, если он быстрее на gain_pct и не медленнее min_mbps. Не лучше никто —
    # «глобальная просадка», новых поисков cooldown_minutes. На поиск — не больше episode_mb,
    # на все поиски за сутки — не больше guard_daily_mb.
    candidates: int = 5
    switch_mbps: int = 25
    min_mbps: int = 12
    cooldown_minutes: int = 40
    episode_mb: int = 15
    guard_daily_mb: int = 300


@dataclass
class Fragment:
    # Дробление ClientHello (generator/fragment.py): первая TLS-запись соединения с сервером
    # уходит частями, и DPI, который ищет имя сайта (SNI) в одной записи, его не видит.
    # auto — демон включает дробление серверу, который без него не отвечает, а с ним
    # отвечает; always — всем серверам с TLS и REALITY; off — никогда.
    mode: str = "auto"
    # Поля freedom.fragment Xray: что дробить, длина кусков (байт) и пауза между ними (мс).
    # Длина и пауза — диапазоны: Xray берёт случайное значение для каждого куска.
    packets: str = "tlshello"
    length: str = "100-200"
    interval: str = "10-20"
    # Вторая ступень дробления в Xray (0.1.18, ТЗ R1): первые TCP-пакеты соединения режутся на
    # сегменты случайной длины (а не на записи TLS) — если ТСПУ собирает ClientHello из записей,
    # из сегментов он может его и не собрать. split = false — без этой ступени.
    split: bool = True
    split_packets: str = "1-3"
    split_length: str = "20-60"
    split_interval: str = "5-10"
    # Сервер на дроблении, который calm_probes проверок подряд отвечает и пробыл на нём не
    # меньше calm_hours, пробуется без дробления (до 0.1.18 — раз в сутки).
    calm_probes: int = 20
    calm_hours: int = 12
    # Больше escalations переводов на тяжёлый профиль за escalation_hours — сервер
    # «нестабилен по ТСПУ»: в работу его шлюз сам не ставит, пока эти часы не пройдут.
    escalations: int = 2
    escalation_hours: int = 6


@dataclass
class Routing:
    direct_domains: list[str] = field(
        default_factory=lambda: ["domain:ru", "domain:su", "domain:xn--p1ai"]
    )
    direct_ips: list[str] = field(default_factory=lambda: ["geoip:ru"])
    proxy_domains: list[str] = field(default_factory=list)
    conn_idle_s: int = 120
    home_country: str = "RU"


# Ещё шифрованные резолверы для bootstrap-DNS (0.1.18, ТЗ R4a): другие операторы и адреса,
# а Quad9 — на нестандартном порту 5053. Проверены 24.10.2026 по IP: AdGuard и DNS.SB отвечают;
# порт 5053 из сети разработки не ответил — его проверит монитор на самом шлюзе.
DEFAULT_BOOTSTRAP_EXTRA = (
    "https://94.140.14.140/dns-query",
    "https://185.222.222.222/dns-query",
    "https://9.9.9.9:5053/dns-query",
)


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
    # Дополнительные резолверы — после bootstrap; монитор проверяет все раз в
    # bootstrap_check_minutes (итог — в diag и событиях), а отказавшие резолвер пробует
    # последними.
    bootstrap_extra: list[str] = field(default_factory=lambda: list(DEFAULT_BOOTSTRAP_EXTRA))
    bootstrap_check_minutes: int = 30

    @property
    def resolvers(self) -> list[str]:
        """bootstrap и bootstrap_extra без повторов — все резолверы, по порядку."""
        return list(dict.fromkeys([*self.bootstrap, *self.bootstrap_extra]))


# Единственная версия Xray-core, с которой работает XGW (решение заказчика 17.10.2026,
# ASSUMPTIONS, п. 190; с 21.10.2026 — 26.10.21, п. 226): её ставят установка и
# `xgw update-xray`, другую `xgw diag` считает ошибкой. 26.10.21 — предварительный выпуск
# (pre-release); 26.10.10 и 26.10.17 разработчики Xray отозвали (корневые сертификаты со
# взломанными ключами). "latest" на GitHub — старый стабильный 26.3.27, поэтому "latest" и
# другие версии в конфиге не учитываются.
XRAY_VERSION = "26.10.21"


@dataclass
class XraySection:
    version: str = XRAY_VERSION
    api_port: int = 10085
    metrics_port: int = 10086
    socks_port: int = 10808
    http_port: int = 10809
    probe_port_base: int = 20001


# Единственная версия sing-box, с которой работает XGW (ASSUMPTIONS, п. 197): её ставят
# установка и `xgw update-singbox`, другую `xgw diag` считает ошибкой. Поля конфига проверены
# на этом выпуске.
SINGBOX_VERSION = "1.14.3"
CORE_MODES = ("auto", "xray", "sing-box")


@dataclass
class CoreSection:
    # Второе ядро — sing-box (generator/singbox.py): Xray остаётся точкой входа всего трафика,
    # а серверы, которые ведёт sing-box, подключены к Xray через его локальные входы.
    # auto — ядро и профиль обхода выбираются сами (generator/profiles.py); xray — только Xray
    # (серверы, которые умеет только sing-box, пропускаются); sing-box — sing-box для всех
    # серверов, которые он умеет.
    mode: str = "auto"
    # Пробовать мультиплексирование с паддингом (multiplex h2mux) серверу, который «замерзает».
    mux_padding: bool = True
    # Первый порт локальных входов sing-box на 127.0.0.1 — по одному на вариант сервера.
    port_base: int = 22001
    # Clash API sing-box на 127.0.0.1 (с паролем): по нему демон проверяет, что ядро живо.
    api_port: int = 10087


@dataclass
class Apply:
    restart_window: str = "04:00-05:00"


@dataclass
class Watchdog:
    interval_s: int = 20
    fail_threshold: int = 3
    wan_check: str = "ya.ru:443"
    # Ещё адреса проверки провайдера (0.1.18, ТЗ R3): «нет провайдера» (WAN_DOWN) — только
    # когда не отвечает ни один из wan_check и этих.
    wan_checks: list[str] = field(default_factory=lambda: ["vk.com:443", "mail.ru:443"])
    # Проверка с учётом трафика: сквозная проба не прошла, а через выбранный сервер за
    # busy_window_s пришло не меньше busy_bytes — проба опоздала в очереди забитого канала,
    # провал не засчитывается (VPN_IMPROVEMENT_PLAN §2.3).
    busy_window_s: int = 10
    busy_bytes: int = 1048576


@dataclass
class StatusConf:
    lan_page: bool = False
    token: str = ""


@dataclass
class Notify:
    desktop: bool = True
    min_interval_min: int = 10


@dataclass
class PanelConf:
    enabled: bool = True
    port: int = 8781
    # API приложения XGW для Android (watch/appapi.py): на 127.0.0.1, наружу — через Funnel.
    app_port: int = 8782


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
    # Устройства со своим сервером (Ф4): адрес IPv4 → отпечаток сервера. Аренда добавлена из
    # panel.json; остальные устройства — через основной сервер.
    routes: dict[str, str] = field(default_factory=dict)
    # Приоритет серверов: отпечаток → "high" или "low"; остальные — средние (priority.py).
    priority: dict[str, str] = field(default_factory=dict)
    # Ядро, закреплённое за сервером: отпечаток → "xray" или "sing-box"; остальные — auto.
    core: dict[str, str] = field(default_factory=dict)
    # Основной сервер включён или выключен в панели (speed.sticky); None — как в config.toml.
    sticky: bool | None = None
    # Имя шлюза в tailnet, для которого панель включила Serve (панель по tailnet, Т2);
    # пусто — не включала. Только тогда панель принимает Host «имя:8443».
    tailscale_serve: str = ""
    # Маршрут Tailscale выбран в панели (tailscale.route); None — как в config.toml.
    tailscale_route: str | None = None
    # Имя шлюза, для которого панель включила Funnel (API приложения, А1); пусто — нет.
    tailscale_funnel: str = ""
    # Устройства tailnet (адреса 100.x), что выходят в интернет через шлюз напрямую, мимо
    # Xray (выходной узел, ASSUMPTIONS п. 230); остальные — через Xray.
    tailscale_direct: list[str] = field(default_factory=list)


@dataclass
class Config:
    network: Network = field(default_factory=Network)
    capture: Capture = field(default_factory=Capture)
    subscriptions: list[Subscription] = field(default_factory=list)
    manual: Manual = field(default_factory=Manual)
    filters: Filters = field(default_factory=Filters)
    probe: Probe = field(default_factory=Probe)
    speed: Speed = field(default_factory=Speed)
    fragment: Fragment = field(default_factory=Fragment)
    routing: Routing = field(default_factory=Routing)
    dns: Dns = field(default_factory=Dns)
    xray: XraySection = field(default_factory=XraySection)
    core: CoreSection = field(default_factory=CoreSection)
    apply: Apply = field(default_factory=Apply)
    watchdog: Watchdog = field(default_factory=Watchdog)
    status: StatusConf = field(default_factory=StatusConf)
    notify: Notify = field(default_factory=Notify)
    panel: PanelConf = field(default_factory=PanelConf)
    tailscale: TailscaleConf = field(default_factory=TailscaleConf)
    tray: TrayConf = field(default_factory=TrayConf)
    managed: Managed = field(default_factory=Managed)


_SECTIONS = {
    "network": Network,
    "capture": Capture,
    "manual": Manual,
    "filters": Filters,
    "probe": Probe,
    "speed": Speed,
    "fragment": Fragment,
    "routing": Routing,
    "dns": Dns,
    "xray": XraySection,
    "core": CoreSection,
    "apply": Apply,
    "watchdog": Watchdog,
    "status": StatusConf,
    "notify": Notify,
    "panel": PanelConf,
    "tailscale": TailscaleConf,
    "tray": TrayConf,
}


def load(path: Path | str) -> tuple[Config, list[str]]:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"конфиг не найден: {path}") from exc
    except PermissionError as exc:
        # В конфиге подписка, поэтому его права — 0600 root.
        raise ConfigError(f"нет доступа к {path} — запустите команду через sudo") from exc
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
            headers=item.get("headers") or {},
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
    cfg.managed.core = dict(data["core"])
    if data["sticky"] is not None:
        cfg.speed.sticky = cfg.managed.sticky = data["sticky"]
    cfg.managed.tailscale_serve = data["tailscale"]["serve"]
    cfg.managed.tailscale_funnel = data["tailscale"]["funnel"]
    cfg.managed.tailscale_direct = [item["ip"] for item in data["tailscale"]["direct"]]
    if data["tailscale"]["route"] is not None:
        cfg.tailscale.route = cfg.managed.tailscale_route = data["tailscale"]["route"]
    warnings.extend(_merge_devices(cfg, data["devices"]))
    warnings.extend(_merge_devices(cfg, data["routes"], routes=True))
    return warnings


def _merge_devices(cfg: Config, devices: list[dict], *, routes: bool = False) -> list[str]:
    """Устройства из панели: статическая аренда и запись в bypass_hosts (мимо VPN) либо в
    managed.routes (routes — свой сервер; устройство мимо VPN своего сервера не получает).

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
        if mac in listed or (routes and ip in listed):
            continue  # уже мимо VPN (MAC или адрес в bypass_hosts) — в Xray не попадает
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
        if routes:
            cfg.managed.routes[ip] = device["server"]
            continue
        cfg.network.bypass_hosts.append(mac)
        listed.add(mac)
        cfg.managed.devices.append(mac)
    return warnings


def probe_bytes(url: str) -> int | None:
    """Размер пробы в байтах, если он известен заранее: записан в URL (…?bytes=65536)
    либо это файл по умолчанию. Для прочих адресов размер узнаёт сквозная проверка."""
    if url in KNOWN_PROBE_SIZES:
        return KNOWN_PROBE_SIZES[url]
    values = parse_qs(urlsplit(url).query).get("bytes")
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


# Ключи прежних версий, которые больше ничего не значат: в config.toml у заказчика они
# остаются, предупреждение объясняет почему, а не называет их «неизвестными».
_DROPPED = {
    "notify": ("telegram_bot_token", "telegram_chat_id", "commands", "telegram_api"),
}


def _build_section(cls, data: object, section: str, warnings: list[str]):
    if not isinstance(data, dict):
        warnings.append(f"секция [{section}] не является таблицей — значения по умолчанию")
        return cls()
    defaults = cls()
    known = {f.name for f in fields(cls)}
    values: dict[str, object] = {}
    for name, value in data.items():
        if name in _DROPPED.get(section, ()):
            warnings.append(f"{section}.{name}: Telegram в XGW больше нет — строку можно удалить")
            continue
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


def _validate_core(core: CoreSection) -> list[str]:
    """[core]: неизвестный режим — auto; порты — в своих пределах (иначе по умолчанию)."""
    warnings: list[str] = []
    defaults = CoreSection()
    mode = core.mode.strip().lower()
    if mode not in CORE_MODES:
        warnings.append(
            f'core.mode = "{core.mode}": ожидается auto, xray или sing-box — используется auto'
        )
        mode = defaults.mode
    core.mode = mode
    if not 1024 <= core.port_base <= 60000:
        warnings.append(
            f"core.port_base={core.port_base}: ожидается 1024–60000 — используется "
            f"{defaults.port_base}"
        )
        core.port_base = defaults.port_base
    if not 1 <= core.api_port <= 65535:
        warnings.append(
            f"core.api_port={core.api_port} вне диапазона — используется {defaults.api_port}"
        )
        core.api_port = defaults.api_port
    return warnings


def _validate(cfg: Config) -> list[str]:
    """Проверяет значения; опасные для работы исправляет на значения по умолчанию."""
    warnings: list[str] = []
    for name in ("include_regex", "exclude_regex", "multiplier_regex"):
        try:
            re.compile(getattr(cfg.filters, name))
        except re.error as exc:
            default = getattr(Filters(), name)
            warnings.append(f"filters.{name}: неверное регулярное выражение ({exc}) — сброшено")
            setattr(cfg.filters, name, default)
    if cfg.filters.max_members < 1:
        warnings.append("filters.max_members должен быть не меньше 1 — используется 1")
        cfg.filters.max_members = 1
    if cfg.watchdog.busy_window_s < 1:
        warnings.append("watchdog.busy_window_s должен быть не меньше 1 — используется 10")
        cfg.watchdog.busy_window_s = Watchdog().busy_window_s
    if cfg.watchdog.busy_bytes < 1:
        warnings.append("watchdog.busy_bytes должен быть не меньше 1 — используется 1048576")
        cfg.watchdog.busy_bytes = Watchdog().busy_bytes
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
    if cfg.capture.hold.strip().lower() not in ("block", "direct"):
        warnings.append(
            f"capture.hold={cfg.capture.hold!r}: допустимо block или direct; принято block"
        )
    route = cfg.tailscale.route.strip().lower()
    if route not in ("direct", "vpn"):
        warnings.append(
            f"tailscale.route={cfg.tailscale.route!r}: допустимо direct или vpn; принято direct"
        )
        route = TailscaleConf().route
    cfg.tailscale.route = route
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
    warnings.extend(_validate_speed(cfg.speed))
    warnings.extend(_validate_fragment(cfg.fragment))
    warnings.extend(_validate_core(cfg.core))
    warnings.extend(_validate_hosts(cfg))
    listening = {
        "tproxy": cfg.capture.tproxy_port,
        "api": cfg.xray.api_port,
        "metrics": cfg.xray.metrics_port,
        "socks": cfg.xray.socks_port,
        "http": cfg.xray.http_port,
        "panel": cfg.panel.port,
    }
    listening["core.api_port"] = cfg.core.api_port
    ports = list(listening.values()) + [
        cfg.xray.probe_port_base + i for i in range(cfg.filters.max_members + 8)
    ]
    if len(set(ports)) != len(ports):
        warnings.append("служебные порты и probe-порты пересекаются — проверьте [xray] и [capture]")
    for name, port in {**listening, "probe_port_base": cfg.xray.probe_port_base}.items():
        if not 1 <= port <= 65535:
            warnings.append(f"порт {name}={port} вне диапазона 1–65535")
    if cfg.xray.version.strip().lstrip("vV") != XRAY_VERSION:
        # "latest" стоял в прежнем примере конфига: это не выбор версии, предупреждать не о чем.
        if cfg.xray.version.strip() not in ("", "latest"):
            warnings.append(
                f'xray.version = "{cfg.xray.version}" не учитывается: XGW работает только с '
                f"Xray {XRAY_VERSION}"
            )
        cfg.xray.version = XRAY_VERSION
    return warnings


# Пределы настроек замера скорости: (наименьшее, наибольшее).
_SPEED_LIMITS = {
    "max_mb": (1, 100),
    "max_seconds": (2, 30),
    "unlimited_hours": (0, 168),
    "limited_hours": (0, 168),
    "spare_hours": (0, 168),
    "spare_mb": (1, 100),
    "gain_pct": (0, 1000),
    "hold_minutes": (0, 1440),
    "passive_seconds": (30, 600),
    "passive_mbps": (1, 1000),
    "low_mbps": (1, 1000),
    "low_count": (1, 10),
    "low_minutes": (1, 120),
    "candidates": (1, 20),
    "switch_mbps": (1, 1000),
    "min_mbps": (1, 1000),
    "cooldown_minutes": (1, 1440),
    "episode_mb": (1, 200),
    "guard_daily_mb": (0, 10000),
}


def _validate_speed(speed: Speed) -> list[str]:
    warnings: list[str] = []
    for name, (low, high) in _SPEED_LIMITS.items():
        value = getattr(speed, name)
        if not low <= value <= high:
            default = getattr(Speed(), name)
            warnings.append(
                f"speed.{name}={value}: допустимо от {low} до {high} — используется {default}"
            )
            setattr(speed, name, default)
    for name in ("url", "url_fallback"):
        value = getattr(speed, name).strip()
        if value and urlsplit(value).scheme not in ("http", "https"):
            default = getattr(Speed(), name)
            warnings.append(f"speed.{name}: ожидается http(s)://адрес — используется {default}")
            value = default
        setattr(speed, name, value)
    if not speed.url:
        speed.url, speed.url_fallback = speed.url_fallback, ""
    if speed.every_hours == 0:
        speed.unlimited_hours = speed.limited_hours = 0
        warnings.append(
            "speed.every_hours = 0: замеры скорости выключены; теперь это ключи "
            "speed.unlimited_hours и speed.limited_hours"
        )
    elif speed.every_hours != -1:
        warnings.append(
            f"speed.every_hours = {speed.every_hours} больше не действует: безлимитные серверы "
            f"замеряются раз в speed.unlimited_hours ({speed.unlimited_hours} ч), "
            f"лимитированные — раз в speed.limited_hours ({speed.limited_hours} ч); строку "
            "можно удалить"
        )
    return warnings


FRAGMENT_MODES = ("auto", "off", "always")


def _span(text: str, low: int) -> bool:
    """«N» или «N-M» (N ≤ M, N ≥ low) — так Xray записывает длину кусков и паузу."""
    match = re.fullmatch(r"(\d{1,5})(?:-(\d{1,5}))?", text)
    if not match:
        return False
    first = int(match.group(1))
    return first >= low and first <= int(match.group(2) or first)


def _validate_fragment(fragment: Fragment) -> list[str]:
    warnings: list[str] = []
    mode = fragment.mode.strip().lower()
    if mode not in FRAGMENT_MODES:
        warnings.append(
            f"fragment.mode={fragment.mode!r}: допустимо auto, off или always; принято auto"
        )
        mode = Fragment().mode
    fragment.mode = mode
    checks = {
        "packets": lambda value: value == "tlshello" or _span(value, 1),
        "length": lambda value: _span(value, 1),
        "interval": lambda value: _span(value, 0),
        "split_packets": lambda value: _span(value, 1),
        "split_length": lambda value: _span(value, 1),
        "split_interval": lambda value: _span(value, 0),
    }
    for name, valid in checks.items():
        value = getattr(fragment, name).strip()
        if not valid(value):
            default = getattr(Fragment(), name)
            warnings.append(
                f"fragment.{name}={getattr(fragment, name)!r}: ожидается, например, "
                f"{default!r} — используется {default!r}"
            )
            value = default
        setattr(fragment, name, value)
    for name, (low, high) in _FRAGMENT_LIMITS.items():
        value = getattr(fragment, name)
        if not low <= value <= high:
            default = getattr(Fragment(), name)
            warnings.append(
                f"fragment.{name}={value}: допустимо от {low} до {high} — используется {default}"
            )
            setattr(fragment, name, default)
    return warnings


_FRAGMENT_LIMITS = {
    "calm_probes": (1, 1000),
    "calm_hours": (1, 168),
    "escalations": (1, 50),
    "escalation_hours": (1, 168),
}


def _host_port(entry: str) -> bool:
    host, sep, port = entry.strip().rpartition(":")
    return bool(sep and host and port.isdigit() and 0 < int(port) < 65536)


def _validate_hosts(cfg: Config) -> list[str]:
    """probe.urls, watchdog.wan_checks, dns.bootstrap_extra и пределы других ключей 0.1.18:
    негодная запись пропускается с предупреждением, а не ломает остальные."""
    warnings: list[str] = []
    urls: list[str] = []
    for url in cfg.probe.urls:
        url = url.strip()
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            warnings.append(f"probe.urls: «{url}» — не http(s)://адрес; пропущен")
        elif url != cfg.probe.url and url not in urls:
            urls.append(url)
    cfg.probe.urls = urls
    if not 1 <= cfg.probe.host_pause_minutes <= 1440:
        warnings.append(
            f"probe.host_pause_minutes={cfg.probe.host_pause_minutes}: допустимо от 1 до 1440 "
            f"— используется {Probe().host_pause_minutes}"
        )
        cfg.probe.host_pause_minutes = Probe().host_pause_minutes
    checks: list[str] = []
    for entry in cfg.watchdog.wan_checks:
        if not _host_port(entry):
            warnings.append(f"watchdog.wan_checks: «{entry}» — ожидается хост:порт; пропущен")
        elif entry.strip() not in checks and entry.strip() != cfg.watchdog.wan_check.strip():
            checks.append(entry.strip())
    cfg.watchdog.wan_checks = checks
    extra: list[str] = []
    for entry in cfg.dns.bootstrap_extra:
        entry = entry.strip()
        if not entry.startswith(("https://", "udp://")):
            warnings.append(
                f"dns.bootstrap_extra: «{entry}» — ожидается https://… или udp://…; пропущен"
            )
        elif entry not in extra:
            extra.append(entry)
    cfg.dns.bootstrap_extra = extra
    if not 5 <= cfg.dns.bootstrap_check_minutes <= 1440:
        warnings.append(
            f"dns.bootstrap_check_minutes={cfg.dns.bootstrap_check_minutes}: допустимо от 5 до "
            f"1440 — используется {Dns().bootstrap_check_minutes}"
        )
        cfg.dns.bootstrap_check_minutes = Dns().bootstrap_check_minutes
    if not 1 <= cfg.tailscale.derp_fails <= 100:
        warnings.append(
            f"tailscale.derp_fails={cfg.tailscale.derp_fails}: допустимо от 1 до 100 — "
            f"используется {TailscaleConf().derp_fails}"
        )
        cfg.tailscale.derp_fails = TailscaleConf().derp_fails
    return warnings
