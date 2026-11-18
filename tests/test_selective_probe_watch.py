import pytest

from docs.helpers import selective_probe_watch as watch
from docs.helpers import selective_wan_control as wan_control
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


def test_wan_control_skips_tcp_when_bypass_routes_to_another_interface(monkeypatch):
    monkeypatch.setattr(wan_control, "route", lambda *_args: {"dev": "xgw-tun"})

    def unexpected_connect(*_args, **_kwargs):
        pytest.fail("control must not send TCP traffic on an unconfirmed WAN")

    monkeypatch.setattr(wan_control.marknet, "connect_marked", unexpected_connect)
    result = wan_control.control("203.0.113.4", "wan0", 2, 111, 0)
    assert result["tcp"] == "wan_route_unconfirmed"


def test_wan_control_binds_expected_interface_and_uses_configured_bypass(monkeypatch):
    recorded = []

    class Sock:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def setsockopt(self, _level, _option, value):
            recorded.append(value)

        def settimeout(self, timeout):
            assert timeout == 5

        def connect(self, address):
            recorded.append(address)

        def getsockname(self):
            return "192.0.2.2", 1234

    def lookup(peer, mark, uid):
        recorded.append((peer, mark, uid))
        return {"dev": "wan0", "prefsrc": "192.0.2.2"}

    def tcp(host, port, *, timeout, mark, connect):
        assert mark == 2 and timeout == 5
        sock = Sock()
        connect(sock, (host, port))
        return sock

    monkeypatch.setattr(wan_control, "route", lookup)
    monkeypatch.setattr(wan_control.marknet, "connect_marked", tcp)
    monkeypatch.setattr(wan_control.socket, "SO_BINDTODEVICE", 25, raising=False)
    result = wan_control.control("203.0.113.4", "wan0", 2, 111, 0)
    assert recorded == [
        ("203.0.113.4", 2, 0), ("203.0.113.4", 0x10000000, 111),
        b"wan0\0", ("203.0.113.4", 443),
    ]
    assert result["tcp"] == "connected" and result["source_matches_lookup"]
