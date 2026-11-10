#!/usr/bin/env python3
"""Проверка смены выхода через настоящий API Xray с синтетическим ответом страницы."""

import argparse
import contextlib
import gzip
import json
import logging
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


class Stop(Exception):
    """Причина из фиксированного набора меток."""


def require(condition, stage):
    if not condition:
        raise Stop(stage)


@contextlib.contextmanager
def xray_process(binary, config, *sockets):
    with subprocess.Popen([str(binary), "run", "-c", str(config)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
        try:
            deadline = time.monotonic() + 5
            while proc.poll() is None and time.monotonic() < deadline:
                if all(path.is_socket() for path in sockets):
                    break
                time.sleep(0.05)
            require(all(path.is_socket() for path in sockets) and proc.poll() is None,
                    "xray_start")
            yield proc
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def exercise(paths, binary):
    from xgw import engine
    from xgw.config import Config
    from xgw.daemon import Daemon
    from xgw.generator import builder
    from xgw.watch import youtube
    from xgw.watch.checks import DownloadResult

    paths.ensure()
    control = paths.xray_api_socket
    control.parent.mkdir()
    ingress = paths.run / "probe.sock"
    access = paths.run / "probe.log"
    view = [builder.NodeInfo(fingerprint=letter * 16, tag=f"proxy-{letter}", probe_tag="",
                             probe_port=1, role="proxy") for letter in "ab"]
    first, second = view
    cfg = Config()
    cfg.media.youtube_mode = "best"
    cfg.media.youtube_sign_url = "fixture"
    _, domain = cfg.media.youtube_domains[0].split(":", 1)
    common = {"type": "field", "network": "tcp,udp", "outboundTag": "common",
              "ruleTag": "common-rule"}
    base = {
        "log": {"loglevel": "error", "access": str(access)},
        "api": {"tag": "control", "listen": str(control), "services": ["RoutingService"]},
        "inbounds": [{"tag": "sample", "listen": str(ingress), "protocol": "dokodemo-door",
                      "settings": {"address": domain, "port": 443, "network": "tcp"}}],
        "outbounds": [{"tag": tag, "protocol": "blackhole",
                       "settings": {"response": {"type": "http"}}}
                      for tag in ("common", first.tag, second.tag)],
        "routing": {"rules": [common], "balancers": []},
        "observatory": {"subjectSelector": ["fixture-unused-"]},
    }
    paths.xray_config_file.write_text(json.dumps(base), encoding="utf-8")
    logger = logging.getLogger("youtube-refusal-check")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    wall = time.time()

    def now():
        return wall

    with xray_process(binary, paths.xray_config_file, control, ingress) as proc:
        daemon = Daemon(cfg, paths, xray_bin=binary, logger=logger, wall=now, clock=now)
        with contextlib.closing(daemon.store):
            daemon._prices = lambda: dict.fromkeys((info.fingerprint for info in view), 0)
            records = daemon._youtube_records()
            for node, mbps in zip(view, (50, 20), strict=True):
                records[node.fingerprint] = {"state": youtube.OK, "mbps": mbps, "ts": wall}
            alive = {node.tag: {"alive": True} for node in view}
            applied = base

            def apply(expected, stage):
                nonlocal applied
                daemon._media_step(view, applied, alive, now())
                require(daemon._media_apply(now()), stage + "_apply")
                applied = engine.read_json(paths.xray_config_file)
                require(builder.applied_media(applied) == expected, stage + "_config")
                require(proc.poll() is None, stage + "_process")
                targets = json.loads(daemon.api._run("lsrules"))["rules"]
                require(len(targets) == (2 if expected else 1)
                        and targets[-1].get("ruleTag") == "common-rule"
                        and targets[-1].get("tag") == "common", stage + "_routing")
                offset = access.stat().st_size if access.exists() else 0
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                    stream.settimeout(3)
                    stream.connect(str(ingress))
                    stream.sendall(b"GET / HTTP/1.1\r\n\r\n")
                    require(b"403" in stream.recv(4096), stage + "_probe")
                tag = expected[0] if expected else "common"
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    if access.exists() and access.stat().st_size > offset:
                        break
                    time.sleep(0.05)
                require(access.exists()
                        and f"[sample -> {tag}]".encode() in access.read_bytes()[offset:],
                        stage + "_outbound")

            apply((first.tag,), "baseline")
            print("CHECK baseline=1")
            refusal = gzip.compress(b'{"playabilityStatus":{"status":"LOGIN_REQUIRED"}}')
            result = DownloadResult(True, status=200, body=refusal, downloaded=len(refusal))
            # Подменяем только ответ HTTP, перед настоящим разбором страницы.
            with patch.object(youtube, "http_get_via_proxy", return_value=result) as http:
                for index, node in enumerate(view):
                    wall += 1  # обе смены укладываются внутрь планового hold
                    require(daemon._youtube_sign_step(view, applied, alive, "", wall), "sign_probe")
                    key = youtube.sign_key(cfg.media.youtube_sign_url)
                    require(youtube.sign_sample(records[node.fingerprint], key, wall)
                            == youtube.REFUSE, "sign_refuse")
                    if index == 0:
                        apply((second.tag,), "switch")
                        print("CHECK switched_on_refuse=1")
                    else:
                        apply((), "fallback")
                        print("CHECK common_on_all_refuse=1")
                require(http.call_count == 2, "probe_count")
            events = daemon.store.recent_events(30)
            changes = [event for event in events if event["kind"] == "youtube"
                       and "YouTube потребовал вход" in event["detail"]]
            require(len(changes) == 2, "refusal_events")
            require(daemon._media_wanted(view, alive, (), wall)
                    == ("waiting_for_acceptance", ()), "refusal_state")
            print("CHECK refusal_events=2 xray_alive=1")
    print("RESULT refusal_path_ok")


def main():
    from xgw.paths import Paths

    parser = argparse.ArgumentParser()
    parser.add_argument("--xray", type=Path, default=Paths.from_env({}).xray_bin)
    args = parser.parse_args()
    if not args.xray.is_file():
        print("NOT_RUN xray_missing")
        return 4
    with tempfile.TemporaryDirectory(prefix="xgw-sign-") as temp:
        paths = Paths(Path(temp))
        with patch.dict("os.environ", {"XGW_ROOT": temp, "XGW_XRAY_SERVICE": "process"}):
            exercise(paths, args.xray.resolve())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as exc:
        print("STOP", exc)
        sys.exit(2)
    except Exception:
        print("STOP isolated_check_failed")
        sys.exit(2)
