// render-all.mjs <run-dir> — render every clip of <run>/render.json at the same time on Modal (one ComfyUI job per clip:
// research/h3/runpod/comfy_r2v.py builds it, research/h3/modal_h3.py runs it), then join the clips under the soundtrack.
import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { joinFilm } from './join.mjs';
import { uncoveredRows } from './check-prompt.mjs';
import { clipTail } from '../../research/h3/soundtrack.mjs';
import { GoogleGenAI } from '@google/genai';
import { imageModel, quotaWait } from '../../research/h3/tools-film.mjs';

const run = path.resolve(process.argv[2]);
const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
// A run whose session stopped on a failed still, voice or image (FAILED.json, research/h3/tools-film.mjs) is never rendered.
if (fs.existsSync(path.join(run, 'FAILED.json'))) { console.log(`REFUSED: the run failed and lacks what its clips need: ${fs.readFileSync(path.join(run, 'FAILED.json'), 'utf8')}`); process.exit(1); }
const plan = JSON.parse(fs.readFileSync(path.join(run, 'render.json'), 'utf8'));
// Map shots (agent/h3film/maps.mjs, map_shots): a failed map half renders nothing, and a code clip whose mp4 is not there is refused here.
if (fs.existsSync(path.join(run, 'maps/failed.json'))) { console.log(`REFUSED: the map shots failed: ${fs.readFileSync(path.join(run, 'maps/failed.json'), 'utf8')}`); process.exit(1); }
const noCode = plan.clips.filter((c) => c.code && !fs.existsSync(c.code)).map((c) => `${c.id}: ${c.code}`);
if (noCode.length) { console.log(`REFUSED: code clips with no mp4: ${noCode.join(', ')}`); process.exit(1); }
const MAPC = plan.clips.find((c) => c.code && path.resolve(c.code).startsWith(path.join(run, 'maps') + path.sep));
// A code clip ("code": <mp4> from the code_clip tool, CODE_SHOTS=1) and a clean footage clip ("footage": <the segment user_video
// cut from the user's own video, research/h3/tools-footage.mjs>) are no H3 call: the mp4 is the clip, conformed below.
const H3C = plan.clips.filter((c) => !c.code && !c.footage);
// A clip of the user's footage with no stills sends its footage reference at most 360 rows on a draft (480 rows at 720p and up): Alec
// watched it at 720p and the edits looked the same; on drafts the long clips matched shipped at 0.90-0.98 (2026-10-10, 19-29% less GPU
// on long clips, 19-25% at 720p). Never with stills: there the talking head's speaker vanished at 360 and the chart came out too small
// at 480.
const footRows = (c) => (c.images || []).length || !(c.videos || []).some((v) => v.includes('/footage/')) ? 0 : +(process.env.GPU_ROWS || 480) <= 480 ? 360 : 480;
// A proven component's reference clip often carries its neighbours (another scene, a caption card): its stills.json
// records the cut its proof rendered with, [start, length]. Send that cut, never the raw clip.
const PROVEN = path.join(REPO, 'agent/h3film/library/proven');
const trims = Object.fromEntries(fs.readdirSync(PROVEN).filter((d) => fs.existsSync(path.join(PROVEN, d, 'stills.json')))
  .map((d) => JSON.parse(fs.readFileSync(path.join(PROVEN, d, 'stills.json'), 'utf8'))).filter((j) => j.trim)
  .map((j) => [path.join(REPO, j.source), j.trim]));
const cut = (v) => {
  const t = trims[path.resolve(v)]; if (!t) return v;
  const o = path.join(run, 'render', 'refs', `${path.basename(v, '.mp4')}-${t[0]}-${t[1]}.mp4`);
  fs.mkdirSync(path.dirname(o), { recursive: true });
  // fal refuses a reference video under 2.0 s: a shorter cut holds its last frame to 2.0 s (the motion is unchanged)
  const hold = t[1] < 2 ? ['-vf', `tpad=stop_mode=clone:stop_duration=${(2.05 - t[1]).toFixed(2)}`] : [];
  if (!fs.existsSync(o)) execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-ss', String(t[0]), '-t', String(t[1]), '-i', v, ...hold, '-an', o]);
  return o;
};
for (const c of plan.clips) c.videos = (c.videos || []).map(cut);
// A clip whose only video is a segment of the user's footage opens on exactly that segment's first frame: the render pins it
// (2026-10-09: the planner was told to write this pin and skipped it, AMV v3m-r02).
// Not when the clip also attaches stills (a caption banner, type, a logo): the pinned raw frame has none of them, so H3 kept the footage bare
// and dropped them (2026-10-10: the Fanum meme lost its caption banner; the take before the pin existed kept it)
for (const c of H3C) if (c.videos.length === 1 && c.videos[0].includes('/footage/') && !(c.images || []).length && !(c.pins || []).some((p) => +p.t === 0)) c.pins = [{ t: 0, video: c.videos[0], at: 0 }, ...(c.pins || [])];
// ...and renders only what the film keeps of it, its span + 0.3 s: the AMV planner wrote seconds 5 on every one-shot clip and rendered 110 s for a 33 s film (2026-10-09)
// In an edit (a film with footage clips), a painted clip also renders only its span + 0.3 s, not PAINTED.md's "minimum 5" (EDIT_TRIM=0 turns it off).
// Alec 2026-10-10 on prod-b14 side by side: the same, the fast cuts at the end a bit better (a chained film keeps its lengths: the next clip takes
// a 3 s tail): prod-b14's nine painted shots rendered 5.2 s each for 0.4-4.2 s kept, 46.5 s for 12 s (2026-10-10)
// Every film trims the same way (2026-10-10 evening, Alec: motion is inpainted to the soundtrack, so a tail past
// the cut is never seen, and RULES A5 has H3 stretching the action over an empty tail; launch films too, "it probably wouldn't matter"):
// the planner writes seconds = ceil(span + 0.3), so 9.9% of the 16 run-sheet painted films' frames fell past their cuts (5.9% after,
// ~$0.04 a film; launch films $0.04-0.06); every painted last row still ends at least 0.87 s before the render does (RULES ask 0.7 s).
if (process.env.EDIT_TRIM !== '0' && !plan.chain)
  for (const c of H3C) if (!c.videos.some((v) => v.includes('/footage/')) && c.span) {
    c.seconds = Math.min(+c.seconds, +(c.span + 0.3).toFixed(2));
    if (c.pins) c.pins = c.pins.filter((p) => +p.t < c.seconds);  // a pin past the shorter render would be clamped onto its last frame (comfy_r2v.py)
  }
for (const c of H3C) if (c.videos.length === 1 && c.videos[0].includes('/footage/') && c.span) c.seconds = +(c.span + 0.3).toFixed(2);  // no 2 s floor: a one-beat shot rendered at 0.88 s (22 frames) came out as close to its footage as the 2 s render (SSIM 0.85 vs 0.76 over the frames that play) in half the GPU time (2026-10-09)
// the frames join.mjs keeps of each clip: its span on the film's 24 fps grid
const keep = {}; { let t = 0; for (const c of plan.clips) { const a = Math.round(t * 24); t += c.span; keep[c.id] = Math.round(t * 24) - a; } }
// "zoom" on a one-shot footage clip ({to} pushes in from the frame as filmed, {from, to} pulls back; 1 = as filmed): the edit's zoom made of the
// shot's own frames, cropped and pinned every 0.2 s along an eased curve, fast at the start like the CapCut sources (2026-10-10: a last-frame
// pin alone held the shot and then snapped; a pin every 0.2 s followed a planned 1.0 -> 1.6 push within 0.01). It replaces the first-frame pin.
// "frame" ({x, y}: the centre of the film's frame on the shot, a share of its width and height; 2026-10-11, Alec: a wide podcast in a tall
// film, framed on whoever speaks): the shot's own frames are pinned cropped to the film's shape there, and H3 gets the whole shot as Video 1.
// A shot that also attaches a picture (someone in it becomes the character drawn there, a restyle) is never pinned to its own frames: they
// show the original person and H3 kept him (2026-10-11: Peter Griffin never replaced the Denver big man). Its "frame" crops the reference
// video itself to the film's shape instead, and its "zoom" pushes in on that point in the reference itself, the way a podcast shot is framed
// on its speaker (2026-10-11: wide broadcast shots left the player a small figure among ten and H3 could not redraw him as Peter Griffin;
// a close shot of one player swapped cleanly): {"to": 2} makes them twice as big for the whole shot, {"from": 1, "to": 2} pushes in (eased).
for (const c of H3C) if ((c.frame || c.zoom) && (c.images || []).length && c.videos.length === 1 && c.videos[0].includes('/footage/')) {
  const v = c.videos[0], fx = +(c.frame?.x ?? 0.5), fy = +(c.frame?.y ?? 0.5), A = ((r) => r[0] / r[1])((plan.ratio || '16:9').split(':').map(Number));
  const za = Math.max(1, +((c.zoom || {}).from ?? (c.zoom || {}).to ?? 1)), zb = Math.max(1, +((c.zoom || {}).to ?? 1));
  const [iw, ih] = execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', v]).toString().trim().split(',').map(Number);
  const bw = Math.min(iw, ih * A), bh = bw / A, bx = Math.max(0, Math.min(iw - bw, fx * iw - bw / 2)), by = Math.max(0, Math.min(ih - bh, fy * ih - bh / 2));  // the film's shape around the point
  const ev = (n) => 2 * Math.round(n / 2), lx = fx * iw - bx, ly = fy * ih - by, fps = 30, F = Math.max(1, Math.round(fps * +c.seconds));
  const zp = za === 1 && zb === 1 ? '' : `,fps=${fps},zoompan=z='${za}+(${(zb - za).toFixed(4)})*(1-pow(1-min(on/${F}\\,1)\\,2))':x='max(0\\,min(iw-iw/zoom\\,${lx.toFixed(1)}-iw/zoom/2))':y='max(0\\,min(ih-ih/zoom\\,${ly.toFixed(1)}-ih/zoom/2))':d=1:s=${ev(bw)}x${ev(bh)}:fps=${fps}`;
  const o = path.join(path.dirname(v), `${path.basename(v, '.mp4')}-framed-${fx}-${fy}${zp ? `-z${za}-${zb}` : ''}.mp4`);  // still under footage/: the steps below know it as footage
  if (!fs.existsSync(o)) execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', v, '-vf', `crop=${ev(bw)}:${ev(bh)}:${Math.round(bx)}:${Math.round(by)}${zp}`, '-c:v', 'libx264', '-crf', '16', '-an', o]);
  c.videos = [o]; c.frame = null; c.zoom = null;  // never pinned: the pins below would bring the original person back
}
for (const c of H3C) if ((c.zoom || c.frame) && c.videos.length === 1 && c.videos[0].includes('/footage/')) {
  const v = c.videos[0], D = +c.seconds, a = Math.max(1, +((c.zoom || {}).from ?? 1)), b = Math.max(1, +((c.zoom || {}).to ?? 1)), dir = path.join(run, 'render-gpu', 'zoom');
  const len = +execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', v]).toString(); fs.mkdirSync(dir, { recursive: true }); c.pins = [];
  for (let t = 0; t <= D - 0.05 + 1e-9; t += +(process.env.ZOOM_STEP || 0.2)) {  // ZOOM_STEP: seconds between zoom pins (each pin adds one latent frame of tokens to the render)
    const z = a + (b - a) * (1 - (1 - t / D) ** 2), fx = c.frame ? +(c.frame.x ?? 0.5) : null, fy = c.frame ? +(c.frame.y ?? 0.5) : null, A = ((r) => r[0] / r[1])((plan.ratio || '16:9').split(':').map(Number));  // the film's shape
    const o = path.join(dir, `${path.basename(v, '.mp4')}-${a}-${b}${c.frame ? `-${fx}-${fy}` : ''}-${t.toFixed(2)}.png`);
    const crop = c.frame ? `crop=min(iw\\,ih*${A.toFixed(5)})/${z.toFixed(4)}:min(iw\\,ih*${A.toFixed(5)})/${z.toFixed(4)}/${A.toFixed(5)}:max(0\\,min(iw-ow\\,${fx}*iw-ow/2)):max(0\\,min(ih-oh\\,${fy}*ih-oh/2))` : `crop=iw/${z.toFixed(4)}:ih/${z.toFixed(4)}`;
    if (!fs.existsSync(o)) execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-ss', String(Math.min(t, len - 0.05)), '-i', v, '-vf', crop, '-frames:v', '1', o]);
    c.pins.push({ t: +t.toFixed(2), image: o });
  }
}
// A live-action swap clip (render.json "swap": true: its shot of the footage as Video 1, real photos of whoever takes someone's place; FOOTAGE
// rule 3) opens on that shot's first frame with the
// swap already made (2026-10-12, Alec: "pin a start frame where the swap was made with nano banana", one per clip, not pins all through):
// Nano Banana edits the frame to the prompt's swap line (who becomes whom, each pointed at their photo) and the edit is pinned at t 0.
// A refused or failed edit leaves the clip as it was. SWAP_PIN=0 turns it off.
const isPhoto = (f) => /\/(refs|attached)\//.test(f);
const NB_RATIOS = ['1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9'];
const ratioOf = (f) => { const [w, h] = execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', f]).toString().trim().split(',').map(Number); return NB_RATIOS.reduce((b, r) => { const [x, y] = r.split(':').map(Number); return Math.abs(Math.log(x / y / (w / h))) < Math.abs(Math.log(b[0] / b[1] / (w / h))) ? [x, y] : b; }, [1, 1]).join(':'); };
if (process.env.SWAP_PIN !== '0') for (const c of H3C) {
  if (c.swap !== true || c.videos.length !== 1 || !c.videos[0].includes('/footage/') || !(c.images || []).some(isPhoto) || (c.pins || []).some((p) => +p.t === 0)) continue;
  // who becomes whom: MiniMax's layout (subject_definitions: "<Subject 1> is Kai Cenat, whose appearance comes from <Picture 1>: ..."),
  // or the older one-line form ("... becomes Kai Cenat (Image 1) ..."); Nano Banana sees the frame as Image 1 and the photos after it
  const L = fs.readFileSync(c.prompt, 'utf8').split('\n'), defs = L.filter((l) => /appearance comes from <Picture \d+>/.test(l));
  const swap = defs.length ? defs.join(' ').replace(/<Subject \d+> is /g, '').replace(/<Picture (\d+)>/g, (_, n) => `Image ${+n + 1}`).replace(/<Video \d+>/g, 'Image 1')
    : L.find((l) => /\bbecomes?\b[^.]*\bImage \d/.test(l))?.replace(/Image (\d+)/g, (_, n) => `Image ${+n + 1}`);
  if (!swap) continue;
  const dir = path.join(run, 'render-gpu', 'swap'), frame = path.join(dir, `${c.id}-frame0.png`); fs.mkdirSync(dir, { recursive: true });
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', c.videos[0], '-frames:v', '1', frame]);
  const refs = [frame, ...c.images], text = `Image 1 is one frame of a live-action film. Return this exact frame unchanged: the same framing, camera, place, light, and every other person and object in it, except this change: ${swap} Each new person has exactly the face, hair, skin tone and build of their picture, in the pose, size and place of the person they replace, photographed like the rest of the frame.`;
  const key = createHash('sha1').update([imageModel(), text, ...refs.map((f) => createHash('sha1').update(fs.readFileSync(f)).digest('hex'))].join('|')).digest('hex'), out = path.join(dir, `${c.id}-swapped-${key.slice(0, 8)}.png`);
  if (!fs.existsSync(out)) try {
    const ai = quotaWait(new GoogleGenAI({ vertexai: true, project: process.env.GOOGLE_VERTEX_PROJECT, location: process.env.GOOGLE_VERTEX_LOCATION || 'global', httpOptions: { retryOptions: { attempts: 6, initialDelay: 5, maxDelay: 60 } } }));
    const res = await ai.models.generateContent({ model: imageModel(), contents: [{ role: 'user', parts: [...refs.map((f) => ({ inlineData: { mimeType: /\.jpe?g$/i.test(f) ? 'image/jpeg' : 'image/png', data: fs.readFileSync(f).toString('base64') } })), { text }] }], config: { responseModalities: ['IMAGE'], imageConfig: { aspectRatio: ratioOf(frame), imageSize: '1K' } } });
    const part = res.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
    if (!part) throw new Error(`no image returned: ${res.candidates?.[0]?.finishReason ?? 'empty'}`);
    fs.writeFileSync(out, Buffer.from(part.inlineData.data, 'base64'));
  } catch (e) { console.log(`${c.id}: no swapped first frame (${String(e.message).slice(0, 160)}): renders without it`); continue; }
  c.pins = [{ t: 0, image: out }, ...(c.pins || [])]; console.log(`${c.id}: opens on its first frame with the swap made (${path.relative(run, out)})`);
}
// A one-shot zoom shot renders the smallest H3 length that holds the frames the join keeps (17k+5 frames: ComfyUI
// comfy_extras/nodes_minimax_h3.py align_frame_count) with no 0.3 s margin; a pin at the last rendered frame holds its end (the zoom
// curve's crop). Since 2026-10-10 (the morning study's Cut 1: 13 same-seed zoom-shot renders matched their footage as before).
const grid = (n) => { n = Math.max(5, n); while (n % 17 !== 5) n++; return n; };  // the frames H3 renders for n asked (comfy_r2v.py, V1's node 131)
if (!plan.chain) {
  for (const c of H3C) if (c.zoom && c.videos.length === 1 && c.videos[0].includes('/footage/') && c.span && !(c.images || []).length) {
    const K = keep[c.id], F = grid(Math.max(6, K)), D = +c.seconds; if (!(K > 0) || F >= grid(Math.round(D * 24))) continue;
    const v = c.videos[0], te = +((F - 1) / 24).toFixed(3), len = +execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', v]).toString();
    c.pins = (c.pins || []).filter((p) => Math.round(+p.t * 24) <= F - 1);
    if (!c.pins.some((p) => Math.round(+p.t * 24) >= K - 1)) {
      // the same eased curve, planned over the old length, so the kept frames' zoom is unchanged
      const a = Math.max(1, +(c.zoom.from ?? 1)), b = Math.max(1, +(c.zoom.to ?? 1)), z = a + (b - a) * (1 - (1 - te / D) ** 2);
      // a framed shot's end pin is cropped like its other pins; uncropped, comfy_r2v.py centre-cropped it and the shot ended on the
      // middle of the room (2026-10-11: two podcast shots framed on their speakers ended on the empty middle, a jump at the cut)
      const A = ((r) => r[0] / r[1])((plan.ratio || '16:9').split(':').map(Number)), fx = +(c.frame?.x ?? 0.5), fy = +(c.frame?.y ?? 0.5);
      const crop = c.frame ? `crop=min(iw\\,ih*${A.toFixed(5)})/${z.toFixed(4)}:min(iw\\,ih*${A.toFixed(5)})/${z.toFixed(4)}/${A.toFixed(5)}:max(0\\,min(iw-ow\\,${fx}*iw-ow/2)):max(0\\,min(ih-oh\\,${fy}*ih-oh/2))` : `crop=iw/${z.toFixed(4)}:ih/${z.toFixed(4)}`;
      const o = path.join(run, 'render-gpu', 'zoom', `${path.basename(v, '.mp4')}-${a}-${b}${c.frame ? `-${fx}-${fy}` : ''}-${te.toFixed(3)}.png`); fs.mkdirSync(path.dirname(o), { recursive: true });
      if (!fs.existsSync(o)) execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-ss', String(Math.min(te, len - 0.05)), '-i', v, '-vf', crop, '-frames:v', '1', o]);
      c.pins.push({ t: te, image: o });
    }
    c.seconds = +(F / 24).toFixed(4);
  }
}
// NOVID=1: no reference videos — the rows carry the motion (the Opus proofs held without them) and no other product's UI can
// leak in. Its prompts go to render-novid/, its clips to render-gpu-novid/, the film to final-novid.mp4.
const NOVID = process.env.NOVID === '1';
if (NOVID) for (const c of H3C) {
  c.videos = [];
  const f = path.join(run, 'render-novid', `${c.id}.txt`); fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, fs.readFileSync(c.prompt, 'utf8').replace(/^Video \d+ is .*\n+/gm, '')); c.prompt = f;
}
// Lyric videos: prompts carry [Ln] ids; H3 gets the real words (lyrics.json from agent/h3film/lyric-ids.py).
const LYR = fs.existsSync(path.join(run, 'lyrics.json')) ? JSON.parse(fs.readFileSync(path.join(run, 'lyrics.json'), 'utf8')) : null;
if (LYR) for (const c of H3C) {
  const f = path.join(run, 'prompts-lyrics', `${c.id}.txt`); fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, fs.readFileSync(c.prompt, 'utf8').replace(/\[L(\d+)(?::(\d+)(?:-(\d+))?)?\]/g, (k, n, a, b) => { const w = LYR[`[L${n}]`]; return w == null ? k : a ? w.split(' ').slice(a - 1, +(b || a)).join(' ') : w; })); c.prompt = f;
}
// Painted films (skills/h3-film/PAINTED.md): pool stills are STYLE references, not content, so an arrival row names no
// Image by design; the card's ban line is their leak guard. The check is for launch films' product stills only.
const PAINTED = plan.kind === 'painted' || plan.clips.some((c) => (c.videos || []).some((v) => v.includes('/footage/')));  // an edit of footage is never a launch film, even when its render.json forgets its kind (AMV v3m-r02)
// The H3 node labels its references <Picture i> / <Video k> / <Audio j> and says "Use the same tags when prompting" (ComfyUI
// comfy_extras/nodes_minimax_h3.py, MiniMaxH3ReferenceToVideo); our prompts say "Image N" / "Video N" / "Audio N" (fal's names). A swap
// clip ("swap": true) gets the node's own tags so each person's words land on their photo (2026-10-12, the swap test); every other clip keeps its words
// until the tags are tested on them. TAGS=all tags every clip, TAGS=0 none.
const TAGS = process.env.TAGS || 'swap';
for (const c of H3C) if (TAGS === 'all' || (TAGS === 'swap' && c.swap === true)) {
  const f = path.join(run, 'prompts-tagged', `${c.id}.txt`); fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, fs.readFileSync(c.prompt, 'utf8').replace(/(?<!<)\b(Image|Video|Audio) (\d+)\b/g, (_, k, n) => `<${k === 'Image' ? 'Picture' : k} ${n}>`)); c.prompt = f;
}
const gaps = PAINTED ? [] : H3C.flatMap((c) => uncoveredRows(fs.readFileSync(c.prompt, 'utf8')).map((r) => `${c.id}: ${r.slice(0, 140)}`));
if (gaps.length) { console.log(`REFUSED: rows bring in something no still shows (H3 would paint it from the reference video):\n${gaps.join('\n')}`); process.exit(1); }
// The user's own photos may go to H3 (2026-10-12, Alec: no redraw first): a live-action film or an edit of real footage attaches them
// themselves, a drawn film the stills drawn from them (skills/h3-film/REFERENCES.md). The refusal of attached/ files is gone: on our own
// GPUs no face filter refuses a real face, and a photo in a drawn film is the planner's rule to keep.
// A clip is reused only when it was rendered from exactly these inputs: its prompt text, every image, video and audio file (by
// content), its length, ratio and render size, and for a chained clip the clip before it (key in <clip>.key). A rewritten prompt
// or a remade still renders again and the old clip is kept as <clip>.stale-<time> (it used to reuse whatever was there, open
// since 2026-09-30). A clip from before keys: a GPU clip carries its prompt in its metadata (ComfyUI's graph), so it is kept
// only if that is the current prompt; a fal clip is kept as before.
const sha = (f) => createHash('sha1').update(fs.readFileSync(f)).digest('hex'), keys = {};
const keyOf = (c, tail) => createHash('sha1').update(JSON.stringify({ prompt: fs.readFileSync(c.prompt, 'utf8'), images: (c.images || []).map(sha), videos: (c.videos || []).map(sha),
  audio: c.audio && sha(c.audio), first: c.first && sha(c.first), last: c.last && sha(c.last), ...(c.pins?.length ? { pins: c.pins.map((p) => [p.t, p.video ? [sha(p.video), p.at || 0] : sha(p.image)]) } : {}), tail: tail && sha(tail.replace(/\.tail\d+s\.mp4$/, '.mp4')),
  seconds: c.seconds, expansion: c.expansion, ratio: plan.ratio, rows: process.env.GPU_ROWS, r2v: process.env.R2V, footrows: footRows(c) || undefined })).digest('hex');  // r2v, footrows: unset leaves every key as it was
const graph = (f) => { try { return JSON.parse(JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format_tags=prompt', '-of', 'json', f]).toString()).format.tags.prompt); } catch { return null; } };
const reuse = (file, keyFile, key, c) => fs.existsSync(keyFile) ? fs.readFileSync(keyFile, 'utf8').trim() === key : ((g) => !g || g['138']?.inputs?.value === fs.readFileSync(c.prompt, 'utf8'))(graph(file));
// The render cap (H3_BUDGET_USD, default 5) is priced at fal's H3 rate although the clips render on Modal: $0.05 a second of each clip
// (at least 5 s) and of each reference video (fal bills those too, at the output rate: matched to the cent on its usage export,
// 2026-09-29), + the previous clip's 3 s tail on chained clips, + $0.08 per reference image past the first five (fal's price page).
const secs = (f) => +execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString() || 0;
const cost = plan.clips.map((c, i) => [c, i]).filter(([c]) => !c.code && !c.footage).reduce((a, [c, i]) => a + 0.05 * (Math.max(5, c.seconds) + c.videos.reduce((t, v) => t + secs(v), 0) + (plan.chain && i ? 3 : 0)) + 0.08 * Math.max(0, (c.images || []).length - 5), 0), cap = +(process.env.H3_BUDGET_USD || 5);
if (cost > cap + 1e-9) { console.log(`REFUSED: renders cost $${cost.toFixed(2)}, budget $${cap}`); process.exit(1); }
const t0 = Date.now();
// Each H3 clip is one ComfyUI job (research/h3/runpod/comfy_r2v.py) on Modal (research/h3/modal_h3.py, which scales out per call): the
// production R2V graph, style and motion clips sent at 360 rows.
const renderGpu = (c, tail) => new Promise((resolve, reject) => {
  if (c.first || c.last) return reject(new Error(`${c.id}: frame mode (render.json first/last) does not render on Modal: pin those frames instead (pins)`));
  const dir = path.join(run, NOVID ? 'render-gpu-novid' : 'render-gpu'), out = path.join(dir, `${c.id}.mp4`);  // NOVID renders apart, never reusing the with-video clips
  const keyFile = out.replace(/\.mp4$/, '.key'), key = keys[c.id] = keyOf(c, tail);
  if (fs.existsSync(out)) {
    if (reuse(out, keyFile, key, c)) { fs.writeFileSync(keyFile, key); return resolve(out); }
    fs.renameSync(out, `${out}.stale-${Date.now()}`); console.log(`${c.id}: its inputs changed since it was rendered: rendering it again`);
  }
  fs.mkdirSync(dir, { recursive: true });
  const cj = path.join(dir, `${c.id}.json`);
  fs.writeFileSync(cj, JSON.stringify({ ...c, videos: [...(tail ? [tail] : []), ...(c.videos || [])] }));
  const args = [path.join(REPO, 'research/h3/runpod/comfy_r2v.py'), `--clip=${cj}`, out, '--refh=360',
    `--ratio=${plan.ratio || '16:9'}`, ...(process.env.GPU_ROWS ? [`--rows=${process.env.GPU_ROWS}`] : []),
    ...(footRows(c) ? [`--footrows=${footRows(c)}`] : []),  // the user's footage sent at most footRows(c) rows (comfy_r2v.py --footrows)
    ...(['v2', 'v2-shipped', 'v2-sage'].includes(process.env.R2V) ? [`--${process.env.R2V}`] : []),  // R2V=v2: comfy_r2v.py stops with a message (the V2 graph and its Modal app are not in this repo)
    ...((process.env.H3_AUDIO_MODE ?? 'inpaint') !== 'reference' ? [`--audio=${process.env.H3_AUDIO_MODE ?? 'inpaint'}`] : []), ...((c.seed ?? process.env.H3_SEED) ? [`--seed=${c.seed ?? process.env.H3_SEED}`] : []), ...(process.env.H3_FOOTAGE_MODE ? [`--footage=${process.env.H3_FOOTAGE_MODE}`] : [])];  // the user's footage kept on the clip's own timeline (comfy_r2v.py --footage)  // GPU_ROWS=704: render taller than 480; audio inpaint by default (comfy_r2v.py; H3_AUDIO_MODE=reference for the old mode, Alec 2026-10-08); H3_SEED or a clip's own render.json "seed": fixed noise for A/B tests
  const p = spawn(path.join(REPO, '.venv/bin/python'), args, { stdio: ['ignore', 'pipe', 'pipe'] }); let log = '';
  p.stdout.on('data', (d) => (log += d)); p.stderr.on('data', (d) => (log += d));
  p.on('close', (code) => { fs.writeFileSync(path.join(run, `render-${c.id}.log`), log); if (fs.existsSync(out)) fs.writeFileSync(keyFile, key); fs.existsSync(out) ? resolve(out) : reject(new Error(`${c.id} failed on modal: ${log.trim().split('\n').pop() || 'code ' + code}`)); });
});
// A clip H3 drew boxed (black bars on both sides, agent/h3film/boxed-check.py) is only logged, never rendered again (2026-10-09: the
// hidden retake re-rendered it up to twice with new seeds; its main cause, a wide footage reference sent uncropped, is fixed at the input).
const boxed = (f) => { try { execFileSync(path.join(REPO, '.venv/bin/python'), [path.join(REPO, 'agent/h3film/boxed-check.py'), f]); return false; } catch (e) { return e.status === 2; } };
const logged = (render) => async (c, ...a) => { const f = await render(c, ...a); if (boxed(f)) console.log(`${c.id} came back boxed (black bars on both sides)`); return f; };
const asIs = (render) => (c, ...a) => c.code || c.footage ? Promise.resolve(c.code || c.footage) : render(c, ...a);  // a code or footage clip renders nothing here
const renderGpuOk = asIs(logged(renderGpu));
// Launch films: every clip at once. Painted films (chain): in order, each clip gets the previous one's tail as Video 1.
// A shot that runs on across a seam (2026-10-11, Alec on v51-t1: "exact last frame, first frame pinning if it's supposed to be continuous across clips"): a clip whose
// first pin (t 0) is the same picture as the previous clip's last pin renders after it, that pin swapped for the last frame the join keeps of the previous clip (keep:
// the film's 24 fps grid). Rendered apart, both clips started the shot from the same master still and the picture jumped back at both seams of the phone call.
// Every other clip still renders at once.
const lastPin = (c) => (c.pins || []).reduce((m, p) => (!m || +p.t > +m.t ? p : m), null);
const runsOn = plan.clips.map((c, i) => { const a = plan.clips[i - 1], p = a && lastPin(a), q = (c.pins || []).find((x) => +x.t === 0); return !!(!plan.chain && keep[a?.id] > 0 && H3C.includes(a) && H3C.includes(c) && p?.image && q?.image && sha(p.image) === sha(q.image)); });
const P = [], after = (i, render) => (P[i] = (runsOn[i] ? P[i - 1].then((f) => {
  const a = plan.clips[i - 1], c = plan.clips[i], k = keep[a.id] - 1, o = path.join(path.dirname(f), 'chain', `${a.id}-frame${k}.png`); fs.mkdirSync(path.dirname(o), { recursive: true });
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', f, '-vf', `select=eq(n\\,${k})`, '-frames:v', '1', o]);  // frame k by its index, exact
  c.pins = c.pins.map((p) => (+p.t === 0 ? { t: 0, image: o } : p)); console.log(`${c.id}: runs on from ${a.id}: its first frame is ${a.id}'s frame ${k}, the last the film shows`);
}) : Promise.resolve()).then(render));
const files = [];
if (plan.chain) for (const [i, c] of plan.clips.entries()) files.push(await renderGpuOk(c, i ? clipTail(files[i - 1], 3) : null));
else files.push(...await Promise.all(plan.clips.map((c, i) => after(i, () => renderGpuOk(c, null)))));  // Modal scales out per call
const probe = (f, k) => execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', `stream=${k}`, '-of', 'csv=s=x:p=0', f]).toString().trim();
const ref = files[plan.clips.findIndex((c) => !c.code && !c.footage)] ?? files[0], fps = probe(ref, 'r_frame_rate');
// a film of footage or code clips only has no H3 clip to take its size from: the size H3 renders its ratio at (comfy_r2v.py)
const h3size = (ratio = '16:9') => { const R = +process.env.GPU_ROWS || 0, H = R || 480, W = R ? Math.round(R * 16 / 9 / 32) * 32 : 832;
  if (ratio === '16:9' || ratio === '9:16') return ratio === '16:9' ? `${W}x${H}` : `${H}x${W}`;
  const [a, b] = ratio.split(':').map(Number), k = Math.sqrt(W * H / (a * b)); return `${Math.round(a * k / 32) * 32}x${Math.round(b * k / 32) * 32}`; };
const size = MAPC ? probe(files[plan.clips.indexOf(MAPC)], 'width,height') : plan.clips.some((c) => !c.code && !c.footage) ? probe(ref, 'width,height') : h3size(plan.ratio);  // a film with map shots keeps them at their own size (exact type, coastlines); its H3 clips are scaled up to it
// code and footage clips take the H3 clips' size, frame rate and the clip's seconds (the last frame held if short), video only:
// a code clip fitted (never stretched), a footage clip filling the frame, centre-cropped, unless it asks for its whole picture
// ("fit": "whole": on black, as a meme edit shows a show's 16:9 picture in a tall frame)
for (const [i, c] of plan.clips.entries()) if (c.code || c.footage) {
  const [w, h] = size.split('x'), o = path.join(run, 'render-code', `${c.id}.mp4`); fs.mkdirSync(path.dirname(o), { recursive: true });
  const fit = c.code || c.fit === 'whole' ? `decrease,pad=${w}:${h}:(ow-iw)/2:(oh-ih)/2` : c.frame ? `increase,crop=${w}:${h}:max(0\\,min(iw-ow\\,${+(c.frame.x ?? 0.5)}*iw-ow/2)):max(0\\,min(ih-oh\\,${+(c.frame.y ?? 0.5)}*ih-oh/2))` : `increase,crop=${w}:${h}`;  // a clean shot's "frame" is cut exactly by code
  const za = Math.max(1, +((c.zoom || {}).from ?? 1)), zb = Math.max(1, +((c.zoom || {}).to ?? 1)), F = Math.max(1, Math.round(fps * c.seconds));
  const zp = c.footage && c.zoom ? `,zoompan=z='${za}+(${(zb - za).toFixed(4)})*(1-pow(1-min(on/${F}\\,1)\\,2))':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=${w}x${h}:fps=${fps}` : '';
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', c.code || c.footage, '-vf', `scale=${w}:${h}:force_original_aspect_ratio=${fit},setsar=1,fps=${fps}${zp},tpad=stop_mode=clone:stop_duration=${c.seconds}`, '-t', String(c.seconds), '-an', '-c:v', 'libx264', '-crf', '16', '-pix_fmt', 'yuv420p', o]);
  files[i] = o;
}
// Lyric subtitles (2026-10-11, Alec: a reference whose lyrics are plain subtitles should get them drawn by code): a { "lyrics": true }
// caption is every sung line in the film's window, its exact words (lyrics.json) at its sung times (lyrics-ids.vtt, less the song's
// start), held until the next line; [Ln] ids in any caption's text get their words.
const SONG = fs.existsSync(path.join(run, 'soundtrack', 'song.json')) ? JSON.parse(fs.readFileSync(path.join(run, 'soundtrack', 'song.json'), 'utf8')) : null;
const vttSecs = (x) => x.split(":").reduce((s, v) => s * 60 + +v, 0), filmLen = plan.clips.reduce((s, c) => s + c.span, 0);
const cues = SONG && fs.existsSync(path.join(run, 'lyrics-ids.vtt')) ? [...fs.readFileSync(path.join(run, 'lyrics-ids.vtt'), 'utf8').matchAll(/([\d:.]+) --> ([\d:.]+)\s*\n(\[L\d+\])/g)].map(([, a, b, id]) => ({ from: vttSecs(a) - SONG.songStart, to: vttSecs(b) - SONG.songStart, id })).filter((q) => q.to > 0 && q.from < filmLen) : [];
const words = (t) => String(t ?? '').replace(/\[L\d+\]/g, (k) => LYR?.[k] ?? k);
// { "narration": true } (2026-10-11, Alec: recap shorts caption their voiceover): every spoken line of the soundtrack, a few words at a
// time ("words", default 3; a line with no spaces by 8 characters) across its spoken time, each chunk's share by its length
const ST = fs.existsSync(path.join(run, 'soundtrack', 'soundtrack.json')) ? JSON.parse(fs.readFileSync(path.join(run, 'soundtrack', 'soundtrack.json'), 'utf8')) : null;
const said = (n) => (ST?.lines || []).filter((l) => l?.text && l.at != null && l.end > l.at).flatMap((l) => {
  const w = l.text.trim().split(/\s+/), parts = w.length > 1 ? Array.from({ length: Math.ceil(w.length / n) }, (_, i) => w.slice(i * n, i * n + n).join(' ')) : l.text.match(/.{1,8}/gu);
  const tot = parts.reduce((s, p) => s + p.length, 0); let t = l.at;
  return parts.map((p) => { const d = ((l.end - l.at) * p.length) / tot, c = { text: p, from: +t.toFixed(2), to: +(t + d).toFixed(2) }; t += d; return c; });
});
for (const [, k, v] of (fs.existsSync(path.join(REPO, '.env.local')) ? fs.readFileSync(path.join(REPO, '.env.local'), 'utf8') : '').matchAll(/^(?:export\s+)?([A-Z_][A-Z0-9_]*)=(.*)$/gm)) process.env[k] ??= v.trim().replace(/^(["'])(.*)\1$/, '$2');
const heardWords = (plan.captions || []).some((c) => c.speech) && plan.music ? await (async () => {
  const cache = path.join(run, 'speech-words.json'); if (fs.existsSync(cache)) return JSON.parse(fs.readFileSync(cache, 'utf8'));
  const form = new FormData(); form.append('model_id', process.env.ELEVENLABS_STT_MODEL || 'scribe_v2'); form.append('file', new Blob([fs.readFileSync(plan.music)]), path.basename(plan.music));
  const r = await fetch('https://api.elevenlabs.io/v1/speech-to-text', { method: 'POST', headers: { 'xi-api-key': process.env.ELEVENLABS_API_KEY }, body: form });
  if (!r.ok) { console.log(`speech captions: speech to text failed (${r.status} ${(await r.text()).slice(0, 120)}): this film has no speech captions; a re-render tries again`); return []; }  // never saved as "no words"
  const w = ((await r.json()).words || []).filter((x) => x.type === 'word').map((x) => ({ text: x.text, at: x.start, end: x.end })); fs.writeFileSync(cache, JSON.stringify(w)); return w;
})() : [];
const speech = (n) => heardWords.flatMap((x, i, a) => i % n ? [] : [{ text: a.slice(i, i + n).map((y) => y.text).join(' '), from: x.at, to: Math.min((a[i + n - 1] || a.at(-1)).end + 0.15, a[i + n]?.at ?? Infinity) }]);
const captions = (plan.captions || []).flatMap((c) => c.speech ? speech(c.words || 3).map((q) => ({ ...c, ...q })) : c.narration ? said(c.words || 3).map((q) => ({ ...c, ...q })) : c.lyrics ? cues.map((q, i) => ({ ...c, text: words(q.id), from: Math.max(0, q.from), to: Math.min(filmLen, Math.max(q.from + 0.5, Math.min(cues[i + 1]?.from ?? Infinity, q.to + 0.8))) })) : [{ ...c, text: words(c.text) }]);
const r = await joinFilm({ clips: plan.clips.map((c, i) => ({ file: files[i], seconds: c.span })), music: plan.music, out: path.join(run, NOVID ? 'final-novid.mp4' : 'final-gpu.mp4'), size, target: +process.env.H3_DURATION || undefined, captions });  // the user's duration: the file is exactly that long (join.mjs)
fs.writeFileSync(path.join(run, 'spend.json'), JSON.stringify({ spent: cost, cap }));
// manifest.json (agent/h3film/manifest.py): how each clip was rendered: backend, size, its prompt, input key and seed (read
// from the clip's own metadata, ComfyUI's graph).
const mf = path.join(run, 'manifest.json'); let m = {}; try { m = JSON.parse(fs.readFileSync(mf, 'utf8')); } catch {}
m.render = { at: new Date().toISOString(), backend: 'modal', res: null, rows: +(process.env.GPU_ROWS || 480), novid: NOVID, final: r.out, size,
  clips: plan.clips.map((c, i) => ({ id: c.id, file: files[i], code: c.code, footage: c.footage, prompt: c.prompt, prompt_chars: c.prompt ? fs.readFileSync(c.prompt, 'utf8').length : 0, images: (c.images || []).length, videos: (c.videos || []).length, audio: !!c.audio, seconds: c.seconds, span: c.span, key: keys[c.id], seed: ((g) => g?.['129']?.inputs?.noise_seed ?? g?.['25']?.inputs?.noise_seed)(graph(files[i])) ?? null })) };  // '25': R2V V2's noise node
fs.writeFileSync(mf, JSON.stringify(m, null, 1));
// the line starts "rendered N clips in X s" as before: agent/scorecard/clean_runs.py reads it from the styles log
console.log(`rendered ${files.length} clips in ${((Date.now() - t0) / 1000).toFixed(0)} s${H3C.length < files.length ? ` (${files.length - H3C.length} code or footage clips, no H3 call)` : ''}, on Modal → ${r.out}`);
