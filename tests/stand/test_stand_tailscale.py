"""Проверки стенда: Tailscale рядом с XGW (Т1 `TAILSCALE_MINIAPP_PLAN.md`, раздел 2.5).

Только режим netns, на настоящем ядре и настоящем Xray; нужны Linux, root, nft:

    sudo -E XGW_XRAY_BIN=<путь к xray> pytest tests/stand/test_stand_tailscale.py -q

Tailscale на шлюзе изображён так, как его видит ядро: интерфейс tailscale0 (veth в
«интернет», за ним — «tailnet»: устройство 100.64.0.2 и MagicDNS 100.100.100.100),
таблица 52 с маршрутами tailnet и правила `ip rule` 5210/5270, как ставит tailscaled.
Сам tailscaled — процесс-заглушка: сокет с меткой 0x80000 (SO_MARK) к адресу в «интернете».
Как отличить путь трафика — как в test_stand_lan.py: origin на /trace отдаёт адрес, с
которого пришёл запрос: 5.5.5.1 — через VPN-сервер, 5.5.5.2 — напрямую с WAN шлюза.

Т2 (раздел 3.4): панель по tailnet — настоящий демон с CLI-заглушкой fake_tailscale_cli.py
принимает Host «gw.example.ts.net:8443», только пока Serve включён кнопкой панели; песочница
xgw.service (systemd-run) подключается к сокету tailscaled.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import netns
import pytest
from stand import HERE, Stand, wait_for

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
VIA_VPN = netns.INET_IP
DIRECT = netns.GW_WAN_IP
DIRECT6 = netns.GW_WAN_IP6
TS_MARK = str(0x80000)  # метка сокетов tailscaled
GW_TS_IP, PEER_IP, MAGIC_DNS = "100.64.0.1", "100.64.0.2", "100.100.100.100"
GW_TS_IP6, PEER_IP6 = "fd7a:115c:a1e0::1", "fd7a:115c:a1e0::2"
TS_ANSWER = "100.64.0.77"  # так отвечает MagicDNS «tailnet»; Xray ответил бы адресом «интернета»

pytestmark = [
    pytest.mark.skipif(
        not XRAY_BIN or not Path(XRAY_BIN).exists(), reason="нет XGW_XRAY_BIN — стенд пропущен"
    ),
    pytest.mark.skipif(
        not netns.available() or shutil.which("nft") is None,
        reason="проверки Tailscale: нужны Linux, root и nft",
    ),
]


def _ip(*args: str) -> None:
    subprocess.run(["ip", *args], check=True, capture_output=True, text=True, timeout=15)


def _tailscale(stand: Stand) -> None:
    """tailscale0 шлюза, маршруты и правила Tailscale, «tailnet» и MagicDNS за ним."""
    topo = stand._topology
    gw, inet = topo.gw, topo.inet
    _ip("link", "add", "tailscale0", "netns", gw, "type", "veth", "peer", "name", "tsnet0",
        "netns", inet)
    for namespace, device, addresses in (
        (gw, "tailscale0", (f"{GW_TS_IP}/32", f"{GW_TS_IP6}/128")),
        (inet, "tsnet0", (f"{PEER_IP}/32", f"{MAGIC_DNS}/32", f"{PEER_IP6}/128")),
    ):
        for address in addresses:
            _ip("-n", namespace, "addr", "add", address, "dev", device, "nodad")
        _ip("-n", namespace, "link", "set", device, "up")
    _ip("-n", inet, "route", "add", GW_TS_IP, "dev", "tsnet0")
    _ip("-n", inet, "-6", "route", "add", GW_TS_IP6, "dev", "tsnet0")
    # Как у tailscaled: адреса tailnet — в таблице 52, помеченные им сокеты — в main.
    _ip("-n", gw, "route", "add", "100.64.0.0/10", "dev", "tailscale0", "table", "52")
    _ip("-n", gw, "route", "add", MAGIC_DNS, "dev", "tailscale0", "table", "52")
    _ip("-n", gw, "-6", "route", "add", "fd7a:115c:a1e0::/48", "dev", "tailscale0",
        "table", "52")
    for family in ("-4", "-6"):
        _ip("-n", gw, family, "rule", "add", "pref", "5210", "fwmark", "0x80000/0xff0000",
            "lookup", "main")
        _ip("-n", gw, family, "rule", "add", "pref", "5270", "lookup", "52")
    stand._spawn(
        "tailnet", "inet",
        [sys.executable, str(HERE / "origin.py"), "--host", PEER_IP, "--port", "8080",
         "--dns-port", "53", "--answer", TS_ANSWER, "--dns-also", MAGIC_DNS],
        "READY",
    )
    stand._spawn(
        "tailnet6", "inet",
        [sys.executable, str(HERE / "origin.py"), "--host", PEER_IP6, "--port", "8080"],
        "READY",
    )


def _stand(tmp_path: Path, xray: Path | None = None, *, v6: bool = False, capture=True,
           **config) -> Stand:
    stand = Stand(tmp_path, xray or Path(XRAY_BIN), mode="netns", ipv6=v6)
    try:
        stand.start()
        _tailscale(stand)
        stand.up(capture=capture, **config)
        if capture:
            enabled = stand.xgw("enable")
            assert enabled.returncode == 0, enabled.stderr
    except BaseException:
        stand.stop()
        raise
    return stand


def _magic_dns(stand: Stand) -> list[str] | None:
    """Ответ на запрос шлюза к MagicDNS; None — ответа нет."""
    reply = stand.client("gw", "dns", MAGIC_DNS, "peer.tailnet.test", "--timeout", "3")
    return reply.get("answers")


def _tailnet(stand: Stand, host: str) -> str:
    """С какого адреса запрос шлюза дошёл до устройства в tailnet; пусто — не дошёл."""
    url = f"http://[{host}]:8080/trace" if ":" in host else f"http://{host}:8080/trace"
    reply = stand.client("gw", "get", url, "--timeout", "4")
    for line in reply.get("body", "").splitlines():
        if line.startswith("ip="):
            return line[3:]
    return ""


def _route(route: str) -> str:
    return f'\n[tailscale]\nroute = "{route}"\n'


def test_tailscaled_goes_direct_and_magic_dns_is_not_captured(tmp_path):
    """Режим on, route = "direct" (К1, К2): сокет tailscaled выходит напрямую, обычный —
    через Xray; DNS к 100.100.100.100 уходит в tailscale0, а не в Xray."""
    stand = _stand(tmp_path)
    try:
        assert stand.exit_ip("gw") == VIA_VPN
        assert stand.exit_ip("gw", "--mark", TS_MARK) == DIRECT
        assert _magic_dns(stand) == [TS_ANSWER]
        assert _tailnet(stand, PEER_IP) == GW_TS_IP
        assert stand.client("gw", "dns", "8.8.8.8", "example.org").get("answers") == [VIA_VPN]
        table = stand.gw_run("nft", "list", "table", "ip", "xgw")
        assert 'oifname "tailscale0" return' in table and "@ts_direct" in table
        assert stand.xgw_json("status")["capture"]["loaded"] is True
    finally:
        stand.stop()


@pytest.mark.parametrize("route", ["direct", "vpn"])
def test_blocked_keeps_tailscale(tmp_path, route):
    """Режим blocked (К3): Xray запущен без inbound'а перехвата. Обычный сокет отбит, а
    tailscaled соединяется (при любом route), MagicDNS и tailnet отвечают."""
    stand = _stand(tmp_path, capture=False)
    try:
        stand.write_config(capture=True, extra=_route(route))
        stand.xgw("net", "up")
        assert "chain block_output" in stand.gw_run("nft", "list", "table", "ip", "xgw")
        assert stand.exit_ip("gw") == ""
        assert stand.exit_ip("gw", "--mark", TS_MARK) == DIRECT
        assert _magic_dns(stand) == [TS_ANSWER]
        assert _tailnet(stand, PEER_IP) == GW_TS_IP
    finally:
        stand.stop()


def test_ipv6_off_closes_ipv6_but_not_the_tailnet(tmp_path):
    """network.ipv6 = "off" (К4): обычный IPv6 машины наружу отбит, IPv6 в tailscale0
    проходит, IPv6-сокет tailscaled выходит напрямую."""
    stand = _stand(tmp_path, v6=True, ipv6="off")
    try:
        assert stand.exit_ip6("gw", "--mark", "2") == DIRECT6  # IPv6 на стенде работает
        assert stand.exit_ip6("gw") == ""
        assert _tailnet(stand, PEER_IP6) == GW_TS_IP6
        assert stand.exit_ip6("gw", "--mark", TS_MARK) == DIRECT6
    finally:
        stand.stop()


def test_route_vpn_follows_xray(tmp_path):
    """route = "vpn": пока Xray отвечает, tailscaled идёт через Xray; Xray остановлен (и не
    запускается) — демон кладёт метку в набор, и tailscaled выходит напрямую; Xray вернулся —
    снова через Xray. Обычный трафик всё это время закрыт (fail-closed)."""
    switch = tmp_path / "xray-off"
    wrapper = tmp_path / "xray-wrapper.sh"  # Xray, который можно «сломать»: не запускается
    wrapper.write_text(
        "#!/bin/sh\n"
        f'if [ -e "{switch}" ] && [ "$1" = run ]; then\n'
        '    echo "xray отключён тестом" >&2\n'
        "    exit 1\n"
        "fi\n"
        f'exec "{XRAY_BIN}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    stand = _stand(tmp_path / "stand", wrapper, extra=_route("vpn"))
    try:
        stand.start_daemon()
        assert wait_for(
            lambda: (s := stand.xgw_json("status"))["daemon"] and s["state"] == "HEALTHY",
            60, step=2,
        ), stand.tail("daemon", 30)
        assert stand.exit_ip("gw", "--mark", TS_MARK) == VIA_VPN

        switch.touch()
        stand.xray_service().stop()
        started = time.monotonic()
        assert wait_for(lambda: stand.exit_ip("gw", "--mark", TS_MARK) == DIRECT, 30, step=1), (
            stand.tail("daemon", 30))
        assert time.monotonic() - started < 30
        assert stand.exit_ip("gw") == ""  # обычный трафик — никуда
        details = [event["detail"] for event in stand.xgw_json("status")["events"]]
        assert any("Tailscale идёт напрямую" in detail for detail in details)

        switch.unlink()
        assert wait_for(lambda: stand.exit_ip("gw", "--mark", TS_MARK) == VIA_VPN, 60, step=2), (
            stand.tail("daemon", 30))
        assert stand.exit_ip("gw") == VIA_VPN
    finally:
        stand.stop()


# --- Т2: панель по tailnet и доступ к tailscaled из службы ---------------------------

TAILNET_HOST = "gw.example.ts.net:8443"


def _panel(stand: Stand, *args: str) -> dict:
    result = stand.run_in("gw", sys.executable, str(HERE / "panel_client.py"), "8781", *args)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_panel_answers_the_tailnet_host_only_while_serve_is_on(tmp_path, monkeypatch):
    """Т2 (3.4): настоящий демон и панель; Host «gw.example.ts.net:8443» (так приходит
    Tailscale Serve) принимается, только пока Serve включён кнопкой панели. Вместо
    tailscaled — CLI-заглушка fake_tailscale_cli.py и пустой файл сокета."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cli = bin_dir / "tailscale"
    cli.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "fake_tailscale_cli.py"}" "$@"\n',
        encoding="utf-8")
    cli.chmod(0o755)
    fake = tmp_path / "tailscale.json"
    fake.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("XGW_FAKE_TAILSCALE", str(fake))
    stand = Stand(tmp_path / "stand", Path(XRAY_BIN), mode="netns")
    try:
        stand.start()
        stand.up(panel=True)
        socket = stand.root / "run/tailscale/tailscaled.sock"
        socket.parent.mkdir(parents=True, exist_ok=True)
        socket.touch()
        stand.start_daemon()
        assert wait_for(lambda: _panel(stand, "raw", "/").get("status") == 200, 60), (
            stand.tail("daemon", 30))
        token = (stand.root / "var/lib/xgw/panel-token").read_text(encoding="ascii").strip()
        assert _panel(stand, "host", TAILNET_HOST, token)["status"] == 403
        card = _panel(stand, "state", token)["tailscale"]
        assert card["state"] == "running" and card["name"] == "gw.example.ts.net"

        result = _panel(stand, "act", token, "tailscale/serve", json.dumps({"on": True}))
        assert result.get("ok"), result
        assert json.loads(fake.read_text(encoding="utf-8"))["serve"] == "http://127.0.0.1:8781"
        assert _panel(stand, "host", TAILNET_HOST, token)["status"] == 200
        for host in ("other.example.ts.net:8443", "gw.example.ts.net"):
            assert _panel(stand, "host", host, token)["status"] == 403

        result = _panel(stand, "act", token, "tailscale/serve", json.dumps({"on": False}))
        assert result.get("ok"), result
        assert json.loads(fake.read_text(encoding="utf-8"))["serve"] == ""
        assert _panel(stand, "host", TAILNET_HOST, token)["status"] == 403
    finally:
        stand.stop()


def _service_sandbox() -> list[str]:
    """Свойства песочницы из packaging/xgw.service — для systemd-run. Каталоги из
    ReadWritePaths — с «-»: на стенде /etc/xgw и /var/lib/xgw может не быть."""
    unit = (HERE.parents[1] / "packaging/xgw.service").read_text(encoding="utf-8")
    section = unit.split("[Service]", 1)[1].split("\n[", 1)[0]
    options: list[str] = []
    for line in section.splitlines():
        key, _, value = line.strip().partition("=")
        if key in ("ProtectSystem", "PrivateTmp", "NoNewPrivileges", "CapabilityBoundingSet"):
            options += ["-p", f"{key}={value}"]
        elif key == "ReadWritePaths":
            options += ["-p", "ReadWritePaths=" + " ".join(f"-{item}" for item in value.split())]
    assert any(item == "ProtectSystem=strict" for item in options)
    return options


@pytest.mark.skipif(
    shutil.which("systemd-run") is None or not Path("/run/systemd/system").is_dir(),
    reason="нужен systemd (systemd-run)",
)
def test_service_sandbox_reaches_the_tailscaled_socket():
    """3.3: демон XGW обращается к tailscaled через CLI, то есть подключается к сокету
    /run/tailscale/tailscaled.sock. Под ProtectSystem=strict /run только для чтения — а
    подключиться к сокету можно и так, ReadWritePaths=/run/tailscale не нужен. Если
    tailscaled на машине есть, проверка идёт с его настоящим сокетом."""
    import socket as sockets
    import threading

    directory, path = Path("/run/tailscale"), Path("/run/tailscale/tailscaled.sock")
    made_dir, server = False, None
    if not path.exists():
        made_dir = not directory.exists()
        directory.mkdir(mode=0o755, exist_ok=True)
        server = sockets.socket(sockets.AF_UNIX, sockets.SOCK_STREAM)
        server.bind(str(path))
        server.listen(4)

        def answer() -> None:
            while True:
                try:
                    conn, _ = server.accept()
                except OSError:
                    return
                with conn:
                    conn.recv(4096)
                    conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok")

        threading.Thread(target=answer, daemon=True).start()
    # Проба — строкой (-c): у службы свой /tmp (PrivateTmp), файла из tmp_path она не видит.
    probe = (
        "import socket\n"
        "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        "s.settimeout(10)\n"
        f"s.connect({str(path)!r})\n"
        "s.sendall(b'GET /localapi/v0/status HTTP/1.0\\r\\nHost: local-tailscaled.sock"
        "\\r\\n\\r\\n')\n"
        "print(s.recv(64)[:12].decode('ascii', 'replace'))\n"
        "try:\n"
        "    open('/run/tailscale/xgw-write-probe', 'w')\n"
        "    print('WRITABLE')\n"
        "except OSError as exc:\n"
        "    print('READONLY', exc.errno)\n"
    )
    try:
        result = subprocess.run(
            ["systemd-run", "--wait", "--pipe", "--quiet", "--collect", *_service_sandbox(),
             sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        lines = result.stdout.split()
        assert lines[0].startswith("HTTP/"), result.stdout
        assert "READONLY" in lines and "WRITABLE" not in lines  # /run — только чтение
    finally:
        if server is not None:
            server.close()
            path.unlink(missing_ok=True)
            Path("/run/tailscale/xgw-write-probe").unlink(missing_ok=True)
            if made_dir:
                directory.rmdir()


# --- А1 (ANDROID_APP_PLAN.md): приложение на телефоне через Funnel -----------------------


def test_phone_pairs_through_the_panel_button_and_gets_a_valid_xray_config(tmp_path, monkeypatch):
    """Настоящий демон: кнопка «Привязать телефон» включает Funnel (CLI-заглушка) и даёт
    ссылку из QR; эталонный клиент phone_client.py привязывается, читает состояние, нажимает
    «Проверить запасные» и получает конфиг Xray для телефона — его принимает сам Xray."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cli = bin_dir / "tailscale"
    cli.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "fake_tailscale_cli.py"}" "$@"\n',
        encoding="utf-8")
    cli.chmod(0o755)
    fake = tmp_path / "tailscale.json"
    fake.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("XGW_FAKE_TAILSCALE", str(fake))
    stand = Stand(tmp_path / "stand", Path(XRAY_BIN), mode="netns")
    client = [sys.executable, str(HERE.parent / "phone_client.py")]
    url, host = "http://127.0.0.1:8782", "gw.example.ts.net"
    keyfile = tmp_path / "phone.key"
    try:
        stand.start()
        stand.up(panel=True)
        socket = stand.root / "run/tailscale/tailscaled.sock"
        socket.parent.mkdir(parents=True, exist_ok=True)
        socket.touch()
        stand.start_daemon()
        assert wait_for(lambda: _panel(stand, "raw", "/").get("status") == 200, 60), (
            stand.tail("daemon", 30))
        token = (stand.root / "var/lib/xgw/panel-token").read_text(encoding="ascii").strip()

        def phone(*args: str) -> dict:
            done = stand.run_in("gw", *client, "--host", host, url, *args)
            return json.loads(done.stdout.strip().splitlines()[-1])

        assert phone("hello")["status"] == 421  # Funnel ещё не включён — API закрыт
        result = _panel(stand, "act", token, "phones/pair", "{}")
        assert result.get("ok") and "Наведите камеру" in result["text"], result
        assert json.loads(fake.read_text(encoding="utf-8"))["funnel"] == url
        link = _panel(stand, "state", token)["phones"]["pairing"]["link"]
        assert link.startswith(f"xgw://pair?u=https://{host}&c=")
        assert phone("hello") == {"status": 200, "app": "XGW"}

        paired = phone("pair", link.split("&c=")[1], str(keyfile))
        assert paired["paired"] is True, paired
        state = phone("state", str(keyfile))
        assert state["status"] == 200 and state["state"] and state["members"] >= 1, state
        acted = phone("act", str(keyfile), json.dumps({"name": "scan"}))
        assert acted["status"] == 200 and acted["ok"] is True, acted
        refused = phone("act", str(keyfile), json.dumps({"name": "add", "text": "x"}))
        assert refused["status"] == 403
        replay = phone("replay", str(keyfile))
        assert replay == {"first": 200, "replay": 403}

        # Конфиг для телефона — из настоящего применённого конфига; Xray его принимает.
        status = stand.run_in(
            "gw", sys.executable, "-c",
            "import json,sys; sys.path.insert(0, sys.argv[1]); from phone_client import "
            "PhoneClient, _load; c = PhoneClient(sys.argv[2], host=sys.argv[3]); "
            "c.phone, c.key = _load(sys.argv[4]); s, p = c.signed('GET', '/api/phone-config'); "
            "print(json.dumps({'status': s, 'config': p.get('config')}))",
            str(HERE.parent), url, host, str(keyfile),
        )
        reply = json.loads(status.stdout.strip().splitlines()[-1])
        assert reply["status"] == 200, reply
        phone_config = tmp_path / "phone.json"
        phone_config.write_text(json.dumps(reply["config"]), encoding="utf-8")
        checked = subprocess.run([XRAY_BIN, "run", "-test", "-c", str(phone_config)],
                                 capture_output=True, text=True, timeout=60)
        assert checked.returncode == 0, checked.stdout + checked.stderr

        state = _panel(stand, "state", token)
        assert [item["name"] for item in state["phones"]["list"]] == ["Тестовый телефон"]
        assert state["tailscale"]["funnel"]["on"] is True
        result = _panel(stand, "act", token, "tailscale/funnel", json.dumps({"on": False}))
        assert result.get("ok"), result
        assert phone("hello")["status"] == 421
    finally:
        stand.stop()
