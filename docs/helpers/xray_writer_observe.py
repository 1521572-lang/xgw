"""Bounded Linux observer for atomic replacements of the installed Xray JSON."""
import argparse
import ctypes
import difflib
import hashlib
import json
import os
import select
import struct
import time
from pathlib import Path

CONFIG = Path("/etc/xgw/xray/config.json")
STEP = Path("/run/xgw/watchdog-step.json")
SECTIONS = ("routing", "inbounds", "outbounds")
LIMIT = 4 * 1024 * 1024
EVENT = struct.Struct("iIII")
CLOSE_WRITE, MOVED_FROM, MOVED_TO, CREATE, DELETE = 8, 64, 128, 256, 512
WATCH_LOST = 0x400 | 0x800 | 0x2000 | 0x4000 | 0x8000


def emit(kind, **fields):
    print(json.dumps(dict(event=kind, unix=time.time(), mono=time.monotonic(), **fields)),
          flush=True)


def snapshot(path):
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
        info = os.fstat(stream.fileno())
    if len(data) > LIMIT:
        raise ValueError("config_size")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("config_schema")
    return info.st_ino, hashlib.sha256(data).digest(), value


def section_changes(before, after):
    # Use a dict wrapper to preserve missing versus explicit null.
    changes = {}
    for name in (*SECTIONS, "other"):
        pair = []
        for side in (before, after):
            group = {k: v for k, v in side.items()
                     if (k not in SECTIONS if name == "other" else k == name)}
            pair.append(json.dumps(group, sort_keys=True, indent=2).splitlines())
        if pair[0] != pair[1]:
            # Never serialize diff content. Config sections may contain credentials.
            changes[name] = sum(line.startswith("@@ ") for line in difflib.unified_diff(*pair))
    return changes


def watch_directory(path):
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        return None
    mask = CLOSE_WRITE | MOVED_TO | MOVED_FROM | CREATE | DELETE | 0x400 | 0x800
    if libc.inotify_add_watch(fd, os.fsencode(path.parent), mask) < 0:
        os.close(fd)
        return None
    return fd


def drain(fd, filename):
    raw = os.read(fd, 65536)
    events = []
    offset = 0
    while offset < len(raw):
        _, mask, _, size = EVENT.unpack_from(raw, offset)
        offset += EVENT.size
        name = raw[offset:offset + size].rstrip(b"\0")
        offset += size
        if mask & WATCH_LOST:
            raise ValueError("inotify_coverage_lost")
        if name == filename:
            events.append(mask)
    return events


def watchdog():
    try:
        row = json.loads(STEP.read_bytes())
        phase = row.get("phase")
        return {"phase": phase if phase in ("tick", "sleep", "start", "step") else "other",
                "age_s": round(time.monotonic() - float(row["at"]), 2)}
    except (OSError, KeyError, TypeError, ValueError):
        return None


def observe(path, seconds):
    fd = watch_directory(path)
    try:
        previous = snapshot(path)
        emit("begin", backend="inotify" if fd is not None else "poll")
        deadline = time.monotonic() + seconds
        samples = transitions = signals = gaps = 0
        next_heartbeat = time.monotonic()
        while (left := deadline - time.monotonic()) > 0:
            wait = min(left, 1.0)
            masks = []
            if fd is None:
                time.sleep(wait)
            elif select.select([fd], [], [], wait)[0]:
                masks = drain(fd, os.fsencode(path.name))
            current = snapshot(path)
            samples += 1
            signals += len(masks)
            if time.monotonic() >= next_heartbeat:
                emit("heartbeat", watchdog=watchdog())
                next_heartbeat = time.monotonic() + 20
            if signals > 256:
                raise ValueError("event_budget")
            if masks or current[:2] != previous[:2]:
                transitions += current[:2] != previous[:2]
                gaps += len(masks) > 1
                emit("sample", file_events=len(masks), moved_to=sum(bool(m & MOVED_TO) for m in masks),
                     inode_changed=current[0] != previous[0], bytes_changed=current[1] != previous[1],
                     diff_hunks=section_changes(previous[2], current[2]), watchdog=watchdog())
            previous = current
        emit("end", reads=samples, observed_transitions=transitions, file_events=signals,
             batches_with_multiple_events=gaps)
    finally:
        if fd is not None:
            os.close(fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, choices=range(1, 301), metavar="1..300", default=180)
    args = parser.parse_args()
    try:
        observe(CONFIG, args.seconds)
    except (OSError, ValueError) as exc:
        reason = str(exc) if type(exc) is ValueError else type(exc).__name__
        emit("incomplete", error=reason)
        raise SystemExit(2) from None
