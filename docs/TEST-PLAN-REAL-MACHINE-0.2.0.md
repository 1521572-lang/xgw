# Проверка XGW 0.2.0: рекомендации к аудиту 0.1.18

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы сохраняй в файлы, как написано (`$HOME/xgw-020/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, KDE Plasma (X11), браузер Chromium. Клон —
`~/zcod/xgw`. Код — ветка `release-0.2.0`, версия 0.2.0 (до неё — ветка `direct-f6`, версия
0.1.18; её программа f6b пройдена, отчёт `docs/TEST-REPORT-REAL-MACHINE-0.1.18-f6b-2026-10-26.md`).
Проверяемый телефон — S25 Ultra, адрес в домашней сети 192.168.60.135.

Что нового (ASSUMPTIONS п. 248):
1. **Выбор серверов — по рейтингу** (issue #2): классов «приоритет × стоимость» больше нет.
   У каждого сервера рейтинг (скорость, задержка, стабильность, стоимость, приоритет), в работе
   — лучшие по нему из всех подписок; мёртвого меняет лучший годный запасной любого уровня.
2. **Свой сервер устройства — без перезапуска Xray.** Правило устройства — прямо на его сервер;
   если сервер не отвечает, устройство само идёт через основной, а потом возвращается.
3. **Сетевая задержка (RTT)** в панели — отдельно от времени пробы целиком.
4. **DNS:** домены подписок — только через шифрованные резолверы (DNS-over-TLS Яндекса и Quad9,
   DoH Cloudflare, Google, AdGuard, DNS.SB), удачный адрес подписки шлюз помнит неделю;
   российские домены Xray спрашивает у Яндекса по DoH, а не обычным UDP.
5. **Проверка правил nftables** — коротким выводом (`nft -t`): меньше процессора.
6. Мягкий `rp_filter` у TUN и мостов Docker; теневая проба профиля обхода отдельным Xray; запись
   трафика — до 5 минут и 50 МБ; скан запасных — в пределах суточного лимита проверок.

Здесь, у разработчика, проверены юнит-тесты и живые Xray 26.10.21, sing-box 1.14.3, nftables
1.1.6 в WSL; шлюз заказчика, телефон, панель и полчаса работы проверяет эта программа.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list` и `nft -t list`), `ip`, `iptables`, `tc`, `sysctl -w`.
- Править `/etc/xgw` (в том числе `panel.json`), `/opt/xgw`, `/var/lib/xgw`, `/etc/systemd`,
  код XGW. Серверы и переключатели в панели меняет только заказчик. Коммитить что-либо, кроме
  отчёта (§12).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP и домены серверов
  VPN. Можно: адреса устройств в домашней сети (`192.168.…`), отпечатки серверов (8 знаков),
  названия и страны серверов, IP публичных резолверов (77.88.8.8, 1.1.1.1 и т. п.), рейтинги,
  задержки, скорости, счётчики.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю новую версию XGW 0.2.0. По пунктам:
(1) Переустановка XGW с новым кодом: Xray перезапустится — интернет дома пропадёт на несколько
секунд (если у телефона выбран свой сервер — один раз ещё на пару секунд).
(2) Свой сервер для телефона S25 Ultra: выберете в панели сервер, посмотрите страну на телефоне;
потом — сервер, который сейчас не отвечает (если такой есть), и посмотрите, что интернет на
телефоне есть; в конце вернёте как было.
(3) Панель: посмотрите строки серверов (рейтинг, задержка) и щёлкнете значок XGW в трее.
(4) Запись трафика телефона на 20 секунд из панели.
(5) Полчаса обычной работы: я только смотрю журнал, вы пользуетесь интернетом как обычно.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — §5 пропустить, против 3 — §7.2 и §10, против 4 — §9,
против 5 — §8; в отчёте у пропущенного — «не выполнялся».

Шаг 1.2. Папка и помощник проверки (только читает):

```bash
mkdir -p "$HOME/xgw-020" && chmod 700 "$HOME/xgw-020" && cd "$HOME/xgw-020" && cat > v020check.py <<'EOF'
"""XGW 0.2.0: помощник проверки. Только читает: config.toml (без подписок), конфиг Xray,
status.json демона, кэш адресов подписок (без имён), таблицу nftables ip xgw, /proc.
Режимы: cpu, dns, nft, device, rtt, rating, budget, record."""
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, "/opt/xgw/lib")
from xgw.paths import Paths  # noqa: E402

paths = Paths.from_env()
mode = sys.argv[1] if len(sys.argv) > 1 else ""


def status():
    return json.loads(paths.status_file.read_text(encoding="utf-8"))


def xray():
    return json.loads(paths.xray_config_file.read_text(encoding="utf-8"))


if mode == "cpu":
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    pid = subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", "xgw.service"],
                         capture_output=True, text=True).stdout.strip()

    def ticks():
        fields = open(f"/proc/{pid}/stat", encoding="ascii").read().rsplit(")", 1)[1].split()
        return int(fields[11]) + int(fields[12])

    first = ticks()
    time.sleep(seconds)
    used = (ticks() - first) / os.sysconf("SC_CLK_TCK")
    print(f"процессор демона xgw: {used:.1f} с за {seconds} с ({100 * used / seconds:.1f} %)")
    sys.exit(0)

from xgw import config, fetch  # noqa: E402

cfg, _warnings = config.load(paths.config_file)

if mode == "dns":
    print("резолверы bootstrap:", cfg.dns.resolvers)
    print("для подписок (шифрованные):", fetch.encrypted(cfg.dns.resolvers))
    print("direct_servers:", cfg.dns.direct_servers)
    servers = xray()["dns"]["servers"]
    first = servers[0] if servers and isinstance(servers[0], dict) else {}
    print(f"DNS Xray для российских доменов: {first.get('address')} "
          f"(доменов в правиле: {len(first.get('domains') or [])})")
    direct = [rule for rule in xray()["routing"]["rules"]
              if rule.get("outboundTag") == "direct" and "77.88.8.8" in (rule.get("ip") or [])]
    print(f"правило «77.88.8.8 — напрямую»: {'есть' if direct else 'нет'}")
    for entry in cfg.dns.resolvers:
        started = time.monotonic()
        try:
            ips = fetch.resolve_domain("ya.ru", [entry], mark=cfg.capture.mark_bypass)
            print(f"  {entry}: OK, адресов {len(ips)}, {1000 * (time.monotonic() - started):.0f} мс")
        except Exception as exc:  # noqa: BLE001 — печатаем причину
            print(f"  {entry}: НЕ ОТВЕЧАЕТ ({type(exc).__name__})")
    cache = paths.cache_dir / "dns-cache.json"
    try:
        hosts = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hosts = None
    if hosts is None:
        print("кэш адресов подписок: файла нет")
    else:
        addresses = [ip for entry in hosts.values() for ip in entry.get("ips", [])]
        newest = max((entry.get("ts", 0) for entry in hosts.values()), default=0)
        mode_bits = oct(cache.stat().st_mode & 0o777)
        print(f"кэш адресов подписок: имён {len(hosts)}, адресов {len(addresses)}, служебных "
              f"{sum(fetch.is_bogon(ip) for ip in addresses)}, права {mode_bits}, последняя "
              f"запись {int((time.time() - newest) // 60)} мин назад")
elif mode == "nft":
    from xgw.net.capture import capture_for

    for argv in (["nft", "list", "table", "ip", "xgw"], ["nft", "-t", "list", "table", "ip", "xgw"]):
        started = time.monotonic()
        text = subprocess.run(argv, capture_output=True, text=True).stdout
        print(f"{' '.join(argv)}: {len(text) // 1024} КБ, {1000 * (time.monotonic() - started):.0f} мс")
    started = time.monotonic()
    loaded = capture_for(cfg, paths).loaded()
    print(f"проверка правил демоном (loaded): {loaded}, {1000 * (time.monotonic() - started):.0f} мс")
    tun = cfg.capture.tun_name
    for where in ("all", "default", tun):
        try:
            value = open(f"/proc/sys/net/ipv4/conf/{where}/rp_filter", encoding="ascii").read().strip()
        except OSError:
            value = "нет интерфейса"
        print(f"rp_filter {where}: {value}")
    mark = open("/proc/sys/net/ipv4/conf/all/src_valid_mark", encoding="ascii").read().strip()
    print(f"src_valid_mark all: {mark}")
    try:
        conf = paths.sysctl_file.read_text(encoding="utf-8")
    except OSError:
        conf = ""
    print("90-xgw.conf rp_filter:", [line for line in conf.splitlines() if "rp_filter" in line])
    full = subprocess.run(["nft", "-t", "list", "table", "ip", "xgw"], capture_output=True,
                          text=True).stdout
    needle = 'oifname "' + tun + '" tcp flags syn'
    print(f"MSS для контейнеров в {tun}: {sum(needle in line for line in full.splitlines())}")
elif mode == "device":
    config_xray = xray()
    print(f"устройств со своим сервером: {len(cfg.managed.routes)}")
    tags = {}
    for rule in config_xray["routing"]["rules"]:
        if rule.get("source") and rule.get("outboundTag"):
            tags[rule["source"][0]] = rule["outboundTag"]
    for ip, server in sorted(cfg.managed.routes.items()):
        print(f"  {ip} -> сервер {server}; правило в Xray: {tags.get(ip, 'нет (через основной)')}")
    balancers = [item["tag"] for item in config_xray["routing"]["balancers"]]
    print(f"балансировщики: {balancers}")
    loopback = any(item.get("protocol") == "loopback" for item in config_xray["outbounds"])
    print(f"выход to-main (loopback): {'есть' if loopback else 'нет'}")
    print(f"burstObservatory.subjectSelector: "
          f"{config_xray['burstObservatory']['subjectSelector']}")
    try:
        down = json.loads(paths.devices_down_file.read_text(encoding="utf-8")).get("ips")
    except (OSError, ValueError):
        down = []
    print(f"свой сервер молчит (идут через основной): {down}")
    started = subprocess.run(
        ["systemctl", "show", "-p", "ActiveEnterTimestamp", "--value", "xgw-xray.service"],
        capture_output=True, text=True).stdout.strip()
    print(f"Xray запущен: {started}")
elif mode == "rtt":
    data = status()
    rows = [*(data.get("members") or []), *(data.get("spares") or [])]
    with_rtt = [row for row in rows if row.get("rtt_ms") is not None]
    print(f"серверов: {len(rows)}, с RTT: {len(with_rtt)} (участников "
          f"{sum(1 for row in data.get('members') or [] if row.get('rtt_ms') is not None)})")
    pairs = [(row["rtt_ms"], row["delay_ms"]) for row in with_rtt if row.get("delay_ms")]
    if pairs:
        print(f"медиана RTT {statistics.median(p[0] for p in pairs):.0f} мс, медиана времени "
              f"пробы {statistics.median(p[1] for p in pairs):.0f} мс, RTT меньше пробы у "
              f"{sum(1 for rtt, delay in pairs if rtt < delay)} из {len(pairs)}")
    for row in with_rtt[:8]:
        print(f"  {row['fingerprint'][:8]}: RTT {row['rtt_ms']} мс, проба {row.get('delay_ms')} мс")
elif mode == "rating":
    data = status()
    print(f"состояние: {data.get('state')}; {data.get('action')}")
    members = data.get("members") or []
    spares = data.get("spares") or []
    for row in members:
        print(f"  в работе {row['fingerprint'][:8]}: рейтинг {row.get('score')}, "
              f"{row.get('priority')}, x{row.get('multiplier')} {'лимит' if row.get('limited') else 'безлимит'}, "
              f"{row.get('speed_mbps')} Мбит/с, RTT {row.get('rtt_ms')}, жив {row.get('alive')}"
              f"{', основной' if row.get('main') else ''}")
    good = [row for row in spares if row.get("verdict") == "OK" and row.get("score")]
    good.sort(key=lambda row: -row["score"])
    for row in good[:5]:
        print(f"  запасной {row['fingerprint'][:8]}: рейтинг {row['score']}, {row.get('priority')}, "
              f"x{row.get('multiplier')}, {row.get('speed_mbps')} Мбит/с")
    alive = [row for row in members if row.get("alive") and row.get("score") and not row.get("main")]
    if good and alive:
        weakest = min(row["score"] for row in alive)
        print(f"лучший годный запасной {good[0]['score']} / слабейший живой участник (не основной) "
              f"{weakest}: выше на {100 * (good[0]['score'] / weakest - 1):.0f} %")
    print(f"без рейтинга: участников {sum(1 for r in members if r.get('score') is None)}, "
          f"запасных {sum(1 for r in spares if r.get('score') is None)}")
    print(f"«заменить некем»: {'да' if data.get('stranded') else 'нет'}")
elif mode == "budget":
    budget = status().get("budget") or {}
    keys = ("probes_mb", "scans_mb", "checks_mb", "total_mb", "limit_mb", "scan_minutes",
            "members", "spares", "cheap", "over")
    print({key: budget.get(key) for key in keys})
    print("предупреждения:", budget.get("warnings"))
elif mode == "record":
    directory = paths.records_dir
    files = sorted(directory.glob("*.pcap")) if directory.is_dir() else []
    print(f"записей: {len(files)}")
    for path in files[-3:]:
        try:
            meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        print(f"  {path.stat().st_size / 1e6:.1f} МБ, пакетов {meta.get('packets')}, "
              f"секунд {meta.get('seconds')}, итог: {meta.get('why')}")
else:
    print("режим: cpu | dns | nft | device | rtt | rating | budget | record")
EOF
sha256sum v020check.py | cut -c1-16; sudo xgw status | grep -E '^Состояние|Перехват:' | tee before.txt
```

Ожидается: `b1b05c5acd4294cc`; `Состояние: HEALTHY …`, `Перехват: включён …`. Записать как есть.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать (это до установки) и продолжить.

Шаг 1.3. Процессор демона **до** установки (старый код, 2 минуты):

```bash
cd "$HOME/xgw-020" && sudo python3 -I v020check.py cpu 120 | tee cpu-before.txt
```

Ожидается: строка «процессор демона xgw: X с за 120 с (Y %)». Записать Y.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout release-0.2.0 && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def dot_query' src/xgw/fetch.py && grep -q '_rebalance' src/xgw/daemon.py && test -f src/xgw/rating.py && test -f src/xgw/watch/shadow.py && echo "0.2.0 в коде: есть"; cd "$HOME/xgw-020"
```

Ожидается: «0.2.0 в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-020/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-020/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-020"
```

Ожидается: «код 0», «демон xgw запущен». Код не 0 — **стоп**, сохранить вывод, сообщить
заказчику (сеть не тронута).

Шаг 2.3. Через 2 минуты — шлюз в порядке, конфиг Xray нового вида:

```bash
sleep 120; cd "$HOME/xgw-020" && sudo xgw status | grep -E '^Состояние|Перехват:|^Xray' | tee after-install.txt; sudo python3 -I v020check.py device | tee -a after-install.txt
```

Ожидается: `HEALTHY`, перехват включён; «балансировщики: ['auto']» (балансировщиков `dev-…` нет);
«выход to-main (loopback): нет»; «burstObservatory.subjectSelector: ['proxy-']»; у каждого
устройства со своим сервером — «правило в Xray: proxy-… или spare-…» (если сервер жив) либо
«нет (через основной)». Записать.

Если не так: не `HEALTHY` — подождать 2 минуты, повторить; снова нет — записать `sudo xgw
status` целиком (без адресов серверов) и продолжить. Есть `dev-…` или to-main «есть» — **дефект
«старая схема своего сервера»**: записать и продолжить. Помощник упал с ошибкой Python —
**дефект «помощник»**: записать вывод целиком, дальше без шагов с этим режимом.

## 3. DNS

Шаг 3.1. Резолверы и DNS Xray:

```bash
cd "$HOME/xgw-020" && sudo python3 -I v020check.py dns | tee dns.txt
```

Ожидается:
- «резолверы bootstrap» — среди них `tls://77.88.8.8` и `tls://9.9.9.11`; `udp://77.88.8.8`
  нет (если есть — значит, в config.toml свой список: записать, это не дефект);
- «для подписок (шифрованные)» — без `udp://`;
- «direct_servers: ['https://77.88.8.8/dns-query']» (или свой список из config.toml — записать);
- «DNS Xray для российских доменов: https://77.88.8.8/dns-query (доменов в правиле: 3)»;
  «правило «77.88.8.8 — напрямую»: есть»;
- по каждому резолверу — «OK, адресов N, M мс» или «НЕ ОТВЕЧАЕТ». Записать, какие не отвечают;
- «кэш адресов подписок: имён K, адресов A, служебных 0, права 0o600, последняя запись …»
  (K — сколько разных доменов у подписок, обычно 1–3; запись — со времени установки).

Если не так: не отвечает ни один `tls://` — **дефект «DoT не работает на шлюзе»**: записать
вывод и продолжить. «служебных» больше 0 — **дефект «в кэш попал подменённый адрес»**. «файла
нет» — подождать 5 минут (демон опрашивает подписки после запуска), повторить; снова нет —
**дефект «кэш адресов подписок не пишется»**: записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -iE 'подписк' | tail -10 | tee dns-log.txt`
(адреса подписок в выводе замаскированы — всё равно проверить и убрать, если видны).

Шаг 3.2. Российский домен — через DoH Яндекса:

```bash
cd "$HOME/xgw-020" && getent ahostsv4 ya.ru | head -1; getent ahostsv4 gosuslugi.ru | head -1; sleep 2; sudo ss -tnp state established '( dport = :443 )' | grep -c '77.88.8.8:443' | sed 's/^/соединений Xray к 77.88.8.8:443: /' | tee doh.txt
```

Ожидается: у ya.ru и gosuslugi.ru — адреса (строки с IP; их в отчёт не писать — только
«разрешились»); «соединений Xray к 77.88.8.8:443: 1» или больше.

Если не так: имена не разрешились — **стоп по DNS**: записать и сообщить заказчику (сайты могут
не открываться). Соединений 0 — повторить шаг через минуту; снова 0 — **дефект «DoH Яндекса не
используется»**: записать и продолжить.

## 4. Правила nftables и rp_filter

Шаг 4.1.

```bash
cd "$HOME/xgw-020" && sudo python3 -I v020check.py nft | tee nft.txt
```

Ожидается:
- `nft list table ip xgw` — сотни КБ, `nft -t list table ip xgw` — единицы КБ и в разы быстрее
  (записать оба размера и времени);
- «проверка правил демоном (loaded): True», время — десятки мс, а не сотни;
- «rp_filter all: 2», «rp_filter default: 2»; у `xgwtun0` — 2 или «нет интерфейса» (если Docker
  и TUN не используются);
- «90-xgw.conf rp_filter:» — две строки `net.ipv4.conf.all.rp_filter = 2` и
  `net.ipv4.conf.default.rp_filter = 2`;
- `src_valid_mark all` — записать как есть (XGW его не меняет; Tailscale ставит 1);
- «MSS для контейнеров в xgwtun0: 1», если перехват контейнеров включён; иначе 0.

Если не так: `loaded: False` — повторить через минуту; снова False — **дефект «проверка правил»**:
записать и продолжить. rp_filter не 2 или строк в 90-xgw.conf нет — **дефект «rp_filter»**.

Шаг 4.2. Процессор демона **после** установки (2 минуты) и правила не перезагружаются:

```bash
cd "$HOME/xgw-020" && sudo python3 -I v020check.py cpu 120 | tee cpu-after.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c 'загружены заново' | sed 's/^/перезагрузок правил: /' | tee -a cpu-after.txt
```

Ожидается: Y после установки меньше, чем в шаге 1.3 (записать оба); «перезагрузок правил: 0»
(одна допустима — сразу после установки).

Если не так: Y больше, чем до установки, — записать как наблюдение (на нагрузку влияют и
замеры скорости). Перезагрузок 2 и больше — **дефект «правила перезагружаются по кругу»**:
записать `sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -B2 'загружены заново' | tail -20 | tee nft-log.txt`.

## 5. Свой сервер устройства без перезапуска (при согласии на пункт 2)

Шаг 5.1. Сначала:

```bash
cd "$HOME/xgw-020" && date '+%F %T' | tee route-time.txt && sudo python3 -I v020check.py device | tee route-before.txt
```

Записать «Xray запущен: …».

Затем **попроси заказчика** (дословно):

«Откройте панель XGW, карточку „Устройства". В строке телефона S25 Ultra (192.168.60.135) —
список „Сервер: …". Выберите в нём сервер **в работе или запасной без пометки „недоступен"** и
другой страны, чем сейчас у телефона. Какую страну выбрали и что написала панель? Потом на
телефоне откройте myip.com — какая страна?»

Затем:

```bash
sleep 30; cd "$HOME/xgw-020" && sudo python3 -I v020check.py device | tee route.txt; sudo journalctl -u xgw --since "$(cat route-time.txt)" --no-pager | grep 'свой сервер устройства' | tail -3 | tee -a route.txt
```

Ожидается: у 192.168.60.135 — «правило в Xray: proxy-… или spare-…»; «Xray запущен:» — **то же
время, что в 5.1** (перезапуска не было); в журнале — «свой сервер устройства: применено через
API без перезапуска»; страна на телефоне — выбранная.

Если не так: время запуска Xray другое (позже 5.1) — **дефект «перезапуск Xray при выборе
сервера»**: записать `route.txt` и продолжить. Страна прежняя — **дефект «устройство идёт через
основной»**: записать. Панель написала ошибку — записать текст, перейти к §6.

Шаг 5.2. Сервер, который не отвечает. **Попроси заказчика** (дословно):

«В карточке „Серверы" есть запасные с пометкой „недоступен" или „тайм-аут" справа? Если есть —
выберите такой сервер телефону в том же списке „Сервер: …" и через две минуты откройте на
телефоне myip.com: открывается? Какая страна? Что написано в строке телефона справа? Если таких
серверов нет — скажите „нет"».

Ответ «нет» — шаг пропустить, перейти к 5.3. Иначе через 2 минуты:

```bash
sleep 120; cd "$HOME/xgw-020" && sudo python3 -I v020check.py device | tee route-dead.txt; sudo journalctl -u xgw --since "$(cat route-time.txt)" --no-pager | grep -E 'свой сервер устройства' | tail -4 | tee -a route-dead.txt
```

Ожидается: «свой сервер молчит (идут через основной): ['192.168.60.135']»; у телефона «правило
в Xray: нет (через основной)»; в журнале — «… не отвечает: устройство идёт через основной, пока
он не ответит»; «Xray запущен:» — то же время; у заказчика интернет на телефоне есть, страна —
основного сервера, в строке телефона — «свой сервер молчит · через основной».

Если не так: телефона нет в списке «молчит», а сервер в панели «недоступен» — подождать ещё
минуту, повторить; снова нет — **дефект «мёртвый свой сервер не обходится»**: записать. Нет
интернета на телефоне — сразу попросить заказчика выбрать «Сервер: авто», записать **дефект
«нет интернета при мёртвом своём сервере»**.

Шаг 5.3. **Попроси заказчика** (дословно):

«Верните телефону сервер, который был до проверки (вчера оставили „польша 2"), или „Сервер:
авто" — как хотите. Что выбрали?»

Через 30 секунд:

```bash
sleep 30; cd "$HOME/xgw-020" && sudo python3 -I v020check.py device | tee route-end.txt
```

Ожидается: у телефона — правило на выбранный сервер (или устройств со своим сервером на одно
меньше при «авто»); «Xray запущен:» — то же время, что в 5.1. Записать ответ заказчика.

## 6. Сетевая задержка (RTT)

Шаг 6.1. Через 10 минут после установки (по `install-time.txt`):

```bash
cd "$HOME/xgw-020" && sudo python3 -I v020check.py rtt | tee rtt.txt
```

Ожидается: «серверов: N, с RTT: M (участников K)», K — все участники или почти все; строка
«медиана RTT … мс, медиана времени пробы … мс, RTT меньше пробы у X из Y» — RTT в разы меньше
пробы, X равно или почти равно Y. Записать N, M, K, медианы, X и Y.

Если не так: «с RTT: 0» через 15 минут после установки — **дефект «RTT не замеряется»**:
записать.

## 7. Рейтинг серверов

Шаг 7.1.

```bash
cd "$HOME/xgw-020" && sudo python3 -I v020check.py rating | tee rating.txt
```

Ожидается: состояние `HEALTHY` (или `DEGRADED` с текстом про замену — записать); у каждого
участника и запасного есть рейтинг («без рейтинга: участников 0, запасных 0»); участники — с
наибольшими рейтингами (сравнить с «запасной …: рейтинг …»; запасной лучше участника не больше
чем на 25 % — норма, перестановка — раз в 15 минут); ««заменить некем»: нет». Записать таблицу.

Если не так: у кого-то нет рейтинга через 15 минут после установки — записать как наблюдение.
«заменить некем: да» при живых запасных с рейтингом — **дефект «заменить некем»**.

Шаг 7.2 (при согласии на пункт 3). **Попроси заказчика** (дословно):

«В панели, карточка „Серверы": под названием сервера в работе есть слово „рейтинг" с числом?
Наведите мышь на задержку в мс справа — что во всплывающей подсказке? Если у вас есть серверы с
приоритетом „высокий" или „низкий" — что написано в пояснении над списком серверов?»

Ожидается: «рейтинг 0,xx» в подписи сервера; подсказка «Сетевая задержка (RTT) по замеру <время>;
проба целиком — N мс»; пояснение «Приоритет — вес в рейтинге сервера: «высокий» ×1,45, «низкий» ×0,65.
В работе — лучшие по рейтингу из всех подписок…». Записать ответы дословно.

## 8. Полчаса работы (при согласии на пункт 5)

Шаг 8.1. Подожди 30 минут (заказчик пользуется интернетом как обычно), затем:

```bash
cd "$HOME/xgw-020" && J="sudo journalctl -u xgw --since $(printf %q "$(cat install-time.txt)") --no-pager"; eval "$J" | grep -c 'перестановка по рейтингу' | sed 's/^/перестановок по рейтингу: /' | tee work.txt; eval "$J" | grep -c 'замена участников' | sed 's/^/замен мёртвых: /' | tee -a work.txt; eval "$J" | grep -c 'основной сервер сменён' | sed 's/^/смен основного: /' | tee -a work.txt; eval "$J" | grep -c 'теневая проба' | sed 's/^/теневых проб: /' | tee -a work.txt; eval "$J" | grep -cE 'перезапуск Xray|restart' | sed 's/^/строк о перезапуске Xray: /' | tee -a work.txt; eval "$J" | grep -E 'в работу —|замена участников|скан запасных —' | tail -6 | tee -a work.txt; sudo python3 -I v020check.py budget | tee -a work.txt; sudo xgw status | grep -E '^Состояние' | tee -a work.txt
```

Ожидается: перестановок по рейтингу — 0–2 (не чаще раза в 15 минут); смен основного — 0–2;
теневых проб — любое число (бывают раз в 12–24 ч на сервер с обходом — чаще всего 0); строк о
перезапуске Xray — 0 или 1 (после установки); бюджет: `total_mb` не больше `limit_mb`,
`over: False`, `scan_minutes` — 60 или больше (больше — шлюз растянул скан, чтобы уложиться в
лимит; тогда в журнале строка «скан запасных — раз в N мин»); состояние `HEALTHY`. Записать всё.

Если не так: перестановок больше 2 или смен основного больше 3 — **дефект «скачет между
серверами»**: записать последние строки журнала (уже в `work.txt`). `over: True` — записать
предупреждения бюджета (это наблюдение: пробы ядра больше лимита).

## 9. Запись трафика (при согласии на пункт 4)

Шаг 9.1. **Попроси заказчика** (дословно):

«В строке телефона в карточке „Устройства" нажмите „Записать" и через 20 секунд — „Остановить".
Что написала панель (там должно быть „Не дольше 5 минут")? Скачивать файл не нужно.»

Затем:

```bash
cd "$HOME/xgw-020" && sudo python3 -I v020check.py record | tee record.txt
```

Ожидается: панель — «… Не дольше 5 минут; готовый файл — в карточке „Устройства"»; в выводе —
запись меньше 50 МБ, «итог: остановлено». Записать. Попросить заказчика удалить запись кнопкой у
файла (в нём трафик телефона).

## 10. Значок в трее (при согласии на пункт 3)

Шаг 10.1. **Попроси заказчика** (дословно):

«Закройте вкладку XGW в браузере. Щёлкните значок XGW в трее два раза подряд быстро. Сколько
вкладок XGW открылось? Потом щёлкните ещё раз — новая вкладка или та же вышла вперёд?»

Ожидается: одна вкладка; на третий щелчок — та же вкладка вперёд. Две и больше — **дефект «две
вкладки»**: записать ответ.

## 11. Итог

Шаг 11.1.

```bash
cd "$HOME/xgw-020" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c Traceback | sed 's/^/Traceback в xgw: /' | tee final.txt; sudo xgw diag | tail -1 | tee -a final.txt; sudo xgw status | grep -E '^Состояние|Перехват:' | tee -a final.txt
```

Ожидается: Traceback — 0; «FAIL — 0»; `HEALTHY`, перехват включён.

Если не так: Traceback больше 0 — записать `sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | head -60 | tee traceback.txt`
(без адресов серверов и подписок).

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- У телефона пропал интернет после выбора сервера — попросить заказчика выбрать «Сервер: авто».
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.

## 12. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`release-0.2.0`), коммит «Отчёт: XGW 0.2.0», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0 (рекомендации к аудиту 0.1.18)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
v020check.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, перехват |
| 1.3 процессор до | — | Y % |
| 2.2 установка | … | код … |
| 2.3 после установки | … | HEALTHY, балансировщики, to-main, subjectSelector |
| 3.1 резолверы | … | какие не отвечают, кэш: имён K, адресов A, служебных … |
| 3.2 DoH Яндекса | … | соединений … |
| 4.1 nft и rp_filter | … | КБ/мс полного и -t, loaded, rp_filter, 90-xgw.conf, MSS |
| 4.2 процессор после | … | Y % до / после, перезагрузок … |
| 5.1 свой сервер | … / не выполнялся | страна, правило, Xray без перезапуска |
| 5.2 мёртвый свой сервер | … / нет такого / не выполнялся | молчит, через основной, интернет |
| 5.3 возврат | … | что выбрал заказчик |
| 6.1 RTT | … | N, M, K, медианы |
| 7.1 рейтинг | … | состояние, без рейтинга, «некем» |
| 7.2 панель | … / не выполнялся | рейтинг, подсказка, пояснение |
| 8.1 полчаса | … / не выполнялся | перестановок, замен, смен основного, теневых, бюджет |
| 9.1 запись | … / не выполнялся | МБ, итог |
| 10.1 трей | … / не выполнялся | вкладок |
| 11.1 итог | … | Traceback, FAIL, HEALTHY |

## Выводы шагов
<файлы $HOME/xgw-020/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
