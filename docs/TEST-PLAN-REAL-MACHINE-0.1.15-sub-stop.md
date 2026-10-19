# Программа испытаний XGW на реальной машине: остановка демона посреди опроса подписок (Н1)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§7).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома (LAN `enp4s0`). Стоит XGW **0.1.15** с
исправлением Д1/Д2 (ветка `install-d1d2`). Номер версии не меняется: и после обновления
`xgw --version` пишет `xgw 0.1.15`. Новый код узнаётся по строке «отмена опроса подписок: есть»
(шаги 2.1 и 2.3).

Что нового (ASSUMPTIONS п. 216). В прошлом отчёте (наблюдение Н1) остановка демона, заставшая
запрос подписки, ждала таймаута запроса: 5 с, а в худшем случае — больше 90 с (тогда systemd
убивает демон). Теперь остановка прерывает опрос подписок за доли секунды: на любом ожидании
сети (разрешение имени, соединение, ответ прокси, рукопожатие TLS, заголовки, тело) и в паузе
перед повтором. Прерванный опрос — не сбой подписки: кэш не трогается, в журнале и панели нет
«подписки получить не удалось».

Цели:

1. Поставить новый код (шаг 2).
2. Проверить отмену на установленном коде с местными «молчащими» серверами (шаг 3): сеть дома
   и демон это не затрагивает.
3. Перезапустить демон во время настоящего обновления подписки и измерить остановку (шаг 4).
4. Итоговое состояние (шаг 5), отчёт (§7).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, `install.sh --force` — **никогда**.
- Ручные команды `nft` (кроме `nft list`), `ip` (кроме `ip … show`), `iptables`, `sysctl -w`.
- Останавливать или перезапускать `xgw-xray`, `xgw-singbox`, `xgw-net`, `xgw-dhcp`. Демон `xgw`
  перезапускают **только** команды шага 4.
- Править `/etc/xgw/config.toml` и `/etc/xgw/panel.json`.
- Выбирать сервер вручную, менять приоритеты, нажимать «Замерить скорость» и «Проверить запасные».
- Открывать или скачивать адреса подписок, копировать ссылки серверов.
- Править код XGW. Коммитить что-либо, кроме отчёта (§7). Файлы из `~/xgw-substop-test` в Git
  **не класть**.
- Писать в отчёт: адреса подписок, UUID, пароли, ключи, токены, IP и домены серверов, свой
  внешний IP.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика:** «Обновлю XGW: демон быстрее останавливается, когда обновляет
подписку. (1) При установке демон XGW перезапустится сам: интернет не пропадёт, панель и бот
секунд на десять станут недоступны. (2) Потом я до трёх раз попрошу демон обновить подписку и
сразу перезапущу его — каждый раз панель и бот недоступны пару секунд, интернет не пропадает.
Можно?» Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против пункта 2 — шаг 4 пропустить (в отчёте: «не проводилось — нет согласия»).

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p ~/xgw-substop-test/before ~/xgw-substop-test/after && chmod 700 ~/xgw-substop-test && cd ~/xgw-substop-test && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды выполняй из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без пароля
на время испытаний — вводить пароль некому.

Шаг 1.2. Снимок состояния до обновления:

```bash
sudo xgw --version; sudo xgw status > before/status.txt; sudo xgw diag > before/diag.txt; tail -1 before/diag.txt; grep -E '^Состояние' before/status.txt
```

Ожидается: `xgw 0.1.15`, итог diag с «FAIL — 0», состояние `HEALTHY`.
Если FAIL не 0 или состояние не `HEALTHY`: записать в отчёт как есть и **спросить заказчика**,
продолжать ли.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/xgw && git fetch && git checkout install-d1d2 && git pull --ff-only && git log -1 --format='%h %s' && grep -q 'def wait_connect' src/xgw/fetch.py && echo "отмена опроса подписок: есть"; grep __version__ src/xgw/__init__.py; cd ~/xgw-substop-test
```

Ожидается: «отмена опроса подписок: есть» и `__version__ = "0.1.15"`. Записать хеш.
Если «отмена опроса подписок: есть» не напечатано: **стоп**, сообщить заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/xgw && date '+%F %T' | tee ~/xgw-substop-test/install-time.txt && sudo sh packaging/install.sh --yes 2>&1 | tee ~/xgw-substop-test/after/install.txt | tail -25; echo "код ${PIPESTATUS[0]}"; cd ~/xgw-substop-test
```

Ожидается: «код 0» и строка «демон xgw запущен».
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику.

Шаг 2.3. Установленный код и службы:

```bash
grep -q 'def wait_connect' /opt/xgw/lib/xgw/fetch.py && echo "отмена опроса подписок: есть"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox; python3 --version
```

Ожидается: «отмена опроса подписок: есть», пять строк `active` (у `xgw-singbox` допустимо
`inactive`, если sing-box выключен в настройках — записать), версия Python.
Если строки «отмена…» нет или `xgw` не `active`: **стоп**, сообщить заказчику.

## 3. Отмена на местных «молчащих» серверах

Скрипт запускает код XGW из `/opt/xgw/lib` и поднимает на `127.0.0.1` серверы, которые
принимают соединение и молчат. Сеть дома, Xray и демон он не трогает и в интернет не ходит.
Для каждого случая через 1 с выставляется событие остановки; запрос должен закончиться
`Cancelled` меньше чем за 2 с (таймаут запроса в скрипте — 10 с). Последний случай — контроль
без события: тот же запрос ждёт своего таймаута (2 с) и кончается ошибкой.

Шаг 3.1. Создать скрипт (копируй блок целиком):

```bash
cat > substop.py <<'EOF'
import socket, ssl, subprocess, sys, tempfile, threading, time
sys.path.insert(0, "/opt/xgw/lib")
from xgw import fetch

def silent_tcp(reply=b""):
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(8); keep = []
    def run():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            keep.append(conn)
            try:
                conn.settimeout(0.5); conn.recv(65536)
            except OSError:
                pass
            try:
                conn.sendall(reply)
            except OSError:
                pass
    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]

def full_backlog():
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(0)
    port = srv.getsockname()[1]
    full_backlog.keep = (srv, socket.create_connection(("127.0.0.1", port)))
    return port

def silent_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.bind(("127.0.0.1", 0))
    silent_udp.keep = sock
    return sock.getsockname()[1]

def cancel_after(seconds):
    event = threading.Event(); timer = threading.Timer(seconds, event.set)
    timer.daemon = True; timer.start()
    return event

def case(name, call, cancel=True):
    event = cancel_after(1.0) if cancel else None
    started = time.monotonic()
    try:
        call(event)
        result = "ответ"
    except fetch.Cancelled:
        result = "Cancelled"
    except Exception as exc:
        result = f"ошибка {type(exc).__name__}"
    took = time.monotonic() - started
    if cancel:
        verdict = "ПРОЙДЕН" if result == "Cancelled" and took < 2.0 else "ДЕФЕКТ"
    else:
        verdict = "ПРОЙДЕН" if result.startswith("ошибка") and took >= 1.8 else "ДЕФЕКТ"
    print(f"{name:<34} {result:<22} {took:5.2f} с  {verdict}")
    return verdict

head = b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n" + b"x" * 10
p_proxy, p_headers, p_body, p_tls = silent_tcp(), silent_tcp(), silent_tcp(head), silent_tcp()
p_conn, p_dns = full_backlog(), silent_udp()
retry = silent_tcp(b"HTTP/1.1 503 X\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
verdicts = [
    case("1 прокси молчит на CONNECT", lambda c: fetch.fetch_subscription(
        "http://sub.invalid/s", proxy=("127.0.0.1", p_proxy), timeout=10, cancel=c)),
    case("2 соединение без ответа", lambda c: fetch.fetch_subscription(
        f"http://127.0.0.1:{p_conn}/s", timeout=10, cancel=c)),
    case("3 нет рукопожатия TLS", lambda c: fetch.fetch_subscription(
        f"https://127.0.0.1:{p_tls}/s", timeout=10, cancel=c)),
    case("4 нет заголовков ответа", lambda c: fetch.fetch_subscription(
        f"http://127.0.0.1:{p_headers}/s", timeout=10, cancel=c)),
    case("5 тело остановилось", lambda c: fetch.fetch_subscription(
        f"http://127.0.0.1:{p_body}/s", timeout=10, cancel=c)),
    case("6 пауза перед повтором (503)", lambda c: fetch.fetch_subscription(
        f"http://127.0.0.1:{retry}/s", timeout=10, cancel=c)),
    case("7 DNS не отвечает", lambda c: fetch.fetch_subscription(
        "http://sub.invalid/s", bootstrap=[f"udp://127.0.0.1:{p_dns}"], timeout=10, cancel=c)),
    case("8 контроль: без остановки", lambda c: fetch.fetch_url(
        f"http://127.0.0.1:{p_headers}/s", timeout=2, retries=0), cancel=False),
]
print("ИТОГ:", "ПРОЙДЕН" if all(v == "ПРОЙДЕН" for v in verdicts) else "ДЕФЕКТ")
EOF
echo "скрипт создан"
```

Ожидается: «скрипт создан».

Шаг 3.2. Запуск (около 15 с):

```bash
sudo python3 substop.py 2>&1 | tee after/substop.txt
```

Ожидается: восемь строк, у каждой в конце «ПРОЙДЕН»; у строк 1–7 — `Cancelled` и время около
1,0–1,5 с; у строки 8 — `ошибка FetchError` и время около 2 с; последняя строка
«ИТОГ: ПРОЙДЕН».
Если в какой-то строке «ДЕФЕКТ» или скрипт упал с трассировкой: записать вывод в отчёт как
дефект и **перейти к шагу 4** (повторно не запускать, ничего не исправлять).

## 4. Остановка во время настоящего обновления подписки

Пропусти шаг целиком, если заказчик не согласился с пунктом 2 шага 1.1.

Демон обновляет подписку по запросу из панели. Скрипт шага 4.1 просит обновление, через 0,3 с
перезапускает демон и меряет, сколько длилась остановка. Подписка через Xray обычно приходит за
1–3 с, поэтому перезапуск может попасть и в запрос, и уже после него — оба исхода нормальны;
делается до трёх попыток.

Шаг 4.1. Создать скрипт:

```bash
cat > restart.sh <<'EOF'
#!/bin/bash
# restart.sh N — попытка N: обновить подписку из панели и сразу перезапустить демон.
J=~/xgw-substop-test/panel.jar
curl -s -o /dev/null -c $J "http://127.0.0.1:8781/?token=$(sudo cat /var/lib/xgw/panel-token)"
SINCE=$(date '+%F %T')
curl -s -b $J -X POST -H 'X-XGW-Panel: 1' -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8781/api/refresh; echo
sleep 0.3
T0=$(date +%s.%N); sudo systemctl restart xgw; T1=$(date +%s.%N)
sleep 3
echo "попытка $1: restart занял $(python3 -c "print(f'{$T1 - $T0:.2f}')") с"
sudo journalctl -u xgw --since "$SINCE" -o short-precise --no-pager | grep -E 'Stopping|Stopped|подписк|остановлен|запущен|apply:' | sed -E 's#https?://[^ )]*#(адрес скрыт)#g'
EOF
chmod +x restart.sh; echo "скрипт создан"
```

Ожидается: «скрипт создан».

Шаг 4.2. Попытка 1:

```bash
./restart.sh 1 2>&1 | tee after/restart-1.txt
```

Ожидается:
- ответ панели со словами «Обновляю подписки…»;
- «restart занял» — меньше 3 с;
- в журнале есть `Stopping` и `Started`/«демон XGW запущен»;
- после строки `Stopping` нет строк «подписки получить не удалось» и `apply:`.

Посмотри в журнале попытки строку «опрос подписок прерван: демон останавливается»:
- есть — остановка попала в запрос подписки, это главный случай. Шаги 4.3 и 4.4 **пропустить**;
- нет — перезапуск пришёлся до или после запроса. Подожди 60 с и переходи к шагу 4.3.

Если ответ панели не «Обновляю подписки…» (например, «демон XGW ещё не готов»): подождать 60 с и
повторить эту же попытку один раз; не помогло — записать ответ в отчёт и перейти к шагу 5.
Если «restart занял» 3 с или больше, или после `Stopping` есть «подписки получить не удалось»
или `apply:` — это дефект: записать в отчёт и перейти к шагу 5.

Шаг 4.3. Попытка 2 (только если в попытке 1 не было строки «опрос подписок прерван»):

```bash
./restart.sh 2 2>&1 | tee after/restart-2.txt
```

Ожидается и что делать — как в шаге 4.2. Строка «опрос подписок прерван» есть — шаг 4.4
пропустить; нет — подождать 60 с и перейти к шагу 4.4.

Шаг 4.4. Попытка 3 (только если её не было ни в попытке 1, ни в попытке 2):

```bash
./restart.sh 3 2>&1 | tee after/restart-3.txt
```

Ожидается — как в шаге 4.2. Если строки «опрос подписок прерван» не было ни разу, в отчёте:
«в запрос подписки попасть не удалось за 3 попытки» — это не дефект: шаг 3 проверяет то же на
установленном коде.

## 5. Итоговое состояние

Шаг 5.1. Подожди 2 минуты после последнего перезапуска, затем:

```bash
sudo xgw status > after/status.txt; sudo xgw diag > after/diag.txt; tail -1 after/diag.txt; grep -E '^Состояние' after/status.txt; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c 'подписки получить не удалось'
```

Ожидается: «FAIL — 0», состояние `HEALTHY`, службы `active` (как в шаге 2.3), последнее число —
`0`.
Если число не 0: записать в отчёт строки журнала с этим текстом и временем (адреса скрыть) — и
отметить, были ли они рядом с перезапуском (тогда дефект) или в другое время (тогда наблюдение:
подписка у провайдера не отвечала).

## 6. Если что-то пошло не так

Демон `xgw` не `active` после шага 4 (подожди 30 с и проверь ещё раз):

```bash
sudo systemctl start xgw; sleep 10; systemctl is-active xgw; sudo journalctl -u xgw -n 30 --no-pager | sed -E 's#https?://[^ )]*#(адрес скрыт)#g'
```

Не стал `active` — **стоп**, сообщить заказчику (интернет при этом работает: демон не стоит на
пути трафика). Ничего больше не делать.

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.15-sub-stop-<ГГГГ-ММ-ДД>.md` в репозитории. Заполни бланк:

```markdown
# Отчёт: остановка демона посреди опроса подписок (Н1, ветка install-d1d2)

Код: <хеш>. Установка: <время>, код <0/…>. Python: <версия>. Согласие заказчика: пункты <1–2 / какие нет>.

## Итог
<3–4 предложения: прерывается ли опрос на каждом этапе (шаг 3); сколько длилась остановка
при настоящем обновлении и попала ли она в запрос (шаг 4); есть ли ложные «подписки получить не
удалось»; итоговое состояние>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до обновления | — | <версия, FAIL — …, состояние> |
| 2 установка | пройден / нет | <код, «демон xgw запущен»> |
| 3 местные серверы | пройден / дефект | <ИТОГ; строки с ДЕФЕКТ, если есть> |
| 4 попытка 1 | пройден / дефект / не проводилась | <restart N с; «прерван» есть/нет> |
| 4 попытка 2 | пройден / дефект / не нужна / не проводилась | |
| 4 попытка 3 | пройден / дефект / не нужна / не проводилась | |
| 5 итоговое состояние | пройден / нет | <FAIL — …; число «не удалось»> |

## Шаг 3 — местные серверы
<вывод after/substop.txt целиком>

## Шаг 4 — перезапуск во время обновления
<вывод каждой проведённой попытки целиком>

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние машины
```

Перед коммитом проверь, что в отчёте нет секретов:

```bash
grep -nE '(vless|vmess|trojan|ss|hysteria2)://[^*]|[0-9a-f]{8}-[0-9a-f]{4}-|token|/sub/' ~/xgw/docs/TEST-REPORT-REAL-MACHINE-0.1.15-sub-stop-*.md
```

Ожидается: пусто. Если что-то нашлось — убрать из отчёта.

Коммит только отчёта: `cd ~/xgw && git add docs/TEST-REPORT-REAL-MACHINE-0.1.15-sub-stop-*.md &&
git commit -m "Отчёт: остановка демона посреди опроса подписок (Н1)" && git push`.
