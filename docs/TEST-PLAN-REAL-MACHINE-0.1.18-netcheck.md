# Проверка XGW: кнопка «Проверить сеть» (Ф3)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы сохраняй в файлы, как написано (`$HOME/xgw-f3/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, KDE Plasma (X11), XGW 0.1.18 из main. Клон —
`~/zcod/xgw`. Код — ветка `netcheck-f3` (версия остаётся 0.1.18).

Что нового (ASSUMPTIONS п. 242). В панели — карточка «Проверка сети» с кнопкой «Проверить
сеть»; в терминале — `sudo xgw diag --netcheck`. Проверки: MTU до основного сервера, UDP
напрямую (STUN), UDP через VPN, утечка DNS, утечка IPv6, чужие правила фаервола. Демон их сам
не запускает — только по кнопке или команде.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list`), `ip`, `iptables`, `tc`, `sysctl -w`.
- Править `/etc/xgw`, `/opt/xgw`, `/var/lib/xgw`, `/etc/systemd`, код XGW. Коммитить что-либо,
  кроме отчёта (§7).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса подписок, IP и домены серверов VPN.
  Имена и теги серверов из вывода проверок — можно, не заменять (адресов там нет).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю новую кнопку „Проверить сеть". По пунктам:
(1) Переустановка XGW с новым кодом: Xray перезапустится — интернет дома пропадёт на несколько
секунд.
(2) Попрошу открыть панель XGW, нажать в карточке „Проверка сети" кнопку „Проверить сеть" и
сказать, что она показала.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против пункта 2 — §4 пропустить, в отчёте «не выполнялся».

Шаг 1.2. Папка и помощник проверки (только читает и шлёт пакеты к 192.0.2.53):

```bash
mkdir -p "$HOME/xgw-f3" && chmod 700 "$HOME/xgw-f3" && cd "$HOME/xgw-f3" && cat > f3check.py <<'EOF'
#!/usr/bin/env python3
"""ТЗ Ф3: контроль проверки сети на машине. Ничего не меняет; пакеты — только к 192.0.2.53.

  f3check.py cli ФАЙЛ   — проверки сети из `xgw diag --netcheck --json`
  f3check.py dns        — запрос к 192.0.2.53 без метки и с меткой мимо VPN
  f3check.py panel      — итог кнопки «Проверить сеть» и события из базы состояния
"""
import json
import re
import secrets
import socket
import sqlite3
import struct
import subprocess
import sys
import time

NAMES = ("MTU до сервера", "UDP напрямую", "UDP через VPN", "Утечка DNS", "Утечка IPv6")
DB = "file:/var/lib/xgw/state.db?mode=ro"


def show(check):
    line = f"{check['level']:<4}  {check['name']}: {check['text']}"
    return line + (f"\n      → {check['advice']}" if check.get("advice") else "")


def cli(path):
    checks = json.load(open(path, encoding="utf-8"))
    found = [check for check in checks if check["name"] in NAMES]
    for check in found:
        print(show(check))
    print(f"проверок сети: {len(found)} из {len(NAMES)}")


def bypass_mark():
    text = subprocess.run(["nft", "list", "chain", "ip", "xgw", "output"],
                          capture_output=True, text=True).stdout
    found = re.search(r"meta mark (0x[0-9a-f]+) return", text)
    return int(found.group(1), 16) if found else None


def ask(mark):
    name = b"".join(bytes([len(part)]) + part for part in b"example.com".split(b".")) + b"\0"
    query = struct.pack(">HHHHHH", secrets.randbits(16), 0x0100, 1, 0, 0, 0) + name + b"\0\1\0\1"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        if mark is not None:
            sock.setsockopt(socket.SOL_SOCKET, 36, mark)
        sock.settimeout(3)
        sock.sendto(query, ("192.0.2.53", 53))
        try:
            data = sock.recv(512)
        except TimeoutError:
            return "ответа нет"
    return "ответ есть" if data[:2] == query[:2] else "чужой ответ"


def dns():
    mark = bypass_mark()
    print(f"без метки (как DNS машины): {ask(None)}")
    if mark is None:
        print("метка мимо VPN: не найдена в цепочке output (перехват машины выключен?)")
    else:
        print(f"с меткой мимо VPN ({mark:#x}): {ask(mark)}")


def panel():
    db = sqlite3.connect(DB, uri=True)
    row = db.execute("SELECT value FROM meta WHERE key = 'netcheck'").fetchone()
    if not row or not row[0]:
        print("итога кнопки нет")
    else:
        last = json.loads(row[0])
        print(f"проверено: {time.strftime('%F %T', time.localtime(last['at']))}, "
              f"за {last['took']} с")
        for check in last["checks"]:
            print(show(check))
    for ts, detail in db.execute("SELECT ts, detail FROM events WHERE kind = 'netcheck' "
                                 "ORDER BY id DESC LIMIT 3"):
        print(f"событие {time.strftime('%T', time.localtime(ts))}: {detail}")


if __name__ == "__main__":
    {"cli": lambda: cli(sys.argv[2]), "dns": dns, "panel": panel}[sys.argv[1]]()
EOF
sha256sum f3check.py | cut -c1-16
```

Ожидается: `11395d10f7bb15d7`. Другая сумма — команда скопирована не целиком: выполнить шаг заново;
снова другая — **стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки:

```bash
cd "$HOME/xgw-f3" && sudo xgw status | grep -E '^Состояние|Перехват:' | tee before.txt
```

Ожидается: `Состояние: HEALTHY …`, `Перехват: включён …`. Записать как есть.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout netcheck-f3 && git pull --ff-only && git log -1 --format='%h %s' && test -f src/xgw/netcheck.py && echo "проверка сети в коде: есть"; cd "$HOME/xgw-f3"
```

Ожидается: «проверка сети в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-f3/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-f3/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-f3"
```

Ожидается: «код 0», «демон xgw запущен». Код не 0 — **стоп**, сохранить вывод, сообщить
заказчику (сеть не тронута).

Шаг 2.3. Через минуту — шлюз в порядке:

```bash
sleep 60; sudo xgw status | grep -E '^Состояние|Перехват:' | tee "$HOME/xgw-f3/after-install.txt"
```

Ожидается: `HEALTHY`, перехват включён. Иначе — подождать ещё 2 минуты и повторить; снова не
`HEALTHY` — записать вывод `sudo xgw status` целиком (без адресов) и продолжить.

## 3. Проверка сети в терминале

Шаг 3.1.

```bash
cd "$HOME/xgw-f3" && start=$(date +%s); sudo xgw diag --netcheck --json > diag.json; echo "код $?, заняло $(( $(date +%s) - start )) с" | tee netcheck-cli.txt; python3 -I f3check.py cli diag.json | tee -a netcheck-cli.txt
```

Ожидается:

- «проверок сети: 5 из 5» — строки «MTU до сервера», «UDP напрямую», «UDP через VPN», «Утечка
  DNS», «Утечка IPv6»;
- «Утечка DNS» — `OK` («DNS машины идёт через Xray: … ответил перехват, а мимо VPN — никто»
  или «не проверена: … провайдер подменяет DNS»);
- «Утечка IPv6» — `OK`;
- «UDP через VPN» — `OK` (если `WARN` — записать, это наблюдение, не дефект);
- «MTU до сервера», «UDP напрямую» — **записать как есть** (это данные о сети, не дефект);
- всё вместе (`diag` целиком) — не дольше 60 с. Код может быть 1, если у `diag` есть FAIL в
  других строках, — записать.

Если не так: строк меньше пяти или есть строка «проверка не выполнена» — **дефект «проверка
не выполнена»**, записать строку целиком. «Утечка DNS» или «Утечка IPv6» — `FAIL` — **дефект**:
записать и сразу выполнить шаг 3.2.

Шаг 3.2. Контроль проверки DNS — тот же запрос к недоступному адресу 192.0.2.53, без метки и с
меткой мимо VPN:

```bash
cd "$HOME/xgw-f3" && sudo python3 -I f3check.py dns | tee dns-control.txt
```

Ожидается: «без метки (как DNS машины): ответ есть» и «с меткой мимо VPN (0x…): ответа нет».
Это значит: на запрос машины отвечает перехват, а мимо VPN адрес не отвечает — проверка
показывает правду. «С меткой … ответ есть» — провайдер сам отвечает на DNS к любому адресу:
записать (тогда в 3.1 «Утечка DNS» должна быть «не проверена»). «Без метки … ответа нет» —
**дефект «DNS машины мимо перехвата»** — записать.

## 4. Кнопка в панели (при согласии на пункт 2)

Шаг 4.1. **Попроси заказчика** (дословно):

«Откройте панель XGW (ярлык „XGW" или адрес из установки). Слева, ниже карточки „Ядра", —
карточка „Проверка сети". Нажмите „Проверить сеть" и подождите до 15 секунд. Скажите: что
написано под кнопкой, пока идёт проверка; сколько строк появилось и у каких стоит „внимание"
или „ошибка".»

Записать ответ.

Шаг 4.2. Итог кнопки в базе состояния и событие:

```bash
cd "$HOME/xgw-f3" && sudo python3 -I f3check.py panel | tee netcheck-panel.txt
```

Ожидается: «проверено: <время> , за N с» — N не больше 15; шесть строк — те же пять, что в 3.1,
и строка о фаерволе («Файрвол», «ufw» или «Docker»); вердикты пяти общих строк — как в 3.1
(«UDP напрямую» и «MTU до сервера» могут отличаться — сеть меняется, записать); строка
«событие …: проверка сети: OK — …».

Если не так: «итога кнопки нет» после того, как заказчик нажал кнопку, — **дефект «итог не
записан»**: записать `sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager |
grep -iE 'проверк[аи] сети' | tail -5`.

## 5. Итог

Шаг 5.1.

```bash
sudo journalctl -u xgw --since "$(cat "$HOME/xgw-f3/install-time.txt")" --no-pager | grep -c Traceback | sed 's/^/Traceback в xgw: /'; sudo xgw diag | tail -1; sudo xgw status | grep -E '^Состояние|Перехват:'
```

Ожидается: Traceback — 0; «FAIL — 0»; состояние `HEALTHY`.

## 6. Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Шлюз не `HEALTHY` после установки — записать и продолжить: проверка сети как раз покажет, что
  не так; сеть не трогать.

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.18-netcheck-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`netcheck-f3`), коммит «Отчёт: проверка сети», `git push`. Шаблон:

```markdown
# Отчёт: кнопка «Проверить сеть»

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
f3check.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до | — | состояние, перехват |
| 2.2 установка | … | код … |
| 2.3 после установки | … | HEALTHY / … |
| 3.1 diag --netcheck | … | 5 из 5, DNS …, IPv6 …, UDP через VPN …, заняло N с |
| 3.1 данные сети | — | MTU: …; UDP напрямую: … |
| 3.2 контроль DNS | … | без метки: …, с меткой: … |
| 4.1 кнопка (заказчик) | … / не выполнялся | что видел |
| 4.2 итог кнопки | … | за N с, 6 строк, событие … |
| 5.1 итог | … | Traceback 0, FAIL — 0 |

## Выводы шагов
<файлы $HOME/xgw-f3/*.txt; имя пользователя → <user>>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
