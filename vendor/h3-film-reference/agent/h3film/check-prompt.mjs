// check-prompt.mjs — every beat row that brings something INTO the film must name the Image that shows it.
// Measured 2026-09-29 over five films: both leaks (Ghost Note's pill row, Claude's app) sat on an arrival row with no
// still; the two approved films had none. With no picture, H3 paints that moment from the reference video.
//   node check-prompt.mjs <prompt.txt> …   (prints uncovered rows; exit 1 if any)
import fs from 'node:fs';

const ARRIVES = /\b(appears?|arriv(es|ing)|enters?|pops?( in)?|opens?|draws? itself|writes? itself|fades? (up|in)|rises (in|up|from|into)|blooms?|lands? (dead|in|on|centred|from|as)|slides? in|drops? in|is pressed|pressed)\b/i;
const CAMERA = /^[\d.\s-]+s\b\s*—\s*(HARD CUT:\s*)?(the|a) (frame|eye|camera|view)\b/i; // a camera move brings nothing in
const EMPTY = /\bopens? on (the |an? )?(empty|blank|bare|plain)\b/i; // a shot that opens on an empty field brings nothing in (2026-10-11: v42-x12's render was refused for "Opens on the empty soft pastel field")

export function uncoveredRows(text) {
  const imageLines = [...text.matchAll(/^@?Image ?(\d+) is\b.*$/gm)];
  const images = new Set(imageLines.map((m) => m[1])), described = imageLines.map((m) => m[0]).join('\n');
  const cites = (l) => [...l.matchAll(/@?Images? ?(\d+)(?:\s*(?:and|,|&)\s*@?(?:Image ?)?(\d+))?/g)].some((m) => images.has(m[1]) || images.has(m[2]));
  const quotedInImage = (l) => [...l.matchAll(/"([^"]{2,})"/g)].some((m) => described.includes(m[1]));
  return text.split('\n').map((l) => l.trim())
    .filter((l) => /^\d+(\.\d+)?(\s*-\s*\d+(\.\d+)?)?s\b/.test(l) && ARRIVES.test(l) && !CAMERA.test(l) && !EMPTY.test(l))
    .filter((l) => !cites(l) && !quotedInImage(l));
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  let bad = 0;
  for (const f of process.argv.slice(2)) {
    const rows = uncoveredRows(fs.readFileSync(f, 'utf8'));
    bad += rows.length;
    console.log(`${f}: ${rows.length ? rows.length + ' uncovered' : 'OK'}`);
    for (const r of rows) console.log('  ' + r.slice(0, 160));
  }
  process.exit(bad ? 1 : 0);
}
