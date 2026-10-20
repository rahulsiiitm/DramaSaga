"""Nano Banana image-first planning only. No network, credentials or live executor."""
import hashlib
import json
from .core import integer, identifier
from .planning import reference_plan
from .story import validate_story

MODEL = 'nano-banana-2.1'
CREDITS_PER_IMAGE = 50
DEFAULT_IMAGE_CAP = 12  # 600 credits maximum, part of (not extra to) episode total.
SOURCES = ['https://docs.magichour.ai/api-reference/models',
           'https://docs.magichour.ai/api-reference/image-projects/ai-image-generator',
           'https://docs.magichour.ai/api-reference/image-projects/ai-image-editor']


def image_request(asset, uploaded_references=None):
    """Materialize a request only after every dependency has a provider asset path."""
    uploaded_references = uploaded_references or {}
    refs = asset.get('references', [])
    paths = []
    for ref in refs:
        path = uploaded_references.get(ref)
        if not isinstance(path, str) or not path.startswith('api-assets/') or '..' in path.split('/'):
            raise ValueError('Missing verified provider asset path for ' + ref)
        paths.append(path)
    # Docs permit primary image plus nine additional; use at most nine total.
    if len(paths) > 9:
        raise ValueError('Conservative reference limit exceeded; do not drop identities silently')
    body = {'name': asset['id'], 'image_count': 1, 'model': MODEL,
            'aspect_ratio': '9:16', 'resolution': '1k', 'style': {'prompt': asset['prompt']}}
    endpoint = '/v1/ai-image-editor' if paths else '/v1/ai-image-generator'
    if paths:
        body['assets'] = {'image_file_paths': paths}
    return {'method': 'POST', 'endpoint': endpoint, 'body': body,
            'quoted_credits': CREDITS_PER_IMAGE, 'live_enabled': False}


def image_first_plan(brief, story, image_cap=DEFAULT_IMAGE_CAP, exposure=None):
    """Charge shared references to first-use episode. Reuse is planned, never presumed generated.

    exposure must include all batch episode charges + outstanding reservations, including
    images, video, retries and unknown submissions. Caller must reconcile it before execution.
    """
    validate_story(brief, story)
    integer(image_cap, 'image_cap', 1, 60)
    reference_plan(brief, story['episodes'])
    cast = {c['id']: c for c in brief['characters']}
    available = {}; tasks = []; episodes = []; known = set(); location_specs = {}; prop_specs = {}
    for character in brief['characters']:
        if character['image']['mode'] == 'upload':
            available['character-' + character['id']] = character['image']['path']
            known.add('character-' + character['id'])
    for ep in story['episodes']:
        start = len(tasks)
        def add(aid, kind, prompt, dependencies=()):
            if aid not in known:
                known.add(aid)
                tasks.append({'id': aid, 'episode_id': ep['id'], 'kind': kind,
                              'prompt': prompt, 'references': list(dependencies),
                              'credits': CREDITS_PER_IMAGE, 'status': 'planned_not_rendered',
                              'requires_pixel_check': True})
        for shot in ep['shots']:
            deps = []
            for cid in shot['visible_characters']:
                c = cast[cid]; aid = 'character-' + cid
                add(aid, 'character', c['description'] + '. ' + c['image'].get('prompt', '') +
                    '. Identity and wardrobe reference, front and side views, consistent proportions.')
                deps.append(aid)
            lid = 'location-' + shot['location']
            spec = shot['location_description']
            if lid in location_specs and location_specs[lid] != spec:
                raise ValueError('Conflicting shared location description: ' + lid)
            location_specs[lid] = spec
            add(lid, 'location', brief['setting'] + '. ' + spec + '. Establish layout, entrances and camera axes.')
            deps.append(lid)
            props = {p['id']: p['description'] for p in shot.get('recurring_props', [])}
            for p in shot['props']:
                if p not in props and p not in props.values():
                    props['item-' + hashlib.sha256(p.encode()).hexdigest()[:12]] = p
            for pid, description in props.items():
                aid = 'prop-' + identifier(pid, 'prop id')
                if aid in prop_specs and prop_specs[aid] != description:
                    raise ValueError('Conflicting prop description: ' + aid)
                prop_specs[aid] = description
                add(aid, 'prop', description + '. Object reference: orientation, scale, front and reverse.')
                deps.append(aid)
            add('frame-' + shot['id'], 'shot_frame', json.dumps({
                'camera': shot['camera'], 'action': shot['action'], 'wardrobe': shot['wardrobe'],
                'props': shot['props'], 'performance': [line.get('performance', '') for line in ep['lines']
                            if line['id'] in shot['line_ids']],
                'instruction': 'Use reference identities, wardrobe, location layout and prop orientation. Show the specified action and expression. Fresh keyframe for a location change; never chain across locations.'
            }, sort_keys=True), deps)
        count = len(tasks) - start
        episodes.append({'episode_id': ep['id'], 'new_images': count, 'planned_credits': count * CREDITS_PER_IMAGE})
    blockers = []
    if exposure is None:
        blockers.append('Current reconciled batch exposure not supplied; quote is planning only')
    else:
        if not isinstance(exposure, dict) or any(type(v) is not int or v < 0 for v in exposure.values()):
            raise ValueError('Exposure must map episode IDs to nonnegative integer credit exposure')
        if any(ep['id'] not in exposure for ep in story['episodes']):
            raise ValueError('Exposure missing an episode; unknown is not zero')
    for ep in episodes:
        if ep['new_images'] > image_cap:
            blockers.append(ep['episode_id'] + ': image cap exceeded; reduce plan, no automatic partial render')
        if exposure is not None and exposure[ep['episode_id']] + ep['planned_credits'] > 3000:
            blockers.append(ep['episode_id'] + ': combined image/video episode cap exceeded')
    total = sum(e['planned_credits'] for e in episodes)
    if exposure is not None and sum(exposure.values()) + total > 30000:
        blockers.append('Combined image/video batch cap exceeded')
    signature = hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest()
    return {'model': MODEL, 'resolution': '1k', 'image_count_per_request': 1,
            'credits_per_image': CREDITS_PER_IMAGE, 'sources': SOURCES,
            'price_checked_on': '2026-10-20', 'recheck_price_before_execution': True,
            'image_cap_per_episode': image_cap, 'episode_credit_cap': 3000, 'batch_credit_cap': 30000,
            'planned_images': len(tasks), 'planned_credits': total, 'episodes': episodes,
            'uploaded_local_references': available, 'tasks': tasks, 'plan_sha256': signature,
            'budget_blockers': blockers, 'live_enabled': False, 'paid_requests': 0,
            'key_policy': 'Yogita image/video key only; never voice or other services',
            'approval_required': 'Exact plan hash, count, credits and current owner approval before key use; model choice alone is not spend approval',
            'execution_policy': 'No auto-retry. Persist reservations including unknown submissions. Reconcile credits_charged before next job. Count replacements toward caps.',
            'video_gate': 'All required reference and shot images must exist, match hashes and pass actual-pixel identity/action/expression/prop-orientation/layout checks before video. No placeholders count as accepted images.',
            'note': '2D reference images, not guaranteed 3D geometry. Planning is not rendering or approval.'}


def submit_image_live(*args, **kwargs):
    raise RuntimeError('Live image generation disabled. Exact count/cost approval and reconciled spend required.')


def require_rendered_images(plan, accepted):
    """Verify local image/check evidence before any video request can consume this plan.

    A boolean record cannot prove visual quality or authenticate its author. The runner
    must actually inspect pixels before recording it; this only binds that result to bytes.
    """
    from pathlib import Path
    from .core import digest
    required = set(plan['uploaded_local_references']) | {a['id'] for a in plan['tasks']}
    checks = ('identity', 'wardrobe', 'action', 'expression', 'prop_orientation', 'layout')
    for aid in sorted(required):
        item = accepted.get(aid, {})
        path = Path(item.get('path', ''))
        if not path.is_file() or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('Required rendered image missing: ' + aid)
        if item.get('sha256') != digest(path) or item.get('plan_sha256') != plan['plan_sha256']:
            raise ValueError('Image or plan changed since pixel check: ' + aid)
        if not item.get('reviewer') or not item.get('reviewed_at') or any(item.get('checks', {}).get(k) is not True for k in checks):
            raise ValueError('Actual-pixel check evidence incomplete: ' + aid)
    return {'status': 'image_evidence_bound_not_quality_certified', 'count': len(required)}
