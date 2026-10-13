"""Versioned closed synthetic recipes. Old journal bytes remain replayable."""
import hashlib
from .data.encoding import canonical
from .data.errors import DataError


def recipe(*,version=2):
    if type(version) is not int:raise DataError('GENERATED_RECIPE_UNSUPPORTED')
    if version==1:
        return dict(schema='builtin-generated-final-recipe-v1',source='BUILTIN_GENERATED_ONLY',
            generator='arithmetic-prices-v1',years=[2024,2025],seed=1729,
            coverage='PARTIAL_FIXTURE_UNQUALIFIED',warmup_sessions=252,training_sessions=45,
            scoring_sessions=31,price_formula='80 + session_index * (symbol_index + 1) / 20',
            volume='50000',actions=[],availability='SIMULATED_AVAILABILITY',
            financial_accepted=False,real_protected_access=False)
    if version!=2:raise DataError('GENERATED_RECIPE_UNSUPPORTED')
    return dict(schema='builtin-generated-final-recipe-v2',source='BUILTIN_GENERATED_ONLY',
        generator='continuous-arithmetic-market-v2',years=[2024,2025],seed=1729,
        coverage='PARTIAL_FIXTURE_UNQUALIFIED',warmup_sessions=252,initial_training_sessions=45,
        warmup_start='2022-10-25',initial_training_start='2023-10-26',
        first_score='2024-01-02',last_score='2025-12-31',
        scoring='ALL_EXCHANGE_SESSIONS_IN_BOTH_YEARS',
        annual_training='EXPANDING_FROM_FIXED_PARTIAL_FIXTURE_START',
        symbols=['AAPL','MSFT','JPM','SPY'],denominator_stocks=12,
        sectors={'AAPL':'fixture-tech','MSFT':'fixture-tech','JPM':'fixture-bank','SPY':'fixture-index'},
        calendar={'name':'XNYS','package':'exchange-calendars','version':'4.13.2'},
        price_formula='80 + session_index * (symbol_index + 1) / 20',
        session_index='ZERO_AT_WARMUP_START',volume='50000',actions=[],
        availability='SIMULATED_AVAILABILITY',financial_accepted=False,real_protected_access=False)


def recipe_hash(*,version=2):return hashlib.sha256(canonical(recipe(version=version))).hexdigest()


def recipe_for_pin(pin):
    for version in (1,2):
        value=recipe(version=version)
        if hashlib.sha256(canonical(value)).hexdigest()==pin:return value
    raise DataError('GENERATED_RECIPE_UNVERIFIED')

