"""Тесты загрузчика Xray: версии, выбор файла релиза, SHA-256 (без сети)."""

import hashlib
import io
import json
import subprocess
import zipfile

import pytest

from xgw import fetch
from xgw.xraycore import binary
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


def test_verify_sha256_reads_only_the_sha256_line():
    """Формат .dgst релиза Xray; половина SHA2-512 за SHA-256 не принимается."""
    data = b"xray-payload"
    good = hashlib.sha256(data).hexdigest()
    dgst = f"MD5= {'0' * 32}\nSHA1= {'0' * 40}\nSHA2-256= {good}\nSHA2-512= {'0' * 128}\n"
    assert verify_sha256(data, dgst)
    assert verify_sha256(data, f"SHA256= {good.upper()}\n")
    fake = f"SHA2-256= {'1' * 64}\nSHA2-512= {good}{'0' * 64}\n"
    assert not verify_sha256(data, fake)


def test_installed_version(monkeypatch):
    def fake_run(stdout):
        def run(argv, **_kwargs):
            assert argv[1:] == ["version"]
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")
        return run

    banner = "Xray 26.3.27 (Xray, Penetrates Everything.) abcdef0 (go1.26 linux/amd64)\nA unified"
    monkeypatch.setattr(binary.subprocess, "run", fake_run(banner))
    assert binary.installed_version("xray") == (26, 3, 27)
    monkeypatch.setattr(binary.subprocess, "run", fake_run("something else"))
    assert binary.installed_version("xray") is None

    def missing(argv, **_kwargs):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(binary.subprocess, "run", missing)
    assert binary.installed_version("xray") is None


def test_download_release_verifies_and_installs(tmp_path, monkeypatch):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("xray", b"#!new-binary")
        bundle.writestr("geoip.dat", b"geo")
    payload = archive.getvalue()
    release = {
        "tag_name": "v26.3.27",
        "assets": [
            {"name": name, "browser_download_url": f"https://github.example/{name}"}
            for name in ("Xray-linux-64.zip", "Xray-linux-64.zip.dgst")
        ],
    }
    digest = {"value": hashlib.sha256(payload).hexdigest()}

    def fake_fetch(url, **_kwargs):
        if url.endswith("/latest"):
            body = json.dumps(release).encode()
        elif url.endswith(".dgst"):
            body = f"SHA2-256= {digest['value']}\n".encode()
        else:
            body = payload
        return fetch.FetchResult(status=200, headers={}, body=body, url=url)

    monkeypatch.setattr(binary.fetch, "fetch_url", fake_fetch)
    monkeypatch.setattr(binary, "platform_pair", lambda: ("linux", "x86_64"))
    dest = tmp_path / "xray"
    dest.mkdir()
    (dest / "xray").write_bytes(b"old-binary")
    tag, path = binary.download_release(dest)
    assert tag == "v26.3.27" and path == dest / "xray"
    assert path.read_bytes() == b"#!new-binary"
    # временных каталогов и архива после установки не остаётся
    assert sorted(item.name for item in dest.iterdir()) == ["geoip.dat", "xray"]

    digest["value"] = "0" * 64  # .dgst не сходится — рабочий бинарник остаётся на месте
    path.write_bytes(b"current")
    with pytest.raises(binary.BinaryError, match="SHA-256"):
        binary.download_release(dest)
    assert path.read_bytes() == b"current"

    release["tag_name"] = "v25.6.8"  # в этой версии ещё нет httpMethod
    with pytest.raises(binary.BinaryError, match="ниже требуемой"):
        binary.download_release(dest)
