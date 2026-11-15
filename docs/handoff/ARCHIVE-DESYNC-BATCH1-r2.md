# GLM 5.3 Flash — батч 1, повтор r2: установка после исправления сохранённой стратегии

- target_os: **Ubuntu 24.04 LTS** (уточнение владельца; прежние упоминания 26.04 не эталон).
- base_commit: **48f7ebae15096c40aaa4b82b7f3b19488ab24dd3**, gui-light.
- delivery_branch: **integration/zapret2-batch1**.
- gui_base_commit: **7c20f59023ec39e5c5ce4606767ea915c3b91f64**, freepool.
- code_commit: коммит этого NEXT_STEP в delivery_branch; вычисли командой ниже и закрепи.
- report: `docs/reports/YYYY-MM-DD_desync-batch1-r2.md` в delivery_branch.
- scope: **только T01 + T02**. T03–T07 и сетевые эксперименты здесь не выполнять.

Ты выполняешь команды, читаешь журналы, запускаешь GUI и проверяешь экран сама через vision.
Не поручай владельцу запуск скриптов. Нет терминала/sudo/GUI — запроси соответствующий доступ.
Один связный проход: проверка, установка с откатом, испытания, восстановление при проблеме,
автоматическая публикация отчёта и разрешённых хотфиксов. Никакого отдельного подтверждения
для commit/push отчёта не требуется. Не публикуй токены, подписки, конфиги или полный status.json.

## Что изменилось после первого отчёта

Сначала прочитай `docs/reports/2026-11-15_desync-batch1.md` (48040ea) и fixture-хотфикс
0a4b664, уже включённый в ветку. В том проходе apply не выполнялся: рабочий backend и GUI
остались прежними. Теперь известная стратегия `hostfakesplit_md5` сохраняется при mode=off
в обоих валидаторах, без подстановки multisplit. Включение её в selective/compare и режим
standalone пока запрещены. Исправлено также старое ожидание `pin` в тесте free_pool;
оно не меняет поведение приложения. Эти изменения требуют повторной приёмки на Ubuntu.

Не удаляй и не редактируй legacy-zapret2 в рабочем panel.json для обхода проверки.
Не используй payload, manifest и backup от 557e515: теперь меняется также `zapret2.py`.
Пройди инструкции заново с новым CODE и новыми каталогами. Старые материалы оставь до
закрытия приёмки. Новый manifest должен иметь **8 строк backend или 10 с GUI**.
Старый отчёт не перезаписывай; результат повторного прохода публикуй как `*-r2.md`.

## 1. Получи закреплённый код

В существующем репозитории, от обычного пользователя. Команды — Bash на Ubuntu, НЕ Windows:

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
git fetch origin \
  refs/heads/integration/zapret2-batch1:refs/remotes/origin/integration/zapret2-batch1 \
  refs/heads/freepool:refs/remotes/origin/freepool
BASE=48f7ebae15096c40aaa4b82b7f3b19488ab24dd3
GUI_BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
DELIVERY=origin/integration/zapret2-batch1
CODE=$(git log -1 --format=%H "$DELIVERY" -- docs/handoff/NEXT_STEP.md)
test -n "$CODE"
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-desync-b1.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
printf '%s\n' "$BASE" "$CODE" "$GUI_BASE" > "$D/revisions.txt"
git diff --stat "$BASE" "$CODE" > "$D/change-stat.txt"
```

Если после CODE уже опубликованы хотфиксы, прочитай их и прежний отчёт до повторного запуска.
Для нового прогона явно запиши новый CODE; не применяй старый план поверх работающего хотфикса.
Прочитай `docs/handoff/DESYNC-CONTRACT-v1.md` и helper перед запуском sudo.

## 2. Подтверди окружение и текущую установку

```bash
cat /etc/os-release > "$D/os-release.txt"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
uname -r > "$D/kernel.txt"
nft --version > "$D/nft-version.txt"
curl --version > "$D/curl-version.txt"
sudo systemctl show xgw.service -p ExecStart -p MainPID -p ActiveState > "$D/service-before.txt"
sudo systemctl cat xgw.service > "$D/service-unit.txt"
sudo cat /usr/local/bin/xgw > "$D/launcher.txt"
PID=$(systemctl show xgw.service -p MainPID --value)
test "$PID" -gt 0
PY=$(sudo readlink -f "/proc/$PID/exe")
"$PY" --version > "$D/python-version.txt"
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=/etc/xgw/config.toml
```

Проверь launcher и ExecStart: PACKAGE/PY/CFG должны соответствовать именно работающему
демону. При другом пути найди его сама по launcher, /proc/PID/cmdline и unit, запиши факты.
Не угадывай package по `python -c import xgw` другого виртуального окружения.
Если ОС не 24.04 — не устанавливай; отчёт BLOCKED_ENV с содержимым ID/VERSION_ID.

Определи бинарник nfqws2 по действующей конфигурации и выполни **только `--version`**.
Если он отсутствует — зафиксируй ABSENT, не скачивай и не собирай новый бинарник.
Проверь наличие HTTP3 в выводе curl, но никаких QUIC-тестов в батче 1 не запускай.
Сними приватно `nft -j list ruleset`, `ip -j rule`, `ip -j route show table all`, PID Xray,
хэши config.toml/panel.json и активность xgw-net/xgw-xray/xgw-singbox.
В публичный отчёт вынеси сравнение, не содержимое сетевых/пользовательских данных.

## 3. Выполни целевые проверки до установки

Используй имеющееся dev-окружение с pytest/ruff. Если его нет — создай отдельное venv в D,
установи pytest/ruff туда, не в системный Python и не в окружение рабочего XGW.

```bash
python3 -m venv "$D/test-env"
"$D/test-env/bin/python" -m pip install pytest ruff
"$D/test-env/bin/python" -m pytest --portable \
  tests/test_desync_schema.py tests/test_zapret2_panel.py
"$D/test-env/bin/python" -m pytest -q \
  tests/test_config.py tests/test_managed.py tests/test_zapret2.py tests/test_nfqws2.py tests/test_panel.py
"$D/test-env/bin/python" -m ruff check \
  src/xgw/desync src/xgw/config.py src/xgw/managed.py src/xgw/daemon.py src/xgw/zapret2.py \
  src/xgw/watch/panel.py src/xgw/watch/zapret2_control.py src/xgw/gui/zapret2.py \
  vpn_ui/xgw/overview.py tests/conftest.py tests/test_desync_schema.py \
  tests/test_zapret2_panel.py tests/test_zapret2.py tests/test_managed.py tests/test_panel.py \
  docs/helpers/desync_batch1_install.py
```

Если Python venv отсутствует, сначала найди существующее dev-окружение. Для установки
python3-venv запроси недостающий sudo-доступ, если его нет. Не обновляй ОС/ядро/сетевые пакеты.
Новый провал тестов не скрывай через skip или ослабление assert.
В r2 ожидается отсутствие прежнего провала free_pool/pin; если он сохранился или появились
другие — разбери до установки. Отдельно запиши результат параметризованного
`test_off_is_original_config_without_starting_anything`: сохранённая hostfakesplit_md5
при off не должна создавать маршрут, вход для проб или запускать обработчик.

## 4. Подготовь неизменяемый payload и резервную копию

В действующей конфигурации mode и engine должны быть off. Если сейчас включён обход,
не выключай его ради установки: остановись перед деплоем и опубликуй BLOCKED_ACTIVE_WORKER.
Отчёт предыдущего прогона утверждал, что engine оставлен off; проверь, не считай это фактом.

```bash
PAYLOAD="/opt/xgw/handoff/desync-batch1-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-batch1-$CODE"
test ! -e "$PAYLOAD"
test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base" "$PAYLOAD/gui_base"
git archive "$CODE" src/xgw docs/helpers/desync_batch1_install.py vpn_ui/xgw/overview.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" src/xgw/config.py src/xgw/managed.py src/xgw/daemon.py src/xgw/watch/panel.py src/xgw/zapret2.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$GUI_BASE" vpn_ui/xgw/overview.py src/xgw/gui/zapret2.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/gui_base"
# git archive сохраняет group-write каталогов; убрать его только в новом payload.
sudo chmod -R go-w -- "$PAYLOAD"
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
sudo "$PY" -I - "$PAYLOAD/code/src" "$CFG" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from xgw.config import load
cfg, warnings = load(sys.argv[2])
assert cfg.zapret2.mode == "off" and cfg.zapret2.engine == "off", "active policy: STOP"
from dataclasses import asdict
from xgw.desync import schema
assert schema.migrate(asdict(cfg.zapret2)) == cfg.desync, "policy was substituted: STOP"
print("new config reader: PASS; policy off; warnings:", len(warnings))
PY
```

Helper проверяет root-владельца и права всех родителей, запрет ссылок, совпадение пяти
существующих backend-файлов с BASE и отсутствие конфликтующих новых файлов. Его отказ —
сигнал разобрать расхождение, а не ослабить проверку. PACKAGE передавай уже разрешённым
через readlink -f: установленный lib может быть root-owned symlink.

Определи frontend по работающему GUI и dispatcher в установленном gui/app.py.
Если принятой версии GUI ещё нет в установленном приложении, оставь GUI пустым и выполни
проверку из полного checkout по §6; результат установки GUI будет NOT_RUN/PREVIEW.

```bash
GUI=
# Только если dispatcher и запущенное приложение подтверждают этот каталог:
# GUI=/opt/xgw/gui/releases/7c20f59023ec39e5c5ce4606767ea915c3b91f64
GUI_ARGS=()
if test -n "$GUI"; then GUI_ARGS=(--gui "$(readlink -f "$GUI")"); fi
sudo "$PY" "$HELPER" prepare --payload "$PAYLOAD" --package "$PACKAGE" \
  --backup "$BACKUP" "${GUI_ARGS[@]}"
```

До prepare закрой окно GUI штатно. Не закрывай терминал исполнителя/канал управления.
При изменённом GUI-base — останови именно его деплой и зафиксируй расхождение; не заменяй
весь GUI или весь backend на freepool. Две накладки не являются полным GUI-дистрибутивом.

## 5. Вооружи откат, примени, проверь

**Никаких `flush ruleset`, очистки conntrack, `xgw disable`, смены маршрутов или профилей.**
Единственное системное действие helper — остановить/запустить xgw.service при замене файлов.
Изначально активный демон восстановится и при независимом таймерном откате. Старые файлы
сохраняются до остановки демона, rollback работает без сети и git.

```bash
sudo systemd-run --unit=xgw-desync-b1-rollback --on-active=20m \
  "$PY" "$HELPER" rollback --backup "$BACKUP"
sudo systemctl is-active xgw-desync-b1-rollback.timer
sudo "$PY" "$HELPER" apply --backup "$BACKUP"
sudo systemctl is-active xgw.service
sudo journalctl -u xgw.service --since '-3 minutes' --no-pager > "$D/journal-after.txt"
```

Не оставляй эту последовательность владельцу: запусти сама. При ошибке apply helper
пытается немедленно вернуть файлы; таймер остаётся дополнительной независимой страховкой.
Если остался сбой или исчез доступ — дождись независимого rollback, переподключись и
сними результаты. При доступном терминале можно выполнить rollback немедленно:

```bash
sudo "$PY" "$HELPER" rollback --backup "$BACKUP"
```

Проверь PID Xray и состояния остальных служб, отсутствие новых сетевых правил и неизменность
пользовательских настроек. Счётчики/динамические наборы могут естественно изменяться;
отличай изменение структуры правил от естественной динамики. Если Xray перезапустился
или поменялся маршрут — откати и сообщи REGRESSION, не продолжай к сетевым экспериментам.

## 6. Проверь API и GUI на реальной машине

Получи `/api/state` существующим авторизованным клиентом/браузером панели. Если используешь
скрипт, прочитай token через `xgw.paths.Paths.from_env().panel_token_file` под sudo и выполни
обычный вход в localhost-панель; не печатай токен, URL входа или полный ответ. Сохрани
приватный JSON в D, в отчёт выведи только перечисленные поля карточки.

Обязательно проверь:

1. `zapret2` присутствует; schema_version=1; fresh=true; policy_matched=true; state=off.
2. `strategy=null`, счётчики null, playback=not_tested. Нет выдуманного успеха видео.
3. После появления нового status.json нет бесконечного pending/legacy_snapshot.
   Это обязательно проверить с исходной сохранённой стратегией при off, без её замены.
4. POST-команды не предлагаются: can_off/can_edit=false; причина видна в GUI.
5. В реальном новом GUI пропало «Нет данных», главный экран и подробная карточка согласованы.
6. Светлая/тёмная темы, узкое окно; текст не обрезан; ошибок/None в подписи стратегии нет.
7. Старый status без policy_key, ошибка worker, отсутствие worker, stale и active проверены
   через фикстуры тестов и отдельное preview GUI, не подменой рабочего status.json/API.
   Явно раздели в отчёте LIVE_OFF и FIXTURE_ACTIVE/ERROR/ABSENT/STALE.

Если GUI не установлен, создай полный checkout принятой версии и наложи два файла:

```bash
git worktree add --detach "$D/gui" "$GUI_BASE"
cp vpn_ui/xgw/overview.py "$D/gui/vpn_ui/xgw/overview.py"
cp src/xgw/gui/zapret2.py "$D/gui/src/xgw/gui/zapret2.py"
python3 "$D/gui/vpn_ui/main_xgw.py" --theme light --native-titlebar
```

Запускай GUI от пользователя графической сессии с существующим PyQt6, не от root.
Отсутствует GUI-доступ — запроси его. Не проси скриншоты у владельца при доступном vision.
Не нажимай центральную кнопку питания и не переключай режимы ради этой проверки.
Для тёмной темы используй штатный выбор темы или повторный запуск с `--theme dark`.

Подтверди миграцию реальных конфигов только чтением/экспортом в D. Не переписывай рабочие
config.toml/panel.json. Проверь flock/права 0600 на временном отдельном panel.json в D
через managed.set_desync; не применяй этот тестовый файл к рабочей службе.
На копии с `mode=off, strategy=hostfakesplit_md5` проверь сохранение стратегии при чтении,
сохранении и повторном чтении; перевод копии в selective/compare должен отклоняться до
записи. На рабочей конфигурации режимы не переключай. Исходные probes и domains должны
сохраниться точно, но не публикуй их. В результатах укажи отдельно DORMANT_LOAD,
DORMANT_PERSIST и UNSUPPORTED_ACTIVATION_REJECTED.

После успешной проверки оставь новый backend и установленные GUI-накладки. Сначала отмени
таймер, убедись, что rollback не запустился, и сверь SHA файлов с manifest:

```bash
sudo systemctl stop xgw-desync-b1-rollback.timer
if sudo systemctl is-active --quiet xgw-desync-b1-rollback.service; then
  printf '%s\n' 'Rollback already running: do not report PASS'; exit 1
fi
sudo "$PY" -I - "$BACKUP" <<'PY'
import hashlib, json, pathlib, sys
backup = pathlib.Path(sys.argv[1])
for row in json.loads((backup / 'manifest.json').read_text()):
    actual = hashlib.sha256(pathlib.Path(row['target']).read_bytes()).hexdigest()
    assert actual == row['new_sha'], 'installed payload differs or rollback executed'
print('installed payload hashes: PASS')
PY
```

Если проверка неуспешна — восстанови helper rollback и только после подтверждения восстановления
отмени таймер. Не удаляй backup/payload до разбора отчёта. Никаких 720p/1080p-прогонов в батче 1:
изменений сетевого движка нет; видео будет обязательным для следующих сетевых батчей.

## 7. Границы хотфиксов

Разрешено: исправить обнаруженный путь запуска по фактическому launcher, совместимость
команды инспекции с установленным systemd, кодировку, опечатку fixture, косметическое
отображение новых статусов. Любой кодовый хотфикс — отдельный commit с причиной и проверкой.

Остановись и откати при: необходимости менять nft/маршруты/метки/очередь; конфликте
политик; неподдерживаемом режиме; несовпадении backend с BASE; изменении смысла fallback;
предложении отключить sandbox/права; необходимости запуска двух worker; неизвестной
схеме установки. Не ослабляй тесты и проверки доверия ради продолжения.

## 8. Автоматическая публикация

Используй `docs/reports/TEMPLATE_desync-batch1.md`. Укажи CODE, фактическую Ubuntu 24.04,
версии, импортируемые пути, PASS/FAIL/NOT_RUN по каждому пункту и оставленное состояние.
Отметь, был ли GUI установлен или проверялся из checkout. Не называй этот батч проверкой
обхода YouTube. Если остановилась раньше, всё равно опубликуй BLOCKED/PARTIAL и причину.

В исходном репозитории создай рабочую ветку отчёта от свежего delivery tip, добавь только
отчёт и разрешённые хотфиксы. Пример (замени дату на фактическую):

```bash
git fetch origin integration/zapret2-batch1
git switch -c glm/desync-batch1-r2-report FETCH_HEAD
git add docs/reports/YYYY-MM-DD_desync-batch1-r2.md
git diff --cached --check
git diff --cached --stat
git commit -m 'docs: report Ubuntu 24.04 desync batch 1 r2 acceptance'
git push origin HEAD:integration/zapret2-batch1
```

Перед commit посмотри staged diff на приватные данные. Не используй `git add .`/force push.
При движении remote перечитай новые коммиты, перенеси только свой отчёт/согласованный
хотфикс на свежий tip и повтори обычный push. Убедись через ls-remote, что commit опубликован.
При отсутствии доступа GitHub запроси его, сохрани локальный отчёт и не заявляй публикацию.

Следующий батч разработчик начинает с чтения этого отчёта и коммитов GLM.
