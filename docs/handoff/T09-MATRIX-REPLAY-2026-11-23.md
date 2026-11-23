# ThinkCentre — пересчёт сохранённых HTTPS-матриц, T07–T09

**Ubuntu 24.04 LTS.** Flash самостоятельно выполняет команды и
автоматически публикует один обезличенный отчёт при любом исходе.
При недоступности терминала, архивов, sudo или GitHub запроси доступ.

Приняты закреплённая проверка NFQUEUE и 4/4 сценария диагностики
на реальном journald. Следующий шаг по плану — разобрать накопленные
HTTPS-пробы и проверить, какая польза была бы от изменения их порядка.
[Отчёт о воркере](../reports/2026-11-23T000601Z_worker-fault-diagnostics.md)

## 1. Исходные файлы

Найди оригинальные сохранённые результаты на машине. Сопоставь задачу,
имя файла и дату с опубликованным отчётом. Укажи абсолютные пути
в переменных. Архивы можно оставить на месте.

| Переменная | Что искать |
|---|---|
| `XGW_T09_JOB` | `matrix-result.json` из раздела 5 полной матрицы 9×2 либо оригинальный сохранённый JSON этого задания |
| `XGW_T09_EXTRA_JOB` | Дополнительная сохранённая матрица, если доступна, например `direct-b-job.json`, `signed-job.json` или `persistent-job.json` |
| `XGW_T09_MONITOR` | Сохранённый журнал monitor того же задания, например `matrix.jsonl` или `matrix-full.jsonl` |
| `XGW_T09_LEDGER` | Пересчитанный `ledger.json` T09 по 12 сохранённым окнам плеера, если он доступен |

[ТЗ полной матрицы](COMBINED-ADMISSION-2026-11-19.md) · [Отчёт матрицы](../reports/2026-11-19_admission-matrix.md) · [ТЗ повторного импорта T09](T09-CDN-REPLAY.md)

Если файла нет, оставь переменную пустой и укажи недоступный источник.
Таблицы опубликованных отчётов служат для сверки результата. Для
пересчёта нужны сохранённые исходные JSON. Задание выполняет только
чтение сохранённых результатов и локальную сверку состояния шлюза.

## 2. Запуск

В терминале выполни `sudo -v`. Если pytest установлен в отдельном
окружении, экспортируй абсолютный `XGW_TEST_PYTHON`. Запусти блок
из рабочей копии XGW. Записывай вывод каждого этапа отдельно.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
printf 'MATRIX_REPLAY_HOST %s %s\n' "$PRETTY_NAME" "$(uname -r)"
BR=integration/zapret2-batch1
CODE=c25f34c655af69f67a5b1eda88bab465a707d226
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
sudo -n true
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t09-matrix-replay.XXXXXXXX")
printf 'MATRIX_REPLAY_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml |
  tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"

fib() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B - snapshot
}
fib >"$D/fib.before"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.before"

if timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    "$TEST_PY" -B -P -m pytest --portable -o addopts= -p no:cacheprovider \
    -q --tb=short tests/test_desync_jobs.py tests/test_desync_tournament.py \
    tests/test_desync_experiment.py >"$D/contracts.out" 2>&1 &&
    grep -Eq '^85 passed in ' "$D/contracts.out"; then
  grep -E '^85 passed in ' "$D/contracts.out"
  printf 'MATRIX_CONTRACTS_OK\n'
else
  printf 'MATRIX_CONTRACTS_FAILED\n'
fi

inputs=()
read_saved() {
  local label=$1 file=$2 rc=0
  shift 2
  if [[ $file != /* || ! -f $file || ! -r $file ]]; then
    printf 'MATRIX_SOURCE_UNAVAILABLE %s\n' "$label"
    return
  fi
  inputs+=("$file")
  sha256sum -- "$file" >>"$D/source.sha256"
  timeout -k 3 25 "$PY" -B -P -m "$@" "$file" \
    >"$D/$label.json" 2>"$D/$label.err" || rc=$?
  printf 'MATRIX_SOURCE_RESULT %s %s\n' "$label" "$rc"
  if [[ -s $D/$label.json ]]; then cat "$D/$label.json"; fi
}
read_saved main "${XGW_T09_JOB:-}" xgw.desync.client matrix --replay
read_saved extra "${XGW_T09_EXTRA_JOB:-}" xgw.desync.client matrix --replay
read_saved monitor "${XGW_T09_MONITOR:-}" xgw.desync.client analyze
read_saved playback "${XGW_T09_LEDGER:-}" xgw.desync.tournament report --ledger
if (( ${#inputs[@]} > 0 )); then
  if sha256sum --check --status "$D/source.sha256"; then
    printf 'MATRIX_SOURCES_UNCHANGED\n'
  else
    printf 'MATRIX_SOURCES_CHANGED\n'
  fi
fi

fib >"$D/fib.after"
if cmp -s "$D/fib.before" "$D/fib.after" &&
   sudo -n sha256sum --check --status "$D/settings.before"; then
  printf 'MATRIX_REPLAY_GATEWAY_UNCHANGED\n'
else
  printf 'MATRIX_REPLAY_GATEWAY_CHANGED\n'
fi
BASH
~~~

## 3. Критерии и отчёт

- Укажи `MATRIX_CONTRACTS_OK` и 85 проверок либо точную фазу
  отказа. Для исходных файлов приведи только статус доступа, штатную
  метку этапа и число строк. Для незаконченного задания анализ
  может выйти с кодом 2 и вернуть счётчики с
  `replay.state=two_complete_rounds_required`.
- Для каждой HTTPS-матрицы приведи `observed_rows`, `expected_rows`
  и разбивку исходов по кругам. Истечение CDN требует явной метки.
  HTTP-ошибка, отсутствие сведений, TLS, пауза или обрыв тела и
  ожидание контроллера учитываются отдельно. При наличии журнала
  того же задания укажи число клиентских ошибок локального API
  отдельно от HTTPS-результатов профилей.
- Для двух полных кругов сравни фактический порядок второго круга
  с порядком, построенным по первому. Для каждого укажи число
  попыток и сумму измеренных длительностей до первого HTTPS-успеха,
  число альтернативных успехов, которые пропустила бы остановка
  после первого, и байты тела с числом покрытых попыток. Сумма
  длительностей относится к самим попыткам. Полное время переходов
  и возврата в off в этой метрике отсутствует. Байты отражают
  наблюдаемую часть тел проб.
- Без сверки endpoint и маршрута этот пересчёт носит описательный
  характер. Укажи `endpoint_context=NOT_VERIFIED`. Для отдельного
  журнала плеера приведи `compared` или `mixed_context`, число
  пригодных записей и прежний результат отбора. Живое видео для
  этого прогона — `NOT_RUN`.
- Укажи Ubuntu, SHA кандидата, `MATRIX_SOURCES_UNCHANGED` при
  наличии источников и итог сверки шлюза. Публикуй агрегаты и имена
  профилей. Подписанные ссылки, адреса, идентификаторы, содержимое
  исходных JSON и локальные пути храни приватно.

## 4. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`.
Выполни блок из рабочей копии при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t09-matrix-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t09-matrix-replay.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre read-only HTTPS matrix replay'
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
