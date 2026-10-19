import json
import tempfile
import unittest
import pathlib
from unittest import mock

from magicdrama import config
from magicdrama.stages import series

def good_concept(i):
    return {"slug": f"s{i}", "title": f"Series {i}", "genre": f"genre{i}", "setting": "x", "tone": "a b c",
            "logline": "l", "world_rules": ["r1", "r2", "r3"],
            "characters": [{"name": f"N{i}{j}", "role": "lead", "physical": "p", "secret": "s"} for j in range(4)]}

class SeriesTest(unittest.TestCase):
    def test_concepts_valid(self):
        self.assertEqual(series.validate_concepts([good_concept(i) for i in range(10)], 10), [])

    def test_concepts_reject_dupe_slug(self):
        cs = [good_concept(i) for i in range(10)]
        cs[1]["slug"] = cs[0]["slug"]
        self.assertTrue(any("duplicate slug" in e for e in series.validate_concepts(cs, 10)))

    def test_concepts_reject_same_genre(self):
        cs = [good_concept(i) for i in range(10)]
        cs[3]["genre"] = cs[4]["genre"]
        self.assertTrue(any("genre" in e for e in series.validate_concepts(cs, 10)))

    def test_concepts_reject_missing_secret(self):
        cs = [good_concept(i) for i in range(10)]
        del cs[0]["characters"][0]["secret"]
        self.assertTrue(any("secret" in e for e in series.validate_concepts(cs, 10)))

    def test_arc_validation(self):
        arc = {"episodes": [{"ep": i + 1, "title": "t", "hook": "h", "beat": "b", "reversal": "r", "cliffhanger": "c"} for i in range(10)]}
        self.assertEqual(series.validate_series_arc(arc, good_concept(0)), [])
        arc["episodes"][3]["ep"] = 9
        self.assertTrue(series.validate_series_arc(arc, good_concept(0)))

    def test_dry_run_episode_passes_mechanical_validation(self):
        old = config.DRY_RUN
        config.DRY_RUN = True
        try:
            c = good_concept(0)
            script = series.episode_script(c, {"ep": 1, "title": "t"}, [], None)
            from magicdrama.validators import validate_script
            self.assertEqual(validate_script(script, series.concept_brief(c)), [])
        finally:
            config.DRY_RUN = old

    def test_mocked_writer_json_parsing(self):
        old = config.DRY_RUN
        config.DRY_RUN = False
        payload = {"choices": [{"message": {"content": json.dumps([good_concept(i) for i in range(10)])}}]}
        try:
            with mock.patch("magicdrama.stages.series.nvidia_chat", return_value=payload):
                cs = series.generate_concepts(10)
            self.assertEqual(series.validate_concepts(cs, 10), [])
        finally:
            config.DRY_RUN = old

    def test_mocked_eval_parse(self):
        old = config.DRY_RUN
        config.DRY_RUN = False
        verdict = {"scores": {"character": 90, "timeline": 85, "secrets": 95, "voice": 80, "tone": 88},
                   "failures": [], "pass": True}
        payload = {"choices": [{"message": {"content": "text " + json.dumps(verdict) + " tail"}}]}
        try:
            with mock.patch("magicdrama.stages.series.nvidia_chat", return_value=payload):
                out = series.evaluate_series(good_concept(0), {"episodes": []}, [])
            self.assertTrue(out["pass"])
            self.assertEqual(out["scores"]["character"], 90)
        finally:
            config.DRY_RUN = old

if __name__ == "__main__":
    unittest.main()

