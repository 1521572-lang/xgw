"""Проверка hold=block на ядре ThinkCentre в изолированных сетях."""
import json
import logging
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

WAN = "198.51.100.2"
URL = f"http://{WAN}:18080/sub"


def run(argv, *, timeout=20):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def require(ok, label):
    if not ok:
        print("STOP " + label, flush=True)
        raise ValueError(label)
    print(f"OK {label}", flush=True)


def process(stack, argv):
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    stack.callback(child.wait)
    stack.callback(child.terminate)
    return child


def peer(stack, name, local, remote):
    child = process(stack, ["unshare", "--net", "--", "sleep", "120"])
    ns = f"/proc/{child.pid}/ns/net"
    for _ in range(100):
        if child.poll() is not None:
            raise RuntimeError("namespace")
        if not os.path.samefile(ns, "/proc/self/ns/net"):
            break
        time.sleep(0.02)
    else:
        raise TimeoutError("namespace")
    enter = ["nsenter", "--net=" + ns, "--"]
    run(["ip", "link", "add", name, "type", "veth", "peer", "name", "edge", "netns",
         str(child.pid)])
    run(["ip", "addr", "add", local + "/24", "dev", name])
    run(["ip", "link", "set", name, "up"])
    run([*enter, "ip", "addr", "add", remote + "/24", "dev", "edge"])
    run([*enter, "ip", "link", "set", "edge", "up"])
    run([*enter, "ip", "link", "set", "lo", "up"])
    run([*enter, "ip", "route", "add", "default", "via", local])
    return enter


def http(enter=()):
    proc = subprocess.run([*enter, "curl", "--silent", "--fail", "--noproxy", "*",
                           "--max-time", "2", URL], capture_output=True, timeout=4)
    if proc.returncode == 0 and proc.stdout == b"xgw-test":
        return True
    if proc.returncode in (7, 28):
        return False
    raise RuntimeError("http")


def udp_received(enter, port):
    listing = run([*enter, "nft", "-nn", "list", "chain", "inet", "observe", "incoming"])
    return int(re.search(rf"udp dport {port} counter packets (\d+)", listing)[1])


def isolated(root, stack):
    require(not os.path.samefile("/proc/self/ns/net", "/proc/1/ns/net")
            and socket.if_nameindex() == [(1, "lo")] and not run(["nft", "list", "tables"]).strip(),
            "isolated")
    os.environ["XGW_ROOT"] = str(root)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from xgw import engine, fetch
    from xgw.config import Config
    from xgw.net.capture import Capture
    from xgw.paths import Paths

    run(["ip", "link", "set", "lo", "up"])
    wan = peer(stack, "wan0", "198.51.100.1", WAN)
    lan = peer(stack, "lan0", "192.168.50.1", "192.168.50.2")
    run(["sysctl", "-q", "-w", "net.ipv4.ip_forward=1"])
    body = root / "www"
    body.mkdir()
    (body / "sub").write_bytes(b"xgw-test")
    process(stack, [*wan, "timeout", "100s", sys.executable, "-I", "-m", "http.server",
                    "18080", "--bind", WAN, "--directory", str(body)])
    for _ in range(50):
        if http():
            break
        time.sleep(0.05)
    require(http() and http(lan), "positive_controls")
    run([*wan, "nft", "add", "table", "inet", "observe"])
    run([*wan, "nft", "add", "chain", "inet", "observe", "incoming",
         "{ type filter hook input priority 0; policy accept; }"])
    for port in (67, 123):
        run([*wan, "nft", "add", "rule", "inet", "observe", "incoming",
             "udp", "dport", str(port), "counter"])
    paths = Paths(root)
    paths.ensure()
    cfg = Config()
    cfg.capture.containers = cfg.network.tcp_bbr = False
    cfg.network.lan_if, cfg.network.wan_if = "lan0", "wan0"
    cap = Capture(cfg, paths, time_uids=(os.getuid(),))
    cap.sys_net = root / "sys"
    for label, content in [("missing", None), ("broken", b"{"), ("encoding", b"\xff")]:
        if content is not None:
            paths.xray_config_file.write_bytes(content)
        require(cap.up() == "blocked" and cap.guard_loaded() is True and cap.loaded() is True,
                label + "_rules")
        require(not http() and not http(lan), label + "_host_lan_closed")
        mark = engine.bypass_mark(cfg, logging.getLogger("acceptance"))
        require(mark == cfg.capture.mark_bypass and
                fetch.fetch_subscription(URL, mark=mark, retries=1, timeout=3).body == b"xgw-test",
                label + "_subscription")
    for source, dest, label in [(68, 67, "dhcp"), (0, 123, "time")]:
        before = udp_received(wan, dest)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("", source))
            sock.sendto(b"x", (WAN, dest))
        for _ in range(20):
            if udp_received(wan, dest) > before:
                break
            time.sleep(0.03)
        require(udp_received(wan, dest) == before + 1, label + "_packet")
    for fail, hold in [("closed", "direct"), ("open", "block")]:
        cfg.capture.fail_mode, cfg.capture.hold = fail, hold
        require(cap.up() == "off" and http() and http(lan), fail + "_" + hold)
    cfg.capture.fail_mode, cfg.capture.hold = "closed", "block"
    require(cap.disable() == "off" and cap.up() == "off" and http(lan), "explicit_off")
    require(cap.enable() == "blocked" and not http(lan), "enabled")
    paths.xray_config_file.write_text(json.dumps({
        "inbounds": [{"tag": "tproxy-in", "port": cfg.capture.tproxy_port}],
    }))
    require(cap.up() == "on" and cap.loaded() is True and cap.guard_loaded() is True, "on_again")


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
    directory = Path("/run/xgw-hold-install")
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
        logging.disable(logging.CRITICAL)
        with tempfile.TemporaryDirectory(prefix="xgw-hold-") as root, ExitStack() as stack:
            isolated(Path(root), stack)
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
