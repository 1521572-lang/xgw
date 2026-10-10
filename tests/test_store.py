"""Тесты хранилища состояния (SQLite)."""

import os
import stat

import pytest

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


@pytest.mark.skipif(os.name == "nt", reason="права файлов POSIX")
def test_subscription_cache_is_private(tmp_path):
    cache = SubscriptionCache(tmp_path / "cache")
    cache.save("main", b"secret links")
    for path in (tmp_path / "cache").iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
