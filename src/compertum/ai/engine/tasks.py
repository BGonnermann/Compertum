"""The text of every role task, in one place (25 October 2026). The cycle builds its tasks with these functions, and the preflight
check (preflight.py) builds the same tasks from sample data before a run, so a broken task is refused before the model is loaded.

No engine library is imported here, so the product environment can check tasks too. Moved out of cycle.py unchanged: every task
is byte-identical to the one the cycle built before.
"""
import json
from .market import COST

TRANSCRIPT_BYTES=8192
RETRY_REPLY_BYTES=2048  # how much of an unusable reply a retry task shows the model
SAMPLE_ROWS=6  # train rows shown to the Engineer. Never validation rows: a model that has read the validation returns can type positions from memory.
STARTER_MAIN='''"""Starter program for one specification. Edit decide(); keep the file names as they are.
The job folder holds train.csv and validation.csv next to this file. Open them by these plain names.
Write signals.csv next to this file. The run is complete when signals.csv exists."""
import csv


def read_rows(name):
    with open(name,newline='',encoding='utf-8') as handle: return list(csv.DictReader(handle))


def decide(train,validation):
    """Return one position (0 or 1) for every validation row, in order, using only rows up to that session."""
    return [0 for _ in validation]


def main():
    train=read_rows('train.csv');validation=read_rows('validation.csv')
    positions=decide(train,validation)
    with open('signals.csv','w',newline='',encoding='utf-8') as out:
        out.write('session,position\\n')
        for row,position in zip(validation,positions): out.write(f"{row['session']},{int(position)}\\n")
    print('signals written',len(positions))


if __name__=='__main__': main()
'''


def clip_bytes(text,limit=TRANSCRIPT_BYTES):
    raw=text.encode('utf-8')
    return text if len(raw)<=limit else raw[:limit].decode('utf-8',errors='ignore')


def market_brief(engine):
    """The fixed description of the market and the scoring rule that every idea task carries. Code, not a prompt: GEPA cannot remove it.
    Practice run 1 (24 October 2026) showed a real model inventing software hypotheses when the task held only the ledger summary."""
    train=max(engine.train_csv.count('\n')-1,0);validation=len(engine.validation_rows)
    return ('MARKET\n'
            f'One asset, daily sessions, synthetic and closed. Two files: train.csv ({train} sessions) and validation.csv ({validation} sessions), '
            'columns session, close, return (return is the fractional change of close from the previous session). '
            'A hypothesis is a rule that sets a position of 0 (flat) or 1 (long) for every validation session from data up to that session. '
            f'Score: the position at session t earns the return of session t+1, minus a cost of {COST} of NAV for each position change. '
            'A strategy beats the baseline when its Sharpe ratio is defined, its annual mean excess over buy-and-hold is positive, and its Sharpe is above buy-and-hold\'s. '
            'Only these two files exist; propose nothing that needs other data.')


def pick_task(max_hypotheses,cycle_index,brief,summary):
    return f'Pick at most {max_hypotheses} hypotheses for cycle {cycle_index}.\n\n{brief}\n\nLedger summary:\n{json.dumps(summary,sort_keys=True)}'


def memo_task(brief,hypothesis,summary=None):
    """summary: the ledger summary, when the routing sends it to the Researcher (routing key researcher_sees_lessons)."""
    lessons='' if summary is None else f'\n\nLedger summary:\n{json.dumps(summary,sort_keys=True)}'
    return f'Write the memo for this hypothesis.\n\n{brief}\n\nHYPOTHESIS\n{json.dumps(hypothesis,sort_keys=True)}{lessons}'


def approve_task(hypothesis_id,memo_text):
    return f'Approve or reject this memo for hypothesis {hypothesis_id}.\n\n{memo_text}'


def specify_task(brief,memo_text,hypothesis=None):
    """hypothesis: the Director's hypothesis, when the routing sends it to the Mathematician (routing key specify_sees_hypothesis)."""
    extra='' if hypothesis is None else f'\n\nHYPOTHESIS\n{json.dumps(hypothesis,sort_keys=True)}'
    return f'Write the specification for this approved memo.\n\n{brief}\n\nMEMO\n{memo_text}{extra}'


# Bench baseline 1 (26 October 2026): three Mathematician reviews filled the 2,048-token cap with about 1,530 tokens of visible answer and were refused.
# The review is advice only, so a short one loses nothing. Code adds the limit, so GEPA cannot remove it; the preflight check confirms it.
REVIEW_LENGTH_RULE='Write at most 150 words.'


def review_task(specification,code):
    return (f'Review this code against the specification. {REVIEW_LENGTH_RULE}\n\nSPECIFICATION\n{specification}\n\n'
            f'CODE\n{json.dumps(code,sort_keys=True)}')


def agenda_task(brief,summary):
    return f'Review the repeated failures and update the agenda.\n\n{brief}\n\nLedger summary:\n{json.dumps(summary,sort_keys=True)}'


def retry_task(task,code,previous_reply):
    """The task again, after an unusable JSON reply: it names the failure and shows the reply, clipped (practice run 3)."""
    previous=clip_bytes(previous_reply,RETRY_REPLY_BYTES)
    return (f'{task}\n\nYour previous reply was not usable ({code}). Reply again with JSON only, no other text, exactly in the format the role prompt gives.'
            f'\n\nPREVIOUS REPLY\n{previous}')


def engineer_task(engine,specification,*,previous_reply=None,memo=None,review=None,code=None):
    """The Engineer's task and its starting files. The specification is in the task text AND in /spec.md. A sample of the TRAIN rows shows the columns.
    Practice runs 5 to 10 (24 to 25 October 2026) sent the literal text of a template instead of the specification: the second half of the string had no f prefix.
    Routing (26 October 2026): memo adds the Researcher's memo; review and code make a rebuild task that starts from the built code and the Mathematician's review."""
    sample='\n'.join(engine.train_csv.splitlines()[:SAMPLE_ROWS+1])
    if review is not None:
        head=('Rebuild this specification and run it with run_job. The Mathematician reviewed your code; the review is below. '
              'Fix every point that the review shows to break the specification, run the program again with run_job, then reply DONE.\n\n'
              f'REVIEW\n{clip_bytes(review,RETRY_REPLY_BYTES)}\n\n')
    elif previous_reply is None: head='Build this specification and run it with run_job.\n\n'
    else:
        head=('Build this specification and run it with run_job.\n\n'
              'Your previous attempt replied without running the program, so nothing was produced. '
              'This time: edit decide() in /main.py (or rewrite the file), then call run_job with entry main.py, then reply DONE.\n\n'
              f'PREVIOUS REPLY\n{clip_bytes(previous_reply,RETRY_REPLY_BYTES)}\n\n')
    starter='your program from the first build' if review is not None else 'a starter program'
    task=(head+f'Your file store holds two files: /main.py, {starter} (edit decide(), keep the file names), and /spec.md, the specification below. '
          'It holds nothing else. You cannot read train.csv or validation.csv yourself: your program opens them by those plain names in the job folder. '
          'When run_job reports that signals.csv was written, reply DONE.\n\n'
          f'TRAIN SAMPLE (the first rows of train.csv)\n{sample}\n\nSPECIFICATION\n{specification}')
    if memo is not None: task+=f'\n\nMEMO (the research behind the specification)\n{memo}'
    main=code.get('/main.py',STARTER_MAIN) if review is not None and isinstance(code,dict) else STARTER_MAIN
    return task,{'/main.py':main,'/spec.md':specification}
