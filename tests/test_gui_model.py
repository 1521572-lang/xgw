"""Окно XGW (xgw.gui.model): логика без Qt на настоящих ответах панели (tests/fixtures/gui —
Panel.state() демо-сцен tests/panel_demo.py)."""

import json
import os
import stat
from pathlib import Path

import pytest

from xgw.gui import model

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gui"


def _state(scene: str) -> dict:
    return json.loads((FIXTURES / f"state-{scene}.json").read_text(encoding="utf-8"))


def test_health_matches_the_web_panel_on_real_states():
    work = _state("work")
    assert model.health(work, False) == ("warn", "Часть серверов недоступна")
    assert model.health(_state("empty"), False)[1] == "Серверов нет"
    assert model.health(work, True) == ("bad", "Демон XGW не отвечает")
    assert model.health(None, True) == ("bad", "Панель XGW не отвечает")
    for scene in ("trouble", "reserve", "stranded", "tspu", "cores"):
        tone, text = model.health(_state(scene), False)
        assert tone in ("ok", "warn", "bad", "off") and text


def test_unknown_and_missing_fields_do_not_break_the_window():
    assert model.health({"updated": 1.0, "members": [{}], "state": "NEW_STATE"}, False) == (
        "off", "NEW_STATE")
    assert model.health({}, False) == ("off", "Запускается…")
    power = model.power({}, False)
    assert power.title == "VPN выключен" and not power.enabled
    assert model.main_server({"servers": "?", "pin": 3}) is None
    assert model.lifecycle({"capture": {"lifecycle": "новое"}}, False) is None
    assert model.versions({"singbox": {"installed": False}})[2] == ("sing-box", "не установлен")


def test_stale_state_is_not_shown_as_current():
    state = {"now": 1000.0, "updated": 1000.0 - model.STALE_S - 1}
    assert model.is_stale(state) and model.is_stale(None)
    assert not model.is_stale({"now": 1000.0, "updated": 990.0})
    work = _state("work")
    assert not model.power(work, True).enabled
    assert model.lifecycle(work, True) is None


def test_power_follows_capture_and_what_the_panel_allows():
    work = _state("work")
    power = model.power(work, False)
    assert power.pressed and power.title == "VPN включён" and power.enabled
    assert not model.power(work, False, acting=True).enabled
    off = dict(work, capture={**work["capture"], "mode": "off"},
               power={"can_on": False, "can_off": False, "why": "сначала добавьте подписку"})
    blocked = model.power(off, False)
    assert not blocked.pressed and not blocked.enabled
    assert blocked.why == "Сначала добавьте подписку"
    assert model.lifecycle(work, False) == ("ok", "Перехват: работает — трафик идёт через VPN")


def test_main_server_keeps_speed_rtt_and_full_probe_apart():
    main = model.main_server(_state("work"))
    assert main is not None and main.country == "NL" and not main.pinned
    assert (main.speed_mbps, main.rtt_ms, main.delay_ms) == (87.3, 29.0, 84.0)
    pinned = dict(_state("work"), pin={"tag": "proxy-nl-a1a1", "down": False})
    assert model.main_server(pinned).pinned


def test_number_formats_are_russian():
    assert model.mbps_text(87.3) == "87,3 Мбит/с" and model.mbps_text(150.4) == "150 Мбит/с"
    assert model.mbps_text(None) == "—" and model.ms_text(84.4) == "84 мс"
    assert model.bytes_text(1536) == "1,5 КБ" and model.bytes_text(3 * 1024 ** 3) == "3,0 ГБ"
    assert model.bytes_text(512) == "512 Б"
    assert model.ago_text(3) == "только что" and model.ago_text(125) == "2 мин назад"
    assert model.ago_text(7300) == "2 ч назад"


def test_backoff_grows_with_jitter_and_resets():
    middle = model.Backoff(lambda: 0.5)
    assert [round(middle.fail(), 1) for _ in range(7)] == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]
    middle.reset()
    assert middle.fail() == 2.0
    low, high = model.Backoff(lambda: 0.0), model.Backoff(lambda: 1.0)
    assert low.fail() == pytest.approx(2.0 * (1 - model.JITTER))
    assert high.fail() == pytest.approx(2.0 * (1 + model.JITTER))


def test_poll_gate_allows_one_request_and_ignores_old_answers():
    gate = model.PollGate()
    first = gate.begin()
    assert first == 1 and gate.begin() is None
    assert gate.finish(first)
    second = gate.begin()
    gate.drop()  # сеанс сменился, пока второй шёл
    third = gate.begin()
    assert third == 3
    assert not gate.finish(second)  # старый ответ не перезаписывает
    assert gate.finish(third)


def test_action_guard_blocks_repeats_until_the_answer():
    guard = model.ActionGuard()
    assert guard.begin("power") and not guard.begin("power") and guard.begin("scan")
    guard.end("power")
    assert guard.begin("power") and guard.busy("scan")


def test_errors_are_human_and_without_secrets():
    secret = "vless://11111111-2222-3333-4455-666666666661@203.0.113.10:443?pbk=x#NL"
    text = model.error_text(500, f"сбой: {secret}")
    assert "11111111-2222" not in text and "203.0.113.10" not in text
    assert text.startswith("Ошибка панели XGW")
    assert model.error_text(401, "Нужен вход по токену") == model.HTTP_TEXTS[401]
    for code in (403, 404, 413):
        assert model.error_text(code).startswith(model.HTTP_TEXTS[code])
    assert model.error_text(None, network="Connection refused").startswith("Нет связи")
    assert model.parse_json(b"[1]") is None and model.parse_json(b"\xff") is None


def test_session_file_is_private_and_junk_means_login_again(tmp_path):
    path = tmp_path / "cfg" / "gui.json"
    session = model.Session(8781, "a" * 64)
    model.save_session(path, session)
    assert model.load_session(path) == session
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    path.write_text('{"port": "8781", "cookie": "x"}', encoding="utf-8")
    assert model.load_session(path) is None
    path.write_text("не json", encoding="utf-8")
    assert model.load_session(path) is None
    model.clear_session(path)
    model.clear_session(path)
    assert not path.exists()
    assert model.session_file(environ={model.SESSION_ENV: str(path)}) == path


def test_login_output_and_cookie_header_are_parsed_strictly():
    good = "предупреждение\n" + json.dumps({"port": 8781, "code": "Ab_c-" + "d" * 20})
    assert model.parse_login(good) == (8781, "Ab_c-" + "d" * 20)
    assert model.parse_login('{"port": 8781, "code": "a b"}') is None
    assert model.parse_login('{"port": 0, "code": "' + "a" * 20 + '"}') is None
    assert model.parse_login("") is None
    header = b"other=1; Path=/\nxgw_panel=" + b"f" * 64 + b"; Path=/; HttpOnly"
    assert model.cookie_from([header]) == "f" * 64
    assert model.cookie_from([b"xgw_panel=<script>; Path=/"]) == ""


def test_capture_line_does_not_lag_behind_the_power_switch():
    work = _state("work")
    turned_off = dict(work, capture={**work["capture"], "mode": "off"})
    assert model.lifecycle(turned_off, False) is None  # не «работает» рядом с «VPN выключен»
    turned_on = dict(work, capture={**work["capture"], "lifecycle": "off"})
    assert model.lifecycle(turned_on, False) == (
        "busy", "Перехват: включается — демон загружает правила сети")


def test_shield_word_says_whether_traffic_is_protected():
    work = _state("work")
    assert model.shield(work, False) == ("ok", "Защищено")
    assert model.shield(work, False, acting=True) == ("warn", "Выключаю…")
    off = dict(work, capture={**work["capture"], "mode": "off"})
    assert model.shield(off, False) == ("off", "Не защищено")
    assert model.shield(None, True)[0] == "bad" and model.shield(work, True)[0] == "bad"
    assert model.shield(_state("trouble"), False)[0] in ("bad", "warn", "off")


def test_server_rows_put_the_main_server_first_and_speak_plainly():
    members, spares, hidden = model.server_rows(_state("work"))
    assert [row.main for row in members] == [True, False, False, False, False]
    first = members[0]
    assert (first.flag, first.name, first.code) == ("🇳🇱", "Нидерланды · Амстердам 1", "NL")
    assert first.speed == "87,3 Мбит/с" and first.delay == "RTT 29 мс · проба 84 мс"
    assert first.sub == "xray · подписка «main»" and first.tone == "ok"
    assert members[-1].tone == "bad" and "×100" in members[-1].sub
    assert [row.status for row in spares] == [
        "проверен", "медленный", "ещё не проверен", "не прошёл проверку"]
    assert hidden == 3
    assert model.server_rows(None) == ([], [], 0)
    assert model.split_flag("Trojan-1") == ("", "Trojan-1")


def test_pinned_spare_is_the_first_row_in_work_not_lost_among_spares():
    work = _state("work")
    pinned = dict(work, pin={"tag": "spare-pl-f6f6", "down": False})
    members, spares, _hidden = model.server_rows(pinned)
    assert members[0].key == "spare-pl-f6f6" and members[0].main
    assert not any(row.main for row in members[1:]) and len(members) == 6
    assert all(row.key != "spare-pl-f6f6" for row in spares)
