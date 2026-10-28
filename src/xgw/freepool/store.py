"""Хранилище бесплатного пула: /var/lib/xgw/freepool (0700, root).

    snapshots/<источник>.json      последний принятый снимок каталога (варианты, итог опроса)
    snapshots/<источник>.<n>.json  три прежних (R13)
    secrets.json (0600)            общие учётки источников (VPNBook)
                                   (у серверов списков GitHub учётка — в самой ссылке, она в
                                   снимке, и снимок тоже 0600)
    profiles/<вариант>.ovpn        профили VPNBook, скачанные кнопкой «Download» (М2а)
    candidates.json                состояние проверок вариантов (по variant_id)

Снимок принимается атомарно (запись во временный файл и переименование). Итог опроса с ошибкой
(UNAVAILABLE, SCHEMA_CHANGED, RATE_LIMITED…) снимок не заменяет: остаётся прежний (last-good), а
отметка об ошибке пишется рядом (status). Секреты в журнал и состояние не попадают.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..paths import Paths, atomic_write_json, atomic_write_text
from .models import ProviderResult, Status, Variant
from .ovpn import OvpnProfile, Remote

KEEP_SNAPSHOTS = 3
ACCEPTED = (Status.SUCCESS, Status.PARTIAL)


def root(paths: Paths) -> Path:
    return paths.var / "freepool"


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def variant_to_dict(variant: Variant) -> dict:
    data = asdict(variant)
    data["hints"] = [list(item) for item in variant.hints]
    data["extra"] = [list(item) for item in variant.extra]
    data["usage_policy"] = list(variant.usage_policy)
    if variant.profile is not None:
        profile = asdict(variant.profile)
        profile["remotes"] = [asdict(remote) for remote in variant.profile.remotes]
        profile["ciphers"] = list(variant.profile.ciphers)
        profile["managed"] = list(variant.profile.managed)
        profile["tuning"] = [list(item) for item in variant.profile.tuning]
        data["profile"] = profile
    return data


def variant_from_dict(data: dict) -> Variant | None:
    try:
        profile = data.get("profile")
        if isinstance(profile, dict):
            profile = OvpnProfile(
                remotes=tuple(Remote(**remote) for remote in profile["remotes"]),
                ciphers=tuple(profile["ciphers"]), auth=profile["auth"], ca=profile["ca"],
                cert=profile.get("cert", ""), key=profile.get("key", ""),
                tls_auth=profile.get("tls_auth", ""), tls_crypt=profile.get("tls_crypt", ""),
                key_direction=profile.get("key_direction", ""),
                needs_password=bool(profile.get("needs_password")),
                remote_cert_tls=profile.get("remote_cert_tls", ""),
                verify_x509_name=profile.get("verify_x509_name", ""),
                tls_version_min=profile.get("tls_version_min", ""),
                legacy_crypto=bool(profile.get("legacy_crypto")),
                managed=tuple(profile.get("managed", ())),
                tuning=tuple(tuple(item) for item in profile.get("tuning", ())),
                fallback_cipher=str(profile.get("fallback_cipher") or ""),
            )
        else:
            profile = None
        return Variant(
            provider=data["provider"], backend=data["backend"], protocol=data["protocol"],
            host=data["host"], address=data["address"], port=int(data["port"]),
            transport=data["transport"], name=data["name"], country_hint=data["country_hint"],
            access=data.get("access", "free"),
            hints=tuple(tuple(item) for item in data.get("hints", ())),
            needs=data.get("needs", ""), credential_scope=data.get("credential_scope", ""),
            usage_policy=tuple(data.get("usage_policy", ())), profile=profile,
            outbound=data.get("outbound"), source_url=data.get("source_url", ""),
            extra=tuple(tuple(item) for item in data.get("extra", ())),
            singbox=data.get("singbox") if isinstance(data.get("singbox"), dict) else None,
        )
    except (KeyError, TypeError, ValueError):
        return None


class PoolStore:
    def __init__(self, paths: Paths) -> None:
        self.dir = root(paths)

    def _ensure(self) -> None:
        (self.dir / "snapshots").mkdir(parents=True, exist_ok=True)
        self.dir.chmod(0o700)

    # --- снимки ---------------------------------------------------------------------------

    def snapshot_path(self, provider: str, generation: int = 0) -> Path:
        suffix = f".{generation}" if generation else ""
        return self.dir / "snapshots" / f"{provider}{suffix}.json"

    def commit(self, result: ProviderResult) -> bool:
        """Принять итог опроса: SUCCESS/PARTIAL — новый снимок (прежние — со сдвигом номеров),
        иначе — только отметка об ошибке рядом с прежним. True — снимок заменён."""
        self._ensure()
        status = {
            "status": str(result.status), "retrieved_at": result.retrieved_at,
            "detail": result.detail[:300], "rejected": result.rejected,
            "rejections": dict(list(result.rejections.items())[:20]),
        }
        current = self.snapshot_path(result.provider)
        if result.status not in ACCEPTED:
            previous = _read(current)
            previous["last_attempt"] = status
            if previous.get("variants") is not None:
                atomic_write_json(current, previous, mode=0o600)
            else:
                atomic_write_json(current, {"variants": [], "last_attempt": status}, mode=0o600)
            return False
        for generation in range(KEEP_SNAPSHOTS, 0, -1):
            older = self.snapshot_path(result.provider, generation - 1)
            if older.exists():
                older.replace(self.snapshot_path(result.provider, generation))
        snapshot = {
            **status, "complete_response": result.complete_response,
            "authoritative": result.authoritative, "last_attempt": status,
            "variants": [variant_to_dict(variant) for variant in result.variants],
        }
        atomic_write_json(current, snapshot, mode=0o600)
        if result.credentials:
            secrets = self.secrets()
            secrets.setdefault("shared", {}).update(result.credentials)
            atomic_write_json(self.dir / "secrets.json", secrets, mode=0o600)
        return True

    def snapshot(self, provider: str) -> dict:
        return _read(self.snapshot_path(provider))

    def variants(self, provider: str) -> list[Variant]:
        items = self.snapshot(provider).get("variants") or []
        return [variant for variant in map(variant_from_dict, items) if variant is not None]

    def prune(self, keep: tuple[str, ...]) -> list[str]:
        """Удалить снимки источников не из keep (убранных из XGW); их имена."""
        removed: set[str] = set()
        for path in sorted((self.dir / "snapshots").glob("*.json")):
            provider = path.name.split(".", 1)[0]
            if provider not in keep:
                path.unlink()
                removed.add(provider)
        return sorted(removed)

    # --- секреты и состояние проверок -----------------------------------------------------

    def secrets(self) -> dict:
        return _read(self.dir / "secrets.json")

    def candidates(self) -> dict[str, dict]:
        data = _read(self.dir / "candidates.json")
        return {key: value for key, value in data.items() if isinstance(value, dict)}

    def save_candidates(self, data: dict[str, dict]) -> None:
        self._ensure()
        atomic_write_json(self.dir / "candidates.json", data, mode=0o600)

    # --- профили, скачанные отдельно (VPNBook) ----------------------------------------------

    def profile(self, key: str) -> tuple[str, float]:
        """Сохранённый текст профиля и когда скачан; ("", 0) — нет."""
        path = self.dir / "profiles" / f"{key}.ovpn"
        try:
            return path.read_text(encoding="utf-8"), path.stat().st_mtime
        except OSError:
            return "", 0.0

    def save_profile(self, key: str, text: str) -> None:
        self._ensure()
        directory = self.dir / "profiles"
        directory.mkdir(mode=0o700, exist_ok=True)
        atomic_write_text(directory / f"{key}.ovpn", text, mode=0o600)
