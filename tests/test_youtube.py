"""Проверка YouTube через сервер (М3, watch/youtube.py): доступность сайта и видеосети, скорость
с серверов Google вместе с трафиком клиентов, ключи speed.youtube_*."""

from types import SimpleNamespace

import pytest

from xgw import config
from xgw.config import Config
from xgw.generator.builder import NodeInfo
from xgw.watch import youtube
from xgw.watch.checks import DownloadResult

NODE = SimpleNamespace(tag="proxy-de-aaaa", probe_port=20001)
SITE, VIDEO = config.DEFAULT_YOUTUBE_URLS
FILE = config.DEFAULT_YOUTUBE_SPEED_URL
ANSWER = DownloadResult(ok=True, status=204)


def _fake(monkeypatch, results: dict[str, DownloadResult]) -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []

    def get(_host, _port, url, **kwargs):
        calls.append((url, kwargs.get("range_end", 0)))
        return results[url]

    monkeypatch.setattr(youtube, "http_get_via_proxy", get)
    return calls


def test_youtube_is_blocked_when_the_video_network_does_not_answer(monkeypatch):
    calls = _fake(monkeypatch, {
        SITE: ANSWER, VIDEO: DownloadResult(ok=False, kind="tls", error="TLS: reset")})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.BLOCKED
    assert verdict.error == "redirector.googlevideo.com: TLS: reset"
    assert [url for url, _end in calls] == [SITE, VIDEO]  # файл Google уже не качается
    assert youtube.problem({"state": "blocked"}) == "не пропускает YouTube"


def test_youtube_redirect_is_an_answer_and_the_speed_decides(monkeypatch):
    """Переадресация — тоже ответ YouTube через сервер. 1 МБ за 4 с — 2 Мбит/с: тормозит;
    клиенты через этот сервер уже качают 4 Мбит/с — вместе хватает."""
    slow = DownloadResult(ok=True, downloaded=1_000_000, status=206, body_seconds=4.0)
    calls = _fake(monkeypatch, {
        SITE: DownloadResult(ok=False, kind="http", status=302, error="HTTP 302"),
        VIDEO: ANSWER, FILE: slow})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.SLOW and verdict.mbps == 2.0
    assert calls[-1] == (FILE, 4_000_000)  # кусок файла (Range), а не весь архив
    assert youtube.check(NODE, Config(), probe_pass="x", client_mbps=4.0).state == youtube.OK
    assert youtube.problem({"state": "slow", "mbps": 2.0, "client": 1.5}) == (
        "тормозит на YouTube (2,0 Мбит/с с серверов Google и 1,5 Мбит/с у клиентов)")


def test_youtube_speed_file_failures(monkeypatch):
    """Отчёт youtube2: файл Google не отдан с ошибкой HTTP — замер по запасному файлу; не отдан и
    он — «скорость не узнать», неудача. Тишина посреди тела — тормозит. Лимитированный сервер —
    без файла."""
    missing = DownloadResult(ok=False, kind="http", status=404, error="HTTP 404")
    calls = _fake(monkeypatch, {SITE: ANSWER, VIDEO: ANSWER, FILE: missing,
                                youtube.SPARE_URL: DownloadResult(
                                    ok=True, downloaded=4_000_000, status=206, body_seconds=2.0)})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.OK and verdict.mbps == 16.0
    assert verdict.error == "основной файл замера: HTTP 404 от dl.google.com; замер по запасному"
    assert [url for url, _end in calls[2:]] == [FILE, youtube.SPARE_URL]
    _fake(monkeypatch, {SITE: ANSWER, VIDEO: ANSWER, FILE: missing,
                        youtube.SPARE_URL: DownloadResult(
                            ok=False, kind="http", status=403, error="HTTP 403")})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.UNKNOWN and verdict.mbps is None
    assert verdict.error == ("файл замера Google: HTTP 404 от dl.google.com; запасной: HTTP 403 "
                             "от dl.google.com")
    assert youtube.problem({"state": "unknown"}).startswith("не даёт замерить скорость YouTube")
    assert youtube.summary(verdict).startswith("скорость не узнать (файл замера Google: HTTP 404")
    stall = DownloadResult(ok=False, downloaded=200_000, stalled=True, kind="stall",
                           body_seconds=6.0, error="тишина 5 с после 200000 байт тела")
    _fake(monkeypatch, {SITE: ANSWER, VIDEO: ANSWER, FILE: stall})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.SLOW and verdict.mbps == 0.3
    calls = _fake(monkeypatch, {SITE: ANSWER, VIDEO: ANSWER})
    assert youtube.check(NODE, Config(), probe_pass="x", speed=False).state == youtube.OK
    assert len(calls) == 2


def test_youtube_settings_are_checked(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[speed]\nyoutube_urls = ["ftp://x"]\n'
                    'youtube_speed_url = "file:///etc/hosts"\nyoutube_minutes = 1\n',
                    encoding="utf-8")
    cfg, warnings = config.load(path)
    assert not cfg.speed.youtube and cfg.speed.youtube_urls == []
    assert cfg.speed.youtube_speed_url == config.DEFAULT_YOUTUBE_SPEED_URL
    assert cfg.speed.youtube_minutes == 30
    assert any("speed.youtube_urls пуст" in item for item in warnings)
    defaults = Config().speed
    assert defaults.youtube and defaults.youtube_mbps == 5
    assert defaults.youtube_urls == list(config.DEFAULT_YOUTUBE_URLS)


def test_youtube_speed_file_follows_google_redirects(monkeypatch):
    """Отчёт youtube 01.11.2026: у 7 серверов пула из 8 скорость не замерялась — dl.google.com
    отдавал файл переадресацией на узел кэша Google. По ней проверка идёт (только к Google);
    переадресация не к Google — скорость не узнать."""
    hop = "https://redirector.gvt1.com/edgedl/go/go1.22.5.linux-amd64.tar.gz"
    cache = "https://r3---sn-abcd.gvt1.com/edgedl/go/go1.22.5.linux-amd64.tar.gz"
    slow = DownloadResult(ok=True, downloaded=1_000_000, status=206, body_seconds=4.0)
    calls = _fake(monkeypatch, {
        SITE: ANSWER, VIDEO: ANSWER,
        FILE: DownloadResult(ok=False, kind="http", status=302, error="HTTP 302", location=hop),
        hop: DownloadResult(ok=False, kind="http", status=302, error="HTTP 302", location=cache),
        cache: slow})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.SLOW and verdict.mbps == 2.0
    assert calls[2:] == [(FILE, 4_000_000), (hop, 4_000_000), (cache, 4_000_000)]
    away = DownloadResult(ok=False, kind="http", status=302, error="HTTP 302",
                          location="https://block.example/")
    missing = DownloadResult(ok=False, kind="http", status=404, error="HTTP 404")
    _fake(monkeypatch, {
        SITE: ANSWER, VIDEO: ANSWER, FILE: away,
        youtube.SPARE_URL: DownloadResult(ok=False, kind="http", status=302, error="HTTP 302",
                                          location=hop),
        hop: DownloadResult(ok=False, kind="http", status=302, error="HTTP 302", location=cache),
        cache: missing})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.UNKNOWN and verdict.mbps is None
    assert verdict.error == ("файл замера Google: переадресация не к Google; запасной: HTTP 404 "
                             "от узла кэша Google после переадресаций: 2")


def test_youtube_speed_cut_by_time_is_slow(monkeypatch):
    """За 8 с пришло меньше 256 КБ — это не «файл мал», а «тормозит»."""
    crawl = DownloadResult(ok=True, downloaded=100_000, status=206, body_seconds=8.0)
    _fake(monkeypatch, {SITE: ANSWER, VIDEO: ANSWER, FILE: crawl})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.SLOW and verdict.mbps == 0.1


# --- п. 348: выход для видео -----------------------------------------------------------------


FP = {"a": "a" * 16, "b": "b" * 16, "c": "c" * 16}
NOW = 100_000.0


def _info(name, role="proxy"):
    return NodeInfo(fingerprint=FP[name], tag=f"{role}-x-{name}", probe_tag=f"probe-x-{name}",
                    probe_port=20000, role=role)


def _good(mbps=20.0, **extra):
    return {"state": youtube.OK, "fails": 0, "mbps": mbps, "ts": NOW - 60, **extra}


def _pick(records, *, nodes=None, alive=("a", "b", "c"), prices=None):
    nodes = nodes if nodes is not None else [_info("a"), _info("b")]
    observatory = {f"proxy-x-{name}": {"alive": name in alive, "delay": 0.1} for name in FP}
    return youtube.media_candidates(
        nodes, records, observatory,
        prices if prices is not None else dict.fromkeys(FP.values(), 0.0),
        NOW, min_mbps=5, sample_ttl=3600.0)


@pytest.mark.parametrize("record", [
    None,
    {},
    _good(ts=NOW - 7200),
    {**_good(), "state": youtube.UNKNOWN},
    {**_good(), "state": "cancelled"},
    {**_good(), "state": youtube.SLOW},
    {**_good(), "state": youtube.BLOCKED},
    {**_good(), "fails": 1},
    _good(mbps=None),
    _good(mbps=4.9),
], ids=["no-record", "empty", "stale", "unknown", "cancelled", "slow", "blocked", "failed-once",
        "no-speed", "below-threshold"])
def test_media_candidate_needs_a_fresh_good_sample(record):
    assert _pick({FP["a"]: record} if record is not None else {}) == []


def test_media_candidate_excludes_other_roles_dead_and_limited():
    records = {FP["a"]: _good()}
    assert _pick(records, alive=()) == []
    assert _pick(records, nodes=[_info("a", "spare")]) == []
    assert _pick(records, nodes=[_info("a", "pool")]) == []
    assert _pick(records, prices={FP["a"]: 1.0}) == []
    assert _pick(records, prices={}) == []  # цена неизвестна — данных нет, это не «безлимитный»


def test_media_plan_takes_the_best_and_breaks_ties_by_tag():
    candidates = _pick({FP["a"]: _good(10.0), FP["b"]: _good(30.0)})
    assert youtube.media_plan(candidates, (), gain_pct=30) == ("proxy-x-b",)
    equal = _pick({FP["a"]: _good(20.0), FP["b"]: _good(20.0)})
    assert youtube.media_plan(equal, (), gain_pct=30) == ("proxy-x-a",)


def test_media_plan_keeps_the_previous_within_the_gain():
    candidates = _pick({FP["a"]: _good(20.0), FP["b"]: _good(25.0)})
    assert youtube.media_plan(candidates, ("proxy-x-a",), gain_pct=30) == ("proxy-x-a",)
    faster = _pick({FP["a"]: _good(20.0), FP["b"]: _good(26.0)})
    assert youtube.media_plan(faster, ("proxy-x-a",), gain_pct=30) == ("proxy-x-b",)
    assert youtube.media_plan([], ("proxy-x-a",), gain_pct=30) == ()


def test_busy_exit_is_not_dropped_for_its_own_clients():
    """Выход, через который уже идёт видео, своей загрузкой не разогнать (как в check)."""
    busy = _pick({FP["a"]: _good(2.0, client=20.0)})
    assert [(info.tag, total) for info, total in busy] == [("proxy-x-a", 22.0)]
    assert _pick({FP["a"]: _good(2.0)}) == []  # чужая загрузка в чужой записи не считается
