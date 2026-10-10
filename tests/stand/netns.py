"""Сетевые пространства имён стенда (Linux, root).

Три пространства, связанные veth-парами, — шлюз с двумя картами, «интернет»
и устройство в LAN (раздел 9 ТЗ):

    inet (5.5.5.1) ──eth0══wan0── gw (5.5.5.2 / 192.168.50.1) ──lan0══eth0── lan (192.168.50.100)

Сеть хоста не затрагивается: оба конца каждой veth-пары создаются сразу внутри
пространств имён, в корневом ничего не появляется. Адрес «интернета» намеренно
не из частных диапазонов — иначе правило geoip:private отправляло бы трафик
стенда напрямую, мимо балансировщика.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

INET_IP = "5.5.5.1"
GW_WAN_IP = "5.5.5.2"
GW_LAN_IP = "192.168.50.1"
LAN_IP = "192.168.50.100"


def available() -> bool:
    """Стенд в пространствах имён возможен только на Linux под root и с iproute2."""
    return (
        sys.platform.startswith("linux")
        and hasattr(os, "geteuid")
        and os.geteuid() == 0
        and shutil.which("ip") is not None
    )


class Topology:
    def __init__(self, suffix: str | None = None) -> None:
        suffix = suffix or str(os.getpid())
        self.inet = f"xgw-inet-{suffix}"
        self.gw = f"xgw-gw-{suffix}"
        self.lan = f"xgw-lan-{suffix}"
        self._created: list[str] = []

    def _ip(self, *args: str) -> None:
        subprocess.run(["ip", *args], check=True, capture_output=True, text=True, timeout=15)

    def create(self) -> None:
        try:
            for namespace in (self.inet, self.gw, self.lan):
                self._ip("netns", "add", namespace)
                self._created.append(namespace)
                self._ip("-n", namespace, "link", "set", "lo", "up")
            self._link(self.gw, "wan0", f"{GW_WAN_IP}/24", self.inet, "eth0", f"{INET_IP}/24")
            self._link(self.gw, "lan0", f"{GW_LAN_IP}/24", self.lan, "eth0", f"{LAN_IP}/24")
            self._ip("-n", self.gw, "route", "add", "default", "via", INET_IP)
            self._ip("-n", self.lan, "route", "add", "default", "via", GW_LAN_IP)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            self.destroy()
            raise

    def _link(self, ns_a: str, dev_a: str, addr_a: str, ns_b: str, dev_b: str, addr_b: str) -> None:
        self._ip("link", "add", dev_a, "netns", ns_a, "type", "veth",
                 "peer", "name", dev_b, "netns", ns_b)
        for namespace, device, address in ((ns_a, dev_a, addr_a), (ns_b, dev_b, addr_b)):
            self._ip("-n", namespace, "addr", "add", address, "dev", device)
            self._ip("-n", namespace, "link", "set", device, "up")

    def destroy(self) -> None:
        """Удаление пространства имён убирает и его интерфейсы (veth — вместе с парой)."""
        for namespace in reversed(self._created):
            subprocess.run(["ip", "netns", "del", namespace], capture_output=True, timeout=15)
        self._created.clear()

    def prefix(self, namespace: str) -> list[str]:
        """Префикс команды, чтобы выполнить её внутри пространства имён."""
        return ["ip", "netns", "exec", namespace]
