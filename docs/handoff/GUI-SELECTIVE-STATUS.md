# ThinkCentre — сортировка каталога и состояние Selective при отказе

ОС — Ubuntu 24.04 LTS. Код dfccea8c88418e839532ccaec40f85b019669f51, база принятой установки
f4c994546bab083032ffda87a06ff8c0f28241d0. Проход занимает около 35–50 минут,
плюс до 25 минут при успешном старте Selective и проверке видео.

[Последний отчёт](../reports/2026-11-18_gui-t12-acceptance.md) принял обновление
GUI, фильтр пула, проверку срока ссылки и возврат VPN. Остался воспроизводимый
клик «Серверы → Мбит/с». На образце Qt прежняя граница колонки менялась при
переносе стрелки. В этой версии ширина обеих числовых колонок фиксирована для
текущего шрифта. При парной проверке TLS истёк и через WAN, и через Selective
к тому же CDN. Новый сеанс по VPN работал. Эти наблюдения относятся к
измеренному адресу и интервалу. Точная причина потери ответа неизвестна.

Flash сама выполняет команды, использует vision и публикует один отчёт.
Если нет терминала, sudo или графической сессии, запроси соответствующий
доступ. Исходники и тесты выполняются из закреплённого checkout. Если GUI
заблокирован, сетевой блок можно выполнить отдельно после проверки шлюза.

## 1. Подготовка и тесты

Работай в одном Bash от пользователя рабочего стола. Используй системный
Qt и pytest или уже настроенный dev-venv.

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
printf '%s\n' "$PRETTY_NAME"
REPO=$(git rev-parse --show-toplevel)
BR=integration/zapret2-batch1
CODE=dfccea8c88418e839532ccaec40f85b019669f51
OLD=f4c994546bab083032ffda87a06ff8c0f28241d0
GUI_BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-status.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
export PYTHONPATH="$D/source/src:$D/source"
"$TEST_PY" -m pytest -q tests/test_zapret2_panel.py
bash -n docs/helpers/t11_management_restore.sh
```

## 2. Сортировка в установленном GUI

Создай копию установленного релиза для Qt-тестов. Установщик сверяет три
файла каталога со старой доставкой и меняет только файл, который отличается.

```bash
GUI="/opt/xgw/gui/releases/$GUI_BASE"
G="/var/lib/xgw/handoff/gui-stable-columns-$CODE"
G_FILES=(vpn_ui/xgw/catalog.py vpn_ui/xgw/sidebar.py vpn_ui/xgw/panels.py)
mkdir -p "$D/gui/vpn_ui" "$D/gui/src" "$D/gui/tests"
cp -R "$GUI/vpn_ui/." "$D/gui/vpn_ui/"
cp -R "$GUI/src/." "$D/gui/src/"
cp vpn_ui/xgw/sidebar.py "$D/gui/vpn_ui/xgw/sidebar.py"
cp tests/test_vpn_ui_sidebar.py "$D/gui/tests/"
(
  cd "$D/gui"
  export PYTHONPATH="$D/gui:$D/gui/src" QT_QPA_PLATFORM=offscreen
  "$TEST_PY" -m pytest -q tests/test_vpn_ui_sidebar.py
)
sudo install -d -m 0700 "$G"
for h in gui_home_install.py gui_catalog_install.py; do
  sudo install -m 0600 "docs/helpers/$h" "$G/$h"
done
for f in "${G_FILES[@]}"; do
  git show "$OLD:$f" >"$D/gui-before.py"
  sudo install -D -m 0600 "$D/gui-before.py" "$G/before/$f"
  sudo install -D -m 0600 "$f" "$G/after/$f"
done
gui_install() { sudo "$PY" -I "$G/gui_home_install.py" "$1" --catalog-refresh; }
gui_install check
systemctl show -p MainPID -p ActiveState xgw.service xgw-xray.service >"$D/services.before"
sudo sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/config.gui.sha256"
```

Ожидается 4 теста Qt без пропусков. При неизвестных байтах установленного
файла запиши имя и оставь действующий релиз. После успешной сверки закрой
окно XGW, выполни gui_install apply и gui_install check. Открой systemd-run
--user --collect xgw gui из графической сессии.

1. В подписке и в бесплатном пуле сделай «Серверы → Мбит/с → Рейтинг → Серверы → Мбит/с».
   Щёлкни «Мбит/с» по центру и у начала надписи. Повтори переход после очередного
   опроса. Направление соответствует порядку строк, стрелка рисуется у выбранной
   колонки. Границы при переносе стрелки остаются на месте. Сверь два кадра.
2. Выполни тот же переход в компактной панели ☰ и в другой теме. Проверь
   читаемость показателей, верни исходную тему. Выбор сервера не нажимай.
3. Сверь установленные байты, PID и хэши. При дефекте закрой окно, выполни
   gui_install rollback и вновь открой xgw gui. Зафиксируй оставленную версию.

```bash
gui_install check
systemctl show -p MainPID -p ActiveState xgw.service xgw-xray.service >"$D/services.after"
cmp "$D/services.before" "$D/services.after"
sudo sha256sum -c "$D/config.gui.sha256"
```

## 3. Обновление серверной карточки

Начни с работающих VPN и панели, off/off и обоих воркеров inactive.
Сначала собери резервную копию. Точка восстановления из этого блока включает
старую карточку и исходный panel.json. Оставь последние 10 минут на возврат.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/selective-status-$CODE"
BACKUP="/var/lib/xgw/handoff/selective-status-$CODE"
UNIT=xgw-selective-status-rollback
OVERLAY=--selective-status
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
CARD=src/xgw/watch/zapret2_control.py
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$OLD" "$CARD" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$CODE" "$CARD" docs/helpers/desync_batch1_install.py \
  docs/helpers/t11_management_restore.sh | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
sudo chmod -R go-w -- "$PAYLOAD"
sudo "$PY" "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" \
  --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$PANEL" "$UNIT" "$OVERLAY" "$HELPER" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=65m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback "$OVERLAY"
sudo systemctl is-active "$UNIT.timer"
sudo "$PY" "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
sudo sha256sum -c "$BACKUP/config-before.sha256"
sudo cmp "$CARD" "$PACKAGE/watch/zapret2_control.py"
```

При несовпадении базы до установки укажи путь. При проблеме после установки
используй rollback. Сверь off/off и активные VPN и панель. В веб-интерфейсе и
настольном разделе проверь, что запущенный режим отображается одинаково.

## 4. Одна штатная попытка и возврат

Если есть свежий подписанный URL, выполни одну штатную попытку Selective.
Из обычного Chrome с отключённым QUIC возьми свежий адрес CDN из DevTools,
введи его в панель и используй принятый набор доменов YouTube, /t/terms,
multisplit, интервал 180 с и retry 120 с. Перед редактированием формы выполни
sudo touch "$BACKUP/network-test-started". Закрой плеер перед стартом пробы.

- Таймаут страницы. В деталях есть этап TLS и сообщение, что CDN не запускался.
- Таймаут CDN. В деталях есть этап TLS. Сообщение о повторном таймауте
  появляется при наблюдённых двух отказах. При ответе HTTP 403 или 410
  ожидаются код и подсказка о свежем адресе из плеера.
- После подтверждённого закрытия прямого маршрута сверь отдельный результат VPN.
  Текст об успешной пробе VPN допустим при свежем подтверждении. При незакрытом
  gate карточка указывает, что возврат не подтверждён.
- При fallback запиши фактическую причину и перейди к возврату. Повтор парного
  WAN-опыта в этом проходе не требуется. Если старт успешен, используй
  [проверку медиапар, воспроизведения и параллельного VPN](GUI-T12-ACCEPTANCE.md#5-живое-видео-до-и-после-перемотки).
  Новый IP и попытку не подставляй при отказе. Если подходящего URL нет,
  отметь живой сценарий NOT_RUN и приложи тесты карточки.

Для ветки active выполни подготовку сборщика до запуска плеера:

```bash
read -r -p 'Selected NFQUEUE number: ' QUEUE
watch_run() {
  local name=$1 duration=$2
  shift 2
  sudo -v
  sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_probe_watch.py \
    --queue "$QUEUE" --seconds "$duration" --socket-stats "$@" >"$D/$name.jsonl" &
  WATCH_PID=$!
}
```

Выключи Selective и дождись off/off. Подтверди новый сеанс YouTube через VPN,
обычный сайт и панель. Если заявляешь дельту, используй
[снимки до и после свежей передачи](GUI-T12-ACCEPTANCE.md#6-возврат-живого-трафика-и-настроек).
Закрой браузер. При исправном слое оставь его через accept. При дефекте слоя
или восстановления выбери rollback.

```bash
RESTORE=accept
# Для возврата кода задай RESTORE=rollback.
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" "$RESTORE" "$OVERLAY"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-nfqws2.service xgw-zapret2.service -p ActiveState -p MainPID
sudo test -s "$BACKUP/restore-completed"
if [[ "$RESTORE" == accept ]]; then sudo cmp "$CARD" "$PACKAGE/watch/zapret2_control.py"; fi
```

Сверь off/off, VPN и панель, затем останови таймер командой sudo systemctl stop
"$UNIT.timer". Если он уже сработал, укажи итог возврата и фактически
установленные версии.

## 5. Публикация

Укажи CODE, точную ОС, Qt, результаты тестов, GUI_SEQUENCE, STATUS,
MEDIA_PATH, VPN_RETURN и RESTORE. Для каждой строки приведи факт или причину
FAIL, NOT_RUN или BLOCKED. GUI_SEQUENCE включает обе подписки, сохранение
границ, компактную раскладку и опрос API. Для STATUS запиши наблюдённую фазу
и отображаемый текст. Результаты фикстур и установленной машины перечисли
явно. Подписки, имена серверов, IP, токены, signed URL, квоты, маршруты и
скриншоты с такими данными остаются локально.

Опубликуй отчёт даже при блокере. Если подготовка прервалась, задай REPO,
BR=integration/zapret2-batch1 и D=$(mktemp -d) из checkout.

```bash
cd "$REPO"
git fetch origin "$BR"
git worktree add --detach "$D/report" FETCH_HEAD
cd "$D/report"
REPORT="docs/reports/$(date +%F)_gui-selective-status.md"
# Заполни отчёт по результатам.
git add -- "$REPORT"
git diff --cached --check
git diff --cached --stat
git commit -m "docs: report stable GUI sorting and Selective status acceptance"
git push origin "HEAD:refs/heads/$BR"
git ls-remote origin "refs/heads/$BR"
```

Если ветка продвинулась, перенеси коммит на актуальный FETCH_HEAD и повтори
обычный push. При совпадении имени отчёта используй свободное имя.
