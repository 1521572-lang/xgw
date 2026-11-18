# T12 — сравнение Selective и штатного WAN на одном IP

ThinkCentre, Ubuntu 24.04 LTS. Код проверки — `f24b25764fdcd9e3c7c2e0414cff9583bfdca0fb`.
В последнем раунде CDN-сокет оставался в `SYN-SENT` при обеих попытках.
Сокет страницы установил соединение. Контрольный HTTPS к тому же CDN-IP
прошёл, но путь запроса остался неизвестен. [Отчёт TCP](../reports/2026-11-18_desync-t12-selective-tcp-evidence.md).

В этом опыте сравниваем TCP одного публичного IPv4 и порта 443. Контрольный
скрипт получает решение ядра для метки Selective с UID Xray и для штатной
метки прямого выхода. Затем открывает один TCP-сокет со штатной меткой,
привязав его к подтверждённому WAN. Таймаут 5 с, HTTP и URL скрипту не нужны.
Поиск маршрута показывает решение ядра для указанных параметров. Для сокета
Selective это оценка без реального исходного порта и состояния соединения.
[Документация ip route](https://github.com/iproute2/iproute2/blob/main/man/man8/ip-route.8.in).

Flash сама запускает скрипты, работает с Chrome и vision, выполняет возврат
и публикует технический отчёт. При недоступности терминала, sudo или GUI запроси
доступ. Скрипты запускаются из checkout. Адреса, конфиги, файлы с метаданными
и секреты остаются локальными. Захват пакетов для опыта не требуется.

## 1. Подготовка

Начни с чистого checkout. Проверь off/off, штатный VPN, панель и неактивные
воркеры. Определи рабочий WAN по настройкам шлюза и реальному uplink.
Выбери IPv4 CDN из локального JSONL прошлого раунда. При недоступности
архива возьми фактический адрес нового CDN-сокета в §2 и используй
тот же адрес в контроле. Достаточно одного выбранного IP за проверку.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=f24b25764fdcd9e3c7c2e0414cff9583bfdca0fb
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-selective-wan.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
PY=/usr/bin/python3
python3 -m pytest -q tests/test_selective_probe_watch.py tests/test_desync_route_evidence.py
bash -n docs/helpers/t11_management_restore.sh
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
sudo cmp "$PACKAGE/zapret2.py" src/xgw/zapret2.py
sudo cmp "$PACKAGE/watch/checks.py" src/xgw/watch/checks.py
sudo cmp "$PACKAGE/ui/zapret2.js" src/xgw/ui/zapret2.js
systemctl show xgw.service xgw-xray.service -p ActiveState -p MainPID
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Для pytest подойдёт ранее настроенный dev-venv. При падении тестов, расхождении
слоя или недоступности WAN опубликуй блокер по §3. Если применяешь старый IP,
выполни один контроль до сетевой фазы. Если используешь новый, пропусти
эту команду до появления наблюдаемого сокета.

```bash
read -r -p 'WAN interface: ' WAN
read -rs -p 'Private previous CDN IPv4 (empty if unavailable): ' OLD_PEER
printf '\n'
wan_control() {
  sudo env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_wan_control.py \
    --wan "$WAN" --peer "$1" "${@:2}"
}
if [[ -n "$OLD_PEER" ]]; then wan_control "$OLD_PEER" >"$D/wan-before.json"; fi
```

Проверь поле `tcp` локально. При `wan_route_unconfirmed` сверь выбранный
интерфейс с настройками и сообщи причину. Такой контроль не отправляет TCP-запрос.
Остальные результаты трактуй по таблице ниже после сравнения IP.

## 2. Один запуск Selective и сравнение маршрутов

Проверь VPN в обычном Chrome. Подготовь свежий CDN-адрес из DevTools того же
браузера с выключенным QUIC. Перед записью настроек установи таймер.

```bash
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
UNIT="xgw-selective-wan-$(date +%s)"
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
BACKUP=$(sudo mktemp -d /var/lib/xgw/handoff/selective-wan.XXXXXXXX)
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 docs/helpers/t11_management_restore.sh "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$PANEL" "$UNIT" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
sudo systemctl is-active "$UNIT.timer"
sudo touch "$BACKUP/network-test-started"
snap() {
  sudo env PYTHONPATH="$PYTHONPATH" "$PY" -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
delta() {
  "$PY" -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"
}
```

1. Сохрани `multisplit`, шесть доменов YouTube, интервал проверки 120 с,
   HTTPS-опцию, `/t/terms` и CDN. Дождись свежей карточки off/off и пустого
   `blockers.selective`. Закрой плеер на момент стартовой пробы. Укажи номер
   очереди из настроек, если он отличается от 200.

   ```bash
   snap vpn-before
   QUEUE=200
   sudo -v
   sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_probe_watch.py \
     --queue "$QUEUE" --seconds 90 --socket-stats >"$D/start.jsonl" &
   WATCH_PID=$!
   ```

2. После первой строки сборщика нажми Selective. Если в окне пробы уже
   различим один CDN-IP, введи его приватно и сними решение ядра в том же
   окне. Для привязки используй время пробы, появление отдельного TCP-сокета
   и его состояние. DNS-адрес браузера сам по себе не подтверждает IP пробы.

   ```bash
   read -rs -p 'Observed CDN IPv4: ' PEER
   printf '\n'
   wan_control "$PEER" --routes-only >"$D/routes-during.json"
   ```

3. При fallback подтверди снятие прямого правила и выключи режим кнопкой.
   Сразу выполни контроль WAN к фактически наблюдавшемуся CDN-IP. Если IP
   определился только после fallback, сохрани время и отметь, что решение
   ядра снималось после переключения. Дождись окончания сборщика командой
   `wait "$WATCH_PID"` перед разбором полной записи. При нескольких
   неоднозначных адресах зафиксируй `WAN_CONTROL=INCONCLUSIVE`.

   ```bash
   wan_control "$PEER" >"$D/wan-after.json"
   unset PEER OLD_PEER
   ```

4. При active сразу сними короткую пару Xray и NFQUEUE с новым медиазапросом
   и параллельным VPN-контролем. Проверь плеер через CDP и vision.
   Используй те же критерии маршрута, что в предыдущих раундах.
   [Дельты и критерии](T12-SELECTIVE-ROUTE-EVIDENCE.md#3-дельты-и-подтверждение-маршрута).

| Результат на одном IP | Что записать |
| --- | --- |
| Контроль WAN подключился, сокет Selective застрял в SYN-SENT | Зафиксируй разницу исходов и интервал между ними. Укажи, совпали ли интерфейс, шлюз, таблица и исходный адрес в двух решениях ядра. Разница исходов сама по себе не устанавливает причину. |
| Оба TCP-соединения истекли | Оба наблюдаемых прямых пути к этому IP отказали. Укажи разницу во времени проверок и итог нового сеанса через VPN. |
| Маршрут для метки Selective отличается | Зафиксируй различие и время замера. Укажи, измерялся ли маршрут во время SYN-SENT. |
| IP различаются или TCP-контроль не готов | `WAN_CONTROL=INCONCLUSIVE` с конкретной причиной. Сравнивай только совпавшие IP. |
| Selective активен | Укажи, подтверждён ли маршрут по паре Xray и свежему медиазапросу. Запиши длительность фактического окна. |

Перед возвратом сохрани режим, причину, стадию пробы, время и socket state,
итог контроля и наличие совпавшего IP. В сводке адрес обозначь буквенным
именем. Не увеличивай число попыток в этом раунде.

## 3. Возврат и публикация

Выключи Selective и проверь новый сеанс через VPN. Оставь не менее 10 минут
на возврат. При срабатывании таймера проверь `restore-completed` и состояние
без повторного запуска скрипта. При блокере до изменения настроек сразу
переходи к публикации.

```bash
sudo /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

После проверки off/off, VPN, панели и хэшей останови таймер
`sudo systemctl stop "$UNIT.timer"`. Закрой тестовый Chrome. Пути для
восстановления записаны в `restore-location.txt`.

Автоматически опубликуй только обезличенный отчёт, включая блокеры.
Приведи SHA, тесты, отметки времени, сопоставление маршрутов, статус TCP,
результаты видео и конечное состояние. Сырые данные оставь в `$D`.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t12-selective-wan-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t12-selective-wan-control.md"
test ! -e "$REPORT"
# Заполни отчёт по фактам, включая блокеры.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify WAN TCP control for Selective on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке выполни fetch, rebase и обычный push. Сообщи ссылку и состояние шлюза.
