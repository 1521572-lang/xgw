"""Применённый конфиг Xray для тестов — тот, с которым ядро запущено.

Перехват включается только тогда, когда в применённом конфиге есть inbound
перехвата на его порту (net/capture.py): правила отправляют пакеты именно туда,
и без inbound'а трафик ушёл бы в никуда. В тестах, где перехват включается,
конфиг должен быть на месте — как на живой машине, где его пишет Applier.
"""

from __future__ import annotations

import json

from xgw.config import Config


def applied_config(
    port: int | None = None, *, listen: str = "127.0.0.1", tun: str | None = "xgwtun0"
) -> dict:
    """Конфиг с inbound'ами перехвата: как их собирает генератор (builder.py).

    tun — имя интерфейса inbound'а `tun-in` (capture.method = "tun"); None — без него.
    """
    if port is None:
        port = Config().capture.tproxy_port
    inbounds = [
        {"tag": "tproxy-in", "listen": listen, "port": port, "protocol": "tunnel"},
        {"tag": "tproxy-in6", "listen": "::1", "port": port, "protocol": "tunnel"},
    ]
    if tun:
        inbounds.append({"tag": "tun-in", "protocol": "tun", "settings": {"name": tun}})
    return {"inbounds": inbounds}


def write(paths, config: dict | None = None) -> None:
    """Записать применённый конфиг туда, откуда его читает XGW."""
    path = paths.xray_config_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config if config is not None else applied_config(), ensure_ascii=False),
        encoding="utf-8",
    )
