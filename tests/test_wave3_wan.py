"""Обновление сохраняет действующий WAN; проверка без настоящей сети."""
from test_install import Box

from xgw.install import Journal
from xgw.net import nm, sysctl


def test_existing_unit_preserves_current_wan_even_after_partial_install(tmp_path):
    box = Box(tmp_path)
    box.paths.systemd_dir.mkdir(parents=True, exist_ok=True)
    (box.paths.systemd_dir / "xgw.service").write_text("existing partial installation")
    before = dict(box.system.profile("wan"))
    box.cfg.tailscale.route = "vpn"
    assert box.install() == 0, box.text()
    assert box.system.profile("wan") == before
    assert not box.system.commands("nmcli", "device", "reapply", "wan0")
    assert not [call for call in box.system.commands("nmcli", "connection", "modify")
                if box.system.uuid_of("wan") in call]
    assert box.cfg.tailscale.route == "vpn" and box.cfg.capture.local


def test_preserved_wan_boot_key_is_not_written_back_to_current_interface(tmp_path, monkeypatch):
    box = Box(tmp_path)
    key = "net/ipv6/conf/wan0/disable_ipv6"
    target = box.proc / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("0\n")  # владелец уже изменил текущее значение
    box.paths.sysctl_file.parent.mkdir(parents=True, exist_ok=True)
    box.paths.sysctl_file.write_text(key + " = 1\n")
    written = []
    original = sysctl.write

    def write(name, value, root):
        written.append(name)
        original(name, value, root)

    monkeypatch.setattr(sysctl, "write", write)
    previous = sysctl.install(box.paths, box.proc, {**sysctl.SETTINGS, key: "1"}, preserve_wan=True)
    assert key not in written and key not in previous
    assert target.read_text().strip() == "0"
    assert key + " = 1" in box.paths.sysctl_file.read_text()


def test_update_does_not_move_active_wan_profile_named_xgw_lan(tmp_path):
    box = Box(tmp_path)
    Journal(box.paths.journal_file).set("finished", 1)
    wan = box.system.profile("wan")
    wan["connection.id"] = nm.PROFILE  # след старой ошибочной привязки
    before = dict(wan)
    assert box.install() == 1
    assert "перепривязка входящего подключения запрещена" in box.text()
    assert wan == before
    uuid = box.system.uuid_of(nm.PROFILE)
    assert not [call for call in box.system.commands("nmcli", "connection", "modify")
                if uuid in call]
