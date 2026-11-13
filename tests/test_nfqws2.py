import dataclasses
import unittest
from pathlib import Path
from unittest import mock

from xgw import nfqws2
from xgw.config import Config
from xgw.generator import fragment, profiles
from xgw.generator.builder import build, select_nodes
from xgw.model import ServerNode
from xgw.net import nft


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
        with mock.patch("xgw.nfqws2.find_installation", return_value=self.installation):
            controller.step(Config(), [], active=True)
        self.assertEqual(controller.view, {
            "state": "fallback", "reason": "unsafe_files", "profile": "seqovl",
        })
        self.assertEqual(runtime.stopped, 1)


if __name__ == "__main__":
    unittest.main()
