"""Exit without cleanup at exact invented-effect durability boundaries."""
import os,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_fake_execution_journal import checked_records,observed,arguments
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from test_execution_risk import NOW
from uuid import uuid4

root=Path(sys.argv[1]);point=sys.argv[2];project=resolve_project(root);lease=acquire_owner(project,'execution');journal=FakeIntentJournal(open_store(lease,'execution'))
i,d=checked_records(lease);journal.record_checked(i,d);waiting,decision=checked_records(lease);journal.record_checked(waiting,decision)
with sqlite3.connect(root/'independent-fake-broker.sqlite') as broker:broker.execute('CREATE TABLE accepted(client TEXT PRIMARY KEY,body TEXT NOT NULL)')
(root/'fixture.json').write_text(json.dumps(dict(intent=i.to_payload(),waiting=waiting.to_payload(),point=point)))
if point=='before_attempt':os._exit(23)
if point in {'before_attempt_guard_head','after_attempt_guard_head'}:
 with journal.store._live() as owner:api=owner.api
 publish=api.publish_metadata
 def crash_publish(path,data):
  if path.name=='head.json' and path.parent.name=='fake-execution-attempts':
   if point=='before_attempt_guard_head':os._exit(23)
   publish(path,data);os._exit(23)
  return publish(path,data)
 api.publish_metadata=crash_publish

assert journal.begin_attempt(*arguments(i),now=NOW)['simulate_once']
if point=='after_attempt':os._exit(23)
with sqlite3.connect(root/'independent-fake-broker.sqlite') as broker:broker.execute('INSERT INTO accepted VALUES(?,?)',(journal.read(*arguments(i))['client_order_id'],json.dumps(i.to_payload())))
if point=='after_acceptance':os._exit(23)
journal.observe(*arguments(i),observed(i,lease),event_id=str(uuid4()))
if point=='after_late_incident':
 from datetime import timedelta
 from compertum.execution_contracts import instant
 def at(seconds):return (instant(NOW)+timedelta(seconds=seconds)).isoformat()
 journal.uncertain(*arguments(i),reason='DISCONNECT',now=at(130))
 assert journal.reserve_poll(*arguments(i),now=at(132))['poll']
os._exit(23)
