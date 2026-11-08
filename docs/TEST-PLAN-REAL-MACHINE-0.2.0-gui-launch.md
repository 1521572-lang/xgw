# ThinkCentre: ярлык и значок открывают окно XGW

Исполнитель — GLM-5.3-Flash. Запускать **только после отчёта sub-expiry**: на машине должен стоять
33f7879. Код CODE (ASSUMPTIONS п. 344): ярлык «XGW» и значок в трее открывают окно (`xgw gui`), если
окно не запустилось — браузерную панель. Правая кнопка по ярлыку и меню значка — «Открыть в
браузере». Демон, Xray, sing-box и сеть не менялись.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не
кликает:** нажатия в разделе 6 — только владелец мышью. Нельзя: подписки, пул, ручной выбор,
«Обновить», замеры, настройки, WAN, LAN, Tailscale и сетевые правила; перезапуск демона, кроме
установки шага 5; `xgw net down`, перезагрузка, `--force`. В отчёт — только числа, признаки и
имена тестов: без имён серверов и подписок, адресов, доменов, кода входа, cookie, сумм файлов и
снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=45f3eae4d4972cef8f98f3aa001279b8f48dc0ba
BASE=33f7879e8e45a93e9dfa4d1f01d8c3256e30c732
D=$(mktemp -d "$HOME/xgw-guilaunch.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/gui_launch_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' 'f34e3a9b1af8e5d3c2418ace31d4cf9cd178f86d4d8fc45d1d99c828aeffa4a1' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидается `OK` и ровно пять строк: `src/xgw/cli.py`, `src/xgw/gui/app.py`, `src/xgw/install.py`,
`src/xgw/tray.py`, `src/xgw/trayapp.py`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`INFO state=…` (переписать), `OK prepare`, `helper_rc=0`. Записать числа OK/WARN/FAIL diag.
- `STOP installed_is_base` — стоит не 33f7879 (нет отчёта sub-expiry): установку не делать,
  отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты (от владельца, без sudo)

```bash
cd "$TARGET" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider tests/test_tray.py -k window 2>&1 | tail -1
for T in new base; do
  (cd "$D/$T" && QT_QPA_PLATFORM=offscreen PYTHONPATH=src timeout 900 python3 -m pytest -p no:cacheprovider tests/test_tray.py tests/test_install.py tests/test_gui_model.py tests/test_gui_listing.py tests/test_gui_qt.py >"$D/out-$T" 2>&1; echo "$T rc=$?")
  tail -1 "$D/out-$T"
  grep -E '^(FAILED|ERROR) tests/' "$D/out-$T" | sed 's/ - .*//' | sort >"$D/fails-$T"
done
echo "новые падения:"; comm -23 "$D/fails-new" "$D/fails-base"; echo "конец списка"
echo "упавшие на прежнем коде:"; cat "$D/fails-base"; echo "конец списка"
cd ~/xgw
```

Ожидается первая строка `6 passed, 16 deselected`, для new и base `rc=0` или `rc=1` и итог pytest.
Между `новые падения:` и `конец списка` — пусто. Имена упавших на прежнем коде — в отчёт. Новые
падения, другая первая строка или `rc=124` — записать, установку не делать, отчёт PARTIAL.

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить 45f3eae (ярлык и значок открывают окно XGW: пять файлов
из шага 1) поверх 33f7879 штатным установщиком? Установщик перезапустит демон и значок. Если on/HTTPS
не подтвердятся за 45 с, помощник сам вернёт 33f7879 и проверит связь. Затем проверка запуска, ваши
щелчки мышью и 10 минут наблюдения». Дождаться явного ответа, время записать приватно. Нет ответа
или отказ — INSTALL_NOT_RUN, перейти к шагу 8.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-guilaunch-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-guilaunch-deploy.log && break; sleep 5; done; cat /run/xgw-guilaunch-deploy.log'
```

Вторую команду можно повторять, в том числе после обрыва связи; установку второй раз не
запускать. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`,
`helper_rc=0`. Записать `at`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл: записать
  времена, перейти к шагу 8 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Запуск окна

В терминале графического сеанса владельца, не через sudo и не по SSH:

```bash
python3 -I "$H" launch
```

Команда повторяет команду ярлыка: два запуска подряд дают одно окно, третий выводит его вперёд.
Окно, открытое этой проверкой, она сама закрывает; открытое раньше — не трогает. Ожидаются
`OK not_root`, `OK graphic_session`, `OK shortcut_opens_window`, `OK shortcut_browser_action`,
`OK shortcut_login_action`, `INFO panel_http=… xdg_open=… default_browser=…` (переписать),
`INFO windows_before=…`, `OK launch_rc`, `OK window_started`, `OK one_window`,
`OK one_window_after_pause`, `OK second_launch_rc`, `OK still_one_window`, `OK launch`,
`helper_rc=0`. `STOP graphic_session` — запущено не из графического сеанса: повторить там. Другой
`STOP` — FAIL, записать шаг, не чинить.

Затем попросить владельца нажать мышью и записать да/нет; владельца нет — NOT_RUN:
1. меню приложений → «XGW»: открылось окно XGW;
2. щелчок по значку в трее: окно вышло вперёд, второго окна нет;
3. правая кнопка по значку: есть «Открыть XGW» и «Открыть в браузере»;
4. правая кнопка по ярлыку «XGW» → «Открыть в браузере»: страница панели открылась.

Если страница в пункте 4 не открылась, записать, что видно: браузер не запустился, браузер
запустился и показал ошибку (её вид, без адреса) или страницу входа. Это не FAIL окна: причина ещё
не установлена. Окно владелец закрывает сам.

## 7. Одно наблюдение, 10 минут (только чтение)

```bash
sudo python3 -I "$H" observe 10 2>&1 | tee "$D/observe.txt"
```

Ожидаются `INFO window_min=… states=[(состояние, число замеров)…] status_age_max_s=…`, `OK
config_unchanged`, `OK on`, `OK https`, `OK observe`, `helper_rc=0`. Один замер — 15 с. DEGRADED
проверку не останавливает; причину не придумывать, в отчёт — только число замеров.
`WARN status_age` — записать `status_age_max_s`, FAIL по этой части. `STOP config_unchanged`, `STOP
on`, `STOP https` — сразу владельцу, ничего не чинить.

## 8. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет. Каталог /run/xgw-guilaunch-install остаётся до
перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-gui-launch-ДАТА.md` в freepool, одна страница, без
пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем
`git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; пять файлов (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); state:
Тесты: первая строка; new и base (rc, итог); новые падения (пусто/какие); имена упавших на base:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Запуск: helper_rc; panel_http; xdg_open; default_browser; windows_before; первый STOP (если был):
Щелчки владельца 1–4 (да/нет/NOT_RUN); что видно, если страница не открылась:
Наблюдение 10 мин: helper_rc; состояния с числом замеров; status_age_max_s; config_unchanged:
Конечное: on/HTTPS, diag после:
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит
на машине:
```
