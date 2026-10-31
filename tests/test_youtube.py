"""Проверка YouTube через сервер (М3, watch/youtube.py): доступность сайта и видеосети, скорость
с серверов Google вместе с трафиком клиентов, ключи speed.youtube_*."""

from types import SimpleNamespace

from xgw import config
from xgw.config import Config
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
    """Файл Google не отдан с ошибкой HTTP — скорость не узнать, а YouTube отвечает: годен.
    Тишина посреди тела — тормозит. Лимитированный сервер — без файла."""
    _fake(monkeypatch, {SITE: ANSWER, VIDEO: ANSWER,
                        FILE: DownloadResult(ok=False, kind="http", status=403, error="HTTP 403")})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.OK and verdict.mbps is None and "HTTP 403" in verdict.error
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
    _fake(monkeypatch, {SITE: ANSWER, VIDEO: ANSWER, FILE: DownloadResult(
        ok=False, kind="http", status=302, error="HTTP 302", location="https://block.example/")})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.OK and verdict.mbps is None
    assert verdict.error == "файл замера Google: переадресация не к Google"


def test_youtube_speed_cut_by_time_is_slow(monkeypatch):
    """За 8 с пришло меньше 256 КБ — это не «файл мал», а «тормозит»."""
    crawl = DownloadResult(ok=True, downloaded=100_000, status=206, body_seconds=8.0)
    _fake(monkeypatch, {SITE: ANSWER, VIDEO: ANSWER, FILE: crawl})
    verdict = youtube.check(NODE, Config(), probe_pass="x")
    assert verdict.state == youtube.SLOW and verdict.mbps == 0.1
