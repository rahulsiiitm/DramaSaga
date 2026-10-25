from pathlib import Path

from .core import digest, identifier, validate_brief


def reference_plan(brief, episodes):
    validate_brief(brief)
    if len(episodes) != brief['episodes_per_season']:
        raise ValueError('Episode count must match brief')
    cast = {c['id']: c for c in brief['characters']}
    assets = []
    environment_sources = {e['id']: e for e in brief.get('environments', [])}
    for cid, character in cast.items():
        assets.append({'id': 'character-' + cid, 'kind': 'character', 'identity': cid,
                       'source': character['image'], 'required_review': ['identity', 'wardrobe', 'style'],
                       'status': 'requires_reference_or_generation'})
    locations = {}
    shot_ids = set()
    for episode in episodes:
        identifier(episode['id'], 'episode id')
        for shot in episode['shots']:
            sid = identifier(shot['id'], 'shot id')
            if sid in shot_ids:
                raise ValueError('Shot ids must be unique across the season')
            shot_ids.add(sid)
            for cid in shot['visible_characters']:
                if cid not in cast:
                    raise ValueError('Unknown visible character')
            location = shot['location']
            identifier(location, 'location id')
            if location not in locations:
                locations[location] = {'id': 'location-' + location, 'kind': 'location',
                                       'setting': brief['setting'], 'description': shot['location_description'],
                                       'required_review': ['layout', 'style', 'era', 'camera_axes']}
                if location in environment_sources and environment_sources[location].get('image'):
                    locations[location]['source'] = environment_sources[location]['image']
            elif locations[location]['description'] != shot['location_description']:
                raise ValueError('Conflicting shared location description: ' + location)
            refs = ['location-' + location] + ['character-' + cid for cid in shot['visible_characters']]
            for prop in shot.get('recurring_props', []):
                pid = identifier(prop['id'], 'prop id')
                if not any(a['id'] == 'prop-' + pid for a in assets):
                    assets.append({'id': 'prop-' + pid, 'kind': 'prop', 'description': prop['description'],
                                   'required_review': ['identity', 'orientation', 'scale']})
                refs.append('prop-' + pid)
            assets.append({'id': 'frame-' + sid, 'kind': 'shot_frame', 'shot': sid,
                           'references': refs, 'camera': shot['camera'], 'action': shot['action'],
                           'wardrobe': shot['wardrobe'], 'required_review': ['faces', 'wardrobe', 'props', 'action', 'expression', 'composition']})
            if 'start_state' in shot:
                assets[-1].update({'start_state': shot['start_state'], 'end_state': shot['end_state'],
                                   'narrative_purpose': shot['narrative_purpose']})
    return {'assets': assets + list(locations.values()), 'paid_requests': 0,
            'note': 'This is a per-shot reference plan, not generated or approved images.'}


def threejs_request(asset_id, reference, subject, output_dir):
    identifier(asset_id, 'asset id')
    if subject not in ('prop', 'location', 'character'):
        raise ValueError('3D subject must be prop, location or character')
    path = Path(reference)
    if not path.is_file() or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
        raise ValueError('3D request needs a local reference image')
    data = path.read_bytes()[:16]
    if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff') or (data[:4] == b'RIFF' and data[8:12] == b'WEBP')):
        raise ValueError('Reference is not a recognized image container')
    return {'asset_id': asset_id, 'route': 'procedural_threejs', 'reference_path': str(path.resolve()),
            'reference_sha256': digest(path), 'subject': subject, 'output_dir': str(Path(output_dir).resolve()),
            'upstream': 'https://github.com/img2threejs/img2threejs',
            'stages': ['assess_reference', 'detail_inventory', 'component_spec', 'blockout', 'geometry_checks',
                       'render', 'side_by_side_review', 'materials', 'rig_if_needed', 'export'],
            'acceptance': {'requires_pixel_review': True, 'requires_multi_angle_review': True,
                           'hidden_geometry_is_inferred': True, 'human_likeness_guaranteed': False},
            'status': 'handoff_only_not_reconstructed', 'paid_requests': 0,
            'warning': 'Code-authored geometry workflow, not a mesh-reconstruction model. No external code or agent is executed.'}
