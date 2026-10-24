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
"""

from __future__ import annotations

import contextlib
import hmac
import http.client
import json
import os
import secrets
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

DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Version=1.0
Name=XGW tray
Name[ru]=XGW — значок в трее
Comment=XGW gateway state in the system tray
Comment[ru]=Состояние шлюза XGW в системном трее
Exec={launcher} tray
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
    """`xgw tray` — сторож; `xgw tray --run` — сам значок (trayapp.py)."""
    if "--run" in argv:
        from . import trayapp

        return trayapp.run()
    # Значок — тем же путём, каким запущен сторож: команда xgw сама находит код XGW.
    launcher = Path(sys.argv[0])
    child = (
        [str(launcher), "tray", "--run"] if launcher.name == "xgw"
        else [sys.executable, "-m", "xgw", "tray", "--run"]
    )
    return supervise(child)


def desktop_entry(launcher: Path, icon: Path) -> str:
    return DESKTOP_ENTRY.format(launcher=launcher.as_posix(), icon=icon.as_posix())
