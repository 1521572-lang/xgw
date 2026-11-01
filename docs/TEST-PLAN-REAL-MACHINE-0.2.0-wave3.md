# Проверка XGW 0.2.0: волна 3 кросс-аудита — барьер и отдельный пользователь sing-box

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть **терминал** в сеансе заказчика
(`sudo` — от его имени). Браузер в этой проверке не нужен: всё — командами.

Одна сессия, около 45 минут (из них около 15 минут — ожидание). Режим бесплатных серверов в этой
проверке **не трогается** — дом всё время идёт через подписку.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. Выводы команд сохраняются в файлы `$HOME/xgw-w3/…`. Время шага — по выводу `date` в
   команде, не по памяти.
4. Тестовые правки правил XGW делает **только** помощник (`w3check.py cut …`) в шагах 3.2–3.4:
   он убирает одно правило, сразу пробует соединение и ждёт, пока шлюз вернёт правило сам.
5. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
6. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
7. Экземпляр этого ТЗ держи в `$HOME/xgw-w3/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2. Это **новый** помощник (`w3check.py`).
8. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `w3check.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
9. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши
   дословно строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
   «Наблюдения», со словом «предположение».

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11). Клон — `~/zcod/xgw`.
Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.31 и sing-box 1.14.4, принятые
шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 285) и зачем проверка

Внешний аудит предложил ещё две защиты:
1. **Барьер.** Раньше, если чужая программа удаляла правила перехвата XGW (цепочку, всю таблицу
   или правило маршрутизации), трафик самой машины на секунды уходил мимо VPN — пока демон не
   вернёт правила. Теперь есть отдельная таблица-барьер `inet xgw_guard`: она выпускает в
   интернет только сокеты ядер, служебное (DHCP, время, Tailscale) и то, что правила перехвата
   пропустили сами. Пропали правила — соединение отбивается сразу, а не идёт мимо VPN.
2. **sing-box от своего пользователя.** Раньше Xray и sing-box работали от одного пользователя
   `xray`, и у sing-box были права менять сеть машины. Теперь sing-box — от пользователя
   `xgw-singbox`, без прав: конфиг и API Xray ему недоступны, правила сети он не меняет.

Ожидания этой проверки:
1. После установки: барьер есть; sing-box — от `xgw-singbox`, «права: нет», в его конфиге нет
   `routing_mark`; серверы через sing-box живы, как до установки; в журнале sing-box нет
   «operation not permitted».
2. От имени sing-box **все шесть** попыток (конфиг и API Xray, состояние XGW, правила nftables и
   ip rule; и Xray — конфиг sing-box) — «отказ».
3. В каждой из трёх тестовых правок соединение сразу после правки — **«отбито (сброс)»**, барьер
   отбил хотя бы один пакет, шлюз вернул правило сам (за секунды; правило ip rule — до 40 с), и
   после возврата соединение снова идёт.
4. За 10 минут наблюдения барьер **не отбил ни одного** пакета (законный трафик он не трогает),
   правила не загружались заново, Tailscale в сети, время синхронизировано.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, `reboot`, сон машины —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh` — кроме `sudo systemctl start xgw` в разделе «Если что-то пошло не так».
- Ручные `nft`, `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`, `apt`, `runuser`, `sudo -u` —
  **никогда** (правки и попытки от имени ядер делает помощник в шагах 3.1–3.4). Исключение —
  `sudo xgw net up` в «Если не так» шагов 3.2–3.4. Команды `tailscale`, `xray`, `sing-box`,
  `sstpc`, `pppd`, `sudo xgw pool …` (кроме `sudo xgw pool` без аргументов в шаге 1.3),
  `sudo xgw pin`, `sudo xgw unpin`, `sudo xgw probe` — **никогда**.
- Браузер, панель, сайты — в этой проверке не открывать.
- Править `/etc/xgw`, `/opt/xgw`, `/var/lib/xgw`, `/run/xgw`, `/etc/systemd`, код XGW. Печатать
  `config.toml`, `panel.json`, `status.json`, `capture.json`, рабочие конфиги Xray и sing-box,
  кэш подписок, `inventory.json`, базу `state.db`, полный вывод `nft list ruleset`, `nft list
  table`, `ip rule`, `ip route`. Коммитить что-либо, кроме файла отчёта (§6).
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, MAC, имена
  пользователей машины (→ `<user>`), внешние IP, адреса LAN-устройств, домены и ссылки серверов
  VPN, строки журнала. Можно: коды стран, теги вида `proxy-nl-8763`, имена служебных
  пользователей `xray` и `xgw-singbox`, права (`CAP_NET_ADMIN`), строки помощника, счётчики,
  статусы, времена.

## 1. Подготовка

Шаг 1.0. Предусловие — прошлая проверка закончена:

```bash
cd ~/zcod/xgw && git fetch -q && git log origin/freepool --format=%s | grep -ci 'волна 2 кросс-аудита'; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3; cd ~
```

Ожидается: `1` или больше (отчёт прошлой проверки); «0 timers listed».

Если не так: первая строка `0` — **стоп**, сообщить заказчику.

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю исправления по аудиту: (а) отдельный барьер — если чужая программа удалит правила
XGW, трафик дома не уйдёт мимо VPN; (б) sing-box работает от своего пользователя, без прав на
сеть машины. Режим бесплатных серверов не трогаю, дом всё время идёт через подписку. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд, соединения, открытые до установки, могут один раз оборваться.
Ядра останутся.
(2) Три тестовые правки правил самого XGW: убираю по одному его правилу и сразу проверяю, что
соединение с общедоступным адресом в интернете отбивается, а не идёт мимо VPN. Правило шлюз
возвращает сам: в двух случаях за секунды, в третьем — до 40 секунд, и всё это время интернета
дома нет. Ещё — проверки, что sing-box не может читать чужие файлы и менять правила сети (они
ничего не меняют).
(3) 10 минут наблюдения: я ничего не меняю, только читаю журнал и счётчики.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — пропустить §3 (кроме метки в конце шага 3.4). Против 3 —
пропустить шаг 4.1. **Запиши, на что согласился заказчик.**

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-w3" && chmod 700 "$HOME/xgw-w3" && cd "$HOME/xgw-w3" && cat > w3check.py <<'EOF'
"""XGW 0.2.0: волна 3 кросс-аудита (барьер inet xgw_guard, sing-box от своего пользователя) —
помощник проверки. Читает состояние XGW (/run/xgw/status.json, /var/lib/xgw/capture.json — только
наличие эталона и текст расхождения), таблицы nftables (счётчики барьера, число правил),
процессы ядер (/proc/PID/status), права на их конфиги и журнал со стандартного ввода
(journalctl -o short-unix). Меняет что-то только режим cut — по команде шага: убирает одно
своё правило XGW и ждёт, пока демон его вернёт. Режим isolation пробует от имени пользователей
ядер читать чужое и добавить правило ip rule (у них прав нет — ничего не меняется; если вдруг
добавится — убирает сразу). Адресов устройств и серверов не печатает. Время — секунды с 1970
(date +%s). Режимы: units, state, sub, sbstat [МЕТКА], guard, allow, cores, isolation,
cut output|table|rule, capstate, check, log [МЕТКА], sblog, ts, time."""
import grp
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
CHAIN = re.compile(r"^\s*chain (\w+) \{\n(.*?)^\s*\}", flags=re.MULTILINE | re.DOTALL)
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
        sys.exit(0)


def status_of(paths):
    loaded = read_json(paths.status_file)
    return loaded if isinstance(loaded, dict) else {}


def when(line):
    found = STAMP.match(line)
    return float(found.group(1)) if found else None


def guard_counts():
    """{цепочка: [счётчики правил отказа]} барьера; None — барьера нет; строка — ошибка."""
    code, out = run(["nft", "list", "table", *GUARD])
    if code != 0:
        return None if "No such file" in out else (out.strip().splitlines() or ["?"])[-1]
    return {name: [int(n) for n in re.findall(r"counter packets (\d+)", body)]
            for name, body in CHAIN.findall(out)}


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
    return name, (", ".join(rights) or "нет") + (f" и ещё {other:#x}" if other else "")


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
            return f"TCP {values[0]}, прочее {values[1]}" if values and len(values) >= 2 else "—"
        print(f"барьер: есть; цепочки: {', '.join(sorted(counts))}; отбито: машина {pair('output')}"
              f"; транзит {pair('transit')}; всего {total(counts)}")
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
    write = ("import os, sys\np = os.path.join(sys.argv[1], 'w3-test')\ntry:\n"
             "    open(p, 'x').close()\n    os.remove(p)\n    print('записал')\n"
             "except PermissionError:\n    print('отказ')\nexcept OSError as e:\n"
             "    print(type(e).__name__)")

    def py(user, code, arg):
        rc, out = run(["python3", "-I", "-c", code, str(arg)], user=user)
        return out.strip().splitlines()[-1] if out.strip() else f"код {rc}"

    xray_conf = paths.xray_config_dir / "config.json"
    print(f"sing-box → конфиг Xray: {py(SB_USER, read, xray_conf)}")
    print(f"sing-box → API Xray: {py(SB_USER, sock, '/run/xgw-xray/api.sock')}")
    print(f"sing-box → состояние XGW (/var/lib/xgw): {py(SB_USER, write, paths.var)}")
    code, out = run(["nft", "list", "tables"], user=SB_USER)
    print("sing-box → правила nftables: " + ("ПРОЧИТАЛ" if code == 0 else "отказ"
                                              if "not permitted" in out else f"код {code}"))
    rule = ["ip", "rule", "add", "from", TEST_NET, "lookup", "main", "pref", "49"]
    code, out = run(rule, user=SB_USER)
    if code == 0:
        run(["ip", "rule", "del", "from", TEST_NET, "lookup", "main", "pref", "49"])
        print("sing-box → правило ip rule: ДОБАВИЛ (сразу убрано)")
    else:
        print("sing-box → правило ip rule: " + ("отказ" if "not permitted" in out
                                                 else f"код {code}"))
    print(f"Xray → конфиг sing-box: {py('xray', read, paths.singbox_config_file)}")
elif mode == "cut":
    cfg, _paths = xgw()
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
        sys.exit(0)

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
        return any(isinstance(item, dict) and item.get("priority") == 100
                   and str(item.get("table")) == str(table) for item in rules)

    if not restored():
        print("правило и так не на месте — правку не делаю")
        sys.exit(0)
    before = guard_counts()
    label, argv = commands[what]
    code, out = run(argv)
    if code != 0:
        print(f"правка не сделана: {(out.strip().splitlines() or ['?'])[-1]}")
        sys.exit(0)
    began = time.monotonic()
    first = probe()
    after = guard_counts()
    back = None
    while time.monotonic() - began < 60:
        if restored():
            back = time.monotonic() - began
            break
        time.sleep(0.5)
    second = probe() if back is not None else "не проверялось"
    grown = (f"+{total(after) - total(before)}" if isinstance(after, dict)
             and isinstance(before, dict) else "барьера нет")
    print(f"{label}; соединение с адресом в интернете сразу после правки: {first}; барьер "
          f"отбил пакетов: {grown}")
    print("правило вернул демон через " + (f"{back:.1f} с" if back is not None
                                           else "— НЕ вернул за 60 с")
          + f"; соединение после возврата: {second}")
elif mode == "capstate":
    _cfg, paths = xgw()
    state = read_json(paths.var / "capture.json")
    state = state if isinstance(state, dict) else {}
    mismatch = state.get("mismatch") or ""
    print(f"эталон правил: {'есть' if state.get('baseline') else 'нет'}; расхождение с текстом "
          "правил: " + (mismatch if mismatch else "нет"))
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
python3 -c "import hashlib;d=open('w3check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `3ef5da75fc86fe66`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки (здесь ещё прежний код):

```bash
cd "$HOME/xgw-w3" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units state sub sbstat guard allow cores isolation check; do sudo python3 -I w3check.py $m; done 2>&1 | tee -a before.txt
```

Ожидается (записать **целиком** строки помощника):
- `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4; первая строка `xgw pool` —
  «Бесплатный пул: выключен; …»; пять служб `active`; `sub` — «выбран вручную: …» — записать;
- `sbstat` — «sing-box: отвечает: да; серверов через него: N; участников на sing-box: A (живы
  B); …» — **записать N, A, B**;
- `guard` — «барьер: нет»; `allow` — «правил с битом барьера в ip xgw: 0 (бит 0x20000000: нет);
  правил с пользователем sing-box: 0»;
- `cores` — «Xray: пользователь xray, права: CAP_NET_BIND_SERVICE, CAP_NET_ADMIN», «sing-box:
  пользователь xray, права: CAP_NET_BIND_SERVICE, CAP_NET_ADMIN»; оба конфига «root:xray 640»;
  «routing_mark в конфиге sing-box: K» (K больше 0) — записать;
- `isolation` — «пользователя xgw-singbox нет»;
- `check` — «проверка правил: True за X с; повторно: True за Y с» — записать X и Y.

Если не так: режим пула `on` — **стоп**, сообщить заказчику. `sing-box: … не работает` или
«отвечает: нет» — записать; в шаге 2.3 строки о sing-box сравнивать не с чем, остальное —
выполнять.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def render_guard' src/xgw/net/nft.py && grep -q '^User=xgw-singbox' packaging/xgw-singbox.service && echo "правка в коде: есть"; cd "$HOME/xgw-w3"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-w3/install-time.txt" && date +%s > "$HOME/xgw-w3/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-w3/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'пользователь xgw-singbox|sing-box перезапущен|Ядро|демон xgw|Установка не начата' "$HOME/xgw-w3/install.txt"; cd "$HOME/xgw-w3"
```

Ожидается: «код 0», «✓ пользователь xgw-singbox», «sing-box перезапущен: файл его службы
изменился», «демон xgw запущен».

Если не так: «Установка не начата» и строка «Ядро: … не принимает правила» — **дефект «ядро не
принимает барьер»**: записать строку `Ядро` целиком, **стоп**, сообщить заказчику (сеть не
менялась). Код не 0 по другой причине — **стоп**, сохранить вывод, сообщить заказчику (сеть не
откатывать). Нет строки «sing-box перезапущен» — записать «не по ожиданию», продолжать.

Шаг 2.3. Через 90 секунд — барьер, ядра и журналы после установки:

```bash
cd "$HOME/xgw-w3" && sleep 90; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^sing-box|Ожидает окна' | tee after-install.txt; for m in units state sub guard allow cores capstate check; do sudo python3 -I w3check.py $m; done 2>&1 | tee -a after-install.txt; sudo python3 -I w3check.py sbstat "$(cat t-install.txt)" | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log | tee log-install.txt; sudo journalctl -u xgw-singbox --since "$(cat install-time.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py sblog | tee -a log-install.txt; sudo xgw diag 2>&1 | grep -E 'Ядро|Перехват|Барьер|Пользователи ядер|Эталон правил' | tee -a after-install.txt
```

Ожидается (записать **целиком**):
- `HEALTHY`, перехват включён, «sing-box …: работает, серверов через него: N» (N — как в шаге
  1.3); строки «Ожидает окна перезапуска» нет; пять служб `active`; `sub` — как в шаге 1.3;
- **`guard` — «барьер: есть; цепочки: forward, output, pass, transit; отбито: машина TCP …,
  прочее …; транзит TCP …, прочее …; всего G»** — записать G (может быть больше 0: соединения,
  открытые до установки);
- `allow` — «правил с битом барьера в ip xgw: 1 или больше (бит 0x20000000: есть); правил с
  пользователем sing-box: 2»;
- **`cores` — «Xray: пользователь xray, права: CAP_NET_BIND_SERVICE, CAP_NET_ADMIN»; «sing-box:
  пользователь xgw-singbox, права: нет»; «конфиг Xray: root:xray 640 (каталог root:xray 2750);
  конфиг sing-box: root:xgw-singbox 640 (каталог root:xgw-singbox 2750)»; «routing_mark в
  конфиге sing-box: 0»**;
- `capstate` — «эталон правил: есть; расхождение с текстом правил: нет»; `check` — `True`,
  записать X и Y;
- `sbstat` — «sing-box: отвечает: да; серверов через него: N; участников на sing-box: A (живы
  B′); …» — записать (B′ — не меньше B из шага 1.3, если серверы не менялись);
- журнал XGW: «загрузок правил заново: 0» (или 1); «барьер держит: 0»; «барьер не загружен: 0»;
  «не сходятся с текстом правил: 0»; «ошибок загрузки правил: 0»; «Traceback: 0»;
- **журнал sing-box: «operation not permitted: 0»; «permission denied: 0»; «FATAL: 0»**;
- `xgw diag` — «OK Ядро: … и барьер»; «OK Перехват: включён, правила загружены»; **«OK Барьер:
  держит: …»**; **«OK Пользователи ядер: sing-box — от своего пользователя, без прав на сеть
  машины»**; строки «Эталон правил» нет.

Если не так: `guard` — «барьер: нет» или `xgw diag` «FAIL Барьер» — **дефект «барьер не
загружен»**: записать строки «Барьер» и счётчик «барьер не загружен», продолжать (§3 всё равно
выполнять — он покажет, отбивается ли соединение). `cores` — sing-box от `xray` или «права» не
«нет» — **дефект «sing-box не отделён»**. В журнале sing-box «operation not permitted» больше 0
или «отвечает: нет» — **дефект «sing-box без прав не работает»**: подождать 2 минуты, повторить
`sudo python3 -I w3check.py sbstat "$(cat t-install.txt)"`, записать оба вывода. Живых участников
на sing-box меньше, чем в шаге 1.3, — записать «не по ожиданию» (сервер мог и правда умереть).

## 3. Проверки (если заказчик согласился на пункт 2)

Шаг 3.1. Изоляция ядер — попытки от имени sing-box и Xray (ничего не меняют):

```bash
cd "$HOME/xgw-w3" && sudo python3 -I w3check.py isolation | tee r-31.txt
```

Ожидается — шесть строк, **везде «отказ»**:
«sing-box → конфиг Xray: отказ», «sing-box → API Xray: отказ», «sing-box → состояние XGW
(/var/lib/xgw): отказ», «sing-box → правила nftables: отказ», «sing-box → правило ip rule:
отказ», «Xray → конфиг sing-box: отказ».

Если не так: в любой строке «прочитан», «подключился», «записал», «ПРОЧИТАЛ» или «ДОБАВИЛ
(сразу убрано)» — **дефект «изоляция ядер»**: записать строку целиком. Другое слово (например,
`FileNotFoundError`) — записать «не по ожиданию».

Шаг 3.2. Опустошить цепочку меток трафика самой машины:

```bash
cd "$HOME/xgw-w3" && date +%s > t-32.txt && sudo python3 -I w3check.py cut output | tee r-32.txt; sleep 5; for m in guard capstate check; do sudo python3 -I w3check.py $m; done 2>&1 | tee -a r-32.txt; sudo journalctl -u xgw --since "@$(cat t-32.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log "$(cat t-32.txt)" | tee -a r-32.txt
```

Ожидается:
- **«цепочка output (метки трафика машины) опустошена; соединение с адресом в интернете сразу
  после правки: отбито (сброс) за 0.0X с; барьер отбил пакетов: +1»** (или больше);
- «правило вернул демон через T с» (T — до 10) — **записать T**; «соединение после возврата:
  соединилось за … с»;
- `guard` — «всего» больше, чем в шаге 2.3; `capstate` — «эталон правил: есть; расхождение …:
  нет»; `check` — `True`;
- журнал: «загрузок правил заново: 1»; «Traceback: 0».

Если не так: сразу после правки «соединилось» — **дефект «барьер пропустил соединение»** (без
барьера оно ушло бы мимо VPN): записать обе строки `cut` целиком. «нет ответа за 3 с» — записать
«не по ожиданию» (барьер должен отбивать сразу). «НЕ вернул за 60 с» — выполнить `sudo xgw net
up`, записать её вывод и **дефект «демон не вернул правило»**. «правило и так не на месте» —
записать, выполнить `sudo xgw net up`, повторить шаг один раз.

Шаг 3.3. Удалить таблицу перехвата `ip xgw` целиком:

```bash
cd "$HOME/xgw-w3" && date +%s > t-33.txt && sudo python3 -I w3check.py cut table | tee r-33.txt; sleep 5; for m in guard capstate check; do sudo python3 -I w3check.py $m; done 2>&1 | tee -a r-33.txt; sudo journalctl -u xgw --since "@$(cat t-33.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log "$(cat t-33.txt)" | tee -a r-33.txt
```

Ожидается: **«таблица ip xgw удалена; соединение … сразу после правки: отбито (сброс) …; барьер
отбил пакетов: +1»** (или больше); «правило вернул демон через T с» (T — до 10) — **записать
T**; «соединение после возврата: соединилось …»; `capstate`, `check` — как в шаге 3.2; журнал —
«загрузок правил заново: 1»; «Traceback: 0».

Если не так: как в шаге 3.2.

Шаг 3.4. Удалить правило маршрутизации XGW (pref 100) — его демон замечает на ближайшем шаге,
до 40 секунд; всё это время интернета дома нет:

```bash
cd "$HOME/xgw-w3" && date +%s > t-34.txt && sudo python3 -I w3check.py cut rule | tee r-34.txt; sleep 5; for m in guard capstate check; do sudo python3 -I w3check.py $m; done 2>&1 | tee -a r-34.txt; sudo journalctl -u xgw --since "@$(cat t-34.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log "$(cat t-34.txt)" | tee -a r-34.txt; date +%s > t-watch.txt
```

Ожидается: **«правило ip rule XGW (pref 100) удалено; соединение … сразу после правки: отбито
(сброс) …; барьер отбил пакетов: +1»** (или больше); «правило вернул демон через T с» (T — до 40)
— **записать T**; «соединение после возврата: соединилось …»; `capstate`, `check` — как в шаге
3.2; журнал — «загрузок правил заново: 1»; «Traceback: 0».

Если не так: как в шаге 3.2.

Если заказчик **не** согласился на пункт 2 — выполни только это, чтобы была метка наблюдения:

```bash
cd "$HOME/xgw-w3" && date +%s > t-watch.txt && echo "метка записана"
```

## 4. Наблюдение (если заказчик согласился на пункт 3)

Шаг 4.1. 10 минут без правок — барьер не должен отбить ни одного пакета:

```bash
cd "$HOME/xgw-w3" && sudo python3 -I w3check.py guard | tee guard-start.txt; sleep 600; sudo python3 -I w3check.py guard | tee guard-end.txt; sudo journalctl -u xgw --since "@$(cat t-watch.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py log "$(cat t-watch.txt)" | tee log-watch.txt; sudo journalctl -u xgw-singbox --since "@$(cat t-watch.txt)" -o short-unix --no-pager | sudo python3 -I w3check.py sblog | tee -a log-watch.txt; sudo python3 -I w3check.py sbstat "$(cat t-install.txt)" | tee -a log-watch.txt; for m in state ts time capstate check; do sudo python3 -I w3check.py $m; done 2>&1 | tee -a log-watch.txt
```

(Если терминал обрывает длинные команды — первая команда с `guard-start.txt`, затем `sleep 110`
5 раз и `sleep 50`, затем остальное без `sleep`.)

Ожидается (записать **целиком**):
- **«всего» в `guard-end.txt` — то же число, что в `guard-start.txt`** (главная проверка:
  законный трафик барьер не трогает);
- журнал XGW: «загрузок правил заново: 0»; «барьер держит: 0»; «Traceback: 0»; журнал sing-box —
  все три счётчика `0`;
- `sbstat` — «отвечает: да»; участники на sing-box живы, как в шаге 2.3; «проверены после
  метки: …» — записать;
- `HEALTHY`; «Tailscale: Running; в сети: да»; «время синхронизировано: yes»; `capstate` —
  «эталон правил: есть; расхождение … нет»; `check` — `True`.

Если не так: «всего» выросло — **дефект «барьер отбивает законный трафик»**: записать обе строки
`guard` (по ним видно, машина или транзит, TCP или прочее). «Tailscale: …» не Running или «в
сети: нет» — **дефект «Tailscale за барьером»**. «время синхронизировано: no» — записать «не по
ожиданию». «загрузок правил заново» больше 0 — **дефект «загрузка правил по кругу»**.

## 5. Итог

Шаг 5.1. Секреты и итог:

```bash
cd "$HOME/xgw-w3" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt; date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units state sub guard cores; do sudo python3 -I w3check.py $m; done 2>&1 | tee -a final.txt
```

Ожидается: `0`; `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4, строки «Ожидает
окна перезапуска» нет; пять служб `active`; режим пула и «выбран вручную» — как в шаге 1.3;
барьер есть; sing-box — от `xgw-singbox`, «права: нет».

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- Пропал интернет или доступ дольше 60 секунд, или заказчик не отвечает **2 минуты** —
  **сразу**: `sudo xgw net up`; если `systemctl is-active xgw` — не `active`, то `sudo systemctl
  start xgw`; подожди 30 секунд. Записать время и строки `sudo python3 -I w3check.py state` и
  `sudo xgw status 2>&1 | head -5` (без имён). Дальше — §5 и отчёт.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.

## 6. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3-<ДАТА>.md` в клоне (`<ДАТА>` — дата начала
проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, волна 3 кросс-аудита» и `git push` в
`freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и подписок,
адресов, доменов и строк журнала. Шаблон (заполни каждую ячейку; пропущенное — «не
выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — волна 3 кросс-аудита: барьер и отдельный пользователь sing-box

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
w3check.py: <сумма>. Режим пула до проверки: <…>. Ядра: Xray <…>, sing-box <…>. Исполнитель:
<модель>.

## Итог
| Барьер после установки (есть; отбито G) | sing-box: пользователь; права; routing_mark | Изоляция (из 6 — «отказ») | output: сразу; вернул, с | ip xgw: сразу; вернул, с | ip rule: сразу; вернул, с | Барьер отбил за 10 мин | Загрузок правил за 10 мин | sing-box: живых участников до → после |
|---|---|---|---|---|---|---|---|---|
| <есть; 0> | <xgw-singbox; нет; 0> | <6> | <отбито; 1.2> | <отбито; 1.5> | <отбито; 21> | <0> | <0> | <2 → 2> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.0 предусловие | … | … |
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 изоляция ядер | … | … |
| 3.2 опустошена output | … | … |
| 3.3 удалена ip xgw | … | … |
| 3.4 удалено ip rule | … | … |
| 4.1 наблюдение 10 мин | … | … |
| 5 итог | … | … |

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-w3/…); строки xgw diag «Ядро», «Перехват»,
  «Барьер», «Пользователи ядер», «Эталон правил»; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
