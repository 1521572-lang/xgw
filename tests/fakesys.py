"""Подмена системы для тестов установки: nmcli, systemctl, ufw, apt, useradd и
прочее, чем пользуются `xgw install`, `xgw uninstall` и `xgw diag`.

Хранит состояние (профили NetworkManager, службы, пакеты, пользователей,
правила ufw), так что по нему видно, что установка сделала и вернуло ли
удаление всё на место. Команды nft и ip уходят в FakeKernel.
"""

from __future__ import annotations

import itertools
import json

from fakenet import FakeKernel

from xgw.net.cmd import CommandError


def terse(*fields: str) -> str:
    """Строка `nmcli -t`: двоеточие и обратная косая черта в значении экранируются."""
    return ":".join(field.replace("\\", "\\\\").replace(":", "\\:") for field in fields)


class FakeSystem:
    def __init__(self) -> None:
        self.kernel = FakeKernel()
        self.calls: list[tuple[str, ...]] = []
        self.refuse: dict[str, str] = {}  # подстрока команды → текст ошибки
        self.nm_running = True
        self.devices: dict[str, dict] = {
            "wan0": {"type": "ethernet", "state": "connected"},
            "lan0": {"type": "ethernet", "state": "connected"},
        }
        self.profiles: dict[str, dict] = {}
        self._uuid = itertools.count(1)
        self.units: dict[str, dict] = {}
        self.packages: set[str] = {"nftables"}
        self.users: set[str] = set()
        self.ufw_active = False
        self.ufw_rules: list[tuple[str, ...]] = []
        self.ufw_reloads = 0
        self.default_dev = "wan0"
        # Адреса IPv4 интерфейсов («адрес/префикс») — для проверки пересечения подсетей.
        self.addresses: dict[str, list[str]] = {"wan0": ["203.0.113.5/24"]}
        self.gateway = "203.0.113.1"
        self.ipv6_global: list[str] = []  # интерфейсы с глобальным IPv6-адресом
        self.nft_chains: list[dict] = []  # чужие цепочки для `nft -j list ruleset`
        self.time_synced = True
        self.sessions: list[dict] = []  # loginctl list-sessions
        self.session_props: dict[str, str] = {}
        self.add_profile("wan", "wan0", active=True, **{"ipv6.method": "auto"})

    # --- состояние ------------------------------------------------------------

    def add_profile(self, name: str, ifname: str, *, active: bool = False, **settings) -> str:
        uuid = f"00000000-0000-4000-8000-{next(self._uuid):012d}"
        self.profiles[uuid] = {
            "connection.id": name, "connection.interface-name": ifname,
            "connection.autoconnect": "yes", "ipv4.method": "auto", "ipv6.method": "auto",
            "type": "802-3-ethernet", "device": ifname if active else "", **settings,
        }
        return uuid

    def uuid_of(self, name: str) -> str:
        return next(uuid for uuid, item in self.profiles.items() if item["connection.id"] == name)

    def profile(self, name: str) -> dict:
        return self.profiles[self.uuid_of(name)]

    def unit(self, name: str) -> dict:
        return self.units.setdefault(name, {"active": False, "enabled": False})

    # --- вызовы ---------------------------------------------------------------

    def __call__(self, argv, *, input=None, timeout=15.0, check=True) -> str:
        argv = list(argv)
        self.calls.append(tuple(argv))
        command = " ".join(argv)
        for needle, error in self.refuse.items():
            if needle in command:
                if not check:
                    return ""
                raise CommandError(f"{command}: {error}")
        if argv[0] == "env":
            argv = [item for item in argv[1:] if "=" not in item]
        handler = getattr(self, "_" + argv[0].replace("-", "_").rsplit("/", 1)[-1], None)
        if argv[0] in ("nft", "ip") and argv[:5] != ["ip", "-j", "route", "show", "default"] \
                and argv[:3] not in (["ip", "-j", "-6"], ["ip", "-j", "-4"]) \
                and argv[:2] != ["nft", "-j"]:
            return self.kernel(argv, input=input, timeout=timeout)
        if handler is None:
            return ""  # python -m compileall, sysctl и прочее без последствий
        return handler(argv[1:], command, check)

    def commands(self, *prefix: str) -> list[tuple[str, ...]]:
        return [call for call in self.calls if call[: len(prefix)] == prefix]

    def _ip(self, args, command, check) -> str:
        if args[:2] == ["-j", "-6"]:
            return json.dumps([
                {"ifname": name, "addr_info": [{"local": "2001:db8::1"}]}
                for name in self.ipv6_global
            ])
        if args[:3] == ["-j", "-4", "addr"]:
            return json.dumps([
                {"ifname": name, "addr_info": [
                    {"family": "inet", "local": item.split("/")[0],
                     "prefixlen": int(item.split("/")[1])}
                    for item in items
                ]}
                for name, items in self.addresses.items()
            ])
        default = [] if not self.default_dev else [
            {"dst": "default", "gateway": self.gateway, "dev": self.default_dev}
        ]
        if args[:3] == ["-j", "-4", "route"]:
            import ipaddress

            connected = [
                {"dst": str(ipaddress.IPv4Interface(item).network), "dev": name,
                 "protocol": "kernel", "scope": "link"}
                for name, items in self.addresses.items() for item in items
            ]
            return json.dumps([*default, *connected])
        return json.dumps(default)

    def _nft(self, args, command, check) -> str:
        return json.dumps({"nftables": [{"chain": chain} for chain in self.nft_chains]})

    def _unshare(self, args, command, check) -> str:
        return ""

    def _nmcli(self, args, command, check) -> str:
        if not self.nm_running:
            raise CommandError(f"{command}: NetworkManager is not running")
        if args == ["-t", "-f", "RUNNING", "general"]:
            return "running\n"
        if args[:3] == ["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION"]:
            lines = []
            for name, device in self.devices.items():
                active = next((item["connection.id"] for item in self.profiles.values()
                               if item["device"] == name), "")
                lines.append(terse(name, device["type"], device["state"], active))
            return "\n".join(lines) + "\n"
        if args[:5] == ["-t", "-f", "NAME,UUID,TYPE,DEVICE,FILENAME", "connection", "show"]:
            return "".join(
                terse(item["connection.id"], uuid, item["type"], item["device"],
                      f"/run/NetworkManager/system-connections/{uuid}.nmconnection") + "\n"
                for uuid, item in self.profiles.items()
            )
        if args[:2] == ["-t", "-f"] and args[3:5] == ["connection", "show"]:
            item = self._profile(args[5], command)
            return "".join(f"{field}:{terse(item.get(field, ''))}\n"
                           for field in args[2].split(","))
        if args[:2] == ["-g", "GENERAL.CON-UUID"]:
            return next((uuid for uuid, item in self.profiles.items()
                         if item["device"] == args[4]), "") + "\n"
        if args[:2] == ["connection", "modify"]:
            item = self._profile(args[2], command)
            item.update(zip(args[3::2], args[4::2], strict=True))
            return ""
        if args[:2] == ["connection", "add"]:
            options = dict(zip(args[2::2], args[3::2], strict=True))
            self.add_profile(options.pop("con-name"), options.pop("ifname"),
                             **{key: value for key, value in options.items() if "." in key})
            return "Connection successfully added.\n"
        if args[:1] == ["--wait"] and args[2:4] == ["connection", "up"]:
            item = self._profile(args[4], command)
            device = args[6] if len(args) > 6 else item["connection.interface-name"]
            for other in self.profiles.values():
                if other["device"] == device:
                    other["device"] = ""
            item["device"] = device
            return ""
        if args[:2] == ["connection", "delete"]:
            self._profile(args[2], command)
            del self.profiles[args[2]]
            return ""
        if args[:2] == ["device", "reapply"]:
            return ""
        raise AssertionError(f"неожиданная команда: {command}")

    def _profile(self, uuid: str, command: str) -> dict:
        if uuid not in self.profiles:
            raise CommandError(f"{command}: Error: {uuid} - no such connection profile.")
        return self.profiles[uuid]

    def _systemctl(self, args, command, check) -> str:
        verb, rest = args[0], [item for item in args[1:] if not item.startswith("-")]
        if verb == "is-active":
            return "\n".join("active" if self.unit(name)["active"] else "inactive"
                             for name in rest) + "\n"
        if verb == "is-enabled":
            return "\n".join("enabled" if self.unit(name)["enabled"] else "disabled"
                             for name in rest) + "\n"
        for name in rest:
            unit = self.unit(name)
            if verb in ("start", "restart"):
                unit["active"] = True
            elif verb == "stop":
                unit["active"] = False
            elif verb == "enable":
                unit["enabled"] = True
                unit["active"] = unit["active"] or "--now" in args
            elif verb == "disable":
                unit["enabled"] = False
                unit["active"] = unit["active"] and "--now" not in args
        return ""

    def _dpkg_query(self, args, command, check) -> str:
        return "install ok installed" if args[-1] in self.packages else ""

    def _apt_get(self, args, command, check) -> str:
        if args[0] == "install":
            self.packages.update(item for item in args[1:] if not item.startswith("-"))
        return ""

    def _getent(self, args, command, check) -> str:
        name = args[1]
        return f"{name}:x:997:986::/nonexistent:/usr/sbin/nologin\n" if name in self.users else ""

    def _useradd(self, args, command, check) -> str:
        self.users.add(args[-1])
        return ""

    def _userdel(self, args, command, check) -> str:
        self.users.discard(args[-1])
        return ""

    def _ufw(self, args, command, check) -> str:
        if args == ["status"]:
            if not self.ufw_active:
                return "Status: inactive\n"
            return "Status: active\n\n" + "".join(
                f"Anywhere on {rule[rule.index('on') + 1]}  ALLOW  Anywhere\n"
                for rule in self.ufw_rules
            )
        if args == ["reload"]:
            self.ufw_reloads += 1
            return "Firewall reloaded\n"
        if "delete" in args:
            rule = tuple(item for item in args if item != "delete")
            if rule not in self.ufw_rules:
                raise CommandError(f"{command}: Could not delete non-existent rule")
            self.ufw_rules.remove(rule)
            return "Rule deleted\n"
        if tuple(args) in self.ufw_rules:
            return "Skipping adding existing rule\n"
        self.ufw_rules.append(tuple(args))
        return "Rule added\n"

    def _timedatectl(self, args, command, check) -> str:
        return "yes\n" if self.time_synced else "no\n"

    def _loginctl(self, args, command, check) -> str:
        if args[0] == "list-sessions":
            return json.dumps(self.sessions)
        return "".join(f"{key}={value}\n" for key, value in self.session_props.items())
