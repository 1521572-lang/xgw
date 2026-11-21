"""Qt scheduler regression tests for explicit refreshes during an active GET."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from xgw.gui import client as clienting  # noqa: E402
from xgw.gui import model  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class StateReply:
    def __init__(self, status):
        self.status = status

    def attribute(self, _):
        return self.status

    def readAll(self):
        return b'{"now":1000,"updated":999}'

    def error(self):
        return clienting.QNetworkReply.NetworkError.NoError

    def deleteLater(self):
        pass


@pytest.mark.parametrize("status", [200, 503, 401])
def test_explicit_updates_coalesce_while_state_request_is_pending(qapp, status):
    client = clienting.ApiClient(model.Session(8080, "a" * 64))
    client.running = True
    try:
        old = client.gate.begin()
        client.set_visible(False)
        client.set_visible(True)
        client.poll_soon(0.0)
        assert not client.timer.isActive()
        assert client.gate.issued == old

        client._state_done(StateReply(status), old)
        if status == 401:
            assert not client.timer.isActive() and client.link == clienting.LINK_AUTH
            return
        assert client.timer.isActive() and client.timer.interval() == 0
        assert client.gate.issued == old

        # When the follow-up completes the normal polling interval resumes.
        next_poll = client.gate.begin()
        client._state_done(StateReply(200), next_poll)
        assert client.timer.interval() == int(model.POLL_VISIBLE * 1000)
    finally:
        client.close()


def test_refresh_requested_by_state_signal_precedes_the_regular_timer(qapp):
    client = clienting.ApiClient(model.Session(8080, "a" * 64))
    client.running = True
    client.stateReceived.connect(lambda _: client.poll_soon(0.0))
    try:
        number = client.gate.begin()
        client._state_done(StateReply(200), number)
        assert client.timer.interval() == 0
    finally:
        client.close()
