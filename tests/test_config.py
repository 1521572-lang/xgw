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
    # Подписка в примере закомментирована: её добавляют в панели либо вписывают сами.
    assert cfg.subscriptions == [] and cfg.panel.enabled and cfg.panel.port == 8781
    assert "example.com/sub/TOKEN" in EXAMPLE.read_text(encoding="utf-8")


def test_probe_bytes():
    assert probe_bytes("https://speed.cloudflare.com/__down?bytes=65536") == 65536
    assert probe_bytes("https://example.com/x") is None


def test_missing_file_raises():
    import pytest

    from xgw.config import ConfigError

    with pytest.raises(ConfigError):
        load(Path("Z:/nonexistent-xgw/config.toml"))


def _load_text(tmp_path, text: str):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return load(path)


def test_bad_values_are_replaced_not_fatal(tmp_path):
    """Значения, с которыми генерация упала бы, заменяются на безопасные с предупреждением."""
    cfg, warnings = _load_text(
        tmp_path,
        '[filters]\ninclude_regex = "(["\nexclude_regex = "*"\nmax_members = 0\n\n'
        '[probe]\nsampling = 0\ninterval = "5s"\n\n[apply]\nrestart_window = "ночью"\n',
    )
    assert cfg.filters.include_regex == ""
    assert cfg.filters.exclude_regex == Config().filters.exclude_regex
    assert cfg.filters.max_members == 1
    assert cfg.probe.sampling == 2
    assert cfg.apply.restart_window == "04:00-05:00"
    for needle in ("include_regex", "exclude_regex", "max_members", "sampling",
                   "меньше 10s", "restart_window"):
        assert any(needle in warning for warning in warnings), needle


def test_list_and_table_items_must_be_strings(tmp_path):
    cfg, warnings = _load_text(
        tmp_path,
        '[manual]\nlinks = [1, 2]\n\n[[subscriptions]]\nname = "a"\n'
        'url = "https://a.example.com/s"\nheaders = { x-hwid = 5 }\n',
    )
    assert cfg.manual.links == []
    assert cfg.subscriptions[0].headers == {}
    assert any("manual.links" in warning for warning in warnings)
    assert any("subscriptions.headers" in warning for warning in warnings)


def test_subscription_without_url_and_bad_ports_warn(tmp_path):
    _cfg, warnings = _load_text(
        tmp_path, '[[subscriptions]]\nname = "empty"\n\n[xray]\napi_port = 70000\n'
    )
    assert any("empty" in warning and "url" in warning for warning in warnings)
    assert any("api=70000" in warning for warning in warnings)


def test_dangerous_capture_values_are_replaced(tmp_path):
    """Метка 0 и системная таблица маршрутизации сломали бы сеть — не допускаются."""
    path = tmp_path / "config.toml"
    path.write_text(
        '[network]\nlan_if = "lan 0"\nwan_if = "eth0"\nlan_address = "шлюз"\n'
        "[capture]\nmark_proxy = 0\nmark_bypass = 2\nroute_table = 254\n",
        encoding="utf-8",
    )
    cfg, warnings = load(path)
    assert cfg.capture.mark_proxy == 1 and cfg.capture.mark_bypass == 2
    assert cfg.capture.route_table == 100  # 254 — это таблица main
    assert cfg.network.lan_address == "192.168.50.1/24"
    text = "\n".join(warnings)
    assert "capture.mark_proxy" in text and "capture.route_table=254" in text
    assert "network.lan_if='lan 0'" in text and "wan_if" not in text
    assert "network.lan_address" in text
