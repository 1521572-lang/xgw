# Программа испытаний XGW: повтор А3.2 — выключатель сервера, события, имена

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§8). Пути в командах — только абсолютные (`$HOME/xgw-a33-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома, XGW 0.1.17 с кодом ветки `android-a3`
(испытание А3.2 — отчёт `docs/TEST-REPORT-REAL-MACHINE-0.1.17-a3.2-2026-10-24.md`). Шлюз —
выходной узел Tailscale. Телефон заказчика — **Samsung Galaxy S25 Ultra** — привязан к
приложению XGW, на нём Tailscale с выходным узлом через шлюз, VPN XGW в приложении выключен.
`adb` на шлюзе есть. Клон репозитория — `~/zcod/xgw`. Номер версии XGW не меняется
(`xgw 0.1.17`).

Что нового (ASSUMPTIONS п. 233). В испытании А3.2 отключённый с телефона сервер «пропал» из
вкладки «Серверы»: на деле его строка уезжала в конец подписки, за все запасные, а скрипт
проверки не долистывал до конца списка. По отчёту доработано:

1. **Приложение** (сборка 6): после выключателя сервера список сам прокручивается к его
   строке на новом месте и ненадолго подсвечивает её.
2. **Шлюз**: каждое действие с телефона — **одно** событие «с телефона «…»: …» (было два:
   ещё и событие панели); имена серверов из подписок — без пробелов по краям.
3. **Скрипт проверки** `a33check.py` листает вкладку до конца и имя сервера не обрезает.

Телефон управляется как раньше: кабель USB, «Отладка по USB», скрипт `a33check.py` (без
sudo; сам зовёт `sudo -n` только для чтения файлов шлюза). Все действия испытания обратимы:
запасной сервер выключается и сразу включается.

Цели:

1. Подготовка, установка кода шлюза и приложения (шаги 1–2).
2. Имена серверов без пробелов по краям (шаг 3).
3. Выключатель сервера с телефона: строка видна сразу после нажатия — и при выключении, и
   при включении (шаг 4).
4. Одно событие на действие с телефона (шаг 5). Итог (шаг 6), отчёт (§8).

## 0. Запрещено

- На шлюзе: `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины,
  `install.sh --force` — **никогда**; службы `xgw*`, `tailscaled`, NetworkManager, `ssh` не
  трогать; команды Tailscale — только `tailscale status`. Панель шлюза не нажимать.
- В приложении: нажимать только то, что в шагах. Всё остальное — **никогда**: «Выключить VPN
  шлюза», «Отвязать телефон», «Привязать заново», «Выбрать», ядро, приоритет и «Убрать» у
  серверов, «Включить все», «Отключить все», «Один основной сервер», «Замерить скорость»,
  «Проверить запасные», подписки, устройства, Tailscale. «Обновить подписки» — только в
  шаге 3 и только если так сказано.
- На телефоне: ничего, кроме приложения XGW и команд `adb` из шагов; Tailscale не трогать.
- Править `/etc/xgw/*`, `/var/lib/xgw/*`, код XGW. Коммитить что-либо, кроме отчёта (§8).
- Снимки экрана в отчёт и в Git **не класть**.
- Писать в отчёт: адреса tailnet (`100.x.y.z`), имена `*.ts.net`, имена устройств, кроме
  модели телефона, имена серверов (сервер для проверки — «С-1»), внешние IP, MAC-адреса,
  ключи, адреса подписок, IP и домены серверов VPN. Коды стран — можно. Выводы — только
  через `a33check.py` (скрипт маскирует сам).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Повторяю короткую проверку пульта после доработок по отчёту. По пунктам:
(1) Установлю на шлюз новый код: демон XGW перезапустится сам, интернет дома не пропадает,
панель секунд на десять недоступна. Обновлю приложение XGW на телефоне (около 20 МБ).
Телефон — к шлюзу кабелем с „Отладкой по USB“, как раньше; Wi-Fi — домашний.
(2) С телефона выключу и сразу включу один запасной сервер. Серверы в работе и основной не
трогаю.
(3) Если после установки в списке шлюза останутся имена серверов с пробелами, нажму в
приложении «Обновить подписки» — шлюз заново получит ваши подписки, как делает сам по
расписанию.
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против 2 — шаги 4–5 пропустить; против 3 — в шаге 3 «Обновить подписки» не нажимать.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-a33-test/after" && chmod 700 "$HOME/xgw-a33-test" && cd "$HOME/xgw-a33-test" && date; adb version | head -1
```

Ожидается: «sudo без пароля: да», дата, `Android Debug Bridge version 1.0.…`.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без
пароля на время испытаний.

Шаг 1.2. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout android-a3 && git pull --ff-only && git log -1 --format='%h %s'; sha256sum android/apk/XGW-0.1.17-a3.apk; grep -q 'origin: str = ""' src/xgw/watch/panel.py && grep -q 'data-fingerprint' android/app/src/main/assets/app.js && echo "доработки А3.2 в коде: есть"; cd "$HOME/xgw-a33-test"
```

Ожидается: `1b8835b35571679c10fd155aacbc51016dff71b9408c378e2ce6a9f5811ee06a` в начале строки хеша, «доработки А3.2 в коде: есть».
Записать хеш коммита. Если не так: **стоп**, сообщить заказчику.

Шаг 1.3. Скрипт проверки. Скопируй команду целиком (до строки `A33_EOF` включительно):

```bash
cat > "$HOME/xgw-a33-test/a33check.py" <<'A33_EOF'
"""Повтор А3.2 XGW (ветка android-a3): выключатель сервера с телефона, события, имена.

python3 a33check.py devices              телефон подключён и разрешил отладку
python3 a33check.py install              поставить android/apk/XGW-0.1.17-a3.apk из клона
python3 a33check.py start                открыть приложение (вкладка «Главная»)
python3 a33check.py tab ВКЛАДКА          открыть вкладку (home, servers, subs, devices, events) и
                                         показать её надписи (вся вкладка, до конца)
python3 a33check.py tap ID|ТЕКСТ         нажать кнопку приложения (id, подпись или часть надписи)
python3 a33check.py wait ТЕКСТ СЕКУНД    ждать надпись на экране приложения
python3 a33check.py names                имена серверов шлюза с пробелами по краям
python3 a33check.py spare                выбрать запасной сервер для проверки (вкладка «Серверы»)
python3 a33check.py toggle off|on        нажать выключатель этого сервера и сразу, без прокрутки,
                                         проверить его строку на экране
python3 a33check.py spare-state          строка состояния этого сервера
python3 a33check.py events               события вкладки «События» об этом сервере
python3 a33check.py crash                падения приложения в журнале телефона
python3 a33check.py mask < ФАЙЛ          маскировать вывод
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = os.environ.get("ADB", "adb")
PACKAGE = os.environ.get("XGW_A3_PACKAGE", "net.xgw.android")
CLONE = Path(os.environ.get("XGW_CLONE", str(Path.home() / "zcod" / "xgw")))
APK = CLONE / "android" / "apk" / "XGW-0.1.17-a3.apk"
APK_SHA = "1b8835b35571679c10fd155aacbc51016dff71b9408c378e2ce6a9f5811ee06a"
BUILD = 6  # versionCode APK с прокруткой к серверу (ASSUMPTIONS п. 233)
HERE = Path.home() / "xgw-a33-test"
SPARE = HERE / "spare.txt"  # имя запасного сервера для проверки — в отчёт не идёт
INVENTORY = Path("/var/lib/xgw/inventory.json")
TABS = ("home", "servers", "subs", "devices", "events")
CGNAT = ipaddress.ip_network("100.64.0.0/10")
STATES = ("запасной", "отключён", "в работе", "основной", "включён", "резервный")
SWIPES = 120  # потолок прокрутки: 79 серверов — около 60 движений (отчёт А3.2: 14 мало)


def run(argv: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]}: нет программы")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"{argv[0]}: таймаут")


def adb(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return run([ADB, *args], timeout=timeout)


def screen_size() -> tuple[int, int]:
    match = re.search(r"(\d+)x(\d+)", adb("shell", "wm", "size").stdout)
    return (int(match.group(1)), int(match.group(2))) if match else (1080, 2340)


def nodes() -> list[dict]:
    """Элементы экрана: текст или подпись (как есть, без обрезки), id, середина (x, y)."""
    adb("shell", "uiautomator", "dump", "/sdcard/xgw-ui.xml")
    dump = adb("exec-out", "cat", "/sdcard/xgw-ui.xml").stdout
    try:
        root = ET.fromstring(dump)
    except ET.ParseError:
        return []
    result = []
    for node in root.iter("node"):
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if not match:
            continue
        x1, y1, x2, y2 = map(int, match.groups())
        result.append({
            "text": node.get("text") or "", "desc": node.get("content-desc") or "",
            "id": node.get("resource-id") or "", "package": node.get("package") or "",
            "click": node.get("clickable") == "true", "x": (x1 + x2) // 2, "y": (y1 + y2) // 2,
            "visible": y2 > y1 and x2 > x1,
        })
    return result


def ours() -> list[dict]:
    return [n for n in nodes() if n["visible"] and n["package"] == PACKAGE]


def label(node: dict) -> str:
    return node["text"] or node["desc"]


def visible_texts() -> list[str]:
    seen: list[str] = []
    for node in ours():
        text = label(node).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def swipe(down: bool) -> None:
    """Прокрутить страницу: down — к концу (палец вверх), иначе — к началу. Нижняя панель
    вкладок — в последних 10 % экрана: палец её не задевает."""
    width, height = screen_size()
    low, high = int(height * 0.7), int(height * 0.3)
    start, end = (low, high) if down else (high, low)
    adb("shell", "input", "swipe", str(width // 2), str(start), str(width // 2), str(end), "300")
    time.sleep(1)


def to_top() -> None:
    """В начало вкладки: листать вверх, пока экран меняется."""
    before: list[str] = []
    for _ in range(SWIPES):
        swipe(down=False)
        now = visible_texts()
        if now == before:
            return
        before = now


def walk():
    """Экраны вкладки от начала до конца: конец — когда два движения подряд ничего не
    меняют на экране (отчёт А3.2: 14 движений не доходили до конца списка)."""
    to_top()
    still = 0
    previous: list[str] = []
    for _ in range(SWIPES):
        screen = ours()
        yield screen
        texts = [label(n) for n in screen]
        still = still + 1 if texts == previous else 0
        if still >= 2:
            return
        previous = texts
        swipe(down=True)


def screen_texts() -> list[str]:
    seen: list[str] = []
    for screen in walk():
        for node in screen:
            text = label(node).strip()
            if text and text not in seen:
                seen.append(text)
    to_top()
    return seen


def find(what: str, exact: bool = False, screen: list[dict] | None = None) -> dict | None:
    def hit(node: dict) -> bool:
        if node["id"] == what:
            return True
        texts = [node["text"], node["desc"]]
        return any(text == what if exact else what.lower() in text.lower() for text in texts if text)

    found = [n for n in (ours() if screen is None else screen) if hit(n)]
    clickable = [n for n in found if n["click"]] or found
    return clickable[0] if clickable else None


def search(what: str, exact: bool = False) -> dict | None:
    """Элемент на вкладке: на экране, иначе — от начала до конца вкладки."""
    target = find(what, exact)
    if target is not None:
        return target
    for screen in walk():
        target = find(what, exact, screen)
        if target is not None:
            return target
    return None


def tap_node(node: dict) -> None:
    adb("shell", "input", "tap", str(node["x"]), str(node["y"]))
    time.sleep(2)


def cmd_devices() -> int:
    out = adb("devices").stdout
    lines = [line for line in out.splitlines()[1:] if line.strip()]
    if not lines:
        print("телефон: НЕ ВИДЕН (кабель, режим USB, «Отладка по USB»)")
        return 1
    for line in lines:
        state = line.split()[-1]
        word = {"device": "подключён, отладка разрешена",
                "unauthorized": "ЖДЁТ РАЗРЕШЕНИЯ на телефоне («Разрешить отладку по USB?»)",
                "offline": "НЕ ОТВЕЧАЕТ (переподключите кабель)"}.get(state, state)
        print(f"телефон: {word}")
    model = adb("shell", "getprop", "ro.product.model").stdout.strip()
    release = adb("shell", "getprop", "ro.build.version.release").stdout.strip()
    if model:
        print(f"модель: {model}; Android {release}")
    adb("shell", "svc", "power", "stayon", "usb")  # экран не гаснет, пока телефон на кабеле
    return 0


def cmd_install() -> int:
    digest = hashlib.sha256(APK.read_bytes()).hexdigest() if APK.exists() else ""
    if digest != APK_SHA:
        print(f"файл приложения: {'НЕТ' if not digest else 'ДРУГОЙ ХЕШ'} ({APK})")
        return 1
    result = adb("install", "-r", str(APK), timeout=180)
    print("установка:", (result.stdout.strip().splitlines() or [result.stderr.strip()])[-1])
    info = adb("shell", "dumpsys", "package", PACKAGE).stdout
    version = re.search(r"versionName=(\S+)", info)
    build = re.search(r"versionCode=(\d+)", info)
    if not version or not build:
        print("установлено: НЕТ")
        return 1
    print(f"установлено: {PACKAGE} {version.group(1)}, сборка {build.group(1)}")
    return 0 if int(build.group(1)) == BUILD else 1


def cmd_start() -> int:
    adb("shell", "am", "force-stop", PACKAGE)
    adb("shell", "am", "start", "-n", f"{PACKAGE}/{PACKAGE}.MainActivity")
    time.sleep(6)
    masker = Masker()
    for text in visible_texts():
        print(" ", masker.mask(text))
    return 0


def cmd_tab(name: str) -> int:
    if name not in TABS:
        print("вкладки: " + ", ".join(TABS))
        return 2
    target = find(f"go-{name}")
    if target is None:
        print("нижней панели вкладок нет — приложение не на экране пульта")
        return 1
    tap_node(target)
    masker = Masker()
    for text in screen_texts():
        print(" ", masker.mask(text))
    return 0


def cmd_tap(what: str) -> int:
    target = search(what)
    if target is None:
        print(f"на экране нет «{what}»")
        return 1
    tap_node(target)
    print(f"нажато: «{Masker().mask(label(target) or target['id'])}»")
    return 0


def cmd_wait(text: str, seconds: float) -> int:
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        if any(text.lower() in item.lower() for item in visible_texts()):
            print(f"«{text}» на экране через {time.monotonic() - started:.0f} с")
            return 0
        time.sleep(2)
    print(f"«{text}» НЕ ПОЯВИЛОСЬ за {seconds:.0f} с; на экране:")
    masker = Masker()
    for item in visible_texts():
        print(" ", masker.mask(item))
    return 1


def cmd_names() -> int:
    """Имена серверов в списке шлюза (inventory.json) с пробелами по краям — сами имена
    не печатаются."""
    text = run(["sudo", "-n", "cat", str(INVENTORY)]).stdout
    try:
        servers = json.loads(text).get("servers") or []
    except ValueError:
        print("inventory.json не прочитан (sudo без пароля?)")
        return 1
    names = [str(item.get("name") or "") for item in servers]
    padded = [name for name in names if name != name.strip()]
    print(f"серверов в списке шлюза: {len(names)}; имён с пробелами по краям: {len(padded)}")
    return 0


# --- запасной сервер для проверки -----------------------------------------------------------


def spare_name() -> str:
    # Имя — как есть, без strip (отчёт А3.2: обрезанное имя не находилось точным поиском).
    return SPARE.read_text(encoding="utf-8").rstrip("\n") if SPARE.exists() else ""


def cmd_spare() -> int:
    """Первый сверху запасной сервер (строка «запасной …» и выключатель под ней): после
    выключения он уходит дальше всех — в конец группы, за все запасные."""
    for screen in walk():
        for index, node in enumerate(screen):
            if not node["text"].startswith("запасной"):
                continue
            switch = next((n for n in screen[index:] if n["desc"].startswith("Отключить ")), None)
            if switch is not None:
                SPARE.write_text(switch["desc"].removeprefix("Отключить ") + "\n", encoding="utf-8")
                print("запасной сервер для проверки выбран: С-1")
                return 0
    print("запасного сервера на вкладке «Серверы» нет")
    return 1


def cmd_toggle(what: str) -> int:
    name = spare_name()
    if not name:
        print("сначала: a33check.py spare")
        return 1
    if what not in ("off", "on"):
        print("toggle off|on")
        return 2
    press, after = ("Отключить", "Включить") if what == "off" else ("Включить", "Отключить")
    target = search(f"{press} {name}", exact=True)
    if target is None:
        print(f"у сервера С-1 нет «{press} С-1»")
        return 1
    tap_node(target)
    print(f"нажато: «{press} С-1»")
    # Без прокрутки: приложение само показывает строку сервера на новом месте.
    _width, height = screen_size()
    started = time.monotonic()
    while time.monotonic() - started < 15:
        screen = ours()
        shown = find(f"{after} {name}", exact=True, screen=screen)
        if shown is not None and 0 < shown["y"] < height:
            break
        time.sleep(2)
    else:
        print(f"за 15 с после нажатия на экране «{after} С-1»: НЕТ")
        return 1
    print(f"после нажатия на экране «{after} С-1»: да, через {time.monotonic() - started:.0f} с, "
          f"на высоте {100 * shown['y'] // height} % экрана")
    states = [n for n in screen if n["text"].startswith(STATES)]
    if states:
        line = min(states, key=lambda n: abs(n["y"] - shown["y"]))["text"]
        print(f"строка С-1: {Masker().mask(line)}")
    return 0


def cmd_spare_state() -> int:
    name = spare_name()
    for screen in walk():
        for index, node in enumerate(screen):
            if node["text"] == name:
                line = next((n["text"] for n in screen[index + 1:index + 12]
                             if n["text"].startswith(STATES)), "")
                if line:
                    to_top()
                    print(f"С-1: {Masker().mask(line)}")
                    return 0
    to_top()
    print("строки сервера С-1 на вкладке нет")
    return 1


def cmd_events() -> int:
    """События об этом сервере на вкладке «События»: с телефона — одно на нажатие, а
    событий панели «сервер «С-1» отключён» без «с телефона» быть не должно."""
    name = spare_name()
    target = find("go-events")
    if not name or target is None:
        print("сначала: a33check.py spare; приложение — на экране пульта")
        return 1
    tap_node(target)
    masker = Masker()
    lines = [text for text in screen_texts() if f"«{name}» отключён" in text or f"«{name}» включён" in text]
    phone = [text for text in lines if "с телефона" in text]
    print(f"событий «С-1 отключён / включён»: {len(lines)}; из них «с телефона»: {len(phone)}; "
          f"без «с телефона»: {len(lines) - len(phone)}")
    for text in lines:
        print(" ", masker.mask(text))
    return 0


def cmd_crash() -> int:
    log = adb("logcat", "-d", "-b", "crash").stdout
    mine = [line for line in log.splitlines() if PACKAGE in line]
    print(f"падений приложения в журнале телефона: {len(mine)}")
    for line in mine[-5:]:
        print(" ", Masker().mask(line))
    return 0


class Masker:
    """Имена *.ts.net, адреса tailnet и внешние, MAC, ссылки и имя сервера С-1 — метками."""

    def __init__(self) -> None:
        self.labels: dict[str, dict[str, str]] = {}
        self.spare = spare_name()

    def label(self, kind: str, value: str, fmt: str) -> str:
        table = self.labels.setdefault(kind, {})
        return table.setdefault(value, fmt.format(len(table) + 1))

    def _ip(self, match: re.Match) -> str:
        text = match.group(0)
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            return text
        if str(address) in ("100.100.100.100", "127.0.0.1", "1.1.1.1"):
            return text
        if address in CGNAT:
            return self.label("ts4", text, "100.x.y.{}")
        if address.is_global:
            return self.label("ext", text, "внешний-IP-{}")
        return text

    def mask(self, text: str) -> str:
        if self.spare:
            text = text.replace(self.spare, "С-1")
        text = re.sub(r"xgw://\S+", "xgw://…", text)
        text = re.sub(r"(?i)\b[\w-]+(\.[\w-]+)*\.ts\.net\b",
                      lambda m: self.label("name", m.group(0).lower(), "имя-{}.ts-net"), text)
        text = re.sub(r"(?i)\b[0-9a-f]{2}(:[0-9a-f]{2}){5}\b",
                      lambda m: self.label("mac", m.group(0).lower(), "MAC-{}"), text)
        text = re.sub(r"(?i)\b(vless|vmess|trojan|ss|hysteria2|tuic)://\S+", r"\1://…", text)
        text = re.sub(r"[?&](token|login|c)=[A-Za-z0-9_-]+", r"?\1=***", text)
        text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "почта@…", text)
        return re.sub(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])", self._ip, text)


def main(argv: list[str]) -> int:
    command, rest = (argv[0], argv[1:]) if argv else ("", [])
    simple = {"devices": cmd_devices, "install": cmd_install, "start": cmd_start,
              "names": cmd_names, "spare": cmd_spare, "spare-state": cmd_spare_state,
              "events": cmd_events, "crash": cmd_crash}
    if command in simple:
        return simple[command]()
    if command == "tab" and len(rest) == 1:
        return cmd_tab(rest[0])
    if command == "tap" and rest:
        return cmd_tap(" ".join(rest))
    if command == "wait" and len(rest) >= 2:
        return cmd_wait(" ".join(rest[:-1]), float(rest[-1]))
    if command == "toggle" and len(rest) == 1:
        return cmd_toggle(rest[0])
    if command == "mask":
        sys.stdout.write(Masker().mask(sys.stdin.read()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
A33_EOF
sha256sum "$HOME/xgw-a33-test/a33check.py"
```

Ожидается: `fd9d53837c015daa6a837725c964cdfb6cbcd881dd30983bde264be51bdc25e6` в начале строки.
Если хеш другой: повторить шаг 1.3 один раз; снова другой — **стоп**.

Шаг 1.4. Имена серверов до установки (для сравнения):

```bash
python3 "$HOME/xgw-a33-test/a33check.py" names | sed 's/^/до установки: /' | tee "$HOME/xgw-a33-test/after/names.txt"
```

Ожидается: «до установки: серверов в списке шлюза: N; имён с пробелами по краям: M» (M —
сколько есть, обычно больше нуля).
Если «inventory.json не прочитан» — **стоп**, проверить sudo (шаг 1.1).

## 2. Установка

Шаг 2.1. Код шлюза (из каталога кода):

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-a33-test/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-a33-test/after/install.txt" | tail -20; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-a33-test"
```

Ожидается: «код 0», в конце — сообщение об успешной установке.
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику (§7).

Шаг 2.2. Шлюз в порядке (до 5 минут):

```bash
for i in $(seq 30); do sudo xgw status 2>&1 | grep -q '^Состояние: HEALTHY' && break; sleep 10; done; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | python3 "$HOME/xgw-a33-test/a33check.py" mask | tee "$HOME/xgw-a33-test/after/state-install.txt"; sudo xgw diag | tail -1 | tee -a "$HOME/xgw-a33-test/after/state-install.txt"
```

Ожидается: «Состояние: HEALTHY …», «Xray 26.10.21: отвечает», «Перехват: включён …»,
«FAIL — 0».
Если за 5 минут не HEALTHY, но «FAIL — 0» и интернет дома есть — записать вывод, **спросить
заказчика**: «Шлюз в состоянии <состояние>, интернет работает. Продолжать?» — и дальше
только с его согласия. Если FAIL больше 0 — **стоп**, `sudo xgw status` целиком через `mask`
в отчёт, сообщить заказчику.

Шаг 2.3. Приложение. **Скажи заказчику**: «Подключите телефон к шлюзу кабелем („Отладка по
USB“ включена), Wi-Fi — домашний.» Затем:

```bash
python3 "$HOME/xgw-a33-test/a33check.py" devices; python3 "$HOME/xgw-a33-test/a33check.py" install | tee "$HOME/xgw-a33-test/after/app.txt"
```

Ожидается: «телефон: подключён, отладка разрешена», «установка: Success», «установлено:
net.xgw.android 0.1.17-a3, сборка 6».
Если «ЖДЁТ РАЗРЕШЕНИЯ» — попросить заказчика нажать на телефоне «Разрешить» и повторить.
Если сборка не 6 или установка не Success: **стоп**, сохранить вывод, сообщить заказчику.

## 3. Имена серверов

Шаг 3.1. Демон после установки сам заново получает подписки (до 3 минут):

```bash
for i in $(seq 18); do python3 "$HOME/xgw-a33-test/a33check.py" names | grep -q 'по краям: 0$' && break; sleep 10; done; python3 "$HOME/xgw-a33-test/a33check.py" names | sed 's/^/после установки: /' | tee -a "$HOME/xgw-a33-test/after/names.txt"
```

Ожидается: «после установки: серверов в списке шлюза: N; имён с пробелами по краям: 0».
Если больше 0 и заказчик согласился на пункт 3 — шаг 3.2; не согласился — записать
(наблюдение «имена ещё старые»), перейти к шагу 4.

Шаг 3.2. Только если в 3.1 не 0. «Обновить подписки» с телефона:

```bash
python3 "$HOME/xgw-a33-test/a33check.py" start > /dev/null; python3 "$HOME/xgw-a33-test/a33check.py" tap go-servers | tee -a "$HOME/xgw-a33-test/after/names.txt"; python3 "$HOME/xgw-a33-test/a33check.py" tap refresh | tee -a "$HOME/xgw-a33-test/after/names.txt"; sleep 120; python3 "$HOME/xgw-a33-test/a33check.py" names | sed 's/^/после «Обновить подписки»: /' | tee -a "$HOME/xgw-a33-test/after/names.txt"
```

Ожидается: «нажато: «Серверы»», «нажато: «Обновить подписки»», «после «Обновить подписки»:
… имён с пробелами по краям: 0».
Если снова больше 0 — **дефект «имена с пробелами»**, записать и продолжать.

## 4. Выключатель сервера с телефона

Шаг 4.1. Запасной сервер для проверки — первый сверху на вкладке «Серверы» (после выключения
он уходит дальше всех, в конец своей подписки):

```bash
python3 "$HOME/xgw-a33-test/a33check.py" start > /dev/null; python3 "$HOME/xgw-a33-test/a33check.py" tap go-servers > /dev/null; python3 "$HOME/xgw-a33-test/a33check.py" spare | tee "$HOME/xgw-a33-test/after/toggle.txt"; python3 "$HOME/xgw-a33-test/a33check.py" spare-state | tee -a "$HOME/xgw-a33-test/after/toggle.txt"
```

Ожидается: «запасной сервер для проверки выбран: С-1», «С-1: запасной …».
Если «запасного сервера … нет» — шаги 4.2–5.1 пропустить (записать: «запасных нет»), перейти
к шагу 6.

Шаг 4.2. Выключить С-1. Строка должна оказаться на экране сама, без прокрутки:

```bash
python3 "$HOME/xgw-a33-test/a33check.py" toggle off | tee -a "$HOME/xgw-a33-test/after/toggle.txt"
```

Ожидается: «нажато: «Отключить С-1»», «после нажатия на экране «Включить С-1»: да, через N с,
на высоте NN % экрана», «строка С-1: отключён …».
Если «за 15 с после нажатия на экране «Включить С-1»: НЕТ» — **дефект «строка сервера не
видна после выключателя»**; записать, выполнить `python3 "$HOME/xgw-a33-test/a33check.py"
spare-state | tee -a "$HOME/xgw-a33-test/after/toggle.txt"` (есть ли строка ниже по списку) и
продолжать с шага 4.3.

Шаг 4.3. Сразу включить С-1 обратно:

```bash
sleep 5; python3 "$HOME/xgw-a33-test/a33check.py" toggle on | tee -a "$HOME/xgw-a33-test/after/toggle.txt"; sleep 60; python3 "$HOME/xgw-a33-test/a33check.py" spare-state | tee -a "$HOME/xgw-a33-test/after/toggle.txt"
```

Ожидается: «нажато: «Включить С-1»», «после нажатия на экране «Отключить С-1»: да, …»,
«строка С-1: включён — шлюз сейчас возьмёт его в работу» (или «запасной …»); через минуту
«С-1: запасной …» (или «в работе …» — шлюз мог взять его в работу, не дефект).
Если «у сервера С-1 нет «Включить С-1»» — **дефект «включить с телефона»**: попросить
заказчика включить сервер в панели шлюза (вкладка «Серверы», выключатель), записать.
Если «…на экране «Отключить С-1»: НЕТ» — **дефект «строка сервера не видна после
выключателя»**, записать и продолжать.

## 5. События

Шаг 5.1. События об этом сервере (сразу после шага 4):

```bash
python3 "$HOME/xgw-a33-test/a33check.py" events | tee "$HOME/xgw-a33-test/after/events.txt"
```

Ожидается: «событий «С-1 отключён / включён»: 2; из них «с телефона»: 2; без «с телефона»:
0» и две строки «… с телефона «Galaxy S25 Ultra»: сервер «С-1» включён» / «… отключён».
Если «без «с телефона»» больше 0 — **дефект «двойные события»**. Если событий 0 —
записать (наблюдение), не дефект: их могли вытеснить события демона.

## 6. Итог

Шаг 6.1.

```bash
sudo xgw diag | tail -1 | tee "$HOME/xgw-a33-test/after/final.txt"; sudo xgw status | grep -E '^Состояние|^Xray|Перехват:' | python3 "$HOME/xgw-a33-test/a33check.py" mask | tee -a "$HOME/xgw-a33-test/after/final.txt"; python3 "$HOME/xgw-a33-test/a33check.py" crash | tee -a "$HOME/xgw-a33-test/after/final.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-a33-test/install-time.txt")" --no-pager 2>/dev/null | grep -c Traceback | sed 's/^/Traceback: /' | tee -a "$HOME/xgw-a33-test/after/final.txt"; adb shell svc power stayon false; rm -f "$HOME/xgw-a33-test/spare.txt"
```

Ожидается: «FAIL — 0», «Состояние: HEALTHY …» (или то же, что в шаге 2.2, если заказчик
решил продолжать), «Перехват: включён …», «падений приложения в журнале телефона: 0»,
«Traceback: 0».
Затем **скажи**: «Испытание закончено. „Отладку по USB“ можно выключить.»

## 7. Если что-то пошло не так

- Интернет дома пропал после установки — `sudo xgw status`, сообщить заказчику; ничего не
  откатывать без него.
- Приложение не открывается или падает — `python3 "$HOME/xgw-a33-test/a33check.py" crash`,
  записать, сообщить заказчику.
- Сервер С-1 остался выключен — попросить заказчика включить его в панели шлюза и записать.

## 8. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-a3.2-fix-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`android-a3`), коммит «Отчёт А3.2-fix: выключатель сервера, события, имена», `git push`.
Шаблон:

```markdown
# Отчёт: повтор А3.2 — выключатель сервера, события, имена (ветка android-a3)

Код: <хеш>. APK sha256 <первые 8 знаков> — совпал, сборка <…>. Телефон: <модель>, Android <…>.
Согласие заказчика: <на какие пункты>.

## Итог
<2–4 предложения: установился ли код; имена до и после; видна ли строка сервера сразу после
выключения и включения; сколько событий; итоговое состояние.>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 2.1–2.2 код шлюза | … | код 0, <состояние>, FAIL — 0 |
| 2.3 приложение | … | Success, сборка 6 |
| 3 имена серверов | … | с пробелами: до M, после 0 |
| 4.2 выключить С-1 | … | «Включить С-1» на экране через N с, NN % экрана |
| 4.3 включить С-1 | … | «Отключить С-1» на экране через N с; через минуту — «запасной» |
| 5.1 события | … | 2, «с телефона» 2, без — 0 |
| 6.1 итог | … | FAIL — 0, падений 0, Traceback 0 |

## Выводы шагов
<содержимое файлов after/*.txt, по заголовку на файл>

## Дефекты
<или «Не обнаружены»>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние
<шлюз: состояние, С-1 включён; телефон: Tailscale с выходным узлом, VPN XGW выключен,
приложение сборки 6.>
```

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
