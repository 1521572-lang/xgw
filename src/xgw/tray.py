"""Значок XGW в трее рабочего стола (0.1.18, ТЗ R9): всё, кроме самого окна Qt (trayapp.py).

Значок живёт в сеансе человека (KDE: StatusNotifierItem через QSystemTrayIcon), а не в
демоне: демон работает от root без графического сеанса. Запуск — при входе в сеанс (XDG
autostart, /etc/xdg/autostart/xgw-tray.desktop ставит установка, если tray.enabled), упал —
встроенный сторож (supervise) поднимает его снова; «Выход» в меню закрывает только значок.

Данные — у панели на 127.0.0.1 (GET /api/tray), действия — там же (POST /api/tray/<действие>)
по своему токену трея: новых сетевых поверхностей нет, наружу значок не ходит. Токен —
отдельный от токена панели и даёт только эти два запроса: состояние и «проверить выпуски
ядер» / «замерить скорость». Установка кладёт его человеку, который её запустил,
в ~/.config/xgw/tray.json (0600, его файл), а панель держит копию в /var/lib/xgw (0600 root).

Значок у человека один: сторож держит блокировку (lock_path), второй `xgw tray` сразу
выходит. Установка запускает `xgw tray --replace` — он закрывает прежние значки (и те, что
запущены до этой блокировки) и встаёт на их место с новым кодом. Испытания 25.10.2026: каждая
из трёх установок добавляла свой значок, и в трее их стало три. Вход в сеанс — тоже с
`--replace`: сторож прошлого сеанса может пережить выход и держать блокировку со старым
окружением сеанса (XAUTHORITY), а его значок в новый сеанс уже не встанет.

Панель из ярлыка «XGW» и из значка открывает open_panel: вкладку XGW, которая на экране,
KWin выводит вперёд — без новой вкладки (заказчик: «можно сделать незаметным открытие второй
вкладки?»); не на экране или не KDE — xdg-open, как раньше.
"""

from __future__ import annotations

import contextlib
import hmac
import http.client
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from .paths import Paths, atomic_write_text

HEADER = "X-XGW-Tray"
ACTIONS = ("cores/check", "speed")
AUTOSTART = Path("etc/xdg/autostart/xgw-tray.desktop")  # от корня машины (paths.root)
USER_FILE = Path(".config/xgw/tray.json")  # в домашнем каталоге человека
POLL_SECONDS = 5.0
# Сторож: упавший значок поднимается через RESTART_PAUSE с, после серии падений подряд пауза
# растёт до RESTART_MAX; значок, проработавший STABLE_AFTER с, считается здоровым.
RESTART_PAUSE = 2.0
RESTART_MAX = 60.0
STABLE_AFTER = 300.0
# Коды выхода значка: трея в сеансе нет (панель KDE ещё не поднялась) — сторож подождёт;
# значок не настроен (нет файла в ~/.config/xgw, нет PyQt, XGW удалён) — сторож заканчивает:
# перезапуск тут не поможет.
NO_TRAY = 3
NOT_SET = 4
QT_PACKAGE = "python3-pyqt6"
LOCK_NAME = "xgw-tray.lock"
REPLACE_WAIT = 5.0  # сколько --replace ждёт, пока прежний значок отпустит блокировку

DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Version=1.0
Name=XGW tray
Name[ru]=XGW — значок в трее
Comment=XGW gateway state in the system tray
Comment[ru]=Состояние шлюза XGW в системном трее
Exec={launcher} tray --replace
Icon={icon}
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
"""


# --- токен и файл человека --------------------------------------------------------


def token_file(paths: Paths) -> Path:
    return paths.var / "tray.token"


def read_token(paths: Paths) -> str:
    with contextlib.suppress(OSError):
        return token_file(paths).read_text(encoding="ascii").strip()
    return ""


def ensure_token(paths: Paths) -> str:
    """Токен трея; создаётся при первой надобности (0600 root)."""
    token = read_token(paths)
    if not token:
        token = secrets.token_urlsafe(24)
        atomic_write_text(token_file(paths), token + "\n", mode=0o600)
    return token


def check(paths: Paths, given: str) -> bool:
    token = read_token(paths)
    return bool(token) and hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8"))


def user_file(home: Path) -> Path:
    return home / USER_FILE


def write_user_file(home: Path, uid: int, gid: int, port: int, token: str) -> Path:
    """Файл значка в домашнем каталоге человека: порт панели и токен трея (0600, его)."""
    path = user_file(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chown(path.parent, uid, gid)
    atomic_write_text(path, json.dumps({"port": port, "token": token}) + "\n", mode=0o600)
    os.chown(path, uid, gid)
    return path


def read_user_file(home: Path) -> tuple[int, str]:
    """(порт панели, токен трея); TrayError — значок не настроен установкой."""
    path = user_file(home)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TrayError(
            f"нет {path}: значок ставит установка XGW (sudo xgw install), от вашего имени"
        ) from exc
    except (OSError, ValueError) as exc:
        raise TrayError(f"{path} не прочитать: {exc}") from exc
    port, token = data.get("port") if isinstance(data, dict) else None, (
        data.get("token") if isinstance(data, dict) else None)
    if not isinstance(port, int) or not isinstance(token, str) or not token:
        raise TrayError(f"{path}: нет порта панели или токена — переустановите XGW")
    return port, token


# --- модель: что показывает значок -----------------------------------------------------


class TrayError(Exception):
    """Значку не получить данные; текст — для подсказки и журнала."""


# Состояние шлюза → вид значка: ok (зелёный), warn (жёлтый), down (красный), job (синий —
# идёт обновление или возврат ядра), off (серый — нет связи с панелью или XGW выключен).
KINDS = {
    "HEALTHY": "ok", "DEGRADED": "warn", "RESERVE": "warn", "PROBE_TARGET_UNREACHABLE": "warn",
    "WAN_DOWN": "down", "ALL_DEAD": "down", "XRAY_DOWN": "down", "LEAK": "down",
}
WORDS = {
    "HEALTHY": "в порядке", "DEGRADED": "часть серверов недоступна",
    "RESERVE": "трафик через резервный сервер", "ALL_DEAD": "все серверы недоступны",
    "WAN_DOWN": "нет связи с провайдером", "XRAY_DOWN": "Xray не отвечает",
    "LEAK": "утечка мимо VPN", "PROBE_TARGET_UNREACHABLE": "не отвечают адреса проверки",
}


def kind(state: dict | None) -> str:
    if not state:
        return "off"
    if state.get("core_job"):
        return "job"
    return KINDS.get(str(state.get("state") or ""), "off")


def tooltip(state: dict | None, error: str = "") -> str:
    """Подсказка значка: состояние, версии ядер, через какой сервер идёт трафик."""
    if not state:
        return "XGW: нет связи с панелью" + (f" — {error}" if error else "")
    lines = [f"XGW {state.get('version') or ''}: "
             + WORDS.get(str(state.get("state") or ""), str(state.get("state") or "—"))]
    if state.get("core_job"):
        lines.append("идёт обновление или возврат ядра")
    cores = [f"Xray {state['xray']}" if state.get("xray") else "",
             f"sing-box {state['singbox']}" if state.get("singbox") else ""]
    if any(cores):
        lines.append(", ".join(item for item in cores if item))
    main = state.get("main") or {}
    if main.get("name"):
        country = f" [{main['country']}]" if main.get("country") else ""
        speed = f", {_mbps(main['mbps'])}" if isinstance(main.get("mbps"), (int, float)) else ""
        how = "выбран вручную" if main.get("pinned") else "основной"
        lines.append(f"{how}: {main['name']}{country}{speed}")
    return "\n".join(lines)


def _mbps(value: float) -> str:
    return f"{value:.0f} Мбит/с" if value >= 10 else f"{value:.1f}".replace(".", ",") + " Мбит/с"


# Пункты меню: (действие, подпись). Порядок — как в ТЗ R9.
MENU = (
    ("open", "Открыть панель"),
    ("cores/check", "Проверить выпуски ядер"),
    ("speed", "Замерить скорость сейчас"),
    ("about", "О программе"),
    ("quit", "Выход"),
)


def menu(state: dict | None) -> list[tuple[str, str, bool]]:
    """Пункты меню с признаком «доступен»: без связи с панелью действия шлюза недоступны;
    пока идёт проверка или замер — тоже (повторное нажатие ничего бы не дало)."""
    busy = (state or {}).get("busy") or {}
    result = []
    for action, label in MENU:
        enabled = True
        if action in ACTIONS:
            enabled = bool(state) and not busy.get(action.split("/")[0])
            if action == "speed" and state and not state.get("speed_on", True):
                enabled = False
        result.append((action, label, enabled))
    return result


def about(state: dict | None) -> str:
    version = (state or {}).get("version") or ""
    return (
        f"XGW {version} — VPN-шлюз на Xray и sing-box.\n"
        "Значок показывает состояние шлюза; «Выход» закрывает только значок, шлюз работает.\n"
        f"Панель: {(state or {}).get('panel') or 'http://127.0.0.1:8781/'}"
    )


# --- клиент к панели ------------------------------------------------------------------


class Client:
    def __init__(self, port: int, token: str, timeout: float = 5.0) -> None:
        self.port, self.token, self.timeout = port, token, timeout

    def _request(self, method: str, path: str) -> dict:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
        try:
            conn.request(method, path, body=b"{}" if method == "POST" else None, headers={
                "Host": f"127.0.0.1:{self.port}", HEADER: self.token,
                "Content-Type": "application/json",
            })
            response = conn.getresponse()
            data = response.read()
        except OSError as exc:
            raise TrayError(f"панель не отвечает: {exc}") from exc
        finally:
            conn.close()
        if response.status != 200:
            raise TrayError(f"панель ответила HTTP {response.status}: "
                            f"{data.decode('utf-8', 'replace').strip()[:200]}")
        try:
            payload = json.loads(data)
        except ValueError as exc:
            raise TrayError("ответ панели не JSON") from exc
        if not isinstance(payload, dict):
            raise TrayError("ответ панели — не объект")
        return payload

    def state(self) -> dict:
        return self._request("GET", "/api/tray")

    def act(self, action: str) -> dict:
        if action not in ACTIONS:
            raise TrayError(f"нет такого действия: {action}")
        return self._request("POST", f"/api/tray/{action}")


# --- сторож -----------------------------------------------------------------------------


def supervise(
    argv: list[str], *, spawn: Callable[[list[str]], int] | None = None,
    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = lambda text: print(text, file=sys.stderr),
    rounds: int | None = None,
) -> int:
    """Запускает значок (argv) и поднимает его снова, если он упал. Выход с кодом 0 — человек
    нажал «Выход» (или tray.enabled = false): сторож заканчивает. rounds — для тестов."""
    run = spawn or (lambda command: subprocess.call(command))
    pause = RESTART_PAUSE
    done = 0
    while rounds is None or done < rounds:
        done += 1
        started = clock()
        try:
            code = run(argv)
        except OSError as exc:  # команды xgw больше нет (XGW удалён)
            log(f"значок XGW не запускается: {exc}")
            return NOT_SET
        if code in (0, NOT_SET):
            return code
        if clock() - started >= STABLE_AFTER:
            pause = RESTART_PAUSE  # работал долго — это не серия падений
        why = "трея в сеансе нет" if code == NO_TRAY else f"код выхода {code}"
        log(f"значок XGW закрылся ({why}) — снова через {pause:.0f} с")
        sleep(pause)
        pause = min(pause * 2, RESTART_MAX)
    return 1


def main(argv: list[str]) -> int:
    """`xgw tray` — сторож; `xgw tray --run` — сам значок (trayapp.py); `xgw tray --replace` —
    закрыть прежние значки и встать на их место (так запускает установка)."""
    if "--run" in argv:
        from . import trayapp

        return trayapp.run()
    replacing = "--replace" in argv
    if replacing:
        replace()
    deadline = time.monotonic() + REPLACE_WAIT
    lock = take_lock(lock_path())
    while lock is None and replacing and time.monotonic() < deadline:
        time.sleep(0.2)
        lock = take_lock(lock_path())
    if lock is None:
        print("значок XGW уже запущен", file=sys.stderr)
        return 0
    # Значок — тем же путём, каким запущен сторож: команда xgw сама находит код XGW.
    launcher = Path(sys.argv[0])
    child = (
        [str(launcher), "tray", "--run"] if launcher.name == "xgw"
        else [sys.executable, "-m", "xgw", "tray", "--run"]
    )
    current: list[subprocess.Popen] = []

    def spawn(command: list[str]) -> int:
        process = subprocess.Popen(command)
        current[:] = [process]
        try:
            return process.wait()
        finally:
            current.clear()

    def stop(_signum, _frame) -> None:
        # Закрывают сторож (--replace, удаление XGW) — значок уходит вместе с ним.
        for process in current:
            with contextlib.suppress(OSError):
                process.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    with lock:
        return supervise(child, spawn=spawn)


# --- один значок на человека ------------------------------------------------------------


def lock_path(home: Path | None = None, environ: dict[str, str] | None = None) -> Path:
    """Файл блокировки значка: в XDG_RUNTIME_DIR (/run/user/UID), а без него — рядом с файлом
    значка в ~/.config/xgw."""
    environ = dict(os.environ) if environ is None else environ
    runtime = environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    if os.path.isdir(runtime):
        return Path(runtime) / LOCK_NAME
    return (home or Path.home()) / USER_FILE.parent / LOCK_NAME


def take_lock(path: Path):
    """Занять блокировку значка (открытый файл; закрытие — освобождение). None — её держит
    другой запущенный значок."""
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="ascii")  # noqa: SIM115 — держится, пока жив сторож
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle


def other_instances(
    proc: Path = Path("/proc"), *, uid: int | None = None, me: int | None = None,
) -> list[int]:
    """Другие значки XGW этого человека по /proc: процессы с его uid, в командной строке
    которых команда xgw (или `-m xgw`) и `tray`. Сначала сторожа, потом сами значки (`--run`):
    сторож до этой версии, переживший свой значок, поднял бы его снова. Находит и значки,
    запущенные до блокировки."""
    uid = os.getuid() if uid is None else uid
    me = os.getpid() if me is None else me
    found: list[tuple[bool, int]] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        words = [arg.decode("utf-8", "replace") for arg in raw.split(b"\0") if arg]
        if not words or "tray" not in words or Path(words[0]).name == "systemd-run":
            continue
        if "--open" in words:  # ярлык открывает панель (open_main) — это не значок
            continue
        if "xgw" in words or any(Path(word).name == "xgw" for word in words):
            found.append(("--run" in words, int(entry.name)))
    return [pid for _icon, pid in sorted(found)]


def replace(
    proc: Path = Path("/proc"), *, kill: Callable[[int, int], None] = os.kill,
    me: int | None = None,
) -> list[int]:
    """Закрывает прежние значки человека (SIGTERM); какие закрыты."""
    pids = other_instances(proc, me=me)
    for pid in pids:
        with contextlib.suppress(OSError):
            kill(pid, signal.SIGTERM)
    return pids


def desktop_entry(launcher: Path, icon: Path) -> str:
    return DESKTOP_ENTRY.format(launcher=launcher.as_posix(), icon=icon.as_posix())


# --- открыть панель без лишней вкладки ---------------------------------------------------

PAGE_FRESH = 5.0  # вкладка опрашивала панель (раз в 3 с) не раньше — значит, она на экране
RAISE_WAIT = 2.0  # столько ждать, пока выведенная вперёд вкладка скажет панели о фокусе
# Вкладка скрылась: окно свёрнуто (KWin его выведет) или открыта другая вкладка (выводить
# нечего, и это ожидание — задержка перед новой вкладкой), поэтому ждать меньше.
HIDDEN_WAIT = 1.0
# Браузер только что запущен, его вкладка ещё грузится и панели о себе не сказала: щелчок в
# это время открыл бы вторую (отчёт 0.2.0, шаг 10.1: два быстрых щелчка — «две и больше»
# вкладок; защита в trayapp держалась, только пока запускался xdg-open, а это миллисекунды).
# Пока с запуска не прошло LAUNCH_HOLD с, новый щелчок ждёт эту вкладку и выводит её вперёд, а
# новую не открывает. Время запуска — в файле OPEN_STAMP рядом с блокировкой значка: так его
# видят и значок, и ярлык «XGW» (`xgw tray --open` — свой процесс на каждый щелчок).
LAUNCH_HOLD = 8.0
OPEN_STAMP = "xgw-open.stamp"
# При закрытии вкладка шлёт «скрылась» и «закрылась» почти разом, и «скрылась» может дойти
# позже (на испытаниях — на 0,2 с): сигналы ближе этого — закрытие, а не свёрнутое окно.
CLOSED_GAP = 1.0
KWIN_NAME = "xgw-raise"
# Каждый вызов KWin по D-Bus — не дольше этого (ДОП-2 рекомендаций к аудиту 0.1.18): зависший
# за недели работы композитор не держит открытие панели; не ответил — новая вкладка.
KWIN_TIMEOUT = 1.5
# Заголовок окна с вкладкой панели: «XGW - Chromium», «XGW — Mozilla Firefox» (или «XGW —
# вход»). Погасшая вкладка (app.js) называется иначе — её окно не выводится.
KWIN_SCRIPT = """\
const all = workspace.windowList ? workspace.windowList() : workspace.clientList();
for (const item of all) {
  if (/^XGW( [-–—] .+)?$/.test(item.caption)) {
    if ("activeWindow" in workspace) workspace.activeWindow = item;
    else workspace.activeClient = item;
    break;
  }
}
"""


def raise_window(
    environ: dict[str, str] | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    """Просит KWin вывести вперёд окно с вкладкой панели (скрипт KWin через dbus-send).
    False — не KDE, нет dbus-send или KWin скрипт не принял. Нашлось ли окно, KWin не
    сообщает — это видно по фокусу вкладки (open_panel)."""
    environ = dict(os.environ) if environ is None else environ
    desktops = (environ.get("XDG_CURRENT_DESKTOP") or "").upper().split(":")
    if "KDE" not in desktops or shutil.which("dbus-send") is None:
        return False
    script = lock_path(environ=environ).with_name(f"{KWIN_NAME}.js")

    def kwin(method: str, *args: str) -> subprocess.CompletedProcess:
        return run(["dbus-send", "--session", "--print-reply", "--dest=org.kde.KWin",
                    "/Scripting", f"org.kde.kwin.Scripting.{method}", *args],
                   capture_output=True, text=True, timeout=KWIN_TIMEOUT)

    try:
        atomic_write_text(script, KWIN_SCRIPT, mode=0o600)
        # Скрипт прошлого раза ещё загружен (KWin запускает его не сразу, выгружать сразу
        # нельзя) — выгрузить, иначе loadScript с тем же именем вернёт -1.
        kwin("unloadScript", f"string:{KWIN_NAME}")
        loaded = kwin("loadScript", f"string:{script}", f"string:{KWIN_NAME}")
        if loaded.returncode != 0 or "int32 -1" in loaded.stdout:
            return False
        return kwin("start").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def xdg_open(url: str) -> None:
    subprocess.Popen(
        ["xdg-open", url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )


def launch_stamp(home: Path | None = None, environ: dict[str, str] | None = None) -> Path:
    """Файл с временем последнего запуска браузера (time.monotonic(): часы одни на всю машину
    до перезагрузки, а XDG_RUNTIME_DIR перезагрузку не переживает)."""
    return lock_path(home, environ).with_name(OPEN_STAMP)


def _since_launch(stamp: Path | None, now: float) -> float | None:
    """Сколько секунд назад этот человек запускал браузер с панелью; None — неизвестно."""
    if stamp is None:
        return None
    try:
        value = float(stamp.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None  # файла нет (ещё не открывали) или он чужой — без удержания
    return now - value if now >= value else None


def _page(client: Client | None) -> dict:
    if client is None:
        return {}
    try:
        page = client.state().get("page")
    except TrayError:
        return {}
    return page if isinstance(page, dict) else {}


def _age(page: dict, name: str) -> float | None:
    value = page.get(name)
    return float(value) if isinstance(value, (int, float)) else None


def open_panel(
    url: str, client: Client | None = None, *,
    raise_it: Callable[[], bool] = raise_window, launch: Callable[[str], None] = xdg_open,
    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
    stamp: Path | None = None,
) -> str:
    """Панель в браузере без лишней вкладки. Вкладка XGW на экране (опрашивала панель не
    раньше PAGE_FRESH) или скрылась позже последнего опроса и не закрыта (свёрнутое окно) —
    KWin выводит её окно вперёд, и она сама обновляется. Если вкладка не сказала панели о
    фокусе (за RAISE_WAIT, у скрытой — за HIDDEN_WAIT), её закрыли или вывести нечем —
    xdg-open (новая вкладка закрывает прежнюю сама, app.js). "raised" или "opened".

    stamp — файл времени запуска браузера (launch_stamp): с запуска не прошло LAUNCH_HOLD —
    вкладка ещё грузится, и новая не открывается: щелчок ждёт её отклика и выводит её вперёд
    ("raised"), а не дождался — "opening". Закрытая после запуска вкладка удержание снимает."""
    page = _page(client)
    started = clock()
    since = _since_launch(stamp, started)
    held = since is not None and since < LAUNCH_HOLD
    while held:
        ago = since + (clock() - started)  # сколько назад запущен браузер
        closed = _age(page, "closed")
        if closed is not None and closed < ago:
            held = False  # вкладку, открытую тем запуском, уже закрыли
            break
        seen = _age(page, "seen")
        if seen is not None and seen < ago:
            break  # вкладка отозвалась после запуска — дальше как с открытой вкладкой
        if ago >= LAUNCH_HOLD:
            return "opening"  # браузер так и не открыл её; следующий щелчок откроет новую
        sleep(0.2)
        page = _page(client)
    seen, focused, hidden, closed = (
        _age(page, name) for name in ("seen", "focused", "hidden", "closed"))
    wait = 0.0  # возраст: меньше — позже
    if seen is not None and seen <= PAGE_FRESH:
        wait = RAISE_WAIT
    elif (hidden is not None and (seen is None or hidden <= seen)
          and (closed is None or closed > hidden + CLOSED_GAP)):
        wait = HIDDEN_WAIT
    if wait and raise_it():
        if wait == RAISE_WAIT and focused is not None and focused <= seen + 0.5:
            return "raised"  # вкладка уже в фокусе — окно впереди
        started = clock()
        while clock() - started < wait:
            sleep(0.2)
            focused = _age(_page(client), "focused")
            if focused is not None and focused <= clock() - started:
                return "raised"
    if held:
        return "opening"  # вкладка того запуска на месте, вторую не открывать
    if stamp is not None:
        try:
            atomic_write_text(stamp, f"{clock()}\n", mode=0o600)
        except OSError as exc:
            print(f"XGW: время открытия панели не записано ({stamp}): {exc}", file=sys.stderr)
    launch(url)
    return "opened"


def open_main(url: str) -> int:
    """`xgw tray --open <адрес>` — ярлык «XGW» в меню и на панели задач. Без файла значка
    (~/.config/xgw/tray.json) — просто xdg-open."""
    client = None
    with contextlib.suppress(TrayError):
        port, token = read_user_file(Path.home())
        client = Client(port, token, timeout=2.0)
    try:
        open_panel(url, client, stamp=launch_stamp())
    except OSError as exc:
        print(f"XGW: браузер не открылся: {exc}", file=sys.stderr)
        return 1
    return 0
