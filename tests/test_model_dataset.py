"""Synthetic source-to-model bridge with actual calendar and hand labels."""
import json
from decimal import Decimal as D
import pytest
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.modeling.dataset import assemble_training_rows
from compertum.modeling.ridge import prepare_fit,fit_ridge,predict
from compertum.modeling.registry import FEATURES
from helpers.simulation_fixture import fixture,changed,with_action,SECTORS


def invented():
    chunks,start,_,dates=fixture()
    def edit(v):
        for b in v['bars']:
            if b['reference']=='entry':
                price=format(D(100)+D(max(0,dates.index(b['session_date'])-252))/100,'f')
                for key in ('open','high','low','close'):b[key]=price
    return changed(chunks,edit),start,dates


@pytest.mark.parametrize('horizon',[1,5,21])
def test_hand_label_full_denominator_and_fit_serve_bridge(horizon):
    chunks,start,dates=invented();end=dates[254]
    result=assemble_training_rows(chunks,SECTORS,start,end,horizon)
    value=json.loads(result.content);rows=json.loads(result.rows.content)['rows']
    assert value['expected_rows']==36 and value['assembled_rows']==9
    assert len(value['omissions'])==27 and value['financial_accepted'] is False
    first=next(r for r in rows if r['symbol']=='AAPL' and r['decision_at']==session_times(start).decision.isoformat())
    assert first['target']==pytest.approx(horizon*.01/100,abs=1e-15)
    assert first['label_revision_id'].startswith('label-')
    assert value['row_provenance'][0]['feature_sha256']
    manifest=prepare_fit(result.rows,2022);artifact=fit_ridge(result.rows,manifest,f'ridge-h{horizon:02}-a001')
    vectors=[r['features'] for r in rows]
    batch=predict(artifact,vectors,feature_names=FEATURES)
    assert batch==pytest.approx([predict(artifact,[v],feature_names=FEATURES)[0] for v in vectors],rel=1e-12,abs=1e-12)


def test_missing_label_purges_all_otherwise_eligible_assets_at_date():
    chunks,start,dates=invented();exit_day=dates[253]
    from compertum.data.snapshot import validate_snapshot
    shortened=[];last_feature=session_times(start).previous_date
    for chunk in chunks:
        value=json.loads(chunk.content)
        if value['assets'][0]['symbol']=='AAPL':
            value['feature_sessions']=[d for d in value['feature_sessions'] if d<=last_feature]
            if not value['feature_sessions']:continue
            value['bars']=[b for b in value['bars'] if b['session_date']<=(start if b['reference']=='entry' else last_feature)]
        shortened.append(validate_snapshot(json.dumps(value).encode()))
    result=assemble_training_rows(tuple(shortened),SECTORS,start,start,1)
    assert result.rows is None
    value=json.loads(result.content);assert value['assembled_rows']==0 and len(value['omissions'])==12
    eligible=[r for r in value['omissions'] if r['symbol'] in ('AAPL','MSFT','JPM')]
    assert all('SAME_DATE_LABEL_PURGE' in r['reasons'] for r in eligible)


def test_future_label_revision_causes_later_whole_date_fit_purge():
    chunks,start,dates=invented();exit_day=dates[253]
    def edit(v):
        if v['assets'][0]['symbol']=='AAPL':
            for b in v['bars']:
                if b['reference']=='entry' and b['session_date']==exit_day:b['simulated_revision_available_at']='2022-01-03T12:00:01Z'
    result=assemble_training_rows(changed(chunks,edit),SECTORS,start,dates[255],1)
    manifest=json.loads(prepare_fit(result.rows,2022).content)
    assert len(manifest['excluded'])==6 and len(manifest['included'])==6
    assert all('SAME_DATE_PURGE' in r['reasons'] for r in manifest['excluded'])


def test_split_consistent_label_and_dividend_exclusion():
    chunks,start,dates=invented();split_day=dates[253]
    normal=assemble_training_rows(chunks,SECTORS,start,start,5)
    split=assemble_training_rows(with_action(chunks,split_day,kind='SPLIT'),SECTORS,start,start,5)
    dividend=assemble_training_rows(with_action(chunks,split_day,kind='DIVIDEND'),SECTORS,start,start,5)
    values=[json.loads(r.rows.content)['rows'] for r in [normal,split,dividend]]
    assert [r['target'] for r in values[0]]==pytest.approx([r['target'] for r in values[1]],abs=1e-15)
    assert [r['target'] for r in values[0]]==[r['target'] for r in values[2]]
    assert normal.rows.sha256!=split.rows.sha256


def test_determinism_and_snapshot_tampering():
    chunks,start,_=invented();a=assemble_training_rows(chunks,SECTORS,start,start,1);b=assemble_training_rows(tuple(reversed(chunks)),SECTORS,start,start,1)
    assert a.content==b.content and a.rows.content==b.rows.content
    from dataclasses import replace
    with pytest.raises(DataError):assemble_training_rows((replace(chunks[0],content=chunks[0].content+b' '),)+chunks[1:],SECTORS,start,start,1)


@pytest.mark.parametrize('horizon',[0,2,True,'1'])
def test_unregistered_horizon_refused(horizon):
    chunks,start,_=invented()
    with pytest.raises(DataError):assemble_training_rows(chunks,SECTORS,start,start,horizon)


def test_provider_evidence_is_not_retagged_synthetic():
    with pytest.raises(DataError):assemble_training_rows([object()],SECTORS,'2021-01-04','2021-01-04',1)


def test_provider_payload_inside_snapshot_type_is_still_rejected():
    from dataclasses import replace
    import hashlib
    chunks,start,_=invented();value=json.loads(chunks[0].content);value['source']['provider']='alpaca'
    raw=json.dumps(value).encode();fake=replace(chunks[0],content=raw,sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(DataError):assemble_training_rows((fake,)+chunks[1:],SECTORS,start,start,1)
