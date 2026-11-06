# Замеры скорости при выключенном основном сервере

Выполнять после отчёта group-hold: на машине тогда установлен 568e38f. Новый код 6afe21c1a65064bb59c1131332684b340016acde.

Владелец: скорость серверов в панели не обновлялась с 4.11. Причина: на машине выключен
переключатель «Один основной сервер» (отчёт tspu-audit: `sticky_on: false`), а при нём демон
замерял скорость только по кнопке у сервера. Теперь при выключенном основном плановые замеры
идут, как обычно: серверы в работе — раз в 6 часов, запасные — раз в сутки, x100 — нет. Сервер
по-прежнему выбирает ядро по задержке, основной не закрепляется.

Второе: «нет ни одного живого сервера в бесплатных с GitHub». Это не ошибка: наблюдение пула
выключено, и списки не скачиваются. В этом ТЗ пул только читается — включает его владелец сам,
кнопкой «Включить наблюдение» на вкладке «Бесплатные серверы».

Критерии:

- установка и health rc0;
- переключатель основного сервера после установки — как до неё (не менять);
- через 2 часа при выключенном основном: `measured_6h` не меньше числа живых участников
  и больше, чем до установки; `old_note_rows` 0; `main_set` false;
- участники и связь — как до установки; diag без новых FAIL;
- пул: записать `pool` до и после как есть.

Разрешены терминал, чтение status/diag/logs и панели. Пути, sudo и ожидание адаптировать по
месту. WAN, LAN, Tailscale, подписки, пул, pin, профили, переключатели панели и настройки не
менять. В отчёте — только числа и признаки, без имён, тегов, адресов и доменов.

## 1. Код, предыдущая копия и помощник

```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=6afe21c1a65064bb59c1131332684b340016acde
BASE=568e38f36ad6a51b8d50b968c9caec68ca5c0a3e
TARGET="$HOME/xgw-speedoff-$CODE"
PREV="$HOME/xgw-prev-$BASE"
git worktree add --detach "$TARGET" "$CODE"
test -d "$PREV" || git worktree add --detach "$PREV" "$BASE"
HELPER="$PWD/docs/helpers/speed_off_check.py"
printf '%s  %s\n' '5ff1997c734a6bc49a018e9dc0583057def6401c893cda2c8a504a78388ec836' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" speed
sudo python3 -I "$HELPER" pool
```

Ожидаются: чистый клон, сумма OK, точные CODE и BASE, `{"health": true}`. JSON `speed` и `pool`
до установки записать целиком. При выключенном основном у прежнего кода ожидаются
`sticky_on` false и `old_note_rows` больше 0. Если `sticky_on` true — записать: проверка
изменения тогда неполная (основной включён, замеры шли и раньше), остальное выполнить.
Сверить установленный пакет с PREV функцией `match_package` из ТЗ t01-xhttp (раздел 1). Если
стоит другая версия, нет рабочего on или сумма либо код расходятся — только чтение, сообщить
владельцу. Записать `sudo xgw diag --no-net` (числа OK/WARN/FAIL).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE и на условный возврат штатным установщиком
BASE, если установка или on/HTTPS откажут. Нет согласия — INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-speedoff
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
sudo cat /run/xgw-speedoff/install.rc /run/xgw-speedoff/health.rc
```

Ожидаются 0 и 0. Если связь потерялась — проверить сохранённые rc, установку заново не
начинать. При возврате снять health и закончить с PARTIAL. Логи установки приватны.

## 3. Через 2 часа

Не раньше чем через 2 часа после установки (можно закончить сессию и вернуться):

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" speed; printf 'speed rc=%s\n' "$?"
sudo python3 -I "$HELPER" pool
sudo journalctl -u xgw --since "-2h" -o cat --no-pager | grep -c "замер скорости"
sudo xgw status
```

Ожидаются:

- `sticky_on` — как в шаге 1;
- `measured_6h` не меньше числа живых участников (по `xgw status`) и больше, чем в шаге 1;
- `oldest_hours` меньше, чем в шаге 1, или запасные ещё в очереди (записать как есть);
- `old_note_rows` 0, `main_set` false (при выключенном основном);
- число строк журнала «замер скорости» больше 0.

Затем `sudo xgw diag --no-net` — сравнить с шагом 1. Участники, состояние и связь — как до
установки.

## 4. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
speed до: <JSON>; pool до: <JSON>
speed через 2 ч: <JSON>; pool через 2 ч: <JSON>; строк «замер скорости»:
diag до/после (OK/WARN/FAIL); участники/состояние/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-speed-off-ДАТА.md. В freepool добавить, проверить
`git diff --cached --name-only` и `--check`, закоммитить и отправить только этот отчёт (перед
push — `git pull --rebase`, если ветка ушла вперёд).
