"""Local storyboard player and optional still animatic. Never production acceptance."""
import json
import math
import shutil
import subprocess
from pathlib import Path

from .core import digest, write_json
from .renderplan import cut_plan
from .story import validate_story


def _copy(asset, root):
    source = Path(asset['path'])
    if not source.is_file() or digest(source) != asset['sha256']:
        raise ValueError('Preview asset missing/changed: ' + str(source))
    suffix = source.suffix.lower()
    if suffix not in ('.png', '.jpg', '.jpeg', '.webp', '.wav'):
        raise ValueError('Preview supports local images and WAV audio only')
    destination = root / 'media' / (asset['sha256'] + suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copyfile(source, destination)
    elif digest(destination) != asset['sha256']:
        raise ValueError('Preview copy changed')
    return destination.relative_to(root).as_posix()


def storyboard_preview(brief, story, output, assets=None, tracks=None):
    validate_story(brief, story)
    root = Path(output)
    if root.exists() and any(root.iterdir()):
        raise ValueError('Use a fresh storyboard preview directory')
    root.mkdir(parents=True, exist_ok=True)
    assets, tracks = assets or {}, tracks or {}
    episodes = []
    for episode in story['episodes']:
        track = tracks.get(episode['id'])
        if track:
            cuts = cut_plan(episode, track)
            audio = _copy(track['audio'], root)
            duration = track['seconds']
        else:
            duration, cursor, cuts, audio = episode['draft_seconds'], 0, [], None
            words = {l['id']: max(1, len(l['text'].split())) for l in episode['lines']}
            weights = [max(1, sum(words[lid] for lid in s['line_ids'])) for s in episode['shots']]
            total_frames = max(len(weights), math.ceil(duration * 24))
            remaining = total_frames - len(weights)
            for index, (shot, weight) in enumerate(zip(episode['shots'], weights)):
                count = 1 + math.floor(remaining * weight / sum(weights))
                end = total_frames if index == len(weights) - 1 else cursor + count
                cuts.append({**shot, 'start_frame': cursor, 'end_frame': end})
                cursor = end
        lines = {l['id']: l for l in episode['lines']}
        shots = []
        for cut in cuts:
            asset = assets.get('frame-' + cut['id'])
            shots.append({'id': cut['id'], 'start': cut['start_frame'] / 24, 'end': cut['end_frame'] / 24,
                          'image': _copy(asset, root) if asset else None, 'camera': cut['camera'], 'action': cut['action'],
                          'purpose': cut.get('narrative_purpose', 'Legacy story: purpose unspecified'),
                          'lines': [lines[lid] for lid in cut['line_ids']], 'start_state': cut.get('start_state'), 'end_state': cut.get('end_state')})
        episodes.append({'id': episode['id'], 'title': episode['title'], 'duration': duration, 'audio': audio,
                         'timing': 'measured' if track else 'ESTIMATED — no audio timing approval', 'shots': shots})
    data = {'series_id': brief['series_id'], 'episodes': episodes, 'status': 'storyboard_preview_not_generated_video', 'paid_requests': 0}
    write_json(root / 'storyboard.json', data)
    encoded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = Path(__file__).with_name('storyboard.html').read_text(encoding='utf-8')
    (root / 'index.html').write_text(template.replace('/*STORY_DATA*/', encoded), encoding='utf-8')
    return {'path': str((root / 'index.html').resolve()), 'episodes': len(episodes), 'status': data['status'], 'paid_requests': 0}


def render_animatic(episode, track, assets, output, ffmpeg='ffmpeg'):
    """Render approved-timing stills with continuous audio; no pixel approval implied."""
    cuts = cut_plan(episode, track)
    output = Path(output)
    if output.exists():
        raise ValueError('Use a fresh animatic output directory')
    # Validate all inputs before starting any local encoding.
    sources = []
    for cut in cuts:
        asset = assets.get('frame-' + cut['id'], {})
        path = Path(asset.get('path', ''))
        if not path.is_file() or digest(path) != asset.get('sha256') or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('Every animatic shot needs a hash-bound image: ' + cut['id'])
        sources.append(path.resolve())
    output.mkdir(parents=True)
    for index, (cut, source) in enumerate(zip(cuts, sources)):
        subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-loop', '1', '-i', str(source), '-vf',
            'scale=540:960:force_original_aspect_ratio=decrease,pad=540:960:(ow-iw)/2:(oh-ih)/2,fps=24,setsar=1',
            '-frames:v', str(cut['frames']), '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(output / f'shot-{index:04}.mp4')], check=True, capture_output=True)
    (output / 'concat.txt').write_text(''.join(f"file 'shot-{i:04}.mp4'\n" for i in range(len(cuts))), encoding='utf-8')
    destination = output / 'animatic.mp4'
    subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-f', 'concat', '-safe', '1', '-i', str(output / 'concat.txt'),
                    '-i', str(Path(track['audio']['path']).resolve()), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac',
                    '-t', str(track['seconds']), str(destination)], check=True, capture_output=True)
    result = {'path': str(destination.resolve()), 'sha256': digest(destination), 'status': 'still_animatic_not_generated_acting',
              'audio_sha256': track['audio']['sha256'], 'frames': track['frames'], 'paid_requests': 0}
    write_json(output / 'animatic.json', result)
    return result
