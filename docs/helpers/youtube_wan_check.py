"""Играет ли YouTube в Firefox без окна обычным путём, напрямую и напрямую с дроблением ClientHello.
Режимы: health | run КАТАЛОГ. Настройки не меняются: временный Xray только на 127.0.0.1."""
import contextlib
import json
import os
import pwd
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

CONFIG = Path("/etc/xgw/config.toml")
XRAY = Path("/opt/xgw/xray/xray")
SEARCH = "/snap/bin:/usr/local/bin:/usr/bin:/bin"
TRIAL, PLAY_GOAL = 90.0, 20.0  # ролик не дольше (реклама идёт в тот же тег); столько должно сыграть
DEADLINE, NEED = 45 * 60.0, 3  # весь прогон; сколько роликов из четырёх нужно рабочему пути
VIDEOS = (("plain1", "aqz-KE-bpKQ"), ("plain2", "M7lc1UVf-VE"),
          ("music1", "dQw4w9WgXcQ"), ("music2", "9bZkp7q19f0"))
PATHS = ("normal", "direct", "fragment", "split")
UNMEASURED = ("no_marionette", "browser_died", "navigate_hang", "script_hang")
PROBE = """var c=location.hostname.indexOf('consent.')===0;var done=false;var d=document;
var go=arguments[0];var r=d.querySelector('input[name=set_eom][value=true]');
var n=Array.from(document.querySelectorAll('button')).find(function(b){
 return /^Reject/.test(b.getAttribute('aria-label')||b.innerText||'');});
if(go&&r&&r.form){r.form.submit();done=true;}else if(go&&n){n.click();done=true;}
var v=document.querySelector('video');var p=document.querySelector('.ad-showing');var a=!!p;
if(v){v.muted=true;if(v.paused&&!a){var x=v.play();if(x&&x.catch){x.catch(function(){});}}}
var e=document.querySelector('.ytp-error, yt-playability-error-supported-renderers');
return {page:c,dialog:!!(r||n),clicked:done,has:!!v,time:v?v.currentTime:0,ad:a,
 wait:!!(v&&!v.paused&&v.readyState<3),
 fault:v&&v.error?v.error.code:0,error:e?e.innerText.slice(0,300):''};"""


def status():
    return json.loads(subprocess.run(["xgw", "status", "--json"], text=True, capture_output=True,
                                     timeout=60, check=True).stdout)


def require(ok, label):
    print(("OK " if ok else "STOP ") + label, flush=True)
    if not ok:
        raise ValueError(label)


def health():
    data = status()
    cap = data.get("capture") or {}
    require(data.get("daemon_down") is False and data.get("xray", {}).get("ok") is True
            and cap.get("mode") == "on" and cap.get("loaded") is True
            and cap.get("blocked") is False and not cap.get("capture_failed"), "on")
    code = subprocess.run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o",
                           "/dev/null", "-w", "%{http_code}", "https://1.1.1.1/"], text=True,
                          capture_output=True, timeout=12).stdout
    require(code.isdigit() and 200 <= int(code) < 400, "https")


def free_port():
    with socket.socket() as spare:
        spare.bind(("127.0.0.1", 0))
        return spare.getsockname()[1]


def build_config():
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config as xconfig
    from xgw.generator import fragment

    cfg, _warnings = xconfig.load(CONFIG)
    outbounds = {
        "direct": {"tag": "direct", "protocol": "freedom",
                   "settings": {"domainStrategy": "UseIPv4"},
                   "streamSettings": {"sockopt": {"mark": cfg.capture.mark_bypass}}},
        "fragment": {**fragment.outbound(cfg), "tag": "fragment"},
        "split": {**fragment.split_outbound(cfg), "tag": "split"},
    }
    ports = {name: free_port() for name in outbounds}
    return cfg, ports, {
        "log": {"loglevel": "none"},
        "inbounds": [{"tag": f"in-{name}", "protocol": "http", "listen": "127.0.0.1", "port": port}
                     for name, port in ports.items()],
        "outbounds": list(outbounds.values()),
        "routing": {"rules": [{"type": "field", "inboundTag": [f"in-{name}"], "outboundTag": name}
                              for name in ports]},
    }


def precheck(cfg, ports):
    urls = {"page": cfg.speed.youtube_urls[0], "video": cfg.speed.youtube_urls[-1],
            "file": cfg.speed.youtube_speed_url}
    for path in PATHS:
        via = (["--noproxy", "*"] if path == "normal" else
               ["--proxy", f"http://127.0.0.1:{ports[path]}"])
        for name, url in urls.items():
            done = subprocess.run(
                ["curl", "--silent", *via, "--max-time", "15", "-L", "--max-redirs", "4", "-r",
                 "0-2097151", "-o", "/dev/null", "-w", "%{http_code} %{time_starttransfer} "
                 "%{speed_download}", url], text=True, capture_output=True, timeout=20, check=False)
            code, first, rate = ([*done.stdout.split(), "-", "0", "0"])[:3]
            print(f"PRECHECK path={path} url={name} curl={done.returncode} code={code} "
                  f"first_s={float(first):.1f} mbps={float(rate) * 8 / 1e6:.1f}", flush=True)


def start_xray(base, config, ports):
    path = Path(base).resolve() / "temp-xray.json"
    path.touch(mode=0o600)
    path.write_text(json.dumps(config), encoding="utf-8")
    process = subprocess.Popen([str(XRAY), "run", "-c", str(path)], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.monotonic() + 15
    while process.poll() is None and time.monotonic() < end:
        with contextlib.suppress(OSError):
            for port in ports.values():
                socket.create_connection(("127.0.0.1", port), timeout=2).close()
            return process, path
        time.sleep(0.3)
    process.kill()
    process.wait()
    path.unlink(missing_ok=True)
    return None, path


class Mario:
    def __init__(self, port):
        end = time.monotonic() + 45
        while not hasattr(self, "sock"):
            with contextlib.suppress(OSError):
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
            if time.monotonic() > end:
                raise OSError("no marionette")
            time.sleep(0.5)
        self.sock.settimeout(60)
        self.number = 0
        self.read()
        self.call("WebDriver:NewSession", {"capabilities": {"alwaysMatch": {
            "pageLoadStrategy": "eager", "timeouts": {"pageLoad": 45000, "script": 15000}}}})

    def exact(self, need):
        data = b""
        while len(data) < need:
            chunk = self.sock.recv(need - len(data))
            if not chunk:
                raise OSError("closed")
            data += chunk
        return data

    def read(self):
        size = b""
        while not size.endswith(b":"):
            size += self.exact(1)
        return json.loads(self.exact(int(size[:-1])))

    def call(self, name, params):
        self.number += 1
        body = json.dumps([0, self.number, name, params]).encode()
        self.sock.sendall(b"%d:%s" % (len(body), body))
        while True:
            reply = self.read()
            if reply[0] == 1 and reply[1] == self.number:
                if reply[2]:
                    raise ValueError("marionette")
                return reply[3]


def classify(text):
    low = (text or "").lower()
    pairs = (("not a bot", "bot"), ("sign in", "sign_in"), ("unavailable", "unavailable"),
             ("isn't available", "unavailable"), ("not available", "unavailable"))
    return next((label for mark, label in pairs if mark in low),
                "player_error" if low.strip() else None)


def watch(client):
    began = time.monotonic()
    seen, ready, clicks, first, stalls = "no_video", 0.0, 0, None, 0
    while time.monotonic() - began < TRIAL:
        time.sleep(2)
        with contextlib.suppress(ValueError):  # страница могла смениться во время запроса
            go = clicks < 3 and time.monotonic() >= ready  # только отказ и не чаще раза в 15 с
            state = client.call("WebDriver:ExecuteScript", {"script": PROBE, "args": [go]})
            state = state.get("value") or {}
            if state.get("clicked"):
                clicks, ready = clicks + 1, time.monotonic() + 15
            refused = classify(state.get("error"))
            if refused or state.get("fault"):
                return refused or f"media_err_{state['fault']}", first, stalls
            if state.get("ad"):
                seen = "ad"
                continue
            if state.get("time", 0) > 0 and first is None:
                first = time.monotonic() - began
            stalls += bool(first is not None and state.get("wait"))
            if state.get("time", 0) >= PLAY_GOAL:
                return "played", first, stalls
            seen = ("consent_page" if state.get("page") else
                    "consent_dialog" if state.get("dialog") else
                    "stuck" if state.get("has") else seen)
    return seen, first, stalls


def trial(base, firefox, proxy, video):
    user, port = pwd.getpwnam(os.environ["SUDO_USER"]), free_port()
    profile = Path(base).resolve() / f"w{time.time_ns()}"
    profile.mkdir(mode=0o700)
    os.chown(profile, user.pw_uid, user.pw_gid)
    prefs = {"marionette.port": port, "media.autoplay.default": 0,
             "media.autoplay.blocking_policy": 0, "intl.accept_languages": '"en-US"'}
    if proxy is not None:
        prefs.update({"network.proxy.type": 1, "network.proxy.http": '"127.0.0.1"',
                      "network.proxy.http_port": proxy, "network.proxy.ssl": '"127.0.0.1"',
                      "network.proxy.ssl_port": proxy})
    (profile / "user.js").write_text("".join(
        f'user_pref("{key}", {value});\n' for key, value in prefs.items()), encoding="utf-8")
    os.chown(profile / "user.js", user.pw_uid, user.pw_gid)
    place = f"/run/user/{user.pw_uid}"
    process = subprocess.Popen(
        ["runuser", "-u", user.pw_name, "--", "env", f"HOME={user.pw_dir}",
         f"XDG_RUNTIME_DIR={place}", f"PATH={SEARCH}", "MOZ_HEADLESS_WIDTH=854",
         "MOZ_HEADLESS_HEIGHT=480", f"DBUS_SESSION_BUS_ADDRESS=unix:path={place}/bus",
         firefox, "--headless", "--marionette", "--no-remote", "--profile", str(profile)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stage, loaded = "no_marionette", True
    try:
        client = Mario(port)
        stage = "navigate_hang"
        try:
            client.call("WebDriver:Navigate",
                        {"url": f"https://www.youtube.com/watch?v={video}&hl=en"})
        except ValueError:  # страница не загрузилась: это итог пути, а не сбой браузера
            loaded = False
        stage = "script_hang"
        got = watch(client)
        return ("page_not_loaded", *got[1:]) if not loaded and got[0] == "no_video" else got
    except (OSError, ValueError):
        return ("browser_died" if process.poll() is not None else stage), None, 0
    finally:
        subprocess.run(["pkill", "-KILL", "-f", str(profile)], check=False, capture_output=True)
        process.kill()
        process.wait()
        shutil.rmtree(profile, ignore_errors=True)


def run(base):
    health()
    require(os.environ.get("SUDO_USER", "root") != "root", "user")
    firefox = shutil.which("firefox", path=SEARCH)
    if not firefox or not XRAY.is_file():
        print("NOT_RUN " + ("no_browser" if not firefox else "no_xray"), flush=True)
        return 4
    cfg, ports, config = build_config()
    process, config_file = start_xray(base, config, ports)
    require(process is not None, "temp_xray")
    began, played, known = time.monotonic(), dict.fromkeys(PATHS, 0), dict.fromkeys(PATHS, 0)
    try:
        precheck(cfg, ports)
        for path in PATHS:
            for label, video in VIDEOS:
                if time.monotonic() - began > DEADLINE:
                    break
                start = time.monotonic()
                result, first, stalls = trial(base, firefox, ports.get(path), video)
                played[path] += result == "played"
                known[path] += result not in UNMEASURED
                print(f"TRIAL path={path} video={label} result={result} start_s="
                      f"{'-' if first is None else round(first)} stalls={stalls} "
                      f"seconds={time.monotonic() - start:.0f}", flush=True)
    finally:
        process.kill()
        process.wait()
        config_file.unlink(missing_ok=True)
    print("INFO " + " ".join(f"{name}={played[name]}/{known[name]}" for name in PATHS)
          + f" minutes={(time.monotonic() - began) / 60:.1f}", flush=True)
    health()
    if played["normal"] < 2:
        print("NOT_RUN no_playback", flush=True)
        return 4
    tricks = max(played["fragment"], played["split"])
    if played["direct"] < NEED and tricks < NEED and min(known[p] for p in PATHS[1:]) < NEED:
        print("NOT_RUN direct_unmeasured", flush=True)
        return 4
    print("RESULT " + ("direct_ok" if played["direct"] >= NEED else
                       "fragment_ok" if tricks >= NEED else "none_ok"), flush=True)
    return 0


def main():
    args = sys.argv[1:]
    return (health() or 0) if args == ["health"] else (
        run(args[1]) if len(args) == 2 and args[0] == "run" else 2)


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # текст ошибки может содержать адрес
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
