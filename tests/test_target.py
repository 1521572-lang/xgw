"""«Не отвечает сам probe.url» против «не работают серверы» (watch/target.py)."""

import pytest

from xgw import fetch
from xgw.config import Config
from xgw.generator.builder import NodeInfo
from xgw.paths import Paths
from xgw.watch import checks, target
from xgw.watch.scan import ScanResult

WARNING = (
    "Внимание: пробы всех серверов падают — вероятно, недоступны сами проверочные хосты "
    "(probe.url и probe.urls)"
)


def _result(verdict: str, *, bytes_read: int = 0, error: str = "", kind: str = "",
            status: int = 0) -> ScanResult:
    return ScanResult("proxy-nl-0001", verdict, bytes_read, 1.0, error, kind, status)


HTTP_403 = _result("CONNECT_FAIL", error="HTTP 403", kind="http", status=403)
HTTP_404 = _result("CONNECT_FAIL", error="HTTP 404", kind="http", status=404)
TIMEOUT = _result("TIMEOUT", error="таймаут", kind="timeout")
STALL = _result("STALL_BEFORE_BODY", error="тишина 5 с до начала тела", kind="stall")
RESET = _result("CONNECT_FAIL", error="TLS: connection reset", kind="tls")
FROZEN = _result("FROZEN", bytes_read=19451, error="тишина 5 с после 19451 байт тела",
                 kind="stall", status=200)
GOOD = _result("OK", bytes_read=57620)


def test_signature_names_the_class_of_the_failure():
    assert target.signature(HTTP_403) == "HTTP 403"
    assert target.signature(_result("CONNECT_FAIL", error="HTTP 502", kind="http", status=502)) == (
        "HTTP 502")
    assert target.signature(TIMEOUT) == target.signature(STALL) == "таймаут"
    assert target.signature(RESET) == "обрыв соединения"
    # Проба прошла либо пришла часть тела — адрес пробы отвечает.
    assert target.signature(GOOD) == target.signature(FROZEN) == ""
    assert target.signature(_result("SLOW", bytes_read=57620)) == ""
    # Запись без кода ответа (её оставила прежняя версия): код берётся из текста ошибки.
    assert target.signature(_result("CONNECT_FAIL", error="HTTP 403")) == "HTTP 403"


def test_failure_is_the_most_common_error_unless_someone_got_the_file():
    assert target.failure([HTTP_403, HTTP_403, HTTP_403]) == ("HTTP 403", 3, 3)
    assert target.failure([TIMEOUT, STALL]) == ("таймаут", 2, 2)
    assert target.failure([HTTP_403, HTTP_404, HTTP_403]) == ("HTTP 403", 2, 3)
    assert target.failure([HTTP_403, GOOD]) == ("", 0, 2)  # у кого-то проба прошла
    assert target.failure([HTTP_403, FROZEN]) == ("", 0, 2)  # «заморозка» — это про сервер
    assert target.failure([]) == ("", 0, 0)
    assert target.failure_text("HTTP 403", 3, 3) == "HTTP 403"
    assert target.failure_text("обрыв соединения", 64, 67) == "обрыв соединения у 64 из 67"


def test_dominant_failure_for_probe_all():
    """`xgw probe --all` на живой машине: 64 обрыва и 3 таймаута из 67 — прежняя проверка
    «одна ошибка у всех» здесь молчала, хотя не отвечал именно адрес пробы."""
    results = [RESET] * 64 + [TIMEOUT] * 3
    assert target.dominant(results) == "обрыв соединения у 64 из 67"
    assert target.dominant([HTTP_403] * 5) == "HTTP 403"
    assert target.dominant([RESET, TIMEOUT]) == ""  # ни одна ошибка не преобладает
    assert target.dominant([RESET] * 9 + [GOOD]) == ""  # кто-то файл получил


def test_sample_takes_all_members_and_a_few_spares_that_passed_the_scan():
    def node(role: str, name: str, port: int = 20001) -> NodeInfo:
        return NodeInfo(name * 8, f"{role}-nl-{name * 4}", f"probe-nl-{name * 4}", port, role)

    view = [node("proxy", "a"), node("proxy", "b"), node("spare", "c"), node("spare", "d"),
            node("spare", "e"), node("spare", "f"), node("spare", "9", port=0)]
    verdicts = {"probe-nl-ffff": "OK", "probe-nl-dddd": "SLOW", "probe-nl-cccc": "FROZEN"}
    picked = [info.tag for info in target.sample(view, verdicts)]
    assert picked[:2] == ["proxy-nl-aaaa", "proxy-nl-bbbb"]
    # Запасных — три, прошедшие скан первыми; узел без порта пробы опросить нечем.
    assert picked[2:4] == ["spare-nl-dddd", "spare-nl-ffff"] and len(picked) == 5
    assert "spare-nl-9999" not in picked


def _never() -> bool:
    raise AssertionError("контрольный запрос не нужен")


def test_same_http_error_directly_confirms_at_once():
    verdict = target.diagnose([HTTP_403] * 4, base_ping=_never, direct=lambda: "HTTP 403")
    assert verdict.down and verdict.signature == "HTTP 403"
    assert verdict.text == f"{WARNING} (HTTP 403; напрямую, мимо VPN, ответ тот же — HTTP 403)"


def test_http_error_only_through_vpn_is_confirmed_by_the_base_request():
    """Напрямую файл отдаётся, а через все серверы — 403: адрес не пускает сеть VPN."""
    verdict = target.diagnose([HTTP_403] * 3, base_ping=lambda: True, direct=lambda: "")
    assert verdict.down and "хотя напрямую отдаётся" in verdict.detail
    blind = target.diagnose([HTTP_403] * 3, base_ping=lambda: False, direct=lambda: "")
    assert not blind.down  # через VPN не проходит ничего — это уже не про адрес


def test_different_failures_count_too_when_the_base_request_works():
    """Ошибки разные, но файл не получил никто, а через VPN другие адреса открываются:
    это адрес пробы. Случай с живой машины — обрывы у большинства и таймауты у остальных."""
    results = [RESET] * 6 + [TIMEOUT] * 2
    down = target.diagnose(results, base_ping=lambda: True, direct=lambda: "нет ответа")
    assert down.down and down.signature == "обрыв соединения у 6 из 8"
    dead = target.diagnose(results, base_ping=lambda: False, direct=_never)
    assert not dead.down  # через VPN не проходит ничего — серверы мертвы
    # Разные коды HTTP: одного прямого запроса мало, решает базовый запрос через VPN.
    mixed = target.diagnose([HTTP_403, HTTP_403, HTTP_404], base_ping=lambda: True,
                            direct=lambda: "HTTP 403")
    assert mixed.down and mixed.signature == "HTTP 403 у 2 из 3"


def test_timeouts_need_a_working_base_request():
    """Одинаковые таймауты бывают и у мёртвых серверов; а probe.url напрямую может быть
    просто закрыт провайдером — поэтому прямой запрос тут ничего не решает."""
    dead = target.diagnose([TIMEOUT, STALL], base_ping=lambda: False, direct=_never)
    assert not dead.down and dead.signature == "таймаут"  # прямой запрос даже не делался
    down = target.diagnose([TIMEOUT, STALL], base_ping=lambda: True, direct=lambda: "нет ответа")
    assert down.down and "напрямую — нет ответа" in down.detail
    assert down.text.startswith(WARNING)


def test_an_answer_from_anyone_asks_nothing_and_blames_nobody():
    for results in ([HTTP_403, GOOD], [FROZEN, FROZEN], [RESET, FROZEN], []):
        verdict = target.diagnose(results, base_ping=_never, direct=_never)
        assert not verdict.down and verdict.signature == ""


def test_core_probes_use_the_fallback_address_while_the_probe_url_is_down(tmp_path):
    """Пока probe.url не отвечает, ядро пробует серверы по запасному адресу: по
    probe.url_fallback, а без него — по probe.trace_url (другие проверочные хосты — в своём
    тесте). Запись о запасном относится к своему probe.url и переживает перезапуск (лежит в
    /var/lib/xgw)."""
    paths = Paths(root=tmp_path)
    cfg = Config()
    cfg.probe.urls = []
    primary = cfg.probe.url
    assert target.fallback_target(cfg) == cfg.probe.trace_url
    assert target.observatory_url(cfg, paths) == primary
    assert target.use_fallback(cfg, paths, True) is True
    assert target.observatory_url(cfg, paths) == cfg.probe.trace_url
    assert target.use_fallback(cfg, paths, True) is False  # уже на запасном
    cfg.probe.url_fallback = "https://cdn.example.net/blob.woff"
    assert target.observatory_url(cfg, paths) == "https://cdn.example.net/blob.woff"
    # probe.url в конфиге сменили — прежняя запись не действует.
    other = Config()
    other.probe.url = "https://files.example.net/new.bin"
    assert target.observatory_url(other, paths) == other.probe.url
    assert target.use_fallback(cfg, paths, False) is True
    assert target.observatory_url(cfg, paths) == primary
    assert target.use_fallback(cfg, paths, False) is False
    # Подменять нечем: запасного нет, а trace_url совпадает с probe.url или пуст.
    cfg.probe.url_fallback, cfg.probe.trace_url = "", ""
    assert target.fallback_target(cfg) == ""
    assert target.use_fallback(cfg, paths, True) is False
    assert target.observatory_url(cfg, paths) == primary


def test_direct_request_goes_around_the_vpn_with_the_probe_user_agent(monkeypatch):
    cfg = Config()
    cfg.probe.url = "https://probe.example.net/blob"
    cfg.probe.user_agent = "Mozilla/5.0 Test"
    seen: dict = {}

    def fetch_url(url, **kwargs):
        seen.update(kwargs, url=url)
        return fetch.FetchResult(seen.get("answer", 200), {}, b"x" * 100, url)

    monkeypatch.setattr(target.fetch, "fetch_url", fetch_url)
    assert target.direct_signature(cfg, mark=2) == ""
    assert seen["url"] == cfg.probe.url and seen["mark"] == 2 and seen["retries"] == 0
    assert seen["headers"] == {"User-Agent": "Mozilla/5.0 Test"}
    # С меткой — свои резолверы (и дополнительные, 0.1.18), мимо перехвата.
    assert seen["bootstrap"] == cfg.dns.resolvers
    seen["answer"] = 403
    assert target.direct_signature(cfg, mark=None) == "HTTP 403"
    assert seen["bootstrap"] is None

    def broken(url, **kwargs):
        raise fetch.FetchError("не удалось получить probe.example.net: timed out")

    monkeypatch.setattr(target.fetch, "fetch_url", broken)
    assert target.direct_signature(cfg, mark=None) == "нет ответа"


@pytest.mark.parametrize("ok", [True, False])
def test_base_request_goes_through_the_balancer(monkeypatch, ok):
    cfg = Config()
    cfg.xray.http_port = 10999
    seen: dict = {}

    def get(host, port, url, **kwargs):
        seen.update(kwargs, host=host, port=port, url=url)
        return checks.DownloadResult(ok=ok)

    monkeypatch.setattr(target.checks, "http_get_via_proxy", get)
    assert target.base_ping(cfg) is ok
    assert (seen["host"], seen["port"], seen["url"]) == ("127.0.0.1", 10999, cfg.probe.trace_url)
    assert seen["user_agent"] == cfg.probe.user_agent
    cfg.probe.trace_url = ""
    assert target.base_ping(cfg) is False  # проверить нечем — подтверждения нет


def test_the_core_probes_another_probe_host_that_answered(tmp_path):
    """0.1.18 (ТЗ R3): не отвечает только probe.url — ядро пробует серверы по проверочному
    хосту, который демон только что открыл через серверы; без такого — по первому из
    probe.urls. Хост, которого в конфиге больше нет, не используется."""
    paths = Paths(root=tmp_path)
    cfg = Config()
    first, second = cfg.probe.urls[0], cfg.probe.urls[1]
    assert target.fallback_target(cfg) == first
    assert target.fallback_since(paths) is None
    assert target.use_fallback(cfg, paths, True, second) is True
    assert target.observatory_url(cfg, paths) == second
    since = target.fallback_since(paths)
    assert since is not None
    # Повторно с тем же хостом — ничего не меняется, отсчёт «с какого момента» тоже.
    assert target.use_fallback(cfg, paths, True, second) is False
    assert target.use_fallback(cfg, paths, True) is False
    assert target.fallback_since(paths) == since
    cfg.probe.urls = [first]
    assert target.observatory_url(cfg, paths) == first  # второго в конфиге больше нет
    assert target.use_fallback(cfg, paths, False) is True
    assert target.observatory_url(cfg, paths) == cfg.probe.url
