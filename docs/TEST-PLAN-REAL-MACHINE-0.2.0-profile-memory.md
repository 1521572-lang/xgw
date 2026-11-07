# ThinkCentre: волна 2 — память профилей обхода

Исполнитель — GLM-5.3-Flash. Волна 1б принята (18bcd1d + 3925f2e, PASS). Код CODE (ASSUMPTIONS
п. 336): шлюз помнит, на каком профиле обхода сервер ответил после пробы (7 суток), и на каком
проба не помогла (6 ч). При следующей лестнице первым идёт удачный, последним — не помогший.
Память привязана к серверу и его параметрам (адрес, порт, ключ, транспорт, путь, SNI), а не к
имени; отметки «из будущего» после перевода часов запрета не держат. Бюджет проб, пределы
повторов, гистерезис и ручной выбор прежние, новых фоновых проверок нет. Проверяется память и
отсутствие регрессии волн 1 и 1б, а не невидимость для ТСПУ.

На машине стоит один из двух пакетов: 7f09f77 (окно до ТЗ gui-s3b) или f9236a4 (после него).
Помощник сам скажет, какой. Демон в обоих — f57eb5b.

Можно: терминал, зрение, браузер, `xgw status`, `xgw diag --no-net`, `journalctl -u xgw`,
/run/xgw. Нельзя: менять WAN, LAN, Tailscale, подписки, пул, ручной выбор, настройки и сетевые
правила; нажимать «Проверить запасные» и замеры скорости; перезапускать демон кроме установки
шага 5; `xgw net down`, перезагрузку, `--force`, скачивание подписок, сторонние замеры и pcap.
Блокировки не имитировать: лестница профилей бывает только при естественном отказе сервера; не
было — NOT_RUN. DEGRADED и недоступность части серверов исправный on не отменяют. Устройства за
роутером не проверяются. В отчёт — только числа, слова состояний и признаки: без IP, доменов,
имён серверов, устройств и подписок, стран, тегов, SNI, MAC, сырого JSON и снимков экрана.
Каталоги /run/xgw-pacing-install и /run/xgw-diag-install не трогать: у этой волны свой —
/run/xgw-memory-install.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=1568790a2715e3c49e54eeb1f36bad469a64c9e9
B1=7f09f774afd3dd908ab43313533cf7744d7377a0
B2=f9236a4bb9c4347e2dc9af54d86e6a365858170e
D=$(mktemp -d "$HOME/xgw-memory.XXXXXXXX")
TARGET="$D/new"; H="$TARGET/docs/helpers/profile_memory_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$D/b1" "$B1" &&
git worktree add --detach "$D/b2" "$B2" && test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' 'b9ed6b48974849132f776454e45dcf7856b5e6c133a44f2f447ca65c65b240d6' "$H" | sha256sum -c -
```

Ожидается `OK`. Иначе — STOP. Путь D записать приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$D/b1" "$D/b2"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`,
`OK installed_is_one_base`, `installed_is=7f09f77 dir=b1` или `installed_is=f9236a4 dir=b2`,
`INFO memory {…}` (числа записей памяти — записать), `config_sha=…` (приватно), `OK prepare`,
`helper_rc=0`. Записать числа OK/WARN/FAIL diag, состояние, режим пула и есть ли ручной выбор
(да/нет). Затем:

```bash
PREV="$D/b2"   # если installed_is=… dir=b1 — PREV="$D/b1"
git -C "$TARGET" diff --name-only "$(git -C "$PREV" rev-parse HEAD)" "$CODE" -- src packaging
```

Для b2 ожидаются две строки: `src/xgw/daemon.py`, `src/xgw/generator/profiles.py`. Для b1 — ещё
четыре файла окна из f9236a4: `src/xgw/gui/app.py`, `src/xgw/gui/pages.py`,
`src/xgw/gui/widgets.py`, `src/xgw/gui/window.py`. Другие файлы — STOP, сообщить владельцу.
Если не так в подготовке:
- `STOP installed_is_one_base` — стоит ни то, ни другое: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — каталог /run/xgw-memory-install уже есть: ничего
  не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты и логика (от владельца, без sudo)

```bash
cd "$TARGET" && for i in 1 2 3; do PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests/test_profile_memory.py tests/test_scan_pacing.py tests/test_diag_limit.py 2>&1 | tail -1; done; cd ~/xgw
python3 -I "$H" logic; echo "logic_rc=$?"
```

Ожидаются три строки `14 passed` (4 — память, 10 — волны 1 и 1б). Затем
`INFO attempts_before=4 attempts_after=1 failed_last=True` (одна последовательность итогов:
до — 4 попытки лестницы, после — 1), `OK memory_order`, `OK new_params_no_false_success`,
`OK expired_failure_allowed`, `OK clock_back_no_ban`, `INFO keep worked_h=168 failed_h=6`,
`OK logic`, `helper_rc=0`, `logic_rc=0`. Падение или `STOP <имя>` — записать имя и строку
ошибки, установку не делать (PARTIAL).

## 4. Согласие владельца

Спросить: «Разрешаете установить 1568790 (память профилей: src/xgw/daemon.py,
src/xgw/generator/profiles.py; если на машине 7f09f77 — вместе с окном f9236a4) поверх
установленного штатным установщиком? Если после установки on/HTTPS не подтвердится за 45 с,
работник сам вернёт прежний пакет (начнёт не позже 60 с) и проверит связь. Затем 10 минут
наблюдения». Дождаться явного ответа, время сохранить приватно. Нет ответа или отказ —
INSTALL_NOT_RUN, перейти к шагу 7.

## 5. Установка с возвратом (локальный работник)

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-memory-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-memory-deploy.log && break; sleep 5; done; cat /run/xgw-memory-deploy.log'
```

Вторую команду повторять и после обрыва связи; установку второй раз не запускать. Норма:
`OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`, `helper_rc=0`.
Записать `at`. Иначе:
- `STOP baseline` — установка не начиналась, каталога блокировки нет: PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл:
  записать времена, `helper_rc=3`, перейти к шагу 7 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- `STOP FileExistsError` — каталог уже был: не удалять, владельцу;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Одно наблюдение, 10 минут (только чтение)

Сразу после `helper_rc=0` шага 5; ничего не нажимать в панели и окне.

```bash
sudo python3 -I "$H" observe 10 2>&1 | tee "$D/observe.txt"
```

Ожидаются `OK pacing_fields`, строки INFO (паузы, срочные, scan_lines, диагностика, запись
статуса с `long_steps`, `hung`, `steps_seen`, память до и после, `unparsed_lines`,
`ladder_lines`), затем `OK config_unchanged`, `OK on`, `OK https`, `OK watchdog_steps_seen`,
`OK status_without_hang`, `OK diagnosis_fields`, `OK pacing_regression`,
`OK memory_records_parsed`. Итог:
- `NOT_RUN memory` и `helper_rc=4` при всех OK — норма: лестницы в окне не было (повода не
  было). Числа записей памяти до и после установки переписать: прежние записи (switched,
  escalated, closed) не должны исчезнуть без причины; итог — PASS по регрессии, память на
  естественной лестнице — NOT_RUN (её покрывает шаг 3);
- `OK memory_used_in_window` и `helper_rc=0` — лестница шла: записать ladder_lines и числа
  worked/failed, сообщить владельцу; итог — PASS;
- `STOP memory_records_parsed` — демон не разобрал записи базы: FAIL, записать число;
- `STOP status_without_hang` — FAIL: записать max_s, long_steps, step_max_s;
- `STOP pacing_regression`, `STOP diagnosis_fields`, `STOP watchdog_steps_seen` — FAIL;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; пул и ручной выбор те же, что в шаге 2 (иначе —
владельцу, PARTIAL). Каталог /run/xgw-memory-install остаётся до перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-profile-memory-ДАТА.md` в freepool, одна страница,
без пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`,
затем `git pull --rebase` и обычный push без force.

```text
Дата; CODE; installed_is (b1/b2); сумма OK; состав пакета как ожидалось (да/нет):
Подготовка: helper_rc; on/HTTPS до; diag до (OK/WARN/FAIL); память до (числа):
Тесты: три строки; logic: logic_rc, attempts_before/after, keep:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Наблюдение 10 мин: helper_rc; паузы N/min/max/outside; urgent_waited; scan_lines; error_lines;
  запись статуса median/max/over25, long_steps, hung, steps_seen; память до/после,
  unparsed_lines, ladder_lines; config_unchanged:
Конечное: on/HTTPS, diag после, пул и ручной выбор без изменений (да/нет):
Границы: блокировки не имитировались; устройства за роутером не проверялись; что NOT_RUN:
Итог: PASS / PARTIAL / FAIL / NOT_RUN / INSTALL_NOT_RUN; первый непройденный шаг; что стоит
на машине:
```
