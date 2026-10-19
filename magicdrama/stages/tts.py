import json

from .. import config
from ..clients.tts import synthesize
from ..ledgers import ledger_row

DEFAULT_VOICES = {
    "default_female": "Magpie-Multilingual.EN-US.Aria",
    "default_male": "Magpie-Multilingual.EN-US.Jason",
}

def voice_map_path(workdir):
    return workdir / "voice_map.json"

def load_voice_map(workdir, brief):
    p = voice_map_path(workdir)
    if p.exists():
        return json.loads(p.read_text())
    vm = {}
    male = DEFAULT_VOICES["default_male"]
    female = DEFAULT_VOICES["default_female"]
    for i, c in enumerate(brief["characters"]):
        vm[c["name"]] = female if i % 2 == 0 else male
    p.write_text(json.dumps(vm, indent=2))
    return vm

def synthesize_episode(workdir, brief, script):
    vm = load_voice_map(workdir, brief)
    ep = script["ep"]
    adir = workdir / "audio" / f"ep{ep:02d}"
    results = []
    for s in script["shots"]:
        for j, d in enumerate(s.get("dialogue", [])):
            voice = vm.get(d["character"])
            assert voice, f"no voice locked for {d['character']}"
            out = adir / f"shot{s['n']:02d}_line{j}.wav"
            if out.exists():
                results.append({"path": str(out), "resumed": True})
                continue
            r = synthesize(d["line"], voice, out)
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).isoformat()
            key = f"tts-ep{ep}-s{s['n']}-{j}"
            ledger_row(workdir, "generation_jobs.csv",
                       [key, f"ep{ep}-s{s['n']}", "", "nvidia-magpie", voice, "tts", key, key, "v3.4", "", "", "", "",
                        "operator-supplied", 0, "credits", "complete", 100, ts, ts, ts, r["path"], "", 0, 2, "", "", "", "", "pending"])
            results.append(r)
    return results

