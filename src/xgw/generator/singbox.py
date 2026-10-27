"""Второе ядро — sing-box: конфиг, мост к Xray и проверка.

Схема (ASSUMPTIONS, пп. 197–204). Xray остаётся единственной точкой входа: перехват (TPROXY,
TUN), локальные прокси, проверочные входы probe-*, балансировщик, burstObservatory и закрепление
основного сервера работают как раньше. Серверы, которые ведёт sing-box, подключены к Xray так:

    Xray (outbound proxy-… / spare-…, socks) → 127.0.0.1:<порт> → sing-box (inbound sb-in-…,
    socks) → сервер (outbound sb-out-…, с меткой mark_bypass: мимо перехвата)

Для каждого сервера, который умеет sing-box, в его конфиг заранее заведены варианты — по одному
входу и выходу на профиль (generator/profiles.py): обычный (d), с дроблением TLS (f), с
мультиплексированием и паддингом (m). Сменить профиль — значит заменить outbound Xray через API
(другой порт моста): конфиг sing-box не меняется, соединения не рвутся. Проверено на sing-box
1.14.3: перечитывание конфига (SIGHUP) рвёт ВСЕ его соединения, поэтому оно нужно только когда
меняется состав серверов, и откладывается, пока через sing-box идёт трафик (engine.assemble).

Мост — без метки: цепочка loopback_guard отклоняет пакеты с меткой mark_bypass к 127.0.0.0/8.
Метку ставит sing-box на своих сокетах к серверам (routing_mark).

Проверка сертификата не отключается: `tls.insecure` в конфиг не попадает (parsers/).
"""

from __future__ import annotations

import copy
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .. import masking
from ..config import Config, service_ports
from ..model import ServerNode
from ..paths import Paths, secret_tempdir
from . import validate as checks

BRIDGE_USER = "xgw"
FRAGMENT_DELAY = "30ms"  # пауза между сегментами ClientHello (tls.fragment_fallback_delay)
QUIC_TYPES = ("hysteria2", "hysteria", "tuic")
_IN_TAG = re.compile(r"^sb-in-([0-9a-f]{8})-([dfm])$")
_USER = re.compile(rf"^{BRIDGE_USER}-([dfm])$")
LOCAL = "127.0.0.1"


@dataclass
class Plan:
    """Желаемое состояние sing-box: конфиг и порты мостов."""

    config: dict
    ports: dict[tuple[str, str], int] = field(default_factory=dict)  # (отпечаток, буква) → порт
    password: str = ""

    def letters(self, fingerprint: str) -> set[str]:
        return {letter for fp, letter in self.ports if fp == fingerprint}

    def fingerprints(self) -> set[str]:
        return {fp for fp, _letter in self.ports}


def tag_in(fingerprint: str, letter: str) -> str:
    return f"sb-in-{fingerprint}-{letter}"


def tag_out(fingerprint: str, letter: str) -> str:
    return f"sb-out-{fingerprint}-{letter}"


# --- что умеет сервер в sing-box ----------------------------------------------------


def _tls_blocks(spec) -> list[dict]:
    blocks = []
    for body in (spec.main, *spec.extra):
        tls = body.get("tls")
        if isinstance(tls, dict) and tls.get("enabled"):
            blocks.append(tls)
    return blocks


def fragmentable(spec) -> bool:
    """Можно ли резать ClientHello: TLS поверх TCP (QUIC и WireGuard — нет)."""
    kind = str(spec.main.get("type") or "")
    if spec.endpoint or kind in QUIC_TYPES:
        return False
    transport = spec.main.get("transport")
    if isinstance(transport, dict) and transport.get("type") == "quic":
        return False
    return bool(_tls_blocks(spec))


def mux_capable(spec) -> bool:
    """Можно ли включить мультиплексирование: vmess, trojan, shadowsocks, vless без flow."""
    main = spec.main
    kind = str(main.get("type") or "")
    if spec.endpoint or main.get("multiplex") or main.get("plugin") or main.get("detour"):
        return False
    if kind == "vless":
        return not main.get("flow")
    return kind in ("vmess", "trojan", "shadowsocks")


def variant_letters(spec, cfg: Config) -> list[str]:
    letters = ["d"]
    if cfg.fragment.mode != "off" and fragmentable(spec):
        letters.append("f")
    if cfg.core.mux_padding and mux_capable(spec):
        letters.append("m")
    return letters


def _variant(spec, letter: str, fingerprint: str, mark: int) -> tuple[list[dict], bool]:
    """Outbound'ы варианта (главный первым) и признак «это endpoint»."""
    main = copy.deepcopy(spec.main)
    extras = copy.deepcopy(spec.extra)
    if letter in ("f", "m"):
        for tls in _tls_blocks(type(spec)(main=main, endpoint=spec.endpoint, extra=extras)):
            tls["record_fragment"] = True
            if letter == "f":
                tls["fragment"] = True
                # По умолчанию sing-box ждёт между сегментами 500 мс, и рукопожатие тянулось бы
                # полсекунды; Xray-дробление ждёт 10–20 мс (generator/fragment.py).
                tls["fragment_fallback_delay"] = FRAGMENT_DELAY
    if letter == "m":
        main["multiplex"] = {"enabled": True, "protocol": "h2mux", "padding": True}
    main["tag"] = tag_out(fingerprint, letter)
    if extras:
        renames = {item["tag"]: f"{main['tag']}-{item['tag']}" for item in extras}
        for item in extras:
            item["tag"] = renames[item["tag"]]
        if main.get("detour") in renames:
            main["detour"] = renames[main["detour"]]
    for body in (main, *extras):
        body["routing_mark"] = mark
    return [main, *extras], spec.endpoint


# --- разбор применённого конфига -----------------------------------------------------


def bridge_ports(config: Mapping | None) -> dict[tuple[str, str], int]:
    """(отпечаток, буква) → порт моста из конфига sing-box."""
    result: dict[tuple[str, str], int] = {}
    if not isinstance(config, Mapping):
        return result
    for inbound in config.get("inbounds") or []:
        if not isinstance(inbound, Mapping):
            continue
        match = _IN_TAG.match(str(inbound.get("tag") or ""))
        port = inbound.get("listen_port")
        if match and isinstance(port, int):
            result[(match.group(1), match.group(2))] = port
    return result


def bridge_password(config: Mapping | None) -> str:
    if not isinstance(config, Mapping):
        return ""
    for inbound in config.get("inbounds") or []:
        users = inbound.get("users") if isinstance(inbound, Mapping) else None
        if isinstance(users, list) and users and isinstance(users[0], Mapping):
            password = users[0].get("password")
            if isinstance(password, str) and password:
                return password
    return ""


def clash_secret(config: Mapping | None) -> str:
    experimental = config.get("experimental") if isinstance(config, Mapping) else None
    clash = experimental.get("clash_api") if isinstance(experimental, Mapping) else None
    value = clash.get("secret") if isinstance(clash, Mapping) else None
    return value if isinstance(value, str) else ""


def bridge_variant(outbound: Mapping) -> str:
    """Буква варианта, если outbound Xray — мост к sing-box; иначе пусто."""
    if outbound.get("protocol") != "socks":
        return ""
    servers = (outbound.get("settings") or {}).get("servers")
    first = servers[0] if isinstance(servers, list) and servers else None
    if not isinstance(first, Mapping) or first.get("address") != LOCAL:
        return ""
    users = first.get("users")
    user = users[0] if isinstance(users, list) and users and isinstance(users[0], Mapping) else {}
    match = _USER.match(str(user.get("user") or ""))
    return match.group(1) if match else ""


def bridge_outbound(port: int, letter: str, password: str) -> dict:
    """Outbound Xray к варианту sing-box. Без sockopt.mark: см. docstring модуля."""
    return {
        "protocol": "socks",
        "settings": {"servers": [{
            "address": LOCAL, "port": port,
            "users": [{"user": f"{BRIDGE_USER}-{letter}", "pass": password}],
        }]},
    }


# --- сборка конфига ------------------------------------------------------------------


def _reserved_ports(cfg: Config) -> set[int]:
    return set(service_ports(cfg).values())


def build(
    cfg: Config,
    nodes: Sequence[ServerNode],
    hosts: Mapping[str, Sequence[str]],
    *,
    previous: Mapping | None = None,
    avoid: Collection[int] = (),
    skip: Collection[str] = (),
) -> Plan | None:
    """Конфиг sing-box для серверов, которые он умеет. None — вести через него некого.

    previous — применённый конфиг: порты, пароль и секрет Clash API берутся из него, чтобы
    новая сборка не меняла того, что уже работает. avoid — занятые порты (проверки Xray);
    skip — отпечатки, которых в sing-box не заводить (проверка конфига их отвергла)."""
    chosen = [
        node for node in sorted(nodes, key=lambda item: item.fingerprint)
        if node.singbox is not None and not node.keep_tag and node.fingerprint not in skip
    ]
    if not chosen:
        return None
    mark = cfg.capture.mark_bypass
    password = bridge_password(previous) or secrets.token_urlsafe(24)
    secret = clash_secret(previous) or secrets.token_urlsafe(24)
    old_ports = bridge_ports(previous)
    taken = _reserved_ports(cfg) | set(avoid)
    wanted: list[tuple[str, str]] = []
    bodies: dict[tuple[str, str], tuple[list[dict], bool]] = {}
    for node in chosen:
        assert node.singbox is not None
        for letter in variant_letters(node.singbox, cfg):
            key = (node.fingerprint, letter)
            wanted.append(key)
            bodies[key] = _variant(node.singbox, letter, node.fingerprint, mark)
    ports: dict[tuple[str, str], int] = {}
    for key in wanted:
        port = old_ports.get(key)
        if isinstance(port, int) and 0 < port < 65536 and port not in taken:
            ports[key] = port
            taken.add(port)
    candidate = cfg.core.port_base
    for key in wanted:
        if key in ports:
            continue
        while candidate in taken:
            candidate += 1
        if candidate > 65535:
            raise ValueError("закончились порты для sing-box — уменьшите core.port_base")
        ports[key] = candidate
        taken.add(candidate)

    inbounds, outbounds, endpoints, rules = [], [], [], []
    for key in wanted:
        fingerprint, letter = key
        items, endpoint = bodies[key]
        (endpoints if endpoint else outbounds).append(items[0])
        outbounds.extend(items[1:])
        inbounds.append({
            "type": "socks", "tag": tag_in(fingerprint, letter), "listen": LOCAL,
            "listen_port": ports[key],
            "users": [{"username": f"{BRIDGE_USER}-{letter}", "password": password}],
        })
        rules.append({
            "inbound": [tag_in(fingerprint, letter)], "action": "route",
            "outbound": tag_out(fingerprint, letter),
        })
    rules.append({"action": "reject"})
    used = {node.address for node in chosen}
    for node in chosen:
        assert node.singbox is not None
        used.update(str(item.get("server")) for item in node.singbox.extra if item.get("server"))
    config: dict = {
        "log": {"level": "warn"},
        "dns": {"servers": [{
            "type": "hosts", "tag": "hosts",
            "predefined": {host: list(ips) for host, ips in sorted(hosts.items()) if host in used},
        }]},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {"rules": rules, "default_domain_resolver": "hosts"},
        "experimental": {"clash_api": {
            "external_controller": f"{LOCAL}:{cfg.core.api_port}", "secret": secret,
        }},
    }
    if endpoints:
        config["endpoints"] = endpoints
    if not outbounds:
        # sing-box без единого outbound'а (только WireGuard) не стартует: нужен хотя бы один.
        config["outbounds"] = [{"type": "block", "tag": "block"}]
    return Plan(config=config, ports=ports, password=password)


# --- проверка конфига ----------------------------------------------------------------


def find_binary(explicit: str | Path | None = None, paths: Paths | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    env_bin = os.environ.get("XGW_SINGBOX_BIN")
    if env_bin:
        candidates.append(Path(env_bin))
    if paths is not None:
        candidates.append(paths.singbox_bin)
    found = shutil.which("sing-box")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def installed_version(
    bin_path: Path | str, *, timeout: float = 15.0,
) -> tuple[int, int, int] | None:
    """Версия по `sing-box version`; None — узнать не удалось."""
    try:
        proc = subprocess.run(
            [str(bin_path), "version"], capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"sing-box version v?(\d+)\.(\d+)\.(\d+)", proc.stdout or "")
    return tuple(int(group) for group in match.groups()) if match else None  # type: ignore[return-value]


def _run_check(config: dict, bin_path: Path) -> tuple[bool, str]:
    verdict, output = _check_once(config, bin_path)
    return verdict is True, output


def _check_once(config: dict, bin_path: Path) -> tuple[bool | None, str]:
    """Вердикт `sing-box check`; None — вердикта нет (не запустился или завис)."""
    import json

    # Права 0600; в /run/xgw (в памяти), а не в /tmp на диске: в конфиге — ключи серверов.
    fd, tmp_name = tempfile.mkstemp(prefix="xgw-sbcheck-", suffix=".json", dir=secret_tempdir())
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False)
        try:
            proc = subprocess.run(
                [str(bin_path), "--disable-color", "check", "-c", str(tmp)],
                capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            return None, "sing-box check: таймаут 60 с"
        except OSError as exc:
            return None, f"sing-box check не запустился: {exc}"
        output = masking.mask_text(
            (proc.stdout or "") + (proc.stderr or ""), masking.collect_secrets(config),
        )
        return proc.returncode == 0, output.strip().replace(str(tmp), "<config>")
    finally:
        tmp.unlink(missing_ok=True)


def validate_config(config: dict, bin_path: Path | None) -> tuple[bool | None, str]:
    """True/False — вердикт `sing-box check`; None — sing-box не найден."""
    if bin_path is None:
        return None, "sing-box не найден — проверка sing-box check пропущена"
    return _run_check(config, bin_path)


def find_invalid(
    nodes: Iterable[ServerNode], cfg: Config, bin_path: Path,
) -> dict[str, str]:
    """Отпечаток → причина для серверов, чей конфиг установленный sing-box не принимает.

    Проверяется обычный вариант каждого сервера (остальные отличаются полями, которые
    проверены) — чтобы один битый сервер не лишал sing-box всей подписки. Отвергнутые раньше
    этим же sing-box не проверяются снова, остальные — делением пополам (validate.narrow)."""
    core = checks.binary_id(bin_path)
    invalid: dict[str, str] = {}
    unknown: list[tuple[str, list[dict], bool, str]] = []
    for node in nodes:
        if node.singbox is None:
            continue
        items, endpoint = _variant(node.singbox, "d", node.fingerprint, cfg.capture.mark_bypass)
        key = checks.rejected_key(items, core)
        reason = checks.known_rejection(key)
        if reason is None:
            unknown.append((node.fingerprint, items, endpoint, key))
        else:
            invalid[node.fingerprint] = reason

    def check(chunk: list[tuple[str, list[dict], bool, str]]) -> tuple[bool | None, str]:
        endpoints: list[dict] = []
        outbounds: list[dict] = []
        for _fingerprint, items, endpoint, _key in chunk:
            if endpoint:
                endpoints.append(items[0])
                outbounds.extend(items[1:])
            else:
                outbounds.extend(items)
        config: dict = {"log": {"level": "warn"}}
        if endpoints:
            config["endpoints"] = endpoints
            config["outbounds"] = [{"type": "block", "tag": "block"}, *outbounds]
        else:
            config["outbounds"] = outbounds
        return _check_once(config, bin_path)

    for index, output in checks.narrow(unknown, check).items():
        fingerprint, _items, _endpoint, key = unknown[index]
        lines = [line for line in output.splitlines() if line.strip()]
        reason = lines[-1].rsplit(": ", 1)[-1] if lines else "ошибка проверки"
        invalid[fingerprint] = reason
        checks.remember_rejection(key, reason)
    return invalid
