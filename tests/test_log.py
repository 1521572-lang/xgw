"""Журнал: секреты маскируются в каждой записи, от какого бы логгера она ни пришла."""

import io
import logging
import os
import sys

import pytest

from xgw import log

UUID = "11111111-2222-3333-4455-666666666661"


@pytest.fixture()
def journal(monkeypatch):
    """Чистая настройка журнала с перехватом вывода."""
    root = logging.getLogger("xgw")
    saved = root.handlers[:]
    root.handlers.clear()
    monkeypatch.setattr(log, "_secrets", set())
    log.setup()
    stream = io.StringIO()
    root.handlers[0].stream = stream
    yield stream
    root.handlers[:] = saved


def test_child_logger_records_are_masked(journal):
    """Все модули пишут через дочерние логгеры (xgw.generate, xgw.apply, …)."""
    log.get_logger("generate").warning(
        "подписка %s, узел %s", "https://panel.example.com/sub/SECRETTOKEN", UUID
    )
    text = journal.getvalue()
    assert "SECRETTOKEN" not in text
    assert UUID not in text
    assert "panel.example.com" in text and "****6661" in text


def test_registered_short_secret_is_masked(journal):
    log.add_secrets(["tr0jan-pass"])
    log.get_logger("apply").error("ошибка узла с паролем tr0jan-pass")
    assert "tr0jan-pass" not in journal.getvalue()
    assert "***" in journal.getvalue()


def test_exception_text_is_masked(journal):
    try:
        raise ValueError(f"bad link vless://{UUID}@203.0.113.10:443?security=tls")
    except ValueError:
        log.get_logger("generate").exception("разбор не удался")
    text = journal.getvalue()
    assert UUID not in text
    assert "vless://***" in text


def test_setup_is_idempotent(journal):
    log.setup(secrets=["another-secret"])
    handlers = logging.getLogger("xgw").handlers
    assert sum(isinstance(h.formatter, log.MaskingFormatter) for h in handlers) == 1
    log.get_logger("x").info("another-secret")
    assert "another-secret" not in journal.getvalue()


def _record(level: int, message: str, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord("xgw.watch", level, __file__, 1, message, (), exc_info)


def test_journal_prefix_sets_priority_of_every_line():
    """journald берёт уровень из префикса «<N>» каждой строки; без него всё — info (6),
    и `journalctl -p warning` не видит уведомлений (замечание D2 отчёта 0.1.9)."""
    formatter = log.MaskingFormatter(log._FORMAT, journal=True)
    assert formatter.format(_record(logging.WARNING, "reserve: уже 5 мин")).startswith("<4>")
    assert formatter.format(_record(logging.INFO, "rotation")).startswith("<6>")
    assert formatter.format(_record(logging.DEBUG, "metrics")).startswith("<7>")
    try:
        raise ValueError(f"bad link vless://{UUID}@203.0.113.10:443")
    except ValueError:
        text = formatter.format(_record(logging.ERROR, "разбор не удался", sys.exc_info()))
    lines = text.split("\n")
    assert len(lines) > 2 and all(line.startswith("<3>") for line in lines)
    assert UUID not in text
    plain = log.MaskingFormatter(log._FORMAT)
    assert not plain.format(_record(logging.WARNING, "reserve")).startswith("<")
    assert log.syslog_priority(logging.CRITICAL) == 2


def test_journal_stream_matches_device_and_inode(tmp_path, monkeypatch):
    """JOURNAL_STREAM — «устройство:inode» потока журнала; унаследованная переменная при
    stderr, перенаправленном в файл или терминал, не считается."""
    with open(tmp_path / "stderr.log", "w", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        monkeypatch.delenv("JOURNAL_STREAM", raising=False)
        assert not log.journal_stream(stream)
        monkeypatch.setenv("JOURNAL_STREAM", f"{info.st_dev}:{info.st_ino}")
        assert log.journal_stream(stream)
        assert not log.journal_stream(io.StringIO())  # fileno() не поддерживается
        assert not log.journal_stream(None)
        monkeypatch.setenv("JOURNAL_STREAM", f"{info.st_dev}:{info.st_ino + 1}")
        assert not log.journal_stream(stream)
        monkeypatch.setenv("JOURNAL_STREAM", "garbage")
        assert not log.journal_stream(stream)
