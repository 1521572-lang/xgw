# ThinkCentre: сохранённый набор истёкшей подписки (доработка волны 4)

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 343): если опрос подписки не удался и срок
из её сохранённых данных уже прошёл, серверы этой подписки из кэша не берутся. Такая подписка не
мешает применять серверы остальных; кэш не стирается, удачный опрос всё возвращает. При удачном
ответе и у подписки без срока поведение прежнее.

Вызвать истечение подписки нельзя. Если оно само не наступит, живой случай — NOT_RUN, поведение
проверяется тестами шага 3, а на машине — обычный путь и статус. Обход блокировок и невидимость
для ТСПУ здесь не проверяются.

Можно: терминал, `xgw status`, `xgw diag --no-net`, окно и панель (только смотреть). Нельзя:
подписки, пул, ручной выбор, «Обновить», «Проверить запасные», замеры скорости, настройки, WAN,
LAN, Tailscale и сетевые правила; перезапуск демона, кроме установки шага 5; `xgw net down`,
перезагрузка, `--force`, сторонние замеры и pcap. В отчёт — только числа, номера подписок, виды
причин и имена тестов: без имён серверов и подписок, адресов, доменов, стран, тегов, SNI, сумм
файлов и снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=33f7879e8e45a93e9dfa4d1f01d8c3256e30c732
BASE=55aa5c965d0c1cd5518b339a51ccd6d7768034b9
D=$(mktemp -d "$HOME/xgw-subexpiry.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/sub_expiry_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '126f2eeff80fdbae0da0828e4c2bd8e1720c017036cbb50e20cee0c91c1ff861' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидается `OK` и ровно три строки: `src/xgw/engine.py`, `src/xgw/store.py`,
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
- `STOP installed_is_base` — стоит не 55aa5c9: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты (от владельца, без sudo)

Тесты причин и срока, затем файлы сборки и команд на новом и прежнем коде.

```bash
cd "$TARGET" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider \
  tests/test_subscription_reasons.py 2>&1 | tail -1
for T in new base; do
  (cd "$D/$T" && PYTHONPATH=src timeout 600 python3 -m pytest -p no:cacheprovider tests/test_engine.py tests/test_cli.py >"$D/out-$T" 2>&1; echo "$T rc=$?")
  tail -1 "$D/out-$T"
  grep -E '^(FAILED|ERROR) tests/' "$D/out-$T" | sed 's/ - .*//' | sort >"$D/fails-$T"
done
echo "новые падения:"; comm -23 "$D/fails-new" "$D/fails-base"; echo "конец списка"
echo "упавшие на прежнем коде:"; cat "$D/fails-base"; echo "конец списка"
cd ~/xgw
```

Ожидается `12 passed`, затем для new и base `rc=0` или `rc=1` и итоговая строка pytest. Между
`новые падения:` и `конец списка` — пусто. Имена упавших на прежнем коде переписать в отчёт:
прошлый отчёт их не назвал. Если новые падения есть, первая строка не `12 passed` или есть
`rc=124` — записать, установку не делать, отчёт PARTIAL.

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить 33f7879 (сохранённый набор истёкшей подписки не
используется: три файла из шага 1) поверх 55aa5c9 штатным установщиком? Установщик перезапустит
демон. Если on/HTTPS не подтвердятся за 45 с, помощник сам вернёт 55aa5c9 и проверит связь. Затем
15 минут наблюдения». Дождаться явного ответа, время записать приватно. Нет ответа или отказ —
INSTALL_NOT_RUN, перейти к шагу 7.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-subexpiry-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-subexpiry-deploy.log && break; sleep 5; done; cat /run/xgw-subexpiry-deploy.log'
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

Ожидаются `INFO from=install`, `INFO window_min=… states=[(состояние, число замеров)…]
status_age_max_s=…`, `OK fields`, по строке `INFO sub N state=… set_age_s=… reason=…` на подписку,
`OK age_consistent`, `INFO expired_seen=…`, `INFO urls_checked=…`, `OK no_urls_in_status`, `OK
config_unchanged`, `OK on`, `OK https`. Один замер — 15 с. Значения `state`: `fresh` — обновилась
после установки; `cached` — опрос не удался (тогда ещё `OK status_line`); `stale` — опроса с
установки ещё не было. Значения `reason`: `none`, `expired`, `html`, `empty`, `junk`,
`no_servers`, `other`. Итог:
- `OK subscriptions_reported`, `helper_rc=0` — PASS по обычному пути. Переписать строки `INFO
  sub` и состояния с числом замеров. При `expired_seen=0` — ещё `NOT_RUN expired`: живого случая
  не было, это не ошибка;
- `expired_seen` больше 0 и `OK expired_line` — настоящий случай: записать вид причины и не
  чинить;
- `NOT_RUN fetch`, `helper_rc=4` — какая-то подписка не опрашивалась: NOT_RUN по ней, PASS по
  регрессии, если on/HTTPS в норме;
- `STOP fields` / `STOP age_consistent` / `STOP status_line` / `STOP expired_line` — FAIL, дальше
  не чинить, записать шаг STOP;
- `STOP no_urls_in_status` — **сразу владельцу**: адрес подписки попал в статус, файл статуса и
  его содержимое никуда не копировать;
- `WARN status_age` — запись status.json дольше 25 с: записать `status_age_max_s`, FAIL по этой
  части;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

DEGRADED сам по себе проверку не останавливает. Не называть его «обычной волной» и не писать о
причине: в отчёт — только число замеров.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же, что в шаге 2. Каталог
/run/xgw-subexpiry-install остаётся до перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-sub-expiry-ДАТА.md` в freepool, одна страница, без
пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем
`git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; три файла (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); state, members, spares, subscriptions;
  пул; ручной выбор:
Тесты: первая строка; new и base (rc, итог); новые падения (пусто/какие); имена упавших на base:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Наблюдение 15 мин: helper_rc; from; состояния с числом замеров; status_age_max_s; строки INFO sub;
  expired_seen; urls_checked; no_urls_in_status; config_unchanged:
Конечное: on/HTTPS, diag после, режим пула без изменений (да/нет), ручной выбор (есть/нет):
Границы: истечение подписки могло не наступить; обход блокировок не проверялся:
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит
на машине:
```
