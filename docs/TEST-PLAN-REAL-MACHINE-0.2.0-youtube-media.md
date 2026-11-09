# ThinkCentre: дополнительные проверки кандидатов в выход для видео

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 353). В режиме `best` живые безлимитные участники
теперь проверяются чаще обычного: раз в час с разбросом, один сервер за шаг, не чаще раза в 2 минуты, с
суточным лимитом 256 МБ. Ставится поверх b88511f. Затем режим `best` включается на 40 минут, и помощник
считает дополнительные проверки. Внешние устройства не нужны.

Что не проверяется и не заявляется: само видео, его качество, смена выхода при плохом сервере, поведение
при исчерпании лимита за сутки. Невидимость для ТСПУ не заявляется.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: подписки, пул, ручной выбор (ни ставить, ни снимать), «Обновить», замеры, WAN, LAN, Tailscale и
сетевые правила; перезапуск демона, кроме установки шага 5; `xgw net down`, перезагрузка, `--force`.
config.toml меняет только помощник шагов 6 и 8. В отчёт — только числа, признаки и имена тестов: без имён
серверов и подписок, адресов, доменов, тегов, SNI, short_id, сумм файлов и снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=390b38f49b40274d6ab81c32a24c1915686972b4
BASE=b88511f26249a3d350a206e484aa5660c9598bff
D=$(mktemp -d "$HOME/xgw-media.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/youtube_media_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '777c9983566a1b36e8a2b2f3929ba13a72ded98180b3ba55ed8f7e54df85248f' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging | wc -l
```

Ожидается `OK` и `4`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Исходное состояние (только чтение)

```bash
umask 077
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK on`, `OK https`, `helper_rc=0`. Записать числа OK/WARN/FAIL diag и режим пула. Иначе —
STOP, сообщить владельцу, ничего не устанавливать.

## 3. Тесты (от владельца, без sudo)

```bash
FILES="tests/test_youtube.py tests/test_config.py tests/test_daemon.py tests/test_diag.py tests/test_runtime.py"
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
один раз: «Разрешаете установить обновление и включить режим best на 40 минут? Установщик перезапустит
демон; если on/HTTPS не подтвердятся за 2 минуты, помощник вернёт прежнюю версию. Дополнительные проверки
тратят до 256 МБ в сутки. В конце config.toml вернётся байт в байт». Нет ответа или отказ — NOT_RUN, к шагу 9.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-youtube-media.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 110); do grep -q "^helper_rc=" /run/xgw-youtube-media.log && break; sleep 5; done; cat /run/xgw-youtube-media.log'
```

Вторую команду можно повторять; установку второй раз не запускать. Норма: `OK baseline`, `install_rc=0
at=…`, строки `ATTEMPT …`, `OK installed`, `helper_rc=0`. Строки `ATTEMPT` — в отчёт как есть. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL, к шагу 9;
- `recovery_started_at=…`, `rollback_verified=true` — возврат прошёл: PARTIAL, к шагу 9;
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 9 минут — только читать журнал установки, сообщить владельцу.

## 6. Включение

```bash
sudo python3 -I "$H" enable
```

Норма: `OK installed_first`, `INFO pin_active=…` (переписать), `OK enable_once`, `OK no_media_section`,
`INFO media_state=…`, `OK enabled`, `OK on`, `OK https`.
- `STOP installed_first`, `STOP enable_once` или `STOP no_media_section` — файл не менялся: NOT_RUN, к шагу 9;
- `STOP enabled` — к шагу 8, отчёт FAIL.

## 7. Наблюдение 40 минут (только чтение)

```bash
sudo python3 -I "$H" observe 40 2>&1 | tee "$D/observe.txt"
```

Норма: `INFO window_min=… states=[…] exit_changes=…`, `INFO extra_checks=… all_checks=… min_gap_s=…
probe_mb=… probe_limit_mb=… errors=…`, `OK xray_not_restarted`, `OK not_degraded`, `OK config_unchanged`,
`OK budget`, `OK on`, `OK https`, `OK best_applied`, `OK extra_checks`, `OK gap`, `helper_rc=0`.
Строки `INFO` переписать как есть.
- `NOT_RUN best` или `NOT_RUN extra_checks`, `helper_rc=4` — не FAIL: NOT_RUN, к шагу 8;
- `STOP gap`, `STOP budget`, `STOP not_degraded`, `STOP xray_not_restarted`, `STOP config_unchanged` — FAIL, не чинить, к шагу 8;
- `STOP on` / `STOP https` — **сразу шаг 8**, затем владельцу;
- `errors` больше 0 — записать, причину не придумывать.

DEGRADED из `Состояние:` не называть «обычной волной» и причину не придумывать.

## 8. Возврат настроек (обязательно, если был шаг 6)

```bash
sudo python3 -I "$H" disable
```

Норма: `OK backup_found`, `OK config_restored`, `INFO media_state=off`, `OK disabled`, `INFO pin_active=…`
(должно совпасть с шагом 6), `OK on`, `OK https`. `STOP` — сразу владельцу, ничего не чинить.

## 9. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-media-ДАТА.md` в freepool, одна страница, без пути D.
`git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; число файлов совпало (да/нет):
До: helper_rc; on/HTTPS; diag (OK/WARN/FAIL); режим пула:
Тесты: new и base (rc, итог); новые падения (пусто/какие); упавших на base:
Согласие (в сообщении / спрошено) или NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Строки ATTEMPT как есть:
Включение: enable helper_rc; pin_active; media_state:
Наблюдение: helper_rc; строки INFO как есть; итоговые OK/STOP/NOT_RUN:
Возврат настроек: config_restored; media_state; pin_active совпал (да/нет):
Конечное: on/HTTPS, diag после, режим пула без изменений (да/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL; первый непройденный шаг; что стоит на машине:
```

PASS — только при `OK best_applied`, `OK extra_checks`, `OK gap`, `OK budget` и пустых новых падениях.
