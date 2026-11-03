"""Explicit cooperative code identity, no I/O, discovery or activation.

Digests must come from independently checked public manifests. Supplying a digest
does not attest loaded/installed code or fence uncooperating callers.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass


class IdentityRefused(Exception):
    pass


def require(value):
    if not value:
        raise IdentityRefused("CODE_IDENTITY_ARGUMENT")


@dataclass(frozen=True)
class CodeIdentity:
    source_sha256: str
    units_sha256: str
    surface_sha256: str
    protocol: int = 2

    def record(self):
        require(type(self) is CodeIdentity and type(self.protocol) is int and self.protocol == 2)
        values = (self.source_sha256, self.units_sha256, self.surface_sha256)
        require(all(type(v) is str and re.fullmatch(r"[0-9a-f]{64}", v) for v in values))
        return {
            "protocol": 2,
            "source_sha256": values[0],
            "units_sha256": values[1],
            "surface_sha256": values[2],
        }

    def digest(self):
        return hashlib.sha256(canonical(self.record())).hexdigest()


def canonical(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def valid_record(value):
    if type(value) is not dict or set(value) != {
        "protocol",
        "source_sha256",
        "units_sha256",
        "surface_sha256",
    }:
        return False
    try:
        return CodeIdentity(**value).record() == value
    except IdentityRefused:
        return False
