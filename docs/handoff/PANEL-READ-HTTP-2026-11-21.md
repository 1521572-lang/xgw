# ThinkCentre — отдельный HTTP-процесс для статуса zapret2

**Ubuntu 24.04 LTS.** Flash сама выполняет готовые команды и
публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, рабочей сессии панели или GitHub запроси доступ и
продолжи сама. Код, сценарий и критерии подготовлены Codex.

В предыдущем проходе принят Unix-сокет P2.1. Прошли 94 теста,
разрешённый UID получил те же пять полей, что и действующая панель,
второй UID из той же группы был отклонён.
[Отчёт](../reports/2026-11-21T141753Z_panel-read-ipc.md)

Новый процесс под отдельным UID открывает временный loopback-порт.
Единственный маршрут `GET/HEAD /api/zapret2/status` получает пять полей
по принятому Unix-сокету и защищён отдельным случайным ключом этого
прогона. Ключ поступает через stdin. Штатные XGW, Xray и их панель
продолжают работать в ходе проверки. Тестовый процесс и сокет удаляются
после прогона, установки пакетов и правки сети не требуются.

## 1. Запуск

Выполни блок как пользователь рабочей сессии XGW. При необходимости
подтверди sudo с `sudo -v` в интерактивном терминале. Если pytest
установлен отдельно, задай абсолютный путь `XGW_TEST_PYTHON` заранее.

```bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=b68616921658ccbac377de5bae96dcfbd26a4d90
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_panel_read_http_lab.sh" | bash -s -- "$CODE"
BASH
```

Сценарий сохраняет результаты в приватном каталоге, путь к которому
печатается в `Private run`. Он проверяет исходный off/off и HTTPS через
Xray, запускает тесты исходников, затем отдельный HTTP-процесс и IPC.
Имитированный отказ бэкенда происходит в памяти временного процесса.
Заключительная проверка сопоставляет итоговое состояние с исходным.

## 2. Критерии

| Этап | Что записать |
|---|---|
| `PINNED`, `BASELINE_OK`, `CONTRACT_TESTS_RC` | SHA, версия Ubuntu и ядро, исходный off/off fresh/matched и HTTPS 200, число passed/failed/skipped. |
| `socket_permissions`, `http_privileges`, `http_panel_token_denied` | Сокет root 0660. HTTP обслуживает UID без дополнительных групп. Все пять масок capabilities нулевые, `NoNewPrivs=1`. Файл токена установленной панели недоступен этому UID. |
| `http_file_readability` | Отдельно запиши два булевых признака доступности настроек и рабочего снимка. Проба проверяет права чтения без чтения содержимого. Эти признаки нужны для профиля изоляции будущей службы. |
| `http_anonymous`, `http_wrong_key`, `http_duplicate_authorization`, `http_other_origin`, `http_duplicate_host`, `http_post`, `http_only_read_route` | 401 без ключа, с неверным или повторённым заголовком, 403 для чужого Origin или повторённого Host, 405 для POST и 404 для `/api/state`. Отклонённые запросы не доходят до бэкенда. |
| `allowed`, `http_head`, `ISOLATED_HTTP_STATUS_MATCH` | Авторизованный GET даёт 200 и пять полей действующего статуса. HEAD успешен с пустым телом. Поля совпадают со штатной панелью. |
| `http_unavailable`, `http_recovered` | При отказе IPC получается 503, после восстановления 200 с прежней карточкой. |
| `http_cleanup`, `socket_cleanup`, `TOOLS_REMOVED`, `GATEWAY_UNCHANGED` | Временный порт закрыт, процесс, сокет и root-каталог удалены. Обе штатные службы активны, PID и три контрольных файла совпали, off/off fresh/matched и HTTPS 200 сохранены. |

При сбое запиши последний прошедший этап и код первой ошибки.
Если исходный режим отличается, оставь его как есть и укажи `NOT_RUN`
для живого прогона. При изменении финального контроля повтори чтение
статуса и служб один раз. Отчёт содержит коды и агрегированные результаты.
Ключ, cookie, PID, хэши, приватные пути, адреса и URL остаются на машине.

## 3. Автоматическая публикация

Создай один обезличенный Markdown-отчёт. Укажи его абсолютный путь
в `REPORT_SRC` и сама выполни блок из checkout. При параллельном
обновлении ветки блок один раз переносит коммит поверх свежего HEAD.
Верни ссылку на проверенный коммит отчёта.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-http-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-read-http.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre standalone panel read HTTP acceptance'
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
