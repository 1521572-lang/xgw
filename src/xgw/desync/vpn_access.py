"""Attribute a bounded TCP session to one accepted Xray connection."""

from dataclasses import dataclass
from json import loads

from ..net import cmd
from ..xraycore.access import destination, endpoint, journal_identity, parse_accepted
from .route_evidence import GROUPS

UNIT = "xgw-xray.service"
MAX_LOG_ROWS = 512
MICROSECONDS = 1_000_000


@dataclass(frozen=True)
class Connection:
    start: int
    end: int
    source: tuple[str, int] | None
    target: tuple[str, int]
    inbound: str
    pinned: str
    peer_target: tuple[str, int] | None = None


def _journal_rows(epoch, start, end):
    boot, pid = journal_identity(epoch)
    raw = cmd.run(["journalctl", "--quiet", "--no-pager", "-b", boot, "-u", UNIT, f"_PID={pid}",
                   "--since", f"@{start // MICROSECONDS}",
                   "--until", f"@{end // MICROSECONDS + 1}", "-n", str(MAX_LOG_ROWS), "-o", "json",
                   "--output-fields=MESSAGE,_PID,_BOOT_ID,_SYSTEMD_UNIT"], timeout=6)
    return [loads(line) for line in raw.splitlines() if line]


def match(connection, journal, before, after):
    if connection.source is None:
        return {"state": "no_connect_socket"}
    first, last = (round(row["unix"] * MICROSECONDS) for row in (before, after))
    elapsed = (after["monotonic_ns"] - before["monotonic_ns"]) / 1_000
    if not (before["xray_epoch"] == after["xray_epoch"]
            and first <= connection.start < connection.end <= last
            and 0 < last - first <= 35 * MICROSECONDS
            and abs(last - first - elapsed) <= MICROSECONDS):
        return {"state": "window_unconfirmed"}
    if len(journal) >= MAX_LOG_ROWS:
        return {"state": "journal_limit"}
    boot, pid = journal_identity(before["xray_epoch"])
    matches = []
    for row in journal:
        if ((row.get("_SYSTEMD_UNIT"), row.get("_BOOT_ID"), row.get("_PID"))
                != (UNIT, boot, pid)):
            continue
        stamp = row.get("__REALTIME_TIMESTAMP")
        message = row.get("MESSAGE")
        if (not isinstance(stamp, str) or not stamp.isascii() or not stamp.isdecimal()
                or len(stamp) > 20):
            return {"state": "journal_unavailable"}
        if not connection.start <= int(stamp) <= connection.end:
            continue
        if not isinstance(message, str):
            return {"state": "journal_unavailable"}
        entry = parse_accepted(message)
        if entry is None or entry.inbound != connection.inbound:
            continue
        try:
            same_socket = endpoint(entry.source) == connection.source
            same_target = destination(entry.target) in (connection.target, connection.peer_target)
        except ValueError:
            continue
        if same_socket and same_target:
            matches.append(entry.outbound)
    if len(matches) != 1:
        return {"state": "ambiguous" if matches else "no_access_record"}
    (tag,) = matches
    group = before["tags"].get(tag, {}).get("group")
    if group not in GROUPS:
        group = {"direct": "direct", "block": "blocked"}.get(tag, "other")
    return {"state": "observed", "group": group,
            "matches_pinned_outbound": tag == connection.pinned if connection.pinned else None}


def routes(connections, before, after):
    pending = [item for item in connections.values() if item.source is not None]
    journal = []
    if pending:
        try:
            journal = _journal_rows(before["xray_epoch"], min(item.start for item in pending),
                                    max(item.end for item in pending))
            if not all(isinstance(row, dict) for row in journal):
                raise ValueError("invalid_journal")
        except (OSError, ValueError, cmd.CommandError):
            return {lane: {"state": "journal_unavailable" if item.source else "no_connect_socket"}
                    for lane, item in connections.items()}
    return {lane: match(item, journal, before, after) for lane, item in connections.items()}
