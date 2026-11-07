# ThinkCentre: волна 1 — плановые проверки запасных с паузами

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 330, таблица —
docs/SELECT-ROBUST-2026-11-07.md): при HEALTHY плановая проба запасного ждёт 0,2–1,5 с после
предыдущей пробы шага, внутри прежнего бюджета 8 с; серверы в работе, аварийные проверки и
кнопка «Проверить запасные» паузы не ждут. Пакет меняет один файл — src/xgw/daemon.py.
Проверяется расписание и отсутствие регрессии, а не невидимость для ТСПУ.

Можно: терминал, зрение, браузер, `xgw status`, `xgw diag --no-net`, `journalctl -u xgw`,
/run/xgw/status.json. Нельзя: менять WAN, LAN, Tailscale, подписки, пул, ручной выбор,
настройки и сетевые правила; нажимать «Проверить запасные» и замеры скорости; перезапускать
демон кроме установки шага 5; `xgw net down`, перезагрузку, `--force`, скачивание подписок,
сторонние замеры скорости и pcap. Отказы не имитировать: то, что требует естественного
события и его не было, — NOT_RUN. DEGRADED и недоступность части серверов проверку исправного
on не останавливают. Устройства за роутером эта проверка не доказывает — клиента не просить.
В отчёт — только числа, слова состояний и признаки: без IP, доменов, имён серверов, устройств
и подписок, стран, тегов, SNI, MAC, сырого JSON и снимков экрана.

## 0. Только после шага 5 gui-look2

Установка перезапускает демон, а шагу 5 ТЗ gui-look2 нужно 4 ч без перезапуска.

```bash
cd ~/xgw && git fetch origin &&
git show origin/freepool:docs/TEST-REPORT-REAL-MACHINE-0.2.0-gui-look2-2026-11-07.md |
grep -c 'будет выполнен не раньше\|шаг 5 дописывается'
```

Ожидается `0`. Иначе — STOP «жду шага 5 gui-look2», сообщить владельцу, ничего не ставить.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git merge --ff-only origin/freepool
CODE=83d5b37f58036170ed3b51c580e15eb643a3914a
BASE=fe1c2bac1ca294b933ca7943bae0509502a5c5bd
D=$(mktemp -d "$HOME/xgw-pacing.XXXXXXXX")
TARGET="$D/new"; PREV="$D/previous"; H="$TARGET/docs/helpers/scan_pacing_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
test "$(git -C "$PREV" rev-parse HEAD)" = "$BASE" &&
printf '%s  %s\n' '40974cd65e280dd3bd3a3a88f26c60423e33655166b353613b4508697e378161' "$H" | sha256sum -c - &&
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидаются `OK` и одна строка `src/xgw/daemon.py`. Другие файлы пакета — STOP: состав не тот,
на который просят согласие; сообщить владельцу. Путь D записать приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`config_sha=…` (записать приватно), `OK prepare`, `helper_rc=0`. Записать числа OK/WARN/FAIL
diag, состояние шлюза, режим пула и есть ли ручной выбор (да/нет). Если не так:
- `STOP installed_is_base` — на машине не BASE: установку не делать, отчёт PARTIAL;
- `STOP lock_active` — идёт чужая установка: ничего не удалять, сообщить владельцу;
- `STOP lock_finished` — остался итог прошлой установки: сообщить владельцу, не удалять;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.
Подготовка каталогов не создаёт.

## 3. Тесты волны на машине (от владельца, без sudo)

```bash
cd "$TARGET" && PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests/test_scan_pacing.py 2>&1 | tail -3; cd ~/xgw
```

Ожидается `5 passed`: паузы в бюджете, срочные/ручные/DEGRADED без пауз, остановка не теряет
очередь, аварийная перестановка без дубликатов, перемешивание только при равном рейтинге.
Падение — записать имя теста и строку ошибки, установку не делать (PARTIAL).

## 4. Согласие владельца

Спросить: «Разрешаете установить 83d5b37 (меняется только демон, src/xgw/daemon.py) поверх
fe1c2ba штатным установщиком? Если после установки on/HTTPS не подтвердится за 45 с, работник
сам вернёт fe1c2ba (начнёт не позже 60 с) и проверит связь. Затем 10 минут наблюдения».
Дождаться явного ответа на этот вопрос, время сохранить приватно. Нет ответа или отказ —
INSTALL_NOT_RUN, перейти к шагу 7.

## 5. Установка с возвратом (локальный работник)

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-pacing-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
```

Затем (ту же команду повторять и после обрыва связи; вторую установку не запускать):

```bash
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-pacing-deploy.log && break; sleep 5; done; cat /run/xgw-pacing-deploy.log'
```

Смотреть последнюю запись. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`,
`OK installed`, `helper_rc=0`. Записать время `at`. Если не так:
- `STOP baseline` — установка не начиналась, каталог блокировки не оставлен: отчёт PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл: записать
  оба времени, `helper_rc=3`, перейти к шагу 7 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- `STOP FileExistsError` — каталог /run/xgw-pacing-install уже был: не удалять, владельцу;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Один цикл наблюдения, 10 минут (только чтение)

Сразу после `helper_rc=0` шага 5. Ничего не нажимать в панели и окне.

```bash
sudo python3 -I "$H" observe 10 2>&1 | tee "$D/observe.txt"
```

Помощник 10 минут следит за записью /run/xgw/status.json, затем читает журнал, сверяет
config.toml и on/HTTPS. Норма (`helper_rc=0`):
- `OK pacing_fields`; `INFO state=… scan_minutes=… next_planned_in_s=…`;
- `INFO planned_pauses=N min=… max=… outside=0 idle_max_s=…` — N ≥ 1, min ≥ 0,19, max ≤ 1,6;
  `idle_max_s` — справочно (пауза плюс обработка итога, не критерий);
- `INFO urgent_probes=… urgent_waited=0 scan_lines=… error_lines=…`;
- `INFO status_writes=… median_s=… max_s=… over25=0 slow_step_lines=…`, `OK status_every_25s`;
- `OK config_unchanged`, `OK on`, `OK https`, `OK pacing`.
Иначе:
- `helper_rc=4` и `NOT_RUN planned_pauses` — первые пробы после запуска шли без паузы
  (состояние ещё не HEALTHY) или круга не было; это не дефект: записать state и
  next_planned_in_s, итог по паузам — NOT_RUN. Можно один раз через next_planned_in_s секунд
  повторить ту же команду (ещё 10 минут) — только если владелец согласен подождать;
- `STOP status_every_25s` (over25 > 0) — записать max_s и slow_step_lines; если slow_step_lines
  больше нуля, одно уточнение: спросить владельца, считать ли долгий шаг сборки помехой (PARTIAL);
  если 0 — FAIL;
- `STOP pacing` (outside > 0 или urgent_waited > 0) — FAIL, записать числа;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу (FAIL), ничего не чинить.
`error_lines` — справочно: сравнить с тем, что было до установки, если владелец просит.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL в diag нет. Приватно сравнить пул и наличие ручного
выбора с шагом 2; изменились — сообщить владельцу (PARTIAL). Каталог /run/xgw-pacing-install
после установки остаётся до перезагрузки: он не даёт запустить вторую установку этого пакета.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-scan-pacing-ДАТА.md` в freepool, одна страница.
Проверить `git diff --cached --name-only` (только этот файл) и `git diff --cached --check`,
затем `git pull --rebase` и обычный push без force.

```text
Дата; CODE/BASE; сумма OK; состав пакета (одна строка daemon.py — да/нет):
Подготовка: helper_rc; installed_is_base; on/HTTPS до; diag до (OK/WARN/FAIL):
Тесты на машине: N passed / имя упавшего:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат (времена,
  rollback_rc, rollback_verified) или «не нужен»:
Наблюдение 10 мин: helper_rc; state; planned_pauses N, min, max, outside; idle_max_s
  (справочно); urgent_probes, urgent_waited; scan_lines; error_lines; status_writes, median_s,
  max_s, over25, slow_step_lines; config_unchanged; on/HTTPS после:
Конечное: on/HTTPS, diag после, пул и ручной выбор без изменений (да/нет):
Границы: устройства за роутером не проверялись; отказы не имитировались; что NOT_RUN:
Итог: PASS / PARTIAL / FAIL / NOT_RUN / INSTALL_NOT_RUN; первый непройденный шаг;
оставлено на машине: CODE установлен или BASE возвращён, каталог блокировки, путь D:
```
