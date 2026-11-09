"""Играют ли настоящие ссылки youtube.com/watch в Firefox без окна: обычным путём и через отдельные
серверы. Режимы: health | run КАТАЛОГ. Настройки не меняются. Вывод — только числа и признаки."""
import base64
import collections
import contextlib
import json
import os
import pwd
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

APPLIED = Path("/etc/xgw/xray/config.json")
CRLF = (chr(13) + chr(10)).encode()
END = CRLF + CRLF
SEARCH = "/snap/bin:/usr/local/bin:/usr/bin:/bin"
TRIAL, PLAY_GOAL = 90.0, 12.0  # ролик не дольше (реклама идёт в тот же тег); столько должно сыграть
LIMIT_BYTES, DEADLINE = 500_000_000, 30 * 60.0
VIDEOS = (("plain1", "aqz-KE-bpKQ"), ("plain2", "M7lc1UVf-VE"),
          ("music1", "dQw4w9WgXcQ"), ("music2", "9bZkp7q19f0"))
PROBE = """var c=location.hostname.indexOf('consent.')===0;var done=false;var d=document;
var go=arguments[0];var r=d.querySelector('input[name=set_eom][value=true]');
var n=Array.from(document.querySelectorAll('button')).find(function(b){
 return /^Reject/.test(b.getAttribute('aria-label')||b.innerText||'');});
if(go&&r&&r.form){r.form.submit();done=true;}else if(go&&n){n.click();done=true;}
var v=document.querySelector('video');var p=document.querySelector('.ad-showing');var a=!!p;
if(v){v.muted=true;if(v.paused&&!a){var x=v.play();if(x&&x.catch){x.catch(function(){});}}}
var e=document.querySelector('.ytp-error, yt-playability-error-supported-renderers');
return {page:c,dialog:!!(r||n),clicked:done,has:!!v,time:v?v.currentTime:0,ad:a,
 fault:v&&v.error?v.error.code:0,error:e?e.innerText.slice(0,300):''};"""
ROUTE = {"server": None, "spent": 0}
Server = collections.namedtuple("Server", "port password")


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


def read_head(sock):
    head = b""
    while END not in head and len(head) < 16384:
        chunk = sock.recv(4096)
        if not chunk:
            raise OSError("closed")
        head += chunk
    return head.split(None, 2)


def tunnel(server, host, port):
    raw = socket.create_connection(("127.0.0.1", server.port), timeout=15)
    raw.settimeout(15)
    token = base64.b64encode(f"xgw:{server.password}".encode())
    raw.sendall(b"CONNECT %s:%d HTTP/1.1%sHost: %s:%d%sProxy-Authorization: Basic %s%s" % (
        host.encode(), port, CRLF, host.encode(), port, CRLF, token, END))
    words = read_head(raw)
    if len(words) < 2 or words[1] != b"200":
        raise OSError("connect refused")
    return raw


def pump(source, target):
    with contextlib.suppress(OSError):
        while data := source.recv(65536):
            target.sendall(data)
            ROUTE["spent"] += len(data)
    for item in (source, target):
        with contextlib.suppress(OSError):
            item.shutdown(socket.SHUT_RDWR)


class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        sock.settimeout(120)
        try:
            words = read_head(sock)
            host, _colon, port = words[1].decode("latin-1").rpartition(":")
            server = ROUTE["server"]
            if words[0] != b"CONNECT" or server is None or ROUTE["spent"] > LIMIT_BYTES:
                raise OSError("refused")
            upstream = tunnel(server, host, int(port))
        except (OSError, ValueError, IndexError):
            with contextlib.suppress(OSError):
                sock.sendall(b"HTTP/1.1 502 No" + END)
            return
        upstream.settimeout(120)
        sock.sendall(b"HTTP/1.1 200 OK" + END)
        threading.Thread(target=pump, args=(upstream, sock), daemon=True).start()
        pump(sock, upstream)


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
    end, seen, ready, clicks = time.monotonic() + TRIAL, "no_video", 0.0, 0
    while time.monotonic() < end:
        time.sleep(2)
        with contextlib.suppress(ValueError):  # страница могла смениться во время запроса
            go = clicks < 3 and time.monotonic() >= ready  # только отказ и не чаще раза в 15 с
            state = client.call("WebDriver:ExecuteScript", {"script": PROBE, "args": [go]})
            state = state.get("value") or {}
            if state.get("clicked"):
                clicks, ready = clicks + 1, time.monotonic() + 15
            if classify(state.get("error")):
                return classify(state.get("error"))
            if state.get("fault"):
                return f"media_err_{state['fault']}"
            if state.get("ad"):
                seen = "ad"
            elif state.get("time", 0) >= PLAY_GOAL:
                return "played"
            else:
                seen = ("consent_page" if state.get("page") else
                        "consent_dialog" if state.get("dialog") else
                        "stuck" if state.get("has") else seen)
    return seen


def trial(base, firefox, proxy, server, video):
    ROUTE["server"] = server
    user = pwd.getpwnam(os.environ["SUDO_USER"])
    with socket.socket() as spare:  # свободный порт, а не занятый служебным входом
        spare.bind(("127.0.0.1", 0))
        port = spare.getsockname()[1]
    profile = Path(base).resolve() / f"w{time.time_ns()}"
    profile.mkdir(mode=0o700)
    os.chown(profile, user.pw_uid, user.pw_gid)
    prefs = {"marionette.port": port, "media.autoplay.default": 0,
             "media.autoplay.blocking_policy": 0, "intl.accept_languages": '"en-US"'}
    if server is not None:
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
        return "no_browser"
    finally:
        subprocess.run(["pkill", "-KILL", "-f", str(profile)], check=False, capture_output=True)
        process.kill()
        process.wait()
        shutil.rmtree(profile, ignore_errors=True)


def usable():
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw.generator import builder

    applied = json.loads(APPLIED.read_bytes())
    password, _ports = builder.probe_state(applied)
    rows = {row.get("tag"): row for row in status().get("members") or []}
    found = [info for info in builder.applied_nodes(applied)
             if password and info.role == "proxy" and info.probe_port
             and rows.get(info.tag, {}).get("alive") and rows.get(info.tag, {}).get("cost") == 0]
    found.sort(key=lambda info: -(rows[info.tag].get("speed_mbps") or 0))
    return [Server(info.probe_port, password) for info in found[:5]]


def one(base, firefox, proxy, server, path, label, video, began):
    if time.monotonic() - began > DEADLINE or ROUTE["spent"] > LIMIT_BYTES:
        return None
    start = time.monotonic()
    result = trial(base, firefox, proxy, server, video)
    print(f"TRIAL path={path} video={label} result={result} "
          f"seconds={time.monotonic() - start:.0f}", flush=True)
    return result


def run(base):
    health()
    require(os.environ.get("SUDO_USER", "root") != "root", "user")
    firefox = shutil.which("firefox", path=SEARCH)
    if not firefox:
        print("NOT_RUN no_browser", flush=True)
        return 4
    began = time.monotonic()
    listener = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Forward)
    listener.daemon_threads = True
    threading.Thread(target=listener.serve_forever, daemon=True).start()
    chosen, port = usable(), listener.server_address[1]
    normal = [one(base, firefox, port, None, "normal", *item, began) for item in VIDEOS]
    per_server = []
    for index, server in enumerate(chosen, 1):
        pair = (VIDEOS[index % 2], VIDEOS[2 + index % 2])
        results = [one(base, firefox, port, server, f"S{index}", *item, began) for item in pair]
        per_server.append(results.count("played"))
    played = normal.count("played")
    print(f"INFO normal_played={played}/{len(VIDEOS)} servers_played={per_server} "
          f"mb={ROUTE['spent'] / 1_000_000:.1f} minutes={(time.monotonic() - began) / 60:.1f}",
          flush=True)
    health()
    good = sum(count > 0 for count in per_server)
    if len(chosen) < 2 or not (good or played):
        print("NOT_RUN " + ("few_servers" if len(chosen) < 2 else "no_playback"), flush=True)
        return 4
    print("RESULT " + ("all_accept" if good == len(chosen) else
                       "none_accept" if not good else "some_accept"), flush=True)
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
