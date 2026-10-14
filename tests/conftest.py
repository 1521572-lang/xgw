import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"


@pytest.fixture(autouse=True)
def _no_github(monkeypatch):
    """Тесты не ходят на GitHub: забытая подмена не должна скачать релиз Xray."""
    monkeypatch.setattr(
        "xgw.xraycore.binary.RELEASES_API", "http://127.0.0.1:9/tests-must-not-reach-github"
    )


@pytest.fixture(autouse=True)
def _no_panel(monkeypatch):
    """`xgw run` в тестах не открывает порт панели; сама панель проверяется в test_panel."""
    monkeypatch.setattr("xgw.cli._sync_panel", lambda panel, *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _no_bot(monkeypatch):
    """`xgw run` в тестах не запускает бота Telegram; бот проверяется в test_telegram."""
    monkeypatch.setattr("xgw.cli._sync_bot", lambda bot, *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    """Сборка конфига в тестах не ходит в настоящий DNS: резолверы «недоступны», как без
    сети. Результат не должен зависеть от того, есть ли у машины интернет: иначе домен
    вида *.example.com то находился бы, то объявлялся бы несуществующим. Карантин
    доменов — память процесса; между тестами она очищается."""
    from xgw import engine, fetch

    def offline(name, bootstrap, mark):
        raise fetch.ResolveError(f"тесты не ходят в DNS ({name})")

    monkeypatch.setattr(engine, "resolve_domain", offline)
    engine.forget_quarantine()
    engine._hosts_cache.clear()
    yield
    engine.forget_quarantine()
    engine._hosts_cache.clear()


REGEN = os.environ.get("XGW_REGEN_GOLDEN") == "1"


def golden(name: str, payload) -> object:
    """Сверяет payload с golden-файлом; при XGW_REGEN_GOLDEN=1 перезаписывает его."""
    path = GOLDEN_DIR / name
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")  # LF и на Windows
    return json.loads(path.read_text(encoding="utf-8"))
