# Проверка XGW 0.2.0: бесплатные серверы — рабочий конфиг следует режиму «весь дом»

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, вводишь текст, делаешь
  **снимок экрана** и смотришь на него, выполняешь JavaScript в консоли страницы;
- возможно, **adb** — телефон заказчика по USB (шаг 1.4 покажет, есть ли он).

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие** (что сделать), **Команда** (копируй блок целиком, ничего в нём не
   меняя; единственное исключение — шаг 3.3, там сказано, что подставить), **Ожидается** и
   **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J1–J5) — выполни её в консоли
   страницы и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-fpfix3/…` (так написано в командах). Время
   каждого шага — по выводу `date` в команде, не по памяти.
5. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
6. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай
   дословно (без имён серверов и устройств).
7. Экземпляр этого ТЗ держи в `$HOME/xgw-fpfix3/plan.md` (не в /tmp: там его стирают). Файл
   помощника создаётся **только** командой шага 1.2.
8. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   здесь, на машине). Если какой-то режим `fpfix3check.py` выводит `Traceback` — запиши режим и
   последнюю строку ошибки как **дефект помощника** и продолжай шаг по остальным строкам и
   командам `xgw`. Сам файл помощника не исправляй.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. Телефон — S25 Ultra. На машине —
Xray 26.10.29 и sing-box 1.14.4, принятые шлюзом через карточку «Ядра»: установка их не
откатывает.

### Что нового (ASSUMPTIONS п. 270)

Прошлая проверка (отчёт m2b2fix2): удалённый доступ в режиме «весь дом» больше не теряется, но
**после перезагрузки режим снимался, а рабочий конфиг Xray оставался «весь дом»** до ночного
окна перезапуска (04:00–05:00): весь дом шёл через бесплатные серверы при панели «выключено», и
смены режима этого не меняли. Исправлено:
1. **Демон сверяет рабочий конфиг Xray с режимом** на каждом шаге: не совпало — срочная сборка с
   перезапуском Xray (не чаще раза в 5 минут). `xgw diag` показывает расхождение как FAIL.
2. **Режим в состоянии шлюза** (status.json, `xgw pool`) меняется сразу, а не через 2–3 минуты.
3. **«Выключить» останавливает проверки** серверов пула сразу.
4. **Двойные разделители** в именах серверов на месте убранных значков («… | | …») убраны.
5. **Метка вверху панели — переключатель**: в режиме «весь дом» метка «Через бесплатные
   серверы ▾» нажимается и предлагает «Вернуть режим подписок?» (по замечанию заказчика).

Здесь, у разработчика, — только юнит-тесты затронутого модуля, ruff и `node --check` панели.
Перезагрузка, браузер, телефон и Xray не проверялись — всё это на этой машине.

### Главное правило безопасности

Пока включён «весь дом»: пропал интернет на машине (сайты в шагах 6.4/6.5 не открылись), панель с
телефона через Tailscale не открылась два раза подряд, заказчик говорит, что пропал доступ, или
не отвечает на вопрос **2 минуты** — **сразу** раздел «Если что-то пошло не так» (вернуть режим
подписок командой). Не ждать, не продолжать шаги. Перед каждым включением «всего дома» ставится
страховочный таймер: через 25 минут он сам вернёт режим подписок, даже если доступа к машине не
будет ни у кого.

### Что где на экране панели (для снимков)

- **Верх страницы**: слева — значок и «XGW шлюз»; справа — **метка состояния** в рамке со
  скруглёнными краями и цветной точкой («Работает», «Через бесплатные серверы»,
  «Бесплатные серверы подключаются»…). В режиме «весь дом» у метки справа знак **▾** — это
  кнопка.
- **Левая колонка**: главная карточка — большая круглая кнопка питания, заголовок, строка
  сервера; в режиме «весь дом» под ней — полоса «Весь дом идёт через бесплатные серверы…» с
  кнопкой **«Вернуть режим подписок»**. Ниже — карточки «Подписки», «Tailscale», «Телефоны»,
  «Ядра», «Проверка сети».
- **Правая колонка**: две вкладки — **«Подписки»** и **«Бесплатные серверы»**. На вкладке
  «Бесплатные серверы» справа вверху кнопки: «Опросить источники», **«Весь дом через
  бесплатные»** (в режиме «весь дом» вместо неё — «Вернуть режим подписок») и **«Выключить»**
  (при выключенном наблюдении — «Включить наблюдение»). Ниже — «События».
- **Окно подтверждения** — по центру экрана: заголовок, текст, кнопки «Отмена» и кнопка
  действия справа.

### Проверки JavaScript (выполнять в консоли страницы панели)

- **J1 — метка вверху:**
  `(() => { const c = document.getElementById("chip"); return [c.tagName, c.textContent.trim(), c.disabled, c.title].join(" | "); })()`
- **J2 — значки (эмодзи) в видимом тексте:**
  `[...document.body.innerText.matchAll(/\p{Extended_Pictographic}|[\u{1F1E6}-\u{1F1FF}]/gu)].length`
- **J3 — двойные разделители в видимом тексте:**
  `(document.body.innerText.match(/([|•·\/–—])[ \t]+\1/g) || []).length`
- **J4 — окно подтверждения:**
  `(() => { const d = document.getElementById("confirm-dialog"); return [d.open, document.getElementById("confirm-title").textContent, document.getElementById("confirm-yes").textContent].join(" | "); })()`
- **J5 — адрес панели по tailnet** (для телефона; **в отчёт не писать**):
  `(document.getElementById("ts-serve-url") || {}).href || "нет"`

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, сон машины —
  **никогда**; `reboot` — только сам заказчик и только в шаге 9.2 (пункт 6 согласия).
  Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`,
  `apt`; команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`. `systemd-run` и
  `systemctl stop` — только для страховочных таймеров `xgw-fpfix3-guard` и `xgw-fpfix3-guard2`.
  `sudo xgw pool mode …` — только в шаге 4.1 (`observe`), в «Если не так» шагов, где это
  написано, и в разделе «Если что-то пошло не так». `sudo xgw apply --now` — только если это
  прямо написано в «Если не так».
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`), `https://example.com` и
  `https://www.wikipedia.org`. Сайты источников (vpngate, vpnbook), файлы списков на GitHub,
  сайты проверки IP и страны — не открывать.
- В панели нажимать **только** то, что написано в шагах: вкладки «Подписки» и «Бесплатные
  серверы», «Весь дом через бесплатные» и кнопку подтверждения в его окне, метку вверху и
  «Вернуть режим подписок» в её окне, «Выключить», «Включить наблюдение», «Отмена» в окне
  подтверждения. **Не нажимать**: кнопку питания, «Замерить скорость», «Проверить запасные»,
  «Обновить», «Опросить источники», переключатели Tailscale, «Ядра», «Проверить сеть», выбор
  серверов, строки серверов и устройств, «Добавить», «Убрать», «Автовыбор».
- На телефоне через adb — только команды шагов 6.4, 6.5, 9.3 (экран, Wi-Fi, открыть адрес,
  снимок). Ничего не устанавливать и не удалять, настройки кроме Wi-Fi не трогать.
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, код XGW. Печатать `config.toml`, `panel.json`, рабочие конфиги
  Xray и sing-box, файлы в `/var/lib/xgw/freepool`, базу `/var/lib/xgw/state.db`. Коммитить
  что-либо, кроме файла отчёта (§12). Снимки экрана (`*.png`) и файл `ts-url.txt` в git не
  добавлять.
- Писать в отчёт: **имена серверов**, адреса tailnet, имена `*.ts.net`, токен из ссылки
  панели, имена устройств и пользователей (имя пользователя → `<user>`), внешние IP, адреса и
  домены подписок, IP, домены и ссылки серверов VPN, логины и пароли, строки журнала. Можно:
  адреса устройств в домашней сети (`192.168.…`), коды стран, названия источников, надписи
  панели без имён серверов, счётчики, статусы, размеры, времена, строки помощника.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю исправление после прошлой проверки: после перезагрузки режим «весь дом» снимался, а
трафик до утра оставался на бесплатных серверах. Нажатия в панели и осмотр экрана я делаю сам,
в управляемом браузере. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд. WAN и DHCP установка не трогает. Ядра Xray 26.10.29
и sing-box 1.14.4 останутся.
(2) Если наблюдение за бесплатными серверами выключено, я включу его и подожду 30 минут.
(3) Я сам открою панель в управляемом браузере и буду нажимать в ней: вкладки, «Весь дом через
бесплатные» с подтверждением, метку вверху и «Вернуть режим подписок», «Выключить» и «Включить
наблюдение»; для проверки интернета открою example.com и wikipedia.org.
(4) Перед каждым включением «всего дома» — страховочный таймер: через 25 минут он сам вернёт
режим подписок, даже если доступа к машине не будет.
(5) Через 5 и 15 минут после включения проверю, открывается ли панель шлюза с телефона через
Tailscale по мобильной сети. Если телефон подключён к этому компьютеру по USB с разрешённой
отладкой (adb), я сделаю это сам: выключу на телефоне Wi-Fi, открою панель, сделаю снимок экрана
телефона и включу Wi-Fi обратно. Иначе попрошу сделать это вас. Мобильные данные на телефоне
должны быть включены, Tailscale на телефоне — включён.
(6) Главное: перезагрузка машины в режиме «весь дом» — чтобы проверить, что после неё и режим, и
трафик сами возвращаются на подписку. Перезагрузку делаете вы; после неё нужно снова запустить
меня с этим ТЗ, чтобы я закончил проверку.
(7) В конце я на 4 минуты выключу наблюдение (проверю, что проверки серверов останавливаются) и,
если до проверки оно было включено, включу обратно.
Проверка займёт около двух часов. Можно согласиться не на все пункты.»

Против пункта 1, 3 или 4 — **стоп**. Против 2 при выключенном наблюдении — шаги 4–10 пропустить.
Против 5 — шаги 6.4, 6.5 и вопрос о телефоне в 9.3 без телефона (только остальное). Против 6 — §9
пропустить (в отчёте: «главная проверка не выполнялась»). Против 7 — §10 пропустить. В отчёте у
пропущенного — «не выполнялся». Если ответа нет — не начинать, спросить ещё раз.

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-fpfix3" && chmod 700 "$HOME/xgw-fpfix3" && cd "$HOME/xgw-fpfix3" && cat > fpfix3check.py <<'EOF'
"""XGW 0.2.0, бесплатный пул: рабочий конфиг следует режиму «весь дом» (отчёт m2b2fix2) —
помощник проверки. Только читает: состояние XGW (/run/xgw), базу событий (/var/lib/xgw/state.db
— только чтение), рабочий конфиг Xray, время итогов проверок пула и вывод команд со стандартного
ввода — счётчики, коды стран, итоги и да/нет, без адресов, имён, ссылок и ключей. Время — в
секундах с 1970 (date +%s). Режимы: units, pool, route, mark, state, watch on|back, events,
applies, checks, sstp, diag, log."""
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
LIB = os.environ.get("FPFIX3_LIB", "/opt/xgw/lib")
NAME = re.compile("«[^»]*»")
TS = ["domain:tailscale.com", "domain:tailscale.io"]
MARKS = {"on": "бесплатный пул: весь дом через бесплатные серверы",
         "back": "режим подписок возвращён"}
GOALS = {"on": "on", "back": "observe"}
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


def since_arg():
    try:
        return float(sys.argv[2])
    except (IndexError, ValueError):
        return time.time() - 3600


def target(rule):
    if rule.get("balancerTag"):
        return f"балансировщик {rule['balancerTag']}"
    return f"выход {rule.get('outboundTag')}"


def pool_of(status):
    return status.get("free_pool") if isinstance(status.get("free_pool"), dict) else {}


def flow_state(status):
    pool = pool_of(status)
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


def applied_text(detail):
    return NAME.sub("«…»", detail.split(" (")[0])


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
elif mode == "pool":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    pool = pool_of(status)
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
    whole = cfg.free_pool.mode == "on"
    print(f"режим пула: {cfg.free_pool.mode}; последнее правило → "
          f"{target(rules[-1]) if rules else 'правил нет'}; несущий канал (http-in, socks-in): "
          f"{'есть' if carrier else 'нет'}; DNS по TCP: {tcp}; правило Tailscale → "
          f"{target(ts_rule) if ts_rule else 'нет'}")
    print(f"рабочий конфиг совпадает с режимом: {'да' if carrier == whole else 'НЕТ'}; новый "
          f"конфиг ждёт окна перезапуска: "
          f"{'да' if paths.pending_config_file.exists() else 'нет'}")
elif mode == "mark":
    _cfg, paths = xgw()
    print(f"метка «весь дом в этой загрузке»: {'есть' if paths.house_file.exists() else 'нет'}")
elif mode == "state":
    cfg, paths = xgw()
    shown = pool_of(read_json(paths.status_file) or {}).get("mode") or "off"
    print(f"режим в настройках: {cfg.free_pool.mode}; в состоянии шлюза: {shown}; совпадают: "
          f"{'да' if shown == cfg.free_pool.mode else 'НЕТ'}")
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
    last, samples, closed, first, reached = None, 0, 0, None, None
    while time.time() < pressed + WATCH:
        status = read_json(paths.status_file) or {}
        state = flow_state(status)
        shown = pool_of(status).get("mode") or "off"
        samples += 1
        closed += "ЗАКРЫТО" in state
        if first is None:
            first = (time.time() - pressed, shown)
        if reached is None and shown == goal:
            reached = time.time() - pressed
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
    print(f"первый замер: +{first[0]:.0f} с после нажатия, режим в состоянии шлюза на нём: "
          f"{first[1]}; режим {goal} в состоянии шлюза — "
          + (f"с +{reached:.0f} с" if reached is not None else "НЕ появился за 3 минуты"))
    print(f"Xray: запущен {show('xgw-xray.service', 'ExecMainStartTimestamp') or '?'}")
elif mode == "events":
    _cfg, paths = xgw()
    for ts, kind, detail in events_since(paths, since_arg()):
        if kind == "freepool":
            print(f"{stamp(ts)} {NAME.sub('«<сервер>»', detail)}")
        elif kind == "apply" and "бесплатный пул" in detail:
            print(f"{stamp(ts)} применение: {applied_text(detail)}")
elif mode == "applies":
    _cfg, paths = xgw()
    since = since_arg()
    rows = [(ts, applied_text(detail)) for ts, kind, detail in events_since(paths, since)
            if kind == "apply"]

    def count(*words):
        return sum(1 for _ts, detail in rows if all(word in detail for word in words))

    bad = sum(1 for _ts, detail in rows
              if "отклонён" in detail or "откат" in detail or "не поднялся" in detail)
    print(f"применений с {stamp(since)}: {len(rows)}; «режим подписок» с перезапуском Xray: "
          f"{count('бесплатный пул: режим подписок', 'с перезапуском')}; «весь дом» с "
          f"перезапуском Xray: {count('бесплатный пул: весь дом', 'с перезапуском')}; отложено "
          f"до окна перезапуска: {count('отложен')}; отказ или откат: {bad}")
    for ts, detail in rows:
        if "бесплатный пул" in detail or "отложен" in detail:
            print(f"  {stamp(ts)} {detail}")
elif mode == "checks":
    _cfg, paths = xgw()
    from xgw.freepool.store import PoolStore

    since = since_arg()
    times = sorted(float(record.get("checked_at") or 0)
                   for key, record in PoolStore(paths).candidates().items()
                   if not key.startswith("_"))
    after = [ts for ts in times if ts >= since]
    print(f"проверок серверов пула с {stamp(since)}: {len(after)}"
          + (f" (последняя — {stamp(after[-1])})" if after else "")
          + f"; записей итогов всего: {len(times)}")
elif mode == "sstp":
    _cfg, paths = xgw()
    pool = pool_of(read_json(paths.status_file) or {})
    if not pool:
        print("сводки пула нет: наблюдение выключено")
    else:
        fails = ", ".join(f"{code} {number}" for code, number in
                          sorted((pool.get("tunnel_failures") or {}).items())) or "нет"
        print(f"SSTP в списке: {pool.get('sstp')}; туннелем за сутки: попыток "
              f"{pool.get('tunnel_attempts', 0)}, поднялось {pool.get('tunnels_up', 0)}; "
              f"отказы: {fails}; подключений за час {pool.get('handshakes_hour', 0)}, за сутки "
              f"{pool.get('handshakes_day', 0)}; бэкенд: {pool.get('tunnel_backend') or 'готов'}")
elif mode == "diag":
    for line in sys.stdin.read().splitlines():
        found = re.match(r"(\S+)\s+(Tailscale: [^:]+):", line)
        if found:
            print(f"{found.group(1)} {found.group(2)}")
        elif re.match(r"\S+\s+(Весь дом через бесплатный пул|Бесплатный пул|Устройства через "
                      r"бесплатный пул):", line) or line.startswith("Итог:"):
            print(line)
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, word in (
        ("весь дом снят после перезагрузки", "весь дом снят после перезагрузки"),
        ("«режим подписок»: применено с перезапуском Xray",
         "бесплатный пул: режим подписок: применено с перезапуском Xray"),
        ("«весь дом»: применено с перезапуском Xray",
         "бесплатный пул: весь дом: применено с перезапуском Xray"),
        ("нужен перезапуск Xray — отложен", "нужен перезапуск Xray — отложен"),
        ("у всего дома закрыто", "у всего дома закрыто"),
        ("откат на last-good", "last-good"),
        ("метка всего дома не записана", "метка всего дома через пул не записана"),
        ("шаг пула не выполнен", "бесплатный пул: шаг не выполнен"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | pool | route | mark | state | watch on|back | events | applies | "
          "checks | sstp | diag | log")
EOF
python3 -c "import hashlib;d=open('fpfix3check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `27becd61fc89c3fe`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки:

```bash
cd "$HOME/xgw-fpfix3" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units pool route mark state sstp; do sudo python3 -I fpfix3check.py $m; done | tee -a before.txt
```

Ожидается:
- `Состояние: …` (обычно `HEALTHY`), `Перехват: включён …`, `Xray …` 26.10.29,
  `sing-box …` 1.14.4 — записать;
- первая строка `xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать,
  какая** (от неё зависят шаги 4.1 и 10.4);
- четыре службы `active`;
- строки `route` — **записать обе дословно**. Если «режим пула: off» (или observe), а
  «последнее правило → балансировщик pool» и «рабочий конфиг совпадает с режимом: НЕТ» — это и
  есть дефект прошлой проверки (машина в «застрявшем» состоянии); тогда и строка
  «Ожидает окна перезапуска…» в `xgw status` — записать «до установки: застрявший конфиг — да».
  Иначе — «застрявший конфиг — нет»;
- `sstp` — записать (статистика туннелей SSTP за сутки нужна для решения о следующем этапе).

Если не так: первая строка `xgw pool` — «весь дом через бесплатные серверы» — выполнить
`sudo xgw pool mode observe`, подождать минуту и повторить шаг. Не `HEALTHY` — записать и
продолжить.

Шаг 1.4. Есть ли телефон по adb (только если заказчик согласился на пункт 5):

```bash
if command -v adb >/dev/null; then adb devices | sed 1d | awk 'NF{print $2}' | sort | uniq -c; echo "adb: есть"; else echo "adb: нет"; fi
```

Ожидается одно из:
- `1 device` и «adb: есть» — телефон доступен: в шагах 6.4, 6.5, 9.3 делай телефонную часть
  сам (вариант А);
- `1 unauthorized` — **попроси заказчика** (дословно): «На телефоне появился запрос «Разрешить
  отладку по USB?» — разрешите, пожалуйста.» — и повтори шаг;
- пусто или «adb: нет» — телефонную часть делает заказчик (вариант Б). Ничего не устанавливать.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def applied_whole' src/xgw/generator/builder.py && grep -q 'def _house_sync' src/xgw/daemon.py && grep -q '^HOUSE_SYNC = 300.0' src/xgw/daemon.py && grep -q 'class _PoolCancel' src/xgw/daemon.py && grep -q 'всё ещё ведёт' src/xgw/diag.py && grep -q 'SEP_REPEAT' src/xgw/ui/app.js && grep -q '<button id="chip"' src/xgw/ui/index.html && echo "правка в коде: есть"; cd "$HOME/xgw-fpfix3"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fpfix3/install-time.txt" && date +%s > "$HOME/xgw-fpfix3/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fpfix3/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw' "$HOME/xgw-fpfix3/install.txt"; cd "$HOME/xgw-fpfix3"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 3 минуты после установки:

```bash
sleep 180; cd "$HOME/xgw-fpfix3" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee after-install.txt; for m in units route mark state; do sudo python3 -I fpfix3check.py $m; done | tee -a after-install.txt; sudo python3 -I fpfix3check.py applies "$(cat t-install.txt)" | tee -a after-install.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfix3check.py diag | tee diag-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpfix3check.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; строки «Ожидает окна
  перезапуска» **нет**; четыре службы `active`;
- `route`: «последнее правило → балансировщик auto; несущий канал: нет; DNS по TCP: 0; правило
  Tailscale → нет»; **«рабочий конфиг совпадает с режимом: да; новый конфиг ждёт окна
  перезапуска: нет»**;
- `mark`: «нет»; `state`: «совпадают: да»;
- `applies`: «отказ или откат: 0». Если в шаге 1.3 был застрявший конфиг — здесь ожидается
  ««режим подписок» с перезапуском Xray: 1» (или конфиг уже пересобран установкой — тогда 0, но
  `route` всё равно «да») — записать;
- `diag`: строки «OK Tailscale: …», «OK Бесплатный пул: …» (или его нет при off), «Итог: …» —
  записать; строки «FAIL Весь дом через бесплатный пул» **нет**;
- журнал: «Traceback: 0».

Если не так: «совпадает с режимом: НЕТ» — подождать ещё 5 минут и повторить шаг без `sleep`;
снова НЕТ — **дефект** (записать строки), выполнить `sudo xgw apply --now`, через минуту —
`sudo python3 -I fpfix3check.py route`, записать и продолжить. Не `HEALTHY` — подождать 2
минуты и повторить; снова нет — записать и продолжить. Xray стал 26.10.21 — **дефект**,
продолжить.

## 3. Панель в управляемом браузере

Шаг 3.1. Ссылка входа в панель (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

Ожидается: «Панель XGW: http://127.0.0.1:8781/?token=…».

**Действие:** в управляемом браузере открой эту ссылку целиком (введи её в адресную строку и
нажми Enter). Размер окна — не меньше 1280×800. Подожди 5 секунд, сделай снимок экрана.

Ожидается на снимке: вверху слева «XGW», справа — метка состояния (например «Работает»);
справа — вкладки «Подписки» и «Бесплатные серверы». Страницы входа нет.

Если не так: «Панель открывается только по адресу…» — открой ссылку ещё раз точно с
`http://127.0.0.1:8781/`; пустая страница — подожди 10 секунд и обнови (F5); снова нет — **стоп**,
сообщить заказчику.

Шаг 3.2. Метка вверху в режиме подписок. Выполни **J1**.

Ожидается: `BUTTON | <текст состояния> | true | ` — метка есть, но **не нажимается**
(`true` — неактивна, подсказки нет). На снимке у метки **нет** знака ▾.

Если не так: `DIV | …` — в браузере старая страница: обнови (Ctrl+F5) и повтори J1; снова
`DIV` — **дефект** (установка не обновила панель). `false` в режиме не «весь дом» — **дефект**.

Шаг 3.3. Адрес панели по tailnet для телефона (только вариант А шага 1.4; иначе пропустить).
Выполни **J5**. Ответ — адрес вида `https://….ts.net…` или «нет».

Если адрес есть — выполни команду, **подставив его вместо `<АДРЕС>`** (в одинарных кавычках;
это единственная подстановка в ТЗ; адрес в отчёт не писать):

```bash
cd "$HOME/xgw-fpfix3" && printf '%s\n' '<АДРЕС>' > ts-url.txt && chmod 600 ts-url.txt && grep -c '^https://' ts-url.txt
```

Ожидается: `1`.

Если J5 вернул «нет» — в карточке Tailscale панель по tailnet выключена: телефонную часть
делает заказчик (вариант Б), как привык открывать панель с телефона.

## 4. Наблюдение

Шаг 4.1. Только если в шаге 1.3 наблюдение было **выключено** (иначе — пропустить, записать
«уже было включено» и подождать 5 минут):

```bash
cd "$HOME/xgw-fpfix3" && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; date +%s > t-observe.txt
```

Ожидается: «Наблюдение за бесплатным пулом включено: …».

**Скажи заказчику** (дословно): «Наблюдение включено. Дальше 30 минут жду, пока шлюз проверит
бесплатные серверы.» Затем подожди 30 минут:

```bash
sleep 1800; date '+%T'
```

(Если терминал обрывает длинные команды — `sleep 110` повторить 17 раз.)

Шаг 4.2.

```bash
cd "$HOME/xgw-fpfix3" && for m in pool state sstp; do sudo python3 -I fpfix3check.py $m; done | tee rows.txt
```

Ожидается: `pool` — «пригодно» больше 0; `state` — «совпадают: да»; `sstp` — записать.

Если не так: «пригодно 0» — подождать ещё 30 минут и повторить; снова 0 — шаги 6–9 пропустить
(«отложено: нет допущенных серверов»), сделать §5, затем §10 и §11.

## 5. Имена серверов на экране

Шаг 5.1. **Действие:** в браузере обнови страницу (F5), подожди 5 секунд, нажми вкладку
**«Подписки»**, сделай снимок экрана. Выполни **J2** и **J3**.

Ожидается: `0` и `0`. На снимке в именах серверов нет квадратиков, «тофу» и двойных «| |».

Шаг 5.2. **Действие:** нажми вкладку **«Бесплатные серверы»**, подожди 3 секунды, сделай снимок
экрана. Выполни **J2** и **J3**.

Ожидается: `0` и `0`; слова в именах не слиплись (например «x10 Германия», а не «x10Германия»);
на месте убранных значков — один разделитель («Хельсинки | [BL]»), а не «| |».

Если не так (5.1 или 5.2): J2 больше 0 — **дефект** «значки на экране»; J3 больше 0 —
**дефект** «двойные разделители» (записать число, вкладку; имена серверов в отчёт не писать).

## 6. Весь дом и удалённый доступ

Шаг 6.1. Страховочный таймер — **до** включения:

```bash
cd "$HOME/xgw-fpfix3" && date '+%F %T' | tee guard-time.txt && sudo systemd-run --on-active=25min --unit=xgw-fpfix3-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-fpfix3-guard.timer | head -3 | tee -a guard.txt
```

Ожидается: «Running timer as unit: xgw-fpfix3-guard.timer», в списке таймеров — строка
`xgw-fpfix3-guard.timer` со временем срабатывания через ~25 минут.

Если не так: таймера нет — **стоп**: без страховки «весь дом» не включать (шаги 6–9
пропустить, §10).

Шаг 6.2. Включение «всего дома» (нажимаешь ты):
1. В браузере — вкладка «Бесплатные серверы». Нажми кнопку **«Весь дом через бесплатные»**.
2. Сделай снимок. Ожидается окно по центру: заголовок «Пустить весь дом через бесплатные
   серверы?», кнопки «Отмена» и «Весь дом через бесплатные». Выполни **J4**: ожидается
   `true | Пустить весь дом через бесплатные серверы? | Весь дом через бесплатные`.
3. Нажми в окне **«Весь дом через бесплатные»**.
4. **Сразу** (в течение 30 секунд) выполни:

```bash
cd "$HOME/xgw-fpfix3" && sudo python3 -I fpfix3check.py watch on | tee watch-on.txt
```

Ожидается (команда идёт около 3 минут): «нажатие: …»; строки «+N с»: «режим on: подключаются»
(возможно) → «режим on: через сервер (XX), живых … из …»; **ни одной строки «ЗАКРЫТО»**;
«событий «допущенных серверов нет»: 0; «все серверы пула молчат»: 0»; в предпоследней строке —
«режим on в состоянии шлюза — с +N с» (N — не больше, чем «первый замер»).

Если не так: окно подтверждения не появилось — снимок, **дефект**, §10. «нажатия не было» —
снимок экрана, проверь, что нажал кнопку в окне, и повтори пункты 1–4 один раз. «ЗАКРЫТО» или
такие события — **дефект** (записать строки помощника) и продолжить. «через сервер» не появилось
за три минуты — раздел «Если что-то пошло не так».

Шаг 6.3. Что собрал шлюз и как выглядит панель:

```bash
cd "$HOME/xgw-fpfix3" && for m in pool route mark state; do sudo python3 -I fpfix3check.py $m; done | tee house.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfix3check.py diag | tee diag-house.txt
```

Ожидается:
- `pool`: «режим on: через сервер (XX), живых … из …»;
- `route`: «последнее правило → балансировщик pool; несущий канал: есть; DNS по TCP: 2; правило
  Tailscale → балансировщик auto»; «рабочий конфиг совпадает с режимом: да; новый конфиг ждёт
  окна перезапуска: нет»;
- `mark`: «есть»; `state`: «режим в настройках: on; в состоянии шлюза: on; совпадают: да»;
- `diag`: «OK Весь дом через бесплатный пул: через бесплатный пул, серверов в «pool»: N;
  подписка — только входам демона и Tailscale (несущий канал)»; строки «Tailscale: …» — OK.

**Действие в браузере:** обнови страницу (F5), подожди 5 секунд, сделай снимок, выполни **J1**.

Ожидается: J1 — `BUTTON | Через бесплатные серверы | false | Нажмите, чтобы вернуть режим
подписок`; на снимке — метка вверху «Через бесплатные серверы» со знаком **▾**; в главной
карточке — полоса «Весь дом идёт через бесплатные серверы…» с кнопкой «Вернуть режим подписок».
**Метку пока не нажимать** (это шаг 7.1).

Если не так: в `route` «правило Tailscale → нет» или FAIL у «Весь дом через бесплатный пул» —
**дефект**, сразу раздел «Если что-то пошло не так». J1 с `true` или без ▾ — **дефект**
«метка не переключатель», продолжить.

Шаг 6.4. Через **5 минут** после нажатия (по времени «нажатие» из watch-on.txt) — доступ.

Интернет машины: **Действие:** в браузере открой новую вкладку, адрес `https://example.com`,
подожди 10 секунд, снимок; затем `https://www.wikipedia.org`, снимок; вернись на вкладку панели.
Ожидается: обе страницы открылись (заголовок «Example Domain»; логотип и поиск Wikipedia).

Телефон, **вариант А** (adb):

```bash
cd "$HOME/xgw-fpfix3" && date '+%T' | tee -a check-5.txt; adb shell input keyevent KEYCODE_WAKEUP && adb shell cmd wifi set-wifi-enabled disabled && sleep 15 && adb shell am start -a android.intent.action.VIEW -d "$(cat ts-url.txt)" >/dev/null && sleep 30 && adb exec-out screencap -p > phone-5.png; adb shell cmd wifi set-wifi-enabled enabled; ls -l phone-5.png | awk '{print "снимок телефона, байт:", $5}'
```

Затем **посмотри на снимок** `$HOME/xgw-fpfix3/phone-5.png`:
- на экране страница XGW — панель (метка состояния, вкладки) **или страница входа XGW** →
  «панель с телефона открылась» (шлюз ответил через tailnet);
- ошибка браузера («Не удаётся получить доступ к сайту», «ERR_…», «This site can't be
  reached», «Нет подключения к интернету»), пустой экран загрузки → «не открылась»;
- экран блокировки → **попроси заказчика** (дословно): «Разблокируйте, пожалуйста, телефон», и
  повтори команду;
- в строке состояния вверху должен быть значок мобильной сети, а не Wi-Fi (Wi-Fi выключен).

Телефон, **вариант Б** (без adb) — **спроси заказчика** (дословно): «Выключите, пожалуйста,
Wi-Fi на телефоне и откройте панель шлюза через Tailscale по мобильной сети. Она открылась?
Потом включите Wi-Fi обратно.»

Затем:

```bash
cd "$HOME/xgw-fpfix3" && for m in pool route; do sudo python3 -I fpfix3check.py $m; done | tee -a check-5.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfix3check.py diag | tee -a check-5.txt
```

Ожидается: сайты открылись; панель с телефона открылась; `pool` — «через сервер …»; `route` —
«совпадает с режимом: да»; строки `Tailscale: …` — OK.

Если не так: телефон не открыл панель — подождать минуту и повторить телефонную часть; снова
нет — **дефект «удалённый доступ»**: сразу раздел «Если что-то пошло не так». Сайты не открылись
— повторить через минуту; снова нет — тот же раздел.

Шаг 6.5. Через **15 минут** после нажатия — то же, что в шаге 6.4 (сайты, телефон, команды), с
файлами `check-15.txt` и `phone-15.png` вместо `check-5.txt` и `phone-5.png`:

```bash
cd "$HOME/xgw-fpfix3" && date '+%T' | tee -a check-15.txt; adb shell input keyevent KEYCODE_WAKEUP && adb shell cmd wifi set-wifi-enabled disabled && sleep 15 && adb shell am start -a android.intent.action.VIEW -d "$(cat ts-url.txt)" >/dev/null && sleep 30 && adb exec-out screencap -p > phone-15.png; adb shell cmd wifi set-wifi-enabled enabled; ls -l phone-15.png | awk '{print "снимок телефона, байт:", $5}'
```

(Команда выше — только вариант А; в варианте Б — вопрос заказчику, как в 6.4.)

```bash
cd "$HOME/xgw-fpfix3" && for m in pool route; do sudo python3 -I fpfix3check.py $m; done | tee -a check-15.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfix3check.py diag | tee -a check-15.txt
```

Ожидается и «Если не так» — как в шаге 6.4.

## 7. Возврат режима подписок — меткой вверху

Шаг 7.1. Нажимаешь ты:
1. В браузере нажми **метку вверху справа** («Через бесплатные серверы ▾»).
2. Снимок. Ожидается окно по центру: заголовок «Вернуть режим подписок?», текст «Трафик всего
   дома снова пойдёт через серверы подписки; наблюдение за бесплатными серверами продолжится.»,
   кнопки «Отмена» и «Вернуть режим подписок». Выполни **J4**: ожидается
   `true | Вернуть режим подписок? | Вернуть режим подписок`.
3. Нажми в окне **«Отмена»**. Снимок: окно закрылось, метка по-прежнему «Через бесплатные
   серверы ▾», режим не изменился (это проверка, что случайное нажатие ничего не меняет).
4. Снова нажми метку вверху, в окне нажми **«Вернуть режим подписок»**.
5. **Сразу** (в течение 30 секунд) выполни:

```bash
cd "$HOME/xgw-fpfix3" && sudo python3 -I fpfix3check.py watch back | tee watch-back.txt; sudo systemctl stop xgw-fpfix3-guard.timer; systemctl list-timers --all --no-pager xgw-fpfix3-guard.timer | head -3 | tee guard-off.txt
```

Ожидается: «нажатие: …»; «режим on: …» → «режим observe: через пул никто»; ни одной строки
«ЗАКРЫТО»; событие «… режим подписок возвращён, наблюдение продолжается»; строка «первый замер:
+N с после нажатия, режим в состоянии шлюза на нём: **observe**» (при N до 60 с; раньше режим
отставал на 2–3 минуты) и «режим observe в состоянии шлюза — с +N с»; таймер
`xgw-fpfix3-guard.timer` больше не в списке («0 timers listed»).

Если не так: окно после нажатия метки не появилось — снимок, **дефект «метка не
переключатель»**, нажми «Вернуть режим подписок» в главной карточке и выполни команду пункта 5.
«нажатия не было за 10 минут» — `sudo xgw pool mode observe`, затем
`sudo systemctl stop xgw-fpfix3-guard.timer`, дальше 7.2. Режим на первом замере «on» при N до
60 с — **дефект «режим в состоянии отстаёт»**, продолжить.

Шаг 7.2. Через минуту:

```bash
sleep 60; cd "$HOME/xgw-fpfix3" && for m in pool route mark state; do sudo python3 -I fpfix3check.py $m; done | tee back.txt
```

Ожидается: «режим observe: через пул никто»; «последнее правило → балансировщик auto; несущий
канал: нет; DNS по TCP: 0; правило Tailscale → нет»; «рабочий конфиг совпадает с режимом: да;
новый конфиг ждёт окна перезапуска: нет»; «метка …: нет»; «совпадают: да».

**Действие в браузере:** снимок, **J1**. Ожидается: `BUTTON | <текст состояния> | true | ` — метка
снова не нажимается, знака ▾ нет; полосы «Весь дом идёт…» в главной карточке нет.

## 8. Секреты

```bash
cd "$HOME/xgw-fpfix3" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt
```

Ожидается: `0`. Если больше — **дефект** (строки журнала в отчёт не копировать).

## 9. Перезагрузка в режиме «весь дом» — главная проверка (пункт 6 согласия)

Только если заказчик согласился на пункт 6. Иначе — пропустить, в отчёте «не выполнялся».

Шаг 9.1. Второй страховочный таймер (своё имя):

```bash
cd "$HOME/xgw-fpfix3" && sudo systemd-run --on-active=25min --unit=xgw-fpfix3-guard2 /usr/local/bin/xgw pool mode observe 2>&1 | tee guard2.txt; systemctl list-timers --all --no-pager xgw-fpfix3-guard2.timer | head -3 | tee -a guard2.txt
```

Ожидается: «Running timer as unit: xgw-fpfix3-guard2.timer». Нет таймера — §9 пропустить.

**Действие в браузере:** вкладка «Бесплатные серверы» → **«Весь дом через бесплатные»** → в
окне **«Весь дом через бесплатные»** (как в шаге 6.2, пункты 1–3). Затем подожди 3 минуты:

```bash
sleep 180; cd "$HOME/xgw-fpfix3" && for m in pool route mark; do sudo python3 -I fpfix3check.py $m; done | tee before-reboot.txt; date '+%F %T' | tee reboot-time.txt; date +%s > t-reboot.txt
```

Ожидается: «режим on: через сервер …»; `route` — «последнее правило → балансировщик pool …»,
«совпадает с режимом: да»; «метка …: есть».

Если не так: «режим on» не наступил — раздел «Если что-то пошло не так», §9 пропустить.

Шаг 9.2. **Скажи заказчику** (дословно): «Перезагрузите, пожалуйста, компьютер. После загрузки
войдите в свой сеанс, снова запустите меня с этим ТЗ (файл `$HOME/xgw-fpfix3/plan.md`) и
напишите «продолжи с шага 9.3». Страховочный таймер перезагрузку не переживёт — он и не нужен:
после загрузки шлюз сам вернёт режим подписок.»

Дальше ничего не делай, пока заказчик не напишет «продолжи с шага 9.3».

Шаг 9.3. После перезагрузки. Сначала подожди 3 минуты после входа заказчика и запиши время
загрузки:

```bash
sleep 180; cd "$HOME/xgw-fpfix3" && date -d "$(uptime -s)" +%s > t-boot.txt && echo "загрузка: $(uptime -s)" | tee after-reboot.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a after-reboot.txt; sudo xgw pool 2>&1 | head -1 | tee -a after-reboot.txt; for m in units pool route mark state; do sudo python3 -I fpfix3check.py $m; done | tee -a after-reboot.txt; sudo python3 -I fpfix3check.py applies "$(cat t-boot.txt)" | tee applies-reboot.txt; sudo python3 -I fpfix3check.py events "$(cat t-boot.txt)" | tee events-reboot.txt; sudo xgw diag 2>&1 | sudo python3 -I fpfix3check.py diag | tee diag-reboot.txt; sudo journalctl -u xgw -b --no-pager | sudo python3 -I fpfix3check.py log | tee log-reboot.txt; systemctl list-timers --all --no-pager 'xgw-fpfix3-*' | tail -1 | tee -a after-reboot.txt
```

Ожидается (это **главный критерий** всей проверки):
- `HEALTHY` (или ещё запускается — повторить команду через 2 минуты без `sleep`), перехват
  включён; строки «Ожидает окна перезапуска» **нет**;
- первая строка `xgw pool` — «… наблюдение (трафик через подписку) …», **не** «весь дом»;
- `pool`: «режим observe: через пул никто»;
- `route`: «последнее правило → балансировщик auto; несущий канал: нет; DNS по TCP: 0; правило
  Tailscale → нет»; **«рабочий конфиг совпадает с режимом: да; новый конфиг ждёт окна
  перезапуска: нет»** (в прошлой проверке здесь был конфиг «весь дом» до 04:00);
- `mark`: «нет»; `state`: «совпадают: да»;
- `applies`: ««режим подписок» с перезапуском Xray: 1» (срочная сборка после загрузки);
  «отложено до окна перезапуска» — 0 или 1 (одно отложенное до срочной сборки допустимо, если
  за ним в списке идёт «бесплатный пул: режим подписок: применено с перезапуском Xray»);
  «отказ или откат: 0» — записать список времён;
- `events`: «бесплатный пул: весь дом снят после перезагрузки — трафик через подписку,
  наблюдение продолжается; включить снова — кнопкой на вкладке» и «применение: бесплатный пул:
  режим подписок: применено с перезапуском Xray» — записать времена (сколько секунд между
  загрузкой и этим применением);
- `diag`: строки «FAIL Весь дом через бесплатный пул» **нет**;
- журнал этой загрузки: «весь дом снят после перезагрузки: 1», ««режим подписок»: применено с
  перезапуском Xray: 1», «у всего дома закрыто: 0», «Traceback: 0»;
- таймеров `xgw-fpfix3-*` нет («0 timers listed»).

Если не так: `route` «совпадает с режимом: НЕТ» — подождать 5 минут и повторить команду без
`sleep`; снова НЕТ — **дефект 1 не исправлен**: записать все строки, выполнить
`sudo xgw apply --now`, через минуту — `sudo python3 -I fpfix3check.py route` (записать), затем
продолжить. После перезагрузки снова «весь дом» в `xgw pool` — **дефект**, сразу раздел «Если
что-то пошло не так».

Затем **браузер:** панель после перезагрузки нужно открыть заново (шаг 3.1: ссылка из
`sudo xgw panel`), снимок, **J1**. Ожидается: метка — состояние режима подписок (например
«Работает»), `true`, без ▾.

Затем **телефон** — как в шаге 6.4 (вариант А — команда с файлом `phone-boot.png`; вариант Б —
вопрос заказчику):

```bash
cd "$HOME/xgw-fpfix3" && adb shell input keyevent KEYCODE_WAKEUP && adb shell cmd wifi set-wifi-enabled disabled && sleep 15 && adb shell am start -a android.intent.action.VIEW -d "$(cat ts-url.txt)" >/dev/null && sleep 30 && adb exec-out screencap -p > phone-boot.png; adb shell cmd wifi set-wifi-enabled enabled; ls -l phone-boot.png | awk '{print "снимок телефона, байт:", $5}'
```

Ожидается: панель (или страница входа XGW) открылась; если на снимке видна метка вверху — режим
подписок, а не «Через бесплатные серверы».

## 10. Выключение наблюдения останавливает проверки (пункт 7 согласия)

Только если заказчик согласился на пункт 7 и наблюдение сейчас включено (`state`: «режим в
настройках: observe»). Иначе — пропустить.

Шаг 10.1. Статистика SSTP до выключения:

```bash
cd "$HOME/xgw-fpfix3" && for m in sstp state; do sudo python3 -I fpfix3check.py $m; done | tee sstp-final.txt
```

Ожидается: строка `sstp` — записать целиком (попыток, поднялось, отказы по кодам).

Шаг 10.2. **Действие в браузере:** вкладка «Бесплатные серверы» → кнопка **«Выключить»**. Снимок.
**Сразу** затем:

```bash
cd "$HOME/xgw-fpfix3" && date +%s > t-off.txt && date '+%T' | tee off.txt; sleep 60; for m in route state; do sudo python3 -I fpfix3check.py $m; done | tee -a off.txt
```

Ожидается: на снимке кнопка сменилась на «Включить наблюдение» (если всплыло сообщение — записать
его текст); `route` — «режим пула: off; последнее правило → балансировщик auto …», «совпадает с
режимом: да; новый конфиг ждёт окна перезапуска: нет»; `state` — «режим в настройках: off; в
состоянии шлюза: off; совпадают: да».

Если не так: панель отказала (сообщение «Через бесплатные серверы идёт устройство…») — записать
текст дословно (без имён устройств), выполнить `sudo xgw pool mode off`, повторить команду этого
шага.

Шаг 10.3. Проверки остановились — через 4 минуты:

```bash
sleep 240; cd "$HOME/xgw-fpfix3" && sudo python3 -I fpfix3check.py checks "$(( $(cat t-off.txt) + 90 ))" | tee checks-off.txt; sudo python3 -I fpfix3check.py route | tee -a checks-off.txt
```

Ожидается: «проверок серверов пула с ЧЧ:ММ:СС: 0» (с 90 секунд после выключения — ни одной;
начатая до нажатия проверка успевает закончиться за эти 90 секунд); `route` — «совпадает с
режимом: да».

Если не так: больше 0 — **дефект «проверки после выключения»** (записать число и «последняя —
…»), продолжить.

Шаг 10.4. Если в шаге 1.3 наблюдение было **включено** — **действие в браузере:** кнопка
**«Включить наблюдение»**, снимок, затем:

```bash
sleep 90; cd "$HOME/xgw-fpfix3" && for m in route state; do sudo python3 -I fpfix3check.py $m; done | tee observe-again.txt
```

Ожидается: `route` — «режим пула: observe …», «совпадает с режимом: да»; `state` — «совпадают:
да» (если «в состоянии шлюза: off» — первая сводка пула ещё не готова: повторить через минуту
без `sleep`).

Если в шаге 1.3 наблюдение было выключено — ничего не включать, записать «оставлено
выключенным».

## 11. Итог

```bash
sleep 60; cd "$HOME/xgw-fpfix3" && date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units pool route mark state; do sudo python3 -I fpfix3check.py $m; done | tee -a final.txt; sudo python3 -I fpfix3check.py applies "$(cat t-install.txt)" | head -1 | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpfix3check.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4, строки «Ожидает окна
перезапуска» нет; четыре службы `active`; режим — как был до проверки (off или observe); `route`
— «совпадает с режимом: да; … ждёт окна перезапуска: нет»; «метка …: нет»; `applies` — «отказ
или откат: 0»; журнал: «у всего дома закрыто: 0», «метка всего дома не записана: 0», «шаг пула
не выполнен: 0», «откат на last-good: 0», «Traceback: 0».

**Браузер:** вкладку панели можно закрыть. **Скажи заказчику** (дословно): «Проверка
закончена, пишу отчёт.»

## Если что-то пошло не так

- В режиме «весь дом» пропал интернет или доступ (сайты не открылись, панель с телефона через
  Tailscale не открылась два раза), или заказчик не отвечает **2 минуты** — **сразу**, не
  дожидаясь ответа:
  `sudo xgw pool mode observe`, затем `sudo systemctl stop xgw-fpfix3-guard.timer
  xgw-fpfix3-guard2.timer` (ошибка «not loaded» у одного из них — норма). Записать время и
  строки `sudo python3 -I fpfix3check.py pool` и `sudo python3 -I fpfix3check.py route`. Дальше —
  шаги 7.2, 8, 10, 11 и отчёт. «Весь дом» больше не включать.
- Сработал страховочный таймер (через 25 минут режим вернулся сам) — записать время и
  продолжить с шага 7.2 (в §9 — с шага 9.3 без перезагрузки: записать «перезагрузка не
  выполнялась, режим вернул таймер»).
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.
- Браузер не открывает панель или кнопки не нажимаются — снимок, сообщить заказчику и
  попросить нажать то же самое вручную; в отчёте пометить «нажато заказчиком».
- adb перестал видеть телефон — дальше телефонная часть вариантом Б. Если команда adb прервалась
  до включения Wi-Fi — выполнить `adb shell cmd wifi set-wifi-enabled enabled`, а без adb —
  попросить заказчика включить Wi-Fi на телефоне.

## 12. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-m2b2fix3-<ДАТА>.md` в клоне (`<ДАТА>` —
дата начала проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, бесплатные серверы, рабочий
конфиг следует режиму» и `git push` в `freepool`. Только этот файл (`git add` только его). Без
имён серверов, адресов (кроме `192.168.…`), доменов, токена и строк журнала. Шаблон (заполни
каждую ячейку; пропущенное — «не выполнялся»):

```markdown
# Отчёт: XGW 0.2.0, бесплатные серверы — рабочий конфиг следует режиму «весь дом»

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
fpfix3check.py: <сумма>. Наблюдение до проверки: <…>. Ядра: Xray <…>, sing-box <…>.
До установки: застрявший конфиг — <да/нет>. Телефон: <adb / вручную заказчиком / не проверялся>.
Исполнитель: <модель>; нажатия и снимки — управляемым браузером <да/частично>.

## Итог
| После перезагрузки: режим / рабочий конфиг совпадает / ждёт окна / срочная сборка через, с | Включение и возврат: «ЗАКРЫТО» | Режим в состоянии при возврате: на первом замере (+с) | Метка вверху: не нажимается в подписках / переключатель во «всём доме» / «Отмена» ничего не меняет | Панель с телефона: +5 / +15 / после перезагрузки | Проверок после «Выключить» | Значки / двойные разделители на экране |
|---|---|---|---|---|---|---|
| <observe / да / нет / N> | <0 / 0> | <observe (+N)> | <да / да / да> | <да / да / да> | <0> | <0 / 0> |

### SSTP за сутки (для решения о следующем этапе)
| Когда | Попыток | Поднялось | Отказы по кодам | Подключений за сутки |
|---|---|---|---|---|
| 1.3 | … | … | … | … |
| 4.2 | … | … | … | … |
| 10.1 | … | … | … | … |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до | — | … |
| 1.4 adb | … | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 панель | … | … |
| 3.2 метка в подписках | … | … |
| 4.1 наблюдение | … | … |
| 4.2 пригодные | … | … |
| 5.1 «Подписки»: J2 / J3 | … | … |
| 5.2 «Бесплатные серверы»: J2 / J3 | … | … |
| 6.1 страховка | … | … |
| 6.2 включение | … | … |
| 6.3 что собрал шлюз, метка | … | … |
| 6.4 доступ +5 мин | … | … |
| 6.5 доступ +15 мин | … | … |
| 7.1 возврат меткой | … | … |
| 7.2 после возврата | … | … |
| 8 секреты | … | … |
| 9.1 перед перезагрузкой | … | … |
| 9.3 после перезагрузки | … | … |
| 10.1 SSTP | … | … |
| 10.2 выключение | … | … |
| 10.3 проверки после выключения | … | … |
| 10.4 наблюдение снова | … | … |
| 11 итог | … | … |

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-fpfix3/…); результаты J1–J4; что видно на
  снимках экрана и телефона словами; ответы заказчика дословно, без имён серверов>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
