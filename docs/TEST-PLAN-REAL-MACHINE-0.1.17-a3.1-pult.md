# Программа испытаний XGW: пульт при включённом VPN XGW — повтор шага 4.2 А3.1

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§7). Пути в командах — только абсолютные (`$HOME/xgw-a31p-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома, XGW 0.1.17 с кодом ветки `android-a3`
(испытание А3.1, отчёт `docs/TEST-REPORT-REAL-MACHINE-0.1.17-a3.1-2026-10-22.md`). Шлюз —
выходной узел Tailscale. Телефон заказчика — **Samsung Galaxy S25 Ultra** — привязан к
приложению XGW, на нём Tailscale с выходным узлом через шлюз, VPN XGW в приложении выключен.
`adb` на шлюзе есть. Клон репозитория — `~/zcod/xgw`.

**Код шлюза не меняется и не ставится** — новое только в приложении на телефоне. Что нового
(ASSUMPTIONS п. 231), по дефекту 1 отчёта А3.1 («пульт по Wi-Fi с включённым VPN телефона не
работает»):

1. Список серверов VPN телефона, полученный до А3.1, — «старого вида»: в нём нет запасного
   пути пульта через VPN телефона. Приложение теперь узнаёт такой список и обновляет его при
   открытии, перед включением VPN и, пока VPN включён, раз в минуту. В карточке «VPN
   телефона» — строка «Список серверов старого вида…», пока он не обновлён.
2. Не ответил ни один путь к шлюзу — в ошибке оба: «напрямую — …; через VPN телефона — …».
   Ответил только запасной путь — в карточке после «Пульт ходит к шлюзу через VPN телефона»
   в скобках сказано, почему не вышло напрямую.
3. При включённом VPN XGW больше нет совета «Если на телефоне включён другой VPN, выключите
   его».
4. Обновление списка серверов идёт в фоне и не занимает кнопку «Включить VPN телефона».

Новый APK — `android/apk/XGW-0.1.17-a3.apk` (сборка 4). Телефон управляется как в А3.1:
кабель USB, «Отладка по USB», скрипт `pultcheck.py` (все команды — без sudo). Что требует рук
заказчика — отдельные шаги «Скажи / Попроси заказчика».

Цели:

1. Подготовка и установка приложения (шаги 1–2).
2. Обновление списка серверов при открытии приложения (шаг 2.2).
3. Повтор шага 4.2: VPN XGW и пульт по домашнему Wi-Fi (шаг 3).
4. Возврат телефона как было: VPN XGW выключен, Tailscale с выходным узлом (шаг 4).
5. Итог (шаг 5), отчёт (§7).

## 0. Запрещено

- На шлюзе: `install.sh` (код шлюза в этом испытании не ставится), `xgw net down`, `xgw
  disable`, `xgw uninstall`, `reboot`, сон машины — **никогда**; службы `xgw*`,
  `tailscaled`, NetworkManager, `ssh` не трогать; команды Tailscale — только `tailscale
  status`. Панель шлюза не нажимать.
- В приложении: нажимать только кнопки из шагов. «Выключить VPN шлюза», «Отвязать телефон»,
  «Привязать заново» — **никогда**.
- На телефоне: ничего, кроме приложения XGW, Tailscale (только то, что делает сам
  заказчик) и команд `adb` из шагов.
- Править `/etc/xgw/*`, `/var/lib/xgw/*`, код XGW. Коммитить что-либо, кроме отчёта (§7).
- Снимки экрана в отчёт и в Git **не класть**.
- Писать в отчёт: адреса tailnet (`100.x.y.z`), имена `*.ts.net`, имена устройств, кроме
  модели телефона, внешние IP, MAC-адреса, ключи, адреса подписок, IP и домены серверов VPN.
  Коды стран — можно. Выводы — только через `pultcheck.py` (скрипт маскирует сам).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Повторю один шаг прошлого испытания — пульт при включённом VPN XGW. Шлюз не меняю. Обновлю
приложение XGW на телефоне (около 20 МБ), телефон — к шлюзу кабелем с „Отладкой по USB“, как
раньше. Потом попрошу выключить Tailscale на телефоне и быть в домашнем Wi-Fi, включу VPN XGW
в приложении и проверю пульт — минуты три. В конце выключу VPN XGW и попрошу включить Tailscale
обратно, выходной узел останется как был. Согласны?»

Дождись ответа. Нет — **стоп**, испытание не проводится.

Затем:

```bash
mkdir -p "$HOME/xgw-a31p-test/after" && chmod 700 "$HOME/xgw-a31p-test" && cd "$HOME/xgw-a31p-test" && date; adb version | head -1; sudo -n true && echo "sudo без пароля: да"
```

Ожидается: дата, `Android Debug Bridge version 1.0.…`, «sudo без пароля: да».
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без
пароля на время испытаний (нужен только для `xgw status` и `xgw diag` в шаге 5).

Шаг 1.2. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout android-a3 && git pull --ff-only && git log -1 --format='%h %s'; sha256sum android/apk/XGW-0.1.17-a3.apk; git diff --quiet 24387f1 HEAD -- src packaging && echo "код шлюза: как в А3.1"; grep -q "outdated" android/app/src/main/assets/app.js && echo "исправление пульта в коде: есть"; cd "$HOME/xgw-a31p-test"
```

Ожидается: `85ab50ff8c90fa847f47f395c6cc09ad90006f499e198bc7d0e37c46e0d28457` в начале строки
хеша, «код шлюза: как в А3.1», «исправление пульта в коде: есть». Записать хеш коммита.
Если не так: **стоп**, сообщить заказчику.

Шаг 1.3. Скрипт проверки. Скопируй команду целиком (до строки `PULT_EOF` включительно):

```bash
cat > "$HOME/xgw-a31p-test/pultcheck.py" <<'PULT_EOF'
"""Повтор шага 4.2 А3.1 XGW (ветка android-a3): пульт при включённом VPN XGW в приложении.

python3 pultcheck.py devices              телефон подключён и разрешил отладку
python3 pultcheck.py install              поставить android/apk/XGW-0.1.17-a3.apk из клона
python3 pultcheck.py start                открыть приложение
python3 pultcheck.py texts                надписи на экране приложения (маскированные)
python3 pultcheck.py tap ID|ТЕКСТ         нажать кнопку приложения (id элемента или часть надписи)
python3 pultcheck.py system               надписи системного окна Android (разрешения)
python3 pultcheck.py tap-system ID|ТЕКСТ  нажать кнопку в системном окне Android
python3 pultcheck.py wait ТЕКСТ СЕКУНД    ждать надпись на экране приложения
python3 pultcheck.py vpn                  VPN телефона: процесс Xray, интерфейс, приложение мимо VPN
python3 pultcheck.py exit                 страна выхода телефона в интернет (адрес не печатается)
python3 pultcheck.py network              сеть телефона сейчас: Wi-Fi или мобильная
python3 pultcheck.py crash                падения приложения в журнале телефона
python3 pultcheck.py mask < ФАЙЛ          маскировать вывод
"""

from __future__ import annotations

import hashlib
import ipaddress
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
APK_SHA = "85ab50ff8c90fa847f47f395c6cc09ad90006f499e198bc7d0e37c46e0d28457"
BUILD = 4  # versionCode APK с исправлением пульта (ASSUMPTIONS п. 231)
TUN_ADDRESS = "10.233.233.1"  # адрес интерфейса VPN приложения (XgwVpn.kt)
CGNAT = ipaddress.ip_network("100.64.0.0/10")


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
    """Элементы экрана: текст, id, середина (x, y)."""
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
            "text": node.get("text") or node.get("content-desc") or "",
            "id": node.get("resource-id") or "", "package": node.get("package") or "",
            "click": node.get("clickable") == "true", "x": (x1 + x2) // 2, "y": (y1 + y2) // 2,
            "visible": y2 > y1 and x2 > x1,
        })
    return result


def visible_texts() -> list[str]:
    seen: list[str] = []
    for node in nodes():
        text = node["text"].strip()
        if text and node["visible"] and node["package"] == PACKAGE and text not in seen:
            seen.append(text)
    return seen


def swipe(down: bool) -> None:
    """Прокрутить страницу приложения: down — к концу (палец вверх), иначе — к началу."""
    match = re.search(r"(\d+)x(\d+)", adb("shell", "wm", "size").stdout)
    width, height = (int(match.group(1)), int(match.group(2))) if match else (1080, 2340)
    low, high = int(height * 0.75), int(height * 0.3)
    start, end = (low, high) if down else (high, low)
    adb("shell", "input", "swipe", str(width // 2), str(start), str(width // 2), str(end), "300")
    time.sleep(1)


def to_top() -> None:
    for _ in range(6):
        swipe(down=False)


def screen_texts() -> list[str]:
    """Надписи всей страницы: от начала до конца с прокруткой, затем — снова в начало."""
    to_top()
    seen: list[str] = []
    for _ in range(8):
        fresh = [text for text in visible_texts() if text not in seen]
        if not fresh and seen:
            break
        seen.extend(fresh)
        swipe(down=True)
    to_top()
    return seen


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
    adb("shell", "am", "start", "-n", f"{PACKAGE}/{PACKAGE}.MainActivity")
    time.sleep(4)
    return cmd_texts()


def cmd_texts() -> int:
    masker = Masker()
    for text in screen_texts():
        print(" ", masker.mask(text))
    return 0


def find(what: str) -> dict | None:
    found = [n for n in nodes() if n["visible"] and n["package"] == PACKAGE and (
        n["id"] == what or what.lower() in n["text"].lower())]
    clickable = [n for n in found if n["click"]] or found
    return clickable[0] if clickable else None


def cmd_tap(what: str) -> int:
    """Кнопка на экране; нет — ищется прокруткой страницы вниз, потом с начала."""
    target = find(what)
    for down in (True, False):
        if target is None and not down:
            to_top()
            target = find(what)
        for _ in range(8):
            if target is not None:
                break
            swipe(down=True)
            target = find(what)
        if target is not None:
            break
    if target is None:
        print(f"на экране нет «{what}»")
        return 1
    adb("shell", "input", "tap", str(target["x"]), str(target["y"]))
    print(f"нажато: «{Masker().mask(target['text'] or target['id'])}»")
    time.sleep(2)
    return 0


def cmd_wait(text: str, seconds: float) -> int:
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        if any(text.lower() in item.lower() for item in visible_texts()):
            print(f"«{text}» на экране через {time.monotonic() - started:.0f} с")
            return 0
        time.sleep(2)
    print(f"«{text}» НЕ ПОЯВИЛОСЬ за {seconds:.0f} с; на экране:")
    return cmd_texts() or 1


def system_nodes() -> list[dict]:
    return [n for n in nodes() if n["visible"] and n["package"] != PACKAGE and
            not n["package"].endswith("systemui")]


def cmd_system() -> int:
    """Окно Android поверх приложения: «Запрос на подключение» VPN, разрешение на уведомления."""
    shown = [f"{n['text']} [{n['id']}]" for n in system_nodes() if n["text"]]
    print("системное окно:" if shown else "системного окна нет")
    for line in shown:
        print(" ", line)
    return 0


def cmd_tap_system(what: str) -> int:
    found = [n for n in system_nodes() if n["id"] == what or
             (n["text"] and what.lower() == n["text"].lower())]
    if not found:
        print(f"в системном окне нет «{what}»")
        return 1
    adb("shell", "input", "tap", str(found[0]["x"]), str(found[0]["y"]))
    print(f"нажато в системном окне: «{found[0]['text'] or found[0]['id']}»")
    time.sleep(2)
    return 0


def cmd_vpn() -> int:
    pid = adb("shell", "pidof", "libxray.so").stdout.strip()
    addresses = adb("shell", "ip", "-br", "addr", "show").stdout
    tun = next((line.split()[0] for line in addresses.splitlines() if TUN_ADDRESS in line), "")
    print(f"Xray в приложении: {'работает' if pid else 'НЕ ЗАПУЩЕН'}")
    print(f"интерфейс VPN ({TUN_ADDRESS}): {tun or 'НЕТ'}")
    uid_match = re.search(r"(?:userId|appId)=(\d+)",
                          adb("shell", "dumpsys", "package", PACKAGE).stdout)
    rules = adb("shell", "ip", "rule").stdout
    # Правила VPN — диапазоны uid «все, кроме исключённых» (0-10192, 10194-…); 0-0 — системные.
    ranges = [tuple(map(int, m.groups())) for m in re.finditer(r"uidrange (\d+)-(\d+)", rules)]
    ranges = [r for r in ranges if r != (0, 0)]
    if uid_match and ranges:
        uid = int(uid_match.group(1))
        inside = any(low <= uid <= high for low, high in ranges)
        around = any(low <= uid - 1 <= high for low, high in ranges)
        print("приложение XGW мимо своего VPN: " + (
            "НЕТ" if inside else "да" if around else "не видно"))
    else:
        print("приложение XGW мимо своего VPN: не видно (VPN выключен или правила недоступны)")
    return 0 if pid and tun else 1


def cmd_exit() -> int:
    """Страна, из которой телефон выходит в интернет: ip-api.com по HTTP (toybox nc)."""
    ask = ("printf 'GET /line/?fields=countryCode HTTP/1.0\\r\\nHost: ip-api.com\\r\\n"
           "Connection: close\\r\\n\\r\\n'")
    out = adb("shell", f"{ask} | toybox nc -w 15 ip-api.com 80", timeout=40).stdout
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    code = lines[-1] if lines and re.fullmatch(r"[A-Z]{2}", lines[-1]) else ""
    print(f"страна выхода телефона: {code or 'НЕТ ОТВЕТА'}")
    return 0 if code else 1


def cmd_network() -> int:
    wifi = adb("shell", "cmd", "wifi", "status").stdout
    connected = re.search(r"(?i)wifi is connected|connected to", wifi) is not None
    enabled = re.search(r"(?i)wifi is enabled", wifi) is not None
    print("Wi-Fi телефона: " + ("подключён" if connected else "включён, не подключён"
                                if enabled else "выключен"))
    return 0


def cmd_crash() -> int:
    log = adb("logcat", "-d", "-b", "crash").stdout
    ours = [line for line in log.splitlines() if PACKAGE in line]
    print(f"падений приложения в журнале телефона: {len(ours)}")
    for line in ours[-5:]:
        print(" ", Masker().mask(line))
    return 0


class Masker:
    """Имена *.ts.net, адреса tailnet и внешние, ссылки и коды привязки — метками."""

    def __init__(self) -> None:
        self.labels: dict[str, dict[str, str]] = {}

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
        text = re.sub(r"xgw://\S+", "xgw://…", text)
        text = re.sub(r"(?i)\b[\w-]+(\.[\w-]+)*\.ts\.net\b",
                      lambda m: self.label("name", m.group(0).lower(), "имя-{}.ts-net"), text)
        text = re.sub(r"[?&](token|login|c)=[A-Za-z0-9_-]+", r"?\1=***", text)
        text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "почта@…", text)
        return re.sub(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])", self._ip, text)


def main(argv: list[str]) -> int:
    command, rest = (argv[0], argv[1:]) if argv else ("", [])
    simple = {"devices": cmd_devices, "install": cmd_install, "start": cmd_start,
              "texts": cmd_texts, "crash": cmd_crash, "system": cmd_system, "vpn": cmd_vpn,
              "exit": cmd_exit, "network": cmd_network}
    if command in simple:
        return simple[command]()
    if command == "tap" and rest:
        return cmd_tap(" ".join(rest))
    if command == "tap-system" and rest:
        return cmd_tap_system(" ".join(rest))
    if command == "wait" and len(rest) >= 2:
        return cmd_wait(" ".join(rest[:-1]), float(rest[-1]))
    if command == "mask":
        sys.stdout.write(Masker().mask(sys.stdin.read()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
PULT_EOF
sha256sum "$HOME/xgw-a31p-test/pultcheck.py"
```

Ожидается: `91aa3c1c0972a8a1ae767bf7220e4f527b9270634c687f586ea68103125e1da5` в начале строки.
Если хеш другой: повторить шаг 1.3 один раз; снова другой — **стоп**.

## 2. Приложение

Шаг 2.1. **Скажи заказчику**: «Подключите телефон к шлюзу кабелем („Отладка по USB“
включена).» Затем:

```bash
python3 "$HOME/xgw-a31p-test/pultcheck.py" devices; python3 "$HOME/xgw-a31p-test/pultcheck.py" install | tee "$HOME/xgw-a31p-test/after/app.txt"
```

Ожидается: «телефон: подключён, отладка разрешена», «установка: Success», «установлено:
net.xgw.android 0.1.17-a3, сборка 4».
Если «ЖДЁТ РАЗРЕШЕНИЯ» — попросить заказчика нажать на телефоне «Разрешить» и повторить.
Если сборка не 4 или установка не Success: **стоп**, сохранить вывод, сообщить заказчику.

Шаг 2.2. Список серверов при открытии. **Спроси заказчика**: «Tailscale на телефоне сейчас
включён?» Нет — попросить включить (выходной узел — шлюз) и подождать 20 с. Затем:

```bash
python3 "$HOME/xgw-a31p-test/pultcheck.py" start | grep -E 'VPN телефона|Серверов|старого вида|Нет связи|Состояние на' | tee "$HOME/xgw-a31p-test/after/open.txt"; sleep 40; echo "--- через 40 с:" | tee -a "$HOME/xgw-a31p-test/after/open.txt"; python3 "$HOME/xgw-a31p-test/pultcheck.py" texts | grep -E 'Серверов|старого вида|Нет связи|Состояние на' | tee -a "$HOME/xgw-a31p-test/after/open.txt"
```

Ожидается: «VPN телефона выключен»; через 40 с — «Серверов: N · список от сегодня ЧЧ:ММ»
(время — сейчас), строки «Список серверов старого вида» **нет**, пульт: «Состояние на …»
без «Нет связи».
Записать, была ли строка «Список серверов старого вида» в **первой** части вывода (до «через
40 с») и какая дата стояла после «список от»: это проверяет причину дефекта (список остался
от испытания А3).
Если через 40 с строка «старого вида» осталась — записать её целиком (в скобках — причина),
затем:

```bash
python3 "$HOME/xgw-a31p-test/pultcheck.py" tap vpn-fetch; sleep 30; python3 "$HOME/xgw-a31p-test/pultcheck.py" texts | grep -E 'Серверов|старого вида|Нет связи' | tee -a "$HOME/xgw-a31p-test/after/open.txt"
```

Строка осталась и теперь — **дефект «список серверов не обновляется»**: записать текст
целиком и продолжать (шаг 3 проверит, что VPN XGW честно говорит об этом).

## 3. VPN XGW и пульт по домашнему Wi-Fi (повтор шага 4.2)

Шаг 3.1. **Скажи заказчику**: «Выключите на телефоне VPN в приложении Tailscale (Tailscale →
выключить; выбор выходного узла в нём сохранится). Wi-Fi — включён, домашняя сеть.» Затем:

```bash
python3 "$HOME/xgw-a31p-test/pultcheck.py" network | tee "$HOME/xgw-a31p-test/after/vpn-consent.txt"; python3 "$HOME/xgw-a31p-test/pultcheck.py" tap vpn-power | tee -a "$HOME/xgw-a31p-test/after/vpn-consent.txt"; sleep 3; python3 "$HOME/xgw-a31p-test/pultcheck.py" system | tee -a "$HOME/xgw-a31p-test/after/vpn-consent.txt"
```

Ожидается: «Wi-Fi телефона: подключён»; «нажато: «Включить VPN телефона»» — с первого раза
(не «Подождите…»); «системного окна нет» (разрешения уже есть).
Если «Wi-Fi телефона: выключен» — попросить заказчика включить Wi-Fi и повторить шаг 3.1.
Если нажато «Подождите…» — записать (наблюдение), подождать 20 с и повторить только
`tap vpn-power`.
Если системное окно «Запрос на подключение» — `python3 "$HOME/xgw-a31p-test/pultcheck.py"
tap-system android:id/button1`; окно об уведомлениях —
`python3 "$HOME/xgw-a31p-test/pultcheck.py" tap-system com.android.permissioncontroller:id/permission_allow_button`.

Шаг 3.2. VPN и пульт по Wi-Fi:

```bash
python3 "$HOME/xgw-a31p-test/pultcheck.py" wait "VPN телефона включён" 40 | tee "$HOME/xgw-a31p-test/after/vpn-wifi.txt"; python3 "$HOME/xgw-a31p-test/pultcheck.py" vpn | tee -a "$HOME/xgw-a31p-test/after/vpn-wifi.txt"; python3 "$HOME/xgw-a31p-test/pultcheck.py" exit | tee -a "$HOME/xgw-a31p-test/after/vpn-wifi.txt"; sleep 45; python3 "$HOME/xgw-a31p-test/pultcheck.py" texts | grep -E 'Нет связи|Состояние на|Серверов|Пульт ходит|старого вида|прежнем списке|другой VPN' | tee -a "$HOME/xgw-a31p-test/after/vpn-wifi.txt"
```

Ожидается: «VPN телефона включён», «Xray в приложении: работает», «приложение XGW мимо своего
VPN: да», страна выхода — YY (записать); пульт: «Состояние на ЧЧ:ММ:СС» — время позже
включения VPN, **без** «Нет связи»;
строк «старого вида» и «другой VPN» нет.
Записать целиком строку «Серверов: …»: если в ней есть «Пульт ходит к шлюзу через VPN телефона
(напрямую не вышло: …)» — это не дефект: пульт работает запасным путём, а текст в скобках
объясняет, почему не открылся прямой путь из домашнего Wi-Fi (это и нужно для разбора).
Если «Нет связи со шлюзом» — подождать 30 с и повторить последнюю команду (`texts | grep …`);
снова — **дефект «пульт по Wi-Fi с VPN телефона не работает»**: записать текст ошибки целиком
(теперь в нём оба пути: «напрямую — …; через VPN телефона — …») и строки «Серверов» и «старого
вида», если есть.
Если в тексте ошибки есть «Если на телефоне включён другой VPN» — **дефект «ложная
подсказка осталась»**.
Если «Xray в приложении: НЕ ЗАПУЩЕН» — записать надписи карточки VPN
(`python3 "$HOME/xgw-a31p-test/pultcheck.py" texts | grep VPN`), там причина, и перейти к
шагу 4.

Шаг 3.3. Пульт через минуту (путь держится):

```bash
sleep 60; python3 "$HOME/xgw-a31p-test/pultcheck.py" texts | grep -E 'Нет связи|Состояние на|Пульт ходит|старого вида' | tee -a "$HOME/xgw-a31p-test/after/vpn-wifi.txt"; python3 "$HOME/xgw-a31p-test/pultcheck.py" exit | tee -a "$HOME/xgw-a31p-test/after/vpn-wifi.txt"
```

Ожидается: «Состояние на …» со временем позже, чем в 3.2, без «Нет связи»; страна — та же YY.
Если «Нет связи» — записать текст целиком (дефект, если в 3.2 пульт работал: «пульт по Wi-Fi
пропадает через минуту»).

## 4. Возврат телефона

Шаг 4.1. Выключить VPN XGW:

```bash
python3 "$HOME/xgw-a31p-test/pultcheck.py" tap vpn-power | tee "$HOME/xgw-a31p-test/after/back.txt"; sleep 5; python3 "$HOME/xgw-a31p-test/pultcheck.py" vpn | head -1 | tee -a "$HOME/xgw-a31p-test/after/back.txt"
```

Ожидается: «нажато: «Выключить VPN телефона»», «Xray в приложении: НЕ ЗАПУЩЕН».
Если Xray работает — повторить один раз; снова — попросить заказчика выключить VPN XGW
кнопкой в приложении и записать.

Шаг 4.2. **Скажи заказчику**: «Включите VPN в приложении Tailscale обратно (выходной узел —
шлюз, как было).» Через 20 с:

```bash
sleep 20; python3 "$HOME/xgw-a31p-test/pultcheck.py" exit | tee -a "$HOME/xgw-a31p-test/after/back.txt"; python3 "$HOME/xgw-a31p-test/pultcheck.py" start | grep -E 'Нет связи|Состояние на|VPN телефона' | tee -a "$HOME/xgw-a31p-test/after/back.txt"
```

Ожидается: страна выхода — как у шлюза через основной сервер (в А3.1 — PL; не RU);
«VPN телефона выключен», пульт: «Состояние на …» без «Нет связи» (пульт идёт через
Tailscale).
Если «НЕТ ОТВЕТА» — повторить через 30 с; снова — попросить заказчика выключить в Tailscale
Exit node и записать (интернет телефона — напрямую).

## 5. Итог

Шаг 5.1.

```bash
sudo xgw diag | tail -1 | tee "$HOME/xgw-a31p-test/after/final.txt"; sudo xgw status | grep -E '^Состояние|^Xray|Перехват:' | python3 "$HOME/xgw-a31p-test/pultcheck.py" mask | tee -a "$HOME/xgw-a31p-test/after/final.txt"; python3 "$HOME/xgw-a31p-test/pultcheck.py" crash | tee -a "$HOME/xgw-a31p-test/after/final.txt"
```

Ожидается: «FAIL — 0», «Состояние: HEALTHY …», «Перехват: включён», «падений приложения в
журнале телефона: 0».
Затем **скажи**: «Испытание закончено. „Отладку по USB“ можно выключить.»

## 6. Если что-то пошло не так

- У телефона пропал интернет при включённом VPN XGW — попросить заказчика нажать в
  приложении XGW «Выключить VPN телефона» (или включить Tailscale: он заберёт VPN сам).
- Интернет дома пропал — `sudo xgw status`, сообщить заказчику; ничего не откатывать без
  него (код шлюза в этом испытании не менялся).

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-a3.1-pult-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`android-a3`), коммит «Отчёт А3.1: повтор шага 4.2 — пульт при VPN XGW», `git push`.
Шаблон:

```markdown
# Отчёт: повтор шага 4.2 А3.1 — пульт при VPN XGW (ветка android-a3)

Код: <хеш>. APK sha256 <первые 8 знаков> — совпал, сборка <…>. Телефон: <модель>, Android <…>.
Согласие заказчика: да.

## Итог
<3–6 предложений: обновился ли список серверов при открытии и был ли он старого вида; работает
ли пульт по Wi-Fi с VPN XGW и каким путём (напрямую / через VPN телефона, почему не вышло
напрямую); телефон возвращён как было.>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 2.1 приложение | … | Success, сборка 4 |
| 2.2 список серверов при открытии | … | старого вида: да/нет; список от …; через 40 с … |
| 3.1 включение VPN XGW | … | с первого нажатия: да/нет |
| 3.2 VPN XGW + пульт, Wi-Fi | … | страна YY; «Состояние на …» / «Нет связи»; путь пульта |
| 3.3 пульт через минуту | … | … |
| 4.1–4.2 возврат | … | VPN XGW выключен, Tailscale, страна, пульт |
| 5.1 итог | … | FAIL — 0, падений 0 |

## Выводы шагов
<содержимое файлов after/*.txt, по заголовку на файл>

## Дефекты
<или «Не обнаружены»>

## Наблюдения
<в том числе текст в скобках после «Пульт ходит к шлюзу через VPN телефона», если был>

## Что не проверено и почему

## Итоговое состояние
<телефон: Tailscale с выходным узлом / VPN XGW / ничего; шлюз — выходной узел, как был.>
```

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
