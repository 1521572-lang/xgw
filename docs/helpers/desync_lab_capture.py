#!/usr/bin/env python3
"""Bounded Ethernet/IP capture for the isolated T05 lab (Linux AF_PACKET)."""

import argparse
import selectors
import socket
import struct
import time
from pathlib import Path

SNAPLEN = 128
MAX_PACKETS = 16000
ETH_P_ALL = 3
_PCAP_HEADER = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, SNAPLEN, 1)


def matches(frame: memoryview, addresses: set[bytes]) -> bool:
    if len(frame) < 38 or frame[12:14] != b"\x08\x00" or frame[23] != 6:
        return False
    start = 14 + (frame[14] & 15) * 4
    if start < 34 or len(frame) < start + 4:
        return False
    # Non-initial fragments do not carry ports.
    if struct.unpack_from("!H", frame, 20)[0] & 0x1FFF:
        return False
    src, dst = bytes(frame[26:30]), bytes(frame[30:34])
    sport, dport = struct.unpack_from("!HH", frame, start)
    return {src, dst} == addresses and 443 in (sport, dport)


def capture(interface: str, out: Path, stop: Path, ready: Path) -> int:
    addresses = {socket.inet_aton("192.0.2.1"), socket.inet_aton("203.0.113.2")}
    frame = memoryview(bytearray(SNAPLEN))
    with (socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL)) as sock,
          selectors.DefaultSelector() as poll, out.open("xb") as stream):
        sock.bind((interface, ETH_P_ALL))
        sock.setblocking(False)
        poll.register(sock, selectors.EVENT_READ)
        stream.write(_PCAP_HEADER)
        stream.flush()
        ready.touch(exist_ok=False)
        count = 0
        end = time.monotonic() + 20
        while not stop.exists() and time.monotonic() < end:
            if not poll.select(timeout=0.2):
                continue
            try:
                size, *_ = sock.recvmsg_into([frame], 0, socket.MSG_TRUNC)
            except BlockingIOError:
                continue
            sample = frame[:min(size, SNAPLEN)]
            if matches(sample, addresses):
                now = time.time_ns() // 1000
                stream.write(struct.pack("<IIII", now // 1000000, now % 1000000, len(sample), size))
                stream.write(sample)
                count += 1
                if count >= MAX_PACKETS:
                    return 2
        return 0 if stop.exists() and count else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("interface", choices=("right0", "left0"))
    for label in ("out", "stop", "ready"):
        parser.add_argument(label, type=Path)
    args = parser.parse_args()
    raise SystemExit(capture(args.interface, args.out, args.stop, args.ready))
