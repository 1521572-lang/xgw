# Проверка XGW 0.2.0: бесплатные серверы, веха М2в.1 (SSTP вместо OpenVPN у VPN Gate)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-fpv1/…`). Файл помощника создавай только командой шага 1.2, выполненной в
терминале. Блок команды копируй целиком, ничего в нём не меняя.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. Телефон — S25 Ultra в домашней сети.
Команды — в терминале сеанса заказчика (`sudo` от его имени).

Что нового (ASSUMPTIONS п. 263) — решение заказчика: **OpenVPN убран из XGW** («неэффективен в
условиях ТСПУ»: в проверках М2а–М2а.4 из ~20 подключений к VPN Gate туннель поднялся один раз).
У серверов VPN Gate шлюз теперь подключается по **MS-SSTP** — PPP внутри обычного TLS по TCP,
для DPI это выглядит как HTTPS:
1. **Источник VPN Gate** — страница списка серверов вместо CSV с профилями OpenVPN: берутся
   серверы с SSTP (у VPN Gate их около 70 из 100; почти все — в Японии и Корее, в Евросоюзе —
   единицы).
2. **Клиент** — пакет Ubuntu `sstp-client` (`sstpc`, с ним `ppp`) в той же изолированной службе
   `xgw-fp@…`: свои пространство имён, охрана, самопроверка, проверка изнутри и SOCKS-посредник —
   как в М2а. `sstpc` подключается к адресу сервера **без имени в TLS (SNI)**, проверяет
   сертификат по системным и после подключения работает от нового пользователя **`xgw-vpn`**;
   `pppd` не видит `/etc/ppp` машины (у службы он пустой).
3. **Убрано**: профили OpenVPN, страница OpenVPN у VPNBook и её учётка (у VPNBook остались ключи
   Outline). Остатки прошлых вех на диске (учётка VPNBook, профили, итоги проверок OpenVPN)
   шлюз удаляет сам. Пакет openvpn и пользователь xgw-ovpn остаются — они не мешают.

Главные вопросы вехи — работает ли туннель SSTP в изолированной службе и сколько серверов VPN
Gate дают через него данные:
- поднимается ли туннель (**«туннель поднят»**, адрес на `fpt0`);
- принимает ли сервер подключение без SNI и проходит ли проверка сертификата (сколько отказов
  **`CERT_VERIFY_FAILED`**);
- сбрасывает ли `sstpc` права (**«sstpc от xgw-vpn, возможности нет»** после подъёма);
- что видно изнутри туннеля и прошла ли проба (OK/SLOW).

Здесь, у разработчика, — только юнит-тесты затронутых модулей и ruff; `sstpc` и `pppd` не
запускались. Всё остальное — на этой машине.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh`; ручные `nft` (кроме `nft list`), `ip` (кроме чтения помощником),
  `ip netns`, `nsenter`, `iptables`, `tc`, `sysctl -w`, `systemd-run`, `modprobe`, `apt` (пакеты
  ставит только установщик XGW); команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`, `pon`,
  `poff` и `openvpn`. `sudo xgw pool mode …` — только в шагах 1.3 (`off`), 3.1 (`observe`) и по
  правилу «Наблюдение не оставлять включённым» (`off`).
- Самому открывать сайты источников (vpngate, vpnbook), серверы `*.opengw.net` и файлы списков
  на GitHub — в браузере, `curl`, `wget` и как угодно ещё. Их открывает только сам шлюз.
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, `/etc/ppp`, код XGW. Печатать `config.toml`, `panel.json`, файлы в
  `/var/lib/xgw/freepool` и `/run/xgw/fp` (`cat`, `less`, `grep` по ним) — в них ключи подписок,
  пароли и ссылки серверов. Серверы, переключатели и кнопки в панели меняет и нажимает только
  заказчик. Коммитить что-либо, кроме отчёта (§9).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP, домены и ссылки
  серверов VPN (и бесплатных тоже, в том числе имена `*.opengw.net`), логины и пароли, строки
  журнала. Можно: адреса устройств в домашней сети (`192.168.…`), коды стран, названия
  источников, счётчики, статусы, коды причин, размеры, права файлов, времена, версии пакетов и
  строки помощника «SSTP: …», «изнутри: …», «итог туннеля: …», «канал к серверу …» и
  «предупреждение клиента: …» (адреса и имена в них уже заменены).

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю туннели SSTP к бесплатным серверам VPN Gate вместо OpenVPN (веха М2в.1). По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд. Установка поставит из архива Ubuntu пакет
sstp-client (клиент SSTP; с ним — пакет ppp) и системного пользователя xgw-vpn без входа.
Внешний интерфейс (WAN), его соединение и DHCP установка не трогает: меняются только профиль
LAN, свои таблицы nftables и свои службы. Пакет openvpn и пользователь xgw-ovpn остаются (их
можно убрать позже).
(2) Я включу наблюдение командой `sudo xgw pool mode observe`. Трафик устройств идёт через
подписку, как сейчас. Шлюз будет: подключаться к бесплатным серверам VPN Gate по SSTP в
изолированной службе (не больше 2 раз в час); скачивать через подписку списки серверов с
GitHub и проверять их серверы напрямую — до 4 серверов в минуту, без предела трафика (около
15–20 МБ в час). Владельцы этих серверов неизвестны и видят только проверочный запрос шлюза.
Проверка займёт около трёх часов (подключений SSTP всего 2 в час, а нужно их хотя бы шесть).
После установки, до включения наблюдения, я проверю, свободен ли суточный предел подключений;
если занят — скажу, с какого времени можно начать. В конце вы выключите наблюдение кнопкой
«Выключить» в карточке «Бесплатные серверы» панели XGW (не ответите за 30 минут — выключу
командой). Если наблюдение осталось включённым с прошлой проверки, в начале я попрошу вас
выключить его той же кнопкой (не ответите за 10 минут — выключу командой).
(3) В панели по моей просьбе прочитаете мне сводку из карточки «Бесплатные серверы».
(4) В конце откроете любой сайт на этом компьютере и на телефоне.
Можно согласиться не на все пункты.»

Против пункта 1 или 2 — **стоп**. Против 3 — шаги 3.3 и 5.1 пропустить; против 4 — шаг 8.2.
Если против 2 только выключение кнопкой — шаг 7.1 пропустить. В отчёте у пропущенного — «не
выполнялся». Если ответа на вопрос нет — не начинать, спросить ещё раз.

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-fpv1" && chmod 700 "$HOME/xgw-fpv1" && cd "$HOME/xgw-fpv1" && cat > fpv1check.py <<'EOF'
"""XGW 0.2.0, бесплатный пул (веха М2в.1: SSTP вместо OpenVPN): помощник проверки. Только
читает: состояние XGW (/run/xgw, /var/lib/xgw/freepool, рабочие конфиги Xray и sing-box),
бэкенд SSTP (пакеты, модуль pppd, /dev/ppp, пользователи, служба, пересылка IPv4, набор
fp_peers, ufw, veth) и журналы со стандартного ввода — счётчики, коды, права и да/нет, без
адресов, имён, ссылок и паролей. watch — живые поколения по /proc и systemctl show: в
пространство имён не входит и ничего не меняет. checks <секунды> — только записи проверок с
этого времени. quota — свободен ли суточный предел подключений (только время подключений).
Режимы: units, backend, pool, quota, checks, vpngate, lists, files, config, leak, digest, subs,
fwd, log, agentlog, watch."""
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("FPV1_LIB", "/opt/xgw/lib")
DAY = 86400.0
HOUR = 3600.0
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
HOST = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")
NOT_TUNNEL = ("REACHABLE", "CLOSED", "UNTESTED")
LISTS = ("igareck", "mahdibland")
CAPS = {0: "chown", 1: "dac_override", 2: "dac_read_search", 3: "fowner", 4: "fsetid",
        5: "kill", 6: "setgid", 7: "setuid", 8: "setpcap", 10: "net_bind_service",
        12: "net_admin", 13: "net_raw", 16: "sys_module", 18: "sys_chroot", 19: "sys_ptrace",
        21: "sys_admin"}
RANK = {"guarded": 1, "connecting": 2, "up": 3}
LINKS = ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://", "tuic://")
OPTIONS = b"/tmp/xgw-vpn/ppp.options"
FOUR = r"клиент VPN (\d+), работник (\d+), ответы ядра (\d+), служебный IPv6 (\d+)"


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


def is_global(text):
    try:
        return ipaddress.ip_address(text).is_global
    except ValueError:
        return False


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
    for name, files in (("xgw-vpn", ("ppp.options",)), ("xgw-socks", ("socks.json",))):
        items = [describe(tmp / name)] + [f"{item} {describe(tmp / name / item)}"
                                          for item in files if (tmp / name / item).exists()]
        lines.append(f"{name}: " + "; ".join(items))
    return lines


def ppp_view(pid):
    """/etc/ppp и /run/sstpc глазами службы (её пространство имён монтирования)."""
    root = Path(f"/proc/{pid}/root")
    parts = []
    for name in ("etc/ppp", "run/sstpc"):
        try:
            items = sorted(entry.name for entry in (root / name).iterdir())
        except OSError as exc:
            parts.append(f"/{name} службы: не прочитан ({type(exc).__name__})")
            continue
        sockets = sum(1 for item in items if item.startswith("sstpc-"))
        parts.append(f"/{name} службы: " + ("пусто" if not items else
                                             f"{len(items)} (сокетов sstpc {sockets})"))
    return "; ".join(parts)


def snapshot(paths, gen, host_ns):
    unit = f"xgw-fp@{gen}.service"
    _code, props = run(["systemctl", "show", unit, "-p", "PrivateNetwork", "-p", "PrivateTmp",
                        "-p", "NoNewPrivileges", "-p", "ProtectSystem", "-p", "KillMode",
                        "-p", "CapabilityBoundingSet", "-p", "DevicePolicy",
                        "-p", "TemporaryFileSystem"])
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
    lines.append(ppp_view(pid))
    lines.append(f"задание: {describe(directory / 'manifest.json')}; состояние: "
                 f"{describe(directory / 'state.json')}")
    try:
        state_text = (directory / "state.json").read_text(encoding="utf-8")
    except OSError:
        state_text = ""
    words = [word for word in [str(manifest.get("socks_pass") or "")] if len(word) >= 6]
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
    return [routes(pid), workers(pid, ns), *worker_files(pid)[1:], ppp_view(pid)]


def tunnel_line(stats):
    try:
        return (f"в туннель {int(stats['tx_packets'])} пакетов, из туннеля "
                f"{int(stats['rx_packets'])} пакетов")
    except (KeyError, TypeError, ValueError):
        return "—"


def client_processes():
    mine = other = legacy = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        name = command[0].rsplit(b"/", 1)[-1] if command else b""
        if name in (b"sstpc", b"pppd"):
            if OPTIONS in command:
                mine += 1
            else:
                other += 1
        elif name == b"openvpn":
            legacy += 1
    return mine, other, legacy


def diagnosis(record):
    text = str(record.get("diagnosis") or "")
    tcp = re.search(r"TCP Cloudflare:443 — ([A-Z_]+|—)", text)
    back = re.search(r"из туннеля (\d+) пакетов", text)
    guard = re.search(r"охрана после подъёма: клиент VPN (\d+), работник (\d+)", text)
    link = re.search(r"канал к серверу: от сервера \d+ пакетов \((\d+) КБ\)", text)
    return (tcp.group(1) if tcp else "—", re.findall(r"DNS (.+?) — ([A-Z_]+|—)", text),
            int(back.group(1)) if back else None,
            bool(guard and (int(guard.group(1)) or int(guard.group(2)))),
            int(link.group(1)) if link else None)


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
    _code, text = run(["systemctl", "list-units", "--all", "--plain", "--no-legend",
                       "xgw-fp@*.service"])
    states = [line.split()[2] for line in text.splitlines() if len(line.split()) > 2]
    mine, other, legacy = client_processes()
    print(f"поколений xgw-fp@ сейчас: {len(states)} ({counted(states)}); процессов sstpc и pppd "
          f"XGW: {mine}; других sstpc и pppd: {other}; процессов openvpn: {legacy}")
elif mode == "backend":
    cfg, paths = xgw()

    def version(package):
        code, text = run(["dpkg-query", "-W", "-f", "${Status} ${Version}", package])
        return text.split()[-1] if code == 0 and "install ok installed" in text else "нет"

    plugins = sorted(path.parent.name for path in Path("/usr/lib/pppd").glob(
        "*/sstp-pppd-plugin.so")) if Path("/usr/lib/pppd").exists() else []
    print(f"пакет sstp-client: {version('sstp-client')}; ppp: {version('ppp')}; "
          f"/usr/sbin/sstpc: {'есть' if Path('/usr/sbin/sstpc').exists() else 'нет'}; "
          f"/usr/sbin/pppd: {'есть' if Path('/usr/sbin/pppd').exists() else 'нет'}; модуль "
          f"sstp-pppd-plugin.so: {', '.join(plugins) or 'нет'}; /dev/ppp: "
          f"{'есть' if Path('/dev/ppp').exists() else 'нет'}; sing-box для проверок: "
          f"{'есть' if paths.singbox_bin.exists() else 'нет'}")
    for name in ("xgw-vpn", "xgw-fps"):
        code, line = run(["getent", "passwd", name])
        fields = line.strip().split(":")
        if code != 0 or len(fields) < 7:
            print(f"пользователь {name}: нет")
            continue
        system = fields[2].isdigit() and int(fields[2]) < 1000
        print(f"пользователь {name}: есть, {'системный' if system else 'НЕ системный'}, "
              f"оболочка {fields[6]}")
    old_user = run(["getent", "passwd", "xgw-ovpn"])[0] == 0
    print(f"прежнее (OpenVPN): пакет openvpn {version('openvpn')}; пользователь xgw-ovpn: "
          f"{'есть' if old_user else 'нет'}")
    unit = paths.systemd_dir / "xgw-fp@.service"
    try:
        text = unit.read_text(encoding="utf-8")
    except OSError:
        text = ""
    print(f"служба xgw-fp@.service: {'есть' if text else 'нет'}; в ней пустой /etc/ppp: "
          f"{'да' if 'TemporaryFileSystem=/etc/ppp:ro' in text else 'НЕТ'}; /dev/ppp: "
          f"{'да' if 'DeviceAllow=/dev/ppp' in text else 'НЕТ'}; OpenVPN в описании: "
          f"{'ЕСТЬ' if 'OpenVPN' in text else 'нет'}")
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
    print("бэкенд SSTP: " + ("годится" if not problem else problem))
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
          f"sing-box {pool.get('lists_singbox')}; Outline {pool.get('outline')}; SSTP "
          f"{pool.get('sstp')}); проверено {pool.get('checked')}, пригодно {pool.get('ready')} "
          f"({regions}); пригодные по источникам: {sources}; ключи OpenVPN в сводке: "
          f"{'ЕСТЬ' if any(key.startswith('openvpn') for key in pool) else 'нет'}")
    print(f"трафик проверок за сутки: каталоги {pool.get('spent_mb')} из {pool.get('budget_mb')}"
          f" МБ; серверы списков {pool.get('lists_spent_mb')} МБ")
    problem = pool.get("tunnel_backend") or ""
    failures = ", ".join(f"{code} {count}" for code, count in
                         sorted((pool.get("tunnel_failures") or {}).items())) or "—"
    print(f"SSTP туннелем: {'годится' if not problem else 'недоступно — ' + problem}; "
          f"поднялось {pool.get('tunnels_up')}; отказы: {failures}; подключений за час "
          f"{pool.get('handshakes_hour')}, за сутки {pool.get('handshakes_day')} из "
          f"{pool.get('handshakes_day_limit', '?')}")
    free_at = float(pool.get("handshakes_free_at") or 0)
    print("суточный предел подключений: " + (
        "занят, освободится " + time.strftime("%d.%m %H:%M", time.localtime(free_at))
        if free_at else "не занят"))
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
    print(f"подключений туннелей за сутки: {len(stamps)} из {limit}; за час: "
          f"{sum(1 for stamp in stamps if now - stamp < HOUR)}; свободно сейчас: {free}; "
          f"шесть свободны: {when}")
elif mode == "checks":
    _cfg, paths = xgw()
    since = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    found, data = records(paths, since)
    every = records(paths)[0]
    now = time.time()
    lists = [record for record in found.values() if record.get("provider") in LISTS]
    catalogs = [record for record in found.values() if record.get("provider") not in LISTS]
    recent = [record for record in found.values()
              if now - float(record.get("checked_at") or 0) < 1800]
    print(f"проверок с начала прогона: {len(found)} (каталоги {len(catalogs)}, списки GitHub "
          f"{len(lists)}; всего записей {len(every)}; записей OpenVPN: "
          f"{sum(1 for record in every.values() if record.get('backend') == 'openvpn')}); за "
          f"последние 30 минут: каталоги "
          f"{sum(1 for record in recent if record.get('provider') not in LISTS)}, списки "
          f"{sum(1 for record in recent if record.get('provider') in LISTS)}")
    print("каталоги: " + counted(f"{record.get('backend')} {record.get('verdict')}"
                                 for record in catalogs))
    attempts = [record for record in catalogs if record.get("backend") == "sstp"
                and record.get("verdict") not in NOT_TUNNEL]
    up = [record for record in attempts if record.get("tunnel_up")]
    seconds = sorted(float(record.get("connect_seconds") or 0) for record in up
                     if float(record.get("connect_seconds") or 0) > 0)
    print(f"SSTP туннелем: попыток {len(attempts)}, поднялось {len(up)}"
          + (f"; подключение — от {seconds[0]:.1f} до {seconds[-1]:.1f} с" if seconds else ""))
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
    print("охрана после подъёма отбила у клиента или работника: "
          f"{sum(1 for item in seen if item[3])} из {len(seen)}")
    print("канал к серверу после подъёма, от сервера: " + counted(
        "нет записи" if item[4] is None else "до 8 КБ" if item[4] < 8 else "8 КБ и больше"
        for item in seen))
    broken = sum(1 for record, item in zip(up, seen, strict=True)
                 if item[0] == "OPEN" and record.get("verdict") not in ("OK", "SLOW"))
    print(f"туннель пропускает TCP, а проба через посредника — нет: {broken}")
    print("страны выхода через туннель SSTP: " + counted(
        str(record.get("egress_country") or "?") for record in up
        if record.get("verdict") in ("OK", "SLOW")))
    print("причины «не проверено» у SSTP: " + counted(
        clean(record.get("error") or "—").split(":")[0][:50] for record in catalogs
        if record.get("backend") == "sstp" and record.get("verdict") == "UNTESTED"))
    print("SSTP только адресом (без бэкенда): " + counted(
        str(record.get("verdict")) for record in catalogs
        if record.get("backend") == "sstp" and record.get("verdict") in ("REACHABLE", "CLOSED")))
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
elif mode == "vpngate":
    cfg, paths = xgw()
    from xgw.freepool import probe
    from xgw.freepool.store import PoolStore

    store = PoolStore(paths)
    for provider in ("vpngate", "vpnbook"):
        snap = store.snapshot(provider)
        attempt = snap.get("last_attempt") or {}
        raw = [item for item in snap.get("variants") or [] if isinstance(item, dict)]
        variants = store.variants(provider)
        print(f"{provider}: {attempt.get('status') or 'нет'}; вариантов {len(variants)} "
              f"({counted(f'{v.backend} {v.protocol}' for v in variants)}); OpenVPN в снимке: "
              f"{sum(1 for item in raw if item.get('backend') == 'openvpn')}; отклонено "
              f"{attempt.get('rejected', 0)}")
        reasons = attempt.get("rejections") or {}
        print("  причины отказа: " + (", ".join(f"{clean(reason)} {count}" for reason, count in
                                                reasons.items()) or "—"))
        if provider == "vpngate":
            print("  страны по флагу: " + counted(v.country_hint or "?" for v in variants))
            print("  порт SSTP: " + counted("443" if v.port == 443 else "другой"
                                            for v in variants))
            print(f"  с публичным IPv4: {sum(1 for v in variants if probe.tunnel_peer(v))}; "
                  f"имя *.opengw.net: {sum(1 for v in variants if v.host.endswith('.opengw.net'))}")
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
    profiles = sorted((base / "profiles").glob("*")) if (base / "profiles").exists() else []
    print(f"каталог profiles: {perm(base / 'profiles')}; файлов в нём: {len(profiles)}")
    from xgw.freepool.store import PoolStore

    store = PoolStore(paths)
    current = {variant.variant_id for provider in cfg.free_pool.providers
               for variant in store.variants(provider)}
    found, _data = records(paths)
    file = base / "candidates.json"
    size = file.stat().st_size // 1024 if file.exists() else 0
    print(f"записей проверок: {len(found)}; из них OpenVPN: "
          f"{sum(1 for record in found.values() if record.get('backend') == 'openvpn')}; без "
          f"варианта в снимках: {sum(1 for key in found if key not in current)}; размер "
          f"candidates.json: {size} КБ")
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
    whole = {ident for variant in variants
             for ident in [*xray_ids(variant.outbound or {}),
                           *box_ids([(variant.singbox or {}).get("main") or {}])]}
    work = read_json(paths.xray_config_file) or {}
    found = [ident for outbound in work.get("outbounds") or [] for ident in xray_ids(outbound)]
    box = read_json(paths.singbox_config_file) or {}
    servers = box_ids(item for key in ("outbounds", "endpoints") for item in box.get(key) or [])
    print(f"адресов серверов в рабочем конфиге Xray: {len(found)}; из них вариантов бесплатного "
          f"пула целиком (адрес, порт, ключ): {sum(1 for item in found if item in whole)}; "
          "совпал только адрес: "
          f"{sum(1 for item in found if item not in whole and item[0] in hosts)}; выходов к "
          f"работникам пула: {sum(1 for item in found if item[0].startswith('10.250.'))}; "
          f"серверов в конфиге sing-box: {len(servers)}, из них вариантов пула целиком: "
          f"{sum(1 for item in servers if item in whole)}, совпал только адрес: "
          f"{sum(1 for item in servers if item not in whole and item[0] in hosts)}; вариантов в "
          f"пуле: {len(variants)}")
elif mode == "leak":
    lines = sys.stdin.read().splitlines()
    raw = sum(1 for line in lines if any(link in line for link in LINKS))
    names = sum(1 for line in lines if ".opengw.net" in line)
    password = sum(1 for line in lines if "--password" in line or 'password "' in line)
    outer = sum(1 for line in lines if any(is_global(item) for item in IPV4.findall(line)))
    print(f"строк журнала: {len(lines)}; строк со ссылкой сервера: {raw}; строк с именем "
          f"*.opengw.net: {names}; строк с паролем клиента: {password}; строк с внешним адресом: "
          f"{outer}")
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
        ("VPN Gate: список получен", ("бесплатный пул: vpngate — SUCCESS",
                                      "бесплатный пул: vpngate — PARTIAL")),
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
        ("из них SSTP", ("(sstp, ",)),
        ("из них OpenVPN", ("(openvpn, ",)),
        ("из них серверов списков", ("бесплатный пул: проверка igareck ",
                                     "бесплатный пул: проверка mahdibland ")),
        ("из них sing-box", ("(sing-box, ",)),
        ("с итогом изнутри туннеля", ("; изнутри: ",)),
        ("остатки OpenVPN удалены", ("OpenVPN убран (веха М2в)",)),
        ("остатки OpenVPN не удалены", ("остатки OpenVPN не удалены",)),
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
    print(f"туннель поднят: {sum(1 for line in lines if 'туннель поднят, MTU' in line)}; "
          f"SOCKS-работник готов: {sum(1 for line in lines if 'SOCKS-работник готов' in line)}")
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
    after = [tuple(int(value) for value in match.groups()) for text in totals
             for match in [re.search("охрана после подъёма: " + FOUR, text)] if match]
    print(f"в туннель ушло 0 пакетов: {sum(1 for value in sent if value == 0)}; из туннеля "
          f"вернулось 0: {sum(1 for value in back if value == 0)}, больше 0: "
          f"{sum(1 for value in back if value > 0)}")
    print(f"после подъёма отбито у клиента или работника больше 0: "
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
    notices = [text.split("предупреждения клиента: ", 1)[1] for text in totals
               if "предупреждения клиента: " in text]
    print(f"итогов с предупреждениями клиента: {len(notices)}")
    for text in list(dict.fromkeys(clean(item, 160) for text in notices
                                   for item in text.split(" | ")))[:6]:
        print(f"  предупреждение клиента: {text}")
    failures = [match.groups() for line in lines for match in [re.search(
        r"поколение [0-9a-f]{10}: ([A-Z_]+)(?: \(по выводу клиента: ([A-Z_]+)\))? — (.*)",
        line)] if match]
    print(f"отказы поколений: {counted(code for code, _orig, _text in failures)}")
    print("у GUARD_BLOCKED по выводу клиента: " + counted(
        orig or "—" for code, orig, _text in failures if code == "GUARD_BLOCKED"))
    for text in list(dict.fromkeys(clean(text, 140) for code, _orig, text in failures
                                   if code == "SOCKS_FAILED"))[:5]:
        print(f"  SOCKS_FAILED: {text}")
    before = [tuple(int(value) for value in match.groups()) for line in lines
              for match in [re.search("охрана за подключение: " + FOUR, line)] if match]
    print(f"охрана за подключение: строк {len(before)}; клиент VPN "
          f"{sum(item[0] for item in before)}, работник {sum(item[1] for item in before)}, "
          f"ответы ядра {sum(item[2] for item in before)}, служебный IPv6 "
          f"{sum(item[3] for item in before)}")
    own = [line for line in lines if "SSTP: " in line and "поколение " not in line
           and "итог туннеля: " not in line]
    evidence = [clean(line.split("SSTP: ", 1)[1], 160) for line in own]
    for text in list(dict.fromkeys(evidence))[:10]:
        print(f"  SSTP: {text}")
    outer = sum(1 for line in lines if line not in own and any(
        is_global(address) for address in IPV4.findall(line)))
    print(f"строк с внешним адресом: {outer}; строк pppd: "
          f"{sum(1 for line in lines if ' pppd[' in line)}; Traceback: "
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
                                                    "link": "", "notices": [], "mtu": ""})
            phase = str(state.get("phase") or "")
            if phase and (not info["phases"] or info["phases"][-1] != phase):
                info["phases"].append(phase)
            if state.get("reason"):
                info["reason"] = str(state["reason"])
                if state.get("client_code") and state["client_code"] != state["reason"]:
                    info["reason"] += f" (по выводу клиента: {state['client_code']})"
            if state.get("tunnel_at"):
                info["was_up"] = True
            if state.get("mtu"):
                info["mtu"] = str(state["mtu"])
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
        print(f"  туннель поднимался: {'да' if info['was_up'] else 'нет'}"
              + (f"; MTU {info['mtu']}" if info["mtu"] else ""))
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
            print(f"  предупреждение клиента: {text}")
        if info["before"]:
            print(f"  охрана за подключение: {info['before']}")
else:
    print("режим: units | backend | pool | quota | checks | vpngate | lists | files | config"
          " | leak | digest | subs | fwd | log | agentlog | watch")
EOF
python3 -c "import hashlib;d=open('fpv1check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул' | tee before.txt; for m in units files digest subs; do sudo python3 -I fpv1check.py $m; done | tee state-before.txt; sudo journalctl -u xgw --since "60 min ago" --no-pager | sudo python3 -I fpv1check.py log | tee log-before.txt
```

Ожидается:
- `e3bb28ed78866e84`;
- `Состояние: …`, `Перехват: включён …`, строки `Xray …` и `sing-box …` — записать как есть;
- четыре службы `active`; «поколений xgw-fp@ сейчас: 0 (—); процессов sstpc и pppd XGW: 0;
  других sstpc и pppd: 0; процессов openvpn: 0» — записать;
- «каталог freepool: 700; secrets.json: 600 (или нет); …; снимков списков: N (…); права
  снимков: 600 …»; «каталог profiles: 700 (или нет); файлов в нём: …»; «записей проверок: …;
  из них OpenVPN: …» — записать (это остатки прошлых вех: шлюз удалит их после установки);
  «отпечаток таблиц: совпадает; правила на месте (loaded): True»; «подписок с ошибкой: …;
  серверов в списке: …» — записать;
- счётчики журнала — записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать и продолжить. Режим `files` ответил
ошибкой (код до установки — прежний) — записать и продолжить.

Шаг 1.3. Только если в `state-before.txt` — «panel.json: режим пула: observe» (наблюдение
осталось включённым с прошлого прогона); иначе — пропустить, в отчёте «не нужен».
**Попроси заказчика** (дословно):

«Наблюдение за бесплатными серверами осталось включённым с прошлой проверки. В карточке
«Бесплатные серверы» нажмите, пожалуйста, «Выключить». Что ответила панель и что теперь на
кнопке?»

Нет ответа 10 минут — выключить командой (пункт 2 согласия), записать это в отчёт:
`cd "$HOME/xgw-fpv1" && sudo xgw pool mode off 2>&1 | tee off-before.txt` — ожидается «Бесплатный
пул выключен. Демон применит режим на ближайшем шаге». Затем (в обоих случаях):

```bash
cd "$HOME/xgw-fpv1" && sleep 180; for m in pool units files; do sudo python3 -I fpv1check.py $m; done | tee off-before-state.txt; sudo xgw status 2>&1 | grep -c '^Бесплатный пул' | sed 's/^/строк «Бесплатный пул» в xgw status: /' | tee -a off-before-state.txt
```

Ожидается: ответ панели — «Бесплатный пул выключен», на кнопке — «Включить наблюдение» (если
нажимал заказчик); «free_pool в состоянии: нет»; «поколений xgw-fp@ сейчас: 0; процессов
sstpc и pppd XGW: 0; …; процессов openvpn: 0»; «временных Xray и sing-box сейчас: 0»;
«panel.json: режим пула: off»; «строк «Бесплатный пул» в xgw status: 0».

Если не так: «free_pool в состоянии: режим …» — подождать 2 минуты и повторить блок; снова так
— **дефект «наблюдение не выключается»**; поколения или процессы больше 0 — **дефект «пул
оставил следы»**. Продолжить.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'SSTP = "sstp"' src/xgw/freepool/models.py && grep -q 'def sstpc_argv' src/xgw/freepool/agent.py && grep -q 'VPN_USER, SOCKS_USER = "xgw-vpn", "xgw-fps"' src/xgw/freepool/agent.py && grep -q '_VG_MARKER = "DDNS hostname"' src/xgw/freepool/providers.py && grep -q 'def retire_openvpn' src/xgw/freepool/store.py && grep -q 'def check_tunnel' src/xgw/freepool/probe.py && grep -q 'TemporaryFileSystem=/etc/ppp:ro /run/sstpc' packaging/xgw-fp@.service && grep -q 'SSTP_PACKAGE = "sstp-client"' src/xgw/install.py && test ! -e src/xgw/freepool/ovpnconf.py && test ! -e src/xgw/freepool/ovpn.py && grep -q 'def _pool_step' src/xgw/daemon.py && echo "правка в коде: есть"; cd "$HOME/xgw-fpv1"
```

Ожидается: «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. Она поставит пакет sstp-client из
архива Ubuntu и пользователя xgw-vpn. Внешний интерфейс (WAN), его соединение и DHCP она не
трогает; интернет дома пропадёт на несколько секунд, пока перезапускаются службы XGW.
Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fpv1/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fpv1/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'пакеты:|пользователь xgw-|ufw:|перезапущен|Xray запущен' "$HOME/xgw-fpv1/install.txt"; cd "$HOME/xgw-fpv1"
```

Ожидается: «код 0», «демон xgw запущен», «Xray запущен: участников …»; **строки «пакеты:
sstp-client» и «пользователь xgw-vpn»** (xgw-fps уже стоит — его строки нет). Записать строки
как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать); в
выводе есть «не установлены» про sstp-client — записать строку, **стоп** (без пакета SSTP
проверять нечего); строки «пакеты: sstp-client» нет, а код 0 — записать (пакет мог стоять) и
продолжить.

Шаг 2.3. Через 2 минуты — шлюз в порядке, бэкенд на месте, пул выключен:

```bash
sleep 120; cd "$HOME/xgw-fpv1" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул' | tee after-install.txt; for m in units backend digest files pool; do sudo python3 -I fpv1check.py $m; done | tee -a after-install.txt; sudo xgw pool 2>&1 | head -2 | tee -a after-install.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул|Конфиг|^Итог' | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpv1check.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки, строки
  `Бесплатный пул` нет; четыре службы `active`; «поколений xgw-fp@ сейчас: 0»;
- **«пакет sstp-client: <версия>; ppp: <версия>; /usr/sbin/sstpc: есть; /usr/sbin/pppd: есть;
  модуль sstp-pppd-plugin.so: <версия pppd>; /dev/ppp: есть; sing-box для проверок: есть»**;
  оба пользователя (xgw-vpn и xgw-fps) «есть, системный, оболочка /usr/sbin/nologin»;
  «прежнее (OpenVPN): пакет openvpn <версия или нет>; пользователь xgw-ovpn: есть» — записать;
  **«служба xgw-fp@.service: есть; в ней пустой /etc/ppp: да; /dev/ppp: да; OpenVPN в
  описании: нет»**; «пересылка IPv4: 1»; «набор fp_peers: нет»; «бэкенд SSTP: в правилах XGW
  нет набора fp_peers — перехват не загружен» (так и должно быть при выключенном пуле); «срок
  подготовки поколения у демона: 35 с сверх срока агента»;
- «отпечаток таблиц: совпадает; … True»;
- `files`: «secrets.json: …», «каталог profiles: …», «из них OpenVPN: …» — записать (шлюз
  удаляет остатки, когда пул впервые запускается; могут уже быть «нет» и 0);
- «free_pool в состоянии: нет»; первая строка `xgw pool` — «Бесплатный пул: выключен; регион EU
  (строго)», вторая — «Найдено …: из списков GitHub … (из них только sing-box …), Outline …,
  SSTP (VPN Gate) …» — записать;
- `OK    Бесплатный пул: выключен — режим подписок`; строку `Итог: …` — записать;
- в журнале с установки «Traceback: 0».

Если не так:
- не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать, сообщить заказчику и
  продолжить;
- «sing-box для проверок: нет» — **дефект «нет sing-box для проверок»**, продолжить;
- нет пакета sstp-client, /usr/sbin/sstpc или /usr/sbin/pppd, пользователя xgw-vpn или службы
  — **дефект «установка не поставила бэкенд SSTP»**, **стоп**;
- «модуль sstp-pppd-plugin.so: нет» — **дефект «нет модуля pppd»**, **стоп**;
- «/dev/ppp: нет» — **стоп**, сообщить заказчику (ядро без модуля PPP; модули не грузить);
- в службе «пустой /etc/ppp: НЕТ», «/dev/ppp: НЕТ» или «OpenVPN в описании: ЕСТЬ» — **стоп**:
  установлен не тот файл службы (повторить шаги 2.1–2.2);
- «бэкенд SSTP: …» с другой причиной, чем fp_peers, — записать дословно, **дефект «бэкенд не
  годится»**, продолжить;
- «срок подготовки …» не 35 — **стоп**: установлен не тот код (повторить шаг 2.1);
- во второй строке `xgw pool` есть «OpenVPN» — **стоп**: установлен не тот код;
- отпечаток не совпадает — повторить через минуту, снова так — **дефект «отпечаток таблиц
  меняется сам»**.

Шаг 2.4. Свободен ли суточный предел подключений (окно скользящее: подключения прошлых вех
считаются). Помощник читает предел уже установленного кода:

```bash
cd "$HOME/xgw-fpv1" && sudo python3 -I fpv1check.py quota | tee quota.txt
```

Ожидается: «подключений туннелей за сутки: N из 96; за час: H; свободно сейчас: F; шесть
свободны: сейчас» — записать (за два часа наблюдения шлюз делает до 4–6 подключений).

Если не так:
- другое число, не 96, — записать (в config.toml задан свой предел) и продолжить;
- «шесть свободны: <дата время>» — **спроси заказчика** (дословно): «Суточный предел
  подключений ещё занят прошлым наблюдением: шесть подключений освободятся к <дата время>.
  Подождать до этого времени (рекомендую) или отложить проверку?». «Подождать» — повторять
  этот шаг раз в 30 минут, пока не станет «сейчас», затем продолжить с шага 3.1. «Отложить» —
  **стоп**: наблюдение не включать, в отчёте «отложено: предел занят до <дата время>» и строка
  `quota.txt`, отчёт запушить (§9);
- «шесть свободны: никогда …» — **стоп**, сообщить заказчику (в config.toml предел меньше 6).

## 3. Включение наблюдения

Шаг 3.1. Включить и сразу 10 минут наблюдать живые поколения (помощник только читает
`/proc`, `systemctl show` и файлы состояния; в службы не вмешивается):

```bash
cd "$HOME/xgw-fpv1" && date '+%F %T' | tee observe-time.txt && sudo xgw pool mode observe 2>&1 | tee mode-on.txt; sudo python3 -I fpv1check.py watch 600 | tee live.txt
```

Ожидается:
- «Наблюдение за бесплатным пулом включено: … Демон применит режим на ближайшем шаге»;
- через 10 минут: «поколений увидено: N; дошло до фазы up: U; туннель поднимался: T», N — от
  1 до 2 (предел — 2 подключения в час), U и T — любые (0 тоже); **U должно быть равно T** —
  поднявшийся туннель доходит до фазы up;
- у каждого поколения:
  - «фазы guarded → connecting → …», «самопроверка пройдена», «причина отказа: …» (у
    GUARD_BLOCKED — с «по выводу клиента: …»), «туннель поднимался: да/нет» и MTU — записать;
  - «служба: CapabilityBoundingSet=cap_chown cap_kill cap_setgid cap_setuid cap_net_admin;
    DevicePolicy=closed; KillMode=mixed; NoNewPrivileges=yes; PrivateNetwork=yes;
    PrivateTmp=yes; ProtectSystem=strict; TemporaryFileSystem=… /etc/ppp … /run/sstpc …»
    (порядок слов и вид записи TemporaryFileSystem — любые; важны `/etc/ppp` с `ro` и
    `/run/sstpc`);
  - «агент: пользователь root; возможности chown,kill,setgid,setuid,net_admin; NoNewPrivs 1;
    своё пространство имён: да»; «интерфейсы внутри: fpi<номер>, lo» (до подъёма может быть
    и `fpt0`: его создаёт pppd в начале подключения);
  - снимок до подъёма: «маршрут по умолчанию внутри: нет; маршрутов к одному адресу: 1»;
    «работники: sstpc от root, возможности …» (и, может быть, «pppd от root, …») — **SOCKS-
    посредника (xray) до подъёма нет**; «xgw-vpn: 750 root:root; ppp.options 640 root:root»;
    «xgw-socks: нет»; **«/etc/ppp службы: пусто; /run/sstpc службы: …»** (там 1 — сокет
    sstpc — или «пусто», если sstpc ещё не дошёл до него);
  - «задание: 600 root:root; состояние: 600 root:root»; «секреты задания в state.json: нет»;
    «veth на хосте: есть; элементов fp_peers: 1»;
  - у поднявшегося, кроме того: «после подъёма: маршрут по умолчанию внутри: fpt0; маршрутов к
    одному адресу: 1 или 2»; **«после подъёма: работники: pppd от root, возможности …; sstpc от
    xgw-vpn, возможности нет, NoNewPrivs 1; xray от xgw-fps, возможности нет, NoNewPrivs 1»** —
    записать дословно; «после подъёма: xgw-socks: 750 root:xgw-fps; socks.json 640
    root:xgw-fps»; «после подъёма: /etc/ppp службы: пусто; /run/sstpc службы: 1 (сокетов sstpc
    1)»; **«изнутри: TCP Cloudflare:443 — …; DNS шлюза туннеля — …; DNS Cloudflare — …»** и
    **«fpt0 (последнее): в туннель … пакетов, из туннеля … пакетов»** — **записать дословно**:
    это главный результат вехи;
  - у каждого, где туннель поднимался: **«охрана после подъёма: клиент VPN 0, работник 0,
    ответы ядра …, служебный IPv6 …»**; **«канал к серверу после подъёма: от сервера N пакетов
    (X КБ), к серверу M пакетов (Y КБ)»** и строки «предупреждение клиента: …» (если есть) —
    **записать дословно**; у отказавшего до подъёма, если охрана что-то отбила, — «охрана за
    подключение: …» — записать.

Записать всё как есть.

Если не так:
- «ошибка: …» в ответе команды — записать дословно, **стоп**, сообщить заказчику;
- «поколений увидено: 0» — продолжить: шаги 3.2 и 4.1 покажут, идут ли подключения (строки
  «SSTP туннелем: …» и «суточный предел подключений: …» в `pool-1.txt` — записать);
- у агента не root, другие возможности, NoNewPrivs не 1 или «своё пространство имён: НЕТ»; у
  службы нет `PrivateNetwork=yes` или `NoNewPrivileges=yes` — **дефект «изоляция поколения»**,
  **стоп**, сообщить заказчику;
- «/etc/ppp службы» не «пусто» — **дефект «pppd видит настройки машины»**, **стоп**;
- маршрут по умолчанию до подъёма не «нет» или после подъёма не `fpt0` — **дефект «маршрут мимо
  туннеля»**, **стоп**;
- после подъёма «sstpc от root» — **дефект «клиент не сбросил права»** (строки «предупреждение
  клиента» — в отчёт), продолжить; xray от root, с возможностями или NoNewPrivs не 1 — **дефект
  «права работника»**, **стоп**; у pppd возможности агента — так и должно быть (ему нужен
  net_admin), не дефект;
- до подъёма в работниках есть `xray` или `xgw-socks` не «нет» — **дефект «посредник до
  туннеля»**;
- у поднявшегося нет строки «изнутри: …» — **дефект «нет проверки изнутри»**; в ней `TCP … —
  —` (нет итога) — **дефект «проверка изнутри не выполнилась»**;
- «туннель поднимался: да», а фазы up нет и причина `SOCKS_FAILED` — **дефект «посредник не
  запускается»** (шаг 4.1 покажет строку причины);
- в «охрана после подъёма» у клиента или работника больше 0 — **дефект «посредник идёт мимо
  туннеля»**; «ответы ядра» и «служебный IPv6» — любые, не дефект;
- у поднимавшегося нет строки «канал к серверу после подъёма» — **дефект «канал к серверу не
  прочитан»**; в ней «от сервера» 8 КБ и больше, а «fpt0 (последнее): … из туннеля 0 пакетов» —
  **дефект «ответы сервера не доходят до туннеля»**; «от сервера» меньше 8 КБ — сервер или
  блокировка не пропускают данные после подъёма: не дефект, записать;
- причина `GUARD_BLOCKED` — **дефект «охрана отбивает клиента»** (строку «охрана за
  подключение» — в отчёт);
- причина `PPP_DEVICE_FAILED`, `SSTPC_SOCKET` или `AGENT_EXITED` — **дефект «служба SSTP не
  работает: <код>»** (шаг 4.1 покажет строку «SSTP: …»), продолжить;
- «fpt0 (последнее): в туннель 0 пакетов» у поднявшегося — **дефект «в туннель ничего не
  уходит»**;
- права файлов шире (не 750/640/600) или владелец другой — **дефект «права файлов
  поколения»**; «секреты задания в state.json: ЕСТЬ» — **дефект «секрет в состоянии»**;
- «самопроверка НЕ пройдена» — **дефект «охрана пропускает»**, **стоп**;
- «агент: не найден» или строки «не прочитаны» — записать (поколение могло закончиться между
  опросами) и продолжить.

Шаг 3.2. Сразу после шага 3.1 — правила пула, источники, бэкенд, остатки OpenVPN:

```bash
sleep 10; cd "$HOME/xgw-fpv1" && for m in pool vpngate lists backend digest units files; do sudo python3 -I fpv1check.py $m; done | tee pool-1.txt; sudo xgw status 2>&1 | grep -E '^Состояние|^Бесплатный пул' | tee -a pool-1.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул' | tee -a pool-1.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpv1check.py log | tee log-1.txt
```

Ожидается:
- «status.json: N с назад» (N меньше 120); «free_pool в состоянии: режим observe, регион EU;
  найдено … (из списков GitHub L, …; Outline …; SSTP V); …; ключи OpenVPN в сводке: нет»: L —
  150 или больше, **V — 40 или больше**; **«SSTP туннелем: годится; …; подключений за час …,
  за сутки … из 96»**; «суточный предел подключений: не занят»;
- строки источников: `vpngate: SUCCESS` (или `PARTIAL`), `vpnbook: SUCCESS`, `igareck:
  SUCCESS; …`, `mahdibland: SUCCESS; …`;
- режим `vpngate`: **«vpngate: SUCCESS; вариантов V (sstp sstp V); OpenVPN в снимке: 0;
  отклонено …»**, «причины отказа: нет SSTP …» (и, может быть, другие — записать все); «страны
  по флагу: …» — записать (ожидаются JP, KR, RU и другие); «порт SSTP: 443 …, другой …» —
  записать; **«с публичным IPv4: V; имя *.opengw.net: V»**; «vpnbook: SUCCESS; вариантов 3 или
  больше (xray shadowsocks …); OpenVPN в снимке: 0»;
- режим `lists`: у обоих «в providers: да»; «служебных IPv4: 0»; причины отказа — записать;
- «набор fp_peers: есть; элементов 0» (или 1); «бэкенд SSTP: годится»;
- «отпечаток таблиц: совпадает; … True»;
- **остатки OpenVPN убраны**: «secrets.json: нет»; «каталог profiles: нет; файлов в нём: 0»;
  «записей проверок: …; из них OpenVPN: 0»; «права снимков: 600 N»; «panel.json: режим пула:
  observe»;
- `Состояние: HEALTHY …`; строка `Бесплатный пул (наблюдение, регион EU): найдено …`;
- `OK    Бесплатный пул: режим observe; бэкенд SSTP готов (sstpc и pppd, /dev/ppp,
  пользователи xgw-vpn и xgw-fps, служба xgw-fp@, набор fp_peers)`;
- в журнале с установки: «VPN Gate: список получен: 1» (или больше), «VPNBook…», «igareck…»,
  «mahdibland…»; **«список получен через подписку: 4»** (или больше); «список получен
  напрямую: 0»; «остатки OpenVPN удалены: 0 или 1» (1 — если удалил демон; 0 — если удалила
  команда `xgw pool` шага 2.3: строки `files` это покажут) — записать; «остатки OpenVPN не
  удалены: 0»; «из них OpenVPN: 0»; «шаг пула не выполнен: 0»; «Traceback: 0».

Записать всё как есть.

Если не так:
- «free_pool в состоянии: нет» — подождать 2 минуты и повторить шаг; снова нет — **дефект
  «наблюдение не включилось»**;
- `vpngate` не `SUCCESS`/`PARTIAL` — подождать 3 минуты и повторить; снова `UNAVAILABLE` —
  записать (сайт не ответил через подписку) и продолжить — тогда SSTP-часть вехи не
  проверяется; `SCHEMA_CHANGED` — **дефект «формат страницы VPN Gate изменился»** (строка
  `detail` — в отчёт), продолжить;
- V меньше 40, но больше 0 — записать (VPN Gate показывает каждому свою часть списка) и
  продолжить; V равно 0 при `SUCCESS` — **дефект «серверы SSTP не разобраны»** (причины отказа
  — в отчёт);
- «OpenVPN в снимке» больше 0 после `SUCCESS` — **дефект «старый снимок не заменён»**;
- «ключи OpenVPN в сводке: ЕСТЬ» — **дефект «сводка со старыми ключами»**;
- «secrets.json» или «каталог profiles» не «нет», или «из них OpenVPN» больше 0 — **дефект
  «остатки OpenVPN не убраны»**;
- «служебных IPv4» больше 0 — **дефект «адрес LAN в пуле»**;
- «бэкенд SSTP: …» с другой причиной — записать дословно, **дефект «бэкенд не годится»**;
- «список получен напрямую» больше 0 при `HEALTHY` — **дефект «списки не через подписку»**;
- «права снимков» не только 600 — **дефект «права снимков»**;
- «шаг пула не выполнен» или «Traceback» больше 0 — записать
  `sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -20 | tee traceback-1.txt`
  (только строки с файлами и ошибкой) — **дефект «шаг пула падает»**.

Шаг 3.3 (при согласии на пункт 3). **Попроси заказчика** (дословно):

«Откройте панель XGW (обновите страницу: Ctrl+F5), найдите карточку «Бесплатные серверы».
Прочитайте мне первую фразу под заголовком целиком и названия источников в списке под ней с
метками (например «ок»).»

Ожидается: фраза «Наблюдение (регион EU): найдено N: из списков GitHub — L, ключей Outline — …,
SSTP (VPN Gate) — V, туннелем поднялось …, подключений за час …. Проверено …, пригодно …. Трафик
проверок за сутки — … из 512 МБ; серверы списков GitHub — … МБ, без предела.»; N, L и V — как
в `pool-1.txt` (могут отличаться на несколько); слова «OpenVPN» во фразе нет; источники —
«VPN Gate», «VPNBook», «GitHub igareck (проверены в России)», «GitHub mahdibland» с метками.
Записать ответ.

Если не так: во фразе «OpenVPN» — попросить обновить страницу (Ctrl+F5) и прочитать снова;
снова так — **дефект «карточка со старым текстом»**.

## 4. Подключения и проверки

Шаг 4.1. Не раньше чем через 35 минут после шага 3.1:

```bash
cd "$HOME/xgw-fpv1" && S=$(date -d "$(cat observe-time.txt)" +%s) && for m in "checks $S" pool units backend fwd files config; do sudo python3 -I fpv1check.py $m; done | tee checks-1.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpv1check.py agentlog | tee agent-1.txt; sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpv1check.py log | tee log-2.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee -a checks-1.txt
```

Ожидается (**записать все строки `checks` и `agentlog` целиком** — это итог вехи):
- «проверок с начала прогона: C (каталоги …, списки GitHub G; всего записей …; записей
  OpenVPN: 0); …»: G — 20 или больше;
- **SSTP**: «SSTP туннелем: попыток A, поднялось U» (A — 2 или больше); «итоги через поднятый
  туннель», «отказы без туннеля» — записать (коды — ниже); **«изнутри, TCP Cloudflare:443: …»**,
  **«изнутри, DNS: …»**, **«из туннеля вернулось: …»**, **«охрана после подъёма отбила у
  клиента или работника: 0 из …»**, **«туннель пропускает TCP, а проба через посредника — нет:
  B»**, **«канал к серверу после подъёма, от сервера: …»**, «страны выхода через туннель SSTP:
  …» — записать; «причины «не проверено» у SSTP: …» — записать; «подключений за час: H
  (vpngate …)», H не больше 2; «трафик одной проверки туннелем, наибольший: … МБ» не больше 20;
- **серверы списков** — как в прошлых вехах: «списки GitHub: …», страны, причины «не
  проверено», «трафик одной проверки сервера списка, наибольший: X МБ», X не больше 1;
- «трафик проверок за сутки: каталоги … МБ» не больше 384; «серверы списков … МБ» — записать;
- сводка: «пригодно R (…)» — в скобках только `EU …` или «—»; «пригодные по источникам: …» —
  записать;
- «поколений xgw-fp@ сейчас: 0» или 1; «процессов sstpc и pppd XGW: 0» (или 2 — во время
  подключения); «других sstpc и pppd: 0»; «процессов openvpn: 0»; «набор fp_peers: есть;
  элементов 0» (или 1); «veth fpv сейчас: 0» (или 1);
- «из fpv* к серверам пула: пакетов P»; **«из fpv* — сброс: пакетов 0»**;
- «из них OpenVPN: 0»; «без варианта в снимках: X» — X не больше 20; «временных Xray и
  sing-box сейчас: 0» (или 1);
- **«из них вариантов бесплатного пула целиком (адрес, порт, ключ): 0; …; выходов к
  работникам пула: 0; …, из них вариантов пула целиком: 0»** — трафик через пул не идёт;
- журнал поколений: «самопроверок охраны: S; итоги: …» — только `ENETUNREACH` и `… (охрана)`;
  **«туннель поднят: T; SOCKS-работник готов: W» — W равно T**; «проверок изнутри» и «итогов
  туннеля» — как T; строки «изнутри: …» и «итог туннеля: …» — **записать все**; «в туннель ушло
  0 пакетов: 0»; **«после подъёма отбито у клиента или работника больше 0: 0»**; «итогов без
  счётчиков охраны: 0»; «канал к серверу …» и строки «канал к серверу: …» — записать все;
  строки «предупреждение клиента: …» — записать все; «отказы поколений: …», «у GUARD_BLOCKED по
  выводу клиента: …», «охрана за подключение: …» — записать; **строки «SSTP: …» — записать
  все**: по ним видна причина каждого отказа; «строк с внешним адресом: 0»; «строк pppd: …» —
  записать; «Traceback: 0»;
- журнал демона: «из них SSTP: …» (как A или больше), «из них OpenVPN: 0», «из них серверов
  списков: …», «с итогом изнутри туннеля: …» (как T), «Traceback: 0»;
- `HEALTHY`, перехват включён.

Коды отказов SSTP (в «отказы без туннеля», «отказы поколений» и сводке):
- **дефекты шлюза** — `GUARD_BLOCKED`, `GUARD_FAILED`, `NETWORK_UNREACHABLE`, `BACKEND_START`,
  `NO_VETH`, `NO_USER`, `BAD_MANIFEST`, `AGENT_ERROR`, `AGENT_EXITED`, `PPP_DEVICE_FAILED`,
  `SSTPC_SOCKET`, `BAD_TUNNEL_ADDRESS`, `SOCKS_FAILED`: **дефект «бэкенд SSTP: <код>»** (строки
  «SSTP: …» — в отчёт), продолжить; `GUARD_FAILED` — **стоп**, сообщить заказчику;
- **сервер или сеть (ТСПУ)** — `HOST_UNREACHABLE`, `CONNECT_TIMEOUT`, `CONNECT_REFUSED`,
  `CONNECT_FAILED`, `TRANSPORT_RESET`, `TIMEOUT`, `SSTP_REFUSED`, `PPP_TIMEOUT`, `LINK_LOST`,
  `UNKNOWN`: не дефект, записать; у `UNKNOWN` строки «SSTP: …» нет — **наблюдение «UNKNOWN без
  строки»**;
- **главные для вехи** — `CERT_VERIFY_FAILED` (сертификат сервера не прошёл проверку:
  возможно, сервер без имени в TLS отдаёт другой сертификат) и `AUTH_FAILED` (вход `vpn`/`vpn`
  не принят): записать число; **у всех попыток один из них** — **наблюдение «SSTP: все отказы
  <код>»**, в отчёт — строки «SSTP: …».

Если не так:
- G меньше 20 — подождать 10 минут и повторить; снова так — **дефект «серверы списков не
  проверяются»**;
- A равно 0, а «SSTP туннелем: годится» — подождать 10 минут и повторить; снова 0 — посмотреть
  «причины «не проверено» у SSTP» и «подключений за час»: подключений 0 — **дефект «подключения
  SSTP не идут»**;
- **B больше 0** — **дефект «туннель пропускает, а проба через посредника — нет»**;
- «в туннель ушло 0 пакетов» больше 0 — **дефект «в туннель ничего не уходит»**;
- «после подъёма отбито у клиента или работника больше 0» не 0 — **дефект «посредник идёт мимо
  туннеля»**;
- «SOCKS-работник готов» меньше «туннель поднят» — **дефект «посредник не запускается»**;
- «итогов без счётчиков охраны» больше 0 — **дефект «итог туннеля без охраны»**;
- «8 КБ и больше» больше 0, а в «из туннеля вернулось» нет «больше 0» — **дефект «ответы
  сервера не доходят до туннеля»**;
- у `GUARD_BLOCKED` в «охрана за подключение» «клиент VPN 0» — **дефект «ложный GUARD_BLOCKED»**;
- в итогах самопроверки есть что-то кроме `ENETUNREACH` и `(охрана)` — **дефект «охрана
  пропускает»**, **стоп**, сообщить заказчику;
- H больше 2 — **дефект «пределы подключений не соблюдены»**;
- «из fpv* — сброс» больше 0 — **дефект «из пространства имён уходит мимо сервера»**;
- «других sstpc и pppd» больше 0 — записать (на машине свой клиент SSTP); «процессов openvpn»
  больше 0 — записать;
- поколений, veth или каталогов 2 и больше — повторить через 2 минуты; снова так — **дефект
  «поколения не убираются»**;
- в скобках у «пригодно» есть не `EU` — **дефект «регион не строгий»**;
- варианты пула целиком или выходы к работникам в рабочих конфигах больше 0 — **дефект «пул
  попал в рабочий конфиг»**, **стоп**, сообщить заказчику;
- «трафик проверок за сутки: каталоги» больше 384 — **дефект «бюджет каталогов не соблюдён»**;
- «строк с внешним адресом» больше 0 — **наблюдение** (адрес в журнале службы); строки не
  переписывать.

Шаг 4.2. Не раньше чем через **125 минут** после шага 3.1 — второй и третий час (подключений
SSTP — 2 в час, нужно больше попыток):

```bash
cd "$HOME/xgw-fpv1" && S=$(date -d "$(cat observe-time.txt)" +%s) && for m in "checks $S" pool units backend fwd files; do sudo python3 -I fpv1check.py $m; done | tee checks-2.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpv1check.py agentlog | tee agent-2.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee -a checks-2.txt
```

Ожидается: «проверок с начала прогона: … (каталоги …, списки GitHub G2; …)», G2 больше G;
«SSTP туннелем: попыток A2, …», **A2 — 5 или больше** (и больше A); «подключений за час: …» не
больше 2; остальное — как в шаге 4.1. Записать всё.

Если не так: как в шаге 4.1. G2 равно G — **дефект «проверки серверов списков остановились»**;
A2 равно A — повторить через 10 минут; снова равно — посмотреть в `checks-2.txt` строку
«подключений за час: …; за сутки: D»: D равно пределу из шага 2.4 — **наблюдение «суточный
предел занят»**; иначе — **дефект «подключения SSTP остановились»**.

## 5. Сводка в команде

Шаг 5.1 (при согласии на пункт 3). Сводка команды и панели — одна:

```bash
cd "$HOME/xgw-fpv1" && sudo xgw pool 2>&1 | head -7 | tee cli.txt; sudo xgw pool status --json | python3 -c "import json,sys;d=json.load(sys.stdin);print('json:', d['mode'], d['found'], d.get('lists'), d.get('sstp'), d['checked'], d['ready'], d['tunnels_up'], d.get('lists_spent_mb'))" | tee -a cli.txt
```

Затем **попроси заказчика** (дословно): «Прочитайте ещё раз из карточки «Бесплатные серверы»
числа после слов «найдено», «из списков GitHub», «SSTP (VPN Gate)», «туннелем поднялось» и
«Проверено».»

Ожидается: строки «Бесплатный пул: наблюдение (трафик через подписку); регион EU (строго)»,
«Найдено N: из списков GitHub L (из них только sing-box S), Outline …, SSTP (VPN Gate) V» —
**без слов «проверка туннелем недоступна»**; «SSTP туннелем: поднялось U…; подключений за час
…, за сутки … из 96»; «Проверено C, …; SSTP с открытым адресом …, адрес закрыт …»;
«Пригодные по источникам: …» (если пригодные есть); «Трафик проверок за сутки: …»; «json:
observe N L V C R U …»; числа заказчика — как N, L, V, U и C (могут отличаться на несколько).
Записать.

Если не так: в строке «Найдено» есть «проверка туннелем недоступна» — **дефект «xgw pool не
берёт сводку демона»**; есть слово «OpenVPN» — **дефект «сводка со старым текстом»**; команда
отвечает ошибкой — **дефект «xgw pool»**; числа заказчика отличаются больше чем на 10 (U —
больше чем на 1) — **дефект «сводка панели и команды расходится»**.

## 6. Секреты

Шаг 6.1.

```bash
cd "$HOME/xgw-fpv1" && sudo python3 -I fpv1check.py files | tee secrets.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpv1check.py leak | sed 's/^/xgw: /' | tee -a secrets.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpv1check.py leak | sed 's/^/xgw-fp@: /' | tee -a secrets.txt; stat -c 'status.json: %a' /run/xgw/status.json | tee -a secrets.txt
```

Ожидается: «каталог freepool: 700; secrets.json: нет; candidates.json: 600; …; права снимков:
600 …»; «каталог profiles: нет»; у строки `xgw:` — **«строк со ссылкой сервера: 0; строк с
именем *.opengw.net: 0; строк с паролем клиента: 0»**, «строк с внешним адресом: …» — записать;
у строки `xgw-fp@:` — **все четыре — 0** (pppd пишет в журнал только частные адреса туннеля);
«status.json: 644». Записать.

Если не так: строк со ссылкой, с именем `*.opengw.net` или с паролем клиента больше 0 —
**дефект «секрет или имя сервера в журнале»**; у `xgw-fp@:` «строк с внешним адресом» больше 0 —
**дефект «адрес сервера в журнале службы»**.

## 7. Выключение

Шаг 7.1 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В карточке «Бесплатные серверы» нажмите «Выключить». Что ответила панель и что теперь
написано в карточке и на кнопке?»

Сразу после ответа:

```bash
cd "$HOME/xgw-fpv1" && sleep 60; date '+%F %T' | tee off-time.txt; sleep 120; for m in pool units backend files; do sudo python3 -I fpv1check.py $m; done | tee off.txt; sudo xgw pool 2>&1 | head -1 | tee -a off.txt; sudo xgw status 2>&1 | grep -c '^Бесплатный пул' | sed 's/^/строк «Бесплатный пул» в xgw status: /' | tee -a off.txt; sudo xgw diag 2>&1 | grep -E 'Бесплатный пул' | tee -a off.txt
```

Ожидается: ответ панели — «Бесплатный пул выключен»; в карточке — «Альтернативный режим:
бесплатные серверы (списки GitHub, VPN Gate, VPNBook) вместо подписки. …», на кнопке —
«Включить наблюдение»; «free_pool в состоянии: нет»; «поколений xgw-fp@ сейчас: 0; процессов
sstpc и pppd XGW: 0»; «набор fp_peers: нет»; «veth fpv сейчас: 0; каталогов поколений: 0»;
«временных Xray и sing-box сейчас: 0»; «Бесплатный пул: выключен; …»; «строк «Бесплатный пул»
в xgw status: 0»; `OK    Бесплатный пул: выключен — режим подписок`. Записать.

Если не так: «free_pool в состоянии: режим …» — подождать 2 минуты и повторить; снова так —
**дефект «наблюдение не выключается»**. Поколения, veth, каталоги, процессы sstpc и pppd XGW или
временные процессы больше 0 — повторить через 2 минуты; снова так — **дефект «пул оставил
следы»**. «набор fp_peers: есть» — **дефект «правила пула остались»**.

## 8. Итог

Шаг 8.1. Через 3 минуты после шага 7.1:

```bash
sleep 180; cd "$HOME/xgw-fpv1" && sudo journalctl -u xgw --since "$(cat off-time.txt)" --no-pager | sudo python3 -I fpv1check.py log | tee log-off.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpv1check.py log | tee final.txt; S=$(date -d "$(cat observe-time.txt)" +%s); for m in "checks $S" vpngate lists digest subs config units; do sudo python3 -I fpv1check.py $m; done | tee -a final.txt; sudo journalctl -u 'xgw-fp@*' --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpv1check.py agentlog | tee agent-final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee -a final.txt
```

Ожидается:
- в `log-off.txt` (с минуты после нажатия «Выключить»): все «список получен» — 0, «проверок
  серверов пула: 0»;
- в `final.txt`: **«Traceback: 0»**, «шаг пула не выполнен: 0», **«следы поколения не убраны:
  0»**, «правила загружены заново» — не больше 2, «откат на last-good: 0», «Read-only file
  system» и «Permission denied» — не больше, чем в `log-before.txt`; «из них OpenVPN: 0»;
- итог проверок (`checks`), страницы VPN Gate (`vpngate`) и списков (`lists`) — записать
  целиком: это итог вехи;
- «отпечаток таблиц: совпадает; … True»; «подписок с ошибкой» — не больше, чем до установки;
  «серверов в списке» — как до установки (±2); в рабочих конфигах вариантов пула целиком — 0;
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

Повторная установка в этой вехе не проверяется: вторая установка не ставит пакет и
пользователей заново (юнит-тесты установщика), а прошлая повторная — в М2а.

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
- Наблюдение не оставлять включённым после проверки: без решения заказчика шлюз не должен сам
  ходить к бесплатным серверам (в М2а.3 оставленное на ночь наблюдение заняло предел
  подключений). Заказчик не ответил на шаг 7.1 за 30 минут — выключить командой
  `sudo xgw pool mode off` (пункт 2 согласия) и выполнить шаг 8.1.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-m2v1-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`freepool`), коммит «Отчёт: XGW 0.2.0, бесплатные серверы, веха М2в.1», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, бесплатные серверы, веха М2в.1 (SSTP вместо OpenVPN у VPN Gate)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
fpv1check.py: <сумма, 16 знаков>.

## Итог вехи
### SSTP (VPN Gate)
| Серверов SSTP в списке | Попыток | Туннель поднимался | Дошло до up | CERT_VERIFY_FAILED | AUTH_FAILED | Прочие отказы | Изнутри TCP | Изнутри DNS | Из туннеля вернулось | Канал после подъёма: от сервера / к серверу | Охрана после подъёма (клиент/работник) | Итоги пробы | Страны выхода | sstpc после подъёма |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| … | … | … | … | … | … | … | … | … | … | … | … | … | … | от xgw-vpn / от root |

### Служба и остатки OpenVPN
| sstp-client / ppp | Модуль pppd | /dev/ppp | /etc/ppp службы | /run/sstpc службы | secrets.json | profiles | Записей OpenVPN | OpenVPN в снимках |
|---|---|---|---|---|---|---|---|---|
| … | … | … | … | … | … | … | … | … |

### Списки GitHub
| Источник | Вариантов | Проверено | Работают (OK/SLOW) | Пригодны (EU) | Страны выхода | Главные отказы |
|---|---|---|---|---|---|---|
| igareck | … | … | … | … | … | … |
| mahdibland | … | … | … | … | … | … |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | сумма, состояние, службы, остатки OpenVPN, отпечаток, подписки, журнал |
| 1.3 выключение прошлого наблюдения | … / не нужен | кто выключил, ответ панели, следы |
| 2.2 установка | … | код, «пакеты: sstp-client», «пользователь xgw-vpn» |
| 2.3 после установки | … | HEALTHY, пакеты, модуль, /dev/ppp, пользователи, служба, срок 35 с, xgw pool, diag |
| 2.4 предел подключений | … / отложено | за сутки N из 96, «шесть свободны», решение заказчика |
| 3.1 живые поколения | … | поколений / туннель поднимался / дошло до up; служба, /etc/ppp, /run/sstpc; работники до и после подъёма; изнутри, fpt0, канал, охрана |
| 3.2 правила и источники | … | VPN Gate (SSTP, страны, порты, отказы), VPNBook, списки, бэкенд, остатки OpenVPN, журнал |
| 3.3 карточка | … / не выполнялся | фраза, источники и метки |
| 4.1 проверки, 35 мин | … | SSTP: попытки, туннель/up, коды, строки «SSTP: …», изнутри, данные; списки; пределы; конфиги |
| 4.2 проверки, 125 мин | … | то же |
| 5.1 xgw pool | … / не выполнялся | строки, json, числа заказчика |
| 6.1 секреты | … | права, ссылки, имена серверов, пароль клиента, внешние адреса в журналах |
| 7.1 выключение | … / не выполнялся | ответ панели, карточка, следы |
| 8.1 итог | … | после выключения, Traceback, следы, правила, конфиги, HEALTHY |
| 8.2 сайты | … / не выполнялся | ответ заказчика |

## Выводы шагов
<файлы $HOME/xgw-fpv1/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
