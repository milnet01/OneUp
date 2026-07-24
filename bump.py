#!/usr/bin/env python3
"""Bump OneUp to a new version across every version-bearing file at once.

Usage:  ./bump.py X.Y.Z

Edits the six lockstep sites CLAUDE.md documents — updater.py APP_VERSION, the RPM
spec Version + %changelog, the OBS _service versionformat + revision, the AppStream
<release>, and the CHANGELOG heading + link — and derives the spec/metainfo release
notes from the CHANGELOG's `## [Unreleased]` bullets, so that section is the single
source of truth. Afterwards, review `git diff` and run ./local-CI.sh (its
version-lockstep gate confirms all six agree). ./release.sh calls this for you.
"""
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUTHOR = "Anthony Schemel <aant.schemel@gmail.com>"
REPO = "milnet01/OneUp"


def die(msg: str):
    print(f"bump: {msg}", file=sys.stderr)
    sys.exit(1)


def edit(rel_path: str, pattern: str, repl: str, count: int = 1, flags: int = 0):
    path = ROOT / rel_path
    text = path.read_text()
    new, n = re.subn(pattern, repl, text, count=count, flags=flags)
    if n == 0:
        die(f"no match for {pattern!r} in {rel_path} — file drifted from the expected format")
    path.write_text(new)


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        die("usage: ./bump.py X.Y.Z")
    ver = sys.argv[1]
    today = datetime.date.today().isoformat()               # 2026-07-21
    rpmdate = datetime.date.today().strftime("%a %b %d %Y")  # Tue Jul 21 2026

    # --- the CHANGELOG [Unreleased] bullets are the single source of truth ---
    changelog = (ROOT / "CHANGELOG.md").read_text()
    m = re.search(r"## \[Unreleased\]\n(.*?)(?=\n## \[)", changelog, re.S)
    if not m or not m.group(1).strip():
        die("CHANGELOG.md has no non-empty '## [Unreleased]' section to release — "
            "add your changes there first.")
    items = re.findall(r"^- \*\*(.+?)\*\*", m.group(1), re.M)
    if not items:
        items = [f"Release {ver}."]
    # strip inline-code backticks for the plain-text/XML targets
    plain = [re.sub(r"`", "", it).strip() for it in items]

    # 1. updater.py APP_VERSION
    edit("updater.py", r'APP_VERSION = "\d+\.\d+\.\d+"', f'APP_VERSION = "{ver}"')

    # 2. RPM spec Version:
    edit("packaging/rpm/oneup.spec", r'^(Version:\s+)\d+\.\d+\.\d+',
         rf'\g<1>{ver}', flags=re.M)

    # 3. RPM spec %changelog — prepend a stanza
    stanza = f"* {rpmdate} {AUTHOR} - {ver}-0\n" + "".join(f"- {it}\n" for it in plain)
    edit("packaging/rpm/oneup.spec", r'(%changelog\n)', lambda mo: mo.group(1) + stanza)

    # 4. OBS _service versionformat + revision (revision is the git tag vX.Y.Z)
    edit("packaging/obs/_service", r'(versionformat">)\d+\.\d+\.\d+', rf'\g<1>{ver}')
    edit("packaging/obs/_service", r'(revision">)v?\d+\.\d+\.\d+', rf'\g<1>v{ver}')

    # 5. AppStream metainfo <release> — prepend a new entry
    li = "\n".join(f"          <li>{xml_escape(it)}</li>" for it in plain)
    rel = (f'<release version="{ver}" date="{today}">\n'
           f'      <description>\n'
           f'        <p>Release {ver}.</p>\n'
           f'        <ul>\n{li}\n        </ul>\n'
           f'      </description>\n'
           f'    </release>\n    ')
    edit("data/za.co.antsprojectshub.OneUp.metainfo.xml",
         r'(<releases>\n\s*)(<release)', lambda mo: mo.group(1) + rel + mo.group(2))

    # 6. CHANGELOG — promote [Unreleased] to the version (leaving a fresh empty
    #    [Unreleased] on top for the next cycle, per Keep a Changelog), add the
    #    release link, and advance the [Unreleased] compare base to the tag just
    #    cut (else it keeps pointing at the previous release, a stale range — ONEUP-0033).
    edit("CHANGELOG.md", r'## \[Unreleased\]', f'## [Unreleased]\n\n## [{ver}] - {today}')
    edit("CHANGELOG.md", r'(\n\[\d)',
         f'\n[{ver}]: https://github.com/{REPO}/releases/tag/v{ver}\\g<1>')
    edit("CHANGELOG.md", r'(\[Unreleased\]: \S+/compare/)v\d+\.\d+\.\d+(\.\.\.HEAD)',
         rf'\g<1>v{ver}\g<2>')

    print(f"bump: {ver} written to all six version sites (notes from CHANGELOG [Unreleased]).")
    print("Next: review 'git diff', then './local-CI.sh' — or just run './release.sh " + ver + "'.")


if __name__ == "__main__":
    main()
