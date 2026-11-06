# Постоянные SNI и short_id REALITY, вторая проверка: группы одной точки входа

На машине по отчёту 84b1d42 установлен 0492448. Новый код 701412aaa9bbc261d4d2e8caefb01a629fed89e6.

Отчёт reality-pin — PARTIAL: прежние пары держались у 12–14 серверов за обновление, но за 2 часа
было 4 смены поколения sing-box с полями tls.reality.*. Мимо закрепления проходили группы —
несколько записей подписки на одну точку входа (адрес, порт, ключ) и публичный ключ REALITY.
Прежний код их не трогал, а подписка меняет SNI и short_id и у них. Для REALITY такая группа —
один сервер. Теперь группа держит набор пар целиком: каждая запись получает пару своего места из
прошлого опроса, если число записей то же. Места определяются прочими полями и именем, а не
порядком в подписке.

В журнале строки:

- «REALITY: у N серверов … оставлены прежние (до суток; в группах одной точки входа — M)»;
- «REALITY: свежие SNI и short_id у N серверов …» — срок вышел, сервер мёртв или в группе
  другое число записей.

Критерии:

- установка и health rc0;
- `reality` rc0, `groups` > 0;
- после двух обновлений кнопкой второе даёт `held_max` > 0 и `grouped_max` > 0, смены поколения
  с полями tls.reality.* нет;
- через 2 часа смен с tls.reality.* нет, допустима одна, если в той же строке есть `renewed`;
- участники и запасные — как до установки (±1–2);
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
CODE=701412aaa9bbc261d4d2e8caefb01a629fed89e6
BASE=04924485a9f61bf22051df40c91b76659c4b6632
TARGET="$HOME/xgw-rpin2-$CODE"
PREV="$HOME/xgw-prev-$BASE"
git worktree add --detach "$TARGET" "$CODE"
test -d "$PREV" || git worktree add --detach "$PREV" "$BASE"
HELPER="$PWD/docs/helpers/reality_pin_check.py"
printf '%s  %s\n' '611afc41dd20f1f2030f9616444853a9abdbad59a79cb9c08e07becd3b4d7586' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" servers
sudo python3 -I "$HELPER" generations
sudo python3 -I "$HELPER" reality
```

Ожидаются: чистый клон, сумма OK, точные CODE и BASE, `{"health": true}`. Строки `generations` и
`reality` до установки записать: в `reality` должно быть `groups` 0, у прежнего кода групп нет.
Сверить установленный пакет с PREV функцией `match_package` из ТЗ t01-xhttp (раздел 1). Если
стоит другая версия, нет рабочего on или сумма либо код расходятся — только чтение, сообщить
владельцу. Записать `sudo xgw diag --no-net` (числа OK/WARN/FAIL).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE, на два обновления подписок кнопкой и на
условный возврат штатным установщиком BASE, если установка или on/HTTPS откажут. Нет согласия —
INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-rpin2
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
sudo cat /run/xgw-rpin2/install.rc /run/xgw-rpin2/health.rc
```

Ожидаются 0 и 0. Если связь потерялась — проверить сохранённые rc, установку заново не
начинать. При возврате снять health и закончить с PARTIAL. Логи установки приватны.

## 3. Группы и два обновления подписок

Через 5 минут после установки:

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" refresh; printf 'refresh1 rc=%s\n' "$?"
sudo python3 -I "$HELPER" reality; printf 'reality rc=%s\n' "$?"
sudo python3 -I "$HELPER" refresh; printf 'refresh2 rc=%s\n' "$?"
```

Каждый `refresh` занимает до 14 минут. Ожидаются:

- оба `refresh` rc0, `refreshed` true;
- `reality` rc0: `groups` > 0, `grouped_entries` — сколько записей в группах;
- во втором `refresh` `held_max` > 0 и `grouped_max` > 0, в `switch_fields` нет tls.reality.* и
  tls.server_name.

В первом `refresh` смена с полями REALITY ещё возможна: группы записываются в нём впервые.
Смена из-за других частей (servers, dns_hosts) — не дефект: записать части и `switch_servers`.
Если во втором `refresh` смена с полями REALITY всё же есть, сделать третий `refresh` и записать
все три JSON.

## 4. Серверы через 30 минут

```sh
sudo python3 -I "$HELPER" servers
```

Сравнить с шагом 1: `members_alive` и `spares_usable` не меньше, с допуском ±1–2. Заметно
меньше — записать оба среза и `sudo xgw status` (только числа и вердикты).

## 5. Через 2 часа

```sh
sudo python3 -I "$HELPER" generations; printf 'generations rc=%s\n' "$?"
sudo python3 -I "$HELPER" reality
sudo python3 -I "$HELPER" servers
```

Ожидаются:

- `hours_since_start` ≥ 2, `refreshes` ≥ 2;
- `held_times` ≥ 1;
- в `switch_fields` нет tls.reality.*, допустима одна смена, если `renewed` не пуст (свежие пары
  мёртвого сервера через 6 часов или по сроку);
- `switches` сравнить с шагом 1 и с отчётом reality-pin: 4 смены за 2 часа, все с полями
  REALITY.

Прежние пары, записанные 06.11 утром, выходят через сутки после записи. Если 2 часа приходятся на
это время, одна смена с `renewed` ожидаема. Затем `sudo xgw diag --no-net` — сравнить с шагом 1.
Режим пула, ручной выбор и связь — как до установки.

## 6. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
generations и reality до установки: <JSON>
refresh1 / reality / refresh2 (и refresh3, если был): <JSON>, rc:
servers до / через 30 мин / через 2 ч:
generations через N часов: <JSON>; reality: <JSON>
diag до/после (OK/WARN/FAIL); пул/pin/настройки/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-reality-pin-r2-ДАТА.md. В freepool добавить, проверить
`git diff --cached --name-only` и `--check`, закоммитить и отправить только этот отчёт (перед
push — `git pull --rebase`, если ветка ушла вперёд).
