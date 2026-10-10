"""Тесты хранилища состояния (SQLite)."""

from xgw.store import Store


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
