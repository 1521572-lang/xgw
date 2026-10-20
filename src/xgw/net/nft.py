"""Правила nftables: собственная таблица `ip xgw` (и `ip6 xgw6`), раздел 6.3 ТЗ.

Основа — официальная инструкция TPROXY для Xray, адаптированная под шлюз с двумя
картами. Чужие таблицы не затрагиваются, `flush ruleset` не используется: таблица
заменяется целиком и атомарно одной транзакцией («создать, удалить, создать»).

Три вида набора правил:
  перехват включён — prerouting (TPROXY) и output (метка), loopback_guard (Xray не
                     ходит к службам шлюза), forward только для обхода и ICMP;
  перехват снят    — xgw disable или fail_mode = open: обычный роутер, форвардинг
                     LAN → WAN с маскарадингом;
  blocked          — перехват включить нельзя (в применённом конфиге Xray нет его
                     inbound'а), capture.hold = "block": перехвата нет, и мимо VPN не
                     уходит ничего, кроме сокетов Xray, служебного и обхода (bypass_hosts);
  без LAN и без перехвата — таблицы нет вовсе.

Контейнеры Docker (capture.containers): их трафик приходит с мостов docker0 и br-* и
уходит в интернет транзитом через машину — ни output, ни prerouting LAN его не видят.
TPROXY для него не годится: Docker включает br_netfilter, цепочка prerouting для пакетов
с моста вызывается ещё на уровне моста, и сокет, который назначил TPROXY, ядро затем
сбрасывает (ip_rcv) — соединение не устанавливается (проверено на стенде). Поэтому своя
цепочка containers только ставит метку mark_containers, а маршрут по метке (net/iprule.py)
ведёт пакеты в TUN-интерфейс XGW, откуда их читает Xray; метка переживает и br_netfilter.
Ответы опубликованных портов контейнеров (ct direction reply) и адреса самой машины
(маршрутом их в TUN не увести — таблица local главнее) в Xray не попадают.

IPv6: `ip6 xgw6` запрещает форвардинг IPv6 из LAN и в LAN. При network.ipv6 = "proxy"
в ней же перехватывается IPv6 самой машины — теми же цепочками, что и IPv4 (output
помечает, prerouting на lo отдаёт Xray через TPROXY); при "off" цепочка v6_guard не
выпускает IPv6 машины наружу. Обе таблицы загружаются одной транзакцией (apply).
"""

from __future__ import annotations

import contextlib
import ipaddress
import re
from dataclasses import dataclass

from ..config import Config
from . import lan
from .cmd import CommandError, Runner

TABLE = "xgw"
TABLE6 = "xgw6"

# Диапазоны из инструкции Xray: частные, служебные и широковещательные адреса.
RESERVED4 = (
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "255.255.255.255/32",
)
# То же для IPv6: нулевой и loopback-адрес, ULA (в т.ч. локальные сети), link-local, multicast.
RESERVED6 = ("::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8")
# Служба времени идёт мимо перехвата: без точного времени не поднимется Reality.
TIME_USERS = ("_chrony", "systemd-timesync")
# Мосты Docker: docker0 и сети `docker network create` (br-<id>). Звёздочка — шаблон
# имени nftables; в правилах ufw (iptables) ей соответствует «+».
CONTAINER_IFS = ("docker0", "br-*")
NTS_KE_PORT = 4460  # chrony с NTS сначала получает ключи по TCP


@dataclass(frozen=True)
class Rules:
    """Всё, от чего зависит текст правил."""

    lan_if: str  # "" — только эта машина
    wan_if: str  # "" — «любой интерфейс, кроме LAN»
    capture_lan: bool
    capture_local: bool
    tproxy_port: int
    mark_proxy: int
    mark_bypass: int
    reserved: tuple[str, ...]
    bypass: tuple[str, ...]
    forward_icmp: bool
    dns_direct: str  # куда уходит DNS мимо Xray: «адрес» или «адрес:порт»; "" — никуда
    time_uids: tuple[int, ...]
    # IPv6 самой машины идёт через Xray (network.ipv6 = "proxy"); LAN IPv6 не получает.
    capture6: bool = False
    reserved6: tuple[str, ...] = ()
    # Трафик самой машины попадает в Xray не через TPROXY на lo, а маршрутом в
    # TUN-интерфейс tun_name (capture.method = "tun"); сеть LAN по-прежнему через TPROXY.
    tun: bool = False
    tun_name: str = ""
    # Интерфейсы контейнеров (шаблоны имён), чей трафик тоже идёт в Xray; пусто — нет.
    containers: tuple[str, ...] = ()
    mark_containers: int = 3
    # Режим blocked (capture.hold = "block", а перехват включить нельзя): перехвата нет,
    # и мимо VPN не уходит ничего — ни из LAN, ни с машины, ни из контейнеров.
    blocked: bool = False
    block_lan: bool = False
    block_local: bool = False
    block_containers: tuple[str, ...] = ()
    # IPv6 машины закрыт фаерволом (network.ipv6 = "off" или перехват невозможен), а не
    # только настройкой NetworkManager, которой может и не быть.
    v6_guard: bool = False

    @property
    def capture(self) -> bool:
        return self.capture_lan or self.capture_local

    @property
    def tproxy(self) -> bool:
        """TPROXY (и локальная доставка помеченных пакетов) нужен для LAN и для самой
        машины без TUN."""
        return self.capture_lan or (self.capture_local and not self.tun)

    @property
    def prerouting(self) -> bool:
        """Цепочка prerouting нужна для TPROXY и для метки контейнеров."""
        return self.tproxy or bool(self.containers)

    @property
    def prerouting6(self) -> bool:
        return self.capture6 and not self.tun

    @property
    def empty(self) -> bool:
        """Правил нет: ни LAN (форвардинг), ни перехвата, ни блокировки."""
        return (
            not self.lan_if and not self.capture
            and not self.block_local and not self.block_containers
        )


def time_service_uids() -> tuple[int, ...]:
    """uid пользователей службы времени, которые есть в системе: nft не загрузит
    правило с именем несуществующего пользователя, поэтому в текст идут числа."""
    try:
        import pwd
    except ImportError:  # не POSIX: разработка и юнит-тесты
        return ()
    uids = []
    for name in TIME_USERS:
        try:
            uids.append(pwd.getpwnam(name).pw_uid)
        except KeyError:
            continue
    return tuple(uids)


def build_rules(
    cfg: Config, *, capture: bool, blocked: bool = False,
    time_uids: tuple[int, ...] | None = None,
) -> tuple[Rules, list[str]]:
    """Параметры правил из конфига. capture=False — перехват снят (обычный роутер);
    blocked=True — перехвата нет, и то, что он вёл бы в Xray, закрыто (режим blocked)."""
    capture = capture and not blocked
    warnings: list[str] = []
    name = cfg.network.lan_if.strip()
    lan_if = lan.lan_interface(cfg)
    if name and not lan_if:
        warnings.append(f"network.lan_if={name!r}: недопустимое имя интерфейса — LAN не настроен")
    wan_name = cfg.network.wan_if.strip()
    wan_if = lan.wan_interface(cfg)
    if wan_name and not wan_if:
        warnings.append(f"network.wan_if={wan_name!r}: недопустимое имя интерфейса — пропущено")

    networks = [ipaddress.IPv4Network(item) for item in RESERVED4]
    networks6 = [ipaddress.IPv6Network(item) for item in RESERVED6]
    proxy6 = cfg.network.ipv6_proxy
    for item in cfg.capture.exclude_cidrs:
        try:
            network = ipaddress.ip_network(item.strip(), strict=False)
        except ValueError:
            warnings.append(f"capture.exclude_cidrs: «{item}» — не сеть; пропущено")
            continue
        if isinstance(network, ipaddress.IPv4Network):
            networks.append(network)
        elif proxy6:
            networks6.append(network)
        else:
            warnings.append(
                f"capture.exclude_cidrs: «{item}» — сеть IPv6, а IPv6 не проксируется "
                "(network.ipv6 = off); пропущено"
            )
    reserved = tuple(str(network) for network in ipaddress.collapse_addresses(networks))
    reserved6 = tuple(str(network) for network in ipaddress.collapse_addresses(networks6))

    bypass: list[str] = []
    if lan_if:
        bypass, bypass_warnings = lan.bypass_addresses(cfg)
        warnings.extend(bypass_warnings)

    dns_direct = _dns_direct(cfg) if lan_if else ""
    if lan_if and not dns_direct:
        warnings.append(
            "dns.direct_servers пуст: устройствам в обход VPN и всей сети после "
            "xgw disable некому отвечать на DNS-запросы к шлюзу"
        )
    return (
        Rules(
            lan_if=lan_if,
            wan_if=wan_if,
            capture_lan=capture and cfg.capture.lan and bool(lan_if),
            capture_local=capture and cfg.capture.local,
            tproxy_port=cfg.capture.tproxy_port,
            mark_proxy=cfg.capture.mark_proxy,
            mark_bypass=cfg.capture.mark_bypass,
            reserved=reserved,
            bypass=tuple(bypass),
            forward_icmp=cfg.capture.forward_icmp,
            dns_direct=dns_direct,
            time_uids=time_service_uids() if time_uids is None else time_uids,
            capture6=capture and cfg.capture.local and proxy6,
            reserved6=reserved6,
            tun=capture and cfg.capture.local and cfg.capture.tun,
            tun_name=cfg.capture.tun_name,
            containers=CONTAINER_IFS if capture and containers_wanted(cfg) else (),
            mark_containers=cfg.capture.mark_containers,
            blocked=blocked,
            block_lan=blocked and cfg.capture.lan and bool(lan_if),
            block_local=blocked and cfg.capture.local,
            block_containers=CONTAINER_IFS if blocked and containers_wanted(cfg) else (),
            v6_guard=cfg.capture.local and (blocked or not proxy6),
        ),
        warnings,
    )


def containers_wanted(cfg: Config) -> bool:
    """Перехват контейнеров включён в конфиге (сам перехват — тоже)."""
    return cfg.capture.containers and (cfg.capture.lan or cfg.capture.local)


def _dns_direct(cfg: Config) -> str:
    """Первый из direct_servers, записанный адресом IPv4 (с портом или без)."""
    for entry in cfg.dns.direct_servers:
        address, sep, port = entry.strip().rpartition(":")
        if not (sep and port.isdigit()):
            address, port = entry.strip(), ""
        try:
            ipaddress.IPv4Address(address)
        except ValueError:
            continue
        return f"{address}:{port}" if port and port != "53" else address
    return ""


# --- текст правил ---------------------------------------------------------------


def _set(name: str, elements: tuple[str, ...], kind: str = "ipv4_addr") -> list[str]:
    lines = [f"set {name} {{", f"    type {kind}", "    flags interval"]
    if elements:
        lines.append("    elements = { " + ", ".join(elements) + " }")
    lines.append("}")
    return lines


def _chain(name: str, header: str, rules: list[str]) -> list[str]:
    return [f"chain {name} {{", f"    {header}", *(f"    {rule}" for rule in rules), "}"]


def render(rules: Rules) -> str:
    """Текст для `nft -f`: полная замена таблицы `ip xgw`. Пусто — таблица не нужна."""
    if rules.empty:
        return ""
    if rules.blocked:
        return _table("ip", TABLE, _blocked_blocks(rules))
    lan_if, proxy, bypass = rules.lan_if, f"{rules.mark_proxy:#x}", f"{rules.mark_bypass:#x}"
    out = f'oifname "{rules.wan_if}"' if rules.wan_if else f'oifname != "{lan_if}"'
    blocks: list[list[str]] = [_set("reserved4", rules.reserved)]
    if lan_if:
        blocks.append(_set("bypass4", rules.bypass))

    tproxy = (
        "meta l4proto { tcp, udp } counter "
        f"tproxy to 127.0.0.1:{rules.tproxy_port} meta mark set {proxy} accept"
    )
    if rules.prerouting:
        if rules.containers:
            # Обычная цепочка (без hook) — раньше prerouting, который в неё переходит.
            blocks.append([
                "chain containers {",
                "    meta l4proto != { tcp, udp } return",
                # Ответы опубликованных портов контейнеров (docker run -p) — не в Xray.
                "    ct direction reply return",
                "    fib daddr type local return",
                "    ip daddr @reserved4 th dport != 53 return",
                f"    meta l4proto {{ tcp, udp }} counter meta mark set {rules.mark_containers:#x}",
                "}",
            ])
        sources = ([f'"{lan_if}"'] if rules.capture_lan else []) + (
            ['"lo"'] if rules.capture_local and not rules.tun else []
        )
        prerouting = [f'iifname "{name}" goto containers' for name in rules.containers]
        if sources:
            only = sources[0] if len(sources) == 1 else "{ " + ", ".join(sources) + " }"
            prerouting += [
                f"iifname != {only} return",  # входящие из интернета в Xray не попадают
                "meta l4proto != { tcp, udp } return",
            ]
            if rules.capture_local and not rules.tun:
                # На lo перехватывается только то, что пометила цепочка output.
                prerouting.append(f'iifname "lo" meta mark != {proxy} return')
            if rules.capture_lan:
                prerouting.append("ip saddr @bypass4 return")
            prerouting += [
                # Сам шлюз и частные сети — мимо Xray; DNS (порт 53) перехватывается всегда.
                "fib daddr type local th dport != 53 return",
                "ip daddr @reserved4 th dport != 53 return",
                tproxy,
            ]
        blocks.append(
            _chain(
                "prerouting",
                "type filter hook prerouting priority mangle; policy accept;",
                prerouting,
            )
        )
    if rules.capture_local:
        output = [
            f"meta mark {bypass} return",  # сокеты Xray и прямые запросы XGW
            "ct direction reply return",  # ответы на входящие соединения (SSH на шлюз)
            "meta l4proto != { tcp, udp } return",
            "fib daddr type local return",
            "ip daddr @reserved4 th dport != 53 return",
            "udp sport 68 return",  # DHCP-клиент WAN
        ]
        for uid in rules.time_uids:
            output.append(f"meta skuid {uid} udp dport 123 return")
            output.append(f"meta skuid {uid} tcp dport {NTS_KE_PORT} return")
        output.append(f"meta l4proto {{ tcp, udp }} counter meta mark set {proxy}")
        blocks.append(
            _chain("output", "type route hook output priority mangle; policy accept;", output)
        )

    if rules.capture:
        # Сниффинг подставляет в соединение имя из запроса, а outbound direct
        # разрешает его сам: имя из direct_domains, указывающее на 127.0.0.1, привело
        # бы Xray к службам самого шлюза. Сокеты direct помечены mark_bypass —
        # к loopback с этой меткой не пускаем. Свои запросы к loopback XGW шлёт без
        # метки (marknet.connect_marked), остальные сокеты Xray к нему не ходят.
        blocks.append(
            _chain(
                "loopback_guard",
                "type filter hook output priority filter; policy accept;",
                [f"meta mark {bypass} ip daddr 127.0.0.0/8 counter reject"],
            )
        )

    if lan_if:
        if rules.dns_direct:
            # DNS-запрос к самому шлюзу от тех, кого Xray не обслуживает, уходит на
            # прямой резолвер: dnsmasq DNS не отвечает (port=0).
            who = "ip saddr @bypass4 " if rules.capture_lan else ""
            blocks.append(
                _chain(
                    "dns_direct",
                    "type nat hook prerouting priority dstnat; policy accept;",
                    [
                        f'iifname "{lan_if}" {who}meta l4proto {{ tcp, udp }} th dport 53 '
                        f"fib daddr type local counter dnat to {rules.dns_direct}"
                    ],
                )
            )
        forward = [
            # Чужой форвардинг (Docker, libvirt) — не наше дело.
            f'iifname != "{lan_if}" oifname != "{lan_if}" accept',
            "tcp flags syn tcp option maxseg size set rt mtu",  # PPPoE у провайдера
            "ct state established,related accept",
        ]
        if rules.capture_lan:
            forward.append(f'iifname "{lan_if}" {out} ip saddr @bypass4 counter accept')
            if rules.forward_icmp:
                forward.append(f'iifname "{lan_if}" {out} meta l4proto icmp counter accept')
        else:
            forward.append(f'iifname "{lan_if}" {out} counter accept')
        blocks.append(
            _chain("forward", "type filter hook forward priority filter; policy drop;", forward)
        )
        blocks.append(
            _chain(
                "postrouting",
                "type nat hook postrouting priority srcnat; policy accept;",
                [f'iifname "{lan_if}" {out} counter masquerade'],
            )
        )

    return _table("ip", TABLE, blocks)


def _table(family: str, name: str, blocks: list[list[str]]) -> str:
    """Полная замена таблицы одной транзакцией: «создать, удалить, создать»."""
    lines = [f"table {family} {name}", f"delete table {family} {name}", f"table {family} {name} {{"]
    for index, block in enumerate(blocks):
        if index:
            lines.append("")
        lines.extend(f"    {line}" for line in block)
    lines.append("}")
    return "\n".join(lines) + "\n"


def _blocked_blocks(rules: Rules) -> list[list[str]]:
    """`ip xgw` в режиме blocked: перехвата нет, и мимо VPN уходит только то, что ушло бы
    мимо него и при включённом перехвате, — сокеты Xray (метка mark_bypass), служебное
    машины (DHCP-клиент, время), связь с самим шлюзом и LAN, устройства из bypass_hosts.
    Остальное отбивается сразу (reject), а не висит до таймаута."""
    lan_if, bypass = rules.lan_if, f"{rules.mark_bypass:#x}"
    out = f'oifname "{rules.wan_if}"' if rules.wan_if else f'oifname != "{lan_if}"'
    reject = "counter reject with icmp type admin-prohibited"
    blocks: list[list[str]] = [_set("reserved4", rules.reserved)]
    if lan_if:
        blocks.append(_set("bypass4", rules.bypass))
    if rules.block_containers:
        blocks.append(_set("bypass_containers", ()))  # [capture] containers_bypass — Ф4
    if rules.block_local:
        output = [
            'oifname "lo" accept',
            f"meta mark {bypass} accept",  # сокеты Xray/sing-box и прямые запросы XGW
            "ct direction reply accept",  # ответы на входящие (SSH на шлюз, панель)
            "fib daddr type local accept",
            "ip daddr @reserved4 meta l4proto != { tcp, udp } accept",  # ping в LAN и т. п.
            "ip daddr @reserved4 th dport != 53 accept",  # LAN, link-local, multicast
            "udp sport 68 udp dport 67 accept",  # DHCP-клиент WAN
        ]
        for uid in rules.time_uids:
            output.append(f"meta skuid {uid} udp dport 123 accept")
            output.append(f"meta skuid {uid} tcp dport {NTS_KE_PORT} accept")
        output += ["meta l4proto tcp counter reject with tcp reset", reject]
        blocks.append(_chain(
            "block_output", "type filter hook output priority filter; policy accept;", output
        ))
    forward: list[str] = []
    # Контейнеры: в режиме on их уводит в TUN цепочка containers, а здесь её нет — без этих
    # правил мост → WAN прошёл бы правилом «чужой форвардинг» ниже. Между мостами, в частные
    # сети (как и в режиме on) и ответы опубликованных портов (ct reply) — можно.
    bridges = " ".join(f'oifname != "{name}"' for name in rules.block_containers)
    for name in rules.block_containers:
        forward.append(
            f'iifname "{name}" {bridges} ct direction original ip daddr != @reserved4 '
            f"ip saddr != @bypass_containers {reject}"
        )
    if lan_if:
        forward += [
            f'iifname != "{lan_if}" oifname != "{lan_if}" accept',  # libvirt и т. п.
            "tcp flags syn tcp option maxseg size set rt mtu",
        ]
        if rules.block_lan:
            forward += [
                # Установленные соединения — только у тех, кому обход разрешён: сессии,
                # открытые при снятом перехвате, по записи conntrack не доживают.
                f'iifname "{lan_if}" ip saddr @bypass4 ct state established,related accept',
                f'oifname "{lan_if}" ip daddr @bypass4 ct state established,related accept',
                f'iifname "{lan_if}" {out} ip saddr @bypass4 counter accept',
                # TCP — сбросом: и открытая раньше сессия обрывается сразу, а не висит.
                f'iifname "{lan_if}" meta l4proto tcp counter reject with tcp reset',
                f'iifname "{lan_if}" {reject}',
            ]
        else:  # LAN в конфиге не перехватывается — и в режиме on он ходит напрямую
            forward += [
                "ct state established,related accept",
                f'iifname "{lan_if}" {out} counter accept',
            ]
    if forward:
        policy = "drop" if lan_if else "accept"
        blocks.append(_chain(
            "forward", f"type filter hook forward priority filter; policy {policy};", forward
        ))
    if lan_if:
        if rules.dns_direct:
            who = "ip saddr @bypass4 " if rules.block_lan else ""
            blocks.append(_chain(
                "dns_direct",
                "type nat hook prerouting priority dstnat; policy accept;",
                [f'iifname "{lan_if}" {who}meta l4proto {{ tcp, udp }} th dport 53 '
                 f"fib daddr type local counter dnat to {rules.dns_direct}"],
            ))
        blocks.append(_chain(
            "postrouting",
            "type nat hook postrouting priority srcnat; policy accept;",
            [f'iifname "{lan_if}" {out} counter masquerade'],
        ))
    return blocks


def render6(rules: Rules) -> str:
    """`ip6 xgw6`: IPv6 из LAN и в LAN не форвардится; при ipv6 = "proxy" ещё и
    перехват IPv6 самой машины, при ipv6 = "off" — v6_guard: IPv6 машины наружу закрыт.
    Пусто — без LAN, без перехвата IPv6 и без v6_guard."""
    if not rules.lan_if and not rules.capture6 and not rules.v6_guard:
        return ""
    blocks: list[list[str]] = []
    if rules.capture6:
        proxy, bypass = f"{rules.mark_proxy:#x}", f"{rules.mark_bypass:#x}"
        blocks.append(_set("reserved6", rules.reserved6, "ipv6_addr"))
        if rules.prerouting6:
            blocks.append(
                _chain(
                    "prerouting",
                    "type filter hook prerouting priority mangle; policy accept;",
                    [
                        'iifname != "lo" return',  # из интернета в Xray не попадает ничто
                        "meta l4proto != { tcp, udp } return",
                        f"meta mark != {proxy} return",  # на lo — только пометка из output
                        "fib daddr type local th dport != 53 return",
                        "ip6 daddr @reserved6 th dport != 53 return",
                        "meta l4proto { tcp, udp } counter "
                        f"tproxy ip6 to [::1]:{rules.tproxy_port} meta mark set {proxy} accept",
                    ],
                )
            )
        output = [
            f"meta mark {bypass} return",  # сокеты Xray и прямые запросы XGW
            "ct direction reply return",  # ответы на входящие соединения (SSH на шлюз)
            "meta l4proto != { tcp, udp } return",
            "fib daddr type local return",
            "ip6 daddr @reserved6 th dport != 53 return",
            "udp sport 546 return",  # DHCPv6-клиент
        ]
        for uid in rules.time_uids:
            output.append(f"meta skuid {uid} udp dport 123 return")
            output.append(f"meta skuid {uid} tcp dport {NTS_KE_PORT} return")
        output.append(f"meta l4proto {{ tcp, udp }} counter meta mark set {proxy}")
        blocks.append(
            _chain("output", "type route hook output priority mangle; policy accept;", output)
        )
        # То же, что loopback_guard в `ip xgw`: прямой запрос Xray не должен попасть
        # на службы самого шлюза, если имя разрешилось в ::1.
        blocks.append(
            _chain(
                "loopback_guard",
                "type filter hook output priority filter; policy accept;",
                [f"meta mark {bypass} ip6 daddr ::1 counter reject"],
            )
        )
    if rules.v6_guard:
        # IPv6 машины наружу закрыт: при network.ipv6 = "off" его иначе держала бы только
        # настройка NetworkManager, а WAN может быть и не под ним. Сокеты Xray (метка),
        # служебный ICMPv6 самого ядра (ответы ND, ошибки — без метки и бывает на
        # глобальный адрес), link-local и multicast (ND, RA, DHCPv6-клиент) — можно.
        blocks.append(
            _chain(
                "v6_guard",
                "type filter hook output priority filter; policy accept;",
                [
                    'oifname "lo" accept',
                    f"meta mark {rules.mark_bypass:#x} accept",
                    "icmpv6 type { destination-unreachable, packet-too-big, time-exceeded, "
                    "parameter-problem, nd-router-solicit, nd-router-advert, "
                    "nd-neighbor-solicit, nd-neighbor-advert } accept",
                    "ip6 daddr { fe80::/10, ff00::/8 } accept",
                    "ct direction reply accept",
                    "meta l4proto tcp counter reject with tcp reset",
                    "counter reject with icmpv6 type admin-prohibited",
                ],
            )
        )
    if rules.lan_if:
        blocks.append(
            _chain(
                "forward",
                "type filter hook forward priority filter; policy accept;",
                [f'iifname "{rules.lan_if}" drop', f'oifname "{rules.lan_if}" drop'],
            )
        )
    return _table("ip6", TABLE6, blocks)


def _delete_text(family: str, table: str) -> str:
    """Удаление таблицы, которое не падает, если её нет."""
    return f"table {family} {table}\ndelete table {family} {table}\n"


# --- загрузка в ядро ------------------------------------------------------------


def check(text: str, runner: Runner) -> None:
    """Проверка без загрузки: `nft -c -f -`."""
    runner(["nft", "-c", "-f", "-"], input=text)


def apply(rules: Rules, runner: Runner) -> list[str]:
    """Загружает правила (или убирает таблицы, если правил нет) — обе таблицы одной
    транзакцией: между ними правила IPv4 и IPv6 не расходятся. Возвращает предупреждения:
    таблица IPv6 не обязательна — IPv6 в ядре может быть выключен; тогда IPv4 загружается
    отдельно. Обязательна она, когда IPv6 машины проксируется или закрыт (v6_guard)."""
    text = render(rules) or _delete_text("ip", TABLE)
    check(text, runner)
    try:
        runner(["nft", "-f", "-"], input=text + (render6(rules) or _delete_text("ip6", TABLE6)))
    except CommandError as exc:
        if rules.capture6 or rules.v6_guard:
            raise  # без этих правил IPv6 машины ушёл бы мимо VPN
        runner(["nft", "-f", "-"], input=text)
        return [f"таблица ip6 {TABLE6} не загружена: {exc}"]
    return []


def delete(runner: Runner) -> None:
    """Убирает обе таблицы XGW; чужие таблицы не трогает."""
    runner(["nft", "-f", "-"], input=_delete_text("ip", TABLE))
    with contextlib.suppress(CommandError):  # IPv6 в ядре выключен — таблицы и не было
        runner(["nft", "-f", "-"], input=_delete_text("ip6", TABLE6))


def loaded_chains(
    runner: Runner, family: str = "ip", table: str = TABLE
) -> set[str] | None:
    """Имена цепочек загруженной таблицы (`ip xgw` или `ip6 xgw6`); пустое множество —
    таблицы нет, None — узнать не удалось (нет прав или nft)."""
    chains = chain_rules(runner, family, table)
    return None if chains is None else set(chains)


def chain_rules(
    runner: Runner, family: str = "ip", table: str = TABLE
) -> dict[str, bool] | None:
    """Цепочки загруженной таблицы: имя → есть ли в ней хоть одно правило. Пустыми свои
    цепочки XGW не бывают (test_rendered_chains_are_never_empty) — такую оставляет чужой
    `nft flush table ip xgw` или `flush chain`: имена на месте, а перехвата нет. {} —
    таблицы нет, None — узнать не удалось (нет прав или nft)."""
    try:
        listing = runner(["nft", "list", "table", family, table])
    except CommandError as exc:
        text = str(exc)
        if "No such file or directory" in text or "does not exist" in text:
            return {}
        return None
    chains: dict[str, bool] = {}
    for name, body in re.findall(
        r"^\s*chain (\w+) \{\n(.*?)^\s*\}", listing, flags=re.MULTILINE | re.DOTALL
    ):
        chains[name] = chains.get(name, False) or _has_rules(body)
    return chains


def _has_rules(body: str) -> bool:
    """Есть ли в теле цепочки (вывод `nft list`) хоть одно правило, кроме строки hook."""
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith(("type ", "policy ", "comment ", "#")):
            return True
    return False
