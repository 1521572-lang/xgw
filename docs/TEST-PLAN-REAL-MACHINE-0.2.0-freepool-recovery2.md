# Проверка XGW 0.2.0: восстановление бесплатного пула — повтор и долгое наблюдение

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, делаешь **снимок
  экрана** и смотришь на него, выполняешь JavaScript в консоли страницы.

Сессия 1 (§1–§7, около полутора часов) — установка, холодный старт, молчащий выбранный вручную
сервер. Дальше — по сроку, который выберет заказчик (шаг 1.1): **Г** — сразу возврат (§9, §10,
отчёт); **А/Б/В** — «весь дом» остаётся на долгое наблюдение, а сессия 2 (§8.2–§10, около 20
минут) — когда скажет заказчик. Между сессиями файлы в `$HOME/xgw-recov2` не удалять.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J1, J4, J9) — выполни её в
   консоли страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-recov2/…`. Время шага — по выводу `date` в
   команде, не по памяти.
5. **Метка времени — до нажатия.** Где в шаге есть команда «Метка», выполни её **перед**
   нажатием в браузере, а команду проверки — **после**.
6. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
7. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
8. Экземпляр этого ТЗ держи в `$HOME/xgw-recov2/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2.
9. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `recovcheck.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
10. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши
    дословно строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
    «Наблюдения», со словом «предположение».
11. **Дневник пула** пишется раз в минуту: снимай `xgw pool stats` не раньше чем через минуту
    после события (в командах ниже это уже учтено).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.29 и sing-box
1.14.4, принятые шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 276) и зачем повтор

1. **Ручной выбор выбывшего сервера снимается сам.** Выбранный вручную сервер пула ушёл из
   списков или не прошёл проверку шлюза — шлюз снимает выбор с событием «бесплатный пул:
   выбранный вручную сервер «…» больше не допущен (…) — сервер снова выбирает шлюз». Старая
   проверка — не повод.
2. **Резерв бюджета.** Проверки серверов в работе могут тратить защищённый резерв суточного
   бюджета, молчащего — и аварийный запас.
3. **Состав — пулу до проверок.** После запуска демона серверы в работе проверяются с первой же
   пачки.
4. **«Выбыло из состава»** в дневнике считается по самому составу.
5. **Повтор пути «вне очереди».** В прошлой проверке заблокированный сервер перепроверился
   обычной очередью (его проверка была старше 2 часов), и путь «вне очереди» не сработал. Теперь
   порядок обратный: сначала холодный старт (проверки серверов в работе станут свежими), затем
   блокировка — перепроверку даст только путь «вне очереди».

### Как проверяется

- **Холодный старт (§5).** Демон XGW останавливается на минуту (Xray работает, дом идёт через
  пул), помощник (режим `age`) сдвигает время последних проверок серверов в работе на 4 часа
  назад — как будто шлюз был выключен 4 часа, — и демон запускается снова.
- **Молчащий выбранный вручную сервер (§6).** Текущий сервер пула выбирается вручную командой
  `xgw pool pin`, затем помощник (режим `block`) ставит временную таблицу nftables
  `inet xgw_recov`: пакеты этой машины к его адресу сбрасываются. Адрес помощник берёт из
  рабочего конфига Xray и не печатает. Страховочный таймер `xgw-recov-unblock` снимет таблицу
  сам через 40 минут.

### Главное правило безопасности

Пока включён «весь дом» в сессии 1: пропал интернет на машине, заказчик говорит, что пропал
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
  NetworkManager, `ssh` — кроме `sudo systemctl stop xgw` и `sudo systemctl start xgw` в шаге 5.2
  и `sudo systemctl start xgw` в разделе «Если что-то пошло не так». Ручные `nft` (кроме
  `nft list`), `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`, `apt`; команды `tailscale`,
  `xray`, `sing-box`, `sstpc`, `pppd`. `systemd-run` и `systemctl stop` — только для таймеров
  `xgw-recov-guard` и `xgw-recov-unblock`. `sudo xgw pool mode …` — только в шаге 3.1
  (`observe`), в «Если не так» шагов, где это написано, и в разделе «Если что-то пошло не так».
  `sudo xgw pool pin …` — только в шаге 6.2 и в §9.
- Режимы помощника, которые меняют состояние: `block` — только в шаге 6.3, `unblock` — в шаге 7.1
  и в разделе «Если что-то пошло не так», `age` — только в шаге 5.2.
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`). Загрузок из терминала нет.
  Сайты источников, файлы списков на GitHub, сайты проверки IP, страны и скорости — не открывать.
- В панели нажимать **только** то, что написано в шагах: вкладки, «Весь дом через бесплатные» и
  кнопку подтверждения в его окне, метку вверху и кнопки её окна, «Выключить». **Не нажимать**:
  кнопку питания, «Замерить скорость», «Проверить запасные», «Обновить», «Опросить источники»,
  «Выбрать» и «Автовыбор» (у любых серверов), переключатели Tailscale, «Ядра», «Проверить сеть»,
  строки устройств, «Добавить», «Убрать».
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw` (кроме
  помощника в режиме `age`), `/run/xgw`, `/etc/systemd`, код XGW. Печатать `config.toml`,
  `panel.json`, рабочие конфиги Xray и sing-box, файлы в `/var/lib/xgw/freepool`, базу
  `/var/lib/xgw/state.db`, полный вывод `sudo xgw pool` и `sudo xgw traffic`, вывод
  `nft list ruleset`. Коммитить что-либо, кроме файла отчёта (§11). Снимки экрана в git не
  добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, токен из ссылки
  панели, MAC, имена пользователей (→ `<user>`), внешние IP, адреса и домены подписок, IP,
  домены и ссылки серверов VPN, строки журнала. Можно: коды стран, теги вида `pool-de-1a2b`,
  начала id серверов пула (10 знаков), скорости, задержки, вывод `sudo xgw pool stats` целиком
  (имён в нём нет), надписи панели без имён, счётчики, мегабайты, статусы, времена, строки
  помощника.

## 1. Подготовка (сессия 1)

Шаг 1.0. Предусловие — прошлая проверка закончена:

```bash
cd ~/zcod/xgw && git fetch -q && git log origin/freepool --format=%s | grep -c 'восстановление бесплатного пула'; systemctl list-timers --all --no-pager xgw-recov-guard.timer xgw-recov-unblock.timer | head -3; sudo nft list tables | grep -c xgw_recov; cd ~
```

Ожидается: `1` или больше; «0 timers listed»; `0`.

Если не так: первая строка `0` — **стоп**, сообщить заказчику. Таймер в списке или таблица есть —
**стоп**, сообщить заказчику (прошлая проверка не закончена).

Шаг 1.1. **Спроси заказчика** (дословно):

«Повторяю проверку того, как шлюз восстанавливает бесплатные серверы, — в другом порядке, чтобы
проверить путь, который в прошлый раз не сработал, — и, если захотите, оставлю «весь дом через
бесплатные серверы» надолго, чтобы набрать дневник. Нажатия в панели и осмотр экрана я делаю
сам, в управляемом браузере. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Если наблюдение за бесплатными серверами выключено, я включу его и подожду 30 минут.
(3) Я включу «весь дом через бесплатные серверы».
(4) Я остановлю службу XGW примерно на минуту и «состарю» её сохранённые проверки серверов —
как будто шлюз был выключен 4 часа. Интернет при этом идёт через Xray и не пропадает.
(5) Я выберу вручную бесплатный сервер, через который сейчас идёт дом, и на время (до 20 минут)
закрою к нему путь на этом шлюзе. Шлюз должен перейти на другой сервер и сам снять мой выбор;
открытые соединения могут на минуту-две подвиснуть.
(6) Срок «всего дома» после проверок: **А** — до 9 утра, **Б** — на сутки, **В** — на 6 часов,
**Г** — вернуть режим подписок сразу после проверок. По сроку страховочный таймер сам вернёт
режим подписок; если что-то не нравится — нажмите метку вверху панели («Через бесплатные серверы
▾») и «Вернуть режим подписок», это безопасно.
(7) По окончании я верну режим подписок, сниму выбор сервера вручную, если он останется, и верну
наблюдение в то состояние, в каком оно было до проверки.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 при выключенном наблюдении или против 3 — §4–§9 пропустить,
кроме §10 (в отчёте: «весь дом не включался»). Против 4 — пропустить §5. Против 5 — пропустить
§6 и §7. Без ответа на 6 — срок **Г**. Против 7 — §10 без смены режима наблюдения. **Запиши, на
что согласился заказчик, и срок (А, Б, В или Г).**

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-recov2" && chmod 700 "$HOME/xgw-recov2" && cd "$HOME/xgw-recov2" && cat > recovcheck.py <<'EOF'
"""XGW 0.2.0, бесплатный пул: восстановление (холодный старт, молчащий выбранный вручную
сервер, снятие ручного выбора) — помощник проверки. Читает состояние XGW (/run/xgw), базу
состояния (только чтение), рабочий конфиг Xray, итоги проверок пула, настройки и журнал со
стандартного ввода; печатает счётчики, коды стран, теги pool-<страна>-<начало id>, начала id,
итоги и да/нет — без имён серверов, устройств и подписок, адресов, ссылок и ключей. Состояние
меняют только три режима, по шагам ТЗ: block и unblock — временная таблица nftables inet
xgw_recov (сброс пакетов этой машины к одному серверу пула), age — сдвиг времени проверок
серверов «pool» назад при остановленном демоне. Время — секунды с 1970 (date +%s). Режимы:
units, pool, route, state, flow, members, tags, currentid, pinstate, watch on|back, block,
waitdrop, unblock, age, cold, events, eventsum, log."""
import ipaddress
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("RECOVCHECK_LIB", "/opt/xgw/lib")
NAME = re.compile("«[^»]*»")
TAG = re.compile(r"^pool-([a-z]{2})-([0-9a-f]{4,8})$")
MARKS = {"on": "бесплатный пул: весь дом через бесплатные серверы",
         "back": "режим подписок возвращён"}
GOALS = {"on": "on", "back": "observe"}
MANUAL = {"on": "держится", "down": "не отвечает — ведёт выбранный шлюзом", "": "нет"}
SWITCH = ("весь дом идёт через", " идут через ")
REASONS = (("— быстрее, чем", "на более быстрый"), ("— выбран вручную", "выбран вручную"),
           ("выбранный вручную не отвечает", "выбранный вручную молчит"),
           ("больше не в работе", "прежний вне состава"), ("» не отвечает", "прежний не отвечал"))
RELEASED = "больше не допущен"
LISTS = ("igareck", "mahdibland")
TABLE = "xgw_recov"
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


def pin_now(paths):
    try:
        from xgw import config

        return config.load(paths.config_file)[0].managed.free_pool_pin
    except Exception:  # помощник только смотрит: сбой чтения — «?»
        return "?"


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


def alive_of(flow):
    return {str(item.get("tag")): bool(item.get("alive")) for item in flow.get("servers") or []
            if isinstance(item, dict)}


def members(paths):
    work = read_json(paths.xray_config_file) or {}
    found = []
    for item in work.get("outbounds") or []:
        match = TAG.match(str(item.get("tag") or "")) if isinstance(item, dict) else None
        if match:
            found.append((match.group(0), match.group(2), item))
    return found


def records(paths):
    try:
        from xgw.freepool.store import PoolStore

        return PoolStore(paths).candidates()
    except Exception as exc:  # помощник только смотрит: сбой чтения — строкой, без падения
        print(f"итоги проверок не прочитаны: {type(exc).__name__}")
        return {}


def record_of(prefix, recs):
    found = [(key, value) for key, value in recs.items()
             if key.startswith(prefix) and not key.startswith("_") and isinstance(value, dict)]
    if not found:
        return "", {}
    return max(found, key=lambda item: float(item[1].get("checked_at") or 0))


def address(outbound):
    settings = outbound.get("settings") if isinstance(outbound.get("settings"), dict) else {}
    values = [item.get("address") for key in ("vnext", "servers")
              for item in settings.get(key) or [] if isinstance(item, dict)]
    values.append(settings.get("address"))
    for value in values:
        try:
            found = ipaddress.ip_address(str(value))
        except ValueError:
            continue
        if found.version == 4 and found.is_global:
            return str(found)
    return None


def nft():
    return shutil.which("nft") or "/usr/sbin/nft"


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
    last = rules[-1] if rules else {}
    print(f"режим пула: {cfg.free_pool.mode}; последнее правило → "
          f"{last.get('balancerTag') or last.get('outboundTag') or 'правил нет'}; несущий "
          f"канал: {'есть' if carrier else 'нет'}; серверов в «pool»: {len(members(paths))}")
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
elif mode == "members":
    _cfg, paths = xgw()
    flow = flow_of(read_json(paths.status_file) or {}) or {}
    alive, recs, now = alive_of(flow), records(paths), time.time()
    rows = members(paths)
    if not rows:
        print("серверов в «pool» нет")
    for tag, prefix, _outbound in rows:
        rec = record_of(prefix, recs)[1]
        checked = float(rec.get("checked_at") or 0)
        age = (f"{(now - checked) / 60:.0f} мин назад ({rec.get('verdict') or '—'})" if checked
               else "не проверялся")
        state = "жив" if alive.get(tag) else "молчит" if tag in alive else "нет в сводке"
        print(f"{tag}: {state}, проверка {age}"
              + ("  ← сейчас через него" if flow.get("tag") == tag else ""))
elif mode == "tags":
    _cfg, paths = xgw()
    for tag, _prefix, _outbound in members(paths):
        print(tag)
elif mode == "currentid":
    cfg, paths = xgw()
    match = TAG.match(str((flow_of(read_json(paths.status_file) or {}) or {}).get("tag") or ""))
    try:
        from xgw.freepool import traffic

        ids = [item.node.fingerprint for item in traffic.admitted(cfg, paths, time.time())]
    except Exception:  # старый код или сбой чтения: выбрать нечего
        ids = []
    found = [full for full in ids if match and full.startswith(match.group(2))]
    print(found[0][:10] if len(found) == 1 else "нет")
elif mode == "pinstate":
    _cfg, paths = xgw()
    pin = pin_now(paths)
    flow = flow_of(read_json(paths.status_file) or {}) or {}
    match = TAG.match(str(flow.get("tag") or ""))
    same = bool(pin and pin != "?" and match and pin.startswith(match.group(2)))
    print("выбор вручную в настройках: " + ("нет" if not pin else "?" if pin == "?" else
                                            "есть, это текущий сервер" if same
                                            else "есть, не текущий сервер"))
    print(f"выбран вручную в состоянии шлюза: {MANUAL.get(flow.get('manual') or '', '?')}")
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
    if reached is None:
        try:
            age = f"{time.time() - paths.status_file.stat().st_mtime:.0f} с назад"
        except OSError as exc:
            age = f"не прочитать ({type(exc).__name__})"
        status = read_json(paths.status_file) or {}
        print(f"файл состояния обновлён {age}; режим в нём: "
              f"{pool_of(status).get('mode') or 'сводки пула нет'}; состояние: "
              f"{status.get('state')}")
elif mode == "block":
    _cfg, paths = xgw()
    if run([nft(), "list", "table", "inet", TABLE])[0] == 0:
        print(f"таблица {TABLE} уже есть — сначала unblock")
        sys.exit(0)
    current = str((flow_of(read_json(paths.status_file) or {}) or {}).get("tag") or "")
    found = [(tag, address(outbound)) for tag, _prefix, outbound in members(paths)]
    pick, note = next(((tag, ip) for tag, ip in found if tag == current and ip), None), "текущий"
    if pick is None:
        pick = next(((tag, ip) for tag, ip in found if ip), None)
        note = "НЕ текущий: у текущего в конфиге нет адреса IPv4"
    if pick is None:
        print("заблокировать некого: у серверов «pool» в конфиге нет адресов IPv4")
        sys.exit(0)
    tag, ip = pick
    script = (f"table inet {TABLE} {{\n  chain out {{\n    type filter hook output priority 0; "
              f"policy accept;\n    ip daddr {ip} drop\n  }}\n}}\n")
    try:
        done = subprocess.run([nft(), "-f", "-"], input=script, text=True, capture_output=True,
                              timeout=30)
        code = done.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        code = type(exc).__name__
    if code != 0:
        print(f"блокировка не поставлена: {code}")
        sys.exit(0)
    Path("blocked-tag.txt").write_text(tag + "\n", encoding="utf-8")
    print(f"заблокирован {tag} ({note}); адрес не печатается")
elif mode == "waitdrop":
    _cfg, paths = xgw()
    tag = sys.argv[2] if len(sys.argv) > 2 else ""
    match = TAG.match(tag)
    if not match:
        print("тег сервера не задан")
        sys.exit(0)
    since, limit = arg(3, time.time()), arg(4, 1200.0)
    start, last = time.time(), None
    while True:
        flow = flow_of(read_json(paths.status_file) or {}) or {}
        alive = alive_of(flow)
        inside = any(item[0] == tag for item in members(paths))
        rec = record_of(match.group(2), records(paths))[1]
        again = (f"перепроверен ({rec.get('verdict') or '—'})"
                 if float(rec.get("checked_at") or 0) >= since else "не перепроверялся")
        state = "жив" if alive.get(tag) else "молчит" if tag in alive else "нет в сводке"
        pin = pin_now(paths)
        line = (f"{tag}: {'в составе' if inside else 'ВНЕ состава'}, {state}, {again}; выбор "
                f"вручную: {'?' if pin == '?' else 'есть' if pin else 'нет'}; сейчас через "
                f"{flow.get('tag') or '—'}" + ("; ЗАКРЫТО" if flow.get("closed") else ""))
        if line != last:
            print(f"+{time.time() - since:4.0f} с: {line}", flush=True)
            last = line
        if not inside:
            print(f"{tag} вне состава через {time.time() - since:.0f} с после блокировки")
            break
        if time.time() - start > limit:
            print(f"{tag} всё ещё в составе через {limit:.0f} с")
            break
        time.sleep(5)
elif mode == "unblock":
    print("блокировка снята" if run([nft(), "delete", "table", "inet", TABLE])[0] == 0
          else "таблицы блокировки нет")
elif mode == "age":
    _cfg, paths = xgw()
    hours = arg(2, 4.0)
    if show("xgw.service", "ActiveState") == "active":
        print("демон xgw работает — сдвигать нельзя (сначала остановить его по шагу ТЗ)")
        sys.exit(0)
    try:
        from xgw.freepool.store import PoolStore

        path = PoolStore(paths).dir / "candidates.json"
    except Exception as exc:  # старый код: без сдвига, строкой
        print(f"итоги проверок не найдены: {type(exc).__name__}")
        sys.exit(0)
    data = read_json(path)
    rows = members(paths)
    if not isinstance(data, dict) or not rows:
        print("сдвигать нечего: итогов проверок или серверов в «pool» нет")
        sys.exit(0)
    aged = set()
    for _tag, prefix, _outbound in rows:
        for key, rec in data.items():
            if (key.startswith(prefix) and not key.startswith("_") and isinstance(rec, dict)
                    and rec.get("verdict") in ("OK", "SLOW") and rec.get("checked_at")):
                rec["checked_at"] = float(rec["checked_at"]) - hours * 3600
                aged.add(prefix)
    temp = path.with_name(".candidates.recov.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)
    print(f"проверки серверов «pool» сдвинуты на {hours:g} ч назад: {len(aged)} из {len(rows)}; "
          f"права файла: {oct(path.stat().st_mode & 0o777)[2:]}")
elif mode == "cold":
    _cfg, paths = xgw()
    since = arg(2, time.time() - 600)
    try:
        from xgw.freepool import providers

        lists = set(providers.LIST_PROVIDERS)
    except Exception:  # старый код: имена списков по умолчанию
        lists = set(LISTS)
    recs, rows = records(paths), members(paths)
    now_tags = {tag: prefix for tag, prefix, _outbound in rows}
    before = []
    if len(sys.argv) > 3:
        try:
            before = [line.strip() for line in Path(sys.argv[3]).read_text(
                encoding="utf-8").splitlines() if TAG.match(line.strip())]
        except OSError as exc:
            print(f"файл прежнего состава не читается: {type(exc).__name__}")
    base = before or list(now_tags)
    old = [TAG.match(tag).group(2) for tag in base]
    every = old + list(now_tags.values())
    after = sorted((float(value.get("checked_at") or 0), key, value)
                   for key, value in recs.items()
                   if not key.startswith("_") and isinstance(value, dict)
                   and float(value.get("checked_at") or 0) >= since)
    kept = [tag for tag in base if tag in now_tags]
    again = [tag for tag in kept
             if any(item[1].startswith(TAG.match(tag).group(2)) for item in after)]
    print(f"было в «pool» до остановки: {len(base)}; из них в составе сейчас: {len(kept)}, "
          f"выбыли: {len(base) - len(kept)}; новых в составе: {len(set(now_tags) - set(base))}")
    print(f"из оставшихся перепроверены после запуска: {len(again)} из {len(kept)}")
    done = [item for item in after if any(item[1].startswith(prefix) for prefix in old)]
    if done:
        last = done[-1][0]
        others = [item for item in after if item[0] <= last
                  and not any(item[1].startswith(prefix) for prefix in every)]
        print(f"последняя проверка прежнего состава — через {last - since:.0f} с после запуска; "
              f"до неё прочих проверок {len(others)}, из них серверов списков "
              f"{sum(1 for item in others if item[2].get('provider') in lists)}")
    print(f"всего проверок после запуска: {len(after)}")
elif mode == "events":
    _cfg, paths = xgw()
    for ts, kind, detail in events_since(paths, arg(2, time.time() - 3600)):
        if kind == "freepool":
            print(f"{stamp(ts)} {NAME.sub('«<сервер>»', detail)}")
        elif kind == "apply" and "бесплатный пул" in detail:
            print(f"{stamp(ts)} применение: {applied_text(detail)}")
elif mode == "eventsum":
    _cfg, paths = xgw()
    since = arg(2, time.time() - 3600)
    counts = {label: 0 for _word, label in REASONS}
    first = bare = closures = rebuilds = released = 0
    modes, after_switch = [], False
    for ts, kind, detail in events_since(paths, since):
        if kind == "apply" and "бесплатный пул" in detail:
            rebuilds += 1
        if kind != "freepool":
            continue
        if RELEASED in detail:
            released += 1
        elif MARKS["on"] in detail or MARKS["back"] in detail or "после перезагрузки" in detail:
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
          + f"; БЕЗ ПРИЧИНЫ: {bare}; «закрыто»: {closures}; выбор вручную снят: {released}; "
          f"применений ради пула: {rebuilds}")
    print("режим: " + ("; ".join(modes) if modes else "не менялся"))
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, word in (
        ("перепроверка молчащего вне очереди", "перепроверка вне очереди"),
        ("списки обновлены при закрытом пуле", "обновляются вне расписания"),
        ("проверок серверов пула", "бесплатный пул: проверка "),
        ("проба ядра опоздала под нагрузкой (сервер пула жив)", "сервер пула жив"),
        ("сервер бесплатного пула не закреплён", "сервер бесплатного пула не закреплён"),
        ("выбор вручную не снят (ошибка)", "выбор вручную не снят"),
        ("откат на last-good", "last-good"),
        ("шаг пула не выполнен", "бесплатный пул: шаг не выполнен"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | pool | route | state | flow | members | tags | currentid | pinstate | "
          "watch on|back | block | waitdrop | unblock | age | cold | events | eventsum | log")
EOF
python3 -c "import hashlib;d=open('recovcheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `2b9acacab4a72fa3`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки:

```bash
cd "$HOME/xgw-recov2" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units pool route state pinstate; do sudo python3 -I recovcheck.py $m; done | tee -a before.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; первая строка
`xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать, какая**; четыре
службы `active`; `route` — «совпадает с режимом: да»; `pinstate` — «выбор вручную в настройках:
…» — **записать** (может остаться от прошлых проверок).

Если не так: первая строка `xgw pool` — «весь дом через бесплатные серверы» — выполнить
`sudo xgw pool mode observe`, подождать минуту и повторить шаг.

## 2. Установка (сессия 1)

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def _drop_pool_pin' src/xgw/daemon.py && grep -q 'def _ceiling' src/xgw/freepool/pool.py && grep -q 'def pin_gone' src/xgw/freepool/traffic.py && echo "правка в коде: есть"; cd "$HOME/xgw-recov2"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-recov2/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-recov2/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-recov2/install.txt"; cd "$HOME/xgw-recov2"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 3 минуты:

```bash
sleep 180; cd "$HOME/xgw-recov2" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee after-install.txt; for m in units route state; do sudo python3 -I recovcheck.py $m; done | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I recovcheck.py log | tee log-install.txt
```

Ожидается: `HEALTHY`, перехват включён, строки «Ожидает окна перезапуска» нет; четыре службы
`active`; `route` — «совпадает с режимом: да»; журнал: «Traceback: 0».

Если не так: не `HEALTHY` — подожди 2 минуты и повтори; снова нет — запиши и продолжай.

## 3. Наблюдение (сессия 1)

Шаг 3.1. Только если в шаге 1.3 наблюдение было **выключено** (иначе — пропустить, записать «уже
было включено» и подождать 5 минут):

```bash
cd "$HOME/xgw-recov2" && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; sleep 1800; sudo python3 -I recovcheck.py pool | tee -a mode-on.txt
```

(Если терминал обрывает длинные команды — после первой строки выполни `sleep 110` 17 раз, затем
`sudo python3 -I recovcheck.py pool`.)

Ожидается: «Наблюдение за бесплатным пулом включено: …»; через 30 минут — «пригодно» больше 2.

Если не так: «пригодно» 2 или меньше — подожди ещё 30 минут и повтори `pool`; снова не больше 2 —
§4–§9 пропустить («допущенных серверов меньше трёх»), перейти к §10.

## 4. Весь дом (сессия 1)

Шаг 4.1. Страховочный таймер — **до** включения «всего дома». Выполни **один** блок — по сроку
из шага 1.1.

Срок **А** (до 9 утра):

```bash
cd "$HOME/xgw-recov2" && sudo systemd-run --on-calendar='*-*-* 09:00:00' --unit=xgw-recov-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-recov-guard.timer | head -3 | tee -a guard.txt
```

Срок **Б** (сутки):

```bash
cd "$HOME/xgw-recov2" && sudo systemd-run --on-active=24h --unit=xgw-recov-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-recov-guard.timer | head -3 | tee -a guard.txt
```

Срок **В** (6 часов):

```bash
cd "$HOME/xgw-recov2" && sudo systemd-run --on-active=6h --unit=xgw-recov-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-recov-guard.timer | head -3 | tee -a guard.txt
```

Срок **Г** (сразу после проверок; таймер — на 2 часа):

```bash
cd "$HOME/xgw-recov2" && sudo systemd-run --on-active=2h --unit=xgw-recov-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-recov-guard.timer | head -3 | tee -a guard.txt
```

Ожидается: «Running timer as unit: xgw-recov-guard.timer» и строка таймера с временем
срабатывания — **записать его**.

Если не так: таймера нет — **стоп** для §4–§9 (перейти к §10).

Шаг 4.2. Панель. Ссылка входа (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком (окно не меньше 1280×800),
подожди 5 секунд, нажми вкладку **«Бесплатные серверы»**, подожди 5 секунд, снимок.

Шаг 4.3. Включение «всего дома».
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-recov2" && date +%s > t-on.txt && echo "метка записана: $(date '+%T')"
```

2. На вкладке «Бесплатные серверы» нажми **«Весь дом через бесплатные»**.
3. Снимок; **J4** — `true | Пустить весь дом через бесплатные серверы? | Весь дом через
   бесплатные`.
4. Нажми в окне **«Весь дом через бесплатные»**.
5. **Сразу** выполни (около 4 минут):

```bash
cd "$HOME/xgw-recov2" && sudo python3 -I recovcheck.py watch on "$(cat t-on.txt)" | tee watch-on.txt; sleep 60; for m in route members pinstate; do sudo python3 -I recovcheck.py $m; done | tee on.txt; sudo python3 -I recovcheck.py events "$(cat t-on.txt)" | tee events-on.txt; sudo python3 -I recovcheck.py eventsum "$(cat t-on.txt)" | tee -a events-on.txt
```

Ожидается:
- `watch`: «нажатие: …»; строки «+N с: режим on: сейчас через pool-XX-… (XX), …»; «ЗАКРЫТО»
  замеров: 0; «режим on в состоянии шлюза — с +N с»;
- `route` — «последнее правило → pool; несущий канал: есть; серверов в «pool»: N» (N — от 3 до 8,
  **записать**), «совпадает с режимом: да»;
- `members` — N строк «pool-XX-…: жив, проверка M мин назад (OK)» (или SLOW), у одной — «← сейчас
  через него»;
- `pinstate` — записать обе строки;
- события и `eventsum` — записать; если в шаге 1.3 выбор вручную был, возможна строка «…
  выбранный вручную сервер «<сервер>» больше не допущен (…) — сервер снова выбирает шлюз»
  (сервер прошлой проверки не прошёл перепроверку) — это **ожидаемо**, записать.

Если не так: «сейчас через» не появилось за три минуты — раздел «Если что-то пошло не так».
«НЕ появился за 3 минуты» при «сейчас через …» в строках — **не по ожиданию**: запиши строку
«файл состояния обновлён …» и продолжай. N меньше 3 — §6 и §7 пропустить (записать «серверов в
работе меньше трёх»).

Шаг 4.4. **Действие:** обнови страницу (F5), подожди 5 секунд, снимок, **J1** и **J9**.

Ожидается: J1 — `BUTTON | Через бесплатные серверы | false`; J9 — `Бесплатный сервер | N Мбит/с |
задержка есть` (сервер ещё не замерен — «скорости нет», запиши).

## 5. Холодный старт (сессия 1)

Шаг 5.1. **Скажи заказчику** (дословно): «Останавливаю службу XGW примерно на минуту и
«состариваю» её проверки серверов — как будто шлюз был выключен 4 часа. Интернет идёт через Xray
и не должен пропасть.»

Шаг 5.2. Состав до остановки, остановка, сдвиг проверок, запуск:

```bash
cd "$HOME/xgw-recov2" && sudo python3 -I recovcheck.py tags > members-before.txt; wc -l < members-before.txt | tee cold-before.txt; sudo python3 -I recovcheck.py members | tee -a cold-before.txt; date +%s > t-stop.txt; sudo systemctl stop xgw; sleep 5; systemctl is-active xgw | tee -a cold-before.txt; sudo python3 -I recovcheck.py age 4 | tee age.txt; sudo python3 -I recovcheck.py members | tee -a age.txt; date +%s > t-start.txt; sudo systemctl start xgw; sleep 5; systemctl is-active xgw | tee -a age.txt
```

Ожидается: первая строка — число K (серверов в «pool», **записать**); `members` — K строк;
`inactive` (демон остановлен); «проверки серверов «pool» сдвинуты на 4 ч назад: K из K; права
файла: 600»; `members` — у всех «проверка ~240 мин назад (…)» и больше; последняя строка —
`active` (демон снова работает).

Если не так: «демон xgw работает — сдвигать нельзя» — выполнить `sudo systemctl start xgw`,
записать и перейти к §6. Последняя строка не `active` — **сразу** `sudo systemctl start xgw`,
подождать 10 секунд, `systemctl is-active xgw`; снова не `active` — раздел «Если что-то пошло не
так». «сдвинуты … M из K» при M меньше K — запиши (у части серверов последняя проверка не OK).

Шаг 5.3. Через 4 минуты — что стало с составом:

```bash
sleep 240; cd "$HOME/xgw-recov2" && sudo python3 -I recovcheck.py cold "$(cat t-start.txt)" members-before.txt | tee cold.txt; for m in route flow members; do sudo python3 -I recovcheck.py $m; done | tee -a cold.txt; sudo python3 -I recovcheck.py events "$(cat t-stop.txt)" | tee events-cold.txt; sudo python3 -I recovcheck.py eventsum "$(cat t-stop.txt)" | tee -a events-cold.txt; sudo journalctl -u xgw --since "@$(cat t-stop.txt)" --no-pager | sudo python3 -I recovcheck.py log | tee log-cold.txt
```

Ожидается:
- `cold` — «было в «pool» до остановки: K; из них в составе сейчас: M, выбыли: K−M; новых в
  составе: …» (M — обычно K; выбыть может сервер, не прошедший перепроверку, — записать); «из
  оставшихся перепроверены после запуска: M из M»; «последняя проверка прежнего состава — через
  T с после запуска; до неё прочих проверок P, из них серверов списков **0**»;
- `route` — «серверов в «pool»: …» (не 0), «совпадает с режимом: да»;
- `flow` — «режим on: сейчас через pool-… …» (не «ЗАКРЫТО»);
- `members` — у прежних серверов «проверка 0–4 мин назад (…)»;
- `eventsum` — ««закрыто»: 0»;
- журнал: «Traceback: 0», «шаг пула не выполнен: 0».

Если не так: `route` — серверов в «pool» 0 или `flow` — «ЗАКРЫТО» — **дефект «холодный старт
закрыл дом»**: запиши строки `events` и `members`. «перепроверены … R из M» при R меньше M —
подожди 3 минуты и повтори только `cold`; снова меньше — запиши. «из них серверов списков»
больше 0 — **не по ожиданию**, запиши.

## 6. Молчащий выбранный вручную сервер (сессия 1)

Шаг 6.1. **Скажи заказчику** (дословно): «Выбираю вручную сервер, через который сейчас идёт
дом, и закрываю к нему путь на этом шлюзе — до 20 минут. Шлюз должен перейти на другой сервер
и снять мой выбор; открытые соединения могут на минуту-две подвиснуть.»

Шаг 6.2. Выбор текущего сервера вручную:

```bash
cd "$HOME/xgw-recov2" && sudo python3 -I recovcheck.py currentid | tee current-id.txt; sudo xgw pool pin "$(cat current-id.txt)" 2>&1 | sed -E 's/«[^»]*»/«<сервер>»/g' | tee pin.txt; sleep 30; sudo python3 -I recovcheck.py pinstate | tee -a pin.txt
```

Ожидается: первая строка — 10 шестнадцатеричных знаков (начало id, **записать**); ответ
`xgw pool pin` — «Выбран «<сервер>» (XX): трафик пула идёт через него, пока он отвечает; молчит —
через выбранный шлюзом»; `pinstate` — «выбор вручную в настройках: есть, это текущий сервер»,
«выбран вручную в состоянии шлюза: держится».

Если не так: первая строка «нет» или `xgw pool pin` — «Такого сервера среди допущенных нет…» —
подожди 2 минуты и повтори шаг один раз; снова так — записать и продолжить §6.3 без выбора
вручную (снятия выбора в 6.4 тогда не будет).

Шаг 6.3. Страховка снятия, метка и блокировка (одной командой):

```bash
cd "$HOME/xgw-recov2" && sudo systemd-run --on-active=40min --unit=xgw-recov-unblock /usr/sbin/nft delete table inet xgw_recov 2>&1 | tee unblock-guard.txt; date +%s > t-block.txt; sudo python3 -I recovcheck.py block | tee block.txt; sudo chown "$(id -u):$(id -g)" blocked-tag.txt 2>/dev/null; cat blocked-tag.txt 2>/dev/null
```

Ожидается: «Running timer as unit: xgw-recov-unblock.timer»; «заблокирован pool-XX-… (текущий);
адрес не печатается»; последняя строка — тот же тег (**записать**).

Если не так: «(НЕ текущий: …)» — продолжай: смены сервера и снятия выбора в 6.4 может не быть,
это не дефект. «заблокировать некого» или «блокировка не поставлена» — записать, остановить
страховку `sudo systemctl stop xgw-recov-unblock.timer` и перейти к §8.

Шаг 6.4. Ждём выбывания (до 20 минут), затем — через минуту — события, дневник и журнал:

```bash
cd "$HOME/xgw-recov2" && sudo python3 -I recovcheck.py waitdrop "$(cat blocked-tag.txt)" "$(cat t-block.txt)" 1200 | tee waitdrop.txt; sleep 70; sudo python3 -I recovcheck.py events "$(cat t-block.txt)" | tee events-block.txt; sudo python3 -I recovcheck.py eventsum "$(cat t-block.txt)" | tee -a events-block.txt; sudo python3 -I recovcheck.py pinstate | tee -a events-block.txt; sudo xgw pool stats --days 1 2>&1 | tee stats-block.txt; sudo journalctl -u xgw --since "@$(cat t-block.txt)" --no-pager | sudo python3 -I recovcheck.py log | tee log-block.txt
```

(Если терминал обрывает команды дольше 2 минут — выполни `waitdrop` с лимитом 110 несколько раз
подряд, пока не появится строка «… вне состава …» или пока с метки не пройдёт 20 минут, затем
`sleep 70` и остальные команды блока.)

Ожидается:
- `waitdrop`: строки «+N с: pool-XX-…: в составе, …» по мере изменений, по порядку:
  1. «… молчит, не перепроверялся; выбор вручную: есть; сейчас через pool-YY-…» — шлюз перешёл
     на другой сервер (обычно до 3 минут);
  2. «… молчит, перепроверен (<итог>)» — **примерно через 6–13 минут** после метки (не раньше
     5 минут молчания и не раньше 15 минут от прошлой проверки); итог — **не OK и не SLOW**
     (TIMEOUT, ошибка подключения…);
  3. «… выбор вручную: нет …» — вскоре после перепроверки (до 2 минут);
  4. «… ВНЕ состава …» и итоговая строка «pool-XX-… вне состава через N с после блокировки»
     (N — до 1200);
  «ЗАКРЫТО» — ни в одной строке;
- события: смена «… весь дом идёт через «<сервер>» (XX)…: выбранный вручную не отвечает — сервер
  выбирает шлюз» и строка «бесплатный пул: выбранный вручную сервер «<сервер>» больше не допущен
  (последняя проверка не прошла) — сервер снова выбирает шлюз»;
- `eventsum` — «выбранный вручную молчит 1», «БЕЗ ПРИЧИНЫ: 0», «закрыто»: 0, «выбор вручную
  снят: 1», «применений ради пула: 1» или больше;
- `pinstate` — «выбор вручную в настройках: нет», «выбран вручную в состоянии шлюза: нет»;
- `xgw pool stats` — у сегодняшнего дня строка «  восстановление: молчащих перепроверено вне
  очереди 1» (или больше), «выбыло из состава» — 1 или больше;
- журнал: «перепроверка молчащего вне очереди: 1» (или больше), «Traceback: 0», «шаг пула не
  выполнен: 0», «выбор вручную не снят (ошибка): 0».

Если не так: «перепроверен» раньше 5 минут после метки — **не по ожиданию** (запиши: путь «вне
очереди» снова не задет); «перепроверен (OK)» или «(SLOW)» — **не по ожиданию** (проверка шлюза
прошла мимо блокировки). «всё ещё в составе через 1200 с» — **дефект «молчащий не выбыл»**.
«выбор вручную: есть» до конца при перепроверке не OK — **дефект «выбор не снят»**. «ЗАКРЫТО» —
запиши время.

## 7. Снятие блокировки (сессия 1)

Шаг 7.1.

```bash
cd "$HOME/xgw-recov2" && sudo python3 -I recovcheck.py unblock | tee unblock.txt; sudo systemctl stop xgw-recov-unblock.timer; systemctl list-timers --all --no-pager xgw-recov-unblock.timer | head -3 | tee -a unblock.txt; sudo nft list tables | grep -c xgw_recov | tee -a unblock.txt; for m in flow route members; do sudo python3 -I recovcheck.py $m; done | tee after-block.txt
```

Ожидается: «блокировка снята»; «0 timers listed»; `0` (таблицы больше нет); `flow` — «режим on:
сейчас через pool-…»; `route` — «серверов в «pool»: …»; заблокированного тега в `members` нет.

**Скажи заказчику** (дословно): «Путь к серверу открыт.»

## 8. Долгое наблюдение

Шаг 8.1. Срок **Г** — сразу к §9 (сессия одна). Срок **А/Б/В** — **скажи заказчику** (дословно,
подставив время таймера из шага 4.1): «Проверки закончены. Весь дом идёт через бесплатные
серверы. Страховочный таймер вернёт режим подписок в <время>. Пользуйтесь интернетом как обычно.
Если что-то не нравится — нажмите метку вверху панели «Через бесплатные серверы ▾» и «Вернуть
режим подписок». Когда закончим — напишите мне, я сниму итоги.»

Запиши время. **Сессия 1 окончена.** Отчёт пока не пиши; файлы в `$HOME/xgw-recov2` не удаляй.

Шаг 8.2 (сессия 2 — когда скажет заказчик). Помощник на месте и состояние:

```bash
cd "$HOME/xgw-recov2" && python3 -c "import hashlib;d=open('recovcheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; date '+%F %T' | tee end.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Ожидает окна' | tee -a end.txt; for m in units flow state route pinstate; do sudo python3 -I recovcheck.py $m; done | tee -a end.txt; systemctl list-timers --all --no-pager xgw-recov-guard.timer | head -3 | tee -a end.txt
```

Ожидается: сумма — как в шаге 1.2; `HEALTHY`; четыре службы `active`; `flow` — «режим on: сейчас
через pool-XX-… …» (наблюдение ещё идёт) **или** «режим observe: через пул никто» (сработал
таймер или заказчик вернул режим сам — записать, что именно: таймер в списке есть — вернул
заказчик; «0 timers listed» — сработал таймер); `route` — «совпадает с режимом: да».

Если не так: сумма другая — файл помощника изменился: **стоп**, сообщить заказчику.

Шаг 8.3. Итоги дневника, событий и журнала:

```bash
cd "$HOME/xgw-recov2" && sudo xgw pool stats --days 2 2>&1 | tee stats-end.txt; sudo python3 -I recovcheck.py eventsum "$(cat t-on.txt)" | tee eventsum-end.txt; sudo journalctl -u xgw --since "@$(cat t-on.txt)" --no-pager | sudo python3 -I recovcheck.py log | tee log-end.txt
```

Ожидается (записать **целиком** в отчёт — имён в этих строках нет): `xgw pool stats` — по строке
на день с пятью строками у дней с трафиком через пул; `eventsum` — «БЕЗ ПРИЧИНЫ: 0» и строка
режима; журнал: «Traceback: 0», «откат на last-good: 0», остальные числа — записать.

Если не так: «БЕЗ ПРИЧИНЫ» больше 0 — **дефект «смена без причины»**: выполни
`sudo python3 -I recovcheck.py events "$(cat t-on.txt)" | tee events-end.txt` и приложи строки
вокруг смен без причины.

Шаг 8.4. **Спроси заказчика** (дословно): «Весь дом шёл через бесплатные серверы с <время
включения из шага 4.3>. Расскажите, пожалуйста: (1) открывались ли сайты как обычно; (2) как шло
видео (YouTube и т. п.); (3) были ли обрывы или «ничего не открывается» — примерно когда и
надолго; (4) что-то работало хуже, чем через подписку; (5) возвращали ли вы режим подписок сами
и почему?» Ответы — дословно, без имён.

## 9. Возврат режима подписок

Шаг 9.1. Если `flow` (шаг 8.2) — «режим observe» (режим уже вернулся), выполни только:
`cd "$HOME/xgw-recov2" && sudo systemctl stop xgw-recov-guard.timer; for m in route state pinstate; do sudo python3 -I recovcheck.py $m; done | tee back.txt`
(ошибка «not loaded» — норма) и переходи к шагу 9.2. Иначе:
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-recov2" && date +%s > t-back.txt && echo "метка записана: $(date '+%T')"
```

2. Открой панель (ссылка — `sudo xgw panel 2>&1 | head -1`, если вкладка закрыта), нажми
   **метку вверху справа** («Через бесплатные серверы ▾»). Снимок; **J4** — `true | Вернуть
   режим подписок? | Вернуть режим подписок`.
3. Нажми в окне **«Вернуть режим подписок»**.
4. **Сразу** выполни:

```bash
cd "$HOME/xgw-recov2" && sudo python3 -I recovcheck.py watch back "$(cat t-back.txt)" | tee watch-back.txt; sudo systemctl stop xgw-recov-guard.timer; systemctl list-timers --all --no-pager xgw-recov-guard.timer | head -3 | tee guard-off.txt; for m in route state pinstate; do sudo python3 -I recovcheck.py $m; done | tee back.txt; sudo xgw pool stats --days 1 2>&1 | tee stats-back.txt
```

Ожидается: «нажатие: …»; «режим observe: через пул никто»; «ЗАКРЫТО» замеров: 0; «0 timers
listed»; `route` — «последнее правило → auto; несущий канал: нет; серверов в «pool»: 0»,
«совпадает с режимом: да»; `xgw pool stats` — записать **целиком**.

Шаг 9.2. Если `pinstate` в 9.1 — «выбор вручную в настройках: есть…»:

```bash
cd "$HOME/xgw-recov2" && sudo xgw pool pin auto 2>&1 | tee pin-auto.txt; sudo python3 -I recovcheck.py pinstate | tee -a pin-auto.txt
```

Ожидается: «Сервер бесплатного пула снова выбирает шлюз»; «выбор вручную в настройках: нет».
Выбора нет — шаг пропустить, записать «выбора не было».

## 10. Секреты и режим как до проверки

Шаг 10.1. Секреты и таблица блокировки:

```bash
cd "$HOME/xgw-recov2" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt; sudo nft list tables | grep -c xgw_recov | tee -a secrets.txt
```

Ожидается: `0` и `0`. Первое больше — **дефект** (строки журнала в отчёт не копировать); второе
больше — выполнить `sudo python3 -I recovcheck.py unblock` и записать.

Шаг 10.2. Если в шаге 1.3 наблюдение было **выключено** — **действие в браузере:** вкладка
«Бесплатные серверы» → **«Выключить»**, снимок (кнопка сменилась на «Включить наблюдение»). Было
включено — ничего не менять, записать «оставлено включённым».

Шаг 10.3. Итог:

```bash
sleep 60; cd "$HOME/xgw-recov2" && date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units pool route state; do sudo python3 -I recovcheck.py $m; done | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I recovcheck.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4, строки «Ожидает окна
перезапуска» нет; четыре службы `active`; режим — как был до проверки; `route` — «совпадает с
режимом: да»; журнал: «откат на last-good: 0», «Traceback: 0».

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- В сессии 1 в режиме «весь дом» пропал интернет или доступ, или заказчик не отвечает **2
  минуты** — **сразу**, по порядку: `sudo python3 -I recovcheck.py unblock`,
  `sudo xgw pool mode observe`, `sudo systemctl stop xgw-recov-guard.timer xgw-recov-unblock.timer`
  (ошибка «not loaded» — норма); если `systemctl is-active xgw` — не `active`, то
  `sudo systemctl start xgw`. Записать время и строки `sudo python3 -I recovcheck.py flow` и
  `sudo python3 -I recovcheck.py route`. Дальше — шаг 9.2, §10 и отчёт. «Весь дом» больше не
  включать.
- Заказчик во время долгого наблюдения вернул режим подписок сам — это не сбой: в сессии 2
  записать время (из `eventsum`) и его причину (шаг 8.4).
- Не `HEALTHY` больше 5 минут, службы не `active` (кроме остановки `xgw` в шаге 5.2) —
  записать, сообщить заказчику, ничего не перезапускать.
- Браузер не открывает панель или кнопки не нажимаются — снимок, сообщить заказчику и попросить
  нажать то же самое вручную; в отчёте пометить «нажато заказчиком».

## 11. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-recovery2-<ДАТА>.md` в клоне (`<ДАТА>` — дата
начала проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, восстановление бесплатного пула —
повтор» и `git push` в `freepool`. Только этот файл (`git add` только его). Без имён серверов,
устройств и подписок, адресов, доменов, токена и строк журнала. Шаблон (заполни каждую ячейку;
пропущенное — «не выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — восстановление бесплатного пула, повтор и долгое наблюдение

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>, срок <А/Б/В/Г>.
recovcheck.py: <сумма>. Наблюдение до проверки: <…>. Выбор вручную до проверки: <…>. Ядра:
Xray <…>, sing-box <…>. Исполнитель: <модель>; нажатия и снимки — управляемым браузером <да/частично>.

## Итог
| Холодный старт: было / осталось / перепроверены / посторонних списков до них | Молчащий: смена (с) / перепроверка (с, итог) / выбор снят (с) / вне состава (с) | «Вне очереди» в журнале и дневнике | «Закрыто» | Долгое наблюдение: с — по, через пул / закрыто, смен (по причинам) | Заказчик |
|---|---|---|---|---|---|
| <8 / 8 / 8 из 8 / 0> | <90 / 640, TIMEOUT / 700 / 760> | <1 / 1> | <0> | <… или «срок Г»> | <кратко> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.0 предусловие | … | … |
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 наблюдение | … | … |
| 4.1 страховка | … | … |
| 4.3 включение | … | … |
| 4.4 панель | … | … |
| 5.2 остановка и сдвиг | … | … |
| 5.3 холодный старт | … | … |
| 6.2 выбор вручную | … | … |
| 6.3 блокировка | … | … |
| 6.4 молчащий: вне очереди, снятие выбора, выбывание | … | … |
| 7.1 снятие блокировки | … | … |
| 8.2–8.4 долгое наблюдение | … | … |
| 9 возврат и выбор вручную | … | … |
| 10 секреты и итог | … | … |

## Вывод `sudo xgw pool stats` (шаг 8.3 или 9.1, целиком)
<…>

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-recov2/…); результаты J1, J4, J9; что видно
  на снимках словами; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
