"""Offline English SRT/ASS from approved text and measured line timings."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
from .core import digest, validate_timeline, write_json
from .gates import object_hash


def stamp(ms, ass=False):
    hours, rem = divmod(ms, 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, millis = divmod(rem, 1000)
    return (f'{hours}:{minutes:02}:{seconds:02}.{millis // 10:02}' if ass else
            f'{hours:02}:{minutes:02}:{seconds:02},{millis:03}')


def subtitle_text(text):
    # Do not interpret SRT HTML or ASS override/escape sequences.
    if any(c in text for c in ('<', '>', '{', '}', '\\', '\n', '\r')) or any(ord(c) < 32 for c in text):
        raise ValueError('Subtitle markup/control characters require text revision and new approval')
    return text


def write_subtitles(track, output_dir, language='en', max_cps=25, character_names=None, introductions=None):
    if language not in ('en', 'en-IN', 'en-US', 'en-GB'):
        raise ValueError('Only approved English subtitle tracks supported')
    validate_timeline(track)
    if type(max_cps) not in (int, float) or not 1 <= max_cps <= 25:
        raise ValueError('Reading-speed cap must be 1..25 characters/second')
    out = Path(output_dir)
    if out.exists():
        raise ValueError('Refusing to overwrite subtitle directory')
    srt, ass = [], [
        '[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 1080', 'PlayResY: 1920',
        'WrapStyle: 2', '', '[V4+ Styles]',
        'Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding',
        'Style: Default,DejaVu Sans,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,90,90,180,1',
        '', '[Events]', 'Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text']
    cues = []
    for index, line in enumerate(track['lines'], 1):
        text = subtitle_text(line['text'])
        duration = line['measured_seconds']
        wrapped = textwrap.wrap(text, 42, break_long_words=False, break_on_hyphens=False,
                                replace_whitespace=False, drop_whitespace=True)
        if not wrapped or len(wrapped) > 2 or any(len(part) > 42 for part in wrapped) or len(text) / duration > max_cps:
            raise ValueError('Line needs reviewed shorter text or word-aligned cue splits: ' + line['id'])
        start = round(line['start_frame'] / track['fps'] * 1000)
        end = round((line['start_frame'] / track['fps'] + duration) * 1000)
        if end <= start:
            raise ValueError('Subtitle interval below millisecond precision')
        srt.append(f'{index}\n{stamp(start)} --> {stamp(end)}\n' + '\n'.join(wrapped) + '\n')
        ass.append(f'Dialogue: 0,{stamp(start, True)},{stamp(end, True)},Default,,0,0,0,,' + r'\N'.join(wrapped))
        cues.append({'line_id': line['id'], 'start_ms': start, 'end_ms': end, 'text': text})
    names = character_names or {}
    if not isinstance(names, dict):
        raise ValueError('Character names must map speaker ids to display names')
    bars = []
    # Speaker labels are separate overlays; subtitle words remain exact.
    for line in track['lines']:
        if line['speaker'] == 'narrator':
            continue
        if line['speaker'] not in names:
            if character_names is not None:
                raise ValueError('Missing display name for speaker')
            continue
        bars.append({'speaker': line['speaker'], 'start_frame': line['start_frame'],
                     'end_frame': line['end_frame'], 'kind': 'speaker'})
    for intro in introductions or []:
        if intro['speaker'] not in names or type(intro['start_frame']) is not int or type(intro['end_frame']) is not int or not 0 <= intro['start_frame'] < intro['end_frame'] <= track['frames']:
            raise ValueError('Invalid character introduction interval/name')
        bars.append({**intro, 'kind': 'introduction'})
    # Separate styles place speaking name above captions and introduction at top-left.
    style_at = ass.index('[Events]')
    ass[style_at:style_at] = [
        'Style: Speaker,DejaVu Sans,36,&H00FFFFFF,&H00FFFFFF,&H00222222,&H80000000,1,0,0,0,100,100,0,0,3,6,0,2,90,90,320,1',
        'Style: Introduction,DejaVu Sans,44,&H00FFFFFF,&H00FFFFFF,&H00222222,&H80000000,1,0,0,0,100,100,0,0,3,6,0,7,90,90,180,1', '']
    for bar in bars:
        name = subtitle_text(names[bar['speaker']])
        if not name.strip() or len(name) > 32:
            raise ValueError('Name bar needs 1..32 characters')
        style = 'Speaker' if bar['kind'] == 'speaker' else 'Introduction'
        start, end = (round(bar[k] / track['fps'] * 1000) for k in ('start_frame', 'end_frame'))
        ass.append(f'Dialogue: 1,{stamp(start, True)},{stamp(end, True)},{style},,0,0,0,,' + name)
    out.mkdir(parents=True)
    (out / 'captions.srt').write_text('\n'.join(srt), encoding='utf-8')
    (out / 'captions.ass').write_text('\n'.join(ass) + '\n', encoding='utf-8')
    result = {'language': language, 'cues': cues, 'status': 'preview_requires_human_review',
              'timeline_sha256': object_hash(track), 'name_bars': bars,
              'srt_sha256': digest(out / 'captions.srt'), 'ass_sha256': digest(out / 'captions.ass')}
    write_json(out / 'manifest.json', result)
    return result


def burn_subtitles(track, video, subtitle_dir, output):
    validate_timeline(track)
    folder, output = Path(subtitle_dir), Path(output)
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest['timeline_sha256'] != object_hash(track) or any(
            digest(folder / name) != manifest[key] for name, key in
            [('captions.srt', 'srt_sha256'), ('captions.ass', 'ass_sha256')]):
        raise ValueError('Subtitle inputs changed since generation')
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(video)], text=True))
    videos = [s for s in info['streams'] if s['codec_type'] == 'video']
    if len(videos) != 1:
        raise ValueError('One video stream required')
    stream = videos[0]
    if abs(stream['width'] / stream['height'] - 9 / 16) > 0.01:
        raise ValueError('Current subtitle layout is portrait 9:16 only; review another layout before use')
    from fractions import Fraction
    if Fraction(stream['avg_frame_rate']) != track['fps'] or int(stream.get('nb_frames', -1)) != track['frames']:
        raise ValueError('Video frame count/rate does not match approved timeline')
    if output.exists():
        raise ValueError('Refusing to overwrite burned edition')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Fixed local filename avoids filter-string path injection.
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        temp = Path(temp)
        shutil.copyfile(folder / 'captions.ass', temp / 'captions.ass')
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(Path(video).resolve()),
                        '-vf', 'ass=captions.ass', '-map', '0:v:0', '-map', '0:a?', '-c:v', 'libx264',
                        '-crf', '18', '-c:a', 'copy', str(temp / 'burned.mp4')], cwd=temp, check=True)
        (temp / 'burned.mp4').replace(output)
    return {'path': str(output.resolve()), 'sha256': digest(output),
            'status': 'burned_preview_requires_visual_and_playback_review'}
