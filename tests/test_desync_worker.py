import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from xgw import nfqws2, zapret2
from xgw.config import Config
from xgw.desync import preflight as worker_preflight
from xgw.desync import schema, worker
from xgw.net.cmd import CommandError


def test_systemd_main_pid_and_netlink_port_id_are_distinct(tmp_path, monkeypatch):
    queue = tmp_path / "queues"
    netlink = tmp_path / "netlink"
    queue.write_text(" 200 45123 0 2 65535 3 6 42 1\n")
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
    assert worker.owner_sample(run, nfqws2.UNIT, 200) == worker.QueueOwner("socket:[901]", (3, 6, 42))
    queue.write_text("200 45123 0 2 65535 4294967296 6 42 1\n")
    assert worker.owner_sample(run, nfqws2.UNIT, 200) == worker.QueueOwner("socket:[901]", None)
    queue.write_text("200 45123\n")
    assert worker.owner_sample(run, nfqws2.UNIT, 200) == worker.QueueOwner("socket:[901]", None)
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
    monkeypatch.setattr(worker_preflight, "check", lambda args, runner: args)

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
    monkeypatch.setattr(worker_preflight, "check", lambda args, runner: args)
    installation = nfqws2.Installation(Path("nfqws2"), Path("lua"),
                                       dict.fromkeys(nfqws2.BLOBS))
    with pytest.raises(ValueError, match="worker_unit_busy"):
        runtime.start(Config(), installation, "seqovl")
    runtime.stop()
    assert all(argv[0] != "systemd-run" and "stop" not in argv for argv in calls)
    assert runtime.slot.lease is None


@pytest.mark.parametrize("module", [zapret2, nfqws2])
def test_clients_record_only_owner_transitions_for_their_lease(monkeypatch, module):
    slot = worker.WorkerSlot()
    runner = Mock(return_value="active")
    runtime = module.Runtime(runner, slot=slot)
    cfg = Config()
    key = schema.fingerprint(schema.migrate(vars(cfg.zapret2)))
    assert worker.policy_revision(cfg.zapret2) == key
    lease = slot.reserve(module.UNIT, 201, policy_key=key)
    runtime.lease = lease
    monkeypatch.setattr(runtime, "occupied", lambda queue: True)
    owner = worker.QueueOwner("socket:[901]", None)
    verify = Mock(side_effect=[None, owner, owner, None])
    monkeypatch.setattr(worker, "owner_sample", verify)

    assert [runtime.alive(201) for _ in range(4)] == [False, True, True, False]
    slot.release(lease)
    newer = slot.reserve(module.UNIT, 201)
    assert not slot.observe_owner(lease, True)
    assert not runtime.alive(201)
    assert slot.snapshot()[0] is newer
    _, history = slot.snapshot()
    assert [event["phase"] for event in history["events"]] == [
        "reserved", "owner_verified", "owner_unverified", "released", "reserved"]
    assert {event["policy_key"] for event in history["events"][:-1]} == {key}
    assert [event["generation"] for event in history["events"]] == [1, 1, 1, 1, 2]


def test_queue_counters_record_only_deltas_with_continuous_owner():
    slot = worker.WorkerSlot()
    lease = slot.reserve(worker.ENGINE_UNIT, 201)

    def sample(inode, overflow, netlink, sequence):
        return slot.observe_owner(lease, True, worker.QueueOwner(inode, (overflow, netlink, sequence)))

    assert sample("first", 8, 12, 50)  # first observation is a baseline
    assert sample("first", 8, 12, 54)  # incoming packets, no drops
    assert sample("first", 10, 15, 60)
    assert sample("next", 35, 45, 100)  # socket changed
    assert sample("next", 36, 45, 3)  # sequence reset at the same socket
    assert sample("next", 36, 49, 6)
    assert sample("next", 0, 0, 8)  # overflow or reset; no fabricated counter wrap
    assert not slot.observe_owner(lease, False)
    assert slot.snapshot()[1]["queue_counters"] is None
    assert sample("next", 10, 10, 1000)  # fresh baseline after loss
    view = slot.snapshot()[1]
    assert view["queue_counters"]["generation"] == lease.generation
    assert view["queue_counters"]["overflow"] == view["queue_counters"]["netlink"] == 10
    events = view["events"]
    assert [event["phase"] for event in events] == [
        "reserved", "owner_verified", "queue_drops", "queue_drops",
        "owner_unverified", "owner_verified",
    ]
    assert [(e["overflow_delta"], e["netlink_delta"]) for e in events if e["phase"] == "queue_drops"
            ] == [(2, 3), (0, 4)]
    slot.release(lease)
    newer = slot.reserve(worker.SELECTED_UNIT, 201)
    assert not sample("next", 20, 20, 2000)
    assert slot.snapshot()[1]["queue_counters"] is None and slot.lease is newer


def test_worker_history_is_capped_and_restart_gets_a_new_epoch():
    slot = worker.WorkerSlot()
    for _ in range(worker.EVENT_LIMIT):
        lease = slot.reserve(zapret2.UNIT, 201)
        slot.release(lease)
    lease, history = slot.snapshot()
    assert lease is None
    assert len(history["events"]) == history["discarded"] == worker.EVENT_LIMIT
    assert history["events"][0]["seq"] == history["discarded"] + 1
    assert history["events"][-1]["seq"] == history["last_seq"]
    history["events"][-1]["phase"] = "modified"
    assert slot.snapshot()[1]["events"][-1]["phase"] == "released"
    _, restarted = worker.WorkerSlot().snapshot()
    assert restarted["epoch"] != history["epoch"] and restarted["events"] == []


@pytest.mark.parametrize(("failing_flag", "expected"), [
    ("--dry-run", "bad_worker_options"), ("--intercept=0", "lua_init_failed"),
])
def test_preflight_uses_resolved_paths_and_distinguishes_parse_from_lua(
    monkeypatch, tmp_path, failing_flag, expected,
):
    binary = tmp_path / "real-nfqws2"
    lua = tmp_path / "real.lua"
    paths = {Path("alias"): binary, Path("lua-alias"): lua}
    monkeypatch.setattr(worker_preflight, "trusted_file", paths.__getitem__)
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv)
        if argv[-1] == failing_flag:
            raise CommandError("private file detail")

    with pytest.raises(ValueError, match=f"^{expected}$"):
        worker_preflight.check(["alias", "--lua-init=@lua-alias"], run)
    assert all(argv[:2] == [str(binary), f"--lua-init=@{lua}"] for argv in calls)
    assert [argv[-1] for argv in calls] == (
        ["--dry-run"] if failing_flag == "--dry-run" else ["--dry-run", "--intercept=0"])


def test_managed_lua_mismatch_stops_before_executing_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(worker_preflight, "MANAGED_ROOT", tmp_path)
    monkeypatch.setattr(worker_preflight, "trusted_file", lambda path: path)
    binary = tmp_path / worker_preflight.VERSION / "nfqws2"
    lua = binary.parent / "lua" / "zapret-lib.lua"
    lua.parent.mkdir(parents=True)
    lua.write_bytes(b"tampered library")
    runner = Mock()
    with pytest.raises(ValueError, match=r"^bundle_mismatch$"):
        worker_preflight.check([str(binary), f"--lua-init=@{lua}"], runner)
    runner.assert_not_called()


def test_packaged_binary_mismatch_aborts_before_preflight(monkeypatch, tmp_path):
    monkeypatch.setattr(worker_preflight, "MANAGED_ROOT", tmp_path)
    monkeypatch.setattr(worker_preflight, "trusted_file", lambda path: path)
    binary = tmp_path / worker_preflight.VERSION / "nfqws2"
    binary.parent.mkdir()
    binary.write_bytes(b"unexpected program")
    (binary.parent / "bundle.json").write_text(json.dumps({
        "version": worker_preflight.VERSION, "commit": worker_preflight.COMMIT,
        "machine": worker_preflight.platform.machine(), "system": "Linux",
        "files": {"nfqws2": "0" * 64},
    }), encoding="utf-8")
    runner = Mock()
    with pytest.raises(ValueError, match=r"^bundle_mismatch$"):
        worker_preflight.check([str(binary)], runner)
    runner.assert_not_called()
