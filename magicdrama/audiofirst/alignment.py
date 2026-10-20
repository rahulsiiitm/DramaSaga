"""Exact-script recovery from an installed local ASR model, CPU only, no downloads."""
import math
import re
import wave
from array import array
from pathlib import Path
from .core import digest,finite


def tokens(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?",text.casefold().replace('\u2019',"'"))


class LocalWhisper:
    def __init__(self,model_path,model_factory=None):
        path=Path(model_path)
        if not path.is_dir() or not (path/'model.bin').is_file():
            raise ValueError('Existing licensed local faster-whisper model directory required; no download')
        if model_factory is None:
            try:from faster_whisper import WhisperModel
            except ImportError as e:raise RuntimeError('Install faster-whisper separately from official PyPI with permission') from e
            model_factory=WhisperModel
        self.model=model_factory(str(path.resolve()),device='cpu',compute_type='int8',local_files_only=True)
    def __call__(self,path,start=0,end=None):
        kwargs={'word_timestamps':True,'vad_filter':False,'beam_size':5,'language':'en','condition_on_previous_text':False}
        if start or end is not None:
            if end is None:raise ValueError('Bounded recovery clip required')
            kwargs['clip_timestamps']=[start,end]
        segments,_=self.model.transcribe(str(path),**kwargs)
        return [{'word':w.word,'start':w.start,'end':w.end,'probability':w.probability}
                for segment in segments for w in segment.words or []]


def energy_onset(path,start,end,threshold_db=-40):
    with wave.open(str(path),'rb') as f:
        if f.getsampwidth()!=2 or f.getcomptype()!='NONE':raise ValueError('Alignment requires PCM16 WAV')
        rate=f.getframerate();channels=f.getnchannels();duration=f.getnframes()/rate
        a=max(0,int(start*rate));b=min(f.getnframes(),int(end*rate));f.setpos(a)
        samples=array('h',f.readframes(max(0,b-a)))
    if __import__('sys').byteorder!='little':samples.byteswap()
    step=max(1,round(rate*.01))*channels;threshold=32768*10**(threshold_db/20)
    for i in range(0,len(samples),step):
        block=samples[i:i+step]
        if block and math.sqrt(sum(s*s for s in block)/len(block))>=threshold:return a/rate+i/channels/rate
    return None


def validate_words(words,duration,min_probability=.65):
    result=[];previous=0
    if not words:raise ValueError('ASR returned no words')
    for w in words:
        ts=tokens(w['word'])
        if not ts:continue
        start=finite(w['start'],'word start');end=finite(w['end'],'word end');prob=finite(w.get('probability',0),'word probability')
        if start<previous-.001 or end<=start or end>duration+.03 or prob<min_probability or prob>1:raise ValueError('Low-confidence or invalid actual-audio word timing')
        if len(ts)!=1:raise ValueError('ASR word contains multiple normalized words; needs explicit corrected alignment')
        result.append({**w,'token':ts[0]});previous=end
    if not result:raise ValueError('No usable word timings')
    return result


def recover_alignment(path,lines,transcriber,recovery_windows=None,min_probability=.65):
    """Every script word must match ASR, without silent skipping/number substitution.

    Optional nonoverlapping recovery windows cause independent bounded retranscription.
    They are operator-supplied timeline windows, never invented from bad provider drift.
    """
    if type(min_probability) not in (int,float) or not .65<=min_probability<=1:raise ValueError('Cannot loosen ASR confidence below .65')
    with wave.open(str(path),'rb') as f:
        if f.getsampwidth()!=2:raise ValueError('PCM16 WAV required')
        duration=f.getnframes()/f.getframerate()
    if not lines or duration<=0 or duration>180:raise ValueError('Nonempty episode <=180 seconds required')
    raw=transcriber(path,0,None)
    previous=0
    for window in recovery_windows or []:
        start=finite(window['start'],'recovery start');end=finite(window['end'],'recovery end')
        if start<previous or end<=start or end>duration:raise ValueError('Invalid/overlapping recovery window')
        replacement=transcriber(path,start,end)
        if not replacement or any(w['start']<start-.02 or w['end']>end+.02 for w in replacement):raise ValueError('Recovery words not bound to requested clip')
        raw=[w for w in raw if w['end']<=start or w['start']>=end]+replacement
        raw.sort(key=lambda w:w['start']);previous=end
    words=validate_words(raw,duration,min_probability)
    expected=[t for line in lines for t in tokens(line['text'])]
    if expected!=[w['token'] for w in words]:raise ValueError('Actual-audio transcript differs from script; no guessed offsets or dropped words')
    cues=[];cursor=0
    for line in lines:
        count=len(tokens(line['text']))
        if not count:raise ValueError('Script line has no words')
        group=words[cursor:cursor+count];cursor+=count
        # Split only at exact source word boundaries, preserving punctuation and case.
        source=re.findall(r'\S+',line['text']);groups=[];current=[];group_tokens=0;offset=0
        for item in source:
            n=len(tokens(item))
            if current and (len(' '.join(current+[item]))>72 or group_tokens+n>12):
                groups.append((current,offset,offset+group_tokens));offset+=group_tokens;current=[];group_tokens=0
            current.append(item);group_tokens+=n
        if current:groups.append((current,offset,offset+group_tokens))
        for textparts,a,b in groups:
            if b<=a:raise ValueError('Unsupported punctuation-only cue')
            start=group[a]['start'];end=group[b-1]['end'];text=' '.join(textparts)
            onset=energy_onset(path,max(0,start-.15),min(duration,start+.25))
            if onset is None or abs(onset-start)>.2:raise ValueError('ASR cue onset not supported by nearby signal')
            if len(text)/(end-start)>25:raise ValueError('Aligned cue too fast; do not extend across other speech automatically')
            cues.append({'line_id':line['id'],'speaker':line['speaker'],'text':text,'start':start,'end':end,
                         'actual_audio_checked':True,'timing_method':'local_exact_word_match_plus_signal_not_human_certified'})
    return {'audio_sha256':digest(path),'duration':duration,'words':words,'cues':cues,
            'status':'local_alignment_checks_passed_not_speech_quality_certified','paid_requests':0}
