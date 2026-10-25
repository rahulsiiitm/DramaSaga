import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from magicdrama.audiofirst.continuity import continuity_report
from magicdrama.audiofirst.core import load_brief, validate_brief, writing_request
from magicdrama.audiofirst.director import StoryDirector, validate_review
from magicdrama.audiofirst.images import image_first_plan
from magicdrama.audiofirst.runner import run, write_draft
from magicdrama.audiofirst.story import validate_story
from magicdrama.audiofirst.workflow import StageStore, SubmissionNotStarted, workspace_lock
from tests.helpers import pilot, outline, approval


class StoryTests(unittest.TestCase):
    def setUp(self):
        self.brief, self.story = pilot()

    def test_pilot_and_legacy_contracts(self):
        self.assertTrue(validate_story(self.brief, self.story)['valid'])
        legacy = write_draft(self.brief)
        self.assertEqual(validate_story(self.brief, legacy)['continuity']['status'], 'legacy_unchecked')

    def test_single_episode_default_runtime_fits(self):
        self.brief.pop('target_season_seconds')
        validate_brief(self.brief)
        self.assertEqual(writing_request(self.brief)['runtime']['target_seconds'], 60)

    def test_unknown_relationship_rejected(self):
        self.brief['relationships'][0]['to'] = 'stranger'
        with self.assertRaises(ValueError): validate_brief(self.brief)

    def test_reference_paths_relative_to_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.brief['characters'][0]['image'] = {'mode': 'upload', 'path': 'refs/mira.png'}
            path = Path(tmp) / 'brief.json'; path.write_text(json.dumps(self.brief), encoding='utf-8')
            self.assertEqual(load_brief(path)['characters'][0]['image']['path'], str((Path(tmp) / 'refs/mira.png').resolve()))

    def test_prop_teleport_rejected(self):
        self.story['episodes'][0]['shots'][2]['start_state']['props']['envelope']['owner'] = 'dev'
        with self.assertRaisesRegex(ValueError, 'unexplained cut change'): validate_story(self.brief, self.story)

    def test_undeclared_state_change_rejected(self):
        self.story['episodes'][0]['shots'][0]['changes'] = []
        with self.assertRaisesRegex(ValueError, 'explicit changes'): validate_story(self.brief, self.story)

    def test_missing_knowledge_source_rejected(self):
        self.story['episodes'][0]['shots'][2]['reveals'] = []
        with self.assertRaisesRegex(ValueError, 'sourced reveals'): validate_story(self.brief, self.story)

    def test_unknown_fact_rejected(self):
        self.story['episodes'][0]['shots'][0]['start_state']['knowledge']['mira'] = ['invented']
        with self.assertRaisesRegex(ValueError, 'unknown knowledge'): validate_story(self.brief, self.story)

    def test_missing_scene_transition_rejected(self):
        self.story['episodes'][0]['shots'][1]['scene_id'] = 'later'
        with self.assertRaisesRegex(ValueError, 'transition_reason'): validate_story(self.brief, self.story)

    def test_scene_transition_cannot_erase_prop_state(self):
        shot = self.story['episodes'][0]['shots'][2]
        shot.update(scene_id='later', transition_reason='Later that day')
        shot['start_state']['props']['envelope']['owner'] = 'set'
        shot['start_state']['props']['envelope']['hand'] = 'none'
        with self.assertRaisesRegex(ValueError, 'unexplained cut change'): validate_story(self.brief, self.story)

    def test_duplicate_shot_ids_rejected(self):
        shots = self.story['episodes'][0]['shots']; shots[1]['id'] = shots[0]['id']
        with self.assertRaisesRegex(ValueError, 'unique'): validate_story(self.brief, self.story)

    def test_ordered_line_coverage_rejected(self):
        self.story['episodes'][0]['shots'][0]['line_ids'] = ['ep1line2']
        with self.assertRaisesRegex(ValueError, 'coverage'): validate_story(self.brief, self.story)

    def test_empty_prop_list_allowed(self):
        for shot in self.story['episodes'][0]['shots']: shot['props'] = []
        self.assertTrue(validate_story(self.brief, self.story)['valid'])

    def test_character_offscreen_must_be_explicit(self):
        shot = self.story['episodes'][0]['shots'][0]; shot['visible_characters'] = ['dev']
        with self.assertRaisesRegex(ValueError, 'offscreen'): validate_story(self.brief, self.story)
        shot['offscreen_speakers'] = ['mira']
        validate_story(self.brief, self.story)

    def test_environment_upload_reused_and_scene_reference_selected(self):
        self.brief['environments'][0]['image'] = {'mode': 'upload', 'path': 'study.png'}
        plan = image_first_plan(self.brief, self.story)
        self.assertEqual(plan['uploaded_local_references']['location-study'], 'study.png')
        tasks = {t['id']: t for t in plan['tasks']}
        self.assertNotIn('location-study', tasks)
        self.assertIn('frame-ep1shot1', tasks['frame-ep1shot2']['references'])
        self.assertFalse(any(t['kind'] == 'character_stage' for t in tasks.values()))

    def test_planning_resume_preserves_previous_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'run'
            result = run(self.brief, path, self.story)
            self.assertTrue(Path(result['storyboard_preview']).is_file())
            with self.assertRaises(ValueError): run(self.brief, path, self.story)
            self.assertEqual(run(self.brief, path, self.story, resume=True)['continuity_status'], 'contract_checked_not_semantic_proof')


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.brief, self.story = pilot()

    def test_stages_resume_without_duplicate_inference(self):
        transport = Mock(side_effect=[outline(self.story), self.story['episodes'][0], approval()])
        with tempfile.TemporaryDirectory() as tmp:
            writer = StoryDirector(transport, 'test-model', tmp)
            first = writer(writing_request(self.brief))
            second = writer(writing_request(self.brief))
            self.assertEqual(first['episodes'], second['episodes'])
            self.assertEqual(transport.call_count, 3)
            self.assertEqual(first['canon']['state']['props']['key']['owner'], 'mira')

    def test_evidenced_rejection_repairs_only_episode(self):
        ep = self.story['episodes'][0]
        rejected = approval(); rejected['approved'] = False; rejected['dimensions']['dialogue'] = False
        rejected['issues'] = [{'shot_id': ep['shots'][0]['id'], 'quote': ep['lines'][0]['text'], 'problem': 'Unnatural delivery', 'suggestion': 'Use a quieter phrasing'}]
        transport = Mock(side_effect=[outline(self.story), ep, rejected, ep, approval()])
        with tempfile.TemporaryDirectory() as tmp:
            StoryDirector(transport, 'test', tmp)(writing_request(self.brief))
            self.assertEqual(transport.call_count, 5)

    def test_rejected_draft_never_accepted_after_retry_limit(self):
        ep = self.story['episodes'][0]
        rejected = approval(); rejected['approved'] = False; rejected['dimensions']['causality'] = False
        rejected['issues'] = [{'shot_id': ep['shots'][0]['id'], 'quote': ep['lines'][0]['text'], 'problem': 'Unmotivated', 'suggestion': 'Clarify goal'}]
        with tempfile.TemporaryDirectory() as tmp:
            writer = StoryDirector(Mock(side_effect=[outline(self.story), ep, rejected]), 'test', tmp, max_repairs=0)
            with self.assertRaisesRegex(ValueError, 'Creative review rejected'): writer(writing_request(self.brief))
            self.assertTrue((Path(tmp) / 'rejected.json').is_file())

    def test_hallucinated_review_quote_rejected(self):
        review = approval(); review['issues'] = [{'shot_id': 'ep1shot1', 'quote': 'Not in script', 'problem': 'x', 'suggestion': 'y'}]
        with self.assertRaisesRegex(ValueError, 'quote actual'): validate_review(review, self.story['episodes'][0])

    def test_model_cannot_skip_outline_beats(self):
        ep = copy.deepcopy(self.story['episodes'][0]); ep['shots'][0]['beat_id'] = 'invented'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'outline beats'):
                StoryDirector(Mock(side_effect=[outline(self.story), ep]), 'test', tmp,max_repairs=0)(writing_request(self.brief))

    def test_structural_repair_is_bounded_and_reviewed(self):
        invalid=copy.deepcopy(self.story['episodes'][0]);invalid['shots'][0]['changes']=[]
        transport=Mock(side_effect=[outline(self.story),invalid,self.story['episodes'][0],approval()])
        with tempfile.TemporaryDirectory() as tmp:
            result=StoryDirector(transport,'test',tmp)(writing_request(self.brief))
            self.assertEqual(len(result['episodes']),1)
            self.assertEqual(transport.call_count,4)

    def test_local_writer_resumes_cached_work_without_running_model(self):
        from magicdrama.audiofirst.local_writer import LocalWriter
        http=Mock();http.get.return_value.json.return_value={'models':[{'name':'test-model'}]}
        responses=[]
        for value in (outline(self.story),self.story['episodes'][0],approval()):
            response=Mock();response.json.return_value={'message':{'content':json.dumps(value)}};responses.append(response)
        http.post.side_effect=responses
        with tempfile.TemporaryDirectory() as tmp:
            writer=LocalWriter('test-model',http,workspace=tmp)
            writer(writing_request(self.brief));http.get.reset_mock();http.post.reset_mock()
            writer(writing_request(self.brief))
            http.get.assert_not_called();http.post.assert_not_called()

    def test_cloud_stages_need_individual_exact_request_approvals(self):
        import datetime as dt
        from magicdrama.audiofirst.cloud_writer import NvidiaClaudeWriter,NVIDIA_MODEL,CLAUDE_MODEL
        from magicdrama.audiofirst.execution import signature
        config={'nvidia_model':NVIDIA_MODEL,'claude_model':CLAUDE_MODEL,'max_output_tokens':8000,'claude_run_cap_usd':'2.30'}
        with tempfile.TemporaryDirectory() as tmp:
            writer=NvidiaClaudeWriter(config,{'stages':[]},{'nvidia':'fixture'},str(Path(tmp)/'ledger.sqlite'),enabled=True,http=Mock())
            writer.nvidia=Mock(return_value=outline(self.story))
            director=writer.staged(tmp)
            with self.assertRaisesRegex(SubmissionNotStarted,'approval missing'):director(writing_request(self.brief))
            writer.nvidia.assert_not_called()
            body=json.loads(next(Path(tmp).glob('outline-*-request.json')).read_text(encoding='utf-8'))
            writer.approval={'stages':[{'request_sha256':signature({'body':body,'config':config}),
                'expires_at':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),
                'run_id':'fixture','approval_reference':'synthetic-exact-approval',
                'key_identities':{'nvidia':'Saralya NVIDIA API key','claude':'Anthropic API key'}}]}
            with self.assertRaisesRegex(SubmissionNotStarted,'approval missing'):director(writing_request(self.brief))
            self.assertEqual(writer.nvidia.call_count,1)
            # The completed outline stays cached; missing draft approval cannot trigger it again.
            with self.assertRaises(SubmissionNotStarted):director(writing_request(self.brief))
            self.assertEqual(writer.nvidia.call_count,1)


class StageTests(unittest.TestCase):
    def test_workspace_lock_prevents_concurrent_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'workspace.sqlite'
            with workspace_lock(path):
                with self.assertRaisesRegex(RuntimeError,'busy'):
                    with workspace_lock(path):self.fail('Concurrent writer acquired workspace')
            with workspace_lock(path):pass

    def test_change_invalidates_only_dependent_inputs(self):
        action = Mock(return_value={'value': 'done'})
        with tempfile.TemporaryDirectory() as tmp, StageStore(Path(tmp) / 'state.sqlite') as store:
            store.run('a', {'v': 1}, action); store.run('b', {'v': 1}, action)
            store.run('a', {'v': 2}, action); store.run('b', {'v': 1}, action)
            self.assertEqual(action.call_count, 3)

    def test_uncertain_remote_work_not_resubmitted(self):
        action = Mock(side_effect=TimeoutError)
        with tempfile.TemporaryDirectory() as tmp, StageStore(Path(tmp) / 'state.sqlite') as store:
            with self.assertRaises(TimeoutError): store.run('remote', {}, action, remote=True)
            with self.assertRaisesRegex(RuntimeError, 'unresolved'): store.run('remote', {}, action, remote=True)
            self.assertEqual(action.call_count, 1)

    def test_preflight_refusal_can_resume_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp, StageStore(Path(tmp) / 'state.sqlite') as store:
            with self.assertRaises(SubmissionNotStarted):
                store.run('remote', {}, Mock(side_effect=SubmissionNotStarted('approval absent')), remote=True)
            self.assertEqual(store.run('remote', {}, lambda: {'ok': True}, remote=True), {'ok': True})

    def test_changed_cached_bytes_do_not_silently_pass(self):
        from magicdrama.audiofirst.core import digest
        with tempfile.TemporaryDirectory() as tmp, StageStore(Path(tmp) / 'state.sqlite') as store:
            path = Path(tmp) / 'asset'; path.write_bytes(b'original')
            store.run('asset', {}, lambda: {'artifacts': [{'path': str(path), 'sha256': digest(path)}]})
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'missing/changed'): store.run('asset', {}, Mock())


if __name__ == '__main__': unittest.main()
