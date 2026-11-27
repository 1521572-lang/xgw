# ThinkCentre · причина закрытия FreePool R16 и диагностика watchdog

Ubuntu 24.04 LTS, кандидат `f2cb19e05677b3a361dbbfbeb3d950bbcf8c33d8`.
Один проход проверяет причину закрытия в CLI и панели, регрессии маршрута
и различие между отдельным прогоном семи проверок перехвата и полной
матрицей watchdog. [Последний отчёт](https://github.com/1521572-lang/xgw/blob/010d8dc3403f75f7abbc7502e04f3b7f70571434/docs/reports/2026-11-27T070424Z_watchdog-rotation-commit.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r16-closure-status.bundle)

Flash самостоятельно запускает команды обычным пользователем. При
недоступном терминале запросить доступ. Временные процессы и записи
относятся к отдельному префиксу. Сетевые сценарии используют loopback.
Штатные службы и статус шлюза только считываются.

## 1. Запуск

Использовать полный клон с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
Для нестандартных путей к установленным Xray и Python с pytest задать
`XGW_TEST_XRAY` и `XGW_TEST_PYTHON` абсолютными путями.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=f2cb19e05677b3a361dbbfbeb3d950bbcf8c33d8
D=$(mktemp -d /tmp/xgw-r16-closure-status.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' \
    "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r16-closure-status.bundle >"$D/code.bundle"
printf '%s  %s\n' '9c226bf72bde6d721f969b7e7c876f3236cf361f7d214c0739bf15bb70d02b06' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml config.example.toml \
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
    src/xgw docs/helpers/freepool_lifecycle.py; then
  printf 'R16_STATUS_COMPILE=PASS\n'
else
  printf 'R16_STATUS_COMPILE=FAIL\n'
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
record_case R16_WATCHDOG tests/test_daemon.py \
    -k 'watchdog_schedule or test_watchdog_wakes or pool_region_reload'

record_case ROTATION_CONTRACTS tests/test_daemon.py \
    -k 'all_dead_refreshes or failing_the_first_check or failed_rotation or first_check_waits or background_build'
record_case APPLY_CONTRACTS tests/test_rotation.py tests/test_applier.py

record_case R16_CLOSURE_STATUS \
    tests/test_freepool_traffic.py::test_pool_region_deadline_bypasses_composition_cooldown \
    tests/test_freepool_traffic.py::test_pool_expiry_cause_requires_a_compatible_country_and_catalog \
    tests/test_panel.py::test_free_pool_region_expiry_is_visible_in_panel_state

if command -v node >/dev/null; then
  if timeout -k 2 10 node --check src/xgw/ui/app.js; then
    printf 'PANEL_JS=PASS\n'
  else
    printf 'PANEL_JS=FAIL\n'
    status=1
  fi
else
  printf 'PANEL_JS=NOT_RUN (node unavailable)\n'
fi

guard=(
    tests/test_daemon.py::test_daemon_reloads_missing_rules
    tests/test_daemon.py::test_daemon_names_the_tun_without_an_address
    tests/test_daemon.py::test_daemon_repairs_lan_path
    tests/test_daemon.py::test_rules_failure_is_reported_once
    tests/test_daemon.py::test_fail_closed_keeps_capture_while_xray_is_down
    tests/test_daemon.py::test_tailscale_goes_direct_while_xray_is_down
    tests/test_daemon.py::test_leak_reloads_rules_only_when_own_traffic_is_captured
)
record_case WATCHDOG_CAPTURE_ISOLATED "${guard[@]}"

matrix_rc=0
timeout -k 5 720 "$TEST_PY" -B -m pytest -o addopts= -q -rs -rfE \
    --tb=short --show-capture=no -p no:cacheprovider \
    tests/test_daemon.py tests/test_daemon_main.py >"$D/watchdog-matrix.log" 2>&1 || matrix_rc=$?
if [[ "$matrix_rc" == 0 ]]; then
  printf 'WATCHDOG_MATRIX=PASS\n'
else
  printf 'WATCHDOG_MATRIX=FAIL (exit %s)\n' "$matrix_rc"
  status=1
fi
printf '%s\n' "${guard[@]}" | sort -u >"$D/known-errors"
awk '/^(FAILED|ERROR) / {print $2}' "$D/watchdog-matrix.log" | sort -u >"$D/current-errors"
if [[ "$matrix_rc" != 0 && ! -s "$D/current-errors" ]]; then
  printf 'WATCHDOG_MATRIX_MISSING_SUMMARY\n'
else
  printf 'WATCHDOG_MATRIX_KNOWN_FAILURES\n'
  comm -12 "$D/current-errors" "$D/known-errors"
  printf 'WATCHDOG_MATRIX_NEW_FAILURES\n'
  comm -23 "$D/current-errors" "$D/known-errors"
  printf 'WATCHDOG_MATRIX_NOT_REPRODUCED\n'
  comm -13 "$D/current-errors" "$D/known-errors"
fi
tail -n 40 "$D/watchdog-matrix.log"

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
    printf 'R16_STATUS_HOST_FIELDS_MATCH\n'
  else
    printf 'R16_STATUS_HOST_FIELDS_DIFFER\n'
    status=1
  fi
else
  printf 'R16_STATUS_HOST_FIELDS_NOT_RUN\n'
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

## 2. Что зафиксировать

| Блок | Критерий |
| --- | --- |
| R16, причина закрытия | `R16_CLOSURE_STATUS=PASS`. При закрытом пути без подтверждённой альтернативы ожидаются `region_evidence_expired` в JSON панели и текст о сроке в CLI и журнале. При работающей альтернативе причина отсутствует. Свежая проверка убирает причину истечения. Страна вне разрешённого региона и просроченный каталог сами по себе этой причины не дают. |
| Контракты и панель | Записать количество результатов и пропуски `R16_CONTRACTS`, `R16_WATCHDOG`, `ROTATION_CONTRACTS`, `APPLY_CONTRACTS`. Для фронтенда дополнительно записать `PANEL_JS`, если установлен Node.js. |
| Семь тестов перехвата | Сопоставить `WATCHDOG_CAPTURE_ISOLATED` с `WATCHDOG_MATRIX`. Для каждого падения указать имя теста, строку и значения ожидалось/получено из короткого traceback. Совпадение симптомов и зависимость от порядка записать отдельно. По одному набору результатов не назначать причину. |
| Полная матрица | Записать количество прошедших, упавших, пропущенных, совпавших с прошлым отчётом и новых. При `WATCHDOG_MATRIX_MISSING_SUMMARY` указать фактический код выхода и причину, если её удалось прочитать. Отсутствие списка в этом случае означает незавершённое сравнение. |
| Изолированный Xray | Записать итоги `region-route`, `rotation`, `certificate`, `api-switch`, в том числе оба исхода удерживаемого соединения и версию ядра. |
| Штатный шлюз | `R16_STATUS_HOST_FIELDS_MATCH` и `M3_PREFLIGHT`. Штатный WAN, принудительное завершение рабочих соединений и сутки M3 указать как `NOT_RUN`. |

Выполнить доступные блоки даже при отдельном сбое. Полные логи и
временные конфиги сохранить в `PRIVATE_ARTIFACTS`.

## 3. Публикация

Flash автоматически публикует один обезличенный
`docs/reports/<UTC>_freepool-r16-closure-status.md` обычным push в ветку
`docs/flash-proton-ui-manifest` при любом исходе. Указать SHA кандидата и ТЗ,
версии Ubuntu, Python, pytest и Xray, результаты и причины пропусков.
При изменении ветки перенести свой отчёт на актуальную вершину. Системный
код дорабатывает разработчик.
