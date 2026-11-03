from types import SimpleNamespace

import pytest

from xgw import managed
from xgw.net.capture import Capture
from xgw.ownership import Registry
from xgw.ownership_adapters import Verification
from xgw.ownership_hooks import Coordinator, MutationBlocked, owned
from xgw.xraycore.api import ApiClient

BOOT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def context(tmp_path):
    import os

    registry = Registry(
        tmp_path / "registry", boot_id=BOOT, expected_uid=os.getuid(), clock_ns=lambda: 10
    )
    registry.initialize()
    coordinator = Coordinator(
        registry, lambda roles, value: Verification("COMMITTED", (("FILES", True),))
    )
    return registry, coordinator, tmp_path


def arm(registry):
    registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)


def test_capture_real_early_marker_unlink_is_before_no_admission(context):
    registry, coordinator, path = context
    capture = Capture.__new__(Capture)
    capture.ownership = coordinator
    capture.cfg = SimpleNamespace(tailscale=SimpleNamespace(route="direct"))
    capture.ts_marker = path / "marker"
    capture.ts_marker.write_text("fixture")
    capture.ts_fallback_marker = path / "absent"
    arm(registry)
    with pytest.raises(MutationBlocked):
        capture.tailscale_direct(False)
    assert capture.ts_marker.exists()
    capture.ownership = None
    capture.tailscale_direct(False)
    assert not capture.ts_marker.exists()


def test_nested_roles_share_one_receipt(context):
    registry, coordinator, _ = context
    seen = []
    coordinator.verifier = lambda roles, value: (
        seen.append(roles) or Verification("NOOP", (("FILES", True),))
    )
    assert coordinator.call("CORE", lambda: coordinator.call("CAPTURE", lambda: 7)) == 7
    assert seen == [frozenset({"CORE", "CAPTURE"})]
    assert registry.summary()["receipts"] == 1


def test_caught_nested_error_taints_outer(context):
    registry, coordinator, _ = context
    seen = []

    def nested():
        raise ValueError("private")

    def operation():
        try:
            coordinator.call("PEERS", nested)
        except ValueError:
            return 7

    coordinator.verifier = lambda roles, value: (
        seen.append(1) or Verification("COMMITTED", (("FILES", True),))
    )
    with pytest.raises(MutationBlocked):
        coordinator.call("CORE", operation)
    assert not seen and registry.summary()["unknown"] == 1


def test_deferred_functions_refused_without_running(context):
    registry, coordinator, _ = context

    def deferred():
        yield 1

    with pytest.raises(MutationBlocked):
        owned("CORE")(deferred)
    generator = deferred()
    with pytest.raises(MutationBlocked):
        coordinator.call("CORE", lambda: generator)
    generator.close()
    assert registry.summary()["unknown"] == 1


def test_real_api_pin_refused_before_runner(context):
    registry, coordinator, path = context
    client = ApiClient(path / "absent-binary", ownership=coordinator)
    arm(registry)
    with pytest.raises(MutationBlocked):
        client.pin("fixture", "fixture")


def test_nested_deferred_result_cannot_escape_scope(context):
    registry, coordinator, _ = context

    def values():
        yield 1

    value = values()

    def operation():
        try:
            coordinator.call("API", lambda: value)
        except MutationBlocked:
            return None

    try:
        with pytest.raises(MutationBlocked):
            coordinator.call("CORE", operation)
    finally:
        value.close()
    assert registry.summary()["unknown"] == 1


def test_real_panel_update_refused_before_lock_or_file(context):
    registry, coordinator, path = context
    arm(registry)
    with pytest.raises(MutationBlocked):
        managed._update(path / "panel.json", lambda data: True, ownership=coordinator)
    assert not (path / "panel.json").exists()
    assert not (path / ".panel.json.lock").exists()


def test_private_source_package_loader_does_not_reuse_live_namespace(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    repo = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "source_hook_loader_fixture", repo / "tests/stand/wave3_source_hooks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for path in (repo / "src/xgw").rglob("*.py"):
        target = tmp_path / "source" / path.relative_to(repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    monkeypatch.setattr(module, "NOTES", tmp_path)
    module.load_source()
    assert module.MODULES["net.capture"].Capture.__module__ == "frozen_ad.net.capture"
    assert module.MODULES["ownership_hooks"].Coordinator is not Coordinator
