# T04/T12 — YouTube через zapret2, остальной трафик через VPN

Цель на ThinkCentre с Ubuntu 24.04 LTS — подтвердить живой Selective. В одном
интервале YouTube воспроизводит видео через `multisplit`, а контрольный сайт
использует VPN. После отказа воркера новый сеанс YouTube снова использует VPN.

[Standalone ALT9](../reports/2026-11-17_desync-t10-flowseal-live.md) дал две
успешные короткие попытки и 1027,8 с пригодного просмотра в длинной записи.
Дельты байтов отсутствовали. [Selective на Википедии](../reports/2026-11-16_desync-selective-vpn-control.md)
подтвердил возврат после отказа. Текущая проверка соединяет эти наблюдения на
реальном видео. Для неё хватит уже установленного слоя T09 и инструментов из checkout.

Исполнитель сама запускает терминал и Chrome, проверяет кадры через vision и
автоматически публикует отчёт. При недоступности терминала, sudo или браузера
запроси доступ. Выполни независимые проверки и опубликуй частичный результат,
если сетевую часть блокирует недоступность пробы или шлюза.

## 1. Подготовка

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
git merge-base --is-ancestor 1abce7d "$CODE"
D=$(mktemp -d "$HOME/xgw-selective-youtube.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest --portable tests/test_desync_route_evidence.py tests/test_zapret2.py

snap() {
  sudo env PYTHONPATH="$PYTHONPATH" python3 -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
delta() {
  python3 -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"
}
snap initial
```

При нестандартном пути к применённому Xray-конфигу передай `--xray-config` в
`snap`. Убедись, что начальные счётчики читаются, panel и штатный VPN в работе,
off/off, очередь пуста. Сверь `network.quic_mode=reject`, обычный маршрут VPN,
отсутствие `pool_all`, исключений или маршрута устройства, перекрывающих YouTube.
Для контроля выбери HTTPS-ресурс вне всех списков zapret2 и direct. Проверь
`proxy_domains` по установленной схеме. При несовместимости зафиксируй причину.

Сверь свободное место и оставшийся WAN-захват с последним отчётом. Используй
Chrome/CDP, счётчики и наблюдение соединений. Новый WAN-захват не нужен.

## 2. HTTPS-пробы и возврат

Для Selective нужны два реально работающих GET — страница `youtube.com` и контент
на `*.googlevideo.com`. Пусть каждый отдаёт HTTP 2xx и ≥16 КиБ тела без редиректа.
Подбери URL из свежих реальных запросов браузера или приватных записей, проверь
метод и пригодность. SABR POST, корень CDN, HTTP 204, заглушка и просроченная
подпись сами по себе не подходят. Проверка через VPN пригодна как исходная, но
подпись CDN может быть привязана к IP. Прямой GET подтверждает штатный probe в
Selective. Если первая ссылка не подходит, попробуй свежую из того же клиента.
При отсутствии пригодного GET зафиксируй это как блокер открытия маршрута.
Сохрани статусы и примерный срок жизни без самих ссылок и не ослабляй gate.

Создай `"$D/probes.json"` с 0600. Это JSON-массив из двух приватных HTTPS URL.
Страница YouTube идёт первой, так как текущая служебная проверка VPN использует
первый URL. Ссылки не передавай в argv и не сохраняй в Git.

Подготовь возврат, затем используй один lock на все сетевые фазы. Переменные
`PACKAGE`, `PY`, `CFG`, `PANEL` сверь по установленному XGW до продолжения.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
PID=$(systemctl show xgw.service -p MainPID --value)
PY=$(sudo readlink -f "/proc/$PID/exe")
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
QUEUE=201  # замени, если очередь занята
LOCK_ROOT=${XDG_RUNTIME_DIR:-$HOME}
exec 9>"$LOCK_ROOT/xgw-t09-live.lock"
flock -n 9
UNIT=xgw-selective-youtube-rollback
BACKUP=$(sudo mktemp -d /var/lib/xgw/handoff/selective-youtube.XXXXXXXX)
sudo cp --preserve=mode,ownership "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" >"$D/config-before.sha256"
sudo install -m 0700 /dev/stdin "$BACKUP/restore.sh" <<'SH'
#!/bin/bash
set -euo pipefail
backup=$1
panel=$2
exec 9>"$backup/restore.lock"
flock 9
systemctl stop xgw.service
temp=$(mktemp "$(dirname "$panel")/.xgw-selective.XXXXXXXX")
cp --preserve=mode,ownership -- "$backup/panel.before" "$temp"
mv -fT -- "$temp" "$panel"
systemctl start xgw.service
timeout 180 /usr/local/bin/xgw apply --now
SH
sudo systemd-run --unit="$UNIT" --on-active=45m \
  /bin/bash "$BACKUP/restore.sh" "$BACKUP" "$PANEL"
sudo systemctl is-active "$UNIT.timer"
```

Установку пакета здесь не запускай. Замеры и переходы выполняются уже установленным
контроллером. Для выбора второго VPN-ядра используй существующую настройку
сервера XGW. Перед измерением дождись стабильного применённого конфига.

```bash
set_phase() {
  sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - \
    "$CFG" "$1" "$QUEUE" "$D/probes.json" <<'PY'
import json
import sys
from dataclasses import asdict
from pathlib import Path

from xgw import config, managed
from xgw.desync import schema

path, phase, queue, probes = sys.argv[1:]
assert phase in ("off", "selective")
cfg, _ = config.load(Path(path))
policy = schema.migrate(asdict(cfg.zapret2))
urls = json.loads(Path(probes).read_bytes()) if phase == "selective" else []
policy["selected"].update(
    mode=phase, strategy="multisplit", probe_urls=urls, check_seconds=300,
    retry_seconds=300, observe_synack=False, observe_reply_packets=0,
    domains=["domain:youtube.com", "domain:googlevideo.com",
             "domain:youtubei.googleapis.com", "domain:youtube-nocookie.com",
             "domain:ytimg.com", "domain:ggpht.com"],
)
policy["runtime"]["queue_num"] = int(queue)
policy["engine"]["engine"] = "off"
managed.set_desync(managed.path_for(Path(path)), policy)
actual, _ = config.load(Path(path))
assert schema.migrate(asdict(actual.zapret2)) == policy
PY
}
```

## 3. Контроль, живая фаза и отказ

1. **Исходный VPN.** Со свежим Chrome (без прокси, QUIC off) открой ролик
   `8plwv25NYRo` и контрольный сайт. Сними счётчики до и после контрольного запроса
   и отдельно до и после медиазапросов. Отметь фактическое VPN-ядро, TCP/HTTPS
   и состояние проигрывателя. Для VPN-пути с sing-box должно увеличиться число
   байтов тега моста sing-box в Xray. Для Xray — тега нативного выхода.
2. **Selective.** Вызови `set_phase selective`, дождись `active/probes_ok`, нового
   поколения, действующего gate и владельца очереди. Сверь клиентское правило
   Xray для YouTube, а также действующий обычный VPN-выход. Недостаточную
   HTTPS-пробу, ошибку маршрута и сбой браузера запиши раздельно.
3. **Одновременная проверка.** В новом Chrome включи 720p, 1×. Собери ≥150 с
   [телеметрии плеера и CDP](YOUTUBE-TELEMETRY.md#замер-в-обычном-chrome) и проверь
   кадр через vision. Сделай короткое фоновое измерение в покое, затем замерь
   отдельный интервал свежих SABR POST. Во время просмотра выполни один отдельный
   HTTPS-контроль вне YouTube. Сними перед ним и после него счётчики подвыходов.
   Привяжи наблюдения к времени, destination медиа и пути фактического соединения.
   Во время новой передачи проверь соединения к адресу CDN через
   `sudo ss -Hntp dst "$CDN_IP"`, сопоставь с PID Xray и владельцем NFQUEUE.
   Адрес бери только из CDP этой фазы, сохраняй вывод приватно. Так можно отличить
   собственно запросы медиа от служебных probe. Отметь протокол и смену CDN.
4. **Fallback.** Зафиксируй статус и контрольный VPN-запрос, затем заверши только
   MainPID экспериментальной службы `xgw-zapret2.service` тем же способом, что в
   [принятом тесте](../reports/2026-11-16_desync-selective-vpn-control.md).
   Дождись закрытия gate и удаления клиентского прямого правила. В новом Chrome
   повтори YouTube и контрольный запрос. Сними новую пару счётчиков после
   переключения, зафиксируй прирост VPN-байтов, свежий Chrome media-запрос и
   `evidence.vpn_control`. Отдельно измерь время до новой рабочей загрузки.
   Служебная VPN-проба может пройти при ошибке самого видео.
5. **Второе ядро и длинный опыт.** Если оба VPN-выхода доступны в подписке,
   повтори одновременную короткую фазу на другом ядре с новой проверкой probe.
   Недоступное ядро отметь с причиной. Если короткая фаза и fallback подтверждены,
   перезаряди таймер и сделай 15 минут просмотра в 720p, перемотку и ещё 5 минут.
   Отдельно укажи пригодное время и паузы интерфейса. Просроченная probe должна
   закрыть прямой путь и отражаться в отчёте с временем.

Шаблон одного интервала:

```bash
snap media-before
# Сама выполни фазу в Chrome и отметь её границы в CDP.
snap media-after
delta media-before media-after >"$D/media-delta.json"
```

Снимай обе метрики в каждой фазе **до закрытия браузера и до перезапуска Xray**.
У прибора группы `zapret2`, `xray` и `sing-box`. При отсутствии счётчика будет
`null`. При перезапуске, замене конфига или сбросе сравнение будет отклонено.
Сделай новую пару в стабильной фазе. Рост общего счётчика при наличии фонового
трафика оценивай вместе с CDP, маршрутом и временем запроса. При недостающей
привязке публикуй `MEDIA_PATH=PARTIAL`, даже при хорошем видео.

## 4. Восстановление и публикация

Выполни `set_phase off`, дождись освобождения очереди и верни исходный panel.

```bash
sudo /bin/bash "$BACKUP/restore.sh" "$BACKUP" "$PANEL"
sudo sha256sum -c "$D/config-before.sha256"
# Сверь очередь, VPN, panel и исходное состояние off/off до остановки таймера.
sudo systemctl stop "$UNIT.timer"
flock -u 9
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/selective-youtube-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-selective-youtube.md"
# Сама запиши REPORT, даже если была доступна только часть проверок.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: verify Selective YouTube routing and VPN fallback"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

Укажи версию кода и измеренные состояния для обеих сторон маршрута. Публикуй
дельты групп и статусы проб, просмотра и fallback. URL, IP, приватные теги,
снимки конфига и полные выгрузки CDP остаются на машине. При гонке сделай fetch,
rebase и обычный push.
