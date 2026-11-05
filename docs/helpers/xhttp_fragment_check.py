"""T01/T02 на ThinkCentre: каналы загрузки XHTTP и профиль дробления. Печатает только числа.

health  — шлюз в порядке (как в ТЗ c05-scan-bytes);
count   — по применённому конфигу: XHTTP, отдельные каналы загрузки, профиль дробления;
xtest   — копия применённого конфига, где у всех XHTTP с каналом загрузки включён профиль
          дробления установленным кодом, проходит `xray run -test` (рабочий конфиг не трогается);
live    — один XHTTP с внешним каналом загрузки: две загрузки probe.url через временный Xray
          на 127.0.0.1 — без дробления и с дроблением на всех каналах.
"""

import copy
import json
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APPLIED = Path("/etc/xgw/xray/config.json")
XRAY = Path("/opt/xgw/xray/xray")
FRAG = ("fragment", "fragment-split")
XHTTP = ("xhttp", "splithttp")
KEYS = ("xhttpSettings", "splithttpSettings")


def health():
    proc = subprocess.run(["xgw", "status", "--json"], capture_output=True, timeout=180)
    data = json.loads(proc.stdout)
    cap = data.get("capture") or {}
    https = subprocess.run(["curl", "--silent", "--noproxy", "*", "--max-time", "60",
                            "-o", "/dev/null", "-w", "%{http_code}", "https://1.1.1.1/"],
                           capture_output=True, timeout=70)
    return (proc.returncode == 0 and data.get("daemon_down") is False
            and data.get("xray", {}).get("ok") is True and cap.get("mode") == "on"
            and cap.get("blocked") is False and cap.get("loaded") is True
            and https.returncode == 0 and https.stdout.isdigit() and 200 <= int(https.stdout) < 400)


def legs(stream, depth=0):
    found = []
    if depth >= 4 or not isinstance(stream, dict):
        return found
    for key in KEYS:
        settings = stream.get(key)
        if not isinstance(settings, dict):
            continue
        for options in (settings, settings.get("extra")):
            down = options.get("downloadSettings") if isinstance(options, dict) else None
            if isinstance(down, dict):
                found.append(down)
                found.extend(legs(down, depth + 1))
    return found


def sockopt(leg):
    value = leg.get("sockopt")
    return value if isinstance(value, dict) else {}


def alpn(leg):
    tls = leg.get("tlsSettings")
    value = tls.get("alpn") if isinstance(tls, dict) else None
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def h3(leg, network):
    tls = str(leg.get("security") or "").lower() == "tls"
    return network in XHTTP and tls and alpn(leg) == ["h3"]


def external(leg):
    address = str(leg.get("address") or "").strip("[]").lower()
    return not (address in ("localhost", "::1") or address.startswith("127."))


def leg_fits(leg):
    """Канал загрузки, который по правилу Xray идёт по TCP с TLS/REALITY и без чужой цепочки."""
    network = str(leg.get("network") or "xhttp").lower()
    return (external(leg) and str(leg.get("security") or "").lower() in ("tls", "reality")
            and not h3(leg, network) and str(sockopt(leg).get("dialerProxy") or "") in ("", *FRAG))


def servers(config):
    for item in config.get("outbounds") or []:
        tag = str(item.get("tag") or "")
        stream = item.get("streamSettings")
        if tag.startswith(("proxy-", "pool-")) and isinstance(stream, dict):
            yield item, stream


def count(report):
    config = json.loads(APPLIED.read_bytes())
    keys = ("xhttp", "xhttp_h3_exact", "xhttp_h3_among_several", "with_download_legs",
            "legs", "legs_external", "legs_fit", "xhttp_on_profile", "legs_should",
            "legs_fragmented", "legs_mismatch", "legs_external_without_mark")
    stats = dict.fromkeys(keys, 0)
    for _item, stream in servers(config):
        network = str(stream.get("network") or "tcp").lower()
        if network not in XHTTP:
            continue
        stats["xhttp"] += 1
        names = alpn(stream)
        stats["xhttp_h3_exact"] += h3(stream, network)
        stats["xhttp_h3_among_several"] += "h3" in names and len(names) > 1
        top = str(sockopt(stream).get("dialerProxy") or "")
        on_profile = top in FRAG
        stats["xhttp_on_profile"] += on_profile
        found = legs(stream)
        stats["with_download_legs"] += bool(found)
        for leg in found:
            stats["legs"] += 1
            stats["legs_external"] += external(leg)
            stats["legs_fit"] += leg_fits(leg)
            if external(leg) and "mark" not in sockopt(leg):
                stats["legs_external_without_mark"] += 1
            dialer = str(sockopt(leg).get("dialerProxy") or "")
            stats["legs_fragmented"] += dialer in FRAG
            should = on_profile and leg_fits(leg)
            stats["legs_should"] += should
            if (should and dialer != top) or (not should and dialer in FRAG):
                stats["legs_mismatch"] += 1
    report.update(stats)
    return stats["legs_mismatch"] == 0 and stats["legs_external_without_mark"] == 0


def installed():
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config as xconfig
    from xgw.generator import fragment

    cfg, _warnings = xconfig.load(Path("/etc/xgw/config.toml"))
    return cfg, fragment


def xray_test(path):
    proc = subprocess.run([str(XRAY), "run", "-test", "-c", str(path)], capture_output=True,
                          timeout=120)
    return proc.returncode


def xtest(report):
    cfg, fragment = installed()
    config = json.loads(APPLIED.read_bytes())
    forced = 0
    for item, stream in servers(config):
        if legs(stream) and fragment.eligible(item):
            fragment.enable(item)
            forced += 1
    tags = {str(item.get("tag")) for item in config["outbounds"]}
    if forced and "fragment" not in tags:
        config["outbounds"].append(fragment.outbound(cfg))
    report["forced"] = forced
    with tempfile.TemporaryDirectory(prefix="t01-") as folder:
        path = Path(folder) / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        report["xray_test_rc"] = xray_test(path)
    return report["xray_test_rc"] == 0


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch_once(outbound, extra, url):
    port, password = free_port(), secrets.token_urlsafe(12)
    config = {
        "log": {"loglevel": "none"},
        "inbounds": [{"tag": "t01-in", "protocol": "http", "listen": "127.0.0.1", "port": port,
                      "settings": {"accounts": [{"user": "t01", "pass": password}]}}],
        "outbounds": [outbound, *extra],
    }
    with tempfile.TemporaryDirectory(prefix="t01-") as folder:
        path = Path(folder) / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        path.chmod(0o600)
        if xray_test(path) != 0:
            return {"xray_test_rc": 1}
        proc = subprocess.Popen([str(XRAY), "run", "-c", str(path)], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    socket.create_connection(("127.0.0.1", port), 0.2).close()
                    break
                except OSError:
                    time.sleep(0.1)
            run = subprocess.run(
                ["curl", "--silent", "--max-time", "40", "--proxy", f"http://127.0.0.1:{port}",
                 "--proxy-user", f"t01:{password}", "-o", "/dev/null",
                 "-w", "%{http_code} %{size_download} %{time_total}", url],
                capture_output=True, text=True, timeout=60)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    code, size, seconds = (run.stdout.split() + ["0", "0", "0"])[:3]
    return {"curl_rc": run.returncode, "http": int(code or 0), "bytes": int(float(size or 0)),
            "seconds": round(float(seconds or 0), 1)}


def live(report):
    cfg, fragment = installed()
    config = json.loads(APPLIED.read_bytes())
    candidates = [item for item, stream in servers(config)
                  if fragment.eligible(item) and any(leg_fits(leg) for leg in legs(stream))]
    report["candidates"] = len(candidates)
    if not candidates:
        report["reason"] = "NO_XHTTP_WITH_DOWNLOAD_LEG"
        return True
    plain = copy.deepcopy(candidates[0])
    for leg in [plain["streamSettings"], *legs(plain["streamSettings"])]:
        if str(sockopt(leg).get("dialerProxy") or "") in FRAG:
            sockopt(leg).pop("dialerProxy")
    plain["tag"] = "t01-out"
    split = copy.deepcopy(plain)
    fragment.enable(split)
    report["legs_on_profile"] = sum(str(sockopt(leg).get("dialerProxy") or "") == "fragment"
                                    for leg in legs(split["streamSettings"]))
    report["plain"] = fetch_once(plain, [], cfg.probe.url)
    report["fragment"] = fetch_once(split, [fragment.outbound(cfg)], cfg.probe.url)
    ok = report["fragment"].get("http") in range(200, 400) and report["fragment"].get("bytes")
    return bool(ok and report["legs_on_profile"] >= 1)


if __name__ == "__main__":
    record = {}
    try:
        mode = sys.argv[1:]
        if mode == ["health"]:
            passed = health()
            record["health"] = passed
        elif mode == ["count"]:
            passed = count(record)
        elif mode == ["xtest"]:
            passed = xtest(record)
        elif mode == ["live"]:
            passed = live(record)
        else:
            raise ValueError
    except Exception as exc:
        passed = False
        record["reason"] = type(exc).__name__
    print(json.dumps(record, ensure_ascii=False))
    sys.exit(0 if passed else 3)
