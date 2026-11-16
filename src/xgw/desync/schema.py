"""Versioned, lossless policy migration. Parsing never activates a route or worker.

Branch defaults are explicit: a freepool document must be imported with source='freepool'.
The canonical document preserves both legacy controllers, including engine suspension while
the selected-domain controller is enabled. Unimplemented modes are rejected at projection.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from .flowseal import LIVE_STRATEGY, valid_live_scope

VERSION = 1
MODES = ("off", "standalone", "selective", "compare")
T09_PROFILES = ("fake_md5_split", "fake_seq_split")
SELECTED_PROFILES = (
    "multisplit", "multidisorder", "fake_md5", "fake_seq", "fake_ts",
    "fakedsplit_md5", "hostfakesplit_md5", "seqovl", "fake_static_md5", "fake_clone_md5",
    *T09_PROFILES, LIVE_STRATEGY,
)
ENGINE_PROFILES = (
    "seqovl", "hostfakesplit", "disorder-badseq", "hostfakesplit-md5", "fakedsplit-md5",
    "fake-static-md5", "fake-clone-md5",
)
GUI_DOMAINS = [
    "domain:youtube.com", "domain:googlevideo.com", "domain:youtubei.googleapis.com",
    "domain:youtube-nocookie.com",
]
FREEPOOL_DOMAINS = [
    "domain:youtube.com", "domain:googlevideo.com", "domain:ytimg.com", "domain:ggpht.com",
    "domain:youtubei.googleapis.com", "domain:youtube.googleapis.com",
    "domain:youtubeembeddedplayer.googleapis.com", "domain:jnn-pa.googleapis.com",
    "domain:youtube-nocookie.com", "domain:youtu.be",
]
DEFAULTS = {
    "mode": "off", "domains": GUI_DOMAINS,
    "binary": "/opt/xgw/zapret2/1.0.7/nfqws2", "lua_dir": "/opt/xgw/zapret2/1.0.7/lua",
    "strategy": "multisplit", "queue_num": 200, "probe_port": 19999, "probe_urls": [],
    "check_seconds": 180, "retry_seconds": 300, "daily_probe_mb": 256,
    "observe_synack": False,
    "observe_reply_packets": 0,
    "engine": "off", "engine_profile": "seqovl", "engine_queue": 200,
    "engine_offload": True, "blob_dir": "",
}
GROUPS = {
    "selected": ("mode", "domains", "strategy", "probe_urls", "check_seconds",
                 "retry_seconds", "daily_probe_mb"),
    "engine": ("engine", "engine_profile", "engine_offload"),
    "runtime": ("binary", "lua_dir", "blob_dir", "queue_num", "engine_queue", "probe_port"),
}
ENGINE_FIELDS = ("engine", "engine_profile", "engine_queue", "engine_offload", "blob_dir")
OBSERVATION_FIELDS = ("observe_synack", "observe_reply_packets")
MAX_REPLY_PACKETS = 8
_DOMAIN = re.compile(r"(?:domain|full):[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")


class PolicyError(ValueError):
    """Invalid/unsupported policy; messages never include private URL values."""


def _require(ok: bool, field: str) -> None:
    if not ok:
        raise PolicyError(f"desync: invalid {field}")


def validate_patch(value: object) -> dict:
    """Validate only supplied legacy fields, without inserting defaults."""
    _require(isinstance(value, dict), "settings")
    _require(not set(value) - DEFAULTS.keys(), "settings keys")
    for name, item in value.items():
        _require(type(item) is type(DEFAULTS[name]), name)
        if isinstance(item, str):
            _require(not any(ord(c) < 32 or ord(c) == 127 for c in item), name)
    for name, allowed in (("mode", MODES), ("strategy", SELECTED_PROFILES),
                          ("engine", ("off", "auto")), ("engine_profile", ENGINE_PROFILES)):
        if name in value:
            _require(value[name] in allowed, name)
    for name, lower, upper in (("queue_num", 1, 65535), ("engine_queue", 1, 65535),
                               ("probe_port", 1024, 65535), ("check_seconds", 60, 900),
                               ("retry_seconds", 60, 3600), ("daily_probe_mb", 1, 1024),
                               ("observe_reply_packets", 0, MAX_REPLY_PACKETS)):
        if name in value:
            _require(lower <= value[name] <= upper, name)
    for name in ("binary", "lua_dir", "blob_dir"):
        if name in value:
            item = value[name]
            if name == "blob_dir" and not item:
                continue
            path = PurePosixPath(item)
            _require(path.is_absolute() and not item.startswith("//") and "\\" not in item
                     and ".." not in path.parts, name)
    if "domains" in value:
        _require(0 < len(value["domains"]) <= 1024, "domains")
        _require(all(isinstance(d, str) and len(d) <= 260 and _DOMAIN.fullmatch(d)
                     for d in value["domains"]), "domains")
    if "probe_urls" in value:
        _require(len(value["probe_urls"]) <= 4, "probe_urls")
        for item in value["probe_urls"]:
            _require(isinstance(item, str) and len(item) <= 8192, "probe_urls")
            try:
                u = urlsplit(item)
                valid = (u.scheme == "https" and bool(u.hostname) and u.port in (None, 443)
                         and not u.username and not u.password and not u.fragment
                         and all(32 < ord(c) < 127 for c in item))
            except ValueError:
                valid = False
            _require(valid, "probe_urls")
    return copy.deepcopy(value)


def migrate(value: object, *, source: str = "gui-light") -> dict:
    """Legacy settings or canonical policy -> canonical policy, without writes.

Canonical input must include all required fields. Packet observation defaults to off.
Unknown versions/fields are rejected, never stripped.
Calling migrate twice returns equal documents; lists preserve order and exact contents.
"""
    _require(source in ("gui-light", "freepool"), "source")
    _require(isinstance(value, dict), "policy")
    if "schema_version" in value:
        _require(type(value["schema_version"]) is int and value["schema_version"] == VERSION,
                 "schema_version")
        _require(set(value) == {"schema_version", *GROUPS}, "policy keys")
        flat = {}
        for group, names in GROUPS.items():
            section = value[group]
            required = set(names)
            optional = set(OBSERVATION_FIELDS) if group == "selected" else set()
            _require(isinstance(section, dict) and required <= set(section) <= required | optional,
                     group)
            flat.update(section)
        flat = validate_patch(flat)
    else:
        flat = copy.deepcopy(DEFAULTS)
        if source == "freepool":
            flat["domains"] = list(FREEPOOL_DOMAINS)
        flat.update(validate_patch(value))
    result = {"schema_version": VERSION,
              **{group: {name: flat[name] for name in names} for group, names in GROUPS.items()}}
    # Preserve the representation and revision of policies without packet observation.
    for name in OBSERVATION_FIELDS:
        if flat.get(name):
            result["selected"][name] = flat[name]
    return result


def validate_policy(value: object) -> dict:
    """Explicit [desync]/panel.desync is always versioned, never a legacy patch."""
    _require(isinstance(value, dict) and "schema_version" in value, "schema_version")
    return migrate(value)


def flatten(policy: dict) -> dict:
    policy = validate_policy(policy)
    return {name: value for group in GROUPS for name, value in policy[group].items()}


def resolve(legacy: dict, policy: dict | None = None, *, source: str = "gui-light") -> dict:
    """An explicit canonical policy may coexist only with matching legacy values."""
    legacy = validate_patch(legacy)
    if policy is None:
        return migrate(legacy, source=source)
    canonical = validate_policy(policy)
    flat = flatten(canonical)
    for name, value in legacy.items():
        if flat.get(name, DEFAULTS[name]) != value:
            raise PolicyError(f"desync: conflicting legacy field {name}")
    return canonical


def project(policy: dict, *, target: str = "gui-light") -> dict:
    """Project to a supported runtime, refusing semantic loss or silent activation.

Freepool cannot represent the universal engine.
Keep the canonical document for exchange when its target runtime is unsupported.
Known selected strategies may remain dormant in off mode without substitution.
"""
    _require(target in ("gui-light", "freepool"), "target")
    flat = flatten(policy)
    if flat.get("observe_reply_packets") and not flat.get("observe_synack"):
        raise PolicyError("desync: observe_reply_packets requires observe_synack")
    if flat["strategy"] == LIVE_STRATEGY:
        if target == "freepool":
            raise PolicyError("desync: the T10 Flowseal profile cannot be represented by freepool")
        if not valid_live_scope(flat["mode"], flat["domains"]):
            raise PolicyError("desync: Flowseal ALT9 requires Standalone and YouTube domains")
    if target == "gui-light":
        if flat["mode"] == "compare" and flat["strategy"] not in ("multisplit", "multidisorder"):
            raise PolicyError("desync: compare tracing supports multisplit and multidisorder")
    else:
        if flat["strategy"] in ("fake_static_md5", "fake_clone_md5"):
            raise PolicyError("desync: the H05 selected profiles cannot be represented by freepool")
        if flat["strategy"] in T09_PROFILES:
            raise PolicyError("desync: the T09 selected profiles cannot be represented by freepool")
        if any(flat.get(name) for name in OBSERVATION_FIELDS):
            raise PolicyError("desync: SYN/ACK observation cannot be represented by freepool")
        if any(flat[name] != DEFAULTS[name] for name in ENGINE_FIELDS):
            raise PolicyError("desync: engine settings cannot be represented by freepool")
        for name in ENGINE_FIELDS:
            del flat[name]
    return flat


def fingerprint(policy: dict) -> str:
    """Opaque revision, including private probes; never expose the policy itself in state."""
    data = json.dumps(validate_policy(policy), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()
