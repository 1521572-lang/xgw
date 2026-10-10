"""Атомарная запись и файловая блокировка."""

import os
import stat

import pytest

from xgw.paths import LockTimeout, Paths, atomic_write_json, atomic_write_text, file_lock


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path):
    target = tmp_path / "dir" / "config.json"
    atomic_write_json(target, {"a": 1})
    atomic_write_json(target, {"a": 2})
    assert target.read_text(encoding="utf-8") == '{\n  "a": 2\n}\n'
    assert [item.name for item in target.parent.iterdir()] == ["config.json"]


@pytest.mark.skipif(os.name == "nt", reason="права файлов POSIX")
def test_atomic_write_sets_mode(tmp_path):
    target = tmp_path / "config.json"
    atomic_write_text(target, "secret", mode=0o640)
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    atomic_write_text(target, "secret", mode=0o600)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_file_lock_is_exclusive(tmp_path):
    lock = tmp_path / "run" / "apply.lock"
    with file_lock(lock), pytest.raises(LockTimeout), file_lock(lock, timeout=0.2, poll=0.05):
        pass
    with file_lock(lock, timeout=0.2):  # после выхода блокировка свободна
        pass


def test_paths_layout():
    paths = Paths.from_env({"XGW_ROOT": "/tmp/x"})
    assert paths.generated_config_file.parent == paths.xray_config_file.parent
    assert paths.generated_config_file != paths.xray_config_file
    assert paths.lock_file.parent == paths.run and paths.api_dirty_file.parent == paths.run
