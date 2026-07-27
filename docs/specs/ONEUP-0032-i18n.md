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
engine stops sending English at all, and the window is proven to mirror for Hebrew and
Arabic by a test rather than by hope.

**Two documents already own most of this and are not re-argued here.**
`docs/standards/wording-and-translation.md` §5–§7 owns where wording lives, how a
translatable string is written and the catalogue workflow.
`docs/standards/ui-and-accessibility.md` §8 owns the four right-to-left rules. What this
spec adds is the part they leave to this item: the mechanism that loads a catalogue, the
conversion of the engine's payloads to codes — **which is wider than the marker reference
currently reserves, and §3 says why** — and the tests that make the groundwork provable
while no second language exists.

## 1. Goal

After this ships, a contributor who wants OneUp in German writes one file and compiles it;
no Python changes. The engine emits identifiers, so the half that runs as root carries no
locale machinery and its output no longer decides what the user reads. The window renders
every sentence itself, through Qt's translation layer, with plural forms and named
placeholders. And `tests/gui-smoke.py` runs a second time with the layout direction forced
right-to-left, so a widget that hard-codes a side is caught by a gate rather than by a
Hebrew user — with one honest limit, in §7: a *newly hand-painted* widget still needs
somebody to write its own check.

## 2. Background

### 2.1 There is nothing to build on

Measured at `36599ea`: `grep -c 'self\.tr(\|QCoreApplication\.translate' updater.py`
returns **0**. No catalogue exists, no `QTranslator` is constructed, and no code reads the
layout direction. `docs/standards/wording-and-translation.md`'s own **What checks this**
table records the consequence — its §6.1 and §7 rows both say nothing checks them, because
there is nothing yet to check.

The starting position for right-to-left is good and was surveyed before this spec:
`ui-and-accessibility.md` §8 holds the survey and names the sites that will not mirror.
§4.7 is what this item does about them.

### 2.2 The window already re-words the engine's English, by sniffing it

This is the evidence that decides §4.4, and it is not a translation argument.

`Updater._step_badge` takes `@@STEP_END@@`'s `status` and `detail` and returns its **own**
badge. It does so by matching English substrings against the engine's sentence — testing
`detail` for `"up to date"`, `"already"`, `"nothing"`, `"remov"`, `"applied"`, `"updated"`
— and by pulling the number back out with `re.search(r"\d+", detail)`.

So the engine composes an English phrase, sends it, and the window takes it apart again to
recover the two facts it wanted: which outcome, and how many. Every one of those substrings
is a coupling nothing tests. Change `end_step system ok "already up to date"` to *"nothing
to update"* and the badge silently becomes `Done`.

The same shape appears at `@@STEP_BEGIN@@`: the engine sends a `label`, the window shows it
verbatim in the status line — while already holding its own title for that step in `TASKS`.
Two owners for one piece of wording.

### 2.3 What Qt does, measured rather than assumed

Four probes against PySide6 6.11 / Qt 6.11, each run on 2026-07-27. They decide §4.2, and
three of the four contradict what the mechanism is usually assumed to be.

| Question | Measured answer |
| --- | --- |
| Does the system locale set the layout direction? | **No.** With `LC_ALL=he_IL.UTF-8` and no catalogue, `QApplication.isRightToLeft()` is `False` |
| What does set it? | An installed `QTranslator`. Loading `/usr/share/qt6/translations/qtbase_he.qm` and installing it flips `isRightToLeft()` to `True` on its own |
| Does `-reverse` survive? | Yes through an installed left-to-right catalogue — but an explicit `setLayoutDirection()` call **clobbers it** |
| Does an uninstalled reference matter? | Yes. A `QTranslator` created inside a function and installed without keeping a reference is garbage-collected, and the application silently reverts |

The last two are the ones that would have shipped as bugs. A window that sets its own
direction at startup makes the `-reverse` test pass while proving nothing; a translator
nobody holds turns the whole feature off after the first collection.

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
| This item is **last** in 2.0, and starts only after the engine rewrite has passed its gate | inherited, not chosen here — design §5.2, `docs/reference/marker-protocol.md` §5.1 |

**One decision this spec takes, because the evidence forces it.**
`docs/reference/marker-protocol.md` §5.1 reserves this item for the `HINT` and `REMEDY`
payloads. That is too narrow to meet the gate it is meant to meet: design §7's **G10** is
*"every user-facing string is translatable"*, and converting only those two would leave
every task badge, every unreadable-source warning and every reboot reason in English on a
Hebrew desktop. §2.2 shows one of those fields is already being re-worded by the window
through English substring matching, so the conversion is owed for correctness even if no
second language ever ships.

So this spec converts **every payload the window renders as words** (§4.4), and
`marker-protocol.md` §5.1 and §5.2 are amended in the same commit — which is what that
document's own §5 requires of any contract change. It remains one deliberate, versioned
change, taken once, after the rewrite is proven.

### 3.1 What this spec does not decide

- **How a sentence is worded.** `wording-and-translation.md` §2–§4 owns that, and the
  conversion is not a licence to rewrite messages; each code's English is the sentence the
  engine sends today unless §2's rules were already being broken.
- **Which languages ship.** None, in 2.0 (design §5.1). §10.
- **How the interface is laid out.** ONEUP-0064 lands first and its layout is what gets
  mirrored.

## 4. Design

### 4.1 Where the machinery lives

Three placements, and two of them are existing modules rather than new ones
(`docs/standards/coding.md` §4.2 — split by responsibility, and only when there is one).

| Module | Gains |
| --- | --- |
| `oneup/gui/i18n.py` *(new)* | loading the catalogues, and holding them for the process's lifetime |
| `oneup/gui/markers.py` | the code→sentence tables, and the rendering of a code into a sentence |
| `oneup/gui/steps.py` | the in-progress phrasing for each step, which the engine stops sending |

`oneup/gui/markers.py` is where these belong rather than in a new module: ONEUP-0034 §4.2
already gives it *"reading what the engine said, and saying it in English"*, and
`_step_badge` — the function §2.2 is about — is already its own. This replaces its English
substring matching with a lookup; it does not add a layer beside it.

`oneup/gui/i18n.py` is separate because it is the one thing that must happen **before any
translatable string is evaluated**, which in practice means before the first widget is
constructed. `oneup/gui/app.py`'s `main` calls it as its first action after building the
`QApplication`.

### 4.2 Loading a catalogue

Four rules, each one of §2.3's measurements turned into code.

**Two catalogues, loaded as a pair or not at all.** OneUp's own `oneup_<lang>.qm` and Qt's
`qtbase_<lang>.qm` — the latter found through `QLibraryInfo.path(TranslationsPath)`, never
a hard-coded path. If either fails to load, neither is installed and the application stays
English. This is what stops the worst intermediate state: Qt's base catalogue alone flips
the layout to right-to-left, so loading it without ours would mirror a window still full of
English text.

**The application never calls `setLayoutDirection`.** Qt derives the direction from the
installed catalogues, and an explicit call overrides `-reverse` (§2.3) — which would make
the gate in §7 pass while testing nothing. `ui-and-accessibility.md` §8.4 already forbids
*reading* the direction from anywhere but the application; this is the writing half.

**The translators are held for the process's lifetime** — module-level in
`oneup/gui/i18n.py`, not local to the loading function. §2.3 measured what happens
otherwise.

**Every `QApplication` is constructed with `sys.argv` — and there are two.** `main` in
`updater.py` passes `QApplication([])` today, so Qt sees no arguments and `-reverse` cannot
reach it. **`tests/gui-smoke.py` builds its own** — `QApplication.instance() or
QApplication([])` — and never calls the application's `main`, so changing only the
application would leave the gate in §7 running left-to-right while reporting a pass. Both
call sites change. Qt consumes only its own options and leaves Python's `sys.argv` alone, so
the existing `"--tray" not in argv` and `"--check" in sys.argv[1:]` membership tests are
unaffected.

**A missing catalogue is not an error** (`wording-and-translation.md` §7). In 2.0 it is the
*normal* case: no `.ts` file for any language is written, so `load()` returns `False` on
every desktop and the application runs in English, which is correct.

### 4.3 Wrapping the window's strings

`wording-and-translation.md` §6 is the rule and is not restated. Three things this item adds
to it, each because the tree makes them necessary:

- **A table of sentences outside a class uses `QT_TRANSLATE_NOOP`**, with the lookup calling
  `QCoreApplication.translate` at render time — verified extractable in §2.3. `self.tr()`
  is unavailable at module level, and marking at definition while translating at render is
  what lets the language change without rebuilding the table. An entry needing
  `wording-and-translation.md` §6.4's disambiguation comment takes `QT_TRANSLATE_NOOP3`,
  which is the only one of the two forms with a slot for it.
- **A sentence built by an f-string is a concatenation**, and INV-10's check is what catches
  it. `wording-and-translation.md` §6.2's own sweep — `grep -cE '"\s*\+|\+\s*"' oneup/` —
  does not see f-strings at all; `handle_marker` builds both `f"{row.title}: {badge}"` (the
  sentence it passes to `_announce`) and the status line's `f"{label}…"`, and neither is
  reachable by a translator.
- **Accessible names and descriptions are wrapped too.** They are read aloud, so they are
  user-facing in the most literal sense (`ui-and-accessibility.md` §2).

### 4.4 The engine's payloads: three fates

Every field takes exactly one of three routes, decided by what the window does with it. The
rule is what matters; the field lists below are the application of it, checked one by one
against `docs/reference/marker-protocol.md` §3's table, which is the authority on which
fields exist.

**1 — The window already knows it, so the field is retired.**
`@@STEP_BEGIN@@`'s trailing `label`. The window holds a title for every step key in
`TASKS`; it gains the in-progress phrasing beside it (§4.1) and looks both up by `key`. The
engine keeps its own `LABEL` map for the terminal output a user sees when running
`./update_system.sh` directly, which stays English by design (`wording-and-translation.md`
§5).

This one is **not** free, and the reason is worth stating: `STEP_BEGIN` is one of the three
markers with an explicit fixed-shape guard (`marker-protocol.md` §4.1), and both the
reference and the window's parser floor it at four fields. The marker becomes
`key|index|total`, so the floor moves to three in the same commit — otherwise every
well-formed `STEP_BEGIN` is silently ignored and the run appears to freeze while it is in
fact updating. Nothing is lost in the terminal: `begin_step` already prints the label on its
own line before emitting the marker.

**2 — The window renders it as words, so it becomes a code.** `@@HINT@@`'s sentence;
`@@REMEDY@@`'s action; `@@STEP_END@@`'s `detail`; `@@CHECK_UNKNOWN@@`'s `reason`;
`@@REBOOT@@`'s optional `reason`. `REMEDY` is the one already halfway there —
`import-keys` and `skip-repo` are codes today and only need the rule written down.

`@@STEP_END@@`'s `detail` carries a number today, and `_step_badge` recovers it with a
regular expression (§2.2). Under codes the number is an **argument** in its own trailing
field — `key|status|code|count` — so the window renders it through the plural form
(`wording-and-translation.md` §6.3), which is also how the badge stops saying `package(s)`
in English.

`@@CHECK_UNKNOWN@@`'s `reason` is three sentences in the engine, not one, and each becomes
its own code: sources that could not be read (the aliases follow as one space-separated
argument, replacing today's comma joining), zypper exiting with a code nobody can act on
(the exit status is the argument), and the Flatpak remotes that could not be reached. The
window joins a list of aliases the way the language joins lists, which is the point of
sending them as data.

`@@REBOOT@@`'s reason is the interesting one. `reboot_reason_from_log` composes a phrase
today — joining up to three components and agreeing the verb — which no other language
assembles the same way. Under codes it emits the **components**, and the window builds the
sentence, so the joining and the agreement happen where the language is known. They are
several values of one kind, so they share one space-separated field like `@@SERVICES@@`
does (§4.5). ONEUP-0054 §4.2 places that composition in `parsers.py`; this item changes what
it composes, from a phrase to a list.

**3 — It is data, an already-fixed token, or the window never renders it, so it does not
change.** Step keys, repository aliases, package names, counts, byte sizes, mount points,
snapshot ids and dates, and a Btrfs snapshot's own description are data. `STEP_END`'s
`status`, `PROGRESS`'s `phase` and `INSTALLED`'s two `yes`/`no` flags are already tokens the
window branches on rather than reads out; the English *it* chooses from them is wrapped
under §4.3 like any other window string. A translator must never see any of these, and a
code would be a lie about what they are.

**Two fields carry English prose and still belong here**, which is the case worth naming
because it looks like an oversight: `@@CHECK@@`'s `label` and `@@REPO_SKIPPED@@`'s `reason`.
Neither is read by the window at all — `handle_marker` takes `key` and `count` from the
first and only the `alias` from the second, building its own wording in both cases, and
`marker-protocol.md` §4.6 says so outright of the `label`. They are the engine's terminal
output, which stays English (`wording-and-translation.md` §5). Converting them would put a
bare token in front of the one reader they have.

**And one user-facing sentence never travels as a marker at all.** `notify_send` raises a
desktop notification — *"Updates available"*, *"Update complete"*, *"Already up to date"* —
and the paths that reach it are the two systemd user timers, which run `updater.py --check`
and `--update`. Both shell straight through to the engine with `--notify`, so today the
English is the engine's and no window is involved. That is a user-facing string outside every
route above, and leaving it there would make §1's goal false for exactly the user who never
opens the window.

**The timers stop passing `--notify`, and the window sends the notification.** It already
launches the engine on those paths; it reads the run's `@@CHECK@@`, `@@STEP_END@@` and
`@@DONE@@` markers to build the sentence, through the same tables as everything else. The
engine keeps its `--notify` flag for somebody running `./update_system.sh` in a terminal,
where the notification is part of its own English output (§10).

### 4.5 The shape of a code, and its arguments

`marker-protocol.md` §5.2 reserved three questions for this spec. These are the answers.

**A code is `^[a-z0-9-]+$`** — lowercase ASCII, hyphen-separated, no spaces and no `|`. It
names the situation, not the sentence: `repo-key-expired`, not `import-the-key`. The
constraint is not cosmetic — the protocol has no escaping (`marker-protocol.md` §1.1), and a
code that can never contain `|` or a space can never shift a field.

**Arguments are data and travel in trailing fields.** A hint that names a repository sends
`HINT|repo-slow|packman`, and the window's entry for `repo-slow` declares the parameter
names in order, so the sentence uses named placeholders a translator can reorder
(`wording-and-translation.md` §6.2). Where several values of one kind travel together they
share one field, space-separated, as `@@SERVICES@@` already does.

**No argument is ever prose.** Where the engine interpolates an English fragment today it
gains a distinct code instead — the download-size failure, which selects one of four
sentences by zypper's exit code and interpolates it into a fifth, becomes four codes. This
is the rule that keeps English out of the privileged half rather than merely moving it into
a field.

**Free text still applies §1.1's substitution.** One argument is outside the engine's
control — the lock holder's process name, read from `/proc/<pid>/comm` — so the marker
emitter rewrites `|` to `/` in every argument, exactly as `SNAPSHOT_ITEM` already does for a
snapshot description. `oneup/engine/markers.py` is one place, so it is one guard.

**Allocating one.** A code is added in the same commit as the engine branch that emits it
and the window entry that renders it; the two are never separated. Once shipped, a code is
never reused for a different meaning — the same discipline as a roadmap id
(`docs/standards/workflow.md` §4). Retiring one means the window keeps rendering it for as
long as an older engine could still be installed.

### 4.6 Where the wording lives, and what an unknown code shows

The tables live in `oneup/gui/markers.py`, one per marker family, each entry pairing the
code with its `QT_TRANSLATE_NOOP`-marked English and its parameter names.

**Two entries are not a template with placeholders, and the table has to admit it.**
`@@REBOOT@@`'s reason and `@@CHECK_UNKNOWN@@`'s alias list both render a *variable number*
of things into one sentence — which in English means a comma-and-`and` join and a `was`/
`were` agreement, and in another language means whatever that language does. So those
entries carry a small render function rather than a format string, and the sentence around
the join goes through the plural form (`wording-and-translation.md` §6.3) so the agreement
is the catalogue's to decide rather than English's.

**A code with no entry renders a readable sentence, never the raw token and never an empty
banner** (`marker-protocol.md` §5.2). It says that this version of OneUp has no wording for
what the run reported, names the code so a bug report can quote it, and points at the log —
which is the only honest thing it can say. It is a bug in the window, not in the run, and
the run's own verdict is unaffected.

This matters more than it looks: a user on a packaged OneUp can have a newer engine than
window, and the failure mode of the naive version is a blank warning banner on a run that
actually failed.

### 4.7 Right-to-left: the three things Qt will not do

Qt mirrors every layout built from its own containers once the direction is set, and does
nothing else. `ui-and-accessibility.md` §8 owns the four rules; the work this item does
under them is:

- **`ToggleSwitch` applies the direction itself, at both handed sites, and they are handed
  differently.** §8.3 names them: the knob is unconditionally left-anchored, while
  `_paint_state_shape` picks its edge from the state, so the two need different fixes rather
  than the same one twice. Fixing only the knob is worse than fixing neither — the state
  shape is §3's colour-blind cue, so a half fix breaks the cue in Arabic while looking right
  in English. Both read `QApplication.isRightToLeft()`, never the widget's own
  `layoutDirection()` (§8.4).
- **`QPushButton#LinkBtn`'s `text-align: left` goes** (§8.1). The progress bar's
  `text-align: center` stays: centre has no handedness.
- **Nothing else acquires a directional property or a fixed `AlignLeft`/`AlignRight`.**
  Both are at zero and the check in §7 is a guard against growth, not a clean-up.

The tray icon is painted by hand too and is deliberately untouched — it is an icon in a
system tray, not a widget in a mirrored layout (§8.3).

## 5. Correctness invariants

- **INV-1** Nothing under `oneup/engine/` imports or calls translation machinery —
  `QTranslator`, `QCoreApplication.translate`, `tr`, `gettext`. The privileged half has no
  locale.
  *Test:* `tests/i18n-check.py`, the engine-purity check.
- **INV-2** Every code matches `^[a-z0-9-]+$`, and every payload field the window renders as
  words holds codes and nothing else — one code, or several space-separated, `@@REBOOT@@`
  being the only field that carries more than one. No field the window renders carries a
  sentence. (`@@SERVICES@@` is the space-separated *format* this borrows; its own contents
  are unit names, which are data — §4.4.)
  *Test:* `tests/run-tests.sh` splits each such field on spaces and asserts the shape of
  every element, on every `HINT`, `STEP_END` detail, `CHECK_UNKNOWN` reason, `REMEDY` action
  and `REBOOT` reason a scenario produces — the five families §4.4 routes to a code.
- **INV-3** No marker field contains a `|`: the emitter rewrites it to `/` in every
  argument before the line is printed.
  *Test:* `tests/run-tests.sh` — a lock-holder scenario whose process name contains a `|`
  produces a line the window's parser splits into the expected number of fields.
- **INV-4** A code the window has no entry for renders a non-empty sentence that is not the
  code alone.
  *Test:* `tests/gui-smoke.py` feeds an unknown code to the marker handler once for each of
  the five families §4.4 converts, and asserts the rendered text contains the code, contains
  a space, and is at least twice its length — the cheapest checkable proxy for "a sentence,
  not the token with something stuck to it".
- **INV-5** Both catalogues are installed, or neither is. A `qtbase` catalogue is never
  installed on its own, because it alone sets the layout direction. It guarantees nothing
  about how *complete* OneUp's catalogue is; a stale translation is a translator's problem,
  not a loading one.
  *Test:* `tests/gui-smoke.py` synthesises catalogues the way INV-11's check does and loads
  three times — both present, one present, neither — asserting installation only in the
  first.
- **INV-6** The application never calls `setLayoutDirection`, and no widget reads its own
  `layoutDirection()`; the direction is Qt's to derive and `QApplication.isRightToLeft()`'s
  to report (`ui-and-accessibility.md` §8.4). Writing it would override `-reverse` and make
  INV-8's pass vacuous.
  *Test:* `tests/i18n-check.py`, the direction check.
- **INV-7** An installed translator is referenced for the process's lifetime.
  *Test:* `tests/gui-smoke.py` asserts a translated string still translates after
  `gc.collect()`.
- **INV-8** The GUI suite passes with the layout direction forced right-to-left, **and
  asserts that it is right-to-left** before running its checks. A pass that silently ran
  left-to-right proves nothing.
  *Test:* `tests/gui-smoke.py -reverse`, run as a second pass by `local-CI.sh` and
  `.github/workflows/release.yml`; its first assertion is `QApplication.isRightToLeft()`.
- **INV-9** No directional stylesheet property and no hard-coded `AlignLeft`/`AlignRight`
  exists anywhere under `oneup/` (`ui-and-accessibility.md` §8.1, §8.2).
  *Test:* `tests/i18n-check.py`, the directional-property check.
- **INV-10** Every string passed to a text-setting call in `oneup/gui/` is wrapped —
  `setText`, `setToolTip`, `setWindowTitle`, `setAccessibleName`, `setAccessibleDescription`,
  `setPlaceholderText`, `addItem` — with no bare literal and no f-string.
  *Test:* `tests/i18n-check.py`, the wrapping check. It reads the call's argument, so it
  catches a literal and an f-string; it cannot follow a string through a variable, and §7
  says so.
- **INV-11** The catalogue extracts and compiles: `pyside6-lupdate` over `oneup/` followed by
  `pyside6-lrelease` succeeds and produces a non-empty catalogue.
  *Test:* `tests/i18n-check.py`, the catalogue-build check; skips cleanly when the Qt tools
  are absent.
- **INV-12** A shipped code is never reused for a different meaning.
  *Test:* **nothing automatic.** A rename is visible in review as a changed entry in
  `oneup/gui/markers.py` and a changed assertion in `tests/run-tests.sh`; a *reuse* is not
  distinguishable from a correct edit by any script. §7 records it.
- **INV-13** No user-facing sentence is composed by the engine. The desktop notification the
  two timers raise is built by the window, and neither timer passes `--notify`.
  *Test:* `tests/i18n-check.py`, the notification check — `--notify` appears in no argument
  list the window builds; `tests/gui-smoke.py` asserts the headless check paths produce the
  notification text themselves.

## 6. Failure modes

| When this breaks | What the user sees | Why it is survivable |
| --- | --- | --- |
| A catalogue file is missing or corrupt | English, laid out left to right | `load()` returns `False` and nothing is installed (INV-5); a missing catalogue is the normal case in 2.0 |
| The engine emits a code the window does not know | A readable sentence naming the code, and the log | INV-4. The run's verdict, badges and reboot advice are unaffected — only the explanation is |
| The window is newer than the engine | An engine payload the window still has an entry for | Entries are retired only when no supported engine emits them (§4.5) |
| A `\|` reaches a marker argument | Nothing — it arrives as `/` | INV-3, in one place in the emitter |
| A translator is garbage-collected | Silent reversion to English mid-run | INV-7 is the guard; §2.3 measured that it happens without one |
| Somebody adds a `setLayoutDirection` call | Nothing — and that is the danger: the right-to-left gate goes green while running left to right | INV-6 is the guard, and it exists because nothing else would notice. §2.3 measured that an explicit call beats `-reverse` |
| A new widget hard-codes a side in a stylesheet or an alignment flag | A control on the wrong side, in Arabic and Hebrew only | INV-9 catches it in the source, whatever the widget |
| A new widget hard-codes a side in its own `paintEvent` | The same, and **nothing catches it** | The RTL pass only samples the pixels of the one painted widget that exists today. §7 |
| A sentence is added without `tr()` | It stays English in every language | INV-10 catches it at the call site. A sentence assembled through a variable is not caught — §7 |
| The window fails to build the timer's notification | No notification from an unattended run; the update itself is unaffected | INV-13. The engine's `--notify` still exists and a user who wants the old behaviour can call it directly (§10) |

## 7. Tests

| What it locks in | Where |
| --- | --- |
| INV-2, INV-3 — payload shape and the `\|` guard | `tests/run-tests.sh`, per-scenario assertions on every marker carrying a code |
| INV-4, INV-5, INV-7 — unknown code, the catalogue pair, translator lifetime | `tests/gui-smoke.py`, new checks |
| INV-8 — the whole window under right-to-left | `tests/gui-smoke.py -reverse`, a second run wired into `local-CI.sh` and `.github/workflows/release.yml` |
| INV-1, INV-6, INV-9, INV-10, INV-11, INV-13 — the six source-level guards | `tests/i18n-check.py`, a new suite; INV-13's second half also in `tests/gui-smoke.py` |
| INV-12 — a code is never reused | **nothing.** Review only |

**`tests/i18n-check.py` is a new suite and must be named in both places or it runs
nowhere** — `local-CI.sh` and `.github/workflows/release.yml` each name every Python suite
by hand (`docs/standards/files-and-naming.md` §2.2). It exits `77` to skip when the Qt
translation tools are absent, matching how the GUI suite already skips without PySide6.

**Three limits, stated rather than left to be discovered.** The RTL pass runs the whole
window mirrored, but the only *painted* geometry it can judge is `ToggleSwitch`'s, through
the pixel sample the suite already takes. A widget hand-painted after this item ships needs
its own check written with it — `ui-and-accessibility.md` §8.3 states the rule, and its
**What checks this** row is what has to change from `nothing` to that widget's check.
INV-10's check reads the argument
at the call site, so a sentence assembled into a variable and passed in is invisible to it —
the wrapping half of gate **G10** stays a review against
`wording-and-translation.md`, which design §7 already calls the weakest gate in the set. And
INV-11 proves the catalogue *builds*, not that it is current: `pyside6-lupdate` records
source line numbers, so a freshness gate would fail on every unrelated edit.

**The second GUI pass is a second process, not a second function.** A `QApplication` exists
once per process and `-reverse` is read at construction, so the suite is run twice from the
outside. That doubles everything the suite already does per run — including the live
`api.github.com` requests `docs/standards/testing.md` §2.3 records as a defect
(ONEUP-0067). Fixing that is not this item's, but doubling it is this item's doing, and
that is the argument for landing ONEUP-0067 first.

## 8. Docs & release

**All of it lands on `v2`, documentation included**, which is the one case
`docs/standards/workflow.md` §9 sends to the branch rather than to `main`: the reference
edit is bound by `marker-protocol.md` §5 to the same commit as engine, window and both
suites, and those are 2.0-only. A reference amended on `main` would describe a contract the
1.4.0 engine `main` still ships does not implement.

- **`docs/reference/marker-protocol.md`** — §3's field table; §4.1, whose four-field guard
  is the one this item has to move; §4.2, §4.6, §4.8 and §4.10 for the payloads that become
  codes; and §5.1/§5.2, which currently reserve this item for `HINT` and `REMEDY` alone
  (§3). All in the same commit as the engine and both suites, per that document's §5.
- **`local-CI.sh` and `.github/workflows/release.yml`** — both name `tests/i18n-check.py`,
  and both gain the second, `-reverse` run of `tests/gui-smoke.py`. A suite named in neither
  runs nowhere (`docs/standards/files-and-naming.md` §2.2), and over half the invariants
  here are carried by those two additions.
- **`tests/gui-smoke.py`** — its own `QApplication` is constructed with `sys.argv`, or the
  `-reverse` run is silently left-to-right (§4.2).
- **`docs/standards/wording-and-translation.md`** — its **What checks this** table gains
  real catchers for §6.1 and §7, which say *nothing yet* today.
- **`docs/standards/ui-and-accessibility.md`** — §8.1's known `text-align` site and §8.3's
  two handed sites are resolved. §8.1's and §8.2's **What checks this** rows become guards
  rather than outstanding work; §8.3's row goes from `nothing` to the RTL pass's pixel
  sample **for `ToggleSwitch` only**, and says so, because that is all it covers (§7).
- **`docs/standards/files-and-naming.md`** — `tests/i18n-check.py` joins the `tests/` row
  and the test-naming table. `oneup/translations/` is already in its §4 package tree.
- **`CHANGELOG.md`** — one entry under *Changed*, naming the payload conversion as a
  contract change, and saying plainly that **the retained Bash engine stops being a drop-in
  for the window**: it is frozen at the switch-over, so from this item onward it emits prose
  to a window that expects codes. It still runs an update in a terminal. `oneup-2.0.md` §4
  assigns that sentence to this item rather than leaving it to be discovered.
- **`README.md`** — a short note that OneUp ships in English and how to contribute a
  language.
- **The two systemd user timer units** — the `--notify` flag comes off both, because the
  window now raises the notification (§4.4, INV-13).
- **No version-site change** — none of `docs/standards/workflow.md` §5.1's six sites moves.
  This lands inside 2.0, not as a release of its own
  (`docs/standards/workflow.md` §5.1).

## 9. Alternatives considered (and rejected)

- **Convert only `HINT` and `REMEDY`, as the reference reserves.** Rejected: §2.2 shows the
  window is already re-deriving `STEP_END`'s meaning from English substrings, so the coupling
  is a live defect independent of translation — and G10 would be met in name while every
  task badge stayed English.
- **Keep the English in the engine and translate it in the window by lookup.** Rejected:
  the key would be an English sentence, so every wording fix silently loses its translation,
  and the privileged half would still own the vocabulary.
- **Set the layout direction from `QLocale.system().textDirection()` at startup.**
  Rejected on measurement: it clobbers `-reverse` (§2.3), which makes the only gate this
  item has prove nothing. Letting Qt derive the direction from the catalogues costs no code
  at all.
- **Leave the timers' desktop notification with the engine.** Rejected: it is a sentence a
  user reads, on the one path where no window is open to read anything else, so leaving it
  would make §1's goal false for precisely the user the timers exist for — and it would put
  wording back in the privileged half, which is the thing design §5.1 is about.
- **Ship a German catalogue as proof the machinery works.** Rejected: the user's decision is
  English only in 2.0 (§3), and a machine-translated catalogue nobody can review is worse
  than none. INV-11 proves the pipeline instead.
- **Use `gettext` rather than Qt's own machinery.** Rejected: Qt supplies the extraction,
  the editor, the plural rules and the direction derivation; a second system would duplicate
  all four and lose the last one.
- **A single `oneup/gui/translations.py` holding both the loading and the sentence tables.**
  Rejected: `markers.py` already owns turning a marker into English, and the loading has to
  run before any widget exists. Two responsibilities, two homes
  (`docs/standards/coding.md` §4.2).

## 10. Out of scope

- **Any second language.** No `.ts` or `.qm` file for another language is written, reviewed
  or shipped in 2.0 (design §5.1). `oneup/translations/` has its slot in
  `files-and-naming.md` §4 already, but nothing is tracked in it until a real `.ts` lands.
- **Translating the engine's terminal output.** `./update_system.sh` run directly is a
  system tool's output and stays English (`wording-and-translation.md` §5). Its `--notify`
  notification is part of that output and stays with it — what changes is that the timers
  stop using it, not that the flag goes (§4.4).
- **Translating log files, diagnostics or the bug-report clipboard payload.** They are read
  by a developer.
- **Locale-aware number, date and byte formatting.** Worth doing, not this item; the sizes
  the engine reports are data (§4.4).
- **Mirroring the tray icon** (§4.7).
- **Re-wording any message.** The conversion carries each sentence across as it stands
  (§3.1).

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-27 | 3 lanes; 3 critical, 3 high, 9 medium, 3 low — **17 verified, 1 dismissed** | The three worst were each a claim the tree contradicts. `@@CHECK@@`'s `label` and `@@REPO_SKIPPED@@`'s `reason` were routed to codes when the window reads neither — the reference says so of the first outright — which would have put a bare token in front of the only reader they have. §4.4 and §4.5 gave two different wire shapes for `@@REBOOT@@`'s components. And the right-to-left gate was wired to the wrong `QApplication`: `tests/gui-smoke.py` builds its own with an empty argument list and never calls the application's `main`, so `-reverse` would have reached nothing and INV-8 would have passed while proving the opposite. Two fixes landed outside this spec: `ui-and-accessibility.md` §8.3 was wrong that `_paint_state_shape` computes from the left edge as the knob does — it picks its edge from the *state*, so the two handed sites need different fixes — and the ROADMAP bullet repeating it. Dismissed: that §4.2 misattributes the no-`setLayoutDirection` rule to §8.4; the sentence says §8.4 owns the *reading* half and this is the writing half, which is what it says. |
| 2 | 2026-07-27 | 3 lanes; 3 high, 5 medium, 4 low — **10 verified, 2 dismissed** | The gap worth the loop was one the marker protocol could never have shown: `notify_send` raises a desktop notification, in English, on the two timer paths — the only paths where no window is open — and it never travels as a marker, so none of §4.4's routes touched it. The timers now stop passing `--notify` and the window builds the sentence (INV-13). Two of loop 1's own fixes had defects: INV-2's `^[a-z0-9-]+$` could not match the space-separated field the same loop gave `@@REBOOT@@`, and §8's "§4.1 (including its four-field guard, §4.4)" reads as `marker-protocol.md` §4.4, which is `REFRESH` and unrelated. `oneup-2.0.md` §4 assigns this item a release-note sentence — the Bash fallback stops being a drop-in — that §8 was not carrying. Dismissed: that §4.2 does not describe a mechanism for "pair or neither" and §4.4 does not state the new guard value; both sentences already say it, and answering a finding with more prose is what makes the next loop cost more. |
| 3 | 2026-07-27 | 3 lanes, two accepted clean; 1 critical, 2 high, 1 medium, 4 low — **5 verified, 3 dismissed** | The critical was a rule this spec invokes and cannot satisfy: `marker-protocol.md` §5 puts the reference edit in the same commit as the four code files, `workflow.md` §9 sends all documentation to `main`, and those code files are 2.0-only — so the tree as written offered a choice between breaking the same-commit rule and breaking the freeze. Fixed in `workflow.md` §9, where it belongs, along with the two places §2 and §11 restate the branch rule; the answer is that the reference goes to `v2`, because a reference amended on `main` would describe a contract `main`'s own 1.4.0 engine does not implement. Loop 2's own fix stranded a sibling again: INV-2 gained "space-separated as `@@REBOOT@@` and `@@SERVICES@@` do", but `SERVICES` carries unit names, which §4.4 routes to data. And §1 promised a gate for "a widget that only works in English" that only exists for the one painted widget the suite already samples. Dismissed: that §6 has no row for five invariants (they are source-level guards with no runtime failure mode), that §2.1's `grep -c` result is a raw count (`documentation.md` §6b's permitted form is exactly a command plus a past-tense measurement), and that §8 cites the wrong section for the same-commit rule (§5 is where it is written). |
| 4 | 2026-07-27 | 3 lanes, two accepted clean; 3 medium, 3 low, 1 info — **6 verified, 1 dismissed** | Nothing found was a wrong claim; every finding was the document not saying enough, and all in one section. `@@CHECK_UNKNOWN@@`'s `reason` is three engine sentences, not one, and one of them interpolates a comma-joined alias list — so it is three codes and a list argument, which §4.4 had not worked out. `@@REBOOT@@`'s components and that same alias list both render a *variable number* of things into a sentence, which §4.6's "code plus parameter names" table shape cannot express; those two entries carry a render function, and the agreement goes through the plural form rather than English's. `@@STEP_BEGIN@@`'s and `@@STEP_END@@`'s new field shapes are now written out rather than inferable. Dismissed: that §4.4's pointer to §4.5 for the space-separated format is misdirected — §4.5 states that rule. |
