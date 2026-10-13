"""Full fit validation precedes publication; owner proof binding stays lightweight."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.campaign_contract import UNITS
from compertum.modeling.checkpoints import FitCheckpoint
from test_campaign_contract import bundle
from test_fit_checkpoints import checkpoint


def test_malformed_generated_fit_is_rejected_before_worker_returns(monkeypatch):
 from compertum.modeling.campaign import compute_campaign_unit
 import compertum.modeling.checkpoints as m
 campaign=bundle();identity=json.loads(campaign.content)['identity'];index=next(i for i,u in enumerate(UNITS) if u.phase=='fit')
 value=json.loads(checkpoint().content);value['model']['scaler']['scale'][0]=0
 value['model_sha256']=hashlib.sha256(canonical(value['model'])).hexdigest()
 raw=canonical(value);bad=FitCheckpoint(raw,hashlib.sha256(raw).hexdigest())
 monkeypatch.setattr(m,'prepare_fit_checkpoint',lambda *a,**kw:bad)
 with pytest.raises(DataError,match='INVALID_MODEL_SCALE'):compute_campaign_unit(campaign,index,identity=identity)


def test_structural_fit_reader_preserves_bindings_without_numerical_imports(tmp_path):
 fit=checkpoint();value=json.loads(fit.content);p=tmp_path/'fit.json';p.write_bytes(fit.content)
 args={k:value[k] for k in ('candidate_id','year','training_start','training_end')}
 args.update(market_sha256=value['source_market_sha256'],expected_sha256=fit.sha256)
 script="""
import importlib.abc,json,sys
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'numpy','pandas','scipy','sklearn','exchange_calendars'} or fullname.startswith('compertum.modeling'):raise AssertionError(fullname)
sys.meta_path.insert(0,Deny())
from compertum.simulation.fit_record import read_binding
from pathlib import Path
read_binding(Path(sys.argv[1]).read_bytes(),**json.loads(sys.argv[2]))
"""
 result=subprocess.run([sys.executable,'-B','-c',script,str(p),json.dumps(args)],capture_output=True,text=True,timeout=20)
 assert result.returncode==0,result.stderr


@pytest.mark.parametrize('field',['candidate_id','year','training_start','training_end','source_market_sha256','fit_rows_sha256','fit_manifest_sha256','model_sha256'])
def test_structural_fit_reader_refuses_changed_identity_or_nested_hash(field):
 from compertum.simulation.fit_record import read_binding
 fit=checkpoint();value=json.loads(fit.content)
 args={k:value[k] for k in ('candidate_id','year','training_start','training_end')};args['market_sha256']=value['source_market_sha256']
 if field=='year':value[field]=2022
 elif field=='candidate_id':value[field]='ridge-h05-a001'
 elif field in ('training_start','training_end'):value[field]='2016-01-04'
 else:value[field]='0'*64
 raw=canonical(value)
 with pytest.raises(DataError):read_binding(raw,expected_sha256=hashlib.sha256(raw).hexdigest(),**args)