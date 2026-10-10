"""Сокеты с SO_MARK.

Всё, что XGW отправляет напрямую (подписка при упавшем Xray, bootstrap-DNS,
wan_check), обязано идти с меткой mark_bypass — иначе запрос вернётся в перехват.
Метка ставится до connect, чтобы маршрутизация SYN ушла мимо таблицы перехвата.

Имена хостов здесь не разрешаются намеренно: системный резолвер ходит без
метки (через перехват). Вызывающий код передаёт IP-адрес, полученный через
bootstrap-резолверы (fetch.resolve_domain).
"""

from __future__ import annotations

import socket
import sys

# asm-generic/socket.h: SO_MARK = 36 (Linux)
SO_MARK = 36


def is_mark_supported() -> bool:
    return sys.platform.startswith("linux")


def mark_usable(mark: int) -> bool:
    """SO_MARK требует CAP_NET_ADMIN: проверяем на пробном сокете."""
    if not is_mark_supported():
        return False
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, SO_MARK, mark)
    except OSError:
        return False
    finally:
        sock.close()
    return True


class MarkUnavailable(RuntimeError):
    pass


def connect_marked(host: str, port: int, *, timeout: float, mark: int | None) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if mark is not None:
            if not is_mark_supported():
                raise MarkUnavailable("SO_MARK доступен только в Linux")
            sock.setsockopt(socket.SOL_SOCKET, SO_MARK, mark)
        sock.settimeout(timeout)
        sock.connect((host, port))
    except Exception:
        sock.close()
        raise
    return sock


def marked_udp(mark: int | None) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if mark is not None:
        if not is_mark_supported():
            sock.close()
            raise MarkUnavailable("SO_MARK доступен только в Linux")
        try:
            sock.setsockopt(socket.SOL_SOCKET, SO_MARK, mark)
        except OSError:
            sock.close()
            raise
    return sock
