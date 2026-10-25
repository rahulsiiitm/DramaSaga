"""Versioned story structure checks; semantic quality remains a separate review."""
from .core import finite, identifier, validate_brief


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ' must be nonempty text')


def timing_notes(episode):
    words=sum(len(line['text'].split()) for line in episode['lines'])
    return {'episode_id':episode['id'],'spoken_words':words,'rough_speech_seconds_range':[round(words/3.5,2),round(words/1.7,2)],
            'declared_draft_seconds':episode['draft_seconds'],'status':'rough_English_speech_heuristic_not_measured_timing',
            'note':'Evaluate action and silence explicitly when declared runtime greatly exceeds dialogue. Measure real audio before rendering.'}


def validate_episode(brief, episode, line_ids=None, shot_ids=None):
    cast = {c['id'] for c in brief['characters']}
    line_ids = line_ids if line_ids is not None else set()
    shot_ids = shot_ids if shot_ids is not None else set()
    identifier(episode['id'], 'episode id')
    seconds = finite(episode['draft_seconds'], 'draft_seconds', 0.01)
    if seconds > brief.get('max_episode_seconds', 180):
        raise ValueError('Episode exceeds requested maximum')
    for key in ('title', 'setup', 'turn', 'cliffhanger'):
        text(episode.get(key), key)
    if not isinstance(episode.get('lines'), list) or not episode['lines'] or not isinstance(episode.get('shots'), list) or not episode['shots']:
        raise ValueError('Episode requires shots and lines')
    ordered, speakers = [], {}
    for line in episode['lines']:
        lid = identifier(line['id'], 'line id')
        if lid in line_ids or line['speaker'] not in cast | {'narrator'}:
            raise ValueError('Duplicate line id or unknown speaker')
        line_ids.add(lid)
        ordered.append(lid)
        speakers[lid] = line['speaker']
        text(line.get('text'), 'Line text')
        text(line.get('performance'), 'Line performance')
    covered = []
    for shot in episode['shots']:
        sid = identifier(shot['id'], 'shot id')
        if sid in shot_ids:
            raise ValueError('Shot ids must be unique across the season')
        shot_ids.add(sid)
        identifier(shot['location'], 'location id')
        visible = shot['visible_characters']
        if not isinstance(visible, list) or not set(visible) <= cast or len(visible) != len(set(visible)):
            raise ValueError('Invalid visible characters')
        for key in ('location_description', 'camera', 'action', 'wardrobe'):
            text(shot.get(key), key)
        if not isinstance(shot.get('props'), list) or any(not isinstance(p, str) or not p.strip() for p in shot['props']):
            raise ValueError('Props must be a list, which may be empty')
        if not isinstance(shot.get('line_ids'), list) or any(lid not in speakers for lid in shot['line_ids']):
            raise ValueError('Shot references unknown lines')
        offscreen = shot.get('offscreen_speakers', [])
        if not isinstance(offscreen, list) or not set(offscreen) <= cast:
            raise ValueError('Unknown offscreen speaker')
        faces=shot.get('speaking_faces',visible)
        if not isinstance(faces,list) or not set(faces)<=set(visible):
            raise ValueError('Speaking faces must be a subset of visible characters')
        if shot.get('start_state') is not None:
            if any(speakers[lid] not in set(visible) | set(offscreen) | {'narrator'} for lid in shot['line_ids']):
                raise ValueError('Speaking character must be visible or explicitly offscreen')
        covered.extend(shot['line_ids'])
    if covered != ordered:
        raise ValueError('Shot line coverage must match ordered episode lines exactly')
    return seconds


def validate_story(brief, story):
    from .continuity import require_continuity
    validate_brief(brief)
    if story.get('series_id') != brief['series_id'] or story.get('season') != brief['season']:
        raise ValueError('Story identity does not match brief')
    if story.get('schema_version', 1) not in (1, 2):
        raise ValueError('Unsupported story schema version')
    episodes = story['episodes']
    if not isinstance(episodes, list) or len(episodes) != brief['episodes_per_season']:
        raise ValueError('Wrong episode count')
    episode_ids, line_ids, shot_ids = set(), set(), set()
    total = 0
    for episode in episodes:
        if episode['id'] in episode_ids:
            raise ValueError('Duplicate episode id')
        episode_ids.add(episode['id'])
        total += validate_episode(brief, episode, line_ids, shot_ids)
    target = brief.get('target_season_seconds', min(900, brief['episodes_per_season'] * brief.get('max_episode_seconds', 180)))
    if abs(total - target) > max(1, target * 0.05):
        raise ValueError('Draft total must be within 5 percent of requested season runtime')
    continuity = require_continuity(brief, story)
    return {'valid': True, 'draft_seconds': total, 'timing_status': 'estimated_until_accepted_audio',
            'continuity': continuity, 'note': 'Contract validation does not certify dialogue quality or visible continuity.'}
