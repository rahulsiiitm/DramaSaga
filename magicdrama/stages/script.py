import json

from .. import config
from ..clients.nvidia import nvidia_chat, message_text
from ..validators import validate_script
from ..validation import parse_json_from_text
from .story import STORY_RULES, load_arc

JSON_SHAPE_SCRIPT = '{"ep": n, "shots": [{"n": 1, "seconds": int, "visual": str, "camera": str, "dialogue": [{"character": str, "line": str}], "lipsync": bool, "narrative_job": str, "speaker_binding": str, "transition_in": str, "transition_out": str, "screen_direction": str}]}'

def episode_script(workdir, brief, ep):
    p = workdir / f"E{ep:02d}_script.json"
    if p.exists():
        return json.loads(p.read_text())
    arc = load_arc(workdir)
    ep_plan = arc["episodes"][ep - 1]
    is_canon = ep <= config.CANON_LAST_EP
    prompt = (
        f"Write the shot script for episode {ep} of {brief['title']}. Episode plan: {json.dumps(ep_plan)}. "
        f"Rules: {STORY_RULES} Shot timings must be exactly {config.SHOT_SECONDS} seconds. "
        f"Characters: {json.dumps([(c['name'], c['imagined']) for c in brief['characters']])}. "
        + ("This episode is LOCKED CANON: adapt it to shots, do not change the hook, beat, reversal, cliffhanger, or outcome. "
           if is_canon else "")
        + f"Return JSON with this exact shape: {JSON_SHAPE_SCRIPT}. JSON only."
    )
    out = nvidia_chat(config.NVIDIA_MODELS["writer"], [{"role": "user", "content": prompt}], max_tokens=4000)
    if config.DRY_RUN:
        script = {"ep": ep, "shots": [{"n": i + 1, "seconds": s, "visual": "dry", "camera": "dry", "dialogue": [], "lipsync": False, "narrative_job": "dry", "speaker_binding": "", "transition_in": "cut", "transition_out": "cut", "screen_direction": "lr"} for i, s in enumerate(config.SHOT_SECONDS)]}
    else:
        text = message_text(out)
        script = parse_json_from_text(text)
    p.write_text(json.dumps(script, indent=2))
    return script

__all__ = ["episode_script", "validate_script"]

