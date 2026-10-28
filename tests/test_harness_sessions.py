import pytest

from compertum.harness.sessions import SessionError, SessionStore


def test_session_appends_and_resumes_messages(tmp_path):
    store = SessionStore(tmp_path)
    session = store.create()
    session.append("message", {"role": "system", "content": "system"})
    session.append("message", {"role": "user", "content": "hello"})
    session.append("outcome", {"status": "done", "steps": 1})
    restored = store.load(session.identity)
    assert restored.messages[1]["content"] == "hello"
    assert restored.records == 3
    assert store.list() == [session.identity]
    restored.append("message", {"role": "assistant", "content": "answer"})
    assert store.load(session.identity).messages[-1]["content"] == "answer"


def test_session_refuses_bad_identity_and_missing_start(tmp_path):
    store = SessionStore(tmp_path)
    with pytest.raises(SessionError):
        store.load("../secret")
    session = store.create()
    session.path.write_text('{"kind":"outcome","payload":{}}\n')
    with pytest.raises(SessionError, match="starting"):
        session.load()
