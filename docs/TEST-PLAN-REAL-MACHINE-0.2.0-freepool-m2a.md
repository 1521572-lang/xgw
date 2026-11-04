# Проверка XGW 0.2.0: бесплатные серверы, веха М2а (OpenVPN туннелем, наблюдение)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-fp2/…`). Файл помощника создавай только командой шага 1.2, выполненной в терминале.
Блок команды копируй целиком, ничего в нём не меняя (в ТЗ М1 лишняя скобка при переносе
изменила сумму помощника).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0 (в ней же анти-ТСПУ 2.0, уже в
`main`). Телефон — S25 Ultra в домашней сети. Команды — в терминале сеанса заказчика (`sudo`
от его имени).

Что нового (ASSUMPTIONS п. 257, README «Бесплатные серверы»):
1. **Серверы OpenVPN проверяются настоящим подключением**, всё ещё в режиме наблюдения: трафик
   устройств идёт через подписку, как сейчас. Каждое подключение — отдельная служба
   `xgw-fp@<поколение>` в изолированном пространстве имён: OpenVPN и SOCKS-посредник — от своих
   пользователей `xgw-ovpn` и `xgw-fps` без прав; наружу — только к адресу, протоколу и порту
   одного сервера. Перед подключением служба проверяет свою охрану. Подключений — не больше 2 в
   час к каждому источнику (12 в час всего, 60 в сутки).
2. Установка ставит пакет `openvpn` (из репозитория Ubuntu), двух системных пользователей без
   входа и шаблон службы `xgw-fp@`; при включённом ufw — правило `route allow in on fpv+`.
3. **VPNJantit убран** (решение по отчёту М1): источники — VPN Gate и VPNBook; поля «Выданные
   ссылки» в карточке больше нет; старые снимки VPNJantit шлюз удаляет сам.
4. `sudo xgw diag` — новая строка «Бесплатный пул».

Здесь, у разработчика, — только юнит-тесты и ruff (решение заказчика: проверок у разработчика
— минимум). Всё остальное проверяется на этой машине: установка и повторная установка, бэкенд
OpenVPN, правила, **живое поколение** (изоляция службы и работников, маршрут только через
туннель, права файлов, секреты), подключения, журналы, панель, выключение. Настоящий OpenVPN —
впервые на этой машине.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `openvpn*`,
  `tailscaled`, NetworkManager, `ssh`; ручные `nft` (кроме `nft list`), `ip` (кроме чтения
  помощником), `ip netns`, `nsenter`, `iptables`, `tc`, `sysctl -w`, `systemd-run`; команды
  `tailscale`, `xray` и `openvpn`. `sudo xgw pool mode …` — только в шаге 3.1.
- Самому открывать сайты источников (vpngate, vpnbook) — в браузере, `curl`, `wget` и как
  угодно ещё. Их открывает только сам шлюз.
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, `/etc/openvpn`, код XGW. Печатать `config.toml`, `panel.json`,
  файлы в `/var/lib/xgw/freepool` и `/run/xgw/fp` (`cat`, `less`, `grep` по ним) — в них ключи
  подписок, учётки и пароли. Серверы, переключатели и кнопки в панели меняет и нажимает только
  заказчик. Коммитить что-либо, кроме отчёта (§9).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP, домены и ссылки
  серверов VPN (и бесплатных тоже), логины и пароли, строки журнала. Можно: адреса устройств в
  домашней сети (`192.168.…`), коды стран, названия источников, счётчики, статусы, коды причин,
  размеры, права файлов, времена, версии пакетов и строки помощника «OpenVPN: …» (адреса в них
  уже заменены на `<ip>`).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю проверку бесплатных серверов OpenVPN настоящим подключением (веха М2а). По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд. Установка поставит пакет openvpn из репозитория
Ubuntu и двух системных пользователей без входа (xgw-ovpn, xgw-fps). Внешний интерфейс (WAN),
его соединение и DHCP установка не трогает: меняются только профиль LAN, свои таблицы nftables
и свои службы.
(2) Я включу наблюдение командой `sudo xgw pool mode observe`. Трафик идёт через подписку, как
сейчас, а шлюз будет подключаться к бесплатным серверам OpenVPN в изолированной службе — не
больше 2 раз в час к каждому источнику. Проверка займёт около полутора часов. В конце вы
выключите наблюдение кнопкой «Выключить» в карточке «Бесплатные серверы» панели XGW.
(3) В панели по моей просьбе прочитаете мне сводку из карточки «Бесплатные серверы».
(4) В конце откроете любой сайт на этом компьютере и на телефоне.
(5) В конце — ещё одна переустановка тем же кодом (проверка, что повторная установка ничего не
создаёт заново): интернет дома ещё раз пропадёт на несколько секунд.
Можно согласиться не на все пункты.»

Против пункта 1 или 2 — **стоп**. Против 3 — шаги 3.3 и 5.1 пропустить; против 4 — шаг 8.3;
против 5 — шаг 8.2. Если против 2 только выключение кнопкой — шаг 7.1 пропустить. В отчёте у
пропущенного — «не выполнялся».

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-fp2" && chmod 700 "$HOME/xgw-fp2" && cd "$HOME/xgw-fp2" && cat > fpm2check.py <<'EOF'
"""XGW 0.2.0, бесплатный пул (веха М2а, OpenVPN туннелем в наблюдении): помощник проверки.
Только читает: состояние XGW (/run/xgw, /var/lib/xgw/freepool, рабочий конфиг Xray), бэкенд
OpenVPN (пакет, пользователи, служба, пересылка IPv4, набор fp_peers, ufw, veth) и журналы со
стандартного ввода — счётчики, коды, права и да/нет, без адресов, имён, ссылок и паролей.
watch — живые поколения: свойства службы, возможности и пространство имён агента и работников
(/proc), интерфейсы и маршруты внутри (/proc/<pid>/net), права файлов в /tmp службы, секреты в
состоянии; ничего не меняет и в пространство имён не входит.
Режимы: units, backend, pool, checks, files, config, leak, digest, subs, fwd, log, agentlog,
watch."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("FPM2_LIB", "/opt/xgw/lib")
DAY = 86400.0
HOUR = 3600.0
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
NOT_TUNNEL = ("REACHABLE", "CLOSED", "UNTESTED")
CAPS = {0: "chown", 1: "dac_override", 2: "dac_read_search", 3: "fowner", 4: "fsetid",
        5: "kill", 6: "setgid", 7: "setuid", 8: "setpcap", 10: "net_bind_service",
        12: "net_admin", 13: "net_raw", 16: "sys_module", 19: "sys_ptrace", 21: "sys_admin"}
RANK = {"guarded": 1, "connecting": 2, "up": 3}


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


def records(paths):
    data = read_json(paths.var / "freepool" / "candidates.json") or {}
    found = {key: value for key, value in data.items()
             if not key.startswith("_") and isinstance(value, dict)}
    return found, data


def counted(items):
    found = {}
    for item in items:
        found[item] = found.get(item, 0) + 1
    return ", ".join(f"{name} {count}" for name, count in sorted(found.items())) or "—"


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
    workers = []
    for entry in Path("/proc").iterdir() if ns else ():
        if not entry.name.isdigit() or entry.name == pid or netns(entry.name) != ns:
            continue
        info = proc_status(entry.name)
        if info.get("Name", "").startswith("python"):
            continue  # проба самопроверки охраны
        owner = account((info.get("Uid") or "?").split()[0])
        workers.append(f"{info.get('Name', '?')} от {owner}, возможности "
                       f"{caps(info.get('CapEff', '0'))}, NoNewPrivs "
                       f"{info.get('NoNewPrivs', '?')}")
    lines.append("работники: " + ("; ".join(sorted(workers)) or "нет"))
    tmp = Path(f"/proc/{pid}/root/tmp")
    for name, files in (("xgw-ovpn", ("client.conf", "auth")), ("xgw-socks", ("socks.json",))):
        items = [describe(tmp / name)] + [f"{item} {describe(tmp / name / item)}"
                                          for item in files if (tmp / name / item).exists()]
        lines.append(f"{name}: " + "; ".join(items))
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
          f"/usr/sbin/openvpn: {'есть' if Path('/usr/sbin/openvpn').exists() else 'нет'}")
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
    _code, text = run(["systemd-analyze", "security", "--no-pager", "xgw-fp@0000000000.service"])
    level = [line for line in text.splitlines() if "Overall exposure level" in line]
    print("оценка systemd службы xgw-fp@: "
          + (level[-1].split(":", 1)[1].strip() if level else "не получена"))
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
    print(f"free_pool в состоянии: режим {pool.get('mode')}, регион {pool.get('region')}; "
          f"найдено {pool.get('found')} (Outline {pool.get('supported_now')}, OpenVPN "
          f"{pool.get('openvpn')}); проверено {pool.get('checked')}, пригодно {pool.get('ready')} "
          f"({regions}); трафик проверок {pool.get('spent_mb')} из {pool.get('budget_mb')} МБ")
    problem = pool.get("openvpn_backend") or ""
    failures = ", ".join(f"{code} {count}" for code, count in
                         sorted((pool.get("tunnel_failures") or {}).items())) or "—"
    print(f"OpenVPN туннелем: {'годится' if not problem else 'недоступно — ' + problem}; "
          f"поднялось {pool.get('tunnels_up')}; отказы: {failures}; подключений за час "
          f"{pool.get('handshakes_hour')}, за сутки {pool.get('handshakes_day')}; адрес открыт "
          f"{pool.get('reachable_openvpn')}, закрыт {pool.get('closed')}")
    now = time.time()
    for source in pool.get("sources") or []:
        when = source.get("retrieved_at")
        got = f"{int((now - float(when)) // 60)} мин назад" if when else "нет"
        print(f"  {source.get('id')}: {source.get('status')}; список — {got}; вариантов "
              f"{source.get('variants')}; устарел: {'да' if source.get('stale') else 'нет'}")
elif mode == "checks":
    _cfg, paths = xgw()
    found, data = records(paths)
    now = time.time()
    recent = sum(1 for record in found.values()
                 if now - float(record.get("checked_at") or 0) < 1800)
    print(f"проверок всего: {len(found)}; за последние 30 минут: {recent}")
    for line in counted(f"{record.get('backend')} {record.get('verdict')}"
                        for record in found.values()).split(", "):
        print(f"  {line}")
    attempts = [record for record in found.values() if record.get("backend") == "openvpn"
                and record.get("verdict") not in NOT_TUNNEL]
    up = [record for record in attempts if record.get("tunnel_up")]
    seconds = sorted(float(record.get("connect_seconds") or 0) for record in up)
    print(f"OpenVPN туннелем: попыток {len(attempts)}, поднялось {len(up)}"
          + (f"; подключение — от {seconds[0]:.1f} до {seconds[-1]:.1f} с" if seconds else ""))
    for provider in sorted({str(record.get("provider")) for record in attempts}):
        mine = [record for record in attempts if record.get("provider") == provider]
        print(f"  {provider}: попыток {len(mine)}, поднялось "
              f"{sum(1 for record in mine if record.get('tunnel_up'))}")
    print("итоги через поднятый туннель: "
          + counted(str(record.get("verdict")) for record in up))
    print("отказы без туннеля: "
          + counted(str(record.get("verdict")) for record in attempts
                    if not record.get("tunnel_up")))
    print("причины «не проверено» у OpenVPN: " + counted(
        IPV4.sub("<ip>", str(record.get("error") or "—")).split(":")[0][:50]
        for record in found.values()
        if record.get("backend") == "openvpn" and record.get("verdict") == "UNTESTED"))
    biggest = max((int(record.get("bytes") or 0) for record in attempts), default=0)
    print(f"трафик одной проверки туннелем, наибольший: {biggest / 1048576:.1f} МБ")
    items = [item for item in (data.get("_handshakes") or {}).get("items") or []
             if isinstance(item, list) and len(item) == 2]
    hour = [item for item in items if now - float(item[0]) < HOUR]
    day = [item for item in items if now - float(item[0]) < DAY]
    print(f"подключений за час: {len(hour)} ({counted(str(item[1]) for item in hour)}); "
          f"за сутки: {len(day)}")
    print("страны выхода пригодных: " + counted(
        str(record.get("egress_country") or "?") for record in found.values()
        if record.get("verdict") in ("OK", "SLOW")))
    ledger = (data.get("_ledger") or {}).get("items") or []
    spent = sum(int(item[1]) for item in ledger
                if isinstance(item, list) and now - float(item[0]) < DAY)
    print(f"трафик проверок за сутки: {spent / 1048576:.1f} МБ")
elif mode == "files":
    _cfg, paths = xgw()
    base = paths.var / "freepool"
    snapshots = sorted((base / "snapshots").glob("*.json")) if (base / "snapshots").exists() \
        else []
    print(f"каталог freepool: {perm(base)}; secrets.json: {perm(base / 'secrets.json')}; "
          f"candidates.json: {perm(base / 'candidates.json')}; снимков списков: "
          f"{len(snapshots)} ({counted(path.name.split('.')[0] for path in snapshots)})")
    profiles = sorted((base / "profiles").glob("*.ovpn")) if (base / "profiles").exists() \
        else []
    print(f"профилей VPNBook: {len(profiles)}; каталог profiles: {perm(base / 'profiles')}; "
          f"права профилей: {counted(perm(path) for path in profiles)}")
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
    print(f"временных каталогов проверок: {left}; временных Xray сейчас: {running}")
    from xgw import managed

    panel = read_json(managed.path_for(paths.config_file)) or {}
    print(f"panel.json: поле ссылок пула: {'ЕСТЬ' if 'free_pool_links' in panel else 'нет'}; "
          f"режим пула: {panel.get('free_pool_mode') or '—'}")
elif mode == "config":
    cfg, paths = xgw()
    from xgw.freepool.store import PoolStore

    store = PoolStore(paths)
    variants = [variant for provider in cfg.free_pool.providers
                for variant in store.variants(provider)]
    hosts = {name.lower() for variant in variants for name in (variant.host, variant.address)
             if name}
    work = read_json(paths.xray_config_file) or {}
    total = matched = workers = 0
    for outbound in work.get("outbounds") or []:
        settings = outbound.get("settings") or {}
        entries = [*(settings.get("vnext") or []), *(settings.get("servers") or []), settings]
        for entry in entries:
            address = entry.get("address") if isinstance(entry, dict) else None
            if isinstance(address, str) and address:
                total += 1
                matched += address.lower() in hosts
                workers += address.startswith("10.250.")
    print(f"адресов серверов в рабочем конфиге Xray: {total}; из них серверов бесплатного пула: "
          f"{matched}; выходов к работникам пула: {workers}; вариантов в пуле: {len(variants)}")
elif mode == "leak":
    _cfg, paths = xgw()
    secrets = read_json(paths.var / "freepool" / "secrets.json") or {}
    words = [str(value) for record in (secrets.get("shared") or {}).values()
             if isinstance(record, dict) for key, value in record.items()
             if key == "password" and value]
    lines = sys.stdin.read().splitlines()
    hits = sum(1 for line in lines if any(word in line for word in words))
    raw = sum(1 for line in lines if "vless://" in line or "ss://" in line or "trojan://" in line)
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
        ("список получен через подписку", ("(через подписку), вариантов",)),
        ("список получен напрямую", ("(напрямую), вариантов",)),
        ("источник не ответил", ("прежний снимок остаётся",)),
        ("проверок серверов пула", ("бесплатный пул: проверка",)),
        ("из них OpenVPN", ("(openvpn, ",)),
        ("шаг пула не выполнен", ("бесплатный пул: шаг не выполнен",)),
        ("снимки убранных источников удалены", ("удалены снимки убранных источников",)),
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
    print(f"туннель поднят: {sum(1 for line in lines if 'туннель поднят' in line)}")
    codes = [match.group(1) for line in lines
             for match in [re.search(r"поколение [0-9a-f]{10}: ([A-Z_]+) —", line)] if match]
    print(f"отказы поколений: {counted(codes)}")
    evidence = [IPV4.sub("<ip>", line.split("OpenVPN: ", 1)[1])[:160] for line in lines
                if "OpenVPN: " in line]
    for text in list(dict.fromkeys(evidence))[:8]:
        print(f"  OpenVPN: {text}")
    outer = sum(1 for line in lines if "OpenVPN: " not in line and any(
        not address.startswith(("10.250.", "127.")) for address in IPV4.findall(line)))
    print(f"строк с внешним адресом: {outer}; Traceback: "
          f"{sum(1 for line in lines if 'Traceback' in line)}")
elif mode == "watch":
    _cfg, paths = xgw()
    limit = float(sys.argv[2]) if len(sys.argv) > 2 else 480.0
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
                                                    "up": "", "reason": "", "selftest": "—"})
            phase = str(state.get("phase") or "")
            if phase and (not info["phases"] or info["phases"][-1] != phase):
                info["phases"].append(phase)
            if state.get("reason"):
                info["reason"] = str(state["reason"])
            if isinstance(state.get("selftest"), dict):
                info["selftest"] = "пройдена" if state["selftest"].get("ok") else "НЕ пройдена"
            rank = RANK.get(phase, 0)
            if rank > info["rank"]:
                if rank <= 2 or not info["full"]:
                    info["full"] = snapshot(paths, directory.name, host_ns)
                if rank == 3:
                    info["up"] = routes(show(f"xgw-fp@{directory.name}.service", "MainPID"))
                info["rank"] = rank
        time.sleep(0.5)
    up = sum(1 for info in seen.values() if "up" in info["phases"])
    print(f"поколений увидено: {len(seen)}; поднялось: {up}")
    for number, info in enumerate(seen.values(), 1):
        print(f"поколение {number}: фазы {' → '.join(info['phases']) or '—'}; самопроверка "
              f"{info['selftest']}; причина отказа: {info['reason'] or '—'}")
        for line in info["full"]:
            print(f"  {line}")
        if info["up"]:
            print(f"  после подъёма: {info['up']}")
else:
    print("режим: units | backend | pool | checks | files | config | leak | digest | subs | fwd"
          " | log | agentlog | watch")
EOF
python3 -c "import hashlib;d=open('fpm2check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул' | tee before.txt; for m in units files digest subs; do sudo python3 -I fpm2check.py $m; done | tee state-before.txt; sudo journalctl -u xgw --since "60 min ago" --no-pager | sudo python3 -I fpm2check.py log | tee log-before.txt
```

Ожидается:
- `0d9d6a4b827ac706`;
- `Состояние: HEALTHY …`, `Перехват: включён …`, строки `Xray …` и `sing-box …`, строки
  `Бесплатный пул` нет — записать как есть;
- четыре службы `active`; «поколений xgw-fp@ сейчас: 0 (—); процессов openvpn XGW: 0; других
  openvpn: …; openvpn.service: …» — записать (пакета openvpn ещё может не быть — «нет»);
- «каталог freepool: 700; …; снимков списков: N (…)» — снимки с проверки М1, записать;
  «отпечаток таблиц: совпадает; правила на месте (loaded): True»; «подписок с ошибкой: …;
  серверов в списке: …» — записать;
- счётчики журнала — записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать и продолжить. «других openvpn» больше 0
— записать (наблюдение: на машине уже работает свой OpenVPN) и продолжить.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && test -f src/xgw/freepool/agent.py && test -f packaging/xgw-fp@.service && grep -q 'def unavailable' src/xgw/freepool/backend.py && grep -q 'def _free_pool' src/xgw/diag.py && ! grep -q 'VPNJANTIT' src/xgw/freepool/providers.py && echo "правка в коде: есть"; cd "$HOME/xgw-fp2"
```

Ожидается: «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. Внешний интерфейс (WAN), его
соединение и DHCP она не трогает; интернет дома пропадёт на несколько секунд, пока
перезапускаются службы XGW. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fp2/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fp2/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'пакеты:|пользователь xgw-|ufw:|перезапущен|Xray запущен' "$HOME/xgw-fp2/install.txt"; cd "$HOME/xgw-fp2"
```

Ожидается: «код 0», «демон xgw запущен», «Xray запущен: участников …»; «пакеты: openvpn» (если
пакета не было), «пользователь xgw-ovpn», «пользователь xgw-fps»; при включённом ufw — строка
«ufw: …» с `route allow in on fpv+`. Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать). Нет
строки «пакеты: openvpn» — смотри шаг 2.3 (пакет мог стоять заранее).

Шаг 2.3. Через 2 минуты — шлюз в порядке, бэкенд поставлен, пул выключен:

```bash
sleep 120; cd "$HOME/xgw-fp2" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул' | tee after-install.txt; for m in units backend digest files pool; do sudo python3 -I fpm2check.py $m; done | tee -a after-install.txt; sudo xgw pool 2>&1 | head -1 | tee -a after-install.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул|Конфиг|^Итог' | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm2check.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки, строки
  `Бесплатный пул` нет; четыре службы `active`; «поколений xgw-fp@ сейчас: 0»;
- «пакет openvpn: <версия>; /usr/sbin/openvpn: есть»; «пользователь xgw-ovpn: есть,
  системный, оболочка /usr/sbin/nologin» и так же у xgw-fps; «служба xgw-fp@.service: есть»;
  «пересылка IPv4: 1»; «набор fp_peers: нет» (пул выключен — правил пула нет); «veth fpv
  сейчас: 0; каталогов поколений: 0»; «ufw: …» — записать; «бэкенд OpenVPN: в правилах XGW нет
  набора fp_peers — перехват не загружен» (так и должно быть при выключенном пуле);
  «оценка systemd службы xgw-fp@: <число> <OK или MEDIUM> …» — записать;
- «отпечаток таблиц: совпадает; … True»;
- «снимков списков: N (vpnbook …, vpngate …)» — **без vpnjantit**;
- «free_pool в состоянии: нет»; «Бесплатный пул: выключен; регион EU (строго)»;
- `OK    Бесплатный пул: выключен — режим подписок`; строка `Конфиг` — без слов
  `free_pool` и `VPNJantit`; строка `Итог: …` — записать;
- в журнале с установки: «снимки убранных источников удалены: 1» (0 — если снимков VPNJantit
  уже не было), «Traceback: 0».

Если не так:
- не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать, сообщить заказчику и
  продолжить;
- «пакет openvpn: нет», нет пользователя или службы — **дефект «установка не поставила
  бэкенд»**, **стоп**;
- пользователь «НЕ системный» или оболочка не nologin — **дефект «пользователь работника»**;
- «пересылка IPv4: 0» — **стоп**, сообщить заказчику (у шлюза с LAN она должна быть 1);
- «ufw: включён; правило fpv+: НЕТ» — **дефект «ufw: нет правила для туннелей»**;
- в снимках есть vpnjantit — **дефект «снимки VPNJantit не удалены»**;
- в строке `Конфиг` есть `free_pool` или `VPNJantit` — записать дословно (наблюдение: в
  config.toml остались ключи прошлых версий);
- «оценка systemd …» — `EXPOSED` или `UNSAFE` — записать (наблюдение), «не получена» —
  записать и продолжить;
- отпечаток не совпадает — повторить через минуту, снова так — **дефект «отпечаток таблиц
  меняется сам»**.

## 3. Включение наблюдения

Шаг 3.1. Включить и сразу 8 минут наблюдать живые поколения (помощник только читает
`/proc`, `systemctl show` и файлы состояния; в службы не вмешивается):

```bash
cd "$HOME/xgw-fp2" && date '+%F %T' | tee observe-time.txt && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; sudo python3 -I fpm2check.py watch 480 | tee live.txt
```

Ожидается:
- «Наблюдение за бесплатным пулом включено: списки серверов собираются через подписку,
  серверы проверяются, а трафик идёт как прежде — через подписку. Демон применит режим на
  ближайшем шаге»;
- через 8 минут: «поколений увидено: N; поднялось: U», N — от 1 (обычно 3–5), U — любое;
- у каждого поколения:
  - «фазы guarded → connecting → …» (поднявшееся — «… → up»), «самопроверка пройдена» (у
    отказавшего до неё — «—»), «причина отказа: …» — записать;
  - «служба: CapabilityBoundingSet=cap_chown cap_kill cap_setgid cap_setuid cap_net_admin;
    KillMode=mixed; NoNewPrivileges=yes; PrivateNetwork=yes; PrivateTmp=yes;
    ProtectSystem=strict» (порядок слов в возможностях — любой);
  - «агент: пользователь root; возможности chown,kill,setgid,setuid,net_admin; NoNewPrivs 1;
    своё пространство имён: да»;
  - «интерфейсы внутри: fpi<номер>, fpt0, lo»;
  - «маршрут по умолчанию внутри: нет; маршрутов к одному адресу: 1» (снимок сделан до
    подъёма туннеля); у поднявшегося — ещё «после подъёма: маршрут по умолчанию внутри: fpt0;
    …»;
  - «работники: openvpn от xgw-ovpn, возможности нет, NoNewPrivs 1; xray от xgw-fps,
    возможности нет, NoNewPrivs 1» (у отказавшего до запуска работников — «нет»);
  - «xgw-ovpn: 750 root:xgw-ovpn; client.conf 640 root:xgw-ovpn; auth 640 root:xgw-ovpn»
    (`auth` — только у источника с учёткой); «xgw-socks: 750 root:xgw-fps; socks.json 640
    root:xgw-fps»;
  - «задание: 600 root:root; состояние: 600 root:root»; «секреты задания в state.json: нет»;
  - «veth на хосте: есть; элементов fp_peers: 1».

Записать всё как есть.

Если не так:
- «ошибка: …» в ответе команды — записать дословно, **стоп**, сообщить заказчику;
- «поколений увидено: 0» — продолжить: шаг 3.2 покажет, годится ли бэкенд (подключения могли
  начаться позже);
- у агента не root, другие возможности, NoNewPrivs не 1 или «своё пространство имён: НЕТ»; у
  службы нет `PrivateNetwork=yes` или `NoNewPrivileges=yes` — **дефект «изоляция поколения»**,
  **стоп**, сообщить заказчику;
- «маршрут по умолчанию внутри» не «нет» в снимке до подъёма или после подъёма не `fpt0` —
  **дефект «маршрут мимо туннеля»**, **стоп**;
- работник от root или с возможностями, или NoNewPrivs не 1 — **дефект «права работника»**,
  **стоп**;
- среди интерфейсов внутри есть что-то кроме `fpi…`, `fpt0`, `lo` — **дефект «лишний интерфейс
  в пространстве имён»**;
- права файлов шире (не 750/640/600) или владелец другой — **дефект «права файлов
  поколения»**; «секреты задания в state.json: ЕСТЬ» — **дефект «секрет в состоянии»**;
- «самопроверка НЕ пройдена» — **дефект «охрана пропускает»**, **стоп**;
- «агент: не найден» или строки «не прочитаны» — записать (поколение могло закончиться между
  опросами) и продолжить.

Шаг 3.2. Сразу после шага 3.1 — правила пула загружены, списки получены, бэкенд годится:

```bash
sleep 10; cd "$HOME/xgw-fp2" && for m in pool backend digest units files; do sudo python3 -I fpm2check.py $m; done | tee pool-1.txt; sudo xgw status 2>&1 | grep -E '^Состояние|^Бесплатный пул' | tee -a pool-1.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул' | tee -a pool-1.txt; sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm2check.py log | tee log-1.txt
```

Ожидается:
- «status.json: N с назад» (N меньше 120);
- «free_pool в состоянии: режим observe, регион EU; найдено …»;
- **«OpenVPN туннелем: годится; …»**;
- строки источников: `vpngate: SUCCESS; …; вариантов` 30 или больше; `vpnbook: SUCCESS` (или
  `PARTIAL`); `вариантов` 10 или больше; строки `vpnjantit` нет;
- **«набор fp_peers: есть; элементов 0»** (или 1 — идёт подключение); **«бэкенд OpenVPN:
  годится»**;
- «отпечаток таблиц: совпадает; … True»;
- «panel.json: поле ссылок пула: нет; режим пула: observe» (ссылки VPNJantit прошлой версии
  отброшены при записи режима);
- `Состояние: HEALTHY …`; строка `Бесплатный пул (наблюдение, регион EU): найдено …`;
- `OK    Бесплатный пул: режим observe; бэкенд OpenVPN готов (…)`, строки `FAIL` у «Бесплатный
  пул» нет;
- в журнале: «VPN Gate: список получен: 1» (или больше), «VPNBook: …: 1»; «список получен через
  подписку: 2» (или больше); «список получен напрямую: 0»; **«правила загружены заново: 1»**
  (включение пула); «шаг пула не выполнен: 0»; «Traceback: 0».

Записать всё как есть.

Если не так:
- «free_pool в состоянии: нет» — подождать 2 минуты и повторить шаг; снова нет — **дефект
  «наблюдение не включилось»**;
- «набор fp_peers: нет» или «бэкенд OpenVPN: в правилах XGW нет набора fp_peers …» — подождать
  2 минуты и повторить; снова так — **дефект «правила пула не загрузились»** (продолжить: OpenVPN
  тогда проверяется только по адресу);
- «бэкенд OpenVPN: …» с другой причиной — записать дословно, **дефект «бэкенд не годится»**;
- «panel.json: поле ссылок пула: ЕСТЬ» — **дефект «ссылки VPNJantit остались в panel.json»**;
- «правила загружены заново» больше 2 — **дефект «правила загружаются по кругу»**;
- источник `UNAVAILABLE` или `RATE_LIMITED` — записать, продолжить; оба `UNAVAILABLE` —
  записать `sudo python3 -I fpm2check.py subs | tee subs-1.txt` и продолжить;
- источник `SCHEMA_CHANGED` — **дефект «формат страницы источника изменился»**, продолжить;
- «список получен напрямую» больше 0 при `HEALTHY` — **дефект «списки не через подписку»**;
- «шаг пула не выполнен» или «Traceback» больше 0 — записать
  `sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -20 | tee traceback-1.txt`
  (только строки с файлами и ошибкой) — **дефект «шаг пула падает»**.

Шаг 3.3 (при согласии на пункт 3). **Попроси заказчика** (дословно):

«Откройте панель XGW, найдите карточку «Бесплатные серверы». Прочитайте мне первую фразу под
заголовком до слов «Трафик проверок» и метки у VPN Gate и VPNBook (например «ок»). Есть ли в
карточке что-нибудь про VPNJantit или «Выданные ссылки»?»

Ожидается: фраза «Наблюдение (регион EU): найдено N: ключей Outline — …, OpenVPN — …,
туннелем поднялось …, подключений за час …. Проверено …»; N — как «найдено» в `pool-1.txt`
(может отличаться на несколько); метки — как статусы в `pool-1.txt` («ок» — SUCCESS,
«частично» — PARTIAL, «недоступен» — UNAVAILABLE); про VPNJantit и «Выданные ссылки» — нет.
Записать ответ.

Если не так: во фразе «туннелем не проверить: …» — записать причину (сравнить с шагом 3.2);
есть VPNJantit или «Выданные ссылки» — **дефект «VPNJantit остался в панели»** (возможно,
страница из кэша: попросить обновить страницу и прочитать снова).

## 4. Подключения OpenVPN

Шаг 4.1. Не раньше чем через 35 минут после шага 3.1:

```bash
cd "$HOME/xgw-fp2" && for m in checks pool units backend fwd files config; do sudo python3 -I fpm2check.py $m; done | tee tunnels-1.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm2check.py agentlog | tee agent-1.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee -a tunnels-1.txt
```

Ожидается:
- «проверок всего: C …», C — 10 или больше; строки итогов вида `openvpn OK: …`,
  `openvpn TLS_HANDSHAKE_FAILED: …`, `openvpn REACHABLE: …`, `xray OK: …` — записать все;
- **«OpenVPN туннелем: попыток A, поднялось U»**, A — от 2 до 4 (не больше 2 на источник в
  час); строки по источникам, «итоги через поднятый туннель», «отказы без туннеля», «причины
  «не проверено» у OpenVPN» — **записать все как есть** (это и есть результат вехи: сколько
  серверов OpenVPN подключается из дома). U может быть и 0;
- «подключений за час: H (…)», H не больше 4, у каждого источника не больше 2;
- «трафик одной проверки туннелем, наибольший: X МБ», X не больше 20;
- «OpenVPN туннелем: годится; поднялось …» в сводке — U как выше (может отличаться на 1);
  «пригодно R (…)» — в скобках только `EU …` или «—» (регион строгий);
- «поколений xgw-fp@ сейчас: 0» или 1 (идёт подключение); «процессов openvpn XGW: 0» или 1;
  «других openvpn» — как до установки;
- «набор fp_peers: есть; элементов 0» (или 1); «veth fpv сейчас: 0» (или 1); «каталогов
  поколений: 0» (или 1);
- «из fpv* к серверам пула: пакетов P» (P больше 0, если A больше 0); **«из fpv* — сброс:
  пакетов 0»**; «в fpv* — сброс: пакетов …» — записать;
- права: каталог freepool 700, secrets и candidates 600; «профилей VPNBook: …; каталог
  profiles: 700; права профилей: 600 …» (0 профилей — если VPNBook ещё не проверялся туннелем);
  «временных Xray сейчас: 0» (или 1);
- **«из них серверов бесплатного пула: 0; выходов к работникам пула: 0»** — трафик через пул
  не идёт;
- журнал поколений: «самопроверок охраны: S; итоги: …» — в итогах только `ENETUNREACH` и
  `… (охрана)`; «туннель поднят: …» (как U или больше); «отказы поколений: …» — записать;
  строки «OpenVPN: …» — **записать все** (адреса в них уже заменены); «строк с внешним адресом:
  0»; «Traceback: 0»;
- `HEALTHY`, перехват включён.

Если не так:
- A равно 0 — подождать 10 минут и повторить; снова 0 — **дефект «подключения OpenVPN не
  идут»**, записать `sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm2check.py log | tee log-tunnels.txt`;
- H больше 4 или у источника больше 2 — **дефект «пределы подключений не соблюдены»**;
- в отказах (в сводке или в журнале поколений) есть `GUARD_FAILED` или в итогах самопроверки
  есть что-то кроме `ENETUNREACH` и `(охрана)` — **дефект «охрана пропускает»**, **стоп**,
  сообщить заказчику;
- «из fpv* — сброс» больше 0 — **дефект «из пространства имён уходит мимо сервера»**, записать
  и продолжить;
- в отказах есть `BACKEND_START`, `NO_VETH`, `NO_USER`, `BAD_MANIFEST`, `AGENT_ERROR`,
  `AGENT_EXITED`, `NO_MANAGEMENT`, `CONFIG_REJECTED`, `TUN_FAILED`, `NETWORK_UNREACHABLE`,
  `NO_TUNNEL_ADDRESS` или `SOCKS_FAILED` — **дефект «бэкенд OpenVPN: <код>»** (строки «OpenVPN:
  …» помощника — в отчёт), продолжить; `TLS_HANDSHAKE_FAILED`, `CONNECT_TIMEOUT`,
  `CONNECT_REFUSED`, `TRANSPORT_RESET`, `TIMEOUT`, `AUTH_FAILED`, `CERT_VERIFY_FAILED`,
  `UNSUPPORTED_CRYPTO`, `UNKNOWN` — это сервер или сеть (ТСПУ), не дефект: записать;
- поколений, veth или каталогов 2 и больше — повторить через 2 минуты; снова так — **дефект
  «поколения не убираются»**;
- X больше 20 — **дефект «проверка туннелем тратит много трафика»**;
- в скобках у «пригодно» есть не `EU` — **дефект «регион не строгий»**;
- «из них серверов бесплатного пула» или «выходов к работникам пула» больше 0 — **дефект
  «пул попал в рабочий конфиг»**, **стоп**, сообщить заказчику;
- «строк с внешним адресом» больше 0 — **наблюдение** (адрес в журнале службы); строки не
  переписывать;
- права другие — **дефект «права файлов пула»**.

Шаг 4.2. Не раньше чем через 65 минут после шага 3.1 — второй час подключений:

```bash
cd "$HOME/xgw-fp2" && for m in checks pool units backend fwd; do sudo python3 -I fpm2check.py $m; done | tee tunnels-2.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm2check.py agentlog | tee agent-2.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee -a tunnels-2.txt
```

Ожидается: «OpenVPN туннелем: попыток A2, поднялось U2», A2 больше A (обычно до 8);
«подключений за час: …» не больше 4, у источника не больше 2; «за сутки» — как A2 (± 1);
остальное — как в шаге 4.1. Записать всё.

Если не так: как в шаге 4.1. A2 равно A — **дефект «подключения остановились»**.

## 5. Сводка в команде

Шаг 5.1 (при согласии на пункт 3). Сводка команды и панели — одна:

```bash
cd "$HOME/xgw-fp2" && sudo xgw pool 2>&1 | head -5 | tee cli.txt; sudo xgw pool status --json | python3 -c "import json,sys;d=json.load(sys.stdin);print('json:', d['mode'], d['found'], d['checked'], d['ready'], d['tunnels_up'], d['handshakes_hour'])" | tee -a cli.txt
```

Затем **попроси заказчика** (дословно): «Прочитайте ещё раз из карточки «Бесплатные серверы»
числа после слов «найдено», «туннелем поднялось» и «Проверено».»

Ожидается: строки «Бесплатный пул: наблюдение (трафик через подписку); регион EU (строго)»,
«Найдено N: Outline …, OpenVPN …», «OpenVPN туннелем: поднялось U…; подключений за час …, за
сутки …», «Проверено C, …», «Трафик проверок за сутки: …»; «json: observe N C R U H»; числа
заказчика — как N, U и C (могут отличаться на несколько: проверки идут). Записать.

Если не так: команда отвечает ошибкой — **дефект «xgw pool»**; числа заказчика отличаются
больше чем на 10 (U — больше чем на 1) — **дефект «сводка панели и команды расходится»**.

## 6. Секреты

Шаг 6.1.

```bash
cd "$HOME/xgw-fp2" && sudo python3 -I fpm2check.py files | tee secrets.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm2check.py leak | sed 's/^/xgw: /' | tee -a secrets.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm2check.py leak | sed 's/^/xgw-fp@: /' | tee -a secrets.txt; stat -c 'status.json: %a' /run/xgw/status.json | tee -a secrets.txt
```

Ожидается: права 700/600/600, профили 600; у обеих строк «паролей источников известно: 1»
(общая учётка VPNBook; 0 — если VPNBook не ответил); «строк с паролем: 0; строк со ссылкой
сервера: 0; строк OpenVPN с настройками: 0»; «status.json: 644». Записать.

Если не так: строк с паролем, ссылкой или настройками OpenVPN больше 0 — **дефект «секрет в
журнале»**.

## 7. Выключение

Шаг 7.1 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В карточке «Бесплатные серверы» нажмите «Выключить». Что ответила панель и что теперь
написано на кнопке?»

Сразу после ответа:

```bash
cd "$HOME/xgw-fp2" && sleep 60; date '+%F %T' | tee off-time.txt; sleep 120; for m in pool units backend; do sudo python3 -I fpm2check.py $m; done | tee off.txt; sudo xgw pool 2>&1 | head -1 | tee -a off.txt; sudo xgw status 2>&1 | grep -c '^Бесплатный пул' | sed 's/^/строк «Бесплатный пул» в xgw status: /' | tee -a off.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул' | tee -a off.txt
```

Ожидается: ответ панели — «Бесплатный пул выключен», на кнопке — «Включить наблюдение»;
«free_pool в состоянии: нет»; «поколений xgw-fp@ сейчас: 0; процессов openvpn XGW: 0»;
«набор fp_peers: нет»; «veth fpv сейчас: 0; каталогов поколений: 0»; «Бесплатный пул:
выключен; …»; «строк «Бесплатный пул» в xgw status: 0»; `OK    Бесплатный пул: выключен —
режим подписок`. Записать.

Если не так: «free_pool в состоянии: режим …» — подождать 2 минуты и повторить; снова так —
**дефект «наблюдение не выключается»**. Поколения, veth, каталоги или процессы openvpn XGW
больше 0 — повторить через 2 минуты; снова так — **дефект «поколения остались после
выключения»**. «набор fp_peers: есть» — **дефект «правила пула остались»**.

## 8. Итог

Шаг 8.1. Через 3 минуты после шага 7.1:

```bash
sleep 180; cd "$HOME/xgw-fp2" && sudo journalctl -u xgw --since "$(cat off-time.txt)" --no-pager | sudo python3 -I fpm2check.py log | tee log-off.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm2check.py log | tee final.txt; for m in checks digest subs config units; do sudo python3 -I fpm2check.py $m; done | tee -a final.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm2check.py agentlog | tee agent-final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee -a final.txt
```

Ожидается:
- в `log-off.txt` (с минуты после нажатия «Выключить»): «VPN Gate: список получен: 0»,
  «VPNBook: …: 0», «проверок серверов пула: 0»;
- в `final.txt`: **«Traceback: 0»**, «шаг пула не выполнен: 0», **«следы поколения не убраны:
  0»**, «правила загружены заново: 2» (включение и выключение пула; 3 — если ещё одну дала
  установка), «откат на last-good: 0», «Read-only file system» и «Permission denied» — не
  больше, чем в `log-before.txt`;
- итог проверок (`checks`) — записать целиком: это итог вехи;
- «отпечаток таблиц: совпадает; … True»; «подписок с ошибкой» — не больше, чем до установки;
  «серверов в списке» — как до установки (±2); «из них серверов бесплатного пула: 0; выходов к
  работникам пула: 0»; «поколений xgw-fp@ сейчас: 0»;
- `agent-final.txt`: «отказы поколений» без `GUARD_FAILED`; «Traceback: 0»;
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки.

Если не так: опросы или проверки после выключения больше 0 — **дефект «пул работает
выключенным»**; Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -30 | tee traceback.txt`
(только строки с файлами и ошибкой, адреса — убрать); «следы поколения не убраны» больше 0 —
**дефект «поколение убрано не до конца»**; «правила загружены заново» больше 3 — **дефект
«правила загружаются по кругу»**. Сообщить заказчику.

Шаг 8.2 (при согласии на пункт 5). Повторная установка тем же кодом. **Скажи заказчику**
(дословно): «Запускаю повторную установку тем же кодом — интернет дома пропадёт на несколько
секунд. WAN она не трогает.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fp2/reinstall-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fp2/reinstall.txt" | tail -4; echo "код ${PIPESTATUS[0]}"; grep -cE 'пакеты: .*openvpn|пользователь xgw-' "$HOME/xgw-fp2/reinstall.txt" | sed 's/^/строк «пакеты openvpn» и «пользователь xgw-…»: /'; cd "$HOME/xgw-fp2"; sleep 120; for m in units backend digest; do sudo python3 -I fpm2check.py $m; done | tee reinstall-after.txt; sudo journalctl -u xgw --since "$(cat reinstall-time.txt)" --no-pager | sudo python3 -I fpm2check.py log | tee -a reinstall-after.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee -a reinstall-after.txt
```

Ожидается: «код 0»; «строк «пакеты openvpn» и «пользователь xgw-…»: 0» (пакет и пользователи
уже есть — заново не ставятся); пакет, пользователи, служба — как в шаге 2.3; «поколений xgw-fp@
сейчас: 0»; «набор fp_peers: нет»; «отпечаток таблиц: совпадает; … True»; в журнале «Traceback:
0», «снимки убранных источников удалены: 0»; `HEALTHY`, перехват включён. Записать.

Если не так: код не 0 — **стоп**, сообщить заказчику (сеть не откатывать); строк больше 0 —
**дефект «повторная установка создаёт заново»**; пользователей или службы нет — **дефект
«повторная установка убрала бэкенд»**.

Шаг 8.3 (при согласии на пункт 4). **Попроси заказчика** (дословно):

«Откройте любой сайт на этом компьютере и любой сайт на телефоне. Открываются?»

Ожидается: «да». Нет — записать ответ дословно и
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt`,
сообщить заказчику.

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.
- Заказчик просит остановить проверку — попросить его нажать «Выключить» в карточке
  «Бесплатные серверы» и выполнить шаг 7.1 и шаг 8.1; службы `xgw-fp@*` руками не трогать.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-m2a-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`freepool`), коммит «Отчёт: XGW 0.2.0, бесплатные серверы, веха М2а», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, бесплатные серверы, веха М2а (OpenVPN туннелем, наблюдение)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
fpm2check.py: <сумма, 16 знаков>. Пакет openvpn: <версия>.

## Итог вехи
| Источник | Попыток туннелем | Поднялось | Итоги через туннель | Отказы без туннеля |
|---|---|---|---|---|
| vpngate | … | … | … | … |
| vpnbook | … | … | … | … |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, службы, openvpn, снимки, отпечаток, подписки, журнал |
| 2.2 установка | … | код, пакеты, пользователи, ufw |
| 2.3 после установки | … | HEALTHY, бэкенд (пакет, пользователи, служба, пересылка, fp_peers, оценка systemd), снимки без VPNJantit, diag (пул, конфиг) |
| 3.1 включение и живые поколения | … | ответ команды; поколений/поднялось; служба, агент, интерфейсы, маршрут до и после подъёма, работники, права файлов, секреты |
| 3.2 правила и списки | … | fp_peers, бэкенд годится, panel.json, источники, загрузка правил, diag, Traceback |
| 3.3 карточка | … / не выполнялся | фраза, метки, нет VPNJantit |
| 4.1 подключения, 35 мин | … | попыток/поднялось, итоги, отказы, пределы, самопроверки, fwd-сброс, поколения, секреты конфига |
| 4.2 подключения, 65 мин | … | то же |
| 5.1 xgw pool | … / не выполнялся | строки, json, числа заказчика |
| 6.1 секреты | … | права, пароли, ссылки и настройки OpenVPN в журналах, status.json |
| 7.1 выключение | … / не выполнялся | ответ панели, кнопка, поколения, fp_peers, diag |
| 8.1 итог | … | после выключения, Traceback, следы поколений, правила, отпечаток, подписки, HEALTHY |
| 8.2 повторная установка | … / не выполнялся | код, строк пакета и пользователей, бэкенд, HEALTHY |
| 8.3 сайты | … / не выполнялся | ответ заказчика |

## Выводы шагов
<файлы $HOME/xgw-fp2/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
