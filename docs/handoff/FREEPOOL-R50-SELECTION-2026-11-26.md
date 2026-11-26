# ThinkCentre · выбор региона FreePool R50

Ubuntu 24.04 LTS. Кандидат `84964168b9b504a298f7079d190a7a58ad1ed93c`. Целевая проверка кандидата принята
на изолированном экземпляре. Этот проход проверяет `xgw pool select --region US --policy strict` и `xgw pool select --reset`.
[Отчёт целевой проверки](https://github.com/1521572-lang/xgw/blob/50cf1cf2eb815f0d3abc8314fdb43be011a9d328/docs/reports/2026-11-26T160114Z_freepool-r50-targeted.md)

Flash выполняет команды сама. При недоступности терминала либо чтения
полей рабочего шлюза запросить доступ. CLI использует временный `XGW_ROOT`.
Активный пул, каталоги с выходами и пересборка проверяются контрактами.
Рабочие службы и назначения клиентов остаются в текущем состоянии.
[Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r50-selection.bundle)

## Прогон

Выполнить из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. Если pytest установлен
в отдельном окружении, указать путь через `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=84964168b9b504a298f7079d190a7a58ad1ed93c
D=$(mktemp -d "$HOME/xgw-freepool-selection.XXXXXXXX")
PY=/usr/bin/python3
TEST_PY=$PY
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r50-selection.bundle >"$D/code.bundle"
printf '%s  %s\n' 'acfebf47d2e8d4bb55168db8c5c1f0d817d6043f4a7e4fb1fcb8083680f21c32' "$D/code.bundle" | sha256sum --check -
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
tail -n 20 "$D/portable.log"
timeout -k 3 120 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
  tests/test_freepool_selection.py tests/test_freepool.py tests/test_freepool_traffic.py \
  tests/test_panel.py::test_free_pool_card_switches_observation \
  tests/test_daemon.py::test_pool_region_reload_only_prioritizes_rebuild_when_pool_carries_traffic \
  >"$D/selection.log" 2>&1 || status=1
tail -n 20 "$D/selection.log"

isolated() (
  local root="$D/control"
  export XGW_ROOT="$root"
  install -d "$root/etc/xgw" "$root/run/xgw" || return
  printf '[free_pool]\nmode = "observe"\nregion = "EU"\nregion_policy = "preferred"\nfallback_regions = ["ASIA"]\n' \
    >"$root/etc/xgw/config.toml" || return
  printf '{"free_pool_mode":"observe","routes":[]}\n' >"$root/etc/xgw/panel.json" || return
  printf '{"updated":%s,"free_pool":{"mode":"observe","region":"EU","region_policy":"preferred"}}\n' \
    "$(date +%s)" >"$root/run/xgw/status.json" || return
  sha256sum "$root/etc/xgw/config.toml" >"$D/control-before.sha" || return
  "$PY" -B -P -m xgw.cli pool select --region US --policy strict &&
    "$PY" -B -P -m xgw.cli pool status --json >"$D/selected.json" &&
    cp "$root/etc/xgw/panel.json" "$D/selected-panel.json" &&
    "$PY" -B -P -m xgw.cli pool select --reset &&
    "$PY" -B -P -m xgw.cli pool status --json >"$D/reset.json" || return
  sha256sum -c "$D/control-before.sha" || return
  [[ $(stat -c %a "$root/etc/xgw/panel.json") == 600 ]] || return 1
  "$PY" -B -P - "$D" <<'PYTHON'
import json
import sys
from pathlib import Path

from xgw import config
from xgw.paths import Paths

run = Path(sys.argv[1])
selected = json.loads((run / "selected.json").read_bytes())
reset = json.loads((run / "reset.json").read_bytes())
saved = json.loads((run / "selected-panel.json").read_bytes())
assert selected["selection"] == {"region": "US", "policy": "strict"}
assert selected["mode"] == "observe" and selected["region"] == "EU"
assert saved["free_pool_selection"] == {"region": "US", "policy": "strict"}
assert reset["selection"] == {"region": "EU", "policy": "preferred"}
assert reset["mode"] == "observe"
cfg, _ = config.load(Paths.from_env().config_file)
assert cfg.free_pool.fallback_regions == ["ASIA"] and not cfg.managed.routes
print("R50_SELECTION_CLI_OK")
PYTHON
)
isolated >"$D/isolated.log" 2>&1 || status=1
tail -n 14 "$D/isolated.log"

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

- `R50_SELECTION=PASS` требует зелёных наборов, `R50_SELECTION_CLI_OK` и совпавших полей рабочего
  шлюза. Указать сохранение пары, режим observe, восстановление пары TOML,
  резервный регион и прежний TOML.
- По контрактам указать отказ для действующего пула при пустом новом регионе,
  допуск нужного региона после появления пригодного выхода и срочную
  пересборку. CLI показывает сохранённый выбор отдельно от сводки демона.
  При штатном применении несовместимый ручной выбор может быть снят
  существующей логикой. Сброс региона возвращает только пару регион/политика.
- В отчёте явно указать изолированный префикс и контрактную пересборку.
  Переход реального выходного трафика требует отдельного согласованного окна.
- Опубликовать один обезличенный `docs/reports/<UTC>_freepool-r50-selection.md` в ветке `docs/flash-proton-ui-manifest` обычным push
  при любом исходе. Указать SHA кандидата и задания, ОС, исходы и сверку.
  Исходные конфиги, каталоги и журналы оставить локально. При конфликте
  перенести только отчёт поверх актуальной вершины.
