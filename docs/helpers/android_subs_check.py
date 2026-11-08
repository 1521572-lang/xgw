"""Экран подписок приложения XGW на телефоне (п. 346): установка APK и проверка через adb.

Режимы: devices | install APK | version | subs N | dialog N | crash | health (health — через sudo).
Запускать от владельца: adb под root заново спросил бы разрешение отладки. На экране телефона
нажимаются только вкладка «Подписки», кнопка «Убрать подписку …» и «Отмена» в её диалоге;
кнопка «Убрать» диалога не нажимается никогда. Вывод — только числа и признаки: имена и адреса
подписок не выводятся.
"""
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ADB = os.environ.get("ADB", "adb")
PACKAGE = "net.xgw.android"
VERSION_CODE = "8"
REMOVE = "Убрать подписку "
EDIT = "Изменить подписку "
WARNING = "Её серверы пропадут"
CONFIG_NOTE = "Запись в config.toml останется"
SWIPES = 12


def run(argv, timeout=60):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)


def adb(*args, timeout=60):
    return run([ADB, *args], timeout=timeout)


def require(ok, label):
    if not ok:
        print("STOP " + label, flush=True)
        raise ValueError(label)
    print("OK " + label, flush=True)


def nodes():
    """Элементы приложения на экране: подпись, id, середина."""
    adb("shell", "uiautomator", "dump", "/sdcard/xgw-ui.xml")
    dump = adb("exec-out", "cat", "/sdcard/xgw-ui.xml").stdout
    try:
        root = ET.fromstring(dump)
    except ET.ParseError:
        return []
    found = []
    for node in root.iter("node"):
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if not match or node.get("package") != PACKAGE:
            continue
        x1, y1, x2, y2 = map(int, match.groups())
        if y2 > y1 and x2 > x1:
            found.append({"label": node.get("text") or node.get("content-desc") or "",
                          "id": node.get("resource-id") or "", "top": y1, "bottom": y2,
                          "x": (x1 + x2) // 2, "y": (y1 + y2) // 2})
    return found


def tap(node):
    adb("shell", "input", "tap", str(node["x"]), str(node["y"]))
    time.sleep(1.5)


def wait_for(check, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(1)
    return check()


def tab_button():
    return next((node for node in nodes() if node["id"].endswith("go-subs")), None)


def open_subs():
    """Открыть приложение на вкладке «Подписки»."""
    adb("shell", "am", "start", "-n", f"{PACKAGE}/.MainActivity")
    button = wait_for(tab_button, 25)
    require(button is not None, "app_open")
    tap(button)
    time.sleep(2)


def swipe(down):
    size = re.search(r"(\d+)x(\d+)", adb("shell", "wm", "size").stdout)
    width, height = (int(size[1]), int(size[2])) if size else (1080, 2340)
    low, high = int(height * 0.7), int(height * 0.3)
    first, last = (low, high) if down else (high, low)
    adb("shell", "input", "swipe", str(width // 2), str(first), str(width // 2), str(last), "300")
    time.sleep(1)


def walk(visit):
    """Пройти вкладку сверху донизу; visit(экран) вызывается на каждом шаге, True — закончить."""
    before = None
    for _ in range(SWIPES):
        swipe(down=False)
        now = [(node["label"], node["y"]) for node in nodes()]
        if now == before:
            break
        before = now
    before = None
    for _ in range(SWIPES):
        screen = nodes()
        if visit(screen):
            return
        now = [(node["label"], node["y"]) for node in screen]  # страница больше не движется
        if now == before:
            return
        before = now
        swipe(down=True)


def devices():
    lines = adb("devices").stdout.splitlines()[1:]
    ready = [line for line in lines if line.strip().endswith("device")]
    print(f"INFO devices={len(ready)}", flush=True)
    require(len(ready) == 1, "one_phone")


def install(apk):
    result = adb("install", "-r", apk, timeout=180)
    require(result.returncode == 0 and "Success" in result.stdout, "apk_installed")
    check_version()


def check_version():
    version = re.search(r"versionCode=(\d+)", adb("shell", "dumpsys", "package", PACKAGE).stdout)
    print(f"INFO version_code={version[1] if version else 'none'}", flush=True)
    require(version is not None and version[1] == VERSION_CODE, "version_code")


def subs(expected):
    open_subs()
    removes, edits, restores = set(), set(), 0

    def visit(screen):
        nonlocal restores
        removes.update(n["label"] for n in screen if n["label"].startswith(REMOVE))
        edits.update(n["label"] for n in screen if n["label"].startswith(EDIT))
        restores = max(restores, sum(n["label"] == "Вернуть" for n in screen))
        return False

    walk(visit)
    print(f"INFO remove_buttons={len(removes)} edit_buttons={len(edits)} "
          f"restore_buttons={restores}", flush=True)
    require(len(removes) == expected, "remove_on_every_subscription")


def reachable(screen, done):
    """Следующая непроверенная «Убрать подписку …», видимая целиком выше панели вкладок. Панель
    закреплена поверх страницы: uiautomator видит и строки под ней, а нажатие в такую строку
    попало бы в вкладку (отчёт android-subs: крайняя правая — «События»)."""
    bar = next((n for n in screen if n["id"].endswith("go-subs")), None)
    limit = bar["top"] if bar else 0
    return next((n for n in screen if n["label"].startswith(REMOVE)
                 and n["label"] not in done and n["bottom"] <= limit), None)


def dialog(expected):
    """Каждая «Убрать подписку …»: диалог открылся, «Отмена» его закрыла, строка на месте."""
    open_subs()
    done, config = set(), 0

    def visit(screen):
        nonlocal config
        target = reachable(screen, done)
        while target is not None:
            done.add(target["label"])
            tap(target)
            shown = nodes()
            require(any(WARNING in n["label"] for n in shown), "dialog_opened")
            config += any(CONFIG_NOTE in n["label"] for n in shown)
            cancel = next((n for n in shown if n["label"] == "Отмена"), None)
            require(cancel is not None, "cancel_found")
            tap(cancel)
            shown = wait_for(lambda: [n for n in nodes() if WARNING in n["label"]] == [], 6)
            require(shown, "dialog_closed")
            target = reachable(nodes(), done)
        return len(done) >= expected

    walk(visit)
    print(f"INFO dialogs={len(done)} config_note={config}", flush=True)
    require(len(done) == expected, "dialogs_checked")


def crash():
    log = adb("logcat", "-d", "-b", "crash", "--pid=0").stdout + adb(
        "logcat", "-d", "-b", "crash").stdout
    count = sum(PACKAGE in line and "FATAL" in line for line in log.splitlines())
    print(f"INFO crash_lines={count}", flush=True)
    require(count == 0, "no_crash")


def health():
    data = json.loads(run(["xgw", "status", "--json"], timeout=15).stdout)
    cap = data.get("capture") or {}
    require(data.get("daemon_down") is False and data.get("xray", {}).get("ok") is True
            and cap.get("mode") == "on" and cap.get("loaded") is True
            and cap.get("blocked") is False and not cap.get("capture_failed"), "on")
    code = run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o", "/dev/null",
                "-w", "%{http_code}", "https://1.1.1.1/"], timeout=12).stdout
    require(code.isdigit() and 200 <= int(code) < 400, "https")
    print(f"INFO state={data.get('state')} "
          f"subscriptions={len(data.get('subscriptions') or [])}", flush=True)


def main():
    args = sys.argv[1:]
    if args == ["devices"]:
        devices()
    elif len(args) == 2 and args[0] == "install":
        install(args[1])
    elif len(args) == 2 and args[0] == "subs" and args[1].isdigit():
        subs(int(args[1]))
    elif len(args) == 2 and args[0] == "dialog" and args[1].isdigit():
        dialog(int(args[1]))
    elif args == ["version"]:
        check_version()
    elif args == ["crash"]:
        crash()
    elif args == ["health"]:
        health()
    else:
        return 2
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        # Не выводим тексты команд и экрана. Последний OK указывает этап.
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
