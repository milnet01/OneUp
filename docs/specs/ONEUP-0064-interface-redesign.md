# ONEUP-0064 — the interface redesign

**Status:** Draft
**Kind:** ux
**Roadmap:** ONEUP-0064
**Branch:** v2
**Verified at:** `d18fbf2` — every figure below was measured against this tree, on
PySide6 6.11.0, not recalled.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** The window reads as one screen with an obvious next action — the header
stops carrying four buttons of equal weight, Settings gains groups, a whole task row becomes
its own click target, and the tab chain covers every control rather than the first eleven.

**Split on 2026-08-03.** The focus cue, its derivation and its check left this document for
`docs/specs/ONEUP-0076-ringless-focus-cue.md`; §11 carries the provenance row. What stays here is the layout.

**`docs/standards/ui-and-accessibility.md` owns the rules this works under** — colour never
alone (§3), text derived from the desktop point size (§4), tab order follows visual order
(§5.6). None of it is re-argued here.

## 1. Goal

The window reads as one screen with an obvious next action rather than a stack of buttons
that all look equally important. A first-time user can tell which control starts an update
and which merely opens a dialog; a keyboard user reaches every control in the order they see
it; and clicking a task means clicking the task, not hunting a 56×30 switch at the far
right of a row as wide as the window.

## 2. Background

Both figures below were measured by building the window offscreen at `d18fbf2` — the
measurement pass this item's roadmap bullet records — not read off the source.

### 2.1 The warning banner's tab order runs backwards

The banner lays out `[text · Copy command · Show details · <second remedy>]`, but focus
visits *Show details* first, then jumps left to *Copy command*. `_make_banner` parents its
own button before `warn_copy_btn` is inserted ahead of it in the layout, and Qt builds the
focus chain from parenting order. That is a breach of
`docs/standards/ui-and-accessibility.md` §5.6.

### 2.2 The disclosure arrow is small but conforming, which is not the same thing

All five measure 19×19, under SC 2.5.8's 24×24. Its nearest other target is its row's
switch, **47.0 px** away centre to centre. The switch is not itself undersized, so the test
is a 24 px circle on the arrow against the switch's own bounding box — 47.0 − 28 = 19 px of
clearance against a 12 px radius — and the spacing exception applies
(*Source:* <https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html>). It is
an ergonomics defect, not a conformance one, and §4.1 treats it as such.

## 3. Scope decisions

### 3.1 The three fixed points (the user, 2026-07-26)

1. **No focus borders.** Ordinary borders are fine and always were; what must not appear is
   a border or an outline drawn *to mark* the focused control. Restated at its original
   width, not widened — `ui-and-accessibility.md` §5.2.
2. **The phone-style on/off switches stay.** A long-standing preference over check boxes,
   because on/off reads at a glance. A fixed point, not a candidate.
3. **Free rein otherwise** — propose and build, tweak afterwards. So this spec brings
   recommendations rather than questions.

**Fixed point 1 belongs to both halves of the split and is not re-argued here.** `docs/specs/ONEUP-0076-ringless-focus-cue.md`
owns what replaces the hover-based cue and why; this document must simply not introduce a
border or outline to mark a focused control, which no layout change here does.

### 3.2 What this spec does not decide

`documentation.md` §4 reserves this section for choices that were preference rather than
deduction, so the boundaries themselves live in **§10** and are not restated here. One is
worth stating as a decision rather than an omission: `docs/specs/ONEUP-0034-gui-modules.md`
§4.2 hands this item the attempt at getting `oneup/gui/window.py` under the 600-line ceiling
and promises nothing. This spec keeps that posture deliberately — §4.1 splits what the
layout change naturally separates, and claims no figure.

## 4. Design

### 4.1 The layout

Free rein, with the reasons the sweep produced. Nothing here changes what a control *does*.

**The header carries two buttons instead of four.** *Settings* and *About* stay;
*Repositories* and *Recenter* move inside Settings. Four buttons of identical weight beside
the app title make none of them findable, and of the four only Settings is used routinely —
*Recenter* exists because a Wayland compositor owns window placement and `move()` is
silently ignored, as `Updater.recenter`'s own comment says. That is a workaround, not a
feature that has earned a place in the header.

**Settings gains three headings** rather than staying a flat column of ghost buttons.
`SettingsDialog` today lays out eight rows in one column, and the grouping is **exhaustive
over all eight** plus the two controls moving in from the header — every row lands in
exactly one heading, and an implementer who finds a row with no home has found a defect in
this list rather than a judgement call:

| Heading | Rows |
| --- | --- |
| *Automatic behaviour* | `auto_btn` (weekly check), `auth_btn` (passwordless), `autoupdate_btn` (automatic updates), `tray_btn` (tray icon), `startboot_btn` (start at login) |
| *Appearance* | `textsize_btn` (text size), `contrast_btn` (high contrast) — and the theme picker `ONEUP-0027` §4.6 adds next |
| *This machine* | `repos_btn` (Repositories) and `recenter_btn` (Recenter), both moved from the header, plus `diag_btn` (Copy diagnostics) |

The dialog stays a host, not an owner (`ONEUP-0034` §4.2): the window still builds and owns
the controls. Its intro label — *"Background behaviours. Each is off until you turn it
on."* — describes only the first heading and stops being true once the other two exist, so
this item replaces it. That is the one string this item changes; §10 defers the rest.

**The action row reads primary-first.** *Run selected updates* leads, *Check for updates*
follows it, and *Stop* replaces *Check* in place while a run is going rather than appearing
as a third button beside it. Today three identically-styled ghost buttons — *Check*, *Stop*
and *Retry failed steps* — are indistinguishable from *About*, so the one that interrupts a
running update looks exactly like the one that opens a version dialog.

*Stop* is shown for a real run only: `set_controls_enabled` computes `stoppable` as `(not
enabled) and self._run_active and not self._check_mode`, because a `--check` installs
nothing and so has nothing to stop. During a check the slot therefore holds *Check*,
disabled, as it does today — the replacement is a run-time swap, not a check-time one.

*Stop* keeps the ghost outline and its transparent fill; what takes the danger family's
colour is its **border and its label**, the family `#RestartBtn` on the reboot banner
already uses. Leaving the fill transparent is what lets
`docs/specs/ONEUP-0076-ringless-focus-cue.md` derive its focus cue from `card`, which is
what that spec's row for it assumes. It becomes its own object name, `#StopBtn`, because
that spec matches a styled control by object name and a restyled control still called
`#GhostBtn` would be invisible to its check; its §4.2 and §4.3 carry the focus rows, and
its rest colour differs by palette.

***Retry failed steps* leaves the action row for the warning banner** — `#WarnBanner`,
which is the banner a failed step already raises. A remedy belongs beside the thing it
remedies, which is where every other remedy in this window already lives; §9 records why
the alternative was rejected. It keeps its own object name so its styling does not change,
and it is appended **last** in that banner's layout — after `warn_copy_btn`, `warn_btn` and
`warn_btn2` — so it is last in the chain too, which is what INV-1 asserts. That banner now
carries four buttons rather than three, which is the count INV-1's expected chain must
state.

**A whole task row toggles its task.** Today the only hit target in a row is the switch at
its far right — measured 56×30 in a row 61 px tall spanning the full width of the window —
and the name and description beside it do nothing. The row is the width of the window and
the switch is a fixed 56 px of it, so the wider the user makes the window the smaller the
fraction that responds to a click; the ratio, not any one width, is the argument.
Clicking anywhere in the row toggles the switch **except** on the switch itself, the badge,
the disclosure arrow, and anything inside the expanded detail panel — the switch is excluded
because it already toggles itself, and a row handler that also fired would toggle twice and
leave the primary control looking dead. INV-4 asserts each of those four cases. The switch
stays what it is and remains the thing that shows the state — fixed point 2 — it simply
stops being the only place you may click.

**The disclosure arrow grows to 24×24**, which §2.2 establishes is an ergonomics fix rather
than a conformance one, and gets the hover treatment the rest of the controls have. Its
focus treatment is not this item's: `docs/specs/ONEUP-0076-ringless-focus-cue.md` §4.2
carries the `QToolButton#Disclose` row, and §10 keeps the cue out of scope here.
**24×24 is the floor for every pointer target**, width as well as height, over the set
INV-5 defines — a minimum height alone settles only half of SC 2.5.8.

**The tab chain is set for every control, not the first eleven.** `setTabOrder` today
covers the four header buttons, the five switches, *Check* and *Run* — eleven widgets — and
everything after that falls back to parenting order, which is where §2.1's backwards banner
comes from. The chain is stated end to end, and the banner's remedy buttons are ordered as
they are laid out.

### 4.2 What deliberately does not change

- **The five task rows, their keys and their order.** `system, flatpak, firmware, orphans,
  cache` is a contract shared with the engine (`CLAUDE.md` §4).
- **Every accessible name and description.** ONEUP-0028's floor is a regression bar. A name
  may be reworded by ONEUP-0032 later; none is removed here.
- **The marker protocol, and every behaviour behind a control.** This item changes what the
  window looks like and where its controls sit. A button that ran a check still runs the
  same check.
- **Font sizes stay derived from the desktop point size.** No hard-coded `px` for text —
  `ui-and-accessibility.md` §4.

## 5. Correctness invariants

- **INV-1** Tab order follows visual order for every focusable control in the window, in
  each banner, and in each dialog reachable from the window.
  *Test:* `tests/gui-smoke.py` flattens the layout tree into visual order — top to bottom,
  then left to right — and asserts the focus chain, walked end to end, is that exact
  sequence. **A whole-chain comparison, not a within-parent one:** a per-parent check
  cannot see an inversion *between* containers, which is what this redesign moves, and it
  passes a control omitted from `setTabOrder` whose parenting order happens to agree
  locally. Breaks on today's warning banner, whose chain visits *Show details* before
  *Copy command*, and on the four-button banner §4.1 leaves behind if *Retry* is appended
  without a `setTabOrder` call.

- **INV-2** Every focusable widget still reports a non-empty accessible name **or visible
  text**.
  *Test:* the existing `tests/gui-smoke.py` name sweep — ONEUP-0028's guarantee, re-run
  against the redesigned tree, and **extended to open each dialog** rather than stopping at
  the window, because §4.1 moves two named controls into `SettingsDialog`. The "or visible
  text" half is not a relaxation: it is the form `docs/standards/documentation.md` §5 and
  `docs/standards/ui-and-accessibility.md` §2 both state, and the sweep already accepts
  `text()`, so an invariant demanding `accessibleName()` alone would fail on day one
  against every plain labelled button. Breaks if a control is rebuilt during the redesign
  and loses both.

- **INV-3** No text size is expressed in `px`.
  *Test:* the existing assertion in `tests/gui-smoke.py` that the built stylesheet contains
  no `font-size:` followed by a `px` length. Breaks if a redesigned control hard-codes a
  size instead of taking one from `_font_metrics`.

- **INV-4** Clicking a task row's body toggles that row's switch exactly once; clicking the
  switch itself also toggles exactly once; clicking its badge, its disclosure, or anything
  inside its expanded detail panel does not toggle it at all.
  *Test:* `tests/gui-smoke.py` posts a mouse click at the row's text area and asserts
  `isChecked()` flipped, clicks the switch directly and asserts it flipped once rather than
  twice, then clicks the badge, the disclosure and — with the row expanded — a detail item,
  and asserts none of the three moved it. All four exclusions §4.1 names are asserted
  separately. Breaks if the row-level handler is attached to the whole frame without
  excluding its children — which for the switch shows up as a double toggle, leaving the
  primary control looking dead rather than throwing.

- **INV-5** Every **pointer target** measures at least 24×24, width and height, at the
  smallest desktop font size the app renders. The set is not this spec's INV-1's: SC 2.5.8
  is about things you click, so it excludes `#Log` and `#DetailScroll` (focusable, not
  targets) and includes the task row's newly clickable body (a target, not focusable).
  *Test:* `tests/gui-smoke.py` builds the window **and each dialog** offscreen with the
  application font pinned to **6 pt**, makes each banner visible so its buttons are laid
  out rather than carrying a default geometry, walks that target set, and asserts both
  dimensions. 6 pt is the floor because `_font_metrics` accepts a base only in 6–30 pt and
  **substitutes 10.0 outright** outside that band — it does not clamp to the nearest edge,
  so pinning 4 pt would silently test at 10 pt and prove less. Breaks on today's 19×19
  disclosure arrow, and on any control whose size is left to the font alone.
  **Varying `TEXT_SCALES` instead would test nothing:** its smallest entry is `1.0`, the
  default, so the run would sit at whatever point size the machine happens to use — and §6's
  failure mode is a small *desktop* font, which is `QApplication.font()`, not a scale.

- **INV-6** The controls this redesign moves are where it says they are: `repos_btn` and
  `recenter_btn` are children of `SettingsDialog` and not of the header; the header carries
  exactly `settings_btn` and `about_btn`; `retry_btn` is a child of `warn_banner`; and the
  action row's widget order is *Run*, then *Check*.
  *Test:* `tests/gui-smoke.py` builds the window, opens `SettingsDialog`, and asserts each
  parent and the action row's layout order. Breaks if a move is half-done — the control
  reparented but the header not rebuilt, or the reorder missed — which is the one class of
  defect in this item that changes nothing measurable and everything visible, and which no
  other invariant here would catch.

## 6. Failure modes

- **A user's desktop font is small enough to shrink a control below 24×24.** Sizes derive
  from the desktop point size, so §2's figures are this machine's. The redesign sets a
  24×24 floor on pointer targets rather than letting the font decide alone, and INV-5
  measures it at the smallest size the app can render.
- **A control is added later and left out of the tab chain.** It falls back to parenting
  order, which is how the warning banner's chain came to run backwards (§2.1). INV-1 walks
  the chain rather than trusting the `setTabOrder` calls to be complete.
- **The row-level click handler catches a child it should not.** The switch would then
  toggle twice and appear dead, and the disclosure would toggle the task instead of
  expanding it. INV-4 asserts each case separately for that reason.
- **Moving a control into `SettingsDialog` takes it out of a sweep that covered it.**
  *Repositories* and *Recenter* move, so every widget sweep in this spec opens each dialog
  rather than stopping at the window — INV-1, INV-2 and INV-5 each say so in their own
  *Test:* clause, because a scope stated only here is a scope no test inherits. The same
  move is why `docs/specs/ONEUP-0076-ringless-focus-cue.md`'s INV-1 sweeps dialogs for the
  focus cue.

## 7. Tests

| Invariant | Where | What it does |
| --- | --- | --- |
| INV-1 | `tests/gui-smoke.py` | **new** — flattens the layout tree to visual order and asserts the whole focus chain matches it, in the window, each banner and each dialog |
| INV-2 | `tests/gui-smoke.py` | **existing** — ONEUP-0028's accessible-name sweep, re-run against the redesigned tree and extended to open each dialog |
| INV-3 | `tests/gui-smoke.py` | **existing, unchanged** — the assertion that the built stylesheet carries no `font-size:` in `px` |
| INV-4 | `tests/gui-smoke.py` | **new** — posts clicks at a row's body, its switch, its badge, its disclosure and a detail item, and counts the toggles |
| INV-5 | `tests/gui-smoke.py` | **new** — builds the window and each dialog offscreen at a 6 pt application font, reveals each banner, and measures every pointer target |
| INV-6 | `tests/gui-smoke.py` | **new** — asserts the parent of each moved control and the action row's widget order |

**No new test file.** `docs/standards/testing.md` §2 applies unchanged: the sweeps build a
window, so they redirect `HOME` and the state paths the way `tests/gui-smoke.py` already
does.

## 8. Docs & release

- **`README.md`** carries the user-facing description of the window and is re-read against
  the new layout: the header loses two buttons, the action row reorders, and Settings gains
  headings. If it names a control by position, that sentence moves.
- **The two screenshots are re-shot, and they are the part most easily missed.**
  `screenshots/oneup.png` and `screenshots/oneup-light.png` show the window as it is today.
  Both go stale the moment this item lands, and both are *published*: `README.md` embeds
  the dark one, and `data/za.co.antsprojectshub.OneUp.metainfo.xml` points its
  `<screenshot type="default">` at the same file over `raw.githubusercontent.com`, which is
  what an AppStream store page and the software centres render. Re-shooting them ships in
  the same commit as the layout change. The file names and the metainfo URL do not change,
  so nothing else in packaging moves.
- **`docs/standards/ui-and-accessibility.md` §5.6** states that tab order follows visual
  order and that a new control's place in the chain is set in the same commit. §2.1 records
  a live breach of it; nothing in the standard changes, but its **What checks this** row for
  §5.6 gains INV-1, which is the first thing to actually check it.
- **`docs/specs/ONEUP-0076-ringless-focus-cue.md`** cited this document's §4.5 in three
  places — its §4.2 rows for `#StopBtn` and for `#GhostBtn` moved into `SettingsDialog`, and
  its INV-1 — from before the 2026-08-03 split renumbered that section to §4.1. All three
  were repointed when this document was reviewed; nothing further is owed at release.
- **`docs/specs/ONEUP-0034-gui-modules.md` §4.2** predicts `oneup/gui/window.py` will not
  fit the 600-line ceiling and hands the attempt here; §3.2 records what this spec does and
  does not promise about that.
- **`CHANGELOG.md`** gains an `[Unreleased]` entry under **Changed**. It ships inside 2.0;
  there is no 1.4.x release of it, and no version site moves.
- **No marker, no engine change, no packaging change.** The window's argv to the engine is
  untouched, so `docs/reference/marker-protocol.md` is not in scope.

## 9. Alternatives considered (and rejected)

- **Leave the header's four buttons alone.** They are only four, and moving two is a
  visible change to something nobody complained about. Rejected because equal visual weight
  is the problem rather than the count: *Settings*, *Repositories*, *Recenter* and *About*
  render identically beside the app title, so none of them is findable, and *Recenter* is a
  Wayland workaround rather than a feature.
- **Make the whole row a click target *including* the switch.** Simpler to write — one
  handler on the frame — and it double-toggles, because the switch already handles its own
  click. INV-4 exists because that failure looks like a dead control rather than an error.
- **Give *Stop* a completely different shape rather than the danger colour.** Rejected as
  over-correction: it is a button among buttons, and the shared ghost outline is what makes
  the action row read as a row. The colour and the label carry the distinction.
- **Keep *Retry failed steps* beside *Check* and *Run*.** It is a third identically-styled
  ghost button in the primary action row, present only after a failure. Rejected: folding it
  into the warning banner — which §4.1 specifies — puts the remedy beside the thing it
  remedies, which is where every other remedy in this window already lives.

## 10. Out of scope

- **The focus cue, its derivation and its check.** `docs/specs/ONEUP-0076-ringless-focus-cue.md`, split from this
  document on 2026-08-03. Neither **blocks** the other, but they are not independent either,
  and each names exactly one hook in the other: §4.1 gives *Stop* the object name `#StopBtn`
  and keeps its fill transparent *because* 0076 matches by object name and derives that
  control's cue from `card`; and 0076's INV-1 sweeps dialogs *because* §4.1 moves two
  controls into `SettingsDialog`. They ship together or the second one to land fixes the
  first one's rows. `docs/design/oneup-2.0.md` §5.2 owns the order of work and now places
  0076 in the same slot as this item, which it had not done before the split.
- **Any wording.** Translation is `ONEUP-0032` and comes last; strings this item changes are
  wrapped once, there.
- **Right-to-left mirroring.** Also `ONEUP-0032` §4. The layout changes here use no
  directional stylesheet property, so they add nothing for that item to undo.
- **Theming the redesigned layout.** `ONEUP-0027`, which lands after both halves of this
  split.
- **Reaching the 600-line ceiling for `window.py`** as a promise. §3.2.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-08-03 | 3 lanes; 5 critical, 6 high, 8 medium, 12 low, 0 info — **30 verified, 1 dismissed** — 30 draft defects vs 0 fix collateral (30 fixed, 0 carried) | The first review of this document on its own bytes. **The most valuable finding arrived as a lane's open question rather than as a finding**, which is the argument for verifying those too: §8 said *"`data/` carries no screenshot — the AppStream metainfo has none — so nothing in packaging shows the old layout."* Both halves are false. `screenshots/oneup.png` and `screenshots/oneup-light.png` are in the tree, `README.md` embeds the dark one, and the metainfo's `<screenshot type="default">` points at that same file over `raw.githubusercontent.com` — which is what a software centre renders. The redesign obsoletes two *published* images, and the release section said there was nothing to do; §8 now requires re-shooting both in the same commit. **Renumbering residue from the split took three shapes and one of them would have escaped this document:** two dead `§4.5` references, two dead `§2.3` references, and `INV-3` cited twice where `INV-1` was meant — the second of those inside §8's instruction to add a row to `ui-and-accessibility.md`'s **What checks this** table, which would have filed the `px`-check invariant against the tab-order rule. §2 also gained the `§2.2` its dead references had been pointing at. **§7's table was mis-mapped across every row** and credited a *"colour-never-alone"* sweep that is no invariant of this spec; it is the table an implementer builds tests from, so all six rows are restated and marked new or existing. **The central layout change was incomplete against the code it redesigns:** three Settings headings placed six of `SettingsDialog`'s eight rows and left `tray_btn` and `startboot_btn` with no home. The grouping is now a table, stated exhaustive, with the two header controls moving in — and its intro string, which describes only the first heading, is named as the one string this item changes. **A whole design decision lived only in §9 Alternatives** — *Retry failed steps* moving into the warning banner — so §4, the section an implementer reads, never mentioned it; it is now in §4.1 with the banner named `#WarnBanner` and its chain position stated after `warn_btn2`, which is a fourth button INV-1's expected chain has to carry. **The independence claim between the two split halves was false in both directions and unsupported by the section it cited:** each names exactly one hook in the other (`#StopBtn`'s transparent fill, and 0076's INV-1 sweeping the dialogs this item creates), and `docs/design/oneup-2.0.md` §5.2 did not mention 0076 at all — it now places it in this item's slot, as it had to for 0072. **Three figures were re-run offscreen rather than read:** 56×30, 19×19 and the 47.0 px arrow-to-switch clearance all reproduced exactly, and **760 px did not** — no `760` exists anywhere in `updater.py`, the window measures 560 wide with a 736 `sizeHint`, and two careful measurements disagreeing means delete, so §1 and §4.1 now carry the ratio the argument actually rests on. Also draft: INV-2 had dropped *"or visible text"* from the form `documentation.md` §5 and `ui-and-accessibility.md` §2 both state, so as written it would have failed on day one against every plain labelled button; INV-1's test compared position *within a parent*, which cannot see the cross-container inversions this redesign creates; INV-5's headline named the text scale its own test rejects, and called `_font_metrics` a clamp when it substitutes 10.0 outright outside 6–30 pt; and **INV-6 is new** — nothing asserted that the moved controls had actually moved. **Dismissed: one** — a lane reported the loop-log heading appearing twice, which was an artifact of the orchestrator's scrubbed copy, not of the document. The parent's rows below are relabelled `parent N` because this document's own loop 1 would otherwise collide with them. It left this loop at 347 lines, up from 268. |
| 0-split | 2026-08-03 | — | **Provenance, not a review — no reviewer was dispatched to produce this row.** On 2026-08-03 this document was split: the focus cue, its derivation and its check left for `docs/specs/ONEUP-0076-ringless-focus-cue.md` and the layout stayed here. Before the split it had run three cold-eyes loops (24, 34, 35 verified) and converged **by cap rather than clean** at 762 lines, with fix collateral outrunning draft defects two loops running — 24 → 13 → 8 draft against 0 → 21 → 27 collateral — and across those loops and nine lanes essentially every finding fell in the half that left. **Those loops were run against a document that no longer exists, so none of their assurance transfers**: this spec runs the gate from loop 1 on its own bytes, and the rows below it are the parent's, kept because the layout sections were present throughout and the record of what was asked of them is worth keeping. Invariants were renumbered INV-1…INV-5 from the parent's INV-6, 7, 9, 10 and 12; nothing outside this document had cited them. |
| parent 3 | 2026-08-03 | 3 lanes; 3 critical, 9 high, 14 medium, 10 low, 1 info — **35 verified, 2 dismissed** — 8 draft defects vs 27 fix collateral (34 actionable fixed, 1 info carried) | **Converged by cap, not clean, and the ratio is the reason this document should be split rather than reviewed a fourth time.** All three lanes led with the same defect and it was structural, introduced by loop 2: INV-2 had been given a *triple* clause requiring a retained rest border to clear 3:1 against the new focus fill — and loop 2 had also moved `ghostbd` to the smallest blend from `card` reaching 3:1, which is the same construction, in the same direction, as the focus fill derived from `card`. The two land on the same colour by arithmetic: **1.00:1** light and **1.03:1** dark, with the stop button's danger border at 1.49:1 and 1.59:1. The invariant was unsatisfiable on its first run and the ghost button's outline would have vanished into its own focus fill. A retained border now takes the **ink** colour, which inherits §4.1's 4.58 bound (6.92:1 and 6.04:1) — and the stop button's rationale went with it: its danger colour is a rest affordance, and what identifies it when focused is its label, not its tint. **The second finding all three lanes reached corrects a measurement of mine, not a claim of theirs.** Loop 2 recorded the high-contrast ghost button's focus pair as `$card` → `$btn`, pure black to pure white, 21:1 — but `_HC_QSS` groups `#GhostBtn:focus` with the primary buttons and sets `background: $btnhov`. `$btn` is what `:hover` sets. The real pairs are `#000000` → `#ffd400` (**14.67:1**) and `#ffffff` → `#0000cc` (**11.22:1**), so loop 2's row and the "weaken it sevenfold" arithmetic were both wrong while its *decision* — keep a pair that already clears 3:1 — stood. A lane also found that `_HC_QSS` restates `QPlainTextEdit#Log` with `border: 1px solid $border`, which would override mechanism B's 2 px rest border and drop the cue below SC 2.4.13's area threshold in exactly the appearance mode that needs it most; both overlay rules are widened in the same commit. **The most useful draft defect came from outside this document.** `docs/specs/ONEUP-0028-accessibility.md` §5 — shipped — promises `:focus` rules for eight styled controls including three that have none, and specifies a 2 px accent outline that the no-focus-ring decision forbids; §8 corrects it. Its own §2 had already logged *"No `:focus` rule anywhere in the QSS"* as a *"WCAG 2.4.7 failure"*, which independently corroborates the §8 correction loop 1 made to `ui-and-accessibility.md` §5.4. Smaller draft defects: the rule box stated two different algorithms (one anchored, one exhaustive) and `t` was never defined nor its 1% quantisation pinned, so two implementers would print different hexes; INV-12 varied `TEXT_SCALES`, whose smallest entry is the default `1.0`, so it tested nothing and the risk it names is the desktop font — it now pins 6 pt, `_font_metrics`' clamp floor; and a target-size clause had been filed under INV-13, a pure colour computation that cannot see a widget's size. **Dismissed: two.** A lane read §4.4's 101-point gradient sampling as unsourced; it is stated in §4.4 and produced §4.3's worst-pixel figures. And a lane asked whether the stride-3 lattice sweep was actually run rather than extrapolated — it was run; what is extrapolated is the *derivation* cost over that lattice, which is why INV-5 uses stride-16. **Trend across the three loops: draft defects 24 → 13 → 8, collateral 0 → 21 → 27.** The reads are finding less and the fixes are generating more, which is the documented signal that the document is past the review's design point rather than that it is bad. It left this loop at 762 lines. §11 recommends splitting the focus-cue contract (§4.1–§4.4) from the layout redesign (§4.5) before any further review. |
| parent 2 | 2026-08-03 | 3 lanes; 3 critical, 6 high, 13 medium, 12 low, 2 info — **34 verified, 2 dismissed** — 13 draft defects vs 21 fix collateral (32 actionable fixed, 2 info carried) | **Nothing loop 1 fixed came back**, which is the proof those fixes held — one lane recomputed every ratio in §2.2, §4.1 and §4.3 and reported them matching. What it found instead was **loop 1's own damage, and it outnumbered the draft defects two to one.** All three lanes led with the same finding, and it was an invariant loop 1 had *added*: INV-11 said every user-facing text colour clears 4.5:1, which annexes work `ONEUP-0027` §4.8 owns — light `lastrun` at 3.07:1 on `card` and 2.71:1 on `win`, light `amber` — and a pair §4.7 declares exempt (`disfg` on `disbg`). As written it would have failed on day one against three pairs this item never touches. It is now scoped to the colours this item introduces or moves. Two more were loop-1 rows that named things the check cannot read: the banner link button's surface was given as "`#WarnBanner`, `#InfoBanner` — its banner is re-used for both roles", which is simply false (four separate banners exist; `warn_copy_btn` is inserted into one), and both are **alpha gradients** rather than tokens, so §4.4 now states how a translucent rest colour is composited before measurement. **The finding worth the loop was a cue this spec would have made worse.** Loop 1 added high-contrast rows deriving a focus fill for every overlay button — but the overlay's `#GhostBtn` already goes pure black to pure white, **21:1**, and "the smallest blend reaching 3:1" would have cut it to 3.14:1, weakening the focus cue sevenfold in the one appearance mode that exists for low-vision users. §4.1 now states the rule is a floor: a pair already clearing 3:1 is kept. The draft defects the loop turned up were mostly a term used two ways: §4.1 said the cue is derived from "every surface the control can rest on", which is right for a transparent ghost button and wrong for the Run button, whose cue derives from its own fill — an implementer following it literally would have measured the accent against `card`. **Rest pixels** is now defined once and used in the rule, the table header and §1. Also draft: "every one of these focus colours is a lighter version of its rest colour" is false for the light ghost button, which *darkens* (0.598 → 0.349) and still reaches 1.62:1; white is 2.63:1 against the Run button's **top** stop, not its fill (the bottom stop reaches 4.70:1, and the worst pixel governs); `ghostbd` on `card` is handed to this item by `ONEUP-0027` §4.8 with the note that it cannot be deferred to an already-shipped item, and the spec was silent — now INV-13, closed at 3.02:1 and 3.09:1. Two loop-1 figures were wrong again: the `rowcard`/`rowhov` luminance gap was written as 0.02 when it is 0.004 dark and 0.069 light, and the lattice cost was called "measured" when it is extrapolated from a 1,331-colour run (~230 s, not ~226 s). **Dismissed: two.** A lane held the base sheet may carry no explicit `qproperty-highContrast: false`, making the painted-widget seam unfounded — it does carry one, with a comment saying the explicit default is mandatory. And a lane read INV-4's painted half as vacuous because `setFixedSize` fixes the geometry; that is right about `sizeHint()` and the half is kept, rewritten to compare *which pixels are painted* rather than the size. The document left this loop at **718 lines**, up from 623. |
| parent 1 | 2026-08-03 | 3 lanes; 2 critical, 7 high, 8 medium, 9 low, 2 info — **24 verified, 4 dismissed** — 22 actionable fixed, 2 info carried | The first review of this document. **Both criticals were the same defect seen from two sides: a claim about another document that this one had not earned.** §2.3 and §8 said the redesign fixed the light link button's 2.63:1 rest text and instructed `ONEUP-0027` §4.8 to record it closed — while §4 specified only a *focus* fill and never touched the rest colour, so §8 would have written a false row into a reviewed spec. §4.3 now carries `#3779bd` at 4.53:1 and INV-11 measures rest text, in every theme. The second was the mirror of it pointing at a standard: §8 called SC 2.4.7 *"already met"*, copying `ui-and-accessibility.md` §5.4 — but this document's own §2.1 measures sixteen focusable widgets with no cue at all, and a keyboard-operable control with no visible indicator fails 2.4.7, which is Level **AA**. The standard has been wrong since it was written for the four styled controls; §8 now corrects it rather than propagating it. **The most valuable finding was one all three lanes reached and the author had proved the opposite of:** §4.1 claimed the derivation "always succeeds", on an analytic bound that is only true for a *single* surface, while §4.1's own rule demands every surface a control rests on. Measured during verification — `#000000` and `#989898` admit no colour clearing 3:1 against both, and a coarse grey sweep finds **192** such pairs. The claim is now scoped, the search raises a named error instead of returning a best-effort colour, §6 carries the failure mode and INV-5 tests both halves. Three more were contract gaps an implementer would have had to invent: the high-contrast overlay was assigned mechanism B and mechanism A in one sentence, with no rows in either table (it is A, and the four rows exist); `#GhostBtn`/`#LinkBtn` derived from `card` alone when one link sits on the warning banner and another inside a task row, which is the exact defect §4.2 argues against for the disclosure; and `ToggleSwitch`'s row named `switchon`/`switchoff`, tokens `ONEUP-0027` creates *after* this item, with no seam stated for reaching a painted widget at all. **Two numbers were wrong and one was expensive.** The disclosure's 3.09:1/2.91:1 came from a derivation step the prose never describes — the reproduced figures are 3.00:1 and 2.83:1, and INV-2 had locked the wrong one into a test. And INV-5's 3-step lattice was measured at **~226 s** of pure Python inside the suite; it is now a 16-step lattice at ~1.5 s, with the fine sweep kept as a one-off. **Dismissed: four**, each checked rather than waved away. A lane held that Qt orders the focus chain by *creation*; a two-widget probe parenting them in reverse order showed the chain follows **parenting** order, so the document was right. A lane flagged `ONEUP-0034` §4.2 as cited for two different claims — both are in §4.2. *"Copy diagnostics"* was called undefined; it is `diag_btn` in the window. And an objection that §1's goal prose has no measurable referent was dropped: a Goal section is not an invariant. **Carried as INFO:** the switch's state shape is checked against its *resting* track by `ONEUP-0027` §4.7 but against no *focused* one (6.46:1 today, unchecked once `switchmark` becomes per-theme); and §4.5 making a whole row a click target would collapse §2.3's 47.0 px spacing-exception clearance, moot only because the arrow grows to 24×24. The document left this loop at **623 lines**, up from 495. |
