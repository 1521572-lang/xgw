# Аудит противодействия ТСПУ: отпечаток TLS, UA проб, разброс замеров; иконка замера

На машине по отчёту edb5ab0 установлен d94b404. Новый код 8886fcdcaf208e72298d3ca746c2811561d124f1:

- Отпечаток ClientHello: TLS-серверы Xray без `fp` в ссылке получают `fingerprint = chrome`
  (как у sing-box); `fp` из ссылки главнее, REALITY задаёт свой, XHTTP по HTTP/3 не трогается.
- Пробы шлюза берут User-Agent из пула браузерных — один на соединение, а не одну строку
  на все пробы; свой `probe.user_agent` в config.toml главнее.
- Плановый замер скорости каждого сервера — через ×0,8–1,2 от своего срока (постоянно для
  одного замера): серверы, замеренные вместе, расходятся во времени.
- Иконка ручного замера у строки сервера видна всегда (кроме x100) и работает, даже если
  основной сервер или плановые замеры выключены (замечание владельца).
- Смена поколения sing-box записывает изменённые поля серверов (имена без значений):
  `xgw singbox status` — `switch_fields_24h`, `last_switch_fields`.

Критерии: установка и health rc0; после установки ни одного TLS-сервера Xray без отпечатка
(`fingerprint` rc0); живых участников и пригодных запасных через 30 минут не меньше, чем до
установки, с допуском на обычную смену состава (`servers`); ручной замер участника через
API панели прошёл (`icon` rc0); `generations` rc0, поля записаны; diag без новых FAIL; пул,
ручной выбор и связь не изменились.

Разрешены терминал, чтение status/diag/logs. Пути, sudo и ожидание адаптировать по месту.
WAN, LAN, Tailscale, подписки, пул, pin, профили и настройки не менять. В отчёте — только числа
и признаки, без имён, тегов, адресов, доменов и конфигов.

## 1. Код, предыдущая копия и помощник

```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=8886fcdcaf208e72298d3ca746c2811561d124f1
BASE=d94b404d68305c113e084316337769607322dc20
TARGET="$HOME/xgw-tspua-$CODE"
PREV="$HOME/xgw-prev-$BASE"
git worktree add --detach "$TARGET" "$CODE"
test -d "$PREV" || git worktree add --detach "$PREV" "$BASE"
HELPER="$PWD/docs/helpers/tspu_audit_check.py"
printf '%s  %s\n' '4ca91b0f850d202937e9c8ca9a8e314d135d94744978f0216215169fab611aa3' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
sudo python3 -I "$HELPER" fingerprint; printf 'fingerprint rc=%s\n' "$?"
sudo python3 -I "$HELPER" servers
```

Если ветка `freepool` не на CODE и не новее — взять CODE из ветки `anti-tspu-ua`
(`git fetch origin anti-tspu-ua`). Ожидаются чистый клон, сумма OK, точные CODE/BASE,
{"health": true}; `fingerprint` до установки, вероятно, rc3 с `without_fingerprint` > 0 —
записать строку. Сверить установленный пакет с PREV функцией `match_package` из ТЗ
t01-xhttp (раздел 1). Другая версия, нет рабочего on или сумма/код расходятся — только
чтение и сообщить владельцу. Записать `sudo xgw diag --no-net` (числа OK/WARN/FAIL).

## 2. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE, один ручной замер скорости участника
(не больше speed.max_mb, обычно 10 МБ) и условный возврат штатным установщиком BASE, если
установка или on/HTTPS откажут. Нет согласия — INSTALL_NOT_RUN.

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-tspua
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
sudo cat /run/xgw-tspua/install.rc /run/xgw-tspua/health.rc
```

Ожидается 0 и 0. После потери связи — проверить сохранённые rc, установку заново не начинать.
При откате снять health и закончить с PARTIAL. Логи установки приватны.

## 3. Отпечаток и серверы

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" fingerprint; printf 'fingerprint rc=%s\n' "$?"
```

Ожидается rc0: `without_fingerprint` 0, `tls_legs` — как до установки (±обычная смена
состава), в `fingerprints` — chrome и отпечатки из ссылок. Через 30 минут:

```sh
sudo python3 -I "$HELPER" servers
```

Сравнить с шагом 1: `members_alive` и `spares_usable` не меньше, с допуском ±1–2 на обычную
смену. Заметно меньше — записать оба среза и `sudo xgw status` (только числа и вердикты), это
признак, что какой-то сервер не принимает отпечаток chrome.

## 4. Иконка замера

```sh
sudo python3 -I "$HELPER" icon; printf 'icon rc=%s\n' "$?"
```

Ожидается rc0: `icon_rows` > 0, `action_ok` true, `measured` true. Если доступно зрение —
в панели у строк участников и запасных видна иконка ↻ рядом со скоростью (назвать только
наличие). `NO_LIVE_MEMBER` — записать, не дефект кода.

## 5. Причины смен поколения

Не раньше чем через 2 часа после установки (можно закончить сессию и вернуться):

```sh
sudo python3 -I "$HELPER" generations; printf 'generations rc=%s\n' "$?"
sudo journalctl -u xgw --since "$(systemctl show xgw -p ActiveEnterTimestamp --value)" | grep -o 'изменились .*' | sort | uniq -c
```

Записать строку и счётчики причин: в них только слова servers, server_settings, dns_hosts,
endpoints, route, «только порты» и имена полей вроде tls.reality.short_id, servers=N.
Затем `sudo xgw diag --no-net` — числа сравнить с шагом 1. Режим пула, ручной выбор и связь —
как до установки.

## 6. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
fingerprint до/после; servers до/через 30 мин:
icon: <JSON>, rc; иконка в панели (если видно):
generations через N часов: <JSON>; причины и поля из журнала с количеством:
diag до/после (OK/WARN/FAIL); пул/pin/настройки/связь:
Что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-tspu-audit-ДАТА.md. В freepool добавить, проверить
git diff --cached --name-only и --check, закоммитить и отправить только этот отчёт (перед
push — `git pull --rebase`, если ветка ушла вперёд).
