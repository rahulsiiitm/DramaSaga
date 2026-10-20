# One H3 clip on Modal (research/h3/modal_h3.py: app h3-render, class H3, ComfyUI on a serverless GPU), using the manager's
# production R2V graph (r2v_v1.json) with our references wired into MiniMaxH3ReferenceToVideo's ref_* inputs.
#   .venv/bin/python research/h3/runpod/comfy_r2v.py <run-dir> <clip-id> [out.mp4] [--novid]
#   .venv/bin/python research/h3/runpod/comfy_r2v.py --clip=<clip.json> <out.mp4> [--refh=360] [--ratio=9:16]
# Reads the clip from <run-dir>/render.json (prompt file, seconds, images, videos, audio), or from a clip JSON (render-all.mjs
# writes one per clip, reference cuts and chain tail already applied). The input files travel with the call.
# Autogrow inputs are 0-indexed (ref_image_0..8, ref_video_0..2, ref_audio_0..2: ComfyUI _io.py TemplatePrefix).
# References are labelled by the node in request order (images, then videos, then audio) = "Image N", "Video N",
# "Audio N" in our prompts. 832x480 = fal 480P.
import json, random, subprocess, sys, time, uuid
from pathlib import Path

GRAPH = Path(__file__).with_name('r2v_v1.json')
W, H = 832, 480
_rows = next((int(a.split('=')[1]) for a in sys.argv if a.startswith('--rows=')), 0)
if _rows: H, W = _rows, round(_rows * 16 / 9 / 32) * 32  # e.g. --rows=704 -> 1248x704 (Magic Hour's 720p tier)
TURBO = 'minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors'  # Kijai/MiniMax-H3_comfy loras/

SEND = {}  # the input files, sent with the Modal call by the names the graph uses

def upload(path):
    name = f'{uuid.uuid4().hex[:8]}-{Path(path).name}'; SEND[name] = Path(path).read_bytes(); return name

def main():
    pos = [a for a in sys.argv[1:] if not a.startswith('--')]
    cj = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--clip=')), None)
    if cj:
        clip = json.loads(Path(cj).read_text()); clip_id, out = clip['id'], Path(pos[0])
    else:
        run, clip_id = Path(pos[0]), pos[1]
        tag = '-turbo' if '--turbo' in sys.argv else ''
        out = Path(pos[2]) if len(pos) > 2 else run / 'render-comfy' / f'{clip_id}{tag}.mp4'
        clip = next(c for c in json.loads((run / 'render.json').read_text())['clips'] if c['id'] == clip_id)
    videos = [] if '--novid' in sys.argv else clip.get('videos', [])
    g = json.loads(GRAPH.read_text())
    g['138']['inputs']['value'] = Path(clip['prompt']).read_text()
    portrait = next((a for a in sys.argv if a.startswith('--ratio=')), '').endswith('9:16')
    g['151']['inputs']['value'], g['152']['inputs']['value'] = (H, W) if portrait else (W, H)
    ratio = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--ratio=')), '16:9')
    if ratio not in ('16:9', '9:16'):  # any other shape (render.json's ratio): the tier's pixel count, each side rounded to 32
        a, b = map(int, ratio.split(':')); k = (W * H / (a * b)) ** 0.5  # 480 tier: 1:1 640x640, 4:5 576x704, 3:4 544x736, 4:3 736x544, 21:9 960x416
        g['151']['inputs']['value'], g['152']['inputs']['value'] = round(a * k / 32) * 32, round(b * k / 32) * 32
    g['132']['inputs']['value'] = float(clip['seconds'])
    g['129']['inputs']['noise_seed'] = random.randrange(2**48)
    if '--turbo' in sys.argv:  # the manager's I2V speed settings (i2v_v1.json) with the R2V turbo LoRA: 10 steps, no block cache
        g['lora'] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'lora_name': TURBO, 'strength_model': 0.6, 'model': ['141', 0]}}
        g['126']['inputs']['model'] = g['124']['inputs']['model'] = ['lora', 0]
        g['124']['inputs'].update(scheduler='sgm_uniform', steps=10)
        g['123']['inputs']['sampler_name'] = 'er_sde'
    if '--nosage' in sys.argv:  # GPUs our SageAttention build does not cover (built for sm_120: RTX 5090 / PRO 6000)
        g['141']['inputs']['sage_attention'] = 'disabled'
    # Quality knobs (the production graph trades precision for speed): --te=bf16 full text encoder (default 4-bit nvfp4),
    # --unet=bf16 the full unpruned model (default pruned int8), --nocache no T8 block cache, --seed=N fixed noise.
    arg = lambda k: next((a.split('=', 1)[1] for a in sys.argv if a.startswith(f'--{k}=')), None)
    if arg('te') == 'bf16':
        g['128']['inputs']['clip_name'] = 'qwen3vl_32b_minimax_h3_bf16.safetensors'
    if arg('unet') == 'bf16':
        g['127']['inputs']['unet_name'] = 'minimax_h3_ref2va_bf16.safetensors'
    if '--nocache' in sys.argv:
        for n in ('124', '126'):
            if g[n]['inputs']['model'] == ['142', 0]:
                g[n]['inputs']['model'] = ['141', 0]
    # Official-settings knobs (docs.comfy.org/tutorials/video/minimax/minimax-h3, SGLang cookbook): --steps=50, --sampler=euler,
    # --refmax = reference stills encoded at a 2048 short edge instead of matching the output size.
    if arg('steps'):
        g['124']['inputs']['steps'] = int(arg('steps'))
    if arg('sampler'):
        g['123']['inputs']['sampler_name'] = arg('sampler')
    if '--refmax' in sys.argv:
        g['136']['inputs']['ref_image_size'] = 'max'
    if arg('seed'):
        g['129']['inputs']['noise_seed'] = int(arg('seed'))
    g['92']['inputs']['filename_prefix'] = f'video/{clip_id}-{uuid.uuid4().hex[:8]}'
    ref = g['136']['inputs']
    for i, p in enumerate(clip.get('images', []), 1):
        g[f'img{i}'] = {'class_type': 'LoadImage', 'inputs': {'image': upload(p)}}
        ref[f'ref_images.ref_image_{i - 1}'] = [f'img{i}', 0]
    # The node encodes a reference video at up to 1280x704 (768-short-edge canvas, never upscaled), so 720p clips cost
    # several times the output's own tokens; --refh N sends them N rows tall instead.
    refh = next((int(a.split('=')[1]) for a in sys.argv if a.startswith('--refh=')), 0)
    # The user's own footage (user_video cuts it into <run>/footage/) is the picture H3 must keep: sent at the render's own
    # size instead, so it has the detail to keep (style clips are only motion and look, 360p is plenty).
    rw, rh = g['151']['inputs']['value'], g['152']['inputs']['value']
    # --footrows=N (render-all sends it for a clip of the user's footage with no stills: 360 on drafts, 480 at 720p and up, 2026-10-10): that
    # frame scaled down to N rows on its short side, never up (the footage reference is 21-52% of an edit's GPU time at the render's own size)
    k = min(1, int(arg('footrows')) / min(rw, rh)) if arg('footrows') else 1
    fw, fh = round(rw * k / 2) * 2, round(rh * k / 2) * 2
    for i, p in enumerate(videos, 1):
        if '/footage/' in str(p):
            # sent filling the film's frame, centre-cropped, since H3 copies a wide reference as a thin strip with black bars in a tall
            # frame (AMV v3m-r02, 2026-10-09). Every footage video, not only a lone one (2026-10-09: v2n-r02 clip 3, several videos sent
            # whole for H3 to reframe, came back 36% boxed)
            # ...unless the clip also shows stills (a caption banner, type, a logo): the footage keeps its own frame, scaled to fit, so the
            # picture can hold both (2026-10-10: filled, the Fanum meme dropped its caption banner after 1 s; sent as filmed, the first take kept it)
            vf = f'scale={fw}:{fh}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1' if clip.get('images') else f'scale={fw}:{fh}:force_original_aspect_ratio=increase,crop={fw}:{fh},setsar=1'
            big = Path('/tmp') / f'fit{fw}x{fh}-{uuid.uuid4().hex[:8]}-{Path(p).name}'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', p, '-vf', vf, '-an', big], check=True)
            p = big
        elif refh:
            small = Path('/tmp') / f'refh{refh}-{Path(p).name}'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', p, '-vf', f'scale=-2:{refh}', '-an', small], check=True)
            p = small
        g[f'vid{i}'] = {'class_type': 'VHS_LoadVideo', 'inputs': {'video': upload(p), 'force_rate': 24, 'custom_width': 0,
            'custom_height': 0, 'frame_load_cap': 0, 'skip_first_frames': 0, 'select_every_nth': 1}}
        ref[f'ref_videos.ref_video_{i - 1}'] = [f'vid{i}', 0]
    if clip.get('audio'):
        aud = clip['audio']
        if arg('audio') == 'inpaint':  # padded or cut to the clip's exact length: a silent tail left over makes H3 invent words in it
            aud = Path('/tmp') / f'fit{clip["seconds"]}s-{uuid.uuid4().hex[:8]}.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', clip['audio'], '-af', f'apad=whole_dur={clip["seconds"]}', '-t', str(clip['seconds']), aud], check=True)
        g['aud1'] = {'class_type': 'LoadAudio', 'inputs': {'audio': upload(aud)}}
        ref['ref_audios.ref_audio_0'] = ['aud1', 0]
        if arg('audio') == 'inpaint':
            # --audio=inpaint: the clip's audio is also its OWN sound track, kept as is (noise mask 0), so H3 draws the picture
            # against the exact voice and music instead of re-speaking them (0% word errors, the best lip and beat sync of
            # three modes: research/h3/audio-research/REPORT.md, Alec 2026-10-08). LTX-2's audio-to-video recipe, stock nodes.
            g['aenc'] = {'class_type': 'VAEEncodeAudio', 'inputs': {'audio': ['aud1', 0], 'vae': ['120', 0]}}
            g['amask'] = {'class_type': 'SolidMask', 'inputs': {'value': 0.0, 'width': 8, 'height': 8}}
            g['akeep'] = {'class_type': 'SetLatentNoiseMask', 'inputs': {'samples': ['aenc', 0], 'mask': ['amask', 0]}}
            g['av'] = {'class_type': 'LTXVConcatAVLatent', 'inputs': {'video_latent': ['136', 1], 'audio_latent': ['akeep', 0]}}
            g['125']['inputs']['latent_image'] = ['av', 0]
    # --footage=guide|v2v50|v2v70 (render-all: H3_FOOTAGE_MODE): the user's footage also goes on the clip's OWN timeline, not
    # only as a reference video (which H3 repaints: invented frames, fake impact frames on the AMV and Saquon edits). The
    # segments are laid back to back in their Video order (FOOTAGE.md: "cut them together in this order"), each at its own
    # length, the last frame held to the end. guide = one real frame pinned every 0.5 s (MiniMaxH3AddGuide); v2vN = the track
    # is the starting latent at denoise N/100. research/h3/video-research (2026-10-09): SSIM to the footage 0.87 guide,
    # 0.86 v2v50, 0.73 v2v70, against 0.55 for the reference video alone.
    fm, foot = arg('footage'), [p for p in videos if '/footage/' in str(p)]
    if fm and foot:
        n = max(5, round(float(clip['seconds']) * 24)); L = n + (5 - n % 17) % 17
        track = Path('/tmp') / f'track-{uuid.uuid4().hex[:8]}.mp4'
        ins = sum((['-i', str(p)] for p in foot), [])
        fc = ''.join(f'[{i}:v]fps=24,scale={rw}:{rh}:force_original_aspect_ratio=increase,crop={rw}:{rh},setsar=1[v{i}];' for i in range(len(foot)))
        fc += ''.join(f'[v{i}]' for i in range(len(foot))) + f'concat=n={len(foot)}:v=1:a=0,tpad=stop_mode=clone:stop_duration={L / 24:.2f}[t]'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', *ins, '-filter_complex', fc, '-map', '[t]', '-frames:v', str(L), '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', str(track)], check=True)
        g['track'] = {'class_type': 'VHS_LoadVideo', 'inputs': {'video': upload(track), 'force_rate': 24, 'custom_width': 0, 'custom_height': 0,
            'frame_load_cap': 0, 'skip_first_frames': 0, 'select_every_nth': 1}}
        if fm == 'guide':
            prev = g['126']['inputs']['conditioning']
            for k, f in enumerate(range(0, L, 12)):
                g[f'gf{k}'] = {'class_type': 'ImageFromBatch', 'inputs': {'image': ['track', 0], 'batch_index': f, 'length': 1}}
                g[f'g{k}'] = {'class_type': 'MiniMaxH3AddGuide', 'inputs': {'positive': prev, 'vae': ['119', 0], 'latent': ['136', 1], 'image': [f'gf{k}', 0], 'frame_idx': f}}
                prev = [f'g{k}', 0]
            g['126']['inputs']['conditioning'] = prev
        elif fm.startswith('v2v') and 'av' in g:
            g['venc'] = {'class_type': 'VAEEncode', 'inputs': {'pixels': ['track', 0], 'vae': ['119', 0]}}
            g['av']['inputs']['video_latent'] = ['venc', 0]
            g['124']['inputs']['denoise'] = int(fm[3:]) / 100
    # pins (render.json "pins": [{"t": seconds, "image": path}]): a still pinned ON the clip's timeline at that time
    # (MiniMaxH3AddGuide: re-injected every step, never denoised). A reference image has no time and whatever it shows is
    # available to every frame; a pin says where the picture is at that moment: a shot's first frame, the state after a change.
    pins = clip.get('pins') or []
    if pins:
        prev, last = g['126']['inputs']['conditioning'], round(float(clip['seconds']) * 24) - 1
        for k, pin in enumerate(pins):
            fit, src = Path('/tmp') / f'pin{rw}x{rh}-{uuid.uuid4().hex[:8]}.png', pin.get('image')
            if pin.get('video'):  # a frame of a video: {"t", "video", "at"} (an edit's cut: that moment of that footage, on that beat)
                src = Path('/tmp') / f'pinv-{uuid.uuid4().hex[:8]}.png'
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(pin.get('at', 0)), '-i', pin['video'], '-frames:v', '1', str(src)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-vf', f'scale={rw}:{rh}:force_original_aspect_ratio=increase,crop={rw}:{rh},setsar=1', '-frames:v', '1', str(fit)], check=True)
            g[f'pi{k}'] = {'class_type': 'LoadImage', 'inputs': {'image': upload(fit)}}
            g[f'pg{k}'] = {'class_type': 'MiniMaxH3AddGuide', 'inputs': {'positive': prev, 'vae': ['119', 0], 'latent': ['136', 1], 'image': [f'pi{k}', 0], 'frame_idx': min(last, max(0, round(float(pin['t']) * 24)))}}
            prev = [f'pg{k}', 0]
        g['126']['inputs']['conditioning'] = prev
    t0 = time.time()
    if '--v2' in sys.argv or '--v2-shipped' in sys.argv or '--v2-sage' in sys.argv:  # render-all.mjs passes these for R2V=v2
        sys.exit('R2V=v2: the R2V V2 graph and its Modal app are not in this repo; unset R2V')
    import modal
    res = modal.Cls.from_name('h3-render', 'H3')().render.remote(g, SEND)
    out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(res['mp4'])
    print(f"{clip_id}: {time.time() - t0:.0f} s ({res['seconds']} s rendering on {res['gpu']}) → {out}")

if __name__ == '__main__':
    main()
