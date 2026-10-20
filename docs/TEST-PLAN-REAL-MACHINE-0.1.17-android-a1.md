# Программа испытаний XGW на реальной машине: приложение на телефоне — часть шлюза (А1)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§9). Пути в командах — только абсолютные (`$HOME/xgw-a1-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома. Стоит XGW с кодом ветки `tailscale-t2`
(версия 0.1.17), Tailscale подключён, «SSH через Tailscale» и «Панель по tailnet» включены
(отчёт Т2 — `docs/TEST-REPORT-REAL-MACHINE-0.1.17-tailscale-t2-2026-10-20.md`). Клон
репозитория — `~/zcod/xgw`. Номер версии новый код не меняет (`xgw 0.1.17`); новый код
узнаётся по строке «А1 в установленном коде: есть» (шаг 2.3).

Что нового (ASSUMPTIONS п. 221, фаза А1 `ANDROID_APP_PLAN.md`). Заказчик решил делать своё
приложение XGW для Android — VPN телефона и пульт шлюза. Самого приложения ещё нет; в этой
фазе — всё, что для него нужно на шлюзе:

- **API приложения** на `127.0.0.1:8782`, наружу — через **Tailscale Funnel**: публичный
  адрес шлюза `https://<имя шлюза>.<tailnet>.ts.net/` (порт 443). Tailscale на телефоне для
  него не нужен;
- в панели — карточка **«Телефоны»**: кнопка «Привязать телефон» сама включает Funnel и
  показывает QR-код; телефон наводит на него камеру приложения — и привязан;
- в карточке «Tailscale» — переключатель «Приложение на телефоне (Funnel)»;
- для VPN телефона шлюз отдаёт готовый конфиг Xray (те же серверы, что работают на шлюзе).

Как проверяется без приложения. Скрипт `a1check.py` изображает телефон: берёт код из QR
(как камера), привязывается и шлёт подписанные запросы — **по публичному адресу Funnel**,
через интернет и ретранслятор Tailscale, а не изнутри tailnet. Это ровно путь будущего
приложения. Заказчик дополнительно открывает адрес проверки в браузере телефона по мобильной
сети. Имён и адресов скрипт не печатает (кроме ссылки «Разрешить Funnel» — только для
заказчика).

Цели:

1. Снимок до обновления (шаг 1.3).
2. Поставить новый код (шаг 2).
3. Привязка кнопкой: Funnel включается, QR-код появляется (шаг 3).
4. Публичный адрес отвечает: с самого шлюза через интернет и с телефона заказчика по
   мобильной сети — без VPN телефона и с ним (шаг 4).
5. «Тестовый телефон»: привязка, состояние, действие, отказы, конфиг для телефона (шаг 5).
6. Уборка тестового телефона, итоговое состояние (шаги 6–7), отчёт (§9).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**.
- Команды Tailscale, кроме `tailscale status` и `tailscale serve status` из шагов: **нельзя**
  `tailscale up`, `down`, `set`, `login`, `logout`, `switch`, `serve` (кроме `serve status`),
  `funnel` (кроме аварийного шага в §8), `cert`, `ssh`, `file`, `lock`, `update`, `debug`.
  Funnel включается и выключается **только** кнопками панели через `a1check.py press`.
- Через `a1check.py press` нажимать **только** кнопки, названные в шагах: `phones/pair`,
  `phones/revoke` (через `phone forget`), `tailscale/funnel`. Никаких `power`, `pin`,
  `device`, `tailscale/ssh`, `tailscale/serve`, `tailscale/fix`.
- Вход в консоль tailnet (login.tailscale.com) и изменения там — только сам заказчик.
- Запуск, остановка и перезапуск `tailscaled`, `xgw`, `xgw-xray`, `xgw-singbox`, `xgw-net`,
  `xgw-dhcp`, `systemd-resolved`, NetworkManager, `ssh`/`sshd`.
- Ручные команды `nft` (кроме `nft list`), `ip` (кроме `ip … show`), `iptables`,
  `sysctl -w`.
- Отключать WAN или LAN, кабели, Wi-Fi роутера.
- Править `/etc/xgw/config.toml`, `/etc/xgw/panel.json`, `/var/lib/xgw/phones.json`, файлы в
  `/etc/systemd`.
- Править код XGW. Коммитить что-либо, кроме отчёта (§9). Файлы из `~/xgw-a1-test` в Git
  **не класть**; `phone.key` никому не показывать и не копировать.
- Писать в отчёт: адреса tailnet (`100.x.y.z`, кроме `100.100.100.100` и `100.64.0.0/10`;
  `fd7a:…`), имена `*.ts.net` и любые имена устройств, пользователей и tailnet, почту, ссылки
  login.tailscale.com, внешние IP (свой, провайдера, ретрансляторов Funnel), токены, коды
  (`?login=…`, `&c=…`), ключи, содержимое `phone.key`, адреса подписок, UUID, IP и домены
  серверов VPN, MAC-адреса. Выводы с такими данными — только через `a1check.py mask`.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Ставлю на шлюз всё, что нужно будущему приложению XGW на телефоне. По пунктам:
(1) Установка: демон XGW перезапустится сам, интернет не пропадает, панель и бот секунд на
десять недоступны.
(2) Включу „Приложение на телефоне (Funnel)“ (вы так решили): у шлюза появится публичный
адрес https://…ts.net/. Войти туда может только привязанный телефон; без привязки адрес
отвечает лишь „XGW“. Если в вашем tailnet Funnel ещё не разрешён, понадобится один раз
подтвердить это в консоли Tailscale в браузере — я подскажу.
(3) Проверка с телефона: открыть в браузере телефона адрес https://…ts.net/api/hello по
мобильной сети — сначала с выключенным VPN на телефоне, потом с включённым. Tailscale на
телефоне для этого не нужен.
(4) Проверю привязку „тестовым телефоном“ — это программа на самом шлюзе. В конце отвяжу его.
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 или 2 — **стоп**, испытание не проводится (без Funnel проверять нечего).
- Против пункта 3 — шаг 4.2 пропустить («с телефона не проверялось — нет согласия»).
- Против пункта 4 — шаг 5 пропустить.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-a1-test/before" "$HOME/xgw-a1-test/after" && chmod 700 "$HOME/xgw-a1-test" && cd "$HOME/xgw-a1-test" && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды выполняй из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без пароля
на время испытаний.

Шаг 1.2. Скрипт проверки. Скопируй команду целиком (до строки `A1_EOF` включительно):

```bash
cat > "$HOME/xgw-a1-test/a1check.py" <<'A1_EOF'
"""А1 XGW (ветка android-a1): API приложения на телефоне через Tailscale Funnel.

sudo python3 a1check.py pre                 код, Tailscale (Serve, Funnel), телефоны
sudo python3 a1check.py press ДЕЙСТВИЕ [JSON] нажать кнопку панели (как в браузере)
sudo python3 a1check.py card                карточки «Телефоны» и Funnel — текстом
sudo python3 a1check.py wait-funnel         ждать, пока Funnel заработает (до 5 минут)
sudo python3 a1check.py enable-link         ссылка «Разрешить Funnel» — только заказчику!
sudo python3 a1check.py public-hello        /api/hello по публичному адресу (до 10 минут)
sudo python3 a1check.py local-host          API на 127.0.0.1: чужой Host — 421
sudo python3 a1check.py phone pair|state|act|replay|config|forget   «тестовый телефон»
sudo python3 a1check.py mask < ФАЙЛ         маскировать вывод

«Тестовый телефон» — эталонный клиент tests/phone_client.py из клона XGW: так же
подписывает запросы, как будет приложение. Он ходит на ПУБЛИЧНЫЙ адрес Funnel: имя шлюза
разрешается через 1.1.1.1 (не MagicDNS), и запрос идёт через интернет и ретранслятор
Tailscale. Его ключ — в $HOME/xgw-a1-test/phone.key (0600), в отчёт не идёт. Адресов, имён
tailnet, кодов и ключей скрипт не печатает (кроме enable-link).
"""

from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import os
import pwd
import re
import secrets
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

LIB = os.environ.get("XGW_LIB", "/opt/xgw/lib")
# Под sudo HOME — у root; клон и каталог проверки — у того, кто запустил sudo.
HOME = Path(pwd.getpwnam(os.environ["SUDO_USER"]).pw_dir) if os.environ.get("SUDO_USER")     else Path.home()
CLONE = Path(os.environ.get("XGW_CLONE", str(HOME / "zcod" / "xgw")))
sys.path.insert(0, LIB)
sys.path.insert(0, str(CLONE / "tests"))
from xgw import config  # noqa: E402

CONFIG = Path(os.environ.get("XGW_CONFIG", "/etc/xgw/config.toml"))
TOKEN_FILE = Path(os.environ.get("XGW_A1_TOKEN", "/var/lib/xgw/panel-token"))
XRAY = os.environ.get("XGW_A1_XRAY", "/opt/xgw/xray/xray")
WORK = Path(os.environ.get("XGW_A1_DIR", str(HOME / "xgw-a1-test")))
LOCAL_URL = os.environ.get("XGW_A1_URL", "")  # только для проверки самого скрипта
KEY = WORK / "phone.key"
PUBLIC_DNS = os.environ.get("XGW_A1_DNS", "1.1.1.1")
PHONE_NAME = "Проверка А1"
CGNAT = ipaddress.ip_network("100.64.0.0/10")


def run(argv: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]}: нет программы")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"{argv[0]}: таймаут")


def as_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def word(value) -> str:
    return {True: "да", False: "нет", None: "неизвестно"}.get(value, str(value))


def cfg():
    loaded, _warnings = config.load(CONFIG)
    return loaded


# --- панель --------------------------------------------------------------------------


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
    return as_json(text)


def funnel_name() -> str:
    """Имя шлюза для Funnel — из адреса в карточке Tailscale."""
    url = str(((state().get("tailscale") or {}).get("funnel") or {}).get("url") or "")
    return url.removeprefix("https://").rstrip("/")


# --- команды ---------------------------------------------------------------------------


def cmd_pre() -> int:
    print("А1 в установленном коде:",
          "есть" if (Path(LIB) / "xgw" / "phones.py").exists() else "НЕТ")
    print("версия:", run(["/usr/local/bin/xgw", "--version"]).stdout.strip() or "неизвестно")
    status = as_json(run(["tailscale", "status", "--json"], timeout=20).stdout)
    print("BackendState:", status.get("BackendState") or "неизвестно")
    serve = as_json(run(["tailscale", "serve", "status", "--json"], timeout=20).stdout)
    web = serve.get("Web") or {}
    allow = serve.get("AllowFunnel") or {}
    current = cfg()
    for port, target, what in (("8443", current.panel.port, "Serve 8443 (панель по tailnet)"),
                               ("443", current.panel.app_port, "Funnel 443 (приложение)")):
        hosts = [host for host in web if str(host).endswith(f":{port}")]
        proxy = [str((((web[host].get("Handlers") or {}).get("/") or {}).get("Proxy")) or "")
                 for host in hosts]
        public = any(allow.get(host) for host in hosts)
        if not hosts:
            print(f"{what}: нет")
        else:
            ok = f"http://127.0.0.1:{target}" in [item.rstrip("/") for item in proxy]
            print(f"{what}: ведёт на {'XGW' if ok else 'НЕ на XGW'}; открыт в интернет: "
                  f"{word(public)}")
    flags = (current.managed.tailscale_serve, current.managed.tailscale_funnel)
    print(f"panel.json: Serve из панели {word(bool(flags[0]))}; Funnel из панели "
          f"{word(bool(flags[1]))}")
    phones = as_json(Path("/var/lib/xgw/phones.json").read_text(encoding="utf-8")) \
        if Path("/var/lib/xgw/phones.json").exists() else {}
    print("привязанных телефонов:", len(phones.get("phones") or {}))
    listening = run(["ss", "-ltn", f"sport = :{current.panel.app_port}"]).stdout
    print(f"API приложения слушает 127.0.0.1:{current.panel.app_port}:",
          "да" if f"127.0.0.1:{current.panel.app_port}" in listening else "нет")
    return 0


def cmd_press(name: str, body: str) -> int:
    payload = json.loads(body) if body else {}
    started = time.monotonic()
    code, text, _response = request("POST", f"/api/{name}", cookie=login(), body=payload)
    result = as_json(text)
    if code != 200:
        print(f"кнопка {name}: HTTP {code}")
        return 1
    print(f"кнопка {name} {json.dumps(payload, ensure_ascii=False)}: ok={result.get('ok')}, "
          f"{time.monotonic() - started:.1f} с")
    masker = Masker()
    print("  ответ:", masker.mask(str(result.get("text") or "")))
    for note in result.get("notes") or []:
        print("  пояснение:", masker.mask(str(note)))
    return 0 if result.get("ok") else 1


def cmd_card() -> int:
    current = state()
    funnel = (current.get("tailscale") or {}).get("funnel") or {}
    phones = current.get("phones") or {}
    pairing = phones.get("pairing") or {}
    print(f"Funnel в карточке Tailscale: включён {word(funnel.get('on'))}; отвечает "
          f"{word(funnel.get('live'))}; ждёт разрешения {word(funnel.get('pending'))}; "
          f"ссылка «Разрешить»: {'есть' if funnel.get('enable_url') else 'нет'}")
    print(f"Телефоны: API запущен {word(phones.get('available'))}; QR-код "
          f"{'есть' if pairing.get('qr') else 'нет'}; ждёт Funnel {word(phones.get('waiting'))}; "
          f"привязан по последнему коду: {pairing.get('paired') or 'нет'}")
    for phone in phones.get("list") or []:
        print(f"  телефон «{phone.get('name')}»: на связи "
              f"{'да' if phone.get('seen') else 'ещё не заходил'}")
    return 0


def cmd_wait_funnel() -> int:
    started = time.monotonic()
    while time.monotonic() - started < 300:
        funnel = (state().get("tailscale") or {}).get("funnel") or {}
        if funnel.get("live") is True:
            print(f"Funnel отвечает: да, через {time.monotonic() - started:.0f} с")
            return 0
        time.sleep(10)
    print("Funnel отвечает: НЕТ за 5 минут")
    return 1


def cmd_enable_link() -> int:
    funnel = (state().get("tailscale") or {}).get("funnel") or {}
    print(funnel.get("enable_url") or "ссылки нет: Funnel не ждёт разрешения")
    return 0


# --- публичный адрес ---------------------------------------------------------------------


def resolve_public(name: str) -> list[str]:
    """A-записи имени через публичный DNS — адреса ретрансляторов Funnel, а не tailnet."""
    query_id = secrets.randbits(16)
    question = b"".join(bytes([len(part)]) + part.encode("ascii") for part in name.split("."))
    packet = struct.pack(">HHHHHH", query_id, 0x0100, 1, 0, 0, 0) + question + b"\0" + \
        struct.pack(">HH", 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.sendto(packet, (PUBLIC_DNS, 53))
        data, _peer = sock.recvfrom(4096)
    answers = struct.unpack(">H", data[6:8])[0]
    offset = 12
    while data[offset] != 0:  # пропустить вопрос
        offset += data[offset] + 1
    offset += 5
    found = []
    for _ in range(answers):
        if data[offset] & 0xC0 == 0xC0:
            offset += 2
        else:
            while data[offset] != 0:
                offset += data[offset] + 1
            offset += 1
        kind, _cls, _ttl, length = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        if kind == 1 and length == 4:
            found.append(socket.inet_ntoa(data[offset:offset + 4]))
        offset += length
    return [item for item in found if ipaddress.ip_address(item) not in CGNAT]


def public_client():
    from phone_client import PhoneClient

    name = funnel_name()
    if not name:
        raise SystemExit("имени шлюза для Funnel нет — Funnel не включён")
    if LOCAL_URL:
        return PhoneClient(LOCAL_URL, host=name)
    addresses = resolve_public(name)
    if not addresses:
        raise SystemExit("публичный DNS не знает имени шлюза (Funnel ещё не опубликован)")
    return PhoneClient(f"https://{name}", via=addresses[0], timeout=30)


def cmd_public_hello() -> int:
    started = time.monotonic()
    last = ""
    while time.monotonic() - started < 600:
        try:
            client = public_client()
            status, payload = client.raw("GET", "/api/hello")
            if status == 200 and payload.get("app") == "XGW":
                print(f"публичный адрес: имя в публичном DNS — да; /api/hello — 200 «XGW»; "
                      f"через {time.monotonic() - started:.0f} с")
                return 0
            last = f"HTTP {status}"
        except (OSError, SystemExit, ValueError) as exc:
            last = Masker().mask(str(exc))
        time.sleep(20)
    print(f"публичный адрес: НЕТ ответа за 10 минут (последнее: {last})")
    return 1


def cmd_local_host() -> int:
    from phone_client import PhoneClient

    port = cfg().panel.app_port
    name = funnel_name()
    for host, what in ((name, "имя шлюза"), (f"other-{name}", "чужое имя"),
                       (f"127.0.0.1:{port}", "адрес машины")):
        status, _payload = PhoneClient(f"http://127.0.0.1:{port}", host=host).raw(
            "GET", "/api/hello")
        print(f"API на 127.0.0.1, Host {what}: HTTP {status}")
    return 0


def _load_key():
    from phone_client import _load

    if not KEY.exists():
        raise SystemExit("тестовый телефон не привязан (нет phone.key)")
    return _load(str(KEY))


def cmd_phone(action: str) -> int:
    if action == "forget":
        phones = state().get("phones") or {}
        ids = [phone["id"] for phone in phones.get("list") or [] if phone["name"] == PHONE_NAME]
        for phone_id in ids:
            cmd_press("phones/revoke", json.dumps({"id": phone_id}))
        KEY.unlink(missing_ok=True)
        print(f"тестовых телефонов отвязано: {len(ids)}; ключ удалён")
        return 0
    client = public_client()
    if action == "pair":
        link = str(((state().get("phones") or {}).get("pairing") or {}).get("link") or "")
        if "&c=" not in link:
            print("QR-кода нет: сначала кнопка phones/pair")
            return 1
        status, payload = client.pair(link.split("&c=")[1], PHONE_NAME)
        if status == 200:
            fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(f"{client.phone} {base64.b64encode(client.key).decode()}\n")
        print(f"привязка через публичный адрес: HTTP {status}; имя «{payload.get('name')}»")
        return 0 if status == 200 else 1
    client.phone, client.key = _load_key()
    if action == "state":
        status, payload = client.signed("GET", "/api/state")
        print(f"состояние по публичному адресу: HTTP {status}; состояние "
              f"{payload.get('state')}; серверов в работе {len(payload.get('members') or [])}; "
              f"VPN шлюза можно выключить: {word((payload.get('power') or {}).get('can_off'))}")
        secrets_found = [word_ for word_ in ("vless://", "trojan://", "/sub/", "token")
                         if word_ in json.dumps(payload)]
        print("секретов в ответе:", ", ".join(secrets_found) or "нет")
    elif action == "act":
        status, payload = client.signed("POST", "/api/act", {"name": "scan"})
        print(f"кнопка «Проверить запасные» с телефона: HTTP {status}; ok={payload.get('ok')}")
        status, payload = client.signed("POST", "/api/act", {"name": "add", "text": "x"})
        print(f"запрещённое действие «добавить подписку» с телефона: HTTP {status}")
    elif action == "replay":
        first, _payload = client.signed("GET", "/api/state")
        second, _payload = client.replay()
        print(f"повтор того же запроса: первый HTTP {first}, повтор HTTP {second}")
    elif action == "config":
        status, payload = client.signed("GET", "/api/phone-config")
        config_ = payload.get("config") or {}
        marks = "есть" if '"mark"' in json.dumps(config_) else "нет"
        inbounds = [item.get("protocol") for item in config_.get("inbounds", [])]
        print(f"конфиг для телефона: HTTP {status}; серверов {len(payload.get('servers') or [])}; "
              f"вход {inbounds}; меток шлюза {marks}")
        path = WORK / "phone-config.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config_, handle)
        checked = run([XRAY, "run", "-test", "-c", str(path)])
        path.unlink(missing_ok=True)
        print("Xray шлюза принимает конфиг телефона:",
              "да" if checked.returncode == 0 else f"НЕТ: {Masker().mask(checked.stdout[-300:])}")
    else:
        print(__doc__)
        return 2
    return 0


class Masker:
    """Имена *.ts.net, адреса tailnet и внешние, коды и ключи — метками."""

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
        text = re.sub(r"(?i)\b[\w-]+(\.[\w-]+)*\.ts\.net\b",
                      lambda m: self.label("name", m.group(0).lower(), "имя-{}.ts-net"), text)
        text = re.sub(r"[?&](login|c)=[A-Za-z0-9_-]+", r"?\1=***", text)
        text = re.sub(r"(https://login\.tailscale\.com)/\S+", r"\1/…", text)
        text = re.sub(r"\bfd7a:[0-9a-fA-F:]+", "fd7a:…", text)
        text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "почта@…", text)
        return re.sub(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])", self._ip, text)


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("нужен root: sudo python3 a1check.py …")
        return 2
    WORK.mkdir(mode=0o700, exist_ok=True)
    command, rest = (argv[0], argv[1:]) if argv else ("", [])
    if command == "pre":
        return cmd_pre()
    if command == "press" and rest:
        return cmd_press(rest[0], rest[1] if len(rest) > 1 else "")
    if command == "card":
        return cmd_card()
    if command == "wait-funnel":
        return cmd_wait_funnel()
    if command == "enable-link":
        return cmd_enable_link()
    if command == "public-hello":
        return cmd_public_hello()
    if command == "local-host":
        return cmd_local_host()
    if command == "phone" and rest:
        return cmd_phone(rest[0])
    if command == "mask":
        sys.stdout.write(Masker().mask(sys.stdin.read()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
A1_EOF
sha256sum "$HOME/xgw-a1-test/a1check.py"
```

Ожидается: `143ab09f3dd1e2fda24367e49eca54c0bd7c9839f0c1e8023af4061b0cb985de` в начале строки.
Если хеш другой: файл скопирован не целиком — повторить шаг 1.2 один раз; если снова другой —
**стоп**, сообщить заказчику.

Шаг 1.3. Снимок до обновления:

```bash
cd "$HOME/xgw-a1-test" && sudo xgw --version; sudo xgw diag > "$HOME/xgw-a1-test/before/diag.txt"; tail -1 "$HOME/xgw-a1-test/before/diag.txt"; sudo xgw status | grep -E '^Состояние' | tee "$HOME/xgw-a1-test/before/state.txt"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled | tee "$HOME/xgw-a1-test/before/services.txt"; sudo tailscale serve status 2>&1 | sudo python3 "$HOME/xgw-a1-test/a1check.py" mask | tee "$HOME/xgw-a1-test/before/serve-status.txt"
```

Ожидается:

- `xgw 0.1.17`, «FAIL — 0», `HEALTHY`, службы `active` (у `xgw-singbox` допустимо
  `inactive` — записать);
- `serve status` (маскированный): одна строка `https://имя-1.ts-net:8443 (tailnet only)` и под
  ней `|-- / proxy http://127.0.0.1:8781` — это панель по tailnet из Т2. Слова `Funnel` нет.

`a1check.py pre` до обновления не запускается: старый код не знает телефонов.

Если не так:

- FAIL не 0 или состояние не `HEALTHY`: записать как есть и **спросить заказчика**,
  продолжать ли.
- `tailscaled` не `active`: **стоп**, сообщить заказчику.
- В `serve status` уже есть `Funnel on` или порт 443 — **стоп**, спросить заказчика: Funnel
  уже кто-то включил, шаг 3 может его заменить.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout android-a1 && git pull --ff-only && git log -1 --format='%h %s' && test -f src/xgw/phones.py && test -f tests/phone_client.py && echo "А1 в коде: есть"; grep __version__ src/xgw/__init__.py; cd "$HOME/xgw-a1-test"
```

Ожидается: «А1 в коде: есть» и `__version__ = "0.1.17"`. Записать хеш.
Если ветки `android-a1` нет или «А1 в коде: есть» не напечатано: **стоп**, сообщить заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-a1-test/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-a1-test/after/install.txt" | tail -25; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-a1-test"
```

Ожидается: «код 0» и строка «демон xgw запущен».
Если код не 0: **стоп**, сохранить вывод, выполнить §8 (возврат на `tailscale-t2`), сообщить
заказчику.

Шаг 2.3. Установленный код:

```bash
sleep 20; sudo xgw --version; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; sudo python3 "$HOME/xgw-a1-test/a1check.py" pre | tee "$HOME/xgw-a1-test/after/pre.txt"; sudo python3 "$HOME/xgw-a1-test/a1check.py" card | tee "$HOME/xgw-a1-test/after/card.txt"
```

Ожидается:

- `xgw 0.1.17`; службы — как в шаге 1.3;
- «А1 в установленном коде: есть»; «BackendState: Running»;
- «Serve 8443 (панель по tailnet): ведёт на XGW; открыт в интернет: нет»;
- «Funnel 443 (приложение): нет»;
- «panel.json: Serve из панели да; Funnel из панели нет»; «привязанных телефонов: 0»;
- «API приложения слушает 127.0.0.1:8782: да»;
- карточка: «Funnel в карточке Tailscale: включён нет; …»; «Телефоны: API запущен да; QR-код
  нет; …».

Если не так:

- «А1 в установленном коде: НЕТ» — **стоп**: установка не обновила код; сообщить заказчику.
- `xgw` не `active` — подожди 30 с, проверь ещё раз; снова не `active` — §8.
- «API приложения слушает …: нет» или «API запущен нет» — **дефект «API приложения не
  запустился»**: выполнить
  `sudo journalctl -u xgw -n 60 --no-pager | grep -i 'API приложения' | sudo python3 "$HOME/xgw-a1-test/a1check.py" mask`
  и записать; шаги 3–6 пропустить, перейти к шагу 7.

## 3. Привязка кнопкой: Funnel и QR-код

Шаг 3.1. Кнопка «Привязать телефон» (то же, что нажать её в панели):

```bash
sudo python3 "$HOME/xgw-a1-test/a1check.py" press phones/pair | tee "$HOME/xgw-a1-test/after/press-pair.txt"; sudo python3 "$HOME/xgw-a1-test/a1check.py" card | tee -a "$HOME/xgw-a1-test/after/press-pair.txt"
```

Ожидается одно из двух:

- А: «ok=True», «ответ: Наведите камеру приложения XGW на QR-код»; карточка: «Funnel …:
  включён да; отвечает да; ждёт разрешения нет»; «Телефоны: … QR-код есть; ждёт Funnel нет» —
  перейти к шагу 3.3;
- Б: «ok=True», «ответ: Осталось разрешить Funnel в tailnet»; карточка: «… ждёт разрешения да;
  ссылка «Разрешить»: есть»; «… QR-код нет; ждёт Funnel да» — шаг 3.2.

Если не так: «ok=False» — записать ответ (**дефект «Funnel не включается»**), шаги 4–6
пропустить, перейти к шагу 7.

Шаг 3.2. Только для варианта Б. **Скажи заказчику**: «Откройте панель XGW на шлюзе (ярлык
„XGW“), карточка „Телефоны“, нажмите „Разрешить Funnel в tailnet“ и подтвердите в открывшейся
консоли Tailscale. Скажите, когда подтвердите.» Если удобнее, чтобы ссылку прислал ты,
выполни (вывод покажи **только** заказчику, в файлы и отчёт его не писать):

```bash
sudo python3 "$HOME/xgw-a1-test/a1check.py" enable-link
```

Когда заказчик скажет «подтвердил»:

```bash
sudo python3 "$HOME/xgw-a1-test/a1check.py" wait-funnel | tee "$HOME/xgw-a1-test/after/wait-funnel.txt"; sudo python3 "$HOME/xgw-a1-test/a1check.py" card | tee -a "$HOME/xgw-a1-test/after/wait-funnel.txt"
```

Ожидается: «Funnel отвечает: да, через N с» и в карточке «QR-код есть; ждёт Funnel нет».
Если «НЕТ за 5 минут» — спроси заказчика, подтвердил ли он, и повтори команду (в `tee` замени
`wait-funnel.txt` на `wait-funnel-2.txt`); снова НЕТ — **дефект «Funnel не заработал после
разрешения»**, шаги 4–6 пропустить, перейти к шагу 7.

Шаг 3.3. Что настроил Tailscale и что видит панель изнутри:

```bash
sudo python3 "$HOME/xgw-a1-test/a1check.py" pre | tee "$HOME/xgw-a1-test/after/pre-funnel.txt"; sudo tailscale serve status 2>&1 | sudo python3 "$HOME/xgw-a1-test/a1check.py" mask | tee "$HOME/xgw-a1-test/after/serve-status.txt"; sudo python3 "$HOME/xgw-a1-test/a1check.py" local-host | tee "$HOME/xgw-a1-test/after/local-host.txt"
```

Ожидается:

- `pre`: «Serve 8443 …: ведёт на XGW; открыт в интернет: нет» (панель по tailnet по-прежнему
  только для tailnet); «Funnel 443 (приложение): ведёт на XGW; открыт в интернет: да»;
  «panel.json: Serve из панели да; Funnel из панели да»;
- `serve status`: строки `https://имя-1.ts-net (Funnel on)` с `|-- / proxy
  http://127.0.0.1:8782` и `https://имя-1.ts-net:8443 (tailnet only)` с `|-- / proxy
  http://127.0.0.1:8781`;
- `local-host`: «Host имя шлюза: HTTP 200», «Host чужое имя: HTTP 421», «Host адрес машины:
  HTTP 421».

Если не так:

- `:8443 (Funnel on)` — **стоп**, сообщить заказчику: панель стала видна из интернета (так
  быть не должно); сразу шаг 7.2 с выключением Funnel.
- «Host чужое имя» или «адрес машины» — не 421: **дефект «API принимает чужой адрес»**.

## 4. Публичный адрес отвечает

Шаг 4.1. С самого шлюза через интернет (имя — через публичный DNS 1.1.1.1, соединение — с
ретранслятором Funnel). Имя в публичном DNS может появиться не сразу — команда ждёт до 10
минут:

```bash
sudo python3 "$HOME/xgw-a1-test/a1check.py" public-hello | tee "$HOME/xgw-a1-test/after/public-hello.txt"
```

Ожидается: «публичный адрес: имя в публичном DNS — да; /api/hello — 200 «XGW»; через N с».
Если «НЕТ ответа за 10 минут» — записать последнюю причину (она уже маскирована) как
**дефект «Funnel не доступен из интернета»** и продолжать (шаг 4.2 покажет, видно ли его с
телефона); шаг 5 пропустить.

Шаг 4.2. Телефон заказчика — только при согласии на пункт 3. Узнай адрес для заказчика: он
в панели XGW на шлюзе, карточка «Tailscale» → «Приложение на телефоне (Funnel)»; заказчик его
видит сам. **Скажи заказчику**: «На телефоне выключите Wi-Fi (нужна мобильная сеть) и
выключите VPN. Откройте в браузере https://<имя шлюза>.<tailnet>.ts.net/api/hello (адрес из
панели, в конце — /api/hello). 1) Что показалось? 2) Браузер не ругался на сертификат? Потом
включите VPN телефона и откройте тот же адрес ещё раз: 3) что показалось? Потом откройте
https://<тот же адрес>/api/state: 4) что показалось?»

Ожидается: 1) `{"app": "XGW"}` (или то же в виде таблицы JSON); 2) нет; 3) `{"app": "XGW"}`;
4) `{"error": "не принято"}` — без привязки состояние шлюза не отдаётся.

Если не так:

- 1) не открылось без VPN, а 3) открылось — **наблюдение «Funnel из мобильной сети доступен
  только через VPN»** (это допустимо: приложение почти всегда с VPN; так и записать).
- 1) и 3) не открылись, а шаг 4.1 прошёл — **дефект «Funnel не доступен с телефона»**:
  записать, что показал браузер (без адреса).
- 2) «ругался» — записать текст предупреждения (без имён), **дефект «сертификат»**.
- 4) показалось состояние шлюза (серверы, «HEALTHY») — **стоп**, сообщить заказчику:
  состояние отдаётся без привязки; сразу шаг 7.2 с выключением Funnel.

## 5. «Тестовый телефон» через публичный адрес

Только если заказчик согласился на пункт 4 и шаг 4.1 прошёл. Иначе — шаг 6.

Шаг 5.1. Привязка — кодом из QR, который сейчас показан в панели (как камера приложения):

```bash
sudo python3 "$HOME/xgw-a1-test/a1check.py" card | grep 'QR-код есть' || sudo python3 "$HOME/xgw-a1-test/a1check.py" press phones/pair; sudo python3 "$HOME/xgw-a1-test/a1check.py" phone pair | tee "$HOME/xgw-a1-test/after/phone.txt"; sudo python3 "$HOME/xgw-a1-test/a1check.py" card | tee -a "$HOME/xgw-a1-test/after/phone.txt"
```

Ожидается: «привязка через публичный адрес: HTTP 200; имя «Проверка А1»»; в карточке «QR-код
нет; … привязан по последнему коду: Проверка А1» и строка «телефон «Проверка А1»: на связи …».
Если не так: HTTP не 200 — **дефект «привязка не проходит»**, записать; шаги 5.2–5.3
пропустить, перейти к шагу 6.

Шаг 5.2. Состояние, действие, отказы:

```bash
for action in state act replay; do sudo python3 "$HOME/xgw-a1-test/a1check.py" phone $action; done | tee -a "$HOME/xgw-a1-test/after/phone.txt"
```

Ожидается:

- «состояние по публичному адресу: HTTP 200; состояние HEALTHY; серверов в работе N; VPN шлюза
  можно выключить: да» (N — 1 или больше); «секретов в ответе: нет»;
- «кнопка «Проверить запасные» с телефона: HTTP 200; ok=True»;
- «запрещённое действие «добавить подписку» с телефона: HTTP 403»;
- «повтор того же запроса: первый HTTP 200, повтор HTTP 403».

Если не так:

- «секретов в ответе» не «нет» — **дефект «секреты в ответе приложению»**.
- запрещённое действие — не 403, или повтор — не 403: **дефект «защита API»**.
- HTTP 429 — подожди минуту и повтори шаг один раз (лимит запросов), снова 429 — записать.

Шаг 5.3. Конфиг Xray для VPN телефона:

```bash
sudo python3 "$HOME/xgw-a1-test/a1check.py" phone config | tee -a "$HOME/xgw-a1-test/after/phone.txt"; ls "$HOME/xgw-a1-test/phone-config.json" 2>/dev/null || echo "файла конфига нет — так и должно быть"
```

Ожидается: «конфиг для телефона: HTTP 200; серверов N; вход ['tun']; меток шлюза нет» (N — 1
или больше); «Xray шлюза принимает конфиг телефона: да»; «файла конфига нет — так и должно
быть» (в нём ключи серверов — скрипт его удаляет сразу после проверки).
Если не так: HTTP 409 — записать ответ (на шлюзе нет серверов, которые умеет Xray телефона —
**наблюдение**, если все серверы идут через sing-box); «Xray … НЕТ» — **дефект «конфиг
телефона не принимается Xray»**, записать строку.

## 6. Уборка тестового телефона

```bash
sudo python3 "$HOME/xgw-a1-test/a1check.py" phone forget | tee "$HOME/xgw-a1-test/after/forget.txt"; sudo python3 "$HOME/xgw-a1-test/a1check.py" pre | grep 'привязанных' | tee -a "$HOME/xgw-a1-test/after/forget.txt"; ls "$HOME/xgw-a1-test/phone.key" 2>/dev/null || echo "ключа нет"
```

Ожидается: «Телефон «Проверка А1» отвязан», «тестовых телефонов отвязано: 1; ключ удалён»,
«привязанных телефонов: 0», «ключа нет».
Если шаг 5 не выполнялся — «тестовых телефонов отвязано: 0» — тоже верно.

## 7. Итоговое состояние

Шаг 7.1. Подожди 2 минуты после последнего действия, затем:

```bash
systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; sudo xgw status > "$HOME/xgw-a1-test/after/status.txt"; sudo xgw diag > "$HOME/xgw-a1-test/after/diag-end.txt"; tail -1 "$HOME/xgw-a1-test/after/diag-end.txt"; grep -E '^(Состояние|Сейчас)' "$HOME/xgw-a1-test/after/status.txt"; sudo python3 "$HOME/xgw-a1-test/a1check.py" pre | tee "$HOME/xgw-a1-test/after/pre-end.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-a1-test/install-time.txt")" --no-pager | grep -c 'Traceback'; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-a1-test/install-time.txt")" --no-pager | grep -E 'API приложения|телефон' | sudo python3 "$HOME/xgw-a1-test/a1check.py" mask | tail -15 | tee "$HOME/xgw-a1-test/after/journal-a1.txt"
```

Ожидается:

- службы — как в шаге 1.3; «FAIL — 0»; `HEALTHY`; «Сейчас: перехват работает»;
- `pre`: «Funnel 443 (приложение): ведёт на XGW; открыт в интернет: да» (если Funnel включали);
  «Serve 8443 …: ведёт на XGW; открыт в интернет: нет»; «привязанных телефонов: 0»;
- число `Traceback` — `0`;
- журнал: «API приложения слушает 127.0.0.1, порт 8782 (через Funnel)», строки «API
  приложения: запрос отклонён: повтор запроса» и «… привязка …» только от шагов 5.2 — кодов,
  ключей и имён `*.ts.net` в них нет (маска).

Если не так: FAIL не 0 или `Traceback` больше 0 — сохранить подробности:

```bash
grep FAIL "$HOME/xgw-a1-test/after/diag-end.txt" | sudo python3 "$HOME/xgw-a1-test/a1check.py" mask > "$HOME/xgw-a1-test/after/fail.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-a1-test/install-time.txt")" --no-pager | grep -B2 -A12 Traceback | sudo python3 "$HOME/xgw-a1-test/a1check.py" mask > "$HOME/xgw-a1-test/after/traceback.txt"; wc -l "$HOME/xgw-a1-test/after/fail.txt" "$HOME/xgw-a1-test/after/traceback.txt"
```

Шаг 7.2. **Спроси заказчика**: «Адрес для приложения (Funnel) оставить включённым? Приложение
появится в следующей фазе; до тех пор адрес отвечает только „XGW“, а войти без привязки
нельзя.» По умолчанию — оставить (так решил заказчик). Если скажет выключить (или так велит
шаг 3.3 / 4.2):

```bash
sudo python3 "$HOME/xgw-a1-test/a1check.py" press tailscale/funnel '{"on": false}' | tee -a "$HOME/xgw-a1-test/after/final-off.txt"; sudo python3 "$HOME/xgw-a1-test/a1check.py" pre | grep -E 'Funnel' | tee -a "$HOME/xgw-a1-test/after/final-off.txt"
```

Ожидается: «ok=True», «Funnel выключен: …»; «Funnel 443 (приложение): нет»; «… Funnel из
панели нет».

## 8. Если что-то пошло не так

- Новый код не работает — возврат на `tailscale-t2`. Сначала, если панель отвечает, выключи
  Funnel (старый код о нём не знает):

  ```bash
  sudo python3 "$HOME/xgw-a1-test/a1check.py" press tailscale/funnel '{"on": false}' || sudo tailscale funnel --https=443 off; cd ~/zcod/xgw && git checkout tailscale-t2 && git pull --ff-only && sudo sh packaging/install.sh --yes 2>&1 | tail -15; echo "код ${PIPESTATUS[0]}"; systemctl is-active xgw xgw-net xgw-dhcp; cd "$HOME/xgw-a1-test"
  ```

  Ожидается: «код 0», службы `active`. Не помогло — **стоп**, сообщить заказчику.
- Интернета у заказчика нет: `sudo xgw net up; sudo systemctl start xgw; sleep 20;
  sudo xgw status | grep -E '^Перехват|^Состояние'` и сообщить заказчику. `sudo xgw disable` —
  только по его просьбе.
- Связи с машиной нет совсем — заказчик выключает и включает питание шлюза.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-android-a1-<ГГГГ-ММ-ДД>.md` в репозитории (ветка
`android-a1`). Заполни бланк; выводы — только из файлов `$HOME/xgw-a1-test/before` и `after`
(их пишет `a1check.py`, он имён и адресов не печатает) и из выводов, прошедших через
`a1check.py mask`:

```markdown
# Отчёт А1: приложение на телефоне — часть шлюза (ветка android-a1)

Код: <хеш>. Установка: <время>, код <0/…>. Согласие заказчика: пункты <1–4 / какие нет>.

## Итог
<3–4 предложения: включился ли Funnel кнопкой «Привязать телефон» (сразу или после
разрешения); доступен ли публичный адрес из интернета и с телефона (без VPN / с VPN);
привязка и подписанные запросы тестового телефона; конфиг для телефона; итоговое состояние>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до обновления | — | <версия, FAIL — …; serve status> |
| 2.2 установка | пройден / нет | <код, «демон xgw запущен»> |
| 2.3 код и API | пройден / дефект | <А1 в коде; API слушает 8782; Funnel нет> |
| 3.1–3.2 «Привязать телефон» | пройден (А / Б) / дефект | <ответ; ждал ли разрешения; через сколько> |
| 3.3 serve status и Host | пройден / дефект | <Funnel on на 443, 8443 tailnet only; 200 / 421 / 421> |
| 4.1 публичный адрес со шлюза | пройден / дефект | <через N с> |
| 4.2 телефон по мобильной сети | пройден / наблюдение / дефект / не проводилось | <ответы 1–4> |
| 5.1 привязка тестового телефона | пройден / дефект / не проводилось | <HTTP; имя> |
| 5.2 состояние, действие, отказы | пройден / дефект / не проводилось | <200; секретов нет; 403; повтор 403> |
| 5.3 конфиг для телефона | пройден / дефект / не проводилось | <серверов N; tun; Xray принял> |
| 6 уборка | пройден / нет | <отвязан; ключа нет> |
| 7 итоговое состояние | пройден / нет | <FAIL — …; Traceback; Funnel оставлен / выключен> |

## Выводы шагов 2.3–6
<after/pre.txt, after/card.txt, after/press-pair.txt, after/pre-funnel.txt,
after/serve-status.txt, after/local-host.txt, after/public-hello.txt, after/phone.txt,
after/forget.txt — целиком>

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Наблюдения

## Что не проверено и почему
Само приложение для Android — следующие фазы (А2–А3); его роль здесь играл эталонный клиент
`tests/phone_client.py`. Привязка камерой не проверялась — QR-код читал скрипт. Действия
«VPN шлюза вкл/выкл», «выбрать сервер», «устройство мимо VPN» с телефона не нажимались — на
рабочем шлюзе; они идут через тот же код, что кнопки панели (юнит-тесты). `xgw uninstall`
(снимает Funnel, включённый XGW) не выполнялся — запрещено на рабочем шлюзе (юнит-тест).

## Итоговое состояние машины
<Funnel для приложения: включён / выключен; привязанных телефонов: 0; Serve и SSH — как были>
```

Перед коммитом проверь, что в отчёте нет секретов и адресов:

```bash
grep -nE '(vless|vmess|trojan|ss|hysteria2)://[^*]|[0-9a-f]{8}-[0-9a-f]{4}-|[0-9]{8,10}:[A-Za-z0-9_-]{30,}|token=|login=[^*]|[?&]c=[^*]|/sub/|([0-9a-f]{2}:){5}[0-9a-f]{2}|\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]+\.[0-9]+|fd7a:115c|\.ts\.net|login\.tailscale\.com/[a-z]|@[a-z0-9-]+\.[a-z]|PMP response; IP: [0-9]|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+ \(portmap\)' ~/zcod/xgw/docs/TEST-REPORT-REAL-MACHINE-0.1.17-android-a1-*.md
```

Ожидается: пусто или только строки с `100.64.0.0/10`, `100.100.100.100`, `127.0.0.1` — они
разрешены. Метки вида `имя-1.ts-net` (через дефис) — тоже. Если нашлось что-то ещё — убрать из
отчёта (заменить меткой).

Коммит только отчёта: `cd ~/zcod/xgw && git add docs/TEST-REPORT-REAL-MACHINE-0.1.17-android-a1-*.md &&
git commit -m "Отчёт А1: приложение на телефоне — часть шлюза" && git push`. После испытаний
заказчик сам убирает `/etc/sudoers.d/99-xgw-test`, если он больше не нужен.
