# Программа испытаний XGW на реальной машине: фаервол fail-closed (Ф1, ab83a5c)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Все выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§8).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, Docker, роутер HUAWEI AX2 за шлюзом. Стоит XGW
**0.1.15** (код `05a8c68` или новее) в боевом режиме: от него работает интернет всего дома.
Номер версии не меняется: и после обновления `xgw --version` пишет `xgw 0.1.15`. Новый код
узнаётся по коммиту `ab83a5c` (шаг 2.1) и по строке «Ф1 в установленном коде: есть» (шаг 3.1).

Что нового (`a4db3dc` и `ab83a5c`, ASSUMPTIONS пп. 213–214):

- **Режим blocked** (`[capture] hold = "block"`, по умолчанию). Пока в работающем Xray нет
  inbound'а перехвата (настройки сменили, а Xray ещё не перезапущен), раньше трафик всего дома
  шёл **напрямую, мимо VPN**. Теперь мимо VPN не уходит ничего: проходят только сокеты самого
  Xray, связь со шлюзом и внутри домашней сети, DHCP, служба времени и устройства «мимо VPN»;
  остальное отбивается сразу, без долгих таймаутов. Контейнеры Docker тоже закрыты.
- **v6_guard.** IPv6 самой машины при `network.ipv6 = "off"` наружу не выпускает фаервол — а
  не только настройка NetworkManager.
- **Обе таблицы фаервола** (IPv4 и IPv6) загружаются одной транзакцией.
- **`xgw logs --export`** больше не затирает существующий файл и не идёт по символической
  ссылке; правки `panel.json` идут под блокировкой (файл `/etc/xgw/.panel.json.lock`, права 600).

Как проверяется blocked, не трогая настройки. Скрипт делает **копию** `config.toml` (и
`panel.json`) в каталог испытаний и меняет в копии только `capture.tproxy_port`. Правила
загружаются по копии: в работающем Xray inbound'а на таком порту нет — шлюз сам выбирает
blocked. Через 90 секунд скрипт сам загружает правила по настоящему конфигу и запускает демон.
`/etc/xgw` при этом не меняется.

**Важно для исполнителя.** На время окна (шаг 4.2) интернет пропадёт и у этой машины — значит,
и у тебя самого не будет связи. Поэтому окно — одна команда, которую запускает systemd: она всё
делает сама и сама всё возвращает, даже если твой сеанс оборвётся. Все вопросы заказчику —
**до** окна (шаг 4.1) и **после** него (шаг 4.3).

Цели:

1. Поставить новый код (шаг 2), проверить службы и обычный режим (шаг 3).
2. Окно blocked на 90 секунд (шаг 4): правила, связь с машины, телефон заказчика; возврат.
3. Проверить `logs --export` и блокировку `panel.json` (шаг 5).
4. Итоговое состояние (шаг 6), отчёт (§8).

## 0. Запрещено

- `xgw net down`, `xgw uninstall`, `reboot`, `install.sh --force` — **никогда**.
- `flush ruleset`, ручные команды `nft` (кроме `nft list`), `ip` (кроме `ip … show`),
  `iptables`, `sysctl -w` — **никогда**.
- Останавливать или перезапускать `xgw-xray`, `xgw-singbox`, `xgw-net`, `xgw-dhcp`. Демон `xgw`
  останавливает и запускает **только** команда шага 4.2 (и шаг 7, если что-то пошло не так).
- Править `/etc/xgw/config.toml` и `/etc/xgw/panel.json`, менять `capture.hold`.
- Выбирать сервер вручную, снимать выбор, менять приоритеты, нажимать «Замерить скорость».
- Открывать или скачивать адреса подписок, копировать ссылки серверов.
- Править код XGW. Коммитить что-либо, кроме отчёта (§8). Файлы из `~/xgw-f1-test` в Git
  **не класть**.
- Писать в отчёт: адреса подписок, UUID, пароли, ключи, токены, IP и домены серверов, свой
  внешний IP.

Аварийный выход, если интернет не вернулся: шаг 7.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика:** «Обновлю XGW: фаервол станет строже — если Xray когда-нибудь
окажется без нужных настроек, интернет дома закроется, а не пойдёт мимо VPN. (1) Демон XGW при
установке перезапустится сам: интернет не пропадёт, панель и бот секунд на десять станут
недоступны. (2) Потом я на 90 секунд включу этот режим нарочно: **интернет пропадёт у всего
дома** (кроме устройств «мимо VPN», если они есть), панель и бот будут недоступны около двух
минут; через 90 секунд всё вернётся само. (3) В эти 90 секунд прошу вас открыть на телефоне в
домашнем Wi-Fi любой сайт — он не должен открыться; если есть устройство «мимо VPN» — на нём
сайт должен открыться. После окна спрошу, что вы видели. (4) Две короткие проверки команд
XGW — на работу сети не влияют. Можно?» Дождись ответа. Записать в отчёт, на что заказчик
согласился.

- Против пункта 1 — **стоп**, испытание не проводится.
- Против пункта 2 — шаг 4 пропустить целиком (в отчёте: «окно blocked не проводилось»).
- Против пункта 3 — шаг 4 провести, а вопросы В1–В3 шага 4.3 не задавать.
- Против пункта 4 — шаг 5 пропустить.

Затем:

```bash
sudo -n true && echo "sudo без пароля: да"; mkdir -p ~/xgw-f1-test/before ~/xgw-f1-test/after && chmod 700 ~/xgw-f1-test && cd ~/xgw-f1-test && date
```

Ожидается: «sudo без пароля: да» и дата. Дальше все команды выполняй из этого каталога.
Если строки «sudo без пароля: да» нет: **стоп**, попросить заказчика разрешить sudo без пароля
на время испытаний (как в прошлых испытаниях) — вводить пароль некому.

Шаг 1.2. Снимок состояния до обновления:

```bash
sudo xgw --version; git -C ~/xgw log -1 --format='%h %s'; sudo xgw status > before/status.txt; sudo xgw diag > before/diag.txt; tail -1 before/diag.txt; grep -E '^Перехват|^Состояние' before/status.txt; grep -E 'IPv6|Перехват' before/diag.txt
```

(Если код лежит не в `~/xgw` — подставь свой каталог здесь и в шагах 2.1–2.2.)

Ожидается: `xgw 0.1.15`; хеш и заголовок последнего коммита; «Итог: OK — …, WARN — …,
FAIL — 0»; строка «Перехват: включён …»; строки diag про IPv6 и перехват.
Если не так (другая версия или FAIL не 0): записать в отчёт и спросить заказчика, продолжать ли.

Шаг 1.3. Скрипт проверки. Скопируй команду целиком (до строки `EOF` включительно):

```bash
cat > ~/xgw-f1-test/f1check.py <<'EOF'
"""Фаза 1 XGW (ab83a5c): режим blocked и v6_guard на реальной машине.

sudo python3 f1check.py pre                 установленный код, режим, цепочки, IPv6, Docker
sudo python3 f1check.py net --expect on     связь с машины: обычный сокет, метка, через Xray, IPv6
sudo python3 f1check.py window DIR          окно blocked (вызывать только через systemd-run!)
sudo python3 f1check.py audit DIR           logs --export не затирает файл; блокировка panel.json

Код XGW скрипт берёт установленный (/opt/xgw/lib) и ничего в /etc/xgw не правит: окно blocked
загружает правила по копии config.toml в DIR, где изменён только capture.tproxy_port, — в
работающем Xray такого inbound'а нет, и шлюз сам выбирает blocked. Окно всегда кончается
возвратом: `xgw net up` по настоящему конфигу и запуск демона.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

LIB = os.environ.get("XGW_LIB", "/opt/xgw/lib")
sys.path.insert(0, LIB)
from xgw import config, managed  # noqa: E402

XGW = shlex.split(os.environ.get("XGW_CMD", "/usr/local/bin/xgw"))
CONFIG = Path(os.environ.get("XGW_CONFIG", "/etc/xgw/config.toml"))
DAEMON = os.environ.get("XGW_DAEMON_UNIT", "xgw.service")
# Куда стучаться и сколько держать окно; переменные — только для проверки скрипта на стенде.
_HOST4, _, _PORT4 = os.environ.get("XGW_F1_TARGET4", "1.1.1.1:443").rpartition(":")
TARGET4 = (_HOST4, int(_PORT4))
TARGET6 = ("2606:4700:4700::1111", 443)
WINDOW = int(os.environ.get("XGW_F1_WINDOW", "90"))  # секунд blocked: заказчик проверяет телефон


def run(argv: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def chains(family: str, table: str) -> set[str] | None:
    done = run(["nft", "list", "table", family, table])
    if done.returncode != 0:
        return set() if "No such file" in done.stderr else None
    return set(re.findall(r"^\s*chain (\w+) \{", done.stdout, flags=re.MULTILINE))


def mode_of(v4: set[str] | None) -> str:
    if v4 is None:
        return "неизвестно"
    if "block_output" in v4:
        return "blocked"
    if v4 & {"prerouting", "output"}:
        return "on"
    return "off" if v4 else "нет таблицы"


def global_v6() -> list[str]:
    done = run(["ip", "-j", "-6", "addr", "show", "scope", "global"])
    try:
        entries = json.loads(done.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return sorted({e.get("ifname", "") for e in entries if e.get("addr_info")} - {""})


def connect(target: tuple[str, int], *, mark: int = 0, timeout: float = 4.0) -> tuple[str, float]:
    family = socket.AF_INET6 if ":" in target[0] else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    started = time.monotonic()
    try:
        if mark:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, mark)
        sock.settimeout(timeout)
        sock.connect(target)
        return "соединилось", time.monotonic() - started
    except ConnectionRefusedError:
        return "отбито (сброс)", time.monotonic() - started
    except TimeoutError:
        return "таймаут", time.monotonic() - started
    except OSError as exc:
        name = errno.errorcode.get(exc.errno or 0, str(exc.errno))
        return f"отбито ({name})", time.monotonic() - started
    finally:
        sock.close()


def via_xray(port: int, target: tuple[str, int]) -> str:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(f"CONNECT {target[0]}:{target[1]} HTTP/1.1\r\nHost: {target[0]}\r\n\r\n"
                         .encode())
            head = sock.recv(200).decode("latin-1").split("\r\n", 1)[0]
    except OSError as exc:
        return f"нет ({type(exc).__name__})"
    return "соединилось" if " 200" in head else f"нет ({head or 'пусто'})"


def load_cfg(path: Path) -> config.Config:
    cfg, _warnings = config.load(path)
    return cfg


def cmd_pre() -> int:
    nft_src = Path(LIB) / "xgw" / "net" / "nft.py"
    has_f1 = nft_src.exists() and "_blocked_blocks" in nft_src.read_text(encoding="utf-8")
    cfg = load_cfg(CONFIG)
    v4, v6 = chains("ip", "xgw"), chains("ip6", "xgw6")
    print(f"Ф1 в установленном коде: {'есть' if has_f1 else 'НЕТ'}")
    print(f"capture.hold: {cfg.capture.hold!r} → "
          f"{'block' if cfg.capture.hold_blocks else 'direct'}; fail_mode: {cfg.capture.fail_mode}"
          if hasattr(cfg.capture, "hold") else "capture.hold: в этом коде нет")
    print(f"network.ipv6: {cfg.network.ipv6}; tproxy_port: {cfg.capture.tproxy_port}")
    print(f"режим правил: {mode_of(v4)}")
    print("цепочки ip xgw: " + (", ".join(sorted(v4)) if v4 else "—"))
    print("цепочки ip6 xgw6: " + (", ".join(sorted(v6)) if v6 else "—"))
    print(f"v6_guard: {'есть' if v6 and 'v6_guard' in v6 else 'нет'}")
    v6addr = global_v6()
    kernel6 = Path("/proc/sys/net/ipv6/conf/all/disable_ipv6")
    usable = kernel6.exists() and kernel6.read_text(encoding="ascii").strip() != "1"
    print(f"IPv6 в ядре: {'есть' if usable else 'нет'}")
    print("глобальный IPv6: " + (", ".join(v6addr) if v6addr else "нет"))
    print(f"устройств мимо VPN (bypass_hosts): {len(cfg.network.bypass_hosts)}")
    bridges = [p.name for p in Path("/sys/class/net").glob("*")
               if p.name == "docker0" or p.name.startswith("br-")]
    print("мосты Docker: " + (", ".join(sorted(bridges)) if bridges else "нет"))
    lock = managed.lock_path(managed.path_for(CONFIG))
    print(f"файл блокировки panel.json: {'есть' if lock.exists() else 'нет'}")
    return 0 if has_f1 else 3


def probes(cfg: config.Config) -> dict[str, tuple[str, float] | str]:
    mark = cfg.capture.mark_bypass
    result: dict[str, tuple[str, float] | str] = {
        "a": connect(TARGET4),
        "b": connect(TARGET4, mark=mark),
        "c": via_xray(cfg.xray.http_port, TARGET4),
    }
    result["d"] = connect(TARGET6) if global_v6() else "нет глобального IPv6"
    return result


def report(result: dict, expect: str) -> tuple[list[str], int]:
    def show(value) -> str:
        return value if isinstance(value, str) else f"{value[0]} за {value[1]:.2f} с"

    verdicts = []
    a, b, c, d = result["a"], result["b"], result["c"], result["d"]
    if expect == "on":
        verdicts.append(("a обычный сокет (через перехват)", a[0] == "соединилось"))
    else:
        verdicts.append(("a обычный сокет отбит сразу", a[0].startswith("отбито") and a[1] < 2.0))
    verdicts.append(("b сокет с меткой мимо VPN", b[0] == "соединилось"))
    verdicts.append(("c через http-in Xray", c == "соединилось"))
    if isinstance(d, str):
        verdicts.append(("d IPv6 машины", None))
    else:
        verdicts.append(("d IPv6 машины закрыт", d[0].startswith("отбито")))
    lines = [f"Связь с машины (ожидается режим {expect}):"]
    labels = ("a обычный", "b с меткой", "c через Xray", "d IPv6")
    for key, label in zip("abcd", labels, strict=True):
        lines.append(f"  {label}: {show(result[key])}")
    failed = [name for name, ok in verdicts if ok is False]
    skipped = [name for name, ok in verdicts if ok is None]
    for name, ok in verdicts:
        lines.append(f"  {name}: " + ("ПРОЙДЕН" if ok else "НЕ ПРОВЕРЕНО" if ok is None
                                       else "ДЕФЕКТ"))
    lines.append("ИТОГ: " + ("ДЕФЕКТ: " + "; ".join(failed) if failed else
                             "ПРОЙДЕН" + (f" (не проверено: {len(skipped)})" if skipped else "")))
    return lines, 1 if failed else 0


def cmd_net(expect: str) -> int:
    lines, code = report(probes(load_cfg(CONFIG)), expect)
    for line in lines:
        print(line)
    return code


def test_config(directory: Path) -> Path:
    """Копия config.toml (и panel.json) в DIR с другим capture.tproxy_port."""
    text = CONFIG.read_text(encoding="utf-8")
    port = load_cfg(CONFIG).capture.tproxy_port + 54
    lines = text.splitlines()
    section, done = "", False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and not stripped.startswith("[["):
            section = stripped.strip("[] ")
        elif section == "capture" and re.match(r"tproxy_port\s*=", stripped):
            lines[index], done = f"tproxy_port = {port}", True
    if not done:
        for index, line in enumerate(lines):
            if line.strip() == "[capture]":
                lines.insert(index + 1, f"tproxy_port = {port}")
                done = True
                break
    if not done:
        lines += ["", "[capture]", f"tproxy_port = {port}"]
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    target = directory / "config.toml"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    panel = managed.path_for(CONFIG)
    if panel.exists():
        shutil.copy2(panel, managed.path_for(target))
        os.chmod(managed.path_for(target), 0o600)
    copy = load_cfg(target)
    if copy.capture.tproxy_port != port:
        raise SystemExit(f"копия конфига не та: tproxy_port {copy.capture.tproxy_port} ≠ {port}")
    return target


def cmd_window(directory: Path) -> int:
    """Окно blocked с обязательным возвратом. Пишет DIR/window.txt."""
    cfg = load_cfg(CONFIG)
    if not cfg.capture.hold_blocks:
        print(f"СТОП: capture.hold = {cfg.capture.hold!r}, fail_mode = {cfg.capture.fail_mode} —"
              " blocked здесь не включается")
        return 2
    target = test_config(directory)
    out: list[str] = []

    def note(text: str) -> None:
        out.append(text)
        print(text, flush=True)

    started = time.monotonic()
    note(f"окно blocked: {time.strftime('%T')}, копия конфига: tproxy_port "
         f"{load_cfg(target).capture.tproxy_port}")
    code = 0
    try:
        run(["systemctl", "stop", DAEMON], timeout=60)
        up = run([*XGW, "net", "up", "--config", str(target)])
        note(f"net up по копии: код {up.returncode}")
        said = [line for line in up.stdout.splitlines() if line.startswith("Перехват")]
        note(said[-1] if said else (up.stdout + up.stderr).strip()[-300:] or "(вывода нет)")
        v4, v6 = chains("ip", "xgw"), chains("ip6", "xgw6")
        guard = "есть" if v6 and "v6_guard" in v6 else "нет"
        note(f"режим правил: {mode_of(v4)}; v6_guard: {guard}")
        forward = run(["nft", "list", "chain", "ip", "xgw", "forward"]).stdout
        docker = sum(
            1 for line in forward.splitlines()
            if ('iifname "docker0"' in line or 'iifname "br-*"' in line) and "reject" in line
        )
        note(f"отбой выхода контейнеров в forward: правил {docker}")
        lines, code = report(probes(cfg), "blocked")
        for line in lines:
            note(line)
        diag = run([*XGW, "diag", "--no-net", "--config", str(target)], timeout=180)
        for line in diag.stdout.splitlines():
            if line.strip().startswith(("[", "OK", "WARN", "FAIL")) and (
                    "Перехват" in line or "IPv6" in line):
                note("diag: " + line.strip())
        if mode_of(v4) != "blocked":
            code = 1
        left = WINDOW - (time.monotonic() - started)
        note(f"ждём {max(0, int(left))} с: заказчик проверяет телефон")
        if left > 0:
            time.sleep(left)
    finally:
        back = run([*XGW, "net", "up", "--config", str(CONFIG)])
        note(f"возврат: net up по настоящему конфигу — код {back.returncode}")
        started_daemon = run(["systemctl", "start", DAEMON], timeout=60)
        note(f"возврат: запуск демона — код {started_daemon.returncode}")
        note(f"режим правил после возврата: {mode_of(chains('ip', 'xgw'))}; "
             f"конец окна: {time.strftime('%T')}")
        (directory / "window.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    return code


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else "нет файла"


def cmd_audit(directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    failed = 0
    existing = directory / "notes.txt"
    existing.write_text("заметки, которые нельзя затирать\n", encoding="utf-8")
    link = directory / "link.tar.gz"
    link.unlink(missing_ok=True)
    link.symlink_to(existing)
    for name, out in (("существующий файл", existing), ("символическая ссылка", link)):
        before = sha(existing)
        done = run([*XGW, "logs", "--export", "--out", str(out), "--config", str(CONFIG)],
                   timeout=180)
        text = (done.stdout + done.stderr).strip().splitlines()
        message = text[-1] if text else ""
        ok = (done.returncode != 0 and "уже существует" in message and sha(existing) == before
              and existing.read_text(encoding="utf-8").startswith("заметки"))
        failed += not ok
        print(f"logs --export в {name}: код {done.returncode}, «{message}» — "
              + ("ПРОЙДЕН" if ok else "ДЕФЕКТ"))
    panel = managed.path_for(CONFIG)
    lock = managed.lock_path(panel)
    before = sha(panel)
    changed = managed.set_priority(panel, ["00000000"], "medium")  # такого сервера нет
    mode = oct(lock.stat().st_mode & 0o777) if lock.exists() else "нет файла"
    ok = not changed and lock.exists() and mode == "0o600" and sha(panel) == before
    failed += not ok
    print(f"блокировка panel.json: {lock} — права {mode}, panel.json "
          f"{'не изменился' if sha(panel) == before else 'ИЗМЕНИЛСЯ'} — "
          + ("ПРОЙДЕН" if ok else "ДЕФЕКТ"))
    print("ИТОГ: " + ("ПРОЙДЕН" if not failed else f"ДЕФЕКТ: {failed}"))
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("запускать через sudo")
        return 2
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "pre":
        return cmd_pre()
    if argv[0] == "net":
        return cmd_net(argv[2] if len(argv) > 2 and argv[1] == "--expect" else "on")
    if argv[0] == "window" and len(argv) == 2:
        return cmd_window(Path(argv[1]))
    if argv[0] == "audit" and len(argv) == 2:
        return cmd_audit(Path(argv[1]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
EOF
sha256sum ~/xgw-f1-test/f1check.py
```

Ожидается: `589d42358dd9206ed182702762993a2eedfe576d79ca6e9681e4806f2c28147c` в начале строки.
Если хеш другой: файл скопирован не целиком — повторить шаг 1.3 один раз; если снова другой —
**стоп**, сообщить заказчику.

## 2. Установка

Шаг 2.1:

```bash
cd ~/xgw && git pull && git log -1 --format=%H && git merge-base --is-ancestor ab83a5c HEAD && echo "ab83a5c есть"; grep __version__ src/xgw/__init__.py; cd ~/xgw-f1-test
```

Ожидается: «ab83a5c есть» и `__version__ = "0.1.15"`. Записать хеш.
Если «ab83a5c есть» не напечатано: **стоп**, сообщить заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/xgw && date '+%F %T' | tee ~/xgw-f1-test/install-time.txt && sudo sh packaging/install.sh --yes 2>&1 | tee ~/xgw-f1-test/after/install.txt | tail -25; echo "код ${PIPESTATUS[0]}"; cd ~/xgw-f1-test
```

Ожидается: «код 0».
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику.

## 3. Службы и обычный режим

Шаг 3.1:

```bash
sleep 20; sudo xgw --version; systemctl is-active xgw-net xgw-xray xgw xgw-dhcp xgw-singbox; sudo python3 f1check.py pre | tee after/pre.txt
```

Ожидается:

- `xgw 0.1.15`, пять раз `active`;
- «Ф1 в установленном коде: есть»;
- «capture.hold: 'block' → block; fail_mode: closed»;
- «режим правил: on»;
- «v6_guard: есть», если «IPv6 в ядре: есть» (при «IPv6 в ядре: нет» — «v6_guard: нет», так и
  должно быть);
- «мосты Docker: docker0 …» и «устройств мимо VPN (bypass_hosts): N» — записать N.

Если не так:

- «Ф1 в установленном коде: НЕТ» — **стоп**: установка не обновила код; сообщить заказчику.
- hold — `direct` или fail_mode — `open` (заказчик сам так настроил): записать; шаг 4 пропустить
  (blocked в такой настройке не включается — так и задумано), перейти к шагу 5.
- «режим правил» не `on`, или «v6_guard: нет» при «IPv6 в ядре: есть» — записать дефект
  (строки целиком) и перейти к шагу 3.2.

Шаг 3.2. Связь с машины в обычном режиме и diag:

```bash
sudo python3 f1check.py net --expect on | tee after/net-on.txt; sudo xgw diag > after/diag.txt; tail -1 after/diag.txt; grep -E 'IPv6|Перехват' after/diag.txt
```

Ожидается: в конце «ИТОГ: ПРОЙДЕН» (или «ПРОЙДЕН (не проверено: 1)» — так, если глобального
IPv6 на машине нет); «FAIL — 0»; строка «Перехват: включён, правила загружены»; строка IPv6 —
«глобальных IPv6-адресов нет …» или «… наружу IPv6 машины не выпускает фаервол (v6_guard)».

Если не так: «ИТОГ: ДЕФЕКТ: …» или FAIL в IPv6 — записать дефект (вывод целиком); шаг 4 **не
проводить** (обычный режим не в порядке), перейти к шагу 5.

## 4. Окно blocked (90 секунд)

Шаг 4.1. **Скажи заказчику** (если он согласился на пункт 2): «Сейчас на 90 секунд пропадёт
интернет у всего дома. Пока его нет, откройте на телефоне в домашнем Wi-Fi любой сайт — он не
должен открыться (страница с ошибкой, не бесконечная загрузка). Если есть устройство „мимо
VPN“ — откройте сайт и на нём: там он должен открыться. Через две минуты всё вернётся само.
Скажите, когда будете готовы.» Дождись ответа «готов».

Шаг 4.2. Окно. **Одна команда; не прерывай её, дождись вывода** (около 2 минут). Во время окна
у тебя не будет связи — это нормально:

```bash
sudo systemd-run --wait --collect --pipe --quiet --unit=xgw-f1-window /usr/bin/python3 "$HOME/xgw-f1-test/f1check.py" window "$HOME/xgw-f1-test/blk" | tee after/window.txt; echo "код ${PIPESTATUS[0]}"
```

Ожидается, по порядку:

- «окно blocked: ЧЧ:ММ:СС, копия конфига: tproxy_port 12399» (число может быть другим);
- «net up по копии: код 0» и строка «Перехват: НЕ ВКЛЮЧЁН (ожидание применения inbound в Xray) —
  … трафик заблокирован, мимо VPN ничего не уходит (capture.hold = block) …»;
- «режим правил: blocked; v6_guard: есть» (при «IPv6 в ядре: нет» — «нет»);
- «отбой выхода контейнеров в forward: правил 2» (два моста: `docker0` и `br-*`);
- блок «Связь с машины (ожидается режим blocked)»: «a обычный: отбито … за 0.0x с», «b с
  меткой: соединилось», «c через Xray: соединилось», и «ИТОГ: ПРОЙДЕН» (или «… не проверено: 1»);
- строки «diag: WARN  Перехват: включён, но ждёт inbound в Xray: … — трафик заблокирован …» и
  «diag: … IPv6: …»;
- «ждём N с: заказчик проверяет телефон»;
- «возврат: net up по настоящему конфигу — код 0», «возврат: запуск демона — код 0»,
  «режим правил после возврата: on»;
- «код 0».

Если не так:

- «СТОП: capture.hold …» — окно не проводилось (так настроено); записать, перейти к шагу 5.
- «режим правил: off» или строка «… трафик идёт напрямую …» — **дефект «без inbound'а трафик
  идёт напрямую»**: записать вывод целиком.
- «a обычный: соединилось» в блоке blocked — **дефект «в blocked машина выходит мимо VPN»**.
- «b с меткой» или «c через Xray» не «соединилось» — дефект «blocked закрыл и Xray»: записать.
- «режим правил после возврата» не `on` или любой «возврат: … код» не 0 — сразу шаг 7.
- Вывод оборвался, команды нет дольше 4 минут — сразу шаг 7.

Шаг 4.3. После окна — проверка возврата и уборка копии конфига (в ней адреса подписок):

```bash
sleep 20; systemctl is-active xgw xgw-xray; sudo python3 f1check.py net --expect on | tee after/net-after.txt; sudo xgw status | grep -E '^Перехват|^Состояние'; sudo rm -rf ~/xgw-f1-test/blk && echo "копия конфига удалена"
```

Ожидается: два `active`; «ИТОГ: ПРОЙДЕН»; «Перехват: включён …»; «копия конфига удалена».
Если не так: «ИТОГ: ДЕФЕКТ» или демон не `active` — сразу шаг 7.

**Спроси заказчика** (если он согласился на пункт 3) и запиши ответы:

- В1: «Пока не было интернета, сайт на телефоне не открылся?» (ожидается «не открылся»);
- В2: «Как быстро телефон сказал об ошибке — сразу или долго грузил?» (ожидается «сразу» или
  «за пару секунд»);
- В3: «Если есть устройство „мимо VPN“: на нём сайт открылся?» (ожидается «да»; нет такого
  устройства — «нет устройства»);
- В4: «Сейчас интернет на телефоне есть?» (ожидается «да»; если «нет» — сразу шаг 7).

Если В1 — «открылся»: **дефект «в blocked устройства LAN выходят мимо VPN»**. Если В3 — «не
открылся»: дефект «blocked закрыл устройство мимо VPN».

## 5. logs --export и блокировка panel.json

Шаг 5.1 (если заказчик согласился на пункт 4):

```bash
sudo python3 f1check.py audit "$HOME/xgw-f1-test/audit" | tee after/audit.txt
```

Ожидается: три строки «— ПРОЙДЕН» (существующий файл, символическая ссылка, блокировка
`panel.json` с правами `0o600` и неизменным `panel.json`) и «ИТОГ: ПРОЙДЕН».
Если не так: записать дефект (строку целиком) и продолжать.

## 6. Итоговое состояние

Шаг 6.1:

```bash
systemctl is-active xgw-net xgw-xray xgw-singbox xgw xgw-dhcp; sudo xgw diag > after/diag-end.txt; tail -1 after/diag-end.txt; sudo xgw status | head -8; sudo python3 f1check.py pre | grep -E 'режим правил|v6_guard'
```

Ожидается: пять `active`, «FAIL — 0», «режим правил: on», «v6_guard: есть» (как в шаге 3.1).
Если FAIL не 0: записать строки с FAIL (`grep FAIL after/diag-end.txt`).

## 7. Если что-то пошло не так

- Интернет не вернулся после окна или «режим правил после возврата» не `on`:

  ```bash
  sudo xgw net up; sudo systemctl start xgw; sleep 20; sudo python3 ~/xgw-f1-test/f1check.py net --expect on
  ```

  Если и после этого «ИТОГ» не «ПРОЙДЕН» и у заказчика нет интернета — `sudo xgw disable`
  (интернет пойдёт напрямую, мимо VPN), сообщить заказчику. `sudo rm -rf ~/xgw-f1-test/blk` —
  в любом случае.
- Демон не `active` — **не** перезапускать его повторно; журнал
  `sudo journalctl -u xgw -n 80 --no-pager > after/xgw-fail.txt` и сообщить заказчику.
- Команда `xgw` пишет «ошибка» — сохранить вывод в `after/`, записать в отчёт, перейти к
  следующему шагу, если шаг не помечен «стоп».

## 8. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.15-f1-<ГГГГ-ММ-ДД>.md` в репозитории. Заполни бланк:

```markdown
# Отчёт об испытаниях XGW на реальной машине: фаервол fail-closed (Ф1, ab83a5c)

Код: <хеш>. Установка: <время>, код <0/…>. Согласие заказчика: пункты <1–4 / какие нет>.

## Итог
<3–5 предложений: включился ли blocked без inbound'а; уходил ли кто-нибудь мимо VPN в окне;
проходили ли Xray и устройства мимо VPN; вернулось ли всё само; что с v6_guard; logs --export
и блокировка panel.json>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до обновления | — | <версия, FAIL — …> |
| 2 установка | пройден / нет | |
| 3.1 службы и код | пройден / нет | <Ф1 есть; hold; режим; v6_guard; IPv6 в ядре; мосты; N мимо VPN> |
| 3.2 связь в режиме on | пройден / дефект | <ИТОГ net-on; строки diag IPv6 и Перехват> |
| 4.2 окно blocked: правила | пройден / дефект / не проводилось | <режим; v6_guard; отбой контейнеров N> |
| 4.2 окно blocked: связь с машины | пройден / дефект / не проводилось | <a, b, c, d кратко> |
| 4.2 возврат | пройден / нет / не проводилось | <режим после возврата; коды> |
| 4.3 телефон (В1–В4) | пройден / дефект / не задавались | <ответы кратко> |
| 5.1 logs --export и блокировка | пройден / дефект / пропущен | |
| 6 итоговое состояние | пройден / нет | <FAIL — …> |

## Шаг 4 — окно blocked
<вывод after/window.txt целиком>

| Вопрос | Ответ заказчика |
|---|---|
| В1 сайт в окне не открылся | |
| В2 ошибка сразу | |
| В3 устройство мимо VPN работало | |
| В4 интернет вернулся | |

## Шаг 5 — logs --export и блокировка
<вывод after/audit.txt>

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Наблюдения

## Что не проверено и почему

## Итоговое состояние машины
```

Перед коммитом проверь, что в отчёте нет секретов:

```bash
grep -nE '(vless|vmess|trojan|ss|hysteria2)://[^*]|[0-9a-f]{8}-[0-9a-f]{4}-|token|/sub/' docs/TEST-REPORT-REAL-MACHINE-0.1.15-f1-*.md
```

Ожидается: пусто. Если что-то нашлось — убрать из отчёта.

Коммит только отчёта: `git add docs/TEST-REPORT-REAL-MACHINE-0.1.15-f1-*.md && git commit -m
"Отчёт об испытаниях XGW на реальной машине: фаервол fail-closed (Ф1)" && git push`.
