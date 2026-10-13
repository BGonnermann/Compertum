import pytest
from compertum.runtime.startup_record import check_report,expected_proof
from compertum.runtime.job_identity import capture_execution_identity
from compertum.runtime.identity import PeerObservation
from compertum.data.errors import DataError
from uuid import uuid4

@pytest.mark.parametrize('change',['float_pid','bool_pid','extra','schema','missing','plan'])
def test_nested_audit_startup_proof_has_strict_types(change):
 native=capture_execution_identity(PeerObservation(123,123456789,'S-1-5-21-1-2-3-1001','S-1-5-5-100-200'),
  {'task_id':str(uuid4()),'role':'experiment_auditor','code_sha256':'a'*64,'lock_sha256':'b'*64},'compertum.runtime.audit_worker',
  startup={'image_sha256':'c'*64,'volume_serial':123,'file_id':'d'*32,'plan_sha256':'e'*64})
 proof=expected_proof(native);value={'schema':'synthetic-native-unit-audit-v2','startup':proof};fields={'schema'}
 check_report(value,fields,native)
 if change=='float_pid':proof['pid']=123.0
 elif change=='bool_pid':proof['pid']=True
 elif change=='extra':proof['clean']=True
 elif change=='schema':proof['schema']='caller-proof'
 elif change=='missing':value.pop('startup')
 else:proof['plan_sha256']='0'*64
 with pytest.raises(DataError):check_report(value,fields,native)
