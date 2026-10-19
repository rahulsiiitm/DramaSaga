import unittest

from magicdrama.validators import check_arc_batch, validate_script
from magicdrama.brief import BRIEF

GOOD_BATCH = [{"ep": 11, "title": "New One", "hook": "h", "beat": "b", "reversal": "r", "cliffhanger": "c"}]

def good_shot(n, dialogue=None, lipsync=False, binding=""):
    return {"n": n, "seconds": 5, "visual": "v", "camera": "c",
            "dialogue": dialogue or [], "lipsync": lipsync, "narrative_job": "j",
            "speaker_binding": binding, "transition_in": "cut", "transition_out": "cut", "screen_direction": "lr"}

from magicdrama import config
s_times = config.SHOT_SECONDS

def good_script():
    return {"ep": 1, "shots": [dict(good_shot(i + 1), seconds=t) for i, t in enumerate(s_times)]}

class ValidatorsTest(unittest.TestCase):
    def test_canon_overwrite_rejected(self):
        bad = [dict(GOOD_BATCH[0], ep=5)]
        self.assertTrue(any("canon" in e for e in check_arc_batch(bad)))

    def test_canon_title_reuse_rejected(self):
        bad = [dict(GOOD_BATCH[0], title="The Song")]
        self.assertTrue(any("title" in e for e in check_arc_batch(bad)))

    def test_missing_field_rejected(self):
        bad = [{"ep": 11, "title": "x"}]
        self.assertTrue(check_arc_batch(bad))

    def test_good_batch_passes(self):
        self.assertEqual(check_arc_batch(GOOD_BATCH), [])

    def test_good_script_passes(self):
        self.assertEqual(validate_script(good_script(), BRIEF), [])

    def test_unknown_speaker(self):
        script = good_script()
        script["shots"][0]["dialogue"] = [{"character": "Ghost", "line": "hi"}]
        script["shots"][0]["lipsync"] = True
        script["shots"][0]["speaker_binding"] = "Ghost"
        self.assertTrue(any("unknown speaker" in e for e in validate_script(script, BRIEF)))

    def test_long_line(self):
        script = good_script()
        script["shots"][0]["dialogue"] = [{"character": "Mina", "line": " ".join(["word"] * 15)}]
        script["shots"][0]["lipsync"] = True
        script["shots"][0]["speaker_binding"] = "Mina"
        self.assertTrue(any("long line" in e for e in validate_script(script, BRIEF)))

    def test_dialogue_requires_lipsync_and_binding(self):
        script = good_script()
        script["shots"][0]["dialogue"] = [{"character": "Mina", "line": "hello class"}]
        errs = validate_script(script, BRIEF)
        self.assertTrue(any("lipsync" in e for e in errs))
        self.assertTrue(any("speaker_binding" in e for e in errs))

if __name__ == "__main__":
    unittest.main()

