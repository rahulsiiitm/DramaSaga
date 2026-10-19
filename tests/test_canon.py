import json
import tempfile
import unittest
import pathlib

from magicdrama.canon import CANON, CANON_FACTS
from magicdrama.ledgers import ensure_ledgers, seed_canon
from magicdrama.validation import validate_canon

class CanonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        ensure_ledgers(self.tmp)

    def test_canon_data_valid(self):
        self.assertEqual(validate_canon(CANON), [])

    def test_seed_twice_no_duplicates(self):
        seed_canon(self.tmp, CANON, CANON_FACTS)
        seed_canon(self.tmp, CANON, CANON_FACTS)
        arc = json.loads((self.tmp / "season_arc.json").read_text())
        canon_eps = [e["ep"] for e in arc["episodes"] if e.get("canon")]
        self.assertEqual(canon_eps, list(range(1, 11)))
        rows = (self.tmp / "story_memory.csv").read_text().strip().splitlines()
        self.assertEqual(len(rows), 1 + len(CANON_FACTS))

    def test_canon_flagged_immutable(self):
        seed_canon(self.tmp, CANON, CANON_FACTS)
        arc = json.loads((self.tmp / "season_arc.json").read_text())
        for e in arc["episodes"]:
            self.assertTrue(e["canon"])

if __name__ == "__main__":
    unittest.main()

