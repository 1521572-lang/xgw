"""AL: bounded wrapper/default/closure qualification; no product or live changes."""

import contextlib
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import FunctionType, SimpleNamespace

NOTES = Path.home() / "xgw-w3al"
AK_SHA = "927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55"
SLOTS_SHA = "ecfce37207db8aa9af503fcab6df749bf98707306a06eec2ab40fe93a0f35a72"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = "d83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13"
UNITS_SHA = "373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4"
SURFACE_SHA = "8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe"
LEGACY_SHA = "2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5"
LEGACY_COMMIT = "63c9c413930eb348d46b2ff986bef46dd2e423d4"
SLOTS = (
    ("actions.apply_network", 0, "CELL", "function", 0),
    ("actions.apply_network", 0, "CELL", "pinned", 1),
    ("actions.apply_network", 0, "CELL", "role", 2),
    ("actions.apply_network", 0, "CELL", "signature", 3),
    ("actions.apply_network", 1, "CODE", "", 0),
    ("actions.apply_network", 1, "CELL", "function", 0),
    ("actions.apply_network", 1, "CELL", "role", 1),
    ("actions.apply_network", 2, "CODE", "", 0),
    ("actions.apply_network", 2, "KW", "ownership", 0),
    ("actions.apply_network", 2, "KW", "runner", 0),
    ("actions.apply_network", 2, "KW_CODE", "runner", 0),
    ("actions.disable", 0, "CELL", "function", 0),
    ("actions.disable", 0, "CELL", "pinned", 1),
    ("actions.disable", 0, "CELL", "role", 2),
    ("actions.disable", 0, "CELL", "signature", 3),
    ("actions.disable", 1, "CODE", "", 0),
    ("actions.disable", 1, "CELL", "function", 0),
    ("actions.disable", 1, "CELL", "role", 1),
    ("actions.disable", 2, "CODE", "", 0),
    ("actions.disable", 2, "KW", "ownership", 0),
    ("actions.enable", 0, "CELL", "function", 0),
    ("actions.enable", 0, "CELL", "pinned", 1),
    ("actions.enable", 0, "CELL", "role", 2),
    ("actions.enable", 0, "CELL", "signature", 3),
    ("actions.enable", 1, "CODE", "", 0),
    ("actions.enable", 1, "CELL", "function", 0),
    ("actions.enable", 1, "CELL", "role", 1),
    ("actions.enable", 2, "CODE", "", 0),
    ("actions.enable", 2, "KW", "ownership", 0),
    ("actions.enable_checked", 0, "CELL", "function", 0),
    ("actions.enable_checked", 0, "CELL", "pinned", 1),
    ("actions.enable_checked", 0, "CELL", "role", 2),
    ("actions.enable_checked", 0, "CELL", "signature", 3),
    ("actions.enable_checked", 1, "CODE", "", 0),
    ("actions.enable_checked", 1, "CELL", "function", 0),
    ("actions.enable_checked", 1, "CELL", "role", 1),
    ("actions.enable_checked", 2, "CODE", "", 0),
    ("actions.enable_checked", 2, "KW", "ownership", 0),
    ("actions.house_after_boot", 0, "CELL", "function", 0),
    ("actions.house_after_boot", 0, "CELL", "pinned", 1),
    ("actions.house_after_boot", 0, "CELL", "role", 2),
    ("actions.house_after_boot", 0, "CELL", "signature", 3),
    ("actions.house_after_boot", 1, "CODE", "", 0),
    ("actions.house_after_boot", 1, "CELL", "function", 0),
    ("actions.house_after_boot", 1, "CELL", "role", 1),
    ("actions.house_after_boot", 2, "CODE", "", 0),
    ("actions.house_after_boot", 2, "KW", "ownership", 0),
    ("actions.pin", 0, "CELL", "function", 0),
    ("actions.pin", 0, "CELL", "pinned", 1),
    ("actions.pin", 0, "CELL", "role", 2),
    ("actions.pin", 0, "CELL", "signature", 3),
    ("actions.pin", 1, "CODE", "", 0),
    ("actions.pin", 1, "CELL", "function", 0),
    ("actions.pin", 1, "CELL", "role", 1),
    ("actions.pin", 2, "CODE", "", 0),
    ("actions.pin", 2, "KW", "ownership", 0),
    ("actions.set_core", 0, "CELL", "function", 0),
    ("actions.set_core", 0, "CELL", "pinned", 1),
    ("actions.set_core", 0, "CELL", "role", 2),
    ("actions.set_core", 0, "CELL", "signature", 3),
    ("actions.set_core", 1, "CODE", "", 0),
    ("actions.set_core", 1, "CELL", "function", 0),
    ("actions.set_core", 1, "CELL", "role", 1),
    ("actions.set_core", 2, "CODE", "", 0),
    ("actions.set_core", 2, "KW", "ownership", 0),
    ("actions.set_pool_mode", 0, "CELL", "function", 0),
    ("actions.set_pool_mode", 0, "CELL", "pinned", 1),
    ("actions.set_pool_mode", 0, "CELL", "role", 2),
    ("actions.set_pool_mode", 0, "CELL", "signature", 3),
    ("actions.set_pool_mode", 1, "CODE", "", 0),
    ("actions.set_pool_mode", 1, "CELL", "function", 0),
    ("actions.set_pool_mode", 1, "CELL", "role", 1),
    ("actions.set_pool_mode", 2, "CODE", "", 0),
    ("actions.set_pool_mode", 2, "KW", "ownership", 0),
    ("actions.set_pool_mode", 2, "KW", "ready", 0),
    ("actions.set_pool_mode", 2, "KW", "refuse_closing", 0),
    ("actions.set_pool_pin", 0, "CELL", "function", 0),
    ("actions.set_pool_pin", 0, "CELL", "pinned", 1),
    ("actions.set_pool_pin", 0, "CELL", "role", 2),
    ("actions.set_pool_pin", 0, "CELL", "signature", 3),
    ("actions.set_pool_pin", 1, "CODE", "", 0),
    ("actions.set_pool_pin", 1, "CELL", "function", 0),
    ("actions.set_pool_pin", 1, "CELL", "role", 1),
    ("actions.set_pool_pin", 2, "CODE", "", 0),
    ("actions.set_pool_pin", 2, "KW", "ownership", 0),
    ("actions.unpin", 0, "CELL", "function", 0),
    ("actions.unpin", 0, "CELL", "pinned", 1),
    ("actions.unpin", 0, "CELL", "role", 2),
    ("actions.unpin", 0, "CELL", "signature", 3),
    ("actions.unpin", 1, "CODE", "", 0),
    ("actions.unpin", 1, "CELL", "function", 0),
    ("actions.unpin", 1, "CELL", "role", 1),
    ("actions.unpin", 2, "CODE", "", 0),
    ("actions.unpin", 2, "KW", "ownership", 0),
    ("api.add_inbounds", 0, "CELL", "function", 0),
    ("api.add_inbounds", 0, "CELL", "role", 1),
    ("api.add_inbounds", 1, "CODE", "", 0),
    ("api.add_outbounds", 0, "CELL", "function", 0),
    ("api.add_outbounds", 0, "CELL", "role", 1),
    ("api.add_outbounds", 1, "CODE", "", 0),
    ("api.pin", 0, "CELL", "function", 0),
    ("api.pin", 0, "CELL", "role", 1),
    ("api.pin", 1, "CODE", "", 0),
    ("api.remove_inbound", 0, "CELL", "function", 0),
    ("api.remove_inbound", 0, "CELL", "role", 1),
    ("api.remove_inbound", 1, "CODE", "", 0),
    ("api.remove_outbound", 0, "CELL", "function", 0),
    ("api.remove_outbound", 0, "CELL", "role", 1),
    ("api.remove_outbound", 1, "CODE", "", 0),
    ("api.replace_routing", 0, "CELL", "function", 0),
    ("api.replace_routing", 0, "CELL", "role", 1),
    ("api.replace_routing", 1, "CODE", "", 0),
    ("api.replace_routing", 1, "KW", "append", 0),
    ("api.unpin", 0, "CELL", "function", 0),
    ("api.unpin", 0, "CELL", "role", 1),
    ("api.unpin", 1, "CODE", "", 0),
    ("capture._load", 0, "CELL", "function", 0),
    ("capture._load", 0, "CELL", "role", 1),
    ("capture._load", 1, "CODE", "", 0),
    ("capture._save", 0, "CELL", "function", 0),
    ("capture._save", 0, "CELL", "role", 1),
    ("capture._save", 1, "CODE", "", 0),
    ("capture.close", 0, "CELL", "function", 0),
    ("capture.close", 0, "CELL", "role", 1),
    ("capture.close", 1, "CODE", "", 0),
    ("capture.disable", 0, "CELL", "function", 0),
    ("capture.disable", 0, "CELL", "role", 1),
    ("capture.disable", 1, "CODE", "", 0),
    ("capture.down", 0, "CELL", "function", 0),
    ("capture.down", 0, "CELL", "role", 1),
    ("capture.down", 1, "CODE", "", 0),
    ("capture.down", 1, "KW", "remove_tun", 0),
    ("capture.enable", 0, "CELL", "function", 0),
    ("capture.enable", 0, "CELL", "role", 1),
    ("capture.enable", 1, "CODE", "", 0),
    ("capture.open", 0, "CELL", "function", 0),
    ("capture.open", 0, "CELL", "role", 1),
    ("capture.open", 1, "CODE", "", 0),
    ("capture.restore_tun", 0, "CELL", "function", 0),
    ("capture.restore_tun", 0, "CELL", "role", 1),
    ("capture.restore_tun", 1, "CODE", "", 0),
    ("capture.tailscale_direct", 0, "CELL", "function", 0),
    ("capture.tailscale_direct", 0, "CELL", "role", 1),
    ("capture.tailscale_direct", 1, "CODE", "", 0),
    ("capture.tailscale_fallback", 0, "CELL", "function", 0),
    ("capture.tailscale_fallback", 0, "CELL", "role", 1),
    ("capture.tailscale_fallback", 1, "CODE", "", 0),
    ("capture.tidy", 0, "CELL", "function", 0),
    ("capture.tidy", 0, "CELL", "role", 1),
    ("capture.tidy", 1, "CODE", "", 0),
    ("capture.up", 0, "CELL", "function", 0),
    ("capture.up", 0, "CELL", "role", 1),
    ("capture.up", 1, "CODE", "", 0),
    ("cores._event", 0, "CELL", "function", 0),
    ("cores._event", 0, "CELL", "role", 1),
    ("cores._event", 1, "CODE", "", 0),
    ("cores._reject", 0, "CELL", "function", 0),
    ("cores._reject", 0, "CELL", "role", 1),
    ("cores._reject", 1, "CODE", "", 0),
    ("cores._save", 0, "CELL", "function", 0),
    ("cores._save", 0, "CELL", "role", 1),
    ("cores._save", 1, "CODE", "", 0),
    ("cores._stage", 0, "CELL", "function", 0),
    ("cores._stage", 0, "CELL", "role", 1),
    ("cores._stage", 1, "CODE", "", 0),
    ("cores.rollback", 0, "CELL", "function", 0),
    ("cores.rollback", 0, "CELL", "role", 1),
    ("cores.rollback", 1, "CODE", "", 0),
    ("cores.run", 0, "CELL", "function", 0),
    ("cores.run", 0, "CELL", "role", 1),
    ("cores.run", 1, "CODE", "", 0),
    ("cores.run", 1, "POS", "version", 0),
    ("cores.run", 1, "POS", "reason", 1),
    ("cores.update", 0, "CELL", "function", 0),
    ("cores.update", 0, "CELL", "role", 1),
    ("cores.update", 1, "CODE", "", 0),
    ("engine._save_fingerprints", 0, "CELL", "function", 0),
    ("engine._save_fingerprints", 0, "CELL", "pinned", 1),
    ("engine._save_fingerprints", 0, "CELL", "role", 2),
    ("engine._save_fingerprints", 0, "CELL", "signature", 3),
    ("engine._save_fingerprints", 1, "CODE", "", 0),
    ("engine._save_fingerprints", 1, "CELL", "function", 0),
    ("engine._save_fingerprints", 1, "CELL", "role", 1),
    ("engine._save_fingerprints", 2, "CODE", "", 0),
    ("engine._save_fingerprints", 2, "KW", "ownership", 0),
    ("engine.apply_all", 0, "CELL", "function", 0),
    ("engine.apply_all", 0, "CELL", "pinned", 1),
    ("engine.apply_all", 0, "CELL", "role", 2),
    ("engine.apply_all", 0, "CELL", "signature", 3),
    ("engine.apply_all", 1, "CODE", "", 0),
    ("engine.apply_all", 1, "CELL", "function", 0),
    ("engine.apply_all", 1, "CELL", "role", 1),
    ("engine.apply_all", 2, "CODE", "", 0),
    ("engine.apply_all", 2, "KW", "force_now", 0),
    ("engine.apply_all", 2, "KW", "ownership", 0),
    ("engine.apply_all", 2, "KW", "singbox_core", 0),
    ("engine.collect", 0, "CELL", "function", 0),
    ("engine.collect", 0, "CELL", "pinned", 1),
    ("engine.collect", 0, "CELL", "role", 2),
    ("engine.collect", 0, "CELL", "signature", 3),
    ("engine.collect", 1, "CODE", "", 0),
    ("engine.collect", 1, "CELL", "function", 0),
    ("engine.collect", 1, "CELL", "role", 1),
    ("engine.collect", 2, "CODE", "", 0),
    ("engine.collect", 2, "KW", "cancel", 0),
    ("engine.collect", 2, "KW", "ownership", 0),
    ("engine.collect", 2, "KW", "via_xray", 0),
    ("engine.persist", 0, "CELL", "function", 0),
    ("engine.persist", 0, "CELL", "pinned", 1),
    ("engine.persist", 0, "CELL", "role", 2),
    ("engine.persist", 0, "CELL", "signature", 3),
    ("engine.persist", 1, "CODE", "", 0),
    ("engine.persist", 1, "CELL", "function", 0),
    ("engine.persist", 1, "CELL", "role", 1),
    ("engine.persist", 2, "CODE", "", 0),
    ("engine.persist", 2, "KW", "applied", 0),
    ("engine.persist", 2, "KW", "ownership", 0),
    ("engine.persist", 2, "KW", "record_event", 0),
    ("engine.save_inventory", 0, "CELL", "function", 0),
    ("engine.save_inventory", 0, "CELL", "pinned", 1),
    ("engine.save_inventory", 0, "CELL", "role", 2),
    ("engine.save_inventory", 0, "CELL", "signature", 3),
    ("engine.save_inventory", 1, "CODE", "", 0),
    ("engine.save_inventory", 1, "CELL", "function", 0),
    ("engine.save_inventory", 1, "CELL", "role", 1),
    ("engine.save_inventory", 2, "CODE", "", 0),
    ("engine.save_inventory", 2, "KW", "ownership", 0),
    ("panel.update", 0, "CELL", "function", 0),
    ("panel.update", 0, "CELL", "role", 1),
    ("panel.update", 1, "CODE", "", 0),
    ("peers._nft_element", 0, "CELL", "function", 0),
    ("peers._nft_element", 0, "CELL", "role", 1),
    ("peers._nft_element", 1, "CODE", "", 0),
    ("peers._save_peers", 0, "CELL", "function", 0),
    ("peers._save_peers", 0, "CELL", "role", 1),
    ("peers._save_peers", 1, "CODE", "", 0),
    ("peers.prepare", 0, "CELL", "function", 0),
    ("peers.prepare", 0, "CELL", "role", 1),
    ("peers.prepare", 1, "CODE", "", 0),
    ("peers.prepare", 1, "KW", "sstpc_bin", 0),
    ("peers.reconcile", 0, "CELL", "function", 0),
    ("peers.reconcile", 0, "CELL", "role", 1),
    ("peers.reconcile", 1, "CODE", "", 0),
    ("peers.stop", 0, "CELL", "function", 0),
    ("peers.stop", 0, "CELL", "role", 1),
    ("peers.stop", 1, "CODE", "", 0),
    ("pool._check_proxy", 0, "CELL", "function", 0),
    ("pool._check_proxy", 0, "CELL", "role", 1),
    ("pool._check_proxy", 1, "CODE", "", 0),
    ("pool._note_handshake", 0, "CELL", "function", 0),
    ("pool._note_handshake", 0, "CELL", "role", 1),
    ("pool._note_handshake", 1, "CODE", "", 0),
    ("pool._prune_candidates", 0, "CELL", "function", 0),
    ("pool._prune_candidates", 0, "CELL", "role", 1),
    ("pool._prune_candidates", 1, "CODE", "", 0),
    ("pool._prune_retired", 0, "CELL", "function", 0),
    ("pool._prune_retired", 0, "CELL", "role", 1),
    ("pool._prune_retired", 1, "CODE", "", 0),
    ("pool._record", 0, "CELL", "function", 0),
    ("pool._record", 0, "CELL", "role", 1),
    ("pool._record", 1, "CODE", "", 0),
    ("pool._record", 1, "KW", "tunnel", 0),
    ("pool.check_some", 0, "CELL", "function", 0),
    ("pool.check_some", 0, "CELL", "role", 1),
    ("pool.check_some", 1, "CODE", "", 0),
    ("pool.check_some", 1, "KW", "cancel", 0),
    ("pool.check_some", 1, "KW", "via", 0),
    ("pool.refresh_backend", 0, "CELL", "function", 0),
    ("pool.refresh_backend", 0, "CELL", "role", 1),
    ("pool.refresh_backend", 1, "CODE", "", 0),
    ("pool.refresh_due", 0, "CELL", "function", 0),
    ("pool.refresh_due", 0, "CELL", "role", 1),
    ("pool.refresh_due", 1, "CODE", "", 0),
    ("pool.refresh_due", 1, "KW", "force", 0),
    ("pool_store._ensure", 0, "CELL", "function", 0),
    ("pool_store._ensure", 0, "CELL", "role", 1),
    ("pool_store._ensure", 1, "CODE", "", 0),
    ("pool_store.commit", 0, "CELL", "function", 0),
    ("pool_store.commit", 0, "CELL", "role", 1),
    ("pool_store.commit", 1, "CODE", "", 0),
    ("pool_store.prune", 0, "CELL", "function", 0),
    ("pool_store.prune", 0, "CELL", "role", 1),
    ("pool_store.prune", 1, "CODE", "", 0),
    ("pool_store.retire_openvpn", 0, "CELL", "function", 0),
    ("pool_store.retire_openvpn", 0, "CELL", "role", 1),
    ("pool_store.retire_openvpn", 1, "CODE", "", 0),
    ("pool_store.save_candidates", 0, "CELL", "function", 0),
    ("pool_store.save_candidates", 0, "CELL", "role", 1),
    ("pool_store.save_candidates", 1, "CODE", "", 0),
    ("singbox.apply", 0, "CELL", "function", 0),
    ("singbox.apply", 0, "CELL", "role", 1),
    ("singbox.apply", 1, "CODE", "", 0),
    ("singbox.restart", 0, "CELL", "function", 0),
    ("singbox.restart", 0, "CELL", "role", 1),
    ("singbox.restart", 1, "CODE", "", 0),
    ("singbox.rollback", 0, "CELL", "function", 0),
    ("singbox.rollback", 0, "CELL", "role", 1),
    ("singbox.rollback", 1, "CODE", "", 0),
    ("xray.apply", 0, "CELL", "function", 0),
    ("xray.apply", 0, "CELL", "role", 1),
    ("xray.apply", 1, "CODE", "", 0),
    ("xray.apply", 1, "KW", "force_now", 0),
    ("xray.apply", 1, "KW", "urgent", 0),
    ("xray.rollback", 0, "CELL", "function", 0),
    ("xray.rollback", 0, "CELL", "role", 1),
    ("xray.rollback", 1, "CODE", "", 0),
)
EXPECTED = (
    "REPAIR_H_DEFAULT__CATALOG",
    "REPAIR_H_DEFAULT__PREFLIGHT",
    "REPAIR_H_DEFAULT_CODE__CATALOG",
    "REPAIR_H_DEFAULT_CODE__PREFLIGHT",
    "SLOT_000_DRIFT__CATALOG",
    "SLOT_000_DRIFT__PREFLIGHT",
    "SLOT_001_DRIFT__CATALOG",
    "SLOT_001_DRIFT__PREFLIGHT",
    "SLOT_002_DRIFT__CATALOG",
    "SLOT_002_DRIFT__PREFLIGHT",
    "SLOT_003_DRIFT__CATALOG",
    "SLOT_003_DRIFT__PREFLIGHT",
    "SLOT_004_DRIFT__CATALOG",
    "SLOT_004_DRIFT__PREFLIGHT",
    "SLOT_005_DRIFT__CATALOG",
    "SLOT_005_DRIFT__PREFLIGHT",
    "SLOT_006_DRIFT__CATALOG",
    "SLOT_006_DRIFT__PREFLIGHT",
    "SLOT_007_DRIFT__CATALOG",
    "SLOT_007_DRIFT__PREFLIGHT",
    "SLOT_008_LITERAL__CATALOG",
    "SLOT_008_LITERAL__PREFLIGHT",
    "SLOT_008_REMOVE__CATALOG",
    "SLOT_008_REMOVE__PREFLIGHT",
    "SLOT_008_OPAQUE__CATALOG",
    "SLOT_008_OPAQUE__PREFLIGHT",
    "SLOT_009_LITERAL__CATALOG",
    "SLOT_009_LITERAL__PREFLIGHT",
    "SLOT_009_REMOVE__CATALOG",
    "SLOT_009_REMOVE__PREFLIGHT",
    "SLOT_009_OPAQUE__CATALOG",
    "SLOT_009_OPAQUE__PREFLIGHT",
    "SLOT_010_DRIFT__CATALOG",
    "SLOT_010_DRIFT__PREFLIGHT",
    "SLOT_011_DRIFT__CATALOG",
    "SLOT_011_DRIFT__PREFLIGHT",
    "SLOT_012_DRIFT__CATALOG",
    "SLOT_012_DRIFT__PREFLIGHT",
    "SLOT_013_DRIFT__CATALOG",
    "SLOT_013_DRIFT__PREFLIGHT",
    "SLOT_014_DRIFT__CATALOG",
    "SLOT_014_DRIFT__PREFLIGHT",
    "SLOT_015_DRIFT__CATALOG",
    "SLOT_015_DRIFT__PREFLIGHT",
    "SLOT_016_DRIFT__CATALOG",
    "SLOT_016_DRIFT__PREFLIGHT",
    "SLOT_017_DRIFT__CATALOG",
    "SLOT_017_DRIFT__PREFLIGHT",
    "SLOT_018_DRIFT__CATALOG",
    "SLOT_018_DRIFT__PREFLIGHT",
    "SLOT_019_LITERAL__CATALOG",
    "SLOT_019_LITERAL__PREFLIGHT",
    "SLOT_019_REMOVE__CATALOG",
    "SLOT_019_REMOVE__PREFLIGHT",
    "SLOT_019_OPAQUE__CATALOG",
    "SLOT_019_OPAQUE__PREFLIGHT",
    "SLOT_020_DRIFT__CATALOG",
    "SLOT_020_DRIFT__PREFLIGHT",
    "SLOT_021_DRIFT__CATALOG",
    "SLOT_021_DRIFT__PREFLIGHT",
    "SLOT_022_DRIFT__CATALOG",
    "SLOT_022_DRIFT__PREFLIGHT",
    "SLOT_023_DRIFT__CATALOG",
    "SLOT_023_DRIFT__PREFLIGHT",
    "SLOT_024_DRIFT__CATALOG",
    "SLOT_024_DRIFT__PREFLIGHT",
    "SLOT_025_DRIFT__CATALOG",
    "SLOT_025_DRIFT__PREFLIGHT",
    "SLOT_026_DRIFT__CATALOG",
    "SLOT_026_DRIFT__PREFLIGHT",
    "SLOT_027_DRIFT__CATALOG",
    "SLOT_027_DRIFT__PREFLIGHT",
    "SLOT_028_LITERAL__CATALOG",
    "SLOT_028_LITERAL__PREFLIGHT",
    "SLOT_028_REMOVE__CATALOG",
    "SLOT_028_REMOVE__PREFLIGHT",
    "SLOT_028_OPAQUE__CATALOG",
    "SLOT_028_OPAQUE__PREFLIGHT",
    "SLOT_029_DRIFT__CATALOG",
    "SLOT_029_DRIFT__PREFLIGHT",
    "SLOT_030_DRIFT__CATALOG",
    "SLOT_030_DRIFT__PREFLIGHT",
    "SLOT_031_DRIFT__CATALOG",
    "SLOT_031_DRIFT__PREFLIGHT",
    "SLOT_032_DRIFT__CATALOG",
    "SLOT_032_DRIFT__PREFLIGHT",
    "SLOT_033_DRIFT__CATALOG",
    "SLOT_033_DRIFT__PREFLIGHT",
    "SLOT_034_DRIFT__CATALOG",
    "SLOT_034_DRIFT__PREFLIGHT",
    "SLOT_035_DRIFT__CATALOG",
    "SLOT_035_DRIFT__PREFLIGHT",
    "SLOT_036_DRIFT__CATALOG",
    "SLOT_036_DRIFT__PREFLIGHT",
    "SLOT_037_LITERAL__CATALOG",
    "SLOT_037_LITERAL__PREFLIGHT",
    "SLOT_037_REMOVE__CATALOG",
    "SLOT_037_REMOVE__PREFLIGHT",
    "SLOT_037_OPAQUE__CATALOG",
    "SLOT_037_OPAQUE__PREFLIGHT",
    "SLOT_038_DRIFT__CATALOG",
    "SLOT_038_DRIFT__PREFLIGHT",
    "SLOT_039_DRIFT__CATALOG",
    "SLOT_039_DRIFT__PREFLIGHT",
    "SLOT_040_DRIFT__CATALOG",
    "SLOT_040_DRIFT__PREFLIGHT",
    "SLOT_041_DRIFT__CATALOG",
    "SLOT_041_DRIFT__PREFLIGHT",
    "SLOT_042_DRIFT__CATALOG",
    "SLOT_042_DRIFT__PREFLIGHT",
    "SLOT_043_DRIFT__CATALOG",
    "SLOT_043_DRIFT__PREFLIGHT",
    "SLOT_044_DRIFT__CATALOG",
    "SLOT_044_DRIFT__PREFLIGHT",
    "SLOT_045_DRIFT__CATALOG",
    "SLOT_045_DRIFT__PREFLIGHT",
    "SLOT_046_LITERAL__CATALOG",
    "SLOT_046_LITERAL__PREFLIGHT",
    "SLOT_046_REMOVE__CATALOG",
    "SLOT_046_REMOVE__PREFLIGHT",
    "SLOT_046_OPAQUE__CATALOG",
    "SLOT_046_OPAQUE__PREFLIGHT",
    "SLOT_047_DRIFT__CATALOG",
    "SLOT_047_DRIFT__PREFLIGHT",
    "SLOT_048_DRIFT__CATALOG",
    "SLOT_048_DRIFT__PREFLIGHT",
    "SLOT_049_DRIFT__CATALOG",
    "SLOT_049_DRIFT__PREFLIGHT",
    "SLOT_050_DRIFT__CATALOG",
    "SLOT_050_DRIFT__PREFLIGHT",
    "SLOT_051_DRIFT__CATALOG",
    "SLOT_051_DRIFT__PREFLIGHT",
    "SLOT_052_DRIFT__CATALOG",
    "SLOT_052_DRIFT__PREFLIGHT",
    "SLOT_053_DRIFT__CATALOG",
    "SLOT_053_DRIFT__PREFLIGHT",
    "SLOT_054_DRIFT__CATALOG",
    "SLOT_054_DRIFT__PREFLIGHT",
    "SLOT_055_LITERAL__CATALOG",
    "SLOT_055_LITERAL__PREFLIGHT",
    "SLOT_055_REMOVE__CATALOG",
    "SLOT_055_REMOVE__PREFLIGHT",
    "SLOT_055_OPAQUE__CATALOG",
    "SLOT_055_OPAQUE__PREFLIGHT",
    "SLOT_056_DRIFT__CATALOG",
    "SLOT_056_DRIFT__PREFLIGHT",
    "SLOT_057_DRIFT__CATALOG",
    "SLOT_057_DRIFT__PREFLIGHT",
    "SLOT_058_DRIFT__CATALOG",
    "SLOT_058_DRIFT__PREFLIGHT",
    "SLOT_059_DRIFT__CATALOG",
    "SLOT_059_DRIFT__PREFLIGHT",
    "SLOT_060_DRIFT__CATALOG",
    "SLOT_060_DRIFT__PREFLIGHT",
    "SLOT_061_DRIFT__CATALOG",
    "SLOT_061_DRIFT__PREFLIGHT",
    "SLOT_062_DRIFT__CATALOG",
    "SLOT_062_DRIFT__PREFLIGHT",
    "SLOT_063_DRIFT__CATALOG",
    "SLOT_063_DRIFT__PREFLIGHT",
    "SLOT_064_LITERAL__CATALOG",
    "SLOT_064_LITERAL__PREFLIGHT",
    "SLOT_064_REMOVE__CATALOG",
    "SLOT_064_REMOVE__PREFLIGHT",
    "SLOT_064_OPAQUE__CATALOG",
    "SLOT_064_OPAQUE__PREFLIGHT",
    "SLOT_065_DRIFT__CATALOG",
    "SLOT_065_DRIFT__PREFLIGHT",
    "SLOT_066_DRIFT__CATALOG",
    "SLOT_066_DRIFT__PREFLIGHT",
    "SLOT_067_DRIFT__CATALOG",
    "SLOT_067_DRIFT__PREFLIGHT",
    "SLOT_068_DRIFT__CATALOG",
    "SLOT_068_DRIFT__PREFLIGHT",
    "SLOT_069_DRIFT__CATALOG",
    "SLOT_069_DRIFT__PREFLIGHT",
    "SLOT_070_DRIFT__CATALOG",
    "SLOT_070_DRIFT__PREFLIGHT",
    "SLOT_071_DRIFT__CATALOG",
    "SLOT_071_DRIFT__PREFLIGHT",
    "SLOT_072_DRIFT__CATALOG",
    "SLOT_072_DRIFT__PREFLIGHT",
    "SLOT_073_LITERAL__CATALOG",
    "SLOT_073_LITERAL__PREFLIGHT",
    "SLOT_073_REMOVE__CATALOG",
    "SLOT_073_REMOVE__PREFLIGHT",
    "SLOT_073_OPAQUE__CATALOG",
    "SLOT_073_OPAQUE__PREFLIGHT",
    "SLOT_074_LITERAL__CATALOG",
    "SLOT_074_LITERAL__PREFLIGHT",
    "SLOT_074_REMOVE__CATALOG",
    "SLOT_074_REMOVE__PREFLIGHT",
    "SLOT_074_OPAQUE__CATALOG",
    "SLOT_074_OPAQUE__PREFLIGHT",
    "SLOT_075_LITERAL__CATALOG",
    "SLOT_075_LITERAL__PREFLIGHT",
    "SLOT_075_REMOVE__CATALOG",
    "SLOT_075_REMOVE__PREFLIGHT",
    "SLOT_075_OPAQUE__CATALOG",
    "SLOT_075_OPAQUE__PREFLIGHT",
    "SLOT_076_DRIFT__CATALOG",
    "SLOT_076_DRIFT__PREFLIGHT",
    "SLOT_077_DRIFT__CATALOG",
    "SLOT_077_DRIFT__PREFLIGHT",
    "SLOT_078_DRIFT__CATALOG",
    "SLOT_078_DRIFT__PREFLIGHT",
    "SLOT_079_DRIFT__CATALOG",
    "SLOT_079_DRIFT__PREFLIGHT",
    "SLOT_080_DRIFT__CATALOG",
    "SLOT_080_DRIFT__PREFLIGHT",
    "SLOT_081_DRIFT__CATALOG",
    "SLOT_081_DRIFT__PREFLIGHT",
    "SLOT_082_DRIFT__CATALOG",
    "SLOT_082_DRIFT__PREFLIGHT",
    "SLOT_083_DRIFT__CATALOG",
    "SLOT_083_DRIFT__PREFLIGHT",
    "SLOT_084_LITERAL__CATALOG",
    "SLOT_084_LITERAL__PREFLIGHT",
    "SLOT_084_REMOVE__CATALOG",
    "SLOT_084_REMOVE__PREFLIGHT",
    "SLOT_084_OPAQUE__CATALOG",
    "SLOT_084_OPAQUE__PREFLIGHT",
    "SLOT_085_DRIFT__CATALOG",
    "SLOT_085_DRIFT__PREFLIGHT",
    "SLOT_086_DRIFT__CATALOG",
    "SLOT_086_DRIFT__PREFLIGHT",
    "SLOT_087_DRIFT__CATALOG",
    "SLOT_087_DRIFT__PREFLIGHT",
    "SLOT_088_DRIFT__CATALOG",
    "SLOT_088_DRIFT__PREFLIGHT",
    "SLOT_089_DRIFT__CATALOG",
    "SLOT_089_DRIFT__PREFLIGHT",
    "SLOT_090_DRIFT__CATALOG",
    "SLOT_090_DRIFT__PREFLIGHT",
    "SLOT_091_DRIFT__CATALOG",
    "SLOT_091_DRIFT__PREFLIGHT",
    "SLOT_092_DRIFT__CATALOG",
    "SLOT_092_DRIFT__PREFLIGHT",
    "SLOT_093_LITERAL__CATALOG",
    "SLOT_093_LITERAL__PREFLIGHT",
    "SLOT_093_REMOVE__CATALOG",
    "SLOT_093_REMOVE__PREFLIGHT",
    "SLOT_093_OPAQUE__CATALOG",
    "SLOT_093_OPAQUE__PREFLIGHT",
    "SLOT_094_DRIFT__CATALOG",
    "SLOT_094_DRIFT__PREFLIGHT",
    "SLOT_095_DRIFT__CATALOG",
    "SLOT_095_DRIFT__PREFLIGHT",
    "SLOT_096_DRIFT__CATALOG",
    "SLOT_096_DRIFT__PREFLIGHT",
    "SLOT_097_DRIFT__CATALOG",
    "SLOT_097_DRIFT__PREFLIGHT",
    "SLOT_098_DRIFT__CATALOG",
    "SLOT_098_DRIFT__PREFLIGHT",
    "SLOT_099_DRIFT__CATALOG",
    "SLOT_099_DRIFT__PREFLIGHT",
    "SLOT_100_DRIFT__CATALOG",
    "SLOT_100_DRIFT__PREFLIGHT",
    "SLOT_101_DRIFT__CATALOG",
    "SLOT_101_DRIFT__PREFLIGHT",
    "SLOT_102_DRIFT__CATALOG",
    "SLOT_102_DRIFT__PREFLIGHT",
    "SLOT_103_DRIFT__CATALOG",
    "SLOT_103_DRIFT__PREFLIGHT",
    "SLOT_104_DRIFT__CATALOG",
    "SLOT_104_DRIFT__PREFLIGHT",
    "SLOT_105_DRIFT__CATALOG",
    "SLOT_105_DRIFT__PREFLIGHT",
    "SLOT_106_DRIFT__CATALOG",
    "SLOT_106_DRIFT__PREFLIGHT",
    "SLOT_107_DRIFT__CATALOG",
    "SLOT_107_DRIFT__PREFLIGHT",
    "SLOT_108_DRIFT__CATALOG",
    "SLOT_108_DRIFT__PREFLIGHT",
    "SLOT_109_DRIFT__CATALOG",
    "SLOT_109_DRIFT__PREFLIGHT",
    "SLOT_110_DRIFT__CATALOG",
    "SLOT_110_DRIFT__PREFLIGHT",
    "SLOT_111_DRIFT__CATALOG",
    "SLOT_111_DRIFT__PREFLIGHT",
    "SLOT_112_LITERAL__CATALOG",
    "SLOT_112_LITERAL__PREFLIGHT",
    "SLOT_112_REMOVE__CATALOG",
    "SLOT_112_REMOVE__PREFLIGHT",
    "SLOT_112_OPAQUE__CATALOG",
    "SLOT_112_OPAQUE__PREFLIGHT",
    "SLOT_113_DRIFT__CATALOG",
    "SLOT_113_DRIFT__PREFLIGHT",
    "SLOT_114_DRIFT__CATALOG",
    "SLOT_114_DRIFT__PREFLIGHT",
    "SLOT_115_DRIFT__CATALOG",
    "SLOT_115_DRIFT__PREFLIGHT",
    "SLOT_116_DRIFT__CATALOG",
    "SLOT_116_DRIFT__PREFLIGHT",
    "SLOT_117_DRIFT__CATALOG",
    "SLOT_117_DRIFT__PREFLIGHT",
    "SLOT_118_DRIFT__CATALOG",
    "SLOT_118_DRIFT__PREFLIGHT",
    "SLOT_119_DRIFT__CATALOG",
    "SLOT_119_DRIFT__PREFLIGHT",
    "SLOT_120_DRIFT__CATALOG",
    "SLOT_120_DRIFT__PREFLIGHT",
    "SLOT_121_DRIFT__CATALOG",
    "SLOT_121_DRIFT__PREFLIGHT",
    "SLOT_122_DRIFT__CATALOG",
    "SLOT_122_DRIFT__PREFLIGHT",
    "SLOT_123_DRIFT__CATALOG",
    "SLOT_123_DRIFT__PREFLIGHT",
    "SLOT_124_DRIFT__CATALOG",
    "SLOT_124_DRIFT__PREFLIGHT",
    "SLOT_125_DRIFT__CATALOG",
    "SLOT_125_DRIFT__PREFLIGHT",
    "SLOT_126_DRIFT__CATALOG",
    "SLOT_126_DRIFT__PREFLIGHT",
    "SLOT_127_DRIFT__CATALOG",
    "SLOT_127_DRIFT__PREFLIGHT",
    "SLOT_128_DRIFT__CATALOG",
    "SLOT_128_DRIFT__PREFLIGHT",
    "SLOT_129_DRIFT__CATALOG",
    "SLOT_129_DRIFT__PREFLIGHT",
    "SLOT_130_DRIFT__CATALOG",
    "SLOT_130_DRIFT__PREFLIGHT",
    "SLOT_131_LITERAL__CATALOG",
    "SLOT_131_LITERAL__PREFLIGHT",
    "SLOT_131_REMOVE__CATALOG",
    "SLOT_131_REMOVE__PREFLIGHT",
    "SLOT_131_OPAQUE__CATALOG",
    "SLOT_131_OPAQUE__PREFLIGHT",
    "SLOT_132_DRIFT__CATALOG",
    "SLOT_132_DRIFT__PREFLIGHT",
    "SLOT_133_DRIFT__CATALOG",
    "SLOT_133_DRIFT__PREFLIGHT",
    "SLOT_134_DRIFT__CATALOG",
    "SLOT_134_DRIFT__PREFLIGHT",
    "SLOT_135_DRIFT__CATALOG",
    "SLOT_135_DRIFT__PREFLIGHT",
    "SLOT_136_DRIFT__CATALOG",
    "SLOT_136_DRIFT__PREFLIGHT",
    "SLOT_137_DRIFT__CATALOG",
    "SLOT_137_DRIFT__PREFLIGHT",
    "SLOT_138_DRIFT__CATALOG",
    "SLOT_138_DRIFT__PREFLIGHT",
    "SLOT_139_DRIFT__CATALOG",
    "SLOT_139_DRIFT__PREFLIGHT",
    "SLOT_140_DRIFT__CATALOG",
    "SLOT_140_DRIFT__PREFLIGHT",
    "SLOT_141_DRIFT__CATALOG",
    "SLOT_141_DRIFT__PREFLIGHT",
    "SLOT_142_DRIFT__CATALOG",
    "SLOT_142_DRIFT__PREFLIGHT",
    "SLOT_143_DRIFT__CATALOG",
    "SLOT_143_DRIFT__PREFLIGHT",
    "SLOT_144_DRIFT__CATALOG",
    "SLOT_144_DRIFT__PREFLIGHT",
    "SLOT_145_DRIFT__CATALOG",
    "SLOT_145_DRIFT__PREFLIGHT",
    "SLOT_146_DRIFT__CATALOG",
    "SLOT_146_DRIFT__PREFLIGHT",
    "SLOT_147_DRIFT__CATALOG",
    "SLOT_147_DRIFT__PREFLIGHT",
    "SLOT_148_DRIFT__CATALOG",
    "SLOT_148_DRIFT__PREFLIGHT",
    "SLOT_149_DRIFT__CATALOG",
    "SLOT_149_DRIFT__PREFLIGHT",
    "SLOT_150_DRIFT__CATALOG",
    "SLOT_150_DRIFT__PREFLIGHT",
    "SLOT_151_DRIFT__CATALOG",
    "SLOT_151_DRIFT__PREFLIGHT",
    "SLOT_152_DRIFT__CATALOG",
    "SLOT_152_DRIFT__PREFLIGHT",
    "SLOT_153_DRIFT__CATALOG",
    "SLOT_153_DRIFT__PREFLIGHT",
    "SLOT_154_DRIFT__CATALOG",
    "SLOT_154_DRIFT__PREFLIGHT",
    "SLOT_155_DRIFT__CATALOG",
    "SLOT_155_DRIFT__PREFLIGHT",
    "SLOT_156_DRIFT__CATALOG",
    "SLOT_156_DRIFT__PREFLIGHT",
    "SLOT_157_DRIFT__CATALOG",
    "SLOT_157_DRIFT__PREFLIGHT",
    "SLOT_158_DRIFT__CATALOG",
    "SLOT_158_DRIFT__PREFLIGHT",
    "SLOT_159_DRIFT__CATALOG",
    "SLOT_159_DRIFT__PREFLIGHT",
    "SLOT_160_DRIFT__CATALOG",
    "SLOT_160_DRIFT__PREFLIGHT",
    "SLOT_161_DRIFT__CATALOG",
    "SLOT_161_DRIFT__PREFLIGHT",
    "SLOT_162_DRIFT__CATALOG",
    "SLOT_162_DRIFT__PREFLIGHT",
    "SLOT_163_DRIFT__CATALOG",
    "SLOT_163_DRIFT__PREFLIGHT",
    "SLOT_164_DRIFT__CATALOG",
    "SLOT_164_DRIFT__PREFLIGHT",
    "SLOT_165_DRIFT__CATALOG",
    "SLOT_165_DRIFT__PREFLIGHT",
    "SLOT_166_DRIFT__CATALOG",
    "SLOT_166_DRIFT__PREFLIGHT",
    "SLOT_167_DRIFT__CATALOG",
    "SLOT_167_DRIFT__PREFLIGHT",
    "SLOT_168_DRIFT__CATALOG",
    "SLOT_168_DRIFT__PREFLIGHT",
    "SLOT_169_DRIFT__CATALOG",
    "SLOT_169_DRIFT__PREFLIGHT",
    "SLOT_170_DRIFT__CATALOG",
    "SLOT_170_DRIFT__PREFLIGHT",
    "SLOT_171_LITERAL__CATALOG",
    "SLOT_171_LITERAL__PREFLIGHT",
    "SLOT_171_REMOVE__CATALOG",
    "SLOT_171_REMOVE__PREFLIGHT",
    "SLOT_171_OPAQUE__CATALOG",
    "SLOT_171_OPAQUE__PREFLIGHT",
    "SLOT_172_LITERAL__CATALOG",
    "SLOT_172_LITERAL__PREFLIGHT",
    "SLOT_172_REMOVE__CATALOG",
    "SLOT_172_REMOVE__PREFLIGHT",
    "SLOT_172_OPAQUE__CATALOG",
    "SLOT_172_OPAQUE__PREFLIGHT",
    "SLOT_173_DRIFT__CATALOG",
    "SLOT_173_DRIFT__PREFLIGHT",
    "SLOT_174_DRIFT__CATALOG",
    "SLOT_174_DRIFT__PREFLIGHT",
    "SLOT_175_DRIFT__CATALOG",
    "SLOT_175_DRIFT__PREFLIGHT",
    "SLOT_176_DRIFT__CATALOG",
    "SLOT_176_DRIFT__PREFLIGHT",
    "SLOT_177_DRIFT__CATALOG",
    "SLOT_177_DRIFT__PREFLIGHT",
    "SLOT_178_DRIFT__CATALOG",
    "SLOT_178_DRIFT__PREFLIGHT",
    "SLOT_179_DRIFT__CATALOG",
    "SLOT_179_DRIFT__PREFLIGHT",
    "SLOT_180_DRIFT__CATALOG",
    "SLOT_180_DRIFT__PREFLIGHT",
    "SLOT_181_DRIFT__CATALOG",
    "SLOT_181_DRIFT__PREFLIGHT",
    "SLOT_182_DRIFT__CATALOG",
    "SLOT_182_DRIFT__PREFLIGHT",
    "SLOT_183_DRIFT__CATALOG",
    "SLOT_183_DRIFT__PREFLIGHT",
    "SLOT_184_LITERAL__CATALOG",
    "SLOT_184_LITERAL__PREFLIGHT",
    "SLOT_184_REMOVE__CATALOG",
    "SLOT_184_REMOVE__PREFLIGHT",
    "SLOT_184_OPAQUE__CATALOG",
    "SLOT_184_OPAQUE__PREFLIGHT",
    "SLOT_185_DRIFT__CATALOG",
    "SLOT_185_DRIFT__PREFLIGHT",
    "SLOT_186_DRIFT__CATALOG",
    "SLOT_186_DRIFT__PREFLIGHT",
    "SLOT_187_DRIFT__CATALOG",
    "SLOT_187_DRIFT__PREFLIGHT",
    "SLOT_188_DRIFT__CATALOG",
    "SLOT_188_DRIFT__PREFLIGHT",
    "SLOT_189_DRIFT__CATALOG",
    "SLOT_189_DRIFT__PREFLIGHT",
    "SLOT_190_DRIFT__CATALOG",
    "SLOT_190_DRIFT__PREFLIGHT",
    "SLOT_191_DRIFT__CATALOG",
    "SLOT_191_DRIFT__PREFLIGHT",
    "SLOT_192_DRIFT__CATALOG",
    "SLOT_192_DRIFT__PREFLIGHT",
    "SLOT_193_LITERAL__CATALOG",
    "SLOT_193_LITERAL__PREFLIGHT",
    "SLOT_193_REMOVE__CATALOG",
    "SLOT_193_REMOVE__PREFLIGHT",
    "SLOT_193_OPAQUE__CATALOG",
    "SLOT_193_OPAQUE__PREFLIGHT",
    "SLOT_194_LITERAL__CATALOG",
    "SLOT_194_LITERAL__PREFLIGHT",
    "SLOT_194_REMOVE__CATALOG",
    "SLOT_194_REMOVE__PREFLIGHT",
    "SLOT_194_OPAQUE__CATALOG",
    "SLOT_194_OPAQUE__PREFLIGHT",
    "SLOT_195_LITERAL__CATALOG",
    "SLOT_195_LITERAL__PREFLIGHT",
    "SLOT_195_REMOVE__CATALOG",
    "SLOT_195_REMOVE__PREFLIGHT",
    "SLOT_195_OPAQUE__CATALOG",
    "SLOT_195_OPAQUE__PREFLIGHT",
    "SLOT_196_DRIFT__CATALOG",
    "SLOT_196_DRIFT__PREFLIGHT",
    "SLOT_197_DRIFT__CATALOG",
    "SLOT_197_DRIFT__PREFLIGHT",
    "SLOT_198_DRIFT__CATALOG",
    "SLOT_198_DRIFT__PREFLIGHT",
    "SLOT_199_DRIFT__CATALOG",
    "SLOT_199_DRIFT__PREFLIGHT",
    "SLOT_200_DRIFT__CATALOG",
    "SLOT_200_DRIFT__PREFLIGHT",
    "SLOT_201_DRIFT__CATALOG",
    "SLOT_201_DRIFT__PREFLIGHT",
    "SLOT_202_DRIFT__CATALOG",
    "SLOT_202_DRIFT__PREFLIGHT",
    "SLOT_203_DRIFT__CATALOG",
    "SLOT_203_DRIFT__PREFLIGHT",
    "SLOT_204_LITERAL__CATALOG",
    "SLOT_204_LITERAL__PREFLIGHT",
    "SLOT_204_REMOVE__CATALOG",
    "SLOT_204_REMOVE__PREFLIGHT",
    "SLOT_204_OPAQUE__CATALOG",
    "SLOT_204_OPAQUE__PREFLIGHT",
    "SLOT_205_LITERAL__CATALOG",
    "SLOT_205_LITERAL__PREFLIGHT",
    "SLOT_205_REMOVE__CATALOG",
    "SLOT_205_REMOVE__PREFLIGHT",
    "SLOT_205_OPAQUE__CATALOG",
    "SLOT_205_OPAQUE__PREFLIGHT",
    "SLOT_206_LITERAL__CATALOG",
    "SLOT_206_LITERAL__PREFLIGHT",
    "SLOT_206_REMOVE__CATALOG",
    "SLOT_206_REMOVE__PREFLIGHT",
    "SLOT_206_OPAQUE__CATALOG",
    "SLOT_206_OPAQUE__PREFLIGHT",
    "SLOT_207_DRIFT__CATALOG",
    "SLOT_207_DRIFT__PREFLIGHT",
    "SLOT_208_DRIFT__CATALOG",
    "SLOT_208_DRIFT__PREFLIGHT",
    "SLOT_209_DRIFT__CATALOG",
    "SLOT_209_DRIFT__PREFLIGHT",
    "SLOT_210_DRIFT__CATALOG",
    "SLOT_210_DRIFT__PREFLIGHT",
    "SLOT_211_DRIFT__CATALOG",
    "SLOT_211_DRIFT__PREFLIGHT",
    "SLOT_212_DRIFT__CATALOG",
    "SLOT_212_DRIFT__PREFLIGHT",
    "SLOT_213_DRIFT__CATALOG",
    "SLOT_213_DRIFT__PREFLIGHT",
    "SLOT_214_DRIFT__CATALOG",
    "SLOT_214_DRIFT__PREFLIGHT",
    "SLOT_215_LITERAL__CATALOG",
    "SLOT_215_LITERAL__PREFLIGHT",
    "SLOT_215_REMOVE__CATALOG",
    "SLOT_215_REMOVE__PREFLIGHT",
    "SLOT_215_OPAQUE__CATALOG",
    "SLOT_215_OPAQUE__PREFLIGHT",
    "SLOT_216_LITERAL__CATALOG",
    "SLOT_216_LITERAL__PREFLIGHT",
    "SLOT_216_REMOVE__CATALOG",
    "SLOT_216_REMOVE__PREFLIGHT",
    "SLOT_216_OPAQUE__CATALOG",
    "SLOT_216_OPAQUE__PREFLIGHT",
    "SLOT_217_LITERAL__CATALOG",
    "SLOT_217_LITERAL__PREFLIGHT",
    "SLOT_217_REMOVE__CATALOG",
    "SLOT_217_REMOVE__PREFLIGHT",
    "SLOT_217_OPAQUE__CATALOG",
    "SLOT_217_OPAQUE__PREFLIGHT",
    "SLOT_218_DRIFT__CATALOG",
    "SLOT_218_DRIFT__PREFLIGHT",
    "SLOT_219_DRIFT__CATALOG",
    "SLOT_219_DRIFT__PREFLIGHT",
    "SLOT_220_DRIFT__CATALOG",
    "SLOT_220_DRIFT__PREFLIGHT",
    "SLOT_221_DRIFT__CATALOG",
    "SLOT_221_DRIFT__PREFLIGHT",
    "SLOT_222_DRIFT__CATALOG",
    "SLOT_222_DRIFT__PREFLIGHT",
    "SLOT_223_DRIFT__CATALOG",
    "SLOT_223_DRIFT__PREFLIGHT",
    "SLOT_224_DRIFT__CATALOG",
    "SLOT_224_DRIFT__PREFLIGHT",
    "SLOT_225_DRIFT__CATALOG",
    "SLOT_225_DRIFT__PREFLIGHT",
    "SLOT_226_LITERAL__CATALOG",
    "SLOT_226_LITERAL__PREFLIGHT",
    "SLOT_226_REMOVE__CATALOG",
    "SLOT_226_REMOVE__PREFLIGHT",
    "SLOT_226_OPAQUE__CATALOG",
    "SLOT_226_OPAQUE__PREFLIGHT",
    "SLOT_227_DRIFT__CATALOG",
    "SLOT_227_DRIFT__PREFLIGHT",
    "SLOT_228_DRIFT__CATALOG",
    "SLOT_228_DRIFT__PREFLIGHT",
    "SLOT_229_DRIFT__CATALOG",
    "SLOT_229_DRIFT__PREFLIGHT",
    "SLOT_230_DRIFT__CATALOG",
    "SLOT_230_DRIFT__PREFLIGHT",
    "SLOT_231_DRIFT__CATALOG",
    "SLOT_231_DRIFT__PREFLIGHT",
    "SLOT_232_DRIFT__CATALOG",
    "SLOT_232_DRIFT__PREFLIGHT",
    "SLOT_233_DRIFT__CATALOG",
    "SLOT_233_DRIFT__PREFLIGHT",
    "SLOT_234_DRIFT__CATALOG",
    "SLOT_234_DRIFT__PREFLIGHT",
    "SLOT_235_DRIFT__CATALOG",
    "SLOT_235_DRIFT__PREFLIGHT",
    "SLOT_236_DRIFT__CATALOG",
    "SLOT_236_DRIFT__PREFLIGHT",
    "SLOT_237_DRIFT__CATALOG",
    "SLOT_237_DRIFT__PREFLIGHT",
    "SLOT_238_DRIFT__CATALOG",
    "SLOT_238_DRIFT__PREFLIGHT",
    "SLOT_239_LITERAL__CATALOG",
    "SLOT_239_LITERAL__PREFLIGHT",
    "SLOT_239_REMOVE__CATALOG",
    "SLOT_239_REMOVE__PREFLIGHT",
    "SLOT_239_OPAQUE__CATALOG",
    "SLOT_239_OPAQUE__PREFLIGHT",
    "SLOT_240_DRIFT__CATALOG",
    "SLOT_240_DRIFT__PREFLIGHT",
    "SLOT_241_DRIFT__CATALOG",
    "SLOT_241_DRIFT__PREFLIGHT",
    "SLOT_242_DRIFT__CATALOG",
    "SLOT_242_DRIFT__PREFLIGHT",
    "SLOT_243_DRIFT__CATALOG",
    "SLOT_243_DRIFT__PREFLIGHT",
    "SLOT_244_DRIFT__CATALOG",
    "SLOT_244_DRIFT__PREFLIGHT",
    "SLOT_245_DRIFT__CATALOG",
    "SLOT_245_DRIFT__PREFLIGHT",
    "SLOT_246_DRIFT__CATALOG",
    "SLOT_246_DRIFT__PREFLIGHT",
    "SLOT_247_DRIFT__CATALOG",
    "SLOT_247_DRIFT__PREFLIGHT",
    "SLOT_248_DRIFT__CATALOG",
    "SLOT_248_DRIFT__PREFLIGHT",
    "SLOT_249_DRIFT__CATALOG",
    "SLOT_249_DRIFT__PREFLIGHT",
    "SLOT_250_DRIFT__CATALOG",
    "SLOT_250_DRIFT__PREFLIGHT",
    "SLOT_251_DRIFT__CATALOG",
    "SLOT_251_DRIFT__PREFLIGHT",
    "SLOT_252_DRIFT__CATALOG",
    "SLOT_252_DRIFT__PREFLIGHT",
    "SLOT_253_DRIFT__CATALOG",
    "SLOT_253_DRIFT__PREFLIGHT",
    "SLOT_254_DRIFT__CATALOG",
    "SLOT_254_DRIFT__PREFLIGHT",
    "SLOT_255_DRIFT__CATALOG",
    "SLOT_255_DRIFT__PREFLIGHT",
    "SLOT_256_DRIFT__CATALOG",
    "SLOT_256_DRIFT__PREFLIGHT",
    "SLOT_257_DRIFT__CATALOG",
    "SLOT_257_DRIFT__PREFLIGHT",
    "SLOT_258_DRIFT__CATALOG",
    "SLOT_258_DRIFT__PREFLIGHT",
    "SLOT_259_DRIFT__CATALOG",
    "SLOT_259_DRIFT__PREFLIGHT",
    "SLOT_260_DRIFT__CATALOG",
    "SLOT_260_DRIFT__PREFLIGHT",
    "SLOT_261_LITERAL__CATALOG",
    "SLOT_261_LITERAL__PREFLIGHT",
    "SLOT_261_REMOVE__CATALOG",
    "SLOT_261_REMOVE__PREFLIGHT",
    "SLOT_261_OPAQUE__CATALOG",
    "SLOT_261_OPAQUE__PREFLIGHT",
    "SLOT_262_DRIFT__CATALOG",
    "SLOT_262_DRIFT__PREFLIGHT",
    "SLOT_263_DRIFT__CATALOG",
    "SLOT_263_DRIFT__PREFLIGHT",
    "SLOT_264_DRIFT__CATALOG",
    "SLOT_264_DRIFT__PREFLIGHT",
    "SLOT_265_LITERAL__CATALOG",
    "SLOT_265_LITERAL__PREFLIGHT",
    "SLOT_265_REMOVE__CATALOG",
    "SLOT_265_REMOVE__PREFLIGHT",
    "SLOT_265_OPAQUE__CATALOG",
    "SLOT_265_OPAQUE__PREFLIGHT",
    "SLOT_266_LITERAL__CATALOG",
    "SLOT_266_LITERAL__PREFLIGHT",
    "SLOT_266_REMOVE__CATALOG",
    "SLOT_266_REMOVE__PREFLIGHT",
    "SLOT_266_OPAQUE__CATALOG",
    "SLOT_266_OPAQUE__PREFLIGHT",
    "SLOT_267_DRIFT__CATALOG",
    "SLOT_267_DRIFT__PREFLIGHT",
    "SLOT_268_DRIFT__CATALOG",
    "SLOT_268_DRIFT__PREFLIGHT",
    "SLOT_269_DRIFT__CATALOG",
    "SLOT_269_DRIFT__PREFLIGHT",
    "SLOT_270_DRIFT__CATALOG",
    "SLOT_270_DRIFT__PREFLIGHT",
    "SLOT_271_DRIFT__CATALOG",
    "SLOT_271_DRIFT__PREFLIGHT",
    "SLOT_272_DRIFT__CATALOG",
    "SLOT_272_DRIFT__PREFLIGHT",
    "SLOT_273_LITERAL__CATALOG",
    "SLOT_273_LITERAL__PREFLIGHT",
    "SLOT_273_REMOVE__CATALOG",
    "SLOT_273_REMOVE__PREFLIGHT",
    "SLOT_273_OPAQUE__CATALOG",
    "SLOT_273_OPAQUE__PREFLIGHT",
    "SLOT_274_DRIFT__CATALOG",
    "SLOT_274_DRIFT__PREFLIGHT",
    "SLOT_275_DRIFT__CATALOG",
    "SLOT_275_DRIFT__PREFLIGHT",
    "SLOT_276_DRIFT__CATALOG",
    "SLOT_276_DRIFT__PREFLIGHT",
    "SLOT_277_DRIFT__CATALOG",
    "SLOT_277_DRIFT__PREFLIGHT",
    "SLOT_278_DRIFT__CATALOG",
    "SLOT_278_DRIFT__PREFLIGHT",
    "SLOT_279_DRIFT__CATALOG",
    "SLOT_279_DRIFT__PREFLIGHT",
    "SLOT_280_DRIFT__CATALOG",
    "SLOT_280_DRIFT__PREFLIGHT",
    "SLOT_281_DRIFT__CATALOG",
    "SLOT_281_DRIFT__PREFLIGHT",
    "SLOT_282_DRIFT__CATALOG",
    "SLOT_282_DRIFT__PREFLIGHT",
    "SLOT_283_DRIFT__CATALOG",
    "SLOT_283_DRIFT__PREFLIGHT",
    "SLOT_284_DRIFT__CATALOG",
    "SLOT_284_DRIFT__PREFLIGHT",
    "SLOT_285_DRIFT__CATALOG",
    "SLOT_285_DRIFT__PREFLIGHT",
    "SLOT_286_DRIFT__CATALOG",
    "SLOT_286_DRIFT__PREFLIGHT",
    "SLOT_287_DRIFT__CATALOG",
    "SLOT_287_DRIFT__PREFLIGHT",
    "SLOT_288_DRIFT__CATALOG",
    "SLOT_288_DRIFT__PREFLIGHT",
    "SLOT_289_DRIFT__CATALOG",
    "SLOT_289_DRIFT__PREFLIGHT",
    "SLOT_290_DRIFT__CATALOG",
    "SLOT_290_DRIFT__PREFLIGHT",
    "SLOT_291_DRIFT__CATALOG",
    "SLOT_291_DRIFT__PREFLIGHT",
    "SLOT_292_DRIFT__CATALOG",
    "SLOT_292_DRIFT__PREFLIGHT",
    "SLOT_293_DRIFT__CATALOG",
    "SLOT_293_DRIFT__PREFLIGHT",
    "SLOT_294_DRIFT__CATALOG",
    "SLOT_294_DRIFT__PREFLIGHT",
    "SLOT_295_DRIFT__CATALOG",
    "SLOT_295_DRIFT__PREFLIGHT",
    "SLOT_296_DRIFT__CATALOG",
    "SLOT_296_DRIFT__PREFLIGHT",
    "SLOT_297_DRIFT__CATALOG",
    "SLOT_297_DRIFT__PREFLIGHT",
    "SLOT_298_DRIFT__CATALOG",
    "SLOT_298_DRIFT__PREFLIGHT",
    "SLOT_299_DRIFT__CATALOG",
    "SLOT_299_DRIFT__PREFLIGHT",
    "SLOT_300_DRIFT__CATALOG",
    "SLOT_300_DRIFT__PREFLIGHT",
    "SLOT_301_LITERAL__CATALOG",
    "SLOT_301_LITERAL__PREFLIGHT",
    "SLOT_301_REMOVE__CATALOG",
    "SLOT_301_REMOVE__PREFLIGHT",
    "SLOT_301_OPAQUE__CATALOG",
    "SLOT_301_OPAQUE__PREFLIGHT",
    "SLOT_302_LITERAL__CATALOG",
    "SLOT_302_LITERAL__PREFLIGHT",
    "SLOT_302_REMOVE__CATALOG",
    "SLOT_302_REMOVE__PREFLIGHT",
    "SLOT_302_OPAQUE__CATALOG",
    "SLOT_302_OPAQUE__PREFLIGHT",
    "SLOT_303_DRIFT__CATALOG",
    "SLOT_303_DRIFT__PREFLIGHT",
    "SLOT_304_DRIFT__CATALOG",
    "SLOT_304_DRIFT__PREFLIGHT",
    "SLOT_305_DRIFT__CATALOG",
    "SLOT_305_DRIFT__PREFLIGHT",
)
FLAGS = (
    "installed_runtime_changed",
    "runtime_actor_binding_implemented",
    "runtime_writer_fence_verified",
    "runtime_verifier_implemented",
    "runtime_recovery_implemented",
    "repair_implemented",
    "active_faults_authorized",
)
DETAIL_KEYS = (
    "target_resolved",
    "chain_depth",
    "baseline_matched",
    "baseline_checked",
    "mutation_entered",
    "mutated_matched",
    "mutated_checked",
    "restored_matched",
    "restored_checked",
    "target_restored",
    "fresh_catalog_matched",
    "fresh_checked",
    "source_matched",
    "units_matched",
    "source_checked",
    "units_checked",
)
BOOL_KEYS = {
    "target_resolved",
    "baseline_matched",
    "mutation_entered",
    "mutated_matched",
    "restored_matched",
    "target_restored",
    "fresh_catalog_matched",
    "source_matched",
    "units_matched",
}
INT_KEYS = set(DETAIL_KEYS) - BOOL_KEYS
SUPPORT = None
AK = None
M = {}
DETAILS = None
UNITS = {}


class TargetRestoreStop(Exception):
    pass


def require(value, code):
    if not value:
        raise ValueError(code)


def private(path, directory=False):
    i = path.lstat()
    require(
        (stat.S_ISDIR(i.st_mode) if directory else stat.S_ISREG(i.st_mode))
        and i.st_uid == os.getuid()
        and stat.S_IMODE(i.st_mode) == (0o700 if directory else 0o600)
        and (directory or i.st_nlink == 1),
        "PRIVATE_METADATA",
    )


def bootstrap():
    global AK, SUPPORT, UNITS
    private(NOTES, True)
    for name, digest in (("ak.py", AK_SHA), ("slots.json", SLOTS_SHA)):
        private(NOTES / name)
        require(hashlib.sha256((NOTES / name).read_bytes()).hexdigest() == digest, "ARTIFACT_SHA")
    spec = importlib.util.spec_from_file_location("al_pinned_ak_support", NOTES / "ak.py")
    AK = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(AK)
    AK.NOTES = NOTES
    count = AK.bootstrap()
    SUPPORT, UNITS = AK.SUPPORT, AK.UNITS
    return count


def chain(function):
    rows, seen = [], set()
    while function is not None:
        require(
            type(function) is FunctionType and function not in seen and len(rows) < 8,
            "CHAIN_REFUSED",
        )
        rows.append(function)
        seen.add(function)
        function = getattr(function, "__wrapped__", None)
    return tuple(rows)


def catalog(module):
    result = []
    for surface, (owner, method, _) in sorted(module.SURFACES.items()):
        for depth, fn in enumerate(chain(getattr(owner, method))):
            if depth:
                result.append((surface, depth, "CODE", "", 0))
            for index, value in enumerate(fn.__defaults__ or ()):
                name = fn.__code__.co_varnames[
                    fn.__code__.co_argcount - len(fn.__defaults__) + index
                ]
                result.append((surface, depth, "POS", name, index))
                if type(value) is FunctionType:
                    result.append((surface, depth, "POS_CODE", name, index))
            for name, value in sorted((fn.__kwdefaults__ or {}).items()):
                result.append((surface, depth, "KW", name, 0))
                if type(value) is FunctionType:
                    result.append((surface, depth, "KW_CODE", name, 0))
            for index, _ in enumerate(fn.__closure__ or ()):
                result.append((surface, depth, "CELL", fn.__code__.co_freevars[index], index))
    return tuple(result)


def source():
    global M
    AK.source()
    M = AK.M
    actual = catalog(M["ownership_surface"])
    require(actual == SLOTS, "ACTUAL_SLOT_INVENTORY")
    document = SUPPORT.read(NOTES / "slots.json")
    require(document == {"schema": 1, "slots": [list(row) for row in actual]}, "SLOT_DOCUMENT")


@contextlib.contextmanager
def target_attribute(obj, name, value):
    before = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, before)
        restored = getattr(obj, name)
        if name in ("__code__", "cell_contents"):
            equal = restored is before
        else:
            equal = restored is before or (type(restored) is type(before) and restored == before)
        if not equal:
            raise TargetRestoreStop("TARGET_RESTORE_FAILED")
        DETAILS["target_restored"] = True


def default_target(surface, parameter):
    owner, method, _ = M["ownership_surface"].SURFACES[surface]
    matches = [
        (depth, fn)
        for depth, fn in enumerate(chain(getattr(owner, method)))
        if parameter in (fn.__kwdefaults__ or {})
    ]
    require(len(matches) == 1, "DEFAULT_TARGET_AMBIGUOUS")
    return matches[0]


def run_case(f, name):
    module = M["ownership_surface"]
    name, route = name.rsplit("__", 1)
    require(route in ("CATALOG", "PREFLIGHT"), "CASE_ROUTE")
    source_seal = units_seal = None

    def new_observer():
        surface = module.SurfaceCatalog(SURFACE_SHA)
        if route == "CATALOG":
            return surface
        identity = M["ownership_identity"].CodeIdentity(
            source_seal.manifest_digest(), units_seal.manifest_digest(), SURFACE_SHA
        )
        return module.CodePreflight(identity, source_seal, units_seal, surface)

    def checked(result):
        return result.checked if route == "CATALOG" else result.surface_checked

    if route == "PREFLIGHT":
        source_seal, units_seal = AK.make_seal(f, "source"), AK.make_seal(f, "units")
    observer = new_observer()
    baseline = observer.observe()
    DETAILS.update(baseline_matched=baseline.matched, baseline_checked=checked(baseline))
    if not (baseline.matched and checked(baseline) == 65):
        raise TargetRestoreStop("BASELINE_SURFACES")
    if name == "REPAIR_H_DEFAULT":
        depth, fn = default_target("engine.apply_all", "force_now")
        obj, attr, value = fn, "__kwdefaults__", {**fn.__kwdefaults__, "force_now": True}
    elif name == "REPAIR_H_DEFAULT_CODE":
        depth, fn = default_target("actions.apply_network", "runner")
        obj = fn.__kwdefaults__["runner"]
        require(type(obj) is FunctionType, "DEFAULT_FUNCTION")
        attr, value = (
            "__code__",
            obj.__code__.replace(co_firstlineno=obj.__code__.co_firstlineno + 1),
        )
    else:
        prefix, index_text, mode = name.split("_")
        require(prefix == "SLOT", "CASE_ID")
        surface, depth, kind, parameter, index = SLOTS[int(index_text)]
        owner, method, _ = module.SURFACES[surface]
        fn = chain(getattr(owner, method))[depth]
        if kind == "CODE":
            obj, attr, value = (
                fn,
                "__code__",
                fn.__code__.replace(co_firstlineno=fn.__code__.co_firstlineno + 1),
            )
        elif kind == "CELL":
            obj, attr, value = fn.__closure__[index], "cell_contents", object()
        elif kind.endswith("_CODE"):
            obj = fn.__kwdefaults__[parameter] if kind == "KW_CODE" else fn.__defaults__[index]
            require(type(obj) is FunctionType, "DEFAULT_FUNCTION")
            attr, value = (
                "__code__",
                obj.__code__.replace(co_firstlineno=obj.__code__.co_firstlineno + 1),
            )
        elif kind == "KW":
            obj, attr = fn, "__kwdefaults__"
            value = dict(fn.__kwdefaults__)
            if mode == "REMOVE":
                del value[parameter]
            else:
                value[parameter] = object() if mode == "OPAQUE" else "AL_CHANGED_PUBLIC_LITERAL"
        else:
            require(kind == "POS", "SLOT_KIND")
            obj, attr = fn, "__defaults__"
            values = list(fn.__defaults__)
            if mode == "REMOVE":
                values.pop(index)
            else:
                values[index] = object() if mode == "OPAQUE" else "AL_CHANGED_PUBLIC_LITERAL"
            value = tuple(values)
    DETAILS.update(target_resolved=True, chain_depth=depth)
    before = module.function_state(fn)
    failure = None
    with target_attribute(obj, attr, value):
        DETAILS["mutation_entered"] = True
        try:
            result = observer.observe()
            DETAILS.update(mutated_matched=result.matched, mutated_checked=checked(result))
            if route == "PREFLIGHT":
                DETAILS.update(
                    source_matched=result.source_matched,
                    units_matched=result.units_matched,
                    source_checked=result.source_checked,
                    units_checked=result.units_checked,
                )
        except BaseException as exc:
            failure = exc
    restored = observer.observe()
    fresh = new_observer().observe()
    DETAILS.update(
        restored_matched=restored.matched,
        restored_checked=checked(restored),
        fresh_catalog_matched=fresh.matched,
        fresh_checked=checked(fresh),
    )
    if not (
        module.same_state(before, module.function_state(fn)) and restored.matched and fresh.matched
    ):
        raise TargetRestoreStop("SURFACE_RESTORE_FAILED")
    if failure is not None:
        raise failure
    require(
        not result.matched and checked(result) == 0 and checked(restored) == checked(fresh) == 65,
        "DEFAULT_MUTATION_NOT_REJECTED",
    )
    if route == "PREFLIGHT":
        require(
            result.source_matched is result.units_matched is True
            and result.source_checked == result.units_checked == 1,
            "PREFLIGHT_INDEPENDENT_EVIDENCE",
        )


def read_record(path):
    private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == os.getuid()
            and stat.S_IMODE(before.st_mode) == 0o600
            and before.st_nlink == 1
            and before.st_size <= 1048576,
            "RECORD_METADATA",
        )
        raw = stream.read(1048577)
        after = os.fstat(stream.fileno())

    def fields(s):
        return (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_size, s.st_mtime_ns)

    require(len(raw) <= 1048576 and fields(before) == fields(after), "RECORD_CHANGED")

    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, "DUPLICATE_RECORD_KEY")
            result[k] = v
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def batch():
    global DETAILS
    SUPPORT.create(NOTES / "worker-claimed.json", {"claimed": True})
    os.umask(0o077)
    source_count = SUPPORT.verify_source()
    source()
    cases = NOTES / "cases"
    cases.mkdir(mode=0o700)
    rows = []
    scope_stopped = False
    started = time.monotonic()
    for name in EXPECTED:
        root = cases / f"case-{len(rows) + 1:03d}"
        root.mkdir(mode=0o700)
        before = time.monotonic()
        f = None
        DETAILS = dict.fromkeys(DETAIL_KEYS)
        try:
            f = SimpleNamespace(root=root, work=root)
            run_case(f, name)
            row = {"case": name, "passed": True}
        except Exception as exc:
            scope_stopped = isinstance(exc, (SUPPORT.ScopeStop, OSError, TargetRestoreStop))
            public, line = "UNKNOWN", None
            tb = exc.__traceback__
            while tb is not None:
                filename = Path(tb.tb_frame.f_code.co_filename)
                try:
                    public, line = filename.relative_to(NOTES / "source").as_posix(), tb.tb_lineno
                except ValueError:
                    mapping = {
                        "batch.py": "wave3_defaults_closure.py",
                        "ak.py": "wave3_code_handshake.py",
                        "support.py": "wave3_source_hooks.py",
                        "legacy.py": (
                            "legacy@63c9c413930eb348d46b2ff986bef46dd2e423d4/src/xgw/ownership.py"
                        ),
                    }
                    if filename.parent == NOTES and filename.name in mapping:
                        public, line = "tests/stand/" + mapping[filename.name], tb.tb_lineno
                tb = tb.tb_next
            row = {
                "case": name,
                "passed": False,
                "reason": "DEFAULTS_CLOSURE_CASE_FAILED",
                "error_class": type(exc).__name__
                if type(exc).__name__
                in (
                    "ValueError",
                    "TypeError",
                    "RuntimeError",
                    "OSError",
                    "ScopeStop",
                    "TargetRestoreStop",
                    "Refused",
                    "IdentityRefused",
                    "SealRefused",
                    "SurfaceRefused",
                    "AssertionError",
                    "CompletionRefused",
                    "MutationBlocked",
                )
                else "OTHER_EXCEPTION_CLASS",
                "public_error_source": public,
                "public_error_line": line,
            }
        row.update(details=DETAILS, elapsed_ms=int((time.monotonic() - before) * 1000))
        rows.append(row)
        SUPPORT.atomic("progress.json", {"final": False, "completed": len(rows), "cases": rows})
        if SUPPORT.AUDIT["violations"] or scope_stopped:
            break
    passed = sum(row["passed"] for row in rows)
    result = {
        "marker": "DEFAULTS_CLOSURE_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "DEFAULTS_CLOSURE_BATCH_PARTIAL",
        "scope": "DECLARED_DEFAULTS_CLOSURES_AND_TWO_AK_REPAIRS_ONLY",
        "expected": len(EXPECTED),
        "completed": len(rows),
        "passed": passed,
        "cases": rows,
        "global_scope_stop": scope_stopped or SUPPORT.AUDIT["violations"] > 0,
        "remaining_not_run": len(EXPECTED) - len(rows),
        "source_files": source_count,
        "unit_files": len(UNITS),
        "declared_surfaces": 65,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "audit_registered": SUPPORT.AUDIT["ready"],
        "unexpected_forbidden_io": SUPPORT.AUDIT["violations"],
        "workload_subprocesses": 0,
        "network_requests": 0,
        "live_gateway_operations": 0,
        "installed_runtime_changed": False,
        "runtime_actor_binding_implemented": False,
        "runtime_writer_fence_verified": False,
        "runtime_verifier_implemented": False,
        "runtime_recovery_implemented": False,
        "repair_implemented": False,
        "active_faults_authorized": False,
    }
    SUPPORT.atomic("summary.json", result)


def report():
    context = SUPPORT.read(NOTES / "source-current.json")
    require(
        type(context) is dict
        and set(context) == {"head", "tree"}
        and all(type(v) is str and re.fullmatch(r"[0-9a-f]{40}", v) for v in context.values()),
        "REPORT_SOURCE_CONTEXT",
    )
    snapshot = NOTES / "report-record.json"
    if snapshot.exists() or snapshot.is_symlink():
        record = read_record(snapshot)
        require(
            type(record) is dict
            and set(record) == {"context", "selected", "data"}
            and record["context"] == context,
            "REPORT_SNAPSHOT",
        )
        selected, data = record["selected"], record["data"]
    else:
        selected = next(
            (n for n in ("summary.json", "progress.json") if (NOTES / n).exists()), None
        )
        require(selected is not None, "NO_RECORDED_RESULT")
        data = read_record(NOTES / selected)
    require(selected in ("summary.json", "progress.json"), "REPORT_SELECTED_FILE")
    require(type(data) is dict and type(data.get("cases")) is list, "REPORT_SCHEMA")
    numeric = {
        "expected",
        "completed",
        "passed",
        "remaining_not_run",
        "source_files",
        "unit_files",
        "declared_surfaces",
        "elapsed_ms",
        "unexpected_forbidden_io",
        "workload_subprocesses",
        "network_requests",
        "live_gateway_operations",
    }
    boolean = set(FLAGS) | {"audit_registered", "global_scope_stop"}
    require(set(data) <= numeric | boolean | {"marker", "scope", "cases", "final"}, "REPORT_FIELDS")
    for key in numeric:
        val = data.get(key)
        require(val is None or (type(val) is int and 0 <= val <= 2**63 - 1), "CONTROL_TYPE")
    for key in boolean:
        require(data.get(key) is None or type(data[key]) is bool, "CONTROL_TYPE")
    if selected == "summary.json":
        require(
            "final" not in data
            and data.get("scope") == "DECLARED_DEFAULTS_CLOSURES_AND_TWO_AK_REPAIRS_ONLY"
            and data.get("marker")
            in ("DEFAULTS_CLOSURE_BATCH_RECORDED", "DEFAULTS_CLOSURE_BATCH_PARTIAL"),
            "REPORT_IDENTITY",
        )
    else:
        require(
            set(data) == {"final", "completed", "cases"} and data.get("final") is False,
            "CHECKPOINT_ONLY",
        )
    rows = data["cases"]
    require(len(rows) <= len(EXPECTED) and data.get("completed") == len(rows), "REPORT_COUNT")
    manifest = SUPPORT.read(NOTES / "manifest.json")
    lines = [
        "# Отчёт: XGW wave3al — wrapper defaults and closure repair",
        "",
        "Автоматические exact данные; таблицу не редактировать. worker_exit_rc=NOT_COLLECTED.",
        "Private wrapper/default/closure observations; product source/installed runtime неизменны.",
        "",
        "Delivery HEAD/tree: " + context["head"] + " / " + context["tree"],
        "Legacy public reference: " + LEGACY_COMMIT + " / " + LEGACY_SHA,
        "Selected: " + selected,
        "Controls: `"
        + json.dumps({k: v for k, v in data.items() if k != "cases"}, sort_keys=True)
        + "`",
        "",
        "|Case|passed|exact ms|actual details|public error|",
        "|---|---|---|---|---|",
    ]
    boolkeys, intkeys = BOOL_KEYS, INT_KEYS
    for i, row in enumerate(rows):
        require(
            type(row) is dict
            and set(row)
            <= {
                "case",
                "passed",
                "details",
                "elapsed_ms",
                "reason",
                "error_class",
                "public_error_source",
                "public_error_line",
            },
            "ROW_FIELDS",
        )
        require(
            row.get("case") == EXPECTED[i]
            and type(row.get("passed")) is bool
            and type(row.get("elapsed_ms")) is int
            and 0 <= row["elapsed_ms"] <= 2**63 - 1,
            "ROW_SHAPE",
        )
        d = row.get("details")
        require(type(d) is dict and set(d) == set(DETAIL_KEYS), "DETAIL_FIELDS")
        for k in intkeys:
            require(d[k] is None or (type(d[k]) is int and 0 <= d[k] <= 2**63 - 1), "DETAIL_COUNT")
        for k in boolkeys:
            require(d[k] is None or type(d[k]) is bool, "DETAIL_BOOL")
        cls = row.get("error_class")
        require(
            cls is None
            or cls
            in (
                "ValueError",
                "TypeError",
                "RuntimeError",
                "OSError",
                "ScopeStop",
                "TargetRestoreStop",
                "Refused",
                "IdentityRefused",
                "SealRefused",
                "SurfaceRefused",
                "AssertionError",
                "CompletionRefused",
                "MutationBlocked",
                "OTHER_EXCEPTION_CLASS",
            ),
            "ERROR_CLASS",
        )
        public = row.get("public_error_source")
        require(
            public is None
            or public in manifest
            or public
            in (
                "UNKNOWN",
                "tests/stand/wave3_code_handshake.py",
                "tests/stand/wave3_defaults_closure.py",
                "tests/stand/wave3_source_hooks.py",
                "tests/stand/legacy@63c9c413930eb348d46b2ff986bef46dd2e423d4/src/xgw/ownership.py",
            ),
            "ERROR_SOURCE",
        )
        line = row.get("public_error_line")
        require(line is None or (type(line) is int and 0 < line <= 200000), "ERROR_LINE")
        lines.append(
            "|"
            + "|".join(
                (
                    row["case"],
                    json.dumps(row["passed"]),
                    str(row["elapsed_ms"]),
                    json.dumps(d, sort_keys=True, separators=(",", ":")),
                    json.dumps([cls, public, line], separators=(",", ":")),
                )
            )
            + "|"
        )
    lines += [
        "",
        "Null = не собрано. Case PASS отрицательного сценария не означает завершение операции.",
        "Значения7 runtime gates приведены в Controls. Case PASS не разрешает активацию.",
        "Host не LAN proof.",
        "",
    ]
    raw = ("\n".join(lines)).encode()
    if not snapshot.exists():
        clean = {k: v for k, v in data.items() if k != "cases"}
        clean["cases"] = [{k: v for k, v in r.items() if k != "reason"} for r in rows]
        SUPPORT.create(snapshot, {"context": context, "selected": selected, "data": clean})
    target = NOTES / "report-data.md"
    if target.exists() or target.is_symlink():
        private(target)
        require(target.read_bytes() == raw, "REPORT_DATA_CHANGED")
    else:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
    print("DEFAULTS_CLOSURE_REPORT_READY")


if __name__ == "__main__":
    try:
        require(os.geteuid() != 0 and len(sys.argv) == 2, "OWNER_OR_MODE")
        bootstrap()
        command = sys.argv[1]
        if command in ("status", "show"):
            for filename in ("summary.json", "progress.json"):
                if (NOTES / filename).exists():
                    print(json.dumps({"file": filename, "data": read_record(NOTES / filename)}))
                    break
            else:
                print(json.dumps({"file": None, "status": "NO_RECORDED_RESULT"}))
        elif command == "report":
            report()
        elif command == "start":
            SUPPORT.create(NOTES / "started.json", {"started": True})
            subprocess.Popen(
                [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_batch"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print("DEFAULTS_CLOSURE_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception:
        print("DEFAULTS_CLOSURE_BATCH_STOP", "LOCAL_IO_OR_SCHEMA_ERROR")
        raise SystemExit(3) from None
