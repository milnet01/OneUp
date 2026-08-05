# Fix ledger — /cold-eyes on docs/specs/ONEUP-0072-marker-codes.md

Doc: `docs/specs/ONEUP-0072-marker-codes.md` (597 lines, Status: Draft, genre: spec)
Run: loop 1 on its own post-split bytes, 2026-08-05. `--max-loops 3`.

## Standing pair list (seeded before the first fix)

Walk these element-by-element on every sweep, not by reading each in turn:

- P-a **§5's invariant list ↔ §7's tests table ↔ §6's failure-mode table** — three
  sections independently enumerating the same contracts, with no shared token to grep.
- P-b **§4.1's "three fates" field lists ↔ `marker-protocol.md` §3's marker table** —
  the doc says §3 is "the authority on which fields exist".
- P-c **Every literal number in prose ↔ the list or table that owns it**
  (14 HINT sites · 3 CHECK_UNKNOWN reasons · 2 REMEDY actions · 3 REBOOT sources ·
  4 components / 11 subsets / 11 sentences · 3 render functions · 3 side-channel
  readers · 4 channels · 5 families · 3 guards · 6 version sites).
- P-d **§8's doc-edit list ↔ each named section actually saying what §8 claims** —
  and ↔ `ONEUP-0077` §8, which asserts what this spec gave up in the split.
- P-e **§3.3 / §7 / INV-4 / §6 / §10 ↔ the 0072↔0077 split boundary** — which item
  owns the headless notification.
- P-f **§4.2's code shape `^[a-z0-9-]+$` ↔ every example code written anywhere in the
  doc** (including §4.1's vocabulary table cells).

## Restructure record (what moved, for traceability — never briefed)

| was in | now in | what |
| --- | --- | --- |
| ONEUP-0032 (pre-split) | ONEUP-0072 | the payload conversion + INV-1…INV-5 |
| ONEUP-0072 §4.4 | ONEUP-0077 | the timer desktop notification, `--notify`/`--log=` |

## Rows

| # | loop | dim | finding | disposition | anchor | was → now | must_agree | cited_by | collateral | surfaced |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

### Phase 1b — findings that surfaced during packet construction

**PKT-1 — INV-4 asserts ONEUP-0077's deliverable, and is false on the day this item
lands.** Severity: **CRITICAL** (pending Phase 3 re-grade).
INV-4 reads *"The desktop notification the two headless paths raise is built by the
window, and neither passes `--notify` to the engine"*, with a `tests/gui-smoke.py`
test clause asserting `--notify` appears in no argument list the window builds. But
§10 puts the timer notification **out of scope** ("Split out to ONEUP-0077"), §8 says
"The two headless entry points are not this item's — `--notify` out, `--log=` in …
belong to ONEUP-0077, **which lands after this one**", and `ONEUP-0077` INV-2 claims
exactly this property ("no `--notify`, a `--log=` under the window's own `LOG_DIR`").
So an implementer building 0072 would add a test that fails, because the behaviour it
asserts arrives one item later. Split leftover.
Touches: §5 INV-4, §7 row 3, §6 row 9, §3.3 bullet 1.

**PKT-2 — §4.1 misstates `_step_badge`'s `skip` branch, and the design rule built on
it drops a badge.** Severity: **HIGH** (pending re-grade).
§4.1 says *"it returns on `status == "fail"` and `status == "skip"` before looking at
`detail` at all"*. The `skip` branch **does** read `detail`:
`return "Not installed" if "not installed" in detail.lower() else "Skipped"`. §2.1 of
the same document correctly lists `"not installed"` as a skip-branch substring, so the
document contradicts itself. Consequence: the rule *"the code decides it only for
`ok`"* would lose the "Not installed" badge, which is one of the couplings §2.1 exists
to remove.
Touches: §4.1 fate-2 precedence paragraph, §2.1, §6 row 2.

**PKT-3 — §4.1's `@@REBOOT@@` vocabulary table is headed "Codes" but its cells are
English prose, and the prose is not the engine's.** Severity: **MEDIUM** (pending
re-grade). The table's Codes column holds *"a new kernel · an NVIDIA graphics driver ·
a generic graphics driver · kernel driver modules"* and *"core system packages were
updated · firmware was updated"*. None matches §4.2's `^[a-z0-9-]+$`, so an
implementer cannot allocate from it. If the cells are instead meant as the *English*,
two are misquoted: the engine emits `"your NVIDIA graphics driver"` and
`"your graphics driver"`.
Touches: §4.1 vocabulary table, §4.2 code shape, §4.3 fallback example
(`gpu-firmware-blob` is correctly code-shaped, which sharpens the mismatch).

**PKT-4 — `oneup-2.0.md` §4 still carries the narrow "HINT and REMEDY" framing that
§3.1 exists to overturn, and §8's edit list does not name it.** Severity: **MEDIUM**
(pending re-grade). Design §4 reads *"ONEUP-0072 converts the `@@HINT@@` and
`@@REMEDY@@` payloads to codes (§5.1) after the switch-over"*, while design §5.1 has
already been widened to *"every engine payload the window renders as its own wording …
wider than the `@@HINT@@` / `@@REMEDY@@` pair this paragraph once named"*. §8 amends
`marker-protocol.md` §5.1/§5.2 for exactly this reason but leaves design §4 saying the
old thing — and §8 *relies* on design §4 for the CHANGELOG sentence.
Touches: §8 bullet 4, §3.1.

---

## Loop 1 — verified rows (opened BEFORE the fixes)

Lanes: A, B, C (general-purpose, one shared 115 KB packet). Cumulative spend
119,781 / 119,796 / 119,784 tokens — **cumulative, not per-turn**; first-turn
input was ~40k each, inside the 60k budget.

Tally: **CRITICAL 3 · HIGH 4 · MEDIUM 8 · LOW 10 · INFO 1** = 26 = verified 24 +
dismissed 2. Dimension tally: dim 2×2, dim 4×5, dim 5×7, dim 6×4, dim 7×2,
dim 8×3, dim 9×1, dim 10×2, dim 11×1(dismissed), dim 15×1.

| # | sev | dim | lanes | finding | disposition | must_agree |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | CRITICAL | 7 | A,B,C,pkt | INV-4 asserts ONEUP-0077's contract; false on landing day | fixed | §2.2, §3.3 b1, §5 INV-4, §6 r9, §7 r3, §7 ¶1, §9 b4, §10 |
| C2 | CRITICAL | 2 | B,C,pkt | §4.1 misstates `_step_badge`'s skip branch; rule drops "Not installed" | fixed | §2.1, §4.1 fate2, §6 r2, §4.3 |
| C3 | CRITICAL | 4 | A,B,C,pkt | §4.1 "Codes" table holds English prose; violates INV-1 and the space-separated field | fixed | §4.2 shape, INV-1, §4.3 example, §4.1 carve-out |
| H1 | HIGH | 4 | A | `count` optional-and-trailing vs §4.3 "every other converted code is fixed-arity" → countless runs badge as fallback | fixed | §4.1 fate2, §4.3 arity ¶, §6 r5 |
| H2 | HIGH | 5 | C | emitter's variadic signature has no omitted-trailing-field convention; `REBOOT\|no\|` breaks marker-protocol §4.8 | fixed | §4.2 signature ¶, INV-2, §4.1 count ¶ |
| H3 | HIGH | 10 | B | an *unknown* REBOOT token cannot be classed component-vs-standalone; renders inside the join frame | fixed | §4.1 vocab table, §4.3 fallback ¶, §6 r3 |
| H4 | HIGH | 5 | A | §4.3 attributes `and`-join + was/were to all three render fns; only REBOOT has a verb; prescribing it re-words two, which §3.2 forbids | fixed | §4.3 ¶2, §4.1 CHECK_UNKNOWN ¶, §3.2 |
| M1 | MEDIUM | 5 | A,B,C | unknown-step-key fallback form never assigned; lands in 3 slots incl. the bar caption | fixed | §4.1 retire ¶, §4.3 forms ¶, INV-3 test, §6 r6 |
| M2 | MEDIUM | 10 | A | REMEDY routed to fate 2 but window renders no payload text; INV-3/§6 undefined for it | fixed | §4.1 fate2, INV-3, §6 r1 |
| M3 | MEDIUM | 5 | C | STEP_END's code set never enumerated against the 7 badges §3.2 forbids re-wording | fixed | §4.1 fate2, §3.2, §4.3 short form |
| M4 | MEDIUM | 8 | A,C | §2.2's notify_send background motivates work §10 splits to 0077; §4 never returns to it | fixed | §2.2, §10, INV-4 |
| M5 | MEDIUM | 7 | C | who *adds* the in-progress phrasing — 0072 or 0032 — ambiguous across both §4.1s | fixed + out_of_scope | §4.1 fate1, ONEUP-0032 §4.1 |
| M6 | MEDIUM | 8 | pkt | `oneup-2.0.md` §4 keeps the narrow HINT/REMEDY framing §3.1 overturns; §8 doesn't name it | fixed | §8 b1, §3.1, oneup-2.0.md §4 |
| M7 | MEDIUM | 15 | C | INV-1's test vacuous for any of the 5 families no scenario emits (DISK is the precedent) | fixed | INV-1 test, §7 r1 |
| L1 | LOW | 6 | A,B | §4.2 "entry then stays commented out" vs §6 r4 reads as simultaneous | fixed | §4.2 alloc ¶, §6 r4 |
| L2 | LOW | 8 | A,B | Verified-at header dated 2026-07-31 on a doc edited 2026-08-03 | fixed | header |
| L3 | LOW | 1 | A,B | the gui-smoke-not-i18n-check argument made twice at length | fixed | §3.3 b1, §7 ¶1 |
| L4 | LOW | 4 | C | §4.1 says unknown-code **banner**; a STEP_END code renders into a **badge** | fixed | §4.1, §4.3 |
| L5 | LOW | 6 | C | example uses `packman` (an alias) in a ¶ arguing zypper supplies names | fixed | §4.1 example |
| L6 | LOW | 6 | C | "these two codes" antecedent not resolvable until §4.3 | fixed | §4.1 |
| L7 | LOW | 5 | A | "code" vs "token" load-bearing, defined nowhere | fixed | §4.2, §4.1 fate3 |
| L8 | LOW | 6 | A | §4.3's relative clause reads as "the defect renders normally" | fixed | §4.3 arity ¶ |
| L9 | LOW | 5 | A,B | §8 lists no ROADMAP.md bullet, unlike sibling 0077 §8 | fixed | §8 |
| I1 | INFO | 9 | A | INV-2's per-field `\|`→`/` scan runs at PROGRESS frequency; no cost line | carried to Phase 6 | — |
| D1 | LOW | 11 | B | "Sections:" line unanchored | dismissed — house style in all 5 specs; `documentation.md` §4 mandates no anchors | — |
| D2 | MEDIUM | 5 | C | docs-check.py's marker gate broken by the signature change | dismissed — ONEUP-0054 §8 owns that gate; the marker name stays the first quoted argument | — |

**Open questions resolved in the document's favour** (recorded so a later loop does not re-ask):
- download-size: the engine sets `why` from a 4-arm `case "$rc"` then interpolates it into `"Couldn't work out the download size: $why"` — a fifth sentence. §4.2's "four codes" is right.
- §2.2's timer claim: `_headless_check` runs `--check --notify`, `_headless_update` runs `--notify --auto-skip-repos`; `_install_user_timer` installs both. Accurate.
- `oneup/engine/markers.py` (§4.2) vs `oneup/gui/markers.py` (§4.3): two intended modules, each cited correctly.
- "All three packaging paths ship both halves": `oneup-2.0.md` §4 supports it (rpm installs both files, appimage `--add-data`s the engine, obs rolls the tarball the rpm expects).

---

## Loop 2 — verified rows (opened BEFORE the fixes)

Lanes A, B, C. Cumulative spend 123,686 / 123,630 / 123,674 (cumulative, not per-turn;
first-turn ~42k each). **Zero criticals from all three lanes**, down from 3 in loop 1.

Tally: **CRITICAL 0 · HIGH 7 · MEDIUM 8 · LOW 9 · INFO 1** = 25 = verified 25 + dismissed 0.

**ORIGIN SPLIT (Phase 3 step 0): 15 fix collateral vs 10 draft defects.** Collateral
outnumbers draft on the FIRST split with a decisive margin → per `loop-economics.md` this
licenses a **harder sweep now**, not a stop and not automatically another loop. The sweep
must re-run 4b over loop 1's ledger rows and the WHOLE standing pair list.

| # | sev | dim | lanes | origin | finding | disposition |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | HIGH | 5 | A,C | collateral (L1 STEP_END table) | the closed 7-code set has no code for `status == fail`, which INV-1 makes mandatory | fixed |
| H2 | HIGH | 5 | A,B,C | collateral (L1 §8 edit) | "Two edits are already made" now heads a FIVE-bullet list incl. CHANGELOG | fixed |
| H3 | HIGH | 7 | A | draft | the engine reuses the SAME English string for its terminal `echo` and the marker (lines 370/411/505, and 1515 for `DETAIL`), so conversion does NOT remove English from the privileged half | fixed |
| H4 | HIGH | 2 | B,C | collateral (L1 cross-doc fix) | §4.1 quotes ONEUP-0032's superseded row and calls the correction pending, while §8 says it is made | fixed |
| H5 | HIGH | 5 | B | draft | `tests/differential-test.sh` / gate G2 compares v1 and v2 marker streams; this item makes them differ by construction, and §7 says nothing | fixed |
| H6 | HIGH | 7 | B | draft | design §7's G10 row still carries the narrow HINT/REMEDY framing §3.1 overturns, and §3.1 cites G10 | fixed |
| H7 | HIGH | 15 | orchestrator (empirical) | draft | **measured**: with a catalogue, `translate(ctx,src,"",n)` selects a plural form with no `%n` in the source; with NO catalogue it returns the source verbatim. 2.0 ships English only, so §4.3's plural-form mechanism cannot produce the was/were agreement the engine gets right today | **surfaced** — needs a design decision |
| M1 | MEDIUM | 5 | A | collateral (L1 H3 fix) | a REBOOT reason of 2+ elements, none known, satisfies neither rule | fixed |
| M2 | MEDIUM | 6 | A | draft | INV-1's headline says every rendered field holds codes; arguments are data, as its own test clause says | fixed |
| M3 | MEDIUM | 5 | A | collateral (L1 M1/M5 fixes) | two window-held strings, three render sites, no mapping | fixed |
| M4 | MEDIUM | 1 | A,B,C | collateral (L1 fixes) | the fallback rule is stated in full 4–5× — **the delete-N−1 case, and the lever on this loop's collateral rate** | fixed |
| M5 | MEDIUM | 7 | B | collateral (L1 INV-4 rewrite) | INV-4's test forbids raw payload text in any other widget; INV-3's short form requires exactly that | fixed |
| M6 | MEDIUM | 5 | B,C | collateral (L1 STEP_END table) | `HINT`'s ~17 codes enumerated nowhere while three other families now are | fixed |
| M7 | MEDIUM | 7 | C | collateral (L1 REMEDY fix) | REMEDY has no table, but §4.2's allocation/retirement/INV-5 all key off "the window's tables" | fixed |
| M8 | MEDIUM | 10 | C | collateral (L1 H2 fix) | the variadic emitter and `@@REBOOT@@\|no` have no invariant or test | fixed |
| L1 | LOW | 6 | A,B,C | collateral | "the CHANGELOG bullet **above**" — it is below | fixed |
| L2 | LOW | 4 | A,B,C | collateral | proxy stated as "twice the key's length" in §4.1, "the code's" in §4.3 and INV-3 | fixed |
| L3 | LOW | 6 | A,C | collateral | "two forms, because two of these **codes**" — they are families, and three sites take the short form | fixed |
| L4 | LOW | 6 | A | collateral | fate 2's heading says "the window renders it as words", then exempts REMEDY | fixed |
| L5 | LOW | 10 | A,B | draft | the download-size `*` default arm carries `code $rc`, so one of the four codes is not zero-arity | fixed |
| L6 | LOW | 4 | B,C | draft | "Done when" lists "REMEDY's two actions" as work; they are already codes | fixed |
| L7 | LOW | 5 | B | collateral | emitter behaviour for a NON-trailing `None` unstated | fixed |
| L8 | LOW | 6 | C | draft | "a failed step's code is read for the *hint*" names no reader | fixed |
| L9 | LOW | 2 | C | draft | `@@REPO_SKIPPED@@`'s reason never reaches stdout as plain text — only inside the raw marker line | fixed |
| I1 | INFO | 9 | A,B | draft | no budget pinned for the per-marker table lookup | carried to Phase 6 |

**Open questions resolved:**
- `translate()` plural selection — measured with a real `.qm` (see H7). Not inconclusive.
- `tests/differential-test.sh` does not exist; `ONEUP-0054` §4.5 owes it and it is wired
  into neither `local-CI.sh` nor the release workflow today.
- The engine's end-of-run summary DOES consume `DETAIL[$key]` (line 1515), so `STEP_END`
  carries the same English-retention obligation as `HINT`/`CHECK_UNKNOWN` (H3).
- `disable_repo` echoes no reason — `@@REPO_SKIPPED@@`'s reason is visible only in the
  raw marker line (L9).
