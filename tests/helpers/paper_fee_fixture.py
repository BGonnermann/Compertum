"""Keep the test-only fee reference inside checked, reserved artifact storage."""
from pathlib import Path
from uuid import NAMESPACE_URL,uuid5
from compertum.data.encoding import canonical


def reference_location(project_id):
    task=str(uuid5(NAMESPACE_URL,'https://example.invalid/compertum/native-fee-reference/'+project_id))
    return task,Path('artifacts')/'runs'/task/'fee-fixture-reference.json'


def publish_reference(storage,declaration_id,manifest):
    task,relative=reference_location(storage.lease.project_id)
    raw=canonical(dict(declaration_id=declaration_id,manifest=manifest))
    grant=storage.reserve_bytes(task,'records',len(raw))
    writer=storage.open_artifact(grant,relative.as_posix())
    try:
        writer.write(raw)
        return writer.publish()
    finally:
        writer.close()
