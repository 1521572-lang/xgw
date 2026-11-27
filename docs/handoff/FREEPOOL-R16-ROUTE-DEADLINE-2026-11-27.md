# ThinkCentre · пересборка маршрута на границе R16

Ubuntu 24.04 LTS, кандидат `be91e2b965fdc2fa5571fbf27b07a6342617c403`. Задание проверяет
планирование срочной пересборки, переключение новых соединений и поведение
при отсутствии другого подтверждённого выхода.
[Принятый отчёт R16](https://github.com/1521572-lang/xgw/blob/3b4484e960f126ca331480dc2c855356070e6630/docs/reports/2026-11-27T055856Z_freepool-r16-region-evidence.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r16-route-deadline.bundle)

Flash запускает команды самостоятельно обычным пользователем. При отсутствии
терминала запросить доступ. Сетевые сценарии работают на loopback. Штатные
службы и состояние шлюза считываются до и после проверки.

## 1. Запуск

Из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
Использовать установленный Xray. Если он или pytest размещены нестандартно,
задать абсолютные пути `XGW_TEST_XRAY` и `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=be91e2b965fdc2fa5571fbf27b07a6342617c403
CONTROL=2cda05a4c5b0233925c0cc9f136357aec5aede3c
D=$(mktemp -d /tmp/xgw-freepool-r16-route.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\nCONTROL %s\n' \
    "$D" "$PRETTY_NAME" "$CODE" "$CONTROL"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r16-route-deadline.bundle >"$D/code.bundle"
printf '%s  %s\n' '480f99dba78264e8852f93a91e776b546fa7f512cb927ef26cacb55e1a0d502f' "$D/code.bundle" | sha256sum --check -
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
  printf 'R16_COMPILE=PASS\n'
else
  printf 'R16_COMPILE=FAIL\n'
  status=1
fi

pytest_case() {
  timeout -k 5 300 "$TEST_PY" -B -m pytest -o addopts= -q -rs --tb=no -p no:cacheprovider "$@"
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

timing=(tests/test_daemon.py::test_all_dead_refreshes_directly_and_rotates_at_once
        tests/test_daemon.py::test_member_failing_the_first_check_is_replaced_at_once
        -k 'all_dead or FROZEN or CONNECT_FAIL')
if pytest_case "${timing[@]}" >"$D/timing.log" 2>&1; then
  printf 'WATCHDOG_TIMING=PASS\n'
else
  printf 'WATCHDOG_TIMING=FAIL (compare control below)\n'
  status=1
  mkdir "$D/control"
  if git -C "$REPO" archive "$CONTROL" src tests pyproject.toml config.example.toml \
      | tar -x -C "$D/control"; then
    if (cd "$D/control" &&
        PYTHONPATH="$D/control/src" XGW_ROOT="$D/control-fixture" pytest_case "${timing[@]}") \
        >"$D/timing-control.log" 2>&1; then
      printf 'WATCHDOG_TIMING_CONTROL=PASS\n'
    else
      printf 'WATCHDOG_TIMING_CONTROL=FAIL\n'
    fi
    tail -n 18 "$D/timing-control.log"
  else
    printf 'WATCHDOG_TIMING_CONTROL=NOT_RUN\n'
  fi
fi
tail -n 18 "$D/timing.log"

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
    printf 'R16_HOST_FIELDS_MATCH\n'
  else
    printf 'R16_HOST_FIELDS_DIFFER\n'
    status=1
  fi
else
  printf 'R16_HOST_FIELDS_NOT_RUN\n'
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

| Блок | Достаточный результат |
| --- | --- |
| Контракты и такт watchdog | `R16_CONTRACTS=PASS`, `R16_WATCHDOG=PASS`. Зафиксировать количество тестов и причины пропусков. Срок прерывает обычную паузу watchdog и запускает пересборку даже в пределах 10-минутного интервала. За секунду до истечения срочной пересборки ещё нет. Конфликт страны принятого выхода запускает её на ближайшей сверке. |
| Контроль таймингов | На WSL на обеих ревизиях падали проверки немедленной ротации при отказе всех участников и при первом FROZEN/CONNECT_FAIL. Указать исход пяти тестов на Ubuntu 24.04. При FAIL сравнить точные имена упавших тестов с контрольным прогоном и записать совпадающие и новые ошибки. |
| Переход, блокировка, восстановление | У отдельного Xray активный выход A закреплён через API. После границы новые соединения приходят к B, старый тег A удалён. После истечения подтверждения у B новые соединения остаются без полезных данных и не возвращаются на A или B. Свежая проверка B восстанавливает обмен. Нужны `R16_ROUTE_ALTERNATIVE`, `R16_ROUTE_CLOSED`, `R16_ROUTE_RECOVERY` с `PASS`. |
| Удерживаемое соединение | Записать `R16_ROUTE_HELD_STREAM`. Это наблюдение одного обмена после смены, оно не закрывает требование принудительно завершать действующие соединения у утратившего подтверждение выхода. |
| Регрессии | `rotation`, `certificate`, `api-switch`. Для каждого указать исход и версию Xray. |
| Штатный шлюз | Записать совпадение полей служб и значения `M3_PREFLIGHT`. Для рабочего WAN, пользовательских соединений, принудительного завершения и суточного M3 указать `NOT_RUN`. |

При сбое отдельного блока выполнить остальные доступные. Указать наблюдаемый
исход каждого блока. Полные логи и временные конфиги остаются в каталоге
`PRIVATE_ARTIFACTS`.

## 3. Публикация

Flash автоматически публикует один обезличенный отчёт
`docs/reports/<UTC>_freepool-r16-route-deadline.md` обычным push в ветку
`docs/flash-proton-ui-manifest` при любом исходе. Указать SHA кандидата и ТЗ,
версии ОС, Python и Xray, результаты и причины пропусков. При обновлении
ветки перенести свой отчёт на актуальную вершину. Системный код дорабатывает
разработчик.
