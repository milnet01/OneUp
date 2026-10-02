"""Where everything OneUp reads or writes lives.

**The one module in the package allowed to know where things are.** Every other
module imports from here; none builds a path from its own `__file__`. A module
under `oneup/gui/` that computes the parent of its own file gets `oneup/gui/`,
so the engine would be looked for in the wrong directory and never found — the
window opens and Run fails (`docs/standards/files-and-naming.md` §4.2).

**Read these through the module — `paths.RUN_STATE`, never
`from .paths import RUN_STATE`.** The suite redirects them to a sandbox so it
cannot touch the machine it runs on (`docs/standards/testing.md` §2), and a
name bound into another module keeps its own copy: the redirect would land
somewhere nobody reads, the suite would stay green, and the window would delete
the real run's `run.state`
(`docs/specs/ONEUP-0034-gui-modules.md` §4.4, INV-2).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Where our bundled files (the engine, the icon) live. Normally the repo root;
# inside a PyInstaller/AppImage bundle they are unpacked flat to _MEIPASS, where
# a nested package directory does not exist at all — which is why the AppImage
# carries the engine's source as data under `engine-src/` (ONEUP-0054 §4.7).
if getattr(sys, "frozen", False):
    HERE = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    # …/oneup/gui/paths.py -> …/ — parents[2] is the repo root, which is where
    # updater.py and the oneup package sit and what HERE meant before the split.
    HERE = Path(__file__).resolve().parents[2]


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



def write_whole(path: Path, text: str) -> None:
    """Write `path` whole, through a temporary file and a rename (ONEUP-0184). A full
    disk or a crash part-way leaves the old file rather than a truncated one, which
    systemd refuses as a unit and history.json reads as "never". Raises OSError."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def log_dir_ready(win=None, quiet: bool = False) -> bool:
    """Make the log folder, or say why it can't be made (ONEUP-0184). Called before
    a launcher changes any state, so a full or read-only disk leaves the window as
    it was instead of raising out of a slot with a button left disabled. `quiet` is
    for background probes, which have nobody to tell. Qt is imported only on that
    failure path, so this module stays importable with no Qt at all."""
    try:
        STATE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as exc:
        if quiet or win is None:
            print(f"OneUp: cannot write logs to {STATE_LOG_DIR}: {exc}", file=sys.stderr)
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(win, "Can't write OneUp's logs",
                                f"OneUp couldn't create its log folder:\n{STATE_LOG_DIR}\n\n{exc}")
        return False


# The lowest Python the engine runs on: `docs/standards/coding.md` §1's floor. Only
# the AppImage asks, because only there is the interpreter the machine's own.
PYTHON_FLOOR = (3, 13)

# What the resolver learned once per process: the machine's python3 (AppImage only)
# and whether the "not found" line has gone to stderr. One dict, so the suite can
# clear it before each case — a cached answer would otherwise leak between them.
_engine_cache: dict = {}


def _reset_engine_cache() -> None:
    _engine_cache.clear()


def _library_path_env() -> list[str]:
    """`env` arguments undoing what a PyInstaller one-file bundle does to
    `LD_LIBRARY_PATH`: it points it at its own `_MEI…` directory, and every child
    inherits that (measured 2026-10-02). The machine's python3 must load the
    machine's libraries — the bundle's go when the window exits, mid-run.
    The bootloader keeps the original in `LD_LIBRARY_PATH_ORIG` when there was one."""
    orig = os.environ.get("LD_LIBRARY_PATH_ORIG")
    return [f"LD_LIBRARY_PATH={orig}"] if orig is not None else ["-u", "LD_LIBRARY_PATH"]


def _machine_python() -> str | None:
    """The machine's python3, if it meets PYTHON_FLOOR. Asked once per process."""
    if "python3" not in _engine_cache:
        found, ok = shutil.which("python3"), False
        if found:
            env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
            if "LD_LIBRARY_PATH_ORIG" in os.environ:
                env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH_ORIG"]
            probe = f"import sys; sys.exit(sys.version_info < {PYTHON_FLOOR!r})"
            try:
                ok = subprocess.run([found, "-c", probe], env=env,  # noqa: S603
                                    capture_output=True, timeout=10).returncode == 0
            except (OSError, subprocess.SubprocessError):
                ok = False
        _engine_cache["python3"] = found if ok else None
    return _engine_cache["python3"]


def _engine_copy() -> Path | None:
    """The AppImage's engine, copied out of the bundle (ONEUP-0054 §4.7).

    The bundle's mount goes when the window exits, and an engine still reading
    from it mid-transaction would break INV-5 — so the source is copied to a
    directory named for its own content and run from there. Written whole into a
    temporary sibling and renamed into place, so a half-written copy is never
    launched. Older copies are left alone: nothing records which one a live engine
    is using, so no deletion can be shown safe."""
    src = HERE / "engine-src"
    files = sorted(p for p in src.rglob("*.py") if "__pycache__" not in p.parts) \
        if src.is_dir() else []
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(src).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    dest = STATE_DIR / "engine" / digest.hexdigest()[:16]
    if (dest / "oneup" / "engine" / "__main__.py").is_file():
        return dest
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=dest.name + ".", dir=dest.parent))
        try:
            for path in files:
                target = tmp / path.relative_to(src)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            os.replace(tmp, dest)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    except OSError:
        pass                     # another process won the rename, or the disk is full
    return dest if (dest / "oneup" / "engine" / "__main__.py").is_file() else None


def _resolve_engine() -> tuple[list[str] | None, list[str]]:
    """The argv prefix that launches the engine, or None — plus what was tried.

    Replaces `_find_engine`, which returned its first candidate whether or not it
    existed, so each caller decided what a missing engine looked like
    (`docs/standards/files-and-naming.md` §7 Trap 4). This reports what it tried,
    and says so on stderr once per process, so a guard that returns silently still
    leaves a trace (ONEUP-0054 §4.7: "so no caller has to")."""
    if getattr(sys, "frozen", False):
        python, copy = _machine_python(), _engine_copy()
        tried = [f"the engine source in {HERE / 'engine-src'}",
                 f"a python3 of {PYTHON_FLOOR[0]}.{PYTHON_FLOOR[1]} or newer on PATH"]
        prefix = (["env", *_library_path_env(), f"PYTHONPATH={copy}",
                   python, "-m", "oneup.engine"] if python and copy else None)
    else:
        main = HERE / "oneup" / "engine" / "__main__.py"
        tried = [str(main)]
        inherited = os.environ.get("PYTHONPATH", "")
        pythonpath = f"{HERE}{os.pathsep}{inherited}" if inherited else str(HERE)
        prefix = (["env", f"PYTHONPATH={pythonpath}", sys.executable, "-m", "oneup.engine"]
                  if main.is_file() else None)
    if prefix is None and not _engine_cache.get("reported"):
        _engine_cache["reported"] = True
        print(f"OneUp: the update engine was not found; tried {'; '.join(tried)}",
              file=sys.stderr)
    return prefix, tried


def engine_argv(*args: str) -> list[str]:
    """The full command that launches the engine, program first.

    A `QProcess` site takes `argv[0]` as the program and `argv[1:]` as its
    arguments; a `subprocess` site passes the list whole. Every launch in the
    window goes through here. Call it only where `engine_available()` said yes —
    with no engine there is no command to give, and it raises.

    The argv is headed by `env` carrying `PYTHONPATH`: `-m` resolves only from
    the package's parent otherwise, and an argv cannot carry an environment any
    other way short of a per-site environment at all eight call sites. The engine
    spells a call the same way (`sudo env LC_ALL=C bash -c` in `oneup/engine/steps.py`).
    """
    prefix, tried = _resolve_engine()
    if prefix is None:
        raise FileNotFoundError(f"no update engine; tried {'; '.join(tried)}")
    return [*prefix, *args]


def engine_available() -> bool:
    """Can the engine be launched? The guard every launch site checks first."""
    return _resolve_engine()[0] is not None


def engine_tried() -> str:
    """What the resolver looked for, for a "could not find" message."""
    return "\n".join(_resolve_engine()[1])


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
