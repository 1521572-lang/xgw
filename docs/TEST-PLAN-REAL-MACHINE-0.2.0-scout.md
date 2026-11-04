# Разведка перед доработками XGW: что внедрять, а в чём нет смысла

## Зачем и как

Идей для шлюза много: NaiveProxy, Hysteria2 со сменой портов, ShadowTLS, Cloak, mieru, dae, а в
плане — дробление XHTTP, путь UDP, бюджет проб; поколения sing-box (G1) уже сделаны и ждут
приёмки по своему ТЗ. Смысл каждой идеи зависит от
фактов этой машины: какие серверы дают подписки, какие протоколы сейчас живы, пропускает ли
провайдер UDP, упирается ли шлюз в процессор. Эта проверка собирает эти факты, а решение по каждой
идее помощник выносит сам по заранее заданным правилам (раздел 6) — без оценки на глаз.

Исполнитель — GLM-5.3-Flash на ThinkCentre владельца, клон `~/zcod/xgw` (ветка `freepool`).
Одна сессия, около 30 минут. В XGW ничего не меняется. Наружу ходят только проверка сети (то же,
что кнопка «Проверить сеть» в панели) и, если владелец разрешит, одна загрузка 100 МБ через VPN.
Выполнять до или после приёмки G1, но не одновременно с ней и с любой другой проверкой: замер
процессора и загрузка исказили бы чужие замеры.

## Правила

Можно (и нужно, если помогает): любые инструменты — терминал, панель, браузер, зрение; повторять
команды, которые только читают; ждать дольше; подстраивать команду под окружение (путь, кавычки,
sudo), сохранив её смысл, — отметить это в отчёте. Если шаг дал ошибку — прочитать
`sudo xgw status`, `sudo xgw diag --no-net`, `journalctl -u xgw -n 50` для понимания (в отчёт —
только своими словами, без сырья) и перейти к следующему шагу: шаги друг от друга не зависят,
кроме шага 6.

Нельзя: менять настройки XGW, подписки, режим пула, ручной выбор сервера, WAN, LAN, Tailscale и
службы; устанавливать, обновлять, выключать и перезапускать что-либо; запускать старые ТЗ и
помощники; писать в отчёт имена серверов, устройств и подписок, адреса, домены и ссылки серверов
VPN, токены и строки журнала.

Остановиться и сообщить владельцу — только если дома пропал интернет. Ничего не чинить: все шаги
только читают, сами они его не ломают.

## 1. Вопросы владельцу

**Спроси владельца** (дословно) и запиши ответы:

«Готовлю разведку: что из новых средств обхода блокировок имеет смысл встроить в шлюз. Ничего не
меняю. Четыре вопроса:
(1) Как шлюз подключён к интернету: проводной или оптика — или мобильный (LTE/5G)?
(2) Есть ли у вас свой сервер (VPS) для VPN или готовность его завести? Да, нет или может быть.
(3) Что сейчас мешает дома, если мешает: медленно, не работает YouTube, отдельные сайты, обрывы?
(4) Можно ли один раз скачать 100 МБ через VPN, около минуты, чтобы измерить нагрузку на
процессор? Это расходует трафик подписки.»

Запомни для шага 6: ответ (1) — `fixed` (проводной, оптика), `mobile` или `unknown`; ответ (2) —
`yes`, `no` или `maybe`. Ответ (3) — в отчёт дословно, без имён.

## 2. Папка и помощник

```bash
mkdir -p "$HOME/xgw-scout" && cd "$HOME/xgw-scout" && cat > scout.py <<'EOF'
"""XGW: разведка перед доработками — что из идей (NaiveProxy, Hysteria2, ShadowTLS, Cloak, mieru,
dae) и пунктов плана (G1, XHTTP, UDP, бюджет проб) имеет смысл на этом шлюзе. Читает кэш подписок,
inventory.json, status.json, версии ядер и /proc; в сеть ходит только netcheck (кнопка «Проверить
сеть») и, если владелец разрешил, одна загрузка через VPN (load). В XGW ничего не меняет. Имён
серверов, адресов, доменов и ссылок не печатает — только числа. Итоги кладёт в каталог out рядом
с собой. Режимы: facts, links, health, netcheck, cpu [СЕКУНДЫ], load [МБ], owner WAN СВОЙ_СЕРВЕР,
verdict."""
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

LIB = "/opt/xgw/lib"
OUT = Path(__file__).resolve().parent / "out"
SUPPORTED = {"vless", "vmess", "trojan", "ss", "hysteria2", "hy2", "tuic", "anytls", "wireguard",
             "wg", "socks"}
NOT_SERVERS = {"direct", "block", "dns", "freedom", "blackhole", "selector", "urltest", "select",
               "url-test", "fallback", "load-balance", "relay"}
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
SINGBOX_UNITS = ("xgw-singbox.service", "xgw-singbox-blue.service", "xgw-singbox-green.service")
LOAD_URL = "https://speed.cloudflare.com/__down?bytes={}"


def xgw():
    sys.path.insert(0, LIB)
    from xgw import config
    from xgw.paths import Paths

    paths = Paths.from_env()
    return config.load(paths.config_file)[0], paths


def save(name, data):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                      encoding="utf-8")


def saved(name):
    try:
        return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run(argv, timeout=60):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, type(exc).__name__
    return done.returncode, done.stdout or done.stderr


def version(text):
    found = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(part or 0) for part in found.groups()) if found else (0, 0, 0)


def facts():
    _cfg, paths = xgw()
    release = Path("/etc/os-release").read_text(encoding="utf-8")
    pretty = re.search(r'^PRETTY_NAME="?([^"\n]+)', release, flags=re.MULTILINE)
    cpu = re.search(r"model name\s*:\s*(.+)", Path("/proc/cpuinfo").read_text(encoding="utf-8"))
    mem = re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text(encoding="utf-8"))
    sb_lines = run([str(paths.singbox_bin), "version"])[1].splitlines()
    jit = Path("/proc/sys/net/core/bpf_jit_enable")
    info = {
        "os": pretty.group(1) if pretty else "?",
        "kernel": platform.release(),
        "cpu": f"{cpu.group(1).strip() if cpu else '?'}, ядер {os.cpu_count()}",
        "ram_gb": round(int(mem.group(1)) / 1048576, 1) if mem else None,
        "xray": (run([str(paths.xray_bin), "version"])[1].splitlines() or ["нет"])[0][:60],
        "singbox": sb_lines[0][:60] if sb_lines else "нет",
        "singbox_tags": next((line for line in sb_lines if line.lower().startswith("tags")),
                             "")[:300],
        "libcronet": (paths.singbox_bin.parent / "libcronet.so").exists(),
        "dae_kernel_5_17": version(platform.release()) >= (5, 17, 0),
        "dae_btf": Path("/sys/kernel/btf/vmlinux").exists(),
        "dae_cgroup2": Path("/sys/fs/cgroup/cgroup.controllers").exists(),
        "dae_bpf_jit": jit.read_text().strip() if jit.exists() else "нет",
    }
    save("facts", info)
    for key, value in info.items():
        print(f"{key}: {value}")


def _link(line, counts, decode):
    scheme, _, rest = line.partition("://")
    scheme = scheme.strip().lower()
    counts[f"scheme={scheme}"] += 1
    if scheme == "vmess":
        try:
            data = json.loads(decode(rest.split("#")[0]).decode("utf-8"))
        except Exception:  # битая ссылка: считаем только схему
            return
        counts[f"vmess.type={str(data.get('net') or 'tcp').lower()}"] += 1
        counts[f"vmess.security={str(data.get('tls') or 'none').lower()}"] += 1
        return
    try:
        parts = urlsplit(line)
        query = {key.lower(): values[0].lower() for key, values in parse_qs(parts.query).items()}
    except ValueError:
        return
    if scheme in ("vless", "trojan"):
        security = query.get("security") or ("none" if scheme == "vless" else "tls")
        counts[f"{scheme}.security={security}"] += 1
        counts[f"{scheme}.type={query.get('type') or 'tcp'}"] += 1
        if "vision" in query.get("flow", ""):
            counts[f"{scheme}.flow=vision"] += 1
    elif scheme in ("hysteria2", "hy2"):
        port = parts.netloc.rpartition("@")[2].rpartition("]")[2].rpartition(":")[2]
        if query.get("mport") or "," in port or "-" in port:
            counts["hysteria2.ports=range"] += 1
        if query.get("obfs"):
            counts[f"hysteria2.obfs={query['obfs']}"] += 1
    elif scheme == "ss" and query.get("plugin"):
        counts[f"ss.plugin={query['plugin'].split(';')[0]}"] += 1


def _json(text, counts):
    try:
        data = json.loads(text)
    except ValueError:
        return
    for config in data if isinstance(data, list) else [data]:
        if not isinstance(config, dict):
            continue
        outs = [*(config.get("outbounds") or []), *(config.get("endpoints") or [])]
        if not outs and ("type" in config or "protocol" in config):
            outs = [config]
        for out in outs:
            kind = str(out.get("type") or out.get("protocol") or "?").lower() if isinstance(
                out, dict) else "?"
            if kind in NOT_SERVERS or kind == "?":
                continue
            counts[f"json.type={kind}"] += 1
            stream, transport = out.get("streamSettings"), out.get("transport")
            net = (stream.get("network") if isinstance(stream, dict) else None) or (
                transport.get("type") if isinstance(transport, dict) else None)
            if net:
                counts[f"json.{kind}.type={str(net).lower()}"] += 1
            if out.get("server_ports"):
                counts["hysteria2.ports=range"] += 1


def links():
    _cfg, paths = xgw()
    from xgw.parsers.common import b64_decode

    counts, formats = Counter(), Counter()
    for body in sorted(paths.cache_dir.glob("*.body")):
        text = body.read_bytes().decode("utf-8", "replace").lstrip("﻿").strip()
        if not text:
            formats["пусто"] += 1
        elif text[0] in "{[":
            formats["json"] += 1
            _json(text, counts)
        elif re.search(r"(?m)^\s*(proxies|proxy-groups)\s*:", text):
            formats["clash (XGW не разбирает)"] += 1
            for kind in re.findall(r"(?m)^\s*-?\s*type:\s*([\w-]+)", text):
                if kind.lower() not in NOT_SERVERS:
                    counts[f"clash.type={kind.lower()}"] += 1
        else:
            if "://" not in text:
                try:
                    text = b64_decode(text).decode("utf-8")
                except Exception:  # не base64 и не ссылки
                    formats["непонятный"] += 1
                    continue
            formats["ссылки"] += 1
            for line in text.splitlines():
                if "://" in line:
                    _link(line.strip(), counts, b64_decode)
    try:
        servers = json.loads((paths.var / "inventory.json").read_text(encoding="utf-8"))["servers"]
    except (OSError, ValueError, KeyError):
        servers = []
    data = {
        "formats": dict(formats), "links": dict(sorted(counts.items())),
        "xgw_protocols": dict(Counter(str(s.get("protocol")) for s in servers)),
        "xgw_cores": dict(Counter(str(s.get("core")) for s in servers)),
        "xgw_skipped": dict(Counter(str(s.get("protocol")) for s in servers if s.get("skip"))),
    }
    save("links", data)
    for key, value in data.items():
        print(f"{key}: {json.dumps(value, ensure_ascii=False)}")


def health():
    _cfg, paths = xgw()
    status = json.loads(paths.status_file.read_text(encoding="utf-8"))
    rows = {}
    for role in ("members", "spares"):
        for item in status.get(role) or []:
            row = rows.setdefault(f"{item.get('protocol') or '?'} / {item.get('core') or '?'}",
                                  {"всего": 0, "живы": 0, "speeds": []})
            row["всего"] += 1
            good = item.get("alive") if role == "members" else item.get("verdict") in ("OK", "SLOW")
            row["живы"] += bool(good)
            if isinstance(item.get("speed_mbps"), (int, float)):
                row["speeds"].append(item["speed_mbps"])
    for row in rows.values():
        speeds = row.pop("speeds")
        row["медиана_мбит"] = round(statistics.median(speeds), 1) if speeds else None
    singbox = status.get("singbox") or {}
    budget = status.get("budget") if isinstance(status.get("budget"), dict) else {}
    data = {
        "state": status.get("state"), "rows": rows,
        "verdicts": dict(Counter(str(item.get("verdict")) for item in status.get("spares") or [])),
        "whitelist": bool(status.get("whitelist")),
        "singbox_alive": singbox.get("alive"), "singbox_bridged": singbox.get("bridged"),
        "limited_subs": sum(1 for sub in status.get("subscriptions") or []
                            if isinstance(sub, dict) and sub.get("limited")),
        "budget": {key: value for key, value in budget.items() if isinstance(value, (int, float))},
    }
    save("health", data)
    for key, value in data.items():
        print(f"{key}: {json.dumps(value, ensure_ascii=False)}")


def netcheck():
    cfg, paths = xgw()
    from xgw import netcheck as checking
    from xgw.store import Store

    names = set()
    try:
        store = Store(paths.db_file)
        names = {str(node.get("name")) for node in store.all_nodes() if node.get("name")}
        store.close()
    except Exception:  # без имён маскируем только адреса
        pass
    result = []
    for check in checking.Netcheck(cfg, paths, firewall=False).run():
        text = IPV4.sub("<адрес>", check.text)
        for name in sorted(names, key=len, reverse=True):
            text = text.replace(name, "<сервер>")
        result.append({"name": check.name, "level": check.level, "text": text})
        print(f"{check.level} {check.name}: {text}")
    save("netcheck", result)


def _pid(unit):
    pid = run(["systemctl", "show", "-p", "MainPID", "--value", unit])[1].strip()
    return int(pid) if pid.isdigit() and pid != "0" else None


def _ticks(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])


def _system():
    values = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    return sum(values), values[3] + values[4]


def _wan():
    try:
        routes = json.loads(run(["ip", "-j", "route", "show", "default"])[1] or "[]")
        dev = routes[0].get("dev")
    except (ValueError, IndexError, AttributeError):
        return None, None
    for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
        name, _, data = line.partition(":")
        if name.strip() == dev:
            fields = data.split()
            return dev, int(fields[0]) + int(fields[8])
    return dev, None


def sample(seconds, step=5.0, stop=None):
    """Загрузка процессора (% одного ядра у ядер, % всей машины) и трафик WAN по шагам."""
    hz = os.sysconf("SC_CLK_TCK")
    # sing-box после G1 работает и во временных службах поколений: считаются все три.
    pids = {"xray": [_pid("xgw-xray.service")], "singbox": [_pid(unit) for unit in SINGBOX_UNITS]}

    def snap():
        procs = {}
        for key, group in pids.items():
            ticks = []
            for pid in group:
                try:
                    ticks.append(_ticks(pid) if pid else None)
                except (OSError, IndexError, ValueError):
                    ticks.append(None)
            found = [value for value in ticks if value is not None]
            procs[key] = sum(found) if found else None
        return time.monotonic(), _system(), procs, _wan()[1]

    rows, prev, end = [], snap(), time.monotonic() + seconds
    while time.monotonic() < end and not (stop is not None and stop.is_set()):
        time.sleep(step)
        now = snap()
        span = now[0] - prev[0]
        total, idle = now[1][0] - prev[1][0], now[1][1] - prev[1][1]
        row = {"system_pct": round(100 * (total - idle) / total, 1) if total else 0.0}
        for key in pids:
            if now[2][key] is not None and prev[2][key] is not None:
                # Процесс поколения мог завершиться между замерами — без отрицательных долей.
                used = max(0, now[2][key] - prev[2][key])
                row[f"{key}_pct"] = round(100 * used / hz / span, 1)
        if now[3] is not None and prev[3] is not None:
            row["wan_mbps"] = round((now[3] - prev[3]) * 8 / span / 1e6, 1)
        rows.append(row)
        prev = now
    keys = sorted({key for row in rows for key in row})
    return {key: {"средн": round(statistics.mean(r[key] for r in rows if key in r), 1),
                  "макс": max(r[key] for r in rows if key in r)} for key in keys}


def cpu(seconds):
    data = {"seconds": seconds, "cores": os.cpu_count(), **sample(seconds)}
    save("cpu", data)
    print(json.dumps(data, ensure_ascii=False))


def load(megabytes):
    stop, result = threading.Event(), {}
    thread = threading.Thread(target=lambda: result.update(sample(300, 1.0, stop)))
    thread.start()
    started, got, error = time.monotonic(), 0, ""
    request = urllib.request.Request(LOAD_URL.format(megabytes * 1_000_000),
                                     headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            while chunk := response.read(1 << 16):
                got += len(chunk)
                if time.monotonic() - started > 180:
                    break
    except OSError as exc:
        error = type(exc).__name__
    took = time.monotonic() - started
    time.sleep(1.5)
    stop.set()
    thread.join()
    data = {"mb": round(got / 1e6, 1), "seconds": round(took, 1),
            "mbps": round(got * 8 / took / 1e6, 1) if took else 0.0, "error": error, **result}
    save("load", data)
    print(json.dumps(data, ensure_ascii=False))


def verdict():
    facts_, links_, health_ = saved("facts") or {}, saved("links") or {}, saved("health") or {}
    net, owner = saved("netcheck"), saved("owner") or {}
    cpu_, load_ = saved("cpu") or {}, saved("load") or {}
    counts = links_.get("links", {})

    def total(*words):
        return sum(n for key, n in counts.items() if any(word in key for word in words))

    naive, mieru = total("naive"), total("mieru")
    xhttp, ranged = total("type=xhttp", "type=splithttp"), counts.get("hysteria2.ports=range", 0)
    shadowtls, cloak = total("shadow-tls", "shadowtls"), total("ck-client", "cloak")
    protocols, cores = links_.get("xgw_protocols", {}), links_.get("xgw_cores", {})
    udp = sum(protocols.get(name, 0) for name in ("hysteria2", "tuic", "wireguard", "hysteria"))
    # inventory.json: dual | xray | singbox (кто умеет); status.json: через какое ядро идёт сейчас.
    singbox = max(cores.get("singbox", 0), sum(
        row.get("всего", 0) for key, row in (health_.get("rows") or {}).items()
        if key.endswith("sing-box")))
    unknown = sorted(key.split("=", 1)[1] for key in counts if key.startswith("scheme=")
                     and key.split("=", 1)[1] not in SUPPORTED and "naive" not in key
                     and "mieru" not in key)
    # OK бывает и у «не проверен» — проходит только при ответе STUN напрямую.
    udp_check = next((c for c in net or [] if c["name"] == "UDP напрямую"), None)
    udp_ok = None if udp_check is None or "не проверен" in udp_check["text"] else (
        "пропускает UDP" in udp_check["text"])
    own = owner.get("own_server") == "yes"
    peak = max((d.get("xray_pct", {}).get("макс", 0) for d in (cpu_, load_)), default=0)
    rate = max(load_.get("mbps", 0), cpu_.get("wan_mbps", {}).get("макс", 0))
    dae_ready = all(facts_.get(key) for key in ("dae_kernel_5_17", "dae_btf", "dae_cgroup2"))
    sb_ver = version(facts_.get("singbox", ""))
    rows = [
        ("NaiveProxy через sing-box",
         "ВНЕДРЯТЬ" if naive or own else "НЕТ СМЫСЛА СЕЙЧАС",
         f"ссылок naive {naive}; свой сервер: {owner.get('own_server', '?')}; sing-box "
         f"{'.'.join(map(str, sb_ver))} (нужен 1.13+), libcronet.so: {facts_.get('libcronet')}"),
        ("Hysteria2: случайный интервал смены портов",
         "НЕТ СМЫСЛА СЕЙЧАС" if not ranged else "НЕ ХВАТАЕТ ДАННЫХ" if udp_ok is None
         else "ВНЕДРЯТЬ (мелкая правка)" if udp_ok else "НЕТ СМЫСЛА: UDP напрямую не проходит",
         f"hysteria2 с диапазоном портов {ranged}; UDP напрямую: {udp_ok}"),
        ("ShadowTLS v3", "УЖЕ ЕСТЬ (sing-box)", f"ссылок ShadowTLS {shadowtls}"),
        ("Cloak", "РАЗОБРАТЬ ОТДЕЛЬНО" if cloak else "НЕТ СМЫСЛА", f"ссылок Cloak {cloak}"),
        ("mieru (третье ядро)", "РАССМОТРЕТЬ: большой объём" if mieru or own
         else "НЕТ СМЫСЛА СЕЙЧАС",
         f"ссылок mieru {mieru}; свой сервер: {owner.get('own_server', '?')}"),
        ("dae", "НЕЛЬЗЯ: ядро не подходит" if not dae_ready
         else "НЕ ХВАТАЕТ ДАННЫХ" if rate < 20 else "РАССМОТРЕТЬ ЭКСПЕРИМЕНТ" if peak >= 70
         else "НЕТ СМЫСЛА: процессор не узкое место",
         f"Xray макс {peak}% ядра при {rate} Мбит/с; ядро {facts_.get('kernel')}"),
        ("G1: поколения sing-box (сделано, ждёт приёмки)",
         "ПРИЁМКА ИМЕЕТ СМЫСЛ" if singbox else "ПРИЁМКА НЕ ДОКАЖЕТ: через sing-box нет серверов",
         f"серверов через sing-box {singbox}; sing-box отвечает: {health_.get('singbox_alive')}"),
        ("T01/T02: дробление XHTTP", "НУЖНО" if xhttp else "ОТЛОЖИТЬ", f"ссылок XHTTP {xhttp}"),
        ("C07: путь UDP", "НУЖНО" if udp else "ОТЛОЖИТЬ", f"серверов на UDP {udp}"),
        ("C05/C06: бюджет проб", "НУЖНО" if health_.get("limited_subs") else "ПО ПЛАНУ",
         f"лимитированных подписок {health_.get('limited_subs')}"),
        ("Неизвестные схемы ссылок", "РАЗОБРАТЬ ОТДЕЛЬНО" if unknown else "НЕТ",
         ", ".join(unknown) or "нет"),
    ]
    save("verdict", [{"пункт": a, "решение": b, "основание": c} for a, b, c in rows])
    for item, decision, basis in rows:
        print(f"| {item} | {decision} | {basis} |")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "owner" and len(sys.argv) == 4 and sys.argv[2] in ("fixed", "mobile", "unknown") \
            and sys.argv[3] in ("yes", "no", "maybe"):
        save("owner", {"wan": sys.argv[2], "own_server": sys.argv[3]})
        print("ответы владельца записаны")
    elif mode in ("facts", "links", "health", "netcheck", "verdict"):
        globals()[mode]()
    elif mode == "cpu":
        cpu(int(sys.argv[2]) if len(sys.argv) > 2 else 300)
    elif mode == "load":
        load(int(sys.argv[2]) if len(sys.argv) > 2 else 100)
    else:
        print("режим: facts | links | health | netcheck | cpu [С] | load [МБ] | "
              "owner fixed|mobile|unknown yes|no|maybe | verdict")
EOF
python3 -c "import hashlib;d=open('scout.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; git -C "$HOME/zcod/xgw" log -1 --format='%h %s'
```

Ожидается: сумма `adb2dc5fdacf2bdc` и строка последнего коммита клона (записать).

Если сумма другая: выполнить блок ещё раз, скопировав его целиком. Снова другая — сообщить
владельцу и ждать ответа (помощник с ошибкой даст неверные числа).

## 3. Система, подписки, серверы

```bash
cd "$HOME/xgw-scout" && for m in facts links health; do echo "== $m"; sudo python3 -I scout.py $m; done 2>&1 | tee data.txt
```

Ожидается три блока строк `ключ: значение`:
- `facts` — система, ядро, процессор, память, версии Xray и sing-box, строка `Tags` sing-box,
  `libcronet: …`, четыре строки `dae_…`;
- `links` — форматы подписок и счётчики ссылок вида `scheme=vless`, `vless.type=xhttp`,
  `hysteria2.ports=range`, `ss.plugin=…`; ниже — что из этого разобрал сам XGW
  (`xgw_protocols`, `xgw_cores`, `xgw_skipped`);
- `health` — по каждому протоколу и ядру: сколько серверов, сколько живы, медиана скорости;
  вердикты запасных, белые списки, sing-box, лимитированные подписки, бюджет проб.

Если в блоке `Traceback`: записать режим и последнюю строку ошибки (дефект помощника) и идти
дальше — решение в шаге 6 по этому блоку станет «НЕ ХВАТАЕТ ДАННЫХ», остальные пункты не пострадают.

## 4. Проверка сети

```bash
cd "$HOME/xgw-scout" && sudo python3 -I scout.py netcheck 2>&1 | tee netcheck.txt
```

Ожидается 5 строк вида `OK|WARN|FAIL <название>: <текст>` — «MTU до сервера», «UDP напрямую»,
«UDP через VPN», «Утечка DNS», «Утечка IPv6». Имена серверов и адреса помощник уже заменил на
`<сервер>` и `<адрес>`.

Если команда упала или идёт дольше 2 минут — записать, идти дальше.

## 5. Нагрузка на процессор

Шаг 5.1 — пять минут обычной работы дома:

```bash
cd "$HOME/xgw-scout" && sudo python3 -I scout.py cpu 300 2>&1 | tee cpu.txt
```

Ожидается одна строка JSON: загрузка всей машины (`system_pct`), процессов Xray и sing-box (в
процентах одного ядра) и трафик WAN (`wan_mbps`), средние и наибольшие.

Шаг 5.2 — только если владелец разрешил (вопрос 4):

```bash
cd "$HOME/xgw-scout" && sudo python3 -I scout.py load 100 2>&1 | tee load.txt
```

Ожидается одна строка JSON: сколько скачано, за сколько секунд, скорость `mbps` и загрузка
процессора во время загрузки. `error` не пусто или скорость ниже 20 Мбит/с — записать как есть,
не повторять.

Если владелец не разрешил — записать «5.2 не выполнялся (нет согласия)».

## 6. Решение

Подставь ответы владельца из шага 1 вместо `WAN` и `СВОЙ` (например, `owner fixed no`):

```bash
cd "$HOME/xgw-scout" && sudo python3 -I scout.py owner WAN СВОЙ && sudo python3 -I scout.py verdict 2>&1 | tee verdict.txt
```

Ожидается «ответы владельца записаны» и таблица из 11 строк `| пункт | решение | основание |`.

Правила, по которым считает помощник (для проверки и для отчёта):

| Пункт | Решение |
|---|---|
| NaiveProxy через sing-box | ВНЕДРЯТЬ, если в подписках есть ссылки naive или у владельца есть свой сервер; иначе НЕТ СМЫСЛА СЕЙЧАС |
| Hysteria2: случайный интервал смены портов | ВНЕДРЯТЬ, если есть hysteria2 с диапазоном портов и UDP напрямую проходит; без UDP — НЕТ СМЫСЛА |
| ShadowTLS v3 | УЖЕ ЕСТЬ (через sing-box) |
| Cloak | РАЗОБРАТЬ ОТДЕЛЬНО, если есть ссылки Cloak; иначе НЕТ СМЫСЛА |
| mieru (третье ядро) | РАССМОТРЕТЬ, если есть ссылки mieru или свой сервер; иначе НЕТ СМЫСЛА СЕЙЧАС |
| dae | НЕЛЬЗЯ, если ядро не подходит; НЕ ХВАТАЕТ ДАННЫХ, если трафика было меньше 20 Мбит/с; РАССМОТРЕТЬ ЭКСПЕРИМЕНТ, если Xray занимал от 70% ядра; иначе НЕТ СМЫСЛА |
| G1: поколения sing-box (сделано, ждёт приёмки) | ПРИЁМКА ИМЕЕТ СМЫСЛ, если через sing-box идёт хотя бы один сервер; иначе ПРИЁМКА НЕ ДОКАЖЕТ |
| T01/T02: дробление XHTTP | НУЖНО, если в подписках есть XHTTP; иначе ОТЛОЖИТЬ |
| C07: путь UDP | НУЖНО, если есть серверы на UDP (hysteria2, TUIC, WireGuard); иначе ОТЛОЖИТЬ |
| C05/C06: бюджет проб | НУЖНО, если есть лимитированные подписки; иначе ПО ПЛАНУ |
| Неизвестные схемы ссылок | РАЗОБРАТЬ ОТДЕЛЬНО, если такие есть (их схемы — в «основании») |

Если решение явно противоречит числам из шагов 3–5 (например, ссылки naive есть, а решение «НЕТ
СМЫСЛА») — не исправлять таблицу, а отметить расхождение в «Наблюдениях».

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-scout-<ДАТА>.md` в клоне (`<ДАТА>` — ГГГГ-ММ-ДД),
коммит «Отчёт: XGW 0.2.0, разведка перед доработками», `git push` в `freepool`. Только этот файл.
Числа и строки помощника — как есть; без имён, адресов, доменов серверов, ссылок и сырья журналов.
Скажи владельцу: «Разведка закончена, отчёт отправлен».

```markdown
# Отчёт: XGW 0.2.0 — разведка перед доработками

Дата: <…>. Клон: <хеш и тема>. Помощник: <сумма>. Исполнитель: <модель>.

## Ответы владельца
- Подключение шлюза: <…>. Свой сервер: <…>. Согласие на загрузку 100 МБ: <да/нет>.
- Что мешает дома (дословно, без имён): <…>

## Решения (таблица из шага 6 без изменений)
| Пункт | Решение | Основание |
|---|---|---|
| … | … | … |

## Факты
- Система (`facts`): <строки>
- Подписки (`links`): <форматы и счётчики>
- Серверы (`health`): <строки по протоколам, вердикты, белые списки, sing-box, лимиты, бюджет>
- Проверка сети: <5 строк>
- Процессор: <cpu: средн/макс>; загрузка 100 МБ: <мбит/с, загрузка Xray> или «не выполнялась»

## Отклонения и наблюдения
<что делалось не так, как в ТЗ, и почему; ошибки помощника; противоречия решений и чисел; что
заметил сам — со словом «предположение»>
```
