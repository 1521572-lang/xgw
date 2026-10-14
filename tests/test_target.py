"""«Не отвечает сам probe.url» против «не работают серверы» (watch/target.py)."""

import pytest

from xgw import fetch
from xgw.config import Config
from xgw.generator.builder import NodeInfo
from xgw.watch import checks, target
from xgw.watch.scan import ScanResult

WARNING = "Внимание: все пробы падают с одинаковой ошибкой — вероятно, недоступен сам probe.url"


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


def test_uniform_needs_the_same_failure_everywhere():
    assert target.uniform([HTTP_403, HTTP_403, HTTP_403]) == "HTTP 403"
    assert target.uniform([TIMEOUT, STALL]) == "таймаут"
    assert target.uniform([HTTP_403, HTTP_404]) == ""  # разные коды — не «одна ошибка»
    assert target.uniform([HTTP_403, TIMEOUT]) == ""
    assert target.uniform([HTTP_403, GOOD]) == ""  # у кого-то проба прошла
    assert target.uniform([HTTP_403, FROZEN]) == ""  # «заморозка» — это про сервер
    assert target.uniform([FROZEN, FROZEN]) == ""
    assert target.uniform([]) == ""


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


def test_timeouts_need_a_working_base_request():
    """Одинаковые таймауты бывают и у мёртвых серверов; а probe.url напрямую может быть
    просто закрыт провайдером — поэтому прямой запрос тут ничего не решает."""
    dead = target.diagnose([TIMEOUT, STALL], base_ping=lambda: False, direct=_never)
    assert not dead.down and dead.signature == "таймаут"  # прямой запрос даже не делался
    down = target.diagnose([TIMEOUT, STALL], base_ping=lambda: True, direct=lambda: "нет ответа")
    assert down.down and "напрямую — нет ответа" in down.detail
    assert down.text.startswith(WARNING)


def test_mixed_results_ask_nothing_and_blame_nobody():
    for results in ([HTTP_403, GOOD], [FROZEN, FROZEN], [RESET, TIMEOUT], []):
        verdict = target.diagnose(results, base_ping=_never, direct=_never)
        assert not verdict.down and verdict.signature == ""


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
    assert seen["bootstrap"] == cfg.dns.bootstrap  # с меткой — свой резолвер, мимо перехвата
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
