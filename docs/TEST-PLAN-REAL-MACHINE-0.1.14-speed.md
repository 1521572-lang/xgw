# Программа испытаний XGW на реальной машине: скорость в строках серверов (0.1.14, c71085a и ca51474)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Все выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§10).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, Docker, роутер HUAWEI AX2 за шлюзом. Стоит XGW
**0.1.14** (код `245add2` или новее) в боевом режиме: от него работает интернет всего дома.

Номер версии не меняется: и после обновления `xgw --version` пишет `xgw 0.1.14`. Новый код
узнаётся по коммитам `c71085a` и `ca51474` (шаг 2.1) и по строкам «Сколько качает замер» и
«Замеры при ручном выборе (установленный код): идут» (шаг 3).

Что нового (коммиты `e68e687`, `c71085a` и `ca51474` после 0.1.14). Заказчик: «скорость
серверов замеряется, но результаты замера не отображаются в строках данных о сервере».

- Строка сервера в панели — в две строки: сверху имя с метками, **справа — скорость** по
  последнему замеру («14 Мбит/с», жирно) **и задержка** («200 мс»); снизу — состояние и кнопки.
  Под именем — время замера: «в работе · замер скорости 22:03». В узком окне (уже 600 точек,
  как на телефоне) скорость стоит **над** задержкой, кнопки уходят третьей строкой. Раньше
  скорость была только серой подписью под именем.
- **Запасной**, которого замерили, пока он был в работе, показывает этот замер (результаты
  хранятся неделю): скорость справа бледнее, под именем «… · замер скорости 22:03, когда был в
  работе». Запасные по-прежнему не замеряются.
- **Лимитированные** серверы (подписка с лимитом трафика, множитель в имени: x1, x2, x10)
  теперь замеряются **меньшей загрузкой**: квоты на один замер уходит не больше 10 МБ. x1
  качает 10 МБ, x2 — 5 МБ, x10 — 1 МБ; меньше 1 МБ загрузка не бывает. Раньше они не
  замерялись вовсе: когда в работе только они (как на этой машине), скорости не было ни у
  одного сервера, и основной выбирался по задержке. Теперь основной выбирается **по скорости**.
- Серверы **x100** и дороже (серверы для LTE) не замеряются; у такого сервера в работе под
  именем — «скорость серверов x100 не замеряется».
- Строка о трафике проверок (`xgw status`, `xgw diag`, панель) включает замеры скорости и у
  лимитированных серверов, а расход квоты подписки считает их с множителями (замер x10 по 1 МБ —
  10 МБ квоты).
- **Замеры идут и при ручном выборе** (`ca51474`). Раньше, пока сервер выбран вручную (кнопка
  «Выбрать» в панели, `xgw pin`), шлюз скорость **не замерял вовсе** — строки так и оставались
  без скорости. Теперь замеры идут, как без выбора: раз в 6 ч, лимитированные — меньшей
  загрузкой, x100 — никогда. Основной при выборе по-прежнему не выбирается; когда выбор снимут,
  шлюз сразу выбирает основной по этим замерам. Панель при выборе пишет «Замеры скорости идут и
  при ручном выборе: раз в 6 ч, …».

**Важно.** В конце испытаний 0.1.13 на этой машине стоял бессрочный ручной выбор. До замеров
его **не снимают**: шаг 4.1 как раз проверяет, что замеры идут и при нём. После замеров выбор
снимают (шаг 4.2) — проверить, что основной сразу выбран по замерам, и строки панели с
основным, — а в конце возвращают (шаг 7).

Цели:

1. Поставить новый код (шаг 2), проверить службы и установленный код (шаг 3).
2. Дождаться замеров серверов в работе — если стоит ручной выбор, то при нём (шаг 4.1); снять
   выбор и убедиться, что основной сразу выбран по замерам (шаг 4.2).
3. Проверить замеры (шаг 5): лимитированные качают свой предел (x1 — 10 МБ, x2 — 5 МБ, x10 —
   1 МБ), x100 не замеряются, основной выбран по скорости (`basis = speed`), бюджет трафика и
   расход квоты включают замеры.
4. Проверить строки панели: данные (шаг 6.1), запасной с последним замером (6.2–6.3), вид —
   глазами заказчика, в том числе в узком окне (6.4).
5. Вернуть всё, как было (шаги 6.5, 7, 8).

## 0. Запрещено

- `xgw net down`, `xgw uninstall`, `reboot`, `install.sh --force` — **никогда**.
- `flush ruleset`, ручные команды `nft`, `ip`, `iptables`, `sysctl -w` — **никогда**.
- Запускать `sing-box` и `xray` вручную, править их файлы, останавливать или перезапускать
  `xgw-xray`, `xgw-singbox` и демон `xgw` (установка в шаге 2.2 перезапускает демон сама).
- Править `/etc/xgw/config.toml` и `/etc/xgw/panel.json` (в этой программе они руками не
  меняются вовсе).
- Нажимать «Замерить скорость» в панели, `/speed` в боте: каждый раунд тратит квоту
  лимитированной подписки. Шлюз замерит сам сразу после установки.
- Выбирать сервер вручную («Выбрать», `xgw pin`), снимать выбор и менять приоритеты — только
  командами шагов 4.2, 6.2, 6.5 и 7. **Никогда** не выбирать вручную сервер x100.
- Открывать или скачивать адреса подписок (curl, браузер), копировать ссылки серверов.
- Править код XGW.
- Коммитить что-либо, кроме отчёта (§10). Файлы из `~/xgw-speed-test` в Git **не класть**.
- Писать в отчёт: адреса подписок, UUID, пароли, ключи, токены (и токен панели, и файл
  `panel.jar`), IP и домены серверов, свой внешний IP. Серверы называй по имени или тегу
  (`proxy-tr-76a6`).

Аварийный выход, если пропал интернет: `sudo xgw disable` (интернет пойдёт напрямую), затем
сообщить заказчику.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика:** «Обновлю XGW: панель будет показывать скорость серверов рядом с
задержкой, а лимитированные серверы будут замеряться малой загрузкой. (1) Демон XGW при
установке перезапустится сам: интернет не пропадёт, панель и бот секунд на десять станут
недоступны. (2) Сразу после установки шлюз замерит скорость серверов в работе: у
лимитированной подписки это до 10 МБ квоты на сервер за раз (у x10 — загрузка 1 МБ), дальше —
так же раз в 6 часов. (3) Если сейчас сервер выбран вручную, выбор пока останется — шлюз
теперь замеряет скорость и при нём; после замеров я сниму выбор примерно на полчаса: трафик
пойдёт через самый быстрый сервер в работе; в конце верну выбор. (4) Может понадобиться
минут на десять понизить приоритет одного сервера в работе, чтобы он стал запасным, — потом
верну. (5) В конце попрошу вас посмотреть на панель — пара минут. Можно?» Дождись ответа.
Записать в отчёт, на что заказчик согласился.

- Против пункта 1 или 2 — **стоп**, испытание не проводится.
- Против пункта 3, а ручной выбор стоит (это покажет шаг 1.4) — шаги 4.2 и 7 пропустить;
  раздел 4 шага 5.1 тогда напечатает «НЕ ПРОВЕРЕНО: действует ручной выбор», а в шаге 6.4
  вопрос В5 заменяет В8 (там написано как).
- Против пункта 4 — шаги 6.2 и 6.5 пропустить; против пункта 5 — шаг 6.4 пропустить.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p ~/xgw-speed-test/before ~/xgw-speed-test/after && chmod 700 ~/xgw-speed-test && cd ~/xgw-speed-test && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды выполняй из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без пароля
на время испытаний (как в прошлых испытаниях) — вводить пароль некому.

Шаг 1.2. Снимок состояния до обновления:

```bash
sudo xgw --version; git -C ~/xgw log -1 --format='%h %s'; sudo xgw status > before/status.txt; sudo xgw servers > before/servers.txt; sudo cat /run/xgw/status.json > before/status.json; sudo xgw diag > before/diag.txt; tail -1 before/diag.txt; grep -E '^Основной сервер|^Выбран вручную|^Трафик проверок' before/status.txt; grep 'Трафик проверок' before/diag.txt
```

(Если код лежит не в `~/xgw` — подставь свой каталог здесь и в шагах 2.1–2.2.)

Ожидается: `xgw 0.1.14`; хеш и заголовок последнего коммита; «Итог: OK — …, WARN — …,
FAIL — 0»; строки «Основной сервер: …» или «Выбран вручную: …», «Трафик проверок: …» и строка
diag о трафике проверок.
Если не так (другая версия или FAIL не 0): записать в отчёт и спросить заказчика, продолжать ли.

Шаг 1.3. Скрипт проверки. Он **только читает** базу шлюза (`meta`: `speed`, `main`, `pin`),
`/run/xgw/status.json`, раздел `[speed]` из `config.toml`, журнал, ответ панели и код
установленного демона (замеряет ли он при ручном выборе), а размер загрузки считает функцией
самого установленного XGW. Скопируй команду целиком (до строки `EOF` включительно):

```bash
cat > ~/xgw-speed-test/speedcheck.py <<'EOF'
"""Замер скорости в XGW (c71085a, ca51474) — только читает базу, статус, журнал и панель.

sudo python3 speedcheck.py pre [--save-pin FILE]       что сейчас: ручной выбор, основной, участники
sudo python3 speedcheck.py wait T --wait 1800          ждать замеров участников после T (секунды)
sudo python3 speedcheck.py check T JOURNAL [--before FILE]   загрузка, x100, основной, бюджет
python3 speedcheck.py panel STATE                      что панель покажет в строках серверов
python3 speedcheck.py role FP spare|member --wait 600  ждать, пока сервер станет запасным/участником
python3 speedcheck.py pintag FILE                      тег и срок, чтобы вернуть ручной выбор
"""
import argparse, collections, datetime, json, os, re, sqlite3, sys, time, tomllib
from types import SimpleNamespace

ROOT = os.environ.get("XGW_ROOT", "")
DB = f"file:{ROOT}/var/lib/xgw/state.db?mode=ro"
STATUS = f"{ROOT}/run/xgw/status.json"
CONFIG = f"{ROOT}/etc/xgw/config.toml"
LIB = f"{ROOT}/opt/xgw/lib"
MB = 1_000_000
CHUNK = 65536  # загрузка останавливается на первом куске после предела — не больше 64 КБ сверху
LEVELS = {"high": "высокий", "medium": "средний", "low": "низкий"}
VERDICTS = {"OK": "в порядке", "SLOW": "медленный", "FROZEN": "замораживается",
            "STALL_BEFORE_BODY": "не отвечает", "CONNECT_FAIL": "недоступен",
            "TIMEOUT": "тайм-аут"}
LINE_OK = re.compile(r"замер скорости (\S+): (.+?), (\d+) байт за ([\d.]+) с")
LINE_FAIL = re.compile(r"замер скорости (\S+) не удался: (.*)$")
X100 = "скорость серверов x100 не замеряется"


def installed_size_mb():
    """Предел загрузки — функцией установленного XGW (watch/speed.py), а не копией;
    None — установлен код без неё (до c71085a)."""
    sys.dont_write_bytecode = True
    if LIB not in sys.path:
        sys.path.insert(0, LIB)
    try:
        from xgw.watch.speed import size_mb as installed
    except ImportError:
        return None
    return installed


def pin_fix_installed():
    """Замеряет ли установленный демон скорость при ручном выборе (ca51474)."""
    try:
        with open(f"{LIB}/xgw/daemon.py", encoding="utf-8") as handle:
            return "_compare_due" in handle.read()
    except OSError:
        return False


def size_mb(conf, cost):
    installed = installed_size_mb()
    if installed is None:
        sys.exit("ОШИБКА: в установленном XGW нет speed.size_mb — установлен код без c71085a")
    return installed(SimpleNamespace(speed=conf), cost)


def megabytes(value):
    return f"{value:.2f}".rstrip("0").rstrip(".") + " МБ"


def load_status(quiet=False):
    with open(STATUS, encoding="utf-8") as handle:
        data = json.load(handle)
    age = time.time() - float(data.get("updated") or 0)
    if age > 180 and not quiet:
        print(f"ВНИМАНИЕ: статус демона записан {age:.0f} с назад — демон работает?")
    return data


def meta(key):
    conn = sqlite3.connect(DB, uri=True, timeout=10)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    try:
        return json.loads(row[0]) if row and row[0] else None
    except ValueError:
        return None


def speed_conf():
    try:
        with open(CONFIG, "rb") as handle:
            section = tomllib.load(handle).get("speed") or {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"config.toml не прочитан ({exc}) — беру значения по умолчанию")
        section = {}
    return SimpleNamespace(max_mb=section.get("max_mb", 10),
                           max_seconds=section.get("max_seconds", 8),
                           every_hours=section.get("every_hours", 6))


def key_of(entry):
    fingerprint = entry.get("fingerprint") or ""
    return fingerprint if len(fingerprint) >= 8 else entry.get("tag") or ""


def price(entry):
    return float(entry.get("cost") or 0.0)


def label(cost):
    return "безлимитный" if cost == 0 else f"x{cost:g}"


def clock(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m %H:%M") if ts else "—"


def mbps(value):
    return f"{value:.0f} Мбит/с" if value >= 10 else f"{value:.1f}".replace(".", ",") + " Мбит/с"


def size(value):
    return f"{int(value):,}".replace(",", " ")


def record_text(record):
    if not record:
        return "замера нет"
    when = clock(record.get("ts"))
    if record.get("mbps") is None:
        return (f"не удался ({when}): {record.get('error') or '?'}; "
                f"скачано {size(record.get('bytes') or 0)} байт")
    return (f"{mbps(record['mbps'])}, {size(record.get('bytes') or 0)} байт за "
            f"{record.get('seconds')} с ({when})")


def name_of(entry):
    return f"«{entry.get('name') or '?'}» {entry.get('tag') or ''}".strip()


def manual(status):
    pin = status.get("pin")
    return pin if pin and not pin.get("down") else None


def cmd_pre(args):
    status, conf = load_status(), speed_conf()
    records = meta("speed") or {}
    pin, main = status.get("pin"), status.get("main")
    members, spares = status.get("members") or [], status.get("spares") or []
    print(f"Состояние: {status.get('state')}; один основной сервер: "
          f"{'включён' if status.get('sticky') else 'ВЫКЛЮЧЕН'}; замер раз в "
          f"{conf.every_hours} ч, не больше {conf.max_mb} МБ и {conf.max_seconds} с")
    if pin:
        term = "бессрочно" if pin.get("until") is None else f"до {clock(pin['until'])}"
        down = " — сейчас не отвечает, трафик ведёт автовыбор" if pin.get("down") else ""
        print(f"Ручной выбор: «{pin.get('name') or pin['tag']}» ({pin['tag']}), {term}{down}")
    else:
        print("Ручной выбор: нет")
    print("Замеры при ручном выборе (установленный код): " + (
        "идут" if pin_fix_installed()
        else "не идут — код без ca51474 (до шага 2 так и должно быть)"))
    if main:
        basis = ("по скорости" if main.get("basis") == "speed"
                 else "по задержке (скорость не замерена)")
        print(f"Основной: «{main.get('name')}» ({main.get('tag')}), выбран {basis}, "
              f"с {clock(main.get('since'))}")
    else:
        print("Основной: нет")
    new = installed_size_mb() is not None
    if new:
        costs = sorted({0.0, 1.0, 2.0, 10.0, 100.0} | {price(e) for e in members + spares})
        print("Сколько качает замер (установленный код): " + ", ".join(
            f"{label(cost)} — {megabytes(cap) if (cap := size_mb(conf, cost)) else 'не замеряется'}"
            for cost in costs))
    else:
        print("Установлен код без c71085a: размер загрузки не показан "
              "(до шага 2 так и должно быть)")
    print(f"Участники ({len(members)}):")
    for entry in members:
        cap = size_mb(conf, price(entry)) if new else None
        plan = "—" if cap is None else f"замер до {megabytes(cap)}" if cap else "не замеряется"
        level = LEVELS.get(entry.get("priority"), entry.get("priority"))
        mark = "  ← основной" if entry.get("main") else ""
        print(f"  {name_of(entry)} {label(price(entry))} [{level}]: {plan}; последний замер: "
              f"{record_text(records.get(key_of(entry)))}{mark}")
    kept = [entry for entry in spares if records.get(key_of(entry))]
    print(f"Запасных: {len(spares)}, из них с сохранённым замером: {len(kept)}")
    for entry in kept:
        print(f"  {name_of(entry)} {label(price(entry))}: "
              f"{record_text(records.get(key_of(entry)))}")
    print(f"Серверов x100 и дороже: в работе {sum(price(e) >= 100 for e in members)}, "
          f"в запасных {sum(price(e) >= 100 for e in spares)}")
    if args.save_pin:
        with open(args.save_pin, "w", encoding="utf-8") as handle:
            json.dump(pin or {}, handle, ensure_ascii=False)
        os.chmod(args.save_pin, 0o644)
    if not status.get("sticky"):
        verdict = "СТОП: «Один основной сервер» выключен — замеров нет"
    elif not conf.every_hours:
        verdict = "СТОП: замер скорости выключен (every_hours = 0)"
    elif not members:
        verdict = "СТОП: серверов в работе нет"
    elif status.get("state") not in ("HEALTHY", "DEGRADED"):
        verdict = (f"ПОДОЖДАТЬ: состояние {status.get('state')} — скорость замеряется только "
                   "в HEALTHY и DEGRADED")
    else:
        verdict = "можно продолжать"
    print(f"ИТОГ: {verdict}")


def cmd_wait(args):
    conf = speed_conf()
    started = time.time()
    deadline, note = started + args.wait, started
    seen = set()
    pin = manual(load_status(quiet=True))
    if pin and not pin_fix_installed():
        print("ручной выбор действует, а установленный код при нём скорость не замеряет — "
              "код без ca51474")
        return 3
    if pin:
        print(f"ручной выбор «{pin.get('name') or pin['tag']}» действует — замеры идут и при нём")
    while True:
        status = load_status(quiet=True)
        records = meta("speed") or {}
        members = status.get("members") or []
        todo = [entry for entry in members if entry.get("alive") and size_mb(conf, price(entry))]
        done = []
        for entry in todo:
            record = records.get(key_of(entry))
            if record and float(record.get("ts") or 0) >= args.since:
                done.append(entry)
                if key_of(entry) not in seen:
                    seen.add(key_of(entry))
                    print(f"  {time.strftime('%H:%M:%S')} замер {name_of(entry)} "
                          f"{label(price(entry))}: {record_text(record)}")
        if todo and len(done) == len(todo):
            pinned = " — при ручном выборе" if manual(status) else ""
            print(f"замерены все живые участники, которых замеряют: {len(done)}{pinned}")
            return 0
        now = time.time()
        if not todo and now - started > 300:
            print("замерять некого: живых участников, которых замеряют, нет (5 мин)")
            return 4
        if now >= deadline:
            left = [name_of(entry) for entry in todo if entry not in done]
            print(f"за {args.wait:.0f} с не замерены: {len(left)} — " + ", ".join(left))
            return 1
        if now - note >= 120:
            note = now
            print(f"  {time.strftime('%H:%M:%S')} ждём: замерено {len(done)} из {len(todo)}")
        time.sleep(10)


def cmd_check(args):
    status, conf = load_status(), speed_conf()
    records = meta("speed") or {}
    members, spares = status.get("members") or [], status.get("spares") or []
    known = {key_of(entry): (entry, "в работе") for entry in members}
    for entry in spares:
        known.setdefault(key_of(entry), (entry, "запасной"))
    by_suffix = {(entry.get("tag") or "").partition("-")[2]: entry for entry in members + spares}
    fresh = {key: record for key, record in records.items()
             if isinstance(record, dict) and float(record.get("ts") or 0) >= args.since}
    totals = collections.Counter()

    print("1. Сколько качает замер (записи meta «speed» в базе после установки):")
    limited = 0
    for key, record in sorted(fresh.items(), key=lambda item: item[1].get("ts") or 0):
        entry, role = known.get(key, (None, ""))
        if entry is None:
            print(f"  {key[:12]}: сервера нет в статусе — {record_text(record)}")
            continue
        cost = price(entry)
        cap = size_mb(conf, cost)
        if not cap:
            verdict = "ДЕФЕКТ: сервер x100 замерен"
        elif int(record.get("bytes") or 0) > cap * MB + CHUNK:
            verdict = f"ДЕФЕКТ: скачано больше предела {megabytes(cap)}"
        else:
            verdict = "ПРОЙДЕН"
            limited += cost > 0 and record.get("mbps") is not None
        totals[verdict.split(":")[0]] += 1
        print(f"  {name_of(entry)} {label(cost)}, {role}: предел {megabytes(cap)}; "
              f"{record_text(record)} — {verdict}")
    for entry in members:
        if entry.get("alive") and size_mb(conf, price(entry)) and key_of(entry) not in fresh:
            totals["НЕ ЗАМЕРЕН"] += 1
            print(f"  {name_of(entry)} {label(price(entry))}: после установки не замерен — "
                  "НЕ ЗАМЕРЕН")
    print(f"  лимитированных замерено удачно: {limited}")

    print("2. Строки журнала «замер скорости …»:")
    lines = open(args.journal, encoding="utf-8", errors="replace").read().splitlines()
    count, x100_lines = 0, []
    for line in lines:
        good, bad = LINE_OK.search(line), LINE_FAIL.search(line)
        match = good or bad
        if not match:
            continue
        count += 1
        tag = match.group(1)
        entry = by_suffix.get(tag.partition("-")[2])
        if entry is None:
            print(f"  {tag}: сервера нет в статусе — {match.group(0)}")
            continue
        cost = price(entry)
        cap = size_mb(conf, cost)
        text = (f"{match.group(2)}, {size(match.group(3))} байт за {match.group(4)} с"
                if good else f"не удался: {match.group(2)}")
        problem = ""
        if not cap:
            problem = " — ДЕФЕКТ: x100 замерен"
            x100_lines.append(tag)
        elif good and int(match.group(3)) > cap * MB + CHUNK:
            problem = f" — ДЕФЕКТ: больше предела {megabytes(cap)}"
        if problem:
            totals["ДЕФЕКТ"] += 1
        print(f"  {tag} {label(cost)} (предел {megabytes(cap)}): {text}{problem}")
    print(f"  строк: {count}")

    print("3. Серверы x100 и дороже:")
    x100 = [entry for entry in members + spares if price(entry) >= 100]
    measured = [entry for entry in x100 if key_of(entry) in fresh]
    working = [entry for entry in members if price(entry) >= 100]
    print(f"  всего {len(x100)}, в работе {len(working)}; замерены после установки: "
          f"{len(measured)}; строк журнала о них: {len(x100_lines)}")
    if measured or x100_lines:
        verdict = "ДЕФЕКТ: сервер x100 замерен"
    elif not x100:
        verdict = "НЕ ПРОВЕРЕНО: серверов x100 нет"
    else:
        verdict = "ПРОЙДЕН"
    totals[verdict.split(":")[0]] += 1
    print(f"  ИТОГ: {verdict}")

    print("4. Основной сервер:")
    main = status.get("main")
    rated = [(entry, records.get(key_of(entry))) for entry in members]
    rated = [(entry, record) for entry, record in rated
             if record and record.get("mbps") is not None and key_of(entry) in fresh]
    for entry, record in rated:
        mark = "  ← основной" if entry.get("main") else ""
        print(f"  {name_of(entry)} {label(price(entry))}: {mbps(record['mbps'])}{mark}")
    if manual(status):
        verdict = "НЕ ПРОВЕРЕНО: действует ручной выбор"
    elif not main:
        verdict = f"НЕ ПРОВЕРЕНО: основного нет (состояние {status.get('state')})"
    elif main.get("basis") == "speed" and main.get("mbps") is not None:
        verdict = "ПРОЙДЕН"
        best = max(rated, key=lambda item: item[1]["mbps"], default=None)
        if best and best[1]["mbps"] > float(main["mbps"]) * 1.3:
            print(f"  НАБЛЮДЕНИЕ: {name_of(best[0])} быстрее основного больше чем на 30 %")
    elif rated:
        verdict = "ДЕФЕКТ: замеры есть, а основной выбран по задержке"
    else:
        verdict = "НЕ ПРОВЕРЕНО: удачных замеров участников нет"
    totals[verdict.split(":")[0]] += 1
    stored = meta("main") or {}
    print(f"  основной в статусе: «{(main or {}).get('name')}», basis = "
          f"{(main or {}).get('basis')}, скорость {(main or {}).get('mbps')}")
    print(f"  в базе (meta «main»): «{stored.get('name')}», basis = {stored.get('basis')}")
    print(f"  ИТОГ: {verdict}")

    print("5. Бюджет трафика проверок:")
    budget = status.get("budget") or {}
    rounds = 24 / conf.every_hours if status.get("sticky") and conf.every_hours else 0
    caps = [size_mb(conf, price(entry)) for entry in members]
    want = round(int(sum(caps) * MB * rounds) / MB, 1)
    got = budget.get("speed_mb")
    print(f"  раунд: {' + '.join(megabytes(cap) for cap in caps) or '0'} = {megabytes(sum(caps))}, "
          f"раундов в сутки: {rounds:g} → ожидается {want:g} МБ/сут; в статусе: {got}")
    ok = got is not None and abs(float(got) - want) <= 0.15
    parts = collections.defaultdict(float)
    for entry in members:
        if price(entry) > 0 and entry.get("source"):
            parts[entry["source"]] += rounds * size_mb(conf, price(entry)) * price(entry)
    for source, part in parts.items():
        total = (budget.get("quota_mb") or {}).get(source)
        print(f"  квота подписки «{source}»: замеры тратят ~{part:.0f} МБ квоты в сутки "
              f"(с множителями); все проверки — {total} МБ/сут")
        ok = ok and total is not None and float(total) + 0.15 >= part
    if args.before:
        before = (json.load(open(args.before, encoding="utf-8")).get("budget") or {})
        print(f"  до обновления: замер {before.get('speed_mb')} МБ/сут, квота "
              f"{before.get('quota_mb')}; после: замер {got} МБ/сут, "
              f"квота {budget.get('quota_mb')}")
    verdict = "ПРОЙДЕН" if ok else "ДЕФЕКТ: цифры бюджета не сходятся"
    totals[verdict.split(":")[0]] += 1
    print(f"  ИТОГ: {verdict}")
    print("ВСЕГО: " + ", ".join(f"{key.lower()} {value}" for key, value in sorted(totals.items())))


def stamp(ts, now):
    if not ts:
        return "—"
    moment = datetime.datetime.fromtimestamp(ts)
    today = datetime.datetime.fromtimestamp(now).date()
    return moment.strftime("%H:%M") if moment.date() == today else moment.strftime("%d.%m %H:%M")


def cmd_panel(args):
    state = json.load(open(args.state, encoding="utf-8"))
    now, sticky = state.get("now") or time.time(), state.get("sticky") or {}
    snapshot = {key_of(entry): entry for entry in (state.get("members") or [])
                + (state.get("spares") or [])}
    rows = [row for row in state.get("servers") or [] if row.get("status") in ("member", "spare")]
    totals = collections.Counter()
    show, candidates = [], []
    for row in rows:
        source = snapshot.get(key_of(row), {})
        has = row.get("speed_mbps") is not None
        if source.get("speed_mbps") is not None and not (has and row.get("speed_ts")):
            totals["ДЕФЕКТ"] += 1
            print(f"ДЕФЕКТ: у «{row.get('name')}» ({row['status']}) замер есть в статусе, "
                  "а в строке панели его нет")
        elif has:
            totals["ПРОЙДЕН"] += 1
        member = row["status"] == "member"
        x100 = member and not has and not row.get("speed_error") and (
            row.get("multiplier") or 0) >= 100 and sticky.get("on") and sticky.get("every_hours")
        if has or x100 or member:
            show.append((row, x100))
        if (member and has and not row.get("main") and row.get("alive")
                and row.get("speed_error") in ("", None)):
            candidates.append(row)
    print("Что панель покажет (справа — скорость и задержка, под именем — состояние):")
    for row, x100 in show:
        speed = ""
        if row.get("speed_mbps") is not None:
            pale = "бледно" if row["status"] == "spare" else "жирно"
            speed = f"{mbps(row['speed_mbps'])} ({pale}) "
        if row["status"] == "member":
            if row.get("alive") is False:
                value = "нет ответа"
            elif row.get("delay_ms") is None:
                value = "жив" if row.get("alive") else "проверяется"
            else:
                value = f"{row['delay_ms']} мс"
            role = "основной" if row.get("main") and not manual(state) else "в работе"
            if row.get("speed_mbps") is not None:
                role += f" · замер скорости {stamp(row.get('speed_ts'), now)}"
            elif row.get("speed_error"):
                role += f" · замер скорости не удался {stamp(row.get('speed_ts'), now)}"
            elif x100:
                role += f" · {X100}"
        else:
            value = VERDICTS.get(row.get("verdict"), row.get("verdict") or "не проверялся")
            role = "резервный: …" if row.get("reserve") else "запасной"
            if row.get("scanned"):
                role += f" · проверен {stamp(row['scanned'], now)}"
            if row.get("speed_mbps") is not None:
                role += f" · замер скорости {stamp(row.get('speed_ts'), now)}, когда был в работе"
        mult = f" [x{row['multiplier']:g}]" if row.get("multiplier") else ""
        print(f"  «{row.get('name')}»{mult}: справа «{speed}{value}»; под именем «{role}»")
    spares = sum(1 for row, _x in show if row["status"] == "spare")
    print(f"Запасных с замером в панели: {spares}")
    print(f"Серверов x100 в работе с подписью «{X100}»: {sum(1 for _r, x in show if x)}")
    if not spares:
        members = sum(1 for row in rows if row["status"] == "member" and row.get("alive"))
        if candidates and members >= 2:
            row = candidates[0]
            print(f"Кандидат для шага 6.2: {row['fingerprint']} «{row.get('name')}» "
                  f"({row.get('tag')}), приоритет {row.get('priority')}")
        else:
            print("Кандидата для шага 6.2 нет: нужен живой участник с замером, не основной, "
                  "и ещё хотя бы один живой участник")
    main = state.get("main") or {}
    if main and not manual(state):
        basis = ("" if main.get("basis") == "speed"
                 else " (скорость ещё не замерена — выбран по задержке)")
        speed = f" — {mbps(main['mbps'])}" if main.get("mbps") is not None else ""
        print(f"Над списком: «Весь трафик идёт через «{main.get('name') or main.get('tag')}»"
              f"{speed}{basis}. …»")
    print("ВСЕГО: " + ", ".join(f"{key.lower()} {value}" for key, value in sorted(totals.items())))


def cmd_role(args):
    deadline = time.time() + args.wait
    group = "spares" if args.role == "spare" else "members"
    while True:
        status = load_status(quiet=True)
        found = next((entry for entry in status.get(group) or []
                      if (entry.get("fingerprint") or "").startswith(args.fp)), None)
        if found or time.time() >= deadline:
            break
        time.sleep(10)
    word = "запасной" if args.role == "spare" else "в работе"
    if not found:
        print(f"за {args.wait:.0f} с сервер {args.fp[:12]} не стал: {word}")
        return 1
    speed = mbps(found["speed_mbps"]) if found.get("speed_mbps") is not None else "нет"
    print(f"{name_of(found)} теперь {word}; скорость в статусе: {speed}, замер "
          f"{clock(found.get('speed_ts'))}")
    return 0


def cmd_pintag(args):
    pin = json.load(open(args.file, encoding="utf-8")) or {}
    until = pin.get("until")
    if not pin.get("tag"):
        print("ручного выбора не было", file=sys.stderr)
    elif until is not None and until <= time.time() + 60:
        print(f"срок выбора «{pin.get('name')}» истёк — возвращать нечего", file=sys.stderr)
    else:
        status = load_status(quiet=True)
        suffix = pin["tag"].partition("-")[2]
        found = next((entry for entry in (status.get("members") or [])
                      + (status.get("spares") or [])
                      if (entry.get("tag") or "").partition("-")[2] == suffix), None)
        if found:
            ttl = "forever" if until is None else f"{max(1, int((until - time.time()) // 60))}m"
            print(f"{found['tag']} {ttl}")
            return 0
        print(f"сервера «{pin.get('name')}» больше нет в списке", file=sys.stderr)
    print("- -")
    return 0


parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest="command", required=True)
pre = commands.add_parser("pre")
pre.add_argument("--save-pin")
wait = commands.add_parser("wait")
wait.add_argument("since", type=float)
wait.add_argument("--wait", type=float, default=1800)
check = commands.add_parser("check")
check.add_argument("since", type=float)
check.add_argument("journal")
check.add_argument("--before")
panel = commands.add_parser("panel")
panel.add_argument("state")
role = commands.add_parser("role")
role.add_argument("fp")
role.add_argument("role", choices=("spare", "member"))
role.add_argument("--wait", type=float, default=600)
pintag = commands.add_parser("pintag")
pintag.add_argument("file")
args = parser.parse_args()
sys.exit({"pre": cmd_pre, "wait": cmd_wait, "check": cmd_check, "panel": cmd_panel,
          "role": cmd_role, "pintag": cmd_pintag}[args.command](args) or 0)
EOF
python3 -c "import ast; ast.parse(open('$HOME/xgw-speed-test/speedcheck.py').read()); print('speedcheck.py OK')"; sha256sum ~/xgw-speed-test/speedcheck.py
```

Ожидается: `speedcheck.py OK` и строка, которая начинается с
`ff06c71e2bc2cad906d674fc0556315d200cc78029161b2b06ec28941b584058`.
Если хеш другой: файл скопирован с ошибкой — удали его (`rm ~/xgw-speed-test/speedcheck.py`)
и повтори шаг 1.3. Со вторым неверным хешем — **стоп**, сообщить заказчику.

Шаг 1.4. Что сейчас на шлюзе:

```bash
sudo python3 speedcheck.py pre --save-pin before/pin.json | tee before/pre.txt
```

Ожидается: блок со строками «Состояние: …», «Ручной выбор: …» (например «Ручной выбор:
«🇦🇪 x10📶🛜 ОАЭ | Дубай | AI» (proxy-ae-1cbc), бессрочно» или «Ручной выбор: нет»),
«Замеры при ручном выборе (установленный код): не идут — код без ca51474 (до шага 2 так и
должно быть)», «Основной: …», строка «Установлен код без c71085a: размер загрузки не показан
(до шага 2 так и должно быть)», список участников с множителями (например «x10 [высокий]») и
последним замером (у лимитированных сейчас — «замера нет»), «Серверов x100 и дороже: …» и
последняя строка «ИТОГ: …». Ручной выбор **не снимать**: замеры при нём проверяет шаг 4.1.

По последней строке:

- «ИТОГ: можно продолжать» — перейти к шагу 2.1.
- «ИТОГ: ПОДОЖДАТЬ: состояние …» — подождать 10 минут (`sleep 600`) и повторить шаг 1.4; после
  третьего такого ответа — **стоп**, сообщить заказчику.
- «ИТОГ: СТОП: …» — **стоп**, сообщить заказчику (настройки не менять).
- `Traceback` или «ОШИБКА» — **стоп**, сохранить вывод, сообщить заказчику.

## 2. Установка

Шаг 2.1:

```bash
cd ~/xgw && git pull && git log -1 --format=%H && git merge-base --is-ancestor c71085a HEAD && echo "c71085a есть"; git merge-base --is-ancestor ca51474 HEAD && echo "ca51474 есть"; grep __version__ src/xgw/__init__.py; cd ~/xgw-speed-test
```

Ожидается: «c71085a есть», «ca51474 есть» и `__version__ = "0.1.14"`. Записать хеш.
Если «c71085a есть» или «ca51474 есть» не напечатано: **стоп**, сообщить заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/xgw && date +%s > ~/xgw-speed-test/install-epoch.txt && date '+%F %T' | tee ~/xgw-speed-test/install-time.txt && sudo sh packaging/install.sh --yes 2>&1 | tee ~/xgw-speed-test/after/install.txt | tail -25; echo "код ${PIPESTATUS[0]}"; cd ~/xgw-speed-test
```

Ожидается: «код 0». Время из `install-time.txt` — «время установки» в шагах ниже
(`install-epoch.txt` — то же время в секундах, его читает скрипт).
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику.

## 3. Службы и установленный код

Шаг 3.1:

```bash
sleep 20; sudo xgw --version; systemctl is-active xgw-net xgw-xray xgw xgw-dhcp xgw-singbox; curl -s http://127.0.0.1:8781/app.js | grep -c 'скорость серверов x100 не замеряется'; curl -s http://127.0.0.1:8781/app.css | grep -c 'server > .values'; curl -s http://127.0.0.1:8781/app.js | grep -c 'Замеры скорости идут и при ручном выборе'; sudo python3 speedcheck.py pre | tee after/pre.txt
```

Ожидается:

- `xgw 0.1.14`, пять раз `active`;
- `1`, `2` и `1` — панель отдаёт новые файлы;
- блок `pre`, в нём строки «Ручной выбор: …» (тот же, что в шаге 1.4), «Замеры при ручном
  выборе (установленный код): идут» и «Сколько качает замер (установленный код): безлимитный —
  10 МБ, x1 — 10 МБ, x2 — 5 МБ, x10 — 1 МБ, x100 — не замеряется» (плюс множители, которые есть
  в подписках, — например «x3 — 3.33 МБ», «x20 — 1 МБ»); у участников — «замер до 1 МБ» (x10),
  «замер до 10 МБ» (x1, безлимитные) и т. п.; последняя строка «ИТОГ: можно продолжать».

Если не так:

- `xgw` не `active`: **стоп**, `sudo journalctl -u xgw -n 40 --no-pager > after/xgw-fail.txt`,
  сообщить заказчику.
- Вместо «Сколько качает замер» — «Установлен код без c71085a», или «Замеры при ручном
  выборе …: не идут»: **стоп**, установка не обновила код; сообщить заказчику.
- Число не `1`, не `2` или не `1`: записать в отчёт как дефект «панель отдаёт старые файлы» и
  продолжать.
- «ИТОГ: ПОДОЖДАТЬ» или «СТОП»: как в шаге 1.4.

## 4. Замеры после установки

Шаг 4.1. Команда ждёт, пока шлюз замерит каждого живого участника, которого он замеряет (до
30 минут; обычно 2–5 минут после установки: один замер за шаг демона, шаг — 20 с). Ручной
выбор, если он стоит, **не снимать**: замеры должны идти и при нём.

```bash
sudo python3 speedcheck.py wait $(cat install-epoch.txt) --wait 1800 | tee after/wait.txt; date +%T
```

Ожидается: если стоит ручной выбор — первая строка «ручной выбор «…» действует — замеры идут и
при нём»; затем строки вида «22:03:41 замер «🇹🇷 x10 🛜 | Турция | AI» proxy-tr-76a6 x10: 14
Мбит/с, 1 048 576 байт за 0.59 с (18.10 22:03)», последняя — «замерены все живые участники,
которых замеряют: N» (при ручном выборе — с « — при ручном выборе» в конце). Байт: у x10 —
около 1 000 000, у x2 — около 5 000 000, у x1 и безлимитных — до 10 000 000 (меньше, если
сервер медленный: замер длится не дольше 8 с).

Если не так:

- «за 1800 с не замерены: …»: замер ждёт, пока через серверы идёт заметный трафик (кто-то
  смотрит видео или качает), — это не дефект. Повторить шаг 4.1 один раз. Если и тогда не
  все — записать имена; если при этом стоит ручной выбор и **не замерен ни один** —
  записать дефект «при ручном выборе скорость не замеряется». Перейти к шагу 4.2.
- «… установленный код при нём скорость не замеряет …»: **стоп**, установка не обновила код
  (шаг 3.1 должен был это показать); сообщить заказчику.
- «замерять некого …»: в работе только серверы x100 (или серверы не отвечают) — записать и
  перейти к шагу 4.2.

Шаг 4.2. **Только если** в `after/pre.txt` строка «Ручной выбор: …» — не «нет», и заказчик
согласился на пункт 3. Иначе — перейти к шагу 5.1. Снять ручной выбор и посмотреть, какой
основной выбрал шлюз:

```bash
grep '^Ручной выбор' after/pre.txt; sudo xgw unpin; date '+%F %T' | tee unpinned.txt; sleep 60; sudo xgw status | grep -E '^Основной сервер|^Выбран вручную'
```

Ожидается: строка о ручном выборе из `after/pre.txt`, «автовыбор: через минуту шлюз снова
закрепит основной сервер — самый быстрый из серверов в работе», время и через минуту строка
«Основной сервер: proxy-… «…» — N Мбит/с, с ЧЧ:ММ; весь трафик через него, другие участники
наготове» — **без** «(выбран по задержке, скорость ещё не замерена)»: основной выбран сразу по
замерам, сделанным при ручном выборе. Строки «Выбран вручную» нет.

Если не так:

- «Выбран вручную» осталась: повторить шаг 4.2 один раз; если и тогда — **стоп**, сообщить
  заказчику.
- «(выбран по задержке, скорость ещё не замерена)»: если шаг 4.1 кончился «замерены все …» —
  записать дефект «после снятия ручного выбора основной выбран не по замерам» (строки
  `after/wait.txt` и эту строку целиком) и продолжать; если шаг 4.1 кончился иначе — записать,
  не дефект.
- Строки «Основной сервер» нет: `sleep 60; sudo xgw status | grep '^Основной сервер'`; если и
  тогда нет — записать и продолжать.

## 5. Проверка: размер загрузки, x100, основной, бюджет

Шаг 5.1:

```bash
T=$(cat install-time.txt); sudo journalctl -u xgw --since "$T" --no-pager -o cat > after/journal.txt; sudo cat /run/xgw/status.json > after/status.json; sudo xgw status > after/status.txt; sudo xgw diag > after/diag.txt; sudo python3 speedcheck.py check $(cat install-epoch.txt) after/journal.txt --before before/status.json | tee after/check.txt
```

Ожидается, по разделам вывода:

1. «Сколько качает замер (записи meta «speed» …)»: у каждого замеренного сервера — его
   множитель, «предел 1 МБ» (x10), «предел 5 МБ» (x2), «предел 10 МБ» (x1, безлимитные), байты
   и «— ПРОЙДЕН»; строка «лимитированных замерено удачно: N» — N больше 0, если в работе
   лимитированные.
2. «Строки журнала «замер скорости …»»: по строке на каждый замер из раздела 1 (больше — если
   сервер замеряли дважды, это не дефект), у каждой — байты не больше предела, без «ДЕФЕКТ».
   Строки журнала демона выглядят так: «замер скорости proxy-tr-76a6: 14 Мбит/с, 1048576 байт
   за 0.6 с» (неудачный замер — «замер скорости … не удался: …»).
3. «Серверы x100 и дороже»: «замерены после установки: 0; строк журнала о них: 0» и «ИТОГ:
   ПРОЙДЕН» (или «НЕ ПРОВЕРЕНО: серверов x100 нет» — так и записать).
4. «Основной сервер»: скорости участников, «основной в статусе: «…», basis = speed, скорость
   …», «в базе (meta «main»): «…», basis = speed» и «ИТОГ: ПРОЙДЕН».
5. «Бюджет трафика проверок»: «раунд: 1 МБ + 1 МБ + … = N МБ, раундов в сутки: 4 → ожидается
   M МБ/сут; в статусе: M»; для лимитированной подписки — «замеры тратят ~K МБ квоты в сутки
   (с множителями)»; строка «до обновления: замер … МБ/сут …; после: …» (до обновления у
   лимитированных участников замер был 0) и «ИТОГ: ПРОЙДЕН».
6. Последняя строка — «ВСЕГО: пройден N» (может быть ещё «не проверено …» и «не замерен …»),
   **без «дефект»**.

Если не так:

- строка с «ДЕФЕКТ»: записать в отчёт раздел вывода целиком как дефект (что ожидалось — в
  этом шаге выше);
- «НЕ ЗАМЕРЕН»: не дефект, если шаг 4.1 кончился «не замерены»; записать;
- «НЕ ПРОВЕРЕНО: действует ручной выбор» — если заказчик был против пункта 3 (шага 4.2 не
  было), так и должно быть: записать «основной не проверен: ручной выбор». Иначе выбор
  появился снова (его кто-то вернул): записать, спросить заказчика, снять ли его ещё раз (шаг
  4.2), и после этого повторить шаг 5.1;
- «НАБЛЮДЕНИЕ: … быстрее основного больше чем на 30 %» — записать в «Наблюдения» вместе со
  строкой «Основной: …» из `before/pre.txt` (как он был выбран до обновления); дефект это или
  нет, решит разработчик.

Шаг 5.2. Те же цифры в `xgw status` и `xgw diag`:

```bash
grep -E '^Основной сервер|^Трафик проверок|за месяц это|Мбит/с' after/status.txt; echo "--- diag до и после:"; grep 'Трафик проверок' before/diag.txt after/diag.txt
```

Ожидается:

- «Основной сервер: proxy-… «…» — N Мбит/с, с ЧЧ:ММ; весь трафик через него, другие
  участники наготове» — **без** «(выбран по задержке, скорость ещё не замерена)»;
- строки участников со скоростью: «жив, 200 мс, 14 Мбит/с»;
- «Трафик проверок: ~… МБ/сут (…); сквозная проверка ещё ~… МБ/сут, замер скорости — до
  ~M МБ/сут» — M то же, что «в статусе» в разделе 5 шага 5.1 (с округлением);
- «за месяц это ~P % квоты подписки «…» (~Q МБ квоты в сутки с множителями)»;
- в строке diag **после** — «вместе со сквозной проверкой и замером скорости — ~… МБ в сутки».
  Если до обновления в работе были только лимитированные, в строке diag **до** слов «и
  замером скорости» нет.

Если не так: записать в отчёт строки как есть (дефект, если нет «замер скорости — до» в
status или «и замером скорости» в diag после, хотя в шаге 5.1 раздел 5 показал замер больше 0).

## 6. Строки панели

Шаг 6.1. Данные, которые панель отдаёт странице (токен в отчёт не записывать):

```bash
J=~/xgw-speed-test/panel.jar; curl -s -o /dev/null -c $J "http://127.0.0.1:8781/?token=$(sudo cat /var/lib/xgw/panel-token)"; curl -s -b $J http://127.0.0.1:8781/api/state > after/state.json; python3 speedcheck.py panel after/state.json | tee after/panel.txt
```

Ожидается: «Что панель покажет …» и строки серверов в работе вида ««🇹🇷 x10 🛜 | Турция | AI»
[x10]: справа «14 Мбит/с (жирно) 200 мс»; под именем «в работе · замер скорости 22:03»» (у
основного — «основной · замер скорости …»); строки запасных с сохранённым замером — «справа
«63 Мбит/с (бледно) в порядке»; под именем «запасной · проверен 22:10 · замер скорости 17.10
14:05, когда был в работе»»; затем «Запасных с замером в панели: K», «Серверов x100 в работе с
подписью …: X», «Над списком: «Весь трафик идёт через «…» — N Мбит/с. …»» и последняя строка
«ВСЕГО: пройден N» **без «дефект»**.

Если не так:

- `Traceback` с `JSONDecodeError`: панель не ответила данными — повторить шаг 6.1 через минуту;
  если снова — записать и перейти к шагу 7;
- «ДЕФЕКТ: у «…» замер есть в статусе, а в строке панели его нет» — записать как дефект.

Дальше: если «Запасных с замером в панели» — **1 или больше**, шаги 6.2, 6.3 и 6.5 пропустить
(запасной с замером уже есть — запиши его имя) и перейти к шагу 6.4. Если **0** — шаг 6.2.

Шаг 6.2. **Только если** запасных с замером 0 и заказчик согласился на пункт 4. Скрипт в шаге
6.1 напечатал строку «Кандидат для шага 6.2: <отпечаток> «имя» (тег), приоритет <уровень>» —
живой участник с замером, не основной. Команда берёт его оттуда сама, ставит ему приоритет
«низкий» (он уходит в запасные) и ждёт, пока он станет запасным (до 10 минут):

```bash
read FP LEVEL < <(sed -n 's/^Кандидат для шага 6.2: \([0-9a-f]*\) .*, приоритет \([a-z]*\)$/\1 \2/p' after/panel.txt); echo "кандидат: ${FP:-нет} ${LEVEL:-}" | tee demoted.txt; if [ -n "$FP" ]; then sudo xgw priority "$FP" low && sudo python3 speedcheck.py role "$FP" spare --wait 600; fi
```

Ожидается: «кандидат: 76a628c4 high» (отпечаток и прежний приоритет — **файл `demoted.txt` не
удалять**, по нему шаг 6.5 вернёт приоритет), «приоритет сервера «…»: низкий. Демон применит
его на ближайшем шаге; …» и потом ««…» spare-… теперь запасной; скорость в статусе: 14 Мбит/с,
замер 18.10 22:03».

Если не так:

- «кандидат: нет» — в шаге 6.1 было «Кандидата для шага 6.2 нет»: шаги 6.3 и 6.5 пропустить,
  записать «запасной с замером не проверен: подходящего участника нет» и перейти к шагу 6.4;
- «за 600 с сервер … не стал: запасной» — сразу шаг 6.5 (вернуть приоритет), записать «6.2 не
  проверено», шаг 6.3 пропустить.

Шаг 6.3. Панель после того, как сервер стал запасным:

```bash
curl -s -b ~/xgw-speed-test/panel.jar http://127.0.0.1:8781/api/state > after/state-spare.json; python3 speedcheck.py panel after/state-spare.json | tee after/panel-spare.txt | grep -E 'бледно|Запасных с замером|ВСЕГО'
```

Ожидается: строка этого сервера «справа «14 Мбит/с (бледно) …»; под именем «запасной · … ·
замер скорости 22:03, когда был в работе»» (или «резервный: … · …», если шлюз сделал его
резервным выходом), «Запасных с замером в панели: 1» (или больше) и «ВСЕГО» без «дефект».
Если строки «(бледно)» нет — записать как дефект «запасной не показывает последний замер».

Шаг 6.4. **Спроси заказчика** (если он согласился на пункт 5). Перед вопросом открой
`after/panel-spare.txt` (если был шаг 6.3) или `after/panel.txt` и подставь в вопросы имена и
цифры оттуда. Скажи:

«Откройте панель XGW (ярлык «XGW» в меню приложений) и обновите страницу: Ctrl+Shift+R.
Посмотрите на список серверов и ответьте да или нет:

- В1. У серверов в работе справа — скорость жирным (например «14 Мбит/с») и рядом задержка
  («200 мс»)?
- В2. Под именем — «в работе · замер скорости ЧЧ:ММ», у основного — «основной · замер скорости
  ЧЧ:ММ»?
- В3. У запасного «<имя запасного из файла>» справа бледная скорость, а под именем «… · замер
  скорости ЧЧ:ММ, когда был в работе»? Если навести мышь на скорость — подсказка «Скорость по
  замеру …, когда сервер был в работе»?
- В4. Сузьте окно браузера (потяните за край), пока кнопки сервера не уйдут на отдельную
  строку. Теперь скорость стоит над задержкой, а имя сервера видно?
- В5. Над списком серверов: «Весь трафик идёт через «<имя основного>» — <скорость>. …» без
  «скорость ещё не замерена», и дальше «Скорость замеряется раз в 6 ч, до <M> МБ в сутки;
  лимитированные — меньшей загрузкой, чтобы не тратить квоту, x100 — не замеряются.»?
- В6. В строке о проверках: «Проверки серверов расходуют около … (…, замер скорости — до <M>
  МБ в сутки, …)»?
- В7. (только если в файле «Серверов x100 в работе с подписью …» больше 0) У сервера x100 в
  работе под именем «в работе · скорость серверов x100 не замеряется»?»

Если заказчик был против пункта 3 (ручной выбор стоит, шага 4.2 не было): В2 спросить без
«у основного — …», В5 не задавать, а задать вместо него В8 из шага 7.

Записать ответы в таблицу отчёта. Каждое «нет» — что заказчик видит вместо этого (его
словами). «Нет» на В1–В6 — дефект вида панели.

Шаг 6.5. **Только если** был шаг 6.2 с кандидатом. Вернуть прежний приоритет и дождаться, пока
сервер снова будет в работе (до 10 минут):

```bash
read FP LEVEL < <(sed -n 's/^кандидат: \([0-9a-f]*\) \([a-z]*\)$/\1 \2/p' demoted.txt); if [ -n "$FP" ]; then sudo xgw priority "$FP" "$LEVEL" && sudo python3 speedcheck.py role "$FP" member --wait 600; fi
```

Ожидается: «приоритет сервера «…»: высокий» (тот уровень, что был в `demoted.txt`) и ««…»
proxy-… теперь в работе; …».
Если «за 600 с … не стал: в работе»: приоритет уже возвращён; сервер вернётся в работу, когда
ответит, — записать, не дефект.

## 7. Вернуть ручной выбор

**Только если** был шаг 4.2. Скрипт находит нынешний тег сервера, выбранного до испытаний, и
срок выбора:

```bash
read TAG TTL < <(sudo python3 speedcheck.py pintag before/pin.json); echo "вернуть: $TAG $TTL"; if [ "$TAG" != "-" ]; then sudo xgw pin "$TAG" --ttl "$TTL"; fi; sleep 20; sudo xgw status | grep -E '^Выбран вручную|^Основной сервер'
```

Ожидается: «вернуть: proxy-ae-1cbc forever», ««…» выбран вручную: весь трафик идёт через него,
пока не вернёте автовыбор. …» и «Выбран вручную: «…» (proxy-…) — весь трафик через него; …».
Если «вернуть: - -»: вернуть нечего (срок выбора истёк или сервера больше нет — причина
напечатана строкой выше). Записать и сказать заказчику, что ручной выбор не возвращён и почему.

С возвращённым ручным выбором замеры идут и дальше, раз в 6 ч (это проверил шаг 4.1).

**Спроси заказчика** (если выбор возвращён и заказчик согласился на пункт 5): «Обновите панель
(Ctrl+Shift+R) и ответьте да или нет:

- В8. Над списком серверов: «Пока сервер выбран вручную, основной сервер не выбирается — шлюз
  выберет его, когда выбор снимут. Замеры скорости идут и при ручном выборе: раз в 6 ч, до <M>
  МБ в сутки; …», а у серверов в работе справа по-прежнему скорость?»

Записать ответ в таблицу отчёта; «нет» — дефект вида панели (что видно вместо этого — словами
заказчика).

## 8. Итоговое состояние

Шаг 8.1:

```bash
systemctl is-active xgw-net xgw-xray xgw-singbox xgw xgw-dhcp; sudo xgw diag > after/diag-end.txt; tail -1 after/diag-end.txt; sudo xgw status | head -8; rm -f ~/xgw-speed-test/panel.jar
```

Ожидается: пять `active`, «FAIL — 0». Телефон и устройства заказчика — «через VPN».
Если FAIL не 0: записать строки с FAIL (`grep FAIL after/diag-end.txt`).

## 9. Что смотреть, если что-то пошло не так

- Пропал интернет — `sudo xgw disable`, сообщить заказчику (§0).
- Демон не `active` после установки — **не** перезапускать его; журнал в `after/xgw-fail.txt`
  и сообщить заказчику.
- Заказчик просит вернуть ручной выбор раньше — сразу шаг 7 (если был шаг 6.2 — сначала 6.5);
  что не успели проверить — в «Что не проверено».
- Команда `xgw` пишет «ошибка» — сохранить вывод в `after/`, записать в отчёт, перейти к
  следующему шагу, если шаг не помечен «стоп».

## 10. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.14-speed-<ГГГГ-ММ-ДД>.md` в репозитории. Заполни бланк:

```markdown
# Отчёт об испытаниях XGW на реальной машине: скорость в строках серверов (c71085a, ca51474)

Код: <хеш>. Установка: <время>, код <0/…>. Согласие заказчика: пункты <1–5 / какие нет>.

## Итог
<3–5 предложений: видна ли скорость в строках панели; шли ли замеры при ручном выборе; сколько
качали лимитированные и с какими множителями; не замерялись ли x100; выбран ли основной по
скорости; сходится ли бюджет>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.4 до обновления | — | <ручной выбор: да/нет; основной и как выбран; участники и множители> |
| 2 установка | пройден / нет | |
| 3 службы и код | пройден / нет | <строки «Сколько качает замер» и «Замеры при ручном выборе»; app.js/app.css: 1/2/1> |
| 4.1 замеры после установки | пройден / частично | <сколько замерено, через сколько минут после установки; при ручном выборе или без него> |
| 4.2 выбор снят: основной сразу по замерам | пройден / дефект / не нужно | <строка «Основной сервер: …»> |
| 5.1-1,2 размер загрузки | пройден / дефект / не проверено | <множители в работе и байты> |
| 5.1-3 x100 не замеряются | пройден / дефект / не проверено | <сколько x100, в работе ли> |
| 5.1-4 основной по скорости | пройден / дефект / не проверено | <имя, скорость, basis> |
| 5.1-5 бюджет и квота | пройден / дефект | <замер МБ/сут до и после; квота с множителями> |
| 5.2 status и diag | пройден / дефект | |
| 6.1 данные панели | пройден / дефект | <«ВСЕГО» из panel.txt> |
| 6.3 запасной с замером | пройден / дефект / не проверено | <имя запасного; был запасным сам или после 6.2> |
| 6.4 вид панели | пройден / дефект / не проверено | <ответы В1–В7 кратко> |
| 6.5 приоритет возвращён | сделано / не нужно | |
| 7 ручной выбор возвращён | сделано / не нужно / не вышло | |
| 8 итоговое состояние | пройден / нет | <FAIL — …> |

## Шаг 4 — замеры
<вывод after/wait.txt; строки шага 4.2>

## Шаг 5 — проверка
<вывод after/check.txt целиком; строки шага 5.2>

## Шаг 6 — панель
<вывод after/panel.txt (и after/panel-spare.txt, если был шаг 6.3)>

| Вопрос | Ответ заказчика | Что видно вместо ожидаемого |
|---|---|---|
| В1 скорость и задержка справа | | |
| В2 время замера под именем | | |
| В3 запасной: бледная скорость, «когда был в работе» | | |
| В4 узкое окно: скорость над задержкой | | |
| В5 строка об основном сервере | | |
| В6 строка о проверках | | |
| В7 x100 в работе | | |
| В8 при ручном выборе: «Замеры скорости идут и при ручном выборе» | | |

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние машины
```

Перед коммитом проверь, что в отчёте нет секретов:

```bash
grep -nE '(vless|vmess|trojan|ss|hysteria2)://[^*]|[0-9a-f]{8}-[0-9a-f]{4}-|token|/sub/|panel.jar' docs/TEST-REPORT-REAL-MACHINE-0.1.14-speed-*.md
```

Ожидается: пусто. Если что-то нашлось — убрать из отчёта.

Коммит только отчёта: `git add docs/TEST-REPORT-REAL-MACHINE-0.1.14-speed-*.md && git commit -m
"Отчёт об испытаниях XGW на реальной машине: скорость в строках серверов" && git push`.
