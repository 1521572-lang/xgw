import dataclasses
from pathlib import Path

import pytest

from docs.helpers import nfq_lab
from xgw import nfqws2
from xgw.config import Config


def settings(**overrides):
    return {"binary": "/opt/xgw/nfqws2", "strategy": "hostfakesplit-md5",
            "reassembly": "standard", "debug": False, "domains": ["youtube.com"],
            **overrides}


def incoming(profile="seqovl"):
    inst = nfqws2.Installation(Path("/run/xgw-lab/nfqws2"), Path("/opt/xgw/lua"),
                              dict.fromkeys(nfqws2.BLOBS))
    inst = dataclasses.replace(inst, blobs={**inst.blobs, "stun.bin": Path("/opt/stun.bin")})
    return nfqws2.arguments(Config(), inst, profile)[1:]


def test_runtime_preflight_remains_non_intercepting_and_tls_only():
    for profile in nfqws2.PROFILES:
        source = incoming(profile)
        for preflight in ([], ["--intercept=0"]):
            result = nfq_lab.build_arguments(source + preflight, settings())
            assert result[1:5] == source[:4]
            assert (result[-1] == "--intercept=0") == bool(preflight)
            assert "--filter-tcp=443" in result
            assert "--hostlist-domains=youtube.com" in result
            assert not any(a.startswith(("--filter-udp", "--blob=")) for a in result)
            assert "--new" not in result


def test_passthrough_distinguishes_reassembly_from_lua_transformations():
    standard = nfq_lab.build_arguments(incoming(), settings(strategy="pass"))
    disabled = nfq_lab.build_arguments(incoming(), settings(strategy="pass", reassembly="disabled"))
    assert not any(a.startswith("--lua-desync=") for a in standard + disabled)
    assert "--reasm-disable=tls_client_hello" not in standard
    assert "--reasm-disable=tls_client_hello" in disabled


@pytest.mark.parametrize("option", ["--intercept=1", "--lua-init=os.execute('bad')",
                                    "--uid=0", "--qnum=3", "--debug=1"])
def test_unexpected_runtime_options_are_rejected(option):
    with pytest.raises(ValueError):
        nfq_lab.build_arguments([*incoming(), option], settings())


def test_settings_cannot_inject_command_options_or_arbitrary_lua():
    for changes in ({"strategy": "luaexec:code=bad"}, {"debug": "false"},
                    {"domains": []}, {"domains": ["a.com,--uid=0"]},
                    {"domains": ["127.0.0.1"]}, {"binary": "relative"},
                    {"extra": True}, {"domains": ["bad..com"]}):
        with pytest.raises(ValueError):
            nfq_lab.build_arguments(incoming(), settings(**changes))


def test_all_candidates_build_with_scoped_tls_and_no_shell():
    for name in nfq_lab.STRATEGIES:
        result = nfq_lab.build_arguments(incoming(), settings(strategy=name, debug=True))
        assert result[0] == "/opt/xgw/nfqws2"
        assert result.count("--filter-l7=tls") == 1
        assert result.count("--hostlist-domains=youtube.com") == 1
        assert "--debug=1" in result


def test_world_writable_ancestor_and_relative_path_rejected(tmp_path):
    path = tmp_path / "nfqws2.json"
    path.write_text("{}")
    path.chmod(0o600)
    # A root-owned file in /tmp still cannot authorize a root executable wrapper.
    with pytest.raises(ValueError):
        nfq_lab.secure_file(path, private=True)
    with pytest.raises(ValueError):
        nfq_lab.secure_file(Path("relative"))
