"""Клиент панели XGW для стенда — то, что на настоящей машине делает браузер:
входит по токену, читает состояние, нажимает кнопки. Запускается на самом шлюзе.

  panel_client.py <порт> raw <путь>                     — запрос без входа
  panel_client.py <порт> state <токен>                  — состояние панели
  panel_client.py <порт> act <токен> <действие> <JSON>  — нажатие кнопки

Печатает одну строку JSON; при сбое в ней есть поле "error".
"""

from __future__ import annotations

import http.client
import json
import sys


def request(port: int, method: str, path: str, *, cookie: str = "", body: bytes | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    headers = {"Host": f"127.0.0.1:{port}"}
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


def login(port: int, token: str) -> str:
    response, _text = request(port, "GET", f"/?token={token}")
    if response.status != 303:
        raise ValueError(f"вход не удался: HTTP {response.status}")
    return response.getheader("Set-Cookie").split(";")[0]


def main() -> None:
    port, command, *rest = sys.argv[1:]
    try:
        if command == "raw":
            response, text = request(int(port), "GET", rest[0])
            result = {"status": response.status, "body": text[:4000]}
        elif command == "state":
            cookie = login(int(port), rest[0])
            response, text = request(int(port), "GET", "/api/state", cookie=cookie)
            result = json.loads(text) if response.status == 200 else {"error": text}
        elif command == "act":
            token, name, body = rest
            response, text = request(
                int(port), "POST", f"/api/{name}", cookie=login(int(port), token),
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
