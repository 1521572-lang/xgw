# Проверка XGW 0.2.0: YouTube через сервер и прежний сервер пула после перезапуска демона

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, делаешь **снимок
  экрана** и смотришь на него, выполняешь JavaScript в консоли страницы.

Сессия 1 (§1–§7, около двух часов, из них 30 минут — ожидание) — установка, проверки YouTube в
режиме подписок и в режиме «весь дом через бесплатные серверы», принудительная смена сервера из-за
YouTube, перезапуск демона, YouTube у заказчика. Дальше — по сроку, который выберет заказчик (шаг
1.1): **Г** — сразу возврат (§9, §10, отчёт); **А/Б/В** — «весь дом» остаётся на долгое
наблюдение, а сессия 2 (§8.2–§10, около 20 минут) — когда скажет заказчик. Между сессиями файлы в
`$HOME/xgw-yt1` не удалять.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J1, J4, J9) — выполни её в
   консоли страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-yt1/…`. Время шага — по выводу `date` в команде,
   не по памяти.
5. **Метка времени — до нажатия или правки.** Где в шаге есть команда «Метка», выполни её
   **перед** нажатием в браузере (или перед командой, которая меняет настройку), а команду
   проверки — **после**.
6. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
7. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
8. Экземпляр этого ТЗ держи в `$HOME/xgw-yt1/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2.
9. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `ytcheck.py` выводит `Traceback` — запиши режим и последнюю строку
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

### Что нового (ASSUMPTIONS п. 277) и зачем проверка

В прошлой проверке заказчик сказал, что YouTube через бесплатный сервер «грузился с проблемами»,
с буферизацией, — и сам сменил сервер, хотя по замеру скорости у сервера было 93 Мбит/с. Решение
заказчика: если сервер не пропускает трафик YouTube, его надо менять на другой.

1. **Проверка YouTube через сервер.** Шлюз через служебный вход сервера запрашивает сайт YouTube и
   его видеосеть (ответ без тела) и качает 4 МБ с серверов Google. «Не пропускает YouTube» — нет
   ответа, ошибка соединения или код ошибки; «тормозит на YouTube» — скорость с серверов Google
   вместе с трафиком клиентов через этот сервер ниже порога `speed.youtube_mbps` (5 Мбит/с).
2. **Кого и когда.** Сервер, через который идёт трафик (основной или выбранный вручную сервер
   подписки; у пула — ведущий), — раз в 30 минут, после неудачи — через минуту; остальные живые
   — раз в 6 часов, не чаще одной проверки в 2 минуты. В режиме «весь дом» серверы подписки не
   проверяются (подписка — только несущий канал).
3. **Смена.** Две неудачи подряд — сервер плох для YouTube: он не выбирается, пока есть живой
   без этой отметки; ведущий сменяется с событием «… — «<сервер>» тормозит на YouTube (…)» или
   «… не пропускает YouTube». Плохи все — сервер прежний. Три смены из-за YouTube за час —
   смены приостанавливаются на 2 часа (событие «YouTube плох через 3 сервера подряд за час…»).
   Выбранный вручную сервер шлюз не меняет — только сообщает.
4. **Дефект 1 прошлого отчёта.** После перезапуска демона событие «весь дом идёт через «…»»
   писалось второй раз для того же сервера. Теперь после запуска демон остаётся на прежнем
   сервере пула, пока тот жив: без события, в журнале — «бесплатный пул после запуска демона —
   через прежний …».

### Как проверяется

- **Естественные итоги (§2–§4).** Помощник (режим `yt`) читает итоги проверок YouTube из базы
  шлюза (только чтение) и печатает их по тегам серверов: проходит / тормозит / не пропускает,
  скорость с серверов Google, у серверов пула — и скорость замера (Cloudflare).
- **Принудительная смена (§5).** Помощник (режим `threshold 1000`) временно ставит в настройках
  порог 1000 Мбит/с и срок проверки ведущего 5 минут: для шлюза каждый бесплатный сервер
  «тормозит на YouTube». Ведущий должен смениться с причиной, затем следующий, а на третьей смене
  — пауза смен. Прежний файл настроек остаётся копией рядом, `threshold back` возвращает его.
- **Перезапуск демона (§6).** Служба XGW останавливается на минуту (Xray работает, дом идёт через
  пул), помощник (режим `ytreset`) забывает итоги проверок YouTube после §5, служба запускается
  снова — сервер пула должен остаться прежним и без события.

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
- **Журнал событий** панели: у событий проверки YouTube — метка «YouTube».

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
  NetworkManager, `ssh` — кроме `sudo systemctl stop xgw` и `sudo systemctl start xgw` в шаге 6.2
  и `sudo systemctl start xgw` в разделе «Если что-то пошло не так». Ручные `nft` (кроме
  `nft list`), `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`, `apt`; команды `tailscale`,
  `xray`, `sing-box`, `sstpc`, `pppd`. `systemd-run` и `systemctl stop` — только для таймера
  `xgw-yt-guard`. `sudo xgw pool mode …` — только в шаге 3.1 (`observe`), в «Если не так» шагов,
  где это написано, и в разделе «Если что-то пошло не так». `sudo xgw pool pin auto` — только в
  шаге 4.3 (если там написано) и в §9. `sudo xgw pin`, `sudo xgw unpin` — никогда.
- Режимы помощника, которые меняют состояние: `threshold 1000` — только в шаге 5.2,
  `threshold back` — в шаге 5.3, в §10 и в разделе «Если что-то пошло не так», `ytreset` — только
  в шаге 6.2.
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`). Загрузок из терминала нет.
  Сайты источников, YouTube, сайты проверки IP, страны и скорости — **не открывать** (YouTube
  смотрит заказчик на своём устройстве, шаг 7.1).
- В панели нажимать **только** то, что написано в шагах: вкладки, «Весь дом через бесплатные» и
  кнопку подтверждения в его окне, метку вверху и кнопки её окна, «Выключить». **Не нажимать**:
  кнопку питания, «Замерить скорость», «Проверить запасные», «Обновить», «Опросить источники»,
  «Выбрать» и «Автовыбор» (у любых серверов), переключатели Tailscale, «Ядра», «Проверить сеть»,
  строки устройств, «Добавить», «Убрать».
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`) — кроме помощника в режимах
  `threshold`; `/opt/xgw`, `/var/lib/xgw` (кроме помощника в режиме `ytreset`), `/run/xgw`,
  `/etc/systemd`, код XGW. Печатать `config.toml`, его копию `config.toml.ytbak`, `panel.json`,
  рабочие конфиги Xray и sing-box, файлы в `/var/lib/xgw/freepool`, базу
  `/var/lib/xgw/state.db`, полный вывод `sudo xgw pool` и `sudo xgw traffic`, вывод
  `nft list ruleset`. Коммитить что-либо, кроме файла отчёта (§11). Снимки экрана в git не
  добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, токен из ссылки
  панели, MAC, имена пользователей (→ `<user>`), внешние IP, адреса и домены подписок, IP,
  домены и ссылки серверов VPN, строки журнала. Можно: коды стран, теги вида `pool-de-1a2b` и
  `proxy-nl-8763`, скорости, задержки, вывод `sudo xgw pool stats` целиком (имён в нём нет),
  надписи панели без имён, счётчики, мегабайты, статусы, времена, строки помощника.

## 1. Подготовка (сессия 1)

Шаг 1.0. Предусловие — прошлая проверка закончена, копии настроек нет:

```bash
cd ~/zcod/xgw && git fetch -q && git log origin/freepool --format=%s | grep -c 'восстановление бесплатного пула — повтор'; systemctl list-timers --all --no-pager xgw-recov-guard.timer xgw-recov-unblock.timer xgw-yt-guard.timer | head -3; sudo nft list tables | grep -c xgw_recov; sudo test -e /etc/xgw/config.toml.ytbak && echo "копия настроек ЕСТЬ" || echo "копии настроек нет"; cd ~
```

Ожидается: `1` или больше; «0 timers listed»; `0`; «копии настроек нет».

Если не так: первая строка `0` — **стоп**, сообщить заказчику. Таймер в списке, таблица есть или
«копия настроек ЕСТЬ» — **стоп**, сообщить заказчику (прошлая проверка не закончена).

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю, как шлюз следит за YouTube: если YouTube через сервер не проходит или тормозит, шлюз
сам меняет сервер. Нажатия в панели и осмотр экрана я делаю сам, в управляемом браузере. По
пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Если наблюдение за бесплатными серверами выключено, я включу его и подожду 30 минут; в это
время дом идёт через подписку, как обычно.
(3) Я включу «весь дом через бесплатные серверы».
(4) На 15–25 минут я поставлю в настройках шлюза завышенный порог скорости YouTube: шлюз сочтёт,
что YouTube тормозит через каждый бесплатный сервер, и 2–3 раза сменит сервер дома; открытые
соединения при каждой смене могут подвиснуть на несколько секунд. Потом я верну настройку.
(5) Я остановлю службу XGW примерно на минуту и сброшу итоги проверок YouTube после пункта 4.
Интернет при этом идёт через Xray и не пропадает.
(6) Я попрошу вас 10 минут посмотреть YouTube (любое видео, 1080p) на любом устройстве дома и
рассказать, как шло.
(7) Срок «всего дома» после проверок: **А** — до 9 утра, **Б** — на сутки, **В** — на 6 часов,
**Г** — вернуть режим подписок сразу после проверок. По сроку страховочный таймер сам вернёт
режим подписок; если что-то не нравится — нажмите метку вверху панели («Через бесплатные серверы
▾») и «Вернуть режим подписок», это безопасно.
(8) По окончании я верну режим подписок и наблюдение в то состояние, в каком оно было до
проверки.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 при выключенном наблюдении или против 3 — §4–§8 пропустить
(в отчёте: «весь дом не включался»), §3 — только ожидание 10 минут и итоги подписки. Против 4 —
пропустить §5. Против 5 — пропустить §6. Против 6 — пропустить §7. Без ответа на 7 — срок **Г**.
Против 8 — §10 без смены режима наблюдения. **Запиши, на что согласился заказчик, и срок (А, Б, В
или Г).**

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-yt1" && chmod 700 "$HOME/xgw-yt1" && cd "$HOME/xgw-yt1" && cat > ytcheck.py <<'EOF'
"""XGW 0.2.0: проверка YouTube через сервер (основной сервер подписки и сервер бесплатного пула)
и прежний сервер пула после перезапуска демона — помощник проверки. Читает состояние XGW
(/run/xgw), базу состояния (только чтение), рабочий конфиг Xray, настройки и журнал со
стандартного ввода; печатает теги proxy-/spare-/pool-<страна>-<начало id>, итоги проверок
YouTube, скорости, счётчики и да/нет — без имён серверов, устройств и подписок, адресов, ссылок и
ключей. Состояние меняют только два режима, по шагам ТЗ: threshold — порог speed.youtube_mbps и
срок speed.youtube_minutes в config.toml (прежний файл — копией рядом; threshold back
возвращает копию), и ytreset — забыть итоги проверок YouTube (meta youtube) при остановленном
демоне. Время — секунды с 1970 (date +%s). Режимы: units, pool, route, state, flow, current, sub,
pinstate, watch on|back, yt [pool|sub], ytwait, waitswitch, threshold N|back, ytreset, events,
eventsum, log."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import tomllib
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("YTCHECK_LIB", "/opt/xgw/lib")
NAME = re.compile("«[^»]*»")
TAG = re.compile(r"^(proxy|spare|pool)-([a-z]{2})-([0-9a-f]{4,8})$")
WORDS = {"ok": "проходит", "slow": "тормозит", "blocked": "не пропускает"}
MARKS = {"on": "бесплатный пул: весь дом через бесплатные серверы",
         "back": "режим подписок возвращён"}
GOALS = {"on": "on", "back": "observe"}
MANUAL = {"on": "держится", "down": "не отвечает — ведёт выбранный шлюзом", "": "нет"}
SWITCH = ("весь дом идёт через", " идут через ")
REASONS = (("YouTube", "через прежний плох YouTube"), ("— быстрее, чем", "на более быстрый"),
           ("— выбран вручную", "выбран вручную"),
           ("выбранный вручную не отвечает", "выбранный вручную молчит"),
           ("больше не в работе", "прежний вне состава"), ("» не отвечает", "прежний не отвечал"))
PAUSE = "приостановлены"
COPY = "config.toml.ytbak"
KEYS = ("youtube_mbps", "youtube_minutes")
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
        return "—"
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
            f"скорость {rate(flow.get('mbps'))}; живых {flow.get('alive')} из "
            f"{flow.get('members')}; выбран вручную: {manual}")


def tags(paths):
    work = read_json(paths.xray_config_file) or {}
    found = []
    for item in work.get("outbounds") or []:
        match = TAG.match(str(item.get("tag") or "")) if isinstance(item, dict) else None
        if match:
            found.append(match)
    return found


def db(paths):
    conn = sqlite3.connect(f"file:{paths.db_file}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def youtube(paths):
    try:
        conn = db(paths)
        row = conn.execute("SELECT value FROM meta WHERE key = 'youtube'").fetchone()
        conn.close()
    except sqlite3.Error as exc:
        print(f"база не читается: {type(exc).__name__}")
        return None
    try:
        data = json.loads(row["value"]) if row and row["value"] else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def tag_of(key, matches):
    found = [match.group(0) for match in matches if key.startswith(match.group(3))]
    return found[0] if found else f"(нет в конфиге, id {key[:8]})"


def carriers(status):
    flow = flow_of(status) or {}
    main = status.get("main") if isinstance(status.get("main"), dict) else {}
    pin = status.get("pin") if isinstance(status.get("pin"), dict) else {}
    sub = pin.get("tag") if pin.get("tag") and not pin.get("down") else main.get("tag")
    return {item for item in (flow.get("tag"), sub) if item}


def verdict(rec):
    line = f"{WORDS.get(rec.get('state'), rec.get('state'))}, Google {rate(rec.get('mbps'))}"
    if isinstance(rec.get("client"), (int, float)):
        line += f", клиенты {rate(rec.get('client'))}"
    return line + f"; неудач подряд {int(rec.get('fails') or 0)}"


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


def masked(detail):
    return NAME.sub("«<сервер>»", detail)


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
    pooled = sum(1 for match in tags(paths) if match.group(1) == "pool")
    print(f"режим пула: {cfg.free_pool.mode}; последнее правило → "
          f"{last.get('balancerTag') or last.get('outboundTag') or 'правил нет'}; несущий "
          f"канал: {'есть' if carrier else 'нет'}; серверов в «pool»: {pooled}")
    print(f"рабочий конфиг совпадает с режимом: "
          f"{'да' if carrier == (cfg.free_pool.mode == 'on') else 'НЕТ'}; новый конфиг ждёт "
          f"окна перезапуска: {'да' if paths.pending_config_file.exists() else 'нет'}")
elif mode == "state":
    cfg, paths = xgw()
    shown = pool_of(read_json(paths.status_file) or {}).get("mode") or "off"
    speed = cfg.speed
    print(f"режим в настройках: {cfg.free_pool.mode}; в состоянии шлюза: {shown}; совпадают: "
          f"{'да' if shown == cfg.free_pool.mode else 'НЕТ'}")
    print("проверка YouTube в настройках: "
          + (f"{'включена' if speed.youtube else 'выключена'}, порог {speed.youtube_mbps} "
             f"Мбит/с, ведущий — раз в {speed.youtube_minutes} мин"
             if hasattr(speed, "youtube") else "ключей нет (старый код)"))
elif mode == "flow":
    _cfg, paths = xgw()
    print(flow_line(read_json(paths.status_file) or {}))
elif mode == "current":
    _cfg, paths = xgw()
    print((flow_of(read_json(paths.status_file) or {}) or {}).get("tag") or "нет")
elif mode == "sub":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    main = status.get("main") if isinstance(status.get("main"), dict) else None
    pin = status.get("pin") if isinstance(status.get("pin"), dict) else None
    print(f"состояние: {status.get('state')}; основной сервер: "
          + (f"{main.get('tag')} ({rate(main.get('mbps'))})" if main else "нет"))
    print("выбран вручную: " + ("нет" if not pin else f"{pin.get('tag')} — "
                                + ("не отвечает, ведёт автовыбор" if pin.get("down")
                                   else "держится")))
elif mode == "pinstate":
    cfg, paths = xgw()
    pin = cfg.managed.free_pool_pin
    flow = flow_of(read_json(paths.status_file) or {}) or {}
    match = TAG.match(str(flow.get("tag") or ""))
    same = bool(pin and match and pin.startswith(match.group(3)))
    print("выбор вручную сервера пула в настройках: " + (
        "нет" if not pin else "есть, это текущий сервер" if same else "есть, не текущий сервер"))
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
elif mode == "yt":
    which = sys.argv[2] if len(sys.argv) > 2 else "all"
    _cfg, paths = xgw()
    recs = youtube(paths)
    if recs is None:
        sys.exit(0)
    if not recs:
        print("итогов проверок YouTube в базе нет")
    status = read_json(paths.status_file) or {}
    cloud = {str(item.get("tag")): item.get("mbps")
             for item in (flow_of(status) or {}).get("servers") or [] if isinstance(item, dict)}
    carry, now, counts, bad = carriers(status), time.time(), {}, 0
    for match in tags(paths):
        tag, role = match.group(0), match.group(1)
        if which != "all" and (which == "pool") != (role == "pool"):
            continue
        found = [value for key, value in recs.items() if key.startswith(match.group(3))]
        mark = "  ← несёт трафик" if tag in carry else ""
        if not found:
            if role != "spare" or mark:
                print(f"{tag}: YouTube не проверялся{mark}")
            continue
        rec = max(found, key=lambda item: float(item.get("ts") or 0))
        state = str(rec.get("state"))
        counts[state] = counts.get(state, 0) + 1
        bad += int(rec.get("fails") or 0) >= 2
        age = (now - float(rec.get("ts") or 0)) / 60
        cloudflare = f"; Cloudflare {rate(cloud.get(tag))}" if role == "pool" else ""
        print(f"{tag}: {verdict(rec)}; {age:.0f} мин назад{cloudflare}{mark}")
    print(f"итого: проходит {counts.get('ok', 0)}, тормозит {counts.get('slow', 0)}, не "
          f"пропускает {counts.get('blocked', 0)}; плохих (2 неудачи подряд и больше) {bad}; "
          f"записей в базе {len(recs)}")
elif mode == "ytwait":
    _cfg, paths = xgw()
    since, want, limit = arg(2, time.time()), int(arg(3, 1)), arg(4, 600)
    start, seen = time.time(), set()
    print(f"жду проверок YouTube: {want} сервер(а), до {limit:.0f} с…", flush=True)
    while True:
        matches, recs = tags(paths), youtube(paths) or {}
        fresh = sorted((float(value.get("ts") or 0), key) for key, value in recs.items()
                       if float(value.get("ts") or 0) >= since)
        for ts, key in fresh:
            if (key, ts) not in seen:
                seen.add((key, ts))
                print(f"+{ts - since:4.0f} с: {tag_of(key, matches)}: {verdict(recs[key])}",
                      flush=True)
        if len(fresh) >= want:
            print(f"серверов проверено с метки: {len(fresh)}")
            break
        if time.time() - start > limit:
            print(f"за {limit:.0f} с проверено серверов: {len(fresh)} (ждал {want})")
            break
        time.sleep(5)
elif mode == "waitswitch":
    _cfg, paths = xgw()
    since, limit = arg(2, time.time()), arg(3, 1500)
    start, shown = time.time(), 0
    print(f"слежу за сменами из-за YouTube до {limit:.0f} с…", flush=True)
    while True:
        found = [(ts, kind, detail) for ts, kind, detail in events_since(paths, since)
                 if kind == "youtube" or (kind in ("freepool", "main") and "YouTube" in detail)]
        for ts, kind, detail in found[shown:]:
            print(f"+{ts - since:4.0f} с: {kind}: {masked(detail)}", flush=True)
        shown = len(found)
        switches = sum(1 for _ts, kind, _detail in found if kind != "youtube")
        if any(kind == "youtube" and PAUSE in detail for _ts, kind, detail in found):
            print(f"смен из-за YouTube: {switches}; пауза смен — есть")
            break
        if time.time() - start > limit:
            print(f"за {limit:.0f} с смен из-за YouTube: {switches}; паузы нет")
            break
        time.sleep(5)
elif mode == "threshold":
    _cfg, paths = xgw()
    want = sys.argv[2] if len(sys.argv) > 2 else ""
    path = Path(paths.config_file)
    copy = path.with_name(COPY)
    if want == "back":
        if not copy.exists():
            print("копии нет — настройки этим помощником не менялись")
            sys.exit(0)
        os.replace(copy, path)
        os.utime(path, None)
        print(f"настройки возвращены из копии; копии больше нет; права: "
              f"{oct(path.stat().st_mode & 0o777)[2:]}")
        sys.exit(0)
    if not want.isdigit():
        print("порог не задан")
        sys.exit(0)
    if copy.exists():
        print("копия уже есть — сначала threshold back")
        sys.exit(0)
    lines = path.read_text(encoding="utf-8").splitlines()
    values = dict(zip(KEYS, (want, "5")))
    head = next((index for index, line in enumerate(lines)
                 if re.match(r"^\s*\[speed\]\s*(#.*)?$", line)), None)
    if head is None:
        lines += ["", "[speed]", *(f"{key} = {value}" for key, value in values.items())]
    else:
        end = next((index for index in range(head + 1, len(lines))
                    if re.match(r"^\s*\[", lines[index])), len(lines))
        for key, value in values.items():
            at = next((index for index in range(head + 1, end)
                       if re.match(rf"^\s*{key}\s*=", lines[index])), None)
            if at is None:
                lines.insert(head + 1, f"{key} = {value}")
                end += 1
            else:
                lines[at] = f"{key} = {value}"
    text = "\n".join(lines) + "\n"
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        print(f"правка не применена: TOML не разобрался ({type(exc).__name__})")
        sys.exit(0)
    shutil.copy2(path, copy)
    temp = path.with_name(".config.toml.yt.tmp")
    handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, path.stat().st_mode & 0o777)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    os.replace(temp, path)
    print(f"записано: speed.youtube_mbps = {want}, speed.youtube_minutes = 5; копия прежних "
          f"настроек — рядом с config.toml (не печатается); права: "
          f"{oct(path.stat().st_mode & 0o777)[2:]}")
elif mode == "ytreset":
    _cfg, paths = xgw()
    if show("xgw.service", "ActiveState") == "active":
        print("демон xgw работает — сначала остановить его по шагу ТЗ")
        sys.exit(0)
    try:
        conn = sqlite3.connect(str(paths.db_file), timeout=10)
        with conn:
            removed = conn.execute("DELETE FROM meta WHERE key = 'youtube'").rowcount
        conn.close()
    except sqlite3.Error as exc:
        print(f"база не изменена: {type(exc).__name__}")
        sys.exit(0)
    print(f"итоги проверок YouTube забыты: записей {removed}")
elif mode == "events":
    _cfg, paths = xgw()
    for ts, kind, detail in events_since(paths, arg(2, time.time() - 3600)):
        if kind in ("freepool", "main", "youtube"):
            print(f"{stamp(ts)} {kind}: {masked(detail)}")
elif mode == "eventsum":
    _cfg, paths = xgw()
    since = arg(2, time.time() - 3600)
    counts = {label: 0 for _word, label in REASONS}
    first = bare = closures = main_yt = pauses = notes = 0
    after_switch = False
    for _ts, kind, detail in events_since(paths, since):
        if kind == "main" and "YouTube" in detail:
            main_yt += 1
        elif kind == "youtube":
            pauses += PAUSE in detail
            notes += "выбранный вручную" in detail
        elif kind != "freepool":
            continue
        elif MARKS["on"] in detail or MARKS["back"] in detail or "после перезагрузки" in detail:
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
    print(f"основной сервер подписки сменён из-за YouTube: {main_yt}; пауза смен из-за "
          f"YouTube: {pauses}; выбранный вручную плох для YouTube: {notes}")
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    checks = [line for line in lines if "YouTube через" in line]
    print(f"строк журнала: {len(lines)}")
    print(f"проверок YouTube: {len(checks)}: проходит "
          f"{sum(': проходит' in line for line in checks)}, тормозит "
          f"{sum(': тормозит' in line for line in checks)}, не пропускает "
          f"{sum(': не пропускает' in line for line in checks)}; через сервер, который несёт "
          f"трафик: {sum('(несёт трафик)' in line for line in checks)}")
    for label, word in (
        ("после запуска демона — через прежний сервер пула", "после запуска демона — через"),
        ("настройки перечитаны", "настройки изменены"),
        ("сервер бесплатного пула не закреплён", "сервер бесплатного пула не закреплён"),
        ("откат на last-good", "last-good"),
        ("шаг пула не выполнен", "бесплатный пул: шаг не выполнен"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | pool | route | state | flow | current | sub | pinstate | watch on|back "
          "| yt [pool|sub] | ytwait | waitswitch | threshold N|back | ytreset | events | "
          "eventsum | log")
EOF
python3 -c "import hashlib;d=open('ytcheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `b7851c3eccbb4325`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки:

```bash
cd "$HOME/xgw-yt1" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units pool route state sub pinstate; do sudo python3 -I ytcheck.py $m; done | tee -a before.txt; sudo python3 -I ytcheck.py yt | tail -1 | tee -a before.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; первая строка
`xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать, какая**; четыре
службы `active`; `route` — «совпадает с режимом: да»; `state` — вторая строка «проверка YouTube в
настройках: ключей нет (старый код)»; `sub` — **записать** обе строки (основной сервер и выбран
ли сервер подписки вручную); `pinstate` — **записать**; последняя строка — «итогов проверок
YouTube в базе нет» и «итого: … записей в базе 0».

Если не так: первая строка `xgw pool` — «весь дом через бесплатные серверы» — выполнить
`sudo xgw pool mode observe`, подождать минуту и повторить шаг.

## 2. Установка (сессия 1)

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def _youtube_step' src/xgw/daemon.py && grep -q 'POOL_PINNED_META' src/xgw/daemon.py && test -f src/xgw/watch/youtube.py && echo "правка в коде: есть"; cd "$HOME/xgw-yt1"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-yt1/install-time.txt" && date +%s > "$HOME/xgw-yt1/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-yt1/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-yt1/install.txt"; cd "$HOME/xgw-yt1"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 3 минуты — состояние и первая проверка YouTube в режиме подписок:

```bash
sleep 180; cd "$HOME/xgw-yt1" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee after-install.txt; for m in units route state sub; do sudo python3 -I ytcheck.py $m; done | tee -a after-install.txt; sudo python3 -I ytcheck.py ytwait "$(cat t-install.txt)" 1 300 | tee -a after-install.txt; sudo python3 -I ytcheck.py yt sub | tee yt-sub-0.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I ytcheck.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, строки «Ожидает окна перезапуска» нет; четыре службы `active`;
  `route` — «совпадает с режимом: да»;
- `state` — вторая строка «проверка YouTube в настройках: включена, порог 5 Мбит/с, ведущий — раз
  в 30 мин»;
- `ytwait` — хотя бы одна строка «+N с: proxy-XX-…: проходит, Google N Мбит/с; неудач подряд 0»
  (или «spare-XX-…», если вручную выбран запасной) и «серверов проверено с метки: 1» (или больше);
- `yt sub` — у сервера из строки `sub` (основной или выбранный вручную) пометка «← несёт трафик»
  и итог: «проходит, Google N Мбит/с» у безлимитного или «проходит, Google —» у лимитированного
  (у них скорость не замеряется: квота); у остальных — итоги или «YouTube не проверялся» (фоновые
  проверки идут по одной в 2 минуты); **записать** таблицу целиком;
- журнал: «проверок YouTube: N» (N ≥ 1), «Traceback: 0», «откат на last-good: 0».

Если не так: «за 300 с проверено серверов: 0» — подожди 5 минут и выполни
`sudo python3 -I ytcheck.py yt sub`; снова ни одного итога — **дефект** «проверка YouTube не
началась», записать строки `sub` и `state` и продолжать. Не `HEALTHY` — подожди 2 минуты и
повтори; снова нет — запиши и продолжай. Итог «тормозит» или «не пропускает» у сервера,
несущего трафик, — **не дефект**: запиши; через минуту шлюз проверит его снова (шаг 3.2 покажет,
сменился ли основной).

## 3. Режим подписок и наблюдение (сессия 1)

Шаг 3.1. Только если в шаге 1.3 наблюдение было **выключено** (иначе — пропустить, записать «уже
было включено», выполнить `sleep 600` и перейти к шагу 3.2):

```bash
cd "$HOME/xgw-yt1" && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; sleep 600; sudo python3 -I ytcheck.py yt sub | tee yt-sub-10.txt; sleep 1200; sudo python3 -I ytcheck.py pool | tee -a mode-on.txt
```

(Если терминал обрывает длинные команды — после первой строки выполни `sleep 110` 6 раз, затем
`sudo python3 -I ytcheck.py yt sub | tee yt-sub-10.txt`, ещё 11 раз `sleep 110`, затем
`sudo python3 -I ytcheck.py pool | tee -a mode-on.txt`.)

Ожидается: «Наблюдение за бесплатным пулом включено: …»; через 10 минут `yt sub` — проверено
больше серверов, чем в шаге 2.3 (фоновые — по одному в 2 минуты); через 30 минут `pool` —
«пригодно» больше 2.

Если не так: «пригодно» 2 или меньше — подожди ещё 30 минут и повтори `pool`; снова не больше 2 —
§4–§8 пропустить («допущенных серверов меньше трёх»), выполнить шаг 3.2 и перейти к §10.

Шаг 3.2. Итоги проверок YouTube в режиме подписок:

```bash
cd "$HOME/xgw-yt1" && sudo python3 -I ytcheck.py sub | tee yt-sub.txt; sudo python3 -I ytcheck.py yt sub | tee -a yt-sub.txt; sudo python3 -I ytcheck.py eventsum "$(cat t-install.txt)" | tee -a yt-sub.txt; sudo python3 -I ytcheck.py events "$(cat t-install.txt)" | grep -E ' main: | youtube: ' | tee -a yt-sub.txt
```

Ожидается: `yt sub` — итоги у сервера, несущего трафик («← несёт трафик»), и у живых безлимитных
серверов в работе (строки `proxy-…`); **записать таблицу целиком** и строку «итого». Если у
сервера, несущего трафик, «неудач подряд 2» и больше — в событиях строка «main: основной сервер
«<сервер>» не пропускает YouTube — выбираю другой» (или «… тормозит на YouTube (…) — выбираю
другой»), а в `eventsum` — «основной сервер подписки сменён из-за YouTube: 1» (или больше); если
он выбран вручную — вместо смены «youtube: выбранный вручную сервер «<сервер>» …» и «выбранный
вручную плох для YouTube: 1». Все «проходит» — смен из-за YouTube 0 (записать).

Если не так: плохой (2 неудачи подряд) несущий трафик сервер не сменился и не выбран вручную, а
другие серверы подписки «проходит» — **дефект**, приложить строки `sub`, `yt sub` и событий.

## 4. Весь дом (сессия 1)

Шаг 4.1. Страховочный таймер — **до** включения «всего дома». Выполни **один** блок — по сроку
из шага 1.1.

Срок **А** (до 9 утра):

```bash
cd "$HOME/xgw-yt1" && sudo systemd-run --on-calendar='*-*-* 09:00:00' --unit=xgw-yt-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3 | tee -a guard.txt
```

Срок **Б** (сутки):

```bash
cd "$HOME/xgw-yt1" && sudo systemd-run --on-active=24h --unit=xgw-yt-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3 | tee -a guard.txt
```

Срок **В** (6 часов):

```bash
cd "$HOME/xgw-yt1" && sudo systemd-run --on-active=6h --unit=xgw-yt-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3 | tee -a guard.txt
```

Срок **Г** (сразу после проверок; таймер — на 3 часа):

```bash
cd "$HOME/xgw-yt1" && sudo systemd-run --on-active=3h --unit=xgw-yt-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3 | tee -a guard.txt
```

Ожидается: «Running timer as unit: xgw-yt-guard.timer» и строка таймера с временем срабатывания
— **записать его**.

Если не так: таймера нет — **стоп** для §4–§8 (перейти к §10).

Шаг 4.2. Панель. Ссылка входа (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком (окно не меньше 1280×800),
подожди 5 секунд, нажми вкладку **«Бесплатные серверы»**, подожди 5 секунд, снимок.

Шаг 4.3. Включение «всего дома».
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-yt1" && date +%s > t-on.txt && echo "метка записана: $(date '+%T')"
```

2. На вкладке «Бесплатные серверы» нажми **«Весь дом через бесплатные»**.
3. Снимок; **J4** — `true | Пустить весь дом через бесплатные серверы? | Весь дом через
   бесплатные`.
4. Нажми в окне **«Весь дом через бесплатные»**.
5. **Сразу** выполни (до 15 минут):

```bash
cd "$HOME/xgw-yt1" && sudo python3 -I ytcheck.py watch on "$(cat t-on.txt)" | tee watch-on.txt; for m in route pinstate; do sudo python3 -I ytcheck.py $m; done | tee on.txt; sudo python3 -I ytcheck.py ytwait "$(cat t-on.txt)" 1 600 | tee -a on.txt; sudo python3 -I ytcheck.py events "$(cat t-on.txt)" | tee events-on.txt
```

Ожидается:
- `watch`: «нажатие: …»; строки «+N с: режим on: сейчас через pool-XX-… (XX), …»; «ЗАКРЫТО»
  замеров: 0; «режим on в состоянии шлюза — с +N с»;
- `route` — «последнее правило → pool; несущий канал: есть; серверов в «pool»: N» (N — от 3 до 8,
  **записать**), «совпадает с режимом: да»;
- `pinstate` — «выбор вручную сервера пула в настройках: нет» и «… в состоянии шлюза: нет»;
- `ytwait` — строка «+N с: pool-XX-…: проходит, Google N Мбит/с; неудач подряд 0» (или
  «тормозит»/«не пропускает» — записать) и «серверов проверено с метки: 1» (или больше). Первая
  проверка может прийти через несколько минут: шаг с замером скорости сервера пула и следующий за
  ним проверку YouTube пропускают;
- события — записать.

Если не так: «сейчас через» не появилось за три минуты — раздел «Если что-то пошло не так».
`pinstate` — «есть…» — выполнить `sudo xgw pool pin auto`, затем снова
`sudo python3 -I ytcheck.py pinstate` (должно стать «нет») и записать. N меньше 3 — §5 пропустить
(записать «серверов в работе меньше трёх»). «за 600 с проверено серверов: 0» — **дефект**
«проверка YouTube у пула не началась», записать и продолжать.

Шаг 4.4. **Действие:** обнови страницу (F5), подожди 5 секунд, снимок, **J1** и **J9**.

Ожидается: J1 — `BUTTON | Через бесплатные серверы | false`; J9 — `Бесплатный сервер | N Мбит/с |
задержка есть` (сервер ещё не замерен — «скорости нет», запиши).

Шаг 4.5. 20 минут — фоновые проверки остальных серверов пула:

```bash
sleep 1200; cd "$HOME/xgw-yt1" && sudo python3 -I ytcheck.py flow | tee yt-pool.txt; sudo python3 -I ytcheck.py yt pool | tee -a yt-pool.txt; sudo python3 -I ytcheck.py eventsum "$(cat t-on.txt)" | tee -a yt-pool.txt
```

(Если терминал обрывает длинные команды — `sleep 110` 11 раз, затем команда без `sleep`.)

Ожидается: `flow` — «режим on: сейчас через pool-XX-…»; `yt pool` — по строке на сервер «pool»:
у ведущего — «← несёт трафик», у большинства (не меньше половины) — итог проверки со скоростью
Google и Cloudflare; **записать таблицу целиком** — по ней видно, есть ли серверы с высокой
скоростью Cloudflare и низкой Google (как в прошлый раз); `eventsum` — «БЕЗ ПРИЧИНЫ: 0»,
««закрыто»: 0»; смен «через прежний плох YouTube» — сколько есть (записать: если ведущий был
плох для YouTube, шлюз его уже сменил).

Если не так: «БЕЗ ПРИЧИНЫ» больше 0 — **дефект «смена без причины»**: выполни
`sudo python3 -I ytcheck.py events "$(cat t-on.txt)" | tee events-pool.txt` и приложи строки вокруг.
Итогов меньше половины — запиши, **не дефект** (замеры скорости новых серверов пула занимают
шаги, проверки YouTube ждут).

## 5. Принудительная смена из-за YouTube (сессия 1)

Шаг 5.1. **Скажи заказчику** (дословно): «Ставлю завышенный порог скорости YouTube минут на
15–25. Шлюз 2–3 раза сменит бесплатный сервер дома; при каждой смене открытые соединения могут
подвиснуть на несколько секунд. Потом я верну настройку.»

Шаг 5.2. Метка, порог 1000 Мбит/с и ожидание смен (до 25 минут):

```bash
cd "$HOME/xgw-yt1" && date +%s > t-force.txt && echo "метка записана: $(date '+%T')" && sudo python3 -I ytcheck.py current | tee force-start.txt && sudo python3 -I ytcheck.py threshold 1000 | tee force.txt; sleep 40; sudo python3 -I ytcheck.py state | tee -a force.txt; sudo python3 -I ytcheck.py waitswitch "$(cat t-force.txt)" 1500 | tee -a force.txt; for m in flow route; do sudo python3 -I ytcheck.py $m; done | tee -a force.txt
```

Ожидается:
- `current` — тег ведущего сервера (записан в `force-start.txt`);
- `threshold` — «записано: speed.youtube_mbps = 1000, speed.youtube_minutes = 5; копия прежних
  настроек — рядом с config.toml (не печатается); права: 600»;
- `state` — «проверка YouTube в настройках: включена, порог 1000 Мбит/с, ведущий — раз в 5 мин»;
- `waitswitch` — строки «+N с: freepool: бесплатный пул: весь дом идёт через «<сервер>» (XX)… —
  «<сервер>» тормозит на YouTube (N Мбит/с с серверов Google…)» — первая не позже ~8 минут после
  метки, следующие — через 2–6 минут; на третьей смене — «+N с: youtube: YouTube плох через 3
  сервера подряд за час — дело, похоже, не в серверах; смены из-за YouTube приостановлены на 2 ч»
  и итог «смен из-за YouTube: 3; пауза смен — есть». **Записать время каждой смены** (секунды от
  метки);
- `flow` — «режим on: сейчас через pool-XX-… …» (тег — другой, чем в `force-start.txt`); «ЗАКРЫТО»
  нет; `route` — «совпадает с режимом: да».

Если не так: `threshold` — не «записано…» — **стоп** для §5: записать строку, перейти к §6 без
`ytreset` (только перезапуск). `state` всё ещё «порог 5» — подожди минуту и повтори
`sudo python3 -I ytcheck.py state`; снова «порог 5» — **дефект** «настройки не перечитаны»,
перейти к шагу 5.3. Итог «смен из-за YouTube: 1» или «2; паузы нет» при N (шаг 4.3) 3 или 4 —
**не дефект**: замены без отметки «плох» кончились, сервер прежний (записать). Итог «смен из-за
YouTube: 0; паузы нет» — **дефект** «ведущий не сменился», приложить `sudo python3 -I ytcheck.py
yt pool` и `sudo python3 -I ytcheck.py events "$(cat t-force.txt)"`. «ЗАКРЫТО» — раздел «Если
что-то пошло не так».

Шаг 5.3. Вернуть настройку, итоги проверок и дневник:

```bash
cd "$HOME/xgw-yt1" && sudo python3 -I ytcheck.py threshold back | tee force-back.txt; sleep 60; sudo python3 -I ytcheck.py state | tee -a force-back.txt; sudo python3 -I ytcheck.py yt pool | tee -a force-back.txt; sudo python3 -I ytcheck.py eventsum "$(cat t-force.txt)" | tee -a force-back.txt; sudo xgw pool stats --days 1 2>&1 | tee stats-force.txt; sudo journalctl -u xgw --since "@$(cat t-force.txt)" --no-pager | sudo python3 -I ytcheck.py log | tee log-force.txt
```

Ожидается:
- «настройки возвращены из копии; копии больше нет; права: 600»; `state` — «… порог 5 Мбит/с,
  ведущий — раз в 30 мин»;
- `yt pool` — у серверов, через которые шёл дом в шаге 5.2, «тормозит, Google N Мбит/с; неудач
  подряд 2» (или больше); строка «плохих …» — не меньше числа смен;
- `eventsum` — «через прежний плох YouTube N» (N — как в `waitswitch`), «БЕЗ ПРИЧИНЫ: 0»,
  ««закрыто»: 0», «пауза смен из-за YouTube: 1» (или 0 — как в `waitswitch`);
- `xgw pool stats` — у сегодняшнего дня строки «смен сервера …, через прежний плох YouTube N» и
  «YouTube: проверок M, не пропускал K, тормозил L» (L ≥ 2·N) — **записать целиком**;
- журнал: «проверок YouTube: …, тормозит …»; «настройки перечитаны: 2» (правка и возврат);
  «Traceback: 0».

Если не так: «копии нет…» — запиши (копия уже возвращена); `state` — не «порог 5» — **стоп**,
сообщить заказчику, раздел «Если что-то пошло не так».

## 6. Перезапуск демона: прежний сервер пула (сессия 1)

Шаг 6.1. **Скажи заказчику** (дословно): «Останавливаю службу XGW примерно на минуту. Интернет
идёт через Xray и не пропадает.»

Шаг 6.2. Остановка, сброс итогов YouTube, запуск:

```bash
cd "$HOME/xgw-yt1" && sudo python3 -I ytcheck.py current | tee restart-before.txt && sudo systemctl stop xgw && sleep 5 && systemctl is-active xgw | tee -a restart-before.txt; sudo python3 -I ytcheck.py ytreset | tee -a restart-before.txt; date +%s > t-start.txt; sudo systemctl start xgw; sleep 120; systemctl is-active xgw | tee restart.txt; for m in current flow route; do sudo python3 -I ytcheck.py $m; done | tee -a restart.txt; sudo python3 -I ytcheck.py events "$(cat t-start.txt)" | tee events-restart.txt; sudo python3 -I ytcheck.py eventsum "$(cat t-start.txt)" | tee -a events-restart.txt; sudo journalctl -u xgw --since "@$(cat t-start.txt)" --no-pager | sudo python3 -I ytcheck.py log | tee log-restart.txt
```

Ожидается:
- до остановки — тег ведущего; после остановки — `inactive`; `ytreset` — «итоги проверок YouTube
  забыты: записей N» (N ≥ 1);
- после запуска — `active`; `current` — **тот же тег**, что в `restart-before.txt`; `flow` —
  «режим on: сейчас через <тот же тег> …»; `route` — «совпадает с режимом: да»;
- события с запуска — **нет** строки «весь дом идёт через» (или есть, но с причиной — «… «<сервер>»
  не отвечает» / «… больше не в работе», если прежний за минуту замолчал или выбыл из состава —
  записать); `eventsum` — «БЕЗ ПРИЧИНЫ: 0»;
- журнал — «после запуска демона — через прежний сервер пула: 1», «Traceback: 0».

Если не так: `current` — другой тег, а в событиях смена **без причины** (строка «весь дом идёт
через «<сервер>» (XX)» без «—») — **дефект** «дефект 1 не исправлен», приложить события и
`restart-before.txt`. `active` нет — `sudo systemctl start xgw`, подождать минуту, записать.

Шаг 6.3. Итоги YouTube собраны заново (до 10 минут):

```bash
cd "$HOME/xgw-yt1" && sudo python3 -I ytcheck.py ytwait "$(cat t-start.txt)" 2 600 | tee yt-restart.txt; sudo python3 -I ytcheck.py yt pool | tee -a yt-restart.txt
```

Ожидается: строки «+N с: pool-XX-…: …» — первая у ведущего; «серверов проверено с метки: 2»;
`yt pool` — у ведущего «← несёт трафик» и итог с порогом 5 Мбит/с (обычно «проходит»); у прочих —
новые итоги или «YouTube не проверялся»; строк «тормозит … неудач подряд 2» от шага 5 нет
(итоги забыты).

Если не так: «за 600 с проверено серверов: 0» — **дефект**, записать.

## 7. YouTube у заказчика (сессия 1)

Шаг 7.1. **Скажи заказчику** (дословно): «Включите, пожалуйста, на любом устройстве дома YouTube
— любое видео в качестве 1080p — и смотрите 10 минут. Я в это время слежу за проверками шлюза.
Скажите, когда начнёте.» Когда заказчик скажет, что начал:

```bash
cd "$HOME/xgw-yt1" && date +%s > t-yt.txt && echo "метка записана: $(date '+%T')" && sudo python3 -I ytcheck.py waitswitch "$(cat t-yt.txt)" 600 | tee yt-watch.txt; for m in flow; do sudo python3 -I ytcheck.py $m; done | tee -a yt-watch.txt; sudo python3 -I ytcheck.py yt pool | tee -a yt-watch.txt
```

Ожидается: «за 600 с смен из-за YouTube: 0; паузы нет» (или строки смен — **записать**, это
решение шлюза по ходу просмотра); `flow` и `yt pool` — записать.

Шаг 7.2. **Спроси заказчика** (дословно): «Как шло видео: (1) была ли буферизация — сколько раз
примерно; (2) какое качество держалось; (3) лучше, хуже или так же, как в прошлый раз через
бесплатные серверы?» Ответы — дословно, без имён.

Шаг 7.3. **Скажи заказчику** — по сроку из шага 1.1:
- срок **Г**: «Проверки закончены, возвращаю режим подписок.» — и перейти к §9;
- срок **А/Б/В** (подставь время таймера из шага 4.1): «Проверки закончены. Весь дом идёт через
  бесплатные серверы. Страховочный таймер вернёт режим подписок в <время>. Пользуйтесь
  интернетом как обычно, YouTube — тоже: если он через сервер начнёт тормозить, шлюз должен сам
  сменить сервер. Если что-то не нравится — нажмите метку вверху панели «Через бесплатные серверы
  ▾» и «Вернуть режим подписок». Когда закончим — напишите мне, я сниму итоги.»

Запиши время. При сроке А/Б/В **сессия 1 окончена**: отчёт пока не пиши; файлы в `$HOME/xgw-yt1`
не удаляй.

## 8. Долгое наблюдение (сессия 2, сроки А/Б/В)

Шаг 8.2 (когда скажет заказчик). Помощник на месте и состояние:

```bash
cd "$HOME/xgw-yt1" && python3 -c "import hashlib;d=open('ytcheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; date '+%F %T' | tee end.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Ожидает окна' | tee -a end.txt; for m in units flow state route pinstate; do sudo python3 -I ytcheck.py $m; done | tee -a end.txt; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3 | tee -a end.txt; sudo test -e /etc/xgw/config.toml.ytbak && echo "копия настроек ЕСТЬ" || echo "копии настроек нет"
```

Ожидается: сумма — как в шаге 1.2; `HEALTHY`; четыре службы `active`; `flow` — «режим on: сейчас
через pool-XX-… …» (наблюдение ещё идёт) **или** «режим observe: через пул никто» (сработал
таймер или заказчик вернул режим сам — записать, что именно: таймер в списке есть — вернул
заказчик; «0 timers listed» — сработал таймер); `state` — «порог 5 Мбит/с, ведущий — раз в 30
мин»; `route` — «совпадает с режимом: да»; «копии настроек нет».

Если не так: сумма другая — файл помощника изменился: **стоп**, сообщить заказчику.

Шаг 8.3. Итоги дневника, проверок YouTube, событий и журнала:

```bash
cd "$HOME/xgw-yt1" && sudo xgw pool stats --days 2 2>&1 | tee stats-end.txt; sudo python3 -I ytcheck.py yt pool | tee yt-end.txt; sudo python3 -I ytcheck.py eventsum "$(cat t-yt.txt)" | tee eventsum-end.txt; sudo python3 -I ytcheck.py events "$(cat t-yt.txt)" | grep -E 'YouTube' | tee -a eventsum-end.txt; sudo journalctl -u xgw --since "@$(cat t-yt.txt)" --no-pager | sudo python3 -I ytcheck.py log | tee log-end.txt
```

Ожидается (записать **целиком** в отчёт — имён в этих строках нет): `xgw pool stats` — по строке
на день, у дней с трафиком через пул — шесть строк, в том числе «YouTube: проверок …»; `yt pool`
— таблица; `eventsum` — «БЕЗ ПРИЧИНЫ: 0» и сколько смен «через прежний плох YouTube»; события
YouTube — строки (имена скрыты); журнал: «Traceback: 0», «откат на last-good: 0», остальные числа
— записать.

Если не так: «БЕЗ ПРИЧИНЫ» больше 0 — **дефект «смена без причины»**: выполни
`sudo python3 -I ytcheck.py events "$(cat t-yt.txt)" | tee events-end.txt` и приложи строки
вокруг смен без причины.

Шаг 8.4. **Спроси заказчика** (дословно): «Весь дом шёл через бесплатные серверы с <время
включения из шага 4.3>. Расскажите, пожалуйста: (1) открывались ли сайты как обычно; (2) как шёл
YouTube — была ли буферизация, менялось ли качество; (3) были ли обрывы или «ничего не
открывается» — примерно когда и надолго; (4) что-то работало хуже, чем через подписку; (5)
возвращали ли вы режим подписок сами и почему?» Ответы — дословно, без имён.

## 9. Возврат режима подписок

Шаг 9.1. Если `flow` (шаг 8.2) — «режим observe» (режим уже вернулся), выполни только:
`cd "$HOME/xgw-yt1" && sudo systemctl stop xgw-yt-guard.timer; for m in route state pinstate; do sudo python3 -I ytcheck.py $m; done | tee back.txt`
(ошибка «not loaded» — норма) и переходи к шагу 9.2. Иначе:
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-yt1" && date +%s > t-back.txt && echo "метка записана: $(date '+%T')"
```

2. Открой панель (ссылка — `sudo xgw panel 2>&1 | head -1`, если вкладка закрыта), нажми
   **метку вверху справа** («Через бесплатные серверы ▾»). Снимок; **J4** — `true | Вернуть
   режим подписок? | Вернуть режим подписок`.
3. Нажми в окне **«Вернуть режим подписок»**.
4. **Сразу** выполни:

```bash
cd "$HOME/xgw-yt1" && sudo python3 -I ytcheck.py watch back "$(cat t-back.txt)" | tee watch-back.txt; sudo systemctl stop xgw-yt-guard.timer; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3 | tee guard-off.txt; for m in route state pinstate sub; do sudo python3 -I ytcheck.py $m; done | tee back.txt; sudo xgw pool stats --days 1 2>&1 | tee stats-back.txt
```

Ожидается: «нажатие: …»; «режим observe: через пул никто»; «ЗАКРЫТО» замеров: 0; «0 timers
listed»; `route` — «последнее правило → auto; несущий канал: нет; серверов в «pool»: 0»,
«совпадает с режимом: да»; `sub` — записать; `xgw pool stats` — записать **целиком**.

Шаг 9.2. Если `pinstate` в 9.1 — «выбор вручную сервера пула в настройках: есть…»:

```bash
cd "$HOME/xgw-yt1" && sudo xgw pool pin auto 2>&1 | tee pin-auto.txt; sudo python3 -I ytcheck.py pinstate | tee -a pin-auto.txt
```

Ожидается: «Сервер бесплатного пула снова выбирает шлюз»; «… в настройках: нет». Выбора нет — шаг
пропустить, записать «выбора не было».

## 10. Секреты и режим как до проверки

Шаг 10.1. Секреты и копия настроек:

```bash
cd "$HOME/xgw-yt1" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt; sudo test -e /etc/xgw/config.toml.ytbak && echo "копия настроек ЕСТЬ" | tee -a secrets.txt || echo "копии настроек нет" | tee -a secrets.txt
```

Ожидается: `0` и «копии настроек нет». Первое больше — **дефект** (строки журнала в отчёт не
копировать); «копия настроек ЕСТЬ» — выполнить `sudo python3 -I ytcheck.py threshold back` и
записать.

Шаг 10.2. Если в шаге 1.3 наблюдение было **выключено** — **действие в браузере:** вкладка
«Бесплатные серверы» → **«Выключить»**, снимок (кнопка сменилась на «Включить наблюдение»). Было
включено — ничего не менять, записать «оставлено включённым».

Шаг 10.3. Итог:

```bash
sleep 60; cd "$HOME/xgw-yt1" && date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units pool route state sub; do sudo python3 -I ytcheck.py $m; done | tee -a final.txt; sudo python3 -I ytcheck.py yt sub | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I ytcheck.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4, строки «Ожидает окна
перезапуска» нет; четыре службы `active`; режим — как был до проверки; `route` — «совпадает с
режимом: да»; `state` — «порог 5 Мбит/с, ведущий — раз в 30 мин»; `yt sub` — у сервера подписки,
несущего трафик, свежий итог («← несёт трафик»); журнал: «откат на last-good: 0», «Traceback: 0».

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- В сессии 1 в режиме «весь дом» пропал интернет или доступ, или заказчик не отвечает **2
  минуты** — **сразу**, по порядку: `sudo python3 -I ytcheck.py threshold back` («копии нет» —
  норма), `sudo xgw pool mode observe`, `sudo systemctl stop xgw-yt-guard.timer` (ошибка «not
  loaded» — норма); если `systemctl is-active xgw` — не `active`, то `sudo systemctl start xgw`.
  Записать время и строки `sudo python3 -I ytcheck.py flow` и `sudo python3 -I ytcheck.py route`.
  Дальше — шаг 9.2, §10 и отчёт. «Весь дом» больше не включать.
- Заказчик во время долгого наблюдения вернул режим подписок сам — это не сбой: в сессии 2
  записать время (из `eventsum`) и его причину (шаг 8.4).
- Не `HEALTHY` больше 5 минут, службы не `active` (кроме остановки `xgw` в шаге 6.2) — записать,
  сообщить заказчику, ничего не перезапускать.
- Браузер не открывает панель или кнопки не нажимаются — снимок, сообщить заказчику и попросить
  нажать то же самое вручную; в отчёте пометить «нажато заказчиком».

## 11. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-<ДАТА>.md` в клоне (`<ДАТА>` — дата начала
проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, проверка YouTube через сервер» и `git push` в
`freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и подписок,
адресов, доменов, токена и строк журнала. Шаблон (заполни каждую ячейку; пропущенное — «не
выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — проверка YouTube через сервер

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>, срок <А/Б/В/Г>.
ytcheck.py: <сумма>. Наблюдение до проверки: <…>. Сервер подписки выбран вручную до проверки:
<да/нет>. Ядра: Xray <…>, sing-box <…>. Исполнитель: <модель>; нажатия и снимки — управляемым
браузером <да/частично>.

## Итог
| Подписка: проверено / проходит / тормозит / не пропускает; смен основного из-за YouTube | Пул (4.5): проверено / проходит / тормозит / не пропускает; серверы «Cloudflare высоко, Google низко» | Принудительно: смены (с от метки) / пауза | Перезапуск: тот же сервер / событие / «через прежний» в журнале | YouTube у заказчика | Долгое наблюдение: с — по, смен из-за YouTube |
|---|---|---|---|---|---|
| <5 / 4 / 1 / 0; 0> | <6 / 4 / 2 / 0; 1> | <3 (150, 320, 560) / есть> | <да / нет / 1> | <кратко> | <… или «срок Г»> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.0 предусловие | … | … |
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки, первая проверка | … | … |
| 3.1–3.2 режим подписок | … | … |
| 4.1 страховка | … | … |
| 4.3 включение, первая проверка пула | … | … |
| 4.4 панель | … | … |
| 4.5 итоги пула | … | … |
| 5.2 принудительная смена | … | … |
| 5.3 возврат порога, дневник | … | … |
| 6.2 перезапуск демона | … | … |
| 6.3 итоги заново | … | … |
| 7 YouTube у заказчика | … | … |
| 8.2–8.4 долгое наблюдение | … | … |
| 9 возврат | … | … |
| 10 секреты и итог | … | … |

## Таблицы `yt` (шаги 3.2, 4.5, 6.3 — целиком)
<…>

## Вывод `sudo xgw pool stats` (шаги 5.3 и 8.3 или 9.1, целиком)
<…>

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-yt1/…); результаты J1, J4, J9; что видно на
  снимках словами; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
