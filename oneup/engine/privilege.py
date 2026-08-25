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
from collections.abc import Sequence

from . import proc

# Overridable so the suite points it at a mock instead of raising a real KDE dialog.
ASKPASS = os.environ.get("ONEUP_ASKPASS") or "/usr/libexec/ssh/ksshaskpass"

# Label EVERY prompt sudo may raise, including ones we did not pass -p to. sudo's own
# default reads "[sudo] password for root" under this distro's `targetpw` setting — an
# unlabelled request for the ROOT password looks like something nefarious to a user who
# only asked for a download size. A prompt nobody can attribute is one they should refuse
# (ONEUP-0037).
SUDO_PROMPT = "OneUp needs administrator rights to update this system. Password: "


def install_environment() -> None:
    """Export what sudo needs before any privileged call.

    EXPORTED, not merely set: sudo falls back to the askpass helper only when it
    finds `SUDO_ASKPASS` in the environment. Without it, a sudo that cannot see a
    cached credential has no way to ask and dies on "a terminal is required" —
    which is what made "Show download size" fail (ONEUP-0036).
    """
    os.environ["SUDO_ASKPASS"] = ASKPASS
    os.environ["SUDO_PROMPT"] = SUDO_PROMPT


def sudo(argv: Sequence[str], *, flags: Sequence[str] = (), merge_stderr: bool = False
         ) -> tuple[int, str]:
    """Run `argv` as root and return its status and output.

    The single sudo parent for the whole run. `flags` carries sudo's own options
    (`-k`, `-n`, `-A`); everything after them is the command.
    """
    install_environment()
    return proc.run(["sudo", *flags, *argv], merge_stderr=merge_stderr)
