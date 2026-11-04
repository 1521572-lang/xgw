# Проверка XGW 0.2.0: бесплатные серверы, веха М2а.3 (посредник без системного DNS, канал к серверу)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-fp23/…`). Файл помощника создавай только командой шага 1.2, выполненной в
терминале. Блок команды копируй целиком, ничего в нём не меняя.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. Телефон — S25 Ultra в домашней сети.
Команды — в терминале сеанса заказчика (`sudo` от его имени).

Что нового (ASSUMPTIONS п. 260) — по отчёту М2а.2 (посредник запускается, ложного
GUARD_BLOCKED и «кода 23» больше нет; остался дефект «работник 16/8/8 после подъёма»):
1. **Посредник больше не спрашивает системный DNS.** Когда DNS через туннель молчал, Xray
   посредника спрашивал системный резолвер машины (127.0.0.53) — туда посреднику нельзя, и
   охрана отбивала эти запросы (проверено у разработчика в изолированном пространстве имён:
   запросы A и AAAA уходят при `UseIPv4` и не уходят при `ForceIPv4`). Ожидается: **«охрана
   после подъёма: OpenVPN 0, работник 0»** у каждого туннеля. Это была не утечка: наружу
   ничего не уходило.
2. **Главный вопрос вехи — отвечает ли сервер после подъёма.** Во всех трёх прогонах из
   туннеля не вернулось ни одного пакета. Теперь в итоге туннеля — **«канал к серверу после
   подъёма: от сервера N пакетов (X КБ), к серверу M пакетов (Y КБ)»**: молчит сервер (или
   блокировка), или ответы приходят, но в туннель не попадают (тогда виноват шлюз).
3. В итоге туннеля — до трёх **предупреждений OpenVPN** (WARNING, OPTIONS ERROR, сжатие), без
   адресов: несогласие клиента и сервера OpenVPN пишет именно так.
4. Шаг 1.3: если наблюдение осталось включённым с прошлого прогона, оно выключается в начале —
   это заодно проверка выключения, не выполненная в М2а.2.

Здесь, у разработчика, — только юнит-тесты затронутых модулей, ruff, `xray run -test` конфига
посредника и проверка системного DNS у Xray в изолированном пространстве имён. Всё остальное —
на этой машине.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `openvpn*`,
  `tailscaled`, NetworkManager, `ssh`; ручные `nft` (кроме `nft list`), `ip` (кроме чтения
  помощником), `ip netns`, `nsenter`, `iptables`, `tc`, `sysctl -w`, `systemd-run`; команды
  `tailscale`, `xray`, `sing-box` и `openvpn`. `sudo xgw pool mode …` — только в шагах 1.3 (`off`) и 3.1 (`observe`).
- Самому открывать сайты источников (vpngate, vpnbook) и файлы списков на GitHub — в
  браузере, `curl`, `wget` и как угодно ещё. Их открывает только сам шлюз.
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, `/etc/openvpn`, код XGW. Печатать `config.toml`, `panel.json`,
  файлы в `/var/lib/xgw/freepool` и `/run/xgw/fp` (`cat`, `less`, `grep` по ним) — в них ключи
  подписок, учётки, пароли и ссылки серверов. Серверы, переключатели и кнопки в панели меняет
  и нажимает только заказчик. Коммитить что-либо, кроме отчёта (§9).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP, домены и ссылки
  серверов VPN (и бесплатных тоже), логины и пароли, строки журнала. Можно: адреса устройств в
  домашней сети (`192.168.…`), коды стран, названия источников, счётчики, статусы, коды причин,
  размеры, права файлов, времена, версии пакетов и строки помощника «OpenVPN: …», «изнутри: …»,
  «итог туннеля: …», «канал к серверу …» и «предупреждение OpenVPN: …» (адреса и имена в них
  уже заменены).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю туннели OpenVPN к бесплатным серверам и списки серверов с GitHub (веха М2а.3). По
пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд. Внешний интерфейс (WAN), его соединение и DHCP
установка не трогает: меняются только профиль LAN, свои таблицы nftables и свои службы. Пакет
openvpn и пользователи xgw-ovpn, xgw-fps уже стоят — заново не ставятся.
(2) Я включу наблюдение командой `sudo xgw pool mode observe`. Трафик устройств идёт через
подписку, как сейчас. Шлюз будет: подключаться к бесплатным серверам OpenVPN в изолированной
службе (не больше 2 раз в час к каждому источнику); скачивать через подписку списки серверов с
GitHub и проверять их серверы напрямую — до 4 серверов в минуту, без предела трафика (около
15–20 МБ в час: каждая проверка — загрузка небольшого файла с CDN через этот сервер). Владельцы
этих серверов неизвестны и видят только проверочный запрос шлюза. Проверка займёт около
полутора часов. В конце вы выключите наблюдение кнопкой «Выключить» в карточке «Бесплатные
серверы» панели XGW. Если наблюдение осталось включённым с прошлой проверки, в начале я
попрошу вас выключить его той же кнопкой (не ответите за 10 минут — выключу командой).
(3) В панели по моей просьбе прочитаете мне сводку из карточки «Бесплатные серверы».
(4) В конце откроете любой сайт на этом компьютере и на телефоне.
Можно согласиться не на все пункты.»

Против пункта 1 или 2 — **стоп**. Против 3 — шаги 3.3 и 5.1 пропустить; против 4 — шаг 8.2.
Если против 2 только выключение кнопкой — шаг 7.1 пропустить. В отчёте у пропущенного — «не
выполнялся». Если ответа на вопрос нет — не начинать, спросить ещё раз.

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-fp23" && chmod 700 "$HOME/xgw-fp23" && cd "$HOME/xgw-fp23" && cat > fpm23check.py <<'EOF'
"""XGW 0.2.0, бесплатный пул (веха М2а.3: посредник без системного DNS, канал к серверу):
помощник
проверки. Только читает: состояние XGW (/run/xgw, /var/lib/xgw/freepool, рабочие конфиги Xray
и sing-box), бэкенд OpenVPN (пакет, пользователи, служба, пересылка IPv4, набор fp_peers, ufw,
veth) и журналы со стандартного ввода — счётчики, коды, права и да/нет, без адресов, имён,
ссылок и паролей. watch — живые поколения по /proc и systemctl show: в пространство имён не
входит и ничего не меняет. checks <секунды> — только записи проверок с этого времени.
Режимы: units, backend, pool, checks, lists, files, config, leak, digest, subs, fwd, log,
agentlog, watch."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("FPM23_LIB", "/opt/xgw/lib")
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
          f"{pool.get('handshakes_hour')}, за сутки {pool.get('handshakes_day')}")
    now = time.time()
    for source in pool.get("sources") or []:
        when = source.get("retrieved_at")
        got = f"{int((now - float(when)) // 60)} мин назад" if when else "нет"
        print(f"  {source.get('id')}: {source.get('status')}; список — {got}; вариантов "
              f"{source.get('variants')}; устарел: {'да' if source.get('stale') else 'нет'}")
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
    from xgw.freepool.store import PoolStore

    store = PoolStore(paths)
    variants = [variant for provider in cfg.free_pool.providers
                for variant in store.variants(provider)]
    hosts = {name.lower() for variant in variants for name in (variant.host, variant.address)
             if name}
    work = read_json(paths.xray_config_file) or {}
    total = matched = workers_out = 0
    for outbound in work.get("outbounds") or []:
        settings = outbound.get("settings") or {}
        entries = [*(settings.get("vnext") or []), *(settings.get("servers") or []), settings]
        for entry in entries:
            address = entry.get("address") if isinstance(entry, dict) else None
            if isinstance(address, str) and address:
                total += 1
                matched += address.lower() in hosts
                workers_out += address.startswith("10.250.")
    box = read_json(paths.singbox_config_file) or {}
    servers = [str(item.get("server")).lower() for key in ("outbounds", "endpoints")
               for item in box.get(key) or [] if isinstance(item, dict) and item.get("server")]
    print(f"адресов серверов в рабочем конфиге Xray: {total}; из них серверов бесплатного пула: "
          f"{matched}; выходов к работникам пула: {workers_out}; серверов в конфиге sing-box: "
          f"{len(servers)}, из них бесплатного пула: {sum(1 for item in servers if item in hosts)}"
          f"; вариантов в пуле: {len(variants)}")
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
        ("Read-only file system", ("Read-only file system",)),
        ("Permission denied", ("Permission denied",)),
        ("Traceback", ("Traceback",)),
    ):
        print(f"{label}: {sum(1 for line in lines if any(word in line for word in words))}")
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
    print("режим: units | backend | pool | checks | lists | files | config | leak | digest | subs"
          " | fwd | log | agentlog | watch")
EOF
python3 -c "import hashlib;d=open('fpm23check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул' | tee before.txt; for m in units files digest subs; do sudo python3 -I fpm23check.py $m; done | tee state-before.txt; sudo journalctl -u xgw --since "60 min ago" --no-pager | sudo python3 -I fpm23check.py log | tee log-before.txt
```

Ожидается:
- `73e3b86fa66b23df`;
- `Состояние: …`, `Перехват: включён …`, строки `Xray …` и `sing-box …` — записать как есть;
- четыре службы `active`; «поколений xgw-fp@ сейчас: 0 (—); процессов openvpn XGW: 0; …» —
  записать;
- «каталог freepool: 700; …; снимков списков: N (vpnbook …, vpngate …); права снимков: 600 …»
  — снимки с прошлых проверок; «записей проверок: …; без варианта в снимках: …» — записать;
  «отпечаток таблиц: совпадает; правила на месте (loaded): True»; «подписок с ошибкой: …;
  серверов в списке: …» — записать;
- счётчики журнала — записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать и продолжить.

Шаг 1.3. Только если в `state-before.txt` — «panel.json: режим пула: observe» (наблюдение
осталось включённым с прошлого прогона); иначе — пропустить, в отчёте «не нужен».
**Попроси заказчика** (дословно):

«Наблюдение за бесплатными серверами осталось включённым с прошлой проверки. В карточке
«Бесплатные серверы» нажмите, пожалуйста, «Выключить». Что ответила панель и что теперь на
кнопке?»

Нет ответа 10 минут — выключить командой (пункт 2 согласия), записать это в отчёт:
`cd "$HOME/xgw-fp23" && sudo xgw pool mode off 2>&1 | tee off-before.txt` — ожидается «Бесплатный
пул выключен. Демон применит режим на ближайшем шаге». Затем (в обоих случаях):

```bash
cd "$HOME/xgw-fp23" && sleep 180; for m in pool units backend files; do sudo python3 -I fpm23check.py $m; done | tee off-before-state.txt; sudo xgw status 2>&1 | grep -c '^Бесплатный пул' | sed 's/^/строк «Бесплатный пул» в xgw status: /' | tee -a off-before-state.txt
```

Ожидается: ответ панели — «Бесплатный пул выключен», на кнопке — «Включить наблюдение» (если
нажимал заказчик); «free_pool в состоянии: нет»; «поколений xgw-fp@ сейчас: 0; процессов
openvpn XGW: 0»; «набор fp_peers: нет»; «veth fpv сейчас: 0; каталогов поколений: 0»;
«временных Xray и sing-box сейчас: 0»; «panel.json: режим пула: off»; «строк «Бесплатный пул» в
xgw status: 0». Записать: это проверка выключения, не выполненная в М2а.2.

Если не так: «free_pool в состоянии: режим …» — подождать 2 минуты и повторить блок; снова так
— **дефект «наблюдение не выключается»**; поколения, veth, каталоги или процессы больше 0 —
**дефект «пул оставил следы»**; «набор fp_peers: есть» — **дефект «правила пула остались»**.
Продолжить.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def parse_link_list' src/xgw/freepool/providers.py && grep -q 'def check_singbox' src/xgw/freepool/probe.py && grep -q 'refused_socks' src/xgw/freepool/agent.py && grep -q 'PROC_TCP' src/xgw/freepool/agent.py && grep -q 'UP_MARGIN = 35.0' src/xgw/freepool/backend.py && grep -q 'def xray_problem' src/xgw/freepool/providers.py && grep -q 'def core_failure' src/xgw/freepool/probe.py && grep -q 'ForceIPv4' src/xgw/freepool/agent.py && grep -q 'def link_text' src/xgw/freepool/agent.py && echo "правка в коде: есть"; cd "$HOME/xgw-fp23"
```

Ожидается: «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. Внешний интерфейс (WAN), его
соединение и DHCP она не трогает; интернет дома пропадёт на несколько секунд, пока
перезапускаются службы XGW. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fp23/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fp23/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'пакеты:|пользователь xgw-|ufw:|перезапущен|Xray запущен' "$HOME/xgw-fp23/install.txt"; cd "$HOME/xgw-fp23"
```

Ожидается: «код 0», «демон xgw запущен», «Xray запущен: участников …»; строк «пакеты:» и
«пользователь xgw-…» нет (уже стоят). Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке, бэкенд на месте, пул выключен:

```bash
sleep 120; cd "$HOME/xgw-fp23" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул' | tee after-install.txt; for m in units backend digest files pool; do sudo python3 -I fpm23check.py $m; done | tee -a after-install.txt; sudo xgw pool 2>&1 | head -2 | tee -a after-install.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул|Конфиг|^Итог' | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm23check.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки, строки
  `Бесплатный пул` нет; четыре службы `active`; «поколений xgw-fp@ сейчас: 0»;
- «пакет openvpn: <версия>; /usr/sbin/openvpn: есть; sing-box для проверок: есть»; оба
  пользователя «есть, системный, оболочка /usr/sbin/nologin»; «служба xgw-fp@.service: есть»;
  «пересылка IPv4: 1»; «набор fp_peers: нет»; «бэкенд OpenVPN: в правилах XGW нет набора
  fp_peers — перехват не загружен» (так и должно быть при выключенном пуле); «срок подготовки
  поколения у демона: 35 с сверх срока агента»;
- «отпечаток таблиц: совпадает; … True»;
- «free_pool в состоянии: нет»; первая строка `xgw pool` — «Бесплатный пул: выключен; регион EU
  (строго)», вторая — «Найдено …: из списков GitHub 0 (из них только sing-box 0), Outline …,
  OpenVPN …» — записать;
- `OK    Бесплатный пул: выключен — режим подписок`; строку `Итог: …` — записать;
- в журнале с установки «Traceback: 0».

Если не так:
- не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать, сообщить заказчику и
  продолжить;
- «sing-box для проверок: нет» — **дефект «нет sing-box для проверок»** (серверы Hysteria2 тогда
  не проверятся), продолжить;
- нет пакета, пользователя или службы — **дефект «установка убрала бэкенд»**, **стоп**;
- «срок подготовки …» не 35 — **стоп**: установлен не тот код (повторить шаг 2.1);
- отпечаток не совпадает — повторить через минуту, снова так — **дефект «отпечаток таблиц
  меняется сам»**.

## 3. Включение наблюдения

Шаг 3.1. Включить и сразу 10 минут наблюдать живые поколения (помощник только читает
`/proc`, `systemctl show` и файлы состояния; в службы не вмешивается):

```bash
cd "$HOME/xgw-fp23" && date '+%F %T' | tee observe-time.txt && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; sudo python3 -I fpm23check.py watch 600 | tee live.txt
```

Ожидается:
- «Наблюдение за бесплатным пулом включено: … Демон применит режим на ближайшем шаге»;
- через 10 минут: «поколений увидено: N; дошло до фазы up: U; туннель поднимался: T», N — от
  1, U и T — любые (0 тоже: часовой предел подключений мог быть занят прошлым прогоном этого
  дня, а туннель — не подняться); **U должно быть равно T** — поднявшийся туннель теперь
  доходит до фазы up;
- у каждого поколения:
  - «фазы guarded → connecting → …», «самопроверка пройдена», «причина отказа: …» (у
    GUARD_BLOCKED — с «по журналу OpenVPN: …») и «туннель поднимался: да/нет» — записать;
  - «служба: CapabilityBoundingSet=cap_chown cap_kill cap_setgid cap_setuid cap_net_admin;
    KillMode=mixed; NoNewPrivileges=yes; PrivateNetwork=yes; PrivateTmp=yes;
    ProtectSystem=strict» (порядок слов в возможностях — любой);
  - «агент: пользователь root; возможности chown,kill,setgid,setuid,net_admin; NoNewPrivs 1;
    своё пространство имён: да»; «интерфейсы внутри: fpi<номер>, fpt0, lo»;
  - снимок до подъёма: «маршрут по умолчанию внутри: нет; маршрутов к одному адресу: 1»;
    **«работники: openvpn от xgw-ovpn, возможности нет, NoNewPrivs 1»** — только OpenVPN:
    SOCKS-посредника до подъёма туннеля теперь нет; «xgw-ovpn: 750 root:xgw-ovpn; client.conf
    640 root:xgw-ovpn; …»; **«xgw-socks: нет»**;
  - «задание: 600 root:root; состояние: 600 root:root»; «секреты задания в state.json: нет»;
    «veth на хосте: есть; элементов fp_peers: 1»;
  - у поднявшегося, кроме того: «после подъёма: маршрут по умолчанию внутри: fpt0; …»; «после
    подъёма: работники: openvpn от xgw-ovpn, возможности нет, NoNewPrivs 1; xray от xgw-fps,
    возможности нет, NoNewPrivs 1»; «после подъёма: xgw-socks: 750 root:xgw-fps; socks.json 640
    root:xgw-fps»; **«изнутри: TCP Cloudflare:443 — …; DNS … — …»** и **«fpt0 (последнее): в
    туннель … пакетов, из туннеля … пакетов»** — **записать дословно**: это главный результат
    вехи для OpenVPN;
  - у каждого, где туннель поднимался: **«охрана после подъёма: OpenVPN 0, работник 0, ответы
    ядра …, служебный IPv6 …»**; **«канал к серверу после подъёма: от сервера N пакетов (X КБ),
    к серверу M пакетов (Y КБ)»** и строки «предупреждение OpenVPN: …» (если есть) — **записать
    дословно**: это ответ на главный вопрос вехи; у отказавшего до подъёма, если охрана что-то
    отбила, — «охрана за подключение: …» — записать.

Записать всё как есть.

Если не так:
- «ошибка: …» в ответе команды — записать дословно, **стоп**, сообщить заказчику;
- «поколений увидено: 0» — продолжить: шаги 3.2 и 4.1 покажут, идут ли подключения;
- у агента не root, другие возможности, NoNewPrivs не 1 или «своё пространство имён: НЕТ»; у
  службы нет `PrivateNetwork=yes` или `NoNewPrivileges=yes` — **дефект «изоляция поколения»**,
  **стоп**, сообщить заказчику;
- маршрут по умолчанию до подъёма не «нет» или после подъёма не `fpt0` — **дефект «маршрут мимо
  туннеля»**, **стоп**;
- работник от root, с возможностями или NoNewPrivs не 1 — **дефект «права работника»**,
  **стоп**;
- до подъёма в работниках есть `xray` или `xgw-socks` не «нет» — **дефект «посредник до
  туннеля»**;
- у поднявшегося нет строки «изнутри: …» — **дефект «нет проверки изнутри»**; в ней `TCP … —
  —` (нет итога) — **дефект «проверка изнутри не выполнилась»**;
- «туннель поднимался: да», а фазы up нет и причина `SOCKS_FAILED` — **дефект «посредник не
  запускается»** (шаг 4.1 покажет строку причины);
- в «охрана после подъёма» у OpenVPN или работника больше 0 — **дефект «посредник идёт мимо
  туннеля»**; «ответы ядра» и «служебный IPv6» — любые, не дефект;
- у поднимавшегося нет строки «канал к серверу после подъёма» — **дефект «канал к серверу не
  прочитан»**; в ней «от сервера» 8 КБ и больше, а «fpt0 (последнее): … из туннеля 0 пакетов» —
  **дефект «ответы сервера не доходят до туннеля»** (строки «предупреждение OpenVPN» — в
  отчёт); «от сервера» меньше 8 КБ — сервер или блокировка не пропускают данные после
  подъёма (подтверждения TCP и служебные пакеты OpenVPN — это до нескольких КБ): не дефект,
  записать;
- причина `GUARD_BLOCKED` — **дефект «охрана отбивает OpenVPN»** (строку «охрана за
  подключение» — в отчёт);
- «fpt0 (последнее): в туннель 0 пакетов» у поднявшегося — **дефект «в туннель ничего не
  уходит»**;
- права файлов шире (не 750/640/600) или владелец другой — **дефект «права файлов
  поколения»**; «секреты задания в state.json: ЕСТЬ» — **дефект «секрет в состоянии»**;
- «самопроверка НЕ пройдена» — **дефект «охрана пропускает»**, **стоп**;
- «агент: не найден» или строки «не прочитаны» — записать (поколение могло закончиться между
  опросами) и продолжить.

Шаг 3.2. Сразу после шага 3.1 — правила пула, списки (в том числе GitHub), бэкенд:

```bash
sleep 10; cd "$HOME/xgw-fp23" && for m in pool lists backend digest units files; do sudo python3 -I fpm23check.py $m; done | tee pool-1.txt; sudo xgw status 2>&1 | grep -E '^Состояние|^Бесплатный пул' | tee -a pool-1.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул' | tee -a pool-1.txt; sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm23check.py log | tee log-1.txt
```

Ожидается:
- «status.json: N с назад» (N меньше 120); «free_pool в состоянии: режим observe, регион EU;
  найдено … (из списков GitHub L, из них только sing-box S; Outline …; OpenVPN …)»: L — 150 или
  больше, S — 1 или больше; «трафик проверок за сутки: каталоги … из 512 МБ; серверы списков …
  МБ»; **«OpenVPN туннелем: годится; …»**;
- строки источников: `vpngate: SUCCESS`, `vpnbook: SUCCESS` (или `PARTIAL`), **`igareck:
  SUCCESS; …; вариантов` 50 или больше**, **`mahdibland: SUCCESS; …; вариантов` 100 или
  больше**;
- режим `lists`: у обоих «в providers: да»; «ядро и протокол: …» — у igareck есть `xray vless`
  и `sing-box hysteria2`, у mahdibland — `xray shadowsocks`; «страны по флагу: …» — записать;
  «причины отказа: …» — **записать все** (ожидаемые: «повтор», «схема ssr:// не принимается»,
  «адрес сервера — не публичный IPv4» и новые — то, чего Xray не примет: «шифр Shadowsocks … —
  Xray его не принимает», «ключ Shadowsocks 2022 не той длины», «flow VLESS … — убран из
  Xray», «транспорт HTTP/2 (h2) — убран из Xray, заменён XHTTP», «shortId REALITY — …», «ключ
  REALITY — …»); **«служебных IPv4: 0»** у обоих;
- «набор fp_peers: есть; элементов 0» (или 1); «бэкенд OpenVPN: годится»;
- «отпечаток таблиц: совпадает; … True»;
- «права снимков: 600 N»; «без варианта в снимках: …» — записать; «panel.json: режим пула:
  observe»;
- `Состояние: HEALTHY …`; строка `Бесплатный пул (наблюдение, регион EU): найдено …`;
- `OK    Бесплатный пул: режим observe; бэкенд OpenVPN готов (…)`;
- в журнале: «VPN Gate…», «VPNBook…», «igareck: список получен: 1», «mahdibland: список получен:
  1» (или больше); **«список получен через подписку: 4»** (или больше); «список получен
  напрямую: 0»; «шаг пула не выполнен: 0»; «Traceback: 0». «Правила загружены заново» —
  записать (0 — нормально: смена режима перезагружает правила без этой строки).

Записать всё как есть.

Если не так:
- «free_pool в состоянии: нет» — подождать 2 минуты и повторить шаг; снова нет — **дефект
  «наблюдение не включилось»**;
- «igareck» или «mahdibland: нет» или `UNAVAILABLE` — подождать 3 минуты и повторить; снова так
  — записать (GitHub мог не ответить через подписку) и продолжить; `SCHEMA_CHANGED` — **дефект
  «формат списка GitHub изменился»**, продолжить; «в providers: НЕТ» — записать (наблюдение: в
  config.toml свой список источников) и продолжить — тогда проверки серверов списков в шагах
  4–5 не оцениваются;
- вариантов меньше ожидаемого, но больше 0 — записать (списки меняются) и продолжить;
- «служебных IPv4» больше 0 — **дефект «адрес LAN в пуле»**;
- «бэкенд OpenVPN: …» с другой причиной — записать дословно, **дефект «бэкенд не годится»**;
- «список получен напрямую» больше 0 при `HEALTHY` — **дефект «списки не через подписку»**;
- «права снимков» не только 600 — **дефект «права снимков»** (в снимках списков — ссылки с
  ключами серверов);
- «правила загружены заново» больше 2 — **дефект «правила загружаются по кругу»**;
- «шаг пула не выполнен» или «Traceback» больше 0 — записать
  `sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -20 | tee traceback-1.txt`
  (только строки с файлами и ошибкой) — **дефект «шаг пула падает»**.

Шаг 3.3 (при согласии на пункт 3). **Попроси заказчика** (дословно):

«Откройте панель XGW, найдите карточку «Бесплатные серверы». Прочитайте мне первую фразу под
заголовком целиком и названия источников в списке под ней с метками (например «ок»).»

Ожидается: фраза «Наблюдение (регион EU): найдено N: из списков GitHub — L, ключей Outline — …,
OpenVPN — …, туннелем поднялось …, подключений за час …. Проверено …, пригодно …. Трафик
проверок за сутки — … из 512 МБ; серверы списков GitHub — … МБ, без предела.»; N и L — как в
`pool-1.txt` (могут отличаться на несколько); источники — «VPN Gate», «VPNBook», «GitHub igareck
(проверены в России)», «GitHub mahdibland» с метками как статусы в `pool-1.txt` («ок» —
SUCCESS, «частично» — PARTIAL, «недоступен» — UNAVAILABLE). Записать ответ.

Если не так: нет слов «из списков GitHub» или источников GitHub — попросить обновить страницу
(Ctrl+F5) и прочитать снова; снова нет — **дефект «карточка без списков GitHub»**.

## 4. Подключения и проверки

Шаг 4.1. Не раньше чем через 35 минут после шага 3.1:

```bash
cd "$HOME/xgw-fp23" && S=$(date -d "$(cat observe-time.txt)" +%s) && for m in "checks $S" pool units backend fwd files config; do sudo python3 -I fpm23check.py $m; done | tee checks-1.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm23check.py agentlog | tee agent-1.txt; sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm23check.py log | tee log-2.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee -a checks-1.txt
```

Ожидается (**записать все строки `checks` и `agentlog` целиком** — это итог вехи):
- «проверок с начала прогона: C (каталоги …, списки GitHub G; всего записей …); за последние 30
  минут: каталоги …, списки …»: G — 20 или больше (записи прошлых прогонов в C не входят);
- **серверы списков**: «списки GitHub: igareck xray OK …, igareck xray TIMEOUT …, igareck
  sing-box …, mahdibland xray …» — записать; «страны выхода работающих серверов списков: …» —
  записать; «причины «не проверено» у серверов списков: …» — **записать дословно** (у отказа
  временного процесса после двоеточия теперь его причина); «трафик одной проверки
  сервера списка, наибольший: X МБ», X не больше 1;
- **OpenVPN**: «OpenVPN туннелем: попыток A, поднялось U»; строки по источникам; «итоги через
  поднятый туннель», «отказы без туннеля»; **«изнутри, TCP Cloudflare:443: …»**, **«изнутри,
  DNS: …»**, **«из туннеля вернулось: …»**, **«охрана после подъёма отбила у OpenVPN или
  работника: 0 из …»**, **«туннель пропускает TCP, а проба через посредника — нет: B»** —
  записать; **«канал к серверу после подъёма, от сервера: …»** — записать; в «итогах через
  поднятый туннель» ожидаются итоги пробы (OK, SLOW, TIMEOUT, FROZEN…), а не `SOCKS_FAILED`; «подключений за час: H (…)», H не больше 4, у каждого источника не
  больше 2; «трафик одной проверки туннелем, наибольший: … МБ» не больше 20;
- «трафик проверок за сутки: каталоги … МБ» не больше 384; «серверы списков … МБ» — записать
  (предела нет; ожидается до ~20 МБ за час);
- сводка: «пригодно R (…)» — в скобках только `EU …` или «—»; «пригодные по источникам: …» —
  записать;
- «поколений xgw-fp@ сейчас: 0» или 1; «набор fp_peers: есть; элементов 0» (или 1); «veth fpv
  сейчас: 0» (или 1);
- «из fpv* к серверам пула: пакетов P»; **«из fpv* — сброс: пакетов 0»**;
- «записей проверок: …; без варианта в снимках: X» — X не больше 20; «временных Xray и
  sing-box сейчас: 0» (или 1);
- **«из них серверов бесплатного пула: 0; выходов к работникам пула: 0; серверов в конфиге
  sing-box: …, из них бесплатного пула: 0»** — трафик через пул не идёт;
- журнал поколений: «самопроверок охраны: S; итоги: …» — только `ENETUNREACH` и `… (охрана)`;
  **«туннель поднят: T; снова поднят: …; SOCKS-работник готов: W» — W равно T**; «проверок
  изнутри» и «итогов туннеля» — как T; строки «изнутри: …» и «итог туннеля: …» — **записать
  все**; «в туннель ушло 0 пакетов: 0»; **«после подъёма отбито у OpenVPN или работника
  больше 0: 0»**; «ответы ядра всего», «служебный IPv6 всего» — записать; «итогов без
  счётчиков охраны: 0»; **«канал к серверу после подъёма, от сервера: 0 пакетов — …, до 8 КБ —
  …, 8 КБ и больше — …; не прочитан — 0»** и строки «канал к серверу: …» — записать все;
  «итогов с предупреждениями OpenVPN: …» и строки «предупреждение OpenVPN: …» — записать все; «отказы поколений: …», «у GUARD_BLOCKED по журналу OpenVPN: …», строки
  «SOCKS_FAILED: …» и «охрана за подключение: строк …; OpenVPN …, работник …, ответы ядра …,
  служебный IPv6 …» — записать; строки «OpenVPN: …» — **записать все**; «строк с внешним
  адресом: 0»; «Traceback: 0»;
- журнал демона: «из них серверов списков: …» (как G или больше), «из них sing-box: …» (1 или
  больше), «с итогом изнутри туннеля: …» (как T), «Traceback: 0»;
- `HEALTHY`, перехват включён.

Если не так:
- G меньше 20 — подождать 10 минут и повторить; снова так — **дефект «серверы списков не
  проверяются»**;
- среди «причин «не проверено» у серверов списков» есть «нет sing-box» (при «sing-box для
  проверок: есть»), «Xray не запущен», «sing-box не запущен», «… завершился с кодом …» или «… не
  открыл порт» 3 раза и больше — **дефект «временный процесс проверки не запускается»**
  (конфиг не принят ядром; причины после двоеточия — в отчёт дословно); у «… завершился с
  кодом …» нет причины после двоеточия — **наблюдение «отказ ядра без причины»**; «имени
  сервера нет в DNS», «имя сервера не разрешилось», «у имени сервера нет публичного IPv4» —
  это списки, не дефект: записать;
- X больше 1 — **дефект «проверка сервера списка тратит много трафика»**;
- **B больше 0** — **дефект «туннель пропускает, а проба через посредника — нет»** (обрыв в
  шлюзе между пробой и посредником);
- «в туннель ушло 0 пакетов» больше 0 — **дефект «в туннель ничего не уходит»**;
- «после подъёма отбито у OpenVPN или работника больше 0» не 0 (или «охрана после подъёма
  отбила у OpenVPN или работника» не «0 из …») — **дефект «посредник идёт мимо туннеля»**;
  «ответы ядра» и «служебный IPv6» — не дефект: записать;
- «SOCKS-работник готов» меньше «туннель поднят» — **дефект «посредник не запускается»**
  (строки «SOCKS_FAILED: …» — в отчёт);
- «итогов без счётчиков охраны» больше 0 — **дефект «итог туннеля без охраны»**;
- «канал к серверу … не прочитан» больше 0 — **дефект «канал к серверу не прочитан»**;
- «8 КБ и больше» больше 0, а в «из туннеля вернулось» нет «больше 0» — **дефект «ответы
  сервера не доходят до туннеля»**; «0 пакетов» и «до 8 КБ» — сервер или блокировка, не
  дефект: записать;
- у `GUARD_BLOCKED` в «охрана за подключение» OpenVPN 0 — **дефект «ложный GUARD_BLOCKED»**;
- в отказах (сводка или журнал поколений) есть `GUARD_FAILED` или в итогах самопроверки есть
  что-то кроме `ENETUNREACH` и `(охрана)` — **дефект «охрана пропускает»**, **стоп**, сообщить
  заказчику;
- в отказах есть `GUARD_BLOCKED`, `NETWORK_UNREACHABLE`, `BACKEND_START`, `NO_VETH`, `NO_USER`,
  `BAD_MANIFEST`, `AGENT_ERROR`, `AGENT_EXITED`, `NO_MANAGEMENT`, `CONFIG_REJECTED`,
  `TUN_FAILED`, `NO_TUNNEL_ADDRESS` или `SOCKS_FAILED` — **дефект «бэкенд OpenVPN: <код>»**
  (строки «OpenVPN: …» — в отчёт), продолжить; `HOST_UNREACHABLE`, `TLS_HANDSHAKE_FAILED`,
  `CONNECT_TIMEOUT`, `CONNECT_REFUSED`, `TRANSPORT_RESET`, `TIMEOUT`, `AUTH_FAILED`,
  `CERT_VERIFY_FAILED`, `UNSUPPORTED_CRYPTO`, `UNKNOWN` — сервер или сеть (ТСПУ), не дефект:
  записать; у `UNKNOWN` строки «OpenVPN: …» нет — **наблюдение «UNKNOWN без строки»**;
- изнутри `TIMEOUT` у TCP и «из туннеля вернулось: 0 пакетов» — это сервер или блокировка
  OpenVPN за туннелем, не дефект: записать;
- H больше 4 или у источника больше 2 — **дефект «пределы подключений не соблюдены»**;
- «из fpv* — сброс» больше 0 — **дефект «из пространства имён уходит мимо сервера»**;
- поколений, veth или каталогов 2 и больше — повторить через 2 минуты; снова так — **дефект
  «поколения не убираются»**;
- в скобках у «пригодно» есть не `EU` — **дефект «регион не строгий»**;
- X (без варианта в снимках) больше 20 — **дефект «итоги пропавших серверов не убираются»**;
- серверы бесплатного пула или выходы к работникам в рабочих конфигах больше 0 — **дефект «пул
  попал в рабочий конфиг»**, **стоп**, сообщить заказчику;
- «трафик проверок за сутки: каталоги» больше 384 — **дефект «бюджет каталогов не соблюдён»**;
- «строк с внешним адресом» больше 0 — **наблюдение** (адрес в журнале службы); строки не
  переписывать.

Шаг 4.2. Не раньше чем через 65 минут после шага 3.1 — второй час:

```bash
cd "$HOME/xgw-fp23" && S=$(date -d "$(cat observe-time.txt)" +%s) && for m in "checks $S" pool units backend fwd files; do sudo python3 -I fpm23check.py $m; done | tee checks-2.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm23check.py agentlog | tee agent-2.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee -a checks-2.txt
```

Ожидается: «проверок с начала прогона: … (каталоги …, списки GitHub G2; …)», G2 больше G; «OpenVPN туннелем:
попыток A2, …», A2 больше A (если в 4.1 у каждого источника было по 2 за час); «подключений за
час: …» не больше 4, у источника не больше 2; остальное — как в шаге 4.1. Записать всё.

Если не так: как в шаге 4.1. G2 равно G — **дефект «проверки серверов списков остановились»**;
A2 равно A — повторить через 10 минут (часовой предел мог быть занят); снова равно —
**дефект «подключения OpenVPN остановились»**.

## 5. Сводка в команде

Шаг 5.1 (при согласии на пункт 3). Сводка команды и панели — одна:

```bash
cd "$HOME/xgw-fp23" && sudo xgw pool 2>&1 | head -7 | tee cli.txt; sudo xgw pool status --json | python3 -c "import json,sys;d=json.load(sys.stdin);print('json:', d['mode'], d['found'], d.get('lists'), d['checked'], d['ready'], d['tunnels_up'], d.get('lists_spent_mb'))" | tee -a cli.txt
```

Затем **попроси заказчика** (дословно): «Прочитайте ещё раз из карточки «Бесплатные серверы»
числа после слов «найдено», «из списков GitHub», «туннелем поднялось» и «Проверено».»

Ожидается: строки «Бесплатный пул: наблюдение (трафик через подписку); регион EU (строго)»,
«Найдено N: из списков GitHub L (из них только sing-box S), Outline …, OpenVPN …» — **без
слов «проверка туннелем недоступна»**; «OpenVPN туннелем: поднялось U…»; «Проверено C, …»;
«Пригодные по источникам: …» (если пригодные есть); «Трафик проверок за сутки: … из 512 МБ;
серверы списков GitHub — … МБ (без предела)»; «json: observe N L C R U …»; числа заказчика —
как N, L, U и C (могут отличаться на несколько: проверки идут). Записать.

Если не так: в строке «Найдено» есть «проверка туннелем недоступна: ещё не проверялся» —
**дефект «xgw pool не берёт сводку демона»**; команда отвечает ошибкой — **дефект «xgw pool»**;
числа заказчика отличаются больше чем на 10 (U — больше чем на 1) — **дефект «сводка панели и
команды расходится»**.

## 6. Секреты

Шаг 6.1.

```bash
cd "$HOME/xgw-fp23" && sudo python3 -I fpm23check.py files | tee secrets.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm23check.py leak | sed 's/^/xgw: /' | tee -a secrets.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm23check.py leak | sed 's/^/xgw-fp@: /' | tee -a secrets.txt; stat -c 'status.json: %a' /run/xgw/status.json | tee -a secrets.txt
```

Ожидается: права 700/600/600, снимки 600, профили 600; у обеих строк «паролей источников
известно: 1» (0 — если VPNBook не ответил); **«строк с паролем: 0; строк со ссылкой сервера: 0;
строк OpenVPN с настройками: 0»**; «status.json: 644». Записать.

Если не так: строк с паролем, ссылкой или настройками OpenVPN больше 0 — **дефект «секрет в
журнале»** (ссылки серверов списков несут их ключи).

## 7. Выключение

Шаг 7.1 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В карточке «Бесплатные серверы» нажмите «Выключить». Что ответила панель и что теперь
написано в карточке и на кнопке?»

Сразу после ответа:

```bash
cd "$HOME/xgw-fp23" && sleep 60; date '+%F %T' | tee off-time.txt; sleep 120; for m in pool units backend files; do sudo python3 -I fpm23check.py $m; done | tee off.txt; sudo xgw pool 2>&1 | head -1 | tee -a off.txt; sudo xgw status 2>&1 | grep -c '^Бесплатный пул' | sed 's/^/строк «Бесплатный пул» в xgw status: /' | tee -a off.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул' | tee -a off.txt
```

Ожидается: ответ панели — «Бесплатный пул выключен»; в карточке — «Альтернативный режим:
бесплатные серверы (списки GitHub, VPN Gate, VPNBook) вместо подписки. …», на кнопке —
«Включить наблюдение»; «free_pool в состоянии: нет»; «поколений xgw-fp@ сейчас: 0; процессов
openvpn XGW: 0»; «набор fp_peers: нет»; «veth fpv сейчас: 0; каталогов поколений: 0»;
«временных Xray и sing-box сейчас: 0»; «Бесплатный пул: выключен; …»; «строк «Бесплатный пул»
в xgw status: 0»; `OK    Бесплатный пул: выключен — режим подписок`. Записать.

Если не так: «free_pool в состоянии: режим …» — подождать 2 минуты и повторить; снова так —
**дефект «наблюдение не выключается»**. Поколения, veth, каталоги, процессы openvpn XGW или
временные процессы больше 0 — повторить через 2 минуты; снова так — **дефект «пул оставил
следы»**. «набор fp_peers: есть» — **дефект «правила пула остались»**.

## 8. Итог

Шаг 8.1. Через 3 минуты после шага 7.1:

```bash
sleep 180; cd "$HOME/xgw-fp23" && sudo journalctl -u xgw --since "$(cat off-time.txt)" --no-pager | sudo python3 -I fpm23check.py log | tee log-off.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm23check.py log | tee final.txt; S=$(date -d "$(cat observe-time.txt)" +%s); for m in "checks $S" lists digest subs config units; do sudo python3 -I fpm23check.py $m; done | tee -a final.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm23check.py agentlog | tee agent-final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee -a final.txt
```

Ожидается:
- в `log-off.txt` (с минуты после нажатия «Выключить»): все «список получен» — 0, «проверок
  серверов пула: 0»;
- в `final.txt`: **«Traceback: 0»**, «шаг пула не выполнен: 0», **«следы поколения не убраны:
  0»**, «правила загружены заново» — не больше 2, «откат на last-good: 0», «Read-only file
  system» и «Permission denied» — не больше, чем в `log-before.txt`;
- итог проверок (`checks`) и списков (`lists`) — записать целиком: это итог вехи;
- «отпечаток таблиц: совпадает; … True»; «подписок с ошибкой» — не больше, чем до установки;
  «серверов в списке» — как до установки (±2); в рабочих конфигах серверов пула — 0;
  «поколений xgw-fp@ сейчас: 0»;
- `agent-final.txt`: «отказы поколений» без `GUARD_FAILED`; «SOCKS-работник готов» — как
  «туннель поднят»; «Traceback: 0»;
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки.

Если не так: опросы или проверки после выключения больше 0 — **дефект «пул работает
выключенным»**; Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -30 | tee traceback.txt`
(только строки с файлами и ошибкой, адреса — убрать); «следы поколения не убраны» больше 0 —
**дефект «поколение убрано не до конца»**; «правила загружены заново» больше 2 — **дефект
«правила загружаются по кругу»**. Сообщить заказчику.

Повторная установка в этой вехе не проверяется: установщик не менялся, и в М2а она прошла.

Шаг 8.2 (при согласии на пункт 4). **Попроси заказчика** (дословно):

«Откройте любой сайт на этом компьютере и любой сайт на телефоне. Открываются?»

Ожидается: «да». Нет — записать ответ дословно и
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt`,
сообщить заказчику.

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.
- Заказчик просит остановить проверку — попросить его нажать «Выключить» в карточке
  «Бесплатные серверы» и выполнить шаги 7.1 и 8.1; службы `xgw-fp@*` руками не трогать.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-m2a3-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`freepool`), коммит «Отчёт: XGW 0.2.0, бесплатные серверы, веха М2а.3», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, бесплатные серверы, веха М2а.3 (посредник без системного DNS, канал к серверу)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
fpm23check.py: <сумма, 16 знаков>.

## Итог вехи
### Списки GitHub
| Источник | Вариантов | Отсеяно «Xray не примет» | Проверено | Работают (OK/SLOW) | Пригодны (EU) | Страны выхода | Главные отказы |
|---|---|---|---|---|---|---|---|
| igareck | … | … | … | … | … | … | … |
| mahdibland | … | … | … | … | … | … | … |

### OpenVPN
| Источник | Попыток | Туннель поднимался | Дошло до up | Изнутри TCP | Изнутри DNS | Из туннеля вернулось | Канал после подъёма: от сервера / к серверу | Предупреждения OpenVPN | Охрана после подъёма (OpenVPN/работник) | Итоги пробы | Отказы без туннеля |
|---|---|---|---|---|---|---|---|---|---|---|---|
| vpngate | … | … | … | … | … | … | … | … | … | … | … |
| vpnbook | … | … | … | … | … | … | … | … | … | … | … |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | сумма, состояние, службы, снимки, отпечаток, подписки, журнал |
| 1.3 выключение прошлого наблюдения | … / не нужен | кто выключил (кнопка или команда), ответ панели, следы |
| 2.2 установка | … | код, строки установки |
| 2.3 после установки | … | HEALTHY, бэкенд, sing-box, срок 35 с, xgw pool, diag |
| 3.1 живые поколения | … | поколений / туннель поднимался / дошло до up; после — посредник, изнутри, fpt0, канал к серверу, предупреждения OpenVPN, охрана после подъёма |
| 3.2 правила и списки | … | источники (4), списки GitHub (ядра, протоколы, отказы, служебных IPv4), бэкенд, права снимков, журнал |
| 3.3 карточка | … / не выполнялся | фраза, источники и метки |
| 4.1 проверки, 35 мин | … | списки: проверено/итоги/причины/страны/трафик; OpenVPN: попытки, туннель/up, посредник готов, изнутри, из туннеля, охрана, B, коды; пределы; рабочие конфиги |
| 4.2 проверки, 65 мин | … | то же |
| 5.1 xgw pool | … / не выполнялся | строки, json, числа заказчика |
| 6.1 секреты | … | права, пароли, ссылки и настройки OpenVPN в журналах |
| 7.1 выключение | … / не выполнялся | ответ панели, карточка, следы |
| 8.1 итог | … | после выключения, Traceback, следы, правила, конфиги, HEALTHY |
| 8.2 сайты | … / не выполнялся | ответ заказчика |

## Выводы шагов
<файлы $HOME/xgw-fp23/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
