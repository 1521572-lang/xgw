# T12 — подтверждение пути видеотрафика Selective

ThinkCentre, Ubuntu 24.04 LTS. Код проверки `a1ad5d03bd97503e15e021c94af8752bd7c3f494`.
В прошлом раунде Selective стартовал с первого клика, две перепроверки прошли,
Chrome воспроизвёл 15 минут видео, затем после перемотки ещё 5 минут в 720p.
Пара Xray пересекла включение клиентского правила. Счётчик очереди вырос позже,
когда шли медиаданные. Цель этого раунда — поймать новую передачу CDN между
двумя сопоставимыми замерами. Продолжительность воспроизведения уже проверена.
[Отчёт WAN](../reports/2026-11-18_desync-t12-selective-wan-control.md).

Flash сама запускает подготовленные команды и проверяет Chrome через vision.
При отсутствии терминала, sudo или GUI запроси доступ. Сборщик запускается
из checkout, без установки кода. Он пишет локальные счётчики Xray и NFQUEUE,
статус и метаданные сокетов. URL, IP, токены и сырые файлы остаются локально.

## 1. Подготовка и возврат

Начни с чистого checkout и проверь off/off, VPN, панель и остановленные воркеры.
В отдельном тестовом Chrome с выключенным QUIC подготовь свежий адрес CDN
из DevTools и запиши исходный VPN-выход контрольного сайта вне списка YouTube.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=a1ad5d03bd97503e15e021c94af8752bd7c3f494
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-selective-media.XXXXXXXX")
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

Для pytest разрешён уже настроенный dev-venv. При исходном блокере переходи
к публикации в §3. Перед изменением настроек поставь таймер.

```bash
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
UNIT="xgw-selective-media-$(date +%s)"
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
BACKUP=$(sudo mktemp -d /var/lib/xgw/handoff/selective-media.XXXXXXXX)
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 docs/helpers/t11_management_restore.sh "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$PANEL" "$UNIT" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=60m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
sudo systemctl is-active "$UNIT.timer"
sudo touch "$BACKUP/network-test-started"
snap() {
  sudo env PYTHONPATH="$PYTHONPATH" "$PY" -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
delta() {
  "$PY" -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"
}
QUEUE=200
collect() {
  sudo -v
  sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_probe_watch.py \
    --queue "$QUEUE" --seconds 180 --media-pairs --socket-stats >"$D/$1.jsonl" &
  WATCH_PID=$!
}
```

Если очередь отличается от 200, укажи фактическое значение. Сборщик делает
одну выборку примерно каждые три секунды и завершает работу сам.

## 2. Короткое окно живой передачи

1. Сохрани `multisplit`, шесть доменов YouTube, интервал 120 с,
   HTTPS-опцию, `/t/terms` и свежий CDN. В исходном off сделай
   `snap vpn-before`, закрой старую вкладку с видео и выполни `collect first`.
   Включи Selective кнопкой. Запиши время клика и дождись active на текущей
   ревизии. Карточка и первая строка active сами по себе не подтверждают
   применение клиентского правила.
2. При active дождись первой пары с `media_pair.state=accepted`. Пока
   плеер закрыт, сохрани одну пару фона. Затем запусти видео в **новой**
   вкладке обычного Chrome. В DevTools включи Preserve log и отфильтруй
   свежие `googlevideo.com/videoplayback`. Параллельно открой контрольный
   сайт вне списка YouTube и подтверди VPN-выход. Проверь 720p через vision.
   Для времени отдельного запроса используй HAR/DevTools с локальными
   часами шлюза. HAR хранится только локально. Нужны запрос с сетевыми
   байтами и его интервал, включая GET или POST, статус и протокол.
3. Дождись завершения `wait "$WATCH_PID"`. Выведи короткие пары:

   ```bash
   "$PY" - "$D/first.jsonl" <<'PY'
   import json, sys
   from pathlib import Path
   for line in Path(sys.argv[1]).read_text().splitlines():
       row = json.loads(line)
       if pair := row.get("media_pair"):
           print(json.dumps({"sample_at": row["sample_at"],
                             "route_error": row.get("route_error"), **pair}))
   PY
   ```

   `start_unix`–`end_unix` — общее окно между чтениями Xray и очереди.
   Дельты относятся к собственным интервалам каждого счётчика. Для
   доказательства ищи свежую передачу внутри общего окна, а не просто
   начатый ранее запрос. Пары с новой пробой между чтениями
   (`probe_before` отличается от `probe_after`) отметь как смешанные.
   Исключи окно служебной пробы по её времени и длительности, даже если
   граница пробы видна лишь в следующем снимке. Нулевой рост при буфере
   запиши как наблюдение. Отвергнутые пары не складывай.
4. Для `MEDIA_PATH=CONFIRMED` нужны сопоставимая пара и новый CDN-запрос
   с байтами, рост downlink zapret2 и NFQUEUE сверх фона, совпавший CDN-IP
   на помеченном сокете в этом окне и подтверждённый параллельный VPN-выход.
   Если передачи не было или короткий сокет не попал в выборку, разрешён
   один дополнительный сбор `collect seek` с перемоткой за пределы буфера
   или запуском нового ролика после первой принятой пары.
   При недостающей привязке укажи `MEDIA_PATH=PARTIAL` и конкретное поле.
   [Критерии маршрута](T12-SELECTIVE-ROUTE-EVIDENCE.md#3-дельты-и-подтверждение-маршрута).
5. При fallback сохрани фазу пробы, наблюдавшийся адрес и причину остановки.
   Если стартовая CDN-проба дала таймаут, допустим один повтор после off
   со свежим адресом от тестового плеера. Укажи, изменился ли фактический IP.
   Без active укажи `MEDIA_PATH=NOT_RUN` и перейди к возврату.

## 3. Возврат и публикация

Выключи Selective, дождись свежего off/off и открой новый сеанс YouTube через VPN.
Возьми пару `snap vpn-restored-start` и `snap vpn-restored-end` по обе стороны
новой передачи. Проверь `delta vpn-restored-start vpn-restored-end` и контрольный
сайт. Дождись остановки сборщика. Оставь не менее 10 минут на возврат.
При сработавшем таймере проверь `restore-completed` и хэши.

```bash
sudo /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

После подтверждения off/off, VPN, панели и исходных хэшей останови таймер
`sudo systemctl stop "$UNIT.timer"`. Закрой тестовое окно Chrome. Пути для
возврата записаны в `restore-location.txt`.

Автоматически опубликуй только обезличенный отчёт, включая блокеры.
Укажи SHA, итог предзапусковых проверок, количество принятых и отклонённых
пар, причины отклонения, хотя бы один пример с UTC, байтами, пакетами и
медиазапросом, `MEDIA_PATH` и результат возврата. Исходники и конфиги
испытателя в публикацию не входят.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t12-selective-media-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t12-selective-media-pairs.md"
test ! -e "$REPORT"
# Заполни отчёт по выполненным шагам, включая блокеры.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify Selective media counter pairs on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке выполни fetch, rebase и обычный push. Сообщи ссылку и состояние шлюза.
