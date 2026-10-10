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
        {"subscriptions": [], "links": [], "disabled": [], "removed": []}, "")
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
    })
    data, error = managed.load(managed.path_for(conf))
    assert error == "" and data == {
        "subscriptions": [{"name": "good", "url": "https://g.example.org/s", "user_agent": "",
                           "refresh_minutes": 60}],
        "links": [links.VMESS],
        "disabled": ["aaaa1111"],  # убранный сервер отключённым уже не считается
        "removed": ["bbbb2222"],
    }


def test_subscription_names_and_limits(conf):
    path = managed.path_for(conf)
    assert managed.add_subscription(path, " https://sub.example.org/a ", taken={"main"}) == (
        "sub.example.org")
    assert managed.add_subscription(path, "https://sub.example.org/b", taken={"main"}) == (
        "sub.example.org-2")
    assert managed.add_subscription(path, "http://h.example.org/c", "Мой\tVPN", taken=set()) == (
        "Мой VPN")
    if os.name != "nt":
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
