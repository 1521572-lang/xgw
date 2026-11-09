"""Играют ли ссылки youtube.com/watch в Firefox без окна: обычным путём шлюза, напрямую с домашнего
адреса и напрямую с дроблением ClientHello. Режимы: health | run КАТАЛОГ. Настройки шлюза не
меняются: временный Xray слушает только 127.0.0.1 и живёт, пока идёт проверка."""
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
DEADLINE = 45 * 60.0
NEED = 3  # роликов из четырёх, чтобы считать путь рабочим
VIDEOS = (("plain1", "aqz-KE-bpKQ"), ("plain2", "M7lc1UVf-VE"),
          ("music1", "dQw4w9WgXcQ"), ("music2", "9bZkp7q19f0"))
PATHS = ("normal", "direct", "fragment", "split")
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
    """Конфиг временного Xray: те же метка и параметры дробления, что у XGW. Порты — по путям."""
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
    return {
        "log": {"loglevel": "none"},
        "inbounds": [{"tag": f"in-{name}", "protocol": "http", "listen": "127.0.0.1", "port": port}
                     for name, port in ports.items()],
        "outbounds": list(outbounds.values()),
        "routing": {"rules": [{"type": "field", "inboundTag": [f"in-{name}"], "outboundTag": name}
                              for name in ports]},
    }, ports


def start_xray(base, config, ports):
    path = Path(base).resolve() / "temp-xray.json"
    path.touch(mode=0o600)
    path.write_text(json.dumps(config), encoding="utf-8")
    process = subprocess.Popen([str(XRAY), "run", "-c", str(path)], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.monotonic() + 15
    for port in ports.values():
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=2).close()
                break
            except OSError:
                if time.monotonic() > end or process.poll() is not None:
                    process.kill()
                    process.wait()
                    path.unlink(missing_ok=True)
                    return None, path
                time.sleep(0.3)
    return process, path


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
    """(итог, секунд до старта видео или None, опросов с ожиданием данных)."""
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
    try:
        client = Mario(port)
        with contextlib.suppress(ValueError):  # не догрузилась: решает состояние плеера
            client.call("WebDriver:Navigate",
                        {"url": f"https://www.youtube.com/watch?v={video}&hl=en"})
        return watch(client)
    except (OSError, ValueError):
        return "no_browser", None, 0
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
    config, ports = build_config()
    process, config_file = start_xray(base, config, ports)
    require(process is not None, "temp_xray")
    began, played = time.monotonic(), dict.fromkeys(PATHS, 0)
    try:
        for path in PATHS:
            for label, video in VIDEOS:
                if time.monotonic() - began > DEADLINE:
                    break
                start = time.monotonic()
                result, first, stalls = trial(base, firefox, ports.get(path), video)
                played[path] += result == "played"
                start_s = "-" if first is None else f"{first:.0f}"
                print(f"TRIAL path={path} video={label} result={result} start_s={start_s} "
                      f"stalls={stalls} seconds={time.monotonic() - start:.0f}", flush=True)
    finally:
        process.kill()
        process.wait()
        config_file.unlink(missing_ok=True)
    print("INFO " + " ".join(f"{name}={played[name]}/{len(VIDEOS)}" for name in PATHS)
          + f" minutes={(time.monotonic() - began) / 60:.1f}", flush=True)
    health()
    if played["normal"] < 2:
        print("NOT_RUN no_playback", flush=True)
        return 4
    tricks = max(played["fragment"], played["split"])
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
