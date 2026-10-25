# Программа испытаний XGW: VPN телефона в приложении (А3)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§10). Пути в командах — только абсолютные (`$HOME/xgw-a3-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома, XGW 0.1.17 (код шлюза в этом испытании
**не меняется** и не ставится). Funnel для приложения включён, телефон заказчика —
**Samsung Galaxy S25 Ultra** — привязан к приложению XGW (испытание А2). Программа `adb` на
шлюзе стоит с испытания А2. Клон репозитория — `~/zcod/xgw`.

Что нового (ASSUMPTIONS п. 227, фаза А3 `ANDROID_APP_PLAN.md`): **VPN самого телефона в
приложении XGW**. Файл установки — `android/apk/XGW-0.1.17-a3.apk` (ставится поверх А2,
привязка сохраняется). В приложении вверху — карточка «VPN телефона»:

- «Включить VPN телефона» — Android один раз спрашивает разрешение («Запрос на подключение» →
  «ОК») и разрешение на уведомления; весь интернет телефона идёт через Xray 26.10.21 внутри
  приложения на серверы шлюза (их список приложение берёт у шлюза и хранит);
- в строке состояния — значок ключа, в уведомлениях — «VPN XGW: Включён: серверов N» с
  кнопкой «Выключить»;
- «Обновить серверы» — свежий список со шлюза (VPN не выключается);
- «VPN всегда» — открывает настройки VPN Android («Постоянная VPN»);
- само приложение и его Xray — мимо VPN телефона: пульт шлюза работает и с включённым VPN.

Как управляется телефон: как в А2 — телефон подключён к шлюзу кабелем USB, «Отладка по USB»
включена. Скрипт `a3check.py` через `adb` ставит приложение, читает надписи на экране,
нажимает кнопки, показывает состояние VPN телефона и **страну**, из которой телефон выходит в
интернет (запрос к ip-api.com; сам адрес не печатается). Что требует рук заказчика —
разрешения Android, Wi-Fi и мобильная сеть, настройки, перезагрузка телефона — отдельные
шаги «Попроси заказчика».

Цели:

1. Подготовка: телефон подключён, приложение обновлено, привязка на месте (шаги 1–3).
2. Список серверов со шлюза (шаг 4).
3. VPN телефона по Wi-Fi: разрешения, Xray, интерфейс, страна выхода, пульт (шаг 5).
4. VPN по мобильной сети: страна выхода с VPN и без, пульт (шаг 6).
5. Переход Wi-Fi ↔ мобильная сеть с включённым VPN (шаг 7).
6. Выключение из уведомления (шаг 8).
7. «Постоянная VPN» и перезагрузка телефона (шаг 9).
8. Итог (шаг 10), отчёт (§11).

## 0. Запрещено

- На шлюзе: `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh`, `reboot`, сон
  машины — **никогда**; кнопки панели не нажимать; службы `xgw*`, `tailscaled`,
  NetworkManager, `ssh` не трогать; команды Tailscale — только `tailscale status`.
- В приложении: нажимать только кнопки, названные в шагах. «Выключить VPN шлюза» —
  **никогда**. «Отвязать телефон» — **никогда**.
- Через `a3check.py tap-system` — только кнопки, названные в шагах (разрешение на VPN и на
  уведомления).
- На телефоне: ничего, кроме приложения XGW и команд `adb` из шагов. Не удалять и не менять
  другие приложения; настройки меняет только сам заказчик по просьбе из шагов. `adb reboot` —
  только в шаге 9.3 и только при согласии на пункт 6.
- Править `/etc/xgw/*`, `/var/lib/xgw/*`, код XGW. Коммитить что-либо, кроме отчёта (§11).
- В отчёт и в Git не класть снимки экрана (`*.png` в `~/xgw-a3-test`).
- Писать в отчёт: адреса tailnet (`100.x.y.z`), имена `*.ts.net`, имена устройств, кроме
  модели телефона, внешние IP, ключи, серийный номер телефона, адреса подписок, IP и домены
  серверов VPN. Коды стран (`AE`, `RU` и т. п.) — можно. Выводы — только через
  `a3check.py mask` (скрипт маскирует сам).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю VPN телефона в приложении XGW на вашем Galaxy S25 Ultra. Шлюз не трогаю. По
пунктам:
(1) Телефон нужно снова подключить к шлюзу кабелем с включённой „Отладкой по USB“, как в
прошлый раз.
(2) Обновлю приложение XGW на телефоне (около 20 МБ) — привязка к шлюзу сохранится.
(3) Включу VPN телефона: Android спросит разрешение на VPN и на уведомления — я нажму „ОК“
и „Разрешить“ сам через кабель или попрошу вас. Проверю, что интернет телефона идёт через
сервер VPN (по стране выхода, адрес не записывается) и что пульт шлюза работает.
(4) Попрошу выключить на телефоне Wi-Fi и проверить VPN по мобильной сети: сначала с VPN,
потом минуту без него, потом снова с VPN. Другой VPN на телефоне (Happ и т. п.) на время
испытания нужно выключить.
(5) Попрошу включить и выключить Wi-Fi при включённом VPN — проверю, что интернет не
пропадает.
(6) Попрошу включить в настройках Android „Постоянная VPN“ для XGW и перезагрузить
телефон — проверю, что VPN включился сам. Потом скажете, оставить ли „Постоянную VPN“.
(7) В конце скажете, оставить VPN телефона включённым или выключить.
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1, 2 или 3 — **стоп**, испытание не проводится.
- Против пункта 4 — шаг 6 пропустить; против 5 — шаг 7; против 6 — шаг 9.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-a3-test/after" && chmod 700 "$HOME/xgw-a3-test" && cd "$HOME/xgw-a3-test" && date; adb version | head -1
```

Ожидается: «sudo без пароля: да», дата и `Android Debug Bridge version 1.0.…`.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без
пароля на время испытаний. Если `adb` нет: **стоп**, сообщить заказчику (ставился в А2).

Шаг 1.2. Код и файл приложения:

```bash
cd ~/zcod/xgw && git fetch && git checkout android-a3 && git pull --ff-only && git log -1 --format='%h %s'; sha256sum android/apk/XGW-0.1.17-a3.apk; cd "$HOME/xgw-a3-test"
```

Ожидается: `9b96501106e344358544f12b3f92cefb1848e1547452a3eb574558bc832a7d9b` в начале строки хеша. Записать хеш коммита.
Если хеш другой или ветки нет: **стоп**, сообщить заказчику.

Шаг 1.3. Скрипт проверки. Скопируй команду целиком (до строки `A3_EOF` включительно):

```bash
cat > "$HOME/xgw-a3-test/a3check.py" <<'A3_EOF'
"""А3 XGW (ветка android-a3): VPN телефона в приложении, управление через adb.

python3 a3check.py devices              телефон подключён и разрешил отладку
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
WORK = Path(os.environ.get("XGW_A3_DIR", str(HOME / "xgw-a3-test")))
APK = CLONE / "android" / "apk" / "XGW-0.1.17-a3.apk"
APK_SHA = "9b96501106e344358544f12b3f92cefb1848e1547452a3eb574558bc832a7d9b"
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
              "exit": cmd_exit, "network": cmd_network}
    if command in simple:
        return simple[command]()
    if command == "tap" and rest:
        return cmd_tap(" ".join(rest))
    if command == "tap-system" and rest:
        return cmd_tap_system(" ".join(rest))
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
A3_EOF
sha256sum "$HOME/xgw-a3-test/a3check.py"
```

Ожидается: `6e1a53a0df24521d5c5123c9386c5720d6a2390bd60775b66b4252ed33d85823` в начале строки.
Если хеш другой: файл скопирован не целиком — повторить шаг 1.3 один раз; если снова другой —
**стоп**, сообщить заказчику.

## 2. Телефон подключён

Шаг 2.1. **Скажи заказчику** (дословно): «Подключите телефон к шлюзу кабелем. Если „Отладка
по USB“ выключена: Настройки → Параметры разработчика → „Отладка по USB“ — включить. На
вопрос „Разрешить отладку по USB?“ нажмите „Разрешить“.»

Шаг 2.2.

```bash
python3 "$HOME/xgw-a3-test/a3check.py" devices | tee "$HOME/xgw-a3-test/after/devices.txt"
```

Ожидается: «телефон: подключён, отладка разрешена», «модель: SM-S938B; Android …».
Если «ЖДЁТ РАЗРЕШЕНИЯ» — попросить заказчика нажать «Разрешить» и повторить; «НЕ ВИДЕН» —
попросить переподключить кабель и повторить; второй раз так же — **стоп**.

## 3. Обновление приложения

Шаг 3.1.

```bash
python3 "$HOME/xgw-a3-test/a3check.py" install | tee "$HOME/xgw-a3-test/after/install.txt"; python3 "$HOME/xgw-a3-test/a3check.py" start | tee -a "$HOME/xgw-a3-test/after/install.txt"
```

Ожидается: «установка: Success», «установлено: net.xgw.android 0.1.17-a3»; на экране —
«VPN телефона выключен», «Включить VPN телефона», «Обновить серверы», «VPN всегда», ниже —
пульт шлюза («VPN шлюза включён», «Серверы в работе», …) **без** «Шлюз не принял запрос»
(привязка сохранилась).

Если не так:

- «INSTALL_FAILED_UPDATE_INCOMPATIBLE» — **стоп**, сообщить заказчику (подпись не та).
- На экране «Сканировать QR-код» или «Шлюз не принял запрос» — привязка пропала:
  **дефект**, записать; дальше — **спросить заказчика**, привязать ли заново (как в А2: панель
  → «Привязать телефон», в приложении — «Сканировать QR-код»).

## 4. Список серверов со шлюза

Шаг 4.1.

```bash
sleep 10; python3 "$HOME/xgw-a3-test/a3check.py" texts | grep -E 'VPN телефона|Серверов|Списка серверов' | tee "$HOME/xgw-a3-test/after/servers.txt"
```

Ожидается: «Серверов: N · список от сегодня ЧЧ:ММ» — N не меньше 1 (столько серверов в работе
на шлюзе, кроме тех, что идут через sing-box). Записать N.

Если «Списка серверов ещё нет»:

```bash
python3 "$HOME/xgw-a3-test/a3check.py" tap vpn-fetch; sleep 20; python3 "$HOME/xgw-a3-test/a3check.py" texts | grep -E 'Серверов|Списка серверов|Xray|шлюз' | tee -a "$HOME/xgw-a3-test/after/servers.txt"
```

Список так и не появился — **дефект «список серверов не приходит»**: записать вывод, шаги 5–9
пропустить, шаг 10.

## 5. VPN телефона по Wi-Fi

Шаг 5.1. До VPN (телефон в домашнем Wi-Fi, другой VPN выключен — **спроси заказчика**, так
ли):

```bash
python3 "$HOME/xgw-a3-test/a3check.py" network | tee "$HOME/xgw-a3-test/after/wifi.txt"; python3 "$HOME/xgw-a3-test/a3check.py" vpn | tee -a "$HOME/xgw-a3-test/after/wifi.txt"; python3 "$HOME/xgw-a3-test/a3check.py" exit | tee -a "$HOME/xgw-a3-test/after/wifi.txt"
```

Ожидается: «Wi-Fi телефона: подключён», «Xray в приложении: НЕ ЗАПУЩЕН», «страна выхода
телефона: XX» — страна сервера **шлюза** (дома телефон и так идёт через VPN шлюза). Записать XX.

Шаг 5.2. Включить VPN телефона:

```bash
python3 "$HOME/xgw-a3-test/a3check.py" tap vpn-power; sleep 3; python3 "$HOME/xgw-a3-test/a3check.py" system | tee "$HOME/xgw-a3-test/after/consent.txt"
```

Ожидается: «нажато: «Включить VPN телефона»» и системное окно с вопросом о подключении VPN
(«Запрос на подключение» / «Connection request») и кнопками.

- Окно есть:

  ```bash
  python3 "$HOME/xgw-a3-test/a3check.py" tap-system android:id/button1; sleep 3; python3 "$HOME/xgw-a3-test/a3check.py" system | tee -a "$HOME/xgw-a3-test/after/consent.txt"
  ```

  Ожидается: «нажато в системном окне: «ОК»» (или «OK»), затем окно «Разрешить приложению XGW
  отправлять вам уведомления?». Если кнопку не нашло — **попроси заказчика** нажать «ОК».
- Окно уведомлений:

  ```bash
  python3 "$HOME/xgw-a3-test/a3check.py" tap-system com.android.permissioncontroller:id/permission_allow_button; sleep 2; python3 "$HOME/xgw-a3-test/a3check.py" system
  ```

  Ожидается: «нажато в системном окне: «Разрешить»», затем «системного окна нет». Не нашло —
  **попроси заказчика** нажать «Разрешить».
- Окна нет совсем (разрешение уже было) — сразу шаг 5.3.

Шаг 5.3. VPN работает:

```bash
python3 "$HOME/xgw-a3-test/a3check.py" wait "VPN телефона включён" 30 | tee "$HOME/xgw-a3-test/after/vpn-wifi.txt"; python3 "$HOME/xgw-a3-test/a3check.py" vpn | tee -a "$HOME/xgw-a3-test/after/vpn-wifi.txt"; python3 "$HOME/xgw-a3-test/a3check.py" exit | tee -a "$HOME/xgw-a3-test/after/vpn-wifi.txt"
```

Ожидается: «VPN телефона включён» на экране через N с (N ≤ 15); «Xray в приложении:
работает»; «интерфейс VPN (10.233.233.1): tun0» (имя может быть другим — записать); «приложение
XGW мимо своего VPN: да» (или «не видно» — записать как наблюдение); «страна выхода телефона:
YY» — страна сервера VPN телефона. Записать YY (может совпасть с XX из 5.1).

Если не так:

- «НЕ ПОЯВИЛОСЬ за 30 с» — на экране текст ошибки карточки VPN: **дефект «VPN телефона не
  включается»**, записать вывод `texts` и `crash`, шаги 6–9 пропустить.
- «страна выхода телефона: НЕТ ОТВЕТА» — повторить `exit` через 20 с; снова нет — **дефект
  «с VPN телефона нет интернета»**: сразу `python3 "$HOME/xgw-a3-test/a3check.py" tap vpn-power`
  (выключить VPN), записать, шаги 6–9 пропустить.

Шаг 5.4. **Попроси заказчика**: «Откройте на телефоне в браузере любой сайт и, если хотите,
видео. Открывается? Скорость нормальная?» Записать ответ (дома трафик телефона идёт через VPN
телефона, а его соединение с сервером — ещё и через VPN шлюза: возможно, медленнее —
записать как наблюдение).

Шаг 5.5. Пульт шлюза с включённым VPN телефона:

```bash
python3 "$HOME/xgw-a3-test/a3check.py" texts | grep -E 'Нет связи|Серверы в|VPN шлюза|Состояние на' | tee "$HOME/xgw-a3-test/after/pult-wifi.txt"; sleep 15; python3 "$HOME/xgw-a3-test/a3check.py" texts | grep -E 'Состояние на' | tee -a "$HOME/xgw-a3-test/after/pult-wifi.txt"
```

Ожидается: «VPN шлюза включён», строка «Состояние на ЧЧ:ММ:СС» — во втором выводе время
позже (пульт обновляется); строки «Нет связи» нет.
Если «Нет связи со шлюзом» — **дефект «пульт не работает с VPN телефона»**: записать.

## 6. Мобильная сеть (только при согласии на пункт 4)

Шаг 6.1. **Скажи заказчику**: «Выключите на телефоне Wi-Fi (мобильный интернет включён, другой
VPN выключен). Скажите, когда готово.» Затем:

```bash
sleep 20; python3 "$HOME/xgw-a3-test/a3check.py" network | tee "$HOME/xgw-a3-test/after/mobile.txt"; python3 "$HOME/xgw-a3-test/a3check.py" vpn | tee -a "$HOME/xgw-a3-test/after/mobile.txt"; python3 "$HOME/xgw-a3-test/a3check.py" exit | tee -a "$HOME/xgw-a3-test/after/mobile.txt"
```

Ожидается: «Wi-Fi телефона: выключен»; «Xray в приложении: работает»; страна выхода — YY
(сервер VPN телефона).
Если «НЕТ ОТВЕТА» — повторить `exit` через 30 с; снова нет — **дефект «VPN не пережил переход
на мобильную сеть»**, записать.

Шаг 6.2. Без VPN телефона — минуту:

```bash
python3 "$HOME/xgw-a3-test/a3check.py" tap vpn-power; sleep 3; python3 "$HOME/xgw-a3-test/a3check.py" vpn | head -1 | tee -a "$HOME/xgw-a3-test/after/mobile.txt"; python3 "$HOME/xgw-a3-test/a3check.py" exit | sed 's/^/без VPN: /' | tee -a "$HOME/xgw-a3-test/after/mobile.txt"
```

Ожидается: «нажато: «Выключить VPN телефона»», «Xray в приложении: НЕ ЗАПУЩЕН», «без VPN:
страна выхода телефона: ZZ» — страна, где заказчик (обычно `RU`). Записать ZZ: если ZZ = YY,
это **наблюдение** (сервер в той же стране), не дефект.

Шаг 6.3. Снова с VPN и пульт по мобильной сети:

```bash
python3 "$HOME/xgw-a3-test/a3check.py" tap vpn-power; python3 "$HOME/xgw-a3-test/a3check.py" wait "VPN телефона включён" 30 | tee -a "$HOME/xgw-a3-test/after/mobile.txt"; python3 "$HOME/xgw-a3-test/a3check.py" exit | tee -a "$HOME/xgw-a3-test/after/mobile.txt"; python3 "$HOME/xgw-a3-test/a3check.py" texts | grep -E 'Нет связи|Состояние на' | tee -a "$HOME/xgw-a3-test/after/mobile.txt"
```

Ожидается: окна разрешения нет (оно было один раз); «VPN телефона включён»; страна — YY;
«Состояние на …», без «Нет связи».

## 7. Переход Wi-Fi ↔ мобильная сеть (только при согласии на пункт 5)

Шаг 7.1. **Скажи заказчику**: «Включите Wi-Fi (VPN телефона не трогайте).» Затем:

```bash
sleep 30; python3 "$HOME/xgw-a3-test/a3check.py" network | tee "$HOME/xgw-a3-test/after/switch.txt"; python3 "$HOME/xgw-a3-test/a3check.py" vpn | head -1 | tee -a "$HOME/xgw-a3-test/after/switch.txt"; python3 "$HOME/xgw-a3-test/a3check.py" exit | tee -a "$HOME/xgw-a3-test/after/switch.txt"
```

Ожидается: «Wi-Fi телефона: подключён», «Xray в приложении: работает», страна — YY.

Шаг 7.2. **Скажи заказчику**: «Выключите Wi-Fi.» Повторить команду шага 7.1 с `tee -a`
(дописать в тот же файл). Ожидается: «Wi-Fi телефона: выключен», Xray работает, страна — YY.

Шаг 7.3. **Скажи заказчику**: «Включите Wi-Fi обратно.»

Если в 7.1 или 7.2 «НЕТ ОТВЕТА» дважды через 30 с — **дефект «интернет пропадает при смене
сети»**, записать.

## 8. Выключение из уведомления

Шаг 8.1. **Попроси заказчика**: «Опустите шторку уведомлений: есть „VPN XGW — Включён:
серверов N“? Разверните его и нажмите „Выключить“.» Записать ответ. Затем:

```bash
sleep 3; python3 "$HOME/xgw-a3-test/a3check.py" vpn | tee "$HOME/xgw-a3-test/after/note-off.txt"; python3 "$HOME/xgw-a3-test/a3check.py" start | grep -E 'VPN телефона' | tee -a "$HOME/xgw-a3-test/after/note-off.txt"
```

Ожидается: «Xray в приложении: НЕ ЗАПУЩЕН», «интерфейс VPN …: НЕТ»; в приложении — «VPN
телефона выключен», «Включить VPN телефона».
Если уведомления нет или «Выключить» не выключает — **дефект**, записать; выключить кнопкой в
приложении: `python3 "$HOME/xgw-a3-test/a3check.py" tap vpn-power`.

## 9. «Постоянная VPN» и перезагрузка телефона (только при согласии на пункт 6)

Шаг 9.1. **Скажи заказчику** (дословно): «Нажмите в приложении XGW „VPN всегда“, затем
„Открыть настройки“. В списке VPN нажмите на шестерёнку у XGW и включите „Постоянная VPN“
(„Блокировать соединения без VPN“ не включайте). Скажите, когда готово.» Записать ответ.

Шаг 9.2. Через 10 с:

```bash
sleep 10; python3 "$HOME/xgw-a3-test/a3check.py" vpn | tee "$HOME/xgw-a3-test/after/always.txt"
```

Ожидается: «Xray в приложении: работает» (Android включил VPN сам, как только включили
«Постоянная VPN»). Если «НЕ ЗАПУЩЕН» — записать как наблюдение и продолжать.

Шаг 9.3. **Скажи заказчику**: «Сейчас перезагружу телефон; после включения разблокируйте его.»
Затем:

```bash
adb reboot; sleep 20; adb wait-for-device; echo "телефон снова на связи: $(date '+%T')"; sleep 90; python3 "$HOME/xgw-a3-test/a3check.py" vpn | tee -a "$HOME/xgw-a3-test/after/always.txt"; python3 "$HOME/xgw-a3-test/a3check.py" exit | tee -a "$HOME/xgw-a3-test/after/always.txt"
```

Ожидается: «Xray в приложении: работает», интерфейс VPN есть, страна — YY (VPN включился сам
после перезагрузки, приложение не открывали).
Если «НЕ ЗАПУЩЕН» — **попроси заказчика** разблокировать телефон, подожди 60 с и повтори `vpn`;
снова «НЕ ЗАПУЩЕН» — **дефект «Постоянная VPN не включает VPN после перезагрузки»**, записать
вывод `python3 "$HOME/xgw-a3-test/a3check.py" start` и `crash`.

Шаг 9.4. **Спроси заказчика**: «Оставить „Постоянную VPN“ включённой? Если нет — выключите её
там же, в настройках VPN.» Записать ответ.

## 10. Итог

Шаг 10.1.

```bash
python3 "$HOME/xgw-a3-test/a3check.py" crash | tee "$HOME/xgw-a3-test/after/final.txt"; python3 "$HOME/xgw-a3-test/a3check.py" vpn | tee -a "$HOME/xgw-a3-test/after/final.txt"; sudo python3 "$HOME/xgw-a3-test/a3check.py" phones | tee -a "$HOME/xgw-a3-test/after/final.txt"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | python3 "$HOME/xgw-a3-test/a3check.py" mask | tee -a "$HOME/xgw-a3-test/after/final.txt"
```

Ожидается: «падений приложения в журнале телефона: 0»; телефон «Galaxy S25 Ultra» —
«заходил»; состояние шлюза — как было (HEALTHY или DEGRADED), «Перехват: включён».

Шаг 10.2. **Спроси заказчика**: «Оставить VPN телефона включённым?» Если «нет» и VPN включён:
`python3 "$HOME/xgw-a3-test/a3check.py" tap vpn-power`. Затем **скажи**: «Испытание закончено.
„Отладку по USB“ можно выключить: Настройки → Параметры разработчика. Если Samsung будет сам
выключать VPN XGW в фоне — в настройках батареи для XGW выберите „Без ограничений“.»

## 11. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-android-a3-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`android-a3`), коммит «Отчёт А3: VPN телефона», `git push`. В отчёт — только выводы скрипта
(они уже маскированы) и ответы заказчика. Шаблон:

```markdown
# Отчёт А3: VPN телефона в приложении (ветка android-a3)

Код: <хеш>. APK: android/apk/XGW-0.1.17-a3.apk, sha256 <первые 8 знаков> — совпал. Телефон:
<модель>, Android <…>. Согласие заказчика: пункты <…>.

## Итог
<3–6 предложений: включение, страна выхода с VPN и без, пульт, смена сети, уведомление,
«Постоянная VPN».>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 3.1 обновление | … | привязка сохранилась? |
| 4.1 список серверов | … | серверов N |
| 5.1 до VPN (Wi-Fi) | — | страна XX |
| 5.2–5.3 VPN по Wi-Fi | … | разрешения, Xray, интерфейс, страна YY |
| 5.4 сайты (заказчик) | … | … |
| 5.5 пульт с VPN | … | … |
| 6.1–6.3 мобильная сеть | … | с VPN YY, без VPN ZZ |
| 7 смена сети | … | … |
| 8.1 «Выключить» в уведомлении | … | … |
| 9 «Постоянная VPN» и перезагрузка | … | … |
| 10.1 итог | … | падений 0 |

## Выводы шагов
<содержимое файлов after/*.txt, по заголовку на файл>

## Дефекты
<или «Не обнаружены»>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние
<VPN телефона включён/выключен, «Постоянная VPN» — по решению заказчика; шлюз не менялся.>
```

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
