# ThinkCentre — дедлайн дополнительных плановых проб, r8

**Ubuntu 24.04 LTS.** Flash сама выполняет техническую проверку
по готовым командам и публикует один обезличенный отчёт при любом
исходе. При недоступности терминала, sudo или GitHub запроси доступ.

R7 принят с первой установки. Фоновый DNS-ответ использован один раз,
разрешение на этом шаге заняло 0,1 мс. В обоих окнах HTTPS-контроль дал
11/12. В 600-секундном окне r7 после установки очередь запустила 32
пробы за 26 шагов. Работа очереди занимала до 17,90 с. До установки
в очереди не было запусков, поэтому сопоставимых данных по времени
активного сканирования нет. [Отчёт r7](../reports/2026-11-22T212525Z_watchdog-wan-dns.md)

R8 задаёт общий дедлайн в 8 с от начала обработки очереди для
дополнительных плановых проб обычных запасных в состоянии HEALTHY.
Запросы обоих проверочных хостов делят этот срок. При отмене по
дедлайну тег возвращается в начало очереди. Отмена не меняет вердикт
или рейтинг. Первая проба, ручные и срочные проверки, проверки
участников, аварийные режимы и пробы профилей используют свои
таймауты. Полное время обработки очереди может превышать 8 с.

## 1. Порядок прогона

1. Выполни `sudo -v`. Если pytest установлен в отдельном окружении,
   экспортируй абсолютный `XGW_TEST_PYTHON`.
2. На действующем r7 выполни `export PHASE=before LONG_ONLY=0` и запусти
   раздел 3. Если r8 уже применяется, укажи `before=NOT_RUN`.
3. Выполни раздел 2 в окно для штатного перезапуска `xgw.service`.
   На время прогона исключи параллельные обновления и ручные
   переключения. При активном ручном закреплении сохрани выбор
   владельца и зафиксируй маркер сценария.
4. Если r8 принят, выполни `export PHASE=after LONG_ONLY=0` и запусти
   раздел 3. При откате запиши `after=NOT_RUN`.
5. Если в длинном окне не было запусков из очереди или после установки
   не было проб с дедлайном, разрешён один дополнительный 600-секундный
   проход для соответствующей фазы до перехода к следующей.
   Используй `LONG_ONLY=1` и выбери время ближайшего штатного круга
   по `NEXT_PLANNED_SCAN_S`, если он ожидается в пределах 600 с.
   Используй штатный плановый круг с текущими настройками. Если нужный
   случай не возник, запиши `NOT_OBSERVED`.
6. Разбери результаты по разделу 4 и опубликуй отчёт по разделу 6.

## 2. Установка

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=04339a4de37a5e9a7fa4fd3e689c2f2acacc0fe0
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_pin_audit_install.sh" |
  bash -s -- "$CODE" --watchdog-scan-deadline
BASH
~~~

Сценарий обновляет только `daemon.py` из `c101a1f5e60146ed90d9f215efe1f97c3f0706a0` поверх r7
`ee29dd7`. На копии установленного пакета проверяет 43 случая r7
и семь новых случаев. Они проверяют общий дедлайн двух хостов,
возврат тега без вердикта, различение дедлайна и остановки демона,
первую пробу после возврата и полные таймауты для пяти видов
приоритетных проверок.

| Маркер | Что зафиксировать |
|---|---|
| WATCHDOG_SCAN_DEADLINE_BASELINE_MISMATCH | Контекст файла не совпал. Приложи итог команды без исходного diff. |
| WATCHDOG_SCAN_DEADLINE_CONTRACTS_OK | Все 50 контрактов прошли. Приведи счётчик и время. |
| WATCHDOG_SCAN_DEADLINE_MANUAL_PIN_ACTIVE | Установка остановлена до замены. Сверь PID и настройки. Укажи `BLOCKED_BY_MANUAL_PIN`. |
| WATCHDOG_SCAN_DEADLINE_HTTPS baseline 200 | Исходный HTTPS через Xray вернул 200. |
| WATCHDOG_SCAN_DEADLINE_ROLLBACK_ARMED | Независимый таймер на 15 минут активен перед заменой. |
| WATCHDOG_TIMING_PROGRESS_CHECK | Приведи `result`, `polls` и `waiting_first_step`. |
| WATCHDOG_SCAN_DEADLINE_PROGRESS_OK | Свежий завершённый шаг содержит новые поля дедлайна и поля r7. |
| WATCHDOG_SCAN_DEADLINE_DEPLOYED_AND_VERIFIED | Файл, PID Xray и SHA настроек сверены, HTTPS вернул 200, таймер снят. Оставь слой установленным. |
| WATCHDOG_SCAN_DEADLINE_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED | Байты и телеметрия действующего слоя подтверждены. |

## 3. Наблюдения

Основные фазы используют одинаковые окна по 180 с с 12 контрольными
HTTPS-запросами через Xray и по 600 с обычной работы. Дополнительная
фаза снимает длинное окно без контрольной серии. Перед каждой фазой
обнови sudo. Если он истёк посреди окна, укажи прерывание и запиши
повтор отдельно. Свою сетевую активность во время обеих фаз сохраняй
сопоставимой. Сценарий создаёт закрытый каталог для каждого запуска.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
CODE=04339a4de37a5e9a7fa4fd3e689c2f2acacc0fe0
[[ ${PHASE:-} == before || ${PHASE:-} == after ]]
[[ ${LONG_ONLY:-0} == 0 || ${LONG_ONLY:-0} == 1 ]]
cd "$(git rev-parse --show-toplevel)"
git fetch origin integration/zapret2-batch1
git merge-base --is-ancestor "$CODE" FETCH_HEAD
sudo -n true
D=$(mktemp -d "$HOME/xgw-scan-deadline-observe.XXXXXXXX")
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

if [[ ${LONG_ONLY:-0} == 0 ]]; then
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
fi
sudo -n /usr/bin/python3 -I -B - <<'PYTHON' || printf 'NEXT_PLANNED_SCAN_UNAVAILABLE\n'
import json
import math
import time
from pathlib import Path
row = json.loads(Path("/run/xgw/status.json").read_bytes())
assert 0 <= time.time() - row["updated"] <= 180
value = row["scan_pacing"]["next_planned_in_s"]
assert type(value) in (int, float) and math.isfinite(value) and value >= 0
print(f"NEXT_PLANNED_SCAN_S {math.ceil(value)}")
PYTHON
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

## 4. Отчёт

- Приведи ОС, SHA кандидата, итог установки или восстановления,
  результаты 50 контрактов и гейта свежего шага. Сверь PID Xray,
  настройки и таймер. Для двух основных фаз зафиксируй совпадение
  классов, типов и таблиц FIB на границах.
- Для каждого окна приведи интервал watchdog, число завершённых
  и пропущенных шагов, ошибки чтения, p95 и максимум шага. Укажи
  `queue_probes`, переносы, `scan_queue` и `scan_queue_active`
  с числом шагов, p50, p95 и максимумом. Последнее поле содержит
  только шаги, в которых есть запуск из очереди. Если один из слоёв
  не дал активных шагов, пометь сравнение времени скана как
  `NOT_COMPARABLE`. При малой выборке укажи её размер рядом с p95.
- Запиши `scan_budget.steps`, `limited_probes`, `cancelled_steps`
  и `max_queue_s_when_cancelled`. Для r7 эти поля отсутствуют.
  `limited_probes > 0` подтверждает подключение дедлайна,
   `cancelled_steps > 0` подтверждает его срабатывание. При нуле отмен
   отметь `NOT_OBSERVED` для срабатывания. Время обработки очереди включает
  первую пробу, паузы, обработку и сохранение итога. Частичные
  запросы входят в счётчик запусков, сама отмена не создаёт вердикт.
- Укажи числа и длительности `provider_resolve`,
  `provider_connect`, `end_to_end` и `provider_dns_refresh`,
  чтобы отделить изменения сети от эффекта очереди. Если
  наблюдалось пробуждение watchdog, укажи число наборов, максимумы
  задержек и доступные `last_step_overlap` по причинам.
- Для HTTPS приведи числитель и знаменатель. Для отказов укажи
  curl_rc, HTTP, CONNECT и время завершения TLS. По журналу приведи
  числа для четырёх групп. Сырые логи, адреса, имена серверов,
  внутренние пути и контрольные суммы оставь на машине.

## 5. Откат

При `WATCHDOG_SCAN_DEADLINE_ROLLED_BACK` укажи результат сверки и
HTTPS. При `WATCHDOG_SCAN_DEADLINE_ROLLBACK_PENDING` проверь
`xgw-watchdog-scan-deadline-rollback.timer` и соответствующую службу.
Если идёт штатный откат, дождись его завершения. Если таймер и
служба завершились, а восстановление не подтверждено, используй
`ROLLBACK_PAYLOAD` и `ROLLBACK_BACKUP` из текущего запуска.

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/install.py" \
  rollback --watchdog-scan-deadline --backup "$ROLLBACK_BACKUP"
~~~

## 6. Автоматическая публикация

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
PUB=$(mktemp -d "$HOME/xgw-watchdog-scan-deadline-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_watchdog-scan-deadline.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre deadline for additional scheduled scans'
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
