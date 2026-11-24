import hashlib
import io
import json
import logging
import time
from contextlib import contextmanager

import pytest

from docs.helpers import xray_config_writes
from xgw.apply.applier import Applier, ApplySource
from xgw.desync import route_evidence
from xgw.generator import singbox
from xgw.log import MaskingFormatter
from xgw.paths import Paths


def snapshot(ns, zapret, xray, sb):
    applied = {"outbounds": [
        {"tag": "xgw-zapret2", "protocol": "freedom"},
        {"tag": "proxy-x", "protocol": "vless"},
        {"tag": "proxy-sb", **singbox.bridge_outbound(12345, "d", "secret")},
        {"tag": "proxy-idle", "protocol": "vless"},
        {"tag": "probe-foo", "protocol": "vless"},
    ]}
    totals = {"stats": {"outbound": {
        "xgw-zapret2": {"downlink": zapret, "uplink": 7},
        "proxy-x": {"downlink": xray, "uplink": 11},
        "proxy-sb": {"downlink": sb, "uplink": 13},
        "probe-foo": {"downlink": 99999999, "uplink": 99999999},
    }}}
    return {"monotonic_ns": ns, "xray_epoch": "same", "config_sha256": "same",
            "client_zapret2_rule": True, "tags": route_evidence.counters(applied, totals)}


def test_delta_separates_direct_and_both_vpn_cores_and_does_not_assume_missing_zero():
    before = snapshot(1_000_000_000, 100, 200, 300)
    after = snapshot(3_000_000_000, 1100, 210, 900)
    result = route_evidence.deltas(before, after)
    assert result["seconds"] == 2
    groups = result["groups"]
    assert [groups[group]["downlink"] for group in route_evidence.GROUPS] == [1000, 10, 600]
    assert groups["xray"]["tags_with_unknown_counters"] == 1
    for snap in (before, after):
        del snap["tags"]["proxy-sb"]
    groups = route_evidence.deltas(before, after)["groups"]
    assert groups["sing-box"]["downlink"] is None
    assert "secret" not in str(before)


def test_rejects_restart_config_change_and_counter_reset():
    before = snapshot(1, 10, 10, 10)
    after = snapshot(2, 20, 20, 20)
    for modification in ({"xray_epoch": "new"}, {"config_sha256": "changed"}):
        with pytest.raises(ValueError, match="incomparable_snapshots"):
            route_evidence.deltas(before, after | modification)
    with pytest.raises(ValueError, match="counter_reset_or_invalid"):
        route_evidence.deltas(before, snapshot(2, 9, 20, 20))


@pytest.mark.parametrize("prefix", ["tcp:", "//"])
def test_cdn_access_match_uses_socket_window_and_xray_epoch(prefix):
    from docs.helpers.standalone_cdn_compare import route_match

    boot = "12345678123412341234123456789abc"
    epoch = f"{boot}:42:120"
    before = {**snapshot(1, 10, 10, 10), "unix": 100, "xray_epoch": epoch}
    after = {**snapshot(2, 10, 20, 10), "unix": 124, "xray_epoch": epoch}
    sample = {"local_ip": "192.0.2.1", "local_port": 50123, "actual_peer": "1.1.1.1",
              "peer": "1.1.1.1", "started": 104, "finished": 114}
    entry = {"_SYSTEMD_UNIT": "xgw-xray.service", "_BOOT_ID": boot, "_PID": "42",
             "__REALTIME_TIMESTAMP": "105000000",
             "MESSAGE": f"from 192.0.2.1:50123 accepted {prefix}1.1.1.1:443 "
                        "[tproxy-in -> xgw-zapret2]"}
    wrong_process = {**entry, "_PID": "43"}
    later = {**entry, "__REALTIME_TIMESTAMP": "120000000"}
    assert route_match(sample, [entry, wrong_process, later], before, after) == {
        "state": "observed", "group": "zapret2",
    }
    assert route_match(sample, [wrong_process, later], before, after) == {"state": "no_access_record"}
    other_prefix = "//" if prefix == "tcp:" else "tcp:"
    duplicate = {**entry, "MESSAGE": entry["MESSAGE"].replace(
        f"accepted {prefix}", f"accepted {other_prefix}",
    )}
    assert route_match(sample, [entry, duplicate], before, after) == {"state": "ambiguous"}
    assert route_match(sample, [entry], before, {**after, "xray_epoch": "changed"})["state"] == (
        "snapshots_incomparable"
    )


@pytest.mark.parametrize("prefix", ["tcp:", "//"])
def test_xray_reload_trial_matches_only_the_current_connect(tmp_path, monkeypatch, prefix):
    from docs.helpers.cdn_reload_xray_check import MEDIA, observe_route

    log = tmp_path / "xray-access.log"
    # An earlier row with the same endpoints lies outside the appended window.
    line = f"2026/11/24 19:00:00.000001 from 127.0.0.1:41000 accepted {prefix}{MEDIA}:443"
    log.write_text(f"{line} [tproxy-in -> old]\n", encoding="utf-8")

    class Connection:
        def getsockname(self):
            return ("127.0.0.1", 41000)

        def sendall(self, data):
            assert data.startswith(f"CONNECT {MEDIA}:443 ".encode())
            with log.open("a", encoding="utf-8") as stream:
                stream.write(f"{line.replace(':41000', ':41001')} [tproxy-in -> other]\n")
                stream.write(f"{line} [probe-in -> other]\n")
                stream.write(f"{line} [tproxy-in -> vpn-fixture]\n")

        def recv(self, _size):
            return b"HTTP/1.1 200 Connection established\r\n\r\n"

    @contextmanager
    def connect(_address, *, timeout):
        assert timeout == 2
        yield Connection()

    monkeypatch.setattr("docs.helpers.cdn_reload_xray_check.socket.create_connection", connect)
    assert observe_route(log, MEDIA, "vpn-fixture")


def test_live_snapshots_compare_reformatted_config_and_reject_routing_order_changes(
    tmp_path, monkeypatch,
):
    paths = Paths(root=tmp_path)
    path = paths.xray_config_file
    path.parent.mkdir(parents=True)
    config = {
        "outbounds": [{"protocol": "freedom", "tag": "xgw-zapret2"}],
        "metrics": {"listen": "127.0.0.1:2234"},
        "routing": {"rules": [
            {"outboundTag": "xgw-zapret2", "domain": ["domain:example.org"]},
            {"outboundTag": "proxy-a", "network": "tcp"},
        ]},
    }
    lock_held = False

    @contextmanager
    def lock(lock_path, **kwargs):
        nonlocal lock_held
        assert lock_path == paths.lock_file
        lock_held = True
        try:
            yield
        finally:
            lock_held = False

    stamps = iter((10, 20, 30))
    totals = iter((100, 300, 450))

    def fetch(_port, **kwargs):
        assert lock_held
        count = next(totals)
        return {"stats": {"outbound": {"xgw-zapret2": {"uplink": 10, "downlink": count}}}}

    monkeypatch.setattr(route_evidence, "file_lock", lock)
    monkeypatch.setattr(route_evidence, "_xray_epoch", lambda: "epoch")
    monkeypatch.setattr(route_evidence.metrics, "fetch_metrics", fetch)
    monkeypatch.setattr(route_evidence.time, "monotonic_ns", lambda: next(stamps))

    path.write_text(json.dumps(config), encoding="utf-8")
    first = route_evidence.snapshot(path, paths=paths)
    path.write_text(json.dumps(config, sort_keys=True, indent=4), encoding="utf-8")
    second = route_evidence.snapshot(path, paths=paths)
    result = route_evidence.deltas(first, second)
    assert result["config_bytes_changed"]
    assert result["groups"]["zapret2"]["downlink"] == 200

    legacy = {key: item for key, item in first.items() if key != "config_semantic_sha256"}
    with pytest.raises(route_evidence.EvidenceError, match="incomparable_snapshots") as error:
        route_evidence.deltas(legacy, second)
    assert error.value.field == "applied_config"

    config["routing"]["rules"].reverse()
    path.write_text(json.dumps(config), encoding="utf-8")
    third = route_evidence.snapshot(path, paths=paths)
    with pytest.raises(route_evidence.EvidenceError, match="incomparable_snapshots") as error:
        route_evidence.deltas(second, third)
    assert error.value.field == "applied_config"
    assert error.value.details() == {"field": "applied_config", "changed_sections": ["routing"]}


def test_config_comparison_groups_unrecognized_sections_without_exposing_values():
    before = snapshot(1, 10, 10, 10)
    after = snapshot(2, 20, 20, 20) | {"config_sha256": "different"}
    before["config_sections_sha256"] = route_evidence._section_hashes({"policy": {}})
    after["config_sections_sha256"] = route_evidence._section_hashes({
        "policy": {}, "private_extension": {"value": "private-secret"},
    })
    with pytest.raises(route_evidence.EvidenceError, match="incomparable_snapshots") as error:
        route_evidence.deltas(before, after)
    assert error.value.details() == {"field": "applied_config", "changed_sections": ["other"]}
    assert "private_extension" not in str(after) and "private-secret" not in str(after)


def test_snapshot_refuses_unconfirmed_live_api_state(tmp_path, monkeypatch):
    paths = Paths(root=tmp_path)
    paths.api_dirty_file.parent.mkdir(parents=True)
    paths.api_dirty_file.touch()

    @contextmanager
    def lock(*args, **kwargs):
        yield

    monkeypatch.setattr(route_evidence, "file_lock", lock)
    with pytest.raises(route_evidence.EvidenceError, match="xray_api_state_uncertain"):
        route_evidence.snapshot(paths.xray_config_file, paths=paths)


def test_config_write_matches_masked_journal_to_exact_disk_bytes(tmp_path):
    paths = Paths(root=tmp_path)
    stream = io.StringIO()
    logger = logging.Logger("xgw.apply")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(MaskingFormatter("%(name)s: %(message)s"))
    logger.addHandler(handler)
    applier = Applier(None, paths, None, None, logger=logger, validator=lambda _: (True, ""))
    boot = "e6debe06-8450-4f46-8065-6625a1f166b6"
    before = {"xray_epoch": f"{boot}:31:1", "config_sha256": "0" * 64,
              "monotonic_ns": time.monotonic_ns()}
    applier._write_current('{"secret": "test-private-value"}\n',
                           source=ApplySource.SINGBOX_GENERATION, method="api")
    after = before | {
        "config_sha256": hashlib.sha256(paths.xray_config_file.read_bytes()).hexdigest(),
        "monotonic_ns": time.monotonic_ns(),
    }
    message = stream.getvalue().strip()
    row = {"_BOOT_ID": boot.replace("-", ""), "_SYSTEMD_UNIT": "xgw.service",
           "_UID": "0", "MESSAGE": message}
    result = xray_config_writes.analyze(before, after, [row, row | {"_UID": "1000"}])
    assert result["state"] == "attributed" and result["writes"] == 1
    assert result["final_write"]["source"] == "singbox_generation"
    assert result["final_write"]["method"] == "api"
    assert "test-private-value" not in message and "fingerprint" not in str(result)
    assert xray_config_writes.analyze(before, after, [])["state"] == "unattributed"
    foreign = after | {"config_sha256": "2" * 64}
    assert xray_config_writes.analyze(before, foreign, [row])["state"] == "unattributed"
