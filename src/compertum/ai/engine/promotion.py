"""Promotion of audited code to a versioned trusted template, and the Validator's vault run (section 19). Stage E6.

Code leaves the sandbox only after the automated tests and the Auditor pass. The promoted files are the code exactly as the
agent submitted it (the launch record), written to `state/engine/promoted/<candidate>/` with a manifest of hashes; the job
folder stays as quarantine evidence. The vault run reruns the frozen code on the vault tier inside a sealed look and then
deletes the data tier files from that job folder; the Engineer never sees the vault rows.
"""
from datetime import datetime,timezone
import hashlib
from pathlib import Path
import re
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from .execution import remove_data_tiers
from .market import market_csv

PROMOTED_DIR='state/engine/promoted'
_SAFE=re.compile(r'[^A-Za-z0-9_.-]')


def promoted_folder(project_root,candidate_id):
    if not isinstance(candidate_id,str) or not 1<=len(candidate_id)<=128: raise RuntimeRefused('ENGINE_PROMOTION_DENIED')
    return Path(project_root).absolute()/PROMOTED_DIR/_SAFE.sub('_',candidate_id)


def promote(project_root,candidate_id,files,*,audit,score,deflation,source_job_folder):
    """Write the submitted files of an audited candidate into a new template folder with a manifest. One promotion per candidate."""
    if not isinstance(audit,dict) or audit.get('label')!='VERIFIED_PASS': raise RuntimeRefused('ENGINE_PROMOTION_DENIED')
    if not isinstance(files,dict) or not files or any(not isinstance(k,str) or not isinstance(v,str) or k.startswith('/') or '..' in k for k,v in files.items()):
        raise RuntimeRefused('ENGINE_PROMOTION_DENIED')
    folder=promoted_folder(project_root,candidate_id)
    try: folder.mkdir(parents=True)
    except FileExistsError: raise RuntimeRefused('ENGINE_PROMOTION_DUPLICATE') from None
    hashes={}
    for relative,text in files.items():
        target=folder/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text,encoding='utf-8',newline='\n');hashes[relative]=hashlib.sha256(text.encode('utf-8')).hexdigest()
    manifest={'version':1,'candidate_id':candidate_id,'promoted_at':datetime.now(timezone.utc).isoformat(),'source_job_folder':str(source_job_folder),
              'files':hashes,'audit':audit,'score_sha256':hashlib.sha256(canonical(score)).hexdigest(),'deflation':deflation}
    (folder/'manifest.json').write_bytes(canonical(manifest)+b'\n')
    return {'folder':str(folder),'manifest':manifest}


def vault_run(queue,sandbox,look_id,candidate_id,*,files,entry,vault_rows):
    """The Validator's vault evaluation: inside the sealed look, rerun the frozen code with the vault as validation.csv and score it.

    The queue checks the look and the candidate's state before `produce` runs, so nothing reads the vault on a repeat or
    outside a look. The rerun is a sandbox job with purpose 'vault'; the Engineer agent is not involved. After the rerun
    the data tier files are deleted from the vault job folder.
    """
    def produce():
        record=sandbox.rerun_frozen(files,entry,purpose='vault',validation_csv=market_csv(vault_rows))
        if record.get('job_folder'): remove_data_tiers(record['job_folder'])
        if record['status']!='COMPLETED' or record.get('signals') is None: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
        return record['signals'],vault_rows
    return queue.evaluate_in_vault(look_id,candidate_id,None,produce)
