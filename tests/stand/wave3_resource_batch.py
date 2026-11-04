"""AP: pure resource contracts, simulation comparison and dry bootstrap only."""

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
from types import SimpleNamespace

NOTES = Path.home() / "xgw-w3ap"
AK_SHA = "927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = "2abae55ab23815f156bc4628c10d2290fbb02402f175aaf5eda877139b703d9b"
UNITS_SHA = "373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4"
SURFACE_SHA = "8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe"
LEGACY_SHA = "2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5"
LEGACY_COMMIT = "63c9c413930eb348d46b2ff986bef46dd2e423d4"
DOMAINS = ("API", "FILES", "KERNEL", "MARKERS", "MODE", "PROCESSES", "ROUTES")
VARIANTS = (
    "MATCH",
    "MISMATCH",
    "MISSING",
    "TIMEOUT",
    "TRUNCATED",
    "SCHEMA",
    "BINDING",
    "ACTUAL",
    "UNBOUND",
    "DUPLICATE",
    "ABSENCE_BAD",
    "ABSENCE_OK",
    "OPTIONAL",
)
COMPARE = tuple("C_" + d + "_" + v for d in DOMAINS for v in VARIANTS)
POLICY = tuple(
    "P_" + v
    for v in (
        "DOMAIN",
        "ID",
        "EXPECTED",
        "BOOL_REQUIRED",
        "BOOL_ABSENT",
        "EMPTY",
        "LIST",
        "MANY",
        "DUPLICATE",
        "OPTIONAL_ONLY",
        "BINDING",
        "COMPLETENESS",
        "OBS_LIST",
        "OBS_MANY",
        "OBS_TYPE",
        "SCHEMA_BOOL",
        "STATUS",
        "SIM_BOOL",
        "ORIGIN",
        "STATE_TYPE",
    )
)
AGGREGATE = tuple(
    "A_" + v
    for v in (
        "ALL",
        "MISSING",
        "CONFLICT",
        "WRONGTYPE",
        "MISMATCH",
        "ACTUAL",
        "SCHEMA",
        "BINDING",
        "INCOMPLETE",
        "OPTIONAL",
        "EXTRA",
        "LIMIT",
        "EMPTY",
        "MIXED",
    )
)
BOOTSTRAP = tuple(
    "B_" + v
    for v in (
        "READY",
        "NO_FACTS",
        "CODE",
        "CALLER",
        "ACTUAL",
        "LIVE",
        "UNKNOWN_WRITER",
        "BOTH_WRITERS",
        "COUNTS_NONE",
        "COUNTS_PARTIAL",
        "STAGE",
        "ACK",
        "GRAPH",
        "RESCUE",
        "ORIGINAL_ON",
        "FACT_DUP",
        "COUNTS_BAD",
    )
)
CATALOG = tuple(f"T_{i:02d}" for i in range(65))
INTEGRATION = ("I_MATCH", "I_ACTUAL", "I_UNKNOWN", "I_CONSTRUCTOR_IO")
EXPECTED = COMPARE + POLICY + AGGREGATE + BOOTSTRAP + CATALOG + INTEGRATION
DETAIL_KEYS = (
    "decision",
    "checked",
    "required",
    "optional_unmatched",
    "missing_required",
    "blockers",
    "simulation_only",
    "runtime_authorized",
    "verification_accepted",
    "registry_receipts",
    "unknown_writers",
    "writer_total",
    "requirements",
    "completeness",
    "dry_ready",
)
BOOL_KEYS = {"simulation_only", "runtime_authorized", "verification_accepted", "dry_ready"}
INT_KEYS = set(DETAIL_KEYS) - BOOL_KEYS - {"decision", "completeness"}
DECISIONS = {"MATCH", "MISMATCH", "UNKNOWN", "UNSUPPORTED"}
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
    spec = importlib.util.spec_from_file_location("ap_pinned_ak", NOTES / "ak.py")
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
    for name in ("ownership_resources", "ownership_resource_catalog"):
        M[name] = importlib.import_module("frozen_ad." + name)
    require(len(M["ownership_resource_catalog"].ROWS) == 65, "RESOURCE_CATALOG")


def binding():
    return M["ownership_resources"].Binding("code.fixture", "boot.fixture", "context.fixture")


def contract(domain="FILES", **kw):
    r = M["ownership_resources"]
    return r.ResourceContract(
        binding(),
        (r.ResourceRequirement(domain, "item", "expected"),),
        completeness=kw.get("completeness", "DECLARED_COMPLETE"),
    )


def observation(domain="FILES", **kw):
    r = M["ownership_resources"]
    return r.Observation(
        domain,
        kw.pop("binding", binding()),
        kw.pop("states", (r.ResourceState("item", "expected"),)),
        collection_status=kw.pop("collection_status", "COMPLETE"),
        origin=kw.pop("origin", "SIMULATION"),
        **kw,
    )


def record(d):
    DETAILS.update(
        decision=d.status,
        checked=d.checked,
        required=d.required,
        optional_unmatched=d.optional_unmatched,
        simulation_only=d.simulation_only,
        runtime_authorized=d.runtime_completion_authorized,
    )


def compare_case(domain, variant):
    r = M["ownership_resources"]
    c = contract(domain)
    kw = {}
    expected = "UNKNOWN"
    if variant == "MATCH":
        expected = "MATCH"
    elif variant == "MISMATCH":
        kw["states"] = (r.ResourceState("item", "different"),)
        expected = "MISMATCH"
    elif variant == "MISSING":
        kw["states"] = ()
    elif variant in ("TIMEOUT", "TRUNCATED"):
        kw["collection_status"] = variant
    elif variant == "SCHEMA":
        kw["schema_version"] = 2
        expected = "UNSUPPORTED"
    elif variant == "BINDING":
        kw["binding"] = r.Binding("other", "boot.fixture", "context.fixture")
    elif variant == "ACTUAL":
        kw["simulation_only"] = False
        expected = "UNSUPPORTED"
    elif variant == "UNBOUND":
        kw["origin"] = "UNBOUND"
        expected = "UNSUPPORTED"
    elif variant == "DUPLICATE":
        kw["states"] = (r.ResourceState("item", "expected"),) * 2
    elif variant.startswith("ABSENCE"):
        c = r.ResourceContract(
            binding(),
            (r.ResourceRequirement(domain, "item", "expected", expected_absent=True),),
            "DECLARED_COMPLETE",
        )
        kw.update(
            states=(r.ResourceState("item", "expected", True),),
            scope_complete=variant == "ABSENCE_OK",
        )
        expected = "MATCH" if variant == "ABSENCE_OK" else "UNKNOWN"
    elif variant == "OPTIONAL":
        c = r.ResourceContract(
            binding(),
            (
                r.ResourceRequirement(domain, "item", "expected"),
                r.ResourceRequirement(domain, "optional", "expected", False),
            ),
            "DECLARED_COMPLETE",
        )
        expected = "MATCH"
    d = r.compare_observation(c, observation(domain, **kw))
    record(d)
    require(d.status == expected and not d.runtime_completion_authorized, "COMPARISON")
    if variant == "OPTIONAL":
        require(d.optional_unmatched == 1, "OPTIONAL_COUNT")


def policy_case(name):
    r = M["ownership_resources"]
    b = binding()
    req = r.ResourceRequirement("FILES", "item", "expected")

    def rejected(call):
        try:
            call()
        except r.ResourceRefused:
            return
        raise ValueError("EXPECTED_POLICY_REFUSAL")

    calls = {
        "DOMAIN": lambda: r.ResourceRequirement("other", "item", "expected"),
        "ID": lambda: r.ResourceRequirement("FILES", "../item", "expected"),
        "EXPECTED": lambda: r.ResourceRequirement("FILES", "item", ""),
        "BOOL_REQUIRED": lambda: r.ResourceRequirement("FILES", "item", "expected", 1),
        "BOOL_ABSENT": lambda: r.ResourceRequirement(
            "FILES", "item", "expected", expected_absent=1
        ),
        "EMPTY": lambda: r.ResourceContract(b, ()),
        "LIST": lambda: r.ResourceContract(b, [req]),
        "MANY": lambda: r.ResourceContract(b, (req,) * 129),
        "DUPLICATE": lambda: r.ResourceContract(b, (req, req)),
        "OPTIONAL_ONLY": lambda: r.ResourceContract(
            b, (r.ResourceRequirement("FILES", "item", "expected", False),)
        ),
        "BINDING": lambda: r.ResourceContract(object(), (req,)),
        "COMPLETENESS": lambda: r.ResourceContract(b, (req,), "READY"),
        "OBS_LIST": lambda: r.Observation("FILES", b, []),
        "OBS_MANY": lambda: r.Observation("FILES", b, (r.ResourceState("item", "expected"),) * 129),
        "OBS_TYPE": lambda: r.Observation("FILES", b, (object(),)),
        "SCHEMA_BOOL": lambda: r.Observation("FILES", b, schema_version=True),
        "STATUS": lambda: r.Observation("FILES", b, collection_status="OK"),
        "SIM_BOOL": lambda: r.Observation("FILES", b, simulation_only=1),
        "ORIGIN": lambda: r.Observation("FILES", b, origin="TRUSTED"),
        "STATE_TYPE": lambda: r.ResourceState("item", "expected", 1),
    }
    rejected(calls[name])


def aggregate_case(name):
    r = M["ownership_resources"]
    req = (
        r.ResourceRequirement("FILES", "item", "expected"),
        r.ResourceRequirement("API", "item", "expected"),
    )
    c = r.ResourceContract(binding(), req, "DECLARED_COMPLETE")
    obs = (observation("FILES"), observation("API"))
    expected = "MATCH"
    if name in ("MISSING", "EMPTY"):
        obs = obs[:1] if name == "MISSING" else ()
        expected = "UNKNOWN"
    elif name == "CONFLICT":
        obs = (*obs, obs[0])
        expected = "UNKNOWN"
    elif name == "WRONGTYPE":
        obs = (object(),)
        expected = "UNKNOWN"
    elif name == "MISMATCH":
        obs = (observation("FILES", states=(r.ResourceState("item", "wrong"),)), obs[1])
        expected = "MISMATCH"
    elif name == "ACTUAL":
        obs = (observation("FILES", simulation_only=False), obs[1])
        expected = "UNSUPPORTED"
    elif name == "SCHEMA":
        obs = (observation("FILES", schema_version=9), obs[1])
        expected = "UNSUPPORTED"
    elif name == "BINDING":
        obs = (
            observation("FILES", binding=r.Binding("other", "boot.fixture", "context.fixture")),
            obs[1],
        )
        expected = "UNKNOWN"
    elif name == "INCOMPLETE":
        c = r.ResourceContract(binding(), req)
        expected = "UNKNOWN"
    elif name == "OPTIONAL":
        c = r.ResourceContract(
            binding(),
            (req[0], r.ResourceRequirement("API", "item", "expected", False)),
            "DECLARED_COMPLETE",
        )
        obs = obs[:1]
    elif name == "EXTRA":
        obs = (*obs, observation("MODE"))
    elif name == "LIMIT":
        try:
            r.aggregate(c, obs * 8)
        except r.ResourceRefused:
            return
        raise ValueError("AGGREGATE_LIMIT")
    elif name == "MIXED":
        obs = (
            observation("FILES", states=()),
            observation("API", states=(r.ResourceState("item", "wrong"),)),
        )
        expected = "MISMATCH"
    d = r.aggregate(c, obs)
    DETAILS.update(
        decision=d.status,
        missing_required=d.missing_required,
        runtime_authorized=d.runtime_completion_authorized,
        simulation_only=d.simulation_only,
    )
    require(d.status == expected and not d.runtime_completion_authorized, "AGGREGATION")


def inventory(**kw):
    r = M["ownership_resources"]
    b = binding()
    facts = kw.pop(
        "facts", tuple(r.BootstrapFact(n, "CONFIRMED", b, "SIMULATION") for n in r.FACT_NAMES)
    )
    return r.BootstrapInventory(
        kw.pop("binding", b),
        facts,
        **{
            "writer_total": 0,
            "unknown_writers": 0,
            "stage": "NONE",
            "acknowledgement": "CONFIRMED",
            **kw,
        },
    )


def boot_case(name):
    r = M["ownership_resources"]
    kw = {}
    expected = None
    if name == "NO_FACTS":
        kw["facts"] = ()
        expected = "IDENTITY_UNKNOWN"
    elif name == "CODE":
        kw["binding"] = r.Binding("other", "boot.fixture", "context.fixture")
        expected = "IDENTITY_UNKNOWN"
    elif name == "CALLER":
        kw["facts"] = tuple(
            r.BootstrapFact(n, "CONFIRMED", binding(), "CALLER") for n in r.FACT_NAMES
        )
        expected = "IDENTITY_UNKNOWN"
    elif name == "ACTUAL":
        kw["simulation_only"] = False
        expected = "ACTUAL_PROVENANCE_NOT_IMPLEMENTED"
    elif name == "LIVE":
        kw["writer_total"] = 1
        expected = "WRITERS_LIVE"
    elif name == "UNKNOWN_WRITER":
        kw.update(writer_total=1, unknown_writers=1)
        expected = "WRITERS_UNKNOWN"
    elif name == "BOTH_WRITERS":
        kw.update(writer_total=2, unknown_writers=1)
        expected = "WRITERS_LIVE"
    elif name == "COUNTS_NONE":
        kw.update(writer_total=None, unknown_writers=None)
        expected = "WRITERS_UNOBSERVED"
    elif name == "COUNTS_PARTIAL":
        kw.update(writer_total=None, unknown_writers=1)
        expected = "WRITERS_UNKNOWN"
    elif name == "STAGE":
        kw["stage"] = "VALID_UNPROVEN"
        expected = "STAGE_UNPROVEN"
    elif name == "ACK":
        kw["acknowledgement"] = "UNCERTAIN"
        expected = "ACKNOWLEDGEMENT_UNPROVEN"
    elif name in ("GRAPH", "RESCUE", "ORIGINAL_ON"):
        key = "ACTOR_GRAPH" if name == "GRAPH" else name
        kw["facts"] = tuple(
            r.BootstrapFact(n, "UNKNOWN" if n == key else "CONFIRMED", binding(), "SIMULATION")
            for n in r.FACT_NAMES
        )
        expected = {
            "GRAPH": "ACTOR_GRAPH_INCOMPLETE",
            "RESCUE": "RESCUE_NOT_QUALIFIED",
            "ORIGINAL_ON": "ORIGINAL_ON_UNPROVEN",
        }[name]
    elif name in ("FACT_DUP", "COUNTS_BAD"):
        kw = (
            {"facts": (r.BootstrapFact("IDENTITY", "CONFIRMED", binding()),) * 2}
            if name == "FACT_DUP"
            else {"writer_total": 0, "unknown_writers": 1}
        )
        try:
            inventory(**kw)
        except r.ResourceRefused:
            return
        raise ValueError("INVENTORY_POLICY")
    p = r.plan_bootstrap(inventory(**kw), contract())
    DETAILS.update(
        blockers=len(p.blockers),
        dry_ready=p.actions == ("READY_FOR_REVIEW",),
        runtime_authorized=p.live_activation_authorized,
        simulation_only=p.simulation_only,
    )
    require(not p.live_activation_authorized and not p.repair_authorized, "DRY_AUTHORIZATION")
    require((not p.blockers) if name == "READY" else expected in p.blockers, "BLOCKERS")
    if name == "COUNTS_PARTIAL":
        require("WRITERS_UNOBSERVED" in p.blockers, "PARTIAL_WRITER_FACTS")


def catalog_case(index):
    r = M["ownership_resources"]
    cat = M["ownership_resource_catalog"]
    row = cat.ROWS[index]
    c = cat.contract_for_surface(row[0], binding(), dict.fromkeys(DOMAINS, "expected"))
    obs = tuple(
        r.Observation(
            q.domain,
            binding(),
            (r.ResourceState(q.resource_id, q.expected_state_id),),
            collection_status="COMPLETE",
            origin="SIMULATION",
        )
        for q in c.requirements
    )
    d = r.aggregate(c, obs)
    DETAILS.update(
        requirements=len(c.requirements),
        completeness=c.completeness,
        decision=d.status,
        runtime_authorized=d.runtime_completion_authorized,
    )
    require(
        len(c.requirements) == 7 and c.completeness == "UNKNOWN" and d.status == "UNKNOWN",
        "CATALOG_UNKNOWN",
    )


def integration(f, name):
    r = M["ownership_resources"]
    c = contract()
    obs = () if name == "UNKNOWN" else (observation(simulation_only=name != "ACTUAL"),)
    facade = r.ResourceFacade(c, r.ObservationSet(obs), inventory())
    d, p = facade.inspect()
    DETAILS.update(
        decision=d.status, blockers=len(p.blockers), runtime_authorized=p.live_activation_authorized
    )
    if name == "CONSTRUCTOR_IO":
        original = os.open

        def forbidden(*args, **kwargs):
            raise ValueError("CONSTRUCTOR_IO")

        os.open = forbidden
        try:
            pure = r.ResourceFacade(contract(), r.ObservationSet((observation(),)), inventory())
            pure.inspect()
            require(not pure.runtime_verification().accepted(), "ADAPTER")
        finally:
            os.open = original
        return
    reg = M["ownership"].Registry(
        f.root / "registry", boot_id=SUPPORT.BOOT, expected_uid=os.getuid(), clock_ns=lambda: 10
    )
    reg.initialize()
    result = M["ownership_adapters"].execute(
        reg, "LIFECYCLE", lambda: True, lambda value: facade.runtime_verification()
    )
    s = reg.summary()
    DETAILS.update(
        verification_accepted=facade.runtime_verification().accepted(),
        registry_receipts=s["receipts"],
        unknown_writers=s["unknown"],
        writer_total=s["writers"],
    )
    require(
        result.status == "UNKNOWN" and s["receipts"] == 0 and s["unknown"] == 1,
        "SIMULATION_NOT_RUNTIME",
    )


def run_case(f, name):
    if name in COMPARE:
        _, domain, variant = name.split("_", 2)
        compare_case(domain, variant)
    elif name in POLICY:
        policy_case(name[2:])
    elif name in AGGREGATE:
        aggregate_case(name[2:])
    elif name in BOOTSTRAP:
        boot_case(name[2:])
    elif name in CATALOG:
        catalog_case(int(name[2:]))
    else:
        integration(f, name[2:])


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
                        "batch.py": "wave3_resource_batch.py",
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
                "reason": "RESOURCE_CONTRACTS_CASE_FAILED",
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
        "marker": "RESOURCE_CONTRACTS_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "RESOURCE_CONTRACTS_BATCH_PARTIAL",
        "scope": "SIMULATED_RESOURCE_CONTRACTS_AND_DRY_BOOTSTRAP_ONLY",
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
            and data.get("scope") == "SIMULATED_RESOURCE_CONTRACTS_AND_DRY_BOOTSTRAP_ONLY"
            and data.get("marker")
            in ("RESOURCE_CONTRACTS_BATCH_RECORDED", "RESOURCE_CONTRACTS_BATCH_PARTIAL"),
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
        "# Отчёт: XGW wave3ap — resource contracts and dry bootstrap",
        "",
        "Автоматические exact данные; таблицу не редактировать. worker_exit_rc=NOT_COLLECTED.",
        "Synthetic observations only; actual collectors NOT_IMPLEMENTED; runtime unchanged.",
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
        require(
            d["completeness"] is None or d["completeness"] in ("UNKNOWN", "DECLARED_COMPLETE"),
            "DETAIL_COMPLETENESS",
        )
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
                "tests/stand/wave3_resource_batch.py",
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
    print("RESOURCE_CONTRACTS_REPORT_READY")


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
            print("RESOURCE_CONTRACTS_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception:
        print("RESOURCE_CONTRACTS_BATCH_STOP", "LOCAL_IO_OR_SCHEMA_ERROR")
        raise SystemExit(3) from None
