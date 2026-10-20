"""Live-capable provider HTTP adapters. No call without explicit manifest approval.

Never import legacy retry clients. Inputs/outputs are scoped to approved manifest.
"""
import base64
import json
import time
from pathlib import Path
from urllib.parse import urlparse
import requests
from .core import digest
from .execution import signature,verify_approval,RunLedger,money

MH='https://api.magichour.ai'
EL='https://api.elevenlabs.io'
CREATE={'image':{'/v1/ai-image-generator','/v1/ai-image-editor'},'video':{'/v1/audio-to-video','/v1/lip-sync','/v1/image-to-video'}}


def validate_job(job):
    req=job['request'];endpoint=req['endpoint'];body=req['body']
    if job['provider']=='magichour':
        if endpoint not in CREATE.get(job['kind'],set()):raise ValueError('Unapproved endpoint')
        if job['kind']=='image':
            if body.get('model')!='nano-banana-2.1' or body.get('resolution')!='1k' or body.get('image_count')!=1 or money(job['quote']['amount'])!=50:
                raise ValueError('Only quoted single-image 1k Nano Banana 2.1 supported')
        if job['kind']=='video':
            from .images import require_rendered_images
            evidence=job.get('image_evidence',{})
            if not evidence.get('plan',{}).get('tasks'):raise ValueError('Video reference plan cannot be empty')
            require_rendered_images(evidence['plan'],evidence.get('accepted',{}))
    elif job['provider']=='elevenlabs':
        if endpoint!='/v1/text-to-dialogue/with-timestamps' or body.get('model_id')!='eleven_v3':raise ValueError('Unapproved voice route/model')
        if any(not i.get('voice_id') for i in body['inputs']):raise ValueError('Every voice must be selected')
    else:raise ValueError('Unknown provider')


def download_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in ('videos.magichour.ai','storage.googleapis.com') or p.username or p.password:
        raise ValueError('Unverified provider asset host; pause, do not disclose/fetch arbitrary URL')
    return url


class LiveAdapters:
    def __init__(self,manifest,token,ledger,keys,enabled=False,http=None,sleep=time.sleep):
        verify_approval(manifest,token,enabled)
        for j in manifest['jobs']:validate_job(j)
        self.manifest=manifest;self.token=token;self.ledger=ledger;self.keys=keys
        self.http=http or requests.Session();self.sleep=sleep;self.enabled=enabled
        ledger.reserve(manifest,token,enabled)
    def headers(self,provider):
        key=self.keys.get(provider)
        if not key:raise ValueError('Approved provider key not supplied')
        return {'Authorization':'Bearer '+key} if provider=='magichour' else {'xi-api-key':key}
    def upload(self,path,kind):
        # Input content hash must have been explicitly authorized as part of this run.
        verify_approval(self.manifest,self.token,self.enabled)
        path=Path(path);allowed=self.manifest.get('uploads',[])
        if {'sha256':digest(path),'kind':kind} not in allowed:raise ValueError('Upload bytes/audience not approved')
        response=self.http.post(MH+'/v1/files/upload-urls',headers=self.headers('magichour'),json={'items':[{'type':kind,'extension':path.suffix.lstrip('.')}]},timeout=60,allow_redirects=False)
        response.raise_for_status()
        if response.status_code!=200:raise ValueError('Unexpected upload-url response')
        data=response.json();item=(data['items'] if isinstance(data,dict) else data)[0]
        url=download_url(item['upload_url'])
        if not item['file_path'].startswith('api-assets/'):raise ValueError('Unexpected provider upload path')
        with path.open('rb') as f:
            response=self.http.put(url,data=f,timeout=120,allow_redirects=False);response.raise_for_status()
        return item['file_path']
    def execute(self,job_id,output,polls=60):
        verify_approval(self.manifest,self.token,self.enabled)
        if self.ledger.halt_overcharge(self.manifest['batch_id']):raise RuntimeError('Prior provider overcharge: stop and reconcile')
        job=next(j for j in self.manifest['jobs'] if j['id']==job_id);validate_job(job)
        run=self.manifest['run_id'];row=self.ledger.get(run,job_id)
        if row['state']=='complete':
            result=json.loads(row['result']);p=Path(result['path'])
            if not p.is_file() or digest(p)!=result['sha256']:raise ValueError('Completed asset missing/changed; never regenerate automatically')
            return result
        if row['state'] in ('submitting','unknown','overcharge','error'):raise RuntimeError('Uncertain/failed job: reconcile, never auto-resubmit')
        if row['state']=='reserved':
            headers=self.headers(job['provider'])
            self.ledger.transition(run,job_id,'reserved','submitting')
            try:
                base=MH if job['provider']=='magichour' else EL
                r=self.http.post(base+job['request']['endpoint'],headers=headers,json=job['request']['body'],timeout=180,allow_redirects=False)
                r.raise_for_status()
                if r.status_code!=200:raise ValueError('Unexpected provider status or redirect')
                data=r.json()
            except Exception:
                self.ledger.transition(run,job_id,'submitting','unknown');raise
            # Save raw provider response before any decoding/download; voice may have no project ID.
            self.ledger.transition(run,job_id,'submitting','submitted',data)
            row=self.ledger.get(run,job_id)
        data=json.loads(row['result'])
        if job['provider']=='magichour':
            ident=data.get('id')
            if not isinstance(ident,str) or not ident.isalnum():raise ValueError('Unexpected provider ID')
            details='/v1/image-projects/' if job['kind']=='image' else '/v1/video-projects/'
            for n in range(polls):
                r=self.http.get(MH+details+ident,headers=self.headers('magichour'),timeout=60,allow_redirects=False);r.raise_for_status();data=r.json()
                if data.get('status') in ('complete','error','canceled'):break
                self.sleep(10)
            else:raise TimeoutError('Render pending; resume same run, do not submit again')
            actual=money(data['credits_charged'])
            if actual>money(job['quote']['amount']):
                self.ledger.transition(run,job_id,'submitted','overcharge',data,actual);raise RuntimeError('Provider charged above quote; stop batch')
            if data['status']!='complete':
                self.ledger.transition(run,job_id,'submitted','error',data,actual);raise RuntimeError('Provider failed or canceled; reconcile before replacement')
            downloads=data.get('downloads',[])
            if len(downloads)!=1:raise ValueError('Expected exactly one result')
            r=self.http.get(download_url(downloads[0]['url']),timeout=120,allow_redirects=False);r.raise_for_status()
            if r.status_code!=200:raise ValueError('Asset redirect or unexpected status refused')
            raw=r.content
        else:
            raw=base64.b64decode(data['audio_base64'],validate=True)
            actual=money(job['quote']['amount'])  # submitted text count, NOT a billed-credit claim
        output=Path(output)
        if output.exists():raise ValueError('Output already exists; recover submitted result explicitly')
        output.parent.mkdir(parents=True,exist_ok=True);tmp=output.with_suffix(output.suffix+'.pending');tmp.write_bytes(raw);tmp.replace(output)
        result={'path':str(output.resolve()),'sha256':digest(output),'provider_result':data,'quoted_unit':job['quote']['unit'],
                'actual_measure':str(actual),'note':'Voice measure is submitted characters, not verified billing'}
        self.ledger.transition(run,job_id,'submitted','complete',result,actual)
        return result
