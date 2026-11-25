# ThinkCentre · один повтор прямого CDN-запроса после HTTP 302

**Ubuntu 24.04 LTS.** Flash сама выполняет готовые проверки и
публикует обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, pytest, панели или GitHub запроси доступ и
выполни доступные фазы.

ThinkCentre подтвердил восстановление blue/green и сохранение
действующего запроса legacy. Первый запуск тестов требовал каталога
`packaging`, после добавления прошла 71 проверка. Новый архив
содержит этот каталог. [Отчёт восстановления](../reports/2026-11-25T110618Z_t04-standalone-resume-flag.md)

Прямой CDN в одном живом опыте ответил HTTP 302, в следующем дал
TLS-таймаут. Сценарий выполняет один новый запрос к тому же URL и
IPv4 после подтверждённого прямого HTTP 302. Каждый запрос имеет
свои TCP-отсчёты, снимки NFQUEUE и подтверждение пути. Для допуска
пары по-прежнему требуется точный диапазон 65 536 байт на обоих
плечах. [Отчёт HTTP 302](../reports/2026-11-25T081338Z_t04-cdn-tcp-queue.md) ·
[Отчёт сопоставимой пары](../reports/2026-11-25T092146Z_t04-cdn-standalone-exit.md)

## Запуск

Из рабочей копии задай `XGW_TEST_PYTHON`, если pytest установлен
отдельно. Для живого сравнения задай `XGW_CDN_LIVE=1` в согласованное
окно Standalone с паузой VPN и прежним независимым возвратом. При
необходимости выполни `sudo -v`. Для сравнения используй
согласованный ролик. [Процедура возврата](STANDALONE-MANAGED-LIVE-2026-11-23.md)

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=9584f98d41c304bc2ba7206fe407fbc201e8996d
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t04-direct-retry.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers packaging vpn_ui pyproject.toml \
  | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=

contracts() (
  cd "$D/tree"
  timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
    -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short \
    --basetemp "$D/pytest" tests/test_standalone_cdn_compare.py \
    tests/test_cdn_queue_observation.py tests/test_cdn_tcp_observation.py \
    tests/test_singbox_generations.py tests/test_standalone_topology.py
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

## Итоги

- **CONTRACTS** — сводка из `CONTRACTS.log`. Отметь отказ
  при TLS-таймауте, другом IPv4 или URL, неподтверждённом
  маршруте и неполном диапазоне. Отдельные замеры первого
  запроса и повтора должны сохраниться при любом исходе повтора.
- **LIVE** — укажи итог `direct-verdict.out`, подтверждение
  пути и исход допуска `direct-retry-eligible`. При подтверждённом
  302 ожидается не более одного `direct-retry-cdn` на прежнем
  URL и IPv4, без перехода по `Location`. Укажи
  `direct-retry-verdict.out`, диапазон, TCP и дельты NFQUEUE
  повтора отдельно. При таймауте первого запроса или недоступном
  живом окне укажи `NOT_RUN` для повтора.
- **Пара и возврат** — укажи `pair-verdict.out`, какой прямой
  запрос вошёл в результат, диапазон VPN, штатное выключение и
  сверку после отката. При таймауте выключения используй
  `off-daemon.out`, `off-topology.out` и маркеры восстановления.

## Автоматическая публикация

Укажи абсолютный путь Markdown-отчёта в `REPORT_SRC`. Публикуй
версии, SHA, исходы и агрегаты. URL, отпечатки, адреса, снимки
и сырые журналы оставь на машине. Выполни блок из рабочей копии
при любом исходе.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t04-direct-retry-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-cdn-direct-retry.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre one direct CDN retry after HTTP 302'
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
