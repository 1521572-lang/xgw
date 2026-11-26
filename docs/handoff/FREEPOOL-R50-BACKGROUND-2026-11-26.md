# ThinkCentre · пауза фоновой работы FreePool R50

Ubuntu 24.04 LTS. Кандидат `d190be300601bced380f4f73e678be658358db5a`. Предыдущий проход подтвердил отмену
текущей пробы с Xray 26.11.9. Фазы для 320 записей `TIMEOUT` остаются
неизвестны. Этот проход проверяет паузу и возобновление, не повторяя чтение
старых записей. [Отчёт отмены](https://github.com/1521572-lang/xgw/blob/1d4cefb7cb25b8501a691b4673069d3a2ab68277/docs/reports/2026-11-26T140901Z_freepool-r50-probe-cancel.md)

Flash выполняет команды сама. При недоступности терминала либо чтения
полей штатного шлюза запросить доступ. Экземпляр для испытаний запускается
с `XGW_ROOT` в приватном каталоге 0700. Опрос источников и проверки участников
в контрактах подменены. Штатный демон и маршруты работают в прежнем
режиме. [Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r50-background.bundle)

## Прогон

Открыть полный клон с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. Если pytest установлен в отдельном
окружении, задать `XGW_TEST_PYTHON` с путём к его Python.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=d190be300601bced380f4f73e678be658358db5a
D=$(mktemp -d "$HOME/xgw-freepool-background.XXXXXXXX")
PY=/usr/bin/python3
TEST_PY=$PY
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
unset XGW_TEST_FREEPOOL_XRAY
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r50-background.bundle >"$D/code.bundle"
printf '%s  %s\n' '39dc0520782a3c4e4fb15a154ac4ac3cde8784e42a4857fcb102a84c83d81647' "$D/code.bundle" | sha256sum --check -
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
  tests/test_freepool_cancel.py tests/test_freepool.py tests/test_freepool_traffic.py \
  tests/test_freepool_backend.py tests/test_panel.py::test_free_pool_card_switches_observation \
  >"$D/daemon.log" 2>&1 || status=1
tail -n 20 "$D/daemon.log"

isolated() (
  local root="$D/control"
  install -d "$root/etc/xgw" "$root/run/xgw" || return
  printf '[free_pool]\nmode = "observe"\n' >"$root/etc/xgw/config.toml" || return
  printf '{"free_pool_mode":"observe","routes":[]}\n' >"$root/etc/xgw/panel.json" || return
  printf '{"updated":%s,"free_pool":{"mode":"observe","region":"EU"}}\n' "$(date +%s)" \
    >"$root/run/xgw/status.json" || return
  sha256sum "$root/etc/xgw/config.toml" "$root/etc/xgw/panel.json" >"$D/control-before.txt" || return
  export XGW_ROOT="$root"
  "$PY" -B -P -m xgw.cli pool pause-background &&
    "$PY" -B -P -m xgw.cli pool status --json >"$D/paused.json" &&
    "$PY" -B -P -m xgw.cli pool resume-background &&
    "$PY" -B -P -m xgw.cli pool status --json >"$D/resumed.json" || return
  unset XGW_ROOT
  sha256sum -c "$D/control-before.txt" || return
  [[ $(stat -c %a "$root/var/lib/xgw/freepool/background.json") == 600 ]] || return 1
  "$PY" -I -B - "$D" <<'PYTHON'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for name, value in (("paused", True), ("resumed", False)):
    data = json.loads((root / f"{name}.json").read_bytes())
    assert data["mode"] == "observe" and data["background_paused"] is value
print("R50_BACKGROUND_CLI_OK")
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

- `R50_BACKGROUND=PASS` при зелёных наборах, метке `R50_BACKGROUND_CLI_OK` и совпавших полях штатного
  шлюза. Пропуск теста с установленным ядром ожидается: этот сценарий
  принят в предыдущем отчёте.
- Указать, что именно подтвердилось. Новые опросы и поисковые замеры
  откладываются, действующий выход и проверка его здоровья остаются.
  Пауза, замеченная пробой нового кандидата, сохраняется до завершения
  отмены даже при быстром возобновлении. Уже начатый опрос источника или
  замер скорости может завершиться. После возобновления плановые сроки
  и лимиты остаются действующими.
- При любом исходе опубликовать один обезличенный `docs/reports/<UTC>_freepool-r50-background.md` в ветке
  `docs/flash-proton-ui-manifest` обычным push. Указать SHA кандидата и ТЗ, ОС, результаты
  контрактов и CLI, итог сверки. Содержимое конфигов, журналы и адреса
  оставить локально. При конфликте перенести только отчёт поверх
  актуальной вершины.
