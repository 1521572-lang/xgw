import subprocess

import pytest

from xgw.watch import video_probe_http as http


@pytest.mark.parametrize("version,features,expected", [
    (b"8.18.0", b"SSL HTTP2", True),
    (b"8.4.0", b"SSL HTTP2", True),
    (b"8.3.0", b"SSL HTTP2", False),
    (b"8.18.0", b"SSL", False),
])
def test_http2_requires_curl_with_streaming_limit(monkeypatch, version, features, expected):
    def run(command, **kwargs):
        assert command == ["/usr/bin/curl", "--disable", "--version"]
        assert kwargs["timeout"] == 2
        output = b"curl " + version + b" (fixture)\nFeatures: " + features
        return subprocess.CompletedProcess(command, 0, output)

    monkeypatch.setattr(http.subprocess, "run", run)
    assert http.supports_http2("/usr/bin/curl") is expected


@pytest.mark.parametrize("code,downloaded,length,encoding,exit_code,ok", [
    (b"200", b"31", b"31", b" GZip ", 0, False),
    (b"206", b"16384", b"16384", b"", 0, True),
    (b"200", b"0", b"65536", b"PRIVATE", 63, False),
    (b"200", b"16384", b"", b"", 63, True),
    (b"000", b"0", b"31", b"Gzip", 56, False),
])
def test_curl_request_bounds_and_response_metadata(
    monkeypatch, code, downloaded, length, encoding, exit_code, ok,
):
    def run(command, **kwargs):
        assert command[0:4] == ["/usr/bin/curl", "--disable", "--config", "-"]
        assert "--http2" in command and "--verbose" in command and "--location" not in command
        assert command[command.index("--range") + 1] == "0-16383"
        assert command[command.index("--max-filesize") + 1] == "16384"
        assert command[command.index("--max-time") + 1] == "3.000"
        assert command[command.index("--proxy") + 1] == "http://127.0.0.1:12345"
        assert command[command.index("--noproxy") + 1] == ""
        assert all("PRIVATE" not in arg for arg in command)
        assert b"token=PRIVATE" in kwargs["input"] and b":PRIVATE" in kwargs["input"]
        assert kwargs["timeout"] == 3 and kwargs["env"] == http.CURL_ENV
        output = b"\n".join([
            code, b"2", downloaded, length, encoding, b"Text/Plain; x=PRIVATE", b"",
        ])
        stderr = (b"* ALPN: curl offers h2,http/1.1\n* ALPN: server accepted h2\n"
                  b"> Proxy-Authorization: Basic PRIVATE\n< X-Private: PRIVATE\n")
        return subprocess.CompletedProcess(command, exit_code, output, stderr)

    monkeypatch.setattr(http.subprocess, "run", run)
    reply, meta = http.get("/usr/bin/curl", "https://example.test/?token=PRIVATE", 12345,
                           "PRIVATE", "Firefox", http2=True, max_total=3)
    assert reply.ok is ok and reply.downloaded == int(downloaded)
    assert reply.content_type == ("text/plain" if code != b"000" else "")
    assert meta == {
        "http_requested": "2", "http_version": "2" if code != b"000" else None,
        "content_length": int(length) if length and code != b"000" else None,
        "content_encoding": {b" GZip ": "gzip", b"PRIVATE": "other"}.get(encoding),
        "curl_exit": exit_code,
        "alpn_offered": ["h2", "http/1.1"],
        "alpn_selected": "h2",
    }
    assert "PRIVATE" not in repr((reply, meta))


def test_curl_process_timeout_preserves_requested_protocol(monkeypatch):
    def run(command, **_kwargs):
        assert "--http1.1" in command and "--http2" not in command
        stderr = b"* ALPN: curl offers http/1.1\n* certificate details PRIVATE\n"
        raise subprocess.TimeoutExpired(command, 3, output=b"PRIVATE", stderr=stderr)

    monkeypatch.setattr(http.subprocess, "run", run)
    reply, meta = http.get("/usr/bin/curl", "https://example.test/", 12345, "PRIVATE", "Firefox",
                           http2=False, max_total=3)
    assert not reply.ok and reply.kind == "timeout"
    assert meta["http_requested"] == "1.1" and meta["http_version"] is None
    assert meta["alpn_offered"] == ["http/1.1"] and meta["alpn_selected"] is None
    assert "PRIVATE" not in repr((reply, meta))


@pytest.mark.parametrize("stderr,offered,selected", [
    (b"< X-Note: * ALPN: server accepted h2\n", None, None),
    (b"* ALPN: curl offers h2,http/1.1\n"
     b"* ALPN: server did not agree on a protocol. Uses default.\n", ["h2", "http/1.1"], "none"),
    (b"* ALPN: curl offers h2,PRIVATE\n"
     b"* ALPN: server accepted PRIVATE\n", ["h2", "other"], "other"),
    (b"* ALPN: curl offers h2\n* ALPN: server accepted h2\n"
     b"* ALPN: curl offers http/1.1\n", ["http/1.1"], None),
])
def test_alpn_metadata_uses_only_protocol_labels(stderr, offered, selected):
    assert http._alpn(stderr) == {"alpn_offered": offered, "alpn_selected": selected}
