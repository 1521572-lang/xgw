"""Пути файловой системы XGW.

Корень по умолчанию «/» (реальная система). В тестах и разработке корень
переопределяется переменной окружения XGW_ROOT, чтобы не трогать хост.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Paths:
        source = dict(os.environ) if env is None else env
        return cls(root=Path(source.get("XGW_ROOT", "/")))

    @property
    def etc(self) -> Path:
        return self.root / "etc" / "xgw"

    @property
    def var(self) -> Path:
        return self.root / "var" / "lib" / "xgw"

    @property
    def run(self) -> Path:
        return self.root / "run" / "xgw"

    @property
    def opt(self) -> Path:
        return self.root / "opt" / "xgw"

    @property
    def config_file(self) -> Path:
        return self.etc / "config.toml"

    @property
    def xray_config_dir(self) -> Path:
        return self.etc / "xray"

    @property
    def xray_config_file(self) -> Path:
        return self.xray_config_dir / "config.json"

    @property
    def last_good_file(self) -> Path:
        return self.var / "last-good.json"

    @property
    def cache_dir(self) -> Path:
        return self.var / "cache"

    @property
    def backup_dir(self) -> Path:
        return self.var / "backup"

    @property
    def db_file(self) -> Path:
        return self.var / "state.db"

    @property
    def xray_dir(self) -> Path:
        return self.opt / "xray"

    @property
    def xray_bin(self) -> Path:
        return self.xray_dir / ("xray.exe" if os.name == "nt" else "xray")

    def ensure(self) -> None:
        for directory in (
            self.etc,
            self.xray_config_dir,
            self.var,
            self.cache_dir,
            self.backup_dir,
            self.run,
        ):
            directory.mkdir(parents=True, exist_ok=True)
