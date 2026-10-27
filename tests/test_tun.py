"""TUN-интерфейс (capture.method = "tun"): модуль net/tun.py и таблица маршрутов в него."""

import pytest
from fakenet import FakeKernel

from xgw.net import iprule, tun
from xgw.net.cmd import CommandError

NAME = "xgwtun0"


def test_inbound_name_is_taken_from_the_tun_inbound_only():
    config = {"inbounds": [
        {"tag": "socks-in", "protocol": "socks", "settings": {"name": "не то"}},
        {"tag": "tun-in", "protocol": "tun", "settings": {"name": NAME, "mtu": 1500}},
    ]}
    assert tun.inbound_name(config) == NAME
    assert tun.inbound_name({"inbounds": [{"protocol": "http"}]}) is None
    assert tun.inbound_name({}) is None
    assert tun.inbound_name({"inbounds": [{"protocol": "tun", "settings": {}}]}) is None


def test_ensure_creates_a_persistent_interface_with_an_address(tmp_path):
    kernel = FakeKernel()
    conf = tmp_path / "net/ipv4/conf" / NAME
    conf.mkdir(parents=True)
    (conf / "rp_filter").write_text("2\n")
    assert tun.ensure(NAME, kernel, tmp_path) is True
    assert kernel.links == {NAME: "tun"}
    assert kernel.commands("ip", "tuntap", "add") == [
        ("ip", "tuntap", "add", "dev", NAME, "mode", "tun")
    ]
    assert ("ip", "link", "set", "dev", NAME, "mtu", "1500", "up") in kernel.calls
    # Без адреса ядро отбрасывает ответы Xray (rp_filter), поэтому адрес обязателен.
    assert ("ip", "addr", "replace", "169.254.10.1/32", "dev", NAME) in kernel.calls
    assert (conf / "rp_filter").read_text().strip() == "2"  # мягкая и при строгом conf.all
    # Повторно: интерфейс не пересоздаётся (его держит открытым Xray).
    assert tun.ensure(NAME, kernel, tmp_path) is False
    assert len(kernel.commands("ip", "tuntap", "add")) == 1
    assert tun.present(NAME, kernel)


def test_ensure_refuses_a_foreign_interface_with_that_name(tmp_path):
    kernel = FakeKernel()
    kernel.links[NAME] = "veth"
    with pytest.raises(CommandError, match="не TUN"):
        tun.ensure(NAME, kernel, tmp_path)
    assert not tun.present(NAME, kernel)
    tun.remove(NAME, kernel)  # чужой интерфейс не удаляется
    assert kernel.links == {NAME: "veth"}


def test_remove_deletes_only_our_tun_and_its_routes(tmp_path):
    kernel = FakeKernel()
    tun.remove(NAME, kernel)  # нечего убирать — не ошибка
    tun.ensure(NAME, kernel, tmp_path)
    iprule.ensure_tun(1, 101, kernel, 4, NAME)
    tun.remove(NAME, kernel)
    # Вместе с интерфейсом исчезает маршрут в него; чёрная дыра остаётся, её убирает
    # iprule.remove_tun (так делает Capture.down).
    assert kernel.links == {}
    assert kernel.routes(101) == [{"type": "blackhole", "dst": "default", "metric": 4096}]


def test_info_distinguishes_absent_from_other_errors():
    kernel = FakeKernel()
    assert tun.info(NAME, kernel) is None
    kernel.refuse = "ip -d -j link"
    with pytest.raises(CommandError, match="отказано"):
        tun.info(NAME, kernel)


# --- правила и маршруты в TUN ---------------------------------------------------------


def test_tun_rule_picks_only_local_packets_and_leaves_tproxy_alone(tmp_path):
    kernel = FakeKernel()
    tun.ensure(NAME, kernel, tmp_path)
    for family in (4, 6):
        iprule.ensure(1, 100, kernel, family)  # TPROXY сети LAN
        for _ in range(2):
            iprule.ensure_tun(1, 101, kernel, family, NAME)  # TUN для самой машины
    assert kernel.rules == [
        {"priority": 100, "src": "all", "fwmark": "0x1", "table": "100"},
        {"priority": 90, "src": "all", "fwmark": "0x1", "table": "101", "iif": "lo"},
    ]
    assert len(kernel.commands("ip", "rule", "add")) == 2  # повтор дубликатов не плодит
    assert kernel.routes(101) == [
        {"dst": "default", "dev": NAME, "scope": "link"},
        {"type": "blackhole", "dst": "default", "metric": 4096},
    ]
    assert kernel.routes(100) == [
        {"type": "local", "dst": "default", "dev": "lo", "scope": "host"}
    ]
    assert iprule.present(1, 100, kernel) and iprule.present_tun(1, 101, kernel, 4, NAME)
    assert iprule.present_tun(1, 101, kernel, 6, NAME) and kernel.rules6
    # Одно не подменяет другое: TUN-правило не принимается за правило TPROXY и наоборот.
    iprule.remove(1, 100, kernel)
    assert not iprule.present(1, 100, kernel) and iprule.present_tun(1, 101, kernel, 4, NAME)
    iprule.remove_tun(1, 101, kernel, 4, NAME)
    assert kernel.rules == [] and not kernel.routes(101) and not kernel.routes(100)


def test_blackhole_keeps_the_machine_closed_when_the_interface_is_gone(tmp_path):
    kernel = FakeKernel()
    tun.ensure(NAME, kernel, tmp_path)
    iprule.ensure_tun(1, 101, kernel, 4, NAME)
    kernel("ip link del dev xgwtun0".split())  # интерфейс пропал — маршрут в него тоже
    assert kernel.routes(101) == [{"type": "blackhole", "dst": "default", "metric": 4096}]
    assert not iprule.present_tun(1, 101, kernel, 4, NAME)  # демон это заметит и вернёт
    with pytest.raises(CommandError, match="Cannot find device"):
        iprule.ensure_tun(1, 101, kernel, 4, NAME)  # без интерфейса маршрут не добавить
    tun.ensure(NAME, kernel, tmp_path)
    iprule.ensure_tun(1, 101, kernel, 4, NAME)
    assert iprule.present_tun(1, 101, kernel, 4, NAME)
