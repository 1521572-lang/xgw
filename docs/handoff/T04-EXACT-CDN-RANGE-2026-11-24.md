# ThinkCentre · полный диапазон видео для допуска Selective

**Ubuntu 24.04 LTS.** Flash сама запускает опубликованные команды и
публикует обезличенный отчёт при любом исходе. При недоступности
терминала, pytest, OpenSSL, Node, прав чтения или GitHub запроси
соответствующий доступ. Выполни доступные фазы независимо.
Код, тесты и критерии меняет Codex.

[Живой отчёт](../reports/2026-11-24T202842Z_t04-cdn-tcp.md) подтвердил
шесть ретрансляций исходящего сокета Xray при таймауте прямого TLS.
ACK полезных данных и входящие TCP-данные в покрытом окне отсутствовали.
Сопоставимый контроль VPN получил полный диапазон. Место потери
по этим данным не установлено.

Контроллер для `/videoplayback` теперь требует HTTP `206`,
единственный `Content-Range` с байтами 0–65535 и полное тело
65 536 Б. Прямая проба, VPN-контроль и его разрешённое перенаправление
используют тот же критерий. При неверном или коротком диапазоне
новые соединения возвращаются на обычный VPN, а контроль получает
тот же CDN-адрес. `/generate_204` сохраняет смысл отдельной
проверки доступности. Статус хранит код ошибки и счётчики.

## Запуск

Запусти из рабочей копии. При необходимости задай абсолютный путь
к существующему окружению с pytest в `XGW_TEST_PYTHON`. Для снимков
проверь `sudo -n true` и при необходимости авторизуйся через
`sudo -v`. Тесты выполняются в отдельной копии. Локальный стенд
использует настоящий CONNECT/TLS через loopback и моделирует
изменения Xray и nftables. Установка пакета и проба WAN вне этой фазы.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=ae97692987777d0f04071cd9b6879c39895e6fd1
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-exact-cdn-range.XXXXXXXX")
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
  local tag=$1
  shift
  timeout -k 3 120 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -v -rs --tb=short --basetemp "$D/pytest-$tag" "$@"
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
contracts=0
run_phase CONTRACTS tests contracts --portable tests/test_zapret2.py \
  tests/test_zapret2_panel.py tests/test_zapret2_management.py \
  tests/test_selective_admission.py || contracts=$?
http=0
run_phase HTTP tests http tests/test_checks.py tests/test_zapret2_redirect.py || http=$?
transport=0
run_phase TLS tests tls --durations=5 tests/test_zapret2_expiry_transport.py || transport=$?
if [[ $transport == 0 ]] && ! grep -Eq '^=+ 12 passed ' "$D/TLS.log"; then
  printf 'TLS_CASES_INCOMPLETE\n'
  transport=1
fi
ui=0
run_phase UI timeout -k 2 12 node --check src/xgw/ui/zapret2.js || ui=$?
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
gateway=NOT_VERIFIED
if [[ $before == 0 && $after == 0 ]]; then
  gateway=DIFFERENT
  if cmp -s "$D/state.before" "$D/state.after"; then gateway=UNCHANGED; fi
fi
printf 'EXACT_CDN_RANGE_GATEWAY_%s\n' "$gateway"
[[ $contracts == 0 && $http == 0 && $transport == 0 && $ui == 0 && $gateway == UNCHANGED ]]
BASH
~~~

## Критерии

| Фаза | Что записать |
| --- | --- |
| CONTRACTS | Счётчики passed, failed, skipped. Поимённо проверь снятие прямого пути, одну VPN-пробу того же CDN после снятия, сохранение бюджета и перевод статуса в fallback. Вариант `/generate_204` и общие HTTP-пробы должны сохранить прежнее поведение. |
| HTTP | Счётчики. Проверь полный chunked-ответ, отсутствие завершающего фрейма, лишние байты и контракты перенаправления VPN. |
| TLS | Все 12 случаев. Укажи исходы `http_200`, `missing`, `shifted`, `invalid_total`, `duplicate`, `partial` и `exact` поимённо. Через VPN нужен положительный диапазон после `302` и отказ при отсутствии заголовка у цели. Срок CDN и TLS-таймауты проверяются прежними случаями. |
| UI | Код Node и результат контрактов карточки. В ней для неполного диапазона есть отдельная причина без URL. |
| Шлюз | Итог сравнения снимков. При отличиях укажи только категории. |

Укажи Ubuntu, SHA, итог по фазам и первый конкретный блокер при
ошибке. Рабочий диапазон на живом прямом CDN остаётся открытым.
Публикуй только метки, версии и численные агрегаты. Сырые журналы,
снимки, адреса, ключи и временный сертификат остаются на машине.

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
PUB=$(mktemp -d "$HOME/xgw-exact-cdn-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-exact-cdn-range.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre exact CDN range admission'
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
