import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

BOOT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def registry(tmp_path):
    path = Path(__file__).parents[1] / "src/xgw/ownership.py"
    spec = importlib.util.spec_from_file_location("candidate_registry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    store = module.Registry(tmp_path / "store", boot_id=BOOT, expected_uid=os.getuid())
    store.initialize()
    return module, store


def test_pre_replace_failure_retains_writer_and_blocks_reopen(registry, monkeypatch):
    module, store = registry
    token = store.admit("CORE")

    def fail(*args, **kwargs):
        raise OSError("before replace")

    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(module.Refused, match="COMMIT_UNCERTAIN"):
        store.complete(token, outcome="COMMITTED", verified=True)
    raw = json.loads((store.directory / "state.json").read_bytes())
    assert len(raw["writers"]) == 1 and raw["generation"] == 0
    assert (store.directory / "state.next").exists()
    with pytest.raises(module.Refused, match="INTERRUPTED_COMMIT"):
        store.summary()


def test_post_replace_ack_failure_has_single_coherent_receipt(registry, monkeypatch):
    module, store = registry
    token = store.admit("CORE")
    original = module.os.fsync

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("after replace")
        original(fd)

    monkeypatch.setattr(module.os, "fsync", fail_directory)
    with pytest.raises(module.Refused, match="COMMIT_UNCERTAIN"):
        store.complete(token, outcome="COMMITTED", verified=True)
    assert store.summary() == {
        "writers": 0,
        "unknown": 0,
        "generation": 1,
        "receipts": 1,
        "phase": "IDLE",
    }
    with pytest.raises(module.Refused, match="STALE_WRITER_TOKEN"):
        store.complete(token, outcome="COMMITTED", verified=True)
    assert store.receipt(token) == {"outcome": "COMMITTED", "generation": 1}


def test_constructor_has_no_io_and_old_boot_cannot_read_or_admit(registry, tmp_path):
    module, store = registry
    unused = tmp_path / "unused"
    module.Registry(unused, boot_id=BOOT)
    assert not unused.exists()
    other = module.Registry(
        store.directory, boot_id="22222222-2222-2222-2222-222222222222", expected_uid=os.getuid()
    )
    with pytest.raises(module.Refused, match="BOOT_MISMATCH"):
        other.admit("CAPTURE")
    with pytest.raises(module.Refused, match="BOOT_MISMATCH"):
        other.summary()


def test_string_verification_does_not_retire_or_publish(registry):
    module, store = registry
    token = store.admit("API")
    with pytest.raises(module.Refused, match="COMPLETION_UNVERIFIED"):
        store.complete(token, outcome="ROLLED_BACK", verified="true")
    assert store.summary()["writers"] == 1
    assert store.summary()["generation"] == 0
