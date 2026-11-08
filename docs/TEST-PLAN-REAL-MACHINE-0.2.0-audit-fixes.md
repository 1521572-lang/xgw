# ThinkCentre: правки внешнего аудита

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 347): подписка не запрашивается со служебных
адресов, в том числе через перенаправление и через Xray; снятие правил не обрывается на первой
ошибке; «не удалось узнать» больше не выглядит как «пусто»; откаты ufw и DHCP; остальное — см. пункт.
Отказы на машине **не вызываются**: сами отказы проверяются тестами шага 3, а живьём — что обычный
путь не сломан.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: подписки, пул, ручной выбор, «Обновить», замеры, настройки, WAN, LAN, Tailscale и сетевые
правила; перезапуск демона, кроме установки шага 5; `xgw net down`, перезагрузка, `--force`. В отчёт
— только числа, признаки, виды причин и имена тестов: без имён серверов и подписок, адресов, доменов,
тегов, SNI, short_id, сумм файлов и снимков экрана. reality.json и panel.json не выводить.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=4e4376414aff7a38460ef53cafabe6515f91e7ca
BASE=03655f9bcde8743c1bc1cc2709424c1bafd42f45
D=$(mktemp -d "$HOME/xgw-auditfix.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/audit_fixes_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' 'ea4edf100888e62d22a73e2915737d0300e3769a5e1c412db039aa4ba37b690e' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging | wc -l
```

Ожидается `OK` и `15`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, две строки `INFO absent_table
family=… rc=… known_text=…` (переписать), `OK absent_table`, `OK installed_is_base`, `INFO state=…
members=… spares=… subscriptions=…` (переписать), `OK prepare`, `helper_rc=0`. Записать числа
OK/WARN/FAIL diag и режим пула.
- `STOP absent_table` — ответ системы отличается от ожидаемого: установку не делать, отчёт PARTIAL;
- `STOP installed_is_base` — стоит не та версия: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты (от владельца, без sudo)

Здесь проверяются сами отказы: служебные адреса, чужой PID, сбой на каждом шаге снятия правил,
откаты ufw и DHCP, гонка conncheck.

```bash
FILES="tests/test_fetch.py tests/test_runtime.py tests/test_net.py tests/test_conncheck.py tests/test_managed.py tests/test_ops.py tests/test_install.py tests/test_daemon.py tests/test_freepool_backend.py tests/test_panel.py"
for T in new base; do
  (cd "$D/$T" && PYTHONPATH=src timeout 1200 python3 -m pytest -p no:cacheprovider $FILES >"$D/out-$T" 2>&1; echo "$T rc=$?")
  tail -1 "$D/out-$T"
  grep -E '^(FAILED|ERROR) tests/' "$D/out-$T" | sed 's/ - .*//' | sort >"$D/fails-$T"
done
echo "новые падения:"; comm -23 "$D/fails-new" "$D/fails-base"; echo "конец списка"
echo "упавшие на прежнем коде:"; wc -l <"$D/fails-base"; echo "конец списка"
cd ~/xgw
```

Ожидаются для new и base `rc=0` или `rc=1` и итог pytest; у new пройденных больше, чем у base. Между
`новые падения:` и `конец списка` — пусто. Число упавших на прежнем коде — в отчёт. Новые падения или
`rc=124` — записать, установку не делать, отчёт PARTIAL.

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить правки аудита (15 файлов из шага 1) поверх текущей версии
штатным установщиком? Установщик перезапустит демон. Если on/HTTPS не подтвердятся за 45 с, помощник
сам вернёт прежнюю версию и проверит связь. Затем 20 минут наблюдения». Дождаться явного ответа, время
записать приватно. Нет ответа или отказ — INSTALL_NOT_RUN, перейти к шагу 7.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-auditfix-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-auditfix-deploy.log && break; sleep 5; done; cat /run/xgw-auditfix-deploy.log'
```

Вторую команду можно повторять, в том числе после обрыва связи; установку второй раз не запускать.
Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`, `helper_rc=0`. Записать
`at`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL, повтор только по указанию владельца;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл: записать
  времена, перейти к шагу 7 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Одно наблюдение, 20 минут (только чтение)

```bash
sudo python3 -I "$H" observe 20 2>&1 | tee "$D/observe.txt"
```

Ожидаются `INFO from=install`, `INFO window_min=… states=[…] status_age_max_s=…`, `OK fields`, по
строке `INFO sub N state=… set_age_s=… reason=…`, `OK age_consistent`, `OK subscription_path`, `INFO
via_xray_errors=… target_refused=… unconfirmed=… tracebacks=…`, `OK no_tracebacks`, `INFO
unknown_lines=0`, `OK state_known`, `INFO urls_checked=…`, `OK no_urls_in_status`, `OK config_unchanged`,
`OK on`, `OK https`, затем `OK subscriptions_reported`, `helper_rc=0`.

- `state=fresh reason=none` — подписка получена новым кодом;
- `target_refused` больше 0 или `STOP subscription_path` — **FAIL**: подписка, работавшая раньше,
  теперь отклоняется. Сразу владельцу, не чинить;
- `via_xray_errors` больше 0 — записать число, причину не придумывать;
- `helper_rc=4` с `NOT_RUN fetch` — подписка с установки не опрашивалась: NOT_RUN по ней, не FAIL;
- `STOP no_tracebacks`, `STOP state_known`, `STOP fields`, `STOP age_consistent` — FAIL, не чинить;
- `STOP no_urls_in_status` — **сразу владельцу**, файл статуса никуда не копировать;
- `WARN status_age` — записать `status_age_max_s`, причину не придумывать; DEGRADED не называть
  «обычной волной»;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же. Каталог /run/xgw-auditfix-install
остаётся до перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit-fixes-ДАТА.md` в freepool, одна страница, без пути
D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; файлов 15 (да/нет):
Подготовка: helper_rc; on/HTTPS; absent_table (rc и known_text для 4 и 6); diag до (OK/WARN/FAIL);
  state, members, spares, subscriptions:
Тесты: new и base (rc, итог); новые падения (пусто/какие); упавших на base:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Наблюдение 20 мин: helper_rc; состояния с числом замеров; status_age_max_s; строки INFO sub;
  via_xray_errors, target_refused, unconfirmed, tracebacks; unknown_lines; config_unchanged:
Конечное: on/HTTPS, diag после, режим пула без изменений (да/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит на машине:
```
