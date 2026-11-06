# Размер групп REALITY: пропавшая запись держится копией

На машине по отчёту sb-composition (f455265) установлен 96508c2. Новый код 568e38f36ad6a51b8d50b968c9caec68ca5c0a3e.

Отчёт sb-composition: состав sing-box меняет только подписка — за 3 часа новых 12, пропали 17,
пул и варианты не участвуют. Записей в группах одной точки входа пропало 35, вернулось 4:
подписка выдаёт группе то больше записей, то меньше. Все записи группы — один сервер REALITY
(адрес, порт, ключ те же, отличается SNI), и состав менялся от другого числа записей.

Теперь пропавшая запись группы, у которой осталась точка входа, держится копией соседней записи
с прежней парой SNI/short_id — тот же сервер и тот же отпечаток. Новая запись группы сначала
занимает пару пропавшей, и копия уходит. Копия живёт до суток и уходит раньше, если по
проверкам мертва. Группа пропала целиком — копий нет. В журнале строка «REALITY: записей групп
пропало N, вернулось с прежней парой M, держится копиями K».

Критерии:

- установка и health rc0;
- `reality` rc0;
- через 3 часа `copies_max` > 0, если `group_flaps.vanished` > 0;
- `composition`: `new` + `gone` заметно меньше, чем 29 за 3 часа в прошлом отчёте (записать
  как есть; честные появления и пропажи серверов подписки остаются);
- `composition_lines` не меньше числа смен, где в `switch_parts` есть servers;
- участники и пригодные запасные — как до установки (±1–2);
- diag без новых FAIL; пул, ручной выбор и связь не изменились.

Разрешены терминал, чтение status/diag/logs и кнопка «Обновить» (через помощник). Пути, sudo и
ожидание адаптировать по месту. WAN, LAN, Tailscale, подписки, пул, pin, профили и настройки не
менять. В отчёте — только числа и признаки, без имён, тегов, адресов, доменов, SNI и short_id.
Файл reality.json не выводить и не копировать: в нём SNI.

## 1. Код, предыдущая копия и помощник

```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=568e38f36ad6a51b8d50b968c9caec68ca5c0a3e
BASE=96508c2d939974e1237b3c693a08de87a8343345
TARGET="$HOME/xgw-ghold-$CODE"
PREV="$HOME/xgw-prev-$BASE"
git worktree add --detach "$TARGET" "$CODE"
test -d "$PREV" || git worktree add --detach "$PREV" "$BASE"
HELPER="$PWD/docs/helpers/reality_pin_check.py"
printf '%s  %s\n' '073503a02f380f919977fe5c4a2dde1eab17a14f9f5a4fd28907e7be2fdbee62' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" servers
sudo python3 -I "$HELPER" generations
```

Ожидаются: чистый клон, сумма OK, точные CODE и BASE, `{"health": true}`. Строку `generations`
до установки записать: `copies_max` 0 — у прежнего кода копий нет. Сверить установленный пакет
с PREV функцией `match_package` из ТЗ t01-xhttp (раздел 1). Если стоит другая версия, нет
рабочего on или сумма либо код расходятся — только чтение, сообщить владельцу. Записать
`sudo xgw diag --no-net` (числа OK/WARN/FAIL).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE, на два обновления подписок кнопкой и на
условный возврат штатным установщиком BASE, если установка или on/HTTPS откажут. Нет согласия —
INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-ghold
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
sudo cat /run/xgw-ghold/install.rc /run/xgw-ghold/health.rc
```

Ожидаются 0 и 0. Если связь потерялась — проверить сохранённые rc, установку заново не
начинать. При возврате снять health и закончить с PARTIAL. Логи установки приватны.

## 3. Два обновления подписок

Через 5 минут после установки:

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" refresh; printf 'refresh1 rc=%s\n' "$?"
sudo python3 -I "$HELPER" refresh; printf 'refresh2 rc=%s\n' "$?"
sudo python3 -I "$HELPER" reality; printf 'reality rc=%s\n' "$?"
```

Каждый `refresh` занимает до 14 минут. Запускать так, чтобы таймаут инструмента его не прервал.
Если кнопка пришлась на уже идущий опрос (`refreshed` false), повторить один раз. Ожидаются оба
`refresh` rc0 и `refreshed` true, `reality` rc0. Записать оба JSON целиком: `switch_parts`,
`composition`, `group_flaps`, `copies_max`, `renewed`, `switch_fields`. У `reality` записать
`gone_places` и `copies_with_fingerprint`.

Первое обновление после установки копий может не дать: места, пропавшие на прежнем коде,
записаны без вида записи. Копии появляются с мест, пропавших уже на новом коде.

## 4. Серверы через 30 минут

```sh
sudo python3 -I "$HELPER" servers
```

Сравнить с шагом 1: `members_alive` и `spares_usable` не меньше, с допуском ±1–2.

## 5. Через 3 часа

Не раньше чем через 3 часа после установки (можно закончить сессию и вернуться):

```sh
sudo python3 -I "$HELPER" generations; printf 'generations rc=%s\n' "$?"
sudo python3 -I "$HELPER" servers
sudo python3 -I "$HELPER" reality
```

Ожидаются:

- `hours_since_start` ≥ 3, `refreshes` ≥ 3;
- `copies_max` > 0, если `group_flaps.vanished` > 0;
- `composition`: записать целиком, отдельно сумму `new` + `gone` (в прошлом отчёте 29);
- `composition_lines` не меньше числа смен, где в `switch_parts` есть servers;
- число смен поколения `switches` (в прошлом отчёте 6 за 3 часа).

Затем `sudo xgw diag --no-net` — сравнить с шагом 1. Режим пула, ручной выбор и связь — как до
установки. Если `spares_usable` упал больше чем на 2 — записать, есть ли среди запасных с
плохим вердиктом копии: по `reality` число `copies_with_fingerprint`.

## 6. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
generations до установки: <JSON>
refresh1 / refresh2 / reality: <JSON>, rc:
servers до / через 30 мин / через 3 ч:
generations через N часов: <JSON>; new + gone; switches:
reality через 3 ч: <JSON>
diag до/после (OK/WARN/FAIL); пул/pin/настройки/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-group-hold-ДАТА.md. В freepool добавить, проверить
`git diff --cached --name-only` и `--check`, закоммитить и отправить только этот отчёт (перед
push — `git pull --rebase`, если ветка ушла вперёд).
