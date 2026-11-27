# ThinkCentre · привязка замера FreePool к служебному маршруту

Ubuntu 24.04 LTS, кандидат `21e37f97ad216b1e3b68f7903a560f87d4e2c694`. Один проход проверяет
служебный вход и маршрут пробы, смену правила во время HTTP-загрузки
и отклонение чужого выхода. Включены регрессии штатного ExecStart,
обоих ядер, YouTube и R16. [Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/2b5e8166d15946c7fcdacc0b251afc41c77decc6/docs/reports/2026-11-27T112058Z_freepool-r39-execstart-reload.md) · [Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-probe-route.bundle)

Flash самостоятельно выполняет готовые команды обычным пользователем.
При недоступном терминале запросить доступ и продолжить после получения.
Изменение правил выполняется через API отдельного Xray, запросы идут
по loopback. Для регрессии ExecStart создаётся временная пользовательская
служба со случайным именем и лимитом 60 секунд. Состояние штатных служб
сверяется чтением.

## 1. Запуск

Полный клон с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
При нестандартных путях задать абсолютные `XGW_TEST_XRAY`,
`XGW_TEST_SINGBOX` и `XGW_TEST_PYTHON`. Если `/tmp` использует `noexec`,
задать абсолютный `TMPDIR` с разрешённым запуском файлов.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=21e37f97ad216b1e3b68f7903a560f87d4e2c694
BRIDGE_FIXTURE=7ae63fabe8f21128a8bb5ae15c81d2c031362c69
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-r39-probe-route.XXXXXXXX")
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' \
    "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version
systemctl --version | sed -n '1p'

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-probe-route.bundle >"$D/code.bundle"
printf '%s  %s\n' '3f44e069de6976d79c83e9fabf697ee4e5cf7d8a190b3ad3b1afc86efd3dfd2a' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests packaging pyproject.toml config.example.toml \
    docs/helpers/freepool_lifecycle.py | tar -x -C "$D/tree"
cd "$D/tree"

host_fields() {
  local unit fields
  for unit in xgw.service xgw-xray.service xgw-singbox.service \
              xgw-singbox-blue.service xgw-singbox-green.service; do
    if ! fields=$(timeout -k 1 4 systemctl show --property=LoadState,ActiveState,MainPID "$unit" \
        2>/dev/null) && [[ "$fields" != *'LoadState=not-found'* ]]; then
      return 1
    fi
    printf '%s\n%s\n' "$unit" "$fields"
  done
}
status=0
host_read_ok=0
if host_fields >"$D/before.txt"; then
  host_read_ok=1
fi
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=""
export XGW_ROOT="$D/isolated"
core_ok=0
unset XGW_XRAY_BIN XGW_TEST_FREEPOOL_XRAY
if [[ -x "$XRAY" ]] && timeout -k 2 10 "$XRAY" version >"$D/xray-version.txt" 2>&1; then
  core_ok=1
  head -n 1 "$D/xray-version.txt"
  export XGW_XRAY_BIN="$XRAY" XGW_TEST_FREEPOOL_XRAY="$XRAY"
fi

if PYTHONPYCACHEPREFIX="$D/pycache" /usr/bin/python3 -m compileall -q \
    src/xgw docs/helpers/freepool_lifecycle.py tests/conftest.py tests/test_daemon.py; then
  printf 'R39_COMPILE=PASS\n'
else
  printf 'R39_COMPILE=FAIL\n'
  status=1
fi

pytest_case() {
  timeout -k 5 300 "$TEST_PY" -B -m pytest -o addopts= -q -rs -rfE --tb=short --show-capture=no -p no:cacheprovider "$@"
}
record_case() {
  local label=$1
  shift
  if pytest_case "$@" >"$D/$label.log" 2>&1; then
    printf '%s=PASS\n' "$label"
  else
    printf '%s=FAIL\n' "$label"
    status=1
  fi
  tail -n 24 "$D/$label.log"
}

record_case R16_CONTRACTS \
    tests/test_freepool.py tests/test_freepool_sources.py tests/test_freepool_refresh.py \
    tests/test_freepool_traffic.py tests/test_freepool_candidates.py \
    tests/test_freepool_selection.py tests/test_freepool_targeted.py tests/test_freepool_cancel.py \
    tests/test_freepool_backend.py tests/test_freepool_stats.py tests/test_freepool_wan_epoch.py \
    tests/test_api_integration.py tests/test_config.py tests/test_fetch.py::test_parse_userinfo
record_case PROBE_ROUTE_CONTRACTS tests/test_freepool_traffic.py tests/test_generator.py -k 'pool or probe'
record_case EXECSTART_CONTRACTS tests/test_runtime.py -k 'systemd_measurement or systemd_runtime_generation'
record_case BRIDGE_SLOT_CONTRACTS tests/test_singbox.py -k bridge_measurement_context
record_case R39_CONTEXT \
    tests/test_runtime.py tests/test_freepool_traffic.py tests/test_singbox.py \
    tests/test_singbox_generations.py tests/test_freepool_wan_epoch.py tests/test_speed.py \
    tests/test_youtube.py
record_case SUBSCRIPTION_YOUTUBE tests/test_daemon.py tests/test_daemon_main.py -k 'youtube or media'
record_case WATCHDOG_CONTRACTS tests/test_daemon.py tests/test_conncheck.py \
    -k 'conncheck or watchdog_schedule or test_watchdog_wakes or pool_region_reload'

if [[ "$core_ok" == 1 ]]; then
  if timeout -k 5 90 env PYTHONPATH="$D/tree/src:$D/tree/tests:$D/tree/docs/helpers" \
      "$TEST_PY" -B -P - "$D/probe-route" "$XRAY" >"$D/probe-route.log" 2>&1 <<'PYTHON'
import copy
import socket
import sys
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from freepool_lifecycle import serving
from test_freepool_traffic import NOW, _daemon
from xgw.daemon import POOL_SPEED_META, YOUTUBE_META
from xgw.freepool import wan_epoch
from xgw.generator import builder, diff
from xgw.paths import Paths, atomic_write_json
from xgw.store import Store
from xgw.watch import youtube
from xgw.xraycore.api import ApiClient
from xgw.xraycore.service import ProcessXrayService


class Origin(BaseHTTPRequestHandler):
    body = b"xgw-fixture" * 100_000
    on_sample = staticmethod(lambda: None)

    def do_GET(self):
        self.server.requests.append(self.path)
        if self.path == "/sample":
            self.on_sample()
            data = self.body
            self.send_response(200)
        else:
            data = b""
            self.send_response(self.server.verdict)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


root, binary = map(Path, sys.argv[1:])
root.mkdir(mode=0o700)
paths = Paths(root)
paths.ensure()
daemon = _daemon(paths)
daemon.xray_bin = binary
clock = [NOW]
daemon.wall = lambda: clock[0]
primary, alternate = "pool-de-aaaa", "pool-de-bbbb"
daemon._pool_ids = {primary: "a" * 32, alternate: "b" * 32}
daemon._freepool_summary = {}
live = {primary: {"alive": True, "delay": 0.1}}
cfg = daemon.cfg
cfg.speed.youtube, cfg.speed.youtube_mbps = True, 0
password = "loopback-only"
with socket.socket() as listener, socket.socket() as api_listener:
    listener.bind(("127.0.0.1", 0))
    api_listener.bind(("127.0.0.1", 0))
    proxy_port = listener.getsockname()[1]
    api_port = api_listener.getsockname()[1]

origins = [ThreadingHTTPServer(("127.0.0.1", 0), Origin) for _ in range(2)]
for server, status in zip(origins, (204, 503)):
    server.verdict, server.requests = status, []

with (closing(Store(paths.db_file)) as store,
      serving(origins[0]) as first_port, serving(origins[1]) as other_port):
    daemon.store = store
    daemon._pool_wan = wan_epoch.Epoch(store)
    daemon._pool_policy = wan_epoch.Epoch(store, key=wan_epoch.POLICY_META_KEY)
    destination = f"http://127.0.0.1:{first_port}"
    cfg.speed.url, cfg.speed.url_fallback = f"{destination}/sample", ""
    cfg.speed.youtube_urls = [f"{destination}/check"]
    applied = {
        "log": {"loglevel": "warning"},
        "api": {"tag": "api", "listen": f"127.0.0.1:{api_port}", "services": ["RoutingService"]},
        "inbounds": [{"tag": "probe-de-aaaa", "listen": "127.0.0.1", "port": proxy_port,
                      "protocol": "http", "settings": {
                          "accounts": [{"user": builder.PROBE_USER, "pass": password}]}}],
        "outbounds": [
            {"tag": tag, "protocol": "freedom", "settings": {"redirect": f"127.0.0.1:{port}"}}
            for tag, port in ((primary, first_port), (alternate, other_port))
        ],
        "routing": {"rules": [{"type": "field", "inboundTag": ["probe-de-aaaa"],
                               "outboundTag": primary}]},
    }
    redirected = copy.deepcopy(applied)
    redirected["routing"]["rules"][0]["outboundTag"] = alternate
    atomic_write_json(paths.xray_config_file, applied)
    daemon.service = ProcessXrayService(binary, paths.xray_config_file)
    try:
        daemon.service.start()
        daemon._observe_pool_measurement_path()
        daemon._pool_step(applied, live)
        daemon._pool_speed_step(applied, live, 100.0)
        daemon._pool_step(applied, live)
        speed_before = store.get_meta(POOL_SPEED_META)
        assert speed_before and daemon._pool_summary()["traffic"]["servers"][0]["mbps"] is not None

        daemon._pool_speed_ran = False
        daemon._youtube_step([], applied, live, 120.0)
        youtube_before = store.get_meta(YOUTUBE_META)
        assert youtube_before and daemon._pool_summary()["traffic"]["servers"][0]["youtube"] == "ok"
        assert origins[0].requests == ["/sample", "/check"] and not origins[1].requests
        print("R39_PROBE_BOUND=PASS", flush=True)

        api = ApiClient(binary, server=f"127.0.0.1:{api_port}", timeout=4)

        def change_during_sample():
            plan = diff.diff_configs(applied, redirected).plan
            assert plan is not None and plan.routing
            diff.apply_plan(api, plan)
            atomic_write_json(paths.xray_config_file, redirected)

        Origin.on_sample = staticmethod(change_during_sample)
        clock[0] += cfg.speed.unlimited_hours * 3600 + 1
        daemon._pool_speed_step(applied, live, 140.0)
        assert daemon._pool_measured == (primary, len(Origin.body))
        assert store.get_meta(POOL_SPEED_META) == speed_before
        row = daemon._pool_summary()["traffic"]["servers"][0]
        assert row["mbps"] is None and "youtube" not in row
        print("R39_PROBE_ROUTE_CHANGED_DURING_SAMPLE=PASS", flush=True)

        confirmation = youtube.http_get_via_proxy(
            "127.0.0.1", proxy_port, f"{destination}/check", timeout=2, silence=2,
            max_total=4, proxy_user=builder.PROBE_USER, proxy_pass=password,
        )
        assert confirmation.status == 503 and origins[1].requests == ["/check"]
        daemon._pool_speed_ran = False
        daemon._youtube_ran = False
        daemon._youtube_step([], redirected, live, 160.0)
        assert origins[1].requests == ["/check"]
        assert store.get_meta(YOUTUBE_META) == youtube_before
        assert daemon._pool_pinned == primary
        print("R39_PROBE_WRONG_OUTBOUND_SKIPPED=PASS", flush=True)
    finally:
        daemon.service.stop()
PYTHON
  then
    grep '^R39_PROBE_' "$D/probe-route.log"
  else
    grep '^R39_PROBE_' "$D/probe-route.log" || true
    printf 'R39_PROBE_ROUTE=FAIL\n'
    status=1
  fi
else
  printf 'R39_PROBE_ROUTE=NOT_RUN (Xray unavailable)\n'
fi

if [[ "$core_ok" == 1 ]]; then
  if timeout -k 5 100 /usr/bin/python3 -B -P - "$D/user-execstart" "$XRAY" \
      >"$D/user-execstart.log" 2>&1 <<'PYTHON'
import hashlib
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from xgw.paths import atomic_write_json
from xgw.xraycore import service as core


def systemctl(*args, timeout=10):
    return subprocess.run(
        ["systemctl", "--user", "--no-pager", *args], capture_output=True,
        timeout=timeout, text=True,
    )


class UserUnit(core.SystemdXrayService):
    def _systemctl(self, *args, timeout=30):
        result = systemctl(*args, self.unit, timeout=timeout)
        if result.returncode:
            raise core.XrayServiceError("fixture systemctl call failed")
        return result.stdout.strip()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


root, source = map(Path, sys.argv[1:])
if systemctl("show", "--property=Version").returncode:
    print("R39_EXECSTART_USER_UNIT=NOT_RUN (no user systemd bus)")
    raise SystemExit(0)
root.mkdir(mode=0o700)
binary, stock, replacement = (root / name for name in ("custom core", "stock", "next"))
shutil.copyfile(source, binary)
binary.chmod(0o700)
stock.write_bytes(b"stock")
config = root / "config.json"
atomic_write_json(config, {"log": {"loglevel": "warning"},
                           "outbounds": [{"protocol": "freedom"}]})
name = f"xgw-freepool-r39-fixture-{secrets.token_hex(8)}.service"
service = UserUnit(name)
try:
    subprocess.run(
        ["systemd-run", "--user", "--quiet", "--collect", f"--unit={name}",
         "--property=Type=exec", "--property=RuntimeMaxSec=60s",
         "--", str(binary), "run", "-c", str(config)],
        check=True, capture_output=True, timeout=20,
    )
    runtime = service.measurement_runtime()
    assert runtime and runtime.executable == binary
    exe = Path(f"/proc/{runtime.pid}/exe")
    original = digest(binary)
    assert digest(exe) == original
    full = core.measurement_generation(service, stock)
    expected = hashlib.sha256(f"{runtime.generation}:{original}:{original}".encode())
    assert full == expected.hexdigest()
    print("R39_EXECSTART_USER_PATH=PASS", flush=True)

    live_query = service._systemctl
    wrong_path = [False]

    def reloaded_query(*args, timeout=30):
        rows = live_query(*args, timeout=timeout).splitlines()
        for index, row in enumerate(rows):
            if row.startswith("ExecStart="):
                row, count = re.subn(r" ; pid=[0-9]+ ; code=", " ; pid=0 ; code=", row)
                assert count == 1
                if wrong_path[0]:
                    row = row.replace(f"path={binary} ;", f"path={stock} ;", 1)
                rows[index] = row
        return "\n".join(rows)

    with patch.object(service, "_systemctl", reloaded_query):
        recovered = service.measurement_runtime()
        assert recovered.executable == binary and recovered.argv0_start_ticks is not None
        assert core.measurement_generation(service, stock) == full
        print("R39_RELOAD_MATCHED_MAINPID=PASS", flush=True)

        wrong_path[0] = True
        assert service.measurement_runtime().executable is None
        assert core.measurement_generation(service, stock) is None
        print("R39_RELOAD_CHANGED_PATH_REJECTED=PASS", flush=True)

    fingerprint = core._binary_fingerprint

    def only_installed(path):
        if path == exe:
            raise PermissionError
        return fingerprint(path)

    with patch.object(core, "_binary_fingerprint", only_installed):
        initial = core.measurement_generation(service, stock)
        expected = hashlib.sha256(f"{runtime.generation}:{original}".encode())
        assert initial == expected.hexdigest()
        stock.write_bytes(b"stock-edited")
        assert core.measurement_generation(service, stock) == initial

        shutil.copyfile(binary, replacement)
        with replacement.open("ab") as stream:
            stream.write(b"\nxgw-r39-execstart-fixture\n")
        replacement.chmod(0o700)
        replacement.replace(binary)
        changed = digest(binary)
        assert changed != original and digest(exe) == original
        assert service.measurement_runtime() == runtime
        expected = hashlib.sha256(f"{runtime.generation}:{changed}".encode())
        assert core.measurement_generation(service, stock) == expected.hexdigest()
        print("R39_EXECSTART_INSTALLED_ONLY=PASS", flush=True)
finally:
    assert systemctl("stop", name).returncode in (0, 5)
    assert systemctl("is-active", "--quiet", name).returncode in (3, 4)
    print("R39_EXECSTART_USER_UNIT_CLEANUP=PASS", flush=True)
PYTHON
  then
    grep -E '^R39_(EXECSTART|RELOAD)_' "$D/user-execstart.log"
  else
    grep -E '^R39_(EXECSTART|RELOAD)_' "$D/user-execstart.log" || true
    printf 'R39_EXECSTART_USER_UNIT=FAIL\n'
    status=1
  fi
else
  printf 'R39_EXECSTART_USER_UNIT=NOT_RUN (Xray unavailable)\n'
fi

if [[ "$core_ok" == 1 || -x "$SINGBOX" ]]; then
  if timeout -k 5 75 /usr/bin/python3 -B -P - "$D/images" "$XRAY" "$SINGBOX" \
      >"$D/images.log" 2>&1 <<'PYTHON'
import hashlib
import shutil
import sys
from pathlib import Path

from xgw.apply.singbox import PidfileSingboxService
from xgw.paths import atomic_write_json
from xgw.xraycore.service import ProcessXrayService, measurement_generation


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def expected(runtime, installed, loaded):
    return hashlib.sha256(f"{runtime.generation}:{installed}:{loaded}".encode()).hexdigest()


def check(label, source, root, config, start_service):
    if not source.is_file():
        print(f"R39_IMAGE_{label}=NOT_RUN (binary unavailable)")
        return
    root.mkdir(mode=0o700)
    binary = root / "core"
    replacement = root / "next"
    config_path = root / "config.json"
    shutil.copyfile(source, binary)
    binary.chmod(0o700)
    atomic_write_json(config_path, config)
    service = start_service(binary, config_path)
    try:
        service.start()
        first = service.measurement_runtime()
        assert first and first.pid > 0
        exe = Path(f"/proc/{first.pid}/exe")
        initial = digest(binary)
        assert digest(exe) == initial
        key = measurement_generation(service, binary)
        assert key == expected(first, initial, initial)

        shutil.copyfile(binary, replacement)
        replacement.chmod(0o700)
        replacement.replace(binary)
        assert measurement_generation(service, binary) == key
        shutil.copyfile(binary, replacement)
        with replacement.open("ab") as stream:
            stream.write(b"\\nxgw-r39-image-fixture\\n")
        replacement.chmod(0o700)
        replacement.replace(binary)
        updated = digest(binary)
        assert updated != initial and digest(exe) == initial
        assert service.measurement_runtime() == first
        assert measurement_generation(service, binary) == expected(first, updated, initial)
        print(f"R39_IMAGE_{label}_ATOMIC_REPLACE=PASS", flush=True)

        service.restart()
        second = service.measurement_runtime()
        assert second and second != first
        assert digest(Path(f"/proc/{second.pid}/exe")) == updated
        assert measurement_generation(service, binary) == expected(second, updated, updated)
        print(f"R39_IMAGE_{label}_RESTART=PASS", flush=True)
    finally:
        service.stop()
    assert measurement_generation(service, binary) is None


root, xray, singbox = map(Path, sys.argv[1:])
root.mkdir(mode=0o700)
check("XRAY", xray, root / "xray", {
    "log": {"loglevel": "warning"}, "outbounds": [{"protocol": "freedom"}],
}, ProcessXrayService)
check("SINGBOX", singbox, root / "singbox", {
    "log": {"level": "warn"}, "outbounds": [{"type": "direct", "tag": "direct"}],
}, lambda binary, config: PidfileSingboxService(binary, config, config.with_suffix(".pid")))
PYTHON
  then
    grep '^R39_IMAGE_' "$D/images.log"
  else
    grep '^R39_IMAGE_' "$D/images.log" || true
    printf 'R39_IMAGE_PROBE=FAIL\n'
    status=1
  fi
else
  printf 'R39_IMAGE_PROBE=NOT_RUN (no installed core)\n'
fi

if [[ "$core_ok" == 1 ]]; then
  if timeout -k 5 65 env PYTHONPATH="$D/tree/src:$D/tree/tests:$D/tree/docs/helpers" \
      "$TEST_PY" -B -P - "$XRAY" "$D/youtube-probe" >"$D/youtube-probe.log" 2>&1 <<'PYTHON'
import json
import socket
import sys
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from freepool_lifecycle import serving
from test_freepool_traffic import NOW, _daemon
from xgw.daemon import YOUTUBE_META, YOUTUBE_RETRY
from xgw.freepool import wan_epoch
from xgw.generator import builder
from xgw.paths import Paths, atomic_write_json
from xgw.store import Store
from xgw.xraycore.service import ProcessXrayService


class Origin(BaseHTTPRequestHandler):
    status = 503
    requests = 0
    on_request = staticmethod(lambda: None)

    def do_GET(self):
        Origin.requests += 1
        self.on_request()
        self.send_response(self.status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args):
        pass


binary, root = map(Path, sys.argv[1:])
assert root.is_absolute()
root.mkdir(mode=0o700)
paths = Paths(root)
paths.ensure()
daemon = _daemon(paths)
daemon.xray_bin = binary
clock = [NOW]
daemon.wall = lambda: clock[0]
tag, key = "pool-de-aaaa", "a" * 32
daemon._pool_ids = {tag: key}
daemon._freepool_summary = {}
cfg = daemon.cfg
cfg.speed.youtube, cfg.speed.youtube_mbps = True, 0
password = "loopback-only"
live = {tag: {"alive": True, "delay": 0.1}}
with socket.socket() as reservation:
    reservation.bind(("127.0.0.1", 0))
    proxy_port = reservation.getsockname()[1]

with (closing(Store(paths.db_file)) as store,
      serving(ThreadingHTTPServer(("127.0.0.1", 0), Origin)) as port):
    daemon.store = store
    daemon._pool_wan = wan_epoch.Epoch(store)
    daemon._pool_policy = wan_epoch.Epoch(store, key=wan_epoch.POLICY_META_KEY)
    cfg.speed.youtube_urls = [f"http://127.0.0.1:{port}/fixture"]
    applied = {
        "log": {"loglevel": "warning"},
        "inbounds": [{"tag": "probe-de-aaaa", "listen": "127.0.0.1", "port": proxy_port,
                      "protocol": "http", "settings": {
                          "accounts": [{"user": builder.PROBE_USER, "pass": password}]}}],
        "outbounds": [{"tag": tag, "protocol": "freedom",
                       "settings": {"redirect": f"127.0.0.1:{port}"}}],
    }
    atomic_write_json(paths.xray_config_file, applied)
    daemon.service = ProcessXrayService(binary, paths.xray_config_file)
    try:
        daemon.service.start()
        daemon._observe_pool_measurement_path()
        daemon._pool_step(applied, live)
        daemon._youtube_step([], applied, live, clock[0])
        assert json.loads(store.get_meta(YOUTUBE_META))[key]["fails"] == 1
        clock[0] += YOUTUBE_RETRY
        daemon._youtube_step([], applied, live, clock[0])
        first = json.loads(store.get_meta(YOUTUBE_META))[key]
        assert Origin.requests == 2 and first["fails"] == 2 and first["state"] == "blocked"
        assert daemon._youtube_bad(key, pool_tag=tag)
        print("R39_YOUTUBE_SAME_CONTEXT=PASS")

        daemon._observe_pool_wan = lambda: daemon._pool_wan.observe("fixture-other-wan")
        daemon._observe_pool_measurement_path()
        assert "youtube" not in daemon._pool_summary()["traffic"]["servers"][0]
        daemon._youtube_step([], applied, live, clock[0])
        saved = store.get_meta(YOUTUBE_META)
        second = json.loads(saved)[key]
        assert Origin.requests == 3 and second["fails"] == 1
        assert second["context"] != first["context"]
        assert not daemon._youtube_bad(key, pool_tag=tag) and daemon._pool_pinned == tag
        print("R39_YOUTUBE_NEW_WAN=PASS")

        Origin.status = 204
        Origin.on_request = staticmethod(lambda: setattr(cfg.free_pool, "region", "US"))
        clock[0] += YOUTUBE_RETRY
        daemon._youtube_step([], applied, live, clock[0])
        assert Origin.requests == 4 and store.get_meta(YOUTUBE_META) == saved
        assert "youtube" not in daemon._pool_summary()["traffic"]["servers"][0]
        Origin.on_request = staticmethod(lambda: None)
        daemon._youtube_step([], applied, live, clock[0])
        fresh = json.loads(store.get_meta(YOUTUBE_META))[key]
        assert Origin.requests == 5 and fresh["state"] == "ok" and fresh["fails"] == 0
        assert daemon._pool_summary()["traffic"]["servers"][0]["youtube"] == "ok"
        print("R39_YOUTUBE_POLICY_RACE=PASS")
    finally:
        daemon.service.stop()
PYTHON
  then
    grep '^R39_YOUTUBE_' "$D/youtube-probe.log"
  else
    printf 'R39_YOUTUBE_LOOPBACK=FAIL\n'
    status=1
  fi
else
  printf 'R39_YOUTUBE_LOOPBACK=NOT_RUN (Xray unavailable)\n'
fi

if [[ -x "$XRAY" && -x "$SINGBOX" ]]; then
  if timeout -k 2 10 "$SINGBOX" version >"$D/singbox-version.log" 2>&1; then
    head -n 1 "$D/singbox-version.log"
  else
    printf 'SINGBOX_VERSION=FAIL\n'
    status=1
  fi
  if git -C "$REPO" show "$BRIDGE_FIXTURE:docs/handoff/FREEPOOL-R39-SINGBOX-CONTEXT-2026-11-26.md" \
      >"$D/bridge-source.md" &&
    /usr/bin/python3 -I -B - "$D" <<'PYTHON'
import sys
from pathlib import Path

root = Path(sys.argv[1])
source = (root / "bridge-source.md").read_text(encoding="utf-8")
marker = "<<'PYTHON'\n"
assert source.count(marker) == 1
_, _, content = source.partition(marker)
script, end, _ = content.partition("\nPYTHON\n")
assert end and 'fingerprint = "a" * 32' in script
assert 'print("R39_BRIDGE_LOOPBACK=PASS")' in script
compile(script, "pinned-bridge", "exec")
(root / "bridge.py").write_text(script + "\n", encoding="utf-8")
PYTHON
  then
    if timeout -k 5 45 /usr/bin/python3 -B -P "$D/bridge.py" "$D" "$XRAY" "$SINGBOX" \
        >"$D/bridge.log" 2>&1; then
      grep '^R39_BRIDGE_LOOPBACK=PASS$' "$D/bridge.log"
    else
      printf 'R39_BRIDGE_LOOPBACK=FAIL\n'
      status=1
    fi
  else
    printf 'R39_BRIDGE_LOOPBACK=NOT_RUN (pinned fixture unavailable)\n'
    status=1
  fi
else
  printf 'R39_BRIDGE_LOOPBACK=NOT_RUN (both cores required)\n'
fi

# Считать контекст штатных сервисов. Ключи, PID и пути не выводятся.
if ! timeout -k 3 35 /usr/bin/python3 -B -P - <<'PYTHON'
import json
import time
from pathlib import Path

from xgw.apply.singbox import SystemdSingboxService
from xgw.apply.singbox_process import unit as singbox_unit
from xgw.paths import Paths
from xgw.xraycore.service import (
    SystemdXrayService, _binary_fingerprint, measurement_generation,
)

paths = Paths(root=Path("/"))
services = [("XRAY", SystemdXrayService(), paths.xray_bin)]
try:
    state = json.loads((paths.run / "status.json").read_bytes())
    if not 0 <= time.time() - float(state["updated"]) <= 180:
        raise ValueError("stale status")
    slot = state["singbox"]["generations"]["active"]
    selected = singbox_unit(slot)
except (OSError, ValueError, KeyError, TypeError, AttributeError):
    print("R39_HOST_SINGBOX=NOT_RUN (active slot unavailable)")
else:
    print(f"R39_HOST_SINGBOX_SLOT={slot}")
    services.append(("SINGBOX", SystemdSingboxService(selected), paths.singbox_bin))
failed = False
for label, service, path in services:
    runtime = service.measurement_runtime()
    if runtime is None:
        print(f"R39_HOST_{label}=NOT_RUN (service generation unavailable)")
        continue
    if runtime.executable is None:
        try:
            with Path(f"/proc/{runtime.pid}/cmdline").open("rb") as stream:
                argv = "READABLE" if stream.read(1) else "EMPTY"
        except PermissionError:
            argv = "DENIED"
        except OSError:
            argv = "UNAVAILABLE"
        print(f"R39_HOST_{label}_CMDLINE={argv}")
        print(f"R39_HOST_{label}=FAIL (ExecStart path unconfirmed)")
        failed = True
        continue
    location = "STANDARD" if runtime.executable == path else "CUSTOM"
    provenance = "ARGV0" if runtime.argv0_start_ticks is not None else "EXECSTART_PID"
    print(f"R39_HOST_{label}_EXECSTART={location}")
    print(f"R39_HOST_{label}_EXECSTART_SOURCE={provenance}")
    source = "LOADED_IMAGE"
    try:
        _binary_fingerprint(Path(f"/proc/{runtime.pid}/exe"))
    except PermissionError:
        source = "INSTALLED_ONLY"
    except OSError:
        print(f"R39_HOST_{label}=NOT_RUN (active executable could not be read)")
        continue
    print(f"R39_HOST_{label}_SOURCE={source}")
    key = measurement_generation(service, path)
    stable = bool(key) and key == measurement_generation(service, None)
    print(f"R39_HOST_{label}=" + ("PASS" if stable else "FAIL"))
    failed = failed or not stable
raise SystemExit(int(failed))
PYTHON
then
  printf 'R39_HOST_KEYS_FAILED\n'
  status=1
fi

if [[ "$core_ok" == 1 ]]; then
  for trial in 1 2 3; do
    if timeout -k 5 75 /usr/bin/python3 -B -P docs/helpers/freepool_lifecycle.py \
        region-route --xray "$XRAY" --root "$D/region-route-$trial" \
        >"$D/region-route-$trial.log" 2>&1; then
      printf 'R16_REGION_ROUTE_%s=PASS\n' "$trial"
    else
      printf 'R16_REGION_ROUTE_%s=FAIL\n' "$trial"
      status=1
    fi
    grep -E '^(OBSERVED R16_|R16_ROUTE_)' "$D/region-route-$trial.log" || true
  done
else
  printf 'R16_REGION_ROUTE=NOT_RUN (Xray unavailable)\n'
fi

for scenario in rotation certificate api-switch; do
  if [[ "$core_ok" != 1 ]]; then
    printf '%s=NOT_RUN (Xray unavailable)\n' "$scenario"
    continue
  fi
  if [[ "$scenario" == certificate ]] && ! command -v openssl >/dev/null; then
    printf '%s=NOT_RUN (OpenSSL unavailable)\n' "$scenario"
    continue
  fi
  if timeout -k 5 75 /usr/bin/python3 -B -P docs/helpers/freepool_lifecycle.py \
      "$scenario" --xray "$XRAY" --root "$D/$scenario" >"$D/$scenario.log" 2>&1; then
    printf '%s=PASS\n' "$scenario"
  else
    printf '%s=FAIL\n' "$scenario"
    status=1
  fi
  grep -E '^(OBSERVED |F13_|R16_ROUTE_)' "$D/$scenario.log" || true
done

if [[ "$host_read_ok" == 1 ]] && host_fields >"$D/after.txt"; then
  if cmp -s "$D/before.txt" "$D/after.txt"; then
    printf 'R39_HOST_FIELDS_MATCH\n'
  else
    printf 'R39_HOST_FIELDS_DIFFER\n'
    status=1
  fi
else
  printf 'R39_HOST_FIELDS_NOT_RUN\n'
fi

/usr/bin/python3 -I -B - <<'PYTHON'
import json
import time
from pathlib import Path

try:
    state = json.loads(Path("/run/xgw/status.json").read_bytes())
    fresh = 0 <= time.time() - float(state["updated"]) <= 180
    free_pool = state.get("free_pool") or {}
    flow = free_pool.get("traffic") or {}
    capture = state.get("capture") or {}
    mode = free_pool.get("mode")
    devices = len(flow["devices"]) if isinstance(flow.get("devices"), list) else 0
    alive = flow.get("alive") if type(flow.get("alive")) is int else 0
    whole = flow.get("all") is True
    ready = (fresh and capture.get("mode") == "on" and capture.get("loaded") is True
             and capture.get("blocked") is False and (whole or devices > 0)
             and alive > 0 and flow.get("closed") is False)
    print(json.dumps({"check": "M3_PREFLIGHT", "fresh": fresh, "ready": ready,
                      "mode": mode if mode in ("off", "observe", "on") else "unknown",
                      "devices": devices, "alive": alive, "whole": whole}))
except (OSError, ValueError, TypeError, AttributeError, KeyError):
    print("M3_PREFLIGHT=NOT_RUN (status unavailable)")
PYTHON
exit "$status"
BASH
```

## 2. Критерии

| Блок | Ожидаемый результат |
| --- | --- |
| Контракты | `PROBE_ROUTE_CONTRACTS=PASS`. Смена порта меняет отпечаток своего выхода. Позднее общее правило и чужой вход сохраняют ключ. Правило, ведущее к другому выходу, и более раннее общее правило скрывают неподтверждённый контекст. |
| Начальный маршрут | `R39_PROBE_BOUND=PASS`. Скорость и проба YouTube проходят через отдельный Xray на первый локальный источник. У второго источника ноль запросов. |
| Смена маршрута в полёте | `R39_PROBE_ROUTE_CHANGED_DURING_SAMPLE=PASS`. Во время запроса закрытый стенд применяет через API другое правило. Полученные байты учитываются, запись SQLite остаётся прежней, скорость и YouTube исчезают из текущей сводки. |
| Запрос через чужой выход | `R39_PROBE_WRONG_OUTBOUND_SKIPPED=PASS`. Контрольный запрос через тот же вход действительно доходит до второго источника и получает 503. Планировщик пропускает этот вход для замера YouTube, запись и закрепление сохраняются. |
| Штатные ключи и регрессии | Записать `EXECSTART_CONTRACTS`, `BRIDGE_SLOT_CONTRACTS`, `R39_CONTEXT`, `R16_CONTRACTS`, `SUBSCRIPTION_YOUTUBE`, `WATCHDOG_CONTRACTS`. Указать итоги временной службы, четырёх проверок образов, трёх сценариев YouTube, моста, трёх прогонов R16, `rotation`, `certificate`, `api-switch`, ключей штатных Xray и активного sing-box, `R39_HOST_FIELDS_MATCH` и `M3_PREFLIGHT`. |

При сбое выполнить остальные доступные проверки и указать причину.
Публичное видео, смена рабочего WAN и поколений, штатное дренирование
и сутки M3 отметить `NOT_RUN`. Хронология рабочей службы остаётся
в журнале машины.

## 3. Публикация

Flash при любом результате автоматически публикует один обезличенный отчёт
`docs/reports/<UTC>_freepool-r39-probe-route.md` в ветке
`docs/flash-proton-ui-manifest` обычным push. Указать SHA кандидата и
задания, версии Ubuntu, systemd, Python, pytest и ядер, итог каждой
проверки и причины пропусков. Абсолютные пути хоста, аргументы процессов,
PID, хеши, базы, конфиги и полные логи оставить локально. При продвижении
ветки переносить только отчёт.
