"""Linux credentials for local Unix-socket peers."""

import socket
import struct

_UCRED = struct.Struct("iII")


def peer_uid(connection: socket.socket) -> int:
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _UCRED.size)
    return _UCRED.unpack(credentials)[1]
