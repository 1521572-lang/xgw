"""Read accepted TCP destinations and route tags from Xray access records."""

import ipaddress
import re
from typing import NamedTuple
from uuid import UUID

_ACCEPTED = re.compile(
    r"(?:^|[ \t])from (?:tcp:)?(?P<source>\S+) accepted (?:tcp:|//)"
    r"(?P<target>[^\s/?#@\\]+) "
    r"\[(?P<inbound>[^\s\[\]]+) (?:->|>>|==>) (?P<outbound>[^\s\[\]]+)\]"
)


class Accepted(NamedTuple):
    source: str
    target: str
    inbound: str
    outbound: str


def parse_accepted(message: str) -> Accepted | None:
    if "\n" in message or "\r" in message:
        return None
    match = _ACCEPTED.search(message)
    return Accepted(*match.groups()) if match else None


def endpoint(value: str) -> tuple[str, int]:
    host, separator, port = value.rpartition(":")
    if not separator or not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("invalid_endpoint")
    if host.startswith("[") != host.endswith("]"):
        raise ValueError("invalid_endpoint")
    address = ipaddress.ip_address(host.removeprefix("[").removesuffix("]"))
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address), int(port)


def destination(value: str) -> tuple[str, int]:
    """Access logs can represent the CONNECT destination as an IP or hostname."""
    try:
        return endpoint(value)
    except ValueError:
        host, _, port = value.rpartition(":")
        host = host.rstrip(".").lower()
        if (not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,252}", host)
                or not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535):
            raise ValueError("invalid_destination") from None
        return host, int(port)


def journal_identity(epoch: str) -> tuple[str, str]:
    boot, pid, _ = epoch.split(":")
    if not re.fullmatch(r"[1-9][0-9]{0,15}", pid):
        raise ValueError("invalid_xray_epoch")
    return UUID(boot).hex, pid
