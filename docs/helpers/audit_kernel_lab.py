"""Offline IPv4 routing and TCP close controls for the ThinkCentre audit."""

from __future__ import annotations

import errno
import json
import os
import selectors
import socket
import subprocess
import sys
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


def path_counters(nft):
    counts = {}
    for family, table in (("ip", nft.TABLE), ("inet", nft.GUARD)):
        data = json.loads(run("nft", "-a", "-j", "list", "chain", family, table, "output"))
        for item in data["nftables"]:
            rule = item.get("rule", {})
            for expr in rule.get("expr", []):
                if "counter" in expr:
                    key = f"{family}.output.{rule['handle']}"
                    counts[key] = expr["counter"]["packets"]
    return counts


def tail_counters():
    listing = json.loads(run("nft", "-j", "list", "table", "ip", "audit"))
    return {
        item["rule"]["comment"]: next(e["counter"]["packets"] for e in item["rule"]["expr"]
                                      if "counter" in e)
        for item in listing["nftables"] if "rule" in item
    }


def closes(peer, label):
    before = json.loads(request(peer, "counts"))
    start = tail_counters()
    codes = [echo(7443, uid=UID) for _ in range(12)]
    # The peer serves each accepted TCP session before handling this IPC request.
    after = json.loads(request(peer, "counts"))
    end = tail_counters()
    emit({"phase": label, "attempts": len(codes), "client_ok": codes.count(0),
          "client_errors": codes.count(2),
          "peer": {k: after[k] - v for k, v in before.items()},
          "output": {k: end[k] - v for k, v in start.items()}})


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


def lab(host_net, *, candidate=False):
    # An anonymous network AND PID namespace are mandatory even when called by hand.
    if (os.getpid() != 1 or str(os.stat("/proc/self/ns/net").st_ino) == host_net
            or {i["ifname"] for i in json.loads(run("ip", "-j", "link"))} != {"lo"}):
        raise RuntimeError("a new empty network and PID namespace is required")
    # Use the exact installed renderer. No systemctl, XGW daemon or configuration writes.
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
}}
chain delivered {{
 type filter hook postrouting priority 11; policy accept;
 ip daddr {PEER} tcp dport 7443 oifname "audit0" counter comment "after_guard_wan"
 ip daddr {PEER} tcp dport 7443 oifname "audit-tun" counter comment "after_guard_tun"
}}
}}
""")
            closes(peer, "close_control")

            def apply(candidate):
                run("nft", "-f", "-", script=nft.render(candidate) + nft.render_guard(candidate))

            def trial(name, mark, expected, uid=None):
                before = path_counters(nft)
                code = echo(443, mark, uid)
                delta = {k: v - before[k] for k, v in path_counters(nft).items()}
                emit({"phase": name, "echo_rc": code, "expected_rc": expected,
                      "counter_deltas": {k: v for k, v in delta.items() if v}})

            apply(rules)
            trial("bypass_control", 2, 0)
            trial("unmarked_other_uid", None, 1, UID - 1)
            trial("off_selected_copy", zapret2.FAKE_MARK, 1)
            closes(peer, "close_xgw")
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
            if candidate:
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


if __name__ == "__main__":
    if sys.argv[1:] == ["peer"]:
        # Never listen in the host namespace on a stray direct invocation.
        if os.stat("/proc/self/ns/net").st_ino == os.stat("/proc/1/ns/net").st_ino:
            raise SystemExit("peer isolation required")
        peer_server()
    elif len(sys.argv) == 3 and sys.argv[1] in ("lab", "candidate"):
        lab(sys.argv[2], candidate=sys.argv[1] == "candidate")
    else:
        raise SystemExit("use the published ThinkCentre audit assignment")
