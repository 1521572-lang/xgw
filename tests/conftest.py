import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"


def pytest_configure(config):
    # XGW — только для Ubuntu 24.04 и 26.04, и тесты с ним: на другой системе они не идут.
    if not sys.platform.startswith("linux"):
        pytest.exit("тесты XGW запускаются только в Linux (Ubuntu 24.04 или 26.04)", returncode=4)


@pytest.fixture(autouse=True)
def _no_github(monkeypatch):
    """Тесты не ходят на GitHub: забытая подмена не должна скачать релиз Xray или sing-box."""
    monkeypatch.setattr(
        "xgw.xraycore.binary.RELEASES_API", "http://127.0.0.1:9/tests-must-not-reach-github"
    )
    monkeypatch.setattr(
        "xgw.sbcore.binary.RELEASES_API", "http://127.0.0.1:9/tests-must-not-reach-github"
    )


@pytest.fixture(autouse=True)
def _no_core_check(monkeypatch):
    """Демон в тестах сам не проверяет выпуски ядер на GitHub (фоновый поток): её включают
    тесты обновления ядер (test_cores.py)."""
    monkeypatch.setattr("xgw.daemon.CORES_FIRST_CHECK", float("inf"))


@pytest.fixture(autouse=True)
def _no_singbox_from_env(monkeypatch):
    """Настоящий sing-box из окружения нужен только живым тестам и стендам: они читают
    XGW_SINGBOX_BIN при импорте модуля и передают его сами. Остальные тесты не должны
    находить его через find_binary и пытаться запустить службу xgw-singbox."""
    monkeypatch.delenv("XGW_SINGBOX_BIN", raising=False)


@pytest.fixture(autouse=True)
def _no_panel(monkeypatch):
    """`xgw run` в тестах не открывает порт панели; сама панель проверяется в test_panel."""
    monkeypatch.setattr("xgw.cli._sync_panel", lambda panel, *args, **kwargs: None)


@pytest.fixture(scope="session")
def _empty_sys_net(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("sys-class-net")


@pytest.fixture(autouse=True)
def _no_docker(monkeypatch, _empty_sys_net):
    """Мостов Docker «нет»: результат тестов не должен зависеть от того, стоит ли Docker на
    машине, где они идут (отчёт 0.1.4, G2). Тесты контейнеров задают свой каталог."""
    monkeypatch.setattr("xgw.net.lan.SYS_NET", _empty_sys_net)


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
        path.write_text(text, encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))
