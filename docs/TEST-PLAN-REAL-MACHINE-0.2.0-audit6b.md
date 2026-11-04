# Проверка XGW 0.2.0: «близнецы» в подписке, время обновления подписки, `xgw probe`

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть:
- **терминал** в сеансе заказчика (`sudo` — от его имени);
- **управляемый браузер**: ты сам открываешь адреса, нажимаешь кнопки, делаешь **снимок
  экрана** и смотришь на него, выполняешь JavaScript в консоли страницы.

Одна сессия, около полутора часов (из них около 40 минут — ожидание). Режим бесплатных серверов
в этой проверке **не трогается** — дом всё время идёт через подписку.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. После **каждого нажатия** в браузере сделай снимок экрана, посмотри на него и сверь с
   «Ожидается» (тексты — дословно). Где дана проверка JavaScript (J2) — выполни её в консоли
   страницы панели и сверь результат: она точнее снимка.
4. Выводы команд сохраняются в файлы `$HOME/xgw-a6b/…`. Время шага — по выводу `date` в
   команде, не по памяти.
5. **Метка времени — до нажатия.** Где в шаге есть команда «Метка», выполни её **перед**
   нажатием в браузере, а команду проверки — **после**.
6. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
7. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
8. Экземпляр этого ТЗ держи в `$HOME/xgw-a6b/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2.
9. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `b6check.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
10. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши
    дословно строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
    «Наблюдения», со словом «предположение».

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.31 и sing-box
1.14.4, принятые шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 281) и зачем проверка

1. **«Близнецы» в подписке.** В прошлой проверке после каждого скачивания подписки у 21 сервера
   менялись отпечатки. По числам это одна точка входа подписки с ~23 записями, которые
   отличаются путём, Host, SNI, ключом REALITY или режимом, — и у 21 из них эти поля меняются при
   каждом скачивании. Для шлюза это каждый раз ~20 «новых» запасных: сканы, замеры скорости и
   потеря их истории. Эта проверка выясняет, **какое именно поле** меняется (новые значения или
   повторы из небольшого набора) и **сколько трафика** это стоит. Помощник разбирает кэш подписки
   кодом XGW и печатает только имена полей, числа и хеши значений — ни адресов, ни ключей, ни
   самих значений.
2. **Время обновления подписки.** Шаг демона с обновлением подписки длится 80–110 с. Теперь в
   журнале строка «обновление подписки: опрос N с, сборка M с, применение K с».
3. **`xgw probe` с неверным тегом.** В прошлой проверке `xgw probe нет` проверил все серверы
   подряд. Теперь неизвестное слово — «узла нет в рабочем конфиге», код 2, без проб.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, `reboot`, сон машины —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh` — кроме `sudo systemctl start xgw` в разделе «Если что-то пошло не так».
  Ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`, `apt`;
  команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`. `sudo xgw pool …` (кроме
  `sudo xgw pool` без аргументов в шаге 1.3), `sudo xgw pin`, `sudo xgw unpin` — **никогда**.
  `sudo xgw probe` — только в шаге 3.1 и только со словом из команды шага.
- В управляемом браузере — только панель (`http://127.0.0.1:8781/…`). Загрузок из терминала нет.
  Сайты источников, YouTube, сайты проверки IP, страны и скорости — **не открывать**.
- В панели нажимать **только** то, что написано в шагах: вкладку «Подписки» и кнопку «Обновить»
  (два раза: шаги 4.2 и 4.3). **Не нажимать**: кнопку питания, «Замерить скорость», «Проверить
  запасные», «Опросить источники», «Выбрать» и «Автовыбор» (у любых серверов), «Весь дом через
  бесплатные», «Выключить», «Включить наблюдение», переключатели Tailscale, «Ядра», «Проверить
  сеть», строки устройств, «Добавить», «Убрать».
- Править `/etc/xgw`, `/opt/xgw`, `/var/lib/xgw`, `/run/xgw`, `/etc/systemd`, код XGW. Печатать
  `config.toml`, `panel.json`, рабочие конфиги Xray и sing-box, файлы кэша подписок
  (`/var/lib/xgw/cache`), `inventory.json`, `fingerprints.json`, базу
  `/var/lib/xgw/state.db`, полный вывод `sudo xgw pool` и `sudo xgw traffic`, вывод
  `nft list ruleset`. Коммитить что-либо, кроме файла отчёта (§7). Снимки экрана в git не
  добавлять.
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, токен из ссылки
  панели, MAC, имена пользователей (→ `<user>`), внешние IP, адреса и домены подписок, IP,
  домены и ссылки серверов VPN, строки журнала. Можно: коды стран, теги вида `proxy-nl-8763`,
  вердикты, числа байт и секунд, строки помощника (имена полей вида `wsSettings.path`, числа),
  надписи панели без имён, счётчики, статусы, времена.

## 1. Подготовка

Шаг 1.0. Предусловие — прошлая проверка закончена:

```bash
cd ~/zcod/xgw && git fetch -q && git log origin/freepool --format=%s | grep -ci 'волна 1 кросс-аудита'; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3; cd ~
```

Ожидается: `2` или больше (коммит кода и отчёт прошлой проверки); «0 timers listed».

Если не так: первая строка `0` или `1` — **стоп**, сообщить заказчику.

Шаг 1.1. **Спроси заказчика** (дословно):

«Продолжаю проверку по внешнему аудиту: в вашей подписке есть сервер с двумя десятками записей,
которые меняются при каждом скачивании, — шлюз каждый раз считает их новыми серверами и тратит на
них проверки. Я выясню, что именно в них меняется и сколько трафика это стоит. Режим бесплатных
серверов не трогаю, дом всё время идёт через подписку. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Два раза кнопка «Обновить» в панели (с перерывом в 5 минут): подписка скачается заново,
шлюз пересоберёт список серверов — интернет при этом не пропадает.
(3) 30 минут наблюдения: я ничего не меняю, только читаю журнал.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — пропустить §4. Против 3 — пропустить шаг 5.1. **Запиши,
на что согласился заказчик.**

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-a6b" && chmod 700 "$HOME/xgw-a6b" && cd "$HOME/xgw-a6b" && cat > b6check.py <<'EOF'
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

Ожидается: одна строка — сумма `dbf0341d6cd2d678`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки и снимок «близнецов» по кэшу прежнего кода:

```bash
cd "$HOME/xgw-a6b" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units state sub fphist; do sudo python3 -I b6check.py $m; done | tee -a before.txt; sudo python3 -I b6check.py fpsnap before | tee -a before.txt; sudo python3 -I b6check.py varsnap before | tee -a before.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4; первая строка
`xgw pool` — «Бесплатный пул: выключен; …» (или «… наблюдение …») — **записать**; четыре службы
`active`; `sub` — **записать**; `fphist` — «история отпечатков: базовых N, вариантов M» —
записать; `fpsnap` — записать число; `varsnap` — «кэшей подписок: K; записей серверов: …; групп
«близнецов»: G» и строки «группа 1 (протокол/транспорт/защита): записей N; поля и число разных
значений: …» — **записать все строки целиком** (это главные данные).

Если не так: режим пула `on` — **стоп**, сообщить заказчику. «групп «близнецов»: 0» — записать
(не стоп).

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'info.tag.split("-", 1)\[-1\]' src/xgw/cli.py && grep -q 'обновление подписки: опрос' src/xgw/daemon.py && echo "правка в коде: есть"; cd "$HOME/xgw-a6b"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-a6b/install-time.txt" && date +%s > "$HOME/xgw-a6b/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-a6b/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-a6b/install.txt"; cd "$HOME/xgw-a6b"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. После установки (до 5 минут):

```bash
cd "$HOME/xgw-a6b" && sudo python3 -I b6check.py invwait "$(cat t-install.txt)" 300 | tee after-install.txt; sleep 20; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Ожидает окна' | tee -a after-install.txt; for m in units state sub fphist; do sudo python3 -I b6check.py $m; done | tee -a after-install.txt; sudo python3 -I b6check.py fpsnap install | tee -a after-install.txt; sudo python3 -I b6check.py fpdiff before install | tee -a after-install.txt; sudo python3 -I b6check.py varsnap install | tee -a after-install.txt; sudo python3 -I b6check.py vardiff install before | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I b6check.py log | tee log-install.txt
```

Ожидается:
- `invwait` — «список серверов обновлён: +N с от метки»;
- `HEALTHY`, перехват включён; четыре службы `active`; `sub` — как в шаге 1.3;
- `fpdiff` — три строки; **главное — «с общим отпечатком (одиночные): пропало 0, появилось
  0»**; строку про «близнецов» — записать;
- `varsnap` и `vardiff` — **записать все строки целиком** (`vardiff`: у каждой группы — какие
  поля получили новые значения: «wsSettings.path: новых 21 из 23» и т. п.);
- журнал: строка «обновление подписки: опрос N с, сборка M с, применение K с» — **записать**;
  «долгих шагов демона» — записать; «Traceback: 0», «откат на last-good: 0».

Если не так: `invwait` — «за 300 с … не обновлялся» — подожди 3 минуты и повтори всё после
`sleep 20`, запиши. Не `HEALTHY` — подожди 2 минуты, повтори
`sudo python3 -I b6check.py state`; снова нет — запиши и продолжай. «одиночные: пропало» или
«появилось» больше 0 — **не по ожиданию**: записать строку (одиночный сервер мог и правда уйти из
подписки). Нет строки «обновление подписки: опрос…» — **дефект «нет строки времени
обновления»**.

## 3. `xgw probe` с неверным тегом

Шаг 3.1. Проверка без проб:

```bash
cd "$HOME/xgw-a6b" && sudo xgw probe нет > probe.txt 2>&1; echo "код $?" | tee -a probe.txt; cat probe.txt
```

Ожидается: строка «… узла нет нет в рабочем конфиге (см. xgw servers)» и «код 2»; строк с
вердиктами (`OK`, `SLOW`, …) **нет**.

Если не так: строки с вердиктами есть — **дефект «xgw probe с неверным тегом проверяет
серверы»**: записать число строк и код.

## 4. Два обновления подписки (если заказчик согласился на пункт 2)

Шаг 4.1. Панель. Ссылка входа (в ней токен — **никуда не записывать**):

```bash
sudo xgw panel 2>&1 | head -1
```

**Действие:** в управляемом браузере открой эту ссылку целиком (окно не меньше 1280×800),
подожди 5 секунд, нажми вкладку **«Подписки»** (если она уже открыта — не нажимай), подожди 3
секунды, снимок; **J2**.

**J2 — кнопка «Обновить»:**
`(() => { const b = document.getElementById("refresh"); return [b.textContent.trim(), b.hidden, b.disabled, b.offsetParent !== null].join(" | "); })()`

Ожидается: J2 — `Обновить | false | false | true`.

Если не так: J2 — `… | true | …` — подожди 30 секунд, обнови страницу (F5) и повтори J2; снова
не так — §4 пропустить, записать.

Шаг 4.2. Первое обновление.
1. **Метка** (до нажатия):

```bash
cd "$HOME/xgw-a6b" && date +%s > t-r1.txt && echo "метка записана: $(date '+%T')"
```

2. Нажми **«Обновить»**. Снимок.
3. **Сразу** выполни (до 6 минут):

```bash
cd "$HOME/xgw-a6b" && sudo python3 -I b6check.py invwait "$(cat t-r1.txt)" 300 | tee r1.txt; sleep 20; for m in state sub fphist; do sudo python3 -I b6check.py $m; done | tee -a r1.txt; sudo python3 -I b6check.py fpsnap r1 | tee -a r1.txt; sudo python3 -I b6check.py fpdiff install r1 | tee -a r1.txt; sudo python3 -I b6check.py varsnap r1 | tee -a r1.txt; sudo python3 -I b6check.py vardiff r1 install before | tee -a r1.txt
```

Ожидается: «список серверов обновлён: +N с от метки»; `HEALTHY`; `sub` — как в шаге 1.3;
`fpdiff` — «одиночные: пропало 0, появилось 0»; `varsnap`, `vardiff` — **записать все строки
целиком** (в `vardiff` видно, новые ли это значения или повторы: «(встречались раньше N)»).

Если не так: «за 300 с … не обновлялся» — записать, снимок панели; §4 дальше не выполнять.

Шаг 4.3. Через 5 минут — второе обновление.
1. Подожди 5 минут: `sleep 300` (или `sleep 110` три раза). Затем **метка**:

```bash
cd "$HOME/xgw-a6b" && date +%s > t-r2.txt && echo "метка записана: $(date '+%T')"
```

2. Нажми **«Обновить»** ещё раз. Снимок.
3. **Сразу** выполни:

```bash
cd "$HOME/xgw-a6b" && sudo python3 -I b6check.py invwait "$(cat t-r2.txt)" 300 | tee r2.txt; sleep 20; for m in state sub fphist; do sudo python3 -I b6check.py $m; done | tee -a r2.txt; sudo python3 -I b6check.py fpsnap r2 | tee -a r2.txt; sudo python3 -I b6check.py fpdiff r1 r2 | tee -a r2.txt; sudo python3 -I b6check.py varsnap r2 | tee -a r2.txt; sudo python3 -I b6check.py vardiff r2 r1 install before | tee -a r2.txt
```

Ожидается: как в шаге 4.2 — **записать все строки целиком**.

## 5. Наблюдение: сколько стоят «новые» запасные (если заказчик согласился на пункт 3)

Шаг 5.1. 30 минут после второго обновления:

```bash
sleep 1800; cd "$HOME/xgw-a6b" && sudo journalctl -u xgw --since "@$(cat t-r1.txt 2>/dev/null || cat t-install.txt)" --no-pager | sudo python3 -I b6check.py log | tee log-watch.txt; sudo xgw status 2>&1 | grep -E 'Трафик проверок|трафик проверок|проверок' | head -3 | tee -a log-watch.txt
```

(Если терминал обрывает длинные команды — `sleep 110` 17 раз, затем команда без `sleep`.)

Ожидается (записать **целиком**): «сканов: N…; сканов запасных: M»; «замеров скорости: K (X МБ),
из них запасных: L (Y МБ), разных серверов: S; не удались: F»; строки «обновление подписки:
опрос … с, сборка … с, применение … с» (по каждому обновлению); «долгих шагов демона»;
«Traceback: 0»; строки `xgw status` про трафик проверок (если есть).

## 6. Итог

Шаг 6.1. Секреты и итог:

```bash
cd "$HOME/xgw-a6b" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt; date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units state sub; do sudo python3 -I b6check.py $m; done | tee -a final.txt
```

Ожидается: `0`; `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4, строки «Ожидает
окна перезапуска» нет; четыре службы `active`; режим пула и «выбран вручную» — как в шаге 1.3.

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- Пропал интернет или доступ, или заказчик не отвечает **2 минуты** — **сразу**: если
  `systemctl is-active xgw` — не `active`, то `sudo systemctl start xgw`; подожди 30 секунд.
  Записать время и строки `sudo python3 -I b6check.py state` и `sudo xgw status 2>&1 | head -5`
  (без имён). Дальше — §6 и отчёт.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.
- Браузер не открывает панель или кнопки не нажимаются — снимок, сообщить заказчику и попросить
  нажать то же самое вручную; в отчёте пометить «нажато заказчиком».

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit6b-<ДАТА>.md` в клоне (`<ДАТА>` — дата начала
проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, близнецы в подписке» и `git push` в
`freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и подписок,
адресов, доменов, токена и строк журнала. Шаблон (заполни каждую ячейку; пропущенное — «не
выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — «близнецы» в подписке, время обновления подписки, xgw probe

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
b6check.py: <сумма>. Режим пула до проверки: <…>. Ядра: Xray <…>, sing-box <…>. Исполнитель:
<модель>; нажатия и снимки — управляемым браузером <да/частично>.

## Итог
| Группы «близнецов» (записей; какие поля меняются) | Новые значения или повторы | Одиночные отпечатки стабильны | Замеры за 30 мин (всего / запасных, МБ) | Обновление подписки: опрос / сборка / применение (с) | `xgw probe нет` |
|---|---|---|---|---|---|
| <1 группа, 23; wsSettings.path> | <новые 21 из 23 каждый раз> | <да> | <12 / 9, 90 МБ> | <70 / 8 / 4> | <код 2, проб нет> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.0 предусловие | … | … |
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 xgw probe нет | … | … |
| 4.1 панель | … | … |
| 4.2 обновление 1 | … | … |
| 4.3 обновление 2 | … | … |
| 5.1 наблюдение 30 мин | … | … |
| 6 итог | … | … |

## Строки `varsnap` и `vardiff` (шаги 1.3, 2.3, 4.2, 4.3 — целиком)
<…>

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-a6b/…); результат J2; что видно на снимках
  словами; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
