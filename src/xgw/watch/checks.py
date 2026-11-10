"""Сквозные проверки watchdog: загрузка с детектором «тишины», провайдер, утечка.

Ключевая проверка — скачать probe.url через http-in/probe-inbound Xray и
следить за потоком байтов тела: если 5 с нет новых данных — соединение
«заморожено» (это то, что не видят HEAD-пробы sing-box/mihomo).
"""

from __future__ import annotations

import base64
import contextlib
import random
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from .. import fetch, marknet

HEAD_LIMIT = 64 * 1024  # заголовки ответа длиннее — это уже не HTTP
MAX_TOTAL_SECONDS = 60.0
# Строка разметки тела «частями» (размер части с расширениями, трейлер) длиннее — не HTTP.
CHUNK_LINE_LIMIT = 4096
_CHUNK_SIZE = re.compile(rb"[0-9A-Fa-f]{1,16}")


@dataclass
class DownloadResult:
    ok: bool
    downloaded: int = 0            # сколько байт ТЕЛА успели скачать (заголовки не в счёт)
    stalled: bool = False          # True = тишина дольше порога при открытом соединении
    error: str = ""
    # Этап сбоя: connect | proxy | tls | http | stall | truncated | timeout | reset | io.
    # reset — соединение оборвано после отправки запроса (RST, ошибка TLS посреди ответа):
    # код ответа и пришедшие байты тела сохраняются (C02 кросс-аудита 4cc96b9).
    kind: str = ""
    status: int = 0                # код ответа HTTP, если заголовки получены
    body: bytes = b""              # начало тела (не больше keep_body байт)
    # Сколько секунд шло тело — от конца заголовков до последнего байта; по нему считается
    # скорость (watch/speed.py): рукопожатия туннеля и TLS в замер не входят.
    body_seconds: float = 0.0
    # Сетевая задержка (RTT), мс: второй, короткий запрос (HEAD) в том же, уже открытом
    # соединении — без рукопожатий TCP и TLS и без загрузки файла (http_get_via_proxy, rtt).
    # None — не замерялась или сервер закрыл соединение после первого ответа.
    rtt_ms: float | None = None
    reusable: bool = False  # соединение после ответа годится для следующего запроса
    location: str = ""  # заголовок Location ответа 3xx (переходит по нему вызывающий)

    body_time_limited: bool = False  # чтение прервал именно лимит времени тела
    phase: str = ""  # connect, tls, request, headers или body

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
    user_agent: str = "",
    max_bytes: int = 0,
    max_body_seconds: float = 0.0,
    cancel: threading.Event | None = None,
    rtt: bool = False,
    range_end: int = 0,
    min_body: int = 0,
) -> DownloadResult:
    """GET через http-прокси (http-in или probe-inbound Xray).

    https открывается CONNECT-туннелем. Успех — только ответ 2xx с телом,
    дочитанным до Content-Length, до последней части ответа «частями» (chunked) или до
    закрытия, если длина не объявлена. Нет новых байтов `silence` секунд → stalled; вся
    загрузка дольше `max_total` секунд → timeout (защита от «капающего» сервера): это общий
    срок всех этапов — соединения с прокси, CONNECT, рукопожатия TLS и ответа (C03
    кросс-аудита 4cc96b9: раньше каждый этап ждал свои `timeout` секунд сверх него).
    `min_body` — тело короче (ответ 204, пустой 200) — неудача: пробе нужен файл, а не
    ответ без тела (C01).
    `user_agent` — заголовок запроса (probe.user_agent); пусто — «xgw/<версия>».
    `max_bytes` / `max_body_seconds` — замер скорости: тело дальше этого не читается, и
    загрузка всё равно удачная (ok), хоть файл и не дочитан.
    `cancel` — демон останавливается: ожидание сети на любом этапе (ответ на CONNECT,
    рукопожатие TLS, заголовки, тело) прерывается за доли секунды, итог — kind
    "cancelled". О сервере такой итог ничего не говорит, записывать его нельзя.
    `rtt` — после удачной загрузки по https тем же соединением (keep-alive) уходит HEAD, и
    время до его заголовков — сетевая задержка rtt_ms (п. 2.3 рекомендаций к аудиту 0.1.18):
    время пробы целиком (рукопожатия TCP и TLS через сервер, загрузка файла) больше её в
    разы — у «польша 2» 340–470 мс при RTT 40–60.
    `range_end` — сколько байт тела просить (Range: bytes=0-…, ответ 206); 0 — весь файл.
    Сервер, который Range не понимает, отдаёт файл целиком (200) — так тоже удача.
    """
    ranged = {"Range": f"bytes=0-{range_end - 1}"} if range_end > 0 else {}
    user_agent = pick_agent(user_agent)  # один UA на соединение: и GET, и HEAD по нему
    parts = urlsplit(url)
    host = parts.hostname
    if not host or parts.scheme not in ("http", "https"):
        return DownloadResult(ok=False, kind="http", error="неподдерживаемый URL пробы")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    deadline = time.monotonic() + max_total

    def left(cap: float) -> float:
        """Ожидание этапа: не дольше cap и не дольше, чем осталось до общего срока."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("общий срок пробы исчерпан")
        return min(cap, remaining)

    sock: socket.socket | None = None
    phase = "connect"
    try:
        if cancel is not None and cancel.is_set():
            raise fetch.Cancelled
        if parts.scheme == "https":
            try:
                sock = fetch.open_tunnel(
                    (proxy_host, proxy_port), host, port, timeout=left(timeout),
                    user=proxy_user, password=proxy_pass, cancel=cancel, deadline=deadline,
                )
            except fetch.ProxyError as exc:
                return DownloadResult(ok=False, kind="proxy", status=exc.status, error=str(exc),
                                      phase=phase)
            except OSError as exc:  # в т. ч. таймаут: inbound не открыл туннель
                return DownloadResult(ok=False, kind="connect", error=f"connect: {exc}",
                                      phase=phase)
            phase = "tls"
            context = tls_context or ssl.create_default_context()
            try:
                sock = context.wrap_socket(
                    sock, server_hostname=host, do_handshake_on_connect=False
                )
                fetch.wait_io(sock, sock.do_handshake, left(timeout), cancel)
            except TimeoutError as exc:
                return DownloadResult(ok=False, kind="timeout", error=f"таймаут TLS: {exc}",
                                      phase=phase)
            except (ssl.SSLError, OSError) as exc:
                return DownloadResult(ok=False, kind="tls", error=f"TLS: {exc}", phase=phase)
            sock.settimeout(left(timeout))
            path = parts.path or "/"
            if parts.query:
                path = f"{path}?{parts.query}"
            request = _request(
                "GET", path, {"Host": _host_header(host, port, 443), **ranged}, user_agent,
                keep_alive=rtt,
            )
        else:
            try:
                sock = socket.create_connection((proxy_host, proxy_port), timeout=left(timeout))
            except OSError as exc:  # в т. ч. таймаут: локальный inbound недоступен
                return DownloadResult(ok=False, kind="connect", error=f"connect: {exc}",
                                      phase=phase)
            headers = {"Host": _host_header(host, port, 80), **ranged}
            if proxy_user:
                token = base64.b64encode(f"{proxy_user}:{proxy_pass}".encode()).decode("ascii")
                headers["Proxy-Authorization"] = f"Basic {token}"
            request = _request("GET", url, headers, user_agent)  # абсолютный URI
            sock.settimeout(left(timeout))
        phase = "request"
        sock.sendall(request)
        phase = "headers"
        result = _read_response(
            sock, silence=silence, deadline=deadline, keep_body=keep_body,
            max_bytes=max_bytes, max_body_seconds=max_body_seconds, cancel=cancel,
        )
        result.phase = "body" if 200 <= result.status < 300 else phase
        if result.ok and result.downloaded < min_body:
            return DownloadResult(
                ok=False, kind="http", status=result.status, downloaded=result.downloaded,
                body=result.body, body_seconds=result.body_seconds,
                error=f"ответ без тела (HTTP {result.status}, {result.downloaded} байт)",
                phase=result.phase,
            )
        if rtt and parts.scheme == "https" and result.ok and result.reusable:
            head = _request("HEAD", path, {"Host": _host_header(host, port, 443)}, user_agent)
            try:
                result.rtt_ms = _head_rtt(sock, head, silence, deadline, cancel)
            except fetch.Cancelled:
                return DownloadResult(ok=False, kind="cancelled", downloaded=result.downloaded,
                                      error="проверка прервана", status=result.status,
                                      phase=result.phase)
        return result
    except fetch.Cancelled:
        return DownloadResult(
            ok=False, kind="cancelled", error="проверка прервана: демон останавливается",
            phase=phase,
        )
    except TimeoutError as exc:
        return DownloadResult(ok=False, kind="timeout", error=f"таймаут: {exc}", phase=phase)
    except OSError as exc:
        return DownloadResult(ok=False, kind="io", error=str(exc), phase=phase)
    finally:
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.close()


def _head_rtt(
    sock: socket.socket, request: bytes, silence: float, deadline: float,
    cancel: threading.Event | None,
) -> float | None:
    """Время от отправки HEAD до конца его заголовков, мс; None — ответа нет (сервер закрыл
    соединение или замолчал). Ошибка здесь пробу не портит: файл уже скачан."""
    started = time.monotonic()
    buffer = b""
    try:
        sock.sendall(request)
        while fetch.HEAD_END not in buffer and len(buffer) <= HEAD_LIMIT:
            chunk = _recv(sock, silence, deadline, cancel)
            if not chunk:
                return None
            buffer += chunk
    except (OSError, _Silence, _Deadline):
        return None
    if not buffer.startswith(b"HTTP/"):
        return None
    return round((time.monotonic() - started) * 1000.0, 1)


def _host_header(host: str, port: int, default_port: int) -> str:
    name = f"[{host}]" if ":" in host else host
    return name if port == default_port else f"{name}:{port}"


# Пул браузерных User-Agent для проб (аудит противодействия ТСПУ 05.11.2026, P0): одна и та
# же строка во всех пробах — примета для сервера назначения и VPN-сервера (ТСПУ заголовков
# внутри туннеля не видит). Выбор — один на соединение: GET и HEAD по нему идут с одним UA.
# Свой probe.user_agent в config.toml главнее пула.
BROWSER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:144.0) Gecko/20100101 Firefox/144.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/26.0 Safari/605.1.15",
)


def pick_agent(user_agent: str = "") -> str:
    """UA для одного соединения пробы: пул браузерных, если в config.toml свой не задан
    (пусто или прежнее значение по умолчанию)."""
    from ..config import DEFAULT_PROBE_UA

    if not user_agent or user_agent == DEFAULT_PROBE_UA or not user_agent.isprintable():
        return random.choice(BROWSER_AGENTS)
    return user_agent


def _request(
    method: str, target: str, headers: dict[str, str], user_agent: str = "", *,
    keep_alive: bool = False,
) -> bytes:
    lines = [f"{method} {target} HTTP/1.1"]
    lines.extend(f"{key}: {value}" for key, value in headers.items())
    # Без Accept-Encoding: тело нужно целиком, несжатым — по нему считается размер пробы.
    agent = user_agent if user_agent and user_agent.isprintable() else pick_agent()
    connection = "keep-alive" if keep_alive else "close"
    lines.extend(["User-Agent: " + agent, "Accept: */*", f"Connection: {connection}"])
    return (fetch.CRLF.join(lines) + fetch.CRLF * 2).encode("utf-8")


class _Silence(Exception):
    """За `silence` секунд не пришло ни байта."""


class _Deadline(Exception):
    """Исчерпан общий бюджет времени загрузки."""


def _recv(
    sock: socket.socket, silence: float, deadline: float, cancel: threading.Event | None = None
) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _Deadline
    try:
        return fetch.wait_io(sock, lambda: sock.recv(65536), min(silence, remaining), cancel)
    except TimeoutError:
        if time.monotonic() >= deadline:
            raise _Deadline from None
        raise _Silence from None


def _read_response(
    sock: socket.socket, *, silence: float, deadline: float, keep_body: int = 0,
    max_bytes: int = 0, max_body_seconds: float = 0.0, cancel: threading.Event | None = None,
) -> DownloadResult:
    """Читает ответ: заголовки, затем тело до Content-Length, последней части ответа «частями»
    или закрытия (либо до max_bytes / max_body_seconds — тогда загрузка удачная, хоть и не до
    конца). downloaded и body — полезные байты тела, без разметки частей."""
    buffer = b""
    try:
        while fetch.HEAD_END not in buffer:
            if len(buffer) > HEAD_LIMIT:
                return DownloadResult(ok=False, kind="http", error="ответ не похож на HTTP")
            chunk = _recv(sock, silence, deadline, cancel)
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
    except OSError as exc:  # RST, ошибка TLS: таймауты сюда не доходят (_recv)
        return DownloadResult(
            ok=False, kind="reset", error=f"обрыв соединения до заголовков ответа: {exc}"
        )

    head, _, rest = buffer.partition(fetch.HEAD_END)
    status, length, chunked = _parse_head(head)
    if status is None:
        return DownloadResult(ok=False, kind="http", error="ответ не похож на HTTP")
    if not 200 <= status < 300:
        kind = "proxy" if status == 407 else "http"
        return DownloadResult(ok=False, kind=kind, status=status, error=f"HTTP {status}",
                              location=_header(head, "location") if 300 <= status < 400 else "")
    if status == 204:
        length, chunked = 0, False  # тела у ответа 204 нет (RFC 9110): закрытия не ждать

    started = time.monotonic()
    parts = _Chunked() if chunked else None
    payload = parts.feed(rest) if parts is not None else rest
    downloaded = len(payload)
    body = payload[:keep_body]

    body_deadline = started + max_body_seconds if max_body_seconds > 0 else deadline
    read_deadline = min(deadline, body_deadline)

    try:
        while not _complete(downloaded, length, parts):
            if parts is not None and parts.error:
                return DownloadResult(
                    ok=False, downloaded=downloaded, kind="http", status=status, body=body,
                    error=f"ответ частями не по стандарту: {parts.error}",
                    body_seconds=time.monotonic() - started,
                )
            if max_bytes and downloaded >= max_bytes:
                return DownloadResult(
                    ok=True, downloaded=downloaded, status=status, body=body,
                    body_seconds=time.monotonic() - started,
                )
            chunk = _recv(sock, silence, read_deadline, cancel)
            if not chunk:
                break
            data = parts.feed(chunk) if parts is not None else chunk
            downloaded += len(data)
            if len(body) < keep_body:
                body += data[: keep_body - len(body)]
    except fetch.Cancelled:
        return DownloadResult(ok=False, downloaded=downloaded, kind="cancelled", status=status,
                              body=body, error="проверка прервана",
                              body_seconds=time.monotonic() - started)
    except OSError as exc:  # RST посреди тела: не «не подключился» — код и байты сохраняются
        return DownloadResult(
            ok=False, downloaded=downloaded, kind="reset", status=status, body=body,
            error=f"обрыв соединения после {downloaded} байт тела: {exc}",
            body_seconds=time.monotonic() - started,
        )
    except _Silence:
        where = f"после {downloaded} байт тела" if downloaded else "до начала тела"
        return DownloadResult(
            ok=False, downloaded=downloaded, stalled=True, kind="stall", status=status,
            body=body, error=f"тишина {silence:.0f} с {where}",
            body_seconds=time.monotonic() - started,
        )
    except _Deadline:
        if cancel is not None and cancel.is_set():
            return DownloadResult(ok=False, downloaded=downloaded, kind="cancelled", status=status,
                                  error="проверка прервана",
                                  body_seconds=time.monotonic() - started)
        if body_deadline < deadline and downloaded > 0:
            return DownloadResult(ok=True, downloaded=downloaded, status=status, body=body,
                                  body_seconds=time.monotonic() - started, body_time_limited=True)
        return DownloadResult(
            ok=False, downloaded=downloaded, kind="timeout", status=status, body=body,
            error=f"загрузка не уложилась в отведённое время ({downloaded} байт тела)",
            body_seconds=time.monotonic() - started,
        )
    seconds = time.monotonic() - started
    if length is not None and downloaded < length:
        return DownloadResult(
            ok=False, downloaded=downloaded, kind="truncated", status=status, body=body,
            error=f"соединение закрыто после {downloaded} из {length} байт тела",
            body_seconds=seconds,
        )
    if parts is not None and not parts.done:
        # C01 кросс-аудита 4cc96b9: обрыв посреди ответа частями раньше считался целым ответом.
        return DownloadResult(
            ok=False, downloaded=downloaded, kind="truncated", status=status, body=body,
            error=f"соединение закрыто посреди ответа частями, после {downloaded} байт тела",
            body_seconds=seconds,
        )
    result = DownloadResult(
        ok=True, downloaded=downloaded, status=status, body=body, body_seconds=seconds
    )
    # Тело дочитано по длине или по кадрам, а сервер не обещал закрыть соединение — им можно
    # отправить следующий запрос (замер RTT).
    result.reusable = (length is not None or chunked) and b"connection: close" not in (
        head.lower())
    return result


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


def _header(head: bytes, wanted: str) -> str:
    """Значение заголовка ответа (имя без учёта регистра); пусто — заголовка нет."""
    for line in head.decode("latin-1").split(fetch.CRLF)[1:]:
        name, _, value = line.partition(":")
        if name.strip().lower() == wanted:
            return value.strip()
    return ""


def _complete(downloaded: int, length: int | None, parts: _Chunked | None) -> bool:
    if length is not None:
        return downloaded >= length
    # Последняя часть ответа «частями» и трейлеры; без длины и частей — ждём закрытия.
    return parts is not None and parts.done


class _Chunked:
    """Разбор тела «частями» (Transfer-Encoding: chunked, RFC 9112 §7.1): размер части (hex,
    расширения после «;» не в счёт), данные, перевод строки; последняя часть — нулевая, за ней
    трейлеры до пустой строки. feed(data) — полезные байты из data. C01 кросс-аудита 4cc96b9:
    раньше конец тела искался по последним пяти байтам потока — обрыв посреди части считался
    целым ответом, такие же байты внутри данных — концом, а байты разметки — телом."""

    def __init__(self) -> None:
        self.line = b""  # недочитанная строка разметки
        self.left = 0  # сколько байт данных текущей части впереди
        self.state = "size"  # size | data | crlf | trailer | done
        self.trailers = 0
        self.error = ""

    @property
    def done(self) -> bool:
        return self.state == "done"

    def feed(self, data: bytes) -> bytes:
        out = bytearray()
        pos = 0
        while pos < len(data) and self.state != "done" and not self.error:
            if self.state == "data":
                take = min(self.left, len(data) - pos)
                out += data[pos:pos + take]
                pos += take
                self.left -= take
                if not self.left:
                    self.state = "crlf"
                continue
            end = data.find(b"\n", pos)
            if end < 0:
                self.line += data[pos:]
                if len(self.line) > CHUNK_LINE_LIMIT:
                    self.error = "строка разметки слишком длинная"
                break
            line, self.line = (self.line + data[pos:end]).rstrip(b"\r"), b""
            pos = end + 1
            if len(line) > CHUNK_LINE_LIMIT:
                self.error = "строка разметки слишком длинная"
            elif self.state == "crlf":
                if line:
                    self.error = "нет перевода строки после части"
                self.state = "size"
            elif self.state == "size":
                size = line.split(b";", 1)[0].strip()
                if not _CHUNK_SIZE.fullmatch(size):
                    self.error = "неверный размер части"
                else:
                    self.left = int(size, 16)
                    self.state = "data" if self.left else "trailer"
            else:  # трейлеры
                self.trailers += len(line) + 2
                if not line:
                    self.state = "done"
                elif self.trailers > HEAD_LIMIT:
                    self.error = "трейлеры слишком длинные"
        return bytes(out)


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
                   timeout: float = 10.0, mark: int | None = None,
                   user_agent: str = "") -> str | None:
    """Страна выхода по trace_url; None — узнать не удалось.

    Проверка утечки идёт обычным сокетом без метки (via=None, mark=None), то
    есть через перехват. via — то же самое, но явно через http-in Xray.
    """
    if via is None:
        try:
            result = fetch.fetch_url(
                trace_url, timeout=timeout, mark=mark, retries=0,
                headers={"User-Agent": user_agent} if user_agent else None,
            )
        except fetch.FetchError:
            return None
        if result.status != 200:
            return None
        return parse_trace(result.body.decode("utf-8", "replace"))
    download = http_get_via_proxy(
        via[0], via[1], trace_url, timeout=timeout, keep_body=4096, user_agent=user_agent
    )
    if not download.ok:
        return None
    return parse_trace(download.body.decode("utf-8", "replace"))
