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
    guard.save(directory / "baseline.json", {
        "ready": chosen is not None, "baseline_healthy": healthy,
        "target": chosen, "results": results,
        "monotonic": time.monotonic(),
        "sampler_sha256": hashlib.sha256(HERE.read_bytes()).hexdigest(),
    })
    print(json.dumps({"ready_for_enable": chosen is not None,
                      "baseline_healthy": healthy, "baseline": results}))


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


def loaded():
    code = ("import sys,json; sys.path.insert(0,'/opt/xgw/lib'); "
            "from xgw import config; from xgw.paths import Paths; "
            "from xgw.net.capture import capture_for; p=Paths.from_env(); "
            "c,_=config.load(p.config_file); "
            "print(json.dumps({'loaded':capture_for(c,p).loaded()}))")
    try:
        check = subprocess.run([sys.executable, "-I", "-c", code], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=6, check=False)
        if check.returncode == 0:
            return json.loads(check.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {"loaded": "UNKNOWN"}


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
    events.append({"stage": "loaded", **loaded()})
    guard.save(directory / "on-observations.json", events)
    for marked in (False, True):
        events.append({"stage": "https", **probe(directory, base["target"], marked)})
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
    elif mode == "report":
        for name in ("baseline.json", "enable-result.json", "on-observations.json"):
            if (directory / name).exists():
                print(json.dumps({name: read_json(directory / name)}))
    else:
        raise SystemExit("context|baseline|run|report DIR")


if __name__ == "__main__":
    main()
