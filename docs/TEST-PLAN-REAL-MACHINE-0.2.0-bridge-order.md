# ThinkCentre: новое поколение sing-box — мосты работающих серверов первыми

Исполнитель — GLM-5.3-Flash. Отчёт sub-remove (179bdab, c9158d1) — PASS, на машине стоит
e18f53e. В конце того отчёта: пересборка конфига дважды остановилась на «новое поколение
не прошло настоящий запрос через мост», запасных 4 вместо ~54. Код CODE (ASSUMPTIONS
п. 338): перед заменой sing-box шлюз проверяет мосты не в порядке конфига, а начиная с
серверов, которые сейчас ведут трафик, затем по доле сбоев за сутки. На мост уходит не
больше 20 с (было 30), общий срок прежний — 90 с. При отказе в журнале теперь видно, сколько
мостов проверено и чем кончились попытки: «мостов проверено N из M: вид число». Новых запросов
к серверам нет: как и раньше, один запрос за раз. Невидимость для ТСПУ не проверяется.

Можно: терминал, `xgw status`, `xgw diag --no-net`, `journalctl -u xgw`, окно и панель (только
смотреть). Нельзя: подписки, пул, ручной выбор, «Обновить», «Проверить запасные», замеры
скорости, настройки, WAN, LAN, Tailscale и сетевые правила; перезапуск демона, кроме установки
шага 5; `xgw net down`, перезагрузка, `--force`, сторонние замеры и pcap. Пересборку не
вызывать: она идёт сама после установки (перезапуск демона) или при обновлении подписок. В
отчёт — только числа, слова состояний и виды отказов: без имён серверов и подписок, адресов,
доменов, стран, тегов, SNI, сумм файлов и снимков экрана. Каталог установки этой проверки —
/run/xgw-bridge-install, прежние не трогать.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=688f2da7a9e8372083f14542bd9ffef33940cff8
BASE=e18f53e27ccaa5928fcffd2ea605d957e605ab68
D=$(mktemp -d "$HOME/xgw-bridge.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/bridge_order_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' 'd7eb5d774a38597aa70034181c8d82d58c9c49b7d269ad7da4e0841c0cbbfa3e' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидается `OK` и ровно две строки: `src/xgw/apply/singbox_generation.py`, `src/xgw/daemon.py`.
Иначе — STOP, сообщить владельцу. Путь D записать приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`INFO state=… members=… spares=… assembly=…` (переписать), `INFO last_3h switched=…
refused=…` (переписать), `config_sha=…` (только приватно), `OK prepare`, `helper_rc=0`.
Записать числа OK/WARN/FAIL diag, режим пула и есть ли ручной выбор (да/нет).
- `STOP installed_is_base` — стоит не e18f53e: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты и логика (от владельца, без sudo)

```bash
cd "$TARGET" && for i in 1 2; do PYTHONPATH=src python3 -m pytest -p no:cacheprovider \
  tests/test_singbox_generations.py 2>&1 | tail -1; done
PYTHONPATH=src python3 -m pytest -p no:cacheprovider tests/test_daemon.py -k generation 2>&1 | tail -1
cd ~/xgw; python3 -I "$H" logic; echo "logic_rc=$?"
```

Ожидаются две одинаковые строки `N passed` и строка `2 passed` (числа записать, failed и error
нет). Затем `INFO order=[3] each_s=20.0`, `OK member_first`, `OK bridge_cap`,
`OK unknown_before_failing`, `INFO refusal=мостов проверено 3 из 3: stall 3`,
`OK refusal_summary`, `OK logic`, `helper_rc=0`, `logic_rc=0`. Падение или `STOP <имя>` —
записать имя, установку не делать (PARTIAL).

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить 688f2da (проверка нового поколения sing-box: два
файла из шага 1) поверх e18f53e штатным установщиком? Установщик перезапустит демон. Если
on/HTTPS не подтвердятся за 45 с, помощник сам вернёт e18f53e (начнёт не позже 60 с) и
проверит связь. Затем 20 минут наблюдения». Дождаться явного ответа, время записать приватно.
Нет ответа или отказ — INSTALL_NOT_RUN, перейти к шагу 7.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-bridge-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-bridge-deploy.log && break; sleep 5; done; cat /run/xgw-bridge-deploy.log'
```

Вторую команду можно повторять, в том числе после обрыва связи; установку второй раз не
запускать. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`,
`helper_rc=0`. Записать `at`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл:
  записать времена, перейти к шагу 7 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Одно наблюдение, 20 минут (только чтение)

Сразу после `helper_rc=0` шага 5; ничего не нажимать в панели и окне.

```bash
sudo python3 -I "$H" observe 20 2>&1 | tee "$D/observe.txt"
```

Помощник раз в 15 с читает `xgw status` и по окончании считает в журнале строки смены
поколения и отказа. Ожидаются `INFO window_min=… states=… spares_first=… spares_last=…
spares_max=… members_last=…`, `INFO switched=… refused=… error_lines=…`, строки
`INFO refusal мостов проверено …` (если были), `OK config_unchanged`, `OK on`, `OK https`.
Итог:
- `OK generation_switched`, `helper_rc=0` — поколение сменилось: PASS. Записать запасных
  в начале, в конце и наибольшее (ожидается больше 4, вплоть до прежних ~54);
- `STOP generation_refused`, `helper_rc=5` — отказ остался: FAIL. Переписать все строки
  `INFO refusal …` дословно (в них только числа и виды отказов) и `refused`;
- `NOT_RUN generation`, `helper_rc=4` — пересборки sing-box в окне не было: записать
  запасных; если их стало больше 4 — так и написать (поколение могло смениться при запуске
  демона без этой проверки). Итог NOT_RUN по проверке, PASS по регрессии;
- `STOP config_unchanged`, `STOP on`, `STOP https` — сразу владельцу, ничего не чинить.

## 7. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; пул тот же, что в шаге 2. Ручной выбор, снятый
до этой проверки, владелец ставит сам, когда захочет. Каталог /run/xgw-bridge-install
остаётся до перезагрузки.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-bridge-order-ДАТА.md` в freepool, одна страница,
без пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`,
затем `git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; два файла (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); state, members, spares, assembly;
  за 3 ч switched/refused:
Тесты: три строки N passed; logic_rc, order, refusal:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Наблюдение 20 мин: helper_rc; states; запасных в начале/в конце/наибольшее; members;
  switched, refused, error_lines; строки refusal дословно; config_unchanged:
Конечное: on/HTTPS, diag после, пул без изменений (да/нет), ручной выбор (есть/нет):
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит
на машине:
```
