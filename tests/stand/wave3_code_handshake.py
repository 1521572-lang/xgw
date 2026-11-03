"""AK: new code identity/schema2/artifact/surface checks, private fixtures only."""

# ruff: noqa: E731
import contextlib
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

NOTES = Path.home() / "xgw-w3ak"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = "d83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13"
UNITS_SHA = "373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4"
SURFACE_SHA = "8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe"
LEGACY_SHA = "2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5"
LEGACY_COMMIT = "63c9c413930eb348d46b2ff986bef46dd2e423d4"
SURFACE_IDS = (
    "actions.apply_network",
    "actions.disable",
    "actions.enable",
    "actions.enable_checked",
    "actions.house_after_boot",
    "actions.pin",
    "actions.set_core",
    "actions.set_pool_mode",
    "actions.set_pool_pin",
    "actions.unpin",
    "api.add_inbounds",
    "api.add_outbounds",
    "api.pin",
    "api.remove_inbound",
    "api.remove_outbound",
    "api.replace_routing",
    "api.unpin",
    "capture._load",
    "capture._save",
    "capture.close",
    "capture.disable",
    "capture.down",
    "capture.enable",
    "capture.open",
    "capture.restore_tun",
    "capture.tailscale_direct",
    "capture.tailscale_fallback",
    "capture.tidy",
    "capture.up",
    "cores._event",
    "cores._reject",
    "cores._save",
    "cores._stage",
    "cores.rollback",
    "cores.run",
    "cores.update",
    "engine._save_fingerprints",
    "engine.apply_all",
    "engine.collect",
    "engine.persist",
    "engine.save_inventory",
    "panel.update",
    "peers._nft_element",
    "peers._save_peers",
    "peers.prepare",
    "peers.reconcile",
    "peers.stop",
    "pool._check_proxy",
    "pool._note_handshake",
    "pool._prune_candidates",
    "pool._prune_retired",
    "pool._record",
    "pool.check_some",
    "pool.refresh_backend",
    "pool.refresh_due",
    "pool_store._ensure",
    "pool_store.commit",
    "pool_store.prune",
    "pool_store.retire_openvpn",
    "pool_store.save_candidates",
    "singbox.apply",
    "singbox.restart",
    "singbox.rollback",
    "xray.apply",
    "xray.rollback",
)
FIELDS = ("source_sha256", "units_sha256", "surface_sha256")
BAD_DIGEST = ("TYPE", "SHORT", "UPPER", "NONHEX", "EMPTY")
IDENTITIES = (
    *("A_" + f + "__" + b for f in FIELDS for b in BAD_DIGEST),
    "A_PROTOCOL_BOOL",
    "A_PROTOCOL_ONE",
    "A_PROTOCOL_THREE",
    "A_PROTOCOL_TEXT",
    "A_PROTOCOL_FLOAT",
    "A_OBJECT",
    "A_SUBCLASS",
    "A_VALID",
    "A_CANONICAL",
)
OPS = (
    "ADMIT",
    "COMPLETE",
    "UNKNOWN",
    "RECEIPT",
    "ACQUIRE",
    "BEGIN",
    "UNUSED",
    "RESTORED",
    "SUMMARY",
    "DIAGNOSTIC",
)
MISMATCHES = (
    "SOURCE",
    "UNITS",
    "SURFACE",
    "LEGACY",
    "OLD_STORE",
    "MISSING",
    "EXTRA",
    "PROTOCOL",
    "BOOL_SCHEMA",
    "TYPE",
    "CONTEXT",
    "BOOT",
)
REGISTRIES = tuple("R_" + o + "__" + m for o in OPS for m in MISMATCHES)
ROLES = ("CAPTURE", "PANEL", "PEERS", "CORE", "API", "TUN_HOOK", "LIFECYCLE")
WRITERS = tuple("W_" + r + "__" + o for r in ROLES for o in ("COMMITTED", "NOOP", "ROLLED_BACK"))
LEGACY = ("L_STATE", "L_WRITER", "L_RECOVERY", "L_SUMMARY")
TOKEN_OPS = ("COMPLETE", "UNKNOWN", "RECEIPT", "BEGIN", "UNUSED", "RESTORED")
TOKEN_ERRORS = ("DIGEST", "MISSING", "EXTRA", "BOOL", "REGISTRY", "BOOT")
TOKENS = tuple("T_" + o + "__" + e for o in TOKEN_OPS for e in TOKEN_ERRORS)
STAGES = tuple(
    "J_" + n
    for n in (
        "SAME",
        "SOURCE",
        "UNITS",
        "SURFACE",
        "PROTOCOL",
        "LEGACY",
        "MISSING",
        "EXTRA",
        "BAD_SHA",
        "TRUNCATED",
        "DUPLICATE",
        "SYMLINK",
        "REVISION",
        "BOOT",
    )
)
FILE_ARGS = tuple(
    "P_" + n
    for n in (
        "RELATIVE",
        "ANCHOR",
        "PARENT",
        "UID_BOOL",
        "UID_NEGATIVE",
        "EMPTY",
        "LIST",
        "OVER_LIMIT",
        "TYPE",
        "TRAVERSAL",
        "ABSOLUTE",
        "DUPLICATE",
        "COLLISION",
        "BAD_HASH",
        "BOOL_MODE",
        "WRITABLE",
    )
)
FILE_READS = tuple(
    "F_" + n
    for n in (
        "PRESENT",
        "PUBLIC_DIR",
        "PUBLIC_FILE",
        "NESTED",
        "EMPTY",
        "MISSING",
        "EXTRA_FILE",
        "EXTRA_DIR",
        "CONTENT",
        "MODE",
        "ROOT_MODE",
        "CHILD_MODE",
        "OWNER",
        "HARDLINK",
        "SYMLINK",
        "PARENT_SYMLINK",
        "ROOT_SYMLINK",
        "FIFO",
        "OVERSIZE",
        "TOTAL_SIZE",
        "DIRECTORY",
        "DANGLING",
        "MAX_FILES",
        "TOO_DEEP",
    )
)
FILE_CONTEXT = tuple(
    "K_" + n
    for n in ("ROOT", "UID", "EXPECTATIONS", "MANIFEST", "READ", "DIRECTORY", "PID", "THREAD")
)
FULL = ("FULL_SOURCE", "FULL_UNITS")
SURFACE_CASES = tuple("S_" + n + "__" + m for n in SURFACE_IDS for m in ("SHADOW", "ROLE"))
SURFACE_EXTRA = tuple(
    "H_" + n
    for n in (
        "DEFAULT",
        "CODE",
        "WRAPPED",
        "CLOSURE",
        "SIGNATURE",
        "DIGEST",
        "ARGUMENT",
        "EXPECTED",
        "PID",
        "THREAD",
        "SPECS",
        "FUNCTIONS",
        "DEPENDENCIES",
        "DEFAULT_CODE",
        "CYCLE",
        "PRIVATE_SIGNATURE",
    )
)
INTEGRATIONS = tuple(
    "I_" + n
    for n in (
        "OK",
        "SOURCE_BAD",
        "UNITS_BAD",
        "SURFACE_BAD",
        "BOTH_BAD",
        "SOURCE_EXTRA",
        "UNITS_LINK",
        "SHADOW",
        "PROVIDER",
        "IDENTITY",
        "PID",
        "PREFIX",
        "MODE",
        "ADMIT",
        "WRITER_FENCE",
        "FULL_BUILD",
    )
)
BRIDGES = (
    "BRIDGE_OLD_V2_ADMIT",
    "BRIDGE_OLD_V2_SUMMARY",
    "BRIDGE_OLD_V2_COMPLETE",
    "BRIDGE_OLD_V2_BEGIN",
    "BRIDGE_OLD_V1_READ_NEW",
    "BRIDGE_NEW_V1_READ_OLD",
)
EXPECTED = (
    IDENTITIES
    + REGISTRIES
    + WRITERS
    + LEGACY
    + TOKENS
    + STAGES
    + BRIDGES
    + FILE_ARGS
    + FILE_READS
    + FILE_CONTEXT
    + FULL
    + SURFACE_CASES
    + SURFACE_EXTRA
    + INTEGRATIONS
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
    "registry_receipts",
    "registry_generation",
    "unknown_writers",
    "code_bound",
    "matched",
    "checked",
    "source_matched",
    "units_matched",
    "surface_matched",
    "source_checked",
    "units_checked",
    "surface_checked",
    "refused",
    "unchanged",
    "reason",
    "diagnostic",
)
BOOL_KEYS = {
    "code_bound",
    "matched",
    "source_matched",
    "units_matched",
    "surface_matched",
    "refused",
    "unchanged",
}
INT_KEYS = set(DETAIL_KEYS) - BOOL_KEYS - {"reason", "diagnostic"}
REASONS = frozenset(
    (
        "CODE_IDENTITY_ARGUMENT",
        "CODE_IDENTITY_MISMATCH",
        "CODE_CONTEXT_CHANGED",
        "STATE_SCHEMA",
        "BOOT_MISMATCH",
        "WRITER_TOKEN",
        "STALE_WRITER_TOKEN",
        "RECOVERY_TOKEN",
        "INTERRUPTED_COMMIT",
        "WRITERS_IN_FLIGHT",
        "OTHER_REFUSAL",
        "STAGE_VALID_UNPROVEN",
        "STAGE_REFUSED",
        "STAGE_UNRELATED",
        "BASELINE_REFUSED",
        "SEAL_TYPE",
        "SEAL_CONTEXT",
        "DIRECTORY_METADATA",
        "FILE_METADATA",
        "FILE_LIMIT",
        "TOTAL_LIMIT",
        "FILE_CHANGED",
        "CONTENT_MISMATCH",
        "INVENTORY_MISMATCH",
        "DIRECTORY_CHANGED",
        "ROOT_CHANGED",
        "READ_REFUSED",
        "EXACT_CODE_INVENTORY",
        "SURFACE_REFUSED",
        "DECLARED_SURFACES_MATCHED",
        "BUILD_OBSERVED",
        "BUILD_REFUSED",
        "PREFLIGHT_REFUSED",
    )
)
SUPPORT = None
M = {}
DETAILS = None
UNITS = {}


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
    global SUPPORT, UNITS
    private(NOTES, True)
    for name, digest in (
        ("support.py", SUPPORT_SHA),
        ("manifest.json", MANIFEST_SHA),
        ("units.json", UNITS_SHA),
        ("surface.json", SURFACE_SHA),
        ("legacy.py", LEGACY_SHA),
    ):
        private(NOTES / name)
        require(hashlib.sha256((NOTES / name).read_bytes()).hexdigest() == digest, "ARTIFACT_SHA")
    spec = importlib.util.spec_from_file_location("ak_fixture_support", NOTES / "support.py")
    SUPPORT = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(SUPPORT)
    SUPPORT.NOTES, SUPPORT.MANIFEST_SHA = NOTES, MANIFEST_SHA
    count = SUPPORT.verify_source()
    UNITS = SUPPORT.read(NOTES / "units.json")
    require(type(UNITS) is dict and len(UNITS) == 8, "UNIT_INVENTORY")
    private(NOTES / "units", True)
    seen = set()
    for p in (NOTES / "units").rglob("*"):
        if stat.S_ISDIR(p.lstat().st_mode):
            private(p, True)
        else:
            private(p)
            rel = p.relative_to(NOTES / "units").as_posix()
            require(
                rel in UNITS
                and p.stat().st_size <= 2097152
                and hashlib.sha256(p.read_bytes()).hexdigest() == UNITS[rel],
                "UNIT_BYTES",
            )
            seen.add(rel)
    require(seen == set(UNITS), "UNIT_INVENTORY")
    return count


def source():
    global M
    SUPPORT.install_audit()
    SUPPORT.load_source()
    M = SUPPORT.MODULES
    for n in (
        "ownership_identity",
        "ownership_seal",
        "ownership_surface",
        "ownership_diagnostics",
        "ownership_files",
        "ownership_completion",
    ):
        M[n] = importlib.import_module("frozen_ad." + n)
    spec = importlib.util.spec_from_file_location("legacy_ak", NOTES / "legacy.py")
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    M["legacy"] = legacy
    require(tuple(sorted(M["ownership_surface"].SURFACES)) == SURFACE_IDS, "SURFACE_INVENTORY")


def public_reason(value):
    return value if type(value) is str and value in REASONS else "OTHER_REFUSAL"


def refused(call, exceptions=None):
    exceptions = exceptions or (
        M["ownership"].Refused,
        M["ownership_identity"].IdentityRefused,
        M["ownership_seal"].SealRefused,
        M["ownership_surface"].SurfaceRefused,
    )
    try:
        call()
    except exceptions as exc:
        DETAILS.update(
            refused=True, reason=public_reason(exc.args[0] if len(exc.args) == 1 else None)
        )
    else:
        raise ValueError("EXPECTED_REFUSAL")


def code(**changes):
    values = dict(
        source_sha256="a" * 64, units_sha256="b" * 64, surface_sha256="c" * 64, protocol=2
    )
    values.update(changes)
    return M["ownership_identity"].CodeIdentity(**values)


def registry(f, identity, name="v2"):
    r = M["ownership"].Registry(
        f.root / name,
        boot_id=SUPPORT.BOOT,
        expected_uid=os.getuid(),
        clock_ns=lambda: 10,
        code_identity=identity,
    )
    r.initialize()
    f.active_registry = r
    return r


def snapshot(r):
    return SUPPORT.digest_tree(r.directory)


def prepare_operation(r, operation):
    writer = None
    lease = None
    if operation in ("COMPLETE", "UNKNOWN", "RECEIPT"):
        writer = r.admit("CORE")
        if operation == "RECEIPT":
            r.complete(writer, outcome="COMMITTED", verified=True)
    if operation in ("BEGIN", "UNUSED", "RESTORED"):
        lease = r.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
        if operation == "RESTORED":
            r.begin(lease)
    return writer, lease


def operation(r, name, writer=None, lease=None):
    calls = {
        "ADMIT": lambda: r.admit("CORE"),
        "COMPLETE": lambda: r.complete(writer, outcome="COMMITTED", verified=True),
        "UNKNOWN": lambda: r.unknown(writer),
        "RECEIPT": lambda: r.receipt(writer),
        "ACQUIRE": lambda: r.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100),
        "BEGIN": lambda: r.begin(lease),
        "UNUSED": lambda: r.retire(lease, outcome="UNUSED"),
        "RESTORED": lambda: r.retire(lease, outcome="RESTORED_ON", verified=True),
        "SUMMARY": r.summary,
        "DIAGNOSTIC": lambda: M["ownership_diagnostics"].inspect_registry(r),
    }
    return calls[name]()


def identity_case(f, name):
    n = name[2:]
    changes = {}
    if "__" in n:
        field, value = n.split("__")
        changes[field] = {
            "TYPE": None,
            "SHORT": "a" * 63,
            "UPPER": "A" * 64,
            "NONHEX": "g" * 64,
            "EMPTY": "",
        }[value]
    elif n.startswith("PROTOCOL_"):
        changes["protocol"] = {"BOOL": True, "ONE": 1, "THREE": 3, "TEXT": "2", "FLOAT": 2.0}[n[9:]]
    if changes:
        obj = code(**changes)
        refused(lambda: registry(f, obj))
        require(not (f.root / "v2").exists(), "INVALID_IDENTITY_CREATED_STORE")
    elif n in ("OBJECT", "SUBCLASS"):
        cls = M["ownership_identity"].CodeIdentity

        class Foreign(cls):
            pass

        obj = object() if n == "OBJECT" else Foreign("a" * 64, "b" * 64, "c" * 64)
        refused(lambda: registry(f, obj))
        require(not (f.root / "v2").exists(), "INVALID_IDENTITY_CREATED_STORE")
    else:
        obj = code()
        record = obj.record()
        require(
            record["protocol"] == 2 and M["ownership_identity"].valid_record(record),
            "IDENTITY_RECORD",
        )
        if n == "CANONICAL":
            require(
                obj.digest()
                == hashlib.sha256(
                    M["ownership_identity"].canonical(dict(reversed(list(record.items()))))
                ).hexdigest(),
                "CANONICAL_IDENTITY",
            )
        DETAILS["matched"] = True


def registry_case(f, name):
    op, mismatch = name[2:].split("__")
    ident = None if mismatch == "OLD_STORE" else code()
    r = registry(f, ident)
    writer, lease = prepare_operation(r, op)
    peer_identity = code()
    if mismatch in ("SOURCE", "UNITS", "SURFACE"):
        peer_identity = code(**{FIELDS[("SOURCE", "UNITS", "SURFACE").index(mismatch)]: "d" * 64})
    if mismatch == "LEGACY":
        peer_identity = None
    peer = M["ownership"].Registry(
        r.directory,
        boot_id="22222222-2222-2222-2222-222222222222" if mismatch == "BOOT" else SUPPORT.BOOT,
        expected_uid=os.getuid(),
        clock_ns=lambda: 10,
        code_identity=peer_identity,
    )
    if mismatch == "CONTEXT":
        peer.code_identity = code()
    if mismatch in ("MISSING", "EXTRA", "PROTOCOL", "BOOL_SCHEMA", "TYPE"):
        p = r.directory / "state.json"
        value = json.loads(p.read_bytes())
        if mismatch == "MISSING":
            value.pop("code_identity")
        elif mismatch == "EXTRA":
            value["code_identity"]["extra"] = "PRIVATE_FIXTURE"
        elif mismatch == "PROTOCOL":
            value["code_identity"]["protocol"] = 3
        elif mismatch == "BOOL_SCHEMA":
            value["schema"] = True
        else:
            value["code_identity"] = []
        p.write_text(json.dumps(value))
    before = snapshot(r)
    if op == "DIAGNOSTIC":
        d = operation(peer, op, writer, lease)
        require(
            d.status == "BASELINE_REFUSED" and not d.baseline_valid, "DIAGNOSTIC_ACCEPTED_BAD_CODE"
        )
        DETAILS.update(refused=True, reason=d.status, diagnostic=d.status)
    else:
        refused(lambda: operation(peer, op, writer, lease))
    DETAILS["unchanged"] = before == snapshot(r)
    require(DETAILS["unchanged"], "REFUSAL_CHANGED_REGISTRY")


def writer_case(f, name):
    role, result = name[2:].split("__")
    r = registry(f, code())
    token = r.admit(role)
    require(token["code_identity_sha256"] == code().digest(), "WRITER_CODE_TOKEN")
    peer = M["ownership"].Registry(
        r.directory,
        boot_id=SUPPORT.BOOT,
        expected_uid=os.getuid(),
        clock_ns=lambda: 10,
        code_identity=code(),
    )
    peer.complete(token, outcome=result, verified=True)
    require(r.receipt(token) == {"outcome": result, "generation": 1}, "MATCHING_CODE_RECEIPT")
    data = json.loads((r.directory / "state.json").read_bytes())
    require(data["code_identity"] == code().record() and data["schema"] == 2, "CODE_NOT_RETAINED")
    DETAILS["matched"] = True


def legacy_case(f, name):
    r = registry(f, None, "legacy")
    if name == "L_STATE":
        d = json.loads((r.directory / "state.json").read_bytes())
        require(d["schema"] == 1 and "code_identity" not in d and len(d) == 12, "LEGACY_STATE")
    elif name == "L_WRITER":
        token = r.admit("CORE")
        require(set(token) == {"registry_id", "boot_id", "id", "role"}, "LEGACY_WRITER")
        r.complete(token, outcome="COMMITTED", verified=True)
    elif name == "L_RECOVERY":
        token = r.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
        require(
            set(token) == {"registry_id", "boot_id", "run_id", "epoch", "generation"},
            "LEGACY_RECOVERY",
        )
        r.retire(token, outcome="UNUSED")
    else:
        require(
            set(r.summary()) == {"writers", "unknown", "generation", "receipts", "phase"},
            "LEGACY_SUMMARY",
        )
    DETAILS["matched"] = True


def token_case(f, name):
    op, bad = name[2:].split("__")
    r = registry(f, code())
    writer, lease = prepare_operation(r, op)
    token = dict(writer if writer is not None else lease)
    if bad == "DIGEST":
        token["code_identity_sha256"] = "d" * 64
    elif bad == "MISSING":
        token.pop("code_identity_sha256")
    elif bad == "EXTRA":
        token["extra"] = True
    elif bad == "BOOL":
        token["id" if writer is not None else "epoch"] = True
    elif bad == "REGISTRY":
        token["registry_id"] = "f" * 32
    else:
        token["boot_id"] = "22222222-2222-2222-2222-222222222222"
    before = snapshot(r)
    refused(
        lambda: operation(
            r, op, token if writer is not None else None, token if lease is not None else None
        )
    )
    DETAILS["unchanged"] = before == snapshot(r)
    require(DETAILS["unchanged"], "BAD_TOKEN_CHANGED_STORE")


def stage_case(f, name):
    r = registry(f, code())
    n = name[2:]
    data = json.loads((r.directory / "state.json").read_bytes())
    data["revision"] += 1
    if n in ("SOURCE", "UNITS", "SURFACE"):
        data["code_identity"][FIELDS[("SOURCE", "UNITS", "SURFACE").index(n)]] = "d" * 64
    elif n == "PROTOCOL":
        data["code_identity"]["protocol"] = 3
    elif n == "LEGACY":
        data["schema"] = 1
        data.pop("code_identity")
    elif n == "MISSING":
        data.pop("code_identity")
    elif n == "EXTRA":
        data["code_identity"]["extra"] = True
    elif n == "BAD_SHA":
        data["code_identity"]["source_sha256"] = "invalid"
    elif n == "REVISION":
        data["revision"] += 1
    elif n == "BOOT":
        data["boot_id"] = "22222222-2222-2222-2222-222222222222"
    target = r.directory / "state.next"
    if n == "SYMLINK":
        f.write(f.work / "stage.json", data)
        target.symlink_to(f.work / "stage.json")
    else:
        text = json.dumps(data)
        if n == "TRUNCATED":
            text = text[: len(text) // 2]
        elif n == "DUPLICATE":
            text = text.replace('"protocol": 2', '"protocol": 2, "protocol": 2')
        target.write_text(text)
        target.chmod(0o600)
    before = snapshot(r)
    d = M["ownership_diagnostics"].inspect_registry(r)
    expected = (
        "STAGE_VALID_UNPROVEN"
        if n == "SAME"
        else "STAGE_UNRELATED"
        if n == "REVISION"
        else "STAGE_REFUSED"
    )
    require(
        d.status == expected and d.baseline_valid and d.repair_authorized is False,
        "STAGE_CODE_DIAGNOSTIC",
    )
    DETAILS.update(
        diagnostic=d.status,
        registry_receipts=d.receipts,
        unknown_writers=d.unknown,
        refused=n != "SAME",
        unchanged=before == snapshot(r),
    )
    require(DETAILS["unchanged"], "STAGE_DIAGNOSTIC_REPAIRED")
    refused(lambda: r.admit("CORE"))


def make_seal(f, name="artifact", items=None):
    s = M["ownership_seal"]
    root = f.work / name
    root.mkdir(mode=0o700)
    items = items or [("code.py", b"public fixture\n", 0o600)]
    expectations = []
    for relative, raw, mode in items:
        p = root / relative
        p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        p.write_bytes(raw)
        p.chmod(mode)
        expectations.append(s.CodeFile(relative, hashlib.sha256(raw).hexdigest(), mode))
    return s.CodeSeal(root, expected_uid=os.getuid(), expectations=tuple(expectations))


def seal_evidence(observer):
    result = observer.observe()
    DETAILS.update(
        matched=result.matched, checked=result.checked, reason=public_reason(result.reason)
    )
    return result


def file_argument(f, name):
    s = M["ownership_seal"]
    v = make_seal(f)
    n = name[2:]
    root, uid, items = v.root, os.getuid(), v.expectations
    if n == "RELATIVE":
        root = Path("relative")
    elif n == "ANCHOR":
        root = Path("/")
    elif n == "PARENT":
        root = v.root / ".." / "other"
    elif n == "UID_BOOL":
        uid = True
    elif n == "UID_NEGATIVE":
        uid = -1
    elif n == "EMPTY":
        items = ()
    elif n == "LIST":
        items = list(items)
    elif n == "OVER_LIMIT":
        items = tuple(s.CodeFile(f"f{i}", "a" * 64) for i in range(257))
    elif n == "TYPE":
        items = (object(),)
    else:
        relative = (
            "../code.py" if n == "TRAVERSAL" else "/code.py" if n == "ABSOLUTE" else "code.py"
        )
        item = s.CodeFile(
            relative,
            "invalid" if n == "BAD_HASH" else "a" * 64,
            True if n == "BOOL_MODE" else 0o666 if n == "WRITABLE" else 0o600,
        )
        items = (
            (item, item)
            if n == "DUPLICATE"
            else (item, s.CodeFile("code.py/child", "a" * 64))
            if n == "COLLISION"
            else (item,)
        )
    before = SUPPORT.digest_tree(f.work)
    refused(lambda: s.CodeSeal(root, expected_uid=uid, expectations=items))
    DETAILS["unchanged"] = before == SUPPORT.digest_tree(f.work)
    require(DETAILS["unchanged"], "SEAL_CONSTRUCTOR_WRITE")


def file_case(f, name):
    s = M["ownership_seal"]
    n = name[2:]
    items = None
    if n in ("NESTED", "CHILD_MODE", "PARENT_SYMLINK"):
        items = [("pkg/code.py", b"public fixture\n", 0o600)]
    elif n == "EMPTY":
        items = [("code.py", b"", 0o600)]
    elif n == "PUBLIC_FILE":
        items = [("code.py", b"public fixture\n", 0o644)]
    elif n == "MAX_FILES":
        items = [(f"f{i}.py", b"", 0o600) for i in range(256)]
    elif n == "TOTAL_SIZE":
        items = [(f"f{i}.py", b"x" * s.MAX_FILE, 0o600) for i in range(9)]
    v = make_seal(f, items=items)
    target = v.root / ("pkg/code.py" if items and items[0][0].startswith("pkg/") else "code.py")
    if n == "TOO_DEEP":
        refused(
            lambda: s.CodeSeal(
                v.root,
                expected_uid=os.getuid(),
                expectations=(s.CodeFile("a/" * 16 + "file", "a" * 64),),
            )
        )
        return
    if n == "PUBLIC_DIR":
        v.root.chmod(0o755)
    elif n == "MISSING":
        target.unlink()
    elif n == "EXTRA_FILE":
        (v.root / "unlisted").write_text("PRIVATE_FIXTURE")
    elif n == "EXTRA_DIR":
        (v.root / "unlisted").mkdir()
    elif n == "CONTENT":
        target.write_bytes(b"changed")
    elif n == "MODE":
        target.chmod(0o644)
    elif n == "ROOT_MODE":
        v.root.chmod(0o777)
    elif n == "CHILD_MODE":
        target.parent.chmod(0o777)
    elif n == "OWNER":
        v = s.CodeSeal(v.root, expected_uid=os.getuid() + 1, expectations=v.expectations)
    elif n == "HARDLINK":
        (f.work / "hardlink").hardlink_to(target)
    elif n in ("SYMLINK", "DANGLING"):
        target.unlink()
        other = f.work / "outside"
        if n == "SYMLINK":
            other.write_text("PRIVATE_FIXTURE")
        target.symlink_to(other)
    elif n == "PARENT_SYMLINK":
        target.parent.rename(f.work / "parent")
        (v.root / "pkg").symlink_to(f.work / "parent", target_is_directory=True)
    elif n == "ROOT_SYMLINK":
        v.root.rename(f.work / "moved")
        v.root.symlink_to(f.work / "moved", target_is_directory=True)
    elif n == "FIFO":
        target.unlink()
        os.mkfifo(target, 0o600)
    elif n == "OVERSIZE":
        target.write_bytes(b"x" * (s.MAX_FILE + 1))
    elif n == "DIRECTORY":
        target.unlink()
        target.mkdir()
    before = SUPPORT.digest_tree(f.work)
    result = seal_evidence(v)
    positive = n in ("PRESENT", "PUBLIC_DIR", "PUBLIC_FILE", "NESTED", "EMPTY", "MAX_FILES")
    require(result.matched is positive, "FILE_DECISION")
    if n == "TOTAL_SIZE":
        require(result.checked == 8, "TOTAL_PREFIX")
    DETAILS["unchanged"] = before == SUPPORT.digest_tree(f.work)
    require(DETAILS["unchanged"], "SEAL_OBSERVER_WRITE")


def context_case(f, name):
    v = make_seal(f)
    n = name[2:]
    if n == "ROOT":
        v.root = f.work / "other"
    elif n == "UID":
        v.expected_uid = True
    elif n == "EXPECTATIONS":
        v.expectations = ()
    elif n in ("MANIFEST", "READ", "DIRECTORY"):
        setattr(
            v,
            {"MANIFEST": "manifest_digest", "READ": "read_file", "DIRECTORY": "directory"}[n],
            lambda *args: None,
        )
    elif n == "PID":
        v._pid = -1
    else:
        v._thread = -1
    result = seal_evidence(v)
    require(not result.matched and result.checked == 0, "CONTEXT_ACCEPTED")


def full_seal(which):
    manifest = SUPPORT.read(NOTES / ("manifest.json" if which == "SOURCE" else "units.json"))
    s = M["ownership_seal"]
    return s.CodeSeal(
        NOTES / ("source" if which == "SOURCE" else "units"),
        expected_uid=os.getuid(),
        expectations=tuple(s.CodeFile(n, sha) for n, sha in sorted(manifest.items())),
    )


def surface_case(f, name):
    target, kind = name[2:].rsplit("__", 1)
    s = M["ownership_surface"]
    owner, attribute, _ = s.SURFACES[target]
    fn = getattr(owner, attribute)
    catalog = s.SurfaceCatalog(SURFACE_SHA)
    with SUPPORT.patches(
        [(owner, attribute, lambda *args: None)]
        if kind == "SHADOW"
        else [(fn, "ownership_role", "FOREIGN")]
    ):
        result = catalog.observe()
    DETAILS.update(matched=result.matched, checked=result.checked, reason=result.reason)
    require(not result.matched and result.runtime_fence_verified is False, "SURFACE_DRIFT_ACCEPTED")


@contextlib.contextmanager
def attribute(obj, name, value):
    sentinel = object()
    old = getattr(obj, name, sentinel)
    setattr(obj, name, value)
    try:
        yield
    finally:
        if old is sentinel:
            delattr(obj, name)
        else:
            setattr(obj, name, old)


def surface_extra(f, name):
    s = M["ownership_surface"]
    catalog = s.SurfaceCatalog(SURFACE_SHA)
    n = name[2:]
    owner, method, _ = s.SURFACES["engine.apply_all"]
    fn = getattr(owner, method)
    patch = contextlib.nullcontext()
    if n == "ARGUMENT":
        refused(lambda: s.SurfaceCatalog(True))
        return
    if n == "DIGEST":
        catalog = s.SurfaceCatalog("0" * 64)
    elif n == "EXPECTED":
        catalog.expected_sha256 = "0" * 64
    elif n == "PID":
        catalog._pid = -1
    elif n == "THREAD":
        catalog._thread = -1
    elif n == "SPECS":
        patch = attribute(s.ownership_binding, "SPECS", dict(s.ownership_binding.SPECS))
    elif n == "FUNCTIONS":
        patch = attribute(s.ownership_binding, "FUNCTIONS", dict(s.ownership_binding.FUNCTIONS))
    elif n == "CODE":
        patch = attribute(
            fn, "__code__", fn.__code__.replace(co_firstlineno=fn.__code__.co_firstlineno + 1)
        )
    elif n in ("WRAPPED", "CYCLE"):
        patch = attribute(fn, "__wrapped__", fn if n == "CYCLE" else lambda *args, **kwargs: None)
    elif n == "CLOSURE":
        patch = attribute(fn.__closure__[0], "cell_contents", object())
    elif n in ("SIGNATURE", "PRIVATE_SIGNATURE"):
        patch = attribute(
            fn, "__signature__", inspect.Signature() if n == "SIGNATURE" else object()
        )
    elif n == "DEPENDENCIES":
        patch = attribute(fn, "ownership_dependencies", ())
    elif n == "DEFAULT":
        patch = attribute(
            fn.__wrapped__, "__kwdefaults__", {**fn.__wrapped__.__kwdefaults__, "force_now": True}
        )
    elif n == "DEFAULT_CODE":
        runner = M["ownership_surface"].actions.apply_network.__wrapped__.__kwdefaults__["runner"]
        patch = attribute(
            runner,
            "__code__",
            runner.__code__.replace(co_firstlineno=runner.__code__.co_firstlineno + 1),
        )
    with patch:
        result = catalog.observe()
    DETAILS.update(matched=result.matched, checked=result.checked, reason=result.reason)
    require(not result.matched, "SURFACE_MUTATION_ACCEPTED")


def integration(f, name):
    s = M["ownership_surface"]
    n = name[2:]
    source, units = (
        (full_seal("SOURCE"), full_seal("UNITS"))
        if n == "FULL_BUILD"
        else (make_seal(f, "source"), make_seal(f, "units"))
    )
    if n == "PREFIX":
        (source.root / "second.py").write_bytes(b"changed")
        (source.root / "second.py").chmod(0o600)
        sf = M["ownership_seal"]
        source = sf.CodeSeal(
            source.root,
            expected_uid=os.getuid(),
            expectations=(*source.expectations, sf.CodeFile("second.py", "0" * 64)),
        )
    catalog = s.SurfaceCatalog(SURFACE_SHA)
    ident = M["ownership_identity"].CodeIdentity(
        source.manifest_digest(), units.manifest_digest(), SURFACE_SHA
    )
    pre = s.CodePreflight(ident, source, units, catalog)
    patch = contextlib.nullcontext()
    if n in ("SOURCE_BAD", "BOTH_BAD"):
        (source.root / "code.py").write_bytes(b"changed")
    if n in ("UNITS_BAD", "BOTH_BAD"):
        (units.root / "code.py").write_bytes(b"changed")
    if n == "SOURCE_EXTRA":
        (source.root / "extra").write_text("PRIVATE_FIXTURE")
    if n == "UNITS_LINK":
        (f.work / "alias").hardlink_to(units.root / "code.py")
    if n == "MODE":
        (source.root / "code.py").chmod(0o644)
    if n == "SURFACE_BAD":
        owner, method, _ = s.SURFACES["engine.apply_all"]
        patch = attribute(getattr(owner, method), "ownership_role", "FOREIGN")
    if n == "SHADOW":
        source.observe = lambda: None
    if n == "PROVIDER":
        pre.source = make_seal(f, "other")
    if n == "IDENTITY":
        pre.identity = M["ownership_identity"].CodeIdentity(
            source.manifest_digest(), units.manifest_digest(), SURFACE_SHA
        )
    if n == "PID":
        pre._pid = -1
    with patch:
        result = pre.observe()
    DETAILS.update(
        matched=result.matched,
        reason=result.reason,
        source_matched=result.source_matched,
        units_matched=result.units_matched,
        surface_matched=result.surface_matched,
        source_checked=result.source_checked,
        units_checked=result.units_checked,
        surface_checked=result.surface_checked,
    )
    positive = n in ("OK", "ADMIT", "WRITER_FENCE", "FULL_BUILD")
    require(
        result.matched is positive and result.runtime_fence_verified is False, "PREFLIGHT_DECISION"
    )
    if n == "PREFIX":
        require(
            result.source_checked == 1
            and result.units_matched is True
            and result.surface_matched is True,
            "PREFLIGHT_PREFIX",
        )
    if n in ("ADMIT", "WRITER_FENCE", "FULL_BUILD"):
        r = registry(f, ident)
        if n == "WRITER_FENCE":
            path = f.work / "published.txt"
            raw = b"private publication\n"
            fm = M["ownership_files"]
            cm = M["ownership_completion"]
            verifier = cm.FileCompletion(
                cm.CompletionContract(frozenset({"PANEL"}), ("FILES",), "COMMITTED"),
                fm.PrivateFiles(
                    f.work,
                    expected_uid=os.getuid(),
                    expectations=(
                        fm.FileExpectation("published.txt", hashlib.sha256(raw).hexdigest()),
                    ),
                ),
                accept=lambda value: value is True,
            )
            c = M["ownership_hooks"].Coordinator(r, verifier)

            def publish():
                refused(lambda: r.acquire(run_id="b" * 32, expected_generation=0, duration_ns=100))
                path.write_bytes(raw)
                path.chmod(0o600)
                return True

            require(
                c.call("PANEL", publish) is True and r.summary()["receipts"] == 1,
                "CODE_BOUND_COMPLETION",
            )
        else:
            token = r.admit("CORE")
            r.complete(token, outcome="NOOP", verified=True)
        require(r.summary()["code_bound"] is True, "CODE_BOUND_STORE")


def bridge(f, name):
    old = M["legacy"]
    current = M["ownership"]
    if name in ("BRIDGE_OLD_V1_READ_NEW", "BRIDGE_NEW_V1_READ_OLD"):
        cls = old.Registry if name == "BRIDGE_OLD_V1_READ_NEW" else current.Registry
        r = cls(
            f.root / "legacy", boot_id=SUPPORT.BOOT, expected_uid=os.getuid(), clock_ns=lambda: 10
        )
        r.initialize()
        f.active_registry = r
        peer_cls = current.Registry if cls is old.Registry else old.Registry
        peer = peer_cls(
            r.directory, boot_id=SUPPORT.BOOT, expected_uid=os.getuid(), clock_ns=lambda: 10
        )
        before = snapshot(r)
        require(peer.summary() == r.summary(), "LEGACY_READER_COMPATIBILITY")
        DETAILS.update(matched=True, unchanged=before == snapshot(r))
        return
    op = name.removeprefix("BRIDGE_OLD_V2_")
    r = registry(f, code())
    writer, lease = prepare_operation(r, op)
    peer = old.Registry(
        r.directory, boot_id=SUPPORT.BOOT, expected_uid=os.getuid(), clock_ns=lambda: 10
    )
    before = snapshot(r)
    refused(lambda: operation(peer, op, writer, lease), exceptions=(old.Refused,))
    DETAILS["unchanged"] = before == snapshot(r)
    require(DETAILS["unchanged"], "OLD_READER_CHANGED_V2")


def run_case(f, name):
    if name in IDENTITIES:
        return identity_case(f, name)
    if name in REGISTRIES:
        return registry_case(f, name)
    if name in WRITERS:
        return writer_case(f, name)
    if name in LEGACY:
        return legacy_case(f, name)
    if name in TOKENS:
        return token_case(f, name)
    if name in STAGES:
        return stage_case(f, name)
    if name in BRIDGES:
        return bridge(f, name)
    if name in FILE_ARGS:
        return file_argument(f, name)
    if name in FILE_READS:
        return file_case(f, name)
    if name in FILE_CONTEXT:
        return context_case(f, name)
    if name in FULL:
        result = seal_evidence(full_seal(name[5:]))
        require(result.matched, "FROZEN_PUBLIC_BUILD")
        return
    if name in SURFACE_CASES:
        return surface_case(f, name)
    if name in SURFACE_EXTRA:
        return surface_extra(f, name)
    require(name in INTEGRATIONS, "CASE_UNKNOWN")
    return integration(f, name)


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
            and before.st_size <= 524288,
            "RECORD_METADATA",
        )
        raw = stream.read(524289)
        after = os.fstat(stream.fileno())
    fields = lambda s: (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_size, s.st_mtime_ns)
    require(len(raw) <= 524288 and fields(before) == fields(after), "RECORD_CHANGED")

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
            f = SUPPORT.Fixture(root)
            run_case(f, name)
            row = {"case": name, "passed": True}
        except Exception as exc:
            scope_stopped = isinstance(exc, (SUPPORT.ScopeStop, OSError))
            public, line = "UNKNOWN", None
            tb = exc.__traceback__
            while tb is not None:
                filename = Path(tb.tb_frame.f_code.co_filename)
                try:
                    public, line = filename.relative_to(NOTES / "source").as_posix(), tb.tb_lineno
                except ValueError:
                    mapping = {
                        "batch.py": "wave3_code_handshake.py",
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
                "reason": "CODE_HANDSHAKE_CASE_FAILED",
                "error_class": type(exc).__name__
                if type(exc).__name__
                in (
                    "ValueError",
                    "TypeError",
                    "RuntimeError",
                    "OSError",
                    "ScopeStop",
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
        if f is not None and getattr(f, "active_registry", None) is not None:
            try:
                s = f.active_registry.summary()
            except M["ownership"].Refused:
                pass
            else:
                DETAILS.update(
                    registry_receipts=s["receipts"],
                    registry_generation=s["generation"],
                    unknown_writers=s["unknown"],
                    code_bound=s.get("code_bound"),
                )
        row.update(details=DETAILS, elapsed_ms=int((time.monotonic() - before) * 1000))
        rows.append(row)
        SUPPORT.atomic("progress.json", {"final": False, "completed": len(rows), "cases": rows})
        if SUPPORT.AUDIT["violations"] or scope_stopped:
            break
    passed = sum(row["passed"] for row in rows)
    result = {
        "marker": "CODE_HANDSHAKE_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "CODE_HANDSHAKE_BATCH_PARTIAL",
        "scope": "CODE_IDENTITY_ARTIFACTS_AND_DECLARED_SURFACES_ONLY",
        "expected": len(EXPECTED),
        "completed": len(rows),
        "passed": passed,
        "cases": rows,
        "global_scope_stop": scope_stopped or SUPPORT.AUDIT["violations"] > 0,
        "remaining_not_run": len(EXPECTED) - len(rows),
        "source_files": source_count,
        "unit_files": len(UNITS),
        "declared_surfaces": len(SURFACE_IDS),
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
            and data.get("scope") == "CODE_IDENTITY_ARTIFACTS_AND_DECLARED_SURFACES_ONLY"
            and data.get("marker")
            in ("CODE_HANDSHAKE_BATCH_RECORDED", "CODE_HANDSHAKE_BATCH_PARTIAL"),
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
        "# Отчёт: XGW wave3ak — code identity and artifact preflight",
        "",
        "Автоматические exact данные; таблицу не редактировать. worker_exit_rc=NOT_COLLECTED.",
        "Private schema2/artifact copies/declared surfaces; installed runtime не активировался.",
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
        require(
            d["reason"] is None or (type(d["reason"]) is str and d["reason"] in REASONS),
            "DETAIL_REASON",
        )
        require(
            d["diagnostic"] is None
            or d["diagnostic"]
            in ("STAGE_VALID_UNPROVEN", "STAGE_REFUSED", "STAGE_UNRELATED", "BASELINE_REFUSED"),
            "DETAIL_DIAGNOSTIC",
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
    print("CODE_HANDSHAKE_REPORT_READY")


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
            print("CODE_HANDSHAKE_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception:
        print("CODE_HANDSHAKE_BATCH_STOP", "LOCAL_IO_OR_SCHEMA_ERROR")
        raise SystemExit(3) from None
