import argparse
import contextlib
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

import requests


def read_json(path):
    return json.loads(Path(path).read_text())


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command):
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def normalized(text):
    return ' '.join(re.findall(r"[a-z0-9']+", text.lower()))


def compare_transcripts(expected, transcripts, threshold):
    ratios = [difflib.SequenceMatcher(None, normalized(expected), normalized(t)).ratio()
              for t in transcripts]
    agreement = difflib.SequenceMatcher(None, *[normalized(t) for t in transcripts]).ratio() if len(transcripts) == 2 else 0
    return {'expected_similarity': ratios, 'agreement': agreement,
            'pass': len(transcripts) == 2 and all(r >= threshold for r in ratios) and agreement >= threshold}


class Production:
    def __init__(self, config_path, live=False, accept_costs=False):
        self.config_path = Path(config_path).resolve()
        self.base = self.config_path.parent
        self.cfg = read_json(self.config_path)
        self.live = live
        self.accept_costs = accept_costs
        self.output = self.resolve(self.cfg['output_dir'])
        self.api = self.cfg.get('api_base', 'https://api.magichour.ai').rstrip('/')
        self.headers = {'Authorization': 'Bearer ' + os.environ.get(self.cfg.get('api_key_env', 'MAGICHOUR_KEY'), '')}
        self.session = requests.Session()
        self.scripts = [read_json(self.resolve(p)) for p in self.cfg['scripts']]
        self.validate()

    def resolve(self, path):
        return (self.base / path).resolve()

    def validate(self):
        if self.api != 'https://api.magichour.ai':
            raise ValueError('Only the configured Magic Hour HTTPS origin is supported')
        if self.cfg['batch_cap_credits'] <= 0 or self.cfg['episode_cap_credits'] <= 0:
            raise ValueError('Positive credit caps are required')
        quote = self.cfg['quote']
        if quote['image_credits'] <= 0 or quote['video_credits_per_second'] <= 0:
            raise ValueError('Positive explicit price quotes are required')
        episodes = [s['ep'] for s in self.scripts]
        if len(set(episodes)) != len(episodes):
            raise ValueError('Duplicate episode numbers')
        for script in self.scripts:
            if not script['scenes']:
                raise ValueError('An episode must contain scenes')
            nums = [s['n'] for s in script['scenes']]
            if len(set(nums)) != len(nums):
                raise ValueError('Duplicate scene numbers')
            for scene in script['scenes']:
                for field in ('location', 'keyframe_visual', 'camera', 'micro_acting', 'dialogue'):
                    if field not in scene:
                        raise ValueError('Missing scene field: ' + field)
                if not 1 <= scene['seconds'] <= 60:
                    raise ValueError('Invalid duration')
                for line in scene['dialogue']:
                    if line['character'] not in self.cfg['characters']:
                        raise ValueError('Missing character reference specification')
                self.references(script, scene)

    def override(self, script, scene):
        return self.cfg.get('scene_overrides', {}).get(f"E{script['ep']:02d}_S{scene['n']:02d}", {})

    def characters(self, script, scene):
        explicit = self.override(script, scene).get('characters')
        if explicit is not None:
            return explicit
        text = scene['keyframe_visual'] + ' ' + ' '.join(d['character'] for d in scene['dialogue'])
        return [name for name in self.cfg['characters'] if re.search(r'\b' + re.escape(name) + r'\b', text)]

    def references(self, script, scene):
        chars = self.characters(script, scene)
        paths = [self.resolve(self.cfg['characters'][c]['reference']) for c in chars]
        override = self.override(script, scene)
        loc = override.get('location_reference')
        if loc is None:
            blob = (scene['location'] + ' ' + scene['keyframe_visual']).lower()
            loc = next((v for k, v in self.cfg['locations'].items() if k in blob), None)
        if loc is None:
            raise ValueError('No location reference; configure a scene override')
        paths.append(self.resolve(loc))
        return paths

    def chained(self, script, index):
        scene = script['scenes'][index]
        if not self.override(script, scene).get('chain_from_previous', False):
            return False
        if index == 0:
            raise ValueError('First scene cannot chain')
        previous = script['scenes'][index - 1]
        same = self.override(script, scene).get('same_space_confirmed', False)
        if not same or set(self.characters(script, scene)) != set(self.characters(script, previous)):
            raise ValueError('Chaining requires same-space confirmation and identical character references')
        return True

    def preflight_live(self):
        if not self.accept_costs:
            raise ValueError('--live requires --accept-costs')
        key = os.environ.get(self.cfg.get('api_key_env', 'MAGICHOUR_KEY'))
        if not key:
            raise ValueError('API key environment variable is missing')
        verified = self.cfg['quote'].get('verified_at')
        if verified != datetime.date.today().isoformat():
            raise ValueError('Verify current model prices and set quote.verified_at to today before paid execution')
        if len(self.cfg.get('transcribers', [])) != 2:
            raise ValueError('Configure two independent transcription command arrays')
        for script in self.scripts:
            for scene in script['scenes']:
                for p in self.references(script, scene):
                    if not p.is_file():
                        raise FileNotFoundError(p)
        for binary in ('ffmpeg', 'ffprobe'):
            run([binary, '-version'])

    def plan(self):
        output = []
        q = self.cfg['quote']
        total = 0
        for script in self.scripts:
            cost = 0
            scenes = []
            for i, scene in enumerate(script['scenes']):
                chained = self.chained(script, i)
                seconds = scene['seconds'] + self.cfg.get('padding_seconds', 2)
                amount = seconds * q['video_credits_per_second'] + (0 if chained else q['image_credits'])
                cost += amount
                scenes.append({'scene': scene['n'], 'render_seconds': seconds, 'chain': chained,
                               'quoted_credits': amount, 'missing_references': [str(p) for p in self.references(script, scene) if not p.exists()]})
            total += cost
            output.append({'episode': script['ep'], 'quoted_credits': cost, 'scenes': scenes,
                           'fits_episode_cap': cost <= self.cfg['episode_cap_credits']})
        return {'episodes': output, 'quoted_total': total, 'batch_cap': self.cfg['batch_cap_credits'],
                'fits_batch_cap': total <= self.cfg['batch_cap_credits'], 'paid_requests': 0,
                'note': 'Quotes exclude rerolls. Missing references are allowed only in dry-run.'}

    @contextlib.contextmanager
    def lock(self):
        import fcntl
        self.output.mkdir(parents=True, exist_ok=True)
        with (self.output / '.render.lock').open('a') as file:
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another renderer holds this output directory')
            yield

    def records(self):
        p = self.output / 'jobs.json'
        return read_json(p) if p.exists() else {}

    def persist(self, records):
        save_json(self.output / 'jobs.json', records)

    def charged(self, record):
        return max(record['quote'], record.get('credits', 0))

    def reserve(self, records, key, ep, quote):
        batch = sum(self.charged(r) for r in records.values())
        episode = sum(self.charged(r) for r in records.values() if r['episode'] == ep)
        if batch + quote > self.cfg['batch_cap_credits'] or episode + quote > self.cfg['episode_cap_credits']:
            raise RuntimeError('Credit cap would be exceeded; no request submitted')
        records[key] = {'episode': ep, 'quote': quote, 'state': 'submission_unknown'}
        self.persist(records)

    def get(self, path):
        response = self.session.get(self.api + path, headers=self.headers, timeout=60)
        response.raise_for_status()
        return response.json()

    def upload(self, local):
        cache_path = self.output / 'assets.json'
        cache = read_json(cache_path) if cache_path.exists() else {}
        digest = sha(local)
        if digest in cache:
            return cache[digest]
        response = self.session.post(self.api + '/v1/files/upload-urls', headers=self.headers,
                                     json={'items': [{'extension': Path(local).suffix.lstrip('.'), 'type': 'image'}]}, timeout=90)
        response.raise_for_status()
        item = response.json()['items'][0]
        with Path(local).open('rb') as f:
            response = self.session.put(item['upload_url'], data=f, headers={'Content-Type': 'application/octet-stream'}, timeout=120)
            response.raise_for_status()
        cache[digest] = item['file_path']
        save_json(cache_path, cache)
        return item['file_path']

    def job(self, ep, kind, payload, quote, dest):
        signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        key = f'{ep}:{kind}:{dest.relative_to(self.output)}'
        records = self.records()
        record = records.get(key)
        if record is not None:
            if record.get('signature') != signature:
                raise RuntimeError('Job inputs changed. Use a new attempt output directory; keep the existing ledger and caps reconciled.')
            if record['state'] == 'submission_unknown':
                raise RuntimeError('Previous submission outcome is unknown. Reconcile the provider job before retrying.')
            if record['state'] == 'complete' and dest.exists():
                return dest
            if record['state'] in ('error', 'canceled'):
                raise RuntimeError('Failed job retained for credit reconciliation; no automatic reroll')
        else:
            self.reserve(records, key, ep, quote)
            record = records[key]
            record['signature'] = signature
            self.persist(records)
            endpoint = '/v1/ai-image-editor' if kind == 'image' else '/v1/image-to-video'
            response = self.session.post(self.api + endpoint, headers=self.headers, json=payload, timeout=90)
            response.raise_for_status()
            record['id'] = response.json()['id']
            record['state'] = 'submitted'
            self.persist(records)
        deadline = time.monotonic() + self.cfg.get('poll_timeout_seconds', 1500)
        while time.monotonic() < deadline:
            data = self.get(f"/v1/{kind}-projects/{record['id']}")
            status = data.get('status')
            if status in ('complete', 'error', 'canceled'):
                record['state'] = status
                if data.get('credits_charged') is not None:
                    record['credits'] = data['credits_charged']
                self.persist(records)
                if status != 'complete':
                    raise RuntimeError('Generation ended: ' + str(status))
                response = self.session.get(data['downloads'][0]['url'], timeout=120)
                response.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                temp = dest.with_suffix(dest.suffix + '.part')
                temp.write_bytes(response.content)
                temp.replace(dest)
                return dest
            time.sleep(self.cfg.get('poll_interval_seconds', 10))
        raise TimeoutError('Job remains saved. Resume to poll it; do not resubmit.')

    def keyframe_prompt(self, script, scene):
        clothes = ' '.join(self.cfg['characters'][name]['wardrobe'] for name in self.characters(script, scene))
        return (f"{self.cfg['style']} {scene['keyframe_visual']} Camera: {scene['camera']}. {clothes} "
                'Keep faces exactly consistent with reference images. Exactly the described people, no duplicates. '
                'No readable text or numbers, no charts, no legible screens. ' + self.override(script, scene).get('prompt_extra', ''))

    def clip_prompt(self, script, scene):
        dialogue = ' '.join(f"{d['character']} ({d.get('voice', 'natural voice')}) says exactly: {json.dumps(d['line'])}." for d in scene['dialogue'])
        speech = dialogue + ' Each line exactly once. No added words, greetings or other speech.' if dialogue else 'No speech, ambient sound only.'
        return (f"Continue this exact scene: {scene['keyframe_visual']} Camera: {scene['camera']}. "
                f"ACTION BEATS IN ORDER: {scene['micro_acting']}. {speech} "
                'Expressions must match each line and action; no smiling unless appropriate. '
                'Every object keeps its position and orientation unless an action explicitly moves it. '
                'Nothing flips or changes hands off-screen. Same people and wardrobe as the start frame. '
                'No new people or readable on-screen text. Natural lip sync. ' + self.override(script, scene).get('prompt_extra', ''))

    def scene_dir(self, ep, n):
        attempt = int(self.cfg.get('scene_overrides', {}).get(f'E{ep:02d}_S{n:02d}', {}).get('attempt', 1))
        if attempt < 1:
            raise ValueError('attempt must be positive')
        return self.output / f'E{ep:02d}' / f'S{n:02d}' / f'attempt{attempt}'

    def input_signature(self, script, index):
        scene = script['scenes'][index]
        config = {k: v for k, v in self.cfg.items() if k not in ('scene_overrides', 'quote', 'batch_cap_credits', 'episode_cap_credits')}
        config['scene_override'] = self.override(script, scene)
        blob = {'scene': scene, 'config': config, 'refs': {str(p): sha(p) if p.exists() else None for p in self.references(script, scene)}}
        if self.chained(script, index):
            previous = self.scene_dir(script['ep'], script['scenes'][index - 1]['n']) / 'clip.mp4'
            blob['previous_clip'] = sha(previous) if previous.exists() else None
        return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()

    def check_inputs(self, script, index, directory):
        signature = self.input_signature(script, index)
        p = directory / 'inputs.json'
        if p.exists() and read_json(p)['signature'] != signature:
            raise RuntimeError('Scene inputs changed; increment attempt and re-review downstream clips')
        if not p.exists():
            save_json(p, {'signature': signature})

    def approved(self, directory):
        p = directory / 'review.json'
        clip = directory / 'clip.mp4'
        if not p.exists() or not clip.exists():
            return False
        review = read_json(p)
        return (review.get('clip_sha256') == sha(clip) and all(review.get(k) is True for k in
                ('dialogue_correct', 'faces_wardrobe_correct', 'actions_props_expressions_correct', 'no_bad_text', 'approved')))

    def qa(self, script, scene, directory):
        clip = directory / 'clip.mp4'
        probe = json.loads(run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(clip)]))
        duration = float(probe['format']['duration'])
        audio = any(s['codec_type'] == 'audio' for s in probe['streams'])
        expected = scene['seconds'] + self.cfg.get('padding_seconds', 2)
        if abs(duration - expected) > 1 or not audio:
            raise RuntimeError('Clip duration/audio check failed')
        for t, name in ((0.5, 'start'), (duration / 2, 'mid'), (max(duration - 2.5, 0), 'end')):
            run(['ffmpeg', '-y', '-ss', str(t), '-i', str(clip), '-frames:v', '1', str(directory / (name + '.png'))])
        audio_path = directory / 'audio.wav'
        run(['ffmpeg', '-y', '-i', str(clip), '-vn', '-ac', '1', '-ar', '16000', str(audio_path)])
        transcripts = []
        for cmd in self.cfg['transcribers']:
            transcripts.append(run([arg.replace('{audio}', str(audio_path)) for arg in cmd]).strip())
        expected_text = ' '.join(d['line'] for d in scene['dialogue'])
        result = compare_transcripts(expected_text, transcripts, self.cfg.get('transcript_min_similarity', 0.85))
        save_json(directory / 'qa.json', {'duration': duration, 'audio': audio, 'expected': expected_text,
                                        'transcripts': transcripts, 'text_check': result, 'visual_review_required': True})
        if not (directory / 'review.json').exists():
            save_json(directory / 'review.json', {'clip_sha256': sha(clip), 'dialogue_correct': False,
                      'faces_wardrobe_correct': False, 'actions_props_expressions_correct': False,
                      'no_bad_text': False, 'approved': False})
        return result

    def step(self, episode):
        if not self.live:
            return self.plan()
        self.preflight_live()
        script = next(s for s in self.scripts if s['ep'] == episode)
        with self.lock():
            for i, scene in enumerate(script['scenes']):
                directory = self.scene_dir(episode, scene['n'])
                directory.mkdir(parents=True, exist_ok=True)
                self.check_inputs(script, i, directory)
                if (directory / 'clip.mp4').exists():
                    if not (directory / 'qa.json').exists():
                        self.qa(script, scene, directory)
                    if not self.approved(directory):
                        return {'status': 'awaiting_visual_and_dialogue_review', 'directory': str(directory)}
                    continue
                frame = directory / 'frame.png'
                if not frame.exists():
                    if self.chained(script, i):
                        previous = script['scenes'][i - 1]
                        previous_dir = self.scene_dir(episode, previous['n'])
                        if not self.approved(previous_dir):
                            raise RuntimeError('Previous clip requires approval before chaining')
                        run(['ffmpeg', '-y', '-ss', str(previous['seconds']), '-i', str(previous_dir / 'clip.mp4'), '-frames:v', '1', str(frame)])
                    else:
                        refs = [self.upload(p) for p in self.references(script, scene)]
                        payload = {'name': f'E{episode:02d}S{scene["n"]:02d}', 'model': self.cfg['image_model'],
                                   'assets': {'image_file_paths': refs}, 'style': {'prompt': self.keyframe_prompt(script, scene)}}
                        self.job(episode, 'image', payload, self.cfg['quote']['image_credits'], frame)
                asset = self.upload(frame)
                seconds = scene['seconds'] + self.cfg.get('padding_seconds', 2)
                payload = {'name': f'E{episode:02d}S{scene["n"]:02d}', 'model': self.cfg['video_model'],
                           'resolution': self.cfg['resolution'], 'audio': True, 'end_seconds': seconds,
                           'assets': {'image_file_path': asset}, 'style': {'prompt': self.clip_prompt(script, scene)}}
                self.job(episode, 'video', payload, seconds * self.cfg['quote']['video_credits_per_second'], directory / 'clip.mp4')
                qa = self.qa(script, scene, directory)
                return {'status': 'awaiting_visual_and_dialogue_review', 'directory': str(directory), 'text_check': qa}
        return {'status': 'all_scenes_approved', 'episode': episode}

    def assemble(self, episode):
        script = next(s for s in self.scripts if s['ep'] == episode)
        directory = self.output / f'E{episode:02d}'
        with self.lock():
            clips = []
            for i, scene in enumerate(script['scenes']):
                source = self.scene_dir(episode, scene['n'])
                self.check_inputs(script, i, source)
                if not self.approved(source):
                    raise RuntimeError('Every clip must have current human approval before assembly')
                trimmed = source / 'trimmed.mp4'
                run(['ffmpeg', '-y', '-i', str(source / 'clip.mp4'), '-t', str(scene['seconds']),
                     '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(trimmed)])
                clips.append(trimmed)
            listing = directory / 'concat.txt'
            if any("'" in str(p) for p in clips):
                raise ValueError('Assembly output paths cannot contain apostrophes')
            listing.write_text(''.join("file '" + str(p) + "'\n" for p in clips))
            result = directory / 'episode.mp4'
            run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing),
                 '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(result)])
            return {'episode': episode, 'output': str(result), 'final_visual_review_required': True}


def main():
    default = Path(__file__).resolve().parent.parent / 'examples' / 'honesty.json'
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(default))
    parser.add_argument('--episode', type=int, default=1)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--accept-costs', action='store_true')
    parser.add_argument('--assemble', action='store_true')
    args = parser.parse_args()
    pipeline = Production(args.config, args.live, args.accept_costs)
    if args.assemble:
        if not args.live:
            raise SystemExit('--assemble requires --live and approved local clips; it does not call a paid API')
        result = pipeline.assemble(args.episode)
    else:
        result = pipeline.step(args.episode)
    print(json.dumps(result, indent=2))
    if not args.live:
        print('dry run complete')


if __name__ == '__main__':
    main()
