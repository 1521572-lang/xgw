"""Тесты загрузки config.toml: значения по умолчанию, неизвестные ключи, типы."""

from pathlib import Path

from xgw.config import Config, load, probe_bytes

EXAMPLE = Path(__file__).resolve().parents[1] / "config.example.toml"


def test_minimal_file_gives_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[network]\n", encoding="utf-8")
    cfg, warnings = load(path)
    assert warnings == []
    assert cfg.capture.tproxy_port == 12345
    assert cfg.probe.interval == "30s"
    assert cfg.routing.direct_ips == ["geoip:ru"]
    assert cfg.filters.max_members == 5
    assert cfg.dns.bootstrap[0] == "https://1.1.1.1/dns-query"


def test_unknown_keys_and_sections_warn(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[network]\nwan_if = "eth0"\nfoo = 1\n\n[nope]\nx = 1\n', encoding="utf-8"
    )
    cfg, warnings = load(path)
    assert cfg.network.wan_if == "eth0"
    assert any("network.foo" in warning for warning in warnings)
    assert any("nope" in warning for warning in warnings)


def test_wrong_type_falls_back_to_default(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[capture]\ntproxy_port = \"много\"\n", encoding="utf-8")
    cfg, warnings = load(path)
    assert cfg.capture.tproxy_port == 12345
    assert any("tproxy_port" in warning for warning in warnings)


def test_validation_warnings(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[capture]\nmark_proxy = 2\nmark_bypass = 2\n\n[probe]\ninterval = \"сразу\"\n",
        encoding="utf-8",
    )
    _cfg, warnings = load(path)
    assert any("mark_proxy" in warning for warning in warnings)
    assert any("interval" in warning for warning in warnings)


def test_subscriptions_list(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[[subscriptions]]\nname = \"a\"\nurl = \"https://a.example.com/s\"\n\n"
        "[[subscriptions]]\nname = \"b\"\nurl = \"file:///tmp/b.txt\"\nuser_agent = \"v2rayN/6\"\n",
        encoding="utf-8",
    )
    cfg, warnings = load(path)
    assert warnings == []
    assert [sub.name for sub in cfg.subscriptions] == ["a", "b"]
    assert cfg.subscriptions[1].user_agent == "v2rayN/6"


def test_example_config_loads_clean():
    cfg, warnings = load(EXAMPLE)
    assert warnings == []
    assert isinstance(cfg, Config)
    assert cfg.subscriptions and cfg.subscriptions[0].name == "main"


def test_probe_bytes():
    assert probe_bytes("https://speed.cloudflare.com/__down?bytes=65536") == 65536
    assert probe_bytes("https://example.com/x") is None


def test_missing_file_raises():
    import pytest

    from xgw.config import ConfigError

    with pytest.raises(ConfigError):
        load(Path("Z:/nonexistent-xgw/config.toml"))
