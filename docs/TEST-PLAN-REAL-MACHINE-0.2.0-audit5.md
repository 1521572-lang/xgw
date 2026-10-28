# Проверка XGW 0.2.0: правки по пятому аудиту

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-020f/…`). Файл помощника создавай только командой шага 1.2, выполненной в терминале.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `audit5`, версия 0.2.0. Сейчас на машине стоит 0.2.0 с
коммита d327aa4 (ветка `audit4`, теперь она в `main`); её проверка пройдена, отчёт
`docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit4-2026-10-27.md`. Телефон — S25 Ultra в домашней сети,
на нём приложение XGW. Команды — в терминале сеанса заказчика (`sudo` от его имени).

Что изменено (ASSUMPTIONS п. 254):
1. **Дефект прошлого отчёта.** Обрыв соединения клиентом больше не пишет трассировку
   (Traceback) в журнал; запрос, не дочитанный за срок, закрывается без ответа.
2. **Панель** — как API приложения: не больше 32 соединений сразу и срок на чтение запроса
   (20 с). Запись трафика скачивается кусками и не больше двух сразу.
3. **Подписки.** Один узел sing-box с неверными портами больше не роняет всю подписку; узел с
   неизвестным транспортом пропускается (раньше превращался в tcp). Серверы, которые отличаются
   только путём, SNI или режимом XHTTP, больше не схлопываются как дубли. Если первый адрес
   сервера подписки принимает соединение, но не отвечает (так ТСПУ душит отдельные адреса),
   следующая попытка идёт на другой адрес. У каждого адреса в кэше адресов подписок — свой срок.
4. **XHTTP с отдельным каналом загрузки** получает метку обхода и у этого канала — без неё его
   соединение снова попадало в перехват.
5. **Ложное «все серверы мертвы»**, когда через серверы не открываются только probe.url и
   Cloudflare trace, а другие проверочные адреса открываются, — больше нет; проверка идёт
   одновременно через всех участников.
6. **Правило маршрутизации** XGW проверяется вместе с приоритетом: сдвинутое (например, за
   main) — ставится на место. События правил в окне своей загрузки и после перезапуска
   `nft monitor` — одна проверка, а не пропуск.
7. Вход телефона: чужие неверные коды QR не гасят; предел запросов — до записи отметки; если
   отметку записать нельзя, команды телефона не выполняются. Ответ API Xray — с пределом.
   diag предупреждает о `fail_mode = open`, подписке по http и чужой flowtable.

Здесь, у разработчика (Ubuntu 26.04), — юнит-тесты, опыты с Xray 26.10.21 (метка у канала
загрузки XHTTP) и sing-box 1.14.3 (формат `server_ports`), поколение правил по netlink. На
этой машине — всё остальное.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list` и `nft -t list`), `ip`, `iptables`, `tc`, `sysctl -w`,
  `systemd-run`; команды `tailscale` и `xray`. Исключения — только то, что запускает помощник:
  `tailscale status --json` (печатает только состояние), `ip -j rule show` (только читает),
  запросы к API приложения и к панели на 127.0.0.1 в §4 и §5 (без входа — шлюз их отклоняет или
  закрывает).
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/etc/systemd`, код XGW. Печатать `config.toml` (`cat`, `less`, `grep` по нему) — в нём ключи
  подписок. Серверы, переключатели и кнопки в панели и в приложении меняет и нажимает только
  заказчик. Коммитить что-либо, кроме отчёта (§9).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP и домены серверов
  VPN, строки журнала, имена файлов записи. Можно: адреса устройств в домашней сети
  (`192.168.…`), названия и страны серверов, имена программ, проверок и служб, счётчики, права
  файлов, размеры, времена.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю правки XGW по пятому аудиту. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд.
(2) В панели XGW по моей просьбе: нажмёте «Проверить сеть» два раза (до и после установки),
«Обновить» над подписками; запишете полминуты трафика телефона и скачаете файл записи. На
секунду страница панели может показать, что нет связи, — это проверка.
(3) Телефон: по моей просьбе дважды по 1–2 минуты не открывать приложение XGW, а потом открыть
его и сказать, показывает ли оно состояние шлюза. В конце откроете любой сайт на этом
компьютере и на телефоне.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — шаги 1.3, §6, 7.2 и 8.1 пропустить; против 3 — §4 и
шаг 8.2. В отчёте у пропущенного — «не выполнялся».

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-020f" && chmod 700 "$HOME/xgw-020f" && cd "$HOME/xgw-020f" && cat > v020fcheck.py <<'EOF'
"""XGW 0.2.0, пятый аудит: помощник проверки. Читает /proc, правила маршрутизации (`ip -j rule
show`), поколение правил nftables (netlink, только чтение), состояние XGW (/run/xgw,
/var/lib/xgw — только счётчики и да/нет, без адресов и имён), журнал со стандартного ввода
(только счётчики). Кроме чтения: phone-lock и phone-limits — запросы без подписи и пустые
соединения к API приложения на 127.0.0.1; panel-limits — пустые соединения к панели на
127.0.0.1. Режимы: units, rules, gen, digest, phone-lock, phone-limits, panel-limits, records,
cache, inventory, xhttp, subs, netcheck, ts, log."""
import http.client
import json
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = "/opt/xgw/lib"


def show(unit, prop):
    return subprocess.run(["systemctl", "show", "-p", prop, "--value", unit],
                          capture_output=True, text=True).stdout.strip()


def run_mount(pid):
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


def empty_connections(port, count):
    socks = [socket.create_connection(("127.0.0.1", port), timeout=5) for _ in range(count)]
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
    return closed


def slow_request(port, first_line):
    slow = socket.create_connection(("127.0.0.1", port), timeout=5)
    slow.sendall(first_line + b"\r\nX-Slow: ")
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
    return f"сервер закрыл через {cut:.0f} с" if cut else "сервер не закрыл за 45 с"


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
        print(f"{unit}: {show(unit, 'ActiveState')}, Seccomp {found['Seccomp']}, NoNewPrivs "
              f"{found['NoNewPrivs']}, /run {run_mount(pid) if pid != '0' else '-'}")
elif mode == "rules":
    cfg, _paths = xgw()
    cap = cfg.capture
    wanted = {
        (cap.mark_proxy, str(cap.route_table), None): 100,
        (cap.mark_proxy, str(cap.tun_route_table), "lo"): 90,
        (cap.mark_containers, str(cap.tun_route_table), None): 95,
    }
    total = moved = extra = 0
    for family, flag in ((4, []), (6, ["-6"])):
        done = subprocess.run(["ip", *flag, "-j", "rule", "show"], capture_output=True,
                              text=True, timeout=15)
        try:
            listing = json.loads(done.stdout or "[]")
        except ValueError:
            print(f"IPv{family}: ответ ip rule не JSON")
            continue
        seen = {}
        for rule in listing:
            try:
                mark = int(str(rule.get("fwmark", "")), 16)
            except ValueError:
                continue
            key = (mark, str(rule.get("table")), rule.get("iif"))
            if key not in wanted:
                continue
            total += 1
            seen[key] = seen.get(key, 0) + 1
            prio = rule.get("priority")
            selectors = [name for name in ("fwmask", "dst") if name in rule]
            if rule.get("src", "all") != "all":
                selectors.append("src")
            note = "" if prio == wanted[key] else f" — должен быть {wanted[key]}"
            moved += prio != wanted[key]
            print(f"IPv{family}: fwmark {mark:#x}{' iif lo' if key[2] else ''} → таблица "
                  f"{key[1]}, приоритет {prio}{note}"
                  + (f", доп. условия: {', '.join(selectors)}" if selectors else ""))
        extra += sum(count - 1 for count in seen.values())
    print(f"правил XGW: {total}; с другим приоритетом: {moved}; повторов: {extra}")
elif mode == "gen":
    sys.path.insert(0, LIB)
    from xgw.net import nft

    first, second = nft.generation(), nft.generation()
    state = "читается" if isinstance(first, int) and isinstance(second, int) else "не читается"
    print(f"поколение правил nftables: {state} ({first}, {second})")
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
        print(f"20 соединений без запроса: сервер сразу закрыл {empty_connections(port, 20)}")
        time.sleep(1.0)
        print("запрос по байту раз в 3 с: " + slow_request(port, b"GET /api/hello HTTP/1.1"))
        print(f"/api/hello после этого: {hello()}; время: {time.strftime('%H:%M:%S')}")
elif mode == "panel-limits":
    cfg, _paths = xgw()
    port = cfg.panel.port

    def page():
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request("GET", "/", headers={"Host": f"127.0.0.1:{port}"})
            return f"ответила (код {conn.getresponse().status})"
        except OSError as exc:
            return f"не ответила ({type(exc).__name__})"
        finally:
            conn.close()

    print(f"40 соединений без запроса: панель сразу закрыла {empty_connections(port, 40)}")
    time.sleep(1.0)
    print("запрос по байту раз в 3 с: " + slow_request(port, b"GET / HTTP/1.1"))
    print(f"страница панели после этого: {page()}; время: {time.strftime('%H:%M:%S')}")
elif mode == "records":
    _cfg, paths = xgw()
    files = sorted(paths.records_dir.glob("*.pcap"), key=lambda path: path.stat().st_mtime)
    sizes = {path.stat().st_size for path in files}
    print(f"записей трафика на шлюзе: {len(files)}"
          + (f"; последняя: {files[-1].stat().st_size} байт" if files else ""))
    folder = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    got = sorted(folder.glob("xgw-*.pcap"), key=lambda path: path.stat().st_mtime) if folder else []
    if not got:
        print("скачанного файла xgw-….pcap в папке загрузок нет")
    else:
        newest = got[-1]
        head = newest.read_bytes()[:4]
        magic = head in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1",
                         b"\xa1\xb2\x3c\x4d")
        age = int(time.time() - newest.stat().st_mtime)
        print(f"скачанный файл: {newest.stat().st_size} байт, {age} с назад; размер как у записи "
              f"на шлюзе: {'да' if newest.stat().st_size in sizes else 'нет'}; заголовок pcap: "
              f"{'да' if magic else 'нет'}")
elif mode == "cache":
    _cfg, paths = xgw()
    data = read_json(paths.cache_dir / "dns-cache.json")
    if data is None:
        print("кэша адресов подписок нет")
    else:
        entries = [entry for entry in data.values() if isinstance(entry, dict)]
        ips = sum(len(entry.get("ips") or []) for entry in entries)
        own = sum(1 for entry in entries for ip in entry.get("ips") or []
                  if ip in (entry.get("seen") or {}))
        print(f"кэш адресов подписок: имён {len(entries)}, адресов {ips}, со своим сроком "
              f"(seen) {own}")
elif mode == "inventory":
    _cfg, paths = xgw()
    data = read_json(paths.var / "inventory.json") or {}
    servers = data.get("servers") or []
    print(f"серверов в списке: {len(servers)}; разных отпечатков: "
          f"{len({item.get('fingerprint') for item in servers})}")
elif mode == "xhttp":
    cfg, paths = xgw()
    conf = read_json(paths.xray_config_file) or {}
    counts = {"legs": 0, "marked": 0}

    def walk(stream, depth=0):
        if not isinstance(stream, dict) or depth > 4:
            return
        for key in ("xhttpSettings", "splithttpSettings"):
            settings = stream.get(key)
            if not isinstance(settings, dict):
                continue
            for options in (settings, settings.get("extra")):
                down = options.get("downloadSettings") if isinstance(options, dict) else None
                if isinstance(down, dict):
                    counts["legs"] += 1
                    sockopt = down.get("sockopt") if isinstance(down.get("sockopt"), dict) else {}
                    counts["marked"] += sockopt.get("mark") == cfg.capture.mark_bypass
                    walk(down, depth + 1)

    for outbound in conf.get("outbounds") or []:
        if isinstance(outbound, dict):
            walk(outbound.get("streamSettings"))
    print(f"XHTTP с отдельным каналом загрузки в применённом конфиге: {counts['legs']}; из них "
          f"с меткой обхода: {counts['marked']}")
elif mode == "subs":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    errors = status.get("sub_errors") or {}
    texts = [str((item or {}).get("error") or "") for item in errors.values()]
    print(f"подписок с ошибкой: {sum(1 for text in texts if text)}")
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
        ("API приложения: запрос отклонён", "API приложения: запрос отклонён"),
        ("клиент закрыл соединение раньше ответа", "закрыл соединение раньше ответа"),
        ("отметка запроса телефона не сохранена", "отметка запроса телефона не сохранена"),
        ("скачивание записи прервано", "скачивание записи прервано"),
        ("ответ xray api больше предела", "ответ xray api больше"),
        ("монитор событий перезапущен", "завершился — запускаю снова"),
        ("варианты серверов — не дубли", "не дубли"),
        ("узлы с неизвестным транспортом", "неизвестный транспорт"),
        ("узлы с неверным server_ports", "server_ports"),
        ("Read-only file system", "Read-only file system"),
        ("Permission denied", "Permission denied"),
        ("Operation not permitted", "Operation not permitted"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if text in line)}")
else:
    print("режим: units | rules | gen | digest | phone-lock | phone-limits | panel-limits | "
          "records | cache | inventory | xhttp | subs | netcheck | ts | log")
EOF
python3 -c "import hashlib;d=open('v020fcheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee before.txt; sudo python3 -I v020fcheck.py ts | tee -a before.txt; sudo xgw diag | grep -E 'Система:|Конфиг:|Файрвол:|Xray API|Итог' | tee diag-before.txt; sudo python3 -I v020fcheck.py rules | tee rules-before.txt; sudo python3 -I v020fcheck.py gen | tee -a rules-before.txt; for m in inventory cache subs xhttp; do sudo python3 -I v020fcheck.py $m; done | tee subs-before.txt; sudo journalctl -u xgw --since "30 min ago" --no-pager | sudo python3 -I v020fcheck.py log | tee log-before.txt
```

Ожидается:
- `79d8346afdf66472`;
- `Состояние: HEALTHY …`, `Перехват: включён …`, строки `Xray …` и `sing-box …`,
  `Tailscale: Running` — записать как есть;
- строки diag `Система`, `Конфиг`, `Файрвол`, `Xray API`, `Итог: …` — записать как есть;
- правила: строки «IPv4: fwmark 0x1 → таблица 100, приоритет 100» (и, если есть, ещё строки
  XGW) и итог «правил XGW: N; с другим приоритетом: 0; повторов: 0»; «поколение правил
  nftables: читается (…)» — записать;
- «серверов в списке: N; разных отпечатков: M», «кэш адресов подписок: …» (или «кэша … нет»),
  «подписок с ошибкой: …», «XHTTP с отдельным каналом загрузки …: K; из них с меткой обхода: L»
  — записать как есть (с ними сравнивается §7);
- счётчики журнала за 30 минут — записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать (это до установки) и продолжить.

Шаг 1.3 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В панели XGW нажмите кнопку «Проверить сеть» и подождите, пока под ней появится итог (до
15 секунд). Скажите, когда появится.»

После ответа:

```bash
cd "$HOME/xgw-020f" && sudo python3 -I v020fcheck.py netcheck | tee netcheck-before.txt
```

Ожидается: «проверка сети (<время сейчас>): OK — …, WARN — …, FAIL — …» и список проверок.
Записать. Время не сегодняшнее — попросить нажать ещё раз и повторить команду.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout audit5 && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q '^class BoundedServer' src/xgw/watch/httpbound.py && grep -q 'def _download_legs' src/xgw/generator/builder.py && grep -q 'def split_variants' src/xgw/model.py && grep -q 'def _port_ranges' src/xgw/parsers/sbjson.py && grep -q 'def _ensure_rule' src/xgw/net/iprule.py && grep -q 'class NonceStoreError' src/xgw/phones.py && grep -q '^def bounded_run' src/xgw/xraycore/api.py && grep -q 'def send_file' src/xgw/watch/record.py && grep -q 'def untried' src/xgw/fetch.py && grep -q '^QUEUE_MAX' src/xgw/watch/events.py && echo "правка в коде: есть"; cd "$HOME/xgw-020f"
```

Ожидается: «правка в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-020f/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-020f/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|Xray запущен' "$HOME/xgw-020f/install.txt"; cd "$HOME/xgw-020f"
```

Ожидается: «код 0», «демон xgw запущен», «Xray запущен: участников …». Строки «… перезапущен»
могут быть, а могут и не быть. Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке:

```bash
sleep 120; cd "$HOME/xgw-020f" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee after-install.txt; sudo python3 -I v020fcheck.py ts | tee -a after-install.txt; sudo python3 -I v020fcheck.py units | tee -a after-install.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray отвечает, строка sing-box — как до установки;
`Tailscale: …` — как в §1.2; четыре службы `active` (sing-box — как до установки), у всех
`/run только чтение`. Записать.

Если не так: не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать `sudo
systemctl is-active xgw xgw-xray xgw-singbox xgw-dhcp | tee active.txt`, сообщить заказчику и
продолжить.

## 3. Правила и diag

Шаг 3.1. Правила маршрутизации и поколение правил nftables:

```bash
cd "$HOME/xgw-020f" && sudo python3 -I v020fcheck.py rules | tee rules-after.txt; sudo python3 -I v020fcheck.py gen | tee -a rules-after.txt; sudo python3 -I v020fcheck.py digest | tee digest.txt
```

Ожидается:
- те же строки правил, что в `rules-before.txt`; «с другим приоритетом: 0; повторов: 0»;
- «поколение правил nftables: читается (…)»;
- «отпечаток таблиц: совпадает; правила на месте (loaded): True; время: …».

Записать.

Если не так: «с другим приоритетом» или «повторов» больше 0 — **дефект «правило
маршрутизации не на месте»**: записать строки; «не читается» — **дефект «поколение правил не
читается»** (проверка правил тогда идёт без него — медленнее, но работает); отпечаток «НЕ
совпадает» или `False` — повторить через минуту, снова так — **дефект «отпечаток таблиц
меняется сам»**. Продолжить.

Шаг 3.2. diag:

```bash
cd "$HOME/xgw-020f" && sudo xgw diag | grep -E 'Система:|Конфиг:|Файрвол:|Xray API|Итог' | tee diag-after.txt; sudo xgw diag | grep -ciE 'flowtable|fail_mode|подписка по http' | sed 's/^/строк diag о flowtable, fail_mode, http: /' | tee -a diag-after.txt
```

Ожидается: `Система`, `Xray API` — OK; `Итог: …, FAIL — 0`; строк о flowtable, fail_mode и
http — 0 (если есть — записать их уровень и смысл без адресов: это настройки машины, а не
дефект). Записать.

Если не так: FAIL, которого не было в `diag-before.txt`, — **дефект «diag после правок»**:
записать строку без адресов.

## 4. API приложения (при согласии на пункт 3)

Шаг 4.1. **Попроси заказчика** (дословно):

«Не открывайте приложение XGW на телефоне, пока я не попрошу (около минуты). Скажите, когда
оно закрыто.»

После ответа:

```bash
cd "$HOME/xgw-020f" && date '+%F %T' | tee phone-time.txt && sudo python3 -I v020fcheck.py phone-lock | tee lock.txt
```

Ожидается (около 10 секунд): «ответы на 12 запросов без подписи: 403×10, 429×2» и
«/api/hello: 200; время: …». Сразу после этого **попроси заказчика** (дословно):

«Откройте приложение XGW на телефоне. Показывает ли оно состояние шлюза (серверы, состояние), а
не ошибку?»

Записать строки и ответ дословно.

Если не так: приложение показывает ошибку — **дефект «вход телефона после правок»**: записать
ответ, продолжить. Ответы не «403×10, 429×2» — записать как есть (наблюдение).

Шаг 4.2. **Попроси заказчика** (дословно):

«Закройте приложение XGW на телефоне и не открывайте полторы минуты. Скажите, когда закрыто.»

После ответа:

```bash
cd "$HOME/xgw-020f" && sudo python3 -I v020fcheck.py phone-limits | tee limits.txt; sleep 5; sudo journalctl -u xgw --since "$(cat phone-time.txt)" --no-pager | sudo python3 -I v020fcheck.py log | grep -E 'Traceback|закрыл соединение|отметка' | tee -a limits.txt
```

Ожидается (около 30 секунд): «20 соединений без запроса: сервер сразу закрыл 4», «запрос по
байту раз в 3 с: сервер закрыл через N с», N — от 18 до 25, «/api/hello после этого: 200»;
«Traceback: 0» — **главная проверка дефекта прошлого отчёта**; «клиент закрыл соединение
раньше ответа: …» — любое число; «отметка запроса телефона не сохранена: 0». Затем **попроси
заказчика** (дословно): «Откройте приложение XGW снова — работает?»

Записать строки и ответ.

Если не так: «Traceback» больше 0 — **дефект «трассировка при обрыве клиентом»**: записать
`sudo journalctl -u xgw --since "$(cat phone-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -20 | tee traceback-phone.txt`
(только строки с файлами и ошибкой); «сразу закрыл 0» — **дефект «нет предела соединений»**;
«не закрыл за 45 с» — **дефект «медленный запрос не обрывается»**; приложение не работает —
**дефект «API приложения не отвечает после проверки»**. Продолжить.

## 5. Пределы панели

Шаг 5.1. Пустые соединения и медленный запрос к панели (как от чужого по tailnet):

```bash
cd "$HOME/xgw-020f" && date '+%F %T' | tee panel-time.txt && sudo python3 -I v020fcheck.py panel-limits | tee panel-limits.txt; sleep 5; sudo journalctl -u xgw --since "$(cat panel-time.txt)" --no-pager | sudo python3 -I v020fcheck.py log | grep -E 'Traceback|закрыл соединение' | tee -a panel-limits.txt
```

Ожидается (около 30 секунд): «40 соединений без запроса: панель сразу закрыла N», N — от 8
до 12 (открытая вкладка панели может занимать пару мест); «запрос по байту раз в 3 с: сервер
закрыл через N с», N — от 18 до 25; «страница панели после этого: ответила (код …)» — любой
код; «Traceback: 0». Записать.

Если не так: «сразу закрыла 0» — **дефект «у панели нет предела соединений»**; «не закрыл за
45 с» — **дефект «медленный запрос к панели не обрывается»**; «не ответила» — **дефект
«панель не отвечает после проверки»**: сообщить заказчику; Traceback больше 0 — как в шаге 4.2
(`traceback-panel.txt`, `--since "$(cat panel-time.txt)"`).

Шаг 5.2 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«Обновите страницу панели XGW (F5). Открывается и показывает серверы?»

Ожидается: «да». Записать ответ дословно. Нет — **дефект «панель не открывается после
проверки»**, сообщить заказчику.

## 6. Запись трафика (при согласии на пункт 2)

Шаг 6.1. **Попроси заказчика** (дословно):

«В панели XGW, в списке устройств домашней сети, у телефона нажмите круглую кнопку записи
(подсказка «Записать трафик …») и подтвердите «Записать». Через полминуты нажмите у него же
кнопку остановки. Затем у появившейся записи нажмите «Скачать запись» и сохраните файл в
папку загрузок. Скажите, когда файл скачается.»

После ответа:

```bash
cd "$HOME/xgw-020f" && sudo python3 -I v020fcheck.py records "$(xdg-user-dir DOWNLOAD)" | tee records.txt
```

Ожидается: «записей трафика на шлюзе: N; последняя: … байт» (N — 1 или больше);
«скачанный файл: … байт, … с назад; размер как у записи на шлюзе: да; заголовок pcap: да»
(«с назад» — меньше 300). Записать.

Если не так: «размер … нет» или «заголовок pcap: нет» — **дефект «запись скачивается не
целиком»**; файла нет — спросить заказчика, куда сохранился, и повторить команду с этой
папкой вместо `$(xdg-user-dir DOWNLOAD)`; в панели ошибка — записать её текст без адресов.

## 7. Подписки

Шаг 7.1. Не раньше чем через 5 минут после шага 3.1 — отпечаток таблиц не меняется сам:

```bash
cd "$HOME/xgw-020f" && cat digest.txt; sudo python3 -I v020fcheck.py digest | tee -a digest.txt
```

Ожидается: снова «совпадает; … True», время — на 5 минут и больше позже. Если не так — как в
шаге 3.1.

Шаг 7.2 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В панели XGW нажмите «Обновить» над списком подписок. Скажите, когда нажали.»

Через 90 секунд после ответа:

```bash
sleep 90; cd "$HOME/xgw-020f" && for m in inventory cache subs xhttp; do sudo python3 -I v020fcheck.py $m; done | tee subs-after.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020fcheck.py log | grep -E 'не дубли|неизвестным|server_ports' | tee -a subs-after.txt
```

Ожидается:
- «серверов в списке» — не меньше, чем в `subs-before.txt`, за вычетом чисел «узлы с
  неизвестным транспортом» и «узлы с неверным server_ports» (такие узлы теперь пропускаются);
  больше — может быть («варианты серверов — не дубли»);
- «подписок с ошибкой» — не больше, чем до установки;
- «кэш адресов подписок»: «со своим сроком (seen)» — любое число (запись обновляется при
  прямой загрузке, не каждый раз);
- «XHTTP с отдельным каналом загрузки …: K; из них с меткой обхода: K» (оба числа равны; 0 и 0
  — у подписок такого нет).

Записать все строки.

Если не так: серверов стало меньше сверх этих чисел — **дефект «серверы пропали после
правок»**: записать оба числа; ошибок подписок больше — **дефект «подписка не обновляется»**;
меток обхода меньше, чем каналов, — **дефект «канал загрузки XHTTP без метки»**.

## 8. После

Шаг 8.1 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В панели XGW снова нажмите «Проверить сеть» и подождите итог. Скажите, когда появится.»

После ответа:

```bash
cd "$HOME/xgw-020f" && sudo python3 -I v020fcheck.py netcheck | tee netcheck-after.txt
```

Ожидается: время — сейчас; те же проверки и уровни, что в шаге 1.3; FAIL — не больше. Если не
так: проверка, бывшая OK или WARN, стала FAIL — **дефект «проверка сети после правок»**:
записать её название и уровень.

Шаг 8.2 (при согласии на пункт 3). **Попроси заказчика** (дословно):

«Откройте любой сайт на этом компьютере и любой сайт на телефоне. Открываются?»

Ожидается: «да». Нет — записать ответ дословно и
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt`,
сообщить заказчику.

Шаг 8.3. Итог:

```bash
cd "$HOME/xgw-020f" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020fcheck.py log | tee final.txt; sudo python3 -I v020fcheck.py rules | tail -1 | tee -a final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee -a final.txt
```

Ожидается:
- «правила загружены заново: 0» или 1; «откат на last-good: 0»; «ошибка API Xray: 0»;
  «failed to dial: 0»;
- «API приложения: запрос отклонён: 10» (запросы шага 4.1; §4 не выполнялся — 0);
- «отметка запроса телефона не сохранена: 0»; «скачивание записи прервано: 0»; «ответ xray api
  больше предела: 0»;
- «монитор событий перезапущен», «клиент закрыл соединение раньше ответа», «варианты серверов —
  не дубли», «узлы с неизвестным транспортом», «узлы с неверным server_ports» — любые числа,
  записать;
- **«Traceback: 0»**; «Read-only file system», «Permission denied», «Operation not permitted» —
  не больше, чем в `log-before.txt`;
- «правил XGW: …; с другим приоритетом: 0; повторов: 0»;
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки.

Если не так: «правила загружены заново» больше 1 — **дефект «правила загружаются по кругу»**
(вместе с шагами 3.1 и 7.1); Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -30 | tee traceback.txt`
(только строки с файлами и ошибкой, адреса — убрать); остальные счётчики выше ожидаемого —
**дефект** с названием счётчика и числом. Сообщить заказчику.

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit5-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`audit5`), коммит «Отчёт: XGW 0.2.0, правки по пятому аудиту», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, правки по пятому аудиту

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
v020fcheck.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, diag, правила, поколение, серверы, кэш, подписки, XHTTP, журнал |
| 1.3 проверка сети до | — / не выполнялся | OK / WARN / FAIL |
| 2.2 установка | … | код, строки установки |
| 2.3 после установки | … | HEALTHY, Tailscale, службы и /run |
| 3.1 правила | … | приоритеты, повторы, поколение, отпечаток |
| 3.2 diag | … | Система, Конфиг, Файрвол, Xray API, Итог; строки flowtable/fail_mode/http |
| 4.1 чужие запросы и телефон | … / не выполнялся | ответы, приложение |
| 4.2 пределы API приложения | … / не выполнялся | закрыто сразу, через сколько секунд, Traceback, приложение |
| 5.1 пределы панели | … | закрыто сразу, через сколько секунд, страница, Traceback |
| 5.2 панель после | … / не выполнялся | ответ заказчика |
| 6.1 запись трафика | … / не выполнялся | записи, размер, заголовок pcap |
| 7.1 отпечаток таблиц | … | совпадает, loaded, время |
| 7.2 подписки | … / не выполнялся | серверы, ошибки, кэш, XHTTP до → после |
| 8.1 проверка сети после | … / не выполнялся | OK / WARN / FAIL до → после |
| 8.2 сайты | … / не выполнялся | ответ заказчика |
| 8.3 итог | … | счётчики журнала, правила, HEALTHY |

## Выводы шагов
<файлы $HOME/xgw-020f/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
