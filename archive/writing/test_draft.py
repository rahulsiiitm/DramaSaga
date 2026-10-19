import json, os, pathlib, sys, time
sys.path.insert(0, '/tmp/v3/magicdrama')
from magicdrama.stages import series_v2 as v2
H = pathlib.Path('/tmp/v3/honesty_run')
J = lambda p: json.loads((H/p).read_text())
concept = J('bible.json'); concept.setdefault('slug','the-honesty-intern')
arc = J('arc.json')
mem = J('story_memory.json')
priors = [J(f'ep{e:02d}.json') for e in [1,2,3,4]]
mem['prior_episodes'] = [v2.compact_episode(s) for s in priors]
e5 = [e for e in arc['episodes'] if e['ep']==5][0]
prev_cliff = arc['episodes'][3]['cliffhanger']
t0=time.time()
try:
    s = v2.episode_script_v2(concept, e5, v2.memory_slice(mem), prev_cliff, drafts=2)
    dt=time.time()-t0
    issues = v2.coverage_audit(s)
    print(f"DRAFT OK {dt:.0f}s shots={len(s.get('shots',[]))} audit_issues={len(issues)} title={s.get('title')!r}")
    for i in issues[:5]: print("  audit:", i)
                                          
    lines = [d['line'] for sh in s.get('shots',[]) for d in sh.get('dialogue',[])][:5]
    print("  sample lines:", json.dumps(lines, ensure_ascii=False)[:400])
except Exception as ex:
    print(f"DRAFT FAILED {time.time()-t0:.0f}s: {type(ex).__name__} {str(ex)[:300]}")
