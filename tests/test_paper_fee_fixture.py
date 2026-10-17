"""Real record writers and the storage decision; full native lifecycle stays separate."""
import json,runpy
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.storage import sample_storage
from compertum.watchdog import check_storage
from test_execution_health import pair,connect
from test_paper_read_owner import owner


@pytest.mark.parametrize('published',[False,True],ids=['unreserved','published'])
def test_reference_growth_requires_a_record_reservation(owner,published):
    storage=owner.manager
    fixture=runpy.run_path(str(Path(__file__).parent/'helpers/paper_fee_fixture.py'))
    declaration_id=str(uuid4());declaration_manifest=dict(purpose='INVENTED_TEST_ONLY')
    before=sample_storage(storage.project)
    if published:
        manifest=fixture['publish_reference'](storage,declaration_id,declaration_manifest)
        task,path=fixture['reference_location'](storage.lease.project_id)
        row=storage.store.conn.execute('SELECT task,category,status,written,manifest FROM reservations WHERE path=?',
            (path.as_posix(),)).fetchone()
        assert row==(task,'records','PUBLISHED',manifest['size_bytes'],canonical(manifest).decode())
    else:
        path=Path('fee-fixture-reference.json')
        (storage.root/path).write_bytes(canonical(dict(declaration_id=declaration_id,manifest=declaration_manifest)))
    assert json.loads((storage.root/path).read_bytes())==dict(declaration_id=declaration_id,manifest=declaration_manifest)
    after=sample_storage(storage.project)
    reservations=[dict(path=path,maximum=maximum) for path,maximum in
        storage.store.conn.execute('SELECT path,maximum FROM reservations WHERE path IS NOT NULL')]
    observed=check_storage(after,reservations,previous=before)
    assert observed['reason']==(None if published else 'UNACCOUNTED_GROWTH')
