import importlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def context(tmp_path):
    stand = Path(__file__).parents[1] / "tests/stand"

    def load(name):
        spec = importlib.util.spec_from_file_location("aj_narrow_" + name, stand / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    h, support = load("wave3_lifecycle_flow"), load("wave3_source_hooks")
    names = (
        "ownership",
        "ownership_adapters",
        "ownership_hooks",
        "ownership_entrypoints",
        "ownership_files",
        "ownership_completion",
        "paths",
        "config",
        "managed",
        "net.capture",
        "net.nft",
        "net.tun",
        "apply.applier",
        "apply.singbox",
        "xraycore.api",
        "actions",
        "engine",
    )
    support.MODULES = {n: importlib.import_module("xgw." + n) for n in names}
    h.SUPPORT, h.M = support, support.MODULES
    h.DETAILS = dict.fromkeys(h.DETAIL_KEYS)
    before = os.umask(0o077)
    try:
        yield h, support, tmp_path
    finally:
        os.umask(before)


@pytest.mark.parametrize(
    "variant",
    [
        "ENABLE_OK",
        "NETWORK_DHCP_ERROR",
        "PIN_OK",
        "POOL_MODE_ON_READY",
        "HOUSE_CHANGED",
        "PERSIST_CORE",
        "COLLECT_REMOTE",
        "APPLY_AUTO",
    ],
)
def test_representative_legacy_owned_effects(context, variant):
    h, support, root = context
    for i, mode in enumerate(("LEGACY", "OWNED")):
        case = root / str(i)
        case.mkdir(mode=0o700)
        h.DETAILS = dict.fromkeys(h.DETAIL_KEYS)
        h.matrix(support.Fixture(case), variant, mode)


@pytest.mark.parametrize(
    "name",
    [
        "B_ENABLE__UNBOUND",
        "F_API_PIN__FOREIGN",
        "D_APPLIER",
        "C_STARTED__RESTART",
        "I_FILES_OK",
        "I_FILES_BAD",
    ],
)
def test_selected_lifecycle_boundary_and_composite(context, name):
    h, support, root = context
    h.extra(support.Fixture(root), name)


def test_report_rejects_private_enum_and_freezes_partial_data(context, monkeypatch):
    h, support, root = context
    root.chmod(0o700)
    monkeypatch.setattr(h, "NOTES", root)
    support.create(root / "source-current.json", {"head": "a" * 40, "tree": "b" * 40})
    support.create(root / "manifest.json", {})
    details = dict.fromkeys(h.DETAIL_KEYS)
    details["observed_return"] = "PRIVATE_TOKEN"
    data = {
        "final": False,
        "completed": 1,
        "cases": [
            {
                "case": h.EXPECTED[0],
                "passed": False,
                "elapsed_ms": 17,
                "details": details,
                "reason": "PRIVATE_REASON",
            }
        ],
    }
    support.create(root / "progress.json", data)
    with pytest.raises(ValueError, match="RETURN_ENUM"):
        h.report()
    assert not (root / "report-data.md").exists()
    details["observed_return"] = "BLOCKED"
    (root / "progress.json").write_text(json.dumps(data))
    h.report()
    preview = (root / "report-data.md").read_bytes()
    assert b"PRIVATE_REASON" not in preview and b"PRIVATE_TOKEN" not in preview
    assert b'"expected_return":null' in preview
    (root / "progress.json").write_text("{}")
    h.report()
    assert (root / "report-data.md").read_bytes() == preview
