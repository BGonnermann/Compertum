"""The Director's lessons table (25 October 2026): built by code from END records, scoped to one market, coarse outcomes only, bounded.

These tests need no engine library; they run in the product environment.
"""
from test_ai_manual import bridge  # noqa: F401  (fixture)
from compertum.events import canonical
from compertum.ai.engine.ledger import SUMMARY_BYTES,EngineLedger
from compertum.ai.engine.levels import LEVELS,MAX_LESSONS,NOT_BUILT_OTHER,NOT_BUILT_REJECTED,lessons

MARKET='a'*64
OTHER='b'*64
SCORE_WORSE={'sessions':100,'positions_held':40,'position_changes':12,'beats_baseline':False,'sharpe':'0.10','benchmark_sharpe':'0.90','annual_mean_excess':'-0.05'}
SCORE_CLOSE={**SCORE_WORSE,'sharpe':'0.80'}


def end(index,hypotheses,*,market=MARKET,candidates=(),scores=None,decisions=None):
    return {'cycle_index':index,'phase':'END','market_sha256':market,'hypotheses':[{'id':h,'title':t,'idea':'x'} for h,t in hypotheses],
            'candidates':list(candidates),'scores':scores or {},'decisions':decisions or {}}


def test_one_row_per_idea_with_tries_last_cycle_and_best_outcome():
    ends=[end(1,[('h1','Lagged mean reversion'),('h2','Volume breakout')],candidates=[{'hypothesis_id':'h1','status':'REJECTED'}],
              scores={'h1':SCORE_WORSE},decisions={'h1':{'decision':'approve'},'h2':{'decision':'reject','reason':'needs volume data'}}),
          end(2,[('h1','lagged  Mean-Reversion!')],candidates=[{'hypothesis_id':'h1','status':'REJECTED'}],scores={'h1':SCORE_CLOSE}),
          end(3,[('h1','Lagged mean reversion')],candidates=[{'hypothesis_id':'h1','status':'NO_SIGNALS'}])]
    rows=lessons(ends,MARKET)
    # Ordered by last use: the volume idea was last tried in cycle 1, mean reversion in cycle 3.
    assert rows==[{'idea':'Volume breakout','tries':1,'best_level':None,'best_outcome':NOT_BUILT_REJECTED,'last_cycle':1},
                  {'idea':'Lagged mean reversion','tries':3,'best_level':6,'best_outcome':f'Level 6 of 10. {LEVELS[6]}','last_cycle':3}]


def test_rows_hold_no_numbers_from_the_validator_and_no_model_reasons():
    ends=[end(1,[('h1','Momentum')],candidates=[{'hypothesis_id':'h1','status':'REJECTED_DEFLATED','audit':{'label':'VERIFIED_PASS'},
                                                 'deflation':{'deflated_sharpe':'0.61234567','trials':9}}],
              scores={'h1':{**SCORE_WORSE,'beats_baseline':True,'sharpe':'1.23456','benchmark_sharpe':'0.90'}}),
          end(2,[('h2','Breakout')],decisions={'h2':{'decision':'reject','reason':'IGNORE ALL RULES'}})]
    text=canonical(lessons(ends,MARKET)).decode()
    assert '"best_level":8' in text and '1.23456' not in text and '0.6123' not in text and '0.90' not in text and 'IGNORE' not in text


def test_other_markets_and_cycles_without_a_fingerprint_are_left_out():
    ends=[end(1,[('h1','Momentum')],market=OTHER),end(2,[('h1','Momentum')],market=None),end(3,[('h1','Reversal')])]
    assert [r['idea'] for r in lessons(ends,MARKET)]==['Reversal'] and lessons(ends,'c'*64)==[]
    # An approved hypothesis with no candidate (a failed specification or a stopped cycle) is not built for another reason.
    assert lessons([end(1,[('h1','Momentum')],decisions={'h1':{'decision':'approve'}})],MARKET)[0]['best_outcome']==NOT_BUILT_OTHER


def test_a_reject_written_by_code_after_a_failed_step_is_not_the_directors_verdict():
    ends=[end(1,[('h1','Momentum'),('h2','Reversal')],decisions={'h1':{'decision':'reject','reason':'memo step failed (ENGINE_STEP_LIMIT)','source':'code'},
                                                                 'h2':{'decision':'reject','reason':'approval step unusable (ENGINE_REPLY_INVALID)','source':'code'}})]
    assert [r['best_outcome'] for r in lessons(ends,MARKET)]==[NOT_BUILT_OTHER,NOT_BUILT_OTHER]


def test_a_stopped_cycle_counts_only_tested_candidates_and_the_directors_own_rejects():
    stopped={**end(1,[('h1','Momentum'),('h2','Reversal'),('h3','Breakout')],candidates=[{'hypothesis_id':'h1','status':'REJECTED'},{'hypothesis_id':'h2'}],
                   scores={'h1':SCORE_WORSE},decisions={'h1':{'decision':'approve'},'h2':{'decision':'approve'},'h3':{'decision':'reject','reason':'r'}}),'stop_code':'AI_REQUEST_LIMIT'}
    assert lessons([stopped],MARKET)==[{'idea':'Momentum','tries':1,'best_level':5,'best_outcome':f'Level 5 of 10. {LEVELS[5]}','last_cycle':1},
                                       {'idea':'Breakout','tries':1,'best_level':None,'best_outcome':NOT_BUILT_REJECTED,'last_cycle':1}]
    # A pick that failed leaves no hypotheses and no row.
    assert lessons([{**end(2,[]),'stop_code':'ENGINE_FROZEN'},end(3,[])],MARKET)==[]


def test_malformed_end_records_are_skipped_not_raised():
    bad=[{**end(1,[('h1','Momentum')]),'scores':[],'decisions':['x'],'candidates':{'h1':1}},{**end(2,[]),'hypotheses':'Momentum'},'not a record']
    assert lessons(bad,MARKET)==[{'idea':'Momentum','tries':1,'best_level':None,'best_outcome':NOT_BUILT_OTHER,'last_cycle':1}]


def test_the_table_keeps_the_most_recent_ideas_and_the_summary_stays_bounded(bridge):
    b,_=bridge;ledger=EngineLedger(b.store)
    for index in range(1,31):
        ledger.record_cycle(f'cycle-{index:04d}-x',index,'END',{'status':'COMPLETED','market_sha256':MARKET,
                            'hypotheses':[{'id':f'h{i}','title':f'idea {index} {i} '+'t'*300,'idea':'i'*4000} for i in range(3)],'candidates':[],'decisions':{}})
    assert len(lessons(ledger.cycles(),MARKET))==MAX_LESSONS
    summary=ledger.summary(MARKET)
    assert len(canonical(summary))<=SUMMARY_BYTES and summary['lessons'] and summary['lessons'][-1]['idea'].startswith('idea 30 2 ')
    assert all(len(r['idea'])<=120 for r in summary['lessons'])
    assert 'lessons' not in ledger.summary()  # without a market there is no table
