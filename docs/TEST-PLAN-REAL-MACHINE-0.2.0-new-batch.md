# Новые серверы подписки — в работу пачкой

На машине по отчёту speed-off установлен 6afe21c. Новый код 132be8116c7db11eb898e078ce1fd5c41d9273b7.

Отчёт group-hold — PASS: пропавших в составе sing-box больше нет (копии), но смен поколения всё
ещё 4 за 1,6 часа. Их вызывают новые серверы подписки: по 1–2 почти в каждом опросе, и каждый —
новое поколение sing-box (прежнее 5 минут доотдаёт соединения, долгие рвутся).

Теперь новый сервер подписки ждёт пачки: входит в работу не чаще раза в 6 часов
(filters.new_hold_hours). Сразу — когда подписка убрала серверы (состав меняется и так), шлюз
не HEALTHY, опрос срочный или подписку обновили кнопкой «Обновить». Пока сервер ждёт, конфиг
его не содержит, а в списке серверов панели он есть. В журнале строки «новых серверов подписки
ждут пачки: N — в работу не позже ЧЧ:ММ…» и «новые серверы подписки в работу: N (причина)».

Критерии:

- установка и health rc0;
- за 4 часа без нажатий «Обновить»: `new_waiting_lines` > 0, если подписка давала новые
  серверы; `new_batches` и `batch_reasons` записаны;
- смен поколения `switches` за 4 часа заметно меньше, чем 10 (темп group-hold: 4 за 1,6 ч);
- `composition_lines` не меньше числа смен, где в `switch_parts` есть servers;
- участники и пригодные запасные — как до установки (±1–2);
- diag без новых FAIL; пул, ручной выбор и связь не изменились.

Разрешены терминал, чтение status/diag/logs и панели. Кнопку «Обновить» и режим `refresh`
помощника в этом ТЗ **не** нажимать: кнопка впускает ждущих сразу. Пути, sudo и ожидание
адаптировать по месту. WAN, LAN, Tailscale, подписки, пул, pin, профили и настройки не менять.
В отчёте — только числа и признаки, без имён, тегов, адресов, доменов, SNI и short_id. Файл
reality.json не выводить и не копировать.

## 1. Код, предыдущая копия и помощник

```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=132be8116c7db11eb898e078ce1fd5c41d9273b7
BASE=6afe21c1a65064bb59c1131332684b340016acde
TARGET="$HOME/xgw-newbatch-$CODE"
PREV="$HOME/xgw-prev-$BASE"
git worktree add --detach "$TARGET" "$CODE"
test -d "$PREV" || git worktree add --detach "$PREV" "$BASE"
HELPER="$PWD/docs/helpers/reality_pin_check.py"
printf '%s  %s\n' '19169ae0ec1cc6cc2e8f90ea9d145fba4044617259eba4030e80977a5f2e26f7' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" servers
sudo python3 -I "$HELPER" generations
```

Ожидаются: чистый клон, сумма OK, точные CODE и BASE, `{"health": true}`. Строку `generations`
до установки записать: `new_waiting_lines` 0 — у прежнего кода пачек нет; `switches` и
`hours_since_start` — для сравнения темпа. Сверить установленный пакет с PREV функцией
`match_package` из ТЗ t01-xhttp (раздел 1). Если стоит другая версия, нет рабочего on или сумма
либо код расходятся — только чтение, сообщить владельцу. Записать `sudo xgw diag --no-net`
(числа OK/WARN/FAIL).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE и на условный возврат штатным установщиком
BASE, если установка или on/HTTPS откажут. Нет согласия — INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-newbatch
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
sudo cat /run/xgw-newbatch/install.rc /run/xgw-newbatch/health.rc
```

Ожидаются 0 и 0. Если связь потерялась — проверить сохранённые rc, установку заново не
начинать. При возврате снять health и закончить с PARTIAL. Логи установки приватны.

## 3. Через 1 час

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" servers
sudo python3 -I "$HELPER" generations; printf 'generations rc=%s\n' "$?"
```

Сравнить `servers` с шагом 1: `members_alive` и `spares_usable` не меньше, с допуском ±1–2.
Записать `new_waiting_lines`, `new_waiting_max`, `new_batches`, `batch_reasons`, `switches`.
Первая пачка после установки входит сразу: демон перезапущен, и первый опрос ждать некому.

## 4. Через 4 часа

Не раньше чем через 4 часа после установки (можно закончить сессию и вернуться):

```sh
sudo python3 -I "$HELPER" generations; printf 'generations rc=%s\n' "$?"
sudo python3 -I "$HELPER" servers
```

Ожидаются:

- `hours_since_start` ≥ 4, `refreshes` ≥ 4;
- `new_waiting_lines` > 0, если подписка давала новые серверы (`composition.new` или
  `new_waiting_max` > 0);
- `switches` заметно меньше 10; записать и `switch_parts`;
- `composition_lines` не меньше числа смен, где в `switch_parts` есть servers;
- `batch_reasons` — записать как есть (hold — срок 6 ч, removed — подписка убрала серверы,
  state — шлюз не HEALTHY, button — срочный опрос или кнопка).

Затем `sudo xgw diag --no-net` — сравнить с шагом 1. Режим пула, ручной выбор и связь — как до
установки. В панели на вкладке серверов посмотреть, что число серверов подписки не меньше, чем
до установки (ждущие видны в списке), — записать числом.

## 5. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
generations до установки: <JSON>
servers до / через 1 ч / через 4 ч:
generations через 1 ч: <JSON>
generations через 4 ч: <JSON>
diag до/после (OK/WARN/FAIL); число серверов в панели до/после; пул/pin/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-new-batch-ДАТА.md. В freepool добавить, проверить
`git diff --cached --name-only` и `--check`, закоммитить и отправить только этот отчёт (перед
push — `git pull --rebase`, если ветка ушла вперёд).
