"""Тесты хранилища состояния (SQLite)."""

import stat

from xgw.store import Store, SubscriptionCache


def test_store_roundtrip(tmp_path):
    store = Store(tmp_path / "state.db")
    store.set_meta("xray_tag", "v25.7.23")
    store.upsert_nodes(
        [
            {
                "fingerprint": "abc12345",
                "tag": "proxy-nl-abc1",
                "role": "proxy",
                "name": "NL-1",
                "source": "main",
                "address": "203.0.113.10",
                "port": 443,
                "updated": 1000,
            }
        ]
    )
    store.add_event("generate", "участников: 1")
    assert store.get_meta("xray_tag") == "v25.7.23"
    nodes = store.all_nodes()
    assert len(nodes) == 1 and nodes[0]["tag"] == "proxy-nl-abc1"
    events = store.recent_events()
    assert events[0]["kind"] == "generate"
    assert "участников" in store.dump_state()
    store.close()


def test_replace_nodes_drops_vanished_servers(tmp_path):
    store = Store(tmp_path / "state.db")
    row = {"tag": "proxy-nl-abc1", "role": "proxy", "name": "NL-1", "source": "main",
           "address": "203.0.113.10", "port": 443, "updated": 1000}
    store.replace_nodes([{**row, "fingerprint": "abc12345"}, {**row, "fingerprint": "def67890"}])
    store.replace_nodes([{**row, "fingerprint": "def67890"}])
    assert [node["fingerprint"] for node in store.all_nodes()] == ["def67890"]
    store.close()


def test_subscription_cache_roundtrip(tmp_path):
    cache = SubscriptionCache(tmp_path / "cache")
    assert cache.load("main") is None
    cache.save("main", b"vless://...", {"total": 100, "download": 40})
    cache.save("другая/подписка", b"second")  # имя с небезопасными для файла символами
    cached = cache.load("main")
    assert cached.body == b"vless://..."
    assert cached.userinfo == {"total": 100, "download": 40}
    assert cached.saved_at > 0
    assert cache.load("другая/подписка").body == b"second"
    files = sorted(path.name for path in (tmp_path / "cache").iterdir())
    assert len(files) == 4 and all("/" not in name and ".." not in name for name in files)


def test_subscription_cache_is_private(tmp_path):
    cache = SubscriptionCache(tmp_path / "cache")
    cache.save("main", b"secret links")
    for path in (tmp_path / "cache").iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_scans_are_keyed_by_probe_tag(tmp_path):
    store = Store(tmp_path / "state.db")
    store.save_scan("probe-nl-aaaa", "OK", 65536, 0.4)
    store.save_scan("probe-de-bbbb", "FROZEN", 16384, 5.1, "тишина", ts=1000.0)
    store.save_scan("probe-nl-aaaa", "SLOW", 65536, 4.2)  # новый результат заменяет прежний
    scans = store.scans()
    assert scans["probe-nl-aaaa"]["verdict"] == "SLOW" and scans["probe-nl-aaaa"]["ts"] > 1000
    assert scans["probe-de-bbbb"]["ts"] == 1000.0 and scans["probe-de-bbbb"]["error"] == "тишина"
    store.prune_scans({"probe-nl-aaaa"})  # узел пропал из конфига — скан больше не нужен
    assert list(store.scans()) == ["probe-nl-aaaa"]
    store.add_event("rotation", "a → b")
    assert store.last_event_time("rotation") is not None
    assert store.last_event_time("нет такого") is None
    store.close()


def test_host_cache_keeps_checked_addresses_for_a_week(tmp_path):
    """dns-cache.json: адрес записывается после удачного запроса, служебные — нет, через
    неделю запись не используется."""
    from xgw.store import HOST_CACHE_TTL, HostCache

    now = [1000.0]
    cache = HostCache(tmp_path, clock=lambda: now[0])
    cache.remember("sub.example.com", "203.0.113.8")
    cache.remember("sub.example.com", "127.0.0.1")  # подмена — не записывается
    cache.remember("sub.example.com", "203.0.113.9")
    assert cache.addresses() == {"sub.example.com": ["203.0.113.9", "203.0.113.8"]}
    assert (tmp_path / "dns-cache.json").stat().st_mode & 0o777 == 0o600
    now[0] += HOST_CACHE_TTL + 1
    assert cache.addresses() == {}


def test_host_cache_says_when_an_address_is_new(tmp_path):
    """remember: True — адреса в записи не было (о нём строка в журнале), тот же адрес каждый
    час — False (молча)."""
    from xgw.store import HOST_CACHE_TTL, HostCache

    now = [1000.0]
    cache = HostCache(tmp_path, clock=lambda: now[0])
    assert cache.remember("sub.example.com", "203.0.113.8") is True
    assert cache.remember("sub.example.com", "203.0.113.8") is False
    assert cache.remember("sub.example.com", "203.0.113.9") is True
    assert cache.remember("sub.example.com", "127.0.0.1") is False
    now[0] += HOST_CACHE_TTL + 1
    assert cache.remember("sub.example.com", "203.0.113.9") is True  # запись устарела


def test_host_cache_addresses_expire_one_by_one(tmp_path):
    """Пятый аудит, D2: у каждого адреса свой срок — удачный запрос по новому адресу не
    продлевает старый, не проверенный неделю. Запись прежней версии (без seen) — по времени
    всей записи."""
    import json

    from xgw.store import HOST_CACHE_TTL, HostCache

    now = [1000.0]
    cache = HostCache(tmp_path, clock=lambda: now[0])
    cache.remember("sub.example.com", "203.0.113.8")
    now[0] += HOST_CACHE_TTL - 10
    cache.remember("sub.example.com", "203.0.113.9")
    assert cache.addresses() == {"sub.example.com": ["203.0.113.9", "203.0.113.8"]}
    now[0] += 20
    assert cache.addresses() == {"sub.example.com": ["203.0.113.9"]}
    assert cache.remember("sub.example.com", "203.0.113.8") is True  # снова новый
    old = {"old.example.com": {"ips": ["198.51.100.1"], "ts": now[0]}}
    (tmp_path / "dns-cache.json").write_text(json.dumps(old), encoding="utf-8")
    assert cache.addresses() == {"old.example.com": ["198.51.100.1"]}


def test_scan_body_window_retries_and_quota_across_restart(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "state.db"
    store = Store(path)
    store.conn.execute("INSERT INTO nodes (fingerprint,tag,source,name) VALUES ('a','t','s','x10')")
    store.set_meta("quota", '{"s":{"total":10000}}')
    with ThreadPoolExecutor(1) as worker:
        for stamp, size in [(100, 1000), (101, 7), (86500, 0), (86500, 11)]:
            worker.submit(store.record_scan_body, "t", size, "daemon", r"x(\d+)", stamp).result()
    store.close()
    store = Store(path)
    assert store.scan_bodies_24h(86500) == {
        "as_of": 86500, "bytes": 18, "attempts": 3, "quota_bytes": {"s": 180},
        "by_purpose": {"scan": {"bytes": 18, "attempts": 3}}}
    store.close()


def test_ledger_purposes_and_migration_of_old_journal(tmp_path):
    """C06: замеры скорости и сквозная проверка — в том же журнале со своим назначением;
    журнал первой части C05 (без колонки purpose) дополняется, старые записи — сканы."""
    import sqlite3

    path = tmp_path / "state.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE scan_bodies (ts REAL NOT NULL, origin TEXT NOT NULL, "
                   "bytes INTEGER NOT NULL, source TEXT, quota_bytes INTEGER)")
        db.execute("INSERT INTO scan_bodies VALUES (100, 'daemon', 5, NULL, NULL)")
    store = Store(path)
    store.record_scan_body("t", 40, "daemon", None, 101, purpose="speed")
    store.record_scan_body("", 7, "daemon", None, 102, purpose="e2e")
    Store(path).close()  # второй процесс: колонка уже есть
    assert store.scan_bodies_24h(200)["by_purpose"] == {
        "scan": {"bytes": 5, "attempts": 1}, "speed": {"bytes": 40, "attempts": 1},
        "e2e": {"bytes": 7, "attempts": 1}}
    store.close()


def test_ledger_stretches_spare_scans_only_past_the_room():
    """C06: период скана растёт, только когда журнал сканов за 24 ч больше остатка лимита;
    растяжение держится до 80 % остатка, потом прогноз."""
    from xgw.watch import status

    assert status.ledger_minutes(30, 30, 100, 1000) == 30
    assert status.ledger_minutes(30, 30, 2000, 1000) == 60
    assert status.ledger_minutes(30, 60, 900, 1000) == 60
    assert status.ledger_minutes(30, 60, 700, 1000) == 30
    assert status.ledger_minutes(30, 30, 10**12, 1000) == status.MAX_SCAN_MINUTES
    assert status.ledger_minutes(30, 30, 1, 0) == status.MAX_SCAN_MINUTES
    assert status.ledger_parts({"by_purpose": {"scan": {"bytes": 2_000_000},
                                                "e2e": {"bytes": 3000}}}) == (
        "сквозная 3.0 КБ, сканы 2.0 МБ")


def test_scan_body_is_capped_even_if_server_ignores_range():
    """C06: Range — просьба серверу; скан читает не больше запрошенного, известного размера
    адреса или SCAN_CAP_BYTES."""
    from xgw.watch import scan

    assert scan.body_cap("https://example.com/x", 50_000) == 50_000
    assert scan.body_cap("https://example.com/unknown") == scan.SCAN_CAP_BYTES
