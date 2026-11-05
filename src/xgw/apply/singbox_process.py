"""Два процесса sing-box; transient units исчезают при reboot, обычный unit читает current."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..generator import singbox as sb
from ..net import cmd
from ..paths import atomic_write_json
from ..xraycore.service import XrayServiceError

SLOTS = ("blue", "green")
DRAIN_SECONDS = 300
LEGACY = "xgw-singbox.service"


def owner_start(pid):
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def unit(slot):
    if slot not in (*SLOTS, "legacy"):
        raise ValueError("неизвестное поколение sing-box")
    return LEGACY if slot == "legacy" else f"xgw-singbox-{slot}.service"


def state_path(paths):
    return paths.run / "singbox-generations.json"


def marker_path(paths):
    return paths.run / "singbox-managed"


def read(paths):
    try:
        state = json.loads(state_path(paths).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"active": "legacy", "draining": None, "pending": None}
    if (state.get("active") not in (*SLOTS, "legacy")
            or any(state.get(k) and state[k]["slot"] not in (*SLOTS, "legacy")
                   for k in ("draining", "pending"))):
        raise ValueError("состояние поколений sing-box повреждено")
    return state


def write(paths, state):
    atomic_write_json(state_path(paths), state, mode=0o600)


def config_path(paths, slot):
    unit(slot)
    return paths.singbox_config_dir / f"generation-{slot}.json"


def config_write(paths, slot, config):
    path = config_path(paths, slot)
    atomic_write_json(path, config)
    # atomic_write создаёт новый inode от root; наследовать группу как у каталога ядра.
    os.chown(path, 0, paths.singbox_config_dir.stat().st_gid)


def start(core, slot, config):
    """Те же ограничения, что у установленного обычного unit; без capabilities и SIGHUP."""
    path = config_path(core.paths, slot)
    properties = []
    allowed = {
        "User", "Group", "AmbientCapabilities", "CapabilityBoundingSet", "NoNewPrivileges",
        "Restart", "RestartSec", "LimitNOFILE", "ProtectSystem", "ProtectHome", "PrivateTmp",
        "ReadOnlyPaths", "ProtectKernelTunables", "ProtectKernelModules", "ProtectKernelLogs",
        "ProtectClock", "ProtectHostname", "RestrictNamespaces", "RestrictRealtime",
        "RestrictSUIDSGID", "LockPersonality", "SystemCallArchitectures", "RestrictAddressFamilies",
    }
    service = False
    settings = {}
    for line in (core.paths.systemd_dir / LEGACY).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("["):
            service = line == "[Service]"
        if service and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key in allowed:
                settings[key] = value
                properties.extend(["--property", line])
    if any(settings.get(k) != v for k, v in {
        "User": "xgw-singbox", "Group": "xgw-singbox", "AmbientCapabilities": "",
        "CapabilityBoundingSet": "", "NoNewPrivileges": "true", "ProtectSystem": "strict",
    }.items()):
        raise XrayServiceError("обычный unit sing-box не подтверждает ограничения")
    binary = sb.find_binary(None, core.paths)
    if binary is None:
        raise XrayServiceError("бинарник sing-box не найден")
    cmd.run(["systemd-run", "--quiet", "--collect", "--unit", unit(slot),
             "--property", "Type=exec", *properties,
             str(binary), "--disable-color", "run", "-c", str(path)], timeout=60)


def ports(config):
    return set(sb.bridge_ports(config).values())


def stop(slot):
    cmd.run(["systemctl", "stop", "--no-block", unit(slot)], check=False, timeout=10)


def stopped(slot):
    output = cmd.run(["systemctl", "show", unit(slot), "-p", "MainPID", "-p", "LoadState",
                      "-p", "ActiveState"], check=False, timeout=10)
    fields = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    return (fields.get("LoadState") == "not-found"
            or (fields.get("MainPID") == "0"
                and fields.get("ActiveState") in {"inactive", "failed"}))


def xray_ports(config):
    return {
        outbound["settings"]["servers"][0]["port"]
        for outbound in (config or {}).get("outbounds", []) if sb.bridge_variant(outbound)
    }


def reap(core):
    """Вызывается под общей блокировкой; не останавливать процесс, на который ещё ссылаются."""
    state = read(core.paths)
    old = state["draining"]
    if old and time.monotonic() >= old["until"] and not core.paths.api_dirty_file.exists():
        try:
            current = json.loads(core.paths.xray_config_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return state
        if not xray_ports(current).intersection(old["ports"]):
            stop(old["slot"])
            if stopped(old["slot"]):
                state["draining"] = None
                write(core.paths, state)
    if state["active"] == "legacy" and not state["pending"] and not state["draining"]:
        marker_path(core.paths).unlink(missing_ok=True)
    return state


def summary(paths):
    state = read(paths)
    old = state["draining"]
    return {
        "active": state["active"], "draining": old["slot"] if old else None,
        "drain_left_s": max(0, round(old["until"] - time.monotonic())) if old else 0,
        "pending": state["pending"]["phase"] if state["pending"] else None,
        "process_limit": 2,
    }
