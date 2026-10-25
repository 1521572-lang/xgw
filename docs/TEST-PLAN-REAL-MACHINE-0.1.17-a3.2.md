# Программа испытаний XGW: пульт в приложении — как панель шлюза (А3.2)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§10). Пути в командах — только абсолютные (`$HOME/xgw-a32-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома, XGW 0.1.17 с кодом ветки `android-a3`
(испытания А3.1 и повтор пульта — без дефектов). Шлюз — выходной узел Tailscale. Телефон
заказчика — **Samsung Galaxy S25 Ultra** — привязан к приложению XGW, на нём Tailscale с
выходным узлом через шлюз, VPN XGW в приложении выключен. `adb` на шлюзе есть. Клон
репозитория — `~/zcod/xgw`. Номер версии XGW не меняется (`xgw 0.1.17`).

Что нового (ASSUMPTIONS п. 232). Заказчик: пульт в приложении урезан без причины — он должен
уметь то, что панель шлюза, в части серверов и подписок. Теперь:

1. **Шлюз** отдаёт телефону то же состояние, что видит панель (серверы по подпискам,
   подписки, ссылки, устройства, записи трафика, события), и принимает те же действия, кроме
   доступа к самому шлюзу (вход в Tailscale, SSH, панель по tailnet, Funnel, привязка
   телефонов — только в панели). Записи трафика телефон может скачать. Код шлюза ставится.
2. **Приложение** — вкладки внизу экрана: «Главная» (VPN телефона, VPN шлюза, строка
   «Перехват», текущий сервер, «Автовыбор»), «Серверы» (у каждого сервера — «Выбрать», ядро,
   приоритет, выключатель, «Убрать»; «Один основной сервер», «Обновить подписки», «Проверить
   запасные», «Замерить скорость», «Убранные»), «Подписки» (добавить — поле, «Вставить»,
   «QR-код»; изменить, убрать), «Устройства» (мимо VPN, запись трафика, «Скачать» в
   «Загрузки/XGW», Tailscale: выход через шлюз, устройства tailnet, маршрут), «События».
   Новый APK — `android/apk/XGW-0.1.17-a3.apk` (сборка 5).

Телефон управляется как раньше: кабель USB, «Отладка по USB», скрипт `a32check.py` (без
sudo; сам зовёт `sudo -n` только для чтения файлов шлюза). Что требует рук заказчика —
отдельные шаги «Скажи / Попроси заказчика». Все действия испытания обратимы: проверочная
подписка добавляется и убирается, запасной сервер выключается и включается, приоритет
возвращается «Средний», запись трафика удаляется.

Цели:

1. Подготовка, установка кода шлюза и приложения (шаги 1–2).
2. Вкладки пульта показывают то же, что панель (шаг 3).
3. Серверы с телефона: выключить и включить запасной, приоритет, проверить запасные (шаг 4).
4. Подписки с телефона: добавить, изменить, убрать; «Вставить», «QR-код» (шаг 5).
5. Запись трафика телефона с телефона: записать, скачать, удалить (шаг 6).
6. События шлюза — действия с телефона (шаг 7). Итог (шаг 8), отчёт (§10).

## 0. Запрещено

- На шлюзе: `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины,
  `install.sh --force` — **никогда**; службы `xgw*`, `tailscaled`, NetworkManager, `ssh` не
  трогать; команды Tailscale — только `tailscale status`. Панель шлюза не нажимать.
- В приложении: нажимать только то, что в шагах. «Выключить VPN шлюза», «Отвязать телефон»,
  «Привязать заново», «Выбрать» у серверов, «Убрать» у серверов и у настоящих подписок,
  «Отключить все», выключатели устройств, «Выход в интернет через шлюз», выключатели
  устройств tailnet, «Маршрут Tailscale», «Один основной сервер», «Замерить скорость» —
  **никогда**.
- На телефоне: ничего, кроме приложения XGW и команд `adb` из шагов; Tailscale не трогать.
- Править `/etc/xgw/*`, `/var/lib/xgw/*`, код XGW. Коммитить что-либо, кроме отчёта (§10).
- Файлы записи трафика (`*.pcap`) и снимки экрана в отчёт и в Git **не класть**.
- Писать в отчёт: адреса tailnet (`100.x.y.z`), имена `*.ts.net`, имена устройств, кроме
  модели телефона, имена серверов (сервер для проверки — «С-1»), внешние IP, MAC-адреса,
  ключи, адреса подписок (кроме проверочной `example.com`), IP и домены серверов VPN. Коды
  стран — можно. Выводы — только через `a32check.py` (скрипт маскирует сам).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Ставлю на шлюз и телефон новый пульт: в приложении будет всё, что в панели, — серверы,
подписки, устройства, события. По пунктам:
(1) Установка кода на шлюз: демон XGW перезапустится сам, интернет дома не пропадает,
панель секунд на десять недоступна. Обновлю приложение XGW на телефоне (около 20 МБ).
Телефон — к шлюзу кабелем с „Отладкой по USB“, как раньше; Wi-Fi — домашний.
(2) С телефона: выключу и включу один запасной сервер, поменяю ему приоритет и верну,
нажму «Проверить запасные». Серверы в работе и основной не трогаю.
(3) Добавлю с телефона проверочную подписку example.com (она не обновится — так и надо),
поменяю ей User-Agent и уберу. Ваши подписки не трогаю. Попрошу вас скопировать на
телефоне любое слово — проверить кнопку «Вставить».
(4) Запишу с телефона трафик самого телефона на полминуты, скачаю файл на телефон и удалю
его и там, и на шлюзе.
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против 2 — шаг 4 пропустить; против 3 — шаг 5; против 4 — шаг 6.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-a32-test/after" && chmod 700 "$HOME/xgw-a32-test" && cd "$HOME/xgw-a32-test" && date; adb version | head -1
```

Ожидается: «sudo без пароля: да», дата, `Android Debug Bridge version 1.0.…`.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без
пароля на время испытаний.

Шаг 1.2. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout android-a3 && git pull --ff-only && git log -1 --format='%h %s'; sha256sum android/apk/XGW-0.1.17-a3.apk; grep -q "TAILSCALE_KEYS" src/xgw/watch/appapi.py && grep -q 'id="go-servers"' android/app/src/main/assets/index.html && echo "А3.2 в коде: есть"; cd "$HOME/xgw-a32-test"
```

Ожидается: `cb6204ddc6ab2a982ab5ecd3e6dc239d3a396dae5cb0d8d50a42b5f3755cd04a` в начале строки хеша, «А3.2 в коде: есть». Записать хеш
коммита. Если не так: **стоп**, сообщить заказчику.

Шаг 1.3. Скрипт проверки. Скопируй команду целиком (до строки `A32_EOF` включительно):

```bash
cat > "$HOME/xgw-a32-test/a32check.py" <<'A32_EOF'
"""Испытание А3.2 XGW (ветка android-a3): пульт в приложении — как панель шлюза.

python3 a32check.py devices              телефон подключён и разрешил отладку
python3 a32check.py install              поставить android/apk/XGW-0.1.17-a3.apk из клона
python3 a32check.py start                открыть приложение (вкладка «Главная»)
python3 a32check.py texts                надписи на экране приложения (маскированные)
python3 a32check.py tab ВКЛАДКА          открыть вкладку (home, servers, subs, devices, events) и
                                         показать её надписи
python3 a32check.py tap ID|ТЕКСТ         нажать кнопку приложения (id, подпись или часть надписи)
python3 a32check.py type ID ТЕКСТ        нажать поле ввода и набрать текст
python3 a32check.py field ID             сколько знаков в поле ввода (сам текст не печатается)
python3 a32check.py wait ТЕКСТ СЕКУНД    ждать надпись на экране приложения
python3 a32check.py spare                выбрать запасной сервер для проверки (вкладка «Серверы»)
python3 a32check.py spare-tap off|on|prio  выключатель или приоритет этого сервера
python3 a32check.py spare-state          строка состояния этого сервера
python3 a32check.py record               красная точка в строке этого телефона (вкладка «Устройства»)
python3 a32check.py downloaded [--remove]  скачанные записи в «Загрузки/XGW» телефона
python3 a32check.py sub-saved ИМЯ        подписка в panel.json шлюза: есть ли и её User-Agent
python3 a32check.py crash                падения приложения в журнале телефона
python3 a32check.py mask < ФАЙЛ          маскировать вывод
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
APK_SHA = "cb6204ddc6ab2a982ab5ecd3e6dc239d3a396dae5cb0d8d50a42b5f3755cd04a"
BUILD = 5  # versionCode APK с пультом как панель (ASSUMPTIONS п. 232)
HERE = Path.home() / "xgw-a32-test"
SPARE = HERE / "spare.txt"  # имя запасного сервера для проверки — в отчёт не идёт
TABS = ("home", "servers", "subs", "devices", "events")
CGNAT = ipaddress.ip_network("100.64.0.0/10")
STATES = ("запасной", "отключён", "в работе", "основной", "включён", "резервный")


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


def nodes() -> list[dict]:
    """Элементы экрана: текст или подпись, id, середина (x, y)."""
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


def screen_size() -> tuple[int, int]:
    match = re.search(r"(\d+)x(\d+)", adb("shell", "wm", "size").stdout)
    return (int(match.group(1)), int(match.group(2))) if match else (1080, 2340)


def swipe(down: bool) -> None:
    """Прокрутить страницу: down — к концу (палец вверх), иначе — к началу. Нижняя панель
    вкладок — в последних 10 % экрана: палец её не задевает."""
    width, height = screen_size()
    low, high = int(height * 0.7), int(height * 0.3)
    start, end = (low, high) if down else (high, low)
    adb("shell", "input", "swipe", str(width // 2), str(start), str(width // 2), str(end), "300")
    time.sleep(1)


def to_top() -> None:
    for _ in range(8):
        swipe(down=False)


def screen_texts() -> list[str]:
    """Надписи всей вкладки: от начала до конца с прокруткой, затем — снова в начало."""
    to_top()
    seen: list[str] = []
    for _ in range(14):
        fresh = [text for text in visible_texts() if text not in seen]
        if not fresh and seen:
            break
        seen.extend(fresh)
        swipe(down=True)
    to_top()
    return seen


def find(what: str, exact: bool = False) -> dict | None:
    def hit(node: dict) -> bool:
        if node["id"] == what:
            return True
        texts = [node["text"], node["desc"]]
        return any(text == what if exact else what.lower() in text.lower() for text in texts if text)

    found = [n for n in ours() if hit(n)]
    clickable = [n for n in found if n["click"]] or found
    return clickable[0] if clickable else None


def search(what: str, exact: bool = False) -> dict | None:
    """Элемент на вкладке: на экране, ниже прокруткой, потом с начала."""
    target = find(what, exact)
    if target is None:
        to_top()
        target = find(what, exact)
    for _ in range(14):
        if target is not None:
            break
        swipe(down=True)
        target = find(what, exact)
    return target


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
    # Экран не гаснет, пока телефон на кабеле (отчёт А3.1: гас посреди чтения надписей).
    adb("shell", "svc", "power", "stayon", "usb")
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
    return cmd_texts()


def cmd_texts() -> int:
    masker = Masker()
    for text in screen_texts():
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
    return cmd_texts()


def cmd_tap(what: str) -> int:
    target = search(what)
    if target is None:
        print(f"на экране нет «{what}»")
        return 1
    tap_node(target)
    print(f"нажато: «{Masker().mask(label(target) or target['id'])}»")
    return 0


def cmd_type(field: str, text: str) -> int:
    target = search(field)
    if target is None:
        print(f"на экране нет поля «{field}»")
        return 1
    tap_node(target)
    # input text: пробел — %s; адрес подписки в этом испытании без пробелов и &.
    adb("shell", "input", "text", text.replace(" ", "%s"))
    time.sleep(1)
    adb("shell", "input", "keyevent", "111")  # Esc — убрать клавиатуру
    time.sleep(1)
    print(f"набрано в «{field}»: {len(text)} знаков")
    return 0


def cmd_field(field: str) -> int:
    target = search(field)
    if target is None:
        print(f"на экране нет поля «{field}»")
        return 1
    print(f"в поле «{field}»: {len(target['text'])} знаков")
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


def system_nodes() -> list[dict]:
    return [n for n in nodes() if n["visible"] and n["package"] != PACKAGE and
            not n["package"].endswith("systemui")]


def cmd_system() -> int:
    shown = [f"{label(n)} [{n['id']}]" for n in system_nodes() if label(n)]
    print("системное окно:" if shown else "системного окна нет")
    for line in shown:
        print(" ", line)
    return 0


def cmd_tap_system(what: str) -> int:
    found = [n for n in system_nodes() if n["id"] == what or
             (label(n) and what.lower() == label(n).lower())]
    if not found:
        print(f"в системном окне нет «{what}»")
        return 1
    tap_node(found[0])
    print(f"нажато в системном окне: «{label(found[0]) or found[0]['id']}»")
    return 0


# --- запасной сервер для проверки -----------------------------------------------------------


def spare_name() -> str:
    return SPARE.read_text(encoding="utf-8").strip() if SPARE.exists() else ""


def cmd_spare() -> int:
    """Последний в списке запасной сервер (строка «запасной …» и выключатель под ней)."""
    to_top()
    chosen = ""
    for _ in range(14):
        screen = ours()
        for index, node in enumerate(screen):
            if not node["text"].startswith("запасной"):
                continue
            switch = next((n for n in screen[index:] if n["desc"].startswith("Отключить ")), None)
            if switch is not None:
                chosen = switch["desc"].removeprefix("Отключить ")
        swipe(down=True)
    to_top()
    if not chosen:
        print("запасного сервера на вкладке «Серверы» нет")
        return 1
    SPARE.write_text(chosen + "\n", encoding="utf-8")
    print("запасной сервер для проверки выбран: С-1")
    return 0


def cmd_spare_tap(what: str) -> int:
    name = spare_name()
    if not name:
        print("сначала: a32check.py spare")
        return 1
    wanted = {"off": f"Отключить {name}", "on": f"Включить {name}", "prio": f"Приоритет {name}"}
    if what not in wanted:
        print("spare-tap off|on|prio")
        return 2
    target = search(wanted[what], exact=True)
    if target is None:
        print(f"у сервера С-1 нет «{wanted[what].replace(name, 'С-1')}»")
        return 1
    tap_node(target)
    print(f"нажато: «{wanted[what].replace(name, 'С-1')}»")
    return 0


def cmd_spare_state() -> int:
    name = spare_name()
    to_top()
    for _ in range(14):
        screen = ours()
        for index, node in enumerate(screen):
            if node["text"] == name:
                line = next((n["text"] for n in screen[index + 1:index + 12]
                             if n["text"].startswith(STATES)), "")
                if line:
                    to_top()
                    print(f"С-1: {Masker().mask(line)}")
                    return 0
        swipe(down=True)
    to_top()
    print("строки сервера С-1 на вкладке нет")
    return 1


# --- запись трафика этого телефона ---------------------------------------------------------


def phone_mac() -> str:
    """MAC телефона в аренде DHCP шлюза — по адресу его Wi-Fi."""
    route = adb("shell", "ip", "-4", "-o", "addr", "show", "wlan0").stdout
    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", route)
    if not match:
        return ""
    leases = run(["sudo", "-n", "cat", "/var/lib/xgw/dhcp.leases"]).stdout
    for line in leases.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2] == match.group(1):
            return fields[1].lower()
    return ""


def cmd_record() -> int:
    mac = phone_mac()
    if not mac:
        print("телефона нет среди устройств дома: Wi-Fi выключен или адрес не от шлюза")
        return 1
    to_top()
    for _ in range(10):
        screen = ours()
        row = next((n for n in screen if mac in n["text"].lower()), None)
        if row is not None:
            button = min((n for n in screen if n["desc"].startswith("Записать трафик")),
                         key=lambda n: abs(n["y"] - row["y"]), default=None)
            if button is None or abs(button["y"] - row["y"]) > 250:
                print("у строки телефона нет красной точки (идёт другая запись?)")
                return 1
            tap_node(button)
            print("нажато: «Записать трафик» в строке этого телефона")
            return 0
        swipe(down=True)
    print("строки этого телефона на вкладке «Устройства» нет")
    return 1


def cmd_downloaded(remove: bool) -> int:
    listing = adb("shell", "ls", "-l", "/sdcard/Download/XGW/").stdout
    files = [line.split()[-1] for line in listing.splitlines() if line.strip().endswith(".pcap")]
    sizes = [int(line.split()[4]) for line in listing.splitlines() if line.strip().endswith(".pcap")]
    print(f"записей в «Загрузки/XGW»: {len(files)}")
    for name, size in zip(files, sizes):
        head = adb("shell", f"head -c 4 /sdcard/Download/XGW/{name} | od -An -tx1").stdout
        magic = "".join(head.split())
        pcap = magic in ("d4c3b2a1", "a1b2c3d4")
        print(f"  файл .pcap: {size} байт, заголовок pcap: {'да' if pcap else 'НЕТ'}")
        if remove:
            adb("shell", "rm", f"/sdcard/Download/XGW/{name}")
    if remove:
        print("файлы записей с телефона удалены")
    return 0 if files else 1


def cmd_sub_saved(name: str) -> int:
    text = run(["sudo", "-n", "cat", "/etc/xgw/panel.json"]).stdout
    try:
        subs = json.loads(text).get("subscriptions") or []
    except ValueError:
        print("panel.json не прочитан (sudo без пароля?)")
        return 1
    found = next((sub for sub in subs if sub.get("name") == name), None)
    if found is None:
        print(f"подписки «{name}» в panel.json нет")
        return 0
    print(f"подписка «{name}» в panel.json: есть; User-Agent: «{found.get('user_agent') or ''}»")
    return 0


def cmd_crash() -> int:
    log = adb("logcat", "-d", "-b", "crash").stdout
    mine = [line for line in log.splitlines() if PACKAGE in line]
    print(f"падений приложения в журнале телефона: {len(mine)}")
    for line in mine[-5:]:
        print(" ", Masker().mask(line))
    return 0


class Masker:
    """Имена *.ts.net, адреса tailnet и внешние, MAC, ссылки, коды и имя сервера С-1 — метками."""

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
        text = re.sub(r"(?i)\b[0-9a-f]{12}-\d{8}-\d{6}\.pcap\b", "запись.pcap", text)
        text = re.sub(r"(?i)\b(vless|vmess|trojan|ss|hysteria2|tuic)://\S+", r"\1://…", text)
        text = re.sub(r"[?&](token|login|c)=[A-Za-z0-9_-]+", r"?\1=***", text)
        text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "почта@…", text)
        return re.sub(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])", self._ip, text)


def main(argv: list[str]) -> int:
    command, rest = (argv[0], argv[1:]) if argv else ("", [])
    simple = {"devices": cmd_devices, "install": cmd_install, "start": cmd_start,
              "texts": cmd_texts, "crash": cmd_crash, "system": cmd_system, "spare": cmd_spare,
              "spare-state": cmd_spare_state, "record": cmd_record}
    if command in simple:
        return simple[command]()
    if command == "tab" and len(rest) == 1:
        return cmd_tab(rest[0])
    if command == "tap" and rest:
        return cmd_tap(" ".join(rest))
    if command == "tap-system" and rest:
        return cmd_tap_system(" ".join(rest))
    if command == "type" and len(rest) >= 2:
        return cmd_type(rest[0], " ".join(rest[1:]))
    if command == "field" and len(rest) == 1:
        return cmd_field(rest[0])
    if command == "wait" and len(rest) >= 2:
        return cmd_wait(" ".join(rest[:-1]), float(rest[-1]))
    if command == "spare-tap" and len(rest) == 1:
        return cmd_spare_tap(rest[0])
    if command == "downloaded":
        return cmd_downloaded("--remove" in rest)
    if command == "sub-saved" and len(rest) == 1:
        return cmd_sub_saved(rest[0])
    if command == "mask":
        sys.stdout.write(Masker().mask(sys.stdin.read()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
A32_EOF
sha256sum "$HOME/xgw-a32-test/a32check.py"
```

Ожидается: `7498e4a8d8cd94913fbf818142894b6f5ddddf6753f2977a71de87530f080743` в начале строки.
Если хеш другой: повторить шаг 1.3 один раз; снова другой — **стоп**.

## 2. Установка

Шаг 2.1. Код шлюза (из каталога кода):

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-a32-test/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-a32-test/after/install.txt" | tail -20; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-a32-test"
```

Ожидается: «код 0», в конце — сообщение об успешной установке.
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику (§9).

Шаг 2.2. Шлюз в порядке (до 5 минут):

```bash
for i in $(seq 30); do sudo xgw status 2>&1 | grep -q '^Состояние: HEALTHY' && break; sleep 10; done; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | python3 "$HOME/xgw-a32-test/a32check.py" mask | tee "$HOME/xgw-a32-test/after/state-install.txt"; sudo xgw diag | tail -1 | tee -a "$HOME/xgw-a32-test/after/state-install.txt"
```

Ожидается: «Состояние: HEALTHY …», «Xray 26.10.21: отвечает», «Перехват: включён …»,
«FAIL — 0».
Если за 5 минут не HEALTHY — записать вывод и `sudo xgw status` целиком через `mask`,
сообщить заказчику; дальше — только с его согласия.

Шаг 2.3. Приложение. **Скажи заказчику**: «Подключите телефон к шлюзу кабелем („Отладка по
USB“ включена), Wi-Fi — домашний.» Затем:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" devices; python3 "$HOME/xgw-a32-test/a32check.py" install | tee "$HOME/xgw-a32-test/after/app.txt"
```

Ожидается: «телефон: подключён, отладка разрешена», «установка: Success», «установлено:
net.xgw.android 0.1.17-a3, сборка 5».
Если «ЖДЁТ РАЗРЕШЕНИЯ» — попросить заказчика нажать на телефоне «Разрешить» и повторить.
Если сборка не 5 или установка не Success: **стоп**, сохранить вывод, сообщить заказчику.

## 3. Вкладки пульта (только смотреть)

Шаг 3.1. «Главная»:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" start | grep -E 'VPN телефона|VPN шлюза|Перехват:|Основной сервер|Сейчас через|Выбран вручную|Нет связи|Состояние на|Главная|Серверы|Подписки|Устройства|События' | tee "$HOME/xgw-a32-test/after/tab-home.txt"
```

Ожидается: «VPN телефона выключен», «VPN шлюза включён», «Перехват: работает — …», одна из
строк «Основной сервер» / «Сейчас через» / «Выбран вручную», «… · Состояние на ЧЧ:ММ:СС» без
«Нет связи»; внизу — «Главная», «Серверы», «Подписки», «Устройства», «События».
Если «Нет связи со шлюзом» — подождать 30 с и повторить; снова — **стоп**: записать текст
ошибки целиком, сообщить заказчику.
Если нижней панели вкладок нет — **дефект «нет вкладок»**, **стоп**.

Шаг 3.2. «Серверы»:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tab servers > "$HOME/xgw-a32-test/servers.txt"; grep -E '^  (Серверы|Один основной сервер|Обновить подписки|Проверить запасные|Замерить скорость|Узлов:|Убранные|Проверки серверов)' "$HOME/xgw-a32-test/servers.txt" | tee "$HOME/xgw-a32-test/after/tab-servers.txt"; grep -cE '^  включено [0-9]+ из [0-9]+' "$HOME/xgw-a32-test/servers.txt" | sed 's/^/подписок (групп) с серверами: /' | tee -a "$HOME/xgw-a32-test/after/tab-servers.txt"; grep -cE '^  Выбрать ' "$HOME/xgw-a32-test/servers.txt" | sed 's/^/кнопок «Выбрать»: /' | tee -a "$HOME/xgw-a32-test/after/tab-servers.txt"; grep -cE '^  Приоритет ' "$HOME/xgw-a32-test/servers.txt" | sed 's/^/выборов приоритета: /' | tee -a "$HOME/xgw-a32-test/after/tab-servers.txt"; grep -cE '^  (Отключить|Включить) ' "$HOME/xgw-a32-test/servers.txt" | sed 's/^/выключателей серверов: /' | tee -a "$HOME/xgw-a32-test/after/tab-servers.txt"; grep -cE '^  (основной|в работе|запасной)' "$HOME/xgw-a32-test/servers.txt" | sed 's/^/строк «основной / в работе / запасной»: /' | tee -a "$HOME/xgw-a32-test/after/tab-servers.txt"
```

Ожидается: «Серверы N», «Один основной сервер», «Обновить подписки», «Проверить запасные»,
строка «Узлов: …»; групп — столько, сколько подписок с серверами (и «Отдельные ссылки», если
они есть); кнопок «Выбрать», выборов приоритета и выключателей — больше нуля; строк
«основной / в работе / запасной» — больше нуля.
Если групп 0 или кнопок 0 — **дефект «вкладка „Серверы“ пуста»**: записать счётчики (сам
`servers.txt` в отчёт не класть — в нём имена серверов).

Шаг 3.3. «Подписки», «Устройства», «События» и «Назад»:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tab subs | grep -E 'Подписки|серверов:|Израсходовано|Безлимитная|Не обновилась|Вставить|QR-код|Добавить|отдельная ссылка' | sed -E 's/^  [^·]*· серверов/  <подписка> · серверов/' | tee "$HOME/xgw-a32-test/after/tab-other.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tab devices | grep -E 'Устройства дома|через VPN|мимо VPN|Записи трафика|Tailscale|Выход в интернет через шлюз|Устройства tailnet|Маршрут Tailscale|в панели на шлюзе' | sort | uniq -c | tee -a "$HOME/xgw-a32-test/after/tab-other.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tab events | head -4 | tee -a "$HOME/xgw-a32-test/after/tab-other.txt"; adb shell input keyevent 4; sleep 2; python3 "$HOME/xgw-a32-test/a32check.py" texts | grep -cE 'VPN телефона' | sed 's/^/«Назад» вернул на «Главную»: /' | tee -a "$HOME/xgw-a32-test/after/tab-other.txt"
```

Ожидается: «Подписки», строки «<подписка> · серверов: N · обновлена …», у лимитированных —
«Израсходовано …», «Вставить», «QR-код», «Добавить»; «Устройства дома N», строки «через VPN»
(и «мимо VPN», если такие есть), «Tailscale», «Выход в интернет через шлюз», «Устройства
tailnet», «Маршрут Tailscale», строка «…в панели на шлюзе…»; «События» и первые события со
временем; ««Назад» вернул на «Главную»: 1» (или больше).
Если вкладка пуста или «Назад» закрыл приложение (0) — **дефект**, записать и продолжать.

## 4. Серверы с телефона

Шаг 4.1. Запасной сервер для проверки:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tab servers > /dev/null; python3 "$HOME/xgw-a32-test/a32check.py" spare | tee "$HOME/xgw-a32-test/after/servers.txt"; python3 "$HOME/xgw-a32-test/a32check.py" spare-state | tee -a "$HOME/xgw-a32-test/after/servers.txt"
```

Ожидается: «запасной сервер для проверки выбран: С-1», «С-1: запасной …».
Если «запасного сервера … нет» — шаги 4.2–4.3 пропустить (записать: «запасных нет»),
перейти к 4.4.

Шаг 4.2. Выключить и включить С-1:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" spare-tap off | tee -a "$HOME/xgw-a32-test/after/servers.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "» отключён" 15 | tee -a "$HOME/xgw-a32-test/after/servers.txt"; sleep 8; python3 "$HOME/xgw-a32-test/a32check.py" spare-state | tee -a "$HOME/xgw-a32-test/after/servers.txt"; python3 "$HOME/xgw-a32-test/a32check.py" spare-tap on | tee -a "$HOME/xgw-a32-test/after/servers.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "» включён" 15 | tee -a "$HOME/xgw-a32-test/after/servers.txt"; sleep 60; python3 "$HOME/xgw-a32-test/a32check.py" spare-state | tee -a "$HOME/xgw-a32-test/after/servers.txt"
```

Ожидается: «нажато: «Отключить С-1»», сообщение «Сервер «С-1» отключён» на экране, «С-1:
отключён …»; затем «нажато: «Включить С-1»», «Сервер «С-1» включён…», через минуту «С-1:
запасной …» (или «включён — шлюз сейчас возьмёт его в работу»).
Если выключатель не нажался или сообщения нет — **дефект «выключатель сервера»**; если С-1
остался «отключён» — повторить только `spare-tap on`; снова — записать и попросить
заказчика включить сервер в панели шлюза (вкладка «Серверы», выключатель).

Шаг 4.3. Приоритет С-1 — «Низкий», затем обратно «Средний»:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" spare-tap prio | tee -a "$HOME/xgw-a32-test/after/servers.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tap Низкий | tee -a "$HOME/xgw-a32-test/after/servers.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "»: низкий" 15 | tee -a "$HOME/xgw-a32-test/after/servers.txt"; sleep 8; python3 "$HOME/xgw-a32-test/a32check.py" spare-tap prio | tee -a "$HOME/xgw-a32-test/after/servers.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tap Средний | tee -a "$HOME/xgw-a32-test/after/servers.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "»: средний" 15 | tee -a "$HOME/xgw-a32-test/after/servers.txt"
```

Ожидается: «нажато: «Приоритет С-1»», «нажато: «Низкий»», на экране «Приоритет сервера «С-1»:
низкий…»; затем так же «Средний» и «…: средний».
Если после «Приоритет С-1» нет пунктов «Низкий» / «Средний» (список не открылся) — записать
`python3 … texts | head -30` (наблюдение «выбор приоритета на телефоне»), нажать
`adb shell input keyevent 4` и продолжать. Если приоритет остался «низкий» — **дефект**;
попросить заказчика вернуть «Средний» в панели шлюза.

Шаг 4.4. «Проверить запасные»:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tap scan-spares | tee -a "$HOME/xgw-a32-test/after/servers.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "Проверяю запасные" 15 | tee -a "$HOME/xgw-a32-test/after/servers.txt"
```

Ожидается: «нажато: «Проверить запасные»», на экране «Проверяю запасные серверы…» или
«Проверяю запасные…».
Если кнопки нет (запасных нет) — записать, не дефект.

## 5. Подписки с телефона

Шаг 5.1. Добавить проверочную подписку:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tab subs > /dev/null; python3 "$HOME/xgw-a32-test/a32check.py" type add-text "https://example.com/xgw-a32-test" | tee "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tap add-submit | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "добавлена" 20 | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" sub-saved example.com | tee -a "$HOME/xgw-a32-test/after/subs.txt"
```

Ожидается: «набрано в «add-text»: 32 знаков», «нажато: «Добавить»», «Подписка
«example.com» добавлена — получаю серверы…», «подписка «example.com» в panel.json: есть;
User-Agent: «»».
Если подписка не добавилась — **дефект «подписка с телефона»**: записать текст на экране
(`python3 … texts | grep -iE 'подписк|не похоже|ошиб'`), шаги 5.2–5.4 пропустить.

Шаг 5.2. Подписка в списке (шлюз пробует её получить):

```bash
sleep 45; python3 "$HOME/xgw-a32-test/a32check.py" tab subs | grep -A2 -E '^  example.com' | tee -a "$HOME/xgw-a32-test/after/subs.txt"
```

Ожидается: строка «example.com», под ней «example.com · серверов: 0 · …» и, вероятно, «Не
обновилась: …» — **так и должно быть**: по этому адресу подписки нет.

Шаг 5.3. Изменить User-Agent:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tap "Изменить подписку example.com" | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" type edit-sub-ua "XGW-A32-test" | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tap dialog-yes | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "изменена" 20 | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" sub-saved example.com | tee -a "$HOME/xgw-a32-test/after/subs.txt"
```

Ожидается: «нажато: «Изменить подписку example.com»», «набрано в «edit-sub-ua»: 12 знаков»,
«нажато: «Сохранить»», «Подписка «example.com» изменена — получаю серверы…», «… User-Agent:
«XGW-A32-test»».
Если User-Agent пустой — **дефект «правка подписки»**.

Шаг 5.4. Убрать проверочную подписку:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tap "Убрать подписку example.com" | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tap dialog-yes | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "убрана" 20 | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" sub-saved example.com | tee -a "$HOME/xgw-a32-test/after/subs.txt"
```

Ожидается: «нажато: «Убрать подписку example.com»», «нажато: «Убрать»», «Подписка
«example.com» убрана», «подписки «example.com» в panel.json нет».
Если подписка осталась — повторить шаг 5.4 один раз; снова — **дефект**, попросить заказчика
убрать её в панели шлюза (карточка «Подписки», крестик у example.com).

Шаг 5.5. «Вставить» и «QR-код». **Попроси заказчика**: «Скопируйте на телефоне любое слово —
например, в Заметках выделите слово и нажмите „Копировать“. Потом вернитесь в XGW
(вкладка «Подписки») и скажите мне.» Затем:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tap paste | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" field add-text | tee -a "$HOME/xgw-a32-test/after/subs.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tap add-scan | tee -a "$HOME/xgw-a32-test/after/subs.txt"; sleep 4; python3 "$HOME/xgw-a32-test/a32check.py" system | head -3 | tee -a "$HOME/xgw-a32-test/after/subs.txt"; adb shell input keyevent 4; sleep 3; python3 "$HOME/xgw-a32-test/a32check.py" texts | grep -cE 'Подписки' | sed 's/^/приложение после сканера на экране: /' | tee -a "$HOME/xgw-a32-test/after/subs.txt"
```

Ожидается: «нажато: «Вставить»», «в поле «add-text»: N знаков» — N больше 0 (длина
скопированного слова); «нажато: «QR-код»», системное окно сканера (Google) — есть; после
«Назад» — «приложение после сканера на экране: 1» (или больше).
**Не** нажимать «Добавить»: слово в поле останется — при следующем открытии приложения оно
исчезнет.
Если N = 0 — спросить заказчика, скопировал ли он слово; да — **дефект «Вставить»**.
Если сканер не открылся и на экране «загружается из Google Play» — записать (наблюдение).

## 6. Запись трафика с телефона

Шаг 6.1. Записать полминуты:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tab devices > /dev/null; python3 "$HOME/xgw-a32-test/a32check.py" record | tee "$HOME/xgw-a32-test/after/record.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tap dialog-yes | tee -a "$HOME/xgw-a32-test/after/record.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "запись 0:" 20 | tee -a "$HOME/xgw-a32-test/after/record.txt"; sleep 30; python3 "$HOME/xgw-a32-test/a32check.py" tap "Остановить запись трафика" | tee -a "$HOME/xgw-a32-test/after/record.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "Запись остановлена" 20 | tee -a "$HOME/xgw-a32-test/after/record.txt"; sleep 10
```

Ожидается: «нажато: «Записать трафик» в строке этого телефона», «нажато: «Записать»»,
метка «запись 0:… · … КБ» на экране; затем «нажато: «Остановить запись трафика …»» и
«Запись остановлена — файл сохраняется».
Если «телефона нет среди устройств дома» — попросить заказчика подключить Wi-Fi к домашней
сети, подождать 30 с и повторить шаг 6.1; снова — шаг 6 пропустить (записать).
Если «у строки телефона нет красной точки» — идёт другая запись: подождать 5 минут и
повторить.

Шаг 6.2. Скачать на телефон:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tap "Скачать запись" | tee -a "$HOME/xgw-a32-test/after/record.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "Запись сохранена" 60 | tee -a "$HOME/xgw-a32-test/after/record.txt"; python3 "$HOME/xgw-a32-test/a32check.py" downloaded | tee -a "$HOME/xgw-a32-test/after/record.txt"
```

Ожидается: «нажато: «Скачать запись (.pcap)»», «Запись сохранена: Загрузки/XGW/…» на экране,
«записей в «Загрузки/XGW»: 1» (или больше, если были раньше), «файл .pcap: N байт, заголовок
pcap: да».
Если «Запись сохранена» не появилось — записать текст на экране (`python3 … texts | grep -iE
'запис|ошиб|связи'`) — **дефект «скачать запись»**.

Шаг 6.3. Удалить запись — на шлюзе (кнопкой в приложении) и на телефоне:

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tap "Удалить запись" | tee -a "$HOME/xgw-a32-test/after/record.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tap dialog-yes | tee -a "$HOME/xgw-a32-test/after/record.txt"; python3 "$HOME/xgw-a32-test/a32check.py" wait "Запись удалена" 20 | tee -a "$HOME/xgw-a32-test/after/record.txt"; python3 "$HOME/xgw-a32-test/a32check.py" downloaded --remove | tee -a "$HOME/xgw-a32-test/after/record.txt"
```

Ожидается: «нажато: «Удалить запись»», «нажато: «Удалить»», «Запись удалена», «файлы записей
с телефона удалены».

## 7. События шлюза

Шаг 7.1.

```bash
python3 "$HOME/xgw-a32-test/a32check.py" tab events | grep -E 'с телефона' | head -20 | tee "$HOME/xgw-a32-test/after/events.txt"
```

Ожидается: строки «с телефона «Galaxy S25 Ultra»: …» о действиях шагов 4–6, например:
«Сервер «С-1» отключён», «…включён…», «Приоритет сервера «С-1»: …», «Проверяю запасные…»,
«Подписка «example.com» добавлена…», «…изменена…», «…убрана», «Записываю трафик…»,
«Запись остановлена…», «Запись удалена».
Если строк «с телефона» нет — **дефект «события»**.

## 8. Итог

Шаг 8.1.

```bash
sudo xgw diag | tail -1 | tee "$HOME/xgw-a32-test/after/final.txt"; sudo xgw status | grep -E '^Состояние|^Xray|Перехват:' | python3 "$HOME/xgw-a32-test/a32check.py" mask | tee -a "$HOME/xgw-a32-test/after/final.txt"; python3 "$HOME/xgw-a32-test/a32check.py" sub-saved example.com | tee -a "$HOME/xgw-a32-test/after/final.txt"; python3 "$HOME/xgw-a32-test/a32check.py" tab servers > /dev/null; python3 "$HOME/xgw-a32-test/a32check.py" spare-state | tee -a "$HOME/xgw-a32-test/after/final.txt"; python3 "$HOME/xgw-a32-test/a32check.py" crash | tee -a "$HOME/xgw-a32-test/after/final.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-a32-test/install-time.txt")" --no-pager 2>/dev/null | grep -c Traceback | sed 's/^/Traceback: /' | tee -a "$HOME/xgw-a32-test/after/final.txt"; adb shell svc power stayon false; rm -f "$HOME/xgw-a32-test/spare.txt"
```

Ожидается: «FAIL — 0», «Состояние: HEALTHY …», «Перехват: включён …», «подписки
«example.com» в panel.json нет», «С-1: запасной …» (или «в работе»: шлюз мог взять его в
работу — не дефект; «отключён» — дефект, см. 4.2), «падений приложения в журнале телефона:
0», «Traceback: 0».
Затем **скажи**: «Испытание закончено. „Отладку по USB“ можно выключить.»

## 9. Если что-то пошло не так

- Интернет дома пропал после установки — `sudo xgw status`, сообщить заказчику; ничего не
  откатывать без него.
- Приложение не открывается или падает — `python3 … crash`, записать, сообщить заказчику.
- Сервер С-1 остался выключен или с приоритетом «Низкий», проверочная подписка осталась —
  попросить заказчика исправить в панели шлюза (см. шаги 4.2, 4.3, 5.4) и записать.

## 10. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-a3.2-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`android-a3`), коммит «Отчёт А3.2: пульт в приложении — как панель», `git push`.
Шаблон:

```markdown
# Отчёт: А3.2 — пульт в приложении как панель шлюза (ветка android-a3)

Код: <хеш>. APK sha256 <первые 8 знаков> — совпал, сборка <…>. Телефон: <модель>, Android <…>.
Согласие заказчика: <на какие пункты>.

## Итог
<3–6 предложений: установился ли код шлюза; что видно на вкладках; что получилось с
серверами, подписками, записью трафика с телефона; события; итоговое состояние.>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 2.1–2.2 код шлюза | … | код 0, HEALTHY, FAIL — 0 |
| 2.3 приложение | … | Success, сборка 5 |
| 3.1 «Главная» | … | … |
| 3.2 «Серверы» | … | групп N, «Выбрать» N, приоритетов N, выключателей N |
| 3.3 «Подписки», «Устройства», «События», «Назад» | … | … |
| 4.2 выключить / включить С-1 | … | … |
| 4.3 приоритет С-1 | … | … |
| 4.4 «Проверить запасные» | … | … |
| 5.1–5.4 проверочная подписка | … | добавлена, UA, убрана |
| 5.5 «Вставить», «QR-код» | … | N знаков; сканер открылся |
| 6.1–6.3 запись трафика | … | записана, скачана (байт, pcap), удалена |
| 7.1 события | … | строк «с телефона»: N |
| 8.1 итог | … | FAIL — 0, падений 0, Traceback 0 |

## Выводы шагов
<содержимое файлов after/*.txt, по заголовку на файл>

## Дефекты
<или «Не обнаружены»>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние
<шлюз: HEALTHY, С-1 — как был, проверочной подписки нет; телефон: Tailscale с выходным
узлом, VPN XGW выключен, приложение сборки 5.>
```

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
