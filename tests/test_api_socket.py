"""API Xray — Unix-сокет, а не порт на 127.0.0.1 (четвёртый аудит 0.2.0, ASSUMPTIONS п. 253):
сборка конфига, адрес для `xray api`, переход со старого порта и запуск ядра процессом."""

import json
import socket
import subprocess
from pathlib import Path

import pytest
from test_generator import _build

from xgw import engine
from xgw.generator import builder
from xgw.paths import Paths
from xgw.xraycore import api as api_module
from xgw.xraycore.service import PidfileXrayService


def test_config_api_listens_on_the_socket_by_default_and_on_the_given_path():
    result, cfg, selection = _build()
    assert result.config["api"]["listen"] == builder.API_SOCKET == "/run/xgw-xray/api.sock"
    custom = builder.build(cfg, selection, hosts={}, probe_password="P" * 32,
                           api_listen="/tmp/xgw-root/run/xgw-xray/api.sock")
    assert custom.config["api"]["listen"] == "/tmp/xgw-root/run/xgw-xray/api.sock"
    assert "api_port" not in vars(cfg.xray)  # ключ выведен из употребления


def test_api_address_follows_the_applied_config(tmp_path):
    """Ядро слушает то, что в применённом конфиге: до первого конфига — сокет, после отката на
    last-good прежней версии — старый порт, после нового применения — снова сокет."""
    paths = Paths(root=tmp_path)
    paths.ensure()
    client = engine.make_api(paths, Path("/opt/xgw/xray/xray"))
    socket_address = f"unix://{paths.xray_api_socket}"
    assert client.address() == socket_address
    paths.xray_config_file.write_text(
        json.dumps({"api": {"tag": "api", "listen": "127.0.0.1:10085"}}), encoding="utf-8")
    assert client.address() == "127.0.0.1:10085"
    paths.xray_config_file.write_text(
        json.dumps({"api": {"tag": "api", "listen": str(paths.xray_api_socket)}, "log": {}}),
        encoding="utf-8")
    assert client.address() == socket_address
    paths.xray_config_file.write_text("{не json", encoding="utf-8")
    assert client.address() == socket_address  # не читается — сокет по умолчанию


def test_xray_api_is_called_with_the_socket_address(tmp_path, monkeypatch):
    paths = Paths(root=tmp_path)
    paths.ensure()
    calls = []

    def run(argv, timeout, limit=api_module.MAX_OUTPUT):
        calls.append(argv)
        return 0, "", ""

    monkeypatch.setattr(api_module, "bounded_run", run)
    engine.make_api(paths, Path("/opt/xgw/xray/xray")).balancer_info("auto")
    argv = calls[0]
    assert argv[argv.index("-s") + 1] == f"unix://{paths.xray_api_socket}"


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="нет Unix-сокетов")
def test_process_service_makes_the_socket_dir_and_drops_a_stale_socket(tmp_path):
    """Без systemd каталог сокета создаётся сам, а сокет, оставшийся от убитого процесса,
    убирается: иначе новый Xray не запустится (bind: address already in use)."""
    sock_path = tmp_path / "run" / "xgw-xray" / "api.sock"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"api": {"listen": str(sock_path)}}), encoding="utf-8")
    fake = tmp_path / "xray"
    fake.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    fake.chmod(0o755)
    service = PidfileXrayService(fake, config, tmp_path / "xray.pid", grace=1.0)
    service.start()
    try:
        assert sock_path.parent.is_dir()
    finally:
        service.stop()
    stale = socket.socket(socket.AF_UNIX)
    stale.bind(str(sock_path))
    stale.close()  # файл сокета остался, слушателя нет
    assert sock_path.is_socket()
    service.start()
    try:
        assert not sock_path.exists()
    finally:
        service.stop()


def test_xray_api_output_is_bounded():
    """Пятый аудит, A7: ответ `xray api` приходит от процесса ядра — больше предела он не
    копится в памяти демона: процесс убивается, ApiError. Срок — как у subprocess.run."""
    import sys

    from xgw.xraycore.api import ApiError, bounded_run

    code, out, err = bounded_run(
        [sys.executable, "-c", "import sys; print('ok'); print('w', file=sys.stderr)"], 10)
    assert (code, out.strip(), err.strip()) == (0, "ok", "w")
    with pytest.raises(ApiError, match="больше"):
        bounded_run([sys.executable, "-c", "import sys; sys.stdout.write('x' * 50000)"], 10,
                    limit=1000)
    with pytest.raises(subprocess.TimeoutExpired):
        bounded_run([sys.executable, "-c", "import time; time.sleep(5)"], 0.3)
