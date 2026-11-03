"""Real source entrypoint qualification, fake effects only, no installed XGW import."""

# Lazy callbacks keep real method calls inside the temporary patch scope.
# ruff: noqa: E731

import contextlib
import hashlib
import importlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

NOTES = Path.home() / "xgw-w3ad"
MANIFEST_SHA = "69283e6ff3f6e84e7e5415cd6d4dae2dd5f907959c505c14b97003fde9694091"
BOOT = "11111111-1111-1111-1111-111111111111"
VARIANTS = (
    "C_SAVE",
    "C_LOAD_OFF",
    "C_UP",
    "C_ENABLE",
    "C_DISABLE",
    "C_OPEN",
    "C_CLOSE",
    "C_DOWN",
    "C_TUN",
    "C_TIDY",
    "C_TS_DIRECT",
    "C_TS_EARLY",
    "C_TS_FALLBACK",
    "B_SAVE",
    "B_ELEMENT",
    "B_PREPARE",
    "B_STOP",
    "B_RECONCILE",
    "X_APPLY",
    "X_ROLLBACK",
    "S_APPLY",
    "S_EQUAL",
    "S_REMOVE",
    "S_DEFER",
    "S_ROLLBACK",
    "S_RESTART",
    "API_ADD_OUT",
    "API_RM_OUT",
    "API_ADD_IN",
    "API_RM_IN",
    "API_ROUTING",
    "API_PIN",
    "API_UNPIN",
    "P_UPDATE",
    "P_NOOP",
    "K_UPDATE",
    "K_REPLACE",
    "K_ROLLBACK",
)
MODES = ("LEGACY", "OWNED", "FENCED")
RETURNS = {
    "C_SAVE": "NONE",
    "C_LOAD_OFF": "MODE_OFF",
    "C_UP": "MODE_ON",
    "C_ENABLE": "MODE_NONE",
    "C_DISABLE": "MODE_NONE",
    "C_OPEN": "MODE_ON",
    "C_CLOSE": "MODE_ON",
    "C_DOWN": "NONE",
    "C_TUN": "TEXT",
    "C_TIDY": "TEXT",
    "C_TS_DIRECT": "TEXT",
    "C_TS_EARLY": "EMPTY_TEXT",
    "C_TS_FALLBACK": "TEXT",
    "B_SAVE": "NONE",
    "B_ELEMENT": "NONE",
    "B_PREPARE": "LEASE",
    "B_STOP": "NONE",
    "B_RECONCILE": "ZERO",
    "X_APPLY": "OUTCOME_RESTART",
    "X_ROLLBACK": "OUTCOME_ROLLBACK",
    "S_APPLY": "OUTCOME_STARTED",
    "S_EQUAL": "OUTCOME_UNCHANGED",
    "S_REMOVE": "OUTCOME_REMOVED",
    "S_DEFER": "OUTCOME_DEFERRED",
    "S_ROLLBACK": "OUTCOME_ROLLBACK",
    "S_RESTART": "NONE",
    "API_ADD_OUT": "EMPTY_TEXT",
    "API_RM_OUT": "EMPTY_TEXT",
    "API_ADD_IN": "EMPTY_TEXT",
    "API_RM_IN": "EMPTY_TEXT",
    "API_ROUTING": "EMPTY_TEXT",
    "API_PIN": "EMPTY_TEXT",
    "API_UNPIN": "EMPTY_TEXT",
    "P_UPDATE": "BOOL_TRUE",
    "P_NOOP": "BOOL_FALSE",
    "K_UPDATE": "TEXT",
    "K_REPLACE": "TEXT",
    "K_ROLLBACK": "TEXT",
}
MODULES = {}
AUDIT = {"ready": False, "probe": False, "violations": 0}
CASE_DETAILS = None


class ScopeStop(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise ValueError(code)


def private(path, directory=False):
    info = path.lstat()
    require(
        (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and (directory or info.st_nlink == 1),
        "PRIVATE_METADATA",
    )


def read(path):
    private(path)
    require(path.stat().st_size <= 262144, "READ_LIMIT")
    return json.loads(path.read_bytes())


def create(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())


def atomic(name, value):
    create(NOTES / (name + ".part"), value)
    os.replace(NOTES / (name + ".part"), NOTES / name)


def verify_source():
    private(NOTES, True)
    manifest = NOTES / "manifest.json"
    private(manifest)
    require(hashlib.sha256(manifest.read_bytes()).hexdigest() == MANIFEST_SHA, "MANIFEST_SHA")
    data = read(manifest)
    require(type(data) is dict and 1 <= len(data) <= 256, "MANIFEST_SHAPE")
    inventory = set()
    for path in (NOTES / "source").rglob("*"):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            private(path, True)
        else:
            private(path)
            inventory.add(path.relative_to(NOTES / "source").as_posix())
    require(inventory == set(data), "SOURCE_INVENTORY")
    total = 0
    private(NOTES / "source", True)
    for relative, digest in data.items():
        parts = Path(relative).parts
        require(
            parts[:2] == ("src", "xgw") and ".." not in parts and relative.endswith(".py"),
            "SOURCE_PATH",
        )
        path = NOTES / "source" / relative
        private(path)
        total += path.stat().st_size
        require(path.stat().st_size <= 2097152 and total <= 16777216, "SOURCE_LIMIT")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, "SOURCE_SHA")
    return len(data)


def audit(event, args):
    if event == "xgw.hook_fixture.probe":
        AUDIT["ready"] = True
        return
    forbidden = event.startswith("socket.") or event in {
        "subprocess.Popen",
        "os.system",
        "os.posix_spawn",
        "os.exec",
        "os.fork",
        "os.forkpty",
        "os.kill",
        "os.killpg",
        "ctypes.dlopen",
        "ctypes.call_function",
    }
    if event == "import" and args and str(args[0]).split(".")[0] == "xgw":
        forbidden = True
    write_paths = []
    if event == "open" and len(args) > 2 and type(args[2]) is int:
        if args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            write_paths = [args[0]]
    elif event in ("os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "shutil.rmtree"):
        write_paths = [args[0]]
    elif event in ("os.rename", "os.link", "os.symlink"):
        write_paths = list(args[:2])
    for path in write_paths:
        if isinstance(path, (str, bytes, os.PathLike)):
            target = os.path.abspath(os.fsdecode(path))
            if os.path.commonpath((str(NOTES), target)) != str(NOTES):
                forbidden = True
    if forbidden:
        if not AUDIT["probe"]:
            AUDIT["violations"] += 1
        raise ScopeStop("FORBIDDEN_TEST_IO")


def install_audit():
    os.chdir(NOTES)
    sys.addaudithook(audit)
    sys.audit("xgw.hook_fixture.probe")
    require(AUDIT["ready"], "AUDIT_NOT_REGISTERED")
    AUDIT["probe"] = True
    try:
        for event in ("subprocess.Popen", "socket.__new__"):
            try:
                sys.audit(event, None, None, None, None)
            except ScopeStop:
                pass
            else:
                raise ValueError("AUDIT_DID_NOT_REFUSE")
    finally:
        AUDIT["probe"] = False


def load_source():
    root = NOTES / "source/src/xgw"
    spec = importlib.util.spec_from_file_location(
        "frozen_ad", root / "__init__.py", submodule_search_locations=[str(root)]
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[pkg.__name__] = pkg
    spec.loader.exec_module(pkg)
    for name in (
        "ownership",
        "ownership_adapters",
        "ownership_hooks",
        "paths",
        "config",
        "net.capture",
        "net.nft",
        "net.tun",
        "freepool.backend",
        "apply.applier",
        "apply.singbox",
        "xraycore.api",
        "managed",
        "cores",
    ):
        MODULES[name] = importlib.import_module(pkg.__name__ + "." + name)


class Log:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


@contextlib.contextmanager
def patches(changes):
    previous = [(obj, name, getattr(obj, name)) for obj, name, _ in changes]
    try:
        for obj, name, value in changes:
            setattr(obj, name, value)
        yield
    finally:
        for obj, name, value in reversed(previous):
            setattr(obj, name, value)


def digest_tree(root):
    result = {}
    for path in root.rglob("*"):
        info = path.lstat()
        value = [stat.S_IMODE(info.st_mode), info.st_uid, info.st_nlink]
        if stat.S_ISREG(info.st_mode):
            value += ["FILE", hashlib.sha256(path.read_bytes()).hexdigest()]
        elif stat.S_ISDIR(info.st_mode):
            value += ["DIRECTORY"]
        elif stat.S_ISLNK(info.st_mode):
            value += ["SYMLINK", os.readlink(path)]
        else:
            value += ["OTHER"]
        result[path.relative_to(root).as_posix()] = value
    return result


class Fixture:
    def __init__(self, root):
        self.root = root
        self.work = root / "fixture"
        self.work.mkdir(mode=0o700)
        self.paths = MODULES["paths"].Paths(self.work)
        for path in (
            self.paths.run,
            self.paths.var,
            self.paths.xray_config_dir,
            self.paths.singbox_config_dir,
            self.paths.xray_dir,
        ):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.trace = []
        self.changes = []
        self.log = Log()
        self.registry = MODULES["ownership"].Registry(
            root / "registry", boot_id=BOOT, expected_uid=os.getuid(), clock_ns=lambda: 10
        )
        self.registry.initialize()
        self.coordinator = MODULES["ownership_hooks"].Coordinator(self.registry, self.verifier)

    def verifier(self, roles, value):
        mode = getattr(value, "mode", "")
        if mode in ("failed", "rejected", "deferred", "restart_deferred"):
            return MODULES["ownership_adapters"].Verification()
        outcome = (
            "ROLLED_BACK" if mode == "rollback" else "NOOP" if mode == "unchanged" else "COMMITTED"
        )
        return MODULES["ownership_adapters"].Verification(outcome, (("FILES", True),))

    def event(self, name):
        self.trace.append(name)

    def runner(self, argv, **kwargs):
        self.event("RUNNER")
        return ""

    def write(self, path, value):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def capture(self, variant):
        module, nft, tun = (MODULES[n] for n in ("net.capture", "net.nft", "net.tun"))
        cfg = NS(
            capture=NS(local=False, lan=False, tun=False, tun_name=""), tailscale=NS(route="vpn")
        )
        obj = module.Capture(cfg, self.paths, runner=self.runner, logger=self.log)
        rules = nft.Rules("", "", False, False, 12345, 1, 2, (), (), False, "", ())
        obj.mode = lambda: "on"
        obj.effective_mode = lambda: "on"
        obj.rules = lambda *args: rules
        obj._applied = lambda: None
        obj._routes_up = lambda *args: self.event("ROUTES_UP")
        obj._routes_down = lambda *args: self.event("ROUTES_DOWN")
        obj._congestion = lambda: self.event("CONGESTION")
        obj._congestion_restore = lambda: self.event("CONGESTION_RESTORE")
        obj._forwarding_restore = lambda: self.event("FORWARD_RESTORE")
        obj._baseline = lambda *args: ("synthetic", "", True)
        obj._verified_guard = None
        if variant != "C_LOAD_OFF":
            obj._load = lambda mode: self.event("LOAD") or mode
        if variant == "C_SAVE":
            operation = lambda: obj._save(enabled=True)
        elif variant == "C_LOAD_OFF":
            operation = lambda: obj._load("off")
        elif variant in ("C_UP", "C_ENABLE", "C_DISABLE", "C_OPEN", "C_CLOSE", "C_DOWN"):
            method = variant[2:].lower()
            if variant in ("C_CLOSE", "C_DISABLE", "C_DOWN"):
                obj.open_marker.touch()
            operation = lambda: getattr(obj, method)()
        elif variant == "C_TUN":
            rules = NS(tun=True, tun_name="fixture", capture=True)
            self.changes += [
                (nft, "loaded_chains", lambda runner: {"output"}),
                (tun, "ensure", lambda *args: self.event("TUN_ENSURE")),
            ]
            operation = obj.restore_tun
        elif variant == "C_TIDY":
            cfg.capture.tun_name = "fixture"
            self.changes += [
                (tun, "present", lambda *args: True),
                (tun, "remove", lambda *args: self.event("TUN_REMOVE")),
            ]
            operation = obj.tidy
        else:
            rules = NS(capture=True)
            self.changes += [(nft, "ts_elements", lambda *args: "synthetic")]
            if variant == "C_TS_EARLY":
                cfg.tailscale.route = "direct"
                obj.ts_marker.touch()
                operation = lambda: obj.tailscale_direct(False)
            elif variant == "C_TS_FALLBACK":
                cfg.tailscale.route = "direct"
                operation = lambda: obj.tailscale_fallback(True)
            else:
                operation = lambda: obj.tailscale_direct(True)
        return obj, operation

    def backend(self, variant):
        module = MODULES["freepool.backend"]
        obj = module.Backend(
            self.paths, runner=self.runner, logger=self.log, sys_net=self.work / "sys-net"
        )
        obj._main_pid = lambda lease: 4242
        obj._wait_guarded = lambda lease: None
        lease = module.Lease(
            gen="a" * 10, index=1, peer="192.0.2.1", port=443, socks_pass="fixture"
        )
        if variant == "B_SAVE":
            obj.leases[lease.gen] = lease
            operation = obj._save_peers
        elif variant == "B_ELEMENT":
            operation = lambda: obj._nft_element("add", lease.element)
        elif variant == "B_PREPARE":
            operation = lambda: obj.prepare(
                peer="192.0.2.1",
                port=443,
                host="fixture.invalid",
                user="fixture",
                password="fixture",
                lan=(),
                xray_bin=self.work / "dummy",
            )
        elif variant == "B_STOP":
            obj.leases[lease.gen] = lease
            operation = lambda: obj.stop(lease)
        else:
            operation = obj.reconcile
        return obj, operation

    def xray(self, variant):
        module = MODULES["apply.applier"]
        service = NS(restart=lambda: self.event("SERVICE"))
        api = NS(balancer_info=lambda *args: self.event("API_READ"))
        obj = module.Applier(
            NS(apply=NS(restart_window="00:00-23:59")),
            self.paths,
            api,
            service,
            validator=lambda value: (True, ""),
            logger=self.log,
            runner=self.runner,
        )
        obj._prepare_tun = lambda: None
        if variant == "X_APPLY":
            operation = lambda: obj.apply({"inbounds": []})
        else:
            self.write(self.paths.xray_config_file, {"inbounds": []})
            self.write(self.paths.last_good_file, {"inbounds": [], "log": {}})
            operation = lambda: obj.rollback("fixture")
        return obj, operation

    def singbox(self, variant):
        module = MODULES["apply.singbox"]
        service = NS(
            is_active=lambda: False,
            start=lambda: self.event("SERVICE"),
            reload=lambda: self.event("SERVICE"),
            stop=lambda: self.event("SERVICE"),
            restart=lambda: self.event("SERVICE"),
        )
        obj = module.SingboxCore(
            NS(), self.paths, service, validator=lambda value: (True, ""), logger=self.log
        )
        config = {"inbounds": []}
        if variant == "S_APPLY":
            operation = lambda: obj.apply(config, reload=True)
        elif variant == "S_EQUAL":
            self.write(self.paths.singbox_config_file, config)
            self.write(self.paths.singbox_pending_file, {"stale": True})
            operation = lambda: obj.apply(config, reload=True)
        elif variant == "S_REMOVE":
            self.write(self.paths.singbox_config_file, config)
            operation = lambda: obj.apply(None, reload=True)
        elif variant == "S_DEFER":
            # Verifier in this fixture explicitly accepts deferred file-only publication.
            self.verifier = lambda roles, value: MODULES["ownership_adapters"].Verification(
                "COMMITTED", (("FILES", True),)
            )
            self.coordinator.verifier = self.verifier
            operation = lambda: obj.apply(config, reload=False)
        elif variant == "S_ROLLBACK":
            self.write(self.paths.singbox_config_file, {"inbounds": [], "log": {}})
            self.write(self.paths.singbox_last_good_file, config)
            operation = lambda: obj.rollback("fixture")
        else:
            self.write(self.paths.singbox_config_file, config)
            operation = obj.restart
        return obj, operation

    def api(self, variant):
        obj = MODULES["xraycore.api"].ApiClient(self.work / "absent")
        object.__setattr__(obj, "_run", lambda *args, **kwargs: self.event("API_STUB") or "")
        calls = {
            "API_ADD_OUT": lambda: obj.add_outbounds([]),
            "API_RM_OUT": lambda: obj.remove_outbound("fixture"),
            "API_ADD_IN": lambda: obj.add_inbounds([]),
            "API_RM_IN": lambda: obj.remove_inbound("fixture"),
            "API_ROUTING": lambda: obj.replace_routing({}),
            "API_PIN": lambda: obj.pin("fixture", "fixture"),
            "API_UNPIN": lambda: obj.unpin("fixture"),
        }
        return obj, calls[variant]

    def core(self, variant):
        module = MODULES["cores"]
        target, prev = self.paths.xray_dir, self.paths.xray_dir.with_name("xray.prev")
        (target / "xray").write_text("old")

        def version(path):
            return (1, 0, 0) if path.read_text() == "old" else (2, 0, 0)

        def download(dest, wanted, release, route):
            dest.mkdir(mode=0o700)
            (dest / "xray").write_text("new")
            return wanted, dest / "xray"

        adapter = NS(
            version=version,
            release=lambda *args: {},
            download=download,
            precheck=lambda *args: "",
            configured=lambda: False,
        )
        obj = module.Job(
            NS(),
            self.paths,
            cores={"xray": adapter},
            ways=[{}],
            logger=self.log,
            out=lambda *args: None,
        )
        if variant == "K_ROLLBACK":
            prev.mkdir(mode=0o700)
            (prev / "xray").write_text("new")
            operation = lambda: obj.rollback("xray", "fixture")
        else:
            operation = lambda: obj.update(
                "xray", "1.0.0" if variant == "K_UPDATE" else "2.0.0", "fixture"
            )
        return obj, operation

    def operation(self, variant, ownership):
        if variant.startswith("C_"):
            obj, operation = self.capture(variant)
        elif variant.startswith("B_"):
            obj, operation = self.backend(variant)
        elif variant.startswith("X_"):
            obj, operation = self.xray(variant)
        elif variant.startswith("S_"):
            obj, operation = self.singbox(variant)
        elif variant.startswith("API_"):
            obj, operation = self.api(variant)
        elif variant.startswith("K_"):
            obj, operation = self.core(variant)
        else:
            module = MODULES["managed"]

            def change(data):
                self.event("PANEL_CHANGE")
                data["fixture"] = True
                return variant == "P_UPDATE"

            return lambda: module._update(
                self.paths.etc / "panel.json", change, ownership=ownership
            )
        if isinstance(obj, MODULES["xraycore.api"].ApiClient):
            object.__setattr__(obj, "ownership", ownership)
        else:
            obj.ownership = ownership
        return operation


def run_matrix(fixture, variant, mode):
    global CASE_DETAILS
    CASE_DETAILS = {
        "variant": variant,
        "mode": mode,
        "expected_return": RETURNS[variant],
        "observed_return": "NOT_RUN",
        "stub_calls": None,
        "registry_receipts": None,
    }
    coordinator = None if mode == "LEGACY" else fixture.coordinator
    operation = fixture.operation(variant, coordinator)
    if mode == "FENCED":
        fixture.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
    before = digest_tree(fixture.work)
    with patches(fixture.changes):
        if mode == "FENCED":
            try:
                operation()
            except MODULES["ownership_hooks"].MutationBlocked:
                pass
            else:
                raise ValueError("CALLSITE_DID_NOT_REFUSE")
            require(
                before == digest_tree(fixture.work) and not fixture.trace, "EFFECT_BEFORE_ADMISSION"
            )
        else:
            result = operation()
            if result is None:
                observed = "NONE"
            elif type(result) is bool:
                observed = "BOOL_TRUE" if result else "BOOL_FALSE"
            elif type(result) is int:
                observed = "ZERO" if result == 0 else "NONZERO"
            elif type(result) is str:
                observed = (
                    "MODE_" + result.upper()
                    if result in ("on", "off", "none")
                    else "TEXT"
                    if result
                    else "EMPTY_TEXT"
                )
            elif isinstance(result, MODULES["freepool.backend"].Lease):
                observed = "LEASE"
            else:
                value = getattr(result, "mode", None)
                observed = (
                    "OUTCOME_" + value.upper()
                    if value
                    in ("restart", "rollback", "started", "unchanged", "removed", "deferred")
                    else "UNSUPPORTED"
                )
            CASE_DETAILS["observed_return"] = observed
            require(observed == RETURNS[variant], "BUSINESS_RESULT_CHANGED")
            require(
                fixture.coordinator.last_execution is not None if mode == "OWNED" else True,
                "MISSING_EXECUTION",
            )
    summary = fixture.registry.summary()
    require(summary["writers"] == 0 and summary["unknown"] == 0, "TICKET_LEAK")
    require(summary["receipts"] == (1 if mode == "OWNED" else 0), "RECEIPT_COUNT")
    return {
        "fixture_unchanged": before == digest_tree(fixture.work),
        "stub_calls": len(fixture.trace),
        "registry_receipts": summary["receipts"],
        "mode": mode,
    }


def extras(fixture, name):
    h, a = MODULES["ownership_hooks"], MODULES["ownership_adapters"]
    c = fixture.coordinator
    if name == "H_NO_VERIFIER":
        c.verifier = None
        try:
            c.call("CORE", lambda: fixture.event("FORBIDDEN"))
        except h.MutationBlocked:
            pass
        else:
            raise ValueError("UNCONFIGURED_ADMITTED")
        require(
            not fixture.trace and fixture.registry.summary()["receipts"] == 0, "UNCONFIGURED_EFFECT"
        )
    elif name == "H_NESTED_ROLES":
        seen = []
        c.verifier = lambda roles, value: (
            seen.append(roles) or a.Verification("NOOP", (("FILES", True),))
        )
        c.call("CORE", lambda: c.call("CAPTURE", lambda: fixture.event("NESTED")))
        require(
            seen == [frozenset({"CORE", "CAPTURE"})]
            and fixture.registry.summary()["receipts"] == 1,
            "NESTED_RECEIPT",
        )
    elif name == "H_TAINT":

        def fail():
            raise ValueError("fixture")

        def operation():
            try:
                c.call("PEERS", fail)
            except ValueError:
                return None

        try:
            c.call("CORE", operation)
        except h.MutationBlocked:
            pass
        else:
            raise ValueError("TAINT_COMPLETED")
        require(fixture.registry.summary()["unknown"] == 1, "TAINT_NOT_RECORDED")
    elif name in ("H_EXCEPTION", "H_TERMINAL"):
        error = ValueError if name == "H_EXCEPTION" else SystemExit

        def fail():
            raise error("fixture")

        try:
            c.call("CORE", fail)
        except (ValueError, SystemExit) as exc:
            require(type(exc) is error, "EXCEPTION_CHANGED")
        else:
            raise ValueError("EXCEPTION_SWALLOWED")
        require(fixture.registry.summary()["unknown"] == 1, "EXCEPTION_TICKET")
    elif name in ("H_GENERATOR", "H_NESTED_GENERATOR"):

        def values():
            yield 1

        value = values()

        def nested():
            try:
                c.call("API", lambda: value)
            except h.MutationBlocked:
                return None

        try:
            try:
                c.call("CORE", nested if name == "H_NESTED_GENERATOR" else lambda: value)
            except h.MutationBlocked:
                pass
            else:
                raise ValueError("GENERATOR_COMPLETED")
        finally:
            value.close()
        require(fixture.registry.summary()["unknown"] == 1, "DEFERRED_TICKET")
    elif name == "H_THREAD":
        errors = []

        def other():
            try:
                c.call("API", lambda: fixture.event("THREAD"))
            except Exception as exc:
                errors.append(type(exc).__name__)

        def operation():
            thread = threading.Thread(target=other)
            thread.start()
            thread.join(timeout=3)
            require(not thread.is_alive() and not errors, "THREAD_FAILED")

        c.call("CORE", operation)
        require(fixture.registry.summary()["receipts"] == 2, "THREAD_BORROWED_TICKET")
    elif name == "H_FOREIGN_CONTEXT":
        c.local.session = {
            "pid": -1,
            "thread": threading.get_ident(),
            "active": True,
            "roles": set(),
            "tainted": False,
        }
        try:
            try:
                c.call("CORE", lambda: fixture.event("FORBIDDEN"))
            except h.MutationBlocked:
                pass
            else:
                raise ValueError("FOREIGN_CONTEXT_ACCEPTED")
        finally:
            c.local.session = None
        require(not fixture.trace, "FOREIGN_EFFECT")
    elif name == "E_BACKEND_COMPENSATION":
        obj, operation = fixture.backend("B_PREPARE")
        obj.ownership = c

        def failing(argv, **kwargs):
            fixture.event("RUNNER")
            if argv[:3] == ["ip", "link", "add"]:
                raise OSError("fixture")
            return ""

        obj.runner = failing
        try:
            operation()
        except MODULES["freepool.backend"].BackendError:
            pass
        else:
            raise ValueError("BACKEND_FAILURE_LOST")
        require(not obj.leases and fixture.registry.summary()["unknown"] == 1, "COMPENSATION_SCOPE")
    elif name == "E_FAILED_OUTCOME":
        obj, operation = fixture.xray("X_APPLY")
        obj.ownership = c
        obj._restart_and_wait = lambda: "synthetic failure"
        try:
            operation()
        except h.MutationBlocked:
            pass
        else:
            raise ValueError("FAILED_OUTCOME_COMPLETED")
        require(fixture.registry.summary()["unknown"] == 1, "FAILED_OUTCOME_TICKET")
    elif name == "E_SINGBOX_ROLLBACK":
        obj, operation = fixture.singbox("S_APPLY")
        obj.ownership = c
        fixture.write(fixture.paths.singbox_config_file, {"inbounds": [], "log": {}})

        def fail(config):
            return "fixture"

        obj._start_or_reload = fail
        result = operation()
        require(
            result.mode == "rollback" and fixture.registry.summary()["receipts"] == 1,
            "ROLLBACK_RECEIPT",
        )
    elif name.startswith("R_"):
        obj, _ = fixture.api("API_PIN")
        object.__setattr__(obj, "ownership", c)
        fixture.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
        calls = {
            "R_ADDRESS": obj.address,
            "R_OUTBOUNDS": obj.list_outbounds,
            "R_INBOUNDS": obj.list_inbounds,
            "R_BALANCER": lambda: obj.balancer_info("fixture"),
        }
        calls[name]()
        require(fixture.registry.summary()["receipts"] == 0, "READER_WRITER_RECEIPT")
    return {
        "stub_calls": len(fixture.trace),
        "registry_receipts": fixture.registry.summary()["receipts"],
    }


EXTRAS = (
    "H_NO_VERIFIER",
    "H_NESTED_ROLES",
    "H_TAINT",
    "H_EXCEPTION",
    "H_TERMINAL",
    "H_GENERATOR",
    "H_NESTED_GENERATOR",
    "H_THREAD",
    "H_FOREIGN_CONTEXT",
    "E_BACKEND_COMPENSATION",
    "E_FAILED_OUTCOME",
    "E_SINGBOX_ROLLBACK",
    "R_ADDRESS",
    "R_OUTBOUNDS",
    "R_INBOUNDS",
    "R_BALANCER",
)


def batch():
    global CASE_DETAILS
    create(NOTES / "worker-claimed.json", {"claimed": True})
    os.umask(0o077)
    source_count = verify_source()
    install_audit()
    load_source()
    cases = NOTES / "cases"
    cases.mkdir(mode=0o700)
    rows = []
    expected = [v + "__" + m for v in VARIANTS for m in MODES] + list(EXTRAS)
    started = time.monotonic()
    for name in expected:
        CASE_DETAILS = None
        fixture = None
        root = cases / f"case-{len(rows) + 1:03d}"
        root.mkdir(mode=0o700)
        before = time.monotonic()
        try:
            fixture = Fixture(root)
            details = (
                run_matrix(fixture, *name.split("__")) if "__" in name else extras(fixture, name)
            )
            row = {"case": name, "passed": True, "details": details}
        except Exception as exc:
            source, line = "UNKNOWN", None
            tb = exc.__traceback__
            while tb is not None:
                filename = Path(tb.tb_frame.f_code.co_filename)
                try:
                    relative = filename.relative_to(NOTES / "source").as_posix()
                    source, line = relative, tb.tb_lineno
                except ValueError:
                    if filename == Path(__file__).resolve():
                        source, line = "tests/stand/wave3_source_hooks.py", tb.tb_lineno
                tb = tb.tb_next
            row = {
                "case": name,
                "passed": False,
                "reason": "SOURCE_CASE_FAILED",
                "error_class": type(exc).__name__,
                "public_error_source": source,
                "public_error_line": line,
            }
        row["elapsed_ms"] = int((time.monotonic() - before) * 1000)
        if CASE_DETAILS is not None and "details" not in row:
            if fixture is not None:
                CASE_DETAILS["stub_calls"] = len(fixture.trace)
                with contextlib.suppress(Exception):
                    CASE_DETAILS["registry_receipts"] = fixture.registry.summary()["receipts"]
            row["details"] = CASE_DETAILS
        rows.append(row)
        atomic("progress.json", {"final": False, "completed": len(rows), "cases": rows})
        if AUDIT["violations"]:
            break
    passed = sum(r["passed"] for r in rows)
    result = {
        "marker": "SOURCE_HOOK_BATCH_RECORDED"
        if passed == len(expected)
        else "SOURCE_HOOK_BATCH_PARTIAL",
        "scope": "OPT_IN_SOURCE_HOOKS_FAKE_EFFECTS_ONLY",
        "expected": len(expected),
        "completed": len(rows),
        "passed": passed,
        "cases": rows,
        "source_files": source_count,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "audit_registered": AUDIT["ready"],
        "unexpected_forbidden_io": AUDIT["violations"],
        "workload_subprocesses": 0,
        "installed_runtime_changed": False,
        "runtime_actor_binding_implemented": False,
        "runtime_writer_fence_verified": False,
        "runtime_verifier_implemented": False,
        "runtime_recovery_implemented": False,
        "repair_implemented": False,
        "active_faults_authorized": False,
        "network_requests": 0,
        "live_gateway_operations": 0,
    }
    atomic("summary.json", result)


if __name__ == "__main__":
    try:
        require(os.geteuid() != 0 and len(sys.argv) == 2, "OWNER_OR_MODE")
        private(NOTES, True)
        command = sys.argv[1]
        if command in ("status", "show"):
            for name in ("summary.json", "progress.json"):
                if (NOTES / name).exists():
                    print(json.dumps({"file": name, "data": read(NOTES / name)}))
                    break
            else:
                print(json.dumps({"file": None, "status": "NO_RECORDED_RESULT"}))
        elif command == "start":
            verify_source()
            create(NOTES / "started.json", {"started": True})
            subprocess.Popen(
                [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_batch"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print("SOURCE_HOOK_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception as exc:
        print("SOURCE_HOOK_BATCH_STOP", type(exc).__name__)
        raise SystemExit(3) from None
