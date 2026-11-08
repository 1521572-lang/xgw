# Телефон: диалоги экрана подписок, повтор

Исполнитель — GLM-5.3-Flash. Повтор шага 5 ТЗ android-subs (отчёт 02114c5): помощник нажимал кнопку
третьей строки, спрятанную под закреплённой панелью вкладок, и попадал во вкладку «События». Теперь он
нажимает только кнопки выше панели, остальные сначала прокручивает, и сверяет число диалогов с числом
подписок. **Приложение, сборка 8 на телефоне и шлюз не меняются, ничего не устанавливается.**

Нельзя: нажимать на телефоне что-либо, кроме команд помощника (настоящее «Убрать» и «Вернуть» не
нажимаются); подписки, пул, ручной выбор, настройки, WAN, LAN, Tailscale, сетевые правила; перезапуск
демона; удалять приложение. В отчёт — только числа и признаки: без имён подписок и серверов, адресов,
модели телефона, сумм файлов и снимков экрана.

## 1. Код и сумма

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=53df8de679e4dbb9ec6b0737e762922821ed4a01
D=$(mktemp -d "$HOME/xgw-andsubs2.XXXXXXXX")
TARGET="$D/new"; H="$TARGET/docs/helpers/android_subs_check.py"
git worktree add --detach "$TARGET" "$CODE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '4be4ddb7b52391d205af9a0d467cb4ceb7652ce645c8521bb652bc83ced1b97f' "$H" | sha256sum -c -
```

Ожидается `OK`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Шлюз и телефон

Телефон подключён, экран разблокирован.

```bash
sudo python3 -I "$H" health; python3 -I "$H" devices; python3 -I "$H" version
```

Ожидаются `OK on`, `OK https`, `INFO state=… subscriptions=N` (N записать), `INFO devices=1`, `OK
one_phone`, `INFO version_code=8`, `OK version_code`. `STOP one_phone` или `STOP app_open` — попросить
владельца подключить и разблокировать телефон; нет ответа за 15 минут — отчёт NOT_RUN. `STOP
version_code` — приложение не обновлять, сообщить владельцу. `STOP on` / `STOP https` — сразу
владельцу.

## 3. Экран и диалоги

Вместо N — число из шага 2.

```bash
python3 -I "$H" subs N; python3 -I "$H" dialog N; python3 -I "$H" crash
```

Ожидаются:
- `OK app_open`, `INFO remove_buttons=N edit_buttons=… restore_buttons=…`, `OK
  remove_on_every_subscription`, `helper_rc=0`;
- N раз `OK dialog_opened`, `OK cancel_found`, `OK dialog_closed`, затем `INFO dialogs=N config_note=…`,
  `OK dialogs_checked`, `helper_rc=0`;
- `INFO crash_lines=0`, `OK no_crash`, `helper_rc=0`.

Сумма `config_note` и `edit_buttons` равна N. Любой `STOP` — FAIL, записать шаг и что открыто на экране
(вкладка), не чинить, кнопку «Убрать» в диалоге не нажимать.

## 4. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health
```

Норма: `OK on`, `OK https`, то же `subscriptions=N`.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-android-subs-r2-ДАТА.md` в freepool, четверть страницы, без
пути D. `git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; шлюз до: on/HTTPS, state, N; version_code:
Экран: remove_buttons, edit_buttons, restore_buttons; dialogs, config_note; crash_lines; первый STOP:
Конечное: on/HTTPS, N то же (да/нет):
Итог: PASS / FAIL / NOT_RUN:
```
