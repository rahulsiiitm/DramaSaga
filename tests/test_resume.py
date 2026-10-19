import tempfile
import unittest
import pathlib

from magicdrama.governor import Spend
from magicdrama.ledgers import ensure_ledgers

class ResumeTest(unittest.TestCase):
    def test_crash_resume_skips_completed_jobs(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        ensure_ledgers(tmp)
        s1 = Spend(tmp)
        s1.spend("shot1", 100, lambda **k: {"credits_charged": 0}, key_a=1)
        rows_after_first = (tmp / "generation_jobs.csv").read_text().strip().splitlines()
        s2 = Spend(tmp)
        out = s2.spend("shot1", 100, lambda **k: {"credits_charged": 0}, key_a=1)
        rows_after_resume = (tmp / "generation_jobs.csv").read_text().strip().splitlines()
        self.assertTrue(out.get("resumed"))
        self.assertEqual(len(rows_after_first), len(rows_after_resume))
        self.assertEqual(s2.batch, 0)

if __name__ == "__main__":
    unittest.main()

