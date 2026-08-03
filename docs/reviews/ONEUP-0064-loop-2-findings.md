# ONEUP-0064 — cold-eyes loop 2, verified findings (run state)

**Status:** open — verified, **not yet fixed**. Written 2026-08-03 mid-run, because the
loop's three lanes had returned and their output existed nowhere but a chat window.

**This is review run state, not a document anyone builds from.** It is not in
`/cold-eyes`' scope and takes no loop log of its own. Delete it when the findings land.

> **Do not re-review to rediscover these.** A fresh loop costs a full three-lane dispatch
> to regenerate what is already written here. Fold them in directly, then run loop 3
> cold on the result.

## Where the run stands

- **Loop 1: done, committed, pushed** — `d0eb6b8`. 30 verified, all fixed, 1 dismissed.
  `./local-CI.sh` green (exit 0). Its row is in the document's §11.
- **Loop 2: lanes returned, findings verified below, nothing fixed.** Next action is
  Phase 4 (fix), Phase 4b (blast-radius sweep), 4c (re-lint), 4d (write the §11 row),
  4e (commit), then loop 3 — which is the `--max-loops 3` cap.
- **Origin split: 14 draft defects vs 15 fix collateral.** Loop 1 was 30/0. One loop of
  roughly even is not the two-loops-running trigger to stop and consolidate, but it is
  the signal to sweep harder rather than to loop harder. Every "collateral" row below
  landed on a passage loop 1 edited.

## Verified — CRITICAL

1. **`#StopBtn` would be unstyled in both stylesheets.** §4.1 renames *Stop* from
   `#GhostBtn` to `#StopBtn`. Verified: **no unqualified `QPushButton` rule exists** in
   either sheet — every rule in `_QSS` and `_HC_QSS` is qualified by object name
   (`#RunBtn`, `#GhostBtn`, `#LinkBtn`, `#RestartBtn`, `#BannerBtn`). The rename
   therefore drops *Stop* out of rest, `:hover`, `:checked`, `:disabled` and `:focus` in
   the **high-contrast overlay** as well as the base sheet. That is an accessibility
   regression in the one appearance mode that exists for low-vision users, and no
   invariant here or in ONEUP-0076 catches it. *Lanes E, F.* **Draft defect.**
   *Fix:* require matching `#StopBtn` rules in both `_QSS` and `_HC_QSS`, and assert in
   INV-6 (or a new invariant) that every object name styled in `_QSS` has an `_HC_QSS`
   counterpart.

2. **INV-5's pointer-target set is undefined, and as written the invariant cannot pass.**
   INV-5 gives two exclusions (`#Log`, `#DetailScroll`) and one inclusion (the row body)
   — not a set. Verified: `#GhostBtn` is `padding: 8px 14px` and `#LinkBtn` is
   `padding: 4px 2px`, **neither carries a min-height**, and the only explicit minimum in
   the window is `run_btn.setMinimumHeight(44)`. At INV-5's pinned 6 pt the five
   `#LinkBtn` controls (`log_toggle`, `openlog_btn`, `rollback_btn`, `size_btn`,
   `warn_copy_btn`) and every `#GhostBtn` fall well under 24 px — while §4.1 promises a
   resize for the disclosure arrow **only**. *Lanes D, E, F.* **Draft defect.**
   *Fix:* enumerate the target set as a table (control → in/out → SC 2.5.8 exception if
   any), and state in §4.1 the mechanism that lifts every member to 24×24.

3. **§4.1 misdescribes `#RestartBtn`, the exemplar it tells the implementer to copy.**
   The document says *Stop* "keeps the ghost outline and its transparent fill; what takes
   the danger family's colour is its **border and its label**, the family `#RestartBtn`
   on the reboot banner already uses." Verified: `#RestartBtn` is
   `color: #ffffff; border: none;` over a red **fill**
   (`qlineargradient(… #ef6a55 … #d6412a)`) — white label, no border, filled. The red
   border `#e0553f` and the tinted ink belong to `#RebootBanner`, the **frame**. An
   implementer copying `#RestartBtn` builds a filled red Stop, contradicting the same
   sentence's "transparent fill" and breaking the `card` derivation ONEUP-0076 §4.2
   assumes. *Lanes D, E.* **Fix collateral — loop 1 wrote this sentence.**
   *Fix:* cite `#RebootBanner`'s `#e0553f` border and `rgba(231,76,60,…)` ink as the
   source, name the palette key or hex `#StopBtn`'s border and label take, and say
   explicitly that `#RestartBtn`'s filled form is *not* what `#StopBtn` copies.

4. **Retry's reachability after the move is unspecified.** §4.1 moves `retry_btn` into
   `#WarnBanner`. Verified: `retry_btn` is `setVisible(False)` and revealed independently
   after failures; `warn_banner` is created hidden by `_make_banner` and shown only by
   `_show_warning`. Reparented, Retry is reachable only when the banner happens to be up,
   so a run with failed steps but no warning text leaves the user with **no way to
   retry**. INV-6 asserts parentage only, so that build passes every check.
   *Lanes D, E.* **Fix collateral — loop 1 moved the relocation into §4.1.**
   *Fix:* state the visibility contract ("a failed step always raises `#WarnBanner`;
   `retry_btn` is shown iff at least one step failed") and add it to INV-6. Open premise
   worth one lookup: does every failed step in fact raise `#WarnBanner`?

5. **"That is the one string this item changes" is false, and it mis-scopes ONEUP-0032.**
   §4.1 also introduces three heading labels (*Automatic behaviour*, *Appearance*, *This
   machine*) and, because `SettingsDialog._row(description, button)` takes a description
   per row, two new row descriptions for `repos_btn` and `recenter_btn` moving in. Six
   strings, not one — and §10 scopes ONEUP-0032 to "strings this item changes", so the
   new ones would go unwrapped. *Lanes D, E, F.* **Fix collateral — loop 1's sentence.**
   *Fix:* list all six, give the replacement intro text and the two row descriptions
   verbatim (or state that the existing tooltips become the row text).

## Verified — HIGH

6. **"so it is last in the chain too" reproduces the exact bug §2.1 exists to fix.**
   §4.1 says Retry "is appended **last** in that banner's layout … so it is last in the
   chain too". §2.1 proves that inference false: Qt builds the focus chain from
   **parenting** order, not layout order. *Lane D.* **Fix collateral — loop 1's sentence.**
   *Fix:* "…and an explicit `setTabOrder` places it last, because layout order does not
   set the chain (§2.1)."

7. **INV-1's *Test:* clause does not carry the dialog/banner scope §6 claims it does.**
   §6 says "INV-1, INV-2 and INV-5 each say so in their own *Test:* clause". INV-2's does
   ("extended to open each dialog"); INV-5's does ("builds the window **and each dialog**
   offscreen"); INV-1's mentions neither. INV-1 also lacks INV-5's reveal step, and every
   banner plus `stop_btn`, `retry_btn`, `warn_copy_btn` and `warn_btn2` is constructed
   hidden — so "visual order" is undefined for them. *Lanes D, E, F.*
   **Fix collateral — loop 1 wrote both the INV-1 clause and the §6 sentence.**
   *Fix:* repeat the scope inside INV-1's clause, give it INV-5's reveal step, state the
   filter (`focusPolicy() != Qt.NoFocus` and visible), and name the chain's start widget
   and termination rule.

8. **"each dialog reachable from the window" over-binds.** §6's rationale is only that
   *Repositories* and *Recenter* move into `SettingsDialog`, but INV-1 and INV-5 as
   written also bind `RepoManagerDialog` and `RollbackDialog`, whose tab chains and target
   sizes this spec never touches. *Lane F.* **Fix collateral — loop 1's wording.**
   *Fix:* scope to the window, its banners and `SettingsDialog`, or state the others are
   in scope and what changes in them.

9. **"*Stop* replaces *Check* in place" leaves the mechanism unspecified.** Hide/show at
   one index, `QStackedWidget`, or insert/remove — the `#StopBtn` rename implies the
   first, which means `set_controls_enabled` must now **hide** `check_btn` where today it
   only calls `setEnabled`. That is a behaviour change §4.2 says does not happen. INV-6
   pins only "*Run*, then *Check*" and says nothing about the slot, so a build that
   appends Stop at the end passes. *Lanes D, F.* **Draft defect.**
   *Fix:* say plainly that `check_btn` is hidden and `stop_btn` shown at the same layout
   index, and extend INV-6 to assert it in both states.

10. **§4.1 and §8 now disagree with `oneup-2.0.md` §5.2 about the 0064↔0076 dependency.**
    §10 says "Neither **blocks** the other"; `oneup-2.0.md` §5.2 — edited in loop 1 — says
    0076 "**needs the layout and object names 0064 settles**". *Lane F.*
    **Fix collateral — loop 1 wrote both sides.**
    *Fix:* adopt §5.2's wording, or reconcile and name which document is canonical.

## Verified — MEDIUM

11. **`retry_btn` is not in the action row.** Verified: `actions.addWidget` takes
    `check_btn`, `run_btn`, `stop_btn`; `retry_btn` is `root.addWidget` — its own
    full-width row beneath. §4.1's "leaves the action row" and §9's "third
    identically-styled ghost button in the primary action row" are both wrong.
    *Lane E.* **Draft (§9) + collateral (§4.1).**

12. **INV-6's header assertion is untestable and would pass vacuously.** Verified:
    `header` is the object-named `QLabel`; the buttons are added to `header_row`, a
    `QHBoxLayout`, and their Qt parent is `card`. "Children of the header" names nothing.
    *Lanes E, F.* **Fix collateral — INV-6 is loop 1's.**
    *Fix:* phrase INV-6 against `header_row`'s layout items and against `SettingsDialog`
    parentage for the two moved buttons.

13. **The 6 pt justification does not cover the controls INV-5 measures.**
    `_font_metrics` substituting 10.0 outside 6–30 pt bounds only the sizes it feeds into
    the **stylesheet**. `#GhostBtn`, `#LinkBtn` and `QToolButton#Disclose` carry no
    `font-size`, so their geometry follows `QApplication.font()` directly and keeps
    shrinking below 6 pt. *Lanes D, F.* **Fix collateral — loop 1 wrote this sentence.**
    *Fix:* qualify it, and justify 6 pt on the widget-font path or pick a lower pin.

14. **"`testing.md` §2 applies unchanged" understates a known cost.** Verified: that
    standard's §2.3 records that `Updater.__init__` calls `_check_app_update`
    unconditionally, issuing a live `api.github.com` GET — filed as **ONEUP-0067**. This
    item adds three sweeps that build the window *and every dialog*. *Lane D.*
    **Draft defect.** *Fix:* name ONEUP-0067 and say whether the new sweeps stub it.

15. **Fixed point 1 is stated verbatim in both split halves** (this doc line 59 ↔
    ONEUP-0076 line 135, `doc_dedup` 1.000) while line 67 says it "is not re-argued here",
    and its canonical home is `ui-and-accessibility.md` §5.2, which the bullet itself
    cites. *Lanes D, E, F.* **Draft defect.** *Fix:* reduce this copy to a pointer.

16. **INV-4's preconditions are stated for one of three targets.** `self.badge` and
    `self.disclosure` are both `setVisible(False)` in `TaskRow.__init__`; the clause names
    a precondition only for the detail panel. *Lane F.* **Fix collateral — loop 1's.**

## Verified — LOW

17. `#StopBtn` is a contract with no invariant — ONEUP-0076's INV-1 matches rows by object
    name, so a *Stop* left as `#GhostBtn` matches 0076's `#GhostBtn` row and passes
    silently. *Lanes E, F.* Add the object name to INV-6.
18. "It keeps its own object name" — verified `retry_btn.setObjectName("GhostBtn")`, a
    name shared with seventeen other controls. *Lane E.* **Collateral.**
19. "a row 61 px tall spanning the full width of the window" — rows sit inside `card`,
    whose layout has margins plus the `#Frame` ring, so a row is narrower than the window.
    *Lanes E, F.* **Collateral — loop 1 replaced the 716 px figure with this.**
20. "of the four only Settings is used routinely" — unsourced usage claim in a document
    whose header warrants every figure was measured. *Lanes E, F.* **Draft.**
21. INV-4 says "asserts `isChecked()` flipped"; §7's row says "counts the toggles". State
    comparison cannot distinguish one toggle from three. *Lane E.* **Collateral.**
22. §8's ONEUP-0076 repoint bullet records **completed** work ("nothing further is owed at
    release") in the section for work owed. *Lanes D, E, F.* **Collateral.** Move to §11.
23. §2's new intro says "Both figures below were measured" — §2.1 carries no figure; both
    are in §2.2. *Lane F.* **Collateral — loop 1 split §2.**
24. INV-1's "top to bottom, then left to right" hard-codes handedness; ONEUP-0032 mirrors
    layouts. *Lane F.* **Collateral.**
25. §4.1's "except on the switch itself" reads as "clicking the switch does nothing",
    which INV-4 contradicts. *Lane D.* **Draft.**
26. §10's "They ship together or the second one to land fixes the first one's rows" offers
    two options and decides neither. *Lane D.* **Collateral.**
27. §8 evidences publication for the dark screenshot only; nothing shown publishes
    `screenshots/oneup-light.png`. *Lanes D, F.* **Collateral — loop 1's screenshot fix.**

## INFO — carried, not actionable this pass

- `recenter_btn` moved inside `SettingsDialog` still centres the **main** window
  (`_kwin_recenter` skips `transientFor`), and the open dialog does not follow it.
  *Lane F.*
- Lines 299/301 are byte-identical to ONEUP-0076's 578/580 (`doc_dedup` 1.000). This is
  the per-spec "Docs & release" template `documentation.md` §4 mandates, so two specs
  stating it is the template working, not a duplicated fact with a canonical home.
  Dismissed on the same reasoning in loop 1; recorded again because all three lanes
  reach it every loop.

## Open questions for the fixing session — one lookup each

- Does a failed step **always** raise `#WarnBanner`? `_show_warning` is verified but the
  end-of-run path that decides `retry_btn`/banner visibility was not read. This is the
  premise of CRITICAL 4 — if the answer is no, that finding is a functional regression
  rather than an unstated contract.
- Does `QToolButton#Disclose` carry a `:hover` rule today? §4.1 says it "gets the hover
  treatment the rest of the controls have".
- Is `screenshots/oneup-light.png` referenced anywhere published, or only in the tree?

## Lane budget

Three `general-purpose` lanes, ~47–48k input tokens each (128–132k total each including
output and tool use) against a 60k input budget. Loop 1's three ran 48–58k. The bounded
context packet is doing its job; do not hand lanes bare paths.
