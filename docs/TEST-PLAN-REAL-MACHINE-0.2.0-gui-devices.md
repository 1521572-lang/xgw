# ThinkCentre. Раздел «Устройства» в окне XGW

Исполнитель GLM-5.3-Flash. Этап 4 из GUI-NATIVE и HANDOVER. База машины по отчётам ef11633 и
f0930c3: HEALTHY, capture on, Xray active, sing-box inactive. Меняется только код окна.

Машинное зрение на шлюзе по окну не кликает. Раздел открывает владелец. Проверка живого окна
только просмотром: маршруты, WAN, LAN, Tailscale, пул, ручной выбор и записи трафика не менять.
Настройку маршрутов проверять на демо-панели с выдуманными данными.

## 1. Сверка и тесты

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=5779e97e97ab3edde1af1663ef6f8560ba3403d8
BASE=fbd4c28c2b1fd60f4f01d640f8a979c5d184824c
umask 077
D=$(mktemp -d "$HOME/xgw-gui-devices.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
H="$D/new/docs/helpers/gui_devices_check.py"
printf '%s  %s\n' 'b82b2cd467fc6132e5f53d1f9dba17aa9c484566097175f7eebae25d9f2d38eb' "$H" | sha256sum -c -
(cd "$D/new" && QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest \
 -o addopts= -p no:cacheprovider -q tests/test_gui_listing.py tests/test_gui_model.py tests/test_gui_qt.py)
sudo python3 -I "$H" before --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"
```

Нужны baseline_ok, diag без FAIL и тесты без новых падений. Пропуск Qt — NOT_RUN qt,
ничего не устанавливать ради тестов. Состояние и PID ядер сверяет помощник.

## 2. Замена файлов окна

Получить согласие владельца на замену файлов. Установленный пакет: `/opt/xgw/lib/xgw/gui`.
Сверить listing.py и window.py с BASE, devices.py должен отсутствовать. При расхождении STOP.
Сохранить два файла с правами и владельцами в D. Владелец закрывает открытое окно.
Заменить listing.py и window.py из CODE, добавить devices.py с правами и владельцем window.py.
Проверить синтаксис трёх файлов. Запустить `xgw gui` от владельца. Службы не перезапускать.
При ошибке закрыть окно, вернуть два сохранённых файла и удалить только добавленный devices.py.

## 3. Просмотр и отчёт

Владелец открывает «Устройства» и сверяет карточки с браузерной панелью. Нужны имя, адрес,
маршрут и доступность управления. Если есть фиксированное исключение, кнопка недоступна и
видно пояснение. Без локальной сети показано объяснение. Записи пакетов открываются в браузере.
В светлой и тёмной теме карточки читаемы в окне 1024×720. Если владелец недоступен —
NOT_RUN просмотр. Для нажатий, меняющих маршруты, достаточно Qt-теста на демо-панели.

```bash
sudo python3 -I "$H" after --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"
```

Нужны gui_devices_ok, HEALTHY и отсутствие новых FAIL. При ошибке сверки STOP и сообщить владельцу.
Один отчёт `docs/TEST-REPORT-REAL-MACHINE-0.2.0-gui-devices-ДАТА.md`: CODE/BASE, сумма,
тесты, согласие, исходные и конечные числа diag, число карточек, доступность управления,
тема и размер, вывод помощника, PASS/PARTIAL/NOT_RUN. В отчёт только метки и числа, без
имён, адресов, тегов, путей, снимков окна и содержимого настроек.
