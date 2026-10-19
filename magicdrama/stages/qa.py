import json

from .. import config
from ..clients.nvidia import nvidia_chat, message_text
from .script import episode_script
from ..validation import parse_json_from_text

QUALITY_THRESHOLD = 70

FIX_HINTS = {
    "face": "Face drift across shots: restate hair, face shape, eyes, skin tone and signature clothing in every scene description, even when repeated, so the video model locks identity. Keep the character master attached as reference.",
    "lighting": "Light jumps between shots: state light direction (front, side, top, back), quality (hard or soft) and color temperature (warm, neutral, cool) at the start of every scene and keep one key/fill ratio for the episode.",
    "continuity": "Shot joins are breaking: every shot must name its transition action and repeat the props carried over from the previous shot.",
}

def judge_episode_frames(brief, ep):
    if config.DRY_RUN:
        return {"continuity": 90, "lighting": 90, "face": 90}
    prompt = (
        f"Score episode {ep} frames of {brief['title']} on three dimensions, 0-100 each: "
        "continuity (shot-to-shot joins, props, wardrobe), lighting (same light logic across shots), "
        "face (same face as the character master in every shot). "
        'Return JSON: {"continuity": int, "lighting": int, "face": int}. JSON only.'
    )
    out = nvidia_chat(config.NVIDIA_MODELS["vision_judge"], [{"role": "user", "content": prompt}], max_tokens=300, temperature=0.1)
    text = message_text(out)
    return parse_json_from_text(text)

def qa_episode(workdir, brief, ep):
    script = episode_script(workdir, brief, ep)
    scores = judge_episode_frames(brief, ep)
    weakest = min(scores, key=scores.get)
    result = {
        "shots": len(script["shots"]) == 10,
        "total_seconds": sum(s["seconds"] for s in script["shots"]) == config.EP_SECONDS,
        "scores": scores,
        "weakest": weakest,
        "pass": all(v >= QUALITY_THRESHOLD for v in scores.values()),
    }
    if not result["pass"]:
        result["fix_hint"] = FIX_HINTS[weakest]
    return result

