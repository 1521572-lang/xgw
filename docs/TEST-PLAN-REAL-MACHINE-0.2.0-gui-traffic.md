# ThinkCentre. Раздел «Трафик» в окне XGW

Исполнитель GLM-5.3-Flash. База b49cd4b: окно с кодом 5779e97, HEALTHY, capture on.
В этой проверке меняются четыре файла окна. Запуск полного установщика и любые команды
остановки или перезапуска xgw.service, Xray и sing-box запрещены. Окно закрывает владелец.
Машинное зрение по окну не кликает. WAN, LAN, Tailscale, пул, подписки и маршруты не менять.

## 1. Сверка и тесты

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=3e29f1c92dbb2d030579302849e7fe91a85b56df
BASE=5779e97e97ab3edde1af1663ef6f8560ba3403d8
umask 077
D=$(mktemp -d "$HOME/xgw-gui-traffic.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
H="$D/new/docs/helpers/gui_devices_check.py"
printf '%s  %s\n' 'a3c116c9c8f4ec59c2ab2e9875d84debfcef35f5fa4ff6eb6ff3922db6b99b65' "$H" | sha256sum -c -
(cd "$D/new" && QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest \
 -o addopts= -p no:cacheprovider -q tests/test_gui_listing.py tests/test_gui_model.py tests/test_gui_qt.py)
sudo python3 -I "$H" before --section traffic --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"
```

Нужны тесты без новых падений, baseline_ok и diag без FAIL. Нет Qt — NOT_RUN qt.
Отдельный Qt-тест проверяет смену периода во время запроса. Настройки для тестов не менять.

## 2. Замена файлов

Владелец даёт согласие на замену файлов и закрывает xgw gui. При расхождении cmp — STOP.
В блоке только проверка, резервная копия и замена файлов окна. Дополнительных команд нет.

```bash
G=/opt/xgw/lib/xgw/gui
N="$D/new/src/xgw/gui"
B="$D/base/src/xgw/gui"
sudo test ! -e "$G/traffic.py"
sudo test ! -L "$G/traffic.py"
for f in client.py listing.py window.py; do
    sudo test ! -L "$G/$f"
    sudo cmp -s "$G/$f" "$B/$f"
done
python3 -m py_compile "$N/client.py" "$N/listing.py" "$N/traffic.py" "$N/window.py"
mkdir "$D/saved"
sudo cp -a -- "$G/client.py" "$G/listing.py" "$G/window.py" "$D/saved/"
for f in client.py listing.py traffic.py window.py; do
    ref="$D/saved/$f"
    if test "$f" = traffic.py; then ref="$D/saved/window.py"; fi
    sudo install -o "$(sudo stat -c %u "$ref")" -g "$(sudo stat -c %g "$ref")" \
        -m "$(sudo stat -c %a "$ref")" -- "$N/$f" "$G/$f"
done
```

При сбое замены или запуска окна вернуть три файла из `$D/saved` через `sudo cp -a` и удалить
только добавленный `$G/traffic.py`. Запускать окно командой `xgw gui` от владельца.

## 3. Просмотр и отчёт

Владелец открывает «Трафик», проверяет сегодня, 7 и 30 дней и возвращается на сегодня.
Сверить направления и объёмы с браузерной панелью за тот же период. Допустим рост после очередной
записи счётчиков. Если учёт пуст, проверить подпись об отсутствии данных. Если квота доступна,
сверить отдельную подпись «Учтено». Проверить читаемость в окне 1024×720. Без владельца — NOT_RUN
просмотр. Результат сверки сообщать числами строк и метками, без сырых данных.

```bash
sudo python3 -I "$H" after --section traffic --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"
```

Нужны gui_traffic_ok, daemon_same=1, cores_same=1, settings_same=1, HEALTHY и отсутствие новых FAIL.
Если PID или настройки изменились, STOP и сообщить владельцу.
Один отчёт `docs/TEST-REPORT-REAL-MACHINE-0.2.0-gui-traffic-ДАТА.md`: CODE/BASE, сумма,
тесты, согласие, три периода, сверка с панелью, diag до и после, вывод помощника, PASS/PARTIAL/STOP.
Без адресов, имён, путей, снимков и содержимого конфигов.
