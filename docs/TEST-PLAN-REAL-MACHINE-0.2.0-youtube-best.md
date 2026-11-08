# ThinkCentre: отдельный выход для видео YouTube

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 348): режим `[media] youtube_mode = "best"`
ведёт новые соединения к видеосети YouTube через сервер с лучшим свежим замером, остальной трафик не
меняется. По умолчанию выключено. **Запускать только после отчёта audit-fixes со статусом PASS:**
этот код стоит поверх него. Иначе `STOP installed_is_base`.

Что не проверяется и не заявляется: одно соединение не делится между серверами, видео на шлюзе не
кэшируется, замер — файл Google, а не сама скорость видео, улучшение видео не гарантируется.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: подписки, пул, ручной выбор, «Обновить», замеры, WAN, LAN, Tailscale и сетевые правила;
перезапуск демона, кроме установки шага 5; `xgw net down`, перезагрузка, `--force`. config.toml
меняет только помощник шагов 6 и 9. В отчёт — только числа, признаки и имена тестов: без имён серверов
и подписок, адресов, доменов, тегов, SNI, short_id, сумм файлов и снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=30e40684d905a8957a72393f9de8592fbe89f4a5
BASE=4e4376414aff7a38460ef53cafabe6515f91e7ca
D=$(mktemp -d "$HOME/xgw-youtube.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/youtube_best_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' 'ecb349ddf80d8cdf4dbe6582f9641bcd16b9f5824b7b09331a3bc97d7e1239ac' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging | wc -l
```

Ожидается `OK` и `7`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`, `OK
no_media_section`, `INFO state=… members=… spares=…` (переписать), `OK prepare`, `helper_rc=0`. Записать
числа OK/WARN/FAIL diag и режим пула.
- `STOP installed_is_base` — audit-fixes не установлен: установку не делать, отчёт PARTIAL;
- `STOP no_media_section` — раздел уже есть, его писал не помощник: сообщить владельцу, не менять;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

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

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить выход для видео YouTube поверх текущей версии штатным
установщиком? Режим останется выключенным. Установщик перезапустит демон; если on/HTTPS не подтвердятся
за 45 с, помощник вернёт прежнюю версию». Нет ответа или отказ — INSTALL_NOT_RUN, перейти к шагу 10.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-youtube-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-youtube-deploy.log && break; sleep 5; done; cat /run/xgw-youtube-deploy.log'
```

Вторую команду можно повторять; установку второй раз не запускать. Норма: `OK baseline`, `install_rc=0
at=…`, `OK on`, `OK https`, `OK installed`, `helper_rc=0`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL;
- `recovery_started_at=…`, `rollback_verified=true` — возврат прошёл: к шагу 10 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Согласие и включение

Сначала 10 минут наблюдения при выключенном режиме (шаг 7 с `observe 10`): ожидается
`states=[('off', …)]`, `helper_rc=4` и `NOT_RUN best` — при выключенном режиме это норма.

Затем спросить владельца: «Разрешаете включить режим best на 30 минут? Помощник допишет раздел [media]
в config.toml, а в конце вернёт файл байт в байт». Отказ или нет ответа — INSTALL_ONLY, сразу к шагу 10.

```bash
sudo python3 -I "$H" enable
```

Норма: `OK installed_first`, `OK enable_once`, `OK no_media_section`, `INFO media_state=…`, `OK enabled`,
`OK on`, `OK https`. `STOP enabled` — перейти к шагу 9, отчёт FAIL.

## 7. Наблюдение 30 минут (только чтение)

```bash
sudo python3 -I "$H" observe 30 2>&1 | tee "$D/observe.txt"
```

Ожидаются `INFO window_min=… states=[…] exit_changes=… sample_age_max_s=…`, `INFO exit_mbps=…`, `INFO
diag_youtube_lines=… diag_warn=0`, `OK diag_youtube`, `OK xray_not_restarted`, `OK not_degraded`, `OK
config_unchanged`, `OK on`, `OK https`, `OK best_applied`, `helper_rc=0`.

- `helper_rc=4` с `NOT_RUN best` — свежих замеров не набралось: NOT_RUN по режиму, не FAIL;
- `STOP xray_not_restarted`, `STOP diag_youtube`, `STOP not_degraded` — FAIL, не чинить, к шагу 9;
- `STOP on` / `STOP https` — **сразу шаг 9**, затем владельцу;
- `exit_changes` больше 2 за 30 минут — записать, причину не придумывать.

DEGRADED из `Состояние:` не называть «обычной волной» и причину не придумывать.

## 8. Видео глазами владельца (по желанию)

Попросить владельца пока идёт шаг 7 открыть на любом устройстве сети одно и то же видео и сказать
одним словом: лучше, так же или хуже, чем обычно. Это мнение, а не замер: записать как есть.

## 9. Возврат настроек (обязательно, если был шаг 6)

```bash
sudo python3 -I "$H" disable
```

Норма: `OK backup_found`, `OK config_restored`, `INFO media_state=off`, `OK disabled`, `OK on`, `OK https`.
`STOP` — сразу владельцу, ничего не чинить.

## 10. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-best-ДАТА.md` в freepool, одна страница, без пути
D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; число файлов совпало (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); state, members, spares:
Тесты: new и base (rc, итог); новые падения (пусто/какие); упавших на base:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Режим выключен, 10 мин: states:
Включение: согласие (время) или INSTALL_ONLY; helper_rc; media_state:
Наблюдение 30 мин: helper_rc; states; exit_changes; sample_age_max_s; exit_mbps; diag_youtube_lines;
  xray_not_restarted; not_degraded; config_unchanged:
Мнение владельца о видео (лучше / так же / хуже / не смотрел):
Возврат настроек: config_restored; media_state:
Конечное: on/HTTPS, diag после, режим пула без изменений (да/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN / INSTALL_ONLY; первый непройденный шаг; что стоит на машине:
```
