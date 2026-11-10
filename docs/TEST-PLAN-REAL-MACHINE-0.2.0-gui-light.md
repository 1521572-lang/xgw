# ThinkCentre. Светлая тема Proton в окне XGW

Исполнитель: GLM 5.3 Flash. Установить CODE `92bda2b` поверх принятой базы BASE `98ebeb4` и
провести просмотр владельцем. Меняются только три файла открытого окна: `theme.py`, `window.py`,
`app.py`. Четвёртый файл поставки — хелпер проверки; он запускается из worktree и не установленный
пакет не копируется.

Полный установщик запускать запрещено. Запрещены остановка, перезапуск и изменение `xgw.service`,
Xray и sing-box. VPN, WAN, LAN, Tailscale, подписки, пул, серверы, маршруты и настройки не менять.
Машинное зрение по окну не кликает: окно закрывает, открывает и просматривает владелец. Код,
тесты и хелпер не исправлять. При любом расхождении сохранить вывод, остановиться и сообщить.

## 1. Сверка, тесты и исходное состояние

Выполнять блоки в одной bash-сессии, чтобы сохранить переменную `D`. Репозиторий `~/xgw` должен
быть чистым. CODE обязан находиться на `origin/freepool` и быть потомком BASE; чужую ветку или
совпадающий diff на другом корне не принимать.

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=92bda2bbec92a3b330757668d964b79765b97f37
BASE=98ebeb49c0d0c35478e75a969566ac3fb86efb32
git cat-file -e "$CODE^{commit}"
git cat-file -e "$BASE^{commit}"
git merge-base --is-ancestor "$BASE" "$CODE"
git merge-base --is-ancestor "$CODE" origin/freepool
diff -u <(printf '%s\n' \
  docs/helpers/gui_devices_check.py \
  src/xgw/gui/app.py \
  src/xgw/gui/theme.py \
  src/xgw/gui/window.py) <(git diff --name-only "$BASE" "$CODE")
git diff --check "$BASE" "$CODE"
umask 077
D=$(mktemp -d "$HOME/xgw-gui-light.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
H="$D/new/docs/helpers/gui_devices_check.py"
printf '%s  %s\n' \
  79b38304d93a60f5f730d8409851982e6cca8d35506641f769dd8d1f4809a2c2 \
  "$D/new/src/xgw/gui/theme.py" \
  262224eb9c3b1953c1ec0472958145369d00464aa674a53bcef64524be6bfbe3 \
  "$H" | sha256sum -c -
(cd "$D/new" && ruff check src/xgw/gui/theme.py src/xgw/gui/window.py \
  src/xgw/gui/app.py docs/helpers/gui_devices_check.py)
python3 -m py_compile "$D/new/src/xgw/gui/theme.py" \
  "$D/new/src/xgw/gui/window.py" "$D/new/src/xgw/gui/app.py" "$H"
(cd "$D/new" && QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest \
  -o addopts= -p no:cacheprovider -q \
  tests/test_gui_qt.py tests/test_gui_model.py tests/test_gui_listing.py)
sudo python3 -I "$H" before --section light --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"
```

Ожидаются: точный diff из четырёх файлов, обе суммы OK, Ruff и `py_compile` без ошибок,
`41 passed`, `RESULT baseline_ok`, состояние HEALTHY, capture on и diag без FAIL. Если CODE не
найден после `git fetch origin freepool` или не лежит на `origin/freepool` — STOP, запросить
правильную публикацию, ничего не устанавливать. Нет Qt — NOT_RUN qt, ничего не устанавливать ради
тестов. При другом числе тестов, падении или ошибке импорта — STOP с полным traceback.

До замены дополнительно проверить, что установленные 13 модулей GUI не являются ссылками и
совпадают с BASE. Так исключается замена поверх неизвестной версии и побочные изменения остальных
десяти модулей:

```bash
G=/opt/xgw/lib/xgw/gui
B="$D/base/src/xgw/gui"
N="$D/new/src/xgw/gui"
for f in __init__.py app.py client.py devices.py listing.py login.py model.py \
         operations.py pages.py theme.py traffic.py widgets.py window.py; do
    sudo test -f "$G/$f"
    sudo test ! -L "$G/$f"
    sudo cmp -s "$G/$f" "$B/$f"
done
```

При любом расхождении `cmp` — STOP, файлы не менять. Не выводить содержимое конфигов или состояния.

## 2. Резервная копия и замена файлов

Сначала получить явное согласие владельца на замену трёх файлов. Владелец закрывает `xgw gui`.
Без согласия — NOT_RUN install, ничего не менять. В блоке разрешены только проверка синтаксиса,
резервное копирование и замена; дополнительных команд, особенно управления службами, нет.

```bash
python3 -m py_compile "$N/theme.py" "$N/window.py" "$N/app.py"
mkdir "$D/saved"
sudo cp -a -- "$G/theme.py" "$G/window.py" "$G/app.py" "$D/saved/"
for f in theme.py window.py app.py; do
    ref="$D/saved/$f"
    sudo install -o "$(sudo stat -c %u "$ref")" -g "$(sudo stat -c %g "$ref")" \
        -m "$(sudo stat -c %a "$ref")" -- "$N/$f" "$G/$f"
done
for f in theme.py window.py app.py; do
    sudo cmp -s "$G/$f" "$N/$f"
done
```

Ожидаются три успешных `cmp`, прежние владелец и права каждого файла. Службы не перезапускать.
Владелец запускает окно обычной командой `xgw gui` от своего пользователя, без root.

Если замена или запуск окна не удались, владелец закрывает окно, затем исполнитель возвращает
только эти три файла и повторно сверяет их с BASE:

```bash
for f in theme.py window.py app.py; do
    sudo cp -a -- "$D/saved/$f" "$G/$f"
    sudo cmp -s "$G/$f" "$B/$f"
done
```

После отката записать причину и STOP. Не удалять другие файлы и не перезапускать службы.

## 3. Просмотр владельцем, финальная проверка и отчёт

Владелец только просматривает окно, не нажимая элементы, меняющие состояние шлюза. Проверить
«Обзор», «Серверы» и «Подписки», затем окно размером 1024×720. Семь пунктов приёмки:

1. Белый фон; рейка `#f1f1f4`; выбранный пункт — сиреневая плашка `#ebe6ff`; акцент `#6d4aff`.
2. В порядке щит зелёный `#1ea885` со свечением. Выключенная кнопка VPN пурпурная с белым текстом;
   включённая — контурная, наведение без нажатия даёт красный ховер `#d93757`. Сверху панели
   подключения мягкий градиент состояния к белому к 42 %.
3. Карточки и строки белые, бордер `#e3e2e9`; основной сервер — пурпурный бордер 2 px; пилюли,
   точки и полосы квот читаемы на белом.
4. Поля белые, фокус `#6d4aff`; безопасно открытые владельцем меню/диалоги белые, выделение
   `#ebe6ff`. Ничего не вводить, не сохранять и не подтверждать.
5. Кнопки «Тема» в навигации нет; окно светлое. Если в старом QSettings было `dark`, оно
   игнорируется; настройки ради проверки не менять.
6. В окне 1024×720 текст и значки читаемы, нет обрезания, наложений и элементов за краем.
7. Просмотр не изменил VPN, выбранный сервер, подписки, пул, Tailscale или другие настройки.

Если владелец недоступен — NOT_RUN просмотр и итог PARTIAL, даже если технические проверки прошли.
После просмотра выполнить:

```bash
sudo python3 -I "$H" after --section light --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"
```

Ожидаются `CHECK healthy=1 capture_on=1 daemon_same=1 cores_same=1 settings_same=1 gui_files=3`,
`RESULT gui_light_ok`, HEALTHY, capture on и отсутствие новых FAIL в diag. Если PID, конфиг или
настройки изменились либо хелпер вернул STOP — не исправлять это перезапуском, сохранить вывод,
сообщить владельцу и поставить STOP. Откат на этом этапе только по решению владельца.

Создать один отчёт `docs/TEST-REPORT-REAL-MACHINE-0.2.0-gui-light-ДАТА.md`, заменив `ДАТА` на
фактическую дату `ГГГГ-ММ-ДД`:

```text
Дата; CODE/BASE; согласие владельца:
Состав diff; происхождение CODE; sha256; Ruff; py_compile; pytest:
Исходные 13 cmp; baseline; diag до (только OK/WARN/FAIL):
Резервная копия и замена трёх файлов; владелец/права сохранены; откат (был/не был):
Семь пунктов просмотра (PASS/FAIL/NOT_RUN, коротко):
Хелпер after: CHECK и RESULT; HEALTHY/capture; diag после; новые FAIL:
Первый непройденный шаг; что осталось NOT_RUN; итог PASS/PARTIAL/STOP:
```

`PASS` ставить только при успешной замене, всех семи пунктах просмотра, `gui_light_ok` и неизменном
состоянии шлюза. `PARTIAL` — если замена и проверки прошли, но просмотр не завершён. `STOP` — при
расхождении ворот, ошибке замены/запуска, откате или изменении состояния шлюза.

В отчёте только метки и числа: без токенов, cookie, кодов входа, адресов, доменов, имён серверов,
подписок, путей пользователей, снимков и содержимого конфигов. Снимки в репозиторий не добавлять.
Отчёт не коммитить и не отправлять без отдельного поручения владельца.
