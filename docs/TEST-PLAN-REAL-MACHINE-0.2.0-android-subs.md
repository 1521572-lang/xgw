# ThinkCentre и телефон: экран подписок приложения XGW

Исполнитель — GLM-5.3-Flash. Код CODE (ASSUMPTIONS п. 346) меняет только приложение: на вкладке
«Подписки» кнопка «Убрать» есть и у подписки из config.toml, убранные подписки показаны с кнопкой
«Вернуть». Причина «Не обновилась: …» в приложении уже была и берётся у шлюза.
Сборка 8 приносит и правки экрана серверов из 0.1.18 (иконка замера скорости, заметки об обходе).

**На шлюз ничего не ставится**, код шлюза в этом пакете не менялся. Ставится только APK на телефон,
подключённый к ThinkCentre по USB или отладке по Wi-Fi. Настоящее «Убрать» здесь не нажимается: у
шлюза две подписки, и удаление сменило бы серверы. Само действие уже проверено в панели (отчёт
sub-remove); приложение вызывает то же действие шлюза.

Нельзя: нажимать на телефоне что-либо, кроме команд помощника; подписки, пул, ручной выбор, настройки,
WAN, LAN, Tailscale, сетевые правила; перезапуск демона; удалять приложение с телефона. В отчёт —
только числа и признаки: без имён подписок и серверов, адресов, модели и номера телефона, сумм файлов
и снимков экрана.

## 1. Код и суммы

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=bcce313f7551ee59cb892358c89f9b801aab6e75
BASE=1c89d0f190e840c3879eb9eeef3d06ce78392929
D=$(mktemp -d "$HOME/xgw-andsubs.XXXXXXXX")
TARGET="$D/new"; H="$TARGET/docs/helpers/android_subs_check.py"; APK="$TARGET/android/apk/XGW-android-8.apk"
git worktree add --detach "$TARGET" "$CODE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n%s  %s\n' '56bf9b793a469571cccbd7a774f45a6ac786a7ce0404c78f82c44a70e45d10c2' "$H" 'f57c7813ac34e9748aae17ea04a89146d2a7eb22599204c656460a667674c594' "$APK" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging; echo "конец списка"
```

Ожидается `OK` на обе строки; между командой и `конец списка` — пусто (шлюз не меняется). Иначе —
STOP, сообщить владельцу. Путь D — приватно.

## 2. Шлюз до проверки и телефон

```bash
sudo python3 -I "$H" health; python3 -I "$H" devices; which adb
```

Ожидаются `OK on`, `OK https`, `INFO state=… subscriptions=N` (N записать), `INFO devices=1`, `OK
one_phone`. `STOP one_phone` или нет adb — попросить владельца подключить телефон с включённой
отладкой (adb не ставить); нет ответа за 15 минут — отчёт NOT_RUN. `STOP on` / `STOP https` — сразу
владельцу.

## 3. Согласие на установку APK

Спросить владельца: «Разрешаете обновить приложение XGW на телефоне до сборки 8? Шлюз не меняется,
привязка телефона сохранится». Нет ответа или отказ — INSTALL_NOT_RUN, перейти к шагу 6.

## 4. Установка

```bash
python3 -I "$H" install "$APK"
```

Ожидаются `OK apk_installed`, `INFO version_code=8`, `OK version_code`, `helper_rc=0`. `STOP
apk_installed` (в том числе из-за другой подписи) — приложение **не удалять**, сообщить владельцу:
удаление стёрло бы привязку телефона.

## 5. Экран подписок

Экран телефона должен быть разблокирован. Если приложение просит привязку или показывает ошибку
связи — записать и сообщить владельцу, не привязывать заново.

```bash
python3 -I "$H" subs N; python3 -I "$H" dialog; python3 -I "$H" crash
```

Вместо N — число из шага 2. Ожидаются:
- `OK app_open`, `INFO remove_buttons=N edit_buttons=… restore_buttons=…`, `OK
  remove_on_every_subscription`, `helper_rc=0`;
- для каждой подписки `OK dialog_opened`, `OK cancel_found`, `OK dialog_closed`, затем `INFO
  dialogs=N config_note=…`, `OK dialogs_checked`, `helper_rc=0`;
- `INFO crash_lines=0`, `OK no_crash`, `helper_rc=0`.

`config_note` — сколько подписок вписано в config.toml; `edit_buttons` — сколько добавлено в панели:
вместе они дают N. `restore_buttons` — обычно 0: это число убранных подписок на экране. Любой другой
`STOP` — FAIL, записать шаг, не чинить. Если помощник случайно открыл не тот экран — кнопку «Убрать»
в диалоге не нажимать.

Затем сверить, что шлюз не изменился: число подписок то же.

## 6. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health
```

Норма: `OK on`, `OK https`, то же `subscriptions=N`.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-android-subs-ДАТА.md` в freepool, полстраницы, без пути
D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; суммы OK; код шлюза не менялся (да/нет):
Шлюз до: on/HTTPS, state, N; телефон подключён (да/нет):
Согласие (время приватно) или INSTALL_NOT_RUN; version_code:
Экран: remove_buttons, edit_buttons, restore_buttons; dialogs, config_note; crash_lines; первый STOP:
Конечное: on/HTTPS, N то же (да/нет):
Границы: настоящее «Убрать» и «Вернуть» на телефоне не нажимались:
Итог: PASS / FAIL / NOT_RUN / PARTIAL / INSTALL_NOT_RUN; какая сборка стоит на телефоне:
```
