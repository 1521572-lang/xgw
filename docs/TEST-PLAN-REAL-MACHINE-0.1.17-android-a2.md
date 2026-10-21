# Программа испытаний XGW: приложение-пульт на телефоне (А2)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§9). Пути в командах — только абсолютные (`$HOME/xgw-a2-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома, XGW из `main` (6a7de9e, версия 0.1.17,
отчёт issue #1 — без дефектов). Funnel для приложения включён (отчёт А1). Клон репозитория —
`~/zcod/xgw`. Телефон заказчика — **Samsung Galaxy S25 Ultra**.

Что нового (ASSUMPTIONS п. 225, фаза А2 `ANDROID_APP_PLAN.md`): **приложение XGW для
Android — пульт шлюза** (VPN телефона — следующая фаза, А3). Файл установки лежит в клоне:
`android/apk/XGW-0.1.17-a2.apk`. Приложение:

- привязывается к шлюзу по QR-коду из панели (кнопка «Сканировать QR-код» открывает сканер
  Google Play services) или по ссылке `xgw://pair?…` (её открывает и обычная камера телефона);
- ключ телефона хранит в защищённом хранилище Android (Keystore);
- показывает состояние шлюза, VPN шлюза (выключение — с подтверждением), основной сервер,
  серверы в работе (выбрать вручную / вернуть автовыбор), кнопки «Обновить подписки»,
  «Проверить запасные», «Замерить скорость», устройства дома (мимо VPN / через VPN);
- ходит к шлюзу через Funnel **напрямую**, мимо VPN телефона; при включённом другом VPN на
  телефоне (Happ и т. п.) шлюз недоступен — приложение так и говорит.

Код шлюза в этом испытании не меняется (остаётся `main`): прогресс «Замер скорости N из M» и
«Нет интернета в сети» в приложении появятся, когда А2 сольют в `main` и поставят на шлюз, —
до того кнопка замера пишет «Замеряю скорость…».

Как управляется телефон: исполнитель работает на шлюзе, телефон подключён к шлюзу кабелем
USB, на телефоне включена «Отладка по USB». Скрипт `a2check.py` через `adb` ставит приложение,
читает надписи на экране (`uiautomator`) и нажимает кнопки. Что требует рук заказчика —
навести камеру на QR-код, разрешить отладку, выйти на мобильную сеть — отдельные шаги «Попроси
заказчика».

Цели:

1. Подготовка: adb на шлюзе, телефон подключён (шаги 1–2).
2. Установка приложения (шаг 3).
3. Привязка: камерой (заказчик) и, если не вышло, ссылкой (шаг 4).
4. Пульт: состояние, кнопки, ручной выбор сервера, подтверждение выключения VPN (шаг 5).
5. Пульт по мобильной сети (шаг 6).
6. Отвязка в панели — приложение это видит (шаг 7), итог (шаг 8), отчёт (§9).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh` — **никогда**
  (код шлюза в этом испытании не меняется).
- Выключать VPN шлюза: в шаге 5.5 нажимается «Выключить VPN шлюза» и **сразу «Отмена»**
  в вопросе. Нажать «Выключить» в вопросе — **нельзя**.
- Через `a2check.py press` — только `phones/pair` и `phones/revoke`. Кнопки приложения — только
  названные в шагах.
- Команды Tailscale, кроме `tailscale status`; Funnel, Serve, SSH не трогать.
- Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager, `ssh`.
- Править `/etc/xgw/*`, `/var/lib/xgw/*`. Править код XGW. Коммитить что-либо, кроме отчёта (§9).
- На телефоне: ничего, кроме приложения XGW и команд `adb` из шагов. Не удалять и не менять
  другие приложения, не трогать настройки, кроме тех, что меняет сам заказчик по просьбе.
- В отчёт и в Git не класть снимки экрана телефона (`*.png` в `~/xgw-a2-test`): на них могут
  быть имена и адреса.
- Писать в отчёт: адреса tailnet (`100.x.y.z`), имена `*.ts.net`, имена устройств, кроме
  модели телефона, внешние IP, коды и ссылки привязки (`xgw://…`, `&c=…`), ключи, серийный
  номер телефона, адреса подписок, IP и домены серверов VPN. Выводы — только через
  `a2check.py mask` (скрипт маскирует сам).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю приложение XGW на вашем телефоне — пульт шлюза (VPN телефона будет в следующей
версии). По пунктам:
(1) Поставлю на шлюз программу adb (пакет Ubuntu, около 5 МБ) — ею шлюз управляет телефоном
по кабелю.
(2) На телефоне нужно включить „Отладку по USB“ и подключить его к шлюзу кабелем — я подскажу
как. После испытания отладку можно выключить.
(3) Поставлю на телефон приложение XGW (около 5 МБ), привяжу его к шлюзу — нужно будет
навести камеру приложения на QR-код в панели.
(4) В приложении нажму „Проверить запасные“, „Замерить скорость“, выберу сервер вручную и
верну автовыбор (трафик дома на минуту пойдёт через выбранный сервер), открою вопрос
„Выключить VPN шлюза?“ и отвечу „Отмена“ — VPN не выключается.
(5) Попрошу вас выключить на телефоне Wi-Fi и проверить пульт по мобильной сети (другой
VPN на телефоне на это время выключить).
(6) В конце отвяжу телефон в панели и проверю, что приложение это видит; затем можно
привязать заново, если оставляете приложение.
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1, 2 или 3 — **стоп**, испытание не проводится.
- Против пункта 4 — шаги 5.3–5.5 пропустить; против 5 — шаг 6; против 6 — шаг 7.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-a2-test/after" && chmod 700 "$HOME/xgw-a2-test" && cd "$HOME/xgw-a2-test" && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды выполняй из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без
пароля на время испытаний.

Шаг 1.2. adb (пункт 1 согласия):

```bash
command -v adb || sudo apt-get install -y -o Acquire::ForceIPv4=true adb 2>&1 | tail -3; adb version | head -1
```

Ожидается: строка `Android Debug Bridge version 1.0.…`.
Если пакета `adb` нет в репозиториях: `sudo apt-get install -y android-tools-adb`; не
вышло и так — **стоп**, сообщить заказчику.

Шаг 1.3. Код и файл приложения:

```bash
cd ~/zcod/xgw && git fetch && git checkout android-a2 && git pull --ff-only && git log -1 --format='%h %s'; sha256sum android/apk/XGW-0.1.17-a2.apk; cd "$HOME/xgw-a2-test"
```

Ожидается: `758a9b2844c9385be22cb3089e4aa7c0a2d1889042a8e4c0210f0eac5e8e35b8` в начале
строки хеша. Записать хеш коммита.
Если хеш другой или ветки нет: **стоп**, сообщить заказчику.

Шаг 1.4. Скрипт проверки. Скопируй команду целиком (до строки `A2_EOF` включительно):

```bash
cat > "$HOME/xgw-a2-test/a2check.py" <<'A2_EOF'
"""А2 XGW (ветка android-a2): приложение-пульт на телефоне, управление через adb.

python3 a2check.py devices              телефон подключён и разрешил отладку
python3 a2check.py install              поставить android/apk/XGW-0.1.17-a2.apk из клона
python3 a2check.py start                открыть приложение
python3 a2check.py texts                надписи на экране приложения (маскированные)
python3 a2check.py tap ID|ТЕКСТ         нажать кнопку (id элемента или часть надписи)
python3 a2check.py wait ТЕКСТ СЕКУНД    ждать надпись на экране
python3 a2check.py shot ИМЯ             снимок экрана в $HOME/xgw-a2-test/ИМЯ.png (не в отчёт!)
python3 a2check.py crash                падения приложения в журнале телефона
sudo python3 a2check.py press ДЕЙСТВИЕ [JSON]   кнопка панели (phones/pair, phones/revoke)
sudo python3 a2check.py phones          телефоны в панели и код привязки (есть / нет)
sudo python3 a2check.py link-open       открыть ссылку привязки на телефоне (вместо камеры)
sudo python3 a2check.py events          события шлюза «с телефона …» и о телефонах
python3 a2check.py mask < ФАЙЛ          маскировать вывод
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
PACKAGE = os.environ.get("XGW_A2_PACKAGE", "net.xgw.android")
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
WORK = Path(os.environ.get("XGW_A2_DIR", str(HOME / "xgw-a2-test")))
APK = CLONE / "android" / "apk" / "XGW-0.1.17-a2.apk"
APK_SHA = "758a9b2844c9385be22cb3089e4aa7c0a2d1889042a8e4c0210f0eac5e8e35b8"
CONFIG = Path(os.environ.get("XGW_CONFIG", "/etc/xgw/config.toml"))
TOKEN_FILE = Path(os.environ.get("XGW_A2_TOKEN", "/var/lib/xgw/panel-token"))
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


def cmd_press(name: str, body: str) -> int:
    if name not in ("phones/pair", "phones/revoke"):
        print("в этом испытании — только phones/pair и phones/revoke")
        return 2
    code, text, _response = request("POST", f"/api/{name}", cookie=login(),
                                    body=json.loads(body) if body else {})
    result = json.loads(text) if code == 200 else {}
    masker = Masker()
    print(f"кнопка {name}: HTTP {code}, ok={result.get('ok')}; "
          f"{masker.mask(str(result.get('text') or ''))}")
    return 0 if result.get("ok") else 1


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


def cmd_link_open() -> int:
    link = str(((state().get("phones") or {}).get("pairing") or {}).get("link") or "")
    if not link:
        print("кода привязки нет: сначала press phones/pair")
        return 1
    adb("shell", "am", "start", "-p", PACKAGE, "-a", "android.intent.action.VIEW",
        "-d", f"'{link}'")
    print("ссылка привязки открыта в приложении")
    time.sleep(3)
    return cmd_texts()


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
              "link-open": cmd_link_open, "events": cmd_events}
    if command in simple:
        return simple[command]()
    if command == "tap" and rest:
        return cmd_tap(" ".join(rest))
    if command == "wait" and len(rest) >= 2:
        return cmd_wait(" ".join(rest[:-1]), float(rest[-1]))
    if command == "shot" and rest:
        return cmd_shot(rest[0])
    if command == "press" and rest:
        return cmd_press(rest[0], rest[1] if len(rest) > 1 else "")
    if command == "mask":
        sys.stdout.write(Masker().mask(sys.stdin.read()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
A2_EOF
sha256sum "$HOME/xgw-a2-test/a2check.py"
```

Ожидается: `1d3d54d34124eb28ce70cc3391683c39679bc188554dc03402fb2878a70ef17b` в начале строки.
Если хеш другой: файл скопирован не целиком — повторить шаг 1.4 один раз; если снова другой —
**стоп**, сообщить заказчику.

## 2. Телефон подключён

Шаг 2.1. **Скажи заказчику** (дословно): «На телефоне: Настройки → Сведения о телефоне →
Сведения о ПО → семь раз нажмите „Номер сборки“ (появится „Режим разработчика включён“).
Затем Настройки → Параметры разработчика → включите „Отладка по USB“. Подключите телефон к
шлюзу кабелем USB; если телефон спросит „Разрешить отладку по USB?“ — отметьте „Всегда
разрешать с этого компьютера“ и нажмите „Разрешить“. Скажите, когда готово.»

Шаг 2.2.

```bash
python3 "$HOME/xgw-a2-test/a2check.py" devices | tee "$HOME/xgw-a2-test/after/devices.txt"
```

Ожидается: «телефон: подключён, отладка разрешена»; «модель: SM-S938…; Android 15» (или 16).
Если «ЖДЁТ РАЗРЕШЕНИЯ» — попроси заказчика нажать «Разрешить» на телефоне, повтори шаг.
Если «НЕ ВИДЕН» — попроси заказчика проверить кабель и выбрать на телефоне режим USB
«Передача файлов»; повтори; не помогло за 3 попытки — **стоп**.

## 3. Установка приложения

Шаг 3.1.

```bash
python3 "$HOME/xgw-a2-test/a2check.py" install | tee "$HOME/xgw-a2-test/after/install.txt"; python3 "$HOME/xgw-a2-test/a2check.py" start | tee -a "$HOME/xgw-a2-test/after/install.txt"
```

Ожидается: «установка: Success»; «установлено: net.xgw.android 0.1.17-a2»; на экране —
«XGW», «Пульт шлюза XGW», «Сканировать QR-код».
Если установка не прошла (`INSTALL_FAILED…`) — записать строку целиком; если в ней
`UPDATE_INCOMPATIBLE` — **спросить заказчика**, можно ли удалить прежнюю сборку XGW с
телефона (`adb uninstall net.xgw.android`); иначе **стоп**.

## 4. Привязка

Шаг 4.1. QR-код в панели:

```bash
sudo python3 "$HOME/xgw-a2-test/a2check.py" press phones/pair | tee "$HOME/xgw-a2-test/after/pair.txt"; sudo python3 "$HOME/xgw-a2-test/a2check.py" phones | tee -a "$HOME/xgw-a2-test/after/pair.txt"
```

Ожидается: «ok=True; Наведите камеру приложения XGW на QR-код»; «Funnel: включён; код
привязки в QR: есть».

Шаг 4.2. **Скажи заказчику** (дословно): «Откройте панель XGW (как обычно, в браузере
компьютера или другого устройства) — в карточке „Телефоны“ виден QR-код. В приложении XGW на
телефоне нажмите „Сканировать QR-код“ и наведите камеру на QR. Если сканер скажет, что
загружается из Google Play, подождите полминуты и нажмите ещё раз. Когда появится „Привязать
телефон?“ — нажмите „Привязать“. Скажите, что получилось.»

Затем:

```bash
python3 "$HOME/xgw-a2-test/a2check.py" wait "Серверы в работе" 180 | tee "$HOME/xgw-a2-test/after/pair-camera.txt"; sudo python3 "$HOME/xgw-a2-test/a2check.py" phones | tee -a "$HOME/xgw-a2-test/after/pair-camera.txt"
```

Ожидается: «„Серверы в работе“ на экране через N с»; в панели — «телефон «Galaxy S25 Ultra»
…: заходил» и «привязан по последнему коду: Galaxy S25 Ultra». Записать, что ответил
заказчик (сканер открылся сразу / после загрузки).

Если не вышло камерой (сканер не открылся, QR не читается) — записать слова заказчика и
сообщение на экране (`a2check.py texts`) как **наблюдение** и привязать ссылкой:

```bash
sudo python3 "$HOME/xgw-a2-test/a2check.py" press phones/pair; sudo python3 "$HOME/xgw-a2-test/a2check.py" link-open | tee "$HOME/xgw-a2-test/after/pair-link.txt"; python3 "$HOME/xgw-a2-test/a2check.py" tap confirm-yes; python3 "$HOME/xgw-a2-test/a2check.py" wait "Серверы в работе" 60 | tee -a "$HOME/xgw-a2-test/after/pair-link.txt"
```

Ожидается: на экране после ссылки — «Привязать телефон?», «Шлюз имя-1.ts-net»,
«Привязать»; затем «„Серверы в работе“ на экране». Не появилось и так — **дефект
«привязка не работает»**: записать вывод, шаги 5–7 пропустить.

## 5. Пульт

Шаг 5.1. Состояние:

```bash
python3 "$HOME/xgw-a2-test/a2check.py" texts | tee "$HOME/xgw-a2-test/after/remote.txt"; sudo xgw status 2>&1 | grep -E '^Состояние|^Основной' | python3 "$HOME/xgw-a2-test/a2check.py" mask | tee -a "$HOME/xgw-a2-test/after/remote.txt"
```

Ожидается: надпись состояния (например, «Серверы в порядке») совпадает со строкой
«Состояние» `xgw status` (HEALTHY — «Серверы в порядке», DEGRADED — «Часть серверов
недоступна»); «VPN шлюза включён»; строка «Основной сервер: …» с тем же сервером, что
`xgw status`; кнопки «Обновить подписки», «Проверить запасные», «Замерить скорость»;
«Этот телефон», «Отвязать телефон».

Шаг 5.2. «Проверить запасные» (только при согласии на пункт 4):

```bash
python3 "$HOME/xgw-a2-test/a2check.py" tap scan-spares | tee -a "$HOME/xgw-a2-test/after/remote.txt"; sleep 3; sudo python3 "$HOME/xgw-a2-test/a2check.py" events | tee -a "$HOME/xgw-a2-test/after/remote.txt"
```

Ожидается: «нажато: «Проверить запасные»»; среди событий — «с телефона «Galaxy S25 Ultra»:
Проверяю запасные серверы…».

Шаг 5.3. «Замерить скорость»:

```bash
python3 "$HOME/xgw-a2-test/a2check.py" tap speed | tee -a "$HOME/xgw-a2-test/after/remote.txt"; sleep 10; python3 "$HOME/xgw-a2-test/a2check.py" texts | grep -iE 'Замер' | tee -a "$HOME/xgw-a2-test/after/remote.txt"; sudo python3 "$HOME/xgw-a2-test/a2check.py" events | head -3 | tee -a "$HOME/xgw-a2-test/after/remote.txt"
```

Ожидается: «нажато: «Замерить скорость»»; на экране — «Замер скорости N из M» (замер идёт)
или снова «Замерить скорость» (уже закончился); среди событий — «с телефона «Galaxy S25
Ultra»: Замеряю скорость всех живых серверов…». Если кнопки нет — записать: она видна, только
когда в панели включён основной сервер.

Шаг 5.4. Ручной выбор сервера и возврат (заказчик согласился):

```bash
python3 "$HOME/xgw-a2-test/a2check.py" texts > "$HOME/xgw-a2-test/screen.txt"; sed -n '/Серверы в работе/,/Запасных/p' "$HOME/xgw-a2-test/screen.txt" | head -12
```

Выбери **второй** сервер в списке (не основной, без «не отвечает») — возьми первые три
слова его названия, например `Германия · Франкфурт`. Затем (подставь эти слова вместо
`НАЗВАНИЕ`):

```bash
python3 "$HOME/xgw-a2-test/a2check.py" tap "НАЗВАНИЕ"; python3 "$HOME/xgw-a2-test/a2check.py" texts | grep -E 'Выбрать|автовыбор' ; python3 "$HOME/xgw-a2-test/a2check.py" tap dialog-yes; sleep 5; python3 "$HOME/xgw-a2-test/a2check.py" texts | grep -E 'Выбран вручную|выбран' | tee -a "$HOME/xgw-a2-test/after/remote.txt"; sudo xgw status 2>&1 | grep -iE 'выбран|закреп' | python3 "$HOME/xgw-a2-test/a2check.py" mask | tee -a "$HOME/xgw-a2-test/after/remote.txt"
```

Ожидается: вопрос «Выбрать «…»?» с кнопкой «Выбрать»; после — «Выбран вручную: …» на
экране и строка о ручном выборе в `xgw status`.

Сразу вернуть автовыбор:

```bash
python3 "$HOME/xgw-a2-test/a2check.py" tap unpin; sleep 5; python3 "$HOME/xgw-a2-test/a2check.py" texts | grep -cE 'Выбран вручную' | sed 's/^/строк «Выбран вручную» на экране: /' | tee -a "$HOME/xgw-a2-test/after/remote.txt"
```

Ожидается: «строк «Выбран вручную» на экране: 0».
Если кнопки «Вернуть автовыбор» нет или выбор остался — сразу `sudo xgw unpin`, записать
**дефект**.

Шаг 5.5. Вопрос перед выключением VPN шлюза — **только «Отмена»**:

```bash
python3 "$HOME/xgw-a2-test/a2check.py" tap power; python3 "$HOME/xgw-a2-test/a2check.py" texts | grep -E 'Выключить VPN шлюза\?|мимо VPN' | tee -a "$HOME/xgw-a2-test/after/remote.txt"; python3 "$HOME/xgw-a2-test/a2check.py" tap dialog-no; sleep 3; sudo xgw status 2>&1 | grep -E '^Перехват' | python3 "$HOME/xgw-a2-test/a2check.py" mask | tee -a "$HOME/xgw-a2-test/after/remote.txt"
```

Ожидается: «Выключить VPN шлюза?» и «Интернет дома пойдёт напрямую, мимо VPN.»; после
«Отмена» — «Перехват: включён — …» (VPN не выключился).
Если `xgw status` показывает «СНЯТ» — **сразу** `sudo xgw enable`, записать **критический
дефект**, сообщить заказчику.

Шаг 5.6.

```bash
python3 "$HOME/xgw-a2-test/a2check.py" crash | tee -a "$HOME/xgw-a2-test/after/remote.txt"
```

Ожидается: «падений приложения в журнале телефона: 0».

## 6. Пульт по мобильной сети (только при согласии на пункт 5)

Шаг 6.1. **Скажи заказчику**: «Выключите на телефоне Wi-Fi (мобильный интернет включён) и
другой VPN, если он включён. Не закрывая приложение XGW, потяните экран вниз или подождите
10 секунд. Скажите, когда готово.»

```bash
sleep 15; python3 "$HOME/xgw-a2-test/a2check.py" texts | grep -E 'Серверы|Нет связи|VPN шлюза|Состояние на' | tee "$HOME/xgw-a2-test/after/mobile.txt"
```

Ожидается: «VPN шлюза включён», «Состояние на ЧЧ:ММ:СС» со временем последних секунд; чипа
«Нет связи» нет. Если «Нет связи со шлюзом …» — записать текст целиком (это
**наблюдение**: Funnel из мобильной сети недоступен) и спросить заказчика, был ли выключен
другой VPN.

Шаг 6.2. **Скажи заказчику**: «Включите обратно Wi-Fi и, если нужно, ваш VPN.»

## 7. Отвязка в панели (только при согласии на пункт 6)

Шаг 7.1. id телефона — из шага 4.2 (`a2check.py phones`, `id=…`). Подставь его вместо `ID`:

```bash
sudo python3 "$HOME/xgw-a2-test/a2check.py" press phones/revoke '{"id": "ID"}' | tee "$HOME/xgw-a2-test/after/revoke.txt"; python3 "$HOME/xgw-a2-test/a2check.py" start >/dev/null; python3 "$HOME/xgw-a2-test/a2check.py" wait "Шлюз не принял запрос" 30 | tee -a "$HOME/xgw-a2-test/after/revoke.txt"; python3 "$HOME/xgw-a2-test/a2check.py" texts | grep -E 'Привязать заново' | tee -a "$HOME/xgw-a2-test/after/revoke.txt"
```

Ожидается: «ok=True; Телефон «Galaxy S25 Ultra» отвязан»; на экране — «Шлюз не принял
запрос: телефон отвязан в панели …» и кнопка «Привязать заново».

Шаг 7.2. **Спроси заказчика**: «Привязать телефон заново, чтобы пользоваться приложением?»
Да — повторить шаг 4.1 и 4.2 (камерой или ссылкой). Нет — ничего не делать.

## 8. Итог

Шаг 8.1.

```bash
sudo xgw status 2>&1 | grep -E '^Состояние|^Перехват' | python3 "$HOME/xgw-a2-test/a2check.py" mask | tee "$HOME/xgw-a2-test/after/final.txt"; sudo python3 "$HOME/xgw-a2-test/a2check.py" phones | tee -a "$HOME/xgw-a2-test/after/final.txt"; python3 "$HOME/xgw-a2-test/a2check.py" crash | tee -a "$HOME/xgw-a2-test/after/final.txt"
```

Ожидается: состояние как в шаге 5.1, «Перехват: включён», телефоны — по решению заказчика в
7.2, падений 0.

Шаг 8.2. **Скажи заказчику**: «Испытание закончено. „Отладку по USB“ можно выключить:
Настройки → Параметры разработчика. Приложение XGW остаётся на телефоне.»

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-android-a2-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`android-a2`), коммит «Отчёт А2: приложение-пульт на телефоне», `git push`. Снимки экрана
(`*.png`) — **не** в отчёт и не в Git. Шаблон:

```markdown
# Отчёт А2: приложение-пульт на телефоне (ветка android-a2)

Код: <хеш>. Телефон: <модель>, Android <версия>. Согласие заказчика: пункты <…>.

## Итог
<3–6 предложений: установка, привязка камерой или ссылкой, пульт, мобильная сеть, отвязка.>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 2.2 телефон подключён | … | … |
| 3.1 установка | … | … |
| 4.2 привязка камерой | … | сканер открылся сразу / после загрузки / не открылся |
| 4.2 привязка ссылкой | … | (если понадобилась) |
| 5.1 состояние | … | совпадает с xgw status |
| 5.2–5.3 кнопки | … | … |
| 5.4 ручной выбор и автовыбор | … | … |
| 5.5 вопрос о выключении, «Отмена» | … | VPN не выключился |
| 6.1 мобильная сеть | … | … |
| 7.1 отвязка | … | … |
| 8.1 итог | … | падений 0 |

## Выводы шагов
<содержимое файлов after/*.txt, по заголовку на файл>

## Дефекты
<или «Не обнаружены»>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние
```

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
