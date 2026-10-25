import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT,pilot,audio_fixture,reference_images,profile


class CLITests(unittest.TestCase):
    def call(self,*arguments):
        result=subprocess.run([sys.executable,str(ROOT/'audiofirst.py'),*map(str,arguments)],cwd=ROOT,check=True,capture_output=True,text=True)
        return json.loads(result.stdout)

    def test_pilot_run_and_resume_from_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=['run','--brief',ROOT/'examples/pilot/brief.json','--story',ROOT/'examples/pilot/story.json','--out',Path(tmp)/'plan']
            first=self.call(*args)
            self.assertEqual(first['paid_requests'],0)
            self.assertTrue(Path(first['storyboard_preview']).is_file())
            second=self.call(*args,'--resume')
            self.assertEqual(first['storyboard_preview'],second['storyboard_preview'])

    def test_measured_compile_prepare_and_storyboard_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);brief,story=pilot();ep,track=audio_fixture(root,story['episodes'][0]);story['episodes'][0]=ep
            files={'brief':brief,'story':story,'audio':track['audio'],'alignment':{'audio_sha256':track['audio']['sha256'],'cues':track['cues']},
                   'review':track['audio_review'],'renderer':profile(),'assets':reference_images(root,ep)}
            for name,value in files.items():(root/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
            plan=self.call('compile-render','--brief',root/'brief.json','--story',root/'story.json','--episode','ep1',
                '--audio',root/'audio.json','--alignment',root/'alignment.json','--audio-review',root/'review.json',
                '--renderer',root/'renderer.json','--assets',root/'assets.json','--out',root/'compiled')
            self.assertTrue(plan['inputs_bound'])
            candidates=self.call('prepare-render-inputs','--plan',root/'compiled/render-plan.json','--out',root/'inputs')
            self.assertEqual(len([v for v in candidates.values() if v['kind']=='audio']),6)
            (root/'tracks.json').write_text(json.dumps({'ep1':track}),encoding='utf-8')
            result=self.call('storyboard','--brief',root/'brief.json','--story',root/'story.json','--assets',root/'assets.json',
                             '--tracks',root/'tracks.json','--out',root/'preview')
            self.assertTrue(Path(result['path']).is_file())
            self.assertEqual(json.loads((root/'preview/storyboard.json').read_text(encoding='utf-8'))['episodes'][0]['timing'],'measured')


if __name__=='__main__':unittest.main()
