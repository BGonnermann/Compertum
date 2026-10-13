"""Immutable synthetic protocol: hashes bind inputs, never authorize data access."""
from dataclasses import dataclass
import hashlib
import json
import re
from uuid import UUID
from .data.encoding import canonical
from .data.errors import DataError

MAX_PROTOCOL_BYTES = 24 * 1024

@dataclass(frozen=True)
class SyntheticProtocol:
    content: bytes
    sha256: str


def digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise DataError('PROTOCOL_PIN_INVALID')
    return value


def identifier(value):
    try:
        if type(value) is not str or str(UUID(value)) != value or UUID(value).int == 0:
            raise ValueError()
    except (ValueError, AttributeError):
        raise DataError('PROTOCOL_ID_INVALID') from None
    return value


def identity(value):
    if type(value) is not dict or set(value) != {'package_sha256','lock_sha256','python','distributions'}:
        raise DataError('PROTOCOL_ENVIRONMENT_INVALID')
    digest(value['package_sha256']); digest(value['lock_sha256'])
    if value['python'] != '3.14.7': raise DataError('PROTOCOL_ENVIRONMENT_INVALID')
    versions = value['distributions']
    if type(versions) not in (tuple,list) or not 1 <= len(versions) <= 256:
        raise DataError('PROTOCOL_ENVIRONMENT_INVALID')
    normalized = []; names = set()
    for pair in versions:
        if type(pair) not in (tuple,list) or len(pair) != 2 or any(type(x) is not str or re.fullmatch('[A-Za-z0-9_.+!-]{1,96}', x) is None for x in pair):
            raise DataError('PROTOCOL_ENVIRONMENT_INVALID')
        name = re.sub('[-_.]+','-',pair[0]).lower()
        if name in names: raise DataError('PROTOCOL_ENVIRONMENT_INVALID')
        names.add(name); normalized.append(list(pair))
    if normalized != sorted(normalized): raise DataError('PROTOCOL_ENVIRONMENT_INVALID')
    return {**value,'distributions':normalized}


def fixed_definition():
    """Return a fresh stdlib-only contract; engine agreement is tested separately."""
    features = ['return_1','return_5','return_21','return_63','volatility_20','volatility_63',
        'price_mean_20','price_mean_63','volume_mean_20','spy_return_1','spy_return_5',
        'spy_return_21','spy_return_63','spy_volatility_20','spy_volatility_63']
    variants = [dict(candidate_id=f'momentum-h{h:02}',kind='momentum',horizon=h,alpha=None) for h in (1,5,21)]
    variants += [dict(candidate_id=f'ridge-h{h:02}-a{a:03}',kind='ridge',horizon=h,alpha=a) for h in (1,5,21) for a in (1,10,100)]
    return {
        'universe':['AAPL','MSFT','AMZN','GOOGL','META','NVDA','JPM','XOM','JNJ','PG','UNH','HD'],
        'benchmark_symbol':'SPY','universe_claim':'FIXED_PRESENT_DAY_WATCHLIST_NOT_SURVIVORSHIP_FREE',
        'features':features,'feature_formulas':{'returns':'SIMPLE_SPLIT_CONSISTENT','volatility':'SAMPLE_DDOF_1_TIMES_SQRT_252',
            'price_mean':'PRICE_DIV_TRAILING_MEAN_MINUS_1','volume_mean':'VOLUME_DIV_TRAILING_MEAN_NO_SUBTRACTION','version':'causal-features-v1'},'registered_family':variants,'family_size':12,
        'seeds':{'campaign':1729,'model':1730,'bootstrap':1731,'counterexample':1732},
        'models':{'momentum':'H * prior_21_session_return / 21','zero_prediction_baseline':True,
            'feature_missing':'NO_PREDICTION','winsorization':False,'row_weights':'EQUAL','dtype':'float64','rng_state':'NO_RANDOM_DRAWS_SVD_DETERMINISTIC',
            'standard_scaler':{'copy':True,'with_mean':True,'with_std':True},
            'ridge':[{'alpha':a,'copy_X':True,'fit_intercept':True,'max_iter':None,'positive':False,
                'random_state':None,'solver':'svd','tol':0.0001} for a in (1,10,100)]},
        'data':{'profile':'SYNTHETIC_FIXTURES_ONLY','provider':'synthetic','feed':'iex','daily_basis':'PROVIDER_DAILY','real_protected_access':False,
            'availability':'EXPLICIT_SYNTHETIC_SIMULATED_FIELDS','feature_warmup_sessions':252,
            'daily_availability':'NEXT_SESSION_09:25_OR_LATER','minute_availability':'MINUTE_END_PLUS_15_MINUTES_OR_LATER',
            'label_availability':'SESSION_AFTER_EXIT_09:25_OR_LATER','labels':'SPLIT_CONSISTENT_PRICE_RETURN_EXCLUDING_DIVIDENDS',
            'missing':'NO_FILL_OR_IMPUTATION','eligibility_raw_close_minimum':'5','eligibility_raw_mean20_dollar_volume_minimum':'1000000',
            'feature_basis':'CAUSAL_SPLIT_ADJUSTED_WITH_RAW_ELIGIBILITY','revision':'FROZEN_LATEST_ADMITTED_BY_FIT_CUTOFF_LATER_CORRECTIONS_IMMUTABLE',
            'unresolved_action_mapping_input':'INELIGIBLE','substitutions':False,'coverage_denominator':'FROZEN_UNIVERSE_CALENDAR_LISTING_LIFECYCLE','daily_coverage_minimum':'0.995','selected_references_and_held_actions_coverage':'1'},
        'time':{'zone':'America/New_York','calendar':'XNYS_PINNED_BY_MANIFEST','features':'PRIOR_SESSION',
            'decision':'09:25:00','entry_exit':'09:35:00','submission_end':'09:35:59','late_submission':'SKIPPED_WINDOW_EXPIRED',
            'horizons_sessions':[1,5,21],'cadence':'FIRST_ELIGIBLE_DECISION_THEN_EVERY_H_PER_SEGMENT',
            'full_interval_within_segment':True,'terminal_exit_costs':True,'mark':'LAST_REGULAR_SESSION_1MIN_CLOSE',
            'score_finalization':'NEXT_SESSION_09:25_OR_LATER_COMPLETE_RECONCILIATION'},
        'fits':{'cutoff':'FIRST_EXCHANGE_SESSION_OF_YEAR_07:00_NEW_YORK','activation_deadline':'09:25:00',
            'activation':'IMMUTABLE_FIT_PLUS_DETERMINISTIC_AUDIT_AND_OWNER_APPROVAL',
            'training':'EXPANDING_FROM_2016','standardization':'TRAINING_ONLY','split':'SAME_DATE_ALL_ASSETS',
            'purge':'UNAVAILABLE_FEATURE_LABEL_REVISION_OR_INTERVAL_OVERLAP_PURGE_WHOLE_DECISION_DATE',
            'development':[{'training_start':'2016-01-01','training_end':f'{y-1}-12-31','evaluation_start':f'{y}-01-01','evaluation_end':f'{y}-12-31'} for y in (2021,2022,2023)],
            'fixture_coverage':'PARTIAL_FOLDS_REMAIN_DIAGNOSTIC','final_annual_years':[2024,2025],
            'protected_feedback':'NONE_BETWEEN_ANNUAL_FITS'},
        'portfolio':{'initial_nav':'10000','maximum_names':3,'target_name_weight':'0.20','gross_cap':'0.60','cash_minimum':'0.40',
            'sector_cap':'0.40','signal_threshold':'ROUNDTRIP_PRICE_COST_PLUS_0.001','ranking':'PREDICTION_DESC_THEN_SYMBOL_ASC',
            'quantity':'WHOLE_SHARES_FLOOR','buy_buffer':'0.01','reductions_before_buys':True,'skip_ineligible_then_next':True,
            'cost_bps_per_side':[10,20],'financing':'0','cash_interest':'0','fees':'SYNTHETIC_ZERO_ONLY_UNQUALIFIED_FOR_REAL_BILLING',
            'benchmark':'60_PERCENT_SPY_40_PERCENT_CASH_SAME_H_COSTS_ACTIONS','diagnostics':['FULL_SPY','60_PERCENT_GROSS_EQUAL_WEIGHT'],
            'nav':'CASH_PLUS_MARKED_SHARES_PLUS_UNPAID_DIVIDEND_RECEIVABLES_MINUS_UNDEBITED_FEES',
            'splits':'ADJUST_QUANTITY_AND_BASIS','dividends':'ACCRUE_EX_DATE_PAY_TO_CASH_WITHOUT_DOUBLE_COUNT',
            'external_flows':'INVALIDATE_SCORED_RETURN','daily_loss_halt':'0.02','risk_drawdown_halt':'0.10',
            'historical_risk_observations':['POST_FILL_09:35','REGULAR_CLOSE'],'boundary_epsilon':'1e-10'},
        'metrics':{'daily_return':'NAV_T_DIV_NAV_PREVIOUS_MINUS_1','annual_sessions':252,'std_ddof':1,
            'sharpe':'SQRT_252_MEAN_RETURN_DIV_SAMPLE_STD_ZERO_RISK_FREE','zero_variance':'UNDEFINED',
            'cagr':'NAV_END_DIV_NAV_INITIAL_POWER_252_DIV_N_MINUS_1','excess':'252_MEAN_STRATEGY_MINUS_BENCHMARK',
            'drawdown':'1_MINUS_NAV_DIV_RUNNING_PEAK_INCLUDING_INITIAL','cash_sessions':'INCLUDED',
            'predictive':['MSE','MAE','SIGNED_ERROR','PER_DATE_RANK_CORRELATION','COVERAGE'],
            'ridge_mse_improvement_minimum':'0.01','zero_baseline_mse':'UNDEFINED_CANNOT_PASS','ml_gate_separate':True},
        'selection':{'maximum_per_horizon':1,'maximum_total':3,'ranking_cost_bps':10,'ranking':['CONCATENATED_DEVELOPMENT_DAILY_EXCESS_DESC','TURNOVER_ASC','MOMENTUM_FIRST','CANDIDATE_ID_ASC'],
            'gates':['REPRODUCIBILITY','MATH','RISK','INDEPENDENT_DEVELOPMENT_AUDIT'],'retain_all_trials':12,
            'failed_candidates':'RETAINED_NOT_PROMOTED','batch_final':True},
        'qualification':{'historical_start':'2024-01-01','historical_end':'2025-12-31','reserved_years':[2026],'historical_segments':'CALENDAR_YEARS','forward_segments':'ONE_CONTINUOUS_252_SESSION_WINDOW',
            'historical_minimum_sessions':400,'minimum_checkpoints':12,'minimum_completed_intervals':30,
            'annual_mean_excess_minimum':'0.02','sharpe_minimum':'0.75','sharpe_predicate':'POSITIVE_VARIANCE_NONNEGATIVE_MEAN_252_MEAN_SQUARED_GE_0.75_SQUARED_SAMPLE_VARIANCE','drawdown_maximum':'0.15',
            'historical_period_excess':'NONNEGATIVE_EACH_FULL_CALENDAR_YEAR','stress_excess_minimum':'0','stress_drawdown_maximum':'0.20',
            'external_gates':['DATA','TIMING','RISK','REPRODUCIBILITY','INDEPENDENT_AUDIT'],
            'bootstrap':{'draws':10000,'block_sessions':21,'seed':1731,'family_size':12,'rng':'numpy.random.Generator(PCG64)','integer_dtype':'int64',
                'block_starts':'INDEPENDENT_UNIFORM_INTEGER_0_INCLUSIVE_N_EXCLUSIVE','indices':'CIRCULAR_CEIL_N_DIV_21_BLOCKS_TRUNCATE_N',
                'paired':True,'statistic':'MEAN_DAILY_EXCESS','lower_quantile':'0.05/12','method':'linear',
                'required_bound':'STRICTLY_POSITIVE','retain_indices_and_version':True,'index_storage':'LOSSLESS_UINT16_LE_ROW_MAJOR_BLOCK_STARTS_PLUS_SHAPE_HASH_EXPANSION','coverage':'APPROXIMATE'},
            'forward':{'sessions':252,'halves':[126,126],'period_excess':'NONNEGATIVE_EACH_HALF','same_other_thresholds':True,
                'start':'AFTER_LOCK_AND_OWNER_APPROVAL','all_horizons_same_dates':True,'partial_result_switching':False,
                'policy_change':'RESTART_PROSPECTIVE_QUALIFICATION','scheduled_approved_fit':'UNCHANGED_POLICY_DOES_NOT_RESET_WINDOW'}},
        'numeric':{'atol':'1e-10','rtol':'1e-8','daily_portfolio_return_atol':'1e-8','decimal_precision':28,
            'exact':['HASHES','INPUT_ROWS','SPLITS','ORDER_INTENT_IDS','TRADE_DECISIONS','INTEGER_QUANTITIES'],
            'fit_serve_atol':'1e-12','fit_serve_rtol':'1e-12','decimal_rounding':'ROUND_HALF_EVEN','dollar_reporting':'ROUND_HALF_UP_CENTS','ordering':'STABLE_SYMBOL_TIME'},
        'lifecycle':{'seal_before_development':True,'freeze_before_final':True,'consume_before_read':True,
            'repeated_final':'SAME_ID_MATCHING_RECOVERABLE_CHECKPOINT_ONLY','missing_guard':'COMPROMISED',
            'rule_or_input_change':'NEW_IDENTITY_UNTOUCHED_FUTURE_EVIDENCE','financial_authority':False}}


def build_protocol(*, development_run_id, development_sha256, data_manifest_sha256, holdout_manifest_sha256, runtime, clean_pair=None):
    value = {'schema':'synthetic-protocol-v1','financial_accepted':False,'paper_authorized':False,'strategy_accepted':False,'full_M3':False,'status':'SYNTHETIC_ENGINEERING',
        'development_run_id':identifier(development_run_id),'development_sha256':digest(development_sha256),
        'data_manifest_sha256':digest(data_manifest_sha256),'holdout_manifest_sha256':digest(holdout_manifest_sha256),
        'runtime':identity(runtime),'definition':fixed_definition()}
    if clean_pair is not None:
        from .clean_pair import read_pair
        try:
            if type(clean_pair) is not dict or set(clean_pair)!={'record','sha256','lane'} or clean_pair['lane'] not in {'source','wheel'}:raise ValueError()
            pair=read_pair(canonical(clean_pair['record']),expected_sha256=clean_pair['sha256'])
            if (pair[clean_pair['lane']]['run_id']!=value['development_run_id']
                    or any(canonical(pair[k])!=canonical(value[k]) for k in ('data_manifest_sha256','holdout_manifest_sha256','runtime'))):raise ValueError()
        except (ValueError,TypeError,KeyError):raise DataError('PROTOCOL_CLEAN_PAIR_INVALID') from None
        value.update(schema='synthetic-protocol-v2',clean_pair=clean_pair)
    raw = canonical(value)
    if len(raw) > MAX_PROTOCOL_BYTES: raise DataError('PROTOCOL_BOUND')
    return SyntheticProtocol(raw,hashlib.sha256(raw).hexdigest())


def read_protocol(raw, *, expected_sha256):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PROTOCOL_BYTES: raise DataError('PROTOCOL_BOUND')
    if hashlib.sha256(raw).hexdigest() != digest(expected_sha256): raise DataError('PROTOCOL_HASH_MISMATCH')
    try:
        value = json.loads(raw)
        expected = build_protocol(**{k:value[k] for k in ('development_run_id','development_sha256','data_manifest_sha256','holdout_manifest_sha256','runtime')},clean_pair=value.get('clean_pair'))
        if expected.content != raw: raise DataError('PROTOCOL_DEFINITION_CHANGED')
        return value
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError) as error:
        if isinstance(error,DataError): raise
        raise DataError('PROTOCOL_INVALID') from None
