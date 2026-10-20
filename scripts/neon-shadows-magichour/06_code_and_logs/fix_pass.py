import argparse, json, pathlib, sys, time

from magicdrama import config
from magicdrama.stages.series import (concept_brief, episode_script, evaluate_series,
                                      hook_recap_check, repair_episode_script, call_json)
from magicdrama.validators import validate_script


def load(p):
    return json.loads(p.read_text())


def write_json(p, obj):
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def fix_hook(concept, prev_cliff, old_hook):
    if config.DRY_RUN:
        return old_hook + " (dry-fixed)"
    prompt = (
        f"Rewrite ONLY the opening hook of a microdrama episode. Series tone: {concept.get('tone')}. "
        f"The previous episode ended on this cliffhanger: {prev_cliff}. "
        f"The current hook is weak because it does not continue it: {old_hook}. "
        "Write a new hook (1-2 sentences, visual, first 0-3 seconds of the episode) that directly "
        "continues the cliffhanger: reuse its key people, objects and question. "
        'Return JSON: {"hook": str}. JSON only.')
    out = call_json("writer", prompt, 800, 0.5, "off")
    return out.get("hook") or old_hook


def collect_flags(sdir, concept, arc, brief, verdict):
    flagged = {}
    for m in hook_recap_check(arc):
        flagged.setdefault(m["ep"], set()).add("hook_recap")
    for ep_path in sorted(sdir.glob("ep??.json")):
        if "_v" in ep_path.stem:
            continue
        ep_no = int(ep_path.stem[2:4])
        errs = validate_script(load(ep_path), brief)
        if errs:
            flagged.setdefault(ep_no, set()).add("validator:" + ";".join(errs[:3]))
        raw = ep_path.read_text()
        if "\\u00" in raw:
            flagged.setdefault(ep_no, set()).add("literal_escapes")
    dim_scores = verdict.get("scores") or {}
    for f in (verdict.get("failures") or []):
        ep = f.get("ep") or f.get("episode")
        dim = f.get("dimension") or f.get("type")
        weak_dim = isinstance(dim_scores.get(dim), (int, float)) and dim_scores[dim] < 70
        if isinstance(ep, int) and 1 <= ep <= 10 and (f.get("quote_verified", True) or weak_dim):
            flagged.setdefault(ep, set()).add(f"judge:{dim}")
    return flagged


def regenerate_episode(concept, arc, sdir, ep_no, facts_by_ep):
    arc_ep = arc["episodes"][ep_no - 1]
    prior_facts = [f for k in range(1, ep_no) for f in facts_by_ep.get(k, [])][-40:]
    prev_cliff = arc["episodes"][ep_no - 2]["cliffhanger"] if ep_no > 1 else None
    old_path = sdir / f"ep{ep_no:02d}.json"
    old = load(old_path)
    script = episode_script(concept, arc_ep, prior_facts, prev_cliff)
    if script.get("ep") != ep_no:
        script["ep"] = ep_no
    errs = validate_script(script, concept_brief(concept))
    if errs:
        script = repair_episode_script(concept, arc_ep, script, errs)
        if script.get("ep") != ep_no:
            script["ep"] = ep_no
        errs = validate_script(script, concept_brief(concept))
    if errs:
        print(f"  E{ep_no}: regen still invalid {errs}; keeping original", flush=True)
        return False
    keep_facts = [f for f in old.get("new_facts", []) if f not in script.get("new_facts", [])]
    if keep_facts:
        script["new_facts"] = list(script.get("new_facts", [])) + keep_facts
    v1 = sdir / f"ep{ep_no:02d}_v1.json"
    if not v1.exists():
        old_path.rename(v1)
    write_json(old_path, script)
    print(f"  E{ep_no}: regenerated (original kept as {v1.name})", flush=True)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--max-fix-per-series", type=int, default=6)
    args = ap.parse_args()
    out = pathlib.Path(config.WORKDIR) / "series_lab"
    concepts = load(out / "concepts.json")
    from series_run import normalize_eval, verify_failure_quotes, build_report, render_report_md
    for c in concepts:
        slug = c["slug"]
        sdir = out / slug
        ev_path = sdir / "eval.json"
        if not (sdir / "arc.json").exists() or not ev_path.exists():
            print(f"{slug}: incomplete, skipping", flush=True)
            continue
        arc = load(sdir / "arc.json")
        verdict = normalize_eval(load(ev_path))
        verdict["failures"] = verify_failure_quotes(sdir, verdict["failures"])
        brief = concept_brief(c)
        flagged = collect_flags(sdir, c, arc, brief, verdict)
        if not flagged:
            print(f"{slug}: clean, no fixes", flush=True)
            continue
        print(f"{slug}: flagged episodes {sorted(flagged)}", flush=True)
        changed = False
        for ep_no in sorted(flagged)[: args.max_fix_per_series]:
            reasons = flagged[ep_no]
            print(f"  E{ep_no}: {sorted(reasons)}", flush=True)
            if any(str(r).startswith("hook_recap") for r in reasons) and ep_no > 1:
                prev_cliff = arc["episodes"][ep_no - 2]["cliffhanger"]
                old_hook = arc["episodes"][ep_no - 1]["hook"]
                new_hook = fix_hook(c, prev_cliff, old_hook)
                if new_hook != old_hook:
                    av1 = sdir / "arc_v1.json"
                    if not av1.exists():
                        (sdir / "arc.json").rename(av1)
                        arc = load(av1)
                    arc["episodes"][ep_no - 1]["hook"] = new_hook
                    write_json(sdir / "arc.json", arc)
                    print(f"  E{ep_no}: hook rewritten", flush=True)
                    changed = True
                time.sleep(args.sleep)
            facts_by_ep = {}
            for k in range(1, 11):
                p = sdir / f"ep{k:02d}.json"
                if p.exists():
                    facts_by_ep[k] = load(p).get("new_facts", [])
            if regenerate_episode(c, arc, sdir, ep_no, facts_by_ep):
                changed = True
            time.sleep(args.sleep)
        if changed:
            scripts = [load(sdir / f"ep{k:02d}.json") for k in range(1, 11)]
            ev1 = sdir / "eval_v1.json"
            if not ev1.exists():
                ev_path.rename(ev1)
            verdict2 = evaluate_series(c, load(sdir / "arc.json"), scripts)
            write_json(ev_path, verdict2)
            misses = hook_recap_check(load(sdir / "arc.json"))
            write_json(sdir / "arc_hookcheck.json", {"misses": misses, "checked_pairs": 9})
            print(f"{slug}: re-judged", flush=True)
        time.sleep(args.sleep)
    rep = build_report(concepts, out)
    (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n")
    (out / "report.md").write_text(render_report_md(rep))
    print("report rebuilt with before/after", flush=True)


if __name__ == "__main__":
    main()

