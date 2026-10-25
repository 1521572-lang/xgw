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
"""

from __future__ import annotations

from collections.abc import Mapping

from ..config import Config

TAG = "fragment"
SPLIT_TAG = "fragment-split"
# Транспорты поверх UDP: дробить в них нечего.
_UDP_NETWORKS = ("kcp", "mkcp", "quic")


def _stream(outbound: Mapping) -> Mapping:
    stream = outbound.get("streamSettings")
    return stream if isinstance(stream, Mapping) else {}


def dialer(outbound: Mapping) -> str:
    sockopt = _stream(outbound).get("sockopt")
    return str(sockopt.get("dialerProxy") or "") if isinstance(sockopt, Mapping) else ""


def eligible(outbound: Mapping) -> bool:
    """Можно ли дробить ClientHello этого сервера."""
    stream = _stream(outbound)
    security = str(stream.get("security") or "").lower()
    if security not in ("tls", "reality"):
        return False
    network = str(stream.get("network") or "tcp").lower()
    if network in _UDP_NETWORKS:
        return False
    tls = stream.get("tlsSettings")
    alpn = tls.get("alpn") if isinstance(tls, Mapping) else None
    if network == "xhttp" and isinstance(alpn, list) and "h3" in alpn:
        return False  # XHTTP поверх HTTP/3 — это QUIC
    return dialer(outbound) in ("", TAG, SPLIT_TAG)


def used(outbound: Mapping) -> bool:
    """Соединение сервера идёт через дробление ClientHello (первая ступень)."""
    return dialer(outbound) == TAG


def split_used(outbound: Mapping) -> bool:
    """Соединение сервера идёт через нарезку первых пакетов (вторая ступень)."""
    return dialer(outbound) == SPLIT_TAG


def enable(outbound: dict, tag: str = TAG) -> None:
    stream = outbound.setdefault("streamSettings", {})
    sockopt = dict(stream.get("sockopt") or {})
    sockopt["dialerProxy"] = tag
    stream["sockopt"] = sockopt


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
