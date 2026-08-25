"""Run a child process and report what it did.

Stage 2 needs only the immediate form: run a command, wait, hand back its status
and its output. The deadline, the incremental byte counting and the cooperative
cancel that `progress_filter` does today arrive with the steps that need them.

Fixed argv only, never a shell (`docs/standards/coding.md` §5.1). Nothing here
builds a command by interpolating text.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence


def run(argv: Sequence[str], *, merge_stderr: bool = False) -> tuple[int, str]:
    """Run `argv`; return its exit status and its captured stdout.

    With `merge_stderr`, stderr is folded into the returned text — the shape
    `sudo_capture -e` has today.
    """
    completed = subprocess.run(  # noqa: S603 — fixed argv list, no shell; the caller
        # builds every element, and nothing here is interpolated from engine or user text.
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout or ""


def succeeds(argv: Sequence[str]) -> bool:
    """True when `argv` exits 0. Output is discarded."""
    return run(argv)[0] == 0
