"""Where the engine's own files live: the four state files, and the run log.

`docs/specs/ONEUP-0054-python-engine.md` §4.1.1 pins the layout of the state
files and `docs/reference/marker-protocol.md` §8 names them. The paths, their
writers, the log mirror and the hold all live here.

`USER_LOG_DIR`, not `LOG_DIR`: the window has a log directory too, under a
different path, and while the two halves were in different languages the shared
name could not collide. In one package it can — `docs/standards/files-and-naming.md`
§7 Trap 1. The window's is `STATE_LOG_DIR`.
"""

from __future__ import annotations

import atexit
import contextlib
import fcntl
import os
import sys
import tempfile
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


def resolve_log_path(explicit: str | None) -> str:
    """The path this run logs to — creating `USER_LOG_DIR` only if we default into it.

    ONEUP-0058: the Bash engine runs its `mkdir` before looking at `--log=`, so
    the test suite creates `~/Documents/update-logs` on any machine it runs on,
    including one that has never installed OneUp. A directory is made when it is
    about to be written to, and not before.

    A string, not a `Path`: §4.1.1 pins `run.state` line 2 as the `--log=` value
    VERBATIM, and a `Path` normalises it — `logs//./run.log` became `logs/run.log`
    (ONEUP-0188).
    """
    if explicit:
        return explicit
    # A folder that cannot be made is `install_log_mirror`'s to report (ONEUP-0423).
    with contextlib.suppress(OSError):
        USER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return str(USER_LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H%M')}.log")


# Only the process that WROTE the run-state file clears it, so a `--check` or a
# `--size` run cannot erase a real run's record.
_RUN_STATE_OWNED = False

# When this run began: the engine's start, or a held preview's go-ahead. Taken at
# import, before authentication, so a Stop pressed during the password prompt counts.
_BEGAN = time.time()


def owns_run_state() -> bool:
    """Did this process write the run-state record? Stop can reach the run only if so."""
    return _RUN_STATE_OWNED


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
    finished cleanly. `console_gone` is what `install_log_mirror` reads to
    neutralise that flush.
    """

    console_gone = False

    def __init__(self, console, log):
        self._console = console
        self._log = log

    def write(self, text: str) -> int:
        if not _Mirror.console_gone:
            try:
                try:
                    self._console.write(text)
                except UnicodeEncodeError:
                    # A ValueError, so without this arm one character the console
                    # cannot encode would latch `console_gone` and silence every
                    # marker for the rest of the run (ONEUP-0176). Substitute it.
                    enc = getattr(self._console, "encoding", None) or "utf-8"
                    self._console.write(text.encode(enc, "replace").decode(enc))
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

    A log that cannot be opened — a full disk, an unwritable folder — leaves the run
    on the console alone, said once on stderr. A full disk is when an update matters
    most, and the log is a copy of what the console already shows (ONEUP-0423).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a", encoding="utf-8", errors="replace")
    except OSError as exc:
        with contextlib.suppress(OSError, ValueError):
            print(f"OneUp couldn't open its log {path} ({exc.strerror or exc}); "
                  "this run is not logged.", file=sys.__stderr__, flush=True)
        return
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


def _temp_beside(path: Path, text: str) -> Path:
    """Write `text` to a new temporary file in `path`'s directory; return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(name)
        raise
    return Path(name)


def write_whole(path: Path, text: str) -> None:
    """Replace `path` with `text` in one step (ONEUP-0177).

    A truncate-then-write lets a reader land between the two and see an empty
    file — for `run.state` or `hold.state` that reads as "no run". A rename is
    atomic, so a reader sees the old file or the new one, never neither. The
    window's twin is `gui/paths.py` `write_whole`; a change here belongs there too.
    """
    tmp = _temp_beside(path, text)
    try:
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


# What an engine's command line contains. Both engines, because they share the
# state directory: either may meet the other's record.
_ENGINE_MARKS = (b"update_system", b"oneup.engine")


def run_state_holder() -> int | None:
    """The pid of ANOTHER live engine that owns `run.state`, or None (ONEUP-0145).

    `repos.lock_holder` only sees a live zypper, which does not exist during the
    pre-flight, a Flatpak-only run or between passes — so without this two
    engines both wrote the record and the first to exit deleted it, leaving the
    survivor's Stop dead. The command line is checked as well as the pid: a
    stale record outlives a reboot, and its pid may by then be anything.
    """
    try:
        first = RUN_STATE.read_text(errors="replace").split("\n", 1)[0].strip()
    except OSError:
        return None
    if not first.isdecimal() or int(first) == os.getpid():
        return None
    try:
        cmdline = Path(f"/proc/{first}/cmdline").read_bytes()
    except OSError:
        return None
    return int(first) if any(mark in cmdline for mark in _ENGINE_MARKS) else None


def claim_run_state(log_file: str, steps: str) -> int | None:
    """Record this run so a starting window can find it and follow the log.

    Four lines, in this order: our pid, the log path verbatim, the selected
    step keys, and the epoch second we committed. §4.1.1 pins the layout — do
    not reorder or drop a line. Written only once the run is definitely going
    ahead, so a `--check` or a `--size` never claims to be one.

    Returns None once this run owns the record, or the pid of the live engine
    that already does — in which case nothing is written. The record is written
    to a temporary file and hard-linked into place: that appears whole
    (ONEUP-0177), and a link refuses to replace a file that is already there,
    so two engines cannot both own it (ONEUP-0145). A stale record is removed
    and the link retried once. A record that cannot be written at all leaves
    the run going ahead unowned. The Bash engine's `claim_run_state` is the twin.

    The whole claim runs under `claim_lock` (ONEUP-0394). Without it two engines
    meeting one stale record could both judge it stale: the first removed it and
    linked its own, and the second then removed the FIRST engine's live record.

    The record's mtime is then set back to when this run began, because
    `stop_pending` reads it as the run's start: a Stop pressed during the
    password prompt or the lock wait would otherwise be older than the record
    and ignored as a leftover (ONEUP-0394).
    """
    try:
        tmp = _temp_beside(RUN_STATE,
                           f"{os.getpid()}\n{log_file}\n{steps}\n{int(time.time())}\n")
    except OSError:
        # A full or read-only state directory. The run still goes ahead, unowned —
        # a window cannot follow it, but an update must not fail over its record.
        return None
    try:
        with claim_lock():
            holder = _link_or_replace(tmp)
        if holder is None and _RUN_STATE_OWNED:
            with contextlib.suppress(OSError):
                os.utime(RUN_STATE, (_BEGAN, _BEGAN))
        return holder
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def _link_or_replace(tmp: Path) -> int | None:
    """`claim_run_state`'s write, made while holding `claim_lock`."""
    global _RUN_STATE_OWNED
    for _ in range(2):
        try:
            os.link(tmp, RUN_STATE)
            _RUN_STATE_OWNED = True
            return None
        except FileExistsError:
            holder = run_state_holder()
            if holder is not None:
                return holder
            with contextlib.suppress(OSError):
                RUN_STATE.unlink()
        except OSError:
            break                          # no hard links here: fall back to a rename
    # A rename replaces whatever is there, so ask first: without this a filesystem
    # with no hard links let a second engine overwrite a live run's record.
    holder = run_state_holder()
    if holder is not None:
        return holder
    with contextlib.suppress(OSError):
        os.replace(tmp, RUN_STATE)
        _RUN_STATE_OWNED = True
    return None


# How long a claim waits for another process's claim to finish. A claim takes
# microseconds, so this only matters when the holder has stalled; then the claim
# goes ahead unlocked, as before the lock existed, rather than holding up an update.
CLAIM_LOCK_SECONDS = 5.0


@contextlib.contextmanager
def claim_lock():
    """Hold `run.state.lock` while deciding about and changing `run.state`.

    Taken by both engines' claim and by the window before it deletes a stale
    record — flock(2) on one file, so the Bash `flock` and this one exclude each
    other. The lock file is never deleted: removing it would let two processes
    lock two different files of the same name. It sits beside `run.state`, so the
    suite's redirect of that file carries the lock with it. A lock that cannot be
    had in time, or a file that cannot be opened, leaves the caller unlocked.
    """
    try:
        fd = os.open(f"{RUN_STATE}.lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    except OSError:
        fd = -1
    try:
        give_up = time.monotonic() + CLAIM_LOCK_SECONDS
        while fd >= 0:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= give_up:
                    break
                time.sleep(0.05)
            except OSError:
                break
        yield
    finally:
        if fd >= 0:
            os.close(fd)


def mark_begun() -> None:
    """Restamp this run's start: a held preview's run begins at its go-ahead."""
    global _BEGAN
    _BEGAN = time.time()


def stop_since_begun() -> bool:
    """Was Stop pressed after this run began, before it wrote `run.state`?

    For the waits before the claim (the lock wait), where `stop_pending` cannot
    answer yet because the record it compares against does not exist.
    """
    return _newer_than(STOP_REQUEST, _BEGAN)


# How long a hold waits before ending by itself. Two minutes: long enough for a
# user to read the quoted size and decide, short enough that a forgotten window
# does not hold a warm credential open indefinitely. A value that is not a whole
# number falls back to the default, as the keep-alive interval does: read at
# import, a bad one raised before any mode ran, `--check` included (ONEUP-0188).
_HOLD_ENV = os.environ.get("ONEUP_HOLD_SECONDS") or ""
HOLD_SECONDS = int(_HOLD_ENV) if _HOLD_ENV.isdecimal() else 120


def _elapsed_clock() -> float:
    """Seconds on a clock that keeps running while the machine is suspended.

    Not `time.monotonic`, which stops during a suspend on Linux, and not a count
    of sleeps either: a hold held across a suspend must still end at its ceiling,
    because what it holds open is a root credential.
    """
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def hold_for_go_ahead(log_file: str, size: str, launch_pid: int, window_pid: int,
                      poll: float) -> str | None:
    """Wait for the window's go-ahead. Returns its step list, or None.

    RECORDS a decision; it never runs a step. `hold.state` is three lines — the
    pid the window started (ours, or the systemd-inhibit wrapper's when we were
    re-exec'd under it), the log path verbatim, the quoted size — and §4.1.1
    pins that order.

    Cancel reuses `stop.request`, but it may NOT be read through `stop_pending`:
    that requires `run.state` to exist and the request to be newer than it, and
    a hold has deliberately not written `run.state` — so `stop_pending` is false
    for the whole hold and a Cancel wired through it would do nothing for the
    full ceiling. Our own stamp is the comparison instead.

    `hold.state` and `go.request` are deleted on every exit once `hold.state` is
    written. A Cancel's `stop.request` stays, as every stop request does: the next
    run's newness test reads it as a leftover.
    """
    with contextlib.suppress(OSError):
        HOLD_STATE.parent.mkdir(parents=True, exist_ok=True)
    leftover = _identity(GO_REQUEST)
    try:
        write_whole(HOLD_STATE, f"{launch_pid}\n{log_file}\n{size}\n")
    except OSError:
        # A hold that cannot be recorded ends at once; the window falls back to a
        # fresh engine (INV-7), as the Bash engine's hold does.
        return None
    try:
        stamp = HOLD_STATE.stat().st_mtime_ns
        started = _elapsed_clock()
        step = poll if poll > 0 else 1.0
        while _elapsed_clock() - started < HOLD_SECONDS:
            # Staleness the way `stop_pending` decides it: a request older than
            # our own stamp is a leftover from an earlier session. Deleting
            # leftovers at start-up instead would race a go-ahead pressed in
            # that very moment.
            if _go_ahead_fresh(stamp, leftover):
                mark_begun()
                return GO_REQUEST.read_text(errors="replace").split("\n", 1)[0].strip()
            if _newer_than(STOP_REQUEST, stamp / 1e9):
                return None                              # Cancel
            if not _alive(window_pid):
                return None                              # the window has gone
            time.sleep(step)
        return None                                      # the ceiling
    except OSError:
        # `hold.state` or `go.request` unreadable: end the hold as one that could
        # not be recorded ends, so the window falls back (INV-7).
        return None
    finally:
        for path in (HOLD_STATE, GO_REQUEST):
            with contextlib.suppress(OSError):
                path.unlink()


def _newer_than(path: Path, stamp: float) -> bool:
    try:
        return path.stat().st_mtime > stamp
    except OSError:
        return False


def _identity(path: Path) -> tuple[int, int] | None:
    """`path`'s inode and mtime in nanoseconds, or None when it does not exist."""
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_ino, st.st_mtime_ns


def _go_ahead_fresh(stamp_ns: int, leftover: tuple[int, int] | None) -> bool:
    """Is `go.request` the window's answer to THIS hold (ONEUP-0044 §4.3)?

    Newer than `hold.state`, or stamped in the same clock tick and not the file that
    was there before the hold was written: file times tick coarsely, so a go-ahead
    written the moment `hold.state` appears can tie with it (ONEUP-0425).
    """
    now = _identity(GO_REQUEST)
    if now is None:
        return False
    return now[1] > stamp_ns or (now[1] == stamp_ns and now != leftover)


def _alive(pid: int) -> bool:
    """`kill -0` the pid captured at start-up — never a re-read parent id.

    Bash sets `PPID` once and never refreshes it on reparenting, and systemd
    reparents a user session's orphans to `systemd --user` rather than to pid 1,
    so both of the obvious spellings are dead code (`CLAUDE.md` §6).

    A pid we may not signal still exists, so PermissionError reads as alive —
    as the window's twin probe reads it (ONEUP-0188).
    """
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True
