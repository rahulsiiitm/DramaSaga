"""Offline flow planner. Does not synthesize media or call credentials/providers."""
from .core import validate_brief
from .planning import reference_plan
from .story import validate_story
from .images import image_first_plan


def voice_plan(characters):
    result = []
    for char in characters:
        traits = char['description'].lower()
        # Delivery traits, never infer gender, accent or ethnicity from a name.
        qualities = []
        for words, value in [(('calm', 'patient', 'quiet'), 'calm measured delivery'),
                             (('bold', 'confident', 'assertive'), 'clear confident delivery'),
                             (('shy', 'nervous', 'anxious'), 'soft hesitant delivery'),
                             (('energetic', 'playful', 'funny'), 'lively conversational delivery')]:
            if any(word in traits for word in words): qualities.append(value)
        result.append({'character_id': char['id'], 'language': 'English',
                       'delivery': qualities or ['natural conversational delivery'],
                       'provider_voice_id': None, 'status': 'trait_profile_only_voice_catalog_not_connected',
                       'selection_rule': 'Match a licensed English provider voice to these traits when keys are authorized; do not clone an unconsenting person.'})
    return result


def soundtrack_plan(episodes):
    return [{'episode_id': ep['id'], 'shot_id': shot['id'], 'action_context': shot['action'],
             'music': {'brief': 'Low unobtrusive instrumental bed fitting the scene; keep dialogue intelligible',
                       'asset_path': None, 'status': 'no_licensed_asset_selected'},
             'sfx': {'brief': 'Only sounds justified by visible action/props', 'props': shot['props'],
                     'asset_path': None, 'status': 'no_licensed_asset_selected'}}
            for ep in episodes for shot in ep['shots']]


def offline_flow(brief, story):
    validate_brief(brief); validate_story(brief, story)
    if not brief['language'].lower().startswith('en'):
        raise ValueError('This pipeline configuration is English only')
    references = reference_plan(brief, story['episodes'])
    for asset in references['assets']:
        asset['render_requirements'] = {'consistent_identity': True, 'multi_angle_if_character_or_prop':
                                        asset['kind'] in ('character', 'prop'),
                                        'geometry_guaranteed': False}
    return {'mode': 'offline_no_keys_no_spend', 'automatic_continuation': True,
            'human_stage_stops': False, 'paid_requests': 0,
            'completed': ['brief_validation', 'story_structure_validation', 'reference_plan', 'voice_profiles', 'soundtrack_cues'],
            'references': references, 'image_first': image_first_plan(brief, story), 'voices': voice_plan(brief['characters']),
            'soundtrack': soundtrack_plan(story['episodes']),
            'subtitle_policy': {'text': 'exact_spoken_English', 'white_dark_outline': True,
                                'position': 'bottom_center', 'max_lines': 2,
                                'speaker_name_bars': True, 'introduction_bars': True},
            'episode_policy': {'max_seconds': 180, 'minimum_seconds': None,
                               'short_episodes_allowed': True},
            'execution_order': ['write_story', 'reference_images', 'voice_audio', 'measure_audio', 'timeline',
                                'soundtrack_assets', 'picture_shots', 'master_edit', 'subtitles', 'name_bars', 'season_zip'],
            'blocked': [{'stage': stage, 'reason': reason} for stage, reason in [
                ('reference_images', 'No image synthesis executed; API/keys disabled'),
                ('voice_audio', 'No voice synthesis executed; API/keys disabled'),
                ('picture_shots', 'No video/GPU execution; API/keys and spend disabled; H3 license clearance pending'),
                ('soundtrack_assets', 'No track selected/downloaded; each license and content must be verified'),
                ('true_3d', 'Reference-render planning only; no reconstruction/rigging engine implemented')]],
            'note': 'Automatic planning can continue without human stops. Missing real media remains blocked, never replaced by placeholders presented as output.'}


def validate_free_audio_asset(asset):
    """Validate recorded evidence only. This cannot authenticate a claimed license."""
    from pathlib import Path
    from urllib.parse import urlparse
    from .core import digest
    if asset.get('license') not in ('CC0-1.0', 'CC-BY-4.0', 'YouTube-Audio-Library'):
        raise ValueError('No approved free commercial license evidence')
    for key in ('source_url', 'license_url'):
        parsed = urlparse(asset.get(key, ''))
        if parsed.scheme != 'https' or not parsed.netloc:
            raise ValueError('Source and license HTTPS URLs required')
    for key in ('creator', 'title', 'license_checked_at', 'license_terms_path'):
        if not asset.get(key): raise ValueError('Missing asset provenance: ' + key)
    for field, hash_field in [('path', 'sha256'), ('license_terms_path', 'license_terms_sha256')]:
        path = Path(asset[field])
        if not path.is_file() or digest(path) != asset.get(hash_field):
            raise ValueError('Asset or license evidence absent/changed')
    if asset.get('commercial_use_verified') is not True or asset.get('sync_use_verified') is not True:
        raise ValueError('Commercial/synchronization use not verified')
    if asset['license'] != 'CC0-1.0' and not asset.get('attribution'):
        raise ValueError('Attribution required by conservative policy')
    return {'status': 'recorded_evidence_valid_not_legal_certification', 'asset': asset,
            'note': 'Epidemic Sound and arbitrary YouTube uploads are not presumed free.'}
