# T05 — ранние ответы TCP и проверка AutoTTL

**Текущее задание:** [ранние ответы и AutoTTL на ThinkCentre](T05-REPLIES-AUTOTTL.md).
Проверить границы окна при включённом учёте conntrack и провести изолированное сравнение TTL.
Модель выполняет прогон и публикует результат в этой ветке.

Первая часть T05 принята. [Отчёт от 16 ноября](../reports/2026-11-16_desync-t05-synack.md)
подтвердил IPv4 SYN/ACK в очереди, отрицательные контроли, аварийный возврат и 135 секунд
YouTube 720p. Слой оставлен установленным, off/off восстановлен. У WAN не было IPv6.

T04 закрыт. [Телеметрия Chrome и Compare](../reports/2026-11-16_desync-t04-telemetry-compare.md)
приняты. [Отчёт Selective](../reports/2026-11-16_desync-selective-vpn-control.md) подтвердил
`vpn_control=pass` и сохранение результата во всех 41 снимках. Обновление оставлено на машине,
исходный режим off/off со штатным VPN восстановлен.

## Архив T04 — установка и первичная проверка Standalone

На ThinkCentre установлен T04 с исправлением готовности Xray в `1e27384`. Отчёт подтверждает
YouTube 720p без VPN (15 минут + перемотка + 5 минут), закрытие и восстановление Standalone
после SIGKILL и новый клиентский поток через VPN после отказа Selective. Шлюз возвращён
в исходный режим off/off с рабочим VPN. [Отчёт T04](../reports/2026-11-15_desync-t04.md).

Дальнейшие команды сохранены для воспроизведения исходного T04 с базы T03.

Ветка integration/zapret2-batch1. База разработки eea38a3, последний установленный слой
026a935. [Отчёт T03](../reports/2026-11-15_desync-t03.md) подтверждает передачу очереди.
Сетевой ориентир — [опыт r1](../reports/2026-11-15_desync-hypotheses-r1.md) с hostfakesplit-md5
и браузером через SABR. Прочитай оба отчёта до начала.

Ты сама запускаешь команды на Ubuntu 24.04, открываешь браузер и проверяешь экран через vision.
Если недоступны терминал, sudo или GUI, запроси доступ. По завершении опубликуй отчёт
автоматически, включая блокеры и фактическое состояние машины.

## Получение и подготовка

В исходном чистом checkout на шлюзе:

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse 1e273842df23ae4cc017867478a363a152e095c7)
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-desync-t04.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
uname -r
nft --version
```

Если появились хотфиксы, прочитай diff и закрепи SHA, который проверяешь. В имеющемся dev-venv
выполни pytest. Сравни неожиданные падения с базой. В предыдущем отчёте уже отмечены шесть
не связанных с T03 падений test_daemon.

```bash
python3 -m pytest --portable tests/test_desync_standalone.py tests/test_desync_worker.py \
  tests/test_desync_schema.py tests/test_zapret2_panel.py
python3 -m pytest -q tests/test_zapret2.py tests/test_nfqws2.py tests/test_applier.py \
  tests/test_generator.py tests/test_daemon.py tests/test_ops.py
```

По ExecStart, launcher и PID проверь установленные PACKAGE/PY/CFG ниже. Сними исходный статус,
права и хэши конфигов, настройки перехвата и offload, очереди, nft и состояние Xray/sing-box.
Из исходного захваченного браузера запиши доступность и наблюдаемый выход через VPN.
Текущие mode и engine должны быть off, а обе службы nfqws2 — неактивны. Если обрабатывается
рабочий трафик zapret2, согласуй окно его переключения.

## Установка с возвратом

Helper проверяет установленную базу по байтам. Сопоставь каждый файл с известным исходным
коммитом, если есть расхождение. Подтверждённые прежние GUI и конфиги владельца сохраняются.

```bash
BASE=026a935
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
PID=$(systemctl show xgw.service -p MainPID --value)
PY=$(sudo readlink -f "/proc/$PID/exe")
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/desync-t04-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-t04-$CODE"
FILES=(apply/applier.py cli.py config.py daemon.py desync/schema.py engine.py \
       generator/builder.py net/nft.py nfqws2.py watch/zapret2_control.py zapret2.py)
BASE_FILES=()
for file in "${FILES[@]}"; do BASE_FILES+=("src/xgw/$file"); done
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${BASE_FILES[@]}" src/xgw/watch/standalone.py \
  docs/helpers/desync_batch1_install.py | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${BASE_FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
sudo chmod -R go-w -- "$PAYLOAD"
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
sudo "$PY" "$HELPER" prepare --worker-t04 --payload "$PAYLOAD" \
  --package "$PACKAGE" --backup "$BACKUP"
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
exec 9>"$backup/restore.lock"
flock 9
systemctl stop xgw.service
temp=$(mktemp "$(dirname "$panel")/.xgw-t04-restore.XXXXXXXX")
cp --preserve=mode,ownership -- "$backup/panel.before" "$temp"
mv -fT -- "$temp" "$panel"
if [ "$mode" = rollback ]; then
  "$py" "$helper" rollback --worker-t04 --backup "$backup"
else
  systemctl start xgw.service
fi
if [ -e "$backup/network-test-started" ]; then
  timeout 180 /usr/local/bin/xgw apply --now
fi
SH
sudo systemd-run --unit=xgw-desync-t04-rollback --on-active=45m \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback
sudo systemctl is-active xgw-desync-t04-rollback.timer
sudo "$PY" "$HELPER" apply --worker-t04 --backup "$BACKUP"
sudo sha256sum -c "$D/config-before.sha256"
```

Проверь 12 строк манифеста и точные SHA установленных файлов. Сохрани приватный снимок
применённых конфигов Xray и VPN-мостов вместе с их активным поколением. До переключения
убедись, что текущий VPN может восстановиться штатным apply и есть локальный канал доступа.
Перед сетевыми шагами включи предохранитель:

```bash
sudo touch "$BACKUP/network-test-started"
sudo systemctl restart xgw-desync-t04-rollback.timer
sudo systemctl list-timers xgw-desync-t04-rollback.timer
```

Держи таймер активным. Перезаряжай заранее перед длинным видео. При срабатывании останови
эксперимент, проверь фактическое состояние и начни новый блок только после восстановления.
В конце прогона вызови тот же restore с аргументом accept при PASS кода либо rollback при
регрессии. После сверки конфигов и сети останови таймер. Укажи итоговый режим в отчёте.

## Активация Standalone

Переключайся через штатное чтение panel.json. В панели API пока доступен только статус.
Временная политика не требует правки TOML, когда текущие условия перехвата подходят:
fail_mode=closed, hold=block, перехват хотя бы локального или LAN трафика, QUIC=reject.
Проверь, что capture включён для устройства, с которого открываешь браузер.

```bash
set_standalone() {
  sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - "$CFG" <<'PY'
from dataclasses import asdict
from pathlib import Path
import sys
from xgw import config, managed
from xgw.desync import schema
path = Path(sys.argv[1])
cfg, _ = config.load(path)
policy = schema.migrate(asdict(cfg.zapret2))
policy["selected"].update(mode="standalone", strategy="hostfakesplit_md5",
                          probe_urls=[], retry_seconds=60)
policy["engine"]["engine"] = "off"
policy["selected"]["domains"] = [
    "domain:youtube.com", "domain:googlevideo.com", "domain:youtubei.googleapis.com",
    "domain:youtube-nocookie.com", "domain:ytimg.com", "domain:ggpht.com",
]
managed.set_desync(managed.path_for(path), policy)
actual, _ = config.load(path)
assert schema.migrate(asdict(actual.zapret2)) == policy
PY
}
set_standalone
```

Следи за journal/status.json и списком nft. Опиши переход в standalone, локальный Xray и
остановку legacy/managed VPN-мостов. Подтверди отсутствие proxy- и pool-outbound,
VPN-балансировщиков и VPN-наблюдателя в применённом Xray. Проверь queue → netlink → MainPID
по протоколу T03 и наличие обоих элементов zapret2_live с TTL. Покажи, что без очереди
выбранный путь закрыт. Сними отдельный контроль обычного сайта через standalone-direct.
Если профиль не применился или видно только старое соединение, перезапусти конкретную пробу.

### Живое видео

Следуй [обновлённому ТЗ телеметрии](YOUTUBE-TELEMETRY.md). На ThinkCentre основная проверка
маршрута уже прошла в обычном Chrome. Открыта приёмка длительного автоматического замера
в том же режиме браузера. При повторной проверке маршрута используй описанные ниже признаки.

Открой чистый профиль браузера без прокси и с отключённым QUIC. Используй новое окно плеера
и публичный ролик, на котором ранее был успех, либо другой длинный публичный ролик.
Сними начальный прогресс и кадр, затем 15 минут и ещё 5 после перемотки. Вручную выбери
720p или 1080p и запиши фактическое качество, длительность, буфер и остановки. Отдельно
запиши, удалось ли услышать звук. Отсутствие классического GET URL при SABR ожидаемо.

Подтверди фактический маршрут страницы и media через outbound xgw-zapret2 и выход на WAN
(счётчики Xray по тегам, отметка цепочки zapret2_queue и короткое наблюдение свежего
SABR-потока, как в предыдущих отчётах). Фоновые байты от другого direct-трафика не засчитывай.
Отсутствие VPN-мостов подтверждается отдельно. Одно лишь движение позиции плеера может
быть чтением буфера. Публикуй только обезличенные тайминги и счётчики.

### Отказ и восстановление

В том же режиме подведи сетевой браузер к новой точке видео. Заверши только экспериментальный
xgw-zapret2.service через systemctl kill --kill-whom=main --signal=SIGKILL.
Проверь, что новые соединения к выбранным именам закрыты, очередь не bypass, gate исчезает
и клиентское правило снимается, без появления VPN-конфига. Обычный контрольный сайт должен
оставаться доступен через прямой выход. Докажи восстановление worker и gate на новом
поколении после retry. Запиши, сколько секунд занял переход. Не засчитывай буфер браузера
как доказательство доступа в интервале отказа.

## Selective, Compare и Off

Для выхода из Standalone верни policy selected.mode=off через managed.set_desync и дождись
обычной конфигурации с серверами. Сверь применённый исходный тип маршрута, его реальный выход
и оба worker. Подтверди, что существующие подписки и настройки остались доступны.

Затем проверь Selective на известном HTTPS endpoint, который отвечает свежим телом ≥16 KiB на
оба пути. Для этого шага заполни probe_urls, задай domain: или full: этого endpoint и используй
обычную стратегию или hostfakesplit_md5. Сначала дождись активного прямого правила. Прерывание
только нового экспериментального worker должно снять прямое правило. Повтори запрос с новым
соединением через штатный захваченный клиент, сверь VPN-выход и evidence.vpn_control.
Успех отдельной служебной пробы и реальный новый клиентский поток зафиксируй по отдельности.
Если URL не даёт валидной прямой пробы, зафиксируй эту причину и не объявляй успешный fallback.

Для Compare используй multisplit и два валидных HTTPS URL выбранных доменов. Запиши результаты
четырёх проб из status.json, подтверждение отсутствия прямого клиентского правила на протяжении
раунда и освобождение очереди. При отсутствии VPN-контроля отметь состояние как неполное.

Заверши возвратом исходной политики и восстановлением штатной сети. Сверь исходные SHA,
VPN-путь, главные службы, offload, очередь и видимое окно. Режим T04 оставляется установленным
после подтверждённой работы маршрутов. Варианты, которые не удалось воспроизвести, вынеси
в отчёт с точным условием. Слияние в основную ветку в этот проход не входит.

## Исходная проверка Compare и vpn_control

В `1e27384` клиентский fallback доказан новым соединением, служебная проверка осталась
`vpn_control=not_run`, Compare — `NOT_RUN`. Проводить их можно на обычных HTTPS GET: у
обработчика Compare две пары служебных запросов, а у Selective — отдельный запрос после
снятия маршрута. Эффект на YouTube измеряется в браузере.

1. Начни из off/off с живым VPN. Убедись, что у рабочего участника есть порт пробы, а бюджета
   хватает на весь цикл. Выбери два стабильных HTTPS URL с телом ≥16 KiB, без редиректов и
   авторизации. Заранее проверь их через штатный VPN; сохрани статус и размер. Перед временной
   политикой включи предохранитель по [ТЗ замера](YOUTUBE-TELEMETRY.md).
2. В Compare задай эти два URL в `probe_urls`, их имена в `domains`, стратегию `multisplit`
   и engine=off. Сохрани четыре строки `zapret2.probes` из свежего `status.json`, причину
   завершения, очистку gate/очереди и клиентский поток через VPN в ходе раунда. Четыре
   результата с ошибкой тоже проверяют механику лишь в той мере, в какой найден точный этап
   и подтверждён возврат ресурсов. Запиши результат по каждому пути.
3. Для Selective подбери такой URL, который проходит штатную прямую пробу и служебный VPN.
   Дождись `active/probes_ok`, затем выполни SIGKILL экспериментального worker по сценарию
   выше. Запиши первое свежее состояние `fallback` после `worker_down` или `probe_failed`,
   `gate_closed`, сырой `zapret2.vpn_control` и результат нового клиентского запроса.
   Если значение снова `not_run`, сверь условие закрытия gate, снятие маршрута и остановку
   worker, наличие живого VPN-участника с портом, учётные данные пробы без вывода значений,
   бюджет и отмену проверки. Доступность URL без DPI сама по себе вызову пробы не мешает.
4. Верни исходную политику и опубликуй результаты с замером в новом отчёте. Если не получилось
   подобрать URL или выделить окно, укажи конкретное условие и фактический статус.

## Публикация

В отчёте укажи SHA, вывод тестов и результат каждого реального шага. Для видео укажи качество,
тайминг, выбранный outbound и объём сетевого трафика. Для отказов укажи последовательность
изменения gate, очереди и правил. Приватные конфиги, URL и записи пакетов оставь на стенде.
Ошибки окружения разрешены к точечному исправлению с повторной проверкой.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/desync-t04-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t04.md"
# Заполни REPORT. Подтверждённый хотфикс добавляй отдельными точными путями.
git add "$REPORT"
git diff --cached --check
git diff --cached
git commit -m "docs: report standalone and fallback T04 on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При отклонении push из-за свежего коммита сделай fetch/rebase, сверь изменения и повтори обычный
push. В итоговом сообщении укажи SHA отчёта и оставленный режим.
