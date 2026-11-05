"""Приёмка восстановления барьера. Сетевые правки разрешены только в свежем netns."""
import errno
import json
import logging
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

DEST = "198.51.100.2"  # TEST-NET-2, только dummy в новом пространстве
WATCH = "xgw_acceptance"


def run(argv, *, timeout=20):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def require(ok, label):
    if not ok:
        raise ValueError(label)
    print(f"OK {label}", flush=True)


def health():
    data = json.loads(run(["xgw", "status", "--json"]))
    cap = data.get("capture") or {}
    require(data.get("daemon_down") is False and data.get("xray", {}).get("ok") is True
            and cap.get("mode") == "on" and cap.get("loaded") is True
            and cap.get("blocked") is False and not cap.get("capture_failed"), "on")
    code = run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o", "/dev/null",
                "-w", "%{http_code}", "https://1.1.1.1/"])
    require(code.isdigit() and 200 <= int(code) < 400, "https")


def counter(table, chain):
    listing = run(["nft", "-n", "list", "chain", "inet", table, chain])
    pattern = r"^\s*counter packets (\d+) bytes \d+" + (" drop" if chain == "output" else "") + "$"
    matches = re.findall(pattern, listing, flags=re.M)
    if len(matches) != 1:
        raise ValueError("counter_shape")
    return int(matches[0])


def packet(kind):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.settimeout(0.3)
        try:
            if kind == socket.SOCK_STREAM:
                sock.connect((DEST, 23456))
            else:
                sock.sendto(b"x", (DEST, 23457))
        except OSError as exc:
            if not isinstance(exc, TimeoutError) and exc.errno not in (errno.EPERM, errno.EACCES):
                raise


def cut(root):
    # До первой мутации проверяем namespace, его интерфейсы и отсутствие чужих правил.
    require(not os.path.samefile("/proc/self/ns/net", "/proc/1/ns/net")
            and socket.if_nameindex() == [(1, "lo")] and not run(["nft", "list", "tables"]).strip(),
            "isolated")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from xgw.config import Config
    from xgw.daemon import Daemon
    from xgw.net import cmd, nft
    from xgw.net.capture import Capture
    from xgw.paths import Paths

    os.environ["XGW_ROOT"] = str(root)
    paths = Paths(root)
    paths.ensure()
    cfg = Config()
    cfg.capture.containers = cfg.capture.lan = cfg.network.tcp_bbr = False
    cfg.network.lan_if = ""
    cfg.capture.local = True
    paths.xray_config_file.write_text(json.dumps({
        "inbounds": [{"tag": "tproxy-in", "port": cfg.capture.tproxy_port}],
    }))
    fault = False
    rejected = 0

    def runner(argv, **kw):
        nonlocal rejected
        if fault and argv == ["nft", "-f", "-"] and "table ip xgw\n" in kw.get("input", ""):
            # Вся штатная транзакция отклоняется nft. Отдельная таблица проходит как есть.
            kw["input"] += "add rule inet missing_table missing_chain drop\n"
            try:
                return cmd.run(argv, **kw)
            except cmd.CommandError:
                rejected += 1
                raise
        return cmd.run(argv, **kw)

    cap = Capture(cfg, paths, runner=runner, generation=nft.generation,
                  proc_sys=root / "proc", time_uids=())
    cap.sys_net = root / "sys"
    run(["ip", "link", "set", "lo", "up"])
    run(["ip", "link", "add", "dummy0", "type", "dummy"])
    run(["ip", "addr", "add", "198.51.100.1/24", "dev", "dummy0"])
    run(["ip", "link", "set", "dummy0", "up"])
    require(cap.up() == "on" and cap.guard_loaded() is True, "initial_guard")
    cmd.run(["nft", "-f", "-"], input=f"""
delete table ip xgw
delete table inet xgw_guard
table inet {WATCH} {{
    chain late {{
        type filter hook postrouting priority 11; policy accept;
        ip daddr {DEST} jump observe
    }}
    chain observe {{
        counter
    }}
}}
""")
    require(cap.guard_loaded() is False, "deleted")
    for kind, label in [(socket.SOCK_STREAM, "tcp"), (socket.SOCK_DGRAM, "udp")]:
        before = counter(WATCH, "observe")
        packet(kind)
        require(counter(WATCH, "observe") > before, label + "_control")

    fault = True
    context = SimpleNamespace(
        capture=cap, cfg=cfg, capture_info=None, _capture_error="", xray_down_since=None,
        log=logging.getLogger("acceptance"), notifier=SimpleNamespace(event=lambda *a, **k: None),
    )
    Daemon._guard_capture(context, True, 0)
    data = context.capture_info or {}
    require(rejected > 0 and data.get("capture_failed") and data.get("loaded") is False
            and data.get("guard_recovery") == "restored" and cap.guard_loaded() is True
            and nft.listing(runner, "ip", nft.TABLE) == "", "independent_recovery")
    for kind, label in [(socket.SOCK_STREAM, "tcp"), (socket.SOCK_DGRAM, "udp")]:
        before, late = counter(nft.GUARD, "output"), counter(WATCH, "observe")
        packet(kind)
        require(counter(nft.GUARD, "output") > before and counter(WATCH, "observe") == late,
                label + "_dropped")
    require(cap.restore_guard() == "present", "already_present")
    fault = False
    require(cap.up() == "on" and cap.loaded() is True, "full_recovery")
    for change, mode in ((cap.open, "open"), (cap.disable, "off")):
        require(change() == mode and cap.restore_guard() == "not_required"
                and nft.listing(runner, "inet", nft.GUARD) == "", mode)


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
    directory = Path("/run/xgw-guard-recovery")
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
        with tempfile.TemporaryDirectory(prefix="xgw-guard-") as root:
            cut(Path(root))
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
