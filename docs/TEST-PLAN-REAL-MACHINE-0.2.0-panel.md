# Проверка XGW 0.2.0: нагрузка открытой вкладки панели

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком в терминал), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не
уверен — остановись и спроси заказчика. Выводы сохраняй в файлы, как написано
(`$HOME/xgw-020d/…`). Файл помощника создавай только командой шага 1.2, выполненной в терминале:
если создать его по-другому (например, записать текст в файл инструментом), сумма не совпадёт.

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, KDE Plasma (X11), браузер Chromium. Клон —
`~/zcod/xgw`. Код — ветка `panel-cpu`, версия 0.2.0. Сейчас на машине стоит 0.2.0 с коммита
c44759a (то же, что теперь в `main`); проверка доработок по аудиту пройдена, отчёт
`docs/TEST-REPORT-REAL-MACHINE-0.2.0-audit-2026-10-26.md`. Телефон — S25 Ultra в домашней сети.

Что изменено (ASSUMPTIONS п. 251):
1. **Карточка «Tailscale» в панели** реже спрашивает программу `tailscale`. В прошлом отчёте
   открытая вкладка XGW стоила около 4 % ядра, из них ~2,5 % — запущенные программы: пока вкладка
   открыта, карточка раз в 10 секунд запускала `tailscale` четыре раза (одну и ту же команду —
   дважды). Теперь — три запуска раз в минуту, пока Tailscale работает и ничего не идёт; раз в
   10 секунд — только пока идут вход в Tailscale, включение Serve или Funnel. Кнопки карточки,
   как и раньше, обновляют её сразу.
2. **`xgw diag`** считает Ubuntu 24.04 проверенной системой, как 26.04: предупреждение
   «XGW проверялся только на Ubuntu 26.04» больше не появляется.

Здесь, у разработчика, проверены юнит-тесты (один запуск `serve status` на Serve и Funnel,
минута в покое, 10 секунд при входе, обновление по окончании фонового задания) и помощник этого
ТЗ на временной службе. Шлюз заказчика — эта программа.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list` и `nft -t list`), `ip`, `iptables`, `tc`, `sysctl -w`;
  команды `tailscale`, кроме той, что запускает помощник (`tailscale status --json`, он печатает
  только состояние).
- Править `/etc/xgw` (в том числе `config.toml` и `panel.json`), `/opt/xgw`, `/var/lib/xgw`,
  `/etc/systemd`, код XGW. Печатать `config.toml` (`cat`, `less`, `grep` по нему) — в нём ключи
  подписок. Серверы, переключатели и кнопки в панели (и в карточке «Tailscale») меняет и
  нажимает только заказчик. Коммитить что-либо, кроме отчёта (§6).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса и домены подписок, IP и домены серверов
  VPN. Можно: адреса устройств в домашней сети (`192.168.…`), названия и страны серверов,
  имена программ, счётчики, времена, проценты.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю, сколько стоит открытая вкладка XGW. По пунктам:
(1) Переустановка XGW с новым кодом: служба XGW перезапустится, интернет дома может пропасть
на несколько секунд.
(2) Вкладка XGW в браузере: по моей просьбе три раза по 2 минуты — вкладка открыта (сейчас, на
старом коде), все вкладки XGW закрыты, вкладка снова открыта (на новом коде). Все 6 минут
приложение XGW на телефоне не открывайте. Потом посмотрите на карточку «Tailscale» в панели
(ничего в ней не нажимая) и откроете любой сайт на этом компьютере и на телефоне.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против 2 — шаг 1.3 и §4 пропустить; в отчёте у пропущенного —
«не выполнялся».

Шаг 1.2. Папка, помощник проверки (только читает) и состояние до установки:

```bash
mkdir -p "$HOME/xgw-020d" && chmod 700 "$HOME/xgw-020d" && cd "$HOME/xgw-020d" && cat > v020dcheck.py <<'EOF'
"""XGW 0.2.0, нагрузка открытой вкладки: помощник. Только читает: /proc и cgroup службы xgw
(процессор и какие программы она запускает — только их имена), состояние Tailscale (только
BackendState), журнал со стандартного ввода (только счётчики). Режимы: cpu, ts, log."""
import json
import os
import subprocess
import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else ""


def show(unit, prop):
    return subprocess.run(["systemctl", "show", "-p", prop, "--value", unit],
                          capture_output=True, text=True).stdout.strip()


def comm(pid):
    try:
        return open(f"/proc/{pid}/comm", encoding="utf-8").read().strip()
    except OSError:
        return ""


if mode == "cpu":
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    unit = sys.argv[3] if len(sys.argv) > 3 else "xgw.service"
    pid = show(unit, "MainPID")
    group = f"/sys/fs/cgroup{show(unit, 'ControlGroup')}"
    tick = os.sysconf("SC_CLK_TCK")
    own = comm(pid)

    def fields():
        return open(f"/proc/{pid}/stat", encoding="ascii").read().rsplit(")", 1)[1].split()

    def ticks():
        values = fields()
        return (int(values[11]) + int(values[12])) / tick

    def usage():
        try:
            for line in open(f"{group}/cpu.stat", encoding="ascii"):
                name, _, value = line.partition(" ")
                if name == "usage_usec":
                    return int(value) / 1e6
        except OSError:
            return None
        return None

    uptime = float(open("/proc/uptime", encoding="ascii").read().split()[0])
    print(f"демон xgw работает: {int((uptime - int(fields()[19]) / tick) // 60)} мин")
    seen = {}
    start = time.monotonic()
    first, first_all = ticks(), usage()
    while time.monotonic() - start < seconds:
        try:
            current = open(f"{group}/cgroup.procs", encoding="ascii").read().split()
        except OSError:
            current = []
        for child in current:
            name = comm(child)
            if child != pid and name:
                seen[child] = name  # последнее имя — уже после exec
        time.sleep(0.005)
    used, used_all = ticks() - first, usage()
    spent_time = time.monotonic() - start
    print(f"процессор демона xgw (сам процесс): {used:.1f} с за {spent_time:.0f} с "
          f"({100 * used / spent_time:.1f} %)")
    if first_all is None or used_all is None:
        print(f"служба xgw целиком: нет {group}/cpu.stat")
    else:
        spent = used_all - first_all
        print(f"служба xgw целиком (с запущенными программами): {spent:.1f} с за "
              f"{spent_time:.0f} с ({100 * spent / spent_time:.1f} %)")
    counts = {"tailscale": 0}
    for name in seen.values():
        if name != own:  # пойман до exec и сразу вышел
            counts[name] = counts.get(name, 0) + 1
    print("запусков tailscale: " + str(counts.pop("tailscale")))
    others = ", ".join(f"{name} {count}" for name, count in
                       sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    print("других запусков: " + (others or "нет"))
elif mode == "ts":
    try:
        text = subprocess.run(["tailscale", "status", "--json"], capture_output=True,
                              text=True, timeout=15).stdout
    except FileNotFoundError:
        print("Tailscale: не установлен")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Tailscale: не ответил ({type(exc).__name__})")
    else:
        try:
            print(f"Tailscale: {json.loads(text).get('BackendState') or '?'}")
        except (ValueError, AttributeError):
            print("Tailscale: ответ не JSON")
elif mode == "log":
    lines = sys.stdin.read().splitlines()

    def count(text):
        return sum(1 for line in lines if text in line)

    print(f"строк журнала: {len(lines)}")
    print(f"правила загружены заново: {count('загружены заново')}")
    print(f"Traceback: {count('Traceback')}")
else:
    print("режим: cpu | ts | log")
EOF
sha256sum v020dcheck.py | cut -c1-16; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^sing-box' | tee before.txt; sudo python3 -I v020dcheck.py ts | tee -a before.txt; sudo xgw diag | grep -E 'Система:|Итог' | tee diag-before.txt
```

Ожидается:
- `be905fb48a22d2fc`;
- `Состояние: HEALTHY …`, `Перехват: включён …`, строка `sing-box …` (записать как есть);
- `Tailscale: Running`;
- строка `WARN … Система: Ubuntu 24.04.5 LTS, Python 3.12 — XGW проверялся только на Ubuntu
  26.04` и строка `Итог: OK — …, WARN — …, FAIL — …`. Записать обе.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать (это до установки) и продолжить. Вместо
`Running` другое состояние — записать и продолжить (в §4 тогда другой порог).

Шаг 1.3 (при согласии на пункт 2). Старый код, вкладка открыта. **Попроси заказчика**
(дословно):

«Откройте XGW значком в трее и оставьте вкладку на экране 2 минуты: окно не сворачивайте и на
другую вкладку не переключайтесь. Приложение XGW на телефоне не открывайте. Скажите, когда
открыли.»

После ответа:

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py cpu 120 | tee cpu-old-open.txt
```

Ожидается: «демон xgw работает: M мин», «процессор демона xgw (сам процесс): … (Y1 %)», «служба
xgw целиком …: … (Y2 %)», «запусков tailscale: T» — T не меньше 25 (старый код: 3–4 запуска
примерно раз в 12 секунд, за 2 минуты — 30–44), «других запусков: …». Записать M, Y1, Y2, T и
строку других запусков как есть (короткие программы вроде `ip` помощник видит не все — это
нормально).

Если не так: T меньше 25 — спросить заказчика, была ли вкладка XGW на экране все 2 минуты;
записать ответ и T и продолжить.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout panel-cpu && git pull --ff-only && git log -1 --format='%h %s' && grep -q '^__version__ = "0.2.0"' src/xgw/__init__.py && grep -q 'def serve_live' src/xgw/tailscale.py && grep -q '^TS_TTL = 60.0' src/xgw/watch/panel.py && grep -q '^TESTED_UBUNTU' src/xgw/diag.py && echo "правка в коде: есть"; cd "$HOME/xgw-020d"
```

Ожидается: «правка в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-020d/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-020d/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; grep -E 'выключены строки|перезапущен' "$HOME/xgw-020d/install.txt"; cd "$HOME/xgw-020d"
```

Ожидается: «код 0», «демон xgw запущен». Строк «выключены строки» и «перезапущен» быть не
должно: устаревшие строки config.toml выключены прошлой установкой, файлы служб ядер не
менялись. Есть — записать как есть (не дефект).

Если не так: код не 0 — **стоп**, сохранить вывод, сообщить заказчику (сеть не откатывать).

Шаг 2.3. Через 2 минуты — шлюз в порядке:

```bash
sleep 120; cd "$HOME/xgw-020d" && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee after-install.txt; sudo python3 -I v020dcheck.py ts | tee -a after-install.txt
```

Ожидается: `HEALTHY`, перехват включён, Xray отвечает, строка sing-box и `Tailscale: …` — как
до установки (§1.2). Записать.

Если не так: не `HEALTHY` — подождать 2 минуты, повторить; снова нет — записать `sudo xgw
status` целиком (без адресов серверов) и продолжить.

## 3. diag

```bash
cd "$HOME/xgw-020d" && sudo xgw diag | grep -E 'Система:|Итог' | tee diag-after.txt
```

Ожидается: строка `OK … Система: Ubuntu 24.04.5 LTS, Python 3.12` — без «проверялся только»;
`Итог: …, FAIL — 0`, WARN на 1 меньше, чем в §1.2 (если остальные проверки не изменились).
Записать обе строки.

Если не так: строка `Система` — по-прежнему WARN — **дефект «diag предупреждает об Ubuntu
24.04»**: записать строку. FAIL больше 0 — записать `sudo xgw diag | grep FAIL | tee
diag-fail.txt` (без адресов серверов и подписок).

## 4. Вкладка закрыта и открыта (при согласии на пункт 2)

Шаг 4.1. **Попроси заказчика** (дословно):

«Закройте все вкладки XGW в браузере (сам браузер можно не закрывать) и 2 минуты не открывайте;
приложение XGW на телефоне тоже не открывайте. Скажите, когда закрыли.»

После ответа:

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py cpu 120 | tee cpu-closed.txt
```

Ожидается: «запусков tailscale: 0». Записать M, Y1, Y2, T и строку других запусков.

Если не так: T больше 0 — спросить заказчика, не было ли открыто приложение XGW на телефоне или
вкладка XGW где-то ещё; записать ответ и T и продолжить (не дефект).

Шаг 4.2. **Попроси заказчика** (дословно):

«Откройте XGW значком в трее и оставьте вкладку на экране 2 минуты: окно не сворачивайте и на
другую вкладку не переключайтесь. Приложение XGW на телефоне не открывайте. Скажите, когда
открыли.»

После ответа:

```bash
cd "$HOME/xgw-020d" && sudo python3 -I v020dcheck.py cpu 120 | tee cpu-open.txt
```

Ожидается: «запусков tailscale: T», где T не больше 9 (новый код: 3 запуска примерно раз в
минуту). Если
в §2.3 было не `Tailscale: Running` — T не больше 40 (тогда карточка, как и раньше, обновляется
раз в 10 секунд). Записать M, Y1, Y2, T и строку других запусков; Y2 сравнить с §1.3.

Если не так: при `Tailscale: Running` T больше 12 — **дефект «карточка Tailscale по-прежнему
часто запускает tailscale»**: записать T и строку других запусков, сообщить заказчику и
продолжить. Y1 и Y2 — наблюдения, дефектов по ним нет (демон после установки моложе, чем в
§1.3).

Шаг 4.3. Не закрывая вкладку. **Попроси заказчика** (дословно):

«В панели XGW, в карточке «Tailscale» (ничего в ней не нажимайте): написано «Шлюз в tailnet:
к нему можно зайти с телефона и ноутбука…»? Список устройств и переключатели — такие же, как
обычно? И откройте любой сайт на этом компьютере и любой сайт на телефоне — открываются?»

Ожидается: «да» на все вопросы. Нет — записать ответ дословно, выполнить
`sudo python3 -I v020dcheck.py ts | tee card.txt` и сообщить заказчику: карточка не такая, как
обычно, — **дефект «карточка Tailscale изменилась»**; не открываются сайты — выполнить
`sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^Xray|^sing-box' | tee sites.txt`.

## 5. Итог

```bash
cd "$HOME/xgw-020d" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | sudo python3 -I v020dcheck.py log | tee final.txt; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|^sing-box' | tee -a final.txt
```

Ожидается: «Traceback: 0»; «правила загружены заново» — 0 или 1; `HEALTHY`, перехват включён,
sing-box — как до установки.

Если не так: Traceback больше 0 — записать
`sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -A15 Traceback | head -60 | tee traceback.txt`
(без адресов серверов и подписок).

## Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Не открываются сайты на всех устройствах — сообщить заказчику; сеть руками не трогать.
- Шлюз не `HEALTHY` — записать и продолжить.

## 6. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-panel-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`panel-cpu`), коммит «Отчёт: XGW 0.2.0, нагрузка открытой вкладки», `git push`. Шаблон:

```markdown
# Отчёт: XGW 0.2.0, нагрузка открытой вкладки

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
v020dcheck.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, sing-box, Tailscale, строка «Система» и итог diag |
| 1.3 старый код, вкладка открыта | — / не выполнялся | M, Y1, Y2, T |
| 2.2 установка | … | код, строки «выключены строки» / «перезапущен» |
| 2.3 после установки | … | HEALTHY, sing-box, Tailscale |
| 3 diag | … | строка «Система», итог до → после |
| 4.1 вкладка закрыта | … / не выполнялся | M, Y1, Y2, T |
| 4.2 вкладка открыта | … / не выполнялся | M, Y1, Y2, T (сравнение с 1.3) |
| 4.3 карточка и сайты | … / не выполнялся | ответы заказчика |
| 5 итог | … | Traceback, HEALTHY |

## Выводы шагов
<файлы $HOME/xgw-020d/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
