"""Original journal decoding is separate from native source authority."""
import hashlib,json
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_fixture_economic_source import create,pay,snapshot

def decode(raw):
    from compertum.fixture_source_journal import decode_source_journal
    return decode_source_journal(raw)

def journal(tmp_path):
    source,clock=create(tmp_path);pay(source,clock);snapshot(source)
    raw=source.path.read_bytes();source.close();return raw

def test_original_journal_preserves_event_head_and_acknowledged_interval(tmp_path):
    raw=journal(tmp_path);result=decode(raw)
    assert result['ledger']['event_count']==2
    assert result['ledger']['covered_until']=='2023-11-24T15:02:00Z'
    assert result['producer_id'] and result['journal_sha256']==hashlib.sha256(raw).hexdigest()
    assert result['source_qualified'] is False

def test_source_begin_does_not_invent_an_acknowledged_interval(tmp_path):
    source,_=create(tmp_path);raw=source.path.read_bytes();source.close()
    result=decode(raw);assert result['ledger']['covered_until'] is None

@pytest.mark.parametrize('damage',['partial-tail','duplicate-key','changed-amount','wrong-genesis','wrong-sequence',
 'duplicate-event','event-after-ack-at-same-time','clock-backward','unknown-record','missing-version','oversized'])
def test_changed_or_incomplete_journal_refuses(tmp_path,damage):
    raw=journal(tmp_path);lines=raw.splitlines(keepends=True)
    if damage=='partial-tail':raw+=b'{'
    elif damage=='duplicate-key':raw=raw.replace(b'"version":1',b'"version":1,"version":1',1)
    elif damage=='changed-amount':raw=raw.replace(b'"amount":"0.02"',b'"amount":"0.03"',1)
    elif damage=='oversized':raw=b'x'*(128*1024+1)
    else:
        values=[json.loads(line) for line in lines]
        if damage=='wrong-genesis':values[0]['header']['opening_cash']='999'
        elif damage=='wrong-sequence':values[1]['sequence']=2
        elif damage=='duplicate-event':values[2]['event_id']=values[1]['event_id']
        elif damage=='clock-backward':values[-1]['at']='2023-11-24T15:01:00Z'
        elif damage=='unknown-record':values[-1]['kind']='UNSUPPORTED'
        elif damage=='missing-version':values[0].pop('version')
        else:
            row=dict(values[1],event_id='late-fee',sequence=3,at=values[-1]['covered_until'],previous_sha256=values[2]['sha256'])
            row.pop('sha256');row['sha256']=hashlib.sha256(canonical(row)).hexdigest();values.append(row)
        raw=b''.join(canonical(v)+b'\n' for v in values)
    with pytest.raises(RuntimeRefused):decode(raw)

def test_observation_acknowledgements_do_not_replay_fee_events(tmp_path):
    source,clock=create(tmp_path);pay(source,clock);first=snapshot(source)
    clock.value='2023-11-24T15:10:00Z';snapshot(source)
    result=decode(source.path.read_bytes());source.close()
    assert result['ledger']['events']==first['ledger']['events']
    assert result['ledger']['ledger_head_sha256']==first['ledger']['ledger_head_sha256']
    assert result['ledger']['covered_until']==clock.value
