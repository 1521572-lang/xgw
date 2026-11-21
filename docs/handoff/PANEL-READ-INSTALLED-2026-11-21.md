# ThinkCentre — проверка читателя на установленной панели XGW

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарий и автоматически
публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, рабочей сессии панели или GitHub запроси доступ и
продолжи сама. Код и команды подготовлены Codex.

В P2.5 r2 прошли все 205 тестов. На живом снимке первый запрос
запустил временный reader за 735 мс. `/run` был только для чтения,
пять полей совпали со штатной панелью и повторная активация прошла.
[Отчёт P2.5 r2](../reports/2026-11-21T170120Z_panel-read-service-r2.md)

В P2.6 сценарий временно заменяет 13 файлов пакета и три файла
systemd из принятого кандидата. В исходной базе `cli.py` сверяется
с `ad81542`, остальные исходные файлы сверяются с `08d31ee`. При
несовпадении сценарий запишет все найденные имена. После совпадения
базы вооружается независимый таймер отката на 20 минут. Перед
испытанием и при восстановлении перезапускается только `xgw.service`.
Сценарий создаёт системную учётную запись читателя при её отсутствии
и удаляет свою запись после возврата файлов. Существующая подходящая
запись сохраняется. Полная переустановка и действия с VPN, nft и
ядрами шлюза в этот прогон не входят.

## 1. Запуск

Выполни блок как пользователь рабочей сессии XGW в окно перезапуска
панели. Подтверди sudo через `sudo -v` в интерактивном терминале.
Если pytest находится в другом окружении, заранее задай абсолютный
путь `XGW_TEST_PYTHON`. Для проверки установленной панели нужна
действующая сохранённая Qt-сессия, как в предыдущих проходах.

```bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=10fe206c1b3dc7d5a4bd98a5464fda1574307f46
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_panel_installed_trial.sh" | bash -s -- "$CODE"
BASH
```

`Private run` сообщает путь приватного каталога. `steps.tsv`
содержит этапы и коды. Перед временной заменой скрипт запускает два
контракта отката на подставных файлах. Для этапа `candidate-http`
он проверяет браузерный обмен одноразового кода по HTTP и маршрут
на установленной панели. `candidate-session` использует обычный
CLI-клиент с сохранённой сессией, `candidate-qt` запускает настоящий
`ApiClient.fetch()` в Qt. Проверка Qt выполняется без открытия окна.

## 2. Критерии

| Этап | Что записать |
|---|---|
| `baseline-session`, `baseline-http`, `baseline-https`, `contracts`, `prepare` | SHA кандидата, Ubuntu, ядро, systemd, исходный off/off fresh/matched и HTTPS 200. В старой панели обзор 200, узкий маршрут 404. Оба контракта отката прошли и `BASELINE_MATCH 16`. При `baseline_mismatch` запиши имена файлов и статус `NOT_RUN` живой установки. |
| `arm-timer`, `timer-active`, `apply`, `candidate-ready` | Таймер активен до первого изменения, файлы кандидата проверены, `CANDIDATE_STARTED`, исходная сессия видит off/off fresh/matched после запуска. |
| `ONE_TIME_CLI_OK`, `READER_DORMANT_OK` | Команда `xgw panel` выдаёт одноразовую ссылку. HTTP даёт cookie и отклоняет повтор. Запросы без сессии, с чужим Host или Origin, а также POST отклонены. Reader в этот момент остаётся незапущенным. |
| `INSTALLED_STATUS_MATCH`, `READER_RUN_READONLY_OK`, `candidate-session`, `candidate-qt` | GET возвращает 200 и пять полей полного обзора. HEAD даёт пустое тело, `/run` только для чтения, UID и capabilities проверены. Запиши `cold_ms`, результат CLI и `QT_NETWORK_OK` или `QT_NOT_AVAILABLE`. |
| `INSTALLED_READER_RECOVERED_OK`, `candidate-same-xray`, `candidate-same-settings`, `candidate-https` | При остановке пары reader узкий маршрут даёт 503, полный обзор 200. После восстановления сокета проходит 200 с новым PID читателя и тем же PID XGW. PID Xray и три файла совпали с исходными, HTTPS 200. |
| `rollback`, `restored-session`, `restored-http`, `restored-same-xray`, `restored-same-settings`, `restored-https`, `cancel-timer`, `STAGE_REMOVED` | Файлы, права и режим панели возвращены, временные unit и сокеты убраны, права исходной сессии сохранены. Xray всё ещё работает с исходным PID и HTTPS 200. Таймер снят после проверки. |

При сбое отчитайся о последнем успешном этапе, первой ошибке и
состоянии отката. Если процесс сценария прервался, проверь состояние
таймера `xgw-panel-reader-rollback.timer` и дождись его срабатывания
при активном таймере. Зафиксируй статус XGW, Xray и доступность HTTPS.
В отчёте оставь только результаты проверок. Пути, PID, хэши,
URL, cookie, токены и коды входа остаются на машине.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC` и
сама выполни блок. При параллельном обновлении ветки блок один раз
переносит коммит поверх свежего HEAD. Верни ссылку на проверенный
коммит отчёта.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-installed-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-read-installed.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre installed-panel status reader acceptance'
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
git fetch origin "$BR"
git merge-base --is-ancestor HEAD FETCH_HEAD
printf 'PUBLISHED %s %s\n' "$(git rev-parse HEAD)" "$REPORT"
BASH
```
