import json

import pytest

from xgw.desync.shadow import evaluate, load_samples

VIDEO = "8plwv25NYRo"


def sample(t, **changes):
    row = {
        "t_s": t, "video_id": VIDEO, "has_video": True, "document_id": 1, "media_id": 1,
        "position": min(t, 5), "playback_rate": 1, "buffer_seconds": 0, "ready_state": 2,
        "events": [], "event_overflow": 0, "error_code": None,
        **dict.fromkeys(("paused", "ad", "hidden", "seeking", "ended"), False),
    }
    return row | changes


def test_alerts_follow_progress_and_each_threshold_fires_once():
    rows = [sample(t, network={"data_bytes": 65536, "inflight": 1}) for t in range(81)]
    result = evaluate(rows, VIDEO)
    assert result["phase_seconds"] == {"advancing": 5, "starved": 75}
    assert result["signals"] == [
        {"threshold_seconds": n, "start_s": 5, "observed_s": 5 + n, "cause": "unknown",
         "media_network": "pending_without_data"}
        for n in (15, 30, 60)
    ]


@pytest.mark.parametrize(("changes", "phase"), [
    ({"paused": True}, "paused"),
    ({"seeking": True}, "seeking"),
    ({"hidden": True}, "hidden"),
    ({"ad": True}, "ad"),
    ({"ended": True}, "ended"),
    ({"error_code": 2}, "player_error"),
    ({"ready_state": 4, "buffer_seconds": 80}, "buffered"),
    ({"ready_state": 4}, "ready"),
    ({"position": 0}, "startup"),
    ({"events": [{"name": "seeking"}, {"name": "seeked"}]}, "transition"),
    ({"buffer_seconds": None}, "missing"),
])
def test_excludes_non_starvation_even_for_long_intervals(changes, phase):
    result = evaluate([
        sample(t, **(changes if t > 5 or phase == "startup" else {})) for t in range(72)
    ], VIDEO)
    assert result["signals"] == []
    assert result["phase_seconds"][phase] >= 65


@pytest.mark.parametrize("interruption", ["gap", "overflow", "media_switch", "seek"])
def test_does_not_merge_two_short_windows(interruption):
    rows = [sample(t) for t in range(31)]
    if interruption == "gap":
        del rows[17:20]
    elif interruption == "overflow":
        for row in rows[18:]:
            row["event_overflow"] += 1
    elif interruption == "media_switch":
        for row in rows[18:]:
            row["media_id"] += 1
    else:
        rows[18]["events"] = [{"name": "seeking"}, {"name": "seeked"}]
    assert evaluate(rows, VIDEO)["signals"] == []


def test_idle_or_missing_cdp_metrics_do_not_attribute_the_cause():
    rows = [sample(t) for t in range(21)]
    assert evaluate(rows, VIDEO)["signals"][0]["media_network"] == "unavailable"
    for row in rows:
        row["network"] = {"inflight": 0, "data_bytes": 0}
    signal = evaluate(rows, VIDEO)["signals"][0]
    assert signal["media_network"] == "not_continuous"
    assert signal["cause"] == "unknown"


def test_reads_both_recording_formats_and_rejects_a_repeated_clock(tmp_path):
    rows = [sample(0), sample(1)]
    snippet = tmp_path / "player.json"
    snippet.write_text(json.dumps({"rows": rows}))
    cdp = tmp_path / "samples.jsonl"
    cdp.write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert load_samples(snippet) == load_samples(cdp) == rows
    with pytest.raises(ValueError, match="clock"):
        evaluate(rows + rows, VIDEO)
