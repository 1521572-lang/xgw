"""C07 на ThinkCentre: одно правило пути UDP/TCP. Только чтение, печатает только числа.

health — шлюз в порядке (как в ТЗ c05-scan-bytes);
paths  — серверы из кэша подписок (без сети) по установленному коду: сколько идут по UDP
         по новому правилу и сколько по прежнему (только по имени протокола), сколько из них
         стало UDP из-за транспорта (mKCP, QUIC, XHTTP по HTTP/3), и нет ли сервера, который
         прямая TCP-проверка считает TCP, а путь — UDP.
"""

import json
import subprocess
import sys
from collections import Counter

OLD_UDP = ("hysteria2", "hysteria", "tuic", "wireguard")


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


def network_of(node):
    stream = (node.outbound or {}).get("streamSettings")
    if not isinstance(stream, dict):
        return node.protocol
    return str(stream.get("network") or "tcp").lower()


def paths(report):
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw.daemon import _over_tcp, _transport
    from xgw.generator import fragment
    from xgw.model import raw_to_node
    from xgw.parsers.common import parse_body
    from xgw.paths import Paths

    nodes, bodies, failed = [], 0, 0
    for body in sorted(Paths.from_env().cache_dir.glob("*.body")):
        bodies += 1
        try:
            raws, _meta, _warnings = parse_body(body.read_bytes(), "cache")
        except Exception:
            failed += 1
            continue
        nodes.extend(raw_to_node(raw, "cache") for raw in raws)
    new_udp = [n for n in nodes if _transport(n) == "udp"]
    by_transport = Counter()
    for node in new_udp:
        if node.protocol not in OLD_UDP:
            stream = (node.outbound or {}).get("streamSettings") or {}
            kind = "xhttp-h3" if fragment.xhttp_h3(stream) else network_of(node)
            by_transport[kind] += 1
    report.update(
        bodies=bodies, bodies_failed=failed, servers=len(nodes), udp_new=len(new_udp),
        udp_old=sum(n.protocol in OLD_UDP for n in nodes),
        udp_by_transport=dict(by_transport),
        over_tcp=sum(_over_tcp(n) for n in nodes),
        inconsistent=sum(_over_tcp(n) and _transport(n) == "udp" for n in nodes),
        udp_protocols=dict(Counter(n.protocol for n in new_udp)),
    )
    return report["inconsistent"] == 0 and len(nodes) > 0


if __name__ == "__main__":
    record = {}
    try:
        mode = sys.argv[1:]
        if mode == ["health"]:
            passed = health()
            record["health"] = passed
        elif mode == ["paths"]:
            passed = paths(record)
        else:
            raise ValueError
    except Exception as exc:
        passed = False
        record["reason"] = type(exc).__name__
    print(json.dumps(record, ensure_ascii=False))
    sys.exit(0 if passed else 3)
