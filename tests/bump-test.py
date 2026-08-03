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
depend on the mutable real changelog. Every site is read back after the bump —
an exit code alone proves only that the regexes matched, not that they wrote the
right value.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# bump.py itself is copied only so the subprocess's ROOT resolves to the temp tree — it
# never edits itself. The other four are the real version-bearing files it rewrites
# (steps 1–5), copied verbatim so their real formats are exercised.
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

# Deliberately a version no real file already contains. bump.py PREPENDS to the RPM
# %changelog and the AppStream <releases> list, so a target that collides with a version
# already in the shipped history (1.3.0 did) makes those two read-backs match the old
# entry and pass no matter what bump.py wrote — two assertions that could never fail.
NEW = "9.9.9"


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
        # Not just that the heading exists — that the section under it is EMPTY. A bug that
        # left the old bullets in place instead of moving them under the promoted version
        # would still satisfy a bare substring test.
        reopened = re.search(r"## \[Unreleased\]\n(.*?)(?=\n## \[)", chg, re.S)
        check(reopened is not None and not reopened.group(1).strip(),
              "fresh EMPTY ## [Unreleased] section left for the next cycle")
        check(f"[{NEW}]: https://github.com/milnet01/OneUp/releases/tag/v{NEW}" in chg,
              f"release link [{NEW}] added")
        # The ONEUP-0033 fix: the compare base must advance to the released tag.
        check(f"[Unreleased]: https://github.com/milnet01/OneUp/compare/v{NEW}...HEAD" in chg,
              f"[Unreleased] compare base advanced to v{NEW}")
        check("compare/v1.2.0...HEAD" not in chg,
              "stale compare base v1.2.0 no longer present")


        # The other five sites. bump.py exiting 0 proves only that its regexes still
        # MATCHED each file; it cannot catch a substitution that matched and then wrote
        # the wrong value (a mis-numbered backreference, the wrong variable). Assert the
        # new version at each site, in the shape that site actually uses — a bare
        # "NEW appears somewhere in the file" would pass on the release-notes text too.
        v = re.escape(NEW)
        sites = [
            ("updater.py", "APP_VERSION", rf'APP_VERSION = "{v}"'),
            ("packaging/rpm/oneup.spec", "Version:", rf"^Version:\s+{v}$"),
            ("packaging/rpm/oneup.spec", "%changelog stanza", rf"^\* .+ - {v}-0$"),
            ("packaging/obs/_service", "versionformat", rf'versionformat">{v}<'),
            ("packaging/obs/_service", "revision tag", rf'revision">v{v}<'),
            ("data/za.co.antsprojectshub.OneUp.metainfo.xml", "<release> entry",
             rf'<release version="{v}" date="\d{{4}}-\d{{2}}-\d{{2}}">'),
        ]
        for rel, site, pattern in sites:
            found = re.search(pattern, (tmp / rel).read_text(), re.M) is not None
            check(found, f"{rel} {site}: bumped to {NEW}")

    print(f"\nPassed: {passed}   Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
