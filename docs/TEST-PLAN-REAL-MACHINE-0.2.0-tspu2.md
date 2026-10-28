# Проверка XGW 0.2.0: анти-ТСПУ 2.0, первый этап

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-020g/…`). Файл помощника создавай только командой шага 1.2, выполненной в терминале.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `tspu2`, версия 0.2.0. Сейчас на машине стоит 0.2.0 с
коммита eac8eb9 (ветка `audit5`); её проверка пройдена, отчёт
`docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit5-2026-10-28.md`. Телефон — S25 Ultra в домашней сети,
на нём приложение XGW. Команды — в терминале сеанса заказчика (`sudo` от его имени).

Что изменено (ASSUMPTIONS п. 255):
1. **Адрес сервера закрыт целиком.** Сервер не отвечает, а TCP к его адресу напрямую не
   открывается — значит, закрыт сам адрес, и никакой обход (дробление, другое ядро) не поможет.
   Такой сервер больше не перебирает профили обхода (раньше — до пяти ступеней с пересборкой
   конфига), а в работе меняется сразу. В панели у него пометка «адрес закрыт».
2. **Быстрая замена.** Сервер в работе «заморозился», а другие работают и есть проверенный
   запасной — его меняют сразу, а дробление проверяют на нём потом. Дробление на месте, как
   раньше, — только когда отказали больше половины серверов в работе (глушение по всей сети).
3. **Белые списки.** VPN не работает, российские адреса открываются напрямую, а зарубежные —
   нет: шлюз сам ничего не меняет, а пишет событие и предупреждение в панели с кнопкой
   «Включить» для сервера x100 (для белых списков). Дома белых списков нет — здесь проверяется,
   что ложной тревоги нет.
4. **Пробы без шаблона.** Собственная проба сервера качает случайную часть проверочного файла
   (от 40 000 байт до целого), а не всегда одни и те же 57 КБ.

Здесь, у разработчика, — юнит-тесты, стенд фаз отказа (только 127.0.0.1, Xray 26.10.21) и
панель на выдуманных данных (предупреждение о белых списках, кнопка, пометка «адрес закрыт»).
На этой машине — всё остальное.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list` и `nft -t list`), `ip`, `iptables`, `tc`, `sysctl -w`,
  `systemd-run`; команды `tailscale` и `xray`. Исключения — только то, что запускает помощник:
  `tailscale status --json` (печатает только состояние) и прямые TCP-соединения к проверочным
  хостам из настроек (шаг 5.1, как это делает сам шлюз).
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/etc/systemd`, код XGW. Печатать `config.toml` (`cat`, `less`, `grep` по нему) — в нём ключи
  подписок. Серверы, переключатели и кнопки в панели и в приложении меняет и нажимает только
  заказчик. Коммитить что-либо, кроме отчёта (§9).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP и домены серверов
  VPN, строки журнала, имена файлов записи. Можно: адреса устройств в домашней сети
  (`192.168.…`), названия и страны серверов, имена программ, проверок и служб, счётчики,
  размеры, времена.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю защиту XGW от ТСПУ, первый этап. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд.
(2) В панели XGW по моей просьбе: нажмёте «Проверить сеть» два раза (до и после установки),
один раз «Проверить запасные»; запишете полминуты трафика телефона и скачаете файл записи.
(3) Телефон: во время записи откроете на нём любой сайт; в конце откроете любой сайт на этом
компьютере и на телефоне.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — шаги 1.3, 4.1, §6 и 8.1 пропустить; против 3 — §6 и
шаг 8.2. В отчёте у пропущенного — «не выполнялся».

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-020g" && chmod 700 "$HOME/xgw-020g" && cd "$HOME/xgw-020g" && cat > v020gcheck.py <<'EOF'
"""XGW 0.2.0, анти-ТСПУ 2.0 (первый этап): помощник проверки. Читает состояние XGW (/run/xgw,
/var/lib/xgw — только счётчики и да/нет, без адресов и имён), журнал со стандартного ввода
(только счётчики). Кроме чтения: foreign — TCP-соединения напрямую (сокетом с меткой обхода)
к проверочным хостам из настроек, как это делает демон, распознавая белые списки; records —
сравнивает размер скачанного файла записи. Режимы: units, closed, whitelist, foreign, sizes,
records, digest, subs, netcheck, ts, log."""
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = "/opt/xgw/lib"
SCAN_RE = re.compile(r"скан \S+: (OK|SLOW), (\d+) байт")


def show(unit, prop):
    return subprocess.run(["systemctl", "show", "-p", prop, "--value", unit],
                          capture_output=True, text=True).stdout.strip()


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


def meta(paths, key):
    conn = sqlite3.connect(f"{paths.db_file.as_uri()}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    try:
        return json.loads(row[0]) if row and row[0] else {}
    except ValueError:
        return {}


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
elif mode == "closed":
    _cfg, paths = xgw()
    trials = meta(paths, "profile_trials")
    closed = trials.get("closed") if isinstance(trials.get("closed"), dict) else {}
    status = read_json(paths.status_file) or {}
    rows = [*(status.get("members") or []), *(status.get("spares") or [])]
    marked = [row for row in rows if row.get("closed_ts")]
    answering = [row for row in marked if row.get("verdict") in ("OK", "SLOW")]
    refused = [row for row in rows if row.get("verdict") in ("CONNECT_FAIL", "TIMEOUT")]
    print(f"отметок «адрес закрыт» в базе: {len(closed)}; в состоянии: {len(marked)}; из них у "
          f"отвечающих серверов: {len(answering)}; серверов с вердиктом «отказ/таймаут»: "
          f"{len(refused)}")
elif mode == "whitelist":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    print("белые списки в состоянии: " + ("есть" if status.get("whitelist") else "нет"))
elif mode == "foreign":
    cfg, _paths = xgw()
    from xgw import engine, fetch, log
    from xgw.watch import checks
    from xgw.watch import hosts as probehosts

    mark = engine.bypass_mark(cfg, log.get_logger("check"))
    if mark is None:
        print("метки обхода нет — проверить нечем")
        sys.exit(0)
    opened = tried = 0
    for url in probehosts.all_urls(cfg):
        parts = urlsplit(url)
        if not parts.hostname:
            continue
        try:
            address = fetch.resolve_domain(parts.hostname, cfg.dns.resolvers, mark=mark)[0]
        except (fetch.ResolveError, OSError, IndexError):
            continue
        tried += 1
        port = parts.port or (443 if parts.scheme == "https" else 80)
        opened += checks.tcp_check(address, port, timeout=4.0, mark=mark)
    print(f"зарубежные проверочные хосты напрямую: открываются {opened} из {tried}")
elif mode == "sizes":
    lines = sys.stdin.read().splitlines()
    sizes = [int(match.group(2)) for line in lines for match in [SCAN_RE.search(line)] if match]
    full = [size for size in sizes if size >= 40_000]
    print(f"удачных сканов: {len(sizes)}; из них с телом от 40 000 байт: {len(full)}; разных "
          f"длин среди них: {len(set(full))}"
          + (f"; от {min(full)} до {max(full)} байт" if full else ""))
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
              f"{'да' if magic else 'нет'}; пакеты в нём: "
              f"{'есть' if newest.stat().st_size > 24 else 'нет'}")
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
elif mode == "netcheck":
    _cfg, paths = xgw()
    last = meta(paths, "netcheck")
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
        ("адрес сервера закрыт целиком", "адрес закрыт целиком"),
        ("одиночный отказ — замена сразу", "меняю его на проверенный запасной сразу"),
        ("дробление на месте", "не меняю его, а пробую"),
        ("белые списки распознаны", "включил белые списки"),
        ("белые списки сняты", "белые списки сняты"),
        ("замена участников", "замена участников"),
        ("Read-only file system", "Read-only file system"),
        ("Permission denied", "Permission denied"),
        ("Traceback", "Traceback"),
    ):
        print(f"{label}: {sum(1 for line in lines if text in line)}")
else:
    print("режим: units | closed | whitelist | foreign | sizes | records | digest | subs | "
          "netcheck | ts | log")
EOF
python3 -c "import hashlib;d=open('v020gcheck.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Белые списки' | tee before.txt; sudo python3 -I v020gcheck.py ts | tee -a before.txt; sudo xgw diag | grep -E 'Система:|Xray API|Итог' | tee diag-before.txt; for m in closed whitelist foreign subs; do sudo python3 -I v020gcheck.py $m; done | tee state-before.txt; sudo journalctl -u xgw --since "60 min ago" --no-pager | sudo python3 -I v020gcheck.py sizes | tee sizes-before.txt; sudo journalctl -u xgw --since "60 min ago" --no-pager | sudo python3 -I v020gcheck.py log | tee log-before.txt
```

Ожидается:
- `d152f9a04af934ac`;
- `Состояние: HEALTHY …`, `Перехват: включён …`, строки `Xray …` и `sing-box …`, строки
  `Белые списки` нет, `Tailscale: Running` — записать как есть;
- строки diag `Система`, `Xray API`, `Итог: …` — записать;
- «отметок «адрес закрыт» в базе: 0; в состоянии: 0; …» (старый код их не ставит); «белые
  списки в состоянии: нет»; «зарубежные проверочные хосты напрямую: открываются N из M» (N — 1
  или больше); «подписок с ошибкой: …; серверов в списке: …» — записать;
- «удачных сканов: …; … разных длин среди них: K» — на старом коде K не больше 3 (длина
  каждого проверочного файла одна); записать;
- счётчики журнала — записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать и продолжить. «открываются 0 из M» —
записать (дома зарубежные сайты напрямую закрыты? сообщить заказчику) и продолжить.

Шаг 1.3 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В панели XGW нажмите кнопку «Проверить сеть» и подождите, пока под ней появится итог (до
15 секунд). Скажите, когда появится.»

После ответа:

```bash
cd "$HOME/xgw-020g" && sudo python3 -I v020gcheck.py netcheck | tee netcheck-before.txt
```

Ожидается: «проверка сети (<время сейчас>): OK — …, WARN — …, FAIL — …» и список проверок.
Записать. Время не сегодняшнее — попросить нажать ещё раз и повторить команду.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout tspu2 && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q '^CLOSED_RECHECK' src/xgw/daemon.py && grep -q 'def _isolated_failure' src/xgw/daemon.py && grep -q 'def _whitelist_step' src/xgw/daemon.py && grep -q '^RANDOM_MIN = 40_000' src/xgw/watch/scan.py && grep -q 'whitelist-note' src/xgw/ui/index.html && echo "правка в коде: есть"; cd "$HOME/xgw-020g"
```

Ожидается: «правка в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-020g/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-020g/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|Xray запущен' "$HOME/xgw-020g/install.txt"; cd "$HOME/xgw-020g"
```

Ожидается: «код 0», «демон xgw запущен», «Xray запущен: участников …». Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке:

```bash
sleep 120; cd "$HOME/xgw-020g" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Белые списки' | tee after-install.txt; sudo python3 -I v020gcheck.py ts | tee -a after-install.txt; sudo python3 -I v020gcheck.py units | tee -a after-install.txt; sudo python3 -I v020gcheck.py digest | tee digest.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray отвечает, строка sing-box — как до установки,
строки `Белые списки` нет; `Tailscale: …` — как в §1.2; четыре службы `active`; «отпечаток
таблиц: совпадает; правила на месте (loaded): True». Записать.

Если не так: не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать `sudo
systemctl is-active xgw xgw-xray xgw-singbox xgw-dhcp | tee active.txt`, сообщить заказчику и
продолжить. Отпечаток не совпадает — повторить через минуту, снова так — **дефект «отпечаток
таблиц меняется сам»**.

## 3. Пробы без шаблона

Шаг 3.1. Не раньше чем через 10 минут после установки (сканы набрались):

```bash
cd "$HOME/xgw-020g" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020gcheck.py sizes | tee sizes-after.txt
```

Ожидается: «удачных сканов: N; из них с телом от 40 000 байт: F; разных длин среди них: K; от
A до B байт». Если F — 5 или больше: K — 3 или больше, A — не меньше 40 000, B — не больше
70 264. Записать.

Если не так: F 5 или больше, а K меньше 3 — **дефект «длина пробы не меняется»**; A меньше
40 000 — **дефект «проба короче 40 000 байт»**. F меньше 5 — подождать ещё 10 минут и повторить;
снова так — записать как есть (наблюдение: мало сканов) и продолжить.

## 4. Адрес закрыт целиком

Шаг 4.1 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В панели XGW нажмите кнопку «Проверить запасные» (над списком серверов). Скажите, когда
нажали.»

Через 10 минут после ответа:

```bash
cd "$HOME/xgw-020g" && sudo python3 -I v020gcheck.py closed | tee closed.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020gcheck.py log | grep -E 'адрес сервера закрыт|одиночный|дробление на месте|замена участников|Traceback' | tee -a closed.txt
```

Ожидается: «отметок «адрес закрыт» в базе: X; в состоянии: Y; из них у отвечающих серверов: 0;
серверов с вердиктом «отказ/таймаут»: R» — X и Y любые (0 — у отказавших серверов адрес
открыт, их режет не адрес), но Y не больше R; «адрес сервера закрыт целиком: …» — любое число;
«Traceback: 0». Записать.

Если не так: «у отвечающих серверов» больше 0 — **дефект «пометка «адрес закрыт» у
работающего сервера»**; Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -20 | tee traceback-closed.txt`
(только строки с файлами и ошибкой).

Если Y больше 0, **спроси заказчика** (дословно): «Найдите в списке серверов панели сервер с
пометкой «адрес закрыт: напрямую не открывается». Видна ли пометка?» Записать ответ.

## 5. Белые списки — без ложной тревоги

Шаг 5.1.

```bash
cd "$HOME/xgw-020g" && sudo python3 -I v020gcheck.py foreign | tee whitelist.txt; sudo python3 -I v020gcheck.py whitelist | tee -a whitelist.txt; sudo xgw status 2>&1 | grep -c '^Белые списки' | sed 's/^/строк «Белые списки» в xgw status: /' | tee -a whitelist.txt
```

Ожидается: «зарубежные проверочные хосты напрямую: открываются N из M», N — 1 или больше;
«белые списки в состоянии: нет»; «строк «Белые списки» в xgw status: 0». Записать.

Если не так: белые списки «есть», хотя N больше 0 — **дефект «ложная тревога о белых
списках»**; N = 0 — записать и сообщить заказчику (это само по себе не дефект XGW).

## 6. Запись трафика с пакетами (при согласии на пункты 2 и 3)

Шаг 6.1. **Попроси заказчика** (дословно):

«В панели XGW, в списке устройств домашней сети, у телефона нажмите круглую кнопку записи
(подсказка «Записать трафик …») и подтвердите «Записать». Сразу откройте на телефоне любой
сайт и полистайте его полминуты. Затем нажмите у телефона кнопку остановки записи, у
появившейся записи — «Скачать запись» и сохраните файл в папку загрузок. Скажите, когда файл
скачается.»

После ответа:

```bash
cd "$HOME/xgw-020g" && sudo python3 -I v020gcheck.py records "$(xdg-user-dir DOWNLOAD)" | tee records.txt
```

Ожидается: «записей трафика на шлюзе: …»; «скачанный файл: … байт, … с назад; размер как у
записи на шлюзе: да; заголовок pcap: да; пакеты в нём: есть». Записать.

Если не так: «пакеты в нём: нет» — **спроси заказчика** (дословно): «Открывался ли сайт на
телефоне во время записи? Телефон подключён к домашнему Wi-Fi?» — записать ответ (наблюдение:
трафик телефона мог идти мимо шлюза); «размер … нет» или «заголовок pcap: нет» — **дефект
«запись скачивается не целиком»**.

## 7. Правила и подписки

Шаг 7.1. Не раньше чем через 5 минут после шага 2.3:

```bash
cd "$HOME/xgw-020g" && cat digest.txt; sudo python3 -I v020gcheck.py digest | tee -a digest.txt; sudo python3 -I v020gcheck.py subs | tee subs-after.txt
```

Ожидается: снова «совпадает; … True», время — на 5 минут и больше позже; «подписок с ошибкой»
— не больше, чем до установки; «серверов в списке» — как до установки. Записать.

Если не так: отпечаток — как в шаге 2.3; ошибок подписок больше или серверов меньше —
**дефект «подписки после установки»**: записать оба числа.

## 8. После

Шаг 8.1 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В панели XGW снова нажмите «Проверить сеть» и подождите итог. Скажите, когда появится.»

После ответа:

```bash
cd "$HOME/xgw-020g" && sudo python3 -I v020gcheck.py netcheck | tee netcheck-after.txt
```

Ожидается: время — сейчас; те же проверки и уровни, что в шаге 1.3; FAIL — не больше. Если не
так: проверка, бывшая OK или WARN, стала FAIL — **дефект «проверка сети после установки»**.

Шаг 8.2 (при согласии на пункт 3). **Попроси заказчика** (дословно):

«Откройте любой сайт на этом компьютере и любой сайт на телефоне. Открываются?»

Ожидается: «да». Нет — записать ответ дословно и
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt`,
сообщить заказчику.

Шаг 8.3. Итог:

```bash
cd "$HOME/xgw-020g" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020gcheck.py log | tee final.txt; sudo python3 -I v020gcheck.py closed | tee -a final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Белые списки' | tee -a final.txt
```

Ожидается:
- «правила загружены заново: 0» или 1; «откат на last-good: 0»; «ошибка API Xray: 0»;
- «адрес сервера закрыт целиком», «одиночный отказ — замена сразу», «дробление на месте»,
  «замена участников» — любые числа, записать;
- «белые списки распознаны: 0»; «белые списки сняты: 0»;
- **«Traceback: 0»**; «Read-only file system», «Permission denied» — не больше, чем в
  `log-before.txt`;
- «… из них у отвечающих серверов: 0»;
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки, строки `Белые списки`
  нет.

Если не так: «правила загружены заново» больше 1 — **дефект «правила загружаются по кругу»**;
Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -30 | tee traceback.txt`
(только строки с файлами и ошибкой, адреса — убрать); «белые списки распознаны» больше 0 —
**дефект «ложная тревога о белых списках»**. Сообщить заказчику.

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-tspu2-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`tspu2`), коммит «Отчёт: XGW 0.2.0, анти-ТСПУ 2.0, первый этап», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, анти-ТСПУ 2.0, первый этап

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
v020gcheck.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, diag, отметки, белые списки, зарубежные хосты, подписки, длины проб, журнал |
| 1.3 проверка сети до | — / не выполнялся | OK / WARN / FAIL |
| 2.2 установка | … | код, строки установки |
| 2.3 после установки | … | HEALTHY, Tailscale, службы, отпечаток |
| 3.1 пробы без шаблона | … | сканов, разных длин, от … до … |
| 4.1 адрес закрыт | … / не выполнялся | отметки, у отвечающих, счётчики, ответ заказчика |
| 5.1 белые списки | … | зарубежные хосты, состояние, xgw status |
| 6.1 запись трафика | … / не выполнялся | размер, заголовок, пакеты |
| 7.1 правила и подписки | … | отпечаток, ошибки, серверы |
| 8.1 проверка сети после | … / не выполнялся | OK / WARN / FAIL до → после |
| 8.2 сайты | … / не выполнялся | ответ заказчика |
| 8.3 итог | … | счётчики журнала, отметки, HEALTHY |

## Выводы шагов
<файлы $HOME/xgw-020g/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
