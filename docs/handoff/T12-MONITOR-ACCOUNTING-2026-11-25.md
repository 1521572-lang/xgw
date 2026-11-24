# ThinkCentre · учёт проб и бюджета в журнале T12

**Ubuntu 24.04 LTS.** Flash сама запускает команды и публикует один
обезличенный отчёт в GitHub при любом исходе. Если недоступны терминал,
архив, учётная запись панели или GitHub, запроси соответствующий доступ.
Остальные фазы выполни независимо. Правки кода остаются у Codex.

[Приёмка матрицы T09](../reports/2026-11-24T210643Z_t09-matrix-range.md)
закрыла 165 контрактов, проверку блокировки записи и два офлайн-пересчёта.
В основном архиве сохранились 7 и 6 HTTPS-успехов. В обоих архивах
сведений о полных диапазонах нет. Текущий проход проверяет измерительный
инструмент T12 перед суточным наблюдением.

## Команды проверки

Запусти из рабочей копии от пользователя рабочего стола. Для контрактов
можно указать абсолютный путь к существующему Python с pytest через
`XGW_TEST_PYTHON`. Для фазы `ARCHIVE` укажи путь `XGW_T12_DAY_LOG` к
исходному `day.jsonl` из [прохода на 18,51 ч](../reports/2026-11-19_admission-matrix.md).
При необходимости найди кандидатов командой
`find "$HOME" -maxdepth 4 -type f -name day.jsonl -print` и сверь
продолжительность и метки с отчётом. Для `SAMPLE` нужна действующая
локальная сессия панели того же пользователя.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=71789b76e5db76603fa8a95e9dc9797a161225bc
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-monitor.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"

snapshot() {
  sudo -n timeout -k 3 60 "$PY" -I -B - snapshot <docs/helpers/audit_host_observe.py &&
    sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}

cli() {
  "$PY" -B -P -m xgw.desync.client "$@"
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?

contracts=0
timeout -k 3 120 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
  --color=no -v -rs --tb=short --portable --basetemp "$D/pytest" \
  tests/test_desync_monitor_budget.py tests/test_desync_jobs.py \
  >"$D/contracts.log" 2>&1 || contracts=$?
tail -n 12 "$D/contracts.log"
printf 'CONTRACTS_EXIT %s\n' "$contracts"

archive=${XGW_T12_DAY_LOG:-}
if [[ $archive == /* && -f $archive && -r $archive ]]; then
  replay=0
  sha256sum -- "$archive" >"$D/archive.sha256"
  cli analyze "$archive" >"$D/archive-summary.json" || replay=$?
  if sha256sum --check --status "$D/archive.sha256"; then
    printf 'ARCHIVE_UNCHANGED\n'
  else
    printf 'ARCHIVE_HASH_MISMATCH\n'
  fi
  printf 'ARCHIVE_EXIT %s\n' "$replay"
else
  printf 'ARCHIVE_NOT_AVAILABLE\n'
fi

sample=0
timeout -k 3 90 "$PY" -B -P -m xgw.desync.client monitor \
  --output "$D/sample.jsonl" --seconds 60 --interval 15 >"$D/sample.log" || sample=$?
printf 'SAMPLE_EXIT %s\n' "$sample"
if [[ $sample == 0 ]]; then
  stat -c '%a %s' "$D/sample.jsonl"
  replay=0
  cli analyze "$D/sample.jsonl" >"$D/sample-summary.json" || replay=$?
  printf 'SAMPLE_ANALYZE_EXIT %s\n' "$replay"
fi

after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
  if cmp -s "$D/state.before" "$D/state.after"; then
    printf 'T12_GATEWAY_UNCHANGED\n'
  else
    printf 'T12_GATEWAY_SNAPSHOT_DIFF\n'
  fi
else
  printf 'T12_GATEWAY_SNAPSHOT_NOT_AVAILABLE %s %s\n' "$before" "$after"
fi
BASH
~~~

## Что фиксировать

- **CONTRACTS** — количество `passed`, `failed`, `skipped` и время.
  Убедись, что покрыты повторные снимки одной пробы, частичная запись
  VPN-повтора, старый формат, смена ревизии, изменение лимита, откат
  счётчика, обратный ход часов и граница UTC. При сбое приложи имя случая
  и краткую обезличенную причину.
- **ARCHIVE** — сверка исходного файла, длительность, число отсчётов,
  интервалы состояний, ошибки API и прежняя пара UTC. Для архива на
  18,51 ч ожидается одна пара UTC. Старые данные без времён проб
  дают пустые группы `observed_probe_attempts`. Это отсутствие сведений
  о числе попыток. Отдельно укажи `budget.confirmed_utc_rollovers`,
  доверенные и недоступные отсчёты и причину расхождения с прежним
  счётчиком пар, если оно есть. Не восстанавливай траты из временных меток.
- **SAMPLE** — исходные байты и режим файла `600`, число отсчётов и
  ошибок API, границы журнала, причины и длительность видимого fallback,
  итоги `observed_probe_attempts` и `budget` при наличии данных. При
  выключенном контроллере новый сеанс наблюдения может видеть пустые
  группы попыток. Не меняй режим ради заполнения групп. Страница и CDN,
  прямой путь и VPN, первые пробы и повторы указываются раздельно.
  Если все отсчёты с `api_unavailable`, отметь `SAMPLE_UNAVAILABLE`
  и проверь доступ к локальной сессии. Итог считает видимые попытки.
  Отсчёт может содержать сохранённую попытку до начала короткой записи.
- **Бюджет** — `comparable_intervals` служит знаменателем для
  `charged_intervals`, `observed_charge_bytes` суммирует видимые
  приращения счётчика резервирования. Приведи также максимум списания,
  минимум остатка и число снимков сверх текущего лимита по суткам.
  Подтверждённая смена учётного дня сама по себе не свидетельствует о
  списании после полуночи. Фактический сетевой объём, качество видео и
  ручное вмешательство проверяются отдельными измерениями.
- **Шлюз** — итог сравнения и категории расхождений. При недоступном
  `sudo -n` запроси доступ и продолжи остальные фазы. Эта проверка
  читает localhost и сохранённые файлы. Новые WAN-пробы, суточный запуск,
  установка и переключение режима в этом задании не требуются.

## Автоматическая публикация

В отчёт включи только версии, SHA кандидата, итоги фаз и агрегаты.
Оставь настройки, сырые журналы, снимки и пути к ним на машине.
Подставь абсолютный путь к обезличенному файлу в `REPORT_SRC`.
Выполни из рабочей копии и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-monitor-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-monitor-accounting.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre monitor accounting and fallback evidence'
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
