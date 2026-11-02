"""Один enable и автономные безопасные агрегаты внутри независимого окна25с."""
from __future__ import annotations

import hashlib
import http.client
import importlib.util
import io
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve()
SPEC = importlib.util.spec_from_file_location("fixed_guard", HERE.with_name("wave3_safety.py"))
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
MIN_BYTES = 32 * 1024 + 1


def read_json(path):
    return json.loads(path.read_text())


def timeout(sock, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("deadline")
    sock.settimeout(remaining)


def consume(response, sock, deadline, result):
    result["phase"] = "body"
    while result["bytes"] < MIN_BYTES:
        timeout(sock, deadline)
        data = response.read1(min(8192, MIN_BYTES - result["bytes"]))
        if not data:
            result["outcome"] = "short_body"
            return
        result["bytes"] += len(data)
    result["outcome"] = "prefix_ok"


def fetch(directory, index, marked):
    snapshot = read_json(directory / "snapshot.json")
    target = read_json(directory / "probe-plan.json")[index]
    result = {"target": index, "path": "marked" if marked else "plain",
              "phase": "tcp", "bytes": 0, "outcome": "unknown"}
    began = time.monotonic()
    deadline = began + 3
    try:
        context = ssl.create_default_context()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as raw:
            if marked:
                raw.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, snapshot["bypass_mark"])
            timeout(raw, deadline)
            raw.connect(tuple(target["address"]))  # DNS уже разрешён в off-базе
            result["phase"] = "tls"
            with context.wrap_socket(raw, server_hostname=target["host"],
                                     do_handshake_on_connect=False) as stream:
                timeout(stream, deadline)
                stream.do_handshake()
                result["phase"] = "headers"
                timeout(stream, deadline)
                host = target["host"] + (":" + str(target["port"]) if target["port"] != 443 else "")
                request = (f"GET {target['path']} HTTP/1.1\r\nHost: {host}\r\n"
                           f"User-Agent: {snapshot['probe_user_agent']}\r\n"
                           "Accept-Encoding: identity\r\nConnection: close\r\n\r\n")
                stream.sendall(request.encode("ascii"))
                response = http.client.HTTPResponse(stream)
                response.begin()
                result["status"] = response.status
                if response.status != 200:
                    result["outcome"] = "http_status"
                elif response.getheader("Content-Encoding", "identity").lower() != "identity":
                    result["outcome"] = "content_encoding"
                else:
                    consume(response, stream, deadline, result)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        if isinstance(exc, http.client.IncompleteRead) and result["phase"] == "body":
            result["bytes"] += len(exc.partial)
        result["outcome"] = type(exc).__name__  # без URL/IP/текста исключения
    result["seconds"] = round(time.monotonic() - began, 3)
    return result


def probe(directory, index, marked):
    # Абсолютный внешний предел включает TLS/медленные заголовки и импорты.
    try:
        completed = subprocess.run([sys.executable, "-I", str(HERE), "fetch", str(directory),
                                    str(index), str(int(marked))], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, timeout=4, check=False)
        if completed.returncode == 0:
            return json.loads(completed.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {"target": index, "path": "marked" if marked else "plain",
            "outcome": "worker_deadline_or_error", "phase": "unknown", "bytes": None}


def baseline(directory):
    snapshot = read_json(directory / "snapshot.json")
    if read_json(Path(snapshot["capture_state"])).get("enabled") is not False:
        raise SystemExit("STOP: исходный режим не off")
    targets = []
    for url in snapshot["probe_urls"]:
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
                continue
            host = parsed.hostname.encode("idna").decode("ascii")
            port = parsed.port or 443
            resolver = ("import json,socket,sys; print(json.dumps(socket.getaddrinfo("
                        "sys.argv[1],int(sys.argv[2]),socket.AF_INET,socket.SOCK_STREAM)))")
            raw = subprocess.check_output([sys.executable, "-I", "-c", resolver, host, str(port)],
                                          stderr=subprocess.DEVNULL, timeout=3)
            address = next(entry[4] for entry in json.loads(raw)
                           if ipaddress.ip_address(entry[4][0]).is_global)
            path = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
            if any(char in host + path + snapshot["probe_user_agent"] for char in "\r\n"):
                continue
            targets.append({"host": host, "port": port, "address": address, "path": path})
        except (AttributeError, ValueError, OSError, StopIteration, subprocess.SubprocessError):
            continue
    guard.save(directory / "probe-plan.json", targets)  # приватные URL/IP, не публиковать
    results = []
    chosen = None
    healthy = False
    for index in range(len(targets)):
        pair = [probe(directory, index, marked) for marked in (False, True)]
        results.extend(pair)
        if all(item["outcome"] == "prefix_ok" for item in pair):
            chosen = index
            healthy = True
            break
    if chosen is None and targets:
        chosen = 0  # off-body может быть уже заблокирован ТСПУ; сравнение останется ограниченным
    base = {
        "ready": False, "baseline_healthy": healthy,
        "target": chosen, "results": results,
        "monotonic": time.monotonic(),
        "sampler_sha256": hashlib.sha256(HERE.read_bytes()).hexdigest(),
    }
    guard.save(directory / "baseline.json", base)
    diagnostic = loaded(directory)
    guard.save(directory / "off-diagnostic.json", diagnostic)
    base.update(ready=chosen is not None and diagnostic_ready(diagnostic),
                diagnostic_gate=diagnostic_ready(diagnostic))
    guard.save(directory / "baseline.json", base)
    print(json.dumps({"ready_for_enable": base["ready"],
                      "baseline_healthy": healthy, "baseline": results,
                      "off_diagnostic": diagnostic}))


def permit(directory):
    snapshot = read_json(directory / "snapshot.json")
    base = read_json(directory / "baseline.json")
    age = time.monotonic() - base["monotonic"]
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if (not base.get("ready") or not 0 <= age <= 300 or snapshot["boot"] != boot
            or base.get("sampler_sha256") != hashlib.sha256(HERE.read_bytes()).hexdigest()):
        raise SystemExit("STOP: нет свежей проверенной off-базы или изменён sampler")
    return base


def observe(directory):
    stream = io.StringIO()
    with redirect_stdout(stream):
        guard.observe(directory)
    value = json.loads(stream.getvalue())
    try:
        check = subprocess.run(["nft", "list", "table", "inet", "xgw_guard"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=1, check=False)
        value["guard_present"] = check.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        value["guard_present"] = None
    return value


def diagnostic_ready(value):
    """Отсутствующий IPv4 listener/неизвестный контекст — STOP до enable, не настройка сети."""
    if (value.get("schema") != 1 or value.get("requested_mode") != "off"
            or value.get("effective_mode") != "off" or value.get("configured_local") is not True
            or value.get("inbound_problem_present") is not False or value.get("loaded") is False
            or value.get("mismatch_present") is not False
            or value.get("loaded_reason") not in ("measured", "capture_unknown",
                                                  "child_deadline", "child_error")
            or not any("route_type" in item for item in value.get("routes", {}).values())
            or value.get("capture_method") not in ("tproxy", "tun")):
        return False
    if value["capture_method"] == "tproxy":
        listener = value.get("listener", {})
        return listener.get("tcp_read") is True and (
            listener.get("ipv4_any") is True or listener.get("ipv4_loopback") is True)
    return True


def route_summary(route, interfaces, tun_name, tables):
    """Только класс lookup; ни адресов, ни имён интерфейсов, ни чужих table ID."""
    device = route.get("dev")
    role = next((key for key, value in interfaces.items() if device and device == value), None)
    if device == "lo":
        role = "loopback"
    elif device and device == tun_name:
        role = "tun"
    table = str(route.get("table", "main"))
    table_role = next((key for key, value in tables.items() if table == str(value)), None)
    kind = route.get("type", "unicast")
    return {"device_role": role or "other_or_absent",
            "route_type": kind if kind in ("local", "unicast", "blackhole", "unreachable",
                                            "prohibit", "throw") else "other",
            "table_role": table_role or ("main" if table in ("main", "254") else "other")}


def listener_summary(port, root=Path("/proc/net")):
    """LISTEN в текущем netns; наличие сокета не доказывает PID/работу TPROXY."""
    result = {}
    for name, roles in (("tcp", {"00000000": "ipv4_any", "0100007F": "ipv4_loopback"}),
                        ("tcp6", {"0" * 32: "ipv6_any",
                                  "0" * 24 + "01000000": "ipv6_loopback"})):
        try:
            labels = {value: False for value in roles.values()}
            labels[name + "_other_address"] = False
            for line in (root / name).read_text().splitlines()[1:]:
                fields = line.split()
                if len(fields) < 4 or fields[3] != "0A":
                    continue
                address, raw_port = fields[1].split(":")
                if int(raw_port, 16) == port:
                    labels[roles.get(address, name + "_other_address")] = True
            result.update(labels)
            result[name + "_read"] = True
        except (OSError, ValueError):
            result[name + "_read"] = False
    return result


def kernel(directory):
    """Read-only child: сохраняет быстрые факты ДО потенциально медленного loaded()."""
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config
    from xgw.net.capture import capture_for
    from xgw.paths import Paths

    path = directory / "kernel-diagnostic.json"
    value = {"schema": 1, "loaded": None, "loaded_reason": "pending",
             "phase": "config", "routes": {}}
    guard.save(path, value)
    paths = Paths.from_env()
    cfg, _ = config.load(paths.config_file)
    capture = capture_for(cfg, paths)
    problem = capture.inbound_problem()
    mode = capture.mode()
    state = capture._state()
    value.update(
        phase="fast_facts", capture_method="tun" if cfg.capture.tun else "tproxy",
        configured_local=cfg.capture.local, configured_lan=cfg.capture.lan,
        requested_mode=mode,
        effective_mode=capture.hold_mode() if mode == "on" and problem else mode,
        inbound_problem_present=bool(problem), mismatch_present=bool(state.get("mismatch")),
        listener=listener_summary(cfg.capture.tproxy_port),
    )
    guard.save(path, value)
    snapshot = read_json(directory / "snapshot.json")
    chosen = read_json(directory / "baseline.json")["target"]
    target = read_json(directory / "probe-plan.json")[chosen]
    for label, mark in (("unmarked", 0), ("proxy", cfg.capture.mark_proxy),
                        ("bypass", cfg.capture.mark_bypass)):
        try:
            result = subprocess.run(
                ["ip", "-4", "-j", "route", "get", target["address"][0], "mark", str(mark),
                 "uid", "0", "ipproto", "tcp", "dport", str(target["port"])],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=0.7, check=False)
            rows = json.loads(result.stdout) if result.returncode == 0 else []
            summary = route_summary(rows[0], snapshot["interfaces"], cfg.capture.tun_name,
                                    {"tproxy": cfg.capture.route_table,
                                     "tun": cfg.capture.tun_route_table}) if rows else {
                                         "query": "nonzero_or_empty", "rc": result.returncode}
        except (OSError, ValueError, IndexError, TypeError, subprocess.TimeoutExpired):
            summary = {"query": "deadline_or_error"}
        value["routes"][label] = summary
        value["phase"] = "routes"
        guard.save(path, value)
    value.update(phase="loaded", loaded_reason="pending_loaded")
    guard.save(path, value)
    answer = capture.loaded()
    value.update(phase="complete", loaded=answer if type(answer) is bool else None,
                 loaded_reason="measured" if type(answer) is bool else "capture_unknown")
    guard.save(path, value)


def loaded(directory):
    path = directory / "kernel-diagnostic.json"
    guard.save(path, {"schema": 1, "loaded": None, "loaded_reason": "pending_child"})
    reason = "child_error"
    rc = None
    try:
        check = subprocess.run([sys.executable, "-I", str(HERE), "kernel", str(directory)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=4, check=False)
        rc = check.returncode
        reason = "invalid_result" if rc == 0 else "child_error"
    except subprocess.TimeoutExpired:
        reason = "child_deadline"
    except OSError:
        reason = "spawn_error"
    try:
        value = read_json(path)
        if not isinstance(value, dict) or value.get("schema") != 1:
            raise ValueError("schema")
    except (OSError, ValueError):
        value = {"schema": 1}
        reason = "invalid_result"
    if type(value.get("loaded")) is not bool:
        value["loaded"] = None
        if not (rc == 0 and value.get("loaded_reason") == "capture_unknown"):
            value["loaded_reason"] = reason
    else:
        value["loaded_reason"] = "measured"
    value["child_rc"] = rc
    return value


def in_job():
    return any(line.rsplit(":", 1)[-1].strip().endswith("/" + guard.JOB)
               for line in Path("/proc/self/cgroup").read_text().splitlines())


def run(directory):
    base = permit(directory)  # до единственного мутирующего действия
    if not in_job():
        raise SystemExit("STOP: enable разрешён только из отслеживаемого job-unit")
    status = read_json(directory / "status.json")
    if (status.get("state") != "armed" or status.get("kind") != "fixed"
            or status.get("dry") is not False or status.get("deadline", 0) - time.monotonic() < 1
            or guard.call(["systemctl", "is-active", "--quiet", guard.SAFETY], 1) != 0):
        raise SystemExit("STOP: независимое окно не armed/active")
    snapshot = read_json(directory / "snapshot.json")
    if read_json(Path(snapshot["capture_state"])).get("enabled") is not False:
        raise SystemExit("STOP: перед опытом нужен off")
    events = [{"stage": "before_enable", "facts": observe(directory)}]
    guard.save(directory / "on-observations.json", events)
    began = time.monotonic()
    try:
        result = subprocess.run(["/usr/local/bin/xgw", "enable"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=18, check=False)
        guard.atomic(directory / "enable-cli.log", result.stdout)
        rc = result.returncode
    except subprocess.TimeoutExpired as exc:
        guard.atomic(directory / "enable-cli.log", exc.output or b"")
        rc = None
    guard.save(directory / "enable-result.json", {
        "rc": rc, "seconds": round(time.monotonic() - began, 3),
    })
    events.append({"stage": "after_enable", "facts": observe(directory)})
    guard.save(directory / "on-observations.json", events)
    if rc != 0:
        return 2
    # Три независимых read-only задачи; сохранять каждый готовый результат немедленно.
    # Вся группа — внутри JOB cgroup, поэтому rollback прекращает и оставшиеся дочерние.
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks = {pool.submit(loaded, directory): "loaded"}
        tasks.update({pool.submit(probe, directory, base["target"], marked): "https"
                      for marked in (False, True)})
        for future in as_completed(tasks):
            events.append({"stage": tasks[future], **future.result()})
            guard.save(directory / "on-observations.json", events)
    events.append({"stage": "after_https", "facts": observe(directory)})
    guard.save(directory / "on-observations.json", events)
    return 0  # выполнен сбор; это не автоматический PASS сети


def main():
    if os.geteuid() != 0:
        raise SystemExit("нужен sudo")
    mode, directory = sys.argv[1], Path(sys.argv[2]).resolve()
    if directory.stat().st_uid != 0 or directory.stat().st_mode & 0o077:
        raise SystemExit("STOP: нужен root-каталог0700")
    if mode == "context":
        verified = in_job()
        print(json.dumps({"tracked_job_context": verified, "euid_root": True}))
        raise SystemExit(0 if verified else 3)
    elif mode == "baseline":
        baseline(directory)
    elif mode == "fetch":
        print(json.dumps(fetch(directory, int(sys.argv[3]), bool(int(sys.argv[4])))))
    elif mode == "run":
        raise SystemExit(run(directory))
    elif mode == "kernel":
        kernel(directory)
    elif mode == "report":
        for name in ("baseline.json", "off-diagnostic.json", "enable-result.json",
                     "on-observations.json"):
            if (directory / name).exists():
                print(json.dumps({name: read_json(directory / name)}))
    else:
        raise SystemExit("context|baseline|run|report DIR; kernel — внутренний read-only child")


if __name__ == "__main__":
    main()
