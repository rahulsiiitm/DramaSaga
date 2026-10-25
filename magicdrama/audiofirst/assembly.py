"""Local episode/season assembly from accepted assets. No network or paid generation."""
import json
import math
import shutil
import subprocess
from pathlib import Path
from .core import digest,finite,integer,identifier,measure_audio,write_json
from .pipeline import validate_free_audio_asset
from .subtitles import stamp,subtitle_text
from .season import pack_season


def checked(asset):
    p=Path(asset['path'])
    if not p.is_file() or digest(p)!=asset['sha256']:raise ValueError('Absent or changed media asset')
    return p.resolve()


def ff(args):
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y',*map(str,args)],check=True,capture_output=True)


def media_info(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],text=True))


def caption_file(cues,names,duration,path):
    import textwrap
    rows=['[Script Info]','ScriptType: v4.00+','PlayResX: 1080','PlayResY: 1920','WrapStyle: 2','', '[V4+ Styles]',
          'Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding',
          'Style: Default,DejaVu Sans,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,90,90,180,1',
          'Style: Speaker,DejaVu Sans,36,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,3,4,0,2,90,90,320,1',
          '[Events]','Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text']
    srt=[];previous=0;introduced=set()
    for i,c in enumerate(cues,1):
        start=finite(c['start'],'cue start');end=finite(c['end'],'cue end');text=subtitle_text(c['text'])
        if start<previous or end<=start or end>duration+.01:raise ValueError('Caption intervals overlap or exceed audio')
        if c.get('actual_audio_checked') is not True:raise ValueError('Caption timing not checked against actual audio')
        lines=textwrap.wrap(text,42,break_long_words=False,break_on_hyphens=False)
        if not lines or len(lines)>2 or any(len(s)>42 for s in lines) or len(text)/(end-start)>25:raise ValueError('Caption readability requires word-aligned splitting')
        a,b=round(start*1000),round(end*1000)
        rows.append(f'Dialogue: 0,{stamp(a,True)},{stamp(b,True)},Default,,0,0,0,,'+r'\N'.join(lines))
        speaker=c['speaker']
        if speaker!='narrator':
            name=subtitle_text(names[speaker])
            if not name or len(name)>32:raise ValueError('Name length out of range')
            if speaker not in introduced:
                introduced.add(speaker)
                rows.append(fr'Dialogue: 2,{stamp(a,True)},{stamp(min(b,a+2000),True)},Speaker,,0,0,0,,{{\an7\pos(90,180)}}'+name)
            rows.append(f'Dialogue: 1,{stamp(a,True)},{stamp(b,True)},Speaker,,0,0,0,,'+name)
        srt.append(f'{i}\n{stamp(a)} --> {stamp(b)}\n'+'\n'.join(lines)+'\n');previous=end
    if not cues:raise ValueError('Exact checked caption cues required')
    Path(path).write_text('\n'.join(rows)+'\n');Path(path).with_suffix('.srt').write_text('\n'.join(srt))


def assemble_episode(spec,output,backend='own',size=(540,960),cache_dir=None):
    output=Path(output)
    if output.exists():raise ValueError('Fresh episode output directory required')
    master=checked(spec['audio']);duration=measure_audio(master)
    if duration>180:raise ValueError('Episode exceeds 180 seconds')
    if spec.get('audio_checked') is not True:raise ValueError('Speech words/speakers/emotion require actual audio check evidence')
    cues=spec['cues']
    if spec.get('cue_audio_sha256')!=spec['audio']['sha256']:raise ValueError('Cues not bound to actual master audio')
    if not isinstance(spec.get('spoken_lines'),list) or not spec['spoken_lines']:raise ValueError('Exact spoken lines required for subtitle validation')
    if spec.get('spoken_lines') is not None:
        def norm(t):return ' '.join(t.split())
        if norm(' '.join(c['text'] for c in cues))!=norm(' '.join(spec['spoken_lines'])):raise ValueError('Caption text differs from exact speech')
    fps=24;total=math.ceil(duration*fps);cursor=0;validated=[]
    for shot in spec['shots']:
        frames=integer(shot['frames'],'frames',1,4320);path=checked(shot)
        if shot.get('pixel_checked') is not True:raise ValueError('Shot pixels not checked')
        offset=integer(shot.get('source_start_frame',0),'source_start_frame',0,24*180)
        validated.append((path,frames,shot['kind'],offset));cursor+=frames
    if cursor!=total:raise ValueError('Shot frames must cover measured audio exactly')
    w,h=size
    if w/h!=9/16 or any(type(x) is not int or x<100 or x%2 for x in size):raise ValueError('Even portrait 9:16 output dimensions required')
    soundtrack=spec.get('soundtrack',[])
    for a in soundtrack:
        validate_free_audio_asset(a);finite(a.get('start_seconds',0),'sound start')
        gain=finite(a.get('gain',.1),'gain')
        if gain>1:raise ValueError('Soundtrack gain exceeds conservative maximum')
    output.mkdir(parents=True);clips=[]
    for i,(path,frames,kind,offset) in enumerate(validated):
        clip=output/f'shot-{i:04}.mp4'
        args=['-loop','1','-i',path] if kind=='image' else ['-i',path] if kind=='video' else None
        if args is None:raise ValueError('Shot must be image or video')
        if kind=='video' and measure_audio(path)+1/fps<(offset+frames)/fps:raise ValueError('Video is shorter than planned; do not freeze silently')
        def conform(destination):
            ff(args+['-vf',f'fps=24,trim=start_frame={offset}:end_frame={offset+frames},setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1','-frames:v',frames,'-an','-c:v','libx264','-pix_fmt','yuv420p',destination])
        if cache_dir is None:
            conform(clip)
        else:
            from .execution import signature
            from .workflow import StageStore
            cache=Path(cache_dir);cache.mkdir(parents=True,exist_ok=True)
            inputs={'sha256':digest(path),'frames':frames,'offset':offset,'kind':kind,'size':size,'encoder':'libx264-yuv420p-24fps-v2'}
            cached=cache/(signature(inputs)+'.mp4')
            def encode():
                conform(cached)
                return {'path':str(cached.resolve()),'artifacts':[{'path':str(cached.resolve()),'sha256':digest(cached)}]}
            with StageStore(cache/'conform.sqlite') as store:
                receipt=store.run('conform',inputs,encode)
            shutil.copyfile(receipt['path'],clip)
        clips.append(clip)
    mixed=output/'master.wav'
    if soundtrack:
        args=['-i',master];filters=['[0:a]aresample=48000,aformat=channel_layouts=stereo[a0]'];labels=['[a0]']
        for i,a in enumerate(soundtrack,1):
            args+=['-i',checked(a)];delay=round(a.get('start_seconds',0)*1000)
            filters.append(f'[{i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={a.get("gain",.1)},adelay={delay}:all=1[a{i}]');labels.append(f'[a{i}]')
        filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95,apad,atrim=duration={duration}[out]')
        ff(args+['-filter_complex',';'.join(filters),'-map','[out]','-c:a','pcm_s16le',mixed])
    else:ff(['-i',master,'-c:a','pcm_s16le',mixed])
    clean=output/'clean.mp4'
    if backend=='own':
        (output/'concat.txt').write_text(''.join("file '"+c.name+"'\n" for c in clips))
        ff(['-f','concat','-safe','1','-i',output/'concat.txt','-i',mixed,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-t',duration,clean])
    elif backend in ('h3_join','alec'):
        from .h3_wrapper import join_with_alec
        join_with_alec(clips,[f/fps for _,f,_,_ in validated],mixed,clean,size)
    else:raise ValueError('Unknown assembly backend')
    caption_file(cues,spec['names'],duration,output/'captions.ass')
    final=output/'captioned.mp4'
    # Use controlled cwd-relative filter path, never interpolate arbitrary file paths.
    subprocess.run(['ffmpeg','-v','error','-nostdin','-i','clean.mp4','-vf','ass=captions.ass','-map','0:v:0','-map','0:a:0','-c:v','libx264','-crf','18','-c:a','copy','captioned.mp4'],cwd=output,check=True,capture_output=True)
    info=media_info(final);video=next(x for x in info['streams'] if x['codec_type']=='video')
    if abs(float(info['format']['duration'])-duration)>.1 or video['width']!=w or video['height']!=h:raise ValueError('Assembly output duration/dimensions mismatch')
    result={'path':str(final.resolve()),'sha256':digest(final),'clean_path':str(clean.resolve()),'audio_sha256':digest(mixed),'backend':backend,
            'status':'assembled_preview_requires_full_playback_and_pixel_review','motion':'still-image animatic if image shots supplied; not generated acting',
            'duration':duration,'paid_requests':0}
    write_json(output/'assembly.json',result);return result


def assemble_season(spec,output,backend='own',resume=False):
    if resume:
        return _resumable_season(spec,output,backend)
    root=Path(output)
    if root.exists():raise ValueError('Fresh season output directory required')
    root.mkdir(parents=True)
    results=[]
    for ep in spec['episodes']:
        identifier(ep['id'],'episode id');results.append(assemble_episode(ep,root/ep['id'],backend))
    write_json(root/'results.json',results)
    canon=spec['canon']
    archive=root.parent/(root.name+'.zip')
    manifest=pack_season(root,archive,spec['series_id'],spec['season'],canon)
    return {'episodes':results,'archive':str(archive.resolve()),'archive_sha256':digest(archive),'status':'preview_season_archive_not_final_approved','paid_requests':0}


def _resumable_season(spec,output,backend):
    """Immutable versions, per-shot conformance cache, current-cut-only ZIP exports."""
    from .execution import signature
    from .workflow import StageStore
    root=Path(output);state=root.with_name(root.name+'-state')
    marker=state/'assembly-owner.json'
    owner={'output':str(root.resolve()),'series_id':spec['series_id'],'season':spec['season']}
    if marker.exists():
        if json.loads(marker.read_text(encoding='utf-8'))!=owner:raise ValueError('Assembly output belongs to another season')
    elif root.exists() and any(root.iterdir()):
        raise ValueError('Cannot resume an unrelated output directory')
    state.mkdir(parents=True,exist_ok=True);write_json(marker,owner)
    root.mkdir(parents=True,exist_ok=True)
    def fresh(parent):
        parent.mkdir(parents=True,exist_ok=True)
        n=1
        while (parent/str(n)).exists():n+=1
        return parent/str(n)
    results=[]
    with StageStore(state/'assembly.sqlite') as store:
        seen=set()
        for ep in spec['episodes']:
            eid=identifier(ep['id'],'episode id')
            if eid in seen:raise ValueError('Duplicate episode id')
            seen.add(eid)
            for asset in [ep['audio'],*ep['shots'],*ep.get('soundtrack',[])]:checked(asset)
            for asset in ep.get('soundtrack',[]):validate_free_audio_asset(asset)
            inputs={'episode':ep,'backend':backend,'assembly_version':2}
            def assemble(ep=ep,eid=eid,inputs=inputs):
                destination=fresh(state/'episodes'/eid/signature(inputs))
                result=assemble_episode(ep,destination,backend,cache_dir=state/'conformed')
                result['directory']=str(destination.resolve())
                result['artifacts']=[{'path':str(p.resolve()),'sha256':digest(p)} for p in sorted(destination.iterdir()) if p.is_file()]
                return result
            results.append(store.run('episode-'+eid,inputs,assemble))
        export_inputs={'episodes':results,'canon':spec['canon'],'owner':owner}
        def export():
            destination=fresh(root/('cut-'+signature(export_inputs)[:16]))
            destination.mkdir(parents=True)
            exported=[]
            for ep,result in zip(spec['episodes'],results):
                target=destination/ep['id'];shutil.copytree(result['directory'],target)
                current={**result,'path':str((target/'captioned.mp4').resolve()),'clean_path':str((target/'clean.mp4').resolve())}
                current.pop('artifacts',None);current.pop('directory',None)
                exported.append(current)
            write_json(destination/'results.json',exported)
            archive=destination.with_suffix('.zip')
            pack_season(destination,archive,spec['series_id'],spec['season'],spec['canon'])
            return {'episodes':exported,'archive':str(archive.resolve()),'archive_sha256':digest(archive),
                    'status':'preview_season_archive_not_final_approved','paid_requests':0,
                    'artifacts':[{'path':str(p.resolve()),'sha256':digest(p)} for p in sorted(destination.rglob('*')) if p.is_file()]+[{'path':str(archive.resolve()),'sha256':digest(archive)}]}
        result=store.run('export',export_inputs,export)
        return {**result,'stages':store.report()}
