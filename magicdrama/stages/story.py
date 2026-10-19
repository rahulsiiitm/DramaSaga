import json

from .. import config
from ..canon import CANON, CANON_FACTS
from ..clients.nvidia import nvidia_chat, message_text
from ..validators import check_arc_batch
from ..validation import parse_json_from_text

STORY_RULES = (
    "Hook in the first 0-3 seconds, a visible problem or strange sound, no logos. "
    "Exactly one power or knowledge reversal per episode. One detail planted early and paid off by the end. "
    "Dialogue lines under 14 words. The last frame asks a specific question the next episode answers. "
    "Each episode recaps the previous cliffhanger visually in its first 6 seconds. "
    "Photoreal K-drama slice-of-life comedy tone."
)
JSON_SHAPE_ARC = '{"episodes": [{"ep": n, "title": str, "hook": str, "beat": str, "reversal": str, "cliffhanger": str}], "is_last": bool}'

def load_arc(workdir):
    return json.loads((workdir / "season_arc.json").read_text())

def judge_arc_batch(batch):
    if config.DRY_RUN:
        return {"pass": True, "issues": []}
    canon_blob = json.dumps({"canon_episodes": CANON, "canon_facts": CANON_FACTS})
    prompt = (
        "You are the continuity judge of a microdrama. Canon episodes 1-10 are locked and must never be contradicted. "
        f"Canon and established facts: {canon_blob}. "
        f"New batch: {json.dumps(batch)}. "
        "Check: no contradiction of any canon fact, no reversal of a reveal, who-knows-what stays consistent, "
        "character voices and relationships match canon, open threads from E10 are respected. "
        'Return JSON: {"pass": bool, "issues": [str]}. JSON only.'
    )
    out = nvidia_chat(config.NVIDIA_MODELS["judge"], [{"role": "user", "content": prompt}], max_tokens=1500, temperature=0.1)
    text = message_text(out)
    return parse_json_from_text(text)

def plan_arc_batch(workdir, brief, start_ep, count=10):
    arc = load_arc(workdir)
    if len(arc["episodes"]) >= start_ep + count:
        return arc
    start_ep = max(start_ep, config.CANON_LAST_EP + 1)
    prompt = (
        f"You are the story editor of a photoreal microdrama. Title: {brief['title']}. Genre: {brief['genre']}. "
        f"Characters: {json.dumps([(c['name'], c['role'], c['imagined']) for c in brief['characters']])}. "
        f"Rules: {STORY_RULES} "
        f"Episodes 1-10 are locked canon: {json.dumps(CANON)}. Never contradict them. "
        f"Open threads you must respect: Taeyang's comeback offer to Mina, Jun-ho's label email, Han's quiet counter-move. "
        f"Episodes so far: {json.dumps(arc['episodes'])}. "
        f"Write episodes {start_ep} to {start_ep + count - 1} of {config.EPISODES_TOTAL}. "
        f"Return JSON with this exact shape: {JSON_SHAPE_ARC}. JSON only."
    )
    out = nvidia_chat(config.NVIDIA_MODELS["writer"], [{"role": "user", "content": prompt}], max_tokens=4000)
    if config.DRY_RUN:
        batch = [{"ep": i, "title": f"E{i}", "hook": "dry", "beat": "dry", "reversal": "dry", "cliffhanger": "dry"} for i in range(start_ep, start_ep + count)]
        is_last = start_ep + count > config.EPISODES_TOTAL
    else:
        text = message_text(out)
        parsed = parse_json_from_text(text)
        batch, is_last = parsed["episodes"], parsed.get("is_last", False)
    errs = check_arc_batch(batch)
    assert not errs, errs
    verdict = judge_arc_batch(batch)
    assert verdict["pass"], verdict["issues"]
    arc["episodes"].extend(batch)
    arc["episodes"].sort(key=lambda e: e["ep"])
    arc["complete"] = bool(is_last) and len(arc["episodes"]) >= config.EPISODES_TOTAL
    (workdir / "season_arc.json").write_text(json.dumps(arc, indent=2))
    return arc

def plan_full_arc(workdir, brief):
    for start in range(config.CANON_LAST_EP + 1, config.EPISODES_TOTAL + 1, 10):
        arc = plan_arc_batch(workdir, brief, start)
    return arc

