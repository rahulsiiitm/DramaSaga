import base64
from contextlib import closing
import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from magicdrama.audiofirst.benchmark import compare_trials
from magicdrama.audiofirst.core import digest
from magicdrama.audiofirst.execution import RunLedger, signature, verify_approval
from magicdrama.audiofirst.live import LiveAdapters
from magicdrama.audiofirst.production_run import media_run


def fixture():
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=5,minutes=30))).date().isoformat()
    job={'id':'voice1','episode_id':'ep1','provider':'elevenlabs','kind':'voice',
         'request':{'endpoint':'/v1/text-to-dialogue/with-timestamps','body':{'model_id':'eleven_v3','inputs':[{'text':'Wait.','voice_id':'test-voice'}]}},
         'quote':{'amount':5,'unit':'characters','verified_on':today,'source_url':'https://example.test/fixture',
                  'billing':{'unit':'USD','max_amount':'0.10','rate_verified':True}}}
    manifest={'run_id':'r1','batch_id':'b1','jobs':[job]}
    token={'run_id':'r1','batch_id':'b1','expires_at':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),
           'approval_reference':'synthetic-test-only','manifest_sha256':signature(manifest),'job_counts':{'elevenlabs:voice':1},
           'totals':{'elevenlabs:characters':'5'},'billing_limits':{'voice1':job['quote']['billing']},
           'key_identities':{'magichour':'Yogita:image-video-only','elevenlabs':'Roopesh:approved-ElevenLabs'}}
    return manifest,token


class ExecutionTests(unittest.TestCase):
    def test_upload_only_phase_resumes_without_retransmitting(self):
        from magicdrama.audiofirst.bridge import upload_inputs
        manifest,token=fixture();manifest['jobs']=[]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reference.png';path.write_bytes(b'synthetic-upload-fixture')
            asset={'path':str(path),'sha256':digest(path),'kind':'image'}
            manifest['uploads']=[{'sha256':asset['sha256'],'kind':'image'}]
            token.update(manifest_sha256=signature(manifest),job_counts={},totals={},billing_limits={})
            http=Mock();http.post.return_value.status_code=200
            http.post.return_value.json.return_value={'items':[{'upload_url':'https://storage.googleapis.com/fixture','file_path':'api-assets/fixture/reference'}]}
            http.put.return_value.status_code=200
            first=upload_inputs(manifest,token,{'frame-test':asset},Path(tmp)/'ledger.sqlite',Path(tmp)/'uploads',{'magichour':'fixture'},True,http)
            second=upload_inputs(manifest,token,{'frame-test':asset},Path(tmp)/'ledger.sqlite',Path(tmp)/'uploads',{'magichour':'fixture'},True,http)
            self.assertEqual(first,second);self.assertEqual(http.post.call_count,1);self.assertEqual(http.put.call_count,1)

    def test_dependencies_rejected_before_reservation(self):
        manifest,token=fixture();manifest['jobs'][0]['depends_on']=['missing'];token['manifest_sha256']=signature(manifest)
        with self.assertRaisesRegex(ValueError,'dependency'):verify_approval(manifest,token,True)

    def test_uncertain_paid_submission_is_not_repeated(self):
        manifest,token=fixture();http=Mock();http.post.side_effect=TimeoutError
        with tempfile.TemporaryDirectory() as tmp, closing(RunLedger(Path(tmp)/'ledger.sqlite')) as ledger:
            adapter=LiveAdapters(manifest,token,ledger,{'elevenlabs':'fixture'},True,http)
            with self.assertRaises(TimeoutError):adapter.execute('voice1',Path(tmp)/'voice.mp3')
            with self.assertRaisesRegex(RuntimeError,'never auto-resubmit'):adapter.execute('voice1',Path(tmp)/'voice.mp3')
            self.assertEqual(http.post.call_count,1)

    def test_completed_submission_reuses_bytes(self):
        manifest,token=fixture();response=Mock(status_code=200);response.json.return_value={'audio_base64':base64.b64encode(b'synthetic-audio').decode()}
        http=Mock();http.post.return_value=response
        with tempfile.TemporaryDirectory() as tmp, closing(RunLedger(Path(tmp)/'ledger.sqlite')) as ledger:
            adapter=LiveAdapters(manifest,token,ledger,{'elevenlabs':'fixture'},True,http)
            output=Path(tmp)/'voice.mp3';first=adapter.execute('voice1',output);second=adapter.execute('voice1',output)
            self.assertEqual(first['sha256'],second['sha256']);self.assertEqual(http.post.call_count,1)

    def test_crash_after_download_reconciles_without_resubmission(self):
        manifest,token=fixture();data={'audio_base64':base64.b64encode(b'fixture').decode()}
        with tempfile.TemporaryDirectory() as tmp, closing(RunLedger(Path(tmp)/'ledger.sqlite')) as ledger:
            adapter=LiveAdapters(manifest,token,ledger,{'elevenlabs':'fixture'},True,Mock())
            ledger.transition('r1','voice1','reserved','submitting');ledger.transition('r1','voice1','submitting','submitted',data)
            output=Path(tmp)/'voice.mp3';output.write_bytes(b'fixture')
            self.assertEqual(adapter.execute('voice1',output)['sha256'],digest(output))
            adapter.http.post.assert_not_called()

    def test_native_audio_rejected_before_provider_instantiation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'Native audio'):
                media_run({'audio_mode':'native','manifest':{}},Path(tmp)/'out',enabled=True)
            self.assertFalse((Path(tmp)/'out-state').exists())

    def test_changed_manifest_cannot_reuse_old_approval(self):
        manifest,token=fixture();manifest['jobs'][0]['request']['body']['inputs'][0]['text']='Changed'
        with self.assertRaisesRegex(ValueError,'Exact approved'):verify_approval(manifest,token,True)


class BenchmarkTests(unittest.TestCase):
    def trial(self,name,**extra):
        return {'name':name,'input_sha256':'a'*64,'accepted_seconds':10,'generated_seconds':20,'total_cost':{'amount':2,'unit':'USD'},
                'critical_errors':[],'viewer_scores':[],'elapsed_seconds':60,'manual_minutes':3,'rerolls':1,**extra}

    def test_cost_counts_rejects_and_no_invented_quality_winner(self):
        report=compare_trials([self.trial('baseline'),self.trial('candidate',accepted_seconds=0)])
        self.assertEqual(report['trials'][0]['cost_per_accepted_second'],.2)
        self.assertIsNone(report['trials'][1]['cost_per_accepted_second'])
        self.assertIsNone(report['automatic_winner'])

    def test_unequal_inputs_cannot_claim_controlled_comparison(self):
        with self.assertRaisesRegex(ValueError,'same script'):
            compare_trials([self.trial('a'),self.trial('b',input_sha256='b'*64)])


if __name__=='__main__':unittest.main()
