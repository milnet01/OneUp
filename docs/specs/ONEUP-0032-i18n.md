# ONEUP-0032 — translation groundwork

**Status:** Draft
**Kind:** enhancement
**Roadmap:** ONEUP-0032
**Branch:** v2
**Verified at:** `36599ea` — every Qt behaviour below was measured against the installed
PySide6 6.11 / Qt 6.11 on 2026-07-27, not recalled, and every quoted symbol was read from
the tree.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** OneUp 2.0 ships in English and in English only, but every sentence a
user can read is wrapped so a later contributor can translate it with a data file, the
window is proven to mirror for Hebrew and Arabic by a test rather than by hope.

**This item was split in two** at its fifth review loop, because it held two contracts.
**`docs/specs/ONEUP-0072-marker-codes.md`** now owns the engine→window payload conversion —
turning the engine's prose into codes the window words itself. This spec keeps the
translation machinery and right-to-left. They ship as two changes, **this one second** —
`docs/design/oneup-2.0.md` §5.2 owns that order and ONEUP-0072 §3.3 records why the pair
once claimed to depend on each other in both directions. The dependency runs one way:
ONEUP-0072 builds the sentence tables and ONEUP-0077 puts sentence-rendering on the two
headless paths,
and this item then marks those tables and gives those paths the application object they need
to render a translated one (§4.2). Neither spec restates the other.

**Two documents already own most of this and are not re-argued here.**
`docs/standards/wording-and-translation.md` §5–§7 owns where wording lives, how a
translatable string is written and the catalogue workflow.
`docs/standards/ui-and-accessibility.md` §8 owns the four right-to-left rules. What this
spec adds is the part they leave to this item: the mechanism that loads a catalogue, the
rules the wrapping work follows, and the tests that make the groundwork provable while no
second language exists.

## 1. Goal

After this ships, a contributor who wants OneUp in German writes one file and compiles it;
no Python changes. The half that runs as root carries no locale machinery at all. The
window renders every sentence itself, through Qt's translation layer, with plural forms and
named placeholders. And `tests/gui-smoke.py` runs a second time with the layout direction forced
right-to-left, so a widget that hard-codes a side is caught by a gate rather than by a
Hebrew user — with three stated limits, in §7; chiefly that a *newly hand-painted* widget
still needs somebody to write its own check.

## 2. Background

### 2.1 There is nothing to build on

Measured at `36599ea`: `grep -c 'self\.tr(\|QCoreApplication\.translate' updater.py`
returns **0**. No catalogue exists, no `QTranslator` is constructed, and no code reads the
layout direction. `docs/standards/wording-and-translation.md`'s own **What checks this**
table records the consequence — its §6.1 and §7 rows both say nothing checks them, because
there is nothing yet to check.

The starting position for right-to-left is good and was surveyed before this spec:
`ui-and-accessibility.md` §8 holds the survey and names the sites that will not mirror.
§4.4 is what this item does about them.

### 2.2 What Qt does, measured rather than assumed

Every row below was run against PySide6 6.11 / Qt 6.11 on 2026-07-27. They decide §4.2, and
most of them contradict what the mechanism is usually assumed to be.

| Question | Measured answer |
| --- | --- |
| Does the system locale set the layout direction? | **No.** With `LC_ALL=he_IL.UTF-8` and no catalogue, `QApplication.isRightToLeft()` is `False` |
| What does set it? | An installed `QTranslator`. Loading `/usr/share/qt6/translations/qtbase_he.qm` and installing it flips `isRightToLeft()` to `True` on its own |
| Does `-reverse` survive? | Yes through an installed left-to-right catalogue — but an explicit `setLayoutDirection()` call **clobbers it** |
| Does an uninstalled reference matter? | Yes. A `QTranslator` created inside a function and installed without keeping a reference is garbage-collected, and the application silently reverts |
| Does any of it work with no application object? | No. `installTranslator` prints *"Please instantiate the QApplication object first"* and returns `False`; `translate` returns the English. A plain `QCoreApplication` — no display needed — is enough |
| Does `-reverse` work with **no** catalogue installed? | **Yes** — `QApplication(sys.argv)` with `-reverse` and no translator reports `isRightToLeft()` `True`. This is the case the gate actually runs in, since 2.0 ships no catalogue |
| Does Qt consume the arguments it reads? | No. `sys.argv` is byte-identical before and after `QApplication(sys.argv)`, so `--check`/`--tray` membership tests are unaffected |

Rows three, four and five are the ones that would have shipped as bugs. A window that sets
its own direction at startup makes the `-reverse` test pass while proving nothing; a
translator nobody holds turns the whole feature off after the first collection; and a timer
path with no application object silently renders English whatever the catalogues say.

Two more, verified by running the tools rather than reading about them:
`pyside6-lupdate` extracts `QT_TRANSLATE_NOOP("Hints", "…")` from a **module-level dict**
under the context given, alongside `self.tr(…)` from a class — so a lookup table of
sentences is extractable without being inside a widget. And the full round trip works:
mark, extract, translate, `pyside6-lrelease`, load, and `QCoreApplication.translate` returns
the translated text where it returned the English before.

## 3. Scope decisions (agreed with the user)

| Decision | Who, when |
| --- | --- |
| 2.0 ships the **groundwork only** — English alone. Another language is a post-2.0 data file | the user, 2026-07-26 (design §5.1) |
| **Right-to-left is in scope** and lands with the groundwork, not with the languages | the user, 2026-07-26 (design §5.1) |
| The gate tests the **machinery**, not a translation: the GUI suite passes with the direction forced right-to-left | inherited, not chosen here — design §5.1, gate **G10** |
| This item is **last** in 2.0, and starts only after the engine rewrite has passed its gate | inherited, not chosen here — design §5.2 |

### 3.1 What this spec does not decide

- **How a sentence is worded.** `wording-and-translation.md` §2–§4 owns that. Wrapping a
  string for translation is not a licence to rewrite it.
- **Which languages ship.** None, in 2.0 (design §5.1). §10.
- **How the interface is laid out.** ONEUP-0064 lands first and its layout is what gets
  mirrored.

## 4. Design

### 4.1 Where the machinery lives

Three placements, and two of them are modules 2.0 already creates before this item runs
(`docs/standards/coding.md` §4.2 — split by responsibility, and only when there is one).

| Module | Gains |
| --- | --- |
| `oneup/gui/i18n.py` *(new)* | loading the catalogues, and holding them for the process's lifetime |
| `oneup/gui/markers.py` | the marking of its sentence tables for translation — ONEUP-0072 builds the tables |
| `oneup/gui/steps.py` | the **marking** of the in-progress phrasing for each step — ONEUP-0072 stops the engine sending it and writes the window's own |

`oneup/gui/markers.py` is where the sentence tables belong rather than a new module:
ONEUP-0034 §4.2 already gives it *"reading what the engine said, and saying it in English"*.
`docs/specs/ONEUP-0108-window-wording.md` §4.1 builds them, in ONEUP-0072's landing commit;
what this item adds is that their English is marked for
translation like any other string (§4.3).

`oneup/gui/i18n.py` is separate because it is the one thing that must happen **before any
translatable string is evaluated**, which in practice means before the first widget is
constructed. Every entry point in `oneup/gui/app.py` calls it immediately after building its
application object — `main` after the `QApplication`, and the two headless paths after the
`QCoreApplication` they gain in §4.2. There is no path that renders a sentence without
having called it.

### 4.2 Loading a catalogue

Seven rules: six turn §2.2's measurements into code, and the last restates
`wording-and-translation.md` §7.

**The language comes from the system locale, and Qt does the matching.** Both catalogues
load through `QTranslator.load(QLocale(), <prefix>, "_", <dir>)`, so Qt's own fallback chain
applies — `de_AT` falls back to `de`, and the two catalogues count as a pair even when they
match at different specificity. Nothing reads `LANG` or `LC_ALL` directly. §2.2's first row
measured that the locale does not set the *direction*; choosing the *language* is the one
job it does keep.

**Two catalogues, loaded as a pair or not at all.** OneUp's own `oneup_<lang>.qm` and Qt's
`qtbase_<lang>.qm`. **The loading function takes both directories as arguments**, defaulted
to `QLibraryInfo.path(TranslationsPath)` for Qt's and to the `translations/` directory
inside the `oneup` package for OneUp's — resolved from the package's own location rather
than the working directory, which is what makes a checkout,
the AppImage and the RPM find it by the same relative path
(`wording-and-translation.md` §7). Neither default is ever a hard-coded absolute path, and
the arguments are what let INV-2's test point both at `mktemp` directories instead of
writing into a real Qt installation (`docs/standards/testing.md` §2.3). If either fails to load, neither is installed and the application stays
English. This is what stops the worst intermediate state: Qt's base catalogue alone flips
the layout to right-to-left, so loading it without ours would mirror a window still full of
English text.

**The application never calls `setLayoutDirection`.** Qt derives the direction from the
installed catalogues, and an explicit call overrides `-reverse` (§2.2) — which would make
the gate in §7 pass while testing nothing. `ui-and-accessibility.md` §8.4 already forbids
*reading* the direction from anywhere but the application; this is the writing half.

**The translators are held for the process's lifetime** — module-level in
`oneup/gui/i18n.py`, not local to the loading function. §2.2 measured what happens
otherwise.

**Every `QApplication` is constructed with `sys.argv` — and there are two.** Today's tree
shows why: `main` in `updater.py` passes `QApplication([])`, so Qt sees no arguments and
`-reverse` cannot reach it, and **`tests/gui-smoke.py` builds its own** —
`QApplication.instance() or QApplication([])` — and never calls the application's `main`, so
changing only the application would leave the gate in §7 running left-to-right while
reporting a pass. The two call sites this item changes are the 2.0 ones: `oneup/gui/app.py`
(which replaces `updater.py`, ONEUP-0034) and `tests/gui-smoke.py`. Qt consumes only its own options and leaves Python's `sys.argv` alone, so
the existing `"--tray" not in argv` and `"--check" in sys.argv[1:]` membership tests are
unaffected.

**Every entry point builds an application object first, and two of them have none today.**
`main` dispatches `--check` and `--update` — the two systemd user timers — and exits before
`QApplication` is built. §2.2 measured what that costs: with no instance `installTranslator`
refuses outright and `translate` hands back the English. Those two paths construct a
**`QCoreApplication`**, not a `QApplication`: it is enough for the catalogues and needs no
display, which a timer may not have. `docs/specs/ONEUP-0077-headless-notification.md` is what
makes them need it — it puts sentence-rendering on those two paths, and its own INV-5 forbids
an application object until this item arrives, so **this item retires that invariant** as it
adds the `QCoreApplication`. (That work was ONEUP-0072 §4.4 until the 2026-08-03 split moved
it; that section no longer exists.)

**A missing catalogue is not an error** (`wording-and-translation.md` §7). In 2.0 it is the
*normal* case: no `.ts` file for any language is written, so `load()` returns `False` on
every desktop and the application runs in English, which is correct.

### 4.3 Wrapping the window's strings

`wording-and-translation.md` §6 is the rule and is not restated. Three things this item adds
to it, each because the tree makes them necessary:

- **A table of sentences outside a class uses `QT_TRANSLATE_NOOP`**, with the lookup calling
  `QCoreApplication.translate` at render time — verified extractable in §2.2. `self.tr()`
  is unavailable at module level, and marking at definition while translating at render is
  what lets the language change without rebuilding the table. An entry needing
  `wording-and-translation.md` §6.4's disambiguation comment takes `QT_TRANSLATE_NOOP3`,
  which is the only one of the two forms with a slot for it. **Both macros return only the
  source string** — measured, not assumed: `QT_TRANSLATE_NOOP3("Hints", "Lock", "…")`
  evaluates to `"Lock"`, and the context and disambiguation survive only in what
  `pyside6-lupdate` extracts. So the table stores the context and disambiguation itself and
  the render-time call passes all three to `QCoreApplication.translate`; a lookup that omits
  the disambiguation is a different key and silently returns the English.
- **A sentence built by an f-string or by `+` is a concatenation**, and INV-7's check is the
  only thing that catches either. `wording-and-translation.md` §6.2 forbids both and its own
  **What checks this** row against §6.2 reads `nothing automatic`; the one sweep in the tree
  is `docs/design/oneup-2.0.md` §5.1's `grep -cE '"\s*\+|\+\s*"' updater.py`, which that
  section calls a measurement of the work rather than a gate, and which sees no f-string at
  all. `handle_marker` builds both `f"{row.title}: {badge}"` (the
  sentence it passes to `_announce`) and the status line's `f"{label}…"`, and neither is
  reachable by a translator.
- **Accessible names and descriptions are wrapped too.** They are read aloud, so they are
  user-facing in the most literal sense (`ui-and-accessibility.md` §2).

### 4.4 Right-to-left: the three things Qt will not do

Qt mirrors every layout built from its own containers once the direction is set, and does
nothing else. `ui-and-accessibility.md` §8 owns the four rules; the work this item does
under them is:

- **`ToggleSwitch` applies the direction itself, at both handed sites, and they are handed
  differently.** §8.3 names them: the knob is unconditionally left-anchored, while
  `_paint_state_shape` picks its edge from the state, so the two need different fixes rather
  than the same one twice. Fixing only the knob is worse than fixing neither — the state
  shape is `ui-and-accessibility.md` §3's colour-blind cue, so a half fix breaks the cue in
  Arabic while looking right
  in English. Both read `QApplication.isRightToLeft()`, never the widget's own
  `layoutDirection()` (§8.4).
- **`QPushButton#LinkBtn`'s `text-align: left` goes** (§8.1). The progress bar's
  `text-align: center` stays: centre has no handedness.
- **Nothing else acquires a directional property or a fixed `AlignLeft`/`AlignRight`.**
  `AlignLeft`/`AlignRight` are already at zero; directional stylesheet properties reach zero
  once the bullet above removes the one site. From then on the check in §7 is a guard
  against growth.

The tray icon is painted by hand too and is deliberately untouched — it is an icon in a
system tray, not a widget in a mirrored layout (§8.3).

## 5. Correctness invariants

- **INV-1** Nothing under `oneup/engine/` imports or calls translation machinery —
  `QTranslator`, `QCoreApplication.translate`, `tr`, `gettext`. The privileged half has no
  locale.
  *Test:* `tests/i18n-check.py`, the engine-purity check.
- **INV-2** Both catalogues are installed, or neither is. A `qtbase` catalogue is never
  installed on its own, because it alone sets the layout direction. It guarantees nothing
  about how *complete* OneUp's catalogue is; a stale translation is a translator's problem,
  not a loading one.
  *Test:* `tests/gui-smoke.py` compiles a hand-written two-string `.ts` with
  `pyside6-lrelease` — **not** the way INV-8's check builds one, whose freshly extracted
  messages are all unfinished and compile to a catalogue that translates nothing — and loads
  three times, with §4.2's two directory arguments pointed at `mktemp` copies: both
  catalogues present, **`qtbase` only**, ours only, neither — asserting installation only in
  the first. The `qtbase`-only case is the one that falsifies the rule above and is named
  rather than left to a choice of "one present"; ours-only cannot fail it. Skips,
  with the rest of the suite still running, when `pyside6-lrelease` is absent (§7).
- **INV-3** The application never calls `setLayoutDirection`, and no widget reads its own
  `layoutDirection()`; the direction is Qt's to derive and `QApplication.isRightToLeft()`'s
  to report (`ui-and-accessibility.md` §8.4). Writing it would override `-reverse` and make
  INV-5's pass vacuous — so the check reads `tests/` as well as `oneup/`, because a
  `setLayoutDirection` in the suite defeats `-reverse` exactly as one in the application
  does, and INV-5 would then pass on a window that was never mirrored.
  *Test:* `tests/i18n-check.py`, the direction check.
- **INV-4** An installed translator is referenced for the process's lifetime.
  *Test:* `tests/gui-smoke.py` asserts a translated string still translates after
  `gc.collect()`.
- **INV-5** The GUI suite passes with the layout direction forced right-to-left, **and
  asserts that it is right-to-left** before running its checks. A pass that silently ran
  left-to-right proves nothing.
  *Test:* `tests/gui-smoke.py -reverse`, run as a second pass by `local-CI.sh` and
  `.github/workflows/release.yml`; its first assertion is `QApplication.isRightToLeft()`.
- **INV-6** No *left- or right-handed* stylesheet property and no hard-coded
  `AlignLeft`/`AlignRight` exists anywhere under `oneup/` (`ui-and-accessibility.md` §8.1,
  §8.2). `text-align: center` is not handed and is deliberately kept (§4.4).
  *Test:* `tests/i18n-check.py`, the directional-property check.
- **INV-7** Every string passed to a text-setting call in `oneup/gui/` is wrapped, with no
  bare literal, no f-string and no `+` concatenation (§4.3 — nothing else in the tree checks
  either kind). **The list is closed and lives in `tests/i18n-check.py`**;
  adding a text-setting API to the window means adding it there in the same commit, because
  anything off the list is silently exempt. It starts as: `setText`, `setToolTip`,
  `setWindowTitle`, `setAccessibleName`, `setAccessibleDescription`, `setPlaceholderText`,
  `addItem`, `setInformativeText`, `setStatusTip`, `setWhatsThis`, `setTitle`, the
  `QMessageBox` class methods (`warning`, `critical`, `information`, `question`) and
  `QSystemTrayIcon.showMessage` — 23 `QMessageBox` call sites exist in the 1.x window
  already. **The list is not Qt-API-shaped: it is every call that hands a sentence to a
  user**, so it also carries the two that reach one without a setter — the screen-reader
  announcement (`_announce`'s 2.0 equivalent, which is the very site §4.3 offers as its
  example) and the `notify-send` body `ONEUP-0077` composes, which
  `wording-and-translation.md` §6.1 names explicitly. Both deliver prose a user reads or
  hears, and neither passes through any setter above.
  *Test:* `tests/i18n-check.py`, the wrapping check. It reads the call's argument, so it
  catches a literal, an f-string and a `+` expression; it cannot follow a string through a
  variable, and §7 says so.
- **INV-8** The catalogue extracts and compiles. **`pyside6-lupdate` is given the `.py`
  files under `oneup/`, never the directory** — measured on PySide6 6.11,
  `pyside6-lupdate oneup/ -ts …` reports `Found 0 source text(s)` with or without
  `-recursive`, and only a file list extracts anything. **The pass criterion is a *finished*
  translation surviving the round trip, not a file that exists**: `pyside6-lrelease` drops
  every unfinished message, so a freshly extracted catalogue compiles to a 33-byte `.qm`
  carrying zero translations — non-empty as a file, empty as a catalogue. The check writes a
  translation into one extracted message, compiles, and asserts that string comes back from
  `QCoreApplication.translate`.
  *Test:* `tests/i18n-check.py`, the catalogue-build check. It alone skips when the Qt
  translation tools are absent; the suite's four grep checks still run (§7).
- **INV-9** Both headless entry points construct a `QCoreApplication` and load the
  catalogues **before** the first sentence is rendered. This replaces `ONEUP-0077`'s INV-5,
  which §8 deletes: that invariant asserted the opposite and is the only thing guarding the
  path, so retiring it without this leaves §2.2's third measured bug — *"a timer path with no
  application object silently renders English whatever the catalogues say"* — covered by
  nothing at all.
  *Test:* `tests/gui-smoke.py`, INV-5's own subprocess harness inverted — each entry point
  run in a subprocess, asserting the application object exists by the time a sentence is
  composed.

## 6. Failure modes

| When this breaks | What the user sees | Why it is survivable |
| --- | --- | --- |
| A catalogue file is missing or corrupt | English, laid out left to right | `load()` returns `False` and nothing is installed (INV-2); a missing catalogue is the normal case in 2.0 |
| A translator is garbage-collected | Silent reversion to English mid-run | INV-4 is the guard; §2.2 measured that it happens without one |
| Somebody adds a `setLayoutDirection` call | Nothing — and that is the danger: the right-to-left gate goes green while running left to right | INV-3 is the guard, and it exists because nothing else would notice. §2.2 measured that an explicit call beats `-reverse` |
| A new widget hard-codes a side in a stylesheet or an alignment flag | A control on the wrong side, in Arabic and Hebrew only | INV-6 catches it in the source, whatever the widget |
| A new widget hard-codes a side in its own `paintEvent` | The same, and **nothing catches it** | The RTL pass only samples the pixels of the one painted widget that exists today. §7 |
| A sentence is added without `tr()` | It stays English in every language | INV-7 catches it at the call site. A sentence assembled through a variable is not caught — §7 |

## 7. Tests

| What it locks in | Where |
| --- | --- |
| INV-2, INV-4 — the catalogue pair and the translator's lifetime | `tests/gui-smoke.py`, new checks |
| INV-5 — the whole window under right-to-left | `tests/gui-smoke.py -reverse`, a second run wired into `local-CI.sh` and `.github/workflows/release.yml` |
| INV-1, INV-3, INV-6, INV-7, INV-8 — the five source-level guards | `tests/i18n-check.py`, a new suite |
| INV-9 — an application object on both headless paths | `tests/gui-smoke.py`, replacing `ONEUP-0077`'s INV-5 case |

**`tests/i18n-check.py` is a new suite and must be named in both places or it runs
nowhere** — `local-CI.sh` and `.github/workflows/release.yml` each name every Python suite
by hand (`docs/standards/files-and-naming.md` §2.2).

**Only the checks that need the Qt tools skip without them — never the suite.** Four of the
five checks in `tests/i18n-check.py` are source greps needing no Qt at all, so a suite-wide
exit `77` would silently disable INV-1, INV-3, INV-6 and INV-7 on any machine missing
`pyside6-lupdate`, and report a skip rather than a failure. The suite runs its four grep
checks always, skips the catalogue build (INV-8) when the tools are absent, and returns `0`
with the skip named in its output. `tests/gui-smoke.py` does the same for INV-2 and INV-4,
which need `pyside6-lrelease` to synthesise a catalogue: those two checks skip, the rest of
the suite runs, and its existing exit `77` keeps its one meaning — PySide6 is absent.

**Three limits, stated rather than left to be discovered.** The right-to-left pass runs the whole
window mirrored, but the only *painted* geometry it can judge is `ToggleSwitch`'s, through
the pixel sample the suite already takes — and **that sample judges nothing until §8's change
to it lands**, because `shape_pixels` picks its sampled third from `checked` alone
(*"Knob sits right when on, so inspect the LEFT third"*), so a correctly mirrored switch puts
the state shape in the third it does not look at. A widget hand-painted after this item ships needs
its own check written with it — `ui-and-accessibility.md` §8.3 states the rule, and its
**What checks this** row is what has to change from `nothing` to that widget's check.
INV-7's check reads the argument
at the call site, so a sentence assembled into a variable and passed in is invisible to it —
the wrapping half of gate **G10** stays a review against
`wording-and-translation.md`, which design §7 already calls the weakest gate in the set. And
INV-8 proves the catalogue *builds*, not that it is current: `pyside6-lupdate` records
source line numbers, so a freshness gate would fail on every unrelated edit.

**The second GUI pass is a second process, not a second function.** A `QApplication` exists
once per process and `-reverse` is read at construction, so the suite is run twice from the
outside. That doubles everything the suite already does per run — which used to include the
live `api.github.com` requests `docs/standards/testing.md` §2.3 recorded as a defect, and
was the argument for landing ONEUP-0067 before this item. **That argument is discharged:**
ONEUP-0090 fixed it, the suite stubs `_check_app_update` before its first window, and
doubling a run now doubles no network traffic. What doubles is the run's wall-clock cost
and its teardown noise, and this item owns both.

## 8. Docs & release

This item lands on `v2` with the rest of 2.0. Its documentation edits are ordinary
documentation and go to `main` under `docs/standards/workflow.md` §9 — it is **ONEUP-0072**
that carries §9's marker-change exception, because a marker change binds its reference edit
to the same commit as 2.0-only code.

- **`local-CI.sh` and `.github/workflows/release.yml`** — both name `tests/i18n-check.py`,
  and both gain the second, `-reverse` run of `tests/gui-smoke.py`. A suite named in neither
  runs nowhere (`docs/standards/files-and-naming.md` §2.2), and six of the nine invariants
  here are carried by those two additions — INV-1, INV-3, INV-6, INV-7 and INV-8 by the new
  suite, INV-5 by the second run. INV-2, INV-4 and INV-9 ride the ordinary
  `tests/gui-smoke.py` pass.
- **`oneup/gui/app.py` and `tests/gui-smoke.py`** — both construct their `QApplication` with
  `sys.argv`, or the `-reverse` run is silently left-to-right (§4.2). `app.py`'s two headless
  entry points also gain the `QCoreApplication` the catalogues install onto (§4.2), and
  `tests/gui-smoke.py` **loses ONEUP-0077's INV-5 case in the same commit** — its subprocess
  assertion is that no Qt application is constructed on either headless path, which is
  exactly what §4.2 now adds, so leaving it turns the suite red. **`shape_pixels` also picks
  its sampled third from `QApplication.isRightToLeft()` rather than from `checked` alone** —
  §4.4 moves the state shape to the other end, and the existing sample would either go red
  on a correct mirror or pass without having looked at the shape (§7).
- **`docs/standards/wording-and-translation.md`** — its **What checks this** table gains a
  real catcher for §7, which INV-8 supplies. **§6.1's row does not become a guard**: INV-7
  catches a literal, an f-string and a `+` at the listed call sites and nothing assembled
  through a variable, so that row gains a *partial* catcher and keeps the review beside it —
  `oneup-2.0.md` §7 still calls the wrapping half of **G10** the weakest gate in the set, and
  §7 above says why.
- **`docs/standards/ui-and-accessibility.md`** — §8.1's known `text-align` site and §8.3's
  two handed sites are resolved. §8.1's and §8.2's **What checks this** rows become guards
  rather than outstanding work; §8.3's row goes from `nothing` to the RTL pass's pixel
  sample **for `ToggleSwitch` only**, and says so, because that is all it covers (§7).
- **`docs/standards/files-and-naming.md`** — `tests/i18n-check.py` joins the `tests/` row
  and the test-naming table. `oneup/translations/` is already in its §4 package tree.
- **`packaging/appimage/build-appimage.sh` and `packaging/rpm/oneup.spec`** — **neither
  changes for 2.0, and that is correct**: §10 ships no `.ts` for any language, git carries no
  empty directory, and the RPM installs named files rather than trees, so an install line
  over `oneup/translations/` would fail the build on a missing source. What both owe is
  stated here because the first contributed language is when it bites: that change ships
  OneUp's `.qm` under `%{_datadir}/oneup/` — the absolute form of the package-relative path
  §4.2 resolves — **and Qt's matching `qtbase_<lang>.qm`, or neither installs** (§4.2's pair
  rule). Nothing supplies Qt's today: the RPM requires `python3-pyside6` and no translations
  package, and the AppImage names no translation file at all.
- **`README.md`** — a short note that OneUp ships in English and how to contribute a
  language.
- **No version-site change** — none of `docs/standards/workflow.md` §5.1's six sites moves.
  This lands inside 2.0, not as a release of its own
  (`docs/standards/workflow.md` §5.1).

## 9. Alternatives considered (and rejected)

- **Set the layout direction from `QLocale.system().textDirection()` at startup.**
  Rejected on measurement: it clobbers `-reverse` (§2.2), which makes the only gate this
  item has prove nothing. Letting Qt derive the direction from the catalogues costs no code
  at all.
- **Ship a German catalogue as proof the machinery works.** Rejected: the user's decision is
  English only in 2.0 (§3), and a machine-translated catalogue nobody can review is worse
  than none. INV-8 proves the pipeline instead.
- **Use `gettext` rather than Qt's own machinery.** Rejected: Qt supplies the extraction,
  the editor, the plural rules and the direction derivation; a second system would duplicate
  all four and lose the last one.
- **A single `oneup/gui/translations.py` holding both the loading and the sentence tables.**
  Rejected: `markers.py` already owns turning a marker into English, and the loading has to
  run before any widget exists. Two responsibilities, two homes
  (`docs/standards/coding.md` §4.2).
- **Keep the payload conversion in this spec.** Rejected at the fifth review loop: the two
  are separate contracts, every finding in loops 4 and 5 sat on one side of the seam, and a
  document that needs more than three loops is oversized rather than well reviewed
  (`/cold-eyes`'s own budget). `ONEUP-0072` is the other half.

## 10. Out of scope

- **Any second language.** No `.ts` or `.qm` file for another language is written, reviewed
  or shipped in 2.0 (design §5.1). `oneup/translations/` has its slot in
  `files-and-naming.md` §4 already, but nothing is tracked in it until a real `.ts` lands.
- **Translating the engine's terminal output.** `./update_system.sh` run directly is a
  system tool's output and stays English (`wording-and-translation.md` §5).
- **The engine's marker payloads, and the notification its `--notify` raises.** ONEUP-0072.
- **Translating log files, diagnostics or the bug-report clipboard payload.** They are read
  by a developer.
- **Locale-aware number, date and byte formatting.** Worth doing, not this item; the sizes
  the engine reports are data (ONEUP-0072 §4.1).
- **Mirroring the tray icon** (§4.4).
- **Re-wording any message.** Wrapping a string is not a licence to rewrite it (§3.1).

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-27 | 3 lanes; 3 critical, 3 high, 9 medium, 3 low — **17 verified, 1 dismissed** | The three worst were each a claim the tree contradicts. `@@CHECK@@`'s `label` and `@@REPO_SKIPPED@@`'s `reason` were routed to codes when the window reads neither — the reference says so of the first outright — which would have put a bare token in front of the only reader they have. §4.4 and §4.5 gave two different wire shapes for `@@REBOOT@@`'s components. And the right-to-left gate was wired to the wrong `QApplication`: `tests/gui-smoke.py` builds its own with an empty argument list and never calls the application's `main`, so `-reverse` would have reached nothing and INV-8 would have passed while proving the opposite. Two fixes landed outside this spec: `ui-and-accessibility.md` §8.3 was wrong that `_paint_state_shape` computes from the left edge as the knob does — it picks its edge from the *state*, so the two handed sites need different fixes — and the ROADMAP bullet repeating it. Dismissed: that §4.2 misattributes the no-`setLayoutDirection` rule to §8.4; the sentence says §8.4 owns the *reading* half and this is the writing half, which is what it says. |
| 2 | 2026-07-27 | 3 lanes; 3 high, 5 medium, 4 low — **10 verified, 2 dismissed** | The gap worth the loop was one the marker protocol could never have shown: `notify_send` raises a desktop notification, in English, on the two timer paths — the only paths where no window is open — and it never travels as a marker, so none of §4.4's routes touched it. The timers now stop passing `--notify` and the window builds the sentence (INV-13). Two of loop 1's own fixes had defects: INV-2's `^[a-z0-9-]+$` could not match the space-separated field the same loop gave `@@REBOOT@@`, and §8's "§4.1 (including its four-field guard, §4.4)" reads as `marker-protocol.md` §4.4, which is `REFRESH` and unrelated. `oneup-2.0.md` §4 assigns this item a release-note sentence — the Bash fallback stops being a drop-in — that §8 was not carrying. Dismissed: that §4.2 does not describe a mechanism for "pair or neither" and §4.4 does not state the new guard value; both sentences already say it, and answering a finding with more prose is what makes the next loop cost more. |
| 3 | 2026-07-27 | 3 lanes, two accepted clean; 1 critical, 2 high, 1 medium, 4 low — **5 verified, 3 dismissed** | The critical was a rule this spec invokes and cannot satisfy: `marker-protocol.md` §5 puts the reference edit in the same commit as the four code files, `workflow.md` §9 sends all documentation to `main`, and those code files are 2.0-only — so the tree as written offered a choice between breaking the same-commit rule and breaking the freeze. Fixed in `workflow.md` §9, where it belongs, along with the two places §2 and §11 restate the branch rule; the answer is that the reference goes to `v2`, because a reference amended on `main` would describe a contract `main`'s own 1.4.0 engine does not implement. Loop 2's own fix stranded a sibling again: INV-2 gained "space-separated as `@@REBOOT@@` and `@@SERVICES@@` do", but `SERVICES` carries unit names, which §4.4 routes to data. And §1 promised a gate for "a widget that only works in English" that only exists for the one painted widget the suite already samples. Dismissed: that §6 has no row for five invariants (they are source-level guards with no runtime failure mode), that §2.1's `grep -c` result is a raw count (`documentation.md` §6b's permitted form is exactly a command plus a past-tense measurement), and that §8 cites the wrong section for the same-commit rule (§5 is where it is written). |
| 4 | 2026-07-27 | 3 lanes, two accepted clean; 3 medium, 3 low, 1 info — **6 verified, 1 dismissed** | Nothing found was a wrong claim; every finding was the document not saying enough, and all in one section. `@@CHECK_UNKNOWN@@`'s `reason` is three engine sentences, not one, and one of them interpolates a comma-joined alias list — so it is three codes and a list argument, which §4.4 had not worked out. `@@REBOOT@@`'s components and that same alias list both render a *variable number* of things into a sentence, which §4.6's "code plus parameter names" table shape cannot express; those two entries carry a render function, and the agreement goes through the plural form rather than English's. `@@STEP_BEGIN@@`'s and `@@STEP_END@@`'s new field shapes are now written out rather than inferable. Dismissed: that §4.4's pointer to §4.5 for the space-separated format is misdirected — §4.5 states that rule. |
| 5 | 2026-07-27 | 2 lanes; 1 critical, 2 high, 3 medium, 2 low — **6 verified, 2 dismissed** | Every finding was in the payload half, and the critical was loop 2's own fix landing in a place that cannot run it: the notification moved to the window, but `main` dispatches `--check` and `--update` and exits *before* any `QApplication` exists — and with no application object `installTranslator` refuses outright, measured and now in §2.3. Those two paths build a `QCoreApplication`, which needs no display. `@@HINT@@` turned out to have three readers outside `handle_marker` — two `QMessageBox`es and the log — each doing `line.split("|", 1)[1]`, so a bare `auth-write-failed` would have been shown to a user in a message box. And §2.2's worked example, the evidence the whole conversion rests on, was wrong: `_step_badge` already matches `"nothing"`, so the sentence chosen to demonstrate a silent badge change would not have changed it. Three siblings fixed in the same pass: §2.3's "four probes" over five rows, §4.1's single entry point, INV-4's test scope. Dismissed: two requests for field layouts §4.4 and §4.5 already give. |
| 6 | 2026-07-27 | **the split** — no new review; the loops above are why | Loop 5 was the fifth in a row to find something substantive, which `/cold-eyes` treats as evidence that the document is oversized rather than that the review is thorough. Every finding in loops 4 and 5 sat on one side of a clean seam, so the payload conversion left for `docs/specs/ONEUP-0072-marker-codes.md` and this spec kept the machinery and right-to-left. The rows above describe the combined document and use **its** section and invariant numbers, which no longer match either half — they are left exactly as written, because a loop log rewritten after the fact stops being evidence. The eight invariants here were renumbered in the split; nothing cited them, and five gaps in a never-accepted spec would cost a reader more than the renumber does. |
| 7 | 2026-07-31 | 2 lanes, both escalated; 5 high, 7 medium, 9 low, 1 info — **20 verified, 2 dismissed** | The first review of the split document, and most of what it found was the split's own unswept blast radius. Both lanes independently led with the same gap: §4.2 governed *how* the pair loads and never said **which language** — no locale source, no fallback rule — and never said how OneUp's own catalogue directory resolves, so `load()` could not be written at all. Sixteen sites in seven documents still named ONEUP-0032 as the owner of the `HINT`/`REMEDY` payload conversion the split moved to ONEUP-0072, including `marker-protocol.md` §5.1 and §5.2 and `workflow.md` §9's same-commit exception — a reference that outranks this spec telling an implementer the wrong item owns the contract change. Three findings were settled by running the thing rather than reading it: `QT_TRANSLATE_NOOP3` returns **only** the source string, so a table built from it silently loses the disambiguation half of its own lookup key; `-reverse` does set right-to-left with no catalogue installed, which is the case the gate actually runs in and was nowhere measured; and Qt leaves `sys.argv` unmutated, which §4.2 asserted without a measurement. INV-7's list was closed and omitted `QMessageBox` — 23 call sites in the 1.x window — and `QSystemTrayIcon.showMessage`, which `wording-and-translation.md` §6.1 requires wrapped. §7 exited `77` for the whole suite when the Qt tools were absent, which would have silently disabled the four grep guards that need no Qt. Dismissed: that `wording-and-translation.md` §7 gives two catalogue homes — the RPM installs the app to `%{_datadir}/oneup/`, so the absolute and package-relative paths name the same directory; and that a `Draft` status after six loops is itself a finding. |
| 8 | 2026-08-19 | 2 lanes, first loop of a fresh run — the first read of this document since the ONEUP-0101 split reshaped its siblings; Q1 2 · Q2 3 · Q3 1 · Q4 2, 8 verified, 1 dismissed (no severity scale under the four-question gate, so nothing here for §7's tally check to balance; ONEUP-0100) | **Both lanes independently led with the same defect, and it is a one-word path error that would have installed nothing.** §4.2 resolved OneUp's catalogue "through the `translations/` directory **beside** the `oneup` package" — while §8, §10, `files-and-naming.md` §4 ("sits inside the package") and `wording-and-translation.md` §7 ("inside the one package directory") all say *inside*. An implementer writes `Path(oneup.__file__).parent.parent`, `load()` misses on every installed copy, and §4.2's pair rule then keeps the app English forever. **The catalogue-build invariant was wrong twice over, and running it is what settled both.** `pyside6-lupdate oneup/ -ts …` reports `Found 0 source text(s)` — with or without `-recursive`, and for `oneup/gui/` too; only a file list extracts anything, so INV-8's prescribed command extracted nothing. And `pyside6-lrelease` drops every unfinished message, so a freshly extracted catalogue compiles to a **33-byte `.qm` carrying zero translations** — which satisfies "produces a non-empty catalogue" while proving nothing. Both measured on PySide6 6.11, and the repaired criterion was measured too: a finished translation round-trips to `'ÜBERSETZT'` through `QCoreApplication.translate`. That second measurement also killed INV-2, which built its fixture "the way INV-8's check does" and then asked INV-4 to assert a *translated* string still translates — impossible on a catalogue with no translations. It compiles a hand-written `.ts` now, which as a side effect makes §7's skip guard (naming `pyside6-lrelease` alone) correct again. **INV-2's other half could not run at all**: exercising "one present" and "neither" needs a synthetic `qtbase_<lang>.qm` at `QLibraryInfo.path(TranslationsPath)`, measured here as `…/site-packages/PySide6/Qt/translations` — outside the suite's redirected `HOME` (`tests/gui-smoke.py:30`), so the test as written breaches `testing.md` §2.3 or invents a loader override nothing named. §4.2's loading function now takes both directories as arguments. **The Q3 was the pair rule's unowned half:** §8 obliges both packaging paths to ship `oneup/translations/` and neither mentions Qt's `qtbase_<lang>.qm`, which the pair rule makes equally load-bearing — `grep -rn translation packaging/` returns nothing, and the AppImage is PyInstaller over a venv. So a contributor's German catalogue could never load, against §1. **Two smaller ones.** §4.2 says this item retires ONEUP-0077's INV-5, and §8's checklist — the place an implementer works from — never said its subprocess assertion is deleted, so the suite ships red. And §4.3 credited `wording-and-translation.md` §6.2 with a `+`-concatenation sweep it does not have (its **What checks this** row reads `nothing automatic`; the only sweep in the tree is `oneup-2.0.md` §5.1's, over `updater.py`, and that section calls it a measurement rather than a gate) — which mattered because INV-7's check listed a literal and an f-string and **not** `+`, so nothing anywhere would have caught the concatenation §6.2 forbids. Both now named. **Dismissed:** §7's "the live `api.github.com` requests `testing.md` §2.3 recorded as a defect" — §2.3 does record them and the harm, and reserves the word *defect* for the engine suite's un-redirected `HOME`; loose, and it changes no line anyone writes. **Filed, not fixed:** `wording-and-translation.md` §7's Extract row carries the same `pyside6-lupdate` over-a-directory command, and correcting a standard changes what a conformer runs, so it owes its own gate rather than a passing edit. **Four lane open questions resolved clean and are recorded so no later loop re-asks them:** `QT_TRANSLATE_NOOP3` does return only `'Lock'` (§4.3's measurement holds); `tests/gui-smoke.py` parses no `argv` of its own, so `-reverse` reaches Qt cleanly; ONEUP-0108 §8 does put its tables in ONEUP-0072's landing commit, as §4.1 claims; and a synthesised catalogue cannot bleed into the `-reverse` pass, because §7 makes that a separate process. |
| 9 | 2026-08-19 | 2 lanes, the document's second loop and the first spent on loop 8's own fixes; Q1 1 · Q2 3 · Q3 1 · Q4 1, 6 verified, 1 dismissed (no severity scale under the four-question gate, so nothing here for §7's tally check to balance; ONEUP-0100) | **The best finding is a test that would have gone red on a correct implementation, and it is one eight loops walked past.** §7 leans the whole right-to-left gate on "the pixel sample the suite already takes" — and `tests/gui-smoke.py`'s `shape_pixels` picks its sampled third from `checked` alone, commented *"Knob sits right when on, so inspect the LEFT third"*. §4.4 moves the state shape to the other end, so after a correct mirror the sample looks at the third the shape is no longer in: red on a right implementation, or green having judged nothing. §8's file list named the `sys.argv` change and nothing else, so an implementer was told to wire a second run around a sample that cannot survive it. §7 and §8 now both say the third comes from `QApplication.isRightToLeft()`. **Three of the six landed on text loop 8 wrote**, which is 4a-min's pattern and the honest character of this loop. Loop 8's packaging bullet required both paths to ship `oneup/translations/` **and** Qt's `qtbase_<lang>.qm` — while §10 ships no `.ts` at all in 2.0, git carries no empty directory, and the RPM installs named files (`install -Dm0644 updater.py …`), so the instruction was an install line over a path that does not exist. Both lanes found it, from opposite ends. It now says neither packager changes for 2.0 and states what the first contributed language owes, including Qt's half — verified as unmet today: the RPM requires `python3-pyside6` and no translations package, and the AppImage names no translation file. Loop 8's INV-2 rewrite said "one present" of two materially different cases, and only the `qtbase`-alone one can falsify the rule it sits under; both lanes found that too, and it is four loads now with the cases named. **The Q1's sibling was loop 8's other half.** §4.2 retires `ONEUP-0077`'s INV-5 and §8 deletes its case, and nothing replaced it: no invariant asserted the headless paths build a `QCoreApplication`, leaving §2.2's third measured bug — *"a timer path with no application object silently renders English"* — covered by nothing. **INV-9** now asserts it, on INV-5's own subprocess harness inverted; §7 and §8's count moved with it. **Two pre-existing Q2s.** §8 claimed `wording-and-translation.md`'s **What checks this** gains "real catchers for §6.1 and §7" — but §7 above and `oneup-2.0.md` §7 both say the wrapping half of **G10** keeps its review, so §6.1's row gains a *partial* catcher and an implementer would otherwise have retired a gap the design still records. And INV-7's closed list was Qt-setter-shaped while §4.3's own motivating example is `self._announce(f"{row.title}: {badge}")` — a screen-reader call on no setter, so the document's example passed the check the same paragraph calls "the only thing that catches either". The list is now every call that hands a sentence to a user, naming the announcement and `ONEUP-0077`'s `notify-send` body. **Found while resolving a lane's open question and fixed as a finding:** INV-3 alone among the source-level guards stated no scope, and a `setLayoutDirection` in the suite defeats `-reverse` exactly as one in the application does — measured both ways here: with `-reverse` `isRightToLeft()` is `True`, `setLayoutDirection(LeftToRight)` makes it `False`, and `setLayoutDirection(RightToLeft)` makes it `True` with no `-reverse` at all, so INV-5 can be defeated or passed vacuously from test code. The check reads `tests/` as well as `oneup/`. **Dismissed:** that INV-8 does not say where its check writes its `.ts` and `.qm` — `testing.md` §2.3 already binds every test here and §4.2 cites it, so no line changes. **Three lane open questions resolved clean:** `qproperty-alignment` is at **0** in `updater.py` and `text-align: left` is the only directional property left, so §4.4's "reach zero" holds; §4.3's two f-strings are two distinct sites (`self.status.setText(f"{label}…")` at one, `_announce` at the other), not one described twice; and `ONEUP-0077` notifies through `notify-send` rather than `QSystemTrayIcon.showMessage`, which is why INV-7 now names the body rather than relying on the tray entry. |
