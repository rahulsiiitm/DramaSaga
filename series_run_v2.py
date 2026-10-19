                      
import json, os, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from magicdrama import config
from magicdrama.stages import series_v2 as v2

BIBLE_PATH = os.environ.get("V2_BIBLE", "/tmp/v3/honesty_intern_bible.json")
OUT = pathlib.Path(os.environ.get("V2_WORKDIR", "/tmp/v3/honesty_run"))
DRAFTS = int(os.environ.get("V2_DRAFTS", "2"))
EPS = int(os.environ.get("V2_EPS", "10"))

def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)

def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False))

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    concept = json.loads(pathlib.Path(BIBLE_PATH).read_text())
    concept.setdefault("slug", "the-honesty-intern")
    arc_path = OUT / "arc.json"
    if arc_path.exists():
        arc = json.loads(arc_path.read_text())
        log(f"arc loaded ({len(arc['episodes'])} eps)")
    else:
        log("generating arc v2...")
        arc = v2.generate_arc_v2(concept, EPS)
        save("arc.json", arc)
        log("arc done")
    mem_path = OUT / "story_memory.json"
    memory = json.loads(mem_path.read_text()) if mem_path.exists() else {"facts": [], "knows": {}}
    df_path = os.environ.get("V2_DOWNSTREAM")
    if df_path and pathlib.Path(df_path).exists():
        memory["downstream_facts"] = json.loads(pathlib.Path(df_path).read_text())
        log(f"downstream guard: {len(memory['downstream_facts'])} facts")
    scripts = {}
    for e in arc["episodes"]:
        ep = e["ep"]
        p = OUT / f"ep{ep:02d}.json"
        if p.exists():
            scripts[ep] = json.loads(p.read_text())
            memory = v2.update_memory(memory, scripts[ep])
            memory["prior_episodes"] = [v2.compact_episode(scripts[k]) for k in sorted(scripts)]
            continue
        prev_cliff = arc["episodes"][ep - 2]["cliffhanger"] if ep > 1 else None
        log(f"E{ep} writing (drafts={DRAFTS})...")
        try:
            s = v2.episode_script_v2(concept, e, v2.memory_slice(memory), prev_cliff, drafts=DRAFTS)
        except Exception as ex:
            log(f"E{ep} CONTAINED: {ex}")
            save(f"ep{ep:02d}.error.json", {"error": str(ex)})
            continue
                                                                                           
        if os.environ.get("V2_GATE", "1") == "1" and scripts:
            priors = [scripts[k] for k in sorted(scripts)]
            try:
                gate = v2.continuity_gate(concept, priors, s, v2.memory_slice(memory))
            except Exception as gx:
                gate = {"ok": True, "clashes": [], "gate_error": str(gx)}
                log(f"E{ep} gate error (proceeding, flagged): {gx}")
            if not gate.get("ok"):
                log(f"E{ep} continuity clash x{len(gate.get('clashes', []))} - regenerating once")
                save(f"ep{ep:02d}.clash1.json", gate)
                e_retry = dict(e); e_retry["_avoid"] = gate.get("clashes", [])
                try:
                    s = v2.episode_script_v2(concept, e_retry, v2.memory_slice(memory), prev_cliff, drafts=DRAFTS)
                    gate = v2.continuity_gate(concept, priors, s, v2.memory_slice(memory))
                except Exception as ex2:
                    log(f"E{ep} CONTAINED on regen: {ex2}")
                    save(f"ep{ep:02d}.error.json", {"error": str(ex2)})
                    continue
                if not gate.get("ok"):
                    log(f"E{ep} STILL CLASHING after 1 retry - run stopped for review")
                    save(f"ep{ep:02d}.error.json", {"error": "continuity clash after 1 retry", "gate": gate})
                    save(f"ep{ep:02d}.gate.json", gate)
                    return
            save(f"ep{ep:02d}.gate.json", gate)
        save(f"ep{ep:02d}.json", s)
        scripts[ep] = s
        memory = v2.update_memory(memory, s)
        memory["prior_episodes"] = [v2.compact_episode(scripts[k]) for k in sorted(scripts)]
        save("story_memory.json", memory)
        log(f"E{ep} done (audit issues: {len(s.get('audit', []))})")
        stop_after = int(os.environ.get("V2_STOP_AFTER", "10"))
        if ep >= stop_after:
            log(f"stopping after E{ep} per V2_STOP_AFTER")
            save("story_memory.json", memory)
            return
    done = [scripts[e["ep"]] for e in arc["episodes"] if e["ep"] in scripts]
    log(f"{len(done)}/{EPS} episodes written")
    if len(done) == EPS and not (OUT / "eval.json").exists():
        log("judging (v2, realism dim, pass>=80)...")
        ev = v2.evaluate_series_v2(concept, arc, done)
        save("eval.json", ev)
        log(f"eval: {ev.get('scores')} pass={ev.get('pass')}")
    log("RUN_V2_DONE")

if __name__ == "__main__":
    main()

