"""Эксперимент получения видеопробы из страницы. Не участвует в выборе маршрута."""

from __future__ import annotations

import json
import re
import time
import zlib
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from .. import zapret2
from ..generator.builder import PROBE_USER
from . import checks, video_probe_http

PAGE_BYTES = 2 * 1024 * 1024
# Два запроса, включая последний блок чтения и заголовки.
MAX_CHARGE = 3 * 1024 * 1024
MAX_BROWSER_CANDIDATES = 3
REPLAY_SECONDS = 8
REPORT_CONTENT_TYPES = frozenset({
    "application/json", "application/octet-stream", "application/xml",
    "audio/mp4", "audio/webm", "text/html", "text/plain", "text/xml",
    "video/mp4", "video/webm",
})
PLAYER = re.compile(r'(?:\bytInitialPlayerResponse|window\["ytInitialPlayerResponse"\])\s*=\s*')


def allowed(url: str, domains: list[str], *, page=False) -> bool:
    try:
        u = urlsplit(url)
        if (u.scheme != "https" or u.port not in (None, 443) or u.username is not None
                or u.password is not None or u.fragment or len(url) > 8192
                or any(ord(c) < 33 or ord(c) > 126 for c in url)
                or not zapret2.matches(u.hostname or "", domains)):
            return False
        if page:
            return (u.hostname in ("youtube.com", "www.youtube.com") and u.path == "/watch"
                    and len(parse_qs(u.query, max_num_fields=100).get("v", [])) == 1)
        return zapret2.matches(u.hostname or "", ["domain:googlevideo.com"])
    except ValueError:
        return False


def candidate(body: bytes, domains: list[str], now: float) -> tuple[str, str]:
    """Только готовый HTTPS URL видео, с запасом expire. JS и подписи не исполняются."""
    try:
        if body.startswith(b"\x1f\x8b"):
            body = zlib.decompressobj(31).decompress(body, PAGE_BYTES)
        text = body[:PAGE_BYTES].decode("utf-8", "replace")
        match = PLAYER.search(text)
        if match is None:
            return "", "player_missing"
        player, _ = json.JSONDecoder().raw_decode(text, match.end())
        if not isinstance(player, dict):
            return "", "player_invalid"
        status = player.get("playabilityStatus") or {}
        if not isinstance(status, dict) or status.get("status") != "OK":
            return "", "player_not_ready"
        data = player.get("streamingData") or {}
        if not isinstance(data, dict):
            return "", "streams_missing"
        rows = []
        for key in ("formats", "adaptiveFormats"):
            if isinstance(data.get(key), list):
                rows.extend(data[key][:100])
        cipher = False
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("mimeType", "")).startswith("video/"):
                continue
            cipher |= bool(row.get("signatureCipher") or row.get("cipher"))
            url = row.get("url")
            if not isinstance(url, str) or not allowed(url, domains):
                continue
            until = zapret2.expiry(url)
            if until is not None and now + 300 <= until <= now + 86400:
                return url, "candidate"
        return "", "cipher_required" if cipher else "direct_video_missing"
    except (ValueError, RecursionError, zlib.error):
        return "", "player_invalid"


@dataclass(frozen=True)
class BrowserCandidate:
    url: str = field(repr=False)
    index: int
    transfer_size: int | None
    decoded_body_size: int | None


def _browser_video_hint(url: str, domains: list[str], now: float) -> bool | None:
    if not isinstance(url, str) or not allowed(url, domains):
        return None
    parts = urlsplit(url)
    until = zapret2.expiry(url)
    if parts.path != "/videoplayback" or until is None or not now + 300 <= until <= now + 86400:
        return None
    try:
        mime = parse_qs(parts.query, max_num_fields=100).get("mime", [""])[0]
    except ValueError:
        return None
    if not mime:
        return False
    return True if mime.startswith("video/") else None


def _resource_size(value: object) -> int | None:
    if type(value) is int and 0 <= value <= 2**53 - 1:
        return value
    return None


def browser_candidates(resources: list[dict], domains: list[str],
                       now: float) -> list[BrowserCandidate]:
    """Ранжирует свежие ресурсы по transferSize, затем по подсказке video MIME."""
    eligible = []
    for index, resource in enumerate(resources[:16], 1):
        if not isinstance(resource, dict) or not isinstance(url := resource.get("url"), str):
            continue
        video_hint = _browser_video_hint(url, domains, now)
        if video_hint is None:
            continue
        row = BrowserCandidate(url, index, _resource_size(resource.get("transferSize")),
                               _resource_size(resource.get("decodedBodySize")))
        eligible.append((row, video_hint))
    eligible.sort(key=lambda item: (item[0].transfer_size or 0, item[1]), reverse=True)
    unique = {}
    for row, _ in eligible:
        unique.setdefault(row.url, row)
    return list(unique.values())[:MAX_BROWSER_CANDIDATES]


def replay(url: str, domains: list[str], port: int, password: str, agent: str,
           *, max_total: float = REPLAY_SECONDS, use_range: bool = True,
           curl: str | None = None, http2: bool = False) -> dict:
    if _browser_video_hint(url, domains, time.time()) is None:
        return {"result": "browser_url_missing"}
    metadata = {}
    if curl is None:
        reply = checks.http_get_via_proxy(
            "127.0.0.1", port, url, proxy_user=PROBE_USER, proxy_pass=password, user_agent=agent,
            timeout=5, silence=4, max_total=max_total, max_bytes=zapret2.MIN_BODY,
            min_body=zapret2.MIN_BODY, range_end=zapret2.MIN_BODY if use_range else 0,
            strict_max_bytes=True,
        )
    else:
        reply, metadata = video_probe_http.get(
            curl, url, port, password, agent, http2=http2, max_total=max_total,
        )
    video = reply.content_type.startswith("video/")
    enough = reply.ok and reply.status in (200, 206) and reply.downloaded >= zapret2.MIN_BODY
    result = "replay_failed"
    if enough:
        result = "browser_video_verified" if video else "replay_not_video"
    content_type = reply.content_type or None
    if content_type is not None and content_type not in REPORT_CONTENT_TYPES:
        content_type = "other"
    row = zapret2.probe_row(2, reply) | {
        "path": "vpn", "video_mime": video, "content_type": content_type,
    } | metadata
    if metadata.get("curl_exit") == 63 and not enough:
        row["verdict"] = "body_limit"
    return {
        "result": result,
        "video": row,
        "expires_in": max(0, int((zapret2.expiry(url) or 0) - time.time())),
    }


def compare_replays(candidate: BrowserCandidate, domains: list[str], port: int,
                    password: str, agent: str, record_attempt, *, curl: str | None = None) -> dict:
    """Два GET одного адреса: сравниваем Range или версии HTTP в пределах одного срока."""
    deadline = time.monotonic() + REPLAY_SECONDS
    verified = None
    result = {}
    for attempt in (1, 2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            summary = verified or {**result, "result": "replay_time_budget"}
            return {**summary, "comparison_complete": False}
        use_range = curl is not None or attempt == 1
        result = replay(candidate.url, domains, port, password, agent, max_total=remaining,
                        use_range=use_range, curl=curl, http2=curl is not None and attempt == 2)
        if result["result"] == "browser_url_missing":
            return {**(verified or result), "comparison_complete": False}
        result["range_header"] = use_range
        record_attempt(attempt, {
            **result,
            "candidate_index": candidate.index,
            "transfer_size": candidate.transfer_size,
            "decoded_body_size": candidate.decoded_body_size,
        })
        if verified is None and result["result"] == "browser_video_verified":
            verified = result
    return {**(verified or result), "comparison_complete": True}


def check(page: str, domains: list[str], port: int, password: str, agent: str,
          *, cancel=None) -> dict:
    """Один GET страницы и максимум один GET видео тем же выходом. Только безопасная сводка."""
    if not allowed(page, domains, page=True):
        return {"result": "page_not_configured"}
    agent = checks.pick_agent(agent)
    kwargs = dict(proxy_user=PROBE_USER, proxy_pass=password, user_agent=agent,
                  timeout=5, silence=4, max_total=8, cancel=cancel)
    first = checks.http_get_via_proxy(
        "127.0.0.1", port, page, keep_body=PAGE_BYTES, max_bytes=PAGE_BYTES,
        accept_gzip=True, **kwargs)
    result = {"result": "page_failed", "page_http": first.status, "page_bytes": first.downloaded}
    if not first.ok or first.status != 200:
        return result
    url, why = candidate(first.body, domains, time.time())
    if not url:
        return {**result, "result": why}
    if cancel is not None and cancel.is_set():
        return {**result, "result": "cancelled"}
    video = checks.http_get_via_proxy(
        "127.0.0.1", port, url, max_bytes=zapret2.PROBE_BYTES, min_body=zapret2.MIN_BODY,
        range_end=zapret2.PROBE_BYTES, **kwargs)
    return {**result, "result": "fresh_video_verified" if video.ok else "video_failed",
            "video": zapret2.probe_row(2, video) | {"path": "vpn"},
            "expires_in": max(0, int((zapret2.expiry(url) or 0) - time.time()))}
