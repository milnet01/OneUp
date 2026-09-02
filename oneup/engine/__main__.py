"""Parse the command line and dispatch one run.

The flag surface is frozen (`docs/design/oneup-2.0.md` §3): every flag
`update_system.sh` accepts, with the same spelling and the same behaviour.

`run` below reproduces the Bash engine's straight-line order, and the ORDER is
the deliverable rather than the pieces: four points in it are load-bearing and
the suite can only see them indirectly. They are named on `run` itself.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import actions, markers, privilege, proc, repos, runstate, steps

ALL_STEPS = "system,flatpak,firmware,orphans,cache"

# Exit codes. 0 and 1 are ordinary; 2 is an unknown flag or an empty step selection;
# `privilege.install_exit_handlers` owns 130 and 143 (SIGINT, SIGTERM/SIGHUP).
# `docs/specs/ONEUP-0054-python-engine.md` §4.1.2 pins them, and scopes the fourth — 141 —
# to a `tee` without `-p`. v2 has no `tee`, so the construct that code is read from does
# not exist here and it is deliberately not reproduced; `runstate.py`'s mirror owns what
# replaces it.
EXIT_UNKNOWN_FLAG = 2


@dataclass
class Options:
    """Everything the command line said, whether or not this stage acts on it."""

    steps: str = ALL_STEPS
    log_file: str | None = None
    check_only: bool = False
    size_step: str = ""
    hold: bool = False
    auth_action: str = ""
    import_keys: bool = False
    skip_repos: list[str] = field(default_factory=list)
    auto_skip: bool = False
    thin_snapshots: bool = False
    notify: bool = False

    def selected(self, key: str) -> bool:
        """`step_selected`: is this step in `--steps=`?"""
        return f",{key}," in f",{self.steps},"


def usage() -> str:
    """The help text, matching `update_system.sh`'s `usage`.

    Plain concatenation rather than an f-string: ruff's bandit rules read a long
    interpolated literal as a possible SQL query (S608), and a suppression here
    would be silencing a rule rather than answering it.
    """
    # The repository-skip cap is interpolated rather than written out, as the Bash
    # interpolates $MAX_SKIP_REPOS. Hard-coded here, the sentence had already lost
    # the number while the behaviour kept it — gate G2 caught that (stage 6).
    return (_USAGE_HEAD.replace("{MAX_SKIP}", str(steps.MAX_SKIP_REPOS))
            + str(runstate.USER_LOG_DIR) + _USAGE_TAIL)


_USAGE_HEAD = """System Updater engine

Usage: oneup-engine [--steps=LIST] [--check] [--notify] [--log=FILE] [--help]

  --steps=LIST   Comma-separated steps to run. Default: all.
                 Available: system, flatpak, firmware, orphans, cache
  --check        Read-only: report how many updates are available and exit.
                 Runs WITHOUT root, so it is safe for an unattended timer.
  --notify       Raise a desktop notification: with --check when updates exist,
                 and at the end of a full run with the outcome.
  --grant-auth   Opt in to passwordless updates: install a scoped sudoers rule
                 so OneUp's update commands run without a password (stores no
                 password). Asks for your password once to set it up.
  --revoke-auth  Remove that rule — updates prompt for a password again.
  --auth-status  Print whether the passwordless rule is active (@@AUTH@@|on/off).
  --import-keys  Refresh with --gpg-auto-import-keys so a rotated/expired repo
                 signing key is imported for the system upgrade (opt-in per run).
  --skip-repo=ALIAS  Exclude this source from the run: disable it, upgrade the
                 rest, re-enable it. Repeatable.
  --auto-skip-repos  Unattended mode: on a repo-scoped failure, auto-detect and
                 skip the culprit(s) (up to {MAX_SKIP}), then continue.
  --thin-snapshots  Ask snapper to remove old, expendable Btrfs snapshots (its own
                 retention cleanup — keeps the recent ones), then report how many.
  --log=FILE     Write the run log here. Default: """

_USAGE_TAIL = """/<timestamp>.log
  --help         Show this help.

Examples:
  oneup-engine                       # update everything
  oneup-engine --steps=system,cache  # only system packages + cache clean
  oneup-engine --check --notify      # background "updates available?" check"""


def parse(argv: list[str]) -> tuple[Options | None, int]:
    """Parse `argv`. Returns (options, exit-code); options is None when we should exit."""
    opts = Options()
    for arg in argv:
        if arg.startswith("--steps="):
            opts.steps = arg.split("=", 1)[1]
        elif arg.startswith("--log="):
            opts.log_file = arg.split("=", 1)[1]
        elif arg == "--check":
            opts.check_only = True
        # A bare `--size=` falls to the unknown-option arm below: its empty value
        # read as false at the dispatch and ran a FULL upgrade (ONEUP-0173).
        elif arg.startswith("--size=") and arg != "--size=":
            opts.size_step = arg.split("=", 1)[1]
        elif arg == "--hold":
            opts.hold = True
        elif arg == "--grant-auth":
            opts.auth_action = "grant"
        elif arg == "--revoke-auth":
            opts.auth_action = "revoke"
        elif arg == "--auth-status":
            opts.auth_action = "status"
        elif arg == "--emit-guard":
            opts.auth_action = "emit-guard"
        elif arg == "--import-keys":
            opts.import_keys = True
        elif arg.startswith("--skip-repo="):
            opts.skip_repos.append(arg.split("=", 1)[1])
        elif arg == "--auto-skip-repos":
            opts.auto_skip = True
        elif arg == "--thin-snapshots":
            opts.thin_snapshots = True
        elif arg == "--notify":
            opts.notify = True
        elif arg in ("--help", "-h"):
            markers.out(usage())
            return None, 0
        else:
            markers.err(f"Unknown option: {arg}")
            markers.err(usage())
            return None, EXIT_UNKNOWN_FLAG
    return opts, 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    opts, code = parse(args)
    if opts is None:
        return code

    # Before the log mirror, or the re-exec'd process installs a second one.
    _reexec_under_inhibitor(opts, args)

    # Mirror the whole run to its log, for EVERY mode. The Bash installs its
    # `tee` above every dispatch, so `--check`, `--size`, `--thin-snapshots` and
    # the auth actions are all logged. Installed after the parse guard above, so
    # `--help` and an unknown flag still write nothing — the Bash's own order.
    log_file = runstate.resolve_log_path(opts.log_file)
    runstate.install_log_mirror(log_file)

    # The selection and its rejection sit ABOVE every dispatch, exactly where the
    # Bash puts them: a `--steps=sytem` typo must be refused whatever mode was
    # asked for, and "ran nothing, all clear" is the one answer an update checker
    # must never give. Inside the run driver it would reach `--check` as
    # `@@CHECK@@|TOTAL|0` and exit 0.
    run_keys = [key for key in steps.LABEL if opts.selected(key)]
    if not run_keys:
        markers.err(f'No valid update steps selected (got --steps="{opts.steps}").')
        markers.err(f"Valid steps: {ALL_STEPS}")
        return EXIT_UNKNOWN_FLAG
    steps.TOTAL = len(run_keys)

    privilege.install_exit_handlers()

    if opts.auth_action == "status":
        return actions.auth_status()
    if opts.auth_action == "emit-guard":
        return actions.emit_guard()
    if opts.auth_action == "grant":
        return actions.grant_auth()
    if opts.auth_action == "revoke":
        return actions.revoke_auth()
    if opts.thin_snapshots:
        return actions.thin_snapshots()
    if opts.check_only:
        return actions.check(opts)

    held_auth = False
    if opts.size_step:
        actions.HOLDING = opts.hold
        size_rc = actions.run_size(opts.size_step)
        if not (opts.hold and size_rc == 0):
            return size_rc
        # A go-ahead falls THROUGH into the run below, reusing the credential
        # this process already cached — which is the whole fix. The other three
        # arms end the process, and end it with status 0: Cancel, the ceiling
        # and a departed window are not failures, because the job this process
        # was started for — quoting the size — succeeded and was already
        # reported. So is a go-ahead the membership check REFUSES; what that arm
        # must not do is fall through, because the selection has not been
        # re-derived and start-up's default is all five steps, so a tampered
        # go.request would become a full system upgrade.
        adopted = _adopt_go_ahead(opts, runstate.hold_for_go_ahead(
            log_file, actions.HOLD_SIZE, _WINDOW_PID, _poll_seconds()))
        if adopted is None:
            markers.marker("DONE", "ok")      # withheld by size_delivered, emitted here
            return 0
        run_keys = adopted
        held_auth = True

    return run(opts, run_keys, log_file, held_auth)


# Captured once, at start-up. Re-reading a parent id later can never fire: it is
# not refreshed on reparenting, and systemd reparents a user session's orphans to
# `systemd --user` rather than to pid 1 (`CLAUDE.md` §6).
_WINDOW_PID = os.getppid()


def _poll_seconds() -> float:
    """How often the hold looks for an answer — the stop poll's own interval."""
    try:
        return float(steps.STOP_POLL_SECONDS)
    except ValueError:
        return 2.0


def _adopt_go_ahead(opts: Options, asked: str | None) -> list[str] | None:
    """Adopt a go-ahead's step list, or refuse the whole thing.

    Deliberately STRICTER than `--steps=`, and reusing that path would be a
    security defect: `--steps=` drops an unknown key silently and only refuses
    when every key is unknown, so `cache,../../evil` would run the cache step and
    report success. `--steps=` is a flag a person types; a `go.request` is an
    authorisation read by a root process (ONEUP-0044 §4.6, INV-8).

    Membership of the label map is the check, never a shape test on the
    characters: a shape check passes anything well-formed, where membership of a
    closed vocabulary is the property actually wanted.

    The whole selection is re-derived. Setting `opts.steps` alone looks right and
    runs all five, because the run path iterates the derived keys and
    `request_size` passes no `--steps=` — INV-6 catches it.
    """
    if not asked:
        return None
    if any(key not in steps.LABEL for key in asked.split(",")):
        return None
    opts.steps = asked
    run_keys = [key for key in steps.LABEL if opts.selected(key)]
    if not run_keys:
        return None
    steps.TOTAL = len(run_keys)
    steps.STEP_INDEX = 0
    return run_keys


def _reexec_under_inhibitor(opts: Options, argv: list[str]) -> None:
    """Hold a shutdown inhibitor for the whole run, by re-exec (ONEUP-0086).

    zypper runs as ROOT inside the user's session cgroup and `systemd --user`
    may not kill root processes, so a logout or reboot asked for mid-run waits
    on something it can never stop: a black screen that never reboots, until
    the user holds the power button — the worst possible moment to cut power to
    an rpm transaction. A block-mode inhibitor turns that silent hang into a
    visible prompt naming OneUp, which the user can still override.

    Re-exec rather than a background lock-holder, so the lock lives exactly as
    long as this process and nothing is left behind if we are `SIGKILL`ed
    (`docs/standards/security.md` §2.4).

    Probed, never assumed: `systemd-inhibit` exits WITHOUT running its command
    when it cannot take the lock (no logind, a container, a locked-down
    session), so a missing or non-working tool must degrade to "no inhibitor",
    never to "no run".

    Re-exec as `sys.executable -m oneup.engine`, not `sys.argv[0]`: the Bash's
    `"$0"` is a runnable script and ours is `.../oneup/engine/__main__.py`,
    which cannot be re-run directly because its relative imports break.
    """
    if os.environ.get("ONEUP_INHIBITED"):
        return
    if opts.auth_action or opts.check_only:
        return
    # `--size` alone is a read-only price quote and needs no lock. `--size --hold`
    # is NOT that: it falls through into the full transaction (ONEUP-0044 §4.5) and
    # is the GUI's ordinary Update path, so it is inhibited like any other run.
    if opts.size_step and not opts.hold:
        return
    probe = ["systemd-inhibit", "--what=shutdown", "--who=OneUp", "--why=probe", "true"]
    try:
        if not proc.succeeds(probe):
            return
    except OSError:
        return                                    # not installed at all
    os.environ["ONEUP_INHIBITED"] = "1"
    with contextlib.suppress(OSError):
        # S607: a bare name, on purpose — the probe two lines up ran the same
        # name through PATH, so resolving it here would answer a different question.
        os.execvp("systemd-inhibit", [  # noqa: S606,S607 — fixed argv, probed above
            "systemd-inhibit", "--what=shutdown:sleep", "--mode=block", "--who=OneUp",
            "--why=Installing updates — interrupting now can leave packages "
            "half-installed",
            sys.executable, "-m", "oneup.engine", *argv,
        ])


def _pre_update_snapshot() -> None:
    """Record a rollback point, and enumerate recent ones for the picker.

    Read-only apart from the labelled `snapper create`: Tumbleweed already
    auto-snapshots around zypper, but a named entry is unambiguous. The
    description is built FIRST — a nested substitution inside the capture would
    fork a subshell in the Bash and cost a second password prompt, and keeping
    the same shape keeps the two engines' privileged call sequence identical.
    """
    if not shutil.which("snapper"):
        return
    desc = "OneUp pre-update " + time.strftime("%Y-%m-%d %H:%M")
    _, snap_id = privilege.sudo(["snapper", "create", "--description", desc,
                                 "--cleanup-algorithm", "number", "--print-number"])
    snap_id = snap_id.strip()
    if not snap_id:
        _, listing = privilege.sudo(["snapper", "--no-headers", "list"])
        tail = listing.splitlines()
        snap_id = tail[-1].split()[0] if tail and tail[-1].split() else ""
    if snap_id:
        markers.out(f"Pre-update snapshot #{snap_id} recorded  "
                    f"(roll back with: sudo snapper rollback {snap_id})")
        markers.marker("SNAPSHOT", snap_id)
    # ONEUP-0020: the newest restore points, for the GUI's rollback picker. Only
    # the id is trusted downstream; the date and description are display-only.
    # Snapshot 0 is the live "current" pseudo-entry and is not a rollback target.
    _, csv = privilege.sudo(["snapper", "--machine-readable", "csv", "list",
                             "--columns", "number,date,description"])
    rows = []
    for line in csv.splitlines()[1:]:
        fields = line.split(",")
        if len(fields) < 3 or not fields[0].isdigit() or fields[0] == "0" or not fields[1]:
            continue
        desc = line.split(",", 2)[2]
        if desc.startswith('"'):
            desc = desc[1:]
        if desc.endswith('"'):
            desc = desc[:-1]
        rows.append(f"{fields[0]}|{fields[1]}|{desc.replace('|', '/')}")
    for row in rows[-12:]:
        markers.marker("SNAPSHOT_ITEM", row)


_LOW_DISK = 2 * 1024 * 1024 * 1024        # recommend at least 2 GiB free
SNAP_WARN_COUNT = 25                      # warn once this many snapshots have piled up


def _preflight() -> None:
    """Read-only warnings BEFORE anything changes: disk, snapshots, repositories."""
    for mount in ("/", "/var"):
        rc, out = proc.run(["df", "-PB1", mount])
        rows = out.splitlines()
        if rc != 0 or len(rows) < 2:
            continue
        fields = rows[1].split()
        if len(fields) < 4 or not fields[3].isdigit():
            continue
        avail = int(fields[3])
        if avail >= _LOW_DISK:
            continue
        human = steps.human_bytes(avail)
        markers.out(f"  ! Low disk space on {mount}: only {human} free "
                    f"(recommend at least 2 GiB).")
        markers.marker("DISK", f"warn|{mount}|{human}")
    # Btrfs snapshots accumulate around every zypper transaction and can quietly
    # fill the root filesystem. Count is the honest signal: Btrfs shares extents
    # copy-on-write, so a byte figure would overcount.
    if shutil.which("snapper"):
        _, listing = privilege.sudo(["snapper", "--no-headers", "list"])
        count = len([ln for ln in listing.splitlines() if ln.strip()])
        if count >= SNAP_WARN_COUNT:
            markers.out(f"  ! {count} system restore points (snapshots) stored — these build up")
            markers.out("    with each update and can use a lot of disk space; "
                        "consider thinning them.")
            markers.marker("SNAPSHOTS", f"warn|{count}")
    # Duplicate repository URLs are a frequent source of update conflicts.
    _, listing = proc.run(["zypper", "--non-interactive", "lr", "-u"])
    seen: dict[str, int] = {}
    for line in listing.splitlines():
        fields = line.split("|")
        if len(fields) < 6:
            continue
        url = fields[-1].replace(" ", "")
        if url and url != "URI":
            seen[url] = seen.get(url, 0) + 1
    dupes = [u for u, n in seen.items() if n > 1]
    if dupes:
        markers.out("  ! Duplicate repository URL(s) detected — a common cause of conflicts:")
        for url in dupes:
            markers.out(f"      {url}")
        # URLs never contain spaces, so a space-join survives the single marker line.
        markers.marker("REPO", f"warn|duplicate|{' '.join(dupes)}")


# Restarting one of these ends the user's graphical session, so a reboot is the
# honest advice (ONEUP-0111). Kept in step with the window's own list by a test.
_SESSION_CRITICAL = re.compile(
    r"^(display-manager|sddm|gdm|gdm3|lightdm|xdm|kdm|lxdm|greetd|dbus|dbus-broker"
    r"|systemd-logind|polkit|polkitd|user@[0-9]+)$")


def _display_manager_unit() -> str:
    """The unit `display-manager.service` points at, without its suffix."""
    try:
        target = os.path.realpath("/etc/systemd/system/display-manager.service")
    except OSError:
        return ""
    base = target.rsplit("/", 1)[-1]
    return base[:-len(".service")] if base.endswith(".service") else base


def _reboot_and_services(opts: Options) -> tuple[str, str, str, str]:
    """The reboot verdict, its reason, and the services split into safe and risky."""
    reboot, reason = "no", ""
    if shutil.which("zypper"):
        # zypper exits EXACTLY 102 when a reboot is advised. Any OTHER non-zero
        # code means the check itself failed (the lock was held, say) — reading
        # that as "reboot needed" would make a blocked run nag forever.
        if proc.run(["zypper", "needs-rebooting"], merge_stderr=True)[0] == 102:
            reboot = "yes"
            reason = steps.SYS_REBOOT_DETAIL or "core system packages were updated"
    if reboot == "no" and steps.FW_CHANGED:
        reboot, reason = "yes", "firmware was updated"
    markers.marker("INSTALLED", f"{steps.SYS_COUNT}|"
                               f"{'yes' if steps.SYS_CHANGED else 'no'}|"
                               f"{'yes' if steps.FW_CHANGED else 'no'}")
    # The reason is appended only when a reboot is advised, so the no-reboot
    # marker stays exactly "@@REBOOT@@|no" — the reason is an optional field.
    markers.marker("REBOOT", reboot + (f"|{reason}" if reason else ""))

    services = safe = risky = ""
    if steps.SYS_CHANGED and reboot == "no" and shutil.which("zypper"):
        _, raw = privilege.sudo(["zypper", "ps", "-sss"])
        services = " ".join(raw.split())
        if services:
            markers.marker("SERVICES", services)
        # The marker above is deliberately UNCHANGED and still carries every
        # name: the window does its own split and marker-protocol.md §5.1
        # freezes the field. Only the printed advice below is split.
        dm_unit = _display_manager_unit()
        for svc in services.split():
            base = svc[:-len(".service")] if svc.endswith(".service") else svc
            if _SESSION_CRITICAL.match(base) or (dm_unit and base == dm_unit):
                risky += (" " if risky else "") + svc
            else:
                safe += (" " if safe else "") + svc
    return reboot, reason, safe, risky


_ICON = {"ok": "OK  ", "skip": "SKIP", "fail": "FAIL"}


def _summary(opts: Options, run_keys: list[str], reboot: str, reason: str,
             safe: str, risky: str) -> None:
    """The closing block: per-step outcomes, what was installed, and `@@DONE@@`."""
    markers.out("")
    markers.out("==========================================")
    markers.out("               Summary                    ")
    markers.out("==========================================")
    for key in run_keys:
        status = steps.RESULT.get(key, "skip")
        detail = steps.DETAIL.get(key, "")
        secs = steps.SECS.get(key, 0)
        icon = _ICON.get(status, "?   ")
        tail = f"   ({detail})" if detail else ""
        markers.out(f"  [{icon}] {steps.LABEL[key]:<26} {secs:3d}s{tail}")
    markers.out("------------------------------------------")
    if opts.selected("system"):
        if steps.SYS_COUNT == "0":
            markers.out("  Updates installed: none — system was already up to date.")
        elif steps.SYS_COUNT:
            markers.out(f"  Updates installed: {steps.SYS_COUNT} system package(s).")
        elif steps.SYS_CHANGED:
            markers.out("  Updates installed: yes (system packages updated).")
    if steps.FW_CHANGED:
        markers.out("  Firmware: updates applied.")
    markers.out("------------------------------------------")
    if steps.ERRORS > 0:
        markers.out(f"  Finished with {steps.ERRORS} error(s) — see the log above.")
        markers.marker("DONE", "errors")
    elif proc.stop_announced():
        # Not "ok": the run did not do what was asked of it. Not "errors"
        # either — nothing went wrong. The window reports it as stopped.
        markers.out("  Stopped at your request — the steps above are all that ran.")
        markers.marker("DONE", "stopped")
    else:
        markers.out("  All selected steps completed cleanly.")
        markers.marker("DONE", "ok")
    if reboot == "yes":
        markers.out("")
        markers.out(f"  ! A REBOOT is recommended — {reason}.")
    elif safe or risky:
        if safe:
            markers.out("")
            markers.out("  ! No reboot needed for these services, but they should "
                        "restart to use the")
            markers.out(f"    new libraries:  {safe}")
        # ONEUP-0115: where the honest answer is a reboot, say so in the same
        # words the reboot path uses, rather than naming units under a heading
        # that has just said no reboot is needed.
        if risky:
            markers.out("")
            markers.out("  ! A REBOOT is recommended — these hold replaced libraries, "
                        "and restarting")
            markers.out("    them would BREAK OR END your desktop session:")
            markers.out(f"      {risky}")


def _notify(opts: Options, log_file: Path) -> None:
    """The end-of-run desktop notification, for the unattended weekly timer."""
    if not opts.notify:
        return
    # Unattended auto-skip sets a source aside silently, and this notification is
    # the ONLY place a nobody's-watching run reports it — so name it here.
    skip_note = (f" (skipped: {' '.join(repos.DISABLED)} — will retry next time)"
                 if repos.DISABLED else "")
    if steps.ERRORS > 0:
        actions.notify_send("Update failed",
                            f"One or more steps failed — see the log: {log_file}")
    elif steps.SYS_COUNT and steps.SYS_COUNT != "0":
        actions.notify_send("Update complete",
                            f"{steps.SYS_COUNT} system package(s) installed.{skip_note}")
    elif steps.SYS_CHANGED or steps.FW_CHANGED:
        actions.notify_send("Update complete", f"Updates were installed.{skip_note}")
    else:
        actions.notify_send("Already up to date", f"No updates were needed.{skip_note}")


def run(opts: Options, run_keys: list[str], log_file: Path, held_auth: bool = False) -> int:
    """One full run, in the Bash's order — which is itself the deliverable.

    Four points where the order is load-bearing and the suite can only see it
    indirectly: `sudo_init` before `release_zypper_lock`; `run.state` written
    only once the run is definitely going ahead, after the lock-holder check;
    the pre-update snapshot before the pre-flight warnings; the banner
    after both, which reads oddly and is where the Bash prints it; and — above
    this function, in `main` — the inhibitor re-exec before the log mirror, or
    the re-exec'd process installs a second one.

    The banner was the one divergence gate G2 found (ONEUP-0054 stage 6). It is
    console text, so a marker-only diff would not have seen it; do not "tidy" it
    back to the top of the run without changing the Bash in the same commit.
    """
    # Firmware elevates through polkit on its own; every other root step reuses
    # the cached credential, so we only bootstrap when a sudo step is selected.
    needs_sudo = any(opts.selected(k) for k in ("system", "flatpak", "orphans", "cache"))
    # A held preview already authenticated in THIS process and `sudo_init` has no
    # re-entry guard, so re-entering it would re-run the interactive validate AND
    # spawn a second keep-alive — overwriting the handle `cleanup`'s group kill
    # uses, and orphaning the first (ONEUP-0041, security.md §2.4). INV-9 pins it.
    if needs_sudo and not held_auth:
        privilege.sudo_init()
    if needs_sudo:
        repos.release_zypper_lock()

    # Anything else holding the lock would make every zypper step fail for one
    # reason, so say that reason once and stop rather than reporting a pile of
    # failures (ONEUP-0039). A Flatpak- or firmware-only run is unaffected.
    needs_zypper = any(opts.selected(k) for k in ("system", "orphans", "cache"))
    if needs_zypper:
        holder = repos.lock_holder()
        if holder:
            holder_pid, _, holder_name = holder.partition(" ")
            markers.out(f"The package manager is busy: {holder_name} "
                        f"(process {holder_pid}) is using it.")
            markers.out("Nothing has been changed. Try again once it has finished.")
            markers.hint(
                "Something else is installing or removing software right now — "
                f"{holder_name} (process {holder_pid}). That is often OneUp's own earlier "
                "run still finishing in the background; it clears on its own. Nothing was "
                "changed, so just run the update again in a minute.")
            markers.marker("DONE", "errors")
            return 1

    # From here the run is definitely going ahead, so record it: a window
    # starting up can then find a run already in flight and follow its log
    # rather than offering a Run button that could only fail on the lock.
    runstate.write_run_state(log_file, opts.steps)

    if opts.selected("system"):
        _pre_update_snapshot()
        _preflight()

    markers.out("")
    markers.out("########################################################")
    markers.out("#            Starting System Update                    #")
    markers.out(f"#   Steps: {opts.steps}")
    markers.out(f"#   Log:   {log_file}")
    markers.out("########################################################")

    for key in run_keys:
        if proc.stop_pending():
            break
        _DISPATCH[key](opts)

    reboot, reason, safe, risky = _reboot_and_services(opts)
    _summary(opts, run_keys, reboot, reason, safe, risky)
    _notify(opts, log_file)
    markers.out(f"  Log saved: {log_file}")
    markers.out("==========================================")
    # Non-zero when anything failed, so the window can colour the run.
    return 1 if steps.ERRORS else 0


_DISPATCH = {
    "system": lambda opts: steps.run_system(opts),
    "flatpak": lambda _opts: steps.run_flatpak(),
    "firmware": lambda _opts: steps.run_firmware(),
    "orphans": lambda opts: steps.run_orphans(opts),
    "cache": lambda _opts: steps.run_cache(),
}


if __name__ == "__main__":
    sys.exit(main())
