# ThinkCentre — изоляция файлов HTTP-процесса zapret2

**Ubuntu 24.04 LTS.** Flash сама запускает готовый сценарий и
публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, рабочей сессии панели или GitHub запроси доступ
и продолжи сама. Код, команды и критерии подготовлены Codex.

В P2.2 прошли 95 тестов. HTTP-процесс получил по IPC те же пять
полей, что возвращает действующая панель. При отказе IPC проверены
503 и восстановление до 200. UID процесса имел доступ на чтение
к рабочему снимку `status.json`. Это проверяется повторно в P2.3.
[Отчёт P2.2](../reports/2026-11-21T143147Z_panel-read-http.md)

В новом проходе сценарий запускает HTTP-процесс в одном временном
systemd unit с ограниченным доступом к файловой системе. Сокет IPC
находится вне закрытых каталогов. Перед открытием HTTP-порта тот же
процесс под непривилегированным UID пытается открыть четыре рабочих
файла и продолжает только при отказе. Содержимое файлов не читается.
Временные unit, порт, каталог и сокет удаляются по завершении.
Установка пакета, правки конфигурации и перезапуски XGW и Xray для
этой проверки не требуются. [Профиль systemd](../../packaging/panel-read-hardening.conf)

## 1. Запуск

Выполни блок как пользователь рабочей сессии XGW. При необходимости
подтверди sudo с `sudo -v` в интерактивном терминале. Если pytest
установлен отдельно, заранее задай абсолютный путь `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=95aeaa496e080a6374168909f1fbd606c7462a88
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_panel_read_http_lab.sh" | bash -s -- "$CODE"
BASH
```

Сценарий печатает путь приватного каталога в `Private run`. Временный
unit использует уникальное имя и `RuntimeMaxSec=40s`. При ошибке запуска
сверь обезличенный исход `systemd-run`, статус окончания unit и
результат заключительной проверки. Затем опубликуй отчёт.

## 2. Критерии

| Этап | Что записать |
|---|---|
| `PINNED`, `BASELINE_OK`, `CONTRACT_TESTS_RC` | SHA, версия Ubuntu, ядро и версия systemd (`systemctl --version`). Обе службы активны, исходный off/off fresh/matched, HTTPS 200, число passed/failed/skipped. |
| `http_unsandboxed_snapshot` | Доступность снимка для того же UID вне временного unit. Это контрольный замер, оба булевых значения допустимы. |
| `http_sandbox_files_denied`, `http_mount_namespace` | HTTP-процесс не смог открыть конфигурацию, рабочий снимок, токен и базу. Его пространство имён монтирования отдельно от пространства root-чекера. |
| `http_privileges`, `socket_permissions` | Непривилегированный UID, только собственная группа, все маски capabilities нулевые, `NoNewPrivs=1`. Сокет IPC root 0660. |
| `http_anonymous`, `http_wrong_key`, `http_duplicate_authorization`, `http_other_origin`, `http_duplicate_host`, `http_post`, `http_only_read_route` | Все отказы совпали с P2.2. Не прошедшие HTTP-проверки запросы не читали IPC. |
| `allowed`, `http_head`, `ISOLATED_HTTP_STATUS_MATCH`, `http_unavailable`, `http_recovered` | GET и HEAD вернули 200. Пять полей совпали со штатной панелью. При отказе IPC — 503, после восстановления — 200. |
| `http_unit_stopped`, `http_cleanup`, `socket_cleanup`, `TOOLS_REMOVED`, `GATEWAY_UNCHANGED` | Временные unit, порт, сокет и root-каталог закрыты или удалены. Службы в исходном состоянии, оба PID и три контрольных файла совпали, off/off fresh/matched сохранён, HTTPS 200. |

При сбое запиши последний прошедший этап и код первой ошибки. Если
исходный режим отличается, оставь его как есть и укажи `NOT_RUN`
для живого прогона. В отчёте достаточно агрегированных значений и
имён этапов. PID, хэши, приватные пути, адреса, URL, ключи и cookie
остаются на машине.

## 3. Автоматическая публикация

Создай один обезличенный Markdown-отчёт, задай его абсолютный путь
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
PUB=$(mktemp -d "$HOME/xgw-panel-sandbox-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-read-sandbox.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre panel read sandbox acceptance'
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
