# Проверка XGW 0.2.0: защита по четвёртому аудиту

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-020e/…`). Файл помощника создавай только командой шага 1.2, выполненной в терминале:
если создать его по-другому (например, записать текст в файл инструментом), сумма не совпадёт.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `audit4`, версия 0.2.0. Сейчас на машине стоит 0.2.0 с
коммита 7c44b11 (ветка `panel-cpu`, теперь она в `main`); её проверка пройдена, отчёт
`docs/TEST-REPORT-REAL-MACHINE-0.2.0-panel-2026-10-27.md`. Телефон — S25 Ultra в домашней сети,
на нём приложение XGW. Команды — в терминале сеанса заказчика (`sudo` от его имени; шаги 1.3 и
3.2 — без `sudo`).

Что изменено (ASSUMPTIONS п. 253):
1. **API Xray больше не на порту.** Раньше Xray слушал управляющий порт 127.0.0.1:10085 без
   пароля: любая программа на машине, даже без `sudo`, могла через него пустить трафик мимо
   VPN. Теперь это файл-сокет `/run/xgw-xray/api.sock`, открытый только пользователю и группе
   `xray`; в группу добавлены демон XGW и задание обновления ядер.
2. **`/run` только для чтения у всех служб XGW.** В прошлом отчёте у Xray, sing-box и DHCP он
   был открыт на запись. Причина — не версия systemd: его открывают строки
   `ProtectKernelTunables` и `ProtectProc`. Теперь у этих служб (и у службы сети `xgw-net`)
   стоит явная строка `ReadOnlyPaths=/run`.
3. **Вход телефонов через Funnel.** Раньше 10 неудачных запросов кого угодно из интернета
   закрывали вход на минуту всем телефонам. Теперь закрываются только привязка и запросы без
   верной подписи, привязанный телефон работает. Плюс предел одновременных соединений (16) и
   срок на чтение запроса (20 с).
4. **Подписки.** При перенаправлении на другой адрес заголовки `Authorization` и `Cookie` больше
   не отправляются; перенаправление с https на http — отказ.
5. **Проверка правил nftables** сверяет отпечаток всей таблицы и видит пропажу одного правила.
   Отпечаток не должен меняться сам (от счётчиков трафика): иначе правила загружались бы по
   кругу — это проверяют §5 и §6.
6. Повтор подписанного запроса телефона после перезапуска демона не принимается; ключ
   `xray.api_port` в `config.toml` больше не нужен — установка выключит строку, если она есть.

Здесь, у разработчика (Ubuntu 26.04, systemd 259), проверены юнит-тесты и опытом — сокет API в
Xray 26.10.21 и права на него под systemd. На systemd 255 (эта машина) — только здесь. Шлюз
заказчика — эта программа.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list` и `nft -t list`), `ip`, `iptables`, `tc`, `sysctl -w`,
  `systemd-run`; команды `tailscale` и `xray`. Исключения — только то, что запускает помощник:
  `tailscale status --json` (печатает только состояние), `xray api bi` (только читает), временные
  пробы `systemd-run` в шаге 3.3 (пробуют записать файл в `/run` и подключиться к сокету API) и
  запросы к API приложения на 127.0.0.1 в §4 (без подписи — шлюз их отклоняет).
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/etc/systemd`, код XGW. Печатать `config.toml` (`cat`, `less`, `grep` по нему) — в нём ключи
  подписок. Серверы, переключатели и кнопки в панели и в приложении меняет и нажимает только
  заказчик. Коммитить что-либо, кроме отчёта (§7).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP и домены серверов
  VPN, строки журнала. Можно: адреса устройств в домашней сети (`192.168.…`), названия и страны
  серверов, имена программ, проверок и служб, счётчики, права файлов, времена.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю защиту XGW по четвёртому аудиту. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд.
(2) В панели XGW по моей просьбе: нажмёте «Проверить сеть» два раза (до и после установки),
«Обновить» над подписками, выберете вручную любой сервер кнопкой «Выбрать» и через минуту
вернёте «Автовыбор».
(3) Телефон: по моей просьбе трижды по 1–2 минуты не открывать приложение XGW, а потом открыть
его и сказать, показывает ли оно состояние шлюза. В конце откроете любой сайт на этом
компьютере и на телефоне.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — шаги 1.5, 3.5, 5.2 и 5.4 пропустить; против 3 — шаг 1.4,
§4 и шаг 5.5. В отчёте у пропущенного — «не выполнялся».

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-020e" && chmod 700 "$HOME/xgw-020e" && cd "$HOME/xgw-020e" && cat > v020echeck.py <<'EOF'
"""XGW 0.2.0, четвёртый аудит: помощник проверки. Читает /proc, файлы служб, права сокета API
Xray, состояние XGW (/run/xgw, /var/lib/xgw — только счётчики и да/нет), журнал со
стандартного ввода (только счётчики). Кроме чтения: api — подключается к API Xray и вызывает
`xray api bi` (только чтение); probe — временная служба systemd-run с ограничениями службы XGW
(пробует записать файл в /run и в её каталоги в /run и вызвать `xray api bi`); phone-lock и
phone-limits — запросы без подписи и пустые соединения к API приложения на 127.0.0.1.
Режимы: units, api, probe, phone-lock, phone-limits, phone-nonces, digest, subs, netcheck, ts,
log."""
import grp
import http.client
import json
import os
import pwd
import re
import select
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
UNIT_DIR = Path("/etc/systemd/system")
XRAY = "/opt/xgw/xray/xray"
SOCK = "/run/xgw-xray/api.sock"
LIB = "/opt/xgw/lib"
SANDBOX = ("ProtectSystem", "ReadWritePaths", "ReadOnlyPaths", "PrivateTmp", "NoNewPrivileges",
           "CapabilityBoundingSet", "SupplementaryGroups", "ProtectHome", "ProtectKernelModules",
           "ProtectKernelLogs", "ProtectKernelTunables", "ProtectControlGroups", "ProtectClock",
           "ProtectHostname", "ProtectProc", "RestrictNamespaces", "RestrictRealtime",
           "RestrictSUIDSGID", "LockPersonality", "SystemCallArchitectures", "SystemCallFilter",
           "SystemCallErrorNumber", "RestrictAddressFamilies", "PrivateDevices",
           "MemoryDenyWriteExecute")


def show(unit, prop):
    return subprocess.run(["systemctl", "show", "-p", prop, "--value", unit],
                          capture_output=True, text=True).stdout.strip()


def run_mount(pid):
    """Как смонтирован /run у процесса: последняя запись /run в его mountinfo."""
    last = ""
    try:
        for line in open(f"/proc/{pid}/mountinfo", encoding="utf-8"):
            fields = line.split()
            if len(fields) > 5 and fields[4] == "/run":
                last = fields[5]
    except OSError:
        return "-"
    if not last:
        return "-"
    return "только чтение" if last.split(",")[0] == "ro" else "запись"


def perms(path):
    try:
        info = os.stat(path)
    except OSError as exc:
        return f"нет (errno {exc.errno})"
    try:
        owner = pwd.getpwuid(info.st_uid).pw_name
    except KeyError:
        owner = str(info.st_uid)
    try:
        group = grp.getgrgid(info.st_gid).gr_name
    except KeyError:
        group = str(info.st_gid)
    return f"{stat.filemode(info.st_mode)} {owner}:{group}"


def port_listens(port):
    try:
        lines = open("/proc/net/tcp", encoding="ascii").read().splitlines()[1:]
    except OSError:
        return False
    for line in lines:
        fields = line.split()
        address, _, hexport = fields[1].partition(":")
        if address == "0100007F" and int(hexport, 16) == port and fields[3] == "0A":
            return True
    return False


def api_answers(server):
    try:
        done = subprocess.run([XRAY, "api", "bi", "-s", server, "-t", "5", "auto"],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return "не ответил"
    return "ответил" if done.returncode == 0 else "не ответил"


def connect_result(family, address):
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect(address)
        return "подключился"
    except OSError as exc:
        return f"отказ (errno {exc.errno})"
    finally:
        sock.close()


def xgw():
    sys.path.insert(0, LIB)
    from xgw import config
    from xgw.paths import Paths

    paths = Paths.from_env()
    return config.load(paths.config_file)[0], paths


if mode == "units":
    for unit in UNITS:
        pid = show(unit, "MainPID")
        found = {"Seccomp": "-", "NoNewPrivs": "-"}
        try:
            for line in open(f"/proc/{pid}/status", encoding="ascii"):
                name, _, value = line.partition(":")
                if name in found:
                    found[name] = value.strip()
        except OSError:
            pass
        report = subprocess.run(["systemd-analyze", "security", "--no-pager", unit],
                                capture_output=True, text=True).stdout
        score = re.search(r"Overall exposure level for \S+: ([0-9.]+)", report)
        score = score.group(1) if score else "?"
        print(f"{unit}: {show(unit, 'ActiveState')}, Seccomp {found['Seccomp']}, NoNewPrivs "
              f"{found['NoNewPrivs']}, /run {run_mount(pid) if pid != '0' else '-'}, оценка "
              f"{score}")
    pid = show("xgw.service", "MainPID")
    groups = []
    try:
        for line in open(f"/proc/{pid}/status", encoding="ascii"):
            if line.startswith("Groups:"):
                groups = [int(item) for item in line.split()[1:]]
    except OSError:
        pass
    try:
        xray_gid = grp.getgrnam("xray").gr_gid
        print("группа xray у процесса демона: " + ("да" if xray_gid in groups else "нет"))
    except KeyError:
        print("группы xray в системе нет")
    print(f"сокет API Xray: {perms(SOCK)}; каталог: {perms(os.path.dirname(SOCK))}")
    print("порт 10085 на 127.0.0.1 слушает: " + ("да" if port_listens(10085) else "нет"))
    texts = {path.name: path.read_text(encoding="utf-8").splitlines()
             for path in sorted(UNIT_DIR.glob("xgw*.service"))}
    pcg = [name for name, lines in texts.items()
           if any(line.startswith("ProtectControlGroups") for line in lines)]
    rop = [name for name, lines in texts.items() if "ReadOnlyPaths=/run" in lines]
    print("файлов служб XGW с ProtectControlGroups: " + (", ".join(pcg) or "0"))
    print("файлов служб XGW с ReadOnlyPaths=/run: " + (", ".join(rop) or "0"))
elif mode == "api":
    who = "root" if os.geteuid() == 0 else "пользователь"
    print(f"[{who}] порт 127.0.0.1:10085: {connect_result(socket.AF_INET, ('127.0.0.1', 10085))}"
          f"; xray api через порт: {api_answers('127.0.0.1:10085')}")
    print(f"[{who}] сокет {SOCK}: {connect_result(socket.AF_UNIX, SOCK)}; xray api через "
          f"сокет: {api_answers('unix://' + SOCK)}")
elif mode == "probe":
    unit = sys.argv[2] if len(sys.argv) > 2 else "xgw.service"
    nogroup = len(sys.argv) > 3 and sys.argv[3] == "без-группы"
    text = (UNIT_DIR / unit).read_text(encoding="utf-8")
    section = text.split("[Service]", 1)[1].split("\n[", 1)[0]
    props, writable = [], []
    for line in section.splitlines():
        key, _, value = line.strip().partition("=")
        if key == "ReadWritePaths":
            items = [item.lstrip("-") for item in value.split()]
            writable += [item for item in items if item.startswith("/run/")]
            value = " ".join(f"-{item}" for item in items)
        if key == "SupplementaryGroups" and nogroup:
            continue
        if key in SANDBOX:
            props += ["-p", f"{key}={value}"]
    probe = r"""
import os, socket, subprocess, sys
def write(path):
    try:
        with open(path, "w") as handle:
            handle.write("x")
        os.unlink(path)
        return "можно"
    except OSError as exc:
        return "нельзя (errno %d)" % exc.errno
print("запись в /run:", write("/run/.xgw-sandbox-probe"))
for folder in sys.argv[3:]:
    if os.path.isdir(folder):
        print("запись в %s:" % folder, write(folder + "/.xgw-sandbox-probe"))
sock = socket.socket(socket.AF_UNIX)
sock.settimeout(3)
try:
    sock.connect(sys.argv[1])
    print("сокет API Xray: подключился")
except OSError as exc:
    print("сокет API Xray: отказ (errno %d)" % exc.errno)
finally:
    sock.close()
try:
    done = subprocess.run([sys.argv[2], "api", "bi", "-s", "unix://" + sys.argv[1], "-t", "5",
                           "auto"], capture_output=True, text=True, timeout=20)
    print("xray api через сокет:", "ответил" if done.returncode == 0 else "не ответил")
except (OSError, subprocess.TimeoutExpired) as exc:
    print("xray api через сокет: не запустился (%s)" % type(exc).__name__)
"""
    done = subprocess.run(
        ["systemd-run", "--wait", "--pipe", "--quiet", "--collect", *props,
         "/usr/bin/python3", "-I", "-c", probe, SOCK, XRAY, *writable],
        capture_output=True, text=True, timeout=90)
    label = f"{unit}{' без группы xray' if nogroup else ''}"
    print(f"[проба {label}]")
    print(done.stdout.strip() or f"проба не запустилась: {done.stderr.strip()[:300]}")
elif mode in ("phone-lock", "phone-limits"):
    cfg, _paths = xgw()
    name, port = cfg.managed.tailscale_funnel, cfg.panel.app_port
    if not (cfg.panel.enabled and name):
        print("API приложения не включено (нет Funnel) — проверка не проводится")
        sys.exit(0)

    def hello():
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request("GET", "/api/hello", headers={"Host": name})
            return conn.getresponse().status
        except OSError as exc:
            return f"ошибка ({type(exc).__name__})"
        finally:
            conn.close()

    if mode == "phone-lock":
        codes = []
        for _ in range(12):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
            try:
                conn.request("GET", "/api/state", headers={"Host": name})
                codes.append(str(conn.getresponse().status))
            except OSError as exc:
                codes.append(type(exc).__name__)
            finally:
                conn.close()
        runs = []
        for code in codes:
            if runs and runs[-1][0] == code:
                runs[-1][1] += 1
            else:
                runs.append([code, 1])
        print("ответы на 12 запросов без подписи: "
              + ", ".join(f"{code}×{count}" for code, count in runs))
        print(f"/api/hello: {hello()}; время: {time.strftime('%H:%M:%S')}")
    else:
        socks = [socket.create_connection(("127.0.0.1", port), timeout=5) for _ in range(20)]
        time.sleep(1.0)
        closed = 0
        for sock in socks:
            sock.settimeout(0.3)
            try:
                closed += sock.recv(1) == b""
            except socket.timeout:
                pass
            except OSError:
                closed += 1
        for sock in socks:
            sock.close()
        print(f"20 соединений без запроса: сервер сразу закрыл {closed}")
        time.sleep(1.0)
        slow = socket.create_connection(("127.0.0.1", port), timeout=5)
        slow.sendall(b"GET /api/hello HTTP/1.1\r\nX-Slow: ")
        started, cut = time.monotonic(), None
        while time.monotonic() - started < 45:
            ready, _, _ = select.select([slow], [], [], 3.0)
            try:
                if ready and slow.recv(1) == b"":
                    cut = time.monotonic() - started
                    break
                slow.sendall(b"x")  # по байту раз в 3 с: таймаут одного чтения не наступает
            except OSError:
                cut = time.monotonic() - started
                break
        slow.close()
        print("запрос по байту раз в 3 с: " + (f"сервер закрыл через {cut:.0f} с" if cut
                                               else "сервер не закрыл за 45 с"))
        print(f"/api/hello после этого: {hello()}")
elif mode == "phone-nonces":
    try:
        data = json.loads(Path("/run/xgw/phone-nonces.json").read_text(encoding="utf-8"))
        print(f"чисел запросов телефона в /run/xgw: {len(data)}")
    except FileNotFoundError:
        print("файла /run/xgw/phone-nonces.json нет")
    except (OSError, ValueError) as exc:
        print(f"файл не читается: {type(exc).__name__}")
elif mode == "digest":
    cfg, paths = xgw()
    from xgw.net.capture import capture_for

    capture = capture_for(cfg, paths)
    if not hasattr(capture, "_tables_digest"):
        print("в установленном коде сверки отпечатка нет")
        sys.exit(0)
    saved = capture._state().get("tables")
    current = capture._tables_digest()
    verdict = ("не запомнен" if saved is None else "не прочитан" if current is None
               else "совпадает" if current == saved else "НЕ совпадает")
    print(f"отпечаток таблиц: {verdict}; правила на месте (loaded): {capture.loaded()}; "
          f"время: {time.strftime('%H:%M:%S')}")
elif mode == "subs":
    _cfg, paths = xgw()
    try:
        status = json.loads(paths.status_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"status.json не читается: {type(exc).__name__}")
        sys.exit(0)
    errors = status.get("sub_errors") or {}
    texts = [str((item or {}).get("error") or "") for item in errors.values()]
    print(f"подписок с ошибкой: {sum(1 for text in texts if text)}; из них «с https на http»: "
          f"{sum(1 for text in texts if 'с https на' in text)}")
elif mode == "netcheck":
    import sqlite3

    sys.path.insert(0, LIB)
    from xgw.paths import Paths

    conn = sqlite3.connect(f"{Paths.from_env().db_file.as_uri()}?mode=ro", uri=True)
    row = conn.execute("SELECT value FROM meta WHERE key = 'netcheck'").fetchone()
    last = json.loads(row[0]) if row and row[0] else {}
    checks = last.get("checks") or []
    if not checks:
        print("проверка сети: ещё не запускалась")
    else:
        levels = [check.get("level") for check in checks]
        when = time.strftime("%d.%m %H:%M:%S", time.localtime(last.get("at") or 0))
        print(f"проверка сети ({when}): OK — {levels.count('OK')}, WARN — {levels.count('WARN')}, "
              f"FAIL — {levels.count('FAIL')}")
        for check in checks:
            print(f"  {check.get('level')}  {check.get('name')}")
elif mode == "ts":
    try:
        text = subprocess.run(["tailscale", "status", "--json"], capture_output=True,
                              text=True, timeout=15).stdout
    except FileNotFoundError:
        print("Tailscale: не установлен")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Tailscale: не ответил ({type(exc).__name__})")
    else:
        try:
            print(f"Tailscale: {json.loads(text).get('BackendState') or '?'}")
        except (ValueError, AttributeError):
            print("Tailscale: ответ не JSON")
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, text in (
        ("правила загружены заново", "загружены заново"),
        ("откат на last-good", "last-good"),
        ("ошибка API Xray", "ошибка API"),
        ("failed to dial", "failed to dial"),
        ("закрепление не поставлено или не снято", "не закреплён"),
        ("API приложения: запрос отклонён", "API приложения: запрос отклонён"),
        ("отказ «с https на»", "с https на"),
        ("address already in use", "address already in use"),
        ("Read-only file system", "Read-only file system"),
        ("Permission denied", "Permission denied"),
        ("Operation not permitted", "Operation not permitted"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if text in line)}")
else:
    print("режим: units | api | probe | phone-lock | phone-limits | phone-nonces | digest | subs "
          "| netcheck | ts | log")
EOF
sha256sum v020echeck.py | cut -c1-16; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee before.txt; sudo xgw status 2>&1 | grep -c '← выбран' | sed 's/^/строк «← выбран»: /' | tee -a before.txt; sudo python3 -I v020echeck.py ts | tee -a before.txt; sudo xgw diag | grep -E 'Система:|Xray API|Порты|Итог' | tee diag-before.txt; sudo python3 -I v020echeck.py units | tee units-before.txt; sudo python3 -I v020echeck.py subs | tee subs-before.txt; sudo journalctl -u xgw --since "30 min ago" --no-pager | sudo python3 -I v020echeck.py log | tee log-before.txt
```

Ожидается:
- `67d47d73769ee3ef`;
- `Состояние: HEALTHY …`, `Перехват: включён …`, строки `Xray …` и `sing-box …`, «строк «←
  выбран»: N» (N — 1 или больше), `Tailscale: Running` — записать как есть;
- строки diag `Система`, `Xray API`, `Порты` и `Итог: …` — записать как есть;
- службы: `xgw.service … /run только чтение`; `xgw-xray`, `xgw-singbox`, `xgw-dhcp` — `/run
  запись` (как в прошлом отчёте); «группа xray у процесса демона: нет»; «сокет API Xray: нет
  (errno 2)»; «порт 10085 на 127.0.0.1 слушает: да»; «…ProtectControlGroups: 0»; «…ReadOnlyPaths=/run:
  0». Записать все строки;
- «подписок с ошибкой: …» и счётчики журнала за 30 минут — записать как есть (с ними
  сравниваются шаги 5.2 и §6).

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать (это до установки) и продолжить.

Шаг 1.3. Доступ к API Xray **без sudo** (так видит его любая программа пользователя):

```bash
cd "$HOME/xgw-020e" && python3 -I v020echeck.py api | tee api-before.txt
```

Ожидается: «[пользователь] порт 127.0.0.1:10085: подключился; xray api через порт: ответил» —
это и есть то, что закрывает доработка; «[пользователь] сокет …: отказ (errno 2) …». Записать
обе строки.

Если не так: через порт «не ответил», хотя «подключился», — записать (это наблюдение) и
продолжить.

Шаг 1.4 (при согласии на пункт 3). Пределы API приложения на старом коде. **Попроси
заказчика** (дословно):

«Не открывайте приложение XGW на телефоне полторы минуты. Скажите, когда оно закрыто.»

После ответа:

```bash
cd "$HOME/xgw-020e" && sudo python3 -I v020echeck.py phone-limits | tee limits-before.txt
```

Ожидается (около 50 секунд): «20 соединений без запроса: сервер сразу закрыл 0», «запрос по
байту раз в 3 с: сервер не закрыл за 45 с», «/api/hello после этого: 200». Записать.

Если не так: «API приложения не включено (нет Funnel) — проверка не проводится» — записать, §4
пропустить («не выполнялся: Funnel не включён»). Другие числа — записать как есть и продолжить.

Шаг 1.5 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В панели XGW нажмите кнопку «Проверить сеть» и подождите, пока под ней появится итог (до
15 секунд). Скажите, когда появится.»

После ответа:

```bash
cd "$HOME/xgw-020e" && sudo python3 -I v020echeck.py netcheck | tee netcheck-before.txt
```

Ожидается: «проверка сети (<время сейчас>): OK — …, WARN — …, FAIL — …» и список проверок.
Записать. Время не сегодняшнее — попросить нажать ещё раз и повторить команду.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout audit4 && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q '^API_SOCKET = "/run/xgw-xray/api.sock"' src/xgw/generator/builder.py && grep -q '^SupplementaryGroups=xray' packaging/xgw.service && grep -q '^RuntimeDirectory=xgw-xray' packaging/xgw-xray.service && grep -q '^ReadOnlyPaths=/run' packaging/xgw-net.service && grep -q 'def redirect_headers' src/xgw/fetch.py && grep -q '^MAX_CONNECTIONS = 16' src/xgw/watch/appapi.py && grep -q 'def tables_digest' src/xgw/net/nft.py && grep -q '^NONCES_FILE' src/xgw/phones.py && echo "правка в коде: есть"; cd "$HOME/xgw-020e"
```

Ожидается: «правка в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-020e/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-020e/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'выключены строки|перезапущен|Xray запущен' "$HOME/xgw-020e/install.txt"; cd "$HOME/xgw-020e"
```

Ожидается: «код 0», «демон xgw запущен», «Xray запущен: участников …». Строки «Xray
перезапущен…», «sing-box перезапущен: файл его службы изменился» и «…выключены строки, которые
больше ничего не значат — xray.api_port …» могут быть, а могут и не быть (Xray перезапускается
из-за смены адреса API; строки `api_port` в `config.toml` может не быть). Записать строки как
есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке и строка выбранного сервера на месте:

```bash
sleep 120; cd "$HOME/xgw-020e" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee after-install.txt; sudo xgw status 2>&1 | grep -c '← выбран' | sed 's/^/строк «← выбран»: /' | tee -a after-install.txt; sudo xgw status 2>&1 | grep -c 'api_port' | sed 's/^/предупреждений про api_port: /' | tee -a after-install.txt; sudo python3 -I v020echeck.py ts | tee -a after-install.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray отвечает, строка sing-box — как до установки;
«строк «← выбран»: N», N — 1 или больше; «предупреждений про api_port: 0»; `Tailscale: …` — как в §1.2. Записать.

Если не так: не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать `sudo
systemctl is-active xgw xgw-xray xgw-singbox xgw-dhcp | tee active.txt`, сообщить заказчику и
продолжить. «строк «← выбран»: 0» — **дефект «xgw status не видит выбранный сервер»**: записать,
продолжить.

## 3. API Xray и ограничения служб

Шаг 3.1.

```bash
cd "$HOME/xgw-020e" && sudo python3 -I v020echeck.py units | tee units-after.txt
```

Ожидается:
- четыре службы `active` (sing-box — как в §1.2), у всех **`/run только чтение`**; у
  `xgw.service` — `Seccomp 2`;
- «группа xray у процесса демона: да»;
- «сокет API Xray: srwxrwx--- xray:xray; каталог: drwxr-x--- xray:xray»;
- «порт 10085 на 127.0.0.1 слушает: нет»;
- «…ProtectControlGroups: 0»; «…ReadOnlyPaths=/run: xgw-dhcp.service, xgw-net.service,
  xgw-singbox.service, xgw-xray.service».

Записать все строки.

Если не так:
- служба была `active`, а стала не `active` — **дефект «служба не работает с новыми
  ограничениями»**: записать
  `sudo journalctl -u <служба> --since "$(cat install-time.txt)" --no-pager | grep -ciE 'denied|not permitted|read-only|address already in use' | tee unit-errors.txt`
  (только число), сообщить заказчику; сеть руками не трогать;
- у работающей службы `/run запись` — **дефект «/run открыт на запись»**;
- «группа xray у процесса демона: нет» — **дефект «демон не в группе xray»**;
- сокета нет или права другие — **дефект «сокет API Xray»**: записать строку;
- порт 10085 слушает — **дефект «API Xray по-прежнему на порту»**.

Шаг 3.2. Доступ к API **без sudo**, затем с sudo:

```bash
cd "$HOME/xgw-020e" && python3 -I v020echeck.py api | tee api-after.txt; sudo python3 -I v020echeck.py api | tee -a api-after.txt
```

Ожидается:
- «[пользователь] порт 127.0.0.1:10085: отказ (errno 111); xray api через порт: не ответил»;
- «[пользователь] сокет …: отказ (errno 13); xray api через сокет: не ответил» (13 — нет прав);
- «[root] сокет …: подключился; xray api через сокет: ответил».

Записать.

Если не так: у пользователя где-то «ответил» — **дефект «API Xray доступен без sudo»**; у root
через сокет «не ответил» — **дефект «API Xray не отвечает через сокет»**. Записать, продолжить.

Шаг 3.3. Пробы под ограничениями служб (временные службы, ничего не меняют):

```bash
cd "$HOME/xgw-020e" && for unit in xgw.service "xgw.service без-группы" xgw-core.service xgw-net.service; do sudo python3 -I v020echeck.py probe $unit; done | tee probe.txt
```

Ожидается:
- `[проба xgw.service]`: «запись в /run: нельзя (errno 30)», «запись в /run/xgw: можно»,
  «сокет API Xray: подключился», «xray api через сокет: ответил»;
- `[проба xgw.service без группы xray]`: «сокет API Xray: отказ (errno 13)», «…не ответил»
  (доступ даёт именно группа);
- `[проба xgw-core.service]`: «запись в /run: нельзя (errno 30)», «запись в /run/xgw: можно»,
  «подключился», «ответил»;
- `[проба xgw-net.service]`: «запись в /run: нельзя (errno 30)», «запись в /run/xgw: можно»
  (сокет у неё — любой результат: службе сети API не нужен).

Записать.

Если не так: «запись в /run: можно» — **дефект «/run открыт на запись»**; у `xgw.service` или
`xgw-core.service` «отказ» или «не ответил» — **дефект «служба не достаёт до API Xray»**; у
пробы без группы «подключился» — **дефект «сокет открыт не только группе»**; «проба не
запустилась» — записать её текст. Продолжить.

Шаг 3.4. diag:

```bash
cd "$HOME/xgw-020e" && sudo xgw diag | grep -E 'Система:|Xray API|Порты|Итог' | tee diag-after.txt; xgw diag 2>&1 | grep -E 'Xray API' | tee diag-nosudo.txt
```

Ожидается: с sudo — `OK … Xray API: API и метрики отвечают; …`, `OK … Порты …`, `Система` — OK,
`Итог: …, FAIL — 0`. Без sudo — строка `WARN … Xray API: метрики отвечают; API проверяется
только с sudo` (или строки нет вовсе — тогда записать «без sudo diag строку не показал»).
Записать.

Если не так: с sudo `Xray API` — FAIL — **дефект «diag не видит API Xray»**: записать строку.

Шаг 3.5 (при согласии на пункт 2). Ручной выбор сервера — панель (служба демона) через сокет.
**Попроси заказчика** (дословно):

«В панели XGW нажмите «Выбрать» у любого сервера. Появилась ли у него метка «выбран вручную»,
а сообщения об ошибке нет?»

После ответа:

```bash
cd "$HOME/xgw-020e" && sudo xgw status 2>&1 | grep -c '← выбран' | sed 's/^/строк «← выбран»: /' | tee pin.txt
```

Через минуту **попроси заказчика** (дословно):

«Нажмите «Автовыбор». Метка «выбран вручную» пропала, сообщения об ошибке нет?»

Ожидается: «да» на оба вопроса; «строк «← выбран»: 1». Записать ответы дословно.

Если не так: сообщение об ошибке (например, со словами «failed to dial» или «xray api») —
**дефект «панель не достаёт до API Xray»**: записать текст сообщения без адресов, продолжить.

## 4. Вход телефонов (при согласии на пункт 3)

Шаг 4.1. **Попроси заказчика** (дословно):

«Не открывайте приложение XGW на телефоне, пока я не попрошу (около минуты). Скажите, когда
оно закрыто.»

После ответа (запросы без подписи — как от чужого из интернета):

```bash
cd "$HOME/xgw-020e" && sudo python3 -I v020echeck.py phone-lock | tee lock.txt
```

Ожидается (около 10 секунд): «ответы на 12 запросов без подписи: 403×10, 429×2» и
«/api/hello: 200; время: …». Сразу после этого **попроси заказчика** (дословно):

«Откройте приложение XGW на телефоне. Показывает ли оно состояние шлюза (серверы, состояние), а
не ошибку? Ответьте в течение минуты.»

Затем:

```bash
cd "$HOME/xgw-020e" && sudo python3 -I v020echeck.py phone-nonces | tee -a lock.txt
```

Ожидается: заказчик — «да, показывает»; «чисел запросов телефона в /run/xgw: N», N — 1 или
больше. Записать ответ дословно и строки.

Если не так: приложение показывает ошибку — **дефект «чужие неудачи закрыли вход телефону»**:
записать ответ, продолжить. Ответы не «403×10, 429×2» — записать как есть (наблюдение). Файла
нет — **дефект «числа запросов не сохраняются»**.

Шаг 4.2. **Попроси заказчика** (дословно):

«Закройте приложение XGW на телефоне и не открывайте полторы минуты. Скажите, когда закрыто.»

После ответа:

```bash
cd "$HOME/xgw-020e" && sudo python3 -I v020echeck.py phone-limits | tee limits-after.txt
```

Ожидается (около 25 секунд): «20 соединений без запроса: сервер сразу закрыл 4», «запрос по
байту раз в 3 с: сервер закрыл через N с», N — от 18 до 25, «/api/hello после этого: 200».
Затем **попроси заказчика** (дословно): «Откройте приложение XGW снова — работает?»

Записать строки и ответ.

Если не так: «сразу закрыл 0» — **дефект «нет предела соединений»**; «не закрыл за 45 с» —
**дефект «медленный запрос не обрывается»**; `/api/hello` не 200 или приложение не работает —
**дефект «API приложения не отвечает после проверки»**: сообщить заказчику, продолжить.

## 5. Правила и подписки

Шаг 5.1.

```bash
cd "$HOME/xgw-020e" && sudo python3 -I v020echeck.py digest | tee digest.txt
```

Ожидается: «отпечаток таблиц: совпадает; правила на месте (loaded): True; время: …». Записать.

Если не так: «не запомнен» — **дефект «отпечаток не запомнен после установки»**; «НЕ
совпадает» или `False` — повторить команду через минуту; снова так — **дефект «отпечаток
таблиц меняется сам»** (тогда в §6 смотреть «правила загружены заново»). Продолжить.

Шаг 5.2 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В панели XGW нажмите «Обновить» над списком подписок. Скажите, когда нажали.»

Через 60 секунд после ответа:

```bash
sleep 60; cd "$HOME/xgw-020e" && sudo python3 -I v020echeck.py subs | tee subs-after.txt
```

Ожидается: «подписок с ошибкой: …» — не больше, чем в `subs-before.txt`; «из них «с https на
http»: 0». Записать.

Если не так: ошибок стало больше — записать оба числа и
`sudo xgw status 2>&1 | grep -ciE 'перенаправ|redirect' | tee subs-redirect.txt` (только число),
сообщить заказчику — **дефект «подписка не обновляется после доработки»**.

Шаг 5.3. Не раньше чем через 5 минут после шага 5.1 (счётчики трафика за это время выросли):

```bash
cd "$HOME/xgw-020e" && cat digest.txt; sudo python3 -I v020echeck.py digest | tee -a digest.txt
```

Ожидается: снова «отпечаток таблиц: совпадает; … True», время — на 5 минут и больше позже, чем
в первой строке. Записать обе строки. Если не так — как в шаге 5.1.

Шаг 5.4 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В панели XGW снова нажмите «Проверить сеть» и подождите итог. Скажите, когда появится.»

После ответа:

```bash
cd "$HOME/xgw-020e" && sudo python3 -I v020echeck.py netcheck | tee netcheck-after.txt
```

Ожидается: время — сейчас; те же проверки и уровни, что в шаге 1.5; FAIL — не больше. Если не
так: проверка, бывшая OK или WARN, стала FAIL — **дефект «проверка сети после доработки»**:
записать её название и уровень.

Шаг 5.5 (при согласии на пункт 3). **Попроси заказчика** (дословно):

«Откройте любой сайт на этом компьютере и любой сайт на телефоне. Открываются?»

Ожидается: «да». Нет — записать ответ дословно и
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt`,
сообщить заказчику.

## 6. Итог

```bash
cd "$HOME/xgw-020e" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020echeck.py log | tee final.txt; sudo journalctl -u xgw-xray --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020echeck.py log | grep -E '^строк|address already in use' | sed 's/^/xgw-xray: /' | tee -a final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee -a final.txt
```

Ожидается:
- «правила загружены заново: 0» или 1; «откат на last-good: 0»; «ошибка API Xray: 0»;
  «failed to dial: 0»; «закрепление не поставлено или не снято: 0»;
- «API приложения: запрос отклонён: 10» (это запросы шага 4.1; §4 не выполнялся — 0);
- «отказ «с https на»: 0»; «Traceback: 0»; «Read-only file system», «Permission denied»,
  «Operation not permitted» — не больше, чем в `log-before.txt`;
- `xgw-xray: … address already in use: 0`;
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки.

Если не так: «правила загружены заново» больше 1 — **дефект «правила загружаются по кругу»**
(вместе с шагами 5.1 и 5.3); Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -30 | tee traceback.txt`
(только строки с файлами и ошибкой, адреса — убрать); остальные счётчики выше ожидаемого —
**дефект** с названием счётчика и числом. Сообщить заказчику.

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit4-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`audit4`), коммит «Отчёт: XGW 0.2.0, защита по четвёртому аудиту», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, защита по четвёртому аудиту

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
v020echeck.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, diag, службы (/run, группа, сокет, порт 10085), подписки, журнал |
| 1.3 API без sudo до | — | порт, сокет |
| 1.4 пределы API приложения до | — / не выполнялся | закрыто сразу, медленный запрос |
| 1.5 проверка сети до | — / не выполнялся | OK / WARN / FAIL |
| 2.2 установка | … | код, строки установки |
| 2.3 после установки | … | HEALTHY, «← выбран», api_port, Tailscale |
| 3.1 службы | … | /run, Seccomp, группа xray, сокет и каталог, порт 10085, файлы служб |
| 3.2 API без sudo и с sudo | … | порт, сокет |
| 3.3 пробы служб | … | xgw, без группы, xgw-core, xgw-net |
| 3.4 diag | … | Xray API, Порты, Итог; без sudo |
| 3.5 ручной выбор | … / не выполнялся | ответы заказчика, «← выбран» |
| 4.1 чужие неудачи и телефон | … / не выполнялся | ответы, приложение, числа запросов |
| 4.2 пределы API приложения | … / не выполнялся | закрыто сразу, через сколько секунд, приложение |
| 5.1 и 5.3 отпечаток таблиц | … | совпадает, loaded, время |
| 5.2 обновление подписок | … / не выполнялся | ошибки до → после, «с https на http» |
| 5.4 проверка сети после | … / не выполнялся | OK / WARN / FAIL до → после |
| 5.5 сайты | … / не выполнялся | ответ заказчика |
| 6 итог | … | счётчики журнала, xgw-xray, HEALTHY |

## Выводы шагов
<файлы $HOME/xgw-020e/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
