"""Small Linux-only gate. Must run via unshare -n; no host routes/rules/users changed."""

import dataclasses
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = (
    Path(__file__).resolve().parents[2]
    if Path(__file__).parent.name == "stand"
    else Path(__file__).parent / "xgw-wave3"
)
sys.path.insert(0, str(ROOT / "src"))
from xgw.config import Config  # noqa: E402
from xgw.net import nft  # noqa: E402


def run(argv, *, input=None, **kwargs):
    result = subprocess.run(argv, input=input, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(f"{argv}: {result.stderr}")
    return result.stdout


assert os.geteuid() == 0
assert os.readlink("/proc/self/ns/net") != os.readlink(f"/proc/{os.getppid()}/ns/net"), (
    "Refusing host network namespace: use unshare -n"
)

child_code = """import socket,sys,threading,subprocess
print('NAMESPACE',flush=True)
sys.stdin.readline()
commands = [['ip','link','set','lo','up'],
 ['ip','addr','add','198.18.0.2/24','dev','peer0'],['ip','link','set','peer0','up']]
for a in commands:
 subprocess.run(a,check=True)
s=socket.socket();s.bind(('198.18.0.2',23456));s.listen(20);s.settimeout(.2)
stop=threading.Event()
def serve():
 while not stop.is_set():
  try:c,_=s.accept();c.close()
  except socket.timeout:pass
t=threading.Thread(target=serve);t.start();print('LISTEN',flush=True)
sys.stdin.readline();stop.set();t.join();s.close()
"""
peer = subprocess.Popen(
    ["unshare", "-n", sys.executable, "-u", "-c", child_code],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
evidence = []
try:
    assert peer.stdout.readline().strip() == "NAMESPACE"
    run(["ip", "link", "set", "lo", "up"])
    run(["ip", "link", "add", "wan0", "type", "veth", "peer", "name", "peer0"])
    run(["ip", "link", "set", "peer0", "netns", str(peer.pid)])
    run(["ip", "addr", "add", "198.18.0.1/24", "dev", "wan0"])
    run(["ip", "link", "set", "wan0", "up"])
    peer.stdin.write("GO\n")
    peer.stdin.flush()
    assert peer.stdout.readline().strip() == "LISTEN"
    cfg = Config()
    cfg.capture.local = True
    cfg.capture.lan = False
    cfg.network.wan_if = "wan0"
    cfg.network.lan_if = ""
    cfg.capture.containers = False
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    rules = dataclasses.replace(
        rules, singbox_uid=65534, direct4=("198.18.0.0/24",), direct_local=True
    )

    def connect(mark=None):
        with socket.socket() as s:
            s.settimeout(1)
            if mark is not None:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, mark)
            try:
                s.connect(("198.18.0.2", 23456))
                return True
            except (ConnectionRefusedError, TimeoutError):
                return False

    # Syntax and live listing normalization, including actual kernel formatting.
    for blocked in [False, True]:
        case = dataclasses.replace(
            rules,
            blocked=blocked,
            capture_local=not blocked,
            block_local=blocked,
            direct4=() if blocked else rules.direct4,
        )
        text = nft.render(case) + nft.render6(case) + nft.render_guard(case)
        run(["nft", "-c", "-f", "-"], input=text)
    nft.apply(rules, run)
    guard_before = nft.structure(nft.listing(run, "inet", nft.GUARD), "inet", nft.GUARD)
    assert (
        nft.manifest_problem(
            nft.manifest(nft.render_guard(rules), "inet", nft.GUARD),
            nft.manifest(guard_before, "inet", nft.GUARD),
            "guard",
        )
        == ""
    )
    assert connect(), "Capture-authorized direct fixture must connect"
    evidence.append("authorized direct path works before capture-table deletion")
    run(["nft", "delete", "table", "ip", nft.TABLE])
    assert not connect(), "New unauthorized plain TCP escaped the surviving guard"
    assert connect(rules.mark_bypass), "Core marked TCP incorrectly rejected"
    evidence.append("after deleting ip xgw: new plain TCP blocked, core-marked TCP connects")
    guard_after = nft.structure(nft.listing(run, "inet", nft.GUARD), "inet", nft.GUARD)
    assert guard_before == guard_after

    # A failing transaction must not remove the independent barrier.
    failed = subprocess.run(
        ["nft", "-f", "-"],
        input="delete table inet " + nft.GUARD + "\ninvalid_token\n",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert failed.returncode != 0
    assert nft.structure(nft.listing(run, "inet", nft.GUARD), "inet", nft.GUARD) == guard_after
    evidence.append("invalid nft transaction preserves independent guard")

    # Numeric unprivileged UID models the service; no real account is created.
    local = socket.socket()
    local.bind(("127.0.0.1", 23457))
    local.listen()
    uid_code = """import os,socket,json
os.setgroups([]);os.setgid(65534);os.setuid(65534)
def dial(host,port):
 s=socket.socket();s.settimeout(1)
 try:s.connect((host,port));return True
 except (ConnectionRefusedError,TimeoutError):return False
 finally:s.close()
print(json.dumps([dial('198.18.0.2',23456),dial('127.0.0.1',23457)]))
"""
    assert json.loads(run([sys.executable, "-c", uid_code])) == [True, False]
    local.close()
    evidence.append("unprivileged service UID egress works, loopback access rejected")
    # Replies by a dedicated-UID SOCKS/API listener must still work: only its
    # newly initiated loopback connections are prohibited.
    uid_listener = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            """import os,socket
os.setgroups([]);os.setgid(65534);os.setuid(65534)
s=socket.socket();s.bind(('127.0.0.1',23458));s.listen();print('READY',flush=True)
c,_=s.accept();c.sendall(b'uid-reply-ok');c.close();s.close()
""",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert uid_listener.stdout.readline().strip() == "READY"
        with socket.create_connection(("127.0.0.1", 23458), timeout=1) as incoming:
            assert incoming.recv(64) == b"uid-reply-ok"
        assert uid_listener.wait(timeout=2) == 0
    finally:
        if uid_listener.poll() is None:
            uid_listener.kill()
            uid_listener.wait(timeout=2)
    evidence.append("unprivileged service UID can reply on an accepted loopback connection")
    print(
        json.dumps(
            {
                "status": "PASS",
                "scope": "isolated WSL Linux namespaces; IPv4 veth fixture",
                "checks": evidence,
                "physical_WAN_and_actual_systemd_migration": "NOT_RUN",
            },
            indent=2,
        )
    )
finally:
    if peer.poll() is None:
        try:
            peer.stdin.write("STOP\n")
            peer.stdin.flush()
            peer.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            peer.kill()
            peer.wait(timeout=3)
