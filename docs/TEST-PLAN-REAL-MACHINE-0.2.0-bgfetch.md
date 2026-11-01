# Проверка XGW 0.2.0: опрос подписок вне шага демона

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, делаешь **снимок
  экрана** и смотришь на него, выполняешь JavaScript в консоли страницы.

Одна сессия, около часа (из них около 25 минут — ожидание). Режим бесплатных серверов в этой
проверке **не трогается** — дом всё время идёт через подписку.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J2, J3) — выполни её в консоли
   страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-bf/…`. Время шага — по выводу `date` в
   команде, не по памяти.
5. **Метка времени — до нажатия.** Где в шаге есть команда «Метка», выполни её **перед**
   нажатием в браузере, а команду слежения — **сразу после** нажатия и снимка, не делая ничего
   между ними.
6. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
7. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
8. Экземпляр этого ТЗ держи в `$HOME/xgw-bf/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2. Это **новый** помощник (`bfcheck.py`), не тот, что в прошлых
   проверках.
9. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `bfcheck.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
10. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши
    дословно строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
    «Наблюдения», со словом «предположение».

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.31 и sing-box
1.14.4, принятые шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 283) и зачем проверка

Прошлые проверки показали: шаг демона с обновлением подписки длится 90–135 секунд (опрос подписки
37–68 с, сборка конфига 1–39 с, применение 7–9 с). Всё это время демон не следил за серверами:
не замечал упавших, не сканировал запасные, не обновлял состояние в панели. Теперь опрос подписки
идёт **в фоне**: шаги демона в это время идут как обычно (раз в ~20 секунд), а новый список
серверов применяет первый шаг после конца опроса. Сборка и применение остались в шаге.

Ещё одно следствие, которое проверяется: после перезапуска демона (установка) список серверов
подписки приходит не в первом шаге, а через минуту-полторы — первый круг сканов запасных должен
пойти, как только он пришёл, а не через час.

Ожидания этой проверки:
1. В журнале — строка о начале опроса («опросов подписок начато: N» у помощника), а **во время
   опроса** состояние шлюза записывается (помощник: «шаги демона во время опроса шли»).
2. **Долгих шагов демона из-за опроса подписки нет** (помощник: «из них с опросом подписки внутри
   шага: 0»).
3. После установки первый скан запасного — **не позже 15 минут** после запуска демона.
4. Состояние, ручной выбор сервера и службы — как до проверки; ошибок (`Traceback`) нет.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, `reboot`, сон машины —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh` — кроме `sudo systemctl start xgw` в разделе «Если что-то пошло не так».
  Ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`, `apt`;
  команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`. `sudo xgw pool …` (кроме
  `sudo xgw pool` без аргументов в шаге 1.3), `sudo xgw pin`, `sudo xgw unpin`, `sudo xgw probe`
  — **никогда**.
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`). Загрузок из терминала нет.
  Сайты источников, YouTube, сайты проверки IP, страны и скорости — **не открывать**.
- В панели нажимать **только** то, что написано в шагах: вкладку «Подписки» и кнопку «Обновить»
  (два раза: шаги 3.2 и 3.3). **Не нажимать**: кнопку питания, «Замерить скорость», «Проверить
  запасные», «Опросить источники», «Выбрать» и «Автовыбор» (у любых серверов), «Весь дом через
  бесплатные», «Выключить», «Включить наблюдение», переключатели Tailscale, «Ядра», «Проверить
  сеть», строки устройств, «Добавить», «Убрать».
- Править `/etc/xgw`, `/opt/xgw`, `/var/lib/xgw`, `/run/xgw`, `/etc/systemd`, код XGW. Печатать
  `config.toml`, `panel.json`, `status.json`, рабочие конфиги Xray и sing-box, файлы кэша
  подписок (`/var/lib/xgw/cache`), `inventory.json`, `fingerprints.json`, базу
  `/var/lib/xgw/state.db`, полный вывод `sudo xgw pool` и `sudo xgw traffic`, вывод
  `nft list ruleset`. Коммитить что-либо, кроме файла отчёта (§6). Снимки экрана в git не
  добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, токен из ссылки
  панели, MAC, имена пользователей (→ `<user>`), внешние IP, адреса и домены подписок, IP,
  домены и ссылки серверов VPN, строки журнала. Можно: коды стран, теги вида `proxy-nl-8763`,
  вердикты, числа байт и секунд, строки помощника, надписи панели без имён, счётчики, статусы,
  времена.

## 1. Подготовка

Шаг 1.0. Предусловие — прошлая проверка закончена:

```bash
cd ~/zcod/xgw && git fetch -q && git log origin/freepool --format=%s | grep -ci 'отпечатки одиночных серверов'; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3; cd ~
```

Ожидается: `1` или больше (отчёт прошлой проверки); «0 timers listed».

Если не так: первая строка `0` — **стоп**, сообщить заказчику.

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю исправление: раз в час, пока шлюз скачивал подписку, он полторы-две минуты не следил
за серверами. Теперь подписка скачивается в фоне. Режим бесплатных серверов не трогаю, дом всё
время идёт через подписку. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Два раза кнопка «Обновить» в панели (с перерывом в 5 минут): подписка скачается заново —
интернет при этом не пропадает.
(3) 10 минут наблюдения: я ничего не меняю, только читаю журнал.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — пропустить §3. Против 3 — пропустить шаг 4.1. **Запиши,
на что согласился заказчик.**

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-bf" && chmod 700 "$HOME/xgw-bf" && cd "$HOME/xgw-bf" && cat > bfcheck.py <<'EOF'
"""XGW 0.2.0: опрос подписок вне шага демона — помощник проверки. Читает состояние XGW
(/run/xgw/status.json — состояние, режим пула, ручной выбор и время записи файла), время
сохранения списка серверов (/var/lib/xgw/inventory.json — только поле saved) и журнал со
стандартного ввода (journalctl -o short-unix). Ничего не меняет; из журнала печатает только числа
и теги серверов. Время — секунды с 1970 (date +%s). Режимы: units, state, sub, invwait С
[ПРЕДЕЛ], watch С СЕКУНД ИМЯ, log [ИМЯ]."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("BFCHECK_LIB", "/opt/xgw/lib")
STAMP = re.compile(r"^(\d+(?:\.\d+)?) ")
SCAN = re.compile(r"скан (\S+): ([A-Z_]+), (\d+) байт за ([\d.]+) с")
REFRESH = re.compile(r"обновление подписки: опрос (\d+) с, сборка (\d+) с, применение (\d+) с")
SLOW = re.compile(r"шаг watchdog занял (\d+) с")
PART = re.compile(r"подписка и сборка конфига (\d+) с")
STARTED = "опрос подписок начат"
LAUNCHED = "демон XGW запущен"


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


def status_of(paths):
    loaded = read_json(paths.status_file)
    return loaded if isinstance(loaded, dict) else {}


def saved_at(paths):
    data = read_json(paths.var / "inventory.json")
    saved = data.get("saved") if isinstance(data, dict) else None
    return saved if isinstance(saved, (int, float)) else None


def when(line):
    found = STAMP.match(line)
    return float(found.group(1)) if found else None


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
elif mode == "state":
    _cfg, paths = xgw()
    status = status_of(paths)
    pool = status.get("free_pool") if isinstance(status.get("free_pool"), dict) else {}
    print(f"состояние шлюза: {status.get('state')}; режим пула: {pool.get('mode') or 'off'}")
elif mode == "sub":
    _cfg, paths = xgw()
    pin = status_of(paths).get("pin")
    pin = pin if isinstance(pin, dict) else {}
    print("выбран вручную: " + ("нет" if not pin.get("tag") else f"{pin.get('tag')} — "
                                + ("не отвечает, ведёт автовыбор" if pin.get("down")
                                   else "держится")))
elif mode == "invwait":
    _cfg, paths = xgw()
    since, limit = arg(2, time.time()), arg(3, 300)
    print(f"жду обновления списка серверов (до {limit:.0f} с)…", flush=True)
    start = time.time()
    while True:
        saved = saved_at(paths)
        if saved is not None and saved >= since:
            print(f"список серверов обновлён: +{saved - since:.0f} с от метки")
            break
        if time.time() - start > limit:
            print(f"за {limit:.0f} с список серверов не обновлялся")
            break
        time.sleep(3)
elif mode == "watch":
    _cfg, paths = xgw()
    since, seconds = arg(2, time.time()), arg(3, 110)
    name = sys.argv[4] if len(sys.argv) > 4 else "now"
    print(f"слежу за записью состояния шлюза {seconds:.0f} с…", flush=True)
    stamps, saved = [], None
    end = time.time() + seconds
    while time.time() < end:
        try:
            written = paths.status_file.stat().st_mtime
        except OSError:
            written = None
        if written is not None and written >= since and written not in stamps:
            stamps.append(written)
        fresh = saved_at(paths)
        if saved is None and fresh is not None and fresh >= since:
            saved = fresh
        time.sleep(1)
    until = time.time()
    Path(f"st-{name}.json").write_text(json.dumps(
        {"since": since, "until": until, "stamps": stamps, "saved": saved}), encoding="utf-8")
    points = [since, *stamps, until]
    gap = max(later - earlier for earlier, later in zip(points, points[1:], strict=False))
    print(f"записей состояния шлюза: {len(stamps)}; самый долгий перерыв: {gap:.0f} с; "
          + (f"список серверов обновлён: +{saved - since:.0f} с от метки" if saved is not None
             else "список серверов за это время не обновлялся"))
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    name = sys.argv[2] if len(sys.argv) > 2 else ""
    scans = [(when(line), match) for line in lines if (match := SCAN.search(line))]
    spares = [stamp for stamp, match in scans if match.group(1).startswith("spare-")]
    print(f"строк журнала: {len(lines)}; сканов: {len(scans)}; сканов запасных: {len(spares)}")
    launched = [stamp for stamp in (when(line) for line in lines if LAUNCHED in line) if stamp]
    if launched:
        first = next((stamp for stamp in spares if stamp and stamp >= launched[-1]), None)
        print("первый скан запасного после запуска демона: "
              + (f"+{first - launched[-1]:.0f} с" if first is not None else "не было"))
    starts = [stamp for stamp in (when(line) for line in lines if STARTED in line) if stamp]
    print(f"опросов подписок начато: {len(starts)}" + (
        "" if starts else " — строки о начале опроса нет (код до выноса опроса из шага)"))
    refreshes = [(when(line), match) for line in lines if (match := REFRESH.search(line))]
    for _stamp, match in refreshes[-5:]:
        print(f"обновление подписки: опрос {match.group(1)} с, сборка {match.group(2)} с, "
              f"применение {match.group(3)} с")
    slow, inside = [], 0
    for line in lines:
        found = SLOW.search(line)
        if not found:
            continue
        slow.append(int(found.group(1)))
        part, stamp = PART.search(line), when(line)
        before = [match for at, match in refreshes if at and stamp and 0 <= stamp - at < 300]
        if part and before and int(part.group(1)) >= (
                int(before[-1].group(2)) + int(before[-1].group(3)) + 15):
            inside += 1  # часть «подписка и сборка конфига» длиннее сборки и применения
    print(f"долгих шагов демона: {len(slow)}" + (f"; самый долгий: {max(slow)} с" if slow else "")
          + f"; из них с опросом подписки внутри шага: {inside}")
    for label, word in (("откат на last-good", "last-good"), ("Traceback", "Traceback")):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
    if name:
        watched = read_json(Path(f"st-{name}.json"))
        if not isinstance(watched, dict):
            print(f"файла st-{name}.json нет — слежение (watch) не выполнялось")
            sys.exit(0)
        since, until = float(watched.get("since") or 0), float(watched.get("until") or 0)
        stamps = [float(stamp) for stamp in watched.get("stamps") or []]
        start = next((stamp for stamp in starts if stamp >= since - 5), None)
        done = next((match for at, match in refreshes
                     if start is not None and at and at >= start), None)
        if start is None:
            print("начала опроса после метки в журнале нет")
        elif done is None:
            print("строки времени обновления после начала опроса нет — подожди минуту и повтори")
        else:
            polled = int(done.group(1))
            written = [stamp for stamp in stamps if start < stamp <= start + polled]
            print(f"опрос: начат через {start - since:.0f} с после метки, шёл {polled} с; записей "
                  f"состояния шлюза за время опроса: {len(written)} — шаги демона во время опроса "
                  + ("шли" if written else "не шли")
                  + (" (слежение кончилось раньше опроса)" if until < start + polled else ""))
else:
    print("режим: units | state | sub | invwait С [ПРЕДЕЛ] | watch С СЕКУНД ИМЯ | log [ИМЯ]")
EOF
python3 -c "import hashlib;d=open('bfcheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `5cc139a00842eba0`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки:

```bash
cd "$HOME/xgw-bf" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units state sub; do sudo python3 -I bfcheck.py $m; done | tee -a before.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4; первая строка
`xgw pool` — «Бесплатный пул: выключен; …» (или «… наблюдение …») — **записать**; четыре службы
`active`; `sub` — **записать** («выбран вручную: …»).

Если не так: режим пула `on` — **стоп**, сообщить заказчику.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'опрос подписок начат' src/xgw/daemon.py && echo "правка в коде: есть"; cd "$HOME/xgw-bf"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-bf/install-time.txt" && date +%s > "$HOME/xgw-bf/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-bf/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-bf/install.txt"; cd "$HOME/xgw-bf"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Список серверов после установки (до 5 минут):

```bash
cd "$HOME/xgw-bf" && sudo python3 -I bfcheck.py invwait "$(cat t-install.txt)" 300 | tee after-install.txt
```

Ожидается: «список серверов обновлён: +N с от метки» — **записать N** (в него входят сама
установка и опрос подписки; от выноса опроса оно почти не меняется).

Если не так: «за 300 с … не обновлялся» — выполни команду ещё раз, запиши обе строки.

Шаг 2.4. Через 2,5 минуты — состояние и журнал после установки:

```bash
cd "$HOME/xgw-bf" && sleep 110; sleep 40; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Ожидает окна' | tee -a after-install.txt; for m in units state sub; do sudo python3 -I bfcheck.py $m; done | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" -o short-unix --no-pager | sudo python3 -I bfcheck.py log | tee log-install.txt
```

(Если терминал обрывает длинные команды — сначала `sleep 110`, потом `sleep 40`, потом команда
без обоих `sleep`.)

Ожидается:
- `HEALTHY`, перехват включён, строки «Ожидает окна перезапуска» нет; четыре службы `active`;
  `sub` — как в шаге 1.3;
- журнал (`log-install.txt`, записать **целиком**):
  - «опросов подписок начато: 1» (или больше);
  - строка «обновление подписки: опрос … с, сборка … с, применение … с»;
  - «долгих шагов демона: N…; из них с опросом подписки внутри шага: **0**»;
  - «первый скан запасного после запуска демона: +N с» — или «не было» (здесь это ещё не
    ошибка: окончательно — в шаге 4.1);
  - «откат на last-good: 0», «Traceback: 0».

Если не так: «опросов подписок начато: 0 — строки о начале опроса нет» — **дефект «опрос
подписок не вынесен из шага»**; сверь хеш шага 2.1 с последним коммитом ветки и запиши оба.
«из них с опросом подписки внутри шага» больше 0 — **дефект «шаг ждёт опроса подписки»**:
записать строку целиком. Не `HEALTHY` — подожди 2 минуты, повтори
`sudo python3 -I bfcheck.py state`; снова нет — запиши и продолжай.

## 3. Два обновления подписки (если заказчик согласился на пункт 2)

Шаг 3.1. Панель. Ссылка входа (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком (окно не меньше 1280×800),
подожди 5 секунд, нажми вкладку **«Подписки»** (если она уже открыта — не нажимай), подожди 3
секунды, снимок; **J2** и **J3**.

**J2 — кнопка «Обновить»:**
`(() => { const b = document.getElementById("refresh"); return [b.textContent.trim(), b.hidden, b.disabled, b.offsetParent !== null].join(" | "); })()`

**J3 — идёт ли обновление подписок:**
`(() => { const b = document.getElementById("refresh"); return [b.textContent.trim(), b.dataset.busy === "1" ? "занята" : "свободна"].join(" | "); })()`

Ожидается: J2 — `Обновить | false | false | true`; J3 — `Обновить | свободна`.

Если не так: J2 — `… | true | …` или J3 — `… | занята` — подожди 30 секунд, обнови страницу
(F5) и повтори J2 и J3; снова не так — §3 пропустить, записать.

Шаг 3.2. Первое обновление.
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-bf" && date +%s > t-r1.txt && echo "метка записана: $(date '+%T')"
```

2. Нажми **«Обновить»**. Снимок (записать всплывшую надпись).
3. **Сразу** (без J-проверок между ними) — слежение за записью состояния, 110 секунд:

```bash
cd "$HOME/xgw-bf" && sudo python3 -I bfcheck.py watch "$(cat t-r1.txt)" 110 r1 | tee r1.txt
```

Ожидается: «записей состояния шлюза: N; самый долгий перерыв: G с; список серверов обновлён: +K
с от метки» — **записать N, G и K**. N — 3 или больше.

4. **J3** в консоли панели. Ожидается: `Обновить | свободна` (обновление закончилось).
   Если `… | занята` — подожди 30 секунд, F5, повтори J3; запиши оба результата.
5. Журнал обновления:

```bash
cd "$HOME/xgw-bf" && sleep 40; sudo journalctl -u xgw --since "@$(cat t-r1.txt)" -o short-unix --no-pager | sudo python3 -I bfcheck.py log r1 | tee log-r1.txt; for m in state sub; do sudo python3 -I bfcheck.py $m; done | tee -a log-r1.txt
```

Ожидается (записать **целиком**):
- «опросов подписок начато: 1»;
- «обновление подписки: опрос N с, сборка M с, применение K с»;
- «долгих шагов демона: 0…; из них с опросом подписки внутри шага: 0» (если долгие шаги есть —
  записать строку; дефект — только если «с опросом … внутри шага» больше 0);
- последняя строка помощника: «опрос: начат через A с после метки, шёл N с; записей состояния
  шлюза за время опроса: X — **шаги демона во время опроса шли**» (X — обычно 2–3);
- G из пункта 3 **меньше** суммы «опрос + сборка + применение» этой строки (до выноса опроса шаг
  ждал всё это время); `HEALTHY`; `sub` — как в шаге 1.3.

Если не так: «строки времени обновления после начала опроса нет» — `sleep 60` и повтори команду
без `sleep 40`. «шаги демона во время опроса **не шли**» — **дефект «шаг ждёт опроса подписки»**,
кроме случая, когда в той же строке есть «(слежение кончилось раньше опроса)» — тогда это не
дефект, запиши строку. «начала опроса после метки в журнале нет» — записать, снимок панели.
G **не меньше** суммы — записать оба числа, «не по ожиданию».

Шаг 3.3. Через 5 минут — второе обновление.
1. Подожди 5 минут: `sleep 300` (или `sleep 110` три раза). Затем **метка**:

```bash
cd "$HOME/xgw-bf" && date +%s > t-r2.txt && echo "метка записана: $(date '+%T')"
```

2. Нажми **«Обновить»** ещё раз. Снимок.
3. **Сразу** — слежение:

```bash
cd "$HOME/xgw-bf" && sudo python3 -I bfcheck.py watch "$(cat t-r2.txt)" 110 r2 | tee r2.txt
```

4. **J3** — как в шаге 3.2.
5. Журнал:

```bash
cd "$HOME/xgw-bf" && sleep 40; sudo journalctl -u xgw --since "@$(cat t-r2.txt)" -o short-unix --no-pager | sudo python3 -I bfcheck.py log r2 | tee log-r2.txt; for m in state sub; do sudo python3 -I bfcheck.py $m; done | tee -a log-r2.txt
```

Ожидается и «Если не так»: как в шаге 3.2 (опрос во второй раз бывает короче — 30–40 с; записей
состояния за него тогда 1–2).

## 4. Наблюдение (если заказчик согласился на пункт 3)

Шаг 4.1. 10 минут после второго обновления:

```bash
sleep 600; cd "$HOME/xgw-bf" && sudo journalctl -u xgw --since "$(cat install-time.txt)" -o short-unix --no-pager | sudo python3 -I bfcheck.py log | tee log-watch.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Ожидает окна' | tee -a log-watch.txt
```

(Если терминал обрывает длинные команды — `sleep 110` 5 раз и `sleep 50`, затем команда без
`sleep`.)

Ожидается (записать **целиком**): «сканов запасных: M» — M **больше 0**; «первый скан запасного
после запуска демона: +N с» — N **не больше 900**; «опросов подписок начато: 3» (или больше, если
подошёл срок обычного обновления); «из них с опросом подписки внутри шага: 0»; «откат на
last-good: 0»; «Traceback: 0»; `HEALTHY`.

Если не так: «первый скан запасного … не было» или N больше 900 — **дефект «сканы запасных после
запуска демона отложены»**: записать строку. «Traceback» больше 0 — **дефект**: записать число
(сами строки журнала не переписывать).

## 5. Итог

Шаг 5.1. Секреты и итог:

```bash
cd "$HOME/xgw-bf" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt; date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units state sub; do sudo python3 -I bfcheck.py $m; done | tee -a final.txt
```

Ожидается: `0`; `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4, строки «Ожидает
окна перезапуска» нет; четыре службы `active`; режим пула и «выбран вручную» — как в шаге 1.3.

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- Пропал интернет или доступ, или заказчик не отвечает **2 минуты** — **сразу**: если
  `systemctl is-active xgw` — не `active`, то `sudo systemctl start xgw`; подожди 30 секунд.
  Записать время и строки `sudo python3 -I bfcheck.py state` и `sudo xgw status 2>&1 | head -5`
  (без имён). Дальше — §5 и отчёт.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.
- Браузер не открывает панель или кнопки не нажимаются — снимок, сообщить заказчику и попросить
  нажать то же самое вручную; в отчёте пометить «нажато заказчиком».

## 6. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-bgfetch-<ДАТА>.md` в клоне (`<ДАТА>` — дата начала
проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, опрос подписок в фоне» и `git push` в
`freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и подписок,
адресов, доменов, токена и строк журнала. Шаблон (заполни каждую ячейку; пропущенное — «не
выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — опрос подписок вне шага демона

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
bfcheck.py: <сумма>. Режим пула до проверки: <…>. Ядра: Xray <…>, sing-box <…>. Исполнитель:
<модель>; нажатия и снимки — управляемым браузером <да/частично>.

## Итог
| Шаги во время опроса: записей состояния (r1 / r2) | Долгих шагов с опросом внутри (установка / r1 / r2 / наблюдение) | Перерыв записи состояния G, с (r1 / r2) | Опрос / сборка / применение, с (установка / r1 / r2) | Список после установки, с от метки | Первый скан запасного после запуска |
|---|---|---|---|---|---|
| <3 / 2> | <0 / 0 / 0 / 0> | <45 / 38> | <68/39/7; 67/21/8; 37/1/8> | <+95> | <+160 с> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.0 предусловие | … | … |
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 список после установки | … | … |
| 2.4 журнал после установки | … | … |
| 3.1 панель | … | … |
| 3.2 обновление 1 | … | … |
| 3.3 обновление 2 | … | … |
| 4.1 наблюдение 10 мин | … | … |
| 5 итог | … | … |

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-bf/…); результаты J2 и J3; что видно на
  снимках словами; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
