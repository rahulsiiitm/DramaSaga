from . import config
from .canon import CANON

def check_arc_batch(batch):
    errs = []
    canon_titles = {e["title"] for e in CANON}
    canon_eps = {e["ep"] for e in CANON}
    for e in batch:
        if e.get("ep") in canon_eps:
            errs.append(f"overwrites canon E{e.get('ep')}")
        if e.get("title") in canon_titles:
            errs.append(f"reuses canon title {e.get('title')}")
        for field in ("ep", "title", "hook", "beat", "reversal", "cliffhanger"):
            if not e.get(field):
                errs.append(f"E{e.get('ep')} missing {field}")
    eps = [e["ep"] for e in batch]
    if eps != sorted(eps) or len(set(eps)) != len(eps):
        errs.append("episode numbers not sequential")
    return errs

def validate_script(script, brief):
    errs = []
    shots = script.get("shots", [])
    if len(shots) != len(config.SHOT_SECONDS):
        errs.append("shot count")
    if [s.get("seconds") for s in shots] != config.SHOT_SECONDS:
        errs.append("timings")
    names = {c["name"] for c in brief["characters"]}
    for s in shots:
        for d in s.get("dialogue", []):
            if d.get("character") not in names:
                errs.append(f"unknown speaker {d.get('character')}")
            if len(str(d.get("line", "")).split()) > 14:
                errs.append(f"long line shot {s.get('n')}")
        if s.get("dialogue") and not s.get("lipsync"):
            errs.append(f"shot {s.get('n')} has dialogue but lipsync false")
        if s.get("dialogue") and not s.get("speaker_binding"):
            errs.append(f"shot {s.get('n')} has dialogue but no speaker_binding")
    return errs

