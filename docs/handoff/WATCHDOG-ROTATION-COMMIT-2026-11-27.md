# ThinkCentre · подтверждение ротации watchdog после применения конфига

Ubuntu 24.04 LTS, кандидат `0bb6134ec3dd0e91f649ce898cfc4c6baba694f6`. Проверить ротацию
после отказа участников и регрессии FreePool R16 на установленном Xray.
[Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/d6190f5d795574720fae563301d018e41cc8ec6e/docs/reports/2026-11-27T061554Z_freepool-r16-route-deadline.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-watchdog-rotation-commit.bundle)

Flash самостоятельно выполняет проверку обычным пользователем. Если нет
терминала, запросить доступ. Все записи и процессы тестов принадлежат
изолированному префиксу. Сетевые сценарии используют loopback. Штатные
службы и статус шлюза только считываются.

## 1. Запуск

Использовать полный клон с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
При нестандартной установке указать абсолютный `XGW_TEST_XRAY` или
`XGW_TEST_PYTHON`. Записать версии из вывода и сохранить локальный каталог
`PRIVATE_ARTIFACTS`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=0bb6134ec3dd0e91f649ce898cfc4c6baba694f6
CONTROL=ea3b1b915af6cac9776aba80b2ad207b7e205291
D=$(mktemp -d /tmp/xgw-rotation-commit.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\nCONTROL %s\n' \
    "$D" "$PRETTY_NAME" "$CODE" "$CONTROL"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-watchdog-rotation-commit.bundle >"$D/code.bundle"
printf '%s  %s\n' 'dfae270f67c4df8bcda7f3363f2da0aeb9be52ceaeebb698305185730fe52fa1' "$D/code.bundle" | sha256sum --check -
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
  printf 'ROTATION_COMPILE=PASS\n'
else
  printf 'ROTATION_COMPILE=FAIL\n'
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

record_case ROTATION_CONTRACTS tests/test_daemon.py \
    -k 'all_dead_refreshes or failing_the_first_check or failed_rotation or first_check_waits or background_build'
record_case APPLY_CONTRACTS tests/test_rotation.py tests/test_applier.py

watchdog_matrix() {
  timeout -k 5 720 "$TEST_PY" -B -m pytest -o addopts= -q -rs --tb=no -p no:cacheprovider \
      tests/test_daemon.py tests/test_daemon_main.py
}

if watchdog_matrix >"$D/watchdog-matrix.log" 2>&1; then
  printf 'WATCHDOG_MATRIX=PASS\n'
else
  printf 'WATCHDOG_MATRIX=FAIL (compare control below)\n'
  status=1
  mkdir "$D/control"
  if git -C "$REPO" archive "$CONTROL" src tests pyproject.toml config.example.toml \
      | tar -x -C "$D/control"; then
    if (cd "$D/control" &&
        PYTHONPATH="$D/control/src" XGW_ROOT="$D/control-fixture" watchdog_matrix) \
        >"$D/watchdog-control.log" 2>&1; then
      printf 'WATCHDOG_MATRIX_CONTROL=PASS\n'
    else
      printf 'WATCHDOG_MATRIX_CONTROL=FAIL\n'
    fi
    awk '/^(FAILED|ERROR) / {print $2}' "$D/watchdog-matrix.log" | sort -u >"$D/matrix.errors"
    awk '/^(FAILED|ERROR) / {print $2}' "$D/watchdog-control.log" | sort -u >"$D/control.errors"
    printf 'WATCHDOG_MATRIX_NEW_FAILURES\n'
    comm -23 "$D/matrix.errors" "$D/control.errors"
    printf 'WATCHDOG_MATRIX_RESOLVED_FAILURES\n'
    comm -13 "$D/matrix.errors" "$D/control.errors"
    tail -n 24 "$D/watchdog-control.log"
  else
    printf 'WATCHDOG_MATRIX_CONTROL=NOT_RUN\n'
  fi
fi
tail -n 24 "$D/watchdog-matrix.log"

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
    printf 'ROTATION_HOST_FIELDS_MATCH\n'
  else
    printf 'ROTATION_HOST_FIELDS_DIFFER\n'
    status=1
  fi
else
  printf 'ROTATION_HOST_FIELDS_NOT_RUN\n'
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

## 2. Критерии и содержание отчёта

| Блок | Достаточный результат |
| --- | --- |
| Пять сценариев предыдущего отчёта | `ROTATION_CONTRACTS=PASS`. Все предыдущие FAIL проходят. При `ALL_DEAD` прямое обновление, проверка запасных и запрос срочной замены происходят в одном шаге. При первой неудаче FROZEN или CONNECT_FAIL запрос замены попадает в очередь на первом шаге для обоих типов подписок. Следующий готовый результат применяется и заменяет участника. |
| Отказ или откат сборки | Два варианта `test_failed_rotation_keeps_first_failure_until_apply_succeeds` проходят. Старый участник и диагноз сохраняются, успешной записи о замене ещё нет. После применения нужного состава новый участник в работе, прежний диагноз убран, событие о ротации одно. |
| Регрессии применения и FreePool | `APPLY_CONTRACTS=PASS`, `R16_CONTRACTS=PASS`, `R16_WATCHDOG=PASS`. Указать число тестов и пропусков для каждой группы. |
| Вся матрица watchdog | Два полных файла. При FAIL сверить названия и фактические ошибки с контрольным прогоном. Раздельно перечислить совпавшие, новые и исчезнувшие сбои. Истечение тайм-аута, ошибку сбора или отсутствие результата записать отдельно. |
| Изолированный Xray | Четыре сценария `region-route`, `rotation`, `certificate`, `api-switch`. Указать метки перехода, закрытия и восстановления R16, регрессии ключа и TLS, оба наблюдения удерживаемого соединения и версию Xray. |
| Штатный шлюз | `ROTATION_HOST_FIELDS_MATCH` и снимок `M3_PREFLIGHT`. Рабочий WAN, принудительное завершение пользовательских соединений и сутки M3 указать как `NOT_RUN`. |

При сбое блока завершить остальные доступные проверки. Любую ошибку или
пропуск отразить в отчёте. Полные логи, конфиги и данные узлов оставить
в приватном каталоге.

## 3. Публикация

Flash автоматически публикует один обезличенный
`docs/reports/<UTC>_watchdog-rotation-commit.md` обычным push в ветку
`docs/flash-proton-ui-manifest` при любом исходе. Записать SHA кандидата,
ТЗ, а при сравнении и контроля, версии ОС/Python/Xray и таблицу итогов.
При изменении ветки перенести свой отчёт на актуальную вершину. Системные
правки остаются задачей разработчика.
