# Проверка XGW 0.2.0: бесплатные серверы — исправления после отчётов вкладки и М2б.2

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-fpfix/…`). Файл помощника создавай только командой шага 1.2, выполненной в
терминале. Блок команды копируй целиком, ничего в нём не меняя.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. Телефон — S25 Ultra в домашней сети.
Команды — в терминале сеанса заказчика (`sudo` от его имени). На машине — Xray 26.10.29 и
sing-box 1.14.4, принятые шлюзом через карточку «Ядра»: установка их не откатывает.

Что нового (ASSUMPTIONS п. 268):
1. **Дефект М2б.2.** При включении всего дома панель и события на минуту говорили «допущенных
   серверов нет — у всего дома закрыто», хотя допущенные были. Теперь, пока шлюз пересобирает
   конфиг и пока ядро не проверило серверы пула, вверху панели «Бесплатные серверы
   подключаются», а событий о закрытии нет. Затем — «Через бесплатные серверы».
2. **Флажки в именах серверов** (битые значки вместо флагов) панель больше не показывает — на
   обеих вкладках, в главной карточке и в окнах подтверждения. Страна видна меткой.
3. **На вкладке «Бесплатные серверы»** не прошедшие проверку серверы свёрнуты в строку «Не
   прошли проверку — N» у каждого источника; на виду — в работе, допущенные и рабочие.
4. **Страница шире** на мониторе от 1500 точек: поля по бокам меньше.
5. Проверки Tailscale из `xgw diag` и предупреждения Xray 26.10.29 — записать.

Здесь, у разработчика, — только юнит-тесты затронутых модулей, ruff и `node --check` панели;
панель в браузере и переключение режима не проверялись. Всё это — на этой машине.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh`; ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`,
  `sysctl -w`, `systemd-run`, `apt`; команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`.
  `sudo xgw pool mode …` — только в шаге 3.1 (`observe`), в шагах 6.1 и 8.1 (если заказчик не
  нажал кнопку) и по правилам раздела «Если что-то пошло не так».
- Самому открывать сайты источников (vpngate, vpnbook), файлы списков на GitHub и сайты для
  проверки страны. Сайты на устройствах открывает только заказчик. Кнопки замера скорости в
  панели не нажимать (и не просить). Кнопки «Ядра» (обновить, вернуть) не нажимать (и не
  просить).
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, код XGW. Печатать `config.toml`, `panel.json`, рабочие конфиги
  Xray и sing-box, файлы в `/var/lib/xgw/freepool`, базу `/var/lib/xgw/state.db` — в них ключи
  подписок, пароли и ссылки серверов. Кнопки, вкладки и выбор в панели нажимает только
  заказчик. Коммитить что-либо, кроме отчёта (§9).
- Писать в отчёт: **имена серверов** (и бесплатных, и подписки — заказчик видит их в панели, в
  отчёт они не идут), адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP, домены и ссылки
  серверов VPN, логины и пароли, строки журнала. Можно: адреса устройств в домашней сети
  (`192.168.…`), коды стран, названия источников, надписи панели без имён серверов, счётчики,
  статусы, размеры, времена, строки помощника.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю исправления после прошлых проверок бесплатных серверов. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд. Внешний интерфейс (WAN), его соединение и DHCP
установка не трогает. Ядра Xray 26.10.29 и sing-box 1.14.4 останутся.
(2) Если наблюдение за бесплатными серверами выключено, я включу его командой
`sudo xgw pool mode observe` и подожду 30 минут, пока серверы проверятся.
(3) Вы откроете панель на вкладке «Бесплатные серверы» и на вкладке «Подписки» и скажете,
остались ли битые флажки в именах, как выглядят списки и поля по бокам страницы.
(4) Вы нажмёте «Весь дом через бесплатные» и подтвердите — как в прошлый раз: весь дом пойдёт
через бесплатные серверы (владельцы серверов неизвестны, сайты без https им видны), Xray может
перезапуститься — интернет на несколько секунд. Я посмотрю, что шлюз пишет в первые три
минуты. Если интернет перестанет работать — сразу скажите мне: вернём режим подписок.
(5) Через 5 минут вы откроете пару сайтов на компьютере и телефоне, затем нажмёте «Вернуть
режим подписок».
(6) В конце вы нажмёте «Выключить» на вкладке «Бесплатные серверы» (не ответите за 30 минут —
сделаю командами).
Проверка займёт около часа. Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 при выключенном наблюдении — пункты 4–5 не проверить:
шаги 3–6 пропустить. Против 3 — шаг 4.1 только командой, вопросы заказчику пропустить; против
4 — шаги 5–6 пропустить; против 5 — шаг 5.3 пропустить, в 6.1 вернуть командой; против 6 — в
8.1 командой. В отчёте у пропущенного — «не выполнялся». Если ответа на вопрос нет — не
начинать, спросить ещё раз.

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-fpfix" && chmod 700 "$HOME/xgw-fpfix" && cd "$HOME/xgw-fpfix" && cat > fpfixcheck.py <<'EOF'
"""XGW 0.2.0, бесплатный пул (исправления после отчётов вкладки и М2б.2): помощник проверки.
Только читает: состояние XGW (/run/xgw), базу событий (/var/lib/xgw/state.db — только чтение),
рабочий конфиг Xray, строки вкладки пула (код XGW) и журнал со стандартного ввода — счётчики,
коды стран, итоги и да/нет, без адресов, имён, ссылок и ключей. watch on|back — ход включения
всего дома или возврата: состояние пула раз в секунду три минуты после нажатия и события пула
(имена серверов скрыты). Режимы: units, pool, route, rows, names, watch, diag, warn, log."""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("FPFIX_LIB", "/opt/xgw/lib")
FLAG = re.compile("[\U0001F1E6-\U0001F1FF]")
NAME = re.compile("«[^»]*»")
MARKS = {"on": "бесплатный пул: весь дом через бесплатные серверы",
         "back": "режим подписок возвращён"}
WATCH = 180


def run(argv):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, type(exc).__name__
    return done.returncode, done.stdout


def show(unit, prop):
    return run(["systemctl", "show", "-p", prop, "--value", unit])[1].strip()


def xgw():
    sys.path.insert(0, LIB)
    from xgw import config
    from xgw.paths import Paths

    paths = Paths.from_env()
    return config.load(paths.config_file)[0], paths


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        print(f"{Path(path).name} не читается: {type(exc).__name__}")
        sys.exit(0)


def target(rule):
    if rule.get("balancerTag"):
        return f"балансировщик {rule['balancerTag']}"
    return f"выход {rule.get('outboundTag')}"


def flow_state(status):
    pool = status.get("free_pool") if isinstance(status.get("free_pool"), dict) else {}
    head = f"режим {pool.get('mode') or 'off'}"
    flow = pool.get("traffic")
    if not isinstance(flow, dict):
        return head + (": подключаются" if pool.get("mode") == "on" else ": через пул никто")
    if flow.get("closed"):
        why = "все серверы пула молчат" if flow.get("members") else "допущенных серверов нет"
        return f"{head}: ЗАКРЫТО — {why}"
    return (f"{head}: через сервер ({flow.get('country') or '—'}), живых {flow.get('alive')} "
            f"из {flow.get('members')}")


def events_since(paths, since):
    try:
        conn = sqlite3.connect(f"file:{paths.db_file}?mode=ro", uri=True, timeout=5)
        rows = conn.execute("SELECT ts, kind, detail FROM events WHERE ts >= ? ORDER BY id",
                            (since,)).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        print(f"база событий не читается: {type(exc).__name__}")
        return []
    return [(float(ts), str(kind), str(detail)) for ts, kind, detail in rows]


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
elif mode == "pool":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    pool = status.get("free_pool") if isinstance(status.get("free_pool"), dict) else {}
    print(f"состояние шлюза: {status.get('state')}; пул: {flow_state(status)}; найдено "
          f"{pool.get('found')}, проверено {pool.get('checked')}, пригодно {pool.get('ready')}")
elif mode == "route":
    cfg, paths = xgw()
    work = read_json(paths.xray_config_file) or {}
    rules = [rule for rule in (work.get("routing") or {}).get("rules") or []
             if isinstance(rule, dict)]
    carrier = any(rule.get("inboundTag") == ["http-in", "socks-in"] for rule in rules)
    servers = (work.get("dns") or {}).get("servers") or []
    tcp = sum(1 for entry in servers if str(
        (entry.get("address") if isinstance(entry, dict) else entry) or "").startswith("tcp://"))
    print(f"режим пула: {cfg.free_pool.mode}; последнее правило → "
          f"{target(rules[-1]) if rules else 'правил нет'}; несущий канал (http-in, socks-in): "
          f"{'есть' if carrier else 'нет'}; DNS по TCP: {tcp}")
elif mode == "rows":
    cfg, paths = xgw()
    from xgw.freepool import pool as pooling

    rows = pooling.server_rows(cfg, paths, time.time())
    status = read_json(paths.status_file) or {}
    flow = (status.get("free_pool") or {}).get("traffic") or {}
    live = [str(item.get("id") or "") for item in flow.get("servers") or []]
    print(f"режим пула: {cfg.free_pool.mode}; строк: {len(rows)}; имён с флажками: "
          f"{sum(1 for row in rows if FLAG.search(str(row.get('name') or '')))}")
    for source in sorted({str(row.get("source")) for row in rows}):
        mine = [row for row in rows if str(row.get("source")) == source]
        checked = [row for row in mine if row.get("checked_at")]
        shown = [row for row in checked
                 if not row.get("why") or row.get("verdict") in ("OK", "SLOW")
                 or any(ident and str(row.get("id")).startswith(ident) for ident in live)]
        print(f"{source}: на виду {len(shown)}; «Не прошли проверку» {len(checked) - len(shown)}"
              f"; «Ещё не проверялись» {len(mine) - len(checked)}")
elif mode == "names":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    names = [str(item.get("name") or "") for key in ("members", "spares")
             for item in status.get(key) or [] if isinstance(item, dict)]
    print(f"серверов подписки в состоянии: {len(names)}; имён с флажками: "
          f"{sum(1 for name in names if FLAG.search(name))}")
elif mode == "watch":
    which = sys.argv[2] if len(sys.argv) > 2 else "on"
    _cfg, paths = xgw()
    mark = MARKS.get(which, MARKS["on"])
    start, deadline, pressed = time.time() - 120, time.time() + 600, None
    print("жду нажатия кнопки (до 10 минут)…", flush=True)
    while pressed is None and time.time() < deadline:
        pressed = next((ts for ts, kind, detail in events_since(paths, start)
                        if kind == "freepool" and mark in detail), None)
        if pressed is None:
            time.sleep(1)
    if pressed is None:
        print("нажатия не было за 10 минут")
        sys.exit(0)
    print(f"нажатие: {time.strftime('%H:%M:%S', time.localtime(pressed))}", flush=True)
    last, samples, closed = None, 0, 0
    while time.time() < pressed + WATCH:
        state = flow_state(read_json(paths.status_file) or {})
        samples += 1
        closed += "ЗАКРЫТО" in state
        if state != last:
            print(f"+{time.time() - pressed:4.0f} с: {state}", flush=True)
            last = state
        time.sleep(1)
    found = [(ts, detail) for ts, kind, detail in events_since(paths, pressed - 1)
             if kind == "freepool"]
    for ts, detail in found:
        print(f"событие +{ts - pressed:4.0f} с: {NAME.sub('«<сервер>»', detail)}")
    print(f"замеров: {samples}; из них «ЗАКРЫТО»: {closed}; событий «допущенных серверов нет»: "
          f"{sum('допущенных серверов нет' in detail for _ts, detail in found)}; «все серверы "
          f"пула молчат»: {sum('молчат' in detail for _ts, detail in found)}; «идёт через»: "
          f"{sum(' идёт через ' in detail for _ts, detail in found)}")
    print(f"Xray: запущен {show('xgw-xray.service', 'ExecMainStartTimestamp') or '?'}")
elif mode == "diag":
    for line in sys.stdin.read().splitlines():
        found = re.match(r"(\S+)\s+(Tailscale: [^:]+):", line)
        if found:
            print(f"{found.group(1)} {found.group(2)}")
        elif line.startswith("Итог:"):
            print(line)
elif mode == "warn":
    lines = sys.stdin.read().splitlines()
    old = [line for line in lines if "deprecated" in line.lower()]
    print(f"строк журнала Xray: {len(lines)}; об устаревших настройках: {len(old)}; из них про "
          f"fragment: {sum(1 for line in old if 'fragment' in line)}")
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, words in (
        ("у всего дома закрыто", ("у всего дома закрыто",)),
        ("весь дом идёт через", ("бесплатный пул: весь дом идёт через",)),
        ("закрепление сервера пула не удалось", ("сервер бесплатного пула не закреплён",)),
        ("применений с перезапуском Xray", ("применено с перезапуском Xray",)),
        ("откат на last-good", ("last-good",)),
        ("шаг пула не выполнен", ("бесплатный пул: шаг не выполнен",)),
        ("Traceback", ("Traceback",)),
    ):
        print(f"{label}: {sum(1 for line in lines if any(word in line for word in words))}")
else:
    print("режим: units | pool | route | rows | names | watch on|back | diag | warn | log")
EOF
python3 -c "import hashlib;d=open('fpfixcheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units pool; do sudo python3 -I fpfixcheck.py $m; done | tee -a before.txt
```

Ожидается:
- `80be381989829da3`;
- `Состояние: …`, `Перехват: включён …`, строки `Xray …` (версия 26.10.29) и `sing-box …` —
  записать;
- первая строка `xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать,
  какая** (от неё зависит шаг 3.1);
- четыре службы `active`; строка `pool` — записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать и продолжить. Первая строка `xgw pool` —
«весь дом через бесплатные серверы» — попросить заказчика нажать «Вернуть режим подписок» в
главной карточке панели и выполнить шаг заново.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'not any(info.tag in observatory for info in pool)' src/xgw/daemon.py && grep -q 'const FLAGS = ' src/xgw/ui/app.js && grep -q 'Не прошли проверку' src/xgw/ui/app.js && grep -q -- '--page: min(1560px, 94vw)' src/xgw/ui/app.css && echo "правка в коде: есть"; cd "$HOME/xgw-fpfix"
```

Ожидается: «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. Внешний интерфейс (WAN), его
соединение и DHCP она не трогает; интернет дома пропадёт на несколько секунд, пока
перезапускаются службы XGW. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fpfix/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fpfix/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw' "$HOME/xgw-fpfix/install.txt"; cd "$HOME/xgw-fpfix"
```

Ожидается: «код 0», «демон xgw запущен». Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке, ядра прежние, проверки Tailscale и предупреждения Xray:

```bash
sleep 120; cd "$HOME/xgw-fpfix" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee after-install.txt; for m in units route pool; do sudo python3 -I fpfixcheck.py $m; done | tee -a after-install.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfixcheck.py diag | tee diag.txt; sudo journalctl -u xgw-xray --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpfixcheck.py warn | tee warn.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpfixcheck.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, `Xray …` — **26.10.29**, `sing-box …` — **1.14.4** (как в шаге
  1.2); четыре службы `active`;
- `route`: «режим пула: off» (или observe); «последнее правило → балансировщик auto»;
  «несущий канал (http-in, socks-in): нет»; «DNS по TCP: 0»;
- `diag`: строки вида «OK Tailscale: …» и «Итог: …» — **записать все** (WARN или FAIL у
  Tailscale — записать как есть, это наблюдение, не стоп);
- `warn`: «строк журнала Xray: …; об устаревших настройках: …; из них про fragment: …» —
  записать;
- журнал с установки: «Traceback: 0».

Если не так: не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать, сообщить
заказчику и продолжить. Версия Xray стала 26.10.21 (откатилась) — записать как **дефект** и
продолжить. «DNS по TCP» больше 0 или «несущий канал: есть» — **стоп**: режим остался с
другого прогона (попросить заказчика «Вернуть режим подписок» и повторить шаг).

## 3. Наблюдение

Шаг 3.1. Только если в шаге 1.2 наблюдение было **выключено**; иначе — пропустить, в отчёте
«уже было включено»:

```bash
cd "$HOME/xgw-fpfix" && date '+%F %T' | tee observe-time.txt && sudo xgw pool mode observe 2>&1 | tee mode-on.txt
```

Ожидается: «Наблюдение за бесплатным пулом включено: … Демон применит режим на ближайшем шаге».

**Скажи заказчику** (дословно): «Наблюдение включено. Через 30 минут попрошу вас посмотреть
вкладку и включить весь дом.» Подожди **30 минут** (если наблюдение уже было включено — 5
минут).

## 4. Вкладки панели

Шаг 4.1. Строки вкладки и имена серверов:

```bash
cd "$HOME/xgw-fpfix" && for m in pool rows names; do sudo python3 -I fpfixcheck.py $m; done | tee rows.txt
```

Ожидается:
- `pool`: «пул: режим observe: через пул никто; найдено …, проверено …, пригодно …» —
  записать; пригодно — больше 0;
- `rows`: «режим пула: observe; строк: …; имён с флажками: F» — записать F (это сколько имён
  **с флажками в данных**; на экране флажков быть не должно); по строке на источник
  (`vpngate` — VPN Gate, `vpnbook` — VPNBook, `igareck` — GitHub igareck, `mahdibland` —
  GitHub mahdibland): «на виду A; «Не прошли проверку» B; «Ещё не проверялись» C» — записать
  все;
- `names`: «серверов подписки в состоянии: …; имён с флажками: G» — записать G.

Если не так: «пригодно 0» — подождать ещё 30 минут и повторить; снова 0 — шаги 5–6
пропустить («отложено: нет допущенных серверов»), продолжить с шага 4.2.

Шаг 4.2. **Спроси заказчика** (дословно):

«Откройте, пожалуйста, панель XGW на этом компьютере, обновите страницу (F5) и откройте
вкладку «Бесплатные серверы». Ответьте по пунктам (имена серверов называть не нужно):
(а) Есть ли в именах серверов битые значки вместо флагов?
(б) У каждого источника — сначала серверы с задержкой или меткой «допущен», а ниже свёрнутые
строки «Не прошли проверку — N…» и «Ещё не проверялись — N…»? Назовите числа N у каждого
источника. Нажмите «Не прошли проверку» у одного источника — раскрылся ли список и
сворачивается ли он обратно повторным нажатием?
(в) Откройте вкладку «Подписки»: есть ли битые значки в именах серверов там?
(г) Как теперь с полями слева и справа страницы — стали меньше? Какой у вас монитор (ширина в
точках, если знаете, например 1920)?»

Ожидается: (а) нет; (б) да, числа N совпадают с B и C из шага 4.1 у тех же источников (могут
отличаться на 1–2 — проверки идут; записать оба); раскрывается и сворачивается; (в) нет; (г)
меньше (на мониторе уже 1500 точек страница прежняя — это правильно).

Если не так: битые значки остались — **дефект** (записать, на какой вкладке и где: в строке,
в главной карточке, в окне); нет строки «Не прошли проверку», а непрошедшие видны списком —
**дефект**; поля прежние на мониторе от 1920 точек — **дефект**.

## 5. Включение всего дома

Шаг 5.1. **Скажи заказчику** (дословно): «Теперь, пожалуйста, на вкладке «Бесплатные серверы»
нажмите «Весь дом через бесплатные» и подтвердите. Посмотрите на надпись вверху страницы
справа сразу после нажатия и через минуту-две — потом скажу, что прочитать.» Сразу затем
(команда ждёт нажатия до 10 минут и следит три минуты после):

```bash
cd "$HOME/xgw-fpfix" && sudo python3 -I fpfixcheck.py watch on | tee watch-on.txt
```

Ожидается:
- «нажатие: ЧЧ:ММ:СС»;
- строки «+N с: …» по порядку: «режим observe: через пул никто» (возможно), затем «режим on:
  подключаются», затем «режим on: через сервер (XX), живых … из …» — обычно в пределах двух
  минут; **ни одной строки с «ЗАКРЫТО»**;
- события: «бесплатный пул: весь дом через бесплатные серверы», «… весь дом идёт через
  «<сервер>» (XX)»;
- «замеров: …; из них «ЗАКРЫТО»: 0; событий «допущенных серверов нет»: 0; «все серверы пула
  молчат»: 0; «идёт через»: 1» (или больше, если сервер сменился);
- «Xray: запущен …» — записать (перезапуск при включении — норма).

Если не так: «ЗАКРЫТО» или событие «допущенных серверов нет» / «молчат» — **дефект** (записать
строки помощника целиком, они без имён) и продолжить. «через сервер» так и не появилось за три
минуты — выполнить `sudo python3 -I fpfixcheck.py pool` ещё раз через 2 минуты; снова не
«через сервер» — **дефект**, попросить заказчика «Вернуть режим подписок» и перейти к шагу 6.2.

Шаг 5.2. **Спроси заказчика** (дословно): «Что было написано вверху страницы справа сразу после
нажатия и что написано сейчас? Если не успели заметить первое — так и скажите.»

Ожидается: сразу — «Бесплатные серверы подключаются» (или «не успел заметить»), сейчас —
«Через бесплатные серверы». «Бесплатных серверов нет» сразу после нажатия — **дефект**.

Шаг 5.3. Через 5 минут после нажатия **спроси заказчика** (дословно): «Откройте, пожалуйста,
два-три сайта на компьютере и на телефоне. Открываются?» Затем:

```bash
cd "$HOME/xgw-fpfix" && for m in pool route; do sudo python3 -I fpfixcheck.py $m; done | tee house.txt
```

Ожидается: ответ «открываются»; `pool`: «режим on: через сервер (XX), живых … из …»; `route`:
«режим пула: on; последнее правило → балансировщик pool; несущий канал (http-in, socks-in):
есть; DNS по TCP: 2» (как в М2б.2).

Если не так: сайты не открываются — **сразу** раздел «Если что-то пошло не так».

## 6. Возврат режима подписок

Шаг 6.1. **Скажи заказчику** (дословно): «Нажмите, пожалуйста, «Вернуть режим подписок» в
главной карточке панели.» Сразу затем:

```bash
cd "$HOME/xgw-fpfix" && sudo python3 -I fpfixcheck.py watch back | tee watch-back.txt
```

Ожидается: «нажатие: …»; строки «+N с: …»: «режим on: через сервер …», затем «режим observe:
через пул никто»; ни одной строки с «ЗАКРЫТО»; событие «бесплатный пул: режим подписок
возвращён, наблюдение продолжается»; «из них «ЗАКРЫТО»: 0; событий «допущенных серверов нет»:
0».

Если не так: заказчик не нажал за 10 минут — `sudo xgw pool mode observe` и шаг 6.2; «ЗАКРЫТО» —
**дефект** (записать строки) и продолжить.

Шаг 6.2. Через минуту после возврата:

```bash
sleep 60; cd "$HOME/xgw-fpfix" && for m in pool route; do sudo python3 -I fpfixcheck.py $m; done | tee back.txt
```

Ожидается: `pool`: «режим observe: через пул никто»; `route`: «режим пула: observe; последнее
правило → балансировщик auto; несущий канал (http-in, socks-in): нет; DNS по TCP: 0».

## 7. Секреты

```bash
cd "$HOME/xgw-fpfix" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt
```

Ожидается: `0` — строк со ссылкой сервера в журнале нет.

Если не так: больше 0 — **дефект** (строки журнала в отчёт не копировать).

## 8. Выключение и итог

Шаг 8.1. **Скажи заказчику** (дословно): «Нажмите, пожалуйста, «Выключить» на вкладке
«Бесплатные серверы».» Не нажал за 30 минут (или пункт 6 не согласован) — `sudo xgw pool mode
off`. Если наблюдение до проверки было включено (шаг 1.2) — **не выключать**: пропустить, в
отчёте «оставлено включённым, как было».

Шаг 8.2. Итог:

```bash
sleep 60; cd "$HOME/xgw-fpfix" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee final.txt; for m in units pool route; do sudo python3 -I fpfixcheck.py $m; done | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpfixcheck.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; четыре службы
`active`; «режим пула: off» (или observe, если так было); журнал: «у всего дома закрыто: 0»,
«весь дом идёт через: 1» или больше, «шаг пула не выполнен: 0», «откат на last-good: 0»,
«Traceback: 0»; «применений с перезапуском Xray» — записать.

## Если что-то пошло не так

- Интернет у всего дома пропал в режиме «весь дом» — попросить заказчика нажать «Вернуть
  режим подписок» (в главной карточке); не ответил за 2 минуты — `sudo xgw pool mode
  observe`. Записать время и строку `sudo python3 -I fpfixcheck.py pool`, дальше — шаги 6.2,
  8.1, 8.2 и отчёт.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-m2b2fix-<ДАТА>.md` в клоне, коммит
«Отчёт: XGW 0.2.0, бесплатные серверы, исправления после М2б.2» и `git push` в `freepool`.
Только этот файл. Без имён серверов, адресов (кроме `192.168.…`), доменов и строк журнала.

```markdown
# Отчёт: XGW 0.2.0, бесплатные серверы — исправления после отчётов вкладки и М2б.2

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
fpfixcheck.py: <сумма>. Наблюдение до проверки: <выключено / включено>. Ядра: Xray <…>,
sing-box <…> (до установки / после).

## Итог
| Включение: «ЗАКРЫТО» | События «допущенных нет» / «молчат» | «подключаются» → «через сервер», с | Надпись вверху (сразу / потом) | Возврат: «ЗАКРЫТО» |
|---|---|---|---|---|
| <0> | <0 / 0> | <+N> | <…> | <0> |

| Флажки на экране: пул / подписки | Флажков в данных: пул F / подписки G | Свёрнутые «Не прошли проверку» | Поля страницы | Монитор |
|---|---|---|---|---|
| <нет / нет> | <F / G> | <да; числа совпали> | <меньше> | <…> |

| Tailscale в diag | Предупреждений Xray: всего / про fragment | Traceback |
|---|---|---|
| <OK ×N> | <… / …> | <0> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 наблюдение | … | … |
| 4.1 строки | … | … |
| 4.2 вкладки | … | … |
| 5.1 включение | … | … |
| 5.2 надпись | … | … |
| 5.3 сайты | … | … |
| 6.1 возврат | … | … |
| 6.2 после возврата | … | … |
| 7 секреты | … | … |
| 8.1 выключение | … | … |
| 8.2 итог | … | … |

## Выводы шагов
- <строки помощника по шагам; ответы заказчика дословно, без имён серверов>

## Дефекты
<нет / список>

## Наблюдения
<…>
```
