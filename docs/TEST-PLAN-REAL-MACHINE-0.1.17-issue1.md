# Программа испытаний XGW на реальной машине: issue #1 — интернет в LAN и замеры скорости

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§9). Пути в командах — только абсолютные (`$HOME/xgw-i1-test/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, шлюз дома. Стоит XGW с кодом ветки `android-a1`
(a93ca44, версия 0.1.17), Tailscale подключён, Funnel для приложения включён. Клон
репозитория — `~/zcod/xgw`. Номер версии новый код не меняет (`xgw 0.1.17`); новый код
узнаётся по строке «issue #1 в установленном коде: есть» (шаг 2.3).

Что исправлено (ASSUMPTIONS п. 223–224; отчёт — GitHub issue #1 от 20.10.2026):

1. **Устройства в LAN без интернета при «зелёном» шлюзе.** При
   `net.ipv4.conf.all.src_valid_mark = 1` ядро отбрасывало помеченные пакеты LAN до Xray.
   Теперь в таблице TPROXY есть маршрут `throw <подсеть LAN>` — пакеты доходят при любом
   значении флага. Демон каждый шаг проверяет путь пакета LAN (`ip route get … iif <LAN>
   mark …`) и чинит его сам; не помогло — панель «Нет интернета в сети», уведомление,
   `xgw diag` — строка «Путь LAN» с FAIL.
2. **Замеры скорости.** Замеряются все живые серверы — в работе и запасные: безлимитные раз
   в час, лимитированные раз в 6 часов, запасные — загрузкой 3 МБ. Кнопка «Замерить
   скорость» — все живые сразу, с прогрессом «N из M», занятый канал не ждёт. Фоновый
   замер при занятом канале ждёт не дольше часа. Основной — самый быстрый, и из запасных
   тоже (запасной встаёт в работу и становится основным); при отказе основного — замена
   той же страны. У сервера без цифры — причина.

На машине сейчас обходное решение из отчёта: `/etc/sysctl.d/99-xgw-lan-tproxy.conf`
(`src_valid_mark = 0`). Его **не трогать**: проверка исправления ставит флаг в 1 только
до перезагрузки (шаг 4) и возвращает как было.

Цели:

1. Снимок до обновления (шаг 1.3).
2. Поставить новый код (шаг 2).
3. Маршрут throw на месте, путь LAN — local, `xgw diag` «Путь LAN» — OK (шаг 3).
4. С `src_valid_mark = 1` интернет в LAN есть; пропавший маршрут демон возвращает сам
   (шаг 4).
5. Кнопка замера: цифры у всех живых серверов, прогресс, причины у остальных (шаг 5).
6. Через час — фоновые замеры прошли у всех живых безлимитных (шаг 6).
7. Итоговое состояние (шаг 7), отчёт (§9).

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**.
- Команды Tailscale, кроме `tailscale status`; Funnel, Serve и SSH не трогать.
- Через `i1check.py press` нажимать **только** кнопку `speed`.
- Запуск, остановка и перезапуск `tailscaled`, `xgw`, `xgw-xray`, `xgw-singbox`, `xgw-net`,
  `xgw-dhcp`, `systemd-resolved`, NetworkManager, `ssh`/`sshd`.
- Ручные команды `nft` (кроме `nft list`), `ip` (кроме `ip … show`, `ip route get` и одной
  команды `ip route del throw …` из шага 4.3), `iptables`, `sysctl -w` (кроме двух команд
  шага 4 — только с согласия заказчика).
- Отключать WAN или LAN, кабели, Wi-Fi роутера.
- Править `/etc/xgw/config.toml`, `/etc/xgw/panel.json`, файлы в `/etc/sysctl.d/`,
  `/etc/systemd`.
- Править код XGW. Коммитить что-либо, кроме отчёта (§9). Файлы из `~/xgw-i1-test` в Git
  **не класть**.
- Писать в отчёт: адреса tailnet (`100.x.y.z`, кроме `100.100.100.100` и `100.64.0.0/10`),
  имена `*.ts.net`, имена устройств и пользователей, почту, внешние IP, токены, адреса
  подписок, UUID, IP и домены серверов VPN, MAC-адреса. Внутренние подсети
  (`192.168.x.0/24`) — можно. Выводы с такими данными — только через `i1check.py mask`.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Ставлю исправления по отчёту о критических проблемах (интернет в домашней сети и замеры
скорости). По пунктам:
(1) Установка: демон XGW перезапустится сам, интернет не пропадает, панель секунд на десять
недоступна.
(2) Проверка исправления „интернет в сети“: я на время поставлю флаг ядра
src_valid_mark = 1 (так делает Tailscale, из-за него и пропадал интернет) и попрошу вас
открыть любой сайт на телефоне, подключённом к домашнему Wi-Fi. Если исправление не
сработает, интернет у устройств дома пропадёт — я сразу верну флаг (меньше минуты). Флаг
ставится только до перезагрузки, файлы не меняются.
(3) Нажму „Замерить скорость“: шлюз замерит все живые серверы, это около 0,3–0,7 ГБ
трафика домашнего интернета за раз.
(4) Подожду час и проверю, что фоновые замеры прошли сами (ещё около 0,3 ГБ).
Можно согласиться не на все пункты.»

Дождись ответа. Записать в отчёт, на что заказчик согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против пункта 2 — шаг 4 пропустить («не проверялось — нет согласия»).
- Против пункта 3 — шаг 5 пропустить; против пункта 4 — шаг 6 пропустить.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p "$HOME/xgw-i1-test/before" "$HOME/xgw-i1-test/after" && chmod 700 "$HOME/xgw-i1-test" && cd "$HOME/xgw-i1-test" && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды выполняй из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без пароля
на время испытаний.

Шаг 1.2. Скрипт проверки. Скопируй команду целиком (до строки `I1_EOF` включительно):

```bash
cat > "$HOME/xgw-i1-test/i1check.py" <<'I1_EOF'
"""Issue #1 XGW (ветка issue1-lan-speed): путь LAN и замеры скорости всех серверов.

sudo python3 i1check.py pre               код, флаг src_valid_mark, маршрут throw, путь LAN
sudo python3 i1check.py lanpath           путь пакета устройства сети сейчас
sudo python3 i1check.py wait-lan СЕКУНД   ждать, пока маршрут throw и путь LAN вернутся
sudo python3 i1check.py press speed       нажать «Замерить скорость» (как в браузере)
sudo python3 i1check.py speed             сводка: у кого есть скорость, причины у остальных
sudo python3 i1check.py wait-speed МИНУТ  ждать конца замеров, прогресс раз в минуту
sudo python3 i1check.py fresh МИНУТ       живые безлимитные, замеренные за последние N минут
sudo python3 i1check.py events            последние события: путь LAN, перехват, основной
sudo python3 i1check.py mask < ФАЙЛ       маскировать вывод

Имён серверов, адресов, токенов скрипт не печатает: серверы — тегами (proxy-nl-1234).
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

LIB = os.environ.get("XGW_LIB", "/opt/xgw/lib")
sys.path.insert(0, LIB)
from xgw import config  # noqa: E402

CONFIG = Path(os.environ.get("XGW_CONFIG", "/etc/xgw/config.toml"))
TOKEN_FILE = Path(os.environ.get("XGW_I1_TOKEN", "/var/lib/xgw/panel-token"))
DB = Path(os.environ.get("XGW_I1_DB", "/var/lib/xgw/state.db"))
CGNAT = ipaddress.ip_network("100.64.0.0/10")
SVM = Path("/proc/sys/net/ipv4/conf/all/src_valid_mark")


def run(argv: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]}: нет программы")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"{argv[0]}: таймаут")


def as_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def cfg():
    loaded, _warnings = config.load(CONFIG)
    return loaded


# --- панель --------------------------------------------------------------------------


def request(method: str, path: str, *, cookie: str = "", body: dict | None = None):
    port = cfg().panel.port
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=90)
    headers = {"Host": f"127.0.0.1:{port}"}
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers.update({"Content-Type": "application/json", "X-XGW-Panel": "1",
                        "Origin": f"http://127.0.0.1:{port}"})
    try:
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8", "replace"), response
    finally:
        conn.close()


def login() -> str:
    token = TOKEN_FILE.read_text(encoding="ascii").strip()
    code, _text, response = request("GET", f"/?token={token}")
    if code != 303:
        raise SystemExit(f"вход в панель не удался: HTTP {code}")
    return response.getheader("Set-Cookie").split(";")[0]


def state() -> dict:
    code, text, _response = request("GET", "/api/state", cookie=login())
    if code != 200:
        raise SystemExit(f"состояние панели: HTTP {code}")
    return as_json(text) or {}


# --- путь LAN --------------------------------------------------------------------------


def lan_setup():
    current = cfg()
    lan_if = current.network.lan_if
    try:
        gateway = ipaddress.IPv4Interface(current.network.lan_address.strip())
    except ValueError:
        gateway = None
    return current, lan_if, gateway


def throws() -> list[str]:
    current, _lan_if, _gateway = lan_setup()
    routes = as_json(run(["ip", "-j", "route", "show", "table",
                          str(current.capture.route_table)]).stdout) or []
    return [str(r.get("dst")) for r in routes if isinstance(r, dict) and r.get("type") == "throw"]


def lan_path() -> str:
    """local — пакет устройства сети доставляется в TPROXY; иначе — что ответило ядро."""
    current, lan_if, gateway = lan_setup()
    if not lan_if or gateway is None:
        return "LAN не настроен"
    host = next(str(item) for item in gateway.network.hosts() if item != gateway.ip)
    result = run(["ip", "-j", "route", "get", "1.1.1.1", "from", host, "iif", lan_if,
                  "mark", str(current.capture.mark_proxy)])
    if result.returncode != 0:
        return "ОШИБКА: " + (result.stderr.strip().splitlines() or ["?"])[-1]
    routes = as_json(result.stdout) or [{}]
    route = routes[0] if routes and isinstance(routes[0], dict) else {}
    return str(route.get("type") or "?") + f" (dev {route.get('dev') or '?'})"


def cmd_pre() -> int:
    capture = Path(LIB) / "xgw" / "net" / "capture.py"
    has = capture.exists() and "def lan_path" in capture.read_text(encoding="utf-8")
    print("issue #1 в установленном коде:", "есть" if has else "НЕТ")
    print("версия:", run(["/usr/local/bin/xgw", "--version"]).stdout.strip() or "неизвестно")
    print("src_valid_mark:", SVM.read_text().strip() if SVM.exists() else "нет файла")
    _current, lan_if, gateway = lan_setup()
    print("LAN:", lan_if or "нет", "подсеть", gateway.network if gateway else "?")
    print("маршруты throw в таблице TPROXY:", ", ".join(throws()) or "нет")
    print("путь пакета LAN:", lan_path())
    diag = run(["/usr/local/bin/xgw", "diag"], timeout=300).stdout
    line = next((item for item in diag.splitlines() if "Путь LAN" in item), "строки нет")
    print("xgw diag:", Masker().mask(line.strip()))
    return 0


def cmd_lanpath() -> int:
    print(f"{time.strftime('%T')} путь пакета LAN: {lan_path()}; throw: "
          f"{', '.join(throws()) or 'нет'}; src_valid_mark: {SVM.read_text().strip()}")
    return 0


def cmd_wait_lan(seconds: float) -> int:
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        if throws() and lan_path().startswith("local"):
            print(f"маршрут throw и путь LAN вернулись через {time.monotonic() - started:.0f} с")
            return 0
        time.sleep(2)
    print(f"НЕ ВЕРНУЛИСЬ за {seconds:.0f} с: путь {lan_path()}; throw: {throws() or 'нет'}")
    return 1


# --- замеры скорости ----------------------------------------------------------------


def servers() -> tuple[list[dict], dict]:
    current = state()
    rows = [row for row in current.get("servers") or []
            if row.get("status") in ("member", "spare")]
    return rows, current


def live(row: dict) -> bool:
    if row["status"] == "member":
        return row.get("alive") is True
    return row.get("verdict") in ("OK", "SLOW")


def cmd_press(name: str) -> int:
    if name != "speed":
        print("в этом испытании нажимается только speed")
        return 2
    started = time.monotonic()
    code, text, _response = request("POST", "/api/speed", cookie=login(), body={})
    result = as_json(text) or {}
    print(f"кнопка speed: HTTP {code}, ok={result.get('ok')}, "
          f"{time.monotonic() - started:.1f} с; ответ: {result.get('text')}")
    return 0 if result.get("ok") else 1


def cmd_speed() -> int:
    rows, current = servers()
    busy = (current.get("busy") or {}).get("speed")
    progress = current.get("speed_progress") or {}
    print(f"замер идёт: {'да' if busy else 'нет'}; прогресс: {progress.get('done')} из "
          f"{progress.get('total')}; канал занят (фон ждёт): "
          f"{'да' if progress.get('deferred') else 'нет'}")
    for status, title in (("member", "в работе"), ("spare", "запасные")):
        group = [row for row in rows if row["status"] == status]
        alive = [row for row in group if live(row)]
        measured = [row for row in alive if row.get("speed_mbps") is not None]
        print(f"{title}: всего {len(group)}, живых {len(alive)}, со скоростью {len(measured)}")
    empty = [row for row in rows if row.get("speed_mbps") is None]
    silent = [row for row in empty if not row.get("speed_note")]
    print(f"без цифры: {len(empty)}; из них без причины: {len(silent)}")
    for note, count in Counter(
            re.sub(r": .*", ": …", str(row.get("speed_note"))) for row in empty
    ).most_common():
        print(f"  {count} × {note}")
    busy_rows = [row for row in rows if row.get("speed_busy")]
    print(f"замеров при занятом канале: {len(busy_rows)}")
    best = sorted((row for row in rows if row.get("speed_mbps") is not None),
                  key=lambda row: -float(row["speed_mbps"]))[:5]
    for row in best:
        print(f"  {row.get('tag')} [{row['status']}] {row['speed_mbps']} Мбит/с"
              f"{' x' + str(row.get('multiplier')) if row.get('multiplier') else ''}")
    main = current.get("main") or {}
    print("основной:", main.get("tag") or "нет", f"({main.get('mbps')} Мбит/с)"
          if main.get("mbps") is not None else "")
    budget = current.get("budget") or {}
    print("оценка замеров скорости в сутки, МБ:", budget.get("speed_mb"))
    return 0


def cmd_wait_speed(minutes: float) -> int:
    started = time.monotonic()
    while time.monotonic() - started < minutes * 60:
        rows, current = servers()
        progress = current.get("speed_progress") or {}
        busy = (current.get("busy") or {}).get("speed")
        print(f"{time.strftime('%T')} замер идёт: {'да' if busy else 'нет'}, "
              f"{progress.get('done')} из {progress.get('total')}", flush=True)
        if not busy:
            return 0
        time.sleep(60)
    print(f"замеры не закончились за {minutes:.0f} мин")
    return 1


def cmd_fresh(minutes: float) -> int:
    rows, current = servers()
    now = float(current.get("now") or time.time())
    unlimited = [row for row in rows if live(row) and not row.get("multiplier")]
    fresh = [row for row in unlimited
             if row.get("speed_ts") and now - float(row["speed_ts"]) <= minutes * 60]
    print(f"живых безлимитных: {len(unlimited)}; замерены за последние {minutes:.0f} мин: "
          f"{len(fresh)}")
    for row in unlimited:
        if row not in fresh:
            age = (f"{(now - float(row['speed_ts'])) / 60:.0f} мин назад"
                   if row.get("speed_ts") else "никогда")
            print(f"  не замерен недавно: {row.get('tag')} [{row['status']}] — {age}; "
                  f"{row.get('speed_note') or ''}")
    return 0


def cmd_events() -> int:
    current = state()
    for event in (current.get("events") or [])[:40]:
        if event.get("kind") in ("lan", "capture", "lifecycle", "main", "rotation"):
            stamp = time.strftime("%H:%M:%S", time.localtime(float(event.get("ts") or 0)))
            print(f"{stamp} [{event.get('kind')}] {Masker().mask(str(event.get('detail')))}")
    return 0


class Masker:
    """Имена *.ts.net, адреса tailnet и внешние, почта — метками."""

    def __init__(self) -> None:
        self.labels: dict[str, dict[str, str]] = {}

    def label(self, kind: str, value: str, fmt: str) -> str:
        table = self.labels.setdefault(kind, {})
        return table.setdefault(value, fmt.format(len(table) + 1))

    def _ip(self, match: re.Match) -> str:
        text = match.group(0)
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            return text
        if str(address) in ("100.100.100.100", "127.0.0.1", "1.1.1.1"):
            return text
        if address in CGNAT:
            return self.label("ts4", text, "100.x.y.{}")
        if address.is_global:
            return self.label("ext", text, "внешний-IP-{}")
        return text

    def mask(self, text: str) -> str:
        text = re.sub(r"(?i)\b[\w-]+(\.[\w-]+)*\.ts\.net\b",
                      lambda m: self.label("name", m.group(0).lower(), "имя-{}.ts-net"), text)
        text = re.sub(r"[?&](token|login|c)=[A-Za-z0-9_-]+", r"?\1=***", text)
        text = re.sub(r"\bfd7a:[0-9a-fA-F:]+", "fd7a:…", text)
        text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "почта@…", text)
        return re.sub(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])", self._ip, text)


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("нужен root: sudo python3 i1check.py …")
        return 2
    command, rest = (argv[0], argv[1:]) if argv else ("", [])
    if command == "pre":
        return cmd_pre()
    if command == "lanpath":
        return cmd_lanpath()
    if command == "wait-lan" and rest:
        return cmd_wait_lan(float(rest[0]))
    if command == "press" and rest:
        return cmd_press(rest[0])
    if command == "speed":
        return cmd_speed()
    if command == "wait-speed" and rest:
        return cmd_wait_speed(float(rest[0]))
    if command == "fresh" and rest:
        return cmd_fresh(float(rest[0]))
    if command == "events":
        return cmd_events()
    if command == "mask":
        sys.stdout.write(Masker().mask(sys.stdin.read()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
I1_EOF
sha256sum "$HOME/xgw-i1-test/i1check.py"
```

Ожидается: `45756cab63902020917ad93a0f90546d9d38f992666d85fe236dbb04c1ab5fd0` в начале строки.
Если хеш другой: файл скопирован не целиком — повторить шаг 1.2 один раз; если снова другой —
**стоп**, сообщить заказчику.

Шаг 1.3. Снимок до обновления:

```bash
cd "$HOME/xgw-i1-test" && sudo xgw --version; sudo xgw diag > "$HOME/xgw-i1-test/before/diag.txt"; tail -1 "$HOME/xgw-i1-test/before/diag.txt"; sudo xgw status | grep -E '^Состояние' | tee "$HOME/xgw-i1-test/before/state.txt"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled | tee "$HOME/xgw-i1-test/before/services.txt"; cat /proc/sys/net/ipv4/conf/all/src_valid_mark | sed 's/^/src_valid_mark до обновления: /' | tee "$HOME/xgw-i1-test/before/svm.txt"; ls /etc/sysctl.d/ | tee "$HOME/xgw-i1-test/before/sysctl-files.txt"
```

Ожидается: `xgw 0.1.17`, «FAIL — 0», состояние `HEALTHY` или `DEGRADED` (записать), службы
`active` (у `xgw-singbox` допустимо `inactive` — записать); `src_valid_mark до обновления: 0`;
в списке файлов есть `99-xgw-lan-tproxy.conf` (обходное решение — не трогать).

Если не так: FAIL не 0 — записать как есть и **спросить заказчика**, продолжать ли.
`src_valid_mark` = 1 — записать (Tailscale снова поставил флаг) и продолжать.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout issue1-lan-speed && git pull --ff-only && git log -1 --format='%h %s' && grep -q "def lan_path" src/xgw/net/capture.py && echo "issue #1 в коде: есть"; grep __version__ src/xgw/__init__.py; cd "$HOME/xgw-i1-test"
```

Ожидается: «issue #1 в коде: есть» и `__version__ = "0.1.17"`. Записать хеш.
Если ветки `issue1-lan-speed` нет или «issue #1 в коде: есть» не напечатано: **стоп**,
сообщить заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-i1-test/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-i1-test/after/install.txt" | tail -25; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-i1-test"
```

Ожидается: «код 0» и строка «демон xgw запущен».
Если код не 0: **стоп**, сохранить вывод, выполнить §8, сообщить заказчику.

Шаг 2.3. Установленный код:

```bash
sleep 30; sudo xgw --version; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; sudo python3 "$HOME/xgw-i1-test/i1check.py" pre | tee "$HOME/xgw-i1-test/after/pre.txt"; sudo xgw status 2>&1 | grep -E 'every_hours|Перехват:' | sudo python3 "$HOME/xgw-i1-test/i1check.py" mask | tee "$HOME/xgw-i1-test/after/status-lines.txt"
```

Ожидается:

- `xgw 0.1.17`; службы — как в шаге 1.3;
- «issue #1 в установленном коде: есть»; «src_valid_mark: 0»;
- «маршруты throw в таблице TPROXY: 192.168.60.0/24» (подсеть LAN; записать как есть);
- «путь пакета LAN: local (dev lo)»;
- «xgw diag:» — строка «Путь LAN» с OK и словами «доходят до Xray»;
- строка «Перехват: включён — …» без слов «НЕТ ИНТЕРНЕТА»; если в `config.toml` есть
  `every_hours = 6`, будет предупреждение «speed.every_hours = 6 больше не действует …» —
  записать (ничего не править).

Если не так:

- «issue #1 в установленном коде: НЕТ» — **стоп**: установка не обновила код.
- Нет маршрута throw, путь не `local` или «Путь LAN» — FAIL: **дефект «маршрут throw не
  загружен»**; записать вывод `sudo xgw diag | grep -A2 'Путь LAN'`; шаг 4 пропустить.

## 3. Интернет в LAN при обычном флаге

Шаг 3.1. **Попроси заказчика**: «Откройте на телефоне, подключённом к домашнему Wi-Fi (не
мобильный интернет), любой сайт. Открылся?» Записать ответ.

Ожидается: «открылся». Если нет — **стоп**: это сбой до проверки исправления; выполнить §8.

## 4. Флаг src_valid_mark = 1 (только при согласии на пункт 2)

Шаг 4.1. Поставить флаг, как это делает Tailscale, и сразу проверить путь:

```bash
sudo sysctl -w net.ipv4.conf.all.src_valid_mark=1; sleep 3; sudo python3 "$HOME/xgw-i1-test/i1check.py" lanpath | tee "$HOME/xgw-i1-test/after/svm1.txt"
```

Ожидается: «путь пакета LAN: local (dev lo); throw: 192.168.60.0/24; src_valid_mark: 1».

Если путь «ОШИБКА: … Invalid argument» — **дефект «исправление не работает»**: сразу
`sudo sysctl -w net.ipv4.conf.all.src_valid_mark=0`, затем шаг 4.5, шаги 4.2–4.4 пропустить.

Шаг 4.2. **Попроси заказчика**: «Откройте на телефоне в домашнем Wi-Fi другой сайт (не тот,
что в прошлый раз). Открылся?» Записать ответ. Не открылся за 30 секунд — **дефект**: сразу
`sudo sysctl -w net.ipv4.conf.all.src_valid_mark=0` и шаг 4.5.

Шаг 4.3. Маршрут пропал (так бывает после чужого `nft flush` или пересоздания таблиц) —
демон должен вернуть его сам за один-два шага (по 20 с):

```bash
SUBNET=$(sudo python3 "$HOME/xgw-i1-test/i1check.py" pre | sed -n 's/^маршруты throw в таблице TPROXY: //p' | cut -d, -f1); TABLE=$(sudo python3 -c "import sys; sys.path.insert(0,'/opt/xgw/lib'); from xgw import config; print(config.load(__import__('pathlib').Path('/etc/xgw/config.toml'))[0].capture.route_table)"); echo "подсеть $SUBNET, таблица $TABLE"; date '+%T'; sudo ip route del throw "$SUBNET" table "$TABLE"; sudo python3 "$HOME/xgw-i1-test/i1check.py" lanpath; sudo python3 "$HOME/xgw-i1-test/i1check.py" wait-lan 90 | tee "$HOME/xgw-i1-test/after/heal.txt"
```

Ожидается: сразу после удаления — «путь пакета LAN: ОШИБКА: … Invalid argument; throw:
нет» (флаг 1 — без маршрута пакеты гибнут); затем «маршрут throw и путь LAN вернулись через
N с», N — не больше 60.

Если «НЕ ВЕРНУЛИСЬ за 90 с» — **дефект «демон не чинит путь LAN»**: сразу
`sudo sysctl -w net.ipv4.conf.all.src_valid_mark=0`, записать
`sudo xgw logs 2>&1 | tail -40 | sudo python3 "$HOME/xgw-i1-test/i1check.py" mask`, шаг 4.5.

Шаг 4.4. События и статус:

```bash
sudo python3 "$HOME/xgw-i1-test/i1check.py" events | tee "$HOME/xgw-i1-test/after/events-lan.txt"; sudo xgw status 2>&1 | grep -E '^Состояние|Перехват:|Сейчас:' | sudo python3 "$HOME/xgw-i1-test/i1check.py" mask | tee -a "$HOME/xgw-i1-test/after/events-lan.txt"
```

Ожидается: событие «[capture] правила сети не были загружены — загружены заново» или
«[capture] пакеты устройств сети не доходили до Xray — правила маршрутизации загружены
заново…» (одно из двух — демон заметил пропажу маршрута); событий «[lan] нет интернета у
устройств сети» — нет (демон починил сам); строка «Перехват: включён — …» без «НЕТ
ИНТЕРНЕТА».

Шаг 4.5. Вернуть флаг, как был до испытания (шаг 1.3, обычно 0):

```bash
sudo sysctl -w net.ipv4.conf.all.src_valid_mark=$(sed 's/.*: //' "$HOME/xgw-i1-test/before/svm.txt"); sudo python3 "$HOME/xgw-i1-test/i1check.py" lanpath | tee -a "$HOME/xgw-i1-test/after/svm1.txt"
```

Ожидается: флаг — как в шаге 1.3, «путь пакета LAN: local (dev lo)».

## 5. Кнопка «Замерить скорость» (только при согласии на пункт 3)

Шаг 5.1. До кнопки (демон уже замеряет сам после установки — это нормально):

```bash
sudo python3 "$HOME/xgw-i1-test/i1check.py" speed | tee "$HOME/xgw-i1-test/after/speed-before.txt"
```

Записать как есть.

Шаг 5.2. Кнопка и ожидание конца замеров:

```bash
sudo python3 "$HOME/xgw-i1-test/i1check.py" press speed | tee "$HOME/xgw-i1-test/after/speed-press.txt"; sleep 20; sudo python3 "$HOME/xgw-i1-test/i1check.py" speed | head -1 | tee -a "$HOME/xgw-i1-test/after/speed-press.txt"; sudo python3 "$HOME/xgw-i1-test/i1check.py" wait-speed 40 | tee -a "$HOME/xgw-i1-test/after/speed-press.txt"
```

Ожидается: «кнопка speed: HTTP 200, ok=True … ответ: Замеряю скорость всех живых серверов —
в работе и запасных…»; через 20 с — «замер идёт: да; прогресс: N из M» (M — примерно число
живых серверов, десятки); затем строки ожидания, последняя — «замер идёт: нет». Обычно —
за 5–20 минут.

Если «замеры не закончились за 40 мин» — записать последнюю строку прогресса как
**наблюдение** и продолжать.

Шаг 5.3. Итог:

```bash
sudo python3 "$HOME/xgw-i1-test/i1check.py" speed | tee "$HOME/xgw-i1-test/after/speed-after.txt"; sudo python3 "$HOME/xgw-i1-test/i1check.py" events | grep -E '\[main\]|\[rotation\]' | tee "$HOME/xgw-i1-test/after/events-main.txt"
```

Ожидается:

- «в работе: всего N, живых N, со скоростью N» — у всех живых участников есть скорость
  (x100 — исключение, у них причина);
- «запасные: всего …, живых K, со скоростью K или почти K» — у живых запасных есть скорость
  (раньше — ни у одного);
- «без цифры: …; из них без причины: 0» — у каждого сервера без цифры есть причина
  («скорость не замеряется: запасной не прошёл последнюю проверку», «скорость серверов x100
  не замеряется: они для LTE», «замер не удался: …» и т. п.);
- «основной: proxy-… (… Мбит/с)»;
- события `[main]` — допустимы «основной сервер — …», «основной сервер сменён: …»,
  «запасной … быстрее основного … — встаёт в работу вместо …» (записать как есть).

Если «из них без причины» больше 0 — **дефект «пустая скорость без причины»**: записать
вывод. Если у живых запасных скорости нет совсем (0 из K, K > 0) — **дефект «запасные не
замеряются»**.

Шаг 5.4. **Попроси заказчика**: «Откройте панель XGW: у серверов в списке — и в работе, и
запасных — теперь есть скорость (Мбит/с), а у тех, где её нет, написано почему. Так?»
Записать ответ.

## 6. Фоновые замеры через час (только при согласии на пункт 4)

Шаг 6.1. Подожди 65 минут после конца шага 5.2 (ничего не делая), затем:

```bash
sudo python3 "$HOME/xgw-i1-test/i1check.py" fresh 65 | tee "$HOME/xgw-i1-test/after/fresh.txt"; sudo python3 "$HOME/xgw-i1-test/i1check.py" speed | sed -n '1p;/занятом/p' | tee -a "$HOME/xgw-i1-test/after/fresh.txt"
```

Ожидается: «живых безлимитных: N; замерены за последние 65 мин: N» (или N−1, N−2 — сервер
мог только что ожить; записать); «замеров при занятом канале» — любое число (записать).

Если замерено меньше половины живых безлимитных — **дефект «фоновые замеры не идут»**:
записать вывод целиком.

## 7. Итоговое состояние

Шаг 7.1.

```bash
sudo xgw diag > "$HOME/xgw-i1-test/after/diag.txt"; tail -1 "$HOME/xgw-i1-test/after/diag.txt"; grep -A1 'Путь LAN' "$HOME/xgw-i1-test/after/diag.txt"; sudo xgw status | grep -E '^Состояние' | tee "$HOME/xgw-i1-test/after/state.txt"; systemctl is-active xgw xgw-xray xgw-net xgw-dhcp xgw-singbox tailscaled; cat /proc/sys/net/ipv4/conf/all/src_valid_mark | sed 's/^/src_valid_mark: /'; sudo grep -c Traceback /var/log/xgw/*.log 2>/dev/null | sed 's/^/Traceback: /'
```

Ожидается: «FAIL — 0», «Путь LAN» — OK, состояние `HEALTHY` или `DEGRADED` (записать),
службы — как в шаге 1.3, `src_valid_mark` — как в шаге 1.3, Traceback — 0.

## 8. Если что-то пошло не так

- Интернет у устройств дома пропал — первым делом
  `sudo sysctl -w net.ipv4.conf.all.src_valid_mark=0`, затем
  `sudo python3 "$HOME/xgw-i1-test/i1check.py" lanpath`; сообщить заказчику.
- Установка не прошла или демон не запускается — вернуть прежний код:
  `cd ~/zcod/xgw && git checkout android-a1 && sudo sh packaging/install.sh --yes`, затем
  шаг 2.3 без `i1check.py pre`; сообщить заказчику.

## 9. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.17-issue1-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`issue1-lan-speed`), коммит «Отчёт issue #1: интернет в LAN и замеры скорости», `git push`.
В отчёт — только маскированные выводы. Шаблон:

```markdown
# Отчёт issue #1: интернет в LAN и замеры скорости (ветка issue1-lan-speed)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.

## Итог
<3–6 предложений: путь LAN при флаге 1, самовосстановление, замеры, причины.>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 до обновления | — | … |
| 2.3 установка | пройден / дефект | … |
| 3.1 сайт в LAN | … | … |
| 4.1–4.2 флаг 1 | … | … |
| 4.3 маршрут пропал | … | вернулся через N с |
| 4.4 события | … | … |
| 5.2–5.3 кнопка замера | … | живых запасных со скоростью K из K; без причины 0 |
| 5.4 панель глазами заказчика | … | … |
| 6.1 через час | … | N из N |
| 7 итог | … | FAIL — 0 |

## Выводы шагов 2.3–6
<содержимое файлов after/*.txt, по заголовку на файл>

## Дефекты
<или «Не обнаружены»>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние машины
```

## Итог

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
