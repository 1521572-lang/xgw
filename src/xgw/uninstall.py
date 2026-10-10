"""Удаление XGW: `sudo xgw uninstall` (раздел 6.9).

Возвращает систему в исходное состояние по журналу установки: службы, таблицы
nftables и правила маршрутизации, dnsmasq, профили NetworkManager, sysctl, сон,
правила ufw. Каждый шаг выполняется независимо от остальных: сбой одного не
мешает вернуть остальное, а журнал при сбое остаётся — удаление можно повторить.
"""

from __future__ import annotations

import contextlib
import shutil
from collections.abc import Callable
from pathlib import Path

from . import log
from .config import Config
from .install import UNITS, XRAY_USER, Journal
from .net import cmd, dnsmasq, nm, sleep, sysctl, ufw
from .net.capture import Capture
from .paths import Paths

# Что остаётся в журнале после отката неудачной установки: это установка не
# откатывает, а при повторном запуске должна помнить, что было до неё.
_KEPT_AFTER_ROLLBACK = ("packages", "user_created", "dnsmasq")


class Uninstaller:
    def __init__(
        self,
        cfg: Config | None,
        paths: Paths,
        *,
        runner: cmd.Runner = cmd.run,
        out: Callable[[str], None] = print,
        proc_sys: Path = sysctl.PROC_SYS,
        logger=None,
    ) -> None:
        self.paths = paths
        self.runner = runner
        self.out = out
        self.proc_sys = proc_sys
        self.log = logger or log.get_logger("uninstall")
        self.journal = Journal(paths.journal_file)
        self.cfg = cfg if cfg is not None else self._fallback_config()
        self.failed: list[str] = []

    def _fallback_config(self) -> Config:
        """config.toml не читается — метки и таблица берутся из журнала установки."""
        cfg = Config()
        saved = self.journal.get("capture") or {}
        for name in ("mark_proxy", "route_table"):
            if isinstance(saved.get(name), int):
                setattr(cfg.capture, name, saved[name])
        return cfg

    def run(self, *, keep_files: bool = False, purge: bool = False) -> int:
        """keep_files — откат неудачной установки: код, конфиг и состояние остаются."""
        steps: list[tuple[str, Callable[[], str | None]]] = [
            ("службы", self._stop_units),
            ("правила сети", self._rules),
            ("dnsmasq", self._dnsmasq),
            ("NetworkManager", self._nm),
            ("sysctl", self._sysctl),
            ("сон", self._sleep),
            ("ufw", self._ufw),
            ("файлы служб", self._unit_files),
            ("ярлык панели", self._launcher),
        ]
        if not keep_files:
            steps.append(("пользователь", self._user))
        for name, step in steps:
            try:
                done = step()
            except Exception as exc:  # шаги независимы: сбой одного не мешает остальным
                self.failed.append(name)
                self.log.error("удаление, шаг «%s»: %s", name, exc)
                self.out(f"  ✗ {name}: {exc}")
                continue
            if done:
                self.out(f"  ✓ {done}")
        if keep_files:
            self._trim_journal()
        elif not self.failed:
            self._files(purge)
        return self._report(keep_files, purge)

    def _warn(self, warnings: list[str]) -> None:
        for warning in warnings:
            self.out(f"  ! {warning}")

    # --- шаги -------------------------------------------------------------------

    def _stop_units(self) -> str | None:
        present = [unit for unit in UNITS if (self.paths.systemd_dir / unit).exists()]
        if not present:
            return None
        # Демон первым: иначе он успел бы вернуть правила и перезапустить Xray.
        for unit in reversed(UNITS):
            self.runner(["systemctl", "disable", "--now", unit], timeout=90.0, check=False)
        return "службы xgw, xgw-xray и xgw-net остановлены"

    def _rules(self) -> str | None:
        Capture(
            self.cfg, self.paths, runner=self.runner, logger=self.log, proc_sys=self.proc_sys
        ).down()
        return "таблицы nftables, ip rule и маршрут убраны"

    def _dnsmasq(self) -> str | None:
        conf = dnsmasq.conf_path(self.paths)
        record = self.journal.get("dnsmasq")
        if not conf.exists() and record is None:
            return None
        conf.unlink(missing_ok=True)
        if record is None:
            return f"{conf} удалён"
        if record.get("active"):
            # Работал и до XGW — пусть работает дальше, уже без нашего файла.
            self.runner(["systemctl", "restart", dnsmasq.UNIT], timeout=60.0, check=False)
            return "dnsmasq перезапущен без настроек XGW"
        self.runner(["systemctl", "stop", dnsmasq.UNIT], timeout=60.0, check=False)
        if not record.get("enabled"):
            self.runner(["systemctl", "disable", dnsmasq.UNIT], timeout=60.0, check=False)
        return "dnsmasq остановлен, его конфиг XGW удалён"

    def _nm(self) -> str | None:
        lan_record = self.journal.get("nm_lan")
        wan_record = self.journal.get("nm_wan")
        if not lan_record and not wan_record:
            return None
        manager = nm.Nm(self.runner)
        if not manager.running():
            raise cmd.CommandError(
                "NetworkManager не запущен — профили не возвращены; запустите его и "
                "повторите удаление"
            )
        done: list[str] = []
        if lan_record:
            self._warn(nm.restore_lan(manager, lan_record))
            done.append(f"профиль {nm.PROFILE} удалён, прежние профили возвращены")
        if wan_record:
            self._warn(nm.restore_wan(manager, wan_record))
            done.append(f"IPv6 в профиле WAN — снова {wan_record.get('ipv6_method', 'auto')}")
        return "; ".join(done)

    def _sysctl(self) -> str | None:
        previous = self.journal.get("sysctl")
        if previous is None and not self.paths.sysctl_file.exists():
            return None
        sysctl.restore(previous or {}, self.paths, self.proc_sys)
        return "sysctl возвращён"

    def _sleep(self) -> str | None:
        targets = self.journal.get("sleep") or []
        if not targets:
            return None
        sleep.unmask(list(targets), self.runner)
        return "сон размаскирован"

    def _ufw(self) -> str | None:
        rules = self.journal.get("ufw") or []
        before = bool(self.journal.get("ufw_before"))
        if not rules and not before:
            return None
        self._warn(ufw.remove([list(rule) for rule in rules], self.runner))
        if before:
            ufw.remove_tproxy_rule(ufw.before_rules(self.paths.root), self.runner)
        return "правила ufw убраны"

    def _unit_files(self) -> str | None:
        removed = False
        for unit in UNITS:
            path = self.paths.systemd_dir / unit
            if path.exists():
                path.unlink()
                removed = True
        if not removed:
            return None
        self.runner(["systemctl", "daemon-reload"], timeout=60.0, check=False)
        return "файлы служб удалены"

    def _launcher(self) -> str | None:
        path = self.paths.desktop_file
        if not path.exists():
            return None
        path.unlink()
        if self.journal.get("launcher_dir"):
            with contextlib.suppress(OSError):
                path.parent.rmdir()  # только пустой: чужие ярлыки не трогаются
        return "ярлык панели удалён"

    def _user(self) -> str | None:
        if not self.journal.get("user_created"):
            return None
        self.runner(["userdel", XRAY_USER], timeout=30.0)
        return f"пользователь {XRAY_USER} удалён"

    # --- файлы и итог -----------------------------------------------------------

    def _trim_journal(self) -> None:
        kept = {key: self.journal.data[key] for key in _KEPT_AFTER_ROLLBACK if key in self.journal}
        self.journal.data = kept
        with contextlib.suppress(OSError):
            self.journal.save()

    def _files(self, purge: bool) -> None:
        """Последний шаг: удаляется и код, из которого идёт выполнение."""
        targets = [self.paths.opt, self.paths.var, self.paths.run, self.paths.xray_config_dir]
        if purge:
            targets.append(self.paths.etc)
        self.paths.launcher.unlink(missing_ok=True)
        for target in targets:
            shutil.rmtree(target, ignore_errors=True)
        self.out("  ✓ файлы XGW удалены")

    def _report(self, keep_files: bool, purge: bool) -> int:
        packages = self.journal.get("packages") or []
        if self.failed:
            self.out(
                "Не всё удалось вернуть: " + ", ".join(self.failed) + ". Журнал установки "
                f"сохранён ({self.paths.journal_file}) — исправьте причину и повторите "
                "sudo xgw uninstall."
            )
            return 1
        if keep_files:
            self.out("Сеть возвращена в состояние до установки.")
            return 0
        self.out("XGW удалён, сеть возвращена в состояние до установки.")
        if not purge and self.paths.config_file.exists():
            self.out(
                f"Конфиг оставлен: {self.paths.config_file} (в нём ваша подписка); подписки, "
                "добавленные в панели, — в panel.json рядом. Убрать и их: --purge."
            )
        if packages:
            self.out(
                f"Пакеты, поставленные при установке, оставлены: {', '.join(packages)} "
                f"(убрать: sudo apt remove {' '.join(packages)})."
            )
        return 0
