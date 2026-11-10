"""Окно XGW, этап 3 (xgw.gui.listing): разделы «Серверы» и «Подписки» без Qt — на настоящих
ответах демо-панели (tests/fixtures/gui) и коротком выдуманном списке бесплатного пула."""

import json
from pathlib import Path

from xgw.gui import listing

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gui"


def _state(scene: str) -> dict:
    return json.loads((FIXTURES / f"state-{scene}.json").read_text(encoding="utf-8"))


def test_devices_keep_fixed_exclusions_and_unavailable_routes_visible():
    state = _state("work")
    fixed, selected, unnamed = state["devices"]
    selected.update(route="fixture-missing", route_down=True, offline=True)
    unnamed.update(route="pool")
    rows = {item.mac: item for item in listing.devices(state)}
    assert rows[fixed["mac"]].locked and "config.toml" in rows[fixed["mac"]].status
    row = rows[selected["mac"]]
    assert row.offline and "через основной" in row.status
    choices = dict(row.choices)
    assert choices["fixture-missing"] == "Выбранный сервер недоступен"
    assert "pool" not in choices
    disabled = next(server for server in state["servers"] if server["status"] == "disabled")
    assert disabled["fingerprint"] not in choices
    assert "закрыты" in rows[unnamed["mac"]].status
    state["lan"] = {}
    assert listing.devices(state) == []


def test_servers_are_grouped_by_subscription_and_speak_like_the_web_panel():
    groups = listing.groups(_state("work"))
    assert [group.title for group in groups] == ["main", "запасная", "Отдельные ссылки"]
    main = groups[0]
    assert main.count.startswith("включено ") and main.can_enable_all
    first = main.items[0]
    assert (first.flag, first.name, first.code) == ("🇳🇱", "Нидерланды · Амстердам 1", "NL")
    assert ("busy", "основной") in first.tags and first.sub.startswith("основной")
    assert first.speed == "87,3 Мбит/с" and first.delay == "RTT 29 мс · проба 84 мс"
    assert first.editable and first.choosable and first.measurable and first.dual
    dead = next(item for item in main.items if item.code == "SE")
    assert dead.tone == "bad" and dead.delay == "нет ответа" and not dead.measurable  # x100
    disabled = next(item for item in main.items if item.status == "disabled")
    assert disabled.sub == "отключён: шлюз к нему не обращается" and not disabled.choosable
    skipped = next(item for item in main.items if item.status == "skipped")
    assert not skipped.editable and skipped.sub.startswith("не используется")
    assert [group.title for group in listing.groups(_state("work"), "герман")] == ["main"]
    assert listing.groups(_state("work"), "нет такого") == []


def test_manual_choice_marks_the_server_and_explains_auto():
    state = dict(_state("work"), pin={"tag": "spare-pl-f6f6", "name": "", "down": None})
    items = [item for group in listing.groups(state) for item in group.items]
    chosen = next(item for item in items if item.code == "PL")
    assert chosen.pinned and ("busy", "выбран вручную") in chosen.tags and not chosen.choosable
    assert not any(("busy", "основной") in item.tags for item in items)
    on, measuring, text, note = listing.selection(state)
    assert on and measuring and "выбран вручную" in text
    assert note.startswith("Выбран вручную «Польша · Варшава»") and "Автовыбор" in note
    down = dict(state, pin={"tag": "spare-pl-f6f6", "down": "нет ответа"})
    assert "не отвечает" in listing.selection(down)[3]


def test_removed_subscriptions_links_and_quota():
    work = _state("work")
    assert listing.removed(work) == [("0de1e7ed", "🇮🇳 Индия · Мумбаи", "main")]
    main, backup = listing.subscriptions(work)
    assert main.sub.startswith("sub.example.com · серверов: 6 · обновлена")
    assert main.quota.startswith("Израсходовано 64,5 ГБ из 100 ГБ, осталось 35,5 ГБ")
    assert abs(main.share - 0.645) < 0.001 and not main.managed
    assert ("off", "из config.toml") in main.tags
    assert backup.error == "Не обновилась: HTTP 403 от сервера подписки"
    assert ("warn", "http, без шифрования") in backup.tags and backup.managed
    assert backup.share is None and backup.quota == ""
    assert listing.links(work) == [("6615916525c6", "trojan · Trojan-1", True)]
    assert listing.parse_headers("X-Token: a:b\nмусор\n: пусто\nAccept: */*") == {
        "X-Token": "a:b", "Accept": "*/*"}


def test_free_pool_rows_rank_working_first_and_offer_choice():
    state = dict(_state("work"), free_pool={"mode": "observe", "pin": "", "summary": {
        "computed_at": 1.0, "region": "EU", "found": 3, "checked": 2, "ready": 1,
        "spent_mb": 5, "budget_mb": 300, "by_region": {"EU": 1},
        "sources": [{"id": "igareck", "status": "SUCCESS", "retrieved_at": 1794000000}],
        "traffic": {"all": False, "devices": ["192.168.50.23"], "server": "x", "tag": "t1",
                    "servers": [{"id": "aaa", "tag": "t1", "alive": True, "delay_ms": 120}],
                    "alive": 1, "members": 1, "delay_ms": 120},
    }})
    pool = {"servers": [
        {"id": "bbb1", "source": "igareck", "name": "Отказ", "protocol": "vless",
         "verdict": "TIMEOUT", "checked_at": 1794000100, "why": "проверка не прошла"},
        {"id": "ccc1", "source": "igareck", "name": "Новый", "protocol": "trojan",
         "why": "ещё не проверен"},
        {"id": "aaa1", "source": "igareck", "name": "Рабочий", "protocol": "vless",
         "backend": "sing-box", "country": "DE", "egress": True, "verdict": "OK",
         "delay_ms": 300, "checked_at": 1794000000, "why": ""},
    ]}
    mode, text, flow = listing.pool_summary(state)
    assert mode == "observe" and "найдено 3" in text and flow.startswith("Через бесплатные")
    (group,) = listing.pool_groups(state, pool)
    assert group.title == "GitHub igareck (проверены в России)" and group.status == ("ok", "ок")
    assert [item.name for item in group.items] == ["Рабочий", "Отказ", "Новый"]
    working = group.items[0]
    assert working.rank == 0 and ("busy", "сейчас через") in working.tags
    assert ("off", "VLESS · sing-box") in working.tags and working.country == "DE"
    assert working.value == "120 мс" and working.choosable
    assert group.items[1].rank == 4 and "тайм-аут" in group.items[1].sub
    assert group.count == "допущено 1 · проверено 2 из 3"
    assert listing.pool_summary({"free_pool": {"mode": "off"}})[0] == "off"


def test_hidden_config_subscriptions_are_listed_for_restore():
    """П. 337: убранные подписки config.toml — имя и адрес под маской, кнопка «Вернуть»."""
    state = {"hidden_subscriptions": [{"name": "main", "host": "sub.example.net/…"},
                                      {"name": ""}, "мусор"]}
    assert listing.hidden(state) == [("main", "sub.example.net/…")]
    assert listing.hidden({}) == [] and listing.hidden(None) == []
