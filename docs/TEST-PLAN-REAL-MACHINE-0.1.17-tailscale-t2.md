# Программа испытаний XGW на реальной машине: удалённый доступ через Tailscale (Т2)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§9). Пути в командах — только абсолютные (`$HOME/xgw-t2-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома (LAN `enp4s0`). Стоит XGW **0.1.17** (или
0.1.16 с кодом ветки `tailscale-t1` — записать, что именно), Tailscale 1.104.1 поставлен и
подключён, шлюз в tailnet (отчёт Т1 —
`docs/TEST-REPORT-REAL-MACHINE-0.1.17-tailscale-t1-2026-10-20.md`). Клон репозитория —
`~/zcod/xgw`. Номер версии новый код не меняет: после обновления `xgw --version` пишет
`xgw 0.1.17`. Новый код узнаётся по строке «Т2 в установленном коде: есть» (шаг 2.3).

Что нового (ASSUMPTIONS п. 220, фаза Т2 `TAILSCALE_MINIAPP_PLAN.md`). В панели XGW — карточка
«Tailscale»: вход шлюза в tailnet (кнопка и QR-код), переключатели «SSH через Tailscale» и
«Панель по tailnet», выбор «Маршрут Tailscale» (напрямую / через VPN) и предупреждения о двух
ловушках (адрес провайдера из 100.64.0.0/10, «Override local DNS») с кнопкой исправления.
«Панель по tailnet» — это Tailscale Serve: панель открывается с телефона и ноутбука с
включённым Tailscale по `https://<имя шлюза>.<tailnet>.ts.net:8443/`, из интернета — нет. Бот
Telegram по команде `/panel` присылает одноразовую ссылку туда (15 минут, один вход).

Решения заказчика (уже приняты): SSH — через Tailscale SSH, панель по tailnet на порту 8443 —
включать, маршрут Tailscale — напрямую.

Как проверяется без браузера. Скрипт `t2check.py` открывает панель на самой машине по её
токену — как браузер — и показывает карточку «Tailscale» текстом; «нажать кнопку» — тоже он
(`press`), это ровно то, что делает кнопка в браузере. Имён и адресов tailnet скрипт не
печатает: только «есть / нет» и метки вроде `устройство-1`. Единственное исключение —
`enable-link` (шаг 5.2): эту ссылку видит только заказчик, в отчёт она не идёт.

Цели:

1. Снимок до обновления (шаг 1.3).
2. Поставить новый код (шаг 2).
3. Карточка после обновления: Tailscale виден демону XGW, кнопка входа не ломает уже
   выполненный вход, панель по tailnet ещё не принимается (шаг 3).
4. SSH через Tailscale (шаг 4).
5. Панель по tailnet: включение, разрешение HTTPS в tailnet (если попросит), проверка на
   шлюзе и с телефона заказчика, ссылка `/panel` из бота (шаг 5).
6. Маршрут «через VPN» на минуту и обратно — только с согласия заказчика (шаг 6).
7. Итоговое состояние (шаг 7), отчёт (§9).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**.
- Команды Tailscale, кроме `tailscale status`, `tailscale debug prefs` и
  `tailscale serve status` из шагов: **нельзя** `tailscale up`, `down`, `set`, `login`,
  `logout`, `switch`, `serve` (кроме `serve status` и аварийного шага в §8), `funnel`, `cert`,
  `ssh`, `file`, `lock`, `update`. Настройки Tailscale меняются **только** кнопками карточки
  через `t2check.py press` — в шагах, где это написано.
- Кнопки «Выключить фаервол Tailscale» и «Не принимать DNS из tailnet» (`press fix …`) —
  **не нажимать**, даже если предупреждение появилось: только записать.
- Вход в консоль tailnet (login.tailscale.com) и изменения там — только сам заказчик.
- Запуск, остановка и перезапуск `tailscaled`, `xgw`, `xgw-xray`, `xgw-singbox`, `xgw-net`,
  `xgw-dhcp`, `systemd-resolved`, NetworkManager, `ssh`/`sshd`.
- Ручные команды `nft` (кроме `nft list`), `ip` (кроме `ip … show`), `iptables`,
  `sysctl -w`, `resolvectl` с аргументами, кроме `status`.
- Отключать WAN или LAN: кабели, `ip link set … down`, `nmcli … down`, Wi-Fi роутера.
- Править `/etc/xgw/config.toml`, `/etc/xgw/panel.json`, файлы в `/etc/systemd`,
  `/etc/default/tailscaled`, `/etc/ssh`.
- Править код XGW. Коммитить что-либо, кроме отчёта (§9). Файлы из `~/xgw-t2-test` в Git
  **не класть**.
- Писать в отчёт: адреса tailnet (`100.x.y.z`, кроме `100.100.100.100` и `100.64.0.0/10`;
  `fd7a:…`), имена `*.ts.net` и любые имена устройств, пользователей и самого tailnet,
  почту, ссылки login.tailscale.com, свой внешний IP и адрес провайдера (в том числе в
  строках portmap и `Got PMP response`), токены, коды входа (`?login=…`), адреса подписок,
  UUID, ключи, IP и домены серверов VPN, MAC-адреса. Выводы с такими данными — только через
  `t2check.py mask`, как написано в шагах.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Обновлю XGW: в панели появится карточка „Tailscale“ — с ней шлюзом можно управлять с
телефона и ноутбука через Tailscale. По пунктам:
(1) Установка: демон XGW перезапустится сам, интернет не пропадает, панель и бот секунд на
десять недоступны.
(2) Включу „SSH через Tailscale“ (вы так решили): заходить на шлюз по SSH можно будет только с
ваших устройств в tailnet, по учётной записи Tailscale. Если вы сейчас подключены к шлюзу по
SSH через адрес 100.x — сеанс может оборваться, переподключитесь.
(3) Включу „Панель по tailnet“ (вы так решили): панель откроется с телефона по адресу
https://…ts.net:8443/, только когда на телефоне включён Tailscale. Если в вашем tailnet ещё
не разрешены сертификаты HTTPS, понадобится один раз подтвердить это в консоли Tailscale в
браузере — я подскажу.
(4) Проверка с телефона: включить на телефоне Tailscale (другой VPN на телефоне на это время
выключится), отправить боту /panel, открыть ссылку. И по желанию — зайти на шлюз по SSH с
ноутбука или телефона.
(5) На минуту переключу „Маршрут Tailscale“ на „через VPN“ и верну „напрямую“ — проверить, что
шлюз перестраивает правила сам. Интернет не пропадает.
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против пункта 2 — шаг 4 пропустить («SSH не включался — нет согласия»).
- Против пункта 3 — шаг 5 пропустить; против пункта 4 — пропустить шаги 5.4–5.5.
- Против пункта 5 — шаг 6 пропустить.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-t2-test/before" "$HOME/xgw-t2-test/after" && chmod 700 "$HOME/xgw-t2-test" && cd "$HOME/xgw-t2-test" && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды выполняй из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без пароля
на время испытаний — вводить пароль некому.

Шаг 1.2. Скрипт проверки. Скопируй команду целиком (до строки `T2_EOF` включительно):

```bash
cat > "$HOME/xgw-t2-test/t2check.py" <<'T2_EOF'
"""Т2 XGW (ветка tailscale-t2): удалённый доступ через Tailscale на реальной машине.

sudo python3 t2check.py pre                  код, Tailscale (состояние, SSH, Serve), правила
sudo python3 t2check.py card                 карточка «Tailscale» панели — как её видит браузер
sudo python3 t2check.py press ДЕЙСТВИЕ [JSON] нажать кнопку карточки (то же, что в браузере)
sudo python3 t2check.py host                 принимает ли панель Host «<имя шлюза>:8443»
sudo python3 t2check.py wait-serve           ждать, пока Serve заработает (до 5 минут)
sudo python3 t2check.py wait-set mark|empty  ждать метку в наборе ts_direct (до 60 с)
sudo python3 t2check.py enable-link          ссылка «Разрешить HTTPS» — только заказчику!
sudo python3 t2check.py mask < ФАЙЛ          маскировать вывод (адреса, имена tailnet, почта)

Адресов и имён tailnet скрипт не печатает (кроме enable-link): только «есть», «нет»,
метки «устройство-N». Код XGW он берёт установленный (/opt/xgw/lib), в /etc/xgw ничего не
правит; кнопки нажимает через панель на 127.0.0.1 по токену — как браузер на этой машине.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

LIB = os.environ.get("XGW_LIB", "/opt/xgw/lib")
sys.path.insert(0, LIB)
from xgw import config, managed  # noqa: E402

CONFIG = Path(os.environ.get("XGW_CONFIG", "/etc/xgw/config.toml"))
TOKEN_FILE = Path(os.environ.get("XGW_T2_TOKEN", "/var/lib/xgw/panel-token"))
MAGIC_DNS = "100.100.100.100"
CGNAT = ipaddress.ip_network("100.64.0.0/10")
TAILNET6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")


def run(argv: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    """Команда с выводом; нет программы или не уложилась — код 127 или 124, а не сбой."""
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


def status() -> dict:
    return as_json(run(["tailscale", "status", "--json"], timeout=20).stdout)


def ts_rules() -> str:
    done = run(["nft", "list", "table", "ip", "xgw"])
    if done.returncode != 0:
        return "нет таблицы"
    text = done.stdout
    has = '"tailscale0"' in text
    match = re.search(r"^\s*set ts_direct \{\n(.*?)^\s*\}", text, flags=re.MULTILINE | re.DOTALL)
    mark = "набора нет" if match is None else (
        "метка в наборе" if "elements" in match.group(1) else "набор пуст")
    return ("есть" if has else "нет") + f" ({mark})"


def word(value) -> str:
    return {True: "да", False: "нет", None: "неизвестно"}.get(value, str(value))


# --- панель --------------------------------------------------------------------------


def panel_port() -> int:
    cfg, _warnings = config.load(CONFIG)
    return int(cfg.panel.port)


def request(method: str, path: str, *, cookie: str = "", body: dict | None = None,
            host: str = "") -> tuple[int, str, http.client.HTTPResponse]:
    port = panel_port()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    headers = {"Host": host or f"127.0.0.1:{port}"}
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


def card(cookie: str = "") -> dict:
    code, text, _response = request("GET", "/api/state", cookie=cookie or login())
    if code != 200:
        raise SystemExit(f"состояние панели: HTTP {code}")
    return as_json(text).get("tailscale") or {}


def cmd_pre() -> int:
    marker = Path(LIB) / "xgw" / "qr.py"
    print("Т2 в установленном коде:", "есть" if marker.exists() else "НЕТ")
    version = run(["/usr/local/bin/xgw", "--version"]).stdout.strip()
    print("версия:", version or "неизвестно")
    active = run(["systemctl", "is-active", "tailscaled"]).stdout.strip()
    state = status()
    print(f"tailscaled: {active or 'неизвестно'}; BackendState: "
          f"{state.get('BackendState') or 'неизвестно'}")
    prefs = as_json(run(["tailscale", "debug", "prefs"], timeout=20).stdout)
    print(f"prefs RunSSH: {word(prefs.get('RunSSH'))}; NetfilterMode: "
          f"{prefs.get('NetfilterMode', 'неизвестно')}; CorpDNS: {word(prefs.get('CorpDNS'))}")
    serve = as_json(run(["tailscale", "serve", "status", "--json"], timeout=20).stdout)
    port = panel_port()
    proxies = [
        str(((conf.get("Handlers") or {}).get("/") or {}).get("Proxy") or "")
        for host, conf in (serve.get("Web") or {}).items()
        if str(host).endswith(":8443") and isinstance(conf, dict)
    ]
    if not proxies:
        print("Serve на 8443: нет")
    elif f"http://127.0.0.1:{port}" in [item.rstrip("/") for item in proxies]:
        print("Serve на 8443: ведёт на панель XGW")
    else:
        print("Serve на 8443: ведёт НЕ на панель XGW")
    other = [host for host in (serve.get("Web") or {}) if not str(host).endswith(":8443")]
    print("другие Serve/Funnel:", "есть" if other or serve.get("AllowFunnel") else "нет")
    data, error = managed.load(managed.path_for(CONFIG))
    flag = data["tailscale"]
    print(f"panel.json: панель по tailnet включена из панели: {word(bool(flag['serve']))}; "
          f"маршрут из панели: {flag['route'] or 'нет (как в config.toml)'}"
          + (f"; ОШИБКА: {error}" if error else ""))
    print("исключения Tailscale в ip xgw:", ts_rules())
    return 0


def cmd_card() -> int:
    item = card()
    serve = item.get("serve") or {}
    print("состояние:", item.get("state") or "нет карточки")
    print("имя шлюза в tailnet:", "есть" if item.get("name") else "нет",
          "; адрес 100.x:", "есть" if item.get("address") else "нет")
    print("ссылка входа:", "есть" if item.get("auth_url") else "нет",
          "; вход идёт:", word(item.get("login_pending")))
    print("SSH через Tailscale:", word(item.get("ssh")))
    print(f"панель по tailnet: включена {word(serve.get('on'))}; Serve отвечает "
          f"{word(serve.get('live'))}; ждёт HTTPS {word(serve.get('pending'))}; ссылка "
          f"«Разрешить HTTPS»: {'есть' if serve.get('enable_url') else 'нет'}; адрес: "
          f"{'есть' if serve.get('url') else 'нет'}")
    print(f"маршрут: {item.get('route')}; выбран в панели: {word(item.get('route_panel'))}")
    print("К5 CGNAT:", ", ".join(item.get("cgnat") or []) or "нет",
          "; фаервол Tailscale выключен:", word(item.get("netfilter_off")))
    print("К6 Override local DNS:", word(item.get("override_dns")))
    return 0


def cmd_press(name: str, body: str) -> int:
    payload = json.loads(body) if body else {}
    started = time.monotonic()
    code, text, _response = request("POST", f"/api/tailscale/{name}", cookie=login(),
                                    body=payload)
    took = time.monotonic() - started
    result = as_json(text)
    if code != 200:
        print(f"кнопка {name}: HTTP {code}: {Masker(status()).mask(text.strip())}")
        return 1
    print(f"кнопка {name} {json.dumps(payload, ensure_ascii=False)}: ok={result.get('ok')}, "
          f"{took:.1f} с")
    masker = Masker(status())
    print("  ответ:", masker.mask(str(result.get("text") or "")))
    for note in result.get("notes") or []:
        print("  пояснение:", masker.mask(str(note)))
    return 0 if result.get("ok") else 1


def cmd_host() -> int:
    cookie = login()
    name = str(card(cookie).get("name") or "")
    if not name:
        print("имя шлюза в tailnet неизвестно — проверять нечего")
        return 1
    labels = Masker(status())
    for host, what in ((f"{name}:8443", "своё имя :8443"),
                       (f"other-{name}:8443", "чужое имя :8443"),
                       (name, "своё имя без порта"), (f"{name}:443", "своё имя :443")):
        code, _text, _response = request("GET", "/api/state", cookie=cookie, host=host)
        print(f"Host {what} ({labels.mask(host)}): HTTP {code}")
    return 0


def cmd_wait_serve() -> int:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        serve = card().get("serve") or {}
        if serve.get("live") is True:
            print("Serve отвечает: да, через",
                  f"{300 - (deadline - time.monotonic()):.0f} с")
            return 0
        time.sleep(10)
    print("Serve отвечает: НЕТ за 5 минут")
    return 1


def cmd_wait_set(want: str) -> int:
    expected = "метка в наборе" if want == "mark" else "набор пуст"
    started = time.monotonic()
    while time.monotonic() - started < 60:
        found = ts_rules()
        if expected in found:
            print(f"исключения Tailscale в ip xgw: {found} — через "
                  f"{time.monotonic() - started:.0f} с")
            return 0
        time.sleep(2)
    print(f"исключения Tailscale в ip xgw: {ts_rules()} — за 60 с не стало «{expected}»")
    return 1


def cmd_enable_link() -> int:
    link = str((card().get("serve") or {}).get("enable_url") or "")
    print(link or "ссылки нет: Serve не ждёт разрешения HTTPS")
    return 0


class Masker:
    """Адреса tailnet → 100.x.y.N и fd7a:…:N, внешние → внешний-IP-N, адрес провайдера в
    строках portmap → адрес-провайдера; имена устройств, пользователей и tailnet — метками."""

    def __init__(self, state: dict) -> None:
        self.maps: dict[str, dict[str, str]] = {}
        self.names: dict[str, str] = {}
        nodes = [state.get("Self") or {}, *(state.get("Peer") or {}).values()]
        for node in nodes:
            for key in ("HostName", "DNSName"):
                value = str(node.get(key) or "").rstrip(".")
                self.add(value, "устройство-{}")
                self.add(value.split(".")[0], "устройство-{}")
        tailnet = state.get("CurrentTailnet") or {}
        for value in (state.get("MagicDNSSuffix"), tailnet.get("MagicDNSSuffix"),
                      tailnet.get("Name"), *(state.get("CertDomains") or [])):
            self.add(str(value or ""), "tailnet-{}")
        for user in (state.get("User") or {}).values():
            for key in ("LoginName", "DisplayName"):
                self.add(str(user.get(key) or ""), "пользователь-{}")
        self.add(socket.gethostname(), "устройство-{}")

    def label(self, kind: str, value: str, fmt: str) -> str:
        table = self.maps.setdefault(kind, {})
        return table.setdefault(value, fmt.format(len(table) + 1))

    def add(self, value: str, fmt: str) -> None:
        value = value.strip().lower()
        if len(value) >= 3 and value not in ("localhost", "ubuntu"):
            self.names.setdefault(value, self.label(fmt, value, fmt))

    def _ip(self, match: re.Match) -> str:
        text = match.group(0)
        bare, _, prefix = text.partition("/")
        try:
            address = ipaddress.ip_address(bare)
        except ValueError:
            return text
        tail = f"/{prefix}" if prefix else ""
        if str(address) == MAGIC_DNS or address in (CGNAT.network_address,
                                                    TAILNET6.network_address):
            return text
        if address.version == 4 and address in CGNAT:
            return self.label("ts4", bare, "100.x.y.{}") + tail
        if address.version == 6 and address in TAILNET6:
            return self.label("ts6", bare, "fd7a:…:{}") + tail
        if address.is_global and not address.is_multicast:
            return self.label("ext", bare, "внешний-IP-{}") + tail
        return text

    def mask(self, text: str) -> str:
        # Адрес роутера у провайдера (часто частный 10.x — CGNAT) в строках portmap.
        text = re.sub(r"(Got PMP response; IP: )[0-9a-fA-F.:]+", r"\1адрес-провайдера", text)
        text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}(:\d+ \(portmap\))", r"адрес-провайдера\1", text)
        text = re.sub(r"\b(nodekey|discokey|machinekey|mkey|nlpub|privkey):[0-9a-fA-F]+",
                      r"\1:***", text)
        text = re.sub(r"\btskey-[A-Za-z0-9-]+", "tskey-***", text)
        text = re.sub(r"[?&]login=[A-Za-z0-9_-]+", "?login=***", text)
        text = re.sub(r"(https?://)([^/\s\"']+)(/[^\s\"']*)?",
                      lambda m: m.group(1) + m.group(2) + ("/…" if m.group(3) else ""), text)
        text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "почта@…", text)
        text = re.sub(r"[\w.+-]+@(?=\s|$)", "пользователь@", text, flags=re.MULTILINE)
        text = re.sub(r"\b([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "MAC-скрыт", text)
        for value in sorted(self.names, key=len, reverse=True):
            text = re.sub(re.escape(value), self.names[value], text, flags=re.IGNORECASE)
        # Имя *.ts.net, которого нет в status (чужое, устаревшее), — тоже меткой.
        text = re.sub(r"\b[\w-]+(\.[\w-]+)*\.ts\.net\b",
                      lambda m: self.label("ts-name", m.group(0).lower(), "имя-{}.ts-net"),
                      text, flags=re.IGNORECASE)
        text = re.sub(r"(?<![\w:.])(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}(?:/\d{1,3})?"
                      r"(?![\w:])", self._ip, text)
        return re.sub(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?(?![\w.])", self._ip, text)


def cmd_mask() -> int:
    sys.stdout.write(Masker(status()).mask(sys.stdin.read()))
    return 0


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("нужен root: sudo python3 t2check.py …")
        return 2
    if not argv:
        print(__doc__)
        return 2
    command, rest = argv[0], argv[1:]
    if command == "pre":
        return cmd_pre()
    if command == "card":
        return cmd_card()
    if command == "press" and rest:
        return cmd_press(rest[0], rest[1] if len(rest) > 1 else "")
    if command == "host":
        return cmd_host()
    if command == "wait-serve":
        return cmd_wait_serve()
    if command == "wait-set" and rest and rest[0] in ("mark", "empty"):
        return cmd_wait_set(rest[0])
    if command == "enable-link":
        return cmd_enable_link()
    if command == "mask":
        return cmd_mask()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
T2_EOF
sha256sum "$HOME/xgw-t2-test/t2check.py"
```

Ожидается: `14ca227c636689aa454a5ba9f0f644ad7ffc54aaad0e6dcb506eae25c540c1b7` в начале строки.
Если хеш другой: файл скопирован не целиком — повторить шаг 1.2 один раз; если снова другой —
**стоп**, сообщить заказчику.

Шаг 1.3. Снимок до обновления:

```bash
cd "$HOME/xgw-t2-test" && sudo xgw --version; sudo xgw status > "$HOME/xgw-t2-test/before/status.txt"; sudo xgw diag > "$HOME/xgw-t2-test/before/diag.txt"; tail -1 "$HOME/xgw-t2-test/before/diag.txt"; grep -E '^Состояние' "$HOME/xgw-t2-test/before/status.txt"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled | tee "$HOME/xgw-t2-test/before/services.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" pre | tee "$HOME/xgw-t2-test/before/pre.txt"
```

Ожидается:

- `xgw 0.1.17` (или `xgw 0.1.16` — записать, какая), итог diag с «FAIL — 0», состояние
  `HEALTHY`, службы `active` (у `xgw-singbox` допустимо `inactive` — записать);
- «Т2 в установленном коде: НЕТ» (так и должно быть до обновления);
- «tailscaled: active; BackendState: Running»;
- строку «prefs RunSSH: …; NetfilterMode: …; CorpDNS: …» — записать как есть (ожидается
  «RunSSH: нет; NetfilterMode: 2; CorpDNS: да», как в отчёте Т1);
- «Serve на 8443: нет»; «другие Serve/Funnel: нет»;
- «panel.json: … включена из панели: нет; маршрут из панели: нет (как в config.toml)»;
- «исключения Tailscale в ip xgw: есть (метка в наборе)».

Если не так:

- FAIL не 0 или состояние не `HEALTHY`: записать в отчёт как есть и **спросить заказчика**,
  продолжать ли.
- `tailscaled` не `active` или BackendState не `Running`: **стоп**, сообщить заказчику
  (Tailscale должен быть включён и подключён; входит в tailnet заказчик сам).
- «Serve на 8443» не «нет» или «другие Serve/Funnel: есть»: **стоп**, спросить заказчика —
  кто-то уже настроил Serve; шаг 5 может его заменить.
- `RunSSH: да` — SSH через Tailscale уже включён: записать, шаг 4.1 всё равно выполнить
  (кнопка ничего не испортит).
- «исключения …» не «есть (метка в наборе)» — записать (это Т1), продолжать.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout tailscale-t2 && git pull --ff-only && git log -1 --format='%h %s' && test -f src/xgw/qr.py && echo "Т2 в коде: есть"; grep __version__ src/xgw/__init__.py; cd "$HOME/xgw-t2-test"
```

Ожидается: «Т2 в коде: есть» и `__version__ = "0.1.17"`. Записать хеш.
Если ветки `tailscale-t2` нет или «Т2 в коде: есть» не напечатано: **стоп**, сообщить заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-t2-test/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-t2-test/after/install.txt" | tail -25; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-t2-test"
```

Ожидается: «код 0» и строка «демон xgw запущен».
Если код не 0: **стоп**, сохранить вывод, выполнить §8 (возврат на `main`), сообщить
заказчику.

Шаг 2.3. Установленный код и карточка:

```bash
sleep 20; sudo xgw --version; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; sudo python3 "$HOME/xgw-t2-test/t2check.py" pre | tee "$HOME/xgw-t2-test/after/pre.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" card | tee "$HOME/xgw-t2-test/after/card.txt"
```

Ожидается:

- `xgw 0.1.17`; службы — как в шаге 1.3;
- «Т2 в установленном коде: есть»; строки prefs, Serve и panel.json — как в шаге 1.3;
- карточка: «состояние: running»; «имя шлюза в tailnet: есть ; адрес 100.x: есть»; «ссылка
  входа: нет»; «SSH через Tailscale: нет» (или «да», если было «да» в шаге 1.3); «панель по
  tailnet: включена нет; …»; «маршрут: direct; выбран в панели: нет»; «К5 CGNAT: нет»; «К6
  Override local DNS: нет».

Состояние «running» в карточке значит, что демон XGW из своей защищённой службы
(`ProtectSystem=strict`) достучался до `tailscaled` — это отдельный пункт отчёта.

Если не так:

- «Т2 в установленном коде: НЕТ» — **стоп**: установка не обновила код; сообщить заказчику.
- `xgw` не `active` — подожди 30 с, проверь ещё раз; снова не `active` — §8.
- «состояние: unknown» или «stopped» при `tailscaled: active` — **дефект «демон не видит
  Tailscale»**: выполнить
  `sudo journalctl -u xgw -n 60 --no-pager | sudo python3 "$HOME/xgw-t2-test/t2check.py" mask > "$HOME/xgw-t2-test/after/xgw-journal.txt"`,
  записать; шаги 3–6 пропустить, перейти к шагу 7.
- «К5 CGNAT» или «К6 …» не «нет» — записать строку (кнопки исправления **не** нажимать),
  продолжать.

## 3. Карточка: вход и чужой Host

Шаг 3.1. Кнопка «Войти в Tailscale», когда шлюз уже в tailnet: XGW **не** должен начинать
новый вход (иначе Tailscale переключился бы на пустой профиль).

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" press login | tee "$HOME/xgw-t2-test/after/press-login.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" pre | grep -E 'BackendState|prefs' | tee -a "$HOME/xgw-t2-test/after/press-login.txt"; pgrep -af '[t]ailscale login' || echo "tailscale login не запущен"
```

Ожидается: «кнопка login {}: ok=True», «ответ: Шлюз уже в tailnet»; «BackendState: Running»;
строка prefs — как в шаге 2.3; «tailscale login не запущен».
Если не так: ответ другой, BackendState не `Running` или процесс `tailscale login` есть —
**дефект «кнопка входа трогает подключённый шлюз»**: записать вывод, **стоп**, сообщить
заказчику (вход в tailnet восстанавливает заказчик сам).

Шаг 3.2. Панель по tailnet ещё выключена — её адрес не должен приниматься:

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" host | tee "$HOME/xgw-t2-test/after/host-before.txt"
```

Ожидается: четыре строки, все «HTTP 403».
Если хоть одна «HTTP 200» — **дефект «панель принимает адрес tailnet без включения»**:
записать, продолжать.

## 4. SSH через Tailscale

Только если заказчик согласился на пункт 2. Иначе — шаг 5.

Шаг 4.1. Включить:

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" press ssh '{"on": true}' | tee "$HOME/xgw-t2-test/after/press-ssh.txt"; sleep 5; sudo python3 "$HOME/xgw-t2-test/t2check.py" pre | grep -E 'prefs' | tee -a "$HOME/xgw-t2-test/after/press-ssh.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" card | grep -E 'SSH' | tee -a "$HOME/xgw-t2-test/after/press-ssh.txt"
```

Ожидается: «ok=True», «ответ: SSH через Tailscale включён» (и пояснение); «prefs RunSSH: да»
(NetfilterMode и CorpDNS — как раньше); «SSH через Tailscale: да».
Если не так: «ok=False» — записать ответ целиком (**дефект «SSH не включается»**),
продолжать с шага 5.

Шаг 4.2. Проверка заказчиком — только если он согласился на пункт 4 и хочет проверить SSH.
**Скажи заказчику**: «С ноутбука или телефона, где включён Tailscale, зайдите на шлюз:
`ssh ВАШ-ПОЛЬЗОВАТЕЛЬ@ИМЯ-ШЛЮЗА` (имя шлюза — как в приложении Tailscale). Tailscale может
попросить подтвердить вход в браузере — это нормально. Удалось войти?»

Записать ответ: «вошёл», «попросил подтверждение в браузере и вошёл», «не пустило: <что
написано>» (без имён и адресов). «Не пустило» с сообщением про правила доступа (policy, ACL,
`tailnet policy does not permit`) — **наблюдение**, не дефект: кто и под каким пользователем
входит, решают правила в консоли tailnet. Другое — **дефект «SSH через Tailscale не
работает»**.

## 5. Панель по tailnet

Только если заказчик согласился на пункт 3. Иначе — шаг 6.

Шаг 5.1. Включить:

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" press serve '{"on": true}' | tee "$HOME/xgw-t2-test/after/press-serve.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" card | grep -E 'панель по tailnet' | tee -a "$HOME/xgw-t2-test/after/press-serve.txt"
```

Ожидается одно из двух:

- А: «ok=True», «ответ: Панель по tailnet включена — адрес в карточке» и «панель по tailnet:
  включена да; Serve отвечает да; ждёт HTTPS нет» — перейти к шагу 5.3;
- Б: «ok=True», «ответ: Осталось разрешить HTTPS в tailnet» и «панель по tailnet: включена да;
  Serve отвечает нет; ждёт HTTPS да; ссылка «Разрешить HTTPS»: есть» — шаг 5.2.

Если не так: «ok=False» — записать ответ (**дефект «панель по tailnet не включается»**),
шаг 5 дальше не выполнять, перейти к шагу 6.

Шаг 5.2. Только для варианта Б. **Скажи заказчику**: «Откройте панель XGW на шлюзе (ярлык
„XGW“), карточка „Tailscale“, нажмите „Разрешить HTTPS в tailnet“ и подтвердите в открывшейся
консоли Tailscale. Скажите, когда подтвердите.» Если заказчику удобнее, чтобы ссылку прислал
ты, выполни (вывод покажи **только** заказчику, в файлы и отчёт его не писать):

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" enable-link
```

Когда заказчик скажет «подтвердил»:

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" wait-serve | tee "$HOME/xgw-t2-test/after/wait-serve.txt"
```

Ожидается: «Serve отвечает: да, через N с» (до 5 минут).
Если «Serve отвечает: НЕТ за 5 минут» — спроси заказчика, подтвердил ли он в консоли, и
выполни `wait-serve` ещё раз (тот же `tee`, но в файл `$HOME/xgw-t2-test/after/wait-serve-2.txt`);
снова НЕТ — **дефект «Serve не заработал после разрешения HTTPS»**, записать, перейти к шагу 6.

Шаг 5.3. Проверка на шлюзе: адрес tailnet теперь принимается, чужие — нет; что именно
настроил Tailscale:

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" host | tee "$HOME/xgw-t2-test/after/host-after.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" pre | grep -E 'Serve|panel.json' | tee -a "$HOME/xgw-t2-test/after/host-after.txt"; sudo tailscale serve status 2>&1 | sudo python3 "$HOME/xgw-t2-test/t2check.py" mask | tee "$HOME/xgw-t2-test/after/serve-status.txt"
```

Ожидается:

- «Host своё имя :8443 (…): HTTP 200», остальные три — «HTTP 403»;
- «Serve на 8443: ведёт на панель XGW»; «другие Serve/Funnel: нет»; «panel.json: панель по
  tailnet включена из панели: да; …»;
- `tailscale serve status` (маскированный): строка вида `https://устройство-N:8443 (tailnet
  only)` и под ней `|-- / proxy http://127.0.0.1:8781`. Слова `Funnel on` быть не должно.

Если не так:

- своё имя — не 200 или чужое — 200: **дефект «Host панели по tailnet»**, записать.
- В `serve status` есть `Funnel` или `(Funnel on)` — **стоп**, сообщить заказчику: панель
  открыта в интернет (так быть не должно); сразу выполнить шаг 7.2 (выключение).
- В маскированном выводе видно настоящее имя или адрес — **не** записывать его в отчёт;
  записать «маскировка пропустила …» (без самого значения).

Шаг 5.4. Телефон заказчика — только при согласии на пункт 4. **Скажи заказчику**:
«На телефоне включите Tailscale. Отправьте боту XGW в Telegram команду /panel и откройте
ссылку из ответа. 1) Открылась панель XGW без запроса токена? 2) Браузер не ругался на
сертификат? 3) Видны ваши серверы и кнопка VPN? Потом нажмите на ту же ссылку ещё раз:
4) что показалось — панель или страница входа? И 5) выключите на телефоне Tailscale и снова
откройте https://…ts.net:8443/ (адрес из карточки „Tailscale“ на шлюзе) — открылось?»

Ожидается: 1) да; 2) нет (сертификат в порядке); 3) да; 4) панель, если браузер запомнил вход
(cookie), или страница входа «нужен токен» — оба ответа верны: ссылка одноразовая, а
повторный заход держится на cookie; 5) нет — без Tailscale адрес не открывается.

Если не так:

- 1) «нет, просит токен» — сразу (в первые 15 минут после `/panel`) — **дефект «ссылка
  /panel не пускает»**; бот ответил «Панель по tailnet выключена» — **дефект** (шаг 5.3
  показал, что она включена).
- 2) «ругался» — записать текст предупреждения (без имён), **дефект «сертификат»**.
- 5) «открылось» без Tailscale — **стоп**, сообщить заказчику (панель видна не только
  tailnet), сразу шаг 7.2.
- Бот не ответил на `/panel` минуту — записать (наблюдение), продолжать.

Шаг 5.5. Записать после ответов заказчика (журнал без кодов и адресов):

```bash
sudo journalctl -u xgw --since "$(cat "$HOME/xgw-t2-test/install-time.txt")" --no-pager | grep -E 'Telegram|Tailscale|tailnet|панель' | sudo python3 "$HOME/xgw-t2-test/t2check.py" mask | tail -20 | tee "$HOME/xgw-t2-test/after/journal-t2.txt"; sudo xgw status | grep -E 'ссылка в панель|Tailscale' | sudo python3 "$HOME/xgw-t2-test/t2check.py" mask | tee -a "$HOME/xgw-t2-test/after/journal-t2.txt"
```

Ожидается: среди событий есть «Tailscale: панель по tailnet включена» и (если заказчик
отправил `/panel`) «Telegram: выдана ссылка в панель по tailnet». Строк `?login=` с кодом
быть не должно (маска заменяет код на `***`; если видно сам код — записать «код попал в
журнал» как **дефект**, без самого кода).

## 6. Маршрут Tailscale «через VPN» и обратно

Только если заказчик согласился на пункт 5. Иначе — шаг 7.

Шаг 6.1:

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" press route '{"route": "vpn"}' | tee "$HOME/xgw-t2-test/after/route.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" wait-set empty | tee -a "$HOME/xgw-t2-test/after/route.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" press route '{"route": "direct"}' | tee -a "$HOME/xgw-t2-test/after/route.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" wait-set mark | tee -a "$HOME/xgw-t2-test/after/route.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" card | grep -E 'маршрут' | tee -a "$HOME/xgw-t2-test/after/route.txt"; sudo tailscale status --json | python3 -c "import json,sys; print('BackendState после смены маршрута:', json.load(sys.stdin).get('BackendState'))" | tee -a "$HOME/xgw-t2-test/after/route.txt"
```

Ожидается, по порядку:

- «кнопка route {"route": "vpn"}: ok=True», «ответ: Tailscale идёт через VPN, пока Xray
  отвечает»;
- «исключения Tailscale в ip xgw: есть (набор пуст) — через N с» (N — до 60);
- «кнопка route {"route": "direct"}: ok=True», «ответ: Tailscale идёт напрямую, мимо VPN»;
- «исключения Tailscale в ip xgw: есть (метка в наборе) — через N с»;
- «маршрут: direct; выбран в панели: да»;
- «BackendState после смены маршрута: Running».

Если не так:

- «за 60 с не стало …» — **дефект «маршрут из панели не перестраивает правила»**: записать;
  если последняя строка про набор не «метка в наборе» — сразу выполнить
  `sudo xgw net up; sleep 10; sudo python3 "$HOME/xgw-t2-test/t2check.py" pre | grep исключения`
  и записать вывод.
- BackendState не `Running` — подожди минуту, проверь ещё раз (`sudo tailscale status`
  первой строкой); снова не `Running` — **дефект**, сообщить заказчику.

## 7. Итоговое состояние

Шаг 7.1. Подожди 2 минуты после последнего действия, затем:

```bash
systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; sudo xgw status > "$HOME/xgw-t2-test/after/status.txt"; sudo xgw diag > "$HOME/xgw-t2-test/after/diag-end.txt"; tail -1 "$HOME/xgw-t2-test/after/diag-end.txt"; grep -E '^(Состояние|Сейчас)' "$HOME/xgw-t2-test/after/status.txt"; grep -E 'Tailscale' "$HOME/xgw-t2-test/after/diag-end.txt" | sudo python3 "$HOME/xgw-t2-test/t2check.py" mask; sudo python3 "$HOME/xgw-t2-test/t2check.py" pre | tee "$HOME/xgw-t2-test/after/pre-end.txt"; sudo python3 "$HOME/xgw-t2-test/t2check.py" card | tee "$HOME/xgw-t2-test/after/card-end.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-t2-test/install-time.txt")" --no-pager | grep -c 'Traceback'
```

Ожидается:

- службы — как в шаге 1.3; «FAIL — 0»; `HEALTHY`; «Сейчас: перехват работает»;
- строки diag «Tailscale…» — как в отчёте Т1 (все OK);
- `pre`: «Т2 в установленном коде: есть»; «BackendState: Running»; «prefs RunSSH: да» (если
  выполнялся шаг 4); «Serve на 8443: ведёт на панель XGW» (если выполнялся шаг 5);
  «исключения Tailscale в ip xgw: есть (метка в наборе)»;
- карточка — «состояние: running», SSH и панель по tailnet — как включены;
- последнее число — `0`.

Если не так: FAIL не 0 или число `Traceback` больше 0 — сохранить подробности и записать
дефект с этими файлами:

```bash
grep FAIL "$HOME/xgw-t2-test/after/diag-end.txt" | sudo python3 "$HOME/xgw-t2-test/t2check.py" mask > "$HOME/xgw-t2-test/after/fail.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-t2-test/install-time.txt")" --no-pager | grep -B2 -A12 Traceback | sudo python3 "$HOME/xgw-t2-test/t2check.py" mask > "$HOME/xgw-t2-test/after/traceback.txt"; wc -l "$HOME/xgw-t2-test/after/fail.txt" "$HOME/xgw-t2-test/after/traceback.txt"
```

Шаг 7.2. **Спроси заказчика**: «SSH через Tailscale и панель по tailnet оставить включёнными
(как вы решили) или выключить?» По умолчанию — оставить. Если заказчик скажет выключить —
выполни только нужное:

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" press serve '{"on": false}' | tee -a "$HOME/xgw-t2-test/after/final-off.txt"
```

```bash
sudo python3 "$HOME/xgw-t2-test/t2check.py" press ssh '{"on": false}' | tee -a "$HOME/xgw-t2-test/after/final-off.txt"
```

Ожидается: «ok=True», «Панель по tailnet выключена» / «SSH через Tailscale выключен». После
выключения панели `sudo python3 "$HOME/xgw-t2-test/t2check.py" host` — все четыре «HTTP 403».

## 8. Если что-то пошло не так

- Демон `xgw` не `active` после установки или новый код не работает — возврат на `main`.
  Сначала, если панель отвечает, выключи панель по tailnet (иначе Serve останется, а старый
  код его адрес не примет):

  ```bash
  sudo python3 "$HOME/xgw-t2-test/t2check.py" press serve '{"on": false}' || sudo tailscale serve --https=8443 off; cd ~/zcod/xgw && git checkout main && git pull --ff-only && sudo sh packaging/install.sh --yes 2>&1 | tail -15; echo "код ${PIPESTATUS[0]}"; systemctl is-active xgw xgw-net xgw-dhcp; cd "$HOME/xgw-t2-test"
  ```

  Ожидается: «код 0», службы `active`. Не помогло — **стоп**, сообщить заказчику.
  SSH через Tailscale возврат кода не выключает — это настройка Tailscale, а не XGW.
- Интернета у заказчика нет: `sudo xgw net up; sudo systemctl start xgw; sleep 20;
  sudo xgw status | grep -E '^Перехват|^Состояние'` и сообщить заказчику. `sudo xgw disable`
  (интернет напрямую, мимо VPN) — только по его просьбе.
- Связи с машиной нет совсем (ни у тебя, ни у заказчика) — заказчик выключает и включает
  питание шлюза; Serve и SSH через Tailscale переживают перезагрузку.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-tailscale-t2-<ГГГГ-ММ-ДД>.md` в репозитории (ветка
`tailscale-t2`). Заполни бланк; выводы — только из файлов `$HOME/xgw-t2-test/before` и
`after` (их пишет `t2check.py`, он имён и адресов не печатает) и из выводов, прошедших через
`t2check.py mask`:

```markdown
# Отчёт Т2: удалённый доступ через Tailscale (ветка tailscale-t2)

Код: <хеш>. Установка: <время>, код <0/…>. Было: <xgw 0.1.17 / 0.1.16>. Согласие заказчика:
пункты <1–5 / какие нет>.

## Итог
<3–4 предложения: видит ли демон Tailscale; SSH через Tailscale; панель по tailnet (на шлюзе
и с телефона), ссылка /panel; маршрут; итоговое состояние>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до обновления | — | <версия, FAIL — …; prefs; Serve> |
| 2.2 установка | пройден / нет | <код, «демон xgw запущен»> |
| 2.3 карточка, доступ к tailscaled из службы | пройден / дефект | <состояние; имя/адрес есть; К5, К6> |
| 3.1 «Войти» при выполненном входе | пройден / дефект | <ответ; BackendState; login не запущен> |
| 3.2 Host tailnet до включения | пройден / дефект | <четыре 403> |
| 4.1 SSH через Tailscale | пройден / дефект / не проводилось | <ответ; RunSSH> |
| 4.2 SSH с устройства заказчика | пройден / наблюдение / дефект / не проводилось | <ответ заказчика> |
| 5.1–5.2 панель по tailnet | пройден (А / Б) / дефект / не проводилось | <ответ; ждала ли HTTPS; через сколько заработала> |
| 5.3 Host и serve status | пройден / дефект | <200 / три 403; «ведёт на панель»; без Funnel> |
| 5.4 телефон и /panel | пройден / дефект / не проводилось | <ответы 1–5> |
| 5.5 журнал | пройден / дефект | <события; кода нет> |
| 6 маршрут vpn → direct | пройден / дефект / не проводилось | <набор пуст через N с; метка через N с> |
| 7 итоговое состояние | пройден / нет | <FAIL — …; Traceback; что оставлено включённым> |

## Выводы шагов 2.3, 3, 5.3 и 6
<after/pre.txt, after/card.txt, after/press-login.txt, after/host-before.txt,
after/host-after.txt, after/serve-status.txt, after/route.txt — целиком>

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Наблюдения

## Что не проверено и почему
Вход в tailnet кнопкой карточки (ссылка и QR-код) на машине не проверялся: шлюз уже в tailnet,
а выход из него ради проверки запрещён (проверено в юнит-тестах и в демо панели). Кнопки
исправления К5 и К6 не нажимались: ловушек на машине нет (Т1). `xgw uninstall` (снимает
Serve, включённый XGW) не выполнялся — запрещено на рабочем шлюзе (проверено юнит-тестом).

## Итоговое состояние машины
<SSH через Tailscale: включён / выключен; панель по tailnet: включена / выключена; маршрут>
```

Перед коммитом проверь, что в отчёте нет секретов и адресов:

```bash
grep -nE '(vless|vmess|trojan|ss|hysteria2)://[^*]|[0-9a-f]{8}-[0-9a-f]{4}-|[0-9]{8,10}:[A-Za-z0-9_-]{30,}|token=|login=[^*]|/sub/|([0-9a-f]{2}:){5}[0-9a-f]{2}|\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]+\.[0-9]+|fd7a:115c|\.ts\.net|login\.tailscale\.com/[a-z]|@[a-z0-9-]+\.[a-z]|PMP response; IP: [0-9]|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+ \(portmap\)' ~/zcod/xgw/docs/TEST-REPORT-REAL-MACHINE-0.1.17-tailscale-t2-*.md
```

Ожидается: пусто или только строки с `100.64.0.0/10` и `100.100.100.100` — они разрешены.
Метки вида `имя-1.ts-net` (через дефис) — тоже разрешены, это не настоящие имена. Если нашлось
что-то ещё — убрать из отчёта (заменить меткой).

Коммит только отчёта: `cd ~/zcod/xgw && git add docs/TEST-REPORT-REAL-MACHINE-0.1.17-tailscale-t2-*.md &&
git commit -m "Отчёт Т2: удалённый доступ через Tailscale" && git push`. После испытаний
заказчик сам убирает `/etc/sudoers.d/99-xgw-test`, если он больше не нужен.
