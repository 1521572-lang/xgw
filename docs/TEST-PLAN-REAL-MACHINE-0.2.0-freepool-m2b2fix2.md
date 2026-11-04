# Проверка XGW 0.2.0: бесплатные серверы — удалённый доступ в режиме «весь дом»

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-fpfix2/…`). Файл помощника создавай только командой шага 1.2, выполненной в
терминале. Блок команды копируй целиком, ничего в нём не меняя. Экземпляр этого ТЗ держи в
`$HOME/xgw-fpfix2/plan.md`, а не в /tmp (там его стирают).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. Телефон — S25 Ultra. Команды — в
терминале сеанса заказчика (`sudo` от его имени). На машине — Xray 26.10.29 и sing-box 1.14.4,
принятые шлюзом через карточку «Ядра»: установка их не откатывает.

Что нового (ASSUMPTIONS п. 269) — по отчёту прошлой проверки, где в режиме «весь дом» пропал
удалённый доступ к шлюзу и режим пережил две перезагрузки:
1. **Tailscale мимо бесплатных серверов.** В режиме «весь дом» управление и DERP Tailscale
   (если tailscaled идёт через VPN) — через подписку, а имена Tailscale — прямыми серверами
   DNS. Удалённый доступ к шлюзу (панель и SSH через tailnet) от бесплатных серверов не
   зависит. `xgw diag` проверяет это правило.
2. **Перезагрузка снимает «весь дом»**: после неё шлюз сам в режиме подписок (наблюдение
   продолжается), в событиях — «весь дом снят после перезагрузки». Перезапуск службы и
   переустановка режим не снимают.
3. «Бесплатные серверы подключаются» — и после перезапуска Xray, а не только при нажатии.
4. Из имён серверов в панели убраны **все эмодзи** (не только флажки).

Здесь, у разработчика, — только юнит-тесты затронутых модулей, ruff и `node --check` панели;
Tailscale, перезагрузка и панель не проверялись. Всё это — на этой машине.

**Главное правило безопасности.** Пока включён «весь дом»: заказчик не ответил **2 минуты**
или говорит, что пропал интернет или доступ, — **сразу** раздел «Если что-то пошло не так»
(вернуть режим подписок командой). Не ждать, не продолжать шаги. Кроме того, перед включением
ставится страховочный таймер (шаг 5.1): через 25 минут он сам вернёт режим подписок, даже если
доступа к машине не будет ни у кого.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, сон машины —
  **никогда**; `reboot` — только сам заказчик и только в шаге 8.1 (пункт 7 согласия).
  Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`,
  `apt`; команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`. `systemd-run` и `systemctl
  stop` — только для страховочных таймеров `xgw-fpfix2-guard` и `xgw-fpfix2-guard2` (шаги 5.1,
  6.1, 8.1 и раздел «Если что-то пошло не так»). `sudo xgw pool mode …` — только в шаге 3.1 (`observe`), в шагах 6.1 и
  9.1 (если заказчик не нажал кнопку) и по правилам раздела «Если что-то пошло не так».
- Самому открывать сайты источников (vpngate, vpnbook), файлы списков на GitHub и сайты для
  проверки страны. Сайты на устройствах открывает только заказчик. Кнопки замера скорости и
  кнопки «Ядра» в панели не нажимать (и не просить).
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, код XGW. Печатать `config.toml`, `panel.json`, рабочие конфиги
  Xray и sing-box, файлы в `/var/lib/xgw/freepool`, базу `/var/lib/xgw/state.db`. Кнопки,
  вкладки и выбор в панели нажимает только заказчик (или, по его просьбе, управляемый браузер —
  только чтение страницы, без нажатий кнопок режима). Коммитить что-либо, кроме отчёта (§10).
- Писать в отчёт: **имена серверов**, адреса tailnet, имена `*.ts.net`, имена устройств и
  пользователей (имя пользователя → `<user>`), внешние IP, токены, адреса и домены подписок,
  IP, домены и ссылки серверов VPN, логины и пароли, строки журнала. Можно: адреса устройств в
  домашней сети (`192.168.…`), коды стран, названия источников, надписи панели без имён
  серверов, счётчики, статусы, размеры, времена, строки помощника.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю исправления после прошлой проверки, где в режиме «весь дом» пропал удалённый доступ.
По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд. WAN и DHCP установка не трогает. Ядра Xray 26.10.29
и sing-box 1.14.4 останутся.
(2) Если наблюдение за бесплатными серверами выключено, я включу его и подожду 30 минут.
(3) Вы посмотрите вкладки «Бесплатные серверы» и «Подписки»: остались ли битые значки в именах
серверов (можно поручить это проверить автоматически, как в прошлый раз).
(4) Перед включением «всего дома» я поставлю страховочный таймер: через 25 минут он сам вернёт
режим подписок, даже если доступа к машине не будет. Затем вы нажмёте «Весь дом через
бесплатные» и подтвердите. Если интернет или доступ пропадут — сразу скажите; если вы не
ответите 2 минуты, я сам верну режим подписок.
(5) Через 5 и через 15 минут после включения вы откроете панель шлюза **с телефона через
Tailscale по мобильной сети** (Wi-Fi на телефоне выключить) и скажете, открылась ли она; и
откроете пару сайтов на компьютере.
(6) Затем вы нажмёте «Вернуть режим подписок».
(7) По желанию: в конце — одна перезагрузка машины в режиме «весь дом», чтобы проверить, что
после неё шлюз сам в режиме подписок. Перезагрузку делаете вы; после неё нужно снова запустить
меня, чтобы я закончил проверку.
(8) В конце вы нажмёте «Выключить» на вкладке «Бесплатные серверы», если наблюдение до
проверки было выключено.
Проверка займёт около полутора часов. Можно согласиться не на все пункты.»

Против пункта 1 или 4 — **стоп**. Против 2 при выключенном наблюдении — шаги 3–8 пропустить.
Против 3 — шаг 4.2 только командой. Против 5 — шаги 5.4 и 5.5 без вопросов о телефоне (только
команды). Против 6 — в 6.1 вернуть командой. Против 7 — §8 пропустить. Против 8 — в 9.1
командой. В отчёте у пропущенного — «не выполнялся». Если ответа нет — не начинать, спросить
ещё раз.

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-fpfix2" && chmod 700 "$HOME/xgw-fpfix2" && cd "$HOME/xgw-fpfix2" && cat > fpfix2check.py <<'EOF'
"""XGW 0.2.0, бесплатный пул: удалённый доступ в режиме «весь дом» (отчёт m2b2fix) — помощник
проверки. Только читает: состояние XGW (/run/xgw), базу событий (/var/lib/xgw/state.db — только
чтение), рабочий конфиг Xray, строки вкладки пула (код XGW) и вывод команд со стандартного
ввода — счётчики, коды стран, итоги и да/нет, без адресов, имён, ссылок и ключей. watch on|back
— ход включения или возврата: состояние пула раз в секунду три минуты после нажатия и события
пула (имена серверов скрыты). Режимы: units, pool, route, ts, mark, rows, names, watch, events,
diag, log."""
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
LIB = os.environ.get("FPFIX2_LIB", "/opt/xgw/lib")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣"
                   "\U000E0020-\U000E007F]")
NAME = re.compile("«[^»]*»")
TS = ["domain:tailscale.com", "domain:tailscale.io"]
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
    ts_rule = next((rule for rule in rules if rule.get("domain") == TS), None)
    servers = (work.get("dns") or {}).get("servers") or []
    tcp = sum(1 for entry in servers if str(
        (entry.get("address") if isinstance(entry, dict) else entry) or "").startswith("tcp://"))
    direct = [entry for entry in servers if isinstance(entry, dict) and entry.get("domains")]
    ts_dns = bool(direct) and all(set(TS) <= set(entry["domains"]) for entry in direct)
    print(f"режим пула: {cfg.free_pool.mode}; последнее правило → "
          f"{target(rules[-1]) if rules else 'правил нет'}; несущий канал (http-in, socks-in): "
          f"{'есть' if carrier else 'нет'}; DNS по TCP: {tcp}")
    print("правило Tailscale (tailscale.com, tailscale.io) → "
          + (target(ts_rule) if ts_rule else "нет")
          + f"; имена Tailscale у прямых серверов DNS: {'да' if ts_dns else 'нет'}")
elif mode == "ts":
    cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    print(f"tailscale.route: {cfg.tailscale.route}; tailscaled через VPN сейчас (DERP напрямую "
          f"не отвечает или route = vpn): {'да' if status.get('tailscale_via_vpn') else 'нет'}")
elif mode == "mark":
    _cfg, paths = xgw()
    print(f"метка «весь дом в этой загрузке»: {'есть' if paths.house_file.exists() else 'нет'}")
elif mode == "rows":
    cfg, paths = xgw()
    from xgw.freepool import pool as pooling

    rows = pooling.server_rows(cfg, paths, time.time())
    print(f"режим пула: {cfg.free_pool.mode}; строк: {len(rows)}; имён с эмодзи (в данных): "
          f"{sum(1 for row in rows if EMOJI.search(str(row.get('name') or '')))}")
elif mode == "names":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    names = [str(item.get("name") or "") for key in ("members", "spares")
             for item in status.get(key) or [] if isinstance(item, dict)]
    print(f"серверов подписки в состоянии: {len(names)}; имён с эмодзи (в данных): "
          f"{sum(1 for name in names if EMOJI.search(name))}")
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
elif mode == "events":
    _cfg, paths = xgw()
    hours = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    for ts, kind, detail in events_since(paths, time.time() - hours * 3600):
        if kind == "freepool":
            print(f"{time.strftime('%H:%M:%S', time.localtime(ts))} "
                  f"{NAME.sub('«<сервер>»', detail)}")
elif mode == "diag":
    for line in sys.stdin.read().splitlines():
        found = re.match(r"(\S+)\s+(Tailscale: [^:]+):", line)
        if found:
            print(f"{found.group(1)} {found.group(2)}")
        elif re.match(r"\S+\s+Весь дом через бесплатный пул:", line) or line.startswith("Итог:"):
            print(line)
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, words in (
        ("у всего дома закрыто", ("у всего дома закрыто",)),
        ("весь дом идёт через", ("бесплатный пул: весь дом идёт через",)),
        ("весь дом снят после перезагрузки", ("весь дом снят после перезагрузки",)),
        ("метка всего дома не записана", ("метка всего дома через пул не записана",)),
        ("применений с перезапуском Xray", ("применено с перезапуском Xray",)),
        ("откат на last-good", ("last-good",)),
        ("шаг пула не выполнен", ("бесплатный пул: шаг не выполнен",)),
        ("Traceback", ("Traceback",)),
    ):
        print(f"{label}: {sum(1 for line in lines if any(word in line for word in words))}")
else:
    print("режим: units | pool | route | ts | mark | rows | names | watch on|back | events | "
          "diag | log")
EOF
python3 -c "import hashlib;d=open('fpfix2check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units pool ts; do sudo python3 -I fpfix2check.py $m; done | tee -a before.txt
```

Ожидается:
- `0d52a24a50ec0a66`;
- `Состояние: …`, `Перехват: включён …`, `Xray …` (26.10.29), `sing-box …` (1.14.4) — записать;
- первая строка `xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать,
  какая** (от неё зависят шаги 3.1 и 9.1);
- четыре службы `active`; строки `pool` и `ts` — записать (`ts`: «tailscale.route: …;
  tailscaled через VPN сейчас: …» — это и есть ответ, каким путём tailscaled ходил до
  проверки).

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**. Не `HEALTHY` — записать и продолжить. Первая строка `xgw pool` — «весь дом через
бесплатные серверы» — попросить заказчика нажать «Вернуть режим подписок» и повторить шаг.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q '^TS_CONTROL = ("domain:tailscale.com", "domain:tailscale.io")' src/xgw/generator/builder.py && grep -q 'def house_after_boot' src/xgw/actions.py && grep -q 'def _house_mark' src/xgw/daemon.py && grep -q '^POOL_WAIT = 120.0' src/xgw/daemon.py && grep -q 'Extended_Pictographic' src/xgw/ui/app.js && echo "правка в коде: есть"; cd "$HOME/xgw-fpfix2"
```

Ожидается: «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fpfix2/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fpfix2/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw' "$HOME/xgw-fpfix2/install.txt"; cd "$HOME/xgw-fpfix2"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты:

```bash
sleep 120; cd "$HOME/xgw-fpfix2" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee after-install.txt; for m in units route ts mark; do sudo python3 -I fpfix2check.py $m; done | tee -a after-install.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfix2check.py diag | tee diag-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpfix2check.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; четыре службы `active`;
- `route`: «режим пула: off» (или observe); «последнее правило → балансировщик auto»;
  «несущий канал: нет»; «DNS по TCP: 0»; «правило Tailscale … → нет; имена Tailscale у прямых
  серверов DNS: нет» (в режиме подписок их и не должно быть);
- `mark`: «метка «весь дом в этой загрузке»: нет»;
- `diag`: строки «OK Tailscale: …» и «Итог: …» — записать; строки «Весь дом через бесплатный
  пул» нет (режим не on);
- журнал: «Traceback: 0».

Если не так: не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать, сообщить
заказчику и продолжить. Xray стал 26.10.21 — **дефект**, продолжить.

## 3. Наблюдение

Шаг 3.1. Только если в шаге 1.2 наблюдение было **выключено** (иначе — пропустить, «уже было
включено»):

```bash
cd "$HOME/xgw-fpfix2" && sudo xgw pool mode observe 2>&1 | tee mode-on.txt
```

Ожидается: «Наблюдение за бесплатным пулом включено: …».

**Скажи заказчику** (дословно): «Наблюдение включено. Через 30 минут попрошу вас посмотреть
вкладки.» Подожди **30 минут** (если было включено — 5 минут).

## 4. Вкладки панели

Шаг 4.1.

```bash
cd "$HOME/xgw-fpfix2" && for m in pool rows names; do sudo python3 -I fpfix2check.py $m; done | tee rows.txt
```

Ожидается: `pool` — «пригодно» больше 0; `rows` и `names` — «имён с эмодзи (в данных): E» и
«… K» — записать (это эмодзи **в данных**; на экране их быть не должно).

Если не так: «пригодно 0» — подождать ещё 30 минут и повторить; снова 0 — шаги 5–8 пропустить
(«отложено: нет допущенных серверов»), перейти к шагу 4.2, затем §9.

Шаг 4.2. **Спроси заказчика** (дословно): «Откройте, пожалуйста, панель на этом компьютере,
обновите страницу (F5) и посмотрите вкладки «Бесплатные серверы» и «Подписки», а также
главную карточку: есть ли где-нибудь в именах серверов битые значки (квадратики, «тофу»,
непонятные символы)? Если хотите, я проверю это автоматически, как в прошлый раз.»

Если заказчик просит проверить автоматически — управляемым браузером открыть панель (без
нажатий кнопок режима), на каждой вкладке выполнить в консоли страницы
`[...document.body.innerText.matchAll(/\p{Extended_Pictographic}|[\u{1F1E6}-\u{1F1FF}]/gu)].length`
и записать числа.

Ожидается: битых значков нет; автоматически — `0` на обеих вкладках. Имена без эмодзи
читаются нормально (слова не слиплись: например «x10 Германия», а не «x10Германия»).

Если не так: значки остались — **дефект** (где именно: вкладка, строка, карточка, окно).

## 5. Весь дом и удалённый доступ

Шаг 5.1. Страховочный таймер — **до** включения:

```bash
cd "$HOME/xgw-fpfix2" && date '+%F %T' | tee guard-time.txt && sudo systemd-run --on-active=25min --unit=xgw-fpfix2-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-fpfix2-guard.timer | head -3 | tee -a guard.txt
```

Ожидается: «Running timer as unit: xgw-fpfix2-guard.timer», в списке таймеров — строка
`xgw-fpfix2-guard.timer` со временем срабатывания через ~25 минут.

Если не так: таймера нет — **стоп**: без страховки «весь дом» не включать (шаги 5–8
пропустить, §9).

Шаг 5.2. **Скажи заказчику** (дословно): «Страховка стоит: через 25 минут режим подписок
вернётся сам. Нажмите, пожалуйста, на вкладке «Бесплатные серверы» «Весь дом через бесплатные»
и подтвердите.» Сразу затем:

```bash
cd "$HOME/xgw-fpfix2" && sudo python3 -I fpfix2check.py watch on | tee watch-on.txt
```

Ожидается: «нажатие: …»; строки «+N с»: «режим observe: через пул никто» (возможно) →
«режим on: подключаются» (возможно) → «режим on: через сервер (XX), живых … из …»; **ни одной
строки «ЗАКРЫТО»**; «событий «допущенных серверов нет»: 0; «все серверы пула молчат»: 0».

Если не так: «ЗАКРЫТО» или такие события — **дефект** (записать строки помощника) и
продолжить; «через сервер» не появилось за три минуты — раздел «Если что-то пошло не так».

Шаг 5.3. Что собрал шлюз:

```bash
cd "$HOME/xgw-fpfix2" && for m in pool route ts mark; do sudo python3 -I fpfix2check.py $m; done | tee house.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfix2check.py diag | tee diag-house.txt
```

Ожидается:
- `pool`: «режим on: через сервер (XX), живых … из …»;
- `route`: «последнее правило → балансировщик pool; несущий канал: есть; DNS по TCP: 2»;
  «правило Tailscale (tailscale.com, tailscale.io) → балансировщик auto; имена Tailscale у
  прямых серверов DNS: да»;
- `ts`: записать (как в 1.2 или другое — записать оба);
- `mark`: «метка «весь дом в этой загрузке»: есть»;
- `diag`: «OK Весь дом через бесплатный пул: через бесплатный пул, серверов в «pool»: N;
  подписка — только входам демона и Tailscale (несущий канал)»; строки «Tailscale: …» — OK.

Если не так: «правило Tailscale … → нет», «имена Tailscale … нет» или FAIL у «Весь дом через
бесплатный пул» — **дефект**, сразу раздел «Если что-то пошло не так» (вернуть режим подписок).

Шаг 5.4. Через **5 минут** после нажатия **спроси заказчика** (дословно): «Выключите,
пожалуйста, Wi-Fi на телефоне и откройте панель шлюза через Tailscale по мобильной сети. Она
открылась? И откройте пару сайтов на этом компьютере — открываются?» Затем:

```bash
cd "$HOME/xgw-fpfix2" && date '+%T' | tee -a check-5.txt; for m in pool ts; do sudo python3 -I fpfix2check.py $m; done | tee -a check-5.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfix2check.py diag | tee -a check-5.txt
```

Ожидается: «панель открылась», «сайты открываются»; `pool` — «через сервер …»; строки
`Tailscale: …` — OK.

Если не так: панель с телефона не открылась — подождать минуту и попросить ещё раз; снова нет —
**дефект 1 не исправлен**: сразу раздел «Если что-то пошло не так». Заказчик не ответил 2
минуты — тот же раздел.

Шаг 5.5. Через **15 минут** после нажатия — то же, что в шаге 5.4 (вопрос дословно тот же),
команда с файлом `check-15.txt`:

```bash
cd "$HOME/xgw-fpfix2" && date '+%T' | tee -a check-15.txt; for m in pool ts; do sudo python3 -I fpfix2check.py $m; done | tee -a check-15.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfix2check.py diag | tee -a check-15.txt
```

Ожидается и «Если не так» — как в шаге 5.4.

## 6. Возврат режима подписок

Шаг 6.1. **Скажи заказчику** (дословно): «Нажмите, пожалуйста, «Вернуть режим подписок» в
главной карточке панели.» Сразу затем:

```bash
cd "$HOME/xgw-fpfix2" && sudo python3 -I fpfix2check.py watch back | tee watch-back.txt; sudo systemctl stop xgw-fpfix2-guard.timer; systemctl list-timers --all --no-pager xgw-fpfix2-guard.timer | head -3 | tee guard-off.txt
```

Ожидается: «нажатие: …»; «режим on: через сервер …» → «режим observe: через пул никто»; ни
одной строки «ЗАКРЫТО»; событие «… режим подписок возвращён, наблюдение продолжается»;
таймер `xgw-fpfix2-guard.timer` больше не в списке («0 timers listed»).

Если не так: заказчик не нажал за 10 минут — `sudo xgw pool mode observe`, затем `sudo
systemctl stop xgw-fpfix2-guard.timer`, дальше шаг 6.2.

Шаг 6.2. Через минуту:

```bash
sleep 60; cd "$HOME/xgw-fpfix2" && for m in pool route mark; do sudo python3 -I fpfix2check.py $m; done | tee back.txt
```

Ожидается: «режим observe: через пул никто»; «последнее правило → балансировщик auto;
несущий канал: нет; DNS по TCP: 0»; «правило Tailscale … → нет»; «метка …: нет».

## 7. Секреты

```bash
cd "$HOME/xgw-fpfix2" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt
```

Ожидается: `0`. Если больше — **дефект** (строки журнала в отчёт не копировать).

## 8. Перезагрузка снимает «весь дом» (пункт 7 согласия)

Только если заказчик согласился на пункт 7. Иначе — пропустить, в отчёте «не выполнялся».

Шаг 8.1. Снова страховка (второй таймер — своё имя):

```bash
cd "$HOME/xgw-fpfix2" && sudo systemd-run --on-active=25min --unit=xgw-fpfix2-guard2 /usr/local/bin/xgw pool mode observe 2>&1 | tee guard2.txt; systemctl list-timers --all --no-pager xgw-fpfix2-guard2.timer | head -3 | tee -a guard2.txt
```

Ожидается: «Running timer as unit: xgw-fpfix2-guard2.timer». Нет таймера — §8 пропустить.
Затем **скажи заказчику** (дословно): «Нажмите, пожалуйста, снова «Весь дом через бесплатные»
и подтвердите.» Через 3 минуты:

```bash
cd "$HOME/xgw-fpfix2" && for m in pool mark; do sudo python3 -I fpfix2check.py $m; done | tee before-reboot.txt; date '+%F %T' | tee reboot-time.txt
```

Ожидается: «режим on: через сервер …», «метка …: есть». Затем **скажи заказчику** (дословно):
«Перезагрузите, пожалуйста, компьютер. После загрузки войдите в свой сеанс, снова запустите
меня с этим ТЗ (файл `$HOME/xgw-fpfix2/plan.md`) и напишите «продолжи с шага 8.2».»

Шаг 8.2. После перезагрузки (через 3 минуты после входа заказчика):

```bash
cd "$HOME/xgw-fpfix2" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee after-reboot.txt; sudo xgw pool 2>&1 | head -1 | tee -a after-reboot.txt; for m in units pool route mark; do sudo python3 -I fpfix2check.py $m; done | tee -a after-reboot.txt; sudo python3 -I fpfix2check.py events 2 | tee events-reboot.txt; sudo journalctl -u xgw -b --no-pager | sudo python3 -I fpfix2check.py log | tee log-reboot.txt; systemctl list-timers --all --no-pager xgw-fpfix2-guard.timer | head -3 | tee -a after-reboot.txt
```

Ожидается:
- `HEALTHY` (или ещё запускается — повторить через 2 минуты), перехват включён;
- первая строка `xgw pool` — «… наблюдение (трафик через подписку) …», **не** «весь дом»;
- `pool`: «режим observe: через пул никто»; `route`: «последнее правило → балансировщик auto;
  несущий канал: нет»; `mark`: «нет»;
- `events`: среди последних — «бесплатный пул: весь дом снят после перезагрузки — трафик через
  подписку, наблюдение продолжается; включить снова — кнопкой на вкладке»;
- журнал этой загрузки: «весь дом снят после перезагрузки: 1», «у всего дома закрыто: 0»,
  «Traceback: 0»;
- страховочного таймера нет (transient-таймер перезагрузку не переживает).

**Спроси заказчика** (дословно): «Откройте, пожалуйста, панель шлюза с телефона через Tailscale
по мобильной сети — открылась? И что написано вверху страницы?»

Ожидается: «открылась», вверху — состояние режима подписок (например «Работает»), не «Через
бесплатные серверы».

Если не так: после перезагрузки снова «весь дом» — **дефект** (рекомендация (б) прошлого
отчёта не выполнена), сразу раздел «Если что-то пошло не так».

## 9. Выключение и итог

Шаг 9.1. Если наблюдение до проверки было выключено (шаг 1.2) — **скажи заказчику**
(дословно): «Нажмите, пожалуйста, «Выключить» на вкладке «Бесплатные серверы».» Не нажал за 30
минут — `sudo xgw pool mode off`. Было включено — не выключать, «оставлено включённым».

Шаг 9.2. Итог:

```bash
sleep 60; cd "$HOME/xgw-fpfix2" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee final.txt; for m in units pool route mark; do sudo python3 -I fpfix2check.py $m; done | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpfix2check.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; четыре службы `active`;
режим off (или observe, если так было); «метка …: нет»; журнал: «у всего дома закрыто: 0»,
«метка всего дома не записана: 0», «шаг пула не выполнен: 0», «откат на last-good: 0»,
«Traceback: 0».

## Если что-то пошло не так

- В режиме «весь дом» пропал интернет или доступ (панель через Tailscale с телефона не
  открывается), или заказчик не отвечает **2 минуты** — **сразу**, не дожидаясь ответа:
  `sudo xgw pool mode observe`, затем `sudo systemctl stop xgw-fpfix2-guard.timer
  xgw-fpfix2-guard2.timer` (ошибка «not loaded» у одного из них — норма). Записать
  время и строку `sudo python3 -I fpfix2check.py pool`, строки `ts` и `route`. Дальше — шаги
  6.2, 7, 9 и отчёт. «Весь дом» больше не включать.
- Сработал страховочный таймер (через 25 минут режим вернулся сам) — записать время и
  продолжить с шага 6.2.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.

## 10. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-m2b2fix2-<ДАТА>.md` в клоне, коммит
«Отчёт: XGW 0.2.0, бесплатные серверы, удалённый доступ в режиме «весь дом»» и `git push` в
`freepool`. Только этот файл. Без имён серверов, адресов (кроме `192.168.…`), доменов и строк
журнала.

```markdown
# Отчёт: XGW 0.2.0, бесплатные серверы — удалённый доступ в режиме «весь дом»

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
fpfix2check.py: <сумма>. Наблюдение до проверки: <…>. Ядра: Xray <…>, sing-box <…>.
Tailscale до проверки: route <…>, через VPN <да/нет>.

## Итог
| Панель с телефона через Tailscale: +5 / +15 мин / после перезагрузки | Правило Tailscale → auto / имена у прямых DNS | diag «Весь дом» | Включение: «ЗАКРЫТО» / события | После перезагрузки режим | Эмодзи на экране |
|---|---|---|---|---|---|
| <да / да / да> | <да / да> | <OK> | <0 / 0> | <observe, событие есть> | <нет> |

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
| 5.1 страховка | … | … |
| 5.2 включение | … | … |
| 5.3 что собрал шлюз | … | … |
| 5.4 доступ +5 мин | … | … |
| 5.5 доступ +15 мин | … | … |
| 6.1 возврат | … | … |
| 6.2 после возврата | … | … |
| 7 секреты | … | … |
| 8.1 перед перезагрузкой | … | … |
| 8.2 после перезагрузки | … | … |
| 9.1 выключение | … | … |
| 9.2 итог | … | … |

## Выводы шагов
- <строки помощника по шагам; ответы заказчика дословно, без имён серверов>

## Дефекты
<нет / список>

## Наблюдения
<…>
```
