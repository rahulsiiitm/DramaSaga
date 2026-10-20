from .core import finite, identifier, validate_brief


def validate_story(brief, story):
    validate_brief(brief)
    if story.get('series_id') != brief['series_id'] or story.get('season') != brief['season']:
        raise ValueError('Story identity does not match brief')
    episodes = story['episodes']
    if len(episodes) != brief['episodes_per_season']:
        raise ValueError('Wrong episode count')
    cast = {c['id'] for c in brief['characters']}
    episode_ids = set()
    line_ids = set()
    total = 0
    for episode in episodes:
        eid = identifier(episode['id'], 'episode id')
        if eid in episode_ids:
            raise ValueError('Duplicate episode id')
        episode_ids.add(eid)
        seconds = finite(episode['draft_seconds'], 'draft_seconds', 0.01)
        if seconds > brief.get('max_episode_seconds', 180):
            raise ValueError('Episode exceeds requested maximum')
        total += seconds
        if not all(episode.get(k) for k in ('title', 'setup', 'turn', 'cliffhanger', 'shots', 'lines')):
            raise ValueError('Episode requires story beats, shots and lines')
        local_lines = []
        for line in episode['lines']:
            lid = identifier(line['id'], 'line id')
            if lid in line_ids or line['speaker'] not in cast | {'narrator'}:
                raise ValueError('Duplicate line id or unknown speaker')
            line_ids.add(lid); local_lines.append(lid)
            if not line.get('text') or not line.get('performance'):
                raise ValueError('Line text and performance direction required')
        covered = []
        for shot in episode['shots']:
            identifier(shot['id'], 'shot id')
            if not set(shot['visible_characters']) <= cast:
                raise ValueError('Unknown visible character')
            if not all(shot.get(k) for k in ('location', 'location_description', 'camera', 'action', 'wardrobe', 'props')):
                raise ValueError('Missing shot specification')
            covered.extend(shot['line_ids'])
        if covered != local_lines:
            raise ValueError('Shot line coverage must match ordered episode lines exactly')
    target = brief.get('target_season_seconds', 900)
    if abs(total - target) > max(1, target * 0.05):
        raise ValueError('Draft total must be within 5 percent of requested season runtime')
    return {'valid': True, 'draft_seconds': total, 'timing_status': 'estimated_until_accepted_audio',
            'note': 'Structure validation does not certify dialogue quality or continuity.'}
