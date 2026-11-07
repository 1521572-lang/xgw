# ThinkCentre: волна 1б — повтор наблюдения с исправленным помощником (без установки)

Исполнитель — GLM-5.3-Flash. Отчёт diag-limit (18bcd1d) дал FAIL по правилу помощника: один
разрыв записи статуса 39 с без строки о долгом шаге. Правило было неверным (ASSUMPTIONS п. 334):
обычный шаг, у которого до первой записи статуса ушло ~15 с, даёт разрыв до 24 + 15 с.
Исправленный помощник сверяет каждый разрыв больше 25 с с длительностью шагов демона из
/run/xgw/watchdog-step.json: объяснимый разрыв — справочно, зависание — FAIL. Тест волны 1
больше не сравнивает округлённые паузы точно. Код демона не меняется: на машине остаётся
f57eb5b, ничего не ставить и не возвращать.

Можно: терминал, `xgw status`, `xgw diag --no-net`, `journalctl -u xgw`, файлы /run/xgw.
Нельзя: устанавливать, перезапускать демон, менять WAN, LAN, Tailscale, подписки, пул, ручной
выбор, настройки и правила; нажимать «Проверить запасные» и замеры скорости; удалять
/run/xgw-diag-install и /run/xgw-pacing-install. В отчёт — только числа, слова состояний и
признаки: без IP, доменов, имён серверов, устройств и подписок, стран, тегов, SNI и MAC.

## 1. Код помощника и тестов

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=7461da4af6091169bc86db46b2d38569914dc6c2
D=$(mktemp -d "$HOME/xgw-diag-r2.XXXXXXXX")
TARGET="$D/new"; H="$TARGET/docs/helpers/diag_limit_check.py"
git worktree add --detach "$TARGET" "$CODE" && test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '500dd6e7497282299432ff7b755b62d0eb44f34171b7a9158d171410d74e16b1' "$H" | sha256sum -c - &&
git -C "$TARGET" diff --name-only f57eb5b1b77ffb12b64a479cebaf925fee56eccd "$CODE" -- src/xgw/daemon.py src/xgw/watch/target.py
```

Ожидается `OK` и пустой вывод последней команды (демон и проверка адреса те же, что
установлены). Иначе — STOP, сообщить владельцу.

## 2. Тест волны 1 — три прогона (от владельца, без sudo)

```bash
cd "$TARGET" && for i in 1 2 3; do PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests/test_scan_pacing.py tests/test_diag_limit.py 2>&1 | tail -1; done; cd ~/xgw
```

Ожидается три строки `10 passed`. Падение — записать имя теста и строку ошибки, наблюдение
шага 3 всё равно выполнить.

## 3. Состояние и одно наблюдение 10 минут (только чтение)

```bash
sudo python3 -I "$H" health && sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
sudo python3 -I "$H" observe 10 2>&1 | tee "$D/observe.txt"
```

Ожидаются `OK on`, `OK https`, затем от наблюдения:
- `OK pacing_fields`, `INFO planned_pauses=… outside=0 …`, `INFO urgent_probes=… urgent_waited=0 …`;
- `INFO diagnosis workers=2 budget_s=16.0 pending=… ran_in_window=… …`;
- `INFO status_writes=… median_s=… max_s=… over25=K slow_step_lines=… long_steps=[…] hung=0
  steps_seen=N step_max_s=…` — N > 0; `long_steps` — разрывы больше 25 с с длительностью
  шага рядом («разрыв/шаг», справочно);
- `OK config_unchanged`, `OK on`, `OK https`, `OK watchdog_steps_seen`, `OK status_without_hang`,
  `OK diagnosis_fields`, `OK pacing_regression`.
Итог:
- `NOT_RUN diagnosis` и `helper_rc=4` при всех OK выше — норма (повода для проверки адреса не
  было); итог — PASS;
- `OK diagnosis_two_at_a_time` и `helper_rc=0` — проверка адреса шла в окне: записать
  max_parallel и complete, сообщить владельцу; итог — PASS;
- `STOP status_without_hang` (hung > 0) — FAIL: записать max_s, long_steps, step_max_s;
- `STOP watchdog_steps_seen` — помощник не видел хода цикла: записать, итог PARTIAL;
- `STOP pacing_regression`, `STOP diagnosis_fields` — FAIL, записать числа;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

```bash
sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Числа OK/WARN/FAIL до и после — новых FAIL быть не должно.

## 4. Отчёт

`docs/TEST-REPORT-REAL-MACHINE-0.2.0-diag-limit-r2-ДАТА.md` в freepool, одна страница. Путь D
не писать. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`,
затем `git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; демон и target.py те же, что f57eb5b (да/нет):
Тесты: три строки (N passed / имя упавшего):
on/HTTPS до; diag до и после (OK/WARN/FAIL):
Наблюдение: helper_rc; state; planned_pauses, min, max, outside; urgent_probes, urgent_waited;
  scan_lines; error_lines; diagnosis pending, ran_in_window, max_parallel, complete;
  status_writes, median_s, max_s, over25, slow_step_lines, long_steps, hung, steps_seen,
  step_max_s; config_unchanged:
Границы: ничего не устанавливалось; отказы не имитировались; устройства за роутером не
  проверялись; естественная проверка адреса проб — NOT_RUN, если повода не было:
Итог по волне 1б (вместе с отчётом 18bcd1d): PASS / PARTIAL / FAIL; что осталось:
```
