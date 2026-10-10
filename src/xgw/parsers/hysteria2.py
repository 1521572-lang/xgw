"""hysteria2:// и hy2:// — ссылка распознаётся, но узел включается только
после подтверждения, что установленный Xray поддерживает hysteria2-outbound.

В разделе 4 ТЗ и официальной документации полей hysteria2-outbound нет,
поэтому по умолчанию узел пропускается с предупреждением (см. ASSUMPTIONS.md).
"""

from __future__ import annotations

from urllib.parse import unquote

from .common import RawServer, split_link

REASON = (
    "поля hysteria2-outbound не описаны в документации Xray; "
    "узел включается только после проверки установленной версии"
)


def parse(link: str) -> RawServer:
    parts, host, port = split_link(link, "hysteria2")
    if port is None:
        port = 443
    password = unquote(parts.username or "")
    name = unquote(parts.fragment) or f"{host}:{port}"
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
