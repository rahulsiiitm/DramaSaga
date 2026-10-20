"""Automatic evidence decisions for real bytes, never unconditional quality approval."""
import copy
import json
from pathlib import Path
from .core import digest,write_json
from .assembly import checked
from .alignment import recover_alignment,LocalWhisper
from .quality import decide_quality,visual_evidence,sample_frames,image_metrics,CHECKS


def accept_asset(asset,expectations,evaluators,workspace,kind='video'):
    path=checked(asset)
    if len(evaluators)<2:raise ValueError('Automatic acceptance unavailable without two configured independent local evaluators')
    Path(workspace).mkdir(parents=True,exist_ok=False)
    references=[checked(x) for x in expectations.get('references',[])]
    if kind=='video':frames=sample_frames(path,Path(workspace)/'frames')
    elif kind=='image':
        metrics=image_metrics(path)
        if metrics['blank_or_extreme']:raise ValueError('Blank/extreme image rejected')
        frames=[path]
    else:raise ValueError('Visual acceptance kind must be image or video')
    evidence=[]
    for evaluator in evaluators:
        evidence.append(visual_evidence(path,frames,references,expectations,evaluator['evaluate'],evaluator['engine']))
    required=CHECKS if kind=='video' else tuple(c for c in CHECKS if c not in ('lip_sync','speech'))
    verdict=decide_quality(path,expectations,evidence,required=required)
    result={'asset':asset,'verdict':verdict,'evidence':evidence}
    write_json(Path(workspace)/'acceptance.json',result);return result


def prepare_episode(episode,workspace,transcriber=None,evaluators=None):
    """Optional automatic alignment and output acceptance inside production runner.

    No evaluator implementation/model is bundled or assumed. Missing engines reject.
    Existing manual accepted-media assembly remains a separate explicit mode.
    """
    result=copy.deepcopy(episode);root=Path(workspace);root.mkdir(parents=True,exist_ok=True)
    audio=checked(result['audio']);lines=result.get('dialogue_lines')
    if audio.suffix.lower()!='.wav':
        import subprocess
        original=digest(audio);decoded=root/'decoded-master.wav'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(audio),'-c:a','pcm_s16le',str(decoded)],check=True,capture_output=True,timeout=120)
        audio=decoded;result['audio']={'path':str(decoded.resolve()),'sha256':digest(decoded),'source_sha256':original}
    if not lines:raise ValueError('Exact line IDs/speakers/text required for automatic preparation')
    if transcriber is None:
        config=result.get('alignment',{})
        if not config.get('local_model_path'):raise ValueError('Existing local ASR model required; no paid/download fallback')
        transcriber=LocalWhisper(config['local_model_path'])
    aligned=recover_alignment(audio,lines,transcriber,result.get('alignment',{}).get('recovery_windows'))
    write_json(root/'alignment.json',aligned)
    result['cues']=aligned['cues'];result['cue_audio_sha256']=aligned['audio_sha256'];result['spoken_lines']=[l['text'] for l in lines]
    # Exact ASR match covers text/timing, not speaker identity or emotional performance.
    audio_qa=result.get('audio_quality_evidence',[])
    required=('speech','identity','expression')
    decide_quality(audio,{'lines':lines,'kind':'speech'},audio_qa,required=required)
    result['audio_checked']=True
    for i,shot in enumerate(result['shots']):
        if not shot.get('expectations'):raise ValueError('Explicit prop/action/identity expectations required')
        accept_asset(shot,shot['expectations'],evaluators or [],root/('shot-'+str(i)),shot['kind'])
        shot['pixel_checked']=True
    result['automatic_checks']={'audio_sha256':digest(audio),'status':'evidence_gate_passed_not_human_quality_certification'}
    return result
