"""Opaque transfer with real loopback evidence and genuine publication ledger."""
import base64,hashlib
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_market_evidence import publish_market_evidence
from test_paper_read_owner import owner
from test_execution_health import pair
from test_paper_market_owner_native import native_market,finish
from test_paper_market_owner import prepare,authorize,start,status
from test_paper_market_collection import pages


@pytest.fixture
def ready(native_market):
 o=native_market
 with pages([canonical(dict(bars={'MSFT':[]},next_page_token=None))]) as (port,seen):
  o.market_port=port;p=prepare(o);authorize(o,p);start(o,p);s=finish(o,p)
  assert s['state']=='EVIDENCE_READY' and len(seen)==1
 return o,p,s


def transfer(o,operation,p,**fields):
 return o.a.market_transfer(dict(operation=operation,job_id=p['job_id'],**fields))


def publish(o):
 cipher=o.a._market._cipher;child=o.manager.split_grant(o.grant,len(cipher.ciphertext))
 return child,publish_market_evidence(o.manager,child,cipher)


def test_transfer_chunks_are_exact_bounded_and_repeat_safe(ready):
 o,p,s=ready;e=s['evidence'];out=bytearray();first=None
 while len(out)<e['size_bytes']:
  args=dict(offset=len(out),sha256=e['sha256']);chunk=transfer(o,'chunk',p,**args)
  assert chunk==transfer(o,'chunk',p,**args)
  if first is None:first=chunk
  assert {k:chunk[k] for k in ('project_id','job_id','task_id','account_alias','mode','grant_sha256')}==dict(project_id=o.e.lease.project_id,job_id=p['job_id'],task_id=p['task_id'],account_alias='fixture',mode='HISTORY',grant_sha256=p['grant_sha256'])
  raw=base64.b64decode(chunk['data'],validate=True);assert len(raw)==min(32768,e['size_bytes']-len(out))
  out.extend(raw)
 assert bytes(out)==o.a._market._cipher.ciphertext and hashlib.sha256(out).hexdigest()==e['sha256']
 for args in (dict(offset=1,sha256=e['sha256']),dict(offset=0,sha256='f'*64),dict(offset=True,sha256=e['sha256'])):
  with pytest.raises(RuntimeRefused):transfer(o,'chunk',p,**args)
 assert 'ciphertext' not in status(o,p)


def test_ack_requires_genuine_publication_and_frees_checkpoint_only_after_validation(ready):
 o,p,s=ready;cipher=o.a._market._cipher
 fake=dict(artifact_id=str(uuid4()),task_id=p['task_id'],path=f'artifacts/runs/{p["task_id"]}/market-collection-{p["job_id"]}.bin',**s['evidence'])
 with pytest.raises(RuntimeRefused):transfer(o,'ack',p,manifest=fake)
 assert o.a._market._cipher is cipher
 child,manifest=publish(o);result=transfer(o,'ack',p,manifest=manifest)
 assert result['state']=='PUBLISHED' and result['manifest']==manifest and o.a._market._cipher is None
 assert transfer(o,'ack',p,manifest=manifest)==result
 o.a.require_checkpoint()


@pytest.mark.parametrize('fault',['task','hash','path','size','artifact'])
def test_ack_substitution_preserves_original_cipher_and_record(ready,fault):
 o,p,s=ready;child,manifest=publish(o);cipher=o.a._market._cipher;bad=dict(manifest)
 key={'task':'task_id','hash':'sha256','path':'path','size':'size_bytes','artifact':'artifact_id'}[fault]
 bad[key]={'task':str(uuid4()),'hash':'f'*64,'path':'artifacts/latest.bin','size':manifest['size_bytes']+1,'artifact':str(uuid4())}[fault]
 with pytest.raises(RuntimeRefused):transfer(o,'ack',p,manifest=bad)
 assert o.a._market._cipher is cipher and status(o,p)['state']=='EVIDENCE_READY'
 assert transfer(o,'ack',p,manifest=manifest)['state']=='PUBLISHED'


def test_ack_after_owner_recreation_recovers_publication_without_cipher_or_dispatch(ready):
 o,p,s=ready;child,manifest=publish(o);o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
 assert status(o,p)['state']=='INTERRUPTED' and o.a._market._cipher is None
 assert transfer(o,'ack',p,manifest=manifest)['state']=='PUBLISHED'
 assert start(o,p)['state']=='PUBLISHED';o.a.tick();o.a.require_checkpoint()


def test_ignored_ack_write_retains_cipher_and_can_verify_exact_same_artifact(ready):
 o,p,s=ready;child,manifest=publish(o);cipher=o.a._market._cipher
 o.a.db.execute("CREATE TRIGGER deny_ack BEFORE UPDATE ON state WHEN NEW.key LIKE 'paper_market_job:%' BEGIN SELECT RAISE(IGNORE); END")
 with pytest.raises(RuntimeRefused,match='MARKET_WRITE_UNVERIFIED'):transfer(o,'ack',p,manifest=manifest)
 assert o.a._market._cipher is cipher and status(o,p)['state']=='EVIDENCE_READY'
 o.a.db.execute('DROP TRIGGER deny_ack');o.a.db.commit()
 assert transfer(o,'ack',p,manifest=manifest)['state']=='PUBLISHED'


def test_public_commands_cannot_request_private_chunks_or_ack(ready):
 o,p,s=ready
 for operation in ('chunk','ack'):
  with pytest.raises(RuntimeRefused,match='CONTROL_PAYLOAD_DENIED'):
   o.a.market_handle(dict(subject_key='a'*64,command=dict(operation=operation,job_id=p['job_id'])))


def test_ack_checks_original_encrypted_generation_against_saved_grant(ready):
 o,p,s=ready;child,manifest=publish(o);record=o.a._market.records.read(p['job_id'])
 record['grant']['owner_generation']+=1
 record['grant_sha256']=hashlib.sha256(canonical(record['grant'])).hexdigest()
 with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',(canonical(record).decode(),'paper_market_job:'+p['job_id']))
 with pytest.raises(RuntimeRefused,match='MARKET_PUBLICATION_UNVERIFIED'):transfer(o,'ack',p,manifest=manifest)
 assert o.a._market._cipher is not None and status(o,p)['state']=='EVIDENCE_READY'


def test_actual_multichunk_evidence_rejects_old_replay_after_advancing(native_market):
 o=native_market;body=canonical(dict(bars={'MSFT':[]},next_page_token=None,fixture_padding='x'*40000))
 with pages([body]) as (port,seen):
  o.market_port=port;p=prepare(o);authorize(o,p);start(o,p);s=finish(o,p)
 assert s['evidence']['size_bytes']>32768
 sha=s['evidence']['sha256'];first=transfer(o,'chunk',p,offset=0,sha256=sha)
 assert len(base64.b64decode(first['data']))==32768
 second=transfer(o,'chunk',p,offset=32768,sha256=sha)
 assert second==transfer(o,'chunk',p,offset=32768,sha256=sha)
 with pytest.raises(RuntimeRefused,match='MARKET_TRANSFER_ORDER'):transfer(o,'chunk',p,offset=0,sha256=sha)
 assert base64.b64decode(first['data'])+base64.b64decode(second['data'])==o.a._market._cipher.ciphertext
