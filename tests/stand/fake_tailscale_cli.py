"""CLI `tailscale` для стенда — без tailscaled: состояние узла в файле XGW_FAKE_TAILSCALE
(JSON). Умеет то, что вызывает карточка «Tailscale» панели: `status --json`, `debug prefs`,
`serve status --json`, `serve --bg --https=8443 URL`, `serve --https=8443 off`, `set …`,
`funnel --bg --https=443 URL`, `funnel --https=443 off`.
Каждый вызов дописывается в поле "calls".
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    path = Path(os.environ["XGW_FAKE_TAILSCALE"])
    state = json.loads(path.read_text(encoding="utf-8"))
    args = sys.argv[1:]
    state.setdefault("calls", []).append(args)
    name = state.get("name", "gw.example.ts.net")
    code = 0
    if args == ["status", "--json"]:
        print(json.dumps({
            "BackendState": "Running", "AuthURL": "",
            "Self": {"DNSName": name + ".", "TailscaleIPs": ["100.64.0.1"]},
            "CurrentTailnet": {"MagicDNSEnabled": True},
        }))
    elif args == ["debug", "prefs"]:
        print(json.dumps({"RunSSH": state.get("ssh", False), "NetfilterMode": 2,
                          "CorpDNS": True}))
    elif args == ["serve", "status", "--json"]:
        web, allow = {}, {}
        for port, key in (("8443", "serve"), ("443", "funnel")):
            if state.get(key):
                web[f"{name}:{port}"] = {"Handlers": {"/": {"Proxy": state[key]}}}
        if state.get("funnel"):
            allow[f"{name}:443"] = True
        print(json.dumps({"Web": web, "AllowFunnel": allow} if web else {}))
    elif args[:3] == ["serve", "--bg", "--https=8443"] and len(args) == 4:
        state["serve"] = args[3]
        print(f"Available within your tailnet:\n\nhttps://{name}:8443/\n|-- proxy {args[3]}")
    elif args == ["serve", "--https=8443", "off"]:
        state["serve"] = ""
    elif args[:3] == ["funnel", "--bg", "--https=443"] and len(args) == 4:
        state["funnel"] = args[3]
        print(f"Available on the internet:\n\nhttps://{name}/\n|-- proxy {args[3]}")
    elif args == ["funnel", "--https=443", "off"]:
        state["funnel"] = ""
    elif args[:1] == ["set"]:
        for flag in args[1:]:
            if flag in ("--ssh", "--ssh=false"):
                state["ssh"] = flag == "--ssh"
    else:
        print(f"unknown command: {' '.join(args)}", file=sys.stderr)
        code = 2
    path.write_text(json.dumps(state), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
