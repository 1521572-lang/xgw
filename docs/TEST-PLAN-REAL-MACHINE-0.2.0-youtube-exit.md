# ThinkCentre: страница и видео YouTube через один выход

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 354). В режиме `best` через выход для видео теперь
идут и видеосеть, и страница YouTube: ссылка на видео выдаётся для адреса, с которого открыта страница.
Ставится поверх 390b38f. Режим `best` включается ненадолго, затем помощник проверяет маршрут и запускает
настоящий браузер **без окна**: он играет четыре общедоступных ролика обычным путём через шлюз.
Внешние устройства не нужны.

Разрешения владельца даны 09.11 только для этой проверки: запросы к адресам YouTube вне настроек XGW и
запуск уже установленного браузера без окна. Браузер не устанавливается. Если его нет — итог NOT_RUN.

Что не проверяется и не заявляется: качество и плавность видео, поведение при смене выхода во время
просмотра, приложения YouTube на телефонах. Невидимость для ТСПУ не заявляется.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: подписки, пул, ручной выбор (ни ставить, ни снимать), «Обновить», замеры, WAN, LAN, Tailscale и
сетевые правила; перезапуск демона, кроме установки шага 5; `xgw net down`, перезагрузка, `--force`.
config.toml меняет только помощник шагов 6 и 8. В отчёт — только числа, признаки и имена тестов: без имён
серверов и подписок, адресов, доменов, тегов, SNI, short_id, сумм файлов и снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=49f0440cda315b9b66eff7f33c72ca3ab76058e9
BASE=390b38f49b40274d6ab81c32a24c1915686972b4
D=$(mktemp -d "$HOME/xgw-exit.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/youtube_exit_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' 'ceadea9339864153206623e54f6719d124a9a2c6e50efcc9aa1257f3ae7daeda' "$H" | sha256sum -c -
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
FILES="tests/test_config.py tests/test_generator.py tests/test_daemon.py tests/test_diag.py"
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
один раз: «Разрешаете установить обновление и включить режим best примерно на 15 минут? Установщик
перезапустит демон; если on/HTTPS не подтвердятся за 2 минуты, помощник вернёт прежнюю версию. В конце
config.toml вернётся байт в байт». Нет ответа или отказ — NOT_RUN, к шагу 9.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-youtube-exit.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 110); do grep -q "^helper_rc=" /run/xgw-youtube-exit.log && break; sleep 5; done; cat /run/xgw-youtube-exit.log'
```

Вторую команду можно повторять; установку второй раз не запускать. Норма: `OK baseline`, `install_rc=0
at=…`, строки `ATTEMPT …`, `OK installed`, `helper_rc=0`. Строки `ATTEMPT` — в отчёт как есть. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL, к шагу 9;
- `recovery_started_at=…`, `rollback_verified=true` — возврат прошёл: PARTIAL, к шагу 9;
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 9 минут — только читать журнал установки, сообщить владельцу.

## 6. Контрольный запуск браузера и включение

```bash
sudo python3 -I "$H" enable "$D"
```

Идёт до 6 минут. Сначала браузер играет ролики при выключенном режиме, затем включается `best`. Норма:
`OK installed_first`, `OK enable_once`, `INFO browser=…`, `INFO play=…`, `INFO baseline_played=…`,
`INFO media_state=…`, `OK enabled`, `OK on`, `OK https`, `helper_rc=0`. Строки `INFO` — в отчёт как есть.
- `STOP installed_first` или `STOP enable_once` — файл не менялся: NOT_RUN, к шагу 9;
- `STOP user` — помощник запущен не через sudo от владельца: NOT_RUN, к шагу 9;
- `STOP enabled` — к шагу 8, отчёт FAIL.

## 7. Маршрут и браузер при включённом режиме (только чтение настроек)

```bash
sudo python3 -I "$H" check "$D" 2>&1 | tee "$D/check.txt"
```

Идёт до 10 минут. Норма: строка `INFO route_video=…`, `INFO browser=…`, `INFO play=…`, `OK on`, `OK https`,
`INFO played=… baseline=… need=3`, `OK route`, `OK play`, `helper_rc=0`. Строки `INFO` — в отчёт как есть.
- `NOT_RUN best`, `NOT_RUN route …` или `NOT_RUN play`, `helper_rc=4` — не FAIL: NOT_RUN, к шагу 8;
- `STOP route_video`, `STOP route_page`, `STOP route_api` или `STOP play` — FAIL, не чинить, к шагу 8;
- `STOP on` / `STOP https` — **сразу шаг 8**, затем владельцу.

Коды `error_…` в `INFO play` переписать как есть, причину не придумывать.
DEGRADED из `Состояние:` не называть «обычной волной» и причину не придумывать.

## 8. Возврат настроек (обязательно, если был шаг 6)

```bash
sudo python3 -I "$H" disable
```

Норма: `OK backup_found`, `OK config_restored`, `OK disabled`, `OK on`, `OK https`. `STOP` — сразу
владельцу, ничего не чинить.

## 9. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-exit-ДАТА.md` в freepool, одна страница, без пути D.
`git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; число файлов совпало (да/нет):
До: helper_rc; on/HTTPS; diag (OK/WARN/FAIL); режим пула:
Тесты: new и base (rc, итог); новые падения (пусто/какие); упавших на base:
Согласие (в сообщении / спрошено) или NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Строки ATTEMPT как есть:
Включение: enable helper_rc; строки INFO как есть:
Проверка: helper_rc; строки INFO как есть; итоговые OK/STOP/NOT_RUN:
Возврат настроек: config_restored; disabled:
Конечное: on/HTTPS, diag после, режим пула без изменений (да/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL; первый непройденный шаг; что стоит на машине:
```

PASS — только при `OK route`, `OK play` и пустых новых падениях.
