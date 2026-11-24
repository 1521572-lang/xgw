"""Run ALT9 policy and worker preflight checks on a copy in a private netns."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

from xgw import config, managed, zapret2
from xgw.desync import flowseal, preflight, schema, worker
from xgw.net import cmd
from xgw.watch import zapret2_management as management


def require(check, reason):
    if not check:
        raise ValueError(reason)


def check_scope(cfg, domains, exclusions):
    args = zapret2.arguments(cfg)
    blocks = 1 + args.count("--new")
    positive = [entry for entry in args if entry.startswith("--hostlist-domains=")]
    hosts = ",".join(domain.removeprefix("domain:") for domain in domains)
    require(positive == ["--hostlist-domains=" + hosts] * blocks, "wrong_positive_scope")
    require(not any(entry.startswith(("--hostlist=", "--ipset=")) for entry in args), "wide_scope")
    if exclusions:
        require(args.count("--hostlist-exclude-domains=" + ",".join(exclusions)) == blocks,
                "missing_local_exclusion")
    preflight.check(args, cmd.run)
    return args, blocks


def run(root):
    path = root / "config.toml"
    with path.open("x", encoding="utf-8") as stream:
        stream.write('[capture]\nlocal=true\nfail_mode="closed"\nhold="block"\n'
                     '[network]\nquic_mode="reject"\n')
    panel = managed.path_for(path)

    def load():
        return config.load(path)[0]

    def send(action, payload, code, *, expected=None):
        if expected is None:
            expected = schema.fingerprint(load().desync)
        result = management.command(path, action, {"expected": expected, action: payload},
                                    ready=True, capture={"mode": "on"})
        require(result["code"] == code, f"{action}_expected_{code}_got_{result['code']}")
        return result["config_key"] if code in {"saved", "unchanged"} else None

    all_domains = list(flowseal.YOUTUBE_DOMAINS)
    send("settings", {"domains": all_domains}, "saved")
    import_key = send("import", flowseal.LIVE_STRATEGY, "saved")
    initial_standalone = send("mode", "standalone", "saved")
    base, blocks = check_scope(load(), all_domains, [])
    require(send("mode", "off", "saved") == import_key, "base_revision")
    print(f"FLOWSEAL_POLICY_BASE_OK blocks={blocks}", flush=True)

    domains = all_domains[:2]
    exclusions = ["example.googlevideo.com", "example.youtube.com"]
    patch = {"domains": domains, "flowseal_exclude_domains": exclusions}
    tryout_key = send("settings", patch, "saved")
    require(tryout_key != import_key, "update_revision")
    before = panel.read_bytes(), panel.stat().st_ino, panel.stat().st_mtime_ns
    require(send("settings", patch, "unchanged") == tryout_key, "repeat_revision")
    send("settings", {"flowseal_exclude_domains": ["example.com"]}, "invalid")
    send("settings", {"flowseal_exclude_domains": []}, "conflict", expected=import_key)
    require((panel.read_bytes(), panel.stat().st_ino, panel.stat().st_mtime_ns) == before,
            "rejection_wrote_policy")
    live = send("mode", "standalone", "saved")
    selected = load()
    _, scoped_blocks = check_scope(selected, domains, exclusions)
    require(scoped_blocks == blocks and worker.policy_revision(selected.zapret2) == live,
            "worker_revision")
    before = panel.read_bytes()
    send("settings", {"flowseal_exclude_domains": []}, "blocked")
    require(panel.read_bytes() == before, "active_edit_wrote_policy")
    print(f"FLOWSEAL_POLICY_NARROW_OK blocks={blocks} hosts={len(domains)} exclusions={len(exclusions)}",
          flush=True)

    send("mode", "off", "saved")
    send("settings", {"flowseal_exclude_domains": ["youtube.com", "googlevideo.com"]}, "saved")
    before = panel.read_bytes()
    send("mode", "standalone", "invalid")
    require(panel.read_bytes() == before, "empty_scope_wrote_policy")
    send("settings", {"flowseal_exclude_domains": exclusions}, "saved")
    send("settings", {"strategy": "multisplit"}, "saved")
    send("import", flowseal.LIVE_STRATEGY, "saved")
    reimported = load().zapret2
    require(reimported.flowseal_exclude_domains == exclusions and reimported.domains == domains,
            "reimport_changed_scope")
    require(send("settings", {"domains": all_domains, "flowseal_exclude_domains": []}, "saved") == import_key,
            "rollback_off_revision")
    require(send("mode", "standalone", "saved") == initial_standalone, "rollback_worker_revision")
    restored, _ = check_scope(load(), all_domains, [])
    require(restored == base, "rollback_arguments")
    require(send("mode", "off", "saved") == import_key, "final_off_revision")
    print("FLOWSEAL_POLICY_ROLLBACK_OK", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--host-netns", required=True, type=int)
    args = parser.parse_args()
    try:
        os.umask(0o077)
        net = Path("/proc/self/ns/net").stat().st_ino
        interfaces = {row.partition(":")[0].strip()
                      for row in Path("/proc/net/dev").read_text().splitlines()[2:]}
        require(os.geteuid() == 0 and net != args.host_netns and interfaces == {"lo"}, "netns_required")
        info = args.out.lstat()
        require(args.out.parent == Path("/run") and args.out.name.startswith("xgw-flowseal-policy.")
                and stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
                "private_output_required")
        run(args.out)
    except (OSError, ValueError, cmd.CommandError) as error:
        # Detailed paths and messages remain in the private stderr.
        print(f"FLOWSEAL_POLICY_FAILED {type(error).__name__}", flush=True)
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
