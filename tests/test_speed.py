"""Замер скорости (watch/speed.py) и загрузка с пределом по объёму и времени — на локальных
фейковых серверах; правила выбора основного; счётчики трафика Xray."""

import socket
import threading
import time
from types import SimpleNamespace

import pytest

from xgw.config import Config
from xgw.watch import speed
from xgw.watch.checks import http_get_via_proxy
from xgw.xraycore.metrics import proxy_traffic

MB = 1_000_000


class Origin(threading.Thread):
    """Локальный «прокси»: на запрос с «/forbidden» в адресе отвечает 403, на остальные —
    телом size байт кусками chunk с паузой pause между ними."""

    def __init__(self, size: int, chunk: int = 65536, pause: float = 0.0):
        super().__init__(daemon=True)
        self.size, self.chunk, self.pause = size, chunk, pause
        self.paths: list[str] = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.start()

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket):
        try:
            request = conn.recv(65536).decode("latin-1")
            self.paths.append(request.split(" ")[1])
            if "/forbidden" in request.split("\r\n")[0]:
                conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            conn.sendall(f"HTTP/1.1 200 OK\r\nContent-Length: {self.size}\r\n\r\n".encode())
            left = self.size
            while left > 0:
                part = min(self.chunk, left)
                conn.sendall(b"x" * part)
                left -= part
                if self.pause:
                    time.sleep(self.pause)
        except OSError:
            pass
        finally:
            conn.close()


@pytest.fixture()
def origin():
    servers: list[Origin] = []

    def factory(*args, **kwargs) -> Origin:
        server = Origin(*args, **kwargs)
        servers.append(server)
        return server

    yield factory
    for server in servers:
        server.sock.close()


def _cfg(url: str, fallback: str = "", *, max_mb: int = 2, max_seconds: int = 8) -> Config:
    cfg = Config()
    cfg.speed.url, cfg.speed.url_fallback = url, fallback
    cfg.speed.max_mb, cfg.speed.max_seconds = max_mb, max_seconds
    return cfg


def test_download_stops_at_max_bytes_and_counts_as_ok(origin):
    server = origin(10 * MB)
    result = http_get_via_proxy(
        "127.0.0.1", server.port, "http://speed.example/file", max_bytes=MB, timeout=5,
    )
    assert result.ok and MB <= result.downloaded < 10 * MB
    assert result.body_seconds > 0


def test_download_stops_at_max_body_seconds(origin):
    server = origin(10 * MB, chunk=16384, pause=0.05)  # ~320 КБ/с — 10 МБ не успеть
    started = time.monotonic()
    result = http_get_via_proxy(
        "127.0.0.1", server.port, "http://speed.example/file", max_body_seconds=1.0, timeout=5,
    )
    assert result.ok and 0 < result.downloaded < 10 * MB
    assert 1.0 <= result.body_seconds < 2.0 and time.monotonic() - started < 3.0


def test_full_download_reports_body_time(origin):
    server = origin(200_000)
    result = http_get_via_proxy("127.0.0.1", server.port, "http://speed.example/file", timeout=5)
    assert result.ok and result.downloaded == 200_000 and result.body_seconds >= 0


def test_measure_counts_body_throughput(origin):
    server = origin(10 * MB, chunk=65536, pause=0.01)
    node = SimpleNamespace(probe_port=server.port)
    result = speed.measure(node, _cfg("http://speed.example/file"), probe_pass="x")
    assert result.mbps is not None and result.mbps > 0 and not result.error
    assert result.bytes_read >= 2 * MB  # max_mb = 2
    # Скорость — байты тела за время тела.
    assert result.mbps == pytest.approx(result.bytes_read * 8 / result.seconds / MB, rel=0.05)


def test_measure_stops_at_the_given_size(origin):
    server = origin(10 * MB, chunk=65536)
    node = SimpleNamespace(probe_port=server.port)
    result = speed.measure(node, _cfg("http://speed.example/file"), probe_pass="x", max_mb=1)
    assert result.mbps is not None and MB <= result.bytes_read < 2 * MB


def test_limited_servers_download_less():
    """Квоты на замер лимитированного — не больше speed.max_mb, загрузка — не меньше 1 МБ."""
    cfg = Config()  # max_mb = 10
    assert speed.size_mb(cfg, 0.0) == speed.size_mb(cfg, 1.0) == 10
    assert speed.size_mb(cfg, 2.0) == 5 and speed.size_mb(cfg, 10.0) == 1
    assert speed.size_mb(cfg, 50.0) == 1
    assert speed.size_mb(cfg, 100.0) == 0  # x100 — серверы для LTE, не замеряются


def test_measure_falls_back_when_the_main_address_refuses(origin):
    server = origin(3 * MB)
    node = SimpleNamespace(probe_port=server.port)
    cfg = _cfg("http://speed.example/forbidden", "http://cdn.example/big.js")
    result = speed.measure(node, cfg, probe_pass="x")
    assert result.mbps is not None
    assert [path.split("/", 3)[-1] for path in server.paths] == ["forbidden", "big.js"]


def test_measure_reports_errors(origin):
    small = origin(100_000)
    node = SimpleNamespace(probe_port=small.port)
    result = speed.measure(node, _cfg("http://speed.example/file"), probe_pass="x")
    assert result.mbps is None and "слишком мал" in result.error

    refused = origin(3 * MB)
    node = SimpleNamespace(probe_port=refused.port)
    result = speed.measure(node, _cfg("http://speed.example/forbidden"), probe_pass="x")
    assert result.mbps is None and "403" in result.error


def _candidate(tag: str, mbps=None, delay=None) -> speed.Candidate:
    return speed.Candidate(tag=tag, key=tag, name=tag.upper(), mbps=mbps, delay_ms=delay)


def test_best_prefers_measured_speed_then_delay():
    assert speed.best([]) is None
    mixed = [_candidate("a", 30), _candidate("b", 90), _candidate("c", None, 10)]
    assert speed.best(mixed).tag == "b"
    assert speed.best([_candidate("a", None, 200), _candidate("b", None, 80)]).tag == "b"
    assert speed.best([_candidate("a", None, None), _candidate("b", None, 80)]).tag == "b"


def test_faster_needs_the_gain():
    main = _candidate("a", 50)
    assert not speed.faster(_candidate("b", 60), main, 30)
    assert speed.faster(_candidate("b", 65), main, 30)
    assert not speed.faster(_candidate("b", None), main, 0)
    assert speed.faster(_candidate("b", 1), _candidate("a", None), 30)  # у основного замера нет
    assert not speed.faster(_candidate("b", 50), main, 0)  # равная скорость — не повод


def test_texts():
    assert speed.mbps_text(85.4) == "85 Мбит/с"
    assert speed.mbps_text(8.46) == "8,5 Мбит/с"
    assert speed.describe(_candidate("a", 85)) == "«A» (85 Мбит/с)"
    assert speed.describe(_candidate("a", None, 120)) == "«A» (задержка 120 мс)"
    assert speed.describe(speed.Candidate(tag="proxy-a", key="k")) == "proxy-a"


def test_proxy_traffic_sums_only_servers_in_work():
    metrics = {"stats": {"outbound": {
        "proxy-a": {"downlink": 3_000_205, "uplink": 102},
        "proxy-b": {"downlink": 10, "uplink": 0},
        "spare-c": {"downlink": 999, "uplink": 0},  # сканы запасных — не нагрузка
        "direct": {"downlink": 5, "uplink": 5},
    }}}
    assert proxy_traffic(metrics) == 3_000_317
    assert proxy_traffic({"observatory": {}}) is None
    assert proxy_traffic({"stats": {"outbound": {}}}) == 0


def test_outbound_downlinks_are_per_server_in_work():
    from xgw.xraycore.metrics import outbound_downlinks

    metrics = {"stats": {"outbound": {
        "proxy-a": {"downlink": 3000205, "uplink": 102}, "proxy-b": {"uplink": 5},
        "spare-c": {"downlink": 7}, "direct": {"downlink": 9}, "proxy-d": {"downlink": True},
    }}}
    assert outbound_downlinks(metrics) == {"proxy-a": 3000205}
    assert outbound_downlinks({}) == {} and outbound_downlinks({"stats": None}) == {}
