"""Test-only append-only economic source. It grants no native or broker authority."""
import hashlib,json,os,re
from decimal import Context,Decimal,localcontext
from pathlib import Path
from uuid import UUID,uuid4
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_read_packet import _nanoseconds

ROOT=Path(__file__).parents[2]
_EXCLUDED={'events','event_count','ledger_head_sha256','opening_sha256','history_sha256','covered_until'}
_KINDS={'ACCRUAL':{'rule_id'},'PAYMENT':{'accrual_id','activity_id'},
        'REVERSAL':{'event_id_reversed','activity_id'},'UNLINKED_CREDIT':{'activity_id'}}

def need(value):
    if not value:raise RuntimeRefused('CONTROLLED_FIXTURE_SOURCE_UNVERIFIED')

def sha(value):return hashlib.sha256(canonical(value)).hexdigest()

def checked_path(path):
    path=Path(path);need(path.is_absolute() and path==path.resolve())
    roots=(ROOT/'.cache/test-runs/m5-local-economics-20261017-01',
           ROOT/'.cache/test-runs/m5-reconciliation-installed-20261016-01/local-economics-20261017-01',
           ROOT/'artifacts/m5/local-economics-20261017-01/controlled-source-ledgers')
    native=ROOT/'.cache/test-runs/native-economic-fresh-20261017-01/native-shared/state/fixture-economic-source.jsonl'
    if path==native:
        admitted=json.loads((ROOT/'artifacts/m5/native-economics-20261017-01/capacity-activation.json').read_text())
        need(admitted['admission']['scratch_cap_gib']==15 and admitted['admission']['additional_native_folders']==1)
    else:need(any(path.is_relative_to(root) for root in roots))
    current=path
    while current!=ROOT:
        if current.exists():need(not current.lstat().st_file_attributes&0x400)
        current=current.parent
    need(path.parent.is_dir());return path

def decode(line):
    need(type(line) is bytes and line.endswith(b'\n') and len(line)<=16384)
    value=json.loads(line);need(canonical(value)+b'\n'==line);return value

class ControlledEconomicSource:
    """Original journal data for tests; copied bytes are never native evidence."""
    def __repr__(self):return '<ControlledEconomicSource test-only private values redacted>'
    @classmethod
    def create(cls,path,header,clock):
        try:
            path=checked_path(path);need(not path.exists() and callable(clock))
            first={k:v for k,v in json.loads(canonical(header)).items() if k not in _EXCLUDED}
            first['covered_after']=clock();_nanoseconds(first['covered_after'])
            raw=canonical(dict(kind='SOURCE_BEGIN',version=1,producer_id=str(uuid4()),header=first))+b'\n'
            need(len(raw)<=16384)
            with path.open('xb',buffering=0) as stream:
                need(stream.write(raw)==len(raw));stream.flush();os.fsync(stream.fileno())
            return cls.open(path,clock)
        except (OSError,ValueError,TypeError,KeyError,RecursionError):
            raise RuntimeRefused('CONTROLLED_FIXTURE_SOURCE_UNVERIFIED') from None
    @classmethod
    def open(cls,path,clock):
        value=cls.__new__(cls);value._stream=None
        try:
            value.path=checked_path(path);need(callable(clock));value.clock=clock
            value._stream=value.path.open('r+b',buffering=0);value._identity=value._file_identity()
            raw=value._stream.read(128*1024+1);need(0<len(raw)<=128*1024)
            lines=raw.splitlines(keepends=True);need(1<=len(lines)<=1025)
            first=decode(lines[0]);need(set(first)=={'kind','version','producer_id','header'} and first['kind']=='SOURCE_BEGIN' and type(first['version']) is int and first['version']==1)
            need(str(UUID(first['producer_id']))==first['producer_id'])
            value._producer=first['producer_id'];value._header=first['header'];value._genesis=sha(value._header)
            value._head=value._genesis;value._events=[];value._last_at=_nanoseconds(value._header['covered_after'])
            value._last_clock=value._last_at
            value._closed_until=value._last_at-1
            for line in lines[1:]:
                event=decode(line)
                if event.get('kind')=='CLOCK_ACK':
                    need(set(event)=={'kind','at','covered_until','previous_sha256','sha256'} and event['previous_sha256']==value._head)
                    need(event['sha256']==sha({k:v for k,v in event.items() if k!='sha256'}))
                    at=_nanoseconds(event['at']);closed=_nanoseconds(event['covered_until'])
                    need(at>=value._last_clock and max(value._last_at,value._closed_until)<=closed<=at)
                    need(at>value._last_clock or closed>value._closed_until)
                    value._last_clock=at;value._closed_until=closed
                else:
                    value._check_event(event);value._events.append(event);value._head=event['sha256']
                    value._last_at=value._last_clock=_nanoseconds(event['at'])
            value._raw=raw;value._live();value._now();return value
        except (RuntimeRefused,OSError,ValueError,TypeError,KeyError,RecursionError):
            value.close();raise RuntimeRefused('CONTROLLED_FIXTURE_SOURCE_UNVERIFIED') from None
    def _file_identity(self):
        info=os.fstat(self._stream.fileno());need(info.st_nlink==1);return info.st_dev,info.st_ino
    def _now(self):
        text=self.clock();need(_nanoseconds(text)>=self._last_clock);return text
    def _write(self,raw):
        self._live();need(len(raw)<=16384 and len(self._raw)+len(raw)<=128*1024 and self._raw.count(b'\n')<1025)
        self._stream.seek(0,2);need(self._stream.write(raw)==len(raw));self._stream.flush();os.fsync(self._stream.fileno())
        self._raw+=raw;self._live()
    def _acknowledge(self,text,until):
        at=_nanoseconds(text);closed=_nanoseconds(until)
        need(at>=self._last_clock and max(self._last_at,self._closed_until)<=closed<=at)
        if at>self._last_clock or closed>self._closed_until:
            event=dict(kind='CLOCK_ACK',at=text,covered_until=until,previous_sha256=self._head);event['sha256']=sha(event)
            self._write(canonical(event)+b'\n');self._last_clock=at;self._closed_until=closed
    def _live(self):
        need(self._stream is not None and not self._stream.closed)
        info=self.path.stat(follow_symlinks=False)
        need((info.st_dev,info.st_ino)==self._identity and info.st_nlink==1 and not info.st_file_attributes&0x400)
        self._stream.seek(0);raw=self._stream.read(128*1024+1);need(raw==self._raw)
        need(self._file_identity()==self._identity)
    def _check_event(self,event):
        need(len(self._events)<128)
        need(type(event) is dict and event.get('kind') in _KINDS)
        expected={'event_id','kind','amount','at','sequence','previous_sha256','sha256'}|_KINDS[event['kind']]
        need(set(event)==expected and type(event['sequence']) is int and event['sequence']==len(self._events)+1)
        need(type(event['event_id']) is str and re.fullmatch('[A-Za-z0-9._:-]{1,128}',event['event_id']) is not None)
        need(event['event_id'] not in {e['event_id'] for e in self._events})
        need(event['previous_sha256']==self._head and event['sha256']==sha({k:v for k,v in event.items() if k!='sha256'}))
        need(_nanoseconds(event['at'])>=max(self._last_at,self._last_clock))
        need(_nanoseconds(event['at'])>self._closed_until)
        need(type(event['amount']) is str and re.fullmatch(r'(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,12})?',event['amount']) is not None and Decimal(event['amount'])>0)
    def append(self,fields):
        self._live();need(type(fields) is dict and len(self._events)<128 and fields.get('kind') in _KINDS)
        need(set(fields)=={'event_id','kind','amount'}|_KINDS[fields['kind']])
        event=json.loads(canonical(fields));event.update(at=self._now(),sequence=len(self._events)+1,previous_sha256=self._head)
        event['sha256']=sha(event);self._check_event(event);raw=canonical(event)+b'\n'
        self._write(raw);self._events.append(event);self._head=event['sha256'];self._last_at=self._last_clock=_nanoseconds(event['at'])
        self._live()
    def snapshot(self,*,opening_sha256,history_sha256,until):
        self._live();text=self._now();now=_nanoseconds(text);need(self._last_at<=_nanoseconds(until)<=now)
        for pin in (opening_sha256,history_sha256):need(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin) is not None)
        self._acknowledge(text,until)
        ledger=dict(self._header,opening_sha256=opening_sha256,history_sha256=history_sha256,covered_until=until,
                    events=self._events,event_count=len(self._events),ledger_head_sha256=self._head)
        return json.loads(canonical(dict(scope='CONTROLLED_FIXTURE_SOURCE_TEST_ONLY',source_qualified=False,
            producer_id=self._producer,genesis_sha256=self._genesis,ledger=ledger)))
    def observations(self):
        self._live();text=self._now();rows=[];seen={}
        with localcontext(Context(prec=160)):
            cash=Decimal(self._header['opening_cash'])
            for event in self._events:
                kind=event['kind'];amount=Decimal(event['amount']);effect=None
                if kind=='PAYMENT':effect=-amount
                elif kind=='UNLINKED_CREDIT':effect=amount
                elif kind=='REVERSAL' and seen[event['event_id_reversed']]['kind']=='PAYMENT':effect=amount
                if effect is not None:
                    cash+=effect;rows.append(dict(id=event['activity_id'],activity_type='FEE',date=event['at'][:10],net_amount=format(effect,'f')))
                seen[event['event_id']]=event
        self._acknowledge(text,text)
        return dict(cash=format(cash,'f'),activities=tuple(rows))
    def close(self):
        if self._stream is not None:self._stream.close();self._stream=None
