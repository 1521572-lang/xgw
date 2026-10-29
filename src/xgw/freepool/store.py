"""Хранилище бесплатного пула: /var/lib/xgw/freepool (0700, root).

    snapshots/<источник>.json      последний принятый снимок каталога (варианты, итог опроса)
    snapshots/<источник>.<n>.json  три прежних (R13); у серверов списков GitHub учётка — в
                                   самой ссылке, она в снимке, и снимок тоже 0600
    candidates.json                состояние проверок вариантов (по variant_id)

До вехи М2в (OpenVPN убран 29.10.2026) здесь были secrets.json (учётка VPNBook) и profiles/
(профили OpenVPN) — retire_openvpn удаляет их, а из снимков и проверок — варианты OpenVPN.

Снимок принимается атомарно (запись во временный файл и переименование). Итог опроса с ошибкой
(UNAVAILABLE, SCHEMA_CHANGED, RATE_LIMITED…) снимок не заменяет: остаётся прежний (last-good), а
отметка об ошибке пишется рядом (status). Секреты в журнал и состояние не попадают.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from ..paths import Paths, atomic_write_json
from .models import Backend, ProviderResult, Status, Variant

KEEP_SNAPSHOTS = 3
ACCEPTED = (Status.SUCCESS, Status.PARTIAL)
KNOWN_BACKENDS = frozenset(str(item) for item in Backend)


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
    return data


def variant_from_dict(data: dict) -> Variant | None:
    """Вариант из снимка; None — не разобрать или бэкенда больше нет (OpenVPN до М2в)."""
    if str(data.get("backend") or "") not in KNOWN_BACKENDS:
        return None
    try:
        return Variant(
            provider=data["provider"], backend=data["backend"], protocol=data["protocol"],
            host=data["host"], address=data["address"], port=int(data["port"]),
            transport=data["transport"], name=data["name"], country_hint=data["country_hint"],
            access=data.get("access", "free"),
            hints=tuple(tuple(item) for item in data.get("hints", ())),
            usage_policy=tuple(data.get("usage_policy", ())),
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

    def retire_openvpn(self) -> list[str]:
        """Остатки OpenVPN (до вехи М2в): учётка VPNBook, профили, итоги проверок туннелей
        OpenVPN. Варианты OpenVPN в снимках не читаются (variant_from_dict), а со следующим
        опросом источника уходят и из файла. Что убрано — для журнала."""
        removed: list[str] = []
        secrets = self.dir / "secrets.json"
        if secrets.exists():
            secrets.unlink()
            removed.append("учётка VPNBook")
        profiles = self.dir / "profiles"
        if profiles.is_dir():
            shutil.rmtree(profiles)
            removed.append("профили OpenVPN")
        state = self.candidates()
        kept = {key: value for key, value in state.items()
                if key.startswith("_") or value.get("backend") != "openvpn"}
        if len(kept) < len(state):
            self.save_candidates(kept)
            removed.append(f"итоги проверок OpenVPN ({len(state) - len(kept)})")
        return removed

    # --- состояние проверок -----------------------------------------------------------------

    def candidates(self) -> dict[str, dict]:
        data = _read(self.dir / "candidates.json")
        return {key: value for key, value in data.items() if isinstance(value, dict)}

    def save_candidates(self, data: dict[str, dict]) -> None:
        self._ensure()
        atomic_write_json(self.dir / "candidates.json", data, mode=0o600)
