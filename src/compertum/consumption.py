"""Synthetic M0 access guard. No holdout reader exists."""
import json
from .domain import atomic_json,digest,now,ContractError,validate_record
from .persistence import open_store

def create_guard(lease):
    lease.verify()
    if lease.role!='evaluation':raise ContractError('WRONG_GUARD_OWNER')
    directory=lease.project.root_path/'state/evaluation-consumption'
    directory.mkdir(exist_ok=True)
    if any(directory.iterdir()):raise ContractError('GUARD_ALREADY_EXISTS_OR_UNCERTAIN')
    atomic_json(directory/'head.json',{'project_id':lease.project.project_id,'sequence':0,'sha256':'0'*64})

def verify_consumption_guard(project):
    directory=project.root_path/'state/evaluation-consumption'
    try:
        head=json.loads((directory/'head.json').read_text());files=sorted(directory.glob('event-*.json'))
        if head['project_id']!=project.project_id or head['sequence']!=len(files):raise ValueError()
        previous='0'*64;consumed={}
        for n,path in enumerate(files,1):
            event=json.loads(path.read_text());validate_record('consumption_event',event)
            h=event.pop('sha256')
            if event['sequence']!=n or event['previous_hash']!=previous or digest(event)!=h or event['seal_id'] in consumed:raise ValueError()
            previous=h;consumed[event['seal_id']]=event['evaluation_id']
        if previous!=head['sha256']:raise ValueError()
        return {'verified':True,'head':head,'consumed':consumed,'reason':'COMPLETE_CHAIN'}
    except (OSError,ValueError,KeyError):return {'verified':False,'head':{},'consumed':{},'reason':'CONSUMPTION_STATUS_UNVERIFIED'}

def consume_once(lease,seal_id,evaluation_id,inputs):
    lease.verify()
    if lease.role!='evaluation' or not seal_id.startswith('synthetic-'):raise ContractError('M0_ONLY_SYNTHETIC_GUARD')
    evidence=verify_consumption_guard(lease.project)
    if not evidence['verified']:raise ContractError('EVALUATION_COMPROMISED')
    if seal_id in evidence['consumed']:raise ContractError('ALREADY_CONSUMED')
    store=open_store(lease,'evaluation')
    try:
        old=store.db.execute('SELECT status FROM seals WHERE seal_id=?',(seal_id,)).fetchone()
        if old and old[0]!='UNUSED':raise ContractError('EVALUATION_COMPROMISED')
    finally:store.close()
    sequence=evidence['head']['sequence']+1
    event={'schema_version':1,'seal_id':seal_id,'evaluation_id':evaluation_id,'sequence':sequence,'previous_hash':evidence['head']['sha256'],'inputs_hash':digest(inputs),'at':now()}
    event['sha256']=digest(event)
    directory=lease.project.root_path/'state/evaluation-consumption'
    target=directory/('event-'+str(sequence).zfill(12)+'.json')
    if target.exists():raise ContractError('GUARD_SEQUENCE_COLLISION')
    atomic_json(target,event)
    atomic_json(directory/'head.json',{'project_id':lease.project.project_id,'sequence':sequence,'sha256':event['sha256']})
    store=open_store(lease,'evaluation')
    try:
        with store.transaction():store.db.execute('INSERT OR REPLACE INTO seals VALUES(?,?,?)',(seal_id,'CONSUMED',evaluation_id))
    finally:store.close()
    return event
