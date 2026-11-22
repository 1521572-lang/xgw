# ThinkCentre — бюджет плановых сканов и время операций watchdog, r4

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарии и автоматически
публикует один обезличенный отчёт. При недоступности терминала,
sudo или GitHub запроси доступ. Команды и проверки подготовлены Codex.

Установка r3 принята, 22 проверки прошли. За 600 с завершились 34 шага,
максимум 37,08 с при интервале 20 с. «Сканы и замены» занимали до 27,53 с,
«сигналы ядра» — до 14,86 с. FIB совпал на границах, HTTPS дал 9/12.
Остальные три запроса истекли по клиентскому таймауту. В обоих окнах
записи `wake` за текущий интервал не наблюдались.
[Отчёт r3](../reports/2026-11-22T145235Z_watchdog-step-attribution-r3.md)

R4 оставляет минимум пять секунд в бюджете очереди после паузы
перед дополнительной плановой пробой запасного. При меньшем остатке
запись остаётся в очереди. Первая проба сохраняет прежний порядок.
Новые метки отдельно показывают сквозную проверку, проверку провайдера,
метрики, очередь сканов, замену и другие операции.

Порядок прогона: раздел 2 с `PHASE=before` на установленном r3,
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
CODE=201c3d0d873ae8e6ea8df6042d0de856545f9d46
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_pin_audit_install.sh" |
  bash -s -- "$CODE" --watchdog-scan
BASH
~~~

Сценарий накладывает правку из `da6d12a21d0fb2fbdc7c4048737b02ecf9835629`
поверх слоя `6de2c66` в копии установленного `daemon.py`.
Контракты покрывают готовность процесса, расписание, сканы, ip rule и TUN.
Приёмка ждёт свежий завершённый шаг текущего процесса до 120 секунд.

| Маркер | Действие и критерий |
|---|---|
| WATCHDOG_SCAN_BASELINE_MISMATCH | Укажи расхождение контекста. Исходный diff оставь на машине. |
| WATCHDOG_SCAN_CONTRACTS_OK | Все 30 тестов прошли на копии установленного пакета. При сбое установка останавливается. |
| WATCHDOG_SCAN_HTTPS baseline 200 | Исходный HTTPS-контроль через Xray вернул 200. |
| WATCHDOG_SCAN_ROLLBACK_ARMED | Независимый таймер активен на 15 минут перед заменой. |
| WATCHDOG_TIMING_PROGRESS_CHECK | Укажи `result`, `polls` и `waiting_first_step`. |
| WATCHDOG_SCAN_PROGRESS_OK | Свежий `last_step` текущего процесса содержит `details_s` и `planned_scan_deferred`. |
| WATCHDOG_SCAN_DEPLOYED_AND_VERIFIED | XGW перезапущен, файл сверили, PID Xray и SHA настроек совпали. HTTPS в обеих проверках 200. Таймер снят. Оставь слой установленным. |
| WATCHDOG_SCAN_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED | Байты и формат действующего процесса подтверждены. |

## 2. Сопоставимые окна до и после

Перед первым запуском выполни `sudo -v` и `export PHASE=before`.
После успешной установки выполни `sudo -v` и `export PHASE=after`.
Оба запуска используют одинаковые HTTPS-запросы в окне по 180 секунд.
После установки дополнительно снимаются 600 секунд обычной работы.
Оба раза сохрани отдельный вывод. При откате запиши `after=NOT_RUN`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
CODE=201c3d0d873ae8e6ea8df6042d0de856545f9d46
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
      code=$(curl -q -sS --max-time 5 --max-filesize 131072 --noproxy '' \
        --proxy "http://127.0.0.1:$port" -o /dev/null -w '%{http_code}' \
        https://example.org/ 2>>"$D/https-private.err") || rc=$?
      printf '%s %s\n' "$rc" "${code:-000}"
      if (( i < 12 )); then sleep 10; fi
    done
  ) >"$D/https-codes.txt" &
  control=$!
  audit 190 watchdog --seconds 180 | tee "$D/https.json" || printf 'WATCHDOG_HTTPS_UNAVAILABLE\n'
  wait "$control"
  audit 60 snapshot >"$D/https-after.json" || printf 'FIB_HTTPS_AFTER_UNAVAILABLE\n'
  awk '$1=="0" && $2=="200" {n++; next}
       {print "HTTPS_ERROR curl_rc=" $1 " http=" $2}
       END {printf "HTTPS_CONTROL %d/%d\n", n, NR}' "$D/https-codes.txt"
else
  printf 'HTTPS_CONTROL_UNAVAILABLE\n'
fi
if [[ $PHASE == after ]]; then
  audit 60 snapshot >"$D/long-before.json" || printf 'FIB_LONG_BEFORE_UNAVAILABLE\n'
  audit 610 watchdog --seconds 600 | tee "$D/long.json" || printf 'WATCHDOG_LONG_UNAVAILABLE\n'
  audit 60 snapshot >"$D/long-after.json" || printf 'FIB_LONG_AFTER_UNAVAILABLE\n'
fi
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
`step_details` по очереди сканов, ротации, проверке провайдера,
сквозной пробе, метрикам и диагностике адреса. Для каждой приведи
максимум и число шагов. `planned_scan_deferred_steps` считает шаги
с переносом дополнительной плановой пробы. При нуле пометь эффект
нового условия как `NOT_OBSERVED`. При ненулевом числе переноси
факт срабатывания отдельно от изменения p95. Причина разницы в p95
требует сопоставимого числа проб и одинакового состояния шлюза.
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

При `WATCHDOG_SCAN_ROLLED_BACK` укажи итог восстановления и HTTPS.
При `WATCHDOG_SCAN_ROLLBACK_PENDING` проверь
`xgw-watchdog-scan-rollback.timer` и `xgw-watchdog-scan-rollback.service`.
Дождись активного таймера. Если таймер и служба завершились,
а проверка восстановления не пройдена, используй значения из
текущего прогона и выполни:

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/install.py" \
  rollback --watchdog-scan --backup "$ROLLBACK_BACKUP"
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
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_watchdog-scan-budget.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre watchdog scan budget'
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
