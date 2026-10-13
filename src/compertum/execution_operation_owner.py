"""One execution-owned simulated step per call, with durable preparation first."""
from decimal import Decimal
import hashlib
from .domain import ExecutionIntent,ExecutionObservation,ContractError
from .execution_contracts import instant,TERMINAL
from .execution_plans import digest,assess_control,_quote
from .execution_risk import snapshot_sha256,control_health,client_order_id
from .execution_plan_owner import _encode,_value
from .execution_authority import MAX_REQUESTS,_decode
from .fake_execution_driver import FakeExecutionDriver
from . import fake_incident_evidence as incidents
from .events import canonical,uuid
from .runtime.errors import RuntimeRefused
from .simulation.policy import fixed_decimal

MAX_STEPS=64
STEP_BYTES=32768
RESULT_BYTES=4096


class FakeOperationOwner:
    def __init__(self,plans):
        self.plans=plans;self.authority=plans.authority;self.db=plans.db

    def _schema(self,*,create=True):
        names=('fake_plan_steps','fake_plan_results','fake_selected_intent_once')
        present=[self.db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(name,)).fetchone() is not None for name in names]
        version=self.db.execute("SELECT value FROM state WHERE key='fake_operation_version'").fetchone()
        if any(present) or version is not None:
            if not all(present) or version!=('1',):raise RuntimeRefused('OPERATION_STATE_CORRUPT')
            return
        if not create:raise RuntimeRefused('OPERATION_NOT_FOUND')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('CREATE TABLE fake_plan_steps(seq INTEGER PRIMARY KEY AUTOINCREMENT,request_id TEXT UNIQUE NOT NULL,plan_id TEXT NOT NULL,intent_id TEXT,action TEXT NOT NULL,sha256 TEXT NOT NULL,body TEXT NOT NULL)')
            self.db.execute('CREATE TABLE fake_plan_results(request_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL)')
            self.db.execute("CREATE UNIQUE INDEX fake_selected_intent_once ON fake_plan_steps(intent_id) WHERE action='DISPATCH'")
            self.authority._state_value('fake_operation_version',1)

    def _pending(self,value,pin):
        return dict(scope='DETERMINISTIC_FAKE',financial_accepted=False,receipt_only=True,
            operation=value['operation'],request_id=value['request_id'],plan_id=value['plan_id'],plan_sha256=value['plan_sha256'],
            context=value['context'],selection_sha256=pin,action=value['action'],status='PENDING_UNCONFIRMED',
            intent_id=None if value['intent'] is None else value['intent']['intent_id'])

    def _rows(self):
        rows=self.db.execute('SELECT seq,request_id,plan_id,intent_id,action,CASE WHEN length(sha256)=64 THEN sha256 END,CASE WHEN length(CAST(body AS BLOB))<=? THEN body END FROM fake_plan_steps ORDER BY seq LIMIT ?',(STEP_BYTES,MAX_STEPS+1)).fetchall()
        if len(rows)>MAX_STEPS:raise RuntimeRefused('OPERATION_STEP_BOUND')
        result=[];dispatches={};plans={}
        try:
            for seq,key,plan_id,intent_id,action,pin,raw in rows:
                value=_value((pin,raw),STEP_BYTES)
                if type(value) is not dict:raise ValueError()
                keys={'request_id','operation','plan_id','plan_sha256','context','action','intent','observation','decision','source_request_id'}
                if 'result_contract' in value:
                    if value['result_contract']!=incidents.CONTRACT:raise ValueError()
                    keys.add('result_contract')
                if set(value)!=keys:raise ValueError()
                if (key,plan_id,action)!=(value['request_id'],value['plan_id'],value['action']) or action not in {'DISPATCH','POLL','REPORT'}:raise ValueError()
                if plan_id not in plans:plans[plan_id]=(self.plans._core(plan_id),self.plans._phase(plan_id,'APPROVAL'),self.plans._phase(plan_id,'START'))
                (core,plan,_),approval,start=plans[plan_id]
                if value['operation'] not in {'advance_plan','reconcile_plan'} or value['plan_sha256']!=digest(plan) or approval is None or start is None:raise ValueError()
                if value['operation']=='advance_plan' and value['context']!=core['context']:raise ValueError()
                if value['operation']=='reconcile_plan' and action=='DISPATCH':raise ValueError()
                if set(value['context'])!=set(core['context']):raise ValueError()
                for field in ('session_id','owner_instance'):uuid(value['context'][field])
                current_profile,current_pin=self.authority._profile(value['context']['session_id'])
                if current_pin!=value['context']['profile_sha256'] or current_profile['account_alias']!=plan.to_payload()['account_alias']:raise ValueError()
                observation=ExecutionObservation(value['observation']);profile,_=self.authority._profile(core['context']['session_id'])
                if observation.to_payload()['generation']!=value['context']['generation'] or observation.to_payload()['account_alias']!=plan.to_payload()['account_alias']:raise ValueError()
                from .domain import ExecutionCalendar
                calendar=ExecutionCalendar(profile['calendar'])
                if action=='REPORT':
                    if intent_id is not None or any(value[k] is not None for k in ('intent','decision','source_request_id')):raise ValueError()
                else:
                    intent=ExecutionIntent(value['intent']);i=intent.to_payload()
                    if intent_id!=i['intent_id'] or i['plan_id']!=plan_id:raise ValueError()
                    if action=='DISPATCH':
                        decision=assess_control(intent,observation,plan,approval[1],start=start[1],now=observation.to_payload()['observed_at'],calendar=calendar).to_payload()
                        if not decision['allowed'] or decision!=value['decision'] or value['source_request_id'] is not None or intent_id in dispatches:raise ValueError()
                        dispatches[intent_id]=value
                    elif intent_id not in dispatches or value['intent']!=dispatches[intent_id]['intent'] or value['source_request_id']!=dispatches[intent_id]['request_id'] or value['decision'] is not None:raise ValueError()
                pending=self._pending(value,pin)
                final=_value(self.db.execute('SELECT sha256,CASE WHEN length(CAST(body AS BLOB))<=? THEN body END FROM fake_plan_results WHERE request_id=?',(RESULT_BYTES,key)).fetchone(),RESULT_BYTES)
                receipt=self.db.execute('SELECT generation,CASE WHEN length(CAST(result AS BLOB))<=? THEN result END FROM fake_operator_requests WHERE request_id=?',(RESULT_BYTES,key)).fetchone()
                if receipt is None or receipt[0]!=value['context']['generation']:raise ValueError()
                expected=pending if final is None else final
                if final is not None:self._validate_result(value,final,pending,plan,calendar,dispatches)
                if receipt[1]!=canonical(expected).decode():raise ValueError()
                result.append(dict(value=value,pending=pending,result=final))
            keys={v['value']['request_id'] for v in result}
            for key, in self.db.execute('SELECT request_id FROM fake_plan_results LIMIT ?',(MAX_STEPS+1,)):
                if key not in keys:raise ValueError()
            for receipt in self.plans._evidence(None,'advance_plan')+self.plans._evidence(None,'reconcile_plan'):
                if receipt['request_id'] not in keys:raise ValueError()
            return result
        except (ValueError,TypeError,KeyError,ContractError,RuntimeRefused):raise RuntimeRefused('OPERATION_STATE_CORRUPT') from None

    def _validate_result(self,value,final,pending,plan,calendar,dispatches):
        if type(final) is not dict or any(final.get(k)!=v for k,v in pending.items() if k!='status'):raise ValueError()
        status=final.get('status');base=set(pending);o=value['observation'];p=plan.to_payload()
        if value['action']=='REPORT':
            extra={'remaining_positions','open_order_ids'}
            if 'reason' in final:
                if type(final['reason']) is not str or not final['reason']:raise ValueError()
                extra.add('reason')
            if set(final)!=base|extra or status not in {'COMPLETE','CANCEL_COMPLETE','RECONCILED','BLOCKED_RESIDUAL','PENDING_UNCONFIRMED'}:raise ValueError()
            expected=self._summary(ExecutionObservation(o),status,final.get('reason'))
            if any(final[k]!=v for k,v in expected.items()):raise ValueError()
            orders={v['order_id']:v for v in o['orders']};by_client={v['client_order_id']:v for v in o['orders']}
            if status in {'COMPLETE','CANCEL_COMPLETE'}:
                if value['operation']!='advance_plan' or final['open_order_ids'] or control_health(ExecutionObservation(o),now=o['observed_at'],calendar=calendar):raise ValueError()
                if any(v['order_id'] not in orders or orders[v['order_id']]['status'] not in TERMINAL for v in p['cancel_orders']):raise ValueError()
                if status=='CANCEL_COMPLETE':
                    if p['kind']!='CANCEL':raise ValueError()
                else:
                    if p['kind']!='CLOSE_LONG' or final['remaining_positions']:raise ValueError()
                    for child in p['children']:
                        selected=dispatches.get(child['intent_id'])
                        if selected is None:raise ValueError()
                        order=by_client.get(client_order_id(ExecutionIntent(selected['intent'])))
                        if order is None or order['status'] not in TERMINAL:raise ValueError()
            if status=='RECONCILED':
                if value['operation']!='reconcile_plan':raise ValueError()
                for selected in dispatches.values():
                    if selected['plan_id']!=p['plan_id']:continue
                    i=selected['intent'];order=orders.get(i['order_id']) if i['kind']=='CANCEL' else by_client.get(client_order_id(ExecutionIntent(i)))
                    if order is None or order['status'] not in TERMINAL:raise ValueError()
            return
        extra={'intent_status','order_id','client_order_id','quantity','filled_quantity','reason'}
        i=value['intent'];state=final.get('intent_status');expected_warning={}
        modern=value.get('result_contract')==incidents.CONTRACT
        witness=incidents.result_witness(self.db,i,value['request_id'],required=modern and state in {'UNKNOWN','SUBMITTING'})
        if witness is not None:
            if not modern or witness['intent_status']!=state or instant(witness['at'])<instant(o['observed_at']) or not incidents.verify_incident(self.db,i,witness['started_at'],witness['elapsed_seconds'],witness['at']):raise ValueError()
            expected_warning=incidents.warning(witness['started_at'],witness['elapsed_seconds'])
        if expected_warning:extra|={'operator_action_required','incident_started_at'}
        if set(final)!=base|extra or any(type(final[k]) is not type(v) or final[k]!=v for k,v in expected_warning.items()):raise ValueError()
        filled=final['filled_quantity']
        allowed={'UNKNOWN','SUBMITTING','ACKNOWLEDGED','PARTIALLY_FILLED','CHECKED','REFUSED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED'}|TERMINAL
        if state not in allowed or type(filled) is not int or filled<0 or type(final['quantity']) is not int or final['quantity']!=i['quantity']:raise ValueError()
        expected='UNKNOWN' if state in {'UNKNOWN','SUBMITTING'} else 'STEP_TERMINAL' if state in TERMINAL else 'BLOCKED_RESIDUAL' if state=='REFUSED' or state.startswith('SKIPPED') else 'PENDING'
        if status!=expected:raise ValueError()
        if state=='REFUSED':
            if final['order_id'] is not None or final['client_order_id'] is not None or filled!=0 or type(final['reason']) is not list or not final['reason'] or any(type(v) is not str for v in final['reason']):raise ValueError()
            return
        if not expected_warning and final['reason'] is not None:raise ValueError()
        if final['client_order_id']!=client_order_id(ExecutionIntent(i)):raise ValueError()
        if final['order_id'] is not None:uuid(final['order_id'])
        if state not in TERMINAL|{'ACKNOWLEDGED','PARTIALLY_FILLED'}:return
        # A confirmed historical state must exist in the independent journal,
        # not merely in two copies of the operator result.
        evidence=self.db.execute("SELECT CASE WHEN length(CAST(body AS BLOB))<=65536 THEN body END FROM fake_intent_events WHERE account=? AND intent_id=? AND kind='OBSERVATION' ORDER BY seq LIMIT 513",(i['account_alias'],i['intent_id'])).fetchall()
        if len(evidence)>512:raise ValueError()
        for raw, in evidence:
            event=_decode(raw,65536);order=event['order']
            if event['result']==state and order['order_id']==final['order_id'] and order['filled_quantity']==filled:
                if order['symbol']!=i['symbol'] or i['kind']!='CANCEL' and (order['side']!='sell' or order['quantity']!=i['quantity']):raise ValueError()
                pin=self.db.execute('SELECT sha256 FROM fake_broker_events WHERE account=? AND event_id=?',(i['account_alias'],event['event_id'])).fetchone()
                if pin!=(hashlib.sha256(canonical(order)).hexdigest(),):raise ValueError()
                return
        raise ValueError()

    def _journal(self,intent_id,account):
        try:return self.plans.observations.journal.read(account,intent_id)
        except RuntimeRefused as error:
            if error.code!='INTENT_NOT_FOUND':raise
            return None

    @fixed_decimal
    def _intent(self,p,a,o,target,kind):
        raw=o.to_payload();quantity=0
        if kind=='CLOSE_LONG':
            q,cap=_quote(raw,target['symbol'],instant(raw['observed_at']))
            owned=next((v['owned_quantity'] for v in raw['positions'] if v['symbol']==target['symbol']),0)
            quantity=max(0,min(target['maximum_quantity'],owned,int(min(cap,Decimal(target['maximum_notional']))/(Decimal(q['ask'])*Decimal('1.01')))))
            if quantity==0:raise ContractError('CHILD_ENVELOPE_EXCEEDED')
        return ExecutionIntent(dict(schema_version='1',record_type='ExecutionIntent',scope='DETERMINISTIC_FAKE',currency='USD',
            intent_id=target['intent_id'],account_alias=raw['account_alias'],generation=raw['generation'],created_at=raw['observed_at'],expires_at=p['deadline'],
            kind=kind,side='sell' if kind=='CLOSE_LONG' else None,symbol=target['symbol'],quantity=quantity,
            inputs_sha256=raw['authority']['inputs_sha256'],strategy_sha256=raw['authority']['strategy_sha256'],authorization_sha256=digest(a),
            rebalance_id=raw['authority']['rebalance_id'],snapshot_sha256=snapshot_sha256(o),plan_id=p['plan_id'],
            child_index=target['index'] if kind=='CLOSE_LONG' else None,order_id=target['order_id'] if kind=='CANCEL' else None))

    def _summary(self,observation,status,reason=None):
        o=observation.to_payload()
        result=dict(status=status,remaining_positions=[dict(symbol=v['symbol'],quantity=v['owned_quantity']) for v in o['positions'] if v['owned_quantity']],open_order_ids=[v['order_id'] for v in o['orders'] if v['status'] not in TERMINAL])
        if reason is not None:result['reason']=reason
        return result

    def _select(self,rows,plan,authorization,start,observation,context):
        p=plan.to_payload();o=observation.to_payload();orders={v['order_id']:v for v in o['orders']}
        prior={v['value']['intent']['intent_id']:v['value'] for v in rows if v['value']['action']=='DISPATCH'}
        # A preparation interrupted before a durable attempt never grants a retry.
        for intent_id,value in prior.items():
            row=self._journal(intent_id,value['intent']['account_alias'])
            if row is None or row['status'] in {'CHECKED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED'}:
                return 'REPORT',None,None,None,self._summary(observation,'PENDING_UNCONFIRMED','PREPARED_EFFECT_UNCONFIRMED')
            if row['intent']!=value['intent']:raise RuntimeRefused('OPERATION_STATE_CORRUPT')
        for target in p['cancel_orders']+p['children']:
            key=target['intent_id'];old=prior.get(key)
            if old is not None:
                row=self._journal(key,p['account_alias'])
                if row['status'] not in TERMINAL:
                    return 'POLL',ExecutionIntent(old['intent']),None,old['request_id'],None
                continue
            kind='CANCEL' if 'order_id' in target else 'CLOSE_LONG'
            if kind=='CANCEL':
                order=orders.get(target['order_id'])
                if order is None:return 'REPORT',None,None,None,self._summary(observation,'BLOCKED_RESIDUAL','CANCELLATION_UNCONFIRMED')
                if order['status'] in TERMINAL:continue
            if instant(context['market_at'])>=instant(p['deadline']):return 'REPORT',None,None,None,self._summary(observation,'BLOCKED_RESIDUAL','PLAN_EXPIRED')
            try:
                intent=self._intent(p,authorization,observation,target,kind)
                decision=assess_control(intent,observation,plan,authorization,start=start,now=context['market_at'],calendar=context['calendar'])
                if not decision['allowed']:raise ContractError(decision['reasons'][0])
            except ContractError as error:return 'REPORT',None,None,None,self._summary(observation,'BLOCKED_RESIDUAL',str(error))
            return 'DISPATCH',intent,decision,None,None
        reasons=control_health(observation,now=context['market_at'],calendar=context['calendar'])
        if reasons:return 'REPORT',None,None,None,self._summary(observation,'BLOCKED_RESIDUAL',reasons[0])
        status='CANCEL_COMPLETE' if p['kind']=='CANCEL' else 'COMPLETE'
        summary=self._summary(observation,status)
        if summary['open_order_ids'] or p['kind']=='CLOSE_LONG' and summary['remaining_positions']:summary['status']='BLOCKED_RESIDUAL'
        return 'REPORT',None,None,None,summary

    def _prepare(self,packet,binding,value):
        raw,pin=_encode(value,STEP_BYTES);pending=self._pending(value,pin)
        with self.db:
            changed=self.db.execute('INSERT INTO fake_plan_steps(request_id,plan_id,intent_id,action,sha256,body) VALUES(?,?,?,?,?,?)',
                (value['request_id'],value['plan_id'],pending['intent_id'],value['action'],pin,raw))
            if changed.rowcount!=1:raise RuntimeRefused('OPERATION_WRITE_UNVERIFIED')
            self.plans._save_request(packet,binding,pending)
            saved=self.db.execute('SELECT sha256,body FROM fake_plan_steps WHERE request_id=?',(value['request_id'],)).fetchone()
            if saved!=(pin,raw):raise RuntimeRefused('OPERATION_WRITE_UNVERIFIED')
        # Verify committed evidence before any driver/journal effect.
        if self._rows()[-1]['pending']!=pending:raise RuntimeRefused('OPERATION_WRITE_UNVERIFIED')
        return pending

    def _complete(self,pending,result):
        final=dict(pending,**result);raw,pin=_encode(final,RESULT_BYTES)
        with self.db:
            changed=self.db.execute('INSERT INTO fake_plan_results VALUES(?,?,?)',(pending['request_id'],pin,raw))
            if changed.rowcount!=1:raise RuntimeRefused('OPERATION_WRITE_UNVERIFIED')
            changed=self.db.execute('UPDATE fake_operator_requests SET result=? WHERE request_id=? AND result=?',(raw,pending['request_id'],canonical(pending).decode()))
            actual=self.db.execute('SELECT sha256,body FROM fake_plan_results WHERE request_id=?',(pending['request_id'],)).fetchone()
            receipt=self.db.execute('SELECT result FROM fake_operator_requests WHERE request_id=?',(pending['request_id'],)).fetchone()
            if changed.rowcount!=1 or actual!=(pin,raw) or receipt!=(raw,):raise RuntimeRefused('OPERATION_WRITE_UNVERIFIED')
        return final

    def _headroom(self,rows):
        pending=self.db.execute("SELECT count(*) FROM fake_intents WHERE state NOT LIKE 'PAPER_%' AND state NOT IN ('FILLED','CANCELED','EXPIRED','REJECTED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED')").fetchone()[0]
        # Reserve dispatch, six lookups, limit warning, late resolution and report.
        # Their journal cost is 5 + 6*3 + 1 + 2; caps remain unchanged.
        slots=10*(pending+1);events=26*(pending+1)
        broker=self.plans.observations.broker.db
        counts=(len(rows)+slots<=MAX_STEPS,
            self.db.execute('SELECT count(*) FROM fake_operator_requests').fetchone()[0]+slots<=MAX_REQUESTS,
            self.db.execute('SELECT count(*) FROM fake_intent_events').fetchone()[0]+events<=512,
            self.db.execute('SELECT count(*) FROM fake_intents').fetchone()[0]+1<=256,
            broker.execute('SELECT count(*) FROM calls').fetchone()[0]+slots<=512,
            broker.execute('SELECT count(*) FROM broker_events').fetchone()[0]+slots<=512,
            broker.execute('SELECT count(*) FROM orders').fetchone()[0]+1<=256,
            self.db.execute('PRAGMA page_count').fetchone()[0]*self.db.execute('PRAGMA page_size').fetchone()[0]+2*1024**2<=16*1024**2,
            broker.execute('PRAGMA page_count').fetchone()[0]*broker.execute('PRAGMA page_size').fetchone()[0]+512*1024<=2*1024**2)
        return all(counts)

    def _limit_evidence(self,intent,started):
        return incidents.verify_incident(self.db,intent,started)

    def _warning(self,intent,status):
        return incidents.current_warning(self.db,intent,status)

    def _status(self,plan_id,rows):
        uuid(plan_id);self.plans._core(plan_id);intents=[]
        for record in rows:
            value=record['value']
            if value['plan_id']!=plan_id or value['action']!='DISPATCH':continue
            i=value['intent']
            row=self.db.execute('SELECT body,state,order_id,filled,notional,client_id FROM fake_intents WHERE account=? AND intent_id=?',(i['account_alias'],i['intent_id'])).fetchone()
            if row is None:intents.append(dict(intent_id=i['intent_id'],status='PENDING_UNCONFIRMED'));continue
            if row[0]!=canonical(i).decode():raise RuntimeRefused('OPERATION_STATE_CORRUPT')
            intents.append(dict(intent_id=i['intent_id'],status=row[1],order_id=row[2],filled_quantity=row[3],filled_notional=row[4],client_order_id=row[5],**self._warning(i,row[1])))
        result=dict(scope='DETERMINISTIC_FAKE',financial_accepted=False,fresh_reconciliation=False,plan_id=plan_id,intents=intents)
        _encode(result,65536);return result

    def _reconcile(self,rows,plan,observation):
        p=plan.to_payload()
        for record in rows:
            value=record['value']
            if value['plan_id']!=p['plan_id'] or value['action']!='DISPATCH':continue
            intent=ExecutionIntent(value['intent']);row=self._journal(value['intent']['intent_id'],p['account_alias'])
            if row is None or row['status'] in {'CHECKED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED'}:
                return 'REPORT',None,None,None,self._summary(observation,'PENDING_UNCONFIRMED','PREPARED_EFFECT_UNCONFIRMED')
            if row['intent']!=value['intent']:raise RuntimeRefused('OPERATION_STATE_CORRUPT')
            if row['status'] not in TERMINAL:return 'POLL',intent,None,value['request_id'],None
        return 'REPORT',None,None,None,self._summary(observation,'RECONCILED')

    def handle(self,packet):
        command=packet['command'];operation=command['operation']
        self._schema(create=operation!='operation_status');rows=self._rows()
        if operation=='operation_status':return self._status(command['plan_id'],rows)
        binding=hashlib.sha256(canonical(packet)).hexdigest();old=self.plans._request(packet,binding)
        if old is not None:return old
        if len(rows)>=MAX_STEPS or self.db.execute('SELECT count(*) FROM fake_operator_requests').fetchone()[0]>=MAX_REQUESTS:raise RuntimeRefused('OPERATION_STEP_BOUND')
        uuid(command['plan_id']);core,plan,_=self.plans._core(command['plan_id'])
        if command['plan_sha256']!=digest(plan):raise RuntimeRefused('PLAN_DIGEST_CHANGED')
        approval=self.plans._phase(command['plan_id'],'APPROVAL');started=self.plans._phase(command['plan_id'],'START')
        if approval is None or started is None:raise RuntimeRefused('PLAN_START_REQUIRED')
        observation,context=self.plans.observations.read();current_context=self.plans._context(context)
        if operation=='advance_plan' and current_context!=core['context']:raise RuntimeRefused('PLAN_CONTEXT_CHANGED')
        if observation.to_payload()['account_alias']!=plan.to_payload()['account_alias']:raise RuntimeRefused('FAKE_ACCOUNT_CHANGED')
        action,intent,decision,origin,report=self._select(rows,plan,approval[1],started[1],observation,context) if operation=='advance_plan' else self._reconcile(rows,plan,observation)
        if action=='DISPATCH' and not self._headroom(rows):
            action,intent,decision,origin,report='REPORT',None,None,None,self._summary(observation,'BLOCKED_RESIDUAL','RECONCILIATION_CAPACITY_REQUIRED')
        value=dict(result_contract=incidents.CONTRACT,request_id=packet['request_id'],operation=operation,plan_id=command['plan_id'],plan_sha256=digest(plan),context=current_context,action=action,
            intent=None if intent is None else intent.to_payload(),observation=observation.to_payload(),decision=None if decision is None else decision.to_payload(),source_request_id=origin)
        pending=self._prepare(packet,binding,value)
        if action=='REPORT':return self._complete(pending,report)
        current=self.authority.observation_context()
        if self.plans._context(current)!=current_context:raise RuntimeRefused('PLAN_CONTEXT_CHANGED')
        driver=FakeExecutionDriver(self.plans.observations.journal,self.plans.observations.broker)
        result=driver.dispatch(intent,observation,now=current['market_at'],calendar=context['calendar'],plan=plan,authorization=approval[1],start=started[1]) if action=='DISPATCH' else (driver.reconcile if operation=='reconcile_plan' else driver.poll)(intent,observation,now=current['market_at'])
        status=result['status'];mapped='UNKNOWN' if status in {'UNKNOWN','SUBMITTING'} else 'STEP_TERMINAL' if status in TERMINAL else 'BLOCKED_RESIDUAL' if status=='REFUSED' or status.startswith('SKIPPED') else 'PENDING'
        result=dict(status=mapped,intent_status=status,order_id=result.get('order_id'),client_order_id=result.get('client_order_id'),quantity=intent.to_payload()['quantity'],filled_quantity=result.get('filled_quantity',0),reason=result.get('decision',{}).get('reasons') if status=='REFUSED' else None)
        result.update(incidents.record_result(self.plans.observations.journal,intent.to_payload(),packet['request_id'],status,current['market_at']))
        return self._complete(pending,result)
