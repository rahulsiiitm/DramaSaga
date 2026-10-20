"""Prepare hash-bound local inputs with audio padded to H3's frame grid."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from magicdrama.audiofirst.core import digest


def prepare(compiled,audio,references,pins,destination):
    out=Path(destination)
    if out.exists():raise ValueError('Fresh staging directory required')
    seconds=compiled['padded_audio_seconds']
    if not 0<seconds<=16:raise ValueError('Invalid padded clip duration')
    out.mkdir(parents=True);records=[]
    try:
        target=out/'dialogue.wav'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(audio),'-af',f'apad=whole_dur={seconds}',
            '-t',str(seconds),'-c:a','pcm_s16le',str(target)],check=True,capture_output=True)
        records.append({'name':target.name,'sha256':digest(target),'source_sha256':digest(audio)})
        names=set(['dialogue.wav'])
        for src in list(references)+list(pins):
            path=Path(src);name=path.name
            if not path.is_file() or path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):raise ValueError('Existing reference image required')
            if name in names:
                if not (out/name).is_file() or digest(out/name)!=digest(path):raise ValueError('Conflicting input basenames')
                continue
            from PIL import Image
            with Image.open(path) as im:im.verify()
            shutil.copyfile(path,out/name);names.add(name);records.append({'name':name,'sha256':digest(out/name)})
        result={'files':records,'audio_asset':'dialogue.wav','padded_seconds':seconds,'trim_seconds':compiled['trim_to_seconds'],
                'note':'Copy listed media into ComfyUI/input. Use these exact names in the clip.'}
        (out/'INPUT_MANIFEST.json').write_text(json.dumps(result,indent=2)+'\n');return result
    except Exception:
        shutil.rmtree(out);raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--compiled',required=True);p.add_argument('--audio',required=True);p.add_argument('--references',nargs='*',default=[]);p.add_argument('--pins',nargs='*',default=[]);p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(prepare(json.loads(Path(a.compiled).read_text()),a.audio,a.references,a.pins,a.out),indent=2))
if __name__=='__main__':main()
