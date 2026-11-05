"""Форматы и конечные размеры помощника G1; без сети и запуска служб."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_real_machine_helper_keeps_query_and_public_types(tmp_path):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "docs/helpers/singbox_generation_check.py"
    spec = importlib.util.spec_from_file_location("g1_helper", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assert helper.download_url("https://example.invalid/down?bytes=10000000&kind=test") == (
        "https://example.invalid/down?bytes=2097152&kind=test")
    assert helper.download_url("https://example.invalid/fixed") == "https://example.invalid/fixed"
    with pytest.raises(ValueError):
        helper.download_url("http://example.invalid/no-size")
    with pytest.raises(ValueError):
        helper.download_url("https://speed.cloudflare.com/__down?bytes=2097152")
    state = {"bytes": 2097152, "ok": True, "seconds": 128.0, "http": 200,
             "error": None, "receiving": object(), "done": object()}
    assert json.loads(json.dumps(helper.public_stream(state)))["bytes"] == 2097152
    helper.ROOT = tmp_path
    status = {"state": "DEGRADED", "daemon_down": False, "xray": {"ok": True},
              "capture": {"mode": "on", "blocked": False, "loaded": True}}
    helper.run = lambda argv: SimpleNamespace(returncode=0, stdout=(
        json.dumps(status) if argv[0] == "xgw" else "301"))
    assert helper.health() == 0
    status["capture"]["loaded"] = False
    assert helper.health() == 3
