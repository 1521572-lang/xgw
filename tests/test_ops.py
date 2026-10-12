"""Обслуживание: `xgw logs --export`, `xgw update-xray`, конфиг DHCP и команды CLI этапа 4."""

import io
import json
import os
import tarfile
import threading
import time
from pathlib import Path

import links
import pytest
from fakesys import FakeSystem

from xgw import cli, config, engine, logs, managed
from xgw.cli import _sync_panel as REAL_SYNC_PANEL
from xgw.cli import main
from xgw.net import dnsmasq, lan
from xgw.paths import Paths
from xgw.store import Store
from xgw.xraycore import binary, update
from xgw.xraycore.api import ApiError

REPO = Path(__file__).resolve().parents[1]
UUID = "11111111-2222-3333-4455-666666666661"
BOT_TOKEN = "123456789:AAFakeFakeFakeFakeFakeFakeFakeFakeFake"
SUB_URL = "https://panel.example.com/sub/s3cr3t-subscription-token"
SHORT_PASSWORD = "pa55"


# --- экспорт логов ------------------------------------------------------------------


def _members(path: Path) -> dict[str, str]:
    with tarfile.open(path, mode="r:gz") as archive:
        return {
            member.name: archive.extractfile(member).read().decode("utf-8")
            for member in archive.getmembers()
        }


def test_log_export_contains_no_secrets(tmp_path):
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    cfg = config.Config()
    cfg.subscriptions = [config.Subscription(url=SUB_URL, headers={"x-hwid": "hw-1d-77"})]
    cfg.notify.telegram_bot_token = BOT_TOKEN
    cfg.status.token = "page-token-12345"
    config_text = (
        f'[[subscriptions]]\nurl = "{SUB_URL}"\nheaders = {{ "x-hwid" = "hw-1d-77" }}\n'
        f'[manual]\nlinks = ["{links.FULL_LINKS[0]}"]\n'
        f'[notify]\ntelegram_bot_token = "{BOT_TOKEN}"\n[status]\ntoken = "page-token-12345"\n'
    )
    paths.config_file.write_text(config_text, encoding="utf-8")
    applied = {"outbounds": [
        {"tag": "proxy-nl-1", "protocol": "vless", "settings": {"vnext": [
            {"address": "nl.example.com", "port": 443, "users": [{"id": UUID}]}]}},
        {"tag": "proxy-ss-2", "protocol": "shadowsocks", "settings": {"servers": [
            {"address": "203.0.113.9", "port": 8388, "password": SHORT_PASSWORD}]}},
    ]}
    paths.xray_config_file.write_text(json.dumps(applied), encoding="utf-8")
    paths.status_file.write_text('{"state": "HEALTHY"}', encoding="utf-8")
    paths.panel_token_file.write_text("pnl-tkn-9\n", encoding="ascii")
    store = Store(paths.db_file)
    store.add_event("apply", f"подписка {SUB_URL}")
    store.close()

    def runner(argv, **_kwargs):
        if argv[0] == "journalctl":
            return (
                f"xgw.daemon: узел {UUID} пароль {SHORT_PASSWORD} заголовок hw-1d-77\n"
                f"xray: {links.FULL_LINKS[0]}\nxgw: бот {BOT_TOKEN}, страница page-token-12345\n"
                "sudo: COMMAND=xgw panel, ссылка http://127.0.0.1:8781/?token=pnl-tkn-9\n"
            )
        return f"вывод {' '.join(argv)}\n"

    out_path = tmp_path / "logs.tar.gz"
    names = logs.export(cfg, paths, out_path, runner=runner,
                        diag_text=lambda: f"OK  Конфиг: {SUB_URL}")
    assert names == ["config.toml", "diag.txt", "journal.txt", "network.txt", "state.json",
                     "status.json", "versions.txt", "xray-config.json"]
    members = _members(out_path)
    whole = "\n".join(members.values())
    for secret in (UUID, SHORT_PASSWORD, "hw-1d-77", BOT_TOKEN, "page-token-12345",
                   "s3cr3t-subscription-token", links.FULL_LINKS[0], "pnl-tkn-9"):
        assert secret not in whole, secret
    # Полезное для разбора при этом остаётся.
    assert "****6661" in members["xgw-logs/journal.txt"]
    assert "panel.example.com" in members["xgw-logs/config.toml"]
    assert "nl.example.com" in members["xgw-logs/xray-config.json"]
    assert '"password": "***"' in members["xgw-logs/xray-config.json"]
    assert "вывод ip -br addr" in members["xgw-logs/network.txt"]
    if os.name != "nt":
        assert out_path.stat().st_mode & 0o777 == 0o600


def test_log_export_survives_missing_pieces(tmp_path):
    paths = Paths(root=tmp_path / "root")

    def runner(argv, **_kwargs):
        raise logs.cmd.CommandError(f"{argv[0]}: программа не найдена")

    names = logs.export(None, paths, tmp_path / "x.tar.gz", runner=runner,
                        diag_text=lambda: 1 / 0)
    members = _members(tmp_path / "x.tar.gz")
    assert "config.toml" in names and "не прочитан" in members["xgw-logs/config.toml"]
    assert "программа не найдена" in members["xgw-logs/journal.txt"]
    assert "diag не выполнен" in members["xgw-logs/diag.txt"]


def test_journal_command_covers_all_units():
    args = logs.journal_args(50, follow=True)
    assert args[:2] == ["journalctl", "--no-pager"] and args[-1] == "-f"
    assert [args[i + 1] for i, item in enumerate(args) if item == "-u"] == [
        "xgw-net.service", "xgw-xray.service", "xgw.service"]


# --- обновление Xray ----------------------------------------------------------------


class Updater:
    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        self.paths = Paths(root=tmp_path)
        self.paths.ensure()
        self.cfg = config.Config()
        self.name = self.paths.xray_bin.name
        self.paths.xray_dir.mkdir(parents=True)
        self.paths.xray_bin.write_bytes(b"old httpMethod")
        (self.paths.xray_dir / "geoip.dat").write_bytes(b"old-geo")
        self.paths.xray_config_file.write_text('{"outbounds": []}', encoding="utf-8")
        self.release = binary.Release("v26.4.13", {"x": "y"})
        self.new_bytes = b"new httpMethod"
        self.verdict = (True, "")
        self.api_ok = [True]
        self.restarts = 0
        self.stops = 0
        self.out: list[str] = []
        self.downloads = 0
        versions = {b"old": (26, 3, 27), b"new": (26, 4, 13), b"anc": (25, 6, 8)}
        monkeypatch.setattr(
            update.binary, "installed_version",
            lambda path: versions.get(Path(path).read_bytes()[:3]),
        )
        monkeypatch.setattr(update.validate, "validate_config", lambda *args: self.verdict)
        monkeypatch.setattr(update.engine, "bypass_mark", lambda cfg, logger: None)
        updater = self

        class Service:
            def restart(self):
                updater.restarts += 1

            def stop(self):
                updater.stops += 1
                # Останавливают ядро раньше, чем трогают его каталог.
                assert updater.paths.xray_bin.read_bytes() == b"old httpMethod"

        class Api:
            def balancer_info(self, tag):
                # Отвечает ли ядро — зависит от того, какой бинарник сейчас на месте.
                index = min(updater.restarts - 1, len(updater.api_ok) - 1)
                if not updater.api_ok[index]:
                    raise ApiError("нет связи с ядром")

        monkeypatch.setattr(update.engine, "make_service", lambda *args: Service())
        monkeypatch.setattr(update.engine, "make_api", lambda *args: Api())

    def download(self, dest, version, *, release=None, **_route):
        self.downloads += 1
        dest.mkdir(parents=True)
        (dest / self.name).write_bytes(self.new_bytes)
        (dest / "geoip.dat").write_bytes(b"new-geo")
        return release.tag, dest / self.name

    def run(self) -> int:
        return update.update_xray(
            self.cfg, self.paths, out=self.out.append,
            get_release=lambda version, **route: self.release, download=self.download, wait=0.0,
        )

    def leftovers(self) -> list[str]:
        return sorted(item.name for item in self.paths.opt.iterdir())


@pytest.fixture()
def updater(tmp_path, monkeypatch):
    return Updater(tmp_path, monkeypatch)


def test_update_replaces_binary_and_restarts(updater):
    assert updater.run() == 0
    assert updater.paths.xray_bin.read_bytes() == b"new httpMethod"
    assert (updater.paths.xray_dir / "geoip.dat").read_bytes() == b"new-geo"
    assert updater.restarts == 1 and updater.leftovers() == ["xray"]
    assert updater.out == ["Xray обновлён и перезапущен: 26.3.27 → 26.4.13"]


@pytest.mark.parametrize("windows", [True, False])
def test_update_stops_xray_first_only_where_the_folder_is_locked(updater, monkeypatch, windows):
    """Windows не даёт переименовать каталог работающей программы: там ядро перед
    заменой останавливается. В Linux оно работает до самого перезапуска."""
    monkeypatch.setattr(update, "WINDOWS", windows)
    assert updater.run() == 0
    assert updater.stops == (1 if windows else 0) and updater.restarts == 1
    assert updater.paths.xray_bin.read_bytes() == b"new httpMethod"


def test_update_keeps_the_old_xray_when_files_cannot_be_replaced(updater, monkeypatch):
    monkeypatch.setattr(update, "WINDOWS", True)
    real_replace = os.replace

    def locked(source, target):
        if Path(source) == updater.paths.xray_dir:
            raise PermissionError("файл занят другим процессом")
        return real_replace(source, target)

    monkeypatch.setattr(update.os, "replace", locked)
    assert updater.run() == 1
    assert "не заменены" in updater.out[0] and "не тронута" in updater.out[0]
    assert updater.paths.xray_bin.read_bytes() == b"old httpMethod"
    assert updater.restarts == 1 and updater.leftovers() == ["xray"]  # ядро запущено снова


def test_update_is_a_no_op_for_the_same_version(updater):
    updater.release = binary.Release("v26.3.27", {"x": "y"})
    assert updater.run() == 0
    assert updater.downloads == 0 and updater.restarts == 0
    assert "уже нужная версия" in updater.out[0]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda u: setattr(u, "verdict", (False, "unknown field")), "не проходит xray run -test"),
        (lambda u: setattr(u, "new_bytes", b"new without the field"), "нет поля httpMethod"),
        (lambda u: setattr(u, "new_bytes", b"anc httpMethod"), "версия ниже 25.7.23"),
        (lambda u: setattr(u, "new_bytes", b"???"), "бинарник не запускается"),
    ],
)
def test_unsuitable_binary_is_rejected_before_replacing(updater, change, expected):
    change(updater)
    assert updater.run() == 1
    assert expected in updater.out[0] and "не тронута" in updater.out[0]
    assert updater.paths.xray_bin.read_bytes() == b"old httpMethod"
    assert updater.restarts == 0 and updater.leftovers() == ["xray"]


def test_update_returns_the_old_binary_if_the_new_one_does_not_start(updater):
    updater.api_ok = [False, True]  # новая версия молчит, прежняя отвечает
    assert updater.run() == 1
    assert updater.paths.xray_bin.read_bytes() == b"old httpMethod"
    assert (updater.paths.xray_dir / "geoip.dat").read_bytes() == b"old-geo"
    assert updater.restarts == 2 and updater.leftovers() == ["xray"]
    assert "не поднялся" in updater.out[0] and "возвращена версия 26.3.27" in updater.out[0]


def test_update_reports_download_failures(updater):
    def broken(*args, **kwargs):
        raise binary.BinaryError("SHA-256 архива не совпал с .dgst релиза")

    updater.download = broken
    assert updater.run() == 1
    assert "SHA-256" in updater.out[0]
    assert updater.paths.xray_bin.read_bytes() == b"old httpMethod"


def test_has_string_finds_a_needle_across_chunk_borders(tmp_path):
    path = tmp_path / "binary"
    path.write_bytes(b"a" * 1000 + b"httpMethod" + b"b" * 1000)
    for chunk in (7, 64, 1005, 4096):
        assert binary.has_string(path, b"httpMethod", chunk=chunk), chunk
    assert not binary.has_string(path, b"allowedNetwork", chunk=64)
    assert not binary.has_string(tmp_path / "нет", b"httpMethod")


# --- DHCP: файл конфига и аренды ------------------------------------------------------


def _lan_cfg() -> config.Config:
    cfg = config.Config()
    cfg.network.lan_if = "lan0"
    return cfg


def test_dnsmasq_conf_is_written_only_when_changed(tmp_path):
    paths, cfg = Paths(root=tmp_path), _lan_cfg()
    assert dnsmasq.write_conf(cfg, paths) == (True, [])
    path = dnsmasq.conf_path(paths)
    text = path.read_text(encoding="utf-8")
    # bind-dynamic: dnsmasq стартует и тогда, когда у карты ещё нет адреса.
    assert "port=0" in text and "bind-dynamic" in text and "bind-interfaces\n" not in text
    assert dnsmasq.write_conf(cfg, paths) == (False, [])
    cfg.network.dhcp_range = "192.168.50.110,192.168.50.160,6h"
    assert dnsmasq.write_conf(cfg, paths)[0] and "192.168.50.160,6h" in path.read_text("utf-8")
    cfg.network.lan_if = ""  # LAN убрали из конфига — раздавать адреса больше не нужно
    assert dnsmasq.write_conf(cfg, paths) == (True, [])
    assert not path.exists()


def test_leases_are_read_and_sorted_by_address(tmp_path):
    paths = Paths(root=tmp_path)
    assert dnsmasq.read_leases(paths) == []
    path = dnsmasq.leases_path(paths)
    path.parent.mkdir(parents=True)
    path.write_text(
        "1791628983 e2:1a:01:92:72:d5 192.168.50.139 * *\n"
        "1791628983 02:00:00:00:00:20 192.168.50.20 tv 01:02:00:00:00:00:20\n"
        "duid 00:01:00:01:2a:3b\n"
        "мусор\n",
        encoding="utf-8",
    )
    assert dnsmasq.read_leases(paths) == [
        {"expires": 1791628983, "mac": "02:00:00:00:00:20", "ip": "192.168.50.20", "name": "tv"},
        {"expires": 1791628983, "mac": "e2:1a:01:92:72:d5", "ip": "192.168.50.139", "name": ""},
    ]


def test_wan_is_the_default_route_interface_unless_configured():
    system, cfg = FakeSystem(), config.Config()
    assert lan.effective_wan(cfg, system) == "wan0"
    cfg.network.wan_if = "ppp0"
    assert lan.effective_wan(cfg, system) == "ppp0"
    cfg.network.wan_if = ""
    system.default_dev = ""
    assert lan.default_route_interface(system) == ""
    system.refuse["ip -j route"] = "нет прав"
    assert lan.default_route_interface(system) == ""


# --- CLI ----------------------------------------------------------------------------


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    monkeypatch.delenv("XGW_XRAY_BIN", raising=False)
    return Paths.from_env()


def test_install_without_config_creates_it_from_the_example(root, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: None)
    assert main(["install"]) == 1
    out = capsys.readouterr().out
    assert f"Создан {root.config_file}" in out and "sudo xgw install" in out
    assert root.config_file.read_text(encoding="utf-8") == (
        REPO / "config.example.toml").read_text(encoding="utf-8")
    if os.name != "nt":
        assert root.config_file.stat().st_mode & 0o777 == 0o600
    assert not root.journal_file.exists()


def test_install_refuses_foreign_config_path_broken_config_and_no_root(
    root, monkeypatch, capsys, tmp_path
):
    other = tmp_path / "other.toml"
    other.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: None)
    assert main(["install", "--config", str(other)]) == 2
    assert "положите конфиг туда" in capsys.readouterr().err
    root.etc.mkdir(parents=True)
    root.config_file.write_text("[network\n", encoding="utf-8")
    assert main(["install"]) == 2
    assert "ошибка чтения TOML" in capsys.readouterr().err
    assert root.config_file.read_text(encoding="utf-8") == "[network\n"  # не перезаписан
    monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: "нужны права root: sudo xgw …")
    assert main(["install"]) == 1 and main(["uninstall", "--yes"]) == 1


def test_uninstall_asks_before_touching_anything(root, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: None)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert main(["uninstall"]) == 1
    assert "Отменено." in capsys.readouterr().out


def test_diag_runs_without_config_and_reports_it(root, capsys):
    assert main(["diag", "--no-net", "--json"]) == 1
    checks = json.loads(capsys.readouterr().out)
    by_name = {check["name"]: check for check in checks}
    assert by_name["Конфиг"]["level"] == "FAIL"
    assert "конфиг не найден" in by_name["Конфиг"]["text"]
    assert main(["diag", "--no-net"]) == 1
    assert "Итог: OK" in capsys.readouterr().out


def test_other_commands_still_need_a_config(root, capsys):
    assert main(["status"]) == 2
    assert "конфиг не найден" in capsys.readouterr().err


def test_logs_export_command_writes_an_archive(root, tmp_path, capsys):
    root.etc.mkdir(parents=True)
    root.config_file.write_text(
        f'[[subscriptions]]\nurl = "{SUB_URL}"\n', encoding="utf-8"
    )
    out_path = tmp_path / "export.tar.gz"
    assert main(["logs", "--export", "--out", str(out_path)]) == 0
    assert f"архив без секретов: {out_path}" in capsys.readouterr().out
    members = _members(out_path)
    assert "s3cr3t-subscription-token" not in "\n".join(members.values())
    assert "xgw-logs/diag.txt" in members and "xgw-logs/versions.txt" in members


def test_update_xray_command_reports_github_errors(root, monkeypatch, capsys):
    root.etc.mkdir(parents=True)
    root.config_file.write_text("", encoding="utf-8")

    def offline(*args, **kwargs):
        raise binary.BinaryError("GitHub API вернул HTTP 403")

    monkeypatch.setattr(update.binary, "get_release", offline)
    monkeypatch.setattr(update.engine, "bypass_mark", lambda cfg, logger: None)
    assert main(["update-xray"]) == 1
    assert "GitHub API вернул HTTP 403" in capsys.readouterr().out
    assert not root.xray_dir.exists()


def _write_gateway_config(path: Path, max_members: int) -> None:
    path.write_text(
        "[manual]\nlinks = [" + ", ".join(f'"{link}"' for link in links.FULL_LINKS) + "]\n"
        f'[filters]\nexclude_regex = ""\nmax_members = {max_members}\n'
        "[notify]\ndesktop = false\n[dns]\nbootstrap = []\n",
        encoding="utf-8",
    )


def test_daemon_rereads_changed_config_without_restarting(root, tmp_path, monkeypatch):
    """Правка config.toml подхватывается на ходу; с битым файлом демон работает дальше."""
    import xgw.daemon

    config_path = tmp_path / "config.toml"
    _write_gateway_config(config_path, 2)
    monkeypatch.setattr(cli.validate, "find_xray", lambda *args: tmp_path / "xray")
    # Без root демон правилами сети не управляет — и тест их не касается.
    monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: "нужны права root: sudo xgw …")
    seen: list[int] = []
    adopted: list[int] = []
    scripts = [
        lambda: _write_gateway_config(config_path, 3),  # правка
        lambda: config_path.write_text("[filters\n", encoding="utf-8"),  # опечатка
        None,  # остановка
    ]

    class FakeDaemon:
        def __init__(self, cfg, paths, *, xray_bin, capture=None, sinks=()):
            self.cfg = cfg
            assert capture is None and list(sinks) == []

        def adopt(self, previous) -> None:
            adopted.append(previous.cfg.filters.max_members)

        def run(self, stop: threading.Event, changed) -> None:
            seen.append(self.cfg.filters.max_members)
            assert not changed()
            script = scripts.pop(0)
            if script is None:
                stop.set()
                return
            script()
            stamp = time.time() + 10 * len(seen)
            os.utime(config_path, (stamp, stamp))
            assert changed()

    monkeypatch.setattr(xgw.daemon, "Daemon", FakeDaemon)
    assert main(["run", "--config", str(config_path)]) == 0
    assert seen == [2, 3, 3]
    # Новый демон получает прежний: при тех же подписках их незачем запрашивать заново.
    assert adopted == [2, 3]


def test_daemon_reloads_capture_rules_after_config_change(root, tmp_path, monkeypatch):
    """Правка bypass_hosts или exclude_cidrs доходит до ядра без команд пользователя."""
    from fakenet import FakeKernel

    import xgw.daemon

    kernel = FakeKernel()
    proc = tmp_path / "proc"
    (proc / "net/ipv4").mkdir(parents=True)
    (proc / "net/ipv4/ip_forward").write_text("0", encoding="ascii")
    real_capture = cli.capture_for
    monkeypatch.setattr(
        cli, "capture_for",
        lambda cfg, paths, **kwargs: real_capture(
            cfg, paths, runner=kernel, proc_sys=proc, time_uids=(), **kwargs),
    )
    monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: None)
    monkeypatch.setattr(cli.validate, "find_xray", lambda *args: tmp_path / "xray")
    config_path = tmp_path / "config.toml"
    _write_gateway_config(config_path, 2)
    runs: list[bool] = []

    class FakeDaemon:
        def __init__(self, cfg, paths, *, xray_bin, capture=None, sinks=()):
            assert capture is not None  # перехват трафика самой машины включён по умолчанию

        def adopt(self, previous) -> None:
            pass

        def run(self, stop: threading.Event, changed) -> None:
            runs.append(bool(kernel.table))
            if len(runs) == 2:
                stop.set()
                return
            with config_path.open("a", encoding="utf-8") as handle:
                handle.write('[capture]\nexclude_cidrs = ["198.51.100.0/24"]\n')
            stamp = time.time() + 10
            os.utime(config_path, (stamp, stamp))

    monkeypatch.setattr(xgw.daemon, "Daemon", FakeDaemon)
    assert main(["run", "--config", str(config_path)]) == 0
    # До правки демон правил не трогал (их грузит xgw-net), после — загрузил заново.
    assert runs == [False, True]
    assert "198.51.100.0/24" in kernel.table


def test_apply_on_installed_gateway_syncs_rules_and_dhcp(root, tmp_path, monkeypatch, capsys):
    from fakenet import FakeKernel

    kernel, system = FakeKernel(), FakeSystem()
    proc = tmp_path / "proc"
    (proc / "net/ipv4").mkdir(parents=True)
    (proc / "net/ipv4/ip_forward").write_text("0\n", encoding="ascii")
    real_capture = cli.capture_for
    monkeypatch.setattr(
        cli, "capture_for",
        lambda cfg, paths, **kwargs: real_capture(
            cfg, paths, runner=kernel, proc_sys=proc, time_uids=(), **kwargs),
    )
    monkeypatch.setattr(cli.cmd, "run", system)
    monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: None)
    cfg = _lan_cfg()
    logger = cli.log.get_logger("test")

    cli._sync_network(cfg, root, logger)
    assert not kernel.calls and not system.calls  # XGW не установлен — сеть не трогаем

    root.backup_dir.mkdir(parents=True)
    root.journal_file.write_text("{}", encoding="utf-8")
    cli._sync_network(cfg, root, logger)
    assert "tproxy" in kernel.table
    assert dnsmasq.conf_path(root).exists()
    assert system.calls == [("systemctl", "restart", "dnsmasq.service")]
    assert "dnsmasq: настройки DHCP обновлены" in capsys.readouterr().out
    cli._sync_network(cfg, root, logger)
    assert len(system.calls) == 1  # конфиг DHCP не менялся — dnsmasq не перезапускается


def test_engine_config_secrets_cover_tokens_and_headers():
    cfg = config.Config()
    cfg.subscriptions = [config.Subscription(url=SUB_URL, headers={"x-hwid": "hw-1d-77"})]
    cfg.notify.telegram_bot_token = BOT_TOKEN
    cfg.status.token = "page-token"
    assert set(engine.config_secrets(cfg)) == {BOT_TOKEN, "page-token", "hw-1d-77"}


def test_archive_members_are_private(tmp_path):
    path = tmp_path / "a.tar.gz"
    logs.write_archive(path, [("a.txt", "текст")])
    with tarfile.open(path, mode="r:gz") as archive:
        member = archive.getmembers()[0]
        assert member.name == "xgw-logs/a.txt" and member.mode == 0o600
        assert archive.extractfile(member).read() == "текст".encode()
    assert io.BytesIO(path.read_bytes()).read(2) == b"\x1f\x8b"


# --- панель: команда, запуск вместе с демоном, первый запуск установки ---------------


def test_panel_command_prints_the_link_with_the_token(root, capsys):
    from xgw.watch import panel

    root.etc.mkdir(parents=True)
    root.config_file.write_text("[panel]\nport = 8899\n", encoding="utf-8")
    assert main(["panel"]) == 0
    token = panel.read_token(root)
    assert token and f"Панель XGW: http://127.0.0.1:8899/?token={token}" in capsys.readouterr().out
    assert main(["panel"]) == 0 and panel.read_token(root) == token  # токен не меняется
    root.config_file.write_text("[panel]\nenabled = false\n", encoding="utf-8")
    assert main(["panel"]) == 2
    assert "панель выключена" in capsys.readouterr().err


def test_panel_open_waits_for_the_panel_and_starts_xgw_in_windows(root, capsys, monkeypatch):
    """`xgw panel --open` (ярлык): браузер открывается, когда панель уже отвечает; в
    Windows не запущенный XGW ярлык сначала запускает сам."""
    import socket

    from xgw import winapp
    from xgw.watch import panel

    opened: list[str] = []
    started: list[bool] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(cli, "PANEL_WAIT", 0.6)
    monkeypatch.setattr(cli, "WINDOWS", False)
    root.etc.mkdir(parents=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        root.config_file.write_text(f"[panel]\nport = {port}\n", encoding="utf-8")
        assert main(["panel", "--open"]) == 0
        token = panel.read_token(root)
        assert opened == [f"http://127.0.0.1:{port}/?token={token}"]
        assert capsys.readouterr().out == ""  # ссылка с токеном в терминал не печатается

        # Windows: демон не запущен — ярлык запускает его и только потом открывает панель.
        monkeypatch.setattr(cli, "WINDOWS", True)
        monkeypatch.setattr(winapp, "start_daemon", lambda paths: started.append(True) or True)
        assert main(["panel", "--open"]) == 0 and started == [True] and len(opened) == 2
        monkeypatch.setattr(winapp, "start_daemon", lambda paths: False)
        assert main(["panel", "--open"]) == 1 and len(opened) == 2
        assert "XGW не запустился" in capsys.readouterr().err
        monkeypatch.setattr(cli, "WINDOWS", False)
    # Панель не отвечает — браузер с пустой страницей не открывается.
    assert main(["panel", "--open"]) == 1 and len(opened) == 2
    assert "панель не отвечает" in capsys.readouterr().err


def test_shortcut_failures_show_a_window_when_there_is_no_console(root, monkeypatch):
    """Ярлык в меню «Пуск» запускает XGW без окна консоли: о любой ошибке — и о
    нечитаемом config.toml тоже — говорит окно с сообщением, а не строка в никуда."""
    import sys

    from xgw import winapp

    shown: list[str] = []
    monkeypatch.setattr(winapp, "alert", shown.append)
    monkeypatch.setattr(cli, "WINDOWS", True)
    root.etc.mkdir(parents=True)
    root.config_file.write_text("[panel\n", encoding="utf-8")
    assert main(["panel", "--open"]) == 2 and shown == []  # в терминале окно не нужно
    monkeypatch.setattr(sys, "stderr", None)
    assert main(["panel", "--open"]) == 2
    assert len(shown) == 1 and "ошибка чтения TOML" in shown[0]
    assert str(root.config_file) in shown[0]  # какой файл править — сказано
    assert main(["status"]) == 2 and len(shown) == 1  # другие команды окон не показывают
    assert main(["panel"]) == 2 and len(shown) == 1  # и панель без --open — тоже
    root.config_file.write_text("[panel]\nenabled = false\n", encoding="utf-8")
    assert main(["panel", "--open"]) == 2 and "панель выключена" in shown[-1]


def _free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _panel_answers(port: int) -> bool:
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", "/")
        return conn.getresponse().status == 200
    except OSError:
        return False
    finally:
        conn.close()


def test_daemon_serves_the_panel_and_keeps_it_across_reloads(root, tmp_path, monkeypatch):
    import xgw.daemon

    port = _free_port()
    config_path = tmp_path / "config.toml"
    config_path.write_text(f"[panel]\nport = {port}\n", encoding="utf-8")
    monkeypatch.setattr(cli.validate, "find_xray", lambda *args: tmp_path / "xray")
    monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: "нужны права root: sudo xgw …")
    panels: list = []

    def sync(panel, *args, **kwargs):
        panels.append(REAL_SYNC_PANEL(panel, *args, **kwargs))
        return panels[-1]

    monkeypatch.setattr(cli, "_sync_panel", sync)
    answers: list[bool] = []
    daemons: list = []

    class FakeDaemon:
        def __init__(self, cfg, paths, *, xray_bin, capture=None, sinks=()):
            self.poke = threading.Event()
            daemons.append(self)

        def adopt(self, previous) -> None:
            pass

        def run(self, stop: threading.Event, changed) -> None:
            answers.append(_panel_answers(port))
            assert panels[-1].daemon is self  # кнопки панели обращаются к текущему демону
            if len(daemons) == 2:
                stop.set()
                return
            # Подписка добавлена из панели — демон должен это заметить.
            managed.add_subscription(
                managed.path_for(config_path), "https://s.example.org/sub", taken=set())
            assert changed()

    monkeypatch.setattr(xgw.daemon, "Daemon", FakeDaemon)
    assert main(["run", "--config", str(config_path)]) == 0
    assert answers == [True, True] and len(daemons) == 2
    assert panels[0] is panels[1]  # панель одна, перечитывание её не перезапускает
    assert panels[0].cfg.managed.subscriptions == ["s.example.org"]
    assert not _panel_answers(port)  # вместе с демоном остановлена и панель


def test_busy_panel_port_does_not_stop_the_daemon(root, tmp_path, monkeypatch, caplog):
    import socket

    import xgw.daemon

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            f"[panel]\nport = {taken.getsockname()[1]}\n", encoding="utf-8")
        monkeypatch.setattr(cli.validate, "find_xray", lambda *args: tmp_path / "xray")
        monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: "нужны права root: sudo xgw …")
        monkeypatch.setattr(cli, "_sync_panel", REAL_SYNC_PANEL)
        ran: list[bool] = []

        class FakeDaemon:
            def __init__(self, cfg, paths, *, xray_bin, capture=None, sinks=()):
                pass

            def run(self, stop: threading.Event, changed) -> None:
                ran.append(True)
                stop.set()

        monkeypatch.setattr(xgw.daemon, "Daemon", FakeDaemon)
        if os.name == "nt":
            # В Windows SO_REUSEADDR позволил бы занять чужой порт; целевая система — Linux.
            monkeypatch.setattr("xgw.watch.panel._Server.allow_reuse_address", False)
        assert main(["run", "--config", str(config_path)]) == 0
    assert ran == [True] and "панель управления не запущена" in caplog.text


def test_first_install_run_asks_about_the_router_and_goes_on(root, monkeypatch, capsys):
    """Запуск человеком в терминале: файл править не нужно — карту спрашивает установка."""
    import xgw.install

    monkeypatch.setattr(cli, "_root_problem", lambda cfg=None: None)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(xgw.install, "choose_lan", lambda: "enp4s0")
    monkeypatch.setattr(cli, "_run_diag", lambda *args, **kwargs: [])
    seen: list[tuple] = []

    class FakeInstaller:
        def __init__(self, cfg, paths, **kwargs):
            seen.append((cfg.network.lan_if, cfg.subscriptions))

        def run(self, *, assume_yes, force):
            return 0

    monkeypatch.setattr(xgw.install, "Installer", FakeInstaller)
    assert main(["install"]) == 0
    assert seen == [("enp4s0", [])]
    assert 'lan_if = "enp4s0"' in root.config_file.read_text(encoding="utf-8")
    assert f"Создан {root.config_file}" in capsys.readouterr().out
    # С ключом --yes вопросов нет: файл создан, установка ждёт второго запуска.
    root.config_file.unlink()
    assert main(["install", "--yes"]) == 1 and len(seen) == 1
    assert 'lan_if = ""' in root.config_file.read_text(encoding="utf-8")
