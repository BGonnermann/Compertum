"""Test-only bounded handshake after the actual worker validates its saved fit."""
from pathlib import Path
import json,os,time
import compertum.runtime.campaign_worker as worker
original=worker.compute_campaign_unit

def entered(campaign,unit,**kwargs):
    assert unit==4 and kwargs.get('fit_checkpoint') is not None
    marker=Path(os.environ['COMPERTUM_FIXTURE_EVALUATION_MARKER'])
    temporary=marker.with_suffix('.partial')
    temporary.write_text(json.dumps({'unit':unit,'phase':'evaluate','fit_supplied':True}),encoding='utf-8')
    temporary.rename(marker)
    time.sleep(30)  # Fixture parent exits after observing the marker; Job must kill us.
    return original(campaign,unit,**kwargs)

worker.compute_campaign_unit=entered
raise SystemExit(worker.main())
