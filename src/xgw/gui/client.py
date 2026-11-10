"""Клиент панели XGW для окна: асинхронные запросы QNetworkAccessManager к 127.0.0.1.

Опрос /api/state — один запрос за раз (model.PollGate), раз в POLL_VISIBLE, пока окно на экране,
и реже, пока оно свёрнуто; после сбоя — паузы model.Backoff. Ответ старого запроса новое
состояние не перезаписывает. Действия — POST /api/<имя> с заголовком X-XGW-Panel, как у
страницы панели; одно и то же действие повторно не уходит, пока не пришёл ответ.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable

from PyQt6.QtCore import QByteArray, QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import model

# Связь с панелью: ok — состояние свежее, stale — демон давно не писал состояние,
# offline — панель не отвечает, auth — нужен вход.
LINK_OK, LINK_STALE, LINK_OFFLINE, LINK_AUTH = "ok", "stale", "offline", "auth"


def _request(url: str, *, cookie: str = "", post: bool = False) -> QNetworkRequest:
    request = QNetworkRequest(QUrl(url))
    request.setTransferTimeout(int(model.REQUEST_TIMEOUT * 1000))
    # Ссылку входа панель отдаёт ответом 303 с cookie: его заголовки нужны самому окну.
    request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
    if cookie:
        request.setRawHeader(b"Cookie", f"{model.COOKIE}={cookie}".encode("ascii"))
    if post:
        request.setRawHeader(model.HEADER.encode("ascii"), b"1")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
    return request


def _status(reply: QNetworkReply) -> int:
    code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
    return int(code) if code is not None else 0


class ApiClient(QObject):
    """Один на окно: опросник состояния и все запросы к панели."""

    stateReceived = pyqtSignal(dict)
    linkChanged = pyqtSignal(str, str)  # LINK_*, текст для человека
    actionFinished = pyqtSignal(str, bool, str)  # ключ действия, выполнено ли, текст панели
    busyChanged = pyqtSignal(str, bool)  # ключ действия, идёт ли оно

    def __init__(self, session: model.Session | None, parent: QObject | None = None,
                 *, rng: Callable[[], float] | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.network = QNetworkAccessManager(self)
        self.gate = model.PollGate()
        self.backoff = model.Backoff(rng) if rng is not None else model.Backoff()
        self.actions = model.ActionGuard()
        self.visible = True
        self.running = False
        self.link, self.link_text = "", ""
        self.state: dict | None = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)
        self.side = {"pool": model.PollGate(), "traffic": model.PollGate()}
        self.replies: set[QNetworkReply] = set()  # ещё без ответа — их обрывает close
        self.closed = False

    # --- опрос ---------------------------------------------------------------------------------

    def set_session(self, session: model.Session | None) -> None:
        self.session = session
        self.gate.drop()
        for gate in self.side.values():
            gate.drop()
        self.backoff.reset()
        self.state = None
        if self.running:
            self.poll_soon(0.0)

    def start(self) -> None:
        self.running = True
        self.poll_soon(0.0)

    def stop(self) -> None:
        self.running = False
        self.timer.stop()

    def close(self) -> None:
        """Окно закрывается: опрос остановлен, запросы без ответа обрываются и уже ничего не
        вызывают (иначе ответ пришёл бы к удалённому окну)."""
        self.stop()
        self.closed = True
        for reply in list(self.replies):
            with contextlib.suppress(TypeError, RuntimeError):
                reply.finished.disconnect()
            reply.abort()
            reply.deleteLater()
        self.replies.clear()

    def _send(self, reply: QNetworkReply, handler: Callable[[], None]) -> None:
        self.replies.add(reply)

        def finished() -> None:
            self.replies.discard(reply)
            if self.closed:
                reply.deleteLater()
                return
            handler()

        reply.finished.connect(finished)

    def set_visible(self, visible: bool) -> None:
        """Окно показали — опросить сразу; скрыли — следующий опрос через POLL_HIDDEN."""
        was, self.visible = self.visible, visible
        if visible and not was and self.running:
            self.poll_soon(0.0)

    def poll_soon(self, seconds: float) -> None:
        if not self.running:
            return
        self.timer.start(max(0, int(seconds * 1000)))

    def _interval(self) -> float:
        return model.POLL_VISIBLE if self.visible else model.POLL_HIDDEN

    def poll(self) -> None:
        if not self.running or self.closed:
            return
        if self.session is None:
            self._set_link(LINK_AUTH, model.HTTP_TEXTS[401])
            return
        number = self.gate.begin()
        if number is None:
            return  # прежний опрос ещё идёт: его ответ назначит следующий
        reply = self.network.get(_request(f"{self.session.base}/api/state",
                                          cookie=self.session.cookie))
        self._send(reply, lambda: self._state_done(reply, number))

    def _state_done(self, reply: QNetworkReply, number: int) -> None:
        code, data = _status(reply), bytes(reply.readAll())
        network = reply.errorString() if reply.error() != QNetworkReply.NetworkError.NoError else ""
        reply.deleteLater()
        fresh = self.gate.finish(number)
        if not fresh:
            return
        if code == 200:
            state = model.parse_json(data)
            if state is not None:
                self.backoff.reset()
                self.state = state
                stale = model.is_stale(state)
                self._set_link(LINK_STALE if stale else LINK_OK,
                               "Данные устарели: демон XGW не отвечает" if stale else "")
                self.stateReceived.emit(state)
                self.poll_soon(self._interval())
                return
            code, network = 0, "ответ панели — не JSON"
        if code == 401:
            self._set_link(LINK_AUTH, model.error_text(401))
            return  # без входа опрашивать незачем: окно попросит войти
        self._set_link(LINK_OFFLINE, model.error_text(code, data.decode("utf-8", "replace"),
                                                      network))
        self.poll_soon(self.backoff.fail())

    def _set_link(self, link: str, text: str) -> None:
        if (link, text) != (self.link, self.link_text):
            self.link, self.link_text = link, text
            self.linkChanged.emit(link, text)

    # --- действия -------------------------------------------------------------------------------

    def act(self, name: str, body: dict | None = None, key: str | None = None) -> bool:
        """POST /api/<name>. False — такое действие уже идёт (или входа нет)."""
        key = key or name
        if self.session is None or not self.actions.begin(key):
            return False
        self.busyChanged.emit(key, True)
        data = QByteArray(json.dumps(body or {}, ensure_ascii=False).encode("utf-8"))
        reply = self.network.post(
            _request(f"{self.session.base}/api/{name}", cookie=self.session.cookie, post=True),
            data)
        self._send(reply, lambda: self._act_done(reply, key))
        return True

    def _act_done(self, reply: QNetworkReply, key: str) -> None:
        code, data = _status(reply), bytes(reply.readAll())
        network = reply.errorString() if reply.error() != QNetworkReply.NetworkError.NoError else ""
        reply.deleteLater()
        self.actions.end(key)
        self.busyChanged.emit(key, False)
        result = model.parse_json(data) if code == 200 else None
        if result is not None:
            ok = bool(result.get("ok"))
            text = str(result.get("text") or ("Готово" if ok else "Не получилось"))
            notes = [str(note) for note in result.get("notes") or [] if note]
            self.actionFinished.emit(key, ok, " ".join([text, *notes]))
        else:
            if code == 401:
                self._set_link(LINK_AUTH, model.error_text(401))
            self.actionFinished.emit(key, False, model.error_text(
                code, data.decode("utf-8", "replace"), network))
        self.poll_soon(0.0)  # итог действия — в состоянии демона: показать его сразу

    # --- отдельные запросы ----------------------------------------------------------------------

    def fetch(self, kind: str, path: str, done: Callable[[dict | None, str], None]) -> bool:
        """GET /api/pool, /api/traffic…: один запрос каждого вида за раз; done(данные, ошибка)."""
        gate = self.side.setdefault(kind, model.PollGate())
        if self.session is None:
            done(None, model.error_text(401))
            return False
        number = gate.begin()
        if number is None:
            return False
        reply = self.network.get(_request(f"{self.session.base}{path}",
                                          cookie=self.session.cookie))

        def finished() -> None:
            code, data = _status(reply), bytes(reply.readAll())
            network = (reply.errorString()
                       if reply.error() != QNetworkReply.NetworkError.NoError else "")
            reply.deleteLater()
            if not gate.finish(number):
                return
            if code == 401:
                self._set_link(LINK_AUTH, model.error_text(401))
            found = model.parse_json(data) if code == 200 else None
            if found is None:
                done(None, model.error_text(code, data.decode("utf-8", "replace"), network))
            else:
                done(found, "")

        self._send(reply, finished)
        return True

    def exchange(self, port: int, code: str,
                 done: Callable[[model.Session | None, str], None]) -> None:
        """Одноразовый код входа → cookie панели (ответ 303 на /?login=…, как в браузере)."""
        reply = self.network.get(_request(f"http://127.0.0.1:{port}/?login={code}"))

        def finished() -> None:
            status = _status(reply)
            headers = [bytes(value) for name, value in reply.rawHeaderPairs()
                       if bytes(name).lower() == b"set-cookie"]
            network = (reply.errorString()
                       if reply.error() != QNetworkReply.NetworkError.NoError else "")
            reply.deleteLater()
            cookie = model.cookie_from(headers) if status == 303 else ""
            if cookie:
                done(model.Session(port, cookie), "")
            elif status == 403:
                done(None, "Код входа не подошёл или устарел — попробуйте ещё раз")
            else:
                done(None, model.error_text(status, "", network))

        self._send(reply, finished)
