"""Профили NetworkManager (раздел 6.2): LAN-профиль xgw-lan и IPv6 на WAN.

LAN-карта получает статический адрес без шлюза по умолчанию; прежние профили
этого интерфейса не удаляются, а запоминаются и лишаются автоподключения —
`xgw uninstall` возвращает их как были. Режим ipv4.method shared не
используется: NetworkManager поднял бы свой dnsmasq и NAT.

К профилям обращаемся только по UUID: имена повторяются (NetworkManager сам
создаёт «Wired connection 1» для каждой карты).
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from . import cmd, lan

PROFILE = "xgw-lan"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@dataclass(frozen=True)
class Device:
    name: str
    type: str
    state: str
    connection: str


@dataclass(frozen=True)
class Profile:
    name: str
    uuid: str
    type: str
    device: str  # где профиль сейчас активен; пусто — нигде
    filename: str


def split_terse(line: str) -> list[str]:
    """Строка `nmcli -t`: поля через «:», двоеточие и обратная косая черта в
    значении экранированы обратной косой чертой."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


class Nm:
    """Тонкая обёртка над nmcli."""

    def __init__(self, runner: cmd.Runner = cmd.run) -> None:
        self.runner = runner

    def nmcli(self, *args: str, timeout: float = 30.0) -> str:
        return self.runner(["nmcli", *args], timeout=timeout)

    def running(self) -> bool:
        try:
            return self.nmcli("-t", "-f", "RUNNING", "general").strip() == "running"
        except cmd.CommandError:
            return False

    def devices(self) -> dict[str, Device]:
        result: dict[str, Device] = {}
        for line in self.nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device").splitlines():
            fields = split_terse(line)
            if len(fields) >= 4:
                result[fields[0]] = Device(*fields[:4])
        return result

    def profiles(self) -> list[Profile]:
        result: list[Profile] = []
        text = self.nmcli("-t", "-f", "NAME,UUID,TYPE,DEVICE,FILENAME", "connection", "show")
        for line in text.splitlines():
            fields = split_terse(line)
            if len(fields) >= 5 and _UUID_RE.fullmatch(fields[1]):
                result.append(Profile(*fields[:5]))
        return result

    def get(self, uuid: str, *fields: str) -> dict[str, str]:
        """Значения полей профиля: {«ipv6.method»: «auto», …}."""
        text = self.nmcli("-t", "-f", ",".join(fields), "connection", "show", uuid)
        result: dict[str, str] = {}
        for line in text.splitlines():
            parts = split_terse(line)
            if len(parts) >= 2:
                result[parts[0]] = ":".join(parts[1:])
        return result

    def active_uuid(self, device: str) -> str:
        """UUID профиля, активного на устройстве; пусто — устройство не подключено
        или не управляется NetworkManager."""
        try:
            text = self.nmcli("-g", "GENERAL.CON-UUID", "device", "show", device)
        except cmd.CommandError:
            return ""
        value = text.strip()
        return value if _UUID_RE.fullmatch(value) else ""

    def modify(self, uuid: str, *settings: str) -> None:
        self.nmcli("connection", "modify", uuid, *settings)

    def up(self, uuid: str, device: str = "", *, wait: int = 20) -> None:
        """Активирует профиль. wait=0 — не дожидаясь результата (DHCP может идти долго)."""
        args = ["--wait", str(wait), "connection", "up", uuid]
        if device:
            args += ["ifname", device]
        self.nmcli(*args, timeout=40.0)

    def delete(self, uuid: str) -> None:
        self.nmcli("connection", "delete", uuid)

    def reapply(self, device: str) -> None:
        self.nmcli("device", "reapply", device)


def lan_settings(cfg: Config) -> list[str]:
    """Свойства профиля xgw-lan."""
    return [
        "ipv4.method", "manual",
        "ipv4.addresses", cfg.network.lan_address.strip(),
        # Шлюз по умолчанию — только через WAN: маршрут через LAN увёл бы трафик
        # самой машины в домашнюю сеть.
        "ipv4.never-default", "yes",
        "ipv6.method", "disabled",
        "connection.autoconnect", "yes",
        # Выше, чем у профилей по умолчанию: и после «nmcli connection up» другого
        # профиля, и после перезагрузки карта вернётся к xgw-lan.
        "connection.autoconnect-priority", "100",
    ]


def bound_profiles(nm: Nm, lan_if: str) -> list[tuple[Profile, dict[str, str]]]:
    """Чужие профили, привязанные к LAN-интерфейсу, с их настройками."""
    result: list[tuple[Profile, dict[str, str]]] = []
    for profile in nm.profiles():
        if profile.name == PROFILE:
            continue
        info = nm.get(
            profile.uuid, "connection.interface-name", "connection.autoconnect", "ipv4.method"
        )
        if info.get("connection.interface-name") == lan_if:
            result.append((profile, info))
    return result


def setup_lan(
    nm: Nm, cfg: Config, backup_dir: Path, previous: dict | None = None
) -> tuple[dict, list[str]]:
    """Создаёт (или обновляет) профиль xgw-lan и отключает прежние профили карты.

    Возвращает запись для журнала установки и предупреждения. previous — запись
    прошлой установки: исходное состояние чужих профилей берётся из неё, иначе
    повторная установка запомнила бы уже отключённые профили как «исходные».
    """
    lan_if = lan.lan_interface(cfg)
    warnings: list[str] = []
    known = {item["uuid"]: item for item in (previous or {}).get("disabled", [])}
    disabled: list[dict] = list(known.values())
    for profile, info in bound_profiles(nm, lan_if):
        if profile.uuid not in known:
            disabled.append(
                {
                    "uuid": profile.uuid,
                    "name": profile.name,
                    "autoconnect": info.get("connection.autoconnect", "yes"),
                    "active": profile.device == lan_if,
                }
            )
            _backup_keyfile(profile, backup_dir)
        if info.get("connection.autoconnect") != "no":
            nm.modify(profile.uuid, "connection.autoconnect", "no")

    ours = [profile for profile in nm.profiles() if profile.name == PROFILE]
    if ours:
        uuid = ours[0].uuid
        nm.modify(uuid, "connection.interface-name", lan_if, *lan_settings(cfg))
        for extra in ours[1:]:
            nm.delete(extra.uuid)
    else:
        nm.nmcli(
            "connection", "add", "type", "ethernet", "con-name", PROFILE, "ifname", lan_if,
            *lan_settings(cfg),
        )
        created = [profile for profile in nm.profiles() if profile.name == PROFILE]
        if not created:
            raise cmd.CommandError(f"nmcli: профиль {PROFILE} не появился после создания")
        uuid = created[0].uuid
    try:
        nm.up(uuid, lan_if)
    except cmd.CommandError as exc:
        # Без кабеля профиль не активируется; NetworkManager поднимет его сам,
        # когда появится связь.
        warnings.append(
            f"профиль {PROFILE} создан, но не активирован (кабель к роутеру подключён?): {exc}"
        )
    return {"lan_if": lan_if, "profile": uuid, "disabled": disabled}, warnings


def _backup_keyfile(profile: Profile, backup_dir: Path) -> None:
    """Копия файла профиля — на случай ручного восстановления."""
    source = Path(profile.filename) if profile.filename else None
    if source is None or not source.is_file():
        return
    target = backup_dir / "nm" / f"{profile.uuid}.nmconnection"
    with contextlib.suppress(OSError):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, 0o600)  # в профиле могут быть пароли 802.1X


def restore_lan(nm: Nm, record: dict) -> list[str]:
    """Удаляет xgw-lan и возвращает прежние профили карты. Возвращает предупреждения."""
    warnings: list[str] = []
    profiles = nm.profiles()
    present = {profile.uuid for profile in profiles}
    for profile in profiles:
        if profile.name == PROFILE:
            try:
                nm.delete(profile.uuid)
            except cmd.CommandError as exc:
                warnings.append(f"профиль {PROFILE} не удалён: {exc}")
    for item in record.get("disabled", []):
        uuid = item.get("uuid", "")
        if uuid not in present:
            continue  # профиль удалили после установки — возвращать нечего
        try:
            nm.modify(uuid, "connection.autoconnect", item.get("autoconnect", "yes"))
        except cmd.CommandError as exc:
            warnings.append(f"профиль «{item.get('name', uuid)}» не восстановлен: {exc}")
            continue
        if item.get("active"):
            # Не дожидаясь результата: без роутера с DHCP на том конце активация не
            # завершится, а автоподключение профилю уже возвращено.
            with contextlib.suppress(cmd.CommandError):
                nm.up(uuid, record.get("lan_if", ""), wait=0)
    return warnings


def netplan_defined(filename: str) -> bool:
    """Профиль описан в /etc/netplan/*.yaml (человеком или cloud-init), а не создан
    NetworkManager.

    NetworkManager в Ubuntu хранит профили в netplan: свои — как netplan-NM-<uuid>,
    описанные в YAML — как netplan-<имя>. Любой `nmcli connection modify` такого
    профиля переписывает его в /etc/netplan/90-NM-<uuid>.yaml, и NetworkManager 1.46
    (Ubuntu 24.04) теряет при этом привязку к карте: match по MAC и set-name
    превращаются в `match: {}`. После перезагрузки профиль WAN встаёт на любую карту —
    на ВМ он занял карту LAN, и шлюз остался без интернета (проверка WIN-03).
    """
    name = os.path.basename(filename)
    return name.startswith("netplan-") and not name.startswith("netplan-NM-")


def wan_ipv6_off(
    nm: Nm, device: str, previous: dict | None = None
) -> tuple[dict | None, list[str]]:
    """ipv6.method disabled в профиле WAN: иначе приложения самой машины уйдут
    мимо перехвата по IPv6. Возвращает запись для журнала (None — менять нечего).

    Профиль из netplan (netplan_defined) не меняется: при ipv6.method ignore
    NetworkManager IPv6 карты не трогает, и его выключает sysctl — в записи тогда
    "sysctl": True, и disable_ipv6 ставит вызывающий."""
    uuid = nm.active_uuid(device) if device else ""
    if not uuid:
        return previous, [
            f"WAN-интерфейс {device or '(не найден)'} не управляется NetworkManager — "
            "IPv6 на нём не отключён, проверьте `xgw diag`"
        ]
    method = nm.get(uuid, "ipv6.method").get("ipv6.method", "")
    if method == "disabled":
        return previous, []
    if previous and previous.get("uuid") == uuid:
        record = previous
    else:
        record = {"device": device, "uuid": uuid, "ipv6_method": method or "auto"}
    profile = next((item for item in nm.profiles() if item.uuid == uuid), None)
    if profile is not None and netplan_defined(profile.filename):
        if method != "ignore":
            return previous, [
                f"IPv6 на {device} не отключён: профиль «{profile.name}» описан в netplan, а "
                "его правка через NetworkManager сбросила бы привязку профиля к карте. Если "
                f"у провайдера есть IPv6, выключите его в /etc/netplan для {device} "
                "(dhcp6: false, accept-ra: false, link-local: []) и повторите установку"
            ]
        return {**record, "sysctl": True}, []
    warnings: list[str] = []
    try:
        nm.modify(uuid, "ipv6.method", "disabled")
    except cmd.CommandError as exc:
        return previous, [f"IPv6 в профиле WAN не отключён: {exc}"]
    try:
        nm.reapply(device)
    except cmd.CommandError as exc:
        warnings.append(
            f"IPv6 в профиле WAN отключён, но применится после переподключения {device}: {exc}"
        )
    return record, warnings


def restore_wan(nm: Nm, record: dict) -> list[str]:
    """Возвращает ipv6.method профиля WAN. Запись с "sysctl" профиль не меняла —
    её disable_ipv6 возвращает sysctl."""
    uuid = record.get("uuid", "")
    if record.get("sysctl") or not uuid or uuid not in {item.uuid for item in nm.profiles()}:
        return []
    method, device = record.get("ipv6_method", "auto"), record.get("device", "")
    try:
        nm.modify(uuid, "ipv6.method", method)
    except cmd.CommandError as exc:
        return [f"IPv6 в профиле WAN не возвращён: {exc}"]
    try:
        nm.reapply(device)
    except cmd.CommandError as exc:
        # Так бывает после перезагрузки: NetworkManager отказывается применять профиль к
        # уже подключённой карте («Can't reapply changes to connection.interface-name»).
        return [
            f"IPv6 в профиле WAN возвращён ({method}), но на {device} включится после "
            f"перезагрузки: {exc}"
        ]
    return []
