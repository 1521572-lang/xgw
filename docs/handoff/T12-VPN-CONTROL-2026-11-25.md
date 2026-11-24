# ThinkCentre · контроль обычного HTTPS через Xray и sing-box

**Ubuntu 24.04 LTS.** Flash сама запускает готовые проверки и публикует
один обезличенный отчёт в GitHub при любом исходе. При недоступности
терминала, sudo, Python с pytest или GitHub запроси доступ. Выполни
остальные доступные фазы. Код подготовлен Codex.

[Отчёт о сроке CDN](../reports/2026-11-24T212942Z_t12-monitor-cdn-expiry.md)
подтвердил 163 контракта и совместимость архива. Пассивное окно осталось
открытым, потому что шлюз был в off/off. Эта проверка закрывает отдельный
пункт плана об обычном HTTPS. Она подходит для текущего VPN при выключенном
Selective и пригодится для проверки нового сеанса после fallback.

## Команды на машине

Начни из рабочей копии. Используй существующий pytest или укажи его
интерпретатор через `XGW_TEST_PYTHON`. Для чтения применённого Xray
проверь `sudo -n true`, при необходимости авторизуйся через `sudo -v`.
Код берётся из закреплённого коммита и запускается из отдельного
каталога. Установка, смена сервера, изменение маршрутов и захват трафика
в этой проверке не нужны.

`PREVIEW` читает конфигурацию и локальные метрики. `LIVE` открывает до
трёх новых HTTPS-соединений к штатному `probe.trace_url`. На путь один
запрос с пределом 8 секунд. Чтение прекращается при первых 4096 байтах
тела с возможным превышением порога в последнем прочитанном блоке.
Изменение ревизии Xray,
перезапуск или сброс счётчиков делает сравнение непригодным. Средство
не устанавливает мост sing-box и не переключает сервер ради проверки.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=284364fd9580cffcba173dff511e36de36ae00f5
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-vpn.XXXXXXXX")
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

run_phase() {
  local label=$1 code=0
  shift
  "$@" >"$D/$label.log" 2>&1 || code=$?
  tail -n 16 "$D/$label.log"
  printf '%s_EXIT %s\n' "$label" "$code"
  return "$code"
}

vpn() {
  sudo -n timeout -k 3 55 /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    "PYTHONPATH=$D/tree/src" "$PY" -B -P -m xgw.desync.vpn_control "$@"
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short --portable \
  --basetemp "$D/pytest" tests/test_desync_vpn_control.py tests/test_desync_route_evidence.py \
  tests/test_desync_monitor_expiry.py tests/test_selective_admission.py || true
if run_phase PREVIEW vpn; then
  run_phase LIVE vpn --live || true
else
  printf 'LIVE_NOT_RUN_PREVIEW_UNAVAILABLE\n'
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

- **CONTRACTS** — количество `passed`, `failed` и `skipped`, время и
  короткая причина каждого сбоя. Проверь ограничения времени и объёма,
  подбор однозначного loopback-входа, обработку смены процесса Xray и
  отсутствие паролей, тегов и адресов в итогах.
- **PREVIEW** — доступные входы. Если в применённой конфигурации нет
  подходящего участника через мост sing-box, отметь путь как
  `UNAVAILABLE`. В этом случае результат проверки Xray относится к Xray.
- **LIVE** — для каждого доступного пути приведи HTTP-код, байты, время,
  наличие публичного выхода и его семейство. При отказе укажи этап и
  отдельный код CONNECT, если он есть. `https_with_exit` означает
  полный HTTP 200 и один пригодный `ip=`. `https_only` означает полный
  HTTP 200 без пригодного `ip=`. `failed` означает неполную проверку,
  включая остановку по пределу тела. Код процесса 0 означает получение
  отчёта, исходы запросов находятся в отдельных строках.
- **Атрибуция** — `http_in` проверяет штатный HTTP-вход, за которым может
  быть балансировщик или исключение маршрутизации. `xray` и `sing-box`
  используют явные правила для разных служебных входов по одному
  участнику подписки. Отметь отдельно факт прироста счётчиков именно
  этого выхода. Прирост включает фоновый трафик. Равенство IP с
  `http_in` означает совпадение выхода, по нему нельзя определить ядро
  штатного запроса. Один неудачный участник не характеризует все серверы.
- **Шлюз** — сравнение снимков, категории изменений при наличии и
  результат сравнения хэшей. Проверка касается обычного HTTPS. Живой
  диапазон CDN, воспроизведение через Selective, пассивное истечение и
  суточное наблюдение остаются самостоятельными фазами плана.

## Автоматическая публикация

Сырые снимки, адреса, теги, пути и настройки оставь на машине. В отчёте
публикуй версии, SHA, метки и агрегаты. Подставь абсолютный путь к
отчёту в `REPORT_SRC`, выполни из рабочей копии и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-vpn-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-vpn-control.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre fresh VPN sessions by applied core'
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
