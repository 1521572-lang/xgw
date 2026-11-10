# ThinkCentre. «Диагностика» и «Ещё» в окне XGW

Исполнитель GLM-5.3-Flash. База по отчёту 5e863e7: окно 3e29f1c, HEALTHY, capture on.
Один блок приёмки двух разделов. Меняются три файла окна. Службы XGW и ядер не перезапускать.
Машинное зрение по окну не кликает. Действия в демо-панели идут на выдуманных данных.
Рабочее окно проверяется просмотром. Сеть, подписки, пул, телефоны и настройки Tailscale
не менять. На шлюзе не запускать проверку сети, установку ядра или привязку телефона по этому ТЗ.

## 1. Сверка и тесты

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=5942365f536788673335ca93177a663f52660e04
BASE=3e29f1c92dbb2d030579302849e7fe91a85b56df
umask 077
D=$(mktemp -d "$HOME/xgw-gui-operations.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
H="$D/new/docs/helpers/gui_devices_check.py"
printf '%s  %s\n' 'b3ae963b5da390e1149dcf3f34820e89e2edf96be6b56082a88333877bade6d7' "$H" | sha256sum -c -
(cd "$D/new" && QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest \
 -o addopts= -p no:cacheprovider -q tests/test_gui_listing.py tests/test_gui_model.py tests/test_gui_qt.py)
sudo python3 -I "$H" before --section operations --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"
```

Нужны baseline_ok, diag без FAIL и тесты без новых падений. Новый Qt-тест проверяет ответы
локальной демо-панели, отказ от подтверждения, отправку команды после подтверждения и QR.
Нет Qt — NOT_RUN qt. Дополнительные пакеты не устанавливать.

## 2. Замена файлов окна

Владелец даёт согласие и закрывает окно. Выполнить только блок ниже. При расхождении cmp — STOP.

```bash
G=/opt/xgw/lib/xgw/gui
N="$D/new/src/xgw/gui"
B="$D/base/src/xgw/gui"
sudo test ! -e "$G/operations.py"
sudo test ! -L "$G/operations.py"
for f in listing.py window.py; do
    sudo test ! -L "$G/$f"
    sudo cmp -s "$G/$f" "$B/$f"
done
python3 -m py_compile "$N/listing.py" "$N/operations.py" "$N/window.py"
mkdir "$D/saved"
sudo cp -a -- "$G/listing.py" "$G/window.py" "$D/saved/"
for f in listing.py operations.py window.py; do
    ref="$D/saved/$f"
    if test "$f" = operations.py; then ref="$D/saved/window.py"; fi
    sudo install -o "$(sudo stat -c %u "$ref")" -g "$(sudo stat -c %g "$ref")" \
        -m "$(sudo stat -c %a "$ref")" -- "$N/$f" "$G/$f"
done
```

Окно запускается командой `xgw gui` от владельца. При сбое закрыть его, вернуть два файла из
`$D/saved` через `sudo cp -a` и удалить только добавленный `$G/operations.py`.

## 3. Просмотр и отчёт

Владелец открывает «Диагностику» и проверяет, что есть состояние проверки сети и события.
Открывает «Ещё» и сверяет состояние Tailscale, телефонов и ядер с браузерной панелью.
Если раздел пуст по данным панели, нужна понятная подпись. Проверить читаемость при 1024×720
и переход обратно на «Трафик». Если владелец недоступен — NOT_RUN просмотр.

```bash
sudo python3 -I "$H" after --section operations --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"
```

Нужны gui_operations_ok, HEALTHY и отсутствие новых FAIL. Изменился PID или настройка — STOP.
Один отчёт `docs/TEST-REPORT-REAL-MACHINE-0.2.0-gui-operations-ДАТА.md`: CODE/BASE, сумма,
тесты, согласие, просмотр обоих разделов, переход на «Трафик», diag до/после, вывод помощника,
итог PASS/PARTIAL/STOP. Никаких QR, кодов, адресов, имён, путей, тегов и снимков.
