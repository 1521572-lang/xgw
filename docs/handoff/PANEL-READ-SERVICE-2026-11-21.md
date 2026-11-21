# ThinkCentre — повторная приёмка запуска статуса через systemd, r2

**Ubuntu 24.04 LTS.** Flash сама выполняет готовый сценарий и
публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, сессии установленной панели или GitHub запроси
доступ и продолжи сама. Код и команды подготовлены Codex.

В P2.4 прошли 97 тестов. Штатная логика cookie, одноразовый допуск
и IPC v2 приняты на живом шлюзе. Изолированный процесс работал
только через AF_UNIX, восстановление после отказа прошло.
[Отчёт P2.4](../reports/2026-11-21T162144Z_panel-read-session.md)

В первом P2.5 живая проба прошла полностью. Читатель стартовал за
664 мс и после остановки повторно запустился с новым PID.
Контрактный набор дал 196 passed и 7 failed, из них 5 воспроизвелись
на родительском коммите. В r2 у читателя `/run` явно закрыт для
записи. Тест группы Xray проверяет обе разрешённые группы демона,
отсутствие членства читателя в `xray` и недоступность каталога её API.
Тесты установки приведены к действующим контрактам переустановки,
смены поколения sing-box и восстановления DAC. Набор также включает
прямую проверку переключения поколения и отказа неисправного моста.
[Первый отчёт P2.5](../reports/2026-11-21T164610Z_panel-read-service.md)

Кандидат P2.5 добавляет системную учётную запись читателя и два
unit-файла. systemd открывает Unix-сокет при запуске XGW, а читатель
стартует, когда доверенная панель впервые запрашивает пять полей.
Панель обслуживает IPC в своём жизненном цикле. Испытание поднимает
рядом временную панель через реальный `Panel.start()` и проверяет
активацию на живом снимке. Для испытания используется существующая
системная учётная запись `daemon` и временные unit с теми же
ограничениями. Проверки установки, повторной установки и удаления
выполняются в изолированных тестах. Действующий пакет, настройки,
учётные записи, правила и службы шлюза сохраняются.

## 1. Запуск

Выполни блок как пользователь рабочей сессии XGW. При необходимости
подтверди sudo через `sudo -v` в интерактивном терминале. Если pytest
установлен отдельно, заранее задай абсолютный `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=b614174b0dfc550c95bbabfc7f6c2a2b556a4f8d
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_panel_read_http_lab.sh" | bash -s -- "$CODE"
BASH
```

`Private run` указывает приватный каталог. Сценарий проверяет три
файла служб, запускает контрактные тесты, создаёт временные unit
и проводит пробу. Страховка reader — `RuntimeMaxSec=60s`, внешний
таймаут — 75 секунд. Сценарий останавливает только временные unit.

## 2. Критерии

| Этап | Что записать |
|---|---|
| `PINNED`, `BASELINE_OK`, `CONTRACT_TESTS_RC`, `SERVICE_FILES_VERIFIED` | SHA, Ubuntu, ядро, systemd, исходный off/off fresh/matched и HTTPS 200. Для приёмки нужен код 0 у полного набора. Запиши число passed/failed/skipped и результат проверки файлов служб. |
| `service_dormant`, `stale_ipc_recovered` | systemd открыл сокет root 0600, reader не запущен. Новый IPC заменил брошенный сокет, получил root 0660 и GID читателя. У процесса проверки нет CAP_CHOWN, CAP_DAC_OVERRIDE и CAP_DAC_READ_SEARCH. |
| `panel_legacy_routes` | Анонимный запрос 401 оставил reader незапущенным. Временная ссылка входа выдала cookie. HTML панели и полный обзор вернули 200. |
| `cold_activation_ms`, `http_privileges`, `http_mount_namespace`, `ISOLATED_HTTP_STATUS_MATCH` | Первый авторизованный запрос запустил reader и получил пять полей, равных статусу штатной панели. Запиши время и признаки изоляции без PID и адресов. |
| `reader_run_readonly` | У `/run` в пространстве монтирования фактически запущенного читателя есть флаг `ST_RDONLY`. Проверка статуса через IPC продолжает работать. |
| `backend_recovered`, `worker_reactivated` | При перечитывании настроек сокет сохранён. Имитация отказа дала 503, после восстановления получен 200. Остановка временного reader и следующий запрос дали 200 с новым PID reader. |
| `candidate_cleanup`, `TOOLS_REMOVED`, `GATEWAY_UNCHANGED` | Временный доверенный вход остановлен, временные сокеты, unit и root-каталог убраны. XGW и Xray активны, PID и три контрольных файла совпали, off/off fresh/matched и HTTPS 200 сохранились. |

При сбое запиши последний успешный этап, код первой ошибки и
результат очистки. Если упали контракты, укажи все имена тестов и
их короткие ошибки, результат живой пробы запиши отдельно. При
исходном режиме, отличающемся от off/off, укажи `NOT_RUN` для
живого прогона и сохрани наблюдаемый режим.
Оставь на машине хэши, PID, URL, приватные пути и данные входа.

## 3. Автоматическая публикация

Укажи абсолютный путь к отчёту в `REPORT_SRC` и сама выполни блок.
При параллельном обновлении ветки он один раз переносит коммит
поверх свежего HEAD. Верни ссылку на проверенный коммит отчёта.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-service-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-read-service-r2.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre panel status service acceptance r2'
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
