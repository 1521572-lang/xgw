"""Status reader parity and the public CLI command."""

import json
import sys
import time
from types import SimpleNamespace

import pytest

from xgw.config import Config
from xgw.desync import client, event_socket, schema
from xgw.paths import Paths
from xgw.watch import panel_ipc, status
from xgw.watch.panel import Panel
from xgw.watch.zapret2_control import card


@pytest.mark.parametrize(("case", "expected"), [
    ("off", "off"), ("active", "active"), ("expired", "unknown"),
    ("stale", "unknown"), ("revision", "pending"), ("missing", "unknown"),
])
def test_compact_status_matches_card_without_database_or_events(tmp_path, monkeypatch,
                                                               case, expected):
    cfg = Config()
    cfg.zapret2.engine = "off"
    cfg.zapret2.mode = "off" if case == "off" else "standalone"
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    now = time.time()
    snapshot = {
        "daemon": True, "updated": now - 120 if case == "stale" else now,
        "zapret2_policy_key": "old" if case == "revision" else schema.fingerprint(cfg.desync),
        "capture": {"loaded": True}, "zapret2": {"state": "off" if case == "off" else "active",
            "valid_until": now - 30 if case == "expired" else now + 60},
    } if case != "missing" else {}
    paths = Paths(tmp_path)
    capture = {"mode": "on"}
    panel = Panel(paths, paths.config_file, "test", port=0,
                  capture_factory=lambda *_a, **_k: SimpleNamespace(mode=lambda: capture["mode"]))
    panel.configure(cfg, object())
    if snapshot:
        status.write_status(paths, snapshot)

    def unexpected(*_args, **_kwargs):
        pytest.fail("compact status accessed the detailed overview")

    monkeypatch.setattr(panel, "_db", unexpected)
    monkeypatch.setattr(panel, "_probe_budget", unexpected)
    monkeypatch.setattr(panel.desync_jobs, "public", unexpected)
    monkeypatch.setattr(event_socket, "cursor_response", unexpected)
    summary = panel.zapret2_status()["zapret2"]
    full = card(cfg, snapshot, capture, True)
    assert summary == panel_ipc.project(full) and summary["state"] == expected


@pytest.mark.parametrize("compact", [False, True])
def test_cli_status_selects_endpoint_and_returns_the_expected_fields(monkeypatch, capsys, compact):
    summary = dict(zip(panel_ipc.STATUS_FIELDS, ("off", "off", "off", True, True), strict=True))
    overview = {**summary, "config_key": "revision", "job": {"state": "idle"}}
    requests = []

    def request(path):
        requests.append(path)
        return {"zapret2": overview}

    monkeypatch.setattr(client, "Client", lambda: SimpleNamespace(request=request))
    monkeypatch.setattr(sys, "argv", ["client", "status", *(["--summary"] if compact else [])])
    assert client.main() == 0
    assert requests == ["/api/zapret2/status" if compact else "/api/zapret2/overview"]
    assert json.loads(capsys.readouterr().out) == (summary if compact else overview)


@pytest.mark.parametrize("code", [404, 503])
def test_cli_summary_reports_unavailable_reader_without_retrying_overview(monkeypatch, capsys, code):
    def request(path):
        assert path == "/api/zapret2/status"
        raise client._HTTPFailure(code)

    monkeypatch.setattr(client, "Client", lambda: SimpleNamespace(request=request))
    monkeypatch.setattr(sys, "argv", ["client", "status", "--summary"])
    assert client.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "isolated_status_unavailable" and payload["http_status"] == code
