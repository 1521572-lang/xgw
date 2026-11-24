"""Check the Selective handoff against an isolated, real Xray API."""

import contextlib
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from test_zapret2 import Harness

from xgw import zapret2
from xgw.apply.applier import Applier, ApplySource
from xgw.paths import Paths
from xgw.xraycore.access import endpoint, parse_accepted
from xgw.xraycore.api import ApiClient

XRAY = Path("/opt/xgw/xray/xray")
CLIENT_PORT = 34100
VPN_OUT = "vpn-fixture"
MEDIA = "r1.googlevideo.com"


def require(condition, label):
    if not condition:
        raise RuntimeError(label)
    print(f"OK {label}", flush=True)


def observe_route(log, host, outbound):
    log_size = log.stat().st_size if log.exists() else 0
    with socket.create_connection(("127.0.0.1", CLIENT_PORT), timeout=2) as client:
        local = client.getsockname()
        client.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode())
        with contextlib.suppress(ConnectionError, TimeoutError):
            client.recv(4096)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if log.exists():
            with log.open("rb") as stream:
                stream.seek(log_size)
                complete, _, _ = stream.read().rpartition(b"\n")
            matches = []
            for line in complete.decode("utf-8").splitlines():
                accepted = parse_accepted(line)
                if accepted is None or (accepted.target, accepted.inbound) != (
                    f"{host}:443", "tproxy-in"
                ):
                    continue
                with contextlib.suppress(ValueError):
                    if endpoint(accepted.source) == local:
                        matches.append(accepted.outbound)
            if matches:
                return matches == [outbound]
        time.sleep(0.05)
    return False


def trial(root):
    h = Harness()
    paths = Paths(root)
    os.environ["XGW_ROOT"] = str(root)
    paths.ensure()
    api_socket, access = root / "api.sock", root / "access.log"
    h.cfg.zapret2.probe_port = CLIENT_PORT + 2
    h.cfg.zapret2.youtube_transport_probe = True
    page = "https://www.youtube.com/t/terms"
    h.cfg.zapret2.probe_urls = [page, f"https://{MEDIA}/videoplayback?sig=fixture-old"]
    # Real Xray selects the outbound. Neither synthetic outbound can send traffic.
    zapret2.selected_outbound = lambda: {"tag": zapret2.OUT, "protocol": "blackhole"}
    base = {
        "log": {"access": str(access), "loglevel": "warning"},
        "api": {"tag": "api", "listen": str(api_socket),
                "services": ["HandlerService", "RoutingService"]},
        "inbounds": [
            {"tag": "tproxy-in", "listen": "127.0.0.1", "port": CLIENT_PORT,
             "protocol": "http"},
            {"tag": "probe-fixture", "listen": "127.0.0.1", "port": CLIENT_PORT + 1,
             "protocol": "http", "settings": {"accounts": [{"user": "xgw", "pass": "fixture"}]}},
        ],
        "outbounds": [{"tag": VPN_OUT, "protocol": "blackhole"}],
        "routing": {"rules": [{"type": "field", "network": "tcp,udp", "outboundTag": VPN_OUT}]},
    }
    h.current = zapret2.patch(base, h.cfg, enabled=True)
    paths.xray_config_file.write_text(json.dumps(h.current), encoding="utf-8")
    api = ApiClient(XRAY, config_file=paths.xray_config_file, timeout=3)
    applier = Applier(h.cfg, paths, api, None, xray_bin=XRAY)

    def apply(target, previous):
        outcome = applier.apply_api_only(target, base=previous, source=ApplySource.ZAPRET2_ROUTE)
        if outcome.mode != "api":
            raise RuntimeError(f"xray_api_apply_{outcome.mode}: {outcome.detail}")
        h.current = target
        return True

    with (root / "xray.log").open("wb") as output, subprocess.Popen(
        [str(XRAY), "run", "-c", str(paths.xray_config_file)], stdout=output, stderr=output,
    ) as core:
        try:
            deadline = time.monotonic() + 5
            while not api_socket.is_socket() and core.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            if not api_socket.is_socket() or core.poll() is not None:
                raise RuntimeError((root / "xray.log").read_text(encoding="utf-8"))
            require(zapret2.OUT in api.list_outbounds(), "xray_ready")
            h.apply = apply
            budget = h.controller.store
            for success in (True, False):
                require(observe_route(access, MEDIA, zapret2.OUT), "previous_client_rule_live")
                h.cfg.zapret2.probe_urls[1] = f"https://{MEDIA}/videoplayback?sig=fixture-{success}"
                h.controller = zapret2.Controller(budget, h.runtime)

                def probe(*_args, passed=success):
                    require(observe_route(access, MEDIA, VPN_OUT), "client_uses_vpn_during_probe")
                    return passed

                h.controller.probe = probe
                for seconds in (0, 1, 2):
                    h.step(seconds)
                expected = zapret2.OUT if success else VPN_OUT
                label = "accepted_new_probe" if success else "failed_new_probe_stays_on_vpn"
                require(zapret2.active(h.current) == success
                        and observe_route(access, MEDIA, expected), label)
                require(observe_route(access, "unrelated.example.test", VPN_OUT), "other_route_stable")
                h.controller.close()
            require(core.poll() is None and not paths.api_dirty_file.exists(), "same_core_clean_api")
        finally:
            if core.poll() is None:
                core.terminate()
                try:
                    core.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    core.kill()


def main():
    require(
        os.geteuid() == 0
        and not os.path.samefile("/proc/self/ns/net", "/proc/1/ns/net")
        and socket.if_nameindex() == [(1, "lo")],
        "fresh_network_namespace",
    )
    require(XRAY.is_file() and os.access(XRAY, os.X_OK), "installed_xray_binary")
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True, timeout=5)
    with tempfile.TemporaryDirectory(prefix="xgw-iso-xray.") as folder:
        trial(Path(folder))


if __name__ == "__main__":
    main()
