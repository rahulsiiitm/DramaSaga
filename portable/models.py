"""Explicit official-source installs. Never downloads on import or inference."""
import argparse,hashlib,json,os,shutil,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOCK=Path(__file__).with_name('sources.lock.json')


def model_root():return Path(os.environ.get('MICRODRAMA_MODELS',str(ROOT/'models'))).resolve()


def download(kind):
    import requests
    lock=json.loads(LOCK.read_text());root=model_root();root.mkdir(parents=True,exist_ok=True)
    if kind=='face':
        spec=lock['face'];target=root/'face_landmarker.task';r=requests.get(spec['url'],timeout=120);r.raise_for_status()
        if hashlib.sha256(r.content).hexdigest()!=spec['sha256']:raise ValueError('Official face model hash changed')
        target.write_bytes(r.content);return {'path':str(target),'source':spec}
    from huggingface_hub import HfApi,snapshot_download
    spec=lock['models'][kind];api=HfApi(token=False)
    info=api.model_info(spec['repo'],revision=spec['revision'],files_metadata=True)
    if info.gated:raise RuntimeError('Gated agreement/login requires owner action; not accepted automatically')
    import fnmatch
    files=[f for f in info.siblings if any(fnmatch.fnmatch(f.rfilename,p) for p in spec['allow_patterns'])]
    if not files:raise ValueError('No matching official files')
    size=sum(f.size or 0 for f in files)
    if shutil.disk_usage(root).free<size+2*1024**3:raise RuntimeError(f'Need {size/1024**3:.1f} GiB models plus 2 GiB headroom')
    target=root/kind
    snapshot_download(spec['repo'],revision=spec['revision'],allow_patterns=spec['allow_patterns'],local_dir=target,token=False)
    records=[]
    for f in files:
        path=target/f.rfilename
        if not path.is_file():raise ValueError('Incomplete model download')
        h=hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda:source.read(1024**2),b''):h.update(block)
        expected=getattr(f.lfs,'sha256',None) if f.lfs else None
        if expected and expected!=h.hexdigest():raise ValueError('Publisher LFS hash mismatch')
        records.append({'path':f.rfilename,'sha256':h.hexdigest(),'bytes':path.stat().st_size})
    result={'source':spec,'files':records};(target/'DOWNLOAD_LEDGER.json').write_text(json.dumps(result,indent=2)+'\n');return {'path':str(target),'bytes':size,'ledger':str(target/'DOWNLOAD_LEDGER.json')}


def main():
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['asr','vision','face','h3']);args=p.parse_args()
    print(json.dumps(download(args.kind),indent=2))
if __name__=='__main__':main()
