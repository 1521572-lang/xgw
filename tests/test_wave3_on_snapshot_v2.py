"""Regression for the real product's guard contract and safe failure details."""

import ast
import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "stand" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_product_render_priorities_pass_v2_and_reproduce_historical_X_rejection():
    module, old = load("wave3_on_snapshot_v2.py"), load("wave3_on_snapshot.py")
    tree = ast.parse((Path(__file__).parents[1] / "src/xgw/net/nft.py").read_text())
    render = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_guard"
    )
    metadata = {}
    for node in ast.walk(render):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_chain"
        ):
            name, definition = ast.literal_eval(node.args[0]), ast.literal_eval(node.args[1])
            if name in ("output", "forward"):
                match = re.search(r"hook (\w+) priority (-?\d+);", definition)
                assert match
                metadata[name] = match[1], int(match[2])
    assert metadata == {"output": ("postrouting", 10), "forward": ("forward", 10)}
    objects = module.synthetic_guard()
    for entry in objects:
        if "chain" in entry:
            chain = entry["chain"]
            chain["hook"], chain["prio"] = metadata[chain["name"]]
    assert module.guard_gate(objects)["forward_priority_expected"] is True
    with pytest.raises(old.Refuse, match="GUARD_LAYOUT"):
        old.guard_gate(objects)


def test_wrong_forward_priority_is_rejected_with_no_private_values_in_details():
    module = load("wave3_on_snapshot_v2.py")
    objects = module.synthetic_guard()
    objects[2]["chain"]["prio"] = 5
    objects.append({"rule": {"chain": "output", "expr": [{"match": {"secret": "PRIVATE_HOST"}}]}})
    with pytest.raises(module.Refuse, match="GUARD_LAYOUT") as caught:
        module.guard_gate(objects)
    details = caught.value.safe_details
    assert details["guard_observation"]["forward_priority_expected"] is False
    assert details["guard_observation"]["host_priority_expected"] is True
    assert details["guard_observation"]["host_drop_rules"] == 5
    assert "PRIVATE" not in json.dumps(details)


def test_failed_guard_keeps_diagnostics_and_dependent_phases_unavailable(tmp_path, monkeypatch):
    module = load("wave3_on_snapshot_v2.py")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "fixtures", lambda: {"passed": 6, "total": 6})
    bad = module.synthetic_guard()
    bad[2]["chain"]["prio"] = 5
    monkeypatch.setattr(module, "collect", lambda: module.guard_gate(copy.deepcopy(bad)))
    monkeypatch.setattr(module, "query", lambda *a: pytest.fail("no complete snapshot; no check"))
    module.worker()
    value = json.loads((tmp_path / "summary.json").read_text())
    assert value["marker"] == "ON_SNAPSHOT_V2_PARTIAL"
    assert len(value["phases"]) == 4
    phase = value["phases"]["Y2_private_snapshot"]
    assert phase["safe_details"]["guard_observation"]["forward_priority_expected"] is False
    assert value["phases"]["Y3_nft_check_only"]["reason"] == "NO_COMPLETE_SNAPSHOT"
    assert value["phases"]["Y4_after_stability"]["reason"] == "NO_BEFORE_SNAPSHOT"
    assert not (tmp_path / "manifest-private.json").exists()
    assert value["active_faults_authorized"] is False


def test_v2_start_dispatches_only_v2_worker_and_blocks_repeated_start(tmp_path, monkeypatch):
    module = load("wave3_on_snapshot_v2.py")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module, "secure_directory", lambda _: None)
    monkeypatch.setattr(module.sys, "argv", ["v2", "start"])
    starts = []
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda argv, **kwargs: starts.append((argv, kwargs))
    )
    assert module.main() == 0
    assert Path(starts[0][0][-2]).name == "wave3_on_snapshot_v2.py"
    assert starts[0][0][-1] == "_worker" and starts[0][1]["start_new_session"] is True
    with pytest.raises(module.Refuse, match="ALREADY_STARTED"):
        module.main()
    assert len(starts) == 1
