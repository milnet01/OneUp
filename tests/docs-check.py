#!/usr/bin/env python3
"""Documentation gate — the rules of docs/standards/documentation.md a script can settle.

It reports and never repairs (workflow.md §6.1): it names the file, the line and the rule,
and the author decides what the right text is. A gate that edited prose would quietly
rewrite a claim it does not understand.

Stdlib only, no network, no writes. Exit 0 = green, 1 = a rule was broken.

    python3 tests/docs-check.py          # or via ./local-CI.sh
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Specs written before 2026-07-26, when §3's header block became prescriptive. They are
# brought to shape the next time each is edited for another reason, not in a sweep (§3).
GRANDFATHERED = {"ONEUP-0018", "ONEUP-0022", "ONEUP-0025", "ONEUP-0028"}

# Markers the engine emits that the engine suite does not assert on. Each needs a roadmap
# id, so the exemption reads as a known gap rather than an oversight. DISK fires only when
# a mount drops below the pre-flight threshold, which no scenario currently arranges; the
# GUI half IS covered, in tests/gui-smoke.py.
KNOWN_UNTESTED_MARKERS = {"DISK"}  # ONEUP-0069

STATUS_RE = re.compile(r"^\*\*Status:\*\* (Draft|Reviewed|Implemented|Superseded by \S+)"
                       r"(?: — cold-eyes in progress)?$")
# §6a's durable-citation ban. The prose form ("~line 786") is deliberately not caught —
# see the "What checks this" table in docs/standards/documentation.md.
LINENO_RE = re.compile(r"\b[\w./-]+\.(?:py|sh|yml|yaml|xml|toml|json|spec):\d+")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)")
PATH_RE = re.compile(r"`([\w.-]+(?:/[\w.<>-]+)+\.(?:md|py|sh|yml|yaml|xml|toml|json|spec))`")
MARKER_RE = re.compile(r"(?<![\w`])(TODO|FIXME|TBD|XXX)(?![\w`])")
SEVERITY_RE = re.compile(r"(\d+)\s+(critical|high|medium|low|info)\b", re.I)
DISPOSITION_RE = re.compile(r"(\d+)\s+(verified|dismissed|info)\b", re.I)

failures: list[str] = []
checked = 0


def check(cond: bool, path: Path, line: int, rule: str, msg: str) -> None:
    global checked
    checked += 1
    if not cond:
        where = f"{path.relative_to(ROOT)}:{line}" if line else str(path.relative_to(ROOT))
        failures.append(f"{where}  [{rule}]  {msg}")


def docs(*subdirs: str) -> list[Path]:
    # A missing directory makes glob() return nothing, which reads exactly like "every
    # document here passes": the rules keyed to it stop checking and the run still goes
    # green, only with a smaller tally nobody reads. Fail loudly instead.
    for d in subdirs:
        check((ROOT / d).is_dir(), ROOT / d, 0, "harness",
              "documentation directory is missing; every rule keyed to it checked nothing")
    return sorted(p for d in subdirs for p in (ROOT / d).glob("*.md"))


def grandfathered(path: Path) -> bool:
    return any(path.name.startswith(g) for g in GRANDFATHERED)


# --- §3: the header block ---------------------------------------------------
def check_headers() -> None:
    fields = ["**Status:**", "**Kind:**", "**Roadmap:**", "**Branch:**", "**Verified at:**"]
    for path in docs("docs/standards", "docs/reference", "docs/design", "docs/specs"):
        if grandfathered(path):
            continue
        head = path.read_text().split("\n")[:30]
        for field in fields:
            check(any(ln.startswith(field) for ln in head), path, 0, "§3",
                  f"header block is missing {field}")
        for i, ln in enumerate(head, 1):
            if ln.startswith("**Status:**"):
                check(bool(STATUS_RE.match(ln)), path, i, "§3",
                      f"Status must be one of the four values and carry no history: {ln!r}")


# --- §4 and §8.2: the sections every standard carries -----------------------
def check_sections() -> None:
    for path in docs("docs/standards", "docs/reference"):
        text = path.read_text()
        check("**In one sentence:**" in text, path, 0, "§8.2",
              "no '**In one sentence:**' opener")
        check("## What checks this" in text, path, 0, "§4",
              "no '## What checks this' section")
        check("Cold-eyes loop log" in text, path, 0, "§4",
              "no 'Cold-eyes loop log' section")


# --- §7: a loop-log tally must balance --------------------------------------
def check_loop_tallies() -> None:
    for path in docs("docs/standards", "docs/reference", "docs/design", "docs/specs"):
        in_log = False
        for i, ln in enumerate(path.read_text().split("\n"), 1):
            if ln.startswith("#"):
                in_log = "Cold-eyes loop log" in ln
                continue
            if not in_log or not ln.startswith("|"):
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) < 3 or not cells[0].isdigit():
                continue
            findings = cells[2]
            # The disposition clause is bolded, and sits in either the Findings cell or the
            # Outcome one — authors have used both, and a check that saw only the first
            # would skip the second in silence.
            bold = re.findall(r"\*\*(.+?)\*\*", " ".join(cells[2:]))
            # Match each bold span on its own. Joining them first lets a number ending one
            # span pair with a disposition word starting the next: a bolded "**0.069**"
            # followed by "**Dismissed: two**" reads as "69 dismissed" and fails a row that
            # balances perfectly. That is the second of this check's two recorded failure
            # modes (the first being that a dismissed finding still needs a severity).
            counts = [int(n) for span in bold for n, _ in DISPOSITION_RE.findall(span)]
            if not counts:
                continue  # no numeric disposition clause — nothing to balance
            raw = [int(n) for n, _ in SEVERITY_RE.findall(findings.split("**")[0])]
            check(sum(raw) == sum(counts), path, i, "§7",
                  f"loop {cells[0]} tally does not balance: {sum(raw)} findings "
                  f"({'+'.join(map(str, raw))}) against {sum(counts)} outcomes "
                  f"({'+'.join(map(str, counts))})")


# --- §6a: cite by name, never by line number --------------------------------
def check_line_citations() -> None:
    # docs/specs/ is exempt until ONEUP-0065 converts the citations the four remaining
    # pre-2026-07-26 specs carry (62 of them; ONEUP-0054's 7 went when ONEUP-0057 Task 12
    # revised it). Widen this to include specs when that item ships.
    for path in docs("docs/standards", "docs/reference", "docs/design"):
        ignore = False
        for i, ln in enumerate(path.read_text().split("\n"), 1):
            if ln.startswith("#"):
                ignore = False
            if "docs-check: ignore-line-numbers" in ln:
                ignore = True
            if ignore:
                continue
            hit = LINENO_RE.search(ln)
            check(hit is None, path, i, "§6a",
                  f"line-number citation {hit.group(0)!r} — cite the symbol instead"
                  if hit else "")


# --- §9: a pointer resolves -------------------------------------------------
def check_pointers() -> None:
    # Only the documents that describe the tree as it is today. A spec, a design document
    # and a plan all legitimately name files they are going to create (§2), so a dangling
    # path in one of those is a forward reference, not a stale pointer.
    for path in [*docs("docs/standards", "docs/reference"), ROOT / "CLAUDE.md",
                 ROOT / "README.md"]:
        for i, ln in enumerate(path.read_text().split("\n"), 1):
            # A markdown link is relative to the document; a backticked path is a command
            # or a repo path, so it is relative to the root and may carry a leading "./".
            for target in LINK_RE.findall(ln):
                if not target.startswith(("http", "mailto")):
                    check((path.parent / target).exists(), path, i, "§9",
                          f"pointer does not resolve: {target}")
            for target in PATH_RE.findall(ln):
                head = target.split("/")[0]
                if "<" in target or head.isupper():  # `$HERE/…` and friends are templates
                    continue
                check((ROOT / target.removeprefix("./")).exists(), path, i, "§9",
                      f"pointer does not resolve: {target}")


# --- §6: no unfinished markers ----------------------------------------------
def check_markers() -> None:
    for path in docs("docs/standards", "docs/reference", "docs/design", "docs/specs"):
        for i, ln in enumerate(path.read_text().split("\n"), 1):
            hit = MARKER_RE.search(ln)
            check(hit is None, path, i, "§6",
                  f"unfinished marker {hit.group(0)!r} in a document meant to be "
                  f"implementable" if hit else "")


# --- the marker contract matches the engine ---------------------------------
def check_marker_table() -> None:
    """docs/reference/ outranks both halves of the app (§1.1), so a marker the engine emits
    and the table omits makes the *contract* wrong, not the code. Compared against the engine
    only: the GUI dispatches on the parsed name, so it has no comparable token list."""
    doc = ROOT / "docs/reference/marker-protocol.md"
    table = set(re.findall(r"^\| `@@([A-Z_]+)@@", doc.read_text(), re.M))
    # Compare against the `marker NAME "payload"` CALL SITES, which is where a marker is
    # actually emitted (`marker()` does the printf). Matching `@@NAME@@` literals instead
    # would compare the table against the engine's header comment — and §7 of that same
    # document records three inaccuracies in it, so the check would be validating one
    # stale list against another and calling it agreement.
    engine = set(re.findall(r"\bmarker ([A-Z_]+)",
                            (ROOT / "update_system.sh").read_text()))
    check(not engine - table, doc, 0, "§3",
          f"the engine emits markers this table omits: {sorted(engine - table)}")
    check(not table - engine, doc, 0, "§3",
          f"this table names markers the engine never emits: {sorted(table - engine)}")
    # The engine suite is what proves each marker is really produced. A marker nothing
    # asserts on is a row in the contract with no evidence behind it.
    tested = set(re.findall(r"@@([A-Z_]+)@@", (ROOT / "tests/run-tests.sh").read_text()))
    untested = engine - tested - KNOWN_UNTESTED_MARKERS
    check(not untested, doc, 0, "§3",
          f"markers the engine emits that no engine-suite scenario asserts on: "
          f"{sorted(untested)}")


# --- the CHANGELOG's own links agree with its newest heading ---------------
def check_changelog_links() -> None:
    """`bump.py` writes three things into CHANGELOG.md — the heading, the release link and
    the [Unreleased] compare base. `local-CI.sh`'s lockstep gate reads only the heading, and
    `tests/bump-test.py` proves bump.py's behaviour against a synthetic fixture, so nothing
    checked the real file. A stale compare base is ONEUP-0033, a bug this project shipped."""
    path = ROOT / "CHANGELOG.md"
    text = path.read_text()
    newest = re.search(r"^## \[(\d+\.\d+\.\d+)\]", text, re.M)
    check(newest is not None, path, 0, "workflow §5.1",
          "no `## [x.y.z]` release heading found" if not newest else "")
    if not newest:
        return
    ver = newest.group(1)
    check(f"\n[{ver}]: " in text, path, 0, "workflow §5.1",
          f"newest heading is {ver} but no `[{ver}]:` link reference exists at the foot")
    base = re.search(r"^\[Unreleased\]: \S+/compare/v(\d+\.\d+\.\d+)\.\.\.HEAD", text, re.M)
    check(base is not None and base.group(1) == ver, path, 0, "workflow §5.1",
          f"[Unreleased] compare base is "
          f"{'absent' if not base else 'v' + base.group(1)}, not v{ver} (ONEUP-0033)")


def main() -> int:
    for fn in (check_headers, check_sections, check_loop_tallies, check_line_citations,
               check_pointers, check_markers, check_marker_table, check_changelog_links):
        fn()
    for line in failures:
        print(f"  FAIL {line}")
    print(f"\n  Checked: {checked}   Failed: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
