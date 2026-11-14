import dataclasses
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from xgw import nfqws2
from xgw.config import Config
from xgw.generator import fragment, profiles
from xgw.generator.builder import build, select_nodes
from xgw.model import ServerNode
from xgw.net import nft
from xgw.net.cmd import CommandError
from xgw.nfqws2 import find_installation


class WorkerHost:
    """systemd уже active, но очередь появляется только после нескольких опросов."""

    def __init__(self):
        self.active = False
        self.starts = self.stops = self.polls = 0
        self.now = 0.0
        self.flags = dict.fromkeys(nfqws2.OFFLOADS, True)
        self.flags["tcp-segmentation-offload"] = False
        self.fixed = {"tcp-segmentation-offload"}
        self.initial_flags = dict(self.flags)
        self.never_ready = False
        self.ignore_offload_writes = False
        self.offload_writes = []

    def sleep(self, seconds):
        self.now += seconds

    def occupied(self, queue):
        self.polls += 1
        return self.active and self.polls >= 3 and not self.never_ready

    def run(self, args, **kwargs):
        if args[:2] == ["systemctl", "is-active"]:
            return "active" if self.active else "inactive"
        if args[:2] == ["systemctl", "stop"]:
            self.stops += 1
            self.active = False
        elif args[0] == "systemd-run":
            self.starts += 1
            self.active, self.polls = True, 0
        elif args[:2] == ["ethtool", "-k"]:
            return "Features for test0:\nrx-checksumming: on\n\n" + "\n".join(
                f"\t{name}: {'on' if value else 'off'}"
                + (" [fixed]" if name in self.fixed else "")
                for name, value in self.flags.items()
            )
        elif args[:2] == ["ethtool", "-K"]:
            changes = {args[i]: args[i + 1] == "on" for i in range(3, len(args), 2)}
            self.offload_writes.append(changes)
            if self.fixed & changes.keys():
                raise CommandError("fixed feature")
            if not self.ignore_offload_writes:
                self.flags.update(changes)
        return ""


class GeneratorTests(unittest.TestCase):
    def test_micro_fragment_and_noise(self):
        cfg = Config()
        self.assertEqual(fragment.outbound(cfg)["settings"]["fragment"], {
            "packets": "tlshello", "length": "5-20", "interval": "5-15",
        })
        self.assertEqual(fragment.split_outbound(cfg)["settings"]["fragment"], {
            "packets": "1-3", "length": "10-30", "interval": "5-10",
        })
        noise = fragment.noise_outbound(cfg)
        self.assertEqual(noise["settings"]["noises"], [
            {"type": "rand", "packet": "64-1200", "delay": "5-15"},
        ] * 3)

    def test_noise_and_cloudflare_routes(self):
        cfg = Config()
        cfg.network.quic_mode = "noise"
        node = ServerNode(
            "0123abcd", "test", "de", "vless", "203.0.113.1", 443,
            {"protocol": "vless", "settings": {}}, "test",
        )
        config = build(cfg, select_nodes([node], cfg), hosts={}).config
        rules = config["routing"]["rules"]
        cloudflare = next(rule for rule in rules if rule.get("network") == "tcp")
        self.assertEqual(cloudflare, {
            "type": "field", "network": "tcp", "port": "2053,2083,2087,2096,8443",
            "balancerTag": "auto",
        })
        noise = next(rule for rule in rules if rule.get("outboundTag") == "direct-noise")
        self.assertEqual(noise["port"], "443,19294-19344,50000-50100,19302,3478")
        self.assertEqual(rules[-1], {
            "type": "field", "network": "tcp,udp", "balancerTag": "auto",
        })


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.installation = nfqws2.Installation(
            Path("/opt/xgw/zapret2/1.0.7/nfqws2"),
            Path("/opt/xgw/zapret2/1.0.7/lua"),
            {name: None for name in nfqws2.BLOBS},
        )

    def worker(self):
        host = WorkerHost()
        runtime = nfqws2.Runtime(host.run)
        patches = self.enterContext(ExitStack())
        patches.enter_context(mock.patch("xgw.nfqws2.find_installation",
                                         return_value=self.installation))
        patches.enter_context(mock.patch.object(runtime, "occupied", host.occupied))
        patches.enter_context(mock.patch.object(runtime, "_check_files"))
        patches.enter_context(mock.patch.object(nfqws2, "time", SimpleNamespace(
            monotonic=lambda: host.now, sleep=host.sleep,
        )))
        cfg = Config()
        cfg.zapret2.engine = "auto"
        cfg.network.wan_if = "test0"
        return cfg, nfqws2.Controller(runtime), host

    def test_delayed_queue_and_profile_switch_preserve_offload(self):
        cfg, controller, host = self.worker()
        controller.step(cfg, [], active=True)
        self.assertEqual(controller.view["state"], "active")
        self.assertEqual((host.starts, host.stops), (1, 0))
        self.assertGreaterEqual(host.now, 2 * nfqws2.READY_POLL)
        cfg.notify.min_interval_min = 7
        controller.step(cfg, [], active=True)
        self.assertEqual((host.starts, host.stops), (1, 0))
        for index, profile in enumerate(("hostfakesplit", "disorder-badseq", "seqovl"), 2):
            cfg.zapret2.engine_profile = profile
            controller.step(cfg, [], active=True)
            self.assertEqual(controller.view["profile"], profile)
            self.assertEqual((host.starts, host.stops), (index, index - 1))
            expected = dict.fromkeys(nfqws2.OFFLOADS, False) if profile == "disorder-badseq" \
                else host.initial_flags
            self.assertEqual(host.flags, expected)
        cfg.zapret2.engine = "off"
        controller.step(cfg, [], active=True)
        self.assertFalse(host.active)
        self.assertEqual(host.flags, host.initial_flags)

    def test_reloaded_worker_arguments_and_offload_trigger_restart(self):
        cfg, controller, host = self.worker()
        cfg.zapret2.engine_profile = "disorder-badseq"
        controller.step(cfg, [], active=True)
        cfg.zapret2.engine_offload = False
        controller.step(cfg, [], active=True)
        self.assertEqual(host.starts, 2)
        self.assertEqual(host.flags, host.initial_flags)
        cfg.routing.cloudflare_tcp_ports.append("9443")
        controller.step(cfg, [], active=True)
        self.assertEqual(host.starts, 3)
        other = dataclasses.replace(self.installation, lua_dir=Path("/opt/new-lua"))
        with mock.patch("xgw.nfqws2.find_installation", return_value=other):
            controller.step(cfg, [], active=True)
        self.assertEqual(host.starts, 4)
        controller.close()

    def test_queue_timeout_stops_worker_and_restores_offload(self):
        cfg, controller, host = self.worker()
        cfg.zapret2.engine_profile = "disorder-badseq"
        host.never_ready = True
        controller.step(cfg, [], active=True)
        self.assertEqual(controller.view["reason"], "worker_start_timeout")
        self.assertEqual((host.starts, host.stops), (1, 1))
        self.assertAlmostEqual(host.now, nfqws2.READY_TIMEOUT)
        self.assertEqual(host.flags, host.initial_flags)

    def test_stop_interrupts_queue_wait_and_prevents_next_start(self):
        cfg, controller, host = self.worker()
        host.never_ready = True
        stop = threading.Event()
        with mock.patch.object(stop, "wait", side_effect=lambda _seconds: stop.set()):
            controller.step(cfg, [], active=True, cancel=stop)
        self.assertEqual(controller.view, {"state": "off", "reason": "stopping"})
        controller.step(cfg, [], active=True, cancel=stop)
        self.assertEqual((host.starts, host.stops), (1, 1))
        self.assertEqual(host.now, 0)

    def test_partial_offload_failure_is_restored(self):
        cfg, controller, host = self.worker()
        cfg.zapret2.engine_profile = "disorder-badseq"

        def run(args, **kwargs):
            result = host.run(args, **kwargs)
            if args[:2] == ["ethtool", "-K"] and "off" in args[3:]:
                raise CommandError("partially applied")
            return result

        controller.runtime.offload.runner = run
        controller.step(cfg, [], active=True)
        self.assertEqual(controller.view["reason"], "offload_apply")
        self.assertEqual((host.starts, host.stops), (0, 0))
        self.assertEqual(host.flags, host.initial_flags)

    def test_real_ethtool_layout_distinguishes_fixed_and_requested_flags(self):
        listing = """Features for test0:
rx-checksumming: on
tx-checksumming: on
    tx-checksum-ipv4: off [fixed]
    tx-checksum-ip-generic: on
tcp-segmentation-offload: off [fixed]
    tx-tcp-ecn-segmentation: off [fixed]
generic-segmentation-offload: on [requested off]
generic-receive-offload: on

unrelated-empty-field:
"""
        flags = nfqws2.Offload.parse(listing)
        self.assertEqual(set(flags), set(nfqws2.OFFLOADS))
        self.assertEqual(flags["tcp-segmentation-offload"], nfqws2.OffloadFlag(False, True))
        self.assertEqual(flags["generic-segmentation-offload"], nfqws2.OffloadFlag(True, False))

    def test_unknown_offload_state_is_not_assumed_disabled(self):
        for listing in ("Features for test0:\n", "generic-receive-offload:\n",
                        "generic-receive-offload: unknown\n",
                        "generic-receive-offload: off\ngeneric-receive-offload: on\n"):
            with self.subTest(listing=listing), self.assertRaisesRegex(
                nfqws2.OffloadError, "offload_state",
            ):
                nfqws2.Offload.parse(listing)

    def test_fixed_on_prevents_profile_without_changing_interface(self):
        cfg, controller, host = self.worker()
        cfg.zapret2.engine_profile = "disorder-badseq"
        host.fixed.add("generic-receive-offload")
        controller.step(cfg, [], active=True)
        self.assertEqual(controller.view["reason"], "offload_fixed")
        self.assertEqual((host.starts, host.stops), (0, 0))
        self.assertEqual(host.offload_writes, [])
        self.assertEqual(host.flags, host.initial_flags)

    def test_successful_command_with_unchanged_flags_is_not_active(self):
        cfg, controller, host = self.worker()
        cfg.zapret2.engine_profile = "disorder-badseq"
        host.ignore_offload_writes = True
        controller.step(cfg, [], active=True)
        self.assertEqual(controller.view["reason"], "offload_apply")
        self.assertEqual((host.starts, host.stops), (0, 0))
        self.assertEqual(host.flags, host.initial_flags)
        self.assertEqual(controller.runtime.offload.saved, {})

    def test_failed_restore_keeps_snapshot_blocks_start_and_retries_when_off(self):
        cfg, controller, host = self.worker()
        cfg.zapret2.engine_profile = "disorder-badseq"
        controller.step(cfg, [], active=True)
        saved = dict(controller.runtime.offload.saved)
        self.assertEqual(saved, host.initial_flags)
        host.ignore_offload_writes = True
        cfg.zapret2.engine = "off"
        controller.step(cfg, [], active=True)
        self.assertEqual(controller.view, {"state": "fallback", "reason": "offload_restore"})
        self.assertEqual(controller.runtime.offload.saved, saved)
        cfg.zapret2.engine = "auto"
        cfg.zapret2.engine_profile = "seqovl"
        controller.step(cfg, [], active=True)
        self.assertEqual(controller.view["reason"], "offload_restore")
        self.assertEqual((host.starts, host.stops), (1, 1))
        self.assertEqual(controller.runtime.offload.saved, saved)
        host.ignore_offload_writes = False
        cfg.zapret2.engine = "off"
        controller.step(cfg, [], active=True)
        self.assertEqual(controller.view, {"state": "off", "reason": "disabled"})
        self.assertEqual(host.flags, host.initial_flags)
        self.assertEqual(controller.runtime.offload.saved, {})
        self.assertTrue(all(not (host.fixed & change.keys()) for change in host.offload_writes))

    def test_dead_worker_is_not_waited_for(self):
        cfg, controller, host = self.worker()
        with mock.patch.object(controller.runtime, "occupied", return_value=False):
            # Процесс успел завершиться ещё до первого опроса готовности.
            original = host.run

            def run(args, **kwargs):
                result = original(args, **kwargs)
                if args[0] == "systemd-run":
                    host.active = False
                return result

            controller.runtime.runner = run
            controller.step(cfg, [], active=True)
        self.assertEqual(controller.view["reason"], "worker_down")
        self.assertEqual(host.now, 0)

    def test_inaccessible_lua_and_blobs_do_not_break_discovery(self):
        cfg = Config()
        cfg.zapret2.lua_dir = "/private/lua"

        def is_file(path):
            if str(path).startswith("/private/") or path.suffix == ".bin":
                raise PermissionError("unreadable")
            return path.name in ("zapret-lib.lua", "zapret-antidpi.lua")

        with (mock.patch("xgw.nfqws2.find_binary", return_value=self.installation.binary),
              mock.patch.object(Path, "is_file", is_file)):
            found = find_installation(cfg)
        self.assertEqual(found.lua_dir, self.installation.lua_dir)
        self.assertEqual(found.blobs, dict.fromkeys(nfqws2.BLOBS))
        with (mock.patch("xgw.nfqws2.find_binary", return_value=self.installation.binary),
              mock.patch.object(Path, "is_file", side_effect=PermissionError("unreadable"))):
            self.assertIsNone(find_installation(cfg))

    def test_unreadable_search_root_keeps_explicit_binary(self):
        cfg = Config()
        cfg.zapret2.binary = str(self.installation.binary)
        with (mock.patch.object(Path, "glob", side_effect=PermissionError("unreadable")),
              mock.patch.object(Path, "is_file", return_value=True),
              mock.patch("xgw.nfqws2.os.access", return_value=True),
              mock.patch("xgw.nfqws2.shutil.which", return_value=None)):
            self.assertEqual(nfqws2.find_binary(cfg), self.installation.binary)

    def test_profiles_arguments_and_ladder(self):
        expected = {
            "seqovl": "--lua-desync=multisplit:pos=2,sniext+1:seqovl=679",
            "hostfakesplit": (
                "--lua-desync=hostfakesplit:host=www.google.com:altorder=1:tcp_ts=+100"
            ),
            "disorder-badseq": "--lua-desync=multidisorder:pos=1,midsld",
        }
        for profile, argument in expected.items():
            with self.subTest(profile=profile):
                args = nfqws2.arguments(Config(), self.installation, profile)
                self.assertIn("--qnum=200", args)
                self.assertIn("--fwmark=0x40000000", args)
                self.assertIn(argument, args)
        steps = profiles.ladder(
            "FROZEN", profiles.XRAY_DEFAULT, profiles.XRAY_DEFAULT, list(profiles.ALL),
        )
        self.assertEqual([step for step in steps if step in profiles.NFQ_PROFILES],
                         list(profiles.NFQ_PROFILES))
        self.assertLess(steps.index(profiles.NFQ_DISORDER), steps.index(profiles.SB_DEFAULT))
        without = [step for step in profiles.ALL if step not in profiles.NFQ_PROFILES]
        self.assertFalse(set(profiles.ladder("FROZEN", profiles.XRAY_DEFAULT,
                                             profiles.XRAY_DEFAULT, without))
                         & set(profiles.NFQ_PROFILES))

    def test_nfqueue_is_bounded_fail_open_and_loop_free(self):
        cfg = Config()
        cfg.zapret2.engine = "off"
        rules, _warnings = nft.build_rules(cfg, capture=True, time_uids=())
        rules = dataclasses.replace(rules, engine_queue=200, singbox_uid=990)
        text = nft.render_guard(rules)
        self.assertIn("queue num 200 bypass", text)
        self.assertIn("meta mark & 0x40000000 == 0x40000000 return", text)
        self.assertIn("meta mark & 0x40000000 == 0x40000000 accept", text)
        self.assertIn("meta mark 0x2 meta l4proto tcp ct packets <= 8", text)
        self.assertIn("meta mark 0x2 meta l4proto udp ct packets <= 4", text)
        self.assertIn("meta skuid 990 meta l4proto tcp ct packets <= 8", text)

    def test_failed_worker_has_explicit_fallback(self):
        class BrokenRuntime:
            key = None

            def __init__(self):
                self.stopped = 0

            def start(self, cfg, installation, profile):
                raise ValueError("unsafe_files")

            def stop(self):
                self.stopped += 1

        runtime = BrokenRuntime()
        controller = nfqws2.Controller(runtime)
        cfg = Config()
        cfg.zapret2.engine = "auto"
        with mock.patch("xgw.nfqws2.find_installation", return_value=self.installation):
            controller.step(cfg, [], active=True)
        self.assertEqual(controller.view, {
            "state": "fallback", "reason": "unsafe_files", "profile": "seqovl",
        })
        self.assertEqual(runtime.stopped, 1)

    def test_disabled_engine_does_not_touch_runtime(self):
        runner = mock.Mock(return_value="inactive")
        controller = nfqws2.Controller(nfqws2.Runtime(runner))
        cfg = Config()
        self.assertEqual(cfg.zapret2.engine, "off")
        with mock.patch("xgw.nfqws2.find_installation", return_value=self.installation) as find:
            controller.step(cfg, [], active=True)
            controller.close()
        find.assert_not_called()
        runner.assert_not_called()

    def test_failed_preflight_does_not_stop_service(self):
        runner = mock.Mock(return_value="inactive")
        runtime = nfqws2.Runtime(runner)
        controller = nfqws2.Controller(runtime)
        cfg = Config()
        cfg.zapret2.engine = "auto"
        with (mock.patch("xgw.nfqws2.find_installation", return_value=self.installation),
              mock.patch.object(runtime, "occupied", return_value=False),
              mock.patch.object(runtime, "_check_files", side_effect=ValueError("unsafe_files"))):
            controller.step(cfg, [], active=True)
            controller.close()
        self.assertEqual(controller.view["reason"], "unsafe_files")
        runner.assert_called_once_with(
            ["systemctl", "is-active", nfqws2.UNIT], check=False, timeout=5,
        )

    def test_runtime_stops_started_worker_once(self):
        runner = mock.Mock(return_value="inactive")
        runtime = nfqws2.Runtime(runner)
        with (mock.patch.object(runtime, "occupied", return_value=False),
              mock.patch.object(runtime, "_check_files")):
            runtime.start(Config(), self.installation, "seqovl")
        runner.reset_mock()
        controller = nfqws2.Controller(runtime)
        controller.close()
        controller.close()
        self.assertEqual(runner.call_args_list, [
            mock.call(["systemctl", "stop", nfqws2.UNIT], check=False, timeout=10),
            mock.call(["systemctl", "is-active", nfqws2.UNIT], check=False, timeout=5),
        ])
        self.assertIsNone(runtime.key)

    def test_failed_start_and_stop_keep_cleanup_pending(self):
        def run(argv, **kwargs):
            if argv[0] == "systemd-run":
                raise CommandError("start timed out after unit creation")
            return "inactive"

        runner = mock.Mock(side_effect=run)
        runtime = nfqws2.Runtime(runner)
        with (mock.patch.object(runtime, "occupied", return_value=False),
              mock.patch.object(runtime, "_check_files"),
              self.assertRaises(CommandError)):
            runtime.start(Config(), self.installation, "seqovl")
        runner.side_effect = CommandError("stop timed out")
        controller = nfqws2.Controller(runtime)
        with self.assertRaises(CommandError):
            controller.close()
        self.assertIsNotNone(runtime.key)
        runner.reset_mock()
        runner.side_effect = None
        runner.return_value = "inactive"
        controller.close()
        runner.assert_any_call(["systemctl", "stop", nfqws2.UNIT], check=False, timeout=10)
        self.assertIsNone(runtime.key)


if __name__ == "__main__":
    unittest.main()
