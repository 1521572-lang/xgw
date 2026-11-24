# ThinkCentre · диапазон CDN в результатах матрицы

**Ubuntu 24.04 LTS.** Flash сама выполняет опубликованные команды и
публикует обезличенный отчёт при любом исходе. При отсутствии
терминала, pytest, архивов, прав чтения или GitHub запроси доступ.
Выполни доступные фазы независимо. Код меняет Codex.

[Последний отчёт](../reports/2026-11-24T205348Z_t04-cdn-range-status.md)
подтвердил 12 случаев TLS, Node 9/9 и Qt 2/2. Закреплённый набор
контрактов дал 184 pass и один сбой на старой сигнатуре дублей ALT9.
Повтор после правки дублей дал 185 pass. Поправка включена в этот
кандидат вместе с сохранением признака диапазона в матрице и мониторинге.

`two_https_pass` по-прежнему показывает успешный HTTPS в двух кругах.
`two_range_pass` перечисляет профили с двумя полными диапазонами
в завершённом задании с подтверждённым возвратом. Пробы должны
иметь явный признак, точный объём и отдельные времена начала.
`range_by_round` показывает подтверждённые, неподтверждённые и
недоступные результаты. Для старых записей без поля ожидается
`unavailable`. Офлайн-пересчёт сохраняет режим `apply:false`.

## Запуск

Начни из рабочей копии. При необходимости укажи абсолютный путь к
существующему окружению `XGW_TEST_PYTHON`. Для чтения снимка шлюза
проверь `sudo -n true`, при необходимости авторизуйся через `sudo -v`.
Контракты используют временные настройки и временную блокировку.
Архивы читаются без установки и WAN-запросов.

До запуска укажи абсолютный путь к прежнему `matrix-result.json`
в `XGW_T09_JOB` и к `direct-b-job.json` в `XGW_T09_EXTRA_JOB`, если
они доступны. При пустой переменной блок ищет файл под домашним каталогом.
Перед сравнением значений сверь, что найден тот же запуск, что в
[предыдущем пересчёте T09](../reports/2026-11-23T002922Z_t09-matrix-timing.md).

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=a444548bc494c34b9c31436bea1e8192fe85ed3a
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t09-range.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"

snapshot() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n timeout -k 3 60 "$PY" -I -B - snapshot &&
    sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
run_phase() {
  local label=$1 rc=0
  shift
  "$@" >"$D/$label.log" 2>&1 || rc=$?
  tail -n 25 "$D/$label.log"
  printf '%s_EXIT %s\n' "$label" "$rc"
  return "$rc"
}
tests() {
  local tag=$1
  shift
  timeout -k 3 150 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -v -rs --tb=short --basetemp "$D/pytest-$tag" "$@"
}
replay() {
  local tag=$1 source=$2 name=$3
  if [[ -z $source ]]; then
    source=$(find "$HOME" -maxdepth 4 -type f -name "$name" -print -quit) || return
  fi
  if [[ $source != /* || ! -f $source || ! -r $source ]]; then
    printf 'ARCHIVE_NOT_AVAILABLE %s\n' "$tag"
    return 3
  fi
  local rc=0
  sha256sum -- "$source" >"$D/$tag.sha256" || return
  timeout -k 3 25 "$PY" -B -P -m xgw.desync.client matrix --replay "$source" \
    >"$D/$tag.json" || rc=$?
  sha256sum --check --status "$D/$tag.sha256" || return
  printf 'ARCHIVE_UNCHANGED %s\n' "$tag"
  if [[ -s $D/$tag.json ]]; then cat "$D/$tag.json"; fi
  return "$rc"
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
contracts=0
run_phase CONTRACTS tests contracts --portable tests/test_desync_jobs.py \
  tests/test_zapret2_panel.py tests/test_selective_admission.py \
  tests/test_desync_tournament.py tests/test_desync_experiment.py || contracts=$?
locking=0
run_phase LOCKING tests locking tests/test_zapret2_management_linux.py || locking=$?
run_phase ARCHIVE_MAIN replay main "${XGW_T09_JOB:-}" matrix-result.json || true
run_phase ARCHIVE_EXTRA replay extra "${XGW_T09_EXTRA_JOB:-}" direct-b-job.json || true
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
gateway=NOT_VERIFIED
if [[ $before == 0 && $after == 0 ]]; then
  gateway=DIFFERENT
  if cmp -s "$D/state.before" "$D/state.after"; then gateway=UNCHANGED; fi
fi
printf 'MATRIX_RANGE_GATEWAY_%s\n' "$gateway"
[[ $contracts == 0 && $locking == 0 && $gateway == UNCHANGED ]]
BASH
~~~

## Критерии отчёта

- **CONTRACTS** — число pass, fail, skip. Поимённо проверь починенный
  тест ALT9, сохранение поля в матрице и monitor, два отдельных
  подтверждения, повтор одной отметки, старую запись и незавершённый
  возврат. Сырые URL и заголовки не должны появляться в результате.
- **LOCKING** — у двух изменений временной политики одно принято,
  второе получают с `conflict`. Укажи итог, даже если архивы
  недоступны.
- **ARCHIVE_MAIN** — для прежнего запуска 18/18, совпадают 7 и 6
  HTTPS-успехов и пять профилей с двумя успехами. Для **ARCHIVE_EXTRA**
  ожидаются 4/4 и два профиля с двумя успехами. Для обоих старых
  архивов список `two_range_pass` пуст, `range_by_round` показывает
  отсутствие сохранённых подтверждений. Укажи сверку исходных файлов.
  При другом архиве опиши, с каким опытом он сопоставлен. При отсутствии
  архива укажи причину отдельно.
- **Шлюз** — код сверки снимков и категории отличий, если они есть.
  Выполнение новых живых проб через zapret2 остаётся отдельной фазой.

В GitHub отправь только версии, SHA, метки и агрегаты. Сырые
настройки, снимки, журналы, пути, ключи и адреса остаются на машине.

## Автоматическая публикация

Подставь абсолютный путь к обезличенному Markdown в `REPORT_SRC`.
Выполни из рабочей копии при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t09-range-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t09-matrix-range.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre CDN range evidence in strategy matrix'
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
