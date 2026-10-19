import json
from .. import config
from .series import call_json, normalize_speakers, compact_episode, _expect_arc, _expect_scores

SHOT_LIST = ", ".join(str(s) for s in config.SHOT_SECONDS)

REALISM_RULES = """REALISM RULES (this is what makes it feel like the reference reel, not AI concept-art):
- Real world only: no fantasy, no stylized neon, no concept-art. Ordinary places, motivated natural or office light.
- Mundane anchors in every episode: at least 3 everyday objects/actions (chai, ID card, elevator, Excel, stapler, phone battery, lunch dabba).
- Inciting incident happens IN MOTION: the character is already doing something ordinary when it hits. Never open with a lecture or explanation.
- Dialogue is subtext-y and mundane: people talk about the small thing while meaning the big thing. Lines are short, interruptible, imperfect. Max 13 words each.
- Micro-acting: after every line, the performer keeps living - eyeline shifts, prop handling, listening, sipping, typing. Nobody freezes.
- Every scene manufactures an expectation gap (McKee): a character acts expecting X, gets Y.
- Every main character has an inner contradiction; nobody is purely good or evil.
- Concrete money: whenever payment, invoices, fines or amounts appear, state a specific small rupee figure (e.g. Rs 850, Rs 2,300) in dialogue or on screen, and keep every figure consistent with story memory forever.
- Process realism: workplaces run on process. A dispute involves HR, written warnings, documentation, notice periods. Nobody is escorted out, fired, or reinstated same-day without paperwork and a witness. Security follows procedure, not drama.
- Believable pivots: a big emotional or power shift (threat to offer, enemy to ally) takes at least a full scene with a visible trigger, or an episode boundary. Never flip a relationship in two beats.
- Establish before use: a character can only repeat a story, excuse, or plan (e.g. a cover story) if a previous scene or episode shows someone telling it to them. If a lie will be used later, plant its telling first."""

COVERAGE_RULES = """COVERAGE RULES (shot grammar, fixes the "one wide shot AI feel"):
- Every shot gets shot_size: "close-up", "medium", or "wide".
- A 2+ person conversation must use shot/reverse-shot: consecutive shots alternate whose close-up we see; both speakers get at least one close-up in the episode.
- Never cover a whole conversation in a single wide shot.
- Do not repeat the same shot_size+camera on consecutive shots.
- One primary camera move per shot; stillness is fine when it serves the moment."""

def generate_arc_v2(concept, eps=10):
    if config.DRY_RUN:
        return {"episodes": [{"ep": i + 1, "title": f"{concept['slug']} E{i+1}", "hook": f"hook{i+1}", "beat": f"beat{i+1}",
                              "reversal": f"reversal{i+1}", "cliffhanger": f"cliff{i+1}", "value_turn": f"v{i+1}",
                              "mundane_anchors": ["chai", "stapler"], "plant": f"plant{i+1}"} for i in range(eps)]}
    prompt = (
        f"Plan a {eps}-episode arc for this grounded, realistic office microdrama. Series bible: {json.dumps(concept)}. "
        + REALISM_RULES + "\n"
        "Each episode: ep, title, hook (first 0-3 seconds, a visual moment not dialogue), beat, "
        "reversal (exactly one, paying off an earlier planted detail), plant (the detail this episode plants for later), "
        "value_turn (what changes: e.g. safe->exposed, winning->owing), "
        "mundane_anchors (2-4 everyday objects/actions in this episode), "
        "cliffhanger (a specific question the next episode answers). "
        "Continuity rule: every hook after E1 MUST directly continue the previous cliffhanger - same people, objects, question. "
        "A character secret may only surface in the episode that reveals it; add it to that episode's reveals list. "
        "Pacing: one attempt->result micro-task loop roughly every 20 seconds; every episode advances the season question "
        "(will the secret deal survive, and what will honesty cost her?). "
        'Keep every field to one short sentence. Compact JSON, no prose, no markdown fences. Return JSON: {"episodes": [...]}. JSON only.'
    )
    import pathlib as _pl, os as _os
    outdir = _pl.Path(_os.environ.get("V2_WORKDIR", "/tmp/v3/honesty_run"))
    ranges = [(1, 4), (5, 7), (8, eps)]
    alleps = []
    for idx, (a, b) in enumerate(ranges, 1):
        part = outdir / f"arc_part{idx}.json"
        if part.exists():
            alleps += json.loads(part.read_text())
            continue
        chunk = _arc_chunk(concept, prompt, a, b, alleps or None)
        part.write_text(json.dumps(chunk))
        alleps += chunk
        print(f"[arc] part {idx} (E{a}-E{b}) saved ({len(chunk)} eps)", flush=True)
    return {"episodes": alleps}

def _arc_chunk(concept, base_prompt, a, b, prior):
    p = base_prompt.replace("Plan a ", f"Plan episodes {a}-{b} of a ").replace(
        'Return JSON: {"episodes": [...]}. JSON only.',
        f'Return JSON: {{"episodes": [...]}} with exactly episodes {a} through {b}. JSON only.')
    if prior:
        p += f" Episodes 1-{a-1} are already planned: {json.dumps(prior)}. Episode {a}'s hook MUST continue episode {a-1}'s cliffhanger."
    out = call_json("writer", p, 9000, 0.7, "low", expect=_expect_arc)
    if isinstance(out, dict):
        out = out.get("episodes", [])
    return out

def _draft_prompt(concept, arc_ep, memory, prev_cliffhanger):
    return (
        f"Write episode {arc_ep['ep']} of this grounded office microdrama as a shot script. "
        f"Series bible: {json.dumps(concept)}. Arc episode: {json.dumps(arc_ep)}. "
        f"Story memory (never contradict): {json.dumps(memory)}. "
        + (f"Downstream facts from later episodes that MUST remain true (do not contradict or re-establish differently): {json.dumps(memory.get('downstream_facts'))}. " if memory.get("downstream_facts") else "")
        + (f"Prior final episodes (full continuity record - never contradict dialogue, facts, addresses or amounts in them): {json.dumps(memory.get('prior_episodes'))}. " if memory.get("prior_episodes") else "")
        + (f"A previous attempt at this episode had these continuity clashes - write a DIFFERENT episode that avoids every one: {json.dumps(arc_ep.get('_avoid'))}. " if arc_ep.get("_avoid") else "")
        + (f"Previous episode ended on this cliffhanger; shot 1 must continue it visually: {prev_cliffhanger}. " if prev_cliffhanger else "")
        + REALISM_RULES + "\n" + COVERAGE_RULES + "\n"
        f"Exactly {len(config.SHOT_SECONDS)} shots with these seconds in order: [{SHOT_LIST}]. "
        "Each shot: n, seconds, shot_size, visual, camera, "
        "dialogue (0-2 entries of {character, line, voice}; voice = that character's locked voice descriptor copied verbatim; each line <= 13 words), "
        "micro_acting (what the performer physically does during/after the line), "
        "lipsync (true iff dialogue present), narrative_job, speaker_binding (speaking character, empty if none). "
        "Dialogue only for cast members, in their established voice and register. "
        "Knowledge discipline: a character can only act on or reference facts listed under their own 'knows' in story memory. Timeline ledger: memory facts carry the episode number where they were established; keep every amount, date, name and arrangement exactly consistent with them, and set events after the episodes whose facts you use. "
        "Also new_facts: list of {fact, learned_by: [names]} this episode establishes (reveals, promises, objects, who learns what). "
        'IMPORTANT: output ONE LINE of compact JSON (no indentation, no newlines inside the JSON, no markdown fences) - pretty-printing wastes half the token budget and gets truncated. '
        'Return JSON: {"ep": n, "title": str, "shots": [...], "new_facts": [...]}. JSON only.'
    )

def enhance_episode(concept, script, arc_ep):
    """ViMax-style enhancer: polish dialogue naturalness + continuity, plot unchanged."""
    if config.DRY_RUN:
        return script
    prompt = (
        "You are a dialogue and continuity polish pass for a realistic office microdrama episode. "
        "Improve dialogue naturalness without changing the plot, shot order, or shot count. "
        "Rules: keep each line <= 13 words; make lines more mundane and subtext-y where possible "
        "(people say the small thing, mean the big thing); keep character names, facts, and voice descriptors identical; "
        "ensure every speaking character's 'voice' field matches their bible voice verbatim; no camera jargon; no metaphors. "
        f"Character voices: {json.dumps({c['name']: c.get('voice','') for c in concept['characters']})}. "
        f"Episode JSON: {json.dumps(script)}. "
        'Return the same JSON shape, polished. JSON only.'
    )
    out = call_json("writer", prompt, 6000, 0.4, "off", expect=_expect_shots_v2)
    out["new_facts"] = script.get("new_facts", [])
    return out

def _expect_shots_v2(v):
    return isinstance(v, dict) and isinstance(v.get("shots"), list)

CLOSE = ("close", "close-up", "closeup", "cu", "mcu", "medium close")
WIDE = ("wide", "long", "full", "establishing")

def _size(shot):
    return str(shot.get("shot_size", "")).strip().lower()

def coverage_audit(script):
    """wind-comic dialogue coverage audit, mechanical. Returns list of issues."""
    issues = []
    shots = script.get("shots", [])
    speakers_seen_close = set()
    all_speakers = set()
    prev_key = None
    for i, s in enumerate(shots):
        dlg = s.get("dialogue", [])
        spk = {d.get("character") for d in dlg if d.get("character")}
        all_speakers |= spk
        sz = _size(s)
        if sz in CLOSE:
            speakers_seen_close |= spk
        if not sz:
            issues.append(f"shot {s.get('n')}: missing shot_size")
        key = (sz, str(s.get("camera", "")).strip().lower())
        if prev_key and key == prev_key and sz:
            issues.append(f"shots {i} and {i+1}: identical shot_size+camera")
        prev_key = key
        if len(dlg) >= 2:
            chars = {d.get("character") for d in dlg}
            if len(chars) >= 2 and sz in WIDE:
                issues.append(f"shot {s.get('n')}: multi-speaker conversation in a wide shot")
                                                                               
    chain = []
    for s in shots + [{"dialogue": [], "n": None}]:
        spk = {d.get("character") for d in s.get("dialogue", []) if d.get("character")}
        if spk and chain and spk & chain[-1][0]:
            chain.append((spk, s))
        else:
            if len(chain) >= 2 and all(_size(sh) in WIDE for _, sh in chain):
                issues.append(f"conversation shots {chain[0][1].get('n')}-{chain[-1][1].get('n')}: all wide, no close-up reaction")
            chain = [(spk, s)] if spk else []
    missing_close = all_speakers - speakers_seen_close
    for name in sorted(missing_close):
        issues.append(f"speaker {name}: no close-up in the episode")
    return issues

def episode_script_v2(concept, arc_ep, memory, prev_cliffhanger, drafts=2):
    if config.DRY_RUN:
        names = [c["name"] for c in concept["characters"]]
        shots = [{"n": i + 1, "seconds": s, "shot_size": ["wide", "medium", "close-up"][i % 3], "visual": f"dry shot {i+1}",
                  "camera": "static", "dialogue": [{"character": names[0], "line": f"dry line {i+1}", "voice": "v"}] if i % 3 == 0 else [],
                  "micro_acting": "dry", "lipsync": i % 3 == 0, "narrative_job": "dry",
                  "speaker_binding": names[0] if i % 3 == 0 else ""}
                 for i, s in enumerate(config.SHOT_SECONDS)]
        return {"ep": arc_ep["ep"], "title": arc_ep["title"], "shots": shots,
                "new_facts": [{"fact": f"dry fact ep{arc_ep['ep']}", "learned_by": names[:1]}], "audit": []}
    import concurrent.futures, time as _t
    t0 = _t.time()
    prompt = _draft_prompt(concept, arc_ep, memory, prev_cliffhanger)
    temps = [0.6, 0.9][:max(1, drafts)]
    cands = []
    if len(temps) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(temps)) as ex:
            futs = [ex.submit(lambda tt: call_json("writer", prompt, 7500, tt, "off", expect=_expect_shots_v2), t) for t in temps]
            for f in futs:
                try:
                    cands.append(f.result())
                except ValueError:
                    continue
    else:
        for t in temps:
            try:
                cands.append(call_json("writer", prompt, 6000, t, "off", expect=_expect_shots_v2))
            except ValueError:
                continue
    t_drafts = _t.time() - t0
    if not cands:
        raise ValueError("all drafts failed to parse")
    t1 = _t.time()
    if len(cands) == 1:
        best = cands[0]
    else:
        best = _pick_draft(concept, arc_ep, cands)
    t_pick = _t.time() - t1
    t1 = _t.time()
    best = enhance_episode(concept, best, arc_ep)
    t_enh = _t.time() - t1
    t1 = _t.time()
    issues = coverage_audit(best)
    repaired = False
    if issues:
        best = _repair_coverage(concept, arc_ep, best, issues)
        issues = coverage_audit(best)
        repaired = True
    t_audit = _t.time() - t1
    best["audit"] = issues
    print(f"[timing] ep{arc_ep.get('ep')} drafts={t_drafts:.0f}s pick={t_pick:.0f}s enhance={t_enh:.0f}s "
          f"audit={'repair+' if repaired else ''}{t_audit:.0f}s total={_t.time()-t0:.0f}s", flush=True)
    return best

def _pick_draft(concept, arc_ep, cands):
    prompt = (
        "Two candidate scripts for the same episode of a realistic office microdrama. "
        "Pick the one with more natural mundane dialogue, better shot/reverse coverage, and stronger realism "
        "(ordinary objects, subtext, imperfect short lines). Reply JSON only: "
        '{"pick": 1} or {"pick": 2}, plus "why": one sentence. '
        f"Arc episode: {json.dumps(arc_ep)}. A: {json.dumps(cands[0])}. B: {json.dumps(cands[1])}."
    )
    try:
        out = call_json("judge", prompt, 2000, 0.1, None, expect=lambda v: isinstance(v, dict) and v.get("pick") in (1, 2))
        return cands[out["pick"] - 1]
    except Exception:
        return cands[0]

def _repair_coverage(concept, arc_ep, script, issues):
    prompt = (
        "Fix ONLY these coverage problems in this episode shot script, changing nothing else: "
        f"{json.dumps(issues)}. Allowed changes: adjust shot_size/camera values, split one dialogue shot into the "
        "existing shot count by moving a line to a neighboring shot, or convert a wide conversation shot to medium/close-up. "
        f"Keep exactly {len(config.SHOT_SECONDS)} shots. Episode JSON: {json.dumps({k: v for k, v in script.items() if k != 'audit'})}. "
        'Return the same JSON shape. JSON only.'
    )
    try:
        out = call_json("writer", prompt, 6000, 0.3, "off", expect=_expect_shots_v2)
        out["new_facts"] = script.get("new_facts", [])
        return out
    except ValueError:
        return script

def update_memory(memory, script):
    for f in script.get("new_facts", []):
        if isinstance(f, dict) and f.get("fact"):
            entry = {"fact": f["fact"], "learned_by": f.get("learned_by", []), "ep": script.get("ep")}
            memory.setdefault("facts", []).append(entry)
            for name in f.get("learned_by", []):
                memory.setdefault("knows", {}).setdefault(name, []).append(f["fact"])
    return memory

def memory_slice(memory):
    return {"facts": memory.get("facts", [])[-40:], "knows": memory.get("knows", {}), "downstream_facts": memory.get("downstream_facts", []), "prior_episodes": memory.get("prior_episodes", [])}


def continuity_gate(concept, prior_scripts, new_script, memory, max_tokens=3000):
    """Cheap per-episode continuity check against ALL prior final episodes.
    Returns {"ok": bool, "clashes": [...]}. Routes NVIDIA-first via call_json."""
    if config.DRY_RUN:
        return {"ok": True, "clashes": [], "dry": True}
    blob = {
        "bible": {"characters": [{"name": c["name"], "role": c["role"], "voice": c.get("voice", "")} for c in concept["characters"]]},
        "prior_episodes": [compact_episode(s) for s in prior_scripts],
        "new_episode": compact_episode(new_script),
        "story_memory": memory,
    }
    prompt = (
        "You are a strict continuity checker for a 10-episode grounded office microdrama. "
        "A new episode was just written. Compare it against ALL prior final episodes and the story memory. "
        "Flag ONLY concrete contradictions: "
        "reveals/secrets (a character uses knowledge they never learned on screen, or a reveal contradicts an established fact), "
        "timeline (impossible event order; failure to continue the previous episode's cliffhanger), "
        "who-knows-what violations, "
        "forms of address (a character addresses someone not present in the scene, or uses a name/rank contradicting prior scenes), "
        "in-world money (any amount contradicting an earlier stated figure), "
        "character details (names, roles, physical details). "
        "Do not flag style, tone, or quality. For each clash give: kind, quote_or_beat (from the NEW episode), "
        "contradicts (prior ep number and what it established), why. "
        f"Material: {json.dumps(blob)}. "
        'Return JSON: {"ok": bool, "clashes": [{"kind": str, "quote_or_beat": str, "contradicts": str, "why": str}]}. JSON only.'
    )
    return call_json("judge", prompt, max_tokens, 0.0, "off",
                     expect=lambda v: isinstance(v, dict) and "ok" in v)

def evaluate_series_v2(concept, arc, scripts):
    if config.DRY_RUN:
        return {"scores": {"character": 100, "timeline": 100, "secrets": 100, "voice": 100, "tone": 100, "realism": 100},
                "failures": [], "pass": True, "dry": True}
    blob = {"concept": concept, "arc": arc.get("episodes", []), "episodes": [compact_episode(s) for s in scripts]}
    prompt = (
        "You are the consistency AND realism judge for a 10-episode grounded office microdrama. Score each 0-100: "
        "character (names, roles, physical details stable), "
        "timeline (order holds, each episode continues the previous cliffhanger), "
        "secrets (no knowledge violations; reveals planted before they land), "
        "voice (each character speaks in a stable register), "
        "tone (episodes match declared tone), "
        "realism (COLD-VIEWER test: dialogue sounds like real mundane speech not exposition; scenes contain ordinary "
        "objects and actions; stakes stay human-sized; nothing reads as concept-art or genre fantasy; a cold viewer "
        "could retell goal, obstacle, choice, outcome for every episode). "
        "For every concrete failure give: ep, dimension, quote (exact line or beat), why. "
        "pass is true only if every score is 80 or above. "
        f"Series: {json.dumps(blob)}. "
        'Return JSON: {"scores": {"character": n, "timeline": n, "secrets": n, "voice": n, "tone": n, "realism": n}, '
        '"failures": [{"ep": n, "dimension": str, "quote": str, "why": str}], "pass": bool}. JSON only.'
    )
    return call_json("judge", prompt, 16000, 0.1, None, expect=_expect_scores)

