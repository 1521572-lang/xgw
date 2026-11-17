# T11 — приёмка веб-обзора zapret2 на ThinkCentre

Ubuntu 24.04 LTS. Проверь вход в панель, новую страницу `/zapret2`, совпадение с
состоянием шлюза, журнал и читаемость. Эта приёмка касается обзора. Управление
режимами, импорт стратегий и запуск тестов будут проверены с их реализацией.
Прочитай [план T11](T11-ZAPRET-MANAGER-UI.md) и
[отчёт Selective](../reports/2026-11-17_desync-selective-youtube-transport.md).

Исполнитель сама запускает терминал, браузер и проверки через vision. Если
недоступен терминал, sudo или браузер, запроси доступ. Опубликуй частичный
отчёт и точное состояние машины при любом блокере.

## 1. Подготовка и установка

До записи проверь свободное место, стабильность рабочего VPN и статус
администратора по растущему WAN-файлу. Последний отчёт отметил 5 ГБ и 96 %
занятого раздела. Новый захват этому тесту не нужен. Положения off/off и
исходные хэши конфигов нужны для сверки после установки. Для UI не нужно
переключать маршруты или изменять настройки владельца.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
BASE=$(git rev-parse f59ebab)
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-t11-web.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest -q tests/test_panel.py::test_zapret2_overview_uses_panel_session_and_limits_state
```

Для установки используй [схему T05 с таймером](T05-SYNACK.md#установка-четырёх-файлов-и-независимый-возврат)
и флаг `--zapret2-web` во всех командах helper, включая restore.sh. Убедись,
что пути PACKAGE, PY, CFG и PANEL взяты из фактической установки. Это overlay
только для HTTP-панели и её ресурсов. Базовыми являются установленные
`watch/panel.py` и `ui/index.html`. При незнакомых байтах объясни блокер вместо
перезаписи. Если файл журнала `desync/event_socket.py` уже установлен, сравни его
с базой. Если его нет, helper создаст и при rollback удалит его.

```bash
BASE_FILES=(src/xgw/watch/panel.py src/xgw/ui/index.html)
EVENT_FILE=src/xgw/desync/event_socket.py
FILES=("${BASE_FILES[@]}" "$EVENT_FILE" src/xgw/ui/zapret2.html
       src/xgw/ui/zapret2.css src/xgw/ui/zapret2.js
       src/xgw/ui/zapret2.LICENSE.txt src/xgw/ui/zapret2.NOTICE.txt)
UNIT=xgw-zapret2-web-rollback
PAYLOAD="/opt/xgw/handoff/zapret2-web-$CODE"
BACKUP="/var/lib/xgw/handoff/zapret2-web-$CODE"
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${FILES[@]}" docs/helpers/desync_batch1_install.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
if sudo test -e "$PACKAGE/desync/event_socket.py"; then
  BASE_FILES+=("$EVENT_FILE")
fi
git archive "$BASE" "${BASE_FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
```

Сохрани panel и исходные SHA, заведя возврат до apply. Используй 25-минутный
таймер и оставь маркер `network-test-started` отсутствующим, поскольку UI
приёмка не меняет маршруты. Сверь файлы, живой VPN и панель после apply.

## 2. Проверки в действующей панели

1. В приватном окне открой `/zapret2`. Должна открыться существующая форма
   входа, а `GET /api/zapret2/overview` до входа должен вернуть 401. Проверь
   чужой Host через локальный HTTP-запрос и ожидай 403. После штатного входа
   открой ссылку zapret2 на главной. Проверь заголовки CSP и отсутствие запросов
   на внешние ресурсы. Сессию, токен и исходные файлы конфигурации не публикуй.
2. Сравни `/api/zapret2/overview` и карточку `zapret2` в `/api/state`, взятые
   со свежим снимком. Сверь режим, активную и настроенную стратегии, домены,
   наблюдение HTTPS, проверку VPN и неизвестные счётчики. В off/off интерфейс
   не должен объявлять обход активным. Потерю сети для вкладки проверь через
   DevTools Offline: значения текущего состояния должны погаснуть, а после
   возврата сети восстановиться. Проверь, что скрытая вкладка не опрашивает
   шлюз. Сверь статус с настоящим Proton GUI.
3. Проверь журнал. При отсутствии записей ожидается «Событий пока нет», а
   недоступный или устаревший журнал обозначен отдельно. HTTP-тест из подготовки
   проверяет порядок, предел 16 и удаление идентификатора политики. Для
   существующих живых записей сверяй очередь, фазу и поколение с локальным
   статусом. Остановка сетевого воркера для проверки журнала не требуется.
4. Через vision оцени обычное окно и ширину около 390 px. Проверь светлую, тёмную
   и системную темы, сохранение темы после обновления, переходы по трём секциям,
   клавиатурный фокус и отсутствие горизонтального обрезания. Сделай пару
   обезличенных снимков. Проверь, что главная панель, серверы и штатный VPN
   по-прежнему работают.

## 3. Возврат и публикация

Если приёмка успешна, оставь файлы и проверь исходный panel и конфиги. При
регрессии запусти restore.sh из шага установки с `rollback`.
Проверь состояние служб, версии файлов, off/off, очередь и VPN. После сверки
останови таймер. Укажи точный SHA, результат по каждому пункту, решение об
установке или rollback и доступность дальнейших проверок.

```bash
sudo sha256sum -c "$D/config-before.sha256"
# Сверь службы и рабочий VPN, затем останови таймер.
sudo systemctl stop "$UNIT.timer"
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/zapret2-web-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-zapret2-web.md"
# Сама запиши REPORT, включая частичный результат или блокер.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: verify XGW zapret2 web overview on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке сделай fetch, rebase и обычный push.
