# Программа испытаний XGW на реальной машине: Tailscale рядом с XGW (Т1)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§7).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома (LAN `enp4s0`). Стоит XGW **0.1.16** с
кодом ветки `f2-events`, Tailscale 1.104.1 уже поставлен и подключён (снимок Т0, отчёт
`docs/TEST-REPORT-REAL-MACHINE-0.1.16-tailscale-t0-2026-10-20.md` в ветке `main`). Клон
репозитория — `~/zcod/xgw`. Номер версии не меняется: и после обновления `xgw --version`
пишет `xgw 0.1.16`. Новый код узнаётся по строке «Т1 в установленном коде: есть» (шаг 2.3).

Что нового (ASSUMPTIONS п. 219, фаза Т1 `TAILSCALE_MINIAPP_PLAN.md`). Снимок Т0 показал, что
XGW мешает Tailscale: соединения Tailscale уходили в VPN-сервер (К1), имена `*.ts.net` на
шлюзе не разрешались (К2), в режиме blocked Tailscale был бы отрезан (К3), а по IPv6 —
отрезан всегда (К4). Теперь:

- соединения самого Tailscale (WireGuard, ретрансляторы DERP, вход) идут **напрямую, мимо
  VPN** — так решил заказчик (`[tailscale] route = "direct"`, по умолчанию);
- адреса tailnet, MagicDNS (`100.100.100.100`) и всё, что идёт через `tailscale0`, — мимо
  перехвата и блокировок, в том числе в режиме blocked и по IPv6;
- `xgw diag` — новый раздел «Tailscale».

Как проверяется «мимо VPN», не показывая адресов. Скрипт `t1check.py` открывает три
соединения с Cloudflare и смотрит, каким адресом машина видна снаружи: обычное (идёт через
VPN), с меткой «мимо VPN» самого XGW (напрямую) и с меткой Tailscale `0x80000` — так
помечает свои соединения `tailscaled`. Скрипт печатает только «напрямую», «через VPN» или
«нет связи» — сами адреса не печатаются.

**Важно для исполнителя.** На время окна blocked (шаг 4.2) интернет пропадёт и у этой
машины — значит, и у тебя самого не будет связи. Поэтому возврат сети не зависит от тебя:
окно — одна команда, которую запускает systemd, через минуту она сама возвращает правила; до
окна та же команда ставит страховку — таймер systemd, который через 4 минуты проверит и
вернёт правила сам. `/etc/xgw` программа не меняет: выключение и включение питания шлюза
всегда возвращает обычный режим.

Цели:

1. Снимок до обновления (шаг 1.3): показать К1 и К2 на прежнем коде.
2. Поставить новый код (шаг 2).
3. После обновления (шаг 3): Tailscale мимо Xray, MagicDNS, `tailscale netcheck`,
   `tailscale status` и `tailscale ping` к устройству в сети, `xgw diag`.
4. Окно blocked на минуту — только с согласия заказчика (шаг 4).
5. Итоговое состояние (шаг 5), отчёт (§7).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда** (`xgw disable` — только аварийный путь из шага 4.2 и §6).
- Команды Tailscale, кроме `tailscale status`, `tailscale netcheck` и `tailscale ping` из
  шагов: **нельзя** `tailscale up`, `down`, `set`, `login`, `logout`, `switch`, `serve`,
  `funnel`, `cert`, `ssh`, `file`, `lock`, `update`, `debug`. Вход в консоль tailnet
  (login.tailscale.com) и изменения там — нельзя.
- Запуск, остановка и перезапуск `tailscaled`, `xgw-xray`, `xgw-singbox`, `xgw-net`,
  `xgw-dhcp`, `systemd-resolved`, NetworkManager. Демон `xgw` останавливает и запускает
  **только** команда шага 4.2 (и §6, если что-то пошло не так).
- Ручные команды `nft` (кроме `nft list`), `ip` (кроме `ip … show`), `iptables`,
  `sysctl -w`, `resolvectl` с аргументами, кроме `status` и `query`.
- Отключать WAN или LAN: кабели, `ip link set … down`, `nmcli … down`, Wi-Fi роутера.
- Править `/etc/xgw/config.toml`, `/etc/xgw/panel.json`, файлы в `/etc/systemd`,
  `/etc/default/tailscaled`.
- Менять что-либо в панели XGW.
- Править код XGW. Коммитить что-либо, кроме отчёта (§7). Файлы из `~/xgw-t1-test` в Git
  **не класть**.
- Писать в отчёт: адреса tailnet (`100.x.y.z`, кроме `100.100.100.100` и `100.64.0.0/10`;
  `fd7a:…`), имена устройств, пользователей и самого tailnet, почту, свой внешний IP и адрес
  провайдера, токены, адреса подписок, UUID, ключи, IP и домены серверов VPN, MAC-адреса.
  Выводы с такими данными — только через `t1check.py mask`, как написано в шагах.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Обновлю XGW, чтобы Tailscale на шлюзе работал рядом с VPN: соединения Tailscale пойдут
напрямую, мимо VPN-сервера (провайдер увидит, что на шлюзе работает Tailscale, но не увидит,
что внутри), имена устройств tailnet начнут разрешаться. По пунктам:
(1) Установка: демон XGW и служба DHCP перезапустятся сами, правила сети перезагрузятся одной
операцией. Интернет не пропадает, панель и бот секунд на десять недоступны.
(2) Для проверки связи внутри tailnet нужно, чтобы ещё одно ваше устройство с Tailscale было в
сети — компьютер или телефон с включённым Tailscale. Можете включить его на время проверки?
(3) Окно blocked на одну минуту: интернет пропадёт у всего дома и у этой машины, я проверю,
что Tailscale при этом работает. Через минуту всё вернётся само, страховка — через 4 минуты.
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против пункта 2 — ничего не пропускать: строки про `tailscale ping` скрипт сам заменит на
  «устройств tailnet в сети нет — ping не проверялся».
- Против пункта 3 — шаг 4 пропустить (в отчёте: «окно blocked не проводилось — нет согласия»).

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p ~/xgw-t1-test/before ~/xgw-t1-test/after && chmod 700 ~/xgw-t1-test && cd ~/xgw-t1-test && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды выполняй из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без пароля
на время испытаний — вводить пароль некому.

Шаг 1.2. Скрипт проверки. Скопируй команду целиком (до строки `T1_EOF` включительно):

```bash
cat > ~/xgw-t1-test/t1check.py <<'T1_EOF'
"""Т1 XGW (ветка tailscale-t1): Tailscale рядом с XGW на реальной машине.

sudo python3 t1check.py pre               установленный код, режим правил, исключения Tailscale
sudo python3 t1check.py net               куда уходят сокеты; MagicDNS; netcheck; ping в tailnet
sudo python3 t1check.py mask < ФАЙЛ       маскировать вывод (адреса, имена tailnet, почта)
sudo python3 t1check.py window DIR        окно blocked (вызывать только через systemd-run!)
sudo python3 t1check.py rescue FILE       страховка: вернуть правила, если окно не вернуло

Адресов скрипт не печатает: только «напрямую», «через VPN», «адрес tailnet». Код XGW он берёт
установленный (/opt/xgw/lib) и ничего в /etc/xgw не правит: окно blocked загружает правила по
копии config.toml в DIR, где изменён только capture.tproxy_port, — в работающем Xray такого
inbound'а нет, и шлюз сам выбирает blocked. Окно всегда кончается возвратом: `xgw net up` по
настоящему конфигу и запуск демона; если правила и после этого blocked — `xgw disable`
(интернет напрямую). Страховку rescue ставит таймер systemd до окна.
"""

from __future__ import annotations

import errno
import ipaddress
import json
import os
import re
import shlex
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import time
from pathlib import Path

LIB = os.environ.get("XGW_LIB", "/opt/xgw/lib")
sys.path.insert(0, LIB)
from xgw import config, managed  # noqa: E402

XGW = shlex.split(os.environ.get("XGW_CMD", "/usr/local/bin/xgw"))
CONFIG = Path(os.environ.get("XGW_CONFIG", "/etc/xgw/config.toml"))
DAEMON = os.environ.get("XGW_DAEMON_UNIT", "xgw.service")
TRACE_IP, TRACE_NAME = os.environ.get("XGW_T1_TRACE", "1.1.1.1"), "one.one.one.one"
TS_MARK = 0x80000  # метка сокетов tailscaled
MAGIC_DNS = os.environ.get("XGW_T1_MAGIC_DNS", "100.100.100.100")
CGNAT = ipaddress.ip_network("100.64.0.0/10")
TAILNET6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
WINDOW = int(os.environ.get("XGW_T1_WINDOW", "60"))  # секунд blocked
STEP_TIMEOUT = 90


def run(argv: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    """Команда с выводом; нет программы или не уложилась — код 127 или 124, а не сбой."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]}: нет программы")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"{argv[0]}: таймаут")


def table(family: str, name: str) -> str | None:
    done = run(["nft", "list", "table", family, name])
    if done.returncode != 0:
        return "" if "No such file" in done.stderr else None
    return done.stdout


def mode_of(text: str | None) -> str:
    if text is None:
        return "неизвестно"
    chains = set(re.findall(r"^\s*chain (\w+) \{", text, flags=re.MULTILINE))
    if "block_output" in chains:
        return "blocked"
    if chains & {"prerouting", "output"}:
        return "on"
    return "off" if chains else "нет таблицы"


def ts_rules(text: str | None) -> str:
    if not text:
        return "нет таблицы"
    has = '"tailscale0"' in text
    match = re.search(r"^\s*set ts_direct \{\n(.*?)^\s*\}", text, flags=re.MULTILINE | re.DOTALL)
    mark = "набора нет" if match is None else (
        "метка в наборе" if "elements" in match.group(1) else "набор пуст")
    return ("есть" if has else "нет") + f" ({mark})"


def load_cfg(path: Path):
    cfg, _warnings = config.load(path)
    return cfg


def status() -> dict:
    done = run(["tailscale", "status", "--json"], timeout=20)
    try:
        data = json.loads(done.stdout)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def tailnet_ips(node: dict) -> tuple[str, str]:
    """(IPv4, IPv6) узла tailnet; пусто — нет."""
    v4 = v6 = ""
    for item in node.get("TailscaleIPs") or []:
        try:
            address = ipaddress.ip_address(item)
        except ValueError:
            continue
        if address.version == 4 and not v4:
            v4 = item
        elif address.version == 6 and not v6:
            v6 = item
    return v4, v6


def trace(mark: int = 0, timeout: float = 6.0) -> str | None:
    """С какого адреса запрос дошёл до Cloudflare (/cdn-cgi/trace); None — не дошёл."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data = b""
    try:
        if mark:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, mark)
        sock.settimeout(timeout)
        sock.connect((TRACE_IP, 443))
        tls = ssl.create_default_context().wrap_socket(sock, server_hostname=TRACE_NAME)
        tls.sendall(f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {TRACE_NAME}\r\n"
                    "Connection: close\r\n\r\n".encode())
        while len(data) < 65536:
            chunk = tls.recv(4096)
            if not chunk:
                break
            data += chunk
    except (OSError, ssl.SSLError):
        return None
    finally:
        sock.close()
    match = re.search(rb"^ip=(\S+)", data, flags=re.MULTILINE)
    return match.group(1).decode() if match else None


def where(address: str | None, direct: str | None, vpn: str | None) -> str:
    if address is None:
        return "нет связи"
    if address == direct:
        return "напрямую"
    if address == vpn:
        return "через VPN"
    return "другой адрес"


def connect(mark: int = 0, timeout: float = 4.0) -> tuple[str, float]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    started = time.monotonic()
    try:
        if mark:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, mark)
        sock.settimeout(timeout)
        sock.connect((TRACE_IP, 443))
        return "соединилось", time.monotonic() - started
    except ConnectionRefusedError:
        return "отбито (сброс)", time.monotonic() - started
    except TimeoutError:
        return "таймаут", time.monotonic() - started
    except OSError as exc:
        return f"отбито ({errno.errorcode.get(exc.errno or 0, exc.errno)})", (
            time.monotonic() - started)
    finally:
        sock.close()


def magic_dns(name: str, timeout: float = 4.0) -> str:
    """Запрос A к MagicDNS напрямую, UDP: чем ответил."""
    if not name:
        return "имя шлюза в tailnet неизвестно"
    query = os.urandom(2) + struct.pack(">HHHHH", 0x0100, 1, 0, 0, 0) + b"".join(
        bytes([len(part)]) + part.encode("ascii") for part in name.split(".")) + struct.pack(
        ">BHH", 0, 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.sendto(query, (MAGIC_DNS, 53))
            reply = sock.recv(4096)
        except OSError:
            return "нет ответа"
    found = [socket.inet_ntoa(reply[i + 10:i + 14]) for i in range(12, len(reply) - 13)
             if reply[i:i + 4] == b"\x00\x01\x00\x01" and reply[i + 8:i + 10] == b"\x00\x04"]
    if any(ipaddress.ip_address(item) in CGNAT for item in found):
        return "адрес tailnet"
    return "ответ без адреса tailnet (так отвечает Xray)" if reply else "пустой ответ"


def resolved(name: str) -> str:
    if not name:
        return "имя шлюза в tailnet неизвестно"
    done = run(["resolvectl", "query", name], timeout=15)
    found = re.findall(r"\b100\.\d+\.\d+\.\d+\b", done.stdout)
    if done.returncode == 0 and any(ipaddress.ip_address(a) in CGNAT for a in found):
        return "разрешилось в адрес tailnet"
    return "не разрешилось"


def netcheck(direct: str | None, vpn: str | None) -> list[str]:
    done = run(["tailscale", "netcheck"], timeout=60)
    text = done.stdout + done.stderr
    udp = re.search(r"\*\s*UDP:\s*(\S+)", text)
    derp = re.search(r"\*\s*Nearest DERP:\s*(.+)", text)
    ipv4 = re.search(r"\*\s*IPv4:\s*yes,\s*([\d.]+):\d+", text)
    return [
        f"netcheck: UDP {'есть' if udp and udp.group(1) == 'true' else 'нет'}; "
        f"ближайший DERP: {derp.group(1).strip() if derp else 'нет'}",
        "netcheck: внешний адрес Tailscale — "
        + (where(ipv4.group(1), direct, vpn) if ipv4 else "нет"),
    ]


def ping_peer(state: dict) -> list[str]:
    peers = [node for node in (state.get("Peer") or {}).values()
             if isinstance(node, dict) and node.get("Online") and tailnet_ips(node)[0]]
    if not peers:
        return ["устройств tailnet в сети нет — ping не проверялся"]
    v4, v6 = tailnet_ips(peers[0])
    done = run(["tailscale", "ping", "-c", "3", "--timeout", "5s", v4], timeout=40)
    pongs = re.findall(r"^pong from .* via (\S+)", done.stdout, flags=re.MULTILINE)
    how = ", ".join(sorted({"через " + p if p.startswith("DERP") else "напрямую (P2P)"
                            for p in pongs})) or "—"
    lines = [f"устройств tailnet в сети: {len(peers)}",
             f"tailscale ping: ответов {len(pongs)}; {how}"]
    if v6:
        six = run(["ping", "-6", "-c", "3", "-W", "2", v6], timeout=20)
        got = len(re.findall(r"bytes from", six.stdout))
        refused = "prohibited" in six.stdout.lower() or "unreachable" in six.stdout.lower()
        lines.append(f"IPv6 в tailnet (ping -6): ответов {got} из 3; отбой фаерволом: "
                     + ("да" if refused else "нет"))
    return lines


def cmd_pre() -> int:
    has_t1 = (Path(LIB) / "xgw" / "tailscale.py").exists()
    cfg = load_cfg(CONFIG)
    route = getattr(getattr(cfg, "tailscale", None), "route", "в этом коде нет")
    v4, v6 = table("ip", "xgw"), table("ip6", "xgw6")
    state = status()
    active = run(["systemctl", "is-active", "tailscaled"]).stdout.strip() or "нет"
    print(f"Т1 в установленном коде: {'есть' if has_t1 else 'НЕТ'}")
    print(f"tailscaled: {active}; BackendState: {state.get('BackendState') or 'неизвестно'}")
    print(f"tailscale.route: {route}")
    print(f"режим правил: {mode_of(v4)}")
    print(f"исключения Tailscale в ip xgw: {ts_rules(v4)}")
    print(f"исключения Tailscale в ip6 xgw6: {ts_rules(v6)}")
    return 0 if has_t1 else 3


def cmd_net() -> int:
    cfg = load_cfg(CONFIG)
    direct, vpn = trace(cfg.capture.mark_bypass), trace()
    print("обычный сокет: " + where(vpn, direct, None if vpn == direct else vpn))
    print(f"сокет с меткой tailscaled (0x80000): {where(trace(TS_MARK), direct, vpn)}")
    state = status()
    name = str((state.get("Self") or {}).get("DNSName") or "").rstrip(".")
    print(f"MagicDNS 100.100.100.100, имя шлюза: {magic_dns(name)}")
    print(f"resolved, имя шлюза: {resolved(name)}")
    for line in netcheck(direct, vpn) + ping_peer(state):
        print(line)
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
        text = re.sub(r"(https?://)([^/\s\"']+)(/[^\s\"']*)?",
                      lambda m: m.group(1) + m.group(2) + ("/…" if m.group(3) else ""), text)
        text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "почта@…", text)
        text = re.sub(r"[\w.+-]+@(?=\s|$)", "пользователь@", text, flags=re.MULTILINE)
        text = re.sub(r"\b([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "MAC-скрыт", text)
        for value in sorted(self.names, key=len, reverse=True):
            text = re.sub(re.escape(value), self.names[value], text, flags=re.IGNORECASE)
        text = re.sub(r"(?<![\w:.])(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}(?:/\d{1,3})?"
                      r"(?![\w:])", self._ip, text)
        return re.sub(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?(?![\w.])", self._ip, text)


def cmd_mask() -> int:
    sys.stdout.write(Masker(status()).mask(sys.stdin.read()))
    return 0


def test_config(directory: Path) -> Path:
    """Копия config.toml (и panel.json) в DIR с другим capture.tproxy_port."""
    text = CONFIG.read_text(encoding="utf-8")
    port = load_cfg(CONFIG).capture.tproxy_port + 54
    lines = text.splitlines()
    section, done = "", False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and not stripped.startswith("[["):
            section = stripped.strip("[] ")
        elif section == "capture" and re.match(r"tproxy_port\s*=", stripped):
            lines[index], done = f"tproxy_port = {port}", True
    if not done:
        for index, line in enumerate(lines):
            if line.strip() == "[capture]":
                lines.insert(index + 1, f"tproxy_port = {port}")
                done = True
                break
    if not done:
        lines += ["", "[capture]", f"tproxy_port = {port}"]
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    target = directory / "config.toml"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    panel = managed.path_for(CONFIG)
    if panel.exists():
        shutil.copy2(panel, managed.path_for(target))
        os.chmod(managed.path_for(target), 0o600)
    if load_cfg(target).capture.tproxy_port != port:
        raise SystemExit("копия конфига не та: tproxy_port не изменился")
    return target


def cmd_window(directory: Path) -> int:
    """Окно blocked с обязательным возвратом. Пишет DIR/window.txt."""
    cfg = load_cfg(CONFIG)
    if not cfg.capture.hold_blocks:
        print(f"СТОП: capture.hold = {cfg.capture.hold!r}, fail_mode = {cfg.capture.fail_mode} —"
              " blocked здесь не включается")
        return 2
    target = test_config(directory)
    out: list[str] = []

    def note(text: str) -> None:
        out.append(text)
        print(text, flush=True)

    started = time.monotonic()
    note(f"окно blocked: {time.strftime('%T')}")
    code = 0
    try:
        run(["systemctl", "stop", DAEMON], timeout=60)
        up = run([*XGW, "net", "up", "--config", str(target)])
        note(f"net up по копии: код {up.returncode}")
        v4 = table("ip", "xgw")
        note(f"режим правил: {mode_of(v4)}")
        note(f"исключения Tailscale в ip xgw: {ts_rules(v4)}")
        note(f"исключения Tailscale в ip6 xgw6: {ts_rules(table('ip6', 'xgw6'))}")
        plain, marked = connect(), connect(TS_MARK)
        note(f"a обычный сокет: {plain[0]} за {plain[1]:.2f} с")
        note(f"b сокет с меткой tailscaled: {marked[0]} за {marked[1]:.2f} с")
        state = status()
        name = str((state.get("Self") or {}).get("DNSName") or "").rstrip(".")
        dns = magic_dns(name)
        note(f"c MagicDNS, имя шлюза: {dns}")
        for line in netcheck(None, None)[:1] + ping_peer(state):
            note("d " + line)
        verdicts = [
            ("a обычный сокет отбит сразу", plain[0].startswith("отбито") and plain[1] < 2.0),
            ("b tailscaled соединяется", marked[0] == "соединилось"),
            ("c MagicDNS отвечает", dns == "адрес tailnet"),
            ("режим blocked", mode_of(v4) == "blocked"),
        ]
        failed = [label for label, ok in verdicts if not ok]
        note("ИТОГ окна: " + ("ДЕФЕКТ: " + "; ".join(failed) if failed else "ПРОЙДЕН"))
        code = 1 if failed else 0
        left = WINDOW - (time.monotonic() - started)
        note(f"ждём {max(0, int(left))} с")
        if left > 0:
            time.sleep(left)
    finally:
        if not restore(note):
            code = 1
        note(f"конец окна: {time.strftime('%T')}")
        (directory / "window.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    return code


def restore(note) -> bool:
    """Возврат: правила по настоящему конфигу и демон; каждый шаг — сам по себе. Правила так и
    остались blocked — `xgw disable`: интернет пойдёт напрямую, но связь с машиной будет."""

    def step(label: str, argv: list[str]) -> None:
        try:
            done = run(argv, timeout=STEP_TIMEOUT)
            note(f"{label} — код {done.returncode}")
        except (OSError, subprocess.SubprocessError) as exc:
            note(f"{label} — сбой: {type(exc).__name__}")

    step("возврат: net up по настоящему конфигу", [*XGW, "net", "up", "--config", str(CONFIG)])
    step("возврат: запуск демона", ["systemctl", "start", DAEMON])
    mode = mode_of(table("ip", "xgw"))
    if mode == "blocked":
        step("АВАРИЙНО: xgw disable — интернет напрямую",
             [*XGW, "disable", "--config", str(CONFIG)])
        mode = mode_of(table("ip", "xgw"))
    note(f"режим правил после возврата: {mode}")
    return mode != "blocked"


def cmd_rescue(log: Path) -> int:
    out: list[str] = []

    def note(text: str) -> None:
        out.append(text)
        print(text, flush=True)

    mode = mode_of(table("ip", "xgw"))
    active = run(["systemctl", "is-active", DAEMON]).stdout.strip()
    note(f"страховка {time.strftime('%T')}: режим правил {mode}, демон {active}")
    if mode != "blocked" and active == "active":
        note("всё в порядке — страховка ничего не делала")
        ok = True
    else:
        ok = restore(note)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(out) + "\n", encoding="utf-8")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("запускать через sudo")
        return 2
    if argv == ["pre"]:
        return cmd_pre()
    if argv == ["net"]:
        return cmd_net()
    if argv == ["mask"]:
        return cmd_mask()
    if len(argv) == 2 and argv[0] == "window":
        return cmd_window(Path(argv[1]))
    if len(argv) == 2 and argv[0] == "rescue":
        return cmd_rescue(Path(argv[1]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
T1_EOF
sha256sum ~/xgw-t1-test/t1check.py
```

Ожидается: `2a87fcbc78b4751fdcb511991b0ec91019a7e4fc21a55ede2003c5adbd357e95` в начале строки.
Если хеш другой: файл скопирован не целиком — повторить шаг 1.2 один раз; если снова другой —
**стоп**, сообщить заказчику.

Шаг 1.3. Снимок до обновления:

```bash
sudo xgw --version; sudo xgw status > before/status.txt; sudo xgw diag > before/diag.txt; tail -1 before/diag.txt; grep -E '^Состояние' before/status.txt; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled | tee before/services.txt; sudo python3 t1check.py pre | tee before/pre.txt; sudo python3 t1check.py net | tee before/net.txt
```

Ожидается:

- `xgw 0.1.16`, итог diag с «FAIL — 0», состояние `HEALTHY`, службы `active` (у
  `xgw-singbox` допустимо `inactive`, если sing-box выключен в настройках — записать);
- «Т1 в установленном коде: НЕТ» (так и должно быть до обновления);
- «tailscaled: active; BackendState: Running»;
- «режим правил: on»; «исключения Tailscale в ip xgw: нет (набора нет)»;
- «обычный сокет: через VPN»;
- «сокет с меткой tailscaled (0x80000): через VPN» — это К1 на прежнем коде;
- «MagicDNS 100.100.100.100, имя шлюза: ответ без адреса tailnet (так отвечает Xray)» или
  «нет ответа» — это К2; «resolved, имя шлюза: не разрешилось»;
- две строки «netcheck: …» и строки про устройства tailnet — записать как есть.

Если не так:

- FAIL не 0 или состояние не `HEALTHY`: записать в отчёт как есть и **спросить заказчика**,
  продолжать ли.
- `tailscaled` не `active` или BackendState не `Running`: **стоп**, сообщить заказчику
  (Tailscale должен быть включён и подключён; входит в tailnet заказчик сам).
- «обычный сокет» не «через VPN»: **стоп**, сообщить заказчику (VPN сейчас не работает —
  сравнивать не с чем).
- Остальные строки другие — записать в отчёт (это снимок «до», не дефект), продолжать.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout tailscale-t1 && git pull --ff-only && git log -1 --format='%h %s' && test -f src/xgw/tailscale.py && echo "Т1 в коде: есть"; grep __version__ src/xgw/__init__.py; cd ~/xgw-t1-test
```

Ожидается: «Т1 в коде: есть» и `__version__ = "0.1.16"`. Записать хеш.
Если ветки `tailscale-t1` нет или «Т1 в коде: есть» не напечатано: **стоп**, сообщить заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/zcod/xgw && date '+%F %T' | tee ~/xgw-t1-test/install-time.txt && sudo sh packaging/install.sh --yes 2>&1 | tee ~/xgw-t1-test/after/install.txt | tail -25; echo "код ${PIPESTATUS[0]}"; cd ~/xgw-t1-test
```

Ожидается: «код 0» и строка «демон xgw запущен».
Если код не 0: **стоп**, сохранить вывод, выполнить §6 (возврат на `f2-events`), сообщить
заказчику.

Шаг 2.3. Установленный код и правила:

```bash
sleep 20; sudo xgw --version; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; sudo python3 t1check.py pre | tee after/pre.txt
```

Ожидается:

- `xgw 0.1.16`; службы — как в шаге 1.3;
- «Т1 в установленном коде: есть»;
- «tailscaled: active; BackendState: Running»; «tailscale.route: direct»;
- «режим правил: on»;
- «исключения Tailscale в ip xgw: есть (метка в наборе)»;
- «исключения Tailscale в ip6 xgw6: есть (метка в наборе)».

Если не так:

- «Т1 в установленном коде: НЕТ» — **стоп**: установка не обновила код; сообщить заказчику.
- `xgw` не `active` — подожди 30 с, проверь ещё раз; снова не `active` — §6.
- «tailscale.route» не `direct` — заказчик сам так настроил: записать, продолжать (ожидания
  шага 3 тогда другие — спросить заказчика, продолжать ли).
- «исключения …: нет» — **дефект «исключения Tailscale не загружены»**: записать вывод
  целиком и выполнить `sudo xgw diag | grep -E 'Tailscale|Перехват'` — строки тоже в отчёт;
  продолжать.

## 3. Tailscale после обновления

Шаг 3.1. Куда идут соединения, MagicDNS, netcheck и связь с устройством в tailnet. Если
заказчик согласился на пункт 2 — **попроси** его включить Tailscale на втором устройстве и
дождись «включил».

```bash
sudo python3 t1check.py net | tee after/net.txt
```

Ожидается:

- «обычный сокет: через VPN» — трафик машины по-прежнему идёт через VPN;
- «сокет с меткой tailscaled (0x80000): напрямую» — К1 исправлена;
- «MagicDNS 100.100.100.100, имя шлюза: адрес tailnet» — К2 исправлена;
- «resolved, имя шлюза: разрешилось в адрес tailnet»;
- «netcheck: UDP есть; ближайший DERP: <город>»;
- «netcheck: внешний адрес Tailscale — напрямую»;
- «устройств tailnet в сети: N» (N — 1 или больше) и «tailscale ping: ответов 3; через
  DERP(…)» или «… напрямую (P2P)» — подходит любое;
- если у устройства есть IPv6 tailnet — «IPv6 в tailnet (ping -6): ответов N из 3; отбой
  фаерволом: нет» (N может быть 0 — устройство может не отвечать на ping, это не дефект;
  важно «отбой фаерволом: нет» — К4 исправлена).

Если не так:

- «сокет с меткой tailscaled» — «через VPN»: **дефект К1** («соединения Tailscale всё ещё
  уходят в Xray»); «нет связи» — **дефект «Tailscale отрезан»**. Вывод целиком в отчёт.
- MagicDNS — не «адрес tailnet»: **дефект К2**.
- «netcheck: внешний адрес Tailscale — через VPN», а «сокет с меткой tailscaled» —
  «напрямую»: записать как наблюдение (сама команда `tailscale netcheck` не помечает
  соединения), не дефект. «другой адрес» — тоже наблюдение.
- «netcheck: UDP нет» — записать как наблюдение (провайдер или роутер режет UDP).
- «tailscale ping: ответов 0» при «устройств tailnet в сети» больше 0: подожди минуту и
  выполни шаг ещё раз (`sudo python3 t1check.py net | tee after/net-2.txt`); снова 0 —
  **дефект «нет связи внутри tailnet»**, вывод целиком в отчёт.
- «отбой фаерволом: да» — **дефект К4**.
- «устройств tailnet в сети нет» при согласии на пункт 2 — спроси заказчика, включён ли
  Tailscale на устройстве, и повтори шаг один раз; снова нет — записать, продолжать.

Шаг 3.2. Список устройств tailnet (маскированный):

```bash
sudo tailscale status 2>&1 | sudo python3 t1check.py mask | tee after/ts-status.txt; sudo tailscale status --json | python3 -c "import json,sys; d=json.load(sys.stdin); print('Health:', '; '.join(d.get('Health') or []) or 'пусто')" | sudo python3 t1check.py mask | tee after/ts-health.txt
```

Ожидается: первая строка — сам шлюз (`100.x.y.N устройство-N …`), у второго устройства
(пункт 2) нет слова `offline`; «Health: пусто». Имён и адресов в выводе нет — только метки.
Если в выводе видно настоящее имя или адрес — **не** записывать его в отчёт; записать в
отчёт «маскировка пропустила …» (без самого значения).
Если «Health» не пустой — записать строку в отчёт (наблюдение).

Шаг 3.3. `xgw diag`:

```bash
sudo xgw diag > after/diag.txt; tail -1 after/diag.txt; grep -E 'Tailscale|Перехват|IPv6' after/diag.txt | sudo python3 t1check.py mask
```

Ожидается: «FAIL — 0» и строки:

- «OK    Tailscale: tailscaled работает, вход выполнен»;
- «OK    Tailscale: правила: tailnet, MagicDNS и tailscale0 — мимо перехвата и блокировок; сам
  Tailscale ходит напрямую, мимо Xray»;
- «OK    Tailscale: связь: UDP есть; ближайший DERP: <город>, N мс»;
- «OK    Tailscale: CGNAT: адреса провайдера вне 100.64.0.0/10»;
- «OK    Tailscale: DNS: через tailscale0 — только имена tailnet»;
- «OK    Перехват: включён, правила загружены» и строка IPv6 — как в `before/diag.txt`.

Если не так:

- «FAIL  Tailscale: правила …» — **дефект «исключения не загружены»**: записать строки.
- «WARN  Tailscale: CGNAT …» или «WARN  Tailscale: DNS …» — записать строку целиком (это
  настройка Tailscale, которую заказчик решает сам; ничего не менять).
- «WARN  Tailscale: связь: нет UDP …» — наблюдение, записать.

## 4. Окно blocked (одна минута)

Только если заказчик согласился на пункт 3. Иначе — сразу шаг 5.

Шаг 4.1. **Скажи заказчику**: «Сейчас на минуту пропадёт интернет у всего дома. Через две
минуты всё вернётся само. Скажите, когда будете готовы.» Дождись ответа «готов».

Шаг 4.2. Окно. **Одна команда; не прерывай её, дождись вывода** (около полутора минут). Во
время окна у тебя не будет связи — это нормально:

```bash
sudo systemctl stop xgw-t1-rescue.timer xgw-t1-rescue.service 2>/dev/null; sudo systemctl reset-failed xgw-t1-rescue.timer xgw-t1-rescue.service 2>/dev/null; sudo systemd-run --quiet --collect --unit=xgw-t1-rescue --on-active=4min --timer-property=AccuracySec=1s /usr/bin/python3 "$HOME/xgw-t1-test/t1check.py" rescue "$HOME/xgw-t1-test/after/rescue.txt" && echo "страховка поставлена, сработает в $(date -d '+4 min' +%T)" && sudo systemd-run --wait --collect --pipe --quiet --unit=xgw-t1-window /usr/bin/python3 "$HOME/xgw-t1-test/t1check.py" window "$HOME/xgw-t1-test/blk" | tee after/window.txt; echo "код ${PIPESTATUS[0]}"
```

Ожидается, по порядку:

- «страховка поставлена, сработает в ЧЧ:ММ:СС» — **первой строкой**; без неё окно не
  запускается (так и задумано): записать ошибку и перейти к шагу 5;
- «окно blocked: ЧЧ:ММ:СС», «net up по копии: код 0», «режим правил: blocked»;
- «исключения Tailscale в ip xgw: есть (набора нет)» (в blocked набор не нужен);
- «исключения Tailscale в ip6 xgw6: есть (метка в наборе)»;
- «a обычный сокет: отбито (сброс) за 0.0x с» — мимо VPN машина не выходит;
- «b сокет с меткой tailscaled: соединилось …» — К3 исправлена;
- «c MagicDNS, имя шлюза: адрес tailnet»;
- «d netcheck: UDP есть; ближайший DERP: <город>», «d устройств tailnet в сети: N»,
  «d tailscale ping: ответов 3; …» (при согласии на пункт 2) и строка IPv6, если есть;
- «ИТОГ окна: ПРОЙДЕН»; «ждём N с»;
- «возврат: net up по настоящему конфигу — код 0», «возврат: запуск демона — код 0»,
  «режим правил после возврата: on», «конец окна: ЧЧ:ММ:СС»;
- «код 0».

Если не так:

- «СТОП: capture.hold …» — окно не проводилось (так настроено); записать, перейти к шагу 5.
- «a обычный сокет: соединилось» — **дефект «в blocked машина выходит мимо VPN»**.
- «b …» не «соединилось» — **дефект К3** («в blocked Tailscale отрезан»).
- «c …» не «адрес tailnet» или «d tailscale ping: ответов 0» при устройстве в сети —
  **дефект К3**: записать вывод целиком.
- Строка «АВАРИЙНО: xgw disable — интернет напрямую» — возврат не удался, сработал аварийный
  путь: интернет есть, но идёт мимо VPN. **Дефект «окно не вернуло перехват»**: записать
  вывод целиком, сообщить заказчику, §6.
- «режим правил после возврата» не `on` или любой «возврат: … код» не 0 — сразу §6.
- Твоя команда оборвалась сама (у тебя кончилось время на команду) — окно от этого **не**
  прерывается: оно идёт в systemd. Ничего не запускай повторно; подожди 3 минуты от первой
  строки и переходи к шагу 4.3 — полный вывод окна сохранится там из файла.
- Вывод оборвался, команды нет дольше 4 минут — ничего не делать до срабатывания страховки
  (время — в первой строке), затем §6.

Шаг 4.3. После окна — проверка возврата и уборка копии конфига (в ней адреса подписок):

```bash
sleep 20; systemctl is-active xgw xgw-xray; sudo python3 t1check.py net | tee after/net-after.txt; sudo xgw status | grep -E '^Перехват|^Состояние'; sudo cat ~/xgw-t1-test/blk/window.txt > after/window-file.txt; sudo rm -rf ~/xgw-t1-test/blk && echo "копия конфига удалена"
```

Ожидается: два `active`; строки `t1check.py net` — как в шаге 3.1; «Перехват: включён …»;
«копия конфига удалена». Файл `after/window-file.txt` — полный вывод окна (в отчёт берётся
он, если `after/window.txt` оборвался).
Если не так: «обычный сокет» не «через VPN» или демон не `active` — сразу §6.

**Спроси заказчика**: «Сейчас интернет дома есть?» Ожидается «да»; если «нет» — сразу §6.

## 5. Итоговое состояние

Шаг 5.1. Подожди 2 минуты после последнего действия, затем:

```bash
timeout 330 bash -c 'until sudo test -s "$HOME/xgw-t1-test/after/rescue.txt"; do sleep 10; done'; sudo cat after/rescue.txt; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; sudo xgw status > after/status.txt; sudo xgw diag > after/diag-end.txt; tail -1 after/diag-end.txt; grep -E '^(Состояние|Сейчас)' after/status.txt; sudo python3 t1check.py pre | grep -E 'режим правил|исключения'; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c 'Traceback'
```

Ожидается:

- строки страховки «страховка ЧЧ:ММ:СС: режим правил on, демон active» и «всё в порядке —
  страховка ничего не делала» (если шаг 4 пропущен — команда ждёт до 5,5 минут и `cat`
  скажет, что файла нет, так и должно быть);
- службы — как в шаге 1.3; «FAIL — 0»; `HEALTHY`; «Сейчас: перехват работает»;
- «режим правил: on», обе строки «исключения … есть (метка в наборе)»;
- последнее число — `0`.

Если не так:

- Страховка что-то делала («возврат: …» в её выводе) — **дефект «окно не вернуло правила
  само»**: записать её вывод целиком.
- FAIL не 0 или число `Traceback` больше 0 — сохранить подробности и записать дефект с
  этими файлами:

  ```bash
  grep FAIL after/diag-end.txt | sudo python3 t1check.py mask > after/fail.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -B2 -A12 Traceback | sudo python3 t1check.py mask > after/traceback.txt; wc -l after/fail.txt after/traceback.txt
  ```

## 6. Если что-то пошло не так

- Интернет не вернулся после окна или «режим правил после возврата» не `on`:

  ```bash
  sudo xgw net up; sudo systemctl start xgw; sleep 20; sudo python3 ~/xgw-t1-test/t1check.py net
  ```

  Если и после этого «обычный сокет» не «через VPN» и у заказчика нет интернета —
  `sudo xgw disable` (интернет пойдёт напрямую, мимо VPN), сообщить заказчику.
  `sudo rm -rf ~/xgw-t1-test/blk` — в любом случае.
- Сработал аварийный путь (`xgw disable` — в выводе окна или страховки): интернет идёт мимо
  VPN. Перехват **не** включать самому: сообщить заказчику; `sudo xgw enable` — только с его
  согласия и после того, как записан вывод `sudo xgw status` и
  `sudo journalctl -u xgw -n 80 --no-pager | sudo python3 t1check.py mask > after/xgw-fail.txt`.
- Связи с машиной нет совсем (ни у тебя, ни у заказчика) — это вне твоих сил: заказчик
  выключает и включает питание шлюза; после загрузки шлюз в обычном режиме.
- Возврат на прежний код (`f2-events`) — когда шаг велит выполнить §6 или новый код не
  работает:

  ```bash
  cd ~/zcod/xgw && git checkout f2-events && git pull --ff-only && sudo sh packaging/install.sh --yes 2>&1 | tail -15; echo "код ${PIPESTATUS[0]}"; systemctl is-active xgw xgw-net xgw-dhcp; cd ~/xgw-t1-test
  ```

  Ожидается: «код 0», службы `active`. Не помогло — **стоп**, сообщить заказчику; аварийный
  выход в интернет напрямую заказчик делает сам: `sudo xgw disable`.

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-tailscale-t1-<ГГГГ-ММ-ДД>.md` в репозитории (ветка
`tailscale-t1`). Заполни бланк; выводы — только из файлов `~/xgw-t1-test/before` и `after`,
которые прошли через `t1check.py mask`, или из вывода `t1check.py` (он адресов не печатает):

```markdown
# Отчёт Т1: Tailscale рядом с XGW (ветка tailscale-t1)

Код: <хеш>. Установка: <время>, код <0/…>. Согласие заказчика: пункты <1–3 / какие нет>.

## Итог
<3–4 предложения: идут ли соединения Tailscale мимо Xray; разрешаются ли имена tailnet;
связь с устройством в tailnet; как прошло окно blocked; итоговое состояние>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до обновления | — | <версия, FAIL — …; tailscaled: через VPN / …; MagicDNS: …> |
| 2.2 установка | пройден / нет | <код, «демон xgw запущен»> |
| 2.3 правила | пройден / дефект | <Т1 в коде; route; исключения в ip и ip6> |
| 3.1 К1 соединения Tailscale | пройден / дефект | <сокет с меткой: напрямую; netcheck: …> |
| 3.1 К2 MagicDNS | пройден / дефект | <MagicDNS; resolved> |
| 3.1 связь в tailnet | пройден / дефект / не проверялась | <ping: ответов, путь; IPv6: отбой> |
| 3.2 tailscale status | пройден / наблюдение | <устройство в сети; Health> |
| 3.3 xgw diag | пройден / дефект | <строки раздела «Tailscale»; FAIL — …> |
| 4 окно blocked (К3) | пройден / дефект / не проводилось | <a, b, c, d; возврат> |
| 5 итоговое состояние | пройден / нет | <FAIL — …; страховка; Traceback> |

## Шаги 1.3, 3.1 и 4 — выводы
<before/net.txt, after/net.txt и after/window.txt (или window-file.txt) целиком>

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Наблюдения

## Что не проверено и почему
`route = "vpn"` (Tailscale через VPN) на машине не проверялся: заказчик выбрал `direct`
(проверено на стенде). Tailscale SSH и панель по tailnet — фаза Т2.

## Итоговое состояние машины
```

Перед коммитом проверь, что в отчёте нет секретов и адресов:

```bash
grep -nE '(vless|vmess|trojan|ss|hysteria2)://[^*]|[0-9a-f]{8}-[0-9a-f]{4}-|[0-9]{8,10}:[A-Za-z0-9_-]{30,}|token|/sub/|([0-9a-f]{2}:){5}[0-9a-f]{2}|\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]+\.[0-9]+|fd7a:115c|\.ts\.net|@[a-z0-9-]+\.[a-z]' ~/zcod/xgw/docs/TEST-REPORT-REAL-MACHINE-0.1.17-tailscale-t1-*.md
```

Ожидается: пусто или только строки с `100.64.0.0/10` и `100.100.100.100` — они разрешены. Если
нашлось что-то ещё — убрать из отчёта (заменить меткой).

Коммит только отчёта: `cd ~/zcod/xgw && git add docs/TEST-REPORT-REAL-MACHINE-0.1.17-tailscale-t1-*.md &&
git commit -m "Отчёт Т1: Tailscale рядом с XGW" && git push`.
