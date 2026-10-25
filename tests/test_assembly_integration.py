"""Real FFmpeg/ffprobe integration with synthetic colors and tone, not real acting."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from magicdrama.audiofirst import assembly
from magicdrama.audiofirst.bridge import accepted_package
from magicdrama.audiofirst.core import digest
from magicdrama.audiofirst.production_run import media_run
from magicdrama.audiofirst.renderplan import compile_render_plan
from magicdrama.audiofirst.season import inspect_season_zip
from tests.helpers import pilot, audio_fixture, profile, reference_images


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Existing ffmpeg and ffprobe required')
class AssemblyIntegrationTests(unittest.TestCase):
    def make_clip(self,path,color,frames=12):
        subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i',f'color=c={color}:s=144x256:r=24',
                        '-frames:v',str(frames),'-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True)

    def test_assemble_resume_and_only_reconform_replaced_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);brief,story=pilot();ep,track=audio_fixture(root,story['episodes'][0]);story['episodes'][0]=ep
            plan=compile_render_plan(ep,track,profile(),reference_assets=reference_images(root,ep));media={}
            for index,job in enumerate(plan['jobs']):
                path=root/(job['id']+'.mp4');self.make_clip(path,['red','green','blue','yellow','cyan','magenta'][index])
                media[job['id']]={'path':str(path),'sha256':digest(path),'kind':'video','pixel_checked':True,'input_sha256':job['input_sha256']}
            package=accepted_package(brief,story,'ep1',track,plan,media)
            output=root/'season'
            first=media_run(package,output,resume=True)
            self.assertEqual(inspect_season_zip(first['archive'])['series_id'],brief['series_id'])
            info=assembly.media_info(first['episodes'][0]['path'])
            self.assertAlmostEqual(float(info['format']['duration']),track['seconds'],delta=.1)
            self.assertEqual(len([s for s in info['streams'] if s['codec_type']=='audio']),1)
            with patch.object(assembly,'ff',wraps=assembly.ff) as encode:
                again=media_run(package,output,resume=True)
                self.assertEqual(encode.call_count,0)
            self.assertEqual(first['archive_sha256'],again['archive_sha256'])
            # An explicit reroll replaces one accepted clip; good earlier clips stay cached.
            last=plan['jobs'][-1];path=root/'reroll.mp4';self.make_clip(path,'white')
            media[last['id']].update(path=str(path),sha256=digest(path))
            repaired=accepted_package(brief,story,'ep1',track,plan,media)
            with patch.object(assembly,'ff',wraps=assembly.ff) as encode:
                new=media_run(repaired,output,resume=True)
                # One conformance, one audio master, one concat; captions encode separately.
                self.assertEqual(encode.call_count,3)
            self.assertNotEqual(first['archive'],new['archive'])
            self.assertTrue(Path(first['archive']).is_file())
            archive=inspect_season_zip(new['archive'])
            self.assertFalse(any('reroll' in item['path'] for item in archive['files']))

    def test_grouped_video_is_trimmed_from_each_cut_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);brief,story=pilot();ep,track=audio_fixture(root,story['episodes'][0])
            # One three-second source: first half red, second half blue.
            path=root/'group.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=144x256:r=24:d=1.5',
                '-f','lavfi','-i','color=blue:s=144x256:r=24:d=1.5','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
                '-map','[v]','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True)
            spec={'id':'ep1','audio':track['audio'],'audio_checked':True,'cue_audio_sha256':track['audio']['sha256'],
                  'cues':track['cues'],'spoken_lines':[l['text'] for l in ep['lines']],'names':{c['id']:c['name'] for c in brief['characters']},
                  'shots':[{'path':str(path),'sha256':digest(path),'kind':'video','frames':36,'source_start_frame':offset,'pixel_checked':True} for offset in (0,36)]}
            result=assembly.assemble_episode(spec,root/'episode')
            # Decode the second conformed cut and inspect its actual blue pixel values.
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(root/'episode'/'shot-0001.mp4'),'-vf','scale=1:1',
                '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
            self.assertGreater(raw[2],raw[0]+100)
            self.assertGreater(Path(result['path']).stat().st_size,1000)


if __name__=='__main__':unittest.main()
