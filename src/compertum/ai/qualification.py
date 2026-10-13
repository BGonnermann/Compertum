"""Six bounded model-only checks; absent native identities cannot qualify."""
from uuid import uuid4
from compertum.runtime.errors import RuntimeRefused

REQUIRED_IDENTITIES=frozenset({'model_sha256','binary_sha256','tokenizer_sha256','template_sha256','config_sha256','model_id','engine','context_tokens','serving_slots'})

def qualify_strata(adapter,tasks,identities):
    """Caller supplies three admitted qualification contexts and exact identities.

    No discovery/login/reconfiguration or global cancellation occurs here. The
    task budget ledger counts all six requests, including rejected responses.
    """
    if len(tasks)!=3 or len({t.to_payload()['task_id'] for t in tasks})!=3: raise RuntimeRefused('AI_CONTEXT_ISOLATION')
    checks=[];records=[]
    def run(name,task,messages,expected,**kwargs):
        result=adapter.request_proposal(task,messages,validate_proposal=False,**kwargs);records.append(result)
        passed=result['proposal']==expected
        checks.append({'name':name,'status':'VERIFIED_PASS' if passed else 'VERIFIED_FAIL','request_id':result['request_id']})
        return result
    first=tasks[0]
    try:
        run('json_object',first,[{'role':'user','content':'Return exactly this JSON object: {"fixture":"m0","ok":true}'}],{'fixture':'m0','ok':True})
        run('math_domain',first,[{'role':'user','content':'For real x, what is the domain of sqrt(x-1)? Return exactly {"minimum_x":1,"inclusive":true} if correct, otherwise your corrected JSON.'}],{'minimum_x':1,'inclusive':True})
        fixture_id=str(uuid4())
        tool=run('fictional_tool_proposal',first,[{'role':'user','content':'Propose only the offered fictional fixture lookup. No real tool executes.'}],
            {'name':'fixture_lookup','arguments':{'fixture_id':fixture_id}},approved_fixture_id=fixture_id)
        run('second_turn_fixture_result',first,[{'role':'user','content':'Read the dispatcher supplied synthetic fixture result and return exactly {"fixture_value":7}.'}],
            {'fixture_value':7},fixture_result_for=tool)
        for label,task in zip(('context_a','context_b'),tasks[1:]):
            run(label,task,[{'role':'user','content':'Return exactly '+str({'context':label}).replace("'",'"')}],{'context':label})
    except RuntimeRefused as error:
        checks.append({'name':'remaining_native_checks','status':'UNVERIFIED','reason':error.code})
    missing=sorted(REQUIRED_IDENTITIES-set(identities))
    complete=(len(checks)==6 and all(c['status']=='VERIFIED_PASS' for c in checks) and not missing)
    # Owned timeout/cancel verification is a separate native gate; six successful
    # calls alone do not enable autonomous dispatch after an uncertain request.
    return {'suite':'worker-v1','status':'VERIFIED_PASS' if complete else 'UNVERIFIED','checks':checks,'requests':records,
        'identities':identities,'missing_identities':missing,'native_owned_timeout':'UNVERIFIED',
        'automatic_local_dispatch':False,'executed_tools':0,'strategy_state':'NOT_EVALUATED'}
