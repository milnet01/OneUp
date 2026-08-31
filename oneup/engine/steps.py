"""Run the five steps: system, flatpak, firmware, orphans, cache.

Each step owns its own trap, and the traps are the reason the bodies are not
interchangeable: flatpak counts before it updates so it can say how many;
firmware claims success only when the flash itself succeeded, because that is
what drives the reboot advice; orphans refreshes under ONEUP-0048's guard when
the system step did not, and removes only *unneeded* packages while merely
reporting orphaned ones; cache keeps the downloads when the system step failed
(ONEUP-0087). A step whose tool is absent is `skip`, never `fail`.

The per-step outcome tables below are read by the run driver's summary. They
are module state rather than a passed-around record because the Bash engine's
`RESULT`/`DETAIL`/`SECS` are, and the summary, the reboot check, the service
split and `--notify` all read them from four different places in the run.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from . import markers, parsers, privilege, proc, repos, runstate

# Set by the download-recovery path (ONEUP-0094) to a throwaway repos.d built by
# `repos.make_cdn_reposd`. Empty means "use the system's own".
REPOSD_OVERRIDE = ""

# The human label per step key, in the run order both engines share. Also the
# closed vocabulary `adopt_go_ahead` tests a go-ahead's steps against.
LABEL = {
    "system": "Updating system packages",
    "flatpak": "Updating Flatpak apps",
    "firmware": "Checking firmware updates",
    "orphans": "Removing leftover packages",
    "cache": "Cleaning package cache",
}

# Per-step outcome tracking for the final summary.
RESULT: dict[str, str] = {}
DETAIL: dict[str, str] = {}
SECS: dict[str, int] = {}
ERRORS = 0

# Where we are in the run. TOTAL is set by the driver once the selection is made.
STEP_INDEX = 0
TOTAL = 0
_STEP_START = 0.0

# What the system step found, read by the reboot check and the summary.
SYS_CHANGED = False
SYS_COUNT = ""
SYS_REBOOT_DETAIL = ""
FW_CHANGED = False


def begin_step(key: str) -> None:
    """Announce a step: the banner, then `@@STEP_BEGIN@@`."""
    global STEP_INDEX, _STEP_START
    STEP_INDEX += 1
    _STEP_START = time.monotonic()
    markers.out("")
    markers.out("==========================================")
    markers.out(f"  [{STEP_INDEX}/{TOTAL}] {LABEL[key]}")
    markers.out("==========================================")
    markers.marker("STEP_BEGIN", f"{key}|{STEP_INDEX}|{TOTAL}|{LABEL[key]}")


def end_step(key: str, status: str, detail: str = "") -> None:
    """Close a step: record it, count a failure, then `@@STEP_END@@` and `@@TIMING@@`.

    Two markers in that order, because the window reads them separately — the
    timing is additional to the frozen `status|detail` contract, never part of it.
    """
    global ERRORS
    SECS[key] = int(time.monotonic() - _STEP_START)
    RESULT[key] = status
    DETAIL[key] = detail
    if status == "fail":
        ERRORS += 1
    markers.marker("STEP_END", f"{key}|{status}|{detail}")
    markers.marker("TIMING", f"{key}|{SECS[key]}")


# A per-call budget for the read-only Flatpak update counts — §4.3.2's runner,
# on a step other than the repo refresh. v1 has no budget here: `flatpak
# remote-ls --updates` reaches every configured remote, and a remote that
# accepts the connection then serves nothing hangs the step with the window
# showing an open step and no progress — the shape ONEUP-0048 measured on a
# crawling zypper mirror. The count is a best-effort figure the step already
# degrades without, so expiry can cost the detail line and never the update.
FLATPAK_QUERY_SECONDS = float(os.environ.get("ONEUP_FLATPAK_TIMEOUT") or "60")


def _lines(text: str) -> int:
    """`wc -l`: how many newline-terminated lines the text carries."""
    return text.count("\n")


def run_flatpak() -> None:
    """Update Flatpak apps in both scopes, then drop unused runtimes."""
    begin_step("flatpak")
    if not _have("flatpak"):
        markers.out("Flatpak is not installed. Skipping.")
        end_step("flatpak", "skip", "not installed")
        return
    ok = True
    # Count what will update FIRST — the same read-only query `--check` uses — so
    # the detail can say how many apps were updated rather than just "done".
    count = 0
    for scope in ("--user", "--system"):
        rc, out = proc.run(["flatpak", "remote-ls", "--updates", scope],
                           deadline=FLATPAK_QUERY_SECONDS)
        if rc == 0:
            count += _lines(out)
    if proc.run(["flatpak", "update", "--user", "-y"], stream=True)[0] != 0:
        ok = False
    if privilege.sudo(["flatpak", "update", "--system", "-y"], stream=True)[0] != 0:
        ok = False
    markers.out("Cleaning up unused Flatpak runtimes...")
    proc.run(["flatpak", "uninstall", "--user", "--unused", "-y"], stream=True)
    privilege.sudo(["flatpak", "uninstall", "--system", "--unused", "-y"], stream=True)
    if not ok:
        end_step("flatpak", "fail", "a flatpak update failed")
    elif count > 0:
        end_step("flatpak", "ok", f"{count} app(s) updated")
    else:
        end_step("flatpak", "ok", "up to date")


def run_firmware() -> None:
    """Refresh fwupd's metadata, then flash whatever it offers.

    fwupd elevates through polkit on its own, so nothing here is under `sudo`.
    """
    global FW_CHANGED
    begin_step("firmware")
    if not _have("fwupdmgr"):
        markers.out("fwupd is not installed. Skipping.")
        end_step("firmware", "skip", "not installed")
        return
    proc.run(["fwupdmgr", "refresh"], stream=True)
    # fwupdmgr(1) EXIT STATUS: 0 = ran and found something, 2 = ran with no actions,
    # 1/3 = it could not answer. Treating every non-zero as "nothing to do" tells a
    # user their firmware is current when we never managed to ask.
    fw_rc, _ = proc.run(["fwupdmgr", "get-updates"])
    if fw_rc == 2:
        markers.out("No firmware updates available.")
        end_step("firmware", "ok", "up to date")
        return
    if fw_rc != 0:
        markers.out(f"Couldn't ask fwupd about firmware updates (exit {fw_rc}).")
        end_step("firmware", "fail", "couldn't check for firmware updates")
        return
    # Claim success only if the flash itself succeeded: a failed update must not
    # report "applied", because that is what advises the reboot.
    if proc.run(["fwupdmgr", "update", "-y"], stream=True)[0] == 0:
        FW_CHANGED = True
        end_step("firmware", "ok", "updates applied")
    else:
        end_step("firmware", "fail", "firmware update failed")


# A package name, for the same reason `repos.valid_alias` exists: this column is
# parsed out of zypper's own table — one of the untrusted sources security.md §4
# names — and the result is handed to a ROOT `zypper remove`. The leading class
# excludes `-`, so a spliced field can never be read as an option.
_PACKAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")


def valid_package(name: str) -> bool:
    """Is this safe to pass to a privileged `zypper remove`?"""
    return bool(_PACKAGE.fullmatch(name))


def _package_column(text: str) -> list[str] | None:
    """The name column of a `zypper packages` table: field 3, past the header.

    Returns None when any row fails the shape test — fail closed, per security.md
    §4.2. Dropping the bad row and removing the rest would be a clean-up-and-
    continue on the argv of a root package removal, which §4.4 forbids.
    """
    names = []
    for line in text.splitlines()[2:]:
        fields = line.split("|")
        if len(fields) < 3:
            continue
        name = fields[2].replace(" ", "")
        if not name:
            continue
        if not valid_package(name):
            markers.err(f"Refusing unsafe package name from zypper's table: {name!r}")
            return None
        names.append(name)
    return names


def run_orphans(opts) -> None:
    """Remove packages nothing needs any more; merely REPORT orphaned ones.

    Orphaned packages — installed but provided by no active repository — are
    often software the user installed by hand, so they are never auto-removed.
    """
    begin_step("orphans")
    # zypper auto-refreshes stale metadata before it will answer a `packages`
    # query. With the system step deselected that fetch would happen inside the
    # capture below, losing both of ONEUP-0048's defences at once: its output
    # goes to a variable instead of the log pane, and it runs outside the
    # per-source budget, so a crawling mirror hangs the run showing nothing.
    if not repos.REPOS_REFRESHED:
        repos.refresh_repos(import_keys=opts.import_keys)
    if proc.stop_pending():
        # refresh_repos returns between sources on a stop, and nothing has been
        # removed yet — the same free boundary the system step stops at.
        end_step("orphans", "skip", "stopped before removing anything")
        return
    # --no-refresh on both queries: the refresh above is the only one allowed,
    # because it is the only one the user can see and the run can escape from.
    # The status is checked, not discarded: a query that failed returns no rows,
    # which is byte-identical to a clean machine, so an unchecked call reports
    # "nothing to remove" for a step that never managed to look.
    rc, raw = privilege.sudo(
        ["zypper", "--non-interactive", "--no-refresh", "packages", "--unneeded"])
    if rc != 0:
        markers.out(f"Couldn't list leftover dependency packages (zypper exit {rc}).")
        end_step("orphans", "fail", "couldn't list leftover packages")
        return
    unneeded = _package_column(raw)
    if unneeded is None:
        end_step("orphans", "fail", "unreadable package name in zypper's output")
        return
    if unneeded:
        markers.out(f"Removing {len(unneeded)} leftover dependency package(s):")
        for name in unneeded:
            markers.out(f"  - {name}")
        rc, _ = privilege.sudo(
            ["zypper", "--non-interactive", "remove", "--clean-deps", *unneeded],
            stream=True)
        if rc == 0:
            end_step("orphans", "ok", f"removed {len(unneeded)} package(s)")
        else:
            end_step("orphans", "fail", "removal failed")
    else:
        markers.out("No leftover dependency packages to remove.")
        end_step("orphans", "ok", "nothing to remove")
    _, raw = privilege.sudo(
        ["zypper", "--non-interactive", "--no-refresh", "packages", "--orphaned"])
    # Report-only, and nothing here reaches a privileged argv — so an unreadable
    # name is not fatal for this half; it just means the count cannot be stated.
    orphaned = len(_package_column(raw) or [])
    if orphaned > 0:
        markers.out("")
        markers.out(f"Note: {orphaned} package(s) have no active repository (possibly")
        markers.out("installed by hand). Left in place — review with:  zypper packages --orphaned")


def run_cache() -> None:
    """Clear the downloaded-package cache — unless the system step failed.

    A failed system step almost always failed part-way through the DOWNLOAD, so
    the cache holds most of what the retry needs; clearing it turns one flaky
    mirror into a full re-download (ONEUP-0087).

    Deliberately NOT `clean --all`, which also wipes the repository METADATA
    cache: the rootless `--check` reads that metadata and cannot rebuild it, so
    wiping it made the next check answer "up to date" whatever was waiting
    (ONEUP-0056).
    """
    begin_step("cache")
    if RESULT.get("system") == "fail":
        note = ("Kept the already-downloaded packages, so retrying the update doesn't "
                "fetch them all over again.")
        markers.out(f"  {note}")
        markers.hint(note)
        end_step("cache", "skip", "kept the downloads for a retry")
        return
    before = _cache_bytes()
    if privilege.sudo(["zypper", "--non-interactive", "clean"], stream=True)[0] != 0:
        end_step("cache", "fail", "clean failed")
        return
    end_step("cache", "ok")
    after = _cache_bytes()
    # Only report a genuine reclamation, so the window never shows "Reclaimed 0B".
    if before is None or after is None or before <= after:
        return
    freed = human_bytes(before - after)
    markers.out(f"  Reclaimed {freed} from the package cache.")
    markers.marker("FREED", f"cache|{freed}")


def _cache_bytes() -> int | None:
    """`du -sB1 /var/cache/zypp`'s figure, or None when it could not be read."""
    if privilege.CACHE_DU_ARGV is None:
        return None
    _, out = privilege.sudo(privilege.CACHE_DU_ARGV)
    first = out.split(maxsplit=1)
    if not first or not first[0].isdigit():
        return None
    return int(first[0])


def human_bytes(count: int) -> str:
    """`numfmt --to=iec`, with the Bash's own fallback to a bare byte figure."""
    rc, out = proc.run(["numfmt", "--to=iec", str(count)])
    if rc == 0 and out.strip():
        return out.strip()
    return f"{count}B"


def _have(binary: str) -> bool:
    """`command -v`: is this tool on PATH? A missing one is a skip, never a fail."""
    return shutil.which(binary) is not None


def system_txn_argv() -> list[str]:
    """The system transaction's argv, without `--dry-run`.

    BOTH arms take `--reposd-dir`, or download recovery would be a no-op on Leap
    while working on Tumbleweed — a retry byte-identical to the attempt that just
    failed (ONEUP-0094 §4.3).
    """
    reposd = ["--reposd-dir", REPOSD_OVERRIDE] if REPOSD_OVERRIDE else []
    if _is_leap():
        return ["zypper", "--non-interactive", *reposd, "update"]
    # Tumbleweed: --allow-vendor-change lets Packman codec packages update
    # cleanly; without it the upgrade stalls on vendor conflicts.
    return ["zypper", "--non-interactive", *reposd, "dup", "--allow-vendor-change"]


def _is_leap() -> bool:
    """Same test as the Bash: `grep -q Leap /etc/os-release`, absent file = no."""
    try:
        return "Leap" in Path("/etc/os-release").read_text(errors="replace")
    except OSError:
        return False


# How often the download pass's root-side wrapper looks for a stop request.
STOP_POLL_SECONDS = os.environ.get("ONEUP_STOP_POLL_SECONDS") or "2"
# More than this failing at once is systemic — a network or system problem, not
# one bad source — so we do not silently set them all aside.
MAX_SKIP_REPOS = 2

# The user stopped during or just after the download: the third safe boundary.
SYS_STOPPED = False
# The download pass's status. 143 (128+SIGTERM) is the wrapper reporting a stop,
# which is what tells "stopped" from "failed".
SYS_DL_RC = 0
# Recovery was ATTEMPTED, and separately whether its download pass then failed.
# The failure hint keys on the second: the first is still true when the retry
# SUCCEEDED and the commit failed, where "nothing was installed" would be a lie.
DL_RECOVERY_TRIED = False
DL_RETRY_FAILED = False

_SYS_LOG: Path | None = None
_SYS_LOG_FIRST: Path | None = None
_CDN_REPOSD_DIR = ""

# The unprivileged engine cannot signal a root child (`security.md` §2.2), so a
# root-side wrapper owns zypper and signals its OWN child. This is the inline
# route, used when no ONEUP-0023 guard is installed; the guard route runs the
# installed file instead. The two texts differ — the guard pins its own
# interpreter and zypper, and shifts 4 where this shifts 3 — so never feed one
# into the other's call.
_STOP_WRAPPER = '''
stop_file="$1"; run_state="$2"; poll="$3"; shift 3
"$@" --download-only &
z=$!
while kill -0 "$z" 2>/dev/null; do
    # Same staleness rule as stop_pending: a request older than run.state is a
    # leftover. Re-implemented because a shell function cannot cross sudo.
    if [[ -e "$stop_file" && -e "$run_state" && "$stop_file" -nt "$run_state" ]]; then
        kill -TERM "$z" 2>/dev/null
        break
    fi
    sleep "$poll"
done
wait "$z"        # never exit without reaping — an unreaped root child is the
exit $?          # ONEUP-0041 orphan shape, one level down
'''


def _zypper_ok(rc: int) -> bool:
    """zypper's INFORMATIONAL exits are not failures.

    100-103 say an update, reboot or restart is advised; 106 says a repository was
    skipped. `run_size` and `check` each already exempt their own subset; the
    transaction passes exempted none, so a `dup` that installed cleanly and exited
    102 reported as a failed step, suppressed the reboot advice for packages that
    really landed, and made the cache step hoard the downloads for a retry nobody
    needed.
    """
    return rc == 0 or 100 <= rc <= 103 or rc == 106


def _download_pass() -> bool:
    """Pass 1 of 2: fetch every package, install nothing.

    The one phase of a run that can be interrupted for free, which is why the
    stop the user asked for lands DURING it rather than after (ONEUP-0085).

    Two routes, one contract (ONEUP-0092 §4.5). Where the grant installed a
    guard this engine recognises, run THAT: `env LC_ALL=C bash -c *` is the one
    shape a sudoers rule cannot grant without handing over a root shell, so a
    passwordless run would otherwise meet a password dialog right here.
    """
    global SYS_DL_RC
    from . import actions  # deferred: actions imports this module
    txn = system_txn_argv()
    privilege.install_environment()
    stop_file, run_state = str(runstate.STOP_REQUEST), str(runstate.RUN_STATE)
    if actions.guard_current():
        argv = ["sudo", str(actions.GUARD_FILE), stop_file, run_state,
                STOP_POLL_SECONDS, *txn]
    else:
        # LC_ALL=C reaches the child as an ARGV PREFIX through `sudo env`, never
        # as a Python `env=` argument: sudo resets the environment, and the
        # sudoers rule grants those literal words.
        argv = ["sudo", "env", "LC_ALL=C", "bash", "-c", _STOP_WRAPPER, "_",
                stop_file, run_state, STOP_POLL_SECONDS, *txn]
    SYS_DL_RC = proc.stream_filtered(argv, step="system", phase="download",
                                     log=_SYS_LOG, append=False)
    # 143 is the wrapper reporting a stop. Nothing is installed either way, so it
    # is not a failure — and it must not read as one, or the caller admits the
    # step to the repo-scoped probe and re-runs the transaction just stopped.
    # 143 is 128+SIGTERM: the user stopped it. Nothing is installed either way, so
    # it is not a failure — and it must not read as one, or the caller admits the
    # step to the repo-scoped probe and re-runs the transaction just stopped.
    return _zypper_ok(SYS_DL_RC) or SYS_DL_RC == 143


def _commit_pass() -> bool:
    """Pass 2 of 2: the rpm transaction, and nothing else.

    Every package is already cached, so this performs no network I/O — which is
    exactly why it is NEVER signalled (`security.md` §6.1). It APPENDS to the
    transaction log, because the download pass's output is where a download
    failure's evidence lives.
    """
    privilege.install_environment()
    argv = ["sudo", "env", "LC_ALL=C", *system_txn_argv()]
    return _zypper_ok(proc.stream_filtered(argv, step="system", phase="install",
                                           log=_SYS_LOG, append=True))


_TRANSFER_FAILURE = re.compile(
    r"bytes missing|returned error: 404|Download.*failed|Curl error|connection failed",
    re.IGNORECASE)
_NOT_TRANSFER = re.compile(
    r"No space left|disk full|conflict|nothing provides|not installable|signature|GPG",
    re.IGNORECASE)


def _log_text() -> str:
    try:
        return _SYS_LOG.read_text(errors="replace")
    except OSError:
        return ""


def _system_upgrade() -> bool:
    """The transaction, with download recovery. Clears the repos.d override on every exit.

    The clearing is why this wrapper exists: the caller's repo-skip path can run
    the transaction a third time after disabling a repository, and `disable_repo`
    edits the REAL directory — so an attempt still reading the redirected copy
    would not see the repository just disabled (ONEUP-0094 §4.1).
    """
    global REPOSD_OVERRIDE
    try:
        return _system_upgrade_inner()
    finally:
        REPOSD_OVERRIDE = ""


def _system_upgrade_inner() -> bool:
    global SYS_STOPPED, SYS_DL_RC, DL_RECOVERY_TRIED, DL_RETRY_FAILED
    global REPOSD_OVERRIDE, _SYS_LOG_FIRST, _CDN_REPOSD_DIR
    SYS_DL_RC = 0
    ok = _download_pass()
    if not ok:
        # ONEUP-0094: openSUSE's mirror routing can send one package to a host
        # that will not serve it, and one unfetchable file discards the whole
        # transaction. Retry the DOWNLOAD pass once against the content CDN,
        # which answers directly instead of selecting a mirror. Runs BEFORE the
        # caller's repo-scoped probe: that probe's remedy is to disable a
        # repository, and a transfer failure is the one case where doing so
        # throws away a working source.
        log = _log_text()
        if (not DL_RECOVERY_TRIED and not proc.stop_pending()
                and _TRANSFER_FAILURE.search(log) and not _NOT_TRANSFER.search(log)
                and repos.redirectable()):
            cdn_dir = repos.make_cdn_reposd()
            if cdn_dir:
                _CDN_REPOSD_DIR = cdn_dir      # outlives REPOSD_OVERRIDE, for the cleanup
                DL_RECOVERY_TRIED = True
                # The retry TRUNCATES the transaction log, and the failure hint
                # below names its package from this snapshot of the first attempt.
                handle, first = tempfile.mkstemp(prefix="oneup-sys-")
                os.close(handle)
                _SYS_LOG_FIRST = Path(first)
                with contextlib.suppress(OSError):
                    _SYS_LOG_FIRST.write_text(log)
                REPOSD_OVERRIDE = cdn_dir
                markers.out("  Recovery: retrying downloads via "
                            "downloadcontentcdn.opensuse.org "
                            f"(repositories copied to {cdn_dir})")
                SYS_DL_RC = 0
                ok = _download_pass()
                if not ok:
                    DL_RETRY_FAILED = True
        if not ok:
            return False                 # a real download failure — the caller reports it
    if SYS_DL_RC == 143 or proc.stop_pending():
        SYS_STOPPED = True               # the third safe boundary (ONEUP-0085 §4.2)
        return True
    return _commit_pass()


_UPGRADE_COUNT = re.compile(r"([0-9]+) packages? to upgrade", re.IGNORECASE)
_INSTALL_COUNT = re.compile(r"([0-9]+) to install", re.IGNORECASE)
_FAILED_PKG = re.compile(r"^(?:Preloading|Retrieving): (\S+) \[([^]]*)\]", re.MULTILINE)
_CACHED = re.compile(r"^(done|already in cache)$", re.IGNORECASE)


def _last_count(pattern: re.Pattern[str], text: str) -> int:
    """The LAST occurrence's figure, as zypper prints its plan more than once."""
    found = pattern.findall(text)
    return int(found[-1]) if found else 0


def _failed_package() -> str:
    """The package the first download attempt could not fetch, or "".

    A bracketed clause that is neither "done" nor "already in cache" is the
    failure; anything else and the clause is dropped rather than printed empty.
    """
    if _SYS_LOG_FIRST is None:
        return ""
    try:
        text = _SYS_LOG_FIRST.read_text(errors="replace")
    except OSError:
        return ""
    for name, state in _FAILED_PKG.findall(text):
        if not _CACHED.match(state.strip()):
            return name
    return ""


def _discard_logs() -> None:
    """Drop this step's temporary files, including the throwaway repos.d copy."""
    global _CDN_REPOSD_DIR
    for path in (_SYS_LOG, _SYS_LOG_FIRST):
        if path is not None:
            with contextlib.suppress(OSError):
                path.unlink()
    if _CDN_REPOSD_DIR:
        shutil.rmtree(_CDN_REPOSD_DIR, ignore_errors=True)
        _CDN_REPOSD_DIR = ""


def _note(text: str) -> None:
    """Say the same thing to the terminal and to the window."""
    markers.out(f"  Note: {text}")
    markers.hint(text)


def _success(refresh_ok: bool) -> None:
    """Interpret a transaction that SUCCEEDED, and only then."""
    global SYS_CHANGED, SYS_COUNT, SYS_REBOOT_DETAIL
    log = _log_text()
    if not refresh_ok:
        # The upgrade worked, but off possibly-stale metadata — say so, or a
        # genuinely newer package is silently missed until the next run.
        _note("Couldn't refresh one or more repositories — upgraded from cached "
              "metadata. A future run should refresh cleanly.")
    if "Nothing to do." in log:
        SYS_COUNT = "0"
        end_step("system", "ok", "already up to date")
    else:
        SYS_CHANGED = True
        if proc.PROGRESS_SEEN == 0:
            # ONEUP-0046's canary. A transaction that installed packages while no
            # progress line was recognised is the signature of zypper having
            # renamed the lines we read — and silence is how the "download size:
            # 0 B" bug hid for weeks. Say so rather than quietly showing nothing.
            markers.hint(
                "Packages were installed, but OneUp couldn't follow the progress — zypper "
                "has probably renamed the lines it reports progress on. The update itself "
                "was fine; please report this so the progress display can be updated.")
            markers.out("  Note: no progress lines recognised in zypper's output "
                        "(see @@HINT@@ above).")
        count = _last_count(_UPGRADE_COUNT, log) + _last_count(_INSTALL_COUNT, log)
        SYS_COUNT = str(count)
        # Read the reboot-reason names now, while the transaction log still
        # exists — it is discarded at the end of this step, long before the
        # reboot check runs.
        SYS_REBOOT_DETAIL = parsers.reboot_reason(log)
        end_step("system", "ok",
                 f"{count} package(s) updated" if count > 0 else "packages updated")
    if repos.DISABLED:
        _note(f"Updated everything except: {' '.join(repos.DISABLED)} — set aside this "
              "run (temporary problem); OneUp will retry next time.")
    if DL_RECOVERY_TRIED and not DL_RETRY_FAILED:
        # This one reports a run that already succeeded, so unlike the failure
        # hints it has nothing for the user to do.
        _note("Recovered from a failed download — some packages were fetched from "
              "openSUSE's content delivery network instead of the mirror that failed.")


def _failure(systemic: bool, import_keys: bool) -> None:
    """Turn the most common zypper failures into one plain-English line."""
    log = _log_text()
    hint = ""
    if systemic:
        hint = ("Several repositories are failing at once — likely a network or system "
                "problem, not a single bad source. Check your connection and retry.")
    elif DL_RETRY_FAILED and _TRANSFER_FAILURE.search(log):
        # Guarded on the RETRY having failed, not merely on recovery having been
        # tried: the latter is still true when the retry succeeded and the commit
        # then failed. The log is re-tested so a retry that died of a full disk
        # still reaches the disk-full arm below.
        named = _failed_package()
        hint = (f"Could not download {named} — " if named else
                "A package could not be downloaded — ")
        hint += ("openSUSE's servers are still catching up with this update. Nothing was "
                 "installed and everything already downloaded has been kept; try again "
                 "later.")
    elif re.search(r"No space left|disk full", log, re.IGNORECASE):
        hint = ("Ran out of disk space — free some room (clear the package cache, delete "
                "old snapshots) and retry.")
    elif re.search(r"signature|GPG|key.*(expired|reject)", log, re.IGNORECASE):
        if import_keys:
            # Keys were already imported this run and it STILL failed, so
            # importing will not help: do not offer the one-click remedy again.
            hint = ("A repository signing key is still rejected even after importing keys "
                    "— check the log for the offending repository, or run: sudo zypper "
                    "--gpg-auto-import-keys refresh, then retry.")
        else:
            markers.marker("REMEDY", "import-keys")
            hint = ('A repository signing key is out of date. Use "Import signing key & '
                    'retry" to fix it, or run: sudo zypper --gpg-auto-import-keys refresh, '
                    "then retry.")
    elif re.search(r"Timeout|could not resolve|connection failed|Curl error"
                   r"|Download.*failed|Temporary failure", log, re.IGNORECASE):
        hint = "A download failed — check your internet connection, then retry."
    elif re.search(r"conflict|nothing provides|not installable", log, re.IGNORECASE):
        hint = ("A package conflict — often a third-party repo. Check the log; you may "
                "need to disable a conflicting repository.")
    if hint:
        markers.out(f"  Hint: {hint}")
        markers.hint(hint)
    end_step("system", "fail", "zypper reported an error")


def run_system(opts) -> None:
    """The system transaction, with its refresh, its stops and its repo resilience.

    The transaction — NOT the refresh — decides whether the step succeeded. A
    refresh can fail transiently while zypper still upgrades cleanly from cached
    metadata; failing the step then would deny a working update and drop the
    reboot advice for changes that really landed.
    """
    global _SYS_LOG
    begin_step("system")
    # An interactive "Skip & update the rest" re-run: set the named sources aside
    # up front, before anything reads them.
    for alias in opts.skip_repos:
        if alias:
            repos.disable_repo(alias, "manual")
    repos.REFRESH_FAILED = False
    # One repository at a time, each with its own budget, so a crawling mirror
    # cannot hang the run and the window can name the source it is waiting on.
    repos.refresh_repos(import_keys=opts.import_keys)
    refresh_ok = not repos.REFRESH_FAILED
    # Second safe boundary: the refresh can take a minute on a slow mirror.
    # Nothing has been installed yet, which is exactly why stopping here is free.
    if proc.stop_pending():
        end_step("system", "skip", "stopped before installing anything")
        return
    handle, path = tempfile.mkstemp(prefix="oneup-sys-")
    os.close(handle)
    _SYS_LOG = Path(path)
    try:
        ok = _system_upgrade()
        if SYS_STOPPED:
            # Returns BEFORE the repo-scoped probe below, which would otherwise
            # re-run the whole transaction the user just stopped.
            end_step("system", "skip", "stopped before installing anything")
            return
        systemic = False
        # Only probe when we were not already told which sources to skip — a
        # --skip-repo run already named them, so probing again would mask a
        # genuinely different error — and when the failure really looks
        # repo-scoped (disk-full and conflicts are not).
        if not ok and not opts.skip_repos and repos.repo_scoped_failure(_SYS_LOG):
            failing = repos.find_failing_repos()
            if len(failing) > MAX_SKIP_REPOS:
                systemic = True                    # too many at once: not one bad source
            elif failing:
                if opts.auto_skip:
                    for entry in failing:
                        alias, _, reason = entry.partition(" ")
                        repos.disable_repo(alias, reason)
                    # Retry on the healthy repositories only if we actually
                    # disabled something: a disable that itself failed must not
                    # silently retry.
                    if repos.DISABLED:
                        ok = _system_upgrade()
                        # The retry can itself be stopped, and the boundary check
                        # that guards the FIRST transaction sits above this probe
                        # rather than below it — so without this a stop during the
                        # retry falls through and reports the solver's package
                        # count as an install that never happened (INV-1).
                        if SYS_STOPPED:
                            end_step("system", "skip",
                                     "stopped before installing anything")
                            return
                else:
                    # Interactive: ask, do not act. Offer the skip for each
                    # culprit; disable nothing on our own.
                    for entry in failing:
                        markers.marker("REMEDY", f"skip-repo|{entry.partition(' ')[0]}")
        if ok:
            _success(refresh_ok)
        else:
            _failure(systemic, opts.import_keys)
    finally:
        _discard_logs()
