"""Наблюдение штатной смены. Два ограниченных HTTP/2 GET, без команд изменения XGW."""

import argparse
import json
import os
import pwd
import re
import ssl
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import urlsplit

SIZE = 2 * 1024 * 1024
SLOTS = ("legacy", "blue", "green")


class Partial(Exception):
    """Публичная причина из фиксированного набора."""


def image(pid):
    proc = Path("/proc") / str(pid)
    born = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
    exe = (proc / "exe").stat()
    return born, exe.st_dev, exe.st_ino


def sample(processes, expected, uid, phase, result):
    live = {}
    for slot in SLOTS:
        command = ["systemctl", "show", processes.unit(slot), "-p", "MainPID", "-p", "LoadState"]
        response = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        fields = dict(s.split("=", 1) for s in response.stdout.splitlines() if "=" in s)
        if fields.get("LoadState") == "not-found":
            continue
        if response.returncode or not fields.get("MainPID", "").isdigit():
            raise Partial("UNIT_UNREADABLE")
        pid = int(fields["MainPID"])
        if not pid:
            continue
        try:
            ident = image(pid)
            status = (Path("/proc") / str(pid) / "status").read_text()
            values = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
            uids = [int(n) for n in values["Uid"].split()]
            item = {"phase": phase, "slot": slot, "same_image": ident == image(pid),
                    "core": ident[1:] == expected, "uid_ok": uids == [uid] * 4,
                    "caps_zero": int(values["CapEff"], 16) == 0}
        except (FileNotFoundError, ProcessLookupError):
            result["vanished_samples"] += 1
            continue
        if not all(item[k] for k in ("same_image", "core", "uid_ok", "caps_zero")):
            item["sample"] = result["samples"]
            kind = "unstable" if not item["same_image"] else ("core" if item["core"] else "other")
            result["permission_observations"].setdefault(kind, item)
        live[slot] = (pid, ident)
    result["samples"] += 1
    return live


def bridge_sockets(process, port):
    pid, ident = process
    if ident != image(pid):
        raise Partial("PROCESS_CHANGED")
    fds = set()
    for fd in (Path("/proc") / str(pid) / "fd").iterdir():
        try:
            fds.add(os.readlink(fd))
        except FileNotFoundError:
            continue
    rows = [line.split() for line in Path("/proc/net/tcp").read_text().splitlines()[1:]]
    return {r[9] for r in rows if r[1] == f"0100007F:{port:04X}" and r[3] == "01"
            and f"socket:[{r[9]}]" in fds}


class Transfer:
    def __init__(self, stack, cfg, proxy, password, parts):
        from h2.config import H2Configuration
        from h2.connection import H2Connection

        from xgw.fetch import open_tunnel

        ctx = ssl.create_default_context()
        ctx.set_alpn_protocols(["h2"])
        raw = stack.enter_context(open_tunnel(("127.0.0.1", proxy), parts.hostname,
                                              parts.port or 443, user="xgw", password=password,
                                              timeout=20, deadline=time.monotonic() + 30))
        self.sock = stack.enter_context(ctx.wrap_socket(raw, server_hostname=parts.hostname))
        if self.sock.selected_alpn_protocol() != "h2":
            raise Partial("NO_HTTP2")
        self.h2 = H2Connection(H2Configuration(client_side=True, header_encoding="utf-8"))
        self.h2.initiate_connection()
        path = parts.path or "/"
        self.h2.send_headers(1, [(":method", "GET"), (":scheme", "https"),
                                 (":authority", parts.netloc),
                                 (":path", path + ("?" + parts.query if parts.query else "")),
                                 ("user-agent", cfg.probe.user_agent),
                                 ("accept-encoding", "identity"),
                                 ("range", f"bytes=0-{SIZE - 1}")], end_stream=True)
        self.flush()
        self.count = self.credit = 0
        self.ended = self.headers_ok = False
        self.ack = None
        deadline = time.monotonic() + 45
        while not self.count:
            self.receive(deadline)

    def flush(self):
        data = self.h2.data_to_send()
        if data:
            self.sock.sendall(data)

    def receive(self, deadline):
        from h2 import events

        left = deadline - time.monotonic()
        if left <= 0:
            raise Partial("TIMEOUT")
        self.sock.settimeout(min(30, left))
        data = self.sock.recv(65536)
        if not data:
            raise Partial("CONNECTION_CLOSED")
        for event in self.h2.receive_data(data):
            if isinstance(event, events.ResponseReceived):
                h = dict(event.headers)
                span = re.fullmatch(r"bytes 0-2097151/(\d+|\*)", h.get("content-range", ""), re.I)
                self.headers_ok = (h.get(":status") == "206" and bool(span)
                                   and (span[1] == "*" or int(span[1]) >= SIZE)
                                   and h.get("content-length", str(SIZE)) == str(SIZE)
                                   and h.get("content-encoding", "identity") == "identity")
                if not self.headers_ok:
                    raise Partial("RANGE_OR_HEADERS")
            elif isinstance(event, events.DataReceived):
                if event.stream_id != 1 or not self.headers_ok:
                    raise Partial("UNEXPECTED_STREAM")
                self.count += len(event.data)
                self.credit += event.flow_controlled_length
                if self.count > SIZE:
                    raise Partial("BODY_SIZE")
            elif isinstance(event, events.PingAckReceived):
                self.ack = event.ping_data
            elif isinstance(event, events.StreamEnded) and event.stream_id == 1:
                self.ended = True
                if self.count != SIZE:
                    raise Partial("BODY_SIZE")
            elif isinstance(event, (events.StreamReset, events.ConnectionTerminated)):
                raise Partial("REMOTE_CLOSED")
        self.flush()  # Квитанции HTTP/2. Кредит DATA выдаётся только в finish().

    def challenge(self):
        token = os.urandom(8)
        self.h2.ping(token)
        self.flush()
        deadline = time.monotonic() + 30
        while self.ack != token:
            self.receive(deadline)
        if self.ended or not 0 < self.count <= 65535:
            raise Partial("FLOW_WINDOW")

    def finish(self):
        deadline = time.monotonic() + 240
        while not self.ended:
            if self.credit:
                time.sleep(self.credit / 30000)
                self.h2.acknowledge_received_data(self.credit, 1)
                self.credit = 0
                self.flush()
            self.receive(deadline)
        return self.count


def observe(result):
    from xgw import config
    from xgw.apply import singbox_process as processes
    from xgw.generator import builder, singbox
    from xgw.paths import Paths

    paths = Paths(Path("/"))
    cfg, _ = config.load(paths.config_file)
    parts = urlsplit(cfg.speed.youtube_speed_url)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.hostname.lower().rstrip(".") == "speed.cloudflare.com"):
        raise Partial("CONFIGURED_TARGET_UNAVAILABLE")
    binary = singbox.find_binary(None, paths)
    if binary is None:
        raise Partial("CORE_NOT_FOUND")
    info = binary.stat()
    expected = info.st_dev, info.st_ino
    uid = pwd.getpwnam("xgw-singbox").pw_uid
    state = processes.read(paths)
    old = state["active"]
    if state["pending"] or state["draining"]:
        raise Partial("BUSY")
    routed = json.loads(paths.xray_config_file.read_text())
    password, _ = builder.probe_state(routed)
    bridges = {o["tag"]: o["settings"]["servers"][0]["port"] for o in routed["outbounds"]
               if singbox.bridge_variant(o)}
    live = sample(processes, expected, uid, "before", result)
    if set(live) != {old}:
        raise Partial("BASELINE_PROCESS")
    old_process = live[old]
    with ExitStack() as stack:
        nodes = [n for n in builder.applied_nodes(routed) if n.tag in bridges]
        for node in nodes[:3]:
            port = bridges[node.tag]
            baseline = bridge_sockets(old_process, port)
            attempt = ExitStack()
            try:
                first = Transfer(attempt, cfg, node.probe_port, password, parts)
            except (OSError, Partial) as exc:
                result["target_error"] = str(exc) if isinstance(exc, Partial) else "CONNECT_ERROR"
                attempt.close()
                continue
            except BaseException:
                attempt.close()
                raise
            stack.enter_context(attempt)
            break
        else:
            raise Partial("NO_WORKING_TRANSFER")
        old_socket = bridge_sockets(old_process, port) - baseline
        if len(old_socket) != 1:
            raise Partial("OLD_SOCKET_AMBIGUOUS")
        first.challenge()
        if processes.read(paths) != state:
            raise Partial("BASELINE_CHANGED")
        until = time.monotonic() + 180
        while time.monotonic() < until:
            live = sample(processes, expected, uid, "waiting", result)
            state = processes.read(paths)
            new = state["active"]
            if new != old:
                break
            time.sleep(1)
        else:
            raise Partial("NO_NATURAL_SWITCH")
        if set(live) != {old, new} or live[old] != old_process:
            raise Partial("GENERATION_CHANGED")
        current = json.loads(paths.xray_config_file.read_text())
        new_port = next((o["settings"]["servers"][0]["port"] for o in current["outbounds"]
                         if o.get("tag") == node.tag and singbox.bridge_variant(o)), None)
        same_entry = any(n.tag == node.tag and n.probe_port == node.probe_port
                         for n in builder.applied_nodes(current))
        if (not new_port or new_port == port or not same_entry
                or builder.probe_state(current)[0] != password):
            raise Partial("ROUTE_CHANGED")
        baseline = bridge_sockets(live[new], new_port)
        second = Transfer(stack, cfg, node.probe_port, password, parts)
        new_socket = bridge_sockets(live[new], new_port) - baseline
        if len(new_socket) != 1:
            raise Partial("NEW_SOCKET_AMBIGUOUS")
        for edge in (0, 1):
            if (not old_socket <= bridge_sockets(old_process, port)
                    or not new_socket <= bridge_sockets(live[new], new_port)):
                raise Partial("SOCKET_LEFT")
            if edge == 0:
                first.challenge()
                second.challenge()
        result["overlap"] = True
        with ThreadPoolExecutor(2) as pool:
            transfers = [pool.submit(s.finish) for s in (first, second)]
            while not all(t.done() for t in transfers):
                sample(processes, expected, uid, "body", result)
                time.sleep(1)
            result["body_bytes"] = [t.result() for t in transfers]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observe", action="store_true", required=True)
    parser.parse_args()
    sys.path.insert(0, "/opt/xgw/lib")
    summary = {"overlap": None, "body_bytes": None, "permission_observations": {},
               "vanished_samples": 0, "samples": 0}
    try:
        observe(summary)
        summary["result"] = ("PROCESS_SAMPLE_REQUIRES_REVIEW" if summary["permission_observations"]
                             else "INCOMPLETE_SAMPLES" if summary["vanished_samples"]
                             else "OBSERVED")
    except Partial as exc:
        summary["result"] = str(exc)
    except ImportError:
        summary["result"] = "DEPENDENCY_UNAVAILABLE"
    except Exception as exc:
        summary["result"] = type(exc).__name__
    print(json.dumps(summary))
    sys.exit(0 if summary["result"] == "OBSERVED" else 3)
