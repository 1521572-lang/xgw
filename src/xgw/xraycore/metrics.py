"""Метрики Xray: GET 127.0.0.1:<metrics_port>/debug/vars → observatory.

Фактический формат Xray 26.3.27 (проверено на живом процессе):
  "observatory": {
    "proxy-a": {"alive": true, "delay": 4, "outbound_tag": "proxy-a",
                 "health_ping": {"all": 2, "average": 4809600, ...}},
    "proxy-b": {"outbound_tag": "proxy-b", "health_ping": {"all": 2, "fail": 2}}
  }
`alive` отсутствует у мёртвых узлов; `delay` — миллисекунды,
`health_ping.average` — наносекунды. XGW только читает состояние
(переключает серверы сам Xray).
"""

from __future__ import annotations

import json
import re

from .. import fetch


def fetch_metrics(port: int, *, timeout: float = 5.0) -> dict:
    result = fetch.fetch_url(
        f"http://127.0.0.1:{port}/debug/vars", timeout=timeout, retries=1
    )
    if result.status != 200:
        raise RuntimeError(f"/debug/vars: HTTP {result.status}")
    return json.loads(result.body.decode("utf-8"))


def parse_duration(value: str | int | float, *, unit_ms: bool = True) -> float | None:
    """Значение → секунды. Число по умолчанию — миллисекунды (delay),
    unit_ms=False — наносекунды (health_ping.average)."""
    if isinstance(value, (int, float)):
        return float(value) / (1000.0 if unit_ms else 1e9)
    match = re.fullmatch(r"([\d.]+)\s*(ns|us|µs|ms|s|m|h)?", str(value).strip())
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or "ms"
    factor = {
        "ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0,
    }
    return number * factor[unit]


def parse_observatory(metrics: dict) -> dict[str, dict]:
    """По каждому outbound-тегу — alive и delay (секунды)."""
    section = metrics.get("observatory")
    if isinstance(section, str):  # толерантность к JSON-строке
        try:
            section = json.loads(section)
        except json.JSONDecodeError:
            section = None
    if not isinstance(section, dict):
        return {}
    result: dict[str, dict] = {}
    for tag, entry in section.items():
        if not isinstance(entry, dict):
            continue
        delay: float | None = None
        if entry.get("delay") is not None:
            delay = parse_duration(entry["delay"], unit_ms=True)
        elif isinstance(entry.get("health_ping"), dict):
            average = entry["health_ping"].get("average")
            if average is not None:
                delay = parse_duration(average, unit_ms=False)
        result[str(tag)] = {"alive": bool(entry.get("alive", False)), "delay": delay}
    return result
