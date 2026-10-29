"""Модели бесплатного пула (ТЗ R07–R08, R19): вариант сервера и итог опроса источника.

Идентичность — не 32-битный отпечаток подписок (model.make_fingerprint), а variant_id: 128 бит
SHA-256 от канонического описания (источник, бэкенд, протокол, адрес, порт, транспорт, отпечаток
outbound'а). endpoint_id — источник + хост + порт + транспорт: один сервер разных вариантов —
общий endpoint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum


class Status(StrEnum):
    """Итог опроса источника (R08). PARTIAL и ошибки не удаляют пропавшие узлы."""

    SUCCESS = "SUCCESS"
    NOT_MODIFIED = "NOT_MODIFIED"
    PARTIAL = "PARTIAL"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    DISABLED = "DISABLED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class Access(StrEnum):
    FREE = "free"
    PAID = "paid"
    UNKNOWN = "unknown"


class Backend(StrEnum):
    # Туннель SSTP в изолированном пространстве имён (agent.py, веха М2в: вместо OpenVPN —
    # решение заказчика 29.10.2026).
    SSTP = "sstp"
    XRAY = "xray"  # outbound Xray: VLESS, VMess, Trojan, Shadowsocks (Outline, списки GitHub)
    SINGBOX = "sing-box"  # только sing-box: Hysteria2, TUIC, AnyTLS (списки GitHub)


@dataclass(frozen=True)
class Variant:
    """Вариант сервера из каталога: как к нему подключиться и что о нём сказал источник."""

    provider: str
    backend: str
    protocol: str  # sstp | shadowsocks | vless | vmess | trojan | hysteria2 | tuic | anytls
    host: str
    address: str  # IPv4 из каталога, если он есть
    port: int
    transport: str  # tcp | udp
    name: str
    country_hint: str  # страна по каталогу (ISO2) — только подсказка (R15)
    access: str = Access.FREE
    # Показатели источника (ping, speed, score, sessions…) — подсказки порядка проверки, не
    # измерения шлюза (R23 шаг 2).
    hints: tuple[tuple[str, str], ...] = ()
    usage_policy: tuple[str, ...] = ()  # например ("no-torrent",)
    outbound: dict | None = None
    source_url: str = ""
    extra: tuple[tuple[str, str], ...] = field(default=())
    # Сервер для sing-box (parsers.common.SingboxSpec словарём: main, endpoint, extra) — у тех,
    # кого Xray не умеет.
    singbox: dict | None = None

    @property
    def endpoint_id(self) -> str:
        return f"{self.provider}|{self.host or self.address}|{self.port}|{self.transport}"

    @property
    def variant_id(self) -> str:
        if self.outbound is not None or self.singbox is not None:
            payload = hashlib.sha256(
                json.dumps(self.outbound if self.outbound is not None else self.singbox,
                           sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
        else:
            payload = ""
        basis = "|".join((self.provider, self.backend, self.protocol, self.host, self.address,
                          str(self.port), self.transport, payload))
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


@dataclass
class ProviderResult:
    """Итог опроса одного источника (R08)."""

    provider: str
    status: Status
    variants: list[Variant] = field(default_factory=list)
    retrieved_at: float = 0.0
    complete_response: bool = False  # документ получен и разобран целиком
    authoritative: bool = False  # источник обещает полный инвентарь (у VPN Gate — нет)
    detail: str = ""
    rejected: int = 0  # строк каталога, не принятых разбором (причины — в rejections)
    rejections: dict[str, int] = field(default_factory=dict)
