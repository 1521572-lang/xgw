"""Сквозной тест xgw generate без сети: только manual-ссылки."""

import json

import links

from xgw.cli import main


def test_generate_manual_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    config = tmp_path / "config.toml"
    config.write_text(
        "[manual]\nlinks = ["
        + ", ".join(f'"{link}"' for link in links.FULL_LINKS)
        + "]\n[filters]\nexclude_regex = \"\"\n",
        encoding="utf-8",
    )
    out = tmp_path / "out" / "config.json"
    code = main(["generate", "--config", str(config), "--out", str(out), "--no-validate"])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    tags = [outbound["tag"] for outbound in payload["outbounds"]]
    assert tags[0].startswith("proxy-")
    assert payload["routing"]["balancers"][0]["selector"] == ["proxy-"]
    summary = capsys.readouterr().out
    assert "участники" in summary


def test_generate_no_servers_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    config = tmp_path / "config.toml"
    config.write_text("[manual]\nlinks = []\n", encoding="utf-8")
    code = main(["generate", "--config", str(config), "--out", str(tmp_path / "c.json"),
                 "--no-validate"])
    assert code == 1
