"""`xgw logs` — журнал служб XGW; `--export` — архив для разбора без секретов.

Всё, что попадает в архив, проходит через masking.mask_text: UUID остаются
последними четырьмя символами, пароли, ключи и токены превращаются в «***», от
URL подписок остаётся домен, от ссылок серверов — схема.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import platform
import subprocess
import sys
import tarfile
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from . import __version__, engine, masking
from .config import Config
from .generator import validate
from .install import UNITS
from .net import cmd, nft
from .paths import Paths
from .store import Store
from .xraycore import binary

EXPORT_LINES = 5000


def journal_args(lines: int, *, follow: bool = False) -> list[str]:
    args = ["journalctl", "--no-pager", "-o", "short-iso", "-n", str(lines)]
    for unit in UNITS:
        args += ["-u", unit]
    if follow:
        args.append("-f")
    return args


def show(lines: int, follow: bool) -> int:
    """Печатает журнал как есть: секреты замаскированы ещё при записи."""
    try:
        return subprocess.call(journal_args(lines, follow=follow))
    except FileNotFoundError:
        print("ошибка: journalctl не найден — журнал ведёт systemd", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


def known_secrets(cfg: Config | None, paths: Paths) -> set[str]:
    """Секреты, которые регулярками не распознать: пароли серверов, токены, заголовки."""
    secrets: set[str] = set()
    if cfg is not None:
        secrets.update(engine.config_secrets(cfg))
    for path in (paths.xray_config_file, paths.last_good_file, paths.pending_config_file,
                 paths.generated_config_file):
        loaded = engine.read_json(path)
        if loaded is not None:
            secrets.update(masking.collect_secrets(loaded))
    for token_file in (paths.status_token_file, paths.panel_token_file):
        with contextlib.suppress(OSError):
            secrets.add(token_file.read_text(encoding="ascii").strip())
    return {secret for secret in secrets if len(secret) >= 4}


def export(
    cfg: Config | None,
    paths: Paths,
    out_path: Path,
    *,
    config_path: Path | None = None,
    runner: cmd.Runner = cmd.run,
    diag_text: Callable[[], str] | None = None,
    lines: int = EXPORT_LINES,
) -> list[str]:
    """Собирает архив; возвращает имена вложенных файлов."""
    secrets = known_secrets(cfg, paths)

    def clean(text: str) -> str:
        return masking.mask_text(text, secrets)

    def command(argv: list[str]) -> str:
        try:
            return runner(argv, timeout=60.0)
        except cmd.CommandError as exc:
            return f"# {exc}\n"

    members: dict[str, str] = {}
    members["journal.txt"] = clean(command(journal_args(lines)))
    xray_bin = validate.find_xray(None, paths)
    version = binary.installed_version(xray_bin) if xray_bin else None
    members["versions.txt"] = "\n".join([
        f"xgw {__version__}",
        "xray " + (".".join(map(str, version)) if version else "не найден"),
        f"python {platform.python_version()}",
        f"система {platform.platform()}",
        f"собрано {time.strftime('%Y-%m-%d %H:%M:%S %z')}",
    ]) + "\n"
    try:
        members["config.toml"] = clean(
            (config_path or paths.config_file).read_text(encoding="utf-8", errors="replace")
        )
    except OSError as exc:
        members["config.toml"] = f"# не прочитан: {exc}\n"
    for name, path in (("status.json", paths.status_file),):
        try:
            members[name] = clean(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    applied = engine.read_json(paths.xray_config_file)
    if applied is not None:
        masked = masking.mask_obj(_mask_secret_fields(applied), secrets)
        members["xray-config.json"] = json.dumps(masked, ensure_ascii=False, indent=2) + "\n"
    if paths.db_file.exists():
        try:
            store = Store(paths.db_file)
            try:
                members["state.json"] = clean(store.dump_state()) + "\n"
            finally:
                store.close()
        except Exception as exc:
            members["state.json"] = f"# состояние не прочитано: {exc}\n"
    members["network.txt"] = clean("".join(
        f"$ {' '.join(argv)}\n{command(argv)}\n"
        for argv in (
            ["ip", "-br", "addr"], ["ip", "rule", "show"], ["ip", "route", "show", "table", "all"],
            ["nft", "list", "table", "ip", nft.TABLE], ["nft", "list", "table", "ip6", nft.TABLE6],
            ["systemctl", "--no-pager", "status", *UNITS],
        )
    ))
    if diag_text is not None:
        try:
            members["diag.txt"] = clean(diag_text()) + "\n"
        except Exception as exc:
            members["diag.txt"] = f"# diag не выполнен: {exc}\n"

    write_archive(out_path, members.items())
    return sorted(members)


def _mask_secret_fields(obj: object) -> object:
    """Значения секретных полей конфига Xray — «***» целиком, а не только известные."""
    if isinstance(obj, dict):
        return {
            key: (masking.mask_uuid(value) if key == "id" and isinstance(value, str)
                  else "***" if key in masking.SECRET_KEYS and isinstance(value, str)
                  else _mask_secret_fields(value))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_mask_secret_fields(item) for item in obj]
    return obj


def write_archive(out_path: Path, members: Iterable[tuple[str, str]]) -> None:
    """tar.gz с правами 0600: в журнале остаются адреса серверов и имена устройств."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    fd = os.open(out_path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle, tarfile.open(fileobj=handle, mode="w:gz") as archive:
        now = time.time()
        for name, text in members:
            data = text.encode("utf-8")
            info = tarfile.TarInfo(f"xgw-logs/{name}")
            info.size = len(data)
            info.mtime = now
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(data))
