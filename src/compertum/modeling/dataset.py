"""Validated synthetic snapshots to causal model rows and explicit omissions."""
from dataclasses import dataclass
import hashlib
from compertum.data.calendar import session_times
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.market import load_market,WATCHLIST
from compertum.simulation.prediction import _label
from compertum.simulation.policy import fixed_decimal
from .features import feature_vector
from .registry import FEATURES
from .ridge import FitRows,freeze_rows

@dataclass(frozen=True)
class DatasetAssembly:
    content:bytes
    sha256:str
    rows:FitRows|None


@fixed_decimal
def assemble_training_rows(chunks,sectors,start,end,horizon):
    """Synthetic engineering only; future labels retain their admission times."""
    if type(horizon) is not int or horizon not in (1,5,21):raise DataError('INVALID_HORIZON')
    session_times(start);session_times(end)
    if not '2016-01-01'<=start<=end<'2024-01-01':raise DataError('DEVELOPMENT_ROWS_ONLY')
    dates=[start]
    while dates[-1]!=end:
        if len(dates)>=1024:raise DataError('INPUT_BOUND')
        dates.append(session_times(dates[-1]).next_date)
    # This reader admits validated synthetic Snapshot objects only; provider
    # evidence has a separate type/reader and must never be relabeled here.
    market=load_market(chunks,sectors)
    rows=[];omissions=[];provenance=[]
    for day in dates:
        t=session_times(day);exit_day=day
        for _ in range(horizon):exit_day=session_times(exit_day).next_date
        pending=[];day_omissions=[];bad_labels=[]
        for symbol in WATCHLIST:
            identity={'symbol':symbol,'decision_at':t.decision.isoformat()}
            if symbol not in market.symbols:
                day_omissions.append(dict(identity,reasons=['MISSING_SYMBOL']));continue
            try:features=feature_vector(market,symbol,day)
            except DataError as exc:
                day_omissions.append(dict(identity,reasons=[exc.code]));continue
            if not features.raw_eligible:
                day_omissions.append(dict(identity,reasons=['INELIGIBLE_RAW_PRICE_OR_VOLUME']));continue
            if exit_day>='2024-01-01':label=None;reason='LABEL_OUTSIDE_DEVELOPMENT'
            else:
                try:label,reason=_label(market,symbol,day,exit_day)
                except DataError as exc:label=None;reason=exc.code
            if reason is not None:
                bad_labels.append(reason);day_omissions.append(dict(identity,reasons=[reason,'SAME_DATE_LABEL_PURGE']));continue
            entry=market.rows[(symbol,day,'entry')];exit_row=market.rows[(symbol,exit_day,'entry')]
            splits=[a for a in market.actions if a['action_id'] in label['split_actions']]
            label_digest=hashlib.sha256(canonical({'entry':entry,'exit':exit_row,'splits':splits,'horizon':horizon})).hexdigest()
            revision='label-'+label_digest;available=label['available'].isoformat()
            row=dict(identity,feature_session=features.feature_session,entry_at=t.entry.isoformat(),label_end_at=session_times(exit_day).entry.isoformat(),
                     simulated_feature_available_at=features.available_at,simulated_label_available_at=available,simulated_revision_available_at=available,
                     label_revision_id=revision,features=features.values,target=float(label['target']))
            source=dict(identity,feature_sha256=features.input_sha256,label_sha256=label_digest,entry_revision_id=label['entry_revision'],exit_revision_id=label['exit_revision'],
                        split_action_ids=label['split_actions'],selected_label_revision_id=revision,label_available_at=available)
            pending.append((row,source))
        if bad_labels:
            reasons=sorted(set(bad_labels)|{'SAME_DATE_LABEL_PURGE'})
            for row,_ in pending:day_omissions.append({'symbol':row['symbol'],'decision_at':row['decision_at'],'reasons':reasons})
        else:
            rows.extend(row for row,_ in pending);provenance.extend(source for _,source in pending)
        omissions.extend(day_omissions)
    rows.sort(key=lambda r:(r['decision_at'],r['symbol']));provenance.sort(key=lambda r:(r['decision_at'],r['symbol']));omissions.sort(key=lambda r:(r['decision_at'],r['symbol']))
    bundle=freeze_rows(rows,horizon=horizon,feature_names=FEATURES) if rows else None
    expected=len(dates)*len(WATCHLIST)
    if len(rows)+len(omissions)!=expected:raise DataError('COVERAGE_ACCOUNTING')
    report={'schema':'synthetic-dataset-assembly-v1','status':'SYNTHETIC_ENGINEERING','financial_accepted':False,'full_M2':False,'horizon':horizon,'start':start,'end':end,
            'source_market_sha256':market.sha256,'feature_order':FEATURES,'frozen_universe':WATCHLIST,'present_universe':[s for s in market.symbols if s!='SPY'],
            'expected_rows':expected,'assembled_rows':len(rows),'omissions':omissions,'row_provenance':provenance,'fit_rows_sha256':bundle.sha256 if bundle else None,
            'availability_basis':'SIMULATED_AVAILABILITY'}
    raw=canonical(report)
    if len(raw)>8*1024**2:raise DataError('OUTPUT_BOUND')
    return DatasetAssembly(raw,hashlib.sha256(raw).hexdigest(),bundle)
