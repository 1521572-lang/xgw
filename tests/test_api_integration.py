"""Интеграционный тест Xray API на живом процессе.

Запускается только при XGW_XRAY_BIN=<путь к xray> (dev/стенд), поднимает
реальный Xray с api/metrics и прогоняет ado/adi/adrules/rmo/rmi/bi/lso/lsi.
Подтверждает фактический синтаксис CLI (пункт «проверить на месте», раздел 4).
"""

import base64
import json
import os
import socket
import time
from pathlib import Path

import pytest

from xgw.xraycore.api import ApiClient, ApiError
from xgw.xraycore.service import ProcessXrayService

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")

pytestmark = pytest.mark.skipif(
    not XRAY_BIN or not Path(XRAY_BIN).exists(),
    reason="нет XGW_XRAY_BIN — интеграционный тест API пропущен",
)

FAKE_PBK = base64.urlsafe_b64encode(b"\x11" * 32).rstrip(b"=").decode()


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _outbound(tag: str, port: int) -> dict:
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": "127.0.0.1",
                    "port": port,
                    "users": [
                        {
                            "id": "11111111-2222-3333-4455-666666666661",
                            "encryption": "none",
                        }
                    ],
                }
            ]
        },
        "streamSettings": {"network": "tcp", "security": "reality",
                           "realitySettings": {"serverName": "www.example.org",
                                               "publicKey": FAKE_PBK}},
    }


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    api_port, metrics_port, socks_port = _free_port(), _free_port(), _free_port()
    config = {
        "log": {"loglevel": "warning"},
        "api": {
            "tag": "api",
            "listen": f"127.0.0.1:{api_port}",
            "services": ["HandlerService", "RoutingService", "StatsService"],
        },
        "inbounds": [
            {"tag": "socks-in", "protocol": "socks", "listen": "127.0.0.1",
             "port": socks_port, "settings": {"udp": False}},
        ],
        "outbounds": [
            _outbound("proxy-test-aaaa", 443),
            _outbound("proxy-test-bbbb", 443),
            {"tag": "direct", "protocol": "freedom"},
        ],
        "routing": {
            "rules": [{"type": "field", "network": "tcp,udp", "outboundTag": "direct"}],
            "balancers": [
                {"tag": "auto", "selector": ["proxy-"], "strategy": {"type": "random"}}
            ],
        },
    }
    _ = metrics_port
    config_path = tmp_path_factory.mktemp("xgw-itest") / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    service = ProcessXrayService(Path(XRAY_BIN), config_path, grace=10)
    service.start()
    client = ApiClient(Path(XRAY_BIN), server=f"127.0.0.1:{api_port}", timeout=5)
    # ждём готовности API
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            client.balancer_info("auto")
            break
        except ApiError:
            time.sleep(0.3)
    else:
        service.stop()
        pytest.fail("API не поднялся за 10 с")
    yield client
    service.stop()


def test_balloancer_info(runtime):
    info = runtime.balancer_info("auto")
    assert isinstance(info, str) and info.strip()


def test_add_and_remove_outbound_and_inbound(runtime):
    runtime.add_outbounds([_outbound("proxy-test-cccc", 8443)])
    listing = runtime.list_outbounds()
    assert "proxy-test-cccc" in listing

    probe = {
        "tag": "probe-test-cccc",
        "protocol": "http",
        "listen": "127.0.0.1",
        "port": _free_port(),
        "settings": {"accounts": [{"user": "xgw", "pass": "x" * 32}]},
    }
    runtime.add_inbounds([probe])
    assert "probe-test-cccc" in runtime.list_inbounds()

    runtime.remove_outbound("proxy-test-cccc")
    assert "proxy-test-cccc" not in runtime.list_outbounds()
    runtime.remove_inbound("probe-test-cccc")
    assert "probe-test-cccc" not in runtime.list_inbounds()


def test_adrules_replaces_routing(runtime):
    routing = {
        "rules": [
            {
                "type": "field",
                "ruleTag": "xgw-test-direct",
                "inboundTag": ["socks-in"],
                "outboundTag": "direct",
            }
        ],
        "balancers": [
            {"tag": "auto", "selector": ["proxy-"], "strategy": {"type": "random"},
             "fallbackTag": "proxy-test-aaaa"}
        ],
    }
    runtime.replace_routing(routing)
    rules = runtime._run("lsrules")
    # adrules заменил правила: наш ruleTag виден, балансировщик жив
    assert "xgw-test-direct" in rules
    assert runtime.balancer_info("auto").strip()
