# ThinkCentre — задержка watchdog, FIB, TUN и версии ядер

**Ubuntu 24.04 LTS.** Flash сама запускает команды из терминала ThinkCentre
и публикует один обезличенный отчёт. При недоступности терминала, sudo или
GitHub запроси доступ. Код, сценарий и критерии подготовлены Codex.

Журнал закрепления и диагностика домашнего выхода установлены. Шлюз после
перезапуска исправен, Xray сохранил PID, панель переподключилась.
[Отчёт установки](../reports/2026-11-22T123006Z_pin-audit-install.md)

В опыте A3 число завершённых шагов и длительность шагов были известны,
а задержка от события до начала обработки оставалась неизмеренной.
Кандидат дополняет `watchdog-step.json` монотонными метками каждого
наблюдаемого набора причин. Автоповторы причины в одном наборе
сохраняют время первого события. Номер набора относится к поколению
цикла. Запись появляется при ближайшей штатной записи прогресса.
[Первичный аудит](../reports/2026-11-19_audit-recon.md)

## 1. Контракты и наблюдение

Из рабочей копии выполни `sudo -v`. Если pytest установлен в отдельном
окружении, экспортируй абсолютный `XGW_TEST_PYTHON`. На машине выполняются
16 контрактов из закреплённого архива и два 180-секундных окна наблюдения.
Действующий демон используется для чтения; кандидат проверяется в архиве.
В контрольном окне запускаются до 12 коротких HTTPS-запросов через
настроенный HTTP-вход Xray. Источники тестового трафика, FIB и журнал
остаются в локальной диагностике. Смена режима, закрепление сервера,
отключение TUN и перезапуск служб не требуются.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=c69ff9a75dbeec702f0490f8691144d247b0835d
PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
[[ $PY == /* && -x $PY ]]
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
sudo -n true
D=$(mktemp -d "$HOME/xgw-watchdog-fib.XXXXXXXX")
printf 'PINNED %s | %s | %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$PRETTY_NAME" "$(uname -r)" "$D"
git archive "$CODE" src/xgw pyproject.toml docs/helpers/audit_host_observe.py \
  tests/conftest.py tests/links.py tests/fakenet.py tests/fakexray.py tests/test_daemon.py \
  tests/test_panel.py tests/test_cores.py tests/test_net.py tests/test_audit_host_observe.py |
  tar -x -C "$D"
services() {
  systemctl show -p MainPID -p InvocationID xgw.service xgw-xray.service
}
services >"$D/service.before"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.before"
sudo -n timeout -k 2 15 /usr/local/bin/xgw cores status >"$D/cores.txt" ||
  printf 'CORES_STATUS_UNAVAILABLE\n'

contracts_rc=0
(
  cd "$D"
  timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    "PYTHONPATH=$D/src:$D/tests" "$PY" -B -P -m pytest -o addopts= \
    --rootdir "$D" -p no:cacheprovider -q --tb=short \
    tests/test_audit_host_observe.py \
    tests/test_daemon.py::test_watchdog_wake_progress_keeps_first_arrival_and_batch \
    tests/test_daemon.py::test_rules_event_restores_rules_right_away \
    tests/test_daemon.py::test_net_event_starts_the_step_early_but_not_too_often \
    tests/test_daemon.py::test_wake_after_resume_reloads_rules_and_scans \
    tests/test_daemon.py::test_watchdog_schedule_includes_step_work_in_interval \
    tests/test_net.py::test_iprule_ensure_removes_duplicates_and_ignores_foreign_rules \
    tests/test_net.py::test_tun_and_its_route_come_back_after_xray_starts_again \
    tests/test_net.py::test_loaded_notices_a_lost_interface_route_or_tproxy \
    tests/test_cores.py::test_update_keeps_the_previous_version_next_to_the_new_one \
    tests/test_cores.py::test_rollback_returns_the_previous_version_and_forgets_the_rejected_one \
    tests/test_cores.py::test_install_keeps_an_accepted_newer_core_but_not_an_older_one \
    tests/test_cores.py::test_diag_accepts_the_version_accepted_by_the_gateway
) | tee "$D/contracts.txt" || contracts_rc=$?
printf 'CONTRACTS_RC %s\n' "$contracts_rc"

audit() {
  local seconds=$1
  shift
  git show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 "$seconds" /usr/bin/python3 -I -B - "$@"
}
measure() {
  local label=$1
  audit 60 snapshot >"$D/$label-fib-before.json" || printf 'FIB_BEFORE_UNAVAILABLE %s\n' "$label"
  audit 190 watchdog --seconds 180 | tee "$D/$label-watchdog.json" ||
    printf 'WATCHDOG_UNAVAILABLE %s\n' "$label"
  audit 60 snapshot >"$D/$label-fib-after.json" || printf 'FIB_AFTER_UNAVAILABLE %s\n' "$label"
}

since=$(date --iso-8601=seconds)
measure baseline
port=$(sudo -n /usr/bin/python3 -I -B - <<'PYTHON'
import json
from pathlib import Path
rows = json.loads(Path("/etc/xgw/xray/config.json").read_bytes())["inbounds"]
port, = [row["port"] for row in rows if row.get("tag") == "http-in"
         and row.get("listen") == "127.0.0.1" and row.get("protocol") == "http"]
assert type(port) is int and 0 < port < 65536
print(port)
PYTHON
) || port=

if [[ -n $port ]]; then
  audit 60 snapshot >"$D/https-fib-before.json" || printf 'FIB_BEFORE_UNAVAILABLE https\n'
  (
      for ((i=1; i<=12; i++)); do
        code=$(curl -q -sS --max-time 5 --max-filesize 131072 --noproxy '' \
          --proxy "http://127.0.0.1:$port" -o /dev/null -w '%{http_code}' \
          https://example.org/ 2>>"$D/https-private.err") || code=error
        printf '%s\n' "$code"
        if (( i < 12 )); then sleep 10; fi
      done
  ) >"$D/https-codes.txt" &
  control=$!
  audit 190 watchdog --seconds 180 | tee "$D/https-watchdog.json" ||
    printf 'WATCHDOG_UNAVAILABLE https\n'
  wait "$control"
  audit 60 snapshot >"$D/https-fib-after.json" || printf 'FIB_AFTER_UNAVAILABLE https\n'
  awk '$0=="200" {n++} END {printf "HTTPS_CONTROL %d/%d\n", n, NR}' "$D/https-codes.txt"
else
  printf 'HTTPS_CONTROL_UNAVAILABLE\n'
fi
sudo -n timeout -k 2 15 journalctl -u xgw-xray.service -u xgw.service \
  --since "$since" --no-pager --grep='маршруты в него на месте|правила сети не загружены|Control process exited|шаг watchdog занял' \
  -n 200 -o short-monotonic >"$D/journal-private.txt" || printf 'JOURNAL_EMPTY_OR_UNAVAILABLE\n'
services >"$D/service.after"
if cmp -s "$D/service.before" "$D/service.after" &&
   sudo -n sha256sum --check --status "$D/settings.before"; then
  printf 'WATCHDOG_GATEWAY_UNCHANGED\n'
else
  printf 'WATCHDOG_GATEWAY_CHANGED_DURING_OBSERVATION\n'
fi
BASH
~~~

## 2. Что включить в отчёт

| Раздел | Критерий и результат |
|---|---|
| Контракты | Целевой итог — 16 успешно за один запуск. При ошибке приведи имя теста и обезличенный симптом. |
| A2, FIB | Для `proxy`, `bypass`, `proxy_extra` и `selected` сравни только классы устройств, типы и таблицы. Укажи совпадение границ в каждом окне. Ранние правила перечисляй по приоритету. FIB показывает выбор маршрута для заданных условий. |
| A3, watchdog | Для каждого окна приведи число завершённых шагов, максимум, p95, пропуски и максимальный возраст записи. Укажи число успешных HTTPS-запросов. Второе окно проверяет лёгкую контролируемую нагрузку. |
| A3, задержка реакции | При `wake.available=false` у установленного демона отсутствуют метки кандидата. При нуле наблюдаемых наборов и доступном формате результат `NOT_OBSERVED`. При положительном числе приведи количество и максимум по причинам. Замер охватывает ожидание начала обработки, с учётом объединения событий. |
| A6, TUN | Укажи число записей о восстановлении, ошибок и совпавших по времени пар. При отсутствии конкретного отказа и восстановления результат `NOT_OBSERVED`. Фикстуры покрывают восстановление маршрута и признак пропавшего интерфейса. |
| Версии | Из `cores.txt` укажи базовую версию Xray, установленную версию, признак принятого обновления и наличие версии для отката. Обновление и возврат проверяются на фикстурах. |

Дай коды фаз и маркер итоговой сверки. Файлы из `PRIVATE_ARTIFACTS`
не публикуй. В отчёте допустимы версии, счётчики, классы пути, краткие
критерии и обезличенные итоги. Сырые маршруты, IP, PID, токены
и полный журнал остаются на ThinkCentre.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`.
Выполни из рабочей копии при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-watchdog-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_watchdog-fib-baseline.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre watchdog, FIB and cores baseline'
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
