"""Run the five steps: system, flatpak, firmware, orphans, cache.

**Built so far: `system_txn_argv` and nothing else.** The step bodies, the
pre-update snapshot block, the remedies and the repo skipping arrive with the
run driver at stage 5 (`docs/specs/ONEUP-0054-python-engine.md` §4.6).

That one function is here rather than in `actions.py` because §4.2 places it
here, and it is SHARED rather than copied because ONEUP-0085 INV-5 requires the
argv a `--size` prices and the argv the run performs to be the same one — a flag
in one and not the other quotes the size of a different transaction.
"""

from __future__ import annotations

from pathlib import Path

# Set by the download-recovery path (ONEUP-0094) to a throwaway repos.d built by
# `repos.make_cdn_reposd`. Empty means "use the system's own".
REPOSD_OVERRIDE = ""


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
