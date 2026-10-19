import json

from . import config

def parse_json_from_text(text, expect=None):
    start = len(text)
    opener = None
    for c in ("{", "["):
        i = text.find(c)
        if i != -1 and i < start:
            start, opener = i, c
    if opener is None:
        raise ValueError("no json in model output")
    closer = "}" if opener == "{" else "]"
    end = text.rindex(closer)
    if end < start:
        raise ValueError("no json in model output")
    parsed = json.loads(text[start: end + 1])
    if expect is not None and not expect(parsed):
        raise ValueError("json did not match expected shape")
    return parsed
def validate_brief(brief):
    errs = []
    if not brief.get("title"):
        errs.append("brief.title missing")
    chars = brief.get("characters", [])
    if not (2 <= len(chars) <= 8):
        errs.append(f"brief has {len(chars)} characters (need 2-8)")
    names = [c.get("name") for c in chars]
    if len(names) != len(set(names)):
        errs.append("duplicate character names in brief")
    for c in chars:
        for f in ("name", "role", "imagined"):
            if not c.get(f):
                errs.append(f"brief character missing {f}")
    if not brief.get("episodes"):
        errs.append("brief.episodes missing")
    if not brief.get("episode_seconds"):
        errs.append("brief.episode_seconds missing")
    return errs

def validate_canon(canon):
    errs = []
    if len(canon) != config.CANON_LAST_EP:
        errs.append(f"canon has {len(canon)} episodes, expected {config.CANON_LAST_EP}")
    if [e.get("ep") for e in canon] != list(range(1, config.CANON_LAST_EP + 1)):
        errs.append("canon episode numbers not 1..10")
    for e in canon:
        for f in ("ep", "title", "hook", "beat", "reversal", "cliffhanger"):
            if not e.get(f):
                errs.append(f"canon E{e.get('ep')} missing {f}")
    return errs

def validate_config():
    errs = []
    if config.EPISODE_CAP_CREDITS <= 0 or config.BATCH_CAP_CREDITS < config.EPISODE_CAP_CREDITS:
        errs.append("credit caps inconsistent")
    if sum(config.SHOT_SECONDS) != config.EP_SECONDS:
        errs.append(f"shot seconds sum {sum(config.SHOT_SECONDS)} != {config.EP_SECONDS}")
    for k in ("writer", "judge", "vision_judge", "tts"):
        if not config.NVIDIA_MODELS.get(k):
            errs.append(f"NVIDIA_MODELS.{k} missing")
    if config.NVIDIA_MODELS.get("writer") == config.NVIDIA_MODELS.get("judge"):
        errs.append("writer and judge must be different models (decision D8)")
    if not config.MH_VIDEO_MODEL or not config.MH_IMAGE_MODEL:
        errs.append("Magic Hour models missing")
    if config.CANON_LAST_EP >= config.EPISODES_TOTAL:
        errs.append("canon range exceeds season")
    return errs

