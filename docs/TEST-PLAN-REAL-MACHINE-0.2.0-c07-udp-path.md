# C07. Одно правило пути UDP/TCP

На машине по отчёту 28231fa установлен 87942c2 (T01/T02). Новый код f10250b44ac9a7f3331ff4e8aae606259d2dc35d: демон решает,
идёт ли сервер по UDP, одним правилом в двух местах — при выборе запасного «по другому пути»
во время массового отказа и перед прямой TCP-проверкой адреса сервера. UDP — протоколы
hysteria, hysteria2, TUIC, WireGuard, а у Xray ещё транспорт mKCP, QUIC и XHTTP по HTTP/3.
Раньше выбор запасного смотрел только на протокол, и VLESS по mKCP или XHTTP-h3 считался TCP.
Бесплатный пул не менялся: там транспорт входит в ключ сервера.

Критерии: установка и health rc0; по кэшу подписок (без сети) установленный код не находит
сервера, который прямая TCP-проверка считает TCP, а путь — UDP (`inconsistent` 0); числа
UDP по новому и прежнему правилу записаны; diag без новых FAIL. Ожидаемо на этой машине
`udp_by_transport` пуст или мал: по разведке mKCP в подписках нет, hysteria и hysteria2 и так
были UDP. Тогда поведение не меняется — это не дефект.

Разрешены терминал, чтение status/diag/logs. Пути, sudo и ожидание адаптировать по месту.
WAN, LAN, Tailscale, подписки, пул, pin, профили и настройки не менять. В отчёте — только числа
и обезличенные признаки, без имён, тегов, адресов, доменов и конфигов.

## 1. Код, предыдущая копия и помощник

```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=f10250b44ac9a7f3331ff4e8aae606259d2dc35d
BASE=87942c2266ffe49f87d7575b51c46f87fbbb01e9
TARGET="$HOME/xgw-c07-$CODE"
PREV="$HOME/xgw-t01-$BASE"
git worktree add --detach "$TARGET" "$CODE"
HELPER="$PWD/docs/helpers/udp_path_check.py"
printf '%s  %s\n' 'ae5fd423ef3edbbf6390f24d7e754644ae01f8b996cff75552737ee38b033722' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
```

Ожидаются чистый клон, сумма OK, точные CODE/BASE, {"health": true} и rc0. Если PREV нет —
`git worktree add --detach "$PREV" "$BASE"`. Сверить установленный пакет с PREV функцией
`match_package` из ТЗ t01-xhttp (раздел 1). Другая версия, нет рабочего on или сумма/код
расходятся — только чтение и сообщить владельцу. Записать итог `sudo xgw diag --no-net`
(только числа OK/WARN/FAIL).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE и условный возврат штатным установщиком
BASE, если установка или on/HTTPS откажут. Нет согласия — INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-c07
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
sudo cat /run/xgw-c07/install.rc /run/xgw-c07/health.rc
```

Ожидается 0 и 0. После потери связи — проверить сохранённые rc, установку заново не начинать.
При откате снять health и закончить с PARTIAL. Логи установки приватны.

## 3. После установки

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" paths; printf 'paths rc=%s\n' "$?"
```

Ожидаются «Пакет совпадает», {"health": true} и `paths` rc0: `inconsistent` 0, `servers` > 0,
`bodies_failed` 0. Записать строку `paths` целиком: `udp_old` — UDP по прежнему правилу,
`udp_new` — по новому, `udp_by_transport` — какие транспорты добавились. Затем
`sudo xgw diag --no-net` — числа сравнить с шагом 1. Режим пула, ручной выбор и связь — как
до установки. Массовый отказ не имитировать: порядок запасных проверен узкими тестами.

## 4. Один отчёт, максимум полстраницы

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
paths: <JSON>, rc:
diag до/после (OK/WARN/FAIL); пул/pin/настройки/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-c07-udp-path-ДАТА.md. В freepool добавить, проверить
git diff --cached --name-only и --check, закоммитить и отправить только этот отчёт.
