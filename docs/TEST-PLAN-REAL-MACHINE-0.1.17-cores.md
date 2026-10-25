# Программа испытаний XGW на реальной машине: обновление ядер из панели

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§10). Пути в командах — только абсолютные (`$HOME/xgw-cores-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома. Стоит XGW с кодом ветки `android-a3`
(версия 0.1.17) на Xray 26.10.21 и sing-box 1.14.3; Tailscale подключён, телефон заказчика
привязан к приложению XGW. Клон репозитория — `~/zcod/xgw`. Номер версии XGW новый код не
меняет (`xgw 0.1.17`).

Что изменилось (ASSUMPTIONS п. 234, ветка `cores-update`):

1. **Проверка выпусков на GitHub.** Раз в сутки (и по кнопке «Проверить сейчас») шлюз смотрит
   выпуски Xray (и предварительные) и sing-box (только стабильные) и показывает в новой
   карточке панели «Ядра»: «На GitHub есть …» с кнопкой «Обновить до …».
2. **Обновление с проверкой и самовозвратом.** Новое ядро скачивается со сверкой SHA-256,
   проверяется на рабочем конфиге (`xray run -test` / `sing-box check`), ставится, ядро
   перезапускается; должен ответить API ядра и пройти запрос в интернет через серверы. Не
   прошло — прежняя версия возвращается сама. Прошло — версия «принята шлюзом»: `xgw diag`
   её не считает ошибкой.
3. **Кнопка «Вернуть X.Y.Z».** Прежний бинарник лежит рядом (`/opt/xgw/xray.prev`); кнопка
   возвращает его. Сутки после обновления шлюз сам вернёт прежнее ядро, если новое перестанет
   отвечать (этот случай здесь не воспроизводится — §10, «Что не проверено»).
4. **Служба `xgw-core`.** Файлы ядер меняет отдельная служба (Type=oneshot, не включается):
   у демона `/opt/xgw` только для чтения. Её ставит переустановка.

Цели:

1. Снимок до обновления, копия ядер для ручного отката (шаг 1.3).
2. Новый код и служба `xgw-core` (шаг 2).
3. Карточка «Ядра» и проверка выпусков на настоящем GitHub (шаг 3).
4. Служба `xgw-core` на заведомо отсутствующем выпуске: ничего не меняет (шаг 4).
5. Настоящее обновление Xray через службу (шаг 5) и возврат кнопкой в панели (шаг 6).
6. sing-box — если на GitHub есть выпуск новее 1.14.3 (шаг 7).
7. Журнал и итог (шаг 8), отчёт (§10).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**.
- `sudo xgw update-xray` и `sudo xgw update-singbox` — не запускать (они ставят проверенную
  версию и сбросили бы то, что проверяется).
- Команды Tailscale, кроме `tailscale status`; Funnel, Serve и SSH не трогать.
- Запуск, остановка и перезапуск `tailscaled`, `xgw`, `xgw-xray`, `xgw-singbox`, `xgw-net`,
  `xgw-dhcp`, `systemd-resolved`, NetworkManager, `ssh`/`sshd` — кроме §9 (откат).
  Служба `xgw-core` запускается только командами из шагов 4 и 5.
- Ручные команды `nft` (кроме `nft list`), `ip` (кроме `ip … show`), `iptables`,
  `sysctl -w`.
- Отключать WAN или LAN, кабели, Wi-Fi роутера.
- Править `/etc/xgw/config.toml`, `/etc/xgw/panel.json`, `/etc/systemd`, файлы в `/opt/xgw`
  и `/var/lib/xgw` (кроме §9). Файл задания `/run/xgw/core-request.json` пишется только
  командами шагов 4 и 5.
- Нажимать в панели или приложении что-либо, кроме того, что написано в шагах.
- Править код XGW. Коммитить что-либо, кроме отчёта (§10). Файлы из `~/xgw-cores-test` в Git
  **не класть**.
- Писать в отчёт: адреса tailnet (`100.x.y.z`), имена `*.ts.net`, имена устройств и
  пользователей, почту, внешние IP, токены (в том числе токен панели), адреса подписок, UUID,
  IP и домены серверов VPN, MAC-адреса. Внутренние подсети (`192.168.x.0/24`), коды стран и
  версии ядер — можно.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю новую функцию шлюза — обновление ядер Xray и sing-box из панели с возвратом
прежней версии. По пунктам:
(1) Переустановка XGW с новым кодом: Xray перезапустится — интернет дома пропадёт на
несколько секунд, панель секунд на десять недоступна.
(2) Шлюз спросит у GitHub список выпусков Xray и sing-box (несколько запросов к
api.github.com).
(3) Проверка службы обновления на выпуске, которого нет на GitHub: ничего не скачивается и
не меняется.
(4) Обновление Xray: если на GitHub есть выпуск новее 26.10.21 — до него; если нет — для
проверки механизма шлюз временно поставит прежний стабильный Xray 26.3.27. Это около 15 МБ
с GitHub; интернет дома дважды пропадёт на несколько секунд (обновление и возврат), шлюз
поработает на этой версии несколько минут.
(5) Попрошу вас нажать в панели кнопку „Вернуть 26.10.21“.
(6) Если на GitHub есть sing-box новее 1.14.3 — то же для него (около 20 МБ), с возвратом.
(7) Скачаю через VPN шлюза файл 20 МБ, чтобы проверить трафик на новом ядре.
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против пункта 2 — шаг 3.2 пропустить; шаги 5–7 тогда тоже пропустить (не будет известно,
  что есть на GitHub).
- Против пункта 3 — шаг 4 пропустить.
- Против пункта 4 — шаги 5 и 6 пропустить; против пункта 5 — шаг 6.1 выполнить самому
  (вариант «если заказчик не может» в шаге 6.1).
- Против пункта 6 — шаг 7 пропустить; против пункта 7 — шаг 5.4 пропустить.

Шаг 1.2. Каталог испытания и вспомогательный скрипт `corecheck.py` (делает то же, что
кнопки карточки «Ядра»: читает её и нажимает «Проверить сейчас», «Обновить», «Вернуть»).
Скопируй блок **целиком**, от первой строки до последней:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-cores-test/before" "$HOME/xgw-cores-test/after" && chmod 700 "$HOME/xgw-cores-test" && cat > "$HOME/xgw-cores-test/corecheck.py" <<'PY'
"""Испытание обновления ядер XGW: то же, что кнопки карточки «Ядра» в панели (только чтение,
кроме команд check, update и rollback). Запуск: sudo python3 corecheck.py <команда>.

  card                 — карточка «Ядра»: версии, выпуски на GitHub, прежняя версия, задание
  check                — «Проверить сейчас» и дождаться итога (до 120 с)
  update ЯДРО ВЕРСИЯ   — «Обновить до ВЕРСИЯ» (ядро: xray или sing-box) и дождаться итога
  rollback ЯДРО        — «Вернуть …» и дождаться итога
  wait [СЕКУНД]        — дождаться конца задания, начатого кнопкой в панели (до 600 с)
  events               — последние события об ядрах и откатах
"""

import hashlib
import hmac
import http.client
import json
import sys
import time
import tomllib

PORT, TOKEN = 8781, ""
for arg in list(sys.argv[1:]):
    if arg.startswith("--port="):
        PORT = int(arg.split("=", 1)[1])
        sys.argv.remove(arg)
    elif arg.startswith("--token="):
        TOKEN = arg.split("=", 1)[1]
        sys.argv.remove(arg)
if not TOKEN:
    with open("/etc/xgw/config.toml", "rb") as handle:
        PORT = int(tomllib.load(handle).get("panel", {}).get("port", PORT))
    with open("/var/lib/xgw/panel-token", encoding="utf-8") as handle:
        TOKEN = handle.read().strip()
COOKIE = "xgw_panel=" + hmac.new(TOKEN.encode(), b"xgw-panel", hashlib.sha256).hexdigest()
HOST = f"127.0.0.1:{PORT}"


def request(method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    headers = {"Host": HOST, "Cookie": COOKIE}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers.update({"Content-Type": "application/json", "X-XGW-Panel": "1",
                        "Origin": f"http://{HOST}"})
    conn.request(method, path, body=data, headers=headers)
    response = conn.getresponse()
    text = response.read().decode("utf-8", "replace")
    conn.close()
    if response.status != 200:
        sys.exit(f"панель ответила HTTP {response.status}: {text.strip()[:200]}")
    return json.loads(text)


def stamp(ts):
    return time.strftime("%d.%m %H:%M:%S", time.localtime(float(ts))) if ts else "—"


def card(state=None):
    state = state or request("GET", "/api/state")
    cores = state.get("cores") or {}
    print(f"состояние шлюза: {state.get('state')}")
    for row in cores.get("rows") or []:
        origin = ("принята шлюзом" if row.get("accepted")
                  else "проверена XGW" if row.get("installed") == row.get("baseline")
                  else f"другая (XGW проверен на {row.get('baseline')})")
        print(f"{row['title']}: установлен {row.get('installed') or '—'} ({origin})")
        latest = row.get("latest")
        print("  на GitHub: " + (f"{latest['version']}"
                                 + (" (предварительный выпуск)" if latest.get("prerelease") else "")
                                 if latest else "новее нет"))
        print(f"  прежняя версия: {row.get('previous') or 'нет'}")
        print(f"  наблюдение до: {stamp(row.get('watch_until'))}")
        print(f"  убрана с GitHub: {'да' if row.get('withdrawn') else 'нет'}")
        rejected = row.get("rejected")
        if rejected:
            word = "убрана" if rejected.get("kind") == "rollback" else "не прошла проверку"
            print(f"  {word}: {rejected.get('version')} — {rejected.get('reason')}")
    print(f"выпуски проверены: {stamp(cores.get('checked'))}"
          + (f", ошибка: {cores['error']}" if cores.get("error") else ", ошибок нет"))
    job = cores.get("job") or {}
    print(f"задание идёт: {'да' if cores.get('active') else 'нет'}")
    if job:
        print(f"последнее задание: {job.get('action')} {job.get('core')} {job.get('version') or ''}"
              f" — {job.get('state')}, начато {stamp(job.get('started'))}, "
              f"кончено {stamp(job.get('finished'))}")
        print(f"  итог: {job.get('text') or job.get('stage') or '—'}")
    return state


def act(name, body):
    result = request("POST", f"/api/{name}", body)
    print(f"ответ панели: {'принято' if result.get('ok') else 'отказ'} — {result.get('text')}")
    return result


def wait(seconds, start):
    stage = None
    deadline = time.time() + seconds
    while time.time() < deadline:
        cores = request("GET", "/api/state").get("cores") or {}
        job = cores.get("job") or {}
        if job.get("stage") and job.get("stage") != stage:
            stage = job["stage"]
            print(f"{time.strftime('%H:%M:%S')} этап: {stage}")
        finished = float(job.get("finished") or 0)
        if not cores.get("active") and finished >= start - 5:
            print(f"{time.strftime('%H:%M:%S')} задание кончилось: {job.get('state')}")
            print(f"итог: {job.get('text')}")
            return 0 if job.get("state") == "ok" else 1
        time.sleep(3)
    print(f"задание не кончилось за {seconds} с")
    return 2


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    command, rest = sys.argv[1], sys.argv[2:]
    if command == "card":
        card()
    elif command == "check":
        act("cores/check", {})
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(3)
            state = request("GET", "/api/state")
            if not (state.get("busy") or {}).get("cores"):
                card(state)
                return 0
        print("проверка не кончилась за 120 с")
        return 2
    elif command in ("update", "rollback") and len(rest) == (2 if command == "update" else 1):
        start = time.time()
        body = {"core": rest[0], **({"version": rest[1]} if command == "update" else {})}
        if not act(f"cores/{command}", body).get("ok"):
            return 1
        return wait(900, start)
    elif command == "wait":
        return wait(int(rest[0]) if rest else 600, time.time() - 600)
    elif command == "events":
        kinds = {"cores", "rollback", "xray", "XRAY_DOWN", "singbox"}
        for event in reversed(request("GET", "/api/state").get("events") or []):
            detail = event.get("detail") or ""
            if event.get("kind") in kinds or (event.get("kind") == "panel" and (
                    "Xray" in detail or "sing-box" in detail)):
                print(f"{stamp(event.get('ts'))} [{event.get('kind')}] {detail}")
    else:
        sys.exit(__doc__)
    return 0


sys.exit(main())
PY
cd "$HOME/xgw-cores-test" && sha256sum corecheck.py && date
```

Ожидается: «sudo без пароля: да»; строка
`ea9dd714c3d03b994c972974503b28ba079915d4c8447509181614e6d49fd986  corecheck.py`; дата. Дальше все команды выполняй из этого каталога.

Если не так: строки «sudo без пароля: да» нет — **стоп**, попросить заказчика разрешить sudo
без пароля на время испытаний. Хеш другой — блок скопирован не целиком: удали файл
(`rm "$HOME/xgw-cores-test/corecheck.py"`) и повтори шаг 1.2; снова другой — **стоп**,
сообщить заказчику.

Шаг 1.3. Снимок до обновления и копия ядер (для ручного отката, §9):

```bash
cd "$HOME/xgw-cores-test" && sudo xgw --version; sudo /opt/xgw/xray/xray version | head -1 | tee "$HOME/xgw-cores-test/before/xray.txt"; sudo /opt/xgw/sing-box/sing-box version 2>&1 | head -1 | tee "$HOME/xgw-cores-test/before/singbox.txt"; ls -d /opt/xgw/xray* /opt/xgw/sing-box* 2>&1 | tee "$HOME/xgw-cores-test/before/dirs.txt"; sudo xgw diag > "$HOME/xgw-cores-test/before/diag.txt"; tail -1 "$HOME/xgw-cores-test/before/diag.txt"; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | tee "$HOME/xgw-cores-test/before/state.txt"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled | tee "$HOME/xgw-cores-test/before/services.txt"; sudo mkdir -p "$HOME/xgw-cores-test/backup" && sudo cp -a /opt/xgw/xray "$HOME/xgw-cores-test/backup/xray" && echo "копия Xray: есть"; test -d /opt/xgw/sing-box && sudo cp -a /opt/xgw/sing-box "$HOME/xgw-cores-test/backup/sing-box" && echo "копия sing-box: есть"
```

Ожидается: `xgw 0.1.17`; «Xray 26.10.21 …»; «sing-box version 1.14.3» (или «No such file» —
sing-box не установлен, записать); каталоги `/opt/xgw/xray` и `/opt/xgw/sing-box`, без
`.prev` и `.new`; «FAIL — 0»; состояние `HEALTHY` или `DEGRADED` (записать); службы `active`
(у `xgw-singbox` допустимо `inactive` — записать); «копия Xray: есть» (и «копия sing-box:
есть», если sing-box установлен).

Если не так: FAIL не 0 — записать как есть и **спросить заказчика**, продолжать ли. Нет
строки «копия Xray: есть» — **стоп**, сообщить заказчику.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout cores-update && git pull --ff-only && git log -1 --format='%h %s' && test -f packaging/xgw-core.service && grep -q 'def run_request' src/xgw/cores.py && echo "обновление ядер в коде: есть"; grep __version__ src/xgw/__init__.py; cd "$HOME/xgw-cores-test"
```

Ожидается: «обновление ядер в коде: есть» и `__version__ = "0.1.17"`. Записать хеш.
Если ветки `cores-update` нет или строки «обновление ядер в коде: есть» нет: **стоп**,
сообщить заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-cores-test/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-cores-test/after/install.txt" | tail -25; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-cores-test"
```

Ожидается: «код 0» и «демон xgw запущен». Xray заново не скачивается (строки «Xray-core v… —
/opt/xgw/xray» нет): он уже нужной версии.

Если код не 0: **стоп**, сохранить вывод, сообщить заказчику (сеть и ядра не тронуты).

Шаг 2.3. Служба `xgw-core` на месте и не включена:

```bash
systemctl cat xgw-core.service | grep -E '^(ExecStart|Type|ReadWritePaths|ConditionPathExists)=' | tee "$HOME/xgw-cores-test/after/unit.txt"; echo "включена: $(systemctl is-enabled xgw-core.service)"; echo "состояние: $(systemctl is-active xgw-core.service)"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled
```

Ожидается: четыре строки — `Type=oneshot`, `ExecStart=/usr/local/bin/xgw cores run-job`,
`ReadWritePaths=/opt/xgw /var/lib/xgw -/run/xgw`,
`ConditionPathExists=/run/xgw/core-request.json`; «включена: static»; «состояние:
inactive»; службы — как в шаге 1.3.

Если не так: `systemctl cat` пишет «No files found» — **дефект «служба xgw-core не
установлена»**, записать; шаги 4–7 пропустить, выполнить шаг 8.

Шаг 2.4. Шлюз здоров (ждать до 5 минут):

```bash
for i in $(seq 30); do sudo xgw status 2>&1 | grep -q '^Состояние: HEALTHY' && break; sleep 10; done; date '+%T'; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | tee "$HOME/xgw-cores-test/after/state-install.txt"; sudo xgw diag > "$HOME/xgw-cores-test/after/diag-install.txt"; tail -1 "$HOME/xgw-cores-test/after/diag-install.txt"
```

Ожидается: состояние — как в шаге 1.3 (или лучше), «Перехват: включён — …», «FAIL — 0».

Если состояние хуже, чем в шаге 1.3: записать `sudo xgw status 2>&1 | head -30` (без
адресов серверов) и **спросить заказчика**, продолжать ли.

## 3. Карточка «Ядра» и выпуски на GitHub

Шаг 3.1. Карточка:

```bash
cd "$HOME/xgw-cores-test" && sudo python3 corecheck.py card | tee "$HOME/xgw-cores-test/after/card-1.txt"
```

Ожидается: строка «Xray: установлен 26.10.21 (проверена XGW)»; строка sing-box — «sing-box:
установлен 1.14.3 (проверена XGW)» (её нет, если sing-box не установлен); у обоих «прежняя
версия: нет», «наблюдение до: —»; «задание идёт: нет». Строка «выпуски проверены» — время или
«—» (первая проверка идёт через 5 минут после запуска демона).

Если не так: «панель ответила HTTP …» — записать строку и **стоп**, сообщить заказчику.

Шаг 3.2 (при согласии на пункт 2). «Проверить сейчас»:

```bash
cd "$HOME/xgw-cores-test" && sudo python3 corecheck.py check | tee "$HOME/xgw-cores-test/after/card-check.txt"; sudo python3 -c "import json; d = json.load(open('/var/lib/xgw/cores-check.json')); print({k: d[k] for k in ('xray', 'sing-box') if k in d})" | tee -a "$HOME/xgw-cores-test/after/card-check.txt"
```

Ожидается: «ответ панели: принято — Проверяю выпуски Xray и sing-box на GitHub…»; затем
карточка: «выпуски проверены: <сейчас>, ошибок нет»; у Xray — «на GitHub: X.Y.Z …» или «на
GitHub: новее нет»; у sing-box — так же. Последняя строка — словарь с полями `installed`,
`latest`, `withdrawn`, `error` (записать как есть). «убрана с GitHub: нет» у обоих.

Если не так:

- «ошибка: …» — подожди 1 минуту и повтори шаг один раз. Снова ошибка — **дефект «проверка
  выпусков на GitHub не работает»**: записать текст ошибки (адресов серверов в нём нет).
  Шаги 5–7 пропустить.
- «убрана с GitHub: да» у Xray или sing-box — не дефект: разработчики убрали установленную
  версию. Записать и **сообщить заказчику** сразу (это повод обновить ядро).

Запиши, что нашлось: «Xray на GitHub: …», «sing-box на GitHub: …» — от этого зависят шаги 5
и 7.

Шаг 3.3. **Попроси заказчика**: «Откройте панель XGW (ярлык „XGW“) и найдите карточку „Ядра“
(в левой колонке внизу, на узком окне — в самом конце). Что в ней написано у Xray и у
sing-box? Есть ли кнопки „Обновить до …“ и „Проверить сейчас“?» Записать ответ.

Ожидается: те же версии, что в шаге 3.2; кнопка «Обновить до …» — только там, где в шаге 3.2
нашёлся выпуск новее; «Проверить сейчас» — есть. Карточки нет — **дефект «карточки „Ядра“
нет в панели»** (попроси обновить страницу один раз, Ctrl+F5).

## 4. Служба `xgw-core` на выпуске, которого нет (при согласии на пункт 3)

Шаг 4.1. Задание «обновить Xray до 26.10.10» (разработчики Xray убрали этот выпуск с GitHub
21.10.2026 — загрузка должна не пройти, а Xray остаться прежним):

```bash
cd "$HOME/xgw-cores-test" && echo '{"core": "xray", "action": "update", "version": "26.10.10", "reason": "test"}' | sudo tee /run/xgw/core-request.json > /dev/null && sudo chmod 600 /run/xgw/core-request.json && sudo systemctl start xgw-core.service; echo "код systemctl $?"; echo "состояние службы: $(systemctl is-active xgw-core.service)"; sudo python3 corecheck.py card | tee "$HOME/xgw-cores-test/after/card-404.txt" | tail -4; sudo /opt/xgw/xray/xray version | head -1; ls -d /opt/xgw/xray* ; test -e /run/xgw/core-request.json && echo "файл задания остался" || echo "файл задания убран"
```

Ожидается: «код systemctl 0»; «состояние службы: inactive» (не `failed`); «задание идёт:
нет»; «последнее задание: update xray 26.10.10 — failed …»; итог «Xray 26.10.10 не загружен:
… HTTP 404 …. Стоит прежний 26.10.21»; «Xray 26.10.21 …»; только `/opt/xgw/xray`; «файл
задания убран».

Если не так:

- Итог «не загружен: … таймаут / не удалось подключиться …» (без «404») — запись как
  **наблюдение** «GitHub недоступен из службы»: служба работает, но сеть до GitHub из неё не
  прошла; шаги 5–7 пропустить, выполнить шаг 8.
- «состояние службы: failed» или «последнее задание» не про 26.10.10 — **дефект «служба
  xgw-core не выполняет задание»**: записать
  `sudo journalctl -u xgw-core.service --no-pager | tail -30` (проверь глазами, что адресов
  серверов нет). Шаги 5–7 пропустить.
- Версия Xray не 26.10.21 или есть `/opt/xgw/xray.new` / `xray.prev` — **дефект «задание
  тронуло ядро при неудачной загрузке»**: выполнить §9 (Xray), сообщить заказчику.

## 5. Обновление Xray (при согласии на пункт 4)

Шаг 5.1. Выбор выпуска — по шагу 3.2:

- **Вариант А.** У Xray «на GitHub: X.Y.Z» (новее 26.10.21) — обновление идёт кнопкой
  панели (тот же запрос, что кнопка «Обновить до X.Y.Z»). Подставь найденную версию вместо
  `X.Y.Z`:

  ```bash
  cd "$HOME/xgw-cores-test" && date '+%F %T' | tee "$HOME/xgw-cores-test/update-time.txt" && sudo python3 corecheck.py update xray X.Y.Z | tee "$HOME/xgw-cores-test/after/update.txt"
  ```

- **Вариант Б.** У Xray «на GitHub: новее нет» — панель предлагать нечего, поэтому задание
  кладётся службе напрямую: временно поставить стабильный 26.3.27 (он старше, но XGW с ним
  работает; конфиг XGW 26.3.27 принимает):

  ```bash
  cd "$HOME/xgw-cores-test" && date '+%F %T' | tee "$HOME/xgw-cores-test/update-time.txt" && echo '{"core": "xray", "action": "update", "version": "26.3.27", "reason": "test"}' | sudo tee /run/xgw/core-request.json > /dev/null && sudo chmod 600 /run/xgw/core-request.json && sudo systemctl start xgw-core.service; echo "код systemctl $?"; sudo python3 corecheck.py card | tee "$HOME/xgw-cores-test/after/update.txt" | tail -4
  ```

Дальше `НОВАЯ` — это X.Y.Z (вариант А) или 26.3.27 (вариант Б).

Ожидается:

- вариант А: «ответ панели: принято — Обновляю Xray до НОВАЯ…», затем этапы «скачиваю Xray
  НОВАЯ с GitHub», «проверяю Xray НОВАЯ на рабочем конфиге», «ставлю Xray НОВАЯ и
  перезапускаю», «проверяю запрос через серверы с Xray НОВАЯ» (быстрые этапы могут не
  попасть в вывод), «задание кончилось: ok»;
- вариант Б: «код systemctl 0», «последнее задание: update xray 26.3.27 — ok …»;
- итог в обоих: «Xray обновлён: 26.10.21 → НОВАЯ, проверки пройдены. Сутки шлюз следит за
  ним и вернёт 26.10.21 сам, если ядро перестанет отвечать. …».

Если не так:

- «задание кончилось: failed» / «— failed» с итогом «… не подходит — …» или «… не прошёл
  проверку: … — возвращён прежний 26.10.21» — **это сработала защита**, а не сбой: записать
  итог целиком, выполнить шаг 5.3 (Xray должен быть 26.10.21 и работать), шаг 6 пропустить,
  перейти к шагу 7.
- «не загружен: …» — записать итог; шаги 5.2–6 пропустить, перейти к шагу 7.
- «задание не кончилось за 900 с» — **стоп**: выполнить
  `systemctl status xgw-core.service --no-pager | head -15`, записать, **сообщить
  заказчику**; при пропаже интернета — §9 (Xray).
- Интернет дома пропал больше чем на минуту — §9 (Xray), сообщить заказчику.

Шаг 5.2. Работает новое ядро, прежнее лежит рядом:

```bash
cd "$HOME/xgw-cores-test" && PID=$(systemctl show -p MainPID --value xgw-xray); echo "процесс Xray: $(sudo readlink /proc/$PID/exe)"; sudo /opt/xgw/xray/xray version | head -1; sudo /opt/xgw/xray.prev/xray version | head -1; ls -d /opt/xgw/xray*; sudo xgw diag > "$HOME/xgw-cores-test/after/diag-updated.txt"; tail -1 "$HOME/xgw-cores-test/after/diag-updated.txt"; grep -E '^\S+ +Xray ' "$HOME/xgw-cores-test/after/diag-updated.txt" | head -2
```

Ожидается: «процесс Xray: /opt/xgw/xray/xray» — **без** `(deleted)`; «Xray НОВАЯ …»; вторая
версия — «Xray 26.10.21 …» (прежняя); каталоги `/opt/xgw/xray` и `/opt/xgw/xray.prev`, без
`.new` и `.prev.old`; «FAIL — 0»; строка Xray — OK «версия НОВАЯ — обновлена из панели и
проверена шлюзом …».

Если не так: `(deleted)` — **дефект «Xray не перезапущен после обновления»**; Xray FAIL —
записать строку целиком. В обоих случаях — шаг 6 (возврат) всё равно выполнить.

Шаг 5.3. Шлюз здоров, демон не мешал заданию (ждать до 3 минут):

```bash
cd "$HOME/xgw-cores-test" && for i in $(seq 18); do sudo xgw status 2>&1 | grep -q '^Состояние: HEALTHY' && break; sleep 10; done; date '+%T'; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | tee "$HOME/xgw-cores-test/after/state-updated.txt"; sudo python3 corecheck.py card | tee "$HOME/xgw-cores-test/after/card-updated.txt" | head -6; sudo python3 corecheck.py events | tail -8 | tee "$HOME/xgw-cores-test/after/events-updated.txt"
```

Ожидается: состояние — как в шаге 1.3, «Xray НОВАЯ: …», «Перехват: включён»; карточка:
«Xray: установлен НОВАЯ (принята шлюзом)», «прежняя версия: 26.10.21», «наблюдение до:
<завтра, примерно это время>»; в событиях — `[cores] Xray обновлён: 26.10.21 → НОВАЯ …` и
**нет** событий `[rollback]` после времени из `update-time.txt`. Одно событие `[XRAY_DOWN]`
на время перезапуска и возврат в прежнее состояние — допустимы (записать).

Если не так: событие `[rollback]` после обновления — **дефект «демон откатил конфиг во время
обновления ядра»**: записать события. Состояние хуже, чем в шаге 1.3, дольше 3 минут —
записать и перейти к шагу 6 (возврат).

Шаг 5.4 (при согласии на пункт 7). Трафик самой машины через новое ядро:

```bash
curl -s -o /dev/null --max-time 90 -w 'загрузка: код %{http_code}, %{size_download} байт за %{time_total} с\n' 'https://speed.cloudflare.com/__down?bytes=20000000' | tee "$HOME/xgw-cores-test/after/machine.txt"; echo "страна выхода: $(curl -s --max-time 20 https://ipinfo.io/country)" | tee -a "$HOME/xgw-cores-test/after/machine.txt"
```

Ожидается: «загрузка: код 200, 20000000 байт за N с»; «страна выхода: XX» — страна сервера
VPN, не машины.

Если не так: код не 200 — повторить один раз; снова не так — **дефект «трафик через новое
ядро не идёт»** (записать) и сразу шаг 6. Страна выхода — страна машины: записать как
**наблюдение**.

## 6. Возврат прежней версии кнопкой

Шаг 6.1 (при согласии на пункт 5). **Попроси заказчика**: «В панели XGW, в карточке „Ядра“, в
строке Xray нажмите „Вернуть 26.10.21“, в окне — „Вернуть“. Что написано в карточке через
полминуты?» Сразу после просьбы выполни:

```bash
cd "$HOME/xgw-cores-test" && sudo python3 corecheck.py wait 300 | tee "$HOME/xgw-cores-test/after/rollback.txt"
```

Если заказчик не может (или не согласился на пункт 5) — вместо этого:

```bash
cd "$HOME/xgw-cores-test" && sudo python3 corecheck.py rollback xray | tee "$HOME/xgw-cores-test/after/rollback.txt"
```

Ожидается: этапы «проверяю прежний Xray 26.10.21 на рабочем конфиге», «возвращаю Xray
26.10.21»; «задание кончилось: ok»; итог «Xray НОВАЯ убран, возвращён прежний 26.10.21».
Заказчик видит в карточке тот же итог. Записать его ответ.

Если не так: «задание не кончилось за 300 с» (заказчик не нажал) — повторить просьбу один
раз, затем — вариант «если заказчик не может». «задание кончилось: failed» — записать итог;
Xray не 26.10.21 — выполнить §9 (Xray), сообщить заказчику.

Шаг 6.2. Снова 26.10.21:

```bash
cd "$HOME/xgw-cores-test" && PID=$(systemctl show -p MainPID --value xgw-xray); echo "процесс Xray: $(sudo readlink /proc/$PID/exe)"; sudo /opt/xgw/xray/xray version | head -1; ls -d /opt/xgw/xray*; for i in $(seq 18); do sudo xgw status 2>&1 | grep -q '^Состояние: HEALTHY' && break; sleep 10; done; sudo xgw status 2>&1 | grep -E '^Состояние|^Xray|Перехват:' | tee "$HOME/xgw-cores-test/after/state-back.txt"; sudo xgw diag > "$HOME/xgw-cores-test/after/diag-back.txt"; tail -1 "$HOME/xgw-cores-test/after/diag-back.txt"; sudo python3 corecheck.py card | tee "$HOME/xgw-cores-test/after/card-back.txt" | head -7
```

Ожидается: процесс без `(deleted)`; «Xray 26.10.21 …»; только `/opt/xgw/xray`; состояние — как
в шаге 1.3; «FAIL — 0»; карточка: «Xray: установлен 26.10.21 (проверена XGW)», «прежняя
версия: нет», «наблюдение до: —», «убрана: НОВАЯ — возвращена прежняя версия». В варианте А —
ещё «на GitHub: НОВАЯ» (выпуск снова предлагается).

Если не так: записать; Xray не 26.10.21 — §9 (Xray).

## 7. sing-box (при согласии на пункт 6)

Шаг 7.1. Только если в шаге 3.2 у sing-box «на GitHub: V.V.V» (новее 1.14.3). Иначе записать
«sing-box новее 1.14.3 на GitHub нет» и перейти к шагу 8. Подставь найденную версию вместо
`V.V.V`:

```bash
cd "$HOME/xgw-cores-test" && date '+%F %T' | tee "$HOME/xgw-cores-test/singbox-time.txt" && sudo python3 corecheck.py update sing-box V.V.V | tee "$HOME/xgw-cores-test/after/singbox-update.txt"; sudo /opt/xgw/sing-box/sing-box version | head -1; systemctl is-active xgw-singbox; ls -d /opt/xgw/sing-box*
```

Ожидается: «задание кончилось: ok», итог «sing-box обновлён: 1.14.3 → V.V.V, проверки
пройдены …» (или «… sing-box сейчас не запущен: проверены только версия и конфиг» — если у
шлюза нет серверов для sing-box); «sing-box version V.V.V»; `xgw-singbox` — как в шаге 1.3;
каталоги `/opt/xgw/sing-box` и `/opt/xgw/sing-box.prev`.

Если не так: «задание кончилось: failed» с итогом «не подходит — …» или «не прошёл проверку: …
— возвращён прежний 1.14.3» — **сработала защита** (новый sing-box не принял конфиг XGW или
серверы через него не ответили): записать итог целиком, проверить, что версия 1.14.3, шаг 7.2
пропустить.

Шаг 7.2. Возврат sing-box:

```bash
cd "$HOME/xgw-cores-test" && sudo python3 corecheck.py rollback sing-box | tee "$HOME/xgw-cores-test/after/singbox-rollback.txt"; sudo /opt/xgw/sing-box/sing-box version | head -1; systemctl is-active xgw-singbox; ls -d /opt/xgw/sing-box*; sudo xgw status 2>&1 | grep -E '^Состояние|^sing-box'
```

Ожидается: «задание кончилось: ok», итог «sing-box V.V.V убран, возвращён прежний 1.14.3»;
«sing-box version 1.14.3»; служба — как в шаге 1.3; только `/opt/xgw/sing-box`.

Если не так: версия не 1.14.3 — §9 (sing-box), сообщить заказчику.

## 8. Журнал и итоговое состояние

Шаг 8.1.

```bash
cd "$HOME/xgw-cores-test" && sudo journalctl -u xgw-core.service --since "$(cat "$HOME/xgw-cores-test/install-time.txt")" --no-pager | tail -20 | sed -E 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/<ip>/g' | tee "$HOME/xgw-cores-test/after/journal-core.txt"; sudo journalctl -u xgw-core.service --since "$(cat "$HOME/xgw-cores-test/install-time.txt")" --no-pager | grep -c Traceback | sed 's/^/Traceback в xgw-core: /'; echo "xgw-core: $(systemctl is-active xgw-core.service), $(systemctl is-failed xgw-core.service)"; sudo xgw cores | tee "$HOME/xgw-cores-test/after/cores.txt"
```

Ожидается: строки журнала об этапах заданий («скачиваю…», «проверяю…», итоги); «Traceback в
xgw-core: 0»; «xgw-core: inactive, inactive»; вывод `xgw cores` — те же версии, что в шаге 6.2
(и 7.2).

Шаг 8.2.

```bash
sudo xgw diag > "$HOME/xgw-cores-test/after/diag.txt"; tail -1 "$HOME/xgw-cores-test/after/diag.txt"; sudo xgw status | grep -E '^Состояние|^Xray|^sing-box' | tee "$HOME/xgw-cores-test/after/state.txt"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; sudo grep -c Traceback /var/log/xgw/*.log 2>/dev/null | sed 's/^/Traceback: /'; sudo /opt/xgw/xray/xray version | head -1; ls -d /opt/xgw/xray* /opt/xgw/sing-box* 2>&1
```

Ожидается: «FAIL — 0»; состояние `HEALTHY` или как в шаге 1.3; службы — как в шаге 1.3;
Traceback — 0; «Xray 26.10.21 …»; каталоги — как в шаге 1.3.

## 9. Если что-то пошло не так (ручной откат)

- **Xray** не поднимается или интернет дома пропал — вернуть копию из шага 1.3:

  ```bash
  sudo systemctl stop xgw-core.service; sudo rm -f /run/xgw/core-request.json; sudo rm -rf /opt/xgw/xray.new /opt/xgw/xray.prev.old /opt/xgw/xray.prev; sudo cp -a "$HOME/xgw-cores-test/backup/xray/." /opt/xgw/xray/ && sudo systemctl restart xgw-xray && sleep 15 && sudo /opt/xgw/xray/xray version | head -1 && sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:'
  ```

  Ожидается: «Xray 26.10.21 …», состояние как в шаге 1.3. Сообщить заказчику.
- **sing-box** не 1.14.3 после шага 7 — так же из копии:

  ```bash
  sudo systemctl stop xgw-core.service; sudo rm -f /run/xgw/core-request.json; sudo rm -rf /opt/xgw/sing-box.new /opt/xgw/sing-box.prev.old /opt/xgw/sing-box.prev; sudo cp -a "$HOME/xgw-cores-test/backup/sing-box/." /opt/xgw/sing-box/ && sudo systemctl restart xgw-singbox; sleep 5; sudo /opt/xgw/sing-box/sing-box version | head -1; systemctl is-active xgw-singbox
  ```

- После ручного отката `xgw diag` может показать FAIL у Xray или sing-box («принятой шлюзом»
  версии больше нет на диске) — так и должно быть, записать. Заказчику: исправит повторная
  установка (`sudo sh packaging/install.sh --yes` из `~/zcod/xgw`) — её не выполнять без его
  слова.
- Установка не прошла (код не 0) — сеть и ядра не тронуты; ничего не откатывать.

## 10. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-cores-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`cores-update`), коммит «Отчёт: обновление ядер из панели», `git push`. В отчёт — только
выводы без адресов и имён (см. §0). Шаблон:

```markdown
# Отчёт: обновление ядер из панели (ветка cores-update)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
Вариант шага 5: <А — до X.Y.Z / Б — 26.3.27 / не выполнялся>.

## Итог
<3–6 предложений: служба xgw-core, проверка GitHub, что нашлось, обновление, возврат кнопкой,
sing-box, состояние шлюза.>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до обновления | — | Xray 26.10.21, sing-box 1.14.3, состояние … |
| 2.2 установка | пройден / дефект | … |
| 2.3 служба xgw-core | … | static, inactive |
| 3.1 карточка | … | … |
| 3.2 проверка GitHub | … | Xray на GitHub: …, sing-box на GitHub: …, ошибок … |
| 3.3 карточка у заказчика | … | … |
| 4.1 выпуск, которого нет | … | 404, Xray не тронут |
| 5.1 обновление Xray | … | 26.10.21 → …, итог … |
| 5.2 новое ядро | … | без (deleted), diag OK |
| 5.3 шлюз во время обновления | … | rollback-событий: … |
| 5.4 трафик машины | … | 20 МБ за N с, страна XX |
| 6.1 возврат кнопкой | … | нажал заказчик / исполнитель |
| 6.2 снова 26.10.21 | … | … |
| 7 sing-box | … | … / нет выпуска новее |
| 8 журнал и итог | … | Traceback 0, FAIL — 0 |

## Выводы шагов
<содержимое файлов after/*.txt, по заголовку на файл>

## Дефекты
<или «Не обнаружены»>

## Наблюдения

## Что не проверено и почему
- Самовозврат ядра в сутки наблюдения (ядро перестало отвечать после обновления) — на
  работающем шлюзе не воспроизводится; проверен юнит-тестами.
- <прочее>

## Итоговое состояние машины
```

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
