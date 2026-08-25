"""Become root safely, and stay the parent of everything that does.

`docs/standards/security.md` §2.3: **one runner owns every privileged child.**
With no terminal — and there is none, because the window runs the engine through
`QProcess` — sudo keys its cached credential to the parent process id. In Bash
that made every `$(sudo …)` subshell authenticate again, and a full run once
asked for the password seven times (ONEUP-0038). Python has no subshell, so the
same trap takes a different shape: scatter `subprocess.run(["sudo", …])` across
modules and each call site becomes its own discipline to remember. Route them
through `sudo()` here instead, and there is one place to get right.

Stage 2 holds the environment and the runner. `sudo_init`'s one-time bootstrap,
the keep-alive, the askpass reaping and `cleanup` arrive with the run driver.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import pathlib
import shutil
import signal
import subprocess
import sys
from collections.abc import Sequence

from . import markers, proc

# Overridable so the suite points it at a mock instead of raising a real KDE dialog.
ASKPASS = os.environ.get("ONEUP_ASKPASS") or "/usr/libexec/ssh/ksshaskpass"

# Label EVERY prompt sudo may raise, including ones we did not pass -p to. sudo's own
# default reads "[sudo] password for root" under this distro's `targetpw` setting — an
# unlabelled request for the ROOT password looks like something nefarious to a user who
# only asked for a download size. A prompt nobody can attribute is one they should refuse
# (ONEUP-0037).
SUDO_PROMPT = "OneUp needs administrator rights to update this system. Password: "

# ---------------------------------------------------------------------------
# The privileged argvs this engine issues in more than one place.
# ---------------------------------------------------------------------------
# ONEUP-0092 §4.2, "One definition per shape": each of these is written ONCE and
# read by both the call site and the sudoers rule that grants it, so a respelling
# on either side cannot drift unnoticed. A drifted pair is invisible until a
# passwordless user meets it mid-run, in sudo's own bare wording.
#
# `None` when the binary is missing, and deliberately NOT a bare-name fallback:
# `build_auth_rule` must emit an absolute path or `visudo -cf` rejects the whole
# file, so the two readers want opposite things on failure and the refusal has to
# win. `auth_cmnds` returns None on it; a caller that needs to RUN one checks first.
_TIMEOUT_BIN = shutil.which("timeout")
_DU_BIN = shutil.which("du")

# The per-repository refresh budget. It arrives from the environment, so it is
# pinned to digits where it reaches the sudoers rule rather than trusted here.
REFRESH_TIMEOUT = os.environ.get("ONEUP_REFRESH_TIMEOUT") or "120"

# `sudo timeout <budget> zypper …` — zypper has no timeout of its own, so a
# crawling mirror is bounded from outside (ONEUP-0048).
REFRESH_SUDO_ARGV: list[str] | None = (
    [_TIMEOUT_BIN, REFRESH_TIMEOUT, "zypper"] if _TIMEOUT_BIN else None
)

# `sudo du -sB1 /var/cache/zypp` — the cache step measures the package cache
# before and after the clean so it can report what it freed. Fixed argv, no
# wildcard: `du` takes no sub-command, so there is nothing to escape into.
CACHE_DU_ARGV: list[str] | None = (
    [_DU_BIN, "-sB1", "/var/cache/zypp"] if _DU_BIN else None
)


def install_environment() -> None:
    """Export what sudo needs before any privileged call.

    EXPORTED, not merely set: sudo falls back to the askpass helper only when it
    finds `SUDO_ASKPASS` in the environment. Without it, a sudo that cannot see a
    cached credential has no way to ask and dies on "a terminal is required" —
    which is what made "Show download size" fail (ONEUP-0036).
    """
    os.environ["SUDO_ASKPASS"] = ASKPASS
    os.environ["SUDO_PROMPT"] = SUDO_PROMPT


# sudo_init's own prompt label, and it is NOT `SUDO_PROMPT` above. The Bash
# passes this one to the up-front `-v` validate and exports the other for every
# other prompt; `reap_orphaned_askpass` matches an orphaned dialog against
# EITHER string, so collapsing them into one leaves that reaper — stage 5's —
# with a target that never appears.
VALIDATE_PROMPT = "System Updater: authenticate to update the system"


def sudo_init() -> None:
    """Become root once, up front, so nothing later has to ask again.

    Stage 4 builds the authenticate half only. The keep-alive is `cleanup`'s to
    kill and `cleanup` is stage 5's; a keep-alive with nothing to kill it is the
    shape `CLAUDE.md` §6's fourth trap names.
    """
    # Deferred: `auth_current` is `actions.py`'s by §4.2, and `actions` imports
    # this module — a module-level import back would be a cycle.
    from . import actions

    # If the ONEUP-0023 drop-in is active AND grants what this engine needs,
    # every privileged command below is individually NOPASSWD, so no cached
    # credential is needed — and the interactive `-v` here would prompt ANYWAY:
    # sudo's `verifypw` defaults to `all`, so a bare validate is password-free
    # only when EVERY one of the user's sudoers entries is NOPASSWD, which a
    # normal wheel user's is not. Skipping it is what lets a headless timer run.
    #
    # `auth_current`, not a bare zypper probe: a drop-in from an older OneUp is
    # live and still leaves three calls prompting, and that is what turned into
    # a surprise dialog in the middle of step 1 (ONEUP-0092).
    if actions.auth_current():
        return
    install_environment()
    # STREAMED, not captured. The Bash redirects this call nowhere, so whatever
    # sudo says — a prompt, a refusal, "a terminal is required" — reaches the
    # run's own stderr and its log. Capturing it silently swallows the one
    # message a user who cancelled the dialog has to go on.
    rc, _ = proc.run(["sudo", "-A", "-p", VALIDATE_PROMPT, "-v"], stream=True)
    if rc != 0:
        markers.err("Authentication failed or cancelled — aborting.")
        raise SystemExit(1)
    _start_keepalive()


# How often the keep-alive re-validates. Overridable so a test can watch the loop
# exit inside its own patience — a 50-second sleep makes the property unobservable.
KEEPALIVE_SECONDS = os.environ.get("ONEUP_KEEPALIVE_SECONDS") or "50"

# `argv[0]` of the keep-alive child. A grep-able tag so a test can find these
# without matching every `sleep` on the machine; `pgrep -f oneup-keepalive` is
# what both scenarios use, so renaming it makes them pass by finding nothing.
KEEPALIVE_TAG = "oneup-keepalive"

_KEEPALIVE: subprocess.Popen | None = None

# The loop, as its own argv so nothing is interpolated into a shell. It watches
# OUR pid and exits on its own once we are gone: `cleanup`'s group kill is the
# fast path, but a trap cannot run when the engine is SIGKILLed, and then the
# loop ran forever — two were found still calling `sudo -n -v` every 50 seconds,
# 40 minutes after the runs that spawned them were killed (ONEUP-0041).
#
# `os.kill(pid, 0)` is the liveness test, against a pid captured ONCE at start.
# Re-reading our own parent id instead can never fire: it is set at start and is
# not refreshed on reparenting, and testing it against 1 never fires either,
# because systemd reparents a user session's orphans to `systemd --user`
# (CLAUDE.md §6).
_KEEPALIVE_SRC = """
import os, subprocess, sys, time
pid, interval = int(sys.argv[2]), float(sys.argv[3])   # argv[1] is the tag
while True:
    try:
        os.kill(pid, 0)
    except OSError:
        break
    subprocess.run(["sudo", "-n", "-v"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(interval)
"""


def _start_keepalive() -> None:
    """Refresh the cached credential in the background for the rest of the run.

    Its own process group, so `cleanup` can kill the WHOLE group: killing the
    child alone leaves its `sleep` orphaned and lingering for up to an interval.
    Detached from our stdout and stderr so it never pollutes the log stream, and
    so a consumer capturing our output is not held open by its sleep.

    Never two. `sudo_init` has no re-entry guard of its own beyond `auth_current`,
    and a second keep-alive would overwrite the handle so `cleanup`'s group kill
    could only reach the later group — the orphan leak of ONEUP-0041 (INV-9).
    """
    global _KEEPALIVE
    if _KEEPALIVE is not None:
        return
    interval = KEEPALIVE_SECONDS if KEEPALIVE_SECONDS.replace(".", "", 1).isdigit() else "50"
    # The tag rides in argv so `pgrep -f oneup-keepalive` finds this child; it is
    # read back out of sys.argv rather than used, which is why the loop skips it.
    _KEEPALIVE = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [sys.executable, "-c", _KEEPALIVE_SRC, KEEPALIVE_TAG, str(os.getpid()), interval],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def sudo(argv: Sequence[str], *, flags: Sequence[str] = (), merge_stderr: bool = False,
         stream: bool = False) -> tuple[int, str]:
    """Run `argv` as root and return its status and output.

    The single sudo parent for the whole run. `flags` carries sudo's own options
    (`-k`, `-n`, `-A`); everything after them is the command. With `stream` the
    child writes to our own stdout and stderr rather than being captured — see
    `proc.run`.
    """
    install_environment()
    return proc.run(["sudo", *flags, *argv], merge_stderr=merge_stderr, stream=stream)


def reap_orphaned_askpass() -> None:
    """Kill a password dialog nobody is waiting on any more.

    Both the helper's path AND one of our own prompts must appear: the path
    alone would catch another app's dialog, a prompt alone could match an
    unrelated process that merely mentions the text. Matched as substrings,
    because a script helper shows up as `bash <script> …`.

    A dialog someone IS waiting on is a child of the sudo that launched it, so
    the PARENT's command line is the test. Deliberately not "parent is pid 1":
    systemd reparents a user session's orphans to `systemd --user`, so an
    orphan-check against pid 1 silently never fires — that was the first version
    of this function in Bash and it reaped nothing.
    """
    try:
        rc, out = proc.run(["ps", "-eo", "pid=,ppid=,args="])
    except OSError:
        return
    if rc != 0:
        return
    for line in out.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        pid, ppid, args = parts
        if ASKPASS not in args:
            continue
        if SUDO_PROMPT not in args and VALIDATE_PROMPT not in args:
            continue
        try:
            parent = pathlib.Path(f"/proc/{ppid}/cmdline").read_bytes().replace(b"\0", b" ")
        except OSError:
            parent = b""
        if b"sudo" in parent:
            continue                      # someone is still waiting on this one
        with contextlib.suppress(OSError, ValueError):
            os.kill(int(pid), signal.SIGTERM)


def kill_keepalive() -> None:
    """Kill the keep-alive's whole process GROUP, not just the child.

    A plain kill leaves the inner sleep orphaned and lingering for up to one
    interval after a cancelled run.
    """
    global _KEEPALIVE
    if _KEEPALIVE is None:
        return
    with contextlib.suppress(OSError, ProcessLookupError):
        os.killpg(_KEEPALIVE.pid, signal.SIGTERM)
    _KEEPALIVE = None


def cleanup() -> None:
    """Everything this process must undo, whatever way it is leaving.

    §4.2 splits the Bash `cleanup` three ways and this is the seam that
    re-joins them. **The ORDER is load-bearing**: the repository re-enable runs
    `sudo -n`, non-interactively, so it needs the credential the keep-alive is
    keeping warm — kill the group first and an interrupted `--skip-repo` run
    leaves the user's repository disabled. No scenario can see it; the suite's
    cached-sudo mock succeeds on `sudo -n` either way.
    """
    # Deferred: both modules import this one, so a top-level import is a cycle.
    from . import repos, runstate

    runstate.clear_owned_state()
    reap_orphaned_askpass()
    repos.restore_disabled()
    kill_keepalive()


def _signal_exit(code: int):
    """A handler that EXITS rather than merely tidying up.

    A handler that ran `cleanup` and returned would resume after the interrupted
    call and plough on through the remaining privileged steps the user just
    cancelled. Raising `SystemExit` unwinds instead, and the `atexit` hook below
    still runs. 130 = 128+SIGINT, 143 = 128+SIGTERM, the conventional codes
    `docs/specs/ONEUP-0054-python-engine.md` §4.1.2 freezes.
    """
    def handler(_signum, _frame):
        raise SystemExit(code)
    return handler


def install_exit_handlers() -> None:
    """Run `cleanup` however this process leaves — including on an exception."""
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, _signal_exit(130))
    signal.signal(signal.SIGTERM, _signal_exit(143))
    signal.signal(signal.SIGHUP, _signal_exit(143))

