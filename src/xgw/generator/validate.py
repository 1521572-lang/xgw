"""Проверка конфига установленным Xray: xray run -test.

Конфиг содержит секреты, поэтому временный файл создаётся с правами 0600
и удаляется сразу после проверки; вывод маскируется.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import masking
from ..paths import Paths


def find_xray(explicit: str | Path | None = None, paths: Paths | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    env_bin = os.environ.get("XGW_XRAY_BIN")
    if env_bin:
        candidates.append(Path(env_bin))
    if paths is not None:
        candidates.append(paths.xray_bin)
    for name in ("xray", "xray.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def validate_config(config: dict, xray_bin: Path | None) -> tuple[bool | None, str]:
    """True/False — вердикт xray run -test; None — Xray не найден (проверка пропущена)."""
    if xray_bin is None:
        return None, "xray не найден — проверка xray run -test пропущена"
    fd, tmp_name = tempfile.mkstemp(prefix="xgw-validate-", suffix=".json")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
        with contextlib.suppress(OSError):
            os.chmod(tmp, 0o600)
        try:
            proc = subprocess.run(
                [str(xray_bin), "run", "-test", "-c", str(tmp)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return False, "xray run -test: таймаут 60 с"
        output = masking.mask_text((proc.stdout or "") + (proc.stderr or ""))
        return proc.returncode == 0, output.strip()
    finally:
        tmp.unlink(missing_ok=True)
