"""Drain child output into reserved files without giving children file handles.

The existing Windows Job must still contain the process and descendants.
An output failure terminates the process. The caller must reject the stage.
"""
import subprocess
import threading


class CapturedProcess:
    def __init__(self, args, stdout, stderr, poll, **options):
        self.outputs = (stdout, stderr)
        self.check = poll
        self.error = None
        self.check()
        self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
        self.threads = []
        for source, target in zip((self.process.stdout, self.process.stderr), self.outputs):
            worker = threading.Thread(target=self._drain, args=(source, target), daemon=True)
            self.threads.append(worker)
            worker.start()

    def _drain(self, source, target):
        try:
            while True:
                data = source.read(4096)
                if not data:
                    break
                target.write(data)
        except BaseException as error:
            self.error = error
            self.process.kill()
        finally:
            source.close()
            target.close()

    def poll(self):
        self.check()
        if self.error is not None:
            raise RuntimeError('CHILD_EVIDENCE_OUTPUT_FAILED') from self.error
        return self.process.poll()

    def finish(self, timeout=5):
        """Call after the enclosing Job has closed all child handles."""
        import time
        deadline = time.monotonic() + timeout
        for worker in self.threads:
            worker.join(max(0, deadline - time.monotonic()))
        if any(worker.is_alive() for worker in self.threads):
            raise TimeoutError('EVIDENCE_DRAIN_DEADLINE')
        if self.error is not None:
            raise RuntimeError('CHILD_EVIDENCE_OUTPUT_FAILED') from self.error
