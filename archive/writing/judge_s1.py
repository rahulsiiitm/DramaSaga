import json, os, pathlib, sys
sys.path.insert(0, '/tmp/v3/magicdrama')
from magicdrama.stages import series_v2 as v2
OUT = pathlib.Path('/tmp/v3/honesty_run')
concept = json.loads((OUT/'bible.json').read_text())
concept.setdefault('slug','the-honesty-intern')
arc = json.loads((OUT/'arc.json').read_text())
scripts = [json.loads((OUT/f'ep{e["ep"]:02d}.json').read_text()) for e in arc['episodes']]
ev = v2.evaluate_series_v2(concept, arc, scripts)
(OUT/'eval.json').write_text(json.dumps(ev, indent=1, ensure_ascii=False))
print('SCORES:', json.dumps(ev.get('scores')))
print('PASS:', ev.get('pass'))
print('FAILURES:', len(ev.get('failures', [])))
for f in ev.get('failures', [])[:15]:
    print('-', f.get('ep'), f.get('dimension'), '|', str(f.get('why'))[:120])
