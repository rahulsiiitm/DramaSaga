"""Private-use wrapper for Alec Li's unchanged local joiner, never H3 model execution."""
import json
import subprocess
from pathlib import Path
from .core import digest

ROOT=Path(__file__).resolve().parents[2]/'vendor'/'h3-film-reference'
JOIN_SHA256='68cb16b72374f33735f05ded789c68944920009f4bfbf6faa673dd0ef924832c'


def join_with_alec(clips,seconds,audio,output,size):
    module=ROOT/'agent'/'h3film'/'join.mjs'
    if digest(module)!=JOIN_SHA256:raise ValueError('Verbatim vendor module hash changed')
    # No vendor caption path: that path depends on upstream .venv/fonts not bundled.
    # Our own ASS caption pass is applied after join in assembly.py.
    payload={'clips':[{'file':str(Path(p).resolve()),'seconds':s} for p,s in zip(clips,seconds)],
             'music':str(Path(audio).resolve()),'out':str(Path(output).resolve()),'size':str(size[0])+'x'+str(size[1]),'captions':[]}
    script='import {readFileSync} from "node:fs"; const {joinFilm}=await import(process.argv[1]); await joinFilm(JSON.parse(readFileSync(0,"utf8")));'
    subprocess.run(['node','--input-type=module','-e',script,module.as_uri()],input=json.dumps(payload),text=True,check=True,capture_output=True)
    if not Path(output).is_file():raise ValueError('Vendor join did not produce output')


def render_h3(*args,**kwargs):
    raise RuntimeError('MiniMax H3 model execution blocked pending separate written model-license clearance and budget approval')
