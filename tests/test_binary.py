"""Тесты загрузчика Xray: версии, выбор файла релиза, SHA-256 (без сети)."""

import hashlib

from xgw.xraycore.binary import (
    MIN_VERSION,
    Release,
    parse_version,
    pick_asset,
    verify_sha256,
    version_ok,
)


def test_parse_version():
    assert parse_version("v25.7.23") == (25, 7, 23)
    assert parse_version("25.10.1") == (25, 10, 1)
    assert parse_version("v26.1") == (26, 1, 0)


def test_version_ok():
    assert not version_ok("v25.6.8")
    assert version_ok("v25.7.23")
    assert version_ok("v26.4.13")
    assert MIN_VERSION == (25, 7, 23)


def test_pick_asset_case_insensitive():
    release = Release(
        tag="v25.7.23",
        assets={
            "Xray-Linux-64.zip": "u1",
            "Xray-linux-arm64-v8a.zip": "u2",
            "Xray-windows-64.zip": "u3",
        },
    )
    assert pick_asset(release, "linux", "x86_64") == "Xray-Linux-64.zip"
    assert pick_asset(release, "linux", "aarch64") == "Xray-linux-arm64-v8a.zip"
    assert pick_asset(release, "windows", "x86_64") == "Xray-windows-64.zip"
    assert pick_asset(release, "darwin", "x86_64") is None


def test_verify_sha256():
    data = b"xray-payload"
    good = hashlib.sha256(data).hexdigest()
    assert verify_sha256(data, f"SHA256 = {good}\n")
    assert not verify_sha256(data, "0" * 64)
