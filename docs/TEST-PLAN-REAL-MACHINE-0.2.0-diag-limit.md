# ThinkCentre: волна 1б — проверка адреса проб по два запроса с общим дедлайном

Исполнитель — GLM-5.3-Flash. После отчёта scan-pacing (PASS, ad9b380) на машине стоит 83d5b37.
Код CODE (ASSUMPTIONS п. 332): когда все серверы в работе разом не отвечают, демон проверяет,
не сам ли адрес проб недоступен. Раньше он слал 8 проб сразу, теперь — не больше 2 одновременно
и все вместе не дольше 16 с за шаг. Не успел — итога нет: ни «адрес отвечает», ни «серверы
мертвы»; сканы и замены ждут, проверка доделывается на следующих шагах без повторных проб.
Пакет меняет три файла: src/xgw/daemon.py и src/xgw/watch/target.py (эта волна) и
src/xgw/gui/app.py — правка окна XGW из 6f49129 (п. 331, другая работа: новый запуск окна
заменяет открытое окно прежней версии), она уже в freepool под этой волной и ставится вместе.
Проверяется расписание и отсутствие регрессии, а не невидимость для ТСПУ.

Можно: терминал, зрение, браузер, `xgw status`, `xgw diag --no-net`, `journalctl -u xgw`,
/run/xgw/status.json. Нельзя: менять WAN, LAN, Tailscale, подписки, пул, ручной выбор,
настройки и сетевые правила; нажимать «Проверить запасные» и замеры скорости; перезапускать
демон кроме установки шага 5; `xgw net down`, перезагрузку, `--force`, скачивание подписок,
сторонние замеры скорости и pcap. Отказ серверов не имитировать: проверка адреса проб на
настоящем шлюзе бывает только при естественном отказе всех участников; его не было — NOT_RUN.
DEGRADED и недоступность части серверов проверку исправного on не останавливают. Устройства за
роутером эта проверка не доказывает — клиента не просить. В отчёт — только числа, слова
состояний и признаки: без IP, доменов, имён серверов, устройств и подписок, стран, тегов, SNI,
MAC, сырого JSON и снимков экрана. Каталог /run/xgw-pacing-install от волны 1 не трогать: у
этой волны свой каталог /run/xgw-diag-install.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=f57eb5b1b77ffb12b64a479cebaf925fee56eccd
BASE=83d5b37f58036170ed3b51c580e15eb643a3914a
D=$(mktemp -d "$HOME/xgw-diag.XXXXXXXX")
TARGET="$D/new"; PREV="$D/previous"; H="$TARGET/docs/helpers/diag_limit_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
test "$(git -C "$PREV" rev-parse HEAD)" = "$BASE" &&
printf '%s  %s\n' '3bffbcdfaa4bf32a4ea8dd7c223837903111bad531e4f2ab90312a5975219d11' "$H" | sha256sum -c - &&
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидаются `OK` и ровно три строки: `src/xgw/daemon.py`, `src/xgw/gui/app.py`,
`src/xgw/watch/target.py`. Другие файлы пакета — STOP: состав не тот, на который просят
согласие; сообщить владельцу. Путь D записать приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`config_sha=…` (приватно), `OK prepare`, `helper_rc=0`. Записать числа OK/WARN/FAIL diag,
состояние шлюза, режим пула и есть ли ручной выбор (да/нет). Если не так:
- `STOP installed_is_base` — на машине не 83d5b37: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — каталог /run/xgw-diag-install уже есть: ничего не
  удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.
Подготовка каталогов не создаёт.

## 3. Тесты и логика на машине (от владельца, без sudo)

```bash
cd "$TARGET" && PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests/test_diag_limit.py tests/test_scan_pacing.py 2>&1 | tail -3; cd ~/xgw
python3 -I "$H" logic; echo "logic_rc=$?"
```

Ожидается `10 passed` (5 — эта волна: два запроса сразу; дедлайн и остановка не начинают
новых проб; истёкший дедлайн — без вывода; один ответ даёт итог сразу; при неполной проверке
нет замен; 5 — волна 1 не сломана). Затем `OK two_at_a_time` (INFO: results=6,
max_parallel=2), `OK deadline_leaves_rest_unstarted` (results меньше 6),
`OK stop_starts_nothing`, `OK incomplete_is_no_verdict`, `OK logic`, `helper_rc=0`,
`logic_rc=0`. Это проверка на подменённых пробах, без сети: она заменяет имитацию отказа.
Падение теста или `STOP <имя>` — записать имя и строку ошибки, установку не делать (PARTIAL).

## 4. Согласие владельца

Спросить: «Разрешаете установить f57eb5b (меняются демон и проверка адреса проб —
src/xgw/daemon.py, src/xgw/watch/target.py — и вместе с ними правка окна XGW из 6f49129,
src/xgw/gui/app.py) поверх 83d5b37 штатным установщиком? Если после
установки on/HTTPS не подтвердится за 45 с, работник сам вернёт 83d5b37 (начнёт не позже 60 с)
и проверит связь. Затем 10 минут наблюдения». Дождаться явного ответа на этот вопрос, время
сохранить приватно. Нет ответа или отказ — INSTALL_NOT_RUN, перейти к шагу 7.

## 5. Установка с возвратом (локальный работник)

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-diag-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
```

Затем (ту же команду повторять и после обрыва связи; вторую установку не запускать):

```bash
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-diag-deploy.log && break; sleep 5; done; cat /run/xgw-diag-deploy.log'
```

Смотреть последнюю запись. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`,
`OK installed`, `helper_rc=0`. Записать время `at`. Если не так:
- `STOP baseline` — установка не начиналась, каталог блокировки не оставлен: отчёт PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл: записать
  оба времени, `helper_rc=3`, перейти к шагу 7 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- `STOP FileExistsError` — каталог /run/xgw-diag-install уже был: не удалять, владельцу;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Один цикл наблюдения, 10 минут (только чтение)

Сразу после `helper_rc=0` шага 5. Ничего не нажимать в панели и окне.

```bash
sudo python3 -I "$H" observe 10 2>&1 | tee "$D/observe.txt"
```

Помощник 10 минут следит за записью /run/xgw/status.json, затем читает журнал, сверяет
config.toml и on/HTTPS. Ожидаются:
- `OK pacing_fields`; `INFO state=… scan_minutes=… next_planned_in_s=…`;
- `INFO planned_pauses=N min=… max=… outside=0 idle_max_s=…` (min ≥ 0,19, max ≤ 1,6 — волна 1
  после установки не сломана; N = 0 допустим, если круг ещё не начинался);
- `INFO urgent_probes=… urgent_waited=0 scan_lines=… error_lines=…` (scan_lines теперь
  считается верно — в отчёте scan-pacing было 0 из-за счёта помощника);
- `INFO diagnosis workers=2 budget_s=16.0 pending=… ran_in_window=… max_parallel=…
  complete=… unfinished_lines=…`;
- `INFO status_writes=… median_s=… max_s=… over25=0 slow_step_lines=…`, `OK config_unchanged`,
  `OK on`, `OK https`, `OK status_every_25s`, `OK diagnosis_fields`, `OK pacing_regression`.
Итог:
- `NOT_RUN diagnosis` и `helper_rc=4` при всех OK выше — норма: шлюз был в порядке, повода для
  проверки адреса проб не было. Итог волны — PASS по регрессии, NOT_RUN по естественной
  проверке на машине (её покрывает шаг 3);
- `OK diagnosis_two_at_a_time` и `helper_rc=0` — проверка адреса шла в окне: записать
  max_parallel, complete и unfinished_lines; сообщить владельцу, что был отказ всех участников;
- `STOP status_every_25s` (over25 > 0) — записать max_s и slow_step_lines; если slow_step_lines
  больше нуля, одно уточнение у владельца, считать ли долгий шаг сборки помехой (PARTIAL);
  если 0 — FAIL;
- `STOP pacing_regression` или `STOP diagnosis_fields` — FAIL, записать числа;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу (FAIL), ничего не чинить.
`error_lines` — справочно.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL в diag нет. Приватно сравнить пул и наличие ручного
выбора с шагом 2; изменились — сообщить владельцу (PARTIAL). Каталог /run/xgw-diag-install
после установки остаётся до перезагрузки: он не даёт второй установки этого пакета.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-diag-limit-ДАТА.md` в freepool, одна страница.
Путь D в отчёт не писать. Проверить `git diff --cached --name-only` (только этот файл) и
`git diff --cached --check`, затем `git pull --rebase` и обычный push без force.

```text
Дата; CODE/BASE; сумма OK; состав пакета (три строки — да/нет); окно XGW здесь не проверялось:
Подготовка: helper_rc; installed_is_base; on/HTTPS до; diag до (OK/WARN/FAIL):
Тесты на машине: N passed / имя упавшего; logic: logic_rc, results/max_parallel, deadline results:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат (времена,
  rollback_rc, rollback_verified) или «не нужен»:
Наблюдение 10 мин: helper_rc; state; planned_pauses N, min, max, outside; urgent_probes,
  urgent_waited; scan_lines; error_lines; diagnosis pending, ran_in_window, max_parallel, complete,
  unfinished_lines; status_writes, median_s, max_s, over25, slow_step_lines; config_unchanged:
Конечное: on/HTTPS, diag после, пул и ручной выбор без изменений (да/нет):
Границы: устройства за роутером не проверялись; отказы не имитировались; что NOT_RUN:
Итог: PASS / PARTIAL / FAIL / NOT_RUN / INSTALL_NOT_RUN; первый непройденный шаг;
оставлено на машине: CODE установлен или BASE возвращён, каталог блокировки:
```
