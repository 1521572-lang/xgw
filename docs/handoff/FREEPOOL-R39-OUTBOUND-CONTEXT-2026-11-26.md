# ThinkCentre · контекст выхода Xray для замеров FreePool R39

Ubuntu 24.04 LTS. Кандидат `1ef2fbf93db580d296f924de95c5978f67e689cb`. Проверить связь замера
с применённым выходом и звеньями цепочки в конфиге Xray.
[Предыдущее подтверждение маршрута и F16](https://github.com/1521572-lang/xgw/blob/9ef255c72f74d890f135bce39307daddb0c88e28/docs/reports/2026-11-26T171042Z_freepool-f16-r39.md) · [Подтверждение параметров замера](https://github.com/1521572-lang/xgw/blob/3de2440e107a7bf00e802f79f31ebf631d25dc67/docs/reports/2026-11-26T171220Z_freepool-r39-probe-parameters.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-outbound-context.bundle)

Flash выполняет команды сама. При недоступном терминале запросить
доступ. Команды используют приватный временный каталог, фикстуры и
локальный HTTP-сервер тестов. Установленный Xray проверяет два
синтетических конфига командой `run -test`. Рабочий конфиг и подписки
для прогона не нужны. Зафиксировать установленную версию Xray и
использовать её. Замена ядра для этого задания не требуется.

## Прогон

Из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`
выполнить от обычного пользователя. Путь к Python с pytest указывается
через `XGW_TEST_PYTHON`, путь к установленному ядру — `XGW_TEST_XRAY`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=1ef2fbf93db580d296f924de95c5978f67e689cb
D=$(mktemp -d "$HOME/xgw-freepool-r39-outbound.XXXXXXXX")
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-outbound-context.bundle >"$D/code.bundle"
printf '%s  %s\n' '193133c91683128cb0bf698ed300465b745933f683a1413adb0ad1724b03ebac' "$D/code.bundle" | sha256sum --check -
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
if timeout -k 5 150 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool_traffic.py tests/test_freepool_wan_epoch.py tests/test_speed.py \
    tests/test_daemon.py::test_pool_region_reload_only_prioritizes_rebuild_when_pool_carries_traffic \
    >"$D/contracts.log" 2>&1; then
  printf 'R39_OUTBOUND_CONTRACTS=PASS\n'
else
  printf 'R39_OUTBOUND_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 25 "$D/contracts.log"

fixtures() {
  "$PY" -B -P - "$D" <<'PYTHON'
import json
import sys
from pathlib import Path

from xgw.generator.builder import pool_outbound_keys

root = Path(sys.argv[1])
a, b = "pool-de-aaaa", "pool-de-bbbb"
cfg = {"outbounds": [
    {"tag": a, "protocol": "freedom",
     "streamSettings": {"sockopt": {"dialerProxy": "hop"}}},
    {"tag": b, "protocol": "freedom"},
    {"tag": "hop", "protocol": "freedom", "settings": {"domainStrategy": "AsIs"}},
]}
before = pool_outbound_keys(cfg)
assert set(before) == {a, b}
(root / "before-xray.json").write_text(json.dumps(cfg), encoding="utf-8")
cfg["outbounds"][2]["settings"]["domainStrategy"] = "UseIP"
after = pool_outbound_keys(cfg)
assert set(after) == {a, b} and after[a] != before[a] and after[b] == before[b]
(root / "after-xray.json").write_text(json.dumps(cfg), encoding="utf-8")
PYTHON
}
if fixtures; then
  printf 'R39_OUTBOUND_FIXTURE=PASS\n'
  if [[ -x "$XRAY" ]]; then
    if timeout -k 2 10 "$XRAY" version >"$D/xray-version.txt" 2>&1 &&
       timeout -k 2 15 "$XRAY" run -test -config "$D/before-xray.json" >"$D/xray-before.log" 2>&1 &&
       timeout -k 2 15 "$XRAY" run -test -config "$D/after-xray.json" >"$D/xray-after.log" 2>&1; then
      head -n 1 "$D/xray-version.txt"
      printf 'R39_OUTBOUND_XRAY_PARSE=PASS\n'
    else
      printf 'R39_OUTBOUND_XRAY_PARSE=FAIL\n'
      status=1
    fi
  else
    printf 'R39_OUTBOUND_XRAY_PARSE=NOT_RUN\n'
  fi
else
  printf 'R39_OUTBOUND_FIXTURE=FAIL\n'
  status=1
fi

host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R39_OUTBOUND_HOST_FIELDS_MATCH\n'
else
  printf 'R39_OUTBOUND_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- Для `R39_OUTBOUND_CONTEXT=PASS` нужны зелёные контракты,
  `R39_OUTBOUND_FIXTURE=PASS`, `R39_OUTBOUND_XRAY_PARSE=PASS` и
  совпадение полей служб. При недоступном ядре указать причину и
  отдельно отразить результат контрактов.
- По контрактам подтвердить стабильность при правке несвязанного
  выхода и при перестановке блоков, смену отпечатка одного участника
  при изменении звена, отказ при недостающем звене и цикле. При смене
  выхода во время замера байты учтены, результат скорости отбрасывается.
  Указать, что замер второго участника остаётся видимым и что
  запись без отпечатка выхода считается исторической.
- Проверка использует файл применённого конфига как источник состава
  цепочки. Публичная WAN-идентичность, бинарники ядер, внутренняя
  конфигурация sing-box за мостом, рабочий трафик и сутки M3 открыты.
- При любом исходе Flash публикует один обезличенный
  `docs/reports/<UTC>_freepool-r39-outbound-context.md` в ветке
  `docs/flash-proton-ui-manifest` обычным push. Указать SHA задания и
  кандидата, ОС, число тестов, версию ядра и исходы. При расхождении
  ветки перенести только отчёт поверх актуальной вершины. Конфиги,
  отпечатки и журналы оставить локально. Системный код Flash не меняет.
