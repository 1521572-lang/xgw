"""panel.json — то, что добавлено из панели: подписки, ссылки, отключённые и
убранные серверы. Файл дополняет config.toml, а не заменяет его."""

import json
import stat
import threading

import links
import pytest

from xgw import config, managed
from xgw.generator.builder import select_nodes, skip_reason
from xgw.managed import ManagedError
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import file_lock


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
         "routes": [], "priority": {}, "sticky": None, "kernel_direct": None,
         "kernel_devices": [], "core": {},
         "tailscale": {"serve": "", "route": None, "funnel": "", "direct": []},
         "free_pool_mode": None, "free_pool_pin": ""}, "")
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
                           "headers": {}, "refresh_minutes": 60}],
        "links": [links.VMESS],
        "disabled": ["aaaa1111"],  # убранный сервер отключённым уже не считается
        "removed": ["bbbb2222"],
        "devices": [],
        "routes": [],  # своих серверов устройствам не выбирали
        # средний не хранится; неизвестный уровень и чужой отпечаток отброшены
        "priority": {"aaaa1111": "high", "eeee5555": "low"},
        "sticky": None,  # переключатель основного сервера в панели не трогали
        "kernel_direct": None,  # и российские адреса мимо Xray — тоже
        "kernel_devices": [],
        "core": {},  # ядро за серверами не закрепляли
        # панель по tailnet не включали
        "tailscale": {"serve": "", "route": None, "funnel": "", "direct": []},
        # бесплатный пул из панели не включали
        "free_pool_mode": None,
        "free_pool_pin": "",
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


def test_subscription_user_agent_and_headers(conf):
    path = managed.path_for(conf)
    name = managed.add_subscription(
        path, "https://sub.example.org/x", taken=set(),
        user_agent="Happ/1.0", headers={"X-Custom": "value", "Bad\nHeader": "x"},
    )
    data = managed.load(path)[0]
    assert data["subscriptions"][0] == {
        "name": name,
        "url": "https://sub.example.org/x",
        "user_agent": "Happ/1.0",
        "headers": {"X-Custom": "value"},
        "refresh_minutes": 60,
    }
    assert managed.update_subscription(path, name, user_agent="New/2.0") is True
    assert managed.update_subscription(path, "missing", user_agent="x") is False
    data = managed.load(path)[0]
    assert data["subscriptions"][0]["user_agent"] == "New/2.0"
    assert data["subscriptions"][0]["headers"] == {"X-Custom": "value"}
    assert managed.update_subscription(path, name, headers={"A": "b"}) is True
    data = managed.load(path)[0]
    assert data["subscriptions"][0]["headers"] == {"A": "b"}


def test_subscription_headers_are_loaded_by_config(conf):
    _save(conf, {
        "subscriptions": [
            {"name": "second", "url": "https://b.example.com/s", "user_agent": "UA/1",
             "headers": {"X-H": "v"}},
        ],
    })
    cfg, _warnings = config.load(conf)
    sub = next(s for s in cfg.subscriptions if s.name == "second")
    assert sub.user_agent == "UA/1"
    assert sub.headers == {"X-H": "v"}


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


def test_device_with_its_own_server_gets_a_lease_and_never_goes_with_bypass(conf):
    """Ф4: свой сервер устройства — статическая аренда и managed.routes (адрес → отпечаток);
    устройство мимо VPN своего сервера получить не может, и наоборот; «авто» убирает маршрут."""
    path = managed.path_for(conf)
    assert managed.set_route(path, "AA-BB-CC-00-11-22", "192.168.50.120", "tv", "ab12cd34")
    assert not managed.set_route(path, "aa:bb:cc:00:11:22", "192.168.50.120", "tv", "ab12cd34")
    with pytest.raises(ManagedError, match="свой сервер"):
        managed.set_device(path, "aa:bb:cc:00:11:22", "192.168.50.120", "tv", bypass=True)
    managed.set_device(path, "aa:bb:cc:00:11:33", "192.168.50.130", "", bypass=True)
    with pytest.raises(ManagedError, match="мимо VPN"):
        managed.set_route(path, "aa:bb:cc:00:11:33", "192.168.50.130", "", "ab12cd34")
    cfg, warnings = config.load(conf)
    assert warnings == []
    assert "aa:bb:cc:00:11:22,192.168.50.120,tv" in cfg.network.static_leases
    assert cfg.managed.routes == {"192.168.50.120": "ab12cd34"}
    assert "aa:bb:cc:00:11:22" not in cfg.network.bypass_hosts
    assert managed.set_route(path, "aa:bb:cc:00:11:22", "", "", "")  # «авто»
    assert config.load(conf)[0].managed.routes == {}


def test_russian_addresses_past_xray_are_chosen_per_device(conf):
    """Ф6 по устройству (пожелание заказчика): аренда и managed.kernel_devices, вместе со своим
    сервером тоже; адрес другого устройства не занять. Прежний общий переключатель, включённый
    в panel.json, переходит к этой машине и к устройствам, что сейчас в сети, — один раз."""
    path = managed.path_for(conf)
    assert managed.set_route(path, "aa:bb:cc:00:11:22", "192.168.50.120", "tv", "ab12cd34")
    assert managed.set_kernel_device(path, "AA-BB-CC-00-11-22", "192.168.50.120", "tv", on=True)
    assert not managed.set_kernel_device(path, "aa:bb:cc:00:11:22", "192.168.50.120", "tv", on=True)
    with pytest.raises(ManagedError, match="закреплён"):
        managed.set_kernel_device(path, "aa:bb:cc:00:11:33", "192.168.50.120", on=True)
    cfg, warnings = config.load(conf)
    assert warnings == [] and cfg.managed.kernel_devices == ["192.168.50.120"]
    assert cfg.network.static_leases == ["aa:bb:cc:00:11:22,192.168.50.120,tv"]
    assert not cfg.routing.kernel_direct  # машина — своим переключателем
    assert managed.set_kernel_device(path, "aa:bb:cc:00:11:22", "", on=False)
    assert config.load(conf)[0].managed.kernel_devices == []

    online = [{"mac": "aa:bb:cc:00:11:44", "ip": "192.168.50.140", "name": "phone"},
              {"mac": "aa:bb:cc:00:11:55", "ip": "192.168.50.120", "name": ""}]  # адрес tv
    _save(conf, {"kernel_direct": True, "routes": [
        {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.50.120", "name": "tv", "server": "ab12cd34"}]})
    assert managed.split_kernel_direct(path, online)
    cfg = config.load(conf)[0]
    assert cfg.routing.kernel_direct and cfg.managed.kernel_devices == ["192.168.50.140"]
    assert not managed.split_kernel_direct(path, online)  # один раз
    _save(conf, {"kernel_direct": False})
    assert not managed.split_kernel_direct(path, online)


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


# --- Telegram прежних версий ------------------------------------------------------------

BOT_TOKEN = "123456789:AAFakeTokenForTestsOnly_0123456789abc"


def test_old_panel_bot_is_ignored_and_wiped(conf):
    """Telegram в XGW больше нет: бот из panel.json не читается, а drop_telegram стирает его
    токен с диска, оставляя всё остальное."""
    _save(conf, {"telegram": {"token": BOT_TOKEN, "chat_id": "1001"}, "sticky": False})
    path = managed.path_for(conf)
    assert "telegram" not in managed.load(path)[0]
    cfg, warnings = config.load(conf)
    assert warnings == [] and cfg.speed.sticky is False
    assert managed.drop_telegram(path) is True
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "telegram" not in raw and raw["sticky"] is False and BOT_TOKEN not in path.read_text()
    assert managed.drop_telegram(path) is False  # убирать уже нечего


def test_old_telegram_keys_in_config_toml_are_explained(conf):
    conf.write_text(
        conf.read_text(encoding="utf-8")
        + f'[notify]\ntelegram_bot_token = "{BOT_TOKEN}"\ntelegram_chat_id = "7"\n'
        + 'commands = true\ntelegram_api = "https://api.telegram.org"\n',
        encoding="utf-8")
    cfg, warnings = config.load(conf)
    assert warnings == [
        f"notify.{key}: Telegram в XGW больше нет — строку можно удалить"
        for key in ("telegram_bot_token", "telegram_chat_id", "commands", "telegram_api")
    ]
    assert not hasattr(cfg.notify, "telegram_bot_token")


def test_sticky_switch_is_stored_and_merged_into_the_config(conf):
    path = managed.path_for(conf)
    assert managed.load(path)[0]["sticky"] is None
    assert managed.set_sticky(path, False) is True
    assert managed.set_sticky(path, False) is False  # уже так
    assert managed.load(path)[0]["sticky"] is False
    cfg, _warnings = config.load(conf)
    assert cfg.speed.sticky is False and cfg.managed.sticky is False
    assert managed.set_sticky(path, True) is True
    assert config.load(conf)[0].speed.sticky is True
    with pytest.raises(managed.ManagedError):
        managed.set_sticky(path, "yes")


# --- несколько писателей: панель и команды xgw ------------------------------------------


def test_concurrent_writers_keep_each_others_changes(conf):
    """Панель отключает серверы, `xgw priority` тем временем меняет приоритеты: обе правки
    остаются."""
    path = managed.path_for(conf)
    rounds = 40
    barrier, errors = threading.Barrier(2), []

    def servers() -> None:
        for number in range(rounds):
            managed.set_servers(path, [f"{number:08x}"], "disabled")

    def priorities() -> None:
        for number in range(rounds):
            managed.set_priority(path, [f"{number + 1000:08x}"], "high")

    def run(job) -> None:
        barrier.wait()
        try:
            job()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(job,)) for job in (servers, priorities)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    data = managed.load(path)[0]
    assert data["disabled"] == [f"{number:08x}" for number in range(rounds)]
    assert data["priority"] == {f"{number + 1000:08x}": "high" for number in range(rounds)}


def test_writer_waits_while_another_process_holds_the_lock(conf):
    path = managed.path_for(conf)
    assert managed.set_sticky(path, True)
    assert stat.S_IMODE(managed.lock_path(path).stat().st_mode) == 0o600
    done = threading.Event()

    def write() -> None:
        managed.set_sticky(path, False)
        done.set()

    worker = threading.Thread(target=write)
    with file_lock(managed.lock_path(path)):  # так её держит, например, `xgw priority`
        worker.start()
        assert not done.wait(0.3)
        assert managed.load(path)[0]["sticky"] is True
    worker.join(5)
    assert done.is_set() and managed.load(path)[0]["sticky"] is False


def test_lock_held_too_long_is_a_message_not_a_crash(conf, monkeypatch):
    path = managed.path_for(conf)
    monkeypatch.setattr(managed, "LOCK_TIMEOUT", 0.1)
    with file_lock(managed.lock_path(path)), pytest.raises(ManagedError, match="другой процесс"):
        managed.set_priority(path, ["aaaa1111"], "high")
    assert not path.exists()
