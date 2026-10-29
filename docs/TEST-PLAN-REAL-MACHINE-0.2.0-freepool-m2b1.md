# Проверка XGW 0.2.0: бесплатные серверы, веха М2б.1 (устройство через бесплатные серверы)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-fpb1/…`). Файл помощника создавай только командой шага 1.2, выполненной в
терминале. Блок команды копируй целиком, ничего в нём не меняя.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. Телефон — S25 Ultra в домашней сети.
Команды — в терминале сеанса заказчика (`sudo` от его имени).

Что нового (ASSUMPTIONS п. 262, план — «Веха М2б»): впервые **настоящий трафик идёт через
бесплатные серверы** — у одного устройства, которое выберет заказчик. Остальной дом, сама машина
и каналы демона — через подписку, как сейчас (решения заказчика 29.10.2026: сначала одно
устройство, OpenVPN — отдельным шагом).
1. В списке устройств панели у устройства — «Бесплатные серверы» (с предупреждением). Его
   зарубежные сайты идут через проверенные шлюзом бесплатные серверы (списки GitHub, ключи
   Outline: своя проверка OK или SLOW не старше 3 часов, страна выхода — EU, адрес — IPv4 в
   ссылке), российские домены (.ru, .su, .рф) — напрямую, как у всех.
2. В рабочем конфиге Xray — выходы `pool-*` (до 8), балансировщик `pool` и правило по адресу
   устройства после прямых российских доменов. Закреплён живой сервер с меньшей задержкой, он
   держится, пока жив; умер — следующий.
3. Серверов нет или все молчат — у устройства **закрыто** (через подписку оно не идёт), в панели
   метка «бесплатные серверы · закрыто».
4. Смена состава пула — через API ядра, **без перезапуска Xray** (перезапуск — только когда
   устройство выбрало пул и когда с него ушло). Это у разработчика на живом ядре не проверялось —
   проверяется здесь.
5. Выключить наблюдение, пока через пул идёт устройство, панель не даёт; команда выключает и
   предупреждает.

Здесь, у разработчика, — только юнит-тесты затронутых модулей и ruff. Всё остальное — на этой
машине.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `openvpn*`,
  `tailscaled`, NetworkManager, `ssh`; ручные `nft` (кроме `nft list`), `ip` (кроме чтения
  помощником), `ip netns`, `nsenter`, `iptables`, `tc`, `sysctl -w`, `systemd-run`; команды
  `tailscale`, `xray`, `sing-box` и `openvpn`. `sudo xgw pool mode …` — только в шагах 1.3
  (`off`), 3.1 (`observe`), 6.2 (`off`), 6.3 (`observe`) и по правилу «Наблюдение не оставлять
  включённым» (`off`).
- Самому открывать сайты источников (vpngate, vpnbook), файлы списков на GitHub и сайты для
  проверки страны — в браузере, `curl`, `wget` и как угодно ещё. Сайты на устройствах
  открывает только заказчик.
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, `/etc/openvpn`, код XGW. Печатать `config.toml`, `panel.json`,
  рабочие конфиги Xray и sing-box, файлы в `/var/lib/xgw/freepool` и `/run/xgw/fp` (`cat`,
  `less`, `grep` по ним) — в них ключи подписок, учётки, пароли и ссылки серверов. Серверы,
  выбор устройств, переключатели и кнопки в панели меняет и нажимает только заказчик.
  Коммитить что-либо, кроме отчёта (§10).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`; тестовое устройство — «тестовое устройство» и его адрес
  `192.168.…`), внешние IP (и тот, что покажет сайт проверки страны), токены, адреса и домены
  подписок, IP, домены, имена и ссылки серверов VPN (и бесплатных тоже), логины и пароли, строки
  журнала. Можно: адреса устройств в домашней сети (`192.168.…`), коды стран, названия
  источников, счётчики, статусы, коды причин, размеры, права файлов, времена, версии пакетов и
  строки помощника.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю, как устройство ходит в интернет через бесплатные серверы (веха М2б.1). По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд. Внешний интерфейс (WAN), его соединение и DHCP
установка не трогает: меняются только профиль LAN, свои таблицы nftables и свои службы.
(2) Я включу наблюдение командой `sudo xgw pool mode observe`: шлюз будет собирать списки
бесплатных серверов через подписку и проверять их (до 4 серверов в минуту, около 15–20 МБ в
час). В середине я на 5 минут выключу его командой и включу снова — проверка «закрыто». В конце
вы выключите его кнопкой «Выключить» (не ответите за 30 минут — выключу командой).
(3) Вы выберете в панели одно тестовое устройство (лучше телефон в домашнем Wi-Fi без своего
VPN) и пустите его через бесплатные серверы. Владельцы этих серверов неизвестны и видят, к каким
сайтам идёт устройство; содержимое сайтов с https защищено, без https — нет. Российские сайты
(.ru, .su, .рф) у него идут напрямую. Остальные устройства и этот компьютер — через подписку,
как сейчас. В конце вы вернёте устройство на подписку («Сервер: авто»).
(4) На тестовом устройстве и на этом компьютере вы откроете сайт, который показывает страну
выхода (например ipinfo.io), и скажете мне только страну — без адреса.
(5) Около часа вы будете обычным образом пользоваться тестовым устройством (сайты, видео,
приложения) и скажете, что открывалось и как.
(6) По моей просьбе прочитаете мне сводку из карточки «Бесплатные серверы» и метку устройства.
(7) В конце откроете любой сайт на этом компьютере и на телефоне.
Проверка займёт около двух с половиной часов. Можно согласиться не на все пункты.»

Против пункта 1, 2 или 3 — **стоп**. Против 4 — шаги 4.3, 6.2 (часть заказчика), 6.3 (часть
заказчика) и 7.2 пропустить; против 5 — шаг 5.1 сократить до 10 минут без вопросов заказчику;
против 6 — шаги 4.4 и 6.1 пропустить; против 7 — шаг 9.3. Если против 2 только выключение
кнопкой — в шаге 9.1 выключить командой. В отчёте у пропущенного — «не выполнялся». Если ответа
на вопрос нет — не начинать, спросить ещё раз.

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-fpb1" && chmod 700 "$HOME/xgw-fpb1" && cd "$HOME/xgw-fpb1" && cat > fpb1check.py <<'EOF'
"""XGW 0.2.0, бесплатный пул (веха М2б.1: устройство через бесплатные серверы): помощник
проверки. Только читает: состояние XGW (/run/xgw, /var/lib/xgw/freepool, рабочие конфиги Xray
и sing-box), бэкенд OpenVPN (пакет, пользователи, служба, пересылка IPv4, набор fp_peers, ufw,
veth) и журналы со стандартного ввода — счётчики, коды, права и да/нет, без адресов, имён,
ссылок и паролей. watch — живые поколения по /proc и systemctl show: в пространство имён не
входит и ничего не меняет. checks <секунды> — только записи проверок с этого времени.
quota — свободен ли суточный предел подключений OpenVPN (только время подключений).
admitted — допущенные к трафику серверы пула; route — правило устройства, балансировщики и
пробы ядра в рабочем конфиге; config — серверы пула в выходах подписки и pool-*; xstats —
трафик Xray по выходам и пробы ядра (метрики на 127.0.0.1); xray — когда запущен Xray.
Режимы: units, backend, pool, quota, admitted, route, checks, lists, files, config, xstats,
xray, leak, digest, subs, fwd, log, agentlog, watch."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("FPB1_LIB", "/opt/xgw/lib")
DAY = 86400.0
HOUR = 3600.0
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
HOST = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")
NOT_TUNNEL = ("REACHABLE", "CLOSED", "UNTESTED")
LISTS = ("igareck", "mahdibland")
CAPS = {0: "chown", 1: "dac_override", 2: "dac_read_search", 3: "fowner", 4: "fsetid",
        5: "kill", 6: "setgid", 7: "setuid", 8: "setpcap", 10: "net_bind_service",
        12: "net_admin", 13: "net_raw", 16: "sys_module", 19: "sys_ptrace", 21: "sys_admin"}
RANK = {"guarded": 1, "connecting": 2, "up": 3}
LINKS = ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://", "tuic://")


def run(argv):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, type(exc).__name__
    return done.returncode, done.stdout


def show(unit, prop):
    return run(["systemctl", "show", "-p", prop, "--value", unit])[1].strip()


def xgw():
    sys.path.insert(0, LIB)
    from xgw import config
    from xgw.paths import Paths

    paths = Paths.from_env()
    return config.load(paths.config_file)[0], paths


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        print(f"{Path(path).name} не читается: {type(exc).__name__}")
        sys.exit(0)


def perm(path):
    return oct(path.stat().st_mode & 0o777)[2:] if path.exists() else "нет"


def clean(text, limit=60):
    return HOST.sub("<host>", IPV4.sub("<ip>", str(text)))[:limit]


def records(paths, since=0.0):
    data = read_json(paths.var / "freepool" / "candidates.json") or {}
    found = {key: value for key, value in data.items()
             if not key.startswith("_") and isinstance(value, dict)
             and float(value.get("checked_at") or 0) >= since}
    return found, data


def counted(items):
    found = {}
    for item in items:
        found[item] = found.get(item, 0) + 1
    return ", ".join(f"{name} {count}" for name, count in sorted(found.items())) or "—"


def secret_of(entry):
    users = entry.get("users") if isinstance(entry.get("users"), list) else []
    first = users[0] if users and isinstance(users[0], dict) else {}
    return str(first.get("id") or first.get("password") or entry.get("id")
               or entry.get("password") or "")


def xray_ids(outbound):
    """(адрес, порт, ключ) каждого сервера исходящего Xray: сравнение целиком, не по адресу."""
    settings = outbound.get("settings") if isinstance(outbound, dict) else None
    if not isinstance(settings, dict):
        return []
    entries = [*(settings.get("vnext") or []), *(settings.get("servers") or []), settings]
    return [(entry["address"].lower(), str(entry.get("port") or ""), secret_of(entry))
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("address"), str)
            and entry["address"]]


def box_ids(items):
    return [(str(item["server"]).lower(), str(item.get("server_port") or ""),
             str(item.get("password") or item.get("uuid") or ""))
            for item in items if isinstance(item, dict) and item.get("server")]


def spent(data, key, now):
    items = (data.get(key) or {}).get("items") or []
    return sum(int(item[1]) for item in items
               if isinstance(item, list) and now - float(item[0]) < DAY) / 1048576


def caps(value):
    try:
        number = int(value, 16)
    except ValueError:
        return "?"
    return ",".join(CAPS.get(bit, f"bit{bit}") for bit in range(64) if number >> bit & 1) or "нет"


def proc_status(pid):
    fields = {}
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            key, _sep, value = line.partition(":")
            fields[key] = value.strip()
    except OSError:
        pass
    return fields


def account(uid, group=False):
    import grp
    import pwd

    try:
        return grp.getgrgid(int(uid)).gr_name if group else pwd.getpwuid(int(uid)).pw_name
    except (KeyError, ValueError):
        return str(uid)


def netns(pid):
    try:
        return os.readlink(f"/proc/{pid}/ns/net")
    except OSError:
        return ""


def describe(path):
    try:
        info = path.stat()
    except OSError:
        return "нет"
    return (f"{oct(info.st_mode & 0o777)[2:]} {account(info.st_uid)}:"
            f"{account(info.st_gid, group=True)}")


def routes(pid):
    default, single = "нет", 0
    try:
        rows = Path(f"/proc/{pid}/net/route").read_text(encoding="ascii").splitlines()[1:]
    except OSError:
        return "маршруты внутри: не прочитаны"
    for row in rows:
        cols = row.split()
        if len(cols) < 8:
            continue
        if cols[1] == "00000000" and cols[7] == "00000000":
            default = cols[0]
        elif cols[7] == "FFFFFFFF":
            single += 1
    return f"маршрут по умолчанию внутри: {default}; маршрутов к одному адресу: {single}"


def workers(pid, ns):
    found = []
    for entry in Path("/proc").iterdir() if ns else ():
        if not entry.name.isdigit() or entry.name == pid or netns(entry.name) != ns:
            continue
        info = proc_status(entry.name)
        if info.get("Name", "").startswith("python"):
            continue  # проба самопроверки охраны или проверка изнутри
        owner = account((info.get("Uid") or "?").split()[0])
        found.append(f"{info.get('Name', '?')} от {owner}, возможности "
                     f"{caps(info.get('CapEff', '0'))}, NoNewPrivs {info.get('NoNewPrivs', '?')}")
    return "работники: " + ("; ".join(sorted(found)) or "нет")


def worker_files(pid):
    tmp = Path(f"/proc/{pid}/root/tmp")
    lines = []
    for name, files in (("xgw-ovpn", ("client.conf", "auth")), ("xgw-socks", ("socks.json",))):
        items = [describe(tmp / name)] + [f"{item} {describe(tmp / name / item)}"
                                          for item in files if (tmp / name / item).exists()]
        lines.append(f"{name}: " + "; ".join(items))
    return lines


def snapshot(paths, gen, host_ns):
    unit = f"xgw-fp@{gen}.service"
    _code, props = run(["systemctl", "show", unit, "-p", "PrivateNetwork", "-p", "PrivateTmp",
                        "-p", "NoNewPrivileges", "-p", "ProtectSystem", "-p", "KillMode",
                        "-p", "CapabilityBoundingSet"])
    lines = ["служба: " + "; ".join(sorted(line.strip() for line in props.splitlines()
                                           if line.strip()))]
    pid = show(unit, "MainPID")
    directory = paths.run / "fp" / gen
    manifest = read_json(directory / "manifest.json") or {}
    if not pid.isdigit() or pid == "0":
        return lines + ["агент: не найден"]
    status = proc_status(pid)
    ns = netns(pid)
    lines.append(f"агент: пользователь {account((status.get('Uid') or '?').split()[0])}; "
                 f"возможности {caps(status.get('CapEff', '0'))}; NoNewPrivs "
                 f"{status.get('NoNewPrivs', '?')}; своё пространство имён: "
                 f"{'да' if ns and ns != host_ns else 'НЕТ'}")
    try:
        names = sorted(line.split(":")[0].strip() for line in
                       Path(f"/proc/{pid}/net/dev").read_text(encoding="ascii").splitlines()[2:])
    except OSError:
        names = []
    lines.append("интерфейсы внутри: " + (", ".join(names) or "не прочитаны"))
    lines.append(routes(pid))
    lines.append(workers(pid, ns))
    lines.extend(worker_files(pid))
    lines.append(f"задание: {describe(directory / 'manifest.json')}; состояние: "
                 f"{describe(directory / 'state.json')}")
    try:
        state_text = (directory / "state.json").read_text(encoding="utf-8")
    except OSError:
        state_text = ""
    words = [word for word in [str(manifest.get("socks_pass") or ""),
                               *str(manifest.get("auth") or "").splitlines()[1:2]]
             if len(word) >= 6]
    lines.append(f"секреты задания в state.json: "
                 f"{'ЕСТЬ' if any(word in state_text for word in words) else 'нет'} "
                 f"(проверено {len(words)})")
    index = manifest.get("index")
    _code, peers = run(["nft", "list", "set", "ip", "xgw", "fp_peers"])
    match = re.search(r"elements = \{([^}]*)\}", peers, re.S)
    count = len([item for item in match.group(1).split(",") if item.strip()]) if match else 0
    veth = Path(f"/sys/class/net/fpv{index}").exists()
    lines.append(f"veth на хосте: {'есть' if veth else 'нет'}; элементов fp_peers: {count}")
    return lines


def after_up(gen):
    pid = show(f"xgw-fp@{gen}.service", "MainPID")
    if not pid.isdigit() or pid == "0":
        return ["агент: не найден"]
    ns = netns(pid)
    return [routes(pid), workers(pid, ns), *worker_files(pid)[1:]]


def tunnel_line(stats):
    try:
        return (f"в туннель {int(stats['tx_packets'])} пакетов, из туннеля "
                f"{int(stats['rx_packets'])} пакетов")
    except (KeyError, TypeError, ValueError):
        return "—"


def openvpn_processes():
    mine = other = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if not command or not command[0].endswith(b"openvpn"):
            continue
        if b"/tmp/xgw-ovpn/client.conf" in command:
            mine += 1
        else:
            other += 1
    return mine, other


def diagnosis(record):
    text = str(record.get("diagnosis") or "")
    tcp = re.search(r"TCP Cloudflare:443 — ([A-Z_]+|—)", text)
    back = re.search(r"из туннеля (\d+) пакетов", text)
    guard = re.search(r"охрана после подъёма: OpenVPN (\d+), работник (\d+)", text)
    link = re.search(r"канал к серверу: от сервера \d+ пакетов \((\d+) КБ\)", text)
    return (tcp.group(1) if tcp else "—", re.findall(r"DNS (\S+) — ([A-Z_]+|—)", text),
            int(back.group(1)) if back else None,
            bool(guard and (int(guard.group(1)) or int(guard.group(2)))),
            int(link.group(1)) if link else None)


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
    _code, text = run(["systemctl", "list-units", "--all", "--plain", "--no-legend",
                       "xgw-fp@*.service"])
    states = [line.split()[2] for line in text.splitlines() if len(line.split()) > 2]
    mine, other = openvpn_processes()
    load = show("openvpn.service", "LoadState")
    print(f"поколений xgw-fp@ сейчас: {len(states)} ({counted(states)}); процессов openvpn XGW: "
          f"{mine}; других openvpn: {other}; openvpn.service: "
          + ("нет" if load in ("", "not-found") else show("openvpn.service", "ActiveState")))
elif mode == "backend":
    cfg, paths = xgw()
    code, version = run(["dpkg-query", "-W", "-f", "${Version}", "openvpn"])
    print(f"пакет openvpn: {version.strip() if code == 0 and version.strip() else 'нет'}; "
          f"/usr/sbin/openvpn: {'есть' if Path('/usr/sbin/openvpn').exists() else 'нет'}; "
          f"sing-box для проверок: {'есть' if paths.singbox_bin.exists() else 'нет'}")
    for name in ("xgw-ovpn", "xgw-fps"):
        code, line = run(["getent", "passwd", name])
        fields = line.strip().split(":")
        if code != 0 or len(fields) < 7:
            print(f"пользователь {name}: нет")
            continue
        system = fields[2].isdigit() and int(fields[2]) < 1000
        print(f"пользователь {name}: есть, {'системный' if system else 'НЕ системный'}, "
              f"оболочка {fields[6]}")
    unit = paths.systemd_dir / "xgw-fp@.service"
    print(f"служба xgw-fp@.service: {'есть' if unit.exists() else 'нет'}")
    try:
        forward = Path("/proc/sys/net/ipv4/ip_forward").read_text(encoding="ascii").strip()
    except OSError:
        forward = "?"
    print(f"пересылка IPv4: {forward}")
    code, text = run(["nft", "list", "set", "ip", "xgw", "fp_peers"])
    if code != 0:
        print("набор fp_peers: нет")
    else:
        match = re.search(r"elements = \{([^}]*)\}", text, re.S)
        count = len([item for item in match.group(1).split(",") if item.strip()]) if match else 0
        print(f"набор fp_peers: есть; элементов {count}")
    veth = [entry.name for entry in Path("/sys/class/net").iterdir()
            if re.fullmatch(r"fpv\d+", entry.name)]
    base = paths.run / "fp"
    dirs = [entry for entry in base.iterdir() if entry.is_dir()] if base.exists() else []
    print(f"veth fpv сейчас: {len(veth)}; каталогов поколений: {len(dirs)}; peers.json: "
          f"{perm(base / 'peers.json')}")
    code, text = run(["ufw", "status"])
    if code != 0 or not text.strip().lower().startswith("status: active"):
        print("ufw: выключен или не установлен")
    else:
        print(f"ufw: включён; правило fpv+: {'есть' if 'fpv+' in text else 'НЕТ'}")
    from xgw.freepool import backend
    from xgw.net import cmd

    problem = backend.unavailable(paths, cmd.run)
    print("бэкенд OpenVPN: " + ("годится" if not problem else problem))
    print(f"срок подготовки поколения у демона: {backend.UP_MARGIN:.0f} с сверх срока агента")
elif mode == "pool":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    age = int(time.time() - float(status["updated"])) if status.get("updated") else None
    print(f"status.json: {'нет' if age is None else f'{age} с назад'}")
    pool = status.get("free_pool")
    if not isinstance(pool, dict):
        print("free_pool в состоянии: нет")
        sys.exit(0)
    regions = ", ".join(f"{name} {count}" for name, count in
                        sorted((pool.get("by_region") or {}).items())) or "—"
    sources = ", ".join(f"{name} {count}" for name, count in
                        sorted((pool.get("ready_by_source") or {}).items())) or "—"
    print(f"free_pool в состоянии: режим {pool.get('mode')}, регион {pool.get('region')}; "
          f"найдено {pool.get('found')} (из списков GitHub {pool.get('lists')}, из них только "
          f"sing-box {pool.get('lists_singbox')}; Outline {pool.get('outline')}; OpenVPN "
          f"{pool.get('openvpn')}); проверено {pool.get('checked')}, пригодно {pool.get('ready')} "
          f"({regions}); пригодные по источникам: {sources}")
    print(f"трафик проверок за сутки: каталоги {pool.get('spent_mb')} из {pool.get('budget_mb')}"
          f" МБ; серверы списков {pool.get('lists_spent_mb')} МБ")
    problem = pool.get("openvpn_backend") or ""
    failures = ", ".join(f"{code} {count}" for code, count in
                         sorted((pool.get("tunnel_failures") or {}).items())) or "—"
    print(f"OpenVPN туннелем: {'годится' if not problem else 'недоступно — ' + problem}; "
          f"поднялось {pool.get('tunnels_up')}; отказы: {failures}; подключений за час "
          f"{pool.get('handshakes_hour')}, за сутки {pool.get('handshakes_day')} из "
          f"{pool.get('handshakes_day_limit', '?')}")
    free_at = float(pool.get("handshakes_free_at") or 0)
    print("суточный предел подключений: " + (
        "занят, освободится " + time.strftime("%d.%m %H:%M", time.localtime(free_at))
        if free_at else "не занят"))
    flow = pool.get("traffic")
    if isinstance(flow, dict):
        print(f"через пул: устройства {', '.join(flow.get('devices') or []) or '—'}; серверов в "
              f"pool {flow.get('members')}, живых {flow.get('alive')}; закрыто: "
              f"{'ДА' if flow.get('closed') else 'нет'}; страна {flow.get('country') or '—'}; "
              f"задержка {flow.get('delay_ms')} мс")
    else:
        print("через пул: устройств нет")
    now = time.time()
    for source in pool.get("sources") or []:
        when = source.get("retrieved_at")
        got = f"{int((now - float(when)) // 60)} мин назад" if when else "нет"
        print(f"  {source.get('id')}: {source.get('status')}; список — {got}; вариантов "
              f"{source.get('variants')}; устарел: {'да' if source.get('stale') else 'нет'}")
elif mode == "quota":
    cfg, paths = xgw()
    _found, data = records(paths)
    now = time.time()
    limit = int(cfg.free_pool.handshakes_per_day)
    stamps = sorted(float(item[0]) for item in (data.get("_handshakes") or {}).get("items") or []
                    if isinstance(item, list) and len(item) == 2 and now - float(item[0]) < DAY)
    free = max(limit - len(stamps), 0)
    if limit < 6:
        when = f"никогда: предел {limit} меньше 6"
    elif free >= 6:
        when = "сейчас"
    else:
        when = time.strftime("%d.%m %H:%M", time.localtime(stamps[5 - free] + DAY))
    print(f"подключений OpenVPN за сутки: {len(stamps)} из {limit}; за час: "
          f"{sum(1 for stamp in stamps if now - stamp < HOUR)}; свободно сейчас: {free}; "
          f"шесть свободны: {when}")
elif mode == "admitted":
    cfg, paths = xgw()
    from xgw.freepool import traffic as fptraffic

    found = fptraffic.admitted(cfg, paths, time.time())
    print(f"допущено к трафику: {len(found)} (OK {sum(1 for i in found if i.verdict == 'OK')}, "
          f"SLOW {sum(1 for i in found if i.verdict == 'SLOW')}); страны: "
          f"{counted(i.node.country.upper() for i in found)}; источники: "
          f"{counted(i.variant.provider for i in found)}; ядро: "
          f"{counted(i.variant.backend for i in found)}")
    speeds = sorted((item.speed for item in found), reverse=True)[:5]
    print("скорость проверки у лучших: " + (", ".join(f"{value * 8 / 1e6:.1f}" for value in speeds)
                                            + " Мбит/с" if speeds else "—"))
elif mode == "route":
    cfg, paths = xgw()
    from xgw.freepool import traffic as fptraffic

    devices = fptraffic.pool_devices(cfg)
    work = read_json(paths.xray_config_file) or {}
    routing = work.get("routing") or {}
    rules = [rule for rule in routing.get("rules") or [] if isinstance(rule, dict)]
    print(f"режим пула: {cfg.free_pool.mode}; устройств через пул в настройках: {len(devices)} "
          f"({', '.join(devices) or '—'})")
    for ip in devices:
        index = next((i for i, rule in enumerate(rules) if ip in (rule.get("source") or [])),
                     None)
        if index is None:
            print(f"  {ip}: правила в рабочем конфиге НЕТ")
            continue
        rule = rules[index]
        target = (f"балансировщик {rule['balancerTag']}" if rule.get("balancerTag")
                  else f"выход {rule.get('outboundTag')}")
        direct = any("domain:ru" in (item.get("domain") or []) for item in rules[:index])
        print(f"  {ip}: правило → {target}; российские домены напрямую раньше него: "
              f"{'да' if direct else 'НЕТ'}")
    balancers = {str(item.get("tag")): item for item in routing.get("balancers") or []
                 if isinstance(item, dict)}
    found = balancers.get("pool")
    print("балансировщик pool: " + (
        f"есть; selector {found.get('selector')}; стратегия "
        f"{(found.get('strategy') or {}).get('type')}; fallbackTag {found.get('fallbackTag')}"
        if found else "нет"))
    print(f"балансировщик auto: selector {(balancers.get('auto') or {}).get('selector')}")
    print("пробы ядра (subjectSelector): "
          f"{(work.get('burstObservatory') or {}).get('subjectSelector')}")
    own = [rule for rule in rules
           if rule.get("source") and not set(rule.get("source") or []) & set(devices)]
    print(f"правил «свой сервер устройства» (Ф4): {len(own)}")
elif mode == "checks":
    _cfg, paths = xgw()
    since = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    found, data = records(paths, since)
    total = len(records(paths)[0])
    now = time.time()
    lists = [record for record in found.values() if record.get("provider") in LISTS]
    catalogs = [record for record in found.values() if record.get("provider") not in LISTS]
    recent = [record for record in found.values()
              if now - float(record.get("checked_at") or 0) < 1800]
    print(f"проверок с начала прогона: {len(found)} (каталоги {len(catalogs)}, списки GitHub "
          f"{len(lists)}; всего записей {total}); за последние 30 минут: каталоги "
          f"{sum(1 for record in recent if record.get('provider') not in LISTS)}, списки "
          f"{sum(1 for record in recent if record.get('provider') in LISTS)}")
    print("каталоги: " + counted(f"{record.get('backend')} {record.get('verdict')}"
                                 for record in catalogs))
    attempts = [record for record in catalogs if record.get("backend") == "openvpn"
                and record.get("verdict") not in NOT_TUNNEL]
    up = [record for record in attempts if record.get("tunnel_up")]
    seconds = sorted(float(record.get("connect_seconds") or 0) for record in up
                     if float(record.get("connect_seconds") or 0) > 0)
    print(f"OpenVPN туннелем: попыток {len(attempts)}, поднялось {len(up)}"
          + (f"; подключение — от {seconds[0]:.1f} до {seconds[-1]:.1f} с" if seconds else ""))
    for provider in sorted({str(record.get("provider")) for record in attempts}):
        mine = [record for record in attempts if record.get("provider") == provider]
        print(f"  {provider}: попыток {len(mine)}, поднялось "
              f"{sum(1 for record in mine if record.get('tunnel_up'))}")
    print("итоги через поднятый туннель: " + counted(str(record.get("verdict")) for record in up))
    print("отказы без туннеля: " + counted(str(record.get("verdict")) for record in attempts
                                           if not record.get("tunnel_up")))
    seen = [diagnosis(record) for record in up]
    print("изнутри, TCP Cloudflare:443: " + counted(item[0] for item in seen))
    print("изнутри, DNS: " + counted(f"{who} {result}" for item in seen
                                     for who, result in item[1]))
    print("из туннеля вернулось: " + counted(
        "нет записи" if item[2] is None else "0 пакетов" if item[2] == 0 else "больше 0"
        for item in seen))
    print("охрана после подъёма отбила у OpenVPN или работника: "
          f"{sum(1 for item in seen if item[3])} из {len(seen)}")
    print("канал к серверу после подъёма, от сервера: " + counted(
        "нет записи" if item[4] is None else "до 8 КБ" if item[4] < 8 else "8 КБ и больше"
        for item in seen))
    broken = sum(1 for record, item in zip(up, seen, strict=True)
                 if item[0] == "OPEN" and record.get("verdict") not in ("OK", "SLOW"))
    print(f"туннель пропускает TCP, а проба через посредника — нет: {broken}")
    print("причины «не проверено» у OpenVPN: " + counted(
        clean(record.get("error") or "—").split(":")[0][:50] for record in catalogs
        if record.get("backend") == "openvpn" and record.get("verdict") == "UNTESTED"))
    biggest = max((int(record.get("bytes") or 0) for record in attempts), default=0)
    print(f"трафик одной проверки туннелем, наибольший: {biggest / 1048576:.1f} МБ")
    items = [item for item in (data.get("_handshakes") or {}).get("items") or []
             if isinstance(item, list) and len(item) == 2]
    hour = [item for item in items if now - float(item[0]) < HOUR]
    day = [item for item in items if now - float(item[0]) < DAY]
    print(f"подключений за час: {len(hour)} ({counted(str(item[1]) for item in hour)}); "
          f"за сутки: {len(day)}")
    print("списки GitHub: " + counted(f"{record.get('provider')} {record.get('backend')} "
                                      f"{record.get('verdict')}" for record in lists))
    print("страны выхода работающих серверов списков: " + counted(
        str(record.get("egress_country") or "?") for record in lists
        if record.get("verdict") in ("OK", "SLOW")))
    print("причины «не проверено» у серверов списков: " + counted(
        clean(record.get("error") or "—", 100) for record in lists
        if record.get("verdict") == "UNTESTED"))
    largest = max((int(record.get("bytes") or 0) for record in lists), default=0)
    print(f"трафик одной проверки сервера списка, наибольший: {largest / 1048576:.2f} МБ")
    print("страны выхода пригодных (все источники): " + counted(
        str(record.get("egress_country") or "?") for record in found.values()
        if record.get("verdict") in ("OK", "SLOW")))
    print(f"трафик проверок за сутки: каталоги {spent(data, '_ledger', now):.1f} МБ; серверы "
          f"списков {spent(data, '_list_ledger', now):.1f} МБ")
elif mode == "lists":
    cfg, paths = xgw()
    from xgw.fetch import is_bogon
    from xgw.freepool.store import PoolStore

    store = PoolStore(paths)
    for provider in LISTS:
        snap = store.snapshot(provider)
        attempt = snap.get("last_attempt") or {}
        variants = store.variants(provider)
        print(f"{provider}: {attempt.get('status') or 'нет'}; вариантов {len(variants)}; "
              f"отклонено {attempt.get('rejected', 0)}; в providers: "
              f"{'да' if provider in cfg.free_pool.providers else 'НЕТ'}")
        print("  ядро и протокол: " + counted(f"{variant.backend} {variant.protocol}"
                                              for variant in variants))
        print("  страны по флагу: " + counted(variant.country_hint or "?" for variant in variants))
        reasons = attempt.get("rejections") or {}
        print("  причины отказа: " + (", ".join(f"{clean(reason)} {count}" for reason, count in
                                                reasons.items()) or "—"))
        literal = [variant for variant in variants if variant.address]
        print(f"  адрес — IPv4 {len(literal)}, имя {len(variants) - len(literal)}; служебных IPv4: "
              f"{sum(1 for variant in literal if is_bogon(variant.address))}")
elif mode == "files":
    cfg, paths = xgw()
    base = paths.var / "freepool"
    snapshots = sorted((base / "snapshots").glob("*.json")) if (base / "snapshots").exists() \
        else []
    print(f"каталог freepool: {perm(base)}; secrets.json: {perm(base / 'secrets.json')}; "
          f"candidates.json: {perm(base / 'candidates.json')}; снимков списков: "
          f"{len(snapshots)} ({counted(path.name.split('.')[0] for path in snapshots)}); права "
          f"снимков: {counted(perm(path) for path in snapshots)}")
    profiles = sorted((base / "profiles").glob("*.ovpn")) if (base / "profiles").exists() \
        else []
    print(f"профилей VPNBook: {len(profiles)}; каталог profiles: {perm(base / 'profiles')}; "
          f"права профилей: {counted(perm(path) for path in profiles)}")
    from xgw.freepool.store import PoolStore

    store = PoolStore(paths)
    current = {variant.variant_id for provider in cfg.free_pool.providers
               for variant in store.variants(provider)}
    found, _data = records(paths)
    file = base / "candidates.json"
    size = file.stat().st_size // 1024 if file.exists() else 0
    print(f"записей проверок: {len(found)}; без варианта в снимках: "
          f"{sum(1 for key in found if key not in current)}; размер candidates.json: {size} КБ")
    run_dir = paths.run / "freepool"
    left = len(list(run_dir.iterdir())) if run_dir.exists() else 0
    pattern = str(run_dir / "pool-").encode()
    running = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        running += pattern in command
    print(f"временных каталогов проверок: {left}; временных Xray и sing-box сейчас: {running}")
    from xgw import managed

    panel = read_json(managed.path_for(paths.config_file)) or {}
    print(f"panel.json: режим пула: {panel.get('free_pool_mode') or '—'}")
elif mode == "config":
    cfg, paths = xgw()
    from xgw.fetch import is_bogon
    from xgw.freepool.store import PoolStore

    store = PoolStore(paths)
    variants = [variant for provider in cfg.free_pool.providers
                for variant in store.variants(provider)]
    whole = {ident for variant in variants
             for ident in [*xray_ids(variant.outbound or {}),
                           *box_ids([(variant.singbox or {}).get("main") or {}])]}
    work = read_json(paths.xray_config_file) or {}
    outbounds = [item for item in work.get("outbounds") or [] if isinstance(item, dict)]
    sub = [ident for item in outbounds
           if str(item.get("tag") or "").startswith(("proxy-", "spare-"))
           for ident in xray_ids(item)]
    pooled = [item for item in outbounds if str(item.get("tag") or "").startswith("pool-")]
    bridged = [item for item in pooled
               if any(ident[0] == "127.0.0.1" for ident in xray_ids(item))]
    direct = [ident for item in pooled if item not in bridged for ident in xray_ids(item)]
    public = sum(1 for ident in direct if IPV4.fullmatch(ident[0]) and not is_bogon(ident[0]))
    box = read_json(paths.singbox_config_file) or {}
    servers = box_ids(item for key in ("outbounds", "endpoints") for item in box.get(key) or [])
    print(f"выходов подписки (proxy-/spare-): {len(sub)}; из них вариантов бесплатного пула "
          f"целиком (адрес, порт, ключ): {sum(1 for item in sub if item in whole)}; к работникам "
          f"OpenVPN: {sum(1 for item in sub if item[0].startswith('10.250.'))}")
    print(f"выходов бесплатного пула (pool-*): {len(pooled)}; напрямую {len(pooled) - len(bridged)}"
          f", мостом sing-box {len(bridged)}; у прямых адрес — публичный IPv4: {public} из "
          f"{len(direct)}; вариантов пула целиком: {sum(1 for item in direct if item in whole)} "
          f"из {len(direct)}")
    print(f"серверов в конфиге sing-box: {len(servers)}, из них вариантов пула целиком: "
          f"{sum(1 for item in servers if item in whole)}")
elif mode == "xstats":
    cfg, paths = xgw()
    from xgw.xraycore import metrics

    try:
        data = metrics.fetch_metrics(cfg.xray.metrics_port)
    except Exception as exc:
        print(f"метрики Xray не прочитаны: {type(exc).__name__}")
        sys.exit(0)
    outbound = (data.get("stats") or {}).get("outbound") or {}

    def total(counters):
        return sum(value for value in (counters or {}).values()
                   if isinstance(value, int) and not isinstance(value, bool))

    pool = {str(tag): total(item) for tag, item in outbound.items()
            if str(tag).startswith("pool-")}
    subscription = sum(total(item) for tag, item in outbound.items()
                       if str(tag).startswith(("proxy-", "spare-")))
    observatory = metrics.parse_observatory(data)
    tags = sorted(tag for tag in observatory if tag.startswith("pool-"))
    flow = ((read_json(paths.status_file) or {}).get("free_pool") or {}).get("traffic") or {}
    pinned = str(flow.get("tag") or "")
    mb = 1048576
    print(f"трафик с запуска Xray: через бесплатный пул {sum(pool.values()) / mb:.1f} МБ (у "
          f"закреплённого {pool.get(pinned, 0) / mb:.1f} МБ), через подписку "
          f"{subscription / mb:.1f} МБ, напрямую {total(outbound.get('direct')) / mb:.1f} МБ")
    print(f"выходов pool-* под пробами ядра: {len(tags)}, живых: "
          f"{sum(1 for tag in tags if observatory[tag].get('alive'))}; закреплён: "
          f"{'да' if pinned else 'нет'}"
          + (" (его тега нет среди проб!)" if pinned and pinned not in tags else ""))
elif mode == "xray":
    print(f"Xray: запущен {show('xgw-xray.service', 'ExecMainStartTimestamp') or '?'}; "
          f"NRestarts {show('xgw-xray.service', 'NRestarts') or '?'}")
elif mode == "leak":
    _cfg, paths = xgw()
    secrets = read_json(paths.var / "freepool" / "secrets.json") or {}
    words = [str(value) for record in (secrets.get("shared") or {}).values()
             if isinstance(record, dict) for key, value in record.items()
             if key == "password" and value]
    lines = sys.stdin.read().splitlines()
    hits = sum(1 for line in lines if any(word in line for word in words))
    raw = sum(1 for line in lines if any(link in line for link in LINKS))
    pushed = sum(1 for line in lines if "PUSH_REPLY" in line or "auth-user-pass" in line)
    print(f"паролей источников известно: {len(words)}; строк журнала: {len(lines)}; строк с "
          f"паролем: {hits}; строк со ссылкой сервера: {raw}; строк OpenVPN с настройками: "
          f"{pushed}")
elif mode == "digest":
    cfg, paths = xgw()
    from xgw.net.capture import capture_for

    capture = capture_for(cfg, paths)
    saved = capture._state().get("tables")
    current = capture._tables_digest()
    verdict = ("не запомнен" if saved is None else "не прочитан" if current is None
               else "совпадает" if current == saved else "НЕ совпадает")
    print(f"отпечаток таблиц: {verdict}; правила на месте (loaded): {capture.loaded()}; "
          f"время: {time.strftime('%H:%M:%S')}")
elif mode == "subs":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    errors = status.get("sub_errors") or {}
    texts = [str((item or {}).get("error") or "") for item in errors.values()]
    data = read_json(paths.var / "inventory.json") or {}
    print(f"подписок с ошибкой: {sum(1 for text in texts if text)}; серверов в списке: "
          f"{len(data.get('servers') or [])}")
elif mode == "fwd":
    code, text = run(["nft", "list", "chain", "ip", "xgw", "forward"])
    if code != 0:
        print("цепочка forward: нет")
        sys.exit(0)
    found = {}
    for line in text.splitlines():
        line = line.strip()
        packets = re.search(r"packets (\d+)", line)
        if '"fpv*"' not in line or packets is None:
            continue
        if "@fp_peers" in line:
            found["из fpv* к серверам пула"] = packets.group(1)
        elif line.startswith('iifname "fpv*"'):
            found["из fpv* — сброс"] = packets.group(1)
        elif line.startswith('oifname "fpv*"'):
            found["в fpv* — сброс"] = packets.group(1)
    print("; ".join(f"{name}: пакетов {count}" for name, count in found.items())
          or "правил пула в forward нет")
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, words in (
        ("VPN Gate: список получен", ("бесплатный пул: vpngate — SUCCESS",)),
        ("VPNBook: список получен", ("бесплатный пул: vpnbook — SUCCESS",
                                     "бесплатный пул: vpnbook — PARTIAL")),
        ("igareck: список получен", ("бесплатный пул: igareck — SUCCESS",
                                     "бесплатный пул: igareck — PARTIAL")),
        ("mahdibland: список получен", ("бесплатный пул: mahdibland — SUCCESS",
                                        "бесплатный пул: mahdibland — PARTIAL")),
        ("список получен через подписку", ("(через подписку), вариантов",)),
        ("список получен напрямую", ("(напрямую), вариантов",)),
        ("источник не ответил", ("прежний снимок остаётся",)),
        ("проверок серверов пула", ("бесплатный пул: проверка",)),
        ("из них OpenVPN", ("(openvpn, ",)),
        ("из них серверов списков", ("бесплатный пул: проверка igareck ",
                                     "бесплатный пул: проверка mahdibland ")),
        ("из них sing-box", ("(sing-box, ",)),
        ("с итогом изнутри туннеля", ("; изнутри: ",)),
        ("шаг пула не выполнен", ("бесплатный пул: шаг не выполнен",)),
        ("поколения прошлого запуска убраны", ("убраны поколения прошлого запуска",)),
        ("следы поколения не убраны", ("бесплатный пул: systemctl", "не убран из fp_peers",
                                       "peers.json не записан")),
        ("правила загружены заново", ("загружены заново",)),
        ("откат на last-good", ("last-good",)),
        ("пул: сервер для устройств выбран", ("freepool: бесплатный пул: устройства ",)),
        ("пул: у устройств закрыто", ("— у устройств ",)),
        ("пул: закрепление не удалось", ("сервер бесплатного пула не закреплён",)),
        ("применений через API", ("применено через API без перезапуска",)),
        ("применений с перезапуском Xray", ("применено с перезапуском Xray",)),
        ("Read-only file system", ("Read-only file system",)),
        ("Permission denied", ("Permission denied",)),
        ("Traceback", ("Traceback",)),
    ):
        print(f"{label}: {sum(1 for line in lines if any(word in line for word in words))}")
    ours = [line for line in lines if "бесплатный пул: состав серверов для устройств" in line
            or "бесплатный пул: обновление серверов для устройств" in line]
    print(f"сборок ради пула: {len(ours)}; из них с перезапуском Xray: "
          f"{sum(1 for line in ours if 'с перезапуском Xray' in line)}")
elif mode == "agentlog":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала поколений: {len(lines)}")
    guard = [line.split("охрана проверена: ", 1)[1] for line in lines
             if "охрана проверена: " in line]
    results = [item.split(" ", 1)[1] for text in guard for item in text.split(", ")
               if " " in item]
    print(f"самопроверок охраны: {len(guard)}; итоги: {counted(results)}")
    print(f"туннель поднят: {sum(1 for line in lines if 'туннель поднят, MTU' in line)}; снова "
          f"поднят: {sum(1 for line in lines if 'туннель снова поднят' in line)}; SOCKS-работник "
          f"готов: {sum(1 for line in lines if 'SOCKS-работник готов' in line)}")
    inner = [line.split("через туннель: ", 1)[1] for line in lines if "через туннель: " in line]
    print(f"проверок изнутри: {len(inner)}")
    for text in list(dict.fromkeys(clean(text, 160) for text in inner))[:8]:
        print(f"  изнутри: {text}")
    totals = [line.split("итог туннеля: ", 1)[1] for line in lines if "итог туннеля: " in line]
    print(f"итогов туннеля: {len(totals)}")
    for text in totals[:8]:
        print(f"  итог туннеля: {clean(text, 400)}")
    sent = [int(match.group(1)) for text in totals
            for match in [re.search(r"в туннель (\d+) пакетов", text)] if match]
    back = [int(match.group(1)) for text in totals
            for match in [re.search(r"из туннеля (\d+) пакетов", text)] if match]
    four = (r"OpenVPN (\d+), работник (\d+), ответы ядра (\d+), служебный IPv6 (\d+)")
    after = [tuple(int(value) for value in match.groups()) for text in totals
             for match in [re.search("охрана после подъёма: " + four, text)] if match]
    print(f"в туннель ушло 0 пакетов: {sum(1 for value in sent if value == 0)}; из туннеля "
          f"вернулось 0: {sum(1 for value in back if value == 0)}, больше 0: "
          f"{sum(1 for value in back if value > 0)}")
    print(f"после подъёма отбито у OpenVPN или работника больше 0: "
          f"{sum(1 for item in after if item[0] or item[1])}; ответы ядра всего: "
          f"{sum(item[2] for item in after)}; служебный IPv6 всего: "
          f"{sum(item[3] for item in after)}; итогов без счётчиков охраны: "
          f"{len(totals) - len(after)}")
    link = [(int(match.group(1)), int(match.group(2))) for text in totals for match in [
        re.search(r"канал к серверу после подъёма: от сервера (\d+) пакетов \((\d+) КБ\)",
                  text)] if match]
    print(f"канал к серверу после подъёма, от сервера: 0 пакетов — "
          f"{sum(1 for packets, _kb in link if packets == 0)}, до 8 КБ — "
          f"{sum(1 for packets, kb in link if packets and kb < 8)}, 8 КБ и больше — "
          f"{sum(1 for _packets, kb in link if kb >= 8)}; не прочитан — "
          f"{len(totals) - len(link)}")
    for text in totals[:8]:
        found = re.search(r"канал к серверу после подъёма: ([^;]*)", text)
        if found:
            print(f"  канал к серверу: {clean(found.group(1), 120)}")
    notices = [text.split("предупреждения OpenVPN: ", 1)[1] for text in totals
               if "предупреждения OpenVPN: " in text]
    print(f"итогов с предупреждениями OpenVPN: {len(notices)}")
    for text in list(dict.fromkeys(clean(item, 160) for text in notices
                                   for item in text.split(" | ")))[:6]:
        print(f"  предупреждение OpenVPN: {text}")
    failures = [match.groups() for line in lines for match in [re.search(
        r"поколение [0-9a-f]{10}: ([A-Z_]+)(?: \(по журналу OpenVPN: ([A-Z_]+)\))? — (.*)",
        line)] if match]
    print(f"отказы поколений: {counted(code for code, _orig, _text in failures)}")
    print("у GUARD_BLOCKED по журналу OpenVPN: " + counted(
        orig or "—" for code, orig, _text in failures if code == "GUARD_BLOCKED"))
    for text in list(dict.fromkeys(clean(text, 140) for code, _orig, text in failures
                                   if code == "SOCKS_FAILED"))[:5]:
        print(f"  SOCKS_FAILED: {text}")
    before = [tuple(int(value) for value in match.groups()) for line in lines
              for match in [re.search("охрана за подключение: " + four, line)] if match]
    print(f"охрана за подключение: строк {len(before)}; OpenVPN "
          f"{sum(item[0] for item in before)}, работник {sum(item[1] for item in before)}, "
          f"ответы ядра {sum(item[2] for item in before)}, служебный IPv6 "
          f"{sum(item[3] for item in before)}")
    own = [line for line in lines if "OpenVPN: " in line and "поколение " not in line
           and "итог туннеля: " not in line]
    evidence = [clean(line.split("OpenVPN: ", 1)[1], 160) for line in own]
    for text in list(dict.fromkeys(evidence))[:10]:
        print(f"  OpenVPN: {text}")
    outer = sum(1 for line in lines if line not in own and any(
        not address.startswith(("10.250.", "127.")) for address in IPV4.findall(line)))
    print(f"строк с внешним адресом: {outer}; Traceback: "
          f"{sum(1 for line in lines if 'Traceback' in line)}")
elif mode == "watch":
    _cfg, paths = xgw()
    from xgw.freepool import agent

    limit = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
    deadline = time.time() + limit
    host_ns = netns(1)
    seen = {}
    while time.time() < deadline:
        base = paths.run / "fp"
        for directory in sorted(base.iterdir()) if base.exists() else []:
            if not directory.is_dir() or not re.fullmatch(r"[0-9a-f]{10}", directory.name):
                continue
            try:
                state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state = {}
            info = seen.setdefault(directory.name, {"phases": [], "rank": 0, "full": [],
                                                    "up": [], "reason": "", "selftest": "—",
                                                    "inner": "", "tun": None, "was_up": False,
                                                    "after": "", "before": "",
                                                    "link": "", "notices": []})
            phase = str(state.get("phase") or "")
            if phase and (not info["phases"] or info["phases"][-1] != phase):
                info["phases"].append(phase)
            if state.get("reason"):
                info["reason"] = str(state["reason"])
                if state.get("openvpn_code") and state["openvpn_code"] != state["reason"]:
                    info["reason"] += f" (по журналу OpenVPN: {state['openvpn_code']})"
            if state.get("tunnel_at"):
                info["was_up"] = True
            if isinstance(state.get("refused_after_up"), dict):
                info["after"] = agent.guard_text(state["refused_after_up"])
            if isinstance(state.get("refused_before_up"), dict):
                info["before"] = agent.guard_text(state["refused_before_up"])
            if isinstance(state.get("link_after_up"), dict):
                info["link"] = agent.link_text(state["link_after_up"])
            if isinstance(state.get("notices"), list):
                info["notices"] = [clean(item, 160) for item in state["notices"]][:3]
            if isinstance(state.get("selftest"), dict):
                info["selftest"] = "пройдена" if state["selftest"].get("ok") else "НЕ пройдена"
            if state.get("inner"):
                info["inner"] = agent.inner_text(state["inner"])
            if isinstance(state.get("tun"), dict):
                info["tun"] = state["tun"]
            rank = RANK.get(phase, 0)
            if rank > info["rank"]:
                if rank <= 2 or not info["full"]:
                    info["full"] = snapshot(paths, directory.name, host_ns)
                if rank == 3:
                    info["up"] = after_up(directory.name)
                info["rank"] = rank
        time.sleep(0.5)
    up = sum(1 for info in seen.values() if "up" in info["phases"])
    was = sum(1 for info in seen.values() if info["was_up"])
    print(f"поколений увидено: {len(seen)}; дошло до фазы up: {up}; туннель поднимался: {was}")
    for number, info in enumerate(seen.values(), 1):
        print(f"поколение {number}: фазы {' → '.join(info['phases']) or '—'}; самопроверка "
              f"{info['selftest']}; причина отказа: {info['reason'] or '—'}")
        print(f"  туннель поднимался: {'да' if info['was_up'] else 'нет'}")
        for line in info["full"]:
            print(f"  {line}")
        for line in info["up"]:
            print(f"  после подъёма: {line}")
        if info["inner"]:
            print(f"  изнутри: {clean(info['inner'], 200)}")
        if info["tun"] is not None:
            print(f"  fpt0 (последнее): {tunnel_line(info['tun'])}")
        if info["after"]:
            print(f"  охрана после подъёма: {info['after']}")
        if info["link"]:
            print(f"  канал к серверу после подъёма: {info['link']}")
        for text in info["notices"]:
            print(f"  предупреждение OpenVPN: {text}")
        if info["before"]:
            print(f"  охрана за подключение: {info['before']}")
else:
    print("режим: units | backend | pool | quota | admitted | route | checks | lists | files | "
          "config | xstats | xray | leak | digest | subs | fwd | log | agentlog | watch")
EOF
python3 -c "import hashlib;d=open('fpb1check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул|^Через бесплатные' | tee before.txt; for m in units files digest subs xray; do sudo python3 -I fpb1check.py $m; done | tee state-before.txt; sudo journalctl -u xgw --since "60 min ago" --no-pager | sudo python3 -I fpb1check.py log | tee log-before.txt
```

Ожидается:
- `09bcef4814649a96`;
- `Состояние: …`, `Перехват: включён …`, строки `Xray …` и `sing-box …` — записать как есть;
- четыре службы `active`; «поколений xgw-fp@ сейчас: 0 (—); процессов openvpn XGW: 0; …» —
  записать;
- «каталог freepool: 700; …; права снимков: 600 …»; «panel.json: режим пула: …» — записать;
  «отпечаток таблиц: совпадает; правила на месте (loaded): True»; «подписок с ошибкой: …;
  серверов в списке: …» — записать; «Xray: запущен …; NRestarts …» — записать;
- счётчики журнала — записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать и продолжить.

Шаг 1.3. Только если в `state-before.txt` — «panel.json: режим пула: observe» (наблюдение
осталось включённым с прошлого прогона); иначе — пропустить, в отчёте «не нужен». Выключить
командой (пункт 2 согласия):

```bash
cd "$HOME/xgw-fpb1" && sudo xgw pool mode off 2>&1 | tee off-before.txt; sleep 180; for m in pool units files; do sudo python3 -I fpb1check.py $m; done | tee off-before-state.txt
```

Ожидается: «Бесплатный пул выключен. Демон применит режим на ближайшем шаге»; «free_pool в
состоянии: нет»; «поколений xgw-fp@ сейчас: 0»; «panel.json: режим пула: off». Записать.

Если не так: «free_pool в состоянии: режим …» — подождать 2 минуты и повторить вторую часть
блока; снова так — **дефект «наблюдение не выключается»**, продолжить.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def admitted' src/xgw/freepool/traffic.py && grep -q 'POOL_BALANCER = "pool"' src/xgw/generator/builder.py && grep -q 'def _pool_step' src/xgw/daemon.py && grep -q '"fragment", "pool-")' src/xgw/generator/diff.py && grep -q 'POOL_ROUTE = "pool"' src/xgw/managed.py && grep -q 'handshakes_per_day: int = 96' src/xgw/config.py && echo "правка в коде: есть"; cd "$HOME/xgw-fpb1"
```

Ожидается: «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. Внешний интерфейс (WAN), его
соединение и DHCP она не трогает; интернет дома пропадёт на несколько секунд, пока
перезапускаются службы XGW. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fpb1/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fpb1/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'пакеты:|пользователь xgw-|ufw:|перезапущен|Xray запущен' "$HOME/xgw-fpb1/install.txt"; cd "$HOME/xgw-fpb1"
```

Ожидается: «код 0», «демон xgw запущен», «Xray запущен: участников …»; строк «пакеты:» и
«пользователь xgw-…» нет (уже стоят). Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке, пул выключен, устройств через пул нет:

```bash
sleep 120; cd "$HOME/xgw-fpb1" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул|^Через бесплатные' | tee after-install.txt; for m in units digest pool route xray; do sudo python3 -I fpb1check.py $m; done | tee -a after-install.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул|Устройства через|Конфиг|^Итог' | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpb1check.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки; строк `Бесплатный
  пул` и `Через бесплатные` нет; четыре службы `active`;
- «отпечаток таблиц: совпадает; … True»; «free_pool в состоянии: нет»;
- режим `route`: «режим пула: off; устройств через пул в настройках: 0 (—)»; «балансировщик
  pool: нет»; «балансировщик auto: selector ['proxy-']»; «пробы ядра (subjectSelector):
  ['proxy-']»; «правил «свой сервер устройства» (Ф4): …» — записать;
- «Xray: запущен …» — записать (время — после установки);
- `OK    Бесплатный пул: выключен — режим подписок`; строки «Устройства через» нет; строку
  `Итог: …` — записать;
- в журнале с установки «Traceback: 0».

Если не так: не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать, сообщить
заказчику и продолжить; отпечаток не совпадает — повторить через минуту, снова так —
**дефект «отпечаток таблиц меняется сам»**; «балансировщик pool: есть» или в subjectSelector
есть `pool-` — **дефект «пул в конфиге без устройств»**.

## 3. Наблюдение и допущенные серверы

Шаг 3.1. Включить наблюдение:

```bash
cd "$HOME/xgw-fpb1" && date '+%F %T' | tee observe-time.txt && sudo xgw pool mode observe 2>&1 | tee mode-on.txt
```

Ожидается: «Наблюдение за бесплатным пулом включено: … Демон применит режим на ближайшем
шаге».

Если не так: «ошибка: …» — записать дословно, **стоп**, сообщить заказчику.

Шаг 3.2. Не раньше чем через 25 минут после шага 3.1 — сколько серверов допущено к трафику:

```bash
cd "$HOME/xgw-fpb1" && for m in pool admitted lists units digest; do sudo python3 -I fpb1check.py $m; done | tee pool-1.txt; sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpb1check.py log | tee log-1.txt
```

Ожидается:
- «free_pool в состоянии: режим observe, регион EU; …»; «через пул: устройств нет»;
- **«допущено к трафику: N (OK …, SLOW …); страны: …; источники: …; ядро: …»**, N — 3 или
  больше; в «странах» — только страны EU; «скорость проверки у лучших: …» — записать;
- `igareck: SUCCESS`, `mahdibland: SUCCESS` (или PARTIAL), «служебных IPv4: 0» у обоих;
- «отпечаток таблиц: совпадает»; в журнале: «список получен через подписку» 2 или больше,
  «список получен напрямую: 0», «Traceback: 0».

Если не так: N меньше 3 — подождать 15 минут и повторить шаг; снова меньше 3 — записать
(бесплатных серверов EU сейчас мало) и продолжить, если N — 1 или больше; N = 0 — **стоп**,
сообщить заказчику (устройству идти некуда); в «странах» не EU — **дефект «регион не
строгий»**; «служебных IPv4» больше 0 — **дефект «адрес LAN в пуле»**.

## 4. Тестовое устройство через бесплатные серверы

Шаг 4.1. **Попроси заказчика** (дословно):

«Откройте панель XGW, карточку «Устройства». Выберите тестовое устройство (лучше телефон в
домашнем Wi-Fi, без своего VPN) и в его строке в списке «Сервер: авто» выберите «Бесплатные
серверы». Прочитайте мне заголовок и текст окна, которое появится, и нажмите «Через
бесплатные». Затем прочитайте ответ панели и метку справа в строке устройства. Скажите адрес
устройства из строки (192.168.…).»

Записать: адрес тестового устройства, текст окна, ответ панели, метку.

Ожидается: окно «Пустить «…» через бесплатные серверы?» с текстом «Владельцы бесплатных
серверов неизвестны и видят, к каким сайтам идёт устройство: … Российские домены (.ru, .su, .рф)
— напрямую, как у всех. Пока бесплатных серверов нет, зарубежные сайты у устройства закрыты:
через подписку оно не пойдёт. Вернуть — «Сервер: авто».»; ответ панели — «Устройство «…» идёт
через бесплатные серверы» с пояснениями; метка — «бесплатные серверы» (через минуту, после
обновления страницы; сразу может быть «бесплатные серверы · закрыто»).

Если не так: в списке нет «Бесплатные серверы» — попросить обновить страницу (Ctrl+F5); снова
нет — **дефект «нет выбора пула в панели»**, **стоп**; ответ панели — ошибка — записать
дословно, **стоп**.

Шаг 4.2. Через 2 минуты после ответа заказчика — что собрал шлюз:

```bash
sleep 120; cd "$HOME/xgw-fpb1" && date '+%F %T' | tee device-time.txt; for m in route config pool xstats xray units digest; do sudo python3 -I fpb1check.py $m; done | tee device-1.txt; sudo xgw pool 2>&1 | grep -E '^Через бесплатные' | tee -a device-1.txt; sudo xgw status 2>&1 | grep -E '^Состояние|^Через бесплатные' | tee -a device-1.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул|Устройства через' | tee -a device-1.txt; sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpb1check.py log | tee log-2.txt
```

Ожидается:
- режим `route`: «режим пула: observe; устройств через пул в настройках: 1 (<адрес>)»;
  **«<адрес>: правило → балансировщик pool; российские домены напрямую раньше него: да»**;
  **«балансировщик pool: есть; selector ['pool-']; стратегия leastPing; fallbackTag block»**;
  **«балансировщик auto: selector ['proxy-']»**; «пробы ядра (subjectSelector): ['proxy-',
  'pool-']»;
- режим `config`: **«выходов подписки (proxy-/spare-): …; из них вариантов бесплатного пула
  целиком …: 0; к работникам OpenVPN: 0»**; **«выходов бесплатного пула (pool-*): M; напрямую
  …, мостом sing-box …; у прямых адрес — публичный IPv4: K из K; вариантов пула целиком: K из
  K»**, M — от 1 до 8;
- режим `pool`: «через пул: устройства <адрес>; серверов в pool M, живых A; закрыто: нет;
  страна XX; задержка … мс», A — 1 или больше, XX — страна EU;
- режим `xstats`: «трафик с запуска Xray: через бесплатный пул … МБ …» — записать; «выходов
  pool-* под пробами ядра: M, живых: A; закреплён: да»;
- «Xray: запущен …» — записать (перезапуск при выборе устройства возможен — один раз: пробы ядра
  получили `pool-`);
- `xgw pool` и `xgw status`: «Через бесплатные серверы: <адрес> — сервер «…» (XX), задержка …
  мс; живых A из M» (имя сервера в отчёт не писать — только страну);
- diag: `OK    Устройства через бесплатный пул: <адрес>: через бесплатный пул, серверов в
  «pool»: M`;
- журнал: «пул: сервер для устройств выбран: 1» (или больше); «пул: закрепление не удалось: 0»;
  «сборок ради пула: …; из них с перезапуском Xray: 0»; «Traceback: 0».

Если не так:
- «правила в рабочем конфиге НЕТ» — подождать 2 минуты и повторить шаг; снова — **дефект
  «устройство идёт через подписку»**, **стоп**, попросить заказчика вернуть устройство («Сервер:
  авто») и сообщить;
- «правило → выход block», а «допущено к трафику» в шаге 3.2 было больше 0 — подождать 2 минуты
  и повторить; снова — **дефект «устройство закрыто при допущенных серверах»**;
- «российские домены напрямую раньше него: НЕТ» — **дефект «российские сайты через пул»**;
- в «auto» есть `pool-` или «вариантов бесплатного пула целиком» у выходов подписки больше 0 —
  **дефект «пул попал в подписку»**, **стоп**, как выше;
- «у прямых адрес — публичный IPv4» меньше K — **дефект «адрес сервера пула не публичный»**,
  **стоп**, как выше;
- «закреплён: нет» при живых больше 0 — повторить через минуту; снова — **дефект «сервер пула
  не закрепляется»**; «пул: закрепление не удалось» больше 0 — записать строки помощника, тот
  же дефект;
- «сборок ради пула … с перезапуском Xray» больше 0 — **дефект «смена состава пула
  перезапускает Xray»**;
- diag `FAIL` — записать строку, **дефект «diag: устройства через пул»**;
- Traceback больше 0 — записать
  `sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -20 | tee traceback-1.txt`
  — **дефект «шаг пула падает»**.

Шаг 4.3 (при согласии на пункт 4). **Попроси заказчика** (дословно):

«На тестовом устройстве откройте ipinfo.io и скажите только страну (без адреса). Затем там же
откройте ya.ru — открылся? Потом на этом компьютере откройте ipinfo.io и скажите страну.»

Сразу после ответа:

```bash
cd "$HOME/xgw-fpb1" && for m in pool xstats; do sudo python3 -I fpb1check.py $m; done | tee country-1.txt
```

Ожидается: страна на тестовом устройстве — **та же, что «страна XX»** в `country-1.txt`; ya.ru
открылся; страна на этом компьютере — страна сервера подписки (записать; может совпасть с XX —
это не дефект). В `xstats` «через бесплатный пул … МБ» больше, чем в шаге 4.2.

Если не так: ipinfo.io на тестовом устройстве не открылся — попросить подождать минуту и
открыть снова; снова нет — записать `pool` и `xstats`, **дефект «через пул сайты не
открываются»** (если «закрыто: нет»); страна другая — повторить через минуту (сервер мог
смениться: «пул: сервер для устройств выбран» в журнале); снова другая — **дефект «устройство
идёт не через закреплённый сервер пула»**; «через бесплатный пул» не вырос — тот же дефект;
ya.ru не открылся — **дефект «российские сайты у устройства не открываются»**.

Шаг 4.4 (при согласии на пункт 6). **Попроси заказчика** (дословно): «Прочитайте мне в
карточке «Бесплатные серверы» последнее предложение (начинается со слов «Через бесплатные
серверы») и метку тестового устройства.»

Ожидается: «Через бесплатные серверы: <имя устройства> — сервер «…» (XX), задержка … мс; живых
A из M.»; метка — «бесплатные серверы». Записать (имя сервера — не писать).

Если не так: предложения нет — попросить обновить страницу (Ctrl+F5); снова нет — **дефект
«карточка без устройств через пул»**.

## 5. Обычная работа через пул

Шаг 5.1 (при согласии на пункт 5). **Попроси заказчика** (дословно): «Около часа пользуйтесь
тестовым устройством как обычно: сайты, видео, приложения. Через 30 минут я спрошу, как идёт.»

Через 30 минут после просьбы:

```bash
cd "$HOME/xgw-fpb1" && for m in pool route xstats xray admitted; do sudo python3 -I fpb1check.py $m; done | tee use-1.txt; sudo journalctl -u xgw --since "$(cat device-time.txt)" --no-pager | sudo python3 -I fpb1check.py log | tee log-3.txt
```

**Спроси заказчика** (дословно): «Как работает тестовое устройство: что открывалось, что нет,
было ли медленно или с перерывами?» — записать ответ дословно.

Ещё через 30 минут — тот же блок, с `use-2.txt` и `log-4.txt` вместо `use-1.txt` и `log-3.txt`,
и тот же вопрос заказчику.

Ожидается (оба раза):
- «правило → балансировщик pool»; «закрыто: нет»; «живых A», A — 1 или больше;
- «через бесплатный пул … МБ» растёт от замера к замеру; «у закреплённого …» — большая часть
  его; «через подписку» — записать (это остальной дом);
- «Xray: запущен …» — **то же время, что в шаге 4.2** (перезапусков не было);
- журнал: «сборок ради пула: …; из них с перезапуском Xray: 0»; «пул: сервер для устройств
  выбран» и «пул: у устройств закрыто» — записать (смены сервера и паузы); «Traceback: 0»;
- «допущено к трафику» — записать (меняется: серверы перепроверяются).

Если не так: «закрыто: ДА» дольше 3 минут при «допущено к трафику» больше 0 — **дефект
«устройство закрыто при допущенных серверах»**; время запуска Xray изменилось — записать
«применений с перезапуском Xray» из журнала; если вырос и «сборок ради пула … с перезапуском» —
**дефект «смена состава пула перезапускает Xray»**, иначе — наблюдение (перезапуск по другой
причине: подписка, окно перезапуска); «через бесплатный пул» не растёт, а заказчик пользуется
устройством — **дефект «трафик устройства не через пул»**; жалобы заказчика — в отчёт
дословно (медленно — не дефект: серверы бесплатные).

Против пункта 5: блок выполнить один раз через 10 минут после шага 4.3, без вопроса.

## 6. Закрыто без пула

Шаг 6.1 (при согласии на пункт 6). **Попроси заказчика** (дословно): «В карточке «Бесплатные
серверы» нажмите «Выключить». Что ответила панель?»

Ожидается: отказ — «Через бесплатные серверы идёт устройство «…»: без пула у него закроются
зарубежные сайты. Сначала верните его на подписку в списке устройств (сервер: авто), потом
выключайте». Наблюдение не выключилось (кнопка по-прежнему «Выключить»).

Если не так: панель выключила наблюдение — **дефект «панель выключает пул с устройством»**;
тогда шаг 6.2 начать со второй команды (`sleep 120; …`).

Шаг 6.2. **Скажи заказчику** (дословно): «Сейчас на 5 минут выключу наблюдение командой — у
тестового устройства должны закрыться зарубежные сайты, российские останутся.» Затем:

```bash
cd "$HOME/xgw-fpb1" && date '+%F %T' | tee off-time.txt && sudo xgw pool mode off 2>&1 | tee off.txt; sleep 120; for m in route pool xstats xray; do sudo python3 -I fpb1check.py $m; done | tee closed.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул|Устройства через' | tee -a closed.txt
```

Ожидается: «Бесплатный пул выключен. Устройства через бесплатные серверы (<адрес>) остались без
зарубежных сайтов — верните их на подписку в списке устройств панели. Демон применит режим на
ближайшем шаге»; через 2 минуты: **«<адрес>: правило → выход block; российские домены напрямую
раньше него: да»**; «балансировщик pool: нет»; «пробы ядра (subjectSelector): ['proxy-',
'pool-']» (как были: перезапуска нет); «free_pool в состоянии: нет»; «Xray: запущен …» — то же
время, что в шаге 4.2; diag: `OK    Бесплатный пул: выключен — режим подписок` и `WARN
Устройства через бесплатный пул: <адрес>: закрыто — наблюдение выключено`.

Затем (при согласии на пункт 4) **попроси заказчика** (дословно): «На тестовом устройстве
откройте ipinfo.io и ya.ru. Что открылось?»

Ожидается: ipinfo.io **не открывается**, ya.ru открывается.

Если не так: правило не block — подождать минуту и повторить вторую часть блока; снова — **дефект
«без пула устройство не закрыто»**; ipinfo.io открылся — **дефект «без пула устройство идёт
мимо пула»** (страну — в отчёт); ya.ru не открылся — **дефект «российские сайты у устройства не
открываются»**; время запуска Xray изменилось — **дефект «выключение пула перезапускает Xray»**.

Шаг 6.3. Не раньше чем через 5 минут после шага 6.2 — включить обратно:

```bash
cd "$HOME/xgw-fpb1" && sudo xgw pool mode observe 2>&1 | tee on-again.txt; sleep 180; for m in route pool xstats xray; do sudo python3 -I fpb1check.py $m; done | tee reopened.txt
```

Ожидается: «Наблюдение … включено …»; через 3 минуты — **«правило → балансировщик pool»**,
«закрыто: нет», «живых A» — 1 или больше; «Xray: запущен …» — то же время. Затем (при согласии на
пункт 4) **попроси заказчика**: «Откройте на тестовом устройстве ipinfo.io ещё раз — какая
страна?» — открывается, страна — как «страна XX» в `reopened.txt`.

Если не так: через 3 минуты правило ещё block — подождать 3 минуты и повторить вторую часть
блока; снова — **дефект «устройство не открывается после возврата пула»**.

## 7. Возврат на подписку

Шаг 7.1. **Попроси заказчика** (дословно): «В строке тестового устройства выберите «Сервер:
авто». Что ответила панель и какая теперь метка?»

Ожидается: «Устройство «…» снова идёт через основной сервер»; метка — «через VPN».

Шаг 7.2. Через 2 минуты:

```bash
sleep 120; cd "$HOME/xgw-fpb1" && for m in route config pool xray; do sudo python3 -I fpb1check.py $m; done | tee returned.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул|Устройства через' | tee -a returned.txt
```

Ожидается: «устройств через пул в настройках: 0 (—)»; «балансировщик pool: нет»; «пробы ядра
(subjectSelector): ['proxy-']»; «выходов бесплатного пула (pool-*): 0»; «вариантов
бесплатного пула целиком» у выходов подписки — 0; «через пул: устройств нет»; «Xray: запущен
…» — записать (перезапуск здесь возможен один раз: пробы ядра потеряли `pool-`); строки
«Устройства через» в diag нет. Затем (при согласии на пункт 4) **попроси заказчика**: «Откройте
на тестовом устройстве ipinfo.io — какая страна?» — страна сервера подписки (как у этого
компьютера в шаге 4.3).

Если не так: выходы pool-* или балансировщик pool остались через 2 минуты — подождать ещё 2 и
повторить; снова — **дефект «пул остался после возврата устройства»**.

## 8. Секреты

Шаг 8.1.

```bash
cd "$HOME/xgw-fpb1" && sudo python3 -I fpb1check.py files | tee secrets.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpb1check.py leak | sed 's/^/xgw: /' | tee -a secrets.txt; stat -c 'status.json: %a' /run/xgw/status.json | tee -a secrets.txt
```

Ожидается: права 700/600/600, снимки 600; «паролей источников известно: 1» (0 — если VPNBook
не ответил); **«строк с паролем: 0; строк со ссылкой сервера: 0; строк OpenVPN с настройками:
0»**; «status.json: 644». Записать.

Если не так: строк с паролем, ссылкой или настройками больше 0 — **дефект «секрет в журнале»**.

## 9. Выключение и итог

Шаг 9.1. **Попроси заказчика** (дословно): «В карточке «Бесплатные серверы» нажмите
«Выключить». Что ответила панель и что теперь написано в карточке?» Нет ответа 30 минут —
выключить командой `cd "$HOME/xgw-fpb1" && sudo xgw pool mode off 2>&1 | tee off-final.txt` (пункт 2
согласия) и записать это.

Сразу после ответа (или команды):

```bash
cd "$HOME/xgw-fpb1" && sleep 60; date '+%F %T' | tee final-time.txt; sleep 120; for m in pool route config units files; do sudo python3 -I fpb1check.py $m; done | tee off-final-state.txt
```

Ожидается: ответ панели — «Бесплатный пул выключен» (без отказа: устройств через пул уже нет);
в карточке — «Альтернативный режим: …»; «free_pool в состоянии: нет»; «устройств через пул в
настройках: 0»; «выходов бесплатного пула (pool-*): 0»; «поколений xgw-fp@ сейчас: 0»;
«временных Xray и sing-box сейчас: 0»; «panel.json: режим пула: off».

Если не так: «free_pool в состоянии: режим …» — подождать 2 минуты и повторить; снова — **дефект
«наблюдение не выключается»**.

Шаг 9.2. Через 3 минуты после шага 9.1:

```bash
sleep 180; cd "$HOME/xgw-fpb1" && sudo journalctl -u xgw --since "$(cat final-time.txt)" --no-pager | sudo python3 -I fpb1check.py log | tee log-off.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpb1check.py log | tee final.txt; for m in digest subs xray units; do sudo python3 -I fpb1check.py $m; done | tee -a final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Через бесплатные' | tee -a final.txt
```

Ожидается:
- в `log-off.txt`: все «список получен» — 0, «проверок серверов пула: 0»;
- в `final.txt`: **«Traceback: 0»**, «шаг пула не выполнен: 0», «откат на last-good: 0»,
  «пул: закрепление не удалось: 0», **«сборок ради пула: …; из них с перезапуском Xray: 0»**;
  «применений с перезапуском Xray» — записать (ожидается не больше 2–3: выбор устройства, его
  возврат и, может быть, окно перезапуска); «Read-only file system» и «Permission denied» — не
  больше, чем в `log-before.txt`;
- «отпечаток таблиц: совпадает»; «подписок с ошибкой» — не больше, чем до установки; «серверов в
  списке» — как до установки (±5);
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки; строки `Через
  бесплатные` нет.

Если не так: опросы или проверки после выключения больше 0 — **дефект «пул работает
выключенным»**; Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -30 | tee traceback.txt`
(только строки с файлами и ошибкой, адреса — убрать). Сообщить заказчику.

Шаг 9.3 (при согласии на пункт 7). **Попроси заказчика** (дословно): «Откройте любой сайт на
этом компьютере и любой сайт на телефоне. Открываются?»

Ожидается: «да». Нет — записать ответ дословно и
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt`,
сообщить заказчику.

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.
- Остановка проверки (по стоп-правилу или по просьбе заказчика) — попросить заказчика вернуть
  тестовое устройство на «Сервер: авто», затем нажать «Выключить» в карточке «Бесплатные
  серверы»; выполнить шаги 7.2 и 9.2; службы руками не трогать.
- Наблюдение не оставлять включённым после проверки: без решения заказчика шлюз не должен сам
  ходить к бесплатным серверам. Заказчик не ответил на шаг 9.1 за 30 минут — выключить командой
  `sudo xgw pool mode off` (пункт 2 согласия) и выполнить шаг 9.2. Устройство, оставшееся «через
  бесплатные серверы», без наблюдения закрыто — напомнить заказчику вернуть его на «Сервер:
  авто».

## 10. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-m2b1-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`freepool`), коммит «Отчёт: XGW 0.2.0, бесплатные серверы, веха М2б.1», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, бесплатные серверы, веха М2б.1 (устройство через бесплатные серверы)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
fpb1check.py: <сумма, 16 знаков>. Тестовое устройство: <адрес 192.168.…>, <телефон/компьютер/…>.

## Итог вехи
| Шаг | Правило устройства | pool-* (живых) | Закрыто | Страна: пул / ipinfo.io на устройстве | Через пул, МБ | Через подписку, МБ | Xray запущен |
|---|---|---|---|---|---|---|---|
| 4.2 выбор | … | … | … | … / … | … | … | … |
| 5.1 30 мин | … | … | … | … / — | … | … | … |
| 5.1 60 мин | … | … | … | … / — | … | … | … |
| 6.2 пул выключен | … | … | … | — / открылся? | … | … | … |
| 6.3 пул снова | … | … | … | … / … | … | … | … |
| 7.2 возврат | … | … | … | — / … | — | … | … |

Допущено к трафику (3.2): … (страны …, источники …). Сборок ради пула: …, с перезапуском Xray:
… Применений с перезапуском Xray за прогон: … (причины). Смен закреплённого сервера: …, пауз
«закрыто»: …

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | сумма, состояние, службы, режим пула, отпечаток, подписки, Xray |
| 1.3 оставшееся наблюдение | … / не нужен | |
| 2.2 установка | … | код, строки установки |
| 2.3 после установки | … | HEALTHY, route без пула, diag |
| 3.2 допущенные | … | N, страны, источники, ядро, скорость |
| 4.1 выбор в панели | … | текст окна, ответ панели, метка |
| 4.2 конфиг и сводка | … | правило, балансировщики, пробы ядра, pool-*, адреса, закрепление, diag, журнал |
| 4.3 страна | … / не выполнялся | страна на устройстве и на этом компьютере, ya.ru |
| 4.4 карточка | … / не выполнялся | фраза, метка |
| 5.1 работа | … | рост трафика, перезапуски, смены сервера, ответы заказчика |
| 6.1 кнопка «Выключить» | … / не выполнялся | отказ панели |
| 6.2 закрыто | … | block, diag, ipinfo.io не открылся, ya.ru открылся, Xray без перезапуска |
| 6.3 пул снова | … | правило pool, страна |
| 7.2 возврат | … | pool-* 0, балансировщика нет, страна подписки |
| 8.1 секреты | … | права, пароли, ссылки в журнале |
| 9.1 выключение | … | ответ панели, следы |
| 9.2 итог | … | Traceback, перезапуски, отпечаток, подписки, HEALTHY |
| 9.3 сайты | … / не выполнялся | ответ заказчика |

## Выводы шагов
<файлы $HOME/xgw-fpb1/*.txt; имя пользователя → <user>; ответы заказчика дословно, без адресов
и имён серверов>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
