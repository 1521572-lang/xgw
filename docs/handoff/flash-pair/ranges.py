"""Four small HTTP Range observations on loopback for paired Flash runs."""

import hashlib
import http.client
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def main():
    content = secrets.token_bytes(8192)
    start = 128 + secrets.randbelow(512)
    length = 1024
    end = start + length - 1
    kinds = ["exact", "shifted", "short", "whole"]
    secrets.SystemRandom().shuffle(kinds)
    cases = {f"/{index}": kind for index, kind in enumerate(kinds, 1)}

    class Origin(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Range") != f"bytes={start}-{end}" or self.path not in cases:
                self.send_error(400)
                return
            kind = cases[self.path]
            if kind == "whole":
                body = content
                self.send_response(200)
            else:
                offset = start + int(kind == "shifted")
                body = content[offset:offset + length]
                if kind == "short":
                    body = body[:-17]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {offset}-{offset + length - 1}/{len(content)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    expected = hashlib.sha256(content[start:end + 1]).hexdigest()
    with HTTPServer(("127.0.0.1", 0), Origin) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path in cases:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                try:
                    conn.request("GET", path, headers={"Range": f"bytes={start}-{end}"})
                    response = conn.getresponse()
                    body = response.read()
                    actual = hashlib.sha256(body).hexdigest()
                    header = response.getheader("Content-Range", "-").replace("bytes ", "")
                    print(f"RANGE id=H{path[1:]} requested={start}-{end} expected_bytes={length}"
                          f" http={response.status} content_range={header} read={len(body)}"
                          f" body_matches={int(actual == expected)}", flush=True)
                finally:
                    conn.close()
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    main()
