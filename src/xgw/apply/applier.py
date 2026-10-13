"""Применение нового конфига Xray без разрыва соединений (раздел 6.7).

Xray не умеет перечитывать конфиг, поэтому:
- изменились только outbounds / probe-inbounds / routing → API:
  adi/ado → adrules → rmo/rmi, соединения не рвутся;
- изменились dns / burstObservatory / policy / api / основные inbounds →
  полный перезапуск: сразу в состояниях ALL_DEAD и XRAY_DOWN (urgent),
  иначе в restart_window или по force_now (xgw apply --now);
  изменение inbound'а перехвата (tproxy-in) — всегда сразу: пока Xray не
  перезапущен с ним, включать перехват нельзя (см. net/capture.py);
- ошибка любого вызова API → полный перезапуск с новым конфигом по тем же
  правилам; до перезапуска ядро считается изменённым частично, и через API
  больше ничего не применяется;
- Xray не поднялся за 15 с после перезапуска → откат на last-good.

Все операции — под файловой блокировкой; файлы пишутся атомарно.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import log
from ..generator.builder import BALANCER_TAG
from ..generator.diff import apply_plan, diff_configs
from ..generator.validate import find_xray, validate_config
from ..net import cmd, tun
from ..net.capture import TPROXY_TAG
from ..paths import Paths, atomic_write_json, atomic_write_text, file_lock
from ..xraycore.api import ApiClient, ApiError
from ..xraycore.service import XrayService, XrayServiceError

RESTART_WAIT_SECONDS = 15.0
Validator = Callable[[dict], "tuple[bool | None, str]"]


@dataclass
class ApplyOutcome:
    # api | restart | restart_deferred | unchanged | rejected | rollback | failed
    mode: str
    ops: list[str] = field(default_factory=list)
    detail: str = ""


def in_restart_window(window: str, now: datetime.time) -> bool:
    """«04:00-05:00» — окно планового перезапуска (учитывает переход через полночь).

    Формат проверяет config._validate; сюда битое окно попасть не должно, а если
    попало — перезапуск не откладываем навсегда.
    """
    try:
        start_s, end_s = window.split("-")
        start = datetime.time.fromisoformat(start_s.strip())
        end = datetime.time.fromisoformat(end_s.strip())
    except ValueError:
        return True
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end  # окно через полночь


def tproxy_inbounds(config: dict) -> list[tuple]:
    """Inbound'ы перехвата в конфиге — то, от чего зависят правила nftables.

    Пока применённый конфиг и правила расходятся (перехват включён, а Xray не
    слушает tproxy_port), трафик уходит в никуда: при fail_mode = "closed" машина
    остаётся без интернета. Поэтому такое расхождение нельзя откладывать до окна
    перезапуска — его применяют сразу.
    """
    inbounds = config.get("inbounds")
    if not isinstance(inbounds, list):
        return []
    result = []
    for inbound in inbounds:
        if not isinstance(inbound, dict):
            continue
        tag = str(inbound.get("tag", ""))
        if tag == TPROXY_TAG or tag.startswith(TPROXY_TAG + "6"):
            result.append(
                (tag, inbound.get("listen"), inbound.get("port"), inbound.get("protocol"))
            )
    return sorted(result)


class Applier:
    def __init__(
        self,
        cfg,
        paths: Paths,
        api: ApiClient,
        service: XrayService,
        *,
        xray_bin: Path | None = None,
        validator: Validator | None = None,
        logger=None,
        now_fn=lambda: datetime.datetime.now().time(),
        wait_seconds: float = RESTART_WAIT_SECONDS,
        runner: cmd.Runner = cmd.run,
    ) -> None:
        self.runner = runner
        self.cfg = cfg
        self.paths = paths
        self.api = api
        self.service = service
        if validator is None:
            binary = xray_bin if xray_bin is not None else find_xray(None, paths)
            validator = lambda config: validate_config(config, binary)  # noqa: E731
        self.validator = validator
        self.log = logger or log.get_logger("apply")
        self.now_fn = now_fn
        self.wait_seconds = wait_seconds

    def apply(
        self, new_config: dict, *, urgent: bool = False, force_now: bool = False
    ) -> ApplyOutcome:
        ok, output = self.validator(new_config)
        if not ok:
            # Без проверки xray run -test конфиг не применяется: Xray продолжает
            # работать на последнем рабочем.
            return ApplyOutcome("rejected", detail=output)
        with file_lock(self.paths.lock_file):
            return self._apply_locked(new_config, restart_now=urgent or force_now)

    def rollback(self, reason: str) -> ApplyOutcome:
        """Откат на last-good по решению watchdog: Xray не поднимается с текущим
        конфигом. Если last-good нет или он совпадает с текущим — откатывать нечего."""
        with file_lock(self.paths.lock_file):
            try:
                good = json.loads(self.paths.last_good_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return ApplyOutcome("unchanged", detail="last-good отсутствует")
            if good == self._read_current():
                return ApplyOutcome("unchanged", detail="last-good совпадает с текущим конфигом")
            return self._rollback(reason=reason)

    # --- внутреннее ------------------------------------------------------------

    def _apply_locked(self, new_config: dict, *, restart_now: bool) -> ApplyOutcome:
        current = self._read_current()
        if current is None:
            return self._restart(new_config, reason="первый запуск")
        if current == new_config:
            self._clear_pending()
            return ApplyOutcome("unchanged")

        diff = diff_configs(current, new_config)
        reasons = list(diff.restart_reasons)
        if diff.plan is not None and self.paths.api_dirty_file.exists():
            reasons.append("ядро изменено через API частично")

        if tproxy_inbounds(current) != tproxy_inbounds(new_config):
            # Inbound перехвата меняется: откладывать нельзя. Правила nftables
            # загружаются по новому конфигу сразу, и если ядро останется на старом
            # (без tproxy-in), перехваченный трафик уйдёт в никуда.
            if "изменение inbound перехвата" not in reasons:
                reasons.append("изменение inbound перехвата")
            restart_now = True

        if not reasons and diff.plan is not None:
            try:
                ops = apply_plan(self.api, diff.plan)
            except ApiError as exc:
                self.log.error("ошибка API (%s) — нужен полный перезапуск", exc)
                self._mark_dirty()
                reasons.append("ошибка API")
            else:
                self._promote(new_config)
                return ApplyOutcome("api", ops=ops + diff.deferred)

        if restart_now:
            return self._restart(new_config, reason="срочное применение: " + ", ".join(reasons))
        if in_restart_window(self.cfg.apply.restart_window, self.now_fn()):
            return self._restart(new_config, reason="окно перезапуска: " + ", ".join(reasons))
        atomic_write_json(self.paths.pending_config_file, new_config)
        return ApplyOutcome(
            "restart_deferred",
            ops=reasons,
            detail="ожидание окна " + self.cfg.apply.restart_window,
        )

    def _restart(self, config: dict, *, reason: str) -> ApplyOutcome:
        self._promote(config)
        error = self._restart_and_wait()
        if error is None:
            return ApplyOutcome("restart", ops=[f"restart ({reason})"])
        return self._rollback(reason=error)

    def _prepare_tun(self) -> None:
        """Конфиг с inbound `tun`: интерфейс должен появиться раньше Xray и быть
        постоянным (создан XGW). Созданный самим Xray, он исчезает вместе с ним, а с ним
        и маршрут в него: после перезапуска Xray трафик машины шёл бы в чёрную дыру,
        пока демон не вернёт маршрут."""
        config = self._read_current()
        name = tun.inbound_name(config) if config else None
        if name is None:
            return
        try:
            tun.ensure(name, self.runner)
        except (cmd.CommandError, OSError) as exc:
            self.log.warning(
                "TUN-интерфейс %s не подготовлен (Xray создаст свой, не постоянный): %s", name, exc
            )

    def _restart_and_wait(self) -> str | None:
        """Перезапускает Xray и ждёт ответа API. None — поднялся, иначе причина."""
        self._prepare_tun()
        try:
            self.service.restart()
        except XrayServiceError as exc:
            return f"перезапуск не удался: {exc}"
        # Ядро запущено заново с конфигом с диска — следов частичного применения нет.
        self._clear_dirty()
        deadline = time.monotonic() + self.wait_seconds
        while True:
            try:
                # Балансировщик называем явно: без тега `xray api bi` отвечает ошибкой.
                self.api.balancer_info(BALANCER_TAG)
                return None
            except ApiError:
                if time.monotonic() >= deadline:
                    return f"Xray не поднялся за {self.wait_seconds:.0f} с"
                time.sleep(0.5)

    def _rollback(self, *, reason: str) -> ApplyOutcome:
        last_good = self.paths.last_good_file
        try:
            good_text = last_good.read_text(encoding="utf-8")
            json.loads(good_text)
        except (OSError, json.JSONDecodeError) as exc:
            self.log.error("%s; откат невозможен: last-good не читается (%s)", reason, exc)
            return ApplyOutcome("failed", detail=f"{reason}; last-good отсутствует или бит")
        atomic_write_text(self.paths.xray_config_file, good_text)
        error = self._restart_and_wait()
        if error is not None:
            self.log.error("%s; откат на last-good не помог: %s", reason, error)
            return ApplyOutcome("failed", detail=f"{reason}; после отката: {error}")
        return ApplyOutcome("rollback", detail=reason)

    def _read_current(self) -> dict | None:
        path = self.paths.xray_config_file
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            self.log.error("текущий конфиг не читается (%s) — применяю как первый запуск", exc)
            return None
        return loaded if isinstance(loaded, dict) else None

    def _promote(self, new_config: dict) -> None:
        """Новый конфиг становится текущим, предыдущий — last-good.

        Текущий копируется, а не переносится: между двумя записями конфиг Xray
        не должен пропадать с диска (служба может перезапуститься в любой момент).
        """
        path = self.paths.xray_config_file
        with contextlib.suppress(FileNotFoundError):
            atomic_write_text(self.paths.last_good_file, path.read_text(encoding="utf-8"))
        atomic_write_json(path, new_config)
        self._clear_pending()

    def _clear_pending(self) -> None:
        self.paths.pending_config_file.unlink(missing_ok=True)

    def _mark_dirty(self) -> None:
        atomic_write_text(self.paths.api_dirty_file, "1\n", mode=0o644)

    def _clear_dirty(self) -> None:
        self.paths.api_dirty_file.unlink(missing_ok=True)
