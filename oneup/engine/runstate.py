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

import contextlib
import os
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

