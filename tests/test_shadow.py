"""Теневая проба (0.2.0, ДОП-3) живым Xray: отдельный процесс с одним выходом отвечает на
скан и останавливается. Только при XGW_XRAY_BIN (как другие живые проверки)."""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from xgw.config import Config
from xgw.watch import shadow

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
pytestmark = pytest.mark.skipif(not XRAY_BIN, reason="нет XGW_XRAY_BIN — живой Xray не проверяется")


class _Origin(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"x" * 4096
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def test_shadow_xray_answers_a_scan_and_stops(tmp_path):
    origin = ThreadingHTTPServer(("127.0.0.1", 0), _Origin)
    threading.Thread(target=origin.serve_forever, daemon=True).start()
    try:
        cfg = Config()
        outbound = shadow.outbound_for({"protocol": "freedom", "settings": {}}, cfg)
        assert outbound is not None and outbound["tag"] == "shadow"
        url = f"http://127.0.0.1:{origin.server_address[1]}/probe"
        result = shadow.probe(outbound, cfg, Path(XRAY_BIN), url=url, run_dir=tmp_path)
        assert result.verdict == "OK", result.error
        assert list(tmp_path.iterdir()) == []  # временный конфиг убран
        assert shadow.outbound_for(
            {"protocol": "vless", "streamSettings": {"sockopt": {"dialerProxy": "chain-x"}}},
            cfg) is None
    finally:
        origin.shutdown()
