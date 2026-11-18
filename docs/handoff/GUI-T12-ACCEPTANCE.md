# Единая приёмка GUI и T12 на ThinkCentre

Рабочая машина — Ubuntu 24.04 LTS. Проверяемый код f4c994546bab083032ffda87a06ff8c0f28241d0. Ориентир на один проход — 90–120 минут. Выполни проверки GUI, backend, формы, TLS, видео и возврата. Опубликуй один отчёт. При блокере GUI продолжи сетевую часть после сверки исходного состояния шлюза. При отказе CDN всё равно проверь возврат на VPN.

[Главное окно принято и оставлено установленным](../reports/2026-11-18_gui-home-proton.md). Flash отмечала индикатор сортировки, фильтр допуска пула, компактные подписи и нестабильный холодный тест пульса. [Последний сетевой отчёт](../reports/2026-11-18_desync-t12-selective-media-pairs.md) зафиксировал два таймаута TLS к одному CDN, успешное TCP-соединение к нему по WAN за 51 мс и возврат на VPN. Ранее играло 15+5 минут в 720p. Маршрут свежих медиабайтов и одновременный VPN для обычного сайта предстоит подтвердить.

Flash сама запускает команды, работает с GUI и Chrome через vision и публикует результат. При отсутствии терминала, sudo или графического сеанса запроси соответствующий доступ. Используй подготовленный код из GitHub. Все сетевые файлы храни в приватном каталоге опыта. Сбор счётчиков ограничен по времени, захват пакетов для этого задания не требуется.

## 1. Подготовка

Выполняй блоки в Bash от пользователя рабочего стола в одной сессии. После прерывания восстанови пути из каталога опыта и перейди к проверке исходного состояния или возврату. При дефекте теста укажи имя и полный обезличенный результат. Ранее настроенный venv можно передать через XGW_TEST_PYTHON.

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
printf '%s\n' "$PRETTY_NAME"
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
BR=integration/zapret2-batch1
CODE=f4c994546bab083032ffda87a06ff8c0f28241d0
GUI_BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
GUI_OLD=3c4ae6b8446cd36e94dad1b3a9f74ac75dca23b5
CORE_OLD=a382971f162db53a8bd7435f124d591b6a5287fa
WEB_OLD=1fc4e69d569bbf583ffeb4e7799ff165741b3cc7
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git cat-file -e "$GUI_BASE^{commit}" || git fetch origin "$GUI_BASE"
D=$(mktemp -d "$HOME/xgw-acceptance.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
export PYTHONPATH="$D/source/src:$D/source"
"$TEST_PY" -m pytest -q \
  tests/test_zapret2.py tests/test_zapret2_panel.py tests/test_zapret2_management.py \
  tests/test_zapret2_management_linux.py tests/test_desync_schema.py \
  tests/test_selective_probe_watch.py tests/test_desync_route_evidence.py \
  tests/test_youtube_telemetry.py
node --check src/xgw/ui/zapret2.js
bash -n docs/helpers/t11_management_restore.sh
```

Ожидаются тесты без падений и пропусков. Проверь VPN и панель, off/off, оба воркера inactive. Проблема сети до установки блокирует сетевую фазу. Проверку Qt можно провести на фикстуре.

## 2. Исправления установленного GUI

Используй копию действующего релиза со всеми ранее установленными накладками. Фикстура проверяет интерфейс с подставным клиентом. В этом блоке сохраняются состояние шлюза и PID служб.

```bash
GUI="/opt/xgw/gui/releases/$GUI_BASE"
G_PAYLOAD="/var/lib/xgw/handoff/gui-catalog-refresh-$CODE"
G_FILES=(vpn_ui/xgw/catalog.py vpn_ui/xgw/sidebar.py vpn_ui/xgw/panels.py)
mkdir -p "$D/gui/vpn_ui" "$D/gui/src" "$D/gui/tests/fixtures/gui"
cp -R "$GUI/vpn_ui/." "$D/gui/vpn_ui/"
cp -R "$GUI/src/." "$D/gui/src/"
for f in "${G_FILES[@]}"; do cp -- "$f" "$D/gui/$f"; done
git show "$GUI_BASE:tests/test_vpn_ui_xgw.py" >"$D/gui/tests/test_vpn_ui_xgw.py"
git show "$GUI_BASE:tests/fixtures/gui/state-work.json" >"$D/gui/tests/fixtures/gui/state-work.json"
cp tests/test_vpn_ui_sidebar.py "$D/gui/tests/"
"$TEST_PY" -c 'import PyQt6.QtSvg, PyQt6.QtWidgets'
(
  cd "$D/gui"
  export PYTHONPATH="$D/gui:$D/gui/src" QT_QPA_PLATFORM=offscreen
  "$TEST_PY" -m pytest -q tests/test_vpn_ui_sidebar.py tests/test_vpn_ui_xgw.py
  "$TEST_PY" -m pytest -q tests/test_vpn_ui_sidebar.py -k pulses
)
sudo install -d -m 0700 "$G_PAYLOAD"
for h in gui_home_install.py gui_catalog_install.py; do
  sudo install -o root -g root -m 0600 "docs/helpers/$h" "$G_PAYLOAD/$h"
done
for f in "${G_FILES[@]}"; do
  git show "$GUI_OLD:$f" >"$D/gui-before.py"
  sudo install -D -o root -g root -m 0600 "$D/gui-before.py" "$G_PAYLOAD/before/$f"
  sudo install -D -o root -g root -m 0600 "$f" "$G_PAYLOAD/after/$f"
done
gui_install() {
  sudo "$PY" -I "$G_PAYLOAD/gui_home_install.py" "$1" --catalog-refresh
}
gui_install check
systemctl show -p MainPID -p ActiveState xgw.service xgw-xray.service >"$D/gui-before"
sudo sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/gui-config.sha256"
```

Если байты отличаются, укажи конкретный файл и оставь действующее окно. Иначе закрой окно, выполни gui_install apply и gui_install check. Ожидается READY changed files: 0. Запусти systemd-run --user --collect xgw gui из графического сеанса.

1. Щёлкни каждый заголовок дважды. Стрелка видна у активной колонки, направление совпадает с порядком. Пропуски в числовой колонке остаются внизу. Обновление API и смена темы сохраняют сортировку.
2. Проверь вкладки «Доступные» для подписки и «Допущенные» для пула. В observe допущенные строки показываются при недоступном ручном выборе. «Выбранные» показывают закреплённые серверы. Если на шлюзе нет подходящих строк, укажи подтверждение фикстурой.
3. Проверь 720×660 и минимальное окно. Короткие подписи нижних метрик читаются, ☰ и Esc работают. В широком окне сними два кадра пульса на стране активного VPN. Открой zapret2 и сверь режим с веб-панелью. Верни исходную тему.
4. Сверь конфиги и PID. Если правка мешает работе GUI, закрой окно, выполни gui_install rollback и заново запусти xgw gui. Отметь оставленную версию.

```bash
systemctl show -p MainPID -p ActiveState xgw.service xgw-xray.service >"$D/gui-after"
cmp "$D/gui-before" "$D/gui-after"
sudo sha256sum -c "$D/gui-config.sha256"
```

## 3. Установка backend и проверка формы

Ещё раз подтверди VPN, панель, off/off и отсутствие активных воркеров. Таймер действует 100 минут. Оставь минимум 10 минут на возврат. Установщик сверит ранее принятые четыре файла backend и обновление опроса веб-панели.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/selective-expiry-$CODE"
BACKUP="/var/lib/xgw/handoff/selective-expiry-$CODE"
UNIT=xgw-selective-expiry-rollback
OVERLAY=--selective-expiry
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
CORE=(src/xgw/zapret2.py src/xgw/desync/schema.py src/xgw/watch/zapret2_control.py
      src/xgw/watch/zapret2_management.py)
WEB=src/xgw/ui/zapret2.js
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo cmp "$PACKAGE/watch/checks.py" src/xgw/watch/checks.py
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CORE_OLD" "${CORE[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$WEB_OLD" "$WEB" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$CODE" "${CORE[@]}" "$WEB" docs/helpers/desync_batch1_install.py \
  docs/helpers/t11_management_restore.sh | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
sudo chmod -R go-w -- "$PAYLOAD"
sudo "$PY" "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" \
  --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$PANEL" "$UNIT" "$OVERLAY" "$HELPER" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=100m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback "$OVERLAY"
sudo systemctl is-active "$UNIT.timer"
sudo "$PY" "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
sudo sha256sum -c "$BACKUP/config-before.sha256"
check_installed() {
  for f in "${CORE[@]}" "$WEB"; do sudo cmp "$f" "$PACKAGE/${f#src/xgw/}"; done
}
check_installed
sudo touch "$BACKUP/network-test-started"
```

1. Обнови веб-панель. В off включи HTTPS-проверку и подставь шесть доменов YouTube. Сохрани /t/terms и фикстуру https://r1.googlevideo.com/videoplayback?expire=1&sig=xgw-expired-fixture. Сохранение в off должно пройти. В API есть expires_at=1 и причина в blockers.selective, кнопка Selective недоступна, оба воркера inactive. Форма показывает срок, а GET API не выдаёт полный URL или параметр sig.
2. Удали сохранённые адреса в off. Опция HTTPS остаётся, probe_count=0, probe_expiry пустое. Selective недоступен. Повторное открытие формы подтверждает очистку. [Принятый путь очистки](../reports/2026-11-18_desync-t12-selective-cdn-retry-r2.md).
3. Тесты §1 проверяют истечение на активном маршруте и во время пробы. Если свежий подписанный URL естественно истекает после просмотра в этом же окне, зафиксируй снятие правила, закрытие gate и новый сеанс VPN. В ином случае LIVE_EXPIRY=NOT_RUN и приложи результат фикстуры. Искусственное изменение expire в подписанном URL проверяет только форму.

## 4. Запуск Selective и парный TLS

Возьми свежий HTTPS /videoplayback в отдельном Chrome с выключенным QUIC. Сохрани полный URL только в панели. Локально запиши hostname, IPv4 и запас до expire. Для полного просмотра желателен запас от 35 минут. Сохрани multisplit, шесть доменов YouTube, интервал 180 с, retry 120 с, бюджет 256 МиБ. При двух обычных пробах такое расписание резервирует около 240 МиБ за сутки без повторов. Закрой вкладки плеера перед служебной пробой.

```bash
read -r -p 'WAN interface: ' WAN
read -r -p 'Selected NFQUEUE number: ' QUEUE
read -r -s -p 'CDN hostname: ' CDN_HOST; printf '\n'
read -r -s -p 'CDN IPv4 (empty if unavailable): ' PEER; printf '\n'
watch_run() {
  local name=$1 duration=$2
  shift 2
  sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_probe_watch.py \
    --queue "$QUEUE" --seconds "$duration" --socket-stats "$@" >"$D/$name.jsonl" &
  WATCH_PID=$!
}
wan_tls() {
  sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_wan_control.py \
    --wan "$WAN" --peer "$PEER" --tls-host "$CDN_HOST" "$@"
}
start_trial() {
  local name=$1
  sudo -v
  PAIR_PID=
  if [[ -n "$PEER" ]]; then
    wan_tls >"$D/$name-wan.json"
    wan_tls --during-selective 90 >"$D/$name-tls.json" 2>"$D/$name-ready.log" &
    PAIR_PID=$!
  fi
  watch_run "$name-start" 110
  START_PID=$WATCH_PID
  for _ in {1..40}; do
    if test -s "$D/$name-start.jsonl" && {
        [[ -z "$PAIR_PID" ]] || grep -q '^READY:' "$D/$name-ready.log"
    }; then
      printf 'Наблюдатели готовы. Включи Selective.\n'
      return 0
    fi
    sleep 0.25
  done
  printf 'Наблюдатели не готовы. Проверь локальный журнал.\n' >&2
  return 1
}
finish_start() {
  if [[ -n "$PAIR_PID" ]]; then wait "$PAIR_PID"; fi
  wait "$START_PID"
}
start_trial a
```

Включи Selective кнопкой. Запиши время клика, ревизию, длительность и стадии page/CDN, первый таймаут и исход встроенного повтора. После запуска active можно начать §5, пока завершаются первоначальные сборщики. Для разбора дождись finish_start.

Для парной оценки используй *-wan.json, *-tls.json, *-start.jsonl. Требуются одинаковые hostname и наблюдавшийся CDN-IP, gate и пересечение начала WAN TLS с интервалом того же сокета CDN. Сверь решения маршрута и source_matches_lookup. Различи первый и повторный TLS по started_at, elapsed_ms и first_tls_timeout_ms. Запиши WAN TLS с проверкой сертификата, TLS Selective, входящие байты и ретрансляции. Если TLS прошёл только по WAN, это различие двух путей в измеренном окне. [Команды для просмотра результатов и критерии пары](T12-SELECTIVE-TLS-PAIR.md#2-контроль-tls-и-одна-штатная-попытка-selective).

При fallback проверь обычный VPN, выключи Selective и дождись off/off. Разрешён один повтор. Если не совпал IP, возьми однозначно наблюдавшийся IPv4 того же hostname. Если отказала страница или старый адрес больше недоступен, возьми свежий URL из плеера, сверь hostname и IPv4. Введи новые значения CDN_HOST и PEER теми же командами read, закрой плеер и выполни start_trial b. При втором отказе перейди к §6. При active продолжи §5.

## 5. Живое видео до и после перемотки

1. После active выполни sudo -v и watch_run media-open 180 --media-pairs. Пока плеер закрыт, дождись принятой пары фона. Открой новый сеанс Chrome, выбери 720p, проверь «Статистику для сисадминов» через vision. Используй телеметрию ниже при наличии Playwright. В остальных случаях сохрани локально DevTools и хронометраж. Цель — свежая передача с сетевыми байтами, а не воспроизведение из буфера.
2. На том же временном отрезке открой обычный сайт вне списка YouTube в отдельном сеансе. Сверь выход с исходным VPN по тому же контрольному ресурсу. Если выбранный сервер подписки уже работает через мост sing-box, отрази это в отчёте. Сохрани вкладку с плеером на переднем плане.
3. Наблюдай 15 минут пригодного просмотра и две перепроверки на той же ревизии. При буферном окне или пересечении служебной пробы выполни sudo -v и watch_run media-mid 180 --media-pairs. Перед перемоткой запусти watch_run media-seek 180 --media-pairs, перемотай за пределы буфера и наблюдай ещё 5 минут. Указывай число пригодных секунд, долю 720p, реальные остановки, пропуски кадров и восстановление после перемотки.
4. Для каждой заявленной фазы MEDIA_PATH=CONFIRMED нужны общая принятая пара Xray/NFQUEUE, свежие CDN-байты плеера, прирост downlink zapret2 и очереди сверх фона, помеченный сокет к тому же IP и параллельный VPN-контроль. Исключи смену правила, ревизии, процесса, служебную пробу и кадры из буфера. При пробеле запиши PARTIAL и причину. [Вывод пар и критерии сопоставления](T12-SELECTIVE-MEDIA-PAIRS.md#2-короткое-окно-живой-передачи).

```bash
read -r -p 'Public video ID (11 characters): ' VIDEO
"${XGW_TELEMETRY_PYTHON:-$TEST_PY}" docs/helpers/youtube_telemetry.py \
  --video "$VIDEO" --label selective-acceptance --out "$D/player" \
  --seconds 1560 --height 720 --channel chrome --disable-quic >"$D/player.log" 2>&1 &
PLAYER_PID=$!
```

Если произошёл естественный fallback, запиши последнюю удачную пробу, причину и время до появления свежего VPN-сеанса. Если встроенный повтор восстановил CDN, сохрани обе фазы. Если таймаута в действующем режиме не было, укажи RETRY_LIVE=NOT_OBSERVED. Если active не достигнут, VIDEO и MEDIA_PATH получают NOT_RUN.

## 6. Возврат живого трафика и настроек

Выключи Selective. Подтверди off/off, остановку воркеров и свежий YouTube-сеанс через VPN. Проверь новый CDN-запрос с байтами и обычный сайт. Сними состояние Xray до и после передачи.

```bash
snap() {
  sudo env PYTHONPATH="$PYTHONPATH" "$PY" -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
snap vpn-start
```

Открой новый сеанс. Дождись просмотра и свежих сетевых байтов, затем выполни:

```bash
snap vpn-end
"$PY" -m xgw.desync.route_evidence delta "$D/vpn-start.json" "$D/vpn-end.json" \
  >"$D/vpn-delta.json"
```

Закрой тестовый Chrome. Дождись завершения ограниченных сборщиков и телеметрии, если она запускалась, чтобы файлы успели закрыться. При исправном пакете и работающем возврате используй accept. При дефекте пакета или восстановлении маршрутов с ошибкой используй rollback. Если установка backend не начиналась, достаточно сверки исходного состояния.

```bash
RESTORE=accept
# При необходимости возврата кода задай RESTORE=rollback.
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" "$RESTORE" "$OVERLAY"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-nfqws2.service xgw-zapret2.service -p ActiveState -p MainPID
sudo test -s "$BACKUP/restore-completed"
if [[ "$RESTORE" == accept ]]; then check_installed; fi
```

После сверки off/off, VPN, панели и хэшей останови таймер командой sudo systemctl stop "$UNIT.timer". Если таймер сработал автоматически, укажи исход отката и фактические байты файлов. При потере сессии используй сохранённый restore-location.txt.

## 7. Один публичный отчёт

Укажи CODE, ОС, Qt, результаты тестов и фактически оставленные версии. Для каждой строки зафиксируй PASS, FAIL, PARTIAL, NOT_RUN или BLOCKED и наблюдение.

| Блок | Доказательство |
|---|---|
| GUI | Три индикатора в двух направлениях, фильтры подписки и пула, ширины, темы, пульс, PID и хэши |
| EXPIRY | Истёкшая фикстура, результат очистки, автоматический возврат в тесте Controller, естественная граница при наличии |
| START / RECHECK / RETRY | Число попыток, состояния, ревизия, фазы страницы и CDN, исход встроенного повтора |
| TLS_PAIR | Совпадение hostname/IP и времени, результат TLS каждого пути, входящие байты и ретрансляции |
| PLAYBACK / MEDIA_PATH | Длительность и качество до/после перемотки, новые байты, пары и контроль VPN, точная причина пробела |
| VPN_RETURN / RESTORE | Новый сеанс, дельта, off/off, состояние воркеров, хэши и исход таймера |

В отчёт переносить агрегаты, обозначения узлов и причины. Реальные имена подписок и серверов, квоты, IP, hostname CDN, URL с подписью, снимки экрана с идентификаторами и сырые JSON остаются в приватном каталоге. При блокере до создания $D задай REPO через git rev-parse --show-toplevel, BR=integration/zapret2-batch1 и D=$(mktemp -d).

```bash
cd "$REPO"
git fetch origin "$BR"
git worktree add --detach "$D/report" FETCH_HEAD
cd "$D/report"
REPORT="docs/reports/$(date +%F)_gui-t12-acceptance.md"
# Заполни отчёт фактическими наблюдениями.
git add -- "$REPORT"
git diff --cached --check
git diff --cached --stat
git commit -m "docs: report combined GUI and T12 ThinkCentre acceptance"
git push origin "HEAD:refs/heads/$BR"
git ls-remote origin "refs/heads/$BR"
```

Если ветка продвинулась, перенеси коммит на свежий FETCH_HEAD и выполни обычный push. При совпадении имени отчёта опубликуй под уникальным именем.
