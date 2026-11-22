# ThinkCentre — установка меток реакции watchdog

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарии и автоматически
публикует один обезличенный отчёт. При недоступности терминала,
sudo или GitHub запроси доступ. Команды и проверки подготовлены Codex.

В первом проходе прошли 16 контрактов. FIB совпал во всех четырёх
снимках, получили 12 ответов HTTPS 200 из 12, максимальные шаги
в двух окнах составили 5,59 и 6,39 с. Установленный демон использовал
старый формат прогресса. На машине работают принятые шлюзом Xray
26.11.9 и sing-box 1.14.4. [Отчёт базовой линии](../reports/2026-11-22T125715Z_watchdog-fib-baseline.md)

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
CODE=bb7508e1901f23dc078da8881d808dc6c7e0d8c5
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_pin_audit_install.sh" |
  bash -s -- "$CODE" --watchdog-wake
BASH
~~~

Сценарий применяет принятый diff `c69ff9a` к частной копии
установленного `daemon.py`. Прогон покрывает метки, окно измерения,
watchdog, ip rule и TUN. Контракты обновления ядер уже прошли в
закреплённом дереве предыдущего ТЗ. Установка касается одного файла,
поэтому версии ядер и конфигурация остаются прежними.

| Маркер | Действие и критерий |
|---|---|
| WATCHDOG_WAKE_BASELINE_MISMATCH | Контекст в установленном файле расходится. Укажи имя файла и классификацию сбоя, исходный diff оставь на машине. |
| WATCHDOG_WAKE_CONTRACTS_OK | 15 тестов прошли на копии установленного пакета. При сбое установка останавливается. |
| WATCHDOG_WAKE_HTTPS baseline 200 | После сверки исходных байтов и свежего статуса начальный HTTPS-контроль через Xray вернул 200. Ручного закрепления нет. |
| WATCHDOG_WAKE_ROLLBACK_ARMED | Независимый таймер на 15 минут активен перед заменой. Установщик повторно сверил байты и состояние воркеров. |
| WATCHDOG_WAKE_PROGRESS_OK | Штатный закрытый файл `watchdog-step.json` обновился и содержит поколение и поле `wake`. Начальное `null` допустимо. |
| WATCHDOG_WAKE_DEPLOYED_AND_VERIFIED | Файл сверили, XGW опубликовал свежий статус после перезапуска, PID Xray и SHA настроек совпали. HTTPS при установке и подтверждении вернул 200. Таймер снят. Оставь слой установленным. |
| WATCHDOG_WAKE_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED | Установленные байты совпали с правкой по контексту. Живой процесс подтвердил формат. Повторного перезапуска не было. |

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
CODE=bb7508e1901f23dc078da8881d808dc6c7e0d8c5
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
      code=$(curl -q -sS --max-time 5 --max-filesize 131072 --noproxy '' \
        --proxy "http://127.0.0.1:$port" -o /dev/null -w '%{http_code}' \
        https://example.org/ 2>>"$D/https-private.err") || code=error
      printf '%s\n' "$code"
      if (( i < 12 )); then sleep 10; fi
    done
  ) >"$D/https-codes.txt" &
  control=$!
  audit 190 watchdog --seconds 180 | tee "$D/https.json" || printf 'WATCHDOG_HTTPS_UNAVAILABLE\n'
  wait "$control"
  audit 60 snapshot >"$D/https-after.json" || printf 'FIB_HTTPS_AFTER_UNAVAILABLE\n'
  awk '$0=="200" {n++} END {printf "HTTPS_CONTROL %d/%d\n", n, NR}' "$D/https-codes.txt"
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

В отчёте приведи число завершённых шагов, максимум, p95 и ошибки
чтения в каждом окне. При малой выборке пометь p95 как описательный.
Подсчёт охватывает завершения внутри текущего окна. Отдельно
укажи `wake.state` и количество наборов. `not_observed` означает,
что формат доступен, а причин в выборке нет. `not_instrumented`
означает старый формат. `unavailable` означает отсутствие читаемых
данных. Для `observed` укажи число и максимум по каждой причине.
Наблюдатель читает последнюю опубликованную отметку. Число увиденных
наборов характеризует выборку, а задержка заканчивается в момент
начала обработки. Из снимков FIB перенеси только классы путей,
типы, таблицы и факт совпадения на границах. Из журнала перенеси
счётчики сообщений, включая ноль. Приватные данные оставь на машине.

## 3. Откат

При `WATCHDOG_WAKE_ROLLED_BACK` укажи итог восстановления и HTTPS.
При `WATCHDOG_WAKE_ROLLBACK_PENDING` проверь
`xgw-watchdog-wake-rollback.timer` и `xgw-watchdog-wake-rollback.service`.
Дождись активного таймера. Если таймер и служба завершились,
а проверка восстановления не пройдена, используй значения из
текущего прогона и выполни:

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/install.py" \
  rollback --watchdog-wake --backup "$ROLLBACK_BACKUP"
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
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_watchdog-wake-install.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre watchdog wake deployment'
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
