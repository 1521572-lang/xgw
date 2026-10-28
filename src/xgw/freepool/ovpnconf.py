"""Конфиг клиента OpenVPN для изолированного работника (веха М2а). Собирается заново из
разобранного профиля (ovpn.OvpnProfile), а не из текста источника (ТЗ R47): ни одна строка
профиля в него не попадает как есть, блоки ключей — только проверенные PEM и статические ключи.

Директивы — по руководству OpenVPN 2.6. Проверить их здесь нечем (решение заказчика 28.10.2026:
OpenVPN — только на его машине), первая проверка — ТЗ М2а.

Работник OpenVPN без прав на сеть: устройство fpt0 заранее создано агентом с владельцем
xgw-ovpn (проверено в пространстве имён WSL: процесс этого uid без возможностей подключается к
нему, к другому имени — EPERM), адрес и маршрут ставит агент. Отсюда:

  ifconfig-noexec, route-noexec — OpenVPN не вызывает ip (и без прав не смог бы);
  disable-dco — устройство DCO создаётся в ядре с CAP_NET_ADMIN, которого у работника нет;
  pull-filter ignore — маршруты, шлюз по умолчанию и DNS сервера не нужны даже как данные;
  script-security 1 — внешних программ нет; профиль задать их не может (ovpn.py);
  management 127.0.0.1 — внутри своего пространства имён: агент узнаёт состояние и адрес
    туннеля (state); подключиться к нему правила охраны дают только root и xgw-ovpn;
  auth-retry none — неверная учётка: выход, а не бесконечные попытки (R22);
  connect-retry-max, server-poll-timeout, hand-window — попытки ограничены, агент тоже ждёт
    не дольше своего срока.
TLS не ниже 1.2 (R47); remote-cert-tls и verify-x509-name — как в профиле: ослаблять проверку
сервера нельзя, а добавленная без схемы доверия источника отвергла бы его серверы.
"""

from __future__ import annotations

import ipaddress
import re

from .ovpn import OvpnProfile, OvpnRejected

TUN = "fpt0"
AUTH_FILE = "/tmp/xgw-ovpn/auth"
_X509 = re.compile(r"[A-Za-z0-9.*_-]{1,128}( (name|name-prefix|subject))?")
_TLS = {"1.2", "1.3"}


def peer_address(text: str) -> str:
    """Адрес сервера для remote: только публичный IPv4 (R45: один закреплённый адрес на
    вариант; имя здесь не резолвится)."""
    try:
        address = ipaddress.IPv4Address(text.strip())
    except ValueError as exc:
        raise OvpnRejected("адрес сервера — не IPv4") from exc
    if not address.is_global:
        raise OvpnRejected("адрес сервера — не публичный")
    return str(address)


def client_config(
    profile: OvpnProfile, *, remote_ip: str, proto: str, port: int, with_auth: bool,
    mgmt_port: int, tun: str = TUN, auth_file: str = AUTH_FILE,
) -> str:
    """Текст конфига OpenVPN. OvpnRejected — профиль так не собрать (адрес, протокол,
    проверка сервера, которую нельзя передать без искажения)."""
    remote_ip = peer_address(remote_ip)
    if proto not in ("tcp", "udp"):
        raise OvpnRejected("протокол — только tcp или udp")
    if not 0 < port < 65536 or not 0 < mgmt_port < 65536:
        raise OvpnRejected("неверный порт")
    lines = [
        "client",
        f"dev {tun}",
        "dev-type tun",
        f"proto {'tcp-client' if proto == 'tcp' else 'udp'}",
        f"remote {remote_ip} {port}",
        "nobind",
        "persist-key",
        "persist-tun",
        "ifconfig-noexec",
        "route-noexec",
        "disable-dco",
        "script-security 1",
        'pull-filter ignore "redirect-gateway"',
        'pull-filter ignore "route"',
        'pull-filter ignore "dhcp-option"',
        'pull-filter ignore "block-outside-dns"',
        'pull-filter ignore "ifconfig-ipv6"',
        f"tls-version-min {profile.tls_version_min if profile.tls_version_min in _TLS else '1.2'}",
        f"data-ciphers {':'.join(profile.ciphers)}",
    ]
    if profile.fallback_cipher:
        lines.append(f"data-ciphers-fallback {profile.fallback_cipher}")
    lines.append(f"auth {profile.auth}")
    if profile.remote_cert_tls:
        if profile.remote_cert_tls != "server":
            raise OvpnRejected("remote-cert-tls: ожидается server")
        lines.append("remote-cert-tls server")
    if profile.verify_x509_name:
        if not _X509.fullmatch(profile.verify_x509_name):
            raise OvpnRejected("verify-x509-name: такую запись не передать без искажения")
        name, _space, kind = profile.verify_x509_name.partition(" ")
        lines.append(f'verify-x509-name "{name}"' + (f" {kind}" if kind else ""))
    for key, value in profile.tuning:
        lines.append(f"{key} {value}".rstrip())
    lines += [
        "connect-retry 2 5",
        "connect-retry-max 2",
        "server-poll-timeout 15",
        "hand-window 30",
        "auth-retry none",
    ]
    if proto == "udp":
        lines.append("explicit-exit-notify 1")
    if with_auth:
        lines += [f"auth-user-pass {auth_file}", "auth-nocache"]
    lines += [f"management 127.0.0.1 {mgmt_port}", "verb 3", "mute 10"]
    for name, body in (("ca", profile.ca), ("cert", profile.cert), ("key", profile.key),
                       ("tls-auth", profile.tls_auth), ("tls-crypt", profile.tls_crypt)):
        if body:
            lines += [f"<{name}>", body.strip(), f"</{name}>"]
    if profile.tls_auth and profile.key_direction in ("0", "1"):
        lines.append(f"key-direction {profile.key_direction}")
    return "\n".join(lines) + "\n"


def auth_text(username: str, password: str) -> str:
    """Файл auth-user-pass: две строки. Перевод строки внутри значения сломал бы разбор —
    такая учётка не принимается."""
    for value in (username, password):
        if not value or "\n" in value or "\r" in value or len(value) > 256:
            raise OvpnRejected("учётка источника не годится для auth-user-pass")
    return f"{username}\n{password}\n"
