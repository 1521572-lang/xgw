# Проверка XGW 0.2.0: волна 3 — барьер и отдельный пользователь sing-box

## Как выполнять

Исполнитель — Flash в терминале сеанса заказчика; `sudo` — от его имени. Прочитать весь план
до первого действия. Выполнять по одному шагу: **Действие → Команда → Ожидается →
Если не так**, сохранять вывод в `$HOME/xgw-w3`. Около 45 минут. Подписку, ручной выбор сервера
и FreePool не менять. Не выполнять дополнительные сетевые опыты. При неоднозначности
остановить зависимые шаги и сообщить заказчику; предположения отделять от фактов.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS/systemd 255, KDE X11; клон `~/zcod/xgw`.
Принятые ядра Xray 26.10.31 и sing-box 1.14.4 должны сохраниться. Код — ветка `freepool`, версия 0.2.0.
Commit реализации: **`fd65fc4b18fa8ea658737e9612544bdf63536b4c`**. ТЗ находится в том же репозитории, как и предыдущие планы;
локальный ZIP/patch и ручная передача manifest не требуются. Документы могут быть новее
commit реализации: перед установкой проверяется неизменность кода `src/`, `packaging/`,
`config.example.toml`, `pyproject.toml`. Текст ТЗ и наличие функции не подтверждают результаты
реального прогона. Все реальные результаты первоначально `NOT_RUN`.

Проверяем только PR-N4/N5: независимый `inet xgw_guard` при повреждении перехвата и постоянный
sing-box под `xgw-singbox` с пустыми capabilities, отдельными конфигом/группой. Новая FSM,
all-core netns, capless Xray, TUN ownership, G1, DAE и временные FreePool-процессы вне проверки.
Ядро должно принимать guard; отказ его загрузки должен прерывать всю транзакцию, сохраняя
предыдущий набор. Устаревший текст о продолжении без guard не является допустимым fallback.
Полное `flush ruleset` снимает и guard: от него эта волна защиты не обещает.

**Граница доказательства.** RST и рост локального reject-счётчика — только
`LOCAL_GUARD_EVIDENCE`. Это не доказательство отсутствия пакета на WAN. Общий счётчик может
включать чужой трафик; демон может восстановить правила до пробы и обнулить счётчики при
перезагрузке. Без внешнего WAN sentinel/фактической записи пакетов E4 на этой машине остаётся
`NOT_RUN`, даже если все локальные проверки успешны. Здесь выполняется только IPv4 TCP с
самого шлюза; LAN, Docker, tailnet, IPv6 и UDP не получают статус PASS по этой пробе. Их
пакетные проверки относятся к отдельному Linux VM/netns gate и должны иметь свои артефакты.

## 0. Ограничения и остановка

- Не выполнять `net down`, disable, uninstall, `--force`, reboot, сон, остановку/перезапуск
  служб, произвольные nft/ip/sysctl/apt/runuser, панель/браузер, pool/pin/probe-команды.
  Исключения: штатная установка шага 2.2, точные режимы помощника §3 и восстановление ниже.
- Не редактировать установленный код/конфиги и системные службы. Рабочий клон обновляется только
  штатным fast-forward в шаге2.1. Не выполнять reset/checkout при несовпадении.
- Не печатать сырые конфиги, status/capture/state, подписки, полный ruleset/маршруты и журналы.
  В локальных install.txt могут быть частные данные: не публиковать файл целиком.
- В отчёте скрыть имена устройств/подписок/пользователей машины, LAN/tailnet/MAC/внешние IP,
  домены/URL серверов и строки журнала. Разрешены служебные xray/xgw-singbox, теги proxy-…,
  capabilities, права, счётчики, времена и подготовленные строки помощника.
- Нет guard, несовпадение Capture.loaded, нездоровая база или ошибка изоляции — **не делать
  cut**, записать FAIL/NOT_RUN и перейти к безопасному итогу. Traceback помощника — дефект
  помощника; не чинить его на машине и не делать последующие cut.
- Интернет/доступ отсутствует дольше 60 с: `sudo xgw net up`; если `systemctl is-active xgw`
  не active — `sudo systemctl start xgw`; подождать 30 с. Сохранить сокращённый status/state,
  остановить все дальнейшие cut и сообщить заказчику. Не откатывать сеть произвольными командами.

## 1. Подготовка

### 1.0. Предусловия (только чтение)

В клоне `~/zcod/xgw` должна быть ветка `freepool`, без локальных правок. Другую ветку,
незавершённый merge, изменённые/неотслеживаемые файлы не сбрасывать: STOP и сообщить заказчику.
Сохранить экземпляр этого ТЗ в `$HOME/xgw-w3/plan.md` вне клона; чтение нового ТЗ на GitHub
само по себе клон не обновляет. Обновление — только шаг2.1 после исходных замеров.

```bash
mkdir -p "$HOME/xgw-w3" && chmod 700 "$HOME/xgw-w3" && cd ~/zcod/xgw && git branch --show-current && git rev-parse HEAD && git status --porcelain && systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3
```

Ожидается `freepool`, хеш исходного кода, чистый клон, `0 timers listed`.
Wave2-отчёт уже завершён; его наличие не доказывает wave3. Если уже установлен новый код,
записать факт и исходный HEAD: повторный прогон не выдавать за первую миграцию.

### 1.1. Согласие на живую проверку

Если в этой сессии уже дано явное согласие на соответствующий пункт, сослаться на него и не
спрашивать повторно. Иначе спросить по пунктам, записать ответ и время:

«Проверяю отдельный барьер и sing-box без сетевых прав. FreePool и подписку не меняю.
(1) Можно установить проверенный локальный код? Службы могут перезапуститься; возможен короткий
обрыв интернета и старых соединений, принятые ядра сохраняются.
(2) Можно выполнить шесть проверок изоляции и три точные тестовые правки правил XGW? Возможен
обрыв до 40 секунд (граница ожидания 60 секунд). Проверка пытается открыть чужой файл/API,
создать временный файл состояния и добавить безопасное тестовое ip rule; ожидается отказ,
неожиданно созданные объекты сразу удаляются. RST со счётчиком даёт лишь локальное свидетельство,
без WAN sentinel отсутствие пакетов на проводе этим не доказано.
(3) Можно 10 минут читать состояние/счётчики и журнал без правок? Можно согласиться частично.»

Отказ от (1) — STOP; отказ от (2) — весь §3 NOT_RUN; отказ от (3) — §4 NOT_RUN.
Не считать молчание согласием. Новые live-проверки сверх этих пунктов не добавлять.

### 1.2. Помощник и его fingerprint

Команду скопировать целиком. Не менять помощник на машине. Он читает только подготовленные
агрегаты; `isolation` делает описанные попытки, `cut` — одну точную правку. Перед cut он
отказывается работать без целого guard/исходного перехвата/успешной пробы и в открытом режиме.
`cut rule` для host TUN не применяется: host использует pref90, а не pref100.

```bash
cd "$HOME/xgw-w3" && cat > w3check.py <<'EOF'
"""XGW 0.2.0: волна 3 кросс-аудита (барьер inet xgw_guard, sing-box от своего пользователя) —
помощник проверки. Читает состояние XGW (/run/xgw/status.json, /var/lib/xgw/capture.json — только
наличие эталона и признак расхождения), таблицы nftables (счётчики барьера, число правил),
процессы ядер (/proc/PID/status), права на их конфиги и журнал со стандартного ввода
(journalctl -o short-unix). Меняет что-то только режим cut — по команде шага: убирает одно
своё правило XGW и ждёт, пока демон его вернёт. Режим isolation пробует от имени пользователей
ядер читать чужое и добавить правило ip rule (у них прав нет — ничего не меняется; если вдруг
добавится — убирает сразу; при неудаче очистки останавливается). Адресов устройств и серверов не печатает. Время — секунды с 1970
(date +%s). Режимы: units, state, sub, sbstat [МЕТКА], guard, allow, cores, isolation,
cut output|table|rule, capstate, check, log [МЕТКА], sblog, ts, time."""
import grp
import ipaddress
import json
import os
import pwd
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-net.service", "xgw-xray.service", "xgw-singbox.service",
         "xgw-dhcp.service")
LIB = os.environ.get("W3CHECK_LIB", "/opt/xgw/lib")
STAMP = re.compile(r"^(\d+(?:\.\d+)?) ")
CHAIN = re.compile(r"^\s*chain (\w+) \{[^\n]*\n(.*?)^\s*\}", flags=re.MULTILINE | re.DOTALL)
SB_USER = "xgw-singbox"
GUARD = ("inet", "xgw_guard")
BIT = "0x20000000"
PROBE = ("1.1.1.1", 443)  # общедоступный адрес в интернете; в выводе не печатается
TEST_NET = "203.0.113.0/24"
RELOADED = "правила сети не были загружены — загружены заново"
CAPS = {10: "CAP_NET_BIND_SERVICE", 12: "CAP_NET_ADMIN", 13: "CAP_NET_RAW"}


def run(argv, user=None, timeout=30):
    if user is not None:
        argv = ["runuser", "-u", user, "--", *argv]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd="/")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, type(exc).__name__
    return done.returncode, done.stdout if done.returncode == 0 else done.stderr


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
        sys.exit(2)


def status_of(paths):
    loaded = read_json(paths.status_file)
    return loaded if isinstance(loaded, dict) else {}


def when(line):
    found = STAMP.match(line)
    return float(found.group(1)) if found else None


class GuardCounts(dict):
    generation = None


def guard_counts():
    """{цепочка: [счётчики правил отказа]} барьера; None — барьера нет; строка — ошибка."""
    code, out = run(["nft", "-a", "list", "table", *GUARD])
    if code != 0:
        return None if "No such file" in out else f"код {code}"
    counts = GuardCounts({name: [int(n) for n in re.findall(r"counter packets (\d+)", body)]
                          for name, body in CHAIN.findall(out)})
    handle = re.search(r"table inet xgw_guard \{\s*# handle (\d+)", out)
    counts.generation = int(handle.group(1)) if handle else None
    return counts


def total(counts):
    return sum(sum(values) for values in counts.values()) if isinstance(counts, dict) else 0


def probe():
    """TCP к адресу в интернете: «отбито (сброс)», «соединилось», «нет ответа за 3 с»."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    began = time.monotonic()
    try:
        sock.connect(PROBE)
        result = "соединилось"
    except ConnectionRefusedError:
        result = "отбито (сброс)"
    except TimeoutError:
        result = "нет ответа за 3 с"
    except OSError as exc:
        result = f"ошибка {type(exc).__name__} {exc.errno}"
    finally:
        sock.close()
    return f"{result} за {time.monotonic() - began:.2f} с"


def unit_process(unit):
    pid = show(unit, "MainPID")
    if not pid.isdigit() or pid == "0":
        return None
    fields = dict(line.split(":", 1) for line in
                  Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines()
                  if ":" in line)
    uid = int(fields["Uid"].split()[1])
    caps = int(fields["CapEff"].strip(), 16)
    try:
        name = pwd.getpwuid(uid).pw_name
    except KeyError:
        name = str(uid)
    rights = [label for bit, label in sorted(CAPS.items()) if caps >> bit & 1]
    other = caps & ~sum(1 << bit for bit in CAPS)
    try:
        xray_gid = grp.getgrnam("xray").gr_gid
    except KeyError:
        xray_gid = -1
    gids = {int(value) for value in fields.get("Groups", "").split()}
    gids.add(int(fields["Gid"].split()[1]))
    capsets = {label: int(fields[key].strip(), 16) for label, key in
               (("Eff", "CapEff"), ("Prm", "CapPrm"), ("Amb", "CapAmb"), ("Bnd", "CapBnd"))}
    return (name, (", ".join(rights) or "нет") + (f" и ещё {other:#x}" if other else ""),
            xray_gid in gids, capsets)


def name_of(lookup, ident):
    try:
        return lookup(ident)[0]
    except KeyError:
        return str(ident)


def owner(path):
    try:
        info = path.stat()
    except OSError as exc:
        return f"нет ({type(exc).__name__})"
    return (f"{name_of(pwd.getpwuid, info.st_uid)}:{name_of(grp.getgrgid, info.st_gid)} "
            f"{info.st_mode & 0o7777:o}")


def keys_named(node, key):
    if isinstance(node, dict):
        return (key in node) + sum(keys_named(value, key) for value in node.values())
    if isinstance(node, list):
        return sum(keys_named(value, key) for value in node)
    return 0


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
elif mode == "state":
    _cfg, paths = xgw()
    status = status_of(paths)
    pool = status.get("free_pool") if isinstance(status.get("free_pool"), dict) else {}
    print(f"состояние шлюза: {status.get('state')}; режим пула: {pool.get('mode') or 'off'}")
elif mode == "sub":
    _cfg, paths = xgw()
    pin = status_of(paths).get("pin")
    pin = pin if isinstance(pin, dict) else {}
    print("выбран вручную: " + ("нет" if not pin.get("tag") else f"{pin.get('tag')} — "
                                + ("не отвечает, ведёт автовыбор" if pin.get("down")
                                   else "держится")))
elif mode == "sbstat":
    _cfg, paths = xgw()
    try:
        mark = float(sys.argv[2])
    except (IndexError, ValueError):
        mark = 0.0
    status = status_of(paths)
    info = status.get("singbox") if isinstance(status.get("singbox"), dict) else {}
    members = [item for item in status.get("members") or []
               if isinstance(item, dict) and item.get("core") == "sing-box"]
    spares = [item for item in status.get("spares") or []
              if isinstance(item, dict) and item.get("core") == "sing-box"]
    fresh = [item for item in spares if (item.get("scanned") or 0) >= mark]
    good = [item for item in fresh if item.get("verdict") in ("OK", "SLOW")]
    alive = info.get("alive")
    print(f"sing-box: отвечает: {'да' if alive else 'нет' if alive is False else '—'}; "
          f"серверов через него: {info.get('bridged', 0)}; участников на sing-box: "
          f"{len(members)} (живы {sum(1 for item in members if item.get('alive'))}); "
          f"запасных на sing-box: {len(spares)}, проверены после метки: {len(fresh)} "
          f"(OK или SLOW: {len(good)})")
elif mode == "guard":
    counts = guard_counts()
    if counts is None:
        print("барьер: нет")
    elif isinstance(counts, str):
        print(f"барьер: не прочитать — {counts}")
    else:
        def pair(name):
            values = counts.get(name)
            return f"TCP {values[-2]}, прочее {values[-1]}" if values and len(values) >= 2 else "—"
        print(f"барьер: есть; цепочки: {', '.join(sorted(counts))}; отбито: машина {pair('output')}"
              f"; транзит {pair('transit')}; loopback {sum(counts.get('output', [])[:-2])}; "
              f"всего {total(counts)}; поколение таблицы {counts.generation}")
elif mode == "allow":
    code, out = run(["nft", "-t", "list", "table", "ip", "xgw"])
    if code != 0:
        print("таблицы ip xgw нет" if "No such file" in out else "ip xgw не прочитать")
        sys.exit(0)
    lines = [line for line in out.splitlines() if "ct mark set" in line]
    skuid = [line for line in out.splitlines() if "meta skuid" in line]
    try:
        uid = str(pwd.getpwnam(SB_USER).pw_uid)
    except KeyError:
        uid = ""
    # nft печатает пользователя числом или именем — в зависимости от сборки и ключей.
    who = re.compile(rf'skuid (?:{uid}(?![0-9])|"{SB_USER}")') if uid else None
    print(f"правил с битом барьера в ip xgw: {len(lines)} (бит {BIT}: "
          f"{'есть' if any(BIT in line for line in lines) else 'нет'}); правил с пользователем "
          f"sing-box: {sum(1 for line in skuid if who and who.search(line))}")
elif mode == "cores":
    _cfg, paths = xgw()
    for label, unit in (("Xray", "xgw-xray.service"), ("sing-box", "xgw-singbox.service")):
        found = unit_process(unit)
        print(f"{label}: " + ("не работает" if found is None
                              else f"пользователь {found[0]}, права: {found[1]}"))
        if label == "sing-box" and found is not None:
            print("группа xray у процесса sing-box: " + ("ДА" if found[2] else "нет"))
            print("sing-box capabilities: " + " ".join(f"{key}={value:#x}"
                                                         for key, value in found[3].items()))
    xray_dir = paths.xray_config_dir
    sb_dir = paths.singbox_config_file.parent
    print(f"конфиг Xray: {owner(xray_dir / 'config.json')} (каталог {owner(xray_dir)}); "
          f"конфиг sing-box: {owner(paths.singbox_config_file)} (каталог {owner(sb_dir)})")
    config = read_json(paths.singbox_config_file)
    print("routing_mark в конфиге sing-box: "
          + ("конфига нет" if config is None else str(keys_named(config, "routing_mark"))))
elif mode == "isolation":
    _cfg, paths = xgw()
    try:
        pwd.getpwnam(SB_USER)
    except KeyError:
        print(f"пользователя {SB_USER} нет")
        sys.exit(0)
    read = ("import sys\ntry:\n    open(sys.argv[1], 'rb').read(1)\n    print('прочитан')\n"
            "except PermissionError:\n    print('отказ')\nexcept OSError as e:\n"
            "    print(type(e).__name__)")
    sock = ("import socket, sys\ns = socket.socket(socket.AF_UNIX)\ntry:\n"
            "    s.connect(sys.argv[1])\n    print('подключился')\nexcept PermissionError:\n"
            "    print('отказ')\nexcept OSError as e:\n    print(type(e).__name__)")
    write = ("import os, sys\np = os.path.join(sys.argv[1], 'w3-test-' + str(os.getpid()))\ntry:\n"
             "    open(p, 'x').close()\n    os.remove(p)\n    print('записал')\n"
             "except PermissionError:\n    print('отказ')\nexcept OSError as e:\n"
             "    print(type(e).__name__)")

    def py(user, code, arg):
        rc, out = run(["python3", "-I", "-c", code, str(arg)], user=user)
        return out.strip().splitlines()[-1] if out.strip() else f"код {rc}"

    xray_conf = paths.xray_config_dir / "config.json"
    print(f"sing-box → конфиг Xray: {py(SB_USER, read, xray_conf)}")
    print(f"sing-box → API Xray: {py(SB_USER, sock, '/run/xgw-xray/api.sock')}")
    print(f"sing-box → запись в состояние XGW (/var/lib/xgw): {py(SB_USER, write, paths.var)}")
    code, out = run(["nft", "list", "tables"], user=SB_USER)
    print("sing-box → правила nftables: " + ("ПРОЧИТАЛ" if code == 0 else "отказ"
                                              if "not permitted" in out else f"код {code}"))
    rc, listing = run(["ip", "-j", "rule", "show"])
    try:
        rules = json.loads(listing) if rc == 0 else None
    except ValueError:
        rules = None
    if not isinstance(rules, list) or any(isinstance(rule, dict)
            and rule.get("priority") == 49 for rule in rules):
        print("sing-box → правило ip rule: NOT_RUN (pref 49 занят или список недоступен)")
        print(f"Xray → конфиг sing-box: {py('xray', read, paths.singbox_config_file)}")
        sys.exit(2)
    rule = ["ip", "rule", "add", "from", TEST_NET, "lookup", "main", "pref", "49"]
    code, out = run(rule, user=SB_USER)
    if code == 0:
        cleaned, _out = run(["ip", "rule", "del", "from", TEST_NET, "lookup", "main", "pref", "49"])
        print("sing-box → правило ip rule: ДОБАВИЛ (сразу убрано)" if cleaned == 0
              else "sing-box → правило ip rule: ДОБАВИЛ; ОЧИСТКА НЕ УДАЛАСЬ; STOP")
        if cleaned != 0:
            sys.exit(2)
    else:
        print("sing-box → правило ip rule: " + ("отказ" if "not permitted" in out
                                                 else f"код {code}"))
    print(f"Xray → конфиг sing-box: {py('xray', read, paths.singbox_config_file)}")
elif mode == "cut":
    cfg, paths = xgw()
    from xgw.net import capture as capturing

    what = sys.argv[2] if len(sys.argv) > 2 else ""
    mark, table = cfg.capture.mark_proxy, cfg.capture.route_table
    commands = {
        "output": ("цепочка output (метки трафика машины) опустошена",
                   ["nft", "flush", "chain", "ip", "xgw", "output"]),
        "table": ("таблица ip xgw удалена", ["nft", "delete", "table", "ip", "xgw"]),
        "rule": ("правило ip rule XGW (pref 100) удалено",
                 ["ip", "rule", "del", "fwmark", str(mark), "lookup", str(table), "pref", "100"]),
    }
    if what not in commands:
        print("cut: output | table | rule")
        sys.exit(2)
    capture = capturing.capture_for(cfg, paths)
    if (not cfg.capture.local or not cfg.capture.hold_blocks or cfg.capture.fail_mode != "closed"
            or cfg.free_pool.mode != "off" or capture.effective_mode() != "on"):
        print("NOT_RUN: нужны local=True, hold=block, fail_mode=closed, pool=off и capture mode=on")
        sys.exit(2)
    if what == "rule" and cfg.capture.tun:
        print("NOT_RUN: host TUN использует pref 90; host probe не проверяет удаление pref 100")
        sys.exit(2)
    if any(ipaddress.ip_address(PROBE[0]) in ipaddress.ip_network(cidr, strict=False)
           for cidr in cfg.capture.exclude_cidrs):
        print("NOT_RUN: адрес пробы исключён из перехвата")
        sys.exit(2)
    before = guard_counts()
    if (not isinstance(before, dict) or not {"forward", "output", "pass", "transit"} <= before.keys()
            or len(before.get("output", [])) != 6 or len(before.get("transit", [])) != 2):
        print("NOT_RUN: барьер отсутствует, не читается или его структура не ожидаемая")
        sys.exit(2)
    if capture.loaded() is not True:
        print("NOT_RUN: исходные правила не соответствуют эталону")
        sys.exit(2)
    process = unit_process("xgw-singbox.service")
    if (process is None or process[0] != SB_USER or process[2]
            or any(process[3].values())):
        print("NOT_RUN: UID/группы/capability-наборы службы sing-box не изолированы")
        sys.exit(2)

    def number(value):
        try:
            return int(str(value), 0)
        except ValueError:
            return None

    def restored():
        if what == "output":
            code, out = run(["nft", "list", "chain", "ip", "xgw", "output"])
            return code == 0 and "meta mark set" in out
        if what == "table":
            code, out = run(["nft", "-t", "list", "table", "ip", "xgw"])
            return code == 0 and "chain output" in out
        code, out = run(["ip", "-j", "rule", "show"])
        try:
            rules = json.loads(out) if code == 0 else []
        except ValueError:
            rules = []
        keys = {"priority", "src", "dst", "fwmark", "fwmask", "iif", "table", "protocol"}
        return any(isinstance(item, dict) and set(item) <= keys
                   and item.get("priority") == 100 and str(item.get("table")) == str(table)
                   and number(item.get("fwmark", "")) == mark
                   and number(item.get("fwmask", "0xffffffff")) == 0xffffffff
                   and item.get("src", "all") == "all" and item.get("dst", "all") == "all"
                   and item.get("iif") is None for item in rules)

    if not restored():
        print("NOT_RUN: правило и так не на месте — правку не делаю")
        sys.exit(2)
    baseline = probe()
    print(f"соединение до правки: {baseline}")
    if not baseline.startswith("соединилось"):
        print("NOT_RUN: нет исходного успешного соединения; правку не делаю")
        sys.exit(2)
    label, argv = commands[what]
    code, _out = run(argv)
    if code != 0:
        print(f"NOT_RUN: правка не сделана, код {code}")
        sys.exit(2)
    began = time.monotonic()
    damage_before = not restored()
    first = probe()
    damage_after = not restored()
    after = guard_counts()
    back = None
    while time.monotonic() - began < 60:
        if restored():
            back = time.monotonic() - began
            break
        time.sleep(0.5)
    second = probe() if back is not None else "не проверялось"
    delta = tcp_delta = None
    stable = (isinstance(after, dict) and isinstance(before, dict)
              and before.generation is not None and before.generation == after.generation
              and len(after.get("output", [])) == 6)
    if stable:
        delta = total(after) - total(before)
        tcp_delta = after["output"][-2] - before["output"][-2]
        grown = (f"{delta:+d}; final host TCP {tcp_delta:+d}" if delta >= 0 and tcp_delta >= 0
                 else "COUNTER_RESET_OR_RELOAD")
    else:
        grown = "COUNTER_RESET_OR_RELOAD_OR_GENERATION_UNKNOWN"
    local = (stable and damage_before and damage_after and first.startswith("отбито (сброс)")
             and delta is not None and delta >= 0 and tcp_delta is not None and tcp_delta > 0)
    print(f"{label}; соединение сразу после правки: {first}; изменение счётчиков: {grown}")
    print(f"повреждение присутствует до/после пробы: {damage_before}/{damage_after}; "
          + ("LOCAL_GUARD_EVIDENCE" if local else "INCONCLUSIVE") + "; E4 NOT_RUN")
    print("структура правила вернулась через " + (f"{back:.1f} с" if back is not None
                                                   else "— НЕ вернулась за 60 с")
          + f"; соединение после возврата: {second}")
elif mode == "capstate":
    _cfg, paths = xgw()
    state = read_json(paths.var / "capture.json")
    state = state if isinstance(state, dict) else {}
    mismatch = state.get("mismatch") or ""
    print(f"эталон правил: {'есть' if state.get('baseline') else 'нет'}; расхождение с текстом "
          "правил: " + ("ЕСТЬ (текст скрыт)" if mismatch else "нет"))
elif mode == "check":
    cfg, paths = xgw()
    from xgw.net import capture as capturing

    capture = capturing.capture_for(cfg, paths)
    began = time.monotonic()
    first = capture.loaded()
    middle = time.monotonic()
    second = capture.loaded()
    end = time.monotonic()
    print(f"проверка правил: {first} за {middle - began:.2f} с; повторно: {second} за "
          f"{end - middle:.2f} с")
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    try:
        mark = float(sys.argv[2])
    except (IndexError, ValueError):
        mark = 0.0
    reloads = [stamp for stamp in (when(line) for line in lines if RELOADED in line) if stamp]
    after = [stamp for stamp in reloads if stamp >= mark]
    print(f"строк журнала: {len(lines)}; загрузок правил заново: {len(after)}")
    for label, word in (("барьер держит", "барьер держит"),
                        ("барьер не загружен", "не загружен: "),
                        ("не сходятся с текстом правил", "не сходятся с текстом правил"),
                        ("ошибок загрузки правил", "правила перехвата не загружены"),
                        ("Traceback", "Traceback")):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
elif mode == "sblog":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала sing-box: {len(lines)}")
    for label, word in (("operation not permitted", "operation not permitted"),
                        ("permission denied", "permission denied"),
                        ("FATAL", "fatal")):
        print(f"{label}: {sum(1 for line in lines if word in line.lower())}")
elif mode == "ts":
    code, out = run(["tailscale", "status", "--json"])
    if code == 127:
        print("Tailscale: нет на машине")
        sys.exit(0)
    try:
        data = json.loads(out)
    except ValueError:
        print(f"Tailscale: ответ не разобрать (код {code})")
        sys.exit(0)
    me = data.get("Self") if isinstance(data.get("Self"), dict) else {}
    print(f"Tailscale: {data.get('BackendState')}; в сети: {'да' if me.get('Online') else 'нет'}")
elif mode == "time":
    value = run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])[1].strip()
    print(f"время синхронизировано: {value or 'не узнать'}")
else:
    print("режим: units | state | sub | sbstat [МЕТКА] | guard | allow | cores | isolation | "
          "cut output|table|rule | capstate | check | log [МЕТКА] | sblog | ts | time")
EOF
python3 - <<'PY'
from pathlib import Path
import hashlib
p = Path('w3check.py')
data = p.read_bytes().replace(b'\r\n', b'\n').rstrip(b'\n') + b'\n'
p.write_bytes(data)
print(hashlib.sha256(data).hexdigest())
PY
```

Ожидается полный SHA256 `ac3e6d94cb90c66759474204f1a8b7bfbd6d2008dde094d63a5cf2c2389b8b04`. Нормализация: CRLF→LF и один завершающий LF.
Другая сумма — повторить копирование один раз; снова другая — STOP. Эту же сумму должен
подтвердить шаг2.1. Только синтаксическая/offline проверка помощника у разработчика не является
запуском на машине и не переводит реальные кейсы в PASS.

### 1.3. До установки

```bash
cd "$HOME/xgw-w3" && date '+%F %T' | tee before.txt
sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt
sudo xgw pool 2>&1 | head -1 | tee -a before.txt
for m in units state sub sbstat guard allow cores check; do sudo python3 -I w3check.py "$m"; done 2>&1 | tee -a before.txt
```

Записать весь безопасный вывод помощника, N/A/B sing-box, версии и ручной выбор. Ожидается
HEALTHY, включённый перехват, pool off, рабочие службы, Capture.loaded True дважды. На старом
коде отсутствие guard/UID xgw-singbox — ожидаемая база, а не результат wave3. Старые capabilities,
права конфигов и routing_mark зафиксировать фактически, не подставлять образец. При pool on,
не-HEALTHY или неработающих ядрах — STOP до установки и согласовать дальнейшую диагностику.

## 2. Опубликованный код и установка

### 2.1. Обновление freepool и проверка commit

Только после исходных замеров и согласия1. Блок обновляет чистую ветку fast-forward,
проверяет commit реализации, неизменность runtime-кода и fingerprint помощника.
Любая ошибка — STOP; не обходить её reset/force/ручной правкой. Никакого ZIP применять не нужно.

```bash
(
set -o pipefail
cd "$HOME/xgw-w3" || exit 2
python3 - <<'PY' | tee source-preflight.txt
import ast, hashlib, subprocess
from pathlib import Path
repo = Path.home() / 'zcod/xgw'
helper = Path.home() / 'xgw-w3/w3check.py'
code = 'fd65fc4b18fa8ea658737e9612544bdf63536b4c'
expected_helper = 'ac3e6d94cb90c66759474204f1a8b7bfbd6d2008dde094d63a5cf2c2389b8b04'

def git(*args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

def require(ok, text):
    if not ok:
        raise SystemExit('STOP: ' + text)

require(git('branch', '--show-current') == 'freepool', 'нужна ветка freepool')
require(not git('status', '--porcelain'), 'рабочее дерево не чистое')
before = git('rev-parse', 'HEAD')
subprocess.run(['git', '-C', str(repo), 'fetch', '-q', 'origin', 'freepool'], check=True)
subprocess.run(['git', '-C', str(repo), 'merge', '--ff-only', 'origin/freepool'], check=True)
subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', code, 'HEAD'], check=True)
runtime = ['src', 'packaging', 'config.example.toml', 'pyproject.toml']
require(not git('diff', '--name-only', code, 'HEAD', '--', *runtime),
        'опубликованный runtime-код изменён после проверяемого commit; требуется новое ТЗ')
require(not git('status', '--porcelain'), 'после обновления клон не чистый')
data = helper.read_bytes().replace(b'\r\n', b'\n').rstrip(b'\n') + b'\n'
require(hashlib.sha256(data).hexdigest() == expected_helper, 'сумма помощника')
tree = ast.parse((repo / 'src/xgw/net/nft.py').read_text(encoding='utf-8'))
require(any(isinstance(n, ast.FunctionDef) and n.name == 'render_guard' for n in tree.body),
        'нет render_guard')
unit = (repo / 'packaging/xgw-singbox.service').read_text(encoding='utf-8').splitlines()
for line in ('User=xgw-singbox', 'Group=xgw-singbox', 'AmbientCapabilities=', 'CapabilityBoundingSet='):
    require(line in unit, 'не тот unit sing-box: ' + line)
print('SOURCE_PREFLIGHT_OK')
print('HEAD до обновления: ' + before)
print('commit реализации: ' + code)
print('HEAD установки: ' + git('rev-parse', 'HEAD'))
print('tree установки: ' + git('rev-parse', 'HEAD^{tree}'))
print('helper_sha256: ' + hashlib.sha256(data).hexdigest())
PY
)
```

Ожидается `SOURCE_PREFLIGHT_OK`, исходный HEAD, commit реализации, HEAD/tree установки и
полный fingerprint помощника. Сохранить source-preflight.txt. После неуспешного обновления
установку не начинать. В отчёте идентичность кода — эти фактические Git-хеши.
Локальные проверки описаны в `docs/IMPLEMENTATION-WAVE3-LOCAL.md`; реальные проверки пока
NOT_RUN. Наличие commit не превращает отсутствующее WAN packet evidence в E4 PASS.

### 2.2. Установка

Только после успешного 2.1 и согласия1. Сказать: «Запускаю установку опубликованного проверяемого
кода. Возможен краткий обрыв; дождитесь завершения». Полный вывод остаётся локально:

```bash
(
set -o pipefail
cd ~/zcod/xgw || exit 2
date '+%F %T' | tee "$HOME/xgw-w3/install-time.txt"
date +%s > "$HOME/xgw-w3/t-install.txt"
sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-w3/install.txt" | tail -6
w3_install_rc=${PIPESTATUS[0]}
printf 'код %s\n' "$w3_install_rc" | tee "$HOME/xgw-w3/install-rc.txt"
exit "$w3_install_rc"
)
```

Ожидается код0. Не угадывать успех по последней строке tee. При не-0 — STOP, сохранить файлы,
сообщить заказчику; не исправлять/откатывать вручную. Если kernel/guard preflight отказывает,
записать FAIL совместимости и выполнить только безопасный итог. Не продолжать без guard.

### 2.3. После установки

Подождать 90 секунд (двумя ожиданиями по45, если нужно поддерживать связь). Затем:

```bash
cd "$HOME/xgw-w3"
sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee after-install.txt
for m in units state sub guard allow cores capstate check; do sudo python3 -I w3check.py "$m"; done 2>&1 | tee -a after-install.txt
sudo python3 -I w3check.py sbstat "$(cat t-install.txt)" | tee -a after-install.txt
sudo journalctl -u xgw --since "$(cat install-time.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log | tee log-install.txt
sudo journalctl -u xgw-singbox --since "$(cat install-time.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py sblog | tee -a log-install.txt
sudo xgw diag 2>&1 | grep -E 'Ядро|Перехват|Барьер|Пользователи ядер|Эталон правил' | tee -a after-install.txt
```

Ожидается HEALTHY, pooloff, те же версии/ручной выбор; пять служб active, Capture.loaded True
дважды, эталон есть и расхождения нет. Guard имеет forward/output/pass/transit; в output четыре loopback-reject и два
финальных reject, в transit два финальных reject. TCP/прочее — последние два счётчика каждой
цепочки, loopback показан отдельно, «всего» включает все восемь. Бит0x20000000 присутствует в правилах прямого пропуска; UID bypass
sing-box присутствует (ожидаются два в ipxgw; точный режим и фактическое число записать).
Постоянный sing-box: пользователь xgw-singbox, effective capabilities нет, группы xray нет;
capability-наборы Eff/Prm/Amb/Bnd=0; его конфиг root:xgw-singbox0640, каталог2750; Xray отдельно root:xray0640/2750; routing_mark0.
Diag подтверждает соответствие guard политике и изоляцию; FAIL недопустим; sing-box отвечает, нет новых permission/fatal
ошибок. Числа N/A/B сравнить фактически: уменьшение alive само по себе ещё не доказывает
регрессию прав, удалённый узел мог стать недоступным. `sbstat` берёт статус XGW, не заменяет
самостоятельную передачу payload. Начальные ненулевые guard counters возможны после обрыва
старых direct-сессий; записать их, не обнулять.

Нет guard, нет изоляции, capture mismatch, неHEALTHY или sing-box не работает — записать FAIL,
**весь §3 NOT_RUN**, сообщить заказчику и перейти к §5. Не проверять дырявый барьер cut-правкой.
При одной недоступности удалённого узла не приписывать причину permissions без подтверждения.

## 3. Изоляция и три scoped fault (только согласие2 и целая база)

### 3.1. Шесть попыток изоляции

```bash
cd "$HOME/xgw-w3" && sudo python3 -I w3check.py isolation | tee r-31.txt
```

Ожидаются шесть «отказ»: чтение конфигаXray, UNIXAPIXray, запись состоянияXGW, nftlisttables,
ipruleadd и чтение конфигаSB пользователемXray. Проверка runuser описывает обычный UID;
CapEff/группа **реального процесса службы** отдельно проверены в2.3. FileNotFoundError,
отсутствующий пользователь, занятый pref49, ошибка инструмента — INCONCLUSIVE/NOT_RUN, не PASS
изоляции. Любой успешный доступ/создание — FAIL изоляции, последующие cut NOT_RUN. При ошибке
очистки тестового правила — STOP и сообщить; не импровизировать с ip-командами.

**Оценка каждого cut до перехода к следующему:**

Записать исходную успешную пробу, fault-present до/после, ответ после повреждения, counterdelta,
структурное время восстановления, успешную пробу после и Capture.loaded True. Ориентиры: output/
таблица до10с, RPDB до40с, предел60с. Время — структурный polling, полное восстановление отдельно
подтверждает loaded, не округлять до первого пакета. RST+положительная delta при наблюдённом
повреждении — только LOCAL_GUARD_EVIDENCE. Если демон успел до/во время пробы, поколение guard сменилось/не читается, счётчик сброшен,
проба timeout или delta0 — INCONCLUSIVE, не leak/PASS. `соединилось` при fault-present — сигнал
для расследования пути; без packet evidence не объявлять утечку. Не повторять cut ради гонки.
Если guard пропал или loaded остаётсяFalse, нет восстановления60с или соединение после не
вернулось — FAIL восстановления, выполнить безопасный recovery§0, дальнейшие cut NOT_RUN.
Даже три LOCAL_GUARD_EVIDENCE не закрывают E4 actual-packets gate.


### 3.2. Опустошить только output ipxgw

```bash
cd "$HOME/xgw-w3" && date +%s > t-32.txt && sudo python3 -I w3check.py cut output | tee r-32.txt
for m in guard capstate check; do sudo python3 -I w3check.py "$m"; done 2>&1 | tee -a r-32.txt
sudo journalctl -u xgw --since "@$(cat t-32.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log "$(cat t-32.txt)" | tee -a r-32.txt
```

### 3.3. Удалить только ipxgw

Только после успешного восстановления и проверки3.2, иначе NOT_RUN:

```bash
cd "$HOME/xgw-w3" && date +%s > t-33.txt && sudo python3 -I w3check.py cut table | tee r-33.txt
for m in guard capstate check; do sudo python3 -I w3check.py "$m"; done 2>&1 | tee -a r-33.txt
sudo journalctl -u xgw --since "@$(cat t-33.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log "$(cat t-33.txt)" | tee -a r-33.txt
```

### 3.4. Удалить только собственное fwmark/RPDB pref100

Только после успешного восстановления3.3. В hostTUN этот кейс NOT_RUN без изменения сети;
проверку pref90 или клиентовLAN здесь не добавлять.

```bash
cd "$HOME/xgw-w3" && date +%s > t-34.txt && sudo python3 -I w3check.py cut rule | tee r-34.txt
for m in guard capstate check; do sudo python3 -I w3check.py "$m"; done 2>&1 | tee -a r-34.txt
sudo journalctl -u xgw --since "@$(cat t-34.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log "$(cat t-34.txt)" | tee -a r-34.txt
```


## 4. Десять минут наблюдения (только согласие3)

Сохранить начальные счётчики и метку независимо от того, выполнялся ли §3:

```bash
cd "$HOME/xgw-w3" && date +%s > t-watch.txt && sudo python3 -I w3check.py guard | tee guard-start.txt
```

Подождать 10 минут без вмешательства; поддерживать связь с заказчиком. Ожидать отдельными
командами `sleep 60` десять раз, не одним блокирующим вызовом на600с. Затем:

```bash
cd "$HOME/xgw-w3"
sudo python3 -I w3check.py guard | tee guard-end.txt
sudo journalctl -u xgw --since "@$(cat t-watch.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log "$(cat t-watch.txt)" | tee log-watch.txt
sudo journalctl -u xgw-singbox --since "@$(cat t-watch.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py sblog | tee -a log-watch.txt
sudo python3 -I w3check.py sbstat "$(cat t-install.txt)" | tee -a log-watch.txt
for m in state ts time capstate check; do sudo python3 -I w3check.py "$m"; done 2>&1 | tee -a log-watch.txt
```

Желательно отсутствие неожиданных reload/permission/fatal/Traceback, стабильная работа подписки,
Tailscale/time и loadedTrue. Записать начальные/конечные счётчики и **факт reload**. Рост reject
не доказывает блокировку законного трафика: без атрибуции потоку это OBSERVATION. Нулевая delta
тоже не доказывает работоспособность всех разрешённых путей. При reload/reset delta несопоставима.
Новые регулярные reload без внесённых правок или воспроизводимая потеря ранее работавшего пути —
дефект/расследование с условиями; не приписывать все фоновые отказы guard по одному счётчику.

## 5. Безопасный итог

Если установка не начиналась, пропустить чтение отсутствующего install-time; записать STOP и
фактическое состояние. Иначе:

```bash
cd "$HOME/xgw-w3"
sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt
date '+%F %T' | tee final.txt
sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt
for m in units state sub guard cores; do sudo python3 -I w3check.py "$m"; done 2>&1 | tee -a final.txt
```

Ожидается0 URL-pattern matches, HEALTHY, те же ядра/режим/ручной выбор, guard и SBизоляция.
Нулевой pattern-count покрывает только перечисленные URI, **не доказывает отсутствие всех
секретов** в журнале. При matches не печатать строки, отметить число и сообщить разработчику.
Сказать заказчику: «Проверка закончена, сохраняю локальный отчёт».

## 6. Локальный отчёт и последующий review

Заполнить отдельный `docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3-TEMPLATE.md`, сохранить результат
**локально** в `$HOME/xgw-w3/TEST-REPORT-REAL-MACHINE-0.2.0-wave3-YYYY-MM-DD.md`. Каждый пункт
получает фактический PASS/FAIL/INCONCLUSIVE/NOT_RUN и ссылку на сохранённый файл. Не выполненные
кейсы и отсутствующее согласие остаются NOT_RUN; пример успешного вывода не является результатом.
Код обозначить commit реализации, фактическими HEAD/tree установки и helperSHA.
E4 без фактического packet artifact — NOT_RUN с явной причиной «нет WANsentinel на машине».
Итог ограничить проверенными плоскостями и отдельно назвать непокрытые пути/сценарии.

Отчёт оформить по аналогии с предыдущими:
`docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3-<ДАТА>.md` в клоне (`<ДАТА>` — дата начала
проверки). Перенести только заполненный обезличенный отчёт. Для публикации отчёта применяется
тот же порядок, что в wave2: коммит «Отчёт: XGW 0.2.0, волна 3 кросс-аудита» и `git push`
в `freepool`. В staging должен быть **только этот файл отчёта**. Если отчёт уже опубликован,
push не fast-forward или есть чужие изменения — STOP; не amend/reset/rebase/force и не
публиковать код, конфиги, evidence/private install.txt. Исходники исполнитель не исправляет.

После публикации сообщить разработчику ссылку/commit отчёта, фактические дефекты и NOT_RUN.
Разработчик продолжает исправления по отчёту. Отчёт не закрывает непроверенные сценарии.
