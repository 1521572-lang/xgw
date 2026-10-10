import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"
REGEN = os.environ.get("XGW_REGEN_GOLDEN") == "1"


def golden(name: str, payload) -> object:
    """Сверяет payload с golden-файлом; при XGW_REGEN_GOLDEN=1 перезаписывает его."""
    path = GOLDEN_DIR / name
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")  # LF и на Windows
    return json.loads(path.read_text(encoding="utf-8"))
