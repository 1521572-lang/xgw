"""Сквозные проверки watchdog: загрузка с детектором «тишины», провайдер, утечка.

Ключевая проверка — скачать probe.url через http-in/probe-inbound Xray и
следить за потоком байтов тела: если 5 с нет новых данных — соединение
«заморожено» (это то, что не видят HEAD-пробы sing-box/mihomo).
"""

from __future__ import annotations

import base64
import contextlib
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from .. import fetch, marknet

HEAD_LIMIT = 64 * 1024  # заголовки ответа длиннее — это уже не HTTP
MAX_TOTAL_SECONDS = 60.0


@dataclass
class DownloadResult:
    ok: bool
    downloaded: int = 0            # сколько байт ТЕЛА успели скачать (заголовки не в счёт)
    stalled: bool = False          # True = тишина дольше порога при открытом соединении
    error: str = ""
    # Этап сбоя: connect | proxy | tls | http | stall | truncated | timeout | io
    kind: str = ""
    status: int = 0                # код ответа HTTP, если заголовки получены
    body: bytes = b""              # начало тела (не больше keep_body байт)

    @property
    def frozen(self) -> bool:
        """«Заморозка»: часть тела пришла, затем тишина."""
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
    keep_body: int = 0,
    max_total: float = MAX_TOTAL_SECONDS,
    tls_context: ssl.SSLContext | None = None,
) -> DownloadResult:
    """GET через http-прокси (http-in или probe-inbound Xray).

    https открывается CONNECT-туннелем. Успех — только ответ 2xx с телом,
    дочитанным до Content-Length (или до закрытия, если длина не объявлена).
    Нет новых байтов `silence` секунд → stalled; вся загрузка дольше
    `max_total` секунд → timeout (защита от «капающего» сервера).
    """
    parts = urlsplit(url)
    host = parts.hostname
    if not host or parts.scheme not in ("http", "https"):
        return DownloadResult(ok=False, kind="http", error="неподдерживаемый URL пробы")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    deadline = time.monotonic() + max_total
    sock: socket.socket | None = None
    try:
        if parts.scheme == "https":
            try:
                sock = fetch.open_tunnel(
                    (proxy_host, proxy_port), host, port,
                    timeout=timeout, user=proxy_user, password=proxy_pass,
                )
            except fetch.ProxyError as exc:
                return DownloadResult(ok=False, kind="proxy", status=exc.status, error=str(exc))
            except OSError as exc:  # в т. ч. таймаут: inbound не открыл туннель
                return DownloadResult(ok=False, kind="connect", error=f"connect: {exc}")
            context = tls_context or ssl.create_default_context()
            try:
                sock = context.wrap_socket(sock, server_hostname=host)
            except TimeoutError as exc:
                return DownloadResult(ok=False, kind="timeout", error=f"таймаут TLS: {exc}")
            except (ssl.SSLError, OSError) as exc:
                return DownloadResult(ok=False, kind="tls", error=f"TLS: {exc}")
            path = parts.path or "/"
            if parts.query:
                path = f"{path}?{parts.query}"
            request = _request("GET", path, {"Host": _host_header(host, port, 443)})
        else:
            try:
                sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
            except OSError as exc:  # в т. ч. таймаут: локальный inbound недоступен
                return DownloadResult(ok=False, kind="connect", error=f"connect: {exc}")
            headers = {"Host": _host_header(host, port, 80)}
            if proxy_user:
                token = base64.b64encode(f"{proxy_user}:{proxy_pass}".encode()).decode("ascii")
                headers["Proxy-Authorization"] = f"Basic {token}"
            request = _request("GET", url, headers)  # абсолютный URI для http-прокси
        sock.sendall(request)
        return _read_response(sock, silence=silence, deadline=deadline, keep_body=keep_body)
    except TimeoutError as exc:
        return DownloadResult(ok=False, kind="timeout", error=f"таймаут: {exc}")
    except OSError as exc:
        return DownloadResult(ok=False, kind="io", error=str(exc))
    finally:
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.close()


def _host_header(host: str, port: int, default_port: int) -> str:
    name = f"[{host}]" if ":" in host else host
    return name if port == default_port else f"{name}:{port}"


def _request(method: str, target: str, headers: dict[str, str]) -> bytes:
    lines = [f"{method} {target} HTTP/1.1"]
    lines.extend(f"{key}: {value}" for key, value in headers.items())
    lines.extend(["User-Agent: " + fetch.DEFAULT_UA, "Accept: */*", "Connection: close"])
    return (fetch.CRLF.join(lines) + fetch.CRLF * 2).encode("utf-8")


class _Silence(Exception):
    """За `silence` секунд не пришло ни байта."""


class _Deadline(Exception):
    """Исчерпан общий бюджет времени загрузки."""


def _recv(sock: socket.socket, silence: float, deadline: float) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _Deadline
    sock.settimeout(min(silence, remaining))
    try:
        return sock.recv(65536)
    except TimeoutError:
        if time.monotonic() >= deadline:
            raise _Deadline from None
        raise _Silence from None


def _read_response(
    sock: socket.socket, *, silence: float, deadline: float, keep_body: int = 0
) -> DownloadResult:
    """Читает ответ: заголовки, затем тело до Content-Length или закрытия."""
    buffer = b""
    try:
        while fetch.HEAD_END not in buffer:
            if len(buffer) > HEAD_LIMIT:
                return DownloadResult(ok=False, kind="http", error="ответ не похож на HTTP")
            chunk = _recv(sock, silence, deadline)
            if not chunk:
                return DownloadResult(
                    ok=False, kind="truncated", error="соединение закрыто до заголовков ответа"
                )
            buffer += chunk
    except _Silence:
        return DownloadResult(
            ok=False, stalled=True, kind="stall", error=f"тишина {silence:.0f} с до начала тела"
        )
    except _Deadline:
        return DownloadResult(ok=False, kind="timeout", error="таймаут до заголовков ответа")

    head, _, rest = buffer.partition(fetch.HEAD_END)
    status, length, chunked = _parse_head(head)
    if status is None:
        return DownloadResult(ok=False, kind="http", error="ответ не похож на HTTP")
    if not 200 <= status < 300:
        kind = "proxy" if status == 407 else "http"
        return DownloadResult(ok=False, kind=kind, status=status, error=f"HTTP {status}")

    downloaded = len(rest)
    body = rest[:keep_body]
    tail = rest[-5:]
    try:
        while not _complete(downloaded, length, chunked, tail):
            chunk = _recv(sock, silence, deadline)
            if not chunk:
                break
            downloaded += len(chunk)
            if len(body) < keep_body:
                body += chunk[: keep_body - len(body)]
            tail = (tail + chunk)[-5:]
    except _Silence:
        where = f"после {downloaded} байт тела" if downloaded else "до начала тела"
        return DownloadResult(
            ok=False, downloaded=downloaded, stalled=True, kind="stall", status=status,
            body=body, error=f"тишина {silence:.0f} с {where}",
        )
    except _Deadline:
        return DownloadResult(
            ok=False, downloaded=downloaded, kind="timeout", status=status, body=body,
            error=f"загрузка не уложилась в отведённое время ({downloaded} байт тела)",
        )
    if length is not None and downloaded < length:
        return DownloadResult(
            ok=False, downloaded=downloaded, kind="truncated", status=status, body=body,
            error=f"соединение закрыто после {downloaded} из {length} байт тела",
        )
    return DownloadResult(ok=True, downloaded=downloaded, status=status, body=body)


def _parse_head(head: bytes) -> tuple[int | None, int | None, bool]:
    """(код ответа, Content-Length, chunked) из блока заголовков."""
    lines = head.decode("latin-1").split(fetch.CRLF)
    fields = lines[0].split()
    if len(fields) < 2 or not fields[0].startswith("HTTP/") or not fields[1].isdigit():
        return None, None, False
    length: int | None = None
    chunked = False
    for line in lines[1:]:
        name, _, value = line.partition(":")
        name, value = name.strip().lower(), value.strip().lower()
        if name == "content-length" and value.isdigit():
            length = int(value)
        elif name == "transfer-encoding" and "chunked" in value:
            chunked = True
    if chunked:
        length = None  # длина тела задаётся кадрами, Content-Length игнорируется
    return int(fields[1]), length, chunked


def _complete(downloaded: int, length: int | None, chunked: bool, tail: bytes) -> bool:
    if length is not None:
        return downloaded >= length
    # Завершающий кадр chunked-тела; без него ждём закрытия соединения.
    return chunked and tail == b"0" + fetch.HEAD_END


def tcp_check(host: str, port: int, *, timeout: float = 5.0, mark: int | None = None) -> bool:
    """Прямая проверка провайдера (wan_check) сокетом с меткой mark_bypass."""
    try:
        sock = marknet.connect_marked(host, port, timeout=timeout, mark=mark)
    except (OSError, marknet.MarkUnavailable):
        return False
    sock.close()
    return True


def parse_trace(body: str) -> str | None:
    """loc=… из ответа /cdn-cgi/trace."""
    for line in body.splitlines():
        if line.startswith("loc="):
            return line.split("=", 1)[1].strip().upper() or None
    return None


def trace_location(trace_url: str, *, via: tuple[str, int] | None = None,
                   timeout: float = 10.0, mark: int | None = None) -> str | None:
    """Страна выхода по trace_url; None — узнать не удалось.

    Проверка утечки идёт обычным сокетом без метки (via=None, mark=None), то
    есть через перехват. via — то же самое, но явно через http-in Xray.
    """
    if via is None:
        try:
            result = fetch.fetch_url(trace_url, timeout=timeout, mark=mark, retries=0)
        except fetch.FetchError:
            return None
        if result.status != 200:
            return None
        return parse_trace(result.body.decode("utf-8", "replace"))
    download = http_get_via_proxy(via[0], via[1], trace_url, timeout=timeout, keep_body=4096)
    if not download.ok:
        return None
    return parse_trace(download.body.decode("utf-8", "replace"))
