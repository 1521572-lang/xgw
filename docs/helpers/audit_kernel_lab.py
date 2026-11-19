"""Offline IPv4 routing and TCP close controls for the ThinkCentre audit."""

from __future__ import annotations

import errno
import json
import os
import selectors
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

PEER = "198.51.100.2"
UID = 65534  # synthetic application UID, independent of the installed service account


def run(*argv, script=None):
    return subprocess.run(argv, input=script, text=True, capture_output=True,
                          check=True, timeout=8).stdout


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def peer_server():
    print("namespace ready", flush=True)
    if input() != "start":
        raise ValueError("missing start")
    counts = {"echo": 0, "client_fin": 0, "final_ack": 0, "errors": 0,
              "last_ack_at_deadline": 0, "other_at_deadline": 0}
    with selectors.DefaultSelector() as events:
        events.register(sys.stdin, selectors.EVENT_READ)
        listeners = []
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind((PEER, 7444))
        events.register(udp, selectors.EVENT_READ)
        for port in (443, 7443):
            listener = socket.create_server((PEER, port), backlog=16)
            listeners.append(listener)
            events.register(listener, selectors.EVENT_READ)
        print("listening", flush=True)
        while True:
            for key, _ in events.select():
                if key.fileobj is udp:
                    if udp.recv(64) == b"x":
                        print("datagram", flush=True)
                    continue
                if key.fileobj is sys.stdin:
                    if sys.stdin.readline().strip() != "counts":
                        return
                    emit(counts)
                    continue
                conn, _ = key.fileobj.accept()
                with conn:
                    conn.settimeout(1)
                    try:
                        if conn.recv(1) != b"x":
                            continue
                        conn.sendall(b"x")
                        counts["echo"] += 1
                        if key.fileobj.getsockname()[1] != 7443 or conn.recv(1) != b"":
                            continue
                        counts["client_fin"] += 1
                        # Delay our FIN until the client has closed its fd and exited.
                        time.sleep(0.10)
                        conn.shutdown(socket.SHUT_WR)
                        end = time.monotonic() + 0.8
                        while True:
                            state = conn.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 1)[0]
                            if state == 7:
                                counts["final_ack"] += 1  # Linux TCP_CLOSE after LAST_ACK
                                break
                            if time.monotonic() >= end:
                                field = ("last_ack_at_deadline" if state == 9
                                         else "other_at_deadline")
                                counts[field] += 1
                                break
                            time.sleep(0.02)
                    except OSError:
                        counts["errors"] += 1


def line(proc):
    with selectors.DefaultSelector() as wait:
        wait.register(proc.stdout, selectors.EVENT_READ)
        if not wait.select(5):
            raise TimeoutError("peer timeout")
    return proc.stdout.readline().strip()


def request(proc, command):
    proc.stdin.write(command + "\n")
    proc.stdin.flush()
    return line(proc)


def echo(port, mark=None, uid=None):
    pid = os.fork()
    if not pid:
        result = 2
        try:
            if uid is not None:
                os.setgroups([])
                os.setgid(uid)
                os.setuid(uid)
            with socket.socket() as client:
                if mark is not None:
                    client.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, mark)
                client.settimeout(1.5)
                try:
                    client.connect((PEER, port))
                except OSError as exc:
                    # Kernel output drops may surface as EPERM. Setup/mark errors
                    # above must still be distinguishable from traffic not delivered.
                    if exc.errno in (errno.EPERM, errno.EACCES, errno.EHOSTUNREACH,
                                     errno.ENETUNREACH):
                        os._exit(1)
                    raise
                client.sendall(b"x")
                result = 0 if client.recv(1) == b"x" else 2
        except (TimeoutError, ConnectionRefusedError, ConnectionResetError):
            result = 1
        except OSError:
            result = 2
        finally:
            os._exit(result)
    return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1])


def audit_counters(*, path=False):
    # Read witness counters from our own table, independently of XGW rule listing.
    listing = json.loads(run("nft", "-j", "list", "table", "ip", "audit"))
    return {
        item["rule"]["comment"]: next(e["counter"]["packets"] for e in item["rule"]["expr"]
                                      if "counter" in e)
        for item in listing["nftables"] if "rule" in item
        and item["rule"]["comment"].startswith("probe_") == path
    }


def closes(peer, label, client=None):
    before = json.loads(request(peer, "counts"))
    start = audit_counters()
    codes = [echo(7443, uid=UID) if client is None else client() for _ in range(12)]
    # The peer serves each accepted TCP session before handling this IPC request.
    after = json.loads(request(peer, "counts"))
    # An asynchronous proxy may still be forwarding the last client's FIN.
    deadline = time.monotonic() + 3
    while (after["client_fin"] - before["client_fin"] < codes.count(0)
           and time.monotonic() < deadline):
        time.sleep(0.05)
        after = json.loads(request(peer, "counts"))
    end = audit_counters()
    emit({"phase": label, "attempts": len(codes), "client_ok": codes.count(0),
          "client_errors": codes.count(2),
          "peer": {k: after[k] - v for k, v in before.items()},
          "output": {k: end[k] - v for k, v in start.items()}})


def through_singbox():
    try:
        with (socket.create_connection(("127.0.0.1", 17443), timeout=3) as client,
              client.makefile("rb") as response):
            target = f"{PEER}:7443"
            client.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
            if response.readline(1024).split()[1:2] != [b"200"]:
                return 2
            for _ in range(16):
                if response.readline(1024) == b"\r\n":
                    client.sendall(b"x")
                    return 0 if response.read(1) == b"x" else 1
    except OSError:
        return 1
    return 2


def singbox_closes(peer, uid):
    binary = Path("/opt/xgw/sing-box/sing-box")
    if not binary.is_file():
        emit({"phase": "close_singbox", "blocked": "missing_installed_binary"})
        return
    config = {"inbounds": [{"type": "http", "listen": "127.0.0.1", "listen_port": 17443}],
              "outbounds": [{"type": "direct", "tag": "direct"}]}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(config), encoding="ascii")
        path.chmod(0o444)
        Path(directory).chmod(0o711)
        args = ["setpriv", "--no-new-privs", "--bounding-set=-all", "--clear-groups",
                f"--reuid={uid}", f"--regid={uid}", str(binary), "run", "-c", str(path)]
        with subprocess.Popen(args, cwd="/", stdout=subprocess.DEVNULL) as proc:
            try:
                end = time.monotonic() + 5
                while proc.poll() is None and time.monotonic() < end:
                    try:
                        with socket.create_connection(("127.0.0.1", 17443), timeout=0.3):
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    emit({"phase": "close_singbox", "blocked": "startup", "rc": proc.poll()})
                    return
                closes(peer, "close_singbox", through_singbox)
            finally:
                proc.kill()
                proc.wait(timeout=5)


def accounting_trials(peer, rules, apply):
    from xgw.config import Config
    from xgw.net import nft, sysctl

    def queued():
        data = json.loads(run("nft", "-j", "list", "table", "inet", nft.GUARD))
        return sum(expr["counter"]["packets"] for row in data["nftables"]
                   if row.get("rule", {}).get("chain") == "nfq_output"
                   for expr in row["rule"]["expr"] if "counter" in expr)

    def burst(client, label):
        start = queued()
        for _ in range(8):
            client.sendto(b"x", (PEER, 7444))
            if line(peer) != "datagram":
                raise RuntimeError("missing UDP receipt")
        emit({"phase": label, "received": 8, "queue_matches": queued() - start})

    cfg = Config()
    cfg.zapret2.engine = "auto"
    with (socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as old,
          socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as fresh):
        for client in (old, fresh):
            client.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, rules.mark_bypass)
        for value in ("0", "1"):
            (sysctl.PROC_SYS / sysctl.CONNTRACK_ACCT).write_text(value, encoding="ascii")
            wanted, _ = nft.build_rules(cfg, capture=True, time_uids=())
            apply(replace(rules, engine_queue=wanted.engine_queue))
            actual = sysctl.read(sysctl.CONNTRACK_ACCT)
            emit({"phase": "install_acct_" + value, "actual": actual, "queue": wanted.engine_queue})
            if actual != value or (wanted.engine_queue is not None) != (value == "1"):
                raise RuntimeError("unexpected accounting or missing Engine installation")
            if value == "0":
                burst(old, "unaccounted")
            else:
                burst(old, "existing_flow_after_enable")
                burst(fresh, "fresh_flow_after_enable")


def list_rules(*argv, as_json=False):
    """Keep the data-path measurement available when the listing command fails."""
    try:
        result = run("nft", *argv)
        if as_json:
            result = json.loads(result)
            if not isinstance(result, dict) or not isinstance(result.get("nftables"), list):
                return None, "invalid_output"
        return result, "ok"
    except subprocess.CalledProcessError as exc:
        return None, f"exit:{exc.returncode}"
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except ValueError:
        return None, "invalid_output"


def lab(host_net, *, candidate=False, close_ab=False):
    # An anonymous network AND PID namespace are mandatory even when called by hand.
    if (os.getpid() != 1 or str(os.stat("/proc/self/ns/net").st_ino) == host_net
            or {i["ifname"] for i in json.loads(run("ip", "-j", "link"))} != {"lo"}):
        raise RuntimeError("a new empty network and PID namespace is required")
    # Load only the renderer selected by the assignment.
    sys.dont_write_bytecode = True
    lib = Path(__file__).parent / "src" if candidate else Path("/opt/xgw/lib")
    if not (lib / "xgw/net/nft.py").is_file():
        raise RuntimeError("requested renderer is missing")
    sys.path.insert(0, str(lib))
    from xgw import nfqws2, zapret2
    from xgw.net import cmd, iprule, nft, tun

    rules = nft.Rules(lan_if="", wan_if="audit0", capture_lan=False, capture_local=True,
                      tproxy_port=12345, mark_proxy=1, mark_bypass=2, reserved=(), bypass=(),
                      forward_icmp=False, dns_direct="", time_uids=(), tun=True,
                      tun_name="audit-tun", singbox_uid=UID)
    with subprocess.Popen(["unshare", "--net", sys.executable, "-I", __file__, "peer"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as peer:
        try:
            if line(peer) != "namespace ready":
                raise RuntimeError("peer startup")
            if os.stat(f"/proc/{peer.pid}/ns/net").st_ino == os.stat("/proc/self/ns/net").st_ino:
                raise RuntimeError("peer network was not isolated")
            run("ip", "link", "add", "audit0", "type", "veth", "peer", "name", "audit1",
                "netns", str(peer.pid))
            run("ip", "addr", "add", "198.51.100.1/30", "dev", "audit0")
            for dev in ("audit0", "lo"):
                run("ip", "link", "set", dev, "up")
            ns = ("nsenter", "-t", str(peer.pid), "-n")
            run(*ns, "ip", "addr", "add", PEER + "/30", "dev", "audit1")
            run(*ns, "ip", "link", "set", "audit1", "up")
            if request(peer, "start") != "listening":
                raise RuntimeError("peer not listening")
            run("ip", "link", "add", "audit-tun", "type", "dummy")
            run("ip", "link", "set", "audit-tun", "up")
            iprule.ensure_tun(1, 101, cmd.run, 4, "audit-tun")
            for mark in (1, 2, 0x20000001, 0x20000012, zapret2.MARK, zapret2.FAKE_MARK):
                route = json.loads(run("ip", "-j", "route", "get", PEER, "mark", hex(mark)))
                emit({"phase": "fib", "mark": hex(mark), "dev": route[0].get("dev")})
            run("nft", "-f", "-", script=f"""table ip audit {{
chain before {{
 type filter hook output priority -151; policy accept;
 ip daddr {PEER} tcp dport 7443 counter comment "all"
 ip daddr {PEER} tcp dport 7443 meta skuid {UID} counter comment "uid"
}}
chain marked {{
 type filter hook output priority -149; policy accept;
 ip daddr {PEER} tcp dport 7443 meta mark 1 counter comment "marked_proxy"
 ip daddr {PEER} tcp dport 7443 meta mark 0 counter comment "marked_zero"
 ip daddr {PEER} tcp dport 7443 meta mark 2 tcp flags == ack counter comment "marked_bypass_ack"
 ip daddr {PEER} tcp dport 443 meta mark 1 counter comment "probe_proxy"
}}
chain delivered {{
 type filter hook postrouting priority 11; policy accept;
 ip daddr {PEER} tcp dport 7443 oifname "audit0" counter comment "after_guard_wan"
 ip daddr {PEER} tcp dport 7443 oifname "audit-tun" counter comment "after_guard_tun"
 ip daddr {PEER} tcp dport 443 oifname "audit0" counter comment "probe_wan"
 ip daddr {PEER} tcp dport 443 oifname "audit-tun" counter comment "probe_tun"
}}
}}
""")
            closes(peer, "close_control")

            def apply(candidate):
                run("nft", "-f", "-", script=nft.render(candidate) + nft.render_guard(candidate))

            def trial(name, mark, expected, uid=None):
                before = audit_counters(path=True)
                code = echo(443, mark, uid)
                delta = {k: v - before[k] for k, v in audit_counters(path=True).items()}
                emit({"phase": name, "echo_rc": code, "expected_rc": expected,
                      "counter_deltas": {k: v for k, v in delta.items() if v}})

            apply(rules)
            trial("bypass_control", 2, 0)
            trial("unmarked_other_uid", None, 1, UID - 1)
            trial("off_selected_copy", zapret2.FAKE_MARK, 1)
            if close_ab:
                expected = nft.render(rules)
                table = ("ip", nft.TABLE)
                initial, initial_status = list_rules("-t", "list", "table", *table)
            closes(peer, "close_xgw")
            if close_ab:
                singbox_closes(peer, UID)
                trial("other_uid_after_close", None, 1, UID - 1)
                terse, terse_status = list_rules("-t", "list", "table", *table)
                full, full_status = list_rules("list", "table", *table)
                _, json_chain = list_rules("-a", "-j", "list", "chain", *table, "output",
                                           as_json=True)
                _, json_ruleset = list_rules("-j", "list", "ruleset", as_json=True)
                manifest = nft.manifest(expected, *table)
                emit({"phase": "rule_integrity", "text_initial": initial_status,
                      "text_final": terse_status, "text_full": full_status,
                      "json_chain": json_chain, "json_ruleset": json_ruleset,
                      "manifest_ok": bool(terse and nft.manifest(terse, *table) == manifest),
                      "stable": bool(initial and terse and full
                                     and nft.structure(initial, *table)
                                     == nft.structure(terse, *table)
                                     == nft.structure(full, *table))})
            apply(replace(rules, zapret2_queue=200))
            trial("closed_selected_copy", zapret2.FAKE_MARK, 1)
            elems = ", ".join(f"{m:#x} timeout 30s" for m in (zapret2.MARK, zapret2.FAKE_MARK))
            run("nft", "-f", "-", script=f"add element inet {nft.GUARD} {zapret2.LIVE} "
                f"{{ {elems} }}\n")
            trial("open_selected_copy", zapret2.FAKE_MARK, 0)
            trial("open_selected_no_listener", zapret2.MARK, 1)
            apply(replace(rules, engine_queue=200))
            trial("engine_copy", 2 | nfqws2.FAKE_MARK, 0)
            trial("engine_no_listener", 2, 0)
            trial("engine_other_uid", None, 1, UID - 1)
            if candidate and not close_ab:
                accounting_trials(peer, rules, apply)
            # Exercise the actual routines used by Capture.restore_tun independently
            # of the dummy used above. TUN may be unavailable under hardening.
            for stage in ("absent", "down"):
                dev = "audit-real"
                if stage == "down":
                    run("ip", "link", "set", dev, "down")
                started = time.monotonic()
                created = tun.ensure(dev, cmd.run)
                iprule.ensure_tun(7, 107, cmd.run, 4, dev)
                emit({"phase": "tun_" + stage, "created": created,
                      "usable": tun.present(dev, cmd.run),
                      "routes": iprule.present_tun(7, 107, cmd.run, 4, dev),
                      "ms": round(1000 * (time.monotonic() - started))})
        finally:
            peer.kill()
            peer.wait(timeout=5)


def assess_close(path, *, baseline):
    with Path(path).open(encoding="ascii") as stream:
        rows = [json.loads(line) for line in stream]
    phases = {r["phase"]: r for r in rows if r["phase"] != "fib"}
    if len(phases) != sum(r["phase"] != "fib" for r in rows):
        raise ValueError("duplicate phase")
    controls = {"bypass_control": 0, "unmarked_other_uid": 1, "off_selected_copy": 1,
                "other_uid_after_close": 1, "closed_selected_copy": 1, "open_selected_copy": 0,
                "open_selected_no_listener": 1, "engine_copy": 0, "engine_no_listener": 0,
                "engine_other_uid": 1}
    missing = sorted((controls.keys() | {"close_control", "close_xgw", "close_singbox",
                                         "rule_integrity"}) - phases.keys())
    if missing:
        return {"missing_phases": missing, "synthetic_pass": False, "listing_pass": False}
    paths = {name: phases[name]["echo_rc"] == expected for name, expected in controls.items()}
    protected = ("unmarked_other_uid", "other_uid_after_close", "engine_other_uid")
    leaks = {name: phases[name]["counter_deltas"].get("probe_wan", 0) for name in protected}
    fib = [r for r in rows if r["phase"] == "fib"]
    marks = {"0x1", "0x2", "0x20000001", "0x20000012", "0x10000000", "0x50000000"}
    routing = (len(fib) == len(marks) and {r["mark"] for r in fib} == marks and
               all(r["dev"] == ("audit-tun" if r["mark"] == "0x1" else "audit0") for r in fib))

    def close(row, *, old):
        p = row["peer"]
        transfer = (row["attempts"] == row["client_ok"] == p["echo"] == p["client_fin"] == 12
                    and row["client_errors"] == p["errors"] == p["other_at_deadline"] == 0)
        return transfer and (p["final_ack"], p["last_ack_at_deadline"]) == (
            (0, 12) if old else (12, 0))

    control = close(phases["close_control"], old=False)
    synthetic = phases["close_xgw"]
    delta = synthetic["output"]
    route_seen = delta["after_guard_tun"] > 0 if baseline else delta["marked_bypass_ack"] >= 12
    integrity = phases["rule_integrity"]
    proxy = phases["close_singbox"]
    if "blocked" in proxy:
        proxy_result = "BLOCKED"
    elif close(proxy, old=False):
        proxy_result = "CLOSED"
    elif close(proxy, old=True):
        proxy_result = "LAST_ACK"
    else:
        proxy_result = "MIXED_OR_FAILED"
    result = {"side": "old" if baseline else "new", "paths": paths, "fib": routing,
              "protected_wan_packets": leaks,
              "control": control, "synthetic_expected": close(synthetic, old=baseline),
              "route_seen": route_seen, "integrity": integrity, "installed_binary": proxy_result}
    result["synthetic_pass"] = all((all(paths.values()), not any(leaks.values()), routing, control,
                                    result["synthetic_expected"], route_seen))
    result["listing_pass"] = integrity["manifest_ok"] and integrity["stable"] and all(
        integrity.get(field) == "ok"
        for field in ("text_initial", "text_final", "text_full", "json_chain", "json_ruleset")
    )
    return result


if __name__ == "__main__":
    if sys.argv[1:] == ["peer"]:
        # Never listen in the host namespace on a stray direct invocation.
        if os.stat("/proc/self/ns/net").st_ino == os.stat("/proc/1/ns/net").st_ino:
            raise SystemExit("peer isolation required")
        peer_server()
    elif len(sys.argv) == 3 and sys.argv[1] in ("lab", "candidate", "close-ab"):
        lab(sys.argv[2], candidate=sys.argv[1] != "lab", close_ab=sys.argv[1] == "close-ab")
    elif len(sys.argv) == 3 and sys.argv[1] in ("assess-old", "assess-new"):
        result = assess_close(sys.argv[2], baseline=sys.argv[1] == "assess-old")
        emit(result)
        raise SystemExit(0 if result["synthetic_pass"] and result["listing_pass"] else 1)
    else:
        raise SystemExit("use the published ThinkCentre audit assignment")
