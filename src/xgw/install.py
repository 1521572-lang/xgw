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
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import engine, fetch, log, managed
from .config import Config
from .generator.builder import BALANCER_TAG
from .net import cmd, dnsmasq, lan, nm, sleep, sysctl, ufw
from .net.capture import Capture, CaptureError
from .paths import Paths, atomic_write_json, atomic_write_text
from .watch import panel, status_page
from .xraycore import binary
from .xraycore.api import ApiError
from .xraycore.service import XrayServiceError

# Корень дистрибутива: репозиторий при запуске из исходников, /opt/xgw после установки.
SOURCE_ROOT = Path(__file__).resolve().parents[2]
UNITS = ("xgw-net.service", "xgw-xray.service", "xgw.service")
XRAY_USER = "xray"
XRAY_WAIT = 20.0  # сколько ждать ответа API после первого запуска Xray
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
Exec=xdg-open {url}
Icon={icon}
Terminal=false
Categories=Network;
Keywords=vpn;xray;proxy;
StartupNotify=false
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
    nm_running: bool = False
    lan_profiles: list[str] = field(default_factory=list)  # профили, которые будут отключены
    ufw_active: bool = False


def _lock_down(directory: Path) -> None:
    """Каталоги 0755, файлы 0644 — без права записи для группы и остальных."""
    if os.name == "nt":
        return
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
        checks: Callable[[], list] | None = None,
        first_apply: Callable[[], bool] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        chown: Callable[..., None] = shutil.chown,
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
        self.checks = checks
        self.first_apply = first_apply or self._first_apply
        self.which = which
        self.chown = chown
        self.journal = Journal(paths.journal_file)
        self.nm = nm.Nm(runner)
        self.capture = Capture(cfg, paths, runner=runner, logger=self.log, proc_sys=proc_sys)
        self.warnings: list[str] = []

    # --- что известно о машине --------------------------------------------------

    def facts(self) -> Facts:
        facts = Facts(lan_if=lan.lan_interface(self.cfg))
        facts.wan_if = lan.effective_wan(self.cfg, self.runner)
        if self.which("nft") is None:
            facts.packages.append("nftables")
        if facts.lan_if and not self._package_installed("dnsmasq"):
            facts.packages.append("dnsmasq")
        facts.user_exists = bool(
            self.runner(["getent", "passwd", XRAY_USER], check=False).strip()
        )
        if self.paths.xray_bin.exists():
            facts.xray_version = binary.installed_version(self.paths.xray_bin)
        facts.nm_running = self.which("nmcli") is not None and self.nm.running()
        if facts.lan_if and facts.nm_running:
            facts.lan_profiles = [
                profile.name
                for profile, info in nm.bound_profiles(self.nm, facts.lan_if)
                if info.get("connection.autoconnect") != "no"
            ]
        facts.ufw_active = self.which("ufw") is not None and ufw.active(self.runner)
        return facts

    def _package_installed(self, name: str) -> bool:
        text = self.runner(["dpkg-query", "-W", "-f=${Status}", name], check=False)
        return "ok installed" in text

    def _xray_fits(self, version: tuple[int, int, int] | None) -> bool:
        """Подходит ли уже лежащий Xray: не ниже минимальной и той версии, что в конфиге."""
        if version is None or version < binary.MIN_VERSION:
            return False
        wanted = self.cfg.xray.version
        if wanted in ("", "latest"):
            return True
        with contextlib.suppress(binary.BinaryError):
            return binary.parse_version(wanted) == version
        return False

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
                f"  • Xray-core ({cfg.xray.version}) с GitHub — в {self.paths.xray_dir}, "
                "SHA-256 сверяется с .dgst релиза"
            )
        lines.append("  • службы systemd: xgw-net, xgw-xray, xgw — с автозапуском")
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
                f"  • dnsmasq: DHCP {start.strip()}–{end.strip()} на {facts.lan_if} "
                f"({dnsmasq.conf_path(self.paths)}); DNS в dnsmasq выключен"
            )
        if cfg.network.ipv6 == "off":
            lines.append(
                f"  • IPv6 в профиле WAN ({facts.wan_if or 'не найден'}) будет отключён: "
                "иначе трафик уйдёт мимо VPN"
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
            closed = (
                "без работающего Xray интернета не будет (fail-closed)"
                if cfg.capture.fail_mode != "open"
                else "без Xray перехват через минуту снимется (fail_mode = open)"
            )
            lines.append(f"  • перехват: {' и '.join(scope)} — через Xray; {closed}")
            if not engine.has_sources(cfg):
                lines.append(
                    "  • подписок пока нет: VPN не включится, пока вы не добавите подписку "
                    "в панели и не нажмёте кнопку — до этого интернет работает напрямую"
                )
        if cfg.network.disable_sleep:
            lines.append("  • сон: sleep, suspend, hibernate и hybrid-sleep будут замаскированы")
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
        if self.checks is not None:
            problems += [
                f"{check.name}: {check.text}" for check in self.checks() if check.level == "FAIL"
            ]
        if problems:
            for problem in problems:
                self.out(f"✗ {problem}")
            if not force:
                self.out("Установка не начата. Исправьте и повторите (или --force).")
                return 1
        for line in self.plan(facts):
            self.out(line)
        if not assume_yes and not self.ask("Продолжить?"):
            self.out("Отменено, в системе ничего не изменено.")
            return 1

        self.paths.ensure()
        self.journal.setdefault("started", time.time())
        # Метки и таблица — чтобы удаление нашло правила и без config.toml.
        self.journal.set("capture", {
            "mark_proxy": self.cfg.capture.mark_proxy,
            "route_table": self.cfg.capture.route_table,
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
        if facts.lan_if:
            # До установки пакета: с конфигом по умолчанию dnsmasq занял бы порт 53,
            # на котором уже слушает systemd-resolved, и его служба не запустилась бы.
            self._remember_dnsmasq()
            dnsmasq.write_conf(self.cfg, self.paths)
        self._packages(facts)
        self._user(facts)
        self._code()
        self._xray(facts)
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

    def _remember_dnsmasq(self) -> None:
        if "dnsmasq" in self.journal:
            return
        installed = self._package_installed("dnsmasq")
        self.journal.set("dnsmasq", {
            "package": not installed,  # пакет поставит XGW
            "enabled": installed and self._unit_is("is-enabled", dnsmasq.UNIT, "enabled"),
            "active": installed and self._unit_is("is-active", dnsmasq.UNIT, "active"),
        })

    def _unit_is(self, verb: str, unit: str, expected: str) -> bool:
        return self.runner(["systemctl", verb, unit], check=False).strip() == expected

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
                self.paths.xray_dir, self.cfg.xray.version,
                mark=mark, bootstrap=self.cfg.dns.bootstrap if mark is not None else None,
            )
        except (binary.BinaryError, fetch.FetchError) as exc:
            raise InstallError(
                f"Xray не загружен: {exc}. Можно положить xray, geoip.dat и geosite.dat в "
                f"{self.paths.xray_dir} вручную и запустить установку снова"
            ) from exc
        self._step(f"Xray-core {tag} — {self.paths.xray_dir}")

    def _permissions(self) -> None:
        """/etc/xgw/config.toml — 0600; конфиг Xray — 0640 root:xray.

        Каталог конфигов Xray получает setgid: файлы, которые XGW создаёт в нём
        позже (атомарная запись через временный файл), наследуют группу xray.
        """
        for secret in (self.paths.config_file, managed.path_for(self.paths.config_file)):
            with contextlib.suppress(OSError):
                os.chmod(secret, 0o600)
        if os.name == "nt" or os.geteuid() != 0:
            return
        os.chmod(self.paths.etc, 0o755)
        os.chmod(self.paths.var, 0o700)
        directory = self.paths.xray_config_dir
        try:
            self.chown(directory, "root", XRAY_USER)
            os.chmod(directory, 0o2750)
            for item in directory.iterdir():
                if item.is_file():
                    self.chown(item, "root", XRAY_USER)
                    os.chmod(item, 0o640)
        except LookupError as exc:
            raise InstallError(f"пользователь {XRAY_USER} не создан: {exc}") from exc
        for item in (self.paths.opt, self.paths.xray_dir, self.paths.lib_dir):
            with contextlib.suppress(OSError):
                os.chmod(item, 0o755)

    # --- сеть -------------------------------------------------------------------

    def _network(self, facts: Facts, assume_yes: bool) -> bool:
        self.out("")
        self.out("Сеть:")
        if facts.lan_if:
            previous = sysctl.install(self.paths, self.proc_sys)
            self.journal.setdefault("sysctl", previous)
            self._step(f"sysctl — {self.paths.sysctl_file}")
            record, warnings = nm.setup_lan(
                self.nm, self.cfg, self.paths.backup_dir, self.journal.get("nm_lan")
            )
            self.journal.set("nm_lan", record)
            self._step(f"профиль {nm.PROFILE} на {facts.lan_if}: {self.cfg.network.lan_address}")
            for warning in warnings:
                self._warn(warning)
        if self.cfg.network.ipv6 == "off":
            self._wan_ipv6(facts)
        if self.cfg.network.disable_sleep:
            masked = sleep.mask(self.paths.systemd_dir, self.runner)
            self.journal.extend("sleep", masked)
            self._step("сон замаскирован")
        if facts.ufw_active and facts.lan_if:
            self._ufw(facts, assume_yes)
        if facts.lan_if:
            self._dnsmasq()
        self._units()
        # Без подписок собирать нечего: Xray запустит демон, когда их добавят в панели.
        xray_ok = self.first_apply() if engine.has_sources(self.cfg) else False
        self._capture(xray_ok)
        if self.cfg.panel.enabled:
            self._panel()
        self.runner(["systemctl", "restart", "xgw.service"], timeout=60.0)
        self._step("демон xgw запущен")
        if self.cfg.status.lan_page and facts.lan_if:
            self._token()
        self.journal.set("finished", time.time())
        return xray_ok

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
            self._step(f"IPv6 в профиле WAN ({facts.wan_if}) отключён")
        for warning in warnings:
            self._warn(warning)

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

    def _dnsmasq(self) -> None:
        _changed, warnings = dnsmasq.write_conf(self.cfg, self.paths)
        for warning in warnings:
            self._warn(warning)
        self.runner(["systemctl", "enable", dnsmasq.UNIT], timeout=60.0)
        try:
            self.runner(["systemctl", "restart", dnsmasq.UNIT], timeout=120.0)
        except cmd.CommandError as exc:
            self._warn(f"dnsmasq не запустился — устройства не получат адреса: {exc}")
            return
        self._step(f"dnsmasq: DHCP на {lan.lan_interface(self.cfg)}")

    def _units(self) -> None:
        source = self.source_root / "packaging"
        if not source.is_dir():
            source = self.paths.opt / "packaging"
        self.paths.systemd_dir.mkdir(parents=True, exist_ok=True)
        for unit in UNITS:
            try:
                text = (source / unit).read_text(encoding="utf-8")
            except OSError as exc:
                raise InstallError(f"нет файла службы {source / unit}: {exc}") from exc
            atomic_write_text(self.paths.systemd_dir / unit, text, mode=0o644)
        self.journal.set("units", list(UNITS))
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
        outcome = applier.apply(assembly.result.config, force_now=True)
        if outcome.mode in ("api", "restart", "unchanged"):
            engine.persist(self.paths, assembly, inventory.quotas)
        if outcome.mode == "unchanged" and not self._xray_answers(applier, 0.0):
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
            mode = {"on": "перехват включён", "off": "перехват снят", "open": "перехват снят"}
            self._step(f"правила nftables загружены, {mode.get(capture.mode(), 'перехвата нет')}")

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
                path, DESKTOP_ENTRY.format(url=panel.address(self.cfg), icon=icon.as_posix()),
                mode=0o644,
            )
        except OSError as exc:
            self._warn(f"ярлык панели не создан ({exc}) — открывайте её по ссылке")
            return
        self.journal.set("launcher", str(path))
        self._step(f"панель управления: {panel.address(self.cfg)}, ярлык «XGW» в меню приложений")

    # --- итог -------------------------------------------------------------------

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
            token = panel.read_token(self.paths)
            self.out(f"Панель управления: {panel.address(self.cfg)}?token={token}")
            self.out(
                "  Откройте эту ссылку в браузере на этой машине (в терминале — Ctrl и щелчок)."
            )
            if not sources:
                self.out("  Вставьте в панели адрес подписки и нажмите кнопку включения.")
            self.out(
                "  Дальше панель открывается ярлыком «XGW» в меню приложений; ссылку заново "
                "напечатает sudo xgw panel."
            )
        if facts.lan_if:
            address = self.cfg.network.lan_address.split("/")[0]
            self.out(
                f"Роутер: переведите в режим точки доступа, выключите его DHCP и подключите "
                f"кабель от {facts.lan_if} в LAN-порт. Шлюз для устройств — {address}."
            )
        if self.cfg.network.disable_sleep:
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
