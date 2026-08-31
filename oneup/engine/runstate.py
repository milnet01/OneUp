"""Where the engine's own files live: the four state files, and the run log.

`docs/specs/ONEUP-0054-python-engine.md` §4.1.1 pins the layout of the state
files and `docs/reference/marker-protocol.md` §8 names them. Stage 2 owns the
PATHS; the writers arrive with the run driver.

`USER_LOG_DIR`, not `LOG_DIR`: the window has a log directory too, under a
different path, and while the two halves were in different languages the shared
name could not collide. In one package it can — `docs/standards/files-and-naming.md`
§7 Trap 1. The window's is `STATE_LOG_DIR`.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Where a user can find a run's log. No environment override — the individual run's
# file is redirected with `--log=FILE` instead, which every test scenario uses.
USER_LOG_DIR = Path.home() / "Documents" / "update-logs"


def _state_home() -> Path:
    """The XDG state base directory (ONEUP-0059).

    `XDG_STATE_HOME` wins when it is set to an ABSOLUTE path; anything else —
    unset, empty, or relative — falls back to the specification's own default.
    `oneup/gui/paths.py` and `update_system.sh` apply the IDENTICAL rule: these
    files are a contract between the two halves, so a disagreement here has the
    window writing `stop.request` where the engine never looks, and Stop quietly
    stops working with nothing failing anywhere.
    """
    xdg = os.environ.get("XDG_STATE_HOME", "")
    return Path(xdg) if xdg.startswith("/") else Path.home() / ".local" / "state"


STATE_DIR = _state_home() / "oneup"

# Each overridable so the suite never reads or damages the real machine's state
# (docs/standards/testing.md §2).
RUN_STATE = Path(os.environ.get("ONEUP_RUN_STATE") or STATE_DIR / "run.state")
STOP_REQUEST = Path(os.environ.get("ONEUP_STOP_FILE") or STATE_DIR / "stop.request")
HOLD_STATE = Path(os.environ.get("ONEUP_HOLD_STATE") or STATE_DIR / "hold.state")
GO_REQUEST = Path(os.environ.get("ONEUP_GO_FILE") or STATE_DIR / "go.request")


def stop_and_run_mtimes() -> tuple[float | None, float | None]:
    """(`stop.request`, `run.state`) modification times; None where absent.

    The reads only — `proc.stop_pending` owns the decision they feed (§4.2).
    Both answers matter and the second is the one that looks droppable: §4.1.1
    says that with no `run.state` at all **no stop is ever honoured**, which is
    what stops a request outliving the run it was meant for.
    """
    def mtime(path: Path) -> float | None:
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    return mtime(STOP_REQUEST), mtime(RUN_STATE)


def resolve_log_path(explicit: str | None) -> Path:
    """The path this run logs to — creating `USER_LOG_DIR` only if we default into it.

    ONEUP-0058: the Bash engine runs its `mkdir` before looking at `--log=`, so
    the test suite creates `~/Documents/update-logs` on any machine it runs on,
    including one that has never installed OneUp. A directory is made when it is
    about to be written to, and not before.
    """
    if explicit:
        return Path(explicit)
    USER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return USER_LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H%M')}.log"


# Only the process that WROTE the run-state file clears it, so a `--check` or a
# `--size` run cannot erase a real run's record.
_RUN_STATE_OWNED = False


def clear_owned_state() -> None:
    """Delete this run's own state files, if this process wrote them."""
    if not _RUN_STATE_OWNED:
        return
    for path in (RUN_STATE, STOP_REQUEST):
        with contextlib.suppress(OSError):
            path.unlink()


class _Mirror:
    """One output stream, written to the console AND appended to the run's log.

    The Bash installs `exec > >(tee -a -p "$LOG_FILE") 2>&1`, and both halves of
    that matter. It MERGES — stderr goes into the same tee — so every `>&2` line
    (the `TOTAL == 0` rejection, "Authentication failed or cancelled",
    `cleanup`'s re-enable warning) reaches the log. And `-p` is what lets a run
    survive the GUI going away (ONEUP-0042): our stdout is a pipe to the window,
    and when the user quits, a plain `tee` dies on the broken pipe and then
    SIGPIPEs the engine mid-transaction — which is the one thing that must never
    happen, because a half-applied rpm transaction can leave packages broken.

    Python sets SIGPIPE to SIG_IGN, so the same event arrives as
    `BrokenPipeError` on the console write. Swallowing it here is NOT enough:
    the interpreter's shutdown flush of `sys.stdout` fails in its turn and the
    process exits 120, which the window colours as a failure on a run that
    finished cleanly. `console_is_gone` is what `install_log_mirror` reads to
    neutralise that flush.
    """

    console_gone = False

    def __init__(self, console, log):
        self._console = console
        self._log = log

    def write(self, text: str) -> int:
        if not _Mirror.console_gone:
            try:
                self._console.write(text)
                self._console.flush()
            except (BrokenPipeError, ValueError, OSError):
                _Mirror.console_gone = True     # the window quit; the run carries on
        try:
            self._log.write(text)
            self._log.flush()
        except (ValueError, OSError):
            pass
        return len(text)

    def flush(self) -> None:
        if not _Mirror.console_gone:
            with contextlib.suppress(BrokenPipeError, ValueError, OSError):
                self._console.flush()
        with contextlib.suppress(ValueError, OSError):
            self._log.flush()

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        return self._console.fileno()


def install_log_mirror(path: Path) -> None:
    """Mirror this run's whole output to `path`, whatever the run mode.

    EVERY mode, not just a full run: the Bash installs its tee above every
    dispatch, so `--check`, `--size`, `--thin-snapshots` and the auth actions
    are all logged. The directory is created here, at the moment it is about to
    be written to, and not before (ONEUP-0058).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", encoding="utf-8", errors="replace")
    sys.stdout = _Mirror(sys.__stdout__, handle)
    sys.stderr = _Mirror(sys.__stderr__, handle)

    def _drop_stdout_at_exit() -> None:
        # Once the console end is gone, the interpreter's own shutdown flush
        # would fail and turn a clean run into exit 120. Point the streams at
        # something that cannot fail; the log is already flushed per write.
        if _Mirror.console_gone:
            with contextlib.suppress(OSError):
                sys.stdout = open(os.devnull, "w")   # lives to interpreter exit by design
                sys.stderr = sys.stdout

    atexit.register(_drop_stdout_at_exit)


def write_run_state(log_file: Path, steps: str) -> None:
    """Record this run so a starting window can find it and follow the log.

    Four lines, in this order: our pid, the log path verbatim, the selected
    step keys, and the epoch second we committed. §4.1.1 pins the layout — do
    not reorder or drop a line. Written only once the run is definitely going
    ahead, so a `--check` or a `--size` never claims to be one.
    """
    global _RUN_STATE_OWNED
    RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
    RUN_STATE.write_text(f"{os.getpid()}\n{log_file}\n{steps}\n{int(time.time())}\n")
    _RUN_STATE_OWNED = True



# How long a hold waits before ending by itself. Two minutes: long enough for a
# user to read the quoted size and decide, short enough that a forgotten window
# does not hold a warm credential open indefinitely.
HOLD_SECONDS = int(os.environ.get("ONEUP_HOLD_SECONDS") or "120")


def hold_for_go_ahead(log_file: Path, size: str, window_pid: int,
                      poll: float) -> str | None:
    """Wait for the window's go-ahead. Returns its step list, or None.

    RECORDS a decision; it never runs a step. `hold.state` is three lines — our
    pid, the log path verbatim, the quoted size — and §4.1.1 pins that order.

    Cancel reuses `stop.request`, but it may NOT be read through `stop_pending`:
    that requires `run.state` to exist and the request to be newer than it, and
    a hold has deliberately not written `run.state` — so `stop_pending` is false
    for the whole hold and a Cancel wired through it would do nothing for the
    full ceiling. Our own stamp is the comparison instead.

    Both files are deleted on EVERY exit.
    """
    with contextlib.suppress(OSError):
        HOLD_STATE.parent.mkdir(parents=True, exist_ok=True)
    HOLD_STATE.write_text(f"{os.getpid()}\n{log_file}\n{size}\n")
    try:
        stamp = HOLD_STATE.stat().st_mtime
        waited = 0.0
        step = poll if poll > 0 else 1.0
        while waited < HOLD_SECONDS:
            # Staleness the way `stop_pending` decides it: a request older than
            # our own stamp is a leftover from an earlier session. Deleting
            # leftovers at start-up instead would race a go-ahead pressed in
            # that very moment.
            if _newer_than(GO_REQUEST, stamp):
                return GO_REQUEST.read_text(errors="replace").split("\n", 1)[0].strip()
            if _newer_than(STOP_REQUEST, stamp):
                return None                              # Cancel
            if not _alive(window_pid):
                return None                              # the window has gone
            time.sleep(step)
            waited += step
        return None                                      # the ceiling
    finally:
        for path in (HOLD_STATE, GO_REQUEST):
            with contextlib.suppress(OSError):
                path.unlink()


def _newer_than(path: Path, stamp: float) -> bool:
    try:
        return path.stat().st_mtime > stamp
    except OSError:
        return False


def _alive(pid: int) -> bool:
    """`kill -0` the pid captured at start-up — never a re-read parent id.

    Bash sets `PPID` once and never refreshes it on reparenting, and systemd
    reparents a user session's orphans to `systemd --user` rather than to pid 1,
    so both of the obvious spellings are dead code (`CLAUDE.md` §6).
    """
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
