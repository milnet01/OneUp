"""The runs that are not an update.

`--auth-status`, the `--emit-guard` that proves a guard is current, the
read-only `--check`, `--size=`, the grant/revoke pair and `--thin-snapshots`.
The hold that `--size --hold` waits in is `runstate.py`'s: it writes a state
file, so it belongs beside the others.
"""

from __future__ import annotations

import contextlib
import getpass
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from . import markers, parsers, privilege, proc, repos, steps

if TYPE_CHECKING:  # the run-time import would be a cycle — `__main__` imports this module
    from .__main__ import Options

# Overridable so the suite points them at throwaway paths, never real /etc.
AUTH_FILE = Path(os.environ.get("ONEUP_AUTH_FILE") or "/etc/sudoers.d/oneup")

# /usr/libexec per FHS 3.0 (Tumbleweed since 2020), /usr/lib on Leap 15.x.
GUARD_DIR = "/usr/libexec" if Path("/usr/libexec").is_dir() else "/usr/lib"
GUARD_FILE = Path(os.environ.get("ONEUP_GUARD_FILE") or f"{GUARD_DIR}/oneup-download-guard")

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
    # Both argvs are written once, in privilege.py, and read by the call site AND by
    # this rule (ONEUP-0092 §4.2). `None` means the binary is absent — refuse the whole
    # rule rather than emit a bare name, which visudo rejects outright, taking the
    # user's working sudoers with it.
    refresh, cache_du = privilege.REFRESH_SUDO_ARGV, privilege.CACHE_DU_ARGV
    if refresh is None or cache_du is None:
        return None
    # The budget lands in the one slot a wildcard would make exploitable, and it arrives
    # from the environment, so it is pinned to digits rather than trusted: `5 *` would
    # generate `timeout 5 * zypper *`, which visudo accepts and which
    # `timeout 5 /bin/sh -c 'zypper x'` then satisfies.
    if not refresh[1].isdigit():
        return None
    cmds.append(" ".join(refresh) + " *")   # timeout <budget> zypper …
    cmds.append(" ".join(cache_du))         # exactly this
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


# --- `--check`: the read-only "what would update?" pass -----------------------
#
# Never becomes root and never mutates: an unattended timer runs it, so a
# password prompt would strand the run. It reads the repository METADATA cache
# it cannot refresh, which is why it has to be scrupulous about saying when the
# metadata was not there to read (ONEUP-0056).

APP_ID = "za.co.antsprojectshub.OneUp"

# zypper marks an upgradable package with `v` in its status column.
_V_ROW = re.compile(r"^v[ \t]*\|")
_SKIPPED = re.compile(r"Skipping repository '([^']*)'")


def notify_send(title: str, body: str) -> None:
    """A desktop notification. Not a marker, and never fatal."""
    if shutil.which("notify-send"):
        proc.run(["notify-send", "-a", "OneUp", "-i", APP_ID, title, body])


def _check_system() -> tuple[int, bool]:
    """Count pending system updates. Returns (count, whether a source was unreadable)."""
    # One read serves both the count and the per-package detail. stderr is MERGED
    # rather than discarded: zypper reports a repository it had to set aside as a
    # warning there (exit 106), and that warning is the only difference between
    # "nothing to update" and "I couldn't read the repository that had the updates".
    # Merging is safe — every line parsed below is anchored to the `v` status column.
    rc, text = proc.run(
        ["zypper", "--no-refresh", "--non-interactive", "list-updates"],
        merge_stderr=True,
        env={"LC_ALL": "C"},  # keeps the column layout parseable on any locale
    )
    rows = [line for line in text.splitlines() if _V_ROW.match(line)]
    n = len(rows)
    unreadable = ""
    if rc != 0:
        # 106 = ZYPPER_EXIT_INF_REPO_SKIPPED. Name the repositories if zypper did;
        # otherwise report the failure without guessing at a cause.
        skipped = sorted(set(_SKIPPED.findall(text)))
        if skipped:
            unreadable = "OneUp couldn't read these software sources: " + ", ".join(skipped)
        else:
            unreadable = f"OneUp couldn't read the software sources (zypper exited {rc})"
        unreadable += " — this list may be incomplete. Running an update refreshes them."
        markers.out(f"  System packages: couldn't check — {unreadable}")
    else:
        markers.out(f"  System packages: {n} update(s)")
    markers.emit_check("system", n, "system package(s)", unreadable)
    # Columns: S | Repository | Name | Current | Available | Arch.
    for line in rows:
        f = [field.strip() for field in line.split("|")]
        if len(f) >= 5 and f[2]:
            markers.marker("CHECK_ITEM", f"system|{f[2]}|{f[3]}|{f[4]}")
    return n, bool(unreadable)


def _check_flatpak() -> tuple[int, bool]:
    """Count pending Flatpak updates, asking each remote separately."""
    # `flatpak remote-ls --updates` with no remote named abandons the WHOLE listing
    # the moment any single remote can't be summarised — and a local --no-enumerate
    # origin (what `flatpak install ./app.flatpak` leaves behind) never can be.
    # Measured: six such leftovers on one box hid a real Discord update for weeks.
    # Per-remote, one broken source costs only itself.
    rows: list[str] = []
    unreachable: list[str] = []
    for scope in ("--user", "--system"):
        _, listing = proc.run(["flatpak", "remotes", scope, "--columns=name,options"])
        for entry in listing.splitlines():
            remote, _, opts = entry.partition("\t")
            if not remote.strip():
                continue
            rc, out = proc.run(
                ["flatpak", "remote-ls", "--updates", scope, remote,
                 "--columns=application,version"],
            )
            if rc == 0:
                rows += [r for r in out.splitlines() if r.strip()]
            elif "no-enumerate" not in opts:
                # A no-enumerate origin serves no listing BY DESIGN — apps installed
                # from a local file have no remote updates to miss, so it is not a
                # failed check. Any other remote failing means apps went uncounted.
                unreachable.append(remote)
    n = len(rows)
    unreadable = ""
    if unreachable:
        unreadable = ("OneUp couldn't reach these Flatpak sources: "
                      + ", ".join(unreachable)
                      + " — this list may be incomplete.")
        markers.out(f"  Flatpak apps: couldn't check — {unreadable}")
    else:
        markers.out(f"  Flatpak apps: {n} update(s)")
    markers.emit_check("flatpak", n, "Flatpak app(s)", unreadable)
    for row in rows:
        parts = row.split()
        if parts:
            version = parts[1] if len(parts) > 1 else ""
            markers.marker("CHECK_ITEM", f"flatpak|{parts[0]}||{version}")
    return n, bool(unreadable)


def _check_firmware() -> tuple[int, bool]:
    """Ask fwupd whether anything is pending, and say when it could not answer.

    fwupdmgr(1) EXIT STATUS: 0 = ran and found something, 2 = ran with no actions,
    1/3 = it could not answer. The docstring here used to read "yes or no, so there
    is no unreadable case", which is a property the tool's exit surface does not
    have — an unreachable daemon rendered as a bare zero, i.e. "you're up to date".
    """
    fw_rc, _ = proc.run(["fwupdmgr", "get-updates"])
    if fw_rc not in (0, 2):
        markers.marker("CHECK_UNKNOWN", "firmware|OneUp couldn't ask fwupd")
        markers.out("  Firmware: couldn't check")
        return 0, True
    n = 1 if fw_rc == 0 else 0
    # Emitted DIRECTLY, not through `emit_check`: a firmware zero we DID earn is
    # reported on purpose, which that emitter's suppression rule would withhold.
    markers.marker("CHECK", f"firmware|{n}|firmware update(s)")
    markers.out("  Firmware: " + ("available" if n else "up to date"))
    return n, False


def check(opts: Options) -> int:
    """`--check`: report what WOULD update, install nothing, become root nowhere.

    `orphans` and `cache` have no check arm, and a step whose tool is absent is
    not checked at all — neither case emits a marker of any kind.
    """
    markers.out("Checking for available updates (read-only)…")
    total = 0
    incomplete = False
    if opts.selected("system"):
        n, bad = _check_system()
        total += n
        incomplete = incomplete or bad
    if opts.selected("flatpak") and shutil.which("flatpak"):
        n, bad = _check_flatpak()
        total += n
        incomplete = incomplete or bad
    if opts.selected("firmware") and shutil.which("fwupdmgr"):
        n, bad = _check_firmware()
        total += n
        incomplete = incomplete or bad
    # A step whose read FAILED still contributes its partial count: incompleteness is
    # carried by CHECK_UNKNOWN and by the wording below, never by a lowered total.
    markers.marker("CHECK", f"TOTAL|{total}|updates available")
    if incomplete:
        markers.out(f"  Total: {total} update(s) found, "
                    "but at least one source couldn't be read")
        markers.out("         — treat this as a floor, not an all-clear.")
    else:
        markers.out(f"  Total: {total} update(s) available.")
    if opts.notify and total > 0:
        notify_send("Updates available",
                    f"{total} update(s) ready to install. Open OneUp to update.")
    markers.marker("DONE", "ok")
    return 0


# --- `--size=<step>`: what would this cost to download? -----------------------

# zypper's INFORMATIONAL exits (update / reboot / restart needed). A non-zero
# code here is not a failure and must not be mistaken for one.
_INF_FIRST, _INF_LAST = 100, 103

# The documented exit codes worth naming, in the user's words rather than
# zypper's. Anything else reports its code and shows what zypper actually said.
_WHY = {
    7: "another program is using the package manager (PackageKit, or a zypper "
       "you have open elsewhere) — close it and try again.",
    5: "OneUp wasn't allowed to run the check as administrator — the password "
       "prompt may have been cancelled.",
    6: "no software sources are enabled, so there is nothing to weigh up.",
}

# How many lines of zypper's own output to show after a failed dry run. `out` is
# captured into a variable, so without this the log records only "unavailable"
# and the user has nothing to act on.
_TAIL = 5

EXIT_WRONG_STEP = 2


# The size this process quoted, for `hold.state`'s third line.
HOLD_SIZE = ""
# Set by the caller when `--hold` was asked for, so the DONE is withheld.
HOLDING = False


def size_delivered(size: str) -> None:
    """Close out a successful `--size` probe.

    Under `--hold` the process does not end here and the `@@DONE@@` is withheld
    until its true end — the marker reference describes exactly one DONE per run
    (§4.9), and for a run another window merely FOLLOWED through `run.state` it
    is the only verdict there is. Two in one stream, the first saying ok before
    a single step had run, is what breaks that reader.
    """
    global HOLD_SIZE
    HOLD_SIZE = size
    if not HOLDING:
        markers.marker("DONE", "ok")


def run_size(step: str) -> int:
    """`--size=<step>`: price the system transaction without performing it."""
    if step != "system":
        markers.err("Download-size preview is only available for the system step.")
        return EXIT_WRONG_STEP
    privilege.sudo_init()
    repos.release_zypper_lock()
    markers.out("Calculating download size (dry run)…")
    # The locale is pinned as an ARGV PREFIX, not as a child environment: sudo
    # resets the environment, so `LC_ALL` set on the child never reaches zypper —
    # and `auth_cmnds` grants the literal words `env LC_ALL=C zypper *`, so a
    # passwordless user's rule matches this argv and no other.
    #
    # The same argv the run itself will use (ONEUP-0085 INV-5): a flag here that
    # the transaction does not have would quote a different transaction's size.
    rc, out = privilege.sudo(
        ["env", "LC_ALL=C", *steps.system_txn_argv(), "--dry-run"], merge_stderr=True,
    )
    size = parsers.download_size(out)
    if size:
        markers.marker("SIZE", f"system|{size}")
        markers.out(f"  Download size: {size}")
        size_delivered(size)
        return 0
    if rc == 0 or _INF_FIRST <= rc <= _INF_LAST:
        # zypper ran fine and reported no size = nothing to fetch (up to date, or
        # all cached). Report zero so the window shows a definitive answer.
        markers.marker("SIZE", "system|0 B")
        markers.out("  Download size: nothing to fetch.")
        size_delivered("0 B")
        return 0
    # The dry run FAILED. Never answer "0 B" here: a confident zero the run did
    # not earn is the exact failure class the test suite exists to prevent. Stay
    # silent on SIZE and return non-zero — the window re-arms its "Show download
    # size" link for a retry.
    why = _WHY.get(rc, f"the package manager reported an error (code {rc}) — see the lines below.")
    markers.hint(f"Couldn't work out the download size: {why}")
    markers.out(f"  Download size: unavailable — {why}")
    for line in out.rstrip("\n").split("\n")[-_TAIL:]:
        markers.out(f"    zypper: {line}")
    return 1


def build_auth_rule() -> str | None:
    """The sudoers drop-in's text, or None when the scope cannot be built."""
    cmnds = auth_cmnds()
    if cmnds is None:
        return None
    user = getpass.getuser()
    return (
        '# Installed by OneUp\'s "remember my authorization" setting — stores NO password.\n'
        f"# Lets {user} run OneUp's update commands as root without a password prompt.\n"
        "# Delete this file (or turn the setting off in OneUp) to revoke immediately.\n"
        f"Cmnd_Alias ONEUP_UPDATE = {cmnds}\n"
        f"{user} ALL=(root) NOPASSWD: ONEUP_UPDATE\n"
    )


_GRANT_IMPOSSIBLE = (
    "Passwordless authorization can't be set up on this machine: zypper, timeout or du "
    "was not found, or the refresh budget is not a whole number of seconds."
)


def grant_auth() -> int:
    """Install the guard and the sudoers drop-in — in that order, all or nothing.

    The order is fixed and each position is load-bearing (ONEUP-0092 §4.3):
    validate FIRST so a malformed rule costs nothing, then the guard, then the
    drop-in — and any failure after the guard lands removes it again. A stranded
    root-owned executable is worse than a failed grant: the toggle then reads
    off, which makes the window's revoke arm unreachable, so the user has
    consented to a file they can no longer withdraw.
    """
    rule, guard = build_auth_rule(), download_guard_src()
    if rule is None or guard is None:
        markers.hint(_GRANT_IMPOSSIBLE)
        return 1
    try:
        rule_file, guard_file = _spill(rule), _spill(guard)
    except OSError:
        markers.hint("Could not create a temporary file.")
        return 1
    try:
        privilege.sudo_init()
        # Validate the generated rule in ISOLATION before it can affect the live
        # policy: a syntactically broken file under /etc/sudoers.d can lock the
        # user out of sudo entirely.
        if privilege.sudo(["visudo", "-cf", rule_file])[0] != 0:
            markers.hint("The generated authorization rule failed validation — "
                         "nothing was changed.")
            return 1
        # 0755: the window and the engine both read the guard back to tell whether
        # the drop-in beside it is the one this OneUp needs; only root may write it.
        if privilege.sudo(["install", "-o", "root", "-g", "root", "-m", "0755",
                           guard_file, str(GUARD_FILE)])[0] != 0:
            markers.hint(f"Could not write the download helper ({GUARD_FILE}).")
            return 1
        # install(1) places it root-owned and 0440 atomically, the mode sudo requires.
        if privilege.sudo(["install", "-o", "root", "-g", "root", "-m", "0440",
                           rule_file, str(AUTH_FILE)])[0] != 0:
            privilege.sudo(["rm", "-f", str(GUARD_FILE)])   # never leave a guard ruleless
            markers.hint(f"Could not write the authorization rule ({AUTH_FILE}).")
            return 1
    finally:
        for path in (rule_file, guard_file):
            with contextlib.suppress(OSError):
                os.unlink(path)
    markers.out("Passwordless authorization for OneUp's update commands is now enabled.")
    markers.marker("AUTH", "on")
    return 0


def _spill(text: str) -> str:
    """Write `text` to a fresh temporary file and return its path."""
    handle, path = tempfile.mkstemp(prefix="oneup-auth-")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(text)
    return path


def revoke_auth() -> int:
    """Remove the drop-in and the guard, sweeping BOTH candidate guard paths.

    `GUARD_DIR` is recomputed per run, so a `/usr/libexec` created by another
    package after the grant would move it and leave the `/usr/lib` copy beyond
    reach. With the override set the sweep collapses to that one path — the
    override exists so the suite never touches a real system directory.
    """
    privilege.sudo_init()
    if os.environ.get("ONEUP_GUARD_FILE"):
        guards = [str(GUARD_FILE)]
    else:
        guards = ["/usr/libexec/oneup-download-guard", "/usr/lib/oneup-download-guard"]
    if privilege.sudo(["rm", "-f", str(AUTH_FILE), *guards])[0] != 0:
        markers.hint(f"Could not remove the authorization rule ({AUTH_FILE}).")
        return 1
    markers.out("Passwordless authorization has been revoked.")
    markers.marker("AUTH", "off")
    return 0


def thin_snapshots() -> int:
    """Run snapper's OWN retention cleanup and report the before/after difference.

    Only the `number` and `timeline` algorithms, which drop nothing the
    configured policy does not already consider surplus — we never hand-delete a
    specific snapshot, so the most recent rollback points are always kept.
    """
    if not shutil.which("snapper"):
        markers.hint("Snapper isn't installed, so there are no snapshots to thin.")
        return 0
    privilege.sudo_init()
    before = _snapshot_count()
    for algorithm in ("number", "timeline"):
        privilege.sudo(["snapper", "cleanup", algorithm], merge_stderr=True, stream=True)
    after = _snapshot_count()
    if before is not None and after is not None and before > after:
        markers.out(f"Thinned {before - after} old snapshot(s) ({before} → {after}).")
        markers.marker("SNAPSHOTS", f"thinned|{before - after}")
    else:
        # Zero rather than nothing: a run that removed none still answered the
        # question, and the window has no other way to tell that from silence.
        markers.out("No snapshots needed thinning — snapper's retention policy is "
                    "already satisfied.")
        markers.marker("SNAPSHOTS", "thinned|0")
    return 0


def _snapshot_count() -> int | None:
    """How many snapshots snapper lists, or None when it could not be read."""
    rc, listing = privilege.sudo(["snapper", "--no-headers", "list"])
    if rc != 0:
        return None
    return len([line for line in listing.splitlines() if line.strip()])
