# Проверка XGW 0.2.0: причина смены сервера пула, «жив под нагрузкой» и долгое наблюдение

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, делаешь **снимок
  экрана** и смотришь на него, выполняешь JavaScript в консоли страницы.

Проверка идёт **в две сессии**: сессия 1 (§1–§4, около часа) — установка, проверка правки и
запуск долгого наблюдения «всего дома»; сессия 2 (§5–§7, около 20 минут) — когда скажет
заказчик (утром или по окончании срока): итог наблюдения, рассказ заказчика, возврат режима,
отчёт. Между сессиями файлы в `$HOME/xgw-diary` не удалять.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J1, J4, J9) — выполни её в
   консоли страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-diary/…`. Время шага — по выводу `date` в
   команде, не по памяти.
5. **Метка времени — до нажатия.** Где в шаге есть команда «Метка», выполни её **перед**
   нажатием в браузере, а команду проверки — **после**.
6. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
7. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
8. Экземпляр этого ТЗ держи в `$HOME/xgw-diary/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2.
9. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `diarycheck.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
10. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши
    дословно строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
    «Наблюдения», со словом «предположение».

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.29 и sing-box
1.14.4, принятые шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 274)

1. **Причина смены сервера пула.** В прошлой проверке закреплённый бесплатный сервер дважды
   сменился событием без причины. Теперь у каждой смены, кроме первого выбора, — причина:
   «— быстрее, чем «…» (N Мбит/с)», «— «…» не отвечает», «— «…» больше не в работе»,
   «— выбран вручную».
2. **«Жив под нагрузкой».** Если пробы ядра сочли закреплённый сервер мёртвым, а данные через
   него идут (проба опоздала в загруженном канале), шлюз его не меняет; в журнале — «проба ядра
   опоздала под нагрузкой: … — сервер пула жив».
3. **Дневник пула.** `sudo xgw pool stats` — по дням: сколько времени трафик шёл через пул и
   сколько было закрыто, смены сервера по причинам, средняя скорость, замеры, трафик через пул и
   через подписку. По нему после долгого наблюдения решается, нужны ли новые правила выбора.

### Главное правило безопасности

В сессии 1, пока включён «весь дом»: пропал интернет на машине, заказчик говорит, что пропал
доступ, или не отвечает на вопрос **2 минуты** — **сразу** раздел «Если что-то пошло не так».
Во время долгого наблюдения режим сторожит страховочный таймер, а заказчик в любой момент может
вернуть режим подписок меткой вверху панели.

### Что где на экране панели (для снимков)

- **Верх страницы**: справа — **метка состояния** («Серверы в порядке», «Через бесплатные
  серверы ▾»…). В режиме «весь дом» метка — кнопка возврата.
- **Главная карточка** (левая колонка, вверху): строка «Бесплатный сервер» — имя, страна,
  скорость («· 25 Мбит/с») и задержка («· 85 мс»).
- **Правая колонка**: вкладки **«Подписки»** и **«Бесплатные серверы»**; на второй вверху справа
  — «Весь дом через бесплатные» (во «всём доме» — «Вернуть режим подписок»), «Выключить».
- **Окно подтверждения** — по центру: заголовок, текст, «Отмена» и кнопка действия справа.

### Проверки JavaScript (в консоли страницы панели)

- **J1 — метка вверху:**
  `(() => { const c = document.getElementById("chip"); return [c.tagName, c.textContent.trim(), c.disabled].join(" | "); })()`
- **J4 — окно подтверждения:**
  `(() => { const d = document.getElementById("confirm-dialog"); return [d.open, document.getElementById("confirm-title").textContent, document.getElementById("confirm-yes").textContent].join(" | "); })()`
- **J9 — скорость в главной карточке:**
  `(() => { const n = document.getElementById("current-name").textContent; const m = n.match(/ · ([\d,]+ Мбит\/с)/); return [document.getElementById("current-label").textContent, m ? m[1] : "скорости нет", / · \d+ мс$/.test(n) ? "задержка есть" : "задержки нет"].join(" | "); })()`

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, `reboot`, сон машины —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh`; ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`,
  `sysctl -w`, `apt`; команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`. `systemd-run` и
  `systemctl stop` — только для страховочного таймера `xgw-diary-guard`. `sudo xgw pool mode …` —
  только в шаге 3.1 (`observe`), в «Если не так» шагов, где это написано, и в разделе «Если
  что-то пошло не так». `sudo xgw pool pin …` — только в разделе «Если что-то пошло не так».
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`). Загрузок из терминала нет.
  Сайты источников, файлы списков на GitHub, сайты проверки IP, страны и скорости — не открывать.
- В панели нажимать **только** то, что написано в шагах: вкладки, «Весь дом через бесплатные» и
  кнопку подтверждения в его окне, метку вверху и кнопки её окна, «Выключить». **Не нажимать**:
  кнопку питания, «Замерить скорость», «Проверить запасные», «Обновить», «Опросить источники»,
  «Выбрать» и «Автовыбор» (у любых серверов), переключатели Tailscale, «Ядра», «Проверить сеть»,
  строки устройств, «Добавить», «Убрать».
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, код XGW. Печатать `config.toml`, `panel.json`, рабочие конфиги
  Xray и sing-box, файлы в `/var/lib/xgw/freepool`, базу `/var/lib/xgw/state.db`, полный вывод
  `sudo xgw pool` и `sudo xgw traffic`. Коммитить что-либо, кроме файла отчёта (§7). Снимки
  экрана в git не добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, токен из ссылки
  панели, MAC, имена пользователей (→ `<user>`), внешние IP, адреса и домены подписок, IP,
  домены и ссылки серверов VPN, строки журнала. Можно: коды стран, теги вида `pool-de-1a2b`,
  скорости, задержки, вывод `sudo xgw pool stats` целиком (имён в нём нет), надписи панели без
  имён, счётчики, мегабайты, статусы, времена, строки помощника.

## 1. Подготовка (сессия 1)

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю две правки бесплатных серверов и хочу понаблюдать «весь дом через бесплатные серверы»
подольше — это решит, нужны ли шлюзу новые правила выбора сервера. Нажатия в панели и осмотр
экрана я делаю сам, в управляемом браузере. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Если наблюдение за бесплатными серверами выключено, я включу его и подожду 30 минут.
(3) Я включу «весь дом через бесплатные серверы» и оставлю его надолго. Срок выберите: **А** — до
9 утра, **Б** — на сутки, **В** — на 6 часов. По сроку страховочный таймер сам вернёт режим
подписок. Пользуйтесь интернетом как обычно; если что-то не нравится — нажмите метку вверху
панели («Через бесплатные серверы ▾») и «Вернуть режим подписок», это безопасно. Шлюз скачает
через каждый бесплатный сервер в работе пробный файл до 10 МБ раз в 6 часов (квоту подписок это
не тратит).
(4) По окончании я спрошу, как работал интернет, и верну наблюдение в то состояние, в каком оно
было до проверки.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 при выключенном наблюдении или против 3 — §4 и сессию 2
пропустить, кроме §6 (в отчёте: «долгое наблюдение не проводилось»). Против 4 — §6 без смены
режима. **Запиши срок (А, Б или В)** — от него зависит команда шага 4.1. Если ответа нет — не
начинать, спросить ещё раз.

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-diary" && chmod 700 "$HOME/xgw-diary" && cd "$HOME/xgw-diary" && cat > diarycheck.py <<'EOF'
"""XGW 0.2.0, бесплатный пул: причина смены сервера, «жив под нагрузкой» и дневник пула —
помощник проверки. Только читает: состояние XGW (/run/xgw), базу состояния
(/var/lib/xgw/state.db — только чтение), рабочий конфиг Xray, настройки и журнал со
стандартного ввода — счётчики, скорости, коды стран, теги pool-<страна>-<начало id>, итоги и
да/нет; без имён серверов, устройств и подписок, ссылок и ключей. Время — секунды с 1970
(date +%s). Режимы: units, pool, route, state, flow, speed, waitspeed, watch on|back, events,
eventsum, log."""
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
LIB = os.environ.get("DIARYCHECK_LIB", "/opt/xgw/lib")
NAME = re.compile("«[^»]*»")
MARKS = {"on": "бесплатный пул: весь дом через бесплатные серверы",
         "back": "режим подписок возвращён"}
GOALS = {"on": "on", "back": "observe"}
MANUAL = {"on": "держится", "down": "не отвечает — ведёт выбранный шлюзом", "": "нет"}
SWITCH = ("весь дом идёт через", " идут через ")
REASONS = (("— быстрее, чем", "на более быстрый"), ("— выбран вручную", "выбран вручную"),
           ("выбранный вручную не отвечает", "выбранный вручную молчит"),
           ("больше не в работе", "прежний вне состава"), ("» не отвечает", "прежний не отвечал"))
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
    return time.strftime("%d.%m %H:%M:%S", time.localtime(ts))


def arg(index, default):
    try:
        return float(sys.argv[index])
    except (IndexError, ValueError):
        return default


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


def measured_ids(paths):
    try:
        conn = db(paths)
        row = conn.execute("SELECT value FROM meta WHERE key = 'pool_speed'").fetchone()
        conn.close()
        records = json.loads(row["value"]) if row and row["value"] else {}
    except (sqlite3.Error, ValueError):
        return []
    return list(records) if isinstance(records, dict) else []


def speed_rows(cfg, paths):
    flow = flow_of(read_json(paths.status_file) or {}) or {}
    ids, tried = admitted_ids(cfg, paths), measured_ids(paths)
    rows = []
    for item in flow.get("servers") or []:
        if not isinstance(item, dict):
            continue
        prefix = str(item.get("id") or "")
        rows.append({
            "tag": str(item.get("tag") or ""), "alive": bool(item.get("alive")),
            "mbps": item.get("mbps"), "delay": item.get("delay_ms") or 0,
            "admitted": bool(prefix) and any(full.startswith(prefix) for full in ids),
            "tried": bool(prefix) and any(full.startswith(prefix) for full in tried),
            "current": bool(flow.get("tag")) and item.get("tag") == flow.get("tag"),
        })
    return flow, rows


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
              f"задержка {row['delay']} мс, допущен: {'да' if row['admitted'] else 'нет'}, "
              f"замер был: {'да' if row['tried'] else 'нет'}"
              + ("  ← сейчас через него" if row["current"] else ""))
elif mode == "waitspeed":
    cfg, paths = xgw()
    limit = arg(2, 420.0)
    start, last = time.time(), None
    while True:
        flow, rows = speed_rows(cfg, paths)
        live = [row for row in rows if row["alive"] and row["admitted"]]
        tried = [row for row in live if row["tried"]]
        line = (f"сейчас через {flow.get('tag') or '—'}, {rate(flow.get('mbps'))}; замер был у "
                f"{len(tried)} из {len(live)} живых допущенных")
        if line != last:
            print(f"+{time.time() - start:4.0f} с: {line}", flush=True)
            last = line
        if live and len(tried) == len(live):
            print(f"замер был у всех живых допущенных за {time.time() - start:.0f} с")
            break
        if time.time() - start > limit:
            print(f"НЕ у всех за {limit:.0f} с")
            break
        time.sleep(5)
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
elif mode == "eventsum":
    _cfg, paths = xgw()
    since = arg(2, time.time() - 86400)
    counts = {label: 0 for _word, label in REASONS}
    first = bare = closures = 0
    modes, after_switch = [], False
    for ts, kind, detail in events_since(paths, since):
        if kind != "freepool":
            continue
        if MARKS["on"] in detail or MARKS["back"] in detail or "после перезагрузки" in detail:
            modes.append(f"{stamp(ts)} " + ("весь дом включён" if MARKS["on"] in detail
                                            else "режим подписок"))
            after_switch = False
        elif "закрыто" in detail:
            closures += 1
            after_switch = False
        elif any(word in detail for word in SWITCH):
            label = next((label for word, label in REASONS if word in detail), "")
            if label:
                counts[label] += 1
            elif after_switch:
                bare += 1
            else:
                first += 1
            after_switch = True
    total = first + bare + sum(counts.values())
    print(f"события пула с {stamp(since)}: смен сервера {total}: первый выбор {first}, "
          + ", ".join(f"{label} {count}" for label, count in counts.items())
          + f"; БЕЗ ПРИЧИНЫ: {bare}; «закрыто»: {closures}")
    print("режим: " + ("; ".join(modes) if modes else "не менялся"))
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    measures = [line for line in lines if "замер скорости pool-" in line]
    print(f"строк журнала: {len(lines)}")
    print(f"замеров серверов пула: {len(measures)}; из них не удались: "
          f"{sum(1 for line in measures if 'не удался' in line)}")
    for label, word in (
        ("проба ядра опоздала под нагрузкой (сервер пула жив)", "сервер пула жив"),
        ("сервер бесплатного пула не закреплён", "сервер бесплатного пула не закреплён"),
        ("откат на last-good", "last-good"),
        ("шаг пула не выполнен", "бесплатный пул: шаг не выполнен"),
        ("учёт трафика: шаг не выполнен", "учёт трафика: шаг не выполнен"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | pool | route | state | flow | speed | waitspeed | watch on|back | "
          "events | eventsum | log")
EOF
python3 -c "import hashlib;d=open('diarycheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `037c5c2a924cb891`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки:

```bash
cd "$HOME/xgw-diary" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units pool route state; do sudo python3 -I diarycheck.py $m; done | tee -a before.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; первая строка
`xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать, какая**; четыре
службы `active`; `route` — «совпадает с режимом: да».

Если не так: первая строка `xgw pool` — «весь дом через бесплатные серверы» — выполнить
`sudo xgw pool mode observe`, подождать минуту и повторить шаг.

## 2. Установка (сессия 1)

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def _pool_spared' src/xgw/daemon.py && grep -q 'больше не в работе' src/xgw/daemon.py && grep -q 'class Diary' src/xgw/freepool/stats.py && grep -q 'def usage_by_day' src/xgw/store.py && grep -q '"stats", help=' src/xgw/cli.py && echo "правка в коде: есть"; cd "$HOME/xgw-diary"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-diary/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-diary/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-diary/install.txt"; cd "$HOME/xgw-diary"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 3 минуты:

```bash
sleep 180; cd "$HOME/xgw-diary" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee after-install.txt; for m in units route state; do sudo python3 -I diarycheck.py $m; done | tee -a after-install.txt; sudo xgw pool stats 2>&1 | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I diarycheck.py log | tee log-install.txt
```

Ожидается: `HEALTHY`, перехват включён, строки «Ожидает окна перезапуска» нет; четыре службы
`active`; `route` — «совпадает с режимом: да»; `xgw pool stats` — заголовок «Бесплатный пул по
дням (трафик через пул — весь дом или устройства):» и две строки дней «ГГГГ-ММ-ДД: через пул
никто не шёл; трафик через пул ↓ … ↑ …, через подписку ↓ … ↑ …» (дневник ведётся с этой
установки); журнал: «Traceback: 0».

Если не так: не `HEALTHY` — подожди 2 минуты и повтори; снова нет — запиши и продолжай.
`xgw pool stats` — «invalid choice» или ошибка — **дефект «нет дневника»**, продолжай.

## 3. Наблюдение (сессия 1)

Шаг 3.1. Только если в шаге 1.3 наблюдение было **выключено** (иначе — пропустить, записать «уже
было включено» и подождать 5 минут):

```bash
cd "$HOME/xgw-diary" && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; sleep 1800; sudo python3 -I diarycheck.py pool | tee -a mode-on.txt
```

(Если терминал обрывает длинные команды — после первой строки выполни `sleep 110` 17 раз, затем
`sudo python3 -I diarycheck.py pool`.)

Ожидается: «Наблюдение за бесплатным пулом включено: …»; через 30 минут — «пригодно» больше 1.

Если не так: «пригодно» 0 или 1 — подожди ещё 30 минут и повтори `pool`; снова не больше 1 — §4
и сессию 2 пропустить («допущенных серверов меньше двух»), перейти к §6.

## 4. Весь дом: проверка правки и запуск долгого наблюдения (сессия 1)

Шаг 4.1. Страховочный таймер — **до** включения «всего дома». Выполни **один** блок — по сроку
из шага 1.1.

Срок **А** (до 9 утра):

```bash
cd "$HOME/xgw-diary" && sudo systemd-run --on-calendar='*-*-* 09:00:00' --unit=xgw-diary-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-diary-guard.timer | head -3 | tee -a guard.txt
```

Срок **Б** (сутки):

```bash
cd "$HOME/xgw-diary" && sudo systemd-run --on-active=24h --unit=xgw-diary-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-diary-guard.timer | head -3 | tee -a guard.txt
```

Срок **В** (6 часов):

```bash
cd "$HOME/xgw-diary" && sudo systemd-run --on-active=6h --unit=xgw-diary-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-diary-guard.timer | head -3 | tee -a guard.txt
```

Ожидается: «Running timer as unit: xgw-diary-guard.timer» и строка таймера с временем
срабатывания — **записать его** (А — ближайшие 09:00, Б — через сутки, В — через 6 часов).

Если не так: таймера нет — **стоп** для §4 и сессии 2 (перейти к §6).

Шаг 4.2. Панель. Ссылка входа (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком (окно не меньше 1280×800),
подожди 5 секунд, нажми вкладку **«Бесплатные серверы»**, подожди 5 секунд, снимок.

Шаг 4.3. Включение «всего дома».
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-diary" && date +%s > t-on.txt && echo "метка записана: $(date '+%T')"
```

2. На вкладке «Бесплатные серверы» нажми **«Весь дом через бесплатные»**.
3. Снимок; **J4** — `true | Пустить весь дом через бесплатные серверы? | Весь дом через
   бесплатные`.
4. Нажми в окне **«Весь дом через бесплатные»**.
5. **Сразу** выполни (около 3 минут на `watch` и до 7 минут на `waitspeed`):

```bash
cd "$HOME/xgw-diary" && sudo python3 -I diarycheck.py watch on "$(cat t-on.txt)" | tee watch-on.txt; sudo python3 -I diarycheck.py waitspeed 420 | tee speed-wait.txt; for m in speed route; do sudo python3 -I diarycheck.py $m; done | tee speed-on.txt; sudo python3 -I diarycheck.py events "$(cat t-on.txt)" | tee events-on.txt; sudo python3 -I diarycheck.py eventsum "$(cat t-on.txt)" | tee -a events-on.txt
```

Ожидается:
- `watch`: «нажатие: …»; строки «+N с: режим on: сейчас через pool-XX-… (XX), …»; «ЗАКРЫТО»
  замеров: 0;
- `waitspeed`: «замер был у всех живых допущенных за N с» (N — до 420; неудачный замер тоже
  считается: «замер был»);
- `speed`: по строке на сервер, у живых допущенных — «замер был: да», у одной — «← сейчас через
  него»;
- `route` — «последнее правило → pool; несущий канал: есть; серверов в «pool»: N», «совпадает с
  режимом: да»;
- события: каждая строка «… весь дом идёт через «<сервер>» (XX)…», **кроме первой после
  включения**, заканчивается причиной: «— быстрее, чем «<сервер>» (…)», «— «<сервер>» не
  отвечает» или «— «<сервер>» больше не в работе»;
- `eventsum` — «смен сервера N: первый выбор 1, …; БЕЗ ПРИЧИНЫ: 0; «закрыто»: 0» и «режим: …
  весь дом включён».

Если не так: «сейчас через» не появилось за три минуты — раздел «Если что-то пошло не так»,
сессию 2 пропустить. «БЕЗ ПРИЧИНЫ» больше 0 — **дефект «смена без причины»** (запиши строки
событий), продолжай.

Шаг 4.4. Панель, дневник и журнал:

**Действие:** обнови страницу (F5), подожди 5 секунд, снимок, **J9** и **J1**.

Ожидается: J9 — `Бесплатный сервер | N Мбит/с | задержка есть` (сервер ещё не замерен —
«скорости нет», запиши); J1 — `BUTTON | Через бесплатные серверы | false` (стрелка «▾» рисуется
стилем, в тексте её нет).

```bash
cd "$HOME/xgw-diary" && sudo xgw pool stats --days 1 2>&1 | tee stats-start.txt; sudo journalctl -u xgw --since "@$(cat t-on.txt)" --no-pager | sudo python3 -I diarycheck.py log | tee log-start.txt
```

Ожидается: `xgw pool stats` — строка сегодняшнего дня «ГГГГ-ММ-ДД: через пул N мин, закрыто 0 с»
(N — около 10–15: столько прошло с включения), «смен сервера K: первый выбор 1, …», «средняя
скорость ведущего … Мбит/с; замеров M, …» (M — как число серверов с «замер был: да»),
«трафик через пул ↓ … ↑ …, через подписку …»; журнал: «замеров серверов пула: M», «проба ядра
опоздала под нагрузкой (сервер пула жив): …» (записать число — может быть 0),
«Traceback: 0».

Если не так: строка дня «через пул никто не шёл» при включённом «всём доме» — **дефект «дневник
не считает»**, продолжай.

Шаг 4.5. **Скажи заказчику** (дословно, подставив время таймера из шага 4.1): «Весь дом идёт
через бесплатные серверы. Страховочный таймер вернёт режим подписок в <время>. Пользуйтесь
интернетом как обычно. Если что-то не нравится — нажмите метку вверху панели «Через бесплатные
серверы ▾» и «Вернуть режим подписок». Когда закончим — напишите мне, я сниму итоги.»

Запиши время. **Сессия 1 окончена.** Отчёт пока не пиши; файлы в `$HOME/xgw-diary` не удаляй.

## 5. Итоги наблюдения (сессия 2 — когда скажет заказчик)

Шаг 5.1. Помощник на месте и состояние:

```bash
cd "$HOME/xgw-diary" && python3 -c "import hashlib;d=open('diarycheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; date '+%F %T' | tee end.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Ожидает окна' | tee -a end.txt; for m in units flow state route; do sudo python3 -I diarycheck.py $m; done | tee -a end.txt; systemctl list-timers --all --no-pager xgw-diary-guard.timer | head -3 | tee -a end.txt
```

Ожидается: сумма — как в шаге 1.2; `HEALTHY`; четыре службы `active`; `flow` — «режим on: сейчас
через pool-XX-… …» (наблюдение ещё идёт) **или** «режим observe: через пул никто» (сработал
таймер или заказчик вернул режим сам — записать, что именно: таймер в списке есть — вернул
заказчик; «0 timers listed» — сработал таймер); `route` — «совпадает с режимом: да».

Если не так: сумма другая — файл помощника изменился: **стоп**, сообщить заказчику.

Шаг 5.2. Итоги дневника, событий и журнала:

```bash
cd "$HOME/xgw-diary" && sudo xgw pool stats --days 2 2>&1 | tee stats-end.txt; sudo python3 -I diarycheck.py eventsum "$(cat t-on.txt)" | tee eventsum-end.txt; sudo journalctl -u xgw --since "@$(cat t-on.txt)" --no-pager | sudo python3 -I diarycheck.py log | tee log-end.txt
```

Ожидается (записать **целиком** в отчёт — имён в этих строках нет):
- `xgw pool stats` — по строке на день: «через пул …, закрыто … (… раз)», «смен сервера …: …»,
  «средняя скорость ведущего …; замеров …, не удались …; проба ядра опоздала под нагрузкой: …»,
  «трафик через пул …, через подписку …»; суммарное «через пул» за оба дня — близко ко времени
  от включения до конца наблюдения;
- `eventsum` — «смен сервера N: …; БЕЗ ПРИЧИНЫ: 0; «закрыто»: K» и строка режима (включение и,
  если было, возврат — таймером, заказчиком или «после перезагрузки»);
- журнал: «Traceback: 0», «откат на last-good: 0», остальные числа — записать.

Если не так: «БЕЗ ПРИЧИНЫ» больше 0 — **дефект «смена без причины»**: выполни
`sudo python3 -I diarycheck.py events "$(cat t-on.txt)" | tee events-end.txt` и приложи строки
вокруг смен без причины. «Traceback» больше 0 — **дефект**.

Шаг 5.3. **Спроси заказчика** (дословно): «Весь дом шёл через бесплатные серверы с <время
включения из шага 4.3>. Расскажите, пожалуйста: (1) открывались ли сайты как обычно; (2) как шло
видео (YouTube и т. п.); (3) были ли обрывы или «ничего не открывается» — примерно когда и
надолго; (4) что-то работало хуже, чем через подписку; (5) возвращали ли вы режим подписок сами
и почему?» Ответы — дословно, без имён.

Шаг 5.4. Возврат режима подписок. Если в шаге 5.1 `flow` — «режим observe» (режим уже вернулся),
выполни только команду пункта 4 без `watch`:
`sudo systemctl stop xgw-diary-guard.timer; for m in route state; do sudo python3 -I diarycheck.py $m; done | tee back.txt`
(ошибка «not loaded» — норма) и переходи к §6. Иначе:
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-diary" && date +%s > t-back.txt && echo "метка записана: $(date '+%T')"
```

2. Открой панель (ссылка — `sudo xgw panel 2>&1 | head -1`, если вкладка закрыта), нажми
   **метку вверху справа** («Через бесплатные серверы ▾»). Снимок; **J4** — `true | Вернуть
   режим подписок? | Вернуть режим подписок`.
3. Нажми в окне **«Вернуть режим подписок»**.
4. **Сразу** выполни:

```bash
cd "$HOME/xgw-diary" && sudo python3 -I diarycheck.py watch back "$(cat t-back.txt)" | tee watch-back.txt; sudo systemctl stop xgw-diary-guard.timer; systemctl list-timers --all --no-pager xgw-diary-guard.timer | head -3 | tee guard-off.txt; for m in route state; do sudo python3 -I diarycheck.py $m; done | tee back.txt
```

Ожидается: «нажатие: …»; «режим observe: через пул никто»; «ЗАКРЫТО» замеров: 0; «0 timers
listed»; `route` — «последнее правило → auto; несущий канал: нет; серверов в «pool»: 0»,
«совпадает с режимом: да».

## 6. Секреты и режим как до проверки

Шаг 6.1. Секреты:

```bash
cd "$HOME/xgw-diary" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt
```

Ожидается: `0`. Если больше — **дефект** (строки журнала в отчёт не копировать).

Шаг 6.2. Если в шаге 1.3 наблюдение было **выключено** — **действие в браузере:** вкладка
«Бесплатные серверы» → **«Выключить»**, снимок (кнопка сменилась на «Включить наблюдение»). Было
включено — ничего не менять, записать «оставлено включённым».

Шаг 6.3. Итог:

```bash
sleep 60; cd "$HOME/xgw-diary" && date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units pool route state; do sudo python3 -I diarycheck.py $m; done | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I diarycheck.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4, строки «Ожидает окна
перезапуска» нет; четыре службы `active`; режим — как был до проверки; `route` — «совпадает с
режимом: да»; журнал: «откат на last-good: 0», «Traceback: 0».

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- В сессии 1 в режиме «весь дом» пропал интернет или доступ, или заказчик не отвечает **2
  минуты** — **сразу**: `sudo xgw pool mode observe`, затем
  `sudo systemctl stop xgw-diary-guard.timer` (ошибка «not loaded» — норма). Записать время и
  строки `sudo python3 -I diarycheck.py flow` и `sudo python3 -I diarycheck.py route`. Дальше —
  §6 и отчёт. «Весь дом» больше не включать.
- Заказчик во время долгого наблюдения вернул режим подписок сам — это не сбой: в сессии 2
  записать время (из `eventsum`) и его причину (шаг 5.3).
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.
- Браузер не открывает панель или кнопки не нажимаются — снимок, сообщить заказчику и попросить
  нажать то же самое вручную; в отчёте пометить «нажато заказчиком».

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-diary-<ДАТА>.md` в клоне (`<ДАТА>` — дата
начала проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, долгое наблюдение бесплатного пула» и
`git push` в `freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и
подписок, адресов, доменов, токена и строк журнала. Шаблон (заполни каждую ячейку; пропущенное —
«не выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — причина смены сервера пула, «жив под нагрузкой» и долгое наблюдение

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>, срок <А/Б/В>.
diarycheck.py: <сумма>. Наблюдение до проверки: <…>. Ядра: Xray <…>, sing-box <…>.
Исполнитель: <модель>; нажатия и снимки — управляемым браузером <да/частично>.

## Итог
| Весь дом: с — по (чем закончился) | Через пул / закрыто (раз) | Смен сервера: всего / на быстрый / не отвечал / вне состава / без причины | Средняя скорость ведущего | Замеров / не удались | «Жив под нагрузкой» | Трафик через пул / подписку | Заказчик: как работало |
|---|---|---|---|---|---|---|---|
| <13:20 — 09:00 (таймер)> | <19 ч 30 мин / 4 мин (2 раза)> | <N / a / b / c / 0> | <… Мбит/с> | <M / F> | <K> | <… ГБ / … МБ> | <кратко> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 наблюдение | … | … |
| 4.1 страховка | … | … |
| 4.3 включение | … | … |
| 4.4 панель, дневник, журнал | … | … |
| 5.1 состояние в конце | … | … |
| 5.2 итоги дневника и событий | … | … |
| 5.3 рассказ заказчика | … | … |
| 5.4 возврат | … | … |
| 6 секреты и итог | … | … |

## Вывод `sudo xgw pool stats --days 2` (шаг 5.2, целиком)
<…>

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-diary/…); результаты J1, J4, J9; что видно
  на снимках словами; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
