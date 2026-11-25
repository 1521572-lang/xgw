import pytest

from docs.helpers import standalone_topology
from xgw.apply import singbox_process as processes


@pytest.mark.parametrize("slot", processes.SLOTS)
def test_managed_topology_accepts_an_obsolete_resume_flag(slot):
    state = {"active": slot, "pending": None, "draining": None, "resume_managed": True}
    sample = standalone_topology.project(state, True, {processes.unit(slot): "active"})
    assert sample["stale_resume_managed"] is True and sample["resume_managed"] is False
    assert standalone_topology.ready("stable", sample)
    assert standalone_topology.ready("managed", sample)
    assert not standalone_topology.ready("legacy_resume", sample)
    for changes in ({"marker": False}, {"pending": True}, {"standalone_stopping": True},
                    {"units": {processes.unit(slot): "inactive"}}):
        assert not standalone_topology.ready("managed", sample | changes)
        assert not standalone_topology.ready("stable", sample | changes)
    assert not standalone_topology.ready("stable", sample | {"draining": True})


def test_legacy_return_and_pause_require_a_resume_request():
    state = {"active": "legacy", "pending": None, "draining": None, "resume_managed": True}
    sample = standalone_topology.project(state, False, {processes.LEGACY: "active"})
    assert sample["resume_managed"] is True and sample["stale_resume_managed"] is False
    assert standalone_topology.ready("legacy_resume", sample)
    assert not standalone_topology.ready("paused", sample)
    paused = sample | {"units": {processes.LEGACY: "inactive"}}
    assert standalone_topology.ready("paused", paused)
    assert not standalone_topology.ready("paused", paused | {"resume_managed": False})
