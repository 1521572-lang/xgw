# Проверка XGW 0.2.0: учёт расхода трафика и перезагрузка во «всём доме»

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, прокручиваешь страницу,
  делаешь **снимок экрана** и смотришь на него, выполняешь JavaScript в консоли страницы;
- возможно, **adb** — телефон заказчика по USB (шаг 1.4 покажет, есть ли он).

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя;
   единственное исключение — шаг 3.4, там сказано, что подставить), **Ожидается** и **Если не
   так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J1–J6) — выполни её в консоли
   страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-usage/…` (так написано в командах). Время шага —
   по выводу `date` в команде, не по памяти.
5. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
6. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
7. Экземпляр этого ТЗ держи в `$HOME/xgw-usage/plan.md` (не в /tmp: там его стирают). Файл
   помощника создаётся **только** командой шага 1.2.
8. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если какой-то режим `usagecheck.py` выводит `Traceback` — запиши режим и
   последнюю строку ошибки как **дефект помощника** и продолжай шаг по остальным строкам и
   командам `xgw`. Сам файл помощника не исправляй.
9. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши дословно
   строку помощника, отметь «не по ожиданию» и иди дальше. Свои догадки о причине пиши только в
   «Наблюдения» и помечай словом «предположение».

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. Телефон — S25 Ultra. На машине —
Xray 26.10.29 и sing-box 1.14.4, принятые шлюзом через карточку «Ядра»: установка их не
откатывает.

### Что нового (ASSUMPTIONS п. 271)

1. **Учёт расхода трафика.** Карточка **«Трафик»** в панели (кнопки «Сегодня», «7 дней», «30
   дней») и команда `sudo xgw traffic [--days N]`: сколько получило (↓) и отправило (↑) каждое
   устройство сети; сколько ушло через серверы каждой подписки (и «учтено подпиской» — с
   множителями серверов x10 и т. п.); бесплатные серверы; напрямую мимо VPN; всего через
   провайдера (WAN); «шлюз и служебное» = WAN минус устройства. Устройства считает своя таблица
   nftables `ip xgw_acct` (её ставит демон), подписки — счётчики Xray. Демон пишет расход в базу
   раз в минуту.
2. **Установка не отказывает из-за застрявшего конфига**: проверка «Весь дом через бесплатный
   пул» перед установкой — WARN, а не FAIL (после установки демон сам пересоберёт конфиг).
3. **Полоса «Выбран вручную «…»»** над серверами подписок — без значков в имени.
4. **Повтор главной проверки прошлого раза**: перезагрузка именно в режиме «весь дом». В прошлый
   раз страховочный таймер вернул режим подписок в 01:03, а перезагрузка была в 08:02 — то есть
   уже в режиме наблюдения, и проверка не состоялась. Здесь шаг 5.4 по событиям проверяет, каким
   был режим перед перезагрузкой.

### Главное правило безопасности

Пока включён «весь дом»: пропал интернет на машине, панель с телефона через Tailscale не
открылась два раза подряд, заказчик говорит, что пропал доступ, или не отвечает на вопрос **2
минуты** — **сразу** раздел «Если что-то пошло не так» (вернуть режим подписок командой). Перед
включением «всего дома» ставится страховочный таймер: через 25 минут он сам вернёт режим
подписок, даже если доступа к машине не будет ни у кого.

### Что где на экране панели (для снимков)

- **Верх страницы**: слева — значок и «XGW шлюз»; справа — **метка состояния** в рамке с цветной
  точкой («Серверы в порядке», «Через бесплатные серверы ▾»…).
- **Левая колонка**: главная карточка (кнопка питания, заголовок, строка сервера), ниже —
  «Подписки», «Tailscale», «Телефоны», «Ядра», «Проверка сети».
- **Правая колонка**: вкладки **«Подписки»** и **«Бесплатные серверы»**, под ними — карточка
  «Устройства», затем **новая карточка «Трафик»** (справа в её заголовке — кнопки «Сегодня»,
  «7 дней», «30 дней»; ниже — серый текст, список «Устройства», список «Подписки и выходы»; у
  каждой строки — имя, серая метка, строка «↓ … · ↑ …» и тонкая зелёная полоса), ниже —
  «События». Карточка «Трафик» может быть ниже края экрана — **прокрути страницу**.
- На вкладке «Бесплатные серверы» справа вверху: «Опросить источники», **«Весь дом через
  бесплатные»**, **«Выключить»** / «Включить наблюдение».
- **Окно подтверждения** — по центру: заголовок, текст, «Отмена» и кнопка действия справа.

### Проверки JavaScript (в консоли страницы панели)

- **J1 — метка вверху:**
  `(() => { const c = document.getElementById("chip"); return [c.tagName, c.textContent.trim(), c.disabled, c.title].join(" | "); })()`
- **J2 — значки (эмодзи) в видимом тексте:**
  `[...document.body.innerText.matchAll(/\p{Extended_Pictographic}|[\u{1F1E6}-\u{1F1FF}]/gu)].length`
- **J3 — полоса «Выбран вручную»:**
  `(() => { const n = document.getElementById("pin-note"); return n.hidden || !n.textContent ? "полосы нет" : "полоса есть, значков: " + [...n.textContent.matchAll(/\p{Extended_Pictographic}|[\u{1F1E6}-\u{1F1FF}]/gu)].length; })()`
- **J4 — окно подтверждения:**
  `(() => { const d = document.getElementById("confirm-dialog"); return [d.open, document.getElementById("confirm-title").textContent, document.getElementById("confirm-yes").textContent].join(" | "); })()`
- **J5 — адрес панели по tailnet** (для телефона; **в отчёт не писать**):
  `(document.getElementById("ts-serve-url") || {}).href || "нет"`
- **J6 — карточка «Трафик»:**
  `(() => { const t = document.getElementById("usage-text").textContent; return [t.split(":")[0], document.querySelectorAll("#usage-devices > li:not(.empty)").length, document.querySelectorAll("#usage-subs > li:not(.empty)").length, [...document.querySelectorAll(".usage-period")].map((b) => b.getAttribute("aria-pressed")).join(",")].join(" | "); })()`

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, сон машины —
  **никогда**; `reboot` — только сам заказчик и только в шаге 5.3 (пункт 6 согласия).
  Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list` и `nft -j list` в командах помощника), `ip`, `ip netns`,
  `iptables`, `tc`, `sysctl -w`, `apt`; команды `tailscale`, `xray`, `sing-box`, `sstpc`,
  `pppd`. `systemd-run` и `systemctl stop` — только для страховочного таймера `xgw-usage-guard`.
  `sudo xgw pool mode …` — только в шаге 4.1 (`observe`), в «Если не так» шагов, где это
  написано, и в разделе «Если что-то пошло не так». `sudo xgw apply --now` — только если это
  прямо написано в «Если не так».
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`), `https://example.com` и
  `https://www.wikipedia.org`. Единственная загрузка из терминала — команда шага 3.2
  (`speed.cloudflare.com`, 30 МБ). Сайты источников (vpngate, vpnbook), файлы списков на GitHub,
  сайты проверки IP и страны — не открывать.
- В панели нажимать **только** то, что написано в шагах: вкладки «Подписки» и «Бесплатные
  серверы», кнопки периода карточки «Трафик», «Весь дом через бесплатные» и кнопку подтверждения
  в его окне, метку вверху и кнопки её окна, «Выключить», «Включить наблюдение». **Не нажимать**:
  кнопку питания, «Замерить скорость», «Проверить запасные», «Обновить», «Опросить источники»,
  переключатели Tailscale, «Ядра», «Проверить сеть», выбор серверов, строки серверов и
  устройств, «Добавить», «Убрать», «Автовыбор».
- На телефоне через adb — только команды шагов 5.5 (экран, Wi-Fi, открыть адрес, снимок).
  Ничего не устанавливать и не удалять, настройки кроме Wi-Fi не трогать.
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, код XGW. Печатать `config.toml`, `panel.json`, рабочие конфиги
  Xray и sing-box, файлы в `/var/lib/xgw/freepool`, базу `/var/lib/xgw/state.db`, полный вывод
  `nft list table ip xgw_acct` и `sudo xgw traffic` (в нём имена устройств и подписок — в отчёт
  только строки помощника). Коммитить что-либо, кроме файла отчёта (§8). Снимки экрана (`*.png`)
  и `ts-url.txt` в git не добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, имена `*.ts.net`,
  токен из ссылки панели, MAC целиком, имена пользователей (→ `<user>`), внешние IP, адреса и
  домены подписок, IP, домены и ссылки серверов VPN, логины и пароли, строки журнала. Можно:
  адреса устройств в домашней сети (`192.168.…`), хвост MAC, как его печатает помощник
  (`…:11:22`), коды стран, названия источников, надписи панели без имён, счётчики, мегабайты,
  статусы, времена, строки помощника.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю новый учёт расхода трафика по устройствам и подпискам и ещё раз — перезагрузку в
режиме «весь дом» (в прошлый раз её опередил страховочный таймер, и она прошла уже в обычном
режиме). Нажатия в панели и осмотр экрана я делаю сам, в управляемом браузере. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. WAN и DHCP установка не трогает. Ядра останутся.
(2) Если наблюдение за бесплатными серверами выключено, я включу его и подожду 30 минут (оно
нужно для режима «весь дом»).
(3) Я сам открою панель в управляемом браузере и буду нажимать в ней: вкладки, кнопки периода
карточки «Трафик», «Весь дом через бесплатные» с подтверждением, метку вверху и «Вернуть режим
подписок», «Выключить» и «Включить наблюдение»; для проверки интернета открою example.com и
wikipedia.org.
(4) Для проверки учёта шлюз один раз скачает пробный файл 30 МБ (speed.cloudflare.com) — через
подписку, как обычный трафик. Если подписка с лимитом и сервер с множителем, это 30 МБ ×
множитель.
(5) Попрошу вас 2–3 минуты посмотреть любое видео на телефоне по домашнему Wi-Fi — чтобы учёт
увидел трафик устройства.
(6) Главное: перезагрузка машины в режиме «весь дом». Перед включением — страховочный таймер на
25 минут. Когда я попрошу, перезагрузите, пожалуйста, машину **сразу, в течение 10 минут** —
иначе таймер вернёт режим раньше и проверка снова не состоится. После загрузки нужно снова
запустить меня с этим ТЗ. После перезагрузки проверю, открывается ли панель с телефона через
Tailscale по мобильной сети: если телефон подключён к компьютеру по USB с разрешённой отладкой
(adb), сделаю это сам (выключу на телефоне Wi-Fi, открою панель, сниму экран, включу Wi-Fi
обратно), иначе попрошу вас.
(7) В конце верну наблюдение в то состояние, в каком оно было до проверки.
Проверка займёт около полутора часов. Можно согласиться не на все пункты.»

Против пункта 1 или 3 — **стоп**. Против 2 при выключенном наблюдении — §5 пропустить. Против 4 —
шаг 3.2 пропустить. Против 5 — шаг 3.3 без видео (только команды). Против 6 — §5 пропустить (в
отчёте: «перезагрузка не выполнялась»). Против 7 — §7 без изменения режима. В отчёте у
пропущенного — «не выполнялся». Если ответа нет — не начинать, спросить ещё раз.

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-usage" && chmod 700 "$HOME/xgw-usage" && cd "$HOME/xgw-usage" && cat > usagecheck.py <<'EOF'
"""XGW 0.2.0: учёт расхода трафика и перезагрузка во «всём доме» — помощник проверки. Только
читает: состояние XGW (/run/xgw), базу состояния (/var/lib/xgw/state.db — только чтение),
рабочий конфиг Xray, таблицу учёта nftables (nft -j list table ip xgw_acct) и вывод команд со
стандартного ввода — счётчики, мегабайты, итоги и да/нет; без имён серверов, устройств и
подписок, ссылок и ключей: подписки — по номерам, устройства — по адресу в LAN и хвосту MAC.
Время — секунды с 1970 (date +%s). Режимы: units, pool, route, mark, state, watch on|back,
events, applies, boot, acct, rows, devices, cli, diag, log."""
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
LIB = os.environ.get("USAGECHECK_LIB", "/opt/xgw/lib")
NAME = re.compile("«[^»]*»")
MODE_ON = "бесплатный пул: весь дом через бесплатные серверы"
MODE_BACK = "режим подписок возвращён"
BOOT_DROP = "весь дом снят после перезагрузки"
MARKS = {"on": MODE_ON, "back": MODE_BACK}
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


def arg(index, default):
    try:
        return float(sys.argv[index])
    except (IndexError, ValueError):
        return default


def mb(value):
    return f"{int(value or 0) / 1e6:.1f} МБ"


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


def usage_rows(paths, days):
    since = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
    try:
        conn = db(paths)
        rows = [dict(row) for row in conn.execute(
            "SELECT kind, key, SUM(up) AS up, SUM(down) AS down, SUM(billed) AS billed "
            "FROM usage WHERE day >= ? GROUP BY kind, key", (since,))]
        found = conn.execute("SELECT value FROM meta WHERE key = 'usage_labels'").fetchone()
        conn.close()
    except sqlite3.Error as exc:
        print(f"учёт в базе не читается: {type(exc).__name__}: {exc}")
        sys.exit(0)
    try:
        labels = json.loads(found["value"]) if found else {}
    except ValueError:
        labels = {}
    return since, rows, labels if isinstance(labels, dict) else {}


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
    whole = cfg.free_pool.mode == "on"
    print(f"режим пула: {cfg.free_pool.mode}; последнее правило → "
          f"{target(rules[-1]) if rules else 'правил нет'}; несущий канал (http-in, socks-in): "
          f"{'есть' if carrier else 'нет'}")
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
    mark, goal = MARKS.get(which, MODE_ON), GOALS.get(which, "on")
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
    last, samples, closed, reached = None, 0, 0, None
    while time.time() < pressed + WATCH:
        status = read_json(paths.status_file) or {}
        state = flow_state(status)
        samples += 1
        closed += "ЗАКРЫТО" in state
        if reached is None and (pool_of(status).get("mode") or "off") == goal:
            reached = time.time() - pressed
        if state != last:
            print(f"+{time.time() - pressed:4.0f} с: {state}", flush=True)
            last = state
        time.sleep(1)
    found = [(ts, detail) for ts, kind, detail in events_since(paths, pressed - 1)
             if kind == "freepool"]
    for ts, detail in found:
        print(f"событие +{ts - pressed:4.0f} с: {NAME.sub('«<сервер>»', detail)}")
    print(f"замеров: {samples}; из них «ЗАКРЫТО»: {closed}; режим {goal} в состоянии шлюза — "
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

    def count(*words):
        return sum(1 for _ts, detail in rows if all(word in detail for word in words))

    bad = sum(1 for _ts, detail in rows
              if "отклонён" in detail or "откат" in detail or "не поднялся" in detail)
    print(f"применений с {stamp(since)}: {len(rows)}; «режим подписок» с перезапуском Xray: "
          f"{count('бесплатный пул: режим подписок', 'с перезапуском')}; отложено до окна "
          f"перезапуска: {count('отложен')}; отказ или откат: {bad}")
elif mode == "boot":
    _cfg, paths = xgw()
    since, boot = arg(2, 0.0), arg(3, time.time())
    rows = events_since(paths, since)
    before = [(ts, detail) for ts, kind, detail in rows
              if kind == "freepool" and ts < boot and (MODE_ON in detail or MODE_BACK in detail)]
    last = before[-1] if before else None
    was = ("on" if MODE_ON in last[1] else "observe") if last else "неизвестно"
    dropped = [ts for ts, kind, detail in rows
               if kind == "freepool" and ts >= boot and BOOT_DROP in detail]
    rebuilt = [ts for ts, kind, detail in rows
               if kind == "apply" and ts >= boot and "бесплатный пул: режим подписок" in detail
               and "с перезапуском" in detail]
    print(f"режим перед перезагрузкой (по событиям): {was}"
          + (f" (последняя смена {stamp(last[0])})" if last else ""))
    print(f"загрузка {stamp(boot)}; событие «весь дом снят после перезагрузки»: "
          + (f"+{dropped[0] - boot:.0f} с" if dropped else "нет")
          + "; срочная сборка «режим подписок» с перезапуском Xray: "
          + (f"+{rebuilt[0] - boot:.0f} с" if rebuilt else "нет"))
elif mode == "acct":
    code, out = run(["nft", "-j", "list", "table", "ip", "xgw_acct"])
    if code != 0:
        print("таблица учёта ip xgw_acct: нет")
        sys.exit(0)
    sets, counters, chains, shape = {}, {}, [], "—"
    for item in json.loads(out).get("nftables") or []:
        if "set" in item:
            elems = [elem.get("elem") for elem in item["set"].get("elem") or []
                     if isinstance(elem, dict) and isinstance(elem.get("elem"), dict)]
            with_counter = [body for body in elems if isinstance(body.get("counter"), dict)]
            if elems and shape == "—":
                shape = "+".join(sorted(elems[0]))
            sets[item["set"]["name"]] = (len(item["set"].get("elem") or []), len(with_counter),
                                         sum(int(body["counter"].get("bytes") or 0)
                                             for body in with_counter))
        elif "counter" in item:
            counters[item["counter"].get("name")] = int(item["counter"].get("bytes") or 0)
        elif "chain" in item:
            chain = item["chain"]
            chains.append(f"{chain.get('name')} ({chain.get('hook')} {chain.get('prio')})")
    parts = [f"{name}: элементов {total}, со счётчиком {counted}, {mb(size)}"
             for name, (total, counted, size) in sorted(sets.items())]
    parts += [f"{name}: {mb(size)}" for name, size in sorted(counters.items())]
    print(f"таблица учёта ip xgw_acct: есть; цепочки: {', '.join(chains) or 'нет'}")
    print("; ".join(parts) or "наборов и счётчиков нет")
    print(f"поля элемента набора: {shape}")
elif mode == "rows":
    _cfg, paths = xgw()
    days = int(arg(2, 1))
    since, rows, _labels = usage_rows(paths, days)
    kinds = {}
    for row in rows:
        kinds.setdefault(row["kind"], []).append(row)
    devices = kinds.get("device", [])
    subs = sorted(kinds.get("sub", []), key=lambda row: -(row["up"] + row["down"]))
    print(f"учёт с {since}: строк {len(rows)}; устройств {len(devices)}: ↓ "
          f"{mb(sum(row['down'] for row in devices))}, ↑ {mb(sum(row['up'] for row in devices))}")
    for index, row in enumerate(subs, 1):
        print(f"подписка #{index}: ↓ {mb(row['down'])}, ↑ {mb(row['up'])}, учтено "
              f"{mb(row['billed'])}")
    for kind, label in (("pool", "бесплатные серверы"), ("direct", "напрямую"), ("wan", "WAN")):
        for row in kinds.get(kind, []):
            print(f"{label}: ↓ {mb(row['down'])}, ↑ {mb(row['up'])}")
    print(f"всего по всем строкам: {mb(sum(row['up'] + row['down'] for row in rows))}")
elif mode == "devices":
    _cfg, paths = xgw()
    _since, rows, labels = usage_rows(paths, int(arg(2, 1)))
    devices = sorted((row for row in rows if row["kind"] == "device"),
                     key=lambda row: -(row["up"] + row["down"]))
    for row in devices:
        key = str(row["key"])
        label = labels.get(key) if isinstance(labels.get(key), dict) else {}
        tail = "без MAC" if key.startswith("ip:") else f"MAC …{key[-5:]}"
        print(f"{label.get('ip') or key.removeprefix('ip:')} ({tail}, имя: "
              f"{'есть' if label.get('name') else 'нет'}): ↓ {mb(row['down'])}, ↑ {mb(row['up'])}")
    if not devices:
        print("устройств в учёте нет")
elif mode == "cli":
    lines = sys.stdin.read().splitlines()
    head = lines[0] if lines else ""
    section, counts = "", {"Устройства:": 0, "Подписки и выходы:": 0}
    for line in lines[1:]:
        if line in counts:
            section = line
        elif line.startswith("  ") and section:
            counts[section] += 1
        elif not line:
            section = ""
    billed = any("учтено подпиской" in line for line in lines)
    wan = any(line.startswith("Всего через провайдера") for line in lines)
    print(f"первая строка: {head}; строк устройств: {counts['Устройства:']}; строк подписок и "
          f"выходов: {counts['Подписки и выходы:']}; «учтено подпиской»: "
          f"{'есть' if billed else 'нет'}; WAN: {'есть' if wan else 'нет'}")
elif mode == "diag":
    for line in sys.stdin.read().splitlines():
        found = re.match(r"(\S+)\s+(Tailscale: [^:]+):", line)
        if found:
            print(f"{found.group(1)} {found.group(2)}")
        elif re.match(r"\S+\s+(Весь дом через бесплатный пул|Бесплатный пул):", line) or \
                line.startswith("Итог:"):
            print(line)
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, word in (
        ("учёт трафика устройств: предупреждений", "учёт трафика устройств:"),
        ("учёт трафика: шаг не выполнен", "учёт трафика: шаг не выполнен"),
        ("весь дом снят после перезагрузки", BOOT_DROP),
        ("«режим подписок»: применено с перезапуском Xray",
         "бесплатный пул: режим подписок: применено с перезапуском Xray"),
        ("нужен перезапуск Xray — отложен", "нужен перезапуск Xray — отложен"),
        ("у всего дома закрыто", "у всего дома закрыто"),
        ("откат на last-good", "last-good"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | pool | route | mark | state | watch on|back | events | applies | boot "
          "| acct | rows | devices | cli | diag | log")
EOF
python3 -c "import hashlib;d=open('usagecheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `338932ee85a79ae2`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки:

```bash
cd "$HOME/xgw-usage" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units pool route mark state acct; do sudo python3 -I usagecheck.py $m; done | tee -a before.txt
```

Ожидается:
- `Состояние: …` (обычно `HEALTHY`), `Перехват: включён …`, Xray 26.10.29, sing-box 1.14.4;
- первая строка `xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать,
  какая** (от неё зависят шаги 4.1 и §7);
- четыре службы `active`; `route` — «совпадает с режимом: да» (записать обе строки);
- `acct` — «таблица учёта ip xgw_acct: нет» (её ставит новый код).

Если не так: первая строка `xgw pool` — «весь дом через бесплатные серверы» — выполнить
`sudo xgw pool mode observe`, подождать минуту и повторить шаг.

Шаг 1.4. Есть ли телефон по adb (только если заказчик согласился на пункт 6):

```bash
if command -v adb >/dev/null; then adb devices | sed 1d | awk 'NF{print $2}' | sort | uniq -c; echo "adb: есть"; else echo "adb: нет"; fi
```

Ожидается одно из:
- `1 device` и «adb: есть» — телефон доступен: в шаге 5.5 телефонную часть делаешь сам
  (вариант А);
- `1 unauthorized` — **попроси заказчика** (дословно): «На телефоне появился запрос «Разрешить
  отладку по USB?» — разрешите, пожалуйста.» — и повтори шаг;
- пусто или «adb: нет» — телефонную часть делает заказчик (вариант Б). Ничего не устанавливать.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q '^TABLE = "xgw_acct"' src/xgw/usage.py && grep -q 'def _usage_step' src/xgw/daemon.py && grep -q 'CREATE TABLE IF NOT EXISTS usage' src/xgw/store.py && grep -q '"traffic": _cmd_traffic' src/xgw/cli.py && grep -q 'id="usage-card"' src/xgw/ui/index.html && grep -q 'установка пересоберёт конфиг под режим' src/xgw/diag.py && echo "правка в коде: есть"; cd "$HOME/xgw-usage"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-usage/install-time.txt" && date +%s > "$HOME/xgw-usage/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-usage/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-usage/install.txt"; cd "$HOME/xgw-usage"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: «Установка не начата» — записать строки с «✗» дословно (без имён) и **стоп**,
сообщить заказчику (ничего не исправлять). Код не 0 по другой причине — **стоп**, сохранить
вывод, сообщить заказчику.

Шаг 2.3. Через 3 минуты после установки:

```bash
sleep 180; cd "$HOME/xgw-usage" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee after-install.txt; for m in units route mark state acct; do sudo python3 -I usagecheck.py $m; done | tee -a after-install.txt; sudo python3 -I usagecheck.py rows 1 | tee -a after-install.txt; sudo xgw diag 2>&1 | sudo python3 -I usagecheck.py diag | tee diag-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I usagecheck.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4; строки «Ожидает окна
  перезапуска» нет; четыре службы `active`; `route` — «совпадает с режимом: да; … ждёт окна
  перезапуска: нет»;
- `acct` — **«таблица учёта ip xgw_acct: есть; цепочки: pre (prerouting -300), post
  (postrouting 300)»**; вторая строка — «dev_down: элементов N, со счётчиком N, … МБ; dev_up:
  элементов N, со счётчиком N, … МБ; wan_in: … МБ; wan_out: … МБ» (N — сколько устройств сети
  выходили в интернет; «со счётчиком» = «элементов»); третья — «поля элемента набора: …»
  (записать дословно, в ней должно быть слово `counter`);
- `rows` — «учёт с <сегодня>: строк …» (строк больше 0: хотя бы подписка, WAN и напрямую);
- `diag` — строки «FAIL Весь дом через бесплатный пул» нет; «Итог: …» — записать;
- журнал: «учёт трафика устройств: предупреждений: 0», «учёт трафика: шаг не выполнен: 0»,
  «Traceback: 0».

Если не так:
- `acct` — «таблица учёта ip xgw_acct: нет», а в журнале «учёт трафика устройств:
  предупреждений» больше 0 — **дефект «таблица учёта не встала»**: выполни
  `sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -o 'учёт трафика устройств: .*' | head -3`
  и запиши строки дословно (в них — ответ nft, имён там нет), продолжай;
- «со счётчиком 0» при «элементов» больше 0 — **дефект «счётчики элементов»**, продолжай;
- `rows` — «учёт в базе не читается» — **дефект**, продолжай;
- не `HEALTHY` — подожди 2 минуты и повтори; снова нет — запиши и продолжай.

## 3. Учёт трафика

Шаг 3.1. Пять минут работы, затем отсчёт «до»:

```bash
sleep 300; cd "$HOME/xgw-usage" && date '+%T' | tee usage-1.txt; for m in acct rows devices; do sudo python3 -I usagecheck.py $m; done | tee -a usage-1.txt
```

Ожидается: `rows` — «устройств N» (N больше 0, если в сети есть активные устройства), строки
«подписка #1: …», «напрямую: …», «WAN: …»; «всего по всем строкам» — больше 0; `devices` — по
строке на устройство «192.168.… (MAC …xx:yy, имя: есть/нет): ↓ … МБ, ↑ … МБ». Записать всё.

Если не так: «устройств 0» при «dev_up: элементов» больше 0 в `acct` — **дефект «устройства не
пишутся»**, продолжай.

Шаг 3.2. Пробная загрузка 30 МБ самим шлюзом (пункт 4 согласия) — она идёт через подписку и
должна прибавиться у подписки и в WAN, но **не** у устройств:

```bash
cd "$HOME/xgw-usage" && sudo python3 -I usagecheck.py rows 1 | tee dl-before.txt; curl -s -o /dev/null -w 'загружено: %{size_download} байт за %{time_total} с, код %{http_code}\n' 'https://speed.cloudflare.com/__down?bytes=30000000' | tee dl.txt; sleep 130; sudo python3 -I usagecheck.py rows 1 | tee dl-after.txt
```

Ожидается: «загружено: 30000000 байт за … с, код 200»; в `dl-after.txt` по сравнению с
`dl-before.txt`:
- у одной из подписок «↓» больше примерно на 30 МБ (от 28 до 40 МБ — с проверками серверов);
  «учтено» у неё выросло на 30 МБ × множитель сервера (у сервера без множителя — так же на ~30);
- «WAN: ↓» больше не меньше чем на 30 МБ;
- «устройств … ↓» выросло меньше чем на 30 МБ (загрузка шла с самого шлюза).

Запиши три разницы: подписка ↓, WAN ↓, устройства ↓ (в МБ).

Если не так: код не 200 или «загружено» меньше 30000000 — запиши и пропусти сравнение («загрузка
не удалась»). Ни одна подписка не выросла на 28+ МБ — **дефект «подписка не считается»**. WAN
не вырос — **дефект «WAN не считается»**. Устройства выросли на 30+ МБ — **дефект «шлюз
посчитан как устройство»**.

Шаг 3.3. Трафик устройства (пункт 5 согласия). **Скажи заказчику** (дословно): «Посмотрите,
пожалуйста, 2–3 минуты любое видео на телефоне по домашнему Wi-Fi (не по мобильной сети) и
напишите, когда закончите.» Сразу затем:

```bash
cd "$HOME/xgw-usage" && sudo python3 -I usagecheck.py devices 1 | tee video-before.txt
```

Когда заказчик ответил — подожди 70 секунд и:

```bash
sleep 70; cd "$HOME/xgw-usage" && sudo python3 -I usagecheck.py devices 1 | tee video-after.txt
```

Ожидается: у одного устройства (телефона) «↓» выросло заметно — на десятки МБ или больше;
записать его адрес `192.168.…`, хвост MAC и разницу ↓ и ↑ в МБ.

Если не так: ни одно устройство не выросло больше чем на 5 МБ — спроси заказчика (дословно):
«Телефон был подключён к домашнему Wi-Fi?» и запиши ответ; если да — **дефект «трафик
устройства не считается»**.

Шаг 3.4. Карточка «Трафик» в панели. Ссылка входа (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком, окно не меньше 1280×800,
подожди 5 секунд. Прокрути страницу вниз до карточки **«Трафик»** (под «Устройствами»),
подожди 5 секунд, сделай снимок. Выполни **J6**.

Ожидается:
- на снимке — заголовок «Трафик», справа кнопки «Сегодня» (выделена), «7 дней», «30 дней»;
  серый текст начинается с «Сегодня: ↓ получено, ↑ отправлено.»; список «Устройства» — строки с
  именем (или «Без имени»), серой меткой `192.168.…`, «↓ … · ↑ …» и полосой; список «Подписки и
  выходы» — строки подписок с меткой «подписка», «Напрямую (мимо VPN)», «Всего через провайдера
  (WAN)», «Шлюз и служебное» (и «Бесплатные серверы», если через них шёл трафик);
- J6 — `Сегодня | <устройств> | <строк подписок и выходов> | true,false,false`; числа — как
  в шаге 3.1 по смыслу (устройств столько же, сколько строк в `devices`).

**Действие:** нажми **«7 дней»**, подожди 3 секунды, снимок, **J6**. Ожидается `За 7 дней, с
ДД.ММ.ГГГГ | … | … | false,true,false`. Нажми **«30 дней»**, снимок, **J6** — `За 30 дней, с … |
… | … | false,false,true`. Нажми **«Сегодня»**, **J6** — снова `Сегодня | … | true,false,false`.

**Действие:** обнови страницу (F5), подожди 5 секунд, прокрути до «Трафика», **J6** — период
«Сегодня» сохранился (последний выбранный).

Если не так: карточки нет — обнови Ctrl+F5 и повтори; снова нет — **дефект**. Текст «Данных пока
нет» в обоих списках при `rows` с данными — подожди минуту и повтори; снова так — **дефект
«карточка не получает учёт»**. Кнопки не переключают период — **дефект**.

Шаг 3.5. Команда `xgw traffic`:

```bash
cd "$HOME/xgw-usage" && sudo xgw traffic 2>&1 | sudo python3 -I usagecheck.py cli | tee cli.txt; sudo xgw traffic --days 7 2>&1 | sudo python3 -I usagecheck.py cli | tee -a cli.txt; xgw traffic 2>&1 | head -1 | tee -a cli.txt
```

Ожидается:
- первая строка: «первая строка: Трафик сегодня: ↓ получено, ↑ отправлено.; строк устройств: N;
  строк подписок и выходов: M; «учтено подпиской»: есть/нет; WAN: есть» (N — как в шаге 3.1;
  «учтено подпиской» — «есть», только если подписка сообщает квоту);
- вторая — «первая строка: Трафик за 7 дн. (с ГГГГ-ММ-ДД): …»;
- третья (без sudo) — строка «ошибка: …» (без прав на базу или конфиг) или первая строка сводки —
  записать дословно; это не дефект.

Шаг 3.6. Значки и полоса «Выбран вручную». **Действие:** прокрути страницу вверх, нажми вкладку
**«Подписки»**, снимок, выполни **J2** и **J3**.

Ожидается: J2 — `0`; J3 — «полосы нет» (сервер вручную не выбран) или «полоса есть, значков: 0».

Если не так: J2 больше 0 или «значков» больше 0 — **дефект** (где именно — по снимку; имён в
отчёт не писать).

## 4. Наблюдение

Шаг 4.1. Только если в шаге 1.3 наблюдение было **выключено** и заказчик согласился на пункты 2
и 6 (иначе — пропустить, записать «уже было включено» или «не выполнялся»):

```bash
cd "$HOME/xgw-usage" && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; sleep 1800; sudo python3 -I usagecheck.py pool | tee -a mode-on.txt
```

(Если терминал обрывает длинные команды — после первой строки выполни `sleep 110` 17 раз, затем
`sudo python3 -I usagecheck.py pool`.)

Ожидается: «Наблюдение за бесплатным пулом включено: …»; через 30 минут `pool` — «пригодно»
больше 0.

Если не так: «пригодно 0» — подожди ещё 30 минут и повтори `pool`; снова 0 — §5 пропустить
(«нет допущенных серверов»), перейти к §6.

## 5. Перезагрузка во «всём доме» (пункт 6 согласия)

Шаг 5.1. **Спроси заказчика** (дословно): «Сейчас включу «весь дом» и попрошу перезагрузить
машину. Сможете перезагрузить её в ближайшие 10 минут, как только я попрошу?» Ответ «нет» —
подожди, пока заказчик будет готов; без готовности §5 не начинать.

Затем страховочный таймер — **до** включения:

```bash
cd "$HOME/xgw-usage" && sudo systemd-run --on-active=25min --unit=xgw-usage-guard /usr/local/bin/xgw pool mode observe 2>&1 | tee guard.txt; systemctl list-timers --all --no-pager xgw-usage-guard.timer | head -3 | tee -a guard.txt
```

Ожидается: «Running timer as unit: xgw-usage-guard.timer» и строка таймера через ~25 минут.

Если не так: таймера нет — **стоп** для §5 (её пропустить, перейти к §6).

Шаг 5.2. Включение (нажимаешь ты):
1. В браузере — вкладка «Бесплатные серверы». Нажми **«Весь дом через бесплатные»**.
2. Снимок; **J4** — `true | Пустить весь дом через бесплатные серверы? | Весь дом через
   бесплатные`.
3. Нажми в окне **«Весь дом через бесплатные»**.
4. **Сразу** (в течение 30 секунд) выполни:

```bash
cd "$HOME/xgw-usage" && date +%s > t-on.txt && sudo python3 -I usagecheck.py watch on | tee watch-on.txt; for m in pool route mark acct; do sudo python3 -I usagecheck.py $m; done | tee house.txt; date '+%F %T' | tee reboot-time.txt
```

Ожидается (около 3 минут): «нажатие: …»; «режим on: через сервер (XX), живых … из …»;
«ЗАКРЫТО: 0»; «режим on в состоянии шлюза — с +N с»; `route` — «последнее правило → балансировщик
pool; несущий канал: есть», «совпадает с режимом: да»; `mark` — «есть»; `acct` — таблица учёта
на месте (перезагрузка правил перехвата её не убрала).

Если не так: «через сервер» не появилось за три минуты — раздел «Если что-то пошло не так», §5
пропустить.

Шаг 5.3. **Сразу скажи заказчику** (дословно): «Перезагрузите, пожалуйста, компьютер прямо
сейчас. После загрузки войдите в свой сеанс, снова запустите меня с этим ТЗ (файл
`$HOME/xgw-usage/plan.md`) и напишите «продолжи с шага 5.4».»

Дальше ничего не делай, пока заказчик не напишет «продолжи с шага 5.4».

Шаг 5.4. После перезагрузки. Подожди 3 минуты после входа заказчика:

```bash
sleep 180; cd "$HOME/xgw-usage" && date -d "$(uptime -s)" +%s > t-boot.txt && echo "загрузка: $(uptime -s)" | tee after-reboot.txt; sudo python3 -I usagecheck.py boot "$(( $(cat t-on.txt) - 120 ))" "$(cat t-boot.txt)" | tee boot.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Ожидает окна' | tee -a after-reboot.txt; sudo xgw pool 2>&1 | head -1 | tee -a after-reboot.txt; for m in units pool route mark state acct; do sudo python3 -I usagecheck.py $m; done | tee -a after-reboot.txt; sudo python3 -I usagecheck.py applies "$(cat t-boot.txt)" | tee -a after-reboot.txt; sudo xgw diag 2>&1 | sudo python3 -I usagecheck.py diag | tee diag-reboot.txt; sudo journalctl -u xgw -b --no-pager | sudo python3 -I usagecheck.py log | tee log-reboot.txt; systemctl list-timers --all --no-pager 'xgw-usage-*' | tail -1 | tee -a after-reboot.txt
```

**Сначала посмотри на первую строку `boot.txt`:**
- «режим перед перезагрузкой (по событиям): **on**» — проверка состоялась, сверяй ожидания ниже;
- «режим перед перезагрузкой (по событиям): **observe** (последняя смена ЧЧ:ММ:СС)» —
  перезагрузку опередил страховочный таймер: проверка **не состоялась**. Запиши это и **один раз**
  повтори §5 с шага 5.1 (новый таймер, новое включение, сразу перезагрузка). Снова observe —
  запиши «перезагрузка во «всём доме» не выполнена: таймер» и переходи к §6;
- «режим перед перезагрузкой (по событиям): **неизвестно**» — запиши это дословно и сверяй
  ожидания ниже, как при «on»; в отчёте пометь «режим перед перезагрузкой не установлен».

Ожидается при «on» (это **главный критерий**):
- вторая строка `boot.txt`: «событие «весь дом снят после перезагрузки»: +N с; срочная сборка
  «режим подписок» с перезапуском Xray: +M с» — **оба есть**, M — не больше 300 (записать N и M);
- строки «Ожидает окна перезапуска» нет; первая строка `xgw pool` — «… наблюдение (трафик через
  подписку) …»;
- `pool` — «режим observe: через пул никто»; `route` — «последнее правило → балансировщик auto;
  несущий канал: нет», **«рабочий конфиг совпадает с режимом: да; новый конфиг ждёт окна
  перезапуска: нет»**; `mark` — «нет»; `state` — «совпадают: да»;
- `acct` — таблица учёта снова есть (её поставил демон после загрузки);
- `applies` — «отказ или откат: 0»;
- `diag` — строки «FAIL Весь дом через бесплатный пул» нет;
- журнал загрузки: «весь дом снят после перезагрузки: 1», ««режим подписок»: применено с
  перезапуском Xray: 1», «у всего дома закрыто: 0», «Traceback: 0»;
- таймеров `xgw-usage-*` нет («0 timers listed»).

Если не так (при «on»): события снятия нет — **дефект «перезагрузка не сняла режим»**, сразу
раздел «Если что-то пошло не так». `route` «совпадает: НЕТ» — подожди 5 минут и повтори команду
без `sleep`; снова НЕТ — **дефект «сверка конфига с режимом не сработала»**: запиши строки,
выполни `sudo xgw apply --now`, через минуту `sudo python3 -I usagecheck.py route`, продолжай.
Срочной сборки нет, а `route` «да» — запиши «конфиг совпал без срочной сборки» (не дефект,
наблюдение).

Шаг 5.5. Доступ после перезагрузки.

Панель на машине: открой заново ссылку из `sudo xgw panel` (как в шаге 3.4), снимок, **J1** —
`BUTTON | <состояние режима подписок> | true | ` (не «Через бесплатные серверы»).

Телефон, **вариант А** (adb). Выполни **J5**; если ответ — адрес `https://…` (не «нет»),
выполни команду, **подставив его вместо `<АДРЕС>`** (в одинарных кавычках; это единственная
подстановка в ТЗ; адрес в отчёт не писать):

```bash
cd "$HOME/xgw-usage" && printf '%s\n' '<АДРЕС>' > ts-url.txt && chmod 600 ts-url.txt && adb shell input keyevent KEYCODE_WAKEUP && adb shell cmd wifi set-wifi-enabled disabled && sleep 15 && adb shell am start -a android.intent.action.VIEW -d "$(cat ts-url.txt)" >/dev/null && sleep 30 && adb exec-out screencap -p > phone-boot.png; adb shell cmd wifi set-wifi-enabled enabled; ls -l phone-boot.png | awk '{print "снимок телефона, байт:", $5}'
```

Посмотри на снимок `$HOME/xgw-usage/phone-boot.png`: страница XGW (панель или страница входа XGW)
— «открылась»; ошибка браузера («Не удаётся получить доступ к сайту», «ERR_…», «This site can't be
reached») — «не открылась»; экран блокировки — попроси заказчика разблокировать телефон и повтори.

Телефон, **вариант Б** — **спроси заказчика** (дословно): «Выключите, пожалуйста, Wi-Fi на
телефоне и откройте панель шлюза через Tailscale по мобильной сети. Она открылась? Потом включите
Wi-Fi обратно.»

Ожидается: «открылась».

Если не так: не открылась — повтори через минуту; снова нет — **дефект «удалённый доступ после
перезагрузки»**, запиши, продолжай (режим уже подписок).

Шаг 5.6. Учёт пережил перезагрузку:

```bash
cd "$HOME/xgw-usage" && sleep 70; sudo python3 -I usagecheck.py rows 1 | tee usage-boot.txt
```

Ожидается: «всего по всем строкам» — **не меньше**, чем в `dl-after.txt` (записанное до
перезагрузки осталось в базе), «устройств» — не меньше, чем в шаге 3.1.

Если не так: меньше — **дефект «учёт потерян при перезагрузке»**.

## 6. Секреты

```bash
cd "$HOME/xgw-usage" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt
```

Ожидается: `0`. Если больше — **дефект** (строки журнала в отчёт не копировать).

## 7. Режим как до проверки и итог

Шаг 7.1. Если в шаге 1.3 наблюдение было **выключено**, а сейчас включено — **действие в
браузере:** вкладка «Бесплатные серверы» → **«Выключить»**, снимок (кнопка сменилась на «Включить
наблюдение»). Было включено — ничего не менять, записать «оставлено включённым».

Шаг 7.2. Итог:

```bash
sleep 60; cd "$HOME/xgw-usage" && date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units pool route mark state acct; do sudo python3 -I usagecheck.py $m; done | tee -a final.txt; sudo python3 -I usagecheck.py rows 1 | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I usagecheck.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.29, sing-box 1.14.4, строки «Ожидает окна
перезапуска» нет; четыре службы `active`; режим — как был до проверки; `route` — «совпадает с
режимом: да; … ждёт окна перезапуска: нет»; `mark` — «нет»; таблица учёта есть; журнал: «учёт
трафика: шаг не выполнен: 0», «у всего дома закрыто: 0», «откат на last-good: 0», «Traceback: 0».

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- В режиме «весь дом» пропал интернет или доступ, или заказчик не отвечает **2 минуты** —
  **сразу**: `sudo xgw pool mode observe`, затем `sudo systemctl stop xgw-usage-guard.timer`
  (ошибка «not loaded» — норма). Записать время и строки `sudo python3 -I usagecheck.py pool` и
  `sudo python3 -I usagecheck.py route`. Дальше — §6, §7 и отчёт. «Весь дом» больше не включать.
- Сработал страховочный таймер до перезагрузки — это видно в шаге 5.4 («observe» в `boot.txt`):
  там сказано, что делать.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.
- Браузер не открывает панель или кнопки не нажимаются — снимок, сообщить заказчику и попросить
  нажать то же самое вручную; в отчёте пометить «нажато заказчиком».
- adb прервался до включения Wi-Fi — выполнить `adb shell cmd wifi set-wifi-enabled enabled`, а
  без adb — попросить заказчика включить Wi-Fi на телефоне.

## 8. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-usage-<ДАТА>.md` в клоне (`<ДАТА>` — дата начала
проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, учёт трафика и перезагрузка во «всём доме»» и
`git push` в `freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и
подписок, MAC целиком, адресов (кроме `192.168.…`), доменов, токена и строк журнала. Шаблон
(заполни каждую ячейку; пропущенное — «не выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — учёт расхода трафика и перезагрузка во «всём доме»

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
usagecheck.py: <сумма>. Наблюдение до проверки: <…>. Ядра: Xray <…>, sing-box <…>.
Телефон: <adb / вручную заказчиком / не проверялся>. Исполнитель: <модель>; нажатия и снимки —
управляемым браузером <да/частично>.

## Итог
| Таблица учёта: есть / поля элемента / со счётчиком = элементов | Загрузка 30 МБ: подписка ↓ / WAN ↓ / устройства ↓, МБ | Видео: устройство ↓, МБ | Карточка «Трафик»: периоды / сохранение периода | `xgw traffic` | Значки / полоса «Выбран вручную» |
|---|---|---|---|---|---|
| <да / … / да> | <+30 / +31 / +0.2> | <+…> | <да / да> | <да> | <0 / полосы нет> |

| Перезагрузка: режим перед ней (по событиям) | Снятие режима / срочная сборка, с | После загрузки: конфиг совпадает / ждёт окна | Панель с телефона после загрузки | Учёт после перезагрузки сохранился |
|---|---|---|---|---|
| <on> | <+N / +M> | <да / нет> | <да> | <да> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до | — | … |
| 1.4 adb | … | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 учёт «до» | … | … |
| 3.2 загрузка 30 МБ | … | … |
| 3.3 видео на телефоне | … | … |
| 3.4 карточка «Трафик» | … | … |
| 3.5 `xgw traffic` | … | … |
| 3.6 значки, полоса | … | … |
| 4.1 наблюдение | … | … |
| 5.1 страховка | … | … |
| 5.2 включение | … | … |
| 5.4 после перезагрузки | … | … |
| 5.5 доступ | … | … |
| 5.6 учёт после перезагрузки | … | … |
| 6 секреты | … | … |
| 7 итог | … | … |

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-usage/…); результаты J1–J6; что видно на
  снимках экрана и телефона словами; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
