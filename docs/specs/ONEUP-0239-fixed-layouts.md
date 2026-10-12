# ONEUP-0239 — three fixed layouts, and the Settings choice between them

**Status:** Reviewed
**Kind:** feature
**Roadmap:** ONEUP-0239
**Branch:** v2
**Verified at:** `24f69d1` — every symbol below was opened on 2026-10-12.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes loop log

**In one sentence:** the window offers three layouts — Rows, Rail and Spotlight — chosen in
Settings, and in each one nothing moves or resizes while a check or a run fills it in.

**Part 2 of 3**, split by the user on 2026-10-12. ONEUP-0259 built the package model this
spec reads (`docs/specs/ONEUP-0259-package-model.md`, built in `52325d4`).
ONEUP-0260, the package details dialog, follows this one.

## 1. Goal

The window has three layouts, sketched for the user on 2026-10-10 and approved: **Rows**
(the five step rows above a package list), **Rail** (the steps down one side, the packages
as a board of cards) and **Spotlight** (large type about what is happening now, with *Up
next* and *Done* lists). The user picks one in Settings and the window switches at once.
In every layout, every area has a size set by the window and the text size, never by what
it holds: a package arriving, a step starting, a message appearing or the log being opened
moves nothing else on screen. Every package shows its name, versions, size, source and
state, read from `win.packages`; no layout writes to it.

## 2. Background

**Today the window grows and shrinks as a run fills it in.** The user reported it on
2026-10-08: *"buttons and boxes move and resize as detail appears"*. Every source of it is
a `setVisible` call on something in a layout:

- `TaskRow._on_disclosure` shows a row's package panel, pushing every row below it down.
  The panel is `QScrollArea#DetailScroll`, capped by `setMaximumHeight(180)`, so it grows
  with its content until the cap.
- `_set_activity` in `oneup/gui/run.py` shows and hides the liveness line.
- The four banners `Updater.__init__` builds with `banners._make_banner` — reboot,
  services, warning and app update — are shown and hidden as a run proceeds.
- `rollback_btn` is shown by `on_finished`.
- `Updater._show_log` shows and hides `#Log`, the window's only stretching area.

**One case is already solved, and it shows the shape.** `Updater._pin_check_stop_width`
gives Check and Stop the width of the widest label either shows, so the swap between them
moves nothing (ONEUP-0240). Each layout below generalises that: decide the size first,
from the font, and let the content fit it.

**The data exists; only the views are missing.** `PackageModel` in `oneup/gui/packages.py`
holds every package with `key`, `name`, `edition`, `old`, `size`, `repo` and `state`;
`shown_state` gives the state to show, `subscribe` reports which step changed, and
`STATE_WORDS` in `oneup/gui/steps.py` words each state. Today only `TaskRow._redraw` reads
it, as one line of text per package.

**What the sketches show that the window cannot give:** a percentage for one package
(zypper prints none), a time left (nothing estimates one) and a package's one-line
description (not in the model). None of the three appears below.

**The per-step progress the sketches show does exist.** `handle_marker`'s `STEP_BEGIN`
and `STEP_END` branches carry the step key, and `PROGRESS` carries `key|done|total|phase`.
Today the window draws them into one bar, `win.bar`, and into the row's badge text.

## 3. Scope decisions (agreed with the user)

1. **Three layouts, the user's choice in Settings** (2026-10-10). The three are the
   sketches at the roadmap item's link: `project/Main.dc.html`, `project/Rail.dc.html` and
   `project/Spotlight.dc.html`.
2. **Show the updates the way Discover does, in OneUp's own layout** (2026-10-10): each
   package with its versions and size, and a total. The raw log stays, behind a link.
3. **Toggle switches stay, the palette stays, no focus rings** — standing decisions,
   restated on the item.
4. **Messages live in one fixed strip** (2026-10-12). Every layout has one message strip,
   always in the same place and of fixed height. Empty, it shows nothing. Several messages
   stack inside it and it scrolls.
5. **The log swaps in place** (2026-10-12). The link exchanges the package area for the
   log, at the same place and size, and a second link exchanges it back.
6. **A layout change applies at once, even during a run** (2026-10-12).
7. **Rows is the default** (2026-10-12), for new users and for users upgrading from 1.4.
8. **No package percentage, no time left, no package description** — §2. The sketches'
   figures are replaced by counts the model can give.

Two calls this spec makes by deduction, stated so they are not mistaken for preference:

- **The package area opens on the packages, every launch.** The `log_shown` setting is no
  longer read. It defaults to `true`, so honouring it would open most upgraded windows on
  the log the new view replaces.
- **"Nothing moves" covers what the engine and the run do**, not what the user does.
  Resizing the window, changing the text size or switching layout may move things; a
  marker arriving may not.

## 4. Design

### 4.1 Shared controls, three hosts

**The window owns every control and every piece of run state; a layout only arranges
them.** This is `SettingsDialog`'s existing idiom — *"A host, not an owner"*, in its module
docstring — applied to the window's body. So badges, switch states, the status text and
the progress all survive a layout change, because none of them lives in the layout.

Three pieces of run state are new, all on the window and all cleared by `_reset_for_run`:

- `win.current_step` — the key of the step running now, or `""`. `STEP_BEGIN` sets it;
  `STEP_END` for that key clears it. Rail's board reads it (§4.3.1).
- `win.latest_package` — `(key, name, edition)` of the package named by the last `PKG`
  line, or `None`. Spotlight's latest-package line reads it, and the package's state from
  `win.packages` (§4.3.3).
- `win.engine_finished` — `False` until `on_finished` sets it. The package pages' empty
  sentence reads it (§4.3.1).

`current_step` and `latest_package` are kept by `handle_marker`.

**The header is not a layout's.** `header_row` stays in `#Card`, above the host, unchanged
in all three. The shared controls a host lays out, all built in `Updater.__init__`:

| Group | Controls |
| --- | --- |
| Steps | the five `TaskRow`s in `win.rows` |
| Actions | `win.action_bar`, a widget holding today's `action_row` unchanged — Run at index 0, Check at 1, Stop at 2 — so ONEUP-0064 INV-6 keeps holding |
| Status | `status`, `bar`, `bar_caption`, `activity` |
| Messages | the four banners, inside the new message strip (§4.4) |
| Package area | `win.package_area`, a `QStackedWidget`: the layout's package page, and `log` (§4.5) |
| Footer | `last_run`, `rollback_btn`, `log_toggle`, `openlog_btn` |
| Size | the "Show download size" link and its result, moved out of `TaskRow` (§4.6) |

A layout is a `QWidget` subclass, one per module, built with the window:

```python
class RowsLayout(QWidget):          # oneup/gui/layout_rows.py
    LAYOUT_ID = "rows"
    def __init__(self, win: Updater) -> None   # re-parents win's controls into itself
    def focus_chain(self) -> list[QWidget]     # its controls, in visual order
```

`RailLayout` (`oneup/gui/layout_rail.py`, `"rail"`) and `SpotlightLayout`
(`oneup/gui/layout_spotlight.py`, `"spotlight"`) have the same shape. Each also builds its
own package page from `win.packages` (§4.3). `Updater.apply_layout(layout_id)` builds the
new host, swaps its package page into `win.package_area` in place of the old one —
keeping whichever page was current — puts the host inside `#Card` below the header in
place of the old host, deletes the old one, and re-runs the `setTabOrder` loop over
`focus_chain()`, which becomes the header's three buttons plus the host's chain.
`__init__` calls it with the stored id (§4.7).

**A deleted host stops hearing the model.** `PackageModel` gains
`unsubscribe(callback)`, the inverse of `subscribe`. Each host gives back every callback it
subscribed, and `apply_layout` calls that before deleting it. Without it, the next marker
calls into a deleted widget from inside `handle_marker`, which must never raise.

`TaskRow` gains `set_form(form)`, with `form` one of `"full"`, `"rail"` and `"tile"`. It
re-arranges the row's own children and shows or hides its description; it never changes
what the row holds. Each host sets the form of all five rows.

**`TaskRow` loses its disclosure arrow and its detail panel.** ONEUP-0259 §4.7 built that
list for this item to replace; the package page replaces it. So `disclosure`,
`details`, `detail_scroll`, `_items_label`, `watch` and `_redraw` go, and
`_EXCLUDED` keeps `switch` and `badge`. The body still toggles the switch (ONEUP-0064
INV-4).

**Each row gains a thin progress bar of its own**, a `QProgressBar` with no text and
`Qt.NoFocus`, named for the screen reader *"Progress of {title}"*. `handle_marker` drives it
beside what each branch does today: `STEP_BEGIN` makes it busy (range `0, 0`); `PROGRESS`
for that key sets `done` of `total` when `total` is non-zero; `STEP_END` fills it.
`_reset_for_run` empties it. A step not selected for the run gets no markers and stays
empty; one that starts and ends as skipped, its tool absent, fills like any other, and its
badge says why. Its meaning is also in the
badge text, so the bar is never the only signal.

**The badge has a fixed width and is never hidden.** Today `TaskRow.__init__` hides it
until it has text, and its text grows as a step runs — *"3/10"*, then *"3 installed ·
42s"*. Both would move the row's other children. Its width is a fixed number of average
character widths at the current font; empty, it shows nothing in that space; longer
text is elided, with the full text in its tooltip and, as today, in the switch's
accessible description.

### 4.2 Sizes come from the font, never from the content

The rule every layout follows, and the one §5 tests:

1. **Every area's height is fixed from the current font**, as a number of text lines times
   `fontMetrics().lineSpacing()` plus padding, and recomputed when the text size or the
   desktop font changes — the event `Updater.eventFilter` already listens for on
   `check_btn` and `stop_btn`. A step row in Rows is two lines: title and description.
2. **Exactly one area per layout stretches**: the package area. It takes whatever height
   the window gives and has a minimum of six package lines.
3. **A control that can be hidden keeps its space.** Its `QSizePolicy` carries
   `setRetainSizeWhenHidden(True)`: `activity` and `rollback_btn`. **Two controls that take
   turns in one slot do not** — each would then hold a slot of its own. Check and Stop keep
   today's pinning, and the size link and its result take the same treatment (§4.6).
   **A control whose label changes is pinned to its widest label** the same way:
   `log_toggle` (§4.5).
4. **Text longer than its area wraps inside a scroll area or is elided.** A label outside
   a scroll area never wraps to more lines than its area holds. **Elision happens when the
   label is painted**: `text()` keeps the full text, so `_announce`, which reads
   `status`, and every test reading a label's text see it whole. The full text is also the
   tooltip.
5. **The window's minimum size is the layout's**, computed from the same metrics, so no
   window can be made too small to hold a layout at its current text size.

**Nothing below names a pixel figure for any of this**, because every one is a product of
the font (`docs/standards/ui-and-accessibility.md` §4).

### 4.3 What each layout holds

Top to bottom, below the header, in reading order. Rail and Spotlight mirror like any Qt
layout.

**Rows** (`project/Main.dc.html`)

1. The five rows in `full` form: title, description, badge, switch, and the bar along the
   row's foot.
2. The package area. Its package page holds a filter strip — three checkable `#GhostBtn`s
   in an exclusive group, *All*, *System packages*, *Flatpak apps*, with *All* the default,
   checked by the existing `#GhostBtn:checked` rule — then a summary line with the
   download-size link, then a table: state, package (with its source under the name),
   versions, size. The summary names what is shown, e.g. *"System packages · 24 updates ·
   17.5 MiB"*, so the chosen filter is said in words and not only by the button's look.
3. The message strip.
4. Status, bar, caption and activity, with Run and Check/Stop beside them.
5. Footer.

**Rail** (`project/Rail.dc.html`)

1. Two columns. **The rail**: the five rows in `rail` form — title and switch, badge, bar.
   Its width is fixed from the font: the widest step title, plus the switch and padding.
   It does not follow the badges, which elide to fit (§4.1). **The board** is the package
   area, and its whole package page: a summary with the download-size link (§4.3.1), the
   size strip (§4.3.2), and a grid of cards, one per package, each a fixed number of text
   lines: name; versions; size, source and state.
2. The message strip, full width.
3. Status, bar, caption and activity, with Run and Check/Stop.
4. Footer.

**Spotlight** (`project/Spotlight.dc.html`)

1. The five rows in `tile` form, side by side: title and switch, then badge. A title wraps
   to two lines rather than elide; the tile's height allows two.
2. The spotlight panel: the status, bar, caption and activity, the status in large type
   by a selector qualified on the panel; then the *latest package* line (§4.3.3), three
   figures (§4.3.1) and the download-size link (§4.6).
3. The package area, whose package page is two lists side by side, *Up next* and *Done*
   (§4.3.1). The panel above stays in view when the log is shown.
4. The message strip.
5. Run and Check/Stop, then the footer.

#### 4.3.1 Counts, and which packages each view shows

All counts are over `win.packages.packages(key)`, using `shown_state`:

| Group | States |
| --- | --- |
| to go | `queued` |
| now | `downloading`, `downloaded` |
| done | `installed`, `removed`, `unchanged` |

- **Rows' table** shows the filter's packages, all steps under *All*.
- **Rail's board** shows the packages of `win.current_step`, and all packages when it is
  `""` or names a step with none. Its summary reads the step's title (or *All updates*),
  the number of packages and their total size, then *"3 done · 1 now · 20 to go"*.
- **Spotlight's lists**: *Up next* holds to go and now; *Done* holds done. Its three
  figures are *Downloaded* (packages past `downloading`, of all), *Installed* (installed or
  removed, of all) and *Download* (the bytes of packages past `downloading`, of the total
  bytes). The *Download* figure reads *"not known"* when the total is `0`.
- **A total size counts only known sizes.** Where any package's size is `0`, the summary
  says so: *"17.5 MiB, some sizes not known"*. Sizes print with `_format_size` in
  `oneup/gui/markers.py`, as `TaskRow._redraw` does today.
- **Every package view shows the state word** from `STATE_WORDS`, as text, on every
  package. Spotlight's *Done* list mixes `installed`, `removed` and `unchanged`, so its
  group heading alone cannot carry the state.
- **With no packages**, each package page shows one sentence instead: *"Press Check for
  updates to see what will change."* while `win.engine_finished` is `False` and no engine
  is running; nothing while one runs; and *"No package updates."* once it is `True`. It
  says nothing about the other steps, whose badges speak for them.

#### 4.3.2 Rail's size strip

A painted widget, one block per package in engine order, each block's width in proportion
to its size; a package of unknown size gets the narrowest block. **State is never colour
alone**: each group has its own fill — solid for done, diagonal hatching for now, an empty
outline for to go — and a legend shows each fill beside its word. Blocks run in the reading
direction: the widget reads `QApplication.isRightToLeft()`, as `ToggleSwitch` does
(`docs/standards/ui-and-accessibility.md` §8.3). When there are more packages than the
strip has room for at two pixels each, neighbouring blocks of one group merge. It takes no
focus; its accessible name is the summary's counts sentence.

#### 4.3.3 Spotlight's latest package

One line naming `win.latest_package` (§4.1), with its state word from `shown_state`, its
versions and its source: *"libavcodec62 · downloading · 8.1.3-pm.2 → 8.1.3-pm.3 · Packman"*.
While it is `None` the line is blank, and it keeps its height.

### 4.4 The message strip

A `QScrollArea` named `#MessageStrip`, holding the four banners stacked in today's order.
Its height is three lines of banner text plus the banner's padding, at the current font.
Empty, it paints nothing and keeps its height. It takes no focus itself, so it is built
with `setFocusPolicy(Qt.NoFocus)`: a `QScrollArea` takes focus by default (its
`focusPolicy()` measured `11` under PySide6 6.11.0, 2026-10-12). The banners' buttons are
in the tab chain. **The strip scrolls a newly focused button into view itself**, with
`ensureWidgetVisible`, on `QApplication.focusChanged`: Qt does not do it when Tab arrives
from outside the strip (measured 2026-10-12, PySide6 6.11.0 offscreen — the scroll value
stayed `0` of `116`). A banner's own visibility rules are unchanged; only its parent moves.

### 4.5 The package area and the log

`win.package_area`, a `QStackedWidget` the window owns, with two pages: the current
layout's package page, and `win.log`. A layout switch keeps whichever page is current.
`log_toggle` reads *"Show technical log"* on the first page and *"Show packages"* on the
second, and flips the page. It is pinned to the wider of the two labels (§4.2 item 3).
`Updater._show_log` changes the page rather than the log's visibility, and stops writing
`log_shown`. Every call that today makes the log visible, so that a failure's
detail is on screen, makes the log page current instead.

### 4.6 The download-size link

`size_btn`, `size_result`, `size_pending`, `size_failed`, `set_size_result` and `has_size`
move from `TaskRow` to one window-level control with the same behaviour. Rows and Rail
show it in their package-page summary, Spotlight in its panel (§4.3).
`TaskRow.size_requested` goes; the link calls `run.request_size` for `system` directly.
The link and its result share one slot of fixed width — the widest of their texts — the
way Check and Stop do.

### 4.7 The Settings choice

`layout_btn`, a cycling `#GhostBtn` like `textsize_btn` and `logkeep_btn`, built in
`Updater.__init__` and laid out by `SettingsDialog` in the *Appearance* group after the
theme row, with the description *"How the main window is arranged. Changing it keeps
whatever is running."* Its label is *"Layout: {name}"*; the names are *Rows*, *Rail* and
*Spotlight*, each marked with `QT_TRANSLATE_NOOP`. Each click moves to the next of
`rows → rail → spotlight → rows`, stores the id under the `QSettings` key `layout` and calls
`apply_layout`. **The stored value is the id, never the label**, as the theme's is
(`Updater.on_theme_changed`). An unknown stored id shows Rows and leaves the stored value
alone, as `_refresh_theme_combo` does. `SettingsDialog.focus_chain` gains it after
`theme_combo`.

### 4.8 Styling

New object names: `#MessageStrip`, the three package views (`#PackageTable`,
`#PackageBoard`, `#PackageLists` — the last on both of Spotlight's lists), `#SpotlightPanel`,
`#SizeStrip`, `#PackageFilter` (the filter strip's frame) and `#PackageSummary`. Each styled
name gets a rule in both `_QSS` and `_HC_QSS` (ONEUP-0064 INV-7). **The containers
`#PackageFilter`, `#PackageSummary` and `#SpotlightPanel` paint no background**, so every
button on them rests on `card` — the surface the `#GhostBtn` and `#LinkBtn` rows of
ONEUP-0076 §4.2 already name, with their derived focus colours. The focusable package
views are scrolling content, so they take focus mechanism B: a 2 px rest border in
`$logbd`, `$border` under the overlay (ONEUP-0076 §4.2). Large type is a new `_FONT_SCALE`
entry, so it follows the text size like every other. No new palette key: every colour
above is one the palettes already carry.

## 5. Correctness invariants

- **INV-1** In each layout, at a fixed window size, no shared control and no area moves or
  resizes as a check or run proceeds. The message strip is one area: the banners inside it
  stack by design.
  *Test:* `tests/gui-smoke.py` — for each of the three layouts, builds the window at its
  minimum size and records, mapped to the window, the geometry of each area (each row,
  the package area, the message strip, the spotlight panel) and of each shared control
  outside the strip, recording a control only in stages where it is visible — a widget
  never laid out reports a default geometry, not a place. It then feeds markers: 200
  `CHECK_ITEM`s and their `CHECK`s; a run's `STEP_BEGIN`, `PROGRESS` and `PKG` lines; `on_finished` with a reboot, services, a warning with all its buttons and an
  app update; an activity line; `rollback_btn` shown; the log page made current. After each
  stage every recorded geometry is unchanged.
  *Breaks when:* a control is hidden without keeping its space, a label wraps to grow its
  area, or a view grows with its content.

- **INV-2** No text outside a scroll area is cut off, at every text size.
  *Test:* `tests/gui-smoke.py` — for each layout and each `TEXT_SCALES` entry, at the
  layout's minimum size, every visible `QLabel` with no scroll area among its ancestors is
  at least as tall as `heightForWidth(width())` for a wrapping label, or `sizeHint()` for
  one that does not wrap, unless it is elided with its full text in its tooltip.
  *Breaks when:* an area's height is a constant, or is measured once at one text size.

- **INV-3** Every package view shows every package's state as a word.
  *Test:* `tests/gui-smoke.py` — a model holding one package in each of the six shown states
  (a finished step supplies `unchanged`); in each layout, the text each view gives each
  package contains that state's translated `STATE_WORDS` word.
  *Breaks when:* a view shows state by colour, an icon or a list heading alone.

- **INV-4** No layout writes to the package model.
  *Test:* `tests/gui-smoke.py` — builds each layout over a filled model, replaces
  `reset`, `add_check_item`, `apply` and `end_step` with stubs that record a call, then
  triggers each layout's redraw through the model's subscribers; no stub was called.
  *Breaks when:* a view calls a write method, for instance to clear itself.

- **INV-5** A change to the model does not scroll a view.
  *Test:* `tests/gui-smoke.py` — each view holding 200 `queued` packages, scrolled to the
  end; a `PKG` line moves its first package to `downloading`, which keeps it in the same
  view in every layout; its vertical scroll position is unchanged.
  *Breaks when:* the view's model resets on every notification.

- **INV-6** Switching layout during a run keeps the run's state on screen.
  *Test:* `tests/gui-smoke.py` — mid-run (a `STEP_BEGIN`, a `PROGRESS`, `PKG` lines, a
  warning shown, the log page current), records each row's badge text and bar value,
  `status.text()`, `bar.value()`, the warning's visibility, `package_area`'s current page,
  `current_step`, `latest_package` and each package's state word; switches to each other
  layout in turn; every recorded value is the same after each switch, and a `PKG` line fed
  after each switch raises nothing and reaches the new layout's views.
  *Breaks when:* any of these lives in a layout rather than in the window, or an old
  layout's callback is left subscribed.

- **INV-7** Each layout lays out every shared control exactly once.
  *Test:* `tests/gui-smoke.py` — for each layout, every control in §4.1's table is found by
  walking the host's own `QLayout` tree, not merely by its parent chain; and `header_row`
  is found in none of them.
  *Breaks when:* a layout leaves out a control — `rollback_btn`, say — or parents it to the
  host without adding it to a layout, so it never gets a place on screen and a feature
  vanishes in that layout alone.

- **INV-8** The layout setting stores an id, cycles in order, and survives an unknown value.
  *Test:* `tests/gui-smoke.py` — three clicks of `layout_btn` from Rows store `rail`,
  `spotlight`, `rows` and apply each; a stored `nonsense` builds Rows and is still
  `nonsense` afterwards; with no stored value the window builds Rows.
  *Breaks when:* the label is stored, the order changes, or an unknown id is overwritten.

- **INV-9** Tab order follows visual order in every layout.
  *Test:* `tests/gui-smoke.py`'s ONEUP-0064 INV-1 walk, run once per layout, and once more
  in `SettingsDialog` with `layout_btn` in it.
  *Breaks when:* a host's `focus_chain` omits a control or lists one out of place.

- **INV-10** The size strip shows each state group by a different fill, and runs in the
  reading direction.
  *Test:* `tests/gui-smoke.py` — the strip's fill for each of the three groups is a
  distinct `Qt.BrushStyle`; and in the `-reverse` pass, with the first package done and the
  rest to go, a pixel near the right edge carries the done fill and one near the left the
  to-go fill. **Partial**: nothing checks that the fills stay legible in every theme beyond
  the colours the palette sweep already measures.
  *Breaks when:* two groups share a fill, or the painter lays blocks out from the left
  regardless of direction.

- **INV-11** A row's progress bar follows its own step only.
  *Test:* `tests/gui-smoke.py` — `STEP_BEGIN|system|1|2` makes the system row's bar busy
  and leaves flatpak's empty; `PROGRESS|system|3|10|download` sets it to 3 of 10;
  `STEP_END|system|ok` fills it; then `STEP_BEGIN|flatpak|2|2` and
  `PROGRESS|flatpak|1|0|download` leave flatpak's bar busy rather than at 1 of 0.
  *Breaks when:* a bar reads another key's marker, or divides by a zero total.

## 6. Failure modes

| Assumption | When it breaks | What the user sees |
| --- | --- | --- |
| The window is at least the layout's minimum size | A tiling window manager forces it smaller | Areas clip at the window's edge. The layout still does not move as data arrives |
| A label's text fits its area | A long translation, or a long repository name | Elided, with the full text in the tooltip and to the screen reader (§4.2 item 4) |
| More messages fit the strip | A reboot, a services note, a warning and an app update at once | The strip scrolls; Tab reaches every banner's buttons and scrolls each into view |
| Package sizes are known | ONEUP-0259 §6: a repository with no raw cache, no `zstdcat`, a lookup past its deadline, any Flatpak | The size column is blank; totals say *"some sizes not known"*; Rail's block is the narrowest |
| The engine's order is a useful order | `dup` installs in its own order, not `list-updates`' | The lists stay in engine order and do not reorder or scroll; Spotlight's latest-package line names what is happening |
| A run has thousands of packages | A large Tumbleweed snapshot | The views are item views and paint only the rows in sight; the size strip merges blocks (§4.3.2) |
| A step reports a total | `PROGRESS` with total `0`, zypper's preload phase | That row's bar stays busy rather than showing a fraction |
| The window read every marker | A window attached to a run already going (ONEUP-0045) | Packages from markers it did not read are missing, as ONEUP-0259 §6 records |

## 7. Tests

INV-1, INV-2, INV-3, INV-4, INV-5, INV-6, INV-7, INV-8, INV-9, INV-10 and INV-11 are all
tested in `tests/gui-smoke.py`, each as its §5 clause says. Beside them:

- **ONEUP-0076 INV-1's sweep** fails any focusable widget missing from its `FOCUS_TABLE`, so
  the three package views and the filter buttons get rows there, as ONEUP-0027 added
  `ThemeCombo` and `ThemeList`. Its `Disclose` and `DetailScroll` rows go with the widgets.
- **ONEUP-0064 INV-7's parity check** fails a new object name styled in `_QSS` with no
  `_HC_QSS` rule.
- **ONEUP-0064 INV-4's** clicks on the disclosure and the detail panel go; its clicks on the
  row body, the switch and the badge stay, and run once per form.
- **ONEUP-0064 INV-6's** action-row assertions keep holding: `win.action_bar` carries the
  same `action_row`, at the same indices, into every layout (§4.1).
- **ONEUP-0064 INV-5's** 24 px pointer-target walk gains the filter buttons and
  `layout_btn`, and loses the disclosure.
- **ONEUP-0259 INV-13's** check that *"the redrawn list shows the table's word"* moves to
  INV-3 here, which covers all three layouts' views.
- **The whole suite already runs twice** — once mirrored by `-reverse` — so every test
  above runs right-to-left as well.

Each new test is seen failing first: the geometry, clipping and layout tests against the
window as it is today, and the model tests before the views exist.

## 8. Docs & release

- `docs/standards/ui-and-accessibility.md` — §8.3's paragraph on the disclosure arrow goes,
  with that arrow; §8.3 gains the size strip as the second painted widget in a layout; the
  *What checks this* row for §8.3 names INV-10 here.
- `docs/specs/ONEUP-0064-interface-redesign.md` — INV-1, INV-4 and INV-5 each gain a note
  that the disclosure and the detail panel were removed by ONEUP-0239.
- `docs/specs/ONEUP-0076-ringless-focus-cue.md` — §4.2's rows for `QToolButton#Disclose`,
  `QScrollArea#DetailScroll` and `size_btn` inside a row's detail panel gain the same note,
  and the table gains the three package views.
- `docs/specs/ONEUP-0259-package-model.md` — §4.7 gains a note that ONEUP-0239 replaced the
  per-row list, and §4.6's API gains `unsubscribe` (§4.1).
- `CHANGELOG.md` `[Unreleased]` — one user-facing line: three window layouts to choose from
  in Settings, none of which moves as an update runs.

No marker changes: the marker contract stays frozen (`docs/reference/marker-protocol.md`
§5.1). No engine change. No new file outside `oneup/`, so no packaging change
(`docs/standards/files-and-naming.md` §6).

## 9. Alternatives considered (and rejected)

- **Steps side by side, each with its own log** — the user's first idea, 2026-10-08.
  Rejected on the item: five columns leave each about a phone's width, so package names and
  versions wrap or clip, and worse at large text.
- **One fixed layout instead of three.** Superseded by the user's choice on 2026-10-10.
- **Discover's inline details panel.** It moves the list, which is the complaint; the
  details open as a dialog in ONEUP-0260.
- **A layout-owned copy of each control.** Three copies of every button, badge and bar,
  each kept in step by hand, and a layout switch mid-run would lose whatever one copy held.
  One owner and three hosts is the idiom `SettingsDialog` already uses.
- **`QTabBar` for Rows' filter.** It is a focusable control the focus derivation has no row
  for, and the platform style may paint its own focus frame on the current tab — a ring,
  which `docs/standards/ui-and-accessibility.md` §5 forbids. Three `#GhostBtn`s already
  have a measured focus treatment.
- **Custom item painting for Rail's cards.** Qt's own item delegate draws multi-line text
  and mirrors it. A painted card would be a third painted widget owing its own
  right-to-left handling.
- **Following the running package by scrolling the list.** That is movement the user did
  not ask for. Spotlight's latest-package line and Rail's board both say what is happening
  without moving anything.
- **Honouring `log_shown`.** §3, the deductions.

## 10. Out of scope

- The package details dialog — ONEUP-0260.
- What a Flatpak size means — ONEUP-0241.
- A percentage for one package, a time left, and a package's description (§2).
- Package lists for firmware, leftover packages and the cache; those rows keep their badges
  (ONEUP-0259 §10).
- Whether the download-size link is still needed now that sizes show after a check. It
  moves unchanged (§4.6).
- Reshooting the trailer — ONEUP-0261.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-10-12 | Q1 1 · Q2 3 · Q3 4 · Q4 3 — 11 verified, 6 dismissed | all 11 fixed. Two lanes, each holding every question; both found the header's owner, the rail sized from its badges, the missing slot for Spotlight's size link, the unnamed current-step state and INV-11's flatpak bar. Two Q3s and the Q1 came from settling open questions: the stack's owner, the latest package moved to the window, and a `QScrollArea`'s default focus (measured `11`). The six dismissed changed nothing built, each a false sentence corrected by deletion: four from a peer session's fact-check (the banner hide list, a ONEUP-0259 misquote, an over-cited §10, ONEUP-0064 INV-7 described as two-way), plus "three focusable views" and "every 1.4 user has it stored" |
| 2 | 2026-10-12 | Q1 1 · Q2 3 · Q3 6 — 10 verified, 0 dismissed | all 10 fixed; the cap for a spec, so this loop's fixes are read by no lane, and implementation reads them. Two lanes, each holding every question; both found the missing `unsubscribe` for a deleted layout and the unclear edge of the package page. The Q1 is a measurement a lane asked for: Tab arriving from outside the message strip does not scroll it (value stayed `0` of `116`). The Q2 on a skipped step's bar came from settling an open question. Own-fix share 3 of 10 — the package page's edge, the empty sentence and the board during a step with no packages — read as a calm cap, but the armed change was the whole document, so the share says little; no second share for the same reason |
