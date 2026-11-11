# ThinkCentre. Управление zapret2 в окне XGW

CODE `15f143fa2273d9fe614890485308f1cf6e13e114`. Сумма помощника сверена по этому коммиту.
Исполнитель GLM-5.3-Flash. Версия 0.2.0. Нужен уже установленный светлый обзор из ТЗ gui-layout
(ae328e8). При другой версии сначала закончить его приёмку, смешанную установку не угадывать.
Обновляются девять файлов окна, панели и демона. Дистрибутив не собирается, nfqws2 не меняется.
Проверяем видимость и управление на локальной демо-панели. На шлюзе zapret2 остаётся off.
Машинное зрение по живому окну не кликает. Владелец только смотрит и открывает форму без сохранения.
Не менять VPN, pin, пул, подписки, WAN/LAN/Tailscale и не запускать сетевые пробы.
Остановить и запустить можно только xgw.service для замены кода после отдельного согласия владельца.
Службы Xray/sing-box не трогать. Ошибка, смена PID ядра или новый FAIL — STOP с объяснением.
Исходный WARN учитывать отдельно. DEGRADED не считать доказательством сбоя этой установки.

## 1. Источник и исходное состояние

Все блоки выполнять в одной bash-сессии. При ошибке остановиться, не чинить службы вне ТЗ.

```bash
set -euo pipefail
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=15f143fa2273d9fe614890485308f1cf6e13e114
BASE=5ff2106f1ed4827f5eded6d339bbae7586164afa
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-gui-zapret2.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
H="$D/new/docs/helpers/gui_zapret2_check.py"
printf '%s  %s\n' 249fcaa1c7f8ed57956aeb55101b6e86f7d9e91ae94b4118eb101e1ac6bbfa55 "$H" | sha256sum -c -
sudo python3 -I "$H" before --state "$D/before.json" --base "$D/base"
sudo xgw diag --no-net >"$D/diag-before"
```

Нужны `OK baseline`, capture on, zapret2 off, активные демон и Xray, отсутствие нового FAIL.
Сумма помощника должна совпасть. sing-box может быть inactive, проверяется сохранение его состояния.
STOP files означает другую установленную базу, не повод переписывать её без разбора.
Локально уже пройдены проверки API, Qt и демона. На машине повторить только новую приёмку API/Qt
с установленными зависимостями, без установки пакетов. Тесты используют выдуманные данные.

```bash
(cd "$D/new" && PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m pytest \
 -p no:cacheprovider -o addopts= -q tests/test_zapret2_panel.py tests/test_gui_qt.py -k zapret2)
```

Ожидаются 6 passed, ни одного skipped. Qt отсутствует — NOT_RUN tools и STOP установки.
Полный набор не запускать. Известное старое падение test_free_pool_card_switches_observation
воспроизведено на BASE разработчиком и не относится к этому изменению.

## 2. Установить после согласия владельца

Получить согласие закрыть окно и кратко остановить только демон для обновления панели.
Владелец закрывает окно. Блок ниже сохраняет семь прежних файлов и ставит два новых.
На ошибке выполняется возврат. Настройки не переписываются.

```bash
sudo bash -s -- "$D" <<'SH'
set -euo pipefail
D=$1
G=/opt/xgw/lib/xgw
N="$D/new/src/xgw"
old=(managed.py config.py zapret2.py daemon.py watch/panel.py gui/window.py gui/widgets.py)
new=(watch/zapret2_control.py gui/zapret2.py)
files=("${old[@]}" "${new[@]}")
for dir in "$G" "$G/watch" "$G/gui"; do test -d "$dir"; test ! -L "$dir"; done
mkdir -p "$D/saved/watch" "$D/saved/gui"
for f in "${old[@]}"; do
    test ! -L "$G/$f"
    cmp -s "$G/$f" "$D/base/src/xgw/$f"
    cp -a -- "$G/$f" "$D/saved/$f"
done
for f in "${new[@]}"; do test ! -e "$G/$f"; test ! -L "$G/$f"; done
python3 - "$N" "${files[@]}" <<'PY'
import ast, pathlib, sys
for name in sys.argv[2:]:
    ast.parse((pathlib.Path(sys.argv[1]) / name).read_text(encoding='utf-8'))
print('OK syntax')
PY
rollback() {
    trap - ERR
    set +e
    systemctl stop xgw.service
    for f in "${old[@]}"; do cp -a -- "$D/saved/$f" "$G/$f"; done
    rm -f -- "$G/watch/zapret2_control.py" "$G/gui/zapret2.py"
    systemctl start xgw.service
    echo 'STOP install_rollback_attempted'
    exit 2
}
trap rollback ERR
systemctl stop xgw.service
for f in "${files[@]}"; do
    ref="$D/saved/$f"
    test -f "$ref" || ref="$D/saved/config.py"
    install -o "$(stat -c %u "$ref")" -g "$(stat -c %g "$ref")" -m "$(stat -c %a "$ref")" "$N/$f" "$G/$f"
done
for f in "${files[@]}"; do cmp -s "$G/$f" "$N/$f"; done
systemctl start xgw.service
trap - ERR
echo 'OK installed files=9'
SH
```

Дождаться свежего статуса, до 90 секунд. Если демон не поднялся, код вернуть блоком раздела 4.
Не запускать повторные рестарты для подбора. При проблеме сначала сохранить её причину приватно.

## 3. Один просмотр владельцем

Запустить `xgw gui` от пользователя в его графическом сеансе и войти штатно.
Владелец проверяет при 1024×720 и развёрнутом окне следующие пункты.

1. Под кнопкой VPN на «Обзоре» виден `zapret2 · Выключен`.
2. Нажатие открывает отдельный раздел, тот же раздел доступен по значку молнии и Ctrl+8.
3. Видны три кнопки режима, выбранный режим, состояние и объяснения недоступных действий.
4. Видны стратегия, список доменов, количество адресов проб, интервалы и суточный бюджет.
5. Открыть «Настроить», проверить поля доменов, стратегии и два скрытых поля адресов, нажать «Отмена».
6. Вернуться на «Обзор». Ни одно действие запуска/сохранения/выключения в этой приёмке не нажимать.

Демо-тест отдельно доказал подтверждение действий, отправку API, скрытый ввод и блокировку при
потере связи. Живой compare/selective и работа против ТСПУ в этом прогоне — NOT_RUN.

```bash
sudo python3 -I "$H" after --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"
```

Нужны `RESULT gui_zapret2_ok`, прежние настройки, capture on, zapret2 off и прежние ядра.
Смена PID демона ожидаема. Смена PID ядра — STOP, причину выяснить по приватному журналу,
не приписывать окну автоматически. Успешный код оставить, окно по желанию владельца оставить открытым.

## 4. Возврат при ошибке установки или окна

После закрытия окна владельцем вернуть только заменённые файлы. Настройки не менялись.

```bash
sudo bash -s -- "$D" <<'SH'
set -euo pipefail
D=$1
G=/opt/xgw/lib/xgw
systemctl stop xgw.service
for f in managed.py config.py zapret2.py daemon.py watch/panel.py gui/window.py gui/widgets.py; do
    cp -a -- "$D/saved/$f" "$G/$f"
done
rm -f -- "$G/watch/zapret2_control.py" "$G/gui/zapret2.py"
systemctl start xgw.service
SH
sudo xgw diag --no-net >"$D/diag-rollback"
```

Сверить прежний код, capture on, zapret2 off, здоровье шлюза и ядра. При неудаче сообщить владельцу.
Не удалять приватные копии до подтверждения результата.

## 5. Отчёт

Одна страница `docs/TEST-REPORT-REAL-MACHINE-0.2.0-gui-zapret2-ДАТА.md`, включая STOP/NOT_RUN.
Указать CODE, BASE, сумму, 6 тестов, согласие, результат установки, пункты просмотра, метки помощника,
диагностику OK/WARN/FAIL до и после, смену PID по ролям без самих PID, возврат при необходимости.
Адреса, домены, имена серверов, секреты, снимки живого окна и сырые журналы в Git не отправлять.
