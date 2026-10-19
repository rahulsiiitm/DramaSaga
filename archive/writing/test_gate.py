import json, os, pathlib, sys, time
sys.path.insert(0, '/tmp/v3/magicdrama')
from magicdrama.stages import series_v2 as v2
H = pathlib.Path('/tmp/v3/honesty_run')
J = lambda p: json.loads((H/p).read_text())
concept = J('bible.json'); concept.setdefault('slug','the-honesty-intern')
mem = J('story_memory.json')

def run(name, prior_paths, new_path):
    priors = [J(p) for p in prior_paths]
    new = J(new_path)
    t0 = time.time()
    try:
        g = v2.continuity_gate(concept, priors, new, v2.memory_slice(mem))
        dt = time.time()-t0
        print(f"[{name}] {dt:.0f}s ok={g.get('ok')} clashes={len(g.get('clashes', []))}")
        for c in g.get('clashes', [])[:6]:
            print(f"   - {c.get('kind')}: {str(c.get('why'))[:110]}")
    except Exception as e:
        print(f"[{name}] FAILED after {time.time()-t0:.0f}s: {type(e).__name__} {str(e)[:200]}")

                                                                        
run("A v2E1-4 vs v1E5 (expect CLASH)", ['ep01.json','ep02.json','ep03.json','ep04.json'], 'ep05.json')
                                                     
run("C v1E1-4 vs v1E5 (expect OK)", ['ep01.bak.json','ep02.bak.json','ep03.bak.json','ep04.bak.json'], 'ep05.json')
                                                                                
run("B priors vs v2E7 (expect CLASH)", ['ep01.json','ep02.json','ep03.json','ep04.json','ep05.json','ep06.json'], 'ep07.json')
