# ThinkCentre — фоновое обновление DNS для WAN, r7

**Ubuntu 24.04 LTS.** Flash сама выполняет готовые команды и публикует
один обезличенный отчёт при любом исходе. При недоступности терминала,
sudo или GitHub запроси соответствующий доступ.

R6 установлен. В длинном окне очередь запустила 39 проб на 30 шагах.
Переносов из-за остатка интервала не было. В двух окнах разрешение WAN
занимало до 5,34 и 8,30 с при медиане около 0,1 мс. FIB совпал на всех
восьми снимках. HTTPS через Xray дал 10/12 до установки и 11/12 после.
[Отчёт r6](../reports/2026-11-22T181135Z_watchdog-scan-slot.md)

R7 запускает одно фоновое разрешение для адреса, который только что
ответил на TCP-проверку WAN и у которого до истечения кеша осталось
не больше 120 с из 600 с. Готовый ответ используется при истечении
предыдущей записи. Если результат не готов, не годится или сеть
сменилась, вступает штатное разрешение. Холодный кеш проверяется
обычным путём. Доступность WAN по-прежнему определяет результат TCP.

## 1. Порядок и исходные условия

1. В терминале ThinkCentre выполни `sudo -v`. Если pytest установлен
   в отдельном окружении, экспортируй абсолютный `XGW_TEST_PYTHON`.
2. Выполни `export PHASE=before LONG_ONLY=0` и запусти раздел 3
   на работающем слое r6.
   Если r7 уже применяется, укажи исходное окно как `NOT_RUN`.
3. Выполни раздел 2 в согласованное окно для одного штатного перезапуска
   `xgw.service`. На время работы исключи параллельные обновления
   и ручные переключения. Если ручное закрепление активно, сценарий
   выдаст отдельный маркер и завершится до подготовки установки.
4. При принятом r7 выполни `export PHASE=after LONG_ONLY=0` и запусти
   раздел 3.
   Если фоновых применений не видно и система работает штатно, запусти
   один дополнительный 600-секундный проход после
   `export PHASE=after LONG_ONLY=1`.
   Если произошёл откат, укажи `after=NOT_RUN`.
5. Разбери результаты по разделу 4 и автоматически опубликуй отчёт
   по разделу 6. Используй имеющиеся настройки и штатные запросы
   сценария. Для проверки фонового цикла достаточно обычной работы шлюза.

## 2. Установка и технические критерии

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=6438e403ec8c902587d613e041abfdc540ce1850
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_pin_audit_install.sh" |
  bash -s -- "$CODE" --watchdog-wan-dns
BASH
~~~

Сценарий подготавливает только `daemon.py` из `ee29dd7ed4f54263a033ebf404a40c0ab25f0124`
на базе слоя r6 `aa2a3ab`. Предварительная проверка включает 39
контрактов r6 и четыре случая для r7. Последние покрывают неблокирующее
разрешение с применением по TTL, переход на штатное разрешение при
ошибке или незавершённом запросе и отмену при смене сети.
После перезапуска гейт ждёт свежий шаг
текущего процесса до 120 с.

| Маркер | Что зафиксировать |
|---|---|
| WATCHDOG_WAN_DNS_BASELINE_MISMATCH | Контекст установленного файла не совпал. Приведи маркер и оставь исходный diff на машине. |
| WATCHDOG_WAN_DNS_CONTRACTS_OK | Все 43 контракта прошли на копии установленного пакета. Приведи счётчик и время. |
| WATCHDOG_WAN_DNS_MANUAL_PIN_ACTIVE | Установка остановлена до резервной копии и таймера. Сверь PID и настройки с исходными. Сохрани ручной выбор и укажи `BLOCKED_BY_MANUAL_PIN`. |
| WATCHDOG_WAN_DNS_HTTPS baseline 200 | Исходный HTTPS-контроль через Xray прошёл. |
| WATCHDOG_WAN_DNS_ROLLBACK_ARMED | Таймер активирован на 15 минут до замены. |
| WATCHDOG_TIMING_PROGRESS_CHECK | Запиши `result`, `polls` и `waiting_first_step`. |
| WATCHDOG_WAN_DNS_PROGRESS_OK | Свежий `last_step` содержит оба булевых счётчика фонового DNS. |
| WATCHDOG_WAN_DNS_DEPLOYED_AND_VERIFIED | Сверены байты файла, PID Xray и SHA настроек. HTTPS до и после установки вернул 200. Таймер снят. Оставь слой установленным. |
| WATCHDOG_WAN_DNS_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED | Действующий слой и его телеметрия подтверждены. |

Сценарий определяет ручное закрепление по полю `pin` в свежем статусе.
Автоназначение балансировщика отмечается отдельным событием `main_override`.
Имя и тег сервера оставь на машине. При каждом прогоне обновляй sudo при
необходимости. Если sudo истёк посреди фазы, укажи это и сохрани
повтор фазы отдельно.

## 3. Наблюдения до и после

В каждой основной фазе сценарий делает 12 HTTPS-запросов через Xray
за 180 секунд, затем наблюдает 600 секунд обычной работы. Снимки на
границах показывают классы FIB и позволяют сверить процессы и настройки.
Дополнительный проход снимает только длинное окно. Храни каждый вывод
в отдельном закрытом каталоге, который создаёт сценарий.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
CODE=6438e403ec8c902587d613e041abfdc540ce1850
[[ ${PHASE:-} == before || ${PHASE:-} == after ]]
[[ ${LONG_ONLY:-0} == 0 || ( $PHASE == after && $LONG_ONLY == 1 ) ]]
cd "$(git rev-parse --show-toplevel)"
git fetch origin integration/zapret2-batch1
git merge-base --is-ancestor "$CODE" FETCH_HEAD
sudo -n true
D=$(mktemp -d "$HOME/xgw-wan-dns-observe.XXXXXXXX")
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

## 4. Что должно быть в отчёте

- Итог установки, результат контрактов, ожидание свежего шага,
  восстановление при откате, факт совпадения FIB, PID Xray и SHA
  настроек. Укажи версию ОС и SHA использованных коммитов.
- На каждое окно приведи число завершённых и пропущенных шагов,
  интервал, p95, максимум и ошибки чтения. Укажи `provider_resolve`,
  `provider_connect`, `end_to_end` и `scan_queue` с числом замеров,
  p50, p95 и максимумом. Приведи также число WAN-попыток, число проб
  из очереди и переносы. При малой выборке укажи её размер рядом с p95.
- Для `provider_dns_refresh` приведи `steps`, `started`, `used`
  и `max_resolve_s_when_used`. `null` на r6 означает старый формат.
  При `used > 0` зафиксируй живое использование фонового ответа.
  Максимум включает всё разрешение WAN в соответствующем шаге, в том
  числе попытки других WAN-целей при переключении. При `used=0`
  после дополнительного окна запиши `NOT_OBSERVED` и отдельно укажи,
  был ли запуск. Уменьшение общего p95 само по себе не подтверждает
  эффект DNS.
- По HTTPS укажи числитель и знаменатель, для отказов — curl_rc,
  HTTP, CONNECT и время завершения TLS. По FIB приведи классы
  путей, типы, таблицы и совпадение на границах. По журналу укажи
  число сообщений по каждой из четырёх групп. Оставь на машине
  сырые логи, адреса, имена, внутренние пути и контрольные суммы.
- Если доступен `wake.state`, приведи состояние и число наборов.
  Для наблюдавшихся причин запиши максимум задержки и
  `last_step_overlap`. Укажи, если маршрут, PID или настройки
  изменились во время окна. Оцени такие окна отдельно.

## 5. Восстановление

При `WATCHDOG_WAN_DNS_ROLLED_BACK` приведи статус, HTTPS и результат
сверки с исходным слоем. При `WATCHDOG_WAN_DNS_ROLLBACK_PENDING`
проверь `xgw-watchdog-wan-dns-rollback.timer` и соответствующую службу.
Если идёт штатный откат, дождись его завершения. Если таймер и служба
завершились, а восстановление не подтверждено, используй значения
`ROLLBACK_PAYLOAD` и `ROLLBACK_BACKUP` из текущего запуска.

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/install.py" \
  rollback --watchdog-wan-dns --backup "$ROLLBACK_BACKUP"
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
PUB=$(mktemp -d "$HOME/xgw-watchdog-wan-dns-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_watchdog-wan-dns.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre WAN DNS refresh'
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
