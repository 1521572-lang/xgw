#!/usr/bin/python3
"""Temporary, allowlisted nfqws2 launcher for the real-machine YouTube test plan."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath

STRATEGIES = {
    "pass": (),
    "split-2": ("multisplit:pos=2",),
    "split-sniext": ("multisplit:pos=2,sniext+1",),
    "split-midsld": ("multisplit:pos=1,midsld",),
    "disorder": ("multidisorder:pos=1,midsld",),
    "seqovl": ("multisplit:pos=2,sniext+1:seqovl=679",),
    "seqovl-small": ("multisplit:pos=2,sniext+1:seqovl=1",),
    "hostfakesplit-md5": ("hostfakesplit:midhost=midsld:tcp_md5",),
    "fakedsplit-md5": ("fakedsplit:pos=midsld:tcp_md5",),
    "hostfakesplit-badseq": ("hostfakesplit:midhost=midsld:tcp_seq=-10000",),
    "hostfakesplit-ts": ("hostfakesplit:midhost=midsld:tcp_ts=+100",),
    "fake-md5-split": (
        "fake:blob=fake_default_tls:tls_mod=rnd,dupsid,sni=www.google.com:tcp_md5",
        "multisplit:pos=1,midsld",
    ),
    "fake-badseq-disorder": (
        "fake:blob=fake_default_tls:tls_mod=rnd,dupsid,sni=www.google.com:tcp_seq=-10000",
        "multidisorder:pos=1,midsld",
    ),
    "hostfakesplit-md5-repeat": ("hostfakesplit:midhost=midsld:tcp_md5:repeats=2",),
    "hostfakesplit-md5-nosplit": ("hostfakesplit:tcp_md5",),
    "fake-static-md5": (
        "fake:blob=fake_default_tls:optional:tls_mod=rnd,rndsni:tcp_md5",
        "multisplit:pos=1,midsld",
    ),
    "fake-clone-md5": (
        "tls_client_hello_clone:blob=xgw_tls_clone",
        "fake:blob=xgw_tls_clone:optional:tls_mod=rnd,rndsni:tcp_md5",
        "multisplit:pos=1,midsld",
    ),
}
FIELDS = {"binary", "strategy", "reassembly", "debug", "domains"}
DOMAIN = re.compile(r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")


def settings_check(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("settings_schema")
    binary = value["binary"]
    if (not isinstance(binary, str) or not PurePosixPath(binary).is_absolute()
            or any(c in binary for c in "\r\n\x00")):
        raise ValueError("binary_path")
    if not isinstance(value["strategy"], str) or value["strategy"] not in STRATEGIES:
        raise ValueError("strategy")
    if value["reassembly"] not in ("standard", "disabled") or type(value["debug"]) is not bool:
        raise ValueError("settings_type")
    domains = value["domains"]
    if not isinstance(domains, list) or not 1 <= len(domains) <= 16:
        raise ValueError("domains")
    for name in domains:
        if (not isinstance(name, str) or not DOMAIN.fullmatch(name) or "." not in name
                or any(not label or len(label) > 63 or label.startswith("-")
                       or label.endswith("-") for label in name.split("."))):
            raise ValueError("domains")
        try:
            ipaddress.ip_address(name)
        except ValueError:
            pass
        else:
            raise ValueError("domains")
    return value


def secure_file(path: Path, *, private: bool = False, executable: bool = False) -> None:
    """Reject symlinks and writable ancestors before executing root-controlled input."""
    if not path.is_absolute():
        raise ValueError("unsafe_path")
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        directory = item != path
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
            raise ValueError("unsafe_file")
    info = path.lstat()
    if private and stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("settings_permissions")
    if executable and not os.access(path, os.X_OK):
        raise ValueError("not_executable")


def build_arguments(incoming: list[str], settings: dict) -> list[str]:
    """Keep XGW's queue/mark/Lua, replacing its protocol blocks by one TLS experiment."""
    settings_check(settings)
    if len(incoming) < 5:
        raise ValueError("runtime_arguments")
    qnum, mark, lib, antidpi = incoming[:4]
    if not re.fullmatch(r"--qnum=[0-9]+", qnum) or not 1 <= int(qnum[7:]) <= 65535:
        raise ValueError("runtime_queue")
    if mark != "--fwmark=0x40000000":
        raise ValueError("runtime_mark")
    for arg, filename in ((lib, "zapret-lib.lua"), (antidpi, "zapret-antidpi.lua")):
        if not arg.startswith("--lua-init=@"):
            raise ValueError("runtime_lua")
        path = PurePosixPath(arg.removeprefix("--lua-init=@"))
        if not path.is_absolute() or path.name != filename:
            raise ValueError("runtime_lua")
    if not incoming[4].startswith("--filter-tcp="):
        raise ValueError("runtime_filter")
    preflight = incoming[-1] if incoming[-1] in ("--dry-run", "--intercept=0") else ""
    body = incoming[4:-1] if preflight else incoming[4:]
    allowed = ("--filter-tcp=", "--filter-udp=", "--filter-l7=", "--payload=",
               "--lua-desync=", "--blob=")
    if any(arg != "--new" and not arg.startswith(allowed) for arg in body):
        raise ValueError("runtime_option")
    if any(any(c in arg for c in "\r\n\x00") for arg in incoming):
        raise ValueError("runtime_character")
    args = [settings["binary"], qnum, mark, lib, antidpi,
            "--debug=1" if settings["debug"] else "--debug=0"]
    if settings["reassembly"] == "disabled":
        args.append("--reasm-disable=tls_client_hello")
    args += ["--filter-tcp=443", "--filter-l7=tls",
             "--hostlist-domains=" + ",".join(dict.fromkeys(settings["domains"])),
             "--payload=tls_client_hello"]
    args += ["--lua-desync=" + call for call in STRATEGIES[settings["strategy"]]]
    if preflight:
        args.append(preflight)
    return args


def main() -> int:
    if sys.argv[1:] == ["--list"]:
        print(json.dumps(STRATEGIES, indent=2))
        return 0
    try:
        if os.geteuid() != 0:
            raise ValueError("root_required")
        script = Path(__file__).absolute()
        secure_file(script, executable=True)
        path = script.with_suffix(".json")
        secure_file(path, private=True)
        settings = settings_check(json.loads(path.read_text(encoding="utf-8")))
        binary = Path(settings["binary"])
        secure_file(binary, executable=True)
        if binary.samefile(script):
            raise ValueError("recursive_binary")
        args = build_arguments(sys.argv[1:], settings)
        for arg in args:
            if arg.startswith("--lua-init=@"):
                secure_file(Path(arg.removeprefix("--lua-init=@")))
        os.execv(str(binary), args)
    except (OSError, ValueError, TypeError):
        print("nfq_lab: invalid or inaccessible settings/runtime files", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
