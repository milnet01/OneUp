# OneUp 2.0 Documentation Set — implementation plan

> **For agentic workers:** implement task-by-task. Steps use checkbox (`- [ ]`) syntax
> for tracking. Every task ends at a commit; no task is "done" until its verification
> step has actually been run and its output seen.

**Goal:** produce every document 2.0 will be built against — nine standards, one protocol
reference, four specs — each independently reviewed until clean, before any 2.0 code is
written.

**Approach:** the standards come first because the specs are written *under* them
(sequencing chosen with the user, 2026-07-26). Documents are drafted in dependency order,
then reviewed in three `/cold-eyes` batches. Nothing here writes or changes code; the only
source files touched are `CLAUDE.md` (Task 11) and `docs/standards/dialogs.md` (Task 6,
absorbed and removed).

**Roadmap item:** ONEUP-0057 (🚧). **Design:** `docs/design/oneup-2.0.md` — read it first.

> ## ▶ You are here — **Task 18: `ONEUP-0076` gated (loops 1–2, capped); it owes two decisions, then `ONEUP-0072` from loop 5**
>
> **`ONEUP-0076` has had its first gate on its own bytes — 22 verified across two loops, 20
> fixed, 2 surfaced, capped rather than converged, `Status: Draft`.** The 0-split row was
> right that none of the parent's assurance transfers: loop 1's strongest finding was a
> *recurrence* of one the parent's parent-3 row records fixing on 2026-08-03 — the rule box
> stating two different derivation algorithms — which survived the split untouched. **Gate a
> split document from loop 1; do not count the parent's loops.**
>
> **Five findings came from RUNNING the document rather than reading it**, and every one was
> raised by a lane as an open question it could not settle, because `review-lane` holds no
> `Bash`. That division worked well and is worth repeating: the lanes find the contradiction,
> the orchestrator settles the measurement. INV-1's dialog sweep is red on day one (six of
> 21 dialog widgets match no row); the overlay's `#LinkBtn:focus` cannot reach 3:1 at any
> colour; `_HC_QSS` has no `DetailScroll` rule to widen; the light link ink failed on three
> of its four surfaces; and five `size_btn` objects exist but only one is parented, so the
> census is right and §2.1's claim about it was not.
>
> **Loop 2's strongest finding was loop 1's own fix**, for the third gate running in this
> batch — INV-4's rewritten assertion was red against the very design it tests. The lesson
> from `ONEUP-0077` and `ONEUP-0072` holds unchanged: **a fix that adds assertive text is
> where the next loop's findings come from.**
>
> **`ONEUP-0076` now owes two decisions, not a loop**, both carrying their measurement in a
> `⚠ OPEN` block and both reaching `ONEUP-0064` and `ONEUP-0027`: how one object name carries
> three rest-pixel sets when §4.4 matches by object name, and whether INV-1 covers the six
> uncovered dialog widgets or excludes unstyled Qt chrome by a stated rule.
>
> **Next: `ONEUP-0072` from loop 5**, then `ONEUP-0032` (a real loop 1 — see below), then the
> cheap citation pass on `ONEUP-0027`. `ONEUP-0064` still owes a decision rather than a loop.
>
> **A tool now answers the question this batch kept paying for.** `spec_query
> mode:"gate_drift"` cross-references each spec's last loop-log row against its git history in
> one call. It reports `ONEUP-0027`, `ONEUP-0054` and `ONEUP-0077` as `Reviewed` while
> carrying post-review edits — 4 to 11 lines each, all citation repoints from the two splits
> rather than the §7 rewrite that made `ONEUP-0064` dangerous. Check it before trusting a
> stamp.

> ## Previously — **Task 18: `ONEUP-0064` re-gated (loops 4–6)**
>
> **`ONEUP-0064` came back to the gate and should not have needed to.** It was stamped
> `Reviewed` when loops 1–3 converged by cap on 2026-08-05; `ONEUP-0090` then rewrote its §7
> on 2026-08-07 while closing a defect elsewhere, and that paragraph was never read cold. A
> fresh run on 2026-08-12/13 found **20 verified** across three loops (Q1 7 · Q2 5 · Q3 6 ·
> Q4 2, 2 dismissed out of scope, 19 fixed) — among them a light-palette contrast regression
> `ONEUP-0076` had already measured against, and an INV-7 whose whole *Test:* clause had the
> high-contrast overlay backwards. **Its `Status` is back to `Draft`**, because no loop came
> back empty and §4.1 now carries one open decision — the `:hover` colours for
> `QToolButton#Disclose` and `#StopBtn`. It is 626 lines and still yielding findings on its
> sixth cold read; **splitting §4.1 is the call to make before a seventh.**
>
> **The lesson, and it generalises past this document:** a `Reviewed` stamp does not survive
> an edit made by another item. Anything that rewrites a gated spec in passing re-arms its
> gate, and nothing on this machine notices.
>
> **Next: `ONEUP-0076`, then `ONEUP-0072` from loop 5.** `ONEUP-0101` is
> done — the window half of `ONEUP-0072` is now
> `docs/specs/ONEUP-0108-window-wording.md`, and that document has had three loops of its
> own (17 verified, all fixed, 0 dismissed, no deferred tail). **Both specs are still
> `Draft`**, because neither gate has returned an empty loop; `ONEUP-0072` has not been
> read cold since the split took a third of it away.
>
> **The split paid for itself and the numbers say so.** `ONEUP-0108`'s first three loops
> found 17 findings in content that had already passed four loops inside the parent —
> among them a sentence that had contradicted `ONEUP-0072` §6's own last row throughout,
> and a §6 row illustrating an *unknown* reboot element with `firmware-updated`, which is
> a known one. A cold read was not reaching that text while it lived in an 859-line
> document.
>
> **Both questions that needed a human are answered:**
>
> 1. **Answered 2026-08-12 — `@@REBOOT@@`'s *was/were* agreement.** The old §4.3 routed it
>    through Qt's plural form, which (measured against PySide6 6.11) selects a form only
>    where a catalogue exists, while design §5.1 ships 2.0 with **no locale file for any
>    language** — so English would have regressed wording `reboot_reason_from_log` gets
>    right today. The user chose the **explicit English branch beside the plural call**, of
>    the three ways out on offer. It is `ONEUP-0108` §4.2, settled, with §9 recording the
>    two rejected and INV-2 holding it in place; there is no `⚠ OPEN` block in either
>    document.
> 2. **Answered 2026-08-12 — split rather than a fifth loop.** The condition was written
>    down two loops in advance: run loop 3, and if collateral again outruns draft defects,
>    split §4 rather than raise `--max-loops`. Loop 4 came back 4 collateral to 2 draft, so
>    it fired. `ONEUP-0101`'s bullet holds the measurement.
>
> **The lesson loop 2 paid for, and it is the batch's standing instruction:** loop 1 fixed
> 24 findings and *created* 15 of loop 2's 25. The single largest cause was **stating one
> rule in four places** — the fallback form ended up in §4.1, §4.3, INV-3 and §6, and every
> later edit moved one copy and stranded the others. Loop 2's remedy was to **delete N−1**
> and leave one owner. Reconciling copies is not a fix; it is the next loop's findings. The
> split applied the same rule at document scale: one rule, one owner, and every pointer
> into the moved text rewritten in the same commit — `ONEUP-0077` §4.2 and §6,
> `ONEUP-0032` §4.1 and `marker-protocol.md` §5.2, which was the class that broke after
> the 2026-08-03 split and was found a loop later.
>
> **`ONEUP-0077` is done (2026-08-03) — three loops, `Status: Reviewed`, converged by cap.**
> 21 → 23 → 20 verified, all fixed; nothing left verified and unfixed, one INFO carried.
> **The two still to gate are `ONEUP-0076` and `ONEUP-0072`** — 0076 from loop 1 on its own
> bytes, `ONEUP-0072` from loop 5 — then the cheap pass on `ONEUP-0027`. `ONEUP-0064` has
> had its run and owes a decision rather than a loop. `ONEUP-0034` is untouched
> since its own four-loop gate and needs nothing.
>
> **`ONEUP-0032` no longer qualifies as a cheap pass.** It took a substantive edit during
> 0077's loop 3 — its §4.2 pointed at `ONEUP-0072 §4.4`, a section the split deleted, and it
> now also records that it **retires 0077's INV-5** when it lands. Give it a real loop 1, not
> a citation sweep.
>
> **The lesson 0077 cost, and it is the batch's operating instruction:** loop 1 found 21
> draft defects and 0 collateral; loops 2 and 3 found 8 and 6 draft against 15 and 12
> collateral. **Both of loop 2's criticals and loop 3's critical were my own previous fixes** —
> an invariant rewritten into a conjunction that mandated silence on a broken repository, a
> precedence rule that made a stopped run (which exits zero) read as success, and a table
> pinned at five entries three sections above a §4 mandating eight. Sweep the whole document
> after every fix pass, not per fix, and **never state a count without enumerating the list** —
> that one defect appeared in two separate loops.
>
> **Two of my own claims were wrong and verification caught them, not review:** that the
> window prunes `LOG_DIR` (nothing prunes anything — filed **ONEUP-0082**) and that the log
> growth *starts* with this item (`_launch` already writes one per GUI run, so it is
> inherited). Grep before asserting cover, every time.
>
> **What worked, and is worth repeating verbatim:** a ~91 KB bounded context packet built with
> `sed`/section-extracts so the bytes never transit the orchestrator's context — lanes came in
> at 107–115k tokens. Withhold the loop log with a scrubbed `/tmp` copy, not an instruction.
> Rebuild the cross-reference part **from scratch** each loop: appending to it left two copies
> of `oneup-2.0.md` §5.2 in the packet, and both lanes correctly hedged their findings on it.
>
> ## Superseded — the Task 17 block below is history
>
> **Task 16 done (2026-08-03), and it produced two specs, not one.**
> `docs/specs/ONEUP-0032-i18n.md` was taken through `/cold-eyes` and **split at its fifth
> loop**: the payload conversion left for `docs/specs/ONEUP-0072-marker-codes.md` and 0032
> kept the catalogue machinery and right-to-left. Every finding in loops 4 and 5 had sat on
> one side of a clean seam, which is what made the seam obvious. 0032 then took a sixth
> review as the split document (20 verified, 2 dismissed); 0072 took **three of its own**
> (24, 22, 20 verified) and **converged by cap rather than clean** — its §11 carries the
> tail and the recommendation to split §4 rather than run a fourth loop. Both are
> `Status: Reviewed`.
>
> **The ordering was settled 2026-08-03 (user):** 0072 lands **before** 0032, between the
> engine rewrite and translation. Each spec had claimed the other must land first;
> `docs/design/oneup-2.0.md` §5.2 owns the order of work and now places 0072 in its diagram,
> which it had never done. The rule is the one that already puts 0032 last — wording is
> wrapped once, and 0072 is the last item that changes what the wording *is*.
>
> **Task 16's Step 3 was overtaken by its own spec.** It scoped the contract change to
> `HINT` and `REMEDY`; 0072 §3.1 widened it to every payload the window renders as words,
> because the window is *already* re-deriving `STEP_END`'s meaning from English substrings —
> a live defect independent of translation. `marker-protocol.md` §5.1/§5.2 and
> `oneup-2.0.md` §5.1 are amended to match.
>
> **Task 15 done (2026-07-27).** `docs/specs/ONEUP-0027-themes.md` — selectable themes —
> written and taken through `/cold-eyes` in **four loops**: 9 findings verified, then 9, 3,
> 1. `Status: Reviewed`. Nothing a loop fixed came back.
>
> **The user's three answers:** eight themes to start, **Follow system** stays the default,
> the picker lives in Settings. A named theme is one fixed palette — choosing one is
> choosing not to follow the desktop — and the two palettes that ship today are two of the
> eight, so six are authored rather than eight.
>
> **Writing the contrast check first is what made the item real.** `ui-and-accessibility.md`
> §7 had already handed ONEUP-0027 that job and flagged one failing pair. Computing it found
> nine, including the one that matters most: the white bar-and-circle on the switch — the
> colour-blind cue itself — sits at **2.10:1** against its own green track. And the theme
> cannot currently reach the surfaces that carry state at all: ten colour literals live in
> the two painters, and **thirty more inside the stylesheet template**, twelve distinct,
> including the accent's own first stop written out in eight places.
>
> **The lesson repeated, and it is the same one.** Loops 2 and 3 were almost entirely the
> previous loop's blast radius: splitting a token left a count of "nine" over a table of
> ten; naming four groups of literals left two of them with no home in the pair table;
> saying `build_theme` reads a theme's base left `base` nowhere to live. The one finding
> that was not self-inflicted was worth the whole run — the design lands **ONEUP-0064 before
> this item**, and three passages deferred to it as though it were still to come.
>
> **Task 14 done (2026-07-27).** `docs/specs/ONEUP-0034-gui-modules.md` — the GUI module
> split — written and taken through `/cold-eyes` in **four loops**: 11 findings verified,
> then 6, then 3, then 1. `Status: Reviewed`. Nothing a loop fixed came back.
>
> Two obstacles were measured before the spec was written, and both change what the first
> commit has to be: `tests/gui-smoke.py`'s loader breaks the moment the root `updater.py`
> imports the package, and a test that patches a re-exported name silently stops patching
> anything — which is how the suite could stay green while the window deleted a live run's
> `run.state`. The harness moves first, on its own.
>
> The loops found the same defect over and over in different sentences: **a claim worded
> wider than the thing backing it.** "Nothing in `updater.py` is left unplaced" (true of
> module-level names, not of `Updater`'s methods, and it hid a missing module for the update
> check); "every `QDialog` subclass" (`QMessageBox` is one, and the next sentence exempted
> it); "every focusable widget" (the sweep walks four roots). Three citations resolved to
> sections that say something else, and one standard — `files-and-naming.md` §2.2 — was
> itself wrong about how tests are run, which the spec had inherited. Fixed at the source.
>
> **Task 13's lesson held.** Loop 3's only substantive finding was loop 2's own fix stranding
> a sibling: splitting two rows out of the §7 table left a third merged, so an invariant's
> assertions appeared in no row. Auditing all twelve rows at once cost less than the loop
> that would have found the next one.
>
> **Task 13 done (2026-07-27).** Cold-eyes batch 2 over the 2.0 design, the engine spec and
> `workflow.md` — **nine loops to convergence**, eight full plus a cheap closing pass. Roughly
> 380 findings raised, ~330 verified and fixed; **nothing a loop fixed ever resurfaced**, which
> is the proof the fixes held. All three now `Status: Reviewed`.
>
> The four that mattered most were each a document claiming cover it did not have: the design
> called `ToggleSwitch._paint_state_shape` "symmetric by construction" when it is handed the
> same way the knob is; the engine spec cited the marker reference as owning a state-file
> contract the reference had explicitly delegated *to the spec*, so it existed in neither;
> `workflow.md` credited `tests/bump-test.py` with proving all six version sites when five of
> its six assertions read the CHANGELOG; and G4 was said to gate ONEUP-0044 while its scenario
> counts authentications and the bug is two dialogs from one. Two genuine gaps were closed
> rather than reworded: nothing said how 2.0.0 is released (`release.sh` refuses any branch but
> `main`), and the retained Bash fallback stops being a drop-in the moment ONEUP-0072 lands.
>
> **A lesson for Tasks 14–19, learned expensively:** loops 5–8 were mostly reviewing *the
> previous loop's edits*, not the documents. Every critical from loop 5 on was introduced by an
> earlier fix — a fact rewritten in one document and left stale in its sibling, a list closed
> that the build order exceeds, a coverage claim nobody checked. Fix by deleting and pointing;
> sweep every citation of a fact you change, in the same pass; and do not answer a finding by
> writing a new paragraph.
>
> **Two decisions taken with the user:** `update_system.sh` stays through 2.0 as a documented
> fallback and goes in 2.1; and `workflow.md` §1.2 gains one narrow freeze exception, for the
> `ONEUP_ENGINE_CMD` harness change only, written in the standard that owns the freeze.
>
> **Task 17 done (2026-08-03), and it produced two specs, not one.**
> `docs/specs/ONEUP-0064-interface-redesign.md` was written and taken through `/cold-eyes`
> in **three loops** (24, 34, 35 verified) and **converged by cap rather than clean** — then
> **split**, on the user's decision, into the layout redesign (0064, 268 lines) and
> `docs/specs/ONEUP-0076-ringless-focus-cue.md` (**ONEUP-0076**, new bullet, 636 lines).
> Neither half has been gated on its own bytes; both enter Task 18 from loop 1.
>
> **The measurement settled the design and inverted the obvious answer.** Lightening cannot
> reach SC 2.4.13's 3:1 on the accent at any shade — pure white is 2.63:1 against `#4aa3ff`
> — so the cue **darkens**, which kills "focus reuses the hover look". Rather than author a
> focus colour per theme, the app **derives** one: the smallest blend toward black or toward
> white — whichever reaches it at the lower blend fraction — clearing 3:1 against every one of
> a control's rest pixels. Total for one surface (the max of contrast-vs-black and contrast-vs-white never
> drops below 4.58:1), **not** total for a set — `#000000` and `#989898` admit none, 192 such
> grey pairs exist — so the search fails loudly.
>
> **Two other documents are provably wrong and are corrected when this lands:**
> `ui-and-accessibility.md` §5.4 claims SC 2.4.7 is "still met" when 16 of the window's 34
> focusable widgets have no cue at all; and `ONEUP-0028` §5 promises `:focus` rules for eight
> controls when three have none, and specifies a 2 px outline the no-focus-ring decision
> forbids. ONEUP-0028's own §2 had already logged the absence as a "WCAG 2.4.7 failure".
>
> **The lesson, and it is the same one Task 16 recorded in a different shape:** the loops
> stopped reviewing the document and started reviewing the previous loop's fixes. Draft
> defects fell 24 → 13 → 8 while collateral rose 0 → 21 → 27; loop 3's unanimous critical was
> pure arithmetic self-injury, an invariant added in loop 2 that a value also added in loop 2
> made unsatisfiable at 1.00:1. Split at the cap rather than run a fourth loop.
>
> **Three bullets filed at discovery:** ONEUP-0074 (a stopped run notifies "Already up to
> date"), ONEUP-0075 (`spec_query` reads zero invariants from every spec in `docs/specs/`),
> ONEUP-0076 (the focus cue itself).
>
> **ONEUP-0072 was split too (2026-08-03, user's decision).** Its §4.4 — the notification the
> timers raise — became `docs/specs/ONEUP-0077-headless-notification.md`, which folds in
> ONEUP-0074 (a stopped run notifies *"Already up to date"*); 0072 keeps the payload
> conversion and is down to 595 lines from 654. Its own loop 3 had recommended exactly that.
>
> **Next:** Task 18 — cold-eyes batch 3, now over **seven** specs: 0034, 0027, 0032, 0064,
> 0072, 0076 and 0077. Five have never been gated on their current bytes (0064, 0072, 0076,
> 0077 by the two splits; 0032 and 0027 by the citation edits the splits required). Then
> Task 19.
>
> **Done earlier:** Tasks 1–11 (2026-07-26). Nine standards, the marker-protocol reference,
> cold-eyes batch 1, and `CLAUDE.md`. All ten reviewed documents are `Status: Reviewed`
> and carry their own loop log. Batch 1 ran to convergence over four loops; the last one
> returned polish only. Three things came out of it that outlive it: `tests/docs-check.py`
> now gates the documentation rules a script can settle, every standard ends with a **What
> checks this** table, and `documentation.md` gained §6a (cite by name, never by line
> number) and §6b (keep counts taken from the code out of a document). `./local-CI.sh`
> green — it prints the tallies.
>
> **Carry these forward — they are decisions, not suggestions:**
> - **`main` is frozen at 1.4.0.** Anything found that cannot be fixed is *filed on the
>   roadmap at the moment it is found*, never held to close-out. That standing instruction
>   is why ONEUP-0058 … 0068 exist.
> - **2.0's scope** is ONEUP-0054, 0034, 0027, 0032, 0064, 0044, 0004. No partial 2.0
>   releases.
> - **The interface redesign (0064)** has free rein, with two fixed points: **no focus
>   borders** (ordinary borders are fine) and **the on/off switches stay**.
> - **Translation (0032)** ships groundwork only in 2.0 — English alone, right-to-left in
>   scope.
> - One open decision, recorded not blocking: the ringless focus cue measures **1.14:1** on
>   the main button against WCAG 2.4.13's 3:1 (`docs/standards/ui-and-accessibility.md`
>   §5.4). Routed to Task 17.

## Global Constraints

Copied verbatim from the design doc and the user's decisions. Every task inherits these.

- **Verify, never recall.** Every claim naming a function, file, line, flag, marker,
  constant or version is backed by a `grep`/`read` against the tree *in the same session
  it is written*. Global rule 13. A claim that cannot be verified is deleted, not softened.
- **Cite the commit.** Each document states the commit its figures were measured at.
  Today's baseline is `dbef1a8` (v1.4.0).
- **`main` is frozen** for code (design §5.4) — documentation is not a release and lands
  on `main` normally. **No code changes in this plan** except Task 11's `CLAUDE.md` and
  Task 6's removal of `dialogs.md`.
- **No placeholders.** No "TBD", no "to be decided later". A question that cannot be
  answered from the tree is put to the user in the task that hits it.
- **Plain English, with the jargon defined inline.** Every standard opens with one
  sentence a non-programmer could act on.
- **Commit per document**, message `ONEUP-0057: <what the document settles>`.
- **`./local-CI.sh` before every push**, green. Docs-only commits still run it.
- **The nine standards are:** documentation, files-and-naming, coding, security, testing,
  ui-and-accessibility, wording-and-translation, workflow, dependencies (exists).

## File structure

| Path | Responsibility | Task |
| --- | --- | --- |
| `docs/standards/documentation.md` | What each document is for; the spec template every later task follows | 1 |
| `docs/standards/files-and-naming.md` | Where a new file goes and what it is called | 2 |
| `docs/standards/coding.md` | Python floor, typing, module size, subprocess discipline, comments | 3 |
| `docs/standards/security.md` | Privilege split, sudo rules, input validation, logging, permissions | 4 |
| `docs/standards/testing.md` | Mock-PATH sandbox, machine isolation, invariant↔test traceability | 5 |
| `docs/standards/ui-and-accessibility.md` | Theming, contrast, scaling text, accessible names, dialogs | 6 |
| `docs/standards/wording-and-translation.md` | How user-facing text is written and wrapped | 7 |
| `docs/standards/workflow.md` | Branches, the freeze, commits, roadmap IDs, versioning, releases | 8 |
| `docs/reference/marker-protocol.md` | The engine↔GUI contract, all 23 markers | 9 |
| `CLAUDE.md` | Shrinks to a map that still carries the hard-won traps | 11 |
| `docs/specs/ONEUP-0054-python-engine.md` | Revised under the standards; figures refreshed | 12 |
| `docs/specs/ONEUP-0034-gui-modules.md` | The GUI split | 14 |
| `docs/specs/ONEUP-0027-themes.md` | Selectable themes | 15 |
| `docs/specs/ONEUP-0032-i18n.md` | Translation, incl. the §5.1 contract change | 16 |
| `docs/specs/ONEUP-0064-interface-redesign.md` | The interface redesign — layout, ergonomics, clarity | 17 |
| `docs/specs/ONEUP-0076-ringless-focus-cue.md` | The ringless focus cue, its derivation and its check (split from 0064) | 17 |

---

### Task 1: `documentation.md` — the standard the other thirteen obey

**Files:** Create `docs/standards/documentation.md`

**Produces:** the spec template (section list + INV table format) that Tasks 12/14/15/16
follow verbatim, and the Status header block Tasks 2–9 reuse.

- [ ] **Step 1: Extract the template from what already works.** Read the section headings
      of the four existing specs — they have already converged on a shape:

```bash
grep -n '^#\{1,3\} ' docs/specs/ONEUP-0018-system-tray-icon.md \
                     docs/specs/ONEUP-0025-repo-resilience.md \
                     docs/specs/ONEUP-0028-accessibility.md
```

- [ ] **Step 2: Write the document.** It must settle, concretely:
      - **The document types and what each is for:** README (users), CLAUDE.md (the map),
        ROADMAP.md (the record of intent), CHANGELOG.md (what shipped), `docs/design/`
        (programme-level, cross-item), `docs/specs/` (one item's contract),
        `docs/plans/` (one item's build steps), `docs/standards/` (standing rules),
        `docs/reference/` (frozen contracts).
      - **When each is required.** A roadmap bullet always. A spec when design questions
        exist (design §6.1). A plan when the item starts, never before.
      - **The spec template**, section by section: Status header → Goal → Background →
        Scope decisions agreed with the user → Design → Correctness invariants (numbered
        table, `INV-N | statement | test that locks it in`) → Failure modes → Tests →
        Docs & release → Alternatives rejected → Out of scope → Cold-eyes loop log.
      - **The Status header block:** Status, Kind, Roadmap id, Branch, and the commit the
        figures were verified at.
      - **The verification rule** (global rule 13) stated as a documentation rule: any
        claim naming code must cite it; a citation is checked when written, not recalled.
      - **The layman rule:** every roadmap bullet carries a `**Layman:**` line; every
        standard opens with one plain sentence.
      - **The review gate:** every design/spec/standard/reference goes through
        `/cold-eyes` until a pass returns zero verified findings; loop 2+ runs cold (the
        reviewer is not briefed on earlier findings); the loop log is written as it
        happens, never back-filled.
      - **Staleness:** a document that cites figures states its commit; when a figure is
        found stale, the document is corrected in the same session it is noticed.

- [ ] **Step 3: Verify the claims.** Every path named must exist or be created by this
      plan:

```bash
ls docs/design docs/specs docs/plans docs/standards README.md CLAUDE.md ROADMAP.md CHANGELOG.md
```
      Expected: all present except `docs/reference/` (Task 9 creates it) — say so in the
      document rather than implying it exists.

- [ ] **Step 4: Commit.**

```bash
git add docs/standards/documentation.md
git commit -m "ONEUP-0057: settle what each document is for, and the spec template"
```

---

### Task 2: `files-and-naming.md`

**Files:** Create `docs/standards/files-and-naming.md`

**Consumes:** Task 1's Status header block.
**Produces:** the `oneup/` package naming rules Tasks 12 and 14 must follow.

- [x] **Step 1: Measure the tree as it is.** The standard describes reality first:

```bash
git ls-files | grep -v '^docs/' | sed 's#/[^/]*$##' | sort -u
ls data/ packaging/*/ tests/
```

- [x] **Step 2: Write the document**, settling:
      - **Repo layout**, directory by directory, one line each on what belongs there.
      - **Naming:** Python modules `snake_case.py`; shell scripts `kebab-case.sh` (note
        the existing exceptions `update_system.sh`, `local-CI.sh` — describe, don't
        rename); specs and plans `<ID>-<topic>.md` with a lowercase kebab topic;
        standards `<subject>.md`, singular subject, no `ONEUP-` prefix (they outlive
        items).
      - **The app ID** `za.co.antsprojectshub.OneUp` and the rule that every file under
        `data/` carries it.
      - **The `oneup/` package layout** from design §4, and the rule that a new engine
        module never imports from `oneup/gui/` (enforced by test, gate G5).
      - **Runtime state:** `~/.local/state/oneup/` for `history.json`, `logs/`,
        `run.state`, `stop.request`; log mirror at `~/Documents/update-logs/`; and which
        of them can actually be redirected in a test.
        **Correction made while writing (2026-07-26):** this step originally asserted
        "every one of them has an environment-variable override so tests never touch the
        real path." Measured, that is false — **three paths have no override at all**
        (`~/Documents/update-logs`, the GUI's `logs/`, `history.json`), and the GUI has
        no `ONEUP_*` override of any kind; it is isolated by rewriting `HOME` before
        import. The standard states what is true and §5.2 makes the override a
        *requirement on new state paths* rather than a description of existing ones.
      - **What a new file obliges you to update:** the three packaging paths, and the
        six version sites if it is version-bearing.

- [x] **Step 3: Verify the state-path claims against the engine:**

```bash
grep -n 'ONEUP_RUN_STATE\|ONEUP_STOP_FILE\|ONEUP_ZYPP_PID_FILE\|local/state/oneup\|Documents/update-logs' update_system.sh updater.py | head -20
```
      Every override named in the document must appear here. Any that does not is deleted
      from the document. **Done — and it caught the Step 2 error above.** Two defects
      surfaced by the same sweep and filed rather than fixed (`main` is frozen):
      **ONEUP-0058** (the suite creates `~/Documents/update-logs` on the real machine,
      `update_system.sh:149`) and **ONEUP-0059** (`XDG_STATE_HOME` set by the tests,
      ignored by `updater.py:117`).

- [x] **Step 4: Commit.**

```bash
git add docs/standards/files-and-naming.md
git commit -m "ONEUP-0057: settle where a file goes and what it is called"
```

---

### Task 3: `coding.md`

**Files:** Create `docs/standards/coding.md`

**Consumes:** Task 2's package layout.
**Produces:** the Python floor and lint configuration decision that Task 12's spec and all
2.0 code depend on.

- [x] **Step 1: Establish the Python floor — look it up, do not assume.** The binding
      constraint is the oldest openSUSE Leap OneUp supports, because Tumbleweed is always
      newer:

```bash
python3 -V                                   # this machine
grep -n 'python-version' .github/workflows/release.yml
grep -n 'Requires\|BuildRequires' packaging/rpm/oneup.spec
```
      Then check what Leap ships — `https://software.opensuse.org/package/python3` or a
      Leap box. **If the answer is not obtainable, stop and ask the user** whether Leap is
      a supported target at all; do not guess a floor.
      **Answered from fact (2026-07-26) — the user did not need to be asked.** The floor
      is **3.13**, and this step's own framing ("the oldest Leap") was the thing that
      needed correcting: **Leap 15.6 reached end-of-life on 2026-04-30**, three months
      before this was written, so the oldest *supported* Leap is **16.0**, whose release
      notes state `/usr/bin/python3` is Python **3.13** — the same as Tumbleweed
      (measured on this machine, snapshot `20260723`). PySide6 supplies a **ceiling**
      (`<3.15`), which also confirms ONEUP-0004's pending 3.13 → 3.14 CI bump is safe.
      Two search summaries claimed Leap 16.0's interpreter was 3.11; the release notes
      disagreed and won.

- [x] **Step 2: Decide the lint configuration.** There is no config file today
      (`ruff` runs on `--select F,B` from `local-CI.sh` only), so a developer's local run
      differs from CI's:

```bash
grep -n 'ruff\|shellcheck' local-CI.sh
ls pyproject.toml ruff.toml .ruff.toml 2>/dev/null || echo "no lint config"
```
      Record the decision (add `pyproject.toml` with the ruff rule set, or keep
      flags-in-CI and say why) in the document. Adding the file itself is 2.0 work, not
      this plan's.
      **Decided: add `pyproject.toml`,** with the rule set written out verbatim in §2.1
      so the 2.0 implementer invents nothing. `line-length = 100` was chosen by
      measurement, not taste — at 100 exactly **13** lines in the tree are too long; at
      ruff's default 88, **135** lines in `updater.py` alone would be, which is a
      reformatting project disguised as a lint setting (global rule 11). The rule set
      includes `S`, which turns the **six** existing `# noqa: S603/S607` comments from
      decorative into functional — they currently suppress rules nothing enables.

- [x] **Step 3: Write the document**, settling:
      - The Python floor from Step 1, with its reason, and the rule that idioms may
        assume it (`match`, `X | Y` unions, `list[int]`).
      - **Type hints** on new modules: required on public functions, optional inside.
      - **Module size:** a soft ceiling with the reason (ONEUP-0034 exists because
        `updater.py` reached 3,719 lines), and the instruction to split by responsibility,
        not by layer.
      - **Subprocess discipline:** never `shell=True`; argument lists only; the engine's
        privileged calls go through one runner (design §5) — no ad-hoc `sudo` call sites.
      - **Qt idioms** for the GUI half: new-style `connect`, `QPointer` for lifetime,
        parent every `QMenu`/dialog (the ONEUP-0018 review found an unparented `QMenu`
        that could be garbage-collected).
      - **Error handling:** no bare `except: pass`; a failure is reported, not silenced
        (global rule 1); a failed step records, hints in plain English, and continues.
      - **Comments:** explain *why*, and the six-month test.
      - **Reuse before rewriting**, and the Rule of Three.
      **Done, plus a §10 traps section** (the user's standing instruction to catch the
      gotchas early). Two of this step's own premises needed correcting against the tree:
      the `QMenu` at `updater.py:2222` **is** parented today, so ONEUP-0018's finding is
      history rather than a live defect; and `QPointer` appears **nowhere** in the
      codebase — parenting has covered every case — so it is written as the rule for a
      reference you do *not* own, not as current practice. The measured module figure is
      sharper than the plan's: the `Updater` class alone is **2,340 lines** (1292–3632)
      of `updater.py`'s 3,719.

- [ ] **Step 4: Commit.**

```bash
git add docs/standards/coding.md
git commit -m "ONEUP-0057: settle the Python floor, module size and subprocess discipline"
```

---

### Task 4: `security.md`

**Files:** Create `docs/standards/security.md`

- [x] **Step 1: Re-derive the sudo model from the engine, not from memory.**

```bash
grep -n 'sudo_capture()' -A 25 update_system.sh
grep -c 'sudo_capture' update_system.sh
grep -n 'SUDO_ASKPASS\|SUDO_PROMPT\|sudo -v\|keepalive' update_system.sh | head -20
```

- [x] **Step 2: Write the document**, settling:
      - **The privilege split** as rule one: the GUI never runs as root, ever; the engine
        is the only path to root; gate G5 (engine imports no Qt) is how it stays true.

        **Corrected while writing (2026-07-26).** This framing is not accurate and the
        inaccuracy is the dangerous direction. Measured: `updater.py` contains **zero**
        `sudo` invocations and the engine contains **zero** Qt references, so G5 and "the
        GUI never becomes root" both hold — but the GUI *does* call **`pkexec`** at three
        sites (`updater.py:1118`, `3525`, `3551`), and two of them build a **root shell
        string** (`pkexec sh -c …`). Coding under the absolute version of the rule means
        not writing the boundary validation those sites depend on. The standard therefore
        states the precise rule (§1.4–1.6): the GUI never *becomes* root, may ask polkit
        to run a named program as root for short user-initiated actions outside a run,
        and validates every argument first. `coding.md` §5.1(3) and §10.6 carried the same
        overstatement and were corrected in this task.
      - **One authentication per run**, and *why the subshell rule exists*: with no
        terminal, sudo keys its cached credential to the parent pid, and bash forks a real
        subshell for `$(cmd | other)` — a measured run once needed seven prompts. In
        Python the same trap becomes "one runner owns every privileged child."
      - **`SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass` with a labelled `-p`** — never bare
        `sudo`, never an unlabelled prompt (an unlabelled root prompt is indistinguishable
        from a phishing dialog).
      - **Input validation on anything crossing the boundary:** the snapshot id from
        `SNAPSHOT_ITEM` must be a bare number before it reaches a root `snapper rollback`;
        repo aliases likewise. State the rule generally: *any value that reaches a
        privileged command is validated by shape at the boundary.*
      - **The passwordless drop-in** (`--grant-auth`/`--revoke-auth`): opt-in only, never
        silent, scoped, and revocable — with the exact scope written down.
      - **Never signal the engine mid-transaction.** SIGTERM during `zypper dup` leaves
        rpm half-applied or orphans zypper. Stopping is cooperative, at boundaries only.
      - **Logging:** what may be written to `~/.local/state/oneup/logs/` and the mirror,
        and that nothing captured from a privileged command is echoed without review.
      - **Supply chain:** points at `dependencies.md`; the AppImage and RPM build inputs.

- [x] **Step 3: Verify every claim in the document** by re-reading the greps from Step 1.
      Any rule that the engine does not actually follow is a **finding**, not a rule —
      record it as a roadmap bullet rather than describing fiction.

      **Done, mechanically.** All 13 `file:line` citations in the document were resolved
      against the tree and each prints the construct claimed — no drift, no out-of-range.
      Two claims came back *better* than drafted and were strengthened rather than left
      as assertions: `--no-gpg-checks` is not merely absent but **guarded by two
      regression tests** (`tests/run-tests.sh:1816`, `:1859`, including the auto-skip
      path); and the `env LC_ALL=C zypper *` sudoers entry matches that literal prefix
      only, so it cannot be used to hand `env` an arbitrary environment. One finding was
      recorded in place rather than filed (§4.5): the service-unit pattern permits a
      literal backslash, almost certainly a typo for `\-`, **not exploitable** because
      that site is argv-form — tidy it when the file is next touched, not on frozen
      `main`. No roadmap bullet was warranted from this task. **Tidied 2026-08-18 under
      ONEUP-0110**, which found the same pattern was rejecting every unit name the engine
      sends; §4.5 now records it resolved.

- [x] **Step 4: Commit.**

```bash
git add docs/standards/security.md
git commit -m "ONEUP-0057: settle the privilege split, the sudo model and boundary validation"
```

---

### Task 5: `testing.md`

**Files:** Create `docs/standards/testing.md`

- [x] **Step 1: Read how the harness actually works** — the standard describes it, so it
      must match:

```bash
grep -n 'run_engine()' -A 30 tests/run-tests.sh
grep -n 'ONEUP_RUN_STATE\|ONEUP_STOP_FILE\|ONEUP_ZYPP_PID_FILE' tests/run-tests.sh | head
```

- [x] **Step 2: Write the document**, settling:
      - **A test never depends on, or damages, the machine.** With the precedent: 40 tests
        once failed because the machine happened to be running zypper, and a suite run
        during a real update deleted that run's `run.state` (ONEUP-0045/0050/0055). Every
        engine invocation redirects the three state paths; a scenario that bypasses
        `run_engine` repeats the overrides by hand.
      - **The mock-PATH sandbox:** fake `zypper`, `flatpak`, `sudo`, `snapper`; no root,
        no network.
      - **One invariant, one test.** Each spec INV names the test that locks it in; a spec
        invariant with no test is an incomplete spec.
      - **The four correctness invariants that must never regress** (from CLAUDE.md):
        reboot advice only when earned; a failed step continues the run; a package-only
        change offers a service restart, not a reboot; `--check` is read-only and rootless
        (the mock exits 99 if it is not).
      - **A passing suite is silent.** Live finding, 2026-07-26: `tests/gui-smoke.py`
        passes 283/283 while printing `RuntimeError` tracebacks from teardown. Noise
        in a green run trains you to ignore output. Already filed as **ONEUP-0062** at
        discovery; state the rule here. *Measured at `416caa4`: **28** tracebacks, exit 0.*
      - **New in 2.0:** the Python engine makes *unit* tests possible for parsers, which
        the Bash one could only test end-to-end. Unit-test the parser, keep the end-to-end
        scenario for the contract.
      - **Determinism:** no reliance on wall-clock timing, ordering of a real filesystem,
        or a network.

- [x] **Step 3: Verify the ~26-traceback claim before writing it as fact:**

```bash
python3 tests/gui-smoke.py 2>&1 | grep -c RuntimeError; echo "exit=$?"
```
      Expected: a non-zero count with the suite still reporting `Failed: 0`. If the count
      is now zero, delete the claim.

- [x] **Step 4: Commit.**

```bash
git add docs/standards/testing.md
git commit -m "ONEUP-0057: settle test isolation, the mock sandbox and invariant traceability"
```

---

### Task 6: `ui-and-accessibility.md` — absorbing `dialogs.md`

**Files:** Create `docs/standards/ui-and-accessibility.md`; Delete
`docs/standards/dialogs.md`; Modify `CLAUDE.md:209` region (the accessibility pointer)

- [x] **Step 1: Read both sources in full** — nothing in either may be lost:

```bash
cat docs/standards/dialogs.md
grep -n '^#\{1,3\} ' docs/specs/ONEUP-0028-accessibility.md
```

- [x] **Step 2: Write the merged document**, settling:
      - **Dialogs** (verbatim from `dialogs.md`): theme-matched by inheritance from the
        app-wide stylesheet; centred over the main window via the existing helper — no
        third centring path, no per-dialog palette. Wayland ignores `move()`, which is why
        the helper exists (ONEUP-0049).
      - **Accessible name on every focusable widget** — `tests/gui-smoke.py` fails on a
        nameless one.
      - **State is never signalled by colour alone.** Every colour cue is paired with text
        or shape.
      - **Text scales**: font sizes derive from the desktop's point size, never hard-coded
        `px`.
      - **No focus ring** — a deliberate user-facing decision (2026-07-25): focus reuses
        the hover look. Qt ignores `outline-radius`, so a ring draws square.
        **Scope, clarified by the user 2026-07-26:** the rule is about **focus** borders
        only. **Ordinary borders are fine** — a button may look like a button, a card may
        have an edge. What must never appear is a border or outline drawn to mark the
        focused/highlighted control. Write the rule at that width, and state what carries
        focus *instead* (the hover treatment — fill and contrast shift), because "no ring"
        on its own is a prohibition and a standard has to give the alternative. An earlier
        revision of this plan widened it to "no borders on buttons or links at all"; that
        was a misreading and is corrected here.
      - **New, for themes (ONEUP-0027):** every theme must satisfy the contrast rule and
        the colour-never-alone rule; a theme that cannot is not shipped. State how a new
        theme is checked.
      - **New, for right-to-left languages (ONEUP-0032, design §5.1):** the window must
        mirror for Hebrew and Arabic. Write these as rules a future widget must obey:
        - **Never use a directional stylesheet property** — `margin-left`, `padding-right`,
          `border-left` and friends. Qt does **not** mirror stylesheets, so each one is a
          bug that only appears in Arabic. There are **0** in `updater.py` today
          (verified at `ff4f4a7`); the rule exists to keep it that way.
        - **Never hard-code `AlignLeft` / `AlignRight`** for text that could be
          translated. Also **0** today.
        - **Custom painting must apply the layout direction itself.** Qt mirrors layouts,
          not `paintEvent`. Name the live example: the toggle in `updater.py:699` computes
          its knob position from the left edge (line 712) and is the one thing in the app
          that would mirror wrongly.
        - **Layout direction is never assumed from the widget** — read it from the
          application, so every widget agrees.

- [x] **Step 3: Remove the absorbed file and repoint its readers.**

```bash
git rm docs/standards/dialogs.md
grep -rn 'standards/dialogs' --include='*.md' . | grep -v CHANGELOG
```
      Fix every hit except `CHANGELOG.md` — changelog entries are history and are never
      rewritten.

- [x] **Step 4: Commit.**

```bash
git add -A docs/standards CLAUDE.md
git commit -m "ONEUP-0057: merge the dialog and accessibility rules into one UI standard"
```

---

### Task 7: `wording-and-translation.md`

**Files:** Create `docs/standards/wording-and-translation.md`

**Consumes:** design §5.1 (the engine emits codes; the window does all wording).

- [x] **Step 1: Sample the strings that exist**, so the rules are drawn from real text:

```bash
grep -n '@@HINT@@\|@@REMEDY@@' update_system.sh | head -20
```

- [x] **Step 2: Write the document**, settling:
      - **Plain English, no jargon** — the user is not a programmer. With before/after
        examples taken from Step 1's real hints.
      - **Never blame the user**; say what happened and what to do next.
      - **Never claim what was not earned** — no "up to date" that was not checked
        (ONEUP-0056), no success a step did not achieve.
      - **All wording lives in the GUI** (design §5.1). The engine emits stable codes.
        Root-side code does no translation.
      - **Every user-facing string is wrapped** for translation; no sentence assembled by
        concatenation (word order differs between languages); numbers use plural forms;
        translator comments where a string is ambiguous out of context.
      - **The `.ts`/`.qm` workflow** and where catalogues live.
      - **Marker payloads are not user-facing text** once §5.1's change lands — they are
        identifiers, and renaming one is a contract change (Task 9).

- [x] **Step 3: Commit.**

```bash
git add docs/standards/wording-and-translation.md
git commit -m "ONEUP-0057: settle how user-facing text is written and translated"
```

---

### Task 8: `workflow.md`

**Files:** Create `docs/standards/workflow.md`

- [x] **Step 1: Confirm the release machinery before describing it:**

```bash
grep -n 'six\|lockstep' local-CI.sh | head
./bump.py --help 2>&1 | head -5 || head -20 bump.py
```
      **Done, and widened** — `release.sh`, `githooks/pre-push` and `release.yml` were read
      as well, because the document describes the whole path from commit to release and
      each of the three owns part of it.

- [x] **Step 2: Write the document**, settling:
      - **The v1 freeze** (design §5.4) in the user's own definition: `main` takes a
        change only when people can no longer install system, Flatpak or firmware
        updates — with the two readings inside it (a silent wrong verdict counts; a
        machine left damaged counts) and the outside trigger (zypper changing its output).
        No feature work on `main` during the freeze.
      - **Branches:** `v2` is long-lived and shared, so it is **never rebased**; `main`
        merges *into* `v2` after any 1.4.x release, never the reverse.
      - **Commits:** `<ID>: <description>`; the release commit is `OneUp X.Y.Z`; body
        explains *why*.
      - **Roadmap IDs:** allocated from `.roadmap-counter`, which is git-ignored on
        purpose (every branch would otherwise conflict on it); the rebuild one-liner lives
        in `.gitignore`.
      - **The six version sites** and the rule never to hand-edit them — `./bump.py`
        rewrites all six and `local-CI.sh` gates on their agreement.
      - **`./local-CI.sh` green before every push**, enforced by `githooks/pre-push`.
      - **Semver for this project:** 2.0.0 is major because the engine is replaced; the
        release gate is design §7.
      **Done. Three facts were measured rather than assumed, and one of them changed what
      the document says:** the repository is **PUBLIC** (`gh repo view`), so pushes are
      free and the standard says push as you go rather than batching; `release.yml`
      triggers on **tags only**, so an ordinary commit push runs no CI at all; and the
      history has **zero merge commits, no `CODEOWNERS` and no branch protection**, so the
      standard records direct-to-branch commits as the real workflow instead of describing
      a pull-request gate that does not exist. `release.sh`'s `read -rp` confirmation is
      written up in §8 as intended behaviour (a release is not unattended), together with
      the reason its `git add -A` is safe — the clean-tree precondition is checked first
      and is fatal.

- [x] **Step 3: Commit.**

```bash
git add docs/standards/workflow.md
git commit -m "ONEUP-0057: settle the freeze, branch policy, commits and the release flow"
```

---

### Task 9: `marker-protocol.md` — the frozen contract

**Files:** Create `docs/reference/marker-protocol.md`

**Produces:** the reference Task 12's spec freezes and Task 16's spec deliberately changes.

- [x] **Step 1: Enumerate the markers from both sides — the document is only correct if
      the two agree:**

```bash
grep -oE '@@[A-Z_]+@@' update_system.sh | sort -u
grep -n 'handle_marker' -A 60 updater.py | head -80
grep -oE '@@[A-Z_]+@@' tests/run-tests.sh | sort -u
```
      Expected: 23 markers. **Any marker the engine emits that the GUI does not parse — or
      the reverse — is a finding**, recorded as a roadmap bullet in Task 18.
      **Done — 23, and no asymmetry.** The engine emits 24 distinct `@@…@@` tokens, one of
      which (`@@MARKER@@`) is the header comment's own placeholder, not a marker. Both
      directions check out: `handle_marker` reads 21, and the remaining two (`SIZE`,
      `AUTH`) are read by the `--size` and `--auth-status` side-channel handlers. That
      split is itself a trap worth documenting — a marker emitted on a side channel never
      reaches `handle_marker` — so the reference states it in §2.

- [x] **Step 2: Write the reference.** One row per marker: name, field list in order,
      each field's meaning and type, who emits it, who consumes it, and what the GUI must
      do when a field is `0`/absent. Cover in particular:
      - `PROGRESS|key|done|total|phase[|bytes|bytes_total]` — **total 0 means unknown**,
        rendered as a running tally, never an invented denominator; both zypper wordings
        for the download total are parsed.
      - `DONE|ok|errors|stopped` — `stopped` means neither success nor failure; for a
        *followed* run there is no exit code, so a followed run that never printed `DONE`
        is reported as errors, never success.
      - `REFRESH|done|total|alias` — exists because the metadata fetch is otherwise
        invisible (zypper prints dots with no line ending); byte figures are impossible
        here because the staging directory is root-only.
      - `SNAPSHOT` (singular, the rollback target) vs `SNAPSHOTS` (plural, the pile-up
        advisory) — distinct markers, a documented trap.
      - `REBOOT|yes|no[|reason]` — the optional third field, shown verbatim.
      - The **rules for changing the contract**: a rename or field change touches the
        engine, the GUI parser and both suites in one commit; during 2.0 the contract is
        frozen (design §3) with the single exception of §5.1's codes change.

- [x] **Step 3: Verify the count in the document matches the tree:**

```bash
grep -c '^| `@@' docs/reference/marker-protocol.md
```
      Expected: 23. If it differs, the document is wrong, not the engine.
      **Done — 23, and the check was strengthened.** A count alone would pass with the
      right number of *wrong* names, so the document's marker column was extracted and
      `diff`ed against the engine's own `@@…@@` tokens: identical. Writing the §7 drift
      table nearly broke this gate — its rows began `| \`@@`, which the count would have
      read as three extra markers. Restructured so exactly one table in the file has that
      shape. **Three inaccuracies in the engine's header comment were found and filed as
      ONEUP-0066** (`STEP_END`'s field count, `REPO`'s third field, `DONE|stopped`); not
      patched, because `main` is frozen and only the comment is stale — the emitters and
      the parser agree.

- [x] **Step 4: Commit.**

```bash
git add docs/reference/marker-protocol.md
git commit -m "ONEUP-0057: write the engine-to-window contract down properly"
```

---

### Task 10: Cold-eyes batch 1 — the standards and the reference

**Files:** all of Tasks 1–9; loop log appended to each document reviewed.

- [x] **Step 1: Run `/cold-eyes`** over `docs/standards/*.md` and
      `docs/reference/marker-protocol.md`. **Done — nine lanes**, cheap breadth over all of
      them then a strong depth pass over the six that flagged anything (wording,
      workflow+dependencies and the marker reference came back clean and were not re-read).
- [x] **Step 2: Verify every finding against the tree before acting on it.** A reviewer
      claim is a hypothesis. Fix CRITICAL/HIGH/MEDIUM/LOW; leave INFO. A LOW that proves
      wrong is dropped *explicitly*, with a line saying so — never silently filtered.
      **Done.** Loop 1: 9 critical, 19 high, 28 medium, 30 low — 82 verified, 4 not. Loop 2:
      6 suspects, 2 verified, 4 dismissed with the reason recorded in the log.
- [x] **Step 3: Loop.** Run again, **cold** — do not brief the reviewer on earlier
      findings. **Done, and it did its job:** nothing from loop 1 resurfaced, which is the
      proof the fixes held. Loop 2's only verified findings were precision, so the pass
      converged and all ten documents flipped from Draft to Reviewed.
- [x] **Step 4: Write the loop log** into each document as the loops happen. Never
      back-fill. **Done — two rows in each of the ten.**
- [x] **Step 5: Commit** after each loop:

```bash
git add docs/standards docs/reference
git commit -m "ONEUP-0057: cold-eyes loop N on the standards — <what changed>"
```

---

### Task 11: `CLAUDE.md` becomes a map that keeps the traps

**Files:** Modify `CLAUDE.md` (260 lines today)

**Consumes:** every standard, now reviewed. Runs *after* Task 10 so it points at documents
that have been proven correct.

- [x] **Step 1: Classify every rule currently in `CLAUDE.md`** into: (a) now covered by a
      standard → replace with a pointer; (b) a **trap** — a rule that cost a real bug to
      learn → keep a terse statement *and* point at the standard; (c) orientation (what
      the app is, how to run it) → keep.
- [x] **Step 2: Rewrite.** The traps that stay, at minimum: sudo in subshells; never
      signal the engine mid-transaction; `tee -a -p` so a quitting GUI cannot SIGPIPE the
      engine; tests must not read or damage machine state; anything spawned must not
      outlive the engine; a slow server must never look like a hang.
      Reason this is not pure de-duplication: **`CLAUDE.md` is loaded into every session
      automatically; the standards are not.** A trap that exists only in a standard can be
      walked straight past.
- [x] **Step 3: Verify every pointer resolves:**

```bash
grep -oE 'docs/[a-z/-]+\.md' CLAUDE.md | sort -u | xargs ls
```
      Expected: no "No such file".
- [x] **Step 4: Commit.**

```bash
git add CLAUDE.md
git commit -m "ONEUP-0057: shrink CLAUDE.md to a map that still carries the traps"
```

---

### Task 12: Revise `ONEUP-0054-python-engine.md`

**Files:** Modify `docs/specs/ONEUP-0054-python-engine.md` (276 lines, draft)

- [x] **Step 1: Refresh every figure.** The draft cites `ea51adc`; the tree is `b6d37ed`:

```bash
wc -l update_system.sh updater.py tests/run-tests.sh tests/gui-smoke.py
bash tests/run-tests.sh 2>&1 | tail -3      # 205 assertions over 76 scenarios
python3 tests/gui-smoke.py 2>&1 | tail -3   # 283
```
      **Done, but not the way this step assumed.** §6b landed after this plan was written
      and outranks it (`documentation.md` §1.1): most counts belong out of a document
      altogether. So the line counts and suite tallies were **cut**, not refreshed; the
      figures that stayed are the ones that carry an argument, in §6b.4's measured-and-
      past-tense form. Three were wrong, not merely stale: **57 sudo call sites → 34**
      (14 `sudo_capture` + 20 direct `sudo`, the helper's own two excluded); `history.json`
      and `~/.local/state/oneup/logs/` are the **window's**, not engine contracts; and the
      "ONEUP-0047 wording canary" is the Stop button — the canary is a scenario in
      `tests/run-tests.sh`, with no roadmap id.
- [x] **Step 2: Reconcile the contradiction.** The draft's header says the ONEUP-0034 GUI
      split lands "in the same package"; the roadmap says keep it separate. The design
      settles it: separate items, split first, both on `v2`. Fix the header.
      **Done** — `Kind:` is now plain `implement`, and new §3.1 states the relationship:
      shared package, shared branch, split lands first, separate gate.
- [x] **Step 3: Conform to Task 1's template** — add any missing section, and the Status
      header with the verification commit. **Done.** Full §3 header block; the eleven
      template sections in order; the ten-row invariant table rewritten as INV-1…INV-11,
      each naming the scenario that proves it. Two by-products: the spec dropped out of
      `docs-check.py`'s `GRANDFATHERED` set (§3 says a grandfathered spec is brought to
      shape the next time it is edited — proved by seeding a bad `Status` and watching §3
      fail), and its 7 line-number citations went, so ONEUP-0065 is down to 62 across four
      specs. The tally is corrected in `docs-check.py`, `documentation.md` and the roadmap
      bullet, per §9's *search for who cited it*.
- [x] **Step 4: Point at the design** for everything cross-cutting (§4 layout, §5.1
      codes, §7 gate) instead of restating it, so the two cannot drift. **Done, and the
      drift was already real:** the draft's own gate table said "197/197" and "277/277"
      where the design's says no assertion changed. The spec now keeps only the *how it is
      checked* column and points at design §7 for the conditions.
- [x] **Step 5: Commit.**

```bash
git add docs/specs/ONEUP-0054-python-engine.md
git commit -m "ONEUP-0054: refresh the spec's figures and conform it to the standards"
```

---

### Task 13: Cold-eyes batch 2 — the design and the engine spec

- [x] **Step 1: Run `/cold-eyes`** over `docs/design/oneup-2.0.md`,
      `docs/specs/ONEUP-0054-python-engine.md` **and `docs/standards/workflow.md`**.
      Workflow was added to this batch on 2026-07-27: it is `Reviewed`, but §8.1 (no
      fourth distribution path, ONEUP-0071) was written after batch 1 and no cold reader
      has seen it. Global rule 14 applies to an edited standard, and §8.1 makes a claim
      about the Flatpak sandbox and the privilege boundary that is worth checking.
- [x] **Step 2–4:** verify, fix by severity, loop cold until clean, log as you go —
      exactly as Task 10. **Done — nine loops.** 8 full loops plus a cheap closing pass;
      roughly 380 findings raised, ~330 verified and fixed. Nothing a loop fixed ever
      resurfaced. All three flipped `Draft` → `Reviewed`.
- [x] **Step 5: Commit** per loop: nine commits, one per loop.

```bash
git add docs/design docs/specs
git commit -m "ONEUP-0057: cold-eyes loop N on the 2.0 design and engine spec — <what changed>"
```

---

### Task 14: `ONEUP-0034-gui-modules.md` — the GUI split

**Files:** Create `docs/specs/ONEUP-0034-gui-modules.md`

- [x] **Step 1: Map the seams before proposing them:**

```bash
grep -n '^class \|^def ' updater.py
```
      Group the result by responsibility: main window, dialogs (Settings, Repositories,
      About, Rollback), the marker parser, the QProcess launch layer, banner/remedy state,
      tray + autostart, and the pure helpers.
- [x] **Step 2: Write the spec** to the template. It must settle: the module list and what
      each owns; the import direction (no cycles; `gui/` may not be imported by `engine/`);
      which public names `tests/gui-smoke.py` imports and must keep working; and that the
      split is **behaviour-preserving** — no user-visible change, the 283 GUI tests
      unchanged.
- [x] **Step 3: Name the invariants**, at minimum: the marker parser's behaviour is
      identical; every accessible name survives; no dialog loses its centring; the app
      still launches from `updater.py` at the repo root (packaging depends on it).
- [x] **Step 4: Verify the test-imported names:**

```bash
grep -n '^from updater import\|^import updater\|updater\.[A-Za-z_]*' tests/gui-smoke.py | head -20
```
- [x] **Step 5: Commit.**

```bash
git add docs/specs/ONEUP-0034-gui-modules.md
git commit -m "ONEUP-0034: spec the GUI module split"
```

---

### Task 15: `ONEUP-0027-themes.md`

**Files:** Create `docs/specs/ONEUP-0027-themes.md`

**Confirmed by the user, 2026-07-26:** themes are **required for 2.0**, not optional. The
item's place in the release is settled; only the design questions in Step 2 remain.

- [x] **Step 1: Read how theming works today:**

```bash
grep -n 'build_theme\|apply_theme\|current_is_dark\|colorSchemeChanged' updater.py
```
- [x] **Step 2: Ask the user the open questions** the roadmap already flags, because they
      are preference, not fact: how many themes, whether "Follow system" stays the
      default, and where the picker lives. Do not invent answers.
- [x] **Step 3: Write the spec** to the template, settling: the theme list; where the
      preference is stored; that switching applies live to the main window **and every
      dialog** (they inherit the application stylesheet — Task 6); and that each theme is
      checked against the contrast and colour-never-alone rules before it ships.
- [x] **Step 4: Name the invariants**, at minimum: no theme signals state by colour alone;
      every theme keeps every accessible name; "Follow system" still switches live on
      `colorSchemeChanged`; an unknown/corrupt stored theme name falls back rather than
      failing to start.
- [x] **Step 4a: Cover the painted widgets** — measured 2026-07-26 and recorded on the
      ONEUP-0027 bullet: **ten colours sit outside the theme machinery** and no stylesheet
      can reach them (`GREEN`/`RED` at `updater.py:222-223`, `TRAY_ATTENTION_COLOR` at 141,
      and seven `QColor` calls inside the `ToggleSwitch` and tray `paintEvent` overrides at
      691, 719, 722, 725, 2072, 2078, 2090). `paintEvent` bypasses QSS entirely, so a new
      theme would leave the on/off switch and tray badge at their old colours — and those
      are precisely the surfaces carrying state meaning. The spec must define theme tokens
      the painters read, and the contrast check must cover painted surfaces too.
- [x] **Step 5: Commit.**

```bash
git add docs/specs/ONEUP-0027-themes.md
git commit -m "ONEUP-0027: spec selectable themes"
```

---

### Task 16: `ONEUP-0032-i18n.md`

**Files:** Create `docs/specs/ONEUP-0032-i18n.md`

- [x] **Step 1: Count the surface:**

```bash
grep -coE '"[A-Z][^"]{12,}"' updater.py
grep -n '@@HINT@@\|@@REMEDY@@' update_system.sh | wc -l
```
- [x] **Step 2: Write the spec** to the template, settling: how strings are wrapped; the
      `.ts`/`.qm` build step and where catalogues live; and how a missing catalogue
      degrades (English, never a blank label).
      **Answered by the user, 2026-07-26 — no longer an open question:** 2.0 ships the
      **groundwork only, English alone**; additional languages come after 2.0 is released
      (design §5.1). The spec states that as a scope decision and puts a translated locale
      file in its own "Out of scope" section, so a later reader sees a decision rather than
      an omission.
- [x] **Step 3: Specify the contract change** from design §5.1 explicitly: `HINT` and
      `REMEDY` payloads become stable codes; the GUI holds the wording; the marker
      reference (Task 9), both test suites and the GUI parser change **in one commit**;
      and it happens **after** the engine rewrite has passed its gate, never inside it.
- [x] **Step 4: Specify right-to-left support** (design §5.1 — user's requirement,
      2026-07-26). Settle: where the application's layout direction is set and from what;
      that it is set **once**, at startup, not per widget; and that the toggle's custom
      `paintEvent` (`updater.py:699`, knob position at line 712) applies the direction to
      its knob arithmetic while leaving the symmetric state shapes alone. Verify Qt's own
      mechanism for deriving direction from the locale against the installed Qt's
      documentation before writing it down — do not state it from memory.
- [x] **Step 5: Name the invariants**, at minimum: the engine imports no translation
      machinery (it is the root-privileged half); an unknown code renders as something
      readable rather than raw; no user-facing sentence is built by concatenation (there
      are 10 concatenation sites in `updater.py` today, verified at `ff4f4a7`); **no
      directional stylesheet property or hard-coded `AlignLeft`/`AlignRight` exists**
      (both are 0 today, so the test is a guard, not a clean-up); and **the window opens
      and every smoke assertion passes with the layout direction forced right-to-left** —
      a new pass in `tests/gui-smoke.py`, because on an English desktop nobody will ever
      see an RTL regression by eye.
- [x] **Step 6: Commit.**

```bash
git add docs/specs/ONEUP-0032-i18n.md
git commit -m "ONEUP-0032: spec translation groundwork"
```

---

### Task 17: `ONEUP-0064-interface-redesign.md`

**Files:** Create `docs/specs/ONEUP-0064-interface-redesign.md`

**Requested by the user, 2026-07-26**, as part of 2.0 rather than polish after it. Three
priorities in the user's own order: **ergonomics, user-friendliness, accessibility.**

**The constraints, as clarified by the user 2026-07-26.** Three, and they are design
instructions rather than suggestions — the spec works within them rather than reopening
them:

1. **No focus borders.** Ordinary borders are fine and always were; what must not appear
   is a border or outline drawn to mark the focused/highlighted control. This restates the
   2026-07-25 no-focus-ring decision at its original width. (An earlier revision of this
   task widened it to "no borders at all" — a misreading, corrected.)
2. **The phone-style on/off switches stay.** The user's long-standing preference over
   checkboxes, specifically because on/off reads at a glance. A fixed point, not a
   candidate.
3. **Free rein otherwise.** The user's words: propose and build, and we tweak afterwards.
   So this task does **not** stop to ask how far the layout may move.

- [ ] **Step 1: Read what the interface is today** before proposing anything different.
      The redesign is judged against the current window, so measure it:

```bash
grep -n 'setAccessibleName\|addWidget\|addLayout' updater.py | wc -l
grep -n 'class .*Q\(Dialog\|MainWindow\|Widget\|Frame\)' updater.py
```
- [ ] **Step 2: Answer the ringless-focus question head-on.** Without a focus ring, a
      keyboard user still has to know where they are. WCAG 2.2 SC 2.4.11 (focus not
      obscured) and SC 1.4.11 (non-text contrast) do not go away because the ring is off
      the table. Settle in the spec how focus is conveyed instead — the hover treatment
      (fill and contrast shift) is the existing answer and the likely one — and **measure
      the contrast ratios**, do not assert them. If a chosen treatment cannot meet the
      ratio, say so and pick another. Note this is the *narrower* question than an earlier
      revision posed: affordance may still use an ordinary border, so only focus needs a
      non-border answer.
- [ ] **Step 3: Do not stop to ask.** The user granted free rein (2026-07-26) with two
      fixed points — no focus borders, and the on/off switches stay. Propose the design and
      build it; tweaks come after. Bring recommendations, not questions.
- [ ] **Step 4: Write the spec** to the template, settling: what changes and what
      deliberately does not; the affordance and focus treatment from Step 2 with its
      measured ratios; how the five task rows, the progress area, the log pane and the
      header controls are arranged; and what a first-time user is expected to understand
      without reading anything.
- [ ] **Step 5: Name the invariants.** ONEUP-0028's floor is a regression bar, not a
      starting position: every focusable widget keeps an accessible name (`gui-smoke.py`
      fails on a nameless one); **no state is signalled by colour alone**; font sizes stay
      derived from the desktop point size, never hard-coded `px`. Add the redesign's own:
      focus is never marked by a border or outline, yet is always visibly located; every
      control reachable and operable by keyboard alone; the on/off switches survive the
      redesign with their state still readable without relying on colour.
- [ ] **Step 6: Record the sequencing** the design doc §5.2 now fixes — the redesign lands
      **after** the GUI split (0034) and **before** themes (0027) and translation (0032),
      because it restructures what those two then style and translate.
- [ ] **Step 7: Commit.**

```bash
git add docs/specs/ONEUP-0064-interface-redesign.md
git commit -m "ONEUP-0064: spec the interface redesign"
```

---

### Task 18: Cold-eyes batch 3 — the four new specs

- [ ] **Step 1: Run `/cold-eyes`** over the four specs that have never been gated on their
      current bytes — **ONEUP-0064**, **ONEUP-0072**, **ONEUP-0076**, **ONEUP-0077** — each
      from **loop 1**, because every one carries a `0-split` provenance row and none of the
      parents' loops transfer. Then **ONEUP-0032** (a real loop, not a cheap pass — see the
      resume block) and a cheap citation pass over **ONEUP-0027**. **ONEUP-0034** needs
      nothing: untouched since its own four-loop gate.
      - [x] **ONEUP-0077** — done 2026-08-03, three loops (21, 23, 20 verified), converged by
        cap, `Status: Reviewed`. Commits `b314c2e`, `a8c8f79`, `fe0beb9`, `a8f9cf3`. Added
        INV-6 and INV-7; corrected `oneup-2.0.md` §5.2, `ONEUP-0072` §8 and `ONEUP-0032` §4.2;
        filed **ONEUP-0082**.
      - [x] **ONEUP-0064** — done 2026-08-04, three loops (30, 28, 23 verified), converged by
        cap, `Status: Reviewed`. Commits `d0eb6b8`, `a355419`, `633c85d`. Added INV-6 and
        INV-7; corrected `oneup-2.0.md` §5.2 and `ONEUP-0076` §10. **Collateral outran draft
        defects two loops running** (30/0 → 8/20 → 4/19), which is the stop signal as well as
        the cap — both criticals in loop 3 were invariants loop 2 had itself written.
      - [~] **ONEUP-0072** — **two of three loops done 2026-08-05**, session ended cleanly.
        Loop 1: 24 verified, all fixed (3 criticals, all split leftovers or claims the code
        contradicts). Loop 2: 25 verified, 24 fixed, **1 surfaced**, 0 criticals. Commits
        `9b1d75d`, `96b7621`, `8fd3ca1`. Loops 3 and 4 ran 2026-08-12: 14 verified, all
        fixed, and the run then stopped because loop 4's collateral outran its draft
        defects — the split signal, filed as **ONEUP-0101**. The open question is closed
        (the user chose the English branch). **Read the spec's own §11 loop log**; the
        run-state note is gone under `documentation.md` §7.1. Still `Status: Draft`,
        deliberately — the gate never returned an empty loop.
      - [ ] **ONEUP-0076** (630)
      - [ ] **ONEUP-0032** · [ ] **ONEUP-0027** (cheap)
- [ ] **Step 2–4:** verify, fix by severity, loop cold until clean, log as you go.
- [ ] **Step 5: Commit** per loop:

```bash
git add docs/specs
git commit -m "ONEUP-0057: cold-eyes loop N on the 2.0 specs — <what changed>"
```

---

### Task 19: Close the documentation set

- [ ] **Step 1: Cross-document consistency sweep.** Every internal link resolves; no
      document contradicts the design; every 2.0 item in design §1 has a spec or a stated
      reason it has none:

```bash
grep -rhoE '\bdocs/[a-zA-Z0-9/_.-]+\.md' docs/ CLAUDE.md README.md | sort -u | xargs ls
```
      Expected: no "No such file".
- [ ] **Step 2: File any remaining findings** as roadmap bullets — any marker asymmetry
      (Task 9), and any rule Task 4 found the engine does not actually follow.

      **Filed as they were found, not deferred to here** (2026-07-26): ONEUP-0058
      (test suite writes to `~/Documents`), ONEUP-0059 (XDG paths), ONEUP-0060 (unpinned
      PySide6/PyInstaller in the AppImage build), ONEUP-0061 (QSettings migration),
      ONEUP-0062 (the 28 GUI-suite teardown tracebacks, measured at `416caa4`),
      ONEUP-0063 (`pyproject.toml`, and the six `# noqa: S` comments that currently
      suppress nothing), ONEUP-0065 (the 130 line-number citations left in the older
      documents), ONEUP-0066 (three stale entries in the engine's own marker list). Two further findings
      were folded into existing bullets rather than duplicated: the painted widgets no
      theme can reach (ONEUP-0027) and the single-file test loader the GUI split breaks
      on, plus the untested GUI-side locale pin (ONEUP-0034). Filing at discovery is the
      rule — a gotcha held until close-out is a gotcha that gets lost.
- [ ] **Step 3: Record the outcome on ONEUP-0057** and flip it to shipped, listing the
      documents produced and the loop counts.
- [ ] **Step 4: Add a CHANGELOG `[Unreleased]` entry** — documentation-only, but it is
      what 2.0 is built on.
- [ ] **Step 5: Final gate and push.**

```bash
./local-CI.sh && git push origin main
```

---

## Self-review

**Coverage.** Design §1's **seven** items: 0054 → Task 12; 0034 → Task 14; 0027 → Task 15;
0032 → Task 16; **0064 → Task 17**; 0044 and 0004 → no spec by design §6.2/§6.3, and the
coding standard (Task 3) carries the Python-floor decision 0004 needs. The nine standards
→ Tasks 1–8 plus the existing `dependencies.md`. The reference → Task 9. The three
cold-eyes batches → Tasks 10, 13, 18. `CLAUDE.md` → Task 11.

**Task 17 was added 2026-07-26** at the user's request (the interface redesign), which
renumbered the old Tasks 17 and 18 to 18 and 19. It sits after the two specs it
constrains — themes (15) styles the redesigned layout and translation (16) wraps its new
wording — so batch 3 (Task 18) still cold-eyes all four specs together.

**Placeholders.** Three tasks originally stopped to ask the user rather than inventing an
answer. **Two are now answered (2026-07-26)** and the tasks proceed without pausing:

- *Does 2.0 include themes?* — **yes, required** (Task 15 proceeds; only the sub-questions
  in its Step 2 — how many themes, whether "Follow system" stays the default — remain, and
  they are asked together when the spec is written).
- *Does a locale ship in 2.0?* — **no: groundwork only, English alone, languages after
  release** (Task 16 Step 2, design §5.1).

**The third is now answered too (2026-07-26).** The Python floor was settled from fact
without asking: Leap 15.6 reached end-of-life on 2026-04-30, so the oldest *supported*
Leap is 16.0, whose release notes put `/usr/bin/python3` at **3.13** — the same as
Tumbleweed. See `docs/standards/coding.md` §1.

**One open question remains, in Task 15 Step 2**: how many themes and where the picker
lives — genuine preference rather than fact, and asked *with a recommendation attached*,
never handed back bare.

**Task 17 no longer asks anything.** The user granted free rein on the redesign
(2026-07-26) with two fixed points — no focus borders, and the on/off switches stay — so
the spec proposes and builds rather than pausing. Nothing else defers.

**Consistency.** Task 1 defines the spec template; Tasks 12, 14, 15 and 16 all name it as
the shape they follow. Task 2 defines the `oneup/` layout; Tasks 12 and 14 consume it.
Task 9's marker reference is frozen by Task 12 and changed by Task 16 — the one
intentional exception, stated in both.

**Ordering risk.** Task 11 (`CLAUDE.md`) deliberately runs after Task 10's review, so it
cannot point at unreviewed rules.
