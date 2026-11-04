# Проверка XGW 0.2.0: отпечатки одиночных серверов с меняющимся полем, замеры запасных

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, делаешь **снимок
  экрана** и смотришь на него, выполняешь JavaScript в консоли страницы.

Одна сессия, около полутора часов (из них около 45 минут — ожидание). Режим бесплатных серверов
в этой проверке **не трогается** — дом всё время идёт через подписку.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J2) — выполни её в консоли
   страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-a6c/…`. Время шага — по выводу `date` в
   команде, не по памяти.
5. **Метка времени — до нажатия.** Где в шаге есть команда «Метка», выполни её **перед**
   нажатием в браузере, а команду проверки — **после**.
6. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
7. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
8. Экземпляр этого ТЗ держи в `$HOME/xgw-a6c/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2 (это тот же помощник, что в прошлой проверке, — сумма та же).
9. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `b6check.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
10. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши
    дословно строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
    «Наблюдения», со словом «предположение».
11. **Журнал после метки** читай не раньше чем через 30 секунд после того, как помощник сказал
    «список серверов обновлён»: строка демона о времени обновления пишется в конце его шага (в
    прошлый раз первое чтение было на 15 секунд раньше неё).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.31 и sing-box
1.14.4, принятые шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 282) и зачем проверка

Прошлая проверка показала: у ~21 одиночного сервера подписки одно из полей (путь, SNI или
похожее) другое при каждом скачивании. Код прошлой волны давал такому серверу **новый отпечаток
при каждом обновлении подписки** — и шлюз каждый час считал ~20 запасных новыми: сканировал их
заново, а очередь замеров скорости запасных («Замер скорости 0 из 20» в панели) начиналась
сначала и не доходила до конца (за 30 минут — 0 замеров). Это моя ошибка прошлой волны; теперь
одиночный сервер с изменившимся полем остаётся тем же сервером, с тем же отпечатком.

Ожидания этой проверки:
1. Отпечатки до установки, после неё и после двух нажатий «Обновить» **совпадают**: «пропало 0,
   появилось 0» — и у одиночных, и у «близнецов».
2. История отпечатков **перестаёт расти** на ~21 запись за каждое скачивание.
3. За 30 минут после обновлений **замеры скорости запасных идут** (больше нуля).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, `reboot`, сон машины —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh` — кроме `sudo systemctl start xgw` в разделе «Если что-то пошло не так».
  Ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`, `apt`;
  команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`. `sudo xgw pool …` (кроме
  `sudo xgw pool` без аргументов в шаге 1.3), `sudo xgw pin`, `sudo xgw unpin`, `sudo xgw probe`
  — **никогда**.
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`). Загрузок из терминала нет.
  Сайты источников, YouTube, сайты проверки IP, страны и скорости — **не открывать**.
- В панели нажимать **только** то, что написано в шагах: вкладку «Подписки» и кнопку «Обновить»
  (два раза: шаги 3.2 и 3.3). **Не нажимать**: кнопку питания, «Замерить скорость», «Проверить
  запасные», «Опросить источники», «Выбрать» и «Автовыбор» (у любых серверов), «Весь дом через
  бесплатные», «Выключить», «Включить наблюдение», переключатели Tailscale, «Ядра», «Проверить
  сеть», строки устройств, «Добавить», «Убрать».
- Править `/etc/xgw`, `/opt/xgw`, `/var/lib/xgw`, `/run/xgw`, `/etc/systemd`, код XGW. Печатать
  `config.toml`, `panel.json`, рабочие конфиги Xray и sing-box, файлы кэша подписок
  (`/var/lib/xgw/cache`), `inventory.json`, `fingerprints.json`, базу
  `/var/lib/xgw/state.db`, полный вывод `sudo xgw pool` и `sudo xgw traffic`, вывод
  `nft list ruleset`. Коммитить что-либо, кроме файла отчёта (§6). Снимки экрана в git не
  добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, токен из ссылки
  панели, MAC, имена пользователей (→ `<user>`), внешние IP, адреса и домены подписок, IP,
  домены и ссылки серверов VPN, строки журнала. Можно: коды стран, теги вида `proxy-nl-8763`,
  вердикты, числа байт и секунд, строки помощника, надписи панели без имён, счётчики, статусы,
  времена.

## 1. Подготовка

Шаг 1.0. Предусловие — прошлая проверка закончена:

```bash
cd ~/zcod/xgw && git fetch -q && git log origin/freepool --format=%s | grep -ci 'близнецы в подписке'; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3; cd ~
```

Ожидается: `1` или больше (отчёт прошлой проверки); «0 timers listed».

Если не так: первая строка `0` — **стоп**, сообщить заказчику.

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю исправление: в прошлый раз шлюз каждый час считал два десятка запасных серверов
подписки новыми и не успевал замерить их скорость. Режим бесплатных серверов не трогаю, дом всё
время идёт через подписку. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Два раза кнопка «Обновить» в панели (с перерывом в 5 минут): подписка скачается заново —
интернет при этом не пропадает.
(3) 30 минут наблюдения: я ничего не меняю, только читаю журнал.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — пропустить §3. Против 3 — пропустить шаг 4.1. **Запиши,
на что согласился заказчик.**

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-a6c" && chmod 700 "$HOME/xgw-a6c" && cd "$HOME/xgw-a6c" && cat > b6check.py <<'EOF'
"""XGW 0.2.0: «близнецы» в подписке, время обновления подписки, xgw probe — помощник проверки.
Читает состояние XGW (/run/xgw), список серверов и историю отпечатков (/var/lib/xgw — из них
только отпечатки, это хеши), кэш подписок (/var/lib/xgw/cache — разбирает кодом XGW и печатает
только имена полей, числа и хеши значений: ни адресов, ни ключей, ни самих значений) и журнал со
стандартного ввода. Ничего не меняет. Время — секунды с 1970 (date +%s). Режимы: units, state,
sub, fphist, fpsnap ИМЯ, fpdiff ИМЯ ИМЯ, invwait С [ПРЕДЕЛ], varsnap ИМЯ, vardiff НОВЫЙ
ПРЕЖНИЙ [ЕЩЁ РАНЬШЕ…], log."""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("B6CHECK_LIB", "/opt/xgw/lib")
SCAN = re.compile(r"скан (\S+): ([A-Z_]+), (\d+) байт за ([\d.]+) с")
SPEED = re.compile(r"замер скорости (\S+): .*?, (\d+) байт за ([\d.]+) с")
REFRESH = re.compile(r"обновление подписки: опрос (\d+) с, сборка (\d+) с, применение (\d+) с")


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


def arg(index, default):
    try:
        return float(sys.argv[index])
    except (IndexError, ValueError):
        return default


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:12]


def status_of(paths):
    loaded = read_json(paths.status_file)
    return loaded if isinstance(loaded, dict) else {}


def inventory(paths):
    data = read_json(paths.var / "inventory.json")
    data = data if isinstance(data, dict) else {}
    servers = data.get("servers") if isinstance(data.get("servers"), list) else []
    found = sorted({str(item.get("fingerprint")) for item in servers
                    if isinstance(item, dict) and item.get("fingerprint")})
    saved = data.get("saved")
    return found, saved if isinstance(saved, (int, float)) else None


def history(paths):
    data = read_json(paths.var / "fingerprints.json")
    known = data.get("known") if isinstance(data, dict) else None
    return known if isinstance(known, dict) else {}


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
elif mode == "fphist":
    _cfg, paths = xgw()
    known = history(paths)
    rows = [entry for entries in known.values() if isinstance(entries, dict)
            for entry in entries.values()]
    print(f"история отпечатков: базовых {len(known)}, вариантов {len(rows)}")
elif mode == "fpsnap":
    _cfg, paths = xgw()
    name = sys.argv[2] if len(sys.argv) > 2 else "now"
    found, saved = inventory(paths)
    Path(f"fp-{name}.txt").write_text("".join(f"{item}\n" for item in found), encoding="utf-8")
    age = f"{time.time() - saved:.0f} с назад" if saved is not None else "—"
    print(f"отпечатков в списке серверов: {len(found)}; список сохранён шлюзом {age}; снимок: "
          f"fp-{name}.txt")
elif mode == "fpdiff":
    _cfg, paths = xgw()
    names = sys.argv[2:4]
    if len(names) < 2:
        print("нужны два имени снимков")
        sys.exit(0)
    sets = []
    for name in names:
        try:
            sets.append(set(Path(f"fp-{name}.txt").read_text(encoding="utf-8").split()))
        except OSError:
            print(f"снимка fp-{name}.txt нет")
            sys.exit(0)
    old, new = sets
    bases = set(history(paths))
    print(f"отпечатков было {len(old)}, стало {len(new)}: пропало {len(old - new)}, появилось "
          f"{len(new - old)}")
    print(f"  с общим отпечатком (одиночные): пропало {len((old - new) & bases)}, появилось "
          f"{len((new - old) & bases)}")
    print(f"  с отпечатком варианта («близнецы»): пропало {len((old - new) - bases)}, появилось "
          f"{len((new - old) - bases)}")
elif mode == "invwait":
    _cfg, paths = xgw()
    since, limit = arg(2, time.time()), arg(3, 300)
    print(f"жду обновления списка серверов (до {limit:.0f} с)…", flush=True)
    start = time.time()
    while True:
        _found, saved = inventory(paths)
        if saved is not None and saved >= since:
            print(f"список серверов обновлён: +{saved - since:.0f} с от метки")
            break
        if time.time() - start > limit:
            print(f"за {limit:.0f} с список серверов не обновлялся")
            break
        time.sleep(3)
elif mode == "varsnap":
    _cfg, paths = xgw()
    from xgw.model import raw_to_node, variant_key
    from xgw.parsers.common import ParseError, parse_body

    name = sys.argv[2] if len(sys.argv) > 2 else "now"
    nodes, bodies = [], 0
    for body in sorted(paths.cache_dir.glob("*.body")):
        try:
            raws, _meta, _warnings = parse_body(body.read_bytes(), "sub")
        except (OSError, ParseError) as exc:
            print(f"кэш подписки не разобран: {type(exc).__name__}")
            continue
        bodies += 1
        nodes += [raw_to_node(raw, "sub") for raw in raws]
    groups: dict[str, list] = {}
    for node in nodes:
        groups.setdefault(node.fingerprint, []).append(node)
    snap = {}
    for base, group in groups.items():
        keys = [json.loads(variant_key(node)) for node in group]
        if len({json.dumps(key, sort_keys=True) for key in keys}) < 2:
            continue
        stream = (group[0].outbound or {}).get("streamSettings") or {}
        kind = (f"{group[0].protocol}/{stream.get('network') or '—'}/"
                f"{stream.get('security') or '—'}")
        fields = sorted({field for key in keys for field in key})
        snap[base] = {"kind": kind, "n": len(group), "fields": {
            field: sorted({digest(key.get(field)) for key in keys}) for field in fields}}
    Path(f"var-{name}.json").write_text(json.dumps(snap, sort_keys=True), encoding="utf-8")
    print(f"кэшей подписок: {bodies}; записей серверов: {len(nodes)}, общих отпечатков: "
          f"{len(groups)}; групп «близнецов»: {len(snap)}; снимок: var-{name}.json")
    ranked = sorted(snap.values(), key=lambda item: -item["n"])
    for index, item in enumerate(ranked[:5], 1):
        print(f"  группа {index} ({item['kind']}): записей {item['n']}; поля и число разных "
              "значений: " + ", ".join(f"{field} {len(values)}"
                                       for field, values in item["fields"].items()))
elif mode == "vardiff":
    names = sys.argv[2:]
    if len(names) < 2:
        print("нужны снимки: новый и прежний")
        sys.exit(0)
    snaps = []
    for name in names:
        loaded = read_json(Path(f"var-{name}.json"))
        if not isinstance(loaded, dict):
            print(f"снимка var-{name}.json нет")
            sys.exit(0)
        snaps.append(loaded)
    new, last, older = snaps[0], snaps[1], snaps[1:]
    ranked = sorted(new.items(), key=lambda pair: -pair[1]["n"])
    for index, (base, item) in enumerate(ranked[:5], 1):
        before = last.get(base)
        if not isinstance(before, dict):
            print(f"группа {index} ({item['kind']}): в прежнем снимке её не было")
            continue
        parts = []
        for field, values in item["fields"].items():
            seen_last = set((before.get("fields") or {}).get(field) or [])
            seen_any = set()
            for snap in older:
                seen_any |= set(((snap.get(base) or {}).get("fields") or {}).get(field) or [])
            fresh = [value for value in values if value not in seen_last]
            again = [value for value in fresh if value in seen_any]
            parts.append(f"{field}: новых {len(fresh)} из {len(values)}"
                         + (f" (встречались раньше {len(again)})" if again else ""))
        print(f"группа {index} ({item['kind']}): записей было {before.get('n')}, стало "
              f"{item['n']}; " + "; ".join(parts))
    print(f"групп «близнецов» было {len(last)}, стало {len(new)}; исчезло "
          f"{len([base for base in last if base not in new])}")
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    scans = [match for match in (SCAN.search(line) for line in lines) if match]
    counts: dict[str, int] = {}
    for match in scans:
        counts[match.group(2)] = counts.get(match.group(2), 0) + 1
    print(f"строк журнала: {len(lines)}")
    print(f"сканов: {len(scans)}" + (": " + ", ".join(
        f"{verdict} {count}" for verdict, count in sorted(counts.items())) if counts else "")
        + f"; сканов запасных: {sum(1 for match in scans if match.group(1).startswith('spare-'))}")
    speeds = [match for match in (SPEED.search(line) for line in lines) if match]
    spare = [match for match in speeds if match.group(1).startswith("spare-")]
    print(f"замеров скорости: {len(speeds)} ({sum(int(m.group(2)) for m in speeds) / 1e6:.0f} МБ),"
          f" из них запасных: {len(spare)} ({sum(int(m.group(2)) for m in spare) / 1e6:.0f} МБ),"
          f" разных серверов: {len({m.group(1) for m in speeds})}; не удались: "
          f"{sum(1 for line in lines if 'замер скорости' in line and 'не удался' in line)}")
    for match in [match for match in (REFRESH.search(line) for line in lines) if match][-5:]:
        print(f"обновление подписки: опрос {match.group(1)} с, сборка {match.group(2)} с, "
              f"применение {match.group(3)} с")
    slow = [line for line in lines if "шаг watchdog занял" in line]
    longest = max(slow, key=lambda line: int(
        (re.search(r"занял (\d+) с", line) or [0, "0"])[1]), default="")
    found = re.search(r"занял (\d+) с[^(]*(\(.*\))?", longest)
    print(f"долгих шагов демона: {len(slow)}" + (
        f"; самый долгий: {found.group(1)} с {found.group(2) or ''}" if found else ""))
    for label, word in (("откат на last-good", "last-good"), ("Traceback", "Traceback")):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | state | sub | fphist | fpsnap ИМЯ | fpdiff ИМЯ ИМЯ | invwait С [ПРЕДЕЛ] "
          "| varsnap ИМЯ | vardiff НОВЫЙ ПРЕЖНИЙ… | log")
EOF
python3 -c "import hashlib;d=open('b6check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `dbf0341d6cd2d678` (как в прошлой проверке).

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки:

```bash
cd "$HOME/xgw-a6c" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units state sub fphist; do sudo python3 -I b6check.py $m; done | tee -a before.txt; sudo python3 -I b6check.py fpsnap before | tee -a before.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4; первая строка
`xgw pool` — «Бесплатный пул: выключен; …» (или «… наблюдение …») — **записать**; четыре службы
`active`; `sub` — **записать**; `fphist` — «история отпечатков: базовых N, вариантов M» —
**записать оба числа**; `fpsnap` — записать число.

Если не так: режим пула `on` — **стоп**, сообщить заказчику.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'del seen\[other\]' src/xgw/model.py && echo "правка в коде: есть"; cd "$HOME/xgw-a6c"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-a6c/install-time.txt" && date +%s > "$HOME/xgw-a6c/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-a6c/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-a6c/install.txt"; cd "$HOME/xgw-a6c"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. После установки (до 6 минут):

```bash
cd "$HOME/xgw-a6c" && sudo python3 -I b6check.py invwait "$(cat t-install.txt)" 300 | tee after-install.txt; sleep 40; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Ожидает окна' | tee -a after-install.txt; for m in units state sub fphist; do sudo python3 -I b6check.py $m; done | tee -a after-install.txt; sudo python3 -I b6check.py fpsnap install | tee -a after-install.txt; sudo python3 -I b6check.py fpdiff before install | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I b6check.py log | tee log-install.txt
```

Ожидается:
- `invwait` — «список серверов обновлён: +N с от метки»;
- `HEALTHY`, перехват включён; четыре службы `active`; `sub` — как в шаге 1.3;
- `fphist` — «базовых N, вариантов M» — **записать**; M — **не больше**, чем в шаге 1.3, плюс 3
  (в прошлый раз было +21 за каждое скачивание);
- `fpdiff` — **«отпечатков было N, стало N: пропало 0, появилось 0»** и обе строки ниже — 0/0
  (главная проверка: обновление не сменило отпечатки);
- журнал: строка «обновление подписки: опрос … с, сборка … с, применение … с» — **записать**;
  «долгих шагов демона» — записать; «Traceback: 0», «откат на last-good: 0».

Если не так: `invwait` — «за 300 с … не обновлялся» — подожди 3 минуты и повтори всё после
`sleep 40`, запиши. Не `HEALTHY` — подожди 2 минуты, повтори
`sudo python3 -I b6check.py state`; снова нет — запиши и продолжай. `fpdiff` — «пропало» или
«появилось» больше 0 — **записать все три строки**; если больше 3 — **дефект «отпечатки
по-прежнему меняются»**. M выросло больше чем на 3 — **дефект «история растёт»**: записать оба
числа.

## 3. Два обновления подписки (если заказчик согласился на пункт 2)

Шаг 3.1. Панель. Ссылка входа (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком (окно не меньше 1280×800),
подожди 5 секунд, нажми вкладку **«Подписки»** (если она уже открыта — не нажимай), подожди 3
секунды, снимок; **J2**.

**J2 — кнопка «Обновить»:**
`(() => { const b = document.getElementById("refresh"); return [b.textContent.trim(), b.hidden, b.disabled, b.offsetParent !== null].join(" | "); })()`

Ожидается: J2 — `Обновить | false | false | true`. На снимке — записать, есть ли надпись
«Замер скорости N из M» (и какие N и M).

Если не так: J2 — `… | true | …` — подожди 30 секунд, обнови страницу (F5) и повтори J2; снова
не так — §3 пропустить, записать.

Шаг 3.2. Первое обновление.
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-a6c" && date +%s > t-r1.txt && echo "метка записана: $(date '+%T')"
```

2. Нажми **«Обновить»**. Снимок.
3. **Сразу** выполни (до 6 минут):

```bash
cd "$HOME/xgw-a6c" && sudo python3 -I b6check.py invwait "$(cat t-r1.txt)" 300 | tee r1.txt; sleep 40; for m in state sub fphist; do sudo python3 -I b6check.py $m; done | tee -a r1.txt; sudo python3 -I b6check.py fpsnap r1 | tee -a r1.txt; sudo python3 -I b6check.py fpdiff install r1 | tee -a r1.txt
```

Ожидается: «список серверов обновлён: +N с от метки»; `HEALTHY`; `sub` — как в шаге 1.3;
`fphist` — вариантов столько же, сколько в шаге 2.3 (или на 1–3 больше) — **записать**;
`fpdiff` — «пропало 0, появилось 0» во всех трёх строках.

Если не так: «за 300 с … не обновлялся» — записать, снимок панели; §3 дальше не выполнять.
`fpdiff` — больше 3 — **дефект «отпечатки по-прежнему меняются»**: записать три строки.

Шаг 3.3. Через 5 минут — второе обновление.
1. Подожди 5 минут: `sleep 300` (или `sleep 110` три раза). Затем **метка**:

```bash
cd "$HOME/xgw-a6c" && date +%s > t-r2.txt && echo "метка записана: $(date '+%T')"
```

2. Нажми **«Обновить»** ещё раз. Снимок; записать, есть ли «Замер скорости N из M».
3. **Сразу** выполни:

```bash
cd "$HOME/xgw-a6c" && sudo python3 -I b6check.py invwait "$(cat t-r2.txt)" 300 | tee r2.txt; sleep 40; for m in state sub fphist; do sudo python3 -I b6check.py $m; done | tee -a r2.txt; sudo python3 -I b6check.py fpsnap r2 | tee -a r2.txt; sudo python3 -I b6check.py fpdiff r1 r2 | tee -a r2.txt; sudo python3 -I b6check.py fpdiff before r2 | tee -a r2.txt
```

Ожидается: как в шаге 3.2; `fpdiff before r2` — «пропало 0, появилось 0» (или единицы, если
подписка и правда сменила серверы — записать).

## 4. Наблюдение: замеры запасных (если заказчик согласился на пункт 3)

Шаг 4.1. 30 минут после второго обновления:

```bash
sleep 1800; cd "$HOME/xgw-a6c" && sudo journalctl -u xgw --since "@$(cat t-r1.txt 2>/dev/null || cat t-install.txt)" --no-pager | sudo python3 -I b6check.py log | tee log-watch.txt; sudo python3 -I b6check.py fphist | tee -a log-watch.txt; sudo xgw status 2>&1 | grep -E 'Трафик проверок' | head -2 | tee -a log-watch.txt
```

(Если терминал обрывает длинные команды — `sleep 110` 17 раз, затем команда без `sleep`.)

Ожидается (записать **целиком**): «сканов: N…; сканов запасных: M» — M заметно меньше, чем 34 в
прошлый раз (сканы «новых» запасных больше не нужны); **«замеров скорости: K (X МБ), из них
запасных: L (Y МБ), разных серверов: S»** — L **больше 0**; строки «обновление подписки: опрос …
с, сборка … с, применение … с»; «долгих шагов демона»; «Traceback: 0»; `fphist` — вариантов
столько же, сколько в шаге 3.3; строка «Трафик проверок».

Если не так: «из них запасных: 0» — **не по ожиданию**: обнови страницу панели (F5), снимок —
есть ли «Замер скорости N из M» и какие N и M; записать.

## 5. Итог

Шаг 5.1. Секреты и итог:

```bash
cd "$HOME/xgw-a6c" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt; date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units state sub; do sudo python3 -I b6check.py $m; done | tee -a final.txt
```

Ожидается: `0`; `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4, строки «Ожидает
окна перезапуска» нет; четыре службы `active`; режим пула и «выбран вручную» — как в шаге 1.3.

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- Пропал интернет или доступ, или заказчик не отвечает **2 минуты** — **сразу**: если
  `systemctl is-active xgw` — не `active`, то `sudo systemctl start xgw`; подожди 30 секунд.
  Записать время и строки `sudo python3 -I b6check.py state` и `sudo xgw status 2>&1 | head -5`
  (без имён). Дальше — §5 и отчёт.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.
- Браузер не открывает панель или кнопки не нажимаются — снимок, сообщить заказчику и попросить
  нажать то же самое вручную; в отчёте пометить «нажато заказчиком».

## 6. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit6c-<ДАТА>.md` в клоне (`<ДАТА>` — дата начала
проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, отпечатки одиночных серверов» и `git push` в
`freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и подписок,
адресов, доменов, токена и строк журнала. Шаблон (заполни каждую ячейку; пропущенное — «не
выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — отпечатки одиночных серверов с меняющимся полем, замеры запасных

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
b6check.py: <сумма>. Режим пула до проверки: <…>. Ядра: Xray <…>, sing-box <…>. Исполнитель:
<модель>; нажатия и снимки — управляемым браузером <да/частично>.

## Итог
| Отпечатки: до → установка → r1 → r2 (пропало/появилось) | История: вариантов по шагам | Замеры за 30 мин (всего / запасных, МБ) | Сканы запасных за 30 мин | Обновление подписки: опрос / сборка / применение (с) |
|---|---|---|---|---|
| <0/0 → 0/0 → 0/0> | <260 → 261 → 261 → 261> | <15 / 12, 110 МБ> | <10> | <65 / 20 / 8> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.0 предусловие | … | … |
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 панель | … | … |
| 3.2 обновление 1 | … | … |
| 3.3 обновление 2 | … | … |
| 4.1 наблюдение 30 мин | … | … |
| 5 итог | … | … |

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-a6c/…); результат J2; что видно на снимках
  словами, в том числе «Замер скорости N из M»; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
