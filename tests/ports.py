"""Свободный порт для тестов."""

from __future__ import annotations

import socket


def free_port() -> int:
    """Порт, который сейчас можно занять и по TCP, и по UDP.

    На Windows часть временных портов система резервирует (Hyper-V, WSL, Docker —
    `netsh int ipv4 show excludedportrange protocol=udp`), причём отдельно для TCP и
    для UDP. Порт, свободный по TCP, но зарезервированный по UDP, не открылся бы у
    inbound Xray с UDP и у DNS-заглушки стенда: тест падал бы раз в несколько запусков.
    """
    for _ in range(100):
        with socket.socket() as tcp:
            tcp.bind(("127.0.0.1", 0))
            port = tcp.getsockname()[1]
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                    udp.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError("не нашлось порта, свободного и по TCP, и по UDP")
