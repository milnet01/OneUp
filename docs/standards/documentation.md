# Documentation Standard

**In one sentence:** every document here has one job, and this file says which job, so
nobody has to guess where a decision belongs or whether it has been reviewed.

**Applies to:** every document in the repository. Written 2026-07-26, verified against
the tree at `dbef1a8` (v1.4.0).

## 1. The documents, and what each is for

| Document | Audience | Holds | Never holds |
| --- | --- | --- | --- |
| `README.md` | users | what OneUp is, how to install and run it | design rationale, invariants |
| `CLAUDE.md` | whoever works on the code next | a map of the repo, and the **traps** — rules that cost a real bug to learn | the full text of a rule that lives in a standard |
| `ROADMAP.md` | the project | every item of intended work, its status, and how it was resolved | design detail that belongs in a spec |
| `CHANGELOG.md` | users | what shipped, in each release, in plain English | anything unreleased-and-abandoned |
| `docs/design/` | the project | **programme-level** decisions that several items share or contend over | one item's implementation detail |
| `docs/specs/` | the implementer | **one item's** contract: what it must do and how it is proven | build steps |
| `docs/plans/` | the implementer | **one item's** build steps, in order, with verification | design decisions (they belong in the spec) |
| `docs/standards/` | everyone | standing rules that outlive any one item | anything version-specific |
| `docs/reference/` | both halves of the app | frozen contracts — formats, protocols | rules or rationale |

**The distinction that matters most:** a *standard* is a rule that applies to work not yet
imagined; a *spec* is a contract for one piece of work. If a sentence would still be true
after 2.0 ships, it is a standard.

## 2. When each is required

- **A roadmap bullet: always.** Work that is not on the roadmap did not happen.
- **A spec: when there are design questions to settle.** An item with no open design
  question gets a bullet and a plan, not a spec. Do not write a spec as ceremony.
- **A plan: when the item starts, never before.** A plan written months early describes
  code that does not exist yet — it is fiction, and it will be wrong.
- **A design document: when a decision binds more than one item.** If two specs would
  otherwise each state the same rule, the rule belongs above both.

## 3. The Status header

Every spec, design document and standard opens with a header block:

```markdown
**Status:** Draft | Reviewed | Implemented | Superseded by <id>
**Kind:** implement | fix | refactor | feature | doc | investigate
**Roadmap:** ONEUP-NNNN
**Branch:** main | v2 | <branch name>
**Verified at:** <commit> — every figure below was measured against this tree, not recalled.
```

`Verified at` is not decoration. It is the only thing that lets a later reader know
whether a number is current. A document without it is assumed stale.

## 4. The spec template

Sections in this order. Skip one only when it would be empty, and say so rather than
leaving a heading with nothing under it.

1. **Goal** — one paragraph. What is true after this ships that is not true now.
2. **Background** — what is broken or missing today, with evidence from the tree.
3. **Scope decisions (agreed with the user)** — the choices that were preference, not
   deduction, and who made them. This is what stops the same argument being had twice.
4. **Design** — the mechanism. Cite real files and line numbers.
5. **Correctness invariants** — see §5.
6. **Failure modes** — what happens when each assumption breaks.
7. **Tests** — which test locks in which invariant, and where it lives.
8. **Docs & release** — what else must change when this ships (README, CHANGELOG,
   marker reference, the six version sites).
9. **Alternatives considered (and rejected)** — with the reason. A rejected option with
   no reason gets re-proposed in six months.
10. **Out of scope** — deliberately, so absence reads as a decision rather than an
    oversight.
11. **Cold-eyes loop log** — see §7.

## 5. Correctness invariants — the format

One canonical form, because tooling parses it and because a table cell cannot hold the
detail a real invariant needs:

```markdown
- **INV-1** Every focusable widget reports a non-empty accessible name or visible text.
  *Test:* `tests/gui-smoke.py` walks `findChildren(QWidget)`, keeps
  `focusPolicy() != Qt.NoFocus`, and asserts a name is present.
```

Rules:

- **Numbered `INV-N`, never renumbered.** If an invariant dies, mark it withdrawn; do not
  shuffle the others, because other documents cite them by number.
- **Every invariant names its test.** An invariant with no test is a wish. A spec that
  ships with an untested invariant is incomplete — that is the definition, not an opinion.
- **State it so it can fail.** "Handles errors gracefully" cannot fail a test. "A failed
  step is recorded, emits a plain-English hint, and the run continues to the next step"
  can.

## 6. The verification rule

**Every claim naming a function, file, line number, flag, marker, constant or version is
checked against the tree in the session it is written.** Not recalled, not inferred from
how the code probably works.

- Phrases that must stop you: *"I assume"*, *"presumably"*, *"this is probably how it
  works"*, *"the wiring likely does"*. Each is the signal to run a `grep`, not to keep
  typing.
- A claim that cannot be verified is **deleted**, not softened into a hedge.
- When the answer is not on disk — it concerns intent, scope, or preference — **ask**.
  Two lines of question cost less than a document built on a wrong premise.

The live example of why: the ONEUP-0054 draft cites 197 engine tests and 3,680 lines from
commit `ea51adc`. The real figures at `dbef1a8` are 205 and 3,719. Numbers rot silently,
which is what §3's `Verified at` line is for.

## 7. Review — the cold-eyes gate

**Every design document, spec, standard and reference goes through `/cold-eyes` and is
looped until a pass returns zero verified findings.** Implementation does not start
before that. Per-feature test contracts (`tests/features/*/spec.md`) are exempt — they are
too small to warrant it.

- **Run it before implementation, not after.** A spec is a contract for the implementer;
  if the contract is wrong, the implementation is wrong by construction.
- **Loop 2 and later run cold.** Do not brief the reviewer on earlier findings or fixes.
  A finding that does not resurface is the proof the fix held.
- **Verify each finding before acting on it.** A reviewer's claim is a hypothesis; check
  it against the tree like any other claim (§6).
- **Fix every actionable severity** — critical, high, medium, low. Only informational
  findings are left. A low finding that turns out to be wrong is **dropped explicitly**,
  with a line saying so — never silently filtered.
- **Write the log as the loops happen.** Back-filling it destroys the audit trail, which
  is the only evidence the review was real.

The log format:

```markdown
| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 3 high, 2 medium, 3 low | all fixed — see commit abc1234 |
| 2 | 2026-07-27 | none | converged |
```

## 8. Writing for a non-programmer

The primary reader is not a programmer. Accordingly:

- **Every roadmap bullet carries a `**Layman:**` line** — one sentence saying what the
  work means for someone using the app.
- **Every standard opens with one plain sentence** a non-programmer could act on.
- **Define jargon inline on first use**, or use a plainer word. "The window never runs
  with administrator powers" beats "the GUI is unprivileged".
- Short sentences. Concrete over abstract. Name the actual file or button.

This is a writing rule, not a dumbing-down rule: the technical content stays.

## 9. Keeping documents true

- **Correct a stale figure in the session you notice it**, not "later". Later does not
  arrive, and the next reader trusts the number.
- **Never rewrite `CHANGELOG.md` history.** Released entries are a record of what users
  received. Fix the wording of an unreleased entry freely; leave shipped ones alone.
- **A superseded document is marked, not deleted.** `Status: Superseded by <id>` at the
  top, so its citations still resolve and the reasoning stays readable.
- **When two documents disagree, the one higher in §1's table wins** — a standard beats a
  spec, a design beats a spec, and the loser is fixed immediately rather than noted.

## 10. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| — | — | *not yet run* | scheduled as batch 1 (`docs/plans/ONEUP-0057-documentation-set.md`, Task 10) |
