# ONEUP-0064 — the interface redesign

**Status:** Reviewed
**Kind:** ux
**Roadmap:** ONEUP-0064
**Branch:** v2
**Verified at:** `d18fbf2` — every figure below was measured against this tree, on
PySide6 6.11.0, not recalled. §4.1's contrast figure was re-checked at `bc689ef`.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · cold-eyes loop log (unnumbered)

**In one sentence:** The window reads as one screen with an obvious next action — the header
stops carrying four buttons of equal weight, Settings gains groups, a whole task row becomes
its own click target, and the tab chain covers every control rather than the first eleven.

**Split on 2026-08-03.** The focus cue, its derivation and its check left this document for
`docs/specs/ONEUP-0076-ringless-focus-cue.md`; the cold-eyes loop log carries the
provenance row. What stays here is the layout.

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

**Every figure in §2.2 and §4.1 was measured** by building the window offscreen at
`d18fbf2` — the measurement pass this item's roadmap bullet records — not read off the
source. §2.1 carries no figure: it is a structural claim, established by reading
`_make_banner` and confirmed by walking the built chain.

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

1. **No focus borders.** `docs/standards/ui-and-accessibility.md` §5.1 states the rule and
   is canonical; its §5.2 bounds it (ordinary borders are fine). Neither is restated here.
2. **The phone-style on/off switches stay.** A long-standing preference over check boxes,
   because on/off reads at a glance. A fixed point, not a candidate.
3. **Free rein otherwise** — propose and build, tweak afterwards. So this spec brings
   recommendations rather than questions.

**Fixed point 1 belongs to both halves of the split and is stated in neither.**
`ui-and-accessibility.md` §5.1 is its home; `docs/specs/ONEUP-0076-ringless-focus-cue.md`
owns what replaces the hover-based cue and why. All this document owes it is that no layout
change here introduces a border or outline to mark a focused control, and none does.

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
the app title make none of them findable — the uniform weight is the complaint, not the
count, and no usage figure is claimed for any of the four because none was measured.
*Recenter* is the clearest case on its own merits: it exists because a Wayland compositor
owns window placement and `move()` is silently ignored, as `Updater.recenter`'s own comment
says. That is a workaround, not a feature that has earned a place in the header.

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
the controls.

**This item changes seven strings, not one** — six in Settings and one on the warning
banner, the last of which the *Retry* move requires and which is stated with the rest of
that move below. The intro label describes only the first
heading and stops being true once the other two exist; the three headings are new; and
`SettingsDialog._row(description, button)` takes a description per row, so the two controls
moving in from the header need one each — today they carry tooltips, which `_row` does not
read. All six are given verbatim so §10's hand-off to `ONEUP-0032` covers them rather than
just the one:

| # | String | Where |
| --- | --- | --- |
| 1 | *"How OneUp behaves on its own, how it looks, and what it does on this machine."* | the intro label, replacing *"Background behaviours. Each is off until you turn it on."* |
| 2 | *"Automatic behaviour"* | heading |
| 3 | *"Appearance"* | heading |
| 4 | *"This machine"* | heading |
| 5 | *"Choose which software sources OneUp updates from."* | `repos_btn`'s row description |
| 6 | *"Put the window back in the middle of the screen."* | `recenter_btn`'s row description |
| 7 | *"Some steps did not finish. Open the log to see what went wrong, or retry them."* | `#WarnBanner`'s text when a step failed with no hint and no armed remedy — the fallback §4.1's *Retry* move requires |

The replacement intro drops *"Each is off until you turn it on"* deliberately: it is true
of the first heading's five toggles and false of the other two headings' rows, which is the
same defect the original string has once the groups exist.

**The action row reads primary-first.** *Run selected updates* leads, *Check for updates*
follows it, and *Stop* replaces *Check* in place while a run is going rather than sitting
beside it as it does today. The row today is *Check*, *Run*, *Stop*, with *Retry failed
steps* in its own full-width row beneath it; three of those four — *Check*, *Stop* and
*Retry* — carry `#GhostBtn`, the same object name as *About*, so the button that interrupts
a running update looks exactly like the one that opens a version dialog.

**The replacement is a hide/show, not an insert or a stack.** `check_btn` and `stop_btn`
both stay in the action row for the window's whole life and exactly one of the two is ever
visible. **They do not share a layout position** — a hidden widget still holds its own
layout item, so the row has three items throughout: `run_btn` at index 0 with the stretch,
`check_btn` at 1, `stop_btn` at 2. What *reads* as one slot is the visibility rule, not the
geometry. `set_controls_enabled` therefore gains
`self.check_btn.setVisible(not stoppable)` beside the `self.stop_btn.setVisible(stoppable)`
it already carries; today it calls only `check_btn.setEnabled`, which is why *Check*
currently stays on screen greyed out while *Stop* appears next to it. INV-6 asserts the
three positions and both visibility states.

*Stop* is shown for a real run only: `set_controls_enabled` computes `stoppable` as `(not
enabled) and self._run_active and not self._check_mode`, because a `--check` installs
nothing and so has nothing to stop. During a check the slot therefore holds *Check*,
disabled, as it does today — the replacement is a run-time swap, not a check-time one.

*Stop* keeps the ghost outline and its transparent fill; what takes the danger family's
colour is its **border and its label**. **The construction it copies is `#RebootBanner`'s,
not `#RestartBtn`'s** — the shape, not the hex. The banner is `border: 1px solid #e0553f` over an `rgba(231,76,60,0.22)` →
`rgba(231,76,60,0.05)` wash — a red edge and red-tinted ink over an all-but-transparent
ground, which is exactly the construction *Stop* wants. `#RestartBtn` is the opposite:
`color: #ffffff; border: none;` over a solid `#ef6a55` → `#d6412a` fill. **It is explicitly
not what `#StopBtn` copies** — a filled red Stop would contradict the transparent fill this
paragraph requires and break the `card` derivation `docs/specs/ONEUP-0076-ringless-focus-cue.md`
§4.2 assumes. In `_QSS`, `#StopBtn` takes the danger colour **for its border and its
label**, and that colour is **per palette**: `#d6412a` on the light card and `#e0553f` on
the dark, which are the two rest values
`docs/specs/ONEUP-0076-ringless-focus-cue.md` §4.3 derives. `_QSS` is one template
substituted with `_DARK` or `_LIGHT`, so a per-palette value can only arrive as a **new
palette key** — `#e0553f` as a shared literal would put the light card's label at 3.79:1,
under the 4.5:1 that spec measures it against. Leaving the fill transparent is what lets
0076 derive its focus cue from `card`.

**In `_HC_QSS` it takes tokens, not that literal.** The overlay never carries a literal red;
its danger colour is `$errbd`, which `#RebootBanner` already uses there. `#StopBtn`'s
overlay rule takes the shape the overlay gives `#GhostBtn` — `background: $card;
color: $text;` — with `border: 2px solid $errbd` in place of `$border`, plus the matching
`:hover`, `:checked`, `:disabled` and `:focus` variants. Without this the implementer has
to invent the one appearance mode this paragraph says exists for low-vision users.

It becomes its own object name, `#StopBtn`, because
`docs/specs/ONEUP-0076-ringless-focus-cue.md` matches a styled control by object name and a
restyled control still called `#GhostBtn` would be invisible to that spec's check. That
spec's §4.2 and §4.3 carry `#StopBtn`'s focus rows, and the *focus* colour it derives
differs between the dark and light palettes because `card` does.

**The rename obliges a rule set in both stylesheets, in the same commit.** Neither sheet
carries an unqualified `QPushButton` rule — every button rule in both is qualified by
object name — so renaming *Stop* out of `#GhostBtn` drops it out of rest, `:hover`,
`:checked`, `:disabled` and `:focus` in **both**, leaving it unstyled rather than
mis-styled. That includes the high-contrast overlay, which is the one appearance mode that
exists for low-vision users. `#StopBtn` therefore ships with a full set of rules in `_QSS`
and a matching set in `_HC_QSS`; INV-7 asserts the parity.

***Retry failed steps* moves into the warning banner.** It is not in the action row today —
it is `root.addWidget`, its own full-width row beneath — and it moves into `#WarnBanner`, so the
remedy sits beside the thing it remedies; §9 records why the alternative was rejected.

**The move needs a visibility contract, and today's code does not satisfy it.** `retry_btn`
is revealed at the end of a run by `if self._failed_steps:`, independently of the banner —
while the end-of-run banner in `on_finished` is raised only when `self._hints or
self._remedy_skips or self._remedy_keys`. (`_show_warning` itself is called from four other
places — a snapshot pile-up, a pre-flight disk or repository warning, a `--check` that could
not read every source, and a stopped run — none of which implies a failed step, so Retry
stays hidden there. The claim above is about the end-of-run block, not the method.)
**A run whose steps failed with no hint and no armed remedy therefore
shows Retry today with `#WarnBanner` hidden.** Reparented unchanged, that run would leave
the user no way to retry at all, and INV-6 asserting parentage would not see it. So this
item also makes the banner's rule match Retry's: **for a run that finished, `#WarnBanner`
is raised whenever at least one step failed**, and `retry_btn` is shown inside it if and
only if at least one step failed. **A run the user stopped keeps the behaviour it has:**
`on_finished`'s `if stopped:` branch returns before the `if self._failed_steps:` reveal, so
a stopped run offers no Retry today and offers none after this item — §4.2 records one
behaviour change, and this is not a second. Where no hint and no armed remedy supplies the banner's text it takes
**string 7** of the table above — the same GUI-builds-the-fallback shape the
remedy-without-hint path already uses. INV-6 asserts both halves; §4.2 records this as the
one behaviour this item changes.

It keeps the object name it has, `#GhostBtn` — shared with seventeen other controls — so
its styling does not change. It is appended **last** in that banner's layout, after
`warn_copy_btn`, `warn_btn` and `warn_btn2`, **and an explicit `setTabOrder` call places it
last among that banner's four buttons, because layout order does not set the chain
(§2.1)** — last in the banner, not last in the window's chain, which carries on below it
into `appupdate_banner`'s button, `rollback_btn`, `log_toggle`, `openlog_btn` and the log
pane. That banner now
carries four buttons rather than three, which is the count INV-1's expected chain must
state.

**A whole task row toggles its task.** Today the only hit target in a row is the switch at
its far right — measured 56×30 in a row 61 px tall — and the name and description beside it
do nothing. A row spans the full width of `card`, which is the window less `#Frame`'s ring
and the card's own margins, so a row is narrower than the window while still growing with
it; the switch stays a fixed 56 px. The wider the user makes the window, the smaller the
fraction of a row that responds to a click — that ratio, not any one width, is the
argument.

**Clicking a row's body toggles its switch.** Four regions inside a row are not body: the
switch, the badge, the disclosure arrow, and anything inside the expanded detail panel.
Each keeps the behaviour it has — **the switch still toggles when you click it, exactly as
it does today**; it is excluded from the *row-level handler* so that one click is not
counted twice, which would toggle and untoggle and leave the primary control looking dead.
INV-4 asserts the body and all four regions. The switch stays what it is and remains the
thing that shows the state — fixed point 2 — it simply stops being the only place you may
click.

**The disclosure arrow grows to 24×24**, which §2.2 establishes is an ergonomics fix rather
than a conformance one, and **gains** the hover treatment the rest of the controls have —
it has none today: `QToolButton#Disclose` carries one rule, `background: transparent;
border: none; padding: 0px;`, with no `:hover` variant in either sheet. Its focus treatment
is not this item's: `docs/specs/ONEUP-0076-ringless-focus-cue.md` §4.2 carries the
`QToolButton#Disclose` row, and §10 keeps the cue out of scope here.

**24×24 is the floor for every pointer target**, width as well as height — a minimum height
alone settles only half of SC 2.5.8. The set is enumerated rather than described, because a
set given as two exclusions and one inclusion is not one an implementer can build or INV-5
can walk:

| Control | In the set? | Why |
| --- | --- | --- |
| `run_btn` (`#RunBtn`) | in | already clears it — `setMinimumHeight(44)`, and it takes the action row's stretch |
| `check_btn` / `stop_btn` (`#GhostBtn`, `#StopBtn`) | in | `padding: 8px 14px` with no minimum of any kind |
| every other `#GhostBtn` — `settings_btn`, `about_btn`, `SettingsDialog`'s **ten** rows (its eight today plus `repos_btn` and `recenter_btn`, moved in above) and its `close_btn`, `retry_btn` | in | same rule, same shortfall; `close_btn` is in the dialog's button row rather than a `_row`, so it is named rather than covered by "the rows" |
| every `#LinkBtn` in the window — `log_toggle`, `openlog_btn`, `rollback_btn`, `warn_copy_btn`, and the **system** row's `size_btn` | in | `padding: 4px 2px`, the tightest in the window. Only the system row lays `size_btn` out; `TaskRow.__init__` calls `setVisible(False)` on the other four, so "each row's" would have walked four widgets that never got a geometry |
| `QToolButton#Disclose`, one per row | in | 19×19 today, `padding: 0px` |
| `#BannerBtn`, `#RestartBtn` | in | `padding: 7px 15px`, same shortfall as `#GhostBtn` |
| each row's `ToggleSwitch` | in | 56×30 — already clears it, walked so it cannot regress |
| each row's **body** | in | newly clickable: a target, though not a focusable |
| `QLabel#Badge` | out | not clickable at all — INV-4 asserts a click on it does nothing |
| `#Log`, `#DetailScroll` | out | focusable, not pointer targets |
| `RepoManagerDialog`'s and `RollbackDialog`'s own `#GhostBtn` / `#LinkBtn` controls | out of the **checked set**, not out of the change | §10 keeps both dialogs out of scope. They still get bigger: the mechanism below is a stylesheet rule and the sheet is set on the application, so every `#GhostBtn` and `#LinkBtn` in the process inherits the floor whether a test walks it or not |

Only `run_btn` and the switches clear the floor today; **everything else in the "in" column
reaches it the same way, by a `min-width` and `min-height` of 24 px added to its rule in
both sheets** — `#GhostBtn`, `#StopBtn`, `#LinkBtn`, `#BannerBtn`, `#RestartBtn` and
`QToolButton#Disclose` each gain the pair. A stylesheet minimum rather than a per-widget
`setMinimumSize` call keeps the floor in one place and applies it to controls the window
builds in five different methods. **It also reaches every dialog by construction**, since
the sheet is set on the application — which is why the two out-of-scope dialogs above are
excluded from the *checked set* and not from the change. Adding the pair to
`QToolButton#Disclose` in `_HC_QSS` also gives that name its first overlay rule, which is
what takes it off INV-7's exception list. Those are *box* dimensions, not text sizes, so INV-3 is
not engaged and §4.2's rule about `px` for text stands unchanged. §2.2's spacing exception
for the arrow then stops being load-bearing: it applied only while the arrow stayed 19×19.

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
  same check. **One exception, and §4.1 states it:** at the end of a finished run
  `#WarnBanner` is raised for *any* failed step, not only for one carrying a hint or an
  armed remedy, because *Retry* now lives inside it. That changes when a banner appears; it
  changes no control's action, and a stopped run is untouched.
- **Font sizes stay derived from the desktop point size.** No hard-coded `px` for text —
  `ui-and-accessibility.md` §4.

## 5. Correctness invariants

- **INV-1** Tab order follows visual order for every focusable control in the window, in
  each of its four banners, and in `SettingsDialog`.
  *Test:* `tests/gui-smoke.py` flattens the layout tree into visual order — top to bottom,
  then along the layout direction within a row, so a mirrored layout (`ONEUP-0032` §4)
  reverses the second key instead of failing — and asserts the focus chain, walked end to
  end, is that exact sequence.
  **Scope is the window, its banners and `SettingsDialog`**, because §4.1 moves two named
  controls into that dialog. `RepoManagerDialog` and `RollbackDialog` are out: this item
  changes neither their chains nor their targets, and §10 keeps them out.
  **The sweep reveals before it walks.** Every banner, and `stop_btn`, `retry_btn`,
  `warn_copy_btn`, `warn_btn2`, `rollback_btn` and **each row's `disclosure`**, is
  constructed hidden — visual order is undefined for a widget that has never been laid out
  — so the test makes each banner and each conditionally-shown button visible first, and
  expands each task row's detail panel, as INV-5's does. It then walks only widgets that
  are visible and whose `focusPolicy() != Qt.NoFocus`.
  **The arrow is a separate reveal from the panel, and it is in the chain.** A `QToolButton`
  defaults to `Qt.TabFocus` and `updater.py` never calls `setFocusPolicy`, so the five
  arrows are focusable; but `TaskRow.__init__` hides each one and only `add_detail_item`
  shows it, so a test that expands the panel without feeding the row a detail item walks
  five invisible arrows and skips them all.
  **Two walks, not one — a `QDialog` has its own focus chain.** Qt's chain is per
  top-level widget, so a walk rooted in the window can never enter `SettingsDialog`, and a
  single-walk test would pass the dialog half vacuously — the exact vacuous-coverage
  failure §6 says this scope exists to prevent. The window's walk starts at `settings_btn`;
  the dialog's is run with the dialog open and starts at its own first widget. Each
  terminates when it returns to its start, so a cyclic chain does not loop forever.
  **A whole-chain comparison, not a within-parent one:** a per-parent check
  cannot see an inversion *between* containers, which is what this redesign moves, and it
  passes a control omitted from `setTabOrder` whose parenting order happens to agree
  locally. Breaks on today's warning banner, whose chain visits *Show details* before
  *Copy command*, and on the four-button banner §4.1 leaves behind if *Retry* is appended
  without a `setTabOrder` call.

- **INV-2** Every focusable widget still reports a non-empty accessible name **or visible
  text**.
  *Test:* the existing `tests/gui-smoke.py` name sweep — ONEUP-0028's guarantee, re-run
  against the redesigned tree, and **extended to open `SettingsDialog`** rather than
  stopping at the window, because §4.1 moves two named controls into it. The other two
  dialogs stay out, as they do for INV-1 and INV-5 (§10). The "or visible
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
  *Test:* `tests/gui-smoke.py` counts each switch's `toggled` emissions rather than
  comparing `isChecked()` before and after — a state comparison cannot tell one toggle from
  three. It posts a mouse click at the row's text area and asserts the count is exactly 1,
  clicks the switch directly and asserts exactly 1 rather than 2, then clicks the badge,
  the disclosure and a detail item and asserts 0 for each. All four exclusions §4.1 names
  are asserted separately.
  **Preconditions, for all three excluded children and not just the panel:** `self.badge`
  and `self.disclosure` are both `setVisible(False)` in `TaskRow.__init__`, as the detail
  panel is. The test reveals all three — the badge and the arrow by making them visible,
  the panel by expanding the row — before clicking, because a click at a hidden widget's
  coordinates lands on the row body underneath and the assertion would pass vacuously.
  Breaks if the row-level handler is attached to the whole frame without
  excluding its children — which for the switch shows up as a double toggle, leaving the
  primary control looking dead rather than throwing.

- **INV-5** Every **pointer target** measures at least 24×24, width and height, at 6 pt —
  the floor below which `_font_metrics` stops honouring the desktop font at all. **The set
  is §4.1's table**, not this spec's
  INV-1's: SC 2.5.8 is about things you click, so it excludes `#Log` and `#DetailScroll`
  (focusable, not targets) and includes each task row's newly clickable body (a target, not
  focusable).
  *Test:* `tests/gui-smoke.py` builds the window **and `SettingsDialog`** offscreen with the
  application font pinned to **6 pt**, walks §4.1's table and asserts both dimensions.
  **It reveals the same list INV-1's does first** — each banner, each conditionally-shown
  button including `rollback_btn`, and each task row's detail panel expanded so the system
  row's `size_btn` is laid out — because a widget that has never been laid out carries a
  default geometry and would be measured instead of skipped, which passes vacuously.
  6 pt is the floor because `_font_metrics` reads the application font's own point size and
  **substitutes 10.0 outright** when it falls outside 6–30 pt — it does not clamp to the
  nearest edge, so pinning 4 pt would silently test at 10 pt and prove less.
  **The pin is on the application font, and for most of the set that is the only thing that
  binds.** The 6–30 pt band governs the sizes `_font_metrics` substitutes into the
  stylesheet, and `#GhostBtn`, `#LinkBtn` and `QToolButton#Disclose` carry no `font-size`
  at all — their geometry follows `QApplication.font()` directly. **6 pt is therefore the
  smallest size worth testing, not the smallest a desktop can set:** below it the
  stylesheet path jumps back to 10 pt while the three widget-font controls keep shrinking,
  so the two paths diverge and neither is at a meaningful floor. Pinning the application
  font to 6 pt puts both at their tightest in one run. Breaks on today's 19×19
  disclosure arrow, and on any control whose size is left to the font alone.
  **Varying `TEXT_SCALES` instead would test nothing:** its smallest entry is `1.0`, the
  default, so the run would sit at whatever point size the machine happens to use — and §6's
  failure mode is a small *desktop* font, which is `QApplication.font()`, not a scale.

- **INV-6** The controls this redesign moves are where it says they are, the two that swap
  do so at one index, and *Retry* is reachable whenever it is offered: `repos_btn` and
  `recenter_btn` are children of `SettingsDialog`; **`header_row`'s layout items are
  exactly `titleblock`, `settings_btn` and `about_btn`**; `retry_btn` is a child of
  `warn_banner`; the action row's items are `run_btn` at index 0, `check_btn` at 1 and
  `stop_btn` at 2, with exactly one of indices 1 and 2 visible in each state;
  `stop_btn.objectName()` is `StopBtn`; and after a run that **finished** with at least one
  failed step, `warn_banner` is visible and `retry_btn` is visible within it.
  *Test:* `tests/gui-smoke.py` builds the window, opens `SettingsDialog`, and asserts each
  parent; `header_row`'s items **by layout index** — not "children of the header", which
  names nothing testable, since `header` is the object-named `QLabel` and the buttons' Qt
  parent is `card`; the action row's three indices and both visibility states around a
  simulated run; the object name; and a finished run whose only failure carries no hint and no armed
  remedy, which is the case §4.1 shows today's code gets wrong. Breaks if a move is
  half-done — the control reparented but the header not rebuilt, or the reorder missed —
  which is the one class of defect in this item that changes nothing measurable and
  everything visible, and which no other invariant here would catch.

- **INV-7** Every object name styled in `_QSS` has a counterpart rule in `_HC_QSS`, except
  the two named below.
  *Test:* `tests/gui-smoke.py` extracts the set of object-name selectors from each
  template's text and asserts the base sheet's set, less the exception list, is a subset of
  the overlay's. Neither sheet carries an unqualified `QPushButton` rule, so a *button*
  styled in one and not the other is not mis-coloured in high contrast — it is **unstyled**
  there. (Both sheets also carry class-only rules, and not the same ones, so the extractor
  keys on object names and ignores every selector without one.) Breaks on `#StopBtn` if
  §4.1's rename lands in `_QSS` alone, which is the
  regression this item would otherwise introduce in the one appearance mode that exists for
  low-vision users; no invariant here or in `docs/specs/ONEUP-0076-ringless-focus-cue.md`
  caught it before.
  **The exception list is `#RowDetails` and `QScrollArea#DetailScroll`, and it is named
  rather than discovered.** Three object names are styled in `_QSS` and absent from
  `_HC_QSS` today — those two plus `QToolButton#Disclose` — so an unqualified parity
  assertion would be red on its first run for reasons this item did not cause, and a test
  that is red on arrival gets weakened rather than believed. `#Disclose` comes off the list
  in this item, because §4.1's 24 px floor gives it a rule in both sheets. The other two are
  transparent-background container rules with nothing to restate in high contrast; they stay
  exempt by name, so adding a *third* exemption is a decision someone has to write down.

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
  *Repositories* and *Recenter* move, so every widget sweep in this spec opens
  `SettingsDialog` rather than stopping at the window — INV-1, INV-2 and INV-5 each repeat
  that scope inside their own *Test:* clause, because a scope stated only here is a scope
  no test inherits. The same move is why `docs/specs/ONEUP-0076-ringless-focus-cue.md`'s
  INV-1 sweeps dialogs for the focus cue.
- **A failed step leaves its remedy unreachable.** *Retry* moves inside `#WarnBanner`,
  which at the end of a run is raised today only for a failure carrying a hint or an armed
  remedy. §4.1 makes the banner's condition match Retry's own; INV-6 asserts the case that
  has neither.

## 7. Tests

| Invariant | Where | What it does |
| --- | --- | --- |
| INV-1 | `tests/gui-smoke.py` | **new** — reveals every hidden banner and button, flattens the layout tree to visual order, and asserts the whole focus chain matches it: one walk for the window and its banners, a second for `SettingsDialog`, which has its own chain |
| INV-2 | `tests/gui-smoke.py` | **existing** — ONEUP-0028's accessible-name sweep, re-run against the redesigned tree and extended to open `SettingsDialog` |
| INV-3 | `tests/gui-smoke.py` | **existing, unchanged** — the assertion that the built stylesheet carries no `font-size:` in `px` |
| INV-4 | `tests/gui-smoke.py` | **new** — reveals a row's badge, disclosure and detail panel, then clicks each plus the body and the switch, counting `toggled` emissions per case |
| INV-5 | `tests/gui-smoke.py` | **new** — builds the window and `SettingsDialog` offscreen at a 6 pt application font, reveals every banner, hidden button and detail panel, and measures every target in §4.1's table |
| INV-6 | `tests/gui-smoke.py` | **new** — asserts each moved control's parent, `header_row`'s items by index, the action row's three indices and both swap states, and that a hintless failed run raises the banner with *Retry* inside it |
| INV-7 | `tests/gui-smoke.py` | **new** — asserts every object name styled in `_QSS`, less the two named exceptions, has a rule in `_HC_QSS` |

**No new test file, and the sweeps redirect state as `testing.md` §2 requires** — they
build a window, so `HOME` and the state paths are redirected the way `tests/gui-smoke.py`
already does.

**The cost this passage used to inherit is gone, and the one obligation it left is not.**
It formerly recorded that each new window construction added another live `api.github.com`
GET, because `Updater.__init__` calls `_check_app_update` and nothing stubbed it —
**ONEUP-0067**, later re-filed and fixed as **ONEUP-0090**. `tests/gui-smoke.py` now
replaces `_check_app_update` with a no-op before its first window, so INV-1, INV-5 and
INV-6 may build as many windows as their assertions need and none of them reaches the
network. **What survives is where the stub sits** (`testing.md` §2.3): these sweeps add
their window constructions *below* that line, never above it, and nothing catches it if
they do not. They still reuse an already-constructed window wherever the assertion allows
and build a fresh one only where a pinned font or a simulated run requires it.

## 8. Docs & release

- **`README.md`** carries the user-facing description of the window and is re-read against
  the new layout: the header loses two buttons, the action row reorders, and Settings gains
  headings. If it names a control by position, that sentence moves.
- **The two screenshots are re-shot, and they are the part most easily missed.**
  `screenshots/oneup.png` and `screenshots/oneup-light.png` show the window as it is today
  and both go stale the moment this item lands. **The dark one is published twice:**
  `README.md` embeds it, and `data/za.co.antsprojectshub.OneUp.metainfo.xml` points its one
  `<screenshot type="default">` at that same file over `raw.githubusercontent.com`, which
  is what an AppStream store page and the software centres render. **The light one is in
  the tree only** — nothing in `README.md`, the metainfo or packaging references it — so it
  is re-shot for consistency rather than because a published surface would go stale. Both
  ship in the same commit as the layout change. The file names and the metainfo URL do not
  change, so nothing else in packaging moves.
- **`docs/standards/ui-and-accessibility.md` §5.6** states that tab order follows visual
  order and that a new control's place in the chain is set in the same commit. §2.1 records
  a live breach of it; nothing in the standard changes, but its **What checks this** row for
  §5.6 gains INV-1, which is the first thing to actually check it.
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
- **Leave *Retry failed steps* where it is.** It sits in its own full-width row directly
  beneath the action row, styled `#GhostBtn` like *Check* and *Stop* above it and present
  only after a failure — so it reads as a fourth member of that group while belonging to
  none of it. Rejected: folding it into the warning banner — which §4.1 specifies — puts
  the remedy beside the thing it remedies, which is where every other remedy in this window
  already lives.

## 10. Out of scope

- **The focus cue, its derivation and its check.** `docs/specs/ONEUP-0076-ringless-focus-cue.md`,
  split from this document on 2026-08-03. **`docs/design/oneup-2.0.md` §5.2 owns the order
  of work and states the dependency in one direction: 0076 "needs the layout and object
  names 0064 settles."** That is the canonical wording and this section adopts it rather
  than restating it. The dependency shows up as one named hook each way: §4.1 gives *Stop*
  the object name `#StopBtn` and keeps its fill transparent *because* 0076 matches by
  object name and derives that control's cue from `card`; and 0076's INV-1 sweeps each
  dialog *because* §4.1 moves two controls into `SettingsDialog`. **This item lands first**, as
  §5.2's ordering implies — 0076's rows are written against names that do not exist until
  this one ships — and the two ship inside the same 2.0 slot.
- **Any wording.** Translation is `ONEUP-0032` and comes last. **Every string this item
  changes or introduces is wrapped once, there — all seven of §4.1's table**, the warning
  banner's fallback included, not only the intro label.
- **Right-to-left mirroring.** Also `ONEUP-0032` §4. The layout changes here use no
  directional stylesheet property, so they add nothing for that item to undo.
- **Theming the redesigned layout.** `ONEUP-0027`, which lands after both halves of this
  split.
- **`RepoManagerDialog` and `RollbackDialog`.** Neither their tab chains nor their target
  sizes are checked here — INV-1 and INV-5 scope to the window, its banners and
  `SettingsDialog`, which is where this item moves controls. They are not *unaffected*: the
  24 px floor in §4.1 is a stylesheet rule on an application-wide sheet, so their
  `#GhostBtn` and `#LinkBtn` controls grow with everything else. What is out of scope is
  asserting anything about them.
- **Reaching the 600-line ceiling for `window.py`** as a promise. §3.2.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 4 | 2026-08-12 | 2 lanes, first loop of a fresh run under the four-question gate — no severity scale, so nothing here for §7's tally check to balance (ONEUP-0100): Q1 2 · Q2 4 · Q3 2 · Q4 1 — 9 verified, 2 dismissed as out of scope; 8 fixed, 1 surfaced to the user | **The gate re-armed on an edit this document did not make.** Loops 1–3 converged by cap on 2026-08-05 and the header was stamped `Reviewed`; `ONEUP-0090` then rewrote §7's network paragraph on 2026-08-07 while closing a defect elsewhere, and that paragraph had never been read cold. `updater.py` has itself moved 168 insertions and 44 deletions across five commits since the `d18fbf2` the header pins, so every source fact in the packet was re-measured at `bc689ef` rather than carried forward. **The finding both lanes led with would have shipped a contrast regression into the light palette.** §4.1 gave `#StopBtn` the literal `#e0553f` for its border and label as "a shared literal in both palettes … not a new palette key" — while `docs/specs/ONEUP-0076-ringless-focus-cue.md` §4.3 had already measured that button's rest colour as *per palette*, `#d6412a` light and `#e0553f` dark. Recomputed during verification: `#e0553f` on the light `card` (`#ffffff`) is **3.79:1**, against the 4.5:1 that spec holds it to. 0064 lands first and is the document that writes the `_QSS` rule, so its value is the one that would have shipped. `build_theme` substitutes one template with `_DARK` or `_LIGHT`, so a per-palette value can only arrive as a palette key; the clause denying that is gone. **Three more were this section's own sets disagreeing with the section that fills them.** §4.1's grouping table moves `repos_btn` and `recenter_btn` into `SettingsDialog`, making **ten** rows, while the target-size table still enumerated "eight rows" — and INV-5 walks that table, so the two controls this item exists to move would have been the only ones outside the 24×24 check, which is §6's own named failure mode. INV-2's *Test:* clause still said "extended to open each dialog" where §6, §7 and §10 all scope to `SettingsDialog`; loop 2 narrowed INV-1 and INV-5 for exactly that over-binding and left INV-2 behind. And INV-1's reveal list omitted each row's disclosure arrow: measured here, `QToolButton` defaults to `Qt.TabFocus` and `updater.py` never calls `setFocusPolicy`, so all five are focusable, `TaskRow.__init__` hides each one, and only `add_detail_item` reveals it — a test that merely expands the panel walks five invisible arrows and skips the one control §4.1 resizes to 24×24. **The stopped run was unspecified inside a rule written as an if-and-only-if.** §4.1 required `#WarnBanner` raised whenever a step failed, with *Retry* inside it iff a step failed; but `on_finished`'s `if stopped:` branch returns before the `if self._failed_steps:` reveal, and `_failed_steps` is appended on any `fail` marker, so a stopped run can carry failed steps and offers no Retry today. Read literally the rule made that a second behaviour change, which §4.2 says does not exist — now scoped to a finished run in §4.1, §4.2, §6 and INV-6. Two Q1s of the ordinary kind: "`_show_warning` fires only when `self._hints or self._remedy_skips or self._remedy_keys`" is false of the *method*, which has four other call sites (a snapshot pile-up, a pre-flight disk or repository warning, an unchecked-sources `--check`, and a stopped run) — the guard belongs to `on_finished`'s end-of-run block; and INV-7's parenthetical listed `QMainWindow`, `QProgressBar`, `QToolTip`, `ToggleSwitch` and `*` as class-only rules "both sheets carry", where `*` is in `_QSS` alone and `_HC_QSS` carries `QLabel` and `QDialog` besides — the enumeration was deleted rather than corrected. **Surfaced rather than fixed, because it is a design choice:** §4.1 requires `#StopBtn` to ship "a full set of rules in `_QSS`" but names colours for the rest state only, so the base sheet's `:hover` and `:checked` are unstated — inheriting `#GhostBtn`'s `#4aa3ff` would turn the danger control blue on hover, and holding the rest colour would leave hover indistinguishable from rest. **Dismissed as out of scope, two**, both verified as real and neither changing what gets built: §6 calls INV-5's pin "the smallest size the app can render" where INV-5 explicitly says 6 pt is the smallest *worth testing* — the two produce the same pin; and "everything else in the 'in' column reaches it the same way" sweeps in each row's body, which the six-selector enumeration beneath correctly omits — measured at a 6 pt application font, the body is 516×56 and needs no floor. That 6 pt run also confirmed INV-5's premise rather than assuming it: `check_btn` measures 83×**19** there, `log_toggle` and `openlog_btn` 80×19. The document left this loop at **578 lines**, up from 556 — a fix pass that added more than it deleted, which is the shape the next loop should be read against. |
| 3 | 2026-08-04 | 3 lanes; 2 critical, 6 high, 6 medium, 10 low, 0 info — **23 verified, 1 dismissed** — 4 draft defects vs 19 fix collateral (23 fixed, 0 carried) | **Converged by cap, and the trend agrees with the cap: collateral outran draft defects two loops running (8 vs 20, then 4 vs 19), which is the documented signal to stop looping.** Nothing from loop 1 or loop 2's draft-defect set returned, so those fixes held; what all three lanes found instead was loop 2's own damage, and **both criticals were invariants loop 2 had written.** **INV-7 would have been red on its first run, for reasons this item does not cause.** It asserts every object name styled in `_QSS` has an `_HC_QSS` counterpart — and three do not today: `QToolButton#Disclose`, `#RowDetails` and `QScrollArea#DetailScroll`. A parity test that fails on arrival gets weakened rather than believed, which would have destroyed the `#StopBtn` regression detector it exists to be. `#Disclose` comes off the list inside this item (§4.1's 24 px floor gives it a rule in both sheets); the other two are named exemptions, so a third one is a decision someone has to write down. Loop 2's supporting claim that "every rule in both sheets is qualified by object name" was also false — `QMainWindow`, `QProgressBar`, `QToolTip`, `ToggleSwitch` and `*` are not — and only the narrow form it needed (no unqualified `QPushButton` rule) is true, which INV-7's extractor has to know. **The second critical is a Qt fact loop 2 got backwards: two widgets cannot share one `QHBoxLayout` index.** §4.1 specified the *Check*→*Stop* swap as "a hide/show at one layout index" with INV-6 asserting "`run_btn` at index 0 and the *Check*/*Stop* slot at index 1" — but a hidden widget still holds its own layout item, so the row has three, and the invariant was unassertable. The implementer would have had to either write a failing assertion or reach for the `QStackedWidget` the same sentence forbids. It is now three items, `run_btn` 0 / `check_btn` 1 / `stop_btn` 2, with exactly one of 1 and 2 visible. **Loop 2's own fix introduced a seventh string while the document claimed six.** Requiring `#WarnBanner` for any failed step needs fallback text when no hint exists — a new user-facing string, absent from §4.1's table and therefore from §10's hand-off to `ONEUP-0032`, so it would have shipped unwrapped and unworded. Given verbatim as row 7. **A dialog has its own focus chain, so INV-1's single end-to-end walk could not have reached `SettingsDialog`** — the dialog half would have passed vacuously, which is the exact failure §6 says that scope exists to prevent. Two walks now, each with its own start widget. INV-5 had the mirror defect: its reveal step covered banners but not `rollback_btn` or the collapsed detail panels holding `size_btn`, so three named members of its own target set were measured with default geometry. **Loop 2 narrowed INV-1 and INV-5 to exclude two dialogs and cited §10 for it — and §10 said nothing about them**; worse, the exclusion was partly wrong, because the 24 px floor is a stylesheet rule on an application-wide sheet, so those dialogs' controls *do* resize. §10 gains the bullet, and the distinction is now stated: out of the checked set, not out of the change. **The cross-document half was live in the other direction too.** `docs/specs/ONEUP-0076-ringless-focus-cue.md` §10 said the two specs "neither depends on the other's internals" while this document, corrected in loop 2, says 0076 needs the names 0064 settles — 0076's sentence is repointed at `oneup-2.0.md` §5.2's one-directional wording. Medium and low: `#StopBtn`'s high-contrast colours were never named though the overlay uses tokens and carries `$errbd` already, so the implementer would have invented the low-vision mode the paragraph says exists for low-vision users; `#e0553f` as a literal contradicted "its rest colour differs by palette"; `SettingsDialog`'s `close_btn` is a `#GhostBtn` pointer target and was missing from the enumerated set the table exists to enumerate; "each row's `size_btn`" is four widgets `TaskRow.__init__` never lays out, only the system row's; fixed point 1's home is `ui-and-accessibility.md` **§5.1**, not §5.2, which is the section bounding it; INV-5's "smallest desktop font size the app renders" is not what 6 pt is; `_font_metrics` takes a `scale` and *reads* the base rather than accepting one; the sections list promised a numbered "11 cold-eyes log" against an unnumbered heading; and §7's "not materially worse" now carries the number it was avoiding (at most three added window constructions, 49 → at most 52 live GitHub requests). **Dismissed: one** — a lane held §10's right-to-left pointer at `ONEUP-0032` §4 was wrong; that spec's §4.4 *is* the right-to-left section. **Open question left standing, not a finding:** a lane computed §2.2's arrow-to-switch clearance as 47.5 px from layout spacing against the document's measured 47.0; both clear the spacing exception by a wide margin, the figure was re-measured offscreen in loop 1, and the lane's arithmetic assumes margins it could not see. The document left this loop at **556 lines**, up from 504. |
| 2 | 2026-08-04 | 3 lanes; 5 critical, 5 high, 6 medium, 11 low, 2 info — **28 verified, 1 dismissed** — 8 draft defects vs 20 fix collateral, one finding counted in both (27 actionable fixed, 1 info carried) | **The ratio inverted from loop 1's 30/0 and that is the finding about the review, not about the document:** two thirds of this loop landed on passages loop 1 had written, so the response was to sweep loop 1's blast radius rather than to read colder. **Three lanes independently reached the same critical, and it was a regression this document would have shipped into the one appearance mode that exists for low-vision users:** §4.1 renames *Stop* to `#StopBtn`, and **every** rule in `_QSS` and `_HC_QSS` is qualified by object name — neither sheet has an unqualified `QPushButton` rule — so the rename drops *Stop* out of rest, `:hover`, `:checked`, `:disabled` and `:focus` in the high-contrast overlay as well as the base sheet, leaving it unstyled rather than mis-styled. Nothing here or in `docs/specs/ONEUP-0076-ringless-focus-cue.md` caught it; **INV-7 is new** and asserts the two sheets' object-name sets agree. **The second critical was an exemplar that says the opposite of what it was cited for.** §4.1 told the implementer *Stop* takes the danger colour "the family `#RestartBtn` on the reboot banner already uses" — but `#RestartBtn` is `color: #ffffff; border: none;` over a solid `#ef6a55` → `#d6412a` fill: white label, no border, filled. The red border `#e0553f` and the tinted ink belong to `#RebootBanner`, the *frame*. An implementer copying the named exemplar builds a filled red Stop, contradicting the same sentence's "transparent fill" and breaking the `card` derivation 0076 §4.2 assumes; §4.1 now cites the banner, names the hex, and says explicitly that `#RestartBtn`'s filled form is not what `#StopBtn` copies. **A lane's open premise turned out to be a functional regression rather than a missing contract, which is the second loop running that verifying an open question paid more than verifying a finding.** §4.1 moves *Retry* into `#WarnBanner` and called it "the banner a failed step already raises". It is not: `_show_warning` fires only when `self._hints or self._remedy_skips or self._remedy_keys`, while `retry_btn` is revealed separately by `if self._failed_steps:` — so **a run whose steps failed with no hint and no armed remedy shows Retry today with the banner hidden**, and reparented unchanged that run would leave the user no way to retry at all, past an INV-6 that asserted parentage only. §4.1 now requires the banner for any failed step, §4.2 records it as this item's one behaviour change, §6 carries the failure mode, and INV-6 asserts the hintless case. **INV-5 could not have passed as written:** its target set was two exclusions and one inclusion rather than a set, and at its own pinned 6 pt every `#GhostBtn` (`padding: 8px 14px`), every `#LinkBtn` (`padding: 4px 2px`) and the disclosure arrow fall under 24 px with no minimum anywhere — `run_btn.setMinimumHeight(44)` is the only explicit one in the window — while §4.1 promised a resize for the arrow alone. The set is now an eleven-row table naming what is in, what is out and why, with the lifting mechanism stated: a `min-width`/`min-height` pair on six rules in both sheets, which is a box dimension and so does not engage INV-3. **"That is the one string this item changes" was false by five.** The three new headings are strings, and `SettingsDialog._row(description, button)` takes a description per row, so the two controls moving in from the header need one each — they carry tooltips today, which `_row` does not read. All six are now given verbatim in a table, and §10's hand-off to `ONEUP-0032` names all six rather than "strings this item changes". Also draft: §9 and §4.1 both placed *Retry* in the primary action row when `actions.addWidget` takes only `check_btn`, `run_btn` and `stop_btn` and `retry_btn` is `root.addWidget`, its own full-width row beneath; the "*Stop* replaces *Check* in place" mechanism was unstated, so a build appending Stop at the end passed INV-6 — it is now a hide/show at one layout index, with `set_controls_enabled` gaining the `check_btn.setVisible` call it lacks; "of the four only Settings is used routinely" was an unsourced usage claim in a document whose header warrants every figure measured, and is gone rather than sourced; fixed point 1 was stated verbatim in both split halves (`doc_dedup` 1.000) while the paragraph beneath said it "is not re-argued here", and is now a pointer to its canonical home; and §7 called `testing.md` §2 "unchanged" while that standard's §2.3 records `Updater.__init__` issuing a live `api.github.com` GET on every construction — **ONEUP-0067**, 49 per run — which three new window-building sweeps add to, so §7 now names it and states that this item does not stub it. **Collateral worth naming, because each was loop 1's own sentence:** "appended last in that banner's layout … so it is last in the chain too" reproduces the exact inference §2.1 exists to disprove; INV-1's *Test:* clause did not carry the dialog scope §6 claims all three sweeps state, lacked INV-5's reveal step against controls constructed hidden, and named neither the chain's start widget nor its termination rule; INV-1 and INV-5 bound "each dialog reachable from the window", which over-binds `RepoManagerDialog` and `RollbackDialog` whose chains and targets this spec never touches; INV-6's "children of the header" names nothing testable, since `header` is the object-named `QLabel` and the buttons' Qt parent is `card`; INV-4 gave a precondition for the detail panel and not for the badge and disclosure, which are equally `setVisible(False)` in `TaskRow.__init__`, so three of its five cases would have passed vacuously; the 6 pt justification covers only the stylesheet path when the three tightest controls carry no `font-size` at all; and §10's independence claim now disagreed with `docs/design/oneup-2.0.md` §5.2, which loop 1 had itself edited to say 0076 "needs the layout and object names 0064 settles" — §5.2's wording is adopted as canonical and §10 no longer offers two ship orders and decides neither. **§8's bullet recording the completed 0076 repoint was moved here**, where finished work belongs; §8 is six bullets, re-counted rather than assumed. Its screenshot bullet also claimed both images are published — verified false: `README.md` embeds the dark one and the metainfo's single `<screenshot>` points at that same file, while `screenshots/oneup-light.png` is referenced nowhere outside the tree. **Dismissed: one** — lines 299/301 being byte-identical to 0076's 578/580 is the per-spec "Docs & release" template `documentation.md` §4 mandates, dismissed on the same reasoning in loop 1 and recorded again because all three lanes reach it every loop. **Carried as INFO:** `recenter_btn` moved inside `SettingsDialog` still centres the *main* window (`_kwin_recenter` skips `transientFor`) and the open dialog does not follow it. The document left this loop at **504 lines**, up from 348. |
| 1 | 2026-08-03 | 3 lanes; 5 critical, 6 high, 8 medium, 12 low, 0 info — **30 verified, 1 dismissed** — 30 draft defects vs 0 fix collateral (30 fixed, 0 carried) | The first review of this document on its own bytes. **The most valuable finding arrived as a lane's open question rather than as a finding**, which is the argument for verifying those too: §8 said *"`data/` carries no screenshot — the AppStream metainfo has none — so nothing in packaging shows the old layout."* Both halves are false. `screenshots/oneup.png` and `screenshots/oneup-light.png` are in the tree, `README.md` embeds the dark one, and the metainfo's `<screenshot type="default">` points at that same file over `raw.githubusercontent.com` — which is what a software centre renders. The redesign obsoletes two *published* images, and the release section said there was nothing to do; §8 now requires re-shooting both in the same commit. **Renumbering residue from the split took three shapes and one of them would have escaped this document:** two dead `§4.5` references, two dead `§2.3` references, and `INV-3` cited twice where `INV-1` was meant — the second of those inside §8's instruction to add a row to `ui-and-accessibility.md`'s **What checks this** table, which would have filed the `px`-check invariant against the tab-order rule. §2 also gained the `§2.2` its dead references had been pointing at. **§7's table was mis-mapped across every row** and credited a *"colour-never-alone"* sweep that is no invariant of this spec; it is the table an implementer builds tests from, so all six rows are restated and marked new or existing. **The central layout change was incomplete against the code it redesigns:** three Settings headings placed six of `SettingsDialog`'s eight rows and left `tray_btn` and `startboot_btn` with no home. The grouping is now a table, stated exhaustive, with the two header controls moving in — and its intro string, which describes only the first heading, is named as the one string this item changes. **A whole design decision lived only in §9 Alternatives** — *Retry failed steps* moving into the warning banner — so §4, the section an implementer reads, never mentioned it; it is now in §4.1 with the banner named `#WarnBanner` and its chain position stated after `warn_btn2`, which is a fourth button INV-1's expected chain has to carry. **The independence claim between the two split halves was false in both directions and unsupported by the section it cited:** each names exactly one hook in the other (`#StopBtn`'s transparent fill, and 0076's INV-1 sweeping the dialogs this item creates), and `docs/design/oneup-2.0.md` §5.2 did not mention 0076 at all — it now places it in this item's slot, as it had to for 0072. **Three figures were re-run offscreen rather than read:** 56×30, 19×19 and the 47.0 px arrow-to-switch clearance all reproduced exactly, and **760 px did not** — no `760` exists anywhere in `updater.py`, the window measures 560 wide with a 736 `sizeHint`, and two careful measurements disagreeing means delete, so §1 and §4.1 now carry the ratio the argument actually rests on. Also draft: INV-2 had dropped *"or visible text"* from the form `documentation.md` §5 and `ui-and-accessibility.md` §2 both state, so as written it would have failed on day one against every plain labelled button; INV-1's test compared position *within a parent*, which cannot see the cross-container inversions this redesign creates; INV-5's headline named the text scale its own test rejects, and called `_font_metrics` a clamp when it substitutes 10.0 outright outside 6–30 pt; and **INV-6 is new** — nothing asserted that the moved controls had actually moved. **Dismissed: one** — a lane reported the loop-log heading appearing twice, which was an artifact of the orchestrator's scrubbed copy, not of the document. The parent's rows below are relabelled `parent N` because this document's own loop 1 would otherwise collide with them. It left this loop at 347 lines, up from 268. |
| 0-split | 2026-08-03 | — | **Provenance, not a review — no reviewer was dispatched to produce this row.** On 2026-08-03 this document was split: the focus cue, its derivation and its check left for `docs/specs/ONEUP-0076-ringless-focus-cue.md` and the layout stayed here. Before the split it had run three cold-eyes loops (24, 34, 35 verified) and converged **by cap rather than clean** at 762 lines, with fix collateral outrunning draft defects two loops running — 24 → 13 → 8 draft against 0 → 21 → 27 collateral — and across those loops and nine lanes essentially every finding fell in the half that left. **Those loops were run against a document that no longer exists, so none of their assurance transfers**: this spec runs the gate from loop 1 on its own bytes, and the rows below it are the parent's, kept because the layout sections were present throughout and the record of what was asked of them is worth keeping. Invariants were renumbered INV-1…INV-5 from the parent's INV-6, 7, 9, 10 and 12; nothing outside this document had cited them. |
| parent 3 | 2026-08-03 | 3 lanes; 3 critical, 9 high, 14 medium, 10 low, 1 info — **35 verified, 2 dismissed** — 8 draft defects vs 27 fix collateral (34 actionable fixed, 1 info carried) | **Converged by cap, not clean, and the ratio is the reason this document should be split rather than reviewed a fourth time.** All three lanes led with the same defect and it was structural, introduced by loop 2: INV-2 had been given a *triple* clause requiring a retained rest border to clear 3:1 against the new focus fill — and loop 2 had also moved `ghostbd` to the smallest blend from `card` reaching 3:1, which is the same construction, in the same direction, as the focus fill derived from `card`. The two land on the same colour by arithmetic: **1.00:1** light and **1.03:1** dark, with the stop button's danger border at 1.49:1 and 1.59:1. The invariant was unsatisfiable on its first run and the ghost button's outline would have vanished into its own focus fill. A retained border now takes the **ink** colour, which inherits §4.1's 4.58 bound (6.92:1 and 6.04:1) — and the stop button's rationale went with it: its danger colour is a rest affordance, and what identifies it when focused is its label, not its tint. **The second finding all three lanes reached corrects a measurement of mine, not a claim of theirs.** Loop 2 recorded the high-contrast ghost button's focus pair as `$card` → `$btn`, pure black to pure white, 21:1 — but `_HC_QSS` groups `#GhostBtn:focus` with the primary buttons and sets `background: $btnhov`. `$btn` is what `:hover` sets. The real pairs are `#000000` → `#ffd400` (**14.67:1**) and `#ffffff` → `#0000cc` (**11.22:1**), so loop 2's row and the "weaken it sevenfold" arithmetic were both wrong while its *decision* — keep a pair that already clears 3:1 — stood. A lane also found that `_HC_QSS` restates `QPlainTextEdit#Log` with `border: 1px solid $border`, which would override mechanism B's 2 px rest border and drop the cue below SC 2.4.13's area threshold in exactly the appearance mode that needs it most; both overlay rules are widened in the same commit. **The most useful draft defect came from outside this document.** `docs/specs/ONEUP-0028-accessibility.md` §5 — shipped — promises `:focus` rules for eight styled controls including three that have none, and specifies a 2 px accent outline that the no-focus-ring decision forbids; §8 corrects it. Its own §2 had already logged *"No `:focus` rule anywhere in the QSS"* as a *"WCAG 2.4.7 failure"*, which independently corroborates the §8 correction loop 1 made to `ui-and-accessibility.md` §5.4. Smaller draft defects: the rule box stated two different algorithms (one anchored, one exhaustive) and `t` was never defined nor its 1% quantisation pinned, so two implementers would print different hexes; INV-12 varied `TEXT_SCALES`, whose smallest entry is the default `1.0`, so it tested nothing and the risk it names is the desktop font — it now pins 6 pt, `_font_metrics`' clamp floor; and a target-size clause had been filed under INV-13, a pure colour computation that cannot see a widget's size. **Dismissed: two.** A lane read §4.4's 101-point gradient sampling as unsourced; it is stated in §4.4 and produced §4.3's worst-pixel figures. And a lane asked whether the stride-3 lattice sweep was actually run rather than extrapolated — it was run; what is extrapolated is the *derivation* cost over that lattice, which is why INV-5 uses stride-16. **Trend across the three loops: draft defects 24 → 13 → 8, collateral 0 → 21 → 27.** The reads are finding less and the fixes are generating more, which is the documented signal that the document is past the review's design point rather than that it is bad. It left this loop at 762 lines. §11 recommends splitting the focus-cue contract (§4.1–§4.4) from the layout redesign (§4.5) before any further review. |
| parent 2 | 2026-08-03 | 3 lanes; 3 critical, 6 high, 13 medium, 12 low, 2 info — **34 verified, 2 dismissed** — 13 draft defects vs 21 fix collateral (32 actionable fixed, 2 info carried) | **Nothing loop 1 fixed came back**, which is the proof those fixes held — one lane recomputed every ratio in §2.2, §4.1 and §4.3 and reported them matching. What it found instead was **loop 1's own damage, and it outnumbered the draft defects two to one.** All three lanes led with the same finding, and it was an invariant loop 1 had *added*: INV-11 said every user-facing text colour clears 4.5:1, which annexes work `ONEUP-0027` §4.8 owns — light `lastrun` at 3.07:1 on `card` and 2.71:1 on `win`, light `amber` — and a pair §4.7 declares exempt (`disfg` on `disbg`). As written it would have failed on day one against three pairs this item never touches. It is now scoped to the colours this item introduces or moves. Two more were loop-1 rows that named things the check cannot read: the banner link button's surface was given as "`#WarnBanner`, `#InfoBanner` — its banner is re-used for both roles", which is simply false (four separate banners exist; `warn_copy_btn` is inserted into one), and both are **alpha gradients** rather than tokens, so §4.4 now states how a translucent rest colour is composited before measurement. **The finding worth the loop was a cue this spec would have made worse.** Loop 1 added high-contrast rows deriving a focus fill for every overlay button — but the overlay's `#GhostBtn` already goes pure black to pure white, **21:1**, and "the smallest blend reaching 3:1" would have cut it to 3.14:1, weakening the focus cue sevenfold in the one appearance mode that exists for low-vision users. §4.1 now states the rule is a floor: a pair already clearing 3:1 is kept. The draft defects the loop turned up were mostly a term used two ways: §4.1 said the cue is derived from "every surface the control can rest on", which is right for a transparent ghost button and wrong for the Run button, whose cue derives from its own fill — an implementer following it literally would have measured the accent against `card`. **Rest pixels** is now defined once and used in the rule, the table header and §1. Also draft: "every one of these focus colours is a lighter version of its rest colour" is false for the light ghost button, which *darkens* (0.598 → 0.349) and still reaches 1.62:1; white is 2.63:1 against the Run button's **top** stop, not its fill (the bottom stop reaches 4.70:1, and the worst pixel governs); `ghostbd` on `card` is handed to this item by `ONEUP-0027` §4.8 with the note that it cannot be deferred to an already-shipped item, and the spec was silent — now INV-13, closed at 3.02:1 and 3.09:1. Two loop-1 figures were wrong again: the `rowcard`/`rowhov` luminance gap was written as 0.02 when it is 0.004 dark and 0.069 light, and the lattice cost was called "measured" when it is extrapolated from a 1,331-colour run (~230 s, not ~226 s). **Dismissed: two.** A lane held the base sheet may carry no explicit `qproperty-highContrast: false`, making the painted-widget seam unfounded — it does carry one, with a comment saying the explicit default is mandatory. And a lane read INV-4's painted half as vacuous because `setFixedSize` fixes the geometry; that is right about `sizeHint()` and the half is kept, rewritten to compare *which pixels are painted* rather than the size. The document left this loop at **718 lines**, up from 623. |
| parent 1 | 2026-08-03 | 3 lanes; 2 critical, 7 high, 8 medium, 9 low, 2 info — **24 verified, 4 dismissed** — 22 actionable fixed, 2 info carried | The first review of this document. **Both criticals were the same defect seen from two sides: a claim about another document that this one had not earned.** §2.3 and §8 said the redesign fixed the light link button's 2.63:1 rest text and instructed `ONEUP-0027` §4.8 to record it closed — while §4 specified only a *focus* fill and never touched the rest colour, so §8 would have written a false row into a reviewed spec. §4.3 now carries `#3779bd` at 4.53:1 and INV-11 measures rest text, in every theme. The second was the mirror of it pointing at a standard: §8 called SC 2.4.7 *"already met"*, copying `ui-and-accessibility.md` §5.4 — but this document's own §2.1 measures sixteen focusable widgets with no cue at all, and a keyboard-operable control with no visible indicator fails 2.4.7, which is Level **AA**. The standard has been wrong since it was written for the four styled controls; §8 now corrects it rather than propagating it. **The most valuable finding was one all three lanes reached and the author had proved the opposite of:** §4.1 claimed the derivation "always succeeds", on an analytic bound that is only true for a *single* surface, while §4.1's own rule demands every surface a control rests on. Measured during verification — `#000000` and `#989898` admit no colour clearing 3:1 against both, and a coarse grey sweep finds **192** such pairs. The claim is now scoped, the search raises a named error instead of returning a best-effort colour, §6 carries the failure mode and INV-5 tests both halves. Three more were contract gaps an implementer would have had to invent: the high-contrast overlay was assigned mechanism B and mechanism A in one sentence, with no rows in either table (it is A, and the four rows exist); `#GhostBtn`/`#LinkBtn` derived from `card` alone when one link sits on the warning banner and another inside a task row, which is the exact defect §4.2 argues against for the disclosure; and `ToggleSwitch`'s row named `switchon`/`switchoff`, tokens `ONEUP-0027` creates *after* this item, with no seam stated for reaching a painted widget at all. **Two numbers were wrong and one was expensive.** The disclosure's 3.09:1/2.91:1 came from a derivation step the prose never describes — the reproduced figures are 3.00:1 and 2.83:1, and INV-2 had locked the wrong one into a test. And INV-5's 3-step lattice was measured at **~226 s** of pure Python inside the suite; it is now a 16-step lattice at ~1.5 s, with the fine sweep kept as a one-off. **Dismissed: four**, each checked rather than waved away. A lane held that Qt orders the focus chain by *creation*; a two-widget probe parenting them in reverse order showed the chain follows **parenting** order, so the document was right. A lane flagged `ONEUP-0034` §4.2 as cited for two different claims — both are in §4.2. *"Copy diagnostics"* was called undefined; it is `diag_btn` in the window. And an objection that §1's goal prose has no measurable referent was dropped: a Goal section is not an invariant. **Carried as INFO:** the switch's state shape is checked against its *resting* track by `ONEUP-0027` §4.7 but against no *focused* one (6.46:1 today, unchecked once `switchmark` becomes per-theme); and §4.5 making a whole row a click target would collapse §2.3's 47.0 px spacing-exception clearance, moot only because the arrow grows to 24×24. The document left this loop at **623 lines**, up from 495. |
