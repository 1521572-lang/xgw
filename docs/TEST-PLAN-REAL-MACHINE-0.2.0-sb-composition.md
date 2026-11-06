# Откуда смены состава sing-box и возврат пар пропавших записей

На машине по отчёту 3865615 установлен b6617d2. Новый код 96508c2d939974e1237b3c693a08de87a8343345.

Отчёт reality-pin-r3 — PASS: смены поколения из-за SNI и short_id почти ушли (1 за 2 часа вместо
4). Но за 2 часа осталось 4 смены с частями servers и route — менялся состав серверов sing-box.
В sing-box попадают участники и запасные из подписок и серверы бесплатного пула, так что
источников смены три. Журнал раньше не говорил, какой из них. Теперь при каждой смене
поколения пишется строка:

«состав sing-box: +A −R (подписка: новые +n, снова отобраны +s, пропали −g, не отобраны −d;
пул +p −q; сменили набор вариантов v)»

- новые — отпечатка не было в списке подписок прошлой смены;
- снова отобраны — был в списке, но sing-box его не вёл;
- пропали — отпечатка нет в списке подписок;
- не отобраны — в списке есть, но шлюз его не взял (мёртв, домен не разрешился, фильтры).

Кроме того, записи групп REALITY пропадали и возвращались (80 → 76 → 80), и вернувшаяся получала
свежую пару, новый отпечаток и проверки заново. Теперь пара пропавшей записи помнится сутки и
возвращается ей. В журнале строка «REALITY: записей групп пропало N, вернулось с прежней парой M».

Критерии:

- установка и health rc0;
- `reality` rc0;
- через 3 часа у каждой смены с частью servers есть строка состава: `composition_lines` не
  меньше числа таких смен;
- `group_flaps` записан; если `vanished` > 0, то и `returned` > 0;
- `renewed` — единицы, смен с полями tls.reality.* не больше одной;
- участники и пригодные запасные — как до установки (±1–2);
- diag без новых FAIL; пул, ручной выбор и связь не изменились.

Источник смен состава — не критерий: это данные для разработчика. Записать числа как есть.

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
CODE=96508c2d939974e1237b3c693a08de87a8343345
BASE=b6617d233bb316b46df83d3e7a6022d3d700bfde
TARGET="$HOME/xgw-sbcomp-$CODE"
PREV="$HOME/xgw-prev-$BASE"
git worktree add --detach "$TARGET" "$CODE"
test -d "$PREV" || git worktree add --detach "$PREV" "$BASE"
HELPER="$PWD/docs/helpers/reality_pin_check.py"
printf '%s  %s\n' '5ad49426baee3c94f4cc000d2c1cd744f4dc64b22a9150e689d7aeceffc8a4e4' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" servers
sudo python3 -I "$HELPER" generations
```

Ожидаются: чистый клон, сумма OK, точные CODE и BASE, `{"health": true}`. Строку `generations`
до установки записать: `composition_lines` 0 — у прежнего кода строки состава нет. Сверить
установленный пакет с PREV функцией `match_package` из ТЗ t01-xhttp (раздел 1). Если стоит
другая версия, нет рабочего on или сумма либо код расходятся — только чтение, сообщить
владельцу. Записать `sudo xgw diag --no-net` (числа OK/WARN/FAIL).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE, на два обновления подписок кнопкой и на
условный возврат штатным установщиком BASE, если установка или on/HTTPS откажут. Нет согласия —
INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-sbcomp
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
sudo cat /run/xgw-sbcomp/install.rc /run/xgw-sbcomp/health.rc
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
`composition`, `group_flaps`, `renewed`, `switch_fields`.

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
```

Ожидаются:

- `hours_since_start` ≥ 3, `refreshes` ≥ 3;
- `composition_lines` не меньше числа смен, где в `switch_parts` есть servers;
- `group_flaps.returned` > 0, если `vanished` > 0;
- `renewed` — единицы;
- в `switch_fields` поля tls.reality.* — не больше одной смены.

Записать `composition` целиком: по нему видно, откуда смены состава — подписка (новые, снова
отобраны, пропали, не отобраны), пул или варианты. Затем `sudo xgw diag --no-net` — сравнить с
шагом 1. Режим пула, ручной выбор и связь — как до установки.

## 6. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
generations до установки: <JSON>
refresh1 / refresh2 / reality: <JSON>, rc:
servers до / через 30 мин / через 3 ч:
generations через N часов: <JSON>
diag до/после (OK/WARN/FAIL); пул/pin/настройки/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-sb-composition-ДАТА.md. В freepool добавить, проверить
`git diff --cached --name-only` и `--check`, закоммитить и отправить только этот отчёт (перед
push — `git pull --rebase`, если ветка ушла вперёд).
