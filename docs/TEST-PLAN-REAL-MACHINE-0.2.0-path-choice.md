# ThinkCentre: разные пути при замене сервера (волна 3)

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 341): заменяя отказавший сервер, шлюз
среди сопоставимых по рейтингу запасных той же страны и подписки сначала берёт отличающийся
адресом и TCP/UDP-путём. Два имени на одном адресе запасом не считаются. Страна, подписка,
ручной выбор и пул важнее; единственный годный сервер не отбрасывается. В `xgw status`
появилась строка «Запас» и причина последней замены.

Настоящую замену вызвать нельзя. Если её не было — NOT_RUN по этой части, остальное
проверяется. Обход блокировок и невидимость для ТСПУ здесь не проверяются.

Можно: терминал, `xgw status`, `xgw diag --no-net`, окно и панель (только смотреть). Нельзя:
подписки, пул, ручной выбор, «Обновить», «Проверить запасные», замеры скорости, настройки, WAN,
LAN, Tailscale и сетевые правила; перезапуск демона, кроме установки шага 5; `xgw net down`,
перезагрузка, `--force`, сторонние замеры и pcap. В отчёт — только числа, слова состояний и
виды причин: без имён серверов и подписок, адресов, доменов, стран, тегов, SNI, сумм файлов и
снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=6a3a8d6131844394d8c9254030f081427e4b6d3d
BASE=73ff66ee091af1a79b445eb5708ecab38f769cdb
D=$(mktemp -d "$HOME/xgw-pathchoice.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/path_choice_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '40909e38a528b61490186bc6c9e857cb30d9512903893e1d62891f5246f27ee6' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидается `OK` и ровно три строки: `src/xgw/apply/rotation.py`, `src/xgw/daemon.py`,
`src/xgw/watch/status.py`. Иначе — STOP, сообщить владельцу. Путь D записать приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`INFO state=… members=… spares=…` (переписать), `config_sha=…` (только приватно), `OK prepare`,
`helper_rc=0`. Записать числа OK/WARN/FAIL diag, режим пула и есть ли ручной выбор (да/нет).
- `STOP installed_is_base` — стоит не 73ff66e: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты (от владельца, без sudo)

Новые тесты выбора, затем весь файл демона на новом и прежнем коде (до 25 минут на прогон).

```bash
cd "$TARGET" && PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider \
  tests/test_path_diversity.py tests/test_rotation.py 2>&1 | tail -1
for T in new base; do
  (cd "$D/$T" && PYTHONPATH=src timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_daemon.py >"$D/out-$T" 2>&1; echo "$T rc=$?")
  tail -1 "$D/out-$T"
  grep -E '^(FAILED|ERROR) tests/' "$D/out-$T" | sed 's/ - .*//' | sort >"$D/fails-$T"
done
echo "новые падения:"; comm -23 "$D/fails-new" "$D/fails-base"; echo "конец списка"
cd ~/xgw
```

Ожидается `12 passed`, затем для new и base `rc=0` или `rc=1` (падения старые) и итоговая
строка pytest. Между `новые падения:` и `конец списка` — пусто. Переписать итоговые строки. Если
в списке что-то есть, первая строка не `12 passed` или есть `rc=124` — записать, установку не
делать, отчёт PARTIAL.

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить 6a3a8d6 (разные пути при замене сервера: три файла из
шага 1) поверх 73ff66e штатным установщиком? Установщик перезапустит демон. Если on/HTTPS не
подтвердятся за 45 с, помощник сам вернёт 73ff66e и проверит связь. Затем 30 минут наблюдения».
Дождаться явного ответа, время записать приватно. Нет ответа или отказ — INSTALL_NOT_RUN,
перейти к шагу 7.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-pathchoice-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-pathchoice-deploy.log && break; sleep 5; done; cat /run/xgw-pathchoice-deploy.log'
```

Вторую команду можно повторять, в том числе после обрыва связи; установку второй раз не
запускать. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`,
`helper_rc=0`. Записать `at`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл: записать
  времена, перейти к шагу 7 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Одно наблюдение, 30 минут (только чтение)

Сразу после `helper_rc=0` шага 5; ничего не нажимать в панели и окне.

```bash
sudo python3 -I "$H" observe 30 2>&1 | tee "$D/observe.txt"
sudo xgw status | grep -E '^(Запас|Последняя замена)' | sed 's/([0-9:. -]*):/:/'
```

Ожидаются `INFO from=install`, `INFO window_min=… states=… status_age_max_s=…`, `OK
selection_present`, `INFO selection spares_ok=… paths=… other_paths=… note=…`, `OK
selection_counts`, `INFO rotations total=… reasons={…}`, `INFO generation switched=… refused=…`,
`OK status_line`, `OK config_unchanged`, `OK on`, `OK https`. Итог:
- `OK reason_recorded`, `helper_rc=0` — замена записала причину: PASS. Переписать `reasons`;
- `NOT_RUN replacement`, `helper_rc=4` — замены с причиной не было: NOT_RUN по замене, PASS по
  регрессии, если состояния и on/HTTPS в норме;
- `STOP selection_present` / `STOP selection_counts` / `STOP status_line` — FAIL, дальше не
  чинить, переписать строку `INFO selection` и шаг STOP;
- `WARN status_age` — запись status.json дольше 25 с: записать `status_age_max_s`, FAIL по этой
  части;
- `refused` больше 0 — переписать число: пересборка отказала, FAIL по этой части;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

Смысл чисел: `spares_ok` — запасные, годные в замену; `paths` — разных пар «адрес и TCP/UDP»
среди них; `other_paths` — таких пар нет у участников. `paths` заметно меньше `spares_ok` значит,
что часть имён — на одних адресах. `generation switched` 1 и больше — пересборка от демона
прошла (её ещё ни разу не видели после п. 339): записать; 0 — NOT_RUN по этой части.

Вторая команда показывает строки для человека: записать только есть ли они (да/нет) и вид
причины; адресов и имён в них быть не должно — если есть, сразу владельцу.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; пул тот же, что в шаге 2. Ручной выбор владелец
ставит сам, когда захочет. Каталог /run/xgw-pathchoice-install остаётся до перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-path-choice-ДАТА.md` в freepool, одна страница, без
пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем
`git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; три файла (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); state, members, spares; пул; ручной выбор:
Тесты: первая строка; new и base (rc, итог); новые падения (пусто/какие):
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Наблюдение 30 мин: helper_rc; from; states; status_age_max_s; selection (spares_ok/paths/
  other_paths/note); rotations total и reasons; generation (switched/refused); config_unchanged:
Строки «Запас» и «Последняя замена»: есть (да/нет), вид причины:
Конечное: on/HTTPS, diag после, пул без изменений (да/нет), ручной выбор (есть/нет):
Границы: живой замены могло не быть; обход блокировок не проверялся:
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит
на машине:
```
