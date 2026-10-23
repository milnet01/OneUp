"""Become root safely, and stay the parent of everything that does.

`docs/standards/security.md` §2.3: **one runner owns every privileged child.**
With no terminal — and there is none, because the window runs the engine through
`QProcess` — sudo keys its cached credential to the parent process id. In Bash
that made every `$(sudo …)` subshell authenticate again, and a full run once
asked for the password seven times (ONEUP-0038). Python has no subshell, so the
same trap takes a different shape: scatter raw sudo-headed argvs across
modules and each call site becomes its own discipline to remember. Route them
through `sudo()` here instead — or `sudo_argv()`, where the caller streams the
output itself — and there is one place to get right.

The environment, the runner, `sudo_init`'s one-time bootstrap, the keep-alive,
the askpass reaping and `cleanup` — whose ORDER is load-bearing, and is stated
on `cleanup` itself.
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
import threading
from collections.abc import Sequence

from . import markers, proc

# Overridable so the suite points it at a mock instead of raising a real KDE dialog.
ASKPASS = os.environ.get("ONEUP_ASKPASS") or "/usr/libexec/ssh/ksshaskpass"
# How long `ldd` may take to read the password box's libraries (ONEUP-0337).
_LDD_SECONDS = 10

# Label EVERY prompt sudo may raise, including ones we did not pass -p to. sudo's own
# default reads "[sudo] password for root" under this distro's `targetpw` setting — an
# unlabelled request for the ROOT password looks like something nefarious to a user who
# only asked for a download size. A prompt nobody can attribute is one they should refuse
# (ONEUP-0037).
# ksshaskpass titles its box "Enter SSH Credentials", so the prompt is the only thing
# saying whose password is wanted. sudo expands %p to that user, honouring targetpw,
# rootpw and runaspw, so the prompt names the right password on any setup (ONEUP-0298).
SUDO_PROMPT = "OneUp needs the password for %p to continue updating. Password: "

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
# EITHER string, so collapsing them into one leaves that reaper with a target
# that never appears.
VALIDATE_PROMPT = "OneUp needs the password for %p to install updates."
# What the reaper matches a dialog on: the text before %p, which sudo has expanded by
# the time the dialog runs, plus the prompts before ONEUP-0298, which the Bash fallback
# still passes.
_PROMPT_MARKS = (
    VALIDATE_PROMPT.split("%p")[0],
    SUDO_PROMPT.split("%p")[0],
    "System Updater: authenticate to update the system",
    "OneUp needs administrator rights to update this system.",
)


def sudo_init() -> None:
    """Become root once, up front, so nothing later has to ask again.

    Two halves, and they land together on purpose: the interactive validate, and
    the keep-alive that holds the credential warm. A keep-alive with nothing to
    kill it is the shape `CLAUDE.md` §6's fourth trap names, so it is started
    only where `cleanup` can already reach it.

    Re-entering it re-runs the validate: its one early return is `auth_current`,
    which is false for precisely the users the held path is for, and the run
    driver's `held_auth` is what skips the second call. It does NOT start a
    second keep-alive — `_start_keepalive` refuses while one is running, and
    that refusal is what keeps INV-9.
    """
    # Deferred: `auth_current` is `actions.py`'s by §4.2, and `actions` imports
    # this module — a module-level import back would be a cycle.
    from . import actions, route, steps

    # The route is chosen here, before the first root command (ONEUP-0249 §4.7).
    if chosen_route() == route.SERVICE:
        if _open_service():
            return
        _service_unreachable()

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
    # Nobody is at the screen to answer a box, so a timer run stands down here, as it
    # does on the service route (ONEUP-0249 §4.7, INV-19). A computer without PackageKit
    # reaches this route even where automatic updates were switched on under the service.
    if os.environ.get("ONEUP_NONINTERACTIVE") == "1":
        markers.err("Passwordless is off and nobody is here to type the password — aborting.")
        raise SystemExit(1)
    install_environment()
    # STREAMED, not captured. The Bash redirects this call nowhere, so whatever
    # sudo says — a prompt, a refusal, "a terminal is required" — reaches the
    # run's own stderr and its log. Capturing it silently swallows the one
    # message a user who cancelled the dialog has to go on.
    rc, _ = proc.run(["sudo", "-A", "-p", VALIDATE_PROMPT, "-v"], stream=True)
    if rc != 0:
        if _askpass_cannot_start():
            # Not a cancel: the box never appeared, so pressing Update again cannot help.
            # A half-finished update can leave its toolkit mismatched, and the box is a Qt
            # program; the terminal still works (ONEUP-0337).
            suffix, command = steps.finish_in_terminal()
            markers.hint(
                "askpass-unavailable" + suffix,
                say="The password box could not start, so OneUp cannot get administrator "
                    "rights. This can happen after an update stopped part-way; finish the "
                    f"update in a terminal with: {command}")
        markers.err("Authentication failed or cancelled — aborting.")
        raise SystemExit(1)
    _start_keepalive()


def _askpass_cannot_start() -> bool:
    """Is the password box missing, or unable to load its libraries?

    Asked only after the validate failed, to tell a box that never appeared from one
    the user cancelled; sudo words both the same. `ldd` reads the libraries without
    running the program, so no box opens. Where `ldd` is missing or its answer is not
    a missing library, this says no, and the run reports a cancel as before.
    """
    if not os.access(ASKPASS, os.X_OK):
        return True
    ldd = shutil.which("ldd")
    if not ldd:
        return False
    _, out = proc.run([ldd, ASKPASS], merge_stderr=True, deadline=_LDD_SECONDS)
    return "not found" in out


# The run's route to root, set once by `chosen_route` (ONEUP-0249 §4.7).
_ROUTE: str | None = None


def chosen_route() -> str:
    """`route.SUDO` or `route.SERVICE`: chosen on the first call, then fixed for the run.

    Fixed because §4.7 forbids a route switch mid-run. The one change it allows is
    `_service_unreachable`'s fallback, which happens before any root command has run.
    """
    global _ROUTE
    if _ROUTE is None:
        from . import route
        _ROUTE = route.engine_route(os.environ)
    return _ROUTE


# Whether this run refreshes with `--gpg-auto-import-keys`. Set by `__main__` before
# `sudo_init`, because the service authorises it when the session opens and never
# after (ONEUP-0249 §4.4).
IMPORT_KEYS = False


def _open_service() -> bool:
    """Open this run's session with the service, or reuse the one already open.

    False when §4.7 allows falling back: the service unreachable, a D-Bus error that
    is not `NotAuthorized`, or polkit's `challenge` for a caller it had no agent to
    ask. A `dismissed` or `denied` answer ends the run as a cancelled validate does.
    """
    from . import service_client
    if service_client.has_session():
        return True
    try:
        service_client.open_session(
            interactive=os.environ.get("ONEUP_NONINTERACTIVE") != "1",
            import_keys=IMPORT_KEYS)
    except service_client.Refused as exc:
        if exc.code == "NotAuthorized" and exc.reason != "challenge":
            markers.err("Authentication failed or cancelled — aborting.")
            raise SystemExit(1) from None
        return False
    except service_client.Unreachable:
        return False
    return True


def _service_unreachable() -> None:
    """The service route failed before its session opened: fall back, or end the run.

    §4.7: only the `auto` route falls back, and only interactively, with one line saying
    so. A forced `ONEUP_BACKEND=service` fails the run, and a run nobody started by hand
    (`ONEUP_NONINTERACTIVE=1`) stands down rather than raise a box nobody can answer.
    """
    global _ROUTE
    from . import route
    if (os.environ.get("ONEUP_BACKEND") == route.SERVICE
            or os.environ.get("ONEUP_NONINTERACTIVE") == "1"):
        markers.err("OneUp's system service could not be reached — aborting.")
        raise SystemExit(1)
    markers.out("OneUp's system service could not be reached — asking for the password instead.")
    _ROUTE = route.SUDO


# How often the keep-alive re-validates. Overridable so a test can watch the loop
# exit inside its own patience — a 50-second sleep makes the property unobservable.
KEEPALIVE_SECONDS = os.environ.get("ONEUP_KEEPALIVE_SECONDS") or "50"

# `argv[1]` of the keep-alive child — under `-c`, `argv[0]` is "-c". A grep-able
# tag so a test can find these without matching every `sleep` on the machine;
# `pgrep -f oneup-keepalive` is what both scenarios use, so renaming it makes them
# pass by finding nothing.
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
    A new group, never a new session: started from a terminal, sudo keys the
    cached credential to that terminal's session, and a child in a new session
    has no terminal, so its refresh renewed a different record and the real one
    expired after five minutes (ONEUP-0231, measured on a run from Konsole).
    Detached from our stdout and stderr so it never pollutes the log stream, and
    so a consumer capturing our output is not held open by its sleep.

    Never two, and the early return below is what enforces it: a second
    keep-alive would overwrite the handle so `cleanup`'s group kill could only
    reach the later group — the orphan leak of ONEUP-0041 (INV-9).
    """
    global _KEEPALIVE
    if _KEEPALIVE is not None:
        return
    interval = KEEPALIVE_SECONDS if KEEPALIVE_SECONDS.replace(".", "", 1).isdecimal() else "50"
    # The tag rides in argv so `pgrep -f oneup-keepalive` finds this child; it is
    # read back out of sys.argv rather than used, which is why the loop skips it.
    _KEEPALIVE = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [sys.executable, "-c", _KEEPALIVE_SRC, KEEPALIVE_TAG, str(os.getpid()), interval],
        process_group=0,
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


def root(op: str, args: dict[str, object] | None = None, *, flags: Sequence[str] = (),
         merge_stderr: bool = False, stream: bool = False) -> tuple[int, str]:
    """Run one operation from `rootops`' table as root, and return what `sudo()` does.

    Both routes' entry to the table (ONEUP-0249 §4.2): the argv is built there,
    never at the call site, so the two routes run the same command. On the service
    route the service builds it and `flags`, which are sudo's own, do not apply. A
    refused argument runs nothing and returns 1 with one line saying why — the
    shape of any other failed root command, so no caller needs a second error path.
    """
    from . import rootops, route  # deferred: rootops reads this module's argvs
    if chosen_route() == route.SERVICE:
        return _service_root(op, args, merge_stderr=merge_stderr, stream=stream)
    try:
        argv = rootops.build(op, args)
    except rootops.Invalid as exc:
        markers.err(f"  Refusing root operation {op}: {exc}")
        return 1, ""
    return sudo(argv, flags=flags, merge_stderr=merge_stderr, stream=stream)


def _service_session() -> bool:
    """A session for a root call made before `sudo_init`, or False if the route fell back."""
    from . import route, service_client
    if not service_client.has_session():
        sudo_init()
    return chosen_route() == route.SERVICE


def _service_job(op: str, args: dict[str, object] | None, *, merge_stderr: bool):
    """Start `op` on the service, or say why not and return None (§4.7: no switch mid-run)."""
    from . import service_client
    try:
        return service_client.run(op, dict(args or {}), merge_stderr=merge_stderr)
    except service_client.Refused as exc:
        if exc.code == "Invalid":
            markers.err(f"  Refusing root operation {op}: {exc.reason}")
        else:
            markers.err(f"  OneUp's system service refused {op}: {exc.code} {exc.reason}")
    except service_client.Unreachable as exc:
        markers.err(f"  OneUp's system service could not run {op}: {exc}")
    return None


def _service_root(op: str, args: dict[str, object] | None, *, merge_stderr: bool,
                  stream: bool) -> tuple[int, str]:
    """`root()` on the service route: the same status and output, from the service's job.

    A streamed call merges stderr, as `proc.run`'s pump does on the sudo route.
    """
    if not _service_session():
        return root(op, args, merge_stderr=merge_stderr, stream=stream)
    job = _service_job(op, args, merge_stderr=merge_stderr or stream)
    if job is None:
        return 1, ""
    if stream:
        for line in job.lines():
            print(line.rstrip("\n"), flush=True)   # through the log mirror, as `_pump`
        return job.wait(), ""
    text = job.read()
    return job.wait(), text


def root_stream(op: str, args: dict[str, object] | None = None, *, cdn_dir: str = "",
                step: str, phase: str, log: pathlib.Path, append: bool,
                stop_poll: float | None = None) -> int:
    """A transaction, read line by line by `proc` on either route; returns its status.

    On the sudo route this is `proc.stream_filtered` over `root_argv`. On the service
    route the service builds the argv, with its own CDN copy where `cdn` asks for one,
    and `proc.stream_job` reads the same lines. With `stop_poll`, the user's Stop is
    forwarded once while the job runs, because the service cannot read `stop.request`
    (§4.6).
    """
    from . import route
    if chosen_route() == route.SERVICE and _service_session():
        job = _service_job(op, args, merge_stderr=True)
        if job is None:
            return 1
        done = threading.Event()
        if stop_poll is not None:
            threading.Thread(target=_forward_stop, args=(done, stop_poll), daemon=True).start()
        try:
            return proc.stream_job(job.lines(), job.wait, step=step, phase=phase, log=log,
                                   append=append)
        finally:
            done.set()
    return proc.stream_filtered(root_argv(op, args, cdn_dir=cdn_dir), step=step, phase=phase,
                                log=log, append=append)


def _forward_stop(done: threading.Event, interval: float) -> None:
    """Call `Stop` once, the first time a stop is requested while the job runs."""
    from . import service_client
    while not done.wait(interval):
        if proc.stop_requested():
            with contextlib.suppress(service_client.Refused, service_client.Unreachable):
                service_client.stop()
            return


def root_argv(op: str, args: dict[str, object] | None = None, *,
              cdn_dir: str = "") -> list[str]:
    """`root()`'s argv, sudo-headed, for a child the caller streams itself.

    Raises `rootops.Invalid`: its one caller passes arguments it built itself,
    so a refusal there is a bug to surface, not a run condition.
    """
    from . import rootops
    return sudo_argv(rootops.build(op, args, cdn_dir=cdn_dir))


def sudo_argv(argv: Sequence[str]) -> list[str]:
    """The sudo-headed argv for a child this module does not run itself.

    `proc.stream_filtered` reads a transaction's output line by line, which
    `sudo()` above cannot do. Routing that argv through here keeps the rule of
    this module whole: the environment is installed, and the prefix is written
    once (ONEUP-0174).
    """
    install_environment()
    return ["sudo", *argv]


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
        if not any(mark in args for mark in _PROMPT_MARKS):
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
    _close_service()
    kill_keepalive()


def _close_service() -> None:
    """End the service session, after the re-enables that need it. A no-op on sudo."""
    if _ROUTE is not None:
        from . import route
        if _ROUTE == route.SERVICE:
            from . import service_client
            service_client.close()


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

