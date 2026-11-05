"""Дробление ClientHello — обход DPI, который блокирует соединение по имени сайта (SNI).

Имя сайта клиент передаёт открытым текстом в ClientHello — первой записи TLS. DPI
читает эту запись и по имени решает, пропустить ли соединение. Если запись разрезана на
куски, ClientHello целиком ни в одном нет, и правило по имени не срабатывает. Xray режет
запись outbound'ом freedom с полем `fragment`: через него сервер устанавливает соединение
(`sockopt.dialerProxy`). Проверено на Xray 26.10.10: ClientHello на 1753 байта уходит 12
частями по 100–200 байт (с паузой 10–20 мс рукопожатие дольше примерно на 0,2 с), а
конфиг с таким outbound'ом проходит `xray run -test`.

Дробить есть смысл только TLS и REALITY поверх TCP: у остальных ClientHello либо нет,
либо он идёт по UDP (QUIC). Сервер, который уже устанавливает соединение через
другой outbound (цепочка из JSON-подписки), не трогается.

Применённый конфиг и есть память о том, каким серверам дробление нужно: у их outbound'ов
`dialerProxy` — тег TAG. Так режим переживает перезапуск демона и обновление подписки,
как состав участников и резервный выход (engine.assemble).

Вторая ступень (0.1.18, ТЗ R1) — outbound SPLIT_TAG: freedom.fragment с packets «1-3» режет
на TCP-сегменты случайной длины первые три записи соединения (ClientHello и следующие), а не
ClientHello на записи TLS. Если ТСПУ научился собирать ClientHello из записей, из сегментов
он может его не собрать. Длина кусков и паузы в обеих ступенях — диапазоны: Xray берёт
случайное значение для каждого куска, предсказуемых одинаковых фрагментов нет.

У XHTTP канал загрузки бывает отдельным (downloadSettings — свой StreamConfig со своим адресом,
TLS и sockopt). Его ClientHello DPI видит так же, поэтому выбранный профиль дробления ставится и
на него, если сам канал подходит (T01 кросс-аудита 4cc96b9). XHTTP идёт по QUIC только при TLS с
alpn ровно ["h3"] — так выбирает версию HTTP сам Xray (T02).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping

from ..config import Config

TAG = "fragment"
SPLIT_TAG = "fragment-split"
# Транспорты поверх UDP: дробить в них нечего.
_UDP_NETWORKS = ("kcp", "mkcp", "quic")
# splithttp — прежнее имя XHTTP, Xray 26.10.x принимает оба.
XHTTP_NETWORKS = ("xhttp", "splithttp")
_XHTTP_KEYS = ("xhttpSettings", "splithttpSettings")


def _stream(outbound: Mapping) -> Mapping:
    stream = outbound.get("streamSettings")
    return stream if isinstance(stream, Mapping) else {}


def _sockopt_dialer(stream: Mapping) -> str:
    sockopt = stream.get("sockopt")
    return str(sockopt.get("dialerProxy") or "") if isinstance(sockopt, Mapping) else ""


def dialer(outbound: Mapping) -> str:
    return _sockopt_dialer(_stream(outbound))


def alpn(stream: Mapping) -> list[str]:
    """alpn из tlsSettings: список или строка через запятую (StringList у Xray)."""
    tls = stream.get("tlsSettings")
    value = tls.get("alpn") if isinstance(tls, Mapping) else None
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    return [text for text in (str(item).strip() for item in value) if text]


def xhttp_h3(stream: Mapping, network: str | None = None) -> bool:
    """XHTTP по HTTP/3 (QUIC). Xray 26.10.x (splithttp, decideHTTPVersion): REALITY — HTTP/2,
    без TLS — HTTP/1.1, TLS с alpn ровно из одного "h3" — HTTP/3, иначе HTTP/2 или 1.1 по TCP.
    Значит, ["h2", "h3"] — это TCP, а splithttp — тот же XHTTP (T02 кросс-аудита 4cc96b9)."""
    net = str(network or stream.get("network") or "tcp").lower()
    if net not in XHTTP_NETWORKS:
        return False
    return str(stream.get("security") or "").lower() == "tls" and alpn(stream) == ["h3"]


def over_udp(stream: Mapping, network: str | None = None) -> bool:
    """Транспорт идёт по UDP: mKCP, QUIC или XHTTP по HTTP/3."""
    net = str(network or stream.get("network") or "tcp").lower()
    return net in _UDP_NETWORKS or xhttp_h3(stream, net)


def _leg_eligible(stream: Mapping, network: str | None = None) -> bool:
    if str(stream.get("security") or "").lower() not in ("tls", "reality"):
        return False
    if over_udp(stream, network):
        return False
    return _sockopt_dialer(stream) in ("", TAG, SPLIT_TAG)


def eligible(outbound: Mapping) -> bool:
    """Можно ли дробить ClientHello этого сервера (по основному каналу)."""
    return _leg_eligible(_stream(outbound))


def download_legs(stream: Mapping, depth: int = 0) -> list[dict]:
    """Отдельные каналы загрузки XHTTP — downloadSettings прямо в xhttpSettings или в его
    extra. У Xray это свой StreamConfig со своим sockopt: родительский он берёт, только если
    задан sockopt.penetrate (transport/internet/splithttp/dialer.go, 26.10.21). Без метки
    mark_bypass соединение такого канала снова попало бы в перехват (пятый аудит, T1)."""
    legs: list[dict] = []
    if depth >= 4:
        return legs
    for key in _XHTTP_KEYS:
        settings = stream.get(key)
        if not isinstance(settings, dict):
            continue
        for options in (settings, settings.get("extra")):
            download = options.get("downloadSettings") if isinstance(options, dict) else None
            if isinstance(download, dict):
                legs.append(download)
                legs.extend(download_legs(download, depth + 1))
    return legs


def loopback_address(address: object) -> bool:
    text = str(address or "").strip("[]").lower()
    if text == "localhost":
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _set_dialer(leg: dict, tag: str) -> None:
    current = leg.get("sockopt")
    sockopt = dict(current) if isinstance(current, Mapping) else {}
    sockopt["dialerProxy"] = tag
    leg["sockopt"] = sockopt


def download_targets(outbound: Mapping) -> list[dict]:
    """Каналы загрузки, на которые ложится профиль дробления: TLS/REALITY по TCP, без чужого
    dialerProxy и не мост к своему 127.0.0.1. Сеть канала загрузки — всегда XHTTP."""
    return [leg for leg in download_legs(_stream(outbound))
            if not loopback_address(leg.get("address"))
            and _leg_eligible(leg, str(leg.get("network") or "xhttp"))]


def used(outbound: Mapping) -> bool:
    """Соединение сервера идёт через дробление ClientHello (первая ступень)."""
    return dialer(outbound) == TAG


def split_used(outbound: Mapping) -> bool:
    """Соединение сервера идёт через нарезку первых пакетов (вторая ступень)."""
    return dialer(outbound) == SPLIT_TAG


def enable(outbound: dict, tag: str = TAG) -> None:
    """Основной канал и подходящие отдельные каналы загрузки XHTTP — через дробление."""
    stream = outbound.setdefault("streamSettings", {})
    for leg in download_targets(outbound):
        _set_dialer(leg, tag)
    _set_dialer(stream, tag)


def outbound(cfg: Config) -> dict:
    """Outbound, через который серверы с дроблением устанавливают соединение. Метка —
    «мимо перехвата»: сокет создаёт он, а не outbound сервера."""
    return {
        "tag": TAG,
        "protocol": "freedom",
        "settings": {
            "domainStrategy": "UseIPv4",
            "fragment": {
                "packets": cfg.fragment.packets,
                "length": cfg.fragment.length,
                "interval": cfg.fragment.interval,
            },
        },
        "streamSettings": {"sockopt": {"mark": cfg.capture.mark_bypass}},
    }


def split_outbound(cfg: Config) -> dict:
    """Outbound второй ступени: нарезка первых пакетов соединения (fragment.split_*)."""
    return {
        "tag": SPLIT_TAG,
        "protocol": "freedom",
        "settings": {
            "domainStrategy": "UseIPv4",
            "fragment": {
                "packets": cfg.fragment.split_packets,
                "length": cfg.fragment.split_length,
                "interval": cfg.fragment.split_interval,
            },
        },
        "streamSettings": {"sockopt": {"mark": cfg.capture.mark_bypass}},
    }
