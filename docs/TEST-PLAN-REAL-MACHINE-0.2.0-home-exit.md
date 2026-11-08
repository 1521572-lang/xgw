# ThinkCentre: замена сервера с выходом в домашнюю страну после снятия LEAK

Исполнитель — GLM-5.3-Flash. Отчёт leak-cause (f3f8b54): сразу после установки выбранный сервер
вышел в домашнюю страну, мимо Xray ничего не уходило. Шлюз записал «меняю его на запасной», но
замены не было: через ~5 минут LEAK снялся, и попытки прекратились. Код CODE (ASSUMPTIONS
п. 340): такой сервер меняется и при HEALTHY, как только есть годный запасной, без внеочередных
сканов; пока действует ручной выбор, состав при HEALTHY не меняется.

Вызвать случай нельзя: сервер с таким выходом сам может попасть в работу сразу после установки,
как в прошлый раз. Не случилось — NOT_RUN по этой части, остальное проверяется. Невидимость для
ТСПУ не проверяется.

Можно: терминал, `xgw status`, `xgw diag --no-net`, окно и панель (только смотреть). Нельзя:
подписки, пул, ручной выбор, «Обновить», «Проверить запасные», замеры скорости, настройки, WAN,
LAN, Tailscale и сетевые правила; перезапуск демона, кроме установки шага 5; `xgw net down`,
перезагрузка, `--force`, сторонние замеры и pcap. В отчёт — только числа, слова состояний и
виды записей: без имён серверов и подписок, адресов, доменов, стран, тегов, SNI, сумм файлов и
снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=73ff66ee091af1a79b445eb5708ecab38f769cdb
BASE=910cb4ebfbcd90ac8b0fb302ab9229999979ddfd
D=$(mktemp -d "$HOME/xgw-homeexit.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/home_exit_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '85e5dbe923d531897b012299a8387ef18aa3d176f6768db535b3bc9e08f2918d' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидается `OK` и ровно одна строка: `src/xgw/daemon.py`. Иначе — STOP, сообщить владельцу. Путь
D записать приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`INFO state=… members=… spares=…` (переписать), `config_sha=…` (только приватно), `OK prepare`,
`helper_rc=0`. Записать числа OK/WARN/FAIL diag, режим пула и есть ли ручной выбор (да/нет).
- `STOP installed_is_base` — стоит не 910cb4e: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты (от владельца, без sudo)

Новый тест и тот, что рядом, затем весь файл демона на новом и прежнем коде (до 25 минут на
каждый прогон).

```bash
cd "$TARGET" && PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests/test_daemon.py \
  -k "test_home_exit_member or test_server_exiting_at_home" 2>&1 | tail -1
for T in new base; do
  (cd "$D/$T" && PYTHONPATH=src timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_daemon.py >"$D/out-$T" 2>&1; echo "$T rc=$?")
  tail -1 "$D/out-$T"
  grep -E '^(FAILED|ERROR)' "$D/out-$T" | sed 's/ - .*//' | sort >"$D/fails-$T"
done
echo "новые падения:"; comm -23 "$D/fails-new" "$D/fails-base"; echo "конец списка"
cd ~/xgw
```

Ожидается `2 passed`, затем для new и base `rc=0` или `rc=1` (падения старые) и итоговая строка
pytest. Между `новые падения:` и `конец списка` — пусто. Переписать итоговые строки. Если в
списке что-то есть, если первая строка не `2 passed` или есть `rc=124` (не уложилось) —
записать, установку не делать, отчёт PARTIAL.

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить 73ff66e (замена сервера с выходом в домашнюю страну:
один файл из шага 1) поверх 910cb4e штатным установщиком? Установщик перезапустит демон. Если
on/HTTPS не подтвердятся за 45 с, помощник сам вернёт 910cb4e и проверит связь. Затем 40 минут
наблюдения». Дождаться явного ответа, время записать приватно. Нет ответа или отказ —
INSTALL_NOT_RUN, перейти к шагу 7.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-homeexit-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-homeexit-deploy.log && break; sleep 5; done; cat /run/xgw-homeexit-deploy.log'
```

Вторую команду можно повторять, в том числе после обрыва связи; установку второй раз не
запускать. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`,
`helper_rc=0`. Записать `at`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл: записать
  времена, перейти к шагу 7 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Одно наблюдение, 40 минут (только чтение)

Сразу после `helper_rc=0` шага 5; ничего не нажимать в панели и окне.

```bash
sudo python3 -I "$H" observe 40 2>&1 | tee "$D/observe.txt"
```

Ожидаются `INFO from=install`, `INFO window_min=… states=… last=…`, `INFO leak total=…
promised=… bypass=…`, `INFO rotations total=… home=… delay_s=…`, `INFO generation switched=…
refused=…`, `OK config_unchanged`, `OK on`, `OK https`. Итог:
- `OK home_member_replaced`, `helper_rc=0` — сервер с выходом в домашнюю страну заменён: PASS.
  Записать `delay_s`;
- `NOT_RUN home_exit`, `helper_rc=4` — такого сервера в окне не было: NOT_RUN по замене, PASS по
  регрессии, если состояния и on/HTTPS в норме;
- `STOP home_member_not_replaced`, `helper_rc=5` — обещанной замены за окно нет: FAIL. Записать
  `xgw status --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("state"), len(d.get("spares") or []))'`;
- `bypass` больше 0 — **отдельной строкой владельцу**: возможен выход мимо Xray;
- `refused` больше 0 — переписать число: пересборка отказала, FAIL по этой части;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

`generation switched` 1 и больше — пересборка от демона прошла (её ещё ни разу не видели после
п. 339): записать. 0 — эта часть осталась NOT_RUN.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; пул тот же, что в шаге 2. Ручной выбор владелец
ставит сам, когда захочет. Каталог /run/xgw-homeexit-install остаётся до перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-home-exit-ДАТА.md` в freepool, одна страница, без
пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем
`git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; один файл (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); state, members, spares; пул; ручной выбор:
Тесты: первая строка; new и base (rc, итог); новые падения (пусто/какие):
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Наблюдение 40 мин: helper_rc; from; states; last; leak (total/promised/bypass);
  rotations (total/home/delay_s); generation (switched/refused); config_unchanged:
Конечное: on/HTTPS, diag после, пул без изменений (да/нет), ручной выбор (есть/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит
на машине:
```
