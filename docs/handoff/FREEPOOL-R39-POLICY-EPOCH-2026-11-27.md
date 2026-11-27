# ThinkCentre · поколение политики замеров FreePool R39

Ubuntu 24.04 LTS, кандидат `411586a432768f485e7078577abd493c6f1ed918`. Один проход проверяет переход
между политиками R39, учёт байтов при изменении условий во время замера,
хранение поколения в SQLite и регрессии обоих ядер.
[Отчёт об отпечатках ядер](https://github.com/1521572-lang/xgw/blob/5150842f41d80a30f3c3ad96c9ecc70304309760/docs/reports/2026-11-27T091459Z_freepool-r39-core-fingerprint.md) · [Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-policy-epoch.bundle)

Flash запускает команды самостоятельно обычным пользователем. При недоступном
терминале запросить доступ. Сценарии пишут только в отдельный префикс и ходят
по loopback. Штатные службы и файлы проверяются чтением.

## 1. Запуск

Полный клон с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
При нестандартных путях к установленным ядрам и Python c pytest задать
абсолютные `XGW_TEST_XRAY`, `XGW_TEST_SINGBOX` и `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=411586a432768f485e7078577abd493c6f1ed918
BRIDGE_FIXTURE=7ae63fabe8f21128a8bb5ae15c81d2c031362c69
D=$(mktemp -d /tmp/xgw-r39-policy-epoch.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' \
    "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-policy-epoch.bundle >"$D/code.bundle"
printf '%s  %s\n' 'ab7bb3fc127a7d01cd3cb75c63387ee50a07d2702e56fc522e3dd1d18d1f6edd' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests packaging pyproject.toml config.example.toml \
    docs/helpers/freepool_lifecycle.py | tar -x -C "$D/tree"
cd "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
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
record_case R39_CONTEXT \
    tests/test_runtime.py tests/test_freepool_traffic.py tests/test_singbox.py \
    tests/test_singbox_generations.py tests/test_freepool_wan_epoch.py tests/test_speed.py
record_case WATCHDOG_CONTRACTS tests/test_daemon.py tests/test_conncheck.py \
    -k 'conncheck or watchdog_schedule or test_watchdog_wakes or pool_region_reload'

if [[ "$core_ok" == 1 ]]; then
  if timeout -k 5 65 env PYTHONPATH="$D/tree/src:$D/tree/tests:$D/tree/docs/helpers" \
      "$TEST_PY" -B -P - "$XRAY" "$D/policy-sample" >"$D/policy-sample.log" 2>&1 <<'PYTHON'
import json
import socket
import sys
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from freepool_lifecycle import serving
from test_freepool_traffic import NOW, _daemon
from xgw.daemon import POOL_SPEED_META
from xgw.freepool import traffic, wan_epoch
from xgw.generator import builder
from xgw.paths import Paths, atomic_write_json
from xgw.store import Store
from xgw.xraycore.service import ProcessXrayService


class Origin(BaseHTTPRequestHandler):
    on_request = staticmethod(lambda: None)
    body = b"xgw-39" * 60000

    def do_GET(self):
        self.on_request()
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

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
cfg.speed.url_fallback = ""
cfg.speed.max_seconds = 3
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
    daemon._observe_pool_wan()
    daemon._observe_pool_policy()
    cfg.speed.url = f"http://127.0.0.1:{port}/speed"
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
        daemon._pool_paths = daemon._pool_outbound_keys(applied)
        daemon._observe_pool_xray()
        daemon._pool_step(applied, live)
        daemon._pool_speed_step(applied, live, clock[0])
        saved = store.get_meta(POOL_SPEED_META)
        first = json.loads(saved)[key]
        assert first["mbps"] and first["bytes"] == len(Origin.body), first.get("error")
        assert first["policy"] == daemon._pool_policy.current
        wan = daemon._pool_wan.current
        print("R39_POLICY_SAMPLE=PASS")

        clock[0] += cfg.speed.unlimited_hours * 3600 + 1
        Origin.on_request = staticmethod(lambda: setattr(cfg.free_pool, "region", "US"))
        daemon._pool_speed_step(applied, live, clock[0])
        second = daemon._pool_policy.current
        assert second and second != first["policy"] and daemon._pool_wan.current == wan
        assert daemon._pool_own == len(Origin.body)
        assert store.get_meta(POOL_SPEED_META) == saved
        daemon._pool_step(applied, live)
        assert daemon._pool_pinned == tag and daemon._pool_summary()["traffic"]["mbps"] is None
        print("R39_POLICY_CHANGE_DURING_SAMPLE=PASS")

        with closing(Store(paths.db_file)) as reopened:
            persisted = wan_epoch.Epoch(reopened, key=wan_epoch.POLICY_META_KEY)
            persisted.observe(traffic.policy_identity(cfg))
            assert persisted.current == second
            cfg.free_pool.region = "EU"
            persisted.observe(traffic.policy_identity(cfg))
            assert persisted.current not in (None, first["policy"], second)
        print("R39_POLICY_PERSISTED_RETURN=PASS")
    finally:
        daemon.service.stop()
PYTHON
  then
    grep '^R39_POLICY_' "$D/policy-sample.log"
  else
    printf 'R39_POLICY_LOOPBACK=FAIL\n'
    status=1
  fi
else
  printf 'R39_POLICY_LOOPBACK=NOT_RUN (Xray unavailable)\n'
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
from pathlib import Path

from xgw.apply.singbox import SystemdSingboxService
from xgw.paths import Paths
from xgw.xraycore.service import SystemdXrayService, measurement_generation

paths = Paths(root=Path("/"))
failed = False
for label, service, path in (
    ("XRAY", SystemdXrayService(), paths.xray_bin),
    ("SINGBOX", SystemdSingboxService(), paths.singbox_bin),
):
    if service.runtime_generation() is None:
        print(f"R39_HOST_{label}=NOT_RUN (service generation unavailable)")
        continue
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

for scenario in region-route rotation certificate api-switch; do
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

| Блок | Что проверить |
| --- | --- |
| Контракты | `R39_CONTEXT=PASS`, `WATCHDOG_CONTRACTS=PASS`, `R16_CONTRACTS=PASS`. Указать количество и пропуски. Старый замер без поля политики не влияет на выбор. Бюджет и добавление устройства при прежнем охвате сохраняют поколение. Регион, порядок разрешённых fallback в preferred, TTL и смена охвата меняют ключ. |
| Реальная загрузка | `R39_POLICY_SAMPLE=PASS`. Тест загружает тело через установленный Xray, сохраняет скорость и поколение в приватной SQLite. |
| Смена условий во время загрузки | `R39_POLICY_CHANGE_DURING_SAMPLE=PASS`. Политика меняется после начала HTTP-запроса. Байты учтены, запись скорости не перезаписана, старое число исчезло из сводки. Поколение WAN прежнее. Само изменение кеша не снимает живое закрепление в фикстуре. |
| Повторное открытие и возврат | `R39_POLICY_PERSISTED_RETURN=PASS`. Переоткрытие SQLite с той же политикой сохраняет поколение. Возврат в первый регион выдаёт новое. |
| Регрессии ядер | Записать версии, `R39_BRIDGE_LOOPBACK` с 32-символьным ID, исходы `region-route`, `rotation`, `certificate`, `api-switch` и оба исхода удерживаемого соединения. |
| Штатный шлюз | Записать стабильность ключа `R39_HOST_XRAY`, `R39_HOST_SINGBOX`, совпадение полей служб и `M3_PREFLIGHT`. Неактивная служба даёт `NOT_RUN`. |

Выполнить остальные доступные блоки при отдельном сбое. Записать `NOT_RUN`
для смены рабочего WAN, переключения рабочих поколений, принудительного
завершения потоков и суточного M3. Полные логи, метаданные SQLite и
конфиги оставить в приватном каталоге.

## 3. Публикация

Flash автоматически публикует один обезличенный отчёт
`docs/reports/<UTC>_freepool-r39-policy-epoch.md` в
`docs/flash-proton-ui-manifest` обычным push при любом исходе. Указать SHA
кандидата и задания, версии Ubuntu, Python, pytest и ядер, таблицу исходов
и причины пропусков. При обновлении ветки перенести только отчёт.
Системный код редактирует разработчик.
