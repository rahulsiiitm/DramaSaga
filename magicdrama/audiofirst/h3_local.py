"""Offline H3 workflow compiler and explicitly gated local Comfy runtime transport.

No model download, GPU purchase, external agent or remote cloud compute.
"""
import copy
import json
from pathlib import Path
from urllib.parse import urlparse
import requests
from .core import digest,finite,integer
from .execution import signature


def compile_workflow(template,bindings,clip):
    graph=copy.deepcopy(template)
    if not isinstance(bindings,dict) or not isinstance(clip,dict):raise ValueError('Structured bindings/clip required')
    if not graph or not isinstance(graph,dict):raise ValueError('Explicit pinned API workflow template required')
    allowed={'LoadImage','LoadAudio','VAEEncodeAudio','SolidMask','SetLatentNoiseMask','LTXVConcatAVLatent',
             'MiniMaxH3AddGuide','MiniMaxH3ReferenceToVideo','CLIPLoader','UNETLoader','VAELoader',
             'CLIPTextEncode','KSampler','KSamplerAdvanced','SamplerCustomAdvanced','RandomNoise',
             'BasicScheduler','KSamplerSelect','CFGGuider','BasicGuider','CreateVideo','SaveVideo','VAEDecodeAudio','EmptyLatentImage','VAEDecode','VHS_VideoCombine'}
    if any(str(k).startswith('md_') for k in graph):raise ValueError('Template collides with reserved compiler node IDs')
    for node in graph.values():
        if not isinstance(node,dict) or node.get('class_type') not in allowed or not isinstance(node.get('inputs'),dict):
            raise ValueError('Unknown/custom execution node must be reviewed before compiling')
    assets=[clip['audio_asset']]+[p['asset'] for p in clip.get('pins',[])]
    if any(not isinstance(a,str) or not a or '/' in a or '\\' in a or a in ('.','..') for a in assets):raise ValueError('Local runtime asset names only, not paths/URLs')
    seconds=finite(clip['seconds'],'clip seconds',.01)
    if seconds>15:raise ValueError('Conservative local H3 clip cap 15 seconds')
    frames=max(5,__import__('math').ceil(seconds*24));frames+=(5-frames%17)%17
    for name in ('positive','video_latent','audio_vae','video_vae','sampler'):
        if bindings[name] not in graph:raise ValueError('Missing workflow binding '+name)
    positive=[bindings['positive'],0];latent=[bindings['video_latent'],bindings.get('video_latent_output',0)]
    graph['md_audio']={'class_type':'LoadAudio','inputs':{'audio':clip['audio_asset']}}
    graph['md_aenc']={'class_type':'VAEEncodeAudio','inputs':{'audio':['md_audio',0],'vae':[bindings['audio_vae'],0]}}
    graph['md_mask']={'class_type':'SolidMask','inputs':{'value':0.0,'width':8,'height':8}}
    graph['md_keep']={'class_type':'SetLatentNoiseMask','inputs':{'samples':['md_aenc',0],'mask':['md_mask',0]}}
    graph['md_av']={'class_type':'LTXVConcatAVLatent','inputs':{'video_latent':latent,'audio_latent':['md_keep',0]}}
    previous=-1
    for i,pin in enumerate(clip.get('pins',[])):
        t=finite(pin['seconds'],'pin time')
        if t<previous or t>=seconds:raise ValueError('Pins must be ordered within clip')
        previous=t
        graph['md_image'+str(i)]={'class_type':'LoadImage','inputs':{'image':pin['asset']}}
        key='md_pin'+str(i)
        graph[key]={'class_type':'MiniMaxH3AddGuide','inputs':{'positive':positive,'vae':[bindings['video_vae'],0],
            'latent':latent,'image':['md_image'+str(i),0],'frame_idx':round(t*24)}};positive=[key,0]
    for name in ('width','height'):
        if name in clip:
            integer(clip[name],name,64,2048)
            if clip[name]%32:raise ValueError('H3 dimensions must be multiples of 32')
            if 'frame_count_node' in bindings:graph[bindings['frame_count_node']]['inputs'][name]=clip[name]
    if 'frame_count_node' in bindings:
        key=bindings['frame_count_node']
        if key not in graph or graph[key]['class_type']!='MiniMaxH3ReferenceToVideo':raise ValueError('Frame binding must identify the H3 latent node')
        graph[key]['inputs']['length']=frames
    graph[bindings['sampler']]['inputs']['latent_image']=['md_av',0]
    if 'guider' in bindings:
        if bindings['guider'] not in graph or graph[bindings['guider']]['class_type']!='BasicGuider':raise ValueError('Explicit BasicGuider binding required')
        graph[bindings['guider']]['inputs']['conditioning']=positive
    else:graph[bindings['sampler']]['inputs']['positive']=positive
    return {'workflow':graph,'workflow_sha256':signature(graph),'frames':frames,'fps':24,
            'padded_audio_seconds':frames/24,'trim_to_seconds':seconds,'live_enabled':False,
            'status':'compiled_not_runtime_validated','required':'licensed installed H3 model/runtime and explicit local compute permission'}


def runtime_preflight(config,http=None):
    if config.get('enabled') is not True:raise RuntimeError('H3 local runtime disabled by default')
    compute_ok=config.get('free_local_compute') is True or (config.get('already_provisioned_compute') is True and bool(config.get('compute_approval_reference')))
    if not compute_ok or not config.get('model_license_reference') or not config.get('owner_approval_reference'):
        raise ValueError('Verified model license and explicit available-compute authority required')
    p=urlparse(config['url'])
    if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost') or p.username or p.password or p.path not in ('','/'):
        raise ValueError('Only explicit loopback Comfy runtime supported; no remote paid host')
    for asset in config.get('model_files',[]):
        path=Path(asset['path'])
        if not path.is_file() or digest(path)!=asset['sha256']:raise ValueError('Licensed installed weights absent or changed')
    if not config.get('model_files'):raise ValueError('Installed weight manifest required, never auto-download')
    session=http or requests.Session();r=session.get(config['url'].rstrip('/')+'/object_info',timeout=10,allow_redirects=False);r.raise_for_status()
    if r.status_code!=200:raise ValueError('Runtime metadata unavailable')
    required={'MiniMaxH3AddGuide','VAEEncodeAudio','SetLatentNoiseMask','LTXVConcatAVLatent'}
    if not required<=set(r.json()):raise ValueError('Runtime lacks fixed-audio/guide nodes')
    return {'status':'local_runtime_metadata_checked_not_inference_tested'}


def submit_local(compiled,config,receipt_path,http=None):
    session=http or requests.Session();runtime_preflight(config,session)
    p=Path(receipt_path)
    if p.exists():raise RuntimeError('Existing local job receipt: reconcile/resume, never duplicate GPU submission')
    if signature(compiled['workflow'])!=compiled['workflow_sha256']:raise ValueError('Compiled workflow changed')
    if config.get('approved_workflow_sha256')!=compiled['workflow_sha256']:raise ValueError('Exact workflow approval missing')
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as receipt:receipt.write(json.dumps({'state':'submitting','workflow_sha256':compiled['workflow_sha256']}))
    try:
        r=session.post(config['url'].rstrip('/')+'/prompt',json={'prompt':compiled['workflow']},timeout=30,allow_redirects=False)
        r.raise_for_status()
        if r.status_code!=200:raise ValueError('Local runtime rejected request')
        result=r.json()
        if result.get('node_errors') or not result.get('prompt_id'):raise ValueError('Local workflow validation failed')
        p.write_text(json.dumps({'state':'submitted','prompt_id':result['prompt_id'],'workflow_sha256':compiled['workflow_sha256']}));return result
    except Exception:
        p.write_text(json.dumps({'state':'unknown','workflow_sha256':compiled['workflow_sha256']}));raise


def collect_local(config,receipt_path,output_dir,http=None):
    """Read local job history and copy verified output beneath an explicit runtime root."""
    import shutil
    session=http or requests.Session();runtime_preflight(config,session)
    receipt=Path(receipt_path);data=json.loads(receipt.read_text())
    if data.get('state')!='submitted' or not isinstance(data.get('prompt_id'),str) or not __import__('re').fullmatch(r'[A-Za-z0-9_-]+',data['prompt_id']):
        raise ValueError('Submitted prompt ID required; unknown jobs need manual reconciliation')
    r=session.get(config['url'].rstrip('/')+'/history/'+data['prompt_id'],timeout=15,allow_redirects=False);r.raise_for_status()
    if r.status_code!=200:raise ValueError('Local history unavailable')
    history=r.json().get(data['prompt_id'])
    if not history:return {'status':'pending','prompt_id':data['prompt_id']}
    if history.get('status',{}).get('status_str')=='error':raise RuntimeError('Local inference failed, no automatic resubmit')
    base=Path(config['runtime_output_root']).resolve();dest=Path(output_dir)
    if dest.exists():raise ValueError('Fresh output directory required')
    files=[]
    for node in history.get('outputs',{}).values():
        for item in node.get('gifs',[])+node.get('videos',[])+node.get('images',[]):
            if item.get('type')!='output':continue
            raw=base/item.get('subfolder','')/item['filename']
            if raw.is_symlink():raise ValueError('Runtime output symlinks refused')
            path=raw.resolve()
            if base not in path.parents or path.suffix.lower() not in ('.mp4','.webm') or not path.is_file():raise ValueError('Output outside approved local runtime root or invalid format')
            files.append(path)
    if not files:return {'status':'pending_or_no_video','prompt_id':data['prompt_id']}
    if len(files)!=1:raise ValueError('Ambiguous local outputs; do not choose silently')
    dest.mkdir(parents=True);target=dest/('render'+files[0].suffix);shutil.copyfile(files[0],target)
    result={'status':'downloaded_local_render_requires_qa','path':str(target.resolve()),'sha256':digest(target),'prompt_id':data['prompt_id']}
    receipt.write_text(json.dumps({**data,'state':'complete','result':result}));return result
