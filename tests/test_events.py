"""События сети, сна и правил (watch/events.py): разбор строк, debounce, перезапуск
подпроцесса, окно своих загрузок и — под root — что события доходят без буферизации."""

import os
import shutil
import subprocess
import sys
import threading
import time

import pytest

from xgw.watch import events
from xgw.watch.events import NetEvents, parse_net, parse_rules, parse_sleep

# Настоящий вывод `ip -o monitor link address route` (iproute2 6.19): dummy-интерфейс d0
# поднят, получил адрес и маршрут по умолчанию, затем всё убрано.
IP_LINES = {
    "2: d0: <BROADCAST,NOARP> mtu 1500 qdisc noop state DOWN group default \\    "
    "link/ether b2:4b:ec:ef:d3:d5 brd ff:ff:ff:ff:ff:ff": "d0",
    "2: d0: <BROADCAST,NOARP,UP,LOWER_UP> mtu 1500 qdisc noqueue state UNKNOWN group default "
    "\\    link/ether b2:4b:ec:ef:d3:d5 brd ff:ff:ff:ff:ff:ff": None,
    "multicast ff00::/8 dev d0 table local proto kernel metric 256 pref medium": None,
    "2: d0    inet 10.9.9.2/24 scope global d0\\       valid_lft forever preferred_lft forever":
        None,
    "local 10.9.9.2 dev d0 table local proto kernel scope host src 10.9.9.2 ": None,
    "10.9.9.0/24 dev d0 proto kernel scope link src 10.9.9.2 ": None,
    "default via 10.9.9.1 dev d0 ": "d0",
    "Deleted default via 10.9.9.1 dev d0 ": "d0",
    "Deleted 2: d0    inet 10.9.9.2/24 scope global d0\\       valid_lft forever "
    "preferred_lft forever": "d0",
    "Deleted 10.9.9.0/24 dev d0 proto kernel scope link src 10.9.9.2 ": "d0",
    "Deleted 2: d0: <BROADCAST,NOARP> mtu 1500 qdisc noop state DOWN group default \\    "
    "link/ether b2:4b:ec:ef:d3:d5 brd ff:ff:ff:ff:ff:ff": "d0",
    "3: wan0@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group "
    "default \\    link/ether 6a:1f:00:11:22:33 brd ff:ff:ff:ff:ff:ff link-netns inet": "wan0",
    # Не повод: loopback, TUN самого Xray и контейнеры Docker.
    "Deleted 1: lo    inet 127.0.0.1/8 scope host lo": None,
    "Deleted 7: xgwtun0: <POINTOPOINT,NOARP> mtu 1500 qdisc noop state DOWN group default": None,
    "Deleted local 169.254.10.1 dev xgwtun0 table local proto kernel scope host": None,
    "5: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN group "
    "default": None,
    "Deleted 9: veth12ab@if8: <BROADCAST,MULTICAST> mtu 1500 qdisc noop state DOWN": None,
    "Deleted 172.18.0.0/16 dev br-0a1b2c proto kernel scope link src 172.18.0.1": None,
    "": None,
}

# Настоящий вывод `nft monitor` (nftables 1.1.6). `nft flush table ip xgw` монитор
# показывает правилами (`delete rule … handle N`), `flush ruleset` — таблицами.
NFT_LINES = {
    "add table ip xgw": False,
    "# new generation 2 by process 31391 (nft)": False,
    "add chain ip xgw output { type filter hook output priority filter; policy accept; }": False,
    "add rule ip xgw output counter packets 0 bytes 0 accept": False,
    "delete rule ip xgw output handle 2": True,
    "delete chain ip xgw output": True,
    "delete table ip xgw": True,
    "delete table ip6 xgw6": True,
    "flush table ip xgw": True,
    "flush ruleset": True,
    "delete table ip filter": False,  # чужая таблица
    "delete rule inet docker forward handle 7": False,
    "delete table ip6 xgw": False,  # не та пара семейство + имя
}

SLEEP_RESUMED = (
    '{"type":"signal","endian":"l","flags":1,"version":1,"cookie":2,'
    '"timestamp-realtime":1792449079953825,"sender":":1.101","path":"/org/freedesktop/login1",'
    '"interface":"org.freedesktop.login1.Manager","member":"PrepareForSleep",'
    '"payload":{"type":"b","data":[false]}}'
)


@pytest.mark.parametrize("line", list(IP_LINES))
def test_parse_net_picks_events_worth_a_step(line):
    assert parse_net(line, (*events.IGNORED_IFS, "xgwtun0")) == IP_LINES[line]


@pytest.mark.parametrize("line", list(NFT_LINES))
def test_parse_rules_reacts_to_removals_from_xgw_tables(line):
    assert parse_rules(line) is NFT_LINES[line]


def test_parse_sleep_tells_resume_from_suspend():
    assert parse_sleep(SLEEP_RESUMED) is False
    assert parse_sleep(SLEEP_RESUMED.replace("[false]", "[true]")) is True
    assert parse_sleep(SLEEP_RESUMED.replace("PrepareForSleep", "PrepareForShutdown")) is None
    assert parse_sleep("Monitoring bus message stream.") is None
    assert parse_sleep('{"member":"PrepareForSleep","payload":{"data":["x"]}}') is None


class FakeProc:
    """Подпроцесс-монитор: отдаёт строки (число в списке — пауза, с) и выходит, когда они
    кончились, либо ждёт hold секунд."""

    def __init__(self, lines, gap=0.0, hold=0.0):
        self._lines, self._gap, self._hold = list(lines), gap, hold
        self._done = threading.Event()
        self.stdout = self._read()
        self.returncode = None

    def _read(self):
        for line in self._lines:
            if isinstance(line, float):
                time.sleep(line)
                continue
            if self._gap:
                time.sleep(self._gap)
            yield line + "\n"
        self._done.wait(self._hold)

    def terminate(self):
        self._done.set()
        self.returncode = -15

    kill = terminate

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode


class Launcher:
    """runner_popen: каждый запуск — следующий FakeProc из списка (последний повторяется)."""

    def __init__(self, *procs):
        self.procs = list(procs)
        self.argv: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.argv.append(argv)
        make = self.procs.pop(0) if len(self.procs) > 1 else self.procs[0]
        return make()


def _events(launcher, wakes, **kwargs):
    kwargs.setdefault("sources", {"rules": ["nft", "monitor"]})
    return NetEvents(
        wakes.append, launcher, which=lambda name: f"/usr/sbin/{name}", **kwargs
    )


def _wait(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_one_burst_wakes_once():
    """`nft flush table` — по строке на правило, все сразу: одно пробуждение, без хвоста."""
    wakes: list[str] = []
    lines = [f"delete rule ip xgw output handle {n}" for n in range(20)]
    watcher = _events(Launcher(lambda: FakeProc(lines, hold=5)), wakes, debounce=0.6)
    watcher.start()
    try:
        assert _wait(lambda: wakes == ["rules"], 1.0)
        time.sleep(1.2)
        assert wakes == ["rules"]
    finally:
        watcher.stop()


def test_second_burst_within_the_window_wakes_at_its_end():
    """Второй flush вслед за первым (внутри окна debounce) — ещё одно пробуждение в конце
    окна: последнее изменение не должно ждать очередного шага демона."""
    wakes: list[str] = []
    lines = ["delete table ip xgw", "delete table ip6 xgw6", 0.4, "delete chain ip xgw output",
             "delete chain ip xgw forward"]
    watcher = _events(Launcher(lambda: FakeProc(lines, hold=5)), wakes, debounce=1.0)
    watcher.start()
    try:
        assert _wait(lambda: wakes == ["rules"], 0.3)
        time.sleep(0.55)
        assert wakes == ["rules"]  # вторая пачка в окне сразу не будит…
        assert _wait(lambda: wakes == ["rules", "rules"], 1.0)  # …а в его конце — да
        time.sleep(1.2)
        assert wakes == ["rules", "rules"]
    finally:
        watcher.stop()


def test_own_rule_loads_do_not_wake():
    wakes: list[str] = []
    quiet = [True]
    lines = ["delete table ip xgw", "add table ip xgw"]
    watcher = _events(
        Launcher(lambda: FakeProc(lines, hold=5)), wakes, debounce=0.1,
        quiet_rules=lambda: quiet[0],
    )
    watcher.start()
    try:
        time.sleep(0.4)
        assert wakes == []
    finally:
        watcher.stop()


def test_exited_monitor_is_started_again():
    wakes: list[str] = []
    launcher = Launcher(
        lambda: FakeProc([]), lambda: FakeProc([]), lambda: FakeProc(["flush ruleset"], hold=5)
    )
    watcher = _events(launcher, wakes, restart_pause=0.05)
    watcher.start()
    try:
        assert _wait(lambda: watcher.started.get("rules") == 3 and "rules" in wakes, 3.0)
    finally:
        watcher.stop()


def test_missing_program_is_skipped_with_a_warning(caplog):
    wakes: list[str] = []
    watcher = NetEvents(
        wakes.append, Launcher(lambda: FakeProc([])), which=lambda name: None,
        sources={"sleep": ["busctl", "monitor"]},
    )
    with caplog.at_level("WARNING"):
        watcher.start()
        watcher.stop()
    assert "нет программы busctl" in caplog.text and watcher.started == {}


def test_each_source_wakes_with_its_reason():
    wakes: list[str] = []
    sources = {
        "net": ["ip", "-o", "monitor"],
        "sleep": ["busctl", "monitor"],
        "rules": ["nft", "monitor"],
    }
    feeds = {
        "ip": ["Deleted default via 5.5.5.1 dev wan0 ", "2: lo: <LOOPBACK> state DOWN"],
        "busctl": [SLEEP_RESUMED.replace("[false]", "[true]"), SLEEP_RESUMED],
        "nft": ["add table ip xgw", "delete chain ip xgw output"],
    }
    launcher = lambda argv, **kwargs: FakeProc(feeds[argv[0]], hold=5)  # noqa: E731
    watcher = NetEvents(
        wakes.append, launcher, which=lambda name: name, sources=sources, debounce=0.1
    )
    watcher.start()
    try:
        assert _wait(lambda: sorted(wakes) == ["net", "rules", "sleep"], 2.0)
        time.sleep(0.3)
        assert sorted(wakes) == ["net", "rules", "sleep"]  # засыпание и lo — не повод
    finally:
        watcher.stop()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="нужен Linux")
def test_stop_is_quick_with_real_processes():
    """Остановка демона (systemctl restart xgw, ~0,5 с) не должна ждать мониторов."""
    sleeper = shutil.which("sleep")
    watcher = NetEvents(
        lambda reason: None, sources={"net": [sleeper, "30"], "rules": [sleeper, "30"]},
    )
    watcher.start()
    assert _wait(lambda: len(watcher._procs) == 2, 2.0)
    procs = list(watcher._procs.values())
    began = time.monotonic()
    watcher.stop()
    assert time.monotonic() - began < 0.6
    assert all(proc.poll() is not None for proc in procs)


def _root_tools() -> str:
    if not sys.platform.startswith("linux") or os.geteuid() != 0:
        return "нужен root в Linux"
    missing = [name for name in ("unshare", "nsenter", "ip", "nft") if shutil.which(name) is None]
    return f"нет программ: {', '.join(missing)}" if missing else ""


@pytest.mark.skipif(bool(_root_tools()), reason=_root_tools() or "-")
def test_monitor_events_arrive_while_process_runs():
    """Под root, в своём сетевом пространстве (unshare -n): `nft add table` и `ip link add
    dummy` доходят до читателя не позже чем через 1 с, пока подпроцесс ещё работает, —
    страховка от буферизации пайпа в будущих версиях программ."""
    holder = subprocess.Popen(["unshare", "-n", "sleep", "60"])
    try:
        time.sleep(0.3)
        enter = ["nsenter", "-t", str(holder.pid), "-n"]
        lines: dict[str, list[tuple[float, str]]] = {"net": [], "rules": []}
        watcher = NetEvents(
            lambda reason: None,
            sources={"net": [*enter, *events.SOURCES["net"]],
                     "rules": [*enter, *events.SOURCES["rules"]]},
        )
        watcher._line = lambda name, line: lines[name].append((time.monotonic(), line))
        watcher.start()
        try:
            assert _wait(lambda: len(watcher._procs) == 2, 2.0)
            time.sleep(0.5)  # мониторы подписались на netlink
            for name, argv, needle in (
                ("rules", ["nft", "add", "table", "ip", "xgw"], "add table ip xgw"),
                ("net", ["ip", "link", "add", "xgwtest0", "type", "dummy"], "xgwtest0"),
            ):
                began = time.monotonic()
                subprocess.run([*enter, *argv], check=True)
                seen = lines[name]
                assert _wait(
                    lambda seen=seen, needle=needle: any(needle in text for _, text in seen), 1.0
                ), (name, seen)
                arrived = next(at for at, text in lines[name] if needle in text)
                assert arrived - began <= 1.0
                assert watcher._procs[name].poll() is None  # строка пришла, пока он работает
        finally:
            watcher.stop()
    finally:
        holder.kill()
        holder.wait()


def test_events_in_the_own_load_window_are_checked_once_it_closes():
    """Пятый аудит: события правил в окне своей загрузки не будят сразу, но среди них могли быть
    и чужие — когда окно закроется, одно пробуждение «rules»."""
    wakes: list[str] = []
    quiet = [True]
    lines = ["delete rule ip xgw output handle 7", "add rule ip xgw output handle 9"]
    watcher = _events(
        Launcher(lambda: FakeProc(lines, hold=5)), wakes, debounce=0.1,
        quiet_rules=lambda: quiet[0],
    )
    watcher.start()
    try:
        time.sleep(0.3)
        assert wakes == []
        quiet[0] = False
        assert _wait(lambda: wakes == ["rules"], 3.0)
        time.sleep(0.8)
        assert wakes == ["rules"]
    finally:
        watcher.stop()


def test_restarted_monitor_triggers_one_check():
    """nft monitor вышел и запущен снова: события без него потеряны — одна проверка, хотя
    строк не было."""
    wakes: list[str] = []
    launcher = Launcher(lambda: FakeProc([]), lambda: FakeProc([], hold=5))
    watcher = _events(launcher, wakes, restart_pause=0.05, debounce=0.1)
    watcher.start()
    try:
        assert _wait(lambda: wakes == ["rules"], 3.0)
        assert watcher.started["rules"] == 2
    finally:
        watcher.stop()


def test_wake_queue_is_bounded(monkeypatch):
    """Буря событий не растит очередь без меры: сверх предела пробуждения не копятся."""
    from xgw.watch import events as events_module

    monkeypatch.setattr(events_module, "QUEUE_MAX", 4)
    watcher = _events(Launcher(lambda: FakeProc([])), [])
    for _ in range(100):
        watcher._put("rules")
    assert watcher._queue.qsize() == 4
