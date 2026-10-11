"""«Интернет» стенда: HTTP-origin и DNS-заглушка в одном процессе.

HTTP:
  /64k                      65 536 байт — цель GET-проб (больше порога «заморозки»)
  /bytes?n=N                N байт сразу
  /slow?bytes=N&seconds=S   N байт равномерно за S секунд — «длинная загрузка»
  /trace                    ip=…, loc=NL — как /cdn-cgi/trace
  /sub/<что угодно>         подписка из файла (--sub-file) с заголовком квоты
HEAD на любой путь отдаёт только заголовки с настоящим Content-Length: так
ведёт себя HEAD-проверка, которая «замороженный» сервер считает живым.

DNS (UDP): на любой A-запрос отвечает одним адресом — и для доменов серверов
(*.stand.test), и, на этапе 3, для `dig @8.8.8.8` из LAN. Исключение — имена,
начинающиеся с «loopback.»: на них ответ 127.0.0.1, как у домена, владелец
которого целится в службы самого шлюза. На AAAA-запрос отвечает адресом --answer6
(для «loopback.» это ::1); без --answer6 AAAA-ответов нет.

Адрес --host может быть IPv6 (тогда HTTP слушает по IPv6, а DNS-заглушка не нужна).

Запуск: python origin.py --host 127.0.0.1 --port 8080 --dns-port 5353 --answer 127.0.0.1
"""

from __future__ import annotations

import argparse
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PROBE_BYTES = 65536
CHUNK = b"x" * 4096
# Квота, которую отдаёт «панель провайдера»: израсходовано 3 из 100 ГБ.
USERINFO = "upload=1000000000; download=2000000000; total=100000000000; expire=1893456000"
LOOPBACK_LABEL = b"loopback"


class OriginHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    country = "NL"
    sub_file = ""

    def log_message(self, *_args) -> None:  # тишина в логах стенда
        pass

    def _plan(self) -> tuple[int, float, bytes | None]:
        """(длина тела, секунд на отдачу, готовое тело или None — генерировать)."""
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        if parts.path == "/64k":
            return PROBE_BYTES, 0.0, None
        if parts.path == "/bytes":
            return int(query.get("n", ["1024"])[0]), 0.0, None
        if parts.path == "/slow":
            size = int(query.get("bytes", ["1000000"])[0])
            return size, float(query.get("seconds", ["10"])[0]), None
        if parts.path == "/trace":
            body = f"fl=stand\nip={self.client_address[0]}\nloc={self.country}\n".encode()
            return len(body), 0.0, body
        if parts.path.startswith("/sub/") and self.sub_file:
            try:
                body = Path(self.sub_file).read_bytes()
            except OSError:
                return -1, 0.0, None
            return len(body), 0.0, body
        return -1, 0.0, None

    def _head(self, length: int) -> None:
        if length < 0:
            self.send_response(404)
            self.send_header("Content-Length", "0")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(length))
            if self.path.startswith("/sub/"):
                self.send_header("subscription-userinfo", USERINFO)
        self.send_header("Connection", "close")
        self.end_headers()

    def do_HEAD(self) -> None:
        length, _seconds, _body = self._plan()
        self._head(length)

    def do_GET(self) -> None:
        length, seconds, body = self._plan()
        self._head(length)
        if length <= 0:
            return
        try:
            if body is not None:
                self.wfile.write(body)
                return
            pause = seconds / max(1, length // len(CHUNK)) if seconds else 0.0
            left = length
            while left > 0:
                piece = CHUNK[: min(left, len(CHUNK))]
                self.wfile.write(piece)
                self.wfile.flush()
                left -= len(piece)
                if pause:
                    time.sleep(pause)
        except OSError:
            pass  # клиент ушёл («заморозка», оборванная проба)


class Server6(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def dns_answer(query: bytes, address: str, address6: str = "") -> bytes | None:
    """Ответ на DNS-запрос: A-запись с заданным адресом (для AAAA — адрес address6,
    если он задан), на прочие типы — пусто."""
    if len(query) < 17:
        return None
    offset = 12
    while offset < len(query) and query[offset]:
        offset += query[offset] + 1
    question_end = offset + 5
    if question_end > len(query):
        return None
    if query[12:13] == bytes([len(LOOPBACK_LABEL)]) and (
        query[13 : 13 + len(LOOPBACK_LABEL)].lower() == LOOPBACK_LABEL
    ):
        address, address6 = "127.0.0.1", "::1" if address6 else ""
    qtype = struct.unpack(">H", query[offset + 1 : offset + 3])[0]
    question = query[12:question_end]
    answers = 1 if qtype == 1 or (qtype == 28 and address6) else 0
    header = query[:2] + struct.pack(">HHHHH", 0x8180, 1, answers, 0, 0)
    if not answers:
        return header + question
    v6 = qtype == 28
    data = socket.inet_pton(socket.AF_INET6 if v6 else socket.AF_INET, address6 if v6 else address)
    record = b"\xc0\x0c" + struct.pack(">HHIH", qtype, 1, 30, len(data)) + data
    return header + question + record


def serve_dns(host: str, port: int, address: str, address6: str = "") -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))

    def loop() -> None:
        while True:
            try:
                query, peer = sock.recvfrom(4096)
            except OSError:
                return
            answer = dns_answer(query, address, address6)
            if answer:
                sock.sendto(answer, peer)

    threading.Thread(target=loop, daemon=True).start()
    return sock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--dns-port", type=int, default=0, help="0 — без DNS-заглушки")
    parser.add_argument("--answer", default="127.0.0.1", help="адрес в ответах DNS")
    parser.add_argument("--answer6", default="", help="адрес IPv6 в ответах на AAAA")
    parser.add_argument(
        "--dns-also", action="append", default=[],
        help="ещё один адрес DNS-заглушки (можно несколько раз)",
    )
    parser.add_argument("--country", default="NL", help="значение loc= в /trace")
    parser.add_argument("--sub-file", default="", help="файл подписки для /sub/…")
    args = parser.parse_args()

    OriginHandler.country = args.country
    OriginHandler.sub_file = args.sub_file
    server_class = Server6 if ":" in args.host else ThreadingHTTPServer
    server = server_class((args.host, args.port), OriginHandler)
    server.daemon_threads = True
    if args.dns_port:
        for host in (args.host, *args.dns_also):
            serve_dns(host, args.dns_port, args.answer, args.answer6)
    print("READY", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
