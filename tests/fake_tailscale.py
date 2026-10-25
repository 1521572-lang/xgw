"""CLI `tailscale` для панели — в памяти: что печатают `status --json`, `debug prefs`,
`serve status --json`, что делают `set`, `serve … off`, `funnel … off`, и фоновые `login`,
`serve --bg`, `funnel --bg`.

Вывод — как у настоящего 1.104.1 (снимок Т0): лишние поля есть, нужные — в тех же местах.
"""

from __future__ import annotations

import json
from pathlib import Path

AUTH_URL = "https://login.tailscale.com/a/1a2b3c4d5e6f7"
ENABLE_URL = "https://login.tailscale.com/f/serve?node=nFake123CNTRL"
FUNNEL_URL = "https://login.tailscale.com/f/funnel?node=nFake123CNTRL"


class FakeProc:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15


class FakeTailscale:
    def __init__(self, *, backend: str = "Running", name: str = "gw.tailnet-1.ts.net") -> None:
        self.backend = backend
        self.name = name
        self.addresses = ["100.101.1.1", "fd7a:115c:a1e0::1"]
        self.ssh = False
        self.netfilter = 2
        self.accept_dns = True
        self.override_dns = False
        self.cgnat_wan = False  # провайдер выдаёт адрес из 100.64.0.0/10 (К5)
        self.https_enabled = True  # в tailnet включены сертификаты HTTPS (для Serve)
        self.serve: str = ""  # куда Serve ведёт порт 8443
        self.funnel: str = ""  # куда Funnel ведёт порт 443 (из интернета)
        self.funnel_allowed = True  # в правилах tailnet есть атрибут funnel
        self.exit_node = False  # --advertise-exit-node
        self.exit_approved = False  # одобрен в консоли tailnet (AllowedIPs с 0.0.0.0/0)
        self.peers: list[dict] = []  # Peer: HostName, TailscaleIPs, OS, Online
        self.fail: dict[str, str] = {}  # команда («set», «serve») → текст ошибки
        self.calls: list[tuple[str, ...]] = []
        self.auth_url = ""
        self._login: FakeProc | None = None
        self._serving: tuple[FakeProc, str, Path] | None = None
        self._funneling: tuple[FakeProc, str] | None = None

    # --- runner ---------------------------------------------------------------------

    def __call__(self, argv, *, input=None, timeout=15.0, check=True) -> str:
        argv = list(argv)
        self.calls.append(tuple(argv))
        head = argv[0]
        if head == "tailscale":
            return self._cli(argv[1:])
        if head == "resolvectl" and argv[1:] == ["status", "tailscale0"]:
            return "Link 9 (tailscale0)\n    Protocols: " + (
                "+DefaultRoute" if self.override_dns else "-DefaultRoute") + " +LLMNR\n"
        if head == "resolvectl" and argv[1] == "dns":
            return f"Link 2 ({argv[2]}): " + ("100.64.0.53" if self.cgnat_wan else "192.0.2.53")
        if argv[:5] == ["ip", "-j", "route", "show", "default"]:
            return json.dumps([{"dst": "default", "gateway": "192.0.2.1", "dev": "wan0"}])
        if argv[:5] == ["ip", "-j", "-4", "addr", "show"]:
            local = "100.70.1.2" if self.cgnat_wan else "192.0.2.10"
            return json.dumps([{"ifname": "wan0", "addr_info": [
                {"family": "inet", "local": local, "prefixlen": 24}]}])
        if argv[:5] == ["ip", "-j", "-4", "route", "show"]:
            return "[]"
        return ""

    def _cli(self, args: list[str]) -> str:
        from xgw.net.cmd import CommandError

        if args == ["status", "--json"]:
            return json.dumps({
                "Version": "1.104.1-t0a1b2c3d", "TUN": True, "BackendState": self.backend,
                "HaveNodeKey": True, "AuthURL": self.auth_url if self.backend != "Running" else "",
                "TailscaleIPs": self.addresses if self.backend == "Running" else None,
                "Self": {
                    "ID": "nFake123CNTRL", "HostName": self.name.split(".")[0],
                    "DNSName": self.name + "." if self.backend == "Running" else "",
                    "OS": "linux", "TailscaleIPs": self.addresses if self.backend == "Running"
                    else None, "Online": self.backend == "Running",
                    "AllowedIPs": [f"{ip}/32" if ":" not in ip else f"{ip}/128"
                                   for ip in self.addresses]
                    + (["0.0.0.0/0", "::/0"] if self.exit_node and self.exit_approved else []),
                },
                "MagicDNSSuffix": "tailnet-1.ts.net",
                "CurrentTailnet": {"Name": "user@example.com", "MagicDNSSuffix":
                                   "tailnet-1.ts.net", "MagicDNSEnabled": True},
                "Peer": {f"nodekey:{index}": {"ID": f"n{index}", "ExitNodeOption": False,
                                              **peer} for index, peer in enumerate(self.peers)},
                "User": {}, "ClientVersion": None,
            })
        if args == ["debug", "prefs"]:
            return json.dumps({
                "ControlURL": "https://controlplane.tailscale.com", "RouteAll": False,
                "ExitNodeID": "", "CorpDNS": self.accept_dns, "RunSSH": self.ssh,
                "WantRunning": True, "LoggedOut": self.backend != "Running",
                "ShieldsUp": False, "NetfilterMode": self.netfilter, "AutoUpdate": {},
                "AdvertiseRoutes": ["0.0.0.0/0", "::/0"] if self.exit_node else None,
            }, indent=2)
        if args == ["serve", "status", "--json"]:
            if not self.serve and not self.funnel:
                return "{}\n"
            tcp, web, allow = {}, {}, {}
            for port, target in (("8443", self.serve), ("443", self.funnel)):
                if target:
                    tcp[port] = {"HTTPS": True}
                    web[f"{self.name}:{port}"] = {"Handlers": {"/": {"Proxy": target}}}
            if self.funnel:
                allow[f"{self.name}:443"] = True
            return json.dumps({"TCP": tcp, "Web": web, **({"AllowFunnel": allow} if allow
                                                           else {})}, indent=2)
        command = " ".join(["tailscale", *args])
        if args[:1] == ["set"]:
            if "set" in self.fail:
                raise CommandError(f"{command}: {self.fail['set']}")
            for flag in args[1:]:
                if flag == "--ssh":
                    self.ssh = True
                elif flag == "--ssh=false":
                    self.ssh = False
                elif flag == "--netfilter-mode=off":
                    self.netfilter = 0
                elif flag == "--accept-dns=false":
                    self.accept_dns = False
                    self.override_dns = False
                elif flag in ("--advertise-exit-node=true", "--advertise-exit-node=false"):
                    self.exit_node = flag.endswith("true")
                else:
                    raise CommandError(f"{command}: flag provided but not defined: {flag}")
            return ""
        if args == ["funnel", "--https=443", "off"]:
            if "funnel" in self.fail:
                raise CommandError(f"{command}: {self.fail['funnel']}")
            self.funnel = ""
            return ""
        if args == ["serve", "--https=8443", "off"]:
            if "serve" in self.fail:
                raise CommandError(f"{command}: {self.fail['serve']}")
            self.serve = ""
            return ""
        raise CommandError(f"{command}: неожиданная команда")

    # --- фоновые команды ----------------------------------------------------------

    def spawn(self, argv, output: Path):
        self.calls.append(tuple(argv))
        output.parent.mkdir(parents=True, exist_ok=True)
        proc = FakeProc()
        if argv[:2] == ["tailscale", "login"]:
            self.backend = "NeedsLogin"
            self.auth_url = AUTH_URL
            output.write_text(f"\nTo authenticate, visit:\n\n\t{AUTH_URL}\n\n", encoding="utf-8")
            self._login = proc
        elif argv[:3] == ["tailscale", "serve", "--bg"]:
            if "serve" in self.fail:
                output.write_text(self.fail["serve"] + "\n", encoding="utf-8")
                proc.returncode = 1
            elif self.https_enabled:
                self.serve = argv[-1]
                output.write_text(
                    f"Available within your tailnet:\n\nhttps://{self.name}:8443/\n"
                    f"|-- proxy {argv[-1]}\n\nServe started and running in the background.\n",
                    encoding="utf-8")
                proc.returncode = 0
            else:
                output.write_text(
                    "\nServe is not enabled on your tailnet.\nTo enable, visit:\n\n"
                    f"         {ENABLE_URL}\n", encoding="utf-8")
                self._serving = (proc, argv[-1], output)
        elif argv[:3] == ["tailscale", "funnel", "--bg"]:
            if "funnel" in self.fail:
                output.write_text(self.fail["funnel"] + "\n", encoding="utf-8")
                proc.returncode = 1
            elif self.funnel_allowed:
                self.funnel = argv[-1]
                output.write_text(
                    f"Available on the internet:\n\nhttps://{self.name}/\n"
                    f"|-- proxy {argv[-1]}\n\nFunnel started and running in the background.\n",
                    encoding="utf-8")
                proc.returncode = 0
            else:
                output.write_text(
                    "\nFunnel is not enabled on your tailnet.\nTo enable, visit:\n\n"
                    f"         {FUNNEL_URL}\n", encoding="utf-8")
                self._funneling = (proc, argv[-1])
        else:
            raise AssertionError(f"неожиданная фоновая команда: {argv}")
        return proc

    def allow_funnel(self) -> None:
        """В консоли tailnet разрешили Funnel: ждавший `funnel --bg` доделал своё."""
        self.funnel_allowed = True
        if self._funneling is not None:
            proc, target = self._funneling
            self.funnel, proc.returncode, self._funneling = target, 0, None

    def complete_login(self) -> None:
        """Человек вошёл по ссылке: узел в tailnet, `tailscale login` вышел."""
        self.backend, self.auth_url = "Running", ""
        if self._login is not None:
            self._login.returncode = 0

    def enable_https(self) -> None:
        """В консоли tailnet включили HTTPS: ждавший `serve --bg` доделал своё."""
        self.https_enabled = True
        if self._serving is not None:
            proc, target, _output = self._serving
            self.serve, proc.returncode, self._serving = target, 0, None
