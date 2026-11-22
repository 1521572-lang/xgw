# ThinkCentre — порядок WAN-проб и время сквозной проверки, r5

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарии и автоматически
публикует один обезличенный отчёт. При недоступности терминала,
sudo или GitHub запроси доступ. Команды и проверки подготовлены Codex.

В r4 прошли 30 контрактов. Первый запуск откатился после HTTPS-таймаута,
повторная установка прошла. Плановая проба откладывалась в 4 шагах
за 180 с и 19 за 600 с. В исходном окне сканов почти не было,
поэтому эффект правки на общую длительность шага остаётся неизвестным.
Проверка WAN занимала до 21,14 с, сквозная — до 30,32 с, очередь
сканов — до 19,88 с. [Отчёт r4](../reports/2026-11-22T154911Z_watchdog-scan-budget.md)

R5 начинает WAN-проверку с последнего ответившего адреса. При отказе
проверяет остальные по конфигурации. Событие сети или возобновление после
сна возвращает исходный порядок. Пороги и таймауты остаются прежними.
Замеры отдельно показывают разрешение имени, TCP-подключение,
первую, дополнительную и резервную сквозные пробы. В выводе только
длительности и счётчики, адреса остаются на машине.

Порядок прогона — раздел 2 с `PHASE=before` на установленном r4,
затем установка из раздела 1, затем раздел 2 с `PHASE=after`.

## 1. Установка

Из терминала ThinkCentre выполни `sudo -v`. Если pytest в отдельном
окружении, экспортируй абсолютный `XGW_TEST_PYTHON`.
Выбери время, когда панель может кратко потерять связь при штатном
перезапуске `xgw.service`. На этот период исключи параллельные обновления
и ручные переключения.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=adf8e8b86867904324a9a62b6701e55e8ce8bb91
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_pin_audit_install.sh" |
  bash -s -- "$CODE" --watchdog-wan
BASH
~~~

Сценарий накладывает правку из `1fc8fa526f8353ade444f351f5509e9627059486`
поверх слоя `da6d12a` в копии установленного `daemon.py`.
Контракты покрывают рабочий и отказавший WAN, порядок повторных проб,
две попытки сквозной проверки и уже принятые проверки сканирования,
готовности процесса, расписания, ip rule и TUN.
Приёмка ждёт свежий завершённый шаг текущего процесса до 120 секунд.

| Маркер | Действие и критерий |
|---|---|
| WATCHDOG_WAN_BASELINE_MISMATCH | Укажи расхождение контекста. Исходный diff оставь на машине. |
| WATCHDOG_WAN_CONTRACTS_OK | Все 34 теста прошли на копии установленного пакета. При сбое установка останавливается. |
| WATCHDOG_WAN_HTTPS baseline 200 | Исходный HTTPS-контроль через Xray вернул 200. |
| WATCHDOG_WAN_ROLLBACK_ARMED | Независимый таймер активен на 15 минут перед заменой. |
| WATCHDOG_TIMING_PROGRESS_CHECK | Укажи `result`, `polls` и `waiting_first_step`. |
| WATCHDOG_WAN_PROGRESS_OK | Свежий `last_step` текущего процесса содержит `details_s`, `planned_scan_deferred` и `provider_attempts`. |
| WATCHDOG_WAN_DEPLOYED_AND_VERIFIED | XGW перезапущен, файл сверили, PID Xray и SHA настроек совпали. HTTPS в обеих проверках 200. Таймер снят. Оставь слой установленным. |
| WATCHDOG_WAN_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED | Байты и формат действующего процесса подтверждены. Замер исходного r4 укажи как `NOT_RUN`, если он не проводился. |

## 2. Сопоставимые окна до и после

Перед первым запуском выполни `sudo -v` и `export PHASE=before`.
После успешной установки выполни `sudo -v` и `export PHASE=after`.
Оба запуска используют одинаковые HTTPS-запросы в окне по 180 секунд.
В обеих фазах также снимаются 600 секунд обычной работы.
Если sudo истёк, возобнови авторизацию и зафиксируй повтор фазы отдельно.
Оба раза сохрани отдельный вывод. При откате запиши `after=NOT_RUN`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
CODE=adf8e8b86867904324a9a62b6701e55e8ce8bb91
[[ ${PHASE:-} == before || ${PHASE:-} == after ]]
cd "$(git rev-parse --show-toplevel)"
git fetch origin integration/zapret2-batch1
git merge-base --is-ancestor "$CODE" FETCH_HEAD
sudo -n true
D=$(mktemp -d "$HOME/xgw-wake-observe.XXXXXXXX")
printf 'OBSERVATION_PHASE %s\nPRIVATE_ARTIFACTS %s\n' "$PHASE" "$D"
audit() {
  local limit=$1
  shift
  git show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 "$limit" /usr/bin/python3 -I -B - "$@"
}
services() { systemctl show -p MainPID -p InvocationID xgw.service xgw-xray.service; }
services >"$D/units.before"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.before"
since=$(date --iso-8601=seconds)

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
  audit 60 snapshot >"$D/https-before.json" || printf 'FIB_HTTPS_BEFORE_UNAVAILABLE\n'
  (
    for ((i=1; i<=12; i++)); do
      rc=0
      timing=$(LC_ALL=C curl -q -sS --max-time 5 --max-filesize 131072 --noproxy '' \
        --proxy "http://127.0.0.1:$port" -o /dev/null \
        -w '%{http_code} %{http_connect} %{time_appconnect}' \
        https://example.org/ 2>>"$D/https-private.err") || rc=$?
      printf '%s %s\n' "$rc" "${timing:-000 000 0}"
      if (( i < 12 )); then sleep 10; fi
    done
  ) >"$D/https-codes.txt" &
  control=$!
  audit 190 watchdog --seconds 180 | tee "$D/https.json" || printf 'WATCHDOG_HTTPS_UNAVAILABLE\n'
  wait "$control"
  audit 60 snapshot >"$D/https-after.json" || printf 'FIB_HTTPS_AFTER_UNAVAILABLE\n'
  awk '$1=="0" && $2=="200" {n++; next}
       {print "HTTPS_ERROR curl_rc=" $1 " http=" $2 " connect=" $3 " tls_s=" $4}
       END {printf "HTTPS_CONTROL %d/%d\n", n, NR}' "$D/https-codes.txt"
else
  printf 'HTTPS_CONTROL_UNAVAILABLE\n'
fi
audit 60 snapshot >"$D/long-before.json" || printf 'FIB_LONG_BEFORE_UNAVAILABLE\n'
audit 610 watchdog --seconds 600 | tee "$D/long.json" || printf 'WATCHDOG_LONG_UNAVAILABLE\n'
audit 60 snapshot >"$D/long-after.json" || printf 'FIB_LONG_AFTER_UNAVAILABLE\n'
sudo -n timeout -k 2 15 journalctl -u xgw.service -u xgw-xray.service \
  --since "$since" --no-pager -n 200 -o short-monotonic \
  --grep='маршруты в него на месте|правила сети не загружены|Control process exited|шаг watchdog занял' \
  >"$D/journal-private.txt" || printf 'JOURNAL_EMPTY_OR_UNAVAILABLE\n'
services >"$D/units.after"
if cmp -s "$D/units.before" "$D/units.after" &&
   sudo -n sha256sum --check --status "$D/settings.before"; then
  printf 'WATCHDOG_OBSERVATION_GATEWAY_UNCHANGED\n'
else
  printf 'WATCHDOG_OBSERVATION_GATEWAY_CHANGED\n'
fi
BASH
~~~

В отчёте приведи `configured_intervals_s`, число завершённых
шагов, `unseen_steps_between_samples`, максимум, p95 и ошибки чтения.
При малой выборке пометь p95 как описательный. Приведи три
наибольших значения из `step_part_max_s`. Они описывают выборку
окна. Подсчёт охватывает завершения внутри текущего окна. Укажи
`step_details` для `provider_check`, `provider_resolve`,
`provider_connect`, `end_to_end`, `e2e_primary`,
`e2e_fallback`, `e2e_reserve` и `scan_queue`.
Для каждой операции приведи максимум и число шагов. При отсутствии
отдельного замера пропиши `NOT_OBSERVED`. Приведи `provider_attempts`
с числом шагов, суммой и максимумом. В исходном формате это поле
равно `null`. Сравни длительность WAN отдельно от полного шага
и укажи разницу в активности сканов и состоянии шлюза.
Для повторных таймаутов приведи curl_rc, HTTP, код CONNECT и время
до завершения TLS. Нулевое время TLS означает отсутствие отметки
о завершённом рукопожатии. Состояние VPN оценивай вместе с контролями FIB,
настроек и служб.
Укажи `wake.state` и количество наборов. `not_observed` означает,
что формат доступен, а причин в выборке нет. `not_instrumented`
означает старый формат. `unavailable` означает отсутствие читаемых
данных. Для `observed` укажи число, максимум задержки и
`last_step_overlap` по причине. Перекрытие показывает, сколько
ожидания совпало с интервалом последнего завершённого шага.
Поле `rules_check` измеряет отдельную проверку после начала разбора
набора. При отсутствии значений запиши доступную часть. По HTTPS
укажи числитель, знаменатель и пары кодов отказов. Из снимков FIB перенеси только классы путей,
типы, таблицы и факт совпадения на границах. Из журнала перенеси
счётчики сообщений, включая ноль. Приватные данные оставь на машине.

## 3. Откат

При `WATCHDOG_WAN_ROLLED_BACK` укажи итог восстановления и HTTPS.
При `WATCHDOG_WAN_ROLLBACK_PENDING` проверь
`xgw-watchdog-wan-rollback.timer` и `xgw-watchdog-wan-rollback.service`.
Дождись активного таймера. Если таймер и служба завершились,
а проверка восстановления не пройдена, используй значения из
текущего прогона и выполни:

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/install.py" \
  rollback --watchdog-wan --backup "$ROLLBACK_BACKUP"
~~~

## 4. Автоматическая публикация

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
PUB=$(mktemp -d "$HOME/xgw-watchdog-wake-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_watchdog-wan-check.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre WAN health check ordering'
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
