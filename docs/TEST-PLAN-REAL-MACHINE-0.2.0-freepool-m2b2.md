# Проверка XGW 0.2.0: бесплатные серверы, веха М2б.2 (весь дом через бесплатные серверы)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-fpb2/…`). Файл помощника создавай только командой шага 1.2, выполненной в
терминале. Блок команды копируй целиком, ничего в нём не меняя.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0. Телефон — S25 Ultra в домашней сети.
Команды — в терминале сеанса заказчика (`sudo` от его имени).

Если на этой машине идёт или не закончено ТЗ `docs/TEST-PLAN-REAL-MACHINE-0.2.0-freepool-tab.md`
— сначала оно, потом это.

Что нового (ASSUMPTIONS п. 267, план — «М2б.2 — весь дом»). В М2б.1 через бесплатные серверы
ходило одно устройство; теперь — **весь дом одной кнопкой**:
1. На вкладке «Бесплатные серверы» — кнопка «Весь дом через бесплатные» (с подтверждением).
   После неё через допущенные бесплатные серверы идут все устройства, эта машина, Docker и
   запросы DNS; российские домены (.ru, .su, .рф) — напрямую, как всегда.
2. **Подписка — только несущий канал**: через её серверы идут лишь каналы самого шлюза (списки
   бесплатных серверов, подписки, обновления ядер). В рабочем конфиге Xray это правило
   `http-in, socks-in → auto` перед последним правилом, а последнее правило (весь прочий
   трафик) ведёт в балансировщик `pool`. Плановых замеров скорости серверов подписки в этом
   режиме нет.
3. **DNS через пул — по TCP** (`tcp://1.1.1.1`, `tcp://8.8.8.8`): проверки пула меряют только
   TCP, а бесплатный сервер может не пропускать UDP.
4. Свои серверы устройств (выбор сервера в строке устройства) на время режима не действуют.
5. В главной карточке панели — сервер пула («Бесплатный сервер …») и напоминание с кнопкой
   «Вернуть режим подписок». Без допущенных серверов панель режим не включает.
6. При включении и возврате Xray может перезапуститься — интернет на несколько секунд.

Здесь, у разработчика, — только юнит-тесты затронутых модулей, ruff и `node --check` панели;
настоящий трафик, DNS по TCP через бесплатные серверы и панель не проверялись. Всё это — на
этой машине.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*` (и `xgw-fp@*`), `tailscaled`,
  NetworkManager, `ssh`; ручные `nft` (кроме `nft list`), `ip`, `ip netns`, `iptables`, `tc`,
  `sysctl -w`, `systemd-run`, `apt`; команды `tailscale`, `xray`, `sing-box`, `sstpc`, `pppd`.
  `sudo xgw pool mode …` — только в шагах 3.1 (`observe`), 6.1 и 8.1 (если заказчик не нажал
  кнопку) и по правилам раздела «Если что-то пошло не так».
- Самому открывать сайты источников (vpngate, vpnbook), файлы списков на GitHub и сайты для
  проверки страны. Сайты на устройствах открывает только заказчик. Кнопки замера скорости в
  панели не нажимать (и не просить).
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/run/xgw`, `/etc/systemd`, код XGW. Печатать `config.toml`, `panel.json`, рабочие конфиги
  Xray и sing-box, файлы в `/var/lib/xgw/freepool` — в них ключи подписок, пароли и ссылки
  серверов. Кнопки, вкладки и выбор в панели нажимает только заказчик. Коммитить что-либо,
  кроме отчёта (§9).
- Писать в отчёт: **имена серверов** (и бесплатных, и подписки — заказчик видит их в панели, в
  отчёт они не идут), адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP (и тот, что покажет сайт проверки страны), токены,
  адреса и домены подписок, IP, домены и ссылки серверов VPN, логины и пароли, строки журнала.
  Можно: адреса устройств в домашней сети (`192.168.…`), коды стран, названия источников,
  надписи панели без имён серверов, счётчики, статусы, размеры, времена, строки помощника.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю режим «весь дом через бесплатные серверы» (веха М2б.2). По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд. Внешний интерфейс (WAN), его соединение и DHCP
установка не трогает.
(2) Если наблюдение за бесплатными серверами выключено, я включу его командой
`sudo xgw pool mode observe`: шлюз собирает списки бесплатных серверов через подписку и
проверяет их (до 4 в минуту, около 15–20 МБ в час, подключений SSTP — не больше 2 в час).
Через 30 минут посмотрим, сколько серверов допущено к трафику.
(3) Вы нажмёте на вкладке «Бесплатные серверы» кнопку «Весь дом через бесплатные» и
подтвердите. После этого все устройства дома, этот компьютер и Docker пойдут через бесплатные
серверы, запросы DNS — тоже; российские сайты (.ru, .su, .рф) — напрямую. Владельцы бесплатных
серверов неизвестны и видят, к каким сайтам вы ходите; содержимое сайтов с https защищено, без
https — нет. Xray может перезапуститься — интернет пропадёт на несколько секунд. Подписка
останется несущим каналом (списки, подписки, обновления). Если интернет перестанет работать —
сразу скажите мне: вернём режим подписок.
(4) На телефоне и на этом компьютере вы откроете сайт, который показывает страну выхода
(например ipinfo.io), и скажете мне только страну — без адреса.
(5) Около часа вы будете обычным образом пользоваться интернетом дома (телефон, компьютер,
другие устройства: сайты, видео, приложения) и скажете, что открывалось и как.
(6) По моей просьбе прочитаете, что написано в панели (имена серверов называть не нужно).
(7) В конце вы вернёте режим подписок кнопкой «Вернуть режим подписок» и выключите наблюдение
кнопкой «Выключить» (не ответите за 30 минут — сделаю командами).
(8) В конце откроете любой сайт на этом компьютере и на телефоне.
Проверка займёт около двух с половиной часов. Можно согласиться не на все пункты.»

Против пункта 1, 2 или 3 — **стоп**. Против 4 — шаги 4.4 и 6.3 пропустить; против 5 — шаг 5.1
сократить до 15 минут без вопроса заказчику; против 6 — шаг 4.3 пропустить; против 7 (только
кнопки) — в шагах 6.1 и 8.1 сделать командами; против 8 — шаг 8.3. В отчёте у пропущенного —
«не выполнялся». Если ответа на вопрос нет — не начинать, спросить ещё раз.

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-fpb2" && chmod 700 "$HOME/xgw-fpb2" && cd "$HOME/xgw-fpb2" && cat > fpb2check.py <<'EOF'
"""XGW 0.2.0, бесплатный пул (веха М2б.2: весь дом через бесплатные серверы): помощник
проверки. Только читает: состояние XGW (/run/xgw, /var/lib/xgw/freepool), рабочий конфиг Xray,
метрики Xray на 127.0.0.1 и журнал со стандартного ввода — счётчики, коды стран, итоги и
да/нет, без адресов, имён, ссылок и ключей. route — правила, балансировщики, пробы ядра и DNS
рабочего конфига; xstats — трафик Xray по выходам с его запуска; admitted — допущенные к
трафику серверы пула; config — серверы пула среди выходов подписки и выходы pool-*.
Режимы: units, pool, admitted, route, config, xstats, xray, digest, subs, leak, log."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = os.environ.get("FPB2_LIB", "/opt/xgw/lib")
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
LINKS = ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://", "tuic://")
MB = 1048576


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


def counted(items):
    found = {}
    for item in items:
        found[item] = found.get(item, 0) + 1
    return ", ".join(f"{name} {count}" for name, count in sorted(found.items())) or "—"


def secret_of(entry):
    users = entry.get("users") if isinstance(entry.get("users"), list) else []
    first = users[0] if users and isinstance(users[0], dict) else {}
    return str(first.get("id") or first.get("password") or entry.get("id")
               or entry.get("password") or "")


def xray_ids(outbound):
    """(адрес, порт, ключ) каждого сервера исходящего Xray: сравнение целиком, не по адресу."""
    settings = outbound.get("settings") if isinstance(outbound, dict) else None
    if not isinstance(settings, dict):
        return []
    entries = [*(settings.get("vnext") or []), *(settings.get("servers") or []), settings]
    return [(entry["address"].lower(), str(entry.get("port") or ""), secret_of(entry))
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("address"), str)
            and entry["address"]]


def target(rule):
    if rule.get("balancerTag"):
        return f"балансировщик {rule['balancerTag']}"
    return f"выход {rule.get('outboundTag')}"


def dns_host(entry):
    address = str((entry.get("address") if isinstance(entry, dict) else entry) or "")
    host = address.split("://", 1)[-1].split("/", 1)[0]
    return address, host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def total(counters):
    return sum(value for value in (counters or {}).values()
               if isinstance(value, int) and not isinstance(value, bool))


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
elif mode == "pool":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    age = int(time.time() - float(status["updated"])) if status.get("updated") else None
    print(f"status.json: {'нет' if age is None else f'{age} с назад'}; состояние шлюза: "
          f"{status.get('state')}")
    pool = status.get("free_pool")
    if not isinstance(pool, dict):
        print("free_pool в состоянии: нет")
        sys.exit(0)
    print(f"free_pool в состоянии: режим {pool.get('mode')}, регион {pool.get('region')}; "
          f"найдено {pool.get('found')}; проверено {pool.get('checked')}, пригодно "
          f"{pool.get('ready')}")
    flow = pool.get("traffic")
    if isinstance(flow, dict):
        print(f"через пул: весь дом {'да' if flow.get('all') else 'нет'}; устройств "
              f"{len(flow.get('devices') or [])}; серверов в pool {flow.get('members')}, живых "
              f"{flow.get('alive')}; закрыто: {'ДА' if flow.get('closed') else 'нет'}; страна "
              f"{flow.get('country') or '—'}; задержка {flow.get('delay_ms')} мс")
    else:
        print("через пул: никто")
elif mode == "admitted":
    cfg, paths = xgw()
    from xgw.freepool import traffic as fptraffic

    found = fptraffic.admitted(cfg, paths, time.time())
    print(f"допущено к трафику: {len(found)} (OK {sum(1 for i in found if i.verdict == 'OK')}, "
          f"SLOW {sum(1 for i in found if i.verdict == 'SLOW')}); страны: "
          f"{counted(i.node.country.upper() for i in found)}; источники: "
          f"{counted(i.variant.provider for i in found)}; протоколы: "
          f"{counted(i.variant.protocol for i in found)}")
elif mode == "route":
    cfg, paths = xgw()
    from xgw.freepool import traffic as fptraffic

    devices = fptraffic.pool_devices(cfg)
    own = [ip for ip, server in cfg.managed.routes.items() if server != "pool"]
    work = read_json(paths.xray_config_file) or {}
    routing = work.get("routing") or {}
    rules = [rule for rule in routing.get("rules") or [] if isinstance(rule, dict)]
    print(f"режим пула: {cfg.free_pool.mode}; весь дом: "
          f"{'да' if fptraffic.whole_house(cfg) else 'нет'}; в настройках устройств через пул: "
          f"{len(devices)}, своих серверов устройств: {len(own)}")
    print("последнее правило (весь прочий трафик) → "
          + (target(rules[-1]) if rules else "правил нет"))
    carrier = next((i for i, rule in enumerate(rules)
                    if rule.get("inboundTag") == ["http-in", "socks-in"]), None)
    print("правило несущего канала (http-in, socks-in): "
          + (f"есть → {target(rules[carrier])}" if carrier is not None else "нет"))
    direct = next((i for i, rule in enumerate(rules)
                   if "domain:ru" in (rule.get("domain") or [])), None)
    print("российские домены напрямую раньше последнего правила: "
          + ("да" if direct is not None and direct < len(rules) - 1 else "НЕТ"))
    print(f"правил по адресу источника (свои серверы и устройства пула): "
          f"{sum(1 for rule in rules if rule.get('source'))}")
    balancers = {str(item.get("tag")): item for item in routing.get("balancers") or []
                 if isinstance(item, dict)}
    found = balancers.get("pool")
    print("балансировщик pool: " + (f"есть; fallbackTag {found.get('fallbackTag')}"
                                    if found else "нет"))
    print(f"балансировщик auto: selector {(balancers.get('auto') or {}).get('selector')}")
    print("пробы ядра (subjectSelector): "
          f"{(work.get('burstObservatory') or {}).get('subjectSelector')}")
    servers = (work.get("dns") or {}).get("servers") or []
    general = [dns_host(entry) for entry in servers
               if not (isinstance(entry, dict) and entry.get("domains"))]
    direct_ips = {ip for rule in rules if rule.get("outboundTag") == "direct"
                  for ip in rule.get("ip") or []}
    print(f"DNS-серверов Xray для всех доменов: {len(general)}; по TCP (tcp://): "
          f"{sum(1 for address, _host in general if address.startswith('tcp://'))}; их адресов "
          f"в прямых правилах: {sum(1 for _address, host in general if host in direct_ips)}")
elif mode == "config":
    cfg, paths = xgw()
    from xgw.fetch import is_bogon
    from xgw.freepool.store import PoolStore

    store = PoolStore(paths)
    whole = {ident for provider in cfg.free_pool.providers
             for variant in store.variants(provider)
             for ident in xray_ids(variant.outbound or {})}
    work = read_json(paths.xray_config_file) or {}
    outbounds = [item for item in work.get("outbounds") or [] if isinstance(item, dict)]
    sub = [ident for item in outbounds
           if str(item.get("tag") or "").startswith(("proxy-", "spare-"))
           for ident in xray_ids(item)]
    pooled = [item for item in outbounds if str(item.get("tag") or "").startswith("pool-")]
    bridged = [item for item in pooled
               if any(ident[0] == "127.0.0.1" for ident in xray_ids(item))]
    direct = [ident for item in pooled if item not in bridged for ident in xray_ids(item)]
    public = sum(1 for ident in direct if IPV4.fullmatch(ident[0]) and not is_bogon(ident[0]))
    print(f"выходов подписки (proxy-/spare-): {len(sub)}; из них вариантов бесплатного пула "
          f"целиком: {sum(1 for item in sub if item in whole)}")
    print(f"выходов бесплатного пула (pool-*): {len(pooled)}; мостом sing-box {len(bridged)}; "
          f"у прямых адрес — публичный IPv4: {public} из {len(direct)}")
elif mode == "xstats":
    cfg, paths = xgw()
    from xgw.xraycore import metrics

    try:
        data = metrics.fetch_metrics(cfg.xray.metrics_port)
    except Exception as exc:
        print(f"метрики Xray не прочитаны: {type(exc).__name__}")
        sys.exit(0)
    outbound = (data.get("stats") or {}).get("outbound") or {}
    pool = {str(tag): total(item) for tag, item in outbound.items()
            if str(tag).startswith("pool-")}
    subscription = sum(total(item) for tag, item in outbound.items()
                       if str(tag).startswith(("proxy-", "spare-")))
    observatory = metrics.parse_observatory(data)
    tags = sorted(tag for tag in observatory if tag.startswith("pool-"))
    status = read_json(paths.status_file) or {}
    flow = (status.get("free_pool") or {}).get("traffic") or {}
    pinned = str(flow.get("tag") or "")
    budget = (status.get("budget") or {}).get("all_mb")
    print(f"трафик с запуска Xray, МБ: пул {sum(pool.values()) / MB:.1f} (у закреплённого "
          f"{pool.get(pinned, 0) / MB:.1f}); подписка {subscription / MB:.1f}; напрямую "
          f"{total(outbound.get('direct')) / MB:.1f}; DNS {total(outbound.get('dns-out')) / MB:.1f}"
          f"; закрыто (block) {total(outbound.get('block')) / MB:.1f}; время "
          f"{time.strftime('%H:%M:%S')}")
    print(f"выходов pool-* под пробами ядра: {len(tags)}, живых: "
          f"{sum(1 for tag in tags if observatory[tag].get('alive'))}; закреплён: "
          f"{'да' if pinned else 'нет'}"
          + (" (его тега нет среди проб!)" if pinned and pinned not in tags else ""))
    print("расход проверок подписки по сводке: "
          + (f"{float(budget):.0f} МБ в сутки" if budget else "нет в сводке"))
elif mode == "xray":
    print(f"Xray: запущен {show('xgw-xray.service', 'ExecMainStartTimestamp') or '?'}; "
          f"NRestarts {show('xgw-xray.service', 'NRestarts') or '?'}")
elif mode == "digest":
    cfg, paths = xgw()
    from xgw.net.capture import capture_for

    capture = capture_for(cfg, paths)
    saved = capture._state().get("tables")
    current = capture._tables_digest()
    verdict = ("не запомнен" if saved is None else "не прочитан" if current is None
               else "совпадает" if current == saved else "НЕ совпадает")
    print(f"отпечаток таблиц: {verdict}; правила на месте (loaded): {capture.loaded()}")
elif mode == "subs":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    texts = [str((item or {}).get("error") or "") for item in
             (status.get("sub_errors") or {}).values()]
    data = read_json(paths.var / "inventory.json") or {}
    print(f"подписок с ошибкой: {sum(1 for text in texts if text)}; серверов в списке: "
          f"{len(data.get('servers') or [])}")
elif mode == "leak":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}; строк со ссылкой сервера: "
          f"{sum(1 for line in lines if any(link in line for link in LINKS))}")
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, words in (
        ("событие «весь дом через бесплатные серверы»",
         ("бесплатный пул: весь дом через бесплатные серверы",)),
        ("событие «режим подписок возвращён»", ("режим подписок возвращён",)),
        ("сервер пула для всего дома выбран", ("бесплатный пул: весь дом идёт через",)),
        ("у всего дома закрыто", ("у всего дома закрыто",)),
        ("закрепление сервера пула не удалось", ("сервер бесплатного пула не закреплён",)),
        ("плановых замеров скорости подписки", ("замер скорости proxy-",
                                                "замер скорости spare-")),
        ("контроль скорости: «придушен»", ("придушен",)),
        ("проверок серверов пула", ("бесплатный пул: проверка",)),
        ("применений через API", ("применено через API без перезапуска",)),
        ("применений с перезапуском Xray", ("применено с перезапуском Xray",)),
        ("откат на last-good", ("last-good",)),
        ("шаг пула не выполнен", ("бесплатный пул: шаг не выполнен",)),
        ("Read-only file system", ("Read-only file system",)),
        ("Permission denied", ("Permission denied",)),
        ("Traceback", ("Traceback",)),
    ):
        print(f"{label}: {sum(1 for line in lines if any(word in line for word in words))}")
    for label, reason in (("включение «весь дом»", "бесплатный пул: весь дом: "),
                          ("возврат режима подписок", "бесплатный пул: режим подписок: "),
                          ("состав пула", "серверов для устройств")):
        ours = [line for line in lines if reason in line]
        print(f"сборок «{label}»: {len(ours)}; из них с перезапуском Xray: "
              f"{sum(1 for line in ours if 'с перезапуском Xray' in line)}")
else:
    print("режим: units | pool | admitted | route | config | xstats | xray | digest | subs | "
          "leak | log")
EOF
python3 -c "import hashlib;d=open('fpb2check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee before.txt; sudo xgw pool 2>&1 | head -1 | tee -a before.txt; for m in units subs; do sudo python3 -I fpb2check.py $m; done | tee -a before.txt; sudo journalctl -u xgw --since "60 min ago" --no-pager | sudo python3 -I fpb2check.py log | tee log-before.txt
```

Ожидается:
- `a104e7a5ee4ae84c`;
- `Состояние: …`, `Перехват: включён …`, строки `Xray …` и `sing-box …` — записать;
- первая строка `xgw pool` — «Бесплатный пул: выключен; …» или «… наблюдение (трафик через
  подписку); …» — **записать, какая** (от неё зависит шаг 3.1);
- четыре службы `active`; «подписок с ошибкой: …; серверов в списке: …» — записать;
- счётчики журнала — записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать и продолжить. Первая строка `xgw pool` —
«весь дом через бесплатные серверы» (режим остался с другого прогона) — попросить заказчика
нажать «Вернуть режим подписок» в главной карточке панели и выполнить шаг заново.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def whole_house' src/xgw/freepool/traffic.py && grep -q 'pool_all: bool = False' src/xgw/generator/builder.py && grep -q '"inboundTag": \["http-in", "socks-in"\]' src/xgw/generator/builder.py && grep -q 'address = f"tcp://{address}"' src/xgw/generator/builder.py && grep -q '"on": "Весь дом идёт через бесплатные серверы' src/xgw/actions.py && grep -q 'choices=("off", "observe", "on")' src/xgw/cli.py && grep -q 'def _pool_house' src/xgw/diag.py && grep -q 'id="house-back"' src/xgw/ui/index.html && grep -q 'id="pool-house"' src/xgw/ui/index.html && grep -q 'def server_rows' src/xgw/freepool/pool.py && echo "правка в коде: есть"; cd "$HOME/xgw-fpb2"
```

Ожидается: «правка в коде: есть». Записать хеш.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику.

Шаг 2.2. **Скажи заказчику** (дословно): «Запускаю установку. Внешний интерфейс (WAN), его
соединение и DHCP она не трогает; интернет дома пропадёт на несколько секунд, пока
перезапускаются службы XGW. Дождитесь, пожалуйста, конца — я сообщу.» Затем:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fpb2/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fpb2/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|демон xgw' "$HOME/xgw-fpb2/install.txt"; cd "$HOME/xgw-fpb2"
```

Ожидается: «код 0», «демон xgw запущен». Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке, режим подписок:

```bash
sleep 120; cd "$HOME/xgw-fpb2" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee after-install.txt; for m in units digest route pool xray; do sudo python3 -I fpb2check.py $m; done | tee -a after-install.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpb2check.py log | tee log-install.txt
```

Ожидается:
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки; четыре службы
  `active`; «отпечаток таблиц: совпадает; правила на месте (loaded): True»;
- `route`: «режим пула: off» (или observe); «весь дом: нет»; «последнее правило (весь прочий
  трафик) → балансировщик auto»; «правило несущего канала (http-in, socks-in): нет»;
  «российские домены напрямую раньше последнего правила: да»; «правил по адресу источника:
  N» — записать N (свои серверы и устройства пула, как настроено); «DNS-серверов Xray для всех
  доменов: D; по TCP (tcp://): 0; их адресов в прямых правилах: 0» — записать D (обычно 2);
- «Xray: запущен …» — записать;
- в журнале с установки «Traceback: 0».

Если не так: не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать, сообщить
заказчику и продолжить; «весь дом: да» или «по TCP» больше 0 — **стоп**: режим остался с
другого прогона (попросить заказчика «Вернуть режим подписок» и повторить шаг).

## 3. Наблюдение и допущенные серверы

Шаг 3.1. Только если в шаге 1.2 наблюдение было **выключено**; иначе — пропустить, в отчёте
«уже было включено»:

```bash
cd "$HOME/xgw-fpb2" && date '+%F %T' | tee observe-time.txt && sudo xgw pool mode observe 2>&1 | tee mode-on.txt
```

Ожидается: «Наблюдение за бесплатным пулом включено: … Демон применит режим на ближайшем шаге».

**Скажи заказчику** (дословно): «Наблюдение включено. Через 30 минут посмотрим, сколько
бесплатных серверов допущено, и тогда попрошу вас включить весь дом.» Подожди **30 минут**
(если наблюдение уже было включено — 5 минут).

Шаг 3.2. Сколько серверов допущено к трафику:

```bash
cd "$HOME/xgw-fpb2" && for m in admitted pool; do sudo python3 -I fpb2check.py $m; done | tee admitted.txt
```

Ожидается: «допущено к трафику: N (OK …, SLOW …); страны: …; источники: …; протоколы: …», N —
от 1 до нескольких десятков; «free_pool в состоянии: режим observe …» — записать.

Если не так: N = 0 — подождать ещё 30 минут и повторить; снова 0 — **стоп**: режим всего дома
проверять не на чем (выполнить шаг 8.1 — выключить наблюдение — и §9, в отчёте «отложено: нет
допущенных серверов»).

## 4. Весь дом через бесплатные серверы

Шаг 4.1. Запомнить время и **попроси заказчика** (дословно):

```bash
cd "$HOME/xgw-fpb2" && date '+%F %T' | tee switch-time.txt
```

«Откройте, пожалуйста, панель XGW, вкладку «Бесплатные серверы», и нажмите кнопку «Весь дом
через бесплатные». Прочитайте мне заголовок окна подтверждения и его последнюю фразу, затем
нажмите в нём «Весь дом через бесплатные». Что ответила панель?»

Ожидается: заголовок — «Пустить весь дом через бесплатные серверы?», последняя фраза — «Xray
может перезапуститься — интернет пропадёт на несколько секунд.»; ответ панели — «Весь дом идёт
через бесплатные серверы: устройства, эта машина, Docker и DNS. Подписка — только несущий
канал: …».

Если не так: ответ «Допущенных бесплатных серверов сейчас нет …» — повторить шаг 3.2; если
допущено больше 0 — записать оба вывода, **дефект «панель не включает при допущенных»**,
**стоп** (§8.1, §9); кнопки «Весь дом через бесплатные» нет — попросить обновить страницу
(Ctrl+F5) и спросить снова; снова нет — **дефект «нет кнопки всего дома»**, **стоп**.

Шаг 4.2. Через 2 минуты после ответа заказчика — что собрал шлюз:

```bash
cd "$HOME/xgw-fpb2" && sleep 120; for m in route pool config xray xstats digest; do sudo python3 -I fpb2check.py $m; done | tee house.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Бесплатный пул|^Весь дом' | sed -E 's/«[^»]*»/«<сервер>»/g' | tee -a house.txt; sudo xgw diag 2>&1 | grep -E 'Весь дом|Бесплатный пул|^Итог' | tee -a house.txt; sudo journalctl -u xgw --since "$(cat switch-time.txt)" --no-pager | sudo python3 -I fpb2check.py log | tee log-house.txt
```

Ожидается:
- `route`: «режим пула: on; весь дом: да»; **«последнее правило (весь прочий трафик) →
  балансировщик pool»**; **«правило несущего канала (http-in, socks-in): есть → балансировщик
  auto»**; «российские домены напрямую раньше последнего правила: да»; **«правил по адресу
  источника …: 0»**; «балансировщик pool: есть; fallbackTag block»; «балансировщик auto:
  selector ['proxy-']»; «пробы ядра (subjectSelector): ['proxy-', 'pool-']»; **«DNS-серверов
  Xray для всех доменов: D; по TCP (tcp://): D; их адресов в прямых правилах: 0»** — D как в
  шаге 2.3 (по TCP — все);
- `pool`: «состояние шлюза: HEALTHY» (это серверы подписки — несущий канал); «через пул: весь
  дом да; устройств …; серверов в pool M, живых L; закрыто: нет; страна XX; задержка … мс», M —
  от 1 до 8, L — от 1 до M;
- `config`: «… из них вариантов бесплатного пула целиком: 0»; «выходов бесплатного пула
  (pool-*): M …; у прямых адрес — публичный IPv4: все»;
- «Xray: запущен …» — время после `switch-time.txt` (перезапуск при включении) или прежнее —
  записать;
- `xstats` — записать все три строки (это начало отсчёта);
- «отпечаток таблиц: совпадает; … True»;
- `xgw status`: «Бесплатный пул (весь дом, регион EU): …», «Весь дом через бесплатные серверы —
  сервер «<сервер>» (XX), задержка … мс; живых L из M»;
- `xgw diag`: «OK    Весь дом через бесплатный пул: через бесплатный пул, серверов в «pool»: M;
  подписка — только входам демона (несущий канал)»; строку `Итог: …` — записать;
- журнал: «событие «весь дом через бесплатные серверы»: 1»; «сервер пула для всего дома выбран:
  1» (или больше); «сборок «включение «весь дом»»: 1; из них с перезапуском Xray: 0 или 1» —
  записать; «закрепление сервера пула не удалось: 0»; «Traceback: 0».

Если не так:
- «последнее правило → балансировщик auto» или «правило несущего канала: нет» — подождать 2
  минуты и повторить; снова так — **дефект «весь дом не включился»**, перейти к шагу 6.1;
- «правил по адресу источника» больше 0 — **дефект «свои серверы в режиме всего дома»**;
- «по TCP (tcp://)» меньше D — **дефект «DNS через пул не по TCP»** (если D-серверы в
  config.toml записаны схемой, например https://, — не дефект, записать);
- «закрыто: ДА» при допущенных серверах (шаг 3.2) — подождать 3 минуты и повторить; снова так
  — **дефект «весь дом закрыт при допущенных»**, перейти к шагу 6.1;
- в `config` вариантов пула среди выходов подписки больше 0 — **дефект «сервер пула в
  подписке»**;
- `diag` — не OK: записать строку дословно; «Traceback» больше 0 — записать (см. §8.2).

Шаг 4.3 (при согласии на пункт 6). **Попроси заказчика** (дословно):

«Прочитайте, пожалуйста, что сейчас в панели (имена серверов называть не нужно):
(а) надпись в цветной метке вверху справа;
(б) главная карточка с круглой кнопкой: заголовок, строка под ним, строка «Бесплатный сервер …»
(страна и миллисекунды) и жёлтая полоса с кнопкой — её текст и надпись на кнопке;
(в) вкладка «Подписки»: первая полоса над списком серверов — её текст;
(г) карточка «Устройства»: метка справа у устройств и можно ли выбрать сервер устройства;
(д) вкладка «Бесплатные серверы»: какие кнопки в заголовке, с каких слов начинается сводка, и
какая строка в источниках отмечена «сейчас через» (только её метки и миллисекунды).»

Ожидается:
- (а) «Через бесплатные серверы»;
- (б) «VPN включён»; «Эта машина и сеть … выходят через бесплатные серверы» (или похожее с
  «через бесплатные серверы»); «Бесплатный сервер <имя> (XX) · N мс» — страна та же, что в
  `house.txt`; полоса — «Весь дом идёт через бесплатные серверы; подписка — только несущий
  канал (списки бесплатных серверов, подписки, обновления).», кнопка — «Вернуть режим
  подписок»;
- (в) «Весь дом идёт через бесплатные серверы: серверы подписки несут только каналы шлюза — …»;
- (г) у устройств — «бесплатные серверы»; выбор сервера устройства неактивен (серый);
- (д) кнопки «Опросить источники» и «Вернуть режим подписок» («Выключить» нет); сводка — «Весь
  дом через бесплатные серверы (регион EU): найдено …»; у строки «сейчас через» — протокол,
  страна, «N мс».

Если не так: записать ответ дословно (без имён); нет полосы с кнопкой — **дефект «нет кнопки
возврата»**; метка вверху «Все серверы недоступны» или другое про подписку — **дефект
«здоровье не по пулу»**; прочее — мелкий дефект с названием по смыслу.

Шаг 4.4 (при согласии на пункт 4). **Попроси заказчика** (дословно): «Откройте, пожалуйста,
на телефоне и на этом компьютере сайт, который показывает страну выхода (например ipinfo.io).
Какая страна на каждом? Адрес не называйте.» Сразу после ответа:

```bash
cd "$HOME/xgw-fpb2" && sudo python3 -I fpb2check.py pool | tee country.txt
```

Ожидается: на обоих — страна из строки «через пул: … страна XX» (`country.txt`).

Если не так: страна другая — записать обе; если в `country.txt` страна сменилась по сравнению
с `house.txt` (закреплённый сервер сменился) — не дефект; страна подписки (как до включения)
на телефоне или компьютере — **дефект «устройство идёт мимо пула»**.

## 5. Обычная работа через пул

Шаг 5.1 (при согласии на пункт 5). **Попроси заказчика** (дословно): «Около часа пользуйтесь,
пожалуйста, интернетом дома как обычно — на телефоне, компьютере и других устройствах: сайты,
видео, приложения. Если что-то перестанет открываться — скажите сразу. Через час спрошу, как
всё работало.» Через 30 минут:

```bash
cd "$HOME/xgw-fpb2" && for m in pool xstats xray; do sudo python3 -I fpb2check.py $m; done | tee mid.txt
```

Ещё через 30 минут:

```bash
cd "$HOME/xgw-fpb2" && for m in pool xstats xray route; do sudo python3 -I fpb2check.py $m; done | tee hour.txt; sudo journalctl -u xgw --since "$(cat switch-time.txt)" --no-pager | sudo python3 -I fpb2check.py log | tee log-hour.txt
```

Затем **спроси заказчика** (дословно): «Как работал интернет этот час: что открывалось, что нет,
были ли перерывы или медленно?»

Ожидается:
- прирост трафика с `house.txt` до `hour.txt` (если Xray не перезапускался — разность чисел;
  если перезапускался — записать как есть): **через пул — заметно больше, чем через подписку**
  (если заказчик пользовался интернетом); через подписку — не больше расхода проверок за час
  (строка «расход проверок подписки по сводке: R МБ в сутки» — не больше R/24 × 2 + 30 МБ);
  напрямую — растёт (российские сайты);
- «Xray: запущен …» — то же время, что в `house.txt` (за час без перезапусков);
- `pool`: «закрыто: нет»; страна и число живых — записать (сервер мог смениться);
- журнал за весь режим: **«плановых замеров скорости подписки: 0»**, **«контроль скорости:
  «придушен»: 0»**; «у всего дома закрыто: 0»; «сборок «состав пула»: K; из них с перезапуском
  Xray: 0»; «сервер пула для всего дома выбран: …» — записать (сколько раз менялся);
  «Traceback: 0»;
- `route` — как в шаге 4.2;
- ответ заказчика — записать дословно.

Если не так:
- через подписку прироста больше нормы — записать числа, **дефект «трафик дома идёт через
  подписку»**;
- через пул прироста почти нет, а заказчик пользовался интернетом — **дефект «трафик мимо
  пула»**;
- Xray перезапускался — записать «сборок …» и время, **дефект «перезапуски в режиме всего
  дома»**;
- плановых замеров скорости подписки больше 0 — **дефект «замеры подписки в режиме всего
  дома»**;
- заказчик говорит, что интернет не работал или работал с долгими перерывами, — записать
  дословно, выполнить `sudo python3 -I fpb2check.py pool | tee bad.txt`, записать в
  «Наблюдения» (решение по качеству серверов — за разработчиком).

## 6. Возврат режима подписок

Шаг 6.1. **Попроси заказчика** (дословно): «В главной карточке панели нажмите, пожалуйста,
«Вернуть режим подписок». Что ответила панель и что теперь в главной карточке (без имён
серверов)?» Нет ответа 30 минут (или пункт 7 только командами) — командой:
`cd "$HOME/xgw-fpb2" && sudo xgw pool mode observe 2>&1 | tee back-cmd.txt`. Затем:

```bash
cd "$HOME/xgw-fpb2" && date '+%F %T' | tee back-time.txt
```

Ожидается: ответ панели — «Наблюдение за бесплатным пулом включено: списки серверов собираются
через подписку, серверы проверяются, а трафик идёт как прежде — через подписку»; в главной
карточке — полосы «Весь дом идёт через бесплатные серверы …» нет, строка «Сейчас через …» или
«Основной сервер …» (сервер подписки).

Шаг 6.2. Через 2 минуты:

```bash
cd "$HOME/xgw-fpb2" && sleep 120; for m in route pool xray xstats; do sudo python3 -I fpb2check.py $m; done | tee back.txt; sudo journalctl -u xgw --since "$(cat back-time.txt)" --no-pager | sudo python3 -I fpb2check.py log | tee log-back.txt
```

Ожидается:
- `route`: «режим пула: observe; весь дом: нет»; «последнее правило … → балансировщик auto»;
  «правило несущего канала: нет»; «правил по адресу источника: N» — **как в шаге 2.3**;
  «DNS-серверов … по TCP (tcp://): 0»; subjectSelector — `['proxy-']` (или с `'pool-'`, если
  у какого-то устройства выбран пул — как до проверки);
- `pool`: «через пул: никто» (или устройства, как до проверки);
- журнал: «событие «режим подписок возвращён»: 1»; «сборок «возврат режима подписок»: 1»
  (перезапуск Xray — записать); «Traceback: 0».

Если не так: «последнее правило → балансировщик pool» через 4 минуты — **дефект «режим
подписок не вернулся»**, сообщить заказчику (сеть руками не трогать); число правил по адресу
источника другое — **дефект «свои серверы не вернулись»**.

Шаг 6.3 (при согласии на пункт 4). **Попроси заказчика** (дословно): «Откройте ещё раз на
телефоне сайт проверки страны. Какая страна теперь?» Ожидается: страна подписки (может
совпасть со страной пула — тогда записать «совпадает»). Записать.

## 7. Секреты

Шаг 7.1.

```bash
cd "$HOME/xgw-fpb2" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpb2check.py leak | tee secrets.txt; ls -l /run/xgw/status.json | awk '{print $1}' | tee -a secrets.txt
```

Ожидается: «строк со ссылкой сервера: 0»; права `-rw-r--r--`.

Если не так: ссылки есть — **дефект «ссылки серверов в журнале»** (строки не копировать).

## 8. Выключение и итог

Шаг 8.1. **Попроси заказчика** (дословно): «На вкладке «Бесплатные серверы» нажмите
«Выключить». Что ответила панель?» Нет ответа 30 минут (или пункт 7 только командами) —
`cd "$HOME/xgw-fpb2" && sudo xgw pool mode off 2>&1 | tee off-cmd.txt`. Затем:

```bash
cd "$HOME/xgw-fpb2" && date '+%F %T' | tee off-time.txt; sleep 180; for m in route pool units digest subs; do sudo python3 -I fpb2check.py $m; done | tee off.txt
```

Ожидается: «Бесплатный пул выключен»; `route` — «режим пула: off; весь дом: нет; … →
балансировщик auto»; «free_pool в состоянии: нет»; службы `active`; отпечаток совпадает;
подписки — как до установки.

Шаг 8.2. Итог:

```bash
cd "$HOME/xgw-fpb2" && sleep 60; sudo journalctl -u xgw --since "$(cat off-time.txt)" --no-pager | sudo python3 -I fpb2check.py log | tee log-off.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpb2check.py log | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee -a final.txt
```

Ожидается: в `log-off.txt` «проверок серверов пула: 0»; в `final.txt` «Traceback: 0», «откат
на last-good: 0», «шаг пула не выполнен: 0», «Read-only file system» и «Permission denied» —
не больше, чем в `log-before.txt`; `HEALTHY`, перехват включён.

Если не так: Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -30 | tee traceback.txt`
(только строки с файлами и ошибкой, адреса — убрать); проверки после выключения — **дефект «пул
работает выключенным»**.

Шаг 8.3 (при согласии на пункт 8). **Попроси заказчика** (дословно): «Откройте любой сайт на
этом компьютере и на телефоне. Открываются?» Ожидается: «да». Нет — записать ответ и
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray' | tee sites.txt`, сообщить
заказчику.

## Если что-то пошло не так

- **Интернет пропал или почти не работает в режиме всего дома** (заказчик сказал сам или на
  вопрос) — сразу попросить заказчика нажать «Вернуть режим подписок» в главной карточке; не
  может — командой `sudo xgw pool mode observe`. Затем записать
  `cd "$HOME/xgw-fpb2" && for m in pool route xstats; do sudo python3 -I fpb2check.py $m; done | tee broken.txt; sudo journalctl -u xgw --since "$(cat switch-time.txt)" --no-pager | sudo python3 -I fpb2check.py log | tee log-broken.txt`,
  **дефект «весь дом без интернета»**, продолжить с шага 6.2.
- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Шлюз не `HEALTHY` — записать и продолжить.
- Заказчик просит остановить проверку — вернуть режим подписок (шаг 6.1), выключить
  наблюдение (шаг 8.1) и выполнить шаг 8.2.
- Режим всего дома и наблюдение не оставлять включёнными после проверки: заказчик не ответил
  на шаг 6.1 или 8.1 за 30 минут — сделать командой (как написано в шаге).

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-m2b2-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`freepool`), коммит «Отчёт: XGW 0.2.0, бесплатные серверы, веха М2б.2», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, бесплатные серверы, веха М2б.2 (весь дом через бесплатные серверы)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
fpb2check.py: <сумма, 16 знаков>. Наблюдение до проверки: <выключено / включено>.

## Итог вехи
| Допущено | В pool / живых | Последнее правило | Несущий канал | DNS по TCP | Правил по адресу (до / в режиме / после) | Xray перезапусков: включение / час / возврат | Страна: пул / телефон / компьютер |
|---|---|---|---|---|---|---|---|
| … | … / … | pool / … | есть / нет | … из D | … / 0 / … | … / … / … | … / … / … |

| Трафик за час, МБ: пул | подписка | напрямую | Норма подписки (R/24×2+30) | Плановых замеров подписки | «Придушен» | Смен сервера пула | Закрыто |
|---|---|---|---|---|---|---|---|
| … | … | … | … | … | … | … | … |

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | сумма, состояние, режим пула, службы, подписки, журнал |
| 2.2 установка | … | код |
| 2.3 после установки | … | HEALTHY, route (auto, правил по адресу N, DNS не по TCP), Xray |
| 3.1 наблюдение | … / уже было включено | ответ команды |
| 3.2 допущенные | … | число, страны, источники, протоколы |
| 4.1 включение | … | окно подтверждения, ответ панели |
| 4.2 что собрал шлюз | … | route, pool, config, Xray, xstats, status, diag, журнал |
| 4.3 панель | … / не выполнялся | метка, главная карточка, полоса и кнопка, вкладки, устройства |
| 4.4 страна | … / не выполнялся | телефон, компьютер, пул |
| 5.1 час работы | … / сокращён / не выполнялся | прирост трафика, перезапуски, замеры, смены сервера, ответ заказчика |
| 6.1 возврат | … | кто вернул, ответ панели, главная карточка |
| 6.2 после возврата | … | route как до, pool, журнал |
| 6.3 страна после | … / не выполнялся | … |
| 7.1 секреты | … | ссылки, права |
| 8.1 выключение | … | ответ, следы |
| 8.2 итог | … | Traceback, HEALTHY |
| 8.3 сайты | … / не выполнялся | ответ заказчика |

## Выводы шагов
<файлы $HOME/xgw-fpb2/*.txt; имя пользователя → <user>; ответы заказчика дословно, но без имён
серверов>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
