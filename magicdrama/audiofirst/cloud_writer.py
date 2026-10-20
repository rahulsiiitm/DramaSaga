"""NVIDIA first, Claude only on 60s no-output stall. Explicit approval, default off."""
import datetime as dt
import json
import time
from decimal import Decimal
import requests
from .execution import signature,money
from .budget import SpendLedger
from .writer import write_season

NVIDIA_MODEL='nvidia/nemotron-3-super-120b-a12b'
CLAUDE_MODEL='claude-sonnet-5'

class NoOutputStall(TimeoutError):pass


class NvidiaClaudeWriter:
    def __init__(self,config,approval,keys,ledger_path,enabled=False,http=None,clock=time.monotonic):
        self.config=config;self.approval=approval;self.keys=keys;self.ledger_path=ledger_path
        self.enabled=enabled;self.http=http or requests.Session();self.clock=clock
    def approve(self,body):
        if self.enabled is not True:raise RuntimeError('Cloud writer disabled by default')
        a=self.approval;c=self.config
        expiry=dt.datetime.fromisoformat(a.get('expires_at','').replace('Z','+00:00'))
        now=dt.datetime.now(dt.timezone.utc)
        if expiry.tzinfo is None or not now<expiry<=now+dt.timedelta(days=1):raise ValueError('Writer approval expired or invalid')
        if a.get('request_sha256')!=signature({'body':body,'config':c}) or not a.get('approval_reference'):
            raise ValueError('Exact writing request/model/token/rate approval required')
        if c.get('nvidia_model')!=NVIDIA_MODEL or c.get('claude_model')!=CLAUDE_MODEL:
            raise ValueError('Explicit verified writer models required; no silent substitution')
        if type(c.get('max_output_tokens')) is not int or not 1<=c['max_output_tokens']<=32000:raise ValueError('Explicit output-token limit required')
        if money(c.get('claude_run_cap_usd',0))<=0 or money(c['claude_run_cap_usd'])>Decimal('2.30'):raise ValueError('Claude run cap may not exceed $2.30')
        if a.get('key_identities')!={'nvidia':'Saralya NVIDIA API key','claude':'Anthropic API key'}:raise ValueError('Wrong writer key identities')
    def nvidia(self,body):
        if not self.keys.get('nvidia'):raise ValueError('NVIDIA key missing')
        start=self.clock();parts=[];r=None
        try:
            r=self.http.post('https://integrate.api.nvidia.com/v1/chat/completions',
                headers={'Authorization':'Bearer '+self.keys['nvidia']},json={**body,'model':NVIDIA_MODEL,'stream':True,
                    'max_tokens':self.config['max_output_tokens'],'chat_template_kwargs':{'enable_thinking':False}},
                timeout=(15,60),stream=True,allow_redirects=False)
            r.raise_for_status()
            if r.status_code!=200:raise RuntimeError('Unexpected NVIDIA status; no fallback for HTTP errors')
            for line in r.iter_lines(decode_unicode=True,chunk_size=1):
                if not parts and self.clock()-start>=60:raise NoOutputStall('NVIDIA no-visible-output stall at 60 seconds')
                if parts and self.clock()-start>600:raise TimeoutError('NVIDIA wall limit after partial output; no paid fallback')
                if not line or not line.startswith('data:'):continue
                text=line[5:].strip()
                if text=='[DONE]':break
                data=json.loads(text)
                if data.get('error'):raise RuntimeError('NVIDIA stream error; no paid fallback')
                choices=data.get('choices',[])
                if choices:
                    delta=choices[0].get('delta',{}).get('content')
                    if delta:parts.append(delta)
                    if choices[0].get('finish_reason')=='length':raise ValueError('NVIDIA output truncated; no fallback')
            if not parts:raise ValueError('NVIDIA empty completion before stall; no fallback')
            return ''.join(parts)
        except requests.exceptions.Timeout as e:
            if not parts and self.clock()-start>=60:raise NoOutputStall('NVIDIA no-output timeout') from e
            raise
        finally:
            if r is not None:r.close()
    def claude(self,body):
        c=self.config;a=self.approval
        if a.get('allow_claude_fallback') is not True:raise RuntimeError('Claude fallback not approved')
        today=dt.datetime.now(dt.timezone(dt.timedelta(hours=5,minutes=30))).date().isoformat()
        if c.get('rates_verified_on')!=today or c.get('pricing_url')!='https://platform.claude.com/docs/en/about-claude/pricing':raise ValueError('Claude current official rate verification required')
        # Pinned verified Sonnet 5 base rates; no caching, tools, batch or extended premium features.
        if money(c.get('input_usd_per_million'))!=2 or money(c.get('output_usd_per_million'))!=10:raise ValueError('Recheck changed Claude rates before proceeding')
        if not self.keys.get('claude'):raise ValueError('Claude key missing; do not use another provider key')
        headers={'x-api-key':self.keys['claude'],'anthropic-version':'2023-06-01'}
        system='\n'.join(m['content'] for m in body['messages'] if m['role']=='system')
        messages=[m for m in body['messages'] if m['role']!='system']
        payload={'model':CLAUDE_MODEL,'system':system,'messages':messages}
        # Read-only token counting, not a guessed char/token conversion.
        r=self.http.post('https://api.anthropic.com/v1/messages/count_tokens',headers=headers,json=payload,timeout=30,allow_redirects=False)
        r.raise_for_status()
        if r.status_code!=200:raise RuntimeError('Token count unavailable; cannot bound paid request')
        count=r.json()['input_tokens']
        if type(count) is not int or count<1:raise ValueError('Invalid input token count')
        maximum=Decimal(count)*Decimal('2')/1000000+Decimal(c['max_output_tokens'])*Decimal('10')/1000000
        if maximum>money(c['claude_run_cap_usd']):raise ValueError('Worst-case Claude request exceeds run cap')
        ledger=SpendLedger(self.ledger_path);key=a['run_id']+'-claude-writer'
        try:
            ledger.reserve(key,'claude','USD',payload,{'amount':str(maximum),'unit':'USD','verified_at':dt.date.today().isoformat()},
                {'cap':c['claude_run_cap_usd'],'unit':'USD','provider':'claude','valid_on':dt.date.today().isoformat(),'approval_reference':a['approval_reference']})
            ledger.mark_submitting(key)
            try:
                r=self.http.post('https://api.anthropic.com/v1/messages',headers=headers,json={**payload,'max_tokens':c['max_output_tokens']},timeout=(15,180),allow_redirects=False)
                r.raise_for_status()
                if r.status_code!=200:raise RuntimeError('Unexpected Claude status')
                data=r.json()
            except Exception:ledger.unknown(key);raise
            ledger.submitted(key,data['id'])
            usage=data['usage'];actual=(Decimal(usage['input_tokens'])*2+Decimal(usage['output_tokens'])*10)/1000000
            ledger.complete(key,actual)
            if actual>maximum:raise RuntimeError('Provider exceeded worst-case quote; stop and reconcile')
            if data.get('stop_reason')=='max_tokens':raise ValueError('Claude output truncated, no retry')
            return ''.join(x['text'] for x in data['content'] if x['type']=='text')
        finally:ledger.close()
    def transport(self,body):
        self.approve(body)
        try:return self.nvidia(body)
        except NoOutputStall:
            self.approve(body)  # expiry/payload check again before paid fallback
            return self.claude(body)
    def __call__(self,request):
        previous={'series_id':request['brief']['series_id'],'season':request['brief']['season']-1,'canon':request['previous_canon']} if request['previous_canon'] else None
        return write_season(request['brief'],self.transport,NVIDIA_MODEL,previous,enabled=self.enabled,
                            approval_reference=self.approval.get('approval_reference'))
