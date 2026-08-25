"""The runs that are not an update.

Stage 2 builds `--auth-status` and the `--emit-guard` that proves a guard is
current. `--check`, `--size=`, the grant/revoke pair and `--thin-snapshots`
follow at their own stages.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import markers, privilege

# Overridable so the suite points them at throwaway paths, never real /etc.
AUTH_FILE = Path(os.environ.get("ONEUP_AUTH_FILE") or "/etc/sudoers.d/oneup")

# /usr/libexec per FHS 3.0 (Tumbleweed since 2020), /usr/lib on Leap 15.x.
GUARD_DIR = "/usr/libexec" if Path("/usr/libexec").is_dir() else "/usr/lib"
GUARD_FILE = Path(os.environ.get("ONEUP_GUARD_FILE") or f"{GUARD_DIR}/oneup-download-guard")

# The refresh budget, matching the engine's own default. It reaches auth_cmnds from the
# environment, so it is pinned to digits there rather than trusted.
REFRESH_TIMEOUT = os.environ.get("ONEUP_REFRESH_TIMEOUT") or "120"


def auth_cmnds() -> str | None:
    """The granted scope, written in ONE place (ONEUP-0092).

    Built from the binaries actually present on THIS machine, so each rule
    matches the exact path sudo will resolve. zypper is required; the optional
    ones are skipped when absent. Returns None when the scope cannot be built —
    a bare command name makes visudo reject the whole file.
    """
    zypper = shutil.which("zypper")
    if not zypper:
        return None
    cmds = [zypper]                                    # any zypper subcommand
    for name in ("snapper", "flatpak"):                # snapper create/list, flatpak update
        found = shutil.which(name)
        if found:
            cmds.append(found)
    systemctl = shutil.which("systemctl")
    if systemctl:
        cmds.append(f"{systemctl} stop packagekit")
    # The engine pins the locale via `sudo env LC_ALL=C zypper …`. sudo resolves the
    # command (env) to a path but matches the REST of the argv literally, so this
    # pattern's second word must be the bare `zypper` the engine typed, not its path.
    env = shutil.which("env")
    if env:
        cmds.append(f"{env} LC_ALL=C zypper *")
    timeout, du = shutil.which("timeout"), shutil.which("du")
    if not timeout or not du:
        return None
    # The budget lands in the one slot a wildcard would make exploitable, and it arrives
    # from the environment, so it is pinned to digits rather than trusted: `5 *` would
    # generate `timeout 5 * zypper *`, which visudo accepts and which
    # `timeout 5 /bin/sh -c 'zypper x'` then satisfies.
    if not REFRESH_TIMEOUT.isdigit():
        return None
    cmds.append(f"{timeout} {REFRESH_TIMEOUT} zypper *")   # timeout <budget> zypper …
    cmds.append(f"{du} -sB1 /var/cache/zypp")              # exactly this
    cmds.append(str(GUARD_FILE))                           # any args: the guard restricts itself
    return ", ".join(cmds)


def download_guard_src() -> str | None:
    """The download guard's text — the single source, and the bytes that get installed.

    Compared byte-for-byte by `guard_current`, so every edit here re-grants for
    every user (`docs/standards/security.md` §5.7). It must also stay identical
    to `update_system.sh`'s `download_guard_src`: a guard granted by either
    engine has to read as current to the other.
    """
    zypper = shutil.which("zypper")
    if not zypper:
        return None
    scope = auth_cmnds()
    if scope is None:
        return None
    # `# oneup-auth-scope:` is what makes this file a version stamp for the drop-in beside
    # it: the drop-in is 0440 root-only, so the engine cannot read back what it granted,
    # but both files are written by the same grant and this one is world-readable.
    return f"""#!/bin/bash
# Installed by OneUp's "remember my authorization" setting (ONEUP-0092). Runs the package
# download as root so a Stop request can reach zypper, which an unprivileged parent cannot
# signal. It can exec exactly one program — the zypper below — so granting it in sudoers
# grants no more than the drop-in's own zypper entry.
# Delete it (or turn the setting off in OneUp) to revoke.
# oneup-auth-scope: {scope}
export LC_ALL=C
stop_file="$1"; run_state="$2"; poll="$3"
[[ "$4" == zypper ]] || {{ echo "oneup-download-guard: refusing to run '$4'" >&2; exit 2; }}
shift 4
"{zypper}" "$@" --download-only &
z=$!
while kill -0 "$z" 2>/dev/null; do
    # Same staleness rule as stop_pending: a request older than run.state is a leftover.
    # Re-implemented because a shell function cannot cross sudo.
    if [[ -e "$stop_file" && -e "$run_state" && "$stop_file" -nt "$run_state" ]]; then
        kill -TERM "$z" 2>/dev/null
        break
    fi
    sleep "$poll"
done
wait "$z"        # never exit without reaping — an unreaped root child is the
exit $?          # ONEUP-0041 orphan shape, one level down
"""


def guard_current() -> bool:
    """Is the installed guard the one THIS engine expects?

    A pure file comparison — no sudo, so it is safe to call mid-run. Trailing
    newlines are stripped on both sides, matching the Bash engine's command
    substitution: this compares the text rather than the bytes.
    """
    want = download_guard_src()
    if want is None:
        return False
    try:
        have = GUARD_FILE.read_text()
    except OSError:
        return False
    return have.rstrip("\n") == want.rstrip("\n")


def auth_current() -> bool:
    """Is passwordless actually working for THIS engine?

    Both halves are needed: the drop-in is live, AND it grants what this run
    needs. Asking only the first question of one command out of six is how
    ONEUP-0092's three uncovered calls went unseen.
    """
    zypper = shutil.which("zypper")
    if not zypper:
        return False
    # `-k` ignores any cached credential so a recent run cannot false-positive, and `-n`
    # refuses to prompt. Measured: -k does NOT invalidate a warm credential, so this is
    # safe to issue at any point in a run.
    rc, _ = privilege.sudo([zypper, "--version"], flags=("-k", "-n"))
    return rc == 0 and guard_current()


def auth_status() -> int:
    """`--auth-status`: report whether passwordless WORKS, not whether a rule exists.

    A drop-in installed by an older OneUp is live and still leaves a run
    prompting (`docs/standards/security.md` §5.6 — report real state, never a
    saved preference).
    """
    markers.marker("AUTH", "on" if auth_current() else "off")
    return 0


def emit_guard() -> int:
    """`--emit-guard`: print the guard this engine expects, for the caller to install."""
    src = download_guard_src()
    if src is None:
        markers.hint("Passwordless authorization can't be set up on this machine: "
                     "zypper, timeout or du was not found, or the refresh budget is not "
                     "a whole number of seconds.")
        return 1
    print(src, end="", flush=True)
    return 0
