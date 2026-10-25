"""Synthetic fixtures. None of these receipts certify real creative media."""
import copy
import json
import math
import struct
import wave
from pathlib import Path

from magicdrama.audiofirst.core import digest
from magicdrama.audiofirst.execution import signature
from magicdrama.audiofirst.renderplan import measured_track

ROOT = Path(__file__).resolve().parents[1]


def pilot():
    root = ROOT / 'examples' / 'pilot'
    return (json.loads((root / 'brief.json').read_text(encoding='utf-8')),
            json.loads((root / 'story.json').read_text(encoding='utf-8')))


def outline(story):
    return {'premise': 'A concealed opportunity', 'central_conflict': 'Trust versus fear', 'ending': 'The choice is returned',
            'facts': copy.deepcopy(story['facts']), 'episodes': [
                {**{k: ep[k] for k in ('id', 'draft_seconds', 'setup', 'turn', 'cliffhanger')},
                 'beats': [{'id': s['beat_id'], 'cause': s['action'], 'consequence': s['narrative_purpose']} for s in ep['shots']]}
                for ep in story['episodes']]}


def approval():
    from magicdrama.audiofirst.director import DIMENSIONS
    return {'approved': True, 'dimensions': {d: True for d in DIMENSIONS}, 'issues': []}


def audio_fixture(root, episode):
    episode = copy.deepcopy(episode)
    for line in episode['lines']:
        line['text'] = 'Wait.'
    path = Path(root) / 'synthetic.wav'
    seconds = len(episode['lines']) * .5
    rate = 16000
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
        wav.writeframes(b''.join(struct.pack('<h', round(2000 * math.sin(2 * math.pi * 220 * i / rate))) for i in range(round(rate * seconds))))
    asset = {'path': str(path), 'sha256': digest(path)}
    cues = [{'line_id': line['id'], 'speaker': line['speaker'], 'text': line['text'], 'start': i * .5,
             'end': (i + 1) * .5, 'actual_audio_checked': True} for i, line in enumerate(episode['lines'])]
    review = {'sha256': asset['sha256'], 'lines_sha256': signature(episode['lines']),
              'words': True, 'speakers': True, 'emotion': True, 'pronunciation': True, 'fixture': 'synthetic_not_human_review'}
    alignment = {'audio_sha256': asset['sha256'], 'cues': cues}
    return episode, measured_track(episode, asset, alignment, review)


def profile(**overrides):
    return {'id': 'test_renderer', 'provider': 'magichour', 'model': 'magichour-audio-to-video',
            'modes': ['audio_to_video', 'image_to_video'], 'min_seconds': .1, 'max_seconds': 15,
            'exact_audio': True, 'multi_shot': False, 'max_speakers': 1, 'end_frame': False, **overrides}


def reference_images(root,episode):
    from PIL import Image
    result={}
    for index,shot in enumerate(episode['shots']):
        path=Path(root)/(shot['id']+'.png')
        Image.new('RGB',(144,256),(30+index*20,80,110)).save(path)
        result['frame-'+shot['id']]={'path':str(path.resolve()),'sha256':digest(path)}
    return result
