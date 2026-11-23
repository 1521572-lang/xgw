# ThinkCentre — длительности фаз HTTPS-задания T07–T09

**Ubuntu 24.04 LTS.** Flash сама запускает все проверки. При недоступности
терминала, sudo, исходных файлов или GitHub запроси доступ и продолжи
доступные части. Тесты используют отдельный каталог и фикстуры.
Архивный анализ читает сохранённые результаты. Живые сетевые пробы,
установка файлов, переключение режима и воспроизведение видео здесь
`NOT_RUN`. В конце автоматически опубликуй один обезличенный отчёт.

[Предыдущий отчёт](../reports/2026-11-23T001918Z_t09-matrix-replay.md) · [Где искать исходники](T09-MATRIX-REPLAY-2026-11-23.md#1-исходные-файлы)

## 1. Исходники и подготовка

Экспортируй абсолютный `XGW_T09_JOB` для того же `matrix-result.json` (18
строк) и, если доступен, `XGW_T09_EXTRA_JOB` для того же `direct-b-job.json`
(4 строки). Сопоставь исходники с предыдущим отчётом. При недоступном
архиве оставь переменную пустой. Из рабочей копии XGW выполни `sudo -v`,
затем блок ниже. Для pytest из venv экспортируй его абсолютный
`XGW_TEST_PYTHON`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
printf 'MATRIX_TIMING_HOST %s %s\n' "$PRETTY_NAME" "$(uname -r)"
BR=integration/zapret2-batch1
CODE=bfe75ded6b031e87dadfb068e09db32e92788f7c
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t09-timing.XXXXXXXX")
printf 'MATRIX_TIMING_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml |
  tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=

snapshot() {
  sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B "$D/tree/docs/helpers/audit_host_observe.py" \
    snapshot >"$D/host.$1.json" &&
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.$1"
}
if snapshot before; then
  host_before=1
else
  host_before=0
  printf 'MATRIX_TIMING_HOST_AUDIT_UNAVAILABLE\n'
fi

run_tests() {
  local label=$1 rc=0
  shift
  timeout -k 3 180 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    -q --tb=short "$@" >"$D/$label.out" 2>&1 || rc=$?
  printf 'MATRIX_TIMING_TEST %s %s\n' "$label" "$rc"
  tail -n 3 "$D/$label.out"
}
run_tests contracts --portable tests/test_desync_jobs.py tests/test_desync_tournament.py \
  tests/test_desync_experiment.py
run_tests linux_contention tests/test_zapret2_management_linux.py

read_matrix() {
  local label=$1 file=$2 rc=0
  if [[ $file != /* || ! -f $file || ! -r $file ]]; then
    printf 'MATRIX_TIMING_SOURCE_UNAVAILABLE %s\n' "$label"
    return
  fi
  if ! sha256sum -- "$file" >"$D/$label.sha256"; then
    printf 'MATRIX_TIMING_SOURCE_UNAVAILABLE %s\n' "$label"
    return
  fi
  timeout -k 3 25 "$PY" -B -P -m xgw.desync.client matrix --replay "$file" \
    >"$D/$label.json" 2>"$D/$label.err" || rc=$?
  printf 'MATRIX_TIMING_SOURCE_RESULT %s %s\n' "$label" "$rc"
  if sha256sum --check --status "$D/$label.sha256"; then
    printf 'MATRIX_TIMING_SOURCE_UNCHANGED %s\n' "$label"
  else
    printf 'MATRIX_TIMING_SOURCE_CHANGED %s\n' "$label"
  fi
  if [[ -s $D/$label.json ]]; then cat "$D/$label.json"; fi
}
read_matrix main "${XGW_T09_JOB:-}"
read_matrix extra "${XGW_T09_EXTRA_JOB:-}"

if (( host_before )) && snapshot after; then
  if cmp -s "$D/host.before.json" "$D/host.after.json" &&
     cmp -s "$D/settings.before" "$D/settings.after"; then
    printf 'MATRIX_TIMING_GATEWAY_UNCHANGED\n'
  else
    printf 'MATRIX_TIMING_GATEWAY_CHANGED\n'
  fi
else
  printf 'MATRIX_TIMING_GATEWAY_NOT_VERIFIED\n'
fi
BASH
~~~

## 2. Критерии

- `contracts` — 86 тестов. `linux_contention` — один тест: два процесса
  одновременно меняют ревизию временной политики, одна запись принята,
  вторая получает `conflict`. В контракте часов первая попытка занимает
  95 250 мс, из них 250 мс на применение, 95 000 мс на ожидание; возврат
  в `off` — ещё 1 750 мс. Контракт неудачного возврата сохраняет
  две измеренные фазы и не записывает `off_confirm`.
- Основной архив — 18/18 строк, HTTPS-успехи **7 и 6** по кругам,
  `two_https_pass` — пять профилей (`multidisorder`, `fake_md5_split`,
  `fake_seq`, `fake_md5`, `fake_static_md5`). Сравни оба порядка по
  `first_pass_attempt` и `first_pass_ms`. Ожидаются 2 против 1 и
  примерно 181,0 против 90,5 с. У каждого порядка пять непройденных
  при ранней остановке успехов из шести во втором круге.
- Дополнительный архив, если найден, — 4/4 строки, по два HTTPS-успеха
  в каждом круге, оба профиля в `two_https_pass`.
- Для каждого круга укажи число замеров и сумму `total_ms` отдельно
  для `attempt`, `policy_apply`, `outcome_wait`, `off_confirm`,
  `page_probe` и `cdn_probe`. Новые фазы в прежних архивах отсутствуют,
  ожидаются `samples=0` и `total_ms=null`. Значение 0 мс при наличии
  замера допустимо. При неполном покрытии укажи знаменатель. Время
  `attempt` уже включает `policy_apply` и `outcome_wait`. Внутренние
  HTTPS-пробы входят в ожидание; эти длительности не складываются.
  `outcome_wait` включает работу контроллера и задержку появления
  статуса. Доля запуска воркера требует отдельного сопоставления
  событий его поколения. Последний возврат исходной политики в эти
  измерения не входит.
- Зафиксируй SHA кандидата, исходы тестов, сверку источников и
  FIB/PID/конфигов. При расхождении приведи фазу и наблюдаемое
  значение. В отчёт включай агрегаты. URL, идентификаторы,
  хэши настроек, вывод с локальными путями и исходные записи
  оставь в приватных каталогах.

## 3. Публикация при любом результате

Задай абсолютный путь к обезличенному отчёту в `REPORT_SRC` и сама
выполни блок из рабочей копии XGW. Верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t09-timing-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t09-matrix-timing.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre HTTPS matrix timing and legacy archive coverage'
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
