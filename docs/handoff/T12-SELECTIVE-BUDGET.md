# ThinkCentre — бюджет Selective, отказ и живой контроль VPN

Целевая машина — Ubuntu 24.04 LTS. Код 553de562572c192c78454c927816155b02efc28b.
Ориентир — 75–110 минут при доступных терминале, sudo, браузере и Qt.
Один проход охватывает тесты, доставку, оба интерфейса, нормальный и малый
бюджет, один запуск Selective со штатными настройками, восстановление и отчёт.
При успешном старте сюда же входит проверка видео 15+5 минут.

[Сортировка и карточка отказа приняты](../reports/2026-11-18_gui-selective-status.md).
Последняя попытка завершилась на TLS страницы YouTube, поэтому CDN и прямой
медиапоток не наблюдались. Обычный VPN и новый просмотр через VPN подтверждены.
Здесь проверяется расход резервов и работа VPN при отказе. Доказательство
медиамаршрута требуется в ветке, где штатный Selective станет active.

Flash сама запускает опубликованные команды и выполняет проверки браузера и GUI.
При отсутствии терминала, sudo или рабочего стола запроси доступ. Публикуй один
обезличенный отчёт даже при блокере. Изменения исходников и тестов выполняет Codex.
Сохраняй данные опыта приватно. Для проверки достаточно счётчиков и журналов.

## 1. Подготовка и наборы на Ubuntu

Работай в Bash от пользователя рабочего стола. Для тестов используй установленный
pytest и PyQt6 или существующий venv через XGW_TEST_PYTHON. Вход в панель выполни
штатным способом. Проверь исходный обычный сайт и свежий сеанс через VPN, off/off
и отсутствие активных воркеров. Запиши PRETTY_NAME, версию Qt, время UTC и
исходный VPN-выход локально.

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
printf '%s\n' "$PRETTY_NAME"
REPO=$(git rev-parse --show-toplevel)
BR=integration/zapret2-batch1
CODE=553de562572c192c78454c927816155b02efc28b
OLD=dfccea8c88418e839532ccaec40f85b019669f51
GUI_BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git cat-file -e "$GUI_BASE^{commit}" || git fetch origin "$GUI_BASE"
D=$(mktemp -d "$HOME/xgw-selective-budget.XXXXXXXX")
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
"$TEST_PY" -m pytest -q tests/test_panel.py -k 'zapret2'
"$TEST_PY" -m pytest -q tests/test_zapret2.py -k exhausted_budget
node --check src/xgw/ui/zapret2.js
bash -n docs/helpers/t11_management_restore.sh
```

Покажи отдельно результат теста test_exhausted_budget_preserves_vpn_control_and_reopens_after_utc_boundary.
Он проверяет закрытие маршрута, расход на одну VPN-пробу, отсутствие нового
запуска воркера и возобновление после UTC-границы на управляемых часах фикстуры.
Второй набор сверяет оба авторизованных API, ограничения сессии и команды
панели. Ошибку до установки зафиксируй с именем и сообщением теста.

Qt-прогон использует копию установленного релиза, чтобы учесть все принятые
накладки. Исходный GUI в этой фазе работает как обычно.

```bash
GUI="/opt/xgw/gui/releases/$GUI_BASE"
GUI_FILE=src/xgw/gui/zapret2.py
mkdir -p "$D/gui/src" "$D/gui/vpn_ui" "$D/gui/tests/fixtures/gui"
cp -R "$GUI/vpn_ui/." "$D/gui/vpn_ui/"
cp -R "$GUI/src/." "$D/gui/src/"
cp "$GUI_FILE" "$D/gui/$GUI_FILE"
cp tests/test_vpn_ui_sidebar.py "$D/gui/tests/"
git show "$GUI_BASE:tests/test_vpn_ui_xgw.py" >"$D/gui/tests/test_vpn_ui_xgw.py"
git show "$GUI_BASE:tests/fixtures/gui/state-work.json" >"$D/gui/tests/fixtures/gui/state-work.json"
"$TEST_PY" -c 'import PyQt6.QtWidgets, PyQt6.QtSvg'
(
  cd "$D/gui"
  QT_QPA_PLATFORM=offscreen PYTHONPATH="$D/gui:$D/gui/src" "$TEST_PY" \
    -m pytest -q tests/test_vpn_ui_sidebar.py tests/test_vpn_ui_xgw.py
)
```

Ожидается отсутствие пропусков. Если блокируется только Qt, запиши причину.
Можно провести отдельную серверную проверку без --gui в prepare. Тогда после
серверной установки сверяй пять файлов и оставь GUI как есть.

## 2. Установка пакета с возвратом

Установщик сверяет байты с принятой базой. Комплект состоит из пяти файлов
службы и одного файла окна. При несовпадении исходного файла укажи его путь.
Проверь off/off непосредственно перед установкой. Для живых фаз действует
таймер 95 минут. Оставь последние 10 минут на возврат.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/selective-budget-$CODE"
BACKUP="/var/lib/xgw/handoff/selective-budget-$CODE"
UNIT=xgw-selective-budget-rollback
OVERLAY=--selective-budget
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
CORE=(src/xgw/zapret2.py src/xgw/watch/panel.py src/xgw/watch/zapret2_control.py
      src/xgw/ui/zapret2.html src/xgw/ui/zapret2.js)
GUI_ARGS=(--gui "$GUI")
# При блокере Qt задай GUI_ARGS=() для доставки только серверной части.
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base" "$PAYLOAD/gui_base"
git archive "$OLD" "${CORE[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$OLD" "$GUI_FILE" | sudo tar --no-same-owner -x -C "$PAYLOAD/gui_base"
git archive "$CODE" "${CORE[@]}" "$GUI_FILE" docs/helpers/desync_batch1_install.py \
  docs/helpers/t11_management_restore.sh | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
sudo chmod -R go-w -- "$PAYLOAD"
sudo "$PY" "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" --package "$PACKAGE" \
  "${GUI_ARGS[@]}" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$PANEL" "$UNIT" "$OVERLAY" "$HELPER" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=95m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback "$OVERLAY"
sudo systemctl is-active "$UNIT.timer"
```

Если доставляется GUI, закрой действующее окно штатно. Примени и сверь пакет.

```bash
sudo "$PY" "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
sudo sha256sum -c "$BACKUP/config-before.sha256"
check_installed() {
  for f in "${CORE[@]}"; do sudo cmp "$f" "$PACKAGE/${f#src/xgw/}"; done
  if (( ${#GUI_ARGS[@]} )); then sudo cmp "$GUI_FILE" "$GUI/$GUI_FILE"; fi
}
check_installed
systemctl is-active xgw.service
```

Для установленного GUI заново открой systemd-run --user --collect xgw gui.
При проблеме после установки переходи к rollback в §6.

## 3. Исходное состояние и согласованность интерфейсов

1. Открой /zapret2 после полной перезагрузки. Проверь широкое окно и мобильную
   ширину около 390 px. У отложенного старого окна проверь возврат к вкладке.
   В настольном разделе «Домены и проверки» сверь остаток и 00:00 UTC.
   Кратко проверь уже принятый переход «Серверы → Мбит/с» после опроса API.
2. Из авторизованного браузера возьми текущие /api/state и
   /api/zapret2/overview. В обоих probe_budget совпадает при отсутствии активных проб.
   Сверь spent_bytes, limit_bytes, remaining_bytes=max(0,limit_bytes-spent_bytes)
   и resets_at. У новой сессии без авторизации overview возвращает 401.
   При off, stale или смене ревизии поле последнего HTTPS-успеха отсутствует
   либо равно null. Информация о бюджете основана на чтении общего журнала.
3. Сверь бюджет до и после двух опросов в off. Резервированные байты остаются
   теми же. При настройке 256 МиБ и интервале 180 с плановая пара требует
   0,5 МиБ. Повтор CDN при наличии условий и контроль VPN резервируют
   по 0,25 МиБ. В отчёте укажи резервы по наблюдениям отдельно от медиабайтов.

## 4. Нормальный бюджет и живой результат

Подготовь свежий подписанный CDN-адрес из тестового Chrome с выключенным QUIC.
В off сохрани URL и страницу /t/terms, multisplit, шесть доменов YouTube,
интервал 180 с, retry 120 с и 256 МиБ. До записи отметь начало сетевого теста.
URL хранится только в панели и приватной записи.

```bash
sudo touch "$BACKUP/network-test-started"
read -r -p 'Selected NFQUEUE number: ' QUEUE
watch_run() {
  local name=$1 duration=$2
  shift 2
  sudo -v
  sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_probe_watch.py \
    --queue "$QUEUE" --seconds "$duration" --socket-stats "$@" >"$D/$name.jsonl" &
  WATCH_PID=$!
}
watch_run normal 110
```

После первой записи сборщика один раз включи Selective через панель.
Сверь ревизию и результат. Запиши остаток до старта и после первого исхода,
затем отдельно сумму после VPN-контроля или встроенного повтора, если удалось
увидеть отдельные значения. При таймауте страницы CDN остаётся без результата,
плановая пара уже зарезервирована. При CDN-таймауте допустим один встроенный
повтор в рамках бюджета. Сопоставь дельту с событием и UTC-границей.
Если выполнились дополнительные штатные циклы, перечисли их отдельно.

- При fallback до active сверь фазу и статус в двух UI, проверь обычный VPN
  и перейди к §5 после off. Укажи MEDIA_PATH=NOT_RUN.
- При active сопоставь свежий last_transport_ok_at с результатом пробы и
  следи за двумя перепроверками по той же ревизии. Выполни [проверку живого
  видео и медиапар](GUI-T12-ACCEPTANCE.md#5-живое-видео-до-и-после-перемотки)
  используя watch_run из этого задания. Перед стартом, в середине при необходимости
  и после перемотки собери по 180 с. Цель — 15 минут пригодного 720p и ещё 5
  после перемотки, свежие CDN-байты, принятые пары Xray/NFQUEUE и подтверждённый
  VPN-выход обычного сайта в том же окне. Одна успешная HTTPS-проба даёт время
  последнего HTTPS-успеха. Для факта воспроизведения нужны данные плеера.
- При естественном отказе после успеха время последнего успешного HTTPS остаётся
  доступным для той же ревизии. При смене настроек старая отметка исчезает.
  При заранее истёкшем адресе допустима проверка формы без старта. Используй
  [уже принятую процедуру для expire=1](GUI-T12-ACCEPTANCE.md#3-установка-backend-и-проверка-формы).

## 5. Малый бюджет и прекращение попыток

После off/off и нового рабочего VPN-сеанса возьми актуальные spent_bytes
и resets_at из overview. Сократи лимит через форму, сохранив свежие адреса
в off. Для воспроизводимого выбора лимита вычисли следующий целый МиБ.

```bash
read -r -p 'spent_bytes from the authenticated API: ' SPENT
[[ "$SPENT" =~ ^[0-9]+$ ]]
LIMIT=$(( SPENT / 1048576 + 1 ))
if (( LIMIT > 1024 )); then LIMIT=1024; fi
printf 'Limit for the test in MiB: %s\n' "$LIMIT"
```

1. Проверь, что счётчик резервов не обнуляется при сохранении политики, а новый
   предел одинаков в двух API и обоих UI. При остатке меньше 786432 байт панель
   показывает блокер Selective. Кнопка off доступна. Воркеры inactive.
2. При остатке от 786432 байт запусти один штатный сценарий по тому же адресу.
   Проверь списание и остаток. После первой попытки оставь выбранный режим только
   до следующего запланированного цикла (до 180 с плюс один шаг демона) для
   проверки лимита. Для исчерпания ожидаются reason=probe_budget, снятие правила,
   неактивный воркер и отсутствие новых резервов при повторных опросах. Если
   Selective был active, проверь итог контрольной пробы VPN и допуск резерва.
   Сравни счётчик рабочего PID или события старта до и после ожидания. Достаточно
   двух снимков состояния и одного интервала retry после исчерпания.
3. Подтверди, что рабочий VPN пропускает новую передачу YouTube и обычный сайт.
   Сними [дельту до и после новой передачи](GUI-T12-ACCEPTANCE.md#6-возврат-живого-трафика-и-настроек).
   Запиши фактический результат, включая случаи, где кнопка заблокировала запуск
   ещё в off. Если ночь пересекается с окном опыта, можно сверить обновление
   resets_at и новый остаток. Границу, которой не было в живом времени, укажи
   как NOT_RUN с результатом часовой фикстуры. Часы и рабочую базу вручную не меняй.

## 6. Возврат и отчёт

Выключи Selective, проверь off/off, неактивность воркеров, VPN и панель. Закрой
тестовый Chrome, дождись завершения ограниченных сборщиков. Восстанови исходную
конфигурацию. При успешной установке используй accept, при регрессии rollback.
Уже зарезервированный бюджет относится к реальным попыткам этого дня и остаётся
в журнале. Настройки возвращаются побайтово.

```bash
RESTORE=accept
# Для возврата кода задай RESTORE=rollback.
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" "$RESTORE" "$OVERLAY"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-nfqws2.service xgw-zapret2.service -p ActiveState -p MainPID
sudo test -s "$BACKUP/restore-completed"
if [[ "$RESTORE" == accept ]]; then check_installed; fi
```

После сверки свежего VPN-сеанса, off/off, хэшей и работы панели останови
таймер командой sudo systemctl stop "$UNIT.timer". При сработавшем таймере
проверь фактические байты и оставленные версии. Перезапусти GUI после
rollback, если применялась его накладка. При остановке до установки
зафиксируй исходное состояние и переходи сразу к публикации.

В отчёте укажи CODE, ОС и Qt, результаты и конечное состояние. Таблица должна
охватывать TESTS, INSTALL, API_WEB_QT, PROBE_ACCOUNTING, BUDGET_STOP,
UTC_ROLLOVER, START_RECHECK, MEDIA_PATH, VPN_RETURN, RESTORE. Для каждого поля
укажи PASS, FAIL, PARTIAL, NOT_RUN или BLOCKED и конкретное наблюдение.
Различи результаты фикстур и живого шлюза. IP, имена узлов, подписки, токены,
CDN URL и сырые файлы остаются локально.

Опубликуй один отчёт автоматически. Если подготовка остановилась рано, задай
REPO из checkout, BR=integration/zapret2-batch1 и D=$(mktemp -d).

```bash
cd "$REPO"
git fetch origin "$BR"
git worktree add --detach "$D/report" FETCH_HEAD
cd "$D/report"
REPORT="docs/reports/$(date +%F)_selective-budget.md"
# Заполни "$REPORT" наблюдениями.
git add -- "$REPORT"
git diff --cached --check
git diff --cached --stat
git commit -m "docs: report Selective budget and VPN recovery acceptance"
git push origin "HEAD:refs/heads/$BR"
git ls-remote origin "refs/heads/$BR"
```

При продвижении ветки перенеси коммит отчёта на свежий FETCH_HEAD и повтори
обычный push. При совпадении имени файла выбери свободное имя.
