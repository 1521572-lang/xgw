# ThinkCentre: причина использования кэша подписки (волна 4)

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 342): страница HTML, пустой ответ, заглушка
из служебных адресов и сбой сети по-прежнему не затирают рабочий набор подписки, но причина
теперь своя. `status.json` у подписки получил `last_ok_ts`, `set_age_s`, `cache_reason`, а `xgw
status` — строку «не обновилась (причина) — в работе набор от …». Второго кэша нет, зеркал нет.

Вызвать сбой подписки нельзя. Если подписки обновятся нормально, проверяются успешный путь и поля
статуса, а поведение при сбое — тестами шага 3. Обход блокировок и невидимость для ТСПУ здесь
не проверяются.

Можно: терминал, `xgw status`, `xgw diag --no-net`, окно и панель (только смотреть). Нельзя:
подписки, пул, ручной выбор, «Обновить», «Проверить запасные», замеры скорости, настройки, WAN,
LAN, Tailscale и сетевые правила; перезапуск демона, кроме установки шага 5; `xgw net down`,
перезагрузка, `--force`, сторонние замеры и pcap. В отчёт — только числа, номера подписок и виды
причин: без имён серверов и подписок, адресов, доменов, стран, тегов, SNI, сумм файлов и снимков
экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=55aa5c965d0c1cd5518b339a51ccd6d7768034b9
BASE=6a3a8d6131844394d8c9254030f081427e4b6d3d
D=$(mktemp -d "$HOME/xgw-substatus.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/sub_status_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '09c9a8e6df46d0e25625e05092a9ab626ecf09ef9329aee86a8eec3812d0762e' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидается `OK` и ровно три строки: `src/xgw/daemon.py`, `src/xgw/engine.py`,
`src/xgw/watch/status.py`. Иначе — STOP, сообщить владельцу. Путь D записать приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`INFO state=… members=… spares=… subscriptions=…` (переписать), `config_sha=…` (только
приватно), `OK prepare`, `helper_rc=0`. Записать числа OK/WARN/FAIL diag, режим пула и есть ли
ручной выбор (да/нет).
- `STOP installed_is_base` — стоит не 6a3a8d6: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты (от владельца, без sudo)

Новые тесты причин, затем файлы демона, сборки и команд на новом и прежнем коде (до 25 минут на
прогон).

```bash
cd "$TARGET" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider \
  tests/test_subscription_reasons.py 2>&1 | tail -1
for T in new base; do
  (cd "$D/$T" && PYTHONPATH=src timeout 1500 python3 -m pytest -p no:cacheprovider tests/test_daemon.py tests/test_engine.py tests/test_cli.py >"$D/out-$T" 2>&1; echo "$T rc=$?")
  tail -1 "$D/out-$T"
  grep -E '^(FAILED|ERROR) tests/' "$D/out-$T" | sed 's/ - .*//' | sort >"$D/fails-$T"
done
echo "новые падения:"; comm -23 "$D/fails-new" "$D/fails-base"; echo "конец списка"
cd ~/xgw
```

Ожидается `5 passed`, затем для new и base `rc=0` или `rc=1` (падения старые) и итоговая строка
pytest. Между `новые падения:` и `конец списка` — пусто. Переписать итоговые строки. Если в
списке что-то есть, первая строка не `5 passed` или есть `rc=124` — записать, установку не
делать, отчёт PARTIAL.

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить 55aa5c9 (причина кэша подписки в статусе: три файла из
шага 1) поверх 6a3a8d6 штатным установщиком? Установщик перезапустит демон. Если on/HTTPS не
подтвердятся за 45 с, помощник сам вернёт 6a3a8d6 и проверит связь. Затем 15 минут наблюдения».
Дождаться явного ответа, время записать приватно. Нет ответа или отказ — INSTALL_NOT_RUN,
перейти к шагу 7.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-substatus-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-substatus-deploy.log && break; sleep 5; done; cat /run/xgw-substatus-deploy.log'
```

Вторую команду можно повторять, в том числе после обрыва связи; установку второй раз не
запускать. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`,
`helper_rc=0`. Записать `at`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл: записать
  времена, перейти к шагу 7 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Одно наблюдение, 15 минут (только чтение)

Сразу после `helper_rc=0` шага 5; ничего не нажимать в панели и окне.

```bash
sudo python3 -I "$H" observe 15 2>&1 | tee "$D/observe.txt"
```

Ожидаются `INFO from=install`, `INFO window_min=… states=… status_age_max_s=…`, `OK fields`, по
строке `INFO sub N state=… set_age_s=… reason=…` на подписку, `OK age_consistent`, `INFO
urls_checked=…`, `OK no_urls_in_status`, `OK config_unchanged`, `OK on`, `OK https`.
Значения `state`: `fresh` — обновилась после установки; `cached` — опрос не удался, работает
прежний набор (тогда ещё `OK status_line`); `stale` — опроса с установки ещё не было. Значения
`reason`: `none`, `html`, `empty`, `junk`, `no_servers`, `other` (ошибка сети и прочее). Итог:
- `OK subscriptions_reported`, `helper_rc=0` — PASS. Переписать строки `INFO sub`. Строка
  `cached` — не ошибка: настоящий случай использования кэша, записать вид причины;
- `NOT_RUN fetch`, `helper_rc=4` — какая-то подписка не опрашивалась: NOT_RUN по ней, PASS по
  регрессии, если состояния и on/HTTPS в норме;
- `STOP fields` / `STOP age_consistent` / `STOP status_line` — FAIL, дальше не чинить,
  записать шаг STOP;
- `STOP no_urls_in_status` — **сразу владельцу**: адрес подписки попал в статус, файл статуса и
  его содержимое никуда не копировать;
- `WARN status_age` — запись status.json дольше 25 с: записать `status_age_max_s`, FAIL по этой
  части;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; пул тот же, что в шаге 2. Ручной выбор владелец
ставит сам, когда захочет. Каталог /run/xgw-substatus-install остаётся до перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-sub-status-ДАТА.md` в freepool, одна страница, без
пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем
`git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; три файла (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); state, members, spares, subscriptions;
  пул; ручной выбор:
Тесты: первая строка; new и base (rc, итог); новые падения (пусто/какие):
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Наблюдение 15 мин: helper_rc; from; states; status_age_max_s; строки INFO sub; urls_checked;
  no_urls_in_status; config_unchanged:
Конечное: on/HTTPS, diag после, пул без изменений (да/нет), ручной выбор (есть/нет):
Границы: настоящий сбой подписки мог не случиться; обход блокировок не проверялся:
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит
на машине:
```
