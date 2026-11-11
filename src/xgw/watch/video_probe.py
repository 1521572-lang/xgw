"""Эксперимент получения видеопробы из страницы. Не участвует в выборе маршрута."""

from __future__ import annotations

import json
import re
import time
import zlib
from urllib.parse import parse_qs, urlsplit

from .. import zapret2
from ..generator.builder import PROBE_USER
from . import checks

PAGE_BYTES = 2 * 1024 * 1024
# Два запроса, включая последний блок чтения и заголовки.
MAX_CHARGE = 3 * 1024 * 1024
REPLAY_ATTEMPTS = 3
REPLAY_SECONDS = 8
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


def browser_candidates(urls: list[str], domains: list[str], now: float) -> list[str]:
    """Свежие адреса из Resource Timing. Сначала кандидаты с явным video MIME."""
    video, fallback, seen = [], [], set()
    for url in urls[:16]:
        if not isinstance(url, str) or url in seen or not allowed(url, domains):
            continue
        seen.add(url)
        parts = urlsplit(url)
        until = zapret2.expiry(url)
        if parts.path != "/videoplayback" or until is None or not now + 300 <= until <= now + 86400:
            continue
        try:
            mime = parse_qs(parts.query, max_num_fields=100).get("mime", [""])[0]
        except ValueError:
            continue
        if mime.startswith("video/"):
            video.append(url)
        elif not mime:
            fallback.append(url)
    return (video + fallback)[:REPLAY_ATTEMPTS]


def replay(url: str, domains: list[str], port: int, password: str, agent: str,
           *, max_total: float = REPLAY_SECONDS) -> dict:
    if not browser_candidates([url], domains, time.time()):
        return {"result": "browser_url_missing"}
    reply = checks.http_get_via_proxy(
        "127.0.0.1", port, url, proxy_user=PROBE_USER, proxy_pass=password, user_agent=agent,
        timeout=5, silence=4, max_total=max_total, max_bytes=zapret2.MIN_BODY,
        min_body=zapret2.MIN_BODY, range_end=zapret2.MIN_BODY, strict_max_bytes=True,
    )
    video = reply.content_type.startswith("video/")
    enough = reply.ok and reply.status in (200, 206) and reply.downloaded >= zapret2.MIN_BODY
    result = "replay_failed"
    if enough:
        result = "browser_video_verified" if video else "replay_not_video"
    return {
        "result": result,
        "video": zapret2.probe_row(2, reply) | {"path": "vpn", "video_mime": video},
        "expires_in": max(0, int((zapret2.expiry(url) or 0) - time.time())),
    }


def replay_candidates(urls: list[str], domains: list[str], port: int, password: str, agent: str,
                      record_attempt) -> dict:
    """До трёх GET по 16 КиБ, с одним общим сроком и остановкой на первом успехе."""
    deadline = time.monotonic() + REPLAY_SECONDS
    result = {"result": "browser_url_missing"}
    for index, url in enumerate(browser_candidates(urls, domains, time.time()), 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {**result, "result": "replay_time_budget"}
        result = replay(url, domains, port, password, agent, max_total=remaining)
        record_attempt(index, result)
        if result["result"] == "browser_video_verified":
            break
    return result


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
