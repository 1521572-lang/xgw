"""Сборка конфига: карантин доменов, которых нет в DNS, и сводка разбора подписок."""

import base64
import json
import logging
import threading

import links
import pytest

from xgw import engine, fetch
from xgw.config import Config, Subscription
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths
from xgw.store import Store, SubscriptionCache

LOG = logging.getLogger("test")


def _vless(host: str, name: str, suffix: str) -> str:
    return (
        f"vless://11111111-2222-3333-4455-6666666666{suffix}@{host}:443?"
        f"security=tls&sni={host}&type=tcp#{name}"
    )


GONE = _vless("gone.example.net", "FR%20gone", "a1")
ALIVE = _vless("alive.example.net", "DE%20alive", "a2")
SERVICE = "vless://11111111-2222-3333-4455-6666666666a3@127.0.0.1:443?type=tcp#service"
EXPIRES = _vless("203.0.113.90", "expire%202026-12-01", "a4")


def _inventory(*link_list: str) -> engine.Inventory:
    raws, _meta, _warnings = parse_links_text("\n".join(link_list), "main")
    return engine.Inventory([raw_to_node(raw, "main") for raw in raws])


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    found = Paths.from_env()
    found.ensure()
    return found


@pytest.fixture()
def dns(monkeypatch):
    """Подставной DNS: что знает — отдаёт, имя из gone — «такого нет», прочее — сбой."""
    book = {"alive.example.net": ["203.0.113.50"]}
    gone = {"gone.example.net"}
    asked: list[str] = []

    def resolve(name, bootstrap, mark):
        asked.append(name)
        if name in gone:
            raise fetch.NoSuchDomain(f"домен {name} не разрешается: такого имени нет (NXDOMAIN)")
        if name in book:
            return book[name]
        raise fetch.ResolveError(f"не удалось разрешить {name}: таймаут")

    monkeypatch.setattr(engine, "resolve_domain", resolve)
    resolve.asked, resolve.gone, resolve.book = asked, gone, book
    return resolve


def _assemble(paths, inventory, cfg=None):
    cfg = cfg or Config()
    return engine.assemble(cfg, paths, inventory, mark=None, logger=LOG, xray_bin=None,
                           check=False)


def test_server_with_a_dead_domain_is_set_aside_and_not_asked_again(paths, dns, caplog):
    """Домена нет в DNS (так было с *.aib2bsas.online): сервер в конфиг не попадает и
    пробы на него не тратятся; при следующих сборках имя даже не спрашивается."""
    inventory = _inventory(links.VLESS_REALITY, GONE, ALIVE)
    with caplog.at_level(logging.WARNING):
        assembly = _assemble(paths, inventory)
    names = [node.name for node in [*assembly.selection.members, *assembly.selection.spares]]
    assert "FR gone" not in names and "DE alive" in names and len(names) == 2
    text = json.dumps(assembly.result.config, ensure_ascii=False)
    assert "gone.example.net" not in text
    assert assembly.result.config["dns"]["hosts"] == {"alive.example.net": ["203.0.113.50"]}
    assert assembly.selection.stats["dns"] == 1
    assert engine.quarantined() == frozenset({"gone.example.net"})
    assert "повторная проверка через 6 ч" in caplog.text

    dns.asked.clear()
    _assemble(paths, inventory)
    assert "gone.example.net" not in dns.asked  # карантин: резолверы не дёргаем


def test_quarantine_ends_after_six_hours_or_on_request(paths, dns, monkeypatch):
    inventory = _inventory(links.VLESS_REALITY, GONE)
    _assemble(paths, inventory)
    assert engine.quarantined()
    dns.gone.clear()
    dns.book["gone.example.net"] = ["203.0.113.77"]  # владелец вернул домен

    assert len(_assemble(paths, inventory).result.nodes) == 1  # срок ещё не вышел
    clock = engine.time.monotonic()
    monkeypatch.setattr(engine.time, "monotonic", lambda: clock + 6 * 3600 + 1)
    assert engine.quarantined() == frozenset()
    assert len(_assemble(paths, inventory).result.nodes) == 2

    # Кнопка «Обновить» в панели проверяет отложенные домены сразу.
    dns.gone.add("gone.example.net")
    _assemble(paths, inventory)  # прежний ответ ещё в кэше на четверть часа
    engine._hosts_cache.clear()
    _assemble(paths, inventory)
    assert engine.quarantined()
    engine.forget_quarantine()
    assert engine.quarantined() == frozenset()


def test_resolver_failure_does_not_drop_servers(paths, dns):
    """Нет сети или резолверы не отвечают — это не «домена нет»: иначе при отключении
    интернета из конфига пропали бы все серверы с доменными именами."""
    unknown = _vless("unknown.example.net", "NL%20unknown", "a5")
    assembly = _assemble(paths, _inventory(links.VLESS_REALITY, unknown))
    assert len(assembly.result.nodes) == 2 and engine.quarantined() == frozenset()
    assert assembly.selection.stats["dns"] == 0


def test_no_usable_server_because_of_dns_is_said_plainly(paths, dns):
    with pytest.raises(engine.EngineError, match="домены серверов не разрешаются"):
        _assemble(paths, _inventory(GONE))
    engine.forget_quarantine()
    with pytest.raises(engine.EngineError, match="после фильтров не осталось серверов"):
        _assemble(paths, _inventory(SERVICE))


def test_summary_counts_what_was_dropped_and_merged(paths, dns):
    """«Узлов: N активных, K запасных (отброшено X недоступных/служебных, схлопнуто Y
    дублей)» — из чего складываются числа."""
    cfg = Config()
    cfg.filters.max_members = 1
    duplicate = links.VLESS_REALITY.rsplit("#", 1)[0] + "#NL%20copy"
    inventory = _inventory(
        links.VLESS_REALITY, duplicate, links.TROJAN, GONE, SERVICE, EXPIRES, ALIVE)
    assembly = _assemble(paths, inventory, cfg)
    summary = engine.summary(assembly)
    assert summary == {
        "members": 1, "spares": 2,
        "dropped": 3,  # домен без адреса, служебный адрес и запись «expire» (фильтр имён)
        "duplicates": 1, "excluded": 0, "dns": 1,
    }
    assert assembly.selection.stats["total"] == 7

    engine.persist(paths, assembly, {})
    store = Store(paths.db_file)
    try:
        assert json.loads(store.get_meta("nodes_summary")) == summary
    finally:
        store.close()

    # Отключённый в панели сервер считается отдельно: это выбор человека, а не сбой.
    cfg.managed.disabled = [assembly.selection.spares[0].fingerprint]
    again = engine.summary(_assemble(paths, inventory, cfg))
    assert again["excluded"] == 1 and again["spares"] == 1 and again["dropped"] == 3


def test_server_list_for_the_panel_names_the_dns_reason(paths, dns):
    inventory = _inventory(links.VLESS_REALITY, GONE)
    _assemble(paths, inventory)
    engine.save_inventory(paths, Config(), inventory)
    listed = {item["name"]: item["skip"] for item in engine.load_inventory(paths)}
    assert listed == {"🇳🇱 NL-1": "", "FR gone": "dns"}


# --- заглушки подписок: служебные адреса не считаются серверами ---------------------

STUB = "vless://00000000-0000-0000-0000-000000000000@0.0.0.0:1?type=tcp#stub"


def _subscription_body(*link_list: str) -> bytes:
    return base64.b64encode("\n".join(link_list).encode("utf-8"))


def _stub_fetch(monkeypatch, body: bytes | Exception) -> None:
    """Подставной запрос подписки: заданное тело ответа или исключение."""
    def fake(url, **_kwargs):
        if isinstance(body, Exception):
            raise body
        return fetch.FetchResult(status=200, headers={}, body=body, url=url)

    monkeypatch.setattr(engine.fetch, "fetch_subscription", fake)


def _load_subscription(cache: SubscriptionCache) -> tuple[list, str]:
    sub = Subscription(name="main", url="https://subs.example.org/token")
    raws, _userinfo, error = engine._load_subscription(sub, Config(), cache, None, None, LOG)
    return raws, error


def test_subscription_stub_counts_as_failure_and_is_not_cached(tmp_path, monkeypatch):
    """Заглушка провайдера («сервер» 0.0.0.0:1) — сбой: в кэш не попадает."""
    cache = SubscriptionCache(tmp_path / "cache")
    _stub_fetch(monkeypatch, _subscription_body(STUB))
    raws, error = _load_subscription(cache)
    assert raws == [] and error
    assert cache.load("main") is None


def test_subscription_stub_keeps_the_last_good_cache(tmp_path, monkeypatch):
    """После удачной выборки заглушка не затирает кэш: серверы берутся из него."""
    cache = SubscriptionCache(tmp_path / "cache")
    _stub_fetch(monkeypatch, _subscription_body(ALIVE))
    raws, error = _load_subscription(cache)
    assert [raw.address for raw in raws] == ["alive.example.net"] and error == ""

    _stub_fetch(monkeypatch, _subscription_body(STUB))
    raws, error = _load_subscription(cache)
    assert [raw.address for raw in raws] == ["alive.example.net"] and error
    assert cache.load("main").body == _subscription_body(ALIVE)


def test_subscription_with_junk_and_real_servers_keeps_only_real(tmp_path, monkeypatch):
    """В смешанном ответе служебные адреса отброшены, настоящие серверы остаются."""
    cache = SubscriptionCache(tmp_path / "cache")
    _stub_fetch(monkeypatch, _subscription_body(STUB, ALIVE, SERVICE))
    raws, error = _load_subscription(cache)
    assert [raw.address for raw in raws] == ["alive.example.net"] and error == ""


def test_junk_only_cache_is_a_plain_failure(tmp_path, monkeypatch):
    """Старый кэш из одной заглушки серверами не считается: честный сбой."""
    cache = SubscriptionCache(tmp_path / "cache")
    cache.save("main", _subscription_body(STUB))
    _stub_fetch(monkeypatch, fetch.FetchError("сеть недоступна"))
    raws, error = _load_subscription(cache)
    assert raws == [] and error


# --- остановка демона посреди опроса (наблюдение Н1 отчёта о Д1/Д2) ----------------

FIRST, SECOND = "https://subs.example.org/first", "https://subs.example.org/second"


def _two_subscriptions() -> Config:
    cfg = Config()
    cfg.subscriptions = [Subscription(name="main", url=FIRST),
                         Subscription(name="second", url=SECOND)]
    return cfg


def test_stop_during_a_poll_skips_the_direct_route_and_the_cache(paths, monkeypatch, caplog):
    """SIGTERM, пока подписка шла через Xray: прямого запроса (до 4 попыток с паузами) и
    следующей подписки нет, кэш не подставляется и не меняется — опрос просто прерван."""
    cache = SubscriptionCache(paths.cache_dir)
    cache.save("main", _subscription_body(ALIVE))
    saved = cache.saved_at("main")
    monkeypatch.setattr(engine, "healthy_http_in", lambda _cfg: ("127.0.0.1", 10809))
    cancel = threading.Event()
    asked: list[tuple[str, object]] = []

    def fake(url, **kwargs):
        asked.append((url, kwargs["proxy"]))
        kwargs["cancel"].set()  # остановка пришла, а попытка через Xray не удалась
        raise fetch.FetchError("timed out")

    monkeypatch.setattr(engine.fetch, "fetch_subscription", fake)
    with caplog.at_level(logging.INFO), pytest.raises(fetch.Cancelled):
        engine.collect(_two_subscriptions(), paths, mark=None, logger=LOG, cancel=cancel)
    assert asked == [(FIRST, ("127.0.0.1", 10809))]
    assert cache.load("main").body == _subscription_body(ALIVE)
    assert cache.saved_at("main") == saved
    assert cache.load("second") is None
    assert "используется кэш" not in caplog.text


def test_stop_after_one_subscription_does_not_ask_the_next(paths, monkeypatch):
    """Остановка между подписками: следующая не запрашивается. Полученная до остановки
    подписка — обычный удачный ответ, её кэш обновлён."""
    monkeypatch.setattr(engine, "healthy_http_in", lambda _cfg: None)
    cancel = threading.Event()
    asked: list[str] = []

    def fake(url, **kwargs):
        asked.append(url)
        kwargs["cancel"].set()
        return fetch.FetchResult(status=200, headers={}, body=_subscription_body(ALIVE), url=url)

    monkeypatch.setattr(engine.fetch, "fetch_subscription", fake)
    with pytest.raises(fetch.Cancelled):
        engine.collect(_two_subscriptions(), paths, mark=None, logger=LOG, cancel=cancel)
    assert asked == [FIRST]
    assert SubscriptionCache(paths.cache_dir).load("main").body == _subscription_body(ALIVE)


# --- кэш адресов подписок при живом Xray (отчёт 0.2.0, дефект 1) --------------------------------


def test_subscription_via_xray_checks_its_direct_address_once_a_day(tmp_path, monkeypatch):
    """При живом Xray подписка всегда идёт через него, и прямого запроса, после которого адрес
    записывался в dns-cache.json, не было вовсе. Теперь прямой путь проверяется рукопожатием TLS
    (без запроса HTTP) раз в сутки; неудача — снова через 6 часов; без метки — не проверяется."""
    from xgw.store import HOST_CHECK_EVERY, HOST_CHECK_RETRY, HostCache

    now = [1_000_000.0]
    monkeypatch.setattr(engine.time, "time", lambda: now[0])
    engine._direct_failed.clear()
    cache = SubscriptionCache(tmp_path / "cache")
    hosts = HostCache(tmp_path / "cache", clock=lambda: now[0])
    _stub_fetch(monkeypatch, _subscription_body(ALIVE))
    checked: list[tuple] = []
    answer: list = ["203.0.113.8"]

    def check(host, port, *, bootstrap, mark, cancel=None, timeout=5.0):
        checked.append((host, port, mark))
        if isinstance(answer[0], Exception):
            raise answer[0]
        return answer[0]

    monkeypatch.setattr(engine.fetch, "check_direct", check)
    sub = Subscription(name="main", url="https://subs.example.org/token")

    def load(mark=0xFF):
        raws, _userinfo, error = engine._load_subscription(
            sub, Config(), cache, mark, ("127.0.0.1", 10809), LOG, hosts=hosts)
        assert raws and not error

    load()
    assert checked == [("subs.example.org", 443, 0xFF)]
    assert hosts.addresses() == {"subs.example.org": ["203.0.113.8"]}
    now[0] += 3600
    load()
    load(mark=None)
    assert len(checked) == 1  # в пределах суток и без метки — не проверяется
    now[0] += HOST_CHECK_EVERY
    answer[0] = OSError("timed out")
    load()
    now[0] += 3600
    load()
    assert len(checked) == 2  # неудача — повтор не раньше чем через 6 часов
    now[0] += HOST_CHECK_RETRY
    answer[0] = "203.0.113.9"
    load()
    assert len(checked) == 3
    assert hosts.addresses() == {"subs.example.org": ["203.0.113.9", "203.0.113.8"]}
    engine._direct_failed.clear()


def test_direct_fetch_logs_a_new_cache_address_once(tmp_path, monkeypatch, caplog):
    """Прямой запрос подписки записывает адрес её сервера в кэш: новый адрес — одна строка в
    журнале, тот же адрес на следующих обновлениях — молча (перепроверка 0.2.0, наблюдение 1)."""
    from xgw.store import HostCache

    def fake(url, **_kwargs):
        return fetch.FetchResult(status=200, headers={}, body=_subscription_body(ALIVE), url=url,
                                 host="subs.example.org", address="203.0.113.8")

    monkeypatch.setattr(engine.fetch, "fetch_subscription", fake)
    cache = SubscriptionCache(tmp_path / "cache")
    hosts = HostCache(tmp_path / "cache")
    sub = Subscription(name="main", url="https://subs.example.org/token")
    caplog.set_level(logging.INFO, logger="test")
    for _ in range(3):
        raws, _userinfo, error = engine._load_subscription(
            sub, Config(), cache, None, None, LOG, hosts=hosts)
        assert raws and not error
    lines = [r.getMessage() for r in caplog.records if "записан в кэш адресов" in r.getMessage()]
    assert len(lines) == 1 and lines[0].startswith("подписка main (subs.example.org): получена "
                                                   "напрямую, адрес её сервера записан")
    assert "203.0.113.8" not in lines[0]  # адреса подписок в журнал не пишутся
    assert hosts.addresses() == {"subs.example.org": ["203.0.113.8"]}
