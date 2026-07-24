#!/usr/bin/env python3
"""Functional test for bump.py — runs a real bump inside a throwaway copy of the
repo and asserts every version site advanced, with particular attention to the
CHANGELOG `[Unreleased]` compare-link base (the ONEUP-0033 regression: the base
was left pointing at the *previous* tag after a release).

No dependencies beyond the stdlib. Exit 0 on success, non-zero on any failure —
same contract as tests/gui-smoke.py, so local-CI.sh and GitHub CI invoke it the
same way. The five non-CHANGELOG version files are copied verbatim from the real
checkout (so the test also guards that bump.py's regexes still match their real
formats); the CHANGELOG is a small synthetic fixture so the assertions don't
depend on the mutable real changelog.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Real files bump.py edits (steps 1–5) — copied so their formats are exercised.
REAL_FILES = [
    "bump.py",
    "updater.py",
    "packaging/rpm/oneup.spec",
    "packaging/obs/_service",
    "data/za.co.antsprojectshub.OneUp.metainfo.xml",
]

# A minimal but valid CHANGELOG: a non-empty [Unreleased] section (bump refuses
# an empty one) and a footer whose [Unreleased] compare base points at v1.2.0.
CHANGELOG_FIXTURE = """\
# Changelog

## [Unreleased]
### Added
- **A brand-new widget.**

## [1.2.0] - 2026-07-22
### Added
- **Something already shipped.**

[Unreleased]: https://github.com/milnet01/OneUp/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/milnet01/OneUp/releases/tag/v1.2.0
"""

NEW = "1.3.0"


def main() -> int:
    passed = failed = 0

    def check(cond: bool, msg: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  ok   {msg}")
        else:
            failed += 1
            print(f"  FAIL {msg}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for rel in REAL_FILES:
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dst)
        (tmp / "CHANGELOG.md").write_text(CHANGELOG_FIXTURE)

        # bump.py resolves ROOT from its own location, so running the copy makes
        # it edit the temp tree, never the real checkout.
        proc = subprocess.run(
            [sys.executable, str(tmp / "bump.py"), NEW],
            capture_output=True, text=True,
        )
        check(proc.returncode == 0, f"bump.py {NEW} exits 0 (stderr: {proc.stderr.strip()!r})")

        chg = (tmp / "CHANGELOG.md").read_text()
        check(f"## [{NEW}] - " in chg, f"[Unreleased] heading promoted to ## [{NEW}]")
        check("## [Unreleased]" in chg, "fresh empty ## [Unreleased] heading left for the next cycle")
        check(f"[{NEW}]: https://github.com/milnet01/OneUp/releases/tag/v{NEW}" in chg,
              f"release link [{NEW}] added")
        # The ONEUP-0033 fix: the compare base must advance to the released tag.
        check(f"[Unreleased]: https://github.com/milnet01/OneUp/compare/v{NEW}...HEAD" in chg,
              f"[Unreleased] compare base advanced to v{NEW}")
        check("compare/v1.2.0...HEAD" not in chg,
              "stale compare base v1.2.0 no longer present")

    print(f"\nPassed: {passed}   Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
