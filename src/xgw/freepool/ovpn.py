"""Профиль OpenVPN как недоверенный язык (ТЗ R47): ограниченная грамматика → типизированное
описание (OvpnProfile). Остаток профиля никогда не исполняется: конфиг для работника OpenVPN
генерируется заново из описания (бэкенд, веха М2).

Белый список директив. Неизвестная директива, исполняемое (up/down/script-security/plugin),
управление (management), включение файлов (config, пути), смена пользователя, прокси, движки
и PKCS#11 — профиль отклоняется (OvpnRejected), а не «чистится». Маршруты, DNS и подобное от
провайдера — пометка MANAGED_BY_XGW: на хост не применяются (маршрутами управляет шлюз), профиль
при этом пригоден. Сжатие запрещено (comp-lzo/compress с алгоритмом). Шифры — из списка;
AES-CBC допустим, но помечен legacy (VPN Gate отдаёт AES-128-CBC и SHA1 во всех профилях,
проверено по CSV 28.10.2026).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass, field

MAX_PROFILE = 256 * 1024  # байт (R11)
MAX_BLOCK = 64 * 1024
MAX_REMOTES = 16

# Директивы, которые переносятся в описание.
_KEPT = {
    "client", "dev", "proto", "remote", "cipher", "data-ciphers", "data-ciphers-fallback",
    "auth", "auth-user-pass", "remote-cert-tls", "verify-x509-name", "tls-version-min",
    "key-direction", "tls-client", "reneg-sec", "ping", "ping-restart", "keepalive",
    "tun-mtu", "mssfix", "float", "auth-nocache",
}
# Безопасные служебные и «провайдерские» директивы: на генерируемый конфиг не переносятся.
_MANAGED = {
    "redirect-gateway", "route", "route-ipv6", "route-delay", "route-method", "dhcp-option",
    "block-outside-dns", "pull", "fast-io", "persist-key", "persist-tun", "resolv-retry",
    "nobind", "verb", "mute", "sndbuf", "rcvbuf", "explicit-exit-notify", "connect-retry",
    "connect-retry-max", "server-poll-timeout", "hand-window", "mute-replay-warnings",
    "remote-random", "allow-recursive-routing", "pull-filter", "ignore-unknown-option",
}
_FORBIDDEN = {
    "up", "down", "script-security", "plugin", "management", "management-client",
    "management-hold", "management-query-passwords", "config", "cd", "chroot", "daemon",
    "user", "group", "log", "log-append", "writepid", "ipchange", "route-up", "route-pre-down",
    "tls-verify", "client-connect", "client-disconnect", "learn-address",
    "auth-user-pass-verify", "setenv", "setenv-safe", "push", "iproute", "dev-node", "tmp-dir",
    "http-proxy", "http-proxy-option", "socks-proxy", "engine", "providers", "pkcs11-providers",
    "pkcs11-id", "pkcs11-id-management", "cryptoapicert", "askpass", "status", "replay-persist",
    "tls-export-cert", "auth-gen-token", "dev-type", "lladdr", "ifconfig", "ifconfig-ipv6",
    "up-delay", "down-pre", "up-restart", "mlock", "syslog", "echo", "x509-track",
    "capath", "crl-verify", "remote-random-hostname", "connection",
}
_BLOCKS = {"ca", "cert", "key", "tls-auth", "tls-crypt"}
CIPHERS = {"AES-256-GCM", "AES-128-GCM", "CHACHA20-POLY1305", "AES-256-CBC", "AES-128-CBC",
           "AES-192-GCM", "AES-192-CBC"}
AUTHS = {"SHA1", "SHA256", "SHA384", "SHA512"}
_PEM = re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----\s*([A-Za-z0-9+/=\s]+?)\s*-----END \1-----")
_STATIC_KEY = re.compile(
    r"-----BEGIN OpenVPN Static key V1-----\s*([0-9a-fA-F\s]+?)\s*"
    r"-----END OpenVPN Static key V1-----"
)


class OvpnRejected(Exception):
    """Профиль не принят; текст — причина (без секретов)."""


@dataclass(frozen=True)
class Remote:
    host: str
    port: int
    proto: str  # tcp | udp


@dataclass(frozen=True)
class OvpnProfile:
    remotes: tuple[Remote, ...]
    ciphers: tuple[str, ...]
    auth: str
    ca: str
    cert: str = ""
    key: str = ""
    tls_auth: str = ""
    tls_crypt: str = ""
    key_direction: str = ""
    needs_password: bool = False  # auth-user-pass без файла: логин и пароль — от источника
    remote_cert_tls: str = ""
    verify_x509_name: str = ""
    tls_version_min: str = ""
    legacy_crypto: bool = False
    managed: tuple[str, ...] = ()
    tuning: tuple[tuple[str, str], ...] = field(default=())

    def digest(self) -> str:
        """Отпечаток содержимого (без учёта пометок): для идентичности варианта."""
        basis = "\n".join((
            ";".join(f"{r.host}:{r.port}/{r.proto}" for r in self.remotes),
            ",".join(self.ciphers), self.auth, self.ca, self.cert, self.key, self.tls_auth,
            self.tls_crypt, self.key_direction, str(self.needs_password), self.remote_cert_tls,
            self.verify_x509_name, self.tls_version_min,
        ))
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _proto(value: str) -> str:
    base = value.lower().removesuffix("-client")
    base = base.rstrip("46")
    if base not in ("tcp", "udp"):
        raise OvpnRejected(f"proto {value!r} не поддерживается")
    return base


def _pem_block(name: str, body: str) -> str:
    text = body.strip()
    if len(text) > MAX_BLOCK:
        raise OvpnRejected(f"блок <{name}> слишком большой")
    if name in ("tls-auth", "tls-crypt"):
        match = _STATIC_KEY.fullmatch(text)
        if not match or len(re.sub(r"\s", "", match.group(1))) != 512:
            raise OvpnRejected(f"блок <{name}>: не статический ключ OpenVPN")
        return text
    blocks = list(_PEM.finditer(text))
    if not blocks:
        raise OvpnRejected(f"блок <{name}>: нет PEM")
    rest = _PEM.sub("", text).strip()
    if rest:
        raise OvpnRejected(f"блок <{name}>: посторонний текст вне PEM")
    for match in blocks:
        try:
            base64.b64decode(re.sub(r"\s", "", match.group(2)), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise OvpnRejected(f"блок <{name}>: битый base64") from exc
    return text


def parse(text: str) -> OvpnProfile:
    """Профиль .ovpn → OvpnProfile; OvpnRejected — профиль не пригоден (причина в тексте)."""
    if len(text.encode("utf-8", "replace")) > MAX_PROFILE:
        raise OvpnRejected("профиль больше 256 КиБ")
    if "\x00" in text:
        raise OvpnRejected("в профиле нулевые байты")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: dict[str, str] = {}
    remotes: list[Remote] = []
    values: dict[str, list[str]] = {}
    managed: list[str] = []
    tuning: list[tuple[str, str]] = []
    proto_default = "udp"
    index = 0
    while index < len(lines):
        raw = lines[index].strip()
        index += 1
        if not raw or raw.startswith(("#", ";")):
            continue
        opening = re.fullmatch(r"<([a-z0-9-]+)>", raw)
        if opening:
            name = opening.group(1)
            if name not in _BLOCKS:
                raise OvpnRejected(f"встроенный блок <{name}> не поддерживается")
            if name in blocks:
                raise OvpnRejected(f"блок <{name}> повторяется")
            body: list[str] = []
            while index < len(lines) and lines[index].strip() != f"</{name}>":
                body.append(lines[index])
                index += 1
            if index >= len(lines):
                raise OvpnRejected(f"блок <{name}> не закрыт")
            index += 1
            blocks[name] = _pem_block(name, "\n".join(body))
            continue
        if raw.startswith("</"):
            raise OvpnRejected(f"лишний закрывающий тег {raw[:20]}")
        words = raw.split()
        key = words[0].lower().lstrip("-")
        args = words[1:]
        if key in _FORBIDDEN:
            raise OvpnRejected(f"директива {key} запрещена")
        if any(arg.startswith(("/", "~")) or "../" in arg for arg in args):
            raise OvpnRejected(f"{key}: путь к файлу не допускается")
        if key in ("comp-lzo", "compress", "comp-noadapt"):
            if key == "comp-lzo" and args == ["no"]:
                managed.append(key)
                continue
            if key == "compress" and not args:
                managed.append(key)  # «compress» без алгоритма — заглушка без сжатия
                continue
            raise OvpnRejected("сжатие в туннеле запрещено")
        if key in _BLOCKS:  # ca/cert/key/tls-auth файлом
            raise OvpnRejected(f"{key}: только встроенный блок")
        if key in _MANAGED:
            managed.append(key)
            continue
        if key not in _KEPT:
            raise OvpnRejected(f"неизвестная директива {key}")
        if key == "remote":
            if not args or len(args) > 3:
                raise OvpnRejected("remote: неверная запись")
            host = args[0].lower()
            if not re.fullmatch(r"[a-z0-9.-]{1,253}|[0-9a-f:]{2,39}", host):
                raise OvpnRejected("remote: неверный адрес")
            port = args[1] if len(args) > 1 else "1194"
            if not port.isdigit() or not 0 < int(port) < 65536:
                raise OvpnRejected("remote: неверный порт")
            remotes.append(Remote(host, int(port), _proto(args[2]) if len(args) > 2 else ""))
            if len(remotes) > MAX_REMOTES:
                raise OvpnRejected("слишком много remote")
            continue
        if key == "proto":
            proto_default = _proto(args[0]) if args else proto_default
            continue
        if key == "auth-user-pass":
            if args:
                raise OvpnRejected("auth-user-pass с файлом не допускается")
            values[key] = []
            continue
        if key == "dev":
            if not args or not args[0].startswith("tun"):
                raise OvpnRejected("поддерживается только dev tun")
            continue  # имя устройства задаёт шлюз
        if key in ("tun-mtu", "mssfix", "ping", "ping-restart", "keepalive", "reneg-sec"):
            if not all(arg.isdigit() for arg in args):
                raise OvpnRejected(f"{key}: неверное значение")
            tuning.append((key, " ".join(args)))
            continue
        values[key] = args
    if not remotes:
        raise OvpnRejected("нет remote")
    if "ca" not in blocks:
        raise OvpnRejected("нет <ca>: сервер не проверить")
    if ("cert" in blocks) != ("key" in blocks):
        raise OvpnRejected("<cert> без <key> или наоборот")
    if "client" not in values and "tls-client" not in values:
        raise OvpnRejected("профиль не клиентский")
    ciphers: list[str] = []
    for name in ("data-ciphers", "cipher", "data-ciphers-fallback"):
        for item in values.get(name, []):
            ciphers.extend(part.upper() for part in item.split(":") if part)
    ciphers = list(dict.fromkeys(ciphers)) or ["AES-256-GCM", "AES-128-GCM"]
    bad = [cipher for cipher in ciphers if cipher not in CIPHERS]
    if bad:
        raise OvpnRejected(f"шифр {bad[0]} не поддерживается")
    auth = (values.get("auth") or ["SHA256"])[0].upper()
    if auth not in AUTHS:
        raise OvpnRejected(f"auth {auth} не поддерживается")
    fixed = tuple(
        Remote(item.host, item.port, item.proto or proto_default) for item in remotes
    )
    return OvpnProfile(
        remotes=fixed,
        ciphers=tuple(ciphers),
        auth=auth,
        ca=blocks["ca"],
        cert=blocks.get("cert", ""),
        key=blocks.get("key", ""),
        tls_auth=blocks.get("tls-auth", ""),
        tls_crypt=blocks.get("tls-crypt", ""),
        key_direction=(values.get("key-direction") or [""])[0],
        needs_password="auth-user-pass" in values,
        remote_cert_tls=(values.get("remote-cert-tls") or [""])[0],
        verify_x509_name=" ".join(values.get("verify-x509-name", [])),
        tls_version_min=(values.get("tls-version-min") or [""])[0],
        legacy_crypto=all(cipher.endswith("-CBC") for cipher in ciphers) or auth == "SHA1",
        managed=tuple(dict.fromkeys(managed)),
        tuning=tuple(tuning),
    )
