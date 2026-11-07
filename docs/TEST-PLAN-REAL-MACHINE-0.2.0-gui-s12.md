# Окно XGW (xgw gui), этапы 1–2: вход, «Обзор», переключатель VPN

Выполнять после отчёта new-batch: на машине тогда установлен 132be81. Новый код 9ed094fc20d874339ec5f1254d6c3138f300f9da.

Владелец заказал нативное окно управления шлюзом для Ubuntu 24.04 (PyQt6) вместо открытия
браузерной панели. Окно — клиент той же локальной панели на 127.0.0.1: те же /api/state и
действия, никаких своих обращений к Xray, sing-box, nftables и файлам /etc/xgw. Подробно —
docs/GUI-NATIVE.md. В этой поставке готовы этапы 1–2: вход через пароль администратора
(pkexec, одноразовый код панели), «Обзор» (VPN, состояние и что делать, сервер в работе:
скорость, RTT и полная проба отдельно, перехват, версии), переключатель VPN, светлая и тёмная
тема, один экземпляр окна. Остальные разделы пока открывают браузерную панель.

Критерии:

- до установки — дозапись отчёта new-batch (шаг 1): `generations` записан;
- тесты окна на этой машине (offscreen) проходят;
- установка и health rc0;
- окно запускается от владельца (не через sudo), вход — окном пароля Ubuntu, после входа
  «Обзор» показывает то же состояние, что `xgw status`;
- второй запуск выводит открытое окно вперёд, второго процесса нет;
- закрытие окна не трогает службу xgw; повторный запуск входит без пароля;
- файл входа ~/.config/xgw/gui.json — права 600, в журнале XGW нет кода входа;
- `xgw panel --gui-login` от владельца без pkexec отказывает;
- демо-окно (`tests/panel_demo.py --gui`) открывается без root и без изменений сети.

Разрешены терминал, чтение status/diag/logs, запуск окна и демо. WAN, LAN, Tailscale,
подписки, пул, pin и настройки не менять. Кнопку VPN в настоящем окне нажимать только с
отдельного согласия владельца (шаг 5). В отчёте — только числа и признаки, без имён серверов,
адресов, доменов, кода входа и cookie; содержимое gui.json не выводить.

## 1. Код, предыдущая копия, тесты окна

```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=9ed094fc20d874339ec5f1254d6c3138f300f9da
BASE=132be8116c7db11eb898e078ce1fd5c41d9273b7
TARGET="$HOME/xgw-gui-$CODE"
PREV="$HOME/xgw-prev-$BASE"
git worktree add --detach "$TARGET" "$CODE"
test -d "$PREV" || git worktree add --detach "$PREV" "$BASE"
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
lsb_release -ds
python3 -c "import sys, PyQt6.QtCore as c; print(sys.version.split()[0], c.PYQT_VERSION_STR, c.QT_VERSION_STR)"
python3 -m pytest --version
```

Ожидаются: чистый клон, точные CODE и BASE, Ubuntu 24.04, Python 3.12, PyQt6 6.6 и Qt 6.4.
Нет pytest — с согласия владельца `sudo apt install python3-pytest`, иначе шаг тестов
пропустить и записать. Затем тесты от владельца, не от root:

```sh
cd "$TARGET"
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider \
  tests/test_gui_model.py tests/test_gui_qt.py
cd ~/xgw
sudo xgw status --json | python3 -c "import json,sys; print(json.load(sys.stdin).get('state'))"
HELPER="$PWD/docs/helpers/reality_pin_check.py"
printf '%s  %s\n' '19169ae0ec1cc6cc2e8f90ea9d145fba4044617259eba4030e80977a5f2e26f7' "$HELPER" | sha256sum -c -
sudo python3 -I "$HELPER" generations; printf 'generations rc=%s\n' "$?"
```

Ожидается `21 passed`. Записать состояние шлюза и `sudo xgw diag --no-net` (числа
OK/WARN/FAIL).

`generations` — дозапись отчёта new-batch (тот вышел через 0,6 ч, и пачки не нагружались): с
установки 132be81 в 02:43 машина работала без переустановки. Записать `hours_since_start`,
`refreshes`, `switches`, `switch_parts`, `composition`, `new_waiting_lines`, `new_waiting_max`,
`new_batches`, `new_admitted`, `batch_reasons`, `copies_max`. Ожидается при `hours_since_start`
≥ 4: `new_waiting_lines` > 0, если подписка давала новые серверы, и смен поколения заметно меньше
2,5 в час (темп отчёта group-hold). Это только чтение — машину не трогает. Сверить установленный пакет с PREV функцией `match_package` из ТЗ t01-xhttp
(раздел 1). Если стоит другая версия или нет рабочего on — только чтение, сообщить владельцу.

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE и на условный возврат штатным установщиком
BASE, если установка или on/HTTPS откажут. Нет согласия — INSTALL_NOT_RUN. Помощник health —
тот же `$HELPER` из шага 1.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-gui
mkdir -m 700 "$d" || exit 3
sh "$1/packaging/install.sh" --yes >"$d/install.log" 2>&1
i=$?; echo "$i" >"$d/install.rc"
h=3; n=0
while [ "$n" -lt 9 ]; do
    if python3 -I "$3" health >"$d/health.json" 2>&1; then h=0; break; fi
    n=$((n + 1)); sleep 10
done
echo "$h" >"$d/health.rc"
if [ "$i" -ne 0 ] || [ "$h" -ne 0 ]; then
    sh "$2/packaging/install.sh" --yes >"$d/return.log" 2>&1
    echo "$?" >"$d/return.rc"
    python3 -I "$3" health >"$d/return-health.json" 2>&1
    echo "$?" >"$d/return-health.rc"
fi
printf '%s\n' 'Проверьте сохранённые rc'
SH
sudo cat /run/xgw-gui/install.rc /run/xgw-gui/health.rc
match_package "$TARGET"
```

Ожидаются 0 и 0 и совпадение пакета. При возврате снять health и закончить с PARTIAL.

## 3. Отказы без окна

```sh
xgw panel --gui-login; printf 'gui-login rc=%s\n' "$?"
sudo xgw gui; printf 'root gui rc=%s\n' "$?"
```

Ожидаются rc 1 с текстом «…запускает окно XGW через pkexec…» и rc 2 с текстом «…не от root…».

## 4. Окно владельца

В графическом сеансе владельца, от его имени (не sudo), в терминале:

```sh
rm -f ~/.config/xgw/gui.json
xgw gui &
```

Владелец нажимает «Войти» и вводит пароль администратора в окне Ubuntu. Записать: появилось ли
окно пароля, вошло ли окно, что пишет метка состояния вверху (тон и слово, без имён) и совпадает
ли она со словом из `xgw status`; видны ли в «Обзоре» скорость, RTT и «Полная проба» отдельно,
версии XGW/Xray/sing-box, строка «Перехват: …».

```sh
xgw gui; printf 'second rc=%s\n' "$?"
pgrep -u "$USER" -fc 'xgw gui'
stat -c '%a' ~/.config/xgw/gui.json
python3 -c "import json,pathlib; print(sorted(json.loads((pathlib.Path.home()/'.config/xgw/gui.json').read_text())))"
sudo journalctl -u xgw --since "-15min" -o cat --no-pager | grep -c 'login='
```

Ожидаются: второй запуск rc 0 и окно вышло вперёд; процессов `xgw gui` — 1; права 600; ключи
`['cookie', 'port']`; строк с `login=` — 0. Затем владелец переключает тему (Светлая, Тёмная, Как в
системе), проходит разделы слева (у неперенесённых — «Открыть в браузерной панели») и закрывает
окно крестиком.

```sh
systemctl is-active xgw
sudo python3 -I "$HELPER" health
xgw gui &
```

Ожидаются active, health true, и окно открывается сразу во «Обзор» без пароля. Закрыть.

## 5. Кнопка VPN (только с согласием владельца)

Если владелец согласен на кратковременное выключение VPN: в окне «Выключить VPN» → кнопка
показывает «Выключаю…», затем «VPN выключен»; «Включить VPN» → «VPN включён». Сразу после —
`sudo python3 -I "$HELPER" health` (true). Нет согласия — записать NOT_RUN; это действие
проверено тестами на демо-панели.

## 6. Демо без root

```sh
cd "$TARGET"
python3 tests/panel_demo.py --gui --port 8795 --scene trouble
```

Открываются окно и демо-панель на выдуманных данных (сеть не трогается). Записать метку
состояния; в демо можно нажимать кнопку VPN и «Проверить запасные». Остановить Ctrl+C. Так же
`--scene empty` (ожидается «Серверов нет» и пояснение про подписку).

## 7. Один отчёт, максимум страница

```text
Дата, CODE/BASE, Ubuntu/Python/PyQt6/Qt, согласие, исходный и конечный on/HTTPS:
Дозапись new-batch: generations до установки <JSON>:
Тесты окна (passed/failed) / установка / health / совпадение пакета / возврат:
Отказы шага 3 (rc, суть текста):
Окно владельца: окно пароля, вход, метка = xgw status?, метрики, второй запуск, процессов,
права gui.json, ключи, login= в журнале, закрытие → active/health, вход без пароля:
Кнопка VPN: выполнено / NOT_RUN:
Демо trouble / empty:
Замечания владельца по виду (коротко):
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-gui-s12-ДАТА.md. В freepool добавить, проверить
`git diff --cached --name-only` и `--check`, закоммитить и отправить только этот отчёт (перед
push — `git pull --rebase`, если ветка ушла вперёд).
