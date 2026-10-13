"""Fixed campaign metadata shared by owners and numerical workers."""
from dataclasses import dataclass
from compertum.data.errors import DataError

FEATURES=('return_1','return_5','return_21','return_63','volatility_20','volatility_63',
          'price_mean_20','price_mean_63','volume_mean_20','spy_return_1','spy_return_5',
          'spy_return_21','spy_return_63','spy_volatility_20','spy_volatility_63')

@dataclass(frozen=True)
class Variant:
    candidate_id:str
    kind:str
    horizon:int
    alpha:int|None

VARIANTS=tuple(Variant(f'momentum-h{h:02}','momentum',h,None) for h in (1,5,21))+tuple(
    Variant(f'ridge-h{h:02}-a{a:03}','ridge',h,a) for h in (1,5,21) for a in (1,10,100))


def variant(candidate_id):
    if type(candidate_id) is str:
        for candidate in VARIANTS:
            if candidate.candidate_id==candidate_id:return candidate
    raise DataError('UNREGISTERED_VARIANT')


YEARS=(2021,2022,2023)
SEEDS={'campaign':1729,'model':1730,'bootstrap':1731,'counterexample':1732}

@dataclass(frozen=True)
class Unit:
    phase:str
    candidate_id:str
    year:int
    fit_unit:int|None=None

    @property
    def key(self):return f'{self.year}:{self.candidate_id}:{self.phase}'


def _schedule():
    units=[]
    for year in YEARS:
        for candidate in VARIANTS:
            dependency=None
            if candidate.kind=='ridge':
                dependency=len(units);units.append(Unit('fit',candidate.candidate_id,year))
            units.append(Unit('evaluate',candidate.candidate_id,year,dependency))
    return tuple(units)

UNITS=_schedule()


DETERMINISTIC={'NO_TRAINING_ROWS','INSUFFICIENT_FIT_ROWS','NONFINITE_FIT','NUMERICAL_FIT_FAILURE','NONFINITE_PREDICTION','NUMERICAL_PREDICTION_FAILURE','OUTPUT_BOUND','ACTION_UNAVAILABLE','FRACTIONAL_ENTITLEMENT','MISSING_REFERENCE','REFERENCE_UNAVAILABLE'}
