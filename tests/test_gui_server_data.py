"""Read-only endpoint geography and numeric list order, without Qt or Linux calls."""
import importlib.util
import sys
from pathlib import Path

import pytest

from xgw import geodat
from xgw.watch import server_geo

spec = importlib.util.spec_from_file_location(
    "xgw_gui_catalog_test", Path(__file__).parents[1] / "vpn_ui/xgw/catalog.py")
catalog = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = catalog
spec.loader.exec_module(catalog)


def entry(identifier, speed, rating):
    return catalog.Entry(identifier, "sub:A", identifier, "", "", "member", False, True,
                         speed, None, rating=rating)


@pytest.mark.parametrize(("order", "descending", "expected"), [
    ("speed", True, ["b", "a", "c"]), ("speed", False, ["a", "b", "c"]),
    ("rating", True, ["a", "b", "c"]), ("rating", False, ["b", "a", "c"]),
    ("name", False, ["a", "b", "c"]), ("name", True, ["c", "b", "a"]),
])
def test_numeric_sort_both_directions_unknown_last(order, descending, expected):
    entries = [entry("c", None, None), entry("b", 100, 0.05), entry("a", 9, 0.9)]
    result = catalog.filtered(entries, "sub:A", "", "all", order, descending=descending)
    assert [item.id for item in result] == expected
    assert [item.id for item in entries] == ["c", "b", "a"]


def test_country_is_never_guessed_from_subscription_name():
    assert catalog._country({"name": "🇳🇱 NL Amsterdam", "country": "NL"}) == ""
    assert catalog._country({"name": "🇳🇱 NL Amsterdam", "endpoint_country": "jp"}) == "JP"


def test_country_requires_resolved_consistent_endpoint_ips():
    index = geodat.Countries({32: [(0, {int.from_bytes(bytes([8, 8, 8, 8]), "big"): "JP",
                                       int.from_bytes(bytes([1, 1, 1, 1]), "big"): "DE"})]})
    assert server_geo._country(index, ["server.example"], {}) == ""
    assert server_geo._country(index, ["server.example"], {"server.example": ["8.8.8.8"]}) == "JP"
    assert server_geo._country(index, ["server.example"],
                               {"server.example": ["8.8.8.8", "1.1.1.1"]}) == ""


def test_applied_country_uses_host_pins_and_never_exposes_address(tmp_path):
    from test_geodat import write_geoip

    from xgw.paths import Paths, atomic_write_json

    paths = Paths(root=tmp_path)
    paths.xray_dir.mkdir(parents=True, exist_ok=True)
    asset = write_geoip(paths.xray_dir / "geoip-ui.dat", {"JP": [("8.8.8.0", 24)]})
    atomic_write_json(paths.xray_config_file, {
        "dns": {"hosts": {"nl-server.example": ["8.8.8.8"]}},
        "outbounds": [{"tag": "proxy-nl-a", "settings": {
            "vnext": [{"address": "nl-server.example", "users": [{"id": "secret"}]}]}}],
    })
    geodat.countries(asset)
    assert server_geo.applied_countries(paths, {"proxy-nl-a"}) == {"proxy-nl-a": "JP"}
    paths.api_dirty_file.parent.mkdir(parents=True, exist_ok=True)
    paths.api_dirty_file.touch()
    assert server_geo.applied_countries(paths, {"proxy-nl-a"}) == {}
