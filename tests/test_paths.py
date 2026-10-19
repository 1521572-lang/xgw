"""Атомарная запись и файловая блокировка."""

import os
import stat
import threading

import pytest

from xgw import paths
from xgw.paths import (
    LockTimeout,
    Paths,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    file_lock,
)


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path):
    target = tmp_path / "dir" / "config.json"
    atomic_write_json(target, {"a": 1})
    atomic_write_json(target, {"a": 2})
    assert target.read_text(encoding="utf-8") == '{\n  "a": 2\n}\n'
    assert [item.name for item in target.parent.iterdir()] == ["config.json"]


def test_atomic_write_sets_mode(tmp_path):
    target = tmp_path / "config.json"
    atomic_write_text(target, "secret", mode=0o640)
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    atomic_write_text(target, "secret", mode=0o600)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_atomic_write_fsyncs_the_directory(tmp_path, monkeypatch):
    """После os.replace — fsync каталога: иначе после сбоя питания мог вернуться прежний файл."""
    synced = []
    real_fsync = os.fsync

    def fsync(fd):
        synced.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        real_fsync(fd)

    monkeypatch.setattr(paths.os, "fsync", fsync)
    atomic_write_text(tmp_path / "a.txt", "текст")
    assert synced == [False, True]  # сам файл, затем каталог


def test_threads_writing_one_file_do_not_share_a_temp_file(tmp_path):
    """Два потока демона пишут один файл: каждый целиком, без смеси и без сбоев."""
    target = tmp_path / "panel.json"
    payloads = [letter * 300_000 for letter in (b"a", b"b")]
    barrier, errors = threading.Barrier(len(payloads)), []

    def writer(data: bytes) -> None:
        barrier.wait()
        try:
            for _ in range(30):
                atomic_write_bytes(target, data)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(data,)) for data in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert target.read_bytes() in payloads
    assert [item.name for item in tmp_path.iterdir()] == ["panel.json"]


def test_file_lock_creates_the_file_with_the_given_mode(tmp_path):
    lock = tmp_path / ".panel.json.lock"
    with file_lock(lock, mode=0o600):
        pass
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600


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


def test_no_system_resolver_calls_in_xgw():
    """XGW разрешает имена своим резолвером с меткой мимо VPN или через DNS Xray, а не
    системным: в режиме blocked запросы resolved наружу отбиваются, и getaddrinfo оставил бы
    демон без адресов подписок и серверов (VPN_IMPROVEMENT_PLAN.md, §2.1)."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "xgw"
    pattern = re.compile(r"\b(getaddrinfo|gethostbyname(_ex)?|gethostbyaddr)\s*\(")
    found = [
        f"{path.relative_to(src)}:{number}"
        for path in sorted(src.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line.split("#", 1)[0])
    ]
    assert found == []
