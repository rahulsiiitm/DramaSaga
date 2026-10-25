import base64
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from PIL import Image
from magicdrama.audiofirst.bridge import merge_packages
from magicdrama.audiofirst.core import validate_brief, writing_request
from magicdrama.audiofirst.execution import signature
from magicdrama.audiofirst.form import save_form
from magicdrama.audiofirst.images import image_first_plan
from magicdrama.audiofirst.renderplan import compile_render_plan, require_render_plan,prepare_render_inputs,verify_derived_audio
from magicdrama.audiofirst.workflow import StageStore
from tests.helpers import pilot, profile, audio_fixture, reference_images


class FormTests(unittest.TestCase):
    def test_uploaded_environment_and_character_saved_without_mutating_payload(self):
        brief,_=pilot();brief['characters'][0]['image']={'mode':'upload','path':'pending/mira'}
        brief['environments'][0]['image']={'mode':'upload','path':'pending/study'}
        image=io.BytesIO();Image.new('RGB',(128,128),'red').save(image,format='PNG')
        uploads={k:base64.b64encode(image.getvalue()).decode() for k in ('mira','environment-study')}
        payload={'brief':brief,'uploads':uploads};before=copy.deepcopy(payload)
        with tempfile.TemporaryDirectory() as tmp:
            result=save_form(payload,tmp);saved=json.loads(Path(result['brief_path']).read_text(encoding='utf-8'))
            self.assertTrue(Path(saved['environments'][0]['image']['path']).is_file())
            self.assertTrue(Path(saved['characters'][0]['image']['path']).is_file())
            self.assertEqual(payload,before)
            with self.assertRaisesRegex(ValueError,'already saved'):save_form(payload,tmp)

    def test_corrupt_upload_never_writes_a_brief(self):
        brief,_=pilot();brief['characters'][0]['image']={'mode':'upload','path':'pending/mira'}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):save_form({'brief':brief,'uploads':{'mira':base64.b64encode(b'not an image').decode()}},tmp)
            self.assertFalse((Path(tmp)/'brief.json').exists())

    def test_reference_source_bytes_change_plan_identity(self):
        brief,story=pilot()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reference.png';Image.new('RGB',(128,128),'red').save(path)
            brief['environments'][0]['image']={'mode':'upload','path':str(path)}
            first=image_first_plan(brief,story)
            Image.new('RGB',(128,128),'blue').save(path)
            second=image_first_plan(brief,story)
            self.assertNotEqual(first['plan_sha256'],second['plan_sha256'])


class RecoveryTests(unittest.TestCase):
    def test_external_response_recovery_cannot_rewrite_completed_work(self):
        with tempfile.TemporaryDirectory() as tmp, StageStore(Path(tmp)/'stages.sqlite') as store:
            with self.assertRaises(TimeoutError):store.run('request',{'prompt':'a'},Mock(side_effect=TimeoutError),remote=True)
            store.reconcile('request',signature({'prompt':'a'}),{'actual_response':'recovered'},'provider-record-test')
            transport=Mock()
            self.assertEqual(store.run('request',{'prompt':'a'},transport,remote=True),{'actual_response':'recovered'})
            transport.assert_not_called()
            with self.assertRaises(ValueError):store.reconcile('request',signature({'prompt':'a'}),{},'another-reference')

    def test_frame_bytes_bound_to_render_plan(self):
        brief,story=pilot()
        with tempfile.TemporaryDirectory() as tmp:
            episode,track=audio_fixture(tmp,story['episodes'][0]);frames=reference_images(tmp,episode)
            plan=compile_render_plan(episode,track,profile(),reference_assets=frames)
            Image.new('RGB',(144,256),'white').save(frames['frame-ep1shot1']['path'])
            with self.assertRaisesRegex(ValueError,'reference image changed'):require_render_plan(plan)

    def test_partial_season_cannot_skip_to_next_season(self):
        brief,_=pilot();brief['season']=2
        with self.assertRaisesRegex(ValueError,'partial episode'):
            writing_request(brief,{'series_id':brief['series_id'],'season':1,'canon':{'complete_season':False}})

    def test_exact_pcm_slices_and_padding_preserve_source_provenance(self):
        import wave
        brief,story=pilot()
        with tempfile.TemporaryDirectory() as tmp:
            episode,track=audio_fixture(tmp,story['episodes'][0]);frames=reference_images(tmp,episode)
            plan=compile_render_plan(episode,track,profile(min_seconds=5,max_seconds=5,durations=[5]),reference_assets=frames)
            candidates=prepare_render_inputs(plan,Path(tmp)/'inputs')
            record=candidates['audio-'+plan['jobs'][0]['id']]
            verify_derived_audio(plan['jobs'][0],record)
            with wave.open(record['path'],'rb') as wav:
                self.assertEqual(wav.getnframes()/wav.getframerate(),5)
            path=Path(record['path']);raw=bytearray(path.read_bytes());raw[-1]=1;path.write_bytes(raw)
            from magicdrama.audiofirst.core import digest
            record['sha256']=digest(path)
            with self.assertRaisesRegex(ValueError,'exact accepted samples'):verify_derived_audio(plan['jobs'][0],record)

    def test_package_merge_rejects_missing_duplicate_and_other_story(self):
        brief,story=pilot();base={'audio_mode':'locked','source_story_sha256':signature(story),
            'season':{'series_id':brief['series_id'],'season':1,'episodes':[{'id':'ep1'}],
                      'canon':{'complete_season':False,'facts':[],'ending':'choice','unresolved':[],'characters':brief['characters']}}}
        merged=merge_packages(brief,story,[base]);self.assertTrue(merged['season']['canon']['complete_season'])
        with self.assertRaisesRegex(ValueError,'Duplicate'):merge_packages(brief,story,[base,base])
        wrong=copy.deepcopy(base);wrong['source_story_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'same exact'):merge_packages(brief,story,[wrong])
        with self.assertRaisesRegex(ValueError,'Every planned'):merge_packages(brief,story,[])


if __name__=='__main__':unittest.main()
