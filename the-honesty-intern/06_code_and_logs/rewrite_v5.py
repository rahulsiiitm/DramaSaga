import json, os, pathlib, sys, time
sys.path.insert(0, '/tmp/v3/magicdrama')
from magicdrama.claude_fallback import claude_text
from magicdrama.validation import parse_json_from_text
from magicdrama.stages.series import sanitize

RUN = pathlib.Path('/tmp/v3/honesty_run'); OUT = pathlib.Path('/tmp/v3/honesty_v5')
bible = json.loads((RUN/'bible.json').read_text()); bible.setdefault('slug','the-honesty-intern')
arc = json.loads((RUN/'arc.json').read_text())
voices = {c['name']: c.get('voice','') for c in bible['characters']}
cast = [c['name'] for c in bible['characters']]

REWRITE_RULES = """REWRITE RULES:
1. PLAIN ENGLISH. No fancy words, no metaphors, no exposition. People talk like real Mumbai office workers.
2. CORRECT HUMAN EMOTION. Each character's feeling must match the moment (panic feels like panic, not narration of panic).
3. DIALOGUE FLOWS AS REAL CONVERSATION: lines reply to each other, people interrupt, trail off, use fillers ("haan", "wait", "no no"), say the small thing and mean the big thing. NO disconnected one-liners that could be shuffled. NEVER repeat the same or near-identical line twice in an episode.
4. SCENE-CLIP STRUCTURE: convert the episode into 4-6 CONTINUOUS SCENES, each 10-20 seconds, one location and unbroken time per scene, total 60-64 seconds. A scene = one generation clip, so dialogue within a scene must be performable in its seconds (~2.5 words/sec of speech plus acting beats; a 15s scene carries at most ~6 short lines).
5. Silence is allowed: a scene with no dialogue is fine when the acting carries it - mark dialogue [] explicitly.
6. KEEP LOCKED: plot beats and their order, the cliffhanger in/out, every rupee amount and fact, character names, each speaker's voice descriptor verbatim, new_facts.
7. Every speaking character must be in the cast list. Knowledge discipline: a character only references facts they know per story memory."""

SCHEMA = """Return ONE LINE of compact JSON (no indentation, no markdown fences):
{"ep": n, "title": str, "scenes": [{"n": int, "seconds": int (10-20), "location": str (one place), "keyframe_visual": str (the single start-frame image: who/where/wardrobe/props, photoreal, no text-on-screen), "camera": str, "dialogue": [{"character": str, "line": str (<=16 words), "voice": str (verbatim descriptor)}] (0-6 entries), "micro_acting": str, "narrative_job": str, "speaker_binding": str (main speaker or "")}], "new_facts": [{"fact": str, "learned_by": [str]}]}"""

def rewrite_ep(ep, prior_v5):
    v4 = json.loads((RUN/f"ep{ep:02d}.v4.json").read_text())
    arc_ep = next(a for a in arc['episodes'] if a['ep']==ep)
    prompt = (f"You are rewriting episode {ep} of a 10-episode realistic office microdrama for regeneration as long scene clips. "
        f"Series bible: {json.dumps(bible)}. Arc episode plan: {json.dumps(arc_ep)}. "
        f"Story memory (never contradict): {json.dumps(json.loads((RUN/'story_memory.json').read_text()))}. "
        + (f"Prior rewritten episodes (continuity record - never contradict dialogue, facts, amounts): {json.dumps(prior_v5)}. " if prior_v5 else "")
        + f"Current episode script to convert (keep its plot, beats and facts; fix its dialogue and structure): {json.dumps(v4)}. "
        + REWRITE_RULES + " " + SCHEMA + " JSON only.")
    text, usage = claude_text(prompt, 7000, 0.5, note=f"v5-rewrite-ep{ep}")
    return sanitize(parse_json_from_text(text))

FIRST = {c.split()[0]: c for c in cast}
def check(ep, s):
    errs=[]
    sc=s.get('scenes',[])
    if not (4<=len(sc)<=6): errs.append(f"scenes={len(sc)}")
    tot=sum(x.get('seconds',0) for x in sc)
    if not (55<=tot<=70): errs.append(f"total={tot}")
    for x in sc:
        if not (10<=x.get('seconds',0)<=20): errs.append(f"scene{x.get('n')}={x.get('seconds')}s")
        for d in x.get('dialogue',[]):
            ch = d.get('character','')
            if ch not in cast and ch not in FIRST: errs.append(f"bad speaker {ch}")
            if len(d.get('line','').split())>16: errs.append(f"long line scene{x.get('n')}")
            full = cast[cast.index(ch)] if ch in cast else FIRST.get(ch)
            if voices.get(full) and d.get('voice')!=voices[full]: errs.append(f"voice drift {ch} scene{x.get('n')}")
    return errs

def main():
    prior=[]
    for ep in range(1, 11):
        out = OUT/f"ep{ep:02d}.v5.json"
        if out.exists():
            prior.append(json.loads(out.read_text())); print(f"ep{ep} exists, skip", flush=True); continue
        s=None
        for attempt in (1,2):
            try:
                s = rewrite_ep(ep, prior)
                errs = check(ep, s)
                if errs:
                    print(f"ep{ep} validation {errs}, retrying" if attempt==1 else f"ep{ep} STILL BAD {errs}, keeping", flush=True)
                    if attempt==1: s=None; continue
                break
            except Exception as e:
                print(f"ep{ep} attempt{attempt} ERROR {type(e).__name__}: {e}", flush=True)
                if attempt==2: raise
                time.sleep(5)
        out.write_text(json.dumps(s, ensure_ascii=False))
        prior.append(s)
        print(f"ep{ep} v5 written: {len(s['scenes'])} scenes, {sum(x['seconds'] for x in s['scenes'])}s", flush=True)
    print("REWRITE-ALL-DONE", flush=True)

main()
