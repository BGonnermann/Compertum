"""Gather independently produced native evidence without decoding model outputs."""
import copy
from uuid import uuid4
import pytest
from test_native_seals import state
from test_native_campaign_review import finished_source
from compertum.auditor import AuditorController
from compertum.aggregate_evidence import collect_units,bind_unit_audit,encode_exports,decode_exports
from compertum.review_evidence import source_snapshot,sha
from compertum.data.encoding import canonical
from compertum.data.errors import DataError


def test_aggregate_requires_all_exact_native_unit_audits(state):
    controller,run,seal,remote=finished_source(state);audit=AuditorController(controller.coordinator,controller.storage)
    try:
        source,_,_=source_snapshot(controller.storage,run)
        with pytest.raises(DataError):collect_units(controller.storage,source)
        task=str(uuid4());audit.runs.register(task,run,0);audit.step(task);assert audit.active[2].wait()['exit_code']==0;audit.tick()
        items,records=collect_units(controller.storage,source)
        assert len(items)==len(records)==1 and records[0]['index']==0 and records[0]['artifact']['task_id']==task
        assert items[0]['state']['state']=='COMPLETED' and len(items[0]['history'])==4
        assert decode_exports(encode_exports({},items))==({},items)
        for field,value in [('source_state','STOPPED'),('source_history_sha256','0'*64),('source_run_id',str(uuid4())),('unit',False),('candidate_id','other'),('year',2022)]:
            forged=copy.deepcopy(items[0]['state']);forged['request'][field]=value;forged['request_sha256']=sha(canonical(forged['request']))
            with pytest.raises(DataError):bind_unit_audit(forged,source)
        stopped=copy.deepcopy(source);stopped['state']='STOPPED'
        with pytest.raises(DataError):bind_unit_audit(items[0]['state'],stopped)
    finally:audit.pause();controller.pause()
