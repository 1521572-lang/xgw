"""Свободный порт для тестов."""

from __future__ import annotations

import random
import socket

# Ниже диапазона временных портов ОС (49152+) и выше блока probe-портов стенда
# (21000–29000): сюда система сама никого не селит.
FALLBACK = (30000, 48000)


def _free(port: int) -> bool:
    """Можно ли сейчас занять порт и по TCP, и по UDP."""
    try:
        with socket.socket() as tcp, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            tcp.bind(("127.0.0.1", port))
            udp.bind(("127.0.0.1", port))
    except OSError:
        return False
    return True


def free_port() -> int:
    """Порт, который сейчас можно занять и по TCP, и по UDP.

    На Windows часть временных портов система резервирует (Hyper-V, WSL, Docker —
    `netsh int ipv4 show excludedportrange protocol=udp`), причём отдельно для TCP и
    для UDP. Порт, свободный по TCP, но зарезервированный по UDP, не открылся бы у
    inbound Xray с UDP и у DNS-заглушки стенда: тест падал бы раз в несколько запусков.

    Временные порты ОС выдаёт подряд, а резерв бывает сплошным блоком в сотни портов
    (на этой машине встречался блок из 700): несколько попыток подряд могут целиком
    попасть в него. Тогда порт берётся наугад из диапазона ниже временных.
    """
    for _ in range(20):
        with socket.socket() as tcp:
            tcp.bind(("127.0.0.1", 0))
            port = tcp.getsockname()[1]
        if _free(port):
            return port
    for _ in range(500):
        port = random.randrange(*FALLBACK)
        if _free(port):
            return port
    raise RuntimeError("не нашлось порта, свободного и по TCP, и по UDP")
