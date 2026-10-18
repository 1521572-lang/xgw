"""Второе ядро на живых Xray 26.10.10 и sing-box 1.14.3: конфиг, который строит XGW, принимает
`sing-box check`; сервер, описанный для Xray и переведённый на sing-box, подключается к настоящему
серверу Xray; поведение перечитывания конфига (SIGHUP) — то, на чём держится вся схема.

    XGW_XRAY_BIN=<xray> XGW_SINGBOX_BIN=<sing-box> pytest tests/test_singbox_live.py

Нужен root: sing-box ставит метку на сокеты (routing_mark = mark_bypass).
"""

import base64
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
from pins import spki_pin
from ports import free_port

from xgw.config import Config
from xgw.generator import singbox
from xgw.model import raw_to_node
from xgw.parsers.common import parse_link, parse_links_text

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
SINGBOX_BIN = os.environ.get("XGW_SINGBOX_BIN", "")
UUID = "2dd61d93-75d8-4da4-ac0e-6aece7eac365"

pytestmark = pytest.mark.skipif(
    not XRAY_BIN or not Path(XRAY_BIN).exists() or not SINGBOX_BIN
    or not Path(SINGBOX_BIN).exists() or not hasattr(os, "geteuid") or os.geteuid() != 0,
    reason="нужны XGW_XRAY_BIN, XGW_SINGBOX_BIN и root",
)


def _nodes(*links):
    raws, _meta, _warnings = parse_links_text("\n".join(links), "t")
    return [raw_to_node(raw, "t") for raw in raws]


KEY = "yAnz5TF%2BlXXJte14tji3zlMNq%2Bhd2rYUIgJBgB3fBmk%3D"
PUB = "xTIBA5rboUvnH4htodjb6e697QjLERt1NAB4mZqp8Dg%3D"
EVERY_KIND = [
    "vless://" + UUID + "@203.0.113.1:443?type=ws&security=tls&sni=a.example&fp=chrome"
    "&host=a.example&path=%2Fws%3Fed%3D2048&alpn=h2,http/1.1#a",
    "vless://" + UUID + "@203.0.113.2:443?security=reality&sni=b.example&fp=firefox"
    "&pbk=jNXHt1yRo0vDuchQlIP6Z0ZvjT3KtzVI-T4E7RoLJS0&sid=ab12&flow=xtls-rprx-vision#b",
    "vless://" + UUID + "@203.0.113.3:443?type=grpc&security=tls&sni=c.example"
    "&serviceName=svc#c",
    "vless://" + UUID + "@203.0.113.4:443?type=httpupgrade&security=tls&sni=d.example&path=/u#d",
    "trojan://pw@203.0.113.5:443?security=tls&sni=e.example#e",
    "ss://YWVzLTEyOC1nY206cGFzcw@203.0.113.6:8388#f",
    "socks://dXNlcjpwYXNz@203.0.113.7:1080#g",
    "hysteria2://pw@203.0.113.8:443,20000-30000/?sni=h.example&obfs=salamander"
    "&obfs-password=ob&upmbps=10&downmbps=20#h",
    "tuic://" + UUID + ":pw@203.0.113.9:443?sni=i.example&congestion_control=bbr"
    "&udp_relay_mode=native#i",
    "anytls://pw@203.0.113.10:443?sni=j.example&fp=firefox#j",
    f"wireguard://{KEY}@203.0.113.11:51820?publickey={PUB}&address=10.0.0.2%2F32"
    "&reserved=1,2,3&mtu=1280#k",
    "ss://YWVzLTEyOC1nY206cGFzcw@203.0.113.12:8388?plugin=obfs-local%3Bobfs%3Dhttp"
    "%3Bobfs-host%3Dx.example#l",
    "ss://YWVzLTEyOC1nY206cGFzcw@203.0.113.13:443?plugin=v2ray-plugin%3Btls%3Bhost%3Dx.example#m",
    "ss://YWVzLTEyOC1nY206cGFzcw@203.0.113.14:443?plugin=shadow-tls%3Bhost%3Dx.example"
    "%3Bpassword%3Dpp%3Bversion%3D3#n",
]


def test_the_config_xgw_builds_is_accepted_by_sing_box_check():
    cfg = Config()
    nodes = _nodes(*EVERY_KIND)
    assert len(nodes) == len(EVERY_KIND)
    plan = singbox.build(cfg, nodes, {})
    ok, output = singbox.validate_config(plan.config, Path(SINGBOX_BIN))
    assert ok, output
    # Каждый вариант каждого сервера заведён: d всегда, f — где есть TLS поверх TCP, m — где
    # допустим mux.
    letters = {}
    for fingerprint, letter in plan.ports:
        letters.setdefault(fingerprint, set()).add(letter)
    assert all("d" in got for got in letters.values()) and len(letters) == len(nodes)
    assert any("f" in got for got in letters.values())
    assert any("m" in got for got in letters.values())
    assert singbox.installed_version(Path(SINGBOX_BIN)) == (1, 14, 3)


def test_one_server_that_sing_box_refuses_does_not_spoil_the_rest():
    cfg = Config()
    good, bad = _nodes(EVERY_KIND[4], EVERY_KIND[7])
    bad.singbox.main["no_such_field"] = 1  # то, чего sing-box не знает
    plan = singbox.build(cfg, [good, bad], {})
    ok, output = singbox.validate_config(plan.config, Path(SINGBOX_BIN))
    assert ok is False and "no_such_field" in output
    invalid = singbox.find_invalid([good, bad], cfg, Path(SINGBOX_BIN))
    assert set(invalid) == {bad.fingerprint} and "no_such_field" in invalid[bad.fingerprint]
    without = singbox.build(cfg, [good, bad], {}, skip=set(invalid))
    assert singbox.validate_config(without.config, Path(SINGBOX_BIN))[0] is True


# --- сервер Xray ← клиент sing-box -------------------------------------------------------


@pytest.fixture()
def lab(tmp_path):
    """Серверы Xray на loopback и origin; процессы убираются при выходе."""
    procs: list[subprocess.Popen] = []

    def spawn(argv, log):
        with open(tmp_path / log, "wb") as output:
            proc = subprocess.Popen(
                argv, stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            )
        procs.append(proc)
        return proc

    origin_port = free_port()
    (tmp_path / "www").mkdir()
    (tmp_path / "www" / "hello").write_text("ok", encoding="ascii")
    spawn(["python3", "-m", "http.server", str(origin_port), "--bind", "127.0.0.1",
           "--directory", str(tmp_path / "www")], "origin.log")
    yield tmp_path, origin_port, spawn
    for proc in reversed(procs):
        proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _xray_server(lab, inbound: dict) -> int:
    tmp_path, _origin, spawn = lab
    port = free_port()
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [{"listen": "127.0.0.1", "port": port, **inbound}],
        "outbounds": [{"protocol": "freedom", "settings": {"finalRules": [{"action": "allow"}]}}],
    }
    path = tmp_path / f"xray-{port}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    spawn([XRAY_BIN, "run", "-c", str(path)], f"xray-{port}.log")
    return port


def _cert(lab, domain: str) -> tuple[str, str, str, str]:
    tmp_path = lab[0]
    prefix = tmp_path / f"cert-{domain}"
    subprocess.run([XRAY_BIN, "tls", "cert", f"--domain={domain}", "--expire=48h",
                    f"--file={prefix}"], check=True, capture_output=True, timeout=30)
    shown = subprocess.run([XRAY_BIN, "tls", "hash", f"--cert={prefix}.crt"], check=True,
                           capture_output=True, text=True, timeout=30).stdout
    leaf = next(line.split(":", 1)[1].strip() for line in shown.splitlines()
                if line.startswith("Leaf SHA256:"))
    pin = spki_pin(Path(f"{prefix}.crt").read_text(encoding="ascii"))
    return f"{prefix}.crt", f"{prefix}.key", leaf, pin


def _through_sing_box(lab, link: str, origin: tuple[str, int] | None = None) -> str:
    """Тело ответа origin, полученное через sing-box по описанию сервера из ссылки."""
    tmp_path, origin_port, spawn = lab
    origin_host, origin_port = origin or ("127.0.0.1", origin_port)
    (node,) = _nodes(link)
    assert node.singbox is not None, link
    cfg = Config()
    plan = singbox.build(cfg, [node], {})
    config = {**plan.config, "log": {"level": "error"}}
    config["experimental"]["clash_api"]["external_controller"] = f"127.0.0.1:{free_port()}"
    # Порты мостов — свободные.
    ports = {tag: free_port() for tag in [i["tag"] for i in config["inbounds"]]}
    for inbound in config["inbounds"]:
        inbound["listen_port"] = ports[inbound["tag"]]
    path = tmp_path / "singbox.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    spawn([SINGBOX_BIN, "--disable-color", "run", "-c", str(path)], "singbox.log")
    port = ports[singbox.tag_in(node.fingerprint, "d")]
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    proc = subprocess.run(
        ["curl", "-sS", "--max-time", "8", "--socks5-hostname",
         f"xgw-d:{plan.password}@127.0.0.1:{port}", f"http://{origin_host}:{origin_port}/hello"],
        capture_output=True, text=True,
    )
    return proc.stdout + proc.stderr


def test_vless_over_tcp_goes_through_sing_box(lab):
    port = _xray_server(lab, {"protocol": "vless",
                              "settings": {"clients": [{"id": UUID}], "decryption": "none"}})
    link = f"vless://{UUID}@127.0.0.1:{port}?type=tcp&security=none#a"
    assert _through_sing_box(lab, link) == "ok"


def test_vmess_with_websocket_goes_through_sing_box(lab):
    port = _xray_server(lab, {"protocol": "vmess", "settings": {"clients": [{"id": UUID}]},
                              "streamSettings": {"network": "ws", "wsSettings": {"path": "/w"}}})
    payload = {"v": "2", "ps": "m", "add": "127.0.0.1", "port": str(port), "id": UUID, "aid": "0",
               "scy": "auto", "net": "ws", "path": "/w", "tls": ""}
    link = "vmess://" + base64.b64encode(json.dumps(payload).encode()).decode()
    assert _through_sing_box(lab, link) == "ok"


def test_shadowsocks_goes_through_sing_box(lab):
    port = _xray_server(lab, {"protocol": "shadowsocks", "settings": {
        "method": "aes-128-gcm", "password": "pass", "network": "tcp,udp"}})
    assert _through_sing_box(lab, f"ss://YWVzLTEyOC1nY206cGFzcw@127.0.0.1:{port}#s") == "ok"


def test_trojan_with_a_self_signed_certificate_needs_the_public_key_pin(lab):
    crt, key, leaf, pin = _cert(lab, "pin.example")
    port = _xray_server(lab, {
        "protocol": "trojan", "settings": {"clients": [{"password": "pw"}]},
        "streamSettings": {"security": "tls", "tlsSettings": {
            "certificates": [{"certificateFile": crt, "keyFile": key}]}},
    })
    base = f"trojan://pw@127.0.0.1:{port}?security=tls&sni=pin.example&fp=chrome"
    # pcs (хеш сертификата) — для Xray; sing-box он не годится, и без pks сервер остаётся у Xray.
    assert parse_link(base + f"&pcs={leaf}").singbox is None
    assert _through_sing_box(lab, base + f"&pcs={leaf}&pks={pin.replace('+', '%2B')}") == "ok"
    wrong = base64.b64encode(bytes(32)).decode()
    result = _through_sing_box(lab, base + f"&pcs={leaf}&pks={wrong.replace('+', '%2B')}")
    assert result != "ok"  # чужой ключ — сертификат не принят


# --- перечитывание конфига --------------------------------------------------------------


def test_sighup_reloads_the_config_but_cuts_every_open_connection(lab):
    """Основание схемы «варианты заранее»: SIGHUP добавляет мосты, но рвёт идущие соединения."""
    tmp_path, origin_port, spawn = lab
    ports = [free_port(), free_port()]

    def write(count: int) -> None:
        inbounds = [
            {"type": "socks", "tag": f"in{i}", "listen": "127.0.0.1", "listen_port": ports[i]}
            for i in range(count)
        ]
        outbounds = [{"type": "direct", "tag": "out"}]
        config = {"log": {"level": "error"}, "inbounds": inbounds, "outbounds": outbounds,
                  "route": {"rules": [{"inbound": [i["tag"] for i in inbounds],
                                       "outbound": "out"}]}}
        (tmp_path / "reload.json").write_text(json.dumps(config), encoding="utf-8")

    write(1)
    proc = spawn([SINGBOX_BIN, "run", "-c", str(tmp_path / "reload.json")], "reload.log")
    time.sleep(1.0)

    def connect(port: int) -> socket.socket:
        sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        sock.sendall(b"\x05\x01\x00")
        assert sock.recv(2) == b"\x05\x00"
        sock.sendall(b"\x05\x01\x00\x01\x7f\x00\x00\x01" + origin_port.to_bytes(2, "big"))
        assert sock.recv(10)[1] == 0
        sock.sendall(b"GET /hello HTTP/1.1\r\nHost: x\r\nConnection: keep-alive\r\n\r\n")
        assert b"200" in sock.recv(4096)
        return sock

    held = connect(ports[0])
    with pytest.raises(OSError):  # второго моста в рабочем конфиге ещё нет
        socket.create_connection(("127.0.0.1", ports[1]), timeout=0.3).close()
    write(2)
    proc.send_signal(1)
    time.sleep(1.5)
    assert proc.poll() is None, "sing-box завершился вместо перечитывания"
    socket.create_connection(("127.0.0.1", ports[1]), timeout=1).close()  # теперь слушает
    held.settimeout(2)
    try:
        cut = held.recv(4096) == b""
    except OSError:
        cut = True
    assert cut, "идущее соединение пережило перечитывание — схему можно упростить"
    connect(ports[0]).close()
    connect(ports[1]).close()


def test_wireguard_server_description_connects_to_a_sing_box_wireguard_server(lab):
    """WireGuard как endpoint: ссылка wireguard:// → описание → sing-box подключается к серверу
    WireGuard (тоже sing-box) и ходит через него к origin. Сервер WireGuard в sing-box отбрасывает
    пакеты на loopback («Martian packet»), поэтому origin стоит на адресе машины, а не на
    127.0.0.1."""
    tmp_path, _origin_port, spawn = lab
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # пакетов не шлёт: только выбирает исходящий адрес
        local = probe.getsockname()[0]
    except OSError:
        local = "127.0.0.1"
    finally:
        probe.close()
    if local.startswith("127."):
        pytest.skip("нет адреса машины вне loopback — WireGuard-сервер sing-box его не пропускает")
    origin_port = free_port()
    spawn(["python3", "-m", "http.server", str(origin_port), "--bind", local,
           "--directory", str(tmp_path / "www")], "origin-wg.log")
    time.sleep(0.5)

    def pair() -> tuple[str, str]:
        out = subprocess.run([SINGBOX_BIN, "generate", "wg-keypair"], check=True,
                             capture_output=True, text=True).stdout.splitlines()
        return out[0].split(": ", 1)[1], out[1].split(": ", 1)[1]

    (server_private, server_public), (client_private, client_public) = pair(), pair()
    port = free_port()
    server = {
        "log": {"level": "error"},
        "endpoints": [{
            "type": "wireguard", "tag": "wg-in", "address": ["10.8.0.1/24"],
            "private_key": server_private, "listen_port": port,
            "peers": [{"public_key": client_public, "allowed_ips": ["10.8.0.2/32"]}],
        }],
        "outbounds": [{"type": "direct", "tag": "out"}],
        "route": {"rules": [{"inbound": ["wg-in"], "action": "route", "outbound": "out"}]},
    }
    path = tmp_path / "wg-server.json"
    path.write_text(json.dumps(server), encoding="utf-8")
    spawn([SINGBOX_BIN, "--disable-color", "run", "-c", str(path)], "wg-server.log")
    time.sleep(1.0)
    from urllib.parse import quote

    link = (f"wireguard://{quote(client_private, safe='')}@127.0.0.1:{port}"
            f"?publickey={quote(server_public, safe='')}&address=10.8.0.2%2F32#wg")
    assert _through_sing_box(lab, link, origin=(local, origin_port)) == "ok"
