// Soundtrack for the H3 rig: VO lines (Magic Hour or ElevenLabs, mhSay below) over a ducked bed, passed as reference_audio.
// Final answer 2026-09-08: H3 will not speak over a supplied track (two silent takes), so the VO goes in the mix. H3 adds SFX only.
import fs from 'node:fs'; import path from 'node:path'; import { spawnSync } from 'node:child_process';
const HERE = path.dirname(new URL(import.meta.url).pathname);
// a dropped connection ("fetch failed") killed a whole film on 2026-10-09: retry network errors, never HTTP errors
const fetch = async (u, o, n = 3) => { try { return await globalThis.fetch(u, o); } catch (e) { if (n <= 1) throw e; await new Promise((r) => setTimeout(r, 3000)); return fetch(u, o, n - 1); } };
export const MUSIC_DIR = path.resolve(HERE, '../../agent/music');
export const MUSIC = fs.readdirSync(MUSIC_DIR).sort().filter((f) => f.endsWith('.mp3')).map((f) => f.slice(0, -4));
// The voice shelf. A film's narrator is the house voice; a voice that belongs to somebody ON SCREEN must
// match that person, so the caller picks (2026-09-19: a male narrator read a woman's line in her own ad).
export const VOICES = {
  narrator: 'dXtC3XhB9GtPusIpNtQx',   // male, warm, unhurried — the house narrator
  'narrator-f': 'EXAVITQu4vr4xnSDxMaL', // female, warm, unhurried — the same read, other voice
  'young-f': 'cgSgspJ2msm6clMCkdW9',    // female, young, bright — a person on screen, casual
  'young-m': 'TX3LPaxmHKxFdv7VOQHJ',    // male, young, bright — a person on screen, casual
};
const VOICE = process.env.ELEVENLABS_VOICE_ID || VOICES.narrator;
const ff = (args) => { const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', ...args], { encoding: 'utf8' }); if (r.status) throw new Error(r.stderr); };
const readable = (f) => spawnSync('ffprobe', ['-v', 'error', f]).status === 0;
const hasAudio = (f) => !!spawnSync('ffprobe', ['-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', f], { encoding: 'utf8' }).stdout.trim();
// A mistake in the call (fixable: the session corrects it and calls again) vs a provider or ffmpeg failure, which stops the run
// (research/h3/mcp.mjs): a film is never made without the voice or music it asked for.
const fix = (msg) => Object.assign(new Error(msg), { fixable: true });
const dur = (f) => +spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f], { encoding: 'utf8' }).stdout;

// musicPrompt: generate the bed with ElevenLabs Music (POST /v1/music, instrumental) instead of picking from agent/music.
// Bed loudness is normalised to BED_MEAN dB (mean, before ducking) whatever the source, so a soft generated underscore sits
// as far under the voice as a loud library track. parts: clip lengths in seconds for multi-clip films -> part_N.mp3 files.
const BED_MEAN = -22, VO_MEAN = -20;
const meanDb = (f) => +(spawnSync('ffmpeg', ['-i', f, '-af', 'volumedetect', '-f', 'null', '-'], { encoding: 'utf8' }).stderr.match(/mean_volume: (-?[\d.]+)/)?.[1] ?? -20);
// The VO provider is VOICE_PROVIDER: magichour (default since 2026-10-07, the manager's ask) or elevenlabs (every film before).
// Magic Hour's voice generator has only celebrity and character voices, so its AI Voice Cloner reads each line in a shelf
// voice from a clean sample of it, voices/<voice>.mp3 (that ElevenLabs voice's own reads). 0.1 credits a character. The read
// is set to its sample's mean loudness, so the bed sits under it as under ElevenLabs. Docs: docs.magichour.ai/api-reference/
// audio-projects/ai-voice-cloner, audio-projects/get-audio-details, files/generate-asset-upload-urls.
// A line with a `speaker` is read by one of Magic Hour's AI Voice Generator presets (docs.magichour.ai/api-reference/audio-projects/
// ai-voice-generator: text + voice_name, 1,266 celebrity and character voices, list in voices/mh-presets.json): character dialogue
// with accents and personalities, which the cloner (one sample's voice) and the four shelf voices cannot do.
export const MH_PRESETS = JSON.parse(fs.readFileSync(path.join(HERE, 'voices', 'mh-presets.json'), 'utf8'));
// Magic Hour's voices (presets and shelf clones) speak only these ten languages (its help centre's list); any other comes out garbled
// (2026-10-11, x21: Hindi read by Morgan Freeman, Jennifer Coolidge and the young-m clone came back from speech to text as Dutch and
// English gibberish). A film in another language is read in ElevenLabs (eleven_v4: 94 languages) by voices native in it, from
// voices/native.json: ElevenLabs Voice Library voices (GET /v1/shared-voices?language=hi, most used, standard rate; usable without
// adding them), each with what it fits, and one per shelf role; a language with no list is read by the shelf voices themselves.
export const MH_LANGS = ['en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'zh', 'ko'];   // Japanese (which Magic Hour speaks) is read by native voices/native.json ones: its presets hold almost no native Japanese speaker (2026-10-11)
export const NATIVE = JSON.parse(fs.readFileSync(path.join(HERE, 'voices', 'native.json'), 'utf8'));
export const nativeList = () => Object.entries(NATIVE).map(([k, n]) => `${n.language} ("${k}"): ${Object.entries(n.voices).map(([v, { about }]) => `"${v}" (${about})`).join(', ')}`).join('; ');
export const elVoice = (lang, name) => NATIVE[lang]?.voices[name]?.id || NATIVE[lang]?.voices[NATIVE[lang].roles[name]]?.id || VOICES[name];  // a speaker or a shelf role
async function mhPreset(text, voiceName, file) {
  const H = { Authorization: `Bearer ${process.env.MAGIC_HOUR_API_KEY}`, 'content-type': 'application/json' };
  const call = async (u, o) => { const r = await fetch(`https://api.magichour.ai/v1/${u}`, { headers: H, ...o }); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(`magic hour preset voice ${r.status}: ${JSON.stringify(j).slice(0, 300)}`); return j; };
  const { id } = await call('ai-voice-generator', { method: 'POST', body: JSON.stringify({ name: `vo ${path.basename(file)}`, style: { prompt: text, voice_name: voiceName } }) });
  for (const t0 = Date.now(); Date.now() - t0 < 300e3; await new Promise((ok) => setTimeout(ok, 1000))) {
    const p = await call(`audio-projects/${id}`);
    if (p.status === 'error' || p.status === 'canceled') throw new Error(`magic hour preset voice ${p.status}: ${JSON.stringify(p.error ?? p).slice(0, 300)}`);
    if (p.status !== 'complete') continue;
    const raw = `${file}.dl`; fs.writeFileSync(raw, Buffer.from(await (await fetch(p.downloads[0].url)).arrayBuffer()));
    // at the narration's level (the shelf clones read at about -18 LUFS): the presets come back anywhere from -33 to -20 LUFS, and the
    // quiet ones sank under the ducked music (fruit v2-r01, 2026-10-09: "can't really hear it over the music")
    ff(['-i', raw, '-af', 'loudnorm=I=-18:TP=-1.5', '-ar', '44100', '-b:a', '128k', file]); fs.rmSync(raw); return;
  }
  throw new Error('magic hour preset voice: no read after 5 min');
}
async function mhSay(text, voice, file) {
  const H = { Authorization: `Bearer ${process.env.MAGIC_HOUR_API_KEY}`, 'content-type': 'application/json' };
  const call = async (u, o) => { const r = await fetch(`https://api.magichour.ai/v1/${u}`, { headers: H, ...o }); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(`magic hour voice ${r.status}: ${JSON.stringify(j).slice(0, 300)}`); return j; };
  const sample = path.join(HERE, 'voices', `${voice}.mp3`); if (!fs.existsSync(sample)) throw new Error(`no voice sample for "${voice}": ${sample}`);
  const { items: [up] } = await call('files/upload-urls', { method: 'POST', body: JSON.stringify({ items: [{ type: 'audio', extension: 'mp3' }] }) });
  if (!(await fetch(up.upload_url, { method: 'PUT', body: fs.readFileSync(sample) })).ok) throw new Error('magic hour voice: sample upload failed');
  const { id } = await call('ai-voice-cloner', { method: 'POST', body: JSON.stringify({ name: `vo ${path.basename(file)}`, assets: { audio_file_path: up.file_path }, style: { prompt: text } }) });
  for (const t0 = Date.now(); Date.now() - t0 < 300e3; await new Promise((ok) => setTimeout(ok, 1000))) {
    const p = await call(`audio-projects/${id}`);
    if (p.status === 'error' || p.status === 'canceled') throw new Error(`magic hour voice ${p.status}: ${JSON.stringify(p.error ?? p).slice(0, 300)}`);
    if (p.status !== 'complete') continue;
    const raw = `${file}.dl`; fs.writeFileSync(raw, Buffer.from(await (await fetch(p.downloads[0].url)).arrayBuffer()));
    ff(['-i', raw, '-af', `volume=${(meanDb(sample) - meanDb(raw)).toFixed(1)}dB`, '-ar', '44100', '-b:a', '128k', file]); fs.rmSync(raw);
    return;
  }
  throw new Error('magic hour voice: no read after 5 min');
}
// Painted films: move every clip seam that falls inside a narration line to the middle of the nearest pause between lines
// (or before the first / after the last), keeping each clip 4–15 s and the film's length. A seam already in a pause stays.
// Gemini re-called make_soundtrack in 12 of 16 runs only to move seams (2026-10-04 audit; replayed on 14 runs: one call suffices).
function snapSeams(parts, placed, duration) {
  if (!placed.length || parts.length < 2) return parts;
  const gaps = placed.map((p, i) => [i ? placed[i - 1].end : 0, p.at]).concat([[placed.at(-1).end, duration]]);
  const r2 = (x) => Math.round(x * 100) / 100, n = parts.length, out = []; let prev = 0, want = 0;
  for (let k = 0; k < n - 1; k++) {
    want += parts[k]; const left = n - 1 - k;
    const ok = (c) => c - prev >= 4 && c - prev <= 15 && duration - c >= 4 * left && duration - c <= 15 * left;
    const cands = gaps.map(([a, b]) => (want >= a && want <= b ? want : (a + b) / 2)).filter(ok);
    if (!cands.length) { const i = placed.findIndex((l) => want > l.at && want < l.end); throw fix(`the seam at ${want.toFixed(1)} s falls inside line ${i + 1} and no pause near it leaves every clip 4–15 s long: shorten that line or move it`); }
    const c = r2(cands.reduce((m, x) => (Math.abs(x - want) < Math.abs(m - want) ? x : m)));
    out.push(r2(c - prev)); prev = c;
  }
  return [...out, r2(duration - prev)];
}
// Beat grid of whatever the film plays (beats: true, films with the user's footage): research/tools/analyze_music.py in its light
// mode (madmom, ALLIN1=0, ~6 s a 30 s track; Alec's ear test 2026-10-08 heard no difference from allin1). `offset` = where the
// film starts in that file; times come back in film seconds, inside [0, duration).
const musicJson = (file) => { if (!fs.existsSync(`${file}.music.json`)) spawnSync(path.resolve(HERE, '../../.venv/bin/python'), [path.resolve(HERE, '../tools/analyze_music.py'), file], { env: { ...process.env, ALLIN1: '0' }, stdio: 'ignore' }); return JSON.parse(fs.readFileSync(`${file}.music.json`, 'utf8')); };
function beatGrid(file, offset, duration) {
  try {
    const m = musicJson(file), w = (ts) => (ts || []).map((t) => +(t - offset).toFixed(2)).filter((t) => t >= 0 && t < duration);
    return { bpm: m.bpm, beats: w(m.beats), downbeats: w(m.downbeats), energy: (m.energy || m.segments || []).map((e) => ({ label: e.label, start: +Math.max(0, e.start - offset).toFixed(2), end: +Math.min(duration, e.end - offset).toFixed(2) })).filter((e) => e.end > e.start) };
  } catch { return undefined; }
}
// A song or the user's music with no start given opens on its strongest part (2026-10-09: edits played their song's quiet
// intro from 0 s): of the windows starting where one of analyze_music.py's per-bar loudness bands starts (a downbeat), the one
// holding the most "high" seconds, then the most "mid", the earliest on a tie. 0 when the track has no bands or no window fits.
function strongestStart(file, duration) {
  try {
    const m = musicJson(file), bands = m.energy || [], w = { high: 1, mid: 0.001 }; let best = 0, top = 0;
    for (const { start: s } of bands) {
      if (s + duration > bands.at(-1).end) break;
      const v = bands.reduce((a, b) => a + (w[b.label] || 0) * Math.max(0, Math.min(b.end, s + duration) - Math.max(b.start, s)), 0);
      if (v > top) { best = s; top = v; }
    }
    // two bars before it, so the film opens on the run-up and the drop lands a few seconds in (edits cut their build onto it)
    const run = (m.downbeats || []).filter((d) => d < best - 0.05).slice(-2)[0];
    return +Math.max(0, (best > 0 && run != null ? run : best) - 0.05).toFixed(2);
  } catch { return 0; }
}
const GRID_NOTE = 'beat_grid: the measured beats and downbeats (film seconds) of what the film plays, and its loudness bands (high = the hits). Every cut that follows the music lands on one of these times, and a big hit starts a clip (a clip seam is frame-exact).';

// ElevenLabs answers 429 "system_busy" under heavy traffic (it stopped the fruit film v2z-r01 at its first call, 2026-10-09):
// a busy or failing server is asked again, up to five times, 4 s, 8 s, 16 s, 32 s apart; any other answer is returned as it is.
const elFetch = async (url, opts) => { for (let i = 0; ; i++) { const r = await fetch(url, opts).catch((e) => ({ ok: false, status: 0, text: async () => String(e) }));
  if (r.ok || i >= 4 || !(r.status === 429 || r.status >= 500 || r.status === 0)) return r; await new Promise((ok) => setTimeout(ok, 4000 * 2 ** i)); } };
export async function makeSoundtrack({ lines = [], effects = [], music, musicPrompt, duration, outDir, bedVolume = 1, parts = [], voice, song, songStart, snap = false, beats = false, talkEdit = false, language }) {
  fs.mkdirSync(outDir, { recursive: true });
  const cutParts = (file) => { const out = []; let t0 = 0; for (const [i, len] of parts.entries()) { const pf = path.join(outDir, `part_${i + 1}.mp3`); ff(['-ss', t0.toFixed(2), '-t', String(len), '-i', file, pf]); out.push({ file: pf, start: t0, duration: len }); t0 += len; } return out; };
  // A finished song (lyric videos) IS the soundtrack: the window [songStart, +duration], loudness-normalised, no voice, no bed.
  if (song) {
    if (!fs.existsSync(song)) throw fix(`no song file at ${song}`);
    if (!readable(song)) throw new Error(`${path.basename(song)} cannot be read as sound or video (a broken or unfinished file), so the film stops here`);  // a stop, as before 10-12
    const silent = !hasAudio(song);  // a video with no sound (a screen recording, an AI clip): the film is still made, its soundtrack silence (2026-10-12: genjutsu 4's silent source stopped the whole film)
    if (silent) songStart ??= 0;
    songStart ??= fs.existsSync(path.join(outDir, '..', 'lyrics-ids.vtt')) ? strongestStart(song, duration) : 0;  // a sung song (it has lyric ids); a voice recording or a finished soundtrack keeps 0
    // A window that opens inside a sung line plays that line with no words on screen (minimal-mono fgem6, 2026-10-06):
    // move the start back to just before the line (after the previous one), from the run's lyric ids.
    let note;
    try {
      const ts = (x) => x.split(':').reduce((a, v) => a * 60 + Number(v), 0);
      const cues = [...fs.readFileSync(path.join(outDir, '..', 'lyrics-ids.vtt'), 'utf8').matchAll(/([\d:.]+) --> ([\d:.]+)\s*\n(\[L\d+\])/g)].map((m) => [ts(m[1]), ts(m[2]), m[3]]);
      const k = cues.findIndex(([a, b]) => a < songStart && songStart < b - 0.15);
      if (k >= 0) {
        const s = Math.max(0, cues[k][0] - 0.5, k ? cues[k - 1][1] : 0);
        note = `song_start moved from ${songStart} to ${s.toFixed(2)}: ${cues[k][2]} was already being sung at the first frame and would be heard with no words on screen; it now starts at ${(cues[k][0] - s).toFixed(2)} s of the film, so give it its row.`;
        songStart = Number(s.toFixed(2));
      }
      // a line that starts in the last 1.5 s is cut off by the end and read as random words (kinetic fgem6, 2026-10-06)
      const late = cues.filter(([a]) => a - songStart > duration - 1.5 && a - songStart < duration).map((c) => c[2]);
      if (late.length) note = `${note ? note + ' ' : ''}${late.join(', ')} start${late.length > 1 ? '' : 's'} in the last 1.5 s, too late to be read: give ${late.length > 1 ? 'them' : 'it'} no row; the song fades out under ${late.length > 1 ? 'them' : 'it'}.`;
    } catch {}
    const file = path.join(outDir, 'soundtrack.mp3');
    if (silent) { ff(['-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-t', String(duration), '-b:a', '192k', file]); note = `${note ? note + ' ' : ''}${path.basename(song)} has no sound, so the soundtrack is silence; if the film needs music, call make_soundtrack again with music_prompt (or music) instead of song.`; }
    else ff(['-ss', String(songStart), '-t', String(duration), '-i', song, '-af', `loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=out:st=${(duration - 0.8).toFixed(2)}:d=0.8`, '-b:a', '192k', file]);
    fs.writeFileSync(path.join(outDir, 'song.json'), JSON.stringify({ song, songStart, duration })); // agent/h3film/lyric-retime.py maps the song's caption times to film time
    const grid = beats && !silent ? beatGrid(song, songStart, duration) : undefined;
    // A film cut on the beat sizes its shots before it has the grid (2026-10-09: the AMV planner gave 2.5/2/1 s shots and its
    // seams fell up to 0.3 s off the beat): seams more than a frame from a measured beat are named, so it can call again on the grid.
    const off = [], beat = grid?.bpm ? 60 / grid.bpm : 0, med = [...parts].sort((x, y) => x - y)[parts.length >> 1] || 0;  // only a film cut on the beat (median shot 4 beats or less): lyric clips keep their seams in the gaps between sung lines
    if (grid?.beats?.length && parts.length > 1 && beat && med <= 4 * beat + 0.05) { let t = 0; for (const p of parts.slice(0, -1)) { t += p; if (Math.min(...grid.beats.map((b) => Math.abs(b - t))) > 0.05) off.push(+t.toFixed(2)); } }
    if (off.length) note = `${note ? note + ' ' : ''}Seams more than a frame from a beat: ${off.join(', ')} s. In a film cut on the beat every seam is a time from beat_grid.beats (one beat = ${(60 / grid.bpm).toFixed(3)} s): call make_soundtrack again with parts measured between the beats you cut on.`;
    return { file, duration, music: 'song', songStart, ...(note ? { note } : {}), ...(grid ? { beat_grid: grid, beat_grid_note: GRID_NOTE } : {}), lines: [], parts: cutParts(file) };
  }
  if (!lines.length && !music && !musicPrompt) throw fix('need lines and/or music');
  // music: a library track's name, or the path of an instrumental the user attached (agent/h3film/auto.mjs --ref audio:, in the run's
  // attached/ beside soundtrack/): the bed itself. Any other path is refused as before.
  const userBed = !!music && path.resolve(music).startsWith(path.join(outDir, '..', 'attached') + path.sep) && fs.existsSync(music);
  if (music && !MUSIC.includes(music) && !userBed) throw fix(`unknown music "${music}"; have: ${MUSIC.join(', ')}`);
  if (userBed && !musicPrompt && !readable(music)) throw new Error(`${path.basename(music)} cannot be read as sound or video (a broken or unfinished file), so the film stops here`);  // a stop, as before 10-12
  const silentBed = userBed && !musicPrompt && !hasAudio(music);  // their file has no sound: the bed is silence, as with no music
  // A line with `from` is a moment of the user's own video (a play's call, a crowd roar), cut from it and placed like a voice line.
  for (const l of lines) {
    if (l.from && (!fs.existsSync(l.from) || !(l.end > l.start) || l.end - l.start > (talkEdit ? duration : 15))) throw fix(`line from ${l.from} ${l.start}-${l.end}: needs an existing file and 0 < end - start <= 15 s`);
    if (!l.from && !l.text) throw fix('every line needs text, or from + start + end');
  }
  // 1) VO: synthesize each line, place it, push later lines back if the read runs long. Magic Hour reads all lines at once.
  // The lines' language (2026-10-11): as the call says, else "other" when most of their letters are in a script Magic Hour cannot read
  // (a film that did not say: Hindi, Arabic, Thai), else English as before. In a language Magic Hour cannot speak (el) every line is
  // read in ElevenLabs, and a speaker must be one of that language's native voices or a shelf role.
  const said = lines.filter((l) => !l.from).map((l) => l.text).join(' '), letters = said.match(/\p{L}/gu)?.length || 0;
  const kana = said.match(/[\p{Script=Hiragana}\p{Script=Katakana}]/gu)?.length || 0, lang = language || (kana > letters / 10 ? 'ja' : (said.match(/(?=\p{L})[^\p{Script=Latin}\p{Script=Cyrillic}\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/gu)?.length || 0) > letters / 2 ? 'other' : 'en'), el = !MH_LANGS.includes(lang);
  const mute = el ? [...new Set(lines.filter((l) => l.speaker && !l.from && !elVoice(lang, l.speaker)).map((l) => l.speaker))] : [];
  if (mute.length) throw fix(`speaker ${mute.map((b) => `"${b}"`).join(', ')} cannot speak this film's language${language ? ` ("${language}")` : ' (its lines are not English: give `language`, their ISO 639-1 code)'}: Magic Hour's voices speak only ${MH_LANGS.join(', ')} and garble any other. Give each character a voice native in the film's language, read in ElevenLabs: ${nativeList()}; in a language with no list, "narrator", "narrator-f", "young-m" or "young-f", which ElevenLabs reads in it.`);
  const bad = el ? [] : lines.filter((l) => l.speaker && !MH_PRESETS.includes(l.speaker)).map((l) => l.speaker), words = (s) => s.toLowerCase().split(/[^a-z0-9]+/).filter((x) => x.length > 2);
  if (bad.length) throw fix(`unknown speaker voice ${[...new Set(bad)].map((b) => `"${b}"`).join(', ')}: use an exact Magic Hour preset name, e.g. ${MH_PRESETS.map((n) => [n, Math.max(...bad.map((x) => words(x).filter((w) => words(n).includes(w)).length))]).filter(([, k]) => k).sort((p, q) => q[1] - p[1]).slice(0, 8).map(([n]) => `"${n}"`).join(', ') || '"Morgan Freeman"'}`);   // nearest by shared words (2026-10-12: "Family Guy Peter Griffin" was offered only "Family Guy Quagmire", not "Peter Griffin")
  // a real-audio line names the whole video (its sound), never a footage segment: user_video cuts segments without sound, and ffmpeg's
  // 'no stream' error used to stop the whole film (Saquon v5c-r11, 2026-10-09); now the session is told how to fix it
  for (const [i, l] of lines.entries()) if (l.from && !spawnSync('ffprobe', ['-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', l.from], { encoding: 'utf8' }).stdout.trim())
    throw fix(`line ${i + 1}: ${path.basename(l.from)} has no sound. "from" is the whole video the moment is in (the user's own video, or the clip web_clip downloaded), with start/end in that video's seconds; footage segments are cut without sound`);
  // One recording plays as one (2026-10-11, t1: a remade movie scene given as 13 bites at their own times sounded choppy, silence between
  // the bites and each at its own level): a bite of the same recording as the line before it, in sync with it (film minus source time the
  // same within 0.05 s) and starting at most 2 s after it ends, joins its run, cut once from the run's first word to its last with the pauses
  // between, loudness-normalised once. 2 s: every in-sync pause in our runs is 0.04-1.5 s (t1, r12, b11v, x06, r11); the one longer gap,
  // t1's 4.4 s, is where its planner laid an effect instead. Bites from other moments are cut one by one as before.
  const run = lines.map((l, i) => i); lines.forEach((l, i) => { const p = lines[i - 1]; if (i && l.from && p.from === l.from && Math.abs(l.at - l.start - (p.at - p.start)) <= 0.05 && l.start >= p.start && l.start - p.end <= 2) run[i] = run[i - 1]; });
  lines.forEach((l, i) => l.from && run[i] === i && ff(['-ss', String(l.start), '-t', (Math.max(...lines.filter((_, k) => run[k] === i).map((x) => x.end)) - l.start).toFixed(2), '-i', l.from, '-vn', '-ac', '2', '-ar', '44100', '-af', 'loudnorm=I=-16:TP=-1.5', path.join(outDir, `vo-${i + 1}.mp3`)]));
  const keep = (f) => process.env.SOUNDTRACK_REUSE === '1' && fs.existsSync(f);  // SOUNDTRACK_REUSE=1: mix again from the reads, music and effects already made (a new mix of the same film)
  await Promise.all(lines.map((l, i) => !el && l.speaker && !l.from && !keep(path.join(outDir, `vo-${i + 1}.mp3`)) && mhPreset(l.text, l.speaker, path.join(outDir, `vo-${i + 1}.mp3`))));  // character voices first
  let mh = !el && (process.env.VOICE_PROVIDER || 'magichour') === 'magichour';
  if (mh) try { await Promise.all(lines.map(({ text, speaker, from }, i) => !speaker && !from && !keep(path.join(outDir, `vo-${i + 1}.mp3`)) && mhSay(text, voice || 'narrator', path.join(outDir, `vo-${i + 1}.mp3`)))); }
    catch (e) { console.error(`Magic Hour voice failed (${String(e.message).slice(0, 160)}): ElevenLabs reads this film`); mh = false; }  // the same shelf voices: Magic Hour's reads are clones of them
  // Magic Hour reads (the voice default since 2026-10-07) end in ~0.5 s of silence; ElevenLabs reads, which this placement was built on,
  // ended ~0.1 s after the last word. Placed whole, each read pushed the next line 0.5 s late (fruit v5-r01: 13 lines 2.4 s late, onto its
  // pops and gasps) and ended every line, and the rows timed to it, 0.5 s after its words.
  const trimTail = (f) => { ff(['-i', f, '-af', 'areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.1,areverse', '-b:a', '192k', `${f}.t.mp3`]); fs.renameSync(`${f}.t.mp3`, f); };
  const placed = [], sounds = []; let cursor = 0, runEnd = 0;  // placed: each line, as returned; sounds: each file the mix plays (a run of bites is one)
  for (const [i, { at, text, speaker, from, start: fs0, end: fs1 }] of lines.entries()) {
    const f = path.join(outDir, `vo-${i + 1}.mp3`), h = run[i];
    if ((el || !mh && !speaker) && !from && !keep(f)) {
      if (!process.env.ELEVENLABS_API_KEY) throw new Error('ELEVENLABS_API_KEY missing');
      const r = await elFetch(`https://api.elevenlabs.io/v1/text-to-speech/${el ? elVoice(lang, speaker || voice || 'narrator') : VOICES[voice] || voice || VOICE}?output_format=mp3_44100_128`, { method: 'POST', headers: { 'xi-api-key': process.env.ELEVENLABS_API_KEY, 'content-type': 'application/json' }, body: JSON.stringify({ text, model_id: process.env.ELEVENLABS_TTS_MODEL || 'eleven_v4' }) });
      if (!r.ok) throw new Error(`elevenlabs ${r.status}: ${await r.text()}`);
      fs.writeFileSync(f, Buffer.from(await r.arrayBuffer()));
    }
    if (!from) trimTail(f);
    // a later bite of a run plays inside its first bite's cut, where it falls in it (never pushed); each bite of a run returns its own words' span
    const D = h === i ? dur(f) : 0, start = h < i ? placed[h].at + fs0 - lines[h].start : Math.max(at, cursor), d = h < i || run[i + 1] === i ? fs1 - fs0 : D;
    if (h === i) { runEnd = start + D; sounds.push({ file: f, ...(from ? { from } : speaker ? { speaker } : {}), at: +start.toFixed(2), end: +runEnd.toFixed(2) }); }
    placed.push({ text: text || `(their video ${fs0}-${fs1} s)`, ...(from ? { from } : speaker ? { speaker } : { voice: voice || 'narrator' }), at: +start.toFixed(2), end: +(start + d).toFixed(2), requested_at: at });  // every line says who reads it (a silent default once gave a girl the male narrator)
    // a bite from another moment follows right on (2026-10-10 evening: the 0.25 s breath, older than bites, pushed back-to-back bites
    // 0.15-0.25 s late and past the clip: two retries of b11v); the next chunk of the same recording keeps the breath, since each chunk is
    // loudness-normalised on its own and played with no gap their levels jump mid-phrase (r12 storytime, up to +5.5 dB)
    const nx = lines[i + 1], cont = from && nx && nx.from === from && Math.abs(nx.start - fs1) < 0.3;
    if (run[i + 1] !== h) cursor = runEnd + (from && !cont ? 0 : 0.25);  // after a run's last bite: the next line starts after the whole run
  }
  const pushed = placed.map((p, i) => p.at - p.requested_at > 0.05 ? `line ${i + 1} asked at ${p.requested_at}s, placed at ${p.at}s` : null).filter(Boolean);
  const last = placed.at(-1); if (last && last.end > duration) throw fix(`VO runs to ${last.end}s, past the ${duration}s clip: cut words or lines${pushed.length ? ` (a line starts only after the one before it ends, plus 0.25 s after a read: ${pushed.join('; ')})` : ''}`);
  // Sound effects (a pop, a door, a whoosh) at their times, from ElevenLabs text to sound (elevenlabs.io/docs/api-reference/text-to-sound-effects/convert).
  // A film has no other sound effects: every clip inpaints this soundtrack as its own audio and the join plays only it.
  const fx = await Promise.all(effects.map(async ({ at, sound, seconds, from, start = 0 }, i) => {
    const f = path.join(outDir, `fx-${i + 1}.mp3`);
    if (keep(f)) return { file: f, sound, at: +at.toFixed(2), end: +(at + dur(f)).toFixed(2), fx: true };
    // a real sound (2026-10-10, a meme's own vine boom, fetched): its own length from start, at most 4 s, its last 0.15 s faded
    if (from) { const d = Math.min(seconds || 4, Math.max(0.2, dur(from) - start)); ff(['-ss', String(start), '-t', d.toFixed(2), '-i', from, '-vn', '-ac', '2', '-ar', '44100', '-af', `afade=t=out:st=${Math.max(0, d - 0.15).toFixed(2)}:d=0.15`, f]);
      return { file: f, sound, at: +at.toFixed(2), end: +(at + dur(f)).toFixed(2), fx: true }; }
    const r = await elFetch('https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128', { method: 'POST', headers: { 'xi-api-key': process.env.ELEVENLABS_API_KEY, 'content-type': 'application/json' },
      body: JSON.stringify({ text: sound, prompt_influence: 0.5, ...(seconds ? { duration_seconds: Math.min(30, Math.max(0.5, seconds)) } : {}) }) });
    if (!r.ok) throw new Error(`elevenlabs sound ${r.status}: ${await r.text()}`);
    fs.writeFileSync(f, Buffer.from(await r.arrayBuffer()));
    return { file: f, sound, at: +at.toFixed(2), end: +(at + dur(f)).toFixed(2), fx: true };
  }));
  const asked = parts;  // the seams snap into the pauses: the swap path as r8 (the approved swaps), every other film as the 10-12 batch
  if (process.env.H3_SWAP === '1') { if (snap) parts = snapSeams(parts, placed.filter((p) => !p.from), duration);  // cutParts reads the snapped spans. Only our own lines move a seam: a moment of their own video may cross one (a montage cuts on beats; a remake cuts where the film it follows cut, its speech running on: 2026-10-12, the TJR remake's seam on the movie's cut was moved 0.5 s into a pause, inside the next shot)
  } else { if (snap) { try { parts = snapSeams(parts, placed, duration); } catch (e) { if (!placed.some((p) => p.from)) throw e; parts = snapSeams(parts, placed.filter((p) => !p.from), duration); } } // cutParts reads the snapped spans; a moment of their own video may cross a seam (a montage cuts on beats, not pauses)
  }
  // 2) bed: music from its first downbeat, ducked around the lines (curve from agent/run.mjs duckMusic), faded out.
  // A film the MUSIC carries (an edit: no narration, every line is the footage's own sound, or no lines): its music starts at its
  // strongest part and dips less under the footage's own sound (a call, a roar: at 0.35 saquon7's song sat ~11 dB under its calls and
  // could not be heard, 2026-10-09). Narration (ours, the user's recording) and a longer real take (a talking hook) keep 0.35.
  // An edit of people talking (talkEdit: a podcast, an interview) is carried by their speech, though every line is the footage's own
  // sound: its music is a bed far under the talk (2026-10-11, Alec: "HAVE MUSIC"; as a carried film its bed would sit only 6.6 LU under)
  const carried = !talkEdit && placed.every((p) => p.from && /\.(mp4|mov|m4v|webm|mkv)$/i.test(p.from));
  // a run of bites of one recording dips once, over its pauses too: the music does not swell between two lines of one scene (2026-10-11)
  const ATT = 0.35, REL = 1.2; let expr = '1';
  const talk = talkEdit || placed.some((p) => p.speaker);  // a film of characters talking: a line read by `voice` is a character too (the fruit host sat 6-9 dB over the music, the cast 13-27)
  for (const { at: s, end: e, from, speaker } of sounds) { const DUCK = carried ? 0.6 : speaker || talk ? 0.2 : 0.35;  /* character dialogue dips deeper (-14 dB): at -9 dB the fruit cast was still hard to hear over the music (10-09) */ expr = `min(${expr},if(lt(t,${(s - ATT).toFixed(2)}),1,if(lt(t,${s.toFixed(2)}),1-${(1 - DUCK).toFixed(2)}*(t-${(s - ATT).toFixed(2)})/${ATT},if(lt(t,${e.toFixed(2)}),${DUCK},if(lt(t,${(e + REL).toFixed(2)}),${DUCK}+${(1 - DUCK).toFixed(2)}*(t-${e.toFixed(2)})/${REL},1)))))`; }
  // an edit carried by its song sits 3 dB higher before the dips (2026-10-10, Alec: the Peter edit's song was "pretty muted", ~6 dB under
  // its dialogue): the song is the film's drive, not a bed under narration
  const BED = carried ? BED_MEAN + 3 : BED_MEAN;
  const bed = path.join(outDir, 'bed.wav'); let bpm = null, grid, musicStart;
  if (musicPrompt) {
    const f = path.join(outDir, 'music.mp3');
    const gen = (prompt) => elFetch('https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128', { method: 'POST', headers: { 'xi-api-key': process.env.ELEVENLABS_API_KEY, 'content-type': 'application/json' }, body: JSON.stringify({ prompt, music_length_ms: duration * 1000, force_instrumental: true, model_id: process.env.ELEVENLABS_MUSIC_MODEL || 'music_v2_5' }) });
    if (!keep(f)) {
    let r = await gen(musicPrompt);
    // a prompt naming a game or artist is refused as copyrighted; ElevenLabs returns its own cleaned prompt: use it
    if (r.status === 400) { const t = await r.text(); const alt = (() => { try { return JSON.parse(t).detail.data.prompt_suggestion; } catch { return null; } })(); if (!alt) throw new Error(`elevenlabs music 400: ${t}`); r = await gen(alt); }
    if (!r.ok) throw new Error(`elevenlabs music ${r.status}: ${await r.text()}`);
    fs.writeFileSync(f, Buffer.from(await r.arrayBuffer()));
    }
    if (beats) grid = beatGrid(f, 0, duration);
    if (process.env.H3_SWAP === '1') {  // the swap path: r8's line (the approved swaps)
    ff(['-t', String(duration), '-i', f, '-af', `volume=${(BED - meanDb(f)).toFixed(1)}dB,volume='${expr}':eval=frame,volume=${bedVolume},afade=t=out:st=${(duration - 0.8).toFixed(2)}:d=0.8,apad=whole_dur=${duration}`, bed]);  // a bed shorter than the film is padded, never the film cut to it (2026-10-12: a song from 27.3 s of a 44 s TikTok made a 16.5 s soundtrack for a 57 s film)
    } else {  // every other film: the 10-12 batch's line
    ff(['-t', String(duration), '-i', f, '-af', `volume=${(BED - meanDb(f)).toFixed(1)}dB,volume='${expr}':eval=frame,volume=${bedVolume},afade=t=out:st=${(duration - 0.8).toFixed(2)}:d=0.8`, bed]);
    }
  } else if (music && !silentBed) {
    const src = userBed ? music : path.join(MUSIC_DIR, `${music}.mp3`);
    let ss = userBed ? songStart ?? (carried ? strongestStart(src, duration) : 0) : 0; try { const m = JSON.parse(fs.readFileSync(`${src}.music.json`, 'utf8')); bpm = m.bpm; if (!userBed) ss = Math.max(0, (m.downbeats?.[0] ?? m.beats?.[0] ?? 0) - 0.05); } catch {}
    if (userBed) { musicStart = ss; fs.writeFileSync(path.join(outDir, 'song.json'), JSON.stringify({ song: src, songStart: ss, duration })); }  // lyric-retime.py maps its sung lines to film time
    if (beats) grid = beatGrid(src, ss, duration);
    if (process.env.H3_SWAP === '1') {  // the swap path: r8's line (the approved swaps)
    ff(['-ss', ss.toFixed(2), '-t', String(duration), '-i', src, '-af', `volume=${(BED - meanDb(src)).toFixed(1)}dB,volume='${expr}':eval=frame,volume=${bedVolume},afade=t=out:st=${(duration - 0.8).toFixed(2)}:d=0.8,apad=whole_dur=${duration}`, bed]);  // a bed shorter than the film is padded, never the film cut to it (2026-10-12: a song from 27.3 s of a 44 s TikTok made a 16.5 s soundtrack for a 57 s film)
    } else {  // every other film: the 10-12 batch's line
    ff(['-ss', ss.toFixed(2), '-t', String(duration), '-i', src, '-af', `volume=${(BED - meanDb(src)).toFixed(1)}dB,volume='${expr}':eval=frame,volume=${bedVolume},afade=t=out:st=${(duration - 0.8).toFixed(2)}:d=0.8`, bed]);
    }
  } else ff(['-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-t', String(duration), bed]);
  // 3) mix, as a mixing engineer would: the music and the voices first, brought to programme loudness (-16 LUFS) by ONE fixed gain
  // measured on them alone, so an effect never moves the music or a voice (2026-10-11: a loudnorm over the whole mix turned the music
  // down about 2 dB after every run of effects); every effect then sits at the level of the speech (its loudest 400 ms matched to the
  // reads' loudest; with no speech, a little over the music), with the same gain (Alec: effects "mixed at the vol of speech ... js not
  // distrupting vol of anything else"; they had all been raised to one loud peak). Every read at one level (the presets and our narrator
  // voices differ by 5 dB: the host under the cast). Without the gain a film that is mostly bed ships at the bed's own duck-level (mh1:
  // -27.9 dB mean, "so quiet and ass"). A limiter at -1 dBFS catches only the moment the sum would clip.
  const inputs = ['-i', bed, ...sounds.flatMap((p) => ['-i', p.file])];
  const fc = sounds.map((p, i) => `[${i + 1}:a]${p.from ? '' : `volume=${(VO_MEAN - meanDb(p.file)).toFixed(1)}dB,`}adelay=${Math.round(p.at * 1000)}|${Math.round(p.at * 1000)}[v${i}]`).concat(`[0:a]${sounds.map((_, i) => `[v${i}]`).join('')}amix=inputs=${sounds.length + 1}:normalize=0:duration=first[m]`).join(';');
  const file = path.join(outDir, 'soundtrack.mp3'), base = path.join(outDir, 'mix-base.wav');
  ff([...inputs, '-filter_complex', fc, '-map', '[m]', '-t', String(duration), base]);
  const lufs = (f) => +(spawnSync('ffmpeg', ['-i', f, '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], { encoding: 'utf8' }).stderr.match(/"input_i"\s*:\s*"(-?[\d.]+)"/)?.[1] ?? NaN);
  const loudest = (f) => Math.max(-70, ...[...spawnSync('ffmpeg', ['-nostats', '-i', f, '-af', 'apad=pad_dur=0.5,ebur128', '-f', 'null', '-'], { encoding: 'utf8' }).stderr.matchAll(/ M:\s*(-?[\d.]+)/g)].map((m) => +m[1]));
  const I = lufs(base), gain = Number.isFinite(I) ? -16 - I : 0, lim = 'alimiter=limit=0.891:level=0:latency=1';
  const speech = sounds.map((p) => loudest(p.file) + (p.from ? 0 : VO_MEAN - meanDb(p.file))).sort((a, b) => a - b), bedI = lufs(bed);
  const target = speech.length ? speech[speech.length >> 1] : Number.isFinite(bedI) ? bedI + 6 : -16;  // loudest 400 ms of a bed sits ~6 LU over its average
  const mixed = fx.length ? `[b]${fx.map((_, i) => `[f${i}]`).join('')}amix=inputs=${fx.length + 1}:normalize=0:duration=first,${lim}[o]` : `[b]${lim}[o]`;
  // an effect may play under a line, 10 dB down while the line's words play (2026-10-11, Alec: effects pushed the speech, kept to the gaps between
  // lines; a pro mix plays them under it and never moves a line): 0.1 s ramps inside the line, so an effect before or after a line is as loud as
  // before; frames of 64 samples so the ramp is smooth
  const FXD = 0.32, under = (p) => { const o = placed.filter((l) => l.at < p.end && l.end > p.at); return o.length ? `,asetnsamples=n=64,volume='${o.reduce((x, { at: s, end: e }) => `min(${x},if(between(t,${s},${e}),max(${FXD},1-${(1 - FXD).toFixed(2)}*min(t-${s},${e}-t)/${Math.min(0.1, (e - s) / 2).toFixed(3)}),1))`, '1')}':eval=frame` : ''; };
  ff(['-i', base, ...fx.flatMap((p) => ['-i', p.file]), '-filter_complex', [`[0:a]volume=${gain.toFixed(2)}dB[b]`, ...fx.map((p, i) => `[${i + 1}:a]volume=${(target - loudest(p.file) + gain).toFixed(2)}dB,adelay=${Math.round(p.at * 1000)}|${Math.round(p.at * 1000)}${under(p)}[f${i}]`), mixed].join(';'), '-map', '[o]', '-t', String(duration), '-b:a', '192k', file]);
  fs.rmSync(base, { force: true });
  // 4) parts for multi-clip films: part N is clip N's reference_audio
  const G = { ...(grid ? { beat_grid: grid, beat_grid_note: GRID_NOTE } : {}), ...(musicStart != null ? { music_start: musicStart } : {}), ...(silentBed ? { note: `${path.basename(music)} has no sound, so this film has no music under the voices` } : {}) };
  const E = fx.length ? { effects: fx.map(({ file, fx: _, ...e }) => e) } : {};
  if (!snap) return { file, duration, music: musicPrompt ? 'generated' : music, bpm, ...G, lines: placed.map(({ file, ...p }) => p), ...E, parts: cutParts(file) };
  const cut = cutParts(file), moved = parts.some((p, i) => p !== asked[i]);
  return { file, duration, music: musicPrompt ? 'generated' : music, bpm, ...G,
    // clip_at/clip_end: the line in its own clip's seconds, so rows need no subtraction (2026-10-09: a seam moved to 23.85 s, the
    // fruit planner wrote "I'm loyal" at 0.8 s of clip 3 over a shot from behind, and it was said at 0.15 s)
    lines: placed.map(({ file, ...p }) => { const k = cut.filter((x) => +x.start.toFixed(2) <= p.at).length, c = cut[k - 1];
      return { ...p, clip: k || undefined, ...(c ? { clip_at: +(p.at - c.start).toFixed(2), clip_end: +(p.end - c.start).toFixed(2) } : {}) }; }),
    ...E,
    parts: cut,
    ...(cut.length > 1 && placed.length ? { seams: `FINAL. Clip spans: ${parts.join(' / ')} s${moved ? ` (you asked ${asked.join(' / ')}; seams moved into the pauses between lines)` : ''}. No narration line crosses a seam (a moment of their own video may); each line's "clip" says which clip it is in, and clip_at/clip_end where it starts and ends in that clip's own seconds. Use these spans in the Clips table (seconds = ceil(span + 0.3)) and write each clip's rows from its lines' clip_at/clip_end. Do not call make_soundtrack again.` } : {}) };
}

/** Last `seconds` of a rendered clip, video only: the continuity reference for the next clip of a chained film (render-all.mjs). */
export function clipTail(video, seconds = 3, out) {
  out ||= video.replace(/\.mp4$/, `.tail${seconds}s.mp4`);
  ff(['-sseof', `-${seconds}`, '-i', video, '-an', '-c:v', 'libx264', '-crf', '18', out]); return out;
}
