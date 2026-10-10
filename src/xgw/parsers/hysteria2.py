"""hysteria2:// и hy2:// — ссылка распознаётся, но узел включается только
после подтверждения, что установленный Xray поддерживает hysteria2-outbound.

В разделе 4 ТЗ и официальной документации полей hysteria2-outbound нет,
поэтому по умолчанию узел пропускается с предупреждением (см. ASSUMPTIONS.md).
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit

from .common import ParseError, RawServer

REASON = (
    "поля hysteria2-outbound не описаны в документации Xray; "
    "узел включается только после проверки установленной версии"
)


def parse(link: str) -> RawServer:
    try:
        parts = urlsplit(link)
    except ValueError as exc:
        raise ParseError(f"hysteria2: битая ссылка ({exc})") from exc
    host = (parts.hostname or "").lower()
    if not host:
        raise ParseError("hysteria2: нет адреса")
    port = parts.port
    if port is None:
        port = 443
    password = unquote(parts.username or "")
    name = unquote(parts.fragment) or f"{host}:{port}"
    _ = parse_qs(parts.query, keep_blank_values=True)  # параметры: sni/insecure/obfs/pinSHA256
    return RawServer(
        name=name,
        protocol="hysteria2",
        address=host,
        port=port,
        credential=password,
        transport="udp/none",
        outbound={"protocol": "hysteria2", "settings": {}},
        warnings=[f"hysteria2: {REASON}"],
        supported=False,
    )
