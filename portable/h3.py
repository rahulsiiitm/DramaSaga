"""Compile or execute locally on already provisioned hardware. No cloud rental."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from magicdrama.audiofirst.h3_local import compile_workflow,submit_local,collect_local


def build(clip):
    root=Path(__file__).parent
    graph=json.loads((root/'h3_api_template.json').read_text());bindings=json.loads((root/'h3_bindings.json').read_text())
    if not clip.get('prompt'):raise ValueError('Explicit approved shot prompt required')
    graph['136']['inputs']['prompt']=clip['prompt']
    refs=clip.get('references',[])
    if len(refs)>9:raise ValueError('At most nine H3 image references')
    for i,name in enumerate(refs):
        if not isinstance(name,str) or not name or '/' in name or '\\' in name or name in ('.','..'):raise ValueError('Runtime input basename required')
        key='reference_'+str(i);graph[key]={'class_type':'LoadImage','inputs':{'image':name}}
        graph['136']['inputs']['ref_images.ref_image_'+str(i)]=[key,0]
    return compile_workflow(graph,bindings,clip)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['compile','submit','collect']);p.add_argument('--clip');p.add_argument('--compiled');p.add_argument('--config');p.add_argument('--receipt');p.add_argument('--out',required=True);args=p.parse_args()
    if args.command!='collect' and Path(args.out).exists():raise ValueError('Fresh result path required before any submission')
    if args.command=='compile':result=build(json.loads(Path(args.clip).read_text()))
    elif args.command=='submit':
        if not args.config or not args.compiled or not args.receipt:raise ValueError('Config, compiled workflow and exclusive receipt required')
        result=submit_local(json.loads(Path(args.compiled).read_text()),json.loads(Path(args.config).read_text()),args.receipt)
    else:
        result=collect_local(json.loads(Path(args.config).read_text()),args.receipt,args.out);print(json.dumps(result,indent=2));return
    target=Path(args.out)
    if target.exists():raise ValueError('Refuse to overwrite existing result')
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
