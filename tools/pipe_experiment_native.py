"""Disabled native candidate. Activation requires a separately reviewed copy."""
raise RuntimeError('PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED')

import ctypes as c
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from compertum.runtime._pipes import NativePipeAPI, CLIENT_ACCESS, SECURITY_ATTRIBUTES
from compertum.runtime._windows import HANDLE, DWORD, BOOL, OwnedHandle
from compertum.runtime.jobs import JobAPI, create_suspended
from prepare_pipe_experiment import (
    PIPE_NAME, LABEL, BOUNDS, PREPARATION, prepare, from_record, identity_fields,
    checked_observation, check_pair, descriptor, failure_fields,
)
from prepare_pipe_policy import Observation, proposed_outputs
from pipe_experiment_identity import IdentityReader
from evidence_folder import EvidenceFolder, EvidenceJournal, regular_folder

ROOT = Path(r'C:\Users\bgonn\Desktop\Compertum')
FOLDER = ROOT / 'artifacts/m5/simulated-evidence-next-01'
OBSERVATION = ROOT / 'artifacts/m5/local-economics-20261017-01/pipe-identity01-result.json'
PROPOSAL = ROOT / 'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json'
MANIFEST = ROOT / 'docs/M5_PIPE_EXPERIMENT_BINDINGS.json'


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def read_checked(path, expected_hash, limit):
    regular_folder(path.parent)
    info = path.lstat()
    require(not info.st_file_attributes & 0x400 and path.is_file() and info.st_size <= limit,
            'INPUT_FILE_DENIED')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit and hashlib.sha256(raw).hexdigest() == expected_hash, 'INPUT_HASH_CHANGED')
    return json.loads(raw)


def inputs():
    # The approved launcher binds this manifest and all source hashes before launch.
    manifest = json.loads(MANIFEST.read_text())
    observed = read_checked(OBSERVATION, manifest['identity_file_sha256'], 16384)
    proposal = read_checked(PROPOSAL, manifest['proposal_file_sha256'], 16384)
    candidate = prepare(observed, proposal, PREPARATION)
    require(candidate == manifest['prepared'], 'EXPERIMENT_BINDING_CHANGED')
    require(manifest['status'] == 'PREPARED_NOT_AUTHORIZED', 'MANIFEST_STATUS_CHANGED')
    return manifest, identity_fields(from_record(observed['process']))


def verify_peer(api, reader, pipe, server_side, retained, expected_identity):
    with api.peer(pipe, server_side=server_side) as peer:
        require((peer.pid, peer.creation_filetime) == (retained.pid, retained.creation_time),
                'PIPE_PEER_CHANGED')
        with api.open_process(peer.pid) as handle:
            actual = reader.process(handle, peer.pid)
            checked_observation(actual, actual, expected_identity, retained=retained)
            yield_value = actual
    return yield_value


def create_server(api, observation):
    api._admit()
    sd, size = HANDLE(), DWORD()
    api.checked(api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        descriptor(observation), 1, c.byref(sd), c.byref(size)), 'ConvertSecurityDescriptor')
    try:
        sa = SECURITY_ATTRIBUTES(c.sizeof(SECURITY_ATTRIBUTES), sd, False)
        value = api.CreateNamedPipeW(PIPE_NAME, 3 | 0x40000000 | 0x00080000,
                                    8, 1, 65540, 65540, 5000, c.byref(sa))
        pipe = api._handle(value, 'CreateNamedPipeW')
        try:
            require(not api.handle_flags(pipe) & 1, 'INHERITED_HANDLE_DENIED')
            return pipe
        except BaseException:
            pipe.close()
            raise
    finally:
        api.LocalFree(sd)


def verify_dacl(api, pipe, expected):
    adv = c.WinDLL('advapi32', use_last_error=True)
    get = adv.GetSecurityInfo
    get.argtypes = [HANDLE, DWORD, DWORD, c.POINTER(HANDLE), c.POINTER(HANDLE),
                    c.POINTER(HANDLE), c.POINTER(HANDLE), c.POINTER(HANDLE)]
    get.restype = DWORD
    convert = adv.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [HANDLE, DWORD, DWORD, c.POINTER(HANDLE), c.POINTER(DWORD)]
    convert.restype = BOOL
    sd, text = HANDLE(), HANDLE()
    require(get(pipe.get(), 6, 4, None, None, None, None, c.byref(sd)) == 0, 'DACL_QUERY_FAILED')
    try:
        api.checked(convert(sd, 1, 4, c.byref(text), None), 'ConvertSecurityDescriptorToString')
        actual = c.wstring_at(text)
        # Windows removes leading zeroes from numeric access masks.
        require(actual.replace('0x100083', '0x00100083') == expected, 'APPLIED_DACL_DIFFERS')
    finally:
        if text.value:
            api.LocalFree(text)
        api.LocalFree(sd)


def client_exchange(parent_pid, parent_created):
    _, expected_identity = inputs()
    api, jobs = NativePipeAPI(), JobAPI()
    reader = IdentityReader(api)
    with api.open_process(os.getpid()) as own, api.open_process(parent_pid) as parent:
        own_observation = reader.current(own, expected_identity)
        server_observation = reader.process(parent, parent_pid)
        require(server_observation.creation_time == parent_created, 'PARENT_PROCESS_CHANGED')
        check_pair(server_observation, own_observation, expected_identity)
        with api.open_file(PIPE_NAME, CLIENT_ACCESS, 0, flags=0x40100000) as pipe:
            require(not api.handle_flags(pipe) & 1, 'INHERITED_HANDLE_DENIED')
            verify_peer(api, reader, pipe, False, server_observation, expected_identity)
            reader.current(own, expected_identity, retained=own_observation)
            challenge = api.read_frame(pipe, time.monotonic() + 5)
            require(len(challenge) == 32, 'CHALLENGE_SIZE_DENIED')
            api.write_frame(pipe, hashlib.sha256(b'pipe-experiment-v1' + challenge).digest(), time.monotonic() + 5)
            require(api.read_frame(pipe, time.monotonic() + 5) == b'ACK', 'ACKNOWLEDGEMENT_DENIED')
            # Remain connected without issuing concurrent I/O during server cancellation.
            until = time.monotonic() + 7
            while time.monotonic() < until:
                require(api.WaitForSingleObject(parent.get(), 0) == 258, 'PARENT_EXITED')
                time.sleep(.05)
            require(api.read_frame(pipe, time.monotonic() + 5) == b'CANCELLED', 'CANCELLATION_ACK_DENIED')
            reader.current(own, expected_identity, retained=own_observation)
            verify_peer(api, reader, pipe, False, server_observation, expected_identity)
    return 0


def client(parent_pid, parent_created):
    started = time.monotonic()
    def poll():
        require(time.monotonic()-started < 30, 'CLIENT_DEADLINE')
    output = EvidenceFolder(FOLDER, proposed_outputs(), poll, writable={LABEL+'.log'})
    try:
        client_exchange(parent_pid, parent_created)
        record = dict(status='CLIENT_EXCHANGE_OBSERVED', elapsed_seconds=time.monotonic()-started)
    except BaseException as error:
        record = dict(status='FAILED', elapsed_seconds=time.monotonic()-started, **failure_fields(error))
        output.save_failure(LABEL+'.log', record)
        return 1
    output.save(LABEL+'.log', record)
    output.finish()
    return 0


def server():
    manifest, expected_identity = inputs()
    api, jobs = NativePipeAPI(), JobAPI()
    reader = IdentityReader(api)
    started = time.monotonic()
    result = dict(status='FAILED', diagnostic_only=True, production_admission=False,
                  native_security_qualification=False, broker_actions=0, retries=0,
                  pipe_name=PIPE_NAME, native_negative_cases='UNVERIFIED')
    def poll():
        require(time.monotonic() - started < 30, 'EXPERIMENT_DEADLINE')
        # The enclosing maintenance job enforces memory, capacity, and 120 seconds.
    output = EvidenceFolder(FOLDER, proposed_outputs(), poll,
                            writable={LABEL+'.result.json', LABEL+'.progress.jsonl'})
    journal = EvidenceJournal(output, LABEL+'.progress.jsonl', poll)
    child = thread = pipe = None
    with api.open_process(os.getpid()) as own:
      try:
        current = reader.current(own, expected_identity)
        # No inherited handles, shell, breakaway, or new security context.
        env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR') if key in os.environ}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONOPTIMIZE='0',
                   PYTHONPATH=os.pathsep.join([str(ROOT/'tools'),str(ROOT/'src')]), __PYVENV_LAUNCHER__=sys.executable,
                   TEMP=os.environ['TEMP'], TMP=os.environ['TMP'],
                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        info = create_suspended(jobs, [sys.executable, '-B', str(Path(__file__).resolve()),
                                      'client', str(current.pid), str(current.creation_time)], env, ROOT)
        child, thread = OwnedHandle(jobs, info.process), OwnedHandle(jobs, info.thread)
        member = BOOL()
        jobs.checked(jobs.IsProcessInJob(child.get(), None, c.byref(member)), 'ChildJobMembership')
        require(member.value, 'CHILD_NOT_IN_JOB')
        client_observation = reader.process(child, info.pid)
        check_pair(current, client_observation, expected_identity)
        reader.current(own, expected_identity, retained=current)
        checked_observation(reader.process(child, info.pid), client_observation,
                            expected_identity, retained=client_observation)
        journal.emit('identities_checked')
        pipe = create_server(api, current)
        result['pipe_created'] = True
        verify_dacl(api, pipe, descriptor(current))
        result['applied_dacl_matches'] = True
        jobs.checked(jobs.ResumeThread(thread.get()) == 1, 'ResumeClient')
        thread.close(); thread = None
        api.connect(pipe, time.monotonic() + 5)
        verify_peer(api, reader, pipe, True, client_observation, expected_identity)
        reader.current(own, expected_identity, retained=current)
        nonce = os.urandom(32)
        api.write_frame(pipe, nonce, time.monotonic() + 5)
        require(api.read_frame(pipe, time.monotonic() + 5) ==
                hashlib.sha256(b'pipe-experiment-v1'+nonce).digest(), 'EXCHANGE_MISMATCH')
        result['exchange_verified'] = True
        api.write_frame(pipe, b'ACK', time.monotonic() + 5)
        from compertum.runtime.errors import RuntimeRefused
        try:
            api.read_frame(pipe, time.monotonic() + 5)
        except RuntimeRefused as error:
            require(error.code == 'PIPE_DEADLINE_EXCEEDED', 'CANCELLATION_UNVERIFIED')
            # _io returns only after its one-second cancellation completion check.
            api._admit()
        else:
            raise RuntimeError('EXPECTED_READ_TIMEOUT_MISSING')
        result['cancellation_verified'] = True
        reader.current(own, expected_identity, retained=current)
        verify_peer(api, reader, pipe, True, client_observation, expected_identity)
        api.write_frame(pipe, b'CANCELLED', time.monotonic() + 5)
        require(jobs.WaitForSingleObject(child.get(), 5000) == 0, 'CLIENT_EXIT_UNVERIFIED')
        code = DWORD()
        jobs.checked(jobs.GetExitCodeProcess(child.get(), c.byref(code)), 'ClientExitCode')
        require(code.value == 0, 'CLIENT_FAILED')
        result.update(status='COMMUNICATION_OBSERVED', child_exit_code=0,
                      server_identity_sha256=hashlib.sha256(json.dumps(asdict(current), sort_keys=True).encode()).hexdigest(),
                      client_identity_sha256=hashlib.sha256(json.dumps(asdict(client_observation), sort_keys=True).encode()).hexdigest())
        journal.emit('exchange_and_cancellation_observed')
      except BaseException as error:
        result.update(status='FAILED', **failure_fields(error))
      finally:
        cleanup_errors = []
        try:
            if child is not None:
                if jobs.WaitForSingleObject(child.get(), 0) != 0:
                    jobs.checked(jobs.TerminateProcess(child.get(), 125), 'StopClient')
                result['child_exit_observed'] = jobs.WaitForSingleObject(child.get(), 5000) == 0
                if not result['child_exit_observed']:
                    result['status'] = 'FAILED'
                else:
                    code = DWORD()
                    jobs.checked(jobs.GetExitCodeProcess(child.get(), c.byref(code)), 'ClientCleanupExitCode')
                    result['child_exit_code'] = code.value
        except BaseException as error:
            cleanup_errors.append(failure_fields(error))
        for handle in (thread, child, pipe):
            if handle is not None:
                try:
                    handle.close()
                except BaseException as error:
                    cleanup_errors.append(failure_fields(error))
        # Closing an existing stream needs no execution-time poll.
        try:
            journal.stream.close()
        except BaseException as error:
            cleanup_errors.append(failure_fields(error))
        if cleanup_errors:
            result.update(status='FAILED', cleanup_errors=cleanup_errors)
        result['elapsed_seconds'] = time.monotonic() - started
        if result['status'] == 'FAILED':
            output.save_failure(LABEL+'.result.json', result)
        else:
            try:
                output.save(LABEL+'.result.json', result)
                output.finish()
            except BaseException:
                # The enclosing launcher must reject incomplete output and save closure.
                raise
    return 0 if result['status'] == 'COMMUNICATION_OBSERVED' else 1


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'client':
        raise SystemExit(client(int(sys.argv[2]), int(sys.argv[3])))
    require(len(sys.argv) == 1, 'ARGUMENTS_DENIED')
    raise SystemExit(server())
