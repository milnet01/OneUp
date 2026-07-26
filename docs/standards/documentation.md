# Documentation Standard

**In one sentence:** every document here has one job, and this file says which job, so
nobody has to guess where a decision belongs or whether it has been reviewed.

**Status:** Draft — cold-eyes loop 1 applied; see §10
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every path and claim below was checked against the tree on
2026-07-26, not recalled.

**Applies to:** every document in the repository, including the component `README.md`
files under `packaging/obs/` and `screenshots/` (they follow §8's writing rules; they need
no Status header, because they document a directory rather than a decision).

**Sections:** 1 the documents · 2 when each is required · 3 the Status header · 4 the spec
template · 5 invariants · 6 verification · 6a citing code · 7 the review gate · 8 writing
for a non-programmer · 9 keeping documents true · 10 cold-eyes log

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

A document mid-review is `Draft` with a note — `Draft — cold-eyes loop 1 applied` — never
`Reviewed`. The §10 loop log and the `Status` line must agree; if they disagree, the log
is right.

**This is prescriptive from 2026-07-26, not a description of the tree.** The five specs
written before it (`ONEUP-0018`, `0022`, `0025`, `0028`, `0054`) use their own shapes —
`Status: design`, `Status: Cold-eyes converged (2 loops — …)`, `Kind: accessibility`, and
none carries `Branch:` or `Verified at:`. They are **grandfathered**: each is brought to
this shape the next time it is edited for another reason, not in a sweep.

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
commit `ea51adc`. The real figures at `dbef1a8` are 205 and 3,719. Numbers rot silently,
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

**Every design document, spec, standard and reference goes through `/cold-eyes` and is
looped until a pass returns zero verified findings.** Implementation does not start
before that. Should the project ever adopt per-feature test contracts (a `spec.md` beside
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
- **When two documents disagree, §1.1's order settles it**, and the loser is fixed
  immediately rather than noted.

## 10. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: the precedence rule contradicted §1's table, the header block was missing from the standard that mandates it, the `Status`/`Kind` enums matched no document in the tree, and "standards never hold anything version-specific" contradicted six of the nine |
