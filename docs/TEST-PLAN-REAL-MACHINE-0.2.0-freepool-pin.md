# Проверка XGW 0.2.0: сервер бесплатного пула вручную и точный учёт подписок

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, прокручиваешь страницу,
  делаешь **снимок экрана** и смотришь на него, выполняешь JavaScript в консоли страницы.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J1–J7) — выполни её в консоли
   страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-pin/…` (так написано в командах). Время шага —
   по выводу `date` в команде, не по памяти.
5. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
6. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
7. Экземпляр этого ТЗ держи в `$HOME/xgw-pin/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2.
8. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `pincheck.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
9. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши дословно
   строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
   «Наблюдения», со словом «предположение».

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.29 и sing-box
1.14.4, принятые шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 272)

1. **Сервер бесплатного пула вручную.** Пока через бесплатные серверы идёт трафик (весь дом или
   устройства), у допущенного сервера на вкладке «Бесплатные серверы» — кнопка **«Выбрать»**. У
   выбранного — метка **«выбран вручную»** и кнопка **«Автовыбор»**. Выбранный ведёт трафик, пока
   отвечает; замолчал — трафик ведёт сервер, выбранный шлюзом (метка «выбран · не отвечает»).
   Команда — `sudo xgw pool pin <id|auto>`.
2. **Учёт подписок точнее.** Счётчики Xray теперь снимаются на каждом шаге демона, а не раз в
   минуту: трафик сервера, который пересобрали между отсчётами, больше не теряется (в прошлой
   проверке подписке досталось 26,8 МБ из 30).

### Главное правило безопасности

Пока включён «весь дом»: пропал интернет на машине, заказчик говорит, что пропал доступ, или не
отвечает на вопрос **2 минуты** — **сразу** раздел «Если что-то пошло не так» (вернуть режим
подписок командой). Перед включением «всего дома» ставится страховочный таймер: через 30 минут
он сам вернёт режим подписок.

### Что где на экране панели (для снимков)

- **Верх страницы**: слева — «XGW шлюз»; справа — **метка состояния** («Серверы в порядке»,
  «Через бесплатные серверы ▾»…). В режиме «весь дом» метка — кнопка возврата.
- **Правая колонка**: вкладки **«Подписки»** и **«Бесплатные серверы»**. На вкладке «Бесплатные
  серверы» вверху справа — «Опросить источники», «Весь дом через бесплатные» (во «всём доме» —
  «Вернуть режим подписок»), «Выключить»; ниже — серый текст, синеватая полоса «Весь дом через
  бесплатные серверы — сервер «…» (XX), задержка … мс; живых … из …», затем блоки источников
  (igareck, mahdibland, vpngate, vpnbook) со строками серверов. У строки — точка, имя, метки
  («сейчас через», «в работе», «допущен», протокол, страна), справа — задержка, под ней — серый
  текст, и **справа внизу строки — кнопка «Выбрать»** (у допущенных, пока трафик идёт через
  пул) или **«Автовыбор»** (у выбранного вручную).
- **Окно подтверждения** — по центру: заголовок, текст, «Отмена» и кнопка действия справа.

### Проверки JavaScript (в консоли страницы панели)

- **J1 — метка вверху:**
  `(() => { const c = document.getElementById("chip"); return [c.tagName, c.textContent.trim(), c.disabled].join(" | "); })()`
- **J4 — окно подтверждения:**
  `(() => { const d = document.getElementById("confirm-dialog"); return [d.open, document.getElementById("confirm-title").textContent, document.getElementById("confirm-yes").textContent].join(" | "); })()`
- **J5 — кнопки строк пула:**
  `(() => { const b = [...document.querySelectorAll("#pool-groups button.choose")].map((x) => x.textContent); return "Выбрать: " + b.filter((t) => t === "Выбрать").length + " | Автовыбор: " + b.filter((t) => t === "Автовыбор").length; })()`
- **J6 — метки строк пула:**
  `(() => { const t = [...document.querySelectorAll("#pool-groups .tag")].map((x) => x.textContent); return ["выбран вручную: " + t.filter((x) => x === "выбран вручную").length, "выбран · не отвечает: " + t.filter((x) => x === "выбран · не отвечает").length, "сейчас через: " + t.filter((x) => x === "сейчас через").length, "в работе: " + t.filter((x) => x === "в работе").length, "допущен: " + t.filter((x) => x === "допущен").length].join(" | "); })()`
- **J7 — нажать «Выбрать» у строки с меткой** (запасной путь, если кнопку не получается нажать
  мышью; `"в работе"` замени на `"допущен"`, только если так сказано в шаге):
  `(() => { const want = "в работе"; const row = [...document.querySelectorAll("#pool-groups li")].find((li) => [...li.querySelectorAll(".tag")].some((t) => t.textContent === want) && (li.querySelector("button.choose") || {}).textContent === "Выбрать"); if (!row) return "нет строки с меткой «" + want + "» и кнопкой «Выбрать»"; row.scrollIntoView({ block: "center" }); row.querySelector("button.choose").click(); return "нажато"; })()`

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, `reboot`, сон машины —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh`; ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`,
  `sysctl -w`, `apt`; команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`. `systemd-run` и
  `systemctl stop` — только для страховочного таймера `xgw-pin-guard`. `sudo xgw pool mode …` —
  только в шаге 3.1 (`observe`), в «Если не так» шагов, где это написано, и в разделе «Если
  что-то пошло не так». `sudo xgw pool pin …` — только в шаге 5.6.
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`), `https://example.com` и
  `https://www.wikipedia.org`. Единственная загрузка из терминала — команда шага 4.1
  (`speed.cloudflare.com`, 30 МБ). Сайты источников, файлы списков на GitHub, сайты проверки IP
  и страны — не открывать.
- В панели нажимать **только** то, что написано в шагах: вкладки, «Весь дом через бесплатные» и
  кнопку подтверждения в его окне, «Выбрать» и «Автовыбор» на строках бесплатных серверов, метку
  вверху и кнопки её окна, «Выключить». **Не нажимать**: кнопку питания, «Замерить скорость»,
  «Проверить запасные», «Обновить», «Опросить источники», переключатели Tailscale, «Ядра»,
  «Проверить сеть», «Выбрать» и «Автовыбор» у серверов **подписок**, строки устройств,
  «Добавить», «Убрать».
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, код XGW. Печатать `config.toml`, `panel.json`, рабочие конфиги
  Xray и sing-box, файлы в `/var/lib/xgw/freepool`, базу `/var/lib/xgw/state.db`, полный вывод
  `sudo xgw traffic`. Коммитить что-либо, кроме файла отчёта (§8). Снимки экрана в git не
  добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, токен из ссылки
  панели, MAC, имена пользователей (→ `<user>`), внешние IP, адреса и домены подписок, IP,
  домены и ссылки серверов VPN, строки журнала. Можно: коды стран, теги вида `pool-de-1a2b`,
  начало id сервера пула (8 знаков, как печатает помощник), надписи панели без имён, счётчики,
  мегабайты, статусы, времена, строки помощника.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю новую возможность — выбрать бесплатный сервер вручную, как «Выбрать» у серверов
подписки, — и точность учёта трафика подписок. Нажатия в панели и осмотр экрана я делаю сам, в
управляемом браузере. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Если наблюдение за бесплатными серверами выключено, я включу его и подожду 30 минут.
(3) Шлюз один раз скачает пробный файл 30 МБ (speed.cloudflare.com) — через подписку, как
обычный трафик (у подписки с лимитом — 30 МБ × множитель сервера).
(4) Я включу «весь дом через бесплатные серверы» примерно на 20 минут (страховочный таймер
вернёт режим подписок через 30 минут сам), выберу вручную два разных бесплатных сервера, верну
автовыбор и затем режим подписок. Интернет дома в это время идёт через бесплатные серверы и при
смене сервера может прерываться на несколько секунд. Если интернет или доступ пропадут — сразу
скажите.
(5) В конце верну наблюдение в то состояние, в каком оно было до проверки.
Проверка займёт около часа с четвертью. Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 при выключенном наблюдении или против 4 — §5 пропустить (в
отчёте: «ручной выбор не проверялся»). Против 3 — шаг 4.1 пропустить. Против 5 — §7 без смены
режима. В отчёте у пропущенного — «не выполнялся». Если ответа нет — не начинать, спросить ещё
раз.

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-pin" && chmod 700 "$HOME/xgw-pin" && cd "$HOME/xgw-pin" && cat > pincheck.py <<'EOF'
"""XGW 0.2.0, бесплатный пул: сервер пула вручную и отсчёт Xray на каждом шаге — помощник
проверки. Только читает: состояние XGW (/run/xgw), базу состояния (/var/lib/xgw/state.db —
только чтение), рабочий конфиг Xray, настройки (выбранный сервер — началом id) и вывод команд со
стандартного ввода — счётчики, мегабайты, коды стран, теги pool-<страна>-<начало id>, итоги и
да/нет; без имён серверов, устройств и подписок, ссылок и ключей. Время — секунды с 1970
(date +%s). Режимы: units, pool, route, state, flow, pinned, waitpin, watch on|back, events,
applies, rows, log."""
import datetime
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
LIB = os.environ.get("PINCHECK_LIB", "/opt/xgw/lib")
NAME = re.compile("«[^»]*»")
MARKS = {"on": "бесплатный пул: весь дом через бесплатные серверы",
         "back": "режим подписок возвращён"}
GOALS = {"on": "on", "back": "observe"}
MANUAL = {"on": "держится", "down": "не отвечает — ведёт выбранный шлюзом", "": "нет"}
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


def stamp(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts))


def arg(index, default):
    try:
        return float(sys.argv[index])
    except (IndexError, ValueError):
        return default


def mb(value):
    return f"{int(value or 0) / 1e6:.1f} МБ"


def pool_of(status):
    return status.get("free_pool") if isinstance(status.get("free_pool"), dict) else {}


def flow_line(status):
    pool = pool_of(status)
    head = f"режим {pool.get('mode') or 'off'}"
    flow = pool.get("traffic")
    if not isinstance(flow, dict):
        return head + (": подключаются" if pool.get("mode") == "on" else ": через пул никто")
    if flow.get("closed"):
        return f"{head}: ЗАКРЫТО; выбран вручную: {MANUAL.get(flow.get('manual') or '', '?')}"
    return (f"{head}: сейчас через {flow.get('tag') or '—'} ({flow.get('country') or '—'}), "
            f"живых {flow.get('alive')} из {flow.get('members')}; выбран вручную: "
            f"{MANUAL.get(flow.get('manual') or '', '?')}")


def tag_hex(tag):
    return str(tag or "").rsplit("-", 1)[-1]


def db(paths):
    conn = sqlite3.connect(f"file:{paths.db_file}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def events_since(paths, since):
    try:
        conn = db(paths)
        rows = conn.execute("SELECT ts, kind, detail FROM events WHERE ts >= ? ORDER BY id",
                            (since,)).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        print(f"база событий не читается: {type(exc).__name__}")
        return []
    return [(float(row["ts"]), str(row["kind"]), str(row["detail"])) for row in rows]


def applied_text(detail):
    return NAME.sub("«…»", detail.split(" (")[0])


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
elif mode == "pool":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    pool = pool_of(status)
    print(f"состояние шлюза: {status.get('state')}; пул: {flow_line(status)}; найдено "
          f"{pool.get('found')}, проверено {pool.get('checked')}, пригодно {pool.get('ready')}")
elif mode == "route":
    cfg, paths = xgw()
    work = read_json(paths.xray_config_file) or {}
    rules = [rule for rule in (work.get("routing") or {}).get("rules") or []
             if isinstance(rule, dict)]
    carrier = any(rule.get("inboundTag") == ["http-in", "socks-in"] for rule in rules)
    members = [str(item.get("tag")) for item in work.get("outbounds") or []
               if isinstance(item, dict) and str(item.get("tag") or "").startswith("pool-")]
    last = rules[-1] if rules else {}
    print(f"режим пула: {cfg.free_pool.mode}; последнее правило → "
          f"{last.get('balancerTag') or last.get('outboundTag') or 'правил нет'}; несущий "
          f"канал: {'есть' if carrier else 'нет'}; серверов в «pool»: {len(members)}")
    print(f"рабочий конфиг совпадает с режимом: "
          f"{'да' if carrier == (cfg.free_pool.mode == 'on') else 'НЕТ'}; новый конфиг ждёт "
          f"окна перезапуска: {'да' if paths.pending_config_file.exists() else 'нет'}")
elif mode == "state":
    cfg, paths = xgw()
    shown = pool_of(read_json(paths.status_file) or {}).get("mode") or "off"
    print(f"режим в настройках: {cfg.free_pool.mode}; в состоянии шлюза: {shown}; совпадают: "
          f"{'да' if shown == cfg.free_pool.mode else 'НЕТ'}")
elif mode == "flow":
    _cfg, paths = xgw()
    print(flow_line(read_json(paths.status_file) or {}))
elif mode == "pinned":
    cfg, paths = xgw()
    from xgw.freepool import traffic

    pin = cfg.managed.free_pool_pin
    flow = pool_of(read_json(paths.status_file) or {}).get("traffic") or {}
    work = read_json(paths.xray_config_file) or {}
    members = [tag_hex(item.get("tag")) for item in work.get("outbounds") or []
               if isinstance(item, dict) and str(item.get("tag") or "").startswith("pool-")]
    if not pin:
        print("выбран вручную: нет (сервер выбирает шлюз)")
    else:
        admitted = {item.node.fingerprint: item for item in traffic.admitted(cfg, paths,
                                                                            time.time())}
        item = admitted.get(pin)
        inside = any(pin.startswith(hex_) for hex_ in members)
        leads = pin.startswith(tag_hex(flow.get("tag")) or "-")
        print(f"выбран вручную: {pin[:8]}…; допущен: "
              + (f"да ({item.node.country.upper()})" if item else "нет")
              + f"; в «pool»: {'да' if inside else 'нет'}; ведёт трафик: "
              + ("да" if leads else "нет"))
elif mode == "waitpin":
    cfg, paths = xgw()
    goal = sys.argv[2] if len(sys.argv) > 2 else "on"
    limit = arg(3, 240.0)
    start, last = time.time(), None
    while True:
        line = flow_line(read_json(paths.status_file) or {})
        if line != last:
            print(f"+{time.time() - start:4.0f} с: {line}", flush=True)
            last = line
        flow = pool_of(read_json(paths.status_file) or {}).get("traffic") or {}
        if (flow.get("manual") or "") == ("" if goal == "auto" else goal):
            print(f"достигнуто за {time.time() - start:.0f} с")
            break
        if time.time() - start > limit:
            print(f"НЕ достигнуто за {limit:.0f} с")
            break
        time.sleep(2)
elif mode == "watch":
    which = sys.argv[2] if len(sys.argv) > 2 else "on"
    _cfg, paths = xgw()
    mark, goal = MARKS.get(which, MARKS["on"]), GOALS.get(which, "on")
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
    print(f"нажатие: {stamp(pressed)}", flush=True)
    last, closed, reached = None, 0, None
    while time.time() < pressed + WATCH:
        status = read_json(paths.status_file) or {}
        line = flow_line(status)
        closed += "ЗАКРЫТО" in line
        if reached is None and (pool_of(status).get("mode") or "off") == goal:
            reached = time.time() - pressed
        if line != last:
            print(f"+{time.time() - pressed:4.0f} с: {line}", flush=True)
            last = line
        time.sleep(1)
    print(f"«ЗАКРЫТО» замеров: {closed}; режим {goal} в состоянии шлюза — "
          + (f"с +{reached:.0f} с" if reached is not None else "НЕ появился за 3 минуты"))
elif mode == "events":
    _cfg, paths = xgw()
    for ts, kind, detail in events_since(paths, arg(2, time.time() - 3600)):
        if kind == "freepool":
            print(f"{stamp(ts)} {NAME.sub('«<сервер>»', detail)}")
        elif kind == "apply" and "бесплатный пул" in detail:
            print(f"{stamp(ts)} применение: {applied_text(detail)}")
elif mode == "applies":
    _cfg, paths = xgw()
    since = arg(2, time.time() - 3600)
    rows = [(ts, applied_text(detail)) for ts, kind, detail in events_since(paths, since)
            if kind == "apply"]
    bad = sum(1 for _ts, detail in rows
              if "отклонён" in detail or "откат" in detail or "не поднялся" in detail)
    manual = [detail for _ts, detail in rows if "выбранный вручную сервер" in detail]
    print(f"применений с {stamp(since)}: {len(rows)}; ради выбранного вручную: {len(manual)} "
          f"({'; '.join(sorted(set(manual))) or '—'}); отказ или откат: {bad}")
elif mode == "rows":
    _cfg, paths = xgw()
    since = datetime.date.today().isoformat()
    try:
        conn = db(paths)
        rows = [dict(row) for row in conn.execute(
            "SELECT kind, key, SUM(up) AS up, SUM(down) AS down, SUM(billed) AS billed "
            "FROM usage WHERE day >= ? GROUP BY kind, key", (since,))]
        conn.close()
    except sqlite3.Error as exc:
        print(f"учёт в базе не читается: {type(exc).__name__}: {exc}")
        sys.exit(0)
    subs = sorted((row for row in rows if row["kind"] == "sub"), key=lambda row: str(row["key"]))
    for index, row in enumerate(subs, 1):
        print(f"подписка #{index}: ↓ {mb(row['down'])}, ↑ {mb(row['up'])}, учтено "
              f"{mb(row['billed'])}")
    for kind, label in (("pool", "бесплатные серверы"), ("direct", "напрямую"), ("wan", "WAN")):
        for row in rows:
            if row["kind"] == kind:
                print(f"{label}: ↓ {mb(row['down'])}, ↑ {mb(row['up'])}")
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, word in (
        ("учёт трафика: шаг не выполнен", "учёт трафика: шаг не выполнен"),
        ("учёт трафика устройств: предупреждений", "учёт трафика устройств:"),
        ("сервер бесплатного пула не закреплён", "сервер бесплатного пула не закреплён"),
        ("у всего дома закрыто", "у всего дома закрыто"),
        ("откат на last-good", "last-good"),
        ("шаг пула не выполнен", "бесплатный пул: шаг не выполнен"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | pool | route | state | flow | pinned | waitpin on|down|auto | "
          "watch on|back | events | applies | rows | log")
EOF
python3 -c "import hashlib;d=open('pincheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `c24fed24224601e3`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки:

```bash
cd "$HOME/xgw-pin" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units pool route state pinned; do sudo python3 -I pincheck.py $m; done | tee -a before.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; первая строка
`xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать, какая**; четыре
службы `active`; `route` — «совпадает с режимом: да»; `pinned` — «выбран вручную: нет (сервер
выбирает шлюз)» (в старом коде поля нет).

Если не так: первая строка `xgw pool` — «весь дом через бесплатные серверы» — выполнить
`sudo xgw pool mode observe`, подождать минуту и повторить шаг.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def set_free_pool_pin' src/xgw/managed.py && grep -q 'def set_pool_pin' src/xgw/actions.py && grep -q 'def pinned' src/xgw/freepool/traffic.py && grep -q '"freepool/pin"' src/xgw/watch/panel.py && grep -q 'function poolChoose' src/xgw/ui/app.js && grep -q 'def _xray' src/xgw/usage.py && echo "правка в коде: есть"; cd "$HOME/xgw-pin"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-pin/install-time.txt" && date +%s > "$HOME/xgw-pin/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-pin/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-pin/install.txt"; cd "$HOME/xgw-pin"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 3 минуты:

```bash
sleep 180; cd "$HOME/xgw-pin" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee after-install.txt; for m in units route state pinned rows; do sudo python3 -I pincheck.py $m; done | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I pincheck.py log | tee log-install.txt
```

Ожидается: `HEALTHY`, перехват включён, строки «Ожидает окна перезапуска» нет; четыре службы
`active`; `route` — «совпадает с режимом: да»; `pinned` — «выбран вручную: нет»; `rows` — строки
подписок и «WAN: …» (учёт продолжается); журнал: «учёт трафика: шаг не выполнен: 0»,
«Traceback: 0».

Если не так: не `HEALTHY` — подожди 2 минуты и повтори; снова нет — запиши и продолжай.

## 3. Наблюдение

Шаг 3.1. Только если в шаге 1.3 наблюдение было **выключено** (иначе — пропустить, записать «уже
было включено» и подождать 5 минут):

```bash
cd "$HOME/xgw-pin" && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; sleep 1800; sudo python3 -I pincheck.py pool | tee -a mode-on.txt
```

(Если терминал обрывает длинные команды — после первой строки выполни `sleep 110` 17 раз, затем
`sudo python3 -I pincheck.py pool`.)

Ожидается: «Наблюдение за бесплатным пулом включено: …»; через 30 минут — «пригодно» больше 1
(для проверки нужны хотя бы два допущенных сервера).

Если не так: «пригодно» 0 или 1 — подожди ещё 30 минут и повтори `pool`; снова не больше 1 — §5
пропустить («допущенных серверов меньше двух»), перейти к §4 и дальше.

## 4. Точность учёта подписок

Шаг 4.1. Пробная загрузка 30 МБ самим шлюзом (пункт 3 согласия):

```bash
cd "$HOME/xgw-pin" && sudo python3 -I pincheck.py rows | tee dl-before.txt; curl -s -o /dev/null -w 'загружено: %{size_download} байт за %{time_total} с, код %{http_code}\n' 'https://speed.cloudflare.com/__down?bytes=30000000' | tee dl.txt; sleep 130; sudo python3 -I pincheck.py rows | tee dl-after.txt
```

Ожидается: «загружено: 30000000 байт за … с, код 200»; по сравнению с `dl-before.txt`:
- у одной подписки «↓» выросло **не меньше чем на 29 МБ** (вся загрузка шла одним соединением
  через один сервер; раньше часть терялась при пересборке сервера между отсчётами);
- «WAN: ↓» выросло не меньше чем на 30 МБ.

Запиши разницы по каждой подписке и по WAN (в МБ).

Если не так: код не 200 — запиши и пропусти сравнение. Ни у одной подписки нет +29 МБ, но сумма
приростов всех подписок — 29 МБ и больше: «не по ожиданию — загрузка разделилась между
подписками», запиши разницы. Сумма меньше 29 МБ — **дефект «учёт подписок теряет трафик»**.

## 5. Сервер пула вручную (пункты 2 и 4 согласия)

Шаг 5.1. Страховочный таймер — **до** включения «всего дома»:

```bash
cd "$HOME/xgw-pin" && sudo systemd-run --on-active=30min --unit=xgw-pin-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-pin-guard.timer | head -3 | tee -a guard.txt
```

Ожидается: «Running timer as unit: xgw-pin-guard.timer» и строка таймера через ~30 минут.

Если не так: таймера нет — **стоп** для §5 (её пропустить, перейти к §6).

Шаг 5.2. Панель и кнопки в режиме наблюдения. Ссылка входа (в ней токен — **никуда не
записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком (окно не меньше 1280×800),
подожди 5 секунд, нажми вкладку **«Бесплатные серверы»**, подожди 5 секунд, снимок, **J5**.

Ожидается: `Выбрать: 0 | Автовыбор: 0` — пока через пул никто не идёт, выбирать нечего.

Если не так: «Выбрать» больше 0 в режиме наблюдения — **дефект «кнопка без трафика пула»**,
продолжай.

Шаг 5.3. Включение «всего дома» (нажимаешь ты):
1. На вкладке «Бесплатные серверы» нажми **«Весь дом через бесплатные»**.
2. Снимок; **J4** — `true | Пустить весь дом через бесплатные серверы? | Весь дом через
   бесплатные`.
3. Нажми в окне **«Весь дом через бесплатные»**.
4. **Сразу** (в течение 30 секунд) выполни:

```bash
cd "$HOME/xgw-pin" && date +%s > t-on.txt && sudo python3 -I pincheck.py watch on | tee watch-on.txt; for m in route pinned; do sudo python3 -I pincheck.py $m; done | tee house.txt
```

Ожидается (около 3 минут): «нажатие: …»; строки «+N с: режим on: сейчас через pool-XX-…
(XX), живых … из …; выбран вручную: нет»; «ЗАКРЫТО» замеров: 0; `route` — «последнее правило →
pool; несущий канал: есть; серверов в «pool»: N» (N — от 2 до 8), «совпадает с режимом: да».

Если не так: «сейчас через» не появилось за три минуты — раздел «Если что-то пошло не так», §5
пропустить.

Шаг 5.4. Выбор сервера, который **уже в работе** (в балансировщике):

**Действие:** в браузере обнови страницу (F5), подожди 5 секунд, вкладка «Бесплатные серверы»,
снимок, **J5** и **J6**.

Ожидается: J5 — `Выбрать: K | Автовыбор: 0` (K больше 0 — по кнопке у каждого допущенного);
J6 — «сейчас через: 1», «в работе: …» (больше 0, если в балансировщике больше одного сервера).

**Действие:** найди на снимке строку с зелёной меткой **«в работе»** (не «сейчас через») и
нажми у неё кнопку **«Выбрать»** справа внизу строки. Если кнопку мышью нажать не получается —
выполни **J7** как есть (с `"в работе"`); ответ «нажато». Сразу снимок: вверху справа должна
всплыть надпись «Выбран «…» (XX): трафик пула идёт через него, пока он отвечает; молчит — через
выбранный шлюзом» — запиши её без имени сервера. Затем:

```bash
cd "$HOME/xgw-pin" && date +%s > t-pin1.txt && sudo python3 -I pincheck.py waitpin on 120 | tee pin1.txt; for m in pinned flow; do sudo python3 -I pincheck.py $m; done | tee -a pin1.txt; sudo python3 -I pincheck.py events "$(cat t-pin1.txt)" | tee -a pin1.txt
```

Ожидается:
- `waitpin`: строки «+N с: … выбран вручную: …» и «достигнуто за N с» (N — до 60);
- `pinned`: «выбран вручную: xxxxxxxx…; допущен: да (XX); в «pool»: да; ведёт трафик: да»;
- `flow`: «… сейчас через pool-XX-… ; выбран вручную: держится»;
- события: «бесплатный пул: сервер «<сервер>» (XX) выбран вручную» и «бесплатный пул: весь дом
  идёт через «<сервер>» (XX) — выбран вручную».

**Действие:** обнови страницу (F5), вкладка «Бесплатные серверы», снимок, **J6**, **J5**.
Ожидается: J6 — «выбран вручную: 1»; J5 — «Автовыбор: 1»; на снимке у выбранной строки — метки
«выбран вручную» и «сейчас через», кнопка «Автовыбор».

Если не так: всплыла надпись «Такого сервера среди допущенных…» — запиши, это значит, что строка
не допущена: выбери другую строку с «в работе» (один раз). «НЕ достигнуто за 120 с» — **дефект
«выбранный не закрепился»**: запиши строки `pinned` и `flow`, продолжай.

Шаг 5.5. Выбор допущенного сервера, которого **нет в балансировщике** (метка «допущен» без «в
работе»). Если J6 в шаге 5.4 показал «допущен: 0» — шаг пропусти («все допущенные уже в
работе»).

**Действие:** найди строку с серой меткой **«допущен»** и кнопкой «Выбрать», нажми «Выбрать»
(или **J7**, заменив `"в работе"` на `"допущен"`). Снимок, всплывшая надпись — запиши без имени.
Затем:

```bash
cd "$HOME/xgw-pin" && date +%s > t-pin2.txt && sudo python3 -I pincheck.py waitpin on 240 | tee pin2.txt; for m in pinned flow route; do sudo python3 -I pincheck.py $m; done | tee -a pin2.txt; sudo python3 -I pincheck.py applies "$(cat t-pin2.txt)" | tee -a pin2.txt; sudo python3 -I pincheck.py events "$(cat t-pin2.txt)" | tee -a pin2.txt
```

Ожидается:
- `waitpin`: сначала, возможно, «выбран вручную: не отвечает — ведёт выбранный шлюзом» (сервер
  ещё добавляется в балансировщик и проверяется ядром), затем «держится»; «достигнуто за N с»
  (N — до 240);
- `pinned`: «… допущен: да (XX); в «pool»: да; ведёт трафик: да»;
- `route`: «серверов в «pool»: N» (N — не больше 8), «совпадает с режимом: да»;
- `applies`: «ради выбранного вручную: 1 (бесплатный пул: выбранный вручную сервер: применено …)»
  (через API без перезапуска или с перезапуском Xray — записать), «отказ или откат: 0»;
- события: «сервер «<сервер>» (XX) выбран вручную», затем «весь дом идёт через «<сервер>» (XX)
  — выбран вручную» (возможно, раньше него — «…: выбранный вручную не отвечает — сервер выбирает
  шлюз», пока сервер добавлялся).

Если не так: «НЕ достигнуто за 240 с» — запиши строки `pinned`, `flow`, `applies`: если
«в «pool»: нет» — **дефект «выбранный не попал в состав»**; если «в «pool»: да», а «ведёт
трафик: нет» и в `flow` «не отвечает» — сервер не ответил на пробы ядра (не дефект, запиши
«выбранный молчит»); продолжай.

Шаг 5.6. Автовыбор и команда.

**Действие:** в браузере обнови страницу, вкладка «Бесплатные серверы», нажми у выбранной строки
**«Автовыбор»**. Снимок: всплыла надпись «Сервер бесплатного пула снова выбирает шлюз». Затем:

```bash
cd "$HOME/xgw-pin" && date +%s > t-auto.txt && sudo python3 -I pincheck.py waitpin auto 60 | tee auto.txt; for m in pinned flow; do sudo python3 -I pincheck.py $m; done | tee -a auto.txt; sudo xgw pool pin 12345 2>&1 | tee -a auto.txt; echo "код $?" | tee -a auto.txt; sudo xgw pool pin auto 2>&1 | tee -a auto.txt; sudo python3 -I pincheck.py events "$(cat t-auto.txt)" | tee -a auto.txt
```

Ожидается:
- `waitpin auto`: «… выбран вручную: нет», «достигнуто за N с»;
- `pinned`: «выбран вручную: нет (сервер выбирает шлюз)»; `flow` — «сейчас через» **тот же**
  тег, что в конце шага 5.5 (автовыбор не прыгает на другой живой сервер);
- `xgw pool pin 12345` — «ошибка: Такого сервера среди допущенных к трафику нет …» (начало id
  короче 6 знаков); строка «код …» — из-за `tee` там 0, это норма;
- `xgw pool pin auto` — «Сервер бесплатного пула снова выбирает шлюз. Демон применит выбор на
  ближайшем шаге»;
- события: «бесплатный пул: выбор сервера вручную снят — сервер выбирает шлюз» (одно — повторный
  `pin auto` события не добавляет).

Шаг 5.7. Возврат режима подписок — меткой вверху:
1. Нажми **метку вверху справа** («Через бесплатные серверы ▾»).
2. Снимок; **J4** — `true | Вернуть режим подписок? | Вернуть режим подписок`.
3. Нажми в окне **«Вернуть режим подписок»**.
4. **Сразу** выполни:

```bash
cd "$HOME/xgw-pin" && sudo python3 -I pincheck.py watch back | tee watch-back.txt; sudo systemctl stop xgw-pin-guard.timer; systemctl list-timers --all --no-pager xgw-pin-guard.timer | head -3 | tee guard-off.txt; for m in route state; do sudo python3 -I pincheck.py $m; done | tee back.txt
```

Ожидается: «нажатие: …»; «режим observe: через пул никто»; «ЗАКРЫТО» замеров: 0; таймер больше
не в списке («0 timers listed»); `route` — «последнее правило → auto; несущий канал: нет;
серверов в «pool»: 0», «совпадает с режимом: да».

**Действие в браузере:** обнови страницу, вкладка «Бесплатные серверы», **J5** — `Выбрать: 0 |
Автовыбор: 0`.

## 6. Секреты

```bash
cd "$HOME/xgw-pin" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt
```

Ожидается: `0`. Если больше — **дефект** (строки журнала в отчёт не копировать).

## 7. Режим как до проверки и итог

Шаг 7.1. Если в шаге 1.3 наблюдение было **выключено** — **действие в браузере:** вкладка
«Бесплатные серверы» → **«Выключить»**, снимок (кнопка сменилась на «Включить наблюдение»). Было
включено — ничего не менять, записать «оставлено включённым».

Шаг 7.2. Итог:

```bash
sleep 60; cd "$HOME/xgw-pin" && date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units pool route state pinned rows; do sudo python3 -I pincheck.py $m; done | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I pincheck.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4, строки «Ожидает окна
перезапуска» нет; четыре службы `active`; режим — как был до проверки; `route` — «совпадает с
режимом: да»; `pinned` — «выбран вручную: нет»; журнал: «учёт трафика: шаг не выполнен: 0»,
«сервер бесплатного пула не закреплён: 0», «у всего дома закрыто: 0», «откат на last-good: 0»,
«Traceback: 0».

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- В режиме «весь дом» пропал интернет или доступ, или заказчик не отвечает **2 минуты** —
  **сразу**: `sudo xgw pool mode observe`, `sudo xgw pool pin auto`, затем
  `sudo systemctl stop xgw-pin-guard.timer` (ошибка «not loaded» — норма). Записать время и строки
  `sudo python3 -I pincheck.py flow` и `sudo python3 -I pincheck.py route`. Дальше — §6, §7 и
  отчёт. «Весь дом» больше не включать.
- Сработал страховочный таймер (через 30 минут режим вернулся сам) — записать время, выполнить
  `sudo xgw pool pin auto` и продолжить с §6.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.
- Браузер не открывает панель или кнопки не нажимаются (и J7 не помогает) — снимок, сообщить
  заказчику и попросить нажать то же самое вручную; в отчёте пометить «нажато заказчиком».

## 8. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-pin-<ДАТА>.md` в клоне (`<ДАТА>` — дата
начала проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, сервер бесплатного пула вручную» и
`git push` в `freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и
подписок, адресов, доменов, токена и строк журнала. Шаблон (заполни каждую ячейку; пропущенное —
«не выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — сервер бесплатного пула вручную и точный учёт подписок

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
pincheck.py: <сумма>. Наблюдение до проверки: <…>. Ядра: Xray <…>, sing-box <…>.
Исполнитель: <модель>; нажатия и снимки — управляемым браузером <да/частично>.

## Итог
| Загрузка 30 МБ: наибольший прирост подписки / сумма подписок / WAN, МБ | Кнопки в наблюдении (J5) | Выбор «в работе»: закрепился за, с | Выбор «допущен»: в состав / закрепился за, с / применение | Автовыбор: без прыжка / событие | `xgw pool pin` | Возврат меткой |
|---|---|---|---|---|---|---|
| <+30.1 / +30.4 / +31> | <0 / 0> | <N> | <да / N / через API> | <да / да> | <да> | <да> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 наблюдение | … | … |
| 4.1 загрузка 30 МБ | … | … |
| 5.1 страховка | … | … |
| 5.2 кнопки в наблюдении | … | … |
| 5.3 включение | … | … |
| 5.4 выбор «в работе» | … | … |
| 5.5 выбор «допущен» | … | … |
| 5.6 автовыбор и команда | … | … |
| 5.7 возврат меткой | … | … |
| 6 секреты | … | … |
| 7 итог | … | … |

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-pin/…); результаты J1–J7; что видно на
  снимках словами; всплывшие надписи без имён; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
