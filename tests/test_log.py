"""Журнал: секреты маскируются в каждой записи, от какого бы логгера она ни пришла."""

import io
import logging

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
