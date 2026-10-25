"""Optional existing local Ollama runtime. No key, cloud route or model download."""
import requests
from .writer import write_season

class LocalWriter:
    def __init__(self,model,http=None,workspace=None,max_repairs=1):
        if not isinstance(model,str) or not model.strip():raise ValueError('Explicit installed local model required')
        self.model=model;self.http=http or requests.Session()
        self.workspace=workspace;self.max_repairs=max_repairs
    def available(self):
        r=self.http.get('http://127.0.0.1:11434/api/tags',timeout=5);r.raise_for_status()
        return self.model in [m['name'] for m in r.json().get('models',[])]
    def __call__(self,request):
        def transport(body):
            from .workflow import SubmissionNotStarted
            try:
                if not self.available():raise SubmissionNotStarted('Requested local model is not installed; no auto-download or paid fallback')
            except requests.RequestException as error:
                raise SubmissionNotStarted('Local Ollama runtime unavailable; no inference submitted') from error
            r=self.http.post('http://127.0.0.1:11434/api/chat',json={'model':self.model,'messages':body['messages'],'format':'json','stream':False},timeout=600)
            r.raise_for_status();return r.json()['message']['content']
        if self.workspace is not None:
            from .director import StoryDirector
            result=StoryDirector(transport,self.model,self.workspace,self.max_repairs)(request)
            result['writer_execution']={'provider':'local_ollama','paid_requests':0}
            return result
        previous={'series_id':request['brief']['series_id'],'season':request['brief']['season']-1,'canon':request['previous_canon']} if request['previous_canon'] else None
        result=write_season(request['brief'],transport,self.model,previous,enabled=True,approval_reference='local-runtime-explicit-request-no-cloud')
        result['writer_execution']={'provider':'local_ollama','paid_requests':0}
        return result
