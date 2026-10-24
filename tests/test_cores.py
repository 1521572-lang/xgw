"""Обновление ядер из панели (cores.py, ASSUMPTIONS п. 234): выпуски на GitHub, задание службе
xgw-core, обновление с проверкой и возвратом прежней версии, принятая шлюзом версия, карточка
панели и `xgw cores`."""

import http.server
import json
import os
import threading
import time
from pathlib import Path
from typing import ClassVar

import pytest
from test_daemon import Harness, _started
from test_panel import Rig

from xgw import cli, config, cores, daemon, diag, install
from xgw.fetch import FetchError, FetchResult
from xgw.net.cmd import CommandError
from xgw.paths import Paths, atomic_write_json
from xgw.sbcore import binary as sbbinary
from xgw.store import Store
from xgw.watch.states import State
from xgw.xraycore.binary import BinaryError

REPO = Path(__file__).resolve().parents[1]
LINUX64 = ("linux", "x86_64")


def _xray_release(
    tag, *, prerelease=False, draft=False, dgst=True, published="2026-10-23T10:00:00Z",
):
    assets = [{"name": "Xray-linux-64.zip", "browser_download_url": f"https://x/{tag}/zip"}]
    if dgst:
        assets.append({"name": "Xray-linux-64.zip.dgst", "browser_download_url": f"https://x/{tag}/dgst"})
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "assets": assets,
            "published_at": published}


def _singbox_release(tag, *, prerelease=False, digest=True):
    version = tag.lstrip("v")
    asset = {"name": f"sing-box-{version}-linux-amd64.tar.gz",
             "browser_download_url": f"https://s/{tag}"}
    if digest:
        asset["digest"] = "sha256:" + "a" * 64
    return {"tag_name": tag, "prerelease": prerelease, "draft": False, "assets": [asset],
            "published_at": "2026-10-20T00:00:00Z"}


def _events(paths: Paths) -> list[str]:
    store = Store(paths.db_file)
    try:
        return [f"{event['kind']}: {event['detail']}" for event in store.recent_events(50)]
    finally:
        store.close()


# --- какой выпуск предложить ---------------------------------------------------------


def test_xray_offer_includes_prereleases_and_needs_a_dgst_file():
    releases = [
        _xray_release("v26.10.21", prerelease=True),
        _xray_release("v26.11.2", draft=True),  # черновик — не выпуск
        _xray_release("v26.10.30", prerelease=True),
        _xray_release("v26.10.28", dgst=False),  # хеш сверить нечем
        _xray_release("v26.3.27"),
    ]
    offer = cores.pick_offer("xray", releases, (26, 10, 21), LINUX64)
    assert offer == cores.Offer("26.10.30", True, "2026-10-23T10:00:00Z")
    assert cores.pick_offer("xray", releases, (26, 10, 30), LINUX64) is None
    # Файла для этой машины нет — не предлагается.
    assert cores.pick_offer("xray", releases, (26, 10, 21), ("linux", "mips")) is None


def test_singbox_offer_is_stable_only_and_needs_a_hash():
    releases = [
        _singbox_release("v1.15.0-beta.2", prerelease=True),
        _singbox_release("v1.15.0", prerelease=True),
        _singbox_release("v1.14.5", digest=False),
        _singbox_release("v1.14.4"),
        _singbox_release("v1.14.3"),
    ]
    offer = cores.pick_offer("sing-box", releases, (1, 14, 3), LINUX64)
    assert offer is not None and offer.version == "1.14.4" and not offer.prerelease


def test_the_pinned_singbox_hash_belongs_to_its_own_version_only():
    """Зашитый хеш — для 1.14.3: у более нового выпуска сверка идёт с хешем из API GitHub,
    иначе он отвергался бы как «не совпадает с проверенным»."""
    assert sbbinary.PINNED_VERSION == config.SINGBOX_VERSION
    name = sbbinary.asset_name("v1.14.4", *LINUX64)
    newer = sbbinary.Release("v1.14.4", {name: ("https://s/a", "b" * 64)})
    assert sbbinary.expected_sha256(newer, name, *LINUX64) == "b" * 64
    name = sbbinary.asset_name("v1.14.3", *LINUX64)
    pinned = sbbinary.Release("v1.14.3", {name: ("https://s/a", "b" * 64)})
    with pytest.raises(BinaryError, match="не совпадает с проверенным"):
        sbbinary.expected_sha256(pinned, name, *LINUX64)


# --- проверка на GitHub -------------------------------------------------------------


class FakeGitHub:
    """fetch_url для GitHub: списки выпусков и теги; пути — что запрашивали."""

    def __init__(self) -> None:
        self.xray = [
            _xray_release("v26.10.30", prerelease=True),
            _xray_release("v26.10.21", prerelease=True),
        ]
        self.singbox = [_singbox_release("v1.14.3")]
        self.tags: dict[str, int] = {}
        self.direct_fails = False
        self.calls: list[tuple[str, bool]] = []

    def __call__(self, url, *, headers=None, timeout=0, retries=0, mark=None, bootstrap=None,
                 proxy=None, **_kw):
        self.calls.append((url, proxy is not None))
        if self.direct_fails and proxy is None:
            raise FetchError("GitHub недоступен напрямую")
        if "/tags/" in url:
            return FetchResult(self.tags.get(url.rsplit("/", 1)[1], 404), {}, b"{}")
        data = self.xray if "Xray" in url else self.singbox
        return FetchResult(200, {}, json.dumps(data).encode())


@pytest.fixture()
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(cores.binary, "RELEASES_API", "https://api.github.com/repos/XTLS/Xray-core/releases")
    monkeypatch.setattr(cores.sbbinary, "RELEASES_API", "https://api.github.com/repos/SagerNet/sing-box/releases")
    monkeypatch.setattr(cores.fetch, "fetch_url", fake)
    return fake


def _paths(tmp_path) -> Paths:
    paths = Paths(root=tmp_path)
    paths.ensure()
    return paths


def test_check_finds_a_new_release_and_tells_about_it_once(tmp_path, github):
    paths = _paths(tmp_path)
    installed = {"xray": (26, 10, 21), "sing-box": (1, 14, 3)}
    record, events = cores.check(config.Config(), paths, installed, platform=LINUX64)
    assert record["xray"]["latest"]["version"] == "26.10.30"
    assert record["sing-box"]["latest"] is None and record["error"] == ""
    assert len(events) == 1
    assert "на GitHub вышел Xray 26.10.30 (предварительный выпуск)" in events[0][0]
    assert events[0][1] is False  # предложение — без уведомления
    assert json.loads(paths.cores_check_file.read_text(encoding="utf-8"))["xray"]["latest"]
    _record, again = cores.check(config.Config(), paths, installed, platform=LINUX64)
    assert again == []  # о той же версии второй раз не сообщается


def test_withdrawn_installed_version_is_a_warning_with_a_notification(tmp_path, github):
    """Как 26.10.10 21.10.2026: выпуска с установленной версией на GitHub больше нет."""
    paths = _paths(tmp_path)
    github.xray = [_xray_release("v26.10.30", prerelease=True)]
    record, events = cores.check(config.Config(), paths, {"xray": (26, 10, 21)}, platform=LINUX64)
    assert record["xray"]["withdrawn"] is True
    warning = [event for event in events if "убран с GitHub" in event[0]]
    assert warning and warning[0][1] is True and "Xray 26.10.21" in warning[0][0]
    # Тег на месте (просто не попал в список последних) — не отозван.
    github.tags["v26.10.21"] = 200
    record, _ = cores.check(config.Config(), paths, {"xray": (26, 10, 21)}, platform=LINUX64)
    assert record["xray"]["withdrawn"] is False


def test_check_goes_through_xray_when_github_is_unreachable_directly(tmp_path, github):
    paths = _paths(tmp_path)
    github.direct_fails = True
    record, _ = cores.check(config.Config(), paths, {"xray": (26, 10, 21)}, platform=LINUX64)
    assert record["xray"]["latest"]["version"] == "26.10.30"
    assert (github.calls[0][1], github.calls[1][1]) == (False, True)


def test_check_errors_are_recorded_and_retried_sooner(tmp_path, monkeypatch):
    paths = _paths(tmp_path)

    def down(url, **kwargs):
        raise FetchError("нет сети")

    monkeypatch.setattr(cores.fetch, "fetch_url", down)
    record, events = cores.check(config.Config(), paths, {"xray": (26, 10, 21)}, now=lambda: 1000.0)
    assert "нет сети" in record["error"] and events == []
    assert not cores.check_due(paths, 1000.0 + cores.CHECK_RETRY - 1)
    assert cores.check_due(paths, 1000.0 + cores.CHECK_RETRY)


def test_cores_that_are_not_installed_are_not_checked(tmp_path, github):
    paths = _paths(tmp_path)
    installed = {"xray": None, "sing-box": None}
    record, _ = cores.check(config.Config(), paths, installed, now=lambda: 5.0)
    assert github.calls == [] and record["xray"]["latest"] is None
    assert not cores.check_due(paths, 5.0 + cores.CHECK_EVERY - 1)
    assert cores.check_due(paths, 5.0 + cores.CHECK_EVERY)


# --- задание службе xgw-core ---------------------------------------------------------


def test_start_writes_the_request_and_starts_the_service(tmp_path):
    paths = _paths(tmp_path)
    calls = []
    assert cores.start(paths, "xray", "update", version="26.10.30",
                       runner=lambda argv, **kw: calls.append(argv) or "") == ""
    assert calls == [["systemctl", "start", "--no-block", "xgw-core.service"]]
    request = json.loads(paths.cores_request_file.read_text(encoding="utf-8"))
    assert request["core"] == "xray" and request["version"] == "26.10.30"
    assert paths.cores_request_file.stat().st_mode & 0o777 == 0o600
    # Пока задание не выполнено, второе не ставится.
    assert "уже идёт" in cores.start(paths, "xray", "rollback", runner=lambda argv, **kw: "")
    assert cores.take_request(paths)["action"] == "update"
    paths.cores_request_file.write_text("[1, 2]", encoding="utf-8")  # не задание
    assert cores.take_request(paths) == {} and cores.take_request(paths) is None


def test_start_refuses_bad_input_and_cleans_up_when_systemctl_fails(tmp_path):
    paths = _paths(tmp_path)
    assert "ожидается ядро" in cores.start(paths, "v2ray", "update", version="1.0.0")
    assert "три числа" in cores.start(paths, "xray", "update", version="latest")

    def broken(argv, **kw):
        raise CommandError("systemctl: Unit xgw-core.service not found")

    error = cores.start(paths, "sing-box", "rollback", runner=broken)
    assert "не запустилась" in error and not paths.cores_request_file.exists()


def test_a_stale_running_job_does_not_block_a_new_one(tmp_path):
    paths = _paths(tmp_path)
    cores.save_state(paths, {"job": {"state": "running", "started": 1000.0}})
    assert cores.job_active(paths, 1000.0 + 60)
    assert not cores.job_active(paths, 1000.0 + cores.JOB_STALE + 1)


# --- само задание: обновление и возврат -----------------------------------------------


class FakeCore(cores.Adapter):
    """Ядро-пустышка: «версия» бинарника — его содержимое."""

    def __init__(self, paths: Paths, core: str = "xray") -> None:
        super().__init__(config.Config(), paths)
        self.core = core
        self.name = cores.core_bin(paths, core).name
        self.problem = ""
        self.running = True
        self.restart_errors: list[str | None] = []
        self.restarts = 0
        self.before: object = True
        self.verify_error = ""
        self.download_errors: list[Exception] = []
        self.routes: list[dict] = []
        self.on_restart = lambda: None

    def install(self, version: str, *, where: Path | None = None) -> None:
        directory = where or cores.core_dir(self.paths, self.core)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / self.name).write_text(version, encoding="utf-8")
        (directory / "geoip.dat").write_text(f"geo {version}", encoding="utf-8")

    def version(self, path):
        try:
            return cores.parse(Path(path).read_text(encoding="utf-8"))
        except OSError:
            return None

    def installed(self) -> str:
        return (cores.core_bin(self.paths, self.core)).read_text(encoding="utf-8")

    def release(self, version, route):
        self.routes.append(route)
        return {"tag": f"v{version}"}

    def download(self, dest, version, release, route):
        if self.download_errors:
            raise self.download_errors.pop(0)
        self.install(version, where=dest)
        return release["tag"], dest / self.name

    def precheck(self, new_bin, expected):
        return self.problem

    def configured(self):
        return self.running

    def restart(self):
        self.restarts += 1
        self.on_restart()
        return self.restart_errors.pop(0) if self.restart_errors else None

    def probe(self):
        return self.before

    def verify(self, before):
        return self.verify_error


class Gateway:
    def __init__(self, tmp_path: Path) -> None:
        self.paths = _paths(tmp_path)
        self.xray = FakeCore(self.paths, "xray")
        self.singbox = FakeCore(self.paths, "sing-box")
        self.xray.install("26.10.21")
        self.singbox.install("1.14.3")
        self.out: list[str] = []
        self.t = 1_800_000_000.0

    def job(self) -> cores.Job:
        return cores.Job(
            config.Config(), self.paths, cores={"xray": self.xray, "sing-box": self.singbox},
            ways=[{"mark": None, "bootstrap": None}, {"proxy": ("127.0.0.1", 10809)}],
            out=self.out.append, now=lambda: self.t,
        )

    def state(self) -> dict:
        return cores.load_state(self.paths)

    def leftovers(self) -> list[str]:
        return sorted(item.name for item in self.paths.opt.iterdir())


@pytest.fixture()
def gw(tmp_path):
    return Gateway(tmp_path)


def test_update_keeps_the_previous_version_next_to_the_new_one(gw):
    assert gw.job().run("xray", "update", "26.10.30") == 0
    assert gw.xray.installed() == "26.10.30" and gw.xray.restarts == 1
    assert (cores.prev_dir(gw.paths, "xray") / "xray").read_text(encoding="utf-8") == "26.10.21"
    assert (gw.paths.xray_dir / "geoip.dat").read_text(encoding="utf-8") == "geo 26.10.30"
    entry = gw.state()["xray"]
    assert entry["accepted"] == "26.10.30" and entry["previous"] == "26.10.21"
    assert entry["watch_until"] == gw.t + cores.WATCH_SECONDS
    assert gw.state()["job"]["state"] == "ok"
    assert gw.leftovers() == ["sing-box", "xray", "xray.prev"]
    assert "Xray обновлён: 26.10.21 → 26.10.30, проверки пройдены" in gw.out[0]
    assert any(e.startswith("cores: Xray обновлён") for e in _events(gw.paths))
    assert cores.previous(gw.paths, "xray") == "26.10.21"
    assert cores.watching(gw.paths, "xray", gw.t + 60)
    assert not cores.watching(gw.paths, "xray", gw.t + cores.WATCH_SECONDS + 1)
    assert cores.allowed(gw.paths, "xray", (26, 10, 30))
    assert cores.allowed(gw.paths, "xray", (26, 10, 21))
    # Следующее обновление: прежней становится 26.10.30, а 26.10.21 больше не хранится.
    assert gw.job().run("xray", "update", "26.11.4") == 0
    assert cores.previous(gw.paths, "xray") == "26.10.30"
    assert gw.leftovers() == ["sing-box", "xray", "xray.prev"]


def test_unsuitable_release_is_rejected_before_anything_is_replaced(gw):
    gw.xray.problem = "рабочий конфиг не проходит xray run -test: unknown field"
    assert gw.job().run("xray", "update", "26.10.30") == 1
    assert gw.xray.installed() == "26.10.21" and gw.xray.restarts == 0
    assert gw.leftovers() == ["sing-box", "xray"]
    assert "не подходит" in gw.out[0] and "Стоит прежний 26.10.21" in gw.out[0]
    assert gw.state()["xray"]["rejected"]["version"] == "26.10.30"
    assert gw.state()["job"]["state"] == "failed"
    assert not cores.allowed(gw.paths, "xray", (26, 10, 30))


@pytest.mark.parametrize("failure", ["restart", "e2e"])
def test_new_core_that_fails_its_checks_is_replaced_by_the_old_one(gw, failure):
    # Было и прежнее обновление: его «прежняя версия» должна остаться на месте.
    gw.xray.install("26.10.20", where=cores.prev_dir(gw.paths, "xray"))
    cores.save_state(gw.paths, {"xray": {"accepted": "26.10.21", "previous": "26.10.20"}})
    if failure == "restart":
        gw.xray.restart_errors = ["API не отвечает 15 с (нет связи с ядром)"]
    else:
        gw.xray.verify_error = "запрос в интернет через серверы не проходит 45 с"
    assert gw.job().run("xray", "update", "26.10.30") == 1
    assert gw.xray.installed() == "26.10.21"
    assert (gw.paths.xray_dir / "geoip.dat").read_text(encoding="utf-8") == "geo 26.10.21"
    assert gw.xray.restarts == 2  # новая версия и снова прежняя
    assert cores.previous(gw.paths, "xray") == "26.10.20"
    assert gw.leftovers() == ["sing-box", "xray", "xray.prev"]
    assert "не прошёл проверку" in gw.out[0] and "возвращён прежний 26.10.21" in gw.out[0]
    assert gw.state()["xray"]["rejected"]["version"] == "26.10.30"
    assert gw.state()["xray"]["accepted"] == "26.10.21"


def test_e2e_is_skipped_when_it_did_not_work_before_the_update(gw):
    gw.xray.before = None
    gw.xray.verify_error = "не должна вызываться"
    assert gw.job().run("xray", "update", "26.10.30") == 0
    assert "не проверялся: он не проходил и до обновления" in gw.out[0]


def test_core_that_is_not_running_is_replaced_without_restart_or_watch(gw):
    gw.singbox.running = False
    assert gw.job().run("sing-box", "update", "1.14.4") == 0
    assert gw.singbox.restarts == 0 and gw.singbox.installed() == "1.14.4"
    assert gw.state()["sing-box"]["watch_until"] == 0
    assert "сейчас не запущен" in gw.out[0]


def test_download_tries_xray_after_the_direct_way_and_reports_both(gw):
    gw.xray.download_errors = [FetchError("напрямую: таймаут")]
    assert gw.job().run("xray", "update", "26.10.30") == 0
    assert [("proxy" in route) for route in gw.xray.routes] == [False, True]
    gw.xray.download_errors = [FetchError("напрямую: таймаут"), BinaryError("SHA-256 не совпал")]
    assert gw.job().run("xray", "update", "26.11.4") == 1
    assert "не загружен" in gw.out[-1] and "SHA-256" in gw.out[-1]
    assert gw.xray.installed() == "26.10.30" and not (gw.paths.opt / "xray.new").exists()


def test_rollback_returns_the_previous_version_and_forgets_the_rejected_one(gw):
    assert gw.job().run("xray", "update", "26.10.30") == 0
    gw.t += 3600
    assert gw.job().run("xray", "rollback", reason="panel") == 0
    assert gw.xray.installed() == "26.10.21" and gw.leftovers() == ["sing-box", "xray"]
    entry = gw.state()["xray"]
    assert entry["accepted"] == "26.10.21" and entry["previous"] == "" and entry["watch_until"] == 0
    assert entry["rejected"]["version"] == "26.10.30"
    assert "Xray 26.10.30 убран, возвращён прежний 26.10.21" in gw.out[-1]
    assert cores.previous(gw.paths, "xray") == ""
    assert not cores.allowed(gw.paths, "xray", (26, 10, 30))
    assert gw.job().run("xray", "rollback") == 1
    assert "возвращаться не к чему" in gw.out[-1]


def test_rollback_from_the_watch_says_why(gw):
    assert gw.job().run("sing-box", "update", "1.14.4") == 0
    assert gw.job().run("sing-box", "rollback", reason="watch") == 0
    assert "перестал отвечать — шлюз вернул прежний 1.14.3" in gw.out[-1]


def test_rollback_keeps_the_current_core_when_the_old_one_does_not_start(gw):
    assert gw.job().run("xray", "update", "26.10.30") == 0
    gw.xray.restart_errors = ["не запустился"]
    assert gw.job().run("xray", "rollback") == 1
    assert gw.xray.installed() == "26.10.30" and cores.previous(gw.paths, "xray") == "26.10.21"
    assert "прежний Xray 26.10.21 не поднялся" in gw.out[-1]


def test_rollback_refuses_an_old_core_that_does_not_accept_the_config(gw):
    assert gw.job().run("xray", "update", "26.10.30") == 0
    gw.xray.problem = "рабочий конфиг не проходит xray run -test"
    assert gw.job().run("xray", "rollback") == 1
    assert gw.xray.installed() == "26.10.30" and gw.xray.restarts == 1


def test_update_needs_an_installed_core_and_a_version(gw):
    (gw.paths.singbox_bin).unlink()
    assert gw.job().run("sing-box", "update", "1.14.4") == 1
    assert "не установлен" in gw.out[-1]
    assert gw.job().run("xray", "update", "26.10.21") == 0
    assert "уже установлен" in gw.out[-1]
    assert gw.job().run("v2ray", "update", "1.0.0") == 2


def test_a_crash_inside_the_job_still_ends_up_in_the_panel(gw):
    def boom():
        raise RuntimeError("диск переполнен")

    gw.xray.on_restart = boom
    assert gw.job().run("xray", "update", "26.10.30") == 1
    job = gw.state()["job"]
    assert job["state"] == "failed" and "диск переполнен" in job["text"]


def test_run_request_takes_the_job_from_the_request_file(gw):
    assert cores.run_request(config.Config(), gw.paths, out=gw.out.append, job=gw.job()) == 0
    assert gw.out == ["заданий нет"]
    atomic_write_json(gw.paths.cores_request_file, {
        "core": "xray", "action": "update", "version": "26.10.30", "reason": "panel"})
    # Панель ни на миг не видит «задания нет»: файл задания убирается, когда уже записано «идёт».
    seen = []
    gw.xray.on_restart = lambda: seen.append(cores.job_active(gw.paths, time.time()))
    assert cores.job_active(gw.paths, time.time())
    assert cores.run_request(config.Config(), gw.paths, job=gw.job()) == 0
    assert seen == [True] and not gw.paths.cores_request_file.exists()
    assert gw.xray.installed() == "26.10.30" and not cores.job_active(gw.paths, time.time())
    # Неудача — обычный итог: записан, а служба в systemd не «failed» (код 0).
    gw.xray.problem = "рабочий конфиг не проходит xray run -test"
    atomic_write_json(gw.paths.cores_request_file, {
        "core": "xray", "action": "update", "version": "26.11.4"})
    assert cores.run_request(config.Config(), gw.paths, job=gw.job()) == 0
    assert gw.state()["job"]["state"] == "failed"
    atomic_write_json(gw.paths.cores_request_file, {"core": "v2ray", "action": "update"})
    assert cores.run_request(config.Config(), gw.paths, job=gw.job()) == 2
    assert not cores.job_active(gw.paths, time.time())  # неверное задание не держит очередь


# --- принятая версия: установка, diag, update-xray ----------------------------------


def test_install_keeps_an_accepted_newer_core_but_not_an_older_one(tmp_path):
    paths = _paths(tmp_path)
    assert cores.keeps(paths, "xray", (26, 10, 21))
    assert not cores.keeps(paths, "xray", (26, 10, 30))
    cores.save_state(paths, {"xray": {"accepted": "26.10.30"}, "sing-box": {"accepted": "1.14.2"}})
    assert cores.keeps(paths, "xray", (26, 10, 30))
    # Принятая старше проверенной (вышел XGW с более свежей проверенной) — ставится проверенная.
    assert not cores.keeps(paths, "sing-box", (1, 14, 2))
    prev = cores.prev_dir(paths, "xray")
    prev.mkdir(parents=True)
    (prev / "xray").write_text("26.10.21", encoding="utf-8")
    cores.forget(paths, "xray")
    assert not prev.exists() and "xray" not in cores.load_state(paths)
    assert "sing-box" in cores.load_state(paths)


def test_diag_accepts_the_version_accepted_by_the_gateway(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.xray_dir.mkdir(parents=True)
    paths.xray_bin.write_bytes(b"...httpMethod...")
    monkeypatch.setattr(diag.binary, "installed_version", lambda path: (26, 10, 30))
    check = diag.Diag(config.Config(), paths, net=False)._xray()[0]
    assert check.level == diag.FAIL and "принятой шлюзом" in check.text
    cores.save_state(paths, {"xray": {"accepted": "26.10.30"}})
    check = diag.Diag(config.Config(), paths, net=False)._xray()[0]
    assert check.level == diag.OK and "обновлена из панели и проверена шлюзом" in check.text


def test_service_file_runs_the_job_with_write_access_to_the_cores(tmp_path):
    text = (REPO / "packaging" / "xgw-core.service").read_text(encoding="utf-8")
    assert "ExecStart=/usr/local/bin/xgw cores run-job" in text
    assert "Type=oneshot" in text and "ProtectSystem=strict" in text
    assert "ReadWritePaths=/opt/xgw /var/lib/xgw -/run/xgw" in text
    assert "ConditionPathExists=/run/xgw/core-request.json" in text
    assert "[Install]" not in text  # не включается: работает только по заданию демона
    assert cores.UNIT in install.UNIT_FILES and cores.UNIT not in install.UNITS
    # У демона /opt/xgw только для чтения — поэтому и нужна отдельная служба.
    daemon_unit = (REPO / "packaging" / "xgw.service").read_text(encoding="utf-8")
    assert "ReadWritePaths=/etc/xgw /var/lib/xgw /run/xgw" in daemon_unit


# --- демон: проверка раз в сутки ------------------------------------------------------


@pytest.fixture()
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = config.Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.speed.sticky = False
    monkeypatch.setattr(daemon, "CORES_FIRST_CHECK", 300.0)
    instance = Harness(cfg, paths)
    instance.xray_version = "26.10.21"
    instance._xray_version = lambda: None
    yield instance
    instance.store.close()


def _wait(instance) -> None:
    thread = instance._cores_thread
    if thread is not None:
        thread.join(5)


def test_daemon_checks_releases_in_the_background_once_a_day(harness, monkeypatch):
    seen = []

    def fake_check(cfg, paths, installed, *, mark=None, **kw):
        seen.append(installed)
        atomic_write_json(paths.cores_check_file, {"at": harness.t, "error": ""})
        return {}, [("на GitHub вышел Xray 26.10.30 — обновить можно в панели", False)]

    monkeypatch.setattr(daemon.cores, "check", fake_check)
    _started(harness)
    assert seen == []  # первые 5 минут после запуска — не сразу
    harness.t += 301
    harness.tick()
    _wait(harness)
    assert seen == [{"xray": (26, 10, 21), "sing-box": None}]
    assert any("вышел Xray 26.10.30" in event for event in harness.events())
    harness.t += 3600
    harness.tick()
    _wait(harness)
    assert len(seen) == 1  # до суток не повторяется
    harness.request_core_check()
    assert harness.cores_pending
    harness.tick()
    _wait(harness)
    assert len(seen) == 2 and not harness.cores_pending
    harness.t += cores.CHECK_EVERY + daemon.CORES_RECHECK
    harness.tick()
    _wait(harness)
    assert len(seen) == 3


def test_daemon_leaves_xray_alone_while_the_core_job_runs(harness):
    _started(harness)
    harness.observatory = None
    harness.api.down = True
    cores.save_state(harness.paths, {"job": {"state": "running", "started": time.time()}})
    for _ in range(4):
        assert harness.tick() is State.XRAY_DOWN
    assert harness.applier.rollbacks == [] and harness.down_ticks == 0
    assert harness.service.starts == 0


def _watched(paths: Paths, core: str, previous: str, until: float) -> None:
    prev = cores.prev_dir(paths, core)
    prev.mkdir(parents=True, exist_ok=True)
    (prev / cores.core_bin(paths, core).name).write_text(previous, encoding="utf-8")
    cores.save_state(paths, {core: {"accepted": "26.10.30", "previous": previous,
                                    "watch_until": until}})


@pytest.mark.parametrize("watched", [True, False])
def test_xray_dead_after_the_config_rollback_brings_the_old_core_back(harness, watched):
    asked = []
    harness._start_core_job = (
        lambda core, action, *, reason: asked.append((core, action, reason)) or ""
    )
    if watched:
        _watched(harness.paths, "xray", "26.10.21", harness.t + 3600)
    _started(harness)
    harness.observatory = None
    harness.api.down = True
    harness.service.active = False
    harness.tick()
    harness.tick()
    assert len(harness.applier.rollbacks) == 1 and asked == []  # сначала — откат конфига
    harness.tick()
    assert asked == []
    harness.tick()
    if not watched:
        assert asked == []
        return
    assert asked == [("xray", "rollback", "watch")]
    assert any("шлюз возвращает прежнюю версию 26.10.21" in event for event in harness.events())
    harness.tick()
    harness.tick()
    assert len(asked) == 1  # один раз


def test_failed_watch_rollback_is_reported(harness):
    harness._start_core_job = (
        lambda core, action, *, reason: "служба xgw-core.service не запустилась"
    )
    _watched(harness.paths, "xray", "26.10.21", harness.t + 3600)
    assert harness._core_back("xray", "Xray не отвечает") is False
    assert any("вернуть прежний Xray 26.10.21 не удалось" in event for event in harness.events())


# --- панель ---------------------------------------------------------------------------


@pytest.fixture()
def panel_rig(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.client.login()
    yield rig
    rig.panel.stop()


def _offer(paths: Paths, version="26.10.30") -> None:
    atomic_write_json(paths.cores_check_file, {
        "at": time.time(), "error": "",
        "xray": {"installed": "26.3.27", "latest": {"version": version, "prerelease": True,
                                                    "published": "2026-10-23T10:00:00Z"},
                 "withdrawn": False, "error": ""},
    })


def test_panel_card_shows_the_offer_and_the_previous_version(panel_rig):
    card = panel_rig.client.state()["cores"]
    assert [row["core"] for row in card["rows"]] == ["xray"]  # sing-box не установлен
    row = card["rows"][0]
    assert row["installed"] == "26.3.27" and row["latest"] is None and row["previous"] == ""
    assert card["checked"] is None and card["active"] is False
    _offer(panel_rig.paths)
    _watched(panel_rig.paths, "xray", "26.3.20", time.time() + 3600)
    row = panel_rig.client.state()["cores"]["rows"][0]
    assert row["latest"]["version"] == "26.10.30" and row["previous"] == "26.3.20"
    assert row["watch_until"] > time.time()


def test_panel_update_starts_the_job_only_for_the_offered_release(panel_rig):
    user = panel_rig.client
    result = user.act("cores/update", {"core": "xray", "version": "26.10.30"})
    assert not result["ok"] and "Проверить сейчас" in result["text"]
    _offer(panel_rig.paths)
    result = user.act("cores/update", {"core": "xray", "version": "26.10.30"})
    assert result["ok"], result
    assert ("systemctl", "start", "--no-block", "xgw-core.service") in panel_rig.system_calls
    request = json.loads(panel_rig.paths.cores_request_file.read_text(encoding="utf-8"))
    assert request == {**request, "core": "xray", "action": "update", "version": "26.10.30"}
    assert user.state()["cores"]["active"] is True
    again = user.act("cores/update", {"core": "xray", "version": "26.10.30"})
    assert not again["ok"] and "уже идёт" in again["text"]
    events = _events(panel_rig.paths)
    assert any("обновление Xray до 26.10.30 запущено из панели" in e for e in events)


def test_panel_rollback_needs_a_previous_version_and_root(panel_rig):
    user = panel_rig.client
    result = user.act("cores/rollback", {"core": "xray"})
    assert not result["ok"] and "возвращаться не к чему" in result["text"]
    _watched(panel_rig.paths, "xray", "26.3.20", time.time() + 3600)
    panel_rig.root_problem = "нужны права root: sudo xgw …"
    assert not user.act("cores/rollback", {"core": "xray"})["ok"]
    panel_rig.root_problem = None
    result = user.act("cores/rollback", {"core": "xray"})
    assert result["ok"] and "Возвращаю Xray 26.3.20" in result["text"]
    assert not user.act("cores/rollback", {"core": "v2ray"})["ok"]


def test_panel_check_button_asks_the_daemon(panel_rig):
    assert panel_rig.client.act("cores/check", {})["ok"]
    assert panel_rig.daemon.asked == ["cores"]


# --- xgw cores -------------------------------------------------------------------------


def test_cores_command_prints_the_card_and_runs_the_job(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    paths.config_file.write_text("", encoding="utf-8")
    assert cli.main(["cores"]) == 0
    out = capsys.readouterr().out
    assert "Xray: не установлен" in out and "ещё не проверялись" in out
    calls = []
    monkeypatch.setattr(cores.Job, "run", lambda self, core, action, version="", reason="":
                        calls.append((core, action, version, reason)) or 0)
    assert cli.main(["cores", "rollback", "sing-box"]) == 0
    assert cli.main(["cores", "update", "xray", "--version", "26.10.30"]) == 0
    assert calls == [("sing-box", "rollback", "", "cli"), ("xray", "update", "26.10.30", "cli")]
    atomic_write_json(paths.cores_request_file, {"core": "xray", "action": "rollback"})
    assert cli.main(["cores", "run-job"]) == 0
    assert calls[-1] == ("xray", "rollback", "", "panel")


# --- живые проверки (настоящие бинарники) ---------------------------------------------


@pytest.mark.skipif(not os.environ.get("XGW_XRAY_BIN"),
                    reason="нет XGW_XRAY_BIN — проверка живым Xray пропущена")
def test_xray_precheck_with_the_real_binary(tmp_path):
    paths = _paths(tmp_path)
    adapter = cores.XrayAdapter(config.Config(), paths)
    real = Path(os.environ["XGW_XRAY_BIN"])
    version = adapter.version(real)
    assert version == cores.parse(config.XRAY_VERSION)
    assert adapter.precheck(real, version) == ""
    assert "а не 26.10.30" in adapter.precheck(real, (26, 10, 30))


class _ClashApi(http.server.BaseHTTPRequestHandler):
    seen: ClassVar[list[tuple[str, str]]] = []
    alive: ClassVar[set[str]] = set()

    def do_GET(self):
        type(self).seen.append((self.path, self.headers.get("Authorization", "")))
        tag = self.path.split("/")[2]
        if tag in type(self).alive:
            body, code = b'{"delay": 120}', 200
        else:
            body, code = b'{"message": "timeout"}', 504
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_singbox_e2e_asks_its_clash_api_about_the_servers_it_carries(tmp_path):
    paths = _paths(tmp_path)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ClashApi)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        cfg = config.Config()
        cfg.core.api_port = server.server_address[1]
        atomic_write_json(paths.singbox_config_file, {
            "route": {"rules": [
                {"inbound": ["in-a"], "action": "route", "outbound": "out-a"},
                {"inbound": ["in-b"], "action": "route", "outbound": "out-b"},
                {"action": "reject"},
            ]},
            "experimental": {"clash_api": {"secret": "s3cr3t"}},
        })
        adapter = cores.SingboxAdapter(cfg, paths)
        _ClashApi.alive = {"out-b"}
        assert adapter.probe() == ["out-b"]
        path, auth = _ClashApi.seen[0]
        assert path.startswith("/proxies/out-a/delay?url=") and auth == "Bearer s3cr3t"
        assert adapter.verify(["out-b"]) == ""
        _ClashApi.alive = set()
        assert adapter.probe() is None
    finally:
        server.shutdown()

