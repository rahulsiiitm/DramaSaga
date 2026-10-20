"""Continuous tagged dialogue payloads. No synthesis or key reads."""
from .pipeline import voice_plan

AMELIA = 'ZF6FPAbjXT4488VcRRnw'
PETER = '4dZr8J4CBeokyRkTRpoN'
TAGS = {'angry': '[angry]', 'whisper': '[whispers]', 'sad': '[sad]',
        'suspicion': '[curious]', 'nervous': '[nervous]', 'excited': '[excited]',
        'quiet': '[softly]', 'laugh': '[laughs]', 'sigh': '[sighs]'}


def dialogue_plan(brief, story, selections=None):
    from .story import validate_story
    validate_story(brief, story)
    selections = selections or {}
    if not isinstance(selections, dict) or any(not isinstance(v, str) or not v.strip() for v in selections.values()):
        raise ValueError('Voice selections must map speaker IDs to nonempty catalog voice IDs')
    # These defaults belong to these explicitly selected named roles, not inferred genders.
    cast = {}
    traits = {x['character_id']: x for x in voice_plan(brief['characters'])}
    for c in brief['characters']:
        name = c['name'].casefold().strip()
        default = AMELIA if name in ('clara', 'clara bennett') else PETER if name in ('oliver', 'oliver reed') else None
        cast[c['id']] = {'voice_id': selections.get(c['id'], default), 'trait_profile': traits[c['id']],
                         'status': 'selected_catalog_preview_not_episode_tested' if selections.get(c['id'], default) else 'needs_catalog_selection'}
    episodes = []
    for ep in story['episodes']:
        inputs = []; missing = set(); spoken = 0
        for line in ep['lines']:
            voice = selections.get(line['speaker']) or cast.get(line['speaker'], {}).get('voice_id')
            if not voice: missing.add(line['speaker'])
            direction = line['performance'].casefold()
            tags = list(dict.fromkeys(tag for word, tag in TAGS.items() if word in direction))[:2]
            text = (' '.join(tags) + ' ' if tags else '') + line['text']
            inputs.append({'text': text, 'voice_id': voice})
            spoken += len(line['text'])
        episodes.append({'episode_id': ep['id'], 'spoken_characters': spoken,
                         'submitted_characters': sum(len(x['text']) for x in inputs),
                         'missing_voice_selections': sorted(missing),
                         'request': {'endpoint': '/v1/text-to-dialogue/with-timestamps',
                                     'body': {'model_id': 'eleven_v3', 'inputs': inputs}},
                         'timing_rule': 'Reject timestamps not supported by actual WAV; local word timing/onset checks before captions',
                         'live_enabled': False})
    return {'cast': cast, 'episodes': episodes, 'paid_requests': 0,
            'license_and_model_access': 'Recheck provider catalog, permission and surcharge before execution',
            'key_policy': 'ElevenLabs only with exact tagged-character approval; never Yogita image/video key',
            'emotion_note': 'Performance tags are instructions, not proof of emotional acting',
            'live_enabled': False}


def submit_voice_live(*args, **kwargs):
    raise RuntimeError('Live voice generation disabled; exact count approval required')
