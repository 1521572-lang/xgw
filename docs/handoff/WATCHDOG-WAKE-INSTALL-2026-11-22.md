# ThinkCentre — установка диагностики длительных шагов watchdog, r2

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарии и автоматически
публикует один обезличенный отчёт. При недоступности терминала,
sudo или GitHub запроси доступ. Команды и проверки подготовлены Codex.

Установка первого формата прошла 15/15. В каждом окне наблюдался
один совместный набор `net` и `rules`. Начало разбора было общим.
Время до него составило 10,27–10,54 с для `net` и 5,80–6,21 с
для `rules`. Разность соответствует более раннему поступлению `net`
в этих двух наборах. FIB и настройки совпали, HTTPS дал 11/12.
[Отчёт установки](../reports/2026-11-22T132531Z_watchdog-wake-install.md)

Чтение раз в секунду может пропустить короткую фазу `sleep`. R2 хранит
последний завершённый шаг в обеих фазах и учитывает пробелы номеров
между прочитанными записями. Начало разбора события и время отдельной
проверки правил измеряются независимо.

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
CODE=0b4684129fd1b29da6f98b982fc940594b2d1b7f
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_pin_audit_install.sh" |
  bash -s -- "$CODE" --watchdog-timing
BASH
~~~

Сценарий накладывает диагностику из `6de2c66658f9889a42e906859e480ed05714d84d`
поверх меток `c69ff9a` в копии установленного `daemon.py`.
Прогон покрывает новый формат, перекрытие ожидания с последним
шагом, проверку правил, прежние контракты watchdog, ip rule и TUN.
Установка касается одного файла.

| Маркер | Действие и критерий |
|---|---|
| WATCHDOG_TIMING_BASELINE_MISMATCH | Контекст в установленном файле расходится. Укажи имя файла и классификацию сбоя, исходный diff оставь на машине. |
| WATCHDOG_TIMING_CONTRACTS_OK | Все 17 тестов прошли на копии установленного пакета. При сбое установка останавливается. |
| WATCHDOG_TIMING_HTTPS baseline 200 | После сверки исходных байтов и свежего статуса начальный HTTPS-контроль через Xray вернул 200. Ручного закрепления нет. |
| WATCHDOG_TIMING_ROLLBACK_ARMED | Независимый таймер на 15 минут активен перед заменой. Установщик повторно сверил байты и состояние воркеров. |
| WATCHDOG_TIMING_PROGRESS_OK | Штатный закрытый файл `watchdog-step.json` содержит поколение, `last_step` и `wake`. Для `wake` допустим `null`. |
| WATCHDOG_TIMING_DEPLOYED_AND_VERIFIED | Файл сверили, XGW опубликовал свежий статус после перезапуска, PID Xray и SHA настроек совпали. HTTPS при установке и подтверждении вернул 200. Таймер снят. Оставь слой установленным. |
| WATCHDOG_TIMING_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED | Установленные байты совпали с правкой по контексту. Живой процесс подтвердил формат. Повторного перезапуска не было. |

## 2. Наблюдение после подтверждения

Выполни после одного из двух успешных итогов установки. Сначала
`sudo -v`. Десятиминутное окно увеличивает число шагов для оценки
p95. Второе окно на 180 секунд повторяет лёгкую HTTPS-нагрузку.
Обычная работа шлюза продолжается. Сон, отключение интерфейса
или удаление правил для получения метки в сценарий не входят.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
CODE=0b4684129fd1b29da6f98b982fc940594b2d1b7f
cd "$(git rev-parse --show-toplevel)"
sudo -n true
D=$(mktemp -d "$HOME/xgw-wake-observe.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
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
audit 60 snapshot >"$D/long-before.json" || printf 'FIB_LONG_BEFORE_UNAVAILABLE\n'
audit 610 watchdog --seconds 600 | tee "$D/long.json" || printf 'WATCHDOG_LONG_UNAVAILABLE\n'
audit 60 snapshot >"$D/long-after.json" || printf 'FIB_LONG_AFTER_UNAVAILABLE\n'

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

В отчёте приведи оба `configured_intervals_s`, число завершённых
шагов, `unseen_steps_between_samples`, максимум, p95 и ошибки чтения.
При малой выборке пометь p95 как описательный. Приведи три
наибольших значения из `step_part_max_s`. Они описывают выборку
окна. Подсчёт охватывает завершения внутри текущего окна. Отдельно
укажи `wake.state` и количество наборов. `not_observed` означает,
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

При `WATCHDOG_TIMING_ROLLED_BACK` укажи итог восстановления и HTTPS.
При `WATCHDOG_TIMING_ROLLBACK_PENDING` проверь
`xgw-watchdog-timing-rollback.timer` и `xgw-watchdog-timing-rollback.service`.
Дождись активного таймера. Если таймер и служба завершились,
а проверка восстановления не пройдена, используй значения из
текущего прогона и выполни:

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/install.py" \
  rollback --watchdog-timing --backup "$ROLLBACK_BACKUP"
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
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_watchdog-step-attribution.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre watchdog step timing and wake attribution'
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
