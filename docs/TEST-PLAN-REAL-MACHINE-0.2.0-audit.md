# Проверка XGW 0.2.0: доработки по аудиту

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-020c/…`). Файл помощника создавай только командой шага 1.2, выполненной в терминале:
если создать его по-другому (например, записать текст в файл инструментом), сумма не совпадёт.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, KDE Plasma (X11), браузер Chromium. Клон —
`~/zcod/xgw`. Код — ветка `release-0.2.0`, версия 0.2.0. Сейчас на машине стоит 0.2.0 с
коммита 5b7c633; её перепроверка пройдена, отчёт
`docs/TEST-REPORT-REAL-MACHINE-0.2.0-retest-2026-10-26.md`. Телефон — S25 Ultra в домашней сети.

Что изменено (ASSUMPTIONS п. 250):
1. **Службы Xray и sing-box** получили ограничения systemd: параметры и модули ядра, журнал
   ядра, часы, cgroup и свои пространства имён им закрыты, сокеты — только IP, netlink и UNIX.
   Установка перезапускает ядро, если файл его службы изменился (иначе ограничения вступили бы
   в силу только после перезагрузки).
2. **Устаревшие строки `config.toml`** (Telegram, `xray.version` другой версии) — о них
   предупреждал каждый `xgw status`. Установка выключает их сама: строка становится
   комментарием `# не используется: …`, значение в ней остаётся.
3. **Поиск серверов, которых ядро не принимает** — делением пополам, а не по одному; отвергнутые
   запоминаются до обновления ядра.
4. **Временные файлы с ключами серверов** — в `/run/xgw` (в памяти), а не в `/tmp` на диске.
5. **Порты проверок Xray** обходят порты панели, API sing-box и входов sing-box.
6. **Строка в журнале**, когда прямой запрос подписки записывает новый адрес в кэш адресов.
7. **Замер процессора** — с закрытой и с открытой вкладкой XGW: в перепроверке сам демон
   вырос с 2,2 до 4,2 %, а открытая вкладка опрашивает его каждые 3 секунды.

Здесь, у разработчика, проверены юнит-тесты, Xray 26.10.21 и sing-box 1.14.3 под systemd с
новыми ограничениями (TUN, TPROXY, метка на сокетах, все протоколы sing-box — поведение то же,
что без них), поиск битых серверов живыми Xray и sing-box. Шлюз заказчика — эта программа.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list` и `nft -t list`), `ip`, `iptables`, `tc`, `sysctl -w`.
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/etc/systemd`, код XGW. Печатать `config.toml` (`cat`, `less`, `grep` по нему) — в нём ключи
  подписок. Серверы и переключатели в панели меняет только заказчик. Коммитить что-либо, кроме
  отчёта (§7).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP и домены серверов
  VPN. Можно: адреса устройств в домашней сети (`192.168.…`), отпечатки серверов (8 знаков),
  названия и страны серверов, имена ключей config.toml, счётчики, времена, проценты.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю доработки XGW 0.2.0 по аудиту. По пунктам:
(1) Переустановка XGW с новым кодом: Xray и sing-box перезапустятся — интернет дома пропадёт
на несколько секунд. Установка сама выключит в /etc/xgw/config.toml строки, которые больше
ничего не значат (Telegram, версия Xray): они станут комментариями, значения в них останутся.
(2) Вкладка XGW в браузере: по моей просьбе закроете все вкладки XGW на 2 минуты, потом
откроете значком в трее и оставите на экране ещё на 2 минуты. И откроете любой сайт на этом
компьютере и на телефоне.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — шаги 4.2 и §5 пропустить; в отчёте у пропущенного —
«не выполнялся».

Шаг 1.2. Папка, помощник проверки (только читает) и состояние до установки:

```bash
mkdir -p "$HOME/xgw-020c" && chmod 700 "$HOME/xgw-020c" && cd "$HOME/xgw-020c" && cat > v020ccheck.py <<'EOF'
"""XGW 0.2.0, доработки по аудиту: помощник. Только читает: /proc и cgroup службы xgw, службы
ядер (systemctl show, /proc/<pid>/status, systemd-analyze security), config.toml (печатает
только счётчик строк), журнал со стандартного ввода (только счётчики). Режимы: cpu, units,
config, log."""
import os
import re
import subprocess
import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else ""


def show(unit, prop):
    return subprocess.run(["systemctl", "show", "-p", prop, "--value", unit],
                          capture_output=True, text=True).stdout.strip()


if mode == "cpu":
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    pid = show("xgw.service", "MainPID")
    stat = f"/sys/fs/cgroup{show('xgw.service', 'ControlGroup')}/cpu.stat"
    tick = os.sysconf("SC_CLK_TCK")

    def fields():
        return open(f"/proc/{pid}/stat", encoding="ascii").read().rsplit(")", 1)[1].split()

    def ticks():
        values = fields()
        return (int(values[11]) + int(values[12])) / tick

    def usage():
        try:
            for line in open(stat, encoding="ascii"):
                name, _, value = line.partition(" ")
                if name == "usage_usec":
                    return int(value) / 1e6
        except OSError:
            return None
        return None

    uptime = float(open("/proc/uptime", encoding="ascii").read().split()[0])
    print(f"демон xgw работает: {int((uptime - int(fields()[19]) / tick) // 60)} мин")
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
elif mode == "units":
    for unit in ("xgw-xray.service", "xgw-singbox.service"):
        pid = show(unit, "MainPID")
        found = {"Seccomp": "-", "NoNewPrivs": "-"}
        try:
            for line in open(f"/proc/{pid}/status", encoding="ascii"):
                name, _, value = line.partition(":")
                if name in found:
                    found[name] = value.strip()
        except OSError:
            pass
        report = subprocess.run(["systemd-analyze", "security", "--no-pager", unit],
                                capture_output=True, text=True).stdout
        score = re.search(r"Overall exposure level for \S+: ([0-9.]+)", report)
        print(f"{unit}: {show(unit, 'ActiveState')}, Seccomp {found['Seccomp']}, NoNewPrivs "
              f"{found['NoNewPrivs']}, ProtectKernelTunables "
              f"{show(unit, 'ProtectKernelTunables')}, оценка {score.group(1) if score else '?'}")
elif mode == "config":
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw.paths import Paths

    text = Paths.from_env().config_file.read_text(encoding="utf-8")
    retired = sum(1 for line in text.splitlines() if line.startswith("# не используется:"))
    print(f"выключенных строк в config.toml: {retired}")
elif mode == "log":
    lines = sys.stdin.read().splitlines()

    def count(text):
        return sum(1 for line in lines if text in line)

    print(f"строк журнала: {len(lines)}")
    print(f"отброшено серверов — Xray не принимает: {count('отброшен: Xray не принимает')}")
    print(f"отброшено серверов — sing-box не принимает: {count('отброшен: sing-box не принимает')}")
    print(f"адрес подписки записан при прямом запросе: {count('получена напрямую, адрес её')}")
    print(f"адрес подписки записан суточной проверкой: {count('проверен (TLS) и записан')}")
    print(f"предупреждений sing-box о буфере приёма: {count('receive buffer')}")
    print(f"правила загружены заново: {count('загружены заново')}")
    print(f"Traceback: {count('Traceback')}")
else:
    print("режим: cpu | units | config | log")
EOF
sha256sum v020ccheck.py | cut -c1-16; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^sing-box' | tee before.txt; echo "предупреждений о строках config.toml: $(sudo xgw status 2>&1 | grep -cE 'Telegram в XGW больше нет|не учитывается')" | tee -a before.txt; sudo python3 -I v020ccheck.py units | tee units-before.txt
```

Ожидается:
- `70f85f3392dff215`;
- `Состояние: HEALTHY …`, `Перехват: включён …`, строка `sing-box …` (записать как есть);
- «предупреждений о строках config.toml: W» — W больше 0 (в прошлом отчёте их было 5: четыре
  про Telegram и одно про `xray.version`);
- две строки `xgw-xray.service: …` и `xgw-singbox.service: …` — состояние, `Seccomp`,
  `ProtectKernelTunables`, `оценка` (число). Записать.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать (это до установки) и продолжить.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout release-0.2.0 && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def narrow' src/xgw/generator/validate.py && grep -q 'def retire_obsolete' src/xgw/config.py && grep -q 'def secret_tempdir' src/xgw/paths.py && grep -q '^ProtectKernelTunables=yes' packaging/xgw-xray.service && grep -q '^ProtectKernelTunables=yes' packaging/xgw-singbox.service && echo "доработки в коде: есть"; cd "$HOME/xgw-020c"
```

Ожидается: «доработки в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-020c/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-020c/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'выключены строки|перезапущен' "$HOME/xgw-020c/install.txt"; cd "$HOME/xgw-020c"
```

Ожидается:
- «код 0», «демон xgw запущен»;
- строка «…config.toml: выключены строки, которые больше ничего не значат — <ключи> (значения
  остались в комментарии)» — в ней только имена ключей (`notify.telegram_bot_token`,
  `xray.version` и т. п.);
- «Xray перезапущен: файл его службы изменился» и «sing-box перезапущен: файл его службы
  изменился». Строки про Xray может не быть, если он и так перезапустился с новым конфигом, а
  про sing-box — если sing-box не работал; это решает §4.

Записать строки как есть.

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).
Строки «выключены строки» нет, а W в §1.2 больше 0 — записать и продолжить (§3 покажет).

Шаг 2.3. Через 2 минуты — шлюз в порядке:

```bash
sleep 120; cd "$HOME/xgw-020c" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee after-install.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray отвечает, строка sing-box — как до установки
(§1.2). Записать.

Если не так: не `HEALTHY` — подождать 2 минуты, повторить; снова нет — записать `sudo xgw
status` целиком (без адресов серверов) и продолжить. Строка sing-box стала «НЕ ОТВЕЧАЕТ», а до
установки было «работает» — **дефект «sing-box не работает с новыми ограничениями»**: записать
`sudo journalctl -u xgw-singbox --since "$(cat install-time.txt)" --no-pager | tail -30 | tee singbox-log.txt`
(адреса серверов убрать, если видны), сообщить заказчику и продолжить.

## 3. Строки config.toml

```bash
cd "$HOME/xgw-020c" && echo "предупреждений о строках config.toml: $(sudo xgw status 2>&1 | grep -cE 'Telegram в XGW больше нет|не учитывается')" | tee config.txt; sudo python3 -I v020ccheck.py config | tee -a config.txt
```

Ожидается: «предупреждений о строках config.toml: 0»; «выключенных строк в config.toml: N» — N
равно числу ключей в строке установки (§2.2).

Если не так: предупреждения остались — **дефект «строки config.toml не выключены»**: записать
`sudo xgw status 2>&1 | grep -E 'Telegram в XGW больше нет|не учитывается' | tee config-left.txt`
(в этих строках только имена ключей, значений нет).

## 4. Службы ядер

Шаг 4.1.

```bash
cd "$HOME/xgw-020c" && sudo python3 -I v020ccheck.py units | tee units-after.txt
```

Ожидается: у обеих служб — `active`, `Seccomp 2` (у процесса работает фильтр системных
вызовов — так systemd применяет новые ограничения), `NoNewPrivs 1`, `ProtectKernelTunables yes`,
оценка меньше, чем до установки (§1.2). Записать обе строки.

Если не так:
- `xgw-singbox.service: inactive` и до установки (§1.2) тоже — так бывает, когда серверов для
  sing-box нет: записать и продолжить.
- служба была `active`, а стала не `active` — **дефект «ядро не запускается с новыми
  ограничениями»**: записать
  `sudo journalctl -u <служба> --since "$(cat install-time.txt)" --no-pager | tail -30 | tee unit-log.txt`
  (адреса серверов убрать, если видны), сообщить заказчику; сеть руками не трогать.
- `active`, но `Seccomp 0` или `ProtectKernelTunables no` — **дефект «ограничения не
  применились»** (ядро не перезапустилось после установки): записать строку.

Шаг 4.2 (при согласии на пункт 2). **Попроси заказчика** (дословно):

«Откройте любой сайт на этом компьютере и любой сайт на телефоне. Открываются?»

Ожидается: «да» и там, и там. Нет — записать ответ дословно, выполнить `sudo xgw status 2>&1 |
grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt` и сообщить заказчику.

## 5. Процессор с вкладкой и без (при согласии на пункт 2)

Шаг 5.1. **Попроси заказчика** (дословно):

«Закройте все вкладки XGW в браузере (сам браузер можно не закрывать) и 2 минуты не открывайте.
Скажите, когда закрыли.»

После ответа:

```bash
cd "$HOME/xgw-020c" && sudo python3 -I v020ccheck.py cpu 120 | tee cpu-closed.txt
```

Шаг 5.2. **Попроси заказчика** (дословно):

«Откройте XGW значком в трее и оставьте вкладку на экране 2 минуты: окно не сворачивайте и на
другую вкладку не переключайтесь. Скажите, когда открыли.»

После ответа:

```bash
cd "$HOME/xgw-020c" && sudo python3 -I v020ccheck.py cpu 120 | tee cpu-open.txt
```

Ожидается в каждом: «демон xgw работает: M мин», «процессор демона xgw (сам процесс): … (Y1 %)»,
«служба xgw целиком …: … (Y2 %)». Записать M, Y1 и Y2 обоих замеров. Дефектов в этом шаге нет —
нужны числа: разница Y1 между открытой и закрытой вкладкой — цена опроса панели. Для сравнения
в перепроверке: сам процесс 2,2 % (до установки) и 4,2 % (после).

## 6. Итог

Шаг 6.1. Не раньше чем через 15 минут после установки (по `install-time.txt`):

```bash
cd "$HOME/xgw-020c" && sudo journalctl -u xgw -u xgw-singbox --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020ccheck.py log | tee final.txt; sudo xgw diag | tail -1 | tee -a final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^sing-box' | tee -a final.txt
```

Ожидается: «Traceback: 0»; «FAIL — 0»; `HEALTHY`, перехват включён, sing-box — как до установки;
«правила загружены заново» — 0 или 1. Остальные счётчики записать как есть — это наблюдения:
сколько серверов ядра не приняли; записался ли адрес подписки; пишет ли sing-box, что не смог
поднять буфер приёма для QUIC (аудит, F-08: тогда стоит думать о настройке ядра, иначе — нет).

Если не так: Traceback больше 0 — записать
`sudo journalctl -u xgw -u xgw-singbox --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | head -60 | tee traceback.txt`
(без адресов серверов и подписок).

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`release-0.2.0`), коммит «Отчёт: XGW 0.2.0, доработки по аудиту», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, доработки по аудиту

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
v020ccheck.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, sing-box, W предупреждений, Seccomp и оценки служб |
| 2.2 установка | … | код, выключенные ключи, строки о перезапуске |
| 2.3 после установки | … | HEALTHY, sing-box |
| 3 строки config.toml | … | предупреждений, выключенных строк |
| 4.1 службы ядер | … | active, Seccomp, ProtectKernelTunables, оценка до → после |
| 4.2 сайты | … / не выполнялся | компьютер, телефон |
| 5 процессор | … / не выполнялся | M, Y1, Y2: вкладка закрыта / открыта |
| 6.1 итог | … | Traceback, FAIL, HEALTHY, счётчики |

## Выводы шагов
<файлы $HOME/xgw-020c/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
