# Программа испытаний XGW: почему мёртвый участник не меняется (только чтение)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§7). Пути — только абсолютные (`$HOME/xgw-rot-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома, XGW 0.1.17 с кодом ветки `android-a3`.
Клон репозитория — `~/zcod/xgw`.

Зачем. 24.10.2026 во время испытания А3.2 шлюз больше часа был в состоянии DEGRADED:
участник балансировщика (сервер Турции) «МЁРТВ» с 13:27, но шлюз не заменил его ни одним из
74 запасных, хотя «Проверить запасные» нажимали. Интернет работал; на «Главной» стоял
«Выбран вручную». По коду главная причина-кандидат — **Р1: у участников нет запасных того
же класса** (приоритет и стоимость); другие кандидаты — Р2–Р6 (записка
`docs/DIAG-DEGRADED-NO-ROTATION-2026-10-24.md`). Это ТЗ **только собирает сведения**: на
шлюзе ничего не меняется и не перезапускается. Время — около 15 минут.

Скрипт `rotcheck.py` (шаг 1.3) читает:

- `/run/xgw/status.json` — состояние, участники, запасные, их класс и сканы;
- через `sudo -n` — `config.toml` и `panel.json` (печатает только несколько настроек и
  счётчики), журнал службы `xgw`, базу `state.db` (в режиме «только чтение»).

Имена серверов и подписок он сам заменяет метками С-1…, П-1…, адреса — на `<IP>` и
`<домен>`. Таблица меток лежит в `labels.json`; в конце файл удаляется.

## 0. Запрещено

- На шлюзе: `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины,
  `install.sh` — **никогда**. Службы `xgw*`, `tailscaled`, NetworkManager, `ssh` не
  перезапускать, не останавливать и не запускать.
- Команды `xgw` — только `xgw status` (шаг 2.3). **Нельзя**: `xgw probe` (пишет сканы в
  базу), `xgw apply`, `pin`, `unpin`, `priority`, `core`, `enable`, `net`, `update-*`,
  `logs --export`.
- `sudo` — только в командах из шагов (все они только читают).
- Править `/etc/xgw/*`, `/var/lib/xgw/*`, код XGW. Нажимать что-либо в панели шлюза и в
  приложении на телефоне.
- Коммитить что-либо, кроме отчёта (§7).
- Писать в отчёт имена серверов и подписок, IP-адреса и домены, адреса tailnet
  (`100.x.y.z`, `*.ts.net`), имена устройств, ключи. Коды стран — можно. В отчёт идут
  только выводы `rotcheck.py`, прошедшие проверку утечек (шаг 5.1). `labels.json` в отчёт и
  в Git **не класть**.

Правила стопа:

- Команда спрашивает пароль — **стоп**. Пароль не вводить, сообщить заказчику.
- Заказчик говорит, что дома пропал интернет — **стоп**: это ТЗ ничего не меняет; записать
  время и сообщить заказчику.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Хочу понять, почему 24 октября шлюз больше часа был в состоянии DEGRADED и не заменил мёртвый
сервер Турции. Я только читаю состояние шлюза, его журнал и базу событий. Ничего не меняю,
службы не перезапускаю, кнопки в панели и в приложении не нажимаю; около 15 минут. Имена
серверов и подписок в отчёт не попадут. Два вопроса:
(1) Меняли ли вы после 24 октября приоритеты серверов, включали или отключали серверы,
выбирали сервер вручную или снимали выбор? Если да — что примерно.
(2) На каких серверах вы ставили приоритет «Высокий»: сколько их и какой страны, если
помните?»

Записать ответы в отчёт. Если заказчик против — **стоп**, испытание не проводится.

Шаг 1.2. Папка и проверка sudo:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-rot-test/out" && chmod 700 "$HOME/xgw-rot-test" && cd "$HOME/xgw-rot-test" && date; python3 --version; systemctl is-active xgw
```

Ожидается: «sudo без пароля: да», дата, `Python 3.12.…`, `active`.
Если не так:

- нет строки «sudo без пароля: да» — **стоп**, попросить заказчика разрешить sudo без
  пароля на время испытаний;
- вместо `active` другое — записать в отчёт и продолжать (ничего не запускать).

Шаг 1.3. Скрипт. Скопируй команду целиком (до строки `ROT_EOF` включительно):

```bash
cat > "$HOME/xgw-rot-test/rotcheck.py" <<'ROT_EOF'
"""Разбор XGW: почему мёртвый участник балансировщика не меняется (DEGRADED). Только чтение.

python3 rotcheck.py now                 состояние, участники, класс, запасные, вывод по коду
python3 rotcheck.py table               все серверы: роль, страна, уровень, цена, скан, скорость
python3 rotcheck.py events С ПО         события шлюза из базы за период («2026-10-24 00:00»)
python3 rotcheck.py journal С ПО        журнал службы xgw за период: сканы, замены, ошибки
python3 rotcheck.py mask < ФАЙЛ         маскировать вывод (имена серверов, подписок, адреса)
python3 rotcheck.py leaks ФАЙЛ…         нет ли в файлах имён серверов, подписок и IP

Ничего не меняет. sudo -n — только для чтения: cat config.toml и panel.json, journalctl,
база state.db (открывается в режиме «только чтение»). Имена серверов и подписок заменяются
метками С-1…, П-1…; таблица меток — labels.json рядом со скриптом (в отчёт не класть).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELS = HERE / "labels.json"
ROOT = os.environ.get("XGW_ROOT", "")  # только для проверки скрипта на стенде
SUDO = [] if ROOT else ["sudo", "-n"]
STATUS = Path(ROOT + "/run/xgw/status.json")
CONFIG = ROOT + "/etc/xgw/config.toml"
PANEL = ROOT + "/etc/xgw/panel.json"
DB = ROOT + "/var/lib/xgw/state.db"
RANK = {"high": 0, "medium": 1, "low": 2}
LEVEL = {"high": "высокий", "medium": "средний", "low": "низкий"}
REPLACEABLE = ("OK", "SLOW")
TAG_RE = re.compile(r"\b(proxy|spare|probe)-([a-z]{2})-([0-9a-f]{4,8})\b")
SCAN_RE = re.compile(r"скан (proxy|spare)-([a-z]{2})-([0-9a-f]{4,8}): ([A-Z_]+)")
KEEP_QUOTED = {"высокий", "средний", "низкий", "Высокий", "Средний", "Низкий", "Авто"}
CONFIG_WORDS = {
    "filters", "probe", "speed", "apply", "routing", "watchdog", "capture", "xray", "core",
    "fragment", "notify", "panel", "network", "tailscale", "manual", "dns", "status", "config",
    "xgw", "journal", "sing-box", "net", "engine", "builder", "daemon", "cost", "priority",
}
FILE_EXT = {"toml", "json", "py", "db", "service", "pcap", "md", "txt", "log", "sh", "conf",
            "so", "apk", "url", "target", "socket", "timer"}
# Имена подписок, совпадающие с техническими словами вывода, не заменяются (и не утечка).
TECH_WORDS = {"main", "proxy", "spare", "probe", "xray", "auto", "manual", "high", "medium",
              "low", "pin", "apply", "reserve", "rotation", "priority", "panel", "speed"}
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")


# --- чтение (только чтение) ------------------------------------------------------------

def sh(args: list[str], timeout: float = 60.0) -> tuple[int, str]:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return done.returncode, done.stdout if done.returncode == 0 else done.stderr


def read_root(path: str) -> str | None:
    """Файл, читаемый только root: sudo -n cat. None — нет файла или доступа."""
    if ROOT:
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            return None
    code, out = sh([*SUDO, "cat", path])
    return out if code == 0 else None


def load_status() -> tuple[dict, str]:
    try:
        return json.loads(STATUS.read_text(encoding="utf-8")), ""
    except PermissionError:
        raw = read_root(str(STATUS))
        if raw is not None:
            return json.loads(raw), ""
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"статус не прочитан: {exc}"
    return {}, "статус не прочитан"


def load_config() -> tuple[dict, str]:
    raw = read_root(CONFIG)
    if raw is None:
        return {}, "config.toml не прочитан (sudo -n?) — ниже значения по умолчанию"
    try:
        return tomllib.loads(raw), ""
    except tomllib.TOMLDecodeError as exc:
        return {}, f"config.toml не разобран: {exc}"


def load_panel() -> dict:
    raw = read_root(PANEL)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def db_rows(sql: str, params: list) -> list:
    """Строки базы state.db — открытой только для чтения, от root."""
    code = (
        "import json,sqlite3,sys\n"
        "c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True,timeout=10)\n"
        "print(json.dumps(c.execute(sys.argv[2],json.loads(sys.argv[3])).fetchall()))\n"
    )
    rc, out = sh([*SUDO, sys.executable, "-I", "-c", code, DB, sql, json.dumps(params)])
    if rc != 0:
        raise SystemExit(f"база не прочитана: {out.strip()[:200]}")
    return json.loads(out)


# --- метки и маскирование ----------------------------------------------------------------

def labels() -> dict:
    try:
        data = json.loads(LABELS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    for key in ("names", "tags", "subs"):
        data.setdefault(key, {})
    data.setdefault("next", {"С": 1, "П": 1})
    return data


def save_labels(data: dict) -> None:
    LABELS.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    LABELS.chmod(0o600)


def suffix(tag: str) -> str:
    """«tr-1a2b3c4d» из «proxy-tr-1a2b3c4d»: одинаков у участника и запасного."""
    return tag.split("-", 1)[1] if "-" in tag else tag


def learn(status: dict) -> dict:
    """Метки С-N (серверы: сначала участники) и П-N (подписки) — постоянные между командами."""
    data = labels()
    for entry in [*(status.get("members") or []), *(status.get("spares") or [])]:
        key = suffix(entry.get("tag", ""))
        label = data["tags"].get(key) or data["names"].get(entry.get("name") or "")
        if not label:
            label = f"С-{data['next']['С']}"
            data["next"]["С"] += 1
        data["tags"][key] = label
        if entry.get("name"):
            data["names"][entry["name"]] = label
    subs = [sub.get("name") for sub in status.get("subscriptions") or []]
    subs += [entry.get("source") for entry in [*(status.get("members") or []),
                                               *(status.get("spares") or [])]]
    for name in subs:
        if name and name not in data["subs"]:
            data["subs"][name] = f"П-{data['next']['П']}"
            data["next"]["П"] += 1
    save_labels(data)
    return data


def known_names(data: dict) -> dict[str, str]:
    """Имя сервера или подписки → метка; короткие и технические слова не в счёт."""
    names = {**data["subs"], **data["names"]}
    return {name: label for name, label in names.items()
            if len(name.strip()) >= 3 and name.strip().lower() not in TECH_WORDS}


def mask(text: str, data: dict) -> str:
    names = known_names(data)
    for name in sorted(names, key=len, reverse=True):
        if name:
            text = text.replace(name, names[name])
            if name != name.strip():
                text = text.replace(name.strip(), names[name])

    def tag(match: re.Match) -> str:
        role, country, prefix = match.groups()
        return f"{role}-{country}-{data['tags'].get(f'{country}-{prefix}', '?')}"

    text = TAG_RE.sub(tag, text)

    def quoted(match: re.Match) -> str:
        inner = match.group(1)
        if inner in KEEP_QUOTED or re.fullmatch(r"[СП]-\d+|[СП]-\?", inner.strip()):
            return match.group(0)
        return "«…»"

    text = re.sub(r"«([^«»]*)»", quoted, text)
    text = IPV4_RE.sub("<IP>", text)
    text = re.sub(
        r"(?i)\b(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}\b",
        lambda m: "<IPv6>" if ("::" in m.group(0) or re.search(r"(?i)[a-f]", m.group(0)))
        else m.group(0),
        text,
    )

    def domain(match: re.Match) -> str:
        whole = match.group(0)
        parts = whole.lower().split(".")
        if parts[0] in CONFIG_WORDS or parts[-1] in FILE_EXT:
            return whole
        return "<домен>"

    text = re.sub(r"(?i)\b(?:[a-z0-9-]+\.)+[a-z]{2,24}\b(?![_a-z0-9])", domain, text)
    text = re.sub(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
                  "<uuid>", text)
    text = re.sub(r"(?i)\b[0-9a-f]{16,}\b", "<hex>", text)
    text = re.sub(r"\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{24,}\b",
                  "<токен>", text)
    return text


# --- разбор -------------------------------------------------------------------------------

def clock(ts: float | None) -> str:
    if not ts:
        return "—"
    return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")


def minutes(seconds: float) -> str:
    total = int(seconds // 60)
    return f"{total // 60} ч {total % 60} мин" if total >= 60 else f"{total} мин"


def price(entry: dict) -> str:
    value = float(entry.get("cost") or 0.0)
    if value == 0:
        return "безлимит"
    return "x" + f"{value:.2f}".rstrip("0").rstrip(".")


def level(entry: dict) -> str:
    return entry.get("priority") or "medium"


def klass(entry: dict) -> tuple[int, float]:
    return RANK.get(level(entry), 1), float(entry.get("cost") or 0.0)


def klass_text(value: tuple[int, float]) -> str:
    name = {v: LEVEL[k] for k, v in RANK.items()}[value[0]]
    return f"уровень «{name}», {price({'cost': value[1]})}"


def mapped(entry: dict) -> bool:
    """Сопоставлен с подпиской: отпечаток полный, а не только hex-часть тега."""
    parts = entry.get("tag", "").split("-", 2)
    return len(parts) == 3 and entry.get("fingerprint", "") not in ("", parts[2])


def settings(conf: dict) -> dict:
    filters, probe = conf.get("filters") or {}, conf.get("probe") or {}
    return {
        "max_members": int(filters.get("max_members", 5)),
        "rotate_after_min": int(filters.get("rotate_after_min", 15)),
        "scan_spares_minutes": int(probe.get("scan_spares_minutes", 60)),
        "restart_window": str((conf.get("apply") or {}).get("restart_window", "04:00-05:00")),
        "home_country": str((conf.get("routing") or {}).get("home_country", "ru")),
        "interval_s": int((conf.get("watchdog") or {}).get("interval_s", 30)),
    }


def cmd_now() -> int:
    status, err = load_status()
    if not status:
        print(err)
        return 1
    data = learn(status)
    conf, conf_err = load_config()
    panel = load_panel()
    cfg = settings(conf)
    now = time.time()
    lab = lambda entry: data["tags"].get(suffix(entry.get("tag", "")), "С-?")  # noqa: E731
    country = lambda entry: (entry.get("tag", "--").split("-") + ["?", "?"])[1]  # noqa: E731
    members = status.get("members") or []
    spares = status.get("spares") or []
    print(f"== Сейчас: {clock(now)} ==")
    age = now - float(status.get("updated") or 0)
    if age > 180:
        print(f"ВНИМАНИЕ: статус обновлялся {minutes(age)} назад — демон, похоже, не работает")
    state, since = status.get("state"), status.get("since")
    print(f"Состояние: {state} с {clock(since)} ({minutes(now - float(since or now))}) — "
          f"{status.get('action') or ''}")
    xray = status.get("xray") or {}
    print(f"Демон: {'работает' if status.get('daemon') else 'НЕ работает'}; Xray отвечает: "
          f"{'да' if xray.get('ok') else 'НЕТ'} ({xray.get('version') or '?'}); probe.url: "
          f"{'НЕ отвечает' if status.get('probe_target') else 'отвечает'}; ожидает окна "
          f"перезапуска: {'ДА' if status.get('pending_restart') else 'нет'}")
    pin = status.get("pin")
    if pin:
        owner = next((e for e in [*members, *spares]
                      if suffix(e.get("tag", "")) == suffix(pin.get("tag", ""))), None)
        role = "участник" if (owner or {}).get("tag", "").startswith("proxy-") else "запасной"
        print(f"Ручной выбор: ЕСТЬ — {role} {data['tags'].get(suffix(pin['tag']), 'С-?')} "
              f"({suffix(pin['tag']).split('-')[0]}), "
              f"{'бессрочно' if pin.get('until') is None else 'до ' + clock(pin['until'])}, "
              f"с {clock(pin.get('since'))}; не отвечает: "
              f"{'да, с ' + clock(pin['down']) if pin.get('down') else 'нет'}")
    else:
        print("Ручной выбор: нет (автовыбор)")
    main = status.get("main")
    print(f"Основной сервер (speed.sticky = {'да' if status.get('sticky') else 'нет'}): "
          f"{data['tags'].get(suffix(main['tag']), 'С-?') if main else 'нет'}")
    if conf_err:
        print(conf_err)
    fresh_window = cfg["scan_spares_minutes"] * 120 + 120
    print(f"Настройки: max_members = {cfg['max_members']}, rotate_after_min = "
          f"{cfg['rotate_after_min']} мин, scan_spares_minutes = {cfg['scan_spares_minutes']} "
          f"мин, restart_window = {cfg['restart_window']}, watchdog.interval_s = "
          f"{cfg['interval_s']}")
    print(f"Свежим считается скан не старше {fresh_window // 60} мин (2 × scan_spares_minutes + 2)")
    levels = panel.get("priority") if isinstance(panel.get("priority"), dict) else {}
    disabled = [fp for fp in panel.get("disabled") or [] if isinstance(fp, str)]
    removed = [fp for fp in panel.get("removed") or [] if isinstance(fp, str)]
    high = sum(1 for v in levels.values() if v == "high")
    low = sum(1 for v in levels.values() if v == "low")
    print(f"panel.json: уровень «высокий» у {high} серверов, «низкий» у {low}; отключено вами "
          f"{len(disabled)} (из них «высокий» {sum(levels.get(fp) == 'high' for fp in disabled)}, "
          f"«низкий» {sum(levels.get(fp) == 'low' for fp in disabled)}, «средний» "
          f"{sum(fp not in levels for fp in disabled)}); убрано {len(removed)}")

    print(f"\nУчастники ({len(members)} из max_members {cfg['max_members']}):")
    for entry in members:
        if entry.get("alive") is None:
            health = "нет данных"
        elif entry.get("alive"):
            health = f"жив {entry.get('delay_ms')} мс"
        else:
            dead = entry.get("dead_since")
            health = f"МЁРТВ с {clock(dead)}" + (f" ({minutes(now - dead)})" if dead else "")
        marks = " ← основной" if entry.get("main") else ""
        if entry.get("tag") in (status.get("selecting") or []):
            marks += " ← выбран ядром"
        print(f"  {lab(entry):<6} {country(entry)}  {LEVEL.get(level(entry), level(entry)):<8} "
              f"{price(entry):<9} {data['subs'].get(entry.get('source') or '', 'П-?'):<5} "
              f"{health}{'' if mapped(entry) else '  НЕ сопоставлен с подпиской'}{marks}")
    if not members:
        print("  (нет)")
        return 0
    tier = min(klass(entry) for entry in members)
    print(f"Класс участников: {klass_text(tier)}")

    groups: dict[tuple[int, float], list[dict]] = {}
    for entry in spares:
        groups.setdefault(klass(entry), []).append(entry)
    unmapped_spares = [e for e in spares if not mapped(e)]
    print(f"\nЗапасные: {len(spares)} (не сопоставлены с подпиской: {len(unmapped_spares)})")
    print("  класс                          всего  OK/SLOW свежих  не прошли  устарели  "
          "не проверены")

    def fresh(entry: dict) -> bool:
        return bool(entry.get("scanned")) and now - float(entry["scanned"]) <= fresh_window

    for key in sorted(groups):
        rows = groups[key]
        good = sum(e.get("verdict") in REPLACEABLE and fresh(e) for e in rows)
        bad = sum(e.get("verdict") not in (None, *REPLACEABLE) and fresh(e) for e in rows)
        stale = sum(e.get("verdict") is not None and not fresh(e) for e in rows)
        never = sum(e.get("verdict") is None for e in rows)
        mark = "  ← класс участников" if key == tier else ""
        print(f"  {klass_text(key):<30} {len(rows):>5}  {good:>14}  {bad:>9}  {stale:>8}  "
              f"{never:>12}{mark}")
    if tier not in groups:
        print(f"  {klass_text(tier):<30} {0:>5}  ← класс участников: запасных нет")
    reserve = next((e for e in spares if e.get("reserve")), None)
    if reserve:
        print(f"Резервный выход: {lab(reserve)} ({klass_text(klass(reserve))})")

    same = [e for e in groups.get(tier, []) if mapped(e)]
    ready = [e for e in same if e.get("verdict") in REPLACEABLE and fresh(e)]
    dead = [e for e in members if e.get("alive") is False]
    overdue = [e for e in dead if e.get("dead_since")
               and now - float(e["dead_since"]) >= cfg["rotate_after_min"] * 60]
    unmapped_members = [e for e in members if not mapped(e)]
    degraded = state == "DEGRADED"
    yes = lambda flag: "ДА " if flag else "нет"  # noqa: E731

    print("\nВЫВОД ПО КОДУ (daemon._rotate, apply/rotation.plan_rotation):")
    if not degraded:
        print(f"  Сейчас не DEGRADED ({state}) — Р2, Р4 и Р6 по текущему состоянию не решить; "
              "смотри события и журнал 24.10 (шаги 4–5).")
    found = []
    flag = not same
    found += ["Р1"] if flag else []
    print(f"  Р1 {yes(flag)} — запасных того же класса ({klass_text(tier)}): {len(same)}; "
          f"серверов этого класса всего (в работе + запасные): {len(members) + len(same)}"
          + (f"; участников {len(members)} < max_members {cfg['max_members']} — класс "
             "исчерпан" if len(members) < cfg["max_members"] else ""))
    flag = bool(same) and not ready
    found += ["Р2"] if flag and degraded else []
    print(f"  Р2 {yes(flag)} — из них со свежим OK/SLOW: {len(ready)}")
    flag = bool(unmapped_members)
    found += ["Р3"] if flag else []
    print(f"  Р3 {yes(flag)} — участников, не сопоставленных с подпиской: {len(unmapped_members)}")
    flag = degraded and bool(dead) and not overdue
    found += ["Р4"] if flag else []
    print(f"  Р4 {yes(flag)} — мёртвых участников: {len(dead)}, мёртвых дольше "
          f"rotate_after_min ({cfg['rotate_after_min']} мин): {len(overdue)}")
    flag = bool(status.get("pending_restart"))
    found += ["Р5"] if flag else []
    print(f"  Р5 {yes(flag)} — новый конфиг ждёт окна перезапуска {cfg['restart_window']}")
    flag = degraded and bool(overdue) and bool(ready) and not unmapped_members
    found += ["Р6"] if flag else []
    print(f"  Р6 {yes(flag)} — по правилам замена должна была пройти (есть мёртвый дольше "
          "rotate_after_min и годный запасной того же класса)")
    print(f"ИТОГ: {', '.join(found) if found else 'причина по текущему состоянию не видна'}")
    return 0


def cmd_table() -> int:
    status, err = load_status()
    if not status:
        print(err)
        return 1
    data = learn(status)
    now = time.time()
    print("метка   роль      страна уровень  цена      подписка  скан            "
          "скана мин назад  Мбит/с  отметки")
    for entry in [*(status.get("members") or []), *(status.get("spares") or [])]:
        member = entry.get("tag", "").startswith("proxy-")
        if member:
            scan = "жив" if entry.get("alive") else ("МЁРТВ" if entry.get("alive") is False
                                                     else "нет данных")
            ago = "—"
        else:
            scan = entry.get("verdict") or "не проверялся"
            ago = str(int((now - float(entry["scanned"])) // 60)) if entry.get("scanned") else "—"
        speed = entry.get("speed_mbps")
        marks = []
        if entry.get("main"):
            marks.append("основной")
        if entry.get("reserve"):
            marks.append("резервный выход")
        if not mapped(entry):
            marks.append("не сопоставлен")
        if entry.get("core") and entry.get("core") != "xray":
            marks.append(entry["core"])
        print(f"{data['tags'].get(suffix(entry['tag']), 'С-?'):<7} "
              f"{'участник' if member else 'запасной':<9} {entry['tag'].split('-')[1]:<6} "
              f"{LEVEL.get(level(entry), level(entry)):<8} {price(entry):<9} "
              f"{data['subs'].get(entry.get('source') or '', 'П-?'):<9} {scan:<15} {ago:>16}  "
              f"{'' if speed is None else round(float(speed), 1)!s:>6}  {', '.join(marks)}")
    return 0


def period(args: list[str]) -> tuple[float, float, str, str]:
    if len(args) != 2:
        raise SystemExit("нужно: С ПО, например \"2026-10-24 00:00\" \"2026-10-25 00:00\"")
    start, end = (time.mktime(time.strptime(a, "%Y-%m-%d %H:%M")) for a in args)
    return start, end, args[0], args[1]


def cmd_events(args: list[str]) -> int:
    start, end, a, b = period(args)
    status, _err = load_status()
    data = learn(status) if status else labels()
    rows = db_rows("SELECT ts, kind, detail FROM events WHERE ts >= ? AND ts < ? ORDER BY id",
                   [start, end])
    print(f"== События шлюза {a} — {b} (база state.db) ==")
    kinds: dict[str, int] = {}
    for _ts, kind, _detail in rows:
        kinds[kind] = kinds.get(kind, 0) + 1
    print(f"Всего: {len(rows)}. По видам: "
          + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])))
    states = {"HEALTHY", "DEGRADED", "ALL_DEAD", "RESERVE", "WAN_DOWN", "XRAY_DOWN", "LEAK",
              "PROBE_TARGET_UNREACHABLE"}
    sections = [
        ("Переходы состояния", lambda k: k in states),
        ("Замены участников (rotation)", lambda k: k == "rotation"),
        ("Смены класса и уровня (priority)", lambda k: k == "priority"),
        ("Ручной выбор (pin)", lambda k: k == "pin"),
        ("Основной сервер (main)", lambda k: k == "main"),
        ("Применение конфига (apply, config)", lambda k: k in ("apply", "config")),
        ("Резервный выход (reserve)", lambda k: k == "reserve"),
        ("Проверка запасных и probe.url (probe)", lambda k: k == "probe"),
    ]
    for title, wanted in sections:
        picked = [row for row in rows if wanted(row[1])]
        print(f"\n{title}: {len(picked)}")
        shown = picked if len(picked) <= 40 else picked[:20] + [None] + picked[-20:]
        for row in shown:
            if row is None:
                print(f"  … пропущено {len(picked) - 40} …")
                continue
            ts, kind, detail = row
            print(f"  {clock(ts)[11:]}  {kind}: {mask(detail, data)}")
    return 0


def cmd_journal(args: list[str]) -> int:
    _start, _end, a, b = period(args)
    status, _err = load_status()
    data = learn(status) if status else labels()
    source = os.environ.get("ROTCHECK_JOURNAL")
    if source:
        text = Path(source).read_text(encoding="utf-8")
    else:
        code, text = sh([*SUDO, "journalctl", "-u", "xgw", "--since", a, "--until", b,
                         "--no-pager", "-o", "short-iso"], timeout=180)
        if code != 0:
            print(f"журнал не прочитан: {text.strip()[:200]}")
            return 1
    # «2026-10-24T13:30:00+0300 имя-машины xgw[123]: текст» → «13:30:00 текст»
    lines = [
        re.sub(r"^\d{4}-\d\d-\d\dT(\d\d:\d\d:\d\d)\S*\s+\S+\s+\S+?:\s", r"\1 ", line)
        for line in text.splitlines() if not line.startswith("-- ")
    ]
    print(f"== Журнал службы xgw {a} — {b} ==")
    print(f"Строк: {len(lines)}")
    tier = None
    classes: dict[str, tuple[int, float]] = {}
    if status:
        for entry in [*(status.get("members") or []), *(status.get("spares") or [])]:
            classes[suffix(entry["tag"])] = klass(entry)
        if status.get("members"):
            tier = min(klass(entry) for entry in status["members"])

    def count(pattern: str, title: str, show: int = 6) -> None:
        found = [line for line in lines if re.search(pattern, line)]
        print(f"\n{title}: {len(found)}")
        for line in (found if len(found) <= show else found[: show // 2] + found[-show // 2:]):
            print("  " + mask(line, data)[:240])

    count(r"демон XGW запущен", "Запуски демона («демон XGW запущен»)", 10)
    count(r"настройки изменены|демон XGW остановлен", "Остановки и перечитывание настроек", 10)
    scans = [m for m in (SCAN_RE.search(line) for line in lines) if m]
    verdicts: dict[str, int] = {}
    same: dict[str, int] = {}
    for match in scans:
        role, cc, prefix, verdict = match.groups()
        if role == "spare":
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            if tier is not None and classes.get(f"{cc}-{prefix}") == tier:
                same[verdict] = same.get(verdict, 0) + 1
    members_scanned = sum(1 for m in scans if m.group(1) == "proxy")
    print(f"\nСканы: всего {len(scans)}; участников {members_scanned}; запасных "
          f"{len(scans) - members_scanned}: "
          + (", ".join(f"{k} {v}" for k, v in sorted(verdicts.items())) or "—"))
    print("  из них запасных класса нынешних участников: "
          + (", ".join(f"{k} {v}" for k, v in sorted(same.items())) or "0"))
    count(r"rotation: ", "Замены участников («rotation:»)", 20)
    count(r"priority: ", "Смены класса и уровня («priority:»)", 10)
    count(r"ожидание окна|restart_deferred|окна перезапуска", "Отложено до окна перезапуска", 10)
    count(r"ошибка API", "Ошибки API ядра", 10)
    count(r"шаг watchdog завершился ошибкой|Traceback", "Ошибки шага и Traceback", 10)
    count(r"→ (DEGRADED|ALL_DEAD|RESERVE|WAN_DOWN|XRAY_DOWN|HEALTHY|LEAK|PROBE_TARGET)",
          "Переходы состояния", 20)
    count(r"pin: |main: ", "Ручной выбор и основной сервер", 10)
    return 0


def cmd_leaks(files: list[str]) -> int:
    """Номера строк с именем сервера или подписки (из labels.json) или IPv4; сами строки не
    печатаются."""
    names = [name.strip() for name in known_names(labels())]
    found = 0
    for file in files:
        try:
            text = Path(file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{file}: не прочитан ({exc})")
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if IPV4_RE.search(line) or any(name in line for name in names):
                found += 1
                print(f"{file}:{number}: имя сервера, подписки или IP-адрес")
    print(f"утечек: {found}")
    return 0 if found == 0 else 1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    command, rest = argv[0], argv[1:]
    if command == "now":
        return cmd_now()
    if command == "table":
        return cmd_table()
    if command == "events":
        return cmd_events(rest)
    if command == "journal":
        return cmd_journal(rest)
    if command == "mask":
        status, _err = load_status()
        data = learn(status) if status else labels()
        sys.stdout.write(mask(sys.stdin.read(), data))
        return 0
    if command == "leaks":
        return cmd_leaks(rest)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
ROT_EOF
sha256sum "$HOME/xgw-rot-test/rotcheck.py"; python3 "$HOME/xgw-rot-test/rotcheck.py" | head -2
```

Ожидается: строка хеша начинается с `b20f68654de45fb40e113b1c19268266c420358c8e2e2bd2c10f433771f9b914`; затем «Разбор XGW: почему мёртвый участник
балансировщика не меняется (DEGRADED). Только чтение.»
Если хеш другой: повтори шаг 1.3 (команда скопирована не целиком). Не совпал и со второго
раза — **стоп**, сообщить заказчику.

## 2. Состояние сейчас

Шаг 2.1. Сводка и вывод по коду:

```bash
cd "$HOME/xgw-rot-test" && python3 rotcheck.py now | tee out/now.txt
```

Ожидается, по порядку:

- «== Сейчас: …», «Состояние: …», «Демон: работает …», «Ручной выбор: …»;
- «Настройки: max_members = …»;
- «Участники (N из max_members M):» и строки участников (метка, страна, уровень, цена,
  подписка, жив / МЁРТВ);
- «Класс участников: …»;
- таблица «Запасные» по классам;
- блок «ВЫВОД ПО КОДУ» со строками Р1–Р6 и строка «ИТОГ: …».

Если не так:

- «статус не прочитан» — записать в отчёт и перейти к шагу 3.1: история важнее;
- «config.toml не прочитан» — записать; ниже скрипт берёт значения по умолчанию;
- «ВНИМАНИЕ: статус обновлялся … назад» — записать (демон, похоже, не работает) и
  продолжать. Ничего не запускать.

Записать в отчёт: строки «Состояние», «Ручной выбор», «Настройки», «Участники (N из
max_members M)», «Класс участников», строку таблицы «Запасные» с пометкой «← класс
участников», строки Р1–Р6 и «ИТОГ».

Шаг 2.2. Все серверы одной таблицей:

```bash
cd "$HOME/xgw-rot-test" && python3 rotcheck.py table | tee out/table.txt | head -8; grep -c "участник" out/table.txt; grep -c "запасной" out/table.txt
```

Ожидается: заголовок «метка   роль …», строки серверов, затем два числа: сколько
участников и сколько запасных (около 4 и 74).
Если не так: записать вывод, продолжать.

Шаг 2.3. `xgw status` (маскированный):

```bash
cd "$HOME/xgw-rot-test" && sudo -n xgw status 2>&1 | python3 rotcheck.py mask | tee out/status.txt | head -12
```

Ожидается: первая строка «Состояние: …», дальше Xray, перехват, ручной выбор, участники.
Если не так (ошибка, «рабочего конфига нет»): записать первую строку, продолжать.

## 3. События шлюза из базы

Шаг 3.1. День 24.10:

```bash
cd "$HOME/xgw-rot-test" && python3 rotcheck.py events "2026-10-24 00:00" "2026-10-25 00:00" | tee out/events-1024.txt | head -3
```

Ожидается: «== События шлюза 2026-10-24 00:00 — 2026-10-25 00:00 (база state.db) ==», затем
«Всего: N. По видам: …».
Если «база не прочитана» — записать текст ошибки и перейти к шагу 4.1.

Записать в отчёт из `out/events-1024.txt`:

- сколько событий в разделах «Замены участников (rotation)» и «Смены класса и уровня
  (priority)»;
- все строки раздела «Переходы состояния» (время и «A → B»);
- строки раздела «Ручной выбор (pin)».

Шаг 3.2. Последние сутки (как шлюз ведёт себя сейчас):

```bash
cd "$HOME/xgw-rot-test" && python3 rotcheck.py events "$(date -d '-1 day' '+%Y-%m-%d %H:%M')" "$(date -d '+1 min' '+%Y-%m-%d %H:%M')" | tee out/events-now.txt | head -3
```

Ожидается: то же, что в 3.1, за последние сутки. Записать «Всего» и число событий
«rotation».

## 4. Журнал службы xgw

Шаг 4.1. Время испытания А3.2:

```bash
cd "$HOME/xgw-rot-test" && python3 rotcheck.py journal "2026-10-24 13:00" "2026-10-24 16:00" | tee out/journal-1024.txt | head -3
```

Ожидается: «== Журнал службы xgw 2026-10-24 13:00 — 2026-10-24 16:00 ==», «Строк: N», где N
больше 0.
Если «Строк: 0» — журнал за 24.10 не сохранился: записать и продолжать.
Если «журнал не прочитан» — записать текст и продолжать.

Записать в отчёт из `out/journal-1024.txt`: «Запуски демона», строку «Сканы: …» и строку
«из них запасных класса нынешних участников», «Замены участников», «Отложено до окна
перезапуска», «Ошибки шага и Traceback».

Шаг 4.2. Утро 24.10, до установки (был ли сервер мёртв раньше):

```bash
cd "$HOME/xgw-rot-test" && python3 rotcheck.py journal "2026-10-24 00:00" "2026-10-24 13:26" | tee out/journal-before.txt | head -3
```

Ожидается: как в 4.1. Записать в отчёт раздел «Переходы состояния» (есть ли «→ DEGRADED» до
13:26) и «Замены участников».

## 5. Итог

Шаг 5.1. Проверка утечек:

```bash
cd "$HOME/xgw-rot-test" && python3 rotcheck.py leaks out/*.txt
```

Ожидается: последняя строка «утечек: 0».
Если больше 0: строки из списка (файл и номер) в отчёт **не** вставлять — ни целиком, ни
частью. Записать в отчёт «утечка: <файл>:<номер строки>» и сообщить заказчику.

Шаг 5.2. Уборка и проверка, что ничего не изменилось:

```bash
rm -f "$HOME/xgw-rot-test/labels.json"; systemctl is-active xgw; ls "$HOME/xgw-rot-test"
```

Ожидается: `active`; в папке — `out` и `rotcheck.py`, без `labels.json`.

## 6. Если что-то пошло не так

- Скрипт упал с `Traceback` — записать в отчёт последнюю строку ошибки через маскирование
  (`… 2>&1 | tail -1 | python3 "$HOME/xgw-rot-test/rotcheck.py" mask`) и перейти к
  следующему шагу.
- Любая команда просит пароль — **стоп** (§0).
- Ничего не чинить и не перезапускать: это ТЗ только читает.

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-rotation-diag-<ДАТА>.md` в клоне `~/zcod/xgw`
(ветка `android-a3`):

```bash
cd ~/zcod/xgw && git fetch && git checkout android-a3 && git pull --ff-only && git log -1 --format='%h %s'
```

Коммит «Отчёт: почему мёртвый участник не меняется (только чтение)», `git push`. В коммит —
только файл отчёта.

Шаблон:

````markdown
# Отчёт: почему мёртвый участник не меняется (только чтение)

Дата: <…>. rotcheck.py sha256 <первые 8 знаков> — совпал. Шлюз не менялся.

## Итог
<2–4 предложения: строка «ИТОГ» из out/now.txt; что показали события и журнал 24.10:
были ли замены, сканы запасных класса участников, был ли DEGRADED до 13:26.>

## Ответы заказчика
1. <менял ли приоритеты, серверы, ручной выбор после 24.10>
2. <сколько серверов «Высокий», какой страны>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 подготовка | … | sudo да, Python …, xgw active |
| 1.3 скрипт | … | sha256 совпал |
| 2.1 сейчас | … | состояние …; участников N из M; класс …; ИТОГ … |
| 2.2 таблица | … | участников N, запасных M |
| 2.3 xgw status | … | первая строка |
| 3.1 события 24.10 | … | rotation N, priority N, переходов состояния N |
| 3.2 события за сутки | … | всего N, rotation N |
| 4.1 журнал 24.10, 13–16 ч | … | строк N, запусков N, сканов запасных N (класса участников N), замен N |
| 4.2 журнал 24.10 до 13:26 | … | DEGRADED до установки: да/нет |
| 5.1 утечки | … | утечек: 0 |
| 5.2 итог | … | active, labels.json удалён |

## Выводы шагов
<каждый файл — под своим заголовком, внутри блока ```text; файлы с утечками (5.1) не
вставлять>

### out/now.txt (целиком)
### out/table.txt (целиком)
### out/status.txt (первые 15 строк)
### out/events-1024.txt (целиком)
### out/events-now.txt (целиком)
### out/journal-1024.txt (целиком)
### out/journal-before.txt (целиком)

## Наблюдения

## Что не проверено и почему

## Итоговое состояние
<шлюз не менялся: xgw active, ничего не перезапускалось; labels.json удалён; файлы out/ — в
~/xgw-rot-test у заказчика.>
````

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
