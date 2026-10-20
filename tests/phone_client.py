"""Клиент API приложения XGW — то, что будет делать приложение для Android: привязка по
коду из QR и подписанные запросы (phones.py). Нужен тестам, стенду и программе испытаний,
пока приложения нет.

    python3 phone_client.py URL hello
    python3 phone_client.py URL pair КОД ФАЙЛ_КЛЮЧА        привязаться, ключ — в файл (0600)
    python3 phone_client.py URL state ФАЙЛ_КЛЮЧА
    python3 phone_client.py URL act ФАЙЛ_КЛЮЧА JSON
    python3 phone_client.py URL config ФАЙЛ_КЛЮЧА          только сводка: серверов N
    python3 phone_client.py URL replay ФАЙЛ_КЛЮЧА          повтор того же запроса — 403

URL — https://<шлюз>.<tailnet>.ts.net (Funnel) или http://127.0.0.1:ПОРТ с --host ИМЯ.
--via IP — соединяться с этим адресом (имя — только в TLS и Host): так запрос идёт через
ретранслятор Funnel из интернета, даже когда имя на этой машине разрешается в адрес tailnet.
Печатает одну строку JSON; секретов (ключ, коды, адреса серверов) не печатает.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import os
import secrets
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit


def signed_text(phone: str, method: str, path: str, stamp: str, nonce: str, body: bytes) -> bytes:
    digest = hashlib.sha256(body).hexdigest()
    return "\n".join((phone, method.upper(), path, stamp, nonce, digest)).encode("utf-8")


class _Pinned(http.client.HTTPSConnection):
    """HTTPS к заданному адресу, а имя — в SNI и проверке сертификата."""

    def __init__(self, name: str, port: int, via: str, **kwargs) -> None:
        super().__init__(name, port, **kwargs)
        self.via = via

    def connect(self) -> None:
        sock = socket.create_connection((self.via, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class PhoneClient:
    def __init__(self, url: str, *, host: str = "", via: str = "", phone: str = "",
                 key: bytes = b"", timeout: float = 20.0) -> None:
        parts = urlsplit(url)
        self.scheme, self.name = parts.scheme, parts.hostname or ""
        self.port = parts.port or (443 if self.scheme == "https" else 80)
        self.host = host or parts.netloc
        self.via = via
        self.phone, self.key = phone, key
        self.timeout = timeout
        self.last: tuple[str, str, bytes, dict] | None = None

    def _conn(self) -> http.client.HTTPConnection:
        if self.scheme == "https":
            context = ssl.create_default_context()
            if self.via:
                return _Pinned(self.name, self.port, self.via, timeout=self.timeout,
                               context=context)
            return http.client.HTTPSConnection(self.name, self.port, timeout=self.timeout,
                                               context=context)
        return http.client.HTTPConnection(self.name, self.port, timeout=self.timeout)

    def raw(self, method: str, path: str, body: bytes = b"", headers: dict | None = None):
        conn = self._conn()
        try:
            conn.request(method, path, body=body or None,
                         headers={"Host": self.host, "Content-Type": "application/json",
                                  **(headers or {})})
            response = conn.getresponse()
            data = response.read()
        finally:
            conn.close()
        try:
            payload = json.loads(data or b"{}")
        except ValueError:
            payload = {"raw": data[:200].decode("utf-8", "replace")}
        return response.status, payload

    def signed(self, method: str, path: str, payload: dict | None = None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        stamp, nonce = str(int(time.time())), secrets.token_urlsafe(18)
        signature = hmac.new(self.key, signed_text(self.phone, method, path, stamp, nonce, body),
                             hashlib.sha256).hexdigest()
        headers = {"X-XGW-Phone": self.phone, "X-XGW-Time": stamp, "X-XGW-Nonce": nonce,
                   "X-XGW-Signature": signature}
        self.last = (method, path, body, headers)
        return self.raw(method, path, body, headers)

    def replay(self):
        """Тот же запрос ещё раз — шлюз должен отказать."""
        assert self.last is not None
        method, path, body, headers = self.last
        return self.raw(method, path, body, headers)

    def pair(self, code: str, name: str = "Тестовый телефон"):
        status, payload = self.raw("POST", "/api/pair",
                                   json.dumps({"code": code, "name": name}).encode("utf-8"))
        if status == 200:
            self.phone = payload["phone"]
            self.key = base64.b64decode(payload["key"])
        return status, payload


def _load(path: str) -> tuple[str, bytes]:
    with open(path, encoding="ascii") as handle:
        phone, key = handle.read().split()
    return phone, base64.b64decode(key)


def main(argv: list[str]) -> int:
    via, host = "", ""
    while argv and argv[0].startswith("--"):
        flag, value, argv = argv[0], argv[1], argv[2:]
        via = value if flag == "--via" else via
        host = value if flag == "--host" else host
    url, command, *rest = argv
    client = PhoneClient(url, host=host, via=via)
    try:
        if command == "hello":
            status, payload = client.raw("GET", "/api/hello")
            result = {"status": status, "app": payload.get("app")}
        elif command == "pair":
            code, keyfile = rest
            status, payload = client.pair(code)
            result = {"status": status, "paired": status == 200,
                      "name": payload.get("name"), "error": payload.get("error")}
            if status == 200:
                fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="ascii") as handle:
                    handle.write(f"{client.phone} {base64.b64encode(client.key).decode()}\n")
        else:
            client.phone, client.key = _load(rest[0])
            if command == "state":
                status, payload = client.signed("GET", "/api/state")
                result = {"status": status, "state": payload.get("state"),
                          "members": len(payload.get("members") or []),
                          "power": payload.get("power"), "error": payload.get("error")}
            elif command == "act":
                status, payload = client.signed("POST", "/api/act", json.loads(rest[1]))
                result = {"status": status, "ok": payload.get("ok"), "text": payload.get("text"),
                          "error": payload.get("error")}
            elif command == "config":
                status, payload = client.signed("GET", "/api/phone-config")
                config = payload.get("config") or {}
                result = {"status": status, "servers": len(payload.get("servers") or []),
                          "inbound": [item.get("protocol") for item in config.get("inbounds", [])],
                          "error": payload.get("error")}
            elif command == "replay":
                first, _payload = client.signed("GET", "/api/state")
                second, payload = client.replay()
                result = {"first": first, "replay": second}
            else:
                result = {"error": f"нет команды {command}"}
    except (OSError, ValueError, ssl.SSLError) as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
