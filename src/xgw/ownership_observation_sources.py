"""AQ wire decoders and bounded proposed transport. Host entry stays scope-blocked."""

from __future__ import annotations

import os
import re
import selectors
import stat
import subprocess
import time
from dataclasses import dataclass

from .ownership_observations import (
    SCOPES,
    SPECS,
    CapturePolicy,
    Decoded,
    ObservationRefused,
    SourceResult,
    SourceSpec,
    canonical,
    integer,
    require,
    strict_json,
)

PHASES = ("BEFORE", "AFTER", "SINGLE")
PROPERTIES = ("Id", "LoadState", "ActiveState", "SubState", "MainPID")


def spec_for(scope):
    require(type(scope) is str and scope in SCOPES)
    return next(s for s in SPECS if s.scope_id == scope)


def decode_unit(raw, spec):
    require(type(raw) is bytes and len(raw) <= 8192)
    text = raw.decode("utf-8", errors="strict")
    rows = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        require(separator and key in PROPERTIES and key not in rows)
        require(value and len(value) <= 128 and re.fullmatch(r"[A-Za-z0-9_.:-]+", value))
        rows[key] = value
    require(set(rows) == set(PROPERTIES) and rows["Id"] == spec.target[0])
    require(
        rows["LoadState"]
        in ("loaded", "not-found", "error", "masked", "bad-setting", "merged", "stub")
    )
    require(
        rows["ActiveState"]
        in (
            "active",
            "inactive",
            "failed",
            "activating",
            "deactivating",
            "reloading",
            "maintenance",
            "refreshing",
        )
    )
    require(re.fullmatch(r"0|[1-9][0-9]{0,9}", rows["MainPID"]))
    rows["MainPID"] = int(rows["MainPID"])
    require(integer(rows["MainPID"], 0, 2**31 - 1))
    return canonical(rows)


def decode_stat(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 8192 and b"\x00" not in raw)
    text = raw.decode("utf-8", errors="strict").rstrip("\n")
    # comm may contain spaces, newlines and ')' characters; suffix has no ')'.
    m = re.fullmatch(r"([1-9][0-9]{0,9}) \((.*)\) ([RSDZTWtXxKWPIN]) (.*)", text, re.S)
    require(m is not None)
    fields = m[4].split()
    require(21 <= len(fields) <= 80)
    require(all(re.fullmatch(r"-?[0-9]{1,20}", item) for item in fields))
    pid, start = int(m[1]), int(fields[18])  # suffix starts at documented field4
    require(integer(pid, 1, 2**31 - 1) and integer(start, 0, 2**64 - 1))
    return canonical({"pid": pid, "starttime": start, "state": m[3]})


def decode_context(raw):
    data = strict_json(raw, cap=8192)
    require(type(data) is dict and set(data) == {"boot", "net", "mnt"})
    require(
        type(data["boot"]) is str
        and re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", data["boot"])
    )
    for name in ("net", "mnt"):
        require(type(data[name]) is str and re.fullmatch(name + r":\[[0-9]{1,20}\]", data[name]))
    return canonical(data)


def decode_process(raw, spec):
    data = strict_json(raw, cap=8192)
    require(type(data) is dict and set(data) == {"unit_scope", "stat", "net", "mnt"})
    require(data["unit_scope"] == spec.target[0] and type(data["stat"]) is str)
    decoded = strict_json(decode_stat(data["stat"].encode()))
    for name in ("net", "mnt"):
        require(type(data[name]) is str and re.fullmatch(name + r":\[[0-9]{1,20}\]", data[name]))
    return canonical({**decoded, **{k: data[k] for k in ("unit_scope", "net", "mnt")}})


class UnsupportedWire(ValueError):
    pass


def supported(value):
    if not value:
        raise UnsupportedWire("UNSUPPORTED_FORMAT")


def expression(value):
    supported(type(value) is dict and len(value) == 1)
    key, body = next(iter(value.items()))
    if key in ("accept", "drop", "return", "continue"):
        supported(body is None)
    elif key == "counter":
        supported(type(body) is dict and set(body) == {"packets", "bytes"})
        supported(all(integer(v, 0, 2**64 - 1) for v in body.values()))
        return {"counter": {"packets": 0, "bytes": 0}}
    elif key == "match":
        supported(type(body) is dict and set(body) == {"op", "left", "right"})
        supported(type(body["op"]) is str and body["op"] in ("==", "!=", "<", ">", "<=", ">="))
        left = body["left"]
        supported(type(left) is dict and len(left) == 1)
        kind, attrs = next(iter(left.items()))
        supported(kind in ("meta", "ct", "payload") and type(attrs) is dict)
        if kind in ("meta", "ct"):
            supported(set(attrs) == {"key"} and type(attrs["key"]) is str)
            supported(
                attrs["key"]
                in ("mark", "l4proto", "nfproto", "iifname", "oifname", "state", "direction")
            )
        else:
            supported(set(attrs) == {"protocol", "field"})
            supported(attrs["protocol"] in ("ip", "ip6", "tcp", "udp"))
            supported(attrs["field"] in ("saddr", "daddr", "sport", "dport", "protocol", "nexthdr"))
        right = body["right"]
        supported((type(right) is str and 0 < len(right) <= 128) or integer(right, 0, 2**64 - 1))
    else:
        raise UnsupportedWire("UNSUPPORTED_FORMAT")
    return value


def decode_nft(raw, spec):
    data = strict_json(raw)
    require(type(data) is dict and set(data) == {"nftables"})
    objects = data["nftables"]
    require(type(objects) is list and 1 <= len(objects) <= 1024)
    result = []
    tables, chains, rule_chains = 0, set(), []
    family, table = spec.target
    for item in objects:
        supported(type(item) is dict and len(item) == 1)
        kind, attrs = next(iter(item.items()))
        supported(type(attrs) is dict)
        if kind == "metainfo":
            supported(
                not result and set(attrs) == {"version", "release_name", "json_schema_version"}
            )
            supported(
                type(attrs["json_schema_version"]) is int and attrs["json_schema_version"] == 1
            )
            supported(
                all(
                    type(attrs[k]) is str and len(attrs[k]) <= 128
                    for k in ("version", "release_name")
                )
            )
            # Library metadata is not rule state. Supported schema checked above.
            continue
        supported(kind in ("table", "chain", "rule"))
        supported(attrs.get("family") == family)
        supported(attrs.get("name" if kind == "table" else "table") == table)
        allowed = (
            {"family", "name", "handle"}
            if kind == "table"
            else (
                {"family", "table", "name", "handle", "type", "hook", "prio", "policy"}
                if kind == "chain"
                else {"family", "table", "chain", "handle", "expr", "comment"}
            )
        )
        supported(set(attrs) <= allowed)
        if "handle" in attrs:
            supported(integer(attrs["handle"], 0, 2**64 - 1))
        if kind == "table":
            tables += 1
        elif kind == "chain":
            name = attrs.get("name")
            supported(type(name) is str and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name))
            supported(name not in chains)
            chains.add(name)
            base = {"type", "hook", "prio", "policy"}
            supported(not (base & set(attrs)) or base <= set(attrs))
            if base <= set(attrs):
                supported(attrs["type"] in ("filter", "nat", "route"))
                supported(
                    attrs["hook"]
                    in (
                        "prerouting",
                        "input",
                        "forward",
                        "output",
                        "postrouting",
                        "ingress",
                        "egress",
                    )
                )
                supported(integer(attrs["prio"], -(2**31), 2**31 - 1))
                supported(attrs["policy"] in ("accept", "drop"))
        else:
            supported(type(attrs.get("chain")) is str)
            rule_chains.append(attrs["chain"])
            supported(type(attrs.get("expr")) is list and 1 <= len(attrs["expr"]) <= 64)
            if "comment" in attrs:
                supported(type(attrs["comment"]) is str and len(attrs["comment"]) <= 128)
            attrs = {**attrs, "expr": [expression(e) for e in attrs["expr"]]}
        # Handle remains significant in AQ1; never sort/reorder rule objects.
        result.append({kind: attrs})
    supported(tables == 1 and all(chain in chains for chain in rule_chains))
    return canonical({"nftables": result})


def decode(spec, result):
    require(type(spec) is SourceSpec and type(result) is SourceResult)
    spec.__post_init__()
    result.__post_init__()
    if result.collection != "COMPLETE":
        return Decoded("INVALID", reason="COLLECTION_INCOMPLETE")
    try:
        parser = {"UNIT": decode_unit, "NFT_TABLE": decode_nft, "PROCESS": decode_process}.get(
            spec.source_id
        )
        raw = parser(result.raw, spec) if parser else decode_context(result.raw)
        return Decoded("COMPLETE", raw, "OBSERVED")
    except UnsupportedWire:
        return Decoded("UNSUPPORTED")
    except (ObservationRefused, ValueError, UnicodeError, TypeError, OverflowError):
        return Decoded("INVALID", reason="INVALID_PAYLOAD")


@dataclass(frozen=True)
class FixtureBackend:
    entries: tuple

    def __post_init__(self):
        require(
            type(self) is FixtureBackend and type(self.entries) is tuple and len(self.entries) <= 32
        )
        keys = []
        for row in self.entries:
            require(type(row) is tuple and len(row) == 3)
            scope, phase, result = row
            require(type(scope) is str and scope in SCOPES and phase in PHASES)
            require(type(result) is SourceResult)
            result.__post_init__()
            keys.append((scope, phase))
        require(len(keys) == len(set(keys)))

    def capture(self, scope, phase):
        self.__post_init__()
        spec_for(scope)
        require(type(phase) is str and phase in PHASES)
        return next((r for s, p, r in self.entries if (s, p) == (scope, phase)), SourceResult())


class LinuxReadonlyBackend:
    """Closed host boundary. No token/string/JSON can authorize this candidate."""

    def __init__(self, policy):
        require(type(self) is LinuxReadonlyBackend and type(policy) is CapturePolicy)
        self.policy = policy

    def capture(self, scope, phase):
        spec_for(scope)
        require(type(phase) is str and phase in PHASES)
        return SourceResult(collection="BLOCKED_SCOPE_REVIEW", reason="BLOCKED_SCOPE_REVIEW")


def proposed_argv(spec, executable):
    """Pure argv compiler. Never search PATH, spawn, or add a caller-supplied target."""
    require(type(spec) is SourceSpec and type(executable) is str)
    spec.__post_init__()
    require(
        executable in (("/usr/bin/systemctl",) if spec.source_id == "UNIT" else ("/usr/sbin/nft",))
    )
    if spec.source_id == "UNIT":
        return (
            executable,
            "--no-pager",
            "--no-ask-password",
            "show",
            *("--property=" + key for key in PROPERTIES),
            spec.target[0],
        )
    require(spec.source_id == "NFT_TABLE")
    return (executable, "-j", "-t", "list", "table", *spec.target)


class ProposedTransport:
    """Unwired bounded transport building block, not an enabled host collector.

    Only private helper tests may supply a fake transport. The closed backend above
    does not call this class. Executable metadata and whole-profile review remain gates.
    """

    def __init__(self, policy):
        require(type(policy) is CapturePolicy)
        self.policy = policy
        self.used = 0
        self.started = None
        self.children = 0
        self.cleanup_confirmed = True

    def query(self, spec, executable):
        argv = proposed_argv(spec, executable)
        require(self.cleanup_confirmed)
        now = time.monotonic()
        if self.started is None:
            self.started = now
        left = self.policy.total_seconds - (now - self.started)
        if left <= 0 or self.children >= 9 or self.used >= self.policy.total_bytes:
            return SourceResult(collection="BUDGET", reason="BUDGET")
        # Candidate path policy: no symlink final component, root-owned, not writable
        # by group/other. Full ancestor/mount/loaded-exec attestation is NOT claimed.
        try:
            info = os.lstat(executable)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
            child = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=True,
                env={
                    "PATH": "/usr/sbin:/usr/bin",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "SYSTEMD_PAGER": "cat",
                    "SYSTEMD_COLORS": "0",
                },
            )
        except (OSError, ObservationRefused):
            return SourceResult(collection="ERROR", reason="QUERY_FAILED")
        self.children += 1
        deadline = now + min(left, self.policy.child_seconds)
        output = {"out": bytearray(), "err": bytearray()}
        selector = selectors.DefaultSelector()
        status = "COMPLETE"
        rc = None
        try:
            for stream, name in ((child.stdout, "out"), (child.stderr, "err")):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = "TIMEOUT"
                    break
                for key, _ in selector.select(min(remaining, 0.05)):
                    cap = (
                        self.policy.stdout_bytes if key.data == "out" else self.policy.stderr_bytes
                    )
                    room = min(cap - len(output[key.data]), self.policy.total_bytes - self.used)
                    chunk = os.read(key.fileobj.fileno(), min(8192, room + 1))
                    self.used += len(chunk)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(chunk) > room:
                        status = "OUTPUT_LIMIT"
                        break
                    else:
                        output[key.data].extend(chunk)
                if status != "COMPLETE":
                    break
            if status == "COMPLETE":
                try:
                    rc = child.wait(timeout=max(0.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    status = "TIMEOUT"
        finally:
            selector.close()
            # Popen's unreaped child PID stays owned; no service PID/name/group kill.
            if child.poll() is None:
                try:
                    child.kill()
                except OSError:
                    self.cleanup_confirmed = False
            try:
                rc = child.wait(timeout=0.2)
            except (OSError, subprocess.TimeoutExpired):
                self.cleanup_confirmed = False
            for stream in (child.stdout, child.stderr):
                stream.close()
        if not self.cleanup_confirmed:
            return SourceResult(
                collection="ERROR", rc=rc, reason="CLEANUP_UNCONFIRMED", cleanup_confirmed=False
            )
        if status != "COMPLETE":
            return SourceResult(collection=status, rc=rc, reason=status)
        if rc != 0 or not output["out"]:
            return SourceResult(collection="ERROR", rc=rc, reason="QUERY_FAILED")
        return SourceResult("COMPLETE", bytes(output["out"]), rc, "OBSERVED")
