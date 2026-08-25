"""Parse the command line and dispatch one run.

The flag surface is frozen (`docs/design/oneup-2.0.md` §3): every flag
`update_system.sh` accepts, with the same spelling and the same behaviour.

**Stage 2 acts on `--help`, `--auth-status` and `--emit-guard` only.** Every
other flag is still parsed and stored — `--log=` above all, which the test
suite appends to every invocation, so an engine that rejected it could not be
reached at all. What refuses is a flag selecting *work* this stage has not
built, and it refuses loudly rather than exiting 0 on a run it never performed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from . import actions, markers, runstate

ALL_STEPS = "system,flatpak,firmware,orphans,cache"

# Exit codes. 0 and 1 are ordinary; 2 is an unknown flag; 130/143/141 are the trap codes
# the Bash engine sets (SIGINT, SIGTERM/SIGHUP, SIGPIPE) and are reproduced by the run
# driver at its own stage. `docs/specs/ONEUP-0054-python-engine.md` §4.1.1 pins all of them.
EXIT_UNKNOWN_FLAG = 2
# Stage-only, and it disappears when stage 9 completes the engine: a flag that parses but
# selects work no stage has built yet. Deliberately none of the pinned codes, so it can
# never be mistaken for one.
EXIT_NOT_BUILT = 3


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


def usage() -> str:
    """The help text, matching `update_system.sh`'s `usage`.

    Plain concatenation rather than an f-string: ruff's bandit rules read a long
    interpolated literal as a possible SQL query (S608), and a suppression here
    would be silencing a rule rather than answering it.
    """
    return _USAGE_HEAD + str(runstate.USER_LOG_DIR) + _USAGE_TAIL


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
                 skip the culprit(s), then continue.
  --thin-snapshots  Ask snapper to remove old, expendable Btrfs snapshots (its own
                 retention cleanup — keeps the recent ones), then report how many.
  --log=FILE     Write the run log here. Default: """

_USAGE_TAIL = """/<timestamp>.log
  --help         Show this help.
"""


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
        elif arg.startswith("--size="):
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


def _not_built(what: str, stage: str) -> int:
    """Refuse work this stage has not built — loudly, and never on stdout.

    Silence plus exit 0 would read as a run that found nothing to do, and a
    marker on stdout would read as a run that happened.
    """
    markers.err(f"oneup.engine: {what} is not built yet — ONEUP-0054 {stage} owes it.")
    return EXIT_NOT_BUILT


def main(argv: list[str] | None = None) -> int:
    opts, code = parse(sys.argv[1:] if argv is None else argv)
    if opts is None:
        return code

    if opts.auth_action == "status":
        return actions.auth_status()
    if opts.auth_action == "emit-guard":
        return actions.emit_guard()
    if opts.auth_action in ("grant", "revoke"):
        return _not_built(f"--{opts.auth_action}-auth", "stage 5")
    if opts.thin_snapshots:
        return _not_built("--thin-snapshots", "stage 5")
    if opts.check_only:
        return _not_built("--check", "stage 3")
    if opts.size_step:
        return _not_built("--size=", "stage 4")
    return _not_built("a full run", "stage 5")


if __name__ == "__main__":
    sys.exit(main())
