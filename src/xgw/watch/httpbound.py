"""Ограниченный HTTP-сервер панели и API приложения (пятый аудит, A1/A2).

Без ограничений каждое соединение — свой поток, а медленный запрос (заголовки по байту чаще
таймаута чтения) держал бы поток сколько угодно: таких можно открыть сотни. Здесь соединений
сразу — не больше slots (лишние закрываются без ответа), а на чтение запроса — срок
read_deadline: не дочитан — соединение закрывается, и ответа на него нет. Обрыв соединения
клиентом до ответа — одной строкой в журнале, без трассировки.
"""

from __future__ import annotations

import contextlib
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, *, slots: int, label: str, log=None) -> None:
        self.label = label
        self.log = log
        self._slots = threading.BoundedSemaphore(slots)
        super().__init__(address, handler)

    def process_request(self, request, client_address) -> None:
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)  # заняты все места — сразу закрыть
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request, client_address) -> None:
        if self.log is None:
            return
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            # Клиент закрыл соединение, не дочитав ответ (отчёты f6b и 0.2.0-audit4): не сбой
            # сервера — одной строкой, без трассировки.
            self.log.info("%s: клиент %s закрыл соединение раньше ответа",
                          self.label, client_address[0])
            return
        self.log.exception("%s: запрос не обработан", self.label)


class DeadlineHandler(BaseHTTPRequestHandler):
    """Срок на чтение запроса: от соединения до request_read() (заголовки и тело прочитаны).
    Истёк — соединение закрывается (cut = True), обработчику отвечать некому."""

    read_deadline = 20.0
    cut = False

    def setup(self) -> None:
        super().setup()
        self.deadline = threading.Timer(self.read_deadline, self._cut)
        self.deadline.daemon = True
        self.deadline.start()

    def _cut(self) -> None:
        self.cut = True
        with contextlib.suppress(OSError):
            self.connection.shutdown(socket.SHUT_RDWR)

    def request_read(self) -> None:
        self.deadline.cancel()

    def finish(self) -> None:
        self.deadline.cancel()
        super().finish()


def request_read(handler) -> None:
    """Запрос прочитан целиком: срок чтения снят (у обработчика без срока — ничего)."""
    read = getattr(handler, "request_read", None)
    if read is not None:
        read()
