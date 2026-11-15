from pathlib import Path
from unittest.mock import Mock

import pytest

from xgw import nfqws2, zapret2
from xgw.config import Config
from xgw.desync import worker
from xgw.net.cmd import CommandError


def test_systemd_main_pid_and_netlink_port_id_are_distinct(tmp_path, monkeypatch):
    queue = tmp_path / "queues"
    netlink = tmp_path / "netlink"
    queue.write_text(" 200 45123 0 2 65535 0 0 1 1\n")
    netlink.write_text(
        "sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n"
        "0 12 45123 00000000 0 0 0 2 0 901\n"
        "0  0 45123 00000000 0 0 0 2 0 902\n"
    )
    monkeypatch.setattr(worker, "QUEUE_STATE", queue)
    monkeypatch.setattr(worker, "NETLINK_STATE", netlink)
    fd = Mock()
    # Avoid relying on Windows' permissions for creating symbolic links.
    class ProcessTree:
        def __init__(self, parts=()):
            self.parts = parts

        def __truediv__(self, part):
            return ProcessTree((*self.parts, part))

        def iterdir(self):
            assert self.parts == ("842", "fd")
            return iter([fd])

    monkeypatch.setattr(worker, "PROC", ProcessTree())
    run = Mock(return_value="842\n")
    fd.readlink.return_value = Path("socket:[902]")
    assert not worker.verify_owner(run, nfqws2.UNIT, 200)
    fd.readlink.return_value = Path("socket:[901]")
    assert worker.verify_owner(run, nfqws2.UNIT, 200)
    assert not worker.verify_owner(run, nfqws2.UNIT, 201)
    fd.readlink.side_effect = PermissionError
    assert not worker.verify_owner(run, nfqws2.UNIT, 200)


def test_failed_selected_start_retains_slot_until_its_stop_is_confirmed(monkeypatch):
    slot = worker.WorkerSlot()
    runner = Mock(return_value="inactive")
    selected = zapret2.Runtime(runner, slot=slot)
    engine = nfqws2.Runtime(runner, slot=slot)
    cfg = Config()
    installation = nfqws2.Installation(Path("nfqws2"), Path("lua"),
                                      dict.fromkeys(nfqws2.BLOBS))
    monkeypatch.setattr(selected, "occupied", lambda queue: False)
    monkeypatch.setattr(engine, "occupied", lambda queue: False)
    monkeypatch.setattr(engine, "_check_files", lambda installation: None)
    monkeypatch.setattr(selected, "_check_files", lambda cfg: None)

    def uncertain_start(argv, **kwargs):
        if argv[0] == "systemd-run":
            raise CommandError("timed out after creating the transient unit")
        return "inactive"

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(runner, "side_effect", uncertain_start)
        with pytest.raises(CommandError):
            selected.start(cfg)
    old = slot.lease
    assert old is not None and old.unit == zapret2.UNIT

    runner.side_effect = CommandError("stop timed out")
    with pytest.raises(CommandError):
        selected.stop()
    runner.side_effect = None
    cfg.zapret2.engine_queue += 1
    with pytest.raises(ValueError, match="worker_handoff_pending"):
        engine.start(cfg, installation, "seqovl")
    assert slot.lease is old
    assert engine.lease is None

    selected.stop()
    engine.start(cfg, installation, "seqovl")
    assert slot.lease is not None and slot.lease.generation == old.generation + 1
    runner.reset_mock()
    slot.release(old)
    selected.stop()
    assert slot.lease is engine.lease
    runner.assert_not_called()


def test_active_peer_unit_is_not_taken_over_after_daemon_restart(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return "active" if argv == ["systemctl", "is-active", zapret2.UNIT] else "inactive"

    runtime = nfqws2.Runtime(run)
    monkeypatch.setattr(runtime, "occupied", lambda queue: False)
    monkeypatch.setattr(runtime, "_check_files", lambda installation: None)
    installation = nfqws2.Installation(Path("nfqws2"), Path("lua"),
                                       dict.fromkeys(nfqws2.BLOBS))
    with pytest.raises(ValueError, match="worker_unit_busy"):
        runtime.start(Config(), installation, "seqovl")
    runtime.stop()
    assert all(argv[0] != "systemd-run" and "stop" not in argv for argv in calls)
    assert runtime.slot.lease is None
