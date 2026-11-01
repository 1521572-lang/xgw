# Проверка XGW 0.2.0: волна 2 кросс-аудита — эталон правил, наборы, ip rule, таблицы маршрутов

## Как работать с этим ТЗ (прочитай целиком до начала)

Ты — исполнитель проверки на машине заказчика. У тебя есть **терминал** в сеансе заказчика
(`sudo` — от его имени). Браузер в этой проверке не нужен: всё — командами.

Одна сессия, около 40 минут (из них около 15 минут — ожидание). Режим бесплатных серверов в этой
проверке **не трогается** — дом всё время идёт через подписку.

Правила:
1. Шаги — строго по порядку, по одному. Номер шага пиши в начале своего сообщения.
2. В каждом шаге: **Действие**, **Команда** (копируй блок целиком, ничего в нём не меняя),
   **Ожидается** и **Если не так**. Сверх написанного ничего не делай и не придумывай.
3. Выводы команд сохраняются в файлы `$HOME/xgw-w2/…`. Время шага — по выводу `date` в
   команде, не по памяти.
4. **Метка времени** пишется той же командой, что делает тестовую правку (шаги 3.2 и 3.3).
5. Долгие ожидания — командой `sleep`. Если терминал обрывает команды дольше 2 минут — разбей
   ожидание на несколько `sleep 110` подряд и продолжай с той же команды без `sleep`.
6. Не уверен, что делать, — остановись и спроси заказчика. Ответы заказчика записывай дословно
   (без имён серверов, устройств и подписок).
7. Экземпляр этого ТЗ держи в `$HOME/xgw-w2/plan.md` (не в /tmp). Файл помощника создаётся
   **только** командой шага 1.2. Это **новый** помощник (`w2check.py`).
8. Режимы помощника у разработчика на живом шлюзе не запускались (решение заказчика: проверки —
   на машине). Если режим `w2check.py` выводит `Traceback` — запиши режим и последнюю строку
   ошибки как **дефект помощника** и продолжай шаг по остальным строкам и командам `xgw`. Сам
   файл помощника не исправляй.
9. Если вывод не совпал с «Ожидается», а в «Если не так» этот случай не описан — запиши
   дословно строку помощника, отметь «не по ожиданию» и иди дальше. Догадки о причине — только в
   «Наблюдения», со словом «предположение».
10. Тестовые правки §3 — **только** командами из шагов и **только** с сетью 203.0.113.0/24 (это
    сеть для документации: ни одно устройство её не использует, интернет правки не задевают).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11). Клон — `~/zcod/xgw`.
Код — ветка `freepool`, версия 0.2.0. На машине — Xray 26.10.31 и sing-box 1.14.4, принятые
шлюзом через карточку «Ядра»: установка их не откатывает.

### Что нового (ASSUMPTIONS п. 284) и зачем проверка

Внешний аудит нашёл четыре места, где шлюз мог не заметить чужую правку сетевых правил:
1. **Эталон правил перехвата** (что должно быть в таблицах nftables) снимался с ядра сразу после
   загрузки — вместе с чужой правкой, если она успела. Теперь эталон сверяется с текстом правил и
   снимается, только если между загрузкой и чтением таблицы никто не менял.
2. **Элементы наборов** «частные сети», «мимо VPN» и «российские сети» не проверялись вовсе. Теперь
   чужой элемент — повод загрузить правила заново.
3. **Правило маршрутизации XGW** считалось на месте, даже если его сузили (например, «только для
   одного пользователя»). Теперь — только ровно такое, как ставит XGW; чужие правила с той же
   меткой XGW не трогает, а чужие правила раньше правил XGW `xgw diag` показывает предупреждением.
4. **Таблица маршрутов XGW** могла содержать лишний маршрут — помеченные пакеты к той сети
   уходили бы мимо VPN. Теперь в ней только маршруты XGW, лишний убирается.

Ожидания этой проверки:
1. После установки: «эталон правил: есть», «расхождение с текстом правил: нет», проверка правил —
   `True`; за 10 минут наблюдения правила **ни разу** не загружаются заново сами.
2. Тестовый элемент в наборе «мимо VPN» и тестовый маршрут в таблице XGW шлюз **убирает сам** —
   не дольше 60 секунд; помеченный пакет к тестовой сети снова идёт в Xray.
3. Тестовое чужое правило с той же меткой **остаётся на месте** после перезагрузки правил;
   тестовое правило раньше правил XGW видно в `xgw diag`.
4. Время проверки правил до и после установки — записать (новая проверка читает больше).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `install.sh --force`, `reboot`, сон машины —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh` — кроме `sudo systemctl start xgw` в разделе «Если что-то пошло не так».
- Ручные `nft`, `ip`, `ip netns`, `iptables`, `tc`, `sysctl -w`, `apt` — **кроме** команд шагов
  3.1–3.4 и запасных команд в их «Если не так». Команды `tailscale`, `xray`, `sing-box`,
  `sstpc`, `pppd`. `sudo xgw pool …` (кроме `sudo xgw pool` без аргументов в шаге 1.3),
  `sudo xgw pin`, `sudo xgw unpin`, `sudo xgw probe` — **никогда**.
- Браузер, панель, сайты — в этой проверке не открывать.
- Править `/etc/xgw`, `/opt/xgw`, `/var/lib/xgw`, `/run/xgw`, `/etc/systemd`, код XGW. Печатать
  `config.toml`, `panel.json`, `status.json`, `capture.json`, рабочие конфиги Xray и sing-box,
  кэш подписок, `inventory.json`, базу `state.db`, полный вывод `nft list ruleset`, `nft list
  table`, `ip rule`, `ip route`. Коммитить что-либо, кроме файла отчёта (§6).
- Писать в отчёт: **имена серверов, устройств и подписок**, адреса tailnet, MAC, имена
  пользователей (→ `<user>`), внешние IP, адреса LAN-устройств, домены и ссылки серверов VPN,
  строки журнала. Можно: коды стран, теги вида `proxy-nl-8763`, номера таблиц и приоритеты
  (pref), тестовую сеть 203.0.113.0/24, строки помощника, счётчики, статусы, времена.

## 1. Подготовка

Шаг 1.0. Предусловие — прошлая проверка закончена:

```bash
cd ~/zcod/xgw && git fetch -q && git log origin/freepool --format=%s | grep -ci 'опрос подписок в фоне'; systemctl list-timers --all --no-pager xgw-yt-guard.timer | head -3; cd ~
```

Ожидается: `1` или больше (отчёт прошлой проверки); «0 timers listed».

Если не так: первая строка `0` — **стоп**, сообщить заказчику.

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю исправления по аудиту: шлюз должен сам замечать и убирать чужие правки своих сетевых
правил. Режим бесплатных серверов не трогаю, дом всё время идёт через подписку. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся — интернет
дома пропадёт на несколько секунд. Ядра останутся.
(2) Четыре тестовые правки сетевых правил с адресами 203.0.113.0/24 — это сеть для документации,
её не использует ни одно устройство, интернет они не задевают: адрес в наборе «мимо VPN»,
маршрут «недоступно» в таблице XGW и два правила маршрутизации (одно — для несуществующего
пользователя, другое — только для пакетов из 203.0.113.0/24). Первые две шлюз должен убрать сам,
правила я убираю сам в конце.
(3) 10 минут наблюдения: я ничего не меняю, только читаю журнал.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — пропустить §3 (кроме записи). Против 3 — пропустить шаг
4.1. **Запиши, на что согласился заказчик.**

Шаг 1.2. Папка, помощник проверки и его сумма:

```bash
mkdir -p "$HOME/xgw-w2" && chmod 700 "$HOME/xgw-w2" && cd "$HOME/xgw-w2" && cat > w2check.py <<'EOF'
"""XGW 0.2.0: волна 2 кросс-аудита (эталон правил, наборы, ip rule, таблицы маршрутов) —
помощник проверки. Читает состояние XGW (/run/xgw/status.json, /var/lib/xgw/capture.json —
только наличие эталона и текст расхождения), правила `ip rule`, таблицы маршрутов XGW, набор
bypass4 (`nft list set`) и журнал со стандартного ввода (journalctl -o short-unix). Проверка
правил (check) — тем же кодом XGW, только чтение. Ничего не меняет; адресов устройств и серверов
не печатает — только числа, приоритеты, типы маршрутов и тестовую сеть 203.0.113.0/24. Время —
секунды с 1970 (date +%s). Режимы: units, state, sub, num ИМЯ, capstate, check, rules, routes,
routeget, setcheck, log [МЕТКА]."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("W2CHECK_LIB", "/opt/xgw/lib")
STAMP = re.compile(r"^(\d+(?:\.\d+)?) ")
TEST_NET = "203.0.113.0/24"
TEST_HOST = "203.0.113.5"
TEST_UIDS = "4000000000-4000000000"
RELOADED = "правила сети не были загружены — загружены заново"


def run(argv):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=30)
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


def ip_json(argv):
    code, out = run(argv)
    if code != 0:
        return None, out.strip().splitlines()[-1] if out.strip() else f"код {code}"
    try:
        loaded = json.loads(out or "[]")
    except ValueError:
        return None, "непонятный ответ"
    return [item for item in loaded if isinstance(item, dict)], ""


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
elif mode == "num":
    cfg, _paths = xgw()
    name = sys.argv[2] if len(sys.argv) > 2 else ""
    values = {"mark": hex(cfg.capture.mark_proxy), "table": cfg.capture.route_table,
              "tuntable": cfg.capture.tun_route_table}
    print(values.get(name, "?"))
elif mode == "capstate":
    _cfg, paths = xgw()
    state = read_json(paths.var / "capture.json")
    state = state if isinstance(state, dict) else {}
    mismatch = state.get("mismatch") or ""
    print(f"эталон правил: {'есть' if state.get('baseline') else 'нет'}; старый отпечаток "
          f"(tables): {'есть' if state.get('tables') else 'нет'}; расхождение с текстом правил: "
          + (mismatch if mismatch else "нет"))
elif mode == "check":
    cfg, paths = xgw()
    from xgw.net import capture as capturing
    from xgw.net import iprule

    capture = capturing.capture_for(cfg, paths)
    began = time.monotonic()
    first = capture.loaded()
    middle = time.monotonic()
    second = capture.loaded()
    end = time.monotonic()
    print(f"проверка правил: {first} за {middle - began:.2f} с; повторно: {second} за "
          f"{end - middle:.2f} с")
    early = getattr(iprule, "early", None)
    if early is None:
        print("правил раньше XGW: (в этом коде такой проверки нет)")
    else:
        tables = (cfg.capture.route_table, cfg.capture.tun_route_table)
        prefs = sorted({pref for family in (4, 6)
                        for pref in early(capture.runner, family, tables)})
        print("правил раньше XGW: " + (", ".join(f"pref {pref}" for pref in prefs) or "нет"))
elif mode == "rules":
    cfg, _paths = xgw()
    own = {str(cfg.capture.route_table), str(cfg.capture.tun_route_table)}
    for family, argv in ((4, ["ip", "-j", "rule", "show"]),
                         (6, ["ip", "-6", "-j", "rule", "show"])):
        rules, error = ip_json(argv)
        if rules is None:
            print(f"IPv{family}: правила не прочитать — {error}")
            continue
        xgw_rules = sorted(f"pref {rule.get('priority')} (таблица {rule.get('table')}"
                           + (", с другими условиями" if "uidrange" in rule else "") + ")"
                           for rule in rules if str(rule.get("table")) in own)
        early = sorted(rule.get("priority") for rule in rules
                       if isinstance(rule.get("priority"), int) and rule["priority"] < 100
                       and rule.get("table") is not None and str(rule.get("table")) not in own
                       and not (rule["priority"] == 0 and str(rule.get("table")) == "local"))
        print(f"IPv{family}: правила в таблицы XGW: " + ("; ".join(xgw_rules) or "нет")
              + "; чужие раньше XGW: " + (", ".join(f"pref {pref}" for pref in early) or "нет"))
        if family == 4:
            narrowed = any(rule.get("priority") == 101 and rule.get("uidrange") for rule in rules)
            before = any(rule.get("priority") == 50 and rule.get("src") == TEST_NET.split("/")[0]
                         for rule in rules)
            print(f"тестовое правило с uidrange (pref 101): {'на месте' if narrowed else 'нет'}; "
                  f"тестовое правило раньше XGW (pref 50): {'на месте' if before else 'нет'}")
elif mode == "routes":
    cfg, _paths = xgw()
    for table in (cfg.capture.route_table, cfg.capture.tun_route_table):
        routes, error = ip_json(["ip", "-j", "route", "show", "table", str(table)])
        if routes is None:
            print(f"таблица {table}: не прочитать — {error}")
            continue
        kinds: dict[str, int] = {}
        for route in routes:
            dst = "default" if route.get("dst") in ("default", "0.0.0.0/0") else "сеть"
            key = f"{route.get('type') or 'unicast'} {dst}"
            kinds[key] = kinds.get(key, 0) + 1
        test = any(route.get("dst") == TEST_NET for route in routes)
        print(f"таблица {table}: маршрутов {len(routes)} ("
              + (", ".join(f"{key} ×{count}" for key, count in sorted(kinds.items())) or "пусто")
              + f"); тестовый маршрут {TEST_NET}: {'есть' if test else 'нет'}")
elif mode == "routeget":
    cfg, _paths = xgw()
    from xgw.net import lan

    argv = ["ip", "-j", "route", "get", TEST_HOST]
    gateway = lan.gateway(cfg)
    lan_if = lan.lan_interface(cfg)
    if gateway is not None and lan_if:
        host = next((str(item) for item in gateway.network.hosts() if item != gateway.ip), "")
        argv += ["from", host, "iif", lan_if]
        where = "от устройства сети"
    else:
        where = "с самой машины"
    routes, error = ip_json([*argv, "mark", str(cfg.capture.mark_proxy)])
    if routes is None:
        print(f"помеченный пакет {where} к {TEST_HOST}: ошибка — {error}")
    else:
        route = routes[0] if routes else {}
        kind = route.get("type") or "unicast"
        print(f"помеченный пакет {where} к {TEST_HOST}: {kind}"
              + (" (в Xray, TPROXY)" if kind == "local" else f" через {route.get('dev') or '?'}"))
elif mode == "setcheck":
    code, out = run(["nft", "list", "set", "ip", "xgw", "bypass4"])
    if code != 0:
        print("набора bypass4 нет")
        sys.exit(0)
    found = re.search(r"elements\s*=\s*\{(.*?)\}", out, flags=re.DOTALL)
    items = [item.strip() for item in (found.group(1).split(",") if found else []) if item.strip()]
    print(f"набор bypass4: элементов {len(items)}; тестовый элемент {TEST_NET}: "
          + ("есть" if TEST_NET in items else "нет"))
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    try:
        mark = float(sys.argv[2])
    except (IndexError, ValueError):
        mark = 0.0
    reloads = [stamp for stamp in (when(line) for line in lines if RELOADED in line) if stamp]
    after = [stamp for stamp in reloads if stamp >= mark]
    print(f"строк журнала: {len(lines)}; загрузок правил заново: {len(after)}"
          + (f" (первая — через {after[0] - mark:.0f} с после метки)" if after and mark else ""))
    for label, word in (("эталон правил не снят", "эталон правил не снят"),
                        ("не сходятся с текстом правил", "не сходятся с текстом правил"),
                        ("ошибок загрузки правил", "правила перехвата не загружены"),
                        ("Traceback", "Traceback")):
        print(f"{label}: {sum(1 for line in lines if word in line)}")
else:
    print("режим: units | state | sub | num ИМЯ | capstate | check | rules | routes | routeget "
          "| setcheck | log [МЕТКА]")
EOF
python3 -c "import hashlib;d=open('w2check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"
```

Ожидается: одна строка — сумма `14af6178c1b524c8`.

Если не так: сумма другая — выполнить шаг заново, скопировав блок целиком; снова другая —
**стоп**, сообщить заказчику.

Шаг 1.3. Состояние до установки (здесь ещё прежний код):

```bash
cd "$HOME/xgw-w2" && date '+%F %T' | tee before.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units state sub capstate check rules routes routeget setcheck; do sudo python3 -I w2check.py $m; done 2>&1 | tee -a before.txt
```

Ожидается (записать **целиком** строки помощника):
- `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4; первая строка `xgw pool` —
  «Бесплатный пул: выключен; …» (или «… наблюдение …»); четыре службы `active`; `sub` —
  «выбран вручную: …» — записать;
- `capstate` — прежний код: «эталон правил: нет; старый отпечаток (tables): есть; …»;
- `check` — «проверка правил: True за X с; повторно: True за Y с» — **записать X и Y**;
  «правил раньше XGW: (в этом коде такой проверки нет)»;
- `rules` — «IPv4: правила в таблицы XGW: pref … ; чужие раньше XGW: …» и «тестовое правило …:
  нет; …: нет»;
- `routes` — «таблица N: маршрутов …; тестовый маршрут 203.0.113.0/24: нет» (по строке на
  таблицу);
- `routeget` — «помеченный пакет от устройства сети к 203.0.113.5: local (в Xray, TPROXY)»;
- `setcheck` — «набор bypass4: элементов N; тестовый элемент 203.0.113.0/24: нет».

Если не так: режим пула `on` — **стоп**, сообщить заказчику. `setcheck` — «набора bypass4 нет»
— записать; в §3 шаг 3.2 пропустить. `routeget` — не `local` — записать, продолжать.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def _baseline' src/xgw/net/capture.py && grep -q 'def early' src/xgw/net/iprule.py && echo "правка в коде: есть"; cd "$HOME/xgw-w2"
```

Ожидается: строка `<хеш> <тема коммита>` и «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. WAN и DHCP она не трогает;
интернет дома пропадёт на несколько секунд. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-w2/install-time.txt" && date +%s > "$HOME/xgw-w2/t-install.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-w2/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw|Установка не начата' "$HOME/xgw-w2/install.txt"; cd "$HOME/xgw-w2"
```

Ожидается: «код 0», «демон xgw запущен».

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через минуту — состояние, эталон и журнал после установки:

```bash
cd "$HOME/xgw-w2" && sleep 60; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Ожидает окна' | tee after-install.txt; for m in units state sub capstate check rules routes routeget setcheck; do sudo python3 -I w2check.py $m; done 2>&1 | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" -o short-unix --no-pager | sudo python3 -I w2check.py log | tee log-install.txt; sudo xgw diag 2>&1 | grep -E 'Перехват|Эталон правил|Маршрутизация' | tee -a after-install.txt
```

Ожидается (записать **целиком**):
- `HEALTHY`, перехват включён, строки «Ожидает окна перезапуска» нет; четыре службы `active`;
  `sub` — как в шаге 1.3;
- **`capstate` — «эталон правил: есть; старый отпечаток (tables): нет; расхождение с текстом
  правил: нет»** (главная проверка: загруженные таблицы сошлись с текстом правил);
- `check` — «проверка правил: True за X с; повторно: True за Y с» — **записать X и Y** (X может
  быть больше, чем в шаге 1.3, на 1–2 с: теперь читается и набор российских сетей; Y — меньше X);
  «правил раньше XGW: нет»;
- `rules`, `routes` — как в шаге 1.3; `routeget` — «… local (в Xray, TPROXY)»;
- журнал: «загрузок правил заново: 0» (или 1); «эталон правил не снят: 0»; «не сходятся с
  текстом правил: 0»; «ошибок загрузки правил: 0»; «Traceback: 0»;
- `xgw diag` — строка «Перехват» с «включён, правила загружены»; строк «Эталон правил» и
  «Маршрутизация» нет.

Если не так: «расхождение с текстом правил:» не «нет» — **дефект «эталон не сходится с текстом
правил»**: записать строку целиком (в ней только имена цепочек и наборов) и строку `xgw diag`
«Эталон правил»; продолжать. «эталон правил: нет» при «расхождение: нет» — записать «не по
ожиданию» и число «эталон правил не снят». `check` — `False` — подожди 60 секунд, повтори
`sudo python3 -I w2check.py check`; снова `False` — **дефект «правила считаются не
загруженными»**. «загрузок правил заново» 2 и больше — **дефект «загрузка правил по кругу»**.

## 3. Тестовые правки (если заказчик согласился на пункт 2)

Шаг 3.1. Два чужих правила маршрутизации: с меткой XGW, но только для несуществующего
пользователя (pref 101), и раньше правил XGW, но только для пакетов из 203.0.113.0/24 (pref 50):

```bash
cd "$HOME/xgw-w2" && T=$(sudo python3 -I w2check.py num table) && M=$(sudo python3 -I w2check.py num mark) && sudo ip rule add fwmark "$M" uidrange 4000000000-4000000000 lookup "$T" pref 101 && sudo ip rule add from 203.0.113.0/24 lookup main pref 50 && echo "правила добавлены"; sudo python3 -I w2check.py rules | tee r-31.txt; sudo xgw diag 2>&1 | grep -E 'Перехват|Эталон правил|Маршрутизация' | tee -a r-31.txt
```

Ожидается:
- «правила добавлены»;
- `rules` — в «правила в таблицы XGW» появилось «pref 101 (таблица N, с другими условиями)»;
  «чужие раньше XGW: pref 50»; «тестовое правило с uidrange (pref 101): на месте; тестовое
  правило раньше XGW (pref 50): на месте»;
- `xgw diag` — строка «Маршрутизация» с «pref 50» (предупреждение); «Перехват» — «включён,
  правила загружены».

Если не так: команда `ip rule add` вывела ошибку — записать её; если «правила добавлены» нет,
шаги 3.2 и 3.3 всё равно выполнить, а в 3.4 записать ответ команд удаления. Строки
«Маршрутизация» нет — **не по ожиданию**: записать.

Шаг 3.2. Чужой элемент в наборе «мимо VPN» (bypass4). Если в шаге 1.3 было «набора bypass4 нет»
— шаг пропустить.

```bash
cd "$HOME/xgw-w2" && date +%s > t-32.txt && sudo nft add element ip xgw bypass4 '{ 203.0.113.0/24 }' && echo "элемент добавлен"; sudo python3 -I w2check.py setcheck | tee r-32.txt
```

Ожидается: «элемент добавлен»; «тестовый элемент 203.0.113.0/24: есть».

Затем через минуту:

```bash
cd "$HOME/xgw-w2" && sleep 60; for m in setcheck rules capstate check; do sudo python3 -I w2check.py $m; done 2>&1 | tee -a r-32.txt; sudo journalctl -u xgw --since "@$(cat t-32.txt)" -o short-unix --no-pager | sudo python3 -I w2check.py log "$(cat t-32.txt)" | tee -a r-32.txt
```

Ожидается (записать **целиком**):
- **`setcheck` — «тестовый элемент 203.0.113.0/24: нет»** (шлюз убрал его сам);
- журнал — «загрузок правил заново: 1 (первая — через N с после метки)» — **записать N** (не
  больше 60);
- **`rules` — «тестовое правило с uidrange (pref 101): на месте»** (загрузка правил чужое правило
  не тронула) и правило XGW pref 100 на месте;
- `capstate` — «эталон правил: есть; …; расхождение с текстом правил: нет»; `check` — `True`.

Если не так: тестовый элемент «есть» — `sleep 60` и повтори вторую команду; снова «есть» —
**дефект «чужой элемент набора не замечен»**: убери его сам —
`sudo nft delete element ip xgw bypass4 '{ 203.0.113.0/24 }'` — и запиши. «тестовое правило с
uidrange (pref 101): нет» — **дефект «XGW удалил чужое правило»**.

Шаг 3.3. Лишний маршрут «недоступно» в таблице XGW:

```bash
cd "$HOME/xgw-w2" && date +%s > t-33.txt && sudo ip route add unreachable 203.0.113.0/24 table "$(sudo python3 -I w2check.py num table)" && echo "маршрут добавлен"; for m in routes routeget; do sudo python3 -I w2check.py $m; done 2>&1 | tee r-33.txt
```

Ожидается: «маршрут добавлен»; `routes` — у первой таблицы «тестовый маршрут 203.0.113.0/24:
есть»; `routeget` — «помеченный пакет от устройства сети к 203.0.113.5: ошибка — …unreachable»
(или похожее). Это и есть то, что исправлено: с таким маршрутом помеченный пакет к этой сети шёл
бы не в Xray.

Затем через минуту:

```bash
cd "$HOME/xgw-w2" && sleep 60; for m in routes routeget capstate check; do sudo python3 -I w2check.py $m; done 2>&1 | tee -a r-33.txt; sudo journalctl -u xgw --since "@$(cat t-33.txt)" -o short-unix --no-pager | sudo python3 -I w2check.py log "$(cat t-33.txt)" | tee -a r-33.txt
```

Ожидается (записать **целиком**):
- **`routes` — «тестовый маршрут 203.0.113.0/24: нет»** (шлюз убрал его сам);
- **`routeget` — «… local (в Xray, TPROXY)»**;
- журнал — «загрузок правил заново: 1 (первая — через N с после метки)» — записать N (не больше
  60);
- `capstate` — как в шаге 3.2; `check` — `True`.

Если не так: тестовый маршрут «есть» — `sleep 60` и повтори вторую команду; снова «есть» —
**дефект «лишний маршрут не замечен»**: убери его сам —
`sudo ip route del unreachable 203.0.113.0/24 table "$(sudo python3 -I w2check.py num table)"` —
и запиши.

Шаг 3.4. Убрать оба тестовых правила (их шлюз не трогает и не должен):

```bash
cd "$HOME/xgw-w2" && T=$(sudo python3 -I w2check.py num table) && M=$(sudo python3 -I w2check.py num mark); sudo ip rule del fwmark "$M" uidrange 4000000000-4000000000 lookup "$T" pref 101; sudo ip rule del from 203.0.113.0/24 lookup main pref 50; date +%s > t-watch.txt; for m in rules routes setcheck routeget; do sudo python3 -I w2check.py $m; done 2>&1 | tee r-34.txt; sudo xgw diag 2>&1 | grep -E 'Перехват|Эталон правил|Маршрутизация' | tee -a r-34.txt
```

Ожидается: `rules` — «чужие раньше XGW: нет», «тестовое правило с uidrange (pref 101): нет;
тестовое правило раньше XGW (pref 50): нет», правила XGW — как в шаге 1.3; `routes` и
`setcheck` — тестовых маршрута и элемента нет; `routeget` — `local`; `xgw diag` — «Перехват …
правила загружены», строки «Маршрутизация» нет.

Если не так: `ip rule del` ответил «No such file or directory» — такого правила уже не было:
записать.

Если заказчик **не** согласился на пункт 2 — выполни только это, чтобы была метка наблюдения:

```bash
cd "$HOME/xgw-w2" && date +%s > t-watch.txt && echo "метка записана"
```

## 4. Наблюдение (если заказчик согласился на пункт 3)

Шаг 4.1. 10 минут без правок:

```bash
sleep 600; cd "$HOME/xgw-w2" && sudo journalctl -u xgw --since "@$(cat t-watch.txt)" -o short-unix --no-pager | sudo python3 -I w2check.py log "$(cat t-watch.txt)" | tee log-watch.txt; for m in state capstate check; do sudo python3 -I w2check.py $m; done 2>&1 | tee -a log-watch.txt
```

(Если терминал обрывает длинные команды — `sleep 110` 5 раз и `sleep 50`, затем команда без
`sleep`.)

Ожидается (записать **целиком**): **«загрузок правил заново: 0»** (главная проверка: правила не
загружаются по кругу); «эталон правил не снят: 0»; «не сходятся с текстом правил: 0»; «ошибок
загрузки правил: 0»; «Traceback: 0»; `HEALTHY`; `capstate` — «эталон правил: есть; …;
расхождение … нет»; `check` — `True`, записать X и Y.

Если не так: «загрузок правил заново» больше 0 — **дефект «загрузка правил по кругу»**: записать
число. «эталон правил не снят» больше 0 — **не по ожиданию**: записать число.

## 5. Итог

Шаг 5.1. Секреты и итог:

```bash
cd "$HOME/xgw-w2" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c -E 'vless://|vmess://|trojan://|ss://|hysteria2://|hy2://|tuic://' | tee secrets.txt; date '+%F %T' | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|Ожидает окна' | tee -a final.txt; for m in units state sub rules setcheck; do sudo python3 -I w2check.py $m; done 2>&1 | tee -a final.txt
```

Ожидается: `0`; `HEALTHY`, перехват включён, Xray 26.10.31, sing-box 1.14.4, строки «Ожидает
окна перезапуска» нет; четыре службы `active`; режим пула и «выбран вручную» — как в шаге 1.3;
тестовых правил и элемента нет.

**Скажи заказчику** (дословно): «Проверка закончена, пишу отчёт.»

## Если что-то пошло не так

- Пропал интернет или доступ, или заказчик не отвечает **2 минуты** — **сразу**: убери тестовые
  правки командами «убери его сам» из шагов 3.2 и 3.3 и командой шага 3.4; если
  `systemctl is-active xgw` — не `active`, то `sudo systemctl start xgw`; подожди 30 секунд.
  Записать время и строки `sudo python3 -I w2check.py state` и `sudo xgw status 2>&1 | head -5`
  (без имён). Дальше — §5 и отчёт.
- Не `HEALTHY` больше 5 минут, службы не `active` — записать, сообщить заказчику, ничего не
  перезапускать.

## 6. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave2-<ДАТА>.md` в клоне (`<ДАТА>` — дата начала
проверки, ГГГГ-ММ-ДД), коммит «Отчёт: XGW 0.2.0, волна 2 кросс-аудита» и `git push` в
`freepool`. Только этот файл (`git add` только его). Без имён серверов, устройств и подписок,
адресов, доменов и строк журнала. Шаблон (заполни каждую ячейку; пропущенное — «не
выполнялся»):

```markdown
# Отчёт: XGW 0.2.0 — волна 2 кросс-аудита: эталон правил, наборы, ip rule, таблицы маршрутов

Код: <хеш>. Установка: <время>, код <код>. Согласие заказчика: пункты <…>.
w2check.py: <сумма>. Режим пула до проверки: <…>. Ядра: Xray <…>, sing-box <…>. Исполнитель:
<модель>.

## Итог
| Эталон после установки (есть / расхождение) | Проверка правил до → после, с (X / Y) | Элемент в bypass4 убран через, с | Маршрут в таблице XGW убран через, с; пакет снова в Xray | Чужое правило pref 101 после загрузки правил | pref 50 в xgw diag | Загрузок правил заново за 10 мин |
|---|---|---|---|---|---|---|
| <есть / нет> | <2.1/0.4 → 3.0/0.5> | <25> | <30; да> | <на месте> | <да> | <0> |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.0 предусловие | … | … |
| 1.3 до | — | … |
| 2.1 код | … | … |
| 2.2 установка | … | … |
| 2.3 после установки | … | … |
| 3.1 чужие правила | … | … |
| 3.2 элемент bypass4 | … | … |
| 3.3 маршрут в таблице XGW | … | … |
| 3.4 уборка | … | … |
| 4.1 наблюдение 10 мин | … | … |
| 5 итог | … | … |

## Выводы шагов
- <строки помощника по шагам (из файлов $HOME/xgw-w2/…); строки xgw diag «Перехват»,
  «Эталон правил», «Маршрутизация»; ответы заказчика дословно, без имён>

## Дефекты
<нет / нумерованный список: шаг, что ожидалось, что получилось, строки помощника>

## Наблюдения
<…>
```
