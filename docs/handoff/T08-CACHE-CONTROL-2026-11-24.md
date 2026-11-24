# ThinkCentre — ручное исключение подсказок по точному CDN-контексту

**Ubuntu 24.04 LTS.** Flash сама выполняет готовые команды и автоматически
публикует обезличенный отчёт. При недоступности терминала, окружения для
pytest, браузера или GitHub запроси доступ. Выполни доступные фазы независимо.

CLI кэша получил команды `exclusions`, `exclude` и `restore`. Ключ —
`context_id` из записи воспроизведения, который включает точный IP и
контекст замера. Исключение отключает подсказку по этому ключу и сохраняется
после `rebuild`. `restore` снова разрешает подсказку, если история свежая
и по ней есть два пригодных раунда. Команды сохраняют исходные замеры и
возвращают `apply:false`. [Базовая приёмка кэша](../reports/2026-11-16_desync-t08-cache.md)

Последний отчёт ALT9 подтвердил 18/18 в закреплённой лаборатории и успешные
формы. В повторе веб-фазы устраняем ошибки временной копии: архив теперь
содержит `vpn_ui`, демо-перехват отвечает на `mode()`, каждый старт Firefox
получает отдельный каталог профиля. В активном режиме поле явно помечено
«Только чтение». [Отчёт ALT9](../reports/2026-11-24T183129Z_flowseal-ui.md)

## Проверки на машине

Если нужно, задай абсолютный путь `XGW_TEST_PYTHON` для pytest. Для второго
этапа применимы `XGW_WEB_PYTHON`, `XGW_QT_PYTHON` и `XGW_GECKODRIVER` из
[ТЗ на формы](FLOWSEAL-UI-2026-11-24.md). Выполни `sudo -v` перед этапом
форм для чтения состояния шлюза. Запусти блок из рабочей копии.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=a33aa8b5bfb3df56e000bba9da96b7511e1a06cd
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t08-control.XXXXXXXX")
printf 'PINNED %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir "$D/tree" "$D/state"
git -C "$REPO" archive "$CODE" src tests docs/helpers pyproject.toml | tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
test_rc=0
timeout -k 3 100 "$TEST_PY" -B -P -m pytest --portable -o addopts= -p no:cacheprovider \
  -q --tb=short tests/test_desync_cache.py tests/test_desync_shadow.py \
  >"$D/cache-contracts.out" 2>&1 || test_rc=$?
tail -n 6 "$D/cache-contracts.out"
printf 'T08_CONTRACTS_EXIT %s\n' "$test_rc"

cli_trial() (
  set -euo pipefail
  "$PY" -B -I - "$D" <<'PY'
import json
import sys
import time
from pathlib import Path

folder = Path(sys.argv[1])
rows = []
for letter in ("a", "d"):
    for index, age in enumerate((700, 350)):
        finished = int(time.time()) - age
        rows.append({"measurement_version": 2, "context_id": letter * 64,
                     "prefix_context_id": "b" * 64, "host_context_id": "c" * 64,
                     "recording_id": f"{len(rows) + 1:064x}", "candidate": "fixture",
                     "round": f"round-{index}", "started": finished - 130,
                     "finished": finished, "outcome": "pass"})
(folder / "history.json").write_text(json.dumps(rows), encoding="utf-8")
PY
  A=$("$PY" -I -B -c 'print("a" * 64)')
  B=$("$PY" -I -B -c 'print("d" * 64)')
  CACHE=("$PY" -B -P -m xgw.desync.cache)
  H=(--history "$D/history.json" --state-dir "$D/state")
  S=(--state-dir "$D/state")
  sha256sum "$D/history.json" >"$D/history.sha256"
  "${CACHE[@]}" rebuild "${H[@]}" >"$D/rebuild.json"
  "${CACHE[@]}" lookup "${H[@]}" --context "$A" >"$D/initial.json"
  "${CACHE[@]}" exclude "${S[@]}" --context "$A" >"$D/exclude.json"
  "${CACHE[@]}" exclude "${S[@]}" --context "$A" >"$D/repeat.json"
  "${CACHE[@]}" exclusions "${S[@]}" >"$D/selection.json"
  "${CACHE[@]}" rebuild "${H[@]}" >"$D/rebuilt.json"
  "${CACHE[@]}" lookup "${H[@]}" --context "$A" >"$D/excluded.json"
  "${CACHE[@]}" lookup "${H[@]}" --context "$B" >"$D/other.json"
  "${CACHE[@]}" restore "${S[@]}" --context "$A" >"$D/restore.json"
  "${CACHE[@]}" lookup "${H[@]}" --context "$A" >"$D/restored.json"
  sha256sum --check --status "$D/history.sha256"
  "$PY" -B -I - "$D" "$A" <<'PY'
import json
import stat
import sys
from pathlib import Path

folder, expected = Path(sys.argv[1]), sys.argv[2]
states = {"rebuild": "rebuilt", "initial": "hit", "exclude": "excluded", "repeat": "excluded",
          "selection": "exclusions", "rebuilt": "rebuilt", "excluded": "excluded", "other": "hit",
          "restore": "restored", "restored": "hit"}
rows = {name: json.loads((folder / f"{name}.json").read_bytes()) for name in states}
assert all(row["apply"] is False and row["state"] == states[name] for name, row in rows.items())
assert rows["exclude"]["changed"] is True and rows["repeat"]["changed"] is False
assert rows["selection"]["contexts"] == [expected] and rows["excluded"]["candidates"] == []
assert rows["restored"]["candidates"] == rows["initial"]["candidates"]
assert stat.S_IMODE((folder / "state/playback-shadow-exclusions.json").stat().st_mode) == 0o600
print("T08_EXACT_CONTROL_OK")
PY
)
# Run this phase separately so its exit status is preserved without skipping the UI phase.
set +e
cli_trial
cache_rc=$?
set -e
printf 'T08_CLI_EXIT %s\n' "$cache_rc"

ui_rc=0
(cd "$REPO" && bash "$D/tree/docs/helpers/flowseal_ui_trial.sh" "$CODE" ui) \
  >"$D/ui.out" 2>"$D/ui.err" || ui_rc=$?
cat "$D/ui.out"
printf 'FLOWSEAL_UI_RECHECK_EXIT %s\n' "$ui_rc"
[[ $test_rc == 0 && $cache_rc == 0 && $ui_rc == 0 ]]
BASH
~~~

Зафиксируй SHA, Ubuntu и итоги трёх этапов. Для T08 нужны
`T08_EXACT_CONTROL_OK`, успешные проверки одновременной записи и отказа
перед заменой файла, а также отсутствие изменений исходной истории.
Для UI нужны закреплённые контракты, четыре метки Firefox, результат Qt и
сверка шлюза. Используй vision для обоих снимков и сверь явную пометку
«Только чтение» в имитации Standalone. Повтор 18 TLS-сеансов уже принят.
Ключи кэша, сырые журналы и снимки остаются на машине. Live CDN и перенос
подсказок на другие IP в этом ТЗ не проверяются.

## Автоматическая публикация

Укажи абсолютный путь к готовому обезличенному отчёту в `REPORT_SRC`.
Выполни блок также при частичном результате. Верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t08-control-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t08-cache-control.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre exact cache control and ALT9 form recheck'
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
git fetch origin "$BR"
git merge-base --is-ancestor HEAD FETCH_HEAD
printf 'PUBLISHED %s %s\n' "$(git rev-parse HEAD)" "$REPORT"
BASH
~~~
