"""Lifetime of the trusted status backend owned by the running panel."""

from __future__ import annotations

import grp
import os
import pwd
import stat
import threading
from collections.abc import Callable
from pathlib import Path

from ..paths import LockTimeout, Paths, file_lock
from . import panel_ipc, panel_read_http

USER = "xgw-panel-read"
SERVICE = "xgw-panel-read.service"
SOCKET = "xgw-panel-read.socket"


class StatusRuntime:
    def __init__(self, ipc: Path, relay: Path, uid: int, gid: int,
                 overview: Callable[[], dict | None], logger):
        self.ipc, self.relay = ipc, relay
        self.uid, self.gid = uid, gid
        self._overview, self._log = overview, logger
        self._tickets = panel_ipc.StatusTickets()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="xgw-panel-status", daemon=True)

    @classmethod
    def for_panel(cls, paths: Paths, overview: Callable[[], dict | None], logger):
        if os.geteuid() != 0 or not paths.panel_ipc_dir.is_dir():
            return None
        try:
            identity = pwd.getpwnam(USER)
            group = grp.getgrnam(USER)
            if (identity.pw_uid == 0 or identity.pw_gid == 0 or identity.pw_gid != group.gr_gid
                    or pwd.getpwuid(identity.pw_uid).pw_name != USER
                    or grp.getgrgid(identity.pw_gid).gr_name != USER
                    or set(os.getgrouplist(USER, group.gr_gid)) != {group.gr_gid}
                    or group.gr_gid not in os.getgroups()):
                raise ValueError("isolated_identity_required")
        except (OSError, KeyError, ValueError):
            logger.warning("Изолированный статус zapret2 недоступен: проверьте UID и группу службы")
            return None
        return cls(paths.panel_ipc_dir / "status.sock", paths.panel_relay_socket,
                   identity.pw_uid, identity.pw_gid, overview, logger)

    def _serve(self):
        try:
            info = self.ipc.parent.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o022 or self.ipc.parent.resolve() != self.ipc.parent):
                raise ValueError("trusted_socket_directory_required")
            with file_lock(self.ipc.parent / "serve.lock", mode=0o600, timeout=0.25):
                panel_ipc.serve(self.ipc, self.uid, self.gid, self._overview, self._stop,
                                tickets=self._tickets, recover_stale=True)
        except (OSError, ValueError, LockTimeout) as exc:
            self._log.warning("Сокет статуса zapret2 недоступен: %s", exc)

    def start(self):
        self._thread.start()

    def read(self):
        if not self._thread.is_alive():
            raise panel_ipc.ProtocolError("unavailable")
        # The listening HTTP socket is created by systemd as root.
        return panel_read_http.relay_status(self.relay, 0, self._tickets)

    def close(self):
        self._stop.set()
        self._thread.join(timeout=3)
