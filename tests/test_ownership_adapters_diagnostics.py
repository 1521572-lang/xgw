import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

from xgw import ownership
from xgw.ownership_adapters import Verification, execute
from xgw.ownership_diagnostics import inspect_registry

BOOT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def store(tmp_path):
    value = ownership.Registry(tmp_path / "store", boot_id=BOOT, expected_uid=os.getuid())
    value.initialize()
    return value


def test_terminal_exception_keeps_blocking_unknown(store):
    def interrupt():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute(store, "CORE", interrupt, lambda _: Verification("COMMITTED", (("FILES", True),)))
    assert store.summary()["unknown"] == 1


def test_post_replace_error_not_reclassified_as_success(store, monkeypatch):
    original = ownership.os.fsync

    def operation():
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("ack")
            original(fd)

        monkeypatch.setattr(ownership.os, "fsync", fail_directory)

    result = execute(store, "API", operation, lambda _: Verification("COMMITTED", (("API", True),)))
    assert result.status == "UNKNOWN" and result.reason == "COMPLETION_UNCERTAIN"
    assert result.retained_receipt is True and result.unknown_recorded is False
    assert store.summary()["writers"] == 0


def test_valid_stage_is_observed_but_never_promoted(store):
    original = (store.directory / "state.json").read_bytes()
    candidate = json.loads(original)
    candidate["revision"] += 1
    (store.directory / "state.next").write_text(json.dumps(candidate))
    (store.directory / "state.next").chmod(0o600)
    result = inspect_registry(store)
    assert result.status == "STAGE_VALID_UNPROVEN" and result.stage_valid is True
    assert result.repair_authorized is False
    assert (store.directory / "state.json").read_bytes() == original
    assert (store.directory / "state.next").exists()


def test_diagnostics_refuse_corrupt_baseline_without_zero_counts(store):
    (store.directory / "state.json").write_bytes(b"{")
    result = inspect_registry(store)
    assert result.status == "BASELINE_REFUSED"
    assert result.writers is None and result.baseline_valid is False


def test_frozen_package_loader_shares_registry_exception_identity(tmp_path, monkeypatch):
    repo = Path(__file__).parents[1]
    helper = repo / "tests/stand/wave3_writer_superbatch.py"
    spec = importlib.util.spec_from_file_location("superbatch_loader_fixture", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tmp_path.chmod(0o700)
    sources = {
        "ownership.py": "src/xgw/ownership.py",
        "ownership_adapters.py": "src/xgw/ownership_adapters.py",
        "ownership_diagnostics.py": "src/xgw/ownership_diagnostics.py",
        "fake_driver.py": "tests/stand/wave3_fake_recovery.py",
    }
    for name, source in sources.items():
        path = tmp_path / name
        path.write_bytes((repo / source).read_bytes())
        path.chmod(0o600)
    monkeypatch.setattr(module, "NOTES", tmp_path)
    base, adapter, diagnostic = module.load_sources()
    assert base.__name__ == "frozen_ac.ownership"
    assert adapter.Refused is base.Refused and diagnostic.Refused is base.Refused
    assert adapter.Verification().accepted() is False
