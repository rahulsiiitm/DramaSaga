import unittest
from unittest import mock

import requests

from magicdrama import config

class FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._p = payload or {}
    def json(self):
        return self._p
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")
    def iter_content(self, chunk_size=1, decode_unicode=False):
        import json as _j
        chunk = {"choices": [{"delta": {"content": self._p.get("choices", [{"message": {"content": ""}}])[0]["message"]["content"]}}]}
        text = f"data: {_j.dumps(chunk)}\ndata: [DONE]\n"
        for i in range(0, len(text), max(chunk_size, 7)):
            yield text[i:i + max(chunk_size, 7)]
    def close(self):
        pass

class ClientTest(unittest.TestCase):
    def setUp(self):
        self.old_dry = config.DRY_RUN
        config.DRY_RUN = False
        import os
        os.environ["NVIDIA_KEY"] = "test-key"
        os.environ["MAGICHOUR_KEY"] = "test-key"
        self.sleep_p = mock.patch("time.sleep")
        self.sleep_p.start()

    def tearDown(self):
        config.DRY_RUN = self.old_dry
        self.sleep_p.stop()

    def test_nvidia_retries_on_429_then_succeeds(self):
        from magicdrama.clients import nvidia
        calls = []
        def fake_post(*a, **k):
            calls.append(1)
            return FakeResp(429) if len(calls) == 1 else FakeResp(200, {"choices": [{"message": {"content": "ok"}}]})
        with mock.patch.object(nvidia.requests, "post", side_effect=fake_post):
            out = nvidia.nvidia_chat("m", [{"role": "user", "content": "hi"}])
        self.assertEqual(out["choices"][0]["message"]["content"], "ok")
        self.assertEqual(len(calls), 2)

    def test_nvidia_exhausts_on_500(self):
        from magicdrama.clients import nvidia
        with mock.patch.object(nvidia.requests, "post", return_value=FakeResp(500)) as p:
            with self.assertRaises(requests.HTTPError):
                nvidia.nvidia_chat("m", [{"role": "user", "content": "hi"}])
        self.assertEqual(p.call_count, 3)

    def test_nvidia_timeout_raises_after_retries(self):
        from magicdrama.clients import nvidia
        with mock.patch.object(nvidia.requests, "post", side_effect=requests.Timeout()) as p:
            with self.assertRaises(requests.Timeout):
                nvidia.nvidia_chat("m", [{"role": "user", "content": "hi"}])
        self.assertEqual(p.call_count, 3)

    def test_magichour_retries_on_429(self):
        from magicdrama.clients import magichour as mh
        calls = []
        def fake_post(*a, **k):
            calls.append(1)
            return FakeResp(429) if len(calls) == 1 else FakeResp(200, {"id": "job1", "credits_charged": 24})
        with mock.patch.object(mh.requests, "post", side_effect=fake_post):
            out = mh.mh_post("/v1/x", {})
        self.assertEqual(out["id"], "job1")
        self.assertEqual(len(calls), 2)

    def test_magichour_400_not_retried(self):
        from magicdrama.clients import magichour as mh
        with mock.patch.object(mh.requests, "post", return_value=FakeResp(400)) as p:
            with self.assertRaises(requests.HTTPError):
                mh.mh_post("/v1/x", {})
        self.assertEqual(p.call_count, 1)

    def test_bad_json_rejected_clearly(self):
        from magicdrama.validation import parse_json_from_text
        with self.assertRaises(ValueError):
            parse_json_from_text("no json here at all")
        self.assertEqual(parse_json_from_text('prose {"a": 1} tail'), {"a": 1})

if __name__ == "__main__":
    unittest.main()

