# ThinkCentre: подписку из config.toml можно убрать кнопкой и вернуть

Исполнитель — GLM-5.3-Flash. Отчёты profile-memory (ed18a9b) и gui-s3b-check (6a38144) — PASS,
на машине стоит 1568790. Код CODE (ASSUMPTIONS п. 337): у подписки, вписанной в config.toml,
в окне `xgw gui` и в браузерной панели теперь есть «Убрать». config.toml при этом не
меняется: имя подписки записывается в panel.json как убранное, и шлюз её больше не запрашивает.
Кэш её ответа остаётся. Убранные подписки перечислены в разделе «Подписки» с кнопкой
«Вернуть». Изменить такую подписку по-прежнему можно только правкой файла.

Можно: терминал, `xgw status`, `xgw diag --no-net`, `journalctl -u xgw`, окно и браузерную
панель. **Машинное зрение кликает только по разделам слева и по вкладкам вверху «Серверов».**
«Убрать», «Отмена» и «Вернуть» нажимает только владелец мышью. Нельзя: другие кнопки
подписок и серверов, «Обновить», «Замерить», «Проверить», поле «Добавить», ручной выбор,
режим пула, WAN, LAN, Tailscale, настройки и сетевые правила; `xgw net down`, перезагрузка,
`--force`, правка config.toml и panel.json руками. В отчёт — только числа, слова состояний и
признаки: без имён подписок и серверов, адресов, доменов, стран, тегов, сумм файлов и снимков
экрана. Каталог установки этой проверки — /run/xgw-subremove-install, прежние не трогать.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=e18f53e27ccaa5928fcffd2ea605d957e605ab68
BASE=1568790a2715e3c49e54eeb1f36bad469a64c9e9
D=$(mktemp -d "$HOME/xgw-subremove.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"; H="$TARGET/docs/helpers/sub_remove_check.py"
git worktree add --detach "$TARGET" "$CODE" && git worktree add --detach "$PREV" "$BASE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '5ad42ff6a101efc89d519f9aa3353d03c5a4384152cf4cfa9536de955c832aae' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging
```

Ожидается `OK` и ровно семь файлов: `src/xgw/config.py`, `src/xgw/gui/listing.py`,
`src/xgw/gui/pages.py`, `src/xgw/managed.py`, `src/xgw/ui/app.js`, `src/xgw/watch/appapi.py`,
`src/xgw/watch/panel.py`. Иначе — STOP, сообщить владельцу. Путь D записать приватно.

## 2. Подготовка (только чтение, повтор безопасен)

```bash
umask 077
sudo python3 -I "$H" prepare "$PREV"; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK tools`, `OK install_scripts_parse`, `OK on`, `OK https`, `OK installed_is_base`,
`INFO sources {…}` (переписать числа), `live_allowed=yes` или `no` (записать),
`config_sha=… panel_sha=…` (только приватно), `OK prepare`, `helper_rc=0`. Записать числа
OK/WARN/FAIL diag, состояние, режим пула и есть ли ручной выбор (да/нет).
- `STOP installed_is_base` — стоит не 1568790: установку не делать, отчёт PARTIAL;
- `STOP lock_active` / `STOP lock_finished` — ничего не удалять, сообщить владельцу;
- `STOP on` / `STOP https` / `STOP tools` — STOP, сообщить владельцу.

## 3. Тесты и логика (от владельца, без sudo)

```bash
cd "$TARGET" && QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest -p no:cacheprovider \
  tests/test_panel.py -k subscription 2>&1 | tail -1
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest -p no:cacheprovider \
  tests/test_managed.py tests/test_gui_listing.py tests/test_gui_qt.py 2>&1 | tail -1; cd ~/xgw
python3 -I "$H" logic; echo "logic_rc=$?"
```

Ожидаются две строки `N passed` без failed и error (числа записать). Затем `OK hide_written`,
`OK hidden_skipped`, `OK config_untouched`, `OK hide_idempotent`, `OK name_stays_taken`,
`OK restore_written`, `OK restored`, `OK logic`, `helper_rc=0`, `logic_rc=0`. Падение или
`STOP <имя>` — записать имя теста или шага, установку не делать (PARTIAL).

## 4. Согласие на установку

Спросить владельца: «Разрешаете установить e18f53e (убрать и вернуть подписку из config.toml:
семь файлов из шага 1) поверх 1568790 штатным установщиком? Если on/HTTPS не подтвердятся за
45 с, помощник сам вернёт 1568790 (начнёт не позже 60 с) и проверит связь». Дождаться явного
ответа, время записать приватно. Нет ответа или отказ — INSTALL_NOT_RUN, перейти к шагу 8.

## 5. Установка с возвратом

```bash
sudo sh -c 'nohup setsid python3 -I "$1" deploy "$2" </dev/null >>/run/xgw-subremove-deploy.log 2>&1 &' sh "$H" "$PREV"; echo started
sudo sh -c 'for i in $(seq 60); do grep -q "^helper_rc=" /run/xgw-subremove-deploy.log && break; sleep 5; done; cat /run/xgw-subremove-deploy.log'
```

Вторую команду можно повторять, в том числе после обрыва связи; установку второй раз не
запускать. Норма: `OK baseline`, `install_rc=0 at=…`, `OK on`, `OK https`, `OK installed`,
`helper_rc=0`. Записать `at`. Иначе:
- `STOP baseline` — установка не начиналась: PARTIAL;
- `recovery_started_at=…`, `rollback_rc=…`, `rollback_verified=true` — возврат прошёл:
  записать времена, перейти к шагу 8 (PARTIAL);
- `rollback_verified=false` — сразу владельцу, ничего не чинить;
- нет `helper_rc=` за 5 минут — только читать журнал, сообщить владельцу.

## 6. Кнопки без изменений (окно и панель)

От владельца: `xgw gui &`. Машина открывает раздел «Подписки». Ожидается: у подписки с меткой
«из config.toml» есть кнопка «Убрать», а «Изменить» нет; раздела «Убранные подписки из
config.toml» нет (при hidden 0). Владелец мышью нажимает «Убрать». В окне подтверждения
должна быть фраза «Запись в config.toml останется», а при `live_allowed=yes` ещё
«единственная подписка». Владелец нажимает **«Отмена»**.

В браузерной панели, раздел «Подписки»: у подписки «из config.toml» есть значок корзины.
Владелец нажимает на него, проверяет те же фразы и нажимает **«Отмена»**. Затем:

```bash
sudo python3 -I "$H" sources
```

Ожидаются те же числа, что в шаге 2, и те же config_sha и panel_sha: сравнить приватно, в
отчёт — «совпали: да/нет». Записать по каждому пункту да/нет. Если не совпало — STOP, сообщить
владельцу.

## 7. Убрать и вернуть (только при live_allowed=yes и с отдельного согласия)

При `live_allowed=no` (подписок больше одной или есть ссылки) этот шаг не выполняется:
удаление сменило бы серверы и могло бы снять ручной выбор. Записать NOT_RUN live и перейти
к шагу 8. При `yes` спросить владельца: «Разрешаете убрать единственную подписку кнопкой и
сразу вернуть её? Ядро без подписок остаётся на прежних серверах, ручной выбор не снимается.
Вернуть — не позже чем через 2 минуты». Нет согласия — NOT_RUN live.

1. Владелец мышью: «Убрать» → «Убрать». Через 30 с:
   `sudo python3 -I "$H" sources; sudo python3 -I "$H" health`. Ожидаются `config_subs: 0`,
   `hidden: 1`, config_sha тот же, panel_sha другой, `OK on`, `OK https`. В окне подписка
   появилась в разделе «Убранные подписки из config.toml» с кнопкой «Вернуть» (да/нет).
2. Сразу после этого владелец мышью нажимает «Вернуть». Ждать до 3 минут, пока карточка
   подписки снова не покажет «обновлена …» и число серверов больше 0. Затем те же две
   команды. Ожидаются числа шага 2, `hidden: 0`, config_sha тот же, `OK on`, `OK https`;
   раздела убранных нет; ручной выбор тот же, что в шаге 2 (да/нет).
3. Если «Вернуть» не сработало за 3 минуты или упали on/HTTPS — сразу владельцу, ничего не
   чинить. В журнале за окно шага: `sudo journalctl -u xgw --since "-10 min" -o cat |
   grep -c "убрана из панели"` и то же для `"возвращена из панели"` (ожидается по 1).

## 8. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; пул и ручной выбор те же, что в шаге 2.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-sub-remove-ДАТА.md` в freepool, одна страница,
без пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`,
затем `git pull --rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; семь файлов (да/нет):
Подготовка: helper_rc; on/HTTPS; diag до (OK/WARN/FAIL); sources (числа); live_allowed:
Тесты: две строки N passed; logic_rc и все OK:
Согласие (время) или INSTALL_NOT_RUN; deploy helper_rc; install_rc и at; возврат или «не нужен»:
Окно: «Убрать» есть / «Изменить» нет / фразы подтверждения / Отмена ничего не изменила:
Панель: корзина есть / фразы / Отмена ничего не изменила; sources и суммы совпали:
Убрать и вернуть: NOT_RUN (почему) или числа после «Убрать» и после «Вернуть», on/HTTPS,
  время до «обновлена», ручной выбор тот же, строки журнала:
Конечное: on/HTTPS, diag после, пул и ручной выбор без изменений (да/нет):
Итог: PASS / PARTIAL / FAIL / INSTALL_NOT_RUN; первый непройденный шаг; что стоит на машине:
```
