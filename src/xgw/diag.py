"""`xgw diag` — проверки машины с вердиктом OK, WARN или FAIL и советом (раздел 6.9).

Ничего не меняет в системе. Правила nftables проверяются в отдельном сетевом
пространстве имён (`unshare -n`): ядро принимает их по-настоящему, а сеть
машины при этом не затрагивается. FAIL — установку начинать нельзя.

Перед установкой (preinstall) состояние уже установленного XGW — службы, загруженные
правила, интерфейс TUN — не FAIL, а WARN: это установка и исправит (перезапустит службы,
загрузит правила заново). Иначе обновление на версию с новой службой или цепочкой правил
требовало бы --force.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from . import engine, fetch, log, masking
from .config import SINGBOX_VERSION, XRAY_VERSION, Config, probe_bytes
from .generator import builder, validate
from .generator import singbox as singboxing
from .generator.builder import BALANCER_TAG
from .install import SINGBOX_UNIT, UNITS
from .net import cmd, dnsmasq, lan, nft, nm, sleep, sysctl, ufw
from .net.capture import Capture
from .paths import Paths
from .sbcore import binary as sbbinary
from .store import Store
from .watch import checks as probes
from .watch import scan, status, target
from .xraycore import binary, metrics

OK, WARN, FAIL = "OK", "WARN", "FAIL"
STATUS_PAGE_PORT = 8780
OS_RELEASE = Path("/etc/os-release")
DEV_TUN = Path("/dev/net/tun")
PROC = Path("/proc")
CHRONY_DIR = Path("/etc/chrony")
# Пользователь службы времени → её юнит (chrony в 26.04, systemd-timesyncd в 24.04).
TIME_UNITS = {"_chrony": "chrony", "systemd-timesync": "systemd-timesyncd"}


@dataclass(frozen=True)
class Check:
    name: str
    level: str
    text: str
    advice: str = ""


def render(checks: Sequence[Check]) -> str:
    lines: list[str] = []
    for check in checks:
        lines.append(f"{check.level:<4}  {check.name}: {check.text}")
        if check.advice:
            lines.append(f"      → {check.advice}")
    counts = {level: sum(1 for check in checks if check.level == level)
              for level in (OK, WARN, FAIL)}
    lines.append(f"Итог: OK — {counts[OK]}, WARN — {counts[WARN]}, FAIL — {counts[FAIL]}")
    return "\n".join(lines)


def can_bind(port: int) -> bool:
    """Свободен ли TCP-порт на 127.0.0.1."""
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


class Diag:
    def __init__(
        self,
        cfg: Config,
        paths: Paths,
        *,
        runner: cmd.Runner = cmd.run,
        logger=None,
        net: bool = True,
        config_error: str = "",
        config_warnings: Sequence[str] = (),
        which: Callable[[str], str | None] = shutil.which,
        is_root: bool | None = None,
        os_release: Path = OS_RELEASE,
        port_free: Callable[[int], bool] = can_bind,
        proc_sys: Path = sysctl.PROC_SYS,
        dev_tun: Path = DEV_TUN,
        preinstall: bool = False,
        proc: Path = PROC,
    ) -> None:
        self.proc_sys = proc_sys
        self.proc = proc
        self.preinstall = preinstall
        self.dev_tun = dev_tun
        self.cfg = cfg
        self.paths = paths
        self.runner = runner
        self.log = logger or log.get_logger("diag")
        self.net = net
        self.config_error = config_error
        self.config_warnings = list(config_warnings)
        self.which = which
        if is_root is None:
            is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        self.root = is_root
        self.os_release = os_release
        self.port_free = port_free
        self.lan_if = lan.lan_interface(cfg)
        self.installed = (paths.systemd_dir / "xgw.service").exists()
        self.xray_bin = validate.find_xray(None, paths)
        self._xray_up: bool | None = None

    def run(self) -> list[Check]:
        groups: list[tuple[str, Callable[[], list[Check]]]] = [
            ("Система", self._system),
            ("Конфиг", self._config),
            ("Программы", self._programs),
            ("Xray", self._xray),
            ("Ядро", self._kernel),
            ("TUN", self._tun),
            ("Файрвол", self._firewall),
            ("NetworkManager", self._nm),
            ("Подсеть LAN", self._lan_subnet_conflict),
            ("Порты", self._ports),
            ("Xray API", self._xray_api),
            ("sing-box", self._singbox),
            ("Время", self._time),
            ("Сон", self._sleep),
            ("IPv6", self._ipv6),
            ("Службы", self._services),
            ("Журнал", self._journal),
            ("Панель", self._panel_login),
            ("Трафик проверок", self._budget),
        ]
        if self.net:
            groups += [("probe.url", self._probe), ("bootstrap DNS", self._bootstrap)]
        result: list[Check] = []
        for name, group in groups:
            try:
                result.extend(group())
            except Exception as exc:  # одна проверка не должна ронять остальные
                self.log.error("diag, проверка «%s»: %s", name, exc)
                result.append(Check(name, WARN, f"проверка не выполнена: {exc}"))
        return result

    # --- система и конфиг -------------------------------------------------------

    def _system(self) -> list[Check]:
        if not sys.platform.startswith("linux"):
            return [Check("Система", FAIL, "XGW работает только в Linux (Ubuntu 26.04)")]
        release: dict[str, str] = {}
        try:
            for line in self.os_release.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.partition("=")
                if sep:
                    release[key] = value.strip().strip('"')
        except OSError:
            pass
        name = release.get("PRETTY_NAME") or "неизвестная система"
        python = f"Python {sys.version_info.major}.{sys.version_info.minor}"
        result: list[Check] = []
        if release.get("ID") == "ubuntu" and release.get("VERSION_ID") == "26.04":
            result.append(Check("Система", OK, f"{name}, {python}"))
        else:
            result.append(Check(
                "Система", WARN, f"{name}, {python} — XGW проверялся только на Ubuntu 26.04"
            ))
        if not self.root:
            result.append(Check(
                "Права", WARN, "запущено без root — проверки ядра, файрвола и портов пропущены",
                "sudo xgw diag",
            ))
        return result

    def _config(self) -> list[Check]:
        path = self.paths.config_file
        if self.config_error:
            return [Check(
                "Конфиг", FAIL, self.config_error,
                f"sudo xgw install создаст {path} из примера; подписку можно добавить "
                "после установки в панели",
            )]
        result: list[Check] = []
        try:
            if path.stat().st_mode & 0o077:
                result.append(Check(
                    "Конфиг", WARN, f"{path} доступен другим пользователям, а в нём подписка",
                    f"sudo chmod 600 {path}",
                ))
        except OSError:
            pass
        if self.config_warnings:
            result.append(Check("Конфиг", WARN, "; ".join(self.config_warnings)))
        if not result:
            mode = f"сеть {self.lan_if} и эта машина" if self.lan_if else "только эта машина"
            result.append(Check("Конфиг", OK, f"{path} читается; режим — {mode}"))
        return result

    def _programs(self) -> list[Check]:
        required = ["ip", "systemctl"]
        if self.lan_if:
            required.append("nmcli")
        missing = [name for name in required if self.which(name) is None]
        later = [] if self.which("nft") is not None else ["nftables"]
        # DHCP раздаёт своя служба xgw-dhcp: нужна только программа из dnsmasq-base.
        if self.lan_if and self.which("dnsmasq") is None:
            later.append(dnsmasq.PACKAGE)
        if missing:
            return [Check(
                "Программы", FAIL, "не найдены: " + ", ".join(missing),
                "XGW рассчитан на Ubuntu Desktop с NetworkManager и systemd",
            )]
        if later:
            return [Check(
                "Программы", WARN, "пакеты " + ", ".join(later) + " не установлены",
                "sudo xgw install поставит их из apt",
            )]
        return [Check("Программы", OK, "nft, ip, systemctl" + (
            ", nmcli, dnsmasq" if self.lan_if else "") + " на месте")]

    # --- Xray -------------------------------------------------------------------

    def _xray(self) -> list[Check]:
        if self.xray_bin is None:
            return [Check(
                "Xray", WARN, f"не установлен ({self.paths.xray_bin})",
                "sudo xgw install загрузит его с GitHub и сверит SHA-256",
            )]
        version = binary.installed_version(self.xray_bin)
        if version is None:
            return [Check("Xray", FAIL, f"{self.xray_bin} не запускается", "sudo xgw update-xray")]
        text = ".".join(map(str, version))
        if version < binary.MIN_VERSION:
            return [Check(
                "Xray", FAIL,
                f"версия {text} ниже {binary.min_version_text()}: поля httpMethod в ней нет, "
                "серверы проверялись бы HEAD-запросом и «заморозка» осталась бы незамеченной",
                "sudo xgw update-xray",
            )]
        if not binary.has_string(self.xray_bin, b"httpMethod"):
            return [Check(
                "Xray", FAIL, f"версия {text}, но поля httpMethod в бинарнике нет",
                "sudo xgw update-xray",
            )]
        if version != binary.parse_version(XRAY_VERSION):
            # Другую версию XGW не использует (config.XRAY_VERSION); перед установкой это
            # не ошибка — установка поставит нужную.
            return [Check(
                "Xray", WARN if self.preinstall else FAIL,
                f"версия {text}, а XGW работает только с Xray {XRAY_VERSION}",
                "установка поставит нужную версию" if self.preinstall
                else "sudo xgw update-xray",
            )]
        return [Check("Xray", OK, f"версия {text}, GET-проверка (httpMethod) поддерживается")]

    # --- sing-box (второе ядро) ---------------------------------------------------

    def _singbox(self) -> list[Check]:
        """Бинарник нужной версии, конфиг, который он принимает, и отсутствие ошибок в его
        журнале. Выключенный (`core.mode = "xray"`) или не нужный подпискам — не ошибка."""
        if self.cfg.core.mode == "xray":
            return [Check("sing-box", OK, "выключен в [core] (mode = xray)")]
        path = singboxing.find_binary(None, self.paths)
        if path is None:
            return [Check(
                "sing-box", WARN,
                f"не установлен ({self.paths.singbox_bin}): серверы hysteria2, TUIC, AnyTLS и "
                "WireGuard пропускаются",
                "sudo xgw install или sudo xgw update-singbox",
            )]
        version = singboxing.installed_version(path)
        if version is None:
            return [Check("sing-box", FAIL, f"{path} не запускается", "sudo xgw update-singbox")]
        text = ".".join(map(str, version))
        if version != sbbinary.parse_version(SINGBOX_VERSION):
            return [Check(
                "sing-box", WARN if self.preinstall else FAIL,
                f"версия {text}, а XGW работает только с sing-box {SINGBOX_VERSION}",
                "установка поставит нужную версию" if self.preinstall
                else "sudo xgw update-singbox",
            )]
        result = [Check("sing-box", OK, f"версия {text}")]
        if not self.paths.singbox_config_file.exists():
            return result  # серверов для sing-box нет: служба не запущена, и это нормально
        applied = engine.read_json(self.paths.singbox_config_file)
        if applied is None:
            result.append(Check(
                "sing-box: конфиг", FAIL, f"{self.paths.singbox_config_file} не читается",
                "sudo xgw apply --now (конфиг соберётся заново)",
            ))
            return result
        ok, output = singboxing.validate_config(applied, path)
        lines = [line for line in output.splitlines() if line.strip()]
        if ok is False:
            result.append(Check(
                "sing-box: конфиг", FAIL,
                f"sing-box check не принял {self.paths.singbox_config_file}: "
                + (lines[-1] if lines else "ошибка"),
                "sudo xgw apply --now (конфиг соберётся заново)",
            ))
        else:
            bridges = len(singboxing.bridge_ports(applied))
            result.append(Check(
                "sing-box: конфиг", OK, f"принят sing-box check, мостов: {bridges}",
            ))
        if self.installed and self.root:
            errors = self.runner(
                ["journalctl", "-u", "xgw-singbox", "-p", "err", "-n", "20", "--no-pager",
                 "-o", "cat"], check=False,
            ).strip().splitlines()
            errors = [line for line in errors if line.strip() and not line.startswith("--")]
            if errors:
                result.append(Check(
                    "sing-box: журнал", WARN,
                    f"в журнале службы есть ошибки ({len(errors)}), последняя: "
                    + masking.mask_text(errors[-1])[:200],
                    "sudo journalctl -u xgw-singbox -p err -n 20",
                ))
        return result

    def xray_up(self) -> bool:
        if self._xray_up is None:
            try:
                metrics.fetch_metrics(self.cfg.xray.metrics_port)
                self._xray_up = True
            except Exception:
                self._xray_up = False
        return self._xray_up

    def _xray_api(self) -> list[Check]:
        if self.xray_bin is None or not (self.installed or self.xray_up()):
            return []  # до установки проверять нечего
        try:
            observatory = metrics.parse_observatory(
                metrics.fetch_metrics(self.cfg.xray.metrics_port)
            )
        except Exception as exc:
            return [Check(
                "Xray API", FAIL, f"метрики не отвечают: {exc}",
                "sudo systemctl status xgw-xray; sudo journalctl -u xgw-xray -n 30",
            )]
        try:
            engine.make_api(self.cfg, self.xray_bin).balancer_info(BALANCER_TAG)
        except Exception as exc:
            return [Check("Xray API", FAIL, f"API не отвечает: {exc}",
                          "sudo journalctl -u xgw-xray -n 30")]
        members = {tag: entry for tag, entry in observatory.items() if tag.startswith("proxy-")}
        alive = sum(1 for entry in members.values() if entry["alive"])
        level = OK if alive or not members else WARN
        return [Check(
            "Xray API", level,
            f"API и метрики отвечают; живых участников {alive} из {len(members)}",
            "" if level == OK else "sudo xgw probe --all покажет, что с серверами",
        )]

    # --- ядро и файрвол ---------------------------------------------------------

    def _kernel(self) -> list[Check]:
        if not self.root:
            return []
        if self.which("nft") is None:
            return [Check("Ядро", WARN, "nft не установлен — правила проверить нечем",
                          "sudo xgw install поставит nftables")]
        rules, _warnings = nft.build_rules(self.cfg, capture=True)
        if rules.empty:
            return [Check("Ядро", OK, "перехват выключен в конфиге — правила не нужны")]
        text = nft.render(rules) + nft.render6(rules)
        if self.which("unshare") is None:
            try:
                self.runner(["nft", "-c", "-f", "-"], input=text)
            except cmd.CommandError as exc:
                return [Check("Ядро", FAIL, f"nft не принимает правила: {_first_line(exc)}")]
            return [Check("Ядро", WARN, "синтаксис правил верен; ядро не проверено (нет unshare)")]
        try:
            # Отдельное пространство имён: правила загружаются по-настоящему
            # (нужные модули ядро подгружает само) и исчезают вместе с ним.
            self.runner(["unshare", "-n", "nft", "-f", "-"], input=text, timeout=30.0)
        except cmd.CommandError as exc:
            return [Check(
                "Ядро", FAIL, f"ядро не принимает правила перехвата: {_first_line(exc)}",
                "нужны модули nft_tproxy, nft_fib, nft_ct, nft_masq (пакет linux-modules-extra)",
            )]
        return [Check("Ядро", OK, "ядро принимает правила TPROXY (tproxy, fib, ct, masquerade)")]

    def _tun(self) -> list[Check]:
        """Интерфейс TUN — для трафика машины (capture.method = tun) или контейнеров Docker:
        нужен /dev/net/tun, на интерфейсе — адрес XGW, и ответы Xray не должен резать
        rp_filter."""
        cap = self.cfg.capture
        machine = cap.tun and cap.local
        if not (machine or engine.containers_tun(self.cfg)):
            return []
        result: list[Check] = []
        if not self.dev_tun.exists():
            return [Check(
                "TUN", FAIL, f"нет {self.dev_tun}: в ядре нет TUN, Xray не создаст интерфейс",
                "sudo modprobe tun (и добавьте tun в /etc/modules-load.d/xgw.conf)",
            )]
        whom = "" if machine else " — для контейнеров Docker"
        if self.root and self.installed:
            capture = Capture(
                self.cfg, self.paths, runner=self.runner, logger=self.log, proc_sys=self.proc_sys
            )
            problem = capture.tun_problem() if capture.mode() == "on" else ""
            if problem:
                result.append(Check(
                    "TUN", WARN if self.preinstall else FAIL, problem,
                    "установка подготовит интерфейс заново" if self.preinstall
                    else "sudo xgw net up",
                ))
        if not result:
            result.append(Check("TUN", OK, f"{self.dev_tun} есть; интерфейс {cap.tun_name}{whom}"))
        # Действует наибольшее из общего значения и значения интерфейса; своё значение XGW
        # обнуляет при создании интерфейса, так что решает общее.
        for where in ("all", cap.tun_name):
            if sysctl.read(f"net/ipv4/conf/{where}/rp_filter", self.proc_sys) == "1":
                result.append(Check(
                    "TUN", WARN,
                    f"net.ipv4.conf.{where}.rp_filter = 1 (строгий): ядро отбросит ответы Xray "
                    "из TUN, и трафик машины зависнет",
                    "sudo sysctl -w net.ipv4.conf.all.rp_filter=2 (и то же в /etc/sysctl.d/); "
                    "умолчание Ubuntu — 2",
                ))
                break
        return result

    def _firewall(self) -> list[Check]:
        if not self.root or self.which("nft") is None:
            return []
        result: list[Check] = []
        try:
            ruleset = json.loads(self.runner(["nft", "-j", "list", "ruleset"], timeout=30.0))
        except (cmd.CommandError, json.JSONDecodeError) as exc:
            return [Check("Файрвол", WARN, f"правила nftables не прочитаны: {_first_line(exc)}")]
        dropping: dict[str, list[str]] = {"forward": [], "input": []}
        docker = False
        for item in ruleset.get("nftables", []) if isinstance(ruleset, dict) else []:
            chain = item.get("chain") if isinstance(item, dict) else None
            if not chain or chain.get("table") in (nft.TABLE, nft.TABLE6):
                continue
            if str(chain.get("name", "")).startswith("DOCKER"):
                docker = True
            if chain.get("hook") in dropping and chain.get("policy") == "drop":
                dropping[chain["hook"]].append(f"{chain.get('family')} {chain.get('table')}")
        ufw_on = self.which("ufw") is not None and ufw.active(self.runner)
        wan_if = lan.effective_wan(self.cfg, self.runner)
        if ufw_on and self.lan_if:
            result.append(self._ufw(wan_if))
        elif ufw_on:
            result.append(Check("ufw", OK, "включён; трафику самой машины не мешает"))
        if docker and dropping["forward"] and self.lan_if:
            result.append(Check(
                "Docker", WARN,
                "ставит политику drop в FORWARD: устройства в обход VPN, ICMP и режим "
                "`xgw disable` не пройдут через шлюз",
                f"sudo iptables -I DOCKER-USER -i {self.lan_if} -j ACCEPT; "
                f"sudo iptables -I DOCKER-USER -o {self.lan_if} -m conntrack "
                "--ctstate RELATED,ESTABLISHED -j ACCEPT",
            ))
        elif dropping["forward"] and self.lan_if and not ufw_on:
            tables = ", ".join(sorted(set(dropping["forward"])))
            result.append(Check(
                "Файрвол", WARN,
                f"чужая цепочка forward с политикой drop ({tables}): форвардинг для устройств "
                "в обход VPN и ICMP может не пройти",
                f"разрешите в ней трафик с интерфейса {self.lan_if}",
            ))
        if dropping["input"] and self.lan_if and not ufw_on:
            tables = ", ".join(sorted(set(dropping["input"])))
            result.append(Check(
                "Файрвол", WARN,
                f"чужая цепочка input с политикой drop ({tables}): перехваченный трафик "
                f"устройств приходит в Xray как входящий с {self.lan_if}",
                f"разрешите в ней входящие с интерфейса {self.lan_if}",
            ))
        if self.runner(["systemctl", "is-enabled", "nftables.service"],
                       check=False).strip() == "enabled":
            result.append(Check(
                "nftables.service", WARN,
                "включена, а её конфиг начинается с flush ruleset: при её перезапуске правила "
                "XGW пропадут, пока демон не вернёт их (до одного шага watchdog)",
                "если своих правил в /etc/nftables.conf нет: sudo systemctl disable nftables",
            ))
        containers = self.cfg.capture.containers and (
            self.cfg.capture.lan or self.cfg.capture.local)
        has_docker = docker or bool(lan.container_links(nft.CONTAINER_IFS))
        if has_docker and not containers and (self.cfg.capture.lan or self.cfg.capture.local):
            result.append(Check(
                "Docker", WARN,
                "контейнеры выходят в интернет мимо VPN: capture.containers = false",
                "впишите capture.containers = true в /etc/xgw/config.toml",
            ))
        if not result:
            text = "ufw и Docker перехвату не мешают"
            if has_docker and containers:
                text += "; контейнеры Docker — через VPN"
            result.append(Check("Файрвол", OK, text))
        return result

    def _ufw(self, wan_if: str) -> Check:
        """ufw включён, есть LAN: хватает ли правил, чтобы устройства вышли в сеть."""
        listed = self.runner(["ufw", "status"], timeout=20.0, check=False)
        before = ufw.before_rules(self.paths.root)
        mark = self.cfg.capture.mark_proxy
        missing: list[str] = []
        if f"on {self.lan_if}" not in listed:
            missing += ["sudo ufw " + " ".join(rule) for rule in ufw.wanted(self.lan_if, wan_if)]
        if self.cfg.capture.lan and not ufw.has_tproxy_rule(before, self.lan_if, mark):
            missing.append(
                f"в {before} перед строкой «{ufw.ANCHOR}» — "
                f"«{ufw.tproxy_rule(self.lan_if, mark)}», затем sudo ufw reload"
            )
        if not missing:
            return Check("ufw", OK, f"включён, правила для {self.lan_if} есть")
        text = (
            f"включён и запрещает входящие: устройства за {self.lan_if} останутся без "
            "интернета (перехваченные пакеты ufw отбрасывает в ufw-not-local)"
        )
        if self.installed:
            return Check("ufw", FAIL, text, "; ".join(missing))
        return Check("ufw", WARN, text, "sudo xgw install добавит правила (спросит): "
                     + "; ".join(missing))

    # --- NetworkManager ---------------------------------------------------------

    def _nm(self) -> list[Check]:
        if self.which("nmcli") is None:
            if self.lan_if:
                return []  # уже FAIL в «Программах»
            return [Check("NetworkManager", OK, "не установлен; для режима «только эта машина» "
                          "он не нужен")]
        manager = nm.Nm(self.runner)
        if not manager.running():
            level = FAIL if self.lan_if else WARN
            return [Check("NetworkManager", level, "не запущен",
                          "sudo systemctl enable --now NetworkManager")]
        devices = manager.devices()
        wan_if = lan.effective_wan(self.cfg, self.runner)
        result: list[Check] = []
        if not wan_if:
            result.append(Check("WAN", WARN, "маршрута по умолчанию нет — интернет не подключён?"))
        elif not self.lan_if:
            result.append(Check("NetworkManager", OK, f"запущен; WAN — {wan_if}"))
        if not self.lan_if:
            return result
        if self.lan_if == wan_if:
            return [Check(
                "LAN", FAIL, f"network.lan_if = {self.lan_if} — это интерфейс выхода в интернет",
                "LAN — вторая сетевая карта, к которой подключён Wi-Fi-роутер",
            )]
        device = devices.get(self.lan_if)
        if device is None:
            names = ", ".join(sorted(name for name in devices if name != "lo")) or "нет"
            return [Check("LAN", FAIL, f"интерфейса {self.lan_if} нет; есть: {names}",
                          "исправьте network.lan_if в config.toml")]
        if device.state == "unmanaged":
            return [Check(
                "LAN", FAIL, f"NetworkManager не управляет {self.lan_if} (unmanaged)",
                "в Ubuntu Server сетью управляет networkd: задайте в /etc/netplan/*.yaml "
                "renderer: NetworkManager и выполните sudo netplan apply",
            )]
        if device.type != "ethernet":
            result.append(Check("LAN", WARN, f"{self.lan_if} — не Ethernet ({device.type}); "
                                "XGW рассчитан на проводную карту к роутеру"))
        shared = [profile.name for profile, info in nm.bound_profiles(manager, self.lan_if)
                  if info.get("ipv4.method") == "shared"
                  and info.get("connection.autoconnect") != "no"]
        if shared:
            result.append(Check(
                "LAN", WARN,
                "профиль " + ", ".join(shared) + " в режиме shared: NetworkManager поднимает "
                "свой dnsmasq и NAT, они конфликтуют с XGW",
                "установка лишит такой профиль автоподключения",
            ))
        if device.connection == nm.PROFILE:
            result.append(Check("LAN", OK, f"{self.lan_if}: профиль {nm.PROFILE} активен"))
        elif any(profile.name == nm.PROFILE for profile in manager.profiles()):
            result.append(Check(
                "LAN", WARN, f"профиль {nm.PROFILE} есть, но на {self.lan_if} активен "
                f"«{device.connection or 'никакой'}» ({device.state})",
                "проверьте кабель к роутеру; sudo nmcli connection up xgw-lan",
            ))
        else:
            result.append(Check("LAN", OK, f"{self.lan_if} управляется NetworkManager "
                                f"({device.state}); профиль {nm.PROFILE} создаст установка"))
        return result

    def _lan_subnet_conflict(self) -> list[Check]:
        """network.lan_address не должен пересекаться с сетью провайдера и любой другой
        сетью машины: иначе у шлюза два интерфейса в одной подсети."""
        if not self.lan_if or self.which("ip") is None:
            return []
        conflicts = lan.subnet_conflicts(self.cfg, self.runner)
        if not conflicts:
            address = lan.gateway(self.cfg)
            network = address.network if address is not None else self.cfg.network.lan_address
            return [Check(
                "Подсеть LAN", OK, f"{network} не пересекается с другими сетями машины"
            )]
        return [Check(
            "Подсеть LAN", FAIL,
            lan.conflict_text(
                self.cfg, conflicts, self.paths.config_file,
                lan.free_lan_address(self.cfg, self.runner),
            ),
        )]

    # --- порты, время, сон, IPv6 ------------------------------------------------

    def _ports(self) -> list[Check]:
        if not sys.platform.startswith("linux"):
            return []
        ports = {
            "tproxy": self.cfg.capture.tproxy_port, "api": self.cfg.xray.api_port,
            "metrics": self.cfg.xray.metrics_port, "socks": self.cfg.xray.socks_port,
            "http": self.cfg.xray.http_port,
        }
        busy = [f"{name} {port}" for name, port in ports.items() if not self.port_free(port)]
        if not busy:
            return [Check("Порты", OK, "служебные порты Xray свободны")]
        if self.xray_up():
            return [Check("Порты", OK, "служебные порты заняты работающим Xray")]
        pattern = "|".join(str(port) for port in ports.values())
        return [Check(
            "Порты", FAIL, "заняты другой программой: " + ", ".join(busy),
            f"sudo ss -ltnp | grep -E ':({pattern})\\b' — освободите порт или смените его "
            "в [xray] / [capture]",
        )]

    def _time(self) -> list[Check]:
        if self.which("timedatectl") is None:
            return []
        synced = self.runner(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"], check=False
        ).strip()
        users = [name for name in nft.TIME_USERS if _user_exists(name)]
        notes = [f"служба времени — {users[0]}"] if users else []
        unit = TIME_UNITS.get(users[0], "chrony") if users else "chrony"
        if _chrony_uses_nts():
            notes.append(f"chrony использует NTS (TCP {nft.NTS_KE_PORT} идёт мимо перехвата)")
        result: list[Check] = []
        if synced == "yes":
            result.append(Check("Время", OK, "; ".join(["часы синхронизированы", *notes])))
        else:
            result.append(Check(
                "Время", WARN,
                "; ".join(["часы не синхронизированы: Reality не подключится при расхождении "
                           "времени", *notes]),
                f"timedatectl status; sudo systemctl restart {unit}",
            ))
        if not users and self.cfg.capture.local:
            result.append(Check(
                "Время", WARN,
                "не найден пользователь службы времени (" + ", ".join(nft.TIME_USERS) + "): её "
                "запросы попадут в перехват и без VPN время не синхронизируется",
            ))
        return result

    def _sleep(self) -> list[Check]:
        if not self.cfg.network.disable_sleep:
            return [Check("Сон", OK, "disable_sleep = false — сон оставлен на ваше усмотрение")]
        if not sleep.wanted(self.cfg):
            return [Check("Сон", OK, "роутера нет (network.lan_if пуст) — сон не трогается")]
        awake = sleep.unmasked(self.paths.systemd_dir)
        if not awake:
            return [Check("Сон", OK, "цели сна замаскированы")]
        text = "не замаскированы: " + ", ".join(awake) + " — уснувший шлюз оставит дом без сети"
        advice = "sudo xgw install замаскирует их" if not self.installed else (
            "sudo systemctl mask " + " ".join(awake))
        return [Check("Сон", WARN, text, advice + f"; GNOME: {sleep.GNOME_HINT}")]

    def _ipv6_proxy(self) -> list[Check]:
        """network.ipv6 = proxy: IPv6 самой машины должен идти через Xray."""
        if not self.cfg.capture.local:
            return [Check(
                "IPv6", WARN,
                "network.ipv6 = proxy, но capture.local = false: IPv6 машины не перехватывается",
                "включите capture.local или верните network.ipv6 = off",
            )]
        if not sysctl.ipv6_usable():
            return [Check("IPv6", OK, "IPv6 в ядре выключен — проксировать нечего")]
        if not self.installed or not self.root:
            return [Check("IPv6", OK, "IPv6 машины пойдёт через Xray (network.ipv6 = proxy)")]
        info = Capture(
            self.cfg, self.paths, runner=self.runner, logger=self.log, proc_sys=self.proc_sys
        ).describe()
        if info["mode"] != "on":
            return [Check(
                "IPv6", WARN, "перехват снят — IPv6 идёт напрямую, мимо VPN", "sudo xgw enable"
            )]
        if (info["loaded"] is False and not info.get("tun_problem")) or not info["ipv6"]:
            if self.preinstall:
                return [Check("IPv6", WARN, "IPv6 проксируется, но его правила не загружены",
                              "установка загрузит их заново")]
            return [Check(
                "IPv6", FAIL, "IPv6 проксируется, но его правила не загружены", "sudo xgw net up"
            )]
        return [Check("IPv6", OK, "IPv6 самой машины идёт через Xray")]

    def _ipv6(self) -> list[Check]:
        if self.cfg.network.ipv6_proxy:
            return self._ipv6_proxy()
        if self.which("ip") is None:
            return []
        try:
            entries = json.loads(
                self.runner(["ip", "-j", "-6", "addr", "show", "scope", "global"]) or "[]"
            )
        except (cmd.CommandError, json.JSONDecodeError):
            return []
        devices = sorted({
            entry.get("ifname", "") for entry in entries
            if isinstance(entry, dict) and entry.get("addr_info")
        } - {""})
        if not devices:
            return [Check("IPv6", OK, "глобальных IPv6-адресов нет — мимо перехвата идти нечему")]
        where = "глобальный IPv6-адрес на " + ", ".join(devices)
        text = where + ": по IPv6 трафик идёт мимо VPN"
        if not self.installed:
            return [Check("IPv6", WARN, text, "sudo xgw install отключит IPv6 на WAN")]
        if self.cfg.capture.local and self.root:
            # IPv6 машины держит фаервол (v6_guard), а не только настройка NetworkManager.
            chains6 = nft.loaded_chains(self.runner, "ip6", nft.TABLE6)
            if chains6 is not None and "v6_guard" in chains6:
                return [Check("IPv6", OK, where + ": наружу IPv6 машины не выпускает фаервол "
                              "(v6_guard)")]
            if chains6 is not None:
                return [Check(
                    "IPv6", FAIL, text + " — защита IPv6 (v6_guard) не загружена",
                    "sudo xgw net up — загрузит её; отключить IPv6 на WAN заново: sudo xgw install",
                )]
        # Не «nmcli connection modify»: у профиля из netplan это сбрасывает привязку к
        # карте (nm.netplan_defined). Установка выбирает безопасный способ сама.
        return [Check(
            "IPv6", FAIL, text,
            "sudo xgw install — отключит IPv6 на WAN заново и скажет, если не сможет",
        )]

    def _panel_login(self) -> list[Check]:
        """Пункт «Войти заново» у ярлыка «XGW» спрашивает пароль через pkexec. Без него
        войти в панель заново можно только ссылкой из `sudo xgw panel`. Смотрится там,
        где есть рабочий стол (xdg-open): на сервере ярлык открывать некому."""
        if not sys.platform.startswith("linux") or not self.cfg.panel.enabled:
            return []
        if self.which("xdg-open") is None:
            return []
        if self.which("pkexec") is None:
            return [Check(
                "Панель", WARN,
                "нет pkexec: «Войти заново» у ярлыка «XGW» не спросит пароль, войти в панель "
                "заново можно будет только ссылкой из sudo xgw panel",
                "sudo apt install pkexec",
            )]
        return [Check(
            "Панель", OK, "войти заново — правая кнопка по ярлыку «XGW», «Войти заново»",
        )]

    # --- службы и бюджет --------------------------------------------------------

    def _services(self) -> list[Check]:
        if not self.installed:
            return []
        # Служба sing-box запускается, только когда есть его конфиг (ConditionPathExists).
        units = [
            unit for unit in UNITS
            if unit != SINGBOX_UNIT or self.paths.singbox_config_file.exists()
        ] + ([dnsmasq.UNIT] if self.lan_if else [])
        down = [
            unit for unit in units
            if self.runner(["systemctl", "is-active", unit], check=False).strip() != "active"
        ]
        result: list[Check] = []
        if down and self.preinstall:
            result.append(Check(
                "Службы", WARN, "не работают: " + ", ".join(down),
                "установка запустит их заново",
            ))
        elif down:
            result.append(Check(
                "Службы", FAIL, "не работают: " + ", ".join(down),
                "sudo systemctl status " + " ".join(down),
            ))
        else:
            result.append(Check("Службы", OK, ", ".join(
                unit.removesuffix(".service") for unit in units) + " работают"))
        if self.root:
            capture = Capture(
                self.cfg, self.paths, runner=self.runner, logger=self.log, proc_sys=self.proc_sys
            )
            info = capture.describe()
            # Не готов только интерфейс TUN — правила на месте: об этом строка «TUN».
            missing = info["loaded"] is False and not info.get("tun_problem")
            if info["mode"] == "on" and missing and self.preinstall:
                result.append(Check("Перехват", WARN, "включён, но правила не загружены",
                                    "установка загрузит их заново"))
            elif info["mode"] == "on" and missing:
                result.append(Check("Перехват", FAIL, "включён, но правила не загружены",
                                    "sudo xgw net up"))
            elif info["mode"] in ("off", "open"):
                result.append(Check("Перехват", WARN, "снят — трафик идёт напрямую, мимо VPN",
                                    "sudo xgw enable"))
            elif info["mode"] == "on" and info.get("inbound_missing"):
                held = ("трафик заблокирован, мимо VPN ничего не уходит" if info.get("blocked")
                        else "трафик идёт напрямую, мимо VPN")
                result.append(Check(
                    "Перехват", WARN,
                    f"включён, но ждёт inbound в Xray: {info['inbound_missing']} — {held}",
                    "sudo xgw apply --now",
                ))
            elif info["mode"] == "on":
                result.append(Check("Перехват", OK, "включён, правила загружены"))
        return result

    def _journal(self) -> list[Check]:
        """Уровни записей демона в журнале systemd (log.py): предупреждения должны
        находиться по `journalctl -u xgw -p warning`. Префикс уровня демон ставит, только
        когда его stderr — тот самый поток журнала, чей номер systemd кладёт в
        JOURNAL_STREAM (log.journal_stream). Проверка смотрит и это условие у работающей
        службы, и сами записи: строки с WARNING и ERROR, сохранённые с уровнем info."""
        if not self.installed or not self.root:
            return []
        pid = self.runner(["systemctl", "show", "xgw", "-p", "MainPID", "--value"],
                          check=False).strip()
        if not pid.isdigit() or pid == "0":
            return []  # служба не работает — об этом строка «Службы»
        environ = (self.proc / pid / "environ").read_bytes().split(b"\0")
        stream = next((item.split(b"=", 1)[1].decode("ascii", "replace") for item in environ
                       if item.startswith(b"JOURNAL_STREAM=")), "")
        info = os.stat(self.proc / pid / "fd" / "2")
        actual = f"{info.st_dev}:{info.st_ino}"
        output = self.runner(["journalctl", "-u", "xgw", "-n", "500", "-o", "json", "--no-pager"],
                             check=False)
        wrong = 0
        for line in output.splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = record.get("MESSAGE")
            if (isinstance(message, str) and record.get("_TRANSPORT") == "stdout"
                    and record.get("PRIORITY") == "6"
                    and (" WARNING " in message or " ERROR " in message)):
                wrong += 1
        details = f"JOURNAL_STREAM={stream or 'нет'}, stderr демона {actual}"
        if wrong:
            return [Check(
                "Журнал", WARN,
                f"{wrong} предупреждений и ошибок демона записаны с уровнем info — "
                f"`journalctl -p warning` их не найдёт ({details})",
                "пришлите эту строку разработчику; перезапуск: sudo systemctl restart xgw",
            )]
        if stream != actual:
            return [Check("Журнал", WARN, f"stderr демона — не поток журнала ({details}): "
                                          "предупреждения запишутся с уровнем info")]
        return [Check("Журнал", OK, "предупреждения демона — с уровнем warning "
                                    "(journalctl -u xgw -p warning)")]

    def _budget(self) -> list[Check]:
        members, spares = self.cfg.filters.max_members, 0
        quotas: dict = {}
        size: int | None = None
        nodes: list[dict] = []
        if self.paths.db_file.exists():
            try:
                store = Store(self.paths.db_file)
                try:
                    nodes = store.all_nodes()
                    quotas = json.loads(store.get_meta("quota") or "{}")
                    size = status.measured_probe_size(store, self.cfg.probe.url)
                finally:
                    store.close()
                if nodes:
                    members = sum(1 for node in nodes if node["role"] == "proxy")
                    spares = len(nodes) - members
            except Exception as exc:
                self.log.debug("состояние не прочитано: %s", exc)
        quotas = quotas if isinstance(quotas, dict) else {}
        spend: dict[str, int] | None = None
        if nodes:
            # Как демон проверяет серверы: лимитированные запасные — коротким запросом,
            # кандидаты в резервный выход — изредка; расход квоты — с множителями.
            reserve = builder.reserve_tag(engine.read_json(self.paths.xray_config_file))
            plan = status.scan_plan(
                self.cfg, *status.node_entries(self.cfg, nodes, quotas, reserve)
            )
            budget = status.probe_budget(
                self.cfg, members, len(plan.full), size,
                cheap=len(plan.cheap), candidates=len(plan.candidates),
                speed_round_mb=status.speed_round_mb(self.cfg, plan.members),
            )
            spend = status.quota_spend(self.cfg, plan, budget.size)
        else:
            budget = status.probe_budget(
                self.cfg, members, spares, size, speed_round_mb=members * self.cfg.speed.max_mb
            )
        month = budget.everything * status.MONTH_DAYS / status.GB
        text = (
            f"~{budget.total / status.MB:.0f} МБ в сутки при {members} участниках и "
            f"{spares} запасных (лимит {self.cfg.probe.max_daily_probe_mb} МБ); вместе со "
            f"сквозной проверкой{' и замером скорости' if budget.speed else ''} — "
            f"~{budget.everything / status.MB:.0f} МБ в сутки, "
            f"~{month:.0f} ГБ в месяц (проба {budget.size} Б, "
            f"{'измерено' if budget.measured else 'по оценке'})"
        )
        if budget.guessed:
            text += (
                "; размер пробы пока неизвестен — probe.url ещё не ответил ни разу, цифра "
                "уточнится после первой удачной проверки"
            )
        for name, share in status.quota_share(budget, quotas, spend).items():
            text += f"; за месяц это ~{share:.0f} % квоты подписки «{name}»"
            if spend is not None:
                text += " (с множителями серверов)"
        warnings = status.budget_warnings(self.cfg, budget, quotas, spend)
        if warnings:
            return [Check("Трафик проверок", WARN, "; ".join(warnings) + f". Сейчас: {text}")]
        return [Check("Трафик проверок", OK, text)]

    # --- сеть -------------------------------------------------------------------

    def _mark(self) -> int | None:
        return engine.bypass_mark(self.cfg, self.log)

    def _probe(self) -> list[Check]:
        url = self.cfg.probe.url
        agent = self.cfg.probe.user_agent
        expected = probe_bytes(url)
        mark = self._mark()
        result: list[Check] = []
        started = time.monotonic()
        try:
            reply = fetch.fetch_url(
                url, mark=mark, timeout=15.0, retries=0,
                bootstrap=self.cfg.dns.bootstrap if mark is not None else None,
                headers={"User-Agent": agent},
            )
        except fetch.FetchError as exc:
            result.append(Check(
                "probe.url", WARN, f"напрямую не скачивается: {exc}",
                "не страшно, если скачивается через серверы: sudo xgw probe --all",
            ))
        else:
            size, seconds = len(reply.body), time.monotonic() - started
            if reply.status != 200 or (expected and size < expected):
                result.append(Check(
                    "probe.url", WARN,
                    f"напрямую: HTTP {reply.status}, {size} Б" + (
                        f" из {expected}" if expected else ""),
                    "не страшно, если через серверы файл скачивается целиком; иначе "
                    + target.ADVICE,
                ))
            else:
                result.append(Check("probe.url", OK, f"напрямую: {size} Б за {seconds:.1f} с"))
        if engine.healthy_http_in(self.cfg) is not None:
            started = time.monotonic()
            download = probes.http_get_via_proxy(
                "127.0.0.1", self.cfg.xray.http_port, url, silence=5.0, max_total=30.0,
                user_agent=agent,
            )
            if download.ok:
                result.append(Check(
                    "probe.url", OK,
                    f"через Xray: {download.downloaded} Б за "
                    f"{time.monotonic() - started:.1f} с",
                ))
            else:
                result.append(Check(
                    "probe.url", FAIL, f"через Xray не скачивается: {download.error}",
                    "sudo xgw probe --all покажет серверы по одному",
                ))
                result.extend(self._probe_target(mark))
        return result

    def _probe_target(self, mark: int | None) -> list[Check]:
        """Через Xray probe.url не скачивается. Серверы это или сам адрес пробы? Та же
        проверка, что у демона (watch/target.py): участники и несколько запасных
        опрашиваются собственной пробой; одинаковая ошибка у всех плюс контрольные
        запросы — значит, не отвечает адрес, и серверы ни при чём."""
        applied = engine.read_json(self.paths.xray_config_file)
        password, _ports = builder.probe_state(applied)
        verdicts: dict[str, str] = {}
        try:
            store = Store(self.paths.db_file)
            try:
                verdicts = {tag: entry["verdict"] for tag, entry in store.scans().items()}
            finally:
                store.close()
        except Exception as exc:
            self.log.debug("сканы не прочитаны: %s", exc)
        nodes = target.sample(builder.applied_nodes(applied), verdicts)
        if not password or not nodes:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(nodes))) as pool:
            results = list(pool.map(
                lambda info: scan.scan_node(info, self.cfg, probe_pass=password), nodes
            ))
        diagnosis = target.diagnose(
            results,
            base_ping=lambda: target.base_ping(self.cfg),
            direct=lambda: target.direct_signature(self.cfg, mark),
        )
        if not diagnosis.down:
            return []
        return [Check("probe.url", FAIL, diagnosis.text, target.ADVICE)]

    def _bootstrap(self) -> list[Check]:
        name = _domain_to_resolve(self.cfg)
        if not name:
            return []
        mark = self._mark()
        good: list[str] = []
        bad: list[str] = []
        for resolver in self.cfg.dns.bootstrap:
            try:
                fetch.resolve_domain(name, [resolver], mark=mark)
                good.append(resolver)
            except Exception as exc:
                bad.append(f"{resolver} ({exc})")
        total = len(self.cfg.dns.bootstrap)
        if not good:
            return [Check(
                "bootstrap DNS", FAIL,
                "ни один резолвер не отвечает: домены серверов не разрешить — " + "; ".join(bad),
                "проверьте dns.bootstrap; обычный DNS провайдера: udp://<адрес>",
            )]
        if bad:
            return [Check("bootstrap DNS", WARN,
                          f"отвечают {len(good)} из {total}; не отвечают: " + "; ".join(bad))]
        return [Check("bootstrap DNS", OK, f"отвечают все {total}")]


def _first_line(exc: Exception) -> str:
    lines = [line for line in str(exc).splitlines() if line.strip()]
    return lines[0] if lines else type(exc).__name__


def _user_exists(name: str) -> bool:
    try:
        import pwd
    except ImportError:
        return False
    try:
        pwd.getpwnam(name)
    except KeyError:
        return False
    return True


def _chrony_uses_nts(directory: Path = CHRONY_DIR) -> bool:
    """Есть ли в конфиге chrony источник с ключом nts."""
    try:
        files = [path for path in directory.rglob("*") if path.is_file()]
    except OSError:
        return False
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            words = line.split("#", 1)[0].split()
            if words[:1] and words[0] in ("server", "pool", "peer") and "nts" in words[2:]:
                return True
    return False


def _domain_to_resolve(cfg: Config) -> str:
    """Имя для проверки резолверов — из URL конфигурации: лишних запросов XGW не делает."""
    candidates = [cfg.probe.url, *(sub.url for sub in cfg.subscriptions)]
    for url in candidates:
        host = urlsplit(url).hostname or ""
        if host and not host.replace(".", "").isdigit() and ":" not in host:
            return host
    return ""
