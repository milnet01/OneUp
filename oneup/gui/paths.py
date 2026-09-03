"""Where everything OneUp reads or writes lives.

**The one module in the package allowed to know where things are.** Every other
module imports from here; none builds a path from its own `__file__`. A module
under `oneup/gui/` that computes the parent of its own file gets `oneup/gui/`,
so `_find_engine` would look for `update_system.sh` in the wrong directory,
fall through to its `~/Documents` fallback, and return a path that does not
exist — the window opens and Run fails
(`docs/standards/files-and-naming.md` §4.2).

**Read these through the module — `paths.RUN_STATE`, never
`from .paths import RUN_STATE`.** The suite redirects them to a sandbox so it
cannot touch the machine it runs on (`docs/standards/testing.md` §2), and a
name bound into another module keeps its own copy: the redirect would land
somewhere nobody reads, the suite would stay green, and the window would delete
the real run's `run.state`
(`docs/specs/ONEUP-0034-gui-modules.md` §4.4, INV-2).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Where our bundled files (update_system.sh, the icon) live. Normally the repo
# root; inside a PyInstaller/AppImage bundle they are unpacked flat to _MEIPASS,
# where a nested package directory does not exist at all.
if getattr(sys, "frozen", False):
    HERE = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    # …/oneup/gui/paths.py -> …/ — parents[2] is the repo root, which is where
    # updater.py and update_system.sh sit and what HERE meant before the split.
    HERE = Path(__file__).resolve().parents[2]


def _find_engine() -> Path:
    """Locate update_system.sh. It normally sits next to this file (git checkout,
    RPM or AppImage install); fall back to the legacy ~/Documents path so an
    existing hand-installed setup keeps working."""
    for candidate in (HERE / "update_system.sh",
                      Path.home() / "Documents" / "update_system.sh"):
        if candidate.exists():
            return candidate
    return HERE / "update_system.sh"  # default; start_run() warns if it's missing


def _state_home() -> Path:
    """The XDG state base directory (ONEUP-0059).

    `XDG_STATE_HOME` wins when it is set to an ABSOLUTE path; anything else —
    unset, empty, or relative — falls back to the specification's own default.
    The absolute test is the specification's ("all paths must be absolute; an
    invalid one must be ignored") and is what stops a stray relative value
    creating a state directory under whatever the working directory happens to
    be. `update_system.sh` applies the identical rule to `RUN_STATE_FILE` and
    `STOP_FILE`: the two halves must agree, or Stop writes where the engine
    never looks and quietly stops working (`docs/design/oneup-2.0.md` §6.5).
    """
    xdg = os.environ.get("XDG_STATE_HOME", "")
    return Path(xdg) if xdg.startswith("/") else Path.home() / ".local" / "state"


ENGINE = _find_engine()


def _engine_is_v2() -> bool:
    """Is the window pointed at the Python engine? (ONEUP-0054 §4.7.)

    Read PER CALL, never bound at import: the suite flips the variable between
    scenarios, and a value captured at import would ignore the flip — the same
    reason every path here is read through the module (ONEUP-0034 §4.4, INV-2).

    `v2` selects it; anything else — unset, `v1`, a typo — is the Bash engine,
    which stays the default until stage 9 flips it. Not the suite's
    `ONEUP_ENGINE_CMD`, which is a whole argv the harness pins per side: this
    one names a side, and one variable for both would let an export aimed at
    the suite reach the window.
    """
    return os.environ.get("ONEUP_ENGINE", "") == "v2"


def engine_argv(*args: str) -> list[str]:
    """The full command that launches the engine, program first.

    A `QProcess` site takes `argv[0]` as the program and `argv[1:]` as its
    arguments; a `subprocess` site passes the list whole. Every launch in the
    window goes through here, so the window can launch a non-Bash engine at all.

    The v2 arm is headed by `env` carrying `PYTHONPATH`: `-m` resolves only
    from the checkout root otherwise, and an argv cannot carry an environment
    any other way. Not by mutating `os.environ`, which would reach the v1 bash
    child too; not by a per-site environment, which would change the work at
    all eight call sites to serve one arm of one helper. The engine spells a
    call the same way (`sudo env LC_ALL=C bash -c` in `oneup/engine/steps.py`).
    """
    if _engine_is_v2():
        inherited = os.environ.get("PYTHONPATH", "")
        pythonpath = f"{HERE}{os.pathsep}{inherited}" if inherited else str(HERE)
        return ["env", f"PYTHONPATH={pythonpath}",
                sys.executable, "-m", "oneup.engine", *args]
    return ["bash", str(ENGINE), *args]


def engine_available() -> bool:
    """Is the SELECTED engine present? `ENGINE.exists()` asks it of a Bash file,
    which answers about the wrong engine once the switch is on."""
    if _engine_is_v2():
        return (HERE / "oneup" / "engine" / "__main__.py").is_file()
    return ENGINE.exists()


# The root updater.py — the thing a launcher names. Resolved once, here, because
# a systemd unit built from a package module's __file__ would run
# `python3 …/oneup/gui/autostart.py --check`, which does nothing at all, and the
# existing assertions pass either way (spec §4.4).
ENTRY_POINT = HERE / "updater.py"
STATE_DIR = _state_home() / "oneup"
HISTORY = STATE_DIR / "history.json"
STATE_LOG_DIR = STATE_DIR / "logs"
# Where the engine records a run in flight, so a window that opens mid-run can find
# it, say so, and follow the log instead of letting the user launch a second run that
# can only fail on the package lock (ONEUP-0045). Must match RUN_STATE_FILE in
# update_system.sh.
RUN_STATE = STATE_DIR / "run.state"
# Creating this file asks a running engine to stop at its next safe point. Must match
# STOP_FILE in update_system.sh.
STOP_REQUEST = STATE_DIR / "stop.request"
# ONEUP-0044's pair, and they are a contract between the two halves in exactly the way
# the two above are — not part of the marker protocol, because the window writes one of
# them (`docs/reference/marker-protocol.md` §8).
#
# `hold.state` is written by a held engine and read by us: line 1 is its pid, which is
# how we tell a live hold from one a SIGKILLed engine left behind. Must match
# HOLD_STATE_FILE in update_system.sh.
HOLD_STATE = STATE_DIR / "hold.state"
# `go.request` is written by US to tell a held engine to proceed, and carries a
# comma-separated step list on line 1 and nothing else. It is an authorisation read by a
# root process, so the engine refuses the whole list if any key is unknown rather than
# running the part that resolved. Must match GO_FILE in update_system.sh.
GO_REQUEST = STATE_DIR / "go.request"
# zypper's package cache, which is world-readable — so OneUp can weigh it without root.
# This is the ONLY byte figure available during the prefetch phase: zypper prints one line
# per finished package and nothing else, so an 86 MB download from a slow mirror produced
# no output for ten minutes at a stretch and read as a dead app.
ZYPP_PACKAGE_CACHE = Path("/var/cache/zypp/packages")
