# ThinkCentre · опрос выбранного источника FreePool R50

Ubuntu 24.04 LTS. Кандидат `7ab4f7d2a29e6c6ef92b587024d1510d571a80ed`. Пауза и возобновление прошли приёмку.
Этот проход проверяет `xgw pool refresh --source vpngate` и сохранение сроков планировщика.
[Отчёт о паузе](https://github.com/1521572-lang/xgw/blob/a179877945098ad85b389dc7d7bfea7e50502226/docs/reports/2026-11-26T144848Z_freepool-r50-background.md)

Flash выполняет команды сама. При недоступности терминала или разрешённого
чтения состояния запросить доступ. Запросы CLI используют временный
`XGW_ROOT`. Контракты подменяют ответы источников и проверяют переходы времени,
в том числе `RATE_LIMITED (429)`. Рабочий экземпляр шлюза продолжает работу.
[Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r50-source-refresh.bundle)

## Прогон

Выполнить из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. Если pytest установлен в другом
окружении, указать путь через `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=7ab4f7d2a29e6c6ef92b587024d1510d571a80ed
D=$(mktemp -d "$HOME/xgw-freepool-source-refresh.XXXXXXXX")
PY=/usr/bin/python3
TEST_PY=$PY
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r50-source-refresh.bundle >"$D/code.bundle"
printf '%s  %s\n' 'ca11832347b57d6ed24ce4b0ba897e6dabc1e1e6e5b95b9a6aa1c5f1e2180248' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\n' "$PRETTY_NAME" "$CODE"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
host_fields >"$D/before.txt"
status=0
timeout -k 3 120 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider --portable \
  tests/test_freepool_background.py tests/test_freepool_candidates.py \
  tests/test_freepool_sources.py tests/test_freepool_stats.py \
  >"$D/portable.log" 2>&1 || status=1
tail -n 18 "$D/portable.log"
timeout -k 3 120 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
  tests/test_freepool_refresh.py tests/test_freepool.py \
  tests/test_panel.py::test_free_pool_card_switches_observation \
  >"$D/refresh.log" 2>&1 || status=1
tail -n 18 "$D/refresh.log"

isolated() (
  local root="$D/control"
  export XGW_ROOT="$root"
  install -d "$root/etc/xgw" "$root/run/xgw" || return
  printf '[free_pool]\nmode = "observe"\nproviders = ["vpngate"]\n' \
    >"$root/etc/xgw/config.toml" || return
  printf '{"updated":%s,"free_pool":{"mode":"observe"}}\n' "$(date +%s)" \
    >"$root/run/xgw/status.json" || return
  "$PY" -B -P -m xgw.cli pool refresh --source vpngate &&
    "$PY" -B -P -m xgw.cli pool refresh --source vpngate &&
    "$PY" -B -P -m xgw.cli pool status --json >"$D/pending.json" || return
  if "$PY" -B -P -m xgw.cli pool refresh --source vpnbook; then return 1; fi
  "$PY" -B -P -m xgw.cli pool pause-background || return
  if "$PY" -B -P -m xgw.cli pool refresh --source vpngate; then return 1; fi
  "$PY" -B -P -m xgw.cli pool resume-background &&
    "$PY" -B -P -m xgw.cli pool status --json >"$D/resumed.json" || return
  [[ $(stat -c %a "$root/var/lib/xgw/freepool/refresh-requests.json") == 600 ]] || return 1
  "$PY" -I -B - "$D" <<'PYTHON'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
for name in ("pending", "resumed"):
    data = json.loads((run / f"{name}.json").read_bytes())
    assert data["mode"] == "observe" and data["refresh_pending"] == ["vpngate"]
print("R50_SOURCE_REFRESH_CLI_OK")
PYTHON
)
isolated >"$D/isolated.log" 2>&1 || status=1
tail -n 12 "$D/isolated.log"

host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R50_HOST_FIELDS_MATCH\n'
else
  printf 'R50_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Итог

- `R50_SOURCE_REFRESH=PASS` требует зелёных наборов, `R50_SOURCE_REFRESH_CLI_OK` и совпавших полей шлюза.
  Указать, что очередь объединила повтор, дождалась срока и паузы, а
  результат попытки сохранён до снятия запроса. При `RATE_LIMITED (429)` сохраняются
  принятый каталог и срок повтора, включая создание нового планировщика.
  При ошибке сохранения запрос остаётся в очереди.
- Указать, что срабатывание планировщика принято на фикстуре ответов,
  а CLI и файл очереди проверены на ThinkCentre в отдельном префиксе.
- Опубликовать один обезличенный `docs/reports/<UTC>_freepool-r50-source-refresh.md` в ветке `docs/flash-proton-ui-manifest` обычным push
  при любом исходе. Указать SHA кандидата и ТЗ, ОС, результаты контрактов,
  CLI и сверки шлюза. Исходные кеши, конфиги и журналы оставить локально.
  При конфликте перенести только отчёт поверх актуальной вершины.
