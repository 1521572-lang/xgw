# Программа испытаний XGW 0.1.14 на реальной машине

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Все выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§9).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, Docker, роутер HUAWEI AX2 за шлюзом. Стоит XGW
**0.1.13** в боевом режиме: от него работает интернет всего дома.

Что нового в 0.1.14 (по итогам испытаний 0.1.13, наблюдения 2–3):

- Шлюз пробует неответивший запасной сервер в других профилях обхода по лестнице: `[xray]` →
  `[xray+frag]` → `[sb]` → `[sb+frag]` (→ `[sb+mux]`). Раньше то, что сервер **сейчас на
  пробе**, демон помнил только в памяти. Если демон перезапускался посреди пробы, пробный
  профиль считался «выученным»: сервер оставался на неработающем профиле, а следующая лестница
  «возвращала» его туда же («возвращён «sing-box»» вместо «возвращён «Xray»»). Теперь проба
  записана в базе, и после перезапуска демон **продолжает её с той же ступени** (в журнале —
  строка «проба профиля «…» сервера «…» продолжается»).
- Отсчёт «следующая попытка через 6 ч» и «раз в сутки — проверка на базовом профиле» тоже
  записан в базе: после перезапуска демона лестница сервера, которому она недавно не помогла,
  не начинается заново.

Цели:

1. Поставить 0.1.14 (шаг 2), проверить службы (шаг 3).
2. **Главное:** остановить и запустить демон, **пока сервер на пробе профиля**, и проверить,
   что проба продолжена и закончилась правильно (шаг 4).
3. Проверить, что после перезапуска демона лестницы не начинаются заново раньше 6 ч (шаг 5),
   а ядра Xray и sing-box при этом не перезапускались.
4. Повторить экспорт журналов с исправленным поиском секретов (шаг 6): в 0.1.13 поиск ложно
   находил заглушку `vless://***` из комментария `config.toml`.

## 0. Запрещено

- `xgw net down`, `xgw uninstall`, `reboot`, `install.sh --force` — **никогда**.
- `flush ruleset`, ручные команды `nft`, `ip`, `iptables`, `sysctl -w` — **никогда**.
- Запускать `sing-box` и `xray` вручную, править их файлы, останавливать или перезапускать
  `xgw-xray` и `xgw-singbox`.
- Останавливать и запускать демон `xgw` где-либо, кроме команды шага 4.1.
- Править `/etc/xgw/config.toml` (в этой программе он не меняется вовсе).
- Открывать или скачивать адреса подписок (curl, браузер), копировать ссылки серверов.
- Править код XGW.
- Коммитить что-либо, кроме отчёта (§9). Файлы из `~/xgw-0.1.14-test` в Git **не класть**.
- Писать в отчёт: адреса подписок, UUID, пароли, ключи, токены, IP и домены серверов, свой
  внешний IP. Серверы называй по имени или тегу (`spare-nl-1a2b`).

Аварийный выход, если пропал интернет: `sudo xgw disable` (интернет пойдёт напрямую), затем
сообщить заказчику.

**Шаги 2–4 идут подряд без пауз**: пробы профилей идут в первые минуты после установки, и
шаг 4 должен их застать. Поэтому согласие заказчика берётся заранее, в шаге 1.1.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика:** «Обновлю XGW до 0.1.14. Сразу после обновления в течение часа
до трёх раз остановлю и запущу демон XGW (не ядра): интернет не пропадёт, панель и бот секунд на
десять станут недоступны. Можно?» Дождись согласия. Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p ~/xgw-0.1.14-test/before ~/xgw-0.1.14-test/after && chmod 700 ~/xgw-0.1.14-test && cd ~/xgw-0.1.14-test && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды выполняй из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без пароля
на время испытаний (как в прошлых испытаниях) — в шаге 4 команда ждёт до 40 минут и потом
вызывает sudo, ввести пароль будет некому.

Шаг 1.2. Снимок состояния до обновления:

```bash
sudo xgw --version; sudo xgw status > before/status.txt; sudo xgw servers > before/servers.txt; sudo xgw diag > before/diag.txt; tail -1 before/diag.txt
```

Ожидается: `xgw 0.1.13` и строка «Итог: OK — …, WARN — …, FAIL — 0».
Если не так (другая версия или FAIL не 0): записать в отчёт и спросить заказчика, продолжать ли.

Шаг 1.3. Скрипт, который показывает пробы, записанные в базе шлюза (только читает её).
Скопируй команду целиком (до строки `EOF` включительно):

```bash
cat > ~/xgw-0.1.14-test/trials.py <<'EOF'
"""Пробы профилей обхода в базе XGW 0.1.14 (только чтение).

sudo python3 trials.py                       что записано сейчас
sudo python3 trials.py --wait 2400           ждать, пока появится проба (не дольше 2400 с)
sudo python3 trials.py --json FILE           то же, что без ключей, и записать пробы в FILE
sudo python3 trials.py --until-gone FILE --wait 900   ждать, пока пробы из FILE закончатся
"""
import argparse, json, os, sqlite3, sys, time

ROOT = os.environ.get("XGW_ROOT", "")
DB = f"file:{ROOT}/var/lib/xgw/state.db?mode=ro"
INVENTORY = f"{ROOT}/var/lib/xgw/inventory.json"
NAMES = {"xray:default": "Xray", "xray:fragment": "Xray с дроблением ClientHello",
         "singbox:default": "sing-box", "singbox:tls_fragment": "sing-box с дроблением TLS",
         "singbox:mux_padded": "sing-box с мультиплексированием и паддингом"}


def read():
    conn = sqlite3.connect(DB, uri=True, timeout=10)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'profile_trials'").fetchone()
    finally:
        conn.close()
    saved = json.loads(row[0]) if row and row[0] else {}
    return saved.get("trials") or {}, saved.get("switched") or {}


def names():
    try:
        with open(INVENTORY, encoding="utf-8") as handle:
            servers = json.load(handle)["servers"]
    except (OSError, ValueError, KeyError) as exc:
        print(f"inventory.json не прочитан: {exc}")
        return {}
    return {item["fingerprint"]: item.get("name") or "" for item in servers}


def show(trials, switched):
    known = names()
    print(f"проб: {len(trials)}; таймеров (время смены профиля): {len(switched)}")
    for key, trial in trials.items():
        rest = " → ".join(NAMES.get(step, step) for step in trial["rest"]) or "—"
        recheck = " (суточная проверка на базовом)" if trial.get("recheck") else ""
        print(f"  «{known.get(key, '?')}» {key[:12]}: на пробе «{NAMES.get(trial['profile'])}», "
              f"до неё «{NAMES.get(trial['prev'])}», дальше: {rest}{recheck}")
    return known


parser = argparse.ArgumentParser()
parser.add_argument("--wait", type=float, default=0)
parser.add_argument("--json")
parser.add_argument("--until-gone")
args = parser.parse_args()
deadline = time.time() + args.wait
if args.until_gone:
    with open(args.until_gone, encoding="utf-8") as handle:
        watched = set(json.load(handle))
    while True:
        trials, switched = read()
        left = watched & set(trials)
        if not left or time.time() >= deadline:
            break
        time.sleep(5)
    show(trials, switched)
    print("пробы из файла закончились" if not left
          else f"пробы из файла не закончились за {args.wait:.0f} с: {len(left)}")
    sys.exit(0 if not left else 1)
while True:
    trials, switched = read()
    if trials or time.time() >= deadline:
        break
    time.sleep(2)
known = show(trials, switched)
if args.json:
    with open(args.json, "w", encoding="utf-8") as handle:
        json.dump({key: {**trial, "name": known.get(key, "?")} for key, trial in trials.items()},
                  handle, ensure_ascii=False, indent=1)
    os.chmod(args.json, 0o644)
sys.exit(0 if trials or not args.wait else 1)
EOF
python3 -c "import ast; ast.parse(open('$HOME/xgw-0.1.14-test/trials.py').read()); print('trials.py OK')"
```

Ожидается: `trials.py OK`.

Шаг 1.4. Скрипт проверки проб, прерванных перезапуском (понадобится в шаге 4.3):

```bash
cat > ~/xgw-0.1.14-test/check_resume.py <<'EOF'
"""Чем кончились пробы, прерванные остановкой демона (шаг 4): python3 check_resume.py"""
import json, re

NAMES = {"xray:default": "Xray", "xray:fragment": "Xray с дроблением ClientHello",
         "singbox:default": "sing-box", "singbox:tls_fragment": "sing-box с дроблением TLS",
         "singbox:mux_padded": "sing-box с мультиплексированием и паддингом"}
PROFILE = {name: profile for profile, name in NAMES.items()}
LABEL = {"xray:default": "xray", "xray:fragment": "xray+frag", "singbox:default": "sb",
         "singbox:tls_fragment": "sb+frag", "singbox:mux_padded": "sb+mux"}
EVENT = re.compile(r"(?:profile|fragment): «(.*?)» (.*)$")
STEP = re.compile(r"не отвечает на профиле «(.*?)» — пробую «(.*?)»")
FRAG_ON = "отвечает только с дроблением ClientHello — оно включено"
FRAG_OFF = "не отвечает и с дроблением ClientHello — оно выключено"
BACK_OFF = "отвечает и без дробления ClientHello — оно выключено"
BACK_ON = "без дробления ClientHello не отвечает — оно включено снова"

trials = json.load(open("after/trials-at-restart.json", encoding="utf-8"))
journal = open("after/journal-after-restart.txt", encoding="utf-8", errors="replace").read()
status = json.load(open("after/servers-after-trials.json", encoding="utf-8"))
now = {entry["fingerprint"]: entry for entry in status["members"] + status["spares"]}
events = [m.groups() for m in map(EVENT.search, journal.splitlines()) if m]
totals = {"ПРОЙДЕН": 0, "ДЕФЕКТ": 0, "НЕ ЗАВЕРШЕНА": 0, "ЗАПИСЬ СНЯТА": 0}
if not trials:
    print("в after/trials-at-restart.json проб нет — проверять нечего")
for key, trial in trials.items():
    name, trial_p, prev = trial["name"], trial["profile"], trial["prev"]
    steps = [trial_p, *trial["rest"]]
    good = [f"(был «{NAMES[prev]}»)", f"возвращён «{NAMES[prev]}»"]
    bad = [f"(был «{NAMES[trial_p]}»)", f"возвращён «{NAMES[trial_p]}»"]
    if {trial_p, prev} == {"xray:default", "xray:fragment"}:
        if prev == "xray:default":
            good, bad = good + [FRAG_ON, FRAG_OFF], bad + [BACK_OFF, BACK_ON]
        else:
            good, bad = good + [BACK_OFF, BACK_ON], bad + [FRAG_ON, FRAG_OFF]
    mine = [text for who, text in events if who == name]
    head = f"проба профиля «{NAMES[trial_p]}» сервера «{name}»"
    resumed = f"{head} продолжается" in journal
    dropped = f"{head} снята" in journal
    problems = [text for text in mine if any(item in text for item in bad)]
    for text in mine:
        step = STEP.search(text)
        if step and not {PROFILE.get(step.group(1)), PROFILE.get(step.group(2))} <= set(steps):
            problems.append(text)
    finished = any(item in text for text in mine for item in good)
    if problems:
        verdict = "ДЕФЕКТ"
    elif dropped:
        verdict = "ЗАПИСЬ СНЯТА"
    elif not resumed:
        verdict = "ДЕФЕКТ"
        problems.append("в журнале нет строки «… продолжается»")
    elif finished:
        verdict = "ПРОЙДЕН"
    else:
        verdict = "НЕ ЗАВЕРШЕНА"
    totals[verdict] += 1
    label = LABEL.get((now.get(key) or {}).get("profile"), "нет в списке")
    print(f"«{name}» {key[:12]}: проба «{NAMES[trial_p]}», до неё «{NAMES[prev]}»")
    print(f"  продолжена после перезапуска: {'да' if resumed else 'нет'}"
          + ("; запись снята (сервер ушёл с пробного профиля)" if dropped else ""))
    for text in mine:
        print(f"  событие: {text}")
    print(f"  метка сейчас: [{label}]")
    for text in problems:
        print(f"  ПРОБЛЕМА: {text}")
    print(f"  ИТОГ: {verdict}")
print("ВСЕГО: " + ", ".join(f"{key.lower()} {value}" for key, value in totals.items()))
EOF
python3 -c "import ast; ast.parse(open('$HOME/xgw-0.1.14-test/check_resume.py').read()); print('check_resume.py OK')"
```

Ожидается: `check_resume.py OK`.

Шаг 1.5. Скрипт проверки отсчёта 6 ч после перезапуска (понадобится в шаге 5.2):

```bash
cat > ~/xgw-0.1.14-test/check_timers.py <<'EOF'
"""Не начались ли лестницы заново после перезапуска демона (шаг 5): python3 check_timers.py"""
import json, re

EVENT = re.compile(r"(?:profile|fragment): «(.*?)» (.*)$")


def events(path):
    found = []
    for line in open(path, encoding="utf-8", errors="replace"):
        match = EVENT.search(line.rstrip("\n"))
        if match:
            found.append(match.groups())
    return found


trials = json.load(open("after/trials-at-restart.json", encoding="utf-8"))
skip = {trial["name"] for trial in trials.values()}
before = sorted({name for name, _text in events("after/journal-before-restart.txt")} - skip)
again = [(name, text) for name, text in events("after/journal-after-restart-20m.txt")
         if name in before]
print(f"серверов с событиями профиля до перезапуска (кроме тех, что были на пробе): {len(before)}")
for name in before:
    print(f"  «{name}»")
print(f"событий профиля у них после перезапуска: {len(again)} (ожидается 0)")
for name, text in again:
    print(f"  «{name}» {text}")
if not before:
    print("ИТОГ: проверять нечего — до перезапуска лестниц не было")
elif again:
    print("ИТОГ: ДЕФЕКТ — после перезапуска лестница пошла заново раньше чем через 6 ч")
else:
    print("ИТОГ: ПРОЙДЕН")
EOF
python3 -c "import ast; ast.parse(open('$HOME/xgw-0.1.14-test/check_timers.py').read()); print('check_timers.py OK')"
```

Ожидается: `check_timers.py OK`.

## 2. Установка 0.1.14

Шаг 2.1:

```bash
cd ~/xgw && git pull && git log -1 --format=%H && grep __version__ src/xgw/__init__.py && cd ~/xgw-0.1.14-test
```

(Если код лежит в другом каталоге — перейди в него вместо `~/xgw`.)
Ожидается: `__version__ = "0.1.14"`. Записать хеш.
Если версия другая: **стоп**, сообщить заказчику.

Шаг 2.2. Установка (из каталога кода). **Сразу после неё — шаги 3 и 4, без пауз.**

```bash
cd ~/xgw && date '+%F %T' | tee ~/xgw-0.1.14-test/install-time.txt && sudo sh packaging/install.sh --yes 2>&1 | tee ~/xgw-0.1.14-test/after/install.txt | tail -25; echo "код ${PIPESTATUS[0]}"; date '+%F %T' > ~/xgw-0.1.14-test/installed-time.txt; cd ~/xgw-0.1.14-test
```

Ожидается: «код 0». Время из `install-time.txt` — «время установки» в шагах ниже
(`installed-time.txt` — когда установка закончилась, его читает шаг 5.2).
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику.

Важно для чтения журнала: 0.1.13 пробы в базу не записывал. Если в момент установки какой-то
сервер был у 0.1.13 на пробе, 0.1.14 её продолжить не может, и в первые минуты после установки
у такого сервера может мелькнуть «возвращён «sing-box»» или «(был «sing-box»)». Это след
0.1.13, а не дефект 0.1.14: дефекты 0.1.14 определяют только проверки шагов 4.3 и 5.2.

## 3. Службы (быстро)

Шаг 3.1:

```bash
sudo xgw --version; systemctl is-active xgw-net xgw-xray xgw xgw-dhcp xgw-singbox; systemctl show xgw-xray xgw-singbox -p ExecMainStartTimestamp | tee after/cores-start.txt; sudo python3 trials.py
```

Ожидается: `xgw 0.1.14`, пять раз `active`, две строки `ExecMainStartTimestamp=…` — время
**раньше** времени установки (установка ядра не перезапускает), и строка «проб: N; таймеров
(время смены профиля): M» (сразу после установки обычно `проб: 0; таймеров: 0`: записи в
базе появляются, когда шлюз начинает пробовать профили).
Если `xgw` не `active`: **стоп**, `sudo journalctl -u xgw -n 40 --no-pager > after/xgw-fail.txt`,
сообщить заказчику.
Если `trials.py` пишет ошибку `no such table` или `unable to open database`: записать вывод в
отчёт и перейти к шагу 6 (шаги 4 и 5 без базы не проверить).

## 4. Перезапуск демона посреди пробы — главное

Шаг 4.1. Команда ждёт, пока какой-нибудь сервер окажется на пробе профиля (до 40 минут), сразу
останавливает демон, записывает, какие пробы были в базе в момент остановки, и запускает демон
снова. Копируй **целиком**:

```bash
if sudo python3 trials.py --wait 2400; then sudo systemctl stop xgw; sudo python3 trials.py --json after/trials-at-restart.json | tee after/trials-at-restart.txt; date '+%F %T' | tee restart-time.txt; sudo systemctl start xgw; sleep 5; systemctl is-active xgw; else echo "ПРОБ НЕ БЫЛО ЗА 40 МИНУТ"; fi
```

Ожидается: сначала блок «проб: 1 (или больше) …» со строками вида ««имя» 1a2b3c4d5e6f: на пробе
«Xray с дроблением ClientHello», до неё «Xray», дальше: sing-box → sing-box с дроблением TLS»;
затем второй такой блок (это пробы в момент остановки — он записан в
`after/trials-at-restart.txt`), время и `active`.

Если не так:

- «ПРОБ НЕ БЫЛО ЗА 40 МИНУТ»: шлюз за это время ни одного сервера не пробовал (все запасные
  отвечают). Записать в отчёт «шаги 4–5 не проверены: проб не было» и перейти к шагу 6.
- Во втором блоке «проб: 0»: проба успела закончиться, пока демон останавливался. Демон уже
  запущен снова. **Повтори шаг 4.1** (всего не больше трёх попыток; записать, сколько было).
  Если и после третьей «проб: 0» — записать «шаги 4–5 не проверены: пробы кончались раньше
  остановки» и перейти к шагу 6.
- Последняя строка не `active`: **стоп**, `sudo journalctl -u xgw -n 40 --no-pager >
  after/xgw-fail.txt`, сообщить заказчику.

Шаг 4.2. Дождаться, пока прерванные пробы закончатся (до 15 минут; обычно 1–3 минуты):

```bash
sudo python3 trials.py --until-gone after/trials-at-restart.json --wait 900 | tee after/trials-after.txt; date +%T
```

Ожидается: последняя строка перед временем — «пробы из файла закончились».
Если «не закончились за 900 с»: записать и всё равно перейти к шагу 4.3.

Шаг 4.3. Проверка:

```bash
R=$(cat restart-time.txt); sudo journalctl -u xgw --since "$R" --no-pager -o cat > after/journal-after-restart.txt; sudo xgw servers --json > after/servers-after-trials.json; grep -c 'продолжается' after/journal-after-restart.txt; python3 check_resume.py | tee after/check-resume.txt
```

Ожидается:

- первое число — 1 или больше (строки «проба профиля «…» сервера «…» продолжается (до неё был
  «…»)»);
- для каждого сервера блок со строкой «продолжена после перезапуска: да», событиями вида «не
  отвечает на профиле «…» — пробую «…»» и итоговым событием — «отвечает на профиле «…» — он
  закреплён (был «Xray»)» или «не отвечает ни на одном профиле — возвращён «Xray», следующая
  попытка через 6 ч» (в скобках и после «возвращён» — профиль **до** пробы, а не пробный);
- у каждого сервера «ИТОГ: ПРОЙДЕН», последняя строка «ВСЕГО: пройден N, дефект 0, …».

Если не так:

- «ИТОГ: ДЕФЕКТ»: записать в отчёт блок этого сервера целиком (строки «ПРОБЛЕМА» — главное) как
  дефект «проба, прерванная перезапуском демона, не продолжена»;
- «ИТОГ: НЕ ЗАВЕРШЕНА»: подождать 5 минут и повторить команду шага 4.3; если так и осталось —
  записать как есть;
- «ИТОГ: ЗАПИСЬ СНЯТА»: не дефект (сервер ушёл с пробного профиля — например, стал
  участником); записать и, если ни одного «ПРОЙДЕН» нет, сказать в отчёте, что проверка не
  состоялась.

## 5. Отсчёт 6 часов переживает перезапуск

Шаг 5.1. Ничего не трогать 15 минут: новый демон за это время заново проверяет все запасные.

```bash
sleep 900; date +%T
```

Шаг 5.2. Проверка:

```bash
T=$(cat installed-time.txt); R=$(cat restart-time.txt); sudo journalctl -u xgw --since "$T" --until "$R" --no-pager -o cat > after/journal-before-restart.txt; sudo journalctl -u xgw --since "$R" --no-pager -o cat > after/journal-after-restart-20m.txt; python3 check_timers.py | tee after/check-timers.txt; sudo python3 trials.py | head -1
```

Ожидается: «ИТОГ: ПРОЙДЕН» (или «ИТОГ: проверять нечего …» — тогда так и записать), затем
строка «проб: …; таймеров (время смены профиля): M» — M **не меньше**, чем «таймеров» во втором
блоке шага 4.1 (`after/trials-at-restart.txt`).
Если «ИТОГ: ДЕФЕКТ»: записать в отчёт строки с именами и событиями как дефект «после
перезапуска демона лестница пошла заново раньше 6 ч».
Если M меньше: записать оба числа (это не дефект, если сервер пропал из подписки; иначе —
дефект «таймеры потерялись при перезапуске»).

Шаг 5.3. Ядра не перезапускались — ни при установке, ни при остановке демона:

```bash
systemctl show xgw-xray xgw-singbox -p ExecMainStartTimestamp > after/cores-after.txt; diff after/cores-start.txt after/cores-after.txt && echo "ядра не перезапускались"; grep -c 'применено через API без перезапуска' after/journal-before-restart.txt after/journal-after-restart-20m.txt
```

Ожидается: «ядра не перезапускались» и два числа (смены профиля через API до и после
перезапуска).
Если `diff` показал разницу: записать обе строки в отчёт.

## 6. Экспорт журналов (повтор 0.1.13, исправлен поиск секретов)

Шаг 6.1:

```bash
sudo xgw logs --export --out ~/xgw-0.1.14-test/export.tgz | head -2; stat -c '%U:%G %a' ~/xgw-0.1.14-test/export.tgz; echo "я: $(id -un):$(id -gn)"
```

Ожидается: «архив без секретов: …», затем `user:user 600` — тот же пользователь и группа, что в
строке «я: …».

Шаг 6.2. Распаковка без sudo и поиск секретов. В 0.1.13 поиск ловил заглушку `vless://***` из
комментария `config.toml`; теперь схема ссылки считается находкой, только если за `://` идёт не
`*`:

```bash
mkdir -p ~/xgw-0.1.14-test/export && tar -xzf ~/xgw-0.1.14-test/export.tgz -C ~/xgw-0.1.14-test/export; echo "распаковка: код $?"; cd ~/xgw-0.1.14-test/export && echo "найдено: $(grep -rnE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|(vless|vmess|trojan|hysteria2|ss)://[^*[:space:],]|"password": "[^*]|"private_key": "[^*]|"secret": "[^*]' . | wc -l)"; echo "заглушек ***: $(grep -rnoE '(vless|vmess|trojan|ss)://\*\*\*' . | wc -l)"; cd ~/xgw-0.1.14-test
```

Ожидается: «распаковка: код 0», `найдено: 0`; «заглушек ***» — любое число (это замаскированные
ссылки, не секреты).
Если «найдено» больше 0 — **не копировать** найденное в отчёт; написать «найдены секреты в
<имя файла>» и сообщить заказчику сразу.

## 7. Итоговое состояние

Шаг 7.1:

```bash
systemctl is-active xgw-net xgw-xray xgw-singbox xgw xgw-dhcp; sudo xgw diag > after/diag.txt; tail -1 after/diag.txt; sudo xgw status | head -5; rm -rf ~/xgw-0.1.14-test/export ~/xgw-0.1.14-test/export.tgz
```

Ожидается: пять `active`, «FAIL — 0». Телефон и устройства заказчика — «через VPN».
Если FAIL не 0: записать строки с FAIL (`grep FAIL after/diag.txt`).

## 8. Что смотреть, если что-то пошло не так

- Пропал интернет — `sudo xgw disable`, сообщить заказчику (§0).
- Демон не запустился после шага 4.1 — **не повторять** шаг 4.1; `sudo systemctl start xgw`,
  `systemctl is-active xgw`; если не `active` — журнал в `after/xgw-fail.txt` и сообщить
  заказчику.
- Команда `xgw` пишет «ошибка» — сохранить вывод в `after/`, записать в отчёт, перейти к
  следующему шагу, если шаг не помечен «стоп».

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.14-<ГГГГ-ММ-ДД>.md` в репозитории. Заполни бланк:

```markdown
# Отчёт об испытаниях XGW 0.1.14 на реальной машине

Код: <хеш>. Установка: <время>, код <0/…>.

## Итог
<3–5 предложений: продолжилась ли проба после перезапуска демона и чем кончилась; не пошли ли
лестницы заново; перезапускались ли ядра>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 2 установка | пройден / нет | |
| 3 службы | пройден / нет | <проб и таймеров сразу после установки> |
| 4.1 остановка посреди пробы | пройден / не проверено | <попыток; сколько проб было в момент остановки> |
| 4.3 проба продолжена | пройден / дефект / не проверено | <строка «ВСЕГО» из check_resume> |
| 5.2 отсчёт 6 ч | пройден / дефект / нечего проверять | <ИТОГ из check_timers; таймеров до и после> |
| 5.3 ядра не перезапускались | пройден / нет | |
| 6 экспорт журналов | пройден / нет | <владелец архива, найдено секретов> |
| 7 итоговое состояние | пройден / нет | <FAIL — …> |

## Шаг 4 — пробы, прерванные перезапуском
<вывод after/trials-at-restart.txt (второй блок шага 4.1) и after/check-resume.txt целиком>

## Шаг 5 — отсчёт 6 ч
<вывод after/check-timers.txt>

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние машины
```

Перед коммитом проверь, что в отчёте нет секретов:

```bash
grep -nE '(vless|vmess|trojan|ss|hysteria2)://[^*]|[0-9a-f]{8}-[0-9a-f]{4}-|token|/sub/' docs/TEST-REPORT-REAL-MACHINE-0.1.14-*.md
```

Ожидается: пусто. Если что-то нашлось — убрать из отчёта.

Коммит только отчёта: `git add docs/TEST-REPORT-REAL-MACHINE-0.1.14-*.md && git commit -m
"Отчёт об испытаниях XGW 0.1.14 на реальной машине" && git push`.
