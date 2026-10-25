"""Bridge measured story plans to exact provider requests and accepted-media packages."""
import copy
import json
from pathlib import Path

from .core import digest, write_json
from .execution import signature
from .images import require_rendered_images
from .renderplan import compile_render_plan, require_render_plan, validate_track
from .story import validate_story


def video_manifest(plan, image_plan, accepted_images, uploads, quotes, run_id, batch_id):
    """Build requests for verified existing routes; no upload, network, or spend."""
    require_render_plan(plan)
    if plan.get('inputs_bound') is not True:
        raise ValueError('Compile with actual --assets reference images before materializing provider requests')
    require_rendered_images(image_plan, accepted_images)
    profile = plan['renderer']
    if profile.get('provider') != 'magichour' or plan['audio_mode'] != 'locked':
        raise ValueError('No live adapter for this profile/audio mode; use a tested adapter or import accepted clips')
    def uploaded(aid, expected_hash):
        record = uploads.get(aid, {})
        path = record.get('file_path', '')
        if record.get('sha256') != expected_hash or not isinstance(path, str) or not path.startswith('api-assets/') or any(p in ('', '.', '..') for p in path.split('/')):
            raise ValueError('Missing hash-bound provider upload: ' + aid)
        return path
    jobs = []
    for render in plan['jobs']:
        if len(render['shot_ids']) != 1 or render['mode'] not in ('image_to_video', 'audio_to_video'):
            raise ValueError('Magic Hour request builder supports single-shot image/audio routes only')
        if any(c.get('end_frame_reference') for c in render['cuts']):
            raise ValueError('This request builder has no verified end-frame asset mapping')
        image_id = render['first_frame']
        image = accepted_images.get(image_id)
        if image is None:
            raise ValueError('Compiled first frame absent from accepted image evidence')
        if image['sha256']!=render['reference_images'][0]['sha256']:
            raise ValueError('Accepted keyframe differs from compiled reference bytes')
        body = {'name': render['id'], 'resolution': profile.get('resolution', '720p'), 'end_seconds': render['request_seconds'],
                'assets': {'image_file_path': uploaded(image_id, image['sha256'])},
                'style': {'prompt': json.dumps([{'camera': c['camera'], 'action': c['action'], 'start_state': c.get('start_state'),
                                               'end_state': c.get('end_state'), 'lines': c['active_lines']} for c in render['cuts']], ensure_ascii=False)}}
        if render['mode'] == 'audio_to_video':
            if profile['model'] != 'magichour-audio-to-video':
                raise ValueError('Audio-to-video route has no selectable model field; use its explicit route identity')
            derived_id='audio-'+render['id']
            if derived_id in uploads:
                from .renderplan import verify_derived_audio
                derived=verify_derived_audio(render,uploads[derived_id])
                body['assets']['audio_file_path']=uploaded(derived_id,derived['sha256'])
                body['start_seconds']=0
                body['end_seconds']=render['request_seconds']
            else:
                # Legacy full-master route, only without duration padding.
                if render['request_seconds'] != render['seconds']:
                    raise ValueError('Use prepare-render-inputs for exact padded audio')
                body['assets']['audio_file_path'] = uploaded('audio-' + plan['episode_id'], render['audio']['sha256'])
                body['start_seconds'] = render['audio_segment']['start_seconds']
                body['end_seconds'] = render['audio_segment']['end_seconds']
            endpoint = '/v1/audio-to-video'
        else:
            body['model'] = profile['model']
            endpoint = '/v1/image-to-video'
        quote = quotes.get(render['id'])
        if not isinstance(quote, dict):
            raise ValueError('Exact current quote missing for ' + render['id'])
        jobs.append({'id': render['id'], 'episode_id': plan['episode_id'], 'provider': 'magichour', 'kind': 'video',
                     'request': {'endpoint': endpoint, 'body': body}, 'quote': quote,
                     'image_evidence': {'plan': image_plan, 'accepted': accepted_images},
                     'render_binding': {'plan_sha256': plan['plan_sha256'], 'input_sha256': render['input_sha256'],
                                        'request_sha256': signature({'endpoint': endpoint, 'body': body})}})
    manifest = {'run_id': run_id, 'batch_id': batch_id, 'jobs': jobs,
                'uploads': [{'sha256': x['sha256'], 'kind': 'audio' if key.startswith('audio-') else 'image'} for key, x in uploads.items()]}
    return manifest


def upload_inputs(manifest,token,candidates,ledger,output,keys,enabled=False,http=None):
    """Explicit upload-only phase. Cached receipts preserve derived-audio provenance."""
    from .live import LiveAdapters
    from .workflow import StageStore
    from .execution import RunLedger
    if manifest.get('jobs')!=[]:raise ValueError('Use an exact upload-only manifest with no generation jobs')
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    result={}
    with StageStore(root/'uploads.sqlite') as store:
        provider_ledger=RunLedger(ledger)
        try:
            adapter=LiveAdapters(manifest,token,provider_ledger,keys,enabled,http)
            for aid,asset in candidates.items():
                if digest(asset['path'])!=asset['sha256'] or asset['kind'] not in ('image','audio'):
                    raise ValueError('Upload input missing/changed')
                def upload(asset=asset):
                    path=adapter.upload(asset['path'],asset['kind'])
                    return {**asset,'file_path':path}
                result[aid]=store.run('upload-'+aid,{'asset':asset,'manifest':manifest},upload,remote=True)
        finally:
            provider_ledger.close()
    write_json(root/'uploads.json',result)
    return result


def accepted_package(brief, story, episode_id, track, plan, media):
    validate_story(brief, story)
    episode = next((ep for ep in story['episodes'] if ep['id'] == episode_id), None)
    if episode is None:
        raise ValueError('Unknown episode')
    validate_track(episode, track)
    if track['seconds']>brief.get('max_episode_seconds',180):
        raise ValueError('Measured audio exceeds the requested episode maximum')
    require_render_plan(plan)
    if plan['audio_mode'] != 'locked':
        raise ValueError('Native generated audio requires new review/alignment and a locked plan')
    if plan.get('inputs_bound') is not True:
        raise ValueError('Compile with actual reference --assets before accepting generated media')
    references={image['id']:image for job in plan['jobs'] for image in job['reference_images']}
    fresh = compile_render_plan(episode, track, plan['renderer'], connected=any(len(j['shot_ids']) > 1 for j in plan['jobs']),reference_assets=references)
    if fresh != plan:
        raise ValueError('Render plan is stale for story/timing')
    shots = []
    for job in plan['jobs']:
        asset = media.get(job['id'], {})
        path = Path(asset.get('path', ''))
        if not path.is_file() or digest(path) != asset.get('sha256') or asset.get('pixel_checked') is not True:
            raise ValueError('Every generated result needs actual pixel review bound to bytes')
        if asset.get('input_sha256') != job['input_sha256']:
            raise ValueError('Accepted render is stale for its shot inputs')
        if asset.get('kind') != 'video':
            raise ValueError('Production render results must be videos; use animatic for still previews')
        for cut in job['cuts']:
            shots.append({**asset, 'id': cut['id'], 'frames': cut['frames'],
                          'source_start_frame': cut['start_frame'] - job['start_frame']})
    spec = {'id': episode_id, 'audio': track['audio'], 'audio_checked': True,
            'cue_audio_sha256': track['audio']['sha256'], 'cues': track['cues'],
            'spoken_lines': [l['text'] for l in episode['lines']], 'names': {c['id']: c['name'] for c in brief['characters']}, 'shots': shots}
    from .continuity import require_continuity
    state=require_continuity(brief,{**story,'episodes':story['episodes'][:story['episodes'].index(episode)+1]})['final_state']
    known=set().union(*(set(ids) for ids in state['knowledge'].values())) if state else set()
    canon={'characters':brief['characters'],'facts':[f for f in story.get('facts',[]) if f['id'] in known],
           'unresolved':[episode['cliffhanger']],'ending':episode['turn'],'state':state,
           'complete_season':len(story['episodes'])==1,'included_episode_ids':[episode_id]}
    return {'audio_mode': 'locked', 'season': {'series_id': brief['series_id'], 'season': brief['season'],
            'canon': copy.deepcopy(canon), 'episodes': [spec]}, 'source_plan_sha256': plan['plan_sha256'],'source_story_sha256':signature(story)}


def merge_packages(brief,story,packages):
    """Merge exact-story episode packages, never turn a partial season into canon."""
    validate_story(brief,story)
    selected={}
    for package in packages:
        season=package['season']
        if package.get('audio_mode')!='locked' or package.get('source_story_sha256')!=signature(story) or (season['series_id'],season['season'])!=(brief['series_id'],brief['season']):
            raise ValueError('Episode packages must come from the same exact story and season')
        for episode in season['episodes']:
            if episode['id'] in selected:raise ValueError('Duplicate episode package')
            selected[episode['id']]=(episode,season['canon'])
    expected=[ep['id'] for ep in story['episodes']]
    if set(selected)!=set(expected):raise ValueError('Every planned episode must have an accepted-media package')
    canon=copy.deepcopy(selected[expected[-1]][1]);canon.update(complete_season=True,included_episode_ids=expected)
    return {'audio_mode':'locked','season':{'series_id':brief['series_id'],'season':brief['season'],'canon':canon,
            'episodes':[selected[eid][0] for eid in expected]},'source_story_sha256':signature(story)}
