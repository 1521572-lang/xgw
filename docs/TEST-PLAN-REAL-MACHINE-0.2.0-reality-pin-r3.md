# Постоянные SNI и short_id REALITY, третья проверка: группы с меняющимся числом записей

На машине по отчёту 7825bea установлен 701412a. Новый код b6617d233bb316b46df83d3e7a6022d3d700bfde.

Отчёт reality-pin-r2 — PARTIAL. Группы закреплялись (held_max до 34, grouped_max до 21), но при
каждом опросе 20–23 сервера получали свежие пары (`renewed`). За 2 часа — 4 смены поколения с
полями tls.reality.* по 10–16 серверов. Пригодных запасных через 30 минут было 40 вместо 66:
у серверов со свежими парами менялся отпечаток, и их проверяли заново. Причина: число записей
в группе меняется от опроса к опросу, а прежний код при другом числе записей отдавал свежие
пары всей группе. Теперь каждая запись держит пару своего места (место — прочие поля и имя).
Место, которого раньше не было, берёт свободную прежнюю пару группы: место пропало — его пара
свободна. Свежую пару запись получает, только если свободных не осталось.

В журнале строки:

- «REALITY: у N серверов … оставлены прежние (до суток; в группах одной точки входа — M)»;
- «REALITY: свежие SNI и short_id у N серверов …» — срок вышел, сервер мёртв или новая
  запись в группе без свободной прежней пары.

Критерии:

- установка и health rc0;
- `reality` rc0, `groups` > 0;
- во втором обновлении кнопкой `held_max` > 0, `renewed` — единицы (было 20–23), смены поколения
  с полями tls.reality.* нет;
- через 2 часа смен с tls.reality.* нет, допустима одна, если `renewed` не пуст;
- участники и пригодные запасные — как до установки (±1–2) и на 30-минутном срезе;
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
CODE=b6617d233bb316b46df83d3e7a6022d3d700bfde
BASE=701412aaa9bbc261d4d2e8caefb01a629fed89e6
TARGET="$HOME/xgw-rpin3-$CODE"
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

Ожидаются: чистый клон, сумма OK, точные CODE и BASE, `{"health": true}`. Строки
`generations` и `reality` до установки записать: в `reality` `groups` > 0 — их записал
прежний код. Сверить установленный пакет с PREV функцией `match_package` из ТЗ t01-xhttp
(раздел 1). Если стоит другая версия, нет рабочего on или сумма либо код расходятся — только
чтение, сообщить владельцу. Записать `sudo xgw diag --no-net` (числа OK/WARN/FAIL).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE, на два обновления подписок кнопкой и на
условный возврат штатным установщиком BASE, если установка или on/HTTPS откажут. Нет согласия —
INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-rpin3
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
sudo cat /run/xgw-rpin3/install.rc /run/xgw-rpin3/health.rc
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

Каждый `refresh` занимает до 14 минут. Запускать так, чтобы таймаут инструмента его не
прервал (в r2 первая попытка оборвалась на 10-й минуте). Ожидаются:

- оба `refresh` rc0, `refreshed` true;
- `reality` rc0: `groups` > 0;
- в обоих `refresh` `renewed` — единицы, а не 20–23. Прежние записи групп читаются: места
  запишутся в первом опросе, при этом пары держатся по порядку, как раньше;
- во втором `refresh` `held_max` > 0, в `switch_fields` нет tls.reality.* и tls.server_name.

Смена из-за других частей (servers, dns_hosts, route) — не дефект: записать части и
`switch_servers`. Если во втором `refresh` смена с полями REALITY всё же есть, сделать третий
`refresh` и записать все три JSON.

## 4. Серверы через 30 минут

```sh
sudo python3 -I "$HELPER" servers
```

Сравнить с шагом 1: `members_alive` и `spares_usable` не меньше, с допуском ±1–2 (в r2 —
провал до 40 из 66). Заметно меньше — записать оба среза и `sudo xgw status` (только числа и
вердикты).

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
- `renewed` — единицы в каждом опросе;
- `switches` сравнить с шагом 1 и с отчётом reality-pin-r2: 4 смены за 2 часа с полями
  REALITY.

Прежние пары, записанные 06.11 утром и днём, выходят через сутки после записи. В опросе, где
срок вышел, `renewed` большой и одна смена с полями REALITY ожидаема — один раз; записать время
этого опроса. Затем `sudo xgw diag --no-net` — сравнить с шагом 1.
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

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-reality-pin-r3-ДАТА.md. В freepool добавить, проверить
`git diff --cached --name-only` и `--check`, закоммитить и отправить только этот отчёт (перед
push — `git pull --rebase`, если ветка ушла вперёд).
