"""Transaction boundary for deploying the accepted desktop map files."""

import importlib.util
import stat
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "docs/helpers/gui_home_install.py"


@pytest.fixture()
def trial(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("gui_home_install", HELPER)
    install = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(install)
    root = tmp_path / "release"
    payload = tmp_path / "payload"
    monkeypatch.setattr(install, "RELEASE", root)
    monkeypatch.setattr(install, "trusted", lambda _: None)

    def atomic(path, data, mode=0o644, gid=0):
        path.write_bytes(data)
        path.chmod(mode)

    monkeypatch.setattr(install, "atomic", atomic)
    for name in install.MAP_REFRESH:
        for path, value in ((root / name, "before"), (payload / "before" / name, "before"),
                            (payload / "after" / name, "after")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"# {value}\n".encode())
        (root / name).chmod(0o640)
    rows = install.delivery(payload, map_refresh=True)
    assert [target.relative_to(root).as_posix() for target, _, _ in rows] == list(
        install.MAP_REFRESH,
    )
    return install, rows, payload / "map-apply.started"


def test_map_install_and_rollback_restore_bytes_and_permissions(trial):
    install, rows, marker = trial
    install.switch(rows, "apply", marker=marker)
    assert marker.exists()
    assert all(target.read_bytes() == after for target, _, after in rows)
    install.switch(rows, "rollback", marker=marker)
    assert not marker.exists()
    assert all(target.read_bytes() == before for target, before, _ in rows)
    assert all(stat.S_IMODE(target.stat().st_mode) == 0o640 for target, _, _ in rows)


def test_map_install_refuses_a_partial_baseline_and_timer_leaves_it_alone(trial):
    install, rows, marker = trial
    target, _, after = rows[0]
    target.write_bytes(after)
    with pytest.raises(ValueError, match="map_baseline_not_complete"):
        install.switch(rows, "apply", marker=marker)
    install.switch(rows, "rollback", marker=marker)
    assert not marker.exists() and target.read_bytes() == after
    assert all(target.read_bytes() == before for target, before, _ in rows[1:])


def test_map_timer_can_finish_rollback_after_a_partial_write_error(trial, monkeypatch):
    install, rows, marker = trial
    atomic = install.atomic
    interrupted = rows[1][0]
    first, first_before, first_after = rows[0]

    def fail(path, data, mode=0o644, gid=0):
        if path == interrupted or (path == first and data == first_before):
            raise OSError("synthetic write failure")
        atomic(path, data, mode, gid)

    monkeypatch.setattr(install, "atomic", fail)
    with pytest.raises(OSError, match="synthetic write failure"):
        install.switch(rows, "apply", marker=marker)
    assert marker.exists() and first.read_bytes() == first_after
    monkeypatch.setattr(install, "atomic", atomic)
    install.switch(rows, "rollback", marker=marker)
    assert not marker.exists()
    assert all(target.read_bytes() == before for target, before, _ in rows)
