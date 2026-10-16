"""One root child at a time: started, read by its caller, never killed by either side.

§4.3. The child writes to a job file under the service's runtime directory, never to a
pipe: a child writing to a pipe whose reader vanished dies of `SIGPIPE` mid-`zypper
dup`, the shape of the engine's first trap. The client pulls the file with `Read`; no
descriptor is ever handed over, because SELinux stops the system bus passing one
(ONEUP-0282). When the client leaves, nothing reads the file; when the service dies,
the child still has it. Either way the transaction finishes (INV-5).
"""

from __future__ import annotations

import contextlib
import itertools
import os
import signal
import subprocess
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

CHUNK = 65536                     # the most one `Read` returns (§4.3)

_SERIAL = itertools.count(1)


def clear_stale(runtime_dir: Path) -> None:
    """Delete job files an earlier instance left (§4.3). A child still writing to one
    is unaffected: an unlinked file stays writable."""
    for path in runtime_dir.glob("job-*.out"):
        path.unlink(missing_ok=True)


class Job:
    """A started child, its job file, and what the session needs when it ends."""

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
        threading.Thread(target=self._wait, daemon=True).start()

    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def read(self, offset: int) -> bytes:
        """At most `CHUNK` bytes of the output from `offset` on."""
        try:
            with open(self.path, "rb") as source:
                source.seek(offset)
                return source.read(CHUNK)
        except OSError:
            return b""

    def discard(self) -> None:
        """Delete the job file; only once the child has ended (§4.3)."""
        self.path.unlink(missing_ok=True)

    def stop(self) -> None:
        """`SIGTERM` to the child alone; zypper turns it into exit 105 (§4.6)."""
        if self.child.poll() is None:
            with contextlib.suppress(OSError):
                self.child.send_signal(signal.SIGTERM)

    def _wait(self) -> None:
        rc = self.child.wait()
        # The shell's convention, which the engine already reads: 128+N for signal N.
        # Set only once the child has exited, so everything it wrote is in the file.
        self.status = 128 - rc if rc < 0 else rc
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
