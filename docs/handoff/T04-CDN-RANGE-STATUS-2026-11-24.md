# ThinkCentre · признак подтверждённого диапазона CDN

**Ubuntu 24.04 LTS.** Flash сама запускает проверки и публикует
обезличенный отчёт при любом исходе. При недоступности терминала,
pytest, Node, Qt, чтения шлюза или GitHub запроси доступ. Остальные
этапы выполни независимо. Код и критерии подготовлены Codex.

[Последний отчёт](../reports/2026-11-24T204150Z_t04-exact-cdn-range.md)
подтвердил 180 контрактов, 72 HTTP-проверки и 12 случаев CONNECT/TLS.
Теперь положительный `range_verified` из контроллера виден в API
и карточках. Служебный `/generate_204` показывает доступность HTTPS.
Прежний снимок без поля сохраняет прежнее отображение. Статус
воспроизведения учитывается отдельно.

Помощник допуска принимает только явное подтверждение диапазона.
Для двух контрольных проб каждая должна начаться после завершения
предыдущей. Повторное чтение одной записи или обновление только
времени успеха второй пробой не считается. Снимок старой сборки без
поля `range_verified` по-прежнему показывает доступность HTTPS.
Помощник допуска в таком случае сообщает `range_evidence_unavailable`.

## Запуск на ThinkCentre

Выполни блок из рабочей копии обычным пользователем. Для тестов
можно задать абсолютный путь к существующему `XGW_TEST_PYTHON`.
Если Qt доступен в другом окружении, задай `XGW_QT_PYTHON`.
Для чтения снимков проверь `sudo -n true`, при необходимости
авторизуйся через `sudo -v`.

Тесты работают в архивной копии. Node исполняет проверку текста
в фикстуре DOM, Qt создаёт настоящий виджет в offscreen, локальный
TLS использует loopback. Рабочий шлюз используется для снимков.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=0b8328f354d3e6f85c80a267b75e61cf84ade20d
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
QT_PY=${XGW_QT_PYTHON:-$TEST_PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-cdn-range-status.XXXXXXXX")
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
  tail -n 24 "$D/$label.log"
  printf '%s_EXIT %s\n' "$label" "$rc"
  return "$rc"
}
tests() {
  local interpreter=$1 tag=$2
  shift 2
  timeout -k 3 120 "$interpreter" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -v -rs --tb=short --basetemp "$D/pytest-$tag" "$@"
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
contracts=0
run_phase CONTRACTS tests "$TEST_PY" contracts --portable tests/test_zapret2.py \
  tests/test_zapret2_panel.py tests/test_selective_admission.py \
  tests/test_desync_jobs.py || contracts=$?
transport=0
run_phase TLS tests "$TEST_PY" tls --durations=5 tests/test_zapret2_expiry_transport.py ||
  transport=$?
if [[ $transport == 0 ]] && ! grep -Eq '^=+ 12 passed ' "$D/TLS.log"; then
  transport=1
fi
node_rc=0
run_phase NODE timeout -k 2 30 node --test tests/test_zapret2_web_refresh.cjs || node_rc=$?
qt=0
QT_QPA_PLATFORM=offscreen run_phase QT tests "$QT_PY" qt tests/test_gui_qt.py \
  -k 'zapret2_qt_distinguishes or zapret2_queue_losses' || qt=$?
if [[ $qt == 0 ]] && ! grep -Eq '^=+ 2 passed,' "$D/QT.log"; then
  qt=1
fi
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
gateway=NOT_VERIFIED
if [[ $before == 0 && $after == 0 ]]; then
  gateway=DIFFERENT
  if cmp -s "$D/state.before" "$D/state.after"; then gateway=UNCHANGED; fi
fi
printf 'CDN_RANGE_STATUS_GATEWAY_%s\n' "$gateway"
[[ $contracts == 0 && $transport == 0 && $node_rc == 0 && $qt == 0 && $gateway == UNCHANGED ]]
BASH
~~~

## Критерии отчёта

| Фаза | Что указать |
| --- | --- |
| CONTRACTS | Число passed, failed и skipped. Отдельно укажи точную и старую запись без флага, другой HTTP-статус, смену ревизии, архивный снимок, повтор той же отметки и два настоящих результата. Укажи результат VPN после `302` и отсутствие URL и сырого заголовка в API. |
| TLS | Все 12 тестов. Из реального loopback точный диапазон записывает положительный признак, неполное тело и ошибочные заголовки дают отказ. |
| NODE | Счётчики. Метка «Точный диапазон» видна с истинным флагом. Для старой записи, отрицательного флага и служебного ответа этот текст отсутствует. |
| QT | Две проверки настоящего виджета. Для `/videoplayback` виден проверочный диапазон, для `/generate_204` — служебный адрес. Укажи версию Qt или конкретный блокер. |
| Шлюз | Сверка снимков. При отличии запиши только категорию и состояние этапа. |

В отчёт включи версии, SHA и обезличенные результаты. Сырые логи,
подписанные ссылки, сертификаты и значения снимков остаются
локально. Живой диапазон через zapret2 остаётся открытым, новый
поход на WAN в этом ТЗ не требуется.

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
PUB=$(mktemp -d "$HOME/xgw-cdn-range-status-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-cdn-range-status.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre explicit CDN range evidence in Selective'
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
