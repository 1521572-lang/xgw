"""Профили NetworkManager: разбор вывода nmcli, профиль xgw-lan, IPv6 на WAN."""

import pytest
from fakesys import FakeSystem, terse

from xgw import config
from xgw.net import nm
from xgw.net.cmd import CommandError


@pytest.fixture()
def system():
    return FakeSystem()


def _cfg() -> config.Config:
    cfg = config.Config()
    cfg.network.lan_if = "lan0"
    return cfg


def test_split_terse_unescapes_colons_and_backslashes():
    assert nm.split_terse("a:b:c") == ["a", "b", "c"]
    assert nm.split_terse(r"Wi\:Fi:uuid:02\:00\:00:x\\y") == ["Wi:Fi", "uuid", "02:00:00", "x\\y"]
    assert nm.split_terse("") == [""]
    assert nm.split_terse(terse("имя: с двоеточием", "x")) == ["имя: с двоеточием", "x"]


def test_profiles_and_devices_are_parsed(system):
    system.add_profile("Дом: гости", "lan0", active=True)
    manager = nm.Nm(system)
    assert manager.running()
    assert {profile.name for profile in manager.profiles()} == {"wan", "Дом: гости"}
    assert manager.devices()["lan0"].connection == "Дом: гости"
    assert manager.active_uuid("wan0") == system.uuid_of("wan")
    assert manager.active_uuid("нет0") == ""
    system.nm_running = False
    assert not manager.running()


def test_setup_lan_creates_profile_and_disables_only_bound_ones(system, tmp_path):
    bound = system.add_profile("Wired connection 2", "lan0", active=True)
    shared = system.add_profile("hotspot", "lan0", **{"ipv4.method": "shared"})
    record, warnings = nm.setup_lan(nm.Nm(system), _cfg(), tmp_path)
    assert warnings == []
    profile = system.profile(nm.PROFILE)
    assert profile["device"] == "lan0" and profile["connection.autoconnect-priority"] == "100"
    assert record["profile"] == system.uuid_of(nm.PROFILE) and record["lan_if"] == "lan0"
    assert [item["uuid"] for item in record["disabled"]] == [bound, shared]
    assert [item["active"] for item in record["disabled"]] == [True, False]
    assert system.profiles[bound]["connection.autoconnect"] == "no"
    assert system.profiles[shared]["connection.autoconnect"] == "no"
    assert system.profile("wan")["connection.autoconnect"] == "yes"  # чужой интерфейс


def test_setup_lan_twice_updates_the_profile_and_keeps_original_records(system, tmp_path):
    bound = system.add_profile("Wired connection 2", "lan0", active=True)
    manager, cfg = nm.Nm(system), _cfg()
    first, _ = nm.setup_lan(manager, cfg, tmp_path)
    cfg.network.lan_address = "10.20.0.1/24"
    second, _ = nm.setup_lan(manager, cfg, tmp_path, first)
    assert second["profile"] == first["profile"]
    assert system.profile(nm.PROFILE)["ipv4.addresses"] == "10.20.0.1/24"
    # Исходное состояние чужого профиля — «автоподключение включено», а не то,
    # каким его оставила первая установка.
    assert second["disabled"] == [
        {"uuid": bound, "name": "Wired connection 2", "autoconnect": "yes", "active": True}]


def test_setup_lan_without_carrier_only_warns(system, tmp_path):
    system.refuse["connection up"] = "Connection activation failed: No carrier"
    record, warnings = nm.setup_lan(nm.Nm(system), _cfg(), tmp_path)
    assert record["profile"] and "не активирован" in warnings[0]


def test_restore_lan_returns_profiles_and_survives_a_deleted_one(system, tmp_path):
    bound = system.add_profile("Wired connection 2", "lan0", active=True)
    gone = system.add_profile("старый", "lan0")
    manager = nm.Nm(system)
    record, _ = nm.setup_lan(manager, _cfg(), tmp_path)
    del system.profiles[gone]  # пользователь удалил профиль после установки
    assert nm.restore_lan(manager, record) == []
    assert nm.PROFILE not in [item["connection.id"] for item in system.profiles.values()]
    assert system.profiles[bound]["connection.autoconnect"] == "yes"
    assert system.profiles[bound]["device"] == "lan0"
    # Активация — не дожидаясь DHCP: роутера на том конце может не быть.
    assert ("nmcli", "--wait", "0", "connection", "up", bound, "ifname", "lan0") in system.calls


def test_wan_ipv6_is_disabled_and_restored(system):
    manager = nm.Nm(system)
    record, warnings = nm.wan_ipv6_off(manager, "wan0")
    uuid = system.uuid_of("wan")
    assert record == {"device": "wan0", "uuid": uuid, "ipv6_method": "auto"} and not warnings
    assert system.profiles[uuid]["ipv6.method"] == "disabled"
    # Повторный вызов исходное значение не затирает.
    again, _ = nm.wan_ipv6_off(manager, "wan0", record)
    assert again == record
    assert nm.restore_wan(manager, record) == []
    assert system.profiles[uuid]["ipv6.method"] == "auto"
    assert system.calls[-1] == ("nmcli", "device", "reapply", "wan0")


def test_wan_ipv6_warns_when_wan_is_not_managed(system):
    system.profile("wan")["device"] = ""  # на wan0 нет активного профиля
    record, warnings = nm.wan_ipv6_off(nm.Nm(system), "wan0")
    assert record is None and "не управляется NetworkManager" in warnings[0]
    record, warnings = nm.wan_ipv6_off(nm.Nm(system), "")
    assert record is None and "(не найден)" in warnings[0]


def test_wan_ipv6_failures_are_warnings_not_errors(system):
    manager = nm.Nm(system)
    system.refuse["device reapply"] = "Reapply failed"
    record, warnings = nm.wan_ipv6_off(manager, "wan0")
    assert record is not None and "после переподключения" in warnings[0]
    system.profile("wan")["ipv6.method"] = "auto"
    system.refuse["connection modify"] = "property is not allowed"
    record, warnings = nm.wan_ipv6_off(manager, "wan0")
    assert record is None and "не отключён" in warnings[0]


def test_modify_error_is_a_command_error(system):
    with pytest.raises(CommandError, match="no such connection"):
        nm.Nm(system).modify("00000000-0000-4000-8000-999999999999", "ipv6.method", "auto")
