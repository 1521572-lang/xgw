# Программа T0: почему Tailscale на шлюзе не работает — снимок только для чтения

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома (LAN `enp4s0`), стоит XGW **0.1.16**.
Клон репозитория — `~/zcod/xgw`. **XGW не переустанавливается и не обновляется**: из ветки
`tailscale-t0` нужна только эта программа.

Зачем (`TAILSCALE_MINIAPP_PLAN.md`, §1 и фаза Т0). Tailscale стоит на шлюзе, но нормально не
заработал. По коду XGW есть четыре причины-гипотезы:

| # | Гипотеза | Что ломается |
|---|---|---|
| К1 | цепочка `output` таблицы `ip xgw` ставит сокетам `tailscaled` метку перехвата и затирает их метку `0x80000` | WireGuard, DERP и управление Tailscale уходят в Xray; соединение то есть, то нет |
| К2 | DNS к `100.100.100.100:53` (MagicDNS) перехватывается в Xray | имена `*.ts.net` на шлюзе не разрешаются |
| К3 | в режиме blocked (Ф1) цепочка `block_output` отбивает трафик `tailscaled` и `tailscale0` | удалённый доступ пропадает именно в blocked |
| К4 | `v6_guard` таблицы `ip6 xgw6` отбивает IPv6 tailnet (`fd7a:…`) | Tailscale по IPv6 не работает |

Дополнительно скрипт смотрит К5 (адрес WAN провайдера из `100.64.0.0/10` — его отбрасывает сам
Tailscale) и К6 (Tailscale стал DNS по умолчанию — DNS шлюза мимо VPN).

Скрипт этой программы **ничего не меняет**: только читает состояние (`tailscale status`,
`ip rule`, `nft list ruleset`, `resolvectl status`, `xgw diag`, журнал `tailscaled` за сутки) и
запускает `tailscale netcheck` (он лишь меряет связь с серверами Tailscale). Сырые выводы
остаются на машине в `~/xgw-ts-t0/raw` (каталог 0700); в отчёт идут только маскированные копии
из `~/xgw-ts-t0/masked`: адреса tailnet (`100.x.y.z`, `fd7a:…`), имена устройств,
пользователей и самого tailnet, почта, внешние адреса и домены в них заменены метками.

## 0. Запрещено

- `tailscale up`, `down`, `set`, `login`, `logout`, `switch`, `serve`, `funnel`, `cert`, `ssh`,
  `file`, `lock`, `update`, любые `tailscale debug` (скрипт сам вызывает только
  `tailscale debug prefs` — она только печатает настройки).
- Запуск, остановка, перезапуск и выключение служб: `tailscaled`, `xgw`, `xgw-xray`,
  `xgw-singbox`, `xgw-net`, `xgw-dhcp`, `systemd-resolved`, NetworkManager.
- Любые правки правил и сети: `nft` (кроме `nft list` из скрипта), `ip` (кроме `ip … show` и
  `ip rule` без аргументов из скрипта), `iptables`, `sysctl -w`, `resolvectl` с аргументами,
  кроме `status` и `query`.
- `xgw enable`, `xgw disable`, `xgw net …`, `xgw apply`, `xgw install`, `xgw uninstall`,
  `install.sh`, `reboot`.
- Правка любых файлов в `/etc`, в том числе `/etc/xgw` и `/etc/default/tailscaled`; вход в
  консоль tailnet (login.tailscale.com) и изменения там.
- Писать в отчёт что-либо из `~/xgw-ts-t0/raw`. Класть в Git что-либо, кроме отчёта (§5).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно): «Сниму состояние Tailscale и XGW на шлюзе, чтобы
понять, почему Tailscale не работает. Ничего не меняю и не перезапускаю, интернет и Tailscale
не трогаю; в отчёт пойдут только замаскированные данные — без адресов, имён устройств и
почты. Можно?» Дождись ответа. Против — **стоп**.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p ~/xgw-ts-t0 && chmod 700 ~/xgw-ts-t0 && cd ~/xgw-ts-t0 && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды — из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без пароля
на время снимка — вводить пароль некому.

Шаг 1.2. Ветка с программой (XGW при этом не меняется — ничего не устанавливай):

```bash
cd ~/zcod/xgw && git fetch && git checkout tailscale-t0 && git pull --ff-only && git log -1 --format='%h %s'; ls docs/TEST-PLAN-REAL-MACHINE-0.1.16-tailscale-t0.md; cd ~/xgw-ts-t0; sudo xgw --version
```

Ожидается: хеш и заголовок коммита, путь к этой программе, `xgw 0.1.16`. Записать хеш.
Если ветки нет: **стоп**, сообщить заказчику.

## 2. Скрипты

Шаг 2.1. Скрипт снимка (копируй блок целиком):

```bash
cat > t0.sh <<'T0_EOF'
#!/bin/bash
# t0.sh — снимок «почему Tailscale на шлюзе не работает». ТОЛЬКО ЧТЕНИЕ: ничего не меняет.
# Сырые выводы — в raw/ (каталог 0700, в отчёт и в Git не попадают), маскированные — в
# masked/, итог по гипотезам — masked/summary.txt (его делает mask.py).
cd "$(dirname "$0")" || exit 1
umask 077
rm -rf raw masked
mkdir -p raw masked
if [ "$(id -u)" -eq 0 ]; then S=""; else S="sudo -n"; fi
run() {  # run ИМЯ СЕКУНД КОМАНДА… — вывод и код возврата в raw/ИМЯ.txt
  local name=$1 limit=$2; shift 2
  { echo "\$ $*"; timeout "$limit" "$@" 2>&1; echo "[код $?]"; } > "raw/$name.txt"
}
echo "снимок: $(date '+%F %T')" > raw/when.txt
hostname > raw/hostname.txt 2>&1
run os 10 cat /etc/os-release

if command -v tailscale >/dev/null 2>&1; then
  echo "есть" > raw/ts-installed.txt
  run ts-version 15 tailscale version
  run ts-active 10 systemctl is-active tailscaled
  run ts-status-json 20 $S tailscale status --json
  run ts-status 20 $S tailscale status
  run ts-prefs 20 $S tailscale debug prefs
  run ts-netcheck 60 $S tailscale netcheck
  run ts-journal 30 $S journalctl -u tailscaled --since "24 hours ago" --no-pager -o short-iso
  run ts-resolve 15 bash -c 'n=$(tailscale status --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)[\"Self\"][\"DNSName\"].rstrip(\".\"))" 2>/dev/null); [ -n "$n" ] && resolvectl query "$n" || echo "имя устройства в tailnet не известно"'
else
  echo "Tailscale не установлен" > raw/ts-installed.txt
fi
run ip-rule 10 ip rule
run ip-rule6 10 ip -6 rule
run route52 10 ip route show table 52
run route52v6 10 ip -6 route show table 52
run route-main 10 ip route show
run addr 10 ip -o addr
run nft 20 $S nft list ruleset
run resolved-ts0 10 resolvectl status tailscale0
run resolved 10 resolvectl status
run udp 10 $S ss -ulpn
if command -v xgw >/dev/null 2>&1; then
  run xgw-version 10 $S xgw --version
  run xgw-status 60 $S xgw status
  run xgw-diag 120 $S xgw diag
else
  echo "xgw не установлен" > raw/xgw-status.txt
fi
python3 "$(dirname "$0")/mask.py" raw masked
echo "[код $?]"
T0_EOF
echo "t0.sh: $(wc -l < t0.sh) строк"
```

Ожидается: «t0.sh: 49 строк».

Шаг 2.2. Маскировка и итог по гипотезам (копируй блок целиком):

```bash
cat > mask.py <<'MASK_EOF'
"""mask.py RAW OUT — маскирует сырые выводы t0.sh и подводит итог по гипотезам К1–К6.

Прячет: адреса tailnet (100.64.0.0/10 и fd7a:115c:a1e0::/48), внешние адреса IPv4 и IPv6,
имена устройств, пользователей и самого tailnet, почту, MAC, ключи узлов, пути в ссылках и
домены (кроме tailscale.com). Частные адреса LAN и 100.100.100.100 (DNS tailnet) остаются.
"""

import ipaddress
import json
import re
import sys
from pathlib import Path

RAW, OUT = Path(sys.argv[1]), Path(sys.argv[2])
TAILNET4 = ipaddress.ip_network("100.64.0.0/10")
TAILNET6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
MAGIC_DNS = ipaddress.ip_address("100.100.100.100")
KEEP_DOMAINS = ("tailscale.com", "tailscale.io", "localhost")
# Последние части имён, которые не домены, а файлы, службы и модули.
NOT_DOMAINS = {
    "service", "target", "socket", "timer", "mount", "slice", "scope", "path", "device",
    "json", "toml", "conf", "txt", "md", "py", "log", "sh", "db", "pid", "leases", "nft",
    "d", "so", "deb", "go", "lan", "local", "internal", "arpa", "invalid", "example",
}
KEEP_FIRST = ("xgw.", "systemd.", "org.freedesktop.", "tailscaled.", "net.ipv")


def read(name: str) -> str:
    path = RAW / f"{name}.txt"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


class Masker:
    def __init__(self) -> None:
        self.names: dict[str, str] = {}
        self.maps: dict[str, dict[str, str]] = {}

    def label(self, kind: str, value: str, fmt: str) -> str:
        table = self.maps.setdefault(kind, {})
        if value not in table:
            table[value] = fmt.format(len(table) + 1)
        return table[value]

    def add_name(self, value: str, fmt: str) -> None:
        value = (value or "").strip().rstrip(".")
        if len(value) >= 3 and value.lower() not in ("localhost", "ubuntu"):
            self.names.setdefault(value.lower(), self.label("name:" + fmt, value.lower(), fmt))

    def _ip(self, match: re.Match) -> str:
        text = match.group(0)
        bare, _, prefix = text.partition("/")
        try:
            address = ipaddress.ip_address(bare)
        except ValueError:
            return text
        tail = f"/{prefix}" if prefix else ""
        if address == MAGIC_DNS or address in (TAILNET4.network_address, TAILNET6.network_address):
            return text  # DNS tailnet и сами сети tailnet (100.64.0.0/10) — не чьи-то адреса
        if address.version == 4 and address in TAILNET4:
            return self.label("ts4", bare, "100.x.y.{}") + tail
        if address.version == 6 and address in TAILNET6:
            return self.label("ts6", bare, "fd7a:…:{}") + tail
        if address.is_global and not address.is_multicast:
            kind = "внешний-IP-{}" if address.version == 4 else "внешний-IPv6-{}"
            return self.label("ext", bare, kind) + tail
        return text

    def _domain(self, match: re.Match) -> str:
        text = match.group(0)
        low = text.lower()
        if low.endswith(KEEP_DOMAINS) or low.startswith(KEEP_FIRST):
            return text
        if low.rsplit(".", 1)[-1] in NOT_DOMAINS:
            return text
        return self.label("domain", low, "домен-{}")

    def mask(self, text: str) -> str:
        text = re.sub(r"\btskey-[A-Za-z0-9-]+", "tskey-***", text)
        text = re.sub(r"\b(nodekey|discokey|machinekey|mkey|nlpub):[0-9a-fA-F]+", r"\1:***", text)
        text = re.sub(r"\[[A-Za-z0-9+/_=-]{5}\]", "[ключ]", text)
        text = re.sub(r"(https?://)([^/\s\"']+)(/[^\s\"']*)?",
                      lambda m: m.group(1) + m.group(2) + ("/…" if m.group(3) else ""), text)
        text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "почта@…", text)
        text = re.sub(r"[\w.+-]+@(?=\s|$)", "пользователь@", text, flags=re.MULTILINE)
        text = re.sub(r"\b([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "MAC-скрыт", text)
        for value in sorted(self.names, key=len, reverse=True):
            text = re.sub(re.escape(value), self.names[value], text, flags=re.IGNORECASE)
        text = re.sub(r"(?<![\w:.])(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}(?:/\d{1,3})?"
                      r"(?![\w:])", self._ip, text)
        text = re.sub(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?(?![\w.])", self._ip, text)
        text = re.sub(r"(?<![\w.@-])(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
                      r"[A-Za-z][A-Za-z0-9-]{1,62}(?![\w-])", self._domain, text)
        return text


def body(text: str) -> str:
    """Вывод команды без первой строки «$ …» и последней «[код N]»."""
    lines = text.splitlines()
    if lines and lines[0].startswith("$ "):
        lines = lines[1:]
    if lines and re.fullmatch(r"\[код -?\d+\]", lines[-1].strip()):
        lines = lines[:-1]
    return "\n".join(lines)


def tables(ruleset: str) -> dict[tuple[str, str], dict[str, str]]:
    """`nft list ruleset` → {(семейство, таблица): {цепочка: тело}}."""
    result: dict[tuple[str, str], dict[str, str]] = {}
    current, chain, depth, lines = None, None, 0, []
    for line in ruleset.splitlines():
        stripped = line.strip()
        if depth == 0 and stripped.startswith("table ") and stripped.endswith("{"):
            parts = stripped.split()
            current = (parts[1], parts[2])
            result[current] = {}
        elif depth == 1 and stripped.startswith("chain ") and stripped.endswith("{"):
            chain, lines = stripped.split()[1], []
        elif depth == 2 and chain and stripped == "}":
            result[current][chain] = "\n".join(lines)
            chain = None
        elif chain:
            lines.append(stripped)
        depth += line.count("{") - line.count("}")
    return result


def structure(parsed: dict) -> str:
    out = []
    for (family, name), chains in parsed.items():
        out.append(f"table {family} {name}")
        for chain, text in chains.items():
            rules = [r for r in text.splitlines() if r and not r.startswith(("type ", "policy "))]
            hook = next((r for r in text.splitlines() if r.startswith("type ")), "")
            out.append(f"  chain {chain}: правил {len(rules)}{('; ' + hook) if hook else ''}")
    return "\n".join(out) or "(таблиц нет или нет прав)"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    masker = Masker()
    installed = read("ts-installed").strip() == "есть"
    status: dict = {}
    raw_status = body(read("ts-status-json"))
    if "{" in raw_status:
        try:
            status = json.loads(raw_status[raw_status.index("{"): raw_status.rindex("}") + 1])
        except ValueError:
            status = {}
    hostname = read("hostname").strip()
    masker.add_name(hostname, "устройство-{}")
    nodes = [status.get("Self") or {}] + list((status.get("Peer") or {}).values())
    for node in nodes:
        for key in ("HostName", "DNSName"):
            value = str(node.get(key) or "")
            masker.add_name(value, "устройство-{}")
            masker.add_name(value.split(".")[0], "устройство-{}")
    tailnet = status.get("CurrentTailnet") or {}
    for value in (status.get("MagicDNSSuffix"), tailnet.get("MagicDNSSuffix"),
                  tailnet.get("Name"), *(status.get("CertDomains") or [])):
        masker.add_name(str(value or ""), "tailnet-{}")
    for user in (status.get("User") or {}).values():
        for key in ("LoginName", "DisplayName"):
            masker.add_name(str(user.get(key) or ""), "пользователь-{}")

    # --- маскированные копии -------------------------------------------------------------
    skip = {"ts-status-json", "nft", "ts-journal", "hostname", "ts-installed"}
    for path in sorted(RAW.glob("*.txt")):
        if path.stem in skip:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        (OUT / path.name).write_text(masker.mask(text), encoding="utf-8")
    parsed = tables(body(read("nft")))
    lines = [structure(parsed), ""]
    for key, chains in parsed.items():
        if key in (("ip", "xgw"), ("ip6", "xgw6")):
            for chain in ("output", "block_output", "v6_guard"):
                if chain in chains:
                    lines += [f"--- {key[0]} {key[1]}: chain {chain} ---", chains[chain], ""]
        elif key[1].startswith("ts") or any(c.startswith("ts-") for c in chains):
            for chain, text in chains.items():
                lines += [f"--- {key[0]} {key[1]}: chain {chain} ---", text, ""]
    (OUT / "nft.txt").write_text(masker.mask("\n".join(lines)), encoding="utf-8")
    journal = body(read("ts-journal")).splitlines()
    counts = {
        word: sum(word.lower() in line.lower() for line in journal)
        for word in ("magicsock", "derp", "health", "netcheck", "error", "timeout", "udp",
                     "endpoint", "NeedsLogin", "netfilter", "dns")
    }
    journal_text = [f"строк за сутки: {len(journal)}",
                    "совпадений: " + ", ".join(f"{k} {v}" for k, v in counts.items()), "",
                    "--- последние 200 строк ---", *journal[-200:]]
    if installed:
        (OUT / "ts-journal.txt").write_text(masker.mask("\n".join(journal_text)), encoding="utf-8")

    # --- состояние Tailscale --------------------------------------------------------------
    me = status.get("Self") or {}
    peers = list((status.get("Peer") or {}).values())
    facts = []
    if not installed:
        facts.append("Tailscale не установлен")
    else:
        facts += [
            f"tailscaled: {body(read('ts-active')).strip() or 'нет данных'}",
            f"версия: {body(read('ts-version')).splitlines()[0] if body(read('ts-version')) else 'нет данных'}",
            f"BackendState: {status.get('BackendState', 'нет данных')}",
            f"адреса tailnet: {', '.join(me.get('TailscaleIPs') or []) or 'нет'}",
            f"в сети: {me.get('Online')}; DERP: {me.get('Relay') or 'нет'}",
            f"устройств в tailnet: {len(peers)}, в сети: {sum(bool(p.get('Online')) for p in peers)}",
            f"MagicDNS: {tailnet.get('MagicDNSEnabled', 'нет данных')}",
            "Health: " + ("; ".join(status.get("Health") or []) or "пусто"),
        ]
        prefs = body(read("ts-prefs"))
        for key in ("NetfilterMode", "CorpDNS", "RouteAll", "ExitNodeID", "RunSSH",
                    "ShieldsUp", "WantRunning", "LoggedOut"):
            found = re.search(rf'"{key}":\s*([^,\n]+)', prefs)
            if found:
                facts.append(f"prefs {key}: {found.group(1).strip()}")
        netcheck = body(read("ts-netcheck"))
        for key in ("UDP", "IPv4", "IPv6", "MappingVariesByDestIP", "Nearest DERP"):
            found = re.search(rf"^[ 	]*\*[ 	]*{re.escape(key)}:[ 	]*(.*)$", netcheck,
                              re.MULTILINE)
            if found:
                facts.append(f"netcheck {key}: {found.group(1).strip() or '(пусто)'}")
    rules = body(read("ip-rule"))
    facts.append("ip rule Tailscale (5210/5230/5250/5270): " + (
        ", ".join(p for p in ("5210", "5230", "5250", "5270") if re.search(rf"^{p}:", rules,
                                                                       re.MULTILINE)) or "нет"))
    facts.append("ip rule XGW (90/95/100): " + (
        ", ".join(p for p in ("90", "95", "100") if re.search(rf"^{p}:", rules, re.MULTILINE))
        or "нет"))
    routes52 = [
        line for line in body(read("route52")).splitlines()
        if line.strip() and not re.search(r"Error|does not exist|Dump terminated", line)
    ]
    facts.append(f"таблица 52: маршрутов {len(routes52)}" if routes52 else "таблица 52: нет")
    facts.append("интерфейс tailscale0: " + (
        "есть" if re.search(r"\btailscale0\b", body(read("addr"))) else "нет"))
    ts_chains = sorted({c for chains in parsed.values() for c in chains if c.startswith("ts-")})
    facts.append("цепочки Tailscale в nft: " + (", ".join(ts_chains) or "нет"))
    facts.append("таблицы nft: " + (", ".join(f"{f} {n}" for f, n in parsed) or "нет данных"))

    # --- гипотезы ---------------------------------------------------------------------------
    xgw4 = parsed.get(("ip", "xgw"), {})
    xgw6 = parsed.get(("ip6", "xgw6"), {})

    def exempt(text: str) -> bool:
        return bool(re.search(r"tailscale0|0x00ff0000|0xff0000|0x00080000|0x80000", text))

    verdicts = {}
    no_ts = "нет данных — Tailscale не установлен"
    out = xgw4.get("output")
    if not installed:
        verdicts["К1"] = no_ts
    elif out is None:
        verdicts["К1"] = ("нет — цепочки output в ip xgw нет: перехват трафика самой машины не "
                          "загружен (режим blocked или снят, либо capture.local выключен)"
                          if parsed else "нет данных — правила nft не прочитаны")
    elif "meta mark set" in out and not exempt(out):
        verdicts["К1"] = ("подтверждена — в цепочке output нет исключения для метки Tailscale "
                          "0x80000, правило meta mark set затирает её")
    else:
        verdicts["К1"] = "нет — исключение для метки Tailscale в цепочке output есть"
    if installed and verdicts["К1"].startswith("подтверждена"):
        netcheck = body(read("ts-netcheck"))
        if re.search(r"^\s*\*\s*UDP:\s*false", netcheck, re.MULTILINE):
            verdicts["К1"] += " (и netcheck: UDP нет)"
    resolved = body(read("ts-resolve"))
    resolved_ok = bool(re.search(r"\b100\.\d+\.\d+\.\d+|fd7a:", resolved))
    if not installed:
        verdicts["К2"] = no_ts
    elif tailnet.get("MagicDNSEnabled") is False:
        verdicts["К2"] = "нет — MagicDNS в tailnet выключен"
    elif out is None:
        verdicts["К2"] = "нет — цепочки output в ip xgw нет"
    elif re.search(r"dport != 53", out) and not exempt(out):
        verdicts["К2"] = ("подтверждена — DNS к 100.100.100.100:53 перехватывается в Xray "
                          "(исключения для tailscale0 нет); имя устройства через resolved: "
                          + ("разрешилось" if resolved_ok else "не разрешилось"))
    else:
        verdicts["К2"] = "нет — DNS к адресам tailnet мимо Xray пропускается"
    block = xgw4.get("block_output")
    if not installed:
        verdicts["К3"] = no_ts
    elif block is None:
        verdicts["К3"] = ("нет данных — шлюз сейчас не в режиме blocked (цепочки block_output "
                          "нет); проявляется только в нём")
    elif not exempt(block):
        verdicts["К3"] = ("подтверждена — шлюз в режиме blocked, и в block_output нет "
                          "исключения для tailscaled и tailscale0")
    else:
        verdicts["К3"] = "нет — исключение для Tailscale в block_output есть"
    guard = xgw6.get("v6_guard")
    ts6 = any(":" in ip for ip in (me.get("TailscaleIPs") or []))
    if not installed:
        verdicts["К4"] = no_ts
    elif guard is None:
        verdicts["К4"] = "нет — цепочки v6_guard в ip6 xgw6 нет"
    elif exempt(guard):
        verdicts["К4"] = "нет — исключение для Tailscale в v6_guard есть"
    elif ts6:
        verdicts["К4"] = ("подтверждена — v6_guard отбивает IPv6 tailnet (fd7a:…) и IPv6-сокеты "
                          "tailscaled: исключений нет")
    else:
        verdicts["К4"] = "нет данных — у шлюза нет IPv6-адреса tailnet"
    wan = re.search(r"^default via \S+ dev (\S+)", body(read("route-main")), re.MULTILINE)
    wan_cgnat = False
    if wan:
        for found in re.finditer(rf"\b{re.escape(wan.group(1))}\s+inet (\d+\.\d+\.\d+\.\d+)",
                                 body(read("addr"))):
            wan_cgnat |= ipaddress.ip_address(found.group(1)) in TAILNET4
    verdicts["К5 (доп.)"] = (no_ts if not installed else "нет данных — маршрута по умолчанию нет"
                             if not wan else "подтверждена — адрес WAN из 100.64.0.0/10 (CGNAT)"
                             if wan_cgnat else "нет — адрес WAN не из 100.64.0.0/10")
    ts0 = body(read("resolved-ts0"))
    if not installed or not re.search(r"tailscale0", ts0) or re.search(r"[Nn]o such|not found|"
                                                                       r"Failed", ts0):
        verdicts["К6 (доп.)"] = no_ts if not installed else "нет данных — tailscale0 нет в resolved"
    elif re.search(r"Default Route:\s*yes|\+DefaultRoute", ts0):
        verdicts["К6 (доп.)"] = ("подтверждена — tailscale0 — DNS по умолчанию (Override local "
                                 "DNS): запросы шлюза идут мимо VPN")
    else:
        verdicts["К6 (доп.)"] = "нет — tailscale0 не DNS по умолчанию"

    summary = ["== Состояние ==", *facts, "", "== Гипотезы ==",
               *(f"{key}: {value}" for key, value in verdicts.items())]
    text = masker.mask("\n".join(summary))
    (OUT / "summary.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    return check_leaks(masker)


def check_leaks(masker: Masker) -> int:
    """Ищет в masked/ то, что маскировка должна была спрятать; сами значения не печатает."""
    found = []
    for path in sorted(OUT.glob("*.txt")):
        text = path.read_text(encoding="utf-8").lower()
        if any(name in text for name in masker.names):
            found.append(f"{path.name}: имя устройства, пользователя или tailnet")
        for match in re.finditer(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])", text):
            try:
                address = ipaddress.ip_address(match.group(0))
            except ValueError:
                continue
            if address in TAILNET4 and address != TAILNET4.network_address and address != MAGIC_DNS:
                found.append(f"{path.name}: адрес tailnet")
            elif address.is_global:
                found.append(f"{path.name}: внешний адрес")
        if re.search(r"fd7a:115c:a1e0:[0-9a-f]", text) or "@gmail" in text or ".ts.net" in text:
            found.append(f"{path.name}: адрес или имя tailnet")
    if found:
        print("\nПРОВЕРКА МАСКИРОВКИ: ОСТАЛОСЬ —", "; ".join(sorted(set(found))))
        return 3
    print("\nпроверка маскировки: чисто")
    return 0


if __name__ == "__main__":
    sys.exit(main())
MASK_EOF
python3 -m py_compile mask.py && echo "mask.py: $(wc -l < mask.py) строк, синтаксис в порядке"
```

Ожидается: «mask.py: 358 строк, синтаксис в порядке».
Если число строк другое или есть ошибка: удали файл (`rm mask.py`) и повтори шаг, копируя блок
целиком.

## 3. Снимок

Шаг 3.1.

```bash
bash t0.sh 2>&1 | tee run.txt | tail -45; ls masked
```

Работает до двух минут (`tailscale netcheck` и `xgw diag`). Ожидается:
- блок «== Состояние ==» — по строке о `tailscaled`, версии, `BackendState`, адресах tailnet
  (вида `100.x.y.1`), netcheck, правилах `ip rule`, таблице 52, `tailscale0` и таблицах nft;
- блок «== Гипотезы ==» — шесть строк К1…К6, у каждой «подтверждена», «нет» или «нет данных»
  и пояснение;
- строка «проверка маскировки: чисто» и последней — «[код 0]»;
- список файлов в `masked`: `summary.txt`, `nft.txt`, `ip-rule.txt`, `route52.txt`, `addr.txt`,
  `resolved-ts0.txt`, `ts-status.txt`, `ts-netcheck.txt`, `ts-journal.txt`, `xgw-diag.txt` и
  другие.

Если первая строка «== Состояние ==» — «Tailscale не установлен»: **спроси заказчика**:
«Скрипт не нашёл программу tailscale. Tailscale стоит на шлюзе?» Ответ записать в отчёт. Скрипт
всё равно соберёт правила XGW и `xgw diag` — продолжай.
Если есть «ПРОВЕРКА МАСКИРОВКИ: ОСТАЛОСЬ» (последняя строка тогда «[код 3]»): в отчёт **не
переносить** названные там файлы, записать в «Наблюдения», какие файлы и что осталось (без
самих значений).
Если «[код …]» другой или есть `Traceback`: записать последние 30 строк `run.txt` в отчёт,
продолжать с тем, что есть в `masked`.

Шаг 3.2. Что из этого стоит показать (только чтение, ничего не меняет):

```bash
head -40 masked/nft.txt; echo ---; cat masked/ip-rule.txt masked/route52.txt masked/resolved-ts0.txt; echo ---; grep -E '^(Итог|FAIL|WARN)|Tailscale|tailscale' masked/xgw-diag.txt | head -20; echo ---; head -3 masked/ts-journal.txt
```

Ожидается: структура таблиц nft (у каждой цепочки — число правил), правила `ip rule`, маршруты
таблицы 52, DNS `tailscale0`, строки FAIL/WARN `xgw diag`, сводка журнала `tailscaled`.
Записать в отчёт как есть.

## 4. Порядок после снимка

Шаг 4.1. Ветка и каталог:

```bash
cd ~/zcod/xgw && git checkout main && git status --short | head; ls -ld ~/xgw-ts-t0/raw; cd ~/xgw-ts-t0
```

Ожидается: переключение на `main`, пустой `git status` (или только твой отчёт, когда он уже
создан), каталог `raw` с правами `drwx------`.

Шаг 4.2. **Спроси заказчика**: «Сырые данные снимка лежат на шлюзе в `~/xgw-ts-t0/raw` (только
для вас, в отчёт не попали). Оставить их или удалить?» Удалить — только если заказчик сказал
«удалить»: `rm -r ~/xgw-ts-t0/raw`.

## 5. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.16-tailscale-t0-<ГГГГ-ММ-ДД>.md` в репозитории (в
ветке `main`). Заполни бланк, вставляя файлы **только из `~/xgw-ts-t0/masked`**:

```markdown
# Отчёт T0: снимок Tailscale на шлюзе (только чтение)

Программа: ветка tailscale-t0, <хеш>. XGW: <версия>. Снимок: <дата и время из run.txt>.
Согласие заказчика: <да>. Tailscale установлен: <да / нет — ответ заказчика>.

## Гипотезы
| # | Итог | Пояснение скрипта |
|---|---|---|
| К1 | подтверждена / нет / нет данных | <строка К1 из summary.txt> |
| К2 | | |
| К3 | | |
| К4 | | |
| К5 (доп.) | | |
| К6 (доп.) | | |

## Состояние
<блок «== Состояние ==» из masked/summary.txt целиком>

## Файлы снимка (маскированные)
### summary.txt
### nft.txt
### ip-rule.txt и ip-rule6.txt
### route52.txt и route52v6.txt
### addr.txt
### resolved-ts0.txt
### ts-status.txt
### ts-prefs.txt
### ts-netcheck.txt
### ts-journal.txt
### xgw-status.txt
### xgw-diag.txt
<каждый файл — в блоке кода; если файла нет — «нет файла»>

## Наблюдения
<например: строки проверки маскировки, ошибки скрипта, ответы заказчика>

## Что не сделано и почему
```

Перед коммитом проверь, что в отчёте нет секретов:

```bash
grep -nE '(vless|vmess|trojan|ss|hysteria2)://[^*]|[0-9a-f]{8}-[0-9a-f]{4}-|tskey-[A-Za-z0-9]|nodekey:[0-9a-f]|\.ts\.net|@[a-z0-9-]+\.[a-z]|\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]+\.[0-9]+|fd7a:115c:a1e0:[0-9a-f]|([0-9a-f]{2}:){5}[0-9a-f]{2}' ~/zcod/xgw/docs/TEST-REPORT-REAL-MACHINE-0.1.16-tailscale-t0-*.md
```

Ожидается: пусто (строка `100.64.0.0/10` в пояснениях допустима). Если нашлось что-то ещё —
убрать из отчёта.

Коммит только отчёта: `cd ~/zcod/xgw && git add docs/TEST-REPORT-REAL-MACHINE-0.1.16-tailscale-t0-*.md &&
git commit -m "Отчёт T0: снимок Tailscale на шлюзе" && git push`.
