"""Главный экран не выдаёт старый маршрут и готовность процесса за живое видео."""
import json
from pathlib import Path

import pytest

from vpn_ui.xgw.overview import overview, zapret_status


@pytest.mark.parametrize("mode,extra,stale", [
    ("off", {}, False), ("open", {}, False),
    ("on", {"blocked": True}, False), ("on", {"loaded": False}, False),
    ("on", {"inbound_missing": "restarting"}, False), ("on", {}, True),
])
def test_previous_server_is_not_presented_as_current(mode, extra, stale):
    state = json.loads((Path(__file__).parent / "fixtures/gui/state-work.json").read_text())
    active = overview(state, False)
    assert active.speed != "—"
    state["capture"].update(mode=mode, **extra)
    view = overview(state, stale)
    assert view.server != active.server
    assert (view.speed, view.rtt, view.core) == ("—", "—", "—")


def test_direct_mode_and_pending_mode_do_not_claim_a_vpn_server():
    state = json.loads((Path(__file__).parent / "fixtures/gui/state-work.json").read_text())
    state["zapret2"] = {"mode": "standalone", "state": "pending"}
    assert overview(state, False).speed == "—"
    state["zapret2"].update(without_vpn=True, state="active")
    view = overview(state, False)
    assert "без VPN" in view.server
    assert view.speed == "—"
    status = zapret_status(state, False)
    assert "не подтверждает воспроизведение YouTube" in status.detail
    assert zapret_status(state, True).tone != "ok"
    assert zapret_status(state, True).text == "Нет связи"


def test_missing_or_requested_zapret_mode_is_not_reported_as_running():
    assert zapret_status({}, False).text == "Нет данных"
    assert zapret_status({"zapret2": {"mode": "standalone", "state": "off"}}, False).text == (
        "Не используется")
    assert zapret_status({"zapret2": {"mode": "selective", "state": "fallback"}}, False).text == (
        "Возврат на VPN")


@pytest.mark.parametrize("phase,capture,busy", [
    ("preparing", {}, False), ("pending", {}, False), ("blocked", {}, False),
    ("unknown", {}, False), ("off", {}, False),
    ("active", {"loaded": False}, False), ("active", {"blocked": True}, False),
    ("active", {}, True),
])
def test_direct_route_does_not_imply_ready_handler(phase, capture, busy):
    state = {"capture": {"mode": "on", **capture},
             "zapret2": {"mode": "standalone", "state": phase, "without_vpn": True}}
    view = overview(state, False, busy)
    assert "без VPN" in view.server
    assert "готов" not in view.source
    assert view.tone != "ok"
