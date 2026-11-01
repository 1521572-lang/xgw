# Проверка XGW 0.2.0: волна 1 кросс-аудита — пробы, события, отпечатки серверов

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, делаешь **снимок
  экрана** и смотришь на него, выполняешь JavaScript в консоли страницы.

Одна сессия, около полутора часов (из них 30 минут — ожидание). Режим бесплатных серверов в этой
проверке **не трогается** — дом всё время идёт через подписку.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J1, J2) — выполни её в
   консоли страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-a6/…`. Время шага — по выводу `date` в команде,
   не по памяти.
5. **Метка времени — до нажатия.** Где в шаге есть команда «Метка», выполни её **перед**
   нажатием в браузере, а команду проверки — **после**.
6. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
7. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
8. Экземпляр этого ТЗ держи в `$HOME/xgw-a6/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2.
9. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `a6check.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
10. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши
    дословно строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
    «Наблюдения», со словом «предположение».

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.31 и sing-box
1.14.4, принятые шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 280) и зачем проверка

Внешний кросс-аудит нашёл ошибки в том, как шлюз судит о серверах. Исправлено:

1. **Пробы.** Ответ «частями» (chunked), оборванный посередине, раньше считался целым, а байты
   разметки — телом. Обрыв соединения посреди ответа превращался в «не подключился» (без кода и
   байт) — теперь это отдельный итог `BODY_RESET` («обрывается»), с кодом и числом байт до
   обрыва, и для обхода блокировок он значит то же, что «заморозка». Сброс соединения до начала
   ответа — повод повторить пробу другим проверочным хостом. Срок пробы теперь общий для
   соединения, рукопожатия и загрузки.
2. **События.** Сигнал «правила XGW изменились» больше не теряется ни в окне собственной
   загрузки правил, ни в буре событий сети.
3. **Отпечатки серверов.** Раньше, когда в подписке рядом с сервером появлялся «близнец» (тот же
   адрес и ключ, другой путь или SNI), у сервера менялся отпечаток — и терялись его выбор
   вручную, замеры и итоги проверок. Теперь отпечаток сервера от соседей не зависит; история
   выдачи — в `/var/lib/xgw/fingerprints.json` (только хеши). При обновлении отпечатки должны
   остаться прежними.
4. **Проба профиля обхода** решается загрузкой файла пробы целиком, а не случайной его частью.

### Как проверяется

- **Отпечатки (§2, §4).** Помощник снимает список отпечатков серверов до установки, после неё и
  после кнопки «Обновить» (подписки скачиваются заново) — списки должны совпасть. Выбор вручную
  сервера подписки должен держаться. История отпечатков — только хеши, права 600.
- **Пробы (§3).** Одна проба основного сервера командой `xgw probe` и 30 минут штатных сканов:
  вердикты, длительность, обрывы и паузы проверочных хостов — из журнала.
- **События (§5, по согласию).** Помощник удаляет таблицу правил `ip xgw` — шлюз должен
  вернуть её сам примерно за секунду.

### Главное правило безопасности

Пропал интернет на машине, заказчик говорит, что пропал доступ, или не отвечает на вопрос
**2 минуты** — **сразу** раздел «Если что-то пошло не так».

### Что где на экране панели (для снимков)

- **Верх страницы**: справа — **метка состояния** («Серверы в порядке» и т. п.).
- **Правая колонка**: вкладки **«Подписки»** и **«Бесплатные серверы»**. На вкладке «Подписки»
  вверху справа — кнопка **«Обновить»**.

### Проверки JavaScript (в консоли страницы панели)

- **J1 — метка вверху:**
  `(() => { const c = document.getElementById("chip"); return [c.tagName, c.textContent.trim(), c.disabled].join(" | "); })()`
- **J2 — кнопка «Обновить»:**
  `(() => { const b = document.getElementById("refresh"); return [b.textContent.trim(), b.hidden, b.disabled, b.offsetParent !== null].join(" | "); })()`

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, `reboot`, сон машины —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh` — кроме `sudo systemctl start xgw` в разделе «Если что-то пошло не так».
  Ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`, `apt`;
  команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`. `sudo xgw pool …` (кроме
  `sudo xgw pool` без аргументов в шаге 1.3), `sudo xgw pin`, `sudo xgw unpin` — **никогда**.
  `sudo xgw probe` — только в шаге 3.1 и только с тегом из команды шага.
- Режим помощника, который меняет состояние, — `rulesdrop`: только в шаге 5.2 и только при
  согласии заказчика на пункт 4.
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`). Загрузок из терминала нет.
  Сайты источников, YouTube, сайты проверки IP, страны и скорости — **не открывать**.
- В панели нажимать **только** то, что написано в шагах: вкладку «Подписки» и кнопку «Обновить»
  (один раз, шаг 4.2). **Не нажимать**: кнопку питания, «Замерить скорость», «Проверить
  запасные», «Опросить источники», «Выбрать» и «Автовыбор» (у любых серверов), «Весь дом через
  бесплатные», «Выключить», «Включить наблюдение», переключатели Tailscale, «Ядра», «Проверить
  сеть», строки устройств, «Добавить», «Убрать».
- Править `/etc/xgw`, `/opt/xgw`, `/var/lib/xgw`, `/run/xgw`, `/etc/systemd`, код XGW. Печатать
  `config.toml`, `panel.json`, рабочие конфиги Xray и sing-box, `inventory.json`,
  `fingerprints.json`, базу `/var/lib/xgw/state.db`, полный вывод `sudo xgw pool` и
  `sudo xgw traffic`, вывод `nft list ruleset`. Коммитить что-либо, кроме файла отчёта (§7).
  Снимки экрана в git не добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, токен из ссылки
  панели, MAC, имена пользователей (→ `<user>`), внешние IP, адреса и домены подписок, IP,
  домены и ссылки серверов VPN, строки журнала. Можно: коды стран, теги вида `proxy-nl-8763`,
  скорости, вердикты, числа байт и секунд, строки помощника (хосты в них уже скрыты), надписи
  панели без имён, счётчики, статусы, времена.

## 1. Подготовка

Шаг 1.0. Предусловие — прошлая проверка закончена, хвостов нет:

```bash
cd ~/zcod/xgw && git fetch -q && git log origin/freepool --format=%s | grep -ci 'youtube через сервер — третий прогон'; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3; sudo test -e /etc/xgw/config.toml.ytbak && echo "копия настроек ЕСТЬ" || echo "копии настроек нет"; cd ~
```

Ожидается: `1` или больше (отчёт прошлой проверки); «0 timers listed»; «копии настроек нет».

Если не так: первая строка `0` — **стоп**, сообщить заказчику. Таймер в списке или «копия
настроек ЕСТЬ» — **стоп**, сообщить заказчику (прошлая проверка не закончена).

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю исправления по внешнему аудиту: как шлюз проверяет серверы, следит за правилами сети и
опознаёт серверы подписки. Режим бесплатных серверов не трогаю, дом всё время идёт через
подписку. Нажатия в панели и осмотр экрана я делаю сам, в управляемом браузере. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Одна проверка основного сервера командой (около 60 КБ через него).
(3) Кнопка «Обновить» в панели: подписки скачаются заново; если в них что-то изменилось, шлюз
пересоберёт список серверов — интернет при этом не пропадает.
(4) Я удалю таблицу правил XGW, чтобы проверить, что шлюз сам вернёт её за секунду. На эту
секунду устройства дома могут пойти в интернет мимо VPN. Можно отказаться — это необязательно.
(5) 30 минут наблюдения: я ничего не меняю, только читаю журнал.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — пропустить шаг 3.1. Против 3 — пропустить §4. Против 4 —
пропустить §5. Против 5 — пропустить шаг 3.2. **Запиши, на что согласился заказчик.**

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-a6" && chmod 700 "$HOME/xgw-a6" && cd "$HOME/xgw-a6" && cat > a6check.py <<'EOF'
"""XGW 0.2.0: волна 1 кросс-аудита (пробы, события, отпечатки серверов) — помощник проверки.
Читает состояние XGW (/run/xgw), список серверов и историю отпечатков (/var/lib/xgw — из них
только отпечатки, это хеши), базу событий (только чтение) и журнал со стандартного ввода;
печатает теги, вердикты, счётчики и да/нет — без имён серверов, устройств и подписок, адресов,
ссылок и ключей; имена хостов в причинах скрыты. Состояние меняет только режим rulesdrop (шаг
5.2, по согласию заказчика): удаляет таблицу ip xgw и ждёт, пока шлюз вернёт её сам. Время —
секунды с 1970 (date +%s). Режимы: units, state, sub, maintag, fpsnap ИМЯ, fpdiff ИМЯ ИМЯ,
fphist, invwait С [ПРЕДЕЛ], rulesdrop, events С, log."""
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
LIB = os.environ.get("A6CHECK_LIB", "/opt/xgw/lib")
NAME = re.compile("«[^»]*»")
HOST = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)
HEX8 = re.compile(r"[0-9a-f]{8}")
HEX16 = re.compile(r"[0-9a-f]{16}")
SCAN = re.compile(r"скан (\S+): ([A-Z_]+), (\d+) байт за ([\d.]+) с")
PAUSE = re.compile(r"проверочный хост \S+ не отвечает \((.*)\) — пропускаю")


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


def arg(index, default):
    try:
        return float(sys.argv[index])
    except (IndexError, ValueError):
        return default


def stamp(ts):
    return time.strftime("%d.%m %H:%M:%S", time.localtime(ts))


def masked(text):
    return HOST.sub("<хост>", NAME.sub("«<сервер>»", text))


def comma(value):
    return f"{value:.1f}".replace(".", ",")


def status_of(paths):
    loaded = read_json(paths.status_file)
    return loaded if isinstance(loaded, dict) else {}


def inventory(paths):
    data = read_json(paths.var / "inventory.json")
    data = data if isinstance(data, dict) else {}
    servers = data.get("servers") if isinstance(data.get("servers"), list) else []
    found = sorted({str(item.get("fingerprint")) for item in servers
                    if isinstance(item, dict) and item.get("fingerprint")})
    saved = data.get("saved")
    return found, saved if isinstance(saved, (int, float)) else None


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
elif mode == "state":
    _cfg, paths = xgw()
    status = status_of(paths)
    pool = status.get("free_pool") if isinstance(status.get("free_pool"), dict) else {}
    print(f"состояние шлюза: {status.get('state')}; режим пула: {pool.get('mode') or 'off'}")
elif mode in ("sub", "maintag"):
    _cfg, paths = xgw()
    status = status_of(paths)
    main = status.get("main") if isinstance(status.get("main"), dict) else {}
    pin = status.get("pin") if isinstance(status.get("pin"), dict) else {}
    if mode == "maintag":
        print(main.get("tag") or "нет")
        sys.exit(0)
    print(f"основной сервер: {main.get('tag') or 'нет'}")
    print("выбран вручную: " + ("нет" if not pin.get("tag") else f"{pin.get('tag')} — "
                                + ("не отвечает, ведёт автовыбор" if pin.get("down")
                                   else "держится")))
elif mode == "fpsnap":
    _cfg, paths = xgw()
    name = sys.argv[2] if len(sys.argv) > 2 else "now"
    found, saved = inventory(paths)
    Path(f"fp-{name}.txt").write_text("".join(f"{item}\n" for item in found), encoding="utf-8")
    age = f"{time.time() - saved:.0f} с назад" if saved is not None else "—"
    print(f"отпечатков в списке серверов: {len(found)}; список сохранён шлюзом {age}; снимок: "
          f"fp-{name}.txt")
elif mode == "fpdiff":
    names = sys.argv[2:4]
    if len(names) < 2:
        print("нужны два имени снимков")
        sys.exit(0)
    sets = []
    for name in names:
        try:
            sets.append(set(Path(f"fp-{name}.txt").read_text(encoding="utf-8").split()))
        except OSError:
            print(f"снимка fp-{name}.txt нет")
            sys.exit(0)
    old, new = sets
    print(f"отпечатков было {len(old)}, стало {len(new)}: общих {len(old & new)}, пропало "
          f"{len(old - new)}, появилось {len(new - old)}")
elif mode == "fphist":
    _cfg, paths = xgw()
    path = paths.var / "fingerprints.json"
    if not path.exists():
        print("история отпечатков: нет")
        sys.exit(0)
    data = read_json(path)
    known = data.get("known") if isinstance(data, dict) else None
    known = known if isinstance(known, dict) else {}
    rows = [(str(base), str(digest), entry) for base, entries in known.items()
            if isinstance(entries, dict) for digest, entry in entries.items()]
    good = [row for row in rows if HEX8.fullmatch(row[0]) and HEX16.fullmatch(row[1])
            and isinstance(row[2], list) and len(row[2]) == 2
            and HEX8.fullmatch(str(row[2][0])) and isinstance(row[2][1], (int, float))]
    own = sum(1 for base, _digest, entry in good if entry[0] != base)
    oldest = min((entry[1] for _base, _digest, entry in good), default=None)
    print(f"история отпечатков: есть; права {oct(path.stat().st_mode & 0o777)[2:]}; базовых "
          f"{len(known)}, вариантов {len(rows)}, со своим отпечатком варианта {own}; все записи — "
          f"хеши: {'да' if len(good) == len(rows) else 'НЕТ'}" + (
              f"; самая старая запись {(time.time() - oldest) / 3600:.1f} ч назад"
              if oldest is not None else ""))
elif mode == "invwait":
    _cfg, paths = xgw()
    since, limit = arg(2, time.time()), arg(3, 300)
    print(f"жду обновления списка серверов (до {limit:.0f} с)…", flush=True)
    start = time.time()
    while True:
        _found, saved = inventory(paths)
        if saved is not None and saved >= since:
            print(f"список серверов обновлён: +{saved - since:.0f} с от метки")
            break
        if time.time() - start > limit:
            print(f"за {limit:.0f} с список серверов не обновлялся")
            break
        time.sleep(3)
elif mode == "rulesdrop":
    _cfg, paths = xgw()
    if run(["nft", "list", "table", "ip", "xgw"])[0] != 0:
        print("таблицы ip xgw нет — удалять нечего")
        sys.exit(0)
    began = time.time()
    code, _out = run(["nft", "delete", "table", "ip", "xgw"])
    if code != 0:
        print(f"таблица ip xgw не удалена (код {code})")
        sys.exit(0)
    print(f"таблица ip xgw удалена в {stamp(began)}", flush=True)
    back = None
    while time.time() - began < 15:
        if run(["nft", "list", "table", "ip", "xgw"])[0] == 0:
            back = time.time() - began
            break
        time.sleep(0.1)
    print(f"таблица ip xgw вернулась через {comma(back)} с" if back is not None
          else "таблица ip xgw НЕ вернулась за 15 с")
    time.sleep(3)
    found = [(ts, detail) for ts, kind, detail in events_since(paths, began - 1)
             if kind == "capture"]
    print(f"событий перехвата с удаления: {len(found)}")
    for ts, detail in found[:5]:
        print(f"  {stamp(ts)}: {masked(detail)}")
elif mode == "events":
    _cfg, paths = xgw()
    found = events_since(paths, arg(2, time.time() - 3600))
    print(f"событий: {len(found)}" + ("; последние 30:" if len(found) > 30 else ""))
    for ts, kind, detail in found[-30:]:
        print(f"{stamp(ts)} {kind}: {masked(detail)}")
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    scans = [match for match in (SCAN.search(line) for line in lines) if match]
    counts: dict[str, int] = {}
    for match in scans:
        counts[match.group(2)] = counts.get(match.group(2), 0) + 1
    longest = max((float(match.group(4)) for match in scans), default=0.0)
    print(f"строк журнала: {len(lines)}")
    print(f"сканов: {len(scans)}" + (": " + ", ".join(
        f"{verdict} {count}" for verdict, count in sorted(counts.items())) if counts else "")
        + f"; самый долгий: {comma(longest)} с")
    cut = [match.group(3) for match in scans if match.group(2) == "BODY_RESET"]
    print(f"обрывов посреди ответа (BODY_RESET): {len(cut)}"
          + (f"; байт до обрыва: {', '.join(cut[:10])}" if cut else ""))
    pauses = [match.group(1) for match in (PAUSE.search(line) for line in lines) if match]
    print(f"пауз проверочных хостов: {len(pauses)}"
          + (f"; причины: {'; '.join(sorted({masked(item) for item in pauses})[:3])}"
             if pauses else ""))
    slow = [line for line in lines if "шаг watchdog занял" in line]
    longest_step = max(slow, key=lambda line: int(
        (re.search(r"занял (\d+) с", line) or [0, "0"])[1]), default="")
    found = re.search(r"занял (\d+) с[^(]*(\(.*\))?", longest_step)
    print(f"долгих шагов демона: {len(slow)}" + (
        f"; самый долгий: {found.group(1)} с {found.group(2) or ''}" if found else ""))
    for label, word in (
        ("правила загружены заново", "загружены заново"),
        ("откат на last-good", "last-good"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | state | sub | maintag | fpsnap ИМЯ | fpdiff ИМЯ ИМЯ | fphist | "
          "invwait С [ПРЕДЕЛ] | rulesdrop | events С | log")
EOF
python3 -c "import hashlib;d=open('a6check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `6d411121cf5c82d5`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки и снимок отпечатков старым кодом:

```bash
cd "$HOME/xgw-a6" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units state sub fphist; do sudo python3 -I a6check.py $m; done | tee -a before.txt; sudo python3 -I a6check.py fpsnap before | tee -a before.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4; первая строка
`xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение …» — **записать, какая**; четыре
службы `active`; `state` — «состояние шлюза: HEALTHY; режим пула: off» (или `observe`);
`sub` — **записать** (основной и выбран ли сервер вручную); `fphist` — «история отпечатков:
нет» (старый код её не пишет); `fpsnap` — «отпечатков в списке серверов: N; …» — **записать N**.

Если не так: режим пула `on` — **стоп**, сообщить заказчику (весь дом через бесплатные — эта
проверка его не трогает). `fphist` — «есть…» — записать (не стоп).

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q '^class _Chunked' src/xgw/watch/checks.py && grep -q '"BODY_RESET"' src/xgw/watch/scan.py && grep -q '^def _variant_fingerprint' src/xgw/model.py && grep -q '_dropped_lock' src/xgw/watch/events.py && echo "правка в коде: есть"; cd "$HOME/xgw-a6"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-a6/install-time.txt" && date +%s > "$HOME/xgw-a6/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-a6/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-a6/install.txt"; cd "$HOME/xgw-a6"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Список серверов после установки (до 5 минут) и отпечатки:

```bash
cd "$HOME/xgw-a6" && sudo python3 -I a6check.py invwait "$(cat t-install.txt)" 300 | tee after-install.txt; sleep 20; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a after-install.txt; for m in units state sub fphist; do sudo python3 -I a6check.py $m; done | tee -a after-install.txt; sudo python3 -I a6check.py fpsnap install | tee -a after-install.txt; sudo python3 -I a6check.py fpdiff before install | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I a6check.py log | tee log-install.txt
```

Ожидается:
- `invwait` — «список серверов обновлён: +N с от метки» (демон после запуска скачал подписки);
- `HEALTHY` (или ещё `DEGRADED` — тогда см. «Если не так»), перехват включён, строки «Ожидает
  окна перезапуска» нет; четыре службы `active`;
- `sub` — тот же основной или другой (основной шлюз выбирает заново — не дефект), а **«выбран
  вручную» — как в шаге 1.3** (тот же тег, «держится»);
- `fphist` — «история отпечатков: есть; права 600; базовых N, вариантов M, со своим отпечатком
  варианта K; все записи — хеши: да» — **записать строку**;
- `fpdiff` — «отпечатков было N, стало N: общих N, пропало 0, появилось 0» — **записать
  строку** (главная проверка: обновление не сменило отпечатки);
- журнал: «Traceback: 0», «откат на last-good: 0»; «долгих шагов демона» — записать строку.

Если не так: `invwait` — «за 300 с … не обновлялся» — подожди 3 минуты и выполни
`sudo python3 -I a6check.py fpsnap install; sudo python3 -I a6check.py fpdiff before install`,
запиши. Не `HEALTHY` — подожди 2 минуты, повтори `sudo python3 -I a6check.py state`; снова нет —
запиши и продолжай. «выбран вручную» стал другим или «нет» — **дефект «потерян выбор
вручную»**: записать обе строки. `fpdiff` — «пропало» или «появилось» больше 0 — **не по
ожиданию**: записать строку (подписка могла и правда измениться — это проверит §4).

## 3. Пробы

Шаг 3.1. Одна проба основного сервера (если заказчик согласился на пункт 2):

```bash
cd "$HOME/xgw-a6" && T="$(sudo python3 -I a6check.py maintag)" && echo "основной: $T" | tee probe.txt && sudo xgw probe "$T" 2>&1 | tail -3 | tee -a probe.txt
```

Ожидается: «основной: proxy-XX-…»; строка `proxy-XX-…  OK` (или `SLOW`) `N Б за T с` — N
больше 40000, T меньше 30 — **записать строку** (без хвоста с ошибкой, если он есть, — его
записать отдельно, хосты скрыть).

Если не так: «основной: нет» — шаг пропустить, записать. Вердикт не `OK`/`SLOW` — **записать
строку целиком** (с `BODY_RESET` — отметить: это новый итог «обрыв посреди ответа»); не стоп.

Шаг 3.2. 30 минут штатных сканов (если заказчик согласился на пункт 5):

```bash
sleep 1800; cd "$HOME/xgw-a6" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I a6check.py log | tee log-scans.txt; sudo python3 -I a6check.py events "$(cat t-install.txt)" | tee events-scans.txt
```

(Если терминал обрывает длинные команды — `sleep 110` 17 раз, затем команда без `sleep`.)

Ожидается:
- `сканов: N: OK …, SLOW …, …` — N больше 0; **записать строку целиком**; «самый долгий» —
  меньше 61 с;
- «обрывов посреди ответа (BODY_RESET): K» — **записать** (0 — тоже результат; больше 0 —
  записать и байты до обрыва);
- «пауз проверочных хостов: P» — записать (с причинами, если есть);
- «Traceback: 0», «откат на last-good: 0»;
- `events` — записать число и строки (хосты и имена в них скрыты).

Если не так: «сканов: 0» — подожди ещё 15 минут и повтори вторую половину команды (без
`sleep`); снова 0 — записать «не по ожиданию». «самый долгий» 61 с и больше — **дефект «проба
дольше общего срока»**: записать строку.

## 4. Отпечатки после «Обновить» (если заказчик согласился на пункт 3)

Шаг 4.1. Панель. Ссылка входа (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком (окно не меньше 1280×800),
подожди 5 секунд, нажми вкладку **«Подписки»** (если она уже открыта — не нажимай), подожди 3
секунды, снимок; **J1** и **J2**.

Ожидается: J1 — `SPAN | Серверы в порядке | false` или `BUTTON | …` — записать дословно; J2 —
`Обновить | false | false | true`.

Если не так: J2 — `… | true | …` (кнопка скрыта или занята) — подожди 30 секунд, обнови
страницу (F5) и повтори J2; снова не так — §4 пропустить, записать.

Шаг 4.2. Обновление подписок.
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-a6" && date +%s > t-refresh.txt && echo "метка записана: $(date '+%T')"
```

2. Нажми **«Обновить»** (вкладка «Подписки», вверху справа). Снимок.
3. **Сразу** выполни (до 6 минут):

```bash
cd "$HOME/xgw-a6" && sudo python3 -I a6check.py invwait "$(cat t-refresh.txt)" 300 | tee refresh.txt; sleep 30; for m in state sub fphist; do sudo python3 -I a6check.py $m; done | tee -a refresh.txt; sudo python3 -I a6check.py fpsnap refresh | tee -a refresh.txt; sudo python3 -I a6check.py fpdiff install refresh | tee -a refresh.txt; sudo python3 -I a6check.py fpdiff before refresh | tee -a refresh.txt
```

Ожидается: «список серверов обновлён: +N с от метки» (N — до 120); `state` — `HEALTHY`; `sub` —
«выбран вручную» как в шаге 1.3; `fphist` — «… все записи — хеши: да»; `fpdiff install refresh`
— «пропало 0, появилось 0»; `fpdiff before refresh` — **записать строку**.

Если не так: «за 300 с … не обновлялся» — **не по ожиданию**: записать, снимок панели; не стоп.
`fpdiff install refresh` — «пропало» или «появилось» больше 0 — записать строку и выполни
`sudo python3 -I a6check.py events "$(cat t-refresh.txt)" | tee events-refresh.txt` (события
подписок — ушли ли серверы из подписки на самом деле).

## 5. Пропажа правил (если заказчик согласился на пункт 4)

Шаг 5.1. **Скажи заказчику** (дословно): «Удаляю таблицу правил XGW — шлюз должен вернуть её сам
примерно за секунду.»

Шаг 5.2. Удаление и возврат:

```bash
cd "$HOME/xgw-a6" && date +%s > t-rules.txt && sudo python3 -I a6check.py rulesdrop | tee rules.txt; sleep 10; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee -a rules.txt; sudo python3 -I a6check.py state | tee -a rules.txt
```

Ожидается: «таблица ip xgw удалена в …»; «таблица ip xgw вернулась через N,N с» — N не больше 3;
«событий перехвата с удаления: 1» (или больше) и строка «правила сети не были загружены —
загружены заново» (или похожая — записать дословно); через 10 секунд `HEALTHY`, перехват
включён.

Если не так: «НЕ вернулась за 15 с» — **сразу** раздел «Если что-то пошло не так», это
**дефект**. «вернулась через» больше 3 с — **дефект «правила возвращаются медленно»**: записать
строку.

## 6. Секреты и итог

Шаг 6.1. Секреты:

```bash
cd "$HOME/xgw-a6" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt
```

Ожидается: `0`. Больше — **дефект** (строки журнала в отчёт не копировать).

Шаг 6.2. Итог:

```bash
cd "$HOME/xgw-a6" && date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units state sub fphist; do sudo python3 -I a6check.py $m; done | tee -a final.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I a6check.py log | tee log-final.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4, строки «Ожидает окна
перезапуска» нет; четыре службы `active`; режим пула — как в шаге 1.3; «выбран вручную» — как в
шаге 1.3; журнал: «откат на last-good: 0», «Traceback: 0», «долгих шагов демона» — записать.

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- Пропал интернет или доступ, или заказчик не отвечает **2 минуты** — **сразу**: если
  `systemctl is-active xgw` — не `active`, то `sudo systemctl start xgw`; подожди 30 секунд;
  `sudo nft list table ip xgw >/dev/null && echo "таблица есть" || echo "таблицы НЕТ"`. Записать
  время и строки `sudo python3 -I a6check.py state` и `sudo xgw status 2>&1 | head -5` (без
  имён). Таблицы нет и через минуту — сообщить заказчику, больше ничего не делать. Дальше — §6 и
  отчёт.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.
- Браузер не открывает панель или кнопки не нажимаются — снимок, сообщить заказчику и попросить
  нажать то же самое вручную; в отчёте пометить «нажато заказчиком».

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit6-<ДАТА>.md` в клоне (`<ДАТА>` — дата начала
проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, волна 1 кросс-аудита» и `git push` в
`freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и подписок,
адресов, доменов, токена и строк журнала. Шаблон (заполни каждую ячейку; пропущенное — «не
выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — волна 1 кросс-аудита (пробы, события, отпечатки)

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
a6check.py: <сумма>. Режим пула до проверки: <…>. Ядра: Xray <…>, sing-box <…>. Исполнитель:
<модель>; нажатия и снимки — управляемым браузером <да/частично>.

## Итог
| Отпечатки: до → после установки → после «Обновить» (пропало/появилось) | Выбор вручную держится | История отпечатков (права, хеши) | Проба основного (вердикт, байт, с) | Сканы 30 мин (вердикты; самый долгий; BODY_RESET; паузы хостов) | Правила вернулись через (с) |
|---|---|---|---|---|---|
| <0/0 → 0/0> | <да> | <600, да> | <OK, 57620, 1,2> | <OK 40, SLOW 3; 14,2 с; 0; 0> | <0,4> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.0 предусловие | … | … |
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки, отпечатки | … | … |
| 3.1 проба основного | … | … |
| 3.2 сканы 30 мин | … | … |
| 4.1 панель | … | … |
| 4.2 «Обновить», отпечатки | … | … |
| 5.2 пропажа правил | … | … |
| 6 секреты и итог | … | … |

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-a6/…); результаты J1, J2; что видно на
  снимках словами; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
