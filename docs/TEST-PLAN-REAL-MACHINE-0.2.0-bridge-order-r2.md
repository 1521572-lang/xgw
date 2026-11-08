# ThinkCentre: смена поколения sing-box без мостов в работе (повтор bridge-order)

Исполнитель — GLM-5.3-Flash. Отчёт bridge-order (b72f3ca) — FAIL, на машине стоит 688f2da.
Сразу после установки пересборка отказала с «мостов проверено 0 из 0». Причина (ASSUMPTIONS
п. 339): все серверы машины сейчас на Xray, а sing-box держит заготовленные варианты для
лестницы профилей. Xray не ведёт трафик ни через один мост к sing-box, а проверка нового
поколения требовала ответа хотя бы через один такой мост — отказ был всегда, и вместе с ним
отклонялась вся сборка: новые запасные не применялись (4 вместо ~54). Код CODE: нет мостов в
работе — проверка проходит («мостов в работе нет»); есть — как в п. 338 (работающие первыми,
20 с на мост). Тесты поколений теперь идут и от владельца без sudo. Помощник читает журнал с
начала установки. Невидимость для ТСПУ не проверяется.

Можно: терминал, `xgw status`, `xgw diag --no-net`, `journalctl -u xgw`, окно и панель (только
смотреть). Нельзя: подписки, пул, ручной выбор, «Обновить», «Проверить запасные», замеры
скорости, настройки, WAN, LAN, Tailscale и сетевые правила; перезапуск демона, кроме установки
шага 5; `xgw net down`, перезагрузка, `--force`, сторонние замеры и pcap. Пересборку не
вызывать: она идёт сама сразу после установки. В отчёт — только числа, слова состояний и виды
отказов: без имён серверов и подписок, адресов, доменов, стран, тегов, SNI, сумм файлов и
снимков экрана. Каталог установки этой проверки — /run/xgw-bridge2-install, прежние
(/run/xgw-bridge-install и другие) не трогать.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=910cb4ebfbcd90ac8b0fb302ab9229999979ddfd
BASE=688f2da7a9e8372083f14542bd9ffef33940cff8
D=$(mktemp -d "$HOME/xgw-bridge2.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/bridge_order_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '1a40911860a28e7acf8cf52ca8dbc3137cb142acdd78d4c2d5c8fdd9ccb7319f' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидается `OK` и ровно одна строка: `src/xgw/apply/singbox_generation.py`. Иначе — STOP,
сообщить владельцу. Путь D записать приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
sudo journalctl -u xgw --since "-3h" -o cat --no-pager | grep -o "мостов проверено [0-9]* из [0-9]*" | sort | uniq -c
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`INFO state=… members=… spares=… assembly=…` (переписать), `INFO last_3h switched=…
refused=…` (переписать), `config_sha=…` (только приватно), `OK prepare`, `helper_rc=0`.
Последняя команда — сколько раз за 3 ч был отказ «мостов проверено N из M» (переписать числа).
Записать числа OK/WARN/FAIL diag, режим пула и есть ли ручной выбор (да/нет).
- `STOP installed_is_base` — стоит не 688f2da: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты и логика (от владельца, без sudo)

```bash
cd "$TARGET" && for i in 1 2; do PYTHONPATH=src python3 -m pytest -p no:cacheprovider \
  tests/test_singbox_generations.py 2>&1 | tail -1; done
PYTHONPATH=src python3 -m pytest -p no:cacheprovider tests/test_daemon.py -k generation 2>&1 | tail -1
cd ~/xgw; python3 -I "$H" logic; echo "logic_rc=$?"
```

Ожидаются две строки `33 passed` и строка `2 passed` (failed и error нет). Затем
`INFO order=[3] each_s=20.0`, `OK member_first`, `OK bridge_cap`, `OK unknown_before_failing`,
`INFO refusal=мостов проверено 3 из 3: stall 3`, `OK refusal_summary`,
`INFO no_bridge=мостов в работе нет`, `OK no_bridge_in_use`, `OK logic`, `helper_rc=0`,
`logic_rc=0`. Падение или `STOP <имя>` — записать имя и строку ошибки, установку не делать
(PARTIAL).

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить 910cb4e (проверка нового поколения sing-box: один
файл из шага 1) поверх 688f2da штатным установщиком? Установщик перезапустит демон, сразу
после этого шлюз соберёт конфиг заново. Если on/HTTPS не подтвердятся за 45 с, помощник сам
вернёт 688f2da (начнёт не позже 60 с) и проверит связь. Затем 20 минут наблюдения». Дождаться
явного ответа, время записать приватно. Нет ответа или отказ — INSTALL_NOT_RUN, перейти к
шагу 7.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-bridge2-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-bridge2-deploy.log && break; sleep 5; done; cat /run/xgw-bridge2-deploy.log'
```

Вторую команду можно повторять, в том числе после обрыва связи; установку второй раз не
запускать. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`,
`helper_rc=0`. Записать `at`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл:
  записать времена, перейти к шагу 7 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Одно наблюдение, 20 минут (только чтение)

Сразу после `helper_rc=0` шага 5; ничего не нажимать в панели и окне.

```bash
sudo python3 -I "$H" observe 20 2>&1 | tee "$D/observe.txt"
```

Помощник раз в 15 с читает `xgw status`, а журнал считает с начала установки шага 5.
Ожидаются `INFO journal_from=install` (иначе записать слово), `INFO window_min=… states=…
spares_first=… spares_last=… spares_max=… members_last=…`, `INFO switched=… refused=…
error_lines=…`, строки `INFO refusal мостов проверено …` (если были), `OK config_unchanged`,
`OK on`, `OK https`. Итог:
- `OK generation_switched`, `helper_rc=0` — поколение сменилось: PASS. Записать запасных в
  начале, в конце и наибольшее (ожидается больше 4, вплоть до прежних ~54);
- `STOP generation_refused`, `helper_rc=5` — отказ остался: FAIL. Переписать все строки
  `INFO refusal …` дословно (в них только числа и виды отказов) и `refused`;
- `NOT_RUN generation`, `helper_rc=4` — смены поколения не было: записать запасных и число
  `sudo journalctl -u xgw --since "-25min" -o cat --no-pager | grep -c "поколени"`. Итог
  NOT_RUN по проверке, PASS по регрессии;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; пул тот же, что в шаге 2. Ручной выбор владелец
ставит сам, когда захочет. Каталог /run/xgw-bridge2-install остаётся до перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-bridge-order-r2-ДАТА.md` в freepool, одна страница,
без пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`,
затем `git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; один файл (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); state, members, spares, assembly;
  за 3 ч switched/refused и отказы «N из M» (числа):
Тесты: три строки N passed; logic_rc, order, refusal, no_bridge:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Наблюдение 20 мин: helper_rc; journal_from; states; запасных в начале/в конце/наибольшее;
  members; switched, refused, error_lines; строки refusal дословно; config_unchanged:
Конечное: on/HTTPS, diag после, пул без изменений (да/нет), ручной выбор (есть/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит
на машине:
```
