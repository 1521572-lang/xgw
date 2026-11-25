# ThinkCentre · совместный замер TCP и NFQUEUE в паре CDN

**Ubuntu 24.04 LTS.** Flash сама запускает готовые проверки и
публикует обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, панели, согласованного окна или GitHub запроси
доступ и выполни доступные фазы.

На ThinkCentre прошли 95 контрактов. На loopback первый ACK
наблюдался через 569–576 мс, приём задержанного ответа через
1907 мс. Максимум между чтениями составил 423–530 мс.
В следующей сопоставимой паре к временам TCP добавляются дельты
общей очереди NFQUEUE до и после того же прямого запроса.
[Отчёт TCP](../reports/2026-11-25T063139Z_t04-cdn-tcp-timing.md)

Сводка принимает снимки при подтверждённом прямом пути к тому же
IPv4, совпавшей политике, том же слушателе и монотонных счётчиках.
Границы проверяются по монотонным часам хоста. От чтения до запроса
и от конца запроса до второго чтения допускается по четыре секунды.
Счётчики охватывают всю очередь за этот интервал. Атрибуцию сокета
показывают отдельные данные TCP и журнал Xray.

## Запуск

Из обычной рабочей копии укажи `XGW_TEST_PYTHON`, если pytest
установлен отдельно. Для живой фазы используй согласованное короткое
окно Standalone с временной паузой VPN и действующим обратным таймером
по прежней процедуре. Укажи `XGW_CDN_LIVE=1` в этом окне. При необходимости
выполни `sudo -v`. Используй согласованный ролик в `XGW_T09_VIDEO`.
Настройки и хэши проходят проверку после восстановления.
[Процедура и независимый возврат](STANDALONE-MANAGED-LIVE-2026-11-23.md)

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=dbb03fbb35da335903989885e5f43d5f2cdba2cd
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t04-cdn-queue.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
ss -V
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=

contracts() (
  cd "$D/tree"
  timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
    -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short \
    --basetemp "$D/pytest" tests/test_cdn_queue_observation.py \
    tests/test_cdn_tcp_observation.py tests/test_standalone_cdn_compare.py \
    tests/test_selective_probe_watch.py tests/test_desync_route_evidence.py
)

live() (
  cd "$REPO"
  sudo -n true || exit
  git show "$CODE:docs/helpers/standalone_return_preflight.sh" |
    bash -s -- "$CODE" || exit
  git show "$CODE:docs/helpers/standalone_return_live.sh" |
    bash -s -- "$CODE" cdn-pair
)

contracts_rc=0
contracts >"$D/CONTRACTS.log" 2>&1 || contracts_rc=$?
tail -n 8 "$D/CONTRACTS.log"
printf 'CONTRACTS_EXIT %s\n' "$contracts_rc"
if [[ $contracts_rc == 0 && ${XGW_CDN_LIVE:-0} == 1 ]]; then
  live_rc=0
  live >"$D/LIVE.log" 2>&1 || live_rc=$?
  printf 'LIVE_EXIT %s\n' "$live_rc"
else
  printf 'T04_LIVE_NOT_RUN\n'
fi
BASH
~~~

## Отчёт

- **CONTRACTS** — числа из `CONTRACTS.log`. Отметь контроль
  подтверждённого маршрута, смену слушателя, сброс счётчиков,
  границы запроса и прежнюю схему отчёта без замера очереди.
- **LIVE** — из `LIVE.log` возьми метки предпроверки и возврата.
  Из каталога `PRIVATE_ARTIFACTS` живого прохода возьми
  итоговый `pair-verdict.out`. Для обоих плеч укажи исход
  диапазона, маршрут и совпадение фактического IPv4. Для прямого
  плеча приведи TCP-времена, число отсчётов, счётчики и
  `direct_queue`. При `observed` укажи длительность, дельты,
  число назначенных ID и долю. При недоступной сводке запиши
  причину и коды шагов `direct-queue-before` и
  `direct-queue-after`. При отсутствии окна укажи `NOT_RUN`.
- **Возврат** — при запуске живой фазы укажи маркер managed,
  результат нового VPN-сеанса, сверку конфигурации и итоговый код.
  Если выполнение оборвётся, используй сохранённый
  `restore-location` по процедуре независимого возврата.

## Автоматическая публикация

Публикуй версии, SHA, исходы и агрегаты. Подписанный URL, его
отпечаток, адреса, исходные снимки и идентификаторы сокетов
оставь на машине. Укажи абсолютный путь отчёта в `REPORT_SRC`
и выполни блок из рабочей копии при любом исходе.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t04-cdn-queue-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-cdn-tcp-queue.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre paired CDN TCP and NFQUEUE evidence'
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
