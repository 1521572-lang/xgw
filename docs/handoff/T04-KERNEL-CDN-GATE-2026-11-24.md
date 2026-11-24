# ThinkCentre · истечение разрешения CDN в ядре и возврат Selective

Целевая ОС — **Ubuntu 24.04 LTS**. Flash сама запускает готовые команды
и публикует один обезличенный отчёт. При недоступности терминала, sudo,
pytest или GitHub запроси доступ. Проведи остальные фазы даже при блокере.
Изменения исходного кода и тестов остаются за Codex.

[Последний отчёт](../reports/2026-11-24T191234Z_t04-cdn-expiry.md)
подтвердил 133 контракта, 27 сценариев перенаправления и 4 проверки с
локальным CONNECT/TLS. В этом этапе проверяется срок действия самого
разрешения на отправку в ядре. Контроллер хранит дедлайн между шагами
watchdog и при перечитывании конфигурации, вычисляет продление по
монотонным часам и планирует ближайший шаг к концу разрешения.

Основной тест загружает штатные правила в новое сетевое пространство
без WAN. Он измеряет обе записи из `zapret2_live` через nftables.
Воркер и применение правил Xray моделируются. Изменение времени
имитируется внутри тестового процесса. Пакет шлюза, служебные процессы
и часы машины используются как есть. WAN-запросы и захват трафика
в этой проверке отсутствуют.

## Запуск

Запусти блок из рабочей копии обычным пользователем. Для чтения
шлюза и netns сначала проверь `sudo -n true`, при необходимости
авторизуйся через `sudo -v`. Для обычных контрактов можно задать
абсолютный путь к существующему окружению в `XGW_TEST_PYTHON`.
Фаза KERNEL использует системный Python с pytest, подтверждённый в
прошлом отчёте. Если зависимость отсутствует, зафиксируй точное имя.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=1910d5c97e822ca7363451365da468ae3d694270
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-cdn-gate.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
nft --version || true
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
  tail -n 18 "$D/$label.log"
  printf '%s_EXIT %s\n' "$label" "$rc"
  return "$rc"
}
tests() {
  local tag=$1
  shift
  timeout -k 3 120 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no --tb=short --basetemp "$D/pytest-$tag" "$@"
}
kernel_trial() (
  local root
  root=$(sudo -n mktemp -d /var/tmp/xgw-t04-nft.XXXXXXXX) || exit $?
  [[ $root =~ ^/var/tmp/xgw-t04-nft\.[A-Za-z0-9]{8}$ ]] || exit 2
  trap 'sudo -n rm -rf -- "$root"' EXIT
  git -C "$REPO" archive "$CODE" src tests docs/helpers |
    sudo -n tar --no-same-owner -x -C "$root" || exit $?
  timeout -k 3 45 sudo -n unshare --net -- /usr/bin/env -i \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    "PYTHONPATH=$root/src:$root/tests:$root/docs/helpers" \
    "$PY" -B -P "$root/docs/helpers/cdn_gate_check.py"
)

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
contracts=0
run_phase CONTRACTS tests contracts -v --portable tests/test_zapret2.py \
  tests/test_zapret2_panel.py tests/test_selective_admission.py || contracts=$?
daemon=0
run_phase DAEMON tests daemon -v tests/test_daemon.py \
  -k 'signed_cdn or confirmed_fallback or zapret2_tick or watchdog_schedule or watchdog_shortens_pause' \
  || daemon=$?
transport=0
run_phase TRANSPORT tests transport -v -rs --durations=4 tests/test_zapret2_redirect.py \
  tests/test_zapret2_expiry_transport.py || transport=$?
if [[ $transport == 0 ]] && ! grep -Eq '^=+ 31 passed ' "$D/TRANSPORT.log"; then
  printf 'TRANSPORT_CASES_INCOMPLETE\n'
  transport=1
fi
kernel=0
run_phase KERNEL kernel_trial || kernel=$?
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
gateway=NOT_VERIFIED
if [[ $before == 0 && $after == 0 ]]; then
  gateway=DIFFERENT
  if cmp -s "$D/state.before" "$D/state.after"; then gateway=UNCHANGED; fi
fi
printf 'CDN_GATE_GATEWAY_%s\n' "$gateway"
[[ $contracts == 0 && $daemon == 0 && $transport == 0 && $kernel == 0 && $gateway == UNCHANGED ]]
BASH
~~~

## Критерии

| Фаза | Что записать |
| --- | --- |
| CONTRACTS | Число passed/failed/skipped. Поимённо отметь отзыв по исходному монотонному сроку, запрет повторного открытия после коррекции часов и открытие по новому сроку. |
| DAEMON | Штатное применение и снятие правила, сохранение срока после перечитывания, пробуждение к окончанию разрешения. Между закрытием разрешения и подтверждённым возвратом опубликован статус `unknown`. |
| TRANSPORT | 27 проверок редиректа и все четыре случая loopback, полный `206/65536` среди положительных контролей. |
| KERNEL | Приватный netns, две записи перед истечением, отсутствие продления при откате часов, исчезновение обеих записей без шага watchdog. Затем подтверждённый `fallback` в контроллере, открытие на свежей фикстуре и закрытие при выходе. Запиши все метки `OK` и `KERNEL_EXPIRED_AFTER_S` относительно расчётного конца разрешения. |
| Шлюз | Итог сверки снимков, при отличиях укажи категорию. Истечение в netns относится к правилам ядра и тестовому контроллеру. Живой маршрут YouTube и активная замена на рабочем шлюзе требуют отдельного допуска. |

Код завершения и отказавшую фазу запиши даже при блокере. Оставь сырые
данные на машине. В отчёт включи только версии, публичный SHA, счётчики,
имена проверок, категории изменений и обезличенное описание отказов.
[Статья Netfilter о сроках элементов](https://wiki.nftables.org/wiki-nftables/index.php/Element_timeouts)

## Автоматическая публикация

Подставь в `REPORT_SRC` абсолютный путь к обезличенному Markdown.
Из рабочей копии выполни блок при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-cdn-gate-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-cdn-kernel-gate.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre signed CDN kernel gate expiry'
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
