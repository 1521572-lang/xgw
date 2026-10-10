"""Сквозные тесты xgw generate без сети: manual-ссылки и подписки из файла."""

import json
import logging

import links
import pytest

from xgw import cli
from xgw.cli import main
from xgw.paths import Paths
from xgw.store import Store


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    monkeypatch.delenv("XGW_XRAY_BIN", raising=False)
    return tmp_path


def _write_config(root, body: str):
    path = root / "config.toml"
    tail = '\n[filters]\nexclude_regex = ""\nmax_members = 2\n[dns]\nbootstrap = []\n'
    path.write_text(body + tail, encoding="utf-8")
    return path


def _manual(link_list) -> str:
    return "[manual]\nlinks = [" + ", ".join(f'"{link}"' for link in link_list) + "]\n"


def _subscription(root, link_list) -> str:
    source = root / "sub.txt"
    source.write_text("\n".join(link_list), encoding="utf-8")
    return f'[[subscriptions]]\nname = "main"\nurl = "{source.as_uri()}"\n'


def _generate(config, *extra) -> int:
    return main(["generate", "--config", str(config), "--no-validate", *extra])


def test_generate_manual_only(root, capsys):
    config = _write_config(root, _manual(links.FULL_LINKS))
    out = root / "out" / "config.json"
    assert _generate(config, "--out", str(out)) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    tags = [outbound["tag"] for outbound in payload["outbounds"]]
    assert tags[0].startswith("proxy-")
    assert payload["routing"]["balancers"][0]["selector"] == ["proxy-"]
    assert "участники" in capsys.readouterr().out
    nodes = Store(Paths.from_env().db_file).all_nodes()
    assert {node["role"] for node in nodes} == {"proxy", "spare"}
    assert all(node["name"] and node["address"] and node["port"] for node in nodes)


def test_generate_no_servers_fails(root):
    config = _write_config(root, "[manual]\nlinks = []\n")
    assert _generate(config, "--out", str(root / "c.json")) == 1


def test_generate_does_not_touch_applied_config(root):
    """generate без --out пишет рядом с рабочим конфигом, но не поверх него:
    иначе Applier счёл бы новый конфиг уже применённым."""
    config = _write_config(root, _manual(links.FULL_LINKS))
    assert _generate(config) == 0
    paths = Paths.from_env()
    assert paths.generated_config_file.exists()
    assert not paths.xray_config_file.exists()


def test_broken_subscription_falls_back_to_cache(root, caplog):
    """Пустой или битый ответ кэш не затирает: серверы берутся из последней удачной версии."""
    source = root / "sub.txt"
    config = _write_config(root, _subscription(root, links.FULL_LINKS))
    out = root / "config.json"
    assert _generate(config, "--out", str(out)) == 0
    good = json.loads(out.read_text(encoding="utf-8"))

    source.write_text("<html>502 Bad Gateway</html>", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="xgw"):
        assert _generate(config, "--out", str(out)) == 0
    assert "используется кэш" in caplog.text
    again = json.loads(out.read_text(encoding="utf-8"))
    assert [o["tag"] for o in again["outbounds"]] == [o["tag"] for o in good["outbounds"]]

    source.unlink()  # подписка недоступна вовсе — тоже кэш
    assert _generate(config, "--out", str(out)) == 0


def test_subscription_failure_without_cache_fails(root):
    config = _write_config(root, _subscription(root, ["not a link"]))
    assert _generate(config, "--out", str(root / "c.json")) == 1


def test_subscription_quota_is_stored(root):
    body = "#subscription-userinfo: upload=10; download=20; total=1000; expire=1798761600\n"
    config = _write_config(root, _subscription(root, [body.strip(), *links.FULL_LINKS]))
    assert _generate(config, "--out", str(root / "c.json")) == 0
    quota = json.loads(Store(Paths.from_env().db_file).get_meta("quota"))
    assert quota == {"main": {"upload": 10, "download": 20, "total": 1000, "expire": 1798761600}}


def test_regenerate_keeps_members_ports_and_password(root):
    """Новый сервер в подписке не перетасовывает участников и не меняет то, что
    уже работает в ядре: состав, порты и пароль probe-inbounds."""
    paths = Paths.from_env()
    config = _write_config(root, _manual(links.FULL_LINKS))
    assert _generate(config, "--out", str(paths.xray_config_file)) == 0  # «применённый»
    applied = json.loads(paths.xray_config_file.read_text(encoding="utf-8"))

    config = _write_config(root, _manual([*links.FULL_LINKS, links.TROJAN_INSECURE]))
    assert _generate(config) == 0
    fresh = json.loads(paths.generated_config_file.read_text(encoding="utf-8"))

    def members(payload):
        return [o["tag"] for o in payload["outbounds"] if o["tag"].startswith("proxy-")]

    def probes(payload):
        return {i["tag"]: (i["port"], i["settings"]) for i in payload["inbounds"]
                if i["tag"].startswith("probe-")}

    assert members(fresh) == members(applied)
    assert all(probes(fresh)[tag] == value for tag, value in probes(applied).items())
    assert len(probes(fresh)) == len(probes(applied)) + 1


def test_server_rejected_by_xray_is_dropped(root, monkeypatch, caplog):
    """Один сервер, который установленный Xray не принимает, не блокирует всю подписку."""
    bad = "203.0.113.20"  # links.TROJAN
    config = _write_config(root, _manual(links.FULL_LINKS))

    def fake_validate(payload, _xray_bin):
        text = json.dumps(payload)
        return (False, "unknown transport") if bad in text else (True, "Configuration OK")

    def fake_invalid(outbounds, _xray_bin):
        return {o["tag"]: "unknown transport" for o in outbounds if bad in json.dumps(o)}

    monkeypatch.setattr(cli.validate, "find_xray", lambda *_args: root / "xray")
    monkeypatch.setattr(cli.validate, "validate_config", fake_validate)
    monkeypatch.setattr(cli.validate, "find_invalid_outbounds", fake_invalid)
    out = root / "c.json"
    with caplog.at_level(logging.WARNING, logger="xgw"):
        assert main(["generate", "--config", str(config), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert bad not in json.dumps(payload)
    assert len([i for i in payload["inbounds"] if i["tag"].startswith("probe-")]) == 3
    assert "отброшен" in caplog.text


def test_invalid_config_without_culprit_fails(root, monkeypatch):
    config = _write_config(root, _manual(links.FULL_LINKS))
    monkeypatch.setattr(cli.validate, "find_xray", lambda *_args: root / "xray")
    monkeypatch.setattr(cli.validate, "validate_config", lambda *_args: (False, "bad routing"))
    monkeypatch.setattr(cli.validate, "find_invalid_outbounds", lambda *_args: {})
    out = root / "c.json"
    assert main(["generate", "--config", str(config), "--out", str(out)]) == 1
    assert not out.exists()


def test_bad_regex_in_config_does_not_crash(root):
    config = root / "config.toml"
    config.write_text(
        _manual(links.FULL_LINKS)
        + '[filters]\ninclude_regex = "(["\nexclude_regex = ""\n[dns]\nbootstrap = []\n',
        encoding="utf-8",
    )
    assert _generate(config, "--out", str(root / "c.json")) == 0
