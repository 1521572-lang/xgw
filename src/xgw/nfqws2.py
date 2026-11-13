"""Универсальный L3/L4-движок nfqws2, отдельный от selective-режима zapret2."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .net import cmd

if TYPE_CHECKING:
    from .config import Config

FAKE_MARK = 0x40000000
UNIT = "xgw-nfqws2.service"
PROFILES = ("seqovl", "hostfakesplit", "disorder-badseq")
BLOBS = (
    "tls_clienthello_www_google_com.bin",
    "quic_initial_www_google_com.bin",
    "stun.bin",
)
OFFLOADS = ("generic-receive-offload", "generic-segmentation-offload",
            "tcp-segmentation-offload", "tx-checksum-ip-generic")


@dataclass(frozen=True)
class Installation:
    binary: Path
    lua_dir: Path
    blobs: dict[str, Path | None]


def validate(cfg: Config) -> list[str]:
    z = cfg.zapret2
    warnings = []
    if z.engine not in ("auto", "off"):
        warnings.append("zapret2.engine: ожидается auto или off — выключен")
        z.engine = "off"
    if z.engine_profile not in PROFILES:
        warnings.append("zapret2.engine_profile: неизвестный профиль — seqovl")
        z.engine_profile = "seqovl"
    if not 1 <= z.engine_queue <= 65535:
        warnings.append("zapret2.engine_queue: ожидается 1–65535 — 200")
        z.engine_queue = 200
    if z.blob_dir and (not z.blob_dir.startswith("/")
                       or any(char in z.blob_dir for char in "\r\n\x00")):
        warnings.append("zapret2.blob_dir: нужен абсолютный Linux-путь — автопоиск")
        z.blob_dir = ""
    return warnings


def enabled(cfg: Config) -> bool:
    return cfg.zapret2.engine == "auto" and not cfg.zapret2.probe_enabled


def find_binary(cfg: Config) -> Path | None:
    candidates = [Path(cfg.zapret2.binary)]
    explicit = os.environ.get("XGW_NFQWS2_BIN")
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(sorted(Path("/opt/xgw/zapret2").glob("*/nfqws2"), reverse=True))
    candidates.extend((Path("/usr/local/sbin/nfqws2"), Path("/usr/sbin/nfqws2")))
    found = shutil.which("nfqws2")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        except OSError:
            continue
    return None


def find_installation(cfg: Config) -> Installation | None:
    binary = find_binary(cfg)
    if binary is None:
        return None
    lua_candidates = [Path(cfg.zapret2.lua_dir), binary.parent / "lua",
                      binary.parent.parent / "lua"]
    lua_dir = next((directory for directory in lua_candidates
                    if (directory / "zapret-lib.lua").is_file()
                    and (directory / "zapret-antidpi.lua").is_file()), None)
    if lua_dir is None:
        return None
    blob_candidates = []
    if cfg.zapret2.blob_dir:
        blob_candidates.append(Path(cfg.zapret2.blob_dir))
    blob_candidates.extend((binary.parent / "blobs", binary.parent / "files",
                            lua_dir.parent / "blobs", lua_dir.parent / "files"))
    blobs: dict[str, Path | None] = {}
    for name in BLOBS:
        blobs[name] = next((directory / name for directory in blob_candidates
                            if (directory / name).is_file()), None)
    return Installation(binary, lua_dir, blobs)


def _ports(values: Collection[str]) -> str:
    return ",".join(dict.fromkeys(value.strip() for value in values if value.strip()))


def stun_ports(cfg: Config) -> list[str]:
    ports = []
    for endpoint in cfg.network.stun_servers:
        _host, separator, port = endpoint.rpartition(":")
        if separator and port.isdigit():
            ports.append(port)
    return ports


def arguments(cfg: Config, installation: Installation, profile: str | None = None) -> list[str]:
    profile = (profile or cfg.zapret2.engine_profile).removeprefix("nfqws2:")
    if profile not in PROFILES:
        raise ValueError("unknown_profile")
    args = [str(installation.binary), f"--qnum={cfg.zapret2.engine_queue}",
            f"--fwmark={FAKE_MARK:#x}",
            f"--lua-init=@{installation.lua_dir / 'zapret-lib.lua'}",
            f"--lua-init=@{installation.lua_dir / 'zapret-antidpi.lua'}"]
    tcp = _ports(["443", *cfg.routing.cloudflare_tcp_ports])
    args += [f"--filter-tcp={tcp}", "--filter-l7=tls", "--payload=tls_client_hello"]
    if profile == "seqovl":
        args.append("--lua-desync=multisplit:pos=2,sniext+1:seqovl=679")
    elif profile == "hostfakesplit":
        args += [
            "--lua-desync=fake:blob=fake_default_tls:tls_mod=rnd,dupsid,sni=www.google.com:"
            "tcp_ts=+100",
            "--lua-desync=hostfakesplit:host=www.google.com:altorder=1:tcp_ts=+100",
        ]
    else:
        args += [
            "--lua-desync=fake:blob=fake_default_tls:tls_mod=rnd,dupsid,sni=www.google.com:"
            "tcp_seq=-10000",
            "--lua-desync=multidisorder:pos=1,midsld",
        ]
    args += ["--filter-udp=443", "--filter-l7=quic", "--payload=quic_initial",
             "--lua-desync=fake:repeats=2:blob=fake_default_quic"]
    voice = _ports(cfg.routing.discord_udp_ports)
    if voice:
        args += [f"--filter-udp={voice}", "--filter-l7=discord,stun",
                 "--payload=discord_ip_discovery,stun",
                 "--lua-desync=fake:repeats=2:blob=fake_default_quic"]
    stun = stun_ports(cfg)
    stun_blob = installation.blobs["stun.bin"]
    if stun and stun_blob:
        args += [f"--blob=fake_default_stun:@{stun_blob}", f"--filter-udp={_ports(stun)}",
                 "--filter-l7=stun", "--payload=stun",
                 "--lua-desync=fake:repeats=2:blob=fake_default_stun"]
    return args


class Offload:
    def __init__(self, runner=cmd.run):
        self.runner = runner
        self.interface = ""
        self.saved: dict[str, bool] = {}

    def wan_interface(self) -> str:
        result = self.runner(["ip", "-j", "route", "show", "default"], timeout=5)
        for route in json.loads(result or "[]"):
            if isinstance(route, dict) and route.get("dev"):
                return str(route["dev"])
        raise ValueError("offload_interface")

    @staticmethod
    def _enabled(value: str) -> bool:
        return value.split(":", 1)[-1].strip().split()[0] == "on"

    def disable(self, interface: str) -> None:
        interface = interface or self.wan_interface()
        listing = self.runner(["ethtool", "-k", interface], timeout=10)
        current = {line.split(":", 1)[0].strip(): self._enabled(line)
                   for line in listing.splitlines() if ":" in line}
        changes = {name: current[name] for name in OFFLOADS if current.get(name)}
        if changes:
            args = ["ethtool", "-K", interface]
            for name in changes:
                args += [name, "off"]
            self.runner(args, timeout=10)
        self.interface, self.saved = interface, changes

    def restore(self) -> None:
        if not self.interface:
            return
        args = ["ethtool", "-K", self.interface]
        for name, enabled_before in self.saved.items():
            args += [name, "on" if enabled_before else "off"]
        if self.saved:
            self.runner(args, timeout=10)
        self.interface, self.saved = "", {}


class Runtime:
    QUEUE_STATE = Path("/proc/net/netfilter/nfnetlink_queue")

    def __init__(self, runner=cmd.run):
        self.runner = runner
        self.offload = Offload(runner)
        self.key: tuple[str, int, str] | None = None

    @classmethod
    def occupied(cls, queue: int) -> bool:
        try:
            lines = cls.QUEUE_STATE.read_text().splitlines()
        except OSError:
            return False
        return any(line.split() and line.split()[0] == str(queue) for line in lines)

    def alive(self, queue: int) -> bool:
        state = self.runner(["systemctl", "is-active", UNIT], check=False, timeout=5).strip()
        return state == "active" and self.occupied(queue)

    @staticmethod
    def _check_files(installation: Installation) -> None:
        for name in (installation.binary, installation.lua_dir / "zapret-lib.lua",
                     installation.lua_dir / "zapret-antidpi.lua",
                     *(path for path in installation.blobs.values() if path)):
            path = name.resolve(strict=True)
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError("unsafe_files")
            for parent in path.parents:
                info = parent.stat()
                if info.st_uid != 0 or info.st_mode & 0o022:
                    raise ValueError("unsafe_directory")

    def start(self, cfg: Config, installation: Installation, profile: str) -> None:
        if self.alive(cfg.zapret2.engine_queue):
            self.stop()
        if self.occupied(cfg.zapret2.engine_queue):
            raise ValueError("queue_busy")
        self._check_files(installation)
        args = arguments(cfg, installation, profile)
        self.runner([*args, "--intercept=0"], timeout=10)
        if cfg.zapret2.engine_offload and profile == "disorder-badseq":
            self.offload.disable(cfg.network.wan_if.strip())
        properties = [
            "Type=exec", "BindsTo=xgw.service", "After=xgw.service", "Restart=no",
            "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "NoNewPrivileges=yes",
            "CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW", "ProtectKernelTunables=yes",
            "ProtectKernelModules=yes",
            "RestrictAddressFamilies=AF_INET AF_INET6 AF_NETLINK AF_UNIX",
        ]
        try:
            self.runner(["systemd-run", "--quiet", "--collect", "--unit", UNIT,
                         *[arg for item in properties for arg in ("--property", item)], *args],
                        timeout=15)
        except Exception:
            self.offload.restore()
            raise
        self.key = (str(installation.binary), cfg.zapret2.engine_queue, profile)

    def stop(self) -> None:
        try:
            self.runner(["systemctl", "stop", UNIT], check=False, timeout=10)
            state = self.runner(["systemctl", "is-active", UNIT], check=False, timeout=5).strip()
            if state in ("active", "activating", "deactivating"):
                raise cmd.CommandError("nfqws2: остановка не подтверждена")
        finally:
            self.offload.restore()
            self.key = None


class Controller:
    def __init__(self, runtime=None):
        self.runtime = runtime or Runtime()
        self.profile = ""
        self.installation: Installation | None = None
        self.view = {"state": "off", "reason": "off"}

    @staticmethod
    def selected_profile(cfg: Config, applied: Collection[str]) -> str:
        found = {name.removeprefix("nfqws2:") for name in applied if name.startswith("nfqws2:")}
        for profile in reversed(PROFILES):
            if profile in found:
                return profile
        return cfg.zapret2.engine_profile

    def step(self, cfg: Config, applied: Collection[str], *, active: bool) -> None:
        installation = find_installation(cfg) if enabled(cfg) and active else None
        if installation is None:
            if self.profile or self.runtime.key is not None:
                try:
                    self.runtime.stop()
                except (OSError, cmd.CommandError):
                    pass
            self.profile = ""
            self.installation = None
            reason = "disabled" if not enabled(cfg) else ("inactive" if not active else "not_found")
            self.view = {"state": "off", "reason": reason}
            return
        profile = self.selected_profile(cfg, applied)
        key = (str(installation.binary), cfg.zapret2.engine_queue, profile)
        try:
            if key == self.runtime.key and self.runtime.alive(cfg.zapret2.engine_queue):
                self.view = {"state": "active", "profile": profile,
                             "queue": cfg.zapret2.engine_queue}
                return
            self.runtime.start(cfg, installation, profile)
            if not self.runtime.alive(cfg.zapret2.engine_queue):
                raise ValueError("worker_down")
        except (OSError, ValueError, cmd.CommandError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) and str(exc) in {
                "queue_busy", "unsafe_files", "unsafe_directory", "worker_down",
                "offload_interface", "unknown_profile",
            } else "runtime_failed"
            with contextlib.suppress(OSError, cmd.CommandError):
                self.runtime.stop()
            self.view = {"state": "fallback", "reason": reason, "profile": profile}
            return
        self.profile, self.installation = profile, installation
        self.view = {"state": "active", "profile": profile, "queue": cfg.zapret2.engine_queue}

    def close(self) -> None:
        self.runtime.stop()
