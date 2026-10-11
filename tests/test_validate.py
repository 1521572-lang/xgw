"""Проверка конфига установленным Xray: версия, xray run -test, поиск плохих outbounds."""

import os
import subprocess

from xgw.generator import validate
from xgw.xraycore import binary

UUID = "11111111-2222-3333-4455-666666666661"


def _fake_xray(monkeypatch, *, version: str, reject: str = ""):
    """Подменяет запуск xray: `version` печатает баннер, `run -test` падает на конфиге,
    в котором встречается строка reject."""
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(list(argv))
        if argv[1] == "version":
            return subprocess.CompletedProcess(argv, 0, stdout=f"Xray {version} (Xray)", stderr="")
        with open(argv[-1], encoding="utf-8") as handle:
            text = handle.read()
        if reject and reject in text:
            error = f"Failed to start: unknown transport, user {UUID}, password tr0jan-pass"
            return subprocess.CompletedProcess(argv, 23, stdout="", stderr=error)
        return subprocess.CompletedProcess(argv, 0, stdout="Configuration OK.", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_no_binary_means_not_verified():
    verdict, output = validate.validate_config({}, None)
    assert verdict is None and "не найден" in output


def test_old_xray_is_refused_before_test(monkeypatch, tmp_path):
    """Xray старше 25.7.23 конфиг примет, но httpMethod проигнорирует — отказ заранее."""
    calls = _fake_xray(monkeypatch, version="25.6.8")
    verdict, output = validate.validate_config({"outbounds": []}, tmp_path / "xray")
    assert verdict is False
    assert "25.6.8" in output and binary.min_version_text() in output
    assert all(argv[1] == "version" for argv in calls)  # до run -test дело не дошло


def test_valid_and_invalid_config(monkeypatch, tmp_path):
    _fake_xray(monkeypatch, version="26.3.27", reject="h2")
    assert validate.validate_config({"outbounds": []}, tmp_path / "xray") == (
        True,
        "Configuration OK.",
    )
    bad = {
        "outbounds": [
            {
                "settings": {"servers": [{"password": "tr0jan-pass"}]},
                "streamSettings": {"network": "h2"},
            }
        ]
    }
    verdict, output = validate.validate_config(bad, tmp_path / "xray")
    assert verdict is False
    assert "unknown transport" in output
    # вывод Xray маскируется: и UUID, и пароль из самого конфига
    assert UUID not in output and "tr0jan-pass" not in output


def test_temp_config_is_removed(monkeypatch, tmp_path):
    calls = _fake_xray(monkeypatch, version="26.3.27")
    validate.validate_config({"outbounds": []}, tmp_path / "xray")
    config_path = calls[-1][-1]
    assert config_path.endswith(".json")
    assert not os.path.exists(config_path)


def test_find_invalid_outbounds(monkeypatch, tmp_path):
    _fake_xray(monkeypatch, version="26.3.27", reject="h2")
    outbounds = [
        {"tag": "proxy-nl-aaaa", "streamSettings": {"network": "tcp"}},
        {"tag": "spare-de-bbbb", "streamSettings": {"network": "h2"}},
    ]
    invalid = validate.find_invalid_outbounds(outbounds, tmp_path / "xray")
    assert list(invalid) == ["spare-de-bbbb"]
    assert "unknown transport" in invalid["spare-de-bbbb"]


def test_tun_inbound_is_renamed_for_the_check_and_dropped_without_root(monkeypatch):
    """`xray run -test` создаёт интерфейс из inbound tun; рабочий Xray держит интерфейс
    XGW открытым, поэтому проверка идёт с одноразовым именем (а без root — без inbound)."""
    config = {
        "inbounds": [
            {"tag": "tun-in", "protocol": "tun", "settings": {"name": "xgwtun0", "mtu": 1500}},
            {"tag": "http-in", "protocol": "http", "port": 10809},
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
    }
    monkeypatch.setattr(validate.os, "geteuid", lambda: 0, raising=False)
    checked = validate._for_test(config)
    assert checked is not config
    name = checked["inbounds"][0]["settings"]["name"]
    assert name.startswith("xgwchk") and name != "xgwtun0" and len(name) <= 15
    assert checked["inbounds"][0]["settings"]["mtu"] == 1500 and checked["inbounds"][1] == (
        config["inbounds"][1])
    assert config["inbounds"][0]["settings"]["name"] == "xgwtun0"  # исходный конфиг цел

    monkeypatch.setattr(validate.os, "geteuid", lambda: 1000, raising=False)
    assert [i["tag"] for i in validate._for_test(config)["inbounds"]] == ["http-in"]

    plain = {"inbounds": [{"tag": "http-in", "protocol": "http"}]}
    assert validate._for_test(plain) is plain  # без tun конфиг не копируется
    assert validate._for_test({"outbounds": []}) == {"outbounds": []}
