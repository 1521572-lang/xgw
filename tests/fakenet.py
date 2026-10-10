"""Подмена ядра для тестов сети: понимает те команды nft и ip, которыми пользуется XGW.

Хранит «загруженные» таблицы nftables, правила `ip rule` и маршрут таблицы
перехвата; все вызовы записывает в calls — по ним тесты проверяют порядок.
"""

from __future__ import annotations

import json

from xgw.net.cmd import CommandError


class FakeKernel:
    def __init__(self) -> None:
        self.tables: dict[tuple[str, str], str] = {}
        self.rules: list[dict] = []
        self.route = False
        self.calls: list[tuple[str, ...]] = []
        self.refuse: str | None = None  # подстрока команды, которая «не выполняется»
        self.forbidden = False  # запуск не от root: nft ничего не показывает

    def __call__(self, argv, *, input=None, timeout=15.0) -> str:
        argv = list(argv)
        self.calls.append(tuple(argv))
        command = " ".join(argv)
        if self.refuse and self.refuse in command:
            raise CommandError(f"{command}: отказано")
        if argv[0] == "nft":
            return self._nft(argv, input or "")
        if argv[:3] == ["ip", "-j", "rule"]:
            system = [{"priority": 0, "src": "all", "table": "local"},
                      {"priority": 32766, "src": "all", "table": "main"}]
            return json.dumps([system[0], *self.rules, system[1]])
        if argv[:3] == ["ip", "rule", "add"]:
            self.rules.append(
                {"priority": int(argv[8]), "src": "all",
                 "fwmark": hex(int(argv[4])), "table": argv[6]}
            )
            return ""
        if argv[:3] == ["ip", "rule", "del"]:
            for rule in self.rules:
                if rule["fwmark"] == hex(int(argv[4])) and rule["table"] == argv[6]:
                    self.rules.remove(rule)
                    return ""
            raise CommandError(f"{command}: RTNETLINK answers: No such file or directory")
        if argv[:4] == ["ip", "-j", "route", "show"]:
            if not self.route:
                return "[]"
            return json.dumps([{"type": "local", "dst": "default", "dev": "lo", "scope": "host"}])
        if argv[:3] == ["ip", "route", "replace"]:
            self.route = True
            return ""
        if argv[:3] == ["ip", "route", "del"]:
            self.route = False
            return ""
        raise AssertionError(f"неожиданная команда: {command}")

    def _nft(self, argv: list[str], text: str) -> str:
        if self.forbidden:
            raise CommandError("nft: Operation not permitted (you must be root)")
        if argv[1:3] == ["list", "table"]:
            key = (argv[3], argv[4])
            if key not in self.tables:
                raise CommandError(
                    f"{' '.join(argv)}: Error: No such file or directory\n"
                    f"list table {argv[3]} {argv[4]}"
                )
            return self.tables[key]
        if argv[1:] == ["-c", "-f", "-"]:
            return ""
        if argv[1:] == ["-f", "-"]:
            _table, family, name = text.splitlines()[0].split()
            if "{" in text:
                self.tables[(family, name)] = text
            else:
                self.tables.pop((family, name), None)
            return ""
        raise AssertionError(f"неожиданная команда: {' '.join(argv)}")

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
