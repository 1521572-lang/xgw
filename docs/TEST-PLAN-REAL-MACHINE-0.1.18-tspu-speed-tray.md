# Программа испытаний XGW 0.1.18 на реальной машине: устойчивость к ТСПУ, контроль скорости, значок в трее

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§11). Пути в командах — только абсолютные (`$HOME/xgw-018-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома, рабочий стол KDE Plasma. Стоит XGW с
кодом ветки `cores-update` (версия 0.1.17) на Xray 26.10.21 и sing-box 1.14.3; Tailscale
подключён. Клон репозитория — `~/zcod/xgw`. Новый код — ветка `tspu-speed-tray`, версия
**0.1.18**.

Что изменилось (ASSUMPTIONS пп. 235–239, ТЗ `docs/SPEC-0.1.18-TSPU-SPEED-TRAY-2026-10-24.md`):

1. **Эскалация обхода (R1).** Сервер в работе, который «замёрз» или не соединился, шлюз не
   меняет сразу, а проверяет на месте с дроблением ClientHello, затем с новой «нарезкой
   первых пакетов» (`xray+split`). Помогло — у сервера в панели «обход: … после …».
2. **QUIC отбивается (R2).** UDP/443 в интернет у устройств сети и самой машины отбивается
   сразу — браузеры уходят на TCP, где действует дробление (`network.block_quic`).
3. **Проверочные хосты (R3).** Кроме `probe.url` — ещё три хоста на других CDN, по кругу; один
   неработающий хост — событие и пауза 30 минут, а не смена состояния.
4. **bootstrap DNS (R4a)** — ещё три резолвера и их проверка раз в 30 минут; **DERP (R4b)** —
   если серверы DERP напрямую не отвечают, Tailscale временно идёт через VPN.
5. **Контроль скорости (R5–R8).** Скорость серверов в работе — по их реальному трафику
   («из трафика»); «придушенный» сервер шлюз меняет на быстрого кандидата. Фоновые замеры
   реже: серверы в работе — раз в 6 ч, запасные — раз в сутки. У скорости каждого сервера —
   иконка ↻ «замерить только этот».
6. **Значок XGW в трее (R9)** рядом с часами: цвет — состояние шлюза, меню — «Открыть
   панель», «Проверить выпуски ядер», «Замерить скорость сейчас», «О программе», «Выход».
7. **DEGRADED, когда заменить некем (п. 235)** — проверяется отдельной программой
   `docs/TEST-PLAN-REAL-MACHINE-0.1.17-stranded.md`, здесь не проверяется.

Цели:

1. Снимок до установки и копия `config.toml` (шаг 1.3).
2. Новый код, значок в трее, правило против QUIC (шаг 2).
3. QUIC отбивается у машины и у телефона в Wi-Fi шлюза (шаг 3).
4. Один неработающий проверочный хост не меняет состояние шлюза (шаг 4).
5. Расписание замеров, замер одного сервера, скорость «из трафика» (шаг 5).
6. Значок в трее у заказчика: вид, меню, перезапуск после падения (шаг 6).
7. bootstrap DNS, DERP, события (шаг 7); журнал и итог (шаг 8); наблюдение через сутки
   (шаг 9, по согласию); отчёт (§11).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**.
- `sudo xgw update-xray`, `sudo xgw update-singbox`, `sudo xgw cores update|rollback` — не
  запускать.
- Команды Tailscale, кроме `tailscale status`; Funnel, Serve и SSH не трогать.
- Запуск, остановка и перезапуск `tailscaled`, `xgw`, `xgw-xray`, `xgw-singbox`, `xgw-net`,
  `xgw-dhcp`, `systemd-resolved`, NetworkManager, `ssh`/`sshd` — кроме §10 (откат).
- Ручные команды `nft` (кроме `nft list`), `ip` (кроме `ip … show`), `iptables`, `tc`,
  `sysctl -w`.
- Отключать WAN или LAN, кабели, Wi-Fi роутера.
- Править `/etc/xgw/config.toml` — только командами шагов 4.2, 4.4 и 5.1 (через
  `tspucheck.py`) и копией из шага 1.3. Не править `/etc/xgw/panel.json`, `/etc/systemd`,
  файлы в `/opt/xgw` и `/var/lib/xgw`.
- Нажимать в панели или приложении что-либо, кроме того, что написано в шагах. Кнопку
  «Замерить скорость» (общий замер всех серверов) и пункт значка «Замерить скорость сейчас»
  **не нажимать**: это сотни мегабайт.
- Править код XGW. Коммитить что-либо, кроме отчёта (§11). Файлы из `~/xgw-018-test` в Git
  **не класть**.
- Писать в отчёт: адреса tailnet (`100.x.y.z`), имена `*.ts.net`, имена устройств и
  пользователей (имя пользователя машины заменять на `<user>`), почту, внешние IP, токены (в
  том числе токен панели и токен трея), адреса подписок, UUID, IP и домены серверов VPN,
  MAC-адреса. Внутренние подсети (`192.168.x.0/24`), коды стран, теги серверов
  (`proxy-nl-a1b2`), имена проверочных хостов и версии ядер — можно.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю XGW 0.1.18 — устойчивость к блокировкам, контроль скорости серверов и значок в
трее. По пунктам:
(1) Переустановка XGW с новым кодом: Xray перезапустится — интернет дома пропадёт на
несколько секунд, панель секунд на десять недоступна. Установка поставит пакет
python3-pyqt6 из Ubuntu (для значка), и рядом с часами появится значок XGW.
(2) Проверка, что QUIC (HTTP/3) отбивается: с машины — несколько пакетов на 1.1.1.1 и
8.8.8.8; потом попрошу открыть на телефоне в Wi-Fi шлюза одну страницу.
(3) Временная правка config.toml на 15 минут: добавлю заведомо несуществующий проверочный
адрес и посмотрю, что шлюз из-за одного неработающего адреса не меняет состояние. Потом
верну файл как был.
(4) Замер скорости одного запасного сервера (до 3 МБ через VPN) и просьба нажать в панели
иконку ↻ у одного сервера.
(5) Скачаю через VPN шлюза файл 100 МБ — проверю, что шлюз видит скорость по трафику.
(6) Значок в трее: попрошу посмотреть на него, открыть меню, нажать «Открыть панель»,
«Проверить выпуски ядер» и «Выход»; ещё я один раз сам закрою значок аварийно — он должен
подняться сам.
(7) Через сутки — ещё раз собрать журнал и события (только чтение).
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против пункта 2 — шаг 3 пропустить. Против пункта 3 — шаги 4.2–4.4 пропустить.
- Против пункта 4 — шаги 5.2 и 5.3 пропустить. Против пункта 5 — шаг 5.4 пропустить.
- Против пункта 6 — шаги 6.3–6.5 пропустить. Против пункта 7 — шаг 9 пропустить.

Шаг 1.2. Каталог испытания и вспомогательный скрипт `tspucheck.py` (читает то, что видно в
панели, нажимает иконку ↻ у сервера, проверяет вход значка и QUIC, делает две правки
config.toml шагов 4.2 и 5.1). Скопируй блок **целиком**, от первой строки до последней:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-018-test/before" "$HOME/xgw-018-test/after" && chmod 700 "$HOME/xgw-018-test" && cat > "$HOME/xgw-018-test/tspucheck.py" <<'PY'
"""Испытание XGW 0.1.18: читает то же, что видно в панели, и нажимает кнопку замера одного
сервера. Только чтение, кроме команд speedone, addurl и hours6.
Запуск: sudo python3 tspucheck.py <команда> (quic — без sudo).

  state            — состояние, расписание замеров, основной, контроль скорости, проверочные
                     хосты, резолверы, Tailscale; серверы с обходом, пометками, скоростью
  speedone [ТЕГ]   — иконка ↻ у сервера ТЕГ (по умолчанию — первый проверенный запасной не
                     x100) и дождаться нового замера (до 180 с)
  events           — последние события 0.1.18 (обход, контроль скорости, хосты, DNS, Tailscale)
  tray ДОМ         — вход значка: GET /api/tray с токеном из ДОМ/.config/xgw/tray.json и без
  quic             — UDP/443 с этой машины: отбит ли сразу (ICMP «порт недоступен»)
  addurl URL       — config.toml: [probe] urls = [URL и три хоста по умолчанию] (шаг 4.2)
  hours6           — config.toml: unlimited_hours = 1 → 6 в [speed] (шаг 5.1)
"""

import hashlib
import hmac
import http.client
import json
import os
import re
import socket
import sys
import time
import tomllib

PORT, TOKEN = 8781, ""
try:  # команде quic (она без sudo) ни порт, ни токен панели не нужны
    with open("/etc/xgw/config.toml", "rb") as handle:
        PORT = int(tomllib.load(handle).get("panel", {}).get("port", PORT))
    with open("/var/lib/xgw/panel-token", encoding="utf-8") as handle:
        TOKEN = handle.read().strip()
except OSError:
    pass
COOKIE = "xgw_panel=" + hmac.new(TOKEN.encode(), b"xgw-panel", hashlib.sha256).hexdigest()
HOST = f"127.0.0.1:{PORT}"
KINDS = {"profile", "guard", "probe", "dns", "tailscale", "main", "pin", "fragment"}


def request(method, path, body=None, headers=None, quiet=False):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    sent = {"Host": HOST, **(headers if headers is not None else {"Cookie": COOKIE})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        sent.update({"Content-Type": "application/json", "X-XGW-Panel": "1",
                     "Origin": f"http://{HOST}"})
    conn.request(method, path, body=data, headers=sent)
    response = conn.getresponse()
    text = response.read().decode("utf-8", "replace")
    conn.close()
    if quiet:
        return response.status, text
    if response.status != 200:
        sys.exit(f"панель ответила HTTP {response.status}: {text.strip()[:200]}")
    return json.loads(text)


def stamp(ts):
    return time.strftime("%d.%m %H:%M:%S", time.localtime(float(ts))) if ts else "—"


def mbps(value):
    return "—" if value is None else f"{float(value):.1f} Мбит/с"


def country(tag):
    parts = str(tag or "").split("-")
    return parts[1].upper() if len(parts) > 2 else "??"


def show_state():
    state = request("GET", "/api/state")
    sticky = state.get("sticky") or {}
    print(f"состояние шлюза: {state.get('state')}")
    print(f"замеры фоном: в работе — раз в {sticky.get('unlimited_hours')} ч (лимитированные — "
          f"раз в {sticky.get('limited_hours')} ч), запасные — раз в "
          f"{sticky.get('spare_hours')} ч; контроль скорости: "
          f"{'включён' if sticky.get('guard') else 'выключен'}")
    main = state.get("main") or {}
    print(f"основной: {main.get('tag') or '—'} ({country(main.get('tag'))}), "
          f"{mbps(main.get('mbps'))}")
    guard = state.get("guard") or {}
    episode = guard.get("episode")
    print("контроль скорости: "
          + (f"идёт поиск замены ({episode.get('tried')} из {episode.get('total')})"
             if episode else "поиска нет")
          + (f", пауза после просадки до {stamp(guard['cooldown_until'])}"
             if guard.get("cooldown_until") else "")
          + f", придушенных: {len(guard.get('throttled') or [])}"
          + f", трафик поисков за сутки: {guard.get('spent_mb', 0)} МБ из "
            f"{guard.get('daily_mb', '?')}")
    hosts = state.get("probe_hosts") or {}
    print("проверочные хосты:")
    for item in hosts.get("hosts") or []:
        mark = " (активный)" if item.get("url") == hosts.get("current") else ""
        paused = item.get("paused_until")
        print(f"  {item.get('host')}{mark}: удачно {item.get('ok', 0)}, ошибок "
              f"{item.get('errors', 0)}"
              + (f", пропускается до {stamp(paused)}" if paused and paused > time.time() else "")
              + (f" — {item['last_error']}" if item.get("last_error") else ""))
    resolvers = state.get("resolvers") or {}
    results = resolvers.get("results") or []
    print(f"bootstrap-DNS (проверены {stamp(resolvers.get('ts'))}): "
          + (", ".join(f"{item.get('entry')} {'да' if item.get('ok') else 'нет'}"
                       for item in results) or "ещё не проверялись"))
    print(f"Tailscale через VPN: {'да' if state.get('tailscale_via_vpn') else 'нет'}")
    print("серверы (тег, страна, скорость, из трафика, обход, нестабилен):")
    for row in state.get("servers") or []:
        if row.get("status") not in ("member", "spare"):
            continue
        esc = row.get("escalation") or {}
        print(f"  {row.get('status'):6} {row.get('tag')} {country(row.get('tag'))}"
              f" x{row.get('multiplier') or 1:g}: {mbps(row.get('speed_mbps'))}"
              f" ({stamp(row.get('speed_ts'))})"
              + (f", из трафика {mbps(row.get('speed_passive_mbps'))}"
                 if row.get("speed_passive_mbps") is not None else "")
              + (f", обход {esc.get('label')} после {esc.get('verdict')} {stamp(esc.get('ts'))}"
                 if esc else "")
              + (f", нестабилен до {stamp(row.get('unstable_until'))}"
                 if row.get("unstable_until") else "")
              + (f", профиль {row.get('profile')}" if row.get("profile") else ""))
    return state


def find(state, tag):
    return next((row for row in state.get("servers") or [] if row.get("tag") == tag), None)


def speed_one(tag):
    state = request("GET", "/api/state")
    if not tag:
        spares = [row for row in state.get("servers") or []
                  if row.get("status") == "spare" and (row.get("multiplier") or 1) < 100
                  and row.get("verdict") in ("OK", "SLOW")]
        if not spares:
            sys.exit("нет проверенного запасного не x100 — укажите тег")
        tag = spares[0]["tag"]
    row = find(state, tag)
    if row is None:
        sys.exit(f"сервера {tag} нет в панели")
    before = row.get("speed_ts") or 0
    print(f"сервер {tag} ({country(tag)}): было {mbps(row.get('speed_mbps'))} "
          f"({stamp(before)})")
    start = time.time()
    result = request("POST", "/api/speed/one", {"tag": tag})
    print(f"ответ панели: {'принято' if result.get('ok') else 'отказ'} — {result.get('text')}")
    if not result.get("ok"):
        return 1
    seen_busy = False
    while time.time() - start < 180:
        time.sleep(3)
        state = request("GET", "/api/state")
        row = find(state, tag) or {}
        busy = (state.get("busy") or {}).get("speed_one") or []
        seen_busy = seen_busy or bool(busy) or bool(row.get("speed_queued"))
        if (row.get("speed_ts") or 0) > max(before, start - 5):
            print(f"{time.strftime('%H:%M:%S')} новый замер через {time.time() - start:.0f} с: "
                  f"{mbps(row.get('speed_mbps'))}"
                  + (f" (ошибка: {row['speed_error']})" if row.get("speed_error") else "")
                  + f"; иконка была занята: {'да' if seen_busy else 'нет'}")
            return 0
    print(f"нового замера за 180 с нет; иконка была занята: {'да' if seen_busy else 'нет'}")
    return 2


def events():
    for event in reversed(request("GET", "/api/state").get("events") or []):
        if event.get("kind") in KINDS:
            detail = str(event.get("detail") or "")
            print(f"{stamp(event.get('ts'))} [{event.get('kind')}] {detail}")


def tray(home):
    with open(f"{home}/.config/xgw/tray.json", encoding="utf-8") as handle:
        data = json.load(handle)
    status, text = request("GET", "/api/tray", headers={"X-XGW-Tray": data["token"]}, quiet=True)
    print(f"с токеном трея: HTTP {status}")
    if status == 200:
        state = json.loads(text)
        main = state.get("main") or {}
        print(f"  версия {state.get('version')}, состояние {state.get('state')}, Xray "
              f"{state.get('xray')}, sing-box {state.get('singbox') or '—'}, основной "
              f"{main.get('country') or '—'} {mbps(main.get('mbps'))}")
    status, _text = request("GET", "/api/tray", headers={"X-XGW-Tray": "0" * 32}, quiet=True)
    print(f"с чужим токеном: HTTP {status}")
    status, _text = request("GET", "/api/state", headers={"X-XGW-Tray": data["token"]},
                            quiet=True)
    print(f"токен трея на /api/state: HTTP {status}")


def quic():
    for address in ("1.1.1.1", "8.8.8.8"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)
        started = time.monotonic()
        try:
            sock.connect((address, 443))
            sock.send(b"\xc0" + b"\x00" * 1199)
            sock.recv(2048)
            verdict = "пришёл ответ (не отбит)"
        except ConnectionRefusedError:
            verdict = "отбит: ICMP «порт недоступен»"
        except PermissionError:
            # reject в цепочке output самой машины: отправка падает сразу (EPERM).
            verdict = "отбит: отправка запрещена правилом шлюза"
        except TimeoutError:
            verdict = "тишина 3 с (не отбит)"
        except OSError as exc:
            verdict = f"ошибка {exc}"
        finally:
            sock.close()
        print(f"UDP {address}:443 — {verdict} за {time.monotonic() - started:.2f} с")


CONFIG = "/etc/xgw/config.toml"
HOSTS = [
    "https://code.jquery.com/jquery-3.7.1.slim.min.js",
    "https://ajax.aspnetcdn.com/ajax/bootstrap/3.4.1/fonts/glyphicons-halflings-regular.ttf",
    "https://ajax.googleapis.com/ajax/libs/jquery/3.7.1/jquery.slim.min.js",
]


def rewrite(change, check):
    """Правка config.toml: change(текст) → новый текст; check(разобранный) — проверка итога.
    Файл заменяется целиком с прежними правами, только если новый текст разбирается."""
    with open(CONFIG, encoding="utf-8") as handle:
        text = handle.read()
    new = change(text)
    if not check(tomllib.loads(new)):
        sys.exit("правка не дала ожидаемого — config.toml не тронут")
    info = os.stat(CONFIG)
    temp = CONFIG + ".xgw-test"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(new)
    os.chown(temp, info.st_uid, info.st_gid)
    os.chmod(temp, info.st_mode & 0o7777)
    os.replace(temp, CONFIG)
    print("config.toml изменён")


def add_url(url):
    urls = [url, *HOSTS]
    line = "urls = [" + ", ".join(json.dumps(item) for item in urls) + "]"

    def change(text):
        if "urls" in (tomllib.loads(text).get("probe") or {}):
            sys.exit("в [probe] уже есть urls — стоп, config.toml не тронут")
        found = re.search(r"(?m)^\s*\[probe\]\s*(#.*)?$", text)
        if found is None:
            return text.rstrip("\n") + "\n\n[probe]\n" + line + "\n"
        return text[:found.end()] + "\n" + line + text[found.end():]

    rewrite(change, lambda data: (data.get("probe") or {}).get("urls") == urls)


def hours6():
    def change(text):
        new, count = re.subn(r"(?m)^(\s*unlimited_hours\s*=\s*)1(\s*(#.*)?)$", r"\g<1>6\g<2>", text)
        if count != 1:
            sys.exit("строки unlimited_hours = 1 нет — менять нечего, config.toml не тронут")
        return new

    rewrite(change, lambda data: (data.get("speed") or {}).get("unlimited_hours") == 6)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    command, rest = sys.argv[1], sys.argv[2:]
    if command == "state":
        show_state()
    elif command == "speedone":
        return speed_one(rest[0] if rest else "")
    elif command == "events":
        events()
    elif command == "tray" and rest:
        tray(rest[0])
    elif command == "quic":
        quic()
    elif command == "addurl" and rest:
        add_url(rest[0])
    elif command == "hours6":
        hours6()
    else:
        sys.exit(__doc__)
    return 0


sys.exit(main())
PY
cd "$HOME/xgw-018-test" && sha256sum tspucheck.py && date
```

Ожидается: «sudo без пароля: да»; строка
`dfa4342cb773616ac3a72ad7ea24a539a1fcd229a01be6bfd4597cf51ef57d68  tspucheck.py`; дата. Дальше все команды выполняй из этого каталога.

Если не так: строки «sudo без пароля: да» нет — **стоп**, попросить заказчика разрешить sudo
без пароля на время испытаний. Хеш другой — блок скопирован не целиком: удали файл
(`rm "$HOME/xgw-018-test/tspucheck.py"`) и повтори шаг 1.2; снова другой — **стоп**,
сообщить заказчику.

Шаг 1.3. Снимок до установки и копия `config.toml` (для отката, §10):

```bash
cd "$HOME/xgw-018-test" && sudo xgw --version; sudo xgw diag > "$HOME/xgw-018-test/before/diag.txt"; tail -1 "$HOME/xgw-018-test/before/diag.txt"; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | tee "$HOME/xgw-018-test/before/state.txt"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled | tee "$HOME/xgw-018-test/before/services.txt"; sudo grep -nE '^\s*\[(speed|probe|network|tailscale|tray)\]|^\s*(unlimited_hours|limited_hours|spare_hours|every_hours|urls|block_quic|route|derp_fallback)\s*=' /etc/xgw/config.toml | tee "$HOME/xgw-018-test/before/config-keys.txt"; echo "правил QUIC до установки: $(sudo nft list table ip xgw 2>/dev/null | grep -c 'udp dport 443')"; sudo mkdir -p "$HOME/xgw-018-test/backup" && sudo cp -a /etc/xgw/config.toml "$HOME/xgw-018-test/backup/config.toml" && echo "копия config.toml: есть"; for id in $(loginctl list-sessions --no-legend | awk '{print $1}'); do echo "сеанс: $(loginctl show-session "$id" -p Type -p Desktop -p Active | paste -sd' ')"; done | tee "$HOME/xgw-018-test/before/sessions.txt"
```

Ожидается: `xgw 0.1.17`; «FAIL — 0»; состояние `HEALTHY` или `DEGRADED` (записать);
«Перехват: включён — …»; службы `active` (у `xgw-singbox` допустимо `inactive` — записать);
строки config.toml с ключами (записать как есть — по ним решается шаг 5.1); «правил QUIC до
установки: 0»; «копия config.toml: есть»; хотя бы один сеанс `Type=x11` или
`Type=wayland` с `Desktop=KDE` и `Active=yes` — заказчик вошёл в рабочий стол.

Если не так: FAIL не 0 — записать как есть и **спросить заказчика**, продолжать ли. Нет
строки «копия config.toml: есть» — **стоп**, сообщить заказчику. Нет активного графического
сеанса — **попросить заказчика** войти в рабочий стол машины и повторить последнюю часть
шага (цикл `for id …`); без него шаг 6 выполнить нельзя.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout tspu-speed-tray && git pull --ff-only && git log -1 --format='%h %s' && test -f src/xgw/tray.py && test -f src/xgw/watch/guard.py && grep -q block_quic src/xgw/config.py && echo "0.1.18 в коде: есть"; grep __version__ src/xgw/__init__.py; cd "$HOME/xgw-018-test"
```

Ожидается: «0.1.18 в коде: есть» и `__version__ = "0.1.18"`. Записать хеш.
Если ветки `tspu-speed-tray` нет или строки «0.1.18 в коде: есть» нет: **стоп**, сообщить
заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-018-test/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-018-test/after/install.txt" | tail -30; echo "код ${PIPESTATUS[0]}"; grep -E 'значок в трее|python3-pyqt6' "$HOME/xgw-018-test/after/install.txt" | sed -E 's/для [^:]+:/для <user>:/'; cd "$HOME/xgw-018-test"
```

Ожидается: «код 0» и «демон xgw запущен»; строка «пакеты: python3-pyqt6 (значок в трее)»
(её нет, если пакет уже стоял — записать); строка «значок в трее для <user>: автозапуск при
входе, запущен» (без «, запущен» — если заказчик не в рабочем столе: записать).

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (§10). Строка
«значок в трее не поставлен: пакет python3-pyqt6 не установился …» — **дефект**, записать
строку целиком; шаг 6 пропустить, остальное продолжать.

Шаг 2.3. Версия, значок, правило против QUIC:

```bash
sudo xgw --version; ls -l /etc/xdg/autostart/xgw-tray.desktop "$HOME/.config/xgw/tray.json" 2>&1 | awk '{print $1, $NF}'; /usr/bin/python3 -c "import PyQt6.QtWidgets; print('PyQt6: есть')" 2>&1 | tail -1; pgrep -af 'xgw tray' | sed -E 's/^[0-9]+ //'; sudo nft list table ip xgw | grep 'udp dport 443' | tee "$HOME/xgw-018-test/after/nft-quic.txt"
```

Ожидается: `xgw 0.1.18`; `-rw-r--r-- /etc/xdg/autostart/xgw-tray.desktop` и
`-rw------- …/.config/xgw/tray.json`; «PyQt6: есть»; две строки процессов —
`/usr/bin/python3 -I /usr/local/bin/xgw tray` (сторож) и `… -m xgw tray --run` (значок);
не меньше двух строк правил с `udp dport 443` и `reject with icmp type port-unreachable`
(одна с `meta mark`, одна с `iifname` сети LAN).

Если не так: нет процессов значка, а в шаге 2.2 было «, запущен», — записать и продолжать
(шаг 6.1 это разберёт). Нет строк `udp dport 443` — **дефект «правило против QUIC не
загружено»**, записать; шаг 3 выполнить всё равно.

Шаг 2.4. Шлюз здоров (ждать до 5 минут) и новые разделы diag:

```bash
for i in $(seq 30); do sudo xgw status 2>&1 | grep -q '^Состояние: HEALTHY' && break; sleep 10; done; date '+%T'; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | tee "$HOME/xgw-018-test/after/state-install.txt"; sleep 120; sudo xgw diag > "$HOME/xgw-018-test/after/diag-install.txt"; grep -E '^(OK|WARN|FAIL) +(QUIC|Проверочные хосты|Значок в трее|bootstrap DNS|Tailscale|Трафик проверок):' "$HOME/xgw-018-test/after/diag-install.txt"; tail -1 "$HOME/xgw-018-test/after/diag-install.txt"
```

Ожидается: состояние — как в шаге 1.3 (или лучше), «Перехват: включён — …»; строки diag
`OK    QUIC: UDP/443 устройств и машины отбивается …`, `OK    Проверочные хосты: …` (или
WARN с ошибками хоста — записать), `OK    Значок в трее: запускается при входе в сеанс`,
`bootstrap DNS` — OK или WARN с перечнем неответивших (записать какие), `Tailscale` — как
до установки; «FAIL — 0».

Если не так: состояние хуже, чем в шаге 1.3, — записать `sudo xgw status 2>&1 | head -30`
(без адресов серверов) и **спросить заказчика**, продолжать ли. FAIL не 0 — записать строки
FAIL целиком и **спросить заказчика**.

## 3. QUIC (при согласии на пункт 2)

Шаг 3.1. UDP/443 с самой машины (без sudo):

```bash
cd "$HOME/xgw-018-test" && python3 tspucheck.py quic | tee "$HOME/xgw-018-test/after/quic-machine.txt"
```

Ожидается: две строки «UDP … :443 — отбит: …» («отправка запрещена правилом шлюза» или
«ICMP «порт недоступен»»), каждая за доли секунды (меньше 0,5 с).

Если не так: «тишина 3 с (не отбит)» или «пришёл ответ» — **дефект «QUIC машины не
отбивается»**, записать; продолжать.

Шаг 3.2. TCP работает, счётчик правила растёт:

```bash
curl -sS -o /dev/null -m 20 -w 'HTTP %{http_code}, версия %{http_version}\n' https://cloudflare-quic.com/ | tee "$HOME/xgw-018-test/after/quic-tcp.txt"; sudo nft list table ip xgw | grep 'udp dport 443' | grep -o 'packets [0-9]*' | tee -a "$HOME/xgw-018-test/after/quic-tcp.txt"; sudo xgw status 2>&1 | grep -E '^Состояние'
```

Ожидается: «HTTP 200, версия 2» (или 1.1); хотя бы у одного правила `packets` больше 0;
состояние — как в шаге 2.4.

Шаг 3.3. **Попроси заказчика**: «Возьмите телефон, подключённый к Wi-Fi шлюза. Если на
телефоне включён VPN (приложение XGW или Tailscale) — выключите его на минуту. Откройте в
Chrome страницу https://cloudflare-quic.com/, обновите её два-три раза (Chrome переходит на
HTTP/3 не с первого раза) и скажите, какой протокол она показывает — HTTP/2 или HTTP/3.
Потом VPN на телефоне можно включить обратно.»

Ожидается: «HTTP/2» (не HTTP/3).

Если не так: «HTTP/3» — записать дословно, что показала страница, и выполни ещё раз
команду шага 3.2 (счётчик правил); **дефект «QUIC устройства сети не отбивается»**. Заказчик
не может — записать «не проверено» и продолжать.

## 4. Проверочные хосты

Шаг 4.1. Хосты и счётчики:

```bash
cd "$HOME/xgw-018-test" && sudo python3 tspucheck.py state | tee "$HOME/xgw-018-test/after/state-1.txt"
```

Ожидается: «проверочные хосты:» — четыре строки: `cdn.jsdelivr.net` (обычно «(активный)»),
`code.jquery.com`, `ajax.aspnetcdn.com`, `ajax.googleapis.com`; у них растут «удачно …»
(через 5 минут после установки — у каждого больше 0). Ниже — строки bootstrap DNS,
«Tailscale через VPN: нет» и список серверов.

Если не так: хостов меньше четырёх — записать; продолжать.

Шаг 4.2 (при согласии на пункт 3). Добавить неработающий хост (адрес отвечает 404):

```bash
cd "$HOME/xgw-018-test" && date '+%F %T' | tee "$HOME/xgw-018-test/bad-host-time.txt" && sudo python3 tspucheck.py addurl https://unpkg.com/xgw-no-such-package-018@1.0.0/x.js && sudo grep -n '^urls' /etc/xgw/config.toml
```

Ожидается: «config.toml изменён» и строка `urls = ["https://unpkg.com/xgw-no-such-package-018…`.

Если не так: «в [probe] уже есть urls — стоп» — записать, шаги 4.2–4.4 пропустить. Другая
ошибка — выполнить шаг 4.4 (возврат файла) и пропустить 4.3.

Шаг 4.3. Подождать 10 минут и посмотреть (команда сама ждёт):

```bash
cd "$HOME/xgw-018-test" && sleep 600; sudo python3 tspucheck.py state | sed -n '1,/^серверы/p' | tee "$HOME/xgw-018-test/after/state-bad-host.txt"; sudo python3 tspucheck.py events | grep -E 'проверочный хост|адрес проверки|probe' | tail -5 | tee "$HOME/xgw-018-test/after/events-bad-host.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-018-test/bad-host-time.txt")" --no-pager | grep -cE 'WAN_DOWN|PROBE_TARGET_UNREACHABLE' | sed 's/^/переходов в WAN_DOWN или PROBE_TARGET_UNREACHABLE: /'
```

Ожидается: «состояние шлюза: HEALTHY» (или как в шаге 2.4); у `unpkg.com` — «ошибок» 1 или
больше и «пропускается до …» (или ошибки и без паузы, если пауза кончилась); у остальных
хостов «удачно» растёт; событие «[probe] проверочный хост unpkg.com не отвечает (HTTP 404) —
пропускаю его 30 мин; пробы идут через …»; «переходов …: 0».

Если не так: состояние стало `WAN_DOWN` или `PROBE_TARGET_UNREACHABLE` — **дефект «один
неработающий хост меняет состояние»**, записать; сразу выполнить шаг 4.4. У `unpkg.com` нет
ошибок — записать «хост не дошёл до очереди» и выполнить шаг 4.4.

Шаг 4.4. Вернуть config.toml как был:

```bash
sudo cp -a "$HOME/xgw-018-test/backup/config.toml" /etc/xgw/config.toml && sudo cmp "$HOME/xgw-018-test/backup/config.toml" /etc/xgw/config.toml && echo "config.toml как до испытания"; sleep 30; sudo python3 "$HOME/xgw-018-test/tspucheck.py" state | sed -n '/^проверочные/,/^bootstrap/p'
```

Ожидается: «config.toml как до испытания»; снова четыре хоста, без `unpkg.com`.

## 5. Скорость

Шаг 5.1. Расписание замеров:

```bash
cd "$HOME/xgw-018-test" && sudo python3 tspucheck.py state | sed -n '1,4p' | tee "$HOME/xgw-018-test/after/schedule.txt"
```

Ожидается: «замеры фоном: в работе — раз в 6 ч (лимитированные — раз в 6 ч), запасные — раз
в 24 ч; контроль скорости: включён».

Если не так: «в работе — раз в 1 ч» — в config.toml заказчика стоит `unlimited_hours = 1`
(видно в шаге 1.3). **Спроси заказчика**: «В вашем config.toml замер серверов в работе стоит
раз в час. По вашему решению от 24.10 замеры теперь редкие — раз в 6 часов. Поменять строку
unlimited_hours = 1 на 6?» Да — выполнить:

```bash
cd "$HOME/xgw-018-test" && sudo python3 tspucheck.py hours6 && sudo cp -a /etc/xgw/config.toml "$HOME/xgw-018-test/backup/config-hours6.toml" && sleep 30 && sudo python3 tspucheck.py state | sed -n '2p'
```

Ожидается: «config.toml изменён» и «… в работе — раз в 6 ч …». Записать в отчёт, что строка
изменена по слову заказчика. Нет — записать «оставлено 1 ч по решению заказчика». Другие
числа — записать как есть.

Шаг 5.2 (при согласии на пункт 4). Замер одного запасного (иконка ↻):

```bash
cd "$HOME/xgw-018-test" && sudo python3 tspucheck.py speedone | tee "$HOME/xgw-018-test/after/speedone.txt"
```

Ожидается: «ответ панели: принято — Замеряю скорость «…»…»; за 180 с — «новый замер через
N с: … Мбит/с»; «иконка была занята: да».

Если не так: «нет проверенного запасного не x100» — записать, шаг пропустить. «нового замера
за 180 с нет» — записать; если в выводе «иконка была занята: да», подождать ещё 3 минуты и
выполнить `sudo python3 tspucheck.py state | grep <тег из вывода>`; новой даты замера нет —
**дефект «замер одного сервера не выполнен»**.

Шаг 5.3. **Попроси заказчика**: «Откройте панель XGW (ярлык „XGW“ или значок в трее →
„Открыть панель“). В разделе „Серверы“ рядом со скоростью у каждого сервера должна быть
маленькая круглая стрелка ↻. Нажмите её у любого сервера (не x100). Скажите: стрелка
крутилась? Цифра скорости и время замера под именем сервера обновились (до минуты-двух)?»

Ожидается: «стрелка крутилась, цифра обновилась». Записать ответ дословно.

Шаг 5.4 (при согласии на пункт 5). Скорость «из трафика». Команда качает 100 МБ через VPN и
до 4 минут ждёт, когда у основного сервера появится оценка по трафику:

```bash
cd "$HOME/xgw-018-test" && curl -sS -o /dev/null -m 120 -w 'скачано %{size_download} байт за %{time_total} с\n' 'https://speed.cloudflare.com/__down?bytes=100000000' | tee "$HOME/xgw-018-test/after/passive.txt"; for i in $(seq 16); do sudo python3 tspucheck.py state | grep -E '^основной|из трафика' > "$HOME/xgw-018-test/passive-now.txt"; grep -q 'из трафика' "$HOME/xgw-018-test/passive-now.txt" && break; sleep 15; done; cat "$HOME/xgw-018-test/passive-now.txt" | tee -a "$HOME/xgw-018-test/after/passive.txt"
```

Ожидается: «скачано 100000000 байт за N с»; строка «основной: proxy-…» и строка сервера
`member proxy-… : … , из трафика X Мбит/с` (X больше 1). Тег основного и сервера с «из
трафика» обычно совпадают.

Если не так: «из трафика» нет ни у одного сервера — **дефект «нет оценки скорости по
трафику»**, записать вывод; продолжать.

## 6. Значок в трее (при согласии на пункт 6)

Шаг 6.1. Значок запущен:

```bash
pgrep -af 'xgw tray' | sed -E 's/^[0-9]+ //'; cd "$HOME/xgw-018-test" && sudo python3 tspucheck.py tray "$HOME" | tee "$HOME/xgw-018-test/after/tray-api.txt"
```

Ожидается: две строки процессов (как в шаге 2.3); «с токеном трея: HTTP 200» и строка
«версия 0.1.18, состояние HEALTHY, Xray 26.10.21, sing-box 1.14.3, основной XX … Мбит/с»;
«с чужим токеном: HTTP 401»; «токен трея на /api/state: HTTP 401».

Если не так: процессов значка нет — запустить его так же, как установка:

```bash
sudo systemd-run --user --machine="$USER@" --quiet --collect --description="XGW: значок в трее" -- /usr/local/bin/xgw tray; sleep 5; pgrep -af 'xgw tray' | sed -E 's/^[0-9]+ //'
```

Процессы появились — записать «значок не запустился при установке, запущен вручную» и
продолжать. Не появились — **дефект «значок не запускается»**: записать
`journalctl --user -n 30 --no-pager | grep -i xgw` (без имён) и пропустить шаги 6.2–6.5.
«с чужим токеном: HTTP 200» или «токен трея на /api/state: HTTP 200» — **дефект
безопасности**, записать.

Шаг 6.2. **Попроси заказчика**: «Посмотрите в правый нижний угол экрана, рядом с часами
(иногда значок спрятан под стрелкой „^“ — скрытые значки). Есть значок XGW — цветной кружок?
1) Какого он цвета? 2) Наведите на него мышь — что написано в подсказке? 3) Нажмите на
значок правой кнопкой — какие пункты в меню?»

Ожидается: значок есть; цвет зелёный при `HEALTHY` (жёлтый при `DEGRADED`); в подсказке
«XGW 0.1.18: в порядке», версии Xray и sing-box, основной сервер со страной и скоростью;
пункты меню «Открыть панель», «Проверить выпуски ядер», «Замерить скорость сейчас», «О
программе», «Выход». Записать ответы дословно (без имён устройств).

Если не так: значка нет, а процессы в шаге 6.1 были — **дефект «значок не виден в трее
KDE»**, записать; шаги 6.3–6.5 пропустить.

Шаг 6.3. **Попроси заказчика**: «В меню значка нажмите „Открыть панель“ — открылась ли
панель XGW в браузере? Потом снова правой кнопкой по значку → „Проверить выпуски ядер“.
„Замерить скорость сейчас“ не нажимайте — это сотни мегабайт.» Затем выполнить:

```bash
cd "$HOME/xgw-018-test" && sleep 60; sudo python3 tspucheck.py events | tail -5; sudo xgw cores | head -12 | tee "$HOME/xgw-018-test/after/tray-cores.txt"
```

Ожидается: заказчик: «панель открылась»; в `xgw cores` — время проверки выпусков свежее
(минуту-две назад), ошибок нет.

Шаг 6.4. Значок упал — поднимается сам (сторож):

```bash
pgrep -f 'xgw tray --run' | head -1 | tee "$HOME/xgw-018-test/tray-pid.txt"; pkill -KILL -f 'xgw tray --run'; sleep 8; echo "было: $(cat "$HOME/xgw-018-test/tray-pid.txt"), стало: $(pgrep -f 'xgw tray --run' | head -1)"
```

Ожидается: «было: N, стало: M» — два разных числа (значок поднялся заново). **Спроси
заказчика**: «Значок XGW мигнул и снова на месте?»

Если не так: «стало:» пусто — **дефект «сторож не поднимает значок»**; запустить его
командой из «Если не так» шага 6.1 и записать.

Шаг 6.5. «Выход» закрывает только значок. **Попроси заказчика**: «Правой кнопкой по значку →
„Выход“. Значок пропал?» Затем:

```bash
sleep 5; echo "процессов значка: $(pgrep -fc 'xgw tray')"; sudo xgw status 2>&1 | grep -E '^Состояние'; sudo systemd-run --user --machine="$USER@" --quiet --collect --description="XGW: значок в трее" -- /usr/local/bin/xgw tray; sleep 5; echo "после запуска: $(pgrep -fc 'xgw tray')"
```

Ожидается: «процессов значка: 0»; состояние шлюза — как в шаге 2.4 (шлюз работает); «после
запуска: 2». **Спроси заказчика**: «Значок снова появился?»

## 7. bootstrap DNS, DERP, события

Шаг 7.1.

```bash
cd "$HOME/xgw-018-test" && sudo python3 tspucheck.py state | grep -E '^bootstrap|^Tailscale' | tee "$HOME/xgw-018-test/after/dns-derp.txt"; echo "отметка Tailscale через VPN: $(test -e /run/xgw/tailscale-via-vpn && echo есть || echo нет)" | tee -a "$HOME/xgw-018-test/after/dns-derp.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-018-test/install-time.txt")" --no-pager | grep -c 'DERP напрямую не отвечает' | sed 's/^/DERP напрямую не отвечал: /' | tee -a "$HOME/xgw-018-test/after/dns-derp.txt"; sudo grep -nE '^\s*route\s*=' /etc/xgw/config.toml
```

Ожидается: «bootstrap DNS (проверены …): https://1.1.1.1/… да, …» — у каждого резолвера «да»
или «нет» (записать, какие «нет»; `9.9.9.9` — может быть «нет», это наблюдение, не дефект);
«Tailscale через VPN: нет»; «отметка …: нет»; «DERP напрямую не отвечал: 0» (или число —
записать); строка `route = "direct"` (или её нет — тогда тоже direct по умолчанию).

Если не так: «Tailscale через VPN: да» — записать время и `sudo python3 tspucheck.py events |
grep tailscale`; **спросить заказчика**, работает ли удалённый доступ к панели с телефона.
Это не дефект, если DERP напрямую действительно не отвечал.

Шаг 7.2. События 0.1.18 за время испытания:

```bash
cd "$HOME/xgw-018-test" && sudo python3 tspucheck.py events | tee "$HOME/xgw-018-test/after/events.txt" | tail -25
```

Ожидается: события «[probe] проверочный хост unpkg.com …» (шаг 4.3), возможно «[dns] …».
События `[profile]` с «пробую «Xray с нарезкой первых пакетов»», `[guard]` с «придушен» —
бывают, только если провайдер в это время мешал; записать как есть (без адресов).

## 8. Журнал и итоговое состояние

Шаг 8.1.

```bash
cd "$HOME/xgw-018-test" && sudo journalctl -u xgw --since "$(cat "$HOME/xgw-018-test/install-time.txt")" --no-pager | grep -c Traceback | sed 's/^/Traceback в xgw: /'; sudo grep -c Traceback /var/log/xgw/*.log 2>/dev/null | sed 's/^/Traceback: /'; journalctl --user --since "$(cat "$HOME/xgw-018-test/install-time.txt")" --no-pager 2>/dev/null | grep -c 'Traceback' | sed 's/^/Traceback значка: /'; sudo xgw diag > "$HOME/xgw-018-test/after/diag.txt"; tail -1 "$HOME/xgw-018-test/after/diag.txt"; sudo xgw status | grep -E '^Состояние|^Xray|^sing-box|Перехват:' | tee "$HOME/xgw-018-test/after/state.txt"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; sudo cmp "$HOME/xgw-018-test/backup/config.toml" /etc/xgw/config.toml && echo "config.toml как до испытания"
```

Ожидается: все Traceback — 0; «FAIL — 0»; состояние `HEALTHY` или как в шаге 1.3; службы —
как в шаге 1.3; «config.toml как до испытания» (если в шаге 5.1 строку поменяли по слову
заказчика — `cmp` сообщит о различии: так и должно быть, записать).

## 9. Наблюдение через сутки (при согласии на пункт 7)

Через 18–30 часов после установки (время — в `install-time.txt`), только чтение:

```bash
cd "$HOME/xgw-018-test" && date '+%F %T'; sudo python3 tspucheck.py state | tee "$HOME/xgw-018-test/after/state-day.txt" | sed -n '1,4p'; sudo python3 tspucheck.py events | tee "$HOME/xgw-018-test/after/events-day.txt" | grep -cE '\[(profile|guard)\]' | sed 's/^/событий обхода и контроля скорости: /'; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-018-test/install-time.txt")" --no-pager | grep -E 'нарезк|придушен|нестабилен по ТСПУ|глобальная просадка|DERP напрямую' | sed -E 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/<ip>/g' | tail -20 | tee "$HOME/xgw-018-test/after/journal-day.txt"; sudo journalctl -u xgw --since "$(cat "$HOME/xgw-018-test/install-time.txt")" --no-pager | grep -c Traceback | sed 's/^/Traceback в xgw: /'; sudo xgw diag | tail -1
```

Ожидается: состояние `HEALTHY` (или `DEGRADED` с объяснением — записать); строки журнала —
как есть (без адресов и имён серверов: имена заменить на теги); «Traceback в xgw: 0»; «FAIL —
0». В `state-day.txt` у серверов в работе даты замеров — с промежутком около 6 часов, у
запасных — не чаще раза в сутки (кроме сервера из шага 5.2).

## 10. Если что-то пошло не так (ручной откат)

- **Установка не прошла** (код не 0) — сеть и ядра не тронуты; ничего не откатывать.
- **После установки пропал интернет дома или шлюз не HEALTHY дольше 10 минут** — вернуть
  прежний код и config.toml:

  ```bash
  sudo cp -a "$HOME/xgw-018-test/backup/config.toml" /etc/xgw/config.toml; cd ~/zcod/xgw && git checkout cores-update && sudo sh packaging/install.sh --yes 2>&1 | tail -5; sudo rm -f /etc/xdg/autostart/xgw-tray.desktop; pkill -f 'xgw tray'; sleep 60; sudo xgw --version; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:'
  ```

  Ожидается: `xgw 0.1.17`, состояние как в шаге 1.3. Сообщить заказчику.
- **Какое-то устройство или программа перестали работать после установки** (например,
  звонки) — не чинить самому: записать, что именно, и сообщить заказчику (возможная причина —
  отбитый QUIC; отключается строкой `block_quic = false` в `[network]` — только по его слову).
- **config.toml после шагов 4–5 не совпадает с копией** — `sudo cp -a
  "$HOME/xgw-018-test/backup/config.toml" /etc/xgw/config.toml`.

## 11. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.18-tspu-speed-tray-<ДАТА>.md` в клоне `~/zcod/xgw`
(ветка `tspu-speed-tray`), коммит «Отчёт 0.1.18: ТСПУ, контроль скорости, значок в трее»,
`git push`. В отчёт — только выводы без адресов и имён (см. §0). Если шаг 9 выполняется
позже — сначала отчёт без него, потом дополнение тем же файлом и вторым коммитом. Шаблон:

```markdown
# Отчёт: XGW 0.1.18 — устойчивость к ТСПУ, контроль скорости, значок в трее

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
Расписание замеров: <как было в config.toml / изменено на 6 ч по слову заказчика>.

## Итог
<3–6 предложений: установка и значок, QUIC у машины и у телефона, неработающий хост,
замер одного сервера и «из трафика», значок у заказчика, bootstrap DNS и DERP, состояние.>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до установки | — | 0.1.17, состояние …, FAIL — 0, сеанс KDE … |
| 2.2 установка | пройден / дефект | код …, python3-pyqt6 …, значок запущен … |
| 2.3 версия, значок, QUIC | … | 0.1.18, файлы значка, правил QUIC: N |
| 2.4 шлюз и diag | … | состояние …, QUIC OK, хосты …, значок OK, bootstrap DNS … |
| 3.1 QUIC машины | … | отбит за … с |
| 3.2 TCP и счётчик | … | HTTP 200 по версии …, packets … |
| 3.3 QUIC телефона | … | страница показала … |
| 4.1 хосты | … | 4 хоста, удачно … |
| 4.3 неработающий хост | … | состояние …, unpkg.com ошибок …, переходов 0 |
| 4.4 config.toml возвращён | … | … |
| 5.1 расписание | … | 6 ч / 24 ч, контроль скорости включён |
| 5.2 замер одного | … | новый замер через N с, иконка занята: … |
| 5.3 иконка у заказчика | … | ответ заказчика |
| 5.4 из трафика | … | 100 МБ за N с, из трафика X Мбит/с |
| 6.1 значок и вход | … | HTTP 200 / 401 / … |
| 6.2 значок у заказчика | … | цвет …, подсказка …, меню … |
| 6.3 меню | … | панель открылась, выпуски проверены |
| 6.4 сторож | … | было N, стало M |
| 6.5 «Выход» | … | 0 процессов, шлюз …, запущен снова |
| 7.1 bootstrap DNS, DERP | … | не отвечают: …; Tailscale через VPN: нет |
| 7.2 события | … | … |
| 8 журнал и итог | … | Traceback 0, FAIL — 0 |
| 9 сутки | … / не выполнялся | … |

## Выводы шагов
<содержимое файлов after/*.txt, по заголовку на файл; имя пользователя → <user>>

## Дефекты
<или «Не обнаружены»>

## Наблюдения

## Что не проверено и почему
- Эскалация на «придушенном» сервере и уход с ограниченного сервера — по требованию не
  воспроизводятся (ТСПУ и полоса не управляются с машины); проверены юнит-тестами, на
  машине — только то, что случилось само (шаги 7.2 и 9).
- Tailscale через VPN при недоступном DERP — DERP не отключается без запрещённых действий;
  проверено юнит-тестами.
- Иконка ↻ в приложении на телефоне — нужна новая сборка APK.
- <прочее>

## Итоговое состояние машины
```

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
