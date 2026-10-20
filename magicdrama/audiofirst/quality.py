"""Fail-closed local QA orchestration. Unavailable semantic checks never pass."""
import datetime as dt
import json
import math
import subprocess
from pathlib import Path
from PIL import Image,ImageStat
from .core import digest,finite,write_json
from .execution import signature

CHECKS=('identity','wardrobe','props','prop_orientation','action','expression','lip_sync','speech','continuity')


def sample_frames(video,output,interval=.5,max_frames=361):
    interval=finite(interval,'sample interval',.1)
    if interval>.5:raise ValueError('QA samples at least twice per second')
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(video)],text=True));duration=float(info['format']['duration'])
    if duration>180 or math.ceil(duration/interval)>max_frames:raise ValueError('QA duration/sample limit exceeded')
    root=Path(output);root.mkdir(parents=True,exist_ok=False)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(video),'-vf',f'fps=1/{interval}','-frames:v',str(max_frames),str(root/'frame-%05d.png')],check=True,capture_output=True)
    paths=sorted(root.glob('frame-*.png'))
    if not paths:raise ValueError('No decoded frames')
    return paths


def image_metrics(path):
    with Image.open(path) as im:
        im.load();w,h=im.size
        if w<100 or h<100:raise ValueError('Image too small')
        grey=im.convert('L');stats=ImageStat.Stat(grey);variance=stats.var[0]
        return {'width':w,'height':h,'luma_mean':stats.mean[0],'luma_variance':variance,
                'blank_or_extreme':variance<2 or stats.mean[0]<3 or stats.mean[0]>252}


def visual_evidence(asset,frames,references,expectations,evaluator,engine):
    """Evaluator is an explicit local callable, never a paid/cloud auto-fallback.

    It must inspect frames/references and return per-check boolean/confidence/reason.
    The resulting evidence is model/algorithm evidence, not authenticated human review.
    """
    if not callable(evaluator) or not engine.get('id') or not engine.get('version') or engine.get('local_free') is not True:
        raise ValueError('Explicit versioned free/local evaluator required')
    frame_records=[{'path':str(p),'sha256':digest(p)} for p in frames]
    reference_records=[{'path':str(p),'sha256':digest(p)} for p in references]
    context={'asset_sha256':digest(asset),'frames':frame_records,'references':reference_records,'expectations':expectations}
    checks=evaluator(context)
    if not isinstance(checks,dict):raise ValueError('Evaluator result must be structured checks')
    return {**context,'expectations_sha256':signature(expectations),'engine':engine,'checks':checks,
            'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'scope':'sampled_frames_not_every_pixel_or_human_review'}


def decide_quality(asset,expectations,evidence,required=CHECKS,min_confidence=.95):
    """Two distinct explicit evaluators must agree. Unknown or stale evidence rejects."""
    if not evidence or len(evidence)<2:raise ValueError('Two independent local quality evaluators required')
    if type(min_confidence) not in (int,float) or not .95<=min_confidence<=1:raise ValueError('Cannot loosen confidence threshold below .95')
    if not required or any(k not in CHECKS for k in required):raise ValueError('Explicit known quality checks required')
    engines=[];reasons=[]
    for e in evidence:
        engine=e.get('engine',{});identity=(engine.get('id'),engine.get('version'))
        if not all(identity) or engine.get('local_free') is not True:raise ValueError('Unverified evaluator identity/scope')
        engines.append(identity)
        if e.get('expectations')!=expectations:raise ValueError('QA expectation content changed')
        if e.get('asset_sha256')!=digest(asset) or e.get('expectations_sha256')!=signature(expectations):raise ValueError('QA evidence is stale for asset/expectations')
        for item in e.get('frames',[])+e.get('references',[]):
            if not Path(item['path']).is_file() or digest(item['path'])!=item['sha256']:raise ValueError('QA sampled/reference pixels changed')
        if not e.get('frames'):raise ValueError('Semantic QA needs actual sampled frame bytes')
        for key in required:
            c=e.get('checks',{}).get(key,{})
            confidence=c.get('confidence')
            if c.get('pass') is not True or type(confidence) not in (int,float) or not math.isfinite(confidence) or not min_confidence<=confidence<=1 or not c.get('reason'):
                reasons.append(key+': failed, unknown or low confidence from '+identity[0])
    if len(set(x[0] for x in engines))!=len(engines):raise ValueError('Duplicate evaluator is not independent')
    if reasons:raise ValueError('Quality rejected: '+'; '.join(reasons))
    return {'asset_sha256':digest(asset),'expectations_sha256':signature(expectations),'checks':list(required),
            'evidence_sha256':signature(evidence),'status':'automatic_evidence_gate_passed_not_quality_guarantee',
            'engines':engines,'requires_full_playback':True}


def lip_sync_score(audio_envelope,mouth_open,step_seconds=.04,max_offset_seconds=.12):
    """Screen tracked mouth motion vs speech envelope; does not recognize phonemes."""
    if len(audio_envelope)!=len(mouth_open) or len(mouth_open)<25:raise ValueError('Aligned tracked arrays >=25 samples required')
    step=finite(step_seconds,'step',.001)
    a=[finite(v,'audio') for v in audio_envelope];b=[finite(v,'mouth') for v in mouth_open]
    def correlation(x,y):
        mx=sum(x)/len(x);my=sum(y)/len(y);sx=sum((v-mx)**2 for v in x);sy=sum((v-my)**2 for v in y)
        return sum((u-mx)*(v-my) for u,v in zip(x,y))/math.sqrt(sx*sy) if sx>0 and sy>0 else None
    window=min(len(a)//4,round(.5/step));scores=[]
    for lag in range(-window,window+1):
        x=a[max(0,-lag):len(a)-max(0,lag)];y=b[max(0,lag):len(b)-max(0,-lag)];score=correlation(x,y)
        if score is not None:scores.append((score,lag))
    if not scores:raise ValueError('No speech/mouth variation; lip sync unverifiable')
    score,lag=max(scores,key=lambda x:x[0]);offset=lag*step
    return {'correlation':score,'offset_seconds':offset,'screen_pass':score>=.7 and abs(offset)<=max_offset_seconds,
            'status':'correlation_screen_not_phoneme_or_identity_certification'}


def tracked_lip_sync(video,audio,track,step_seconds=.04):
    """Bind correlation screening to actual audio and tracked visible speaker landmarks.

    Tracker identity must be explicit; no tracking model or face inference is downloaded.
    This is one technical signal and never substitutes for phoneme/speaker judging.
    """
    import wave
    from array import array
    if track.get('video_sha256')!=digest(video) or track.get('audio_sha256')!=digest(audio):raise ValueError('Mouth track belongs to different media')
    if track.get('identity_verified') is not True:raise ValueError('Face tracking does not establish speaker identity; independent identity evidence required')
    if not track.get('engine') or not track.get('speaker_id'):raise ValueError('Named tracker and bound speaker required')
    with wave.open(str(audio),'rb') as f:
        if f.getsampwidth()!=2:raise ValueError('PCM16 audio required')
        rate=f.getframerate();channels=f.getnchannels();samples=array('h',f.readframes(f.getnframes()))
    if __import__('sys').byteorder!='little':samples.byteswap()
    entries=track.get('samples',[]);envelope=[];mouth=[]
    for i,item in enumerate(entries):
        if abs(finite(item['seconds'],'track timestamp')-i*step_seconds)>.002:raise ValueError('Continuous uniformly sampled mouth track required')
        if item.get('visible_speakers')!=1 or finite(item.get('confidence',0),'tracking confidence')<.95:raise ValueError('Occluded/ambiguous mouth tracking')
        a=round(i*step_seconds*rate)*channels;b=round((i+1)*step_seconds*rate)*channels;block=samples[a:b]
        if not block:raise ValueError('Mouth track exceeds audio')
        envelope.append(math.sqrt(sum(v*v for v in block)/len(block))/32768)
        mouth.append(finite(item['mouth_open'],'mouth opening'))
    if len(samples)/channels/rate-len(entries)*step_seconds>.08:raise ValueError('Mouth track does not cover audio')
    result=lip_sync_score(envelope,mouth,step_seconds)
    return {**result,'video_sha256':digest(video),'audio_sha256':digest(audio),'speaker_id':track['speaker_id'],'tracker':track['engine']}
