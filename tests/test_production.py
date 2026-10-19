import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
from magicdrama.production import Production, compare_transcripts, read_json

ROOT = Path(__file__).resolve().parent.parent

class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.p = Production(ROOT / 'examples/honesty.json')
        self.p.output = Path(self.temp.name)

    def test_dry_run_never_calls_http(self):
        with patch.object(requests.Session, 'request', side_effect=AssertionError('network')):
            plan = self.p.step(1)
        self.assertEqual(plan['paid_requests'], 0)
        self.assertEqual(len(plan['episodes']), 10)
        self.assertTrue(plan['episodes'][0]['scenes'][0]['missing_references'])

    def test_default_is_fresh_keyframe(self):
        self.assertFalse(self.p.chained(self.p.scripts[0], 1))

    def test_chain_requires_confirmation(self):
        self.p.cfg['scene_overrides']['E01_S02'] = {'chain_from_previous': True}
        with self.assertRaises(ValueError):
            self.p.chained(self.p.scripts[0], 1)

    def test_quote_and_refs_required_live(self):
        self.p.live = True
        with self.assertRaises(ValueError):
            self.p.preflight_live()

    def test_cap_blocks_before_submission(self):
        self.p.cfg['batch_cap_credits'] = 1
        self.p.session = Mock()
        with self.assertRaises(RuntimeError):
            self.p.job(1, 'video', {'x': 1}, 2, self.p.output / 'S01' / 'clip.mp4')
        self.p.session.post.assert_not_called()

    def test_unknown_submission_never_retries(self):
        self.p.session = Mock()
        self.p.session.post.side_effect = requests.Timeout('unknown')
        path = self.p.output / 'S01' / 'clip.mp4'
        with self.assertRaises(requests.Timeout):
            self.p.job(1, 'video', {'x': 1}, 20, path)
        with self.assertRaises(RuntimeError):
            self.p.job(1, 'video', {'x': 1}, 20, path)
        self.assertEqual(self.p.session.post.call_count, 1)

    def test_saved_job_resumes_polling(self):
        dest = self.p.output / 'S01' / 'clip.mp4'
        self.p.session = Mock()
        post = Mock(); post.json.return_value = {'id': 'job-1'}
        self.p.session.post.return_value = post
        status = Mock(); status.json.return_value = {'status': 'complete', 'credits_charged': 20, 'downloads': [{'url': 'https://example.invalid/clip'}]}
        download = Mock(); download.content = b'test'
        self.p.session.get.side_effect = [status, download]
        self.p.job(1, 'video', {'x': 1}, 20, dest)
        self.assertEqual(dest.read_bytes(), b'test')
        self.p.job(1, 'video', {'x': 1}, 20, dest)
        self.assertEqual(self.p.session.post.call_count, 1)
        self.assertEqual(sum(r['credits'] for r in self.p.records().values()), 20)

    def test_scene_ids_do_not_collide(self):
        self.p.reserve({}, '1:video:S01', 1, 10)
        records = self.p.records()
        self.p.reserve(records, '1:video:S02', 1, 10)
        self.assertEqual(len(self.p.records()), 2)

    def test_attempt_keeps_shared_budget(self):
        first = self.p.scene_dir(1, 1)
        self.p.cfg['scene_overrides']['E01_S01'] = {'attempt': 2}
        self.assertNotEqual(first, self.p.scene_dir(1, 1))

    def test_transcript_disagreement_blocks(self):
        self.assertFalse(compare_transcripts('hello world', ['hello world', 'goodbye'], .85)['pass'])
        self.assertTrue(compare_transcripts('hello world', ['Hello, world!', 'hello world'], .85)['pass'])

    def test_changed_inputs_require_new_attempt(self):
        script = self.p.scripts[0]
        directory = self.p.scene_dir(1, 1)
        directory.mkdir(parents=True)
        self.p.check_inputs(script, 0, directory)
        script['scenes'][0]['camera'] += ' altered'
        with self.assertRaises(RuntimeError):
            self.p.check_inputs(script, 0, directory)

    def test_review_bound_to_clip_hash(self):
        directory = self.p.scene_dir(1, 1); directory.mkdir(parents=True)
        (directory / 'clip.mp4').write_bytes(b'new clip')
        (directory / 'review.json').write_text(json.dumps({'approved': True, 'clip_sha256': 'wrong'}))
        self.assertFalse(self.p.approved(directory))

    def test_assemble_blocks_without_reviews(self):
        with self.assertRaises(RuntimeError):
            self.p.assemble(1)

if __name__ == '__main__':
    unittest.main()
