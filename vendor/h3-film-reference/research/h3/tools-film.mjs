// tools-film.mjs — the three tools the one-session H3 film skill (skills/h3-film) adds to mcp.mjs:
//   still       a reference image for H3: type still / surface / a code screen rendered flat into the
//               painted room at 4032×2268 (agent/h3film/still.mjs) — the still IS the design
//   image       Nano Banana (imageModel() below): edit-task stills from real screenshots, white-ground
//               cutouts matted with rembg, backdrops, exact-text diagram frames. ≤14 references. Cached by
//               content hash in agent/artcache (re-runs and recurring props cost nothing).
//   join_film   clips trimmed to their PLANNED seconds, concatenated, the soundtrack laid over once.
// Every tool returns a small JPEG of what it made so the session sees it without a Read.
import { z } from 'zod';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { execSync, spawnSync } from 'node:child_process';
import { GoogleGenAI } from '@google/genai';
import { makeStill, makeScreenStill, makeLockup, ROOM, ROOMS, CANVAS, ratio, canvas } from '../../agent/h3film/still.mjs';
import { joinFilm } from '../../agent/h3film/join.mjs';
import { uncoveredRows } from '../../agent/h3film/check-prompt.mjs';
import { RUNS } from './h3.mjs';

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const PY = path.join(REPO, '.venv/bin/python');
const outDir = (sub) => { const d = path.join(process.env.H3_OUT || RUNS, sub); fs.mkdirSync(d, { recursive: true }); return d; };
const slug = (s) => s.replace(/[^a-z0-9_-]/gi, '_');
// Antigravity sizes its context by image PIXELS and compacted right after Gemini viewed full-size stills (4032x2268, 2560x1600;
// 4 runs). Every still-making tool writes <name>.view.jpg (≤1216x684) beside the full file for Gemini to look at; H3 gets the full file.
// Nano Banana's quota (429) can stay exhausted for minutes when many films run at once, and some calls just hang. A 429 (after
// the SDK's own ~2.5 min of retries) goes to the same model on fal (NB[model].fal); a call slower than 2 min races
// fal and takes whichever answers first. If fal fails too, a 429 waits a minute and retries Google for up to 20 min; the
// call-again wrapper in mcp.mjs keeps Antigravity waiting meanwhile. Google's googleSearch grounding is not sent to fal.
// The image model is NANO_BANANA_MODEL, read per call (mcp.mjs loads .env.local after its imports). Default since 2026-10-07:
// Nano Banana 2.1 (gemini-nano-banana-2.1, GA 2026-10-06, the manager's ask: higher quality at lower cost). Every film before
// it used Nano Banana 2 (gemini-3.1-flash-image); gemini-3.1-flash-lite-image is Nano Banana 2 Lite. Prices: output per image
// at 1K / 2K, ai.google.dev/gemini-api/docs/pricing (2026-10-07; input and thinking tokens extra).
export const imageModel = () => process.env.NANO_BANANA_MODEL || 'gemini-nano-banana-2.1';
const NB = {
  'gemini-nano-banana-2.1': { fal: 'fal-ai/nano-banana-2.1', '1K': 0.0336, '2K': 0.0504 },
  'gemini-3.1-flash-image': { fal: 'fal-ai/nano-banana-2', '1K': 0.067, '2K': 0.101 },
  'gemini-3.1-flash-lite-image': { '1K': 0.0336 },
};
const viaFal = async (req) => {
  const twin = NB[req.model]?.fal; if (!twin) throw new Error(`no fal twin for ${req.model}`);
  const { fal } = await import('@fal-ai/client');
  const parts = req.contents?.[0]?.parts || [], cfg = req.config?.imageConfig || {};
  const image_urls = await Promise.all(parts.filter((p) => p.inlineData).map((p) => fal.storage.upload(new File([Buffer.from(p.inlineData.data, 'base64')], `ref.${(p.inlineData.mimeType || 'image/png').split('/')[1]}`, { type: p.inlineData.mimeType || 'image/png' }))));
  const input = { prompt: parts.filter((p) => p.text).map((p) => p.text).join('\n\n'), aspect_ratio: cfg.aspectRatio || 'auto', resolution: cfg.imageSize || '1K', output_format: 'png', num_images: 1, ...(image_urls.length ? { image_urls } : {}) };
  const r = await fal.subscribe(image_urls.length ? `${twin}/edit` : twin, { input, logs: false });
  const url = r.data?.images?.[0]?.url; if (!url) throw new Error(`fal ${twin} returned no image`);
  return { candidates: [{ content: { parts: [{ inlineData: { mimeType: 'image/png', data: Buffer.from(await (await fetch(url)).arrayBuffer()).toString('base64') } }] } }] };
};
const is429 = (e) => /429|RESOURCE_EXHAUSTED/.test(String(e?.message ?? e));
export const quotaWait = (ai) => { const gen = ai.models.generateContent.bind(ai.models); ai.models.generateContent = async (req) => {
  if (process.env.NANO_BANANA_VIA !== 'vertex') return viaFal(req);  // 2026-10-09: Vertex refuses every request ("terms of use and policies"); fal's Nano Banana is the default
  const g = gen(req); g.catch(() => {});
  let slow = false;
  try { const r = await Promise.race([g, new Promise((ok) => setTimeout(ok, 120e3, 'slow'))]); if (r !== 'slow') return r; slow = true; }
  catch (e) { if (!is429(e)) throw e; try { return await viaFal(req); } catch {} }
  if (slow) try { return await Promise.any([g, viaFal(req)]); } catch {} // slow (no answer in 2 min): race fal, first image wins
  for (const t0 = Date.now(); ;) { try { return await gen(req); } catch (e) {
    if (!is429(e) || Date.now() - t0 > 20 * 60e3) throw e;
    await new Promise((ok) => setTimeout(ok, 60e3)); } } }; return ai; };
export const VIEW_NOTE = ' To look at a still, view its .view.jpg (small copy); prompts and render.json keep the full-size file.';
// The view box is the still canvas at 1216/4032 (1216x684 at 16:9, 684x1216 at 9:16): the same pixels whatever the RATIO.
export const view = (file) => { const v = file.replace(/\.[^./]+$/, '') + '.view.jpg', [vw, vh] = canvas().map((x) => Math.round((x * 1216) / 4032)); try { execSync(`${PY} -c "from PIL import Image;im=Image.open('${file}').convert('RGB');im.thumbnail((${vw},${vh}));im.save('${v}','JPEG',quality=80)"`); return v; } catch { return undefined; } };
export const thumb = (file, px = 640) => { try { return execSync(`${PY} -c "from PIL import Image;import base64,io;im=Image.open('${file}').convert('RGB');im.thumbnail((${px},${px}));b=io.BytesIO();im.save(b,'JPEG',quality=78);print(base64.b64encode(b.getvalue()).decode())"`).toString().trim(); } catch { return ''; } };
const reply = (obj, file) => { const v = file && view(file); const content = [{ type: 'text', text: JSON.stringify(v ? { ...obj, view: v } : obj) }]; const t = file && thumb(v || file); if (t) content.push({ type: 'image', data: t, mimeType: 'image/jpeg' }); return { content }; };
const fail = (msg) => ({ isError: true, content: [{ type: 'text', text: msg }] });
// A provider or render failure (not a refusal the session can reword, not a wrong argument) stops the whole run: FAILED.json
// in the run directory, which the launcher watches (it ends the session, renders nothing and exits non-zero) and render-all
// refuses. A film made without its voice, music or a still is worse than no film (zine lost every photo, glossy-3d its
// trophy, films lost their narration when ElevenLabs ran dry: all shipped).
const accountError = (e) => [401, 402, 404].includes(e?.status) || (e?.status === 403 && /lock|top.?up|balance|credit|billing|exhaust/i.test(failWhy(e)));  // out of money, a bad key, a removed model: the provider, not the picture
export const refusal = (e) => /^no image returned/.test(e?.message) || (e?.status >= 400 && e.status < 500 && e.status !== 429 && !accountError(e));  // the request, not the provider: the session can change it
// why it was refused: fal's client puts the reason in body.detail and leaves message empty (2026-10-11: sixteen refused frames came back as
// "FAILED design-gwen: " and the planner guessed for three rounds); a refusal is retried at once, a provider error after a pause
export const failWhy = (e) => { const d = e?.body?.detail; return (Array.isArray(d) ? d.map((x) => x?.msg).filter(Boolean).join('; ') : typeof d === 'string' ? d : '') || e?.message || 'refused'; };
export const REFUSED_HINT = ' (A refused picture usually names a film, cartoon or game character. Its design is its real official picture: get it with reference_image and attach that instead of drawing it. In any other picture of them, describe them by their look with no names and keep the attached pictures; only the pictures lose the names: the clip prompts still name the film and its characters.)';
export const fatal = (tool, msg) => {
  try { fs.writeFileSync(path.join(process.env.H3_OUT || RUNS, 'FAILED.json'), JSON.stringify({ tool, error: String(msg).slice(0, 2000), at: new Date().toISOString() }, null, 1)); } catch {}
  return fail(`RUN STOPPED: ${tool} failed and this film cannot be made without it (${String(msg).slice(0, 600)}). Do not retry, work around it or continue: end the session now.`);
};
const roomCss = (room, ground, light) => (ROOMS[room] ?? ROOMS.glow)(ground || '#0a0a0b', light || ground || '#a03a86');

// The film directories whose screens can be rendered flat (each has an index.html and relative assets).
const FILMS = { orchids: 'ingest/orchids', blossom: 'ingest/blossom', 'beehiiv-updates': 'ingest/beehiiv-updates', 'ghost-note': 'ingest/ghost-note', goconfirm: 'ingest/goconfirm', 'framer-agents': 'ingest/framer-agents', 'wix-harmony': 'ingest/wix-harmony', chatbase: 'research/lab' };

export function registerFilmTools(server) {
  // H3_REFS=1 (agent/h3-film-agy.sh, when the brief lists the user's references, agent/h3film/auto.mjs --ref): the tools say how a
  // user's file is used (skills/h3-film/REFERENCES.md); without it every description is as before. Their files are in <run>/attached/.
  const REFS = process.env.H3_REFS === '1', ATT = path.join(process.env.H3_OUT || RUNS, 'attached'), attached = (f) => !!f && path.resolve(f).startsWith(ATT + path.sep);
  // RATIO (unset = 16:9, the launcher passes it): the film's frame. Stills are drawn on its canvas, Nano Banana frames in its shape.
  const R = ratio(), [W, H] = canvas(), tall = W <= H;
  // an edit keeps the shape of the image it edits (a desktop screenshot stays wide in a 9:16 film): the nearest film shape
  const shape = (f) => { try { const [w, h] = execSync(`${PY} -c "from PIL import Image;print(*Image.open('${f}').size)"`).toString().trim().split(' ').map(Number);
    return Object.keys(CANVAS).map((r) => [r, Math.abs(Math.log(w / h / (r.split(':')[0] / r.split(':')[1])))]).sort((a, b) => a[1] - b[1])[0][0]; } catch { return R; } };
  server.registerTool('still', {
    description: 'Make one H3 reference image (' + W + '×' + H + ') in the film\'s painted room: kind=lockup (THE ENDCARD as one designed still: design it yourself for THIS film with design=, its own typeface and layout in the film\'s look, so no two films end alike; with design left out, Orchids\' endcard layout with the product\'s mark (if it has one), name, CTA line and URL (if known) swapped in; never hand H3 the mark, name and URL as separate stills), text (one line of the serif, the type still), surface (an image centred at a fraction of the frame with a soft shadow — a screenshot, a Nano Banana still, a pool still), screen (an HTML screen from an ingested film, or your edited copy of one, rendered flat with its own fonts and assets), blank (the empty room). The room is painted as pixels identically in every still (described glows flicker; painted ones hold). Returns the PNG path and a thumbnail: LOOK at it.' + VIEW_NOTE,
    inputSchema: {
      name: z.string().describe('file stem, e.g. claim1, composer, composer-2'),
      kind: z.enum(['text', 'surface', 'screen', 'lockup', 'blank']),
      mark: z.string().optional().describe('lockup: the product\'s SYMBOL, an SVG or PNG file path; the name is typed beside it. If the film shows a mark or mascot beside the name anywhere, pass it here so the lockup still holds the whole group, centred' + (REFS ? '. A brand kit logo the brief lists (in attached/) is the brand\'s own logo: pass it here when it is a symbol alone, as wordmark= when it spells the name' : '')),
      wordmark: z.string().optional().describe('lockup: the product\'s WORDMARK (its name as the brand draws it), an SVG file path; nothing is typed beside it. Give mark= or wordmark= when the film has one'),
      product: z.string().optional().describe('lockup: the product name, e.g. "Magic Hour"'),
      line: z.string().optional().describe('lockup: the CTA line in the pill, 2–4 words, e.g. "Try it free"'),
      url: z.string().optional().describe('lockup: the product\'s web address ONLY when the brief gives it or you opened the product\'s site with the screenshot tool, e.g. "magichour.ai"; otherwise leave url out and the lockup shows no address: never guess one from the name'),
      room: z.enum(['glow', 'studio', 'spot', 'paper', 'gradient', 'vignette', 'flat', 'none']).default('glow').describe('THE ROOM — the style\'s, not the pipeline\'s, and the same for every still in one film. glow: light rising from below the frame (Orchids/dark product). studio: a soft top light (glass, photoreal, premium hardware). spot: a pool of light behind the surface (one object alone, keynote). paper: a near-flat light field (clean light SaaS, collage, editorial). gradient: a two-colour diagonal field (acid, Y2K, brutalist). flat: one flat colour, nothing else (Swiss, kinetic type, flat vector). none: no room — the surface fills the frame edge to edge (screen recording, full-bleed).'),
      ground: z.string().optional().describe('the room\'s ground hex'),
      light: z.string().optional().describe('the room\'s light/second colour hex (the glow, the top light, the far end of the gradient)'),
      text: z.string().optional().describe('text: the line, exactly as it will read on screen'),
      em: z.number().min(0.03).max(0.5).default(0.09).describe(`text: type size as a fraction of frame ${tall ? 'width' : 'height'} (0.09 claim, 0.11 big line, up to 0.5 for one giant word: a word too wide for the frame is shrunk to fit)`),
      ink: z.string().default('#ffffff').describe('text: type colour hex (dark ink on a light room)'),
      font: z.enum(['serif', 'sans', 'mono', 'condensed']).default('serif').describe('text: which face — the style decides (a serif for editorial and product-poetic, a sans for Swiss/technical/flat, mono for developer and blueprint, condensed for huge kinetic-type caps: one weight, use weight 400)'),
      italic: z.boolean().default(false).describe('text: slant'),
      weight: z.number().int().min(100).max(900).default(400).describe('text: 300 light, 400 book, 700 bold, 900 black'),
      caps: z.boolean().default(false).describe('text: uppercase'),
      track: z.number().min(-0.06).max(0.3).default(0).describe('text: letter-spacing in em (negative tightens a display line, 0.12+ is a Swiss label)'),
      lead: z.number().min(0.8).max(1.6).default(1.15).describe('text: line-height'),
      wrap: z.number().min(0.2).max(0.9).optional().describe(`text: the widest a line may run, as a fraction of the frame width; a longer line breaks between words onto the next row (unset: ${tall ? '0.84' : 'every line stays one row'})`),
      place: z.enum(['centre', 'left', 'top-left', 'bottom', 'bottom-left']).default('centre').describe('text: where the line sits in the frame'),
      image: z.string().optional().describe('surface: local image path'),
      width: z.number().min(0.3).max(0.95).default(0.7).describe('surface/screen: fraction of the frame width the surface fills'),
      film: z.enum(Object.keys(FILMS)).optional().describe('screen: which ingested film the screen (or your copy of it) belongs to — its assets resolve from there'),
      screen: z.string().optional().describe('screen: path to the .html screen (an original under ingest/<film>/compositions/screens/, or your edited copy anywhere)'),
      css: z.string().default('').describe('screen: extra CSS, e.g. "#placeholder{display:none}" to remove what the beat replaces, or a state class'),
      head: z.string().optional().describe('screen: replace the film\'s <head> (fonts + @theme tokens) with this HTML, for a re-themed film'),
      design: z.string().optional().describe(`lockup: YOUR OWN ENDCARD for this film, as HTML: a <style> block plus the markup, laid out on a ${Math.round(W * 1920 / Math.max(W, H))}×${Math.round(H * 1920 / Math.max(W, H))} px page (the frame's own shape, scaled up to the frame as it is). Its own typeface (any Google Fonts family, named in font-family: the renderer fetches it) and its own layout, in the film's look and colours. The brand's logo is <img src="LOGO">: the tool puts in the brand's own (the logo the screenshot tool captured — look at it, and when it already spells the name never type the name too — else the mark= or wordmark= you pass, else the site's app icon); leave it out when the brand has none. Every word is typed; no other picture, no <svg>, no url(): the background is bg= or a CSS colour or gradient. Type reads at 480p: the name or main line at least 120 px tall, nothing under 54 px, nothing within 80 px of the page's edges. Only what the card and brief put on the end card (the name, the logo, one line, the address when known). The rows that bring it in describe THIS design's parts where they sit.`),
      bg: z.string().optional().describe('lockup: the ENDCARD BACKGROUND in this film\'s own look, so endcards differ from style to style: first draw the empty end frame in the style (a `storyboard` frame with the card\'s look: its ground, light, setting or texture, NO text and NO logo, space left in the middle), then pass its path here; the mark, name, CTA line and URL are set on it. Without it the lockup sits on the plain room. Pass ink= to suit it (dark ink on a light background). text: a picture (png/jpg) painted under the words, when the card says the words sit over the film\'s own picture.'),
    },
  }, async ({ name, kind, room, ground, light, text, em, ink, font, italic, weight, caps, track, lead, place, wrap, image, width, film, screen, css, head, mark, wordmark, product, line, url, bg, design }) => {
    // a file the user attached is never shown as it is (a surface or background still IS that file to H3): its still is drawn from it
    const raw = [image, bg].find(attached);
    if (raw) return fail(`still: ${raw} is a file the user attached, which H3 never gets as it is: draw its still with the storyboard tool (the photo as content); a logo goes in kind=lockup as mark= or wordmark=.`);
    const out = path.join(outDir('stills'), `${slug(name)}.png`);
    const roomStyle = roomCss(room, ground, light);
    try {
      if (kind === 'screen') {
        if (!film || !screen) return fail('screen needs film= and screen=');
        const ws = path.join(REPO, FILMS[film]);
        const abs = path.resolve(screen);
        let rel = path.relative(ws, abs), tmp = null;
        if (rel.startsWith('..')) { tmp = path.join(ws, 'compositions/screens', `_h3-${slug(name)}.html`); fs.copyFileSync(abs, tmp); rel = path.relative(ws, tmp); }
        // scale so the 1440-wide screen fills `width` of the frame (4032 wide at 16:9); ch from the screen's own data-height if it has one
        const src = fs.readFileSync(abs, 'utf8');
        const cw = +(src.match(/data-width="(\d+)"/)?.[1] ?? 1440), ch = +(src.match(/data-height="(\d+)"/)?.[1] ?? 900);
        const scale = W * 9 > H * 16 + 9 ? Math.min((W * width) / cw, (H * width) / ch) : (W * width) / cw;  // 21:9: held to `width` of the height too
        try { await makeScreenStill({ ws, screen: rel, out, room: roomStyle, css, head: head ?? null, cw, ch, scale }); }
        finally { if (tmp) fs.rmSync(tmp, { force: true }); fs.rmSync(path.join(ws, `verify-still-${path.basename(rel, '.html')}.html`), { force: true }); }
      } else if (kind === 'lockup') {
        if (!product) return fail('lockup needs product= (line=, url= as the frame shows them)');
        // a logo the planner drew itself is never the brand's (fgem9-cinematic wrote its own fake Canva wordmark, 2026-10-06): only a logo the
        // screenshot tool captured (shots/) or the brief gives (agent/refs/) is used
        const own = (f) => !f || attached(f) || [path.join(REPO, 'agent/refs'), path.join(process.env.H3_OUT || RUNS, 'shots')].some((d) => path.resolve(f).startsWith(d + '/'));
        if (!own(mark) || !own(wordmark)) return fail(`lockup: ${own(mark) ? wordmark : mark} is not the brand's own logo. Use the logo the screenshot tool captured (in shots/) or the one the brief gives; with neither, leave mark and wordmark out, and the site's app icon and the typed name are used.`);
        const lightRoom = /^#?[0-9a-f]{6}$/i.test(ground || '') && (([r, g, b]) => 0.2126 * r + 0.7152 * g + 0.0722 * b)((ground.replace('#', '').match(/../g)).map((h) => parseInt(h, 16) / 255)) > 0.6;
        // one logo in the whole film: the brand's own lockup the screenshot tool captured, whatever mark/wordmark is passed
        // (a logo the user attached, auto.mjs --ref brand:, is shown instead: the user chose it)
        const shot = path.join(process.env.H3_OUT || RUNS, 'shots', 'logo.png'); let logo = fs.existsSync(shot) && !attached(mark) && !attached(wordmark) ? shot : undefined;
        // a captured logo drawn for the other ground (Loom's black "ATLASSIAN Loom" on a dark end card) does not read: then the
        // site's app icon (screenshot tool, shots/icon.png) is the mark and the name is typed in the lockup's own readable ink
        if (logo && /^#?[0-9a-f]{6}$/i.test(ground || '')) {
          let unreadable = false;
          try { unreadable = execSync(`${PY} -W ignore -c "import sys;from PIL import Image;L=lambda c:[(v/255/12.92 if v/255<=0.03928 else ((v/255+0.055)/1.055)**2.4) for v in c];Y=lambda c:0.2126*c[0]+0.7152*c[1]+0.0722*c[2];g=Y(L(bytes.fromhex(sys.argv[2]))) ;px=[p for p in Image.open(sys.argv[1]).convert('RGBA').resize((200,64)).getdata() if p[3]>200];r=[(max(Y(L(p[:3])),g)+0.05)/(min(Y(L(p[:3])),g)+0.05) for p in px];print(1 if px and sum(1 for x in r if x<2.5)/len(px)>0.2 else 0)" '${shot}' '${(ground || '').replace('#', '')}'`).toString().trim() === '1'; } catch {}
          // a one-colour logo (Canva's site serves its wordmark in white for a dark header) is recoloured to read on this ground instead of dropped
          if (unreadable) { try { const rc = path.join(path.dirname(out), `${slug(name)}-logo-recoloured.png`); const g0 = (ground || '').replace('#', '');
            const lum = ((c) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])(g0.match(/../g).map((h) => parseInt(h, 16) / 255));
            if (execSync(`${PY} -c "import sys;from PIL import Image;import numpy as np;a=np.asarray(Image.open(sys.argv[1]).convert('RGBA')).astype(int);op=a[...,3]>128;c=a[op][:,:3];one=len(c)>0 and (np.abs(c-np.median(c,0)).max(1)<40).mean()>0.9;a[...,:3]=np.array([int(sys.argv[3][i:i+2],16) for i in (0,2,4)]);one and Image.fromarray(a.astype('uint8'),'RGBA').save(sys.argv[2]);print(1 if one else 0)" '${shot}' '${rc}' '${lum < 0.35 ? 'ffffff' : '111111'}'`).toString().trim() === '1') { logo = rc; unreadable = false; } } catch {} }
          if (unreadable) { logo = undefined; const icon = ['png', 'jpg', 'webp'].map((e) => path.join(path.dirname(shot), `icon.${e}`)).find((f) => fs.existsSync(f)); if (icon) mark = icon; wordmark = undefined; }
        }
        // a dark logo file on a dark ground (or a light one on a light ground) is shown reversed, as brands print theirs: every fill or
        // stroke colour that all but vanishes on the ground (contrast < 1.6) turns white, or near-black on a light ground (2026-10-06:
        // Cal.com's #292929 wordmark and Notion's #111111 mark on black came out grey at the end of light-sweep; at 2.5 it also blacked out Spotify's green on off-white)
        if (/^#?[0-9a-f]{6}$/i.test(ground || '')) {
          const Y = (h) => { const v = h.replace('#', '').replace(/^(.)(.)(.)$/, '$1$1$2$2$3$3').match(/../g).map((x) => parseInt(x, 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
          const g = Y(ground), to = g < 0.18 ? '#ffffff' : '#111111';
          const reverse = (f) => { if (!f?.endsWith('.svg')) return f; let n = 0;
            const s = fs.readFileSync(f, 'utf8').replace(/(fill|stroke)="(#[0-9a-f]{6}|#[0-9a-f]{3})"/gi, (m, a, h) => { const l = Y(h); return (Math.max(l, g) + 0.05) / (Math.min(l, g) + 0.05) < 1.6 ? (n++, `${a}="${to}"`) : m; });
            if (!n) return f; const r = path.join(path.dirname(out), `${slug(name)}-${path.basename(f, '.svg')}-reversed.svg`); fs.writeFileSync(r, s); return r; };
          mark = reverse(mark); wordmark = reverse(wordmark);
        }
        const bgCss = bg && fs.existsSync(bg) ? `#root{background:url(data:image/${bg.endsWith('.png') ? 'png' : 'jpeg'};base64,${fs.readFileSync(bg).toString('base64')}) center/cover no-repeat !important}` : '';
        if (!logo && !mark && !wordmark) { const icon = ['png', 'jpg', 'webp'].map((e) => path.join(path.dirname(shot), `icon.${e}`)).find((f) => fs.existsSync(f)); if (icon) mark = icon; } // no captured logo: the site's app icon is the mark beside the typed name (Squoosh's lockup had no mark at all)
        if (design) { // the film's own endcard (Alec 2026-10-09: "its own font and its own layout"): the one picture in it is the brand's own logo
          // a Google Fonts @import is dropped, not refused: the renderer fetches any family named in font-family (v3-b18v: the refusal cost a request)
          design = design.replace(/@import\s+(?:url\(\s*(['"]?)https?:\/\/fonts\.googleapis\.com\/[^'")]*\1\s*\)|(['"])https?:\/\/fonts\.googleapis\.com\/[^'"]*\2)[^;]*;?/gi, '');
          if (/<svg\b|url\(|@import/i.test(design) || /<img\b(?![^>]*\bsrc=["']LOGO["'])/i.test(design)) return fail('lockup design: no <svg>, no other <img>, no url() or @import. The one picture is <img src="LOGO"> (the brand\'s own logo); the background is bg= or a CSS colour or gradient; every word is typed.');
          const L = logo || wordmark || mark;
          if (/src=["']LOGO["']/.test(design) && !L) return fail('lockup design: this brand has no logo here (none captured, none given): take out <img src="LOGO"> and type the name.');
          const uri = L ? `data:image/${L.endsWith('.svg') ? 'svg+xml' : L.match(/\.(\w+)$/)[1].replace('jpg', 'jpeg')};base64,${fs.readFileSync(L).toString('base64')}` : '';
          await makeStill({ out, kind: 'design', design: design.replace(/src=["']LOGO["']/g, `src="${uri}"`), css: bgCss, room: roomStyle });
        } else         await makeLockup({ out, logo, mark, wordmark, name: product, line, url, room: roomStyle, head: head ?? null, css: bgCss, ink: ink && ink.toLowerCase() !== '#ffffff' ? ink : (lightRoom ? '#111111' : null) }); // a light room gets dark type (the endcard template is white-on-dark)
      } else if (kind === 'text') {
        if (!text) return fail('text needs text=');
        // bg = a picture painted under the words, so each type still is the finished frame (minimal-mono's one held photograph, 2026-10-06)
        const css = bg && fs.existsSync(bg) ? `#root{background:url(data:image/${bg.endsWith('.png') ? 'png' : 'jpeg'};base64,${fs.readFileSync(bg).toString('base64')}) center/cover no-repeat !important}` : '';
        await makeStill({ out, kind: 'text', text, em, ink, font, italic, weight, caps, track, lead, place, wrap, css, room: roomStyle, head: head ?? null });
      } else if (kind === 'surface') {
        if (!image || !fs.existsSync(image)) return fail(`surface needs an existing image= (${image})`);
        await makeStill({ out, kind: 'surface', image, widthFrac: room === 'none' ? 1 : width, shadow: room !== 'none', room: roomStyle, head: head ?? null });
      } else await makeStill({ out, kind: 'blank', room: roomStyle, head: head ?? null });
    } catch (e) { return e.fatal ? fatal('still', e.message.slice(0, 1500)) : fail(`still failed: ${e.message.slice(0, 1500)}`); }
    return reply({ file: out, kind }, out);
  });

  // `frame` is the one that matters: Nano Banana draws the FINISHED still — the surface already in the
  // film's room, lit, at its size — so nothing is composited afterwards. That kills the whole class of
  // bug that came from generating a subject and then framing it ourselves: the model has no alpha, so it
  // always painted a field behind the subject, and floating that field on our own room read as a grey box
  // behind the UI (mh1, 2026-09-19). The room's consistency across stills, which our painted room used to
  // guarantee, is held instead by passing the FIRST finished still back in as a reference to every later
  // one — that is what `refs` is for here.
  const KINDS = {
    frame: (p, n) => `ONE finished frame of a launch film, filling the whole picture edge to edge. ${p}\n\nRules, which override anything above that disagrees: this is the complete frame as it will appear in the film — no border, no margin, no letterbox, no card around the picture, no caption, no watermark, no panel numbers. Flat design. 1.5x zoom. No nested cards. ${n ? 'An attached screenshot is the PRODUCT, not the picture: take the application\'s own interface out of it and leave behind everything that is not the product — the browser window, address bar, tabs, bookmarks, OS menu bar and traffic lights, extension chips, cookie banners, chat bubbles. The interface itself keeps its layout, text, icons, colours and proportions exactly: do not redraw, restyle, reflow or translate it, and invent no screen, panel, chip, icon or control it does not have. Any attached frame of this same film is the ROOM: use its exact ground colour, its exact light and its exact depth so every frame of the film is in one continuous space.' : ''} Any text named above is flat, sharp type spelled exactly as written and is the only text in the picture.`,
    edit: (p, n) => `The attached image is a real screenshot of a web app. Redesign it as the SIMPLIFIED HERO VERSION of this screen that a product launch video would show, the way Apple or a high-end SaaS launch film shows an app: the same theme and colours, the same parts in the same places, but everything inside is reduced to what reads from across the room. Rules: ${p} All of that type is set about twice as large as in the screenshot, in the same UI sans-serif, and there is no other text anywhere: no browser window, no address bar, no tabs, no OS chrome, no small icons or hints. Do not add any element the screenshot does not have. Crisp flat UI, no browser chrome.\n\nRules, and they override anything above that disagrees: the interface FILLS THE WHOLE FRAME, edge to edge. Draw NO container around it — no card, no rounded panel, no border, no bezel, no device, no window, no drop shadow, no margin, no background behind it. The interface's own outermost edge IS the edge of the picture.`,
    cutout: (p) => `${p}. A single isolated subject, complete and fully in frame, centered on a pure solid white background, nothing else in the image, no shadow on the ground.`,
    backdrop: (p) => `${p}. Full-bleed, edge to edge. No text.`,
    diagram: (p, n) => `Draw ONE frame of an explainer. ${p}\n\nEvery label and word named above is set as flat, sharp type, spelled exactly as written, and nothing else is written.${n ? ' Keep every box and line exactly where it is in the attached previous frame; only add what this frame adds.' : ''} No grid, no borders, no captions, no panel numbers, no watermark.`,
    free: (p) => p,
  };
  server.registerTool('image', {
    description: 'Nano Banana 2 (gemini-3.1-flash-image). NEVER draw the product\'s logo, its symbol or its name as lettering with this tool, in any form: the film has ONE logo, the one the screenshot tool captured (logo = symbol and name together, logo_mark = the symbol alone, logo_word = the name alone) or the brief gives; with neither, the film has NO mark at all and its lockup is the typed name alone, so never draw or design a symbol for the product unless the brief asks you to design the mark; show any of them with the still tool (kind=lockup, or kind=surface image=<that file>). A still that shows the PRODUCT\'s screen is ALWAYS kind=edit, never kind=frame: first the hero from the screenshot, then every later still from the previous one (below). kind=frame: a frame with NO product screen in it (a graphic, avatars, an object) — draw the FINISHED frame, standing in the film\'s room, lit, at its size, filling the picture. From the second still on, attach the film\'s FIRST finished still so every frame shares one room. Nothing is composited afterwards. Every product still shows the product IN USE with content in it (a drawing on the canvas, a filled calendar, a sent message): never an empty canvas, a blank page or a welcome screen, which simplify to nothing. If the screenshot is empty, the hero edit draws the in-use content into it (name it in the keep-list: the drawing, the filled rows). STORY CONTINUITY: once the first product still exists, every later still of that product (another state, a dialog opening, a second user joining) is made FROM THE PREVIOUS ONE in story order, that image attached, kind=edit, prompt starting "Return this exact image unchanged except …" — whatever changes, the rest of the screen carries forward, so the canvas never resets or jumps to other content. kind=edit has exactly TWO uses. (1) THE HERO — ONE call per screenshot, never more: the screenshot attached, redrawn as the SIMPLIFIED HERO VERSION of that screen (same theme and colours, same parts in the same places, everything reduced to what reads from across the room). Your prompt is only a KEEP-LIST: every element that stays with its exact string, region by region, then what goes ("No toggle, no …"). Every control keeps its place and size in the screenshot: a small button stays a small button in the product\'s own style, never blown up into a big labelled tile. Never describe a background or where the app sits; the tool makes it fill the frame. (2) EVERY OTHER STATE OF THAT SCREEN (a column emptied, a field not yet filled) is made from THE HERO IMAGE attached (never the screenshot again), so every still of the product matches; it starts "Return this exact image unchanged except …". Never make a close-up or crop still: a still is always the whole screen, and the ROWS frame close on part of it ("the frame swings onto the time slots, filling the frame") — H3 moves the camera; every approved clip did it this way, and Nano Banana cannot crop. APPROVED EXAMPLES (Cal.com, the stills Alec approved). Hero, the booking screenshot attached: \'the left column keeps, top to bottom: the subtitle "Team", the headline "Acme Introductionary Call", the duration pill "30m", the location icon with "Cal Video", and the timezone "America/Toronto". The middle column keeps the month header "September 2026" with small nav arrows, the day-of-week abbreviations "MON TUE WED THU FRI SAT SUN", and the clean calendar day grid with "25" prominently selected in a solid black rounded tile with white text. The right column keeps the header "Fri 25th" and the clean vertical list of rounded time slot buttons: "2:30pm", "2:45pm", "3:00pm", "3:15pm", "3:30pm", "3:45pm", "4:00pm". No toggle, no "Overlay my calendar", no long description paragraph, no 12h/24h toggle.\' State, the hero attached: \'Return this exact image unchanged except the right-hand column: remove all time slot buttons so the column is empty clean white under the header "Fri 25th", preserving every other pixel, layout, and text exactly as attached.\' Write yours in exactly these two shapes for your product. It may NOT invent a screen, panel or control the product does not have: if the film needs a surface no screenshot shows, draw it with kind=frame; cutout: one subject on pure white, matted to a transparent PNG (props, figures, plates — describe the WHOLE silhouette, never a hand at the frame edge); backdrop: full-bleed scene; diagram: an exact-text frame (name every box, label and arrow; attach the previous frame to keep the layout); free: your prompt verbatim. Up to 14 reference images. Style consistency: put the film\'s one locked style sentence at the start of EVERY prompt; for identity, attach the earlier plate of the same subject and say "keep the exact same identity and rendering style". Nano Banana makes UI and simple keyframes only, never composed or stylised multi-object shots. Cached by content: identical calls cost nothing. Returns the path and a thumbnail: LOOK at it and regenerate anything with a wrong label, an invented element, or a broken layout (an element sticking out of its panel or dialog, text over text).' + VIEW_NOTE + (REFS ? ' THE USER\'S REFERENCES (the brief\'s list, files in attached/): a photo of a person, a thing or a place is never an edit here (kind=edit redraws product screenshots) and never drawn from words alone: its subject still comes from the storyboard tool, the photo as `content`. A brand kit\'s logo is never drawn: the still tool shows it (kind=lockup, mark= or wordmark= the logo file). A moodboard\'s images are style refs only.' : ''),
    inputSchema: {
      name: z.string(),
      kind: z.enum(['frame', 'edit', 'cutout', 'backdrop', 'diagram', 'free']),
      prompt: z.string().describe('the slot text: subject/scene, the look sentence, any exact strings in quotes with their font style and placement'),
      refs: z.array(z.string()).max(14).default([]).describe('local image paths: screenshots (edit), the previous plate (identity), the previous frame (diagram), style stills'),
      aspect: (R === '16:9' ? z.enum(['1:1', '3:2', '2:3', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9']).default('16:9') : z.enum(['1:1', '3:2', '2:3', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9']).optional())
        .describe('the film\'s aspect for a `frame`; for other kinds, the shape that fits the subject so little background is drawn' + (R === '16:9' ? '' : `. Unset: ${R} (this film's frame); an edit keeps the shape of the image it edits`)),
      size: z.enum(['1K', '2K']).default('1K').describe('1K for anything H3 will look at; 2K only for a still a code layer shows full-frame'),
    },
  }, async ({ name, kind, prompt, refs, aspect, size }) => {
    aspect ??= kind === 'edit' && refs[0] ? shape(refs[0]) : R;
    let ground = '';
    if (kind === 'edit' && refs[0]) try { ground = execSync(`${PY} -c "from PIL import Image;from collections import Counter;im=Image.open('${refs[0]}').convert('RGB').resize((64,36));print('#%02x%02x%02x'%Counter(im.getdata()).most_common(1)[0][0])"`).toString().trim(); } catch {}
    // An edit of the run's OWN still (a state derived from the fullest one) is sent as written: the hero wrapper is for
    // real screenshots, and on a derived state it zooms and redraws (high8: the before-state came back a close crop).
    const run = path.resolve(process.env.H3_OUT || RUNS), own = kind === 'edit' && refs[0] && ['images', 'stills', 'storyboard'].some((d) => path.resolve(refs[0]).startsWith(path.join(run, d) + path.sep));
    if (own) ground = '';
    const text = (own ? KINDS.free : KINDS[kind])(prompt, refs.length) + (ground ? `\n\nGROUND COLOUR: ${ground} — the scene background is this colour, sampled from the real product; it overrides any background colour named above.` : '');
    const parts = refs.map((f) => ({ inlineData: { mimeType: f.endsWith('.jpg') || f.endsWith('.jpeg') ? 'image/jpeg' : 'image/png', data: fs.readFileSync(f).toString('base64') } }));
    const model = imageModel(), key = createHash('sha1').update([model, kind, aspect, size, text, ...refs.map((f) => createHash('sha1').update(fs.readFileSync(f)).digest('hex'))].join('|')).digest('hex');
    const cache = path.join(REPO, 'agent/artcache'); fs.mkdirSync(cache, { recursive: true });
    const cached = path.join(cache, `${key}.png`);
    const out = path.join(outDir('images'), `${slug(name)}.png`);
    if (!fs.existsSync(cached)) {
      const ai = quotaWait(new GoogleGenAI({ vertexai: true, project: process.env.GOOGLE_VERTEX_PROJECT, location: process.env.GOOGLE_VERTEX_LOCATION || 'global', httpOptions: { retryOptions: { attempts: 6, initialDelay: 5, maxDelay: 60 } } }));  // SDK retries 429/5xx (many films at once hit Nano Banana's quota)
      let raw = null;
      for (let a = 0; a < 4 && !raw; a++) {
        try {
          const res = await ai.models.generateContent({ model, contents: [{ role: 'user', parts: [...parts, { text }] }], config: { responseModalities: ['IMAGE'], imageConfig: { aspectRatio: aspect, imageSize: size } } });
          const part = res.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
          if (!part) throw new Error('no image returned: ' + (res.candidates?.[0]?.finishReason ?? 'empty'));
          raw = Buffer.from(part.inlineData.data, 'base64');
        } catch (e) { if (a === 3) return refusal(e) ? fail(`image failed: ${failWhy(e)}${REFUSED_HINT}`) : fatal('image', `${name}: ${failWhy(e)}`); if (!refusal(e)) await new Promise((r) => setTimeout(r, 15000 * (a + 1))); }
      }
      fs.writeFileSync(cached + '.raw', raw);
      if (kind === 'cutout') {
        const r = spawnSync(PY, ['-c', 'import sys\nfrom rembg import remove\nfrom PIL import Image\nremove(Image.open(sys.argv[1])).save(sys.argv[2])', cached + '.raw', cached], { encoding: 'utf8' });
        if (r.status !== 0) return fatal('image', `rembg failed (pip install rembg onnxruntime into .venv): ${r.stderr?.slice(0, 300)}`);
      } else fs.copyFileSync(cached + '.raw', cached);
    }
    fs.copyFileSync(cached, out);
    return reply({ file: out, kind, cached: fs.existsSync(cached + '.raw') ? 'hit-or-new' : 'new', cost_usd: NB[model]?.[size] }, out);
  });

  // Launch films only. On a painted film it returns ok for every prompt by design (below), yet Gemini spent a turn on it after
  // each clip (557 calls in 182 runs, 2026-10-07 audit), so painted sessions are not offered it.
  if (process.env.H3_PAINTED !== '1') server.registerTool('check_prompt', {
    // H3_CHECK_HOOK=1 (2026-10-10, cost): the Claude planner's write hook (agent/h3film/planner-check.mjs) runs this same check on every
    // clip prompt it writes and returns the result with the write, so the tool is only for re-checking; other planners keep the old text.
    description: (process.env.H3_CHECK_HOOK === '1' ? 'Every clip prompt you write is checked automatically: the result comes back with the write itself, so write all clip prompts in one batch and fix what it lists; call this tool only to re-check a prompt after a fix.' : 'Call after writing EACH clip prompt, and again after every fix, until it returns ok.') + ' Lists every beat row where something ARRIVES (appears, opens, enters, is pressed, writes itself, lands…) that names no Image the prompt attaches. MiniMax paints such a moment from the reference video, i.e. another product\'s UI (measured twice: Ghost Note\'s pill row, Claude\'s app). For each row listed: make the still that shows that state (kind=edit from the previous still, or a type still for a line), add its Image line and cite it in the row ("…: Image 4"); or cite the Image that already shows it. Never delete the row to pass. The runner refuses to render a clip that fails this.',
    inputSchema: { file: z.string().describe('absolute path of prompts/<clip>.txt') },
  }, async ({ file }) => {
    const text = fs.readFileSync(file, 'utf8');
    // Launch films only (every launch prompt carries "Software launch film", no painted one does; 98/98 runs). Painted
    // rows never cite a still by design: on them every flag was false and Gemini weakened the motion to pass (acc-doc-maps).
    if (!text.includes('Software launch film')) return reply({ ok: true });
    const rows = uncoveredRows(text);
    return reply(rows.length ? { ok: false, uncovered: rows } : { ok: true });
  });

  // Not offered to painted sessions (PAINTED §6: never called; the runner joins): its seconds min 1 read as a floor on a shot's
  // span, and the AMV planner held its whole hype at 2-beat shots 'because join_film needs a span of at least 1 s' (v4-r02, 2026-10-09).
  if (process.env.H3_PAINTED !== '1') server.registerTool('join_film', {
    description: 'The finished film: each clip trimmed to its PLANNED seconds (fal returns up to ~0.6 s extra of frozen frame), concatenated in order, the whole-film soundtrack laid over once from t=0. Seams are hard cuts by construction; no crossfade, no retime. Returns the mp4 path.',
    inputSchema: {
      clips: z.array(z.object({ file: z.string(), seconds: z.number().min(1).max(15).describe('the clip\'s real span in the film (end − start), not its render length') })).min(1),
      music: z.string().optional().describe('the whole-film soundtrack (make_soundtrack `file`, or a library track)'),
      name: z.string().default('final'),
    },
  }, async ({ clips, music, name }) => {
    try {
      const size = execSync(`ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "${clips[0].file}"`).toString().trim() || '832x480';
      const out = path.join(process.env.H3_OUT || RUNS, `${slug(name)}.mp4`);
      const r = await joinFilm({ clips, music, out, size });
      return { content: [{ type: 'text', text: JSON.stringify(r) }] };
    } catch (e) { return fail(`join_film failed: ${e.message.slice(0, 800)}`); }
  });

  // 2026-10-10: storyboard (mcp.mjs registers it before this) also returns each frame's view inline, at the size the image, still
  // and screenshot tools return theirs (thumb, 900 px): the planner opened 100 of the 101 frames drawn on 10-10 with a request of
  // its own (0.85 a painted film). One view per frame, never a contact sheet (a misspelled label can hide at sheet size). The files
  // and the result's text are as before (H3 gets the full stills). STORYBOARD_INLINE=0 (env or .env.local) turns it off.
  const sb = server._registeredTools?.storyboard;
  if (sb && process.env.STORYBOARD_INLINE !== '0') { const draw = sb.handler; sb.update({ callback: async (args, extra) => {
    const r = await draw(args, extra); let views = [];
    try { views = JSON.parse(r.content[0].text).views || []; } catch {}  // a failure or "STILL WORKING" (H3_CALL_LIMIT_S) passes as it is
    const seen = views.flatMap((v, i) => { const t = v && thumb(v); return t ? [{ type: 'text', text: `Frame ${i + 1} (${path.basename(v)}):` }, { type: 'image', data: t, mimeType: 'image/jpeg' }] : []; });
    return seen.length ? { ...r, content: [...r.content, ...seen] } : r; } }); }
}

// The spend gate for generate_video: a run has a budget (H3_BUDGET_USD, default 5); every render is priced
// before the call and refused past the cap. The model never decides to spend past it; a human raises it.
export function spendGate(costUsd) {
  const cap = +(process.env.H3_BUDGET_USD || 5);
  const ledger = path.join(process.env.H3_OUT || RUNS, 'spend.json');
  let spent = 0; try { spent = JSON.parse(fs.readFileSync(ledger, 'utf8')).spent || 0; } catch {}
  if (spent + costUsd > cap + 1e-9) return { ok: false, msg: `REFUSED, nothing rendered: this render costs $${costUsd.toFixed(2)} and the run has spent $${spent.toFixed(2)} of its $${cap.toFixed(2)} budget. Do not retry or reduce scope on your own: write NOTES.md with what is done and what remains, and stop; Alec raises the budget (H3_BUDGET_USD) if he wants the rest.`, spent, cap };
  return { ok: true, spent, cap, commit: () => fs.writeFileSync(ledger, JSON.stringify({ spent: spent + costUsd, cap })) };
}
