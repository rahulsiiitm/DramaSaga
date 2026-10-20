import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from models import model_root


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['describe','track']);p.add_argument('--image');p.add_argument('--video');p.add_argument('--audio');p.add_argument('--speaker');p.add_argument('--device',choices=['cpu','cuda'],default='cpu');p.add_argument('--out',required=True);a=p.parse_args()
    dest=Path(a.out)
    if dest.exists():raise ValueError('Fresh output path required')
    if a.command=='describe':
        from magicdrama.audiofirst.transformers_vision import TransformersVision
        result=TransformersVision(model_root()/'vision',a.device).describe(a.image)
    else:
        from magicdrama.audiofirst.mouth_tracker import track_mouth
        result=track_mouth(a.video,a.audio,model_root()/'face_landmarker.task',a.speaker)
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
