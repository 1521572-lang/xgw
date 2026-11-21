"""Check management-panel authentication on the gateway without printing credentials."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit


class FailedCheck(ValueError):
    def __init__(self, name: str, **details) -> None:
        super().__init__(name)
        self.details = details


def require(ok: bool, name: str) -> None:
    if not ok:
        raise FailedCheck(name)


def request(port: int, path: str, *, method: str = "GET", cookie: str = "",
            headers: dict[str, str] | None = None,
            timeout: float = 5) -> tuple[int, dict[str, str]]:
    headers = dict(headers or {})
    if cookie:
        headers["Cookie"] = cookie
    body = None
    if method == "POST":
        headers.update({"Content-Type": "application/json", "X-XGW-Panel": "1"})
        body = "{}"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, {name.lower(): value for name, value in response.getheaders()}
    finally:
        connection.close()


def error_details(exc: Exception) -> dict:
    return {"error": type(exc).__name__, "errno": getattr(exc, "errno", None)}


def wait_for_guest_api(port: int, wait: float = 24) -> dict:
    started = time.monotonic()
    deadline = started + wait
    attempts = 0
    last_error = {}
    while (remaining := deadline - time.monotonic()) > 0:
        attempts += 1
        try:
            status, _headers = request(port, "/api/state", timeout=min(2, remaining))
        except (ConnectionError, TimeoutError) as exc:
            last_error = error_details(exc)
            time.sleep(max(0, min(1, deadline - time.monotonic())))
        except (OSError, http.client.HTTPException) as exc:
            raise FailedCheck("guest_api", attempts=attempts, **error_details(exc)) from exc
        else:
            if status != 401:
                raise FailedCheck("guest_api", attempts=attempts, http_status=status)
            return {"attempts": attempts, "seconds": round(time.monotonic() - started, 3)}
    raise FailedCheck("guest_api_timeout", attempts=attempts, **last_error)


def checked_request(step: str, port: int, path: str, **options) -> tuple[int, dict[str, str]]:
    try:
        return request(port, path, **options)
    except (OSError, http.client.HTTPException) as exc:
        raise FailedCheck(step, **error_details(exc)) from exc


def login_link(port: int, token: str) -> str:
    try:
        cli = subprocess.run(
            ["/usr/local/bin/xgw", "panel"],
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
            capture_output=True, text=True, timeout=12,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise FailedCheck("cli", **error_details(exc)) from exc
    require(cli.returncode == 0 and bool(cli.stdout.splitlines()), "cli")
    require(token not in (cli.stdout + cli.stderr), "cli_permanent_secret")
    prefix = "Панель XGW: "
    first = cli.stdout.splitlines()[0]
    require(first.startswith(prefix), "cli_output")
    try:
        url = urlsplit(first.removeprefix(prefix))
    except ValueError as exc:
        raise FailedCheck("cli_url", **error_details(exc)) from exc
    query = parse_qs(url.query, keep_blank_values=True)
    require(url.scheme == "http" and url.netloc == f"127.0.0.1:{port}" and url.path == "/"
            and not url.fragment and set(query) == {"login"} and len(query["login"]) == 1
            and len(query["login"][0]) == 32, "cli_url")
    return "/?" + urlencode(query, doseq=True)


def session_state_ms(step: str, port: int, cookie: str, *, timeout: float) -> int:
    started = time.monotonic()
    status, _headers = checked_request(step, port, "/api/state", cookie=cookie, timeout=timeout)
    elapsed = round((time.monotonic() - started) * 1000)
    if status != 200:
        raise FailedCheck(step, http_status=status, elapsed_ms=elapsed)
    return elapsed


def verify(port: int, token: str, phase: str) -> dict:
    cookie = "xgw_panel=" + hmac.new(token.encode(), b"xgw-panel", hashlib.sha256).hexdigest()
    readiness = wait_for_guest_api(port)
    # Keep one cold request in flight. Repeated short requests can leave several
    # concurrent state builds running on the server after the client has timed out.
    first_state_ms = session_state_ms("existing_session", port, cookie, timeout=40)
    legacy = "/?" + urlencode({"token": token})
    code, headers = checked_request("legacy_redirect", port, legacy)
    require(code == 303 and headers.get("location") == "/", "legacy_redirect")
    if phase != "candidate":
        require(headers.get("set-cookie", "").split(";", 1)[0] == cookie, "legacy_baseline")
        return {"ok": True, "phase": phase, "http_ready": readiness,
                "first_state_ms": first_state_ms, "existing_session": True, "legacy_login": True}

    require("set-cookie" not in headers and headers.get("referrer-policy") == "no-referrer",
            "legacy_issued_session")
    status, _headers = checked_request("legacy_session_redirect", port, legacy, cookie=cookie)
    require(status == 303, "legacy_session_redirect")
    status, _headers = checked_request("legacy_session_retained", port, "/api/zapret2/overview",
                                      cookie=cookie)
    require(status == 200, "legacy_session_retained")
    fresh_link = login_link(port, token)
    status, _headers = checked_request("foreign_host", port, fresh_link,
                                       headers={"Host": "unrelated.invalid"})
    require(status == 403, "foreign_host")
    code, headers = checked_request("head_consumed_code", port, fresh_link, method="HEAD")
    require(code == 200 and "set-cookie" not in headers, "head_consumed_code")
    code, headers = checked_request("new_session", port, fresh_link)
    issued = headers.get("set-cookie", "")
    require(code == 303 and headers.get("location") == "/" and issued.split(";", 1)[0] == cookie
            and "HttpOnly" in issued and "SameSite=Strict" in issued, "new_session")
    code, headers = checked_request("reused_code", port, fresh_link)
    require(code == 403 and "set-cookie" not in headers, "reused_code")
    # No action has this name, even if an authentication check is accidentally dropped.
    inert = "/api/__t11_login_check__"
    status, _headers = checked_request("unauthorized_post", port, inert, method="POST")
    require(status == 401, "unauthorized_post")
    status, _headers = checked_request("foreign_origin", port, inert, method="POST", cookie=cookie,
                                       headers={"Origin": "http://unrelated.invalid"})
    require(status == 403, "foreign_origin")
    after_login = session_state_ms("state_after_login", port, issued.split(";", 1)[0], timeout=10)
    return {"ok": True, "phase": phase, "http_ready": readiness,
            "first_state_ms": first_state_ms, "state_after_login_ms": after_login,
            "existing_session": True, "legacy_login": False,
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
        result = {"ok": False, "phase": args.phase, "failed": str(exc), **exc.details}
    except (OSError, ValueError, config.ConfigError) as exc:
        result = {"ok": False, "phase": args.phase, "failed": "read_panel_config",
                  **error_details(exc)}
    print(json.dumps(result))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
