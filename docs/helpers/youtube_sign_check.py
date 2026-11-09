"""Совпадает ли лёгкий признак «YouTube принимает сервер» (состояние плеера из страницы ролика)
с настоящим Firefox без окна. Режимы: health | run КАТАЛОГ. Настройки не меняются.
Браузер, служебные входы серверов и проверка состояния шлюза — из youtube_watch_check.py: он лежит
рядом, уже работал на машине и берётся как есть (его сумму ТЗ сверяет отдельно)."""
import contextlib
import http.client
import importlib.util
import os
import re
import shutil
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location(
    "youtube_watch_lib", Path(__file__).resolve().with_name("youtube_watch_check.py"))
lib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lib)

CONFIG = Path("/etc/xgw/config.toml")
DEADLINE = 35 * 60.0
PAGE_BYTES, PAGE_SECONDS = 4_000_000, 40.0  # страница ролика: не больше и не дольше
VIDEOS = lib.VIDEOS[:2]


def fetch(port, agent, video):
    """Страница ролика через тот же сервер, без cookie: (код ответа, конечный адрес, тело)."""
    proxy = f"http://127.0.0.1:{port}"
    handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy})
    request = urllib.request.Request(f"https://www.youtube.com/watch?v={video}&hl=en", headers={
        "User-Agent": agent, "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip"})
    code, final, raw, end = 0, "", b"", time.monotonic() + PAGE_SECONDS
    try:
        with urllib.request.build_opener(handler).open(request, timeout=20) as reply:
            code, final = reply.status, reply.geturl()
            while len(raw) < PAGE_BYTES and time.monotonic() < end:
                chunk = reply.read(65536)
                if not chunk:
                    break
                raw += chunk
    except urllib.error.HTTPError as exc:
        code, final = exc.code, exc.geturl() or ""
    except (OSError, ValueError, http.client.HTTPException):
        pass  # разбирается то, что успело прийти
    return code, final, raw


def judge(code, final, raw):
    """Признак по странице: accept — плеер готов играть, refuse — YouTube требует входа."""
    body = raw
    if raw[:2] == bytes((31, 139)):
        with contextlib.suppress(zlib.error):
            body = zlib.decompressobj(47).decompress(raw)
    parts = urlsplit(final)
    host = parts.hostname or ""
    where = ("consent" if host.startswith("consent.") else "sorry" if "/sorry" in parts.path
             else "watch" if host == "www.youtube.com" and parts.path == "/watch"
             else "other" if host else "none")
    spot = body.find(b'"playabilityStatus":{')
    chunk = body[spot:spot + 700] if spot >= 0 else b""
    state = re.search(rb'"status":"([A-Z_]+)"', chunk)
    why = re.search(rb'"reason":"([^"]*)"', chunk)
    state = state.group(1).decode() if state else "-"
    why = lib.classify(why.group(1).decode("utf-8", "replace")) if why else None
    verdict = "accept" if state == "OK" else "refuse" if state == "LOGIN_REQUIRED" else "unknown"
    return verdict, (f"code={code} where={where} status={state} reason={why or '-'} "
                     f"kb={len(raw) // 1000}")


def one(base, firefox, port, agent, server, index):
    """Один сервер: признак, два ролика в Firefox, признак ещё раз — и сравнение."""
    def light(label, video):
        verdict, text = judge(*fetch(port, agent, video))
        print(f"SIGN server=S{index} video={label} verdict={verdict} {text}", flush=True)
        return verdict

    lib.ROUTE["server"] = server
    before, seen = light(*VIDEOS[0]), []
    for label, video in VIDEOS:
        start = time.monotonic()
        seen.append(lib.trial(base, firefox, port, server, video))
        print(f"TRIAL server=S{index} video={label} result={seen[-1]} "
              f"seconds={time.monotonic() - start:.0f}", flush=True)
    after = light(*VIDEOS[-1])  # до и после браузера: устойчив ли признак
    refused = any(item in ("bot", "sign_in") for item in seen)
    heavy = ("unknown" if refused == ("played" in seen) else "refuse" if refused else "accept")
    sign = before if before == after else "unknown"
    same = "-" if "unknown" in (sign, heavy) else "yes" if sign == heavy else "no"
    print(f"MATCH server=S{index} sign={sign} browser={heavy} same={same}", flush=True)
    return sign, heavy, same


def run(base):
    lib.health()
    lib.require(os.environ.get("SUDO_USER", "root") != "root", "user")
    firefox = shutil.which("firefox", path=lib.SEARCH)
    if not firefox:
        print("NOT_RUN no_browser", flush=True)
        return 4
    began = time.monotonic()
    listener = socketserver.ThreadingTCPServer(("127.0.0.1", 0), lib.Forward)
    listener.daemon_threads = True
    threading.Thread(target=listener.serve_forever, daemon=True).start()
    chosen, port, rows = lib.usable(), listener.server_address[1], []
    from xgw import config as xconfig  # путь к коду шлюза добавил lib.usable()

    agent = xconfig.load(CONFIG)[0].probe.user_agent  # тот же, что у проверок самого шлюза
    for index, server in enumerate(chosen, 1):
        if time.monotonic() - began > DEADLINE or lib.ROUTE["spent"] > lib.LIMIT_BYTES:
            break
        rows.append(one(base, firefox, port, agent, server, index))
    compared = [row for row in rows if row[2] != "-"]
    print(f"INFO servers={len(rows)} compared={len(compared)} "
          f"same={sum(row[2] == 'yes' for row in rows)} "
          f"sign_refuse={sum(row[0] == 'refuse' for row in rows)} "
          f"browser_refuse={sum(row[1] == 'refuse' for row in rows)} "
          f"mb={lib.ROUTE['spent'] / 1_000_000:.1f} minutes={(time.monotonic() - began) / 60:.1f}",
          flush=True)
    lib.health()
    if len(compared) < 2:
        print("NOT_RUN " + ("few_servers" if len(chosen) < 2 else "few_compared"), flush=True)
        return 4
    caught = any(row[1] == "refuse" and row[2] == "yes" for row in rows)
    print("RESULT " + ("sign_differs" if any(row[2] == "no" for row in rows) else
                       "sign_matches" if caught else "sign_agrees_no_refusal"), flush=True)
    return 0


def main():
    args = sys.argv[1:]
    return (lib.health() or 0) if args == ["health"] else (
        run(args[1]) if len(args) == 2 and args[0] == "run" else 2)


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # текст ошибки может содержать адрес
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
