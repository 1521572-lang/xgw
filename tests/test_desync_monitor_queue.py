import json

import pytest

from xgw.desync import client


def sample(at, overflow, netlink, **fields):
    return {"at": at, "epoch": "a" * 32, "series": 1,
            "overflow": overflow, "netlink": netlink} | fields


def row(at, counters, **fields):
    return {"at": at, "config_key": "private", "mode": "selective", "engine_mode": "off",
            "fresh": True, "policy_matched": True, "state": "active",
            "queue_loss_sample": counters} | fields


def summarize(tmp_path, *rows):
    path = tmp_path / "queue.jsonl"
    path.write_text("\n".join(json.dumps(item) for item in rows), encoding="utf-8")
    return client.analyze(path)["queue_losses"]


def test_monitor_uses_kernel_sample_time_and_exports_only_aggregate_drops(tmp_path, monkeypatch):
    monkeypatch.setattr(client.time, "time", lambda: 110)
    counter = sample(100, 10, 30, socket="private")
    state = {"zapret2": {"evidence": {"queue_loss_sample": counter}}}
    assert client.observation(state)["queue_loss_sample"] == sample(100, 10, 30)

    stats = summarize(tmp_path, row(110, counter), row(120, counter),
                      row(150, sample(140, 13, 30)), row(167, sample(160, 13, 33)))
    assert stats == {
        "samples_with_counters": 4,
        "by_policy": {"selective/off": {
            "intervals": 2, "seconds": 60, "overflow_delta": 3, "netlink_delta": 3}},
    }
    assert counter["epoch"] not in json.dumps(stats)


@pytest.mark.parametrize("after", [
    row(130, None), row(130, sample(130, 50, 50, series=2)),
    row(130, sample(130, 50, 50, epoch="b" * 32)),
    row(130, sample(130, 50, 50), config_key="changed"),
    row(130, sample(130, 50, 50), state="fallback"),
    row(130, sample(130, 50, 50), policy_matched=False),
    row(130, sample(130, 50, 50), fresh=False),
    row(130, sample(39, 50, 50)), row(130, sample(131, 50, 50)),
    row(130, sample(130, 11, 7)), row(130, sample(130, 50, True)),
    row(800, sample(795, 50, 50)), row(89, sample(82, 50, 50)),
])
def test_monitor_does_not_add_drops_across_discontinuities(tmp_path, after):
    stats = summarize(tmp_path, row(100, sample(90, 10, 8)), after)
    assert stats["by_policy"] == {}


def test_monitor_distinguishes_measured_zero_from_unavailable_counters(tmp_path):
    result = summarize(tmp_path, row(100, sample(95, 8, 6)), row(120, sample(110, 8, 6)))
    assert result["by_policy"]["selective/off"] == {
        "intervals": 1, "seconds": 15, "overflow_delta": 0, "netlink_delta": 0,
    }
    assert summarize(tmp_path, row(100, None), row(120, None)) == {
        "samples_with_counters": 0, "by_policy": {},
    }
