import json, os, pathlib, sys
sys.path.insert(0, '/tmp/v3/magicdrama')
from magicdrama.stages import series_v2 as v2
OUT = pathlib.Path('/tmp/v3/honesty_run')
concept = json.loads((OUT/'bible.json').read_text()); concept.setdefault('slug','the-honesty-intern')
arc = json.loads((OUT/'arc.json').read_text())
scripts = []
for e in arc['episodes']:
    v3 = OUT/f"ep{e['ep']:02d}.v3.json"
    scripts.append(json.loads((v3 if v3.exists() else OUT/f"ep{e['ep']:02d}.json").read_text()))
ev = v2.evaluate_series_v2(concept, arc, scripts)
(OUT/'eval.v3.json').write_text(json.dumps(ev, indent=1, ensure_ascii=False))
print('SCORES:', json.dumps(ev.get('scores')))
print('PASS:', ev.get('pass'))
for f in ev.get('failures', [])[:12]:
    print('-', f.get('ep'), f.get('dimension'), '|', str(f.get('why'))[:130])
