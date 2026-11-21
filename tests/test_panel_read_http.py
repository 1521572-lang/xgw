"""Read-only loopback HTTP boundary for the standalone panel process."""

import http.client
import json
import threading

from xgw.watch import panel_ipc, panel_read_http


def test_only_authenticated_status_reaches_ipc_and_backend_failure_is_bounded(
        tmp_path, monkeypatch):
    path = tmp_path / "panel.sock"
    secret = b"k" * 43
    calls = []
    status = {"mode": "off", "engine_mode": "off", "state": "off", "fresh": True,
              "policy_matched": True}

    def overview(socket_path, *, server_uid):
        calls.append((socket_path, server_uid))
        if len(calls) == 2:
            raise panel_ipc.ProtocolError("unexpected_server_uid")
        return status

    monkeypatch.setattr(panel_ipc, "read_overview", overview)
    with panel_read_http.create_server(path, secret) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        thread.start()
        host, port = server.server_address

        def request(method="GET", route=panel_read_http.ROUTE, **headers):
            connection = http.client.HTTPConnection(host, port, timeout=2)
            try:
                connection.request(method, route, headers=headers)
                response = connection.getresponse()
                assert response.getheader("Cache-Control") == "no-store"
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
            finally:
                connection.close()

        key = {"Authorization": "Bearer " + secret.decode("ascii")}
        try:
            assert host == "127.0.0.1"
            assert request()[0] == 401
            assert request(Host="foreign.invalid", **key)[0] == 403
            assert request(Origin="https://foreign.invalid", **key)[0] == 403
            assert request("POST", **key)[0] == 405
            assert request(route="/api/state", **key)[0] == 404
            assert calls == []
            assert request(Origin=f"http://{host}:{port}", **key) == (200, {"zapret2": status})
            assert request(**key) == (503, {"error": "unavailable"})
            assert request("HEAD", **key) == (200, None)
            assert calls == [(path, 0)] * 3
        finally:
            server.shutdown()
            thread.join(timeout=2)
