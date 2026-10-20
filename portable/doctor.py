import importlib.metadata,json,os,platform,shutil,sys
from pathlib import Path
if __name__=='__main__':
    modules=['faster-whisper','mediapipe','transformers','huggingface-hub','torch','torchvision','Pillow','requests']
    packages={}
    for name in modules:
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    try:
        import torch
        gpu={'cuda':torch.cuda.is_available(),'name':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
    except ImportError:gpu={'cuda':False}
    result={'python':sys.version,'os':platform.system(),'ffmpeg':shutil.which('ffmpeg'),'ffprobe':shutil.which('ffprobe'),
            'packages':packages,'gpu':gpu,'models':str(Path(os.environ.get('MICRODRAMA_MODELS','models')).resolve()),
            'live_paid_calls_enabled':False}
    print(json.dumps(result,indent=2));sys.exit(0 if all(packages.values()) and result['ffmpeg'] and result['ffprobe'] else 1)
