import json, pathlib, sys, time
sys.path.insert(0, '/tmp/v3/magicdrama')
from magicdrama.claude_fallback import claude_text
from magicdrama.validation import parse_json_from_text
from magicdrama.stages.series import sanitize

RUN = pathlib.Path('/tmp/v3/honesty_run'); OUT = pathlib.Path('/tmp/v3/honesty_v5')
bible = json.loads((RUN/'bible.json').read_text()); bible.setdefault('slug','the-honesty-intern')
mem = json.loads((RUN/'story_memory.json').read_text())
ev = json.loads((OUT/'eval.v5.json').read_text())
voices = {c['name']: c.get('voice','') for c in bible['characters']}

by_ep = {}
for f in ev.get('failures', []):
    by_ep.setdefault(f.get('ep'), []).append(f)

for ep, fails in sorted(by_ep.items()):
    src = OUT/f"ep{ep:02d}.v5.json"
    script = json.loads(src.read_text())
    (OUT/f"ep{ep:02d}.v5.r0.json").write_text(src.read_text())               
    prompt = (f"You are repairing episode {ep} of a realistic office microdrama after a strict dialogue judge failed it. "
        f"Series bible: {json.dumps(bible)}. Story memory (never contradict): {json.dumps(mem)}. "
        f"JUDGE FAILURES to fix (quote + why): {json.dumps(fails)}. "
        "Rules: fix ONLY these problems with minimal edits to the affected scenes/lines. Replacement lines must be plain English a real person would say in that exact emotional moment - no aphorisms, no recycled stock phrases, no quips after raw emotion, no repeated lines from ANY episode. "
        "Keep: scene count, seconds, locations, plot beats, facts, rupee amounts, voice descriptors verbatim, new_facts. "
        f"Episode JSON: {json.dumps(script)}. "
        'Return the full repaired episode as ONE LINE compact JSON, same shape. JSON only.')
    for att in (1, 2):
        try:
            text, _ = claude_text(prompt, 7000, 0.4, note=f"v5-repair-ep{ep}")
            fixed = sanitize(parse_json_from_text(text))
            assert len(fixed.get('scenes', [])) == len(script['scenes']), "scene count changed"
            src.write_text(json.dumps(fixed, ensure_ascii=False))
            print(f"ep{ep} repaired ({len(fails)} failures)", flush=True)
            break
        except Exception as e:
            print(f"ep{ep} attempt{att} ERROR {type(e).__name__}: {e}", flush=True)
            if att == 2: raise
            time.sleep(3)
print("REPAIR-ALL-DONE", flush=True)
