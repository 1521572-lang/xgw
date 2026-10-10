"""Клиент стенда: загрузка через http-прокси Xray (http-in или probe-inbound).

Запускается в контексте шлюза и печатает итог одной строкой JSON:
  {"ok": true, "bytes": 2000000, "seconds": 12.1, "error": ""}

Запуск: python download.py --proxy 127.0.0.1:20001 --user xgw --password … URL
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from xgw.watch.checks import http_get_via_proxy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--proxy", required=True, help="адрес:порт прокси")
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--silence", type=float, default=60.0)
    parser.add_argument("--max-total", type=float, default=180.0)
    args = parser.parse_args()

    host, _, port = args.proxy.rpartition(":")
    started = time.monotonic()
    result = http_get_via_proxy(
        host, int(port), args.url, proxy_user=args.user, proxy_pass=args.password,
        silence=args.silence, max_total=args.max_total,
    )
    print(
        json.dumps(
            {
                "ok": result.ok,
                "bytes": result.downloaded,
                "seconds": round(time.monotonic() - started, 2),
                "error": result.error,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
