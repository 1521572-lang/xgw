# ThinkCentre: поле User-Agent и набор «как Happ» в окне

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 345): в окне XGW при добавлении подписки
можно указать User-Agent или включить «Как Happ»; в «Изменить» есть кнопка «Запрашивать как Happ».
Шлюз запрашивает подписку с заголовками Happ и своим постоянным идентификатором. Примет ли набор
конкретный поставщик, заранее неизвестно: это и проверяется.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не
кликает:** нажатия шага 6 — только владелец мышью. Нельзя: подписки (кроме действия владельца),
пул, ручной выбор, «Обновить», замеры, настройки, WAN, LAN, Tailscale и сетевые правила; перезапуск
демона, кроме установки шага 5; `xgw net down`, перезагрузка, `--force`. **Адрес подписки вводит
только владелец, в отчёт, журнал исполнителя и чат он не попадает.** В отчёт — только числа,
признаки, виды причин и имена тестов: без имён серверов и подписок, адресов, доменов,
идентификатора шлюза, заголовков, сумм файлов и снимков экрана. panel.json не выводить.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=4e759633327b2fc01f0b7c752593e2a2aa20288d
BASE=45f3eae4d4972cef8f98f3aa001279b8f48dc0ba
D=$(mktemp -d "$HOME/xgw-happ.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/happ_preset_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '703730a7ecf6dae8bfa2e64969398f6a3e2ae18548af98e2fe3717a223ab15fe' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидается `OK` и ровно три строки: `src/xgw/gui/pages.py`, `src/xgw/managed.py`,
`src/xgw/watch/panel.py`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`INFO state=… members=… spares=… subscriptions=…` (переписать), `OK prepare`, `helper_rc=0`.
Записать числа OK/WARN/FAIL diag и режим пула.
- `STOP installed_is_base` — стоит не 45f3eae: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты (от владельца, без sudo)

```bash
cd "$TARGET" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider tests/test_panel.py -k happ 2>&1 | tail -1
for T in new base; do
  (cd "$D/$T" && QT_QPA_PLATFORM=offscreen PYTHONPATH=src timeout 900 python3 -m pytest -p no:cacheprovider tests/test_panel.py tests/test_managed.py tests/test_gui_model.py tests/test_gui_listing.py tests/test_gui_qt.py >"$D/out-$T" 2>&1; echo "$T rc=$?")
  tail -1 "$D/out-$T"
  grep -E '^(FAILED|ERROR) tests/' "$D/out-$T" | sed 's/ - .*//' | sort >"$D/fails-$T"
done
echo "новые падения:"; comm -23 "$D/fails-new" "$D/fails-base"; echo "конец списка"
echo "упавшие на прежнем коде:"; cat "$D/fails-base"; echo "конец списка"
cd ~/xgw
```

Ожидается первая строка `2 passed, 59 deselected`, для new и base `rc=0` или `rc=1` и итог pytest.
Между `новые падения:` и `конец списка` — пусто. Имена упавших на прежнем коде — в отчёт. Новые
падения, другая первая строка или `rc=124` — записать, установку не делать, отчёт PARTIAL.

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить 4e75963 (поле User-Agent и набор «как Happ»: три файла
из шага 1) поверх 45f3eae штатным установщиком? Установщик перезапустит демон. Если on/HTTPS не
подтвердятся за 45 с, помощник сам вернёт 45f3eae и проверит связь. Затем ваши действия мышью и 15
минут наблюдения». Дождаться явного ответа, время записать приватно. Нет ответа или отказ —
INSTALL_NOT_RUN, перейти к шагу 8.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-happ-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-happ-deploy.log && break; sleep 5; done; cat /run/xgw-happ-deploy.log'
```

Вторую команду можно повторять, в том числе после обрыва связи; установку второй раз не
запускать. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`,
`helper_rc=0`. Записать `at`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL, повтор только по указанию владельца;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл: записать
  времена, перейти к шагу 8 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Действие владельца (мышью)

Попросить владельца открыть окно XGW → «Подписки» и выбрать один путь:
- **новая подписка:** вставить её адрес, поставить галочку «Как Happ», нажать «Добавить»;
- **подписка, добавленная раньше в окне или панели:** «…» → «Изменить» → «Запрашивать как Happ».
  Сохранённый набор этой подписки при этом сбросится, как при любом «Изменить».

Подписка из config.toml этим способом не меняется. Владелец говорит «готово» или «не буду». Отказ
или нет ответа за 10 минут — наблюдение всё равно запустить: `NOT_RUN happ` не ошибка.

## 7. Одно наблюдение, 15 минут (только чтение)

Сразу после ответа владельца; ничего не нажимать.

```bash
sudo python3 -I "$H" observe 15 2>&1 | tee "$D/observe.txt"
```

Ожидаются `INFO from=install`, `INFO window_min=… states=[(состояние, число замеров)…]
status_age_max_s=…`, `OK fields`, по строке `INFO sub N state=… set_age_s=… reason=… happ=… hwid=…`
на подписку, `OK age_consistent`, `INFO urls_checked=…`, `OK no_urls_in_status`, `OK
no_hwid_in_status`, `INFO happ_subs=… same_hwid=…`, `OK config_unchanged`, `OK on`, `OK https`.
Один замер — 15 с. Итог по строке с `happ=yes hwid=yes`:
- `state=fresh reason=none` — **поставщик принял набор**, серверы получены;
- `reason=junk`, `no_servers`, `html` или `empty` — поставщик набор не принял: записать вид
  причины, это не FAIL кода;
- `reason=other` — ошибка сети или HTTP-отказ: записать, не чинить.

`same_hwid` должно быть True. `helper_rc=4` с `NOT_RUN happ` — набор не включён: NOT_RUN по нему,
PASS по регрессии, если on/HTTPS в норме. `helper_rc=4` с `NOT_RUN fetch` — подписка с установки не
опрашивалась: NOT_RUN по ней. `STOP fields` / `STOP age_consistent` / `STOP status_line` — FAIL, не
чинить. `STOP no_urls_in_status` / `STOP no_hwid_in_status` — **сразу владельцу**, файл статуса
никуда не копировать. `WARN status_age` — записать `status_age_max_s` и причину не придумывать.
`STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

## 8. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же. Каталог /run/xgw-happ-install
остаётся до перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-happ-preset-ДАТА.md` в freepool, одна страница, без
пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем
`git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; три файла (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); state, members, spares, subscriptions:
Тесты: первая строка; new и base (rc, итог); новые падения (пусто/какие); имена упавших на base:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Действие владельца: новая подписка / «Изменить» / NOT_RUN:
Наблюдение 15 мин: helper_rc; состояния с числом замеров; status_age_max_s; строки INFO sub;
  happ_subs; same_hwid; no_urls_in_status; no_hwid_in_status; config_unchanged:
Принял ли поставщик набор (да / нет и вид причины / NOT_RUN):
Конечное: on/HTTPS, diag после, режим пула без изменений (да/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит
на машине:
```
