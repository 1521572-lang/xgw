# T03 — приёмка общего управления очередью на Ubuntu 24.04

Ветка `integration/zapret2-batch1`. База разработки `077dc52`, базовый слой установленного
backend `4f53495`. Отчёт `docs/reports/YYYY-MM-DD_desync-t03.md`.

Исполнитель сам запускает команды, проверяет GUI через vision и публикует отчёт на GitHub
после завершения, включая случаи блокировки. При отсутствии терминала, sudo или GUI запроси
доступ. Прочитай [отчёт r1](../reports/2026-11-15_desync-hypotheses-r1.md) и
[план](DESYNC-ROADMAP.md). В этом проходе измеряется переключение обработчиков.
Для короткого браузерного контроля используй известный рабочий `hostfakesplit-md5`, если
условия прямого маршрута уже проверены. GET к YouTube SABR для приёмки T03 не нужен.

## Подготовка

В чистом checkout, Bash, обычный пользователь:

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
TIP=$(git rev-parse FETCH_HEAD)
CODE=$(git log -1 --format=%H "$TIP" -- docs/handoff/NEXT_STEP.md)
git merge-base --is-ancestor 077dc52 "$CODE"
D=$(mktemp -d "$HOME/xgw-desync-t03.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
uname -r
nft --version
```

Если после CODE есть относящиеся к T03 хотфиксы, проверь diff и закрепи выбранный SHA в отчёте.
Используй существующее dev-окружение с pytest или создай отдельное. Запусти:

```bash
python3 -m pytest -q --portable tests/test_desync_worker.py tests/test_desync_schema.py tests/test_zapret2_panel.py
python3 -m pytest -q tests/test_nfqws2.py tests/test_zapret2.py tests/test_daemon.py tests/test_ops.py
```

Зафиксируй фактический ExecStart и подтверди пути PACKAGE/PY/CFG. Сверь эффективные режимы
`off/off`, исходные PID, хэши TOML и panel.json, очередь, offload и доступность сети.
Сохрани снимки приватно. Если активен используемый пользователем обработчик, запроси окно
для проверки. Сравни SHA реального nfqws2 и Lua с предыдущим отчётом. В GUI отдельно проверь,
что карточка доступна и показывает исходное состояние.

## Установка и независимый откат

Helper рассчитан на подтверждённые байты установленного слоя. Изменения GUI не входят в
перечень. Если один из исходных файлов отличается, определи его коммит по журналу установки
и git, опиши расхождение. Используй другой установленный baseline только после точного
сопоставления байтов и просмотра diff. Не заменяй несовместимый пакет целиком.

```bash
BASE=4f53495
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
PID=$(systemctl show xgw.service -p MainPID --value)
PY=$(sudo readlink -f "/proc/$PID/exe")
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/desync-t03-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-t03-$CODE"
FILES=(cli.py daemon.py nfqws2.py zapret2.py desync/schema.py watch/zapret2_control.py)
BASE_FILES=()
for file in "${FILES[@]}"; do BASE_FILES+=("src/xgw/$file"); done
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${BASE_FILES[@]}" src/xgw/desync/worker.py docs/helpers/desync_batch1_install.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${BASE_FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
sudo chmod -R go-w -- "$PAYLOAD"
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
sudo "$PY" "$HELPER" prepare --worker-t03 --payload "$PAYLOAD" --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" > "$D/config-before.sha256"

sudo install -m 0700 /dev/stdin "$BACKUP/restore.sh" <<'SH'
#!/bin/bash
set -euo pipefail
py=$1
helper=$2
backup=$3
panel=$4
mode=$5
systemctl stop xgw.service
temp=$(mktemp "$(dirname "$panel")/.xgw-t03-restore.XXXXXXXX")
cp --preserve=mode,ownership -- "$backup/panel.before" "$temp"
mv -fT -- "$temp" "$panel"
if [ "$mode" = rollback ]; then
  "$py" "$helper" rollback --worker-t03 --backup "$backup"
else
  systemctl start xgw.service
fi
if [ -e "$backup/network-test-started" ]; then
  timeout 180 /usr/local/bin/xgw apply --now
fi
SH
sudo systemd-run --unit=xgw-desync-t03-rollback --on-active=30m \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback
sudo systemctl is-active xgw-desync-t03-rollback.timer
sudo "$PY" "$HELPER" apply --worker-t03 --backup "$BACKUP"
sudo systemctl is-active xgw.service
sudo sha256sum -c "$D/config-before.sha256"
```

Проверь семь строк манифеста, новую карточку, свежий статус и исходное `off/off`.
Подтверди, что daemon восстановился, а Xray и доступность HTTPS в норме.
Перед live-фазой создай root-файл `$BACKUP/network-test-started`, перезапусти именно
`xgw-desync-t03-rollback.timer` и сверь дедлайн. Если дедлайн сработал, прекращай прогоны
и сначала проверь восстановление. При ошибке можешь сразу вызвать тот же restore с
аргументом `rollback`. Следи за временем на протяжении всех шагов. Не редактируй другие
настройки параллельно с временным изменением panel.json.

## Проверки живого контроллера

Записывай время, PID демона и обоих unit, queue+peer из kernel, effective profile,
generation в `/run/xgw/status.json` (`zapret2_reservation`) и карточку. Приватный снимок
содержит данные пользователей. В отчёт включай только нужные поля. `generation` относится
к текущему процессу демона. Резервация появляется до готовности. Для готовности сопоставь
MainPID → socket inode в /proc/PID/fd → NETLINK_NETFILTER port ID (Eth=12) →
`/proc/net/netfilter/nfnetlink_queue`. Проверь то же от запущенного xgw.service, поскольку
его права могут отличаться от sudo-терминала.

Меняй только временный объект политики в panel.json через `managed.set_desync` и пользуйся
штатным перечитыванием. Не вызывай `apply --now` посреди PID-тестов: он может перезапустить
демон. Пример переключателя, после сверки реальных путей PY/PACKAGE/CFG:

```bash
set_engine() {
  sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - "$CFG" "$@" <<'PY'
from dataclasses import asdict
from pathlib import Path
import sys
from xgw import config, managed
from xgw.desync import schema
config_path = Path(sys.argv[1])
cfg, _ = config.load(config_path)
policy = schema.migrate(asdict(cfg.zapret2))
policy["selected"]["mode"] = "off"
policy["engine"].update(engine=sys.argv[2], engine_profile=sys.argv[3], engine_offload=False)
policy["runtime"]["engine_queue"] = int(sys.argv[4])
managed.set_desync(managed.path_for(config_path), policy)
actual, _ = config.load(config_path)
assert schema.migrate(asdict(actual.zapret2)) == policy
PY
}
```

1. **Старт engine.** Найди две свободные очереди, предпочтительно текущую 200 и свободную
   соседнюю. Включи `set_engine auto hostfakesplit-md5 200` (подставь свободный номер).
   Дождись подтверждения владельца и состояния active. Если выученный профиль имеет
   приоритет, запиши фактический профиль и не называй его hostfakesplit-md5 без подтверждения.
2. **Повторное чтение без изменений.** Атомарно перепиши идентичные байты panel.json
   с исходным владельцем и правами. Проверь по журналу, что reload прошёл, а PID демона,
   PID engine, queue и generation прежние. Затем измени только queue вызовом `set_engine`
   с другим свободным номером. Проверь, что предыдущий PID остановлен до переназначения,
   а новый владелец подтверждён и generation вырос.
3. **Аварийный выход worker.** Убедись, что цель — только запущенный экспериментальный
   `xgw-nfqws2.service`. Выполни `sudo systemctl kill --kill-whom=main --signal=SIGKILL
   xgw-nfqws2.service` одной командой. Проверь исчезновение прежней очереди и появление
   нового PID и generation после шага watchdog. Проверь краткий контроль HTTPS и API.
4. **Оба направления передачи.** Проверь Engine → Selective или Compare на том же номере
   → Engine → Off. Используй принадлежащий вам или доступный для проверки HTTPS endpoint
   с телом ≥16 KiB. Укажи его домен через `full:`, один URL для selective либо два для
   compare и стратегию `multisplit`. Для изменения policy возьми предыдущий Python-блок,
   замени присваивания полей на `selected.mode/strategy/domains/probe_urls` и
   `runtime.queue_num`; сохрани capture и ограничения из config.load. При несовместимых
   текущих QUIC/proxy settings или отсутствии входа пометь эту строку NOT_RUN и продолжи
   независимые проверки. Для приёмки старта selective достаточно подтверждённого слушателя
   и корректного возврата даже при FAIL пробы. Отдельно проверь готовность маршрута,
   если проба успешна. Два unit не должны работать одновременно. Для compare не требуй
   прямого клиентского маршрута.
5. **Чужая очередь и неудачная остановка.** Основной детерминированный тест выполняется в
   pytest. На шлюзе разрешается повторить проверку занятой очереди только если есть
   выделенный тестовый слушатель и очередь вне прежней политики. Конкретный чужой unit
   не останавливай. При статусе `queue_busy` проверь, что XGW не признал чужой socket
   своим. Failed stop не имитируй путём отключения systemd на рабочем шлюзе.
6. **Восстановление.** Подтверди off, освобождённые очереди и пустую резервацию. Верни
   исходный panel.json и прежние сетевые правила, оставив принятый код только при успешной
   проверке. Для штатного возврата с сохранением кода вызови скрипт с аргументом `accept`.
   Для отката кода — `rollback`. Сверь `sha256sum -c`, offload, API/GUI/HTTPS и очереди.
   После подтверждения останови свой rollback timer. Оставь backup приватным.

Если проверка ownership отдаёт false при доказанном слушателе, сопоставь права и proc из
контекста systemd. Зафиксируй причину. Совместимый хотфикс допустим с повторной проверкой.
Отсутствующие доказательства не подменяй проверкой «занят номер очереди».

## Отчёт и публикация

Укажи CODE и базу установки, версии Ubuntu/kernel/nfqws2, фактический доступ к proc,
результаты переносимых/Linux-тестов, результат каждого шага, цепочку PID/queue/generation,
поведение GUI, исходные и итоговые хэши и факт отката. Временные служебные JSON, адреса
подписок, тело ответов и полный status.json не добавляй в Git.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/desync-t03-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t03.md"
# Заполни REPORT, добавь проверенные хотфиксы отдельными точными путями.
git add "$REPORT"
git diff --cached --check
git diff --cached
git commit -m "docs: report T03 worker lifecycle on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

Если появилось новое изменение ветки, перечитай его и повтори обычный push после rebase.
