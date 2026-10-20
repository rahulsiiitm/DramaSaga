"""Cheap real CPU tests using official test fixtures. No paid calls."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from models import model_root


def main():
    import requests
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();root=Path(a.out);root.mkdir(parents=True,exist_ok=False)
    sources={'jfk.flac':'https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac',
             'business-person.png':'https://storage.googleapis.com/mediapipe-assets/business-person.png'}
    for name,url in sources.items():
        r=requests.get(url,timeout=60);r.raise_for_status();(root/name).write_bytes(r.content)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(root/'jfk.flac'),'-ar','16000','-ac','1','-c:a','pcm_s16le',str(root/'jfk.wav')],check=True)
    from magicdrama.audiofirst.alignment import LocalWhisper,tokens,recover_alignment
    t=time.monotonic();m=LocalWhisper(model_root()/'asr');words=m(root/'jfk.wav')
    expected='And so my fellow Americans ask not what your country can do for you ask what you can do for your country'
    aa=tokens(expected);bb=[w for x in words for w in tokens(x['word'])];d=list(range(len(bb)+1))
    for i,x in enumerate(aa,1):
        n=[i]
        for j,y in enumerate(bb,1):n.append(min(n[-1]+1,d[j]+1,d[j-1]+(x!=y)))
        d=n
    result={'asr':{'wall_seconds':time.monotonic()-t,'expected_words':len(aa),'actual_words':words,'word_errors':d[-1],'wer':d[-1]/len(aa)}}
    try:result['asr']['alignment']=recover_alignment(root/'jfk.wav',[{'id':'fixture','speaker':'jfk','text':expected}],m)
    except ValueError as e:result['asr']['alignment_rejected']=str(e)
    del m
    from magicdrama.audiofirst.transformers_vision import TransformersVision
    t=time.monotonic();v=TransformersVision(model_root()/'vision');result['vision']=v.describe(root/'business-person.png');result['vision']['wall_seconds']=time.monotonic()-t;del v
    subprocess.run(['ffmpeg','-v','error','-nostdin','-loop','1','-i',str(root/'business-person.png'),'-t','2','-r','25','-vf','scale=512:-2','-pix_fmt','yuv420p',str(root/'face-static.mp4')],check=True)
    from magicdrama.audiofirst.mouth_tracker import track_mouth
    t=time.monotonic()
    try:
        track=track_mouth(root/'face-static.mp4',root/'jfk.wav',model_root()/'face_landmarker.task','fixture_unverified')
        result['tracking']={'samples':len(track['samples']),'status':track['status'],'identity_verified':False}
    except ValueError as e:result['tracking']={'rejected':str(e)}
    result['tracking'].update(wall_seconds=time.monotonic()-t,note='Static repeated portrait, not moving-mouth or sync ground truth.')
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    with vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(model_root()/'face_landmarker.task')),num_faces=2)) as detector:
        face=detector.detect(mp.Image.create_from_file(str(root/'business-person.png')))
        result['face_detection']={'faces':len(face.face_landmarks),'landmarks_per_face':[len(x) for x in face.face_landmarks],'threshold':.5,'identity_verified':False}
    result['sources']=[{'url':u,'sha256':hashlib.sha256((root/n).read_bytes()).hexdigest()} for n,u in sources.items()]
    result['limits']='Single public speech and static portrait smoke tests, not accuracy benchmarks. H3 inference and semantic acceptance unverified.'
    (root/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
