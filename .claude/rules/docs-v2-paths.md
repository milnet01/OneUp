---
paths:
  - "docs/**"
  - "CLAUDE.md"
  - "README.md"
---

# v2-only paths in scanned documents

Moved from `CLAUDE.md` §4, which keeps a pointer here; only "this file" became `CLAUDE.md`.

**No document `tests/docs-check.py` scans may backtick a path that exists only on `v2`** —
and it scans four: `docs/standards/`, `docs/reference/`, `CLAUDE.md` and `README.md`. Its §9
check fails a backticked path that carries **both** a directory separator and a file
extension and does not resolve, so a standard here cannot name `oneup/gui/…py`. Neither a
bare directory nor a bare filename matches that pattern, which is how
`docs/standards/files-and-naming.md` §4 already describes the package's shape and rules on
`main`, correctly — and is not licence to evade the check by dropping the directory. Where a standard must name a package file, that is a rule binding it
to code `main` does not have; `docs/standards/workflow.md` §9 decides the branch, and
`CLAUDE.md` does not restate it.
