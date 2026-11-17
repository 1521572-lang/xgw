# T12 — проверка лимита TLS в Selective

Исполнитель — Flash на ThinkCentre с Ubuntu 24.04. Самостоятельно запусти
команды и браузер, проверь экран через vision. Если недоступен терминал,
sudo или GUI, запроси доступ. Flash выполняет опубликованные проверки,
возвращает шлюз и публикует отчёт. Исходники, тесты и скрипты правит Codex.

[Отчёт T12](../reports/2026-11-17_desync-t12-selective-route-evidence.md)
подтвердил сравнение дельт в режиме VPN и корректное отклонение снимков
через смену маршрута. Selective остался в fallback. Для watch-страницы и
CDN отмечены TLS-таймауты 5122 и 5147 мс соответственно. Компактная
страница `/t/terms` получила 57 247 байт за 666 мс. Отдельный лимит TLS
в этом прогоне составлял 5 секунд.

Проверяем код `01379afe2445f49d8406295bfaeb03ed831470ec` поверх установленного
`a8b177f6deec1e2c20c4effef977bf144bdf4f24`. Для двух HTTPS-проб Selective
ожидание TLS увеличено до 10 с в пределах общего срока 12 с для каждой.
CONNECT сохраняет лимит 5 с. Страница требует минимум 16 КиБ, CDN — HTTP 200
или 204. Успех внешнего GET с хоста записывай как контроль доступности.

## 1. Подготовка и тесты

Из чистого checkout, в одном сеансе bash:

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=01379afe2445f49d8406295bfaeb03ed831470ec
BASE=a8b177f6deec1e2c20c4effef977bf144bdf4f24
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-selective-tls.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest -q tests/test_checks.py tests/test_zapret2.py tests/test_zapret2_panel.py \
  tests/test_desync_route_evidence.py
bash -n docs/helpers/t11_management_restore.sh
systemctl show xgw.service xgw-xray.service -p ActiveState -p MainPID
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
df -h /home /var/lib/xgw
```

Используй прежнее окружение с pytest, если он установлен там. При падении
теста или отсутствии среды остановись до установки и запиши причину.
Сверь off/off, отсутствие активного воркера, состояние VPN и VPN-выход
обычного сайта в тестовом браузере. Проверь, что браузер захватывается XGW
и запущен с отключённым QUIC. Открой веб-панель, подготовь приватный профиль
с DevTools и сниппетом плеера. Свежую ссылку CDN получи непосредственно перед
сетевой фазой. Не снимай WAN-дамп.

## 2. Установка двух файлов с независимым возвратом

Установщик сверяет `zapret2.py` и `watch/checks.py` с базой перед заменой.
При несовпадении остановись с BLOCKED_BASE и укажи файл. Для возврата
сохранён свежий panel и хэши конфигов. Таймер включает полный откат через
90 минут. Манифест должен содержать две строки.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PY=/usr/bin/python3
PAYLOAD="/opt/xgw/handoff/selective-tls-$CODE"
BACKUP="/var/lib/xgw/handoff/selective-tls-$CODE"
UNIT=xgw-selective-tls-rollback
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
FILES=(src/xgw/zapret2.py src/xgw/watch/checks.py)
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${FILES[@]}" docs/helpers/desync_batch1_install.py \
  docs/helpers/t11_management_restore.sh | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
sudo chmod -R go-w -- "$PAYLOAD"
sudo "$PY" "$HELPER" prepare --selective-tls --payload "$PAYLOAD" \
  --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$HELPER" "$PANEL" "$UNIT" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback --selective-tls
sudo systemctl is-active "$UNIT.timer"
sudo "$PY" "$HELPER" apply --selective-tls --backup "$BACKUP"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl list-timers "$UNIT.timer" --no-pager
verify_manifest() {
  sudo "$PY" - "$BACKUP" "$1" <<'PY'
import hashlib, json, sys
from pathlib import Path
rows = json.loads((Path(sys.argv[1]) / "manifest.json").read_text())
assert len(rows) == 2
for row in rows:
    path = Path(row["target"])
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == row[sys.argv[2] + "_sha"], path
    print(path.name, actual)
PY
}
verify_manifest new
```

При сбое prepare сохрани сведения и проверь старую версию. Если apply начался,
выполни rollback из `4. Не переиспользуй созданные каталоги при повторной
установке. Перед включением Selective захвати блокировку и отметь начало сетевой
фазы. Повтори контроль VPN после установки.

```bash
LOCK_ROOT=${XDG_RUNTIME_DIR:-$HOME}
exec 9>"$LOCK_ROOT/xgw-t09-live.lock"
flock -n 9
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

## 3. Пробы и повтор замера медиа

1. Через веб-форму при off сохрани `multisplit`, домены из
   [TЗ r3, `4](T11-ZAPRET2-SELECTIVE-R3.md#4-selective-и-две-https-пробы), интервал
   проверки 120 с, HTTPS-проверку и две ссылки. Первая —
   `https://www.youtube.com/t/terms`, вторая — свежая
   `https://<CDN>.googlevideo.com/videoplayback?...` из DevTools тестового Chrome.
   Обе ссылки заполняются одновременно. Для CDN укажи контрольный HTTP и время
   из отдельного запроса, если он уже выполнен. Подписанную ссылку не печатай.
2. Включи Selective кнопкой, дождись свежего снимка с этой ревизией.
   В течение 120 с зафиксируй первый итог: state, reason и обе строки
   `evidence.transport_probes`. Нужны phase, kind, elapsed_ms, http,
   connect_http и bytes. Проверь клиентское правило и обычный VPN-выход.
   Если CDN снова не проходит, выключи Selective и разрешён один повтор
   с той же страницей и одной новой свежей CDN-ссылкой. Если после повтора
   фаза active не достигнута, верни шлюз и отметь дальнейшие шаги NOT_RUN.
3. Для отчёта различай результаты:
   - Для успешной пробы запиши общую длительность, которая включает TLS и HTTP.
     По общей длительности нельзя определить время рукопожатия.
   - При повторном `phase=tls/kind=timeout` сопоставь elapsed с бюджетами
     10/12 с. Продолжение отказа подтверждает, что одного изменения лимита
     недостаточно. Не меняй сетевые правила или стратегию во время теста.
   - Если обе пробы прошли, `active/youtube_transport_ok` и клиентское правило
     подтверждены, выполни [T12 `3](T12-SELECTIVE-ROUTE-EVIDENCE.md#3-дельты-и-подтверждение-маршрута)
     с функциями snap/delta из этого сеанса. Нужно ≥150 с пригодного 720p
     с одновременным VPN-контролем, CDP и наблюдением NFQUEUE. Если по таймеру
     осталось ≥35 минут, выполни 15+5 минут с перемоткой, отдельными дельтами
     и контролем. Сохрани поля отклонённых снимков. При неоднозначной привязке
     медиа оставь `MEDIA_PATH=PARTIAL`.

## 4. Возврат и отчёт

Выключи режим кнопкой. Проверь rule=false, off/off, отсутствие очереди и
работу нового VPN-сеанса. Если код прошёл проверку и обе пробы завершились,
`accept` восстанавливает исходный panel и оставляет два файла. Если тест
не подтвердил работу Selective или обнаружил регрессию, `rollback` возвращает
и прежние файлы. Выбери одну команду.

```bash
# При принятии:
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" accept
# При откате вместо accept:
# sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback --selective-tls
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

После сверки манифеста (`new` для accept, `old` для rollback), панели и VPN
останови таймер через `sudo systemctl stop "$UNIT.timer"`. Оставь не менее
10 минут на возврат. Если таймер сработал, проверь `restore-completed`,
манифест old и конечное состояние. Запиши UTC начала и окончания фаз.

Опубликуй только отчёт, включая блокеры. Укажи SHA, испытанные лимиты, фазу
и длительность каждого отказа, статус базового VPN, принятые дельты,
MEDIA_PATH, итог просмотра и фактический возврат. URL, IP, HAR и конфиги
остаются приватными.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t12-selective-tls-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t12-selective-tls.md"
# Заполни REPORT фактическими результатами.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify Selective TLS timing on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке выполни fetch/rebase и обычный push. Сверь удалённый SHA и сообщи
ссылку на отчёт и состояние шлюза.
