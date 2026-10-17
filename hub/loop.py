"""The whole planned flow, with observations kept separate from acceptance."""
STAGES = (
    ('data', 'Data collection', 'Collect authorized market inputs.', 'src/compertum/data/'),
    ('quality', 'Data checks', 'Check quality, timing and allowed use.', 'src/compertum/data/snapshot.py'),
    ('proposals', 'AI proposals', 'Import bounded proposals. Automatic dispatch remains unfinished.', 'src/compertum/ai/manual.py'),
    ('experiments', 'Experiments', 'Run registered models and preserve every outcome.', 'src/compertum/modeling/campaign.py'),
    ('mathematics', 'Mathematics', 'Check claims, derivations and counterexamples.', 'docs/BUILD_SPEC.md'),
    ('development_audit', 'Development audit', 'Independently check development results.', 'src/compertum/audit_campaign.py'),
    ('final_evaluation', 'Protected evaluation', 'Consume one protected evaluation under frozen identities.', 'src/compertum/final_controller.py'),
    ('independent_audit', 'Independent audit', 'Check the final result independently.', 'src/compertum/final_audit_controller.py'),
    ('qualification', 'Qualification', 'Require valid financial and engineering evidence.', 'src/compertum/modeling/qualification.py'),
    ('authorization', 'Owner approval', 'Require the specific operating and account authority.', 'docs/BUILD_SPEC.md'),
    ('signals', 'Signals', 'Build versioned, qualified signals.', 'docs/BUILD_SPEC.md'),
    ('risk', 'Risk and health', 'Check current risk, ownership and health.', 'src/compertum/runtime/execution_health.py'),
    ('intentions', 'Saved intentions', 'Retain exact intentions before dispatch.', 'src/compertum/execution_plans.py'),
    ('execution', 'Paper execution', 'Send only separately authorized paper actions.', 'docs/BUILD_SPEC.md'),
    ('reconciliation', 'Reconciliation', 'Compare original account observations with owned history.', 'src/compertum/paper_reconciliation.py'),
    ('reports', 'Results and reports', 'Retain outcomes and unresolved requirements.', 'src/compertum/session_evidence.py'),
    ('feedback', 'Research feedback', 'A bounded return to proposals remains unfinished.', 'docs/BUILD_SPEC.md'),
)


def build_loop(activity):
    stages = [dict(id=identity, name=name, description=description, source=source,
                   state='Not observed', reporting='No operational stage event', activities=[])
              for identity, name, description, source in STAGES]
    positions = {'data': (0,0), 'quality': (1,0), 'proposals': (2,0), 'experiments': (3,0),
                 'development_audit': (4,0), 'final_evaluation': (5,0), 'mathematics': (1,1),
                 'feedback': (0,1), 'authorization': (3,1), 'qualification': (4,1), 'independent_audit': (5,1),
                 'signals': (0,2), 'risk': (1,2), 'intentions': (2,2), 'execution': (3,2),
                 'reconciliation': (4,2), 'reports': (5,2)}
    for stage in stages: stage['column'], stage['row'] = positions[stage['id']]
    routes = [('data','quality'),('quality','proposals'),('proposals','experiments'),
              ('quality','mathematics'),('mathematics','development_audit'),('experiments','development_audit'),
              ('development_audit','final_evaluation'),('final_evaluation','independent_audit'),
              ('independent_audit','qualification'),('qualification','authorization'),('authorization','signals'),
              ('quality','signals'),('signals','risk'),('risk','intentions'),('intentions','execution'),
              ('execution','reconciliation'),('reconciliation','reports'),('reports','feedback'),
              ('feedback','proposals'),('reconciliation','risk')]
    connections = [dict(**{'from': start, 'to': end}, state='Required return check' if (start,end)==('reconciliation','risk') else 'Planned route') for start,end in routes]
    for edge in connections:
        if edge['from'] in {'proposals', 'feedback'}:
            edge['state'] = 'Connection unfinished'
    for stage in stages:
        report = next((row for row in activity.get('reporting',{}).get('stages',[]) if row['id']==stage['id']),None)
        stage.update(connection=report['connection'] if report else 'Runtime records not connected',
                     saved_records=report['records'] if report else [],record_sources=report['sources'] if report else [],
                     worker_observations=[row for row in activity.get('processes',[]) if row.get('kind')=='stage_worker' and row.get('stage')==stage['id']])
        if report:
            stage['reporting'] = report['connection']
            if report['records']: stage['state']='Saved record'
            elif report['connection']=='Reporting not implemented': stage['state']='Reporting not implemented'
        if stage['worker_observations']: stage['state']='Worker observed'
        feed=activity.get('stage_reports',{}).get('stages',{}).get(stage['id'])
        stage['producer_reports']=feed['reports'] if feed else []
        stage['producer_status']=feed['status'] if feed else None
        if feed:
            stage['connection']=stage['reporting']=feed['status']
            stage['state']='No report received' if not feed['reports'] and feed['status']=='No report received' else 'Report unavailable'
        if stage['id'] in {'mathematics','qualification','signals','feedback'}:
            stage_jobs=[job for job in activity.get('jobs',[]) if job.get('stage')==stage['id']]
            candidates=[('Producer report',row) for row in stage['producer_reports']]+[('Explicit job event',row) for row in stage_jobs]
            if candidates:
                current=[row for row in candidates if row[1]['state']=='Running']
                source,latest=max(current or candidates,key=lambda row:row[1]['observed_at'])
                stage.update(state=f"{latest['kind'].capitalize()}: {latest['state'].lower()}",reporting=source,activities=stage_jobs)
            continue
        jobs = [job for job in activity.get('jobs', []) if job.get('stage') == stage['id'] and job.get('kind') == 'operational']
        if jobs:
            stage.update(state=jobs[0]['state'], reporting='Explicit job event', activities=jobs)
    operational = {job.get('process_identity') for job in activity.get('jobs', []) if job.get('kind') == 'operational' and job.get('state') == 'Running'}
    engineering = [row for row in activity.get('processes', []) if row.get('stage') in {'verification', 'engineering'} and row.get('identity') not in operational]
    identities = {row.get('identity') for row in engineering if row.get('identity')}
    engineering += [job for job in activity.get('jobs', []) if job.get('kind') == 'engineering' and job.get('state') == 'Running' and job.get('process_identity') not in identities]
    return {'stages': stages, 'connections': connections, 'engineering': engineering,
            'note': 'Activity observations do not grant financial acceptance or permission to operate.'}
