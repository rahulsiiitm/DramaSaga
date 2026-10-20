import json, pathlib, sys
sys.path.insert(0, '/tmp/v3/magicdrama')
from magicdrama.claude_fallback import claude_text
from magicdrama.validation import parse_json_from_text
from magicdrama.stages.series import sanitize

RUN = pathlib.Path('/tmp/v3/honesty_run'); OUT = pathlib.Path('/tmp/v3/honesty_v5')
bible = json.loads((RUN/'bible.json').read_text()); bible.setdefault('slug','the-honesty-intern')
arc = json.loads((RUN/'arc.json').read_text())
scripts = [json.loads((OUT/f"ep{e['ep']:02d}.v5.json").read_text()) for e in arc['episodes']]

DIMS = ("character (names, roles, physical details stable), "
 "timeline (order holds, each episode continues the previous cliffhanger), "
 "secrets (no knowledge violations; reveals planted before they land), "
 "voice (each character speaks in a stable register), "
 "tone (episodes match declared tone), "
 "realism (COLD-VIEWER test: scenes contain ordinary objects and actions; stakes stay human-sized; "
 "a cold viewer could retell goal, obstacle, choice, outcome for every episode), "
 "dialogue (NATURAL-SPEECH test: would a real human say this, here, like this? Lines reply to each other as real "
 "conversation; emotion matches the moment; plain everyday English; NO disconnected one-liners; NO repeated or "
 "near-identical lines within or across episodes; no exposition-as-dialogue), "
 "scene_continuity (each scene holds ONE location and unbroken time; scene transitions are motivated; characters "
 "and props do not teleport; seconds are plausible for the dialogue and action in the scene)")

prompt = ("You are the consistency, realism AND dialogue-quality judge for a 10-episode grounded office microdrama. "
    "Score each dimension 0-100: " + DIMS + ". "
    "Be a skeptical reviewer: a polite average is a fail. For every concrete failure give: ep, dimension, quote (exact line or beat), why. "
    "pass is true only if every score is 80 or above. "
    f"Series: {json.dumps({'concept': bible, 'arc': arc.get('episodes', []), 'episodes': scripts})}. "
    'Return JSON: {"scores": {"character": n, "timeline": n, "secrets": n, "voice": n, "tone": n, "realism": n, "dialogue": n, "scene_continuity": n}, '
    '"failures": [{"ep": n, "dimension": str, "quote": str, "why": str}], "pass": bool}. JSON only.')
for _att in (1, 2):
    try:
        text, usage = claude_text(prompt, 16000, 0.1, note="v5-judge")
        break
    except Exception as e:
        print(f"judge attempt{_att} ERROR {type(e).__name__}: {e}", flush=True)
        if _att == 2: raise
ev = sanitize(parse_json_from_text(text))
(OUT/'eval.v5.json').write_text(json.dumps(ev, indent=1, ensure_ascii=False))
print('SCORES:', json.dumps(ev.get('scores')))
print('PASS:', ev.get('pass'))
for f in ev.get('failures', [])[:15]:
    print('-', f.get('ep'), f.get('dimension'), '|', str(f.get('why'))[:130])
