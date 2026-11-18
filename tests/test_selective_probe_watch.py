import pytest

from docs.helpers import selective_probe_watch as watch
from xgw.net import cmd


def test_socket_stats_distinguishes_received_data_from_missing_tcp_info(monkeypatch):
    text = (
        "ESTAB 0 517 192.0.2.1:43120 198.51.100.2:443 uid:150 ino:99 sk:abc "
        "cubic rto:208 bytes_sent:1034 bytes_acked:1 bytes_retrans:517 retrans:1/2\n"
        "ESTAB 0 0 [::ffff:192.0.2.1]:43121 [::ffff:198.51.100.3]:443 sk:def "
        "cubic rto:208 bytes_acked:518 bytes_received:3456 data_segs_in:3\n"
        "SYN-SENT 0 1 192.0.2.1:43122 198.51.100.4:443 sk:123\n"
    )

    def run(args, *, timeout):
        assert args[-7:] == ["fwmark", "=", "0x10000000", "and", "dport", "=", ":443"]
        assert timeout == 1
        return text

    monkeypatch.setattr(watch.cmd, "run", run)
    result = watch.socket_stats()
    assert result["state"] == "read"
    pending, received, unknown = result["sockets"]
    assert pending["bytes_received"] == 0 and pending["bytes_acked"] == 1
    assert pending["retrans_total"] == 2
    assert received["peer_ip"] == "198.51.100.3"
    assert (received["bytes_received"], received["data_segs_in"]) == (3456, 3)
    assert unknown["bytes_received"] is None
    assert "192.0.2.1" not in str(result)


@pytest.mark.parametrize(("text", "state"), [
    ("", "read"), ("unexpected row\n", "unexpected_format"),
])
def test_socket_stats_distinguishes_empty_read_from_bad_format(monkeypatch, text, state):
    monkeypatch.setattr(watch.cmd, "run", lambda *_args, **_kwargs: text)
    assert watch.socket_stats() == {"state": state, "sockets": []}


def test_socket_stats_denied_is_unavailable(monkeypatch):
    def run(*_args, **_kwargs):
        raise cmd.CommandError("private message")

    monkeypatch.setattr(watch.cmd, "run", run)
    assert watch.socket_stats() == {"state": "unavailable", "sockets": []}
