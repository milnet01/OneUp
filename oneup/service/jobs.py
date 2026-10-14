"""One root child at a time: started, relayed to its caller, never killed by either side.

§4.3. The child writes to a job file under the service's runtime directory, never to a
pipe: a child writing to a pipe whose reader vanished dies of `SIGPIPE` mid-`zypper
dup`, the shape of the engine's first trap. A relay thread copies the file to the
client's descriptor as it grows. When the client leaves, the relay keeps draining
into nothing; when the service dies, the child still has its file. Either way the
transaction finishes (INV-5).
"""

from __future__ import annotations

import contextlib
import itertools
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

# How often the relay looks for more output once it has caught up. The child never
# waits on the relay, so this bounds only how late a chunk reaches the client.
_POLL_SECONDS = 0.05
_CHUNK = 65536

_SERIAL = itertools.count(1)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


class Job:
    """A started child, its relay, and what the session needs when it ends."""

    def __init__(self, *, op: str, args: dict, argv: Sequence[str], merge_stderr: bool,
                 runtime_dir: Path, session, on_end: Callable[[Job], None]) -> None:
        self.op = op
        self.args = args
        self.session = session
        self.status: int | None = None
        self._on_end = on_end
        runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = runtime_dir / f"job-{os.getpid()}-{next(_SERIAL)}.out"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            self.child = subprocess.Popen(  # noqa: S603 — argv from rootops' table, no shell
                list(argv),
                stdin=subprocess.DEVNULL,
                stdout=fd,
                # Unmerged stderr goes to the service's own, which is the journal under
                # systemd and outlives the service just as the job file does.
                stderr=subprocess.STDOUT if merge_stderr else None,
                # Its own session: nothing aimed at the service's process group reaches it.
                start_new_session=True,
            )
        except OSError:
            os.close(fd)
            self.path.unlink(missing_ok=True)
            raise
        os.close(fd)
        out_r, self._out_w = os.pipe()
        status_r, self._status_w = os.pipe()
        self.client_fds = (out_r, status_r)
        threading.Thread(target=self._relay, daemon=True).start()

    def stop(self) -> None:
        """`SIGTERM` to the child alone; zypper turns it into exit 105 (§4.6)."""
        if self.child.poll() is None:
            with contextlib.suppress(OSError):
                self.child.send_signal(signal.SIGTERM)

    def _relay(self) -> None:
        listening = True
        with open(self.path, "rb") as source:
            while True:
                chunk = source.read(_CHUNK)
                if not chunk:
                    if self.child.poll() is None:
                        time.sleep(_POLL_SECONDS)
                        continue
                    # Exited: whatever it wrote is already in the file, so one more
                    # empty read means the relay has drained it.
                    chunk = source.read(_CHUNK)
                    if not chunk:
                        break
                if listening:
                    try:
                        _write_all(self._out_w, chunk)
                    except OSError:           # the client left; the job does not
                        listening = False
        rc = self.child.returncode
        # The shell's convention, which the engine already reads: 128+N for signal N.
        self.status = 128 - rc if rc < 0 else rc
        with contextlib.suppress(OSError):
            _write_all(self._status_w, f"{self.status}\n".encode("ascii"))
        for fd in (self._out_w, self._status_w):
            with contextlib.suppress(OSError):
                os.close(fd)
        self.path.unlink(missing_ok=True)
        self._on_end(self)


def run_captured(argv: Sequence[str]) -> tuple[int, str]:
    """A short root child run to completion inside the service, for its own checks.

    Used for `orphans-unneeded` before an `orphans-remove` (§4.2) and for a session's
    re-enables (§4.5). Not a job: the caller sees none of it.
    """
    try:
        done = subprocess.run(  # noqa: S603 — argv from rootops' table, no shell
            list(argv), stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False)
    except OSError as exc:
        return 127, str(exc)
    return done.returncode, done.stdout
