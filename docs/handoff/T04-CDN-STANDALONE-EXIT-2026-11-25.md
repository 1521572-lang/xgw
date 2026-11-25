# ThinkCentre · результат прямого CDN и выключение Standalone

**Ubuntu 24.04 LTS.** Flash сама запускает готовые проверки и
публикует обезличенный отчёт при любом исходе. При недоступности
терминала, доступа к панели, sudo, pytest, архива или GitHub
запроси доступ и выполни доступные фазы.

В предыдущем проходе прямой CDN завершил TLS и ответил HTTP 302.
За 2,107 с NFQUEUE присвоила 9 идентификаторов. Оба счётчика
потерь дали ноль. Штатное выключение истекло по `off_deadline`.
Независимый откат восстановил файлы и рабочий VPN.
[Отчёт ThinkCentre](../reports/2026-11-25T081338Z_t04-cdn-tcp-queue.md)

Сценарий теперь сохраняет `direct-verdict.out` до выключения
Standalone. При отказе выключения он сохраняет статус службы,
резервирование очереди, причину из watchdog, признак применённого
Standalone и топологию sing-box. Затем срабатывает прежний откат.

## Запуск

Из обычной рабочей копии задай `XGW_TEST_PYTHON`, если pytest
установлен отдельно. Для пересчёта укажи абсолютный путь к каталогу
предыдущего живого опыта в `XGW_T04_CDN_ARCHIVE`. Живую фазу
запускай с `XGW_CDN_LIVE=1` в согласованное окно с паузой VPN.
При необходимости выполни `sudo -v`. Используй прежнюю процедуру
возврата и согласованный ролик.
[Процедура и независимый возврат](STANDALONE-MANAGED-LIVE-2026-11-23.md)

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=7b4ea228db1e18a2e38951f3fcb57750b2eaf615
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t04-cdn-exit.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=

run_phase() {
  local label=$1 code=0
  shift
  "$@" >"$D/$label.log" 2>&1 || code=$?
  printf '%s_EXIT %s\n' "$label" "$code"
  return "$code"
}

contracts() (
  cd "$D/tree"
  timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
    -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short \
    --basetemp "$D/pytest" tests/test_standalone_exit_evidence.py \
    tests/test_standalone_cdn_compare.py tests/test_cdn_queue_observation.py \
    tests/test_cdn_tcp_observation.py tests/test_selective_admission.py
)

archive() {
  local source=${XGW_T04_CDN_ARCHIVE:-}
  [[ $source == /* && -r $source/direct-cdn.out ]] || {
    printf 'ARCHIVE_NOT_AVAILABLE\n'; return 3;
  }
  timeout -k 2 20 "$PY" -B -P -m docs.helpers.standalone_cdn_compare evaluate-direct \
    "$source/direct-cdn.out" "$source/direct-route.out" \
    --queue-before "$source/direct-queue-before.out" --queue-after "$source/direct-queue-after.out"
}

live() (
  cd "$REPO"
  sudo -n true || exit
  git show "$CODE:docs/helpers/standalone_return_preflight.sh" |
    bash -s -- "$CODE" || exit
  git show "$CODE:docs/helpers/standalone_return_live.sh" |
    bash -s -- "$CODE" cdn-pair
)

contracts_rc=0
run_phase CONTRACTS contracts || contracts_rc=$?
run_phase ARCHIVE archive || true
if [[ $contracts_rc == 0 && ${XGW_CDN_LIVE:-0} == 1 ]]; then
  run_phase LIVE live || true
else
  printf 'T04_LIVE_NOT_RUN\n'
fi
BASH
~~~

## Итоги

- **CONTRACTS** — сводка из `CONTRACTS.log`. Укажи сохранение HTTP
  302 без VPN-плеча, различение `stop_failed` и `vpn_requested`,
  состояния резерва, устаревший статус и прежние проверки пары.
- **ARCHIVE** — возьми итог из `ARCHIVE.log`. Для прежнего опыта
  ожидаются HTTP 302 и `direct_range_verified=false`. Если
  `direct-route.out` отсутствует, укажи, что привязка маршрута
  остаётся неподтверждённой. При отсутствии архива укажи `NOT_RUN`.
- **LIVE** — укажи исход `direct-verdict.out` и результат
  выключения. При таймауте приведи обезличенные поля из
  `off-daemon.out` и `off-topology.out`, затем исход отката.
  При штатном выключении укажи полный `pair-verdict.out`.
  Совпадение пути, ответ 302 и точный диапазон имеют отдельные
  признаки.
- **Возврат** — укажи сверку файлов и настроек, маркер восстановления,
  итоговую топологию и новый VPN-сеанс. При обрыве используй
  `restore-location` из каталога живого прохода.

## Автоматическая публикация

Публикуй версии, SHA, исходы и агрегаты. Подписанный URL, его
отпечаток, адреса, исходные снимки и конфигурацию оставь на машине.
Укажи абсолютный путь отчёта в `REPORT_SRC`. Выполни блок из
рабочей копии при любом исходе.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t04-cdn-exit-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-cdn-standalone-exit.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre direct CDN and Standalone exit diagnostics'
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
