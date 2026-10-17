# Программа испытаний XGW 0.1.11 на реальной машине

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Все выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§8).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, Docker, роутер HUAWEI AX2 за шлюзом. Стоит XGW
**0.1.10** в боевом режиме: от него работает интернет всего дома.

Цели:

1. Собрать сведения о двух дефектах прошлого отчёта (шаги 2–3) — до обновления.
2. Узнать, работает ли Happ с безлимитными серверами conn-liberty **через домашний
   интернет** (шаг 4) — вместе с заказчиком.
3. Поставить 0.1.11 (шаг 5).
4. Проверить новое: дробление ClientHello (шаги 6–7), BBR (шаг 8), серверы с allowInsecure
   (шаг 9), строку «Журнал» (шаг 10).

## 0. Запрещено

- `xgw net down`, `xgw uninstall`, `reboot`, `install.sh --force` — **никогда**.
- `flush ruleset`, ручные команды `nft`, `ip`, `iptables`, `sysctl -w` — **никогда**.
- Открывать или скачивать адреса подписок (curl, браузер), копировать ссылки серверов.
- Править код XGW.
- Коммитить что-либо, кроме отчёта (§8). Файлы из `~/xgw-0.1.11-test` в Git **не класть**.
- Писать в отчёт: адреса подписок, UUID, пароли, ключи, токены, IP и домены серверов.
  Серверы называй по имени или тегу (`spare-nl-1a2b`).

Аварийный выход, если пропал интернет: `sudo xgw disable` (интернет пойдёт напрямую), затем
сообщить заказчику.

**Остановись и спроси заказчика** перед шагами 4, 6 и 7 — там это написано отдельно.

## 1. Подготовка

Шаг 1.1. Каталог для результатов:

```bash
mkdir -p ~/xgw-0.1.11-test/before ~/xgw-0.1.11-test/after && chmod 700 ~/xgw-0.1.11-test && cd ~/xgw-0.1.11-test && date
```

Ожидается: печатается дата. Дальше все команды выполняй из этого каталога.

Шаг 1.2. Снимок состояния:

```bash
sudo xgw --version; sudo xgw status > before/status.txt; sudo xgw servers > before/servers.txt; sudo xgw diag > before/diag.txt; tail -1 before/diag.txt
```

Ожидается: `xgw 0.1.10` и строка «Итог: OK — …, WARN — …, FAIL — 0».
Если не так (другая версия или FAIL не 0): записать в отчёт и спросить заказчика, продолжать ли.

## 2. Дефект D1 прошлого отчёта: уровень записей демона в журнале (только чтение)

Шаг 2.1. Сведения о службе:

```bash
{ systemctl --version | head -1
  systemctl show xgw -p MainPID -p ExecMainStartTimestamp
  pid=$(systemctl show xgw -p MainPID --value)
  echo "--- JOURNAL_STREAM"; sudo cat /proc/$pid/environ | tr '\0' '\n' | grep -E '^JOURNAL_STREAM='
  echo "--- stderr и stdout (устройство:inode)"; sudo stat -L -c 'stderr %d:%i' /proc/$pid/fd/2; sudo stat -L -c 'stdout %d:%i' /proc/$pid/fd/1
  sudo ls -l /proc/$pid/fd/1 /proc/$pid/fd/2
  echo "--- юнит"; systemctl cat xgw | grep -vE '^\s*#' | grep -v '^$'
  echo "--- код"; head -3 /usr/local/bin/xgw; grep -c journal_stream /opt/xgw/lib/xgw/log.py
  echo "--- уровни (PRIORITY, есть ли WARNING в тексте) → сколько"
  sudo journalctl -u xgw -n 300 -o json --no-pager | python3 -c 'import sys, json, collections; print(collections.Counter((d.get("PRIORITY"), " WARNING " in d.get("MESSAGE", "")) for d in map(json.loads, sys.stdin) if d.get("_TRANSPORT") == "stdout"))'
} > before/d1.txt 2>&1; cat before/d1.txt
```

Ожидается: значение после `JOURNAL_STREAM=` совпадает с числами в строке `stderr`; число
после `grep -c journal_stream` — не 0. В последней строке пары `('4', True)` — так выглядит
исправная запись, пары `('6', True)` — дефект.
Если не так: ничего не делать, просто сохранить файл — он и нужен разработчику.

## 3. Дефект D2 прошлого отчёта: «уровень приоритета «высокий»» (только чтение)

Шаг 3.1:

```bash
{ sudo python3 -c 'import json; print("priority в panel.json:", json.load(open("/etc/xgw/panel.json")).get("priority"))'
  sudo xgw status --json | python3 -c 'import sys, json; s = json.load(sys.stdin); print("tier:", s.get("tier")); print([(m["tag"], m.get("priority")) for m in s["members"] + s["spares"]])'
  sudo xgw servers | head -2
  echo "--- panel.json изменён:"; sudo stat -c '%y' /etc/xgw/panel.json
  systemctl show xgw -p ExecMainStartTimestamp
} > before/d2.txt 2>&1; cat before/d2.txt
```

Ожидается: если `priority` пуст (`{}` или `None`), то во второй строке у всех серверов
`'medium'`, а в строке «Участники балансировщика» нет слов «уровень приоритета».
Если не так: это воспроизведение дефекта — сохранить файл, в отчёте отметить «D2
воспроизведён».

## 4. Happ через домашний интернет (вместе с заказчиком)

**Остановись и спроси заказчика**, готов ли он сейчас взять телефон. Если нет — пропусти шаг
4, в отчёте напиши «пропущен: заказчик не готов».

Зачем: телефон в домашнем Wi-Fi ходит через шлюз XGW, и Happ проверял бы не домашнего
провайдера, а туннель XGW. Поэтому телефон временно пускают мимо VPN.

Шаг 4.1. Передай заказчику текст и дождись ответа на каждый пункт:

> 1. Откройте панель XGW → раздел «Устройства» → у вашего телефона нажмите переключатель VPN
>    → «Пустить мимо VPN». Скажите, когда метка станет «мимо VPN».
> 2. В телефоне, оставаясь в домашнем Wi-Fi, откройте Happ и по очереди подключитесь к 2–3
>    безлимитным серверам conn-liberty. Для каждого скажите: имя сервера, подключился ли,
>    открывается ли сайт (например, ya.ru), что Happ пишет о протоколе сервера (например,
>    «VLESS Reality»).
> 3. Сколько всего серверов conn-liberty показывает Happ?
> 4. Отключите Happ. В панели XGW снова включите переключатель VPN у телефона (метка «через
>    VPN»). Проверьте, что сайт на телефоне открывается.

Записывай время каждого пункта (`date +%T`).

Шаг 4.2. Что видит XGW:

```bash
sudo xgw servers > before/servers-xgw.txt; grep -ci 'liberty' before/servers-xgw.txt
```

Шаг 4.3. Вывод — выбери **одну** строку таблицы и перенеси в отчёт:

| Что ответил заказчик | Вывод |
|---|---|
| Happ в домашнем интернете **не подключается** к conn-liberty | (а) серверы блокирует домашний провайдер |
| Happ **подключается**, но серверов или протоколов в Happ не столько, сколько в `xgw servers` | (б) подписка отдаёт XGW другие серверы |
| Happ **подключается**, состав тот же | (в) дело в XGW или в дроблении — смотрим шаги 6–7 |

## 5. Установка 0.1.11

Шаг 5.1:

```bash
cd ~/xgw && git pull && git log -1 --format=%H && grep __version__ src/xgw/__init__.py && cd ~/xgw-0.1.11-test
```

(Если код лежит в другом каталоге — перейди в него вместо `~/xgw`.)
Ожидается: `__version__ = "0.1.11"`. Записать хеш.

Шаг 5.2. Прежний алгоритм TCP (нужен для шага 8):

```bash
cat /proc/sys/net/ipv4/tcp_congestion_control | tee before/tcp-cc.txt
```

Шаг 5.3. Установка (из каталога кода):

```bash
cd ~/xgw && date +%T | tee ~/xgw-0.1.11-test/install-time.txt && sudo sh packaging/install.sh --yes; echo "код $?"; cd ~/xgw-0.1.11-test
```

Ожидается: «код 0». Время из `install-time.txt` — «время установки» в шагах ниже.
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику.

Шаг 5.4:

```bash
systemctl is-active xgw-net xgw-xray xgw xgw-dhcp; xgw --version; sudo xgw diag > after/diag.txt; tail -1 after/diag.txt
```

Ожидается: четыре строки `active`, `xgw 0.1.11`, «FAIL — 0».

В командах ниже вместо `T` подставляй время установки так:

```bash
T=$(cat ~/xgw-0.1.11-test/install-time.txt); echo $T
```

## 6. Дробление ClientHello в режиме auto

**Спроси заказчика:** «Включить безлимитные серверы conn-liberty в панели на время проверки?
Через них трафик не пойдёт, пока они не отвечают: шлюз будет их только проверять». Если да —
заказчик включает их в панели сам (раздел «Серверы», переключатель у каждого). Записать ответ.

Шаг 6.1. Запустить проверку запасных:

```bash
J=~/xgw-0.1.11-test/panel.jar
curl -s -o /dev/null -c $J "http://127.0.0.1:8781/?token=$(sudo cat /var/lib/xgw/panel-token)"
curl -s -b $J -H 'X-XGW-Panel: 1' -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8781/api/scan; echo; date +%T
```

Ожидается: ответ с `"ok": true` и текстом «Проверяю запасные серверы…». Если `"ok": false` —
записать текст ответа и повторить через минуту. Затем подожди 5 минут (`sleep 300`).

Шаг 6.2. Собрать результаты:

```bash
T=$(cat ~/xgw-0.1.11-test/install-time.txt)
sudo xgw servers > after/servers-auto.txt; echo "с дроблением: $(grep -c 'дробление' after/servers-auto.txt)"
sudo journalctl -u xgw --since "$T" --no-pager -o cat | grep -E 'fragment:|дробление ClientHello' > after/fragment-events.txt; wc -l after/fragment-events.txt
sudo journalctl -u xgw --since "$T" --no-pager -o cat | grep -E ' скан ' | awk '{print $6, $7}' | sort | uniq -c > after/scans.txt; cat after/scans.txt
systemctl show xgw-xray -p ExecMainStartTimestamp
```

Ожидается:
- в `fragment-events.txt` строки вида «fragment: «имя» отвечает только с дроблением
  ClientHello — оно включено» или «… не отвечает и с дроблением ClientHello — оно выключено»;
- строки «apply: дробление ClientHello (…): применено через API без перезапуска»;
- время запуска `xgw-xray` — **раньше** этих событий (Xray не перезапускался);
- уведомлений на рабочий стол и в Telegram о дроблении нет.

Если событий `fragment:` нет совсем: это не ошибка, если все запасные отвечают и без
дробления (в `scans.txt` только `OK`/`SLOW`). Записать.

Шаг 6.3. В отчёт — таблица: имя сервера, подписка, вердикт без дробления, вердикт с
дроблением (из `fragment-events.txt` и `scans.txt`).

## 7. Без дробления и с ним — все серверы сразу

**Предупреди заказчика:** «10 минут соединения будут устанавливаться чуть дольше, интернет
будет». Дождись согласия.

Шаг 7.1. Резервная копия конфига и проверка, что секции `[fragment]` ещё нет:

```bash
sudo cp /etc/xgw/config.toml ~/xgw-0.1.11-test/config.toml.bak && sudo chmod 600 ~/xgw-0.1.11-test/config.toml.bak && sudo grep -c '^\[fragment\]' /etc/xgw/config.toml
```

Ожидается: `0`. Если `1` или больше — **стоп**, шаг 7 пропустить, записать «секция уже есть».

Шаг 7.2. Режим always:

```bash
printf '\n[fragment]\nmode = "always"\n' | sudo tee -a /etc/xgw/config.toml >/dev/null && sleep 40 && sudo xgw servers | grep -c 'дробление'
```

Ожидается: число больше 0 (у всех серверов с TLS и REALITY).
Если 0: подождать ещё 40 с и повторить последнюю команду; если снова 0 — шаг 7.6
(восстановить) и записать.

Шаг 7.3:

```bash
sudo xgw probe --all > after/probe-always.txt; cat after/probe-always.txt
```

Шаг 7.4. Режим off:

```bash
sudo sed -i 's/^mode = "always"$/mode = "off"/' /etc/xgw/config.toml && sleep 40 && sudo xgw servers | grep -c 'дробление'
```

Ожидается: `0`.

Шаг 7.5:

```bash
sudo xgw probe --all > after/probe-off.txt; cat after/probe-off.txt
```

Шаг 7.6. Вернуть конфиг как было:

```bash
sudo install -m 600 -o root -g root ~/xgw-0.1.11-test/config.toml.bak /etc/xgw/config.toml && sudo grep -c '^\[fragment\]' /etc/xgw/config.toml; date +%T
```

Ожидается: `0`.

Шаг 7.7. В отчёт — таблица по серверам: вердикт `off` (из `probe-off.txt`) и `always` (из
`probe-always.txt`). Вывод одной фразой:
- есть серверы с вердиктом `OK` только при `always` → «дробление помогает у этого
  провайдера» и список таких серверов;
- таких нет → «дробление этому провайдеру не помогает».

## 8. TCP BBR

Шаг 8.1:

```bash
cat /proc/sys/net/ipv4/tcp_congestion_control; sudo python3 -c 'import json; print(json.load(open("/var/lib/xgw/capture.json")).get("tcp_congestion_before"))'
```

Ожидается: первая строка `bbr`; вторая — то, что записано в `before/tcp-cc.txt` (или `None`,
если там уже было `bbr`).

## 9. Серверы с allowInsecure

Шаг 9.1:

```bash
T=$(cat ~/xgw-0.1.11-test/install-time.txt)
echo "allowInsecure: $(sudo journalctl -u xgw --since "$T" --no-pager -o cat | grep -c 'allowInsecure не поддерживается')"
echo "отброшены Xray: $(sudo journalctl -u xgw --since "$T" --no-pager -o cat | grep -c 'Xray не принимает его конфиг')"
```

Записать оба числа. Ожидается: второе — `0`.

## 10. Строка «Журнал» и уровни записей

Шаг 10.1:

```bash
sudo xgw diag | grep -A1 'Журнал' | tee after/diag-journal.txt
```

Ожидается: «OK    Журнал: предупреждения демона — с уровнем warning …».
Если WARN: выполнить шаг 2.1 ещё раз, заменив в нём `before/d1.txt` на `after/d1.txt`.

Шаг 10.2:

```bash
T=$(cat ~/xgw-0.1.11-test/install-time.txt); sudo journalctl -u xgw --since "$T" -p warning --no-pager | head -20
```

Ожидается: хотя бы одна строка (например, предупреждения при запуске). Пусто — записать «D1
не исправлен».

## 11. Итоговое состояние

Шаг 11.1:

```bash
systemctl is-active xgw-net xgw-xray xgw xgw-dhcp; sudo grep -c '^\[fragment\]' /etc/xgw/config.toml; sudo xgw diag | tail -1; sudo xgw status | head -5
```

Ожидается: четыре `active`, `0`, «FAIL — 0». Телефон заказчика — «через VPN» (шаг 4.1,
п. 4). Серверы conn-liberty — как решил заказчик в шаге 6 (записать).

## 12. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.11-<ГГГГ-ММ-ДД>.md` в репозитории. Заполни бланк:

```markdown
# Отчёт об испытаниях XGW 0.1.11 на реальной машине

Код: <хеш>. Установка: <время>, код <0/…>.

## Итог
<3–5 предложений: что работает, что нет, вывод по conn-liberty>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 2 D1 до обновления | сведения собраны | <совпал ли JOURNAL_STREAM; пары PRIORITY> |
| 3 D2 | воспроизведён / нет | |
| 4 Happ дома | (а) / (б) / (в) / пропущен | |
| 5 установка | пройден / нет | |
| 6 дробление auto | | <сколько серверов получили дробление> |
| 7 off и always | помогает / не помогает | |
| 8 BBR | пройден / нет | |
| 9 allowInsecure | | <два числа> |
| 10 Журнал | OK / WARN | |

## Шаг 2 (D1) — вывод before/d1.txt
<вставить целиком>

## Шаг 3 (D2) — вывод before/d2.txt
<вставить целиком>

## Шаг 4 — Happ в домашнем интернете
| Сервер | Подключился | Сайт открылся | Протокол в Happ |
|---|---|---|---|
Серверов conn-liberty в Happ: <N>, в XGW: <M>. Вывод: <строка из таблицы шага 4.3>.

## Шаги 6–7 — дробление
| Сервер | Подписка | off | always | auto: событие |
|---|---|---|---|---|
Вывод: <фраза из шага 7.7>.

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Что не проверено и почему

## Итоговое состояние машины
```

Перед коммитом проверь, что в отчёте нет секретов:

```bash
grep -nE 'vless://|vmess://|trojan://|ss://|[0-9a-f]{8}-[0-9a-f]{4}-|token|/sub/' docs/TEST-REPORT-REAL-MACHINE-0.1.11-*.md
```

Ожидается: пусто. Если что-то нашлось — убрать из отчёта.

Коммит только отчёта: `git add docs/TEST-REPORT-REAL-MACHINE-0.1.11-*.md && git commit -m
"Отчёт об испытаниях XGW 0.1.11 на реальной машине" && git push`.
