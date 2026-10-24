"""Stage E4: total trial count, deflated Sharpe ratio and the candidate queue with sealed vault batches.

The expected numbers below were calculated by hand with the standard formulas and the standard library's NormalDist
(statistics module), independent of deflation.py, which uses erfc and bisection. Product lane; no Deep Agents needed.
"""
from decimal import Decimal
from uuid import uuid4
import pytest
from test_ai_manual import bridge  # noqa: F401  (fixture)
from compertum.ai.engine.deflation import (BASE_FAMILY,DSR_MIN,deflated_sharpe,expected_max_sharpe,family_size,moments,normal_cdf,normal_quantile,
                                           probabilistic_sharpe,trial_variance)
from compertum.ai.engine.ledger import EngineLedger
from compertum.ai.engine.market import market_csv,score_signals,split_market_tiers,synthetic_market
from compertum.ai.engine.vault import CandidateQueue
from compertum.runtime.errors import RuntimeRefused

CANDIDATE={'observations':100,'sharpe_per_period':'0.2','sharpe_status':'DEFINED','skewness':'0','kurtosis':'3'}
PASSING={'trials':1,'status':'PASS','deflated_sharpe':'0.97560194','minimum':'0.95'}


def near(value,expected,places=7):
    return abs(Decimal(str(value))-Decimal(str(expected)))<=Decimal(10)**-places


def test_normal_functions_match_the_table():
    # Standard normal quantiles: Z(0.9) = 1.2815516, Z(0.95) = 1.6448536, Z(0.975) = 1.9599640.
    assert near(normal_quantile(0.9),'1.2815516') and near(normal_quantile(0.95),'1.6448536') and near(normal_quantile(0.975),'1.9599640')
    assert normal_cdf(0.0)==0.5 and near(normal_cdf(1.959964),'0.975',6)
    for bad in (0.0,1.0,-0.1,1.5,'0.5',None):
        with pytest.raises(RuntimeRefused,match='^ENGINE_DEFLATION_DENIED$'): normal_quantile(bad)


def test_expected_max_sharpe_hand_cases():
    # N = 10, V = 0.01: SR0 = 0.1 * ((1 - 0.5772157) * Z(0.9) + 0.5772157 * Z(1 - 1/(10 e)))
    #                       = 0.1 * (0.4227843 * 1.2815516 + 0.5772157 * 1.7892418) = 0.1574598
    assert near(expected_max_sharpe(10,'0.01'),'0.15745983')
    # N = 100, V = 0.04: SR0 = 0.2 * (0.4227843 * Z(0.99) + 0.5772157 * Z(1 - 1/(100 e))) = 0.5061206
    assert near(expected_max_sharpe(100,'0.04'),'0.50612058')
    # One trial has no selection effect.
    assert expected_max_sharpe(1,'0.5')==0.0
    # More trials or more variance only raise the bar.
    assert expected_max_sharpe(20,'0.01')>expected_max_sharpe(10,'0.01')>expected_max_sharpe(2,'0.01')>0 and expected_max_sharpe(10,'0.04')>expected_max_sharpe(10,'0.01')
    for trials,variance in ((0,'0.01'),(1.0,'0.01'),(10,'-0.01'),(10,'nan'),(10**9+1,'0.01')):
        with pytest.raises(RuntimeRefused,match='^ENGINE_DEFLATION_DENIED$'): expected_max_sharpe(trials,variance)


def test_deflated_sharpe_hand_cases():
    # Case A: SR = 0.2, T = 100, normal returns, N = 10, V = 0.01. Term = 1 + (3 - 1)/4 * 0.04 = 1.02.
    # z = (0.2 - 0.1574598) * sqrt(99) / sqrt(1.02) = 0.4190991; DSR = Phi(z) = 0.6624281 -> FAIL.
    a=deflated_sharpe(CANDIDATE,10,'0.01')
    assert a['status']=='FAIL' and a['deflated_sharpe']=='0.66242815' and a['expected_max_sharpe']=='0.15745983' and a['trials']==10
    assert a['section_10_family_size']==BASE_FAMILY==12 and a['minimum']=='0.95' and a['observations']==100 and a['sharpe_per_period']=='0.2'
    # Case B: the same candidate as the only trial. z = 0.2 * sqrt(99) / sqrt(1.02) = 1.9703; DSR = 0.9756019 -> PASS.
    b=deflated_sharpe(CANDIDATE,1,'0.01')
    assert b['status']=='PASS' and b['deflated_sharpe']=='0.97560194' and b['expected_max_sharpe']=='0.00000000'
    # Case C: skewness -1 and kurtosis 6 lower the DSR for the same Sharpe ratio. Term = 1 + 0.2 + 5/4 * 0.04 = 1.25; DSR = 0.9624528.
    c=deflated_sharpe({**CANDIDATE,'skewness':'-1','kurtosis':'6'},1,'0.01')
    assert c['status']=='PASS' and c['deflated_sharpe']=='0.96245282' and Decimal(c['deflated_sharpe'])<Decimal(b['deflated_sharpe'])
    # Case D: SR = 0.5, T = 250, N = 100, V = 0.04. SR0 = 0.5061206 is above the estimate; DSR = 0.4637234 -> FAIL. Family size grows to 100.
    d=deflated_sharpe({**CANDIDATE,'observations':250,'sharpe_per_period':'0.5'},100,'0.04')
    assert d['status']=='FAIL' and d['deflated_sharpe']=='0.46372344' and d['section_10_family_size']==100
    # Undefined when the Sharpe ratio is undefined, or when the moment term is not positive (skewness 10: 1 - 2 + 0.02 < 0).
    assert deflated_sharpe({**CANDIDATE,'sharpe_per_period':None,'sharpe_status':'UNDEFINED'},1,'0.01')['status']=='UNDEFINED'
    u=deflated_sharpe({**CANDIDATE,'skewness':'10'},1,'0.01');assert u['status']=='UNDEFINED' and u['deflated_sharpe'] is None
    assert probabilistic_sharpe(0.2,0.0,100,10.0,3.0) is None
    assert DSR_MIN==Decimal('0.95') and family_size(5)==12 and family_size(13)==13
    # The gate compares the unrounded value: a DSR just under 0.95 fails even when its 8-place text reads 0.95000000.
    assert a['trial_variance']=='0.01000000' and deflated_sharpe(CANDIDATE,1,'1e-8')['trial_variance']=='0.00000001'
    with pytest.raises(RuntimeRefused,match='^ENGINE_DEFLATION_DENIED$'): family_size(0)


def test_moments_hand_case():
    # Returns 0.01, -0.02, 0.03, 0.00, 0.02, -0.01: mean 0.005, sample sd 0.0187083, SR = 0.2672612.
    # Deviations 0.005, -0.025, 0.025, -0.005, 0.015, -0.015 are symmetric, so skewness is exactly 0.
    # Kurtosis = (sum d^4 / 6) / (sum d^2 / 6)^2 = 1.7314286.
    m=moments(['0.01','-0.02','0.03','0.00','0.02','-0.01'])
    assert m=={'observations':6,'sharpe_per_period':'0.26726124','sharpe_status':'DEFINED','skewness':'0.00000000','kurtosis':'1.73142857'}
    assert moments([Decimal('0.01')]*5)=={'observations':5,'sharpe_per_period':None,'sharpe_status':'UNDEFINED','skewness':None,'kurtosis':None}
    for bad in (['0.01','0.02','0.03'],['0.01','x','0.03','0.04'],'0.01',None,['0.01','0.02','0.03','inf']):
        with pytest.raises(RuntimeRefused,match='^ENGINE_DEFLATION_DENIED$'): moments(bad)


def test_trial_variance_never_falls_below_the_null_floor():
    # Sharpe ratios 0.1, 0.3, 0.2: sample variance 0.01. Floor for SR = 0.2, T = 100: (1 + 0.02) / 99 = 0.0103030.
    v=trial_variance(['0.1','0.3','0.2'],CANDIDATE)
    assert v=={'trial_sharpes':3,'sample_variance':'0.01000000','floor_variance':'0.01030303','trial_variance':'0.01030303'}
    # Sharpe ratios 0.1 and 0.9: sample variance 0.32 is above the floor and wins.
    assert trial_variance(['0.1',None,'0.9'],CANDIDATE)['trial_variance']=='0.32000000'
    # Fewer than two defined Sharpe ratios: no sample variance; the floor applies.
    assert trial_variance(['0.1'],CANDIDATE)=={'trial_sharpes':1,'sample_variance':None,'floor_variance':'0.01030303','trial_variance':'0.01030303'}
    assert trial_variance([],{**CANDIDATE,'sharpe_per_period':None})['trial_variance']=='0.01010101'
    with pytest.raises(RuntimeRefused,match='^ENGINE_DEFLATION_DENIED$'): trial_variance(['0.1'],{**CANDIDATE,'observations':3})


def test_total_trial_count_is_insert_only(bridge):
    b,_=bridge;ledger=EngineLedger(b.store)
    assert ledger.total_trials()==0
    ledger.record_trial('cycle-0001-x','cycle-0001-x:h1',{'hypothesis_id':'h1'});ledger.record_trial('cycle-0001-x','cycle-0001-x:h2',{'hypothesis_id':'h2'})
    assert ledger.total_trials()==2
    with pytest.raises(RuntimeRefused,match='^ENGINE_TRIAL_DUPLICATE$'): ledger.record_trial('cycle-0002-y','cycle-0001-x:h1',{})
    # Trials from another campaign: the fixed family of 12, recorded once by its source.
    ledger.record_external_trials('m3-repair-20261023-02',12,{'scorecard':'synthetic-campaign-scorecard-v1','family_size':12})
    assert ledger.total_trials()==14
    with pytest.raises(RuntimeRefused,match='^ENGINE_TRIAL_DUPLICATE$'): ledger.record_external_trials('m3-repair-20261023-02',12,{})
    for source,count in (('bad source',1),('ok',0),('ok',100001),('ok','12'),('',1)):
        with pytest.raises(RuntimeRefused,match='^ENGINE_RECORD_DENIED$'): ledger.record_external_trials(source,count,{})
    assert ledger.total_trials()==14
    # Scores: once per engine trial; unknown or external trials refuse; undefined Sharpe ratios stay counted but add no variance.
    ledger.record_trial_score('cycle-0001-x:h1',{'sharpe_per_period':'0.2','status':'SCORED'})
    ledger.record_trial_score('cycle-0001-x:h2',{'sharpe_per_period':None,'status':'NO_SIGNALS'})
    with pytest.raises(RuntimeRefused,match='^ENGINE_TRIAL_DUPLICATE$'): ledger.record_trial_score('cycle-0001-x:h1',{'sharpe_per_period':'0.9'})
    with pytest.raises(RuntimeRefused,match='^ENGINE_TRIAL_UNKNOWN$'): ledger.record_trial_score('nobody',{'sharpe_per_period':'0.9'})
    with pytest.raises(RuntimeRefused,match='^ENGINE_TRIAL_UNKNOWN$'): ledger.record_trial_score('external:m3-repair-20261023-02',{'sharpe_per_period':'0.9'})
    assert ledger.trial_sharpes()==['0.2'] and ledger.total_trials()==14


def test_queue_admission_requires_every_gate(bridge):
    b,_=bridge;queue=CandidateQueue(EngineLedger(b.store));cid=f'cycle-0001-{uuid4().hex[:8]}:h1'
    score={'beats_baseline':True,'sharpe':'1.0'}
    for kwargs,reason in ((dict(score={**score,'beats_baseline':False},deflation=PASSING,tests_passed=True,auditor_passed=True),'does not beat the baseline on VALIDATION'),
                          (dict(score=score,deflation={**PASSING,'status':'FAIL'},tests_passed=True,auditor_passed=True),'deflation gate FAIL'),
                          (dict(score=score,deflation={**PASSING,'deflated_sharpe':'0.94'},tests_passed=True,auditor_passed=True),'deflation record inconsistent'),
                          (dict(score=score,deflation={**PASSING,'minimum':'0.90'},tests_passed=True,auditor_passed=True),'deflation record inconsistent'),
                          (dict(score=score,deflation=PASSING,tests_passed=False,auditor_passed=True),'tests not passed'),
                          (dict(score=score,deflation=PASSING,tests_passed=True,auditor_passed=None),'Auditor not passed')):
        with pytest.raises(RuntimeRefused,match='^ENGINE_QUEUE_DENIED$'): queue.admit(cid,**kwargs)
        assert queue.ledger.queue_events(cid)[-1]['event']=='DENIED' and queue.ledger.queue_events(cid)[-1]['reasons']==[reason]
    assert queue.state(cid)==(None,None) and queue.queued()==[]
    row=queue.admit(cid,score,PASSING,tests_passed=True,auditor_passed=True)
    assert row['event']=='QUEUED' and row['deflation']==PASSING and len(row['score_sha256'])==64 and queue.state(cid)==('QUEUED',None) and queue.queued()==[cid]
    with pytest.raises(RuntimeRefused,match='^ENGINE_QUEUE_DENIED$'): queue.admit(cid,score,PASSING,tests_passed=True,auditor_passed=True)
    assert queue.ledger.queue_events(cid)[-1]['reasons']==['already QUEUED'] and queue.queued()==[cid]
    with pytest.raises(RuntimeRefused,match='^ENGINE_QUEUE_DENIED$'): queue.admit('',score,PASSING,tests_passed=True,auditor_passed=True)


def test_vault_batch_is_sealed_counted_first_and_never_repeated(bridge):
    b,_=bridge;ledger=EngineLedger(b.store);queue=CandidateQueue(ledger)
    rows=synthetic_market(11,200);train,validation,vault=split_market_tiers(rows)
    assert (len(train),len(validation),len(vault))==(100,60,40) and vault[0]['session']==160 and vault[-1]['session']==199
    first,second,third=(f'cycle-0001-{uuid4().hex[:8]}:h{i}' for i in (1,2,3))
    for cid in (first,second,third): queue.admit(cid,{'beats_baseline':True},PASSING,tests_passed=True,auditor_passed=True)
    assert queue.queued()==[first,second,third] and ledger.looks()==[]
    for ids,note in (([first],''),([first],'x'*1025),([],'ok'),([first,first],'ok'),([first,'unknown'],'ok'),([f'c{i}' for i in range(17)],'ok')):
        with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'): queue.open_batch(ids,note)
    assert ledger.looks()==[] and queue.queued()==[first,second,third]
    look=queue.open_batch([first,second],'Owner OK: first vault batch (fixture note)')
    assert look['candidate_ids']==[first,second] and len(look['seal_sha256'])==64 and look['count_before_open']==1 and look['owner_note'].startswith('Owner OK')
    assert ledger.looks()==[look] and queue.state(first)==('LOOK_COUNTED',look['look_id']) and queue.queued()==[third]
    # The vault is read only through the callable, and only after the look exists and the candidate's state passes.
    reads=[]
    def read_vault():
        assert len(ledger.looks())>=1 and queue.state(reads_candidate[0])[0]=='LOOK_COUNTED'
        reads.append(1);return vault
    reads_candidate=[first]
    all_ones='session,position\n'+''.join(f"{r['session']},1\n" for r in vault)
    result=queue.evaluate_in_vault(look['look_id'],first,all_ones,read_vault)
    assert result['status']=='SCORED' and result['result']['sessions']==40 and result['result']['beats_baseline'] is False and len(reads)==1
    assert queue.state(first)==('VAULT_EVALUATED',look['look_id'])
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_REPEAT$'): queue.evaluate_in_vault(look['look_id'],first,all_ones,read_vault)
    assert len(reads)==1  # the repeat never read the vault
    # An invalid signals file still consumes the candidate's one look.
    reads_candidate[0]=second
    with pytest.raises(RuntimeRefused,match='^ENGINE_SIGNALS_INVALID$'): queue.evaluate_in_vault(look['look_id'],second,'session,position\n',read_vault)
    assert queue.state(second)==('VAULT_EVALUATED',look['look_id']) and ledger.queue_events(second)[-1]['status']=='INVALID' and len(reads)==2
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_REPEAT$'): queue.evaluate_in_vault(look['look_id'],second,all_ones,read_vault)
    # Candidates outside the look, unknown looks, a non-callable reader, and a queued candidate without a look all refuse without a read.
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'): queue.evaluate_in_vault(look['look_id'],third,all_ones,read_vault)
    with pytest.raises(RuntimeRefused,match='^ENGINE_LOOK_UNKNOWN$'): queue.evaluate_in_vault('look-nope',third,all_ones,read_vault)
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'): queue.evaluate_in_vault(look['look_id'],third,all_ones,vault)
    assert len(reads)==2
    # The look row and its LOOK_COUNTED events are one transaction: a duplicate look id leaves no partial rows.
    with pytest.raises(RuntimeRefused,match='^ENGINE_LOOK_DUPLICATE$'): ledger.record_look(look['look_id'],'f'*64,{},counted=[(third,{'look_id':look['look_id']})])
    assert queue.state(third)==('QUEUED',None) and len(ledger.looks())==1
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'): queue.open_batch([first],'again')
    second_look=queue.open_batch([third],'Owner OK: second batch');assert second_look['count_before_open']==2 and len(ledger.looks())==2
    events=[e['event'] for e in ledger.queue_events()];assert events.count('QUEUED')==3 and events.count('LOOK_COUNTED')==3 and events.count('VAULT_EVALUATED')==2
    assert [len(x) for x in split_market_tiers(rows,0.9,0.05)]==[180,10,10]
    for bad in ((0.5,0.5),(0.9,0.04),(0,0.3),(0.5,1)):
        with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'): split_market_tiers(rows,*bad)


def test_score_signals_carries_deflation_inputs():
    rows=synthetic_market(7,300,planted={'kind':'momentum','window':5,'strength':0.004});_,validation,_=split_market_tiers(rows)
    text='session,position\n'+''.join(f"{r['session']},{i%2}\n" for i,r in enumerate(validation))
    score=score_signals(text,validation);inputs=score['deflation_inputs']
    assert inputs['observations']==len(validation)-1 and inputs['sharpe_status']=='DEFINED' and set(inputs)=={'observations','sharpe_per_period','sharpe_status','skewness','kurtosis'}
    assert market_csv(validation).startswith('session,close,return\n')
    record=deflated_sharpe(inputs,1,trial_variance([],inputs)['trial_variance'])
    assert record['status'] in ('PASS','FAIL') and record['trials']==1 and record['section_10_family_size']==12
