"""Применение конфига на живом Xray: генератор → Applier → `xray api`.

Запускается только при XGW_XRAY_BIN=<путь к xray>. Проверяет то, что нельзя
проверить заглушками: поведение самого ядра при замене outbound, повторном
ado, вызове `bi` без тега и перезапуске с ожиданием готовности.
"""

import contextlib
import copy
import datetime
import http.server
import json
import os
import threading
import time
from pathlib import Path

import links
import pytest
from ports import free_port

from xgw.apply.applier import Applier
from xgw.config import Config
from xgw.generator import validate
from xgw.generator.builder import API_SOCKET, build, select_nodes
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths
from xgw.xraycore import binary
from xgw.xraycore.api import ApiClient, ApiError
from xgw.xraycore.service import ProcessXrayService

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")

pytestmark = pytest.mark.skipif(
    not XRAY_BIN or not Path(XRAY_BIN).exists(),
    reason="нет XGW_XRAY_BIN — тест применения на живом Xray пропущен",
)


def _live_config(cfg: Config, api_listen: str = API_SOCKET) -> dict:
    """Конфиг генератора без того, чего нет вне шлюза: TPROXY-inbound требует
    Linux и CAP_NET_ADMIN, правила geoip — файла geoip.dat рядом с бинарником."""
    raws, _, _ = parse_links_text("\n".join(links.FULL_LINKS), "test")
    nodes = [raw_to_node(raw, "test") for raw in raws]
    config = build(cfg, select_nodes(nodes, cfg), hosts={}, probe_password="P" * 32,
                   api_listen=api_listen).config
    config["inbounds"] = [i for i in config["inbounds"] if i["tag"] != "tproxy-in"]
    config["routing"]["rules"] = [
        rule
        for rule in config["routing"]["rules"]
        if rule.get("inboundTag") != ["tproxy-in"]
        and not any(str(value).startswith("geoip:") for value in rule.get("ip", []))
    ]
    # Пробы наружу в тесте не нужны: адрес заведомо недоступен, сети тест не трогает.
    config["burstObservatory"]["pingConfig"]["destination"] = "http://127.0.0.1:9/none"
    return config


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.apply.restart_window = "00:00-00:01"
    cfg.xray.metrics_port = free_port()
    cfg.xray.socks_port, cfg.xray.http_port = free_port(), free_port()
    cfg.xray.probe_port_base = free_port()
    # API — сокет, как на шлюзе (ASSUMPTIONS п. 253); каталог у службы создаёт systemd.
    paths.xray_api_socket.parent.mkdir(parents=True, exist_ok=True)
    base = _live_config(cfg, str(paths.xray_api_socket))
    paths.xray_config_file.write_text(json.dumps(base), encoding="utf-8")
    service = ProcessXrayService(Path(XRAY_BIN), paths.xray_config_file)
    api = ApiClient(Path(XRAY_BIN), server=f"unix://{paths.xray_api_socket}", timeout=5)
    service.start()
    deadline = time.monotonic() + 15
    while True:
        try:
            api.balancer_info("auto")
            break
        except ApiError:
            if time.monotonic() > deadline:
                service.stop()
                pytest.fail("API не поднялся за 15 с")
            time.sleep(0.3)
    applier = Applier(
        cfg, paths, api, service, xray_bin=Path(XRAY_BIN),
        now_fn=lambda: datetime.time(12, 0),  # вне окна перезапуска
    )
    yield applier, api, base
    service.stop()


def test_installed_version_and_validation():
    version = binary.installed_version(XRAY_BIN)
    assert version is not None and version >= binary.MIN_VERSION
    cfg = Config()
    cfg.filters.max_members = 2
    verdict, output = validate.validate_config(_live_config(cfg), Path(XRAY_BIN))
    assert verdict is True, output


def test_core_facts_the_code_relies_on(live):
    """Поведение ядра, на которое опираются Applier и diff."""
    _applier, api, base = live
    api.balancer_info("auto")
    with pytest.raises(ApiError):  # поэтому готовность проверяется по `bi auto`
        api.balancer_info()
    with pytest.raises(ApiError):  # поэтому после ошибки API путь API закрыт до перезапуска
        api.add_outbounds([base["outbounds"][0]])


def test_apply_through_api_then_restart(live):
    applier, api, base = live
    member = base["outbounds"][0]["tag"]

    # тот же тег с другим параметром + новый запасной + новый домен в dns.hosts
    changed = copy.deepcopy(base)
    stream = changed["outbounds"][0]["streamSettings"]
    key = "realitySettings" if "realitySettings" in stream else "tlsSettings"
    stream.setdefault(key, {})["serverName"] = "changed.example.org"
    spare = copy.deepcopy(changed["outbounds"][1])
    spare["tag"] = "spare-zz-ffff"
    changed["outbounds"].insert(2, spare)
    changed["dns"]["hosts"]["new.example.com"] = ["203.0.113.98"]

    outcome = applier.apply(changed)
    assert outcome.mode == "api", outcome
    assert f"rmo+ado: {member}" in outcome.ops and "ado: spare-zz-ffff" in outcome.ops
    listing = api.list_outbounds()
    assert "spare-zz-ffff" in listing and "changed.example.org" in listing
    assert applier.apply(changed).mode == "unchanged"

    # удаление запасного — тоже через API
    removed = copy.deepcopy(changed)
    removed["outbounds"] = [o for o in removed["outbounds"] if o["tag"] != "spare-zz-ffff"]
    assert applier.apply(removed).mode == "api"
    assert "spare-zz-ffff" not in api.list_outbounds()

    # policy требует перезапуска: вне окна откладывается, с --now выполняется
    restart = copy.deepcopy(removed)
    restart["policy"]["levels"]["0"]["connIdle"] = 300
    assert applier.apply(restart).mode == "restart_deferred"
    done = applier.apply(restart, force_now=True)
    assert done.mode == "restart", done
    assert "changed.example.org" in api.list_outbounds()  # ядро поднялось с новым конфигом

    # невалидный конфиг отклоняется, ядро продолжает работать
    broken = copy.deepcopy(restart)
    broken["outbounds"][0]["streamSettings"]["network"] = "nonexistent"
    assert applier.apply(broken, force_now=True).mode == "rejected"
    api.balancer_info("auto")


def test_unsupported_outbounds_are_found():
    """Транспорт h2 и шифр rc4-md5 Xray не принимает; поля плагина ss — молча игнорирует."""
    uuid = "11111111-2222-3333-4455-666666666661"
    vnext = {"vnext": [{"address": "203.0.113.1", "port": 443,
                        "users": [{"id": uuid, "encryption": "none"}]}]}

    def shadowsocks(method: str, **extra) -> dict:
        server = {"address": "203.0.113.1", "port": 8388, "method": method, "password": "pw"}
        return {"protocol": "shadowsocks", "settings": {"servers": [{**server, **extra}]}}

    outbounds = [
        {"tag": "proxy-nl-aaaa", "protocol": "vless", "settings": vnext,
         "streamSettings": {"network": "tcp", "security": "tls"}},
        {"tag": "spare-de-bbbb", "protocol": "vless", "settings": vnext,
         "streamSettings": {"network": "h2", "security": "tls"}},
        {"tag": "spare-us-cccc", **shadowsocks("rc4-md5")},
        {"tag": "spare-fr-dddd", **shadowsocks("aes-256-gcm", plugin="obfs-local")},
    ]
    invalid = validate.find_invalid_outbounds(outbounds, Path(XRAY_BIN))
    assert sorted(invalid) == ["spare-de-bbbb", "spare-us-cccc"]
    # в причине — суть ошибки, без пути к временному файлу
    assert all(reason and ".json" not in reason for reason in invalid.values())


def test_media_balancer_selects_only_its_server(tmp_path):
    """п. 348, настоящий Xray: балансировщик с полным тегом выбирает его одного, добавляется и
    меняется через API, без перезапуска; основной балансировщик видит всех."""
    handler = type("Ok", (http.server.BaseHTTPRequestHandler,), {
        "do_GET": lambda self: (self.send_response(204), self.end_headers()),
        "log_message": lambda self, *args: None,
    })
    origin = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=origin.serve_forever, daemon=True).start()
    socket_path = tmp_path / "api.sock"
    config = {
        "log": {"loglevel": "warning"},
        "api": {"tag": "api", "listen": str(socket_path),
                "services": ["HandlerService", "RoutingService", "StatsService"]},
        "inbounds": [{"tag": "http-in", "protocol": "http", "listen": "127.0.0.1",
                      "port": free_port()}],
        "outbounds": [{"tag": tag, "protocol": "freedom"}
                      for tag in ("proxy-de-aaaa", "proxy-nl-bbbb")],
        "routing": {"rules": [{"type": "field", "network": "tcp,udp", "balancerTag": "auto"}],
                    "balancers": [{"tag": "auto", "selector": ["proxy-"],
                                   "strategy": {"type": "leastPing"},
                                   "fallbackTag": "proxy-de-aaaa"}]},
        "burstObservatory": {"subjectSelector": ["proxy-"], "pingConfig": {
            "destination": f"http://127.0.0.1:{origin.server_address[1]}/", "connectivity": "",
            "interval": "1s", "sampling": 1, "timeout": "2s", "httpMethod": "GET"}},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    service = ProcessXrayService(Path(XRAY_BIN), path)
    api = ApiClient(Path(XRAY_BIN), server=f"unix://{socket_path}", timeout=5)
    service.start()

    def media(tag):
        return {**config["routing"], "rules": [
            {"type": "field", "domain": ["domain:googlevideo.com"], "balancerTag": "youtube"},
            *config["routing"]["rules"]],
            "balancers": [*config["routing"]["balancers"], {
                "tag": "youtube", "selector": [tag], "strategy": {"type": "leastPing"},
                "fallbackTag": tag}]}

    def selected(balancer, wanted):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with contextlib.suppress(ApiError):
                got = api.balancer_state(balancer).selects
                if got == wanted:
                    return True
            time.sleep(0.3)
        return False

    try:
        api.replace_routing(media("proxy-nl-bbbb"))
        assert selected("youtube", ("proxy-nl-bbbb",))
        api.replace_routing(media("proxy-de-aaaa"))
        assert selected("youtube", ("proxy-de-aaaa",))
        assert service.is_active()
    finally:
        service.stop()
        origin.shutdown()
