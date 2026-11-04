"""AQ: wire adapters and session provenance, offline only; host scope blocked."""

import hashlib
import importlib
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

NOTES = Path.home() / "xgw-w3aq"
AK_SHA = "927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = '974d03a8a31750a365887c85745b227ce493f62ec4deed203b2744b950e68b4d'
UNITS_SHA = "373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4"
SURFACE_SHA = "8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe"
LEGACY_SHA = "2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5"
LEGACY_COMMIT = "63c9c413930eb348d46b2ff986bef46dd2e423d4"

GROUPS = {
    "J": (
        "VALID",
        "DUP",
        "NAN",
        "INFINITY",
        "OVERFLOW",
        "DEPTH",
        "CAP",
        "UTF8",
        "TRUNCATED",
        "NEGATIVE_DEPTH",
    ),
    "U": (
        "ACTIVE",
        "INACTIVE",
        "NOTFOUND",
        "MISSING",
        "EXTRA",
        "DUP",
        "FOREIGN",
        "PID_NEGATIVE",
        "PID_OVERFLOW",
        "MULTILINE",
        "LOAD",
        "ACTIVE_BAD",
    ),
    "P": (
        "COMM",
        "ZERO",
        "MISSING",
        "SHORT",
        "START_NEGATIVE",
        "START_OVERFLOW",
        "UNIT",
        "NAMESPACE",
        "UTF8",
        "STATE",
    ),
    "N": (
        "TABLE",
        "RULE",
        "COUNTER",
        "ORDER",
        "VERSION",
        "FOREIGN",
        "EXPR",
        "SET",
        "FLAGS",
        "CHAIN",
        "EXTRA",
        "BOOL_HANDLE",
        "DUP_TABLE",
        "EMPTY_EXPR",
        "TRUNCATED",
    ),
    "S": (
        "MATCH",
        "MISMATCH",
        "EXPECTED_MISSING",
        "FOREIGN",
        "CLONE",
        "STALE",
        "CONTEXT_DRIFT",
        "NO_FINAL",
        "UNIT_DRIFT",
        "PROCESS_UNBOUND",
        "PROCESS_BOUND",
        "POLICY",
        "BACKEND",
        "SHADOW",
        "VALIDATOR",
        "EXPECTED_CLONE",
        "EXPECTED_MUTATE",
        "EVIDENCE_MUTATE",
        "NESTED",
        "DUP_COLLECT",
        "FINAL_TWICE",
        "CLOCK_REVERSE",
    ),
    "B": (
        "OUTPUT",
        "TOTAL",
        "DEADLINE",
        "AGE",
        "BOOL",
        "NEGATIVE",
        "ZERO",
        "MANY",
        "CLEANUP",
        "HOST",
    ),
    "I": (
        "PROJECTION",
        "IMPORT",
        "IMPORT_AUTH",
        "DICT",
        "AGGREGATE",
        "RUNTIME",
        "ARGV",
        "CONSTRUCTOR",
        "PROPOSED_PROC",
        "PID_ZERO",
        "PID_MISMATCH",
        "PROFILE_CLEANUP",
    ),
}
EXPECTED = tuple(g + "_" + v for g, values in GROUPS.items() for v in values)
DETAIL_KEYS = (
    "decision",
    "provenance",
    "collection",
    "decode",
    "reason",
    "context_valid",
    "runtime_authorized",
    "verification_accepted",
    "scope_matches",
    "public_fields",
    "host_reads",
    "child_queries",
    "cleanup_confirmed",
)
BOOL_KEYS = {"context_valid", "runtime_authorized", "verification_accepted", "cleanup_confirmed"}
ENUM_KEYS = {"decision", "provenance", "collection", "decode", "reason"}
INT_KEYS = set(DETAIL_KEYS) - BOOL_KEYS - ENUM_KEYS
DECISIONS = {"MATCH", "MISMATCH", "UNKNOWN", "UNSUPPORTED"}
ENUMS = {
    "decision": DECISIONS,
    "provenance": {"FIXTURE", "SESSION_CAPTURED", "IMPORTED_UNTRUSTED"},
    "collection": {
        "COMPLETE",
        "NOT_COLLECTED",
        "TIMEOUT",
        "ERROR",
        "OUTPUT_LIMIT",
        "BUDGET",
        "BLOCKED_SCOPE_REVIEW",
        "INCONSISTENT",
    },
    "decode": {"COMPLETE", "UNSUPPORTED", "INVALID"},
    "reason": {
        "OBSERVED",
        "SOURCE_NOT_COLLECTED",
        "QUERY_FAILED",
        "TIMEOUT",
        "OUTPUT_LIMIT",
        "BUDGET",
        "BLOCKED_SCOPE_REVIEW",
        "CLEANUP_UNCONFIRMED",
        "CONTEXT_CHANGED",
        "UNSUPPORTED_FORMAT",
        "INVALID_PAYLOAD",
        "ABSENCE_UNPROVEN",
        "EXPECTED_MISSING",
        "SCOPED_MATCH",
        "SCOPED_MISMATCH",
        "PROVENANCE_UNBOUND",
        "BINDING_CHANGED",
        "EVIDENCE_STALE",
        "CLOCK_INVALID",
        "COLLECTION_INCOMPLETE",
        "COVERAGE_INCOMPLETE",
        "PROCESS_UNBOUND",
        "PID_NOT_PRESENT",
        "PERMISSION_DENIED",
        "IMPORT_UNTRUSTED",
    },
}
SUPPORT = AK = DETAILS = None
M = {}
UNITS = {}


class TargetRestoreStop(Exception):
    pass


def require(value, reason):
    if not value:
        raise ValueError(reason)


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
    private(NOTES / "ak.py")
    require(hashlib.sha256((NOTES / "ak.py").read_bytes()).hexdigest() == AK_SHA, "AK_SHA")
    spec = importlib.util.spec_from_file_location("aq_pinned_ak", NOTES / "ak.py")
    AK = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(AK)
    AK.NOTES, AK.MANIFEST_SHA = NOTES, MANIFEST_SHA
    count = AK.bootstrap()
    SUPPORT, UNITS = AK.SUPPORT, AK.UNITS
    return count


def source():
    global M
    AK.source()
    M = AK.M
    for name in (
        "ownership_observations",
        "ownership_observation_sources",
        "ownership_observation_compare",
    ):
        M[name] = importlib.import_module("frozen_ad." + name)


def modules():
    return tuple(
        M[n]
        for n in (
            "ownership_observations",
            "ownership_observation_sources",
            "ownership_observation_compare",
        )
    )


def baseline():
    rows = []
    for module in modules():
        for name, value in vars(module).items():
            if type(value) is FunctionType and value.__module__ == module.__name__:
                rows.append(
                    (module, name, value, value.__code__, value.__defaults__, value.__kwdefaults__)
                )
            elif isinstance(value, type) and value.__module__ == module.__name__:
                for key, fn in vars(value).items():
                    if type(fn) is FunctionType:
                        rows.append(
                            (value, key, fn, fn.__code__, fn.__defaults__, fn.__kwdefaults__)
                        )
    return tuple(rows)


def reject(fn):
    try:
        fn()
    except (ValueError, TypeError):
        return
    raise AssertionError("EXPECTED_REFUSAL")


def unit_raw(**kw):
    row = dict(
        Id="xgw.service",
        LoadState="loaded",
        ActiveState="active",
        SubState="running",
        MainPID="123",
    )
    row.update(kw)
    return ("\n".join(k + "=" + v for k, v in row.items()) + "\n").encode()


def stat_raw(comm="a ) name ( x", pid=123, start=77):
    fields = ["0"] * 49
    fields[18] = str(start)
    return (str(pid) + " (" + comm + ") S " + " ".join(fields) + "\n").encode()


def context_raw(boot="11111111-1111-1111-1111-111111111111"):
    t, _, _ = modules()
    return t.canonical(dict(boot=boot, net="net:[1]", mnt="mnt:[2]"))


def process_raw(**kw):
    t, _, _ = modules()
    row = dict(unit_scope="UNIT_XGW", stat=stat_raw().decode(), net="net:[1]", mnt="mnt:[2]")
    row.update(kw)
    return t.canonical(row)


def nft_data():
    return {
        "nftables": [
            {"metainfo": {"version": "1.1.0", "release_name": "fixture", "json_schema_version": 1}},
            {"table": {"family": "ip", "name": "xgw", "handle": 1}},
            {
                "chain": {
                    "family": "ip",
                    "table": "xgw",
                    "name": "input",
                    "handle": 2,
                    "type": "filter",
                    "hook": "input",
                    "prio": 0,
                    "policy": "accept",
                }
            },
            {
                "rule": {
                    "family": "ip",
                    "table": "xgw",
                    "chain": "input",
                    "handle": 3,
                    "expr": [{"counter": {"packets": 123, "bytes": 456}}, {"accept": None}],
                }
            },
        ]
    }


def complete(raw):
    t, _, _ = modules()
    return t.SourceResult("COMPLETE", raw, 0, "OBSERVED")


def session_fixture(*, context_after=None, unit_after=None, process=False, **kw):
    t, s, c = modules()
    rows = [
        ("COLLECTOR_CONTEXT", "BEFORE", complete(context_raw())),
        ("COLLECTOR_CONTEXT", "AFTER", complete(context_after or context_raw())),
        ("UNIT_XGW", "BEFORE", complete(unit_raw())),
        ("UNIT_XGW", "AFTER", complete(unit_after or unit_raw())),
        ("NFT_IPV4", "SINGLE", complete(t.canonical(nft_data()))),
    ]
    if process:
        rows += [("PROCESS_XGW", p, complete(process_raw())) for p in ("BEFORE", "AFTER")]
    exp = c.ExpectedState("NFT_IPV4", s.decode_nft(t.canonical(nft_data()), s.spec_for("NFT_IPV4")))
    kw.setdefault("clock_values", tuple(i / 1000 for i in range(256)))
    kw.setdefault("expected_states", (exp,))
    session = c.ReadonlyObservationSession(t.CapturePolicy(), s.FixtureBackend(tuple(rows)), **kw)
    return session, exp


def collect_fixture(session, *, finalize=True, process=False):
    session.collect_once("COLLECTOR_CONTEXT", "BEFORE")
    session.collect_once("UNIT_XGW", "BEFORE")
    if process:
        session.collect_once("PROCESS_XGW", "BEFORE")
    evidence = session.collect_once("NFT_IPV4")
    if process:
        session.collect_once("PROCESS_XGW", "AFTER")
    session.collect_once("UNIT_XGW", "AFTER")
    session.collect_once("COLLECTOR_CONTEXT", "AFTER")
    if finalize:
        DETAILS["context_valid"] = session.finalize()
    return evidence


def record(d):
    t, _, _ = modules()
    row = t.project_public(d)
    DETAILS.update({k: row[k] for k in ENUM_KEYS | {"runtime_authorized"}})
    DETAILS["public_fields"] = len(row)


def json_case(name):
    t, _, _ = modules()
    raw = {
        "VALID": b'{"a":[1,true,null]}',
        "DUP": b'{"a":1,"a":2}',
        "NAN": b"NaN",
        "INFINITY": b"Infinity",
        "OVERFLOW": b"1e999",
        "DEPTH": b"[" * 33 + b"0" + b"]" * 33,
        "CAP": b" " * 8193,
        "UTF8": b'"\xff"',
        "TRUNCATED": b"{",
        "NEGATIVE_DEPTH": b"]",
    }[name]
    if name == "VALID":
        require(t.strict_json(raw) == {"a": [1, True, None]}, "JSON_VALID")
    else:
        reject(lambda: t.strict_json(raw, cap=8192))


def unit_case(name):
    t, s, _ = modules()
    raw = unit_raw()
    if name in ("INACTIVE", "NOTFOUND"):
        raw = unit_raw(
            ActiveState="inactive",
            SubState="dead",
            MainPID="0",
            LoadState="not-found" if name == "NOTFOUND" else "loaded",
        )
    elif name == "MISSING":
        raw = raw.replace(b"SubState=running\n", b"")
    elif name == "EXTRA":
        raw += b"Environment=forbidden\n"
    elif name == "DUP":
        raw += b"MainPID=123\n"
    elif name == "FOREIGN":
        raw = unit_raw(Id="other.service")
    elif name == "PID_NEGATIVE":
        raw = unit_raw(MainPID="-1")
    elif name == "PID_OVERFLOW":
        raw = unit_raw(MainPID="9999999999")
    elif name == "MULTILINE":
        raw += b"private text\n"
    elif name == "LOAD":
        raw = unit_raw(LoadState="unknown-future")
    elif name == "ACTIVE_BAD":
        raw = unit_raw(ActiveState="unknown-future")
    d = s.decode(s.spec_for("UNIT_XGW"), complete(raw))
    DETAILS["decode"] = d.status
    require((d.status == "COMPLETE") == (name in ("ACTIVE", "INACTIVE", "NOTFOUND")), "UNIT_DECODE")
    if name in ("INACTIVE", "NOTFOUND"):
        require(t.strict_json(d.canonical)["MainPID"] == 0, "PID_ZERO_NOT_ABSENCE")


def process_case(name):
    _, s, _ = modules()
    if name == "COMM":
        require(b'"starttime":77' in s.decode_stat(stat_raw()), "STAT_COMM")
        return
    raw = stat_raw()
    if name == "ZERO":
        raw = stat_raw(pid=0)
    elif name == "MISSING":
        raw = b""
    elif name == "SHORT":
        raw = b"123 (a) S 0 0"
    elif name == "START_NEGATIVE":
        raw = stat_raw(start=-1)
    elif name == "START_OVERFLOW":
        raw = stat_raw(start=2**64)
    elif name == "UTF8":
        raw = b"\xff"
    elif name == "STATE":
        raw = raw.replace(b") S ", b") Q ")
    if name in ("UNIT", "NAMESPACE"):
        raw = process_raw(
            **({"unit_scope": "UNIT_XRAY"} if name == "UNIT" else {"net": "arbitrary"})
        )
        d = s.decode(s.spec_for("PROCESS_XGW"), complete(raw))
        require(d.status == "INVALID", "PROCESS_ENVELOPE")
    else:
        reject(lambda: s.decode_stat(raw))


def nft_case(name):
    t, s, _ = modules()
    data = nft_data()
    rows = data["nftables"]
    if name == "TABLE":
        data["nftables"] = rows[:2]
    elif name == "VERSION":
        rows[0]["metainfo"]["json_schema_version"] = 2
    elif name == "FOREIGN":
        rows[1]["table"]["name"] = "foreign"
    elif name == "EXPR":
        rows[3]["rule"]["expr"] = [{"future": None}]
    elif name == "SET":
        rows.append({"set": {"family": "ip", "table": "xgw", "name": "unqualified"}})
    elif name == "FLAGS":
        rows[1]["table"]["flags"] = ["owner"]
    elif name == "CHAIN":
        rows[3]["rule"]["chain"] = "missing"
    elif name == "EXTRA":
        data["extra"] = True
    elif name == "BOOL_HANDLE":
        rows[1]["table"]["handle"] = True
    elif name == "DUP_TABLE":
        rows.append(rows[1])
    elif name == "EMPTY_EXPR":
        rows[3]["rule"]["expr"] = []
    raw = t.canonical(data)
    if name == "TRUNCATED":
        raw = raw[:-2]
    d = s.decode(s.spec_for("NFT_IPV4"), complete(raw))
    DETAILS["decode"] = d.status
    if name in ("TABLE", "RULE", "COUNTER", "ORDER"):
        require(d.status == "COMPLETE", "NFT_SUPPORTED_SUBSET")
        if name == "COUNTER":
            rows[3]["rule"]["expr"][0]["counter"]["packets"] += 1
            require(
                s.decode_nft(t.canonical(data), s.spec_for("NFT_IPV4")) == d.canonical,
                "COUNTER_VOLATILE",
            )
        if name == "ORDER":
            rows[3]["rule"]["expr"].reverse()
            require(
                s.decode_nft(t.canonical(data), s.spec_for("NFT_IPV4")) != d.canonical,
                "ORDER_PRESERVED",
            )
    else:
        require(d.status != "COMPLETE", "NFT_REFUSE")


def session_case(name):
    import dataclasses

    t, s, c = modules()
    options = {}
    if name == "CONTEXT_DRIFT":
        options["context_after"] = context_raw("22222222-2222-2222-2222-222222222222")
    if name == "UNIT_DRIFT":
        options["unit_after"] = unit_raw(MainPID="124")
    session, exp = session_fixture(**options)
    if name == "PROCESS_BOUND":
        session, exp = session_fixture(process=True)
    if name == "CLOCK_REVERSE":
        session, exp = session_fixture(clock_values=(1.0, 0.0))
        reject(lambda: session.collect_once("COLLECTOR_CONTEXT", "BEFORE"))
        return
    ev = collect_fixture(session, finalize=name != "NO_FINAL", process=name == "PROCESS_BOUND")
    if name == "POLICY":
        session.policy = t.CapturePolicy()
    elif name == "BACKEND":
        session.backend = s.FixtureBackend(())
    elif name == "SHADOW":
        session._validate = lambda: None
    elif name == "VALIDATOR":
        original = c.ReadonlyObservationSession._validate
        c.ReadonlyObservationSession._validate = lambda self: None
        try:
            reject(lambda: session.compare_scoped(ev, exp))
        finally:
            c.ReadonlyObservationSession._validate = original
        return
    elif name == "EXPECTED_CLONE":
        exp = dataclasses.replace(exp)
    elif name == "EXPECTED_MUTATE":
        object.__setattr__(exp, "origin", "DECLARED")
    elif name == "EVIDENCE_MUTATE":
        object.__setattr__(ev.decoded, "canonical", b"{}")
    elif name == "CLONE":
        ev = dataclasses.replace(ev)
    elif name == "FOREIGN":
        session, exp = session_fixture()
        collect_fixture(session)
    elif name == "STALE":
        # Use a separately constructed session with a true late clock sample.
        session, exp = session_fixture(clock_values=tuple([0.0] * 10 + [31.0]))
        ev = collect_fixture(session)
    elif name == "MISMATCH":
        exp2 = c.ExpectedState("NFT_IPV4", b"{}")
        session, _ = session_fixture(expected_states=(exp2,))
        exp, ev = exp2, collect_fixture(session)
    elif name == "PROCESS_UNBOUND":
        rows = [("COLLECTOR_CONTEXT", p, complete(context_raw())) for p in ("BEFORE", "AFTER")]
        rows += [("PROCESS_XGW", p, complete(process_raw())) for p in ("BEFORE", "AFTER")]
        session = c.ReadonlyObservationSession(t.CapturePolicy(), s.FixtureBackend(tuple(rows)))
        session.collect_once("COLLECTOR_CONTEXT", "BEFORE")
        ev = session.collect_once("PROCESS_XGW", "BEFORE")
        session.collect_once("PROCESS_XGW", "AFTER")
        session.collect_once("COLLECTOR_CONTEXT", "AFTER")
        require(session.finalize() is False, "PROCESS_REQUIRES_UNIT")
    elif name == "NESTED":
        session, exp = session_fixture()
        session._busy = True
        reject(lambda: session.collect_once("NFT_IPV4"))
        return
    elif name == "DUP_COLLECT":
        session, exp = session_fixture()
        session.collect_once("NFT_IPV4")
        reject(lambda: session.collect_once("NFT_IPV4"))
        return
    elif name == "FINAL_TWICE":
        reject(session.finalize)
        return
    if name in ("POLICY", "BACKEND", "SHADOW"):
        reject(lambda: session.compare_scoped(ev, exp))
        return
    d = session.compare_scoped(ev, None if name == "EXPECTED_MISSING" else exp)
    record(d)
    expected = (
        "MATCH"
        if name in ("MATCH", "PROCESS_BOUND")
        else "MISMATCH"
        if name == "MISMATCH"
        else "UNKNOWN"
    )
    require(d.decision == expected and not d.runtime_authorized, "SESSION_DECISION")


def budget_case(name):
    t, s, c = modules()
    if name in ("BOOL", "NEGATIVE", "ZERO", "AGE"):
        value = {"BOOL": True, "NEGATIVE": -1, "ZERO": 0, "AGE": 31}[name]
        reject(lambda: t.CapturePolicy(max_age_seconds=value))
        return
    if name == "MANY":
        reject(
            lambda: s.FixtureBackend(
                tuple(("NFT_IPV4", "SINGLE", complete(b"{}")) for _ in range(33))
            )
        )
        return
    if name == "HOST":
        policy = t.CapturePolicy()
        backend = s.LinuxReadonlyBackend(policy)
        for scope in t.SCOPES:
            require(
                backend.capture(scope, "SINGLE").collection == "BLOCKED_SCOPE_REVIEW", "HOST_CLOSED"
            )
        DETAILS.update(host_reads=0, child_queries=0)
        return
    raw = t.canonical(nft_data())
    policy = (
        t.CapturePolicy(stdout_bytes=8)
        if name == "OUTPUT"
        else (t.CapturePolicy(total_bytes=8) if name == "TOTAL" else t.CapturePolicy())
    )
    result = (
        t.SourceResult(collection="ERROR", reason="CLEANUP_UNCONFIRMED", cleanup_confirmed=False)
        if name == "CLEANUP"
        else complete(raw)
    )
    session = c.ReadonlyObservationSession(
        policy,
        s.FixtureBackend((("NFT_IPV4", "SINGLE", result),)),
        clock_values=(0.0, 31.0) if name == "DEADLINE" else (0.0, 0.1),
    )
    ev = session.collect_once("NFT_IPV4")
    require(
        ev.result.collection
        == ("BUDGET" if name == "DEADLINE" else "ERROR" if name == "CLEANUP" else "OUTPUT_LIMIT"),
        "BUDGET_RESULT",
    )
    DETAILS.update(collection=ev.result.collection, cleanup_confirmed=ev.result.cleanup_confirmed)
    if name == "CLEANUP":
        reject(session.finalize)


def integration(name):
    t, s, c = modules()
    if name in ("PROPOSED_PROC", "PID_ZERO", "PID_MISMATCH", "PROFILE_CLEANUP"):
        transport = s.ProposedTransport(t.CapturePolicy())
        transport._proc_stream = lambda path: (
            b"11111111-1111-1111-1111-111111111111\n"
            if path.endswith("boot_id")
            else stat_raw(pid=124 if name == "PID_MISMATCH" else 123)
        )
        transport._namespace = lambda pid, kind: kind + ":[1]"
        if name == "PROPOSED_PROC":
            require(transport.proc_context().collection == "COMPLETE", "CONTEXT_ASSEMBLY")
            result = transport.proc_process(s.spec_for("UNIT_XGW"), complete(unit_raw()))
            require(result.collection == "COMPLETE", "PROC_ASSEMBLY")
        elif name == "PID_ZERO":

            def forbidden(*args):
                raise AssertionError("PID0_READ")

            transport._proc_stream = forbidden
            result = transport.proc_process(s.spec_for("UNIT_XGW"), complete(unit_raw(MainPID="0")))
            require(result.reason == "PID_NOT_PRESENT", "PID0_UNOBSERVED")
        elif name == "PID_MISMATCH":
            result = transport.proc_process(s.spec_for("UNIT_XGW"), complete(unit_raw()))
            require(
                result.collection == "ERROR" and result.reason == "INVALID_PAYLOAD", "PID_BOUND"
            )
        else:
            calls = []
            transport.proc_context = lambda: complete(context_raw())

            def query(spec, executable):
                calls.append(spec.scope_id)
                transport.cleanup_confirmed = False
                return t.SourceResult(
                    collection="ERROR", reason="CLEANUP_UNCONFIRMED", cleanup_confirmed=False
                )

            transport.query = query
            require(
                len(s.proposed_profile(transport)) == 2 and calls == ["UNIT_XGW"], "PROFILE_STOP"
            )
        return
    if name == "ARGV":
        for scope, exe in (("UNIT_XGW", "/usr/bin/systemctl"), ("NFT_IPV4", "/usr/sbin/nft")):
            argv = s.proposed_argv(s.spec_for(scope), exe)
            require(
                type(argv) is tuple and "show" in argv if scope == "UNIT_XGW" else "list" in argv,
                "ARGV_FIXED",
            )
        reject(lambda: s.proposed_argv(s.spec_for("NFT_IPV4"), "/tmp/nft"))
        return
    if name == "CONSTRUCTOR":
        original = os.open

        def forbidden(*args, **kwargs):
            raise AssertionError("CONSTRUCTOR_IO")

        os.open = forbidden
        try:
            session, exp = session_fixture()
            require(not session.runtime_verification().accepted(), "PURE_RUNTIME")
        finally:
            os.open = original
        return
    session, exp = session_fixture()
    ev = collect_fixture(session)
    d = session.compare_scoped(ev, exp)
    record(d)
    row = t.project_public(d)
    if name == "PROJECTION":
        require(len(row) == 12 and "raw" not in row and row["source_rc"] == 0, "PROJECTION")
    elif name == "DICT":
        reject(lambda: t.project_public(dict(row)))
    elif name in ("IMPORT", "IMPORT_AUTH"):
        if name == "IMPORT_AUTH":
            row["runtime_authorized"] = True
            reject(lambda: c.imported_evidence(t.canonical(row)))
        else:
            imported = c.imported_evidence(t.canonical(row))
            record(imported)
            require(
                imported.provenance == "IMPORTED_UNTRUSTED" and imported.decision == "UNKNOWN",
                "NO_IMPORT_AUTHORITY",
            )
    elif name == "AGGREGATE":
        require(
            c.aggregate_scoped((d,))[:2] == ("UNKNOWN", "COVERAGE_INCOMPLETE"), "NOT_GLOBAL_MATCH"
        )
    elif name == "RUNTIME":
        DETAILS["verification_accepted"] = session.runtime_verification().accepted()
        require(DETAILS["verification_accepted"] is False, "NO_RUNTIME_VERIFICATION")


def run_case(f, name):
    group, variant = name.split("_", 1)
    DETAILS.update(host_reads=0, child_queries=0)
    {
        "J": json_case,
        "U": unit_case,
        "P": process_case,
        "N": nft_case,
        "S": session_case,
        "B": budget_case,
        "I": integration,
    }[group](variant)


FLAGS = (
    "installed_runtime_changed",
    "runtime_actor_binding_implemented",
    "runtime_writer_fence_verified",
    "runtime_verifier_implemented",
    "runtime_recovery_implemented",
    "repair_implemented",
    "active_faults_authorized",
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
    SUPPORT.atomic("progress.json", {"final": False, "completed": 0, "cases": []})
    source_count = SUPPORT.verify_source()
    source()
    original_baseline = baseline()
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
            try:
                run_case(f, name)
            finally:
                if baseline() != original_baseline:
                    raise TargetRestoreStop("AQ_BASELINE_CHANGED")
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
                        "batch.py": "wave3_observation_batch.py",
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
                "reason": "READONLY_OBSERVATIONS_CASE_FAILED",
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
        "marker": "READONLY_OBSERVATIONS_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "READONLY_OBSERVATIONS_BATCH_PARTIAL",
        "scope": "OFFLINE_OBSERVATION_QUALIFICATION_HOST_BLOCKED",
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
            and data.get("scope") == "OFFLINE_OBSERVATION_QUALIFICATION_HOST_BLOCKED"
            and data.get("marker")
            in ("READONLY_OBSERVATIONS_BATCH_RECORDED", "READONLY_OBSERVATIONS_BATCH_PARTIAL"),
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
        "# Отчёт: XGW wave3aq — readonly adapters and session provenance",
        "",
        "Автоматические exact данные; таблицу не редактировать. worker_exit_rc=NOT_COLLECTED.",
        "Offline wire fixtures only; HOST_NOT_RUN/BLOCKED_SCOPE_REVIEW; runtime unchanged.",
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
        require(d["decision"] is None or d["decision"] in DECISIONS, "DETAIL_DECISION")
        for key, values in ENUMS.items():
            require(d[key] is None or (type(d[key]) is str and d[key] in values), "DETAIL_ENUM")
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
                "tests/stand/wave3_observation_batch.py",
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
    print("READONLY_OBSERVATIONS_REPORT_READY")


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
            print("READONLY_OBSERVATIONS_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception:
        print("READONLY_OBSERVATIONS_BATCH_STOP", "LOCAL_IO_OR_SCHEMA_ERROR")
        raise SystemExit(3) from None
