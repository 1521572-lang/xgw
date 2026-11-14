"""Универсальный L3/L4-движок nfqws2, отдельный от selective-режима zapret2."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
import threading
import time
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
READY_TIMEOUT = 3.0
READY_POLL = 0.1
LaunchKey = tuple[tuple[str, ...], bool, str]


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


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False  # В том числе каталог, недоступный из sandbox демона.


def find_binary(cfg: Config) -> Path | None:
    candidates = [Path(cfg.zapret2.binary)]
    explicit = os.environ.get("XGW_NFQWS2_BIN")
    if explicit:
        candidates.append(Path(explicit))
    with contextlib.suppress(OSError):
        candidates.extend(sorted(Path("/opt/xgw/zapret2").glob("*/nfqws2"), reverse=True))
    candidates.extend((Path("/usr/local/sbin/nfqws2"), Path("/usr/sbin/nfqws2")))
    found = shutil.which("nfqws2")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if _is_file(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def find_installation(cfg: Config) -> Installation | None:
    binary = find_binary(cfg)
    if binary is None:
        return None
    lua_candidates = [Path(cfg.zapret2.lua_dir), binary.parent / "lua",
                      binary.parent.parent / "lua"]
    lua_dir = next((directory for directory in lua_candidates
                    if _is_file(directory / "zapret-lib.lua")
                    and _is_file(directory / "zapret-antidpi.lua")), None)
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
                            if _is_file(directory / name)), None)
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


def launch_key(cfg: Config, installation: Installation, profile: str) -> LaunchKey:
    """Все параметры процесса: при reload нельзя оставить старые Lua, порты или offload."""
    offload = cfg.zapret2.engine_offload and profile == "disorder-badseq"
    return (tuple(arguments(cfg, installation, profile)), offload,
            cfg.network.wan_if.strip() if offload else "")


class OffloadError(cmd.CommandError):
    """Код отказа offload для статуса; команды и приватные пути туда не попадают."""


@dataclass(frozen=True)
class OffloadFlag:
    enabled: bool
    fixed: bool


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
    def parse(listing: str) -> dict[str, OffloadFlag]:
        features = {}
        for line in listing.splitlines():
            name, _separator, value = line.partition(":")
            name = name.strip()
            if name not in OFFLOADS:
                continue  # Заголовок Features for ..., пустые строки и прочие функции NIC.
            words = value.split()
            if not words or words[0] not in ("on", "off") or name in features:
                raise OffloadError("offload_state")
            features[name] = OffloadFlag(words[0] == "on", "[fixed]" in words)
        if not features:
            raise OffloadError("offload_state")
        return features

    def _read(self, interface: str) -> dict[str, OffloadFlag]:
        try:
            listing = self.runner(["ethtool", "-k", interface], timeout=10)
        except (OSError, cmd.CommandError) as exc:
            raise OffloadError("offload_read") from exc
        return self.parse(listing)

    def _set(self, values: dict[str, bool]) -> None:
        if values:
            args = ["ethtool", "-K", self.interface]
            for name, enabled in values.items():
                args += [name, "on" if enabled else "off"]
            self.runner(args, timeout=10)

    def disable(self, interface: str) -> None:
        if self.interface:
            self.restore()  # Не затирать снимок, чей откат пока не подтверждён.
        interface = interface or self.wan_interface()
        current = self._read(interface)
        if any(flag.enabled and flag.fixed for flag in current.values()):
            raise OffloadError("offload_fixed")
        changes = {name: False for name, flag in current.items() if flag.enabled}
        # ethtool может изменить часть флагов и завершиться ошибкой: откат всё равно нужен.
        self.interface = interface
        self.saved = {name: flag.enabled for name, flag in current.items()}
        try:
            self._set(changes)
            actual = self._read(interface) if changes else current
            if any(name not in actual or actual[name].enabled for name in current):
                raise OffloadError("offload_apply")
        except (OSError, cmd.CommandError) as exc:
            raise OffloadError("offload_apply") from exc

    def restore(self) -> None:
        if not self.interface:
            return
        try:
            current = self._read(self.interface)
            changes = {}
            for name, enabled_before in self.saved.items():
                if name not in current:
                    raise OffloadError("offload_restore")
                if current[name].enabled != enabled_before:
                    if current[name].fixed:
                        raise OffloadError("offload_restore")
                    changes[name] = enabled_before
            self._set(changes)
            actual = self._read(self.interface) if changes else current
            if any(name not in actual or actual[name].enabled != value
                   for name, value in self.saved.items()):
                raise OffloadError("offload_restore")
        except (OSError, cmd.CommandError) as exc:
            # Снимок остаётся до успешного чтения и подтверждения исходных значений.
            raise OffloadError("offload_restore") from exc
        self.interface, self.saved = "", {}


class Runtime:
    QUEUE_STATE = Path("/proc/net/netfilter/nfnetlink_queue")

    def __init__(self, runner=cmd.run):
        self.runner = runner
        self.offload = Offload(runner)
        self.key: LaunchKey | None = None

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

    def wait_ready(self, queue: int, cancel: threading.Event | None = None) -> bool:
        """Type=exec подтверждает execve, очередь nfqws2 привязывает позже."""
        deadline = time.monotonic() + READY_TIMEOUT
        while cancel is None or not cancel.is_set():
            left = deadline - time.monotonic()
            if left <= 0:
                raise ValueError("worker_start_timeout")
            state = self.runner(["systemctl", "is-active", UNIT], check=False,
                                timeout=min(1.0, left)).strip()
            if cancel is not None and cancel.is_set():
                return False
            if state == "active" and self.occupied(queue):
                return True
            if state not in ("active", "activating"):
                return False
            pause = min(READY_POLL, max(0.0, deadline - time.monotonic()))
            if cancel is None:
                time.sleep(pause)
            else:
                cancel.wait(pause)
        return False

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
        key = launch_key(cfg, installation, profile)
        if self.key is not None or self.offload.interface:
            self.stop()
        elif self.alive(cfg.zapret2.engine_queue):
            # Подхватываем оставшийся unit XGW.
            self.key = key
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
        # Таймаут systemd-run не гарантирует, что unit не создан. С этого момента
        # требуется остановка, даже если подтверждения запуска мы не получили.
        self.key = key
        try:
            self.runner(["systemd-run", "--quiet", "--collect", "--unit", UNIT,
                         *[arg for item in properties for arg in ("--property", item)], *args],
                        timeout=15)
        except Exception:
            self.offload.restore()
            raise

    def stop(self) -> None:
        try:
            if self.key is None:
                return  # Движок не запускался: не обращаться к systemd/polkit при выходе.
            self.runner(["systemctl", "stop", UNIT], check=False, timeout=10)
            state = self.runner(["systemctl", "is-active", UNIT], check=False, timeout=5).strip()
            if state in ("active", "activating", "deactivating"):
                raise cmd.CommandError("nfqws2: остановка не подтверждена")
            self.key = None  # При ошибке остановки следующая попытка всё ещё обязательна.
        finally:
            self.offload.restore()


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

    def _stop(self) -> str:
        try:
            self.runtime.stop()
        except OffloadError:
            return "offload_restore"
        except (OSError, cmd.CommandError):
            return "worker_stop_failed"
        self.profile, self.installation = "", None
        return ""

    def step(self, cfg: Config, applied: Collection[str], *, active: bool,
             cancel: threading.Event | None = None) -> None:
        if cancel is not None and cancel.is_set():
            error = self._stop()
            self.view = {"state": "fallback" if error else "off", "reason": error or "stopping"}
            return
        installation = find_installation(cfg) if enabled(cfg) and active else None
        if installation is None:
            error = self._stop()
            reason = "disabled" if not enabled(cfg) else ("inactive" if not active else "not_found")
            self.view = {"state": "fallback" if error else "off", "reason": error or reason}
            return
        profile = self.selected_profile(cfg, applied)
        try:
            key = launch_key(cfg, installation, profile)
            if (self.view["state"] == "active" and key == self.runtime.key
                    and self.runtime.alive(cfg.zapret2.engine_queue)):
                self.view = {"state": "active", "profile": profile,
                             "queue": cfg.zapret2.engine_queue}
                return
            self.runtime.start(cfg, installation, profile)
            if not self.runtime.wait_ready(cfg.zapret2.engine_queue, cancel):
                if cancel is not None and cancel.is_set():
                    error = self._stop()
                    self.view = {"state": "fallback" if error else "off",
                                 "reason": error or "stopping"}
                    return
                raise ValueError("worker_down")
        except (OSError, ValueError, cmd.CommandError) as exc:
            reason = str(exc) if isinstance(exc, (ValueError, OffloadError)) and str(exc) in {
                "queue_busy", "unsafe_files", "unsafe_directory", "worker_down",
                "offload_interface", "unknown_profile", "worker_start_timeout",
                "offload_state", "offload_read", "offload_fixed", "offload_apply",
                "offload_restore",
            } else "runtime_failed"
            error = self._stop()
            self.view = {"state": "fallback", "reason": error or reason, "profile": profile}
            return
        self.profile, self.installation = profile, installation
        self.view = {"state": "active", "profile": profile, "queue": cfg.zapret2.engine_queue}

    def close(self) -> None:
        self.runtime.stop()
