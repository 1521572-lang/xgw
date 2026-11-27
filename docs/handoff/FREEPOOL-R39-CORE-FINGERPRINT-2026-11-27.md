# ThinkCentre · бинарники ядер в контексте замеров FreePool R39

Ubuntu 24.04 LTS, кандидат `afd4a4ec19e30dc2876f8297d56b02c3c80255db`.
Проверить ключи замеров для Xray и моста sing-box, атомарную замену файла
ядра в изолированном каталоге и регрессии R16. [Отчёт watchdog](https://github.com/1521572-lang/xgw/blob/1b7bdc6d3df8b159c6d57118c07ecefd39a50407/docs/reports/2026-11-27T084905Z_watchdog-conncheck-isolation.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-core-fingerprint.bundle)

Flash запускает команды самостоятельно обычным пользователем. При
недоступном терминале запросить доступ. Сценарии используют временные
копии файлов и локальную сеть loopback. Штатные процессы и файлы
используются для чтения состояния и проверки версии.

## 1. Запуск

Использовать полный клон с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
При нестандартных путях задать абсолютные `XGW_TEST_PYTHON`,
`XGW_TEST_XRAY` или `XGW_TEST_SINGBOX`. Для изолированного запуска
используются уже установленные ядра.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=afd4a4ec19e30dc2876f8297d56b02c3c80255db
BRIDGE_FIXTURE=7ae63fabe8f21128a8bb5ae15c81d2c031362c69
D=$(mktemp -d /tmp/xgw-r39-core-fingerprint.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' \
    "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-core-fingerprint.bundle >"$D/code.bundle"
printf '%s  %s\n' '04288c93abb7fb399debffd24665973236f3afb582fc8618a91f32ab9fa4f275' "$D/code.bundle" | sha256sum --check -
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
    tests/test_singbox_generations.py tests/test_freepool_wan_epoch.py
record_case WATCHDOG_CONTRACTS tests/test_daemon.py tests/test_conncheck.py \
    -k 'conncheck or watchdog_schedule or test_watchdog_wakes or pool_region_reload'

cat >"$D/binary_fixture.py" <<'PYTHON'
import shutil
import socket
import sys
from pathlib import Path

from xgw.paths import atomic_write_json
from xgw.xraycore.service import ProcessXrayService, measurement_generation

kind, source, root = sys.argv[1:]
source, root = Path(source).resolve(strict=True), Path(root)
assert root.is_absolute()
root.mkdir(mode=0o700)
binary = root / kind
replacement = root / "next"
config = root / "config.json"

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
if kind == "xray":
    spec = {"log": {"loglevel": "warning"}, "api": {
        "tag": "api", "listen": f"127.0.0.1:{port}", "services": ["HandlerService"],
    }}
elif kind == "sing-box":
    spec = {
        "log": {"level": "error"},
        "inbounds": [{"type": "socks", "tag": "local", "listen": "127.0.0.1",
                      "listen_port": port}],
        "outbounds": [{"type": "direct", "tag": "local-only"}],
        "route": {"rules": [{"action": "reject"}]},
    }
else:
    raise ValueError(kind)
atomic_write_json(config, spec)


def install(suffix=b""):
    shutil.copyfile(source, replacement)
    if suffix:
        with replacement.open("ab") as out:
            out.write(suffix)
    replacement.chmod(0o700)
    replacement.replace(binary)


install()
service = ProcessXrayService(binary, config)
try:
    service.start()
    invocation = service.runtime_generation()
    before = measurement_generation(service, None)
    assert invocation and before and measurement_generation(service, None) == before
    install()
    assert service.runtime_generation() == invocation
    assert measurement_generation(service, None) == before
    install(b"XGW fixture marker")
    updated = measurement_generation(service, None)
    assert service.runtime_generation() == invocation and updated and updated != before
    binary.unlink()
    assert service.runtime_generation() == invocation
    assert measurement_generation(service, None) is None
    install()
    assert measurement_generation(service, None) == before
finally:
    service.stop()
assert measurement_generation(service, None) is None
print(f"R39_BINARY_FIXTURE_{kind}=PASS")
PYTHON

for kind in xray sing-box; do
  case "$kind" in
    xray) installed=$XRAY ;;
    sing-box) installed=$SINGBOX ;;
  esac
  if [[ ! -x "$installed" ]]; then
    printf 'R39_BINARY_FIXTURE_%s=NOT_RUN (binary unavailable)\n' "$kind"
    continue
  fi
  if timeout -k 2 10 "$installed" version >"$D/$kind.fixture-version.log" 2>&1; then
    head -n 1 "$D/$kind.fixture-version.log"
  else
    printf 'R39_BINARY_FIXTURE_%s=FAIL (version unavailable)\n' "$kind"
    status=1
    continue
  fi
  if timeout -k 4 70 /usr/bin/python3 -B -P "$D/binary_fixture.py" \
      "$kind" "$installed" "$D/fixture-$kind" >"$D/$kind.fixture.log" 2>&1; then
    cat "$D/$kind.fixture.log"
  else
    printf 'R39_BINARY_FIXTURE_%s=FAIL\n' "$kind"
    status=1
  fi
done

if [[ -x "$XRAY" && -x "$SINGBOX" ]]; then
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

| Блок | Что зафиксировать |
| --- | --- |
| Контракты | `R39_CONTEXT=PASS`, `WATCHDOG_CONTRACTS=PASS`, `R16_CONTRACTS=PASS`, число тестов и причины пропусков. При изменении бинарника Xray во время пробы байты учитываются, прежний замер сохраняется в истории. Ключ моста меняется при подмене файла sing-box. |
| Два ядра, две частные копии | По каждому `R39_BINARY_FIXTURE_*=PASS`. Идентичная замена файла сохраняет ключ. Другие байты меняют ключ при прежнем запуске процесса. Удалённый файл скрывает ключ, восстановление исходных байтов его возвращает. После выхода процесса ключ недоступен. Версии ядер записать. |
| Мост | `R39_BRIDGE_LOOPBACK=PASS`. Используется исходный 32-символьный ID. Загрузка до и после перезапуска sing-box, отказ при остановке, смена отпечатка моста и стабильный прямой путь. |
| Штатный шлюз | Записать `R39_HOST_XRAY`, `R39_HOST_SINGBOX`, `R39_HOST_FIELDS_MATCH` и `M3_PREFLIGHT`. Неактивная служба или неподтверждённый запуск дают `NOT_RUN`. В systemd ключ использует штатный файл установки и идентификатор запуска. Байты из адресного пространства процесса этим блоком не проверяются. |
| Сценарии Xray | Отдельно зафиксировать `region-route`, `rotation`, `certificate`, `api-switch` и результаты удерживаемых соединений. |

При сбое продолжить остальные доступные блоки. Указать `NOT_RUN` для смены
рабочего WAN, переключения рабочих поколений, принудительного завершения
потоков и суточного M3. Полные логи и идентификаторы оставить в
`PRIVATE_ARTIFACTS`.

## 3. Публикация

Flash автоматически публикует один обезличенный
`docs/reports/<UTC>_freepool-r39-core-fingerprint.md` обычным push в ветку
`docs/flash-proton-ui-manifest` при любом исходе. Указать SHA кандидата и ТЗ,
версии Ubuntu, Python, pytest и обоих доступных ядер, таблицу результатов и
причины пропусков. При изменении ветки перенести отчёт на актуальную
вершину. Системный код редактирует разработчик.
