import tempfile
import unittest
import pathlib

from magicdrama import config
from magicdrama.governor import Spend, estimate_episode_credits, price_for, PriceQuoteRequired
from magicdrama.ledgers import ensure_ledgers

class GovernorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        ensure_ledgers(self.tmp)

    def test_episode_cap_blocks(self):
        s = Spend(self.tmp)
        s.spend("jobA", 2000, lambda **k: {"credits_charged": 0}, ep="t1", key_a=1)
        with self.assertRaises(RuntimeError):
            s.spend("jobB", 1500, lambda **k: {"credits_charged": 0}, ep="t1", key_b=2)

    def test_batch_cap_blocks(self):
        old = config.BATCH_CAP_CREDITS
        config.BATCH_CAP_CREDITS = 2500
        try:
            s = Spend(self.tmp)
            s.spend("jobA", 2000, lambda **k: {"credits_charged": 0}, key_a=1)
            with self.assertRaises(RuntimeError):
                s.spend("jobB", 1000, lambda **k: {"credits_charged": 0}, key_b=2)
        finally:
            config.BATCH_CAP_CREDITS = old

    def test_idempotent_no_double_charge(self):
        fn = lambda **k: {"credits_charged": 0}
        s1 = Spend(self.tmp)
        s1.spend("sameJob", 500, fn, key_a=1)
        self.assertEqual(s1.batch, 500)
        s2 = Spend(self.tmp)
        out = s2.spend("sameJob", 500, fn, key_a=1)
        self.assertTrue(out.get("resumed"))
        self.assertEqual(s2.batch, 0)

    def test_price_for_unknown_model_fails_loud(self):
        with self.assertRaises(PriceQuoteRequired):
            price_for("no-such-model", "480p")

    def test_estimate_math(self):
        est = estimate_episode_credits([5, 6], dialogue_seconds=24, n_images=4, model="ltx-2.5")
        self.assertEqual(est["video"], 11 * 24)
        self.assertEqual(est["images"], 20)
        self.assertEqual(est["lipsync"], 24 * 24)
        self.assertEqual(est["total"], est["video"] + est["images"] + est["lipsync"])

if __name__ == "__main__":
    unittest.main()

