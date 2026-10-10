"""Сквозные проверки watchdog: загрузка с детектором «тишины», провайдер, утечка.

Ключевая проверка — скачать probe.url через http-in/probe-inbound Xray и
следить за потоком байтов: если 5 с нет новых данных — соединение
«заморожено» (это то, что не видят HEAD-пробки sing-box/mihomo).
"""

from __future__ import annotations

import base64
import contextlib
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from .. import marknet


@dataclass
class DownloadResult:
    ok: bool
    downloaded: int = 0            # сколько байт успели скачать
    stalled: bool = False          # True = «заморозка»: поток шёл и замолчал
    error: str = ""

    @property
    def frozen(self) -> bool:
        return self.stalled and self.downloaded > 0


def http_get_via_proxy(
    proxy_host: str,
    proxy_port: int,
    url: str,
    *,
    timeout: float = 15.0,
    silence: float = 5.0,
    proxy_user: str = "",
    proxy_pass: str = "",
) -> DownloadResult:
    """GET через http-прокси (http-in или probe-inbound Xray).

    https открывается CONNECT-туннелем; чтение тела — с детектором тишины:
    нет новых байтов `silence` секунд → stalled (классический «замороженный»
    сервер отдаёт заголовки и 15–20 КиБ, потом замолкает).
    """
    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        return DownloadResult(ok=False, error="в URL нет хоста")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    except OSError as exc:
        return DownloadResult(ok=False, error=f"connect: {exc}")
    try:
        sock.settimeout(min(silence, timeout))
        headers = {"Host": f"{host}:{port}", "Connection": "close"}
        if proxy_user:
            token = base64.b64encode(f"{proxy_user}:{proxy_pass}".encode()).decode()
            headers["Proxy-Authorization"] = f"Basic {token}"
        if parts.scheme == "https":
            request = _request_line("CONNECT", f"{host}:{port}", headers)
            sock.sendall(request)
            line = _read_line(sock)
            if not line.startswith(b"HTTP/1."):
                return DownloadResult(ok=False, error="прокси не ответил на CONNECT")
            if not line.split()[1].startswith(b"2"):
                detail = line.decode(errors="replace").strip()
                return DownloadResult(ok=False, error=f"CONNECT отклонён: {detail}")
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)
            sock.settimeout(min(silence, timeout))
            path = parts.path or "/"
            if parts.query:
                path = f"{path}?{parts.query}"
            sock.sendall(_request_line("GET", path, {"Host": host, "Connection": "close"}))
        else:
            path = url  # абсолютный URI для обычного http-прокси
            sock.sendall(_request_line("GET", path, headers))
        return _read_response(sock, silence=silence)
    except (OSError, ssl.SSLError) as exc:
        return DownloadResult(ok=False, error=str(exc), stalled=False)
    finally:
        with contextlib.suppress(OSError):
            sock.close()


def _request_line(method: str, target: str, headers: dict[str, str]) -> bytes:
    lines = [f"{method} {target} HTTP/1.1"]
    lines.extend(f"{key}: {value}" for key, value in headers.items())
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


def _read_line(sock: socket.socket) -> bytes:
    line = b""
    while not line.endswith(b"\r\n"):
        chunk = sock.recv(1)
        if not chunk:
            break
        line += chunk
    return line


def _read_response(sock: socket.socket, *, silence: float) -> DownloadResult:
    """Читает ответ до конца или до `silence` секунд без новых байтов."""
    downloaded = 0
    header_seen = False
    last_data = time.monotonic()
    try:
        while True:
            try:
                chunk = sock.recv(65536)
            except TimeoutError:
                if header_seen:
                    return DownloadResult(
                        ok=False, downloaded=downloaded, stalled=True,
                        error=f"тишина {silence:.0f} с после {downloaded} байт",
                    )
                return DownloadResult(
                    ok=False, downloaded=0, stalled=True,
                    error=f"тишина {silence:.0f} с до начала тела",
                )
            if not chunk:
                return DownloadResult(ok=header_seen, downloaded=downloaded)
            downloaded += len(chunk)
            if b"\r\n\r\n" in chunk or header_seen:
                header_seen = True
            last_data = time.monotonic()
            _ = last_data  # момент последнего чанка; таймаут сокета отсчитывается заново
    except OSError as exc:
        return DownloadResult(ok=False, downloaded=downloaded, error=str(exc))


def tcp_check(host: str, port: int, *, timeout: float = 5.0, mark: int | None = None) -> bool:
    """Прямая проверка провайдера (wan_check) сокетом с меткой mark_bypass."""
    try:
        sock = marknet.connect_marked(host, port, timeout=timeout, mark=mark)
    except (OSError, marknet.MarkUnavailable):
        return False
    sock.close()
    return True


def trace_location(trace_url: str, *, via: tuple[str, int] | None = None,
                   timeout: float = 10.0, mark: int | None = None) -> str | None:
    """loc=… из trace_url. via — http-in (проверка утечки идёт обычным сокетом
    без метки, то есть через перехват; здесь только парсинг ответа)."""
    if via is None:
        from .. import fetch

        try:
            result = fetch.fetch_url(trace_url, timeout=timeout, mark=mark, retries=1)
            body = result.body.decode("utf-8", "replace")
        except Exception:
            return None
    else:
        download = http_get_via_proxy(via[0], via[1], trace_url, timeout=timeout)
        if not download.ok:
            return None
        body = ""
        # тело после пустой строки
    for line in body.splitlines():
        if line.startswith("loc="):
            return line.split("=", 1)[1].strip().upper()
    return None
