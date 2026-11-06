# Постоянные SNI и short_id REALITY: конец «карусели» поколений sing-box

На машине по отчёту 8625669 установлен 8886fcd. Новый код 04924485a9f61bf22051df40c91b76659c4b6632.

Отчёт tspu-audit показал причину частых смен поколения sing-box: за сутки 18 смен, все
server_settings, поля tls.reality.short_id и tls.server_name у 44 серверов. Подписка при каждом
часовом скачивании выдаёт тем же серверам другие SNI и short_id REALITY. Теперь сервер с теми же
адресом, портом, ключом и публичным ключом REALITY сохраняет прежнюю пару до суток. Свежую пару
он берёт раньше, через 6 часов, если по последнему состоянию шлюза он мёртв. Несколько записей
на одну точку входа (варианты) не трогаются. Пары хранятся в `/var/lib/xgw/reality.json` (0600).
В журнале строка «REALITY: у N серверов подписка сменила SNI или short_id — оставлены прежние».

Критерии:

- установка и health rc0;
- `reality` rc0: файл 0600, записей > 0;
- после двух обновлений кнопкой второе даёт `held_max` > 0, и смены поколения с полями
  tls.reality.* нет;
- через 2 часа смен поколения с полями tls.reality.* нет или единицы (раньше ~2 за 2 часа, все
  с ними);
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
CODE=04924485a9f61bf22051df40c91b76659c4b6632
BASE=8886fcdcaf208e72298d3ca746c2811561d124f1
TARGET="$HOME/xgw-rpin-$CODE"
PREV="$HOME/xgw-prev-$BASE"
git worktree add --detach "$TARGET" "$CODE"
test -d "$PREV" || git worktree add --detach "$PREV" "$BASE"
HELPER="$PWD/docs/helpers/reality_pin_check.py"
printf '%s  %s\n' '53a350223b7b75045eb36c1fb40bafcf29157675a63e67391a97af622ad069d1' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" servers
sudo python3 -I "$HELPER" generations
```

Ожидаются: чистый клон, сумма OK, точные CODE и BASE, `{"health": true}`. `generations` до
установки — записать строку: `switches` и `switch_fields` с tls.reality.* за время работы
службы. Сверить установленный пакет с PREV функцией `match_package` из ТЗ t01-xhttp (раздел 1).
Если стоит другая версия, нет рабочего on или сумма либо код расходятся — только чтение, сообщить
владельцу. Записать `sudo xgw diag --no-net` (числа OK/WARN/FAIL).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE, на два обновления подписок кнопкой и на
условный возврат штатным установщиком BASE, если установка или on/HTTPS откажут. Нет согласия —
INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-rpin
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
sudo cat /run/xgw-rpin/install.rc /run/xgw-rpin/health.rc
```

Ожидаются 0 и 0. Если связь потерялась — проверить сохранённые rc, установку заново не
начинать. При возврате снять health и закончить с PARTIAL. Логи установки приватны.

## 3. Файл пар и два обновления подписок

Через 5 минут после установки (демон уже собрал конфиг):

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" reality; printf 'reality rc=%s\n' "$?"
sudo python3 -I "$HELPER" refresh; printf 'refresh1 rc=%s\n' "$?"
sudo python3 -I "$HELPER" refresh; printf 'refresh2 rc=%s\n' "$?"
sudo python3 -I "$HELPER" reality
```

Каждый `refresh` занимает до 14 минут: опрос, ожидание сборки 4 минуты. Ожидаются:

- `reality` rc0: `mode` 0o600, `records` > 0 — примерно столько серверов REALITY, сколько в
  подписках;
- оба `refresh` rc0 с `refreshed` true;
- во втором `held_max` > 0 (≈20, сколько серверов меняют пару при каждом скачивании) и в
  `switch_fields` нет tls.reality.* и tls.server_name;
- в первом `held_max` тоже, скорее всего, > 0: пары записал первый опрос после установки.

Смена поколения из-за других частей (servers, dns_hosts) — не дефект: записать части.
`held_max` 0 при `refreshed` true — записать оба JSON; подписка в этот раз могла не менять пары.
Тогда через час повторить один `refresh`.

## 4. Серверы через 30 минут

```sh
sudo python3 -I "$HELPER" servers
```

Сравнить с шагом 1: `members_alive` и `spares_usable` не меньше, с допуском ±1–2 на обычную
смену состава. Заметно меньше — записать оба среза и `sudo xgw status` (только числа и
вердикты): это признак, что прежняя пара у части серверов не годится.

## 5. Через 2 часа

Не раньше чем через 2 часа после установки (можно закончить сессию и вернуться):

```sh
sudo python3 -I "$HELPER" generations; printf 'generations rc=%s\n' "$?"
sudo python3 -I "$HELPER" reality
sudo python3 -I "$HELPER" servers
```

Ожидаются:

- `hours_since_start` ≥ 2;
- `refreshes` ≥ 2 (плановые и кнопкой);
- `held_times` ≥ 1;
- `switch_fields` без tls.reality.* или единицы — сравнить с шагом 1 и с отчётом tspu-audit:
  2 смены за 2 часа, обе с ними;
- `switches_24h` скользящий, в нём есть и смены до установки — для сравнения брать `switches`.

Затем `sudo xgw diag --no-net` — сравнить числа с шагом 1. Режим пула, ручной выбор и связь —
как до установки.

## 6. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
generations до установки: <JSON>
reality после установки: <JSON>; refresh1/refresh2: <JSON>, rc:
servers до / через 30 мин / через 2 ч:
generations через N часов: <JSON>; reality: <JSON>
diag до/после (OK/WARN/FAIL); пул/pin/настройки/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-reality-pin-ДАТА.md. В freepool добавить, проверить
`git diff --cached --name-only` и `--check`, закоммитить и отправить только этот отчёт (перед
push — `git pull --rebase`, если ветка ушла вперёд).
