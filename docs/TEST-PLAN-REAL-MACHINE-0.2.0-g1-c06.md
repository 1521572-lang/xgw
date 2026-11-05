# G1 (открытые вопросы) и C06. Права нового поколения, два моста сразу, журнал проверок

На машине по отчёту 6faa72c установлен f10250b (main 4ad8288 по содержимому тот же). Новый
код dcde6b645386cdec494064a3788411fb4becff3b:

- G1, права при запуске: перед переключением Xray на новое поколение sing-box демон сам
  проверяет его работающий процесс — UID/GID xgw-singbox, все capabilities пусты,
  NoNewPrivileges, образ — бинарник sing-box, тот же процесс до и после чтения. Не так —
  поколение отменяется, прежнее работает дальше. `xgw singbox status` показывает
  `identity_ok`.
- G1, одновременность мостов: проверяется одной штатной сменой поколения (`xgw singbox
  rotate`) при открытом соединении через мост — раньше смены ждали и она не наступала.
- C06: журнал проверок кроме сканов пишет замеры скорости и сквозную проверку (назначения
  scan, speed, e2e); тело скана и сквозной проверки читается не дальше запрошенного Range,
  известного размера адреса или 2 МБ — даже если сервер прислал целый файл; период фонового
  скана запасных растягивается по журналу, если сканы за 24 ч съели больше остатка лимита
  probe.max_daily_probe_mb. Резерв здоровья — срочные сканы, проверки участников ядром и
  сквозная — не ограничивается. Панель и `xgw status`: «Журнал проверок за 24 ч … (сканы …,
  замеры скорости …, сквозная …)».

Критерии: установка и health rc0; `handover` rc0 — смена прошла, старое соединение отвечало
во время и после смены, новое соединение через новый мост ответило, оба моста одновременно
держали соединения, `identity_ok` true; `ledger` rc0 — есть записи e2e, суммы статуса и
SQLite совпадают, тело одной записи кроме замеров скорости не больше 2 МБ; diag без новых
FAIL; пул, ручной выбор и связь не изменились.

Разрешены терминал, чтение status/diag/logs и SQLite в mode=ro. Пути, sudo и ожидание
адаптировать по месту. WAN, LAN, Tailscale, подписки, пул, pin, профили и настройки не менять.
В отчёте — только числа и признаки, без имён, тегов, адресов, доменов и конфигов.

## 1. Код, предыдущая копия и помощник

```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=dcde6b645386cdec494064a3788411fb4becff3b
BASE=f10250b44ac9a7f3331ff4e8aae606259d2dc35d
TARGET="$HOME/xgw-g1c06-$CODE"
PREV="$HOME/xgw-c07-$BASE"
git worktree add --detach "$TARGET" "$CODE"
HELPER="$PWD/docs/helpers/g1_c06_check.py"
printf '%s  %s\n' '28355fa40d1b854ce9c989b8f723d490481a80f28a1fde76f871ea4966bed700' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
```

Ожидаются чистый клон, сумма OK, точные CODE/BASE, {"health": true} и rc0. Если PREV нет —
`git worktree add --detach "$PREV" "$BASE"`. Сверить установленный пакет с PREV функцией
`match_package` из ТЗ t01-xhttp (раздел 1). Другая версия, нет рабочего on или сумма/код
расходятся — только чтение и сообщить владельцу. Записать итог `sudo xgw diag --no-net`
(только числа OK/WARN/FAIL) и `sudo xgw singbox status` (поля active, draining, pending).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE, одну штатную смену поколения sing-box
(соединения через sing-box не рвутся, старый процесс дорабатывает до 5 минут) и условный
возврат штатным установщиком BASE, если установка или on/HTTPS откажут. Нет согласия —
INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-g1c06
mkdir -m 700 "$d" || exit 3
sh "$1/packaging/install.sh" --yes >"$d/install.log" 2>&1
i=$?; echo "$i" >"$d/install.rc"
python3 -I "$3" health >"$d/health.json" 2>&1
h=$?; echo "$h" >"$d/health.rc"
if [ "$i" -ne 0 ] || [ "$h" -ne 0 ]; then
    sh "$2/packaging/install.sh" --yes >"$d/return.log" 2>&1
    echo "$?" >"$d/return.rc"
    python3 -I "$3" health >"$d/return-health.json" 2>&1
    echo "$?" >"$d/return-health.rc"
fi
printf '%s\n' 'Проверьте сохранённые rc'
SH
sudo cat /run/xgw-g1c06/install.rc /run/xgw-g1c06/health.rc
```

Ожидается 0 и 0. После потери связи — проверить сохранённые rc, установку заново не начинать.
При откате снять health и закончить с PARTIAL. Логи установки приватны.

## 3. Смена поколения при открытом соединении

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" handover; printf 'handover rc=%s\n' "$?"
```

Помощник ждёт конца прежнего drain (до 5,5 мин), открывает соединение через первый живой
мост sing-box (probe-inbound Xray, HEAD к probe.url), запускает `xgw singbox rotate` и, пока
она идёт, раз в 10 с спрашивает по тому же соединению. Ожидается rc0 и: `rotate_rc` 0,
`slot_changed` и `old_draining` true, `a_broken_at_s` null, `a_after` и `b_after` — код HTTP
(100–599), `overlap` true, `identity_ok` true, `new_process` — все три признака true.
`NO_SINGBOX_BRIDGE` или `NO_LIVE_SINGBOX_BRIDGE` — через sing-box сейчас нет живого сервера:
записать, это не дефект кода, шаг не повторять. Другой отказ — записать строку целиком, не
повторять больше одного раза и только если сменилось что-то внешнее (сервер был мёртв).
Затем `sudo xgw singbox status` и, через 6 минут, ещё раз: `draining` должен стать null.

## 4. Журнал проверок

Подождать не меньше 15 минут после установки (сквозная проверка идёт каждый шаг демона, сканы и
замеры — по своему расписанию), затем:

```sh
sudo python3 -I "$HELPER" ledger; printf 'ledger rc=%s\n' "$?"
sudo xgw status | grep -A3 'Журнал проверок'
```

Ожидаются rc0: `e2e_seen` true, `status_matches` true, `max_body_within_cap` true; в `sql` —
назначения с попытками, байтами и самым длинным телом. `speed` может отсутствовать, если
замеров ещё не было по расписанию. В панели на карточке «Трафик» строка «Журнал проверок за
24 ч» с разбивкой — назвать только значения. Записи журнала до установки — сканы.

Затем `sudo xgw diag --no-net` — числа сравнить с шагом 1. Режим пула, ручной выбор и связь —
как до установки.

## 5. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
handover: <JSON>, rc; singbox status после и через 6 мин (active/draining/pending):
ledger: <JSON>, rc; строка журнала в панели/CLI:
diag до/после (OK/WARN/FAIL); пул/pin/настройки/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-g1-c06-ДАТА.md. В freepool добавить, проверить
git diff --cached --name-only и --check, закоммитить и отправить только этот отчёт.
