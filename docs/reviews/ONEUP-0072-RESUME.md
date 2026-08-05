# Cold-eyes run state — `docs/specs/ONEUP-0072-marker-codes.md`

**Stopped at the end of loop 2, cleanly.** Written 2026-08-05 because the session ended,
not because the run failed. Loop 3 is owed (`--max-loops 3`).

**Docs are at commit `96b7621`.** Both loops' fixes are in the tree and pushed. Working
tree clean, `./local-CI.sh` exit 0 (engine 210/0, GUI smoke 301/0, bump 12/0, docs-check
15534/0).

---

## Resume point

Loop 2 is **fully complete**: dispatched → verified → fixed → swept → loop-log row written
→ committed → pushed. Nothing is half-applied.

**To resume: run loop 3 — but read § The loop-3 decision first, because it may be the
wrong move.**

---

## The loop-3 decision — read before dispatching

| Loop | Verified | Draft defects | Fix collateral | Criticals | Doc lines after |
| --- | --- | --- | --- | --- | --- |
| 1 | 24 | 24 | 0 | 3 | 718 (from 597) |
| 2 | 25 | 10 | **15** | **0** | 812 (from 718) |

Two signals point in **opposite** directions, and this is the judgement the next session
inherits:

- **Toward stopping/splitting.** Collateral outran draft defects on the first split
  (15 vs 10), decisively. `~/.claude/skills/cold-eyes/references/loop-economics.md` says a
  decisive first-split margin licenses a **harder sweep**, which loop 2 performed (the
  fallback rule was deleted down to one owner in §4.3). The document has also grown
  **597 → 812 lines across two loops**, and its own pre-split loop 3 had already
  recommended splitting §4 rather than looping. §4 is now roughly 60% of the document.
- **Toward one more loop.** Criticals went 3 → 0, and loop 2's draft-defect half was still
  finding real contract gaps a cold read is the only way to reach (the engine's retained
  English; the G2/`differential-test.sh` gate).

**Recommendation, not a decision:** run loop 3 as the cap allows, and if its collateral
again outruns its draft defects, **split §4** rather than raising `--max-loops`. Splitting
at loop 3 is cheap; splitting at loop 8 means five loops were wasted. The user decides.

---

## OPEN — needs a decision from the user, blocks nothing else

**§4.3's plural-form mechanism does not cover English, and 2.0 ships English only.**
Surfaced, not fixed; it is written into §4.3 as a `⚠ OPEN` block so it cannot be lost.

Measured 2026-08-05 against PySide6 6.11 — **this is the expensive artifact in this file,
reproduce it only if you doubt it**:

```bash
# with a compiled .qm loaded, translate() DOES select a numerus form with no %n in source:
#   'the listed things installed' -> ['SING-NOVAR', 'PLUR-NOVAR', 'PLUR-NOVAR']  (n=1,2,5)
#   '%n thing(s) installed'       -> ['SING-1', 'PLUR-2', 'PLUR-5']
# with NO catalogue loaded, it returns the source verbatim for every n.
```

Method: hand-written `.ts` with `numerus="yes"` for a source string containing no `%n`,
compiled with `pyside6-lrelease`, loaded via `QTranslator.load` + `installTranslator`,
called as `QCoreApplication.translate(ctx, src, "", n)` for n ∈ {1, 2, 5}. The first,
catalogue-less run is the confound that makes the naive test inconclusive — do not repeat
that mistake.

**Consequence:** design §5.1 ships 2.0 with no locale file for any language, so English is
the only path that runs at launch, and one source string cannot yield both *was* and
*were* (there is no `(s)` idiom for a verb). As written, this item would **regress**
wording `reboot_reason_from_log` gets right today. Three ways out are stated in §4.3:
ship an English `.qm`; give the render function an explicit English branch; or re-word the
sentence, which §3.2 forbids this item doing alone.

---

## Context packet — rebuild, do not reuse

- Loop 2's packet is at `/tmp/claude-1000/.../scratchpad/ce-0072-l2/` and **will not
  survive a reboot**. Its `/doc-lint` figures and the 718-line count are now **stale** —
  the doc is 812 lines.
- **Rebuild from scratch each loop.** Appending to a previous packet once duplicated a
  section and both lanes hedged their findings on it.
- Recipe that worked (lanes came in at ~123k cumulative / ~42k first-turn, inside the 60k
  per-turn budget): `review-brief.md` verbatim + run context + `Verified source facts` +
  bounded `sed` windows over the cited code + the cross-reference passages + the settled
  `/doc-lint` results. ~115 KB packet, handed to every lane as **one shared file path**.
- **Withhold the loop log**: copy the doc to `/tmp`, cut at the line **before** the
  `## 11.` heading (cutting *at* it produces a duplicate heading and costs a lane finding),
  and append the standard placeholder. Verify no history leaked before dispatching.

## Verified source facts worth carrying forward (source unchanged since `dc509e8`)

These cost real lookups and are stable — put them in the next packet rather than
re-deriving. **Facts about the source only; no review history.**

- `marker HINT` × **14** call sites; the download-size one has a **4-arm `case "$rc"`**
  (7, 5, 6, `*`), the `*` arm interpolating `code $rc`.
- `marker REMEDY` × 3 call sites, **2** distinct actions (`import-keys`, `skip-repo`).
- `CHECK_UNKNOWN`'s reason is built by **3** branches; none has a verb after its list.
- `reboot_reason_from_log` builds 4 components verbatim: `"a new kernel"`,
  `"your NVIDIA graphics driver"`, `"your graphics driver"`, `"kernel driver modules"` —
  the two graphics ones mutually exclusive (`if/elif`). 3 reason sources total.
- **The engine uses each sentence twice** — `echo` at lines 370, 411, 505, and
  `DETAIL[$key]` consumed by the summary block at line 1515. This is loop 2's best draft
  finding; do not let a later loop "simplify" it away.
- `_step_badge`'s `skip` branch **reads `detail`**; only `fail` does not.
- `valid_alias` is called from exactly one place (inside `disable_repo`).
- 3 explicit fixed-shape parser guards: `STEP_BEGIN`, `PROGRESS`, `REFRESH`.
- `@@HINT@@` read in 4 places (1 in `handle_marker`, 3 side channels).
- `tests/differential-test.sh` **does not exist**; `ONEUP-0054` §4.5 owes it, and it is
  wired into neither `local-CI.sh` nor the release workflow today.
- `disable_repo` echoes no reason — `@@REPO_SKIPPED@@`'s reason is legible only inside the
  raw marker line.

## Settled — do not re-report, and do not re-verify

- `spec_query` returns `invariants_count: 0` for **every** spec in this project. That is
  **ONEUP-0075**, a parser defect, not a document defect.
- `spec_lint`'s `sections_checked` is `false` project-wide — this project's spec-format
  standard carries no machine-readable required-sections block, so that check never runs.
- The unlinked `**Sections:**` line is house style in all five specs;
  `documentation.md` §4 mandates no anchors. Dismissed in loop 1.
- `tests/docs-check.py`'s marker gate is `ONEUP-0054` §8's, and the marker name stays the
  first quoted argument after §4.2's signature change. Dismissed in loop 1.
- Resolved in the document's favour and **not** to be re-asked: the download-size four
  sentences into a fifth; both headless paths pass `--notify` today;
  `oneup/engine/markers.py` and `oneup/gui/markers.py` are two intended modules each cited
  correctly; design §4 supports the "all three packaging paths" claim.

## Fix ledger

`/tmp/claude-1000/.../scratchpad/ce-0072-l1/fix-ledger.md` — **not durable.** Every row is
`fixed` except:

- **H7 (loop 2)** — `surfaced`, the plural-form decision above. The only open row.
- **I1 (loop 2)** — INFO, carried: no budget pinned for the per-marker table lookup.
  `@@PROGRESS@@` is emitted per package during a download and INV-2's `|`→`/` rewrite now
  applies to every field of every marker; nobody has costed that. Not actionable this pass.

No row has an unfilled `disposition`, and no blast-radius cell is left without a verdict.

## Cross-document edits already made (so a later session does not redo them)

- `docs/design/oneup-2.0.md` **§4** — widened from the narrow `@@HINT@@`/`@@REMEDY@@`
  framing to "every engine payload the window renders as its own wording".
- `docs/design/oneup-2.0.md` **§7's G10 row** — same widening; §3.1 cites G10 by name.
- `docs/specs/ONEUP-0032-i18n.md` **§4.1** — the `steps.py` row now says this item *writes*
  the in-progress phrasing and 0032 only *marks* it.

Per `/cold-eyes`' own rule these three got **no lane, no loop-log row** — one fix is not a
review.

## Where this sits in the wider plan

`docs/plans/ONEUP-0057-documentation-set.md` Task 18. After ONEUP-0072 converges:
**ONEUP-0076** (630 lines), then **ONEUP-0032**, then a cheap citation pass on
**ONEUP-0027**. **ONEUP-0034** needs nothing. ONEUP-0064 and ONEUP-0077 are done
(`Status: Reviewed`) — do not re-review either.
