import json
import pathlib

from magicdrama import config
from magicdrama.brief import BRIEF
from magicdrama.canon import CANON, CANON_FACTS
from magicdrama.governor import Spend, estimate_episode_credits
from magicdrama.ledgers import ensure_ledgers, seed_canon
from magicdrama.stages.story import plan_full_arc
from magicdrama.stages.script import episode_script
from magicdrama.stages.render import ab_render_e1, character_master, lock_voices, render_episode
from magicdrama.stages.qa import qa_episode
from magicdrama.validators import validate_script
from magicdrama.clients.magichour import verify_models

def load_brief():
    p = pathlib.Path("samples/brief.json")
    if p.exists():
        return json.loads(p.read_text())
    return BRIEF

def save_state(workdir, stage):
    import json as _json
    from datetime import datetime, timezone
    (workdir / "run_state.json").write_text(_json.dumps({"stage": stage, "ts": datetime.now(timezone.utc).isoformat()}))

def main():
    workdir = config.WORKDIR
    workdir.mkdir(exist_ok=True)
    brief = load_brief()
    from magicdrama.preflight import report as preflight_report
    if not preflight_report(brief, workdir):
        raise SystemExit("preflight failed; fix the FAIL lines above")
    save_state(workdir, "preflight")
    est = estimate_episode_credits(config.SHOT_SECONDS, dialogue_seconds=32, n_images=10)
    print("per-episode estimate:", est, "| batch:", config.EPISODES_RENDER * est["total"], "of", config.BATCH_CAP_CREDITS, "cap | balance", config.BALANCE_CREDITS)
    print("model check:", verify_models())
    ensure_ledgers(workdir)
    arc = seed_canon(workdir, CANON, CANON_FACTS)
    print("canon seeded:", [e["ep"] for e in arc["episodes"] if e.get("canon")])
    arc = plan_full_arc(workdir, brief)
    print("arc episodes:", len(arc["episodes"]), "complete:", arc["complete"])
    save_state(workdir, "arc")
    lock_voices(workdir, brief)
    spend = Spend(workdir)
    masters = [character_master(spend, workdir, c) for c in brief["characters"]]
    print("masters:", [m["character"] for m in masters])
    script = episode_script(workdir, brief, 1)
    print("E1 validation:", validate_script(script, brief) or "clean")
    from magicdrama.stages.tts import synthesize_episode
    from magicdrama.stages.assembly import assemble_episode, probe_duration
    tts_out = synthesize_episode(workdir, brief, script)
    print("E1 TTS lines:", len(tts_out))
    ab_render_e1(spend, workdir, brief)
    asm = assemble_episode(workdir, brief, script, out_name="E01_ab_ltx_2_5.mp4")
    print("E1 assembled:", asm["path"], "duration:", round(probe_duration(asm["path"]), 1))
    for ep in range(2, config.EPISODES_RENDER + 1):
        render_episode(spend, workdir, brief, ep)
    print("E1 QA:", qa_episode(workdir, brief, 1))
    save_state(workdir, "render")
    print("simulated credits:", spend.batch)
    print("dry run complete" if config.DRY_RUN else "real run complete")

if __name__ == "__main__":
    main()

