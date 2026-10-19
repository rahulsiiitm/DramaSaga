import json
import re
import time

from .. import config
from ..clients.nvidia import nvidia_chat, message_text
from ..validation import parse_json_from_text
from ..validators import validate_script

SHOT_LIST = ", ".join(str(s) for s in config.SHOT_SECONDS)

_ESC = re.compile(r"\\u([0-9a-fA-F]{4})")
_PUNCT = {"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
          "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
          "\u2026": "...", "\u00a0": " "}

def _clean_str(t):
    t = _ESC.sub(lambda m: chr(int(m.group(1), 16)), t)
    try:
        t = t.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    for k, v in _PUNCT.items():
        t = t.replace(k, v)
    return t

def sanitize(obj):
    if isinstance(obj, str):
        return _clean_str(obj)
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    return obj

def _expect_arc(v):
    return isinstance(v, list) or (isinstance(v, dict) and isinstance(v.get("episodes"), list))

def _expect_scores(v):
    return isinstance(v, dict) and isinstance(v.get("scores"), dict)

def _expect_shots(v):
    return isinstance(v, dict) and isinstance(v.get("shots"), list)

def call_json(kind, prompt, max_tokens, temperature, reasoning, expect=None):
    from ..claude_fallback import call_json_with_fallback
    return call_json_with_fallback(_call_json_nvidia, kind, prompt, max_tokens, temperature, reasoning,
                                   expect=expect,
                                   parse=lambda t, expect=None: sanitize(parse_json_from_text(t, expect=expect)))

def _call_json_nvidia(kind, prompt, max_tokens, temperature, reasoning, expect=None):
    text = ""
    last_err = None
    for attempt in range(2):
        p = prompt + (" IMPORTANT: reply with valid compact JSON and nothing else." if attempt else "")
        out = nvidia_chat(config.NVIDIA_MODELS[kind], [{"role": "user", "content": p}],
                          max_tokens=max_tokens, temperature=temperature, reasoning=reasoning)
        text = message_text(out)
        try:
            return sanitize(parse_json_from_text(text, expect=expect))
        except ValueError as e:
            last_err = e
    raise ValueError(f"{kind} response not parseable after retry: {last_err}; raw starts: {text[:300]!r}")


CONCEPT_FIELDS = ("slug", "title", "genre", "setting", "tone", "logline", "characters", "world_rules")

def concept_brief(concept):
    return {"characters": [{"name": c["name"], "role": c["role"]} for c in concept["characters"]], "no_go": []}

def validate_concepts(concepts, expected):
    errs = []
    if not isinstance(concepts, list) or len(concepts) != expected:
        return [f"expected {expected} concepts, got {len(concepts) if isinstance(concepts, list) else type(concepts).__name__}"]
    slugs, titles = set(), set()
    for c in concepts:
        for f in CONCEPT_FIELDS:
            if not c.get(f):
                errs.append(f"concept missing {f}: {c.get('title', c.get('slug', '?'))}")
        slug = c.get("slug", "")
        if slug in slugs:
            errs.append(f"duplicate slug {slug}")
        if c.get("title") in titles:
            errs.append(f"duplicate title {c.get('title')}")
        slugs.add(slug)
        titles.add(c.get("title"))
        chars = c.get("characters", [])
        names = [ch.get("name") for ch in chars]
        if not (3 <= len(chars) <= 6):
            errs.append(f"{slug}: {len(chars)} characters (need 3-6)")
        if len(names) != len(set(names)):
            errs.append(f"{slug}: duplicate character names")
        for ch in chars:
            for f in ("name", "role", "physical", "secret"):
                if not ch.get(f):
                    errs.append(f"{slug}: character missing {f}")
        rules = c.get("world_rules", [])
        if not (2 <= len(rules) <= 4):
            errs.append(f"{slug}: {len(rules)} world rules (need 2-4)")
    genres = [c.get("genre", "").lower() for c in concepts]
    if len(set(genres)) != len(genres):
        errs.append("genres not distinct")
    return errs

def generate_concepts(n=10):
    if config.DRY_RUN:
        return [_dry_concept(i + 1) for i in range(n)]
    concepts = []
    while len(concepts) < n:
        batch = min(5, n - len(concepts))
        used = sorted({c["genre"] for c in concepts})
        prompt = (
            f"You invent vertical microdrama series (64-second episodes, photoreal, fast-cut). "
            f"Create exactly {batch} DISTINCT series with different genres (no two the same genre). "
            + (f"Genres already used, do not reuse: {used}. " if used else "")
            + "For each: slug (lowercase-hyphen), title, genre, setting (one line), tone (exactly 3 words), "
            "logline (one sentence), characters (4 or 5; each: name, role, physical (one stable visual detail), "
            "secret (one fact that must stay consistent until deliberately revealed)), "
            "world_rules (exactly 3 short rules episodes must never break). "
            "Return a JSON list only, no prose."
        )
        parsed = None
        last_err = None
        for attempt in range(2):
            if attempt == 1:
                prompt += " IMPORTANT: reply with valid compact JSON and nothing else."
            out = nvidia_chat(config.NVIDIA_MODELS["writer"], [{"role": "user", "content": prompt}], max_tokens=8000, temperature=0.8, reasoning="low")
            text = message_text(out)
            try:
                parsed = parse_json_from_text(text)
                break
            except ValueError as e:
                last_err = e
        if parsed is None:
            raise ValueError(f"concepts not parseable after retry: {last_err}; raw starts: {text[:300]!r}")
        if isinstance(parsed, dict) and "series" in parsed:
            parsed = parsed["series"]
        if not isinstance(parsed, list):
            raise ValueError(f"concepts response is {type(parsed).__name__}, not a list")
        concepts.extend(parsed)
    return concepts

def generate_arc(concept, eps=10):
    if config.DRY_RUN:
        return {"episodes": [{"ep": i + 1, "title": f"{concept['slug']} E{i+1}", "hook": f"hook{i+1}", "beat": f"beat{i+1}",
                              "reversal": f"reversal{i+1}", "cliffhanger": f"cliff{i+1}"} for i in range(eps)]}
    prompt = (
        f"Plan a {eps}-episode arc for this microdrama series. Concept: {json.dumps(concept)}. "
        "Each episode: ep, title, hook (the first 0-3 seconds), beat, reversal (exactly one per episode), "
        "cliffhanger (a specific question the next episode answers). "
        "Continuity rule: for every episode after the first, the hook MUST directly continue the previous "
        "episode's cliffhanger - reuse its key people, objects and question in the first moments; never open "
        "an unrelated scene. "
        "Never break a world_rule. A character secret may only surface if it is deliberately revealed; "
        "when that happens the episode must name it in a 'reveals' list. No other character may know or "
        "reference a secret before the episode that reveals it. "
        'Return JSON: {"episodes": [...]}. JSON only.'
    )
    arc = call_json("writer", prompt, 12000, 0.7, "low", expect=_expect_arc)
    if isinstance(arc, list):
        arc = {"episodes": arc}
    aliases = {"ep": ("episode", "episode_number", "number"),
               "hook": ("opening", "opening_hook", "cold_open"),
               "beat": ("main_beat", "story"),
               "reversal": ("twist", "turn"),
               "cliffhanger": ("cliff", "cliffhanger_question", "ending")}
    for e in arc.get("episodes", []):
        if isinstance(e, dict):
            for canon, alts in aliases.items():
                if not e.get(canon):
                    for a in alts:
                        if e.get(a) is not None:
                            e[canon] = e[a]
                            break
    return arc

_STOP = set("""a an the and or but of to in on at as is are was were be been with without from by for
how what who whom whose which when where why can could will would shall should may might do does did not no
yes it its this that these those there here into onto out up down over under again once""".split())

def _content_words(t):
    return {w for w in re.findall(r"[a-z0-9]+", str(t).lower()) if len(w) >= 4 and w not in _STOP}

def hook_recap_check(arc):
    misses = []
    eps = arc.get("episodes", [])
    for prev, cur in zip(eps, eps[1:]):
        cw = _content_words(prev.get("cliffhanger", ""))
        hw = _content_words(cur.get("hook", ""))
        if cw and not (cw & hw):
            misses.append({"ep": cur.get("ep"), "cliffhanger": prev.get("cliffhanger"),
                           "hook": cur.get("hook")})
    return misses

def validate_series_arc(arc, concept, eps=10):
    errs = []
    episodes = arc.get("episodes", [])
    if not all(isinstance(e, dict) for e in episodes):
        errs.append("arc episodes must be objects")
        return errs
    if [e.get("ep") for e in episodes] != list(range(1, eps + 1)):
        errs.append(f"episode numbers not 1..{eps}")
    for e in episodes:
        for f in ("ep", "title", "hook", "beat", "reversal", "cliffhanger"):
            if not e.get(f):
                errs.append(f"E{e.get('ep')} missing {f}")
    return errs

def _speaker_candidates(sp, names):
    low = str(sp).strip().lower()
    toks = set(low.split())
    out = set()
    for n in names:
        nl = n.lower()
        if nl == low or nl.endswith(low) or nl.startswith(low) or (toks and toks <= set(nl.split())):
            out.add(n)
    return out

def normalize_speakers(script, brief):
    names = [c["name"] for c in brief["characters"]]
    exact = set(names)
    remapped = 0
    for shot in script.get("shots", []):
        for d in shot.get("dialogue", []):
            sp = d.get("character")
            if not sp or sp in exact:
                continue
            cands = _speaker_candidates(sp, names)
            if len(cands) == 1:
                d["character"] = cands.pop()
                remapped += 1
        binding = shot.get("speaker_binding")
        if binding and binding not in exact:
            cands = _speaker_candidates(binding, names)
            if len(cands) == 1:
                shot["speaker_binding"] = cands.pop()
                remapped += 1
    return remapped

def episode_script(concept, arc_ep, prior_facts, prev_cliffhanger):
    if config.DRY_RUN:
        names = [c["name"] for c in concept["characters"]]
        shots = [{"n": i + 1, "seconds": s, "visual": f"dry shot {i+1}", "camera": "static",
                  "dialogue": [{"character": names[0], "line": f"dry line {i+1}"}] if i % 3 == 0 else [],
                  "lipsync": i % 3 == 0, "narrative_job": "dry", "speaker_binding": names[0] if i % 3 == 0 else ""}
                 for i, s in enumerate(config.SHOT_SECONDS)]
        return {"ep": arc_ep["ep"], "title": arc_ep["title"], "shots": shots, "new_facts": [f"dry fact ep{arc_ep['ep']}"]}
    prompt = (
        f"Write episode {arc_ep['ep']} of this microdrama as a shot script. Series: {json.dumps(concept)}. "
        f"Arc episode: {json.dumps(arc_ep)}. "
        f"Established facts so far (never contradict): {json.dumps(prior_facts[-40:])}. "
        + (f"The previous episode ended on this cliffhanger; the first shot must recap it visually: {prev_cliffhanger}. " if prev_cliffhanger else "")
        + f"Exactly {len(config.SHOT_SECONDS)} shots with these seconds in order: [{SHOT_LIST}]. "
        "Each shot: n, seconds, visual, camera, dialogue (0-2 entries of {character, line}; each line MUST be at most 13 words - count the words), "
        "lipsync (true iff dialogue present), narrative_job, speaker_binding (the speaking character, empty if none). "
        "Dialogue only for characters in the cast, in their established voice. "
        "Secrets discipline: a character's secret stays hidden until the arc episode that reveals it; "
        "never let another character know or reference it earlier. "
        "Also new_facts: facts this episode establishes (reveals, who learns what, promises, objects). "
        'Return JSON: {"ep": n, "title": str, "shots": [...], "new_facts": [str]}. JSON only.'
    )
    script = call_json("writer", prompt, 6000, 0.7, "off", expect=_expect_shots)
    return script

def compact_episode(script):
    lines = []
    for s in script.get("shots", []):
        for d in s.get("dialogue", []):
            lines.append(f"{d.get('character')}: {d.get('line')}")
    return {"ep": script.get("ep"), "title": script.get("title"), "dialogue": lines,
            "new_facts": script.get("new_facts", [])}

def evaluate_series(concept, arc, scripts):
    if config.DRY_RUN:
        return {"scores": {"character": 100, "timeline": 100, "secrets": 100, "voice": 100, "tone": 100},
                "failures": [], "pass": True, "dry": True}
    blob = {"concept": concept, "arc": arc.get("episodes", []), "episodes": [compact_episode(s) for s in scripts]}
    prompt = (
        "You are the consistency judge for a 10-episode microdrama series. Score each dimension 0-100: "
        "character (names, roles, physical details stay stable), "
        "timeline (episode order holds, each episode recaps the previous cliffhanger, no time contradictions), "
        "secrets (no secret contradicted; reveals are set up before they land; world_rules never broken), "
        "voice (each character speaks in a stable register across episodes), "
        "tone (episodes match the declared tone). "
        "For every concrete failure give: ep, dimension, quote (exact line or beat), why. "
        "pass is true only if every score is 70 or above. "
        f"Series: {json.dumps(blob)}. "
        'Return JSON: {"scores": {"character": n, "timeline": n, "secrets": n, "voice": n, "tone": n}, '
        '"failures": [{"ep": n, "dimension": str, "quote": str, "why": str}], "pass": bool}. JSON only.'
    )
    return call_json("judge", prompt, 16000, 0.1, None, expect=_expect_scores)

def _dry_concept(i):
    return {"slug": f"dry-series-{i}", "title": f"Dry Series {i}", "genre": f"genre{i}", "setting": "nowhere",
            "tone": "calm dry test", "logline": "a dry run", "world_rules": ["r1", "r2", "r3"],
            "characters": [{"name": f"C{i}{j}", "role": f"role{j}", "physical": "plain", "secret": f"secret{j}"} for j in range(4)]}

def _expect_concepts(v):
    return isinstance(v, list) and all(isinstance(c, dict) and c.get("slug") for c in v)

def repair_episode_script(concept, arc_ep, broken_script, errs):
    if config.DRY_RUN:
        return broken_script
    cast = ", ".join(c["name"] for c in concept["characters"])
    prompt = (
        "A microdrama shot script failed mechanical validation. Fix ONLY the listed problems, keep everything else identical. "
        f"Cast (exact names required): {cast}. Every dialogue line MUST be at most 13 words - count the words in each line. Validation errors: {json.dumps(errs)}. "
        f"Broken script: {json.dumps(broken_script)}. "
        'Return the corrected script JSON: {"ep": n, "title": str, "shots": [...], "new_facts": [str]}. JSON only.'
    )
    return call_json("writer", prompt, 6000, 0.3, "off")

