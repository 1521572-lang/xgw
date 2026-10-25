# Перепроверка XGW 0.1.18 по отчёту 25.10.2026: правила QUIC, кнопка ↻, эскалация EU-auto

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы сохраняй в файлы, как написано: из них собирается отчёт
(§9). Пути — только абсолютные (`$HOME/xgw-018-retest/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома, рабочий стол KDE Plasma. Стоит XGW 0.1.18
с кодом ветки `tspu-speed-tray` (2cd610a), Xray 26.10.21, sing-box 1.14.4 (принята шлюзом).
Клон — `~/zcod/xgw`. Каталог прошлого испытания `~/xgw-018-test` (там `tspucheck.py`).

Что исправлено (отчёт `docs/TEST-REPORT-REAL-MACHINE-0.1.18-tspu-speed-tray-2026-10-25.md`,
ASSUMPTIONS п. 240):

1. **Дефект 1 — правила перезагружались каждые 30–40 с.** nft печатает «reject with icmp type
   port-unreachable» просто как «reject», а шлюз искал «port-unreachable» и считал правило
   против QUIC незагруженным. Теперь — FAIL 0 в diag, перезагрузок нет.
2. **Дефект 2 — кнопка ↻ «крутится, но не обновляет».** Замер ждал шага без скана, а сканы на
   шлюзе шли почти на каждом шаге. Теперь замер по кнопке идёт и в шаге со сканом, фоновый —
   не позже чем через 10 минут.
3. **Наблюдение 4 — у сервера EU-auto эскалация повторялась каждую минуту.** Не исправлялось:
   сначала нужны данные (шаги 2.2 и 6.1).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. `sudo xgw update-xray`, `update-singbox`, `cores update|rollback` — не запускать.
- Команды Tailscale, кроме `tailscale status`. Запуск, остановка и перезапуск служб `xgw*`,
  `tailscaled`, NetworkManager, `ssh` — кроме §8 (откат).
- Ручные `nft` (кроме `nft list`), `ip` (кроме `ip … show`), `iptables`, `tc`, `sysctl -w`.
- Править `/etc/xgw/config.toml`, `/etc/xgw/panel.json`, файлы в `/opt/xgw`, `/var/lib/xgw`,
  `/etc/systemd`. Нажимать в панели что-либо, кроме написанного; общую кнопку «Замерить
  скорость» и пункт значка «Замерить скорость сейчас» **не нажимать**.
- Править код XGW; коммитить что-либо, кроме отчёта (§9); файлы из `~/xgw-018-retest` в Git не
  класть.
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя машины → `<user>`), почту, внешние IP, токены, адреса подписок, UUID, IP и
  домены серверов VPN, MAC-адреса. **Можно и нужно** (без них данные шагов 2.2 и 6.1
  бесполезны): теги серверов как есть (`spare-eu-1a2b`, не заменять на «С-8»), первые 8 знаков
  отпечатков, отображаемые имена серверов вроде «EU-auto», коды стран, имена подписок,
  внутренние подсети, версии.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Перепроверяю исправления XGW 0.1.18 после ночного испытания. По пунктам:
(1) Переустановка XGW с исправленным кодом: Xray перезапустится — интернет дома пропадёт на
несколько секунд.
(2) Замер скорости одного запасного сервера (до 3 МБ через VPN) и просьба нажать в панели
иконку ↻ у одного сервера.
(3) Сбор данных о сервере EU-auto, у которого шлюз каждую минуту заново перебирает способы
обхода, — только чтение журнала и базы шлюза.
Можно согласиться не на все пункты.»

Дождись ответа и запиши, на что заказчик согласился. Против пункта 1 — выполнить только
шаг 2 (данные) и §9 (отчёт). Против пункта 2 — шаг 5 пропустить. Против пункта 3 — шаги 2.2 и
6.1 пропустить.

Шаг 1.2. Каталог и скрипты. `tspucheck.py` — из прошлого испытания (или заново из его
программы); `eucheck.py` — новый (только чтение базы шлюза и конфига Xray, адресов не
печатает). Скопируй блок **целиком**, от первой строки до последней:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-018-retest/before" "$HOME/xgw-018-retest/after" && chmod 700 "$HOME/xgw-018-retest" && { test -f "$HOME/xgw-018-test/tspucheck.py" && cp "$HOME/xgw-018-test/tspucheck.py" "$HOME/xgw-018-retest/" || awk "/<<'PY'\$/{f=1;next} /^PY\$/{f=0} f" ~/zcod/xgw/docs/TEST-PLAN-REAL-MACHINE-0.1.18-tspu-speed-tray.md > "$HOME/xgw-018-retest/tspucheck.py"; } && cat > "$HOME/xgw-018-retest/eucheck.py" <<'EU'
"""Перепроверка 0.1.18: данные о серверах с данным именем (по умолчанию EU-auto), у которых
эскалация обхода повторяется каждую минуту. Только чтение: база шлюза и рабочий конфиг Xray.
Адресов и ключей серверов не печатает. Запуск: sudo python3 eucheck.py [ИМЯ] [ЧАСОВ]
"""

import json
import re
import sqlite3
import sys
import time

DB = "/var/lib/xgw/state.db"
XRAY = "/etc/xgw/xray/config.json"
NAME = sys.argv[1] if len(sys.argv) > 1 else "EU-auto"
HOURS = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def stamp(ts):
    return time.strftime("%d.%m %H:%M:%S", time.localtime(float(ts))) if ts else "—"


def profile(outbound):
    """Как сервер заведён в Xray: мост к sing-box, дробление, нарезка или обычный Xray."""
    if not outbound:
        return "нет в рабочем конфиге"
    if outbound.get("protocol") == "socks":
        servers = (outbound.get("settings") or {}).get("servers") or [{}]
        first = servers[0] if isinstance(servers[0], dict) else {}
        if first.get("address") in ("127.0.0.1", "::1"):
            users = first.get("users") or [{}]
            return f"мост к sing-box ({(users[0] or {}).get('user', '?')})"
    dialer = ((outbound.get("streamSettings") or {}).get("sockopt") or {}).get("dialerProxy")
    return {"fragment": "xray+frag", "fragment-split": "xray+split"}.get(dialer, "xray")


db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = db.execute(
    "SELECT fingerprint, tag, role, source, name FROM nodes WHERE name LIKE ? ORDER BY tag",
    (f"%{NAME}%",),
).fetchall()
print(f"== серверы с «{NAME}» в имени: {len(rows)}")
tags = {}
for fingerprint, tag, role, source, name in rows:
    tags.setdefault(tag, []).append(fingerprint)
    print(f"  {tag or '—':22} {role or '—':6} {fingerprint[:8]}  подписка «{source}»  {name}")
shared = {tag: fps for tag, fps in tags.items() if tag and len(fps) > 1}
print(f"разных отпечатков: {len(rows)}, разных тегов: {len([t for t in tags if t])}; "
      f"тегов на несколько отпечатков: {len(shared)}")
for tag, fps in shared.items():
    print(f"  ОБЩИЙ ТЕГ {tag}: {', '.join(fp[:8] for fp in fps)}")

try:
    with open(XRAY, encoding="utf-8") as handle:
        applied = json.load(handle)
except OSError as exc:
    applied = {}
    print(f"рабочий конфиг Xray не прочитан: {exc}")
outbounds = {}
for item in applied.get("outbounds") or []:
    outbounds.setdefault(item.get("tag"), []).append(item)
print("== в рабочем конфиге Xray (тег: профиль; outbound'ов с таким тегом)")
for tag in sorted(tag for tag in tags if tag):
    found = outbounds.get(tag) or []
    print(f"  {tag}: {profile(found[0] if found else None)}; outbound'ов: {len(found)}")

print("== последние сканы (probe-…)")
for tag in sorted(tag for tag in tags if tag):
    probe = "probe-" + tag.split("-", 1)[1] if "-" in tag else tag
    scan = db.execute(
        "SELECT verdict, bytes, seconds, error, ts FROM scans WHERE probe_tag = ?", (probe,),
    ).fetchone()
    if scan:
        verdict, size, seconds, error, ts = scan
        print(f"  {probe}: {verdict}, {size} байт за {seconds:.1f} с, {stamp(ts)}"
              + (f" — {IP.sub('<ip>', error)}" if error else ""))
    else:
        print(f"  {probe}: сканов нет")

meta = dict(db.execute("SELECT key, value FROM meta WHERE key IN (?, ?)",
                       ("profile_trials", "core_settings")).fetchall())
fingerprints = {fp for fp, *_rest in rows}
print("== пробы профилей и выученное (profile_trials) по этим отпечаткам")
try:
    trials = json.loads(meta.get("profile_trials") or "{}")
except ValueError:
    trials = {}
for section in ("trials", "switched", "escalations", "escalated", "unstable"):
    part = trials.get(section)
    if not isinstance(part, dict):
        continue
    for key, value in part.items():
        if key in fingerprints:
            text = json.dumps(value, ensure_ascii=False)
            text = re.sub(r"(1[6-9]\d{8}(?:\.\d+)?)", lambda m: stamp(m.group(1)), text)
            print(f"  {section} {key[:8]}: {text[:300]}")
print("== закрепления ядра и профиля (core_settings) по этим отпечаткам")
try:
    core = json.loads(meta.get("core_settings") or "{}")
except ValueError:
    core = {}
for section, part in (core.items() if isinstance(core, dict) else ()):
    if isinstance(part, dict):
        for key, value in part.items():
            if key in fingerprints:
                print(f"  {section} {key[:8]}: {json.dumps(value, ensure_ascii=False)[:200]}")

since = time.time() - HOURS * 3600
events = db.execute(
    "SELECT ts, kind, detail FROM events WHERE ts >= ? AND kind IN ('profile', 'fragment') "
    "AND detail LIKE ? ORDER BY ts", (since, f"%{NAME}%"),
).fetchall()
print(f"== события profile/fragment с «{NAME}» за {HOURS:g} ч: {len(events)}")
for ts, kind, detail in events[-40:]:
    print(f"  {stamp(ts)} [{kind}] {IP.sub('<ip>', detail)}")
print("теги для журнала: " + " ".join(sorted(tag for tag in tags if tag)))
EU
cd "$HOME/xgw-018-retest" && sha256sum tspucheck.py eucheck.py && date
```

Ожидается: «sudo без пароля: да»; две строки:
`dfa4342cb773616ac3a72ad7ea24a539a1fcd229a01be6bfd4597cf51ef57d68  tspucheck.py` и
`60238700f7dfa354b7a83fad822bf558ded6330ada819e9d4f5b7cd2108424a9  eucheck.py`; дата. Дальше все команды — из этого каталога.

Если не так: хеш `eucheck.py` другой — блок скопирован не целиком: удали файл и повтори шаг;
снова другой — **стоп**, сообщить заказчику. Хеш `tspucheck.py` другой — удали его, выполни
`awk "/<<'PY'\$/{f=1;next} /^PY\$/{f=0} f" ~/zcod/xgw/docs/TEST-PLAN-REAL-MACHINE-0.1.18-tspu-speed-tray.md > "$HOME/xgw-018-retest/tspucheck.py"` и сверь снова.

## 2. До установки (прежний код, 2cd610a)

Шаг 2.1. Дефект 1 сейчас:

```bash
cd "$HOME/xgw-018-retest" && sudo xgw --version; git -C ~/zcod/xgw log -1 --format='%h %s'; echo "перезагрузок правил за 15 мин: $(sudo journalctl -u xgw --since '-15 min' --no-pager | grep -c 'правила сети не были загружены')" | tee "$HOME/xgw-018-retest/before/reloads.txt"; sudo xgw diag > "$HOME/xgw-018-retest/before/diag.txt"; grep -E '^(OK|WARN|FAIL) +(Перехват|QUIC):' "$HOME/xgw-018-retest/before/diag.txt"; tail -1 "$HOME/xgw-018-retest/before/diag.txt"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee "$HOME/xgw-018-retest/before/state.txt"
```

Ожидается: `xgw 0.1.18`; перезагрузок за 15 минут — больше 10 (дефект 1 на прежнем коде);
строки diag `FAIL  Перехват: …правила не загружены` и `WARN  QUIC: …`; «FAIL — 1»; состояние
`HEALTHY` (или `DEGRADED` — записать).

Шаг 2.2 (при согласии на пункт 3). Данные о EU-auto на прежнем коде:

```bash
cd "$HOME/xgw-018-retest" && sudo python3 eucheck.py EU-auto 2 | tee "$HOME/xgw-018-retest/before/eu.txt"; TAGS=$(sed -n 's/^теги для журнала: //p' "$HOME/xgw-018-retest/before/eu.txt"); for t in $TAGS; do sudo journalctl -u xgw --since '-60 min' --no-pager | grep -F -- "$t"; done | sed -E 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/<ip>/g' | sort | tail -80 > "$HOME/xgw-018-retest/before/eu-journal.txt"; echo "строк журнала: $(wc -l < "$HOME/xgw-018-retest/before/eu-journal.txt")"; tail -15 "$HOME/xgw-018-retest/before/eu-journal.txt"
```

Ожидается: «серверы с «EU-auto» в имени: N» и их список (тег, роль, отпечаток, подписка,
имя); строка «разных отпечатков …, разных тегов …»; профили в рабочем конфиге; сканы;
пробы профилей; события за 2 часа (по отчёту — много); строки журнала с этими тегами («скан
spare-…: …», переводы профилей). Записать всё как есть.

Если не так: «серверы с «EU-auto» в имени: 0» — спроси заказчика, как сервер называется в
панели (часть имени, без адреса), и повтори шаг, заменив `EU-auto` в обоих местах команды
на это имя. Событий за 2 часа 0 — записать «цикл сейчас не идёт».

## 3. Установка исправлений (при согласии на пункт 1)

Шаг 3.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout tspu-speed-tray && git pull --ff-only && git log -1 --format='%h %s' && grep -q SPEED_SCAN_WAIT src/xgw/daemon.py && grep -q 'Испытание 25.10.2026' src/xgw/net/nft.py && echo "исправления в коде: есть"; cd "$HOME/xgw-018-retest"
```

Ожидается: «исправления в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить
заказчику.

Шаг 3.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-018-retest/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-018-retest/after/install.txt" | tail -12; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-018-retest"
```

Ожидается: «код 0», «демон xgw запущен». Код не 0 — **стоп**, сохранить вывод, сообщить
заказчику (сеть не тронута).

Шаг 3.3. Шлюз здоров (ждать до 5 минут):

```bash
for i in $(seq 30); do sudo xgw status 2>&1 | grep -q '^Состояние: HEALTHY' && break; sleep 10; done; date '+%T'; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | tee "$HOME/xgw-018-retest/after/state-install.txt"
```

Ожидается: состояние — как в шаге 2.1 (или лучше); «Перехват: включён — …» **без** «ПРАВИЛА НЕ
ЗАГРУЖЕНЫ». Хуже, чем в шаге 2.1, — записать `sudo xgw status 2>&1 | head -30` (без адресов) и
**спросить заказчика**, продолжать ли.

## 4. Дефект 1: правила не перезагружаются

Шаг 4.1. Подождать 10 минут (команда ждёт сама), затем:

```bash
cd "$HOME/xgw-018-retest" && sleep 600; echo "перезагрузок правил с установки: $(sudo journalctl -u xgw --since "$(cat "$HOME/xgw-018-retest/install-time.txt")" --no-pager | grep -c 'правила сети не были загружены')" | tee "$HOME/xgw-018-retest/after/reloads.txt"; sudo xgw diag > "$HOME/xgw-018-retest/after/diag.txt"; grep -E '^(OK|WARN|FAIL) +(Перехват|QUIC):' "$HOME/xgw-018-retest/after/diag.txt"; tail -1 "$HOME/xgw-018-retest/after/diag.txt"
```

Ожидается: перезагрузок — 0 (допустимо 1 в первую минуту после запуска демона); строки
`OK    QUIC: UDP/443 устройств и машины отбивается …` и `Перехват` без FAIL (или строки
`Перехват` нет вовсе); «FAIL — 0».

Если не так: перезагрузки идут (больше 2) — **дефект «правила по-прежнему
перезагружаются»**: записать `sudo journalctl -u xgw --since "$(cat
"$HOME/xgw-018-retest/install-time.txt")" --no-pager | grep -B2 -A2 'не были загружены' | tail
-20` (без адресов). Шаги 4.2–6 выполнить всё равно.

Шаг 4.2. Счётчики правил QUIC растут (раньше их сбрасывала перезагрузка):

```bash
cd "$HOME/xgw-018-retest" && python3 tspucheck.py quic; python3 tspucheck.py quic; sudo nft list table ip xgw | grep 'udp dport 443' | grep -o 'packets [0-9]*' | tee "$HOME/xgw-018-retest/after/quic-counters.txt"
```

Ожидается: четыре строки «отбит: …»; у одного из правил (машины) `packets` не меньше 4.

## 5. Дефект 2: кнопка ↻ (при согласии на пункт 2)

Шаг 5.1. Замер одного запасного:

```bash
cd "$HOME/xgw-018-retest" && sudo python3 tspucheck.py speedone | tee "$HOME/xgw-018-retest/after/speedone.txt"
```

Ожидается: «ответ панели: принято — …»; «новый замер через N с: … Мбит/с» (N — до 60);
«иконка была занята: да».

Если не так: «нового замера за 180 с нет» — **дефект «замер одного сервера не выполнен»**:
записать `sudo journalctl -u xgw --since '-5 min' --no-pager | grep -E 'скан |замер' | tail -20`
(без адресов).

Шаг 5.2. **Попроси заказчика**: «Откройте панель XGW, раздел „Серверы“, и нажмите круглую
стрелку ↻ рядом со скоростью у любого сервера (не x100). Стрелка покрутилась и
остановилась? Цифра скорости и время замера под именем обновились (до минуты)?»

Ожидается: «покрутилась, остановилась, обновилась». Записать ответ дословно.

## 6. EU-auto на новом коде и итог

Шаг 6.1 (при согласии на пункт 3). Не раньше чем через 30 минут после установки:

```bash
cd "$HOME/xgw-018-retest" && sudo python3 eucheck.py EU-auto 0.5 | tee "$HOME/xgw-018-retest/after/eu.txt"; TAGS=$(sed -n 's/^теги для журнала: //p' "$HOME/xgw-018-retest/after/eu.txt"); for t in $TAGS; do sudo journalctl -u xgw --since "$(cat "$HOME/xgw-018-retest/install-time.txt")" --no-pager | grep -F -- "$t"; done | sed -E 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/<ip>/g' | sort | tail -80 > "$HOME/xgw-018-retest/after/eu-journal.txt"; echo "строк журнала: $(wc -l < "$HOME/xgw-018-retest/after/eu-journal.txt")"; tail -15 "$HOME/xgw-018-retest/after/eu-journal.txt"
```

(Если в шаге 2.2 имя было другим — подставь его вместо `EU-auto`.) Ожидается: те же разделы,
что в шаге 2.2; записать всё как есть, особенно строку «разных отпечатков …, разных тегов …»,
строки «ОБЩИЙ ТЕГ …» (если есть) и сколько событий за полчаса.

Шаг 6.2. Журнал и итог:

```bash
cd "$HOME/xgw-018-retest" && sudo journalctl -u xgw --since "$(cat "$HOME/xgw-018-retest/install-time.txt")" --no-pager | grep -c Traceback | sed 's/^/Traceback в xgw: /'; sudo xgw diag | tail -1; sudo xgw status | grep -E '^Состояние|^Xray|^sing-box|Перехват:' | tee "$HOME/xgw-018-retest/after/state.txt"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; echo "замеров скорости с установки: $(sudo journalctl -u xgw --since "$(cat "$HOME/xgw-018-retest/install-time.txt")" --no-pager | grep -c 'замер скорости')"
```

Ожидается: «Traceback в xgw: 0»; «FAIL — 0»; состояние `HEALTHY` (или как в шаге 2.1); службы
`active`; замеров скорости с установки — не меньше 1 (шаг 5.1).

Шаг 6.3. Если шаг 9 программы `docs/TEST-PLAN-REAL-MACHINE-0.1.18-tspu-speed-tray.md`
(наблюдение через сутки) ещё не выполнен — выполнить его через 18–30 часов **после этой
установки**, подставив в его командах время из `$HOME/xgw-018-retest/install-time.txt`, и
дополнить им отчёт 0.1.18, как там написано.

## 7. Что не делать

Не пытаться «починить» цикл EU-auto: не отключать сервер, не менять ему ядро и приоритет, не
трогать подписку. Нужны только данные.

## 8. Если что-то пошло не так (откат)

- Установка не прошла (код не 0) — сеть не тронута; ничего не откатывать.
- После установки пропал интернет или шлюз не HEALTHY дольше 10 минут — вернуть прежний код:

  ```bash
  cd ~/zcod/xgw && git checkout 2cd610a && sudo sh packaging/install.sh --yes 2>&1 | tail -5; sleep 60; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:'; git checkout tspu-speed-tray
  ```

  Ожидается: состояние как в шаге 2.1 (с дефектом 1). Сообщить заказчику.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.18-retest-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`tspu-speed-tray`), коммит «Отчёт: перепроверка 0.1.18», `git push`. Шаблон:

```markdown
# Отчёт: перепроверка 0.1.18 (правила QUIC, кнопка ↻, EU-auto)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.

## Итог
<2–4 предложения: перезагрузки правил и diag, кнопка ↻, что видно про EU-auto.>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 2.1 дефект 1 до | — | перезагрузок за 15 мин: N, FAIL — 1 |
| 2.2 EU-auto до | — | серверов N, отпечатков N, тегов N, событий за 2 ч N |
| 3.2 установка | … | код … |
| 4.1 перезагрузки после | … | с установки: N, FAIL — … |
| 4.2 счётчики QUIC | … | packets … |
| 5.1 замер одного | … | через N с, … Мбит/с |
| 5.2 кнопка у заказчика | … | ответ заказчика |
| 6.1 EU-auto после | … | событий за 30 мин N, общий тег: да/нет |
| 6.2 итог | … | Traceback 0, FAIL — … |

## Данные EU-auto
<before/eu.txt, before/eu-journal.txt, after/eu.txt, after/eu-journal.txt — целиком, теги и
отпечатки как есть>

## Выводы шагов
<остальные файлы after/*.txt и before/*.txt>

## Дефекты
<или «Не обнаружены»>

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
