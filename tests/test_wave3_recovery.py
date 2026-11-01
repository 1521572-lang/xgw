"""Узкие регрессии по реальному отчёту wave3, без изменения сети и служб."""

import importlib.util
from pathlib import Path

import pytest
from test_install import Box

from xgw.install import InstallError


def test_install_stops_controller_before_code_and_starts_without_second_sigterm(tmp_path):
    box = Box(tmp_path)
    box.system.unit("xgw.service")["active"] = True
    installer = box.installer()
    order = []
    for method in ("_packages", "_user", "_xray", "_singbox", "_tidy_config", "_permissions"):
        setattr(installer, method, lambda *args: None)
    installer._code = lambda: order.append(box.system.unit("xgw.service")["active"])
    installer._system(installer.facts())
    assert order == [False]
    installer._daemon()
    assert box.system.commands("systemctl", "stop", "xgw.service")
    assert box.system.commands("systemctl", "start", "xgw.service")
    assert not box.system.commands("systemctl", "restart", "xgw.service")


def test_failed_install_resumes_only_paused_controller(tmp_path):
    box = Box(tmp_path)
    box.system.unit("xgw.service")["active"] = True
    installer = box.installer()
    installer._pause_daemon()
    installer._resume_paused_daemon()
    assert box.system.unit("xgw.service")["active"]
    assert not box.system.commands("systemctl", "stop", "xgw-xray.service")


def test_existing_implicit_on_does_not_become_off_on_failed_first_apply(tmp_path):
    box = Box(tmp_path)
    installer = box.installer()
    installer._capture_initial_on = True
    assert installer.capture.choice() is None
    with pytest.raises(InstallError, match="не снимается"):
        installer._capture(False)
    assert installer.capture.choice() is None


@pytest.mark.parametrize("mode,loaded,guard", [("off", True, True), ("on", False, True),
                                             ("on", True, False)])
def test_install_cannot_return_success_for_missing_requested_policy(tmp_path, mode, loaded, guard):
    installer = Box(tmp_path).installer()
    installer._capture_initial_on = True
    capture = type("CaptureFixture", (), {
        "configured": True, "mode": lambda s: mode, "effective_mode": lambda s: mode,
        "loaded": lambda s: loaded, "guard_loaded": lambda s: guard,
    })()
    installer.capture = capture
    with pytest.raises(InstallError):
        installer._verify_capture_result(True)


def test_daemon_unit_preserves_child_transaction_on_sigterm():
    unit = (Path(__file__).parents[1] / "packaging/xgw.service").read_text()
    assert "KillMode=mixed\n" in unit


def safety():
    path = Path(__file__).parent / "stand/wave3_safety.py"
    spec = importlib.util.spec_from_file_location("wave3_safety", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expired_local_lease_recovers_without_tester_or_network(tmp_path, monkeypatch):
    tool = safety()
    clock = [0.0]
    monkeypatch.setattr(tool.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(tool.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0]+seconds))
    tool.watch(tmp_path, dry=True)
    assert tool.json.loads((tmp_path / "status.json").read_text())["state"] == "DRY_EXPIRED"
    assert clock[0] == tool.LEASE_SECONDS
    with pytest.raises(SystemExit, match="lease"):
        tool.pulse(tmp_path)


def test_rescue_uses_prepared_rules_and_bounded_commands_not_installed_xgw(tmp_path, monkeypatch):
    tool = safety()
    rules, state = b"prepared off rules", b'{"enabled":false}'
    (tmp_path / "off.nft").write_bytes(rules)
    (tmp_path / "capture.json").write_bytes(state)
    target = tmp_path / "live-capture.json"
    tool.save(tmp_path / "snapshot.json", {
        "off_sha256": tool.hashlib.sha256(rules).hexdigest(),
        "state_sha256": tool.hashlib.sha256(state).hexdigest(),
        "capture_state": str(target), "open_marker": str(tmp_path / "open"),
    })
    calls = []
    monkeypatch.setattr(tool, "call", lambda argv, timeout, **kw:
                        calls.append((argv, timeout, kw)) or 0)
    tool.restore(tmp_path)
    assert [call[0][0] for call in calls] == ["systemctl", "systemctl", "nft"]
    assert calls[-1][2]["data"] == rules
    assert sum(call[1] for call in calls) == 12
    assert target.read_bytes() == state
    assert tool.json.loads((tmp_path / "status.json").read_text())["state"] == "RESTORED_OFF"
