"""Модель сервера из подписки: отпечаток, страна, исходный outbound.

Отпечаток — первые 8 hex SHA-256 от протокола, адреса, порта, credential
(id или пароля) и транспорта; по нему схлопываются дубли.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from .parsers.common import RawServer, SingboxSpec

_COUNTRIES = set(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ
    BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM
    DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS
    GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN
    KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
    MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM
    PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV
    SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI
    VN VU WF WS YE YT ZA ZM ZW
    """.split()
)

_FLAG_BASE = 0x1F1E6
_TOKEN_RE = re.compile(r"\b[A-Z]{2}\b")


def country_from_name(name: str) -> str:
    """Флаг-эмодзи или отдельный код ISO в имени; иначе xx."""
    for i, ch in enumerate(name):
        if _FLAG_BASE <= ord(ch) <= _FLAG_BASE + 25 and i + 1 < len(name):
            nxt = name[i + 1]
            if _FLAG_BASE <= ord(nxt) <= _FLAG_BASE + 25:
                first = chr(ord(ch) - _FLAG_BASE + ord("A"))
                second = chr(ord(nxt) - _FLAG_BASE + ord("A"))
                return (first + second).lower()
    for token in _TOKEN_RE.findall(name):
        if token in _COUNTRIES:
            return token.lower()
    return "xx"


def make_fingerprint(
    protocol: str, address: str, port: int, credential: str, transport: str
) -> str:
    basis = f"{protocol.lower()}|{address.lower()}|{port}|{credential}|{transport}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8]


# Поля, по которым серверы с одними протоколом, адресом, портом, ключом и транспортом ведут к
# разным выходам: путь и Host (CDN, где у каждого сервера свой путь), режим XHTTP, имя службы
# gRPC, SNI и ключ REALITY (пятый аудит, T2).
_STREAM_KEYS = (
    "wsSettings", "httpupgradeSettings", "xhttpSettings", "splithttpSettings", "grpcSettings",
    "httpSettings",
)
_STREAM_FIELDS = ("path", "host", "mode", "serviceName")
_SB_FIELDS = (
    ("tls", ("server_name",)), ("reality", ("public_key",)),
    ("transport", ("path", "host", "service_name")),
)


@dataclass
class ServerNode:
    fingerprint: str
    name: str
    country: str
    protocol: str
    address: str
    port: int
    outbound: dict
    source: str
    # Исходный тег outbound из JSON-подписки (цепочки sockopt.dialerProxy
    # переносятся целиком и обязаны сохранить тег, иначе связь порвётся).
    keep_tag: str | None = None
    warnings: list[str] = field(default_factory=list)
    # Описание для sing-box (None — сервер умеет только Xray). outbound пуст у серверов,
    # которые умеет только sing-box.
    singbox: SingboxSpec | None = None

    @property
    def capability(self) -> str:
        """Какое ядро умеет этот сервер: dual — оба, xray или singbox — только одно."""
        if self.outbound and self.singbox is not None:
            return "dual"
        return "xray" if self.outbound else "singbox"


def raw_to_node(raw: RawServer, source: str) -> ServerNode:
    fingerprint = make_fingerprint(
        raw.protocol, raw.address, raw.port, raw.credential, raw.transport
    )
    # Пробелы по краям имени из подписки («🇹🇷 Турция ») в списке серверов и событиях
    # не видны, а поиск по имени ломают (отчёт А3.2).
    name = raw.name.strip() or f"{raw.address}:{raw.port}"
    return ServerNode(
        fingerprint=fingerprint,
        name=name,
        country=country_from_name(name),
        protocol=raw.protocol,
        address=raw.address,
        port=raw.port,
        outbound=raw.outbound,
        source=source,
        keep_tag=raw.keep_tag,
        warnings=list(raw.warnings),
        singbox=raw.singbox,
    )


def variant_key(node: ServerNode) -> str:
    """Путь, Host, режим, SNI и ключ REALITY сервера — то, что make_fingerprint не учитывает."""
    parts: dict[str, object] = {}
    stream = node.outbound.get("streamSettings") if node.outbound else None
    if isinstance(stream, dict):
        for key in _STREAM_KEYS:
            settings = stream.get(key)
            if isinstance(settings, dict):
                for name in _STREAM_FIELDS:
                    if settings.get(name):
                        parts[f"{key}.{name}"] = settings[name]
        for key in ("tlsSettings", "realitySettings"):
            settings = stream.get(key)
            if isinstance(settings, dict):
                for name in ("serverName", "publicKey"):
                    if settings.get(name):
                        parts[f"{key}.{name}"] = settings[name]
    elif node.singbox is not None:
        main = node.singbox.main
        tls = main.get("tls") if isinstance(main.get("tls"), dict) else {}
        sources = {
            "tls": tls,
            "reality": tls.get("reality") if isinstance(tls.get("reality"), dict) else {},
            "transport": main.get("transport") if isinstance(main.get("transport"), dict) else {},
        }
        for prefix, names in _SB_FIELDS:
            for name in names:
                if sources[prefix].get(name):
                    parts[f"{prefix}.{name}"] = sources[prefix][name]
    return json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)


def split_variants(nodes: list[ServerNode]) -> int:
    """Серверы с одним отпечатком (протокол, адрес, порт, ключ, транспорт), но разными путём,
    Host, SNI, ключом REALITY или режимом XHTTP — разные выходы, а не дубли: им отпечаток с
    этими полями. У остальных отпечаток прежний — закрепления, история и замеры не теряются;
    настоящие дубли (поля те же) по-прежнему схлопывает builder. Возвращает, скольким серверам
    дан новый отпечаток."""
    groups: dict[str, list[ServerNode]] = {}
    for node in nodes:
        groups.setdefault(node.fingerprint, []).append(node)
    changed = 0
    for fingerprint, group in groups.items():
        keys = [variant_key(node) for node in group]
        if len(set(keys)) < 2:
            continue
        for node, key in zip(group, keys, strict=True):
            basis = f"{fingerprint}|{key}"
            node.fingerprint = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8]
            changed += 1
    return changed
