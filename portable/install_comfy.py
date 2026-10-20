"""Explicit pinned official ComfyUI install, no server start or rental."""
import argparse,json,subprocess,sys
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--destination',required=True);a=p.parse_args();dest=Path(a.destination)
    if dest.exists():raise ValueError('Fresh destination required')
    lock=json.loads(Path(__file__).with_name('sources.lock.json').read_text())
    subprocess.run(['git','clone','--no-checkout',lock['comfy_repo'],str(dest)],check=True)
    subprocess.run(['git','-C',str(dest),'checkout','--detach',lock['comfy_commit']],check=True)
    subprocess.run([sys.executable,'-m','pip','install','-r',str(dest/'requirements.txt'),'--index-url','https://pypi.org/simple'],check=True)
    print('Installed pinned ComfyUI. Start manually: python '+str(dest/'main.py')+' --listen 127.0.0.1 --port 8188')
if __name__=='__main__':main()
