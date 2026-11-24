# ThinkCentre · смена CDN при активном Selective

**Ubuntu 24.04 LTS.** Flash сама запускает готовые проверки и публикует
один обезличенный отчёт. При недоступности терминала, sudo, pytest или
GitHub запроси соответствующий доступ и проведи остальные этапы.
Правки исходного кода и сценариев остаются за Codex.

[Предыдущий отчёт](../reports/2026-11-24T192639Z_t04-cdn-kernel-gate.md)
подтвердил истечение обеих записей nftables в отдельном netns.
Новый этап проверяет, что при замене CDN новые клиентские соединения
переходят на обычный маршрут до пробы новой ссылки. Старая привязка
в Xray возможна, например, после отказа API при уходе из предыдущего
цикла watchdog. Если снять её не удаётся, контроллер оставляет gate
закрытым и не начинает пробу.

В фазе XRAY временный экземпляр установленного Xray работает в чистом
netns с одним loopback. Он получает реальные команды Xray API и
записывает назначенные выходы для TCP CONNECT. Оба выхода — фикстуры
blackhole. Доступ к CDN, результат медиапробы и NFQUEUE моделируются.
Пакет, настройки, часы и процессы рабочего шлюза не изменяются.

## Запуск

Начни из рабочей копии обычным пользователем. Для снимков и netns
выполни `sudo -n true`. При необходимости авторизуйся в терминале
через `sudo -v`. Для обычных контрактов можно задать абсолютный путь к
существующему окружению `XGW_TEST_PYTHON`. Изолированный запуск
использует системный Python с pytest и установленный Xray из пакета.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=2ccdd2c498c75a93042cdaf3ff68186839906761
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-cdn-reload.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
/opt/xgw/xray/xray version | sed -n '1p' || true
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
  tail -n 20 "$D/$label.log"
  printf '%s_EXIT %s\n' "$label" "$rc"
  return "$rc"
}
tests() {
  local tag=$1
  shift
  timeout -k 3 120 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no --tb=short --basetemp "$D/pytest-$tag" "$@"
}
xray_trial() (
  local root
  root=$(sudo -n mktemp -d /var/tmp/xgw-cdn-xray.XXXXXXXX) || exit $?
  [[ $root =~ ^/var/tmp/xgw-cdn-xray\.[A-Za-z0-9]{8}$ ]] || exit 2
  trap 'sudo -n rm -rf -- "$root"' EXIT
  git -C "$REPO" archive "$CODE" src tests docs/helpers |
    sudo -n tar --no-same-owner -x -C "$root" || exit $?
  timeout -k 3 70 sudo -n unshare --net -- /usr/bin/env -i \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$root/src:$root/tests" \
    "$PY" -B -P "$root/docs/helpers/cdn_reload_xray_check.py"
)

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
contracts=0
run_phase CONTRACTS tests contracts -v --portable tests/test_zapret2.py \
  tests/test_zapret2_management.py tests/test_zapret2_panel.py || contracts=$?
watchdog=0
run_phase WATCHDOG tests watchdog -v tests/test_daemon.py \
  -k 'zapret2 or signed_cdn or selective_reload or watchdog_schedule or watchdog_shortens_pause' \
  || watchdog=$?
apply=0
run_phase APPLY tests apply -v tests/test_applier.py || apply=$?
xray=0
run_phase XRAY xray_trial || xray=$?
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
gateway=NOT_VERIFIED
if [[ $before == 0 && $after == 0 ]]; then
  gateway=DIFFERENT
  if cmp -s "$D/state.before" "$D/state.after"; then gateway=UNCHANGED; fi
fi
printf 'CDN_RELOAD_GATEWAY_%s\n' "$gateway"
[[ $contracts == 0 && $watchdog == 0 && $apply == 0 && $xray == 0 && $gateway == UNCHANGED ]]
BASH
~~~

## Критерии

| Фаза | Что записать |
| --- | --- |
| CONTRACTS | Счётчики passed, failed и skipped. Покажи три случая `test_cdn_change_with_unresolved_previous_route`, новый результат после замены служебного порта и CAS замены только CDN. При отказе снять старое правило открытий gate и проб быть не должно. |
| WATCHDOG | Поимённо отметь снятие клиентского правила до остановки воркера. Даже при отказе Xray API воркер должен закрыться, старый маршрут должен остаться неподтверждённым. |
| APPLY | Запиши счётчики, отдельно отметь откат состояния API при ошибке. |
| XRAY | Для двух смен ссылки нужны две метки `previous_client_rule_live`, две `client_uses_vpn_during_probe`, `accepted_new_probe`, `failed_new_probe_stays_on_vpn`, два контроля `other_route_stable` и `same_core_clean_api`. Источник выбора маршрута — журнал пробного Xray. |
| Шлюз | Итог сравнения снимков, при отличиях укажи категории без значений. |

Приведи SHA и версии Ubuntu, Xray и Python. Живой допуск YouTube и
замена URL на рабочем шлюзе остаются отдельным этапом. Для этого опыта
запиши `LIVE_ACTIVE_UPDATE=NOT_RUN`. Сырые логи, снимки и локальные
пути оставь на машине. Если фазу блокирует окружение, укажи точный
блокер и его влияние на остальные результаты.

## Автоматическая публикация

Подставь абсолютный путь к обезличенному отчёту в `REPORT_SRC` и
выполни блок из рабочей копии при любом исходе.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-cdn-reload-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-cdn-reload-xray.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Selective CDN handoff with isolated Xray'
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
