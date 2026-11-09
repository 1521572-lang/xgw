# ThinkCentre: режим best и маршрут видео с самого шлюза

Исполнитель — GLM-5.3-Flash. На машине уже стоит код 30e4068 (отчёт youtube-best: INSTALL_ONLY).
Установка не нужна. Режим best (ASSUMPTIONS п. 348) включается на 30 минут, затем с самого шлюза идут
малые запросы: к видеосети и к обычному адресу. Если байты на выбранном выходе растут только от первых,
видео действительно идёт через него. Внешние устройства не нужны.

Что не проверяется и не заявляется: само видео, его качество и скорость, деление соединения между
серверами, кэш на шлюзе. Запросы малые (ответ без тела), это не замер скорости.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: подписки, пул, ручной выбор, «Обновить», замеры, WAN, LAN, Tailscale и сетевые правила;
перезапуск демона, `xgw net down`, перезагрузка, `--force`. config.toml меняет только помощник шагов
3 и 6. В отчёт — только числа, признаки и имена тестов: без имён серверов и подписок, адресов, доменов,
тегов, SNI, short_id, сумм файлов и снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=975bbc9357b5983747d667ec777a6ddb00d39bda
INSTALLED=30e40684d905a8957a72393f9de8592fbe89f4a5
D=$(mktemp -d "$HOME/xgw-route.XXXXXXXX")
H="$D/new/docs/helpers/youtube_best_check.py"
git worktree add --detach "$D/new" "$CODE" && test "$(git -C "$D/new" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' 'de92a389b5912b06cf17b16144841a1a92f1a7bae94007e6d4acdad9092135eb' "$H" | sha256sum -c -
git -C "$D/new" diff --name-only "$INSTALLED" "$CODE" -- src packaging | wc -l
```

Ожидается `OK` и `0`: код шлюза не менялся, новый только помощник. Иначе — STOP, сообщить владельцу.
Путь D — приватно.

## 2. Исходное состояние (только чтение)

```bash
umask 077
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK on`, `OK https`, `helper_rc=0`. Записать числа OK/WARN/FAIL diag и режим пула. Иначе —
STOP, сообщить владельцу, режим не включать.

## 3. Согласие и включение

Согласие владелец даёт в сообщении, которым передаёт это ТЗ (слово «разрешаю»). Если его нет — спросить
один раз: «Разрешаете включить режим best на 30 минут? Помощник допишет раздел [media] в config.toml,
а в конце вернёт файл байт в байт». Нет ответа или отказ — NOT_RUN, сразу к шагу 7.

```bash
sudo python3 -I "$H" enable
```

Норма: `OK installed_first`, `OK enable_once`, `OK no_media_section`, `INFO media_state=…`, `OK enabled`,
`OK on`, `OK https`.
- `STOP installed_first` или `STOP no_media_section` — файл не менялся: NOT_RUN, к шагу 7;
- `STOP enabled` — к шагу 6, отчёт FAIL.

## 4. Наблюдение 30 минут (только чтение)

```bash
sudo python3 -I "$H" observe 30 2>&1 | tee "$D/observe.txt"
```

Ожидаются `INFO window_min=… states=[…] exit_changes=… sample_age_max_s=…`, `INFO exit_mbps=…`, `INFO
diag_youtube_lines=… diag_warn=0`, `OK diag_youtube`, `OK xray_not_restarted`, `OK not_degraded`, `OK
config_unchanged`, `OK on`, `OK https`, `OK best_applied`, `helper_rc=0`.
- `helper_rc=4` с `NOT_RUN best` — свежих замеров не набралось: NOT_RUN по режиму, не FAIL; шаг 5 всё равно выполнить;
- `STOP xray_not_restarted`, `STOP diag_youtube`, `STOP not_degraded` — FAIL, не чинить, к шагу 6;
- `STOP on` / `STOP https` — **сразу шаг 6**, затем владельцу;
- `exit_changes` больше 2 за 30 минут — записать, причину не придумывать.

DEGRADED из `Состояние:` не называть «обычной волной» и причину не придумывать.

## 5. Маршрут видео с самого шлюза

```bash
sudo python3 -I "$H" route 2>&1 | tee -a "$D/route.txt"
```

Около минуты, 36 малых запросов. Норма: `OK xray_not_restarted`, `INFO route_video=[…] route_control=[…]
need=…`, `OK route_video_seen`, `OK route_video`, `helper_rc=0`. Числа — байты: переписать как есть.
- `NOT_RUN route unclear` — выход видео совпал с обычным маршрутом или мешает чужой трафик: не FAIL.
  Повторить до двух раз с паузой 2 минуты, записать все попытки;
- `NOT_RUN route state` — режим сейчас не best: не FAIL, записать;
- `NOT_RUN route changed` или `NOT_RUN route <имя ошибки>` — один повтор через 2 минуты, записать;
- `STOP route_video_seen` — запросы прошли, но на выходе видео почти нет байт: FAIL, не чинить, к шагу 6;
- `STOP xray_not_restarted` — FAIL, к шагу 6.

Причину `unclear` не придумывать: совпадение выхода с обычным маршрутом помощник отдельно не показывает.

## 6. Возврат настроек (обязательно, если был шаг 3)

```bash
sudo python3 -I "$H" disable
```

Норма: `OK backup_found`, `OK config_restored`, `INFO media_state=off`, `OK disabled`, `OK on`, `OK https`.
`STOP` — сразу владельцу, ничего не чинить.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-route-ДАТА.md` в freepool, одна страница, без пути
D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; изменённых файлов кода 0 (да/нет):
До: helper_rc; on/HTTPS; diag (OK/WARN/FAIL); режим пула:
Согласие (в сообщении / спрошено, время) или NOT_RUN; enable helper_rc; media_state:
Наблюдение 30 мин: helper_rc; states; exit_changes; sample_age_max_s; exit_mbps; diag_youtube_lines;
  xray_not_restarted; not_degraded; config_unchanged:
Маршрут (каждая попытка): helper_rc; route_video; route_control; need; итоговая строка:
Возврат настроек: config_restored; media_state:
Конечное: on/HTTPS, diag после, режим пула без изменений (да/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL; первый непройденный шаг; что стоит на машине:
```

PASS — только при `OK best_applied` и `OK route_video`. `route unclear` при `OK best_applied` — PARTIAL:
режим работал, маршрут не доказан.
