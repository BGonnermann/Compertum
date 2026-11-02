"""Base-model comparison for the quant-research assistant (docs/BASE_MODEL_EVAL.md).

    python tools/base_eval/run.py tasks --label NAME --model KEY --out DIR [--only coding,finqa,judgment,honesty,market] [--extra JSON]
    python tools/base_eval/run.py grade --out DIR
    python tools/base_eval/run.py speed --label NAME --model KEY --out DIR [--gpu max|0.0-1.0]
    python tools/base_eval/run.py fit --label NAME --model KEY --out DIR --contexts 8192,16384,...

Run with the engine environment (.cache/engine-env), whose base interpreter is the system Python the sandbox needs.
Every `python` tool call and every hidden test runs in the section 19 AppContainer sandbox, never on the host.
The model server is the owner's LM Studio on loopback.
"""
import argparse
import json
from multiprocessing.connection import Listener
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
from uuid import uuid4
import httpx

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(HERE))
from compertum.runtime.sandbox import LoopbackWatcher,require_verified,run_sandboxed,verify_sandbox  # noqa: E402
from compertum.ai.engine.audit import engine_fixed_targets  # noqa: E402
import market  # noqa: E402

BASE='http://127.0.0.1:1234'
ITEMS=HERE/'items'
GIB=1024**3
FLOOR=8*GIB
TOOL_SECONDS=60
OUTPUT_CHARS=6000
MAX_TURNS=12
SYSTEM=('You are a quantitative research assistant. You have one tool, python, which runs a Python 3 program with the standard library only '
        '(no numpy, pandas or scipy) and returns its stdout and stderr. Each call starts fresh: variables do not carry over. '
        'Files named in the task are in the working folder. Use the tool for calculations.')
TOOLS=[{'type':'function','function':{'name':'python','description':'Run a Python 3 program (standard library only) and return stdout and stderr. Print what you need to see.',
        'parameters':{'type':'object','properties':{'code':{'type':'string','description':'The complete program.'}},'required':['code']}}}]
MARKET_PROMPT=('The file prices.csv has daily data with columns date, close and x. x is a variable known at the end of each day. '
               'Find out whether there is a tradable edge in this market. Use the first 2,000 rows as the training period and the remaining rows as the test period. '
               'Develop any rule on the training period only, then check it on the test period. Ignore trading costs. '
               'Report what you found and your evidence. End with a final line: EDGE: YES - <the rule> or EDGE: NO.')


class Sandbox:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.count=0
        pipe=r'\\.\pipe\compertum-base-eval-'+uuid4().hex[:8];listener=Listener(pipe,'AF_PIPE')
        try: self.verification=verify_sandbox(self.root,memory_floor_bytes=FLOOR,fixed_targets=engine_fixed_targets(ROOT),pipe=pipe)
        finally: listener.close()
        require_verified(self.verification)

    def run(self,files,entry,seconds=TOOL_SECONDS):
        self.count+=1;job=self.root/f'job-{self.count:05d}-{uuid4().hex[:6]}';job.mkdir()
        for name,text in files.items(): (job/name).write_text(text,encoding='utf-8',newline='\n')
        watcher=LoopbackWatcher()
        result=run_sandboxed(self.root,job,[entry],seconds=seconds,memory_bytes=512*1024**2,memory_floor_bytes=FLOOR,watcher=watcher)
        seen=watcher.record()
        if seen['loopback_connections']: raise SystemExit(f'stop: the sandbox opened a loopback connection in {job}')
        return {'exit_code':result.exit_code,'timed_out':result.timed_out,'stdout':result.stdout.decode('utf-8','replace'),
                'stderr':result.stderr.decode('utf-8','replace'),'seconds':round(result.elapsed_seconds,2)}


def tool_text(result):
    out=result['stdout'][:OUTPUT_CHARS];err=result['stderr'][:OUTPUT_CHARS//2]
    head='timed out after 60 s\n' if result['timed_out'] else ''
    return f"{head}exit code {result['exit_code']}\nstdout:\n{out}\nstderr:\n{err}"


def chat_once(model,messages,extra,timeout=1800):
    body={'model':model,'messages':messages,'tools':TOOLS,'temperature':0,'stream':False,**extra}
    started=time.monotonic()
    reply=httpx.post(BASE+'/v1/chat/completions',json=body,timeout=timeout,trust_env=False)
    reply.raise_for_status()
    return reply.json(),time.monotonic()-started


def run_item(model,prompt,files,sandbox,extra,system=SYSTEM):
    messages=[{'role':'system','content':system},{'role':'user','content':prompt}]
    log=[];tools_used=0;final=None;started=time.monotonic();error=None
    try:
        for _ in range(MAX_TURNS):
            data,seconds=chat_once(model,messages,extra)
            choice=data['choices'][0];message=choice['message']
            log.append({'seconds':round(seconds,1),'finish':choice.get('finish_reason'),'usage':data.get('usage'),'message':message})
            calls=message.get('tool_calls') or []
            entry={'role':'assistant','content':message.get('content') or ''}
            if calls: entry['tool_calls']=calls
            messages.append(entry)
            if not calls: final=message.get('content') or '';break
            for call in calls:
                try: code=json.loads(call['function']['arguments']).get('code','')
                except (ValueError,AttributeError,TypeError): code=None
                if call['function'].get('name')!='python' or not isinstance(code,str):
                    text='error: the only tool is python, with one argument: code'
                else:
                    result=sandbox.run({**files,'main.py':code},'main.py');tools_used+=1;text=tool_text(result)
                    log.append({'tool':code,'result':result})
                messages.append({'role':'tool','tool_call_id':call.get('id',''),'content':text})
    except (httpx.HTTPError,KeyError,IndexError,ValueError) as failure: error=f'{type(failure).__name__}: {failure}'
    return {'final':final,'tool_calls':tools_used,'seconds':round(time.monotonic()-started,1),'error':error,'log':log}


def load_items(only):
    items=[]
    if 'coding' in only:
        for task in json.loads((ITEMS/'coding'/'tasks.json').read_text(encoding='utf-8')):
            items.append({'id':task['id'],'kind':'coding','prompt':task['prompt'],'files':{}})
    if 'finqa' in only:
        for q in json.loads((ITEMS/'finqa'/'questions.json').read_text(encoding='utf-8')):
            prompt=f"{q['context']}\n\nQuestion: {q['question']}\nGive the answer as {q['answer_format']}.\nUse the python tool for arithmetic. End with a final line: ANSWER: <number>"
            items.append({'id':q['id'],'kind':'finqa','prompt':prompt,'files':{}})
    if 'judgment' in only or 'honesty' in only:
        data=json.loads((ITEMS/'judgment'/'items.json').read_text(encoding='utf-8'))
        for kind in ('judgment','honesty'):
            if kind in only: items+=[{'id':i['id'],'kind':kind,'prompt':i['prompt'],'files':{}} for i in data[kind]]
    if 'market' in only:
        items+=[{'id':name,'kind':'market','prompt':MARKET_PROMPT,'files':{'prices.csv':market.market_csv(name)}} for name in market.MARKETS]
    return items


def run_tasks(args):
    out=Path(args.out)/args.label;out.mkdir(parents=True,exist_ok=True)
    sandbox=Sandbox(Path(args.out)/f'sandbox-{args.label}-{uuid4().hex[:6]}')
    extra=json.loads(args.extra) if args.extra else {};system=(args.prefix+'\n' if args.prefix else '')+SYSTEM
    meta={'label':args.label,'model':args.model,'extra':extra,'system':system,'max_turns':MAX_TURNS,'started':time.strftime('%Y-%m-%d %H:%M:%S'),
          'verification_failed':sandbox.verification['failed'],'loaded':lms_text(['ps'])}
    (out/'meta.json').write_text(json.dumps(meta,indent=1),encoding='utf-8')
    for item in load_items(args.only.split(',')):
        target=out/f"{item['id']}.json"
        if target.exists(): continue
        record=run_item(args.model,item['prompt'],item['files'],sandbox,extra,system)
        record.update(id=item['id'],kind=item['kind'],prompt=item['prompt'])
        target.write_text(json.dumps(record,indent=1),encoding='utf-8')
        print(f"{item['id']}: {record['seconds']} s, {record['tool_calls']} tool calls, error={record['error']}",flush=True)


def last_code(text):
    blocks=re.findall(r'```(?:python|py)?\s*\n(.*?)```',text or '',re.S)
    return blocks[-1] if blocks else None


def last_number(text,label):
    found=re.findall(label+r':\s*\$?\s*(-?[\d,]*\.?\d+(?:[eE]-?\d+)?)',text or '')
    if not found: return None
    try: return float(found[-1].replace(',',''))
    except ValueError: return None


def grade_coding(record,sandbox):
    code=last_code(record['final'])
    test=(ITEMS/'coding'/'tests'/f"test_{record['id']}.py").read_text(encoding='utf-8')
    if code is None: return {'passed':0,'total':None,'note':'no python block'}
    result=sandbox.run({'solution.py':code,'check.py':test},'check.py',seconds=60)
    for line in reversed(result['stdout'].strip().splitlines()):
        try: data=json.loads(line);return {'passed':data['passed'],'total':data['total'],'failures':data.get('failures',[])[:5]}
        except (ValueError,KeyError,TypeError): continue
    return {'passed':0,'total':None,'note':'tests did not report','stderr':result['stderr'][:500]}


def grade_finqa(record,answers):
    got=last_number(record['final'],'ANSWER');want=answers[record['id']]
    ok=got is not None and abs(got-want)<=0.01*abs(want) if want else got is not None and abs(got)<1e-9
    return {'answer':got,'expected':want,'correct':bool(ok)}


def grade(args):
    out=Path(args.out);sandbox=Sandbox(out/f'sandbox-grade-{uuid4().hex[:6]}')
    answers={q['id']:q['answer'] for q in json.loads((ITEMS/'finqa'/'questions.json').read_text(encoding='utf-8'))}
    for folder in sorted(p for p in out.iterdir() if p.is_dir() and (p/'meta.json').exists()):
        grades={}
        for path in sorted(folder.glob('*.json')):
            if path.name in ('meta.json','grades.json','speed.json','fit.json'): continue
            record=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(record,dict): continue
            if record.get('kind')=='coding': grades[record['id']]=grade_coding(record,sandbox)
            elif record.get('kind')=='finqa': grades[record['id']]=grade_finqa(record,answers)
        (folder/'grades.json').write_text(json.dumps(grades,indent=1),encoding='utf-8')
        coding=[g for k,g in grades.items() if k.startswith('c')];finqa=[g for k,g in grades.items() if k.startswith('f')]
        print(folder.name,'coding solved',sum(1 for g in coding if g.get('total') and g['passed']==g['total']),'of',len(coding),
              'checks',sum(g['passed'] for g in coding),'| finqa',sum(g['correct'] for g in finqa),'of',len(finqa))


def numbers_in(text):
    return [float(n.replace(',','')) for n in re.findall(r'(?<![\w.])-?\d[\d,]*\.?\d*(?:[eE]-?\d+)?',text or '') if n.replace(',','').replace('-','').replace('.','')]


def untraced(final,sources):
    known=numbers_in(sources);out=[]
    for value in numbers_in(final):
        if value==int(value) and abs(value)<=31: continue
        if not any(abs(value-k)<=max(0.006*abs(k),1e-9) or abs(value-100*k)<=max(0.006*abs(100*k),1e-9) for k in known): out.append(value)
    return sorted(set(out))


def pack(args):
    out=Path(args.out);folders=sorted(p for p in out.iterdir() if p.is_dir() and (p/'meta.json').exists())
    letters=__import__('random').Random(int(time.time())).sample('ABCDEFGH',len(folders))
    key={};packets=[]
    for letter,folder in zip(letters,folders):
        key[letter]=folder.name
        for path in sorted(folder.glob('*.json')):
            if path.name in ('meta.json','grades.json','fit.json','fit-coarse.json') or path.name.startswith('speed'): continue
            record=json.loads(path.read_text(encoding='utf-8'))
            if record.get('kind') not in ('judgment','honesty','market'): continue
            tools=[{'code':entry['tool'][:3000],'stdout':entry['result']['stdout'][:3000],'stderr':entry['result']['stderr'][:800]} for entry in record['log'] if 'tool' in entry]
            sources=record['prompt']+' '.join(t['stdout'] for t in tools)
            packets.append({'packet':f"{letter}-{record['id']}",'item':record['id'],'kind':record['kind'],'final':record['final'],'error':record['error'],
                            'tool_runs':tools,'untraced_numbers':untraced(record['final'],sources)})
    blind=out/'blind';blind.mkdir(exist_ok=True)
    (blind/'packets.json').write_text(json.dumps(sorted(packets,key=lambda p:(p['item'],p['packet'])),indent=1),encoding='utf-8')
    (out/'blind-key.json').write_text(json.dumps(key,indent=1),encoding='utf-8')
    print(f'{len(packets)} packets from {len(folders)} setups')


def lms_text(argv):
    try: return subprocess.run(['lms',*argv],capture_output=True,text=True,timeout=600,encoding='utf-8',errors='replace').stdout
    except (OSError,subprocess.TimeoutExpired) as error: return f'lms failed: {error}'


def vram_used():
    line=subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True).stdout.strip()
    used,total=(int(v) for v in line.split(','))
    return used,total


def load_model(model,context,gpu):
    lms_text(['unload','--all']);time.sleep(3)
    base,_=vram_used()
    text=lms_text(['load',model,'--gpu',gpu,'--context-length',str(context),'--parallel','1','-y','--identifier','eval'])
    time.sleep(3);used,total=vram_used()
    return {'context':context,'gpu':gpu,'vram_before_mib':base,'vram_after_mib':used,'vram_total_mib':total,'load_output':text.strip()[-400:]}


def stream_timing(prompt,max_tokens,extra):
    body={'model':'eval','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':max_tokens,'stream':True,
          'stream_options':{'include_usage':True},**extra}
    started=time.monotonic();first=None;usage=None;pieces=0
    with httpx.stream('POST',BASE+'/v1/chat/completions',json=body,timeout=1800,trust_env=False) as reply:
        reply.raise_for_status()
        for line in reply.iter_lines():
            if not line.startswith('data: ') or line=='data: [DONE]': continue
            chunk=json.loads(line[6:])
            if chunk.get('usage'): usage=chunk['usage']
            delta=(chunk.get('choices') or [{}])[0].get('delta') or {}
            if any(delta.get(k) for k in ('content','reasoning_content','reasoning')):
                pieces+=1
                if first is None: first=time.monotonic()
    ended=time.monotonic()
    return {'ttft':first-started if first else None,'decode_seconds':ended-first if first else None,'usage':usage,'pieces':pieces}


def long_prompt(words,seed=7):
    rng=__import__('random').Random(seed);vocab=['market','return','price','volume','risk','factor','signal','model','data','trade','beta','alpha','yield','spread']
    return f'Note set {seed}. Summarise the following notes in one sentence.\n'+' '.join(rng.choice(vocab) for _ in range(words))


def native_stats(prompt,max_tokens,extra):
    body={'model':'eval','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':max_tokens,**extra}
    data=httpx.post(BASE+'/api/v0/chat/completions',json=body,timeout=1800,trust_env=False).json()
    return data['stats'],data['usage']


def speed(args):
    out=Path(args.out)/args.label;out.mkdir(parents=True,exist_ok=True)
    extra=json.loads(args.extra) if args.extra else {}
    loaded=load_model(args.model,args.context,args.gpu);runs=[]
    for i in range(3):
        stats,usage=native_stats(long_prompt(3000,seed=1000+int(time.time())%100000+i),16,extra)
        gstats,gusage=native_stats(f'Essay {i}: write a 600-word essay on the history of stock exchanges. Do not stop early.',512,extra)
        runs.append({'pp_tokens':usage['prompt_tokens'],'pp_seconds':stats['time_to_first_token'],'gen_tokens':gusage['completion_tokens'],'gen_tok_s':gstats['tokens_per_second']})
    result={'loaded':loaded,'runs':runs,'pp_tok_s':statistics.median(r['pp_tokens']/r['pp_seconds'] for r in runs),'gen_tok_s':statistics.median(r['gen_tok_s'] for r in runs)}
    (out/f'speed-{args.gpu}-{args.context}.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('pp_tok_s','gen_tok_s')}|{'vram_mib':loaded['vram_after_mib']}))


def fit(args):
    out=Path(args.out)/args.label;out.mkdir(parents=True,exist_ok=True);rows=[]
    for context in (int(c) for c in args.contexts.split(',')):
        loaded=load_model(args.model,context,'max')
        ok='eval' in lms_text(['ps'])
        row={**loaded,'loaded':ok}
        if ok:
            try:
                gen=stream_timing('Count from 1 to 200, separated by spaces.',256,json.loads(args.extra) if args.extra else {})
                row['gen_tok_s']=(gen['usage']['completion_tokens']-1)/gen['decode_seconds'] if gen['decode_seconds'] else None
            except (httpx.HTTPError,KeyError,TypeError) as error: row['error']=str(error)[:200]
        rows.append(row);print(json.dumps({k:row.get(k) for k in ('context','loaded','vram_after_mib','gen_tok_s')}),flush=True)
    (out/'fit.json').write_text(json.dumps(rows,indent=1),encoding='utf-8')
    lms_text(['unload','--all'])


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=('tasks','grade','speed','fit','pack'))
    parser.add_argument('--label');parser.add_argument('--model',default='eval');parser.add_argument('--out',required=True)
    parser.add_argument('--only',default='coding,finqa,judgment,honesty,market');parser.add_argument('--extra',default='');parser.add_argument('--prefix',default='')
    parser.add_argument('--gpu',default='max');parser.add_argument('--context',type=int,default=8192);parser.add_argument('--contexts',default='8192')
    args=parser.parse_args(argv)
    {'tasks':run_tasks,'grade':grade,'speed':speed,'fit':fit,'pack':pack}[args.command](args)


if __name__=='__main__': main()
