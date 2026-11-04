import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper(monkeypatch):
    path = Path(__file__).parent / "stand/wave3_resource_batch.py"
    spec = importlib.util.spec_from_file_location("ap_narrow", path)
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    modules = {
        n: importlib.import_module("xgw." + n)
        for n in (
            "ownership_resources",
            "ownership_resource_catalog",
            "ownership",
            "ownership_adapters",
        )
    }
    monkeypatch.setattr(h, "M", modules)
    monkeypatch.setattr(h, "SUPPORT", SimpleNamespace(BOOT="11111111-1111-1111-1111-111111111111"))
    monkeypatch.setattr(h, "DETAILS", dict.fromkeys(h.DETAIL_KEYS))
    return h


@pytest.mark.parametrize(
    "case",
    [
        "C_FILES_MATCH",
        "C_API_ACTUAL",
        "C_ROUTES_ABSENCE_BAD",
        "C_KERNEL_DUPLICATE",
        "A_MIXED",
        "A_OPTIONAL",
        "B_LIVE",
        "B_ACTUAL",
        "B_READY",
        "B_COUNTS_PARTIAL",
        "T_00",
        "I_MATCH",
        "I_CONSTRUCTOR_IO",
        "P_BOOL_REQUIRED",
        "P_SCHEMA_BOOL",
    ],
)
def test_resource_contract_branches(helper, tmp_path, case):
    helper.run_case(SimpleNamespace(root=tmp_path, work=tmp_path), case)


def test_partial_domain_results_are_retained(helper):
    r = helper.M["ownership_resources"]
    c = r.ResourceContract(
        helper.binding(),
        (
            r.ResourceRequirement("FILES", "item", "expected"),
            r.ResourceRequirement("API", "item", "expected"),
        ),
        "DECLARED_COMPLETE",
    )
    d = r.aggregate(c, (helper.observation("FILES"),))
    assert {row.domain: row.status for row in d.decisions} == {"API": "UNKNOWN", "FILES": "MATCH"}
    assert d.status == "UNKNOWN" and not d.runtime_completion_authorized
    facade = r.ResourceFacade(
        c, r.ObservationSet((helper.observation("FILES"),)), helper.inventory()
    )
    _, plan = facade.inspect()
    assert "DOMAIN_UNSUPPORTED" in plan.blockers and not plan.live_activation_authorized
