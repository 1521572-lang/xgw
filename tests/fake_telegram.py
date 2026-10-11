"""Поддельный Telegram Bot API для тестов: getMe, getUpdates и sendMessage на
127.0.0.1. Настоящих токенов тесты не используют (раздел 12 ТЗ): токен — выдуманный.

Устроен как настоящий: getUpdates отдаёт сообщения с update_id не меньше offset
(что раньше — подтверждено и удалено) и, если сообщений нет, ждёт timeout секунд.
Ответы — `{"ok": true, "result": …}`, ошибки — `{"ok": false, "error_code", "description"}`.

Как отдельный процесс (стенд, «машина»): `python fake_telegram.py --host 5.5.5.1 --port 8081`.
Тогда «пользователем» управляют запросы GET: `/_say?text=/status&chat=1001&kind=private&age=0`
(сообщение боту), `/_sent` (что бот ответил, JSON), `/_calls` (какие методы вызывались).
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

TOKEN = "123456789:" + "AAFakeTokenForTestsOnly_0123456789abc"
BOT_NAME = "xgw_test_bot"
OWNER = 1001  # личный чат владельца: у личных чатов Telegram идентификатор положительный


class FakeTelegram:
    def __init__(self, token: str = TOKEN, *, poll_wait: float = 0.05) -> None:
        self.token = token
        self.poll_wait = poll_wait
        self.updates: list[dict] = []
        self.sent: list[dict] = []  # параметры каждого sendMessage
        self.calls: list[str] = []  # имена вызванных методов
        self.offsets: list[int] = []
        self.refuse = 0  # ответить на следующие N запросов HTTP 401
        self.broken = False  # отвечать не по Bot API
        self._next = 100
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self, host: str = "127.0.0.1", port: int = 0) -> FakeTelegram:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args) -> None:
                pass

            def do_GET(self) -> None:
                url = urlsplit(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                data = json.dumps(fake.control(url.path, query)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or "0")
                params = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
                code, body = fake.handle(self.path, params)
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # --- что делает «пользователь» -------------------------------------------------

    def say(
        self, text: str, *, chat: int = OWNER, kind: str = "private", age: float = 0.0,
        sender: int | None = None,
    ) -> int:
        """Сообщение боту. age — сколько секунд назад оно было отправлено."""
        with self._lock:
            self._next += 1
            self.updates.append({
                "update_id": self._next,
                "message": {
                    "message_id": self._next, "date": int(time.time() - age), "text": text,
                    "from": {"id": sender or chat, "is_bot": False, "first_name": "Тест"},
                    "chat": {"id": chat, "type": kind},
                },
            })
            return self._next

    def replies(self, chat: int | None = None) -> list[str]:
        return [item["text"] for item in self.sent if chat is None or int(item["chat_id"]) == chat]

    def control(self, path: str, query: dict) -> object:
        """Управление «пользователем» по HTTP — для процесса на стенде."""
        if path == "/_say":
            return {"update_id": self.say(
                query.get("text", ""), chat=int(query.get("chat") or OWNER),
                kind=query.get("kind", "private"), age=float(query.get("age") or 0),
            )}
        if path == "/_sent":
            return self.sent
        if path == "/_calls":
            return self.calls
        return {"error": "нет такого пути"}

    # --- сам API ---------------------------------------------------------------------

    def handle(self, path: str, params: dict) -> tuple[int, object]:
        prefix = f"/bot{self.token}/"
        if self.refuse > 0 and path.startswith("/bot"):
            self.refuse -= 1
            return 401, {"ok": False, "error_code": 401, "description": "Unauthorized"}
        if not path.startswith(prefix):
            return 401, {"ok": False, "error_code": 401, "description": "Unauthorized"}
        method = path[len(prefix):]
        self.calls.append(method)
        if self.broken:
            return 200, b"<html>not the bot api</html>"
        if method == "getMe":
            return 200, {"ok": True, "result": {"id": 123456789, "is_bot": True,
                                                "username": BOT_NAME}}
        if method == "sendMessage":
            self.sent.append(params)
            return 200, {"ok": True, "result": {"message_id": len(self.sent)}}
        if method == "getUpdates":
            return 200, {"ok": True, "result": self._updates(params)}
        return 404, {"ok": False, "error_code": 404, "description": "Not Found"}

    def _updates(self, params: dict) -> list[dict]:
        offset = int(params.get("offset") or 0)
        self.offsets.append(offset)
        deadline = time.monotonic() + min(float(params.get("timeout") or 0), self.poll_wait)
        while True:
            with self._lock:
                self.updates = [u for u in self.updates if u["update_id"] >= offset]
                ready = list(self.updates)
            if ready or time.monotonic() >= deadline:
                return ready
            time.sleep(0.02)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--poll-wait", type=float, default=3.0, help="как долго ждёт getUpdates")
    args = parser.parse_args()
    FakeTelegram(args.token, poll_wait=args.poll_wait).start(args.host, args.port)
    print("READY", flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
