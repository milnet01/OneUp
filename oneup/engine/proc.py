"""Run a child process and report what it did.

Stage 2 needs only the immediate form: run a command, wait, hand back its status
and its output. The deadline, the incremental byte counting and the cooperative
cancel that `progress_filter` does today arrive with the steps that need them.

Fixed argv only, never a shell (`docs/standards/coding.md` §5.1). Nothing here
builds a command by interpolating text.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence

from . import markers, runstate


def run(
    argv: Sequence[str],
    *,
    merge_stderr: bool = False,
    env: Mapping[str, str] | None = None,
    stream: bool = False,
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
    if stream:
        completed = subprocess.run(  # noqa: S603 — fixed argv list, no shell, as above
            list(argv),
            check=False,
            env={**os.environ, **env} if env else None,
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
    )
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
