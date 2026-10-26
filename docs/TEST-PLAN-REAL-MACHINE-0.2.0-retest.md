# Перепроверка XGW 0.2.0: исправления по отчёту

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы сохраняй в файлы, как написано (`$HOME/xgw-020b/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, KDE Plasma (X11), браузер Chromium. Клон —
`~/zcod/xgw`. Код — ветка `release-0.2.0`, версия 0.2.0. Сейчас на машине стоит 0.2.0 с
коммита af09085; её программа пройдена, отчёт `docs/TEST-REPORT-REAL-MACHINE-0.2.0-2026-10-26.md`.
Проверяемый телефон — S25 Ultra, адрес в домашней сети 192.168.60.135.

Что исправлено (ASSUMPTIONS п. 249):
1. **Кэш адресов подписок** (дефект 1 отчёта): при живом Xray подписка идёт через него, и
   адрес её сервера не записывался никогда. Теперь шлюз раз в сутки проверяет прямой путь к
   серверу подписки — одно рукопожатие TLS с проверкой сертификата, без запроса самой
   подписки — и записывает адрес в `dns-cache.json`.
2. **Значок в трее** (дефект 2): второй быстрый щелчок больше не открывает вторую вкладку —
   8 секунд после запуска браузера щелчок ждёт открывающуюся вкладку и выводит её вперёд.
3. **Проверка правил nftables** (наблюдение 2): с nft 1.0.9 она шла 3,5 с на каждом шаге
   демона (раз в 20 с). Теперь правила перечитываются, только когда ядро сообщает, что их
   кто-то изменил (номер поколения правил).
4. **Помощник**: процессор считается по службе xgw целиком — вместе с запусками nft (раньше —
   только сам процесс демона); у записи трафика — сколько она шла на самом деле (раньше
   печатался предел 300 с).

Здесь, у разработчика, проверены юнит-тесты, поколение правил и кэш на nftables 1.1.6 (Ubuntu 26.04),
рукопожатие TLS через DoT Яндекса. Шлюз заказчика, nft 1.0.9, значок и запись — эта программа.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list` и `nft -t list`), `ip`, `iptables`, `tc`, `sysctl -w`.
- Править `/etc/xgw` (в том числе `panel.json`), `/opt/xgw`, `/var/lib/xgw`, `/etc/systemd`,
  код XGW. Серверы и переключатели в панели меняет только заказчик. Коммитить что-либо, кроме
  отчёта (§8).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP и домены серверов
  VPN. Можно: адреса устройств в домашней сети (`192.168.…`), отпечатки серверов (8 знаков),
  названия и страны серверов, IP публичных резолверов (77.88.8.8, 1.1.1.1 и т. п.), счётчики,
  времена, проценты.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю исправления XGW 0.2.0 по прошлому отчёту. По пунктам:
(1) Переустановка XGW с новым кодом: Xray перезапустится — интернет дома пропадёт на несколько
секунд.
(2) Значок XGW в трее: закроете вкладку XGW и пощёлкаете значок, как я попрошу.
(3) Запись трафика телефона на 20 секунд из панели.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — §5 пропустить, против 3 — §6; в отчёте у пропущенного —
«не выполнялся».

Шаг 1.2. Папка и помощник проверки (только читает):

```bash
mkdir -p "$HOME/xgw-020b" && chmod 700 "$HOME/xgw-020b" && cd "$HOME/xgw-020b" && cat > v020bcheck.py <<'EOF'
"""XGW 0.2.0, перепроверка: помощник. Только читает: /proc и cgroup службы xgw, кэш адресов
подписок (без имён), правила nftables ip xgw (тем же кодом, что демон), записи трафика (без
самих файлов); режим log — журнал xgw со стандартного ввода (печатает только счётчики).
Режимы: cpu, dns, nft, log, record."""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/opt/xgw/lib")
from xgw.paths import Paths  # noqa: E402

paths = Paths.from_env()
mode = sys.argv[1] if len(sys.argv) > 1 else ""


def unit(prop):
    return subprocess.run(["systemctl", "show", "-p", prop, "--value", "xgw.service"],
                          capture_output=True, text=True).stdout.strip()


if mode == "cpu":
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    pid = unit("MainPID")
    stat = f"/sys/fs/cgroup{unit('ControlGroup')}/cpu.stat"

    def ticks():
        fields = open(f"/proc/{pid}/stat", encoding="ascii").read().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")

    def usage():
        try:
            for line in open(stat, encoding="ascii"):
                name, _, value = line.partition(" ")
                if name == "usage_usec":
                    return int(value) / 1e6
        except OSError:
            return None
        return None

    first, first_all = ticks(), usage()
    time.sleep(seconds)
    used, used_all = ticks() - first, usage()
    print(f"процессор демона xgw (сам процесс): {used:.1f} с за {seconds} с "
          f"({100 * used / seconds:.1f} %)")
    if first_all is None or used_all is None:
        print(f"служба xgw целиком: нет {stat}")
    else:
        spent = used_all - first_all
        print(f"служба xgw целиком (с nft и другими запусками): {spent:.1f} с за {seconds} с "
              f"({100 * spent / seconds:.1f} %)")
    sys.exit(0)

from xgw import config, fetch  # noqa: E402

cfg, _warnings = config.load(paths.config_file)

if mode == "dns":
    cache = paths.cache_dir / "dns-cache.json"
    try:
        hosts = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hosts = None
    names = sum(1 for sub in cfg.subscriptions if sub.url.startswith("https://"))
    print(f"подписок https: {names}")
    if hosts is None:
        print("кэш адресов подписок: файла нет")
    else:
        addresses = [ip for entry in hosts.values() for ip in entry.get("ips", [])]
        newest = max((entry.get("ts", 0) for entry in hosts.values()), default=0)
        print(f"кэш адресов подписок: имён {len(hosts)}, адресов {len(addresses)}, служебных "
              f"{sum(fetch.is_bogon(ip) for ip in addresses)}, права "
              f"{oct(cache.stat().st_mode & 0o777)}, последняя запись "
              f"{int((time.time() - newest) // 60)} мин назад")
elif mode == "nft":
    from xgw.net import nft
    from xgw.net.capture import capture_for

    print(f"поколение правил ядра: {nft.generation()}")
    capture = capture_for(cfg, paths)
    lister = capture.lister
    for attempt in ("первая", "вторая", "третья"):
        runs = getattr(lister, "runs", None)
        started = time.monotonic()
        loaded = capture.loaded()
        spent = 1000 * (time.monotonic() - started)
        ran = "кэша нет" if runs is None else str(lister.runs - runs)
        print(f"{attempt} проверка правил (loaded): {loaded}, {spent:.0f} мс, запусков nft для "
              f"чтения: {ran}")
    for argv in (["nft", "list", "table", "ip", "xgw"], ["nft", "-t", "list", "table", "ip", "xgw"]):
        started = time.monotonic()
        text = subprocess.run(argv, capture_output=True, text=True).stdout
        print(f"{' '.join(argv)}: {len(text) // 1024} КБ, "
              f"{1000 * (time.monotonic() - started):.0f} мс")
elif mode == "log":
    lines = sys.stdin.read().splitlines()

    def count(text):
        return sum(1 for line in lines if text in line)

    print(f"строк журнала: {len(lines)}")
    print(f"прямой адрес подписки проверен и записан: {count('прямой адрес её сервера проверен')}")
    failed = [line for line in lines if "прямой путь к её серверу не проверен" in line]
    kinds = {}
    for line in failed:
        low = line.lower()
        kind = ("таймаут" if "timed out" in low or "timeout" in low else
                "сертификат" if "certificate" in low or "ssl" in low else
                "DNS" if "разрешить" in low or "резолвер" in low else
                "отказ соединения" if "refused" in low or "unreachable" in low else "другое")
        kinds[kind] = kinds.get(kind, 0) + 1
    print(f"прямой путь не проверен: {len(failed)} {kinds if kinds else ''}".rstrip())
    print(f"подписка по прежнему адресу (резолверы молчали): {count('получена по прежнему адресу')}")
    print(f"правила загружены заново: {count('загружены заново')}")
    print(f"Traceback: {count('Traceback')}")
elif mode == "record":
    directory = paths.records_dir
    files = sorted(directory.glob("*.pcap")) if directory.is_dir() else []
    print(f"записей: {len(files)}")
    for path in files[-3:]:
        try:
            meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        took = meta.get("ended", 0) - meta.get("started", 0)
        print(f"  {path.stat().st_size / 1e6:.1f} МБ, пакетов {meta.get('packets')}, шла "
              f"{took:.0f} с (предел {meta.get('seconds')} с), итог: {meta.get('why')}")
else:
    print("режим: cpu | dns | nft | log | record")
EOF
sha256sum v020bcheck.py | cut -c1-16; sudo xgw status | grep -E '^Состояние|Перехват:' | tee before.txt
```

Ожидается: `1fe084bf16263373`; `Состояние: HEALTHY …`, `Перехват: включён …`. Записать как есть.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать (это до установки) и продолжить.

Шаг 1.3. Процессор **до** установки (прежний код, 2 минуты):

```bash
cd "$HOME/xgw-020b" && sudo python3 -I v020bcheck.py cpu 120 | tee cpu-before.txt
```

Ожидается: две строки — «процессор демона xgw (сам процесс): … (Y1 %)» и «служба xgw целиком
(с nft и другими запусками): … (Y2 %)». Записать Y1 и Y2. Вторая строка «нет …cpu.stat» —
записать, продолжить (тогда сравнивать в §4.2 нечем — это наблюдение).

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout release-0.2.0 && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def check_direct' src/xgw/fetch.py && grep -q 'class Listings' src/xgw/net/nft.py && grep -q 'LAUNCH_HOLD' src/xgw/tray.py && echo "исправления в коде: есть"; cd "$HOME/xgw-020b"
```

Ожидается: «исправления в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-020b/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-020b/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-020b"
```

Ожидается: «код 0», «демон xgw запущен». Код не 0 — **стоп**, сохранить вывод, сообщить
заказчику (сеть не тронута).

Шаг 2.3. Через 2 минуты — шлюз в порядке:

```bash
sleep 120; cd "$HOME/xgw-020b" && sudo xgw status | grep -E '^Состояние|Перехват:|^Xray' | tee after-install.txt
```

Ожидается: `HEALTHY`, перехват включён. Записать.

Если не так: не `HEALTHY` — подождать 2 минуты, повторить; снова нет — записать `sudo xgw
status` целиком (без адресов серверов) и продолжить.

## 3. Кэш адресов подписок

Шаг 3.1. Через 5 минут после установки (команда сама ждёт ещё 3 минуты):

```bash
sleep 180; cd "$HOME/xgw-020b" && sudo python3 -I v020bcheck.py dns | tee dns.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020bcheck.py log | tee log-dns.txt
```

Ожидается:
- «подписок https: N» (N — 1 или больше);
- «кэш адресов подписок: имён K, адресов A, служебных 0, права 0o600, последняя запись M мин
  назад» — K от 1 до N, A не меньше K, M не больше минут с установки;
- в выводе журнала — «прямой адрес подписки проверен и записан: 1» или больше.

Записать обе части (числа; адресов и имён помощник не печатает).

Если не так:
- «файла нет», а «прямой путь не проверен: X {…}» больше 0 — это **наблюдение «прямой путь к
  подписке закрыт»**: записать X и вид причины в скобках (таймаут, сертификат, DNS, отказ
  соединения) и продолжить. Подписка работает через Xray; кэш нужен только на случай, когда
  Xray не отвечает.
- «файла нет», а оба счётчика («проверен и записан», «не проверен») — 0: подождать 5 минут,
  повторить шаг (без `sleep 180` — можно сразу); снова так — **дефект «кэш адресов подписок
  не пишется»**: записать
  `sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -iE 'подписк' | tail -10 | tee dns-log.txt`
  (адреса подписок в выводе замаскированы — всё равно проверить и убрать, если видны).
- «служебных» больше 0 — **дефект «в кэш попал подменённый адрес»**.

## 4. Проверка правил nftables

Шаг 4.1.

```bash
cd "$HOME/xgw-020b" && sudo python3 -I v020bcheck.py nft | tee nft.txt
```

Ожидается:
- «поколение правил ядра: <число>»;
- «первая проверка правил (loaded): True, … мс, запусков nft для чтения: 1» или больше;
- «вторая …» и «третья …»: `True`, «запусков nft для чтения: 0», время — в разы меньше, чем у
  первой (обычно десятки мс: остаются проверки маршрутов `ip rule` и `ip route`);
- `nft list table ip xgw` и `nft -t list table ip xgw` — размеры и времена (для сравнения с
  прошлым отчётом: 874 КБ / 901 мс и 3 КБ / 765 мс). Записать всё.

Если не так:
- «поколение правил ядра: None», а у второй и третьей «запусков» больше 0 — **дефект
  «поколение правил не читается»**: записать вывод и продолжить.
- Поколение — число, но у второй или третьей «запусков» больше 0 — повторить шаг через минуту
  (правила мог поменять Docker или Tailscale); снова так — **дефект «кэш проверки правил не
  работает»**.
- `loaded: False` — повторить через минуту; снова False — **дефект «проверка правил»**.

Шаг 4.2. Процессор **после** установки (2 минуты) и правила не перезагружаются:

```bash
cd "$HOME/xgw-020b" && sudo python3 -I v020bcheck.py cpu 120 | tee cpu-after.txt; sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020bcheck.py log | tee -a cpu-after.txt
```

Ожидается: у «служба xgw целиком» Y2 **меньше**, чем до установки (§1.3) — с nft 1.0.9 обычно
в разы; «правила загружены заново: 0» или 1 (при установке). Записать Y1 и Y2 до и после.

Если не так: Y2 после не меньше, чем до, — **дефект «процессор не снизился»**: записать обе
пары строк. «правила загружены заново» больше 1 — **дефект «правила перезагружаются»**: записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -B1 -A1 'загружены заново' | tail -20 | tee reload.txt`.

## 5. Значок в трее (при согласии на пункт 2)

Шаг 5.1. **Попроси заказчика** (дословно):

«Закройте вкладку XGW в браузере. Щёлкните значок XGW в трее два раза подряд быстро. Сколько
вкладок XGW открылось? Потом щёлкните ещё раз — новая вкладка или та же вышла вперёд?»

Ожидается: одна вкладка; на третий щелчок — та же вкладка вперёд. Две и больше — **дефект «две
вкладки»**: записать ответ.

Шаг 5.2. **Попроси заказчика** (дословно):

«Закройте вкладку XGW, подождите 10 секунд и щёлкните значок один раз. Открылась вкладка XGW?»

Ожидается: «да», одна. Не открылась — повторить просьбу ещё раз; снова нет — **дефект «панель
не открывается после закрытия»**: записать ответ.

## 6. Запись трафика (при согласии на пункт 3)

Шаг 6.1. **Попроси заказчика** (дословно):

«В строке телефона в карточке „Устройства" нажмите „Записать" и примерно через 20 секунд —
„Остановить". Скачивать файл не нужно.»

Затем:

```bash
cd "$HOME/xgw-020b" && sudo python3 -I v020bcheck.py record | tee record.txt
```

Ожидается: последняя строка — новая запись: «шла N с (предел 300 с), итог: остановлено», N от 10
до 60. Записать. Попросить заказчика удалить запись кнопкой у файла (в нём трафик телефона).

Если не так: «итог: время вышло» и N около 300 — **дефект «Остановить не работает»**.
«остановлено», но N больше 60 — спросить заказчика, когда нажал «Остановить», записать ответ.

## 7. Итог

Шаг 7.1. Не раньше чем через 15 минут после установки (по `install-time.txt`):

```bash
cd "$HOME/xgw-020b" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020bcheck.py log | tee final.txt; sudo xgw diag | tail -1 | tee -a final.txt; sudo xgw status | grep -E '^Состояние|Перехват:' | tee -a final.txt
```

Ожидается: «Traceback: 0»; «FAIL — 0»; `HEALTHY`, перехват включён; «правила загружены заново»
— 0 или 1.

Если не так: Traceback больше 0 — записать `sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | head -60 | tee traceback.txt`
(без адресов серверов и подписок).

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.

## 8. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-retest-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`release-0.2.0`), коммит «Отчёт: XGW 0.2.0, перепроверка», `git push`. Шаблон:

```markdown
# Отчёт: перепроверка XGW 0.2.0 (исправления по отчёту)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
v020bcheck.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, перехват |
| 1.3 процессор до | — | Y1 %, Y2 % |
| 2.2 установка | … | код … |
| 2.3 после установки | … | HEALTHY |
| 3.1 кэш подписок | … | N, K, A, служебных, M; проверен и записан / не проверен (вид) |
| 4.1 проверка правил | … | поколение, мс и запуски трёх проверок, КБ/мс полного и -t |
| 4.2 процессор после | … | Y1 и Y2 до / после, перезагрузок |
| 5.1 трей, два щелчка | … / не выполнялся | вкладок, третий щелчок |
| 5.2 трей после закрытия | … / не выполнялся | открылась ли |
| 6.1 запись | … / не выполнялся | шла N с, итог |
| 7.1 итог | … | Traceback, FAIL, HEALTHY |

## Выводы шагов
<файлы $HOME/xgw-020b/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
