"""Private owner-bound campaign proof retained only across cooperative phases."""
import hashlib,json
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.persistence import checked_path
from compertum.runtime.inherited_input import read_input
from . import campaign_runs as campaign

MIB=1024**2


class _Verification:
    def __init__(self,runs,run_id):
        self.runs=runs;self.run_id=run_id;self.closed=False;self.done=False
        self.bundle=None;self.previous=None;self.previous_index=None;self.position=0
        self.handles=[];self.directories=set()
        with runs.store._live() as guard:
            self.state=runs._load(run_id)
            if not campaign.is_campaign(self.state):raise DataError('RUN_INPUT_KIND')
            self.head=self._head();self.owner=runs.owner
            self.records=[(i,self.state['outcomes'][unit.key]) for i,unit in enumerate(campaign.UNITS)
                if self.state['outcomes'].get(unit.key,{}).get('status')=='COMPLETED']
            guard.resources.append(self)

    def _head(self):
        return self.runs.store.conn.execute('SELECT seq,sha256 FROM baseline_history WHERE run_id=? ORDER BY seq DESC LIMIT 1',(self.run_id,)).fetchone()

    def _current(self):
        if (self.closed or self.runs.owner!=self.owner or self._head()!=self.head
                or self.runs._load(self.run_id)!=self.state):raise DataError('CAMPAIGN_ADMISSION_CHANGED')

    def _constraints(self):
        from compertum.development_seals import check_campaign_seal
        from .runs import runtime_identity
        check_campaign_seal(self.runs.store,self.state)
        if self.state['identity']!=json.loads(canonical(runtime_identity())):raise DataError('RUN_IDENTITY_CHANGED')

    def _read(self,artifact,maximum):
        if (not isinstance(artifact,dict) or type(artifact.get('size_bytes')) is not int
                or not 0<artifact['size_bytes']<=maximum or not isinstance(artifact.get('path'),str)
                or not artifact['path'].startswith(f'artifacts/runs/{self.run_id}/baseline/')):
            raise DataError('RUN_ARTIFACT_CORRUPT')
        with self.runs.store._live() as guard:
            root=self.runs.storage.root;path=checked_path(root,root/artifact['path']);current=root
            for component in path.parent.relative_to(root).parts:
                current=current/component
                if current not in self.directories:
                    self.handles.append(guard.api.open_directory(current));self.directories.add(current)
            # No write/delete sharing. Existing writers and alias replacements refuse.
            handle=guard.api.open_file(path,0x80000000,1);self.handles.append(handle)
            info=guard.api.file_info(handle)
            if info.attributes&(0x400|0x10) or info.links!=1 or (info.size_hi<<32|info.size_lo)!=artifact['size_bytes']:
                raise DataError('RUN_ARTIFACT_CORRUPT')
            raw=read_input(guard.api,handle,artifact['size_bytes'])
            if hashlib.sha256(raw).hexdigest()!=artifact['sha256']:raise DataError('RUN_ARTIFACT_CORRUPT')
            return raw

    def advance(self):
        """Validate at most one bounded artifact. Never keep a DB transaction open."""
        if self.closed:raise DataError('CAMPAIGN_ADMISSION_CHANGED')
        with self.runs.store._live():
            self._current()
            if self.done:return True
            if self.bundle is None:
                self._constraints()
                if self.state['input_artifact'] is None:raise DataError('RUN_INPUT_INCOMPLETE')
                raw=self._read(self.state['input_artifact'],20*MIB)
                if hashlib.sha256(raw).hexdigest()!=self.state['request_sha256']:raise DataError('RUN_ARTIFACT_CORRUPT')
                self.bundle=campaign.read_bundle(self.state,raw)
            elif self.position<len(self.records):
                index,record=self.records[self.position];unit=campaign.UNITS[index]
                dependency=campaign._dependency(self.state,index)
                if record['dependency_sha256']!=(dependency['payload_sha256'] if dependency else None):raise DataError('CAMPAIGN_DEPENDENCY_INVALID')
                body=campaign.read_payload(self.state,record,self._read(record['artifact'],16*MIB))
                previous=self.previous if unit.fit_unit==self.previous_index else None
                campaign._owner_binding(self.runs,self.state,body,self.bundle,index,previous)
                self.previous=body if unit.phase=='fit' else None
                self.previous_index=index if unit.phase=='fit' else None
                self.position+=1
            else:
                self._constraints();self.done=True
            return self.done

    def check(self,runs,state):
        with runs.store._live():
            if runs is not self.runs or state!=self.state or not self.done:raise DataError('CAMPAIGN_ADMISSION_CHANGED')
            self._current();self._constraints()
            return self.bundle

    def close(self):
        if self.closed:return
        self.closed=True;self.bundle=None;self.previous=None;failed=None
        for handle in reversed(self.handles):
            try:handle.close()
            except Exception as error:failed=error
        self.handles=[];self.directories.clear();self.state=None;self.records=[];self.head=None;self.runs=None;self.owner=None
        if failed is not None:raise failed
