// join.mjs — the film from its clips: each clip trimmed to its PLANNED length (fal returns up to
// ~0.6 s more, and what follows the plan's last event is a frozen frame or invented drift, both
// checked on gen1/gen4 2026-09-17), concatenated in order, the soundtrack laid over ONCE from t=0.
// Seams are hard cuts by construction (plan.mjs only cuts where the film cuts), so no crossfade,
// no retime. Alec: "a crossfade sounds retarded".
//
//   import { joinFilm } from "./join.mjs";
//   await joinFilm({ clips: [{ file, seconds }], music, out, size: "832x480", target })
// target (2026-10-10 evening, Alec: the user's duration, which the player must show): the film is touched only when its own length
// falls outside target..target+0.45 s, which a player shows as the target whether it rounds or floors: short, its last frame is held
// and the sound padded with silence up to the target; long, both are cut to target+0.45 s, the sound with a 0.15 s fade out.

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// captions (2026-10-10, Alec): words that stay on screen while the picture changes (a meme's caption, a running title, subtitles)
// are drawn by code on the finished film, the same words, size and place in every frame: H3 painted "peter mentality." at a
// different size and place in each clip, and repainting the real footage under it put Stewie on a table and moved Peter's lips.
// Each { text, from, to, place: "top" | "middle" | "bottom" (default), or x / y: its centre as a share of the width / height }, in the
// look captions have on TikTok and Instagram: white bold type with a black outline ("color" for another fill, e.g. a reference's own
// subtitles). Japanese, Chinese and Korean get their own bold system font and wrap by character (2026-10-11).
const PY = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../.venv/bin/python");
// Off macOS (the team's Linux servers) the Latin captions and the titles use Inter, an open-licence font shipped in assets/fonts;
// on a Mac the system fonts below are used exactly as before. Other scripts still need the Mac fonts (else Pillow's plain one).
const FONTS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../assets/fonts");
const CAPS = `import json, os, sys
from PIL import Image, ImageDraw, ImageFont
W, H, caps = int(sys.argv[1]), int(sys.argv[2]), json.loads(sys.argv[3])
import re
size = round(min(W, H) * 0.065)
CJK = r'\\u3040-\\u30ff\\u3400-\\u9fff\\uac00-\\ud7af\\uff00-\\uffef'
mac = lambda f, i, own: (f, i) if os.path.exists(f) else (os.path.join(${JSON.stringify(FONTS)}, own), 0)  # the macOS font, else ours
TITLE = mac('/System/Library/Fonts/HelveticaNeue.ttc', 7, 'Inter-Light.ttf')  # Helvetica Neue Light
cjk = lambda f, i, noto: (f, i) if os.path.exists(f) else ('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', noto)  # the macOS font, else Noto Sans CJK Bold (Linux: fonts-noto-cjk; face 0 JP, 1 KR)
def pick(t):
    f = cjk('/System/Library/Fonts/AppleSDGothicNeo.ttc', 6, 1) if re.search(r'[\\uac00-\\ud7af]', t) else cjk('/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc', 0, 0) if re.search('[' + CJK + ']', t) else ('/Library/Fonts/Arial Unicode.ttf', 0) if re.search(r'[^\\u0000-\\u052f\\u2000-\\u206f]', t) else mac('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 0, 'Inter-Bold.ttf')
    try: return ImageFont.truetype(f[0], size, index=f[1])
    except OSError: return ImageFont.load_default(size)
UNIT = re.compile(r'\\s*(?:[' + CJK + r']|[^\\s' + CJK + r']+)')
from PIL import ImageFilter
for c in caps:
    title = c.get('style') == 'title'; text = str(c['text']).upper() if title else str(c['text'])
    font = ImageFont.truetype(TITLE[0], round(size * 0.7), index=TITLE[1]) if title and not re.search(r'[^\\u0000-\\u052f\\u2000-\\u206f]', text) else pick(text)
    tr = round(font.size * 0.3) if title else 0
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im); lines = []; cx = c.get('x') or 0.5; mw = W * min(0.88, 2 * min(cx, 1 - cx) - 0.04)
    tl = lambda s: d.textlength(s, font=font) + tr * max(0, len(s) - 1)
    for para in text.split('\\n'):
        line = ''
        for u in UNIT.findall(para):
            if line and tl(line + u) > mw: lines.append(line); line = u.lstrip()
            else: line = line + u if line else u.lstrip()
        lines.append(line)
    lh = round(font.size * (1.5 if title else 1.18)); bh = lh * len(lines); cy = c.get('y') or {'top': 0.12, 'middle': 0.5}.get(c.get('place'), 0.86)
    top = min(max(round(cy * H - bh / 2), 4), H - bh - 4)
    def put(dr, y, l, **kw):
        if not tr: dr.text((cx * W, y), l, font=font, anchor='mm', **kw); return
        x = cx * W - tl(l) / 2
        for ch in l: dr.text((x, y), ch, font=font, anchor='lm', **kw); x += d.textlength(ch, font=font) + tr
    if title:
        sh = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
        for i, l in enumerate(lines): put(ds, top + i * lh + lh / 2, l, fill=(0, 0, 0, 170))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(font.size * 0.12))); d = ImageDraw.Draw(im)
    for i, l in enumerate(lines): put(d, top + i * lh + lh / 2, l, fill=c.get('color') or 'white', **({} if title else {'stroke_width': max(2, round(size * 0.09)), 'stroke_fill': 'black'}))
    im.save(c['file'])`;

export async function joinFilm({ clips, music, out, size = "832x480", target, captions = [] }) {
  const [w, h] = size.split("x").map(Number);
  // Frame-exact cuts: each clip keeps the frames between its planned start and end on the film's own frame grid. "-t seconds"
  // per clip kept up to a frame too many each time, and over the 28 one-shot clips of an AMV the picture ran 0.3-0.6 s behind
  // its song by the end (2026-10-09).
  const [fn, fd] = spawnSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", clips[0].file], { encoding: "utf8" }).stdout.trim().split("/").map(Number);
  const fps = fn / (fd || 1); let t = 0;
  const frames = clips.map((c) => { const a = Math.round(t * fps); t += c.seconds; return Math.round(t * fps) - a; });
  const inputs = clips.flatMap((c) => ["-i", c.file]);
  const chain = clips.map((_, i) => `[${i}:v]fps=${fps},trim=end_frame=${frames[i]},setpts=PTS-STARTPTS,scale=${w}:${h},setsar=1[v${i}]`).join(";") + ";" + clips.map((_, i) => `[v${i}]`).join("") + `concat=n=${clips.length}:v=1:a=0[v]`;
  const total = clips.reduce((s, c) => s + c.seconds, 0);
  const have = frames.reduce((a, b) => a + b, 0), lo = target ? Math.round(target * fps) : 0, hi = target ? Math.floor((target + 0.45) * fps) : 0;
  const T = !target || (have >= lo && have <= hi) ? 0 : have < lo ? lo : hi, len = T / fps;  // 0: the film's own length already shows as the target
  const fit = !T ? "" : have < T ? `;[v]tpad=stop_mode=clone:stop=${T - have}[vt]` : `;[v]trim=end_frame=${T},setpts=PTS-STARTPTS[vt]`;
  const caps = (captions || []).filter((c) => String(c?.text ?? "").trim()).map((c, k) => ({ ...c, file: `${out}.caption${k + 1}.png` }));
  if (caps.length) { const r = spawnSync(PY, ["-c", CAPS, String(w), String(h), JSON.stringify(caps)], { encoding: "utf8" }); if (caps.some((c) => !existsSync(c.file))) throw new Error("captions failed: " + r.stderr); }
  const ci = clips.length + (music ? 1 : 0), vin = fit ? "vt" : "v";
  // a title fades in and out over 0.4 s; other captions cut on and off like a platform's
  const fade = (c, k) => `;[${ci + k}:v]format=rgba,fade=t=in:st=${+c.from || 0}:d=0.4:alpha=1${c.to != null ? `,fade=t=out:st=${Math.max(+c.from || 0, c.to - 0.4)}:d=0.4:alpha=1` : ""}[t${k}]`;
  const fc = caps.map((c, k) => `${c.style === "title" ? fade(c, k) : ""};[${k ? `c${k}` : vin}][${c.style === "title" ? `t${k}` : `${ci + k}:v`}]overlay=0:0:enable='between(t,${+c.from || 0},${c.to ?? 1e9})'[c${k + 1}]`).join("");
  const fa = T && music ? `;[${clips.length}:a]atrim=0:${len},apad=whole_dur=${len},afade=t=out:st=${Math.max(0, len - 0.15)}:d=0.15[at]` : "";
  const args = ["-loglevel", "error", "-y", ...inputs, ...(music ? (T ? ["-i", music] : ["-ss", "0", "-t", String(total), "-i", music]) : []),
    ...caps.flatMap((c) => c.style === "title" ? ["-loop", "1", "-framerate", String(fps), "-t", String(Math.max(total, len) + 1), "-i", c.file] : ["-i", c.file]), "-filter_complex", chain + fit + fa + fc, "-map", caps.length ? `[c${caps.length}]` : `[${vin}]`, ...(music ? (T ? ["-map", "[at]", "-c:a", "aac"] : ["-map", `${clips.length}:a`, "-c:a", "aac", "-shortest"]) : []),
    ...(T ? ["-t", String(len)] : []), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out];
  const r = spawnSync("ffmpeg", args, { encoding: "utf8" });
  if (!existsSync(out)) throw new Error("join failed: " + r.stderr);
  return { out, seconds: T ? len : total };
}
