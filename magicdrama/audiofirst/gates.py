"""Local review evidence, not authorization to spend or publish."""
import datetime
import hashlib
import json
from pathlib import Path
from .core import digest

STAGES = ('story', 'assets', 'audio', 'timing', 'picture', 'subtitles', 'final')
CHECKS = {
    'story': ('english_text', 'continuity', 'runtime_plan'),
    'assets': ('identity', 'wardrobe', 'locations', 'props', 'rights'),
    'audio': ('words', 'speaker', 'emotion', 'pronunciation'),
    'timing': ('measured_audio', 'shot_coverage', 'episode_limit'),
    'picture': ('full_playback', 'identity', 'action', 'props', 'lip_sync'),
    'subtitles': ('exact_text', 'timing', 'readability', 'safe_margins'),
    'final': ('full_playback', 'master_audio', 'continuity', 'subtitle_editions'),
}

def object_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def require_stage(bundle, stage):
    """Check the entire review chain through stage, including current artifact bytes."""
    if stage not in STAGES:
        raise ValueError('Unknown review stage')
    previous = None
    for name in STAGES[:STAGES.index(stage) + 1]:
        receipt = bundle.get(name, {})
        if receipt.get('stage') != name or receipt.get('previous_receipt_sha256') != previous:
            raise ValueError('Missing or stale predecessor: ' + name)
        if not isinstance(receipt.get('reviewer'), str) or not receipt['reviewer'].strip() or not receipt.get('reviewed_at'):
            raise ValueError('Named human reviewer and timestamp required: ' + name)
        try:
            reviewed = datetime.datetime.fromisoformat(receipt['reviewed_at'].replace('Z', '+00:00'))
            if reviewed.tzinfo is None:
                raise ValueError('Review timestamp requires timezone')
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError('Invalid review timestamp: ' + name) from error
        artifacts = receipt.get('artifacts')
        if not isinstance(artifacts, dict) or not artifacts:
            raise ValueError('Reviewed artifact hashes required: ' + name)
        for path, sha in artifacts.items():
            if not Path(path).is_file() or digest(path) != sha:
                raise ValueError('Reviewed artifact absent or changed: ' + path)
        if any(receipt.get('checks', {}).get(check) is not True for check in CHECKS[name]):
            raise ValueError('Human review incomplete: ' + name)
        previous = object_hash(receipt)
    return {'stage': stage, 'receipt_sha256': previous, 'status': 'local_review_checked',
            'authority': 'Does not authorize paid calls, publication or sharing.'}


def require_inputs(bundle, stage, paths):
    result = require_stage(bundle, stage)
    artifacts = {str(Path(p).resolve()): h for p, h in bundle[stage]['artifacts'].items()}
    for path in paths:
        p = str(Path(path).resolve())
        if artifacts.get(p) != digest(path):
            raise ValueError('Current input is not bound to the required stage review: ' + p)
    return result
