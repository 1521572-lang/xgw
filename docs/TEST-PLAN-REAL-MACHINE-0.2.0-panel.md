# Проверка XGW 0.2.0: нагрузка открытой вкладки и ограничения служб

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-020d/…`). Файл помощника создавай только командой шага 1.2, выполненной в терминале:
если создать его по-другому (например, записать текст в файл инструментом), сумма не совпадёт.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `panel-cpu`, версия 0.2.0. Сейчас на машине стоит 0.2.0 с
коммита c44759a (то же, что теперь в `main`); проверка доработок по аудиту пройдена, отчёт
`docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit-2026-10-26.md`. Телефон — S25 Ultra в домашней сети.
Команды — в терминале сеанса заказчика (`sudo` от его имени: проба уведомления берёт
пользователя из `sudo`).

Что изменено (ASSUMPTIONS пп. 251–252):
1. **Карточка «Tailscale» в панели** реже спрашивает программу `tailscale`. В прошлом отчёте
   открытая вкладка XGW стоила около 4 % ядра, из них ~2,5 % — запущенные программы: пока вкладка
   открыта, карточка раз в 10 секунд запускала `tailscale` четыре раза (одну и ту же команду —
   дважды). Теперь — три запуска раз в минуту, пока Tailscale работает и ничего не идёт; раз в
   10 секунд — только пока идут вход в Tailscale, включение Serve или Funnel. Кнопки карточки,
   как и раньше, обновляют её сразу.
2. **`xgw diag`** считает Ubuntu 24.04 проверенной системой, как 26.04: предупреждение
   «XGW проверялся только на Ubuntu 26.04» больше не появляется.
3. **Служба демона `xgw.service`** получила ограничения systemd, как у Xray и sing-box: модули
   и журнал ядра, часы, имя машины, свои пространства имён, realtime, setuid-файлы ей закрыты,
   домашние каталоги — только чтение, сокеты — IP, netlink, UNIX и AF_PACKET (запись трафика).
4. **Строки `ProtectControlGroups` больше нет ни у одной службы XGW**: на systemd 259 (Ubuntu
   26.04) вместе с `ProtectSystem=strict` она открывает `/run` на запись. Как на systemd 255
   (эта машина) — покажет шаг 1.2: там стоят ещё прежние файлы служб.
5. Правило маршрутизации по метке добавляется после маршрутов своей таблицы; демон не
   запускает Xray сам, пока systemd ждёт его автоперезапуска; правила nftables загружаются одной
   транзакцией без отдельной проверки `nft -c`.

Здесь, у разработчика (Ubuntu 26.04, systemd 259), проверены юнит-тесты, демон стенда под
новыми ограничениями (те же проверки, что без них: восстановление правил, DHCP, чужой flush,
пропажа WAN), проба ограничений (запись трафика, netlink, nft, TUN, форвардинг, runuser,
сокет шины) и помощник этого ТЗ. На Ubuntu 24.04 — только здесь. Шлюз заказчика — эта программа.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list` и `nft -t list`), `ip`, `iptables`, `tc`, `sysctl -w`,
  `systemd-run`; команды `tailscale`. Исключения — только то, что запускает помощник: `tailscale
  status --json` (печатает только состояние) и в шаге 4.2 временная проба `systemd-run` (только
  читает, пробует записать файл в `/run` и `/root` и показывает уведомление).
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/etc/systemd`, код XGW. Печатать `config.toml` (`cat`, `less`, `grep` по нему) — в нём ключи
  подписок. Серверы, переключатели и кнопки в панели (и в карточке «Tailscale») меняет и
  нажимает только заказчик. Коммитить что-либо, кроме отчёта (§7).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP и домены серверов
  VPN, строки журнала. Можно: адреса устройств в домашней сети (`192.168.…`), названия и страны
  серверов, имена программ и проверок, счётчики, времена, проценты.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю, сколько стоит открытая вкладка XGW, и новые ограничения служб. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд.
(2) Вкладка XGW в браузере: по моей просьбе три раза по 2 минуты — вкладка открыта (сейчас, на
старом коде), все вкладки XGW закрыты, вкладка снова открыта (на новом коде). Все 6 минут
приложение XGW на телефоне не открывайте. Потом посмотрите на карточку «Tailscale» в панели
(ничего в ней не нажимая) и откроете любой сайт на этом компьютере и на телефоне.
(3) В панели XGW нажмёте кнопку «Проверить сеть» два раза — до установки и после; и на экране
появится проверочное уведомление XGW — скажете, видно ли его.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — шаг 1.3 и §5 пропустить; против 3 — шаги 1.4, 4.2 и
4.3. В отчёте у пропущенного — «не выполнялся».

Шаг 1.2. Папка, помощник проверки (только читает) и состояние до установки:

```bash
mkdir -p "$HOME/xgw-020d" && chmod 700 "$HOME/xgw-020d" && cd "$HOME/xgw-020d" && cat > v020dcheck.py <<'EOF'
"""XGW 0.2.0, вкладка панели и ограничения служб: помощник. Только читает: /proc и cgroup
служб XGW (процессор, какие программы запускает демон — только имена, /run в их mountinfo),
systemd-analyze security, файлы служб, состояние Tailscale (только BackendState), итог
«Проверить сеть» (только названия и уровни), журнал со стандартного ввода (только счётчики).
Режим notify запускает пробу под песочницей xgw.service: сокеты, `nft list tables`, попытки
записи в /run и /root и проверочное уведомление на рабочий стол. Режимы: cpu, ts, units,
notify, netcheck, log."""
import json
import os
import pwd
import re
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
UNIT_DIR = Path("/etc/systemd/system")
SANDBOX = ("ProtectSystem", "ReadWritePaths", "PrivateTmp", "NoNewPrivileges",
           "CapabilityBoundingSet", "ProtectHome", "ProtectKernelModules", "ProtectKernelLogs",
           "ProtectControlGroups", "ProtectClock", "ProtectHostname", "RestrictNamespaces",
           "RestrictRealtime", "RestrictSUIDSGID", "LockPersonality", "SystemCallArchitectures",
           "RestrictAddressFamilies")


def show(unit, prop):
    return subprocess.run(["systemctl", "show", "-p", prop, "--value", unit],
                          capture_output=True, text=True).stdout.strip()


def comm(pid):
    try:
        return open(f"/proc/{pid}/comm", encoding="utf-8").read().strip()
    except OSError:
        return ""


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


if mode == "cpu":
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    unit = sys.argv[3] if len(sys.argv) > 3 else "xgw.service"
    pid = show(unit, "MainPID")
    group = f"/sys/fs/cgroup{show(unit, 'ControlGroup')}"
    tick = os.sysconf("SC_CLK_TCK")
    own = comm(pid)

    def fields():
        return open(f"/proc/{pid}/stat", encoding="ascii").read().rsplit(")", 1)[1].split()

    def ticks():
        values = fields()
        return (int(values[11]) + int(values[12])) / tick

    def usage():
        try:
            for line in open(f"{group}/cpu.stat", encoding="ascii"):
                name, _, value = line.partition(" ")
                if name == "usage_usec":
                    return int(value) / 1e6
        except OSError:
            return None
        return None

    uptime = float(open("/proc/uptime", encoding="ascii").read().split()[0])
    print(f"демон xgw работает: {int((uptime - int(fields()[19]) / tick) // 60)} мин")
    seen = {}
    start = time.monotonic()
    first, first_all = ticks(), usage()
    while time.monotonic() - start < seconds:
        try:
            current = open(f"{group}/cgroup.procs", encoding="ascii").read().split()
        except OSError:
            current = []
        for child in current:
            name = comm(child)
            if child != pid and name:
                seen[child] = name  # последнее имя — уже после exec
        time.sleep(0.005)
    used, used_all = ticks() - first, usage()
    spent_time = time.monotonic() - start
    print(f"процессор демона xgw (сам процесс): {used:.1f} с за {spent_time:.0f} с "
          f"({100 * used / spent_time:.1f} %)")
    if first_all is None or used_all is None:
        print(f"служба xgw целиком: нет {group}/cpu.stat")
    else:
        spent = used_all - first_all
        print(f"служба xgw целиком (с запущенными программами): {spent:.1f} с за "
              f"{spent_time:.0f} с ({100 * spent / spent_time:.1f} %)")
    counts = {"tailscale": 0}
    for name in seen.values():
        if name != own:  # пойман до exec и сразу вышел
            counts[name] = counts.get(name, 0) + 1
    print("запусков tailscale: " + str(counts.pop("tailscale")))
    others = ", ".join(f"{name} {count}" for name, count in
                       sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    print("других запусков: " + (others or "нет"))
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
elif mode == "units":
    for unit in sys.argv[2:] or UNITS:
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
        print(f"{unit}: {show(unit, 'ActiveState')}, Seccomp {found['Seccomp']}, NoNewPrivs "
              f"{found['NoNewPrivs']}, /run {run_mount(pid) if pid != '0' else '-'}, оценка "
              f"{score.group(1) if score else '?'}")
    marked = [path.name for path in sorted(UNIT_DIR.glob("xgw*.service"))
              if any(line.startswith("ProtectControlGroups")
                     for line in path.read_text(encoding="utf-8").splitlines())]
    print("файлов служб XGW с ProtectControlGroups: " + (", ".join(marked) or "0"))
elif mode == "notify":
    unit_file = Path(sys.argv[2]) if len(sys.argv) > 2 else UNIT_DIR / "xgw.service"
    user = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("SUDO_USER", "")
    if not user or user == "root":
        sys.exit("нет пользователя сеанса: запустите через sudo из сеанса заказчика")
    uid = pwd.getpwnam(user).pw_uid
    section = unit_file.read_text(encoding="utf-8").split("[Service]", 1)[1].split("\n[", 1)[0]
    props = []
    for line in section.splitlines():
        key, _, value = line.strip().partition("=")
        if key == "ReadWritePaths":
            value = " ".join(f"-{item}" for item in value.split())
        if key in SANDBOX:
            props += ["-p", f"{key}={value}"]
    probe = r"""
import os, socket, subprocess, sys
def attempt(label, action, good, bad):
    try:
        action()
        print(f"{label}: {good}")
    except OSError as exc:
        print(f"{label}: {bad} (errno {exc.errno})")
attempt("сокет AF_PACKET", lambda: socket.socket(socket.AF_PACKET, socket.SOCK_RAW).close(),
        "можно", "НЕЛЬЗЯ")
attempt("сокет netlink", lambda: socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 0).close(),
        "можно", "НЕЛЬЗЯ")
def nft():
    done = subprocess.run(["nft", "list", "tables"], capture_output=True, text=True, timeout=30)
    if done.returncode:
        raise OSError(done.returncode, "nft")
attempt("nft list tables", nft, "можно", "НЕЛЬЗЯ")
def write(path):
    def action():
        with open(path, "w") as handle:
            handle.write("x")
        os.unlink(path)
    return action
attempt("запись в /run", write("/run/.xgw-sandbox-probe"), "МОЖНО", "нельзя")
attempt("запись в /root", write("/root/.xgw-sandbox-probe"), "МОЖНО", "нельзя")
user, uid = sys.argv[1], sys.argv[2]
done = subprocess.run(
    ["runuser", "-u", user, "--", "env",
     f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
     "notify-send", "--app-name=XGW", "--icon=network-vpn", "XGW: проверка песочницы",
     "Это проверочное уведомление, ничего делать не нужно"],
    capture_output=True, text=True, timeout=15)
first = (done.stderr.strip().splitlines() or [""])[0][:120]
print("уведомление: " + ("отправлено" if done.returncode == 0 else
                         f"ОШИБКА {done.returncode} {first}"))
"""
    done = subprocess.run(
        ["systemd-run", "--wait", "--pipe", "--quiet", "--collect", *props,
         "/usr/bin/python3", "-I", "-c", probe, user, str(uid)],
        capture_output=True, text=True, timeout=90)
    print(done.stdout.strip() or f"проба не запустилась: {done.stderr.strip()[:300]}")
elif mode == "netcheck":
    import sqlite3

    sys.path.insert(0, "/opt/xgw/lib")
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
elif mode == "log":
    lines = sys.stdin.read().splitlines()

    def count(text):
        return sum(1 for line in lines if text in line)

    print(f"строк журнала: {len(lines)}")
    print(f"правила загружены заново: {count('загружены заново')}")
    print(f"уведомление не доставлено: {count('не доставлено')}")
    print(f"Read-only file system: {count('Read-only file system')}")
    print(f"Permission denied: {count('Permission denied')}")
    print(f"Operation not permitted: {count('Operation not permitted')}")
    print(f"Address family not supported: {count('Address family not supported')}")
    print(f"Traceback: {count('Traceback')}")
else:
    print("режим: cpu | ts | units | notify | netcheck | log")
EOF
sha256sum v020dcheck.py | cut -c1-16; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^sing-box' | tee before.txt; sudo python3 -I v020dcheck.py ts | tee -a before.txt; sudo xgw diag | grep -E 'Система:|Итог' | tee diag-before.txt; sudo python3 -I v020dcheck.py units | tee units-before.txt; sudo journalctl -u xgw --since "30 min ago" --no-pager | sudo python3 -I v020dcheck.py log | tee log-before.txt
```

Ожидается:
- `c23f09c411f5d239`;
- `Состояние: HEALTHY …`, `Перехват: включён …`, строка `sing-box …` (записать как есть);
- `Tailscale: Running`;
- строка `WARN … Система: Ubuntu 24.04.5 LTS, Python 3.12 — XGW проверялся только на Ubuntu
  26.04` и строка `Итог: OK — …, WARN — …, FAIL — …`. Записать обе;
- четыре строки служб `xgw.service`, `xgw-xray.service`, `xgw-singbox.service`,
  `xgw-dhcp.service` — состояние, `Seccomp`, `NoNewPrivs`, `/run …`, `оценка`; строка «файлов
  служб XGW с ProtectControlGroups: …» (сейчас — `xgw-dhcp.service, xgw-net.service,
  xgw-singbox.service, xgw-xray.service`). Записать всё как есть. Что стоит у `/run` у Xray,
  sing-box и DHCP (`только чтение` или `запись`) — ответ на вопрос, ведёт ли себя systemd 255
  так же, как 259: это наблюдение, не дефект;
- счётчики журнала за последние 30 минут (записать как есть — с ними сравнивается §6).

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать (это до установки) и продолжить. Вместо
`Running` другое состояние — записать и продолжить (в §5 тогда другой порог).

Шаг 1.3 (при согласии на пункт 2). Старый код, вкладка открыта. **Попроси заказчика**
(дословно):

«Откройте XGW значком в трее и оставьте вкладку на экране 2 минуты: окно не сворачивайте и на
другую вкладку не переключайтесь. Приложение XGW на телефоне не открывайте. Скажите, когда
открыли.»

После ответа:

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py cpu 120 | tee cpu-old-open.txt
```

Ожидается: «демон xgw работает: M мин», «процессор демона xgw (сам процесс): … (Y1 %)», «служба
xgw целиком …: … (Y2 %)», «запусков tailscale: T» — T не меньше 25 (старый код: 3–4 запуска
примерно раз в 12 секунд, за 2 минуты — 30–44), «других запусков: …». Записать M, Y1, Y2, T и
строку других запусков как есть (короткие программы вроде `ip` помощник видит не все — это
нормально).

Если не так: T меньше 25 — спросить заказчика, была ли вкладка XGW на экране все 2 минуты;
записать ответ и T и продолжить.

Шаг 1.4 (при согласии на пункт 3). Проверка сети до установки. **Попроси заказчика**
(дословно):

«В панели XGW нажмите кнопку «Проверить сеть» и подождите, пока под ней появится итог (до
15 секунд). Скажите, когда появится.»

После ответа:

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py netcheck | tee netcheck-before.txt
```

Ожидается: «проверка сети (<время сейчас>): OK — …, WARN — …, FAIL — …» и список проверок с
уровнями. Записать как есть. Время не сегодняшнее или «ещё не запускалась» — попросить
заказчика нажать кнопку ещё раз и повторить команду.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout panel-cpu && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def serve_live' src/xgw/tailscale.py && grep -q '^TS_TTL = 60.0' src/xgw/watch/panel.py && grep -q '^TESTED_UBUNTU' src/xgw/diag.py && grep -q '^RestrictAddressFamilies=.*AF_PACKET' packaging/xgw.service && ! grep -q '^ProtectControlGroups' packaging/*.service && grep -q 'def restart_pending' src/xgw/xraycore/service.py && echo "правка в коде: есть"; cd "$HOME/xgw-020d"
```

Ожидается: «правка в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-020d/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-020d/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'выключены строки|перезапущен' "$HOME/xgw-020d/install.txt"; cd "$HOME/xgw-020d"
```

Ожидается: «код 0», «демон xgw запущен», «Xray перезапущен: файл его службы изменился» и
«sing-box перезапущен: файл его службы изменился» (строки про sing-box нет, если он не работал
до установки). Строки «выключены строки» быть не должно. Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке:

```bash
sleep 120; cd "$HOME/xgw-020d" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee after-install.txt; sudo python3 -I v020dcheck.py ts | tee -a after-install.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray отвечает, строка sing-box и `Tailscale: …` — как
до установки (§1.2). Записать.

Если не так: не `HEALTHY` — подождать 2 минуты, повторить; снова нет — записать `sudo xgw
status` целиком (без адресов серверов) и `sudo systemctl is-active xgw xgw-xray xgw-singbox
xgw-dhcp | tee active.txt`, сообщить заказчику и продолжить.

## 3. diag

```bash
cd "$HOME/xgw-020d" && sudo xgw diag | grep -E 'Система:|Итог' | tee diag-after.txt
```

Ожидается: строка `OK … Система: Ubuntu 24.04.5 LTS, Python 3.12` — без «проверялся только»;
`Итог: …, FAIL — 0`, WARN на 1 меньше, чем в §1.2 (если остальные проверки не изменились).
Записать обе строки.

Если не так: строка `Система` — по-прежнему WARN — **дефект «diag предупреждает об Ubuntu
24.04»**: записать строку. FAIL больше 0 — записать `sudo xgw diag | grep FAIL | tee
diag-fail.txt` (без адресов серверов и подписок).

## 4. Службы и их ограничения

Шаг 4.1.

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py units | tee units-after.txt
```

Ожидается:
- `xgw.service: active, Seccomp 2, NoNewPrivs 1, /run только чтение`, оценка меньше, чем в
  §1.2;
- `xgw-xray.service`, `xgw-singbox.service`, `xgw-dhcp.service` — `active` (sing-box — как в
  §1.2), `/run только чтение`;
- «файлов служб XGW с ProtectControlGroups: 0».

Записать все строки.

Если не так:
- служба была `active` (§1.2), а стала не `active` — **дефект «служба не работает с новыми
  ограничениями»**: записать
  `sudo journalctl -u <служба> --since "$(cat install-time.txt)" --no-pager | grep -ciE 'denied|not permitted|read-only|not supported' | tee unit-errors.txt`
  (это только число строк), сообщить заказчику; сеть руками не трогать;
- у работающей службы `/run запись` — **дефект «/run открыт на запись»**: записать строку;
- у `xgw.service` `Seccomp 0` — **дефект «ограничения демона не применились»**: записать строку;
- файлов с `ProtectControlGroups` больше 0 — **дефект «старый файл службы»**: записать строку.

Шаг 4.2 (при согласии на пункт 3). Проба под ограничениями демона: те же настройки, что в
установленном `xgw.service`, и проверочное уведомление.

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py notify | tee notify.txt
```

Сразу после команды **спроси заказчика** (дословно):

«На экране появилось уведомление «XGW: проверка песочницы»?»

Ожидается: «сокет AF_PACKET: можно», «сокет netlink: можно», «nft list tables: можно», «запись
в /run: нельзя …», «запись в /root: нельзя …», «уведомление: отправлено»; заказчик — «да».
Записать вывод и ответ.

Если не так: «НЕЛЬЗЯ» у сокета или nft, «МОЖНО» у записи, «уведомление: ОШИБКА …» или
заказчик уведомления не видел — **дефект «ограничения демона мешают ему»**: записать вывод и
ответ, продолжить. «нет пользователя сеанса» — команда запущена не из сеанса заказчика: открыть
терминал в его сеансе и повторить.

Шаг 4.3 (при согласии на пункт 3). Проверка сети после установки. **Попроси заказчика**
(дословно):

«В панели XGW снова нажмите «Проверить сеть» и подождите итог. Скажите, когда появится.»

После ответа:

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py netcheck | tee netcheck-after.txt
```

Ожидается: время — сейчас; те же проверки и уровни, что в §1.4; FAIL — не больше, чем там.

Если не так: проверка, которая в §1.4 была OK или WARN, стала FAIL — **дефект «проверка сети
под новыми ограничениями»**: записать её название и уровень, продолжить.

## 5. Вкладка закрыта и открыта (при согласии на пункт 2)

Шаг 5.1. **Попроси заказчика** (дословно):

«Закройте все вкладки XGW в браузере (сам браузер можно не закрывать) и 2 минуты не открывайте;
приложение XGW на телефоне тоже не открывайте. Скажите, когда закрыли.»

После ответа:

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py cpu 120 | tee cpu-closed.txt
```

Ожидается: «запусков tailscale: 0». Записать M, Y1, Y2, T и строку других запусков.

Если не так: T больше 0 — спросить заказчика, не было ли открыто приложение XGW на телефоне или
вкладка XGW где-то ещё; записать ответ и T и продолжить (не дефект).

Шаг 5.2. **Попроси заказчика** (дословно):

«Откройте XGW значком в трее и оставьте вкладку на экране 2 минуты: окно не сворачивайте и на
другую вкладку не переключайтесь. Приложение XGW на телефоне не открывайте. Скажите, когда
открыли.»

После ответа:

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py cpu 120 | tee cpu-open.txt
```

Ожидается: «запусков tailscale: T», где T не больше 9 (новый код: 3 запуска примерно раз в
минуту). Если в §2.3 было не `Tailscale: Running` — T не больше 40 (тогда карточка, как и раньше,
обновляется раз в 10 секунд). Записать M, Y1, Y2, T и строку других запусков; Y2 сравнить с §1.3.

Если не так: при `Tailscale: Running` T больше 12 — **дефект «карточка Tailscale по-прежнему
часто запускает tailscale»**: записать T и строку других запусков, сообщить заказчику и
продолжить. Y1 и Y2 — наблюдения, дефектов по ним нет (демон после установки моложе, чем в
§1.3).

Шаг 5.3. Не закрывая вкладку. **Попроси заказчика** (дословно):

«В панели XGW, в карточке «Tailscale» (ничего в ней не нажимайте): написано «Шлюз в tailnet:
к нему можно зайти с телефона и ноутбука…»? Список устройств и переключатели — такие же, как
обычно? И откройте любой сайт на этом компьютере и любой сайт на телефоне — открываются?»

Ожидается: «да» на все вопросы. Нет — записать ответ дословно, выполнить
`sudo python3 -I v020dcheck.py ts | tee card.txt` и сообщить заказчику: карточка не такая, как
обычно, — **дефект «карточка Tailscale изменилась»**; не открываются сайты — выполнить
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt`.

## 6. Итог

```bash
cd "$HOME/xgw-020d" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020dcheck.py log | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^sing-box' | tee -a final.txt
```

Ожидается: «Traceback: 0»; «правила загружены заново» — 0 или 1; счётчики «уведомление не
доставлено», «Read-only file system», «Permission denied», «Operation not permitted», «Address
family not supported» — не больше, чем в `log-before.txt` (§1.2); `HEALTHY`, перехват включён,
sing-box — как до установки.

Если не так: Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -30 | tee traceback.txt`
(только строки с файлами и ошибкой; адреса серверов и подписок, если видны, — убрать). Счётчик, который в
`log-before.txt` был 0, стал больше 0 — **дефект «ограничения мешают демону»**: записать его
название и число, сообщить заказчику.

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-panel-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`panel-cpu`), коммит «Отчёт: XGW 0.2.0, нагрузка вкладки и ограничения служб», `git push`.
Шаблон:

```markdown
# Отчёт: XGW 0.2.0, нагрузка вкладки и ограничения служб

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
v020dcheck.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, Tailscale, «Система» и итог diag, службы (/run, Seccomp, оценки) |
| 1.3 старый код, вкладка открыта | — / не выполнялся | M, Y1, Y2, T |
| 1.4 проверка сети до | — / не выполнялся | OK / WARN / FAIL |
| 2.2 установка | … | код, строки «перезапущен» |
| 2.3 после установки | … | HEALTHY, sing-box, Tailscale |
| 3 diag | … | строка «Система», итог до → после |
| 4.1 службы | … | active, Seccomp, /run, оценки до → после, файлы с ProtectControlGroups |
| 4.2 проба и уведомление | … / не выполнялся | вывод пробы, ответ заказчика |
| 4.3 проверка сети после | … / не выполнялся | OK / WARN / FAIL до → после |
| 5.1 вкладка закрыта | … / не выполнялся | M, Y1, Y2, T |
| 5.2 вкладка открыта | … / не выполнялся | M, Y1, Y2, T (сравнение с 1.3) |
| 5.3 карточка и сайты | … / не выполнялся | ответы заказчика |
| 6 итог | … | счётчики журнала до → после, Traceback, HEALTHY |

## Выводы шагов
<файлы $HOME/xgw-020d/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
