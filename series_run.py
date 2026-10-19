import argparse
import json, unicodedata, re
import pathlib
import sys
import time

from magicdrama import config
from magicdrama.stages.series import (concept_brief, evaluate_series, generate_arc, generate_concepts,
                                      episode_script, validate_concepts, validate_series_arc, hook_recap_check)
from magicdrama.validators import validate_script

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))

def run_series(concept, args, out, mark, pause):
    slug = concept["slug"]
    sdir = out / slug
    apath = sdir / "arc.json"
    if apath.exists():
        arc = json.loads(apath.read_text())
    else:
        arc = generate_arc(concept, args.eps)
        errs = validate_series_arc(arc, concept, args.eps)
        if errs:
            raise RuntimeError(f"{slug} arc invalid: {errs}")
        write_json(apath, arc)
        misses = hook_recap_check(arc)
        write_json(sdir / "arc_hookcheck.json", {"misses": misses,
                                                 "checked_pairs": args.eps - 1})
        if misses:
            print(f"{slug}: hook-recap misses at E{[m['ep'] for m in misses]}", flush=True)
        mark(f"{slug}/arc")
        print(f"{slug}: arc planned", flush=True)
    pause()
    brief = concept_brief(concept)
    scripts, facts = [], []
    prev_cliff = None
    for arc_ep in arc["episodes"]:
        ep = arc_ep["ep"]
        epath = sdir / f"ep{ep:02d}.json"
        if epath.exists():
            script = json.loads(epath.read_text())
        else:
            script = episode_script(concept, arc_ep, facts, prev_cliff)
            if script.get("ep") != ep:
                script["ep"] = ep
            from magicdrama.stages.series import normalize_speakers
            normalize_speakers(script, brief)
            errs = validate_script(script, brief)
            if errs:
                from magicdrama.stages.series import repair_episode_script
                all_errs = [errs]
                for round_n in range(2):
                    script = repair_episode_script(concept, arc_ep, script, errs)
                    if script.get("ep") != ep:
                        script["ep"] = ep
                    normalize_speakers(script, brief)
                    errs = validate_script(script, brief)
                    if not errs:
                        break
                    all_errs.append(errs)
                if errs:
                    raise RuntimeError(f"{slug} E{ep} failed validation after 2 repairs: {all_errs}")
                write_json(sdir / f"ep{ep:02d}_repair.json", {"rounds": all_errs, "repaired": True})
                print(f"{slug}: E{ep} repaired after drift: {all_errs[0]}", flush=True)
            write_json(epath, script)
            mark(f"{slug}/ep{ep:02d}")
            print(f"{slug}: E{ep} written+validated", flush=True)
        facts.extend(script.get("new_facts", []))
        prev_cliff = arc_ep["cliffhanger"]
        scripts.append(script)
        pause()
    vpath = sdir / "eval.json"
    if vpath.exists():
        verdict = json.loads(vpath.read_text())
    else:
        verdict = evaluate_series(concept, arc, scripts)
        write_json(vpath, verdict)
        mark(f"{slug}/eval")
        print(f"{slug}: judged {verdict.get('scores')}", flush=True)
    pause()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series-count", type=int, default=10)
    ap.add_argument("--eps", type=int, default=10)
    ap.add_argument("--out", default=None)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--only", default=None)
    ap.add_argument("--status-suffix", default=None)
    args = ap.parse_args()
    out = pathlib.Path(args.out or (config.WORKDIR / "series_lab"))
    out.mkdir(parents=True, exist_ok=True)
    status_path = out / ("status_" + args.status_suffix + ".json" if args.status_suffix else "status.json")
    status = json.loads(status_path.read_text()) if status_path.exists() else {"units": [], "error": None}
    def mark(unit):
        status["units"].append(unit)
        write_json(status_path, status)
    def pause():
        time.sleep(args.sleep)
    try:
        cpath = out / "concepts.json"
        if cpath.exists():
            concepts = json.loads(cpath.read_text())
            print("resume: concepts loaded", flush=True)
        else:
            concepts = generate_concepts(args.series_count)
            errs = validate_concepts(concepts, args.series_count)
            if errs:
                raise RuntimeError(f"concept validation failed: {errs}")
            write_json(cpath, concepts)
            mark("concepts")
            print(f"concepts: {[c['slug'] for c in concepts]}", flush=True)
        pause()
        if args.only:
            keep = set(args.only.split(","))
            concepts = [c for c in concepts if c["slug"] in keep]
        for concept in concepts:
            try:
                run_series(concept, args, out, mark, pause)
            except Exception as e:
                slug = concept['slug']
                print(f'{slug}: SERIES FAILED {type(e).__name__}: {e}', flush=True)
                write_json(out / slug / 'series_error.json',
                           {'error': f'{type(e).__name__}: {e}'})
                pause()
        report = build_report(concepts, out)
        write_json(out / "report.json", report)
        (out / "report.md").write_text(render_report_md(report))
        mark("report")
        print("series lab complete:", f"{sum(1 for s in report['series'] if s['pass'])}/{len(report['series'])} series pass", flush=True)
    except Exception as e:
        status["error"] = f"{type(e).__name__}: {e}"
        write_json(status_path, status)
        print("FAILED:", status["error"], file=sys.stderr, flush=True)
        raise

def series_text_blob(sdir):
    parts = []
    ap = sdir / "arc.json"
    if ap.exists():
        parts.append(ap.read_text())
    for ep in sorted(sdir.glob("ep*.json")):
        if "repair" not in ep.name:
            parts.append(ep.read_text())
    return " ".join(parts).lower()

def _normtext(t):
    t = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)
    try:
        t = t.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if ch.isalnum() or ch.isspace())
    return re.sub(r"\s+", " ", t.lower()).strip()

def verify_failure_quotes(sdir, failures):
    blob = _normtext(series_text_blob(sdir))
    for f in failures:
        q = _normtext(str(f.get("quote", "")))
        f["quote_verified"] = bool(q) and (q[:60] in blob if len(q) > 60 else q in blob)
    return failures

def _pick(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return None

def normalize_eval(ev):
    sc = ev.get("scores") or {}
    norm_scores = {
        "character_consistency": _pick(sc, "character_consistency", "character", "characters"),
        "timeline_consistency": _pick(sc, "timeline_consistency", "timeline", "continuity"),
        "secret_consistency": _pick(sc, "secret_consistency", "secrets", "secret"),
        "voice_consistency": _pick(sc, "voice_consistency", "voice", "voices"),
        "tone_consistency": _pick(sc, "tone_consistency", "tone", "mood"),
    }
    vals = [v for v in norm_scores.values() if isinstance(v, (int, float))]
    verdict = ev.get("verdict")
    if verdict is None and ev.get("pass") is not None:
        verdict = "pass" if ev.get("pass") else "fail"
    failures = []
    for f in ev.get("failures") or []:
        failures.append({
            "dimension": _pick(f, "dimension", "type", "category"),
            "ep": _pick(f, "ep", "episode", "episode_number"),
            "quote": _pick(f, "quote", "excerpt", "line"),
            "why": _pick(f, "why", "issue", "explanation", "problem"),
        })
    passed = ev.get("pass")
    if passed is None:
        passed = (verdict == "pass")
    return {"scores": {"character": norm_scores["character_consistency"],
                       "timeline": norm_scores["timeline_consistency"],
                       "secrets": norm_scores["secret_consistency"],
                       "voice": norm_scores["voice_consistency"],
                       "tone": norm_scores["tone_consistency"]},
            "overall": ev.get("overall_score") or ev.get("overall") or (round(sum(vals) / len(vals), 1) if vals else None),
            "verdict": verdict,
            "pass": bool(passed),
            "failures": failures,
            "summary": ev.get("summary") or ev.get("notes")}

def compute_metrics(sdir, arc):
    from magicdrama.stages.series import _content_words, hook_recap_check
    eps = sorted(p for p in sdir.glob("ep??.json") if "_v" not in p.stem)
    wc, over8, over14 = [], 0, 0
    for p in eps:
        for sh in json.loads(p.read_text()).get("shots", []):
            for d in sh.get("dialogue", []):
                n = len(str(d.get("line", "")).split())
                wc.append(n)
                over8 += n > 8
                over14 += n > 14
    hook_misses = len(hook_recap_check(arc)) if arc else None
    cut_misses = []
    if arc:
        for p in eps:
            ep_no = int(p.stem[2:4])
            if ep_no > len(arc.get("episodes", [])):
                continue
            cw = _content_words(arc["episodes"][ep_no - 1].get("cliffhanger", ""))
            shots = json.loads(p.read_text()).get("shots", [])
            tail = " ".join([str(shots[-1].get("visual", "")) if shots else ""]
                            + [str(d.get("line", "")) for d in (shots[-1].get("dialogue", []) if shots else [])])
            if cw and not (cw & _content_words(tail)):
                cut_misses.append(ep_no)
    return {"lines": len(wc), "avg_words_per_line": round(sum(wc) / max(len(wc), 1), 1),
            "max_line_words": max(wc) if wc else 0,
            "pct_lines_over_8_words": round(100 * over8 / max(len(wc), 1), 1),
            "lines_over_14_words": over14,
            "hook_recap_misses": hook_misses, "cliffhanger_cut_misses": cut_misses}

def build_report(concepts, out):
    rows = []
    for c in concepts:
        sdir = out / c["slug"]
        verdict = normalize_eval(json.loads((sdir / "eval.json").read_text())) if (sdir / "eval.json").exists() else {}
        rows.append({"slug": c["slug"], "title": c["title"], "genre": c["genre"],
                     "scores": verdict.get("scores", {}), "pass": bool(verdict.get("pass")),
                     "overall": verdict.get("overall"), "summary": verdict.get("summary"),
                     "metrics": compute_metrics(sdir, arc if (sdir / "arc.json").exists() and (arc := json.loads((sdir / "arc.json").read_text())) is not None else None),
                     "before": (lambda v1: {"scores": v1.get("scores"), "overall": v1.get("overall"),
                                            "pass": bool(v1.get("pass"))} if v1 else None)(
                         normalize_eval(json.loads((sdir / "eval_v1.json").read_text()))
                         if (sdir / "eval_v1.json").exists() else None),
                     "failures": verify_failure_quotes(sdir, verdict.get("failures", [])[:10])})
    dims = ["character", "timeline", "secrets", "voice", "tone"]
    judged = [r for r in rows if any(v is not None for v in r["scores"].values())]
    avg = {d: round(sum(r["scores"].get(d) or 0 for r in judged) / max(len(judged), 1), 1) for d in dims}
    return {"n_series": len(rows), "n_judged": len(judged), "avg_scores": avg, "series": rows,
            "models": {"writer": config.NVIDIA_MODELS["writer"], "judge": config.NVIDIA_MODELS["judge"]}}

def render_report_md(report):
    lines = ["# 10-Series Consistency Lab", "",
             f"Writer: `{report['models']['writer']}`  Judge: `{report['models']['judge']}`", "",
             "| Series | Genre | Char | Time | Secrets | Voice | Tone | Pass |",
             "|---|---|---|---|---|---|---|---|"]
    for r in report["series"]:
        s = r["scores"]
        lines.append(f"| {r['title']} | {r['genre']} | {s.get('character','-')} | {s.get('timeline','-')} | "
                     f"{s.get('secrets','-')} | {s.get('voice','-')} | {s.get('tone','-')} | {'yes' if r['pass'] else 'NO'} |")
        if r.get("before"):
            b = r["before"]
            lines.append(f"| {r['title']} (before fixes) | {r['genre']} | {b['scores'].get('character','-')} | "
                         f"{b['scores'].get('timeline','-')} | {b['scores'].get('secrets','-')} | "
                         f"{b['scores'].get('voice','-')} | {b['scores'].get('tone','-')} | {'yes' if b['pass'] else 'NO'} |")
    lines += ["", "## Average scores", json.dumps(report["avg_scores"]), "",
              "## Mechanical yardsticks (verified by code, not judge opinion)", "",
              "| Series | Lines | Avg words/line | Max | % >8w | >14w | Hook misses | Cliff-cut misses |",
              "|---|---|---|---|---|---|---|---|"]
    for r in report["series"]:
        m = r.get("metrics") or {}
        lines.append(f"| {r['title']} | {m.get('lines','-')} | {m.get('avg_words_per_line','-')} | "
                     f"{m.get('max_line_words','-')} | {m.get('pct_lines_over_8_words','-')} | "
                     f"{m.get('lines_over_14_words','-')} | {m.get('hook_recap_misses','-')} | "
                     f"{','.join(str(e) for e in m.get('cliffhanger_cut_misses', [])) or '-'} |")
    lines += ["", "## Failure examples"]
    for r in report["series"]:
        for f in r["failures"]:
            tag = "" if f.get("quote_verified", True) else " [quote NOT found in episode text - judge paraphrase]"
            lines.append(f"- {r['slug']} E{f.get('ep')} [{f.get('dimension')}]: \"{f.get('quote')}\" - {f.get('why')}{tag}")
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    main()

