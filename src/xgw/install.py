"""Установка XGW на машину: `sudo xgw install` (раздел 6.9).

Порядок: сначала всё, что не трогает сеть (пакеты, пользователь xray, код, Xray),
затем — после показа плана и подтверждения — сеть: sysctl, профиль NetworkManager,
сон, ufw, dnsmasq, службы, первый запуск Xray и правила перехвата.

Каждое изменение записывается в журнал (/var/lib/xgw/backup/install.json) вместе
с тем, что было до него: по журналу `xgw uninstall` возвращает систему в исходное
состояние. Установку можно повторять — она доводит систему до нужного вида, а
исходное состояние в журнале не перезаписывает.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import pwd
import re
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import cores, desktop, engine, fetch, log, managed, tray
from .config import SINGBOX_VERSION, XRAY_VERSION, Config, retire_obsolete
from .generator import singbox as singboxing
from .generator.builder import BALANCER_TAG
from .net import cmd, dnsmasq, lan, nm, sleep, sysctl, ufw
from .net.capture import Capture, CaptureError
from .paths import Paths, atomic_write_json, atomic_write_text
from .sbcore import binary as sbbinary
from .watch import panel, status_page
from .watch.status import join_ru
from .xraycore import binary
from .xraycore.api import ApiError
from .xraycore.service import XrayServiceError

# Корень дистрибутива: репозиторий при запуске из исходников, /opt/xgw после установки.
SOURCE_ROOT = Path(__file__).resolve().parents[2]
SINGBOX_UNIT = "xgw-singbox.service"
UNITS = ("xgw-net.service", "xgw-xray.service", SINGBOX_UNIT, "xgw.service")
# Все файлы служб XGW: и DHCP для сети LAN (свой dnsmasq) — её включают, только когда
# LAN настроен, — и обновление ядер из панели (cores.UNIT): её не включают вовсе, она
# работает только по заданию демона. Порядок — порядок запуска; останавливаются в обратном.
UNIT_FILES = (
    "xgw-net.service", "xgw-xray.service", SINGBOX_UNIT, dnsmasq.UNIT, "xgw.service", cores.UNIT,
)
XRAY_USER = "xray"
XRAY_WAIT = 20.0  # сколько ждать ответа API после первого запуска Xray
# Сколько systemd ждёт остановки демона (TimeoutStopSec в packaging/xgw.service), и сколько
# ждут его перезапуска установка и удаление: дольше, с запасом на запуск. Демон, занятый
# шагом, останавливается не мгновенно, и медленная, но нормальная остановка не должна
# выглядеть как сбой (отчёт 0.1.15, Д2: 79 с при прежнем ожидании 60 с).
DAEMON_STOP_TIMEOUT = 90.0
DAEMON_STOP_WAIT = DAEMON_STOP_TIMEOUT + 30.0
EXAMPLE_URL = "example.com/sub/TOKEN"  # подписка из config.example.toml

LAUNCHER = '''#!/usr/bin/python3 -I
"""XGW. Ключ -I: ни текущий каталог, ни переменные PYTHON* не влияют на поиск модулей."""
import sys

sys.path.insert(0, "{lib}")
from xgw.cli import main  # noqa: E402

raise SystemExit(main())
'''


DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Version=1.0
Name=XGW
GenericName=VPN gateway
GenericName[ru]=VPN-шлюз
Comment=Control panel of the XGW gateway
Comment[ru]=Панель управления шлюзом XGW
Exec={launcher} tray --open {url}
Icon={icon}
Terminal=false
Categories=Network;
Keywords=vpn;xray;proxy;
StartupNotify=false
Actions=login;

[Desktop Action login]
Name=Sign in again
Name[ru]=Войти заново
Exec={launcher} panel --login
"""

_DEVICE_STATES = {
    "connected": "подключена",
    "disconnected": "кабель подключён, сеть не настроена",
    "unavailable": "кабель не подключён",
    "unmanaged": "NetworkManager ею не управляет",
}


class InstallError(Exception):
    """Установка остановлена; сообщение — что случилось и что делать."""


class Journal:
    """Что установка изменила в системе и что было до неё."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict = {}
        with contextlib.suppress(OSError, json.JSONDecodeError):
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data = loaded

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value
        self.save()

    def setdefault(self, key: str, value):
        """Исходное состояние запоминается один раз — повторная установка его не трогает."""
        if key not in self.data:
            self.set(key, value)
        return self.data[key]

    def discard(self, key: str) -> None:
        if key in self.data:
            del self.data[key]
            self.save()

    def extend(self, key: str, items: Sequence) -> None:
        merged = list(self.data.get(key, []))
        merged.extend(item for item in items if item not in merged)
        self.set(key, merged)

    def save(self) -> None:
        atomic_write_json(self.path, self.data, mode=0o600)


def default_ask(question: str) -> bool:
    try:
        answer = input(f"{question} [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes", "д", "да")


def lan_candidates(runner: cmd.Runner = cmd.run) -> tuple[list[nm.Device], str]:
    """Проводные карты, к которым можно подключить роутер, и интерфейс выхода в интернет."""
    wan = lan.default_route_interface(runner)
    manager = nm.Nm(runner)
    try:
        devices = manager.devices() if manager.running() else {}
    except cmd.CommandError:
        devices = {}
    found = [
        device for device in devices.values()
        if device.type == "ethernet" and device.name != wan and lan.valid_interface(device.name)
    ]
    return found, wan


def choose_lan(
    runner: cmd.Runner = cmd.run,
    *,
    read: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> str:
    """Спрашивает, к какой сетевой карте подключён Wi-Fi-роутер.

    Пустой ответ — роутера нет: XGW защищает только эту машину.
    """
    candidates, wan = lan_candidates(runner)
    if not candidates:
        out("Второй проводной сетевой карты нет — XGW будет защищать только эту машину.")
        return ""
    through = f" (интернет идёт через {wan})" if wan else ""
    out(f"Сетевые карты, к которым можно подключить Wi-Fi-роутер{through}:")
    for number, device in enumerate(candidates, 1):
        out(f"  {number}) {device.name} — {_DEVICE_STATES.get(device.state, device.state)}")
    names = [device.name for device in candidates]
    while True:
        try:
            answer = read("К какой подключён роутер? Номер, или Enter — роутера нет: ").strip()
        except EOFError:
            return ""
        if not answer:
            return ""
        if answer.isdigit() and 1 <= int(answer) <= len(names):
            return names[int(answer) - 1]
        if answer in names:
            return answer
        out("Введите номер из списка или просто нажмите Enter.")


def set_lan_if(config_path: Path, name: str) -> bool:
    """Вписывает network.lan_if в только что созданный config.toml.

    Меняется единственная строка `lan_if = ""` из примера; если её нет или их
    несколько, файл не трогается — тогда имя карты вписывает человек.
    """
    if not lan.valid_interface(name):
        return False
    text = config_path.read_text(encoding="utf-8")
    changed, count = re.subn(r'(?m)^lan_if[ \t]*=[ \t]*""[ \t]*$', f'lan_if = "{name}"', text)
    if count != 1:
        return False
    atomic_write_text(config_path, changed, mode=0o600)
    return True


@dataclass
class Facts:
    """Что установка узнала о машине до того, как что-либо менять."""

    lan_if: str = ""
    wan_if: str = ""
    packages: list[str] = field(default_factory=list)  # чего не хватает
    user_exists: bool = False
    xray_version: tuple[int, int, int] | None = None
    singbox_version: tuple[int, int, int] | None = None
    nm_running: bool = False
    lan_profiles: list[str] = field(default_factory=list)  # профили, которые будут отключены
    ufw_active: bool = False


def _has_qt() -> bool:
    """Есть ли у системного Python графический фреймворк значка (PyQt6 или PyQt5)."""
    return any(importlib.util.find_spec(name) is not None for name in ("PyQt6", "PyQt5"))


def _lock_down(directory: Path) -> None:
    """Каталоги 0755, файлы 0644 — без права записи для группы и остальных."""
    for path in (directory, *directory.rglob("*")):
        with contextlib.suppress(OSError):
            if path.is_symlink():
                continue
            os.chmod(path, 0o755 if path.is_dir() else 0o644)


class Installer:
    def __init__(
        self,
        cfg: Config,
        paths: Paths,
        *,
        runner: cmd.Runner = cmd.run,
        logger=None,
        out: Callable[[str], None] = print,
        ask: Callable[[str], bool] = default_ask,
        source_root: Path = SOURCE_ROOT,
        proc_sys: Path = sysctl.PROC_SYS,
        download=binary.download_release,
        download_singbox=sbbinary.download_release,
        checks: Callable[[], list] | None = None,
        first_apply: Callable[[], bool] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        chown: Callable[..., None] = shutil.chown,
        open_panel: Callable[[], str] | None = None,
        has_qt: Callable[[], bool] | None = None,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.runner = runner
        self.log = logger or log.get_logger("install")
        self.out = out
        self.ask = ask
        self.source_root = source_root
        self.proc_sys = proc_sys
        self.download = download
        self.download_singbox = download_singbox
        self.checks = checks
        self.first_apply = first_apply or self._first_apply
        self.which = which
        self.chown = chown
        self.open_panel = open_panel or self._open_panel
        self.has_qt = has_qt or _has_qt
        self.journal = Journal(paths.journal_file)
        self.nm = nm.Nm(runner)
        self.capture = Capture(cfg, paths, runner=runner, logger=self.log, proc_sys=proc_sys)
        self.warnings: list[str] = []
        # Файл Xray заменён поверх прежнего: работающее ядро — ещё на старом (п. 226).
        self.xray_replaced = False
        # Файлы служб, которые эта установка поменяла: работающий процесс живёт по прежнему
        # (ограничения systemd — с запуска), поэтому ядра перезапускаются (_first_apply).
        self.units_changed: set[str] = set()

    # --- что известно о машине --------------------------------------------------

    def facts(self) -> Facts:
        facts = Facts(lan_if=lan.lan_interface(self.cfg))
        facts.wan_if = lan.effective_wan(self.cfg, self.runner)
        if self.which("nft") is None:
            facts.packages.append("nftables")
        if facts.lan_if and self.which("dnsmasq") is None:
            facts.packages.append(dnsmasq.PACKAGE)
        facts.user_exists = bool(
            self.runner(["getent", "passwd", XRAY_USER], check=False).strip()
        )
        if self.paths.xray_bin.exists():
            facts.xray_version = binary.installed_version(self.paths.xray_bin)
        if self.paths.singbox_bin.exists():
            facts.singbox_version = singboxing.installed_version(self.paths.singbox_bin)
        facts.nm_running = self.which("nmcli") is not None and self.nm.running()
        if facts.lan_if and facts.nm_running:
            facts.lan_profiles = [
                profile.name
                for profile, info in nm.bound_profiles(self.nm, facts.lan_if)
                if info.get("connection.autoconnect") != "no"
            ]
        facts.ufw_active = self.which("ufw") is not None and ufw.active(self.runner)
        return facts

    def _xray_fits(self, version: tuple[int, int, int] | None) -> bool:
        """Подходит ли уже лежащий Xray: проверенная XGW версия (XRAY_VERSION, config.py) либо
        более новая, принятая шлюзом после обновления из панели (cores.py)."""
        return cores.keeps(self.paths, "xray", version)

    def _singbox_fits(self, version: tuple[int, int, int] | None) -> bool:
        """Подходит ли уже лежащий sing-box: SINGBOX_VERSION либо принятая шлюзом новее."""
        return cores.keeps(self.paths, "sing-box", version)

    def subnet_conflict(self) -> str:
        """Подсеть LAN пересекается с сетью провайдера или другой сетью машины. С таким
        конфигом установку не начать и ключом --force: профиль xgw-lan дал бы карте
        адрес из чужой сети, и интернет пропал бы и у шлюза, и у устройств за ним."""
        conflicts = lan.subnet_conflicts(self.cfg, self.runner)
        if not conflicts:
            return ""
        return lan.conflict_text(
            self.cfg, conflicts, self.paths.config_file,
            lan.free_lan_address(self.cfg, self.runner),
        )

    def problems(self, facts: Facts) -> list[str]:
        """Причины, по которым установку начинать нельзя."""
        found: list[str] = []
        if facts.lan_if:
            if facts.lan_if == facts.wan_if:
                found.append(
                    f"network.lan_if = {facts.lan_if} — это интерфейс выхода в интернет; "
                    "LAN должен быть второй сетевой картой"
                )
            if not facts.nm_running:
                found.append(
                    "NetworkManager не запущен: профиль LAN создать нечем. XGW рассчитан на "
                    "Ubuntu Desktop; без NetworkManager оставьте network.lan_if пустым"
                )
            elif facts.lan_if not in self.nm.devices():
                found.append(f"интерфейса {facts.lan_if} (network.lan_if) в системе нет")
            elif self.nm.devices()[facts.lan_if].state == "unmanaged":
                found.append(
                    f"NetworkManager не управляет интерфейсом {facts.lan_if} "
                    "(состояние unmanaged) — см. `xgw diag`"
                )
            text, warnings = dnsmasq.render(self.cfg)
            if not text:
                found.extend(warnings or ["конфиг dnsmasq собрать не удалось"])
        if any(EXAMPLE_URL in sub.url for sub in self.cfg.subscriptions):
            found.append(
                f"в {self.paths.config_file} осталась подписка-пример ({EXAMPLE_URL}) — "
                "впишите свою либо удалите блок [[subscriptions]]: подписку можно "
                "добавить и после установки, в панели"
            )
        elif not engine.has_sources(self.cfg) and not self.cfg.panel.enabled:
            found.append(
                f"в {self.paths.config_file} нет ни подписки ([[subscriptions]] url), "
                "ни ссылок в [manual] links, а панель, где их можно добавить, выключена"
            )
        return found

    # --- план -------------------------------------------------------------------

    def plan(self, facts: Facts) -> list[str]:
        cfg = self.cfg
        lines = ["План установки XGW", "", "Система (сеть не меняется):"]
        if facts.packages:
            lines.append(f"  • пакеты из apt: {', '.join(facts.packages)}")
        if not facts.user_exists:
            lines.append(
                f"  • системный пользователь {XRAY_USER} (без входа) — от него работает Xray"
            )
        lines.append(f"  • код — {self.paths.lib_dir}, команда — {self.paths.launcher}")
        if self._xray_fits(facts.xray_version):
            version = ".".join(map(str, facts.xray_version or ()))
            lines.append(f"  • Xray-core {version} уже лежит в {self.paths.xray_dir}")
        else:
            lines.append(
                f"  • Xray-core {XRAY_VERSION} с GitHub — в {self.paths.xray_dir}, "
                "SHA-256 сверяется с .dgst релиза"
            )
        if self.cfg.core.mode != "xray":
            if self._singbox_fits(facts.singbox_version):
                version = ".".join(map(str, facts.singbox_version or ()))
                lines.append(f"  • sing-box {version} уже лежит в {self.paths.singbox_dir}")
            else:
                lines.append(
                    f"  • sing-box {SINGBOX_VERSION} с GitHub (второе ядро: hysteria2, TUIC, "
                    f"AnyTLS, WireGuard и обход блокировок) — в {self.paths.singbox_dir}, "
                    "SHA-256 сверяется"
                )
        lines.append("  • службы systemd: xgw-net, xgw-xray, xgw-singbox, xgw — с автозапуском")
        if cfg.panel.enabled:
            lines.append(
                f"  • панель управления — {panel.address(cfg)} (только с этой машины, "
                "по токену), ярлык «XGW» в меню приложений"
            )
        lines += ["", "Сеть:"]
        if facts.lan_if:
            lines.append(
                f"  • {self.paths.sysctl_file}: " + ", ".join(
                    f"{key}={value}" for key, value in sysctl.SETTINGS.items()
                )
            )
            lines.append(
                f"  • NetworkManager: профиль {nm.PROFILE} на {facts.lan_if} — "
                f"{cfg.network.lan_address}, без шлюза по умолчанию, IPv6 выключен"
            )
            if facts.lan_profiles:
                names = ", ".join(f"«{name}»" for name in facts.lan_profiles)
                lines.append(
                    f"  • прежние профили {facts.lan_if} ({names}) лишатся автоподключения"
                )
            start, end = [*cfg.network.dhcp_range.split(","), "", ""][:2]
            lines.append(
                f"  • DHCP {start.strip()}–{end.strip()} на {facts.lan_if}: своя служба "
                f"xgw-dhcp (dnsmasq, {dnsmasq.conf_path(self.paths)}); DNS в ней выключен"
            )
        if not cfg.network.ipv6_proxy:
            lines.append(
                f"  • IPv6 на WAN ({facts.wan_if or 'не найден'}) будет отключён: "
                "иначе трафик уйдёт мимо VPN"
            )
        else:
            lines.append(
                "  • IPv6 самой машины пойдёт через Xray (network.ipv6 = proxy); "
                "на WAN он остаётся включённым, устройствам в Wi-Fi IPv6 не выдаётся"
            )
        info = self.capture.describe(check=False)
        if self.capture.configured:
            lines.append(
                "  • nftables: свои таблицы ip xgw и ip6 xgw6; чужие правила не трогаются"
            )
        if self.capture.capturing:
            scope = [f"сеть {info['lan_if']}"] if info["lan"] else []
            if info["local"]:
                scope.append("эта машина")
            if info["containers"]:
                scope.append("контейнеры Docker (docker0, br-*)")
            closed = (
                "без работающего Xray интернета не будет (fail-closed)"
                if cfg.capture.fail_mode != "open"
                else "без Xray перехват через минуту снимется (fail_mode = open)"
            )
            lines.append(f"  • перехват: {join_ru(scope)} — через Xray; {closed}")
            if info["tun"]:
                lines.append(
                    f"  • TUN: постоянный интерфейс {cfg.capture.tun_name} (его создаёт XGW, а "
                    "не Xray); трафик самой машины идёт в него, сеть LAN — через TPROXY"
                )
            if not engine.has_sources(cfg):
                lines.append(
                    "  • подписок пока нет: VPN не включится, пока вы не добавите подписку "
                    "в панели и не нажмёте кнопку — до этого интернет работает напрямую"
                )
        if sleep.wanted(cfg):
            lines.append("  • сон: sleep, suspend, hibernate и hybrid-sleep будут замаскированы")
        elif self.journal.get("sleep"):
            lines.append("  • сон: маска, поставленная прошлой установкой, будет снята")
        elif cfg.network.disable_sleep:
            lines.append("  • сон не трогается: роутера нет, без интернета никто не останется")
        if facts.ufw_active and facts.lan_if:
            lines.append(f"  • ufw включён — будут предложены правила: {self._ufw_text(facts)}")
        lines += [
            "",
            "Вернуть всё как было: sudo xgw uninstall. "
            "Аварийно вернуть прямой интернет: sudo xgw disable.",
        ]
        return lines

    # --- запуск -----------------------------------------------------------------

    def run(self, *, assume_yes: bool = False, force: bool = False) -> int:
        facts = self.facts()
        problems = self.problems(facts)
        conflict = self.subnet_conflict()
        if self.checks is not None:
            problems += [
                f"{check.name}: {check.text}" for check in self.checks()
                if check.level == "FAIL" and not (conflict and check.text == conflict)
            ]
        if conflict:
            problems.insert(0, conflict)
        if problems:
            for problem in problems:
                self.out(f"✗ {problem}")
            if conflict:
                # Ключ --force здесь не действует: сеть машины была бы сломана наверняка.
                self.out("Установка не начата: сначала исправьте подсеть LAN в конфиге.")
                return 1
            if not force:
                self.out("Установка не начата. Исправьте и повторите (или --force).")
                return 1
        for line in self.plan(facts):
            self.out(line)
        if not assume_yes and not self.ask("Продолжить?"):
            self.out("Отменено, в системе ничего не изменено.")
            return 1

        # Установка поверх работающей (прошлая дошла до конца и не откатывалась): дом уже
        # ходит в интернет через этот шлюз, и откат к состоянию до XGW оставил бы его без сети.
        reinstall = "finished" in self.journal
        self.paths.ensure()
        self.journal.setdefault("started", time.time())
        # Метки и таблица — чтобы удаление нашло правила и без config.toml.
        self.journal.set("capture", {
            "mark_proxy": self.cfg.capture.mark_proxy,
            "route_table": self.cfg.capture.route_table,
            "tun_route_table": self.cfg.capture.tun_route_table,
            "tun_name": self.cfg.capture.tun_name,
        })
        try:
            self._system(facts)
        except (InstallError, cmd.CommandError, binary.BinaryError, OSError) as exc:
            self.out(f"✗ установка остановлена: {exc}")
            self.out("Сеть не менялась. Исправьте причину и запустите установку снова.")
            return 1
        try:
            xray_ok = self._network(facts, assume_yes)
        except (InstallError, cmd.CommandError, CaptureError, OSError) as exc:
            self.out(f"✗ настройка сети не удалась: {exc}")
            if reinstall:
                self.out(
                    "XGW уже был установлен и работал, поэтому сеть не откатываю: откат убрал "
                    "бы шлюз, и устройства остались бы без интернета. Профиль LAN, DHCP и "
                    "правила остаются как есть. Исправьте причину и запустите установку "
                    "снова; вернуть прямой интернет — sudo xgw disable, убрать XGW — "
                    "sudo xgw uninstall."
                )
                return 1
            self.out("Возвращаю сеть в исходное состояние…")
            from .uninstall import Uninstaller

            Uninstaller(
                self.cfg, self.paths, runner=self.runner, out=self.out, proc_sys=self.proc_sys
            ).run(keep_files=True)
            return 1
        self._summary(facts, xray_ok)
        return 0

    def _step(self, text: str) -> None:
        self.out(f"  ✓ {text}")

    def _warn(self, text: str) -> None:
        self.warnings.append(text)
        self.out(f"  ! {text}")

    # --- система ----------------------------------------------------------------

    def _system(self, facts: Facts) -> None:
        self.out("")
        self.out("Система:")
        self._packages(facts)
        self._user(facts)
        self._code()
        self._xray(facts)
        self._singbox(facts)
        self._tidy_config()
        self._permissions()

    def _packages(self, facts: Facts) -> None:
        if not facts.packages:
            return
        apt = ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y",
               "--no-install-recommends", *facts.packages]
        try:
            self.runner(apt, timeout=600.0)
        except cmd.CommandError:
            # Устаревшие списки пакетов — частая причина; обновляем и пробуем ещё раз.
            self.runner(["apt-get", "update"], timeout=300.0, check=False)
            try:
                self.runner(apt, timeout=600.0)
            except cmd.CommandError as exc:
                raise InstallError(
                    f"пакеты {', '.join(facts.packages)} не установлены: {exc}"
                ) from exc
        self.journal.extend("packages", facts.packages)
        self._step(f"пакеты: {', '.join(facts.packages)}")

    def _user(self, facts: Facts) -> None:
        self.journal.setdefault("user_created", not facts.user_exists)
        if facts.user_exists:
            return
        self.runner([
            "useradd", "--system", "--user-group", "--no-create-home",
            "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin", XRAY_USER,
        ])
        self._step(f"пользователь {XRAY_USER}")

    def _code(self) -> None:
        package = Path(__file__).resolve().parent
        target = self.paths.lib_dir / "xgw"
        if package != target.resolve():
            staging = self.paths.lib_dir / "xgw.new"
            shutil.rmtree(staging, ignore_errors=True)
            shutil.copytree(package, staging, ignore=shutil.ignore_patterns("__pycache__"))
            old = self.paths.lib_dir / "xgw.old"
            shutil.rmtree(old, ignore_errors=True)
            if target.exists():
                os.replace(target, old)
            os.replace(staging, target)
            shutil.rmtree(old, ignore_errors=True)
            for name in ("packaging", "config.example.toml"):
                source = self.source_root / name
                destination = self.paths.opt / name
                if source.is_dir():
                    shutil.rmtree(destination, ignore_errors=True)
                    shutil.copytree(source, destination)
                elif source.is_file():
                    shutil.copyfile(source, destination)
            # Код выполняется от root: писать в него может только root, какими бы
            # ни были права в каталоге, откуда шла установка.
            for directory in (self.paths.lib_dir, self.paths.opt / "packaging"):
                _lock_down(directory)
            self.runner(
                [sys.executable, "-m", "compileall", "-q", str(target)], timeout=120.0, check=False
            )
        atomic_write_text(
            self.paths.launcher, LAUNCHER.format(lib=self.paths.lib_dir.as_posix()), mode=0o755
        )
        self._step(f"код — {target}, команда — {self.paths.launcher}")

    def _xray(self, facts: Facts) -> None:
        if self._xray_fits(facts.xray_version):
            return
        mark = engine.bypass_mark(self.cfg, self.log)
        try:
            tag, _path = self.download(
                self.paths.xray_dir, XRAY_VERSION,
                mark=mark, bootstrap=self.cfg.dns.resolvers if mark is not None else None,
            )
        except (binary.BinaryError, fetch.FetchError) as exc:
            raise InstallError(
                f"Xray не загружен: {exc}. Можно положить xray, geoip.dat и geosite.dat в "
                f"{self.paths.xray_dir} вручную и запустить установку снова"
            ) from exc
        self.xray_replaced = facts.xray_version is not None
        cores.forget(self.paths, "xray")  # принятая из панели версия заменена проверенной
        self._step(f"Xray-core {tag} — {self.paths.xray_dir}")

    def _singbox(self, facts: Facts) -> None:
        """sing-box — второе ядро. Не загрузился — не беда: установка идёт дальше, серверы,
        которые умеет только он, пропускаются, а повторить можно `sudo xgw update-singbox`."""
        if self.cfg.core.mode == "xray" or self._singbox_fits(facts.singbox_version):
            return
        mark = engine.bypass_mark(self.cfg, self.log)
        try:
            tag, _path = self.download_singbox(
                self.paths.singbox_dir, SINGBOX_VERSION,
                mark=mark, bootstrap=self.cfg.dns.resolvers if mark is not None else None,
            )
        except (binary.BinaryError, fetch.FetchError, OSError) as exc:
            self._warn(
                f"sing-box не загружен: {exc}. Серверы hysteria2, TUIC, AnyTLS и WireGuard "
                "пропускаются; повторить: sudo xgw update-singbox"
            )
            return
        cores.forget(self.paths, "sing-box")
        self.journal.set("singbox", {"version": tag, "dir": str(self.paths.singbox_dir)})
        self._step(f"sing-box {tag} — {self.paths.singbox_dir}")

    def _tidy_config(self) -> None:
        """Строки config.toml, которые ничего не значат (Telegram, xray.version другой
        версии), — в комментарий: иначе о них предупреждает каждый запуск xgw
        (config.retire_obsolete). Файл не читается или разбор не сошёлся — не трогаем."""
        path = self.paths.config_file
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return
        changed, retired = retire_obsolete(text)
        if not retired:
            return
        atomic_write_text(path, changed, mode=0o600)
        self._step(f"{path}: выключены строки, которые больше ничего не значат — "
                   f"{', '.join(retired)} (значения остались в комментарии)")

    def _permissions(self) -> None:
        """/etc/xgw/config.toml — 0600; конфиг Xray — 0640 root:xray.

        Каталог конфигов Xray получает setgid: файлы, которые XGW создаёт в нём
        позже (атомарная запись через временный файл), наследуют группу xray.
        """
        for secret in (self.paths.config_file, managed.path_for(self.paths.config_file)):
            with contextlib.suppress(OSError):
                os.chmod(secret, 0o600)
        if os.geteuid() != 0:
            return
        os.chmod(self.paths.etc, 0o755)
        os.chmod(self.paths.var, 0o700)
        try:
            # Конфиги ядер читает пользователь xray: root:xray, каталог с setgid.
            for directory in (self.paths.xray_config_dir, self.paths.singbox_config_dir):
                self.chown(directory, "root", XRAY_USER)
                os.chmod(directory, 0o2750)
                for item in directory.iterdir():
                    if item.is_file():
                        self.chown(item, "root", XRAY_USER)
                        os.chmod(item, 0o640)
        except LookupError as exc:
            raise InstallError(f"пользователь {XRAY_USER} не создан: {exc}") from exc
        for item in (self.paths.opt, self.paths.xray_dir, self.paths.singbox_dir,
                     self.paths.lib_dir):
            with contextlib.suppress(OSError):
                os.chmod(item, 0o755)

    # --- сеть -------------------------------------------------------------------

    def _network(self, facts: Facts, assume_yes: bool) -> bool:
        self.out("")
        self.out("Сеть:")
        if facts.lan_if:
            # Последняя проверка перед тем, как менять сеть: за время установки пакетов
            # у машины мог появиться адрес из той же подсети (поднялся другой интерфейс).
            conflict = self.subnet_conflict()
            if conflict:
                raise InstallError(conflict)
            self._sysctl(facts)
            self._step(f"sysctl — {self.paths.sysctl_file}")
            record, warnings = nm.setup_lan(
                self.nm, self.cfg, self.paths.backup_dir, self.journal.get("nm_lan")
            )
            self.journal.set("nm_lan", record)
            self._step(f"профиль {nm.PROFILE} на {facts.lan_if}: {self.cfg.network.lan_address}")
            for warning in warnings:
                self._warn(warning)
        if not self.cfg.network.ipv6_proxy:
            self._wan_ipv6(facts)
        else:
            self._wan_ipv6_back(facts)
        if sleep.wanted(self.cfg):
            masked = sleep.mask(self.paths.systemd_dir, self.runner)
            self.journal.extend("sleep", masked)
            self._step("сон замаскирован")
        else:
            self._sleep_back()
        if facts.ufw_active and facts.lan_if:
            self._ufw(facts, assume_yes)
        self._legacy_dnsmasq()
        self._units()
        self._dnsmasq(bool(facts.lan_if))
        # Без подписок собирать нечего: Xray запустит демон, когда их добавят в панели.
        xray_ok = self.first_apply() if engine.has_sources(self.cfg) else False
        self._capture(xray_ok)
        if self.cfg.panel.enabled:
            self._panel()
        self._daemon()
        self._tray()
        if self.cfg.status.lan_page and facts.lan_if:
            self._token()
        self.journal.set("finished", time.time())
        return xray_ok

    def _daemon(self) -> None:
        """Запуск (при повторной установке — перезапуск) демона. Сеть LAN, DHCP, правила и
        Xray к этому времени на месте и без демона работают, поэтому его сбой —
        предупреждение, а не повод откатывать установку (отчёт 0.1.15, Д1): клиент
        systemctl не дождался — задание systemd идёт дальше, служба не запустилась —
        systemd (Restart=always) попробует снова."""
        try:
            self.runner(["systemctl", "restart", "xgw.service"], timeout=DAEMON_STOP_WAIT)
        except cmd.CommandError as exc:
            self._warn(
                f"демон xgw пока не запущен ({exc}). Сеть, DHCP и перехват работают и без "
                "него, systemd запустит его сам; проверка — sudo xgw status через минуту"
            )
            return
        self._step("демон xgw запущен")

    def _sleep_back(self) -> None:
        """Роутера больше нет или disable_sleep = false: маска, поставленная прошлой
        установкой, снимается. Цели, замаскированные до XGW, остаются как были."""
        targets = self.journal.get("sleep") or []
        if not targets:
            return
        sleep.unmask(list(targets), self.runner)
        self.journal.discard("sleep")
        self._step("сон размаскирован")

    def _wan_ipv6(self, facts: Facts) -> None:
        if not facts.nm_running:
            self._warn(
                "NetworkManager не запущен — IPv6 на WAN не отключён; если у провайдера есть "
                "IPv6, трафик пойдёт мимо VPN (см. `xgw diag`)"
            )
            return
        record, warnings = nm.wan_ipv6_off(self.nm, facts.wan_if, self.journal.get("nm_wan"))
        if record is not None:
            self.journal.set("nm_wan", record)
            if record.get("sysctl"):
                self._sysctl(facts)
                self._step(
                    f"IPv6 на {facts.wan_if} отключён в {self.paths.sysctl_file}: профиль WAN "
                    "описан в netplan, его XGW не меняет"
                )
            else:
                self._step(f"IPv6 в профиле WAN ({facts.wan_if}) отключён")
        for warning in warnings:
            self._warn(warning)

    def _sysctl(self, facts: Facts) -> None:
        """90-xgw.conf по нынешним настройкам: форвардинг, если есть сеть LAN, и
        disable_ipv6 карты WAN, если IPv6 на ней выключает sysctl (nm.wan_ipv6_off).
        Значения до установки запоминаются один раз — для каждого ключа."""
        record = self.journal.get("nm_wan") or {}
        wan = record.get("device", "") if record.get("sysctl") else ""
        settings = sysctl.wanted(forwarding=bool(facts.lan_if), wan_ipv6_off=wan)
        previous = sysctl.install(self.paths, self.proc_sys, settings)
        saved = dict(self.journal.get("sysctl") or {})
        for name, value in previous.items():
            saved.setdefault(name, value)
        self.journal.set("sysctl", saved)

    def _wan_ipv6_back(self, facts: Facts) -> None:
        """ipv6 = proxy после ipv6 = off: IPv6 на WAN, отключённый прошлой установкой,
        возвращается. Чужие настройки профиля, которых XGW не менял, не трогаются."""
        record = self.journal.get("nm_wan")
        if not record:
            return
        if record.get("sysctl"):
            # IPv6 выключал sysctl: ключ убирается из 90-xgw.conf, значение — прежнее.
            self.journal.discard("nm_wan")
            self._sysctl(facts)
            key = sysctl.wan_ipv6_key(record.get("device", ""))
            sysctl.put_back(self.journal.get("sysctl") or {}, [key], self.proc_sys)
            self._step(f"IPv6 на {record.get('device', '')} возвращён: network.ipv6 = proxy")
            return
        if not facts.nm_running:
            self._warn(
                "NetworkManager не запущен — IPv6 на WAN не возвращён; запустите его и "
                "повторите установку"
            )
            return
        warnings = nm.restore_wan(self.nm, record)
        for warning in warnings:
            self._warn(warning)
        if not warnings:
            self.journal.discard("nm_wan")
            self._step(f"IPv6 в профиле WAN ({facts.wan_if}) возвращён: network.ipv6 = proxy")

    def _ufw_tproxy(self) -> bool:
        """Нужна ли строка в before.rules: только когда перехватывается трафик LAN."""
        return self.cfg.capture.lan

    def _ufw_text(self, facts: Facts) -> str:
        text = "; ".join(
            "ufw " + " ".join(rule) for rule in ufw.wanted(facts.lan_if, facts.wan_if)
        )
        if self._ufw_tproxy():
            rule = ufw.tproxy_rule(facts.lan_if, self.cfg.capture.mark_proxy)
            text += f"; в {ufw.before_rules(self.paths.root)} — «{rule}»"
        return text

    def _ufw(self, facts: Facts, assume_yes: bool) -> None:
        text = self._ufw_text(facts)
        if not assume_yes and not self.ask(f"ufw включён. Добавить правила: {text}?"):
            self._warn(
                "правила ufw не добавлены: устройства в сети останутся без интернета, "
                f"пока вы не добавите их сами ({text}; затем ufw reload)"
            )
            return
        added = ufw.add(ufw.wanted(facts.lan_if, facts.wan_if), self.runner)
        self.journal.extend("ufw", added)
        if self._ufw_tproxy():
            # Без этой строки ufw отбрасывает перехваченные пакеты устройств: у них
            # чужой адрес назначения (цепочка ufw-not-local).
            path = ufw.before_rules(self.paths.root)
            try:
                ufw.add_tproxy_rule(
                    path, facts.lan_if, self.cfg.capture.mark_proxy,
                    self.paths.backup_dir, self.runner,
                )
                self.journal.set("ufw_before", True)
            except cmd.CommandError as exc:
                self._warn(f"ufw: {exc}")
        self._step(f"ufw: {text}")

    def _legacy_dnsmasq(self) -> None:
        """Установка до 0.1.4 раздавала DHCP штатной службой dnsmasq.service по файлу в
        /etc/dnsmasq.d. Теперь у XGW своя служба: файл убирается, штатная служба
        возвращается в состояние до XGW (по журналу), аренды устройств переезжают."""
        record = self.journal.get("dnsmasq")
        if record is None and not dnsmasq.legacy_conf_path(self.paths).exists():
            return
        dnsmasq.migrate_leases(self.paths)
        done = dnsmasq.restore_system(self.paths, record, self.runner)
        self.journal.discard("dnsmasq")
        self._step(f"{done}: DHCP теперь раздаёт своя служба xgw-dhcp")

    def _dnsmasq(self, lan_on: bool) -> None:
        """Своя служба DHCP (xgw-dhcp): с LAN — конфиг и запуск; без LAN — конфиг убран,
        служба остановлена (сеть LAN могли убрать из настроек при повторной установке)."""
        _changed, warnings = dnsmasq.write_conf(self.cfg, self.paths)
        for warning in warnings:
            self._warn(warning)
        if not lan_on:
            self.runner(["systemctl", "disable", "--now", dnsmasq.UNIT], timeout=60.0,
                        check=False)
            return
        self.runner(["systemctl", "enable", dnsmasq.UNIT], timeout=60.0)
        try:
            self.runner(["systemctl", "restart", dnsmasq.UNIT], timeout=120.0)
        except cmd.CommandError as exc:
            self._warn(f"служба DHCP xgw-dhcp не запустилась — устройства не получат адреса: {exc}")
            return
        self._step(f"DHCP на {lan.lan_interface(self.cfg)}: служба xgw-dhcp (dnsmasq)")

    def _units(self) -> None:
        source = self.source_root / "packaging"
        if not source.is_dir():
            source = self.paths.opt / "packaging"
        self.paths.systemd_dir.mkdir(parents=True, exist_ok=True)
        for unit in UNIT_FILES:
            try:
                text = (source / unit).read_text(encoding="utf-8")
            except OSError as exc:
                raise InstallError(f"нет файла службы {source / unit}: {exc}") from exc
            target = self.paths.systemd_dir / unit
            try:
                if target.read_text(encoding="utf-8") != text:
                    self.units_changed.add(unit)
            except OSError:
                pass  # файла не было — служба ещё не запускалась
            atomic_write_text(target, text, mode=0o644)
        self.journal.set("units", list(UNIT_FILES))
        self.runner(["systemctl", "daemon-reload"], timeout=60.0)
        self.runner(["systemctl", "enable", *UNITS], timeout=60.0)
        self._step("службы: " + ", ".join(unit.removesuffix(".service") for unit in UNITS))

    def _first_apply(self) -> bool:
        """Первая генерация конфига и запуск Xray. True — ядро отвечает."""
        xray_bin = self.paths.xray_bin
        mark = engine.bypass_mark(self.cfg, self.log)
        applier = engine.make_applier(self.cfg, self.paths, xray_bin)
        try:
            inventory = engine.collect(self.cfg, self.paths, mark=mark, logger=self.log)
            assembly = engine.assemble(
                self.cfg, self.paths, inventory, mark=mark, logger=self.log, xray_bin=xray_bin
            )
        except engine.EngineError as exc:
            self._warn(f"конфиг Xray не собран: {exc}")
            return self._xray_answers(applier, 0.0)
        outcome, singbox_outcome = engine.apply_all(
            self.cfg, self.paths, assembly, applier, force_now=True,
        )
        if singbox_outcome is not None and singbox_outcome.mode != "unchanged":
            self._step(engine.describe_singbox(singbox_outcome))
        if SINGBOX_UNIT in self.units_changed and (
                singbox_outcome is None or singbox_outcome.mode not in ("started", "removed")):
            # Новые ограничения службы действуют с запуска процесса; перечитывание конфига
            # (SIGHUP) их не применяет. Не работает — и перезапускать нечего (try-restart).
            running = self.runner(
                ["systemctl", "is-active", SINGBOX_UNIT], check=False).strip() == "active"
            if running:
                try:
                    self.runner(["systemctl", "try-restart", SINGBOX_UNIT], timeout=60.0)
                    self._step("sing-box перезапущен: файл его службы изменился")
                except cmd.CommandError as exc:
                    self._warn(f"sing-box не перезапущен ({exc}): новые ограничения службы "
                               "вступят в силу при следующем запуске")
        if outcome is None:
            self._warn(engine.describe_singbox(singbox_outcome))  # type: ignore[arg-type]
            return self._xray_answers(applier, 0.0)
        if outcome.mode in ("api", "restart", "unchanged"):
            engine.persist(self.paths, assembly, inventory.quotas)
        unit_changed = "xgw-xray.service" in self.units_changed
        if (self.xray_replaced or unit_changed) and outcome.mode in ("api", "unchanged"):
            # Установка поверх работающего шлюза положила новую версию Xray (os.replace), а
            # процесс работает на прежнем файле: без перезапуска шлюз остался бы на старой
            # версии до перезагрузки машины (п. 226). То же с файлом службы: её ограничения
            # действуют с запуска процесса.
            with contextlib.suppress(XrayServiceError):
                applier.service.restart()
            self._step("Xray перезапущен на новой версии" if self.xray_replaced
                       else "Xray перезапущен: файл его службы изменился")
        elif outcome.mode == "unchanged" and not self._xray_answers(applier, 0.0):
            with contextlib.suppress(XrayServiceError):
                applier.service.restart()
        members = sum(1 for info in assembly.result.nodes if info.role == "proxy")
        if self._xray_answers(applier, XRAY_WAIT):
            self._step(
                f"Xray запущен: участников {members}, "
                f"запасных {len(assembly.result.nodes) - members}"
            )
            return True
        self._warn(f"Xray не отвечает: {engine.describe(outcome)}")
        return False

    def _xray_answers(self, applier, wait: float) -> bool:
        deadline = time.monotonic() + wait
        while True:
            try:
                applier.api.balancer_info(BALANCER_TAG)
                return True
            except ApiError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.5)

    def _capture(self, xray_ok: bool) -> None:
        """Правила сети. Перехват включается, только когда Xray отвечает: иначе
        fail-closed оставил бы машину без интернета сразу после установки."""
        capture = self.capture
        if capture.choice() is not None or not capture.capturing:
            capture.up()  # повторная установка: выбор пользователя (enable/disable) в силе
        elif xray_ok:
            capture.enable()
        elif not engine.has_sources(self.cfg):
            capture.disable()
            self._step("подписок пока нет — VPN не включён, интернет работает напрямую")
        else:
            capture.disable()
            self._warn(
                "Xray не запущен, поэтому перехват не включён: интернет работает напрямую. "
                "Когда `sudo xgw apply --now` пройдёт, включите перехват: sudo xgw enable"
            )
        # Служба нужна после перезагрузки; сейчас правила уже загружены.
        self.runner(["systemctl", "start", "xgw-net.service"], timeout=60.0)
        if capture.configured:
            mode = {"on": "перехват включён", "off": "перехват снят", "open": "перехват снят",
                    "blocked": "трафик заблокирован до перезапуска Xray"}
            loaded = capture.effective_mode()
            self._step(f"правила nftables загружены, {mode.get(loaded, 'перехвата нет')}")
            if capture.mode() == "on" and loaded != "on":
                # Xray запущен с конфигом без нужного inbound'а: честнее сказать, чем
                # отчитаться «включён». Демон включит перехват сам, когда конфиг применится.
                held = (
                    "Интернет закрыт, мимо VPN ничего не уходит (capture.hold = block)"
                    if loaded == "blocked" else "Интернет работает напрямую"
                )
                self._warn(
                    f"перехват пока не включён: {capture.inbound_problem()}. {held}; "
                    "перехват включится сам после перезапуска Xray (сразу: sudo xgw apply --now)"
                )

    def _token(self) -> None:
        status_page.ensure_token(self.cfg, self.paths)
        self._step("токен страницы статуса готов")

    def _panel(self) -> None:
        """Токен панели и ярлык в меню приложений."""
        panel.ensure_token(self.paths)
        path = self.paths.desktop_file
        icon = self.paths.lib_dir / "xgw" / "ui" / "icon.svg"
        # Каталог мог появиться вместе с ярлыком — тогда удаление уберёт и его.
        self.journal.setdefault("launcher_dir", not path.parent.exists())
        try:
            atomic_write_text(
                path,
                DESKTOP_ENTRY.format(
                    url=panel.address(self.cfg), icon=icon.as_posix(),
                    launcher=self.paths.launcher.as_posix(),
                ),
                mode=0o644,
            )
        except OSError as exc:
            self._warn(f"ярлык панели не создан ({exc}) — открывайте её по ссылке")
            return
        self.journal.set("launcher", str(path))
        self._step(f"панель управления: {panel.address(self.cfg)}, ярлык «XGW» в меню приложений")

    def _tray(self) -> None:
        """Значок в трее (ТЗ R9): PyQt из пакетов Ubuntu, автозапуск при входе в сеанс, файл с
        портом панели и токеном трея — тому, кто запустил установку, и запуск значка сейчас.
        Значок — удобство: что-то не вышло — предупреждение, установка идёт дальше.
        tray.enabled = false — автозапуск убирается."""
        autostart = self.paths.root / tray.AUTOSTART
        if not (self.cfg.tray.enabled and self.cfg.panel.enabled):
            if autostart.exists():
                autostart.unlink()
                self._step("значок в трее выключен (tray.enabled = false) — автозапуск убран")
            return
        if not self.has_qt():
            apt = ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y",
                   "--no-install-recommends", tray.QT_PACKAGE]
            try:
                self.runner(apt, timeout=600.0)
            except cmd.CommandError as exc:
                self._warn(f"значок в трее не поставлен: пакет {tray.QT_PACKAGE} не "
                           f"установился ({exc}); панель работает и без него")
                return
            self.journal.extend("packages", [tray.QT_PACKAGE])
            self._step(f"пакеты: {tray.QT_PACKAGE} (значок в трее)")
        self.journal.setdefault("tray_autostart_dir", not autostart.parent.exists())
        autostart.parent.mkdir(parents=True, exist_ok=True)
        icon = self.paths.lib_dir / "xgw" / "ui" / "icon.svg"
        atomic_write_text(autostart, tray.desktop_entry(self.paths.launcher, icon), mode=0o644)
        self.journal.set("tray_autostart", str(autostart))
        token = tray.ensure_token(self.paths)
        user = desktop.invoking_user()
        if user is None:
            self._step("значок в трее: автозапуск при входе в сеанс (токен — sudo xgw install "
                       "от имени человека)")
            return
        try:
            entry = pwd.getpwuid(user.uid)
            path = tray.write_user_file(
                Path(entry.pw_dir), user.uid, entry.pw_gid, self.cfg.panel.port, token,
            )
        except (KeyError, OSError) as exc:
            self._warn(f"значок в трее: файл для {user.name} не записан ({exc})")
            return
        self.journal.set("tray_user_file", str(path))
        started = ""
        if desktop.graphical(user, self.runner):
            try:
                self.runner(
                    ["systemd-run", "--user", f"--machine={user.name}@", "--quiet", "--collect",
                     "--description=XGW: значок в трее", "--", str(self.paths.launcher), "tray",
                     "--replace"],  # прежний значок (прошлой установки) уступает место новому
                    timeout=20.0,
                )
                started = ", запущен"
            except cmd.CommandError as exc:
                self._warn(f"значок в трее не запущен сейчас ({exc}): он появится при "
                           "следующем входе в сеанс")
        self._step(f"значок в трее для {user.name}: автозапуск при входе{started}")

    # --- итог -------------------------------------------------------------------

    def _open_panel(self) -> str:
        """Панель — в браузере того, кто запустил установку через sudo, с одноразовым
        кодом входа. Имя пользователя; пусто — открывать негде (не через sudo, нет
        графического сеанса)."""
        user = desktop.invoking_user()
        if user is None or not desktop.graphical(user, self.runner):
            return ""
        if not panel.wait_ready(self.cfg.panel.port):
            raise desktop.DesktopError("панель ещё не отвечает")
        url = panel.login_address(self.cfg, panel.new_login(self.paths))
        desktop.open_url(user, url, self.runner)
        return user.name

    def _browser(self) -> str:
        try:
            return self.open_panel()
        except (desktop.DesktopError, OSError) as exc:
            self._warn(f"панель в браузере не открылась: {exc}")
            return ""

    def _summary(self, facts: Facts, xray_ok: bool) -> None:
        self.out("")
        sources = engine.has_sources(self.cfg)
        if xray_ok:
            self.out("XGW установлен.")
        elif sources:
            self.out("XGW установлен, но Xray пока не запущен.")
        else:
            self.out("XGW установлен. Подписок пока нет — VPN выключен, интернет идёт напрямую.")
        if self.cfg.panel.enabled:
            opened = self._browser()
            token = panel.read_token(self.paths)
            self.out(f"Панель управления: {panel.address(self.cfg)}?token={token}")
            if opened:
                self.out(
                    f"  Панель уже открыта в браузере пользователя {opened}, вход выполнен. "
                    "Если окна не видно — откройте ссылку выше (в терминале — Ctrl и щелчок)."
                )
            else:
                self.out(
                    "  Откройте эту ссылку в браузере на этой машине (в терминале — Ctrl и "
                    "щелчок)."
                )
            if not sources:
                self.out("  Вставьте в панели адрес подписки и нажмите кнопку включения.")
            self.out(
                "  Дальше панель открывается ярлыком «XGW» в меню приложений. Если браузер "
                "забудет вход — правая кнопка по ярлыку, «Войти заново» (спросит пароль); "
                "ссылку заново напечатает и sudo xgw panel."
            )
        if facts.lan_if:
            address = self.cfg.network.lan_address.split("/")[0]
            self.out(
                f"Роутер: переведите в режим точки доступа, выключите его DHCP и подключите "
                f"кабель от {facts.lan_if} в LAN-порт. Шлюз для устройств — {address}."
            )
        if sleep.wanted(self.cfg):
            self.out(f"GNOME, чтобы не засыпал по простою: {sleep.GNOME_HINT}")
        if self.cfg.status.lan_page and facts.lan_if:
            address = self.cfg.network.lan_address.split("/")[0]
            self.out(
                f"Страница статуса: http://{address}:8780/?token=… "
                f"(токен — sudo cat {self.paths.status_token_file})"
                if not self.cfg.status.token
                else f"Страница статуса: http://{address}:8780/?token=<status.token>"
            )
        self.out("Проверка: sudo xgw status. Вернуть прямой интернет: sudo xgw disable.")
        if self.warnings:
            self.out(f"Предупреждений: {len(self.warnings)} — они отмечены знаком «!» выше.")
