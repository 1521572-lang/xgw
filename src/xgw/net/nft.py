"""Правила nftables: собственная таблица `ip xgw` (и `ip6 xgw6`), раздел 6.3 ТЗ.

Основа — официальная инструкция TPROXY для Xray, адаптированная под шлюз с двумя
картами. Чужие таблицы не затрагиваются, `flush ruleset` не используется: таблица
заменяется целиком и атомарно одной транзакцией («создать, удалить, создать»).

Три вида набора правил:
  перехват включён — prerouting (TPROXY) и output (метка), loopback_guard (Xray не
                     ходит к службам шлюза), forward только для обхода и ICMP;
  перехват снят    — xgw disable или fail_mode = open: обычный роутер, форвардинг
                     LAN → WAN с маскарадингом;
  без LAN и без перехвата — таблицы нет вовсе.

IPv6: по умолчанию `ip6 xgw6` только запрещает форвардинг IPv6 из LAN и в LAN.
При network.ipv6 = "proxy" в ней же перехватывается IPv6 самой машины — теми же
цепочками, что и IPv4 (output помечает, prerouting на lo отдаёт Xray через TPROXY).
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

    @property
    def capture(self) -> bool:
        return self.capture_lan or self.capture_local

    @property
    def empty(self) -> bool:
        """Правил нет: ни LAN (форвардинг), ни перехвата."""
        return not self.lan_if and not self.capture


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
    cfg: Config, *, capture: bool, time_uids: tuple[int, ...] | None = None
) -> tuple[Rules, list[str]]:
    """Параметры правил из конфига. capture=False — перехват снят (обычный роутер)."""
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
        ),
        warnings,
    )


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
    lan_if, proxy, bypass = rules.lan_if, f"{rules.mark_proxy:#x}", f"{rules.mark_bypass:#x}"
    out = f'oifname "{rules.wan_if}"' if rules.wan_if else f'oifname != "{lan_if}"'
    blocks: list[list[str]] = [_set("reserved4", rules.reserved)]
    if lan_if:
        blocks.append(_set("bypass4", rules.bypass))

    if rules.capture:
        sources = ([f'"{lan_if}"'] if rules.capture_lan else []) + (
            ['"lo"'] if rules.capture_local else []
        )
        only = sources[0] if len(sources) == 1 else "{ " + ", ".join(sources) + " }"
        prerouting = [
            f"iifname != {only} return",  # входящие из интернета в Xray не попадают
            "meta l4proto != { tcp, udp } return",
        ]
        if rules.capture_local:
            # На lo перехватывается только то, что пометила цепочка output.
            prerouting.append(f'iifname "lo" meta mark != {proxy} return')
        if rules.capture_lan:
            prerouting.append("ip saddr @bypass4 return")
        prerouting += [
            # Сам шлюз и частные сети — мимо Xray; DNS (порт 53) перехватывается всегда.
            "fib daddr type local th dport != 53 return",
            "ip daddr @reserved4 th dport != 53 return",
            "meta l4proto { tcp, udp } counter "
            f"tproxy to 127.0.0.1:{rules.tproxy_port} meta mark set {proxy} accept",
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

    lines = [f"table ip {TABLE}", f"delete table ip {TABLE}", f"table ip {TABLE} {{"]
    for index, block in enumerate(blocks):
        if index:
            lines.append("")
        lines.extend(f"    {line}" for line in block)
    lines.append("}")
    return "\n".join(lines) + "\n"


def render6(rules: Rules) -> str:
    """`ip6 xgw6`: IPv6 из LAN и в LAN не форвардится; при ipv6 = "proxy" ещё и
    перехват IPv6 самой машины. Пусто — без LAN и без перехвата IPv6."""
    if not rules.lan_if and not rules.capture6:
        return ""
    blocks: list[list[str]] = []
    if rules.capture6:
        proxy, bypass = f"{rules.mark_proxy:#x}", f"{rules.mark_bypass:#x}"
        blocks.append(_set("reserved6", rules.reserved6, "ipv6_addr"))
        blocks.append(
            _chain(
                "prerouting",
                "type filter hook prerouting priority mangle; policy accept;",
                [
                    'iifname != "lo" return',  # из интернета в Xray не попадает ничто
                    "meta l4proto != { tcp, udp } return",
                    f"meta mark != {proxy} return",  # на lo — только пометка цепочки output
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
    if rules.lan_if:
        blocks.append(
            _chain(
                "forward",
                "type filter hook forward priority filter; policy accept;",
                [f'iifname "{rules.lan_if}" drop', f'oifname "{rules.lan_if}" drop'],
            )
        )
    lines = [f"table ip6 {TABLE6}", f"delete table ip6 {TABLE6}", f"table ip6 {TABLE6} {{"]
    for index, block in enumerate(blocks):
        if index:
            lines.append("")
        lines.extend(f"    {line}" for line in block)
    lines.append("}")
    return "\n".join(lines) + "\n"


def _delete_text(family: str, table: str) -> str:
    """Удаление таблицы, которое не падает, если её нет."""
    return f"table {family} {table}\ndelete table {family} {table}\n"


# --- загрузка в ядро ------------------------------------------------------------


def check(text: str, runner: Runner) -> None:
    """Проверка без загрузки: `nft -c -f -`."""
    runner(["nft", "-c", "-f", "-"], input=text)


def apply(rules: Rules, runner: Runner) -> list[str]:
    """Загружает правила (или убирает таблицы, если правил нет). Возвращает
    предупреждения: таблица IPv6 не обязательна — IPv6 в ядре может быть выключен."""
    warnings: list[str] = []
    text = render(rules) or _delete_text("ip", TABLE)
    check(text, runner)
    runner(["nft", "-f", "-"], input=text)
    try:
        runner(["nft", "-f", "-"], input=render6(rules) or _delete_text("ip6", TABLE6))
    except CommandError as exc:
        if rules.capture6:
            raise  # IPv6 проксируется: без этих правил он ушёл бы мимо перехвата
        warnings.append(f"таблица ip6 {TABLE6} не загружена: {exc}")
    return warnings


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
    try:
        listing = runner(["nft", "list", "table", family, table])
    except CommandError as exc:
        text = str(exc)
        if "No such file or directory" in text or "does not exist" in text:
            return set()
        return None
    return set(re.findall(r"^\s*chain (\w+) \{", listing, flags=re.MULTILINE))
