# ThinkCentre · поколение процесса Xray для FreePool R39

Ubuntu 24.04 LTS. Кандидат `3f8549786ce443a046815336fd2f86be6450897f`. Проверить, что замер скорости
FreePool сохраняет применимость в рамках одного запуска Xray и теряет
её после смены запуска.
[Отчёт о цепочке выхода](https://github.com/1521572-lang/xgw/blob/bc40e926e2b51ece2da55791a1aa57f13c4cae25/docs/reports/2026-11-26T172158Z_freepool-r39-outbound-context.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-xray-generation.bundle)

Flash выполняет команды сама. При недоступном терминале запросить доступ.
Чтение статуса рабочей службы выполняется без записи. Для проверки
перезапуска команды запускают собственный непривилегированный процесс
Xray с UNIX-сокетом в приватном временном каталоге. Рабочие подписки,
конфиги и трафик не нужны. Использовать установленную версию ядра.

## Прогон

От обычного пользователя из полного клона с базой
`9e4c025efb5404086ae601f3dc535a9e881521dd`. Пути к Python с pytest и к
установленному ядру задаются через `XGW_TEST_PYTHON` и `XGW_TEST_XRAY`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=3f8549786ce443a046815336fd2f86be6450897f
D=$(mktemp -d /tmp/xgw-r39-xray.XXXXXXXX)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-xray-generation.bundle >"$D/code.bundle"
printf '%s  %s\n' '091cf90eaae62639c640999dc449756420d3b59359b0575a173ce5cb2e324040' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml | tar -x -C "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
}
host_fields >"$D/before.txt"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"
status=0
if timeout -k 5 180 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool_traffic.py tests/test_freepool_wan_epoch.py tests/test_speed.py \
    tests/test_runtime.py tests/test_daemon.py::test_pool_region_reload_only_prioritizes_rebuild_when_pool_carries_traffic \
    >"$D/contracts.log" 2>&1; then
  printf 'R39_XRAY_GENERATION_CONTRACTS=PASS\n'
else
  printf 'R39_XRAY_GENERATION_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 25 "$D/contracts.log"

if ! timeout -k 3 10 "$PY" -B -P - <<'PYTHON'
from xgw.xraycore.service import SystemdXrayService

service = SystemdXrayService()
if not service.is_active():
    print("R39_XRAY_SYSTEMD=NOT_RUN")
else:
    first = service.runtime_generation()
    second = service.runtime_generation()
    if first and second == first:
        print("R39_XRAY_SYSTEMD=PASS")
    else:
        print("R39_XRAY_SYSTEMD=FAIL")
        raise SystemExit(1)
PYTHON
then
  status=1
fi

if [[ -x "$XRAY" ]]; then
  if timeout -k 2 10 "$XRAY" version >"$D/xray-version.txt" 2>&1; then
    head -n 1 "$D/xray-version.txt"
  else
    printf 'R39_XRAY_VERSION=FAIL\n'
    status=1
  fi
  if timeout -k 5 25 "$PY" -B -P - "$D" "$XRAY" >"$D/isolated.log" 2>&1 <<'PYTHON'
import json
import sys
from pathlib import Path

from xgw.xraycore.service import ProcessXrayService

run_dir, binary = Path(sys.argv[1]), Path(sys.argv[2])
settings = {
    "log": {"loglevel": "warning"},
    "api": {"tag": "api", "listen": str(run_dir / "api.sock"), "services": ["StatsService"]},
    "stats": {},
    "outbounds": [{"tag": "direct", "protocol": "freedom"}],
}
config = run_dir / "xray.json"
config.write_text(json.dumps(settings), encoding="utf-8")
service = ProcessXrayService(binary, config)
assert service.runtime_generation() is None
try:
    service.start()
    first = service.runtime_generation()
    assert first and service.runtime_generation() == first
    service.restart()
    second = service.runtime_generation()
    assert second and second != first and service.runtime_generation() == second
finally:
    service.stop()
assert service.runtime_generation() is None
print("R39_XRAY_CHILD=PASS")
PYTHON
  then
    cat "$D/isolated.log"
  else
    printf 'R39_XRAY_CHILD=FAIL\n'
    status=1
  fi
else
  printf 'R39_XRAY_CHILD=NOT_RUN\n'
fi

host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R39_XRAY_GENERATION_HOST_FIELDS_MATCH\n'
else
  printf 'R39_XRAY_GENERATION_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- `R39_XRAY_GENERATION=PASS` требует зелёных контрактов, чтения
  поколения рабочей службы, прохождения проверки собственного процесса
  и совпадения полей рабочих служб. Указать ОС, версию Xray, кандидата,
  SHA задания и отдельные исходы. При недоступном ядре или неактивной
  службе зафиксировать причину `NOT_RUN`.
- Проверить, что смена поколения к моменту запуска пробы откладывает её,
  а смена во время пробы сохраняет учёт байтов без результата скорости.
  Прежний замер и замер без поколения остаются в кеше и исключаются из
  выбора и текущей сводки. Живое закрепление сохраняется по контракту.
- Хеш содержимого бинарника Xray, ядро и внутренний маршрут sing-box,
  рабочий перезапуск Xray, публичный WAN и сутки M3 остаются открытыми.
- При любом исходе Flash публикует один обезличенный
  `docs/reports/<UTC>_freepool-r39-xray-generation.md` в ветке
  `docs/flash-proton-ui-manifest` обычным push. При расхождении ветки
  перенести только отчёт поверх актуальной вершины. Идентификаторы,
  PID, снимки, конфиги и полные журналы оставить локально.
  Системный код Flash не меняет.
