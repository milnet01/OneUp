# Documentation Standard

**In one sentence:** every document here has one job, and this file says which job, so
nobody has to guess where a decision belongs or whether it has been reviewed.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every path and claim below was checked against the tree on
2026-07-26, not recalled.

**Applies to:** every document in the repository, including the component `README.md`
files under `packaging/obs/` and `screenshots/` (they follow §8's writing rules; they need
no Status header, because they document a directory rather than a decision).

**Sections:** 1 the documents · 2 when each is required · 3 the Status header · 4 the spec
template · 5 invariants · 6 verification · 6a citing code · 7 the review gate · 8 plain
language · 9 keeping documents true · 10 cold-eyes log

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
| `docs/standards/` | everyone | standing rules that outlive any one item | release *status* — what shipped, what is in progress |
| `docs/reference/` | both halves of the app | frozen contracts — formats, protocols | rules or rationale |

**The distinction that matters most:** a *standard* is a rule that applies to work not yet
imagined; a *spec* is a contract for one piece of work. If a sentence would still be true
after 2.0 ships, it is a standard.

**A standard may name a release; it may not track one.** "2.0 adds a `pyproject.toml`
carrying this rule set" is a standing rule with a date attached — it stays true afterwards,
because the rule set is the point. "ONEUP-0063 is in progress" is status, and belongs on
the roadmap. The test: *after 2.0 ships, does deleting this sentence lose a rule?* If yes,
it is a standard.

### 1.1 Which document wins

When two documents disagree, this order settles it — **highest first**:

| # | Document | Why it ranks there |
| --- | --- | --- |
| 1 | `docs/reference/` | a frozen contract. Both halves of the app are built against it, so it cannot bend to any one of them |
| 2 | `docs/standards/` | standing rules. A spec that breaks one is wrong, not an exception |
| 3 | `docs/design/` | programme decisions, binding on the items inside that programme |
| 4 | `docs/specs/` | one item's contract |
| 5 | `docs/plans/` | one item's build steps |
| 6 | `CLAUDE.md` | a map and a trap list; where it restates a rule, the standard is canonical |

`README.md`, `CHANGELOG.md` and `ROADMAP.md` are **descriptive, not authoritative** — they
record what is, what shipped and what is intended. A disagreement between one of them and a
rule above is a bug in the record, fixed by correcting the record.

**The loser is fixed immediately**, in the same session, not noted for later.

## 2. When each is required

- **A roadmap bullet: always.** Work that is not on the roadmap did not happen.
- **A spec: when there are design questions to settle.** An item with no open design
  question gets a bullet and a plan, not a spec. Do not write a spec as ceremony.
- **A plan: when the item starts, never before.** A plan written months early describes
  code that does not exist yet — it is fiction, and it will be wrong.
- **A design document: when a decision binds more than one item.** If two specs would
  otherwise each state the same rule, the rule belongs above both.

## 3. The Status header

Every spec, design document, standard and reference opens with a header block:

```markdown
**Status:** Draft | Reviewed | Implemented | Superseded by <id>
**Kind:** implement | fix | refactor | feature | doc | investigate | accessibility |
          programme-design | reference
**Roadmap:** ONEUP-NNNN
**Branch:** main | v2 | <branch name>
**Verified at:** <commit> — every figure below was measured against this tree, not recalled.
```

**The four `Status` values mean exactly this**, because the word "reviewed" is otherwise
read two ways:

| Value | Means |
| --- | --- |
| `Draft` | written, not yet through `/cold-eyes`. **Implementation may not start** (§7) |
| `Reviewed` | a `/cold-eyes` pass converged. Ready to implement |
| `Implemented` | the work shipped; the document is now a record |
| `Superseded by <id>` | replaced. Kept, not deleted (§9) |

A document mid-review is `Draft`, and may carry a short note saying so — `Draft —
cold-eyes in progress`. It is never `Reviewed`.

**The `Status` line carries state, never history.** No loop counts, no dates, no findings:
those live in the log and nowhere else (§4, item 11). `Reviewed` is the whole value. If the
`Status` line and the log ever disagree, the log is right.

**This is prescriptive from 2026-07-26, not a description of the tree.** The five specs
written before it (`ONEUP-0018`, `0022`, `0025`, `0028`, `0054`) use their own shapes —
`Status: design`, `Status: Cold-eyes converged (2 loops — …)`, `Kind: accessibility`. Only
`ONEUP-0054` carries `Branch:`; none carries `Verified at:`. They are **grandfathered**:
each is brought to this shape the next time it is edited for another reason, not in a
sweep.

`Verified at` is not decoration. It is the only thing that lets a later reader know
whether a number is current. A document without it is assumed stale. The design document
spells it `Baseline:`; that is the same field under an older name.

## 4. The spec template

Sections in this order. Skip one only when it would be empty, and say so rather than
leaving a heading with nothing under it.

1. **Goal** — one paragraph. What is true after this ships that is not true now.
2. **Background** — what is broken or missing today, with evidence from the tree.
3. **Scope decisions (agreed with the user)** — the choices that were preference, not
   deduction, and who made them. This is what stops the same argument being had twice.
4. **Design** — the mechanism. Cite real files and symbols (§6a).
5. **Correctness invariants** — see §5.
6. **Failure modes** — what happens when each assumption breaks.
7. **Tests** — which test locks in which invariant, and where it lives.
8. **Docs & release** — what else must change when this ships (README, CHANGELOG,
   marker reference, the six version sites).
9. **Alternatives considered (and rejected)** — with the reason. A rejected option with
   no reason gets re-proposed in six months.
10. **Out of scope** — deliberately, so absence reads as a decision rather than an
    oversight.
11. **Cold-eyes loop log** — see §7. This is the *only* home for the loop history; the
    `Status` line names the current state and never the loops that got there.

**Every standard and reference carries a `Cold-eyes loop log` section too**, as its last
numbered section. A document subject to the §7 gate with no loop-log section has not been
through the gate.

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

**Every claim naming a function, file, flag, marker, constant or version is checked against
the tree in the session it is written.** Not recalled, not inferred from how the code
probably works. (How to *write* the citation — by name, never by line number — is §6a.)

- Phrases that must stop you: *"I assume"*, *"presumably"*, *"this is probably how it
  works"*, *"the wiring likely does"*. Each is the signal to run a `grep`, not to keep
  typing.
- A claim that cannot be verified is **deleted**, not softened into a hedge.
- When the answer is not on disk — it concerns intent, scope, or preference — **ask**.
  Two lines of question cost less than a document built on a wrong premise.

The live example of why: the ONEUP-0054 draft cites 197 engine tests and 3,680 lines from
commit `ea51adc`. Measured at `dbef1a8` the figures were 205 assertions and 3,719 lines —
and "tests" was the wrong noun anyway; `docs/standards/testing.md` §1 is canonical (76
scenarios, 205 assertions). Numbers rot silently,
which is what §3's `Verified at` line is for.

## 6a. Cite by name, never by line number

**A citation names a symbol or quotes a searchable anchor. It never points at a bare line
number.** Decided with the user, 2026-07-26.

| Don't | Do |
| --- | --- |
| `updater.py:3581` | `updater.py` — `Updater._center_child` |
| `update_system.sh:864` | `update_system.sh` — the held-lock hint, guarded by `lock_holder` |
| "the regex at `:927`" | "the `_ALIAS_RE` pattern" |
| "the comment at `:377-382`" | "the QSS comment beginning *\"Keyboard focus reuses the HOVER look\"*" |

**Why a line number is worse than no locator at all:** it looks precise, so a reader trusts
it, and it is wrong after any edit *above* it — an edit that need not have touched the cited
code at all. A wrong-but-confident pointer costs more than an approximate one, because the
reader follows it, finds unrelated code, and either believes the document is describing that
code or concludes the whole document is stale.

**Why now specifically:** 2.0 splits `updater.py` into `oneup/gui/` and replaces
`update_system.sh` with `oneup/engine/`. Every line number in every document will not merely
drift — it will point into a file that no longer exists. A symbol name mostly survives that
move; where it does not, the rename is a real change worth noticing.

### 6a.1 When there is no symbol to name

Some things genuinely have no enclosing function — a QSS rule inside a template string, a
header comment, a `case` arm, a constant list. Cite them by **quoting enough text to
`grep` for**, in preference order:

1. **The nearest enclosing symbol**, plus what to look for inside it.
2. **A short verbatim quote** of the line itself — six or eight distinctive words is plenty.
3. **A stable named anchor** — a marker name, a QSS selector (`QPushButton#GhostBtn:focus`),
   an environment variable, a step key.

A citation is well-formed when a reader can find the code with one search and no guessing.

### 6a.2 What line numbers are still for

Nothing durable. They are fine in a **commit message**, a **review comment**, or a
**conversation** — all three are pinned to a moment in time and are never re-read as
current. They do not belong in a standard, a spec, a design document, `CLAUDE.md` or the
roadmap.

**Counts and measurements keep working the same way** — "205 engine tests", "0 directional
QSS properties" — because §3's `Verified at` header dates them. A line number has no such
defence: it is stale the moment someone adds an import.

## 7. Review — the cold-eyes gate

**Every design document, spec, standard and reference goes through `/cold-eyes`, and is
looped until a pass finds nothing substantive left.** Implementation does not start before
that.

**Converged means one of two things**, and the distinction matters because chasing the
first one forever is its own waste:

- **Clean** — the pass returned zero verified findings.
- **Polish only** — everything it verified was precision: wording, an exact citation, a
  stale parenthetical. Nothing structural, nothing that changes a mechanism or a contract.
  Fix the polish and stop; another loop to re-check wording buys nothing.

Keep looping while any verified finding is **substantive** — a missing section, a claim the
code contradicts, or an approach that is itself wrong. Should the project ever adopt per-feature test contracts (a `spec.md` beside
a test), those are exempt — they are too small to warrant it. OneUp has none today.

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

## 8. Plain language

### 8.1 Write it so it can be checked

**Plain, short, direct — because a sentence nobody can check is a sentence nobody checks.**
This is a correctness rule wearing a style rule's clothes. Every review is somebody
deciding, sentence by sentence, whether a claim is true. A sentence that has to be read
twice does not get that decision made. It gets skipped, and whatever is wrong inside it
survives.

The rules:

- **One sentence, one claim.** A sentence doing two jobs can be half-wrong and still look
  right.
- **Say the rule, then the reason.** Not a run-up to the point — the point, then why.
- **Short sentences.** If it needs a semicolon and two clauses, it is two sentences.
- **The shorter word, and the concrete noun.** "Uses" beats "utilises". `bump.py` beats
  "the version tooling".
- **No hedge you cannot check.** "Generally", "should usually", "where appropriate" —
  each one means the reader decides, and two readers will decide differently. Either it is
  the rule or it is not. If a real exception exists, name it.
- **Cut anything that does not change what the reader does.** Length is not thoroughness.
  A rule buried in three paragraphs of preamble is a rule that will be missed.
- **The shortest version that is still complete** — not simply the shortest. Cutting a
  qualifier that carried a real exception is not concision. It is a new bug with fewer
  words.
- **Read your own sentence as an opponent would.** If it can be read two ways, it will be.
  Fix it now, while you still know which one you meant.
- **Say "I do not know" loudly.** An open question written plainly — *"the field layout is
  pinned nowhere"* — gets answered. The same gap written as a hedge reads as settled and
  never gets looked at. Silence and vagueness are the same failure. This does not compete
  with §6: ask first, and delete a claim you cannot verify. Write the gap into the document
  only when the answer is nobody's to give yet.

**The evidence is in this file's own §10.** The first cold-eyes loop found that the old
tie-break rule contradicted itself. It read *"the one higher in §1's table wins — a
standard beats a spec"*. Those two halves disagree. §1's table is ordered by audience, so
"higher in the table" actually made a spec beat a standard, and the README beat everything.
The gloss said what the author meant. The rule said something else, and the gloss was
comfortable enough that nobody checked. Stated as the ordered list it is now (§1.1), the
error would have been visible on the first reading.

**This applies to a review comment as much as a document.** A finding written as *"the
sudo count in the security standard may not be consistent with the tree"* cannot be acted
on. *"`security.md` §1.2 says 21 of 22 calls go through `sudo_capture`. The tree has 14 of
34"* can. That is the real finding from the first loop, in its original wording — and it is
why `security.md` §1.2 now reads 34 and 14.

**The same instinct already runs through the rest of the set.** §6 deletes a claim it
cannot verify rather than softening it. `docs/standards/coding.md` §4 puts a soft ceiling
on a module at what a reader can hold in their head. `docs/standards/testing.md` §3 makes a
mock exit **99** rather than fail quietly. Same rule, three subjects: be simple, be
explicit, make the wrong thing loud.

### 8.2 Writing for a non-programmer

The primary reader is not a programmer. Accordingly:

- **Every roadmap bullet carries a `**Layman:**` line** — one sentence saying what the
  work means for someone using the app.
- **Every standard opens with a single `**In one sentence:**` line** saying what the
  standard is for, in words a non-programmer understands. All nine do.
- **Define jargon inline on first use**, or use a plainer word. "The window never runs
  with administrator powers" beats "the GUI is unprivileged".
- **Name the actual thing** — the file, the button, the command. Not "the relevant
  option".

This is a writing rule, not a dumbing-down rule: the technical content stays. Simplifying
the *language* is not the same as simplifying the *claim*, and where the two pull apart,
the claim wins — an accurate sentence that needs a technical word keeps the word and
explains it.

## 9. Keeping documents true

- **Correct a stale figure in the session you notice it**, not "later". Later does not
  arrive, and the next reader trusts the number.
- **Never rewrite `CHANGELOG.md` history.** Released entries are a record of what users
  received. Fix the wording of an unreleased entry freely; leave shipped ones alone.
- **A superseded document is marked, not deleted.** `Status: Superseded by <id>` at the
  top, so its citations still resolve and the reasoning stays readable.
- **When two documents disagree, §1.1's order settles it**, and the loser is fixed
  immediately rather than noted.

## 10. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: the tie-break rule contradicted §1's table, the header block was missing from the standard that mandates it, the `Status`/`Kind` enums matched no document in the tree, and "standards never hold anything version-specific" contradicted six of the nine |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | 5 high, 4 medium, 7 low — **all verified** | §8 (plain language) was added at the user's request and re-reviewed on its own. The section did not obey itself: its showcase example inverted the very error it described, and it used semicolons in the paragraph banning them. Also fixed set-wide: the `Status` line carried loop history that §4 item 11 reserves for the log (ten files), §7 defined convergence as zero findings when the practice is zero *substantive* findings, and §3 claimed no pre-existing spec carries `Branch:` (ONEUP-0054 does) |
