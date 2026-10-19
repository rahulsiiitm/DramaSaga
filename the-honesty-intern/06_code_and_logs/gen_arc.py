import json, pathlib, sys, time
sys.path.insert(0, "/tmp/v3/magicdrama")
from magicdrama.stages import series_v2 as v2
OUT = pathlib.Path("/tmp/v3/honesty_run")
concept = json.loads((OUT/"bible.json").read_text())
concept.setdefault("slug", "the-honesty-intern")
print(time.strftime("%H:%M:%S"), "generating arc v2...", flush=True)
arc = v2.generate_arc_v2(concept, 10)
(OUT/"arc.json").write_text(json.dumps(arc, indent=1, ensure_ascii=False))
print(time.strftime("%H:%M:%S"), "arc done:", len(arc.get("episodes",[])), "eps", flush=True)
