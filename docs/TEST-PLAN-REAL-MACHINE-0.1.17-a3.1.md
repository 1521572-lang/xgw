# Программа испытаний XGW: запись трафика, VPN телефона и выходной узел Tailscale (А3.1)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§11). Пути в командах — только абсолютные (`$HOME/xgw-a31-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома, XGW 0.1.17 с кодом ветки
`xray-26.10.21` (Xray 26.10.21, отчёт — без дефектов). Funnel включён, телефон заказчика —
**Samsung Galaxy S25 Ultra** — привязан к приложению XGW 0.1.17-a3 (испытание А3), на нём
стоит и **Tailscale**. `adb` на шлюзе есть. Клон репозитория — `~/zcod/xgw`. Номер версии
XGW не меняется (`xgw 0.1.17`).

Что нового (ASSUMPTIONS пп. 228–230):

1. **Запись трафика устройства** (п. 228): в панели, в строке устройства — красная точка
   «Записать трафик»; шлюз пишет пакеты устройства в файл `.pcap` для Wireshark (5 минут
   или до «Остановить»). Службе `xgw` нужно право CAP_NET_RAW — оно появляется с установкой.
2. **VPN телефона — исправления по отчёту А3** (п. 229): шлюз ведёт адреса `*.ts.net`
   напрямую (пульт из домашнего Wi-Fi), у пульта запасной путь через VPN телефона, причина
   выключения VPN (его забрал Tailscale) — на экране и уведомлением, разрешение на
   уведомления спрашивается до разрешения на VPN. Новый APK — `android/apk/XGW-0.1.17-a3.apk`.
3. **Шлюз — выходной узел Tailscale** (п. 230): на телефоне один Tailscale, «Exit node →
   шлюз», интернет телефона идёт через Xray шлюза. В панели (карточка «Tailscale») —
   «Выход в интернет через шлюз» и «Устройства tailnet» с переключателем «через VPN /
   напрямую».

Как управляется телефон — как в А3: кабель USB, «Отладка по USB», скрипт `a3check.py`
(команды телефона — без sudo, команды панели — с sudo). Что требует рук заказчика —
отдельные шаги «Попроси заказчика».

Цели:

1. Подготовка и установка кода шлюза и приложения (шаги 1–2).
2. Запись трафика телефона (шаг 3).
3. VPN XGW в приложении: пульт по Wi-Fi и по мобильной сети, Tailscale забирает VPN,
   уведомление (шаги 4–5).
4. Выходной узел: включить, одобрить, выбрать на телефоне, страна выхода и DNS, «напрямую»
   (шаги 6–8).
5. Итог (шаг 9), отчёт (§11).

## 0. Запрещено

- На шлюзе: `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины,
  `install.sh --force` — **никогда**; службы `xgw*`, `tailscaled`, NetworkManager, `ssh` не
  трогать; команды Tailscale — только `tailscale status`.
- Через `a3check.py press` — только `record/start`, `record/stop`, `tailscale/exit`,
  `tailscale/direct` и только как в шагах.
- В приложении: нажимать только кнопки из шагов. «Выключить VPN шлюза», «Отвязать телефон» —
  **никогда**.
- На телефоне: ничего, кроме приложения XGW, Tailscale (только то, что делает сам
  заказчик) и команд `adb` из шагов.
- Править `/etc/xgw/*`, `/var/lib/xgw/*`, код XGW. Коммитить что-либо, кроме отчёта (§11).
- Файлы записи трафика (`*.pcap`) и снимки экрана в отчёт и в Git **не класть**: в них
  адреса и имена. Скачивать .pcap куда-либо, кроме проверки скриптом, — нельзя.
- Писать в отчёт: адреса tailnet (`100.x.y.z`), имена `*.ts.net`, имена устройств, кроме
  модели телефона, внешние IP, MAC-адреса, ключи, адреса подписок, IP и домены серверов VPN.
  Коды стран — можно. Выводы — только через `a3check.py mask` (скрипт маскирует сам).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Ставлю на шлюз и телефон исправления VPN телефона, запись трафика устройства и выход в
интернет через шлюз по Tailscale. По пунктам:
(1) Установка кода на шлюз: демон XGW перезапустится сам, интернет дома не пропадает,
панель секунд на десять недоступна. Обновлю приложение XGW на телефоне (около 20 МБ).
Телефон — к шлюзу кабелем с „Отладкой по USB“, как раньше.
(2) Запись трафика вашего телефона в сети дома на минуту — файл останется на шлюзе (его
можно удалить в панели), в отчёт он не попадает.
(3) VPN XGW в приложении: попрошу выключить Tailscale на телефоне, проверю пульт по Wi-Fi и
по мобильной сети, потом попрошу включить Tailscale — VPN XGW должен уступить ему место с
понятным сообщением.
(4) Сделаю шлюз выходным узлом Tailscale: вам нужно один раз одобрить его в консоли
Tailscale (подскажу где) и выбрать на телефоне в приложении Tailscale „Exit node → шлюз“.
Проверю, через какую страну выходит телефон и чей DNS видят сайты, и одно переключение
„напрямую“ на минуту.
(5) В конце скажете, оставить ли шлюз выходным узлом и что включить на телефоне.
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против 2 — шаг 3 пропустить; против 3 — шаги 4–5; против 4 — шаги 6–8.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-a31-test/after" && chmod 700 "$HOME/xgw-a31-test" && cd "$HOME/xgw-a31-test" && date; adb version | head -1
```

Ожидается: «sudo без пароля: да», дата, `Android Debug Bridge version 1.0.…`.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без
пароля на время испытаний.

Шаг 1.2. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout android-a3 && git pull --ff-only && git log -1 --format='%h %s'; sha256sum android/apk/XGW-0.1.17-a3.apk; grep -q "ts_exit_direct" src/xgw/net/nft.py && grep -q "CAP_NET_RAW" packaging/xgw.service && echo "А3.1 в коде: есть"; cd "$HOME/xgw-a31-test"
```

Ожидается: `c3c2e238cdba070cc0b91a26e9f5dce94c943e03c2c3d5e806ff5b6730a614fc` в начале строки хеша, «А3.1 в коде: есть». Записать хеш
коммита. Если не так: **стоп**, сообщить заказчику.

Шаг 1.3. Скрипт проверки. Скопируй команду целиком (до строки `A31_EOF` включительно):

```bash
cat > "$HOME/xgw-a31-test/a3check.py" <<'A31_EOF'
"""А3.1 XGW (ветка android-a3): запись трафика, VPN телефона, выходной узел Tailscale.

python3 a3check.py devices              телефон подключён и разрешил отладку
python3 a3check.py dns                  страна DNS-сервера, который видят сайты (адрес не печатается)
sudo python3 a3check.py press ДЕЙСТВИЕ [JSON]   кнопка панели (record/*, tailscale/exit, tailscale/direct)
sudo python3 a3check.py records         записи трафика в панели и идущая запись
sudo python3 a3check.py check-record    последняя запись: скачать из панели и проверить файл pcap
sudo python3 a3check.py tscard          выходной узел и устройства tailnet в панели
sudo python3 a3check.py lease-mac       MAC телефона в сети дома (по его адресу Wi-Fi)
python3 a3check.py install              поставить android/apk/XGW-0.1.17-a3.apk из клона
python3 a3check.py start                открыть приложение
python3 a3check.py texts                надписи на экране приложения (маскированные)
python3 a3check.py tap ID|ТЕКСТ         нажать кнопку приложения (id элемента или часть надписи)
python3 a3check.py system               надписи системного окна Android (разрешения)
python3 a3check.py tap-system ID|ТЕКСТ  нажать кнопку в системном окне Android
python3 a3check.py wait ТЕКСТ СЕКУНД    ждать надпись на экране приложения
python3 a3check.py vpn                  VPN телефона: процесс Xray, интерфейс, приложение мимо VPN
python3 a3check.py exit                 страна выхода телефона в интернет (адрес не печатается)
python3 a3check.py network              сеть телефона сейчас: Wi-Fi или мобильная
python3 a3check.py shot ИМЯ             снимок экрана в $HOME/xgw-a3-test/ИМЯ.png (не в отчёт!)
python3 a3check.py crash                падения приложения в журнале телефона
sudo python3 a3check.py phones          телефоны в панели (заходил / нет)
sudo python3 a3check.py events          события шлюза «с телефона …» и о телефонах
python3 a3check.py mask < ФАЙЛ          маскировать вывод
"""

from __future__ import annotations

import hashlib
import http.client
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
LIB = os.environ.get("XGW_LIB", "/opt/xgw/lib")
SUDO_USER = os.environ.get("SUDO_USER", "")


def _home() -> Path:
    """Под sudo HOME — у root; клон и каталог проверки — у того, кто запустил sudo."""
    if SUDO_USER:
        import pwd

        return Path(pwd.getpwnam(SUDO_USER).pw_dir)
    return Path.home()


HOME = _home()
CLONE = Path(os.environ.get("XGW_CLONE", str(HOME / "zcod" / "xgw")))
WORK = Path(os.environ.get("XGW_A3_DIR", str(HOME / "xgw-a31-test")))
APK = CLONE / "android" / "apk" / "XGW-0.1.17-a3.apk"
APK_SHA = "c3c2e238cdba070cc0b91a26e9f5dce94c943e03c2c3d5e806ff5b6730a614fc"
TUN_ADDRESS = "10.233.233.1"  # адрес интерфейса VPN приложения (XgwVpn.kt)
CONFIG = Path(os.environ.get("XGW_CONFIG", "/etc/xgw/config.toml"))
TOKEN_FILE = Path(os.environ.get("XGW_A3_TOKEN", "/var/lib/xgw/panel-token"))
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
    """adb — всегда от пользователя, а не от root: иначе root поднял бы свой сервер adb со
    своим ключом, и телефон спросил бы разрешение на отладку заново."""
    prefix = ["sudo", "-u", SUDO_USER] if SUDO_USER and os.geteuid() == 0 else []
    return run([*prefix, ADB, *args], timeout=timeout)


# --- телефон ---------------------------------------------------------------------------


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
    print("установлено:", f"{PACKAGE} {version.group(1)}" if version else "НЕТ")
    return 0 if version else 1


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


def cmd_dns() -> int:
    """Чей DNS-сервер видят сайты: edns.ip-api.com отвечает страной резолвера (имя — новое
    на каждый запрос у самого сервиса, кеш не мешает)."""
    ask = ("printf 'GET /json HTTP/1.0\\r\\nHost: edns.ip-api.com\\r\\n"
           "Connection: close\\r\\n\\r\\n'")
    out = adb("shell", f"{ask} | toybox nc -w 15 edns.ip-api.com 80", timeout=40).stdout
    body = out[out.find("{"):] if "{" in out else ""
    try:
        geo = str(((json.loads(body).get("dns") or {}).get("geo")) or "")
    except ValueError:
        geo = ""
    country = geo.split(" - ")[0].strip()
    print(f"DNS-сервер, который видят сайты: {country or 'НЕТ ОТВЕТА'}")
    return 0 if country else 1


ALLOWED = ("record/start", "record/stop", "tailscale/exit", "tailscale/direct")


def cmd_press(name: str, body: str) -> int:
    if name not in ALLOWED:
        print("в этом испытании — только " + ", ".join(ALLOWED))
        return 2
    code, text, _response = request("POST", f"/api/{name}", cookie=login(),
                                    body=json.loads(body) if body else {})
    result = json.loads(text) if code == 200 else {}
    masker = Masker()
    print(f"кнопка {name}: HTTP {code}, ok={result.get('ok')}; "
          f"{masker.mask(str(result.get('text') or ''))}")
    for note in result.get("notes") or []:
        print("  ", masker.mask(str(note)))
    return 0 if result.get("ok") else 1


def cmd_records() -> int:
    records = state().get("records") or {}
    active = records.get("active")
    print("идёт запись: " + (f"{active.get('label')} — {active.get('packets')} пакетов, "
                              f"{active.get('bytes')} байт" if active else "нет"))
    for item in records.get("files") or []:
        print(f"  файл {item.get('name')}: пакетов {item.get('packets')}, байт {item.get('bytes')}, "
              f"{item.get('why')}")
    return 0


def cmd_check_record() -> int:
    files = (state().get("records") or {}).get("files") or []
    if not files:
        print("записей нет")
        return 1
    name = files[0]["name"]
    port = cfg().panel.port
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    conn.request("GET", f"/records/{name}", headers={"Host": f"127.0.0.1:{port}",
                                                   "Cookie": login()})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    magic = data[:4].hex()
    unauth = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    unauth.request("GET", f"/records/{name}", headers={"Host": f"127.0.0.1:{port}"})
    closed = unauth.getresponse().status
    unauth.close()
    path = Path("/var/lib/xgw/records") / name
    mode = oct(path.stat().st_mode & 0o777) if path.exists() else "нет файла"
    print(f"скачивание: HTTP {response.status}, {len(data)} байт, заголовок pcap: "
          f"{'да' if magic == 'd4c3b2a1' else 'НЕТ'}; без входа: HTTP {closed}; права файла: {mode}")
    return 0 if response.status == 200 and magic == "d4c3b2a1" and closed == 401 else 1


def cmd_tscard() -> int:
    card = state().get("tailscale") or {}
    exit_ = card.get("exit") or {}
    word = {True: "да", False: "нет", None: "неизвестно"}
    print(f"Tailscale: {card.get('state')}; шлюз объявлен выходным узлом: "
          f"{word[exit_.get('advertised')]}; одобрен в консоли: {word[exit_.get('approved')]}")
    masker = Masker()
    for peer in card.get("peers") or []:
        print(f"  устройство tailnet «{peer.get('name')}» {masker.mask(peer.get('ip') or '')}"
              f" ({peer.get('os')}, {'в сети' if peer.get('online') else 'не в сети'}): "
              f"{'напрямую' if peer.get('direct') else 'через VPN'}")
    return 0


def cmd_lease_mac() -> int:
    """MAC телефона в аренде DHCP шлюза — по адресу его Wi-Fi."""
    route = adb("shell", "ip", "-4", "-o", "addr", "show", "wlan0").stdout
    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", route)
    if not match:
        print("у телефона нет адреса Wi-Fi — включите Wi-Fi")
        return 1
    leases = Path("/var/lib/xgw/dhcp.leases")
    for line in (leases.read_text(encoding="utf-8").splitlines() if leases.exists() else []):
        fields = line.split()
        if len(fields) >= 3 and fields[2] == match.group(1):
            print(f"MAC телефона: {fields[1]}")
            return 0
    print(f"адреса {match.group(1)} в арендах шлюза нет")
    return 1


def cmd_shot(name: str) -> int:
    path = WORK / f"{name}.png"
    prefix = ["sudo", "-u", SUDO_USER] if SUDO_USER and os.geteuid() == 0 else []
    path.write_bytes(subprocess.run([*prefix, ADB, "exec-out", "screencap", "-p"],
                                    capture_output=True, timeout=30).stdout)
    print(f"снимок: {path} (только для заказчика, не в отчёт)")
    return 0


def cmd_crash() -> int:
    log = adb("logcat", "-d", "-b", "crash").stdout
    ours = [line for line in log.splitlines() if PACKAGE in line]
    print(f"падений приложения в журнале телефона: {len(ours)}")
    for line in ours[-5:]:
        print(" ", Masker().mask(line))
    return 0


# --- панель шлюза ----------------------------------------------------------------------


def cfg():
    sys.path.insert(0, LIB)
    from xgw import config

    loaded, _warnings = config.load(CONFIG)
    return loaded


def request(method: str, path: str, *, cookie: str = "", body: dict | None = None):
    port = cfg().panel.port
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=90)
    headers = {"Host": f"127.0.0.1:{port}"}
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers.update({"Content-Type": "application/json", "X-XGW-Panel": "1",
                        "Origin": f"http://127.0.0.1:{port}"})
    try:
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8", "replace"), response
    finally:
        conn.close()


def login() -> str:
    token = TOKEN_FILE.read_text(encoding="ascii").strip()
    code, _text, response = request("GET", f"/?token={token}")
    if code != 303:
        raise SystemExit(f"вход в панель не удался: HTTP {code}")
    return response.getheader("Set-Cookie").split(";")[0]


def state() -> dict:
    code, text, _response = request("GET", "/api/state", cookie=login())
    if code != 200:
        raise SystemExit(f"состояние панели: HTTP {code}")
    return json.loads(text)


def cmd_phones() -> int:
    phones = state().get("phones") or {}
    pairing = phones.get("pairing") or {}
    print(f"Funnel: {'включён' if phones.get('funnel') else 'ВЫКЛЮЧЕН'}; код привязки в QR: "
          f"{'есть' if pairing.get('link') else 'нет'}; привязан по последнему коду: "
          f"{pairing.get('paired') or 'нет'}")
    for phone in phones.get("list") or []:
        print(f"  телефон «{phone.get('name')}» id={phone.get('id')}: "
              f"{'заходил' if phone.get('seen') else 'ещё не заходил'}")
    return 0


def cmd_events() -> int:
    masker = Masker()
    for event in (state().get("events") or [])[:30]:
        detail = str(event.get("detail") or "")
        if "телефон" in detail:
            stamp = time.strftime("%H:%M:%S", time.localtime(float(event.get("ts") or 0)))
            print(f"{stamp} {masker.mask(detail)}")
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
    WORK.mkdir(mode=0o700, exist_ok=True)
    command, rest = (argv[0], argv[1:]) if argv else ("", [])
    simple = {"devices": cmd_devices, "install": cmd_install, "start": cmd_start,
              "texts": cmd_texts, "crash": cmd_crash, "phones": cmd_phones,
              "events": cmd_events, "system": cmd_system, "vpn": cmd_vpn,
              "exit": cmd_exit, "network": cmd_network, "dns": cmd_dns, "records": cmd_records,
              "check-record": cmd_check_record, "tscard": cmd_tscard, "lease-mac": cmd_lease_mac}
    if command in simple:
        return simple[command]()
    if command == "tap" and rest:
        return cmd_tap(" ".join(rest))
    if command == "tap-system" and rest:
        return cmd_tap_system(" ".join(rest))
    if command == "press" and rest:
        return cmd_press(rest[0], rest[1] if len(rest) > 1 else "")
    if command == "wait" and len(rest) >= 2:
        return cmd_wait(" ".join(rest[:-1]), float(rest[-1]))
    if command == "shot" and rest:
        return cmd_shot(rest[0])
    if command == "mask":
        sys.stdout.write(Masker().mask(sys.stdin.read()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
A31_EOF
sha256sum "$HOME/xgw-a31-test/a3check.py"
```

Ожидается: `fcda6e9ae16404bd6dc510b9fc0f2de2451710c520d66e11f848d0ffdac8a5b7` в начале строки.
Если хеш другой: повторить шаг 1.3 один раз; снова другой — **стоп**.

## 2. Установка

Шаг 2.1. Код шлюза (из каталога кода):

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-a31-test/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-a31-test/after/install.txt" | tail -20; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-a31-test"
```

Ожидается: «код 0», «демон xgw запущен», «Xray-core 26.10.21 уже лежит» (Xray не меняется).
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику.

Шаг 2.2. Шлюз в порядке (до 5 минут):

```bash
for i in $(seq 30); do sudo xgw status 2>&1 | grep -q '^Состояние: HEALTHY' && break; sleep 10; done; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | python3 "$HOME/xgw-a31-test/a3check.py" mask | tee "$HOME/xgw-a31-test/after/state-install.txt"; systemctl show xgw -p CapabilityBoundingSet | tr ' ' '\n' | grep -c cap_net_raw | sed 's/^/право CAP_NET_RAW у службы xgw: /'; sudo xgw diag | tail -1
```

Ожидается: «Состояние: HEALTHY …» (или как было до установки — записать), «Xray 26.10.21:
отвечает», «Перехват: включён — …», «право CAP_NET_RAW у службы xgw: 1», «FAIL — 0».

Шаг 2.3. Приложение на телефоне. **Скажи заказчику**: «Подключите телефон к шлюзу кабелем
(„Отладка по USB“ включена).» Затем:

```bash
python3 "$HOME/xgw-a31-test/a3check.py" devices; python3 "$HOME/xgw-a31-test/a3check.py" install | tee "$HOME/xgw-a31-test/after/app.txt"; python3 "$HOME/xgw-a31-test/a3check.py" start | grep -E 'VPN телефона|Серверов|Шлюз не принял' | tee -a "$HOME/xgw-a31-test/after/app.txt"
```

Ожидается: «телефон: подключён», «установка: Success», «установлено: net.xgw.android
0.1.17-a3»; на экране — карточка «VPN телефона», «Серверов: N …»; «Шлюз не принял» — нет.

## 3. Запись трафика телефона (только при согласии на пункт 2)

Шаг 3.1. Телефон — в домашнем Wi-Fi (**спроси заказчика**, если не уверен). MAC телефона:

```bash
sudo python3 "$HOME/xgw-a31-test/a3check.py" lease-mac
```

Ожидается: «MAC телефона: xx:xx:…» — подставь его вместо `MAC` ниже (в отчёт MAC не
писать). «нет адреса Wi-Fi» — попроси включить Wi-Fi и повтори.

Шаг 3.2. Записать минуту:

```bash
sudo python3 "$HOME/xgw-a31-test/a3check.py" press record/start '{"mac": "MAC", "seconds": 60}' | tee "$HOME/xgw-a31-test/after/record.txt"
```

Ожидается: «кнопка record/start: HTTP 200, ok=True; Записываю трафик «…» — 1 мин».
Если «нет права на запись трафика (CAP_NET_RAW)» — **дефект «нет права на запись»**,
записать и шаг 3 пропустить.

Сразу **попроси заказчика**: «Откройте на телефоне пару сайтов в браузере.» Через 70 секунд:

```bash
sleep 70; sudo python3 "$HOME/xgw-a31-test/a3check.py" records | tee -a "$HOME/xgw-a31-test/after/record.txt"; sudo python3 "$HOME/xgw-a31-test/a3check.py" check-record | tee -a "$HOME/xgw-a31-test/after/record.txt"
```

Ожидается: «идёт запись: нет»; строка «файл …: пакетов N, байт M, время вышло» — N больше
0 (обычно сотни); «скачивание: HTTP 200, … байт, заголовок pcap: да; без входа: HTTP 401;
права файла: 0o600».
Если пакетов 0 — **дефект «запись пустая»**. Остальное не так — записать как есть.

Шаг 3.3. **Попроси заказчика**: «Откройте панель XGW, карточку „Устройства“: у телефона в
строке есть красная точка „Записать трафик“, а внизу — „Записи трафика“ с файлом (значки
„скачать“ и „удалить“)? Если хотите, удалите запись крестиком.» Записать ответ.

## 4. VPN XGW в приложении — пульт (только при согласии на пункт 3)

Шаг 4.1. **Скажи заказчику**: «Выключите на телефоне VPN в приложении Tailscale (Tailscale →
выключить). Телефон — в домашнем Wi-Fi.» Затем включить VPN XGW:

```bash
python3 "$HOME/xgw-a31-test/a3check.py" tap vpn-power; sleep 3; python3 "$HOME/xgw-a31-test/a3check.py" system | tee "$HOME/xgw-a31-test/after/vpn-consent.txt"
```

Ожидается: «нажато: «Включить VPN телефона»». Если в системном окне вопрос об уведомлениях
(«Разрешить приложению XGW отправлять уведомления?») — разрешение спрашивается **до**
разрешения на VPN, как и задумано:

```bash
python3 "$HOME/xgw-a31-test/a3check.py" tap-system com.android.permissioncontroller:id/permission_allow_button; sleep 3; python3 "$HOME/xgw-a31-test/a3check.py" system | tee -a "$HOME/xgw-a31-test/after/vpn-consent.txt"
```

Если затем окно «Запрос на подключение» — `python3 "$HOME/xgw-a31-test/a3check.py"
tap-system android:id/button1`. (Если окон нет — разрешения уже были; записать.)

Шаг 4.2. VPN и пульт по Wi-Fi:

```bash
python3 "$HOME/xgw-a31-test/a3check.py" wait "VPN телефона включён" 30 | tee "$HOME/xgw-a31-test/after/vpn-wifi.txt"; python3 "$HOME/xgw-a31-test/a3check.py" vpn | tee -a "$HOME/xgw-a31-test/after/vpn-wifi.txt"; python3 "$HOME/xgw-a31-test/a3check.py" exit | tee -a "$HOME/xgw-a31-test/after/vpn-wifi.txt"; sleep 20; python3 "$HOME/xgw-a31-test/a3check.py" texts | grep -E 'Нет связи|Состояние на|Tailscale на телефоне|Пульт ходит|скрыто' | tee -a "$HOME/xgw-a31-test/after/vpn-wifi.txt"
```

Ожидается: «VPN телефона включён», «Xray в приложении: работает», страна выхода — YY
(записать); строка «Состояние на ЧЧ:ММ:СС», **без** «Нет связи» (дефект 1 отчёта А3
исправлен); в карточке — «Tailscale на телефоне в это время не работает…»; строки
«Уведомление «VPN XGW» скрыто» — нет.
Если «Нет связи со шлюзом» — подождать 30 с и повторить последнюю команду; снова — **дефект
«пульт по Wi-Fi с VPN телефона не работает»**, записать текст ошибки целиком.

Шаг 4.3. **Попроси заказчика**: «Опустите шторку: есть уведомление „VPN XGW — Включён:
серверов N“ с кнопкой „Выключить“?» Записать ответ (дефект 3 отчёта А3). Нет —
**дефект «нет уведомления»**.

Шаг 4.4. По мобильной сети. **Скажи заказчику**: «Выключите Wi-Fi.» Затем:

```bash
sleep 30; python3 "$HOME/xgw-a31-test/a3check.py" network | tee "$HOME/xgw-a31-test/after/vpn-mobile.txt"; python3 "$HOME/xgw-a31-test/a3check.py" vpn | head -1 | tee -a "$HOME/xgw-a31-test/after/vpn-mobile.txt"; python3 "$HOME/xgw-a31-test/a3check.py" exit | tee -a "$HOME/xgw-a31-test/after/vpn-mobile.txt"; sleep 20; python3 "$HOME/xgw-a31-test/a3check.py" texts | grep -E 'Нет связи|Состояние на|Пульт ходит|VPN телефона' | tee -a "$HOME/xgw-a31-test/after/vpn-mobile.txt"
```

Ожидается: «Wi-Fi телефона: выключен», Xray работает, страна — YY; пульт: «Состояние на …»
без «Нет связи»; строка «Пульт ходит к шлюзу через VPN телефона» — может быть или нет
(записать: это значит, что напрямую Funnel с мобильной сети не открылся, а через VPN — да).
Если «Нет связи» — подождать 30 с и повторить последнюю команду; снова — **дефект «пульт по
мобильной сети с VPN телефона не работает»**, записать текст ошибки целиком.
Если «Xray в приложении: НЕ ЗАПУЩЕН» — записать текст карточки VPN (`texts | grep VPN`) — там
причина.

## 5. Tailscale забирает VPN (только при согласии на пункт 3)

Шаг 5.1. **Скажи заказчику**: «Включите Wi-Fi обратно и включите VPN в приложении Tailscale
(Android спросит, заменить ли VPN — согласитесь).» Через 20 с:

```bash
sleep 20; python3 "$HOME/xgw-a31-test/a3check.py" vpn | head -1 | tee "$HOME/xgw-a31-test/after/revoke.txt"; python3 "$HOME/xgw-a31-test/a3check.py" start | grep -E 'VPN телефона|Android отдал' | tee -a "$HOME/xgw-a31-test/after/revoke.txt"
```

Ожидается: «Xray в приложении: НЕ ЗАПУЩЕН»; карточка: «VPN телефона выключен» и «Android
отдал VPN другому приложению (например, Tailscale)…».
**Попроси заказчика**: «В шторке есть уведомление „VPN XGW — VPN выключен: Android отдал VPN
другому приложению…“?» Записать ответ.

## 6. Выходной узел: включить (только при согласии на пункт 4)

Шаг 6.1. Tailscale на телефоне включён (шаг 5.1 или заказчик включил сейчас). Шлюз — выходной
узел:

```bash
sudo python3 "$HOME/xgw-a31-test/a3check.py" press tailscale/exit '{"on": true}' | tee "$HOME/xgw-a31-test/after/exit.txt"; sleep 5; sudo python3 "$HOME/xgw-a31-test/a3check.py" tscard | tee -a "$HOME/xgw-a31-test/after/exit.txt"
```

Ожидается: «кнопка tailscale/exit: HTTP 200, ok=True; Шлюз объявлен выходным узлом
tailnet» и две подсказки; «объявлен выходным узлом: да»; «одобрен в консоли: нет» (или «да»,
если в tailnet есть autoApprovers — записать); список устройств tailnet, среди них телефон
(«через VPN»).

Шаг 6.2. **Попроси заказчика** (дословно): «Откройте консоль Tailscale
(login.tailscale.com/admin/machines) → шлюз → „…“ → Edit route settings → включите „Use as
exit node“ → Save. Скажите, когда готово.» Затем:

```bash
sleep 30; sudo python3 "$HOME/xgw-a31-test/a3check.py" tscard | head -1 | tee -a "$HOME/xgw-a31-test/after/exit.txt"
```

Ожидается: «одобрен в консоли: да». «нет» — подождать минуту и повторить; снова «нет» —
записать как наблюдение и продолжать (одобрение могло не дойти до шлюза — телефон покажет
сам).

## 7. Выходной узел на телефоне (только при согласии на пункт 4)

Шаг 7.1. **Скажи заказчику**: «В приложении Tailscale на телефоне: Exit node → выберите
шлюз. Wi-Fi выключите (мобильная сеть).» Через 30 с:

```bash
sleep 30; python3 "$HOME/xgw-a31-test/a3check.py" network | tee "$HOME/xgw-a31-test/after/exit-phone.txt"; python3 "$HOME/xgw-a31-test/a3check.py" exit | tee -a "$HOME/xgw-a31-test/after/exit-phone.txt"; python3 "$HOME/xgw-a31-test/a3check.py" dns | tee -a "$HOME/xgw-a31-test/after/exit-phone.txt"; sudo xgw status 2>&1 | grep -E '^Основной|основной' | head -1 | python3 "$HOME/xgw-a31-test/a3check.py" mask | tee -a "$HOME/xgw-a31-test/after/exit-phone.txt"; python3 "$HOME/xgw-a31-test/a3check.py" start | grep -E 'Нет связи|Состояние на' | tee -a "$HOME/xgw-a31-test/after/exit-phone.txt"
```

Ожидается: «Wi-Fi телефона: выключен»; «страна выхода телефона: XX» — страна выхода
**основного сервера шлюза** (как у устройств дома, не RU); «DNS-сервер, который видят
сайты: …» — страна **не** RU (записать как есть); пульт: «Состояние на …» без «Нет связи»
(пульт идёт через Tailscale).
Если страна выхода RU — **дефект «выходной узел идёт мимо Xray»**: записать
`sudo nft list chain ip xgw prerouting | head -12` (адресов серверов в выводе нет).
Если DNS-сервер — RU (или страна провайдера заказчика): **наблюдение «DNS через выходной узел
идёт мимо Xray»** (ASSUMPTIONS п. 230(е)) — записать, не дефект этой программы.
«НЕТ ОТВЕТА» в `exit` — повторить через 30 с; снова — **дефект «нет интернета через
выходной узел»**: попросить заказчика выключить Exit node на телефоне, записать.

## 8. «Напрямую» для телефона (только при согласии на пункт 4)

Шаг 8.1. Адрес телефона в tailnet — в выводе `tscard` (шаг 6.1, строка с телефоном,
`100.x.y.N` — в маскированном виде); возьми **настоящий** адрес так:

```bash
sudo python3 -c "import sys,json,subprocess; d=json.loads(subprocess.run(['tailscale','status','--json'],capture_output=True,text=True).stdout); [print(p['HostName'], [i for i in p['TailscaleIPs'] if ':' not in i][0]) for p in (d.get('Peer') or {}).values() if p.get('OS')=='android']"
```

Подставь адрес телефона (100.…) вместо `IP` (в отчёт не писать):

```bash
sudo python3 "$HOME/xgw-a31-test/a3check.py" press tailscale/direct '{"ip": "IP", "name": "phone", "direct": true}' | tee "$HOME/xgw-a31-test/after/direct.txt"; sleep 10; python3 "$HOME/xgw-a31-test/a3check.py" exit | sed 's/^/напрямую: /' | tee -a "$HOME/xgw-a31-test/after/direct.txt"; sudo python3 "$HOME/xgw-a31-test/a3check.py" press tailscale/direct '{"ip": "IP", "direct": false}' | tee -a "$HOME/xgw-a31-test/after/direct.txt"; sleep 10; python3 "$HOME/xgw-a31-test/a3check.py" exit | sed 's/^/через VPN: /' | tee -a "$HOME/xgw-a31-test/after/direct.txt"
```

Ожидается: «ok=True; «phone» выходит в интернет через шлюз напрямую»; «напрямую: страна
выхода телефона: RU» (страна домашнего провайдера); «ok=True; «phone» выходит в интернет
через Xray шлюза»; «через VPN: страна выхода телефона: XX» (как в 7.1).
Если «напрямую» всё равно XX — подождать 30 с (старые соединения) и повторить `exit`; снова XX
— **дефект «напрямую не работает»**. Если «через VPN» осталось RU — **дефект «не вернулось в
VPN»**.

## 9. Итог

Шаг 9.1.

```bash
sudo xgw diag | tail -1; sudo xgw status | grep -E '^Состояние|^Xray|Перехват:' | python3 "$HOME/xgw-a31-test/a3check.py" mask | tee "$HOME/xgw-a31-test/after/final.txt"; python3 "$HOME/xgw-a31-test/a3check.py" crash | tee -a "$HOME/xgw-a31-test/after/final.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-a31-test/install-time.txt")" --no-pager 2>/dev/null | grep -c Traceback | sed 's/^/Traceback: /'
```

Ожидается: «FAIL — 0», состояние как в 2.2, «Перехват: включён», падений приложения 0,
Traceback 0.

Шаг 9.2. **Спроси заказчика**: «Оставить шлюз выходным узлом? На телефоне — что включить:
Tailscale с выходным узлом через шлюз, VPN XGW или ничего?» Если шлюз выходным узлом не
оставлять:

```bash
sudo python3 "$HOME/xgw-a31-test/a3check.py" press tailscale/exit '{"on": false}'
```

Затем **скажи**: «Испытание закончено. „Отладку по USB“ можно выключить.»

## 10. Если что-то пошло не так

- У телефона пропал интернет на выходном узле — попросить заказчика выключить Exit node в
  Tailscale; затем `sudo python3 "$HOME/xgw-a31-test/a3check.py" press tailscale/exit '{"on":
  false}'`.
- Интернет дома пропал после установки — `sudo xgw status`, сообщить заказчику; ничего не
  откатывать без него.

## 11. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-a3.1-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`android-a3`), коммит «Отчёт А3.1: запись трафика, VPN телефона, выходной узел», `git push`.
Шаблон:

```markdown
# Отчёт А3.1: запись трафика, VPN телефона, выходной узел (ветка android-a3)

Код: <хеш>. APK sha256 <первые 8 знаков> — совпал. Установка: <дата время>, код <…>.
Телефон: <модель>, Android <…>. Согласие заказчика: пункты <…>.

## Итог
<4–8 предложений по трём частям.>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 2.1–2.2 установка | … | HEALTHY, CAP_NET_RAW |
| 2.3 приложение | … | … |
| 3.2 запись трафика | … | пакетов N, pcap да, без входа 401, 0600 |
| 3.3 панель глазами заказчика | … | … |
| 4.2 VPN XGW + пульт, Wi-Fi | … | страна YY, «Нет связи» нет |
| 4.3 уведомление | … | … |
| 4.4 VPN XGW + пульт, мобильная сеть | … | путь пульта |
| 5.1 Tailscale забрал VPN | … | сообщение, уведомление |
| 6.1–6.2 выходной узел на шлюзе | … | объявлен, одобрен |
| 7.1 выходной узел на телефоне | … | страна XX, DNS … , пульт |
| 8.1 напрямую и обратно | … | RU → XX |
| 9.1 итог | … | FAIL — 0 |

## Выводы шагов
<содержимое файлов after/*.txt, по заголовку на файл>

## Дефекты
<или «Не обнаружены»>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние
<шлюз выходным узлом — да/нет; телефон — Tailscale / VPN XGW / ничего; запись удалена — да/нет.>
```

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
