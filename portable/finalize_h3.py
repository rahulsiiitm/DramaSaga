"""Trim verified local H3 output and replace its audio with the exact source."""
import argparse,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from magicdrama.audiofirst.core import digest


def finalize(video,audio,seconds,out):
    dest=Path(out)
    if dest.exists() or not 0<float(seconds)<=15:raise ValueError('Fresh output and valid trim duration required')
    dest.parent.mkdir(parents=True,exist_ok=True)
    try:
        subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(video),'-i',str(audio),'-map','0:v:0','-map','1:a:0',
            '-t',str(seconds),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k',str(dest)],check=True,capture_output=True)
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(dest)],text=True))
        if abs(float(info['format']['duration'])-float(seconds))>.1:raise ValueError('Final duration mismatch')
        if not {'audio','video'}<=set(s['codec_type'] for s in info['streams']):raise ValueError('Missing mux streams')
        return {'path':str(dest),'sha256':digest(dest),'source_video_sha256':digest(video),'source_audio_sha256':digest(audio),
            'status':'muxed_not_quality_accepted','audio_note':'Source audio encoded AAC, not byte-identical PCM; verify actual audio again'}
    except Exception:
        dest.unlink(missing_ok=True);raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--video',required=True);p.add_argument('--audio',required=True);p.add_argument('--seconds',type=float,required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(finalize(a.video,a.audio,a.seconds,a.out),indent=2))
if __name__=='__main__':main()
