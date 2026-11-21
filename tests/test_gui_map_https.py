"""Exercise the deployment HTTPS check without accessing the network or installing files."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "docs/helpers/run_gui_map_refresh.sh"


@pytest.mark.parametrize(("curl_rc", "status", "accepted"), [
    (0, "200", True),
    (0, "204", True),
    (0, "301", False),
    (0, "503", False),
    (47, "301", False),
    (35, "000", False),
])
def test_map_deploy_https_uses_final_success_and_reports_failures(tmp_path, curl_rc, status, accepted):
    curl = tmp_path / "curl"
    curl.write_text(
        '#!/bin/bash\n'
        'printf "%s\\n" "$@" >"$CURL_ARGUMENTS"\n'
        'printf "%s" "$CURL_STATUS"\n'
        'exit "$CURL_RESULT"\n',
        encoding="utf-8",
    )
    curl.chmod(0o700)
    arguments = tmp_path / "arguments"
    result = subprocess.run(
        ["bash", str(SCRIPT), "--check-https"], check=False,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CURL_ARGUMENTS": str(arguments),
            "CURL_STATUS": status,
            "CURL_RESULT": str(curl_rc),
        },
        capture_output=True, text=True, timeout=3,
    )
    assert result.returncode == (0 if accepted else 2)
    if accepted:
        assert f"MAP_HTTPS_CONTROL_OK standalone HTTP {status}" in result.stdout
    else:
        assert f"MAP_HTTPS_CONTROL_FAILED standalone CURL_RC {curl_rc} HTTP {status}" in result.stderr
    args = arguments.read_text(encoding="utf-8").splitlines()
    assert args[args.index("--proto") + 1] == "=https"
    assert args[args.index("--proto-redir") + 1] == "=https"
    assert args[args.index("--max-redirs") + 1] == "2" and "--location" in args
    assert args[args.index("--resolve") + 1] == "one.one.one.one:443:1.1.1.1"
    assert args[-1] == "https://one.one.one.one/"
