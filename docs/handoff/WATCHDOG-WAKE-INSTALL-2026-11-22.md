# ThinkCentre — плановые сканы при долгих шагах watchdog, r6

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарии и автоматически
публикует один обезличенный отчёт. При недоступности терминала,
sudo или GitHub запроси доступ. Команды и проверки подготовлены Codex.

R5 установлен с первого раза. Прошли 34 контракта, FIB совпал
во всех восьми снимках. Максимумы после установки достигли
10,02 с для суммы TCP-подключений WAN, 30,66 с для сквозной проверки
и 44,00 с для полного шага при интервале 20 с. Число шагов
в столбце измерений означает охват выборки. Частоту таймаутов
из максимума и этого числа определить нельзя.
[Отчёт r5](../reports/2026-11-22T164641Z_watchdog-wan-check.md)

R6 откладывает плановые проверки запасных, если к началу скана
до конца интервала осталось меньше пяти секунд. Если на следующем
подходящем шаге остаток такой же короткий, запускается одна проба.
Ручные и срочные проверки, проверки участников и сканы в аварийных
состояниях идут по действующему порядку. Сетевые таймауты прежние.

Порядок прогона — раздел 2 с `PHASE=before` на установленном r5,
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
CODE=220a657a787efb062c7867689a51611b6367d7b0
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_pin_audit_install.sh" |
  bash -s -- "$CODE" --watchdog-scan-slot
BASH
~~~

Сценарий накладывает правку из `aa2a3ab4fc6c46134c5949283b2b6e8b658f250c`
поверх слоя `1fc8fa5` в копии установленного `daemon.py`.
Пять новых контрактов покрывают перенос и продвижение очереди
при повторном дефиците времени, ручную и срочную пробы, проверку
участника и аварийный режим. В набор включены 34 контракта r5.
Приёмка ждёт свежий завершённый шаг текущего процесса до 120 секунд.

| Маркер | Действие и критерий |
|---|---|
| WATCHDOG_SCAN_SLOT_BASELINE_MISMATCH | Укажи расхождение контекста. Исходный diff оставь на машине. |
| WATCHDOG_SCAN_SLOT_CONTRACTS_OK | Все 39 тестов прошли на копии установленного пакета. При сбое установка останавливается. |
| WATCHDOG_SCAN_SLOT_HTTPS baseline 200 | Исходный HTTPS-контроль через Xray вернул 200. |
| WATCHDOG_SCAN_SLOT_ROLLBACK_ARMED | Независимый таймер активен на 15 минут перед заменой. |
| WATCHDOG_TIMING_PROGRESS_CHECK | Укажи `result`, `polls` и `waiting_first_step`. |
| WATCHDOG_SCAN_SLOT_PROGRESS_OK | Свежий `last_step` текущего процесса содержит прежние поля, `scan_deferred_for_step` и `queue_probe_count`. |
| WATCHDOG_SCAN_SLOT_DEPLOYED_AND_VERIFIED | XGW перезапущен, файл сверили, PID Xray и SHA настроек совпали. HTTPS в обеих проверках 200. Таймер снят. Оставь слой установленным. |
| WATCHDOG_SCAN_SLOT_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED | Байты и формат действующего процесса подтверждены. Замер исходного r5 укажи как `NOT_RUN`, если он не проводился. |

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
CODE=220a657a787efb062c7867689a51611b6367d7b0
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
Для каждой операции приведи число шагов, p50, p95 и максимум.
При отсутствии замера укажи `NOT_OBSERVED`. Для `provider_attempts`
приведи число шагов, сумму и максимум. Метрика `scan_deferred_for_step`
показывает перенос из-за остатка интервала. `queue_probes` показывает
число шагов с пробами и общее число запусков из очереди. Повтор по
другому хосту внутри одного запуска отдельно в этом счётчике не виден.
В исходном r5 оба поля отсутствуют, поэтому сопоставь время `scan_queue`
и количество наблюдений, отметив ограничение. Если переносов нет,
эффект переноса остаётся `NOT_OBSERVED`. Разницу p95 учитывай
вместе с загрузкой WAN, сквозными пробами и активностью очереди.
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

При `WATCHDOG_SCAN_SLOT_ROLLED_BACK` укажи итог восстановления и HTTPS.
При `WATCHDOG_SCAN_SLOT_ROLLBACK_PENDING` проверь
`xgw-watchdog-scan-slot-rollback.timer` и `xgw-watchdog-scan-slot-rollback.service`.
Дождись активного таймера. Если таймер и служба завершились,
а проверка восстановления не пройдена, используй значения из
текущего прогона и выполни:

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/install.py" \
  rollback --watchdog-scan-slot --backup "$ROLLBACK_BACKUP"
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
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_watchdog-scan-slot.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre scan scheduling under long watchdog steps'
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
