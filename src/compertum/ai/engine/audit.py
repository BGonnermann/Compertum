"""The engine Auditor (section 15 and section 19), the fixed-part probe targets and the request-count invariant. Stage E6.

Deterministic code. The engine never changes it. The Auditor is the binding gate before a candidate leaves the sandbox:
automated tests (the frozen code reproduces its signals in a fresh sandbox job, and its positions before a perturbed tail
do not move when the tail changes) and integrity checks (the trial was counted before any run, the recorded score
recomputes from the signals, the deflation record is consistent, no run reached loopback or a denied path). Evidence
labels follow section 15: VERIFIED_PASS or VERIFIED_FAIL; an AI claim is never evidence.

Two kinds of failure. An integrity failure means the ledger and the Validator disagree, or a run touched what it must not:
the Auditor fails, the engine freezes (AUDITOR_FAILED), only the owner clears it. A candidate failure (not reproducible,
lookahead, a rerun refusal) is a defect of the candidate: it is recorded, the candidate is rejected, the run continues.

Lookahead. The job reads validation.csv with the return of every session, and the score pays position t with return t+1.
Code that reads return[t+1] scores perfectly and reproduces exactly. The perturbation check reruns the frozen code with the
last k rows' return and close changed, k in PERTURBATIONS; positions for sessions before the perturbed tail must equal the
original. A lookahead changes them; a rule that uses only past data does not.
"""
from decimal import Decimal,InvalidOperation
import hashlib
from pathlib import Path
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from .deflation import DSR_MIN
from .market import market_csv,parse_signals,score_signals

FIXED_FILES=('docs/BUILD_SPEC.md','AGENTS.md','config/default.toml','config/engine.toml','config/models.toml',
             'src/compertum/ai/engine/deflation.py','src/compertum/ai/engine/vault.py','src/compertum/ai/engine/limits.py',
             'src/compertum/ai/engine/run.py','src/compertum/ai/engine/cycle.py','src/compertum/ai/engine/audit.py',
             'src/compertum/ai/engine/market.py','src/compertum/ai/engine/ledger.py','src/compertum/ai/engine/execution.py',
             'src/compertum/runtime/sandbox.py')
STORE_FILE='state/research.sqlite'
SCORECARD_SCHEMA='synthetic-campaign-scorecard-v1'
INTEGRITY_CHECKS=('trial_counted','candidates_before_runs','score_recomputed','deflation_consistent','no_forbidden_access')
PERTURBATIONS=(1,4,8)


def engine_fixed_targets(project_root):
    """Real fixed parts that the sandbox probe must fail to read: the rules, the fixed configuration, the judge, the Auditor, the ledger code, the store."""
    root=Path(project_root).absolute()
    targets=[root/name for name in FIXED_FILES if (root/name).is_file()]
    if (root/STORE_FILE).is_file(): targets.append(root/STORE_FILE)
    return targets


def sha(text): return hashlib.sha256(text.encode('utf-8') if isinstance(text,str) else text).hexdigest()


def perturbed_rows(rows,k):
    """The validation rows with the last k rows changed: the return sign flipped, the close scaled. Sessions stay the same."""
    if type(k) is not int or not 1<=k<len(rows)-1: raise RuntimeRefused('ENGINE_AUDIT_DENIED')
    out=[dict(r) for r in rows]
    for index,row in enumerate(out[-k:]):
        row['return']=f"{-Decimal(row['return']):.8f}";row['close']=f"{Decimal(row['close'])*(Decimal('0.97')-Decimal(index)*Decimal('0.01')):.6f}"
    return out


def _rerun(sandbox,source,*,validation_csv=None):
    """A trusted rerun. ENGINE_FROZEN propagates (the engine froze); any other refusal is a candidate defect."""
    try: return sandbox.rerun_frozen(source['files'],source['entry'],purpose='audit',validation_csv=validation_csv),None
    except RuntimeRefused as error:
        if error.code=='ENGINE_FROZEN': raise
        return None,error.code


def deflation_consistent(deflation,total_trials):
    """The deflation record agrees with itself, the fixed minimum and the trial count. Its status must match its value: PASS at or above
    the minimum, FAIL below it, UNDEFINED with no value. Until 25 October 2026 this check demanded PASS, because only candidates at the gate
    were audited; the owner then decided that every candidate that beats buy-and-hold is audited, so a consistent FAIL is not an integrity fault."""
    try:
        status=deflation.get('status');value=deflation.get('deflated_sharpe')
        # deflated_sharpe() decides PASS or FAIL on the unrounded value and stores it rounded to 8 places, so an honest FAIL just below the
        # minimum can be stored as exactly 0.95000000 (review, 25 October 2026). Rounding never lifts a FAIL above the minimum.
        matches=((status=='PASS' and Decimal(value)>=DSR_MIN) or (status=='FAIL' and Decimal(value)<=DSR_MIN) or (status=='UNDEFINED' and value is None))
        return bool(matches and deflation.get('minimum')==str(DSR_MIN) and type(deflation.get('trials')) is int and 1<=deflation['trials']<=total_trials)
    except (InvalidOperation,TypeError,ValueError,AttributeError): return False


def audit_candidate(*,ledger,sandbox,cycle_id,candidate,score,deflation,validation_rows):
    """Audit one candidate that beat the baseline, at the deflation gate or below it (owner decision, 25 October 2026). Returns the audit record.

    record['integrity'] False means the engine must freeze. record['label'] is VERIFIED_PASS only when every check passed.
    """
    checks={};reasons=[];cid=candidate['candidate_id']
    # 1. The trial was counted.
    checks['trial_counted']=ledger.trial_exists(cid)
    # 2. The candidate list was recorded before the first run of the cycle.
    steps=ledger.steps(cycle_id);runs=ledger.runs(cycle_id)
    listed=[s['recorded_at'] for s in steps if s['kind']=='candidates' and s.get('phase')=='RECORDED']
    checks['candidates_before_runs']=bool(listed) and (not runs or all(listed[0]<=r['recorded_at'] for r in runs))
    # 3. The recorded score recomputes from the signals of the candidate's completed Engineer run.
    mine=[sandbox.record_for(r) for r in candidate.get('runs') or []]
    completed=[r for r in mine if r['purpose']=='engineer' and r['status']=='COMPLETED' and r.get('signals') is not None and r.get('files')]
    source=completed[-1] if completed else None
    try: checks['score_recomputed']=source is not None and canonical(score_signals(source['signals'],validation_rows))==canonical(score)
    except RuntimeRefused: checks['score_recomputed']=False
    # 4. The deflation record is consistent with itself, the fixed minimum and the trial count.
    checks['deflation_consistent']=deflation_consistent(deflation,ledger.total_trials())
    # 5. No run of this candidate reached loopback or a denied path.
    checks['no_forbidden_access']=bool(mine) and all(r['status'] not in ('FROZEN','FORBIDDEN_ACCESS') and not ((r.get('watcher') or {}).get('loopback_connections')) for r in mine)
    integrity=all(checks[name] for name in INTEGRITY_CHECKS)
    reasons.extend(f'integrity: {name}' for name in INTEGRITY_CHECKS if not checks[name])
    record={'candidate_id':cid,'checks':checks,'integrity':integrity,'source_run_id':source['run_id'] if source else None,'frozen_sha256':None,
            'rerun_id':None,'rerun_status':None,'perturbations':[]}
    if not integrity:
        record.update(label='VERIFIED_FAIL',reasons=reasons);return record
    # 6. Automated test: the frozen code reproduces its signals in a fresh sandbox job on the same TRAIN and VALIDATION.
    record['frozen_sha256']=sha(source['signals'])
    rerun,refused=_rerun(sandbox,source)
    if rerun is None:
        checks['reproducible']=False;reasons.append(f'candidate: rerun refused {refused}')
    else:
        record.update(rerun_id=rerun['run_id'],rerun_status=rerun['status'])
        checks['reproducible']=rerun['status']=='COMPLETED' and rerun.get('signals') is not None and sha(rerun['signals'])==record['frozen_sha256']
        if not checks['reproducible']: reasons.append('candidate: signals not reproduced by the frozen code')
    # 7. Automated test: no lookahead. Positions before a perturbed tail must not move when the tail changes.
    checks['no_lookahead']=checks['reproducible']
    if checks['reproducible']:
        original=parse_signals(source['signals'],validation_rows);n=len(validation_rows)
        for k in PERTURBATIONS:
            rows=perturbed_rows(validation_rows,k);rerun,refused=_rerun(sandbox,source,validation_csv=market_csv(rows))
            entry={'k':k,'rerun_id':rerun['run_id'] if rerun else None,'status':rerun['status'] if rerun else f'REFUSED_{refused}','prefix_equal':False}
            if rerun is not None and rerun['status']=='COMPLETED' and rerun.get('signals') is not None:
                try: entry['prefix_equal']=parse_signals(rerun['signals'],rows)[:n-k]==original[:n-k]
                except RuntimeRefused: entry['prefix_equal']=False
            record['perturbations'].append(entry)
            if not entry['prefix_equal']: checks['no_lookahead']=False;reasons.append(f'candidate: positions before the perturbed tail changed (k={k})');break
    record.update(label='VERIFIED_PASS' if checks['reproducible'] and checks['no_lookahead'] else 'VERIFIED_FAIL',reasons=reasons)
    return record


def register_scorecard_trials(ledger,source,scorecard):
    """Count the fixed family of a registered campaign scorecard as trials, once per source."""
    if (not isinstance(scorecard,dict) or scorecard.get('schema')!=SCORECARD_SCHEMA or type(scorecard.get('family_size')) is not int
            or scorecard['family_size']<1 or not isinstance(scorecard.get('registered_family'),list) or len(scorecard['registered_family'])!=scorecard['family_size']):
        raise RuntimeRefused('ENGINE_SCORECARD_DENIED')
    return ledger.record_external_trials(source,scorecard['family_size'],{'schema':scorecard['schema'],'scorecard_sha256':sha(canonical(scorecard))})


def check_request_invariant(ledger,run_id,requests,request_limit):
    """A request count above the run limit means the limiter failed. The engine freezes; only the owner clears it."""
    if type(requests) is not int or type(request_limit) is not int: raise RuntimeRefused('ENGINE_RECORD_DENIED')
    if requests>request_limit:
        ledger.freeze('REQUEST_LIMIT_EXCEEDED',{'run_id':run_id,'requests':requests,'request_limit':request_limit});return False
    return True
