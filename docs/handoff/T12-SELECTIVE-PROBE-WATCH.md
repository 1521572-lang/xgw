# T12 — возврат в веб-панель и замер очереди во время HTTPS-пробы

ThinkCentre, Ubuntu 24.04 LTS. Код для проверки `1fc4e69d569bbf583ffeb4e7799ff165741b3cc7`.
Слой `a382971` принят и оставлен на машине. Очистка адресов и клик Selective прошли.
В последнем опыте TLS страницы `/t/terms` завершился таймаутом через 10,1 с.
CDN тогда не проверялась. В новом опыте нужно сопоставить результат HTTPS и
состояние очереди в момент запроса. [Отчёт r2](../reports/2026-11-18_desync-t12-selective-cdn-retry-r2.md).

Flash сама запускает команды, работает с Chrome и vision, восстанавливает шлюз
и публикует технический отчёт. При недоступности терминала, sudo или браузера
запроси доступ. Исходники, тесты и установщик входят в закреплённый коммит.
Сбор ограничен метаданными и счётчиками. Захват пакетов и полный сетевой журнал
Chrome для этого ТЗ не нужны. Подписанные URL и клиентские адреса храни локально.

## 1. Подготовка

В рабочем шлюзе проверь off/off, штатный VPN и панель. Убедись, что оба обработчика
inactive, и что для тестового Chrome выключен QUIC. В отдельной вкладке подготовь
контрольный сайт вне доменов YouTube. В начале запиши его наблюдаемый VPN-выход.
Сетевую фазу начинай только с работающим VPN и перехватом.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=1fc4e69d569bbf583ffeb4e7799ff165741b3cc7
BASE=a382971f162db53a8bd7435f124d591b6a5287fa
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-selective-probe-watch.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
PY=/usr/bin/python3
node --check src/xgw/ui/zapret2.js
bash -n docs/helpers/t11_management_restore.sh
python3 -m pytest -q tests/test_panel.py::test_zapret2_overview_uses_panel_session_and_limits_state \
  tests/test_zapret2_management.py tests/test_desync_route_evidence.py
systemctl show xgw.service xgw-xray.service -p ActiveState -p MainPID
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Для pytest можно взять ранее настроенный dev-venv. При падении проверок
опубликуй блокер из исходного checkout по §5. Для установки нужны точные
байты принятого скрипта панели. Отдельно сверь установленный контроллер с
`a382971`, чтобы сетевой опыт относился к принятому слою.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/selective-web-resume-$CODE"
BACKUP="/var/lib/xgw/handoff/selective-web-resume-$CODE"
UNIT=xgw-selective-web-resume-rollback
OVERLAY=--selective-web-resume
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" src/xgw/ui/zapret2.js docs/helpers/desync_batch1_install.py \
  docs/helpers/t11_management_restore.sh | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" src/xgw/ui/zapret2.js src/xgw/zapret2.py \
  src/xgw/watch/zapret2_control.py | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
sudo chmod -R go-w -- "$PAYLOAD"
sudo cmp "$PAYLOAD/base/src/xgw/zapret2.py" "$PACKAGE/zapret2.py"
sudo cmp "$PAYLOAD/base/src/xgw/watch/zapret2_control.py" "$PACKAGE/watch/zapret2_control.py"
sudo "$PY" "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" \
  --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$HELPER" "$PANEL" "$UNIT" "$OVERLAY" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback "$OVERLAY"
sudo systemctl is-active "$UNIT.timer"
sudo "$PY" "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
verify_manifest() {
  sudo "$PY" - "$BACKUP" "$1" <<'PY'
import hashlib, json, sys
from pathlib import Path
rows = json.loads((Path(sys.argv[1]) / 'manifest.json').read_text())
assert len(rows) == 1
row = rows[0]
path = Path(row['target'])
assert path.name == 'zapret2.js'
actual = hashlib.sha256(path.read_bytes()).hexdigest()
assert actual == row[sys.argv[2] + '_sha']
print(path.name, actual)
PY
}
verify_manifest new
```

Несовпадение байтов до apply — `BLOCKED_BASE` с названием файла. При ошибке после
apply выполни возврат из §5. Подтверди, что панель и VPN работают после установки.

## 2. Возврат в веб-панель

1. Открой `/zapret2` с новой версией JS. Зафиксируй Network с включённым
   Preserve log. Уведи вкладку в фон на 15 с, вернись. Повтори со свёрнутым
   окном и при возврате из истории Chrome. После возврата должен начаться
   GET overview, карточка получает свежие данные без ручного обновления.
   Запиши время до первого GET и до готовой карточки. Пока вкладка скрыта,
   периодических GET быть не должно.
2. Проверь короткий переход в фон, когда GET ещё выполняется. Можно временно
   включить throttling в DevTools только для вкладки панели. Дай запросу
   завершиться или отмениться и вернись. Ожидается свежий GET и отсутствие
   параллельных GET. После проверки выключи throttling.
3. Открой настройки и измени интервал в черновике. Спрячь окно на 15 с,
   вернись, сверив ввод через vision. Черновик и его ревизия сохраняются.
   Скрытие и возврат не отправляют POST. Отмени черновик. Запиши
   `PANEL_RESUME=PASS/FAIL` и условия. При FAIL собери данные Network и выполни
   rollback по §5. При недоступности сценария опиши, какая проверка осталась открыта.

## 3. Захват счётчиков и первая проба

В панели сохрани `multisplit`, шесть доменов из подстановки, интервал 120 с,
опцию HTTPS, страницу `/t/terms` и свежий CDN из DevTools. Повторять всю
приёмку очистки из предыдущего ТЗ не требуется. Проверь off/off и пустой
`blockers.selective`. Очередь в предыдущем раунде была 200. Используй настроенный
номер, если он отличается. Сборщик пишет примерно одну строку в секунду,
останавливается по времени и читает только локальные счётчики и статус.

```bash
sudo systemctl is-active "$UNIT.timer"
sudo touch "$BACKUP/network-test-started"
snap() {
  sudo env PYTHONPATH="$PYTHONPATH" "$PY" -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
delta() {
  "$PY" -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"
}
snap vpn-before
QUEUE=200
sudo -v
sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_probe_watch.py \
  --queue "$QUEUE" --seconds 90 >"$D/start-1.jsonl" &
WATCH_PID=$!
```

Дождись первой строки, нажми Selective в течение 15 с и отметь момент клика в UTC.
При active сразу начни замер по §4, пока сборщик пишет в фоне. При fallback сразу
сделай контрольный HTTPS-запрос ниже. Перед разбором файла или повторным запуском
дождись конца записи командой `wait "$WATCH_PID"`.
Сохрани время проб, ревизию, этап и итог HTTPS из overview. Используй поле
`started_at`, чтобы выделить окно пробы в JSONL. Соотнеси времена начала и конца
состояний, `gate.marked`, `gate.fake`, наличие очереди, `worker_invocation`,
её peer, `outgoing.handle`, прирост пакетов, дропы и очередь в ожидании.
Метрики сравнивай внутри одной жизни воркера при одинаковых peer и handle.
Строка с null означает отсутствие чтения или объекта, числовой ноль — наблюдение.
Записывай отдельно `status_at` и время чтения счётчиков. Снимок демона может
отставать от фактического состояния ядра, а счётчики относятся ко всей очереди.

Если страница или CDN дали TLS-таймаут, после подтверждённого fallback один раз
проверь тот же адрес обычным HTTPS-запросом, пока адрес ещё свежий. Запиши
HTTP-статус, время и известный маршрут запроса. Маршрут браузера или запроса
с хоста обозначь как неизвестный, если он не был подтверждён отдельно. Затем
допустим **один** повтор всего опыта после off с тем же `/t/terms` и свежим CDN,
в отдельный файл `start-2.jsonl`. При отсутствии active на обеих попытках
заверши сетевую фазу и предоставь таблицу. Таймаут при открытом gate, растущих
счётчиках и без дропов локализует проблему дальше по пути только относительно
этих наблюдений. Причину по одному агрегатному счётчику не назначай.

## 4. Если Selective перешёл в active

Используй обычный Chrome, плеер и CDP. В первые 30–60 с сними короткую пару
Xray при свежей передаче CDN и запиши видео вместе с отдельным VPN-сайтом.
В каждой фазе сохраняй локально UTC и фактическое клиентское правило.

Для оценивания пути используй существующие критерии. Нужны свежая передача CDN,
сопоставимая пара Xray, прирост NFQUEUE у того же владельца, наблюдаемый путь
соединения и параллельный VPN-контроль. При недостающих данных укажи конкретный
пробел. [Дельты и подтверждение маршрута](T12-SELECTIVE-ROUTE-EVIDENCE.md#3-дельты-и-подтверждение-маршрута).

Проверь две перепроверки на одной ревизии. Для перепроверок можно запустить ещё
два ограниченных сбора по 90 с, начиная за 25–30 с до ожидаемого времени.
В отчёте укажи `RETRY_LIVE=RECOVERED/FAILED/NOT_OBSERVED/NOT_RUN`
и сохрани результат `first_tls_timeout_ms`, если он появился. Если обе перепроверки
прошли и до отката есть ≥35 минут, проверь 15 минут 720p, перемотку на ≥6 минут
и ещё 5 минут. Через vision проверь экран. Отдельно отметь пригодные секунды,
сетевую активность и паузы. [Телеметрия плеера](YOUTUBE-TELEMETRY.md#замер-в-обычном-chrome).

## 5. Возврат и автоматическая публикация

После сетевой фазы выключи Selective и проверь новый YouTube-сеанс через VPN.
Оставь 10 минут на возврат. При принятой панели выбери accept, при регрессии
выбери rollback. Если таймер уже сработал, проверь старый манифест и
`restore-completed`. Нестабильность TLS оценивай отдельно от обновления панели.

```bash
RESULT=accept  # при регрессии RESULT=rollback
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" "$RESULT" "$OVERLAY"
sudo sha256sum -c "$BACKUP/config-before.sha256"
if [[ "$RESULT" == accept ]]; then verify_manifest new; else verify_manifest old; fi
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Подтверди off/off, VPN, доступность панели и остановку сборщика. После сверки
останови таймер командой `sudo systemctl stop "$UNIT.timer"` и закрой тестовый Chrome.
Пути к возврату записаны в `restore-location.txt`.

Автоматически опубликуй **только обезличенный отчёт**, в том числе при блокере.
Включи SHA, `PANEL_RESUME`, таблицу попыток с UTC и приростом счётчиков,
`RETRY_LIVE`, `MEDIA_PATH`, пригодное время просмотра, VPN-контроль и результат
возврата. В отчёте достаточно обезличенных дельт и факта смены воркера.
Сырые JSONL, адреса CDN и данные сеанса оставь в `$D`.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t12-selective-probe-watch-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t12-selective-probe-watch.md"
test ! -e "$REPORT"
# Заполни файл отчёта по выполненным шагам.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify panel resume and Selective probe counters on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке выполни fetch, rebase и обычный push. Сообщи ссылку и состояние шлюза.
