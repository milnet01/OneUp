"""Run a child process and report what it did.

Two forms. `run` is the immediate one: run a command, wait, hand back its status
and its output. `stream_filtered` is the transaction one: read a child's merged
output line by line, pass every line through unchanged, mirror it to the
transaction log and turn zypper's own chatter into `@@PROGRESS@@`.

Both take an optional `deadline`, which is §4.3.2's per-call budget: one runner
owning the seconds and what to do on expiry, so the per-repository budget
generalises to any call. Python still cannot signal a ROOT child (§2.2), so a
privileged call that must be stoppable keeps the `sudo timeout` shape — the
deadline here is bookkeeping around it, not a replacement for it. Expiry
reports 124, `timeout`'s own "I killed it" code, so both routes read alike.

Fixed argv only, never a shell (`docs/standards/coding.md` §5.1). Nothing here
builds a command by interpolating text.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

from . import markers, parsers, runstate


def run(
    argv: Sequence[str],
    *,
    merge_stderr: bool = False,
    env: Mapping[str, str] | None = None,
    stream: bool = False,
    deadline: float | None = None,
) -> tuple[int, str]:
    """Run `argv`; return its exit status and its captured stdout.

    With `merge_stderr`, stderr is folded into the returned text — the shape
    `sudo_capture -e` has today.

    `env` overlays the engine's own environment for this child only. The Bash
    engine writes `LC_ALL=C zypper …` as a per-command prefix; putting the same
    setting in `os.environ` would reach every later child instead.

    With `stream`, the child INHERITS our stdout and stderr instead of being
    captured, and the returned text is empty. Some of what the Bash engine runs
    is not captured at all — `refresh_repos`' per-repository `sudo timeout …
    refresh` writes straight to the run's stdout and its log — and building
    those on the capturing form sends their output nowhere.
    """
    try:
        if stream:
            completed = subprocess.run(  # noqa: S603 — fixed argv list, no shell, as above
                list(argv),
                check=False,
                env={**os.environ, **env} if env else None,
                timeout=deadline,
            )
            return completed.returncode, ""

        completed = subprocess.run(  # noqa: S603 — fixed argv list, no shell; the caller
            # builds every element, and nothing here is interpolated from engine or user text.
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL,
            text=True,
            check=False,
            env={**os.environ, **env} if env else None,
            timeout=deadline,
        )
    except subprocess.TimeoutExpired as expiry:
        partial = expiry.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode(errors="replace")
        return DEADLINE_EXPIRED, partial
    return completed.returncode, completed.stdout or ""


def succeeds(argv: Sequence[str]) -> bool:
    """True when `argv` exits 0. Output is discarded."""
    return run(argv)[0] == 0


# Whether this run has already announced the stop. The console block and the
# hint belong to the FIRST honoured stop only; every later boundary check is
# silent.
_STOP_ANNOUNCED = False


def stop_pending() -> bool:
    """Is a stop pending at this boundary? `stop_pending`'s decision half.

    Three tests, and the middle one is the one a natural translation drops.
    `stop.request` must exist; `run.state` must **also** exist; and the request
    must be NEWER. A `stat()` with a not-found fallback of 0 turns the middle
    test into its opposite — then a leftover request (the window never deletes
    one, and a `SIGKILL`ed engine never runs `cleanup`) aborts the next run
    before it starts. `docs/specs/ONEUP-0054-python-engine.md` §4.1.1 states it:
    with no `run.state` at all no stop is ever honoured.

    The newness test is load-bearing too. The run-state file is written the
    moment the run commits, so it doubles as the run's start stamp — deleting a
    leftover request at start-up instead would race, silently swallowing a stop
    clicked in the moment before the engine got there.
    """
    global _STOP_ANNOUNCED
    stop, started = runstate.stop_and_run_mtimes()
    if stop is None or started is None or stop <= started:
        return False
    if not _STOP_ANNOUNCED:
        _STOP_ANNOUNCED = True
        markers.out("")
        markers.out("Stopping at your request — the step that was running has finished, and")
        markers.out("nothing further will be started.")
        markers.hint(
            "Stopped at your request. Anything already installed stays installed — a stop "
            "never interrupts an install half-way, because that can leave programs broken. "
            "Run the update again whenever you like."
        )
    return True


def stop_announced() -> bool:
    """Has a stop already been honoured this run? The summary's `STOP_HONOURED`."""
    return _STOP_ANNOUNCED


# `timeout`'s own "I killed it" status, so a Python-side expiry and the
# `sudo timeout` wrapper's report the same thing to the same callers.
DEADLINE_EXPIRED = 124

# How many progress lines the DOWNLOAD pass recognised. The ONEUP-0046
# stale-parser canary reads it: a transaction that installed packages while this
# stayed zero is the signature of zypper having renamed the lines we parse, and
# silence is exactly how the "download size: 0 B" bug hid for weeks.
PROGRESS_SEEN = 0


def stream_filtered(argv: Sequence[str], *, step: str, phase: str, log: Path,
                    append: bool, deadline: float | None = None) -> int:
    """Run `argv`, print every line unchanged, log it, and emit progress markers.

    `phase` is a parameter, never a constant: the COMMIT pass re-reads every
    cached package and prints `Preloading: … [already in cache]` for each, so a
    hard-coded "download" flips the window back to Downloading and resets its
    byte total to zero at the moment installing begins (ONEUP-0085).

    Whether the transaction log is TRUNCATED or appended to is likewise a
    per-pass argument. The download pass truncates and the commit pass appends,
    because the download pass's output is where a download failure's evidence
    lives — and the ONEUP-0094 retry reads a snapshot of it.

    Returns the child's exit status. A line we failed to match must never make
    the transaction itself look like it failed.
    """
    global PROGRESS_SEEN
    preloaded = seen = got = 0
    want = 0
    child = subprocess.Popen(  # noqa: S603 — fixed argv list, no shell, as in `run`
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    expired = False

    def _expire() -> None:
        nonlocal expired
        expired = True
        child.kill()

    timer = None
    if deadline is not None:
        # A watchdog rather than a per-line check: a child that prints nothing
        # at all is exactly the case a budget exists for, and a check that only
        # runs when a line arrives can never fire on it.
        timer = threading.Timer(deadline, _expire)
        timer.start()
    with log.open("a" if append else "w", encoding="utf-8", errors="replace") as handle:
        for raw in child.stdout:
            line = raw.rstrip("\n")
            markers.out(line)
            handle.write(line + "\n")
            handle.flush()
            total = parsers.progress_total_bytes(line)
            if total is not None:
                want = total
            elif line.startswith("Preloading:"):
                # The parallel prefetch: zypper gives it neither a counter nor a
                # size, so all we can pass on is the tally and the transaction
                # total. Emitted directly rather than through `emit_progress`,
                # which needs an `n/m` there is none of here.
                preloaded += 1
                seen += 1
                markers.marker("PROGRESS", f"{step}|{preloaded}|0|{phase}|0|{want}")
            elif line.startswith("Retrieving:"):
                got += parsers.retrieving_bytes(line)
                if markers.emit_progress(step, parsers.retrieving_fraction(line),
                                         phase, str(got), str(want)):
                    seen += 1
            elif line.startswith("(") and (
                    "Installing:" in line or "Removing:" in line or "Upgrading:" in line):
                if markers.emit_progress(step, parsers.install_fraction(line), "install"):
                    seen += 1
    rc = child.wait()
    if rc < 0:
        # A child killed by a signal reports -N here where a shell reports
        # 128+N, and 143 is what the caller reads a stop from.
        rc = 128 - rc
    if timer is not None:
        timer.cancel()
    if expired:
        # A flag set by the watchdog itself, never `timer.is_alive()`: a timer
        # that fires in the moment between the child exiting and the check is
        # indistinguishable from one that never fired at all.
        return DEADLINE_EXPIRED
    if phase == "download":
        # The download pass OWNS the tally. Letting the commit pass write it too
        # would erase the download pass's count and trip the canary on a
        # perfectly healthy run.
        PROGRESS_SEEN = seen
    return rc
