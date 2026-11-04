# Проверка XGW 0.2.0: бесплатные серверы, веха М1 (наблюдение)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-fp1/…`). Файл помощника создавай только командой шага 1.2, выполненной в терминале.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS (systemd 255), KDE Plasma (X11), браузер Chromium.
Клон — `~/zcod/xgw`. Код — ветка `freepool`, версия 0.2.0; в ней же всё из ветки `tspu2`
(анти-ТСПУ 2.0, первый этап). Телефон — S25 Ultra в домашней сети. Команды — в терминале
сеанса заказчика (`sudo` от его имени).

Что нового (ASSUMPTIONS п. 256, README «Бесплатные серверы»):
1. **Альтернативный режим работы — бесплатные серверы** VPN Gate, VPNBook и VPNJantit вместо
   подписки. Сайты со списками этих серверов открываются только через VPN, поэтому подписка
   остаётся несущим каналом: списки шлюз качает через серверы подписки.
2. **Сейчас — только наблюдение** (`free_pool.mode = observe`): шлюз собирает списки, проверяет
   серверы (VLESS, Trojan, Outline — временным Xray; OpenVPN — только доступность адреса) и
   показывает сводку, а **трафик идёт как прежде — через подписку**. Трафик через бесплатные
   серверы — следующая веха.
3. Карточка «Бесплатные серверы» в панели (включить/выключить, «Опросить источники», «Выданные
   ссылки» для VPNJantit), команда `sudo xgw pool`, строка «Бесплатный пул …» в `xgw status`.

Здесь, у разработчика, — юнит-тесты (разбор настоящих страниц источников, сохранённых
28.10.2026), ruff и этот помощник на подставных данных. На этой машине — всё остальное.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list`), `ip`, `iptables`, `tc`, `sysctl -w`, `systemd-run`;
  команды `tailscale`, `xray` и `openvpn`. `sudo xgw pool mode …` — только в шаге 3.1.
- Самому открывать сайты источников (vpngate, vpnbook, vpnjantit) — в браузере, `curl`, `wget`
  и как угодно ещё. Их открывает только заказчик (§6) и сам шлюз.
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/etc/systemd`, код XGW. Печатать `config.toml`, `panel.json` и файлы в
  `/var/lib/xgw/freepool` (`cat`, `less`, `grep` по ним) — в них ключи подписок, ссылки и пароли.
  Серверы, переключатели и кнопки в панели и в приложении меняет и нажимает только заказчик.
  Коммитить что-либо, кроме отчёта (§9).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP, домены и ссылки
  серверов VPN (и бесплатных тоже), логины и пароли, строки журнала. Можно: адреса устройств в
  домашней сети (`192.168.…`), коды стран, названия источников, счётчики, статусы, размеры,
  права файлов, времена.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю наблюдение за бесплатными серверами (веха М1). По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW, Xray, sing-box и DHCP перезапустятся —
интернет дома пропадёт на несколько секунд.
(2) Я включу наблюдение командой `sudo xgw pool mode observe` — трафик при этом идёт через
подписку, как сейчас; в конце вы выключите его кнопкой «Выключить» в карточке «Бесплатные
серверы» панели XGW.
(3) В панели по моей просьбе: прочитаете мне сводку из карточки «Бесплатные серверы» и нажмёте
в ней «Опросить источники».
(4) По желанию: на этом компьютере откроете сайт VPNJantit, создадите бесплатную учётку для
сервера VLESS или Trojan в Европе и вставите выданную ссылку в карточку.
(5) В конце откроете любой сайт на этом компьютере и на телефоне.
Можно согласиться не на все пункты.»

Против пункта 1 или 2 — **стоп**. Против 3 — шаги 3.3, 4.2 и 5.1 пропустить; против 4 — §6;
против 5 — шаг 8.3. Если против 2 только выключение кнопкой — шаг 8.1 пропустить. В отчёте у
пропущенного — «не выполнялся».

Шаг 1.2. Папка, помощник проверки и состояние до установки:

```bash
mkdir -p "$HOME/xgw-fp1" && chmod 700 "$HOME/xgw-fp1" && cd "$HOME/xgw-fp1" && cat > fpm1check.py <<'EOF'
"""XGW 0.2.0, бесплатный пул (веха М1, наблюдение): помощник проверки. Только читает: состояние
XGW (/run/xgw, /var/lib/xgw/freepool, рабочий конфиг Xray — счётчики, коды стран, права файлов
и да/нет, без адресов, имён, ссылок и паролей) и журнал со стандартного ввода (только
счётчики). Режимы: units, pool, checks, files, config, imported, leak, digest, subs, log."""
import json
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
UNITS = ("xgw.service", "xgw-xray.service", "xgw-singbox.service", "xgw-dhcp.service")
LIB = "/opt/xgw/lib"
DAY = 86400.0


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


def perm(path):
    return oct(path.stat().st_mode & 0o777)[2:] if path.exists() else "нет"


def records(paths):
    data = read_json(paths.var / "freepool" / "candidates.json") or {}
    found = {key: value for key, value in data.items()
             if key != "_ledger" and isinstance(value, dict)}
    return found, (data.get("_ledger") or {}).get("items") or []


if mode == "units":
    for unit in UNITS:
        print(f"{unit}: {show(unit, 'ActiveState')}")
elif mode == "pool":
    _cfg, paths = xgw()
    status = read_json(paths.status_file) or {}
    age = int(time.time() - float(status["updated"])) if status.get("updated") else None
    print(f"status.json: {'нет' if age is None else f'{age} с назад'}")
    pool = status.get("free_pool")
    if not isinstance(pool, dict):
        print("free_pool в состоянии: нет")
        sys.exit(0)
    regions = ", ".join(f"{name} {count}" for name, count in
                        sorted((pool.get("by_region") or {}).items())) or "—"
    print(f"free_pool в состоянии: режим {pool.get('mode')}, регион {pool.get('region')}; "
          f"найдено {pool.get('found')} (Xray {pool.get('supported_now')}, OpenVPN "
          f"{pool.get('openvpn')}); проверено {pool.get('checked')}, пригодно {pool.get('ready')} "
          f"({regions}); OpenVPN: адрес открыт {pool.get('reachable_openvpn')}, закрыт "
          f"{pool.get('closed')}; VPNJantit онлайн {pool.get('needs_user_action')}; трафик "
          f"проверок {pool.get('spent_mb')} из {pool.get('budget_mb')} МБ")
    now = time.time()
    for source in pool.get("sources") or []:
        when = source.get("retrieved_at")
        got = f"{int((now - float(when)) // 60)} мин назад" if when else "нет"
        print(f"  {source.get('id')}: {source.get('status')}; список — {got}; вариантов "
              f"{source.get('variants')}; серверов {source.get('endpoints')}; устарел: "
              f"{'да' if source.get('stale') else 'нет'}")
elif mode == "checks":
    _cfg, paths = xgw()
    found, ledger = records(paths)
    now = time.time()
    verdicts = {}
    countries = {}
    for record in found.values():
        key = f"{record.get('backend')} {record.get('verdict')}"
        verdicts[key] = verdicts.get(key, 0) + 1
        if record.get("verdict") in ("OK", "SLOW"):
            country = record.get("egress_country") or "?"
            countries[country] = countries.get(country, 0) + 1
    recent = sum(1 for record in found.values()
                 if now - float(record.get("checked_at") or 0) < 1800)
    spent = sum(int(item[1]) for item in ledger
                if isinstance(item, list) and now - float(item[0]) < DAY)
    print(f"проверок всего: {len(found)}; за последние 30 минут: {recent}")
    for key in sorted(verdicts):
        print(f"  {key}: {verdicts[key]}")
    print("страны выхода пригодных: "
          + (", ".join(f"{name} {count}" for name, count in sorted(countries.items())) or "—"))
    print(f"трафик проверок за сутки: {spent / 1048576:.1f} МБ")
elif mode == "files":
    _cfg, paths = xgw()
    base = paths.var / "freepool"
    snapshots = list((base / "snapshots").glob("*.json")) if (base / "snapshots").exists() else []
    print(f"каталог freepool: {perm(base)}; secrets.json: {perm(base / 'secrets.json')}; "
          f"candidates.json: {perm(base / 'candidates.json')}; снимков списков: {len(snapshots)}")
    run = paths.run / "freepool"
    left = len(list(run.iterdir())) if run.exists() else 0
    pattern = str(run / "pool-").encode()
    running = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        running += pattern in command
    print(f"временных каталогов проверок: {left}; временных Xray сейчас: {running}")
elif mode == "config":
    cfg, paths = xgw()
    from xgw.freepool.pool import FreePool

    variants = FreePool(cfg, paths).variants()
    hosts = {name.lower() for variant in variants for name in (variant.host, variant.address)
             if name}
    work = read_json(paths.xray_config_file) or {}
    total = matched = 0
    for outbound in work.get("outbounds") or []:
        settings = outbound.get("settings") or {}
        entries = [*(settings.get("vnext") or []), *(settings.get("servers") or []), settings]
        for entry in entries:
            address = entry.get("address") if isinstance(entry, dict) else None
            if isinstance(address, str) and address:
                total += 1
                matched += address.lower() in hosts
    print(f"адресов серверов в рабочем конфиге Xray: {total}; из них серверов бесплатного пула: "
          f"{matched}; вариантов в пуле: {len(variants)}")
elif mode == "imported":
    cfg, paths = xgw()
    from xgw.freepool.pool import FreePool

    imported = FreePool(cfg, paths).imported()
    found, _ledger = records(paths)
    print(f"ссылок в карточке: {len(cfg.managed.free_pool_links)}; разобрано: {len(imported)}")
    for variant in imported:
        record = found.get(variant.variant_id) or {}
        print(f"  {variant.provider} {variant.protocol}: "
              + (f"{record.get('verdict')}, выход {record.get('egress_country') or '?'}"
                 if record else "ещё не проверена"))
elif mode == "leak":
    _cfg, paths = xgw()
    secrets = read_json(paths.var / "freepool" / "secrets.json") or {}
    words = [str(value) for record in (secrets.get("shared") or {}).values()
             if isinstance(record, dict) for key, value in record.items()
             if key == "password" and value]
    lines = sys.stdin.read().splitlines()
    hits = sum(1 for line in lines if any(word in line for word in words))
    raw = sum(1 for line in lines if "vless://" in line or "ss://" in line or "trojan://" in line)
    print(f"паролей источников известно: {len(words)}; строк журнала: {len(lines)}; строк с "
          f"паролем: {hits}; строк со ссылкой сервера: {raw}")
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
elif mode == "log":
    lines = sys.stdin.read().splitlines()
    print(f"строк журнала: {len(lines)}")
    for label, words in (
        ("VPN Gate: список получен", ("бесплатный пул: vpngate — SUCCESS",)),
        ("VPNBook: список получен", ("бесплатный пул: vpnbook — SUCCESS",
                                     "бесплатный пул: vpnbook — PARTIAL")),
        ("VPNJantit: список получен", ("бесплатный пул: vpnjantit — SUCCESS",)),
        ("список получен через подписку", ("(через подписку), вариантов",)),
        ("список получен напрямую", ("(напрямую), вариантов",)),
        ("источник не ответил", ("прежний снимок остаётся",)),
        ("проверок серверов пула", ("бесплатный пул: проверка",)),
        ("шаг пула не выполнен", ("бесплатный пул: шаг не выполнен",)),
        ("правила загружены заново", ("загружены заново",)),
        ("откат на last-good", ("last-good",)),
        ("Read-only file system", ("Read-only file system",)),
        ("Permission denied", ("Permission denied",)),
        ("Traceback", ("Traceback",)),
    ):
        print(f"{label}: {sum(1 for line in lines if any(word in line for word in words))}")
else:
    print("режим: units | pool | checks | files | config | imported | leak | digest | subs | log")
EOF
python3 -c "import hashlib;d=open('fpm1check.py','rb').read().rstrip(b'\n')+b'\n';print(hashlib.sha256(d).hexdigest()[:16])"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул' | tee before.txt; for m in units files digest subs; do sudo python3 -I fpm1check.py $m; done | tee state-before.txt; sudo journalctl -u xgw --since "60 min ago" --no-pager | sudo python3 -I fpm1check.py log | tee log-before.txt
```

Ожидается:
- `153f6c4fab72ebf4`;
- `Состояние: HEALTHY …`, `Перехват: включён …`, строки `Xray …` и `sing-box …`, строки
  `Бесплатный пул` нет — записать как есть;
- четыре службы `active`; «каталог freepool: нет; …» (старый код его не создаёт); «отпечаток
  таблиц: совпадает; правила на месте (loaded): True»; «подписок с ошибкой: …; серверов в
  списке: …» — записать;
- счётчики журнала — записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать и продолжить.

## 2. Установка

Шаг 2.1. Код и проверка tspu2:

```bash
cd ~/zcod/xgw && git fetch && git checkout freepool && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q '^FREEPOOL_EVERY' src/xgw/daemon.py && grep -q 'def set_pool_mode' src/xgw/actions.py && test -f src/xgw/freepool/pool.py && grep -q 'id="pool-card"' src/xgw/ui/index.html && echo "правка в коде: есть"; git ls-tree -r --name-only origin/tspu2 docs | grep -c 'TEST-REPORT-REAL-MACHINE-0.2.0-tspu2' | sed 's/^/отчётов tspu2: /'; cd "$HOME/xgw-fp1"
```

Ожидается: «правка в коде: есть». Записать хеш. «отчётов tspu2: …» — записать.

Если не так: нет строки «правка в коде» — **стоп**, сообщить заказчику. «отчётов tspu2: 0» —
**спроси заказчика** (дословно): «Проверки tspu2 ещё не было. Её изменения входят в эту
установку. Продолжить эту проверку или сначала выполнить ТЗ tspu2
(`docs/TEST-PLAN-REAL-MACHINE-0.2.0-tspu2.md`)?» Ответ «сначала tspu2» — **стоп**. Ответ
записать.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-fp1/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-fp1/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'перезапущен|Xray запущен' "$HOME/xgw-fp1/install.txt"; cd "$HOME/xgw-fp1"
```

Ожидается: «код 0», «демон xgw запущен», «Xray запущен: участников …». Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке, пул выключен:

```bash
sleep 120; cd "$HOME/xgw-fp1" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box|^Бесплатный пул' | tee after-install.txt; for m in units digest pool; do sudo python3 -I fpm1check.py $m; done | tee -a after-install.txt; sudo xgw pool 2>&1 | head -1 | tee -a after-install.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray отвечает, строка sing-box — как до установки,
строки `Бесплатный пул` нет; четыре службы `active`; «отпечаток таблиц: совпадает; … True»;
«status.json: N с назад» (N меньше 120); «free_pool в состоянии: нет»; «Бесплатный пул:
выключен; регион EU (строго)». Записать.

Если не так: не `HEALTHY` — подождать 2 минуты и повторить; снова нет — записать, сообщить
заказчику и продолжить. Вместо строки «Бесплатный пул: выключен …» — «invalid choice» или
«ошибка» — **стоп**, установлен не тот код. Отпечаток не совпадает — повторить через минуту, снова так — **дефект «отпечаток
таблиц меняется сам»**.

## 3. Включение наблюдения

Шаг 3.1. Включить:

```bash
cd "$HOME/xgw-fp1" && date '+%F %T' | tee observe-time.txt && sudo xgw pool mode observe 2>&1 | tee mode-on.txt
```

Ожидается: «Наблюдение за бесплатным пулом включено: списки серверов собираются через
подписку, серверы проверяются, а трафик идёт как прежде — через подписку. Демон применит режим
на ближайшем шаге». Записать.

Если не так: «ошибка: …» — записать дословно, **стоп**, сообщить заказчику.

Шаг 3.2. Через 3 минуты — списки получены:

```bash
sleep 180; cd "$HOME/xgw-fp1" && sudo python3 -I fpm1check.py pool | tee pool-1.txt; sudo xgw status 2>&1 | grep -E '^Состояние|^Бесплатный пул' | tee -a pool-1.txt; sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm1check.py log | tee log-1.txt
```

Ожидается:
- «status.json: N с назад» (N меньше 120);
- «free_pool в состоянии: режим observe, регион EU; найдено …»;
- строки источников: `vpngate: SUCCESS; …; вариантов` 30 или больше; `vpnbook: SUCCESS` (или
  `PARTIAL`); `вариантов` 10 или больше; `vpnjantit: SUCCESS; …; вариантов 0; серверов` 30 или
  больше;
- `Состояние: HEALTHY …`; строка `Бесплатный пул (наблюдение, регион EU): найдено …`;
- в журнале: «VPN Gate: список получен: 1» (или больше), «VPNBook: …: 1», «VPNJantit: …: 1»;
  «список получен через подписку: 3» (или больше); «список получен напрямую: 0»; «шаг пула не
  выполнен: 0»; «Traceback: 0».

Записать всё как есть.

Если не так:
- «free_pool в состоянии: нет» — подождать 2 минуты и повторить шаг; снова нет — **дефект
  «наблюдение не включилось»**, записать `sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | grep -c 'настройки перечитаны' | sed 's/^/перечитываний настроек: /' | tee reload.txt`;
- источник `UNAVAILABLE` или `RATE_LIMITED` — записать (наблюдение: источник не ответил через
  подписку), продолжить; все три `UNAVAILABLE` — записать
  `sudo python3 -I fpm1check.py subs | tee subs-1.txt` и продолжить;
- источник `SCHEMA_CHANGED` — **дефект «формат страницы источника изменился»** (какой
  источник), продолжить;
- «список получен напрямую» больше 0 при `HEALTHY` — **дефект «списки не через подписку»**;
- «шаг пула не выполнен» или «Traceback» больше 0 — записать
  `sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -20 | tee traceback-1.txt`
  (только строки с файлами и ошибкой) — **дефект «шаг пула падает»**.

Шаг 3.3 (при согласии на пункт 3). **Попроси заказчика** (дословно):

«Откройте панель XGW, найдите карточку «Бесплатные серверы». Прочитайте мне первую фразу под
заголовком до слов «Трафик проверок» и метки у VPN Gate, VPNBook и VPNJantit (например «ок»).
На кнопке справа от заголовка написано «Выключить»?»

Ожидается: фраза «Наблюдение (регион EU): найдено N, сейчас поддерживается … OpenVPN — … Проверено
…», N — как «найдено» в `pool-1.txt` (может отличаться на несколько); метки — как статусы в
`pool-1.txt` («ок» — SUCCESS, «частично» — PARTIAL, «недоступен» — UNAVAILABLE); на кнопке —
«Выключить». Записать ответ.

Если не так: карточки нет или в ней «Альтернативный режим: …» (наблюдение выключено) — **дефект
«карточка не видит наблюдение»**.

## 4. Проверки серверов

Шаг 4.1. Не раньше чем через 15 минут после шага 3.1:

```bash
cd "$HOME/xgw-fp1" && for m in checks pool files config; do sudo python3 -I fpm1check.py $m; done | tee checks-1.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:' | tee -a checks-1.txt
```

Ожидается:
- «проверок всего: C; за последние 30 минут: …», C — 10 или больше; строки вида
  `xray OK: …`, `openvpn REACHABLE: …`, `openvpn CLOSED: …` — записать все;
- «страны выхода пригодных: …» — записать (коды стран);
- «пригодно R (…)» — в скобках только `EU …` или «—» (регион строгий);
- «трафик проверок X из 512 МБ», X не больше 50;
- «каталог freepool: 700; secrets.json: 600; candidates.json: 600; снимков списков: 3» (3 или
  больше);
- «временных каталогов проверок: 0» (или 1); «временных Xray сейчас: 0» (или 1);
- **«из них серверов бесплатного пула: 0»** — трафик через пул не идёт;
- `HEALTHY`, перехват включён.

Если не так:
- C меньше 10 — подождать 10 минут и повторить; снова меньше 10 — **дефект «проверки не
  идут»**, записать `sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm1check.py log | tee log-checks.txt`;
- в скобках у «пригодно» есть не `EU` — **дефект «регион не строгий»**;
- X больше 50 — **дефект «проверки тратят много трафика»**;
- права другие (не 700/600) — **дефект «права файлов пула»**;
- временных каталогов 2 и больше или временных Xray 2 и больше — повторить через минуту; снова
  так — **дефект «временный Xray не убирается»**;
- «из них серверов бесплатного пула» больше 0 — **дефект «сервер пула попал в рабочий конфиг»**,
  **стоп**, сообщить заказчику.

Шаг 4.2 (при согласии на пункт 3). **Попроси заказчика** (дословно):

«В карточке «Бесплатные серверы» нажмите «Опросить источники». Что ответила панель?»

Через 2 минуты после ответа:

```bash
sleep 120; cd "$HOME/xgw-fp1" && sudo python3 -I fpm1check.py pool | tee pool-2.txt; sudo journalctl -u xgw --since "$(cat observe-time.txt)" --no-pager | sudo python3 -I fpm1check.py log | tee log-2.txt
```

Ожидается: ответ панели — «Опрашиваю источники бесплатных серверов через подписку…»; у каждого
источника «список — 0 мин назад» или «1 мин назад» (у ответивших); в журнале «VPN Gate: список
получен», «VPNBook: …», «VPNJantit: …» — каждое на 1 больше, чем в `log-1.txt` (у ответивших
источников); «Traceback: 0». Записать.

Если не так: время списков не обновилось и счётчики те же — **дефект «Опросить источники» не
работает»**.

## 5. Сводка в команде

Шаг 5.1 (при согласии на пункт 3). Сводка команды и панели — одна:

```bash
cd "$HOME/xgw-fp1" && sudo xgw pool 2>&1 | head -4 | tee cli.txt; sudo xgw pool status --json | python3 -c "import json,sys;d=json.load(sys.stdin);print('json:', d['mode'], d['found'], d['checked'], d['ready'])" | tee -a cli.txt
```

Затем **попроси заказчика** (дословно): «Прочитайте ещё раз из карточки «Бесплатные серверы»
числа после слов «найдено» и «Проверено».»

Ожидается: строки «Бесплатный пул: наблюдение (трафик через подписку); регион EU (строго)»,
«Найдено …», «Проверено …», «Трафик проверок за сутки: …»; «json: observe N C R»; числа
заказчика — как N и C (могут отличаться на несколько: проверки идут). Записать.

Если не так: команда отвечает ошибкой — **дефект «xgw pool»**; числа заказчика отличаются
больше чем на 10 — **дефект «сводка панели и команды расходится»**.

## 6. Ссылка VPNJantit (при согласии на пункт 4)

Шаг 6.1. **Попроси заказчика** (дословно):

«Откройте на этом компьютере в браузере сайт vpnjantit.com (как обычно, через VPN). Выберите
бесплатный сервер VLESS или Trojan в Европе (например, Германия или Нидерланды), создайте на нём
учётку по их форме и скопируйте выданную ссылку (начинается с vless:// или trojan://). В панели
XGW в карточке «Бесплатные серверы» раскройте «Выданные ссылки (VPNJantit и другие)», вставьте
ссылку в поле и нажмите «Добавить». Что ответила панель? Появилась ли ссылка ниже с кнопкой
«Убрать»?»

Ожидается: «Добавлено ссылок: 1 — проверю их в ближайшие минуты»; ссылка видна (имя и тип,
без длинного ключа). Записать ответ.

Если не так: «ссылок … не найдено» — попросить проверить, что ссылка скопирована целиком, и
повторить один раз; снова так — записать (наблюдение: вид ссылки VPNJantit) и перейти к §7.

Шаг 6.2. Через 5 минут после ответа:

```bash
sleep 300; cd "$HOME/xgw-fp1" && sudo python3 -I fpm1check.py imported | tee imported.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm1check.py leak | tee -a imported.txt
```

Ожидается: «ссылок в карточке: 1; разобрано: 1»; строка `vpnjantit vless: …` (или `trojan`;
вместо `vpnjantit` может быть `import`, если в ссылке не имя сервера VPNJantit, а IP) с итогом
проверки — любым (`OK`, `SLOW`, `CONNECT_FAIL`, `TIMEOUT` …; `CONNECT_FAIL` и `TIMEOUT`
значат, что напрямую из дома сервер не открывается), записать итог и страну выхода; «строк с
паролем: 0; строк со ссылкой сервера: 0».

Если не так: «ещё не проверена» — подождать 5 минут и повторить; снова так — **дефект
«выданная ссылка не проверяется»**. «разобрано: 0» — **дефект «ссылка VPNJantit не
разбирается»**. Строк с паролем или ссылкой больше 0 — **дефект «секрет в журнале»**.

## 7. Секреты

Шаг 7.1.

```bash
cd "$HOME/xgw-fp1" && sudo python3 -I fpm1check.py files | tee secrets.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm1check.py leak | tee -a secrets.txt; stat -c 'status.json: %a' /run/xgw/status.json | tee -a secrets.txt
```

Ожидается: права 700/600/600; «паролей источников известно: 1» (общая учётка VPNBook; 0 —
если VPNBook не ответил); «строк с паролем: 0; строк со ссылкой сервера: 0»; «status.json: 644»
(в нём только счётчики пула). Записать.

Если не так: строк с паролем или ссылкой больше 0 — **дефект «секрет в журнале»**.

## 8. Выключение и итог

Шаг 8.1 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«В карточке «Бесплатные серверы» нажмите «Выключить». Что ответила панель и что теперь
написано на кнопке?»

Сразу после ответа:

```bash
cd "$HOME/xgw-fp1" && sleep 60; date '+%F %T' | tee off-time.txt; sleep 60; sudo python3 -I fpm1check.py pool | tee off.txt; sudo xgw pool 2>&1 | head -1 | tee -a off.txt; sudo xgw status 2>&1 | grep -c '^Бесплатный пул' | sed 's/^/строк «Бесплатный пул» в xgw status: /' | tee -a off.txt; sudo python3 -I fpm1check.py files | tee -a off.txt
```

Ожидается: ответ панели — «Бесплатный пул выключен», на кнопке — «Включить наблюдение»;
«free_pool в состоянии: нет»; «Бесплатный пул: выключен; …»; «строк «Бесплатный пул» в xgw
status: 0»; «снимков списков» — как в шаге 4.1 или больше (списки сохраняются). Записать.

Если не так: «free_pool в состоянии: режим …» — подождать 2 минуты и повторить; снова так —
**дефект «наблюдение не выключается»**.

Шаг 8.2. Через 3 минуты после шага 8.1 — итог:

```bash
sleep 180; cd "$HOME/xgw-fp1" && sudo journalctl -u xgw --since "$(cat off-time.txt)" --no-pager | sudo python3 -I fpm1check.py log | tee log-off.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I fpm1check.py log | tee final.txt; for m in digest subs config; do sudo python3 -I fpm1check.py $m; done | tee -a final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee -a final.txt
```

Ожидается:
- в `log-off.txt` (с минуты после нажатия «Выключить»): «VPN Gate: список получен: 0»,
  «VPNBook: …: 0», «VPNJantit: …: 0», «проверок серверов пула: 0» (опросов и проверок нет);
- в `final.txt`: **«Traceback: 0»**, «шаг пула не выполнен: 0», «правила загружены заново: 0»
  или 1, «откат на last-good: 0», «Read-only file system» и «Permission denied» — не больше, чем
  в `log-before.txt`;
- «отпечаток таблиц: совпадает; … True»; «подписок с ошибкой» — не больше, чем до установки;
  «серверов в списке» — как до установки (±2); «из них серверов бесплатного пула: 0»;
- `HEALTHY`, перехват включён, Xray отвечает, sing-box — как до установки.

Если не так: опросы или проверки после выключения больше 0 — **дефект «пул работает
выключенным»**; Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | grep -E 'File "|Error' | head -30 | tee traceback.txt`
(только строки с файлами и ошибкой, адреса — убрать); «правила загружены заново» больше 1 —
**дефект «правила загружаются по кругу»**. Сообщить заказчику.

Шаг 8.3 (при согласии на пункт 5). **Попроси заказчика** (дословно):

«Откройте любой сайт на этом компьютере и любой сайт на телефоне. Открываются?»

Ожидается: «да». Нет — записать ответ дословно и
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt`,
сообщить заказчику.

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-freepool-m1-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`freepool`), коммит «Отчёт: XGW 0.2.0, бесплатные серверы, веха М1», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, бесплатные серверы, веха М1 (наблюдение)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
fpm1check.py: <сумма, 16 знаков>. Отчётов tspu2: <…>, ответ заказчика: <…>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, службы, каталог пула, отпечаток, подписки, журнал |
| 2.2 установка | … | код, строки установки |
| 2.3 после установки | … | HEALTHY, службы, отпечаток, пул выключен |
| 3.1 включение | … | ответ команды |
| 3.2 списки | … | статусы и числа источников, через подписку / напрямую, Traceback |
| 3.3 карточка | … / не выполнялся | фраза, метки, кнопка |
| 4.1 проверки | … | проверок, итоги, страны, регион, трафик, права, временные Xray, пул в конфиге |
| 4.2 «Опросить источники» | … / не выполнялся | ответ панели, счётчики до → после |
| 5.1 xgw pool | … / не выполнялся | строки, json, числа заказчика |
| 6.1–6.2 VPNJantit | … / не выполнялся | ответ панели, итог проверки, страна, секреты в журнале |
| 7.1 секреты | … | права, пароли и ссылки в журнале, status.json |
| 8.1 выключение | … / не выполнялся | ответ панели, кнопка, состояние, снимки |
| 8.2 итог | … | после выключения, Traceback, отпечаток, подписки, HEALTHY |
| 8.3 сайты | … / не выполнялся | ответ заказчика |

## Выводы шагов
<файлы $HOME/xgw-fp1/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
