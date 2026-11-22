# ThinkCentre — установка журнала закрепления и диагностики домашнего выхода

Целевая машина — **Ubuntu 24.04 LTS**. Flash сама запускает готовые
команды в терминале ThinkCentre и публикует один обезличенный отчёт.
Если терминал, sudo или GitHub недоступны, запроси доступ. Исходники,
установщик и критерии подготовлены Codex.

На этой машине прошли 13 контрактов за один запуск. Обе фазы
вернули 0, сводки совпали по всем 41 событиям. Кандидат тогда
проверялся в отдельной копии. В этом проходе нужно подтвердить его
совместимость с установленным комплектом и выполнить установку.
[Отчёт r2](../reports/2026-11-22T121135Z_home-exit-incident-r2.md)

## 1. Проверка и установка

Запусти в обычном терминале ThinkCentre и заранее выполни
`sudo -v`. Если pytest в отдельном окружении, экспортируй абсолютный
`XGW_TEST_PYTHON`. На время запуска исключи параллельные обновления XGW
и ручные переключения. Для применения потребуется один штатный
перезапуск `xgw.service`, поэтому выбери время, когда окно панели
может кратко потерять связь.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=844984a1a217d0b117dc44600baa7090f8db301e
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_pin_audit_install.sh" | bash -s -- "$CODE"
BASH
~~~

Изменения ограничены девятью файлами установленного Python-пакета
и его веб-интерфейса. Сценарий накладывает принятую правку на частную
копию установленных модулей по контексту и повторяет 13 тестов на этой
копии. Подписки, постоянные настройки и отдельный Qt-релиз в состав
обновления не входят. Проверка HTTPS выполняется через уже настроенный
локальный HTTP-вход Xray, с таймаутом 10 секунд на запрос.

| Признак | Критерий и действие |
|---|---|
| PIN_AUDIT_BASELINE_MISMATCH | Контекст расходится. Изменений на шлюзе нет. Укажи имя конфликтующего файла из частного `patch.err`, исходники и журнал оставь на машине. |
| PIN_AUDIT_CONTRACTS_OK | Ровно 13 тестов на копии установленного пакета. Сбой останавливает установку. Укажи имя теста и обезличенный симптом. |
| PIN_AUDIT_HTTPS baseline 200 | Начальное состояние читается, ручное закрепление отсутствует. HTTPS через Xray вернул 200. Если проверка остановилась, запиши последний маркер и причину. |
| PIN_AUDIT_ROLLBACK_ARMED | Перед заменой действует независимый таймер на 15 минут. Установщик повторно сверяет исходные байты и состояние воркеров. |
| PIN_AUDIT_DEPLOYED_AND_VERIFIED | Девять файлов сверены. XGW опубликовал свежий снимок, PID XGW изменился, PID Xray и SHA настроек совпали, HTTPS 200. Таймер снят. Оставь принятый слой установленным. |
| PIN_AUDIT_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED | Установленные байты содержат правку, контракты и исходные контроли прошли. Отдельно зафиксируй, что запуск процесса с этими файлами в данном проходе не проверялся. |

При `PIN_AUDIT_DEPLOYED_AND_VERIFIED` сними двухминутную сводку
штатных событий. В отчёте укажи только метки из вывода. Команды
закрепления и переключения для этого окна отсутствуют. Источники
CLI и панели проверяются на фикстурах.

~~~bash
bash <<'BASH'
set -euo pipefail
CODE=844984a1a217d0b117dc44600baa7090f8db301e
cd "$(git rev-parse --show-toplevel)"
BEGIN=$(date --iso-8601=seconds)
sleep 120
END=$(date --iso-8601=seconds)
timeline=$(git show "$CODE:docs/helpers/leak_cause_check.py" |
  sudo -n /usr/bin/timeout -k 3 15 /usr/bin/python3 -I -B - incident "$BEGIN" "$END")
awk '/^INCIDENT_EVENT .* source=(cli|panel|watchdog|balancer)$/ {print; seen=1}
     END {if (!seen) print "PIN_SOURCE_NOT_OBSERVED"}' <<< "$timeline"
BASH
~~~

## 2. Откат

При ошибке после постановки таймера сценарий пытается вернуть файлы
и подтверждает исходные SHA, PID Xray и HTTPS. Для
`PIN_AUDIT_ROLLBACK_PENDING` проверь состояния
`xgw-pin-audit-rollback.timer` и `xgw-pin-audit-rollback.service`.
Если таймер активен, дождись результата. Если он отсутствует,
а исходные файлы не восстановлены, используй значения двух
переменных из вывода текущего запуска и выполни:

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/install.py" \
  rollback --pin-audit --backup "$ROLLBACK_BACKUP"
~~~

Укажи результат восстановления и отдельно статус HTTPS, состояние
служб и таймера. Адреса, SHA настроек, содержимое базы, путь к
частным файлам и журналы остаются на машине.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`.
Запусти из рабочей копии при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-pin-audit-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_pin-audit-install.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre installed pin audit'
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
