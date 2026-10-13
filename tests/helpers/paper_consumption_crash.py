"""Native process termination at shared-journal persistence boundaries."""
import json,os,sys
from pathlib import Path
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.storage import create_journal_reserve
from compertum.runtime.errors import RuntimeRefused
from paper_consumption_support import records,inspect,AT,args
root=Path(sys.argv[1]).resolve();point=sys.argv[2];project=resolve_project(root)
if point=='block':
    import time
    lease=acquire_owner(project,'execution');open_store(lease,'execution')
    (root/'blocked-ready.json').write_text(json.dumps(dict(pid=os.getpid())))
    while True:time.sleep(1)
if point=='inspect':
    try:result=inspect(root,project)
    except RuntimeRefused as error:result=dict(status=error.code)
    import compertum
    result['package_origin']=str(Path(compertum.__file__).resolve());print(json.dumps(result));raise SystemExit(0)
lease=acquire_owner(project,'execution');store=open_store(lease,'execution');reserve=create_journal_reserve(lease)
journal,rows=records(root,lease,store,reserve)
if point=='before_consumption':os._exit(23)
with store._live() as owner:api=owner.api
publish=api.publish_metadata

def crash_publish(path,data):
    if path.parent.name=='fake-execution-attempts':
        if path.name=='identity.json' and point=='after_identity':publish(path,data);os._exit(23)
        if path.name=='head.json':
            if point=='before_head':os._exit(23)
            if point=='after_head':publish(path,data);os._exit(23)
    return publish(path,data)
api.publish_metadata=crash_publish
assert journal.consume(*args(rows[0]),now=AT)['first_consumption']
assert point=='after_commit'
os._exit(23)
