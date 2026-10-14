"""Части стенда сами по себе — без Xray и без root: реле, origin, DNS-заглушка."""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
from origin import dns_answer
from stand import free_port

from xgw.fetch import _dns_query, _parse_a_answers, plain_dns

HERE = Path(__file__).resolve().parent
PAYLOAD = bytes(range(256)) * 256  # 64 КиБ, не похоже на HTTP


def _spawn(script: str, *args: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(HERE / script), *args],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    assert proc.stdout is not None and proc.stdout.readline().strip() == "READY"
    return proc


@pytest.fixture()
def upstream():
    """«Сервер»: на любое соединение сразу отдаёт 64 КиБ и ждёт закрытия.

    Получив b"close", закрывает соединение первым. `client_gone` выставляется,
    когда сервер увидел конец потока от клиента.
    """
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    client_gone = threading.Event()

    def handle(conn: socket.socket) -> None:
        with contextlib.suppress(OSError), conn:
            conn.sendall(PAYLOAD)
            while data := conn.recv(4096):  # дочитываем до закрытия: иначе close() даст RST
                if data == b"close":
                    return
            client_gone.set()

    def serve() -> None:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    yield SimpleNamespace(port=server.getsockname()[1], client_gone=client_gone)
    server.close()


@pytest.fixture()
def relay(upstream, tmp_path):
    mode_file = tmp_path / "mode"
    mode_file.write_text("pass", encoding="ascii")
    port = free_port()
    proc = _spawn(
        "freeze_relay.py", "--listen", f"127.0.0.1:{port}",
        "--upstream", f"127.0.0.1:{upstream.port}", "--mode-file", str(mode_file),
    )

    def set_mode(mode: str) -> None:
        mode_file.write_text(mode, encoding="ascii")
        time.sleep(0.3)

    yield port, set_mode
    proc.terminate()
    proc.wait(timeout=5)


def _read(port: int, silence: float = 1.0) -> tuple[int, str]:
    """(сколько байт пришло, чем кончилось: closed | silence | reset)."""
    received = 0
    with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
        client.settimeout(silence)
        try:
            client.sendall(b"hello")  # при сбросе соединения ошибка может прийти уже здесь
            while received < len(PAYLOAD):
                chunk = client.recv(65536)
                if not chunk:
                    return received, "closed"
                received += len(chunk)
        except TimeoutError:
            return received, "silence"
        except ConnectionError:
            return received, "reset"
    return received, "complete"


def test_relay_pass(relay):
    port, _set_mode = relay
    assert _read(port) == (len(PAYLOAD), "complete")


def _read_all(client: socket.socket) -> int:
    received = 0
    while received < len(PAYLOAD):
        chunk = client.recv(65536)
        assert chunk, f"соединение закрылось на {received} байтах"
        received += len(chunk)
    return received


def test_relay_passes_server_close_to_client(relay):
    """Сервер закрыл соединение — клиент за реле видит конец потока, а не тишину."""
    port, _set_mode = relay
    with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
        client.sendall(b"close")
        _read_all(client)
        assert client.recv(4096) == b""


def test_relay_passes_client_close_to_server(relay, upstream):
    """Клиент закрыл соединение — сервер за реле тоже видит конец потока."""
    port, _set_mode = relay
    with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
        client.sendall(b"hello")
        _read_all(client)
    assert upstream.client_gone.wait(3)


def test_relay_frozen_connection_ends_when_client_leaves(relay, upstream):
    """«Замороженное» соединение реле держит открытым, пока клиент сам не уйдёт."""
    port, set_mode = relay
    set_mode("freeze_after=16384")
    assert _read(port) == (16384, "silence")
    assert upstream.client_gone.wait(3)


def test_relay_freeze_after_keeps_connection_open(relay):
    """После N байт данные перестают идти, но соединение не закрывается."""
    port, set_mode = relay
    set_mode("freeze_after=16384")
    assert _read(port) == (16384, "silence")
    assert _read(port) == (16384, "silence")  # счётчик — на каждое соединение отдельно
    set_mode("pass")
    assert _read(port) == (len(PAYLOAD), "complete")


def test_relay_small_response_passes_under_freeze(relay):
    """Ответ короче порога проходит целиком — поэтому HEAD-проверка «заморозку» не видит."""
    port, set_mode = relay
    set_mode("freeze_after=100000")
    assert _read(port) == (len(PAYLOAD), "complete")


def test_relay_drop_and_blackhole(relay):
    port, set_mode = relay
    set_mode("drop")
    received, ending = _read(port)
    assert received == 0 and ending in ("closed", "reset")
    set_mode("blackhole")
    assert _read(port) == (0, "silence")


def test_relay_latency(relay):
    port, set_mode = relay
    set_mode("pass;latency=400")
    started = time.monotonic()
    assert _read(port, silence=3.0) == (len(PAYLOAD), "complete")
    assert time.monotonic() - started >= 0.4


def test_origin_http_and_dns():
    port, dns_port = free_port(), free_port()
    proc = _spawn("origin.py", "--port", str(port), "--dns-port", str(dns_port),
                  "--answer", "203.0.113.7", "--country", "NL")
    try:
        base = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(f"{base}/64k", timeout=5) as response:
            assert len(response.read()) == 65536
        with urllib.request.urlopen(f"{base}/trace", timeout=5) as response:
            assert b"loc=NL" in response.read()
        head = urllib.request.Request(f"{base}/64k", method="HEAD")
        with urllib.request.urlopen(head, timeout=5) as response:
            assert response.headers["Content-Length"] == "65536" and response.read() == b""
        started = time.monotonic()
        with urllib.request.urlopen(f"{base}/slow?bytes=40960&seconds=1", timeout=10) as response:
            assert len(response.read()) == 40960
        assert time.monotonic() - started >= 0.8
        # DNS-заглушка отвечает тем же клиентом, которым XGW резолвит домены серверов
        assert plain_dns("127.0.0.1", "nl.stand.test", timeout=3, port=dns_port) == ["203.0.113.7"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_dns_answer_shapes():
    query = _dns_query("any.example.com")
    assert _parse_a_answers(dns_answer(query, "203.0.113.9")) == ["203.0.113.9"]
    aaaa = _dns_query("any.example.com", qtype=28)
    assert _parse_a_answers(dns_answer(aaaa, "203.0.113.9")) == []  # на AAAA — пустой ответ
    assert dns_answer(b"short", "203.0.113.9") is None


# --- «одноразовая машина»: XGW хоста не должен быть виден в контейнере -----------------


def test_host_xgw_is_scrubbed_from_the_container_root(tmp_path):
    """Корень контейнера — оверлей поверх корня хоста. Если на хосте стоит XGW, без
    чистки контейнер видел бы его конфиг, код, службы и следы в настройках: проверки
    «первого запуска» не прошли бы ни одна. Чистится только то, что оставил XGW."""
    import json

    import machine

    root = tmp_path / "root"
    files = {
        "etc/xgw/config.toml": "# конфиг хоста\n",
        "etc/xgw/xray/config.json": "{}",
        "opt/xgw/lib/xgw/__init__.py": "",
        "var/lib/xgw/state.db": "",
        "usr/local/bin/xgw": "#!/usr/bin/python3\n",
        "etc/systemd/system/xgw.service": "[Service]\n",
        "etc/systemd/system/xgw-net.service": "[Service]\n",
        "etc/systemd/system/xgw-xray.service": "[Service]\n",
        "etc/systemd/system/multi-user.target.wants/xgw.service": "",
        "etc/systemd/system/network-pre.target.wants/xgw-net.service": "",
        "etc/dnsmasq.d/xgw.conf": "port=0\n",
        "etc/sysctl.d/90-xgw.conf": "net.ipv4.ip_forward = 1\n",
        "usr/local/share/applications/xgw-panel.desktop": "[Desktop Entry]\n",
        "etc/NetworkManager/system-connections/xgw-lan.nmconnection": "[connection]\n",
        # Чужое — остаётся на месте.
        "etc/systemd/system/ssh.service": "[Service]\n",
        "etc/systemd/system/multi-user.target.wants/ssh.service": "",
        "etc/dnsmasq.d/home.conf": "# своё\n",
        "etc/sysctl.d/10-local.conf": "vm.swappiness = 10\n",
        "etc/NetworkManager/system-connections/Wired.nmconnection": "[connection]\n",
        "usr/local/bin/xgw-helper": "",
        "etc/ufw/before.rules": (
            "*filter\n-A ufw-before-input -i lo -j ACCEPT\n"
            "-A ufw-before-input -i enp4s0 -m mark --mark 0x1 -j ACCEPT\n"
            "-A ufw-before-input -j ufw-not-local\nCOMMIT\n"
        ),
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    journal = {"sleep": ["sleep.target", "suspend.target"], "user_created": True,
               "ufw": [["allow", "in", "on", "enp4s0"]], "ufw_before": True}
    (root / "var/lib/xgw/backup").mkdir(parents=True)
    (root / "var/lib/xgw/backup/install.json").write_text(json.dumps(journal), "utf-8")
    masks = True
    try:
        os.symlink("/dev/null", root / "etc/systemd/system/sleep.target")
        os.symlink("/dev/null", root / "etc/systemd/system/suspend.target")
        os.symlink("/dev/null", root / "etc/systemd/system/ctrl-alt-del.target")  # чужая маска
    except OSError:
        masks = False  # Windows без права создавать ссылки: эта часть проверяется в Linux

    assert machine.scrub_host_xgw(root) == journal
    left = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    )
    expected = [
        "etc/NetworkManager/system-connections/Wired.nmconnection",
        "etc/dnsmasq.d/home.conf",
        "etc/sysctl.d/00-xgw-stand.conf",
        "etc/sysctl.d/10-local.conf",
        "etc/systemd/system/multi-user.target.wants/ssh.service",
        "etc/systemd/system/ssh.service",
        "etc/ufw/before.rules",
        "usr/local/bin/xgw-helper",
    ]
    if masks:
        expected.append("etc/systemd/system/ctrl-alt-del.target")
    assert left == sorted(expected)
    assert "--mark" not in (root / "etc/ufw/before.rules").read_text(encoding="utf-8")
    assert "ufw-not-local" in (root / "etc/ufw/before.rules").read_text(encoding="utf-8")
    # Форвардинг контейнер не наследует от хоста: «заводская» система — не роутер.
    assert "net.ipv4.ip_forward = 0" in (root / machine.STAND_SYSCTL).read_text("utf-8")

    # Чистый хост: чистить нечего, журнала нет; повтор безвреден.
    assert machine.scrub_host_xgw(root) == {}
    with pytest.raises(RuntimeError, match="корень системы"):
        machine.scrub_host_xgw(Path(root.anchor))


def test_docker_of_the_host_is_masked_in_the_machine(tmp_path):
    """Docker, включённый на хосте, в контейнере не запускается: его маска лежит в корне
    контейнера, а свой файл службы хоста (если он был) там же заменён маской."""
    import machine

    root = tmp_path / "root"
    (root / "etc/systemd/system").mkdir(parents=True)
    (root / "etc/systemd/system/docker.service").write_text("[Service]\n", encoding="utf-8")
    try:
        machine.mask_host_services(root)
    except OSError as exc:  # Windows без права создавать ссылки
        pytest.skip(f"символьные ссылки недоступны: {exc}")
    for name in machine.HOST_SERVICES_OFF:
        link = os.readlink(root / "etc/systemd/system" / name).replace("\\", "/")
        assert link == "/dev/null", name
    machine.mask_host_services(root)  # повтор безвреден
