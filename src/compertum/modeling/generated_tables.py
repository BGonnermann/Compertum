"""Lossless tables at fixed generated-batch evidence paths; no audit authority."""
import hashlib,json
from compertum.data.encoding import canonical
from compertum.data.errors import DataError

ENCODING='generated-record-tables-v1'
MAX_ENCODED=16*1024**2
MAX_EXPANDED=32*1024**2
MAX_RECORDS=200000
SCHEMAS={
 'fit_rows':'symbol feature_session decision_at entry_at label_end_at simulated_feature_available_at simulated_label_available_at simulated_revision_available_at label_revision_id features target',
 'fit_omissions':'symbol decision_at reasons',
 'provenance':'symbol decision_at feature_sha256 label_sha256 entry_revision_id exit_revision_id split_action_ids selected_label_revision_id label_available_at',
 'included':'index symbol decision_at row_sha256 label_revision_id revision_available_at',
 'excluded':'index symbol decision_at row_sha256 label_revision_id revision_available_at reasons',
 'predictions':'session symbol decision_at entry_at exit_at label_available_at entry_revision exit_revision split_actions prediction momentum_prediction target signed_error features feature_sha256',
 'omissions':'session symbol reason',
 'daily_rank':'session observations spearman status',
 'trades':'session at symbol side quantity reference fill_price fee price_cost turnover analytic_terminal fill_assumption',
 'observations':'session phase nav daily_loss drawdown',
 'days':'session nav cash receivables positions basis',
 'signals':'session decision_at predictions',
 'qualification_predictions':'session symbol prediction momentum target',
 'intervals':'symbol entry exit',
 'policy_intervals':'symbol start_index end_index start_session end_session',
}
COLUMNS={key:tuple(sorted(value.split())) for key,value in SCHEMAS.items()}


def _require(ok):
    if not ok:raise DataError('GENERATED_TABLE_INVALID')


def _table(rows,kind):
    columns=COLUMNS[kind]
    _require(type(rows) is list and len(rows)<=12288)
    _require(all(type(row) is dict and set(row)==set(columns) for row in rows))
    return dict(columns=list(columns),rows=[[row[c] for c in columns] for row in rows])


def _records(table,kind,budget):
    columns=COLUMNS[kind]
    _require(type(table) is dict and set(table)=={'columns','rows'} and type(table['columns']) is list and table['columns']==list(columns))
    values=table['rows'];_require(type(values) is list and len(values)<=12288)
    budget[0]+=len(values);_require(budget[0]<=MAX_RECORDS)
    rows=[]
    for values_row in values:
        _require(type(values_row) is list and len(values_row)==len(columns))
        row=dict(zip(columns,values_row))
        budget[1]+=len(canonical(row))+1;_require(budget[1]<=MAX_EXPANDED)
        rows.append(row)
    return rows


def _paths(value):
    """Only declared lists are tables; tags cannot redirect arbitrary decoding."""
    _require(type(value) is dict and value.get('schema')=='generated-final-batch-v1')
    fits=value['fits'];candidates=value['candidates']
    _require(type(fits) is list and len(fits)<=6 and type(candidates) is list and 1<=len(candidates)<=3)
    for fit in fits:
        for field,kind in [('rows','fit_rows'),('omissions','fit_omissions'),('provenance','provenance')]:yield fit,field,kind
        for kind in ('included','excluded'):yield fit['manifest'],kind,kind
    for candidate in candidates:
        folds=candidate['folds'];_require(type(folds) is list and len(folds)==2)
        for fold in folds:
            pred=fold['predictions']
            for field,kind in [('rows','predictions'),('omissions','omissions'),('daily_rank_correlation','daily_rank')]:yield pred,field,kind
            _require(set(fold['replays'])==set(fold['checks'])=={'10','20'})
            for cost in ('10','20'):
                portfolios=fold['replays'][cost]['portfolios'];_require(set(portfolios)=={'strategy','spy60','spy100','equal60','zero'})
                for book in portfolios.values():
                    for field in ('trades','observations','days','signals','omissions'):yield book,field,field
                yield fold['checks'][cost]['policy'],'holding_intervals','policy_intervals'
        inputs=candidate['qualification']['inputs']
        yield inputs,'predictions','qualification_predictions'
        yield inputs,'intervals','intervals'


def pack_final(value):
    raw=canonical(value);_require(len(raw)<=MAX_EXPANDED)
    compact=json.loads(raw)
    count=0
    for parent,key,kind in _paths(compact):
        table=_table(parent[key],kind);count+=len(table['rows']);_require(count<=MAX_RECORDS)
        parent[key]=table
    compact['encoding']=ENCODING;compact['expanded_sha256']=hashlib.sha256(raw).hexdigest()
    result=canonical(compact)
    if len(result)>MAX_ENCODED:raise DataError('OUTPUT_BOUND')
    return result


def read_final(raw,*,expected_sha256):
    """Verify representation/hash only, not source, owner, math or admission."""
    _require(type(raw) is bytes and 0<len(raw)<=MAX_ENCODED and hashlib.sha256(raw).hexdigest()==expected_sha256)
    try:
        value=json.loads(raw);_require(type(value) is dict and canonical(value)==raw)
        _require(value.pop('encoding')==ENCODING);expanded_sha=value.pop('expanded_sha256')
        budget=[0,0]
        for parent,key,kind in _paths(value):parent[key]=_records(parent[key],kind,budget)
        expanded=canonical(value)
        _require(len(expanded)<=MAX_EXPANDED and hashlib.sha256(expanded).hexdigest()==expanded_sha)
        return value
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('GENERATED_TABLE_INVALID') from None
