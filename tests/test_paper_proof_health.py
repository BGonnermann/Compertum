"""Native owner/peer identities; simulated original health/account clocks."""
import hashlib,json
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication,launch
from test_paper_account_binding import invented_paper_origin,propose,confirm,call
from test_paper_presence import account,acknowledge,advance,inspect
from test_paper_account_context import context
from test_paper_account_presence_proofs import presence_proof


def test_stale_account_in_joint_proofs_keeps_valid_five_minute_presence(account):
    from compertum.runtime.paper_final_proof import _verify_proofs
    o,_,_=account;_,r=acknowledge(account);ctx=context(account)
    cp=ctx._prepare_proof();pp=presence_proof(o,r);advance(o,31)
    with pytest.raises(RuntimeRefused,match='PAPER_PREFLIGHT_STALE'):_verify_proofs(cp,pp)
    assert ctx._closed and inspect(o,r)['presence_status']=='CURRENT'


@pytest.mark.parametrize('fault',['gap','reversed','drift','stale_peer','native_peer_metadata_changed'])
def test_final_proof_rechecks_health_without_service_or_committing_halt(account,fault):
    o,_,_=account;ctx=context(account);proof=ctx._prepare_proof();original=None
    path=o.manager.root/'state/locks/watchdog.json'
    if fault=='native_peer_metadata_changed':
        original=path.read_bytes();value=json.loads(original);value['generation']+=1
        path.write_text(json.dumps(value))
    elif fault=='gap':o.c.mono+=16;o.c.utc+=16;o.clock.mono+=16;o.clock.utc+=16
    elif fault=='reversed':o.c.mono-=1;o.c.utc-=1
    elif fault=='drift':o.c.mono+=1;o.c.utc+=7
    else:
        o.c.mono+=14;o.c.utc+=14;o.e.tick()
        o.c.mono+=2;o.c.utc+=2;o.clock.mono+=16;o.clock.utc+=16
    assert o.e.reason is None
    observed=(o.e.last_mono,o.e.last_utc,o.e.observed,o.e.observed_utc,o.e.peer_sequence)
    before=o.a.db.total_changes
    try:
        with pytest.raises(RuntimeRefused):proof._verify()
        assert ctx._closed and o.a.db.total_changes==before
        assert (o.e.last_mono,o.e.last_utc,o.e.observed,o.e.observed_utc,o.e.peer_sequence)==observed
    finally:
        if original is not None:
            (o.a.store.root/'injected-proof-peer-fault.json').write_text(json.dumps(dict(fault=fault,observed_sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
            path.write_bytes(original)
