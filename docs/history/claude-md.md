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

## A spec's `Reviewed` stamp goes stale

`ONEUP-0044` pinned `hold.state` and `go.request` into
`docs/specs/ONEUP-0054-python-engine.md` §4.1.1 on 2026-08-23 — a change to what the Python
engine's implementer must build — and that spec's stamp still read `Reviewed` from July. Six
specs were stale on 2026-08-24, which is what established that a stale stamp is the normal
state of a busy branch rather than an incident. Recorded on `ONEUP-0127`.

## The suite's prompt counters

The `HELD_AUTH` measurement was re-taken on 2026-09-02 and came back the same: exactly one
check fails, and the one-prompt scenario stays green. Recorded on `ONEUP-0044`.

## The app draws no focus ring

The trap read *"focus reuses the hover look"* until the contrast measurement replaced it.
Hover lightens, and no lighter shade of the accent button's top gradient stop reaches
SC 2.4.13's 3:1 — so the rule became a derived fill rather than a copied one. The measurement
itself stays in `CLAUDE.md` §6, because it is the reason the rule is believable.
