"""Refresh, skip and disable repositories.

`docs/specs/ONEUP-0054-python-engine.md` §4.2 places this module. It is
deliberately separate from `parsers.py`: an earlier draft had one `zypper.py`
holding the pure parsers *and* the code that calls `sudo`, which would have made
§4.3.4's table-driven tests import the privileged half to reach the pure one.

Only the text-parsing halves live next door. The `$ZYPP_PID_FILE` and
`/proc/<pid>` probe stay here; so does `enabled_repo_aliases`' `zypper lr -u`
invocation, whose table `parsers.enabled_aliases` reads.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from . import markers, parsers, privilege, proc

# Overridable so tests never read or damage the real machine's state
# (`docs/standards/testing.md` §2).
ZYPP_PID_FILE = Path(os.environ.get("ONEUP_ZYPP_PID_FILE") or "/run/zypp.pid")
REPOS_DIR = Path(os.environ.get("ONEUP_REPOS_DIR") or "/etc/zypp/repos.d")

# Aliases WE disabled this run. `cleanup` re-enables every one (§4.2's split
# table calls this the part of `cleanup` to be careful with).
DISABLED: list[str] = []

# A FULL match, not an anchored `re.match`. Bash's `=~ ^…$` rejects a trailing
# newline; Python's `$` matches before one, so `re.match` on the same pattern
# accepts "oss\n" — measured. This is the shape guard
# `docs/standards/security.md` §4 puts in front of a privileged command, so the
# two engines must not disagree about what it lets through.
_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9:@._+-]*")

# A failure that is one repository's fault rather than the transaction's.
_REPO_SCOPED = re.compile(
    r"signature|GPG|key|metadata|Valid metadata not found|Curl|could not resolve"
    r"|Download.*failed|Skipping repository",
    re.IGNORECASE,
)


def valid_alias(alias: str) -> bool:
    """`valid_alias`: is this safe to pass to a privileged command?"""
    return bool(_ALIAS.fullmatch(alias))


def enabled_repo_aliases() -> list[str]:
    """The alias of each ENABLED repository. Read-only; no root."""
    _, text = proc.run(
        ["zypper", "--non-interactive", "lr", "-u"],
        env={"LC_ALL": "C"},  # keeps the column layout parseable on any locale
    )
    return parsers.enabled_aliases(text)


def lock_holder() -> str | None:
    """"<pid> <name>" of whatever else holds the package lock, or None.

    One busy program makes every zypper step below fail for the same
    uninteresting reason, and zypper says so only in its own words (ONEUP-0039).
    libzypp records the holder's pid in a world-readable file, so we can name it
    before touching anything.
    """
    try:
        text = ZYPP_PID_FILE.read_text()
    except OSError:
        return None
    pid = parsers.lock_pid(text)
    if pid is None:
        return None
    # A pid with no /proc entry is a stale lock from a crashed run, not a live
    # holder — zypper clears it itself, so it must not block us.
    if not Path(f"/proc/{pid}").is_dir():
        return None
    if pid == os.getpid():
        return None
    try:
        name = Path(f"/proc/{pid}/comm").read_text().strip()
    except OSError:
        name = ""
    return f"{pid} {name or 'another program'}"


def repo_scoped_failure(log: Path) -> bool:
    """Did this transaction fail for one repository's reason?"""
    try:
        text = log.read_text(errors="replace")
    except OSError:
        return False
    return bool(_REPO_SCOPED.search(text))


def make_cdn_reposd() -> str:
    """A throwaway repos.d pointing openSUSE mirrors at the CDN (ONEUP-0094).

    **The alias is the cache key.** libzypp keys `/var/cache/zypp/packages/`
    by repository alias, and an openSUSE alias usually CONTAINS the host name
    (`download.opensuse.org-oss`) — so a blanket host substitution renames the
    alias and silently discards every package already downloaded, defeating
    ONEUP-0087 on the one path where the kept cache matters most. The
    substitution is anchored to `baseurl=` lines carrying that host, and to
    nothing else.

    Returns "" on any failure: a recovery attempt that cannot be staged simply
    does not happen.
    """
    try:
        directory = tempfile.mkdtemp()  # 0700 by default; root only reads it
    except OSError:
        return ""
    try:
        sources = sorted(REPOS_DIR.glob("*.repo"))
        if not sources:
            shutil.rmtree(directory, ignore_errors=True)
            return ""
        for src in sources:
            text = src.read_text(errors="replace")
            rewritten = "\n".join(
                _cdn_line(line) for line in text.split("\n")
            )
            (Path(directory) / src.name).write_text(rewritten)
    except OSError:
        shutil.rmtree(directory, ignore_errors=True)
        return ""
    return directory


_BASEURL = re.compile(r"^baseurl[ \t]*=", re.IGNORECASE)
_CDN_HOST = re.compile(r"(https?://)download\.opensuse\.org", re.IGNORECASE)


def _cdn_line(line: str) -> str:
    """Rewrite one line, and only if it is a `baseurl=` naming that host."""
    if not _BASEURL.match(line):
        return line
    return _CDN_HOST.sub(r"\1downloadcontentcdn.opensuse.org", line)


# --- the privileged half -----------------------------------------------------

# Whether this run's refresh hit a problem, and whether it has refreshed at all.
# A later step needs to tell fresh metadata from stale without paying for a
# second refresh — the orphans step is reached with the second still False
# whenever the system step was not selected.
REFRESH_FAILED = False
REPOS_REFRESHED = False

# "<alias> <reason>" per enabled repository that fails its own refresh.
FAILING: list[str] = []

_SIGNATURE = re.compile(r"signature|GPG|key", re.IGNORECASE)
_METADATA = re.compile(r"metadata|Valid metadata not found", re.IGNORECASE)

# `timeout` runs AS ROOT so it can actually kill its zypper child, and its exit
# 124 means "I killed it" — a slow server, not a broken repository.
_TIMED_OUT = 124

# Resolved once, and by path: the ONEUP-0023 drop-in grants
# `timeout <budget> zypper *` against the path sudo will resolve, so the argv here and
# the granted rule have to name the same binary.
# The refresh argv lives in privilege.py, read by this call site and by the
# sudoers rule that grants it (ONEUP-0092 §4.2).
REFRESH_TIMEOUT = privilege.REFRESH_TIMEOUT


def release_zypper_lock() -> None:
    """Stop the desktop updater if it is holding the package lock."""
    if proc.succeeds(["systemctl", "is-active", "--quiet", "packagekit"]):
        markers.out("Stopping the desktop updater (PackageKit) so it isn't "
                    "holding the package lock...")
        privilege.sudo(["systemctl", "stop", "packagekit"])


def disable_repo(alias: str, reason: str) -> bool:
    """Disable one repository. Fail-closed, and records what to re-enable."""
    if not valid_alias(alias):
        markers.err(f"  Refusing unsafe repo alias: {alias}")
        return False
    rc, _ = privilege.sudo(["zypper", "--non-interactive", "modifyrepo", "--disable", alias])
    if rc != 0:
        return False
    DISABLED.append(alias)
    markers.marker("REPO_SKIPPED", f"{alias}|{reason}")
    return True


def find_failing_repos() -> list[str]:
    """Which enabled repositories fail their own refresh, and why.

    Fills `FAILING` and returns it. The classification stays here rather than in
    `parsers.py`: §4.2 places this function whole and its `parsers.py` row names
    nothing of it.
    """
    global FAILING
    FAILING = []
    for alias in enabled_repo_aliases():
        if not alias:
            continue
        rc, out = privilege.sudo(
            ["zypper", "--non-interactive", "refresh", alias], merge_stderr=True,
        )
        if rc == 0:
            continue
        if _SIGNATURE.search(out):
            reason = "signature"
        elif _METADATA.search(out):
            reason = "metadata"
        else:
            reason = "unreachable"
        FAILING.append(f"{alias} {reason}")
    return FAILING


def refresh_repos(*, import_keys: bool = False) -> None:
    """Refresh each enabled repository on its own, with its own time budget.

    One bulk `zypper refresh` cannot give any of the three things this buys
    (ONEUP-0048): a NAME, so `@@REFRESH@@` says which source is being fetched —
    bulk refresh reports progress as undelimited dots with no newline, and a
    line-based reader draws nothing at all for the whole phase; an ESCAPE, since
    zypper has no timeout of its own and a mirror serving an 18 MB index at
    1 KB/s hangs the run for hours; and a STOP, because the request is checked
    between repositories, which is the longest phase of a run and free to leave,
    nothing having been installed yet.
    """
    global REFRESH_FAILED, REPOS_REFRESHED
    REPOS_REFRESHED = True
    gpg = ["--gpg-auto-import-keys"] if import_keys else []
    aliases = [a for a in enabled_repo_aliases() if a]
    total = len(aliases)
    if total == 0:
        # The repository list is only available by parsing zypper's own table,
        # so it can come back empty. Fall back to one bulk refresh: upgrading
        # from stale metadata because we quietly skipped the refresh is far
        # worse than losing the per-source progress.
        rc, _ = privilege.sudo(
            ["zypper", "--non-interactive", *gpg, "refresh"], stream=True,
        )
        if rc != 0:
            REFRESH_FAILED = True
        return
    for i, alias in enumerate(aliases, start=1):
        if proc.stop_pending():
            return
        markers.marker("REFRESH", f"{i}|{total}|{alias}")
        rc, _ = privilege.sudo(
            [*(privilege.REFRESH_SUDO_ARGV or ["timeout", REFRESH_TIMEOUT, "zypper"]),
             "--non-interactive", *gpg, "refresh", alias],
            stream=True,
        )
        if rc == 0:
            continue
        if rc == _TIMED_OUT:
            # A slow server, not a broken repository — say so in those words and
            # offer the skip the window already knows how to apply. The repo is
            # NOT disabled here: we simply could not refresh it this run.
            markers.out(f"  Gave up on '{alias}' after {REFRESH_TIMEOUT}s — "
                        "its server is too slow right now.")
            markers.hint(
                f"The '{alias}' source is serving updates too slowly to wait for, so OneUp "
                f'moved on. Use "Skip {alias} & update the rest" to leave it out of the '
                "next run, or try again later."
            )
            markers.marker("REMEDY", f"skip-repo|{alias}")
        REFRESH_FAILED = True
