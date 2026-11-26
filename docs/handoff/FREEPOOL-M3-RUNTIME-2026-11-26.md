# ThinkCentre · FreePool F13/M3 · один проход по рабочим сценариям

Ubuntu 24.04 LTS, кандидат `b7765feb5dde58c96be1dae93b37ad8176b654f6`.
Один отчёт охватывает регрессию R13/R50, ротацию VLESS, отказ и восстановление
TLS, переключение и обратное переключение маршрута через Xray API, а также
готовность рабочего FreePool к дневнику M3.
[Принятый отчёт по объявленному сроку](https://github.com/1521572-lang/xgw/blob/8cc8d467fa37c7a2f4b607ee85f9eb0f0f88d07f/docs/reports/2026-11-26T191848Z_freepool-f13-credential-expiry.md)
· [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-m3-runtime.bundle)

Flash выполняет команды самостоятельно. При недоступном терминале запросить доступ.
Запуск обычным пользователем. Использовать установленный Xray и зафиксировать его
версию. Модели поручена техническая проверка готового кода.

Опрос изолированных сценариев идёт только на loopback. Временные процессы
привязаны к случайным локальным портам, включая API. Временный VLESS-сервер
разрешает только точный порт локальной HTTP-цели. Контракты и сценарии
используют отдельный префикс. Рабочие службы и статус только считываются.
[Параметры Xray Freedom](https://xtls.github.io/en/config/outbounds/freedom.html#finalruleobject)

## 1. Подготовка и запуск

Из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
Если pytest в отдельном окружении, задать `XGW_TEST_PYTHON`. Для нестандартного
пути к установленному Xray задать `XGW_TEST_XRAY`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=b7765feb5dde58c96be1dae93b37ad8176b654f6
D=$(mktemp -d /tmp/xgw-freepool-m3-runtime.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-m3-runtime.bundle >"$D/code.bundle"
printf '%s  %s\n' 'c641096600d27dc0617161dcca247f0a0d9db357b90384c5f4d587b0fc843f23' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml config.example.toml \
    docs/helpers/freepool_lifecycle.py | tar -x -C "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
}
status=0
host_read_ok=0
if host_fields >"$D/before.txt"; then
  host_read_ok=1
fi
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
export XGW_ROOT="$D/isolated"
cd "$D/tree"
core_ok=0
unset XGW_XRAY_BIN XGW_TEST_FREEPOOL_XRAY
if [[ -x "$XRAY" ]] && timeout -k 2 10 "$XRAY" version >"$D/xray-version.txt" 2>&1; then
  core_ok=1
  head -n 1 "$D/xray-version.txt"
  export XGW_XRAY_BIN="$XRAY" XGW_TEST_FREEPOOL_XRAY="$XRAY"
fi

if timeout -k 5 240 "$TEST_PY" -B -m pytest -o addopts= -q -rs -p no:cacheprovider \
    tests/test_freepool.py tests/test_freepool_sources.py tests/test_freepool_refresh.py \
    tests/test_freepool_traffic.py tests/test_freepool_candidates.py \
    tests/test_freepool_selection.py tests/test_freepool_targeted.py tests/test_freepool_cancel.py \
    tests/test_freepool_backend.py tests/test_freepool_stats.py tests/test_api_integration.py \
    tests/test_config.py tests/test_fetch.py::test_parse_userinfo >"$D/contracts.log" 2>&1; then
  printf 'F13_CONTRACTS=PASS\n'
else
  printf 'F13_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 30 "$D/contracts.log"

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
  grep -E -e '^OBSERVED ' -e '^F13_' "$D/$scenario.log" || true
done

if [[ "$host_read_ok" == 1 ]] && host_fields >"$D/after.txt"; then
  if cmp -s "$D/before.txt" "$D/after.txt"; then
    printf 'F13_HOST_FIELDS_MATCH\n'
  else
    printf 'F13_HOST_FIELDS_DIFFER\n'
    status=1
  fi
else
  printf 'F13_HOST_FIELDS_NOT_RUN\n'
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

## 2. Что проверить и записать

| Блок | Достаточное наблюдение |
| --- | --- |
| Контракты | Число тестов, фактические пропуски и причины. В проверках R13 охвачены частичный каталог, два полных пропуска, ранний срок учётных данных и продление. R50 охватывает очереди и выбор региона. Дневник, отмена проверки и команды API идут в тот же прогон. |
| Ротация ключа | `F13_ROTATION=PASS`. Показать исход успешной пробы со старым UUID, отказ того же UUID после замены на сервере и успех нового UUID после его собственной пробы. Перечитать кеш. Для отказа записать наблюдаемые verdict, stage и kind. Несовпавший ключ известен по стенду. Для самого XGW отсутствие точного сообщения означает общий отказ проверки. |
| Сертификат | `F13_CERTIFICATE=PASS`. Одна цепочка и один доверенный локальный CA на валидном и просроченном сертификатах. Сначала успешная загрузка, затем `CERT_TIME_INVALID` и недопуск даже прежнего участника. После возврата валидного сертификата свежая проба восстанавливает допуск. При общем отказе без диагностической метки зафиксировать фактический вывод и FAIL для этого блока. |
| Xray API и обратное переключение | `F13_API_SWITCH_ROLLBACK=PASS`. Новое соединение идёт через новый обработчик после `ado → adrules → rmo`. После обратного применения — снова через исходный. Сам процесс Xray продолжается. Для удерживаемого соединения записать `F13_HELD_STREAM` и причину наблюдавшегося исхода. RETAINED подтверждает один обмен после снятия тега в этом ядре. CLOSED или TIMEOUT также годятся как фактическое наблюдение отдельного пункта. |
| Готовность M3 | Записать только признак свежести, состояние готовности и числа. Это проверка предпосылок. Для рабочего трафика и 24 часов требуется отдельное согласованное окно и свидетельство реальной пользовательской активности. |

При сбое одного блока выполнить остальные доступные. Указать итог каждого
блока и версию Xray. Отдельно отметить `NOT_RUN` для рабочего WAN, действующих
соединений пользователей, долгого дренирования с лимитом и суточного M3.

## 3. Публикация

Flash публикует один обезличенный `docs/reports/<UTC>_freepool-m3-runtime.md`
обычным push в `docs/flash-proton-ui-manifest` при любом исходе. При обновлении
ветки перенести только свой отчёт. Записать SHA кандидата и ТЗ, ОС, Python,
версию ядра, таблицу результатов и совпадение полей служб. Оставить полные логи,
идентификаторы ключей, конфиги и PID в локальном приватном каталоге. Системный
код Flash не редактирует.
