"""Step S3, product lane: the transcript writer marks evaluation work as not for training, caps its file, and never raises."""
import json
from compertum.ai.engine.transcripts import TRANSCRIPTS_DIR,TranscriptWriter


def test_lines_carry_the_training_mark_and_the_file_has_a_cap(tmp_path):
    practice=TranscriptWriter(tmp_path,'run-20261026-0123abcd','practice',max_bytes=600)
    practice({'role':'director','content':'a'*100});practice({'role':'director','content':'b'*100});practice({'role':'director','content':'c'*400})
    lines=[json.loads(x) for x in (tmp_path/TRANSCRIPTS_DIR/'run-20261026-0123abcd.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [x['content'][0] for x in lines]==['a','b'] and all(x['training_allowed'] is True and x['run_purpose']=='practice' for x in lines)
    report=practice.report();assert report['lines']==2 and report['skipped']==1 and report['failures']==0 and report['bytes']<=600
    # Owner rule (26 October 2026): bench and holdout work never becomes training data.
    for purpose in ('bench','holdout'):
        writer=TranscriptWriter(tmp_path,f'run-20261026-0000{purpose[:4]}','bench' if purpose=='bench' else 'holdout');writer({'role':'mathematician'})
        assert json.loads(writer.path.read_text(encoding='utf-8'))['training_allowed'] is False and writer.report()['training_allowed'] is False
    real=TranscriptWriter(tmp_path,'run-20261027-0000real','practice',training_allowed=False);real({'role':'director'})
    assert json.loads(real.path.read_text(encoding='utf-8'))['training_allowed'] is False and real.report()['training_allowed'] is False
    try: TranscriptWriter(tmp_path,'run-20261027-0000bad0','bench',training_allowed=True)
    except ValueError: pass
    else: raise AssertionError('a bench transcript must never become training data')
    # A write that fails is counted, never raised: research goes on.
    broken=TranscriptWriter(tmp_path,'run-20261026-0000dead','gepa');broken.path.mkdir()  # a folder where the file should be
    broken({'role':'director'});assert broken.report()['failures']==1 and broken.report()['lines']==0
