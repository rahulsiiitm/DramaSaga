"""One-command offline orchestration. Honest blocked states, no automatic paid fallback."""
from pathlib import Path
from .core import validate_brief, writing_request, write_json
from .story import validate_story
from .season import inspect_season_zip
from .pipeline import offline_flow, validate_free_audio_asset
from .voices import dialogue_plan


def run(brief, output, story=None, previous_zip=None, writer=None, voices=None, exposure=None, image_cap=12, soundtrack=None):
    from .images import image_first_plan
    validate_brief(brief)
    root = Path(output)
    if root.exists() and any(root.iterdir()):
        raise ValueError('Use a fresh output directory; prior run cannot be silently overwritten')
    previous = inspect_season_zip(previous_zip) if previous_zip else None
    request = writing_request(brief, previous)
    # Inject a separately authorized writer in library use. No subprocess, API or auto-fallback.
    if story is None and writer is not None:
        story = writer(request)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / 'brief.json', brief)
    write_json(root / 'writing-request.json', request)
    if previous:
        write_json(root / 'previous-canon.json', previous['canon'])
    result = {'mode': 'offline', 'paid_requests': 0, 'live_enabled': False,
              'completed': ['brief_validation', 'continuation_validation', 'writing_request'], 'blocked': []}
    if story is None:
        result['blocked'].append({'stage': 'writing', 'reason': 'No story or authorized writer supplied. Writing request created, not a generated season.'})
    else:
        validate_story(brief, story)
        write_json(root / 'story.json', story)
        flow = offline_flow(brief, story)
        flow['image_first'] = image_first_plan(brief, story, image_cap, exposure)
        write_json(root / 'flow.json', flow)
        vp = dialogue_plan(brief, story, voices)
        write_json(root / 'voice-requests.json', vp)
        for asset in soundtrack or []:
            validate_free_audio_asset(asset)
        write_json(root / 'soundtrack-evidence.json', soundtrack or [])
        result['completed'] += ['story_structure_validation', 'image_first_plan', 'tagged_dialogue_plan', 'music_sfx_cues', 'subtitle_policy']
        result['image_count'] = flow['image_first']['planned_images']
        result['image_credits'] = flow['image_first']['planned_credits']
        result['voice_tagged_characters'] = sum(x['submitted_characters'] for x in vp['episodes'])
        result['blocked'] += flow['blocked']
        result['blocked'].append({'stage': 'final_season_video', 'reason': 'No synthesized images/audio/video. No movie, final subtitles or finished-season ZIP claimed.'})
    write_json(root / 'run.json', result)
    return result


def write_draft(brief, previous=None):
    """Local deterministic story draft for UI smoke tests, NOT a creative model writer.

    Kept opt-in and visibly labeled. Produces structurally valid multi-turn episodes,
    without claiming plot quality, new canon, measured runtime, or finished production.
    """
    writing_request(brief, previous)
    cast = brief['characters']; a = cast[0]['id']; b = cast[min(1, len(cast)-1)]['id']
    target = brief.get('target_season_seconds', 900) / brief['episodes_per_season']
    beats = [('A folded note', 'The note names a place nobody mentioned.', 'We go together, or we do not go.'),
             ('An open door', 'Someone arrived before us.', 'Then we stop pretending this is chance.'),
             ('The missing page', 'This page was torn out after I read it.', 'What did you leave out when you told me?'),
             ('A second copy', 'There are two copies, and only one signature.', 'One of us has been protecting the wrong person.'),
             ('A familiar mark', 'I have seen this mark on your desk.', 'I kept it because I was afraid you would ask.'),
             ('The wrong time', 'The time on the note cannot be right.', 'Unless it was meant to send us away.'),
             ('A quiet bargain', 'They offered to make the debt disappear.', 'And what did they want you to forget?'),
             ('The unopened letter', 'I knew the handwriting before I opened it.', 'You could have trusted me with that.'),
             ('A changed plan', 'There is still time to leave this here.', 'I am staying. This time you get a choice.'),
             ('The last name', 'There is another name beneath the signature.', 'Read it to me. No more secrets.')]
    episodes = []
    for n in range(brief['episodes_per_season']):
        title, one, two = beats[n % len(beats)]; eid = 'ep' + str(n+1)
        lines = [{'id': eid + 'a', 'speaker': a, 'text': one, 'performance': 'quiet suspicion'},
                 {'id': eid + 'b', 'speaker': b, 'text': two, 'performance': 'nervous, held back'},
                 {'id': eid + 'c', 'speaker': a, 'text': 'Then look at me when you tell me what happens next.', 'performance': 'quiet, firm'}]
        episodes.append({'id': eid, 'title': title, 'draft_seconds': target,
                         'setup': title, 'turn': one, 'cliffhanger': two, 'lines': lines,
                         'shots': [{'id': eid + 'shot', 'line_ids': [x['id'] for x in lines],
                                    'location': 'main_room', 'location_description': brief['setting'],
                                    'visible_characters': list(dict.fromkeys([a,b])), 'camera': 'medium two-shot' if a != b else 'medium',
                                    'action': 'One adult turns a folded note toward the other' if a != b else 'Reads the folded note aloud',
                                    'wardrobe': 'Keep the selected character reference wardrobe', 'props': ['folded note']}]})
    result = {'series_id': brief['series_id'], 'season': brief['season'], 'episodes': episodes,
              'writer_status': 'LOCAL_TEMPLATE_DRAFT_NOT_MODEL_WRITTEN',
              'limitations': ['Repeated structure; needs creative rewrite', 'Runtime targets are not speech-duration estimates',
                              'Previous canon retained in writing request only, not semantically incorporated',
                              'Additional cast not guaranteed meaningful dialogue']}
    validate_story(brief, result)
    return result
