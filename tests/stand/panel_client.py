"""Клиент панели XGW для стенда. Системный ключ используется локально
для вычисления cookie. Скрипт запускается на самом шлюзе.

  panel_client.py <порт> raw <путь>                     — запрос без входа
  panel_client.py <порт> state <токен>                  — состояние панели
  panel_client.py <порт> act <токен> <действие> <JSON>  — нажатие кнопки
  panel_client.py <порт> host <Host> <токен>            — состояние с другим Host (так
                                                          приходит Tailscale Serve)

Печатает одну строку JSON; при сбое в ней есть поле "error".
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import sys


def request(
    port: int, method: str, path: str, *, cookie: str = "", body: bytes | None = None,
    host: str = "",
):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if cookie:
        headers["Cookie"] = cookie
    if body is not None:
        headers.update({
            "Content-Type": "application/json", "X-XGW-Panel": "1",
            "Origin": f"http://127.0.0.1:{port}",
        })
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        return response, response.read().decode("utf-8", "replace")
    finally:
        conn.close()


def session_cookie(token: str) -> str:
    digest = hmac.new(token.encode("utf-8"), b"xgw-panel", hashlib.sha256).hexdigest()
    return f"xgw_panel={digest}"


def main() -> None:
    port, command, *rest = sys.argv[1:]
    try:
        if command == "raw":
            response, text = request(int(port), "GET", rest[0])
            result = {"status": response.status, "body": text[:4000]}
        elif command == "state":
            cookie = session_cookie(rest[0])
            response, text = request(int(port), "GET", "/api/state", cookie=cookie)
            result = json.loads(text) if response.status == 200 else {"error": text}
        elif command == "host":
            host, token = rest
            response, text = request(
                int(port), "GET", "/api/state", cookie=session_cookie(token), host=host)
            result = {"status": response.status, "body": text[:300]}
        elif command == "act":
            token, name, body = rest
            response, text = request(
                int(port), "POST", f"/api/{name}", cookie=session_cookie(token),
                body=body.encode("utf-8"),
            )
            result = json.loads(text) if response.status == 200 else {
                "error": text, "status": response.status}
        else:
            result = {"error": f"нет команды {command}"}
    except (OSError, ValueError, IndexError) as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
