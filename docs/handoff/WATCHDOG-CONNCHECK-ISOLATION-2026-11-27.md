# ThinkCentre · изоляция проверок watchdog от NetworkManager

Ubuntu 24.04 LTS, кандидат `3915490126cf88602d1f0031fb80855c454093b9`.
Один проход воспроизводит семь прежних ошибок на контрольном коде и проверяет
тот же набор с изолированным NetworkManager. Сценарии FreePool на установленном
Xray идут в том же проходе. [Отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/7d8378e32b262c36e5969b4fcbc158d4ed22e697/docs/reports/2026-11-27T082829Z_freepool-r16-closure-status.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-watchdog-conncheck-isolation.bundle)

Flash выполняет команды самостоятельно обычным пользователем. При недоступном
терминале запросить доступ. Тесты пишут только в свои временные каталоги, сетевые
сценарии работают на loopback. Свойства штатных служб, статус XGW и наличие
проверки связности NetworkManager только считываются.

## 1. Запуск

Нужен полный клон с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
При нестандартном размещении указать абсолютные `XGW_TEST_PYTHON` и
`XGW_TEST_XRAY`. Использовать установленный Xray.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=3915490126cf88602d1f0031fb80855c454093b9
CONTROL=f2cb19e05677b3a361dbbfbeb3d950bbcf8c33d8
D=$(mktemp -d /tmp/xgw-watchdog-conncheck.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' \
    "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-watchdog-conncheck-isolation.bundle >"$D/code.bundle"
printf '%s  %s\n' '6ead77ccf307413689c08627773f335f547f31b4fee379c54f1d796eae5ef5fe' "$D/code.bundle" | sha256sum --check -
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
    src/xgw docs/helpers/freepool_lifecycle.py tests/conftest.py tests/test_daemon.py; then
  printf 'CONNCHECK_COMPILE=PASS\n'
else
  printf 'CONNCHECK_COMPILE=FAIL\n'
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
record_case CONNCHECK_CONTRACTS tests/test_conncheck.py \
    tests/test_daemon.py::test_guard_reloads_rules_after_a_conncheck_update

# Прочитать только наличие настроенной проверки. Домен и адреса не выводятся.
if timeout -k 2 25 /usr/bin/python3 -B -P - <<'PYTHON'
from xgw.net import conncheck

print("HOST_NM_TARGET_PRESENT=" + str(conncheck.nm_target() is not None).lower())
PYTHON
then
  :
else
  printf 'HOST_NM_TARGET_PRESENT=UNKNOWN\n'
fi

mkdir "$D/control" "$D/repro"
cat >"$D/repro/xgw_conncheck_repro.py" <<'PYTHON'
import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    target = fixturedef.argname == "guarded"
    if target:
        from xgw.net import conncheck
        request.getfixturevalue("monkeypatch").setattr(conncheck, "lookup", lambda _resolve: False)
    result = yield
    if target:
        daemon, _capture = result.get_result()
        with daemon._conncheck_lock:
            daemon._conncheck_found = ({"host": "check.example.org", "port": 80,
                                       "ips": ["1.1.1.1"]},)
PYTHON

printf '%s\n' "${guard[@]}" | sort -u >"$D/known-errors"
if git -C "$REPO" archive "$CONTROL" src tests pyproject.toml config.example.toml \
    | tar -x -C "$D/control"; then
  control_rc=0
  (cd "$D/control" &&
     PYTHONPATH="$D/repro:$D/control/src" XGW_ROOT="$D/control-fixture" \
     pytest_case -p xgw_conncheck_repro "${guard[@]}") >"$D/watchdog-control.log" 2>&1 || control_rc=$?
  awk '/^(FAILED|ERROR) / {print $2}' "$D/watchdog-control.log" | sort -u >"$D/control-errors"
  if [[ "$control_rc" == 1 ]] && cmp -s "$D/known-errors" "$D/control-errors"; then
    printf 'CONNCHECK_CONTROL_REPRODUCED_SEVEN\n'
  else
    printf 'CONNCHECK_CONTROL_UNEXPECTED (exit %s)\n' "$control_rc"
    status=1
  fi
  tail -n 36 "$D/watchdog-control.log"
else
  printf 'CONNCHECK_CONTROL_NOT_RUN (archive unavailable)\n'
  status=1
fi

matrix_rc=0
timeout -k 5 720 "$TEST_PY" -B -m pytest -o addopts= -q -rs -rfE \
    --tb=short --show-capture=no -p no:cacheprovider \
    tests/test_daemon.py tests/test_daemon_main.py >"$D/watchdog-matrix.log" 2>&1 || matrix_rc=$?
awk '/^(FAILED|ERROR) / {print $2}' "$D/watchdog-matrix.log" | sort -u >"$D/current-errors"
if [[ "$matrix_rc" == 0 ]]; then
  printf 'WATCHDOG_MATRIX=PASS\n'
else
  printf 'WATCHDOG_MATRIX=FAIL (exit %s)\n' "$matrix_rc"
  status=1
  if [[ -s "$D/current-errors" ]]; then
    printf 'WATCHDOG_MATRIX_EXISTING_FAILURES\n'
    comm -12 "$D/current-errors" "$D/known-errors"
    printf 'WATCHDOG_MATRIX_NEW_FAILURES\n'
    comm -23 "$D/current-errors" "$D/known-errors"
  else
    printf 'WATCHDOG_MATRIX_MISSING_SUMMARY\n'
  fi
fi
tail -n 32 "$D/watchdog-matrix.log"

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
    printf 'CONNCHECK_HOST_FIELDS_MATCH\n'
  else
    printf 'CONNCHECK_HOST_FIELDS_DIFFER\n'
    status=1
  fi
else
  printf 'CONNCHECK_HOST_FIELDS_NOT_RUN\n'
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

## 2. Критерии и отчёт

| Блок | Что проверить |
| --- | --- |
| Контроль причин | `CONNCHECK_CONTROL_REPRODUCED_SEVEN`. Синтетический результат проверки связности подан сразу после первого шага на `f2cb19e`. Сверить семь имён и семь симптомов из последнего отчёта, включая три пустых списка событий и четыре лишних вызова `up`. |
| Перехват на кандидате | `WATCHDOG_CAPTURE_ISOLATED=PASS`. Все семь проверок проходят с исходными ожиданиями. |
| Явное обновление conncheck | `CONNCHECK_CONTRACTS=PASS`. Один reload после готового синтетического результата, корректная запись адресов и `loaded=true`. Следующая самостоятельная потеря правил восстанавливается watchdog и оставляет событие. Контракты парсинга, записи и фонового поиска проходят. |
| Полная матрица | Записать итог `WATCHDOG_MATRIX`, числа прошедших, упавших и пропущенных. При FAIL сохранить имена, строку и значения ожидалось/получено. Указать, какие из семи исчезли. Для `MISSING_SUMMARY` записать код выхода и причину неполного прогона. |
| Контракты FreePool | Отдельно записать R16, статус закрытия, ротацию, применение и `PANEL_JS`. Указать число тестов и причины пропусков. |
| Xray на loopback | Записать исходы `region-route`, `rotation`, `certificate` и `api-switch`, два исхода удерживаемых соединений и версию ядра. |
| Штатный шлюз | Записать `HOST_NM_TARGET_PRESENT`, совпадение состояний служб и `M3_PREFLIGHT`. Адрес NetworkManager не записывать в отчёт. Рабочий WAN, принудительное завершение рабочих соединений и сутки M3 указать как `NOT_RUN`. |

Выполнять доступные блоки при отдельных сбоях. Полные логи оставить в
`PRIVATE_ARTIFACTS`. Тесты штатных правил на реальном WAN проходят в отдельно
согласованном окне.

## 3. Публикация

Flash автоматически публикует один обезличенный отчёт
`docs/reports/<UTC>_watchdog-conncheck-isolation.md` обычным push в
`docs/flash-proton-ui-manifest` при любом исходе. Указать SHA кандидата, ТЗ
и контроля, версии Ubuntu, Python, pytest и Xray, результаты и причины
пропусков. Если ветка обновилась, перенести свой отчёт на её вершину.
Системный код и тесты редактирует разработчик.
