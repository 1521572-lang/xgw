# ThinkCentre · повтор моста R39 и закрытия маршрута R16

Ubuntu 24.04 LTS, кандидат `b198caf11bb59d765616ce555fab7f276371885f`. Один проход
перепроверяет два упавших контракта моста при действующем поколении
sing-box, чтение контекста активного слота и три независимых сценария
закрытия маршрута. Повторяется приёмка загруженных образов обоих ядер.
[Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/d1534d8977181aa2b2f1f8a7f19a06a7b9db9e5c/docs/reports/2026-11-27T102202Z_freepool-r39-loaded-image.md) · [Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-bridge-recheck.bundle)

Flash запускает команды сама обычным пользователем. При недоступности
терминала запросить доступ и продолжить после получения. Команды
запускают отдельные копии ядер, пишут во временный каталог и выполняют
запросы по loopback. Со штатной установки читаются только статус,
свойства служб и доступные файлы ядер.

## 1. Запуск

Полный клон с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. Для
нестандартных путей к установленным ядрам и Python с pytest задать
`XGW_TEST_XRAY`, `XGW_TEST_SINGBOX` и `XGW_TEST_PYTHON` абсолютными
путями. Если `/tmp` смонтирован с `noexec`, задать абсолютный `TMPDIR`
с правом запуска из пользовательского каталога.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=b198caf11bb59d765616ce555fab7f276371885f
BRIDGE_FIXTURE=7ae63fabe8f21128a8bb5ae15c81d2c031362c69
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-r39-bridge-recheck.XXXXXXXX")
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' \
    "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-bridge-recheck.bundle >"$D/code.bundle"
printf '%s  %s\n' '5d97e62507de588ed602bafc5f4e453b72e4a5ecda27b57fcb9dbe2a6ac7e691' "$D/code.bundle" | sha256sum --check -
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
record_case BRIDGE_SLOT_CONTRACTS tests/test_singbox.py -k bridge_measurement_context
record_case R39_CONTEXT \
    tests/test_runtime.py tests/test_freepool_traffic.py tests/test_singbox.py \
    tests/test_singbox_generations.py tests/test_freepool_wan_epoch.py tests/test_speed.py \
    tests/test_youtube.py
record_case SUBSCRIPTION_YOUTUBE tests/test_daemon.py tests/test_daemon_main.py -k 'youtube or media'
record_case WATCHDOG_CONTRACTS tests/test_daemon.py tests/test_conncheck.py \
    -k 'conncheck or watchdog_schedule or test_watchdog_wakes or pool_region_reload'

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
    stable = bool(key) and key == measurement_generation(service, path)
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
| Изоляция контракта | `BRIDGE_SLOT_CONTRACTS=PASS`, оба параметра `subscription` и `freepool`. Фикстура сама задаёт `ActiveState`, PID, идентификатор запуска и образ. После `inactive` контекст пуст при любом состоянии служб хоста. |
| Штатный sing-box | Из свежего статуса прочитать `R39_HOST_SINGBOX_SLOT` (`legacy`, `blue` или `green`) и сверить ключ именно этого юнита, если он активен. При `INSTALLED_ONLY` подтвердить стабильность по файлу и поколению. При неактивном юните или недоступном статусе указать `NOT_RUN` с причиной. Состояния и PID всех трёх юнитов, Xray и XGW сверить до и после. |
| Повтор закрытия | `R16_REGION_ROUTE_1`, `_2`, `_3`. Для каждого прогона записать переход на второй выход, исход удерживаемого соединения, закрытие и восстановление. После исключения тега рабочего выхода и успешного HTTP CONNECT допустимы EOF, TCP reset или обрыв записи без ответа. Отказ самого CONNECT, таймаут и данные от выхода считаются FAIL. Отдельно указать `R16_ROUTE_CLOSE_TRANSPORT`. |
| Контракты и образы | Указать число тестов и пропусков по `R39_CONTEXT`, `R16_CONTRACTS`, `SUBSCRIPTION_YOUTUBE` и `WATCHDOG_CONTRACTS`. Обе отдельные копии проходят идентичную замену, замену с различием файлов и перезапуск. |
| Регрессии | Три `R39_YOUTUBE_*`, `R39_BRIDGE_LOOPBACK`, `rotation`, `certificate`, `api-switch`, штатный ключ Xray и готовность M3. |

При сбое отдельного блока выполнить остальные. Записать каждый из трёх
результатов R16, сохранив любой FAIL в итогах. Если был только EOF,
указать, что TCP reset в этом прогоне не наблюдался. Отдельно отметить
`NOT_RUN` для публичного видео, смены рабочего WAN и поколений,
принудительного закрытия рабочих потоков и суточного M3.

## 3. Публикация

Flash публикует при любом исходе один обезличенный отчёт
`docs/reports/<UTC>_freepool-r39-bridge-recheck.md` в ветке
`docs/flash-proton-ui-manifest` обычным push. Указать SHA кандидата и
задания, версии Ubuntu, Python, pytest и обоих ядер, статусы и причины
пропусков. PID, хеши, базы, конфиги и сырые логи остаются локально.
При продвижении ветки переносить только отчёт.
