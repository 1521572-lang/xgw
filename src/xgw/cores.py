"""Обновление ядер Xray и sing-box из панели: проверка выпусков на GitHub, обновление с
проверкой на этом шлюзе и возврат к прежней версии (ASSUMPTIONS, п. 234).

XGW проверен на одной версии каждого ядра (config.XRAY_VERSION, config.SINGBOX_VERSION): их
ставит установка. Более новый выпуск с GitHub ставится только кнопкой в панели (или
`xgw cores update`) и только если прошёл проверку на этом шлюзе: версия, `xray run -test`
(`sing-box check`) на рабочем конфиге, запуск, ответ ядра и запрос в интернет через серверы. Не
прошёл — прежний бинарник возвращается сам. Прошёл — версия записывается как «принятая шлюзом»:
`xgw diag` её не считает ошибкой, переустановка XGW её не откатывает. Прежний бинарник остаётся
рядом (/opt/xgw/xray.prev) — для кнопки «Вернуть прежнюю версию»; сутки после обновления демон
следит за ядром и, если оно перестало отвечать, а откат конфига на last-good не помог, сам
запускает возврат.

Каталоги ядер в /opt/xgw демону только для чтения (ProtectSystem=strict в xgw.service), поэтому
обновление и возврат выполняет отдельная служба xgw-core.service (Type=oneshot): демон кладёт
задание в /run/xgw/core-request.json и запускает её. Итог, принятые версии и наблюдение пишет
только задание — в /var/lib/xgw/cores.json; что нашлось на GitHub, пишет демон — в
cores-check.json.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import re
import shutil
import time
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from . import engine, fetch, log
from .config import SINGBOX_VERSION, XRAY_VERSION, Config
from .generator import singbox as singboxing
from .net import cmd
from .paths import LockTimeout, Paths, atomic_write_json, file_lock
from .sbcore import binary as sbbinary
from .store import Store
from .watch import checks, scan
from .xraycore import binary
from .xraycore.binary import BinaryError

CORES = ("xray", "sing-box")
TITLES = {"xray": "Xray", "sing-box": "sing-box"}
ACTIONS = ("update", "rollback")
UNIT = "xgw-core.service"
CHECK_EVERY = 24 * 3600.0  # проверка выпусков на GitHub — раз в сутки
CHECK_RETRY = 3 * 3600.0  # не удалась — повтор через 3 часа
WATCH_SECONDS = 24 * 3600.0  # сколько демон следит за ядром после обновления
JOB_STALE = 30 * 60.0  # задание «идёт» дольше — служба оборвана, новое можно начинать
E2E_WAIT = 45.0  # сколько ждать, пока запрос через серверы пройдёт с новым ядром
E2E_PAUSE = 5.0
PER_PAGE = 30  # выпусков в одном ответе GitHub: новейшие идут первыми
DELAY_TAGS = 6  # сколько серверов sing-box проверять через его Clash API
REMEMBER = 20  # о скольких версиях помнить, что о них уже сообщали
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "xgw-updater"}
_TAG = re.compile(r"[vV]?\d+\.\d+\.\d+")


class JobError(Exception):
    """Задание не выполнено; текст — для события и панели."""


# --- версии и каталоги ------------------------------------------------------------


def version_text(version: tuple[int, int, int] | None) -> str:
    return ".".join(map(str, version)) if version else ""


def parse(text: str) -> tuple[int, int, int] | None:
    """Версия из «26.10.21» или тега «v26.10.21»; None — не три числа через точку."""
    if not isinstance(text, str) or not _TAG.fullmatch(text.strip()):
        return None
    return binary.parse_version(text)


def baseline(core: str) -> str:
    """Версия, на которой проверен XGW: её ставит установка."""
    return XRAY_VERSION if core == "xray" else SINGBOX_VERSION


def core_dir(paths: Paths, core: str) -> Path:
    return paths.xray_dir if core == "xray" else paths.singbox_dir


def core_bin(paths: Paths, core: str) -> Path:
    return paths.xray_bin if core == "xray" else paths.singbox_bin


def prev_dir(paths: Paths, core: str) -> Path:
    """Каталог прежней рабочей версии: /opt/xgw/xray.prev, /opt/xgw/sing-box.prev."""
    directory = core_dir(paths, core)
    return directory.with_name(directory.name + ".prev")


def read_version(core: str, path: Path) -> tuple[int, int, int] | None:
    if not path.exists():
        return None
    if core == "xray":
        return binary.installed_version(path)
    return singboxing.installed_version(path)


# --- файлы состояния ---------------------------------------------------------------


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_state(paths: Paths) -> dict:
    return _read(paths.cores_state_file)


def save_state(paths: Paths, state: dict) -> None:
    atomic_write_json(paths.cores_state_file, state, mode=0o644)


def load_check(paths: Paths) -> dict:
    return _read(paths.cores_check_file)


def _core_state(state: dict, core: str) -> dict:
    entry = state.get(core)
    return entry if isinstance(entry, dict) else {}


def accepted(paths: Paths, core: str) -> tuple[int, int, int] | None:
    """Версия, которую шлюз принял после обновления из панели; None — такой нет."""
    return parse(str(_core_state(load_state(paths), core).get("accepted") or ""))


def allowed(paths: Paths, core: str, version: tuple[int, int, int] | None) -> bool:
    """Годится ли установленная версия: проверенная XGW либо принятая шлюзом."""
    if version is None:
        return False
    return version == parse(baseline(core)) or version == accepted(paths, core)


def keeps(paths: Paths, core: str, version: tuple[int, int, int] | None) -> bool:
    """Оставить ли установке лежащее ядро: проверенная версия либо принятая шлюзом, если она не
    старше проверенной (новый выпуск XGW со свежей проверенной версией ставит её)."""
    wanted = parse(baseline(core))
    if version is None or wanted is None:
        return False
    return version == wanted or (version == accepted(paths, core) and version > wanted)


def forget(paths: Paths, core: str) -> None:
    """Установка или `xgw update-xray` поставили проверенную версию: принятая, прежняя и
    наблюдение больше ни к чему."""
    state = load_state(paths)
    if core in state:
        state.pop(core, None)
        with contextlib.suppress(OSError):
            save_state(paths, state)
    shutil.rmtree(prev_dir(paths, core), ignore_errors=True)


def previous(paths: Paths, core: str) -> str:
    """Прежняя рабочая версия, к которой можно вернуться; пусто — её нет."""
    entry = _core_state(load_state(paths), core)
    text = str(entry.get("previous") or "")
    binary_name = core_bin(paths, core).name
    return text if text and (prev_dir(paths, core) / binary_name).exists() else ""


def watching(paths: Paths, core: str, now: float) -> bool:
    """Идут ли сутки наблюдения после обновления — и есть ли к чему вернуться."""
    entry = _core_state(load_state(paths), core)
    return float(entry.get("watch_until") or 0) > now and bool(previous(paths, core))


def job_active(paths: Paths, now: float) -> bool:
    """Задание ждёт службу или выполняется: ядро сейчас перезапускается — демон не трогает его."""
    with contextlib.suppress(OSError):
        if now - paths.cores_request_file.stat().st_mtime < JOB_STALE:
            return True
    job = load_state(paths).get("job")
    if not isinstance(job, dict) or job.get("state") != "running":
        return False
    return now - float(job.get("started") or 0) < JOB_STALE


# --- задание для службы xgw-core -------------------------------------------------


def start(
    paths: Paths,
    core: str,
    action: str,
    *,
    version: str = "",
    reason: str = "panel",
    runner: Callable[..., str] = cmd.run,
    now: Callable[[], float] = time.time,
) -> str:
    """Кладёт задание и запускает службу xgw-core. Пусто — запущено, иначе почему нет."""
    if core not in CORES or action not in ACTIONS:
        return "ожидается ядро xray или sing-box и действие update или rollback"
    if action == "update" and parse(version) is None:
        return f"версия {TITLES[core]} — три числа через точку, а не «{version}»"
    if job_active(paths, now()):
        return "уже идёт обновление или возврат ядра — дождитесь итога"
    request = {"core": core, "action": action, "version": version, "reason": reason, "at": now()}
    atomic_write_json(paths.cores_request_file, request, mode=0o600)
    try:
        runner(["systemctl", "start", "--no-block", UNIT], timeout=30.0)
    except (cmd.CommandError, OSError) as exc:
        paths.cores_request_file.unlink(missing_ok=True)
        return f"служба {UNIT} не запустилась: {exc}"
    return ""


def take_request(paths: Paths) -> dict | None:
    """Задание из /run/xgw/core-request.json. Файл убирает само задание (Job.run), когда уже
    записало «идёт»: иначе между ними панель на миг видела бы итог прошлого задания."""
    try:
        request = json.loads(paths.cores_request_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        request = None
    if not isinstance(request, dict):
        paths.cores_request_file.unlink(missing_ok=True)
        return {}
    return request


# --- проверка выпусков на GitHub ---------------------------------------------------


@dataclass
class Offer:
    version: str
    prerelease: bool
    published: str  # дата выпуска, как её отдаёт GitHub (ISO 8601)


def _api(core: str) -> str:
    return binary.RELEASES_API if core == "xray" else sbbinary.RELEASES_API


def routes(cfg: Config, mark: int | None) -> list[dict]:
    """Как ходить на GitHub: напрямую (сокетом с меткой мимо перехвата, как `xgw update-xray`),
    а если не вышло — через http-вход Xray, то есть через серверы VPN."""
    direct = {"mark": mark, "bootstrap": cfg.dns.bootstrap if mark is not None else None}
    return [direct, {"proxy": ("127.0.0.1", cfg.xray.http_port)}]


def try_routes(attempt: Callable[[dict], object], ways: Sequence[dict]):
    """Первый удавшийся путь: (результат, путь). Не удалось ни одним — ошибка последнего."""
    errors: list[str] = []
    for way in ways:
        try:
            return attempt(way), way
        except (BinaryError, fetch.FetchError, OSError) as exc:
            errors.append(str(exc))
    raise BinaryError("; ".join(dict.fromkeys(errors)) or "некуда обращаться")


def fetch_releases(core: str, route: dict, *, timeout: float = 20.0) -> list[dict]:
    result = fetch.fetch_url(
        f"{_api(core)}?per_page={PER_PAGE}", headers=HEADERS, timeout=timeout, retries=1, **route,
    )
    if result.status != 200:
        raise BinaryError(f"GitHub API вернул HTTP {result.status}")
    try:
        data = json.loads(result.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise BinaryError("GitHub API вернул не JSON") from exc
    if not isinstance(data, list):
        raise BinaryError("GitHub API вернул неожиданный ответ")
    return [item for item in data if isinstance(item, dict)]


def tag_present(core: str, version: str, route: dict) -> bool | None:
    """Есть ли выпуск с этим тегом: True, False (404 — разработчики его убрали) или None
    (не узнать: сеть, лимит запросов)."""
    try:
        result = fetch.fetch_url(
            f"{_api(core)}/tags/v{version}", headers=HEADERS, timeout=20.0, retries=1, **route,
        )
    except fetch.FetchError:
        return None
    if result.status == 200:
        return True
    return False if result.status == 404 else None


def _downloadable(core: str, item: dict, platform: tuple[str, str]) -> bool:
    """Есть ли в выпуске файл для этой машины и чем сверить его SHA-256."""
    goos, machine = platform
    try:
        if core == "xray":
            release = binary.release_from_api(item)
            asset = binary.pick_asset(release, goos, machine)
            return asset is not None and asset + ".dgst" in release.assets
        sb_release = sbbinary.release_from_api(item)
        name = sbbinary.asset_name(sb_release.tag, goos, machine)
        if name is None or name not in sb_release.assets:
            return False
        sbbinary.expected_sha256(sb_release, name, goos, machine)
    except BinaryError:
        return False
    return True


def pick_offer(
    core: str,
    releases: Sequence[dict],
    installed: tuple[int, int, int] | None,
    platform: tuple[str, str],
) -> Offer | None:
    """Новейший выпуск новее установленного. Xray — и предварительные (сам 26.10.21
    предварительный), sing-box — только стабильные: его предварительные — альфы и беты, где
    меняются поля конфига (решение заказчика 24.10.2026). Черновики не в счёт."""
    best: tuple[tuple[int, int, int], Offer] | None = None
    for item in releases:
        prerelease = bool(item.get("prerelease"))
        if item.get("draft") or (core == "sing-box" and prerelease):
            continue
        version = parse(str(item.get("tag_name") or ""))
        if version is None or (core == "xray" and version < binary.MIN_VERSION):
            continue
        if installed is not None and version <= installed:
            continue
        if not _downloadable(core, item, platform):
            continue
        if best is None or version > best[0]:
            offer = Offer(version_text(version), prerelease, str(item.get("published_at") or ""))
            best = (version, offer)
    return best[1] if best else None


def check_due(paths: Paths, now: float) -> bool:
    record = load_check(paths)
    wait = CHECK_RETRY if record.get("error") else CHECK_EVERY
    return now - float(record.get("at") or 0) >= wait


def check(
    cfg: Config,
    paths: Paths,
    installed: dict[str, tuple[int, int, int] | None],
    *,
    mark: int | None = None,
    platform: tuple[str, str] | None = None,
    now: Callable[[], float] = time.time,
) -> tuple[dict, list[tuple[str, bool]]]:
    """Смотрит выпуски на GitHub и пишет cores-check.json. Возвращает запись и события
    (текст, уведомлять ли): о новом выпуске — один раз на версию, об убранной с GitHub
    установленной версии — один раз на версию и с уведомлением."""
    previous_record = load_check(paths)
    announced = list(previous_record.get("announced") or [])
    warned = list(previous_record.get("warned") or [])
    platform = platform or binary.platform_pair()
    ways = routes(cfg, mark)
    record: dict = {"at": now(), "error": ""}
    events: list[tuple[str, bool]] = []
    errors: list[str] = []
    for core in CORES:
        current = installed.get(core)
        entry: dict = {
            "installed": version_text(current), "latest": None, "withdrawn": False, "error": "",
        }
        record[core] = entry
        if current is None:
            continue  # ядра нет: ставит его установка, а не проверка обновлений
        try:
            releases, way = try_routes(lambda route, core=core: fetch_releases(core, route), ways)
        except BinaryError as exc:
            entry["error"] = str(exc)
            errors.append(f"{TITLES[core]}: {exc}")
            continue
        offer = pick_offer(core, releases, current, platform)
        entry["latest"] = asdict(offer) if offer else None
        text = version_text(current)
        listed = any(parse(str(item.get("tag_name") or "")) == current for item in releases)
        if not listed:
            # В последних выпусках установленной версии нет: старая — или убрана с GitHub,
            # как 26.10.10 (корневые сертификаты со взломанными ключами, п. 226).
            entry["withdrawn"] = tag_present(core, text, way) is False
        title = TITLES[core]
        if offer and f"{core} {offer.version}" not in announced:
            announced.append(f"{core} {offer.version}")
            kind = " (предварительный выпуск)" if offer.prerelease else ""
            events.append((
                f"на GitHub вышел {title} {offer.version}{kind} — обновить можно в панели, "
                "карточка «Ядра»: шлюз проверит его и при сбое вернёт прежнюю версию", False,
            ))
        if entry["withdrawn"] and f"{core} {text}" not in warned:
            warned.append(f"{core} {text}")
            events.append((
                f"установленный {title} {text} убран с GitHub его разработчиками — так бывает, "
                "когда в выпуске находят опасную ошибку. Обновите ядро в панели, карточка "
                "«Ядра»", True,
            ))
    record["error"] = "; ".join(errors)
    record["announced"] = announced[-REMEMBER:]
    record["warned"] = warned[-REMEMBER:]
    atomic_write_json(paths.cores_check_file, record, mode=0o644)
    return record, events


# --- для панели ----------------------------------------------------------------------


def panel_state(
    paths: Paths, installed: dict[str, str], *, singbox_shown: bool, now: float,
) -> dict:
    """Карточка «Ядра»: что стоит, что есть на GitHub, к чему можно вернуться, идёт ли
    задание и чем кончилось последнее."""
    state, record = load_state(paths), load_check(paths)
    rows = []
    for core in CORES:
        if core == "sing-box" and not singbox_shown:
            continue
        entry = _core_state(state, core)
        found = record.get(core) if isinstance(record.get(core), dict) else {}
        current = installed.get(core) or ""
        latest = found.get("latest") if isinstance(found.get("latest"), dict) else None
        newer = latest is not None and (parse(str(latest.get("version") or "")) or (0, 0, 0)) > (
            parse(current) or (0, 0, 0)
        )
        rejected = entry.get("rejected") if isinstance(entry.get("rejected"), dict) else None
        rows.append({
            "core": core,
            "title": TITLES[core],
            "installed": current,
            "baseline": baseline(core),
            # Стоит версия новее проверенной, принятая шлюзом после обновления из панели.
            "accepted": bool(current) and current == entry.get("accepted")
            and current != baseline(core),
            "updated": entry.get("updated"),
            "latest": latest if newer else None,
            "previous": previous(paths, core),
            "watch_until": entry.get("watch_until") if watching(paths, core, now) else 0,
            "withdrawn": bool(found.get("withdrawn")) and found.get("installed") == current,
            "rejected": rejected,
        })
    job = state.get("job") if isinstance(state.get("job"), dict) else None
    return {
        "rows": rows,
        "checked": record.get("at"),
        "error": record.get("error") or "",
        "job": job,
        "active": job_active(paths, now),
    }


# --- обновление и возврат (служба xgw-core, `xgw cores update|rollback`) -------------


class Adapter:
    """Что задание делает с одним ядром; тесты подменяют его целиком."""

    core = ""

    def __init__(self, cfg: Config, paths: Paths) -> None:
        self.cfg = cfg
        self.paths = paths

    def version(self, path: Path) -> tuple[int, int, int] | None:
        return read_version(self.core, path)

    def release(self, version: str, route: dict):
        raise NotImplementedError

    def download(self, dest: Path, version: str, release, route: dict) -> tuple[str, Path]:
        raise NotImplementedError

    def precheck(self, new_bin: Path, expected: tuple[int, int, int]) -> str:
        """Почему этот бинарник нельзя ставить; пусто — можно."""
        raise NotImplementedError

    def configured(self) -> bool:
        """Работает ли ядро на шлюзе (конфиг применён) — тогда его перезапускают и проверяют."""
        raise NotImplementedError

    def restart(self) -> str | None:
        """Перезапуск и ожидание ответа; None — отвечает, иначе причина."""
        raise NotImplementedError

    def probe(self):
        """Сквозная проверка до замены: что прошло (None — ничего, сравнивать не с чем)."""
        raise NotImplementedError

    def verify(self, before) -> str:
        """Сквозная проверка после замены; пусто — прошла."""
        raise NotImplementedError


class XrayAdapter(Adapter):
    core = "xray"

    def release(self, version, route):
        return binary.get_release(version, **route)

    def download(self, dest, version, release, route):
        return binary.download_release(dest, version, release=release, **route)

    def precheck(self, new_bin, expected):
        from .xraycore import update

        found = self.version(new_bin)
        if found is not None and found != expected:
            return f"это Xray {version_text(found)}, а не {version_text(expected)}"
        return update.check_new(new_bin, engine.read_json(self.paths.xray_config_file))

    def configured(self):
        return self.paths.xray_config_file.exists()

    def restart(self):
        from .xraycore import update

        service = engine.make_service(self.paths, self.paths.xray_bin)
        api = engine.make_api(self.cfg, self.paths.xray_bin)
        return update.restart_and_wait(service, api, update.WAIT_SECONDS)

    def _e2e(self) -> bool:
        result = checks.http_get_via_proxy(
            "127.0.0.1", self.cfg.xray.http_port, scan.cheap_url(self.cfg), silence=5.0,
            max_total=20.0, user_agent=self.cfg.probe.user_agent,
        )
        return result.ok

    def probe(self):
        return True if self._e2e() else None

    def verify(self, before):
        deadline = time.monotonic() + E2E_WAIT
        while True:
            if self._e2e():
                return ""
            if time.monotonic() >= deadline:
                return (f"запрос в интернет через серверы не проходит {E2E_WAIT:.0f} с, "
                        "а со прежней версией проходил")
            time.sleep(E2E_PAUSE)


class SingboxAdapter(Adapter):
    core = "sing-box"

    def release(self, version, route):
        return sbbinary.get_release(version, **route)

    def download(self, dest, version, release, route):
        return sbbinary.download_release(dest, version, release=release, **route)

    def precheck(self, new_bin, expected):
        found = self.version(new_bin)
        if found is None:
            return "бинарник не запускается"
        if found != expected:
            return f"это sing-box {version_text(found)}, а не {version_text(expected)}"
        applied = engine.read_json(self.paths.singbox_config_file)
        if applied is not None:
            ok, output = singboxing.validate_config(applied, new_bin)
            if ok is False:
                return f"рабочий конфиг не проходит sing-box check: {output}"
        return ""

    def configured(self):
        return self.paths.singbox_config_file.exists()

    def restart(self):
        from .sbcore import update

        return update.restart_and_check(engine.make_singbox(self.cfg, self.paths))

    def _tags(self) -> list[str]:
        """Серверы, через которые sing-box носит трафик Xray (правила маршрута)."""
        config = engine.read_json(self.paths.singbox_config_file) or {}
        rules = (config.get("route") or {}).get("rules") or []
        tags = [
            str(rule["outbound"]) for rule in rules
            if isinstance(rule, dict) and isinstance(rule.get("outbound"), str)
        ]
        return list(dict.fromkeys(tags))[:DELAY_TAGS]

    def _delay(self, tag: str) -> bool:
        """Clash API sing-box: проверка задержки сервера запросом на probe.trace_url."""
        config = engine.read_json(self.paths.singbox_config_file)
        secret = singboxing.clash_secret(config)
        query = urllib.parse.urlencode({"url": scan.cheap_url(self.cfg), "timeout": 5000})
        path = f"/proxies/{urllib.parse.quote(tag, safe='')}/delay?{query}"
        try:
            conn = http.client.HTTPConnection(singboxing.LOCAL, self.cfg.core.api_port, timeout=8.0)
            try:
                conn.request("GET", path, headers={"Authorization": f"Bearer {secret}"})
                response = conn.getresponse()
                body = response.read(4096)
            finally:
                conn.close()
        except (OSError, http.client.HTTPException):
            return False
        if response.status != 200:
            return False
        try:
            return isinstance(json.loads(body.decode("utf-8")).get("delay"), int)
        except (UnicodeDecodeError, ValueError, AttributeError):
            return False

    def probe(self):
        working = [tag for tag in self._tags() if self._delay(tag)]
        return working or None

    def verify(self, before):
        deadline = time.monotonic() + E2E_WAIT
        while True:
            if any(self._delay(tag) for tag in before):
                return ""
            if time.monotonic() >= deadline:
                return (f"ни один из серверов, что отвечали через прежнюю версию, не отвечает "
                        f"{E2E_WAIT:.0f} с")
            time.sleep(E2E_PAUSE)


def adapters(cfg: Config, paths: Paths) -> dict[str, Adapter]:
    return {"xray": XrayAdapter(cfg, paths), "sing-box": SingboxAdapter(cfg, paths)}


class Job:
    """Обновление или возврат одного ядра. Итог — событие «обновление ядер» и запись в
    cores.json, которую показывает панель."""

    def __init__(
        self,
        cfg: Config,
        paths: Paths,
        *,
        cores: dict[str, Adapter] | None = None,
        ways: Sequence[dict] | None = None,
        logger=None,
        out: Callable[[str], None] = print,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.cores = cores if cores is not None else adapters(cfg, paths)
        self.log = logger or log.get_logger("cores")
        self._ways = ways
        self.out = out
        self.now = now

    def ways(self) -> Sequence[dict]:
        if self._ways is None:
            self._ways = routes(self.cfg, engine.bypass_mark(self.cfg, self.log))
        return self._ways

    def run(self, core: str, action: str, version: str = "", reason: str = "panel") -> int:
        if core not in self.cores or action not in ACTIONS:
            self.out("ошибка: ожидается ядро xray или sing-box и действие update или rollback")
            return 2
        state = load_state(self.paths)
        state["job"] = {
            "core": core, "action": action, "version": version, "reason": reason,
            "state": "running", "stage": "", "text": "", "started": self.now(), "finished": None,
        }
        self._save(state)
        self.paths.cores_request_file.unlink(missing_ok=True)  # задание взято (take_request)
        ok, text = False, ""
        try:
            if action == "update":
                text = self.update(core, version, reason)
            else:
                text = self.rollback(core, reason)
            ok = True
        except JobError as exc:
            text = str(exc)
        except LockTimeout as exc:
            text = f"{TITLES[core]}: {exc} — идёт применение конфига, повторите позже"
        except Exception as exc:  # итог должен попасть в панель при любом сбое
            self.log.exception("задание %s %s оборвалось", action, core)
            text = f"{TITLES[core]}: задание оборвалось ({exc}) — подробности в журнале xgw-core"
        state = load_state(self.paths)
        job = dict(state.get("job") or {})
        job.update(state="ok" if ok else "failed", stage="", text=text, finished=self.now())
        state["job"] = job
        self._save(state)
        self._event(text)
        (self.log.info if ok else self.log.error)("%s", text)
        self.out(text if ok else f"ошибка: {text}")
        return 0 if ok else 1

    # --- шаги ----------------------------------------------------------------------

    def update(self, core: str, version: str, reason: str) -> str:
        adapter, title = self.cores[core], TITLES[core]
        target = core_dir(self.paths, core)
        prev = prev_dir(self.paths, core)
        staging = target.with_name(target.name + ".new")
        older = target.with_name(target.name + ".prev.old")
        name = core_bin(self.paths, core).name
        current = adapter.version(target / name)
        wanted = parse(version)
        if current is None:
            raise JobError(f"{title} не установлен — его ставит установка (sudo xgw install)")
        if wanted is None:
            raise JobError(f"версия {title} — три числа через точку, а не «{version}»")
        if wanted == current:
            return f"{title} {version} уже установлен"
        old = version_text(current)

        self._stage(f"скачиваю {title} {version} с GitHub")

        def fetch_new(route: dict) -> tuple[str, Path]:
            shutil.rmtree(staging, ignore_errors=True)
            release = adapter.release(version, route)
            return adapter.download(staging, version, release, route)

        try:
            (_tag, new_bin), _way = try_routes(fetch_new, self.ways())
        except BinaryError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise JobError(f"{title} {version} не загружен: {exc}. Стоит прежний {old}") from exc

        self._stage(f"проверяю {title} {version} на рабочем конфиге")
        problem = adapter.precheck(new_bin, wanted)
        if problem:
            shutil.rmtree(staging, ignore_errors=True)
            self._reject(core, version, problem)
            raise JobError(f"{title} {version} не подходит — {problem}. Стоит прежний {old}")
        configured = adapter.configured()
        before = adapter.probe() if configured else None

        self._stage(f"ставлю {title} {version} и перезапускаю")
        with file_lock(self.paths.lock_file):
            shutil.rmtree(older, ignore_errors=True)
            try:
                if prev.exists():
                    os.replace(prev, older)
                # Работающее ядро продолжает работать на прежнем файле до перезапуска.
                os.replace(target, prev)
                os.replace(staging, target)
            except OSError as exc:
                if not target.exists() and prev.exists():
                    os.replace(prev, target)
                if older.exists() and not prev.exists():
                    os.replace(older, prev)
                shutil.rmtree(staging, ignore_errors=True)
                raise JobError(f"файлы {title} не заменены ({exc}). Стоит прежний {old}") from exc
            with contextlib.suppress(OSError):
                os.chmod(target / name, 0o755)
            error = adapter.restart() if configured else None
        if error is None and before is not None:
            self._stage(f"проверяю запрос через серверы с {title} {version}")
            error = adapter.verify(before) or None
        if error is not None:
            self.log.error("%s %s не прошёл проверку: %s", title, version, error)
            self._stage(f"возвращаю {title} {old}")
            with file_lock(self.paths.lock_file):
                shutil.rmtree(staging, ignore_errors=True)
                os.replace(target, staging)
                os.replace(prev, target)
                if older.exists():
                    os.replace(older, prev)
                shutil.rmtree(staging, ignore_errors=True)
                again = adapter.restart() if configured else None
            self._reject(core, version, error)
            raise JobError(
                f"{title} {version} не прошёл проверку: {error} — возвращён прежний {old}"
                + ("" if again is None else f", но и он не отвечает: {again}")
            )
        shutil.rmtree(older, ignore_errors=True)
        state = load_state(self.paths)
        state[core] = {
            "accepted": version, "previous": old, "updated": self.now(),
            "watch_until": self.now() + WATCH_SECONDS if configured else 0, "rejected": None,
        }
        self._save(state)
        note = ""
        if configured and before is None:
            note = " (запрос через серверы не проверялся: он не проходил и до обновления)"
        elif not configured:
            note = f" ({title} сейчас не запущен: проверены только версия и конфиг)"
        watch = (f" Сутки шлюз следит за ним и вернёт {old} сам, если ядро перестанет отвечать."
                 if configured else "")
        return (f"{title} обновлён: {old} → {version}, проверки пройдены{note}.{watch} Вернуть "
                f"{old} — кнопка «Вернуть {old}» в панели")

    def rollback(self, core: str, reason: str) -> str:
        adapter, title = self.cores[core], TITLES[core]
        target = core_dir(self.paths, core)
        prev = prev_dir(self.paths, core)
        rejected = target.with_name(target.name + ".new")
        name = core_bin(self.paths, core).name
        if not (prev / name).exists():
            raise JobError(f"прежней версии {title} нет — возвращаться не к чему")
        back = adapter.version(prev / name)
        current = adapter.version(target / name)
        if back is None:
            raise JobError(f"прежний {title} в {prev} не запускается — оставлен текущий")
        old, now_text = version_text(back), version_text(current) or "?"
        self._stage(f"проверяю прежний {title} {old} на рабочем конфиге")
        problem = adapter.precheck(prev / name, back)
        if problem:
            raise JobError(f"прежний {title} {old} не подходит — {problem}. Оставлен {now_text}")
        configured = adapter.configured()
        self._stage(f"возвращаю {title} {old}")
        with file_lock(self.paths.lock_file):
            shutil.rmtree(rejected, ignore_errors=True)
            os.replace(target, rejected)
            os.replace(prev, target)
            error = adapter.restart() if configured else None
            if error is not None:
                os.replace(target, prev)
                os.replace(rejected, target)
                again = adapter.restart()
                raise JobError(
                    f"прежний {title} {old} не поднялся ({error}) — оставлен {now_text}"
                    + ("" if again is None else f", но и он не отвечает: {again}")
                )
        shutil.rmtree(rejected, ignore_errors=True)
        why = ("новое ядро перестало отвечать во время наблюдения" if reason == "watch"
               else "возвращена прежняя версия")
        state = load_state(self.paths)
        state[core] = {
            "accepted": old, "previous": "", "updated": self.now(), "watch_until": 0,
            "rejected": {
                "version": now_text, "reason": why, "at": self.now(), "kind": "rollback",
            },
        }
        self._save(state)
        if reason == "watch":
            return f"{title} {now_text} перестал отвечать — шлюз вернул прежний {old}"
        return f"{title} {now_text} убран, возвращён прежний {old}"

    # --- мелочи ------------------------------------------------------------------

    def _reject(self, core: str, version: str, reason: str) -> None:
        """Этот выпуск не прошёл проверку на шлюзе — панель покажет почему."""
        state = load_state(self.paths)
        entry = dict(_core_state(state, core))
        entry["rejected"] = {
            "version": version, "reason": reason, "at": self.now(), "kind": "check",
        }
        state[core] = entry
        self._save(state)

    def _stage(self, text: str) -> None:
        self.log.info("%s", text)
        state = load_state(self.paths)
        job = state.get("job")
        if isinstance(job, dict):
            job["stage"] = text
            self._save(state)

    def _save(self, state: dict) -> None:
        try:
            save_state(self.paths, state)
        except OSError as exc:
            self.log.error("cores.json не записан: %s", exc)

    def _event(self, text: str) -> None:
        try:
            store = Store(self.paths.db_file)
            try:
                store.add_event("cores", text)
            finally:
                store.close()
        except Exception as exc:  # событие не важнее самого задания
            self.log.error("событие не записано: %s", exc)


def run_request(
    cfg: Config, paths: Paths, *, logger=None, out=print, job: Job | None = None,
) -> int:
    """`xgw cores run-job` — то, что выполняет служба xgw-core по заданию демона."""
    request = take_request(paths)
    if request is None:
        out("заданий нет")
        return 0
    job = job or Job(cfg, paths, logger=logger, out=out)
    code = job.run(
        str(request.get("core") or ""), str(request.get("action") or ""),
        str(request.get("version") or ""), str(request.get("reason") or "panel"),
    )
    # Неудача задания — обычный итог (выпуск не прошёл проверку): он записан в cores.json и в
    # события, а служба не остаётся в systemd «failed». Ненулевой код — только у неверного задания.
    if code == 2:
        paths.cores_request_file.unlink(missing_ok=True)  # неверное задание не ждёт 30 минут
        return 2
    return 0

