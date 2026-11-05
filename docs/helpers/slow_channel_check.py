"""PR-3: контролируемая передача на loopback и проверка установленного пакета."""
import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit


def run(argv, *, timeout=20):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def require(ok, label):
    if not ok:
        print("STOP " + label, flush=True)
        raise ValueError(label)
    print("OK " + label, flush=True)


class Origin(BaseHTTPRequestHandler):
    # Отвечаем сами на абсолютный URI HTTP-прокси. Никакого запроса к upstream.
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        small = path == "/short"
        self.send_response(200)
        self.send_header("Content-Length", "64000" if small else "1000000")
        self.end_headers()
        if small:
            self.wfile.write(b"x" * 64000)
            return
        size = 500 if path == "/16" else 2000
        with contextlib.suppress(OSError):
            for _ in range(40):
                self.wfile.write(b"x" * size)
                if path == "/truncated":
                    break
                if path == "/stall":
                    time.sleep(6)
                    break
                time.sleep(0.25)


def slow_channel():
    require(not os.path.samefile("/proc/self/ns/net", "/proc/1/ns/net")
            and socket.if_nameindex() == [(1, "lo")], "isolated")
    run(["ip", "link", "set", "lo", "up"])
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from xgw.config import Config
    from xgw.watch import speed
    from xgw.watch.guard import Guard

    cfg = Config()
    cfg.speed.max_seconds = 8
    cfg.speed.url_fallback = ""
    now = [1000.0]
    guard = Guard(cfg, lambda: now[0])
    tag, key = "proxy-test", "test"
    keys = {tag: key}
    total = 0

    def window(rate, own=False):
        nonlocal total
        span = cfg.speed.passive_seconds
        now[0] += span
        count = int(rate * 1000 * span / 8)
        total += count
        guard.sample({tag: total}, {tag: count if own else 0}, keys)

    guard.sample({tag: 0}, {}, keys)
    window(16)
    window(16)
    window(16, own=True)
    window(0)
    window(16)
    window(16)
    require(not guard.due() and not guard.throttled, "idle_and_own")
    window(16)
    require(guard.due() == [key] and not guard.throttled, "confirmation_due")
    with ThreadingHTTPServer(("127.0.0.1", 0), Origin) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        try:
            for i, rate in enumerate((16, 64, 64), 1):
                cfg.speed.url = f"http://127.0.0.1:{port}/{rate}"
                result = speed.measure(SimpleNamespace(probe_port=port), cfg, probe_pass="dummy")
                print(f"sample={i} bytes={result.bytes_read} sec={result.seconds} "
                      f"mbps={result.mbps}", flush=True)
                require(0 < result.bytes_read < speed.MIN_BYTES and 7.8 <= result.seconds <= 9
                        and result.mbps is not None
                        and rate * 0.8 <= result.mbps * 1000 <= rate * 1.2, f"speed_{i}")
                now[0] += 200
                require(guard.note_total(key, result.mbps) == (i == 3), f"confirmation_{i}")
            require(key in guard.throttled, "throttled")
            for path, detail in [("short", "слишком мал"), ("stall", "тишина"),
                                 ("truncated", "закрыто")]:
                cfg.speed.url = f"http://127.0.0.1:{port}/{path}"
                result = speed.measure(SimpleNamespace(probe_port=port), cfg, probe_pass="dummy")
                require(result.mbps is None and detail in result.error, path)
        finally:
            server.shutdown()
    guard.note_total(key, 40)
    require(not guard.throttled and not guard.due(), "recovered")
    limit = cfg.speed.guard_daily_mb * 1_000_000
    require(guard.can_spend(limit), "budget_available")
    guard.spend(limit)
    require(not guard.can_spend(1) and not guard.better(9.5, 8)
            and guard.better(30, 8) and guard.cool_down() > now[0] and guard.cooling(),
            "budget_and_hysteresis")


def health():
    data = json.loads(run(["xgw", "status", "--json"]))
    cap = data.get("capture") or {}
    require(data.get("daemon_down") is False and data.get("xray", {}).get("ok") is True
            and cap.get("mode") == "on" and cap.get("loaded") is True
            and cap.get("blocked") is False and not cap.get("capture_failed"), "on")
    code = run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o", "/dev/null",
                "-w", "%{http_code}", "https://1.1.1.1/"])
    require(code.isdigit() and 200 <= int(code) < 400, "https")


def match(tree):
    files = run(["git", "-c", f"safe.directory={tree}", "-C", str(tree), "ls-files", "-z",
                 "src/xgw", "packaging"]).rstrip("\0").split("\0")
    if not files or not all(files):
        return False
    for name in files:
        dest = Path("/opt/xgw") / ("lib/" + name[4:] if name.startswith("src/") else name)
        if not dest.is_file() or dest.read_bytes() != (tree / name).read_bytes():
            return False
    return True


def check_health():
    try:
        health()
        return True
    except (ValueError, OSError, subprocess.SubprocessError):
        return False


def deploy(base):
    target = Path(__file__).resolve().parents[2]
    directory = Path("/run/xgw-slow-install")
    # Повторная команда даже после обрыва связи не может начать вторую установку.
    directory.mkdir(mode=0o700)
    require(match(base) and check_health(), "baseline")
    def install(tree, name):
        with (directory / (name + ".log")).open("xb") as stream:
            try:
                rc = subprocess.run(["sh", str(tree / "packaging/install.sh"), "--yes"],
                                    stdout=stream, stderr=subprocess.STDOUT).returncode
            except OSError:
                rc = 127
        print(f"{name}_rc={rc}", flush=True)
        return rc

    accepted = False
    try:
        if install(target, "install") == 0 and match(target):
            for attempt in range(3):
                if check_health():
                    accepted = True
                    break
                if attempt < 2:
                    time.sleep(3)
    finally:
        if not accepted:
            rc = install(base, "rollback")
            restored = rc == 0 and match(base) and check_health()
            print("rollback_verified=" + str(restored).lower(), flush=True)
    require(accepted, "installed")


def main():
    if sys.argv[1:] == ["health"]:
        health()
    elif len(sys.argv) == 3 and sys.argv[1] == "deploy":
        deploy(Path(sys.argv[2]).resolve())
    elif sys.argv[1:] == ["isolated"]:
        return subprocess.run(["unshare", "--net", "--", sys.executable, "-I", __file__, "child"],
                              timeout=90).returncode
    elif sys.argv[1:] == ["child"]:
        slow_channel()
    else:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Не выводим тексты системных команд, адреса и конфиги. Последний OK указывает этап.
        print("STOP", type(exc).__name__, flush=True)
        sys.exit(3)
