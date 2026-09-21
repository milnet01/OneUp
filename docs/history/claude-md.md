# CLAUDE.md — history

Why a rule in `CLAUDE.md` says what it says. **Nothing here is a rule.** Where this file and
`CLAUDE.md` disagree about what to do, `CLAUDE.md` governs; where either disagrees with a
standard, the standard governs (`docs/standards/documentation.md` §1.1).

Each entry names the rule it belongs to, so a reader arriving from `CLAUDE.md` can find it.

## The file's own ranking

`CLAUDE.md` used to restate its place in the document order in full — above only
`~/.claude/standards/`, with `roadmap-format.md`'s bullet grammar as the one exception no
project may override. That ranking is `docs/standards/documentation.md` §1.1's to state and
§1.2 holds the exception, so the restatement was a second copy that could disagree with the
first. `CLAUDE.md` now points at both instead.

## `ROADMAP.md` is generated output

The roadmap moved to the Ants roadmap store on 2026-08-18, and the store has been the source
of truth since. The migration was verified lossless: normalising whitespace makes the
rendered file character-for-character identical to its pre-migration content. Recorded on
`ONEUP-0057`.

## A shape check on a field of codes does not catch English

The defect was caught in review rather than in production, on `ONEUP-0072`. Running the
regex is what found it; reading it had not.
