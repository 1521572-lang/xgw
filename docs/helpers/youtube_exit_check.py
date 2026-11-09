"""Страница и видео YouTube идут через один выход (п. 354); браузер без окна играет ролики по
обычному пути шлюза. Режимы: health | deploy BASE | enable КАТАЛОГ | check КАТАЛОГ | disable."""
import contextlib
import http.server
import json
import os
import pwd
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-youtube-exit")
CONFIG = Path("/etc/xgw/config.toml")
CHANGED = ("config.py", "daemon.py", "generator/builder.py")
ROUTES = {"video": "https://redirector.googlevideo.com/generate_204",
          "page": "https://www.youtube.com/generate_204",
          "api": "https://youtubei.googleapis.com/generate_204",
          "control": "https://www.gstatic.com/generate_204"}  # не должен идти через выход видео
ROUNDS, REQUESTS, MIN_BYTES, NEED_PLAYED = 3, 6, 2000, 3
VIDEOS = ("aqz-KE-bpKQ", "M7lc1UVf-VE", "dQw4w9WgXcQ", "9bZkp7q19f0")
TRIAL, PLAY_GOAL = 70.0, 12.0  # запуск браузера не дольше; столько секунд должно проиграться
BROWSERS = ("firefox", "chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
SEARCH = "/snap/bin:/usr/local/bin:/usr/bin:/bin"
PAGE = b"""<!doctype html><meta charset=utf-8><div id=p></div><script>
var Q=new URLSearchParams(location.search),player=null,failure=0;
function send(){var at=0;try{at=player.getCurrentTime()||0;}catch(e){}
 fetch('/r?n='+Q.get('n')+'&t='+at+'&e='+failure).catch(function(){});}
setInterval(send,2000);send();
function onYouTubeIframeAPIReady(){player=new YT.Player('p',{width:426,height:240,
 videoId:Q.get('v'),playerVars:{autoplay:1,mute:1,playsinline:1,origin:location.origin},
 events:{onReady:function(e){e.target.mute();e.target.playVideo();},
 onError:function(e){failure=e.data;}}});}
var s=document.createElement('script');s.src='https://www.youtube.com/iframe_api';
document.head.appendChild(s);</script>"""
REPORT = {}


def run(argv, *, timeout=20):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def require(ok, label):
    print(("OK " if ok else "STOP ") + label, flush=True)
    if not ok:
        raise ValueError(label)


def status(timeout=40):
    return json.loads(run(["xgw", "status", "--json"], timeout=timeout))


def is_on(data):
    cap = data.get("capture") or {}
    return (data.get("daemon_down") is False and data.get("xray", {}).get("ok") is True
            and cap.get("mode") == "on" and cap.get("loaded") is True
            and cap.get("blocked") is False and not cap.get("capture_failed"))


def https_ok():
    code = run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o", "/dev/null",
                "-w", "%{http_code}", "https://1.1.1.1/"], timeout=12)
    return code.isdigit() and 200 <= int(code) < 400


def health():
    require(is_on(status()), "on")
    require(https_ok(), "https")


def check_health():
    with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
        health()
        return True
    return False


def match(tree):
    return all((tree / "src/xgw" / n).read_bytes() == (Path("/opt/xgw/lib/xgw") / n).read_bytes()
               for n in CHANGED)


def install(tree, name):
    rc = subprocess.run(["sh", str(tree / "packaging/install.sh"), "--yes"], check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    print(f"{name}_rc={rc} at={time.strftime('%H:%M:%S')}", flush=True)
    return rc


def deploy(base):
    base = Path(base).resolve()
    require(match(base) and check_health(), "baseline")
    LOCK.mkdir(mode=0o700)  # второй запуск при живом каталоге не начнёт вторую установку
    accepted, number = False, 0
    try:
        if install(TREE, "install") == 0 and match(TREE):
            done = time.monotonic()
            while not accepted and time.monotonic() - done < 120.0:
                number += 1
                running, web = False, False
                with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
                    running = is_on(status(30))
                    web = https_ok()
                print(f"ATTEMPT {number} at={time.strftime('%H:%M:%S')} on={int(running)} "
                      f"https={int(web)}", flush=True)
                accepted = running and web
                time.sleep(0 if accepted else 3)
    finally:
        if not accepted:
            print(f"recovery_started_at={time.strftime('%H:%M:%S')}", flush=True)
            restored = install(base, "rollback") == 0 and match(base)
            time.sleep(30)  # на подъём связи после возврата
            restored = restored and check_health()
            print("rollback_verified=" + str(restored).lower(), flush=True)
        (LOCK / "result").write_text("accepted\n" if accepted else "returned\n")
    require(accepted, "installed")


def wait_state(check):
    end, state = time.monotonic() + 180, None  # столько демон может перечитывать настройки
    while not check(state) and time.monotonic() < end:
        time.sleep(5)
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            state = (status().get("media") or {}).get("state")
    return state


def place_config(data):
    info = CONFIG.stat()
    temporary = CONFIG.with_name(".xgw-youtube.tmp")
    temporary.write_bytes(data)
    os.chmod(temporary, info.st_mode & 0o777)
    os.chown(temporary, info.st_uid, info.st_gid)
    os.replace(temporary, CONFIG)


def enable(base):
    done, backup = LOCK / "result", LOCK / "config.before"
    require(done.is_file() and done.read_text().strip() == "accepted", "installed_first")
    text = CONFIG.read_text(encoding="utf-8")
    require(not backup.exists() and "[media]" not in text, "enable_once")
    played = play_all(base)  # контроль: играет ли браузер вообще, пока режим выключен
    (LOCK / "baseline").write_text("-1" if played is None else str(played))
    print(f"INFO baseline_played={played}", flush=True)
    shutil.copy2(CONFIG, backup)
    place_config((text.rstrip("\n") + '\n\n[media]\nyoutube_mode = "best"\n').encode("utf-8"))
    state = wait_state(lambda value: value not in (None, "off"))
    print(f"INFO media_state={state}", flush=True)
    require(state not in (None, "off"), "enabled")
    health()


def disable():
    backup = LOCK / "config.before"
    require(backup.is_file(), "backup_found")
    wanted = backup.read_bytes()
    place_config(wanted)
    require(CONFIG.read_bytes() == wanted, "config_restored")
    require(wait_state(lambda value: value == "off") == "off", "disabled")
    health()


def outbound_bytes(tags, port):
    text = run(["curl", "--silent", "--noproxy", "*", "--max-time", "5",
                f"http://127.0.0.1:{port}/debug/vars"], timeout=8)
    stats = json.loads(text)["stats"]["outbound"]
    return sum(value for tag in tags for value in stats[tag].values())


def check_route(tags, port):
    seen = {name: [] for name in ROUTES}
    for _round in range(ROUNDS):
        for name, url in ROUTES.items():
            before = outbound_bytes(tags, port)
            for _attempt in range(REQUESTS):
                with contextlib.suppress(subprocess.SubprocessError):
                    run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o",
                         "/dev/null", url], timeout=12)
            time.sleep(1)  # счётчик должен успеть увидеть последний ответ
            seen[name].append(outbound_bytes(tags, port) - before)
    print("INFO " + " ".join(f"route_{name}={value}" for name, value in seen.items()), flush=True)
    middle = {name: sorted(value)[ROUNDS // 2] for name, value in seen.items()}
    need, verdict = REQUESTS * MIN_BYTES, "proven"
    for name in ("video", "page", "api"):
        require(middle[name] >= need, "route_" + name)
        verdict = "unclear" if middle[name] - middle["control"] < need else verdict
    return verdict


class Web(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parts, body = urlsplit(self.path), PAGE
        if parts.path == "/r":
            ask, body = parse_qs(parts.query), b""
            with contextlib.suppress(KeyError, ValueError):
                REPORT[ask["n"][0]] = {"t": float(ask["t"][0]), "e": int(ask["e"][0])}
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def play_one(base, web, path, video):
    user = pwd.getpwnam(os.environ["SUDO_USER"])
    number = str(time.time_ns())
    profile = Path(base).resolve() / f"p{number}"
    profile.mkdir(mode=0o700)
    os.chown(profile, user.pw_uid, user.pw_gid)
    url = f"http://127.0.0.1:{web}/?n={number}&v={video}"
    args = (["--headless", "--no-remote", "--profile", str(profile), url]
            if path.endswith("firefox") else
            ["--headless=new", "--no-first-run", "--mute-audio",
             "--autoplay-policy=no-user-gesture-required", f"--user-data-dir={profile}", url])
    place = f"/run/user/{user.pw_uid}"
    process = subprocess.Popen(
        ["runuser", "-u", user.pw_name, "--", "env", f"HOME={user.pw_dir}",
         f"XDG_RUNTIME_DIR={place}", f"PATH={SEARCH}",
         f"DBUS_SESSION_BUS_ADDRESS=unix:path={place}/bus", path, *args],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result, began = "no_report", time.monotonic()
    try:
        while time.monotonic() - began < TRIAL:
            time.sleep(1)
            seen = REPORT.get(number)
            if seen and seen["e"]:
                return f"error_{seen['e']}"
            if seen and seen["t"] >= PLAY_GOAL:
                return "played"
            result = "stuck" if seen else result
        return result
    finally:
        subprocess.run(["pkill", "-KILL", "-f", str(profile)], check=False, capture_output=True)
        process.kill()
        process.wait()
        shutil.rmtree(profile, ignore_errors=True)


def play_all(base):
    require(os.environ.get("SUDO_USER", "root") != "root", "user")
    path = next(filter(None, (shutil.which(name, path=SEARCH) for name in BROWSERS)), None)
    print(f"INFO browser={Path(path).name if path else 'none'}", flush=True)
    if path is None:
        return None
    web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Web)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    results = [play_one(base, web.server_address[1], path, video) for video in VIDEOS]
    print(f"INFO play={sorted(results)}", flush=True)
    return results.count("played")


def check(base):
    state = wait_state(lambda value: value == "best")
    if state != "best":
        print(f"NOT_RUN best media_state={state}", flush=True)
        return 4
    tags = (status().get("media") or {}).get("tags") or []
    port = (tomllib.loads(CONFIG.read_text(encoding="utf-8")).get("xray") or {}).get(
        "metrics_port", 10086)
    route = check_route(tags, port)
    played = play_all(base)
    health()
    before = int((LOCK / "baseline").read_text())
    print(f"INFO played={played} baseline={before} need={NEED_PLAYED}", flush=True)
    if route != "proven":
        print("NOT_RUN route " + route, flush=True)
        return 4
    print("OK route", flush=True)
    if played is None or before < NEED_PLAYED:
        print("NOT_RUN play", flush=True)
        return 4
    require(played >= NEED_PLAYED, "play")
    return 0


def main():
    args = sys.argv[1:]
    table = {("health", 1): health, ("disable", 1): disable, ("deploy", 2): deploy,
             ("enable", 2): enable, ("check", 2): check}
    action = table.get((args[0], len(args))) if args else None
    return (action(*args[1:]) or 0) if action else 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # текст ошибки может содержать адрес
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
