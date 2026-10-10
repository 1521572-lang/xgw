"""Применение нового конфига Xray без разрыва соединений (раздел 6.7).

Xray не умеет перечитывать конфиг, поэтому:
- изменились только outbounds / probe-inbounds / routing → API:
  adi/ado → adrules → rmo/rmi, соединения не рвутся;
- изменились dns / burstObservatory / policy / api / основные inbounds →
  полный перезапуск: сразу в состояниях ALL_DEAD и XRAY_DOWN (urgent),
  иначе в restart_window или по force_now (xgw apply --now);
- ошибка любого вызова API → полный перезапуск с новым конфигом;
- Xray не поднялся за 15 с после перезапуска → откат на last-good.

Все операции — под файловой блокировкой; конфиг пишется атомарно.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import log
from ..generator.diff import apply_plan, diff_configs
from ..generator.validate import find_xray, validate_config
from ..paths import Paths
from ..xraycore.api import ApiClient, ApiError
from ..xraycore.service import XrayService, XrayServiceError

RESTART_WAIT_SECONDS = 15.0


@dataclass
class ApplyOutcome:
    mode: str  # api | restart | restart_deferred | unchanged | rejected | rollback
    ops: list[str] = field(default_factory=list)
    detail: str = ""


def in_restart_window(window: str, now: datetime.time) -> bool:
    """«04:00-05:00» — окно планового перезапуска (учитывает переход через полночь)."""
    try:
        start_s, end_s = window.split("-")
        start = datetime.time.fromisoformat(start_s.strip())
        end = datetime.time.fromisoformat(end_s.strip())
    except ValueError:
        return True  # битое окно считаем «всегда разрешено» + предупреждение в логе
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end  # окно через полночь


class Applier:
    def __init__(
        self,
        cfg,
        paths: Paths,
        api: ApiClient,
        service: XrayService,
        *,
        xray_bin: Path | None = None,
        logger=None,
        now_fn=lambda: datetime.datetime.now().time(),
        wait_seconds: float = RESTART_WAIT_SECONDS,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.api = api
        self.service = service
        self.xray_bin = xray_bin if xray_bin is not None else find_xray(None, paths)
        self.log = logger or log.get_logger("apply")
        self.now_fn = now_fn
        self.wait_seconds = wait_seconds

    def apply(
        self, new_config: dict, *, urgent: bool = False, force_now: bool = False
    ) -> ApplyOutcome:
        ok, output = validate_config(new_config, self.xray_bin)
        if ok is False:
            return ApplyOutcome("rejected", detail=output)
        if ok is None:
            self.log.warning("xray не найден — конфиг не проверен xray run -test")

        current = self._read_current()
        if current == new_config:
            return ApplyOutcome("unchanged")

        if current is None:
            self._promote(new_config)
            return self._restart(new_config, urgent=True, reason="первый запуск")

        diff = diff_configs(current, new_config)
        if not diff.changed:
            return ApplyOutcome("unchanged")

        if diff.plan is not None:
            try:
                ops = apply_plan(self.api, diff.plan)
                self._promote(new_config)
                return ApplyOutcome("api", ops=ops)
            except ApiError as exc:
                self.log.error("ошибка API (%s) — полный перезапуск", exc)
                self._promote(new_config)
                return self._restart(new_config, urgent=True, reason="ошибка API")

        if urgent or force_now:
            self._promote(new_config)
            return self._restart(new_config, urgent=True, reason="срочное применение")
        if in_restart_window(self.cfg.apply.restart_window, self.now_fn()):
            self._promote(new_config)
            return self._restart(new_config, reason="окно перезапуска")
        self._write_pending(new_config)
        return ApplyOutcome(
            "restart_deferred",
            ops=diff.restart_reasons,
            detail="ожидание окна " + self.cfg.apply.restart_window,
        )

    # --- внутреннее ------------------------------------------------------------

    def _restart(self, config: dict, *, urgent: bool, reason: str) -> ApplyOutcome:
        try:
            self.service.restart()
        except XrayServiceError as exc:
            return self._rollback(reason=f"перезапуск не удался: {exc}")
        deadline = time.monotonic() + self.wait_seconds
        while time.monotonic() < deadline:
            try:
                self.api.balancer_info()
                return ApplyOutcome("restart", ops=[f"restart ({reason})"])
            except ApiError:
                time.sleep(0.5)
        return self._rollback(reason="Xray не поднялся за 15 с")

    def _rollback(self, *, reason: str) -> ApplyOutcome:
        last_good = self.paths.last_good_file
        if not last_good.exists():
            return ApplyOutcome("rollback", detail=f"{reason}; last-good отсутствует")
        try:
            good = json.loads(last_good.read_text(encoding="utf-8"))
            self.paths.xray_config_file.write_text(
                json.dumps(good, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            self.service.restart()
        except (OSError, json.JSONDecodeError, XrayServiceError) as exc:
            self.log.error("откат на last-good не удался: %s", exc)
        return ApplyOutcome("rollback", detail=reason)

    def _read_current(self) -> dict | None:
        path = self.paths.xray_config_file
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.log.error("текущий конфиг бит — применяюсь как при первом запуске")
            return None

    def _promote(self, new_config: dict) -> None:
        """Новый конфиг становится текущим, предыдущий — last-good."""
        path = self.paths.xray_config_file
        if path.exists():
            last_good = self.paths.last_good_file
            last_good.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, last_good)
        self._atomic_write(path, new_config)

    def _write_pending(self, new_config: dict) -> None:
        self._atomic_write(self.paths.xray_config_dir / "config.pending.json", new_config)

    def _atomic_write(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(tmp, 0o640)
        os.replace(tmp, path)
