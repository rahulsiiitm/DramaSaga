"""Media-producing local/injected-provider runner with staged exact approvals."""
import json
from pathlib import Path
from .assembly import assemble_season,checked
from .core import write_json,digest
from .execution import signature,verify_approval,RunLedger
from .live import LiveAdapters


def media_run(package,output,approval=None,keys=None,enabled=False,http=None,backend='own',ledger_path=None,transcriber=None,evaluators=None):
    """Package has exact live manifest (optional) and accepted media season spec.

    Generated outputs can replace declared {job_id, sha256} asset pointers only once
    actual hashes match. Changed refs/timings/quotes require a new approved manifest.
    This deliberately does not invent timing or fabricate pixel-review receipts.
    """
    output=Path(output)
    state_dir=output.with_name(output.name+'-state');state_dir.mkdir(parents=True,exist_ok=True)
    results={}
    manifest=package.get('manifest')
    if manifest:
        if ledger_path is None:raise ValueError('Explicit shared batch ledger path required for live jobs')
        ledger=RunLedger(ledger_path)
        try:
            adapter=LiveAdapters(manifest,approval or {},ledger,keys or {},enabled,http)
            for job in manifest['jobs']:
                suffix='.png' if job['kind']=='image' else '.mp3' if job['kind']=='voice' else '.mp4'
                results[job['id']]=adapter.execute(job['id'],state_dir/(job['id']+suffix))
        finally:ledger.close()
    def resolve(value):
        if isinstance(value,dict):
            if 'job_id' in value:
                result=results.get(value['job_id'])
                if not result:raise ValueError('Unresolved generated media job')
                if value.get('sha256')!=result['sha256'] and package.get('automatic_acceptance') is not True:
                    raise ValueError('Generated result not yet accepted; inspect and bind actual bytes before assembly')
                return {**value,'path':result['path'],'sha256':result['sha256']}
            return {k:resolve(v) for k,v in value.items()}
        if isinstance(value,list):return [resolve(v) for v in value]
        return value
    spec=resolve(package['season'])
    if package.get('automatic_acceptance') is True:
        from .acceptance import prepare_episode
        spec['episodes']=[prepare_episode(ep,state_dir/('qa-'+ep['id']),transcriber,evaluators) for ep in spec['episodes']]
    result=assemble_season(spec,output,backend)
    write_json(state_dir/'completed.json',result)
    return result
