# Documentation Standard

**In one sentence:** every document here has one job, and this file says which job, so
nobody has to guess where a decision belongs or whether it has been reviewed.

**Status:** Draft
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `07a4b2d` — every path and claim below was checked against the tree on
2026-08-12, not recalled. **§1.2 is newer**: its heading measurement, the `languages/` list
and the `ants-v1` dialect declaration were measured against the tree and against
`~/.claude/standards/` on 2026-08-18.

**Applies to:** every document in the repository, including the component `README.md`
files under `packaging/obs/` and `screenshots/` (they follow §8's writing rules; they need
no Status header, because they document a directory rather than a decision).

**Sections:** 1 the documents · 2 when each is required · 3 the Status header · 4 the spec
template · 5 invariants · 6 verification · 6a citing code · 6b figures from the code · 7 the
review gate · 8 plain language · 9 keeping documents true · what checks this · 10 cold-eyes
log

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
| 7 | `~/.claude/standards/` | the global default set. It governs only where this project states nothing — §1.2 lists what OneUp owns and what it inherits. **One exception outranks this whole table:** `roadmap-format.md`'s bullet grammar, which no project may override (§1.2) |

`README.md`, `CHANGELOG.md` and `ROADMAP.md` are **descriptive, not authoritative** — they
record what is, what shipped and what is intended. A disagreement between one of them and a
rule above is a bug in the record, fixed by correcting the record.

**The loser is fixed immediately**, in the same session, not noted for later.

### 1.2 The global standards set, and what OneUp owns

`~/.claude/standards/` is the default set every project on this machine starts from. Its
`README.md` § *The three cases* is the binding rule. This section records which case each
OneUp standard takes, because nothing else in the repo does and it is not guessable from
the filenames.

**Same filenames as the global set** — `coding.md`, `dependencies.md`, `documentation.md`,
`security.md`, `testing.md`. The global README's test for "the project owns it outright" is
that the pair shares **zero `##` headings**. Measured 2026-08-18 (`comm` over the `^## `
lines):

| Pair | Shared `##` headings |
| --- | --- |
| `coding.md`, `documentation.md`, `testing.md` | 1 each — `What checks this` only |
| `dependencies.md` | 2 — `What checks this`, `Cold-eyes loop log` |
| `security.md` | 2 — `What checks this`, **and `8. Supply chain`** |

**No pair scores zero, and it cannot**: `§4` of this file requires every standard to carry
`## What checks this`, and the global standards carry it too, so the house format guarantees
one shared heading. Read literally the global test therefore classifies every conforming
project standard as a fork. That is a defect in the test, reported upstream 2026-08-18 and
not resolved here. **What is measured and what is claimed are separate**: four of the five
share nothing but structure and are project-owned; `security.md` also shares a content
heading and is the one genuine overlap.

**`security.md` §8 is a deferral, not a contradiction** — **`docs/standards/security.md`'s
own §8.1** sends version policy to `docs/standards/dependencies.md`, and the global §8's
first bullet routes it the same way. (Not *this* file's §8.1, which is a plain-language
rule.) The two do not disagree; they cover different ground under one title.

**And this is the exception to the displacement rule below.** `security.md` §8.1 declares
itself partial — *"This section covers only what is security-specific"* — so the global §8
still binds on the ground it does not cover: scanning for known vulnerabilities on a cadence,
and committing lockfiles. **A project section that declares itself partial does not displace
the global file; it narrows what it displaces.** Anyone changing a dependency or a CI action
reads both.

**Owned under a different filename.** The global set splits into `commits.md`,
`releases.md` and `changelog-format.md`; OneUp states those subjects in `workflow.md` — §3
commits, §5.2 the changelog, §8 releasing. This file's §4 is the spec template and §5 the
invariant format, which is what OneUp keeps of global `spec-format.md`. **OneUp pins no
plan shape**, and by the rule above that silence is not a displacement: global
`~/.claude/standards/spec-format.md` §8 does pin one — every step verified, no design
rationale, a `not started` / `in progress` / `done (DATE)` status vocabulary and a
**Definition of done** heading — and `~/.claude/standards/skeletons/plan-skeleton.md` is its
starting point. Both bind here until this file says otherwise.

**Displacement is per subject, not per rule.** Where a project file states a subject, it is
read as the whole rule on it — do not merge in the global file's extra clauses. Where the
project is silent, row 7 of §1.1 sends you to the global file. One divergence is deliberate
and recorded at its site: the release commit subject, `workflow.md` §3.

**Inherited, and NOT overridable.** `roadmap-format.md`'s bullet grammar. A parser reads it,
so the global README forbids a project inventing its own spelling; what a project may pick
is a *dialect* from the supported set. OneUp declares **`ants-v1`** in `ROADMAP.md`'s first
line (`<!-- ants-roadmap-format: 1 -->`), and `workflow.md` §4 states the bullet shape
locally. **This one rule outranks §1.1's whole table**, which row 7 says.

**Inherited, and it does NOT bind: the global set's first-line version marker.**
`~/.claude/standards/README.md` § *Versioning* says each standard carries one — the form is
an HTML comment reading `ants-coding-standards: 1` — and none of OneUp's nine does. Settled
2026-08-19 (ONEUP-0113) on the global README's own test, *does a parser bind to it?* The
only consumer on this machine is the `check-copied-standards` hook, and what it reads on a
**project** file is a mirror marker or an `OWNED-HERE` marker, never a version; the version
is what that check **strips from the owner's side** when it diffs a mirror
(§ *The public-repo mirror*). So it is the global set's own bookkeeping, and nothing would
read nine more of them. § *The three cases* names `wording-and-translation.md` — this
project's file, by name — as an example of a standard a project owns outright, and run
against OneUp on 2026-08-19 that hook reports `clean`: no standard here scores as a copy or
a partial, so none owes an `OWNED-HERE` marker either. **This is the first global rule
recorded here as not binding**, which is why it carries its evidence rather than a verdict.
The contrast with the paragraph above is the whole point: `ROADMAP.md` carries a first-line
marker because a parser reads it, and these nine carry none because nothing does.

**Global files this section does not place, and they still bind where OneUp is silent** —
`~/.claude/standards/languages/` (python, qt, cpp), `~/.claude/standards/domains/database.md`,
the three `~/.claude/standards/skeletons/`,
`~/.claude/standards/roadmap-store-decisions-2026-08-09.md`, `~/.claude/foundation.md`,
`~/.claude/workflow.md` and `~/.claude/CLAUDE.md` — whose rule 14 owns the review gate §7
invokes and the loop caps that gate runs to.

**The Python and Qt language files are the live ones, but they are already displaced in
part.** `coding.md` §1 is *"The Python floor: **3.13**"* and its §6 is *"Qt idioms (the GUI
half)"*, so the version floor and the Qt idioms are this project's and the global files add
nothing there. The floors agree rather than compete — global `python.md` reads *"Python 3.10
minimum unless the project pins higher"*. What is genuinely not restated here is **casing**,
and the retired Qt 5 spellings §6 does not list. Those have not been reconciled; treat them
as additional and ask rather than assume.

> **`workflow.md` is the same trap by filename rather than by section.** `~/.claude/workflow.md`
> exists and covers a different subject entirely — the states a project moves through — while
> this project's `docs/standards/workflow.md` covers branches, commits, versions and releasing.
> Neither displaces the other; they are unrelated documents that collide on a name.
>
> **A citation of `testing.md` §8 in this repo means THIS file's §8.** The section numbers do
> not correspond between the two sets and never did — global `testing.md` §8 is a conformance
> rule, ours is *"New in 2.0: unit tests become possible"*. A skill or document written
> against the global numbering will land on the wrong rule here. Read the section title, not
> the number.

**Why this is written down at all.** OneUp is a public repository, and an outside contributor
cannot open `~/.claude/`. Without this section they cannot tell which of these files is the
whole rule and which is a local half of something larger — and neither can a future session
holding both sets at once. The global README's § *The public-repo mirror* permits a marked
verbatim copy for exactly this reason; OneUp keeps none, because its standards are its own
rather than copies.

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
| `Draft` | written, not yet through `review-contract`. **Implementation may not start** (§7) |
| `Reviewed` | a `review-contract` pass converged. Ready to implement |
| `Implemented` | the work shipped; the document is now a record |
| `Superseded by <id>` | replaced. Kept, not deleted (§9) |

A document mid-review is `Draft`, and may carry a short note saying so — and **the note has
exactly one permitted spelling, `Draft — cold-eyes in progress`**, because
`tests/docs-check.py`'s `STATUS_RE` matches that literal and nothing else. It still names the
old gate; `review-contract` replaced it, and ONEUP-0100 owns the mismatch. Until that closes,
write the literal above or the bare `Draft` — anything else reds `local-CI.sh`.
It is never `Reviewed`.

**The `Status` line carries state, never history.** No loop counts, no dates, no findings:
those live in the log and nowhere else (§4, item 11). `Reviewed` is the whole value. If the
`Status` line and the log ever disagree, the log is right.

**This is prescriptive from 2026-07-26, not a description of the tree.** The five specs
written before it (`ONEUP-0018`, `0022`, `0025`, `0028`, `0054`) used their own shapes —
`Status: design`, `Status: Cold-eyes converged (2 loops — …)`, `Kind: accessibility` — and
none carried `Verified at:`. They are **grandfathered**: each is brought to this shape the
next time it is edited for another reason, not in a sweep. `ONEUP-0054` was the first, on
2026-07-27; the other four are still waiting for a reason.

**`Branch:` names the branch the *work* lands on, not the branch this file is committed
to.** They differ routinely and on purpose: every 2.0 document was written on `main` while
describing work that happens on `v2`. Say `main` only when the work itself lands there.

`Verified at` is not decoration. It is the only thing that lets a later reader know
whether a figure is current — and §6b says how each figure was counted, so re-checking one
is cheap. A document without `Verified at` is assumed stale. **The field has exactly one
name**: the design document spelled it `Baseline:` until 2026-07-26, and was renamed rather
than blessed, because one thing with two names is the beginning of two things.

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
section — numbered or not, following whatever scheme that document already uses
(`dependencies.md` numbers no heading at all). **A trailing `## Related` pointer list may
follow it**, as `security.md` does; `tests/docs-check.py` checks that the section is present,
not that it is last. A document subject to the §7 gate with no
loop-log section has not been through the gate.

**Every standard and reference also carries an unnumbered `## What checks this` section**,
immediately before the loop log, holding one table: each rule the document sets, and what
catches a breach of it. It is unnumbered so that adding it renumbered nothing (§9). A rule
whose row says *nothing yet* is honest and gets fixed; a rule with no row at all is a rule
nobody has thought about. `tests/docs-check.py` fails a standard that lacks the section.

**The right-hand cell says one of three things, and never blurs the first two:**

- **a gate** — the file that catches a breach, named exactly, plus the assertion or scenario
  if the file is large.
- **`nothing`, in bold, followed by why** — and a roadmap id when the gap is a defect rather
  than a limit of what a script can decide.
- **a gate, plus what that gate does not catch**, in the same cell — for a rule covered in
  part. The partly-gated rows need it, and the carve-out is the point of them: a partly-gated rule
  written as though fully gated is the "row that is wrong" this section warns about, and
  dropping the carve-out to fit one of the first two forms is how that happens.

Keep the row about the rule the *left* cell names. The 2026-07-26 review found a row that
said the GUI suite does not redirect `HOME` — it does; the engine suite is the one that does
not, and the row had borrowed the engine's roadmap id. Two rules, two failures, one row, and
the table read as authoritative while saying the opposite of the truth. **A row that is
wrong is worse than a row that is missing**, because the whole point of the section is that
it can be trusted without re-deriving it.

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

**This generalises past invariants, and it is the governing idea of the whole set: a rule
with no check is a wish.** Whether a rule holds is settled by whether something cheap
catches it failing, not by how firmly it is written. So every standard and reference carries
a **What checks this** section, immediately before its loop log (§4), naming what catches
each of its rules — and naming, in the same table, the rules nothing catches. An unchecked rule recorded as unchecked gets
fixed. An unchecked rule left silent reads as covered.

Which catcher to reach for is §7's ordering, and adding one is
`docs/standards/workflow.md` §6.1.

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
- **A gap is written as a sentence, never as a marker.** No `TODO`, `TBD`, `FIXME` or
  `XXX`. A marker is a claim nobody made: it names no question, so nobody can answer it,
  and it survives every review by looking like work already accounted for. Write what is
  not known and who has to decide it — §8.1's *say "I do not know" loudly*.
  `tests/docs-check.py` fails on a marker in any spec, standard, design document or
  reference.

The live example of why: the `ONEUP-0054` draft cited 197 engine tests and 3,680 lines,
measured at `ea51adc`. By `dbef1a8` neither figure held, and "tests" was the wrong noun
anyway. **Numbers rot silently** — no gate fails and no reader notices — which is why §6b
says to write most of them out of the document altogether, and why §3's `Verified at` dates
the ones that stay.

## 6a. Cite by name, never by line number

**A citation names a symbol or quotes a searchable anchor. It never points at a bare line
number.** Decided with the user, 2026-07-26.

<!-- docs-check: ignore-line-numbers — the Don't column has to show the banned form -->

| Don't | Do |
| --- | --- |
| `updater.py:3581` | `updater.py` — `Updater._center_child` |
| `update_system.sh:864` | `update_system.sh` — the held-lock hint, guarded by `lock_holder` |
| "the regex at `:927`" | "the `_ALIAS_RE` pattern" |
| "the comment at `:377-382`" | "the QSS (Qt stylesheet) comment beginning *\"The painted ToggleSwitch can't be reached by a stylesheet\"*" |

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
current. They do not belong in a standard, a reference, a spec, a design document,
`CLAUDE.md` or the roadmap.

**A count is a separate problem, and a worse one** — §6b, which says to keep most of them
out of a document entirely. A line number cannot even be rescued that way: it is stale the
moment someone adds an import above it, and it is stale while still looking exact.

## 6b. Figures counted from the code

**Most counts taken from the tree should not be in a document at all.** They are the fastest
thing here to go stale: a count of lines, tests, call sites or errors is wrong the next time
anyone edits the thing it counts, and it goes wrong **silently** — no gate fails, no reader
notices, and the number keeps being quoted because it looks precise. Decided with the user,
2026-07-26.

Four forms, best first. Use the highest one that still makes the point.

### 6b.1 No figure

**Ask what the reader does differently for knowing.** If the answer is nothing, cut it.
*"The engine suite has 2,041 lines and 205 assertions"* changes no decision anybody makes;
*"the engine suite asserts on the marker lines the engine prints"* is the whole of what a
reader needs. Most counts in a document are scene-setting, and scene-setting is exactly what
§8 says to cut.

### 6b.2 The shape, not the count

**A rule about "every" survives an edit; a rule about "all 47" does not.** Write the sweep,
not its current result.

`docs/standards/ui-and-accessibility.md` §2 got here first and says why: *"The sweep is the
rule; the current call count is not worth citing, because nothing pins it and the next widget
changes it."*

**A ratio is a shape too, and it is often the honest form.** *"`updater.py` is more than six
times the 600-line ceiling"* carries the whole argument for ONEUP-0034 and stays true through
any ordinary edit, where *"`updater.py` is 3,719 lines"* is wrong by the next commit and
carries no argument at all. Reach for the ratio whenever the *comparison* is the point.

### 6b.3 The command, not its output

**Where a reader really does want the number, give them the thing that prints it.** `Passed:
205` is stale the moment a test is added; *"`./local-CI.sh` prints the tally"* is correct
forever, and it is shorter.

### 6b.4 A measurement, in the past tense

When the figure is *evidence* — for a decision, a cost estimate, a bug — keep it, and write
it as **something that was measured**, not as something that is true:

| Rots | Does not rot |
| --- | --- |
| "there are 47 lint errors" | "measured at `58ea3bc`, adopting the config reported 47 errors" |
| "the GUI suite prints 33 teardown tracebacks" | "measured five times at `5e76cfb`: 33, 32, 33, 33, 33 — the count varies with teardown order" |
| "the engine makes 34 privileged calls" | "a full run once needed **seven** password prompts, which is what `sudo_capture` exists to prevent" |

The right-hand column is durable because each sentence is about **what happened**, and what
happened stays happened. The left-hand column claims a present state the document cannot
keep. Same numbers; one form is a fact and the other is a promise.

A figure kept under this rule states **how it was counted**, because a measurement nobody can
reproduce cannot be disagreed with, and a claim nobody can disagree with never gets checked —
it only gets re-copied:

- **Name the unit.** "Tests" is not a unit here. Scenarios, assertions, call sites, lines.
- **Name the command**, where one exists, short enough to paste.
- **Name what is excluded**, whenever the exclusion took a judgement — *"34 privileged calls
  = 14 `sudo_capture` call sites + 20 direct `sudo` at command position; the helper's own 2
  `sudo` lines are the helper, not call sites."*
- **Say when a grep is the wrong tool**, next to the figure, so a later reader cannot
  innocently "correct" it.

**The worst error this set has produced was not a stale number — it was an unnamed unit.**
The `ONEUP-0054` draft said **197 tests**. The tree held 76 scenarios and 205 assertions.
Nobody was wrong on purpose: "test" meant three different things and no document said which.

### 6b.5 What is exempt

A number that is **fixed by a contract** is not a measurement and does not rot — *provided
something fails when the tree stops matching it*. **That is the test**: if nothing fails when
the number goes wrong, it is a measurement, and §6b.1 to §6b.4 apply, however contractual it
feels.

Applying that test honestly to this project leaves **two** clear exemptions and two near
misses, and the near misses are the useful part:

| Number | Exempt? | Why |
| --- | --- | --- |
| The six version sites (`docs/standards/workflow.md` §5.1) | **yes** | `local-CI.sh`'s version-lockstep gate reads all six and fails on any disagreement |
| The marker **names** (`docs/reference/marker-protocol.md` §3) | **yes** | `tests/docs-check.py` compares the table against the engine's call sites, both ways |
| The marker **count** — "23 markers" | **no** | nothing reads the count. A marker added to the engine *and* the table agrees with itself, and every document quoting 23 goes quietly wrong |
| The Python floor (`docs/standards/coding.md` §1) | **no** | no `python_requires` is declared anywhere in the tree; that standard's own table says so. ONEUP-0063's `pyproject.toml` is what would make it exempt |

So write the count and the floor in §6b.4's form until something checks them. A number
nobody checks is a measurement wearing a contract's clothes.

## 7. Review — the cold-eyes gate

**Every design document, spec, standard and reference goes through `review-contract`, and is
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
- **The severity scale below is the OLD gate's, and `review-contract` does not emit one** —
  its findings carry the question they answer (`[Q1]`–`[Q4]`) instead. The mismatch reaches
  `tests/docs-check.py`, whose loop-log tally balances severity counts against dispositions,
  so a row written from a current run has to be worded to skip that check. **The compliant
  form is to leave the disposition clause unbolded** — `check_loop_tallies` skips a row only
  when no **bolded** span contains `<digits> verified|dismissed|info`, so
  `Q1 4 · Q2 1 · Q3 3 — all 8 verified, 0 dismissed` passes while `**8 verified**` fails.
  §10's newest rows are written that way. **ONEUP-0100 owns the mismatch itself**; renaming the gate here does not fix it, and this paragraph exists so the next reader
  is not left to rediscover why. Rows 7 and 8 of §10 were written under the old scale and
  stay as written — a loop log records what each pass found.
- **Fix every actionable severity** — critical, high, medium, low. Only informational
  findings are left. A low finding that turns out to be wrong is **dropped explicitly**,
  with a line saying so — never silently filtered.
- **Write the log as the loops happen.** Back-filling it destroys the audit trail, which
  is the only evidence the review was real.
- **The tally must balance.** A row saying 8 findings and 6 outcomes is a row where two
  findings were dropped without a decision. `tests/docs-check.py` fails on it.

  Two things about that check are worth knowing before you write a row, because both cost a
  red `local-CI.sh` on 2026-08-03:

  - **A dismissed finding still needs a severity.** The check compares the severity counts
    against *verified + dismissed*, so four findings you checked and dropped have to appear
    in the severity breakdown too. Writing `2 critical, 7 high, 8 medium, 5 low, 2 info —
    24 verified, 4 dismissed` fails: 24 findings against 28 outcomes. The dismissed four
    were all low, so `9 low` is what balances it.
  - **Do not bold a bare number in the Outcome cell.** The check pairs `**…**` spans across
    the whole row and then hunts `<number> verified|dismissed|info` inside them. A bolded
    decimal sitting near a bolded disposition word — `**0.069**` a few clauses before
    `**Dismissed: two.**` — pairs into one span and contributes a phantom `069 Dismissed`,
    which read as 105 outcomes against 36 findings. Leave measurements unbolded in that
    cell; bold the prose instead.

**Spend a cold reader only on what a script cannot do.** The catchers, cheapest first:

| Catcher | Cost | Use for |
| --- | --- | --- |
| a gate in `local-CI.sh` | seconds, every run, forever | anything countable or greppable |
| a checklist (the *Before you commit* section most standards carry; this one and `dependencies.md` do not) | a minute, when you remember | judgement a script cannot make, with a fixed trigger |
| a cold reader (`review-contract`) | a review pass | reasoning, contradictions, an approach that is wrong |
| the user | a bug report | the failure the first three missed |

Four of the six errors the first three loops found were countable: a marker table that would
have broken its own `grep` gate, a "four fields" list naming three, a loop tally of 8
findings against 6 outcomes, and a `Status` line carrying history in ten files. Each was paid
for at cold-reader prices. **When a reviewer or a human catches the same *class* twice, it
becomes a gate** — `docs/standards/workflow.md` §6.1 says how.

The log format:

```markdown
| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 3 high, 2 medium, 3 low | all fixed — see commit abc1234 |
| 2 | 2026-07-27 | none | converged |
```

### 7.1 A run-state note lives only as long as its run

A review stopped part-way may leave a hand-off note under `docs/reviews/` — where it
resumes, what the packet held, which findings are still open. **That note is deleted by the
commit that finishes the run.** Not archived, not left for reference.

The durable record is elsewhere: the loop log above, in the reviewed document, which
`tests/docs-check.py` checks — and the run's fix ledger, which **nothing checks**, because
no gate in this project scans `docs/reviews/` at all. A note that outlives its run
duplicates both while being gated like the weaker of them, so nothing makes it wrong out
loud when the code moves underneath it. **That the ledger is ungated is a reason to keep
`docs/reviews/` small, not a reason to keep the note**: two unchecked files rot faster than
one, and only the note claims to be a hand-off.

**The failure mode is not that it goes stale — it is that it goes stale while claiming to be
verified.** ONEUP-0072's own run-state note — deleted 2026-08-12 under this rule, which is
why no path is given for it — carried a *"Verified source facts worth carrying forward"*
section telling the next session to reuse its figures rather than re-derive them. One of
them counted the engine's `marker HINT` call sites, and 1.4.3 had already added four. The
note bought exactly the trust that stops anyone checking, which is worse than saying
nothing.

**Delete when the run ends, not when the session ends.** A run genuinely still in flight
needs its note — that is what the file is for, and the next session cannot resume without
it. What is forbidden is the note that survives its own run.

**A run abandoned rather than finished has ended too**, and it is the case that would
otherwise never trigger: there is no closing commit, and "still in flight" can be claimed
forever. The session that decides not to resume deletes the note, in that decision's commit.

**The two kinds of file under `docs/reviews/` are told apart by name, because they have
opposite lifetimes**: `<ID>-run-state.md` is the note and is deleted, `<ID>-fix-ledger.md`
is the ledger and is kept. A file there matching neither is a breach of this section — that
is the only way a later reader can tell a stray note from a ledger doing its job.

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
  standard is for, in words a non-programmer understands. `tests/docs-check.py` fails one
  that does not, so this is a gate rather than a habit.
- **Define jargon inline on first use**, or use a plainer word. "The window never runs
  with administrator powers" beats "the GUI is unprivileged".
- **Name the actual thing** — the file, the button, the command. Not "the relevant
  option".

This is a writing rule, not a dumbing-down rule: the technical content stays. Simplifying
the *language* is not the same as simplifying the *claim*, and where the two pull apart,
the claim wins — an accurate sentence that needs a technical word keeps the word and
explains it.

## 9. Keeping documents true

**One document owns each fact. Everywhere else points at it.** §1.1 settles a contradiction
after it exists, which is recovery. Not writing the fact twice is prevention, and it is the
cheaper of the two by a wide margin — you cannot contradict yourself about something you
said once.

Every contradiction the first review loop found existed because a fact lived in two places:
the privileged-call count in `security.md` and in the design document (21 of 22 against 14 of
34), and the cause of the GUI suite's teardown crash, given differently in two standards. A
pointer can go stale in exactly one way, and `tests/docs-check.py` catches **some** of it:
only a path containing a `/`, and only in a standard, the reference, `CLAUDE.md` or
`README.md`. Its `PATH_RE` requires the slash, so a bare `foo.py` — and the `security.md`
§9.6 form this section itself recommends — is caught by nothing, and no spec, plan or design
document is scanned. The hand search below is the only catcher there. A restatement can go
stale in every way, silently.

The owners: `docs/reference/` owns the marker contract, and each standard owns its own
subject. Where a second document needs the fact, it names the owner and the section — as
`security.md` §9.6 does for the test rules — rather than repeating the content. Restate a
fact only to make a *different* point with it, and say where it came from.

- **Changing a fact is not finished until you have searched for who cited it.** Fix document
  A, and document B — which quoted A's figure — is now wrong. B's bytes did not change, so a
  review pass that skips unchanged files never opens it, and the contradiction survives to
  `Reviewed`. Search the whole doc set for the figure, symbol or section you changed, in the
  same session. This applies to every edit, not only inside a `review-contract` run.
- **Renumbering is a blast radius, not a tidy-up.** Renaming a section or an `INV-N` breaks
  every citation of it. If you cannot fix all of them in the same session, do not renumber —
  which is why §6a and §6b are lettered rather than inserted as a new §7.
- **Correct a stale figure in the session you notice it**, not "later". Later does not
  arrive, and the next reader trusts the number.
- **Never rewrite `CHANGELOG.md` history.** Released entries are a record of what users
  received. Fix the wording of an unreleased entry freely; leave shipped ones alone.
- **A superseded document is marked, not deleted.** `Status: Superseded by <id>` at the
  top, so its citations still resolve and the reasoning stays readable.
- **When two documents disagree, §1.1's order settles it**, and the loser is fixed
  immediately rather than noted.

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §1.2 which standard governs a topic, and which global file still binds | **nothing** automatic — a cold reader. The heading measurement it records can be re-run (`comm` over `^## ` lines), but nothing checks that a reader consulted the right file of two with the same name, and nothing checks the `languages/` reconciliation it flags as outstanding |
| §1.1 the losing document is fixed in the same session | **nothing** automatic — a cold reader. The contradiction is what gets found; whether it was fixed then or noted for later is not visible to anything |
| §2 which document each kind of work requires | **nothing** automatic — a cold reader. Nothing can tell that a spec which should exist does not |
| §3 the header block, and the four `Status` values | `tests/docs-check.py` |
| §4 every standard carries this section and a loop log | `tests/docs-check.py` |
| §5 an invariant names its test | **nothing** automatic — a cold reader |
| §6 a claim is checked against the tree | **nothing** automatic. The review gate is the only catcher, which is why §7 is a gate and not advice |
| §6 no `TODO` / `TBD` / `FIXME` / `XXX` left in a document | `tests/docs-check.py` |
| §6a no `path:line` citation | `tests/docs-check.py`, over standards, reference and design — and **that is the whole of its reach**. `docs/specs/` is exempt until ONEUP-0065 converts the `path:line` citations the older specs carry; `CLAUDE.md` and `ROADMAP.md` are inside §6a.2's scope and are scanned by **nothing**, as is the prose form — *"around line 786"* |
| §6b most counts taken from the code stay out of the document | **nothing** automatic — a cold reader. ONEUP-0104 would gate it |
| §7 a loop tally balances | `tests/docs-check.py` |
| §7.1 a run-state note is deleted when its run ends | **nothing** automatic — whether a run has ended is not a fact on disk. The catcher is the closing commit itself; a later reader can only spot a breach by the `-run-state.md` name §7.1 pins |
| §7.1 a file under `docs/reviews/` is named `-run-state.md` or `-fix-ledger.md` | **nothing** automatic — no gate scans that directory at all, which is the same gap the row above rests on |
| §8.2 every standard opens with an `**In one sentence:**` line | `tests/docs-check.py` |
| §8 the rest of plain language | **nothing** automatic — a cold reader, and the author reading their own sentence as an opponent |
| §9 a pointer resolves | `tests/docs-check.py`, over the documents that describe the tree as it is: standards, reference, `CLAUDE.md`, `README.md`. A spec, design document or plan is excluded, because each legitimately names files it is going to create. **Only paths containing a `/` are checked** — a bare `foo.py` is not, because the same form is used for naming-pattern examples (`snake_case.py`), for 2.0 modules that do not exist yet, and for runtime files that are never in git. A renamed script therefore leaves residue this gate cannot see; the 2026-07-26 review found five such references after `check-docs.py` became `tests/docs-check.py` |
| §7 implementation does not start before the gate has run | `tests/docs-check.py` proves a gated document has a `Status` and a loop log — it cannot prove anyone **waited** for them. That half is **nothing** automatic |
| §8.2 every roadmap bullet carries a `**Layman:**` line | **nothing** automatic — `ROADMAP.md` is outside this gate's scope entirely, though the rule is mechanical enough to check |
| §9 never rewrite `CHANGELOG.md` history | **nothing** automatic — a released entry rewritten looks exactly like one written correctly the first time. Git history is the only record, and nothing reads it |
| §9 a superseded document is marked, not deleted | **nothing** automatic — a deleted file leaves nothing behind to check |
| §9 one owner per fact | **nothing** automatic. This is the gap the review loop exists to cover, and the most expensive one to leave uncovered. ONEUP-0105 would gate it |

**More than half these rows have nothing automatic behind them**, and that is the honest
state rather than a to-do list: a gate for *"is this claim true?"* would have to read the
code and decide. (The proportion is stated rather than counted on purpose — §6b's own rule.
The exact figure was written here twice and went stale both times, once within a single
session, because every row added to the table moves it.) Two are worth building anyway, because both would have caught errors this set has
actually produced — a check for a tree-derived count written in the present tense with no
command beside it (§6b, filed as **ONEUP-0104**), and a check for the same figure appearing
in two documents at once (§9, filed as **ONEUP-0105**). Both are approximations. Both are
cheaper than the review pass that currently catches
them.

## 10. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 12 | 2026-08-18 | 2 lanes, cold; genre standard; Q1 3 · Q2 5 · Q3 2 — all 10 verified, 0 dismissed, all fixed. Cap reached (3 for a standard); the run files its tail and exits (disposition clause unbolded per §7) | **Both lanes led with the same defect for the THIRD loop running, and it was mine every time.** §1.2 said the global Python and Qt language files carry *"a version floor, casing, current idioms and retired Qt 5 spellings that this project's `coding.md` does not restate"* — it restates two of the four: `coding.md` §1 is *The Python floor: **3.13*** and §6 is *Qt idioms*. Under §1.2's own displacement rule that made the section contradict itself about which Python the code may require. Narrowed to casing and the Qt 5 spellings §6 omits, with the floors recorded as agreeing rather than competing. **The rest of the loop was this run's own blast radius, which is the honest read of a section edited three times**: row 7 still said global governs *only* where the project is silent, after loop 2 added a partial-section rule that makes it govern more; the roadmap carve-out was scoped to §1.1's table but not to §1.2's displacement rule, so `workflow.md` §4 stating the grammar locally read as displacing a grammar a parser enforces; §1's `docs/plans/` row states the plan subject, which the displacement rule would read as the whole rule on plans against loop 2's finding that global `spec-format.md` §8 binds; and loop 2's residue list named two of global `security.md` §8's four bullets as complete, dropping *review what a new dependency actually is before adding it*, which neither project file covers. **The most consequential finding was about the gate itself, and it was live while the gate ran**: §7 said to loop *until a pass finds nothing substantive*, while `review-contract` caps at 3 for a standard and files its tail — which is exactly what this row is doing. §7 now states the cap and `~/.claude/CLAUDE.md` joins §1.2's unplaced list as the document that owns it. §7's gate list also omitted plans, which global rule 14 gates, and still told an author to *fix every actionable severity* under a gate that emits none. **Two lane open questions settled rather than filed**: §6a's `docs-check: ignore-line-numbers` pragma is section-scoped (`ignore` resets at the next heading), so §6a's own table is legitimately covered; and `security.md` really does carry `## Related` after its loop log — §4 now permits that tail, and the checker tests presence rather than position. `workflow.md` gains the same filename-collision warning `testing.md` §8 has. **Filed at the cap as ONEUP-0113**: the global README mandates a first-line version marker on every standard, the global files carry one and none of OneUp's nine does — a decision about scope, not a sweep, so it is filed rather than rushed. Status stays `Draft — cold-eyes in progress`: the run reached its cap rather than an empty loop. |
| 11 | 2026-08-18 | 2 lanes, cold; genre standard; Q1 4 · Q2 4 · Q3 1 — all 9 verified, 1 dismissed, all fixed (disposition clause left unbolded so §7's tally check skips it; ONEUP-0100) | **Both lanes led with the same defect for the second loop running, and it was mine again.** §1.2 said *"this file's §8.1 sends version policy to `dependencies.md`"* — but *this* file's §8.1 is a plain-language rule; the routing lives in `security.md`'s §8.1. A reader checking whether the one content-heading overlap was a real conflict landed on the wrong document, which is the single question §1.2 exists to answer. **Both lanes also found the displacement rule arguing with itself**: *"do not merge in the global file's extra clauses"* sat four lines from *"should read both"*, and global `security.md` §8 carries real obligations — lockfiles committed, scan on a cadence — that the project's §8 never restates. Resolved with a rule rather than a reword: **a project section that declares itself partial narrows what it displaces rather than displacing wholesale**, and `security.md` §8.1 does declare itself partial. The same rule then falsified a neighbouring claim of mine — *"OneUp pins no plan shape at all"* reads as settled, when by that rule the silence means global `spec-format.md` §8 binds, and it does pin one. **The two findings worth the loop were verified against the checker rather than inferred from it.** `PATH_RE` requires a `/`, so §9's own recommended pointer form — a bare filename plus §N — is caught by nothing, while §9 claimed `docs-check.py` catches staleness outright; and `STATUS_RE` permits exactly one note, `— cold-eyes in progress`, so the natural wording after loop 1's rename would have redded `local-CI.sh`. Loop 1 made that trap live and did not notice. **Loop 1's other unswept blast radius**: `CLAUDE.md` still called itself *the lowest-ranked document in the set* after row 7 was added beneath it. Also fixed: §7 told an author to word a row to skip the tally check without saying how, which this row now demonstrates; a written-down count of a current result (*"two rows below need it"*, and three take that form) deleted per §6b.2; and `roadmap-store-decisions-2026-08-09.md` was in neither of §1.2's lists. **Dismissed, one**: a lane reported `files-and-naming.md` carries no *Before you commit* section, so §7's exclusion list was short — it carries §8, *Quick check before you commit a new file*, under another title, and the list is correct. **Status: Reviewed → Draft** — the run has not returned an empty loop. |
| 10 | 2026-08-18 | 2 lanes, cold; genre standard; Q1 4 · Q2 1 · Q3 3 — all 8 verified, 0 dismissed, all fixed (no severity scale under the four-question gate, so nothing here for §7's tally check to balance; ONEUP-0100) | **Gate on a new §1.2 stating this project's relationship to `~/.claude/standards/`, and both lanes led with the same defect — mine.** §1.2 claimed the five same-named pairs share **zero content headings**, false for `security.md`: both files carry `## 8. Supply chain`. It also quietly reworded the global test from *zero `##` headings* to *zero content headings*, narrowing the rule it cited. §1.2 now prints the per-pair measurement, states that NO pair can score zero because this file's own §4 mandates `## What checks this` on every standard, and records that `security.md`'s overlap is a deferral rather than a contradiction — its §8.1 and the global §8 route version policy to the same place. **The second, also found by both lanes, was a contradiction I introduced**: §1.1's new row 7 said the global set governs *only where this project states nothing*, while §1.2 said `roadmap-format.md`'s bullet grammar is not overridable at all — and `workflow.md` §4 states that grammar locally, so a conformer adding a trailer was conforming and in breach at once. Row 7 now carries the carve-out. **The most valuable finding was pre-existing**: this standard mandated `/cold-eyes` in five live places and that skill does not exist — `review-contract` replaced it on 2026-08-12. The `Draft` and `Reviewed` statuses §3 defines were keyed to an uninvocable gate. Seven invocations across three standards are renamed; loop-log rows and the section name are left as written. Renaming it exposed the severity mismatch ONEUP-0100 already owns, which §7 now states rather than leaving to be rediscovered. Also fixed: §1.2 claimed the plan format lives in §§4-5 and no plan shape is stated anywhere; it omitted `~/.claude/standards/languages/`, which binds a Python and PySide6 project through row 7 and has never been reconciled against this project's `coding.md`; it had no **What checks this** row, which §4 calls a rule nobody has thought about; and the header claimed every claim below was checked on 2026-08-12 while §1.2's measurements are 2026-08-18. |
| 9 | 2026-08-12 | 2 lanes, third and final loop of this run (the default cap): Q1 1 · Q2 3 · Q3 2 — 6 verified, 0 dismissed, of which **only one** was the previous loop's collateral | **Stopped at the cap with findings still arriving, and that is the result worth recording.** The one collateral was mine and the fix was deletion: loop 8's re-stamped `Verified at:` line had grown a clause naming the two review loops behind it, which §3 forbids outright — history lives in the log and nowhere else. The five pre-existing were all §4's own rules failing in the document that sets them, the same shape as loop 8's: §4 said a What-checks-this cell "says one of **two** things, and never blurs them" while two of this table's rows have always needed a third — a gate **plus** what it does not catch — so an author following §4 would drop an honest carve-out and leave a partly-gated rule reading as covered (§4 now permits the third form and says why); §4 called the loop log the "last **numbered** section" when `dependencies.md`, the one standard that numbers no heading at all, has never had one; §6a.2's scope list omitted a reference while the gate has always scanned `docs/reference/`, so a maintainer reading the rule could have narrowed the check and silently un-gated the highest-ranked document class; the §6a row implied its gate reached everything in that scope, while `CLAUDE.md` and `ROADMAP.md` are scanned by nothing; and four more rules had no row at all — §7's own "implementation does not start before that", §8.2's `**Layman:**` line, and both of §9's (never rewrite CHANGELOG history, mark a superseded document rather than delete it). The table went 12 rows to 20 across this run. **The proportion form earned itself**: the sentence beneath it still reads true at 12 of 20 without being touched, where a figure would have gone stale a third time. Fixed in passing, below finding threshold: the `TODO` row named three markers where the rule and `MARKER_RE` both have four. **Filed rather than looped: ONEUP-0107** — 13 pre-existing defects in two loops of a document eight loops had already passed says the four-question gate finds a different class than the severity gate did, and the other eight standards have not been read under it. |
| 8 | 2026-08-12 | 2 lanes, second loop of the §7.1 amendment review: Q1 3 · Q2 3 · Q3 1 — 7 verified, 1 dismissed, of which only 2 were the previous loop's collateral | **Five of the seven were pre-existing, in a document seven loops had already passed** — which is what a differently-shaped gate is for, not evidence the earlier loops were careless. The two that were mine: the header still said every claim was verified at `58ea3bc` on 2026-07-26 while §7.1 had been measured 17 days later (§3 makes that field the only signal a figure is current, so it was actively misleading), and the §8 row still said **nothing** automatic after loop 7 gave §8.2's opener a gate — §4 calls that shape "worse than a row that is missing". The pre-existing five: §7's worked example for the tally check computed `24 verified + 4 dismissed` as **26** where it is 28, so an author debugging a red gate would have worked the example and mistrusted themselves or balanced to the wrong total; §6b.5's prose said **one** clear exemption over a table with two; §4 and §5 gave the document set two different layouts (loop log last vs What-checks-this last) and §5 now defers to §4; §7's catcher table claimed each standard has a *Before you commit* section when this one and `dependencies.md` do not; and the What-checks-this table had no row at all for §1.1 or §2, which §4 itself calls "a rule nobody has thought about". **Dismissed: one** — that the log-format example states no verified/dismissed counts. Checked against `check_loop_tallies`: a row with no numeric disposition clause is skipped, not failed, so the example is valid as written. The table's own row-count sentence was **converted to a proportion rather than re-numbered**: the exact figure was written twice and went stale both times inside one session, which is §6b's rule applied to the document that states it. Swept `CLAUDE.md`, which made the same layout claim §5 did, and corrected it there. |
| 7 | 2026-08-12 | 2 lanes, amendment review for the new §7.1, under the four-question gate — no severity scale, so nothing here for §7's tally check to balance (ONEUP-0100): Q1 1 · Q2 3 · Q3 2, all 6 verified, 0 dismissed | **Half the findings were in the new section and half were things it walked past.** Both lanes independently led with the same Q1: §7.1 said the durable record "is already checked", naming the loop log *and* the run's fix ledger — and no gate in this project scans `docs/reviews/` at all, so the ledger is checked by nothing. A conformer would have deleted the note believing the surviving ledger was gated, keeping exactly the unchecked artefact the rule was written to remove. It now says which half is checked and which is not, and turns that into a reason to keep the directory small. Two contract gaps in the new rule: an **abandoned** run has neither a closing commit nor "still in flight" status, so the note could sit forever with nobody able to show a breach — an abandoned run now ends in the session that decides not to resume; and `docs/reviews/` holds two file kinds with opposite lifetimes and no way to tell them apart, so the names are pinned (`-run-state.md` deleted, `-fix-ledger.md` kept). The three the lanes found *outside* the amendment were all §4's own form being broken by the document that states it: `nothing` unbolded in all six cells (now bolded — and **ONEUP-0106** files the same breach across the other eight standards, where a rule nothing obeys is more likely wrong than eight documents are); a required roadmap id missing from the two cells this document itself calls buildable gates (filed as **ONEUP-0104** and **ONEUP-0105**); and two present-tense tree counts breaching §6b — *"All nine do"*, which is really a gate and now says so, and §6a's *"62 citations"*, which the tree had already moved to 65. Blast-radius sweep found the plan for ONEUP-0057 still opening by sending the reader to ONEUP-0072's run-state note — the file this very rule had just had deleted, so no path for it is given here either; repointed at the spec's own loop log. Lane open question, verified and filed as **ONEUP-0103**: `/cold-eyes` no longer exists on this machine, and 25 files here still send a reader to it. |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: the tie-break rule contradicted §1's table, the header block was missing from the standard that mandates it, the `Status`/`Kind` enums matched no document in the tree, and "standards never hold anything version-specific" contradicted six of the nine |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | 5 high, 4 medium, 7 low — **all verified** | §8 (plain language) was added at the user's request and re-reviewed on its own. The section did not obey itself: its showcase example inverted the very error it described, and it used semicolons in the paragraph banning them. Also fixed set-wide: the `Status` line carried loop history that §4 item 11 reserves for the log (ten files), §7 defined convergence as zero findings when the practice is zero *substantive* findings, and §3 claimed no pre-existing spec carries `Branch:` (ONEUP-0054 does) |
| 4 | 2026-07-26 | none | clean. Skipped in the next pass — its bytes were unchanged, so the same cold read could not surface anything new. |
| 5 | 2026-07-26 | 1 medium — **1 verified** | the What-checks-this table cited §6 for a `TODO`/`TBD` rule §6 never stated. The gate existed; the rule was implicit. Now written into §6. |
| 6 | 2026-07-26 | 2 medium — **2 verified** | converged (polish only). `QSS` was used undefined, against this file's own §8.2; and §6b.4's second example was a ratio, not a past-tense measurement, while the prose beneath claimed every row was 'about what happened'. The ratio moved to §6b.2, where it demonstrates the right rule. |
