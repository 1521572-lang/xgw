"""Волна 4 (ASSUMPTIONS п. 342): пустой ответ, страница HTML, заглушка и сбой сети не затирают
набор подписки, причина своя; в статусе время успеха, возраст набора и причина, без секретов."""

import json
import logging
import time

import pytest
from test_daemon import Harness, _started

from xgw import engine, fetch
from xgw.config import Config, Subscription
from xgw.paths import Paths
from xgw.store import EXPIRED_REASON, SubscriptionCache
from xgw.watch.status import render_status

ALIVE = ("vless://11111111-2222-3333-4455-6666666666a2@alive.example.net:443?type=tcp"
         "&security=tls&sni=alive.example.net#DE%20alive")
OTHER = ("vless://11111111-2222-3333-4455-6666666666a3@other.example.net:443?type=tcp"
         "&security=tls&sni=other.example.net#NL%20other")
JUNK = ("vless://11111111-2222-3333-4455-6666666666a2@0.0.0.0:1?type=tcp"
        "&security=tls&sni=x.example.net#stub")
LOG = logging.getLogger("test")


@pytest.fixture()
def daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.speed.sticky = False
    cfg.speed.unlimited_hours = cfg.speed.limited_hours = 0
    instance = Harness(cfg, paths)
    yield instance
    instance.store.close()


def _loader(tmp_path, monkeypatch, answers):
    cache = SubscriptionCache(tmp_path / "cache")
    sub = Subscription(name="main", url="https://subs.example.org/secret-token-value")
    replies = iter(answers)

    def fake(url, **_kwargs):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return fetch.FetchResult(status=200, headers={}, body=reply, url=url)

    monkeypatch.setattr(engine.fetch, "fetch_subscription", fake)
    return cache, lambda: engine._load_subscription(sub, Config(), cache, None, None, LOG)


def test_bad_answers_keep_the_set_and_say_why(tmp_path, monkeypatch):
    html = b"<!DOCTYPE html><html><body>login</body></html>"
    cache, load = _loader(tmp_path, monkeypatch, [
        ALIVE.encode(), html, b"  ", chr(0xFEFF).encode() + b"<html></html>", JUNK.encode(),
        fetch.FetchError("https://subs.example.org/secret-token-value: нет ответа"),
    ])
    assert load()[0]
    saved = (cache.load("main").body, cache.saved_at("main"))
    reasons = []
    for _ in range(5):
        raws, _info, error = load()
        assert len(raws) == 1  # прежний набор на месте
        reasons.append(error)
    assert "HTML" in reasons[0] and "пустой ответ" in reasons[1] and "HTML" in reasons[2]
    assert "служебные адреса" in reasons[3]
    assert "secret-token-value" not in reasons[4]
    assert (cache.load("main").body, cache.saved_at("main")) == saved  # кэш не тронут


def test_first_bad_answer_without_a_set_gives_nothing(tmp_path, monkeypatch):
    _cache, load = _loader(tmp_path, monkeypatch, [b"<html></html>"])
    raws, _info, error = load()
    assert raws == [] and "HTML" in error


def test_good_answers_are_not_mistaken_for_a_page():
    assert engine.body_problem(ALIVE.encode()) == ""
    assert engine.body_problem(b'{"outbounds": []}') == ""


def test_status_shows_last_success_age_and_reason(daemon):
    _started(daemon)
    SubscriptionCache(daemon.paths.cache_dir).save("main", ALIVE.encode())
    daemon.store.set_meta("sub_errors", json.dumps(
        {"main": {"error": "вместо подписки пришла страница HTML", "ts": daemon.wall()}}))
    snapshot = {"subscriptions": [{"name": "main", "limited": True}]}
    daemon._subscription_status(snapshot)
    entry = snapshot["subscriptions"][0]
    assert entry["last_ok_ts"] and entry["set_age_s"] is not None
    assert entry["cache_reason"] == "вместо подписки пришла страница HTML"
    text = render_status(daemon.status() | snapshot)
    assert "не обновилась (вместо подписки пришла страница HTML) — в работе набор от" in text


@pytest.mark.parametrize(("offset", "kept"), [(-60, False), (3600, True)])
def test_saved_set_lives_only_until_the_subscription_expires(tmp_path, monkeypatch, offset, kept):
    cache, load = _loader(tmp_path, monkeypatch, [fetch.FetchError("нет ответа")])
    expire = int(time.time()) + offset
    cache.save("main", ALIVE.encode(), {"expire": expire})
    saved = cache.saved_at("main")
    raws, info, error = load()
    assert bool(raws) is kept and info == {"expire": expire}  # окну и панели срок виден
    assert error.startswith(EXPIRED_REASON) is not kept
    assert cache.saved_at("main") == saved  # продление подписки вернёт её обычным опросом


def test_fresh_answer_is_not_cut_by_the_old_expiry(tmp_path, monkeypatch):
    cache, load = _loader(tmp_path, monkeypatch, [ALIVE.encode()])
    cache.save("main", ALIVE.encode(), {"expire": int(time.time()) - 60})
    raws, _info, error = load()
    assert raws and error == ""


@pytest.mark.parametrize(("saved", "complete", "sources"), [
    ({"expire": 1}, True, ["new"]),  # истёкшая не держит остальные подписки
    ({"expire": 0}, True, ["old", "new"]),  # срока нет: сбой, работает старый набор
    (None, False, ["new"]),  # временный сбой без набора: неполный список не применяется
])
def test_expired_subscription_leaves_without_blocking_others(
        tmp_path, monkeypatch, saved, complete, sources):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.subscriptions = [Subscription(name="old", url="https://subs.example.org/old"),
                         Subscription(name="new", url="https://subs.example.org/new")]
    if saved is not None:
        SubscriptionCache(paths.cache_dir).save("old", ALIVE.encode(), saved)

    def fake(url, **_kwargs):
        if url.endswith("/old"):
            raise fetch.FetchError("нет ответа")
        return fetch.FetchResult(status=200, headers={}, body=OTHER.encode(), url=url)

    monkeypatch.setattr(engine.fetch, "fetch_subscription", fake)
    inventory = engine.collect(cfg, paths, mark=None, logger=LOG, via_xray=False)
    assert inventory.complete is complete
    assert [node.source for node in inventory.nodes] == sources


def test_status_does_not_promise_a_set_of_an_expired_subscription():
    entry = {"name": "main", "limited": True, "last_ok_ts": 1_700_000_000.0,
             "cache_reason": f"{EXPIRED_REASON} (нет ответа)"}
    text = render_status({"subscriptions": [entry]})
    assert EXPIRED_REASON in text and "в работе набор" not in text


def test_status_without_a_problem_or_a_saved_set(daemon):
    _started(daemon)
    daemon.store.set_meta("sub_errors", "{broken")
    snapshot = {"subscriptions": [{"name": "нет такой", "limited": False}, "мусор"]}
    daemon._subscription_status(snapshot)
    entry = snapshot["subscriptions"][0]
    assert entry["last_ok_ts"] is None and entry["set_age_s"] is None
    assert entry["cache_reason"] is None
    assert "не обновилась" not in render_status(daemon.status() | {
        "subscriptions": [entry]})
