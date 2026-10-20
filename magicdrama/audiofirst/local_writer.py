"""Optional existing local Ollama runtime. No key, cloud route or model download."""
import requests
from .writer import write_season

class LocalWriter:
    def __init__(self,model,http=None):
        if not isinstance(model,str) or not model.strip():raise ValueError('Explicit installed local model required')
        self.model=model;self.http=http or requests.Session()
    def available(self):
        r=self.http.get('http://127.0.0.1:11434/api/tags',timeout=5);r.raise_for_status()
        return self.model in [m['name'] for m in r.json().get('models',[])]
    def __call__(self,request):
        if not self.available():raise RuntimeError('Requested local model is not installed; no auto-download or paid fallback')
        def transport(body):
            r=self.http.post('http://127.0.0.1:11434/api/chat',json={'model':self.model,'messages':body['messages'],'format':'json','stream':False},timeout=600)
            r.raise_for_status();return r.json()['message']['content']
        previous={'series_id':request['brief']['series_id'],'season':request['brief']['season']-1,'canon':request['previous_canon']} if request['previous_canon'] else None
        return write_season(request['brief'],transport,self.model,previous,enabled=True,approval_reference='local-runtime-explicit-request-no-cloud')
