"""Фейковые ссылки с адресами 203.0.113.0/24 и *.example.com (данные только тестовые)."""

import base64
import json


def _fake_pbk() -> str:
    """Синтаксически валидный x25519-ключ (32 байта base64url), не настоящий."""
    return base64.urlsafe_b64encode(b"\x11" * 32).rstrip(b"=").decode("ascii")


FAKE_PBK = _fake_pbk()

VLESS_REALITY = (
    "vless://11111111-2222-3333-4455-666666666661@203.0.113.10:443?"
    "encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.example.org"
    f"&fp=chrome&pbk={FAKE_PBK}&sid=abcd1234&type=tcp"
    "#%F0%9F%87%B3%F0%9F%87%B1%20NL-1"
)

VLESS_WS = (
    "vless://11111111-2222-3333-4455-666666666662@de.example.com:443?"
    "security=tls&sni=de.example.com&fp=chrome&alpn=h2%2Chttp%2F1.1&type=ws"
    "&host=de.example.com&path=%2Fws#%F0%9F%87%A9%F0%9F%87%AA%20DE-1"
)

VLESS_GRPC = (
    "vless://11111111-2222-3333-4455-666666666663@203.0.113.13:443?"
    "security=tls&sni=grpc.example.com&type=grpc&serviceName=grpc-svc&mode=gun"
    "#%F0%9F%87%BA%F0%9F%87%B8%20US-1"
)

VLESS_XHTTP = (
    "vless://11111111-2222-3333-4455-666666666664@203.0.113.14:443?"
    "security=tls&sni=xh.example.com&type=xhttp&path=%2Fxh&host=xh.example.com&mode=auto"
    "&extra=%7B%22scMaxEachPostBytes%22%3A1000000%7D"
    "#%F0%9F%87%BA%F0%9F%87%B8%20US-2"
)

VLESS_KCP = (
    "vless://11111111-2222-3333-4455-666666666665@203.0.113.15:443?"
    "type=kcp&headerType=srtp&seed=kcp-seed#%F0%9F%87%AB%F0%9F%87%B7%20FR-2"
)

VLESS_HTTPUPGRADE = (
    "vless://11111111-2222-3333-4455-666666666666@203.0.113.16:443?"
    "security=tls&sni=hu.example.com&type=httpupgrade&path=%2Fhu&host=hu.example.com"
    "#%F0%9F%87%AB%F0%9F%87%B7%20FR-3"
)

VLESS_TCP_HTTP = (
    "vless://11111111-2222-3333-4455-666666666667@203.0.113.17:80?"
    "type=tcp&headerType=http&host=h.example.com&path=%2Fhpd#%F0%9F%87%AB%F0%9F%87%B7%20FR-4"
)

TROJAN = (
    "trojan://tr0jan-pass@203.0.113.20:443?security=tls&sni=nl2.example.org"
    "#%F0%9F%87%B3%F0%9F%87%B1%20NL-2"
)

TROJAN_INSECURE = (
    "trojan://tr0jan-pass@203.0.113.21:443?security=tls&sni=nl3.example.org&allowInsecure=1"
    "#%F0%9F%87%B3%F0%9F%87%B1%20NL-3"
)


def _vmess_link() -> str:
    payload = {
        "v": "2",
        "ps": "FR-1 🇫🇷",
        "add": "fr.example.com",
        "port": "443",
        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "aid": "0",
        "scy": "auto",
        "net": "ws",
        "type": "",
        "host": "fr.example.com",
        "path": "/vmess",
        "tls": "tls",
        "sni": "fr.example.com",
        "fp": "chrome",
    }
    return "vmess://" + base64.b64encode(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")


VMESS = _vmess_link()


def _ss_userinfo() -> str:
    raw = b"aes-256-gcm:ss-pass-123"
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


SS_SIP002 = f"ss://{_ss_userinfo()}@203.0.113.40:8388/?plugin=simple-obfs%3Bobfs%3Dhttp%3Bobfs-host%3Dob.example.com#SS-1"

SS_PLAIN = "ss://aes-128-gcm:pw123@203.0.113.41:8388#SS-2"


def _ss_old() -> str:
    raw = b"chacha20-ietf-poly1305:old-pass@203.0.113.42:8389"
    return "ss://" + base64.b64encode(raw).decode("ascii") + "#SS-3"


SS_OLD = _ss_old()

SOCKS = "socks://dXNlcjpwYXNz@203.0.113.30:1080#SOCKS-1"

HY2 = "hysteria2://hy-pass@hy.example.com:443?sni=hy.example.com&insecure=0#HY-1"

# Для golden-конфига: 2 участника + 2 запасных (после канонической сортировки).
FULL_LINKS = [VLESS_REALITY, VLESS_WS, TROJAN, VMESS]

VLESS_JUNK_ADDRESS = (
    "vless://11111111-2222-3333-4455-666666666669@0.0.0.0:443?security=tls#junk-zero"
)

VLESS_EXPIRED_NAME = (
    "vless://11111111-2222-3333-4455-666666666670@203.0.113.50:443?security=tls"
    "#%D0%98%D1%81%D1%82%D0%B5%D0%BA%D0%B0%D0%B5%D1%82%20NL-9"
)
