import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from magicdrama.audiofirst.bridge import accepted_package, video_manifest
from magicdrama.audiofirst.core import digest
from magicdrama.audiofirst.execution import signature
from magicdrama.audiofirst.images import image_first_plan
from magicdrama.audiofirst.preview import render_animatic, storyboard_preview
from magicdrama.audiofirst.renderplan import compile_render_plan, cut_plan, measured_track, validate_track
from tests.helpers import pilot, profile, audio_fixture, reference_images


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brief, self.story = pilot()
        self.ep, self.track = audio_fixture(self.root, self.story['episodes'][0])
        self.story['episodes'][0] = self.ep

    def test_measured_frames_cover_master_exactly(self):
        cuts = cut_plan(self.ep, self.track)
        self.assertEqual(sum(c['frames'] for c in cuts), 72)
        self.assertEqual(cuts[-1]['end_frame'], self.track['frames'])

    def test_audio_text_review_and_hash_are_binding(self):
        self.ep['lines'][0]['text'] = 'Different.'
        with self.assertRaisesRegex(ValueError, 'stale'): validate_track(self.ep, self.track)

    def test_edited_timing_is_rejected(self):
        self.track['lines'][0]['end_frame'] += 1
        with self.assertRaisesRegex(ValueError, 'content changed'): validate_track(self.ep, self.track)

    def test_changed_waveform_rejected(self):
        Path(self.track['audio']['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash'): validate_track(self.ep, self.track)

    def test_out_of_order_cues_rejected(self):
        alignment = {'audio_sha256': self.track['audio']['sha256'], 'cues': list(reversed(self.track['cues']))}
        with self.assertRaises(ValueError): measured_track(self.ep, self.track['audio'], alignment, self.track['audio_review'])

    def test_visible_speech_cannot_use_unconditioned_video(self):
        with self.assertRaisesRegex(ValueError, 'exact-audio'):
            compile_render_plan(self.ep, self.track, profile(exact_audio=False))

    def test_duration_limit_requires_split(self):
        with self.assertRaisesRegex(ValueError, 'renderer limit'):
            compile_render_plan(self.ep, self.track, profile(max_seconds=.2))

    def test_local_prompt_repair_does_not_invalidate_unrelated_render_inputs(self):
        first=compile_render_plan(self.ep,self.track,profile())
        self.ep['shots'][-1]['camera']='Slightly tighter close-up'
        self.track['episode_sha256']=signature(self.ep)
        second=compile_render_plan(self.ep,self.track,profile())
        self.assertEqual(first['jobs'][0]['input_sha256'],second['jobs'][0]['input_sha256'])
        self.assertNotEqual(first['jobs'][-1]['input_sha256'],second['jobs'][-1]['input_sha256'])

    def test_connected_shots_require_capability_and_same_scene(self):
        self.ep['shots'][0]['render_group'] = 'pair'; self.ep['shots'][1]['render_group'] = 'pair'
        self.track['episode_sha256'] = signature(self.ep)
        with self.assertRaisesRegex(ValueError, 'multi-shot'):
            compile_render_plan(self.ep, self.track, profile(), connected=True)
        plan = compile_render_plan(self.ep, self.track, profile(multi_shot=True), connected=True)
        self.assertEqual(len(plan['jobs']), 5)
        self.ep['shots'][1]['scene_id'] = 'different'; self.track['episode_sha256'] = signature(self.ep)
        with self.assertRaisesRegex(ValueError, 'boundaries'):
            compile_render_plan(self.ep, self.track, profile(multi_shot=True), connected=True)

    def test_reaction_cut_keeps_offscreen_dialogue(self):
        for i, shot in enumerate(self.ep['shots']):
            shot['cut'] = {'start_frame': i * 12, 'end_frame': (i + 1) * 12}
        self.ep['shots'][0]['visible_characters'] = ['dev']
        self.track['episode_sha256'] = signature(self.ep)
        plan = compile_render_plan(self.ep, self.track, profile())
        self.assertEqual(plan['jobs'][0]['mode'], 'image_to_video')
        self.assertEqual(plan['jobs'][0]['cuts'][0]['audible_offscreen_speakers'], ['mira'])

    def test_explicit_cut_gap_rejected(self):
        self.ep['shots'][0]['cut'] = {'start_frame': 1, 'end_frame': 12}; self.track['episode_sha256'] = signature(self.ep)
        with self.assertRaisesRegex(ValueError, 'without gaps'): cut_plan(self.ep, self.track)

    def test_native_audio_cannot_silently_replace_master(self):
        plan = compile_render_plan(self.ep, self.track, profile(modes=['native_audio']), audio_mode='native')
        with self.assertRaisesRegex(ValueError, 'Native generated audio'):
            accepted_package(self.brief, self.story, 'ep1', self.track, plan, {})

    def test_unreviewed_generated_media_rejected(self):
        plan = compile_render_plan(self.ep, self.track, profile(),reference_assets=reference_images(self.root,self.ep))
        with self.assertRaisesRegex(ValueError, 'actual pixel review'):
            accepted_package(self.brief, self.story, 'ep1', self.track, plan, {})

    def test_exact_video_request_builder_and_reviewed_package(self):
        images = image_first_plan(self.brief, self.story)
        accepted, uploads = {}, {}
        path = self.root / 'synthetic.png'; Image.new('RGB', (128, 128), '#729b91').save(path)
        for task in images['tasks']:
            accepted[task['id']] = {'path': str(path), 'sha256': digest(path), 'plan_sha256': images['plan_sha256'],
                'reviewer': 'synthetic-test-fixture', 'reviewed_at': '2026-10-25',
                'checks': {k: True for k in ('identity', 'wardrobe', 'action', 'expression', 'prop_orientation', 'layout')}}
            uploads[task['id']] = {'file_path': 'api-assets/test/' + task['id'], 'sha256': digest(path)}
        plan = compile_render_plan(self.ep,self.track,profile(),reference_assets=accepted)
        uploads['audio-ep1'] = {'file_path': 'api-assets/test/audio', 'sha256': self.track['audio']['sha256']}
        quotes = {job['id']: {'amount': 1, 'unit': 'credits', 'verified_on': '2026-10-25', 'source_url': 'https://example.test/fixture'} for job in plan['jobs']}
        manifest = video_manifest(plan, images, accepted, uploads, quotes, 'test_run', 'test_batch')
        second = manifest['jobs'][1]['request']
        self.assertEqual(second['endpoint'], '/v1/audio-to-video')
        self.assertEqual(second['body']['start_seconds'], .5)
        self.assertEqual(second['body']['end_seconds'], 1)
        uploads['audio-ep1']['sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'hash-bound'): video_manifest(plan, images, accepted, uploads, quotes, 'r', 'b')
        clip = self.root / 'fixture.mp4'; clip.write_bytes(b'not-a-real-video-unit-test-only')
        media = {job['id']: {'path': str(clip), 'sha256': digest(clip), 'pixel_checked': True,
                 'kind': 'video', 'input_sha256': job['input_sha256']} for job in plan['jobs']}
        package = accepted_package(self.brief, self.story, 'ep1', self.track, plan, media)
        self.assertEqual(sum(s['frames'] for s in package['season']['episodes'][0]['shots']), 72)
        media[plan['jobs'][0]['id']]['input_sha256'] = 'stale'
        with self.assertRaisesRegex(ValueError, 'stale'): accepted_package(self.brief, self.story, 'ep1', self.track, plan, media)

    def test_storyboard_html_escapes_script_injection_and_labels_missing_media(self):
        self.story['episodes'][0]['title'] = '</script><script>alert(1)</script>'
        result = storyboard_preview(self.brief, self.story, self.root / 'preview')
        html = Path(result['path']).read_text(encoding='utf-8')
        self.assertNotIn('</script><script>alert', html)
        self.assertIn('Reference image missing', html)
        data = json.loads((self.root / 'preview' / 'storyboard.json').read_text(encoding='utf-8'))
        self.assertIn('ESTIMATED', data['episodes'][0]['timing'])
        self.assertIsNone(data['episodes'][0]['shots'][0]['image'])

    def test_real_cpu_animatic(self):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            try:
                import imageio_ffmpeg
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                self.skipTest('Existing ffmpeg executable required')
        assets = {}
        for i, shot in enumerate(self.ep['shots']):
            path = self.root / (shot['id'] + '.png')
            Image.new('RGB', (144, 256), (30 + i * 30, 90, 120)).save(path)
            assets['frame-' + shot['id']] = {'path': str(path), 'sha256': digest(path)}
        result = render_animatic(self.ep, self.track, assets, self.root / 'animatic', ffmpeg)
        self.assertEqual(result['frames'], 72)
        self.assertGreater(Path(result['path']).stat().st_size, 1000)
        # Decode actual video/audio, rather than merely checking an output filename.
        subprocess.run([ffmpeg, '-v', 'error', '-i', result['path'], '-f', 'null', '-'], check=True, capture_output=True)


if __name__ == '__main__': unittest.main()
