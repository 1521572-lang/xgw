# Значок «ограниченное подключение» и причины смены поколений sing-box

На машине установлен dcde6b6: первый прогон этого ТЗ (отчёт 7949034, код d05eeb6) откатился
по health сразу после установки. Причина в коде: демон записывал адреса проверки связности
фоном, и до следующего шага сверка считала барьер незагруженным. Теперь файл адресов и
загрузку правил делает основной поток в одном шаге; health после установки ждёт до 90 с.
Новый код c7fc6e446f74f821afa50ccc079b80d838dd7278:

- Значок сети шлюза. NetworkManager проверяет связность HTTP-запросом, привязанным к WAN;
  такой запрос уходит мимо перехвата, и барьер XGW с 02.11 его молча отбрасывал — значок
  писал «ограниченное подключение» при работающем интернете. Теперь демон узнаёт адрес
  проверки у NetworkManager, разрешает его и пишет /run/xgw/conncheck.json, а барьер
  пропускает только root, только TCP на порт проверки и только к этим адресам.
- «Карусель» поколений. Демон записывает каждую смену поколения sing-box и что её вызвало:
  servers (состав серверов), server_settings (параметры серверов), dns_hosts (адреса
  доменов серверов), endpoints, route; rotate — конфиг тот же. `xgw singbox status`
  показывает `switches_24h`, `switch_reasons_24h`, `last_switch_parts`; в журнале демона —
  «поколение sing-box сменено: изменились …». История начинается с установки.

Критерии: установка и health rc0; `conncheck` rc0 — файл адресов есть, правило в барьере
есть, запрос, привязанный к WAN, отвечает кодом 2xx/3xx, `nmcli networking connectivity
check` — full; значок сети шлюза без «ограниченного подключения»; `generations` rc0 в обоих
срезах, числа и причины записаны; diag без новых FAIL; пул, ручной выбор и связь не изменились.
Причины смен — наблюдение для следующего исправления, не критерий приёмки.

Разрешены терминал, чтение status/diag/logs, nmcli в режиме проверки. Пути, sudo и ожидание
адаптировать по месту. WAN, LAN, Tailscale, подписки, пул, pin, профили, настройки и
NetworkManager не менять. В отчёте — только числа и признаки, без имён, тегов, адресов и
доменов.

## 1. Код, предыдущая копия и помощник

```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=c7fc6e446f74f821afa50ccc079b80d838dd7278
BASE=dcde6b645386cdec494064a3788411fb4becff3b
TARGET="$HOME/xgw-ccgen-$CODE"
PREV="$HOME/xgw-g1c06-$BASE"
git worktree add --detach "$TARGET" "$CODE"
HELPER="$PWD/docs/helpers/conncheck_generations_check.py"
printf '%s  %s\n' '27512b737370f302b7e4b5f3fa4319175ea9a107af5f55cb26f7a599ad6d7740' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
nmcli networking connectivity check
```

Ожидаются чистый клон, сумма OK, точные CODE/BASE, {"health": true} и rc0; последняя
команда до установки, вероятно, — limited (записать). Если PREV нет —
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
d=/run/xgw-ccgen2
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
sudo cat /run/xgw-ccgen2/install.rc /run/xgw-ccgen2/health.rc
```

Ожидается 0 и 0. После потери связи — проверить сохранённые rc, установку заново не начинать.
При откате снять health и закончить с PARTIAL. Логи установки приватны.

## 3. Значок связности

Подождать 2 минуты после установки (демон пишет адреса на первом шаге, сверка правил
загружает барьер), затем:

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" conncheck; printf 'conncheck rc=%s\n' "$?"
```

Ожидается rc0: `file` и `guard_rule` true, `ips` > 0, `bound_http` 200–399,
`nm_connectivity` full. Затем посмотреть зрением на значок сети шлюза: нет «ограниченного
подключения» (назвать только состояние). Не full — записать строку целиком; при `file`
false — подождать ещё 5 минут и повторить один раз. `bound_http` 0 при `guard_rule` true —
прямой путь режет не XGW (записать как наблюдение).

## 4. Причины смены поколений

```sh
sudo python3 -I "$HELPER" generations; printf 'generations rc=%s\n' "$?"
```

Записать строку. Затем оставить шлюз в обычной работе не меньше 2 часов (можно закончить
сессию и вернуться) и повторить ту же команду, а также:

```sh
sudo journalctl -u xgw --since "$(systemctl show xgw -p ActiveEnterTimestamp --value)" | grep -c 'поколение sing-box сменено'
sudo journalctl -u xgw --since "$(systemctl show xgw -p ActiveEnterTimestamp --value)" | grep -o 'изменились .*' | sort | uniq -c
```

Записать число смен и строки причин с количеством (в них только слова servers,
server_settings, dns_hosts, endpoints, route или «только порты»). Затем
`sudo xgw diag --no-net` — числа сравнить с шагом 1. Режим пула, ручной выбор и связь —
как до установки.

## 5. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
nmcli до установки; conncheck: <JSON>, rc; значок сети после:
generations сразу: <JSON>; через N часов: <JSON>; журнал: число смен и причины:
diag до/после (OK/WARN/FAIL); пул/pin/настройки/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-conncheck-generations-r2-ДАТА.md. В freepool добавить,
проверить git diff --cached --name-only и --check, закоммитить и отправить только этот отчёт.
