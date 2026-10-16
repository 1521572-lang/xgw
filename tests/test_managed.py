"""panel.json — то, что добавлено из панели: подписки, ссылки, отключённые и
убранные серверы. Файл дополняет config.toml, а не заменяет его."""

import json
import os

import links
import pytest

from xgw import config, managed
from xgw.generator.builder import select_nodes, skip_reason
from xgw.managed import ManagedError
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text


@pytest.fixture()
def conf(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[[subscriptions]]\nname = "main"\nurl = "https://a.example.com/sub/T"\n'
        f'[manual]\nlinks = ["{links.TROJAN}"]\n', encoding="utf-8")
    return path


def _save(conf, data) -> None:
    managed.path_for(conf).write_text(json.dumps(data), encoding="utf-8")


def test_no_file_means_nothing_added(conf):
    assert managed.load(managed.path_for(conf)) == (
        {"subscriptions": [], "links": [], "disabled": [], "removed": [], "devices": [],
         "telegram": {"token": "", "chat_id": ""}, "priority": {}}, "")
    cfg, warnings = config.load(conf)
    assert warnings == [] and cfg.managed == config.Managed()
    assert [sub.name for sub in cfg.subscriptions] == ["main"]


def test_config_is_extended_by_the_panel_file(conf):
    _save(conf, {
        "subscriptions": [
            {"name": "second", "url": "https://b.example.com/s", "refresh_minutes": 15},
            {"name": "main", "url": "https://c.example.com/s"},
        ],
        "links": [links.VMESS, links.TROJAN],
        "disabled": ["aaaa1111"], "removed": ["bbbb2222"],
    })
    cfg, warnings = config.load(conf)
    assert [(sub.name, sub.refresh_minutes) for sub in cfg.subscriptions] == [
        ("main", 60), ("second", 15)]
    assert cfg.subscriptions[0].url == "https://a.example.com/sub/T"  # config.toml главнее
    assert warnings == ["подписка «main» из панели пропущена: такое имя уже есть в config.toml"]
    assert cfg.manual.links == [links.TROJAN, links.VMESS]
    assert cfg.managed == config.Managed(
        subscriptions=["second"], links=[links.VMESS], disabled=["aaaa1111"], removed=["bbbb2222"])


@pytest.mark.parametrize("text", ["{broken", "[1, 2]", '"строка"'])
def test_broken_file_is_a_warning_not_a_crash(conf, text):
    managed.path_for(conf).write_text(text, encoding="utf-8")
    cfg, warnings = config.load(conf)
    assert len(warnings) == 1 and "panel.json" in warnings[0]
    assert [sub.name for sub in cfg.subscriptions] == ["main"]
    with pytest.raises(ManagedError):  # и дописывать в битый файл панель не станет
        managed.add_subscription(managed.path_for(conf), "https://x.example.org/s", taken=set())


def test_junk_inside_the_file_is_ignored(conf):
    _save(conf, {
        "subscriptions": ["строка", {"name": "", "url": "https://x"}, {"name": "ok", "url": 5},
                          {"name": "good", "url": "https://g.example.org/s",
                           "refresh_minutes": True, "user_agent": 7}],
        "links": [5, "", links.VMESS],
        "disabled": ["AAAA1111", "aaaa1111", "aaaa1111", "bbbb2222", 7, "короткий"],
        "removed": ["bbbb2222"],
        "priority": {"aaaa1111": "high", "cccc3333": "medium", "dddd4444": "срочно",
                     "AAAA2222": "low", "eeee5555": "low", "x": "high"},
    })
    data, error = managed.load(managed.path_for(conf))
    assert error == "" and data == {
        "subscriptions": [{"name": "good", "url": "https://g.example.org/s", "user_agent": "",
                           "refresh_minutes": 60}],
        "links": [links.VMESS],
        "disabled": ["aaaa1111"],  # убранный сервер отключённым уже не считается
        "removed": ["bbbb2222"],
        "devices": [],
        "telegram": {"token": "", "chat_id": ""},
        # средний не хранится; неизвестный уровень и чужой отпечаток отброшены
        "priority": {"aaaa1111": "high", "eeee5555": "low"},
    }


def test_priority_is_kept_per_fingerprint_and_medium_is_not_stored(conf):
    path = managed.path_for(conf)
    assert managed.set_priority(path, ["aaaa1111", "bbbb2222"], "high") is True
    assert managed.set_priority(path, ["aaaa1111"], "high") is False  # уже так
    assert managed.set_priority(path, ["bbbb2222"], "low") is True
    assert managed.load(path)[0]["priority"] == {"aaaa1111": "high", "bbbb2222": "low"}
    assert managed.set_priority(path, ["aaaa1111"], "medium") is True
    assert managed.load(path)[0]["priority"] == {"bbbb2222": "low"}
    cfg, _warnings = config.load(conf)
    assert cfg.managed.priority == {"bbbb2222": "low"}
    # Прочее в файле не теряется.
    managed.set_servers(path, ["cccc3333"], "disabled")
    assert managed.load(path)[0]["priority"] == {"bbbb2222": "low"}
    for fingerprints, level in ((["aaaa1111"], "top"), ([], "high"), (["короткий"], "low")):
        with pytest.raises(managed.ManagedError):
            managed.set_priority(path, fingerprints, level)


def test_subscription_names_and_limits(conf):
    path = managed.path_for(conf)
    assert managed.add_subscription(path, " https://sub.example.org/a ", taken={"main"}) == (
        "sub.example.org")
    assert managed.add_subscription(path, "https://sub.example.org/b", taken={"main"}) == (
        "sub.example.org-2")
    assert managed.add_subscription(path, "http://h.example.org/c", "Мой\tVPN", taken=set()) == (
        "Мой VPN")
    assert path.stat().st_mode & 0o777 == 0o600
    for url, name in (("https://sub.example.org/a", ""), ("https://z.example.org/", "main"),
                      ("https://z.example.org/", "Мой VPN")):
        with pytest.raises(ManagedError):
            managed.add_subscription(path, url, name, taken={"main"})
    for url in ("file:///etc/passwd", "https://", "https://exa mple.org/x", "x" * 3000, ""):
        with pytest.raises(ManagedError):
            managed.add_subscription(path, url, taken=set())
    assert managed.remove_subscription(path, "sub.example.org") is True
    assert managed.remove_subscription(path, "sub.example.org") is False
    for number in range(managed.MAX_SUBSCRIPTIONS - 2):
        managed.add_subscription(path, f"https://n{number}.example.org/s", taken=set())
    with pytest.raises(ManagedError, match="больше нельзя"):
        managed.add_subscription(path, "https://one-more.example.org/s", taken=set())


def test_links_are_checked_before_saving(conf):
    path = managed.path_for(conf)
    assert managed.add_links(path, f"{links.VMESS}\n\n{links.VLESS_WS}\n", taken=set()) == 2
    assert managed.add_links(path, links.VMESS, taken=set()) == 0
    assert managed.add_links(path, links.TROJAN, taken={links.TROJAN}) == 0
    with pytest.raises(ManagedError, match="разобрать не удалось"):
        managed.add_links(path, "vless://без-адреса", taken=set())
    saved = managed.load(path)[0]["links"]
    assert saved == [links.VMESS, links.VLESS_WS]
    identifier = managed.link_id(links.VMESS)
    assert len(identifier) == 12 and identifier not in links.VMESS
    assert managed.remove_link(path, identifier) and not managed.remove_link(path, identifier)


def test_servers_move_between_enabled_disabled_and_removed(conf):
    path = managed.path_for(conf)
    assert managed.set_servers(path, ["aaaa1111", "bbbb2222", "aaaa1111"], "disabled") is True
    assert managed.set_servers(path, ["aaaa1111"], "disabled") is False  # уже отключён
    assert managed.set_servers(path, ["aaaa1111"], "removed") is True
    data = managed.load(path)[0]
    assert data["disabled"] == ["bbbb2222"] and data["removed"] == ["aaaa1111"]
    assert managed.set_servers(path, ["aaaa1111", "bbbb2222"], "enabled") is True
    data = managed.load(path)[0]
    assert data["disabled"] == [] and data["removed"] == []
    for fingerprints, mode in ((["zzzz"], "disabled"), (["aaaa1111"], "delete"), ([], "disabled"),
                               (["AAAA1111"], "disabled")):
        with pytest.raises(ManagedError):
            managed.set_servers(path, fingerprints, mode)


def test_oldest_exclusions_are_dropped_beyond_the_limit(conf, monkeypatch):
    monkeypatch.setattr(managed, "MAX_SERVERS", 3)
    path = managed.path_for(conf)
    for number in range(5):
        managed.set_servers(path, [f"{number:08x}"], "removed")
    assert managed.load(path)[0]["removed"] == ["00000002", "00000003", "00000004"]


# --- отключённый или убранный сервер в конфиг Xray не попадает ----------------------


def _nodes():
    raws, _meta, _warnings = parse_links_text("\n".join(links.FULL_LINKS), "main")
    return [raw_to_node(raw, "main") for raw in raws]


def test_excluded_servers_are_neither_members_nor_spares():
    nodes = _nodes()
    cfg = config.Config()
    cfg.filters.exclude_regex = ""
    cfg.filters.max_members = 2
    everyone = {node.fingerprint for node in nodes}
    selection = select_nodes(nodes, cfg)
    assert {n.fingerprint for n in [*selection.members, *selection.spares]} == everyone

    member, spare = selection.members[0], selection.spares[0]
    cfg.managed.disabled = [member.fingerprint]
    cfg.managed.removed = [spare.fingerprint]
    selection = select_nodes(nodes, cfg, prefer=[member.fingerprint])
    kept = {n.fingerprint for n in [*selection.members, *selection.spares]}
    assert kept == everyone - {member.fingerprint, spare.fingerprint}
    assert len(selection.members) == 2  # место отключённого участника занял другой сервер
    assert skip_reason(member, cfg) == "excluded" and skip_reason(spare, cfg) == "excluded"


def test_skip_reason_names_the_filter():
    node = _nodes()[0]
    cfg = config.Config()
    cfg.filters.exclude_regex = ""
    assert skip_reason(node, cfg) == ""
    cfg.filters.include_regex = "нет такого имени"
    assert skip_reason(node, cfg) == "filter"
    cfg.filters.include_regex, cfg.filters.exclude_regex = "", "."
    assert skip_reason(node, cfg) == "filter"


# --- устройства мимо VPN ---------------------------------------------------------------


def test_device_bypass_is_stored_and_turned_back(conf):
    path = managed.path_for(conf)
    assert managed.set_device(path, "AA-BB-CC-00-11-22", "192.168.50.101", "phone", bypass=True)
    assert not managed.set_device(path, "aa:bb:cc:00:11:22", "192.168.50.101", "phone", bypass=True)
    assert managed.load(path)[0]["devices"] == [
        {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.50.101", "name": "phone"}]
    # Адрес принадлежит одному устройству; повтор того же MAC обновляет запись.
    with pytest.raises(ManagedError, match="закреплён"):
        managed.set_device(path, "aa:bb:cc:00:11:33", "192.168.50.101", "", bypass=True)
    assert managed.set_device(path, "aa:bb:cc:00:11:22", "192.168.50.102", "bad name", bypass=True)
    assert managed.load(path)[0]["devices"][0]["name"] == ""  # имя не для dhcp-host — без имени
    assert managed.set_device(path, "aa:bb:cc:00:11:22", "", "", bypass=False)
    assert not managed.set_device(path, "aa:bb:cc:00:11:22", "", "", bypass=False)
    assert managed.load(path)[0]["devices"] == []
    for mac, ip in (("не mac", "192.168.50.5"), ("aa:bb:cc:00:11:22", "не адрес")):
        with pytest.raises(ManagedError):
            managed.set_device(path, mac, ip, "", bypass=True)


def test_devices_survive_other_changes_and_junk_is_dropped(conf):
    path = managed.path_for(conf)
    _save(conf, {"devices": [
        {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.50.101", "name": "tv"},
        {"mac": "AA:BB:CC:00:11:22", "ip": "192.168.50.150"},  # тот же MAC
        {"mac": "aa:bb:cc:00:11:44", "ip": "192.168.50.101"},  # тот же адрес
        {"mac": "нет", "ip": "192.168.50.7"}, {"mac": "aa:bb:cc:00:11:55", "ip": 5},
        {"mac": "aa:bb:cc:00:11:66", "ip": "::1"}, "строка", 7,
        {"mac": "aa:bb:cc:00:11:77", "ip": "192.168.50.77", "name": "x y"},
    ]})
    assert managed.load(path)[0]["devices"] == [
        {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.50.101", "name": "tv"},
        {"mac": "aa:bb:cc:00:11:77", "ip": "192.168.50.77", "name": ""},
    ]
    managed.set_servers(path, ["aaaa1111"], "disabled")
    managed.add_links(path, links.VMESS, taken=set())
    assert len(managed.load(path)[0]["devices"]) == 2  # чужие правки список не трогают
    managed.replace_devices(path, [{"mac": "aa:bb:cc:00:11:22", "ip": "192.168.50.101"}])
    assert managed.load(path)[0]["devices"] == [
        {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.50.101", "name": ""}]


def test_device_limit(conf, monkeypatch):
    monkeypatch.setattr(managed, "MAX_DEVICES", 2)
    path = managed.path_for(conf)
    managed.set_device(path, "aa:bb:cc:00:00:01", "192.168.50.1", "", bypass=True)
    managed.set_device(path, "aa:bb:cc:00:00:02", "192.168.50.2", "", bypass=True)
    with pytest.raises(ManagedError, match="больше нельзя"):
        managed.set_device(path, "aa:bb:cc:00:00:03", "192.168.50.3", "", bypass=True)


def test_panel_devices_become_a_static_lease_and_a_bypass_host(conf):
    _save(conf, {"devices": [{"mac": "aa:bb:cc:00:11:22", "ip": "192.168.50.101", "name": "tv"}]})
    cfg, warnings = config.load(conf)
    assert warnings == []
    assert cfg.network.static_leases == ["aa:bb:cc:00:11:22,192.168.50.101,tv"]
    assert cfg.network.bypass_hosts == ["aa:bb:cc:00:11:22"]
    assert cfg.managed.devices == ["aa:bb:cc:00:11:22"]
    from xgw.net import lan
    assert lan.bypass_addresses(cfg) == (["192.168.50.101"], [])  # арендой MAC стал адресом


def test_config_toml_wins_over_panel_devices(conf):
    conf.write_text(
        conf.read_text(encoding="utf-8")
        + '[network]\nstatic_leases = ["AA-BB-CC-00-11-22,192.168.50.101,tv", '
        '"aa:bb:cc:00:11:99,192.168.50.99", "aa:bb:cc:00:11:88,192.168.50.88"]\n'
        'bypass_hosts = ["aa:bb:cc:00:11:99"]\n', encoding="utf-8")
    _save(conf, {"devices": [
        {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.50.101", "name": "tv"},  # аренда уже есть
        {"mac": "aa:bb:cc:00:11:99", "ip": "192.168.50.99", "name": ""},  # уже мимо VPN в toml
        {"mac": "aa:bb:cc:00:11:33", "ip": "192.168.50.88", "name": ""},  # адрес занят в toml
        {"mac": "aa:bb:cc:00:11:44", "ip": "192.168.50.40", "name": ""},
    ]})
    cfg, warnings = config.load(conf)
    assert cfg.network.static_leases == [
        "AA-BB-CC-00-11-22,192.168.50.101,tv", "aa:bb:cc:00:11:99,192.168.50.99",
        "aa:bb:cc:00:11:88,192.168.50.88", "aa:bb:cc:00:11:44,192.168.50.40"]
    assert cfg.network.bypass_hosts == [
        "aa:bb:cc:00:11:99", "aa:bb:cc:00:11:22", "aa:bb:cc:00:11:44"]
    assert cfg.managed.devices == ["aa:bb:cc:00:11:22", "aa:bb:cc:00:11:44"]
    assert warnings == [
        "устройство aa:bb:cc:00:11:33 из панели пропущено: MAC или адрес 192.168.50.88 "
        "уже заняты в network.static_leases"]


# --- бот Telegram из панели ------------------------------------------------------------------

BOT_TOKEN = "123456789:AAFakeTokenForTestsOnly_0123456789abc"


def test_bot_token_is_checked_before_it_is_saved(conf):
    path = managed.path_for(conf)
    for bad in ("", "  ", "не токен", "123:short", "abc:" + "A" * 35, None, 5):
        with pytest.raises(ManagedError, match="токен бота"):
            managed.check_bot_token(bad)
    assert managed.check_bot_token(f"  {BOT_TOKEN}\n") == BOT_TOKEN
    with pytest.raises(ManagedError):
        managed.set_telegram(path, "не токен")
    with pytest.raises(ManagedError, match="чата"):
        managed.set_telegram(path, BOT_TOKEN, "не число")
    assert not path.exists()

    managed.set_telegram(path, BOT_TOKEN)
    assert managed.load(path)[0]["telegram"] == {"token": BOT_TOKEN, "chat_id": ""}
    managed.set_telegram(path, BOT_TOKEN, "-100123")
    assert managed.load(path)[0]["telegram"] == {"token": BOT_TOKEN, "chat_id": "-100123"}
    assert oct(os.stat(path).st_mode & 0o777) in ("0o600", "0o666")  # токен — как пароль
    managed.set_telegram(path, "")
    assert managed.load(path)[0]["telegram"] == {"token": "", "chat_id": ""}


def test_junk_telegram_entries_are_dropped(conf):
    for value in ("строка", 5, [], {"token": 5}, {"token": "123:short", "chat_id": "1"},
                  {"token": BOT_TOKEN, "chat_id": "abc"}):
        _save(conf, {"telegram": value})
        data = managed.load(managed.path_for(conf))[0]["telegram"]
        assert data == {"token": BOT_TOKEN if isinstance(value, dict) and value.get("token")
                        == BOT_TOKEN else "", "chat_id": ""}, value


def test_panel_bot_fills_the_notify_settings(conf):
    managed.set_telegram(managed.path_for(conf), BOT_TOKEN)
    cfg, warnings = config.load(conf)
    assert warnings == []  # бот без чата — ожидание подключения, а не ошибка
    assert cfg.notify.telegram_bot_token == BOT_TOKEN and cfg.notify.telegram_chat_id == ""
    assert cfg.managed.telegram is True
    managed.set_telegram(managed.path_for(conf), BOT_TOKEN, "1001")
    cfg, warnings = config.load(conf)
    assert (cfg.notify.telegram_chat_id, warnings) == ("1001", [])


def test_bot_in_config_toml_wins_over_the_panel(conf):
    conf.write_text(
        conf.read_text(encoding="utf-8")
        + f'[notify]\ntelegram_bot_token = "999999999:{"Z" * 35}"\ntelegram_chat_id = "7"\n',
        encoding="utf-8")
    managed.set_telegram(managed.path_for(conf), BOT_TOKEN, "1001")
    cfg, warnings = config.load(conf)
    assert cfg.notify.telegram_chat_id == "7" and cfg.managed.telegram is False
    assert warnings == ["бот Telegram из панели пропущен: бот уже задан в config.toml"]


def test_toml_token_without_chat_is_still_a_warning(conf):
    conf.write_text(
        conf.read_text(encoding="utf-8") + f'[notify]\ntelegram_bot_token = "{BOT_TOKEN}"\n',
        encoding="utf-8")
    _cfg, warnings = config.load(conf)
    assert warnings == ["задан telegram_bot_token, но не задан telegram_chat_id"]


@pytest.mark.parametrize("api", ["ftp://x", "api.telegram.org", "http://", "https://a b"])
def test_telegram_api_must_be_an_http_address(conf, api):
    conf.write_text(
        conf.read_text(encoding="utf-8") + f'[notify]\ntelegram_api = "{api}"\n', encoding="utf-8")
    cfg, warnings = config.load(conf)
    assert cfg.notify.telegram_api == "https://api.telegram.org"
    assert any("notify.telegram_api" in warning for warning in warnings)


def test_telegram_api_trailing_slash_is_dropped(conf):
    conf.write_text(
        conf.read_text(encoding="utf-8") + '[notify]\ntelegram_api = "http://127.0.0.1:8081/"\n',
        encoding="utf-8")
    assert config.load(conf)[0].notify.telegram_api == "http://127.0.0.1:8081"
