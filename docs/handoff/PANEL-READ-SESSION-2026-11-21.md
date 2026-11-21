# ThinkCentre — проверка сеанса панели для чтения статуса zapret2

**Ubuntu 24.04 LTS.** Flash сама выполняет готовый сценарий и
публикует один обезличенный отчёт при любом исходе. Если недоступны
терминал, sudo, рабочая сессия панели или GitHub, запроси доступ
и продолжи сама. Код и команды подготовлены Codex.

В P2.3 прошли 95 тестов. HTTP-процесс внутри временного unit
получил отказ на открытие четырёх файлов XGW. Через сокет он вернул
те же пять полей, что и действующая панель.
[Отчёт P2.3](../reports/2026-11-21T145213Z_panel-read-sandbox.md)

Кандидат P2.4 проверяет cookie на доверенном входе панели. Затем
он выдаёт одноразовый допуск со сроком до пяти секунд для чтения
пяти полей zapret2. Изолированный процесс принимает HTTP через
Unix-сокет, проверяет UID вызывающего процесса и передаёт допуск
на IPC версии 2. Бэкенд принимает допуск один раз. Unit допускает
только AF_UNIX. Оба сокета и тестовый вход удаляются после испытания.

Сценарий использует временный вход с собственным одноразовым кодом
и штатной логикой cookie. Состояние zapret2 берётся с работающего
шлюза. Проверка формата Qt-сессии и транспорта CLI выполняется
без запуска или замены настольного приложения. XGW и Xray
продолжают работать, настройки и политики zapret2 сохраняются.

## 1. Запуск

Выполни блок как пользователь рабочей сессии XGW. Подтверди sudo
через `sudo -v` в интерактивном терминале. Если pytest находится
в отдельном окружении, заранее задай абсолютный `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=6d2a897860d355a57c64cc3a616cfcee7af03fae
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_panel_read_http_lab.sh" | bash -s -- "$CODE"
BASH
```

В `Private run` сценарий сообщает путь приватного каталога. При
ошибке запуска зафиксируй последний успешный этап, код ошибки
и итог очистки. Временный unit ограничен 40 секундами работы.
Для шлюза в режиме, отличающемся от `off/off`, запиши `NOT_RUN`
для живого прогона и сохрани наблюдаемый режим.

## 2. Критерии

| Этап | Что записать |
|---|---|
| `PINNED`, `BASELINE_OK`, `CONTRACT_TESTS_RC` | SHA, Ubuntu, ядро, systemd, исходный off/off fresh/matched и HTTPS 200. Число passed/failed/skipped. Контрактный набор включает срок действия допуска и отклонение неподдерживаемой операции. |
| `http_unsandboxed_snapshot`, `http_sandbox_files_denied`, `http_mount_namespace`, `http_privileges` | Контроль читаемости снимка вне unit и отказ при прямом открытии четырёх файлов в unit. Отдельное пространство монтирования, непривилегированный UID, собственная группа, все маски capabilities нулевые, `NoNewPrivs=1`. |
| `socket_permissions`, `http_inet_denied`, `http_unix_relay`, `session_ingress_uid`, `session_denies_unscoped_ipc` | Сокет IPC root 0660 и HTTP-сокет 0660 с группой root. IPv4 и IPv6 сокеты из unit создать нельзя. Чужой UID отклоняется на HTTP-сокете. Пакет v1 без допуска отклоняется даже с разрешённым UID. |
| `session_one_time_login`, `session_ingress_guards` | Временная ссылка выдаёт 303 с cookie, повтор даёт 403. Анонимный и неверный сеансы получают 401, чужой Origin — 403, POST — 405. Передача только cookie из тестового сеанса напрямую HTTP-процессу даёт 401. Эти запросы не открывают данные IPC. |
| `allowed`, `session_head`, `session_qt_cli_client`, `ISOLATED_HTTP_STATUS_MATCH` | GET возвращает 200 с пятью полями штатной панели, HEAD — 200 с пустым телом. Клиент CLI с объектом Qt-сессии получает те же пять полей. |
| `session_ticket_single_use`, `session_recovered` | Первый допуск принимается, повтор и отозванный допуск получают 401. После имитации отказа возвращается 503, после восстановления — 200 с прежними полями. |
| `session_ingress_stopped`, `http_unit_stopped`, `http_relay_removed`, `socket_cleanup`, `TOOLS_REMOVED`, `GATEWAY_UNCHANGED` | Оба слушателя прекращают работу, сокеты и временный root-каталог удалены. XGW и Xray активны, PID и три контрольных файла совпали, off/off fresh/matched и HTTPS 200 сохранились. |

В отчёт включи только коды и агрегированные результаты. Cookie,
одноразовые коды и допуски, PID, хэши, пути, адреса и URL остаются
на машине.

## 3. Автоматическая публикация

Укажи абсолютный путь к подготовленному отчёту в `REPORT_SRC`
и сама выполни блок. При параллельном обновлении ветки команда
один раз переносит коммит поверх свежего HEAD. Верни ссылку на
проверенный коммит отчёта.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-session-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-read-session.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre panel session relay acceptance'
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
