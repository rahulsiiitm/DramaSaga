from pathlib import Path
import subprocess

from .core import digest, finite, write_json, validate_timeline


def build_master(track, output):
    validate_timeline(track)
    output = Path(output)
    if output.exists():
        raise ValueError('Refusing to overwrite master')
    output.parent.mkdir(parents=True, exist_ok=True)
    args = ['ffmpeg', '-v', 'error', '-y']
    filters = []
    labels = []
    for index, line in enumerate(track['lines']):
        source = Path(line['audio_path'])
        if digest(source) != line['sha256']:
            raise ValueError('Accepted audio changed')
        args.extend(['-i', str(source)])
        delay = round(line['start_frame'] / track['fps'] * 1000)
        label = f'a{index}'
        filters.append(f'[{index}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={delay}:all=1[{label}]')
        labels.append(f'[{label}]')
    filters.append(''.join(labels) + f'amix=inputs={len(labels)}:normalize=0,apad,atrim=duration={track["seconds"]}[out]')
    temporary = output.with_name(output.stem + '.pending.wav')
    try:
        subprocess.run(args + ['-filter_complex', ';'.join(filters), '-map', '[out]', '-c:a', 'pcm_s16le', str(temporary)], check=True)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'path': str(output.resolve()), 'sha256': digest(output), 'frames': track['frames'],
            'fps': track['fps'], 'note': 'Accepted speech mixed once; no generated video audio included.'}


def validate_final_review(review, video, master):
    if review.get('video_sha256') != digest(video) or review.get('master_sha256') != digest(master):
        raise ValueError('Final media changed since review')
    for gate in ('full_playback', 'exact_words', 'speaker_binding', 'lip_sync', 'emotion', 'identity',
                 'wardrobe', 'props', 'action', 'continuity', 'sound_mix'):
        if review.get(gate) is not True:
            raise ValueError('Final human review missing: ' + gate)
    return True
