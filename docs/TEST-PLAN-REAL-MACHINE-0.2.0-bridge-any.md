# ThinkCentre: новое поколение sing-box проверяется любым пригодным сервером

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 351, 352). В отчёте bridges-cause все 5 мостов
Xray — запасные и не отвечают, поэтому с 07:38 падала каждая общая сборка. Теперь, если мосты только
запасные, новое поколение можно проверить через сервер работающего ядра: безлимитный или лимитный с
нормальной скоростью. Ставится поверх d7c672b. Затем помощник до 30 минут читает журнал: сменилось ли
поколение и завершилась ли сборка.

Что не проверяется и не заявляется: почему молчат сами hysteria2, качество и скорость, видео.
Молчащие запасные останутся в конфиге — это ожидаемо.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: подписки, пул, ручной выбор, «Обновить», замеры, WAN, LAN, Tailscale и сетевые правила;
config.toml; перезапуск демона, кроме установки шага 5; `xgw net down`, перезагрузка, `--force`.
В отчёт — только числа, признаки и имена тестов: без имён серверов и подписок, адресов, доменов, тегов,
SNI, short_id, сумм файлов и снимков экрана. Журнал руками не читать.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=b88511f26249a3d350a206e484aa5660c9598bff
BASE=d7c672bb9948fc802a34ad1df96396a016ea52a0
D=$(mktemp -d "$HOME/xgw-any.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/bridge_any_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '242738ee6a6a7495da1f54ff2e285713969011e96b003d1177d62d81f0f840f3' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging | wc -l
```

Ожидается `OK` и `2`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Исходное состояние (только чтение)

```bash
umask 077
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK on`, `OK https`, `helper_rc=0`. Записать числа OK/WARN/FAIL diag и режим пула. Иначе —
STOP, сообщить владельцу, ничего не устанавливать.

## 3. Тесты (от владельца, без sudo)

```bash
FILES="tests/test_singbox_generations.py tests/test_daemon.py"
for T in new base; do
  (cd "$D/$T" && PYTHONPATH=src timeout 1200 python3 -m pytest -p no:cacheprovider $FILES >"$D/out-$T" 2>&1; echo "$T rc=$?")
  tail -1 "$D/out-$T"
  grep -E '^(FAILED|ERROR) tests/' "$D/out-$T" | sed 's/ - .*//' | sort >"$D/fails-$T"
done
echo "новые падения:"; comm -23 "$D/fails-new" "$D/fails-base"; echo "конец списка"
echo "упавшие на прежнем коде:"; wc -l <"$D/fails-base"; echo "конец списка"
cd ~/xgw
```

Ожидаются для new и base `rc=0` или `rc=1` и итог pytest. Между `новые падения:` и `конец списка` —
пусто. Новые падения или `rc=124` — записать, установку не делать, отчёт PARTIAL.

## 4. Согласие

Согласие владелец даёт в сообщении, которым передаёт это ТЗ (слово «разрешаю»). Если его нет — спросить
один раз: «Разрешаете установить обновление? Установщик перезапустит демон; если on/HTTPS не
подтвердятся за 45 с, помощник вернёт прежнюю версию». Нет ответа или отказ — NOT_RUN, сразу к шагу 7.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-bridge-any.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-bridge-any.log && break; sleep 5; done; cat /run/xgw-bridge-any.log'
```

Вторую команду можно повторять; установку второй раз не запускать. Норма: `OK baseline`, `install_rc=0
at=…`, `OK on`, `OK https`, `OK installed`, `helper_rc=0`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL, к шагу 7;
- `recovery_started_at=…`, `rollback_verified=true` — возврат прошёл: PARTIAL, к шагу 7;
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал установки, сообщить владельцу.

## 6. Наблюдение (только чтение, до 30 минут)

```bash
sudo python3 -I "$H" observe 30 2>&1 | tee "$D/observe.txt"
```

Заканчивается раньше, если поколение сменилось. Норма: `OK installed_first`, `INFO events …`, `INFO
checked …`, `INFO fail_kinds …`, `OK xray_not_restarted`, `OK on`, `OK https`, `OK generation_changed`,
`helper_rc=0`. Строки `INFO` переписать как есть.
- `NOT_RUN no_generation_needed`, `helper_rc=4` — новое поколение за окно не понадобилось: NOT_RUN;
- `STOP generation_still_failing`, `helper_rc=3` — FAIL, не чинить, к шагу 7;
- `STOP xray_not_restarted` — FAIL, не чинить, к шагу 7;
- `STOP on` / `STOP https` — сразу владельцу, затем к шагу 7.

DEGRADED из `Состояние:` не называть «обычной волной» и причину не придумывать. Новую версию не
откатывать без слов владельца.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-bridge-any-ДАТА.md` в freepool, одна страница, без пути D.
`git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; число файлов совпало (да/нет):
До: helper_rc; on/HTTPS; diag (OK/WARN/FAIL); режим пула:
Тесты: new и base (rc, итог); новые падения (пусто/какие); упавших на base:
Согласие (в сообщении / спрошено) или NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Наблюдение: helper_rc; INFO events; INFO checked; INFO fail_kinds; xray_not_restarted; итоговая строка:
Конечное: on/HTTPS, diag после, режим пула без изменений (да/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL; первый непройденный шаг; что стоит на машине:
```

PASS — только при `OK generation_changed`, `OK xray_not_restarted`, on/HTTPS и пустых новых падениях.
