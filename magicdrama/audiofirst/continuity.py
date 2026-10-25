"""Explicit physical and knowledge state checks, separate from creative judgment."""
import copy

from .core import identifier


def state_fields(state, cast):
    if not isinstance(state, dict) or set(state) != {'characters', 'props', 'knowledge'}:
        raise ValueError('State requires characters, props and knowledge maps')
    flat = {}
    if not isinstance(state['characters'], dict) or set(state['characters']) != cast:
        raise ValueError('State must enumerate the full cast, including offscreen characters')
    for cid, values in state['characters'].items():
        if not isinstance(values, dict) or set(values) != {'position', 'facing', 'wardrobe', 'emotion'}:
            raise ValueError('Character state needs position, facing, wardrobe and emotion')
        for key, value in values.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError('Character state values must be nonempty text')
            flat['characters.' + cid + '.' + key] = value
    if not isinstance(state['props'], dict):
        raise ValueError('Prop state must be a map')
    for pid, values in state['props'].items():
        identifier(pid, 'state prop id')
        if not isinstance(values, dict) or set(values) != {'owner', 'hand', 'status'}:
            raise ValueError('Prop state needs owner, hand and status')
        if values['owner'] not in cast | {'set'} or values['hand'] not in ('left', 'right', 'both', 'none'):
            raise ValueError('Unknown prop owner/hand')
        if values['owner'] == 'set' and values['hand'] != 'none':
            raise ValueError('An unheld prop cannot have a carrying hand')
        if not isinstance(values['status'], str) or not values['status'].strip():
            raise ValueError('Prop status required')
        for key, value in values.items():
            flat['props.' + pid + '.' + key] = value
    if not isinstance(state['knowledge'], dict) or set(state['knowledge']) != cast:
        raise ValueError('Knowledge must enumerate the full cast')
    for cid, facts in state['knowledge'].items():
        if not isinstance(facts, list) or len(facts) != len(set(facts)) or any(not isinstance(f, str) for f in facts):
            raise ValueError('Knowledge requires unique fact IDs')
        flat['knowledge.' + cid] = sorted(facts)
    return flat


def continuity_report(brief, story, initial_state=None):
    if story.get('schema_version', 1) == 1:
        return {'status': 'legacy_unchecked', 'errors': [], 'warnings': ['Legacy story has no explicit continuity contract'], 'final_state': None}
    if story.get('schema_version') != 2:
        raise ValueError('Unsupported story schema version')
    cast = {c['id'] for c in brief['characters']}
    facts = {}
    for fact in story.get('facts', []):
        fid = identifier(fact['id'], 'fact id')
        if fid in facts or not isinstance(fact.get('text'), str) or not fact['text'].strip():
            raise ValueError('Unique facts with text required')
        facts[fid] = fact['text']
    errors, warnings = [], []
    previous, previous_scene = initial_state, None
    for episode in story['episodes']:
        for shot in episode['shots']:
            sid = shot['id']
            scene = identifier(shot['scene_id'], 'scene id')
            scene_key = (scene, shot['location'])
            before = state_fields(shot['start_state'], cast)
            after = state_fields(shot['end_state'], cast)
            if not before.keys() <= after.keys():
                errors.append(sid + ': state entities cannot disappear within a shot')
            if not set(shot['visible_characters']) <= set(shot['start_state']['characters']):
                errors.append(sid + ': visible characters missing from state')
            for state in (shot['start_state'], shot['end_state']):
                if any(not set(ids) <= facts.keys() for ids in state['knowledge'].values()):
                    errors.append(sid + ': unknown knowledge fact')
            if previous is not None:
                previous_cast = set(previous['characters'])
                if not previous_cast <= cast:
                    raise ValueError('Prior canon contains a character missing from the current cast')
                old = state_fields(previous, previous_cast)
                same_scene = scene_key == previous_scene
                for field in old.keys() & before.keys():
                    physical_reset = field.startswith('characters.') and field.rsplit('.', 1)[-1] in ('position', 'facing', 'emotion')
                    if old[field] != before[field] and (same_scene or not physical_reset):
                        errors.append(sid + ': unexplained cut change in ' + field)
                if same_scene and old.keys() != before.keys():
                    errors.append(sid + ': state entity set changed across continuous scene')
                if not same_scene and not shot.get('transition_reason'):
                    errors.append(sid + ': scene change requires transition_reason')
                # Props/known facts persist even when a character is offscreen.
                if set(previous['props']) != set(shot['start_state']['props']):
                    errors.append(sid + ': prop inventory changed across cut')
            declared = {}
            for change in shot.get('changes', []):
                field = change.get('field')
                if not isinstance(field, str) or field in declared or not isinstance(change.get('reason'), str) or not change['reason'].strip():
                    raise ValueError('Unique state changes with visible reasons required')
                declared[field] = change
            actual = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
            if actual != declared.keys():
                errors.append(sid + ': changed state fields must match explicit changes exactly')
            for field in actual & declared.keys():
                change = declared[field]
                old_value,new_value=change.get('from'),change.get('to')
                if field.startswith('knowledge.'):
                    if isinstance(old_value,list):old_value=sorted(old_value)
                    if isinstance(new_value,list):new_value=sorted(new_value)
                if old_value != before.get(field) or new_value != after.get(field):
                    errors.append(sid + ': transition values do not match ' + field)
            gained = set()
            for cid in cast:
                was, now = set(shot['start_state']['knowledge'][cid]), set(shot['end_state']['knowledge'][cid])
                if not was <= now:
                    errors.append(sid + ': knowledge cannot be silently forgotten')
                gained.update((cid, fid) for fid in now - was)
            justified = set()
            for reveal in shot.get('reveals', []):
                if reveal.get('line_id') not in shot['line_ids'] or reveal.get('fact_id') not in facts or not set(reveal.get('learned_by', [])) <= cast:
                    errors.append(sid + ': reveal needs a source line, known fact and cast listeners')
                justified.update((cid, reveal.get('fact_id')) for cid in reveal.get('learned_by', []))
            if gained != justified:
                errors.append(sid + ': new knowledge must match sourced reveals')
            if not shot.get('narrative_purpose'):
                errors.append(sid + ': narrative purpose required')
            previous, previous_scene = copy.deepcopy(shot['end_state']), scene_key
    return {'status': 'rejected' if errors else 'contract_checked_not_semantic_proof', 'errors': errors,
            'warnings': warnings, 'final_state': previous, 'facts': facts}


def require_continuity(brief, story, initial_state=None):
    report = continuity_report(brief, story, initial_state)
    if report['errors']:
        raise ValueError('Continuity rejected: ' + '; '.join(report['errors']))
    return report
