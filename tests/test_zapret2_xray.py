"""Один настоящий Xray на loopback, без systemd, перехвата и запросов в интернет."""

import os
import socket
import subprocess
from pathlib import Path

import pytest

from xgw.apply.applier import Applier
from xgw.config import Config
from xgw.generator import builder
from xgw.paths import Paths
from xgw.xraycore.api import ApiClient, ApiError
from xgw.xraycore.metrics import fetch_metrics


def test_standalone_real_xray_api_and_metrics(tmp_path):
    executable = os.environ.get("XGW_STANDALONE_XRAY")
    if not executable:
        pytest.skip("нужен явно заданный XGW_STANDALONE_XRAY")
    binary = Path(executable)
    assert binary.is_file()
    cfg = Config()
    cfg.zapret2.mode = "standalone"
    cfg.capture.local = cfg.capture.lan = False
    reservations = [socket.socket() for _ in range(3)]
    try:
        for sock in reservations:
            sock.bind(("127.0.0.1", 0))
        cfg.xray.socks_port, cfg.xray.http_port, cfg.xray.metrics_port = (
            sock.getsockname()[1] for sock in reservations)
    finally:
        for sock in reservations:
            sock.close()
    paths = Paths(tmp_path)
    paths.ensure()
    api_socket = tmp_path / "api.sock"
    target = builder.build(cfg, builder.Selection(), hosts={},
                           api_listen=str(api_socket)).config
    api = ApiClient(binary, config_file=paths.xray_config_file, timeout=1)

    class Process:
        child = None
        restarts = 0

        def restart(self):
            self.stop()
            self.restarts += 1
            self.child = subprocess.Popen(
                [str(binary), "run", "-c", str(paths.xray_config_file)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log)

        def stop(self):
            if self.child is not None:
                self.child.terminate()
                try:
                    self.child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.child.kill()
                    self.child.wait(timeout=5)
                self.child = None

    with (tmp_path / "core.log").open("w") as log:
        service = Process()
        try:
            applier = Applier(cfg, paths, api, service, xray_bin=binary, wait_seconds=5)
            outcome = applier.apply(target, urgent=True)
            assert outcome.mode == "restart", outcome.detail
            assert service.restarts == 1
            assert "xgw-without-vpn" in api.list_outbounds()
            with pytest.raises(ApiError):
                api.balancer_info("auto")
            assert isinstance(fetch_metrics(cfg.xray.metrics_port), dict)
            assert applier.apply(target, urgent=True).mode == "unchanged"
            assert service.restarts == 1
        finally:
            service.stop()
