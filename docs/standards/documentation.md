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
written before it (`ONEUP-0018`, `0022`, `0025`, `0028`, `0054`) used their own shapes —
`Status: design`, `Status: Cold-eyes converged (2 loops — …)`, `Kind: accessibility` — and
none carried `Verified at:`. They are **grandfathered**: each is brought to this shape the
next time it is edited for another reason, not in a sweep. `ONEUP-0054` was the first, on
2026-07-27; the other four are still waiting for a reason.

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
numbered section. A document subject to the §7 gate with no loop-log section has not been
through the gate.

**Every standard and reference also carries an unnumbered `## What checks this` section**,
immediately before the loop log, holding one table: each rule the document sets, and what
catches a breach of it. It is unnumbered so that adding it renumbered nothing (§9). A rule
whose row says *nothing yet* is honest and gets fixed; a rule with no row at all is a rule
nobody has thought about. `tests/docs-check.py` fails a standard that lacks the section.

**The right-hand cell says one of two things, and never blurs them:**

- **a gate** — the file that catches a breach, named exactly, plus the assertion or scenario
  if the file is large.
- **`nothing`, in bold, followed by why** — and a roadmap id when the gap is a defect rather
  than a limit of what a script can decide.

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
catches it failing, not by how firmly it is written. So every standard and reference ends
with a **What checks this** section naming what catches each of its rules — and naming, in
the same table, the rules nothing catches. An unchecked rule recorded as unchecked gets
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
| "the comment at `:377-382`" | "the QSS (Qt stylesheet) comment beginning *\"Keyboard focus reuses the HOVER look\"*" |

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

A number that is **fixed by a contract** is not a measurement and does not rot: the six
version sites (`docs/standards/workflow.md` §5.1), the marker table
(`docs/reference/marker-protocol.md` §3), the Python floor. Each is a decision rather than an
observation, and each has a gate that fails when the tree stops matching it. **That is the
test**: if nothing fails when the number goes wrong, it is a measurement, and §6b.1 to §6b.4
apply.

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
- **The tally must balance.** A row saying 8 findings and 6 outcomes is a row where two
  findings were dropped without a decision. `tests/docs-check.py` fails on it.

**Spend a cold reader only on what a script cannot do.** The catchers, cheapest first:

| Catcher | Cost | Use for |
| --- | --- | --- |
| a gate in `local-CI.sh` | seconds, every run, forever | anything countable or greppable |
| a checklist (each standard's *Before you commit*) | a minute, when you remember | judgement a script cannot make, with a fixed trigger |
| a cold reader (`/cold-eyes`) | a review pass | reasoning, contradictions, an approach that is wrong |
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

**One document owns each fact. Everywhere else points at it.** §1.1 settles a contradiction
after it exists, which is recovery. Not writing the fact twice is prevention, and it is the
cheaper of the two by a wide margin — you cannot contradict yourself about something you
said once.

Every contradiction the first review loop found existed because a fact lived in two places:
the privileged-call count in `security.md` and in the design document (21 of 22 against 14 of
34), and the cause of the GUI suite's teardown crash, given differently in two standards. A
pointer can go stale in exactly one way, and `tests/docs-check.py` catches it. A restatement can go
stale in every way, silently.

The owners: `docs/reference/` owns the marker contract, and each standard owns its own
subject. Where a second document needs the fact, it names the owner and the section — as
`security.md` §9.6 does for the test rules — rather than repeating the content. Restate a
fact only to make a *different* point with it, and say where it came from.

- **Changing a fact is not finished until you have searched for who cited it.** Fix document
  A, and document B — which quoted A's figure — is now wrong. B's bytes did not change, so a
  review pass that skips unchanged files never opens it, and the contradiction survives to
  `Reviewed`. Search the whole doc set for the figure, symbol or section you changed, in the
  same session. This applies to every edit, not only inside a `/cold-eyes` run.
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
| §3 the header block, and the four `Status` values | `tests/docs-check.py` |
| §4 every standard carries this section and a loop log | `tests/docs-check.py` |
| §5 an invariant names its test | nothing automatic — a cold reader |
| §6 a claim is checked against the tree | nothing automatic. `/cold-eyes` is the only catcher, which is why §7 is a gate and not advice |
| §6 no `TODO` / `TBD` / `FIXME` left in a document | `tests/docs-check.py` |
| §6a no `path:line` citation | `tests/docs-check.py`, over standards, reference and design. `docs/specs/` is exempt until ONEUP-0065 converts the 62 citations the four older specs carry. The prose form — *"around line 786"* — is caught by nobody |
| §6b most counts taken from the code stay out of the document | nothing automatic — a cold reader |
| §7 a loop tally balances | `tests/docs-check.py` |
| §8 plain language | nothing automatic — a cold reader, and the author reading their own sentence as an opponent |
| §9 a pointer resolves | `tests/docs-check.py`, over the documents that describe the tree as it is: standards, reference, `CLAUDE.md`, `README.md`. A spec, design document or plan is excluded, because each legitimately names files it is going to create. **Only paths containing a `/` are checked** — a bare `foo.py` is not, because the same form is used for naming-pattern examples (`snake_case.py`), for 2.0 modules that do not exist yet, and for runtime files that are never in git. A renamed script therefore leaves residue this gate cannot see; the 2026-07-26 review found five such references after `check-docs.py` became `tests/docs-check.py` |
| §9 one owner per fact | nothing automatic. This is the gap the review loop exists to cover, and the most expensive one to leave uncovered |

**Five of the eleven rows have nothing automatic behind them**, and that is the honest state
rather than a to-do list: a gate for *"is this claim true?"* would have to read the code and
decide. Two are worth building anyway, because both would have caught errors this set has
actually produced — a check for a tree-derived count written in the present tense with no
command beside it (§6b), and a check for the same figure appearing in two documents at once
(§9). Both are approximations. Both are cheaper than the review pass that currently catches
them.

## 10. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: the tie-break rule contradicted §1's table, the header block was missing from the standard that mandates it, the `Status`/`Kind` enums matched no document in the tree, and "standards never hold anything version-specific" contradicted six of the nine |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | 5 high, 4 medium, 7 low — **all verified** | §8 (plain language) was added at the user's request and re-reviewed on its own. The section did not obey itself: its showcase example inverted the very error it described, and it used semicolons in the paragraph banning them. Also fixed set-wide: the `Status` line carried loop history that §4 item 11 reserves for the log (ten files), §7 defined convergence as zero findings when the practice is zero *substantive* findings, and §3 claimed no pre-existing spec carries `Branch:` (ONEUP-0054 does) |
| 4 | 2026-07-26 | none | clean. Skipped in the next pass — its bytes were unchanged, so the same cold read could not surface anything new. |
| 5 | 2026-07-26 | 1 medium — **1 verified** | the What-checks-this table cited §6 for a `TODO`/`TBD` rule §6 never stated. The gate existed; the rule was implicit. Now written into §6. |
| 6 | 2026-07-26 | 2 medium — **2 verified** | converged (polish only). `QSS` was used undefined, against this file's own §8.2; and §6b.4's second example was a ratio, not a past-tense measurement, while the prose beneath claimed every row was 'about what happened'. The ratio moved to §6b.2, where it demonstrates the right rule. |
