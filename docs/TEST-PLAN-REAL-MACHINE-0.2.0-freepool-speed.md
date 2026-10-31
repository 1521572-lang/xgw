# Проверка XGW 0.2.0: скорость серверов бесплатного пула и выбор по скорости

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
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J1–J12) — выполни её в консоли
   страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-speed/…` (так написано в командах). Время шага —
   по выводу `date` в команде, не по памяти.
5. **Метка времени — до нажатия.** Где в шаге есть команда «Метка», выполни её **перед**
   нажатием в браузере, а команду проверки — **после**: проверка ищет события начиная с метки (в
   прошлой проверке метку брали после нажатия, и события шага выпадали).
6. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
7. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
8. Экземпляр этого ТЗ держи в `$HOME/xgw-speed/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2.
9. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `speedcheck.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
10. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши
    дословно строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
    «Наблюдения», со словом «предположение».

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.29 и sing-box
1.14.4, принятые шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 273)

1. **Скорость серверов пула.** Пока через бесплатные серверы идёт трафик (весь дом или
   устройства), шлюз замеряет скорость серверов пула в работе — так же, как серверы подписки
   (загрузка до 10 МБ, не дольше 8 с): новый сервер — сразу, по одному за шаг демона (~20 с),
   повторно — раз в 6 часов.
2. **Выбор по скорости.** Трафик пула ведёт самый быстрый живой сервер. Пока замерены не все,
   выбор предварительный: замеренный сервер быстрее на 30 % сменяет закреплённый сразу; когда
   замерены все — только если закреплённый продержался 60 минут. Выбранный вручную главнее
   скорости; после «Автовыбора» бывший выбранный не сменяется сразу.
3. **Видно:** скорость — в главной карточке, в строках серверов «в работе» на вкладке «Бесплатные
   серверы» (слева от задержки), в синеватой полосе вкладки, в `sudo xgw pool` и в событии смены
   сервера («…, 25 Мбит/с — быстрее, чем «…» (8,5 Мбит/с)»). Трафик замеров учитывается в
   карточке «Трафик» как трафик бесплатных серверов.

### Главное правило безопасности

Пока включён «весь дом»: пропал интернет на машине, заказчик говорит, что пропал доступ, или не
отвечает на вопрос **2 минуты** — **сразу** раздел «Если что-то пошло не так» (вернуть режим
подписок командой). Перед включением «всего дома» ставится страховочный таймер: через 40 минут
он сам вернёт режим подписок.

### Что где на экране панели (для снимков)

- **Верх страницы**: слева — «XGW шлюз»; справа — **метка состояния** («Серверы в порядке»,
  «Через бесплатные серверы ▾»…). В режиме «весь дом» метка — кнопка возврата.
- **Главная карточка** (левая колонка, вверху): строка «Бесплатный сервер» — имя, страна,
  **скорость** («· 25 Мбит/с») и задержка («· 85 мс»).
- **Правая колонка**: вкладки **«Подписки»** и **«Бесплатные серверы»**. На вкладке «Бесплатные
  серверы» вверху справа — «Опросить источники», «Весь дом через бесплатные» (во «всём доме» —
  «Вернуть режим подписок»), «Выключить»; ниже — серый текст, синеватая полоса «Весь дом через
  бесплатные серверы — сервер «…» (XX), 25 Мбит/с, задержка … мс; живых … из …», затем блоки
  источников со строками серверов. У строки — точка, имя, метки («сейчас через», «в работе»,
  «допущен», протокол, страна), **справа — скорость жирным и задержка**, под ними — серый текст,
  справа внизу строки — кнопка «Выбрать» или «Автовыбор».
- **Окно подтверждения** — по центру: заголовок, текст, «Отмена» и кнопка действия справа.

### Проверки JavaScript (в консоли страницы панели)

- **J1 — метка вверху:**
  `(() => { const c = document.getElementById("chip"); return [c.tagName, c.textContent.trim(), c.disabled].join(" | "); })()`
- **J4 — окно подтверждения:**
  `(() => { const d = document.getElementById("confirm-dialog"); return [d.open, document.getElementById("confirm-title").textContent, document.getElementById("confirm-yes").textContent].join(" | "); })()`
- **J5 — кнопки строк пула:**
  `(() => { const b = [...document.querySelectorAll("#pool-groups button.choose")].map((x) => x.textContent); return "Выбрать: " + b.filter((t) => t === "Выбрать").length + " | Автовыбор: " + b.filter((t) => t === "Автовыбор").length; })()`
- **J6 — метки строк пула:**
  `(() => { const t = [...document.querySelectorAll("#pool-groups .tag")].map((x) => x.textContent); return ["выбран вручную: " + t.filter((x) => x === "выбран вручную").length, "сейчас через: " + t.filter((x) => x === "сейчас через").length, "в работе: " + t.filter((x) => x === "в работе").length, "допущен: " + t.filter((x) => x === "допущен").length].join(" | "); })()`
- **J8 — скорость в строках пула:**
  `(() => { const s = [...document.querySelectorAll("#pool-groups .speed")]; return "скоростей в строках: " + s.length + " | пример: " + (s.length ? s[0].textContent + " — " + s[0].title.replace(/\d\d:\d\d/, "ЧЧ:ММ") : "—"); })()`
- **J9 — скорость в главной карточке:**
  `(() => { const n = document.getElementById("current-name").textContent; const m = n.match(/ · ([\d,]+ Мбит\/с)/); return [document.getElementById("current-label").textContent, m ? m[1] : "скорости нет", / · \d+ мс$/.test(n) ? "задержка есть" : "задержки нет"].join(" | "); })()`
- **J10 — скорость в синеватой полосе вкладки:**
  `(() => { const m = document.getElementById("pool-flow").textContent.match(/, ([\d,]+ Мбит\/с), задержка \d+ мс/); return m ? "скорость в полосе: " + m[1] : "скорости в полосе нет"; })()`
- **J11 — нажать «Выбрать» у самого медленного замеренного сервера, кроме того, через который
  идёт трафик:**
  `(() => { const num = (t) => parseFloat(t.replace(",", ".")); const rows = [...document.querySelectorAll("#pool-groups li")].filter((li) => li.querySelector(".speed") && (li.querySelector("button.choose") || {}).textContent === "Выбрать" && ![...li.querySelectorAll(".tag")].some((t) => t.textContent === "сейчас через")); if (!rows.length) return "нет замеренных строк с «Выбрать», кроме текущей"; const row = rows.reduce((a, b) => (num(a.querySelector(".speed").textContent) <= num(b.querySelector(".speed").textContent) ? a : b)); row.scrollIntoView({ block: "center" }); row.querySelector("button.choose").click(); return "нажато у строки со скоростью " + row.querySelector(".speed").textContent + " (подходящих строк: " + rows.length + ")"; })()`
- **J12 — нажать «Автовыбор»** (запасной путь, если кнопку не получается нажать мышью):
  `(() => { const b = [...document.querySelectorAll("#pool-groups button.choose")].find((x) => x.textContent === "Автовыбор"); if (!b) return "кнопки «Автовыбор» нет"; b.scrollIntoView({ block: "center" }); b.click(); return "нажато"; })()`

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, `reboot`, сон машины —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh`; ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`,
  `sysctl -w`, `apt`; команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`. `systemd-run` и
  `systemctl stop` — только для страховочного таймера `xgw-speed-guard`. `sudo xgw pool mode …` —
  только в шаге 3.1 (`observe`), в «Если не так» шагов, где это написано, и в разделе «Если
  что-то пошло не так». `sudo xgw pool pin …` — только в разделе «Если что-то пошло не так».
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`). Загрузок из терминала нет.
  Сайты источников, файлы списков на GitHub, сайты проверки IP, страны и скорости — не открывать.
- В панели нажимать **только** то, что написано в шагах: вкладки, «Весь дом через бесплатные» и
  кнопку подтверждения в его окне, «Выбрать» (через J11) и «Автовыбор» на строках бесплатных
  серверов, метку вверху и кнопки её окна, «Выключить». **Не нажимать**: кнопку питания,
  «Замерить скорость», «Проверить запасные», «Обновить», «Опросить источники», переключатели
  Tailscale, «Ядра», «Проверить сеть», «Выбрать» и «Автовыбор» у серверов **подписок**, строки
  устройств, «Добавить», «Убрать».
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, код XGW. Печатать `config.toml`, `panel.json`, рабочие конфиги
  Xray и sing-box, файлы в `/var/lib/xgw/freepool`, базу `/var/lib/xgw/state.db`, полный вывод
  `sudo xgw pool` и `sudo xgw traffic`. Коммитить что-либо, кроме файла отчёта (§7). Снимки
  экрана в git не добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, токен из ссылки
  панели, MAC, имена пользователей (→ `<user>`), внешние IP, адреса и домены подписок, IP,
  домены и ссылки серверов VPN, строки журнала. Можно: коды стран, теги вида `pool-de-1a2b`,
  начало id сервера пула (8 знаков, как печатает помощник), скорости, задержки, надписи панели
  без имён, счётчики, мегабайты, статусы, времена, строки помощника.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю новую возможность — шлюз замеряет скорость бесплатных серверов и пускает трафик через
самый быстрый. Нажатия в панели и осмотр экрана я делаю сам, в управляемом браузере. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Если наблюдение за бесплатными серверами выключено, я включу его и подожду 30 минут.
(3) Я включу «весь дом через бесплатные серверы» примерно на 25 минут (страховочный таймер
вернёт режим подписок через 40 минут сам). За это время шлюз скачает через каждый бесплатный
сервер в работе пробный файл до 10 МБ (до 8 серверов — до 80 МБ, квоту подписок это не тратит),
я выберу вручную самый медленный сервер, верну автовыбор и затем режим подписок. Интернет дома в
это время идёт через бесплатные серверы и при смене сервера может прерываться на несколько
секунд. Если интернет или доступ пропадут — сразу скажите.
(4) В конце верну наблюдение в то состояние, в каком оно было до проверки.
Проверка займёт около часа с четвертью. Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 при выключенном наблюдении или против 3 — §4 пропустить (в
отчёте: «скорость пула не проверялась»). Против 4 — §6 без смены режима. В отчёте у
пропущенного — «не выполнялся». Если ответа нет — не начинать, спросить ещё раз.

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-speed" && chmod 700 "$HOME/xgw-speed" && cd "$HOME/xgw-speed" && cat > speedcheck.py <<'EOF'
"""XGW 0.2.0, бесплатный пул: замер скорости серверов пула и выбор по скорости — помощник
проверки. Только читает: состояние XGW (/run/xgw), базу состояния (/var/lib/xgw/state.db —
только чтение), рабочий конфиг Xray, настройки и журнал со стандартного ввода — счётчики,
мегабайты, скорости, коды стран, теги pool-<страна>-<начало id>, начало id (8 знаков), итоги и
да/нет; без имён серверов, устройств и подписок, ссылок и ключей. Время — секунды с 1970
(date +%s). Режимы: units, pool, route, state, flow, speed, waitspeed, pinned, waitpin,
holdwatch, watch on|back, events, measured, poolbytes, spent, rows, log."""
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
LIB = os.environ.get("SPEEDCHECK_LIB", "/opt/xgw/lib")
NAME = re.compile("«[^»]*»")
HOST = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")
MARKS = {"on": "бесплатный пул: весь дом через бесплатные серверы",
         "back": "режим подписок возвращён"}
GOALS = {"on": "on", "back": "observe"}
MANUAL = {"on": "держится", "down": "не отвечает — ведёт выбранный шлюзом", "": "нет"}
WATCH = 180
SETTLE = 90  # учёт трафика пишет в базу раз в минуту: свежие замеры ещё не записаны


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


def rate(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "скорость —"
    return (f"{value:.0f}" if value >= 10 else f"{value:.1f}".replace(".", ",")) + " Мбит/с"


def pool_of(status):
    return status.get("free_pool") if isinstance(status.get("free_pool"), dict) else {}


def flow_of(status):
    flow = pool_of(status).get("traffic")
    return flow if isinstance(flow, dict) else None


def flow_line(status):
    pool = pool_of(status)
    head = f"режим {pool.get('mode') or 'off'}"
    flow = flow_of(status)
    if flow is None:
        return head + (": подключаются" if pool.get("mode") == "on" else ": через пул никто")
    manual = MANUAL.get(flow.get("manual") or "", "?")
    if flow.get("closed"):
        return f"{head}: ЗАКРЫТО; выбран вручную: {manual}"
    return (f"{head}: сейчас через {flow.get('tag') or '—'} ({flow.get('country') or '—'}), "
            f"{rate(flow.get('mbps'))}; живых {flow.get('alive')} из {flow.get('members')}; "
            f"выбран вручную: {manual}")


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


def admitted_ids(cfg, paths):
    try:
        from xgw.freepool import traffic

        return [item.node.fingerprint for item in traffic.admitted(cfg, paths, time.time())]
    except Exception as exc:  # помощник только смотрит: сбой чтения — строкой, без падения
        print(f"допущенные не прочитаны: {type(exc).__name__}")
        return []


def speed_rows(cfg, paths):
    flow = flow_of(read_json(paths.status_file) or {}) or {}
    ids = admitted_ids(cfg, paths)
    rows = []
    for item in flow.get("servers") or []:
        if not isinstance(item, dict):
            continue
        prefix = str(item.get("id") or "")
        rows.append({
            "tag": str(item.get("tag") or ""), "alive": bool(item.get("alive")),
            "mbps": item.get("mbps"), "delay": item.get("delay_ms") or 0,
            "admitted": bool(prefix) and any(full.startswith(prefix) for full in ids),
            "current": bool(flow.get("tag")) and item.get("tag") == flow.get("tag"),
        })
    return flow, rows


def measured_ok(row):
    value = row.get("mbps")
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def speed_records(paths):
    try:
        conn = db(paths)
        row = conn.execute("SELECT value FROM meta WHERE key = 'pool_speed'").fetchone()
        conn.close()
    except sqlite3.Error as exc:
        print(f"замеры в базе не читаются: {type(exc).__name__}")
        return {}
    try:
        records = json.loads(row["value"]) if row and row["value"] else {}
    except ValueError:
        return {}
    if not isinstance(records, dict):
        return {}
    return {str(key): value for key, value in records.items() if isinstance(value, dict)}


def usage_rows(paths):
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
    return rows


def pool_down(paths):
    return sum(int(row["down"] or 0) for row in usage_rows(paths) if row["kind"] == "pool")


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
elif mode == "speed":
    cfg, paths = xgw()
    flow, rows = speed_rows(cfg, paths)
    if not rows:
        print("серверов «pool» в сводке нет (через пул никто или подключаются)")
        sys.exit(0)
    for row in rows:
        print(f"{row['tag']}: {'жив' if row['alive'] else 'молчит'}, {rate(row['mbps'])}, "
              f"задержка {row['delay']} мс, допущен: {'да' if row['admitted'] else 'нет'}"
              + ("  ← сейчас через него" if row["current"] else ""))
    live = [row for row in rows if row["alive"] and row["admitted"]]
    done = [row for row in live if measured_ok(row)]
    current = next((row for row in rows if row["current"]), None)
    held = current["mbps"] if current is not None and measured_ok(current) else None
    gain = cfg.speed.gain_pct
    best = max((row["mbps"] for row in done), default=None)
    ahead = [row for row in done if not row["current"] and held is not None
             and row["mbps"] > held and row["mbps"] >= held * (1 + gain / 100)]
    print(f"живых допущенных: {len(live)}, замерено: {len(done)}; закреплённый: {rate(held)}; "
          f"самый быстрый живой: {rate(best)}; быстрее закреплённого на {gain} % и больше: "
          + (str(len(ahead)) if held is not None else "закреплённый не замерен"))
elif mode == "waitspeed":
    cfg, paths = xgw()
    limit = arg(2, 420.0)
    start, last = time.time(), None
    while True:
        flow, rows = speed_rows(cfg, paths)
        live = [row for row in rows if row["alive"] and row["admitted"]]
        done = [row for row in live if measured_ok(row)]
        line = (f"сейчас через {flow.get('tag') or '—'}, {rate(flow.get('mbps'))}; замерено "
                f"{len(done)} из {len(live)} живых допущенных")
        if line != last:
            print(f"+{time.time() - start:4.0f} с: {line}", flush=True)
            last = line
        if live and len(done) == len(live):
            print(f"все живые допущенные замерены за {time.time() - start:.0f} с")
            break
        if time.time() - start > limit:
            print(f"НЕ все замерены за {limit:.0f} с")
            break
        time.sleep(5)
elif mode == "pinned":
    cfg, paths = xgw()
    pin = getattr(getattr(cfg, "managed", None), "free_pool_pin", "")
    flow = flow_of(read_json(paths.status_file) or {}) or {}
    if not pin:
        print("выбран вручную: нет (сервер выбирает шлюз)")
    else:
        leads = pin.startswith(tag_hex(flow.get("tag")) or "-")
        print(f"выбран вручную: {pin[:8]}…; ведёт трафик: {'да' if leads else 'нет'}")
elif mode == "waitpin":
    _cfg, paths = xgw()
    goal = sys.argv[2] if len(sys.argv) > 2 else "on"
    limit = arg(3, 240.0)
    start, last = time.time(), None
    while True:
        status = read_json(paths.status_file) or {}
        line = flow_line(status)
        if line != last:
            print(f"+{time.time() - start:4.0f} с: {line}", flush=True)
            last = line
        flow = flow_of(status) or {}
        if (flow.get("manual") or "") == ("" if goal == "auto" else goal):
            print(f"достигнуто за {time.time() - start:.0f} с")
            break
        if time.time() - start > limit:
            print(f"НЕ достигнуто за {limit:.0f} с")
            break
        time.sleep(2)
elif mode == "holdwatch":
    _cfg, paths = xgw()
    limit = arg(2, 180.0)
    start = time.time()
    last = (flow_of(read_json(paths.status_file) or {}) or {}).get("tag")
    changes = 0
    print(f"сейчас через {last or '—'}; смотрю {limit:.0f} с", flush=True)
    while time.time() - start < limit:
        time.sleep(5)
        tag = (flow_of(read_json(paths.status_file) or {}) or {}).get("tag")
        if tag != last:
            changes += 1
            print(f"+{time.time() - start:4.0f} с: смена → {tag or '—'}", flush=True)
            last = tag
    print(f"смен сервера за {limit:.0f} с: {changes}")
elif mode == "watch":
    which = sys.argv[2] if len(sys.argv) > 2 else "on"
    _cfg, paths = xgw()
    mark, goal = MARKS.get(which, MARKS["on"]), GOALS.get(which, "on")
    start = arg(3, time.time() - 120)
    deadline, pressed = time.time() + 600, None
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
elif mode == "measured":
    _cfg, paths = xgw()
    since = arg(2, time.time() - 3600)
    found = sorted((float(value.get("ts") or 0), key, value)
                   for key, value in speed_records(paths).items()
                   if float(value.get("ts") or 0) >= since)
    failed = [value for _ts, _key, value in found if not measured_ok(value)]
    total = sum(int(value.get("bytes") or 0) for _ts, _key, value in found)
    print(f"серверов, замеренных с {stamp(since)}: {len(found)}; неудачных: {len(failed)}; "
          f"скачано их последними замерами: {mb(total)}")
    for ts, key, value in found:
        why = HOST.sub("<адрес>", str(value.get("error") or ""))[:80]
        print(f"  {stamp(ts)} {key[:8]}…: {rate(value.get('mbps'))}, {mb(value.get('bytes'))} "
              f"за {float(value.get('seconds') or 0):.1f} с"
              + (" (канал был занят)" if value.get("busy") else "")
              + (f" — {why}" if why and not measured_ok(value) else ""))
elif mode == "poolbytes":
    _cfg, paths = xgw()
    print(pool_down(paths))
elif mode == "spent":
    _cfg, paths = xgw()
    since, before = arg(2, time.time() - 3600), arg(3, 0.0)
    upto = time.time() - SETTLE
    total = sum(int(value.get("bytes") or 0) for value in speed_records(paths).values()
                if since <= float(value.get("ts") or 0) <= upto)
    grown = pool_down(paths) - before
    print(f"скачано замерами с {stamp(since)} по {stamp(upto)}: {mb(total)}; «бесплатные "
          f"серверы» ↓ за это время выросло на {mb(grown)}; замеры учтены: "
          f"{'да' if total > 0 and grown >= total else 'НЕТ' if total > 0 else 'замеров нет'}")
elif mode == "rows":
    _cfg, paths = xgw()
    rows = usage_rows(paths)
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
    measures = [line for line in lines if "замер скорости pool-" in line]
    print(f"строк журнала: {len(lines)}")
    print(f"замеров серверов пула: {len(measures)}; из них не удались: "
          f"{sum(1 for line in measures if 'не удался' in line)}")
    for label, word in (
        ("сервер бесплатного пула не закреплён", "сервер бесплатного пула не закреплён"),
        ("у всего дома закрыто", "у всего дома закрыто"),
        ("откат на last-good", "last-good"),
        ("шаг пула не выполнен", "бесплатный пул: шаг не выполнен"),
        ("учёт трафика: шаг не выполнен", "учёт трафика: шаг не выполнен"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | pool | route | state | flow | speed | waitspeed | pinned | "
          "waitpin on|down|auto | holdwatch | watch on|back | events | measured | poolbytes | "
          "spent | rows | log")
EOF
python3 -c "import hashlib;d=open('speedcheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `a7dc0cc4c3a4579f`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки (на старом коде — только режимы, которые у него есть):

```bash
cd "$HOME/xgw-speed" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units pool route state pinned; do sudo python3 -I speedcheck.py $m; done | tee -a before.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; первая строка
`xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать, какая**; четыре
службы `active`; `route` — «совпадает с режимом: да»; `pinned` — «выбран вручную: нет (сервер
выбирает шлюз)».

Если не так: первая строка `xgw pool` — «весь дом через бесплатные серверы» — выполнить
`sudo xgw pool mode observe`, подождать минуту и повторить шаг. `pinned` — «выбран вручную:
xxxxxxxx…» (остался выбор с прошлой проверки) — записать и продолжать.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def _pool_speed_step' src/xgw/daemon.py && grep -q 'def _pool_choice' src/xgw/daemon.py && grep -q 'POOL_SPEED_META = "pool_speed"' src/xgw/daemon.py && grep -q 'speed.mbps_text' src/xgw/freepool/traffic.py && grep -q 'function poolSpeed' src/xgw/ui/app.js && echo "правка в коде: есть"; cd "$HOME/xgw-speed"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-speed/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-speed/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-speed/install.txt"; cd "$HOME/xgw-speed"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 3 минуты:

```bash
sleep 180; cd "$HOME/xgw-speed" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee after-install.txt; for m in units route state pinned measured rows; do sudo python3 -I speedcheck.py $m; done | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I speedcheck.py log | tee log-install.txt
```

Ожидается: `HEALTHY`, перехват включён, строки «Ожидает окна перезапуска» нет; четыре службы
`active`; `route` — «совпадает с режимом: да»; `pinned` — «выбран вручную: нет»; `measured` —
«серверов, замеренных с …: 0» (через пул никто не идёт — замеров нет); `rows` — строки подписок и
«WAN: …»; журнал: «замеров серверов пула: 0», «Traceback: 0».

Если не так: не `HEALTHY` — подожди 2 минуты и повтори; снова нет — запиши и продолжай.

## 3. Наблюдение

Шаг 3.1. Только если в шаге 1.3 наблюдение было **выключено** (иначе — пропустить, записать «уже
было включено» и подождать 5 минут):

```bash
cd "$HOME/xgw-speed" && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; sleep 1800; sudo python3 -I speedcheck.py pool | tee -a mode-on.txt
```

(Если терминал обрывает длинные команды — после первой строки выполни `sleep 110` 17 раз, затем
`sudo python3 -I speedcheck.py pool`.)

Ожидается: «Наблюдение за бесплатным пулом включено: …»; через 30 минут — «пригодно» больше 1
(для проверки нужны хотя бы два допущенных сервера).

Если не так: «пригодно» 0 или 1 — подожди ещё 30 минут и повтори `pool`; снова не больше 1 — §4
пропустить («допущенных серверов меньше двух»), перейти к §5.

## 4. Скорость серверов пула (пункты 2 и 3 согласия)

Шаг 4.1. Страховочный таймер — **до** включения «всего дома»:

```bash
cd "$HOME/xgw-speed" && sudo systemd-run --on-active=40min --unit=xgw-speed-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-speed-guard.timer | head -3 | tee -a guard.txt
```

Ожидается: «Running timer as unit: xgw-speed-guard.timer» и строка таймера через ~40 минут.

Если не так: таймера нет — **стоп** для §4 (её пропустить, перейти к §5).

Шаг 4.2. Панель. Ссылка входа (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком (окно не меньше 1280×800),
подожди 5 секунд, нажми вкладку **«Бесплатные серверы»**, подожди 5 секунд, снимок, **J8**.

Ожидается: `скоростей в строках: 0 | пример: —` — пока через пул никто не идёт, замеров нет.

Если не так: скоростей больше 0 — запиши «не по ожиданию» и продолжай.

Шаг 4.3. Включение «всего дома» и первые замеры.
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-speed" && date +%s > t-on.txt && sudo python3 -I speedcheck.py poolbytes > pool-before.txt && echo "метка записана: $(date '+%T'), пул до: $(cat pool-before.txt) байт"
```

2. На вкладке «Бесплатные серверы» нажми **«Весь дом через бесплатные»**.
3. Снимок; **J4** — `true | Пустить весь дом через бесплатные серверы? | Весь дом через
   бесплатные`.
4. Нажми в окне **«Весь дом через бесплатные»**.
5. **Сразу** выполни (около 3 минут на `watch` и до 7 минут на `waitspeed`):

```bash
cd "$HOME/xgw-speed" && sudo python3 -I speedcheck.py watch on "$(cat t-on.txt)" | tee watch-on.txt; sudo python3 -I speedcheck.py waitspeed 420 | tee speed-wait.txt; for m in speed route; do sudo python3 -I speedcheck.py $m; done | tee speed-on.txt; sudo python3 -I speedcheck.py measured "$(cat t-on.txt)" | tee -a speed-on.txt; sudo python3 -I speedcheck.py events "$(cat t-on.txt)" | tee events-on.txt
```

Ожидается:
- `watch`: «нажатие: …»; строки «+N с: режим on: сейчас через pool-XX-… (XX), …; живых … из …;
  выбран вручную: нет»; «ЗАКРЫТО» замеров: 0;
- `waitspeed`: строки «+N с: сейчас через pool-XX-…, …; замерено K из N живых допущенных», где K
  растёт примерно на 1 каждые 20–30 секунд; итог — «все живые допущенные замерены за N с» (N —
  до 420);
- `speed`: по строке на сервер «pool-XX-…: жив, 12 Мбит/с, задержка … мс, допущен: да» (у живых
  допущенных — скорость, не «скорость —»), у одной — «← сейчас через него»; итоговая строка
  «живых допущенных: N, замерено: N; закреплённый: A Мбит/с; самый быстрый живой: B Мбит/с;
  быстрее закреплённого на 30 % и больше: 0»;
- `route` — «последнее правило → pool; несущий канал: есть; серверов в «pool»: N» (N — от 2 до
  8), «совпадает с режимом: да»;
- `measured` — «серверов, замеренных с …: N; неудачных: …» и строки «ЧЧ:ММ:СС xxxxxxxx…: 12
  Мбит/с, 10.0 МБ за … с» (у неудачных — «скорость —» и причина);
- события: «бесплатный пул: весь дом через бесплатные серверы…», затем «бесплатный пул: весь дом
  идёт через «<сервер>» (XX)» (первый выбор — по задержке, скорости ещё нет) и, возможно, одно
  или несколько «бесплатный пул: весь дом идёт через «<сервер>» (XX), A Мбит/с — быстрее, чем
  «<сервер>» (…)» — смены на более быстрый, пока идут первые замеры.

Если не так: «сейчас через» не появилось за три минуты — раздел «Если что-то пошло не так», §4
дальше пропустить. «НЕ все замерены за 420 с» — запиши строки `waitspeed`, `speed`, `measured` и
продолжай. В итоговой строке `speed` «быстрее закреплённого…» не 0 — запиши строки `speed` и
`events-on.txt` целиком («не по ожиданию»), продолжай. Все замеры неудачные — **дефект «замер
серверов пула не проходит»**, запиши строки `measured` (причины уже без адресов), продолжай.

Шаг 4.4. Скорость в панели и в команде.

**Действие:** обнови страницу (F5), подожди 5 секунд, вкладка «Бесплатные серверы», снимок,
**J8**, **J9**, **J10**, **J6**.

Ожидается:
- J8 — `скоростей в строках: K | пример: 12 Мбит/с — Скорость по замеру ЧЧ:ММ` (K — сколько
  серверов «в работе» и «сейчас через» замерено; обычно равно «замерено» из шага 4.3);
- J9 — `Бесплатный сервер | A Мбит/с | задержка есть` (A — как «закреплённый» в шаге 4.3,
  если сервер не сменился);
- J10 — `скорость в полосе: A Мбит/с`;
- J6 — «сейчас через: 1», «в работе: …».

На снимке: в строках серверов «в работе» справа — скорость жирным, правее неё — задержка.

```bash
cd "$HOME/xgw-speed" && sudo xgw pool 2>&1 | grep -oE '[0-9,]+ Мбит/с, задержка [0-9]+ мс' | head -1 | tee cli.txt; sudo python3 -I speedcheck.py flow | tee -a cli.txt
```

Ожидается: строка «A Мбит/с, задержка … мс» (скорость сервера, через который идёт трафик) и
`flow` — «режим on: сейчас через pool-XX-… (XX), A Мбит/с; …».

Если не так: J8 — 0, J9 — «скорости нет», J10 — «скорости в полосе нет» или пустой вывод `grep` —
**дефект «скорость не видна»** (записать, где именно), продолжай.

Шаг 4.5. Ручной выбор главнее скорости. Если J8 в шаге 4.4 показал меньше 2 — шаг пропусти
(«замеренных серверов меньше двух»).
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-speed" && date +%s > t-pin.txt && sudo python3 -I speedcheck.py flow | tee pin-before.txt
```

2. Выполни **J11** — ответ «нажато у строки со скоростью N Мбит/с (подходящих строк: K)».
   Сразу снимок: вверху справа всплыла надпись «Выбран «…» (XX): трафик пула идёт через него,
   пока он отвечает; молчит — через выбранный шлюзом» — запиши её без имени сервера.
3. Затем:

```bash
cd "$HOME/xgw-speed" && sudo python3 -I speedcheck.py waitpin on 120 | tee pin.txt; sudo python3 -I speedcheck.py speed | tee -a pin.txt; sleep 120; for m in pinned flow; do sudo python3 -I speedcheck.py $m; done | tee -a pin.txt; sudo python3 -I speedcheck.py events "$(cat t-pin.txt)" | tee -a pin.txt
```

Ожидается:
- `waitpin`: «… выбран вручную: держится», «достигнуто за N с» (N — до 60);
- `speed`: «← сейчас через него» — у сервера со скоростью N из J11 (он медленнее других);
  «быстрее закреплённого на 30 % и больше» может быть больше 0 — это норма: выбор вручную
  главнее скорости;
- через 2 минуты `pinned` — «выбран вручную: xxxxxxxx…; ведёт трафик: да», `flow` — «… выбран
  вручную: держится» (шлюз не увёл трафик на более быстрый);
- события: «бесплатный пул: сервер «<сервер>» (XX) выбран вручную» и «бесплатный пул: весь дом
  идёт через «<сервер>» (XX), N Мбит/с — выбран вручную».

Если не так: «НЕ достигнуто за 120 с» — **дефект «выбранный не закрепился»**, запиши строки и
переходи к шагу 4.6. Через 2 минуты «выбран вручную: не отвечает» — сервер замолчал (не дефект,
запиши «выбранный молчит»).

Шаг 4.6. «Автовыбор» не прыгает сразу.
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-speed" && date +%s > t-auto.txt && echo "метка записана: $(date '+%T')"
```

2. **Действие:** обнови страницу (F5), вкладка «Бесплатные серверы», нажми у выбранной строки
   **«Автовыбор»** (мышью; не получается — **J12**). Снимок: всплыла надпись «Сервер бесплатного
   пула снова выбирает шлюз».
3. Затем (около 4 минут):

```bash
cd "$HOME/xgw-speed" && sudo python3 -I speedcheck.py waitpin auto 60 | tee auto.txt; sudo python3 -I speedcheck.py holdwatch 180 | tee -a auto.txt; for m in pinned speed; do sudo python3 -I speedcheck.py $m; done | tee -a auto.txt; sudo python3 -I speedcheck.py events "$(cat t-auto.txt)" | tee -a auto.txt
```

Ожидается:
- `waitpin auto`: «… выбран вручную: нет», «достигнуто за N с»;
- `holdwatch`: «сейчас через pool-XX-…» — тот же тег, что у выбранного в шаге 4.5; «смен
  сервера за 180 с: 0» (после «Автовыбора» бывший выбранный держится до 60 минут, даже если
  другой быстрее);
- `pinned` — «выбран вручную: нет (сервер выбирает шлюз)»;
- события: «бесплатный пул: выбор сервера вручную снят — сервер выбирает шлюз» и больше никаких
  «весь дом идёт через…».

Если не так: смена сервера в `holdwatch` — посмотри события: если перед ней «… : все серверы
пула молчат…» или смена без слова «быстрее» — сервер замолчал (не дефект, запиши); смена со
словом «быстрее» в течение 3 минут после «Автовыбора» — **дефект «автовыбор прыгает на
быстрый»**.

Шаг 4.7. Замеры учтены в трафике:

```bash
sleep 100; cd "$HOME/xgw-speed" && sudo python3 -I speedcheck.py spent "$(cat t-on.txt)" "$(cat pool-before.txt)" | tee spent.txt; sudo python3 -I speedcheck.py rows | tee -a spent.txt
```

Ожидается: «скачано замерами с … по …: X МБ; «бесплатные серверы» ↓ за это время выросло на Y
МБ; замеры учтены: да» (Y не меньше X: в Y ещё и трафик дома); `rows` — строка «бесплатные
серверы: ↓ …».

Если не так: «замеры учтены: НЕТ» — **дефект «трафик замеров не учтён»**, запиши строку.

Шаг 4.8. Возврат режима подписок — меткой вверху.
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-speed" && date +%s > t-back.txt && echo "метка записана: $(date '+%T')"
```

2. Нажми **метку вверху справа** («Через бесплатные серверы ▾»). Снимок; **J4** — `true |
   Вернуть режим подписок? | Вернуть режим подписок`.
3. Нажми в окне **«Вернуть режим подписок»**.
4. **Сразу** выполни (около 6 минут):

```bash
cd "$HOME/xgw-speed" && sudo python3 -I speedcheck.py watch back "$(cat t-back.txt)" | tee watch-back.txt; sudo systemctl stop xgw-speed-guard.timer; systemctl list-timers --all --no-pager xgw-speed-guard.timer | head -3 | tee guard-off.txt; for m in route state; do sudo python3 -I speedcheck.py $m; done | tee back.txt; sleep 120; sudo python3 -I speedcheck.py measured "$(( $(cat t-back.txt) + 60 ))" | tee -a back.txt
```

Ожидается: «нажатие: …»; «режим observe: через пул никто»; «ЗАКРЫТО» замеров: 0; таймер больше
не в списке («0 timers listed»); `route` — «последнее правило → auto; несущий канал: нет;
серверов в «pool»: 0», «совпадает с режимом: да»; `measured` — «серверов, замеренных с …: 0»
(через пул никто не идёт — замеров нет).

**Действие в браузере:** обнови страницу, вкладка «Бесплатные серверы», **J8** — `скоростей в
строках: 0 | пример: —`.

Если не так: `measured` больше 0 — **дефект «замеры без трафика пула»**, запиши строки.

## 5. Секреты

```bash
cd "$HOME/xgw-speed" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt
```

Ожидается: `0`. Если больше — **дефект** (строки журнала в отчёт не копировать).

## 6. Режим как до проверки и итог

Шаг 6.1. Если в шаге 1.3 наблюдение было **выключено** — **действие в браузере:** вкладка
«Бесплатные серверы» → **«Выключить»**, снимок (кнопка сменилась на «Включить наблюдение»). Было
включено — ничего не менять, записать «оставлено включённым».

Шаг 6.2. Итог:

```bash
sleep 60; cd "$HOME/xgw-speed" && date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units pool route state pinned; do sudo python3 -I speedcheck.py $m; done | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I speedcheck.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4, строки «Ожидает окна
перезапуска» нет; четыре службы `active`; режим — как был до проверки; `route` — «совпадает с
режимом: да»; `pinned` — «выбран вручную: нет»; журнал: «замеров серверов пула: N» (N — не
меньше «замерено» из шага 4.3), «из них не удались: …» (записать), «сервер бесплатного пула не
закреплён: 0», «у всего дома закрыто: 0», «откат на last-good: 0», «шаг пула не выполнен: 0»,
«Traceback: 0».

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- В режиме «весь дом» пропал интернет или доступ, или заказчик не отвечает **2 минуты** —
  **сразу**: `sudo xgw pool mode observe`, `sudo xgw pool pin auto`, затем
  `sudo systemctl stop xgw-speed-guard.timer` (ошибка «not loaded» — норма). Записать время и
  строки `sudo python3 -I speedcheck.py flow` и `sudo python3 -I speedcheck.py route`. Дальше —
  §5, §6 и отчёт. «Весь дом» больше не включать.
- Сработал страховочный таймер (через 40 минут режим вернулся сам) — записать время, выполнить
  `sudo xgw pool pin auto` и продолжить с §5.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.
- Браузер не открывает панель или кнопки не нажимаются (и J11/J12 не помогают) — снимок,
  сообщить заказчику и попросить нажать то же самое вручную; в отчёте пометить «нажато
  заказчиком».

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-speed-<ДАТА>.md` в клоне (`<ДАТА>` — дата
начала проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, скорость серверов бесплатного пула» и
`git push` в `freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и
подписок, адресов, доменов, токена и строк журнала. Шаблон (заполни каждую ячейку; пропущенное —
«не выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — скорость серверов бесплатного пула и выбор по скорости

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
speedcheck.py: <сумма>. Наблюдение до проверки: <…>. Ядра: Xray <…>, sing-box <…>.
Исполнитель: <модель>; нажатия и снимки — управляемым браузером <да/частично>.

## Итог
| Замерены все живые: за, с / замерено из / неудачных | Закреплённый / самый быстрый, Мбит/с / быстрее на ≥30 % | Смен на быстрый в первые минуты | Скорость в панели: строки J8 / карточка J9 / полоса J10 / `xgw pool` | Ручной выбор главнее скорости (через 2 мин) | Автовыбор: смен за 3 мин | Замеры учтены в трафике: X / Y МБ | После возврата замеров |
|---|---|---|---|---|---|---|---|
| <N / K из N / F> | <A / B / 0> | <N> | <K / да / да / да> | <да> | <0> | <да: 60 / 75> | <0> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 наблюдение | … | … |
| 4.1 страховка | … | … |
| 4.2 панель до | … | … |
| 4.3 включение и замеры | … | … |
| 4.4 скорость в панели и команде | … | … |
| 4.5 ручной выбор | … | … |
| 4.6 автовыбор | … | … |
| 4.7 учёт замеров | … | … |
| 4.8 возврат меткой | … | … |
| 5 секреты | … | … |
| 6 итог | … | … |

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-speed/…); результаты J1–J12; что видно на
  снимках словами; всплывшие надписи без имён; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
