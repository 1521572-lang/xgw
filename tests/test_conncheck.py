"""Адрес проверки связности NetworkManager для исключения в барьере (net/conncheck.py)."""

import json

from xgw.net import cmd, conncheck
from xgw.paths import Paths


def _run(enabled="b true", uri='s "http://connectivity-check.ubuntu.com./"'):
    def run(argv, **_kwargs):
        if argv[-1] == "ConnectivityCheckEnabled":
            return enabled + chr(10)
        return uri + chr(10)
    return run


def _missing(argv, **_kwargs):
    raise cmd.CommandError("busctl: программа не найдена")


def test_uri_from_busctl_and_plain_text():
    assert conncheck.parse_uri('s "http://connectivity-check.ubuntu.com./"') == (
        "connectivity-check.ubuntu.com", 80)
    assert conncheck.parse_uri("https://check.example.org:8443/x") == ("check.example.org", 8443)
    assert conncheck.parse_uri('s ""') is None
    assert conncheck.nm_target(_run(enabled="b false")) is None
    assert conncheck.nm_target(_missing) is None


def test_refresh_writes_public_ipv4_only_and_removes_when_check_is_off(tmp_path):
    paths = Paths(tmp_path)
    paths.run.mkdir(parents=True)
    answers = ["91.189.91.49", "10.0.0.1", "2001:db8::1", "185.125.190.17", "91.189.91.49"]
    assert conncheck.refresh(paths, lambda host: answers, run=_run())
    data = json.loads(conncheck.path(paths).read_text())
    assert data == {"host": "connectivity-check.ubuntu.com", "port": 80,
                    "ips": ["185.125.190.17", "91.189.91.49"]}
    assert conncheck.read(paths) == (("185.125.190.17", "91.189.91.49"), 80)
    assert not conncheck.refresh(paths, lambda host: answers, run=_run())
    assert not conncheck.refresh(paths, lambda host: [], run=_run())  # не разрешился — прежнее
    assert conncheck.read(paths)[0]
    assert conncheck.refresh(paths, lambda host: answers, run=_run(enabled="b false"))
    assert conncheck.read(paths) == ((), 80)
    conncheck.path(paths).write_text('{"ips": ["10.0.0.1"], "port": 80}')
    assert conncheck.read(paths) == ((), 80)
