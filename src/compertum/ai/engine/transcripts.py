"""Saved transcripts (step S3 of docs/MATHEMATICIAN_PLAN.md; owner request, 26 October 2026: a Compertum dataset for later fine-tuning).

The ledger keeps a hash of every prompt and reply. This writer keeps the words: one JSON line per sent model request, with the
messages, the reply, the tool calls and, from a thinking model, its thinking text. It never sees request headers, so it never
holds a key. Files go to state/engine/transcripts/<run id>.jsonl, which Git ignores with the rest of state/.

Owner rule (26 October 2026): bench and holdout work must never become training data, or a model could learn the test markets.
Real-provider runs also default to training_allowed false until the owner decides otherwise. A dataset builder must keep only true lines.
"""
import json
from pathlib import Path
from .ledger import EVALUATION_PURPOSES

TRANSCRIPTS_DIR='state/engine/transcripts'
FILE_BYTES=2*1024**3  # one run's file stops growing at 2 GiB; later lines are counted as skipped (a 370-cycle flash run needs about 1 GiB)


class TranscriptWriter:
    """The client's transcript callable for one run. A write error is counted, never raised: a lost line must not stop research.
    The texts passed the client's secret check before they were sent or accepted; thinking text that fails it is withheld by the client."""
    def __init__(self,project_root,run_id,run_purpose,max_bytes=FILE_BYTES,training_allowed=None):
        if training_allowed is not None and type(training_allowed) is not bool: raise ValueError('training_allowed')
        if run_purpose in EVALUATION_PURPOSES and training_allowed is True: raise ValueError('evaluation transcripts cannot train')
        folder=Path(project_root).absolute()/TRANSCRIPTS_DIR;folder.mkdir(parents=True,exist_ok=True)
        self.path=folder/f'{run_id}.jsonl';self.run_id=run_id;self.run_purpose=run_purpose;self.max_bytes=max_bytes
        self.training_allowed=run_purpose not in EVALUATION_PURPOSES if training_allowed is None else training_allowed
        self.lines=0;self.failures=0;self.skipped=0;self.bytes=0

    def __call__(self,record):
        line=json.dumps({'run_id':self.run_id,'run_purpose':self.run_purpose,'training_allowed':self.training_allowed,**record},
                        sort_keys=True,ensure_ascii=False,default=str)+'\n'
        size=len(line.encode('utf-8'))
        if self.bytes+size>self.max_bytes: self.skipped+=1;return
        try:
            with self.path.open('a',encoding='utf-8',newline='\n') as stream: stream.write(line)
            self.lines+=1;self.bytes+=size
        except OSError: self.failures+=1

    def report(self):
        return {'path':str(self.path),'lines':self.lines,'bytes':self.bytes,'skipped':self.skipped,'failures':self.failures,
                'training_allowed':self.training_allowed}
