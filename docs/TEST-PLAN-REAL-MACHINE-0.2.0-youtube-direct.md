# ThinkCentre: правило видео отдельно от общей сборки, маршрут и состояние мостов sing-box

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 350): правило `[media] youtube_mode = "best"`
теперь ставится прямо в работающий Xray, меняется только маршрутизация, Xray не перезапускается.
Раньше оно шло в общей сборке и застревало вместе с ней на проверке нового поколения sing-box
(отчёт youtube-journal). Ставится поверх 059d4fc. Затем режим включается на 30 минут, с самого шлюза
идут малые запросы, а в конце проверяются мосты работающего поколения sing-box. Внешние устройства
не нужны.

Что не проверяется и не заявляется: само видео, его качество и скорость, деление соединения между
серверами, кэш на шлюзе. Запросы малые, это не замер скорости.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: подписки, пул, ручной выбор (ни ставить, ни снимать), «Обновить», замеры, WAN, LAN, Tailscale и
сетевые правила; перезапуск демона, кроме установки шага 5; `xgw net down`, перезагрузка, `--force`.
config.toml меняет только помощник шагов 6 и 10. В отчёт — только числа, признаки и имена тестов: без
имён серверов и подписок, адресов, доменов, тегов, SNI, short_id, сумм файлов и снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=d7c672bb9948fc802a34ad1df96396a016ea52a0
BASE=059d4fc82ff2c4660599da1a3e30a895fc7bb974
D=$(mktemp -d "$HOME/xgw-direct.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/youtube_best_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' 'e0c961ebabe365501ebcead4ea0d6d2e24302817b3251f35a570eb8ef3878866' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging | wc -l
```

Ожидается `OK` и `3`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Исходное состояние (только чтение)

```bash
umask 077
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK on`, `OK https`, `helper_rc=0`. Записать числа OK/WARN/FAIL diag и режим пула. Иначе —
STOP, сообщить владельцу, ничего не устанавливать.

## 3. Тесты (от владельца, без sudo)

```bash
FILES="tests/test_youtube.py tests/test_config.py tests/test_generator.py tests/test_daemon.py tests/test_daemon_main.py tests/test_diff.py tests/test_applier.py tests/test_diag.py tests/test_runtime.py"
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
один раз: «Разрешаете установить обновление и включить режим best на 30 минут? Установщик перезапустит
демон; если on/HTTPS не подтвердятся за 45 с, помощник вернёт прежнюю версию. В конце config.toml
вернётся байт в байт». Нет ответа или отказ — NOT_RUN, сразу к шагу 11.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-youtube-direct.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-youtube-direct.log && break; sleep 5; done; cat /run/xgw-youtube-direct.log'
```

Вторую команду можно повторять; установку второй раз не запускать. Норма: `OK baseline`, `install_rc=0
at=…`, `OK on`, `OK https`, `OK installed`, `helper_rc=0`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL, к шагу 11;
- `recovery_started_at=…`, `rollback_verified=true` — возврат прошёл: PARTIAL, к шагу 11;
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Включение

```bash
sudo python3 -I "$H" enable
```

Норма: `OK installed_first`, `INFO pin_active=…` (переписать), `OK enable_once`, `OK no_media_section`,
`INFO media_state=…`, `OK enabled`, `OK on`, `OK https`.
- `STOP installed_first`, `STOP enable_once` или `STOP no_media_section` — файл не менялся: NOT_RUN, к шагу 11;
- `STOP enabled` — к шагу 10, отчёт FAIL.

## 7. Наблюдение 30 минут (только чтение)

```bash
sudo python3 -I "$H" observe 30 2>&1 | tee "$D/observe.txt"
```

Ожидаются `INFO window_min=… states=[…] exit_changes=… sample_age_max_s=…`, `INFO exit_mbps=…`, `INFO
diag_youtube_lines=… diag_warn=0`, `OK diag_youtube`, `OK xray_not_restarted`, `OK not_degraded`, `OK
config_unchanged`, `OK on`, `OK https`, `OK best_applied`, `helper_rc=0`.
- `helper_rc=4` с `NOT_RUN best` — режим не применился: NOT_RUN, не FAIL; причину взять только из `states` (`waiting_for_samples` — нет свежих замеров). Шаги 8 и 9 всё равно выполнить;
- `STOP not_degraded`, `STOP xray_not_restarted`, `STOP diag_youtube` — FAIL, не чинить. Шаг 8 пропустить, **шаг 9 выполнить**, затем шаг 10;
- `STOP on` / `STOP https` — **сразу шаг 10**, затем владельцу;
- `exit_changes` больше 2 за 30 минут — записать, причину не придумывать.

DEGRADED из `Состояние:` не называть «обычной волной» и причину не придумывать.

## 8. Маршрут видео с самого шлюза

```bash
sudo python3 -I "$H" route 2>&1 | tee -a "$D/route.txt"
```

Около минуты, 36 малых запросов. Норма: `OK xray_not_restarted`, `INFO route_video=[…] route_control=[…]
need=…`, `OK route_video_seen`, `OK route_video`, `helper_rc=0`. Числа — байты: переписать как есть.
- `NOT_RUN route unclear` — не FAIL. Повторить до двух раз с паузой 2 минуты, записать все попытки;
- `NOT_RUN route state` — режим сейчас не best: не FAIL, записать;
- `NOT_RUN route changed` или `NOT_RUN route <имя ошибки>` — один повтор через 2 минуты, записать;
- `STOP route_video_seen` — запросы прошли, но на выходе видео почти нет байт: FAIL, не чинить, к шагу 9;
- `STOP xray_not_restarted` — FAIL, к шагу 9.

## 9. Мосты работающего поколения sing-box

```bash
sudo python3 -I "$H" bridges 2>&1 | tee "$D/bridges.txt"
```

Один запрос через каждый мост, не больше 8 и не дольше 20 с на мост. Вывод: `INFO bridges total=…
members=… curl_rc=[…]`, `helper_rc=0`. Переписать как есть. Любые коды — **не FAIL** и причину не
придумывать: разбор делает разработчик. `STOP …` — записать строку, продолжить.

## 10. Возврат настроек (обязательно, если был шаг 6)

```bash
sudo python3 -I "$H" disable
```

Норма: `OK backup_found`, `OK config_restored`, `INFO media_state=off`, `OK disabled`, `INFO pin_active=…`
(должно совпасть с шагом 6), `OK on`, `OK https`. `STOP` — сразу владельцу, ничего не чинить.

## 11. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-direct-ДАТА.md` в freepool, одна страница, без пути
D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; число файлов совпало (да/нет):
До: helper_rc; on/HTTPS; diag (OK/WARN/FAIL); режим пула:
Тесты: new и base (rc, итог); новые падения (пусто/какие); упавших на base:
Согласие (в сообщении / спрошено) или NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Включение: enable helper_rc; pin_active; media_state:
Наблюдение 30 мин: helper_rc; states; exit_changes; sample_age_max_s; exit_mbps; diag_youtube_lines;
  xray_not_restarted; not_degraded; config_unchanged:
Маршрут (каждая попытка): helper_rc; route_video; route_control; need; итоговая строка:
Мосты: total; members; curl_rc; helper_rc:
Возврат настроек: config_restored; media_state; pin_active совпал (да/нет):
Конечное: on/HTTPS, diag после, режим пула без изменений (да/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL; первый непройденный шаг; что стоит на машине:
```

PASS — только при `OK best_applied` и `OK route_video`. `route unclear` при `OK best_applied` — PARTIAL:
режим работал, маршрут не доказан. Если `pin_active=False`, в отчёте указать: работа при ручном выборе
этим прогоном не проверена.
