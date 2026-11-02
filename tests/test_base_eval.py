from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'/'base_eval'))
import market  # noqa: E402
import run  # noqa: E402


def test_market_signal():
    """The signal market has a lagged x relation in both periods; the noise market has none; the files are reproducible."""
    signal=market.market_csv('m1');noise=market.market_csv('m2')
    assert signal==market.market_csv('m1') and signal.count('\n')==market.DAYS+1
    assert market.lag_stats(signal,1,2000)['t']>3 and market.lag_stats(signal,2000,3000)['t']>2
    assert abs(market.lag_stats(noise,1,2000)['t'])<1 and abs(market.lag_stats(noise,2000,3000)['t'])<1


def test_answer_parsing():
    """The grader takes the last python block and the last ANSWER number, with commas and a dollar sign."""
    assert run.last_code('a\n```python\nx=1\n```\nb\n```py\ny=2\n```')=='y=2\n'
    assert run.last_code('no code') is None
    assert run.last_number('ANSWER: 1\nmore\nANSWER: $1,234.5','ANSWER')==1234.5
    assert run.last_number('nothing','ANSWER') is None


def test_finqa_tolerance():
    """A FinQA answer passes within 1% relative and fails outside it."""
    answers={'f1':22.67}
    assert run.grade_finqa({'id':'f1','final':'ANSWER: 22.5'},answers)['correct']
    assert not run.grade_finqa({'id':'f1','final':'ANSWER: 21'},answers)['correct']


def test_untraced_numbers():
    """Numbers found in a tool output or the prompt (also as a percentage) are traced; small counts are ignored."""
    assert run.untraced('Sharpe 1.23, t 2.9, 3 years, CAGR 12.5%','sharpe 1.2301 growth 0.125')==[2.9]
