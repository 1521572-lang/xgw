# T12 — источник проб Selective и стабильность при перепроверках

На ThinkCentre с Ubuntu 24.04 проверь `601238ef053447e1287be918864f8c839e1a3cf4`.
В [отчёте T12 TLS](../reports/2026-11-17_desync-t12-selective-tls.md) обе стартовые
пробы успешны, но в интервале 170 с произошёл fallback. Отчёт называет
`/t/terms` при старте и `/watch` при отказе. Это различие пока не подтверждено
данными контроллера. Новый код показывает тип сохранённой страницы и тип
проверенной страницы с временем запуска запроса. В форме можно явно
подставить короткую страницу условий YouTube.

Flash выполняет тесты, установку, работу с браузером и vision, возврат и
публикацию отчёта. При недоступности терминала, sudo или GUI запроси доступ.
Код, тесты и установщик меняет Codex. URL проб, токены и полные настройки
остаются в приватном каталоге машины.

## 1. Проверки до установки

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=601238ef053447e1287be918864f8c839e1a3cf4
R3=a8b177f6deec1e2c20c4effef977bf144bdf4f24
TLS=01379afe2445f49d8406295bfaeb03ed831470ec
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git merge-base --is-ancestor "$TLS" "$CODE"
D=$(mktemp -d "$HOME/xgw-selective-recheck.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest -q tests/test_zapret2.py tests/test_zapret2_panel.py \
  tests/test_zapret2_management.py tests/test_desync_route_evidence.py
node --check src/xgw/ui/zapret2.js
bash -n docs/helpers/t11_management_restore.sh
systemctl show xgw.service xgw-xray.service -p ActiveState -p MainPID
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Если pytest установлен в прежнем dev-venv, используй его Python. При исходном
отличии от off/off запроси окно проверки. Перед установкой открой веб-панель
и подготовь отдельный Chrome с отключённым QUIC, захватом XGW и DevTools.
На VPN проверь открытие ролика и отдельного контрольного сайта, локально
запиши его VPN-выход. Свежий подписанный адрес CDN нужен перед запуском опыта.
При сбое тестов или отсутствии среды запиши блокер до установки.

## 2. Установка четырёх файлов и возврат

База для `zapret2.py` — слой TLS. `watch/zapret2_control.py`,
`ui/zapret2.html` и `ui/zapret2.js` взяты из r3. `watch/checks.py` сверяется
с принятой версией TLS. Любое несовпадение байтов — BLOCKED_BASE, с названием файла.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PY=/usr/bin/python3
PAYLOAD="/opt/xgw/handoff/selective-probe-info-$CODE"
BACKUP="/var/lib/xgw/handoff/selective-probe-info-$CODE"
UNIT=xgw-selective-probe-info-rollback
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
LOCK_ROOT=${XDG_RUNTIME_DIR:-$HOME}
exec 9>"$LOCK_ROOT/xgw-t09-live.lock"
flock -n 9
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" src/xgw/zapret2.py src/xgw/watch/zapret2_control.py \
  src/xgw/ui/zapret2.html src/xgw/ui/zapret2.js docs/helpers/desync_batch1_install.py \
  docs/helpers/t11_management_restore.sh | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$R3" src/xgw/watch/zapret2_control.py src/xgw/ui/zapret2.html \
  src/xgw/ui/zapret2.js | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$TLS" src/xgw/zapret2.py src/xgw/watch/checks.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/base"
sudo chmod -R go-w -- "$PAYLOAD"
sudo cmp "$PAYLOAD/base/src/xgw/watch/checks.py" "$PACKAGE/watch/checks.py"
sudo "$PY" "$HELPER" prepare --selective-probe-info --payload "$PAYLOAD" \
  --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$HELPER" "$PANEL" "$UNIT" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback \
  --selective-probe-info
sudo systemctl is-active "$UNIT.timer"
sudo "$PY" "$HELPER" apply --selective-probe-info --backup "$BACKUP"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl list-timers "$UNIT.timer" --no-pager
verify_manifest() {
  sudo "$PY" - "$BACKUP" "$1" <<'PY'
import hashlib, json, sys
from pathlib import Path
rows = json.loads((Path(sys.argv[1]) / "manifest.json").read_text())
assert len(rows) == 4
for row in rows:
    path = Path(row["target"])
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == row[sys.argv[2] + "_sha"], path
    print(path.name, actual)
PY
}
verify_manifest new
```

При сбое prepare сохрани имя файла и проверь прежнюю установку. Если сбой
после начала apply, выполни возврат `5. Подтверди VPN и панель после замены.

## 3. Форма, запуск и повторные пробы

1. При off включи в форме «HTTPS-проверка YouTube и CDN». Проверь, что
   подстановка страницы появляется только с этой опцией и скрывается при
   удалении адресов. Нажми кнопку. Она заполняет поле страницы без отправки
   формы и переводит фокус в поле CDN. Сохрани комплект `multisplit`,
   [шесть доменов r3](T11-ZAPRET2-SELECTIVE-R3.md#4-selective-и-две-https-пробы),
   интервал 120 с и свежую CDN-ссылку. Проверь, что форма показывает
   «Страница условий», API `youtube_probe_page_kind=terms`, а до запуска
   `transport_probes={}`. Проверь читаемость на 390 px и отсутствие
   подписанной ссылки в GET/ответах POST.
2. Перед нажатием кнопки Selective зафиксируй исходный VPN и таймер:

   ```bash
   sudo systemctl is-active "$UNIT.timer"
   sudo touch "$BACKUP/network-test-started"
   snap() {
     sudo env PYTHONPATH="$PYTHONPATH" python3 -m xgw.desync.route_evidence snapshot >"$D/$1.json"
   }
   delta() {
     python3 -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"
   }
   snap vpn-before
   ```

3. Включи Selective и в течение 120 с зафиксируй verdict, ревизию, PID
   воркера и клиентское правило. На API `/api/zapret2/overview` проверь
   `evidence.transport_probes.page.page_kind=terms` и
   `page.started_at`, `cdn.started_at`, если CDN запускался. Сохрани их
   локально вместе с UTC и выводом о маршруте. Повторная успешная проба
   должна показать новое время при той же ревизии и том же типе страницы.
   Следи за состоянием при неизменных настройках до двух перепроверок
   либо до первого fallback. Параллельно запускай видео и замеры `4.
4. При fallback сразу запиши state/reason, ревизию, старое и новое время
   проб, страницу, её результат и состояние журнала/воркера. Если есть
   `worker_down` без свежей строки HTTPS, используй код worker_down как
   отдельное наблюдение. Изменение PID после fallback само по себе не
   устанавливает первопричину. Проверь новое подключение через VPN.
   Разрешён один повтор после off только при отказе CDN, со свежим CDN
   и той же страницей условий. При другом отказе заверши сетевую фазу.

## 4. Видео и дельты

Используй [T12, `3](T12-SELECTIVE-ROUTE-EVIDENCE.md#3-дельты-и-подтверждение-маршрута)
для ≥150 с пригодного 720p с одновременным контролем VPN. В начале, сразу
после каждой перепроверки и в конце связывай UTC, started_at, PID и
клиентское правило со снимками дельт. Сохрани хотя бы одну короткую пару
внутри стабильного окна с новой передачей CDN. Простой рост позиции в
буфере не подтверждает сетевую передачу. Используй свежие запросы CDP,
сравни прирост соответствующего правила NFQUEUE и VPN-выход контрольного
сайта. При разрыве или отсутствии счётчиков отметь MEDIA_PATH=PARTIAL.

Если два повторных обновления успешны, короткий просмотр завершён и
до возврата ≥35 минут, проведи живой просмотр 15 минут, перемотку минимум
на 6 минут и ещё 5 минут в 720p со снимками по фазам. При истечении CDN
или fallback укажи время, фазу и активный маршрут. Паузы и просмотр из
предзагруженного буфера отмечай отдельно. Оставь 10 минут на возврат.

## 5. Выключение, возврат и публикация

Выключи Selective кнопкой, проверь свежий off, закрытие прямого правила и новый
сеанс YouTube через VPN. При исправной форме, диагностике и возврате
используй accept. При регрессии кода используй rollback. Отдельно укажи,
если стабильность Selective не подтверждена.

```bash
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" accept
# При регрессии вместо accept:
# sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback --selective-probe-info
sudo sha256sum -c "$BACKUP/config-before.sha256"
verify_manifest new  # old при rollback
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Проверь off/off, VPN и доступность панели. Только после сверки останови таймер
`sudo systemctl stop "$UNIT.timer"`. При срабатывании таймера проверь
restore-completed и манифест old. При потере терминала пути есть в
restore-location.txt, PY=/usr/bin/python3. При сбое возврата опиши состояние
и запроси доступ для диагностики.

Публикуй только новый обезличенный отчёт даже при блокере. Приведи SHA,
PASS/FAIL/BLOCKED/NOT_RUN по шагам, UTC, тип страницы и время каждой попытки,
ошибку пробы или worker_down, ревизию, дельты, MEDIA_PATH, просмотр и конечное
состояние. Сырые снимки и ссылки оставь приватно.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t12-selective-recheck-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t12-selective-recheck.md"
# Заполни REPORT по фактам, включая блокеры.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify Selective probe rechecks on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке выполни fetch/rebase и обычный push. Сообщи ссылку на отчёт
и фактическое состояние машины.
