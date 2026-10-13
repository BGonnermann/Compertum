"""Owner teardown cannot dispose a sink belonging to an unresolved audit Job."""
from types import SimpleNamespace
import pytest
from compertum.storage import BoundedWriter
from compertum.runtime.errors import RuntimeRefused


@pytest.mark.parametrize('published',[False,True])
def test_writer_close_cannot_bypass_unresolved_job(published):
    writer=object.__new__(BoundedWriter);writer.closed=published
    writer._final_audit_job=SimpleNamespace(closed=False,audit_lifetime=SimpleNamespace(exit_verified=False))
    with pytest.raises(RuntimeRefused,match='FINAL_AUDIT_CLEANUP_UNVERIFIED'):writer.close()
    assert writer.closed is published


def test_writer_publication_requires_observed_job_exit():
    writer=object.__new__(BoundedWriter);writer.closed=False;writer.manifest=None
    writer._final_audit_job=SimpleNamespace(closed=False,audit_lifetime=SimpleNamespace(exit_verified=False))
    with pytest.raises(RuntimeRefused,match='JOB_EXIT_UNVERIFIED'):writer.publish()
    assert not writer.closed and writer.manifest is None
