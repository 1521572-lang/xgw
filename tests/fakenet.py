"""Подмена ядра для тестов сети: понимает те команды nft и ip, которыми пользуется XGW.

Хранит «загруженные» таблицы nftables, правила `ip rule`, маршруты таблиц перехвата
(отдельно для IPv4 и для `ip -6`) и TUN-интерфейсы; все вызовы записывает в calls — по
ним тесты проверяют порядок.
"""

from __future__ import annotations

import ipaddress
import json
import re

from xgw.net.cmd import CommandError


class FakeKernel:
    def __init__(self) -> None:
        self.tables: dict[tuple[str, str], str] = {}
        self.rules: list[dict] = []
        self.rules6: list[dict] = []
        # Маршруты таблиц перехвата: (семейство, номер таблицы) → список маршрутов.
        self.route_tables: dict[tuple[int, str], list[dict]] = {}
        self.links: dict[str, str] = {}  # интерфейс → вид (tun)
        # Поднятые интерфейсы и их адреса. Интерфейс, записанный в links напрямую (его
        # «создал Xray»), не поднят XGW и адреса не имеет.
        self.up: set[str] = set()
        self.addresses: dict[str, set[str]] = {}
        self.calls: list[tuple[str, ...]] = []
        self.refuse: str | None = None  # подстрока команды, которая «не выполняется»
        self.forbidden = False  # запуск не от root: nft ничего не показывает
        self.refuse_ip6 = False  # таблицу ip6 ядро не принимает (IPv6 в ядре нет)
        self.loads: list[str] = []  # тексты принятых транзакций `nft -f -`
        # Интерфейсы LAN (имя → поднят ли) для `ip -j link show dev`; и включена ли
        # проверка источника с учётом метки (net.ipv4.conf.all.src_valid_mark): тогда
        # `ip route get … iif LAN mark …` без маршрута throw для подсети отвечает ошибкой.
        self.lan_links: dict[str, bool] = {}
        self.src_valid_mark = False

    def __call__(self, argv, *, input=None, timeout=15.0, check=True) -> str:
        argv = list(argv)
        self.calls.append(tuple(argv))
        command = " ".join(argv)
        if self.refuse and self.refuse in command:
            raise CommandError(f"{command}: отказано")
        if argv[0] == "nft":
            return self._nft(argv, input or "")
        if argv[:2] == ["ip", "-6"]:
            return self._ip(["ip", *argv[2:]], command, 6)
        return self._ip(argv, command, 4)

    def routes(self, table: int | str = 100, family: int = 4) -> list[dict]:
        """Маршруты таблицы (для проверок)."""
        return self.route_tables.setdefault((family, str(table)), [])

    def _has_local(self, family: int) -> bool:
        return any(
            route.get("type") == "local"
            for (fam, _table), routes in self.route_tables.items() if fam == family
            for route in routes
        )

    @property
    def route(self) -> bool:
        """Есть локальный маршрут TPROXY (`local 0.0.0.0/0 dev lo`)."""
        return self._has_local(4)

    @property
    def route6(self) -> bool:
        return self._has_local(6)

    def _link(self, argv: list[str], command: str) -> str:
        """ip -d -j link show / ip -j addr show / ip tuntap add / ip link set /
        ip addr replace / ip link del."""
        if argv[:5] == ["ip", "-d", "-j", "link", "show"]:
            name = argv[6]
            if name not in self.links:
                raise CommandError(f'{command}: Device "{name}" does not exist.')
            return json.dumps([{"ifname": name, "linkinfo": {"info_kind": self.links[name]}}])
        if argv[:4] == ["ip", "-j", "addr", "show"]:
            name = argv[5]
            if name not in self.links:
                raise CommandError(f'{command}: Device "{name}" does not exist.')
            flags = ["POINTOPOINT", "NOARP", *(["UP"] if name in self.up else [])]
            addr_info = [
                {"family": "inet", "local": local, "prefixlen": int(prefix)}
                for local, _, prefix in (
                    item.partition("/") for item in sorted(self.addresses.get(name, ()))
                )
            ]
            return json.dumps([{"ifname": name, "flags": flags, "addr_info": addr_info}])
        if argv[:3] == ["ip", "tuntap", "add"]:
            name = argv[4]
            if name in self.links:
                raise CommandError(f"{command}: ioctl(TUNSETIFF): Device or resource busy")
            self.links[name] = "tun"
            return ""
        if argv[:3] == ["ip", "link", "set"]:
            if argv[4] not in self.links:
                raise CommandError(f'{command}: Cannot find device "{argv[4]}"')
            if argv[-1] == "up":
                self.up.add(argv[4])
            return ""
        if argv[:3] == ["ip", "addr", "replace"]:
            if argv[5] not in self.links:
                raise CommandError(f'{command}: Cannot find device "{argv[5]}"')
            self.addresses.setdefault(argv[5], set()).add(argv[3])
            return ""
        if argv[:3] == ["ip", "link", "del"]:
            name = argv[4]
            if name not in self.links:
                raise CommandError(f'{command}: Cannot find device "{name}"')
            del self.links[name]
            self.up.discard(name)
            self.addresses.pop(name, None)
            for routes in self.route_tables.values():
                routes[:] = [route for route in routes if route.get("dev") != name]
            return ""
        raise AssertionError(f"неожиданная команда: {command}")

    def _route(self, argv: list[str], command: str, family: int) -> str:
        """ip route replace/del и ip -j route show для таблиц перехвата."""
        body = argv[2:] if argv[1] == "route" else argv[4:]
        table = body[body.index("table") + 1]
        routes = self.routes(table, family)
        if argv[:4] == ["ip", "-j", "route", "show"]:
            return json.dumps(routes)
        verb, body = body[0], body[1:]
        metric = int(body[body.index("metric") + 1]) if "metric" in body else 0
        if body[0] == "throw":
            route = {"type": "throw", "dst": body[1]}
            if verb == "del":
                if route not in routes:
                    raise CommandError(f"{command}: RTNETLINK answers: No such process")
                routes.remove(route)
            elif route not in routes:
                routes.append(route)
            return ""
        if body[0] == "local":
            assert ("::/0" if family == 6 else "0.0.0.0/0") in body, f"не то семейство: {command}"
            route = {"type": "local", "dst": "default", "dev": "lo", "scope": "host"}
        elif body[0] == "blackhole":
            route = {"type": "blackhole", "dst": "default", "metric": metric}
        else:
            dev = body[body.index("dev") + 1]
            if verb == "replace" and dev not in self.links:
                raise CommandError(f'{command}: Cannot find device "{dev}"')
            route = {"dst": "default", "dev": dev, "scope": "link"}
        if verb == "del":
            same = [
                r for r in routes
                if r.get("type") == route.get("type") and r.get("dev") == route.get("dev")
                and r.get("metric", 0) == metric
            ]
            if not same:
                raise CommandError(f"{command}: RTNETLINK answers: No such process")
            routes.remove(same[0])
            return ""
        # replace: ключ маршрута в таблице — приемник (везде default) и метрика, а тип в ключ
        # не входит; поэтому local-маршрут и маршрут в TUN с метрикой 0 заменяют друг друга.
        routes[:] = [
            r for r in routes if r.get("metric", 0) != metric or r.get("type") == "throw"
        ]
        routes.append(route)
        return ""

    def _rule(self, argv: list[str], command: str, family: int) -> str:
        """ip rule add/del fwmark M [iif lo] lookup T [pref P]."""
        rules = self.rules6 if family == 6 else self.rules
        words = argv[3:]
        mark = hex(int(words[words.index("fwmark") + 1]))
        table = words[words.index("lookup") + 1]
        iif = words[words.index("iif") + 1] if "iif" in words else None
        if argv[2] == "add":
            rule = {"priority": int(words[words.index("pref") + 1]), "src": "all",
                    "fwmark": mark, "table": table}
            if iif is not None:
                rule["iif"] = iif
            rules.append(rule)
            return ""
        for rule in rules:
            if rule["fwmark"] == mark and rule["table"] == table and rule.get("iif") == iif:
                rules.remove(rule)
                return ""
        raise CommandError(f"{command}: RTNETLINK answers: No such file or directory")

    def _route_get(self, argv: list[str], command: str) -> str:
        """ip -j route get АДРЕС from ИСТОЧНИК iif LAN mark M: local (в TPROXY), если
        проверка источника не мешает."""
        words = argv[4:]
        source = words[words.index("from") + 1]
        iif = words[words.index("iif") + 1]
        if iif not in self.lan_links:
            raise CommandError(f'{command}: Cannot find device "{iif}"')
        throws = [
            route["dst"] for routes in self.route_tables.values() for route in routes
            if route.get("type") == "throw"
        ]
        covered = any(
            ipaddress.ip_address(source) in ipaddress.ip_network(net) for net in throws
        )
        if not self.lan_links[iif] or (self.src_valid_mark and not covered):
            raise CommandError(f"{command}: RTNETLINK answers: Invalid argument")
        return json.dumps([{"type": "local", "dst": words[0], "dev": "lo", "table": "100"}])

    def _ip(self, argv: list[str], command: str, family: int) -> str:
        rules = self.rules6 if family == 6 else self.rules
        if argv[:4] == ["ip", "-j", "route", "get"]:
            return self._route_get(argv, command)
        if argv[:5] == ["ip", "-j", "link", "show", "dev"]:
            name = argv[5]
            if name not in self.lan_links:
                raise CommandError(f'{command}: Device "{name}" does not exist.')
            flags = ["BROADCAST", "MULTICAST", *(["UP"] if self.lan_links[name] else [])]
            return json.dumps([{"ifname": name, "flags": flags}])
        if argv[:3] == ["ip", "-j", "rule"]:
            system = [{"priority": 0, "src": "all", "table": "local"},
                      {"priority": 32766, "src": "all", "table": "main"}]
            return json.dumps([system[0], *sorted(rules, key=lambda r: r["priority"]), system[1]])
        if argv[:3] in (["ip", "rule", "add"], ["ip", "rule", "del"]):
            return self._rule(argv, command, family)
        if argv[:4] == ["ip", "-j", "route", "show"] or (
            argv[:2] == ["ip", "route"] and argv[2] in ("replace", "del")
        ):
            return self._route(argv, command, family)
        if argv[:2] in (["ip", "tuntap"], ["ip", "link"]) or argv[:3] == [
            "ip", "addr", "replace"
        ] or argv[:5] == ["ip", "-d", "-j", "link", "show"] or argv[:4] == [
            "ip", "-j", "addr", "show"
        ]:
            return self._link(argv, command)
        raise AssertionError(f"неожиданная команда: {command}")

    def _nft(self, argv: list[str], text: str) -> str:
        if self.forbidden:
            raise CommandError("nft: Operation not permitted (you must be root)")
        terse = argv[1:2] == ["-t"]  # как nft -t: без элементов именованных наборов
        if terse:
            argv = [argv[0], *argv[2:]]
        if argv[1:3] in (["list", "table"], ["list", "set"]):
            key = (argv[3], argv[4])
            if key not in self.tables:
                raise CommandError(
                    f"{' '.join(argv)}: Error: No such file or directory\n"
                    f"list table {argv[3]} {argv[4]}"
                )
            # Как настоящий nft: отказ по умолчанию для семейства печатается одним «reject».
            body = re.sub(
                r"reject with icmp(?:v6)? type port-unreachable", "reject", self.tables[key]
            )
            if argv[2] == "set":
                found = re.search(
                    rf"^\s*set {re.escape(argv[5])} \{{\n.*?^\s*\}}\n", body,
                    flags=re.MULTILINE | re.DOTALL,
                )
                if found is None:
                    raise CommandError(f"{' '.join(argv)}: Error: No such file or directory")
                return f"table {argv[3]} {argv[4]} {{\n{found.group(0)}}}\n"
            if terse:
                body = re.sub(r"^\s*elements = \{.*?\}\n", "", body,
                              flags=re.MULTILINE | re.DOTALL)
            return body
        if argv[1:] == ["-c", "-f", "-"]:
            return ""
        if argv[1:] == ["-f", "-"] and text.startswith(("add element ", "flush set ")):
            return self._elements(text)
        if argv[1:] == ["-f", "-"]:
            # Одна транзакция может заменять несколько таблиц («table X / delete table X /
            # table X {…}» подряд); отказ любой из них — отказ всей транзакции.
            segments: list[list[str]] = []
            for line in text.splitlines():
                if line.startswith("table ") and "{" not in line:
                    segments.append([line])
                elif segments:
                    segments[-1].append(line)
            if self.refuse_ip6 and any(seg[0].startswith("table ip6 ") for seg in segments):
                raise CommandError("nft: Operation not supported")
            self.loads.append(text)
            for segment in segments:
                _table, family, name = segment[0].split()
                body = "\n".join(segment) + "\n"
                if "{" in body:
                    self.tables[(family, name)] = body
                else:
                    self.tables.pop((family, name), None)
            return ""
        raise AssertionError(f"неожиданная команда: {' '.join(argv)}")

    def _elements(self, text: str) -> str:
        """`add element СЕМЕЙСТВО ТАБЛИЦА НАБОР { X }` и `flush set СЕМЕЙСТВО ТАБЛИЦА НАБОР`
        одной транзакцией: нет таблицы или набора — отказ всей транзакции."""
        tables = dict(self.tables)
        for line in text.splitlines():
            words = line.split()
            if not words:
                continue
            verb, (family, name, set_name) = " ".join(words[:2]), words[2:5]
            body = tables.get((family, name), "")
            head = f"    set {set_name} {{\n"
            if head not in body:
                raise CommandError(f"nft: Error: No such file or directory: {line}")
            start = body.index(head) + len(head)
            end = body.index("    }\n", start)
            lines = [item for item in body[start:end].splitlines(keepends=True)
                     if "elements" not in item]
            if verb == "add element":
                lines.append(f"        elements = {line[line.index('{'):]}\n")
            tables[(family, name)] = body[:start] + "".join(lines) + body[end:]
        self.loads.append(text)
        self.tables = tables
        return ""

    # --- удобства для проверок ---

    def commands(self, *prefix: str) -> list[tuple[str, ...]]:
        return [call for call in self.calls if call[: len(prefix)] == prefix]

    def index(self, *prefix: str) -> int:
        """Номер первого вызова с таким началом; -1 — не было."""
        for number, call in enumerate(self.calls):
            if call[: len(prefix)] == prefix:
                return number
        return -1

    @property
    def table(self) -> str:
        return self.tables.get(("ip", "xgw"), "")

    @property
    def table6(self) -> str:
        return self.tables.get(("ip6", "xgw6"), "")
