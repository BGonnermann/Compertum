"""Original grant consumption clocks and immutable execution-state evidence."""
from copy import deepcopy
from datetime import timedelta
import importlib,math
import pytest
from compertum.data.encoding import canonical
from compertum.paper_contracts import timestamp
from compertum.runtime.paper_market_grants import build_grant,MarketGrant
from compertum.runtime.errors import RuntimeRefused
from test_paper_market_grants import values
from test_paper_market_records import records,record


def module():return importlib.import_module('compertum.runtime.paper_market_consumption')


def proof(grant=None,seconds=0):
    grant=grant or build_grant(**values());g=grant.to_payload()
    return module().build_consumption(grant,consumed_at=(timestamp(g['created_at'])+timedelta(seconds=seconds)).isoformat(),monotonic_at=g['prepared_mono']+seconds)


@pytest.mark.parametrize('seconds',[0,55,59.999])
def test_original_exclusive_lifetime_accepts_observed_consumption(seconds):
    grant=build_grant(**values());p=proof(grant,seconds)
    assert module().validate_consumption(p,grant)==p
    assert p['grant_sha256']==grant.sha256 and p['owner_instance']==grant.to_payload()['owner_instance']
    assert p['monotonic_at']==100+seconds and p['elapsed_seconds']==p['monotonic_at']-100


@pytest.mark.parametrize('fault',['wall_expiry','mono_expiry','wall_rollback','mono_rollback','divergence','nan','inf','bool'])
def test_invalid_consumption_clock_observations_are_refused(fault):
    g=build_grant(**values());wall=0;mono=100
    if fault=='wall_expiry':wall=60;mono=159
    elif fault=='mono_expiry':wall=59;mono=160
    elif fault=='wall_rollback':wall=-1
    elif fault=='mono_rollback':mono=99
    elif fault=='divergence':wall=6
    elif fault=='nan':mono=math.nan
    elif fault=='inf':mono=math.inf
    else:mono=True
    with pytest.raises(RuntimeRefused):module().build_consumption(g,consumed_at=(timestamp(g.to_payload()['created_at'])+timedelta(seconds=wall)).isoformat(),monotonic_at=mono)


@pytest.mark.parametrize('field',['project_id','job_id','grant_sha256','owner_instance','owner_generation','purpose','version','extra','elapsed_seconds','consumed_at'])
def test_consumption_context_or_observation_substitution_is_refused(field):
    g=build_grant(**values());p=proof(g)
    if field in {'owner_generation','version','elapsed_seconds'}:p[field]+=1
    elif field=='extra':p[field]=True
    elif field=='consumed_at':p[field]='2023-11-24T14:00:00Z'
    else:p[field]='changed'
    with pytest.raises(RuntimeRefused):module().validate_consumption(p,g)


def granted(records):
    r,db,_=records;v=record()
    with db:r.write(v,new=True);v['state']='GRANTED';r.write(v)
    return r,db,v,module().ConsumptionRecords(r)


def consume(r,db,v,store):
    p=proof(MarketGrant(canonical(v['grant'])))
    with db:
        v.update(state='RUNNING',consumed=True);r.write(v);store.write(p)
    return p


def test_consumption_is_immutable_and_survives_record_restart(records):
    r,db,v,s=granted(records);p=consume(r,db,v,s)
    r.interrupt_unfinished()
    assert module().ConsumptionRecords(r).read(v['grant']['job_id'])==p
    with pytest.raises(RuntimeRefused),db:s.write(p)
    assert s.read(v['grant']['job_id'])==p


@pytest.mark.parametrize('fault',['ignored_proof','ignored_job'])
def test_ignored_write_rolls_back_both_halves_of_consumption(records,fault):
    r,db,v,s=granted(records);job=v['grant']['job_id']
    if fault=='ignored_proof':sql="CREATE TRIGGER deny_consumption BEFORE INSERT ON state WHEN NEW.key LIKE 'paper_market_consumption:%' BEGIN SELECT RAISE(IGNORE); END"
    else:sql="CREATE TRIGGER deny_job BEFORE UPDATE ON state WHEN NEW.key='paper_market_job:"+job+"' BEGIN SELECT RAISE(IGNORE); END"
    db.execute(sql)
    with pytest.raises(RuntimeRefused):consume(r,db,v,s)
    assert r.read(job)['state']=='GRANTED' and not r.read(job)['consumed']
    assert db.execute("SELECT 1 FROM state WHERE key=?",('paper_market_consumption:'+job,)).fetchone() is None


@pytest.mark.parametrize('fault',['missing','altered','oversized','orphan'])
def test_legacy_or_corrupt_proof_never_manufactures_evidence(records,fault):
    r,db,v,s=granted(records);p=consume(r,db,v,s);job=v['grant']['job_id'];key='paper_market_consumption:'+job
    with db:
        if fault=='missing':db.execute('DELETE FROM state WHERE key=?',(key,))
        elif fault=='oversized':db.execute('UPDATE state SET value=? WHERE key=?',('x'*4097,key))
        elif fault=='orphan':db.execute('DELETE FROM state WHERE key=?',('paper_market_job:'+job,))
        else:
            p['elapsed_seconds']+=1;db.execute('UPDATE state SET value=? WHERE key=?',(canonical(p).decode(),key))
    with pytest.raises(RuntimeRefused):s.read(job)
    if fault=='missing':assert r.read(job)['consumed'] and module().ConsumptionRecords(r)


def test_consumption_requires_an_open_transaction_and_consumed_job(records):
    r,db,v,s=granted(records);p=proof(MarketGrant(canonical(v['grant'])))
    with pytest.raises(RuntimeRefused):s.write(p)
    with pytest.raises(RuntimeRefused),db:
        db.execute("UPDATE state SET value=value WHERE key='paper_market_owner_version'");s.write(p)
