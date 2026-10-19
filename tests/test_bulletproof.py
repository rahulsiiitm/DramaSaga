import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import requests

from magicdrama import config
from magicdrama.stages import series
from magicdrama.retry import call_with_retries
from magicdrama.validators import validate_script


def brief():
    return {"characters": [{"name": "Kaito Ren"}, {"name": "Hana Voss"}, {"name": "Jiro"}], "no_go": []}


def shot(n, speaker=None, line="we move at dawn"):
    return {"n": n, "seconds": config.SHOT_SECONDS[n - 1], "visual": "v", "camera": "static",
            "dialogue": [{"character": speaker, "line": line}] if speaker else [],
            "lipsync": bool(speaker), "narrative_job": "j", "speaker_binding": speaker or ""}


def script_with(speaker=None, line="we move at dawn"):
    return {"ep": 1, "title": "t", "shots": [shot(i + 1, speaker if i == 0 else None, line) for i in range(len(config.SHOT_SECONDS))],
            "new_facts": []}


class DriftInjectionTest(unittest.TestCase):
    def test_first_name_drift_rejected(self):
        errs = validate_script(script_with("Kaito"), brief())
        self.assertTrue(any("unknown speaker" in e for e in errs))

    def test_hallucinated_speaker_rejected(self):
        errs = validate_script(script_with("AI Avatar"), brief())
        self.assertTrue(any("unknown speaker" in e for e in errs))

    def test_long_line_rejected(self):
        errs = validate_script(script_with("Kaito Ren", " ".join(["word"] * 20)), brief())
        self.assertTrue(any("long line" in e for e in errs))

    def test_exact_cast_name_passes(self):
        self.assertEqual(validate_script(script_with("Kaito Ren"), brief()), [])


class SanitizerTest(unittest.TestCase):
    def test_literal_byte_escapes_decoded(self):
        self.assertEqual(series.sanitize("neo-osaka\\u00e2\\u0080\\u0099s"), "neo-osaka's")

    def test_lone_codepoint_escape(self):
        self.assertEqual(series.sanitize("it\\u2019s"), "it's")

    def test_smart_punctuation_normalized(self):
        self.assertEqual(series.sanitize("a\u2011b \u201cc\u201d d\u2026"), 'a-b "c" d...')

    def test_cjk_preserved(self):
        self.assertEqual(series.sanitize("\u6b63\u76f4"), "\u6b63\u76f4")

    def test_nested_structures(self):
        out = series.sanitize({"a": [{"b": "x\\u00e2\\u0080\\u0099y"}]})
        self.assertEqual(out["a"][0]["b"], "x'y")


class CallJsonStressTest(unittest.TestCase):
    def test_malformed_then_valid_retries(self):
        outs = [({"choices": [{"message": {"content": "not json at all"}}]}, None)] * 0 or None
        responses = iter([
            {"choices": [{"message": {"content": "garbage {{{"}}]},
            {"choices": [{"message": {"content": '{"ok": 1}'}}]},
        ])
        with mock.patch.object(series, "nvidia_chat", side_effect=lambda *a, **k: next(responses)):
            self.assertEqual(series.call_json("writer", "p", 100, 0.1, "off"), {"ok": 1})

    def test_persistent_garbage_raises(self):
        with mock.patch.object(series, "nvidia_chat", return_value={"choices": [{"message": {"content": "garbage"}}]}):
            with self.assertRaises(ValueError):
                series.call_json("writer", "p", 100, 0.1, "off")

    def test_reasoning_content_fallback(self):
        resp = {"choices": [{"message": {"content": None, "reasoning_content": '{"ok": 2}'}}]}
        with mock.patch.object(series, "nvidia_chat", return_value=resp):
            self.assertEqual(series.call_json("judge", "p", 100, 0.1, None), {"ok": 2})


class RetryStressTest(unittest.TestCase):
    def test_chunked_encoding_error_retried(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")
            return "ok"

        self.assertEqual(call_with_retries(flaky, max_attempts=3, base_delay=0), "ok")
        self.assertEqual(calls["n"], 3)

    def test_non_retryable_raises_immediately(self):
        calls = {"n": 0}

        def bad():
            calls["n"] += 1
            raise ValueError("nope")

        with self.assertRaises(ValueError):
            call_with_retries(bad, max_attempts=3, base_delay=0)
        self.assertEqual(calls["n"], 1)


class HookRecapTest(unittest.TestCase):
    def arc(self, hook2):
        return {"episodes": [
            {"ep": 1, "title": "a", "hook": "h", "beat": "b", "reversal": "r",
             "cliffhanger": "Can Jiro's shard actually disable the machine?"},
            {"ep": 2, "title": "b", "hook": hook2, "beat": "b", "reversal": "r", "cliffhanger": "c"}]}

    def test_unchained_hook_flagged(self):
        misses = series.hook_recap_check(self.arc("Rain strikes the neon sign overhead as allies meet"))
        self.assertEqual([m["ep"] for m in misses], [2])

    def test_chained_hook_passes(self):
        self.assertEqual(series.hook_recap_check(self.arc("Jiro raises the shard toward the machine")), [])


class SeriesRunResumeTest(unittest.TestCase):
    def test_completed_episode_not_regenerated(self):
        with tempfile.TemporaryDirectory() as td:
            work = pathlib.Path(td)
            env = dict(**{k: v for k, v in __import__("os").environ.items()},
                       MAGICDRAMA_DRY_RUN="1", MAGICDRAMA_WORKDIR=str(work))
            root = pathlib.Path(__file__).resolve().parent.parent
            subprocess.run([sys.executable, "series_run.py", "--series-count", "1", "--eps", "3", "--sleep", "0"],
                           cwd=root, env=env, check=True, capture_output=True)
            ep1 = work / "series_lab" / "dry-series-1" / "ep01.json"
            first = ep1.read_text()
            subprocess.run([sys.executable, "series_run.py", "--series-count", "1", "--eps", "3", "--sleep", "0"],
                           cwd=root, env=env, check=True, capture_output=True)
            self.assertEqual(ep1.read_text(), first)


if __name__ == "__main__":
    unittest.main()

