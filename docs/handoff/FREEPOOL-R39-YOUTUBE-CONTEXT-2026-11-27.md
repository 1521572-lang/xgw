# ThinkCentre · проверки YouTube в контексте FreePool R39

Ubuntu 24.04 LTS, кандидат `ee6f67978e4b658bcab9ca659fb383bcf77d192b`. Один проход проверяет
применимость результатов YouTube в списке и логике выбора FreePool, повтор
после смены WAN, смену политики во время HTTP-запроса и регрессии обоих ядер.
[Отчёт о поколении политики](https://github.com/1521572-lang/xgw/blob/854e4661d3f8f81cfc647caba76c5efaa82fa190/docs/reports/2026-11-27T093151Z_freepool-r39-policy-epoch.md) · [Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-youtube-context.bundle)

Flash самостоятельно запускает команды обычным пользователем. При недоступном
терминале запросить доступ и после получения продолжить. Проверки выполняются
в отдельном каталоге и по loopback. Состояние штатных служб читается до и
после прогона. Отдельный HTTP-источник возвращает заданные коды 503 и 204.
Публичное воспроизведение YouTube в этот прогон не входит.

## 1. Запуск

Полный клон с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
При нестандартных путях к установленным ядрам и Python с pytest задать
абсолютные `XGW_TEST_XRAY`, `XGW_TEST_SINGBOX` и `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=ee6f67978e4b658bcab9ca659fb383bcf77d192b
BRIDGE_FIXTURE=7ae63fabe8f21128a8bb5ae15c81d2c031362c69
D=$(mktemp -d /tmp/xgw-r39-youtube-context.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' \
    "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-youtube-context.bundle >"$D/code.bundle"
printf '%s  %s\n' 'af48b887fea989ba6e803329e2acc77aa83cdd574aa1504020b79c67a29decd7' "$D/code.bundle" | sha256sum --check -
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
    tests/test_singbox_generations.py tests/test_freepool_wan_epoch.py tests/test_speed.py \
    tests/test_youtube.py
record_case SUBSCRIPTION_YOUTUBE tests/test_daemon.py tests/test_daemon_main.py -k 'youtube or media'
record_case WATCHDOG_CONTRACTS tests/test_daemon.py tests/test_conncheck.py \
    -k 'conncheck or watchdog_schedule or test_watchdog_wakes or pool_region_reload'

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
| Контракты | `R39_CONTEXT`, `R16_CONTRACTS`, `WATCHDOG_CONTRACTS`, `SUBSCRIPTION_YOUTUBE`. Записать количество прошедших тестов, сбои и пропуски. Контракт проверяет исключение старой записи без контекста, учёт 1024 байт при смене политики и независимость от лимита обычного замера. Изменение порога YouTube скрывает старый результат. |
| Один контекст | `R39_YOUTUBE_SAME_CONTEXT=PASS`. Два HTTP 503 через установленный Xray подряд сохраняют два отказа в SQLite и дают основание считать выход неподходящим для YouTube. |
| Новое поколение WAN | `R39_YOUTUBE_NEW_WAN=PASS`. В стенде меняется метка WAN. Сводка сразу скрывает старый результат, следующий HTTP 503 начинает счёт с единицы, закрепление сохраняется. |
| Смена политики во время запроса | `R39_YOUTUBE_POLICY_RACE=PASS`. Источник меняет регион после начала HTTP. Запись SQLite остаётся прежней, в сводке результата уже нет. Следующий запрос в новом контексте сохраняет успешный результат и обнуляет счётчик. |
| Регрессии ядер | Записать версии Xray и sing-box, `R39_BRIDGE_LOOPBACK` с 32-символьным ID, исходы `region-route`, `rotation`, `certificate`, `api-switch` и оба исхода удерживаемого соединения. |
| Штатный шлюз | Записать `R39_HOST_XRAY`, `R39_HOST_SINGBOX`, совпадение полей служб и `M3_PREFLIGHT`. Неактивная служба даёт `NOT_RUN`. |

При сбое отдельного блока выполнить остальные доступные проверки. В отчёте
отдельно поставить `NOT_RUN` для публичного YouTube, смены рабочего WAN,
переключения рабочих поколений, принудительного закрытия потоков и суточного
M3. Файлы SQLite, конфиги и полные логи остаются в приватном каталоге.

## 3. Публикация

Flash при любом исходе сама публикует один обезличенный отчёт
`docs/reports/<UTC>_freepool-r39-youtube-context.md` в ветке
`docs/flash-proton-ui-manifest` обычным push. Указать SHA кандидата и задания,
версии Ubuntu, Python, pytest и ядер, результаты и причины пропусков.
При раннем завершении записать шаг и причину, остальные статусы отметить
`NOT_RUN`. При обновлении ветки переносить только отчёт.
