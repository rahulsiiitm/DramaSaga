"""Measured shot compilation and explicit renderer capability checks."""
import math
import wave
from pathlib import Path

from .core import digest, finite, identifier, integer
from .execution import signature


def measured_track(episode, audio, alignment, review):
    path = Path(audio['path'])
    if not path.is_file() or digest(path) != audio['sha256'] or alignment.get('audio_sha256') != audio['sha256']:
        raise ValueError('Alignment/audio hash missing or changed')
    if review.get('sha256') != audio['sha256'] or review.get('lines_sha256') != signature(episode['lines']) or any(review.get(k) is not True for k in ('words', 'speakers', 'emotion', 'pronunciation')):
        raise ValueError('Audio review must bind exact audio, lines, speakers and performance')
    with wave.open(str(path), 'rb') as wav:
        if wav.getsampwidth() != 2 or wav.getcomptype() != 'NONE':
            raise ValueError('Use measured PCM16 WAV')
        duration = wav.getnframes() / wav.getframerate()
    if not 0 < duration <= 180:
        raise ValueError('Audio duration must be within episode limit')
    groups, order, previous = {}, [], 0
    for cue in alignment['cues']:
        start, end = finite(cue['start'], 'cue start'), finite(cue['end'], 'cue end')
        if start < previous or end <= start or end > duration + .001 or cue.get('actual_audio_checked') is not True:
            raise ValueError('Cue intervals must be checked, ordered and within audio')
        lid = cue['line_id']
        if lid not in groups:
            groups[lid] = []
            order.append(lid)
        elif order[-1] != lid:
            raise ValueError('Line cues must be contiguous')
        groups[lid].append(cue)
        previous = end
    if order != [l['id'] for l in episode['lines']]:
        raise ValueError('Cues must cover every script line in order')
    lines = []
    for line in episode['lines']:
        cues = groups[line['id']]
        if ' '.join(' '.join(c['text'].split()) for c in cues) != ' '.join(line['text'].split()) or any(c['speaker'] != line['speaker'] for c in cues):
            raise ValueError('Cue text/speaker differs from script')
        lines.append({**line, 'start_frame': math.floor(cues[0]['start'] * 24), 'end_frame': math.ceil(cues[-1]['end'] * 24)})
    return {'fps': 24, 'frames': math.ceil(duration * 24), 'seconds': duration, 'lines': lines,
            'audio': dict(audio), 'cues': alignment['cues'], 'audio_review': review,
            'episode_id': episode['id'], 'episode_sha256': signature(episode), 'status': 'measured_review_bound_not_automatic_quality_certification'}


def validate_track(episode, track):
    if track.get('episode_id') != episode['id'] or track.get('episode_sha256') != signature(episode):
        raise ValueError('Measured track is stale for this episode')
    fresh = measured_track(episode, track['audio'], {'audio_sha256': track['audio']['sha256'], 'cues': track['cues']}, track['audio_review'])
    if fresh != track:
        raise ValueError('Measured track content changed')
    return fresh


def cut_plan(episode, track):
    validate_track(episode, track)
    by_line = {l['id']: l for l in track['lines']}
    explicit = any('cut' in s for s in episode['shots'])
    previous, result = 0, []
    for index, shot in enumerate(episode['shots']):
        if explicit:
            cut = shot.get('cut', {})
            start = integer(cut.get('start_frame'), 'cut start', 0, track['frames'])
            end = integer(cut.get('end_frame'), 'cut end', 1, track['frames'])
            if start != previous:
                raise ValueError('Explicit cuts must cover the master without gaps/overlap')
        else:
            if not shot['line_ids']:
                raise ValueError('Reaction/insert-only shots require explicit frame cuts')
            start = previous
            end = track['frames'] if index == len(episode['shots']) - 1 else by_line[shot['line_ids'][-1]]['end_frame']
        if end <= start:
            raise ValueError('Cut must have positive duration')
        active = [l for l in track['lines'] if l['start_frame'] < end and l['end_frame'] > start]
        offscreen = sorted({l['speaker'] for l in active if l['speaker'] not in shot['visible_characters'] and l['speaker'] != 'narrator'})
        result.append({**shot, 'start_frame': start, 'end_frame': end, 'frames': end - start,
                       'active_lines': active, 'audible_offscreen_speakers': offscreen})
        previous = end
    if previous != track['frames']:
        raise ValueError('Cuts do not cover the full measured master')
    return result


def renderer_profile(profile):
    identifier(profile['id'], 'renderer id')
    if not isinstance(profile.get('model'), str) or not profile['model'].strip():
        raise ValueError('Explicit renderer model required')
    modes = profile.get('modes')
    if not isinstance(modes, list) or not modes or not set(modes) <= {'image_to_video', 'audio_to_video', 'native_audio', 'performance'}:
        raise ValueError('Explicit supported renderer modes required')
    maximum = finite(profile['max_seconds'], 'renderer maximum', .01)
    minimum = finite(profile.get('min_seconds', .01), 'renderer minimum', .01)
    if maximum < minimum:
        raise ValueError('Invalid renderer duration range')
    for key in ('multi_shot', 'exact_audio', 'end_frame'):
        if type(profile.get(key, False)) is not bool:
            raise ValueError('Capability must be a boolean: ' + key)
    integer(profile.get('max_speakers', 1), 'max_speakers', 1, 50)
    integer(profile.get('max_reference_images',1),'max_reference_images',1,50)
    durations = profile.get('durations', [])
    if not isinstance(durations, list) or any(not minimum <= finite(d, 'supported duration', .01) <= maximum for d in durations):
        raise ValueError('Supported durations must fit renderer limits')
    return profile


def compile_render_plan(episode, track, profile, connected=False, audio_mode='locked',reference_assets=None):
    renderer_profile(profile)
    if audio_mode not in ('locked', 'native'):
        raise ValueError('Audio mode must be locked or native')
    cuts = cut_plan(episode, track)
    groups, seen_groups = [], set()
    for cut in cuts:
        group_id = cut.get('render_group') if connected else None
        if group_id and groups and groups[-1][0].get('render_group') == group_id:
            if (cut.get('scene_id'), cut['location']) != (groups[-1][0].get('scene_id'), groups[-1][0]['location']):
                raise ValueError('Connected generation cannot cross scene/location boundaries')
            groups[-1].append(cut)
        else:
            if group_id:
                identifier(group_id, 'render group')
                if group_id in seen_groups:
                    raise ValueError('Render group must be contiguous')
                seen_groups.add(group_id)
            groups.append([cut])
    jobs = []
    for group in groups:
        if len(group) > 1 and profile.get('multi_shot') is not True:
            raise ValueError('Renderer lacks verified multi-shot capability')
        start, end = group[0]['start_frame'], group[-1]['end_frame']
        seconds = (end - start) / 24
        requested = max(seconds, profile.get('min_seconds', .01))
        if profile.get('durations'):
            available = [d for d in profile['durations'] if d >= requested]
            if not available:
                raise ValueError('Cut exceeds supported renderer duration; split the shot')
            requested = min(available)
        if requested > profile['max_seconds']:
            raise ValueError('Cut exceeds renderer limit; split at a motivated cut')
        speakers = {l['speaker'] for cut in group for l in cut['active_lines'] if l['speaker'] in cut.get('speaking_faces',cut['visible_characters'])}
        if len(speakers) > profile.get('max_speakers', 1):
            raise ValueError('Too many visible speaking characters for this renderer')
        if audio_mode == 'native':
            mode = 'native_audio'
        elif speakers:
            if profile.get('exact_audio') is not True:
                raise ValueError('Visible speech needs exact-audio or performance conditioning')
            mode = 'audio_to_video' if 'audio_to_video' in profile['modes'] else 'performance'
        else:
            mode = 'image_to_video'
        if mode not in profile['modes']:
            raise ValueError('Renderer does not support required mode: ' + mode)
        if any(c.get('end_frame_reference') for c in group) and profile.get('end_frame') is not True:
            raise ValueError('Renderer has no end-frame support')
        render_id='render-'+group[0]['id']
        if len(render_id)>64:render_id='render-'+group[0]['id'][:40]+'-'+signature(group[0]['id'])[:16]
        job = {'id': render_id, 'shot_ids': [c['id'] for c in group],
               'start_frame': start, 'end_frame': end, 'frames': end - start, 'seconds': seconds,
               'request_seconds': requested, 'mode': mode, 'audio_mode': audio_mode,
               'audio': track['audio'], 'audio_segment': {'start_seconds': start / 24, 'end_seconds': end / 24},
               'first_frame': 'frame-' + group[0]['id'], 'cuts': group,
               'requires_realignment': audio_mode == 'native'}
        job['reference_images']=[]
        if reference_assets is not None:
            for cut in group:
                aid='frame-'+cut['id'];asset=reference_assets.get(aid,{})
                path=Path(asset.get('path',''))
                if not path.is_file() or path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or digest(path)!=asset.get('sha256'):
                    raise ValueError('Every compiled frame needs a current hash-bound image: '+aid)
                job['reference_images'].append({'id':aid,'path':str(path.resolve()),'sha256':asset['sha256']})
            if len(job['reference_images'])>profile.get('max_reference_images',1):
                raise ValueError('Renderer reference-image limit exceeded')
        job['input_sha256'] = signature({'job': job, 'profile': profile})
        jobs.append(job)
    result = {'episode_id': episode['id'], 'episode_sha256': signature(episode), 'track_sha256': signature(track),
              'renderer': profile, 'fps': 24, 'frames': track['frames'], 'jobs': jobs, 'audio_mode': audio_mode,
              'status': 'compiled_not_rendered', 'inputs_bound':reference_assets is not None,'paid_requests': 0}
    result['plan_sha256'] = signature(result)
    return result


def require_render_plan(plan):
    content = {k: v for k, v in plan.items() if k != 'plan_sha256'}
    if signature(content) != plan.get('plan_sha256'):
        raise ValueError('Render plan changed')
    renderer_profile(plan['renderer'])
    for job in plan['jobs']:
        for image in job.get('reference_images',[]):
            path=Path(image['path'])
            if not path.is_file() or digest(path)!=image['sha256']:
                raise ValueError('Compiled reference image changed')
    return plan


def _audio_segment(render):
    source=render['audio']
    if digest(source['path'])!=source['sha256']:raise ValueError('Accepted source audio changed')
    with wave.open(str(source['path']),'rb') as wav:
        rate,channels,width=wav.getframerate(),wav.getnchannels(),wav.getsampwidth()
        if width!=2 or wav.getcomptype()!='NONE':raise ValueError('PCM16 source audio required')
        start=round(render['start_frame']/24*rate)
        stop=min(wav.getnframes(),round(render['end_frame']/24*rate))
        wav.setpos(start);raw=wav.readframes(stop-start)
    target=math.ceil(render['request_seconds']*rate)
    if len(raw)>target*channels*width:raise ValueError('Requested audio would truncate accepted dialogue')
    return rate,channels,width,raw+b'\0'*(target*channels*width-len(raw))


def prepare_render_inputs(plan,output):
    """Exact PCM slices plus silence padding, retaining source provenance."""
    from .core import write_json
    require_render_plan(plan)
    if not plan.get('inputs_bound') or plan['audio_mode']!='locked':
        raise ValueError('Bound locked-audio plan required')
    root=Path(output)
    if root.exists():raise ValueError('Use a fresh render input directory')
    root.mkdir(parents=True)
    candidates={}
    for render in plan['jobs']:
        for image in render['reference_images']:
            candidates[image['id']]={'path':image['path'],'sha256':image['sha256'],'kind':'image'}
        if render['mode'] not in ('audio_to_video','performance'):continue
        rate,channels,width,raw=_audio_segment(render)
        path=root/(render['id']+'.wav')
        with wave.open(str(path),'wb') as wav:
            wav.setframerate(rate);wav.setnchannels(channels);wav.setsampwidth(width);wav.writeframes(raw)
        candidates['audio-'+render['id']]={'path':str(path.resolve()),'sha256':digest(path),'kind':'audio',
            'derivation':{'source_sha256':render['audio']['sha256'],'render_input_sha256':render['input_sha256'],
                          'method':'exact_pcm_slice_and_silence_pad_v1'}}
    write_json(root/'upload-candidates.json',candidates)
    return candidates


def verify_derived_audio(render,record):
    derivation=record.get('derivation',{})
    if derivation.get('source_sha256')!=render['audio']['sha256'] or derivation.get('render_input_sha256')!=render['input_sha256'] or derivation.get('method')!='exact_pcm_slice_and_silence_pad_v1':
        raise ValueError('Derived audio provenance differs from compiled input')
    if digest(record['path'])!=record['sha256']:raise ValueError('Derived audio bytes changed')
    rate,channels,width,raw=_audio_segment(render)
    with wave.open(str(record['path']),'rb') as wav:
        if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth(),wav.getcomptype())!=(rate,channels,width,'NONE') or wav.readframes(wav.getnframes())!=raw:
            raise ValueError('Derived audio must be exact accepted samples plus silence')
    return record
