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

import os
import shutil
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
