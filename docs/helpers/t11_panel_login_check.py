"""Check management-panel authentication on the gateway without printing credentials."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit


class FailedCheck(ValueError):
    pass


def require(ok: bool, name: str) -> None:
    if not ok:
        raise FailedCheck(name)


def request(port: int, path: str, *, method: str = "GET", cookie: str = "",
            headers: dict[str, str] | None = None) -> tuple[int, dict[str, str]]:
    headers = dict(headers or {})
    if cookie:
        headers["Cookie"] = cookie
    body = None
    if method == "POST":
        headers.update({"Content-Type": "application/json", "X-XGW-Panel": "1"})
        body = "{}"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, {name.lower(): value for name, value in response.getheaders()}
    finally:
        connection.close()


def login_link(port: int, token: str) -> str:
    cli = subprocess.run(
        ["/usr/local/bin/xgw", "panel"],
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}, capture_output=True, text=True, timeout=12,
    )
    require(cli.returncode == 0 and bool(cli.stdout.splitlines()), "cli")
    require(token not in (cli.stdout + cli.stderr), "cli_permanent_secret")
    prefix = "Панель XGW: "
    first = cli.stdout.splitlines()[0]
    require(first.startswith(prefix), "cli_output")
    url = urlsplit(first.removeprefix(prefix))
    query = parse_qs(url.query, keep_blank_values=True)
    require(url.scheme == "http" and url.netloc == f"127.0.0.1:{port}" and url.path == "/"
            and not url.fragment and set(query) == {"login"} and len(query["login"]) == 1
            and len(query["login"][0]) == 32, "cli_url")
    return "/?" + urlencode(query, doseq=True)


def verify(port: int, token: str, phase: str) -> dict:
    api = "/api/state"
    cookie = "xgw_panel=" + hmac.new(token.encode(), b"xgw-panel", hashlib.sha256).hexdigest()
    require(request(port, api)[0] == 401, "guest_api")
    require(request(port, api, cookie=cookie)[0] == 200, "existing_session")
    legacy = "/?" + urlencode({"token": token})
    code, headers = request(port, legacy)
    require(code == 303 and headers.get("location") == "/", "legacy_redirect")
    if phase != "candidate":
        require(headers.get("set-cookie", "").split(";", 1)[0] == cookie, "legacy_baseline")
        return {"ok": True, "phase": phase, "existing_session": True, "legacy_login": True}

    require("set-cookie" not in headers and headers.get("referrer-policy") == "no-referrer",
            "legacy_issued_session")
    require(request(port, legacy, cookie=cookie)[0] == 303, "legacy_session_redirect")
    require(request(port, api, cookie=cookie)[0] == 200, "legacy_session_retained")
    fresh_link = login_link(port, token)
    require(request(port, fresh_link, headers={"Host": "unrelated.invalid"})[0] == 403,
            "foreign_host")
    code, headers = request(port, fresh_link, method="HEAD")
    require(code == 200 and "set-cookie" not in headers, "head_consumed_code")
    code, headers = request(port, fresh_link)
    issued = headers.get("set-cookie", "")
    require(code == 303 and headers.get("location") == "/" and issued.split(";", 1)[0] == cookie
            and "HttpOnly" in issued and "SameSite=Strict" in issued, "new_session")
    code, headers = request(port, fresh_link)
    require(code == 403 and "set-cookie" not in headers, "reused_code")
    # No action has this name, even if an authentication check is accidentally dropped.
    inert = "/api/__t11_login_check__"
    require(request(port, inert, method="POST")[0] == 401, "unauthorized_post")
    require(request(port, inert, method="POST", cookie=cookie,
                    headers={"Origin": "http://unrelated.invalid"})[0] == 403, "foreign_origin")
    return {"ok": True, "phase": phase, "existing_session": True, "legacy_login": False,
            "one_time_cli": True, "reused_code": 403, "foreign_host": 403, "foreign_origin": 403}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("baseline", "candidate", "restored"))
    args = parser.parse_args()
    # The caller launches the archived checker with isolated Python as root.
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config
    from xgw.paths import Paths
    from xgw.watch.panel import read_token

    try:
        paths = Paths(Path("/"))
        cfg, _warnings = config.load(paths.config_file)
        token = read_token(paths)
        require(bool(token), "missing_signing_key")
        result = verify(cfg.panel.port, token, args.phase)
    except FailedCheck as exc:
        result = {"ok": False, "phase": args.phase, "failed": str(exc)}
    except (OSError, http.client.HTTPException, subprocess.SubprocessError, ValueError,
            config.ConfigError):
        result = {"ok": False, "phase": args.phase, "failed": "request_or_config"}
    print(json.dumps(result))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
