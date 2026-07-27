# OneUp 2.0 — programme design

**Status:** Reviewed
**Kind:** programme-design — the release as a whole. Each item below has (or gets) its
own spec; this document holds only what the items *share* or *contend over*.
**Roadmap:** ONEUP-0057 (the documentation set this design opens)
**Branch:** `v2` — the branch the *work* lands on. This document itself lands on `main`
(§5.3). `main` released **1.4.0** and is now frozen — see §5.4.
**Verified at:** `8d4c93e` — every figure below was measured against that tree on
2026-07-27, not recalled, unless the figure names its own commit.

**Sections:** 1 what 2.0 contains · 2 the baseline · 3 what must not change · 4 the
`oneup/` package · 5 cross-cutting decisions · 6 items without a spec · 7 the gate ·
8 risks · 9 what governs what · 10 out of scope · 11 cold-eyes log

**`Draft` means implementation may not start** (`docs/standards/documentation.md` §3).

**In one sentence:** 2.0 rebuilds OneUp's insides — the updating engine moves from Bash
to Python, the one huge window file becomes several small ones — and adds colour themes
and the groundwork for other languages, and none of it reaches users until the whole
thing can replace what they run today.

---

## 1. What 2.0 contains

| Item | What it is | Spec |
| --- | --- | --- |
| **ONEUP-0054** | Replace the Bash engine with a Python one | `docs/specs/ONEUP-0054-python-engine.md` |
| **ONEUP-0034** | Split `updater.py` into focused modules | `docs/specs/ONEUP-0034-gui-modules.md` *(to be written)* |
| **ONEUP-0064** | Redesign the interface for ergonomics, clarity and accessibility — **no focus borders**; the on/off switches stay. `docs/standards/ui-and-accessibility.md` §5.4 adds a hard obligation: pick a ringless focus treatment measuring **≥ 3:1 against its own rest state, in every shipped theme**, and add the measurement to the suite. Because §5.2 lands themes *after* the redesign, ONEUP-0027 re-takes that measurement for each palette it adds | `docs/specs/ONEUP-0064-interface-redesign.md` *(to be written)* |
| **ONEUP-0027** | Selectable colour themes beyond follow-the-desktop. `docs/standards/ui-and-accessibility.md` §7 adds a hard obligation: the contrast check every new theme must pass | `docs/specs/ONEUP-0027-themes.md` *(to be written)* |
| **ONEUP-0032** | Wrap user-facing text for translation, and mirror the window for right-to-left languages — **groundwork only, English alone**, see §5.1 | `docs/specs/ONEUP-0032-i18n.md` *(to be written)* |
| **ONEUP-0044** | The double password box | no spec — see §6.2 |
| **ONEUP-0004** | Dependency refresh — chiefly the CI Python version | no spec — see §6.3 |
| **ONEUP-0063** | Add `pyproject.toml`, so a bare `ruff check` and the gate agree — not a one-line config drop, see §6.4 | no spec — `docs/standards/coding.md` §2.1 settles it |
| **ONEUP-0059** | Honour `XDG_STATE_HOME` where it is set, instead of hard-coding `~/.local/state` | no spec — `docs/standards/files-and-naming.md` §5.2 and §7 Trap 3 settle it. It moves **both halves at once** — see §6.5 |

**This is the list of top-level items, each with its own slot in §5.2's order.** Work that a
spec commissions inside one of them — ONEUP-0058, 0066 and 0070 are all deliverables of
`ONEUP-0054`'s stages — is gated by that item's spec, not listed again here. **Some open items are 2.0 work by somebody's reckoning and are on neither list, and saying so
is better than implying cover.** ONEUP-0060 (pin PySide6 and PyInstaller in the AppImage
build) is called a 2.0 fix by `docs/standards/security.md`, and **G8 does not check it** — an
unpinned build builds and launches exactly like a pinned one. ONEUP-0062 (the GUI suite's
teardown tracebacks) is called a 2.0 fix by `docs/standards/testing.md`, whose §7 traces them
to `QProcess` parenting that exists today. ONEUP-0067, 0068 and 0069 are test-suite gaps that
the freeze will not take on `main` (`workflow.md` §1.2) and that no 2.0 item carries either.
ONEUP-0061 (migrate `QSettings` if the organisation string changes) states its own
*"requirement for 2.0"* and is likewise on neither list.

None of these has a slot in §5.2 or a bar in §6, so **G7 cannot see any of them**. They
are carried by whoever touches the surrounding code, and if that is not good enough they
should be added to the list above before it closes. This paragraph exists so that choice is
made rather than defaulted into.

The list is **open, but not forever.** More items may be added while 2.0 is being built;
each addition gets a roadmap bullet and, if it needs design, a spec, and is judged against
§7's gate like everything else. **The list closes when the engine rewrite starts** — the
last-but-one item of §5.2 — because §7's G7 ("every item on the list is complete") cannot
be satisfied against a list that can still grow. Anything raised after that point is 2.1
unless it is a defect in something already on the list.

## 2. Verified baseline — what 2.0 replaces

**2.0 replaces 1.4.0**, released from `main` at `dbef1a8`, after which `main` froze (§5.4).

This section is where **2.0's baseline** measurements live — other documents keep their own, for their own arguments — because two
standards point here for them rather than repeat them — `docs/standards/coding.md` §4.1 for
the module sizes and `docs/standards/testing.md` §1 for the suite tallies. The
privileged-call total runs the other way: `docs/standards/security.md` §1.2 **owns** it and
this section merely carries it, which is deliberate — the earlier arrangement, where two
documents each derived the split, is what produced the contradiction that standard's first
review had to unpick. Everything here was
**measured at `8d4c93e` on 2026-07-27** unless the row names its own commit, and is written
as something that was measured, not
as something that is true (`docs/standards/documentation.md` §6b.4). The unit is named in
every row, because the worst figure error this set has produced was an unnamed one.

| Measured at `8d4c93e` | Value | How it was counted |
| --- | --- | --- |
| `update_system.sh` | 1,558 **lines** | `wc -l` |
| `updater.py` | 3,719 **lines** — more than six times `coding.md` §4.1's 600-line ceiling, which is the whole case for ONEUP-0034 | `wc -l` |
| Engine suite | 205 **assertions** over 76 **scenarios**, all passing | `./local-CI.sh` prints the assertion tally; the scenario figure is `grep -c '^echo "TEST: ' tests/run-tests.sh` |
| GUI smoke suite | 283 **assertions**, all passing | `./local-CI.sh` prints the tally |
| `bump.py` functional test | 6 **assertions**, all passing | as above |
| Privileged invocations in the engine | **34**, as measured at `58ea3bc` | `docs/standards/security.md` §1.2 owns the breakdown, the exclusions, and why `grep` alone gets it wrong. Unchanged since, because `update_system.sh` is |

One further figure is exempt from §6b in the way `documentation.md` §6b.5 means — pinned by
a decision *and* gated, so it cannot go stale unnoticed. The other two are pinned by a
decision and gated by nothing, which by §6b.5's own test (*"if nothing fails when the number
goes wrong, it is a measurement"*) makes them measurements. They are kept here, in §6b.4's
form, with the gap named:

| Pinned by | Value, as measured at `8d4c93e` | What fails when the tree stops matching |
| --- | --- | --- |
| `docs/standards/workflow.md` §5.1 — the six version sites | all six read **1.4.0** | `local-CI.sh`'s version-lockstep gate |
| §3 below, via `docs/reference/marker-protocol.md` §3 | **23** markers | **the count, nothing.** `tests/docs-check.py` compares the marker *names* both ways, so a marker added to the engine *and* the table agrees with itself and leaves this figure stale |
| §3 below — the engine's command-line surface | **13** flags: `--auth-status`, `--auto-skip-repos`, `--check`, `--grant-auth`, `--help` (and its `-h` alias), `--import-keys`, `--log=`, `--notify`, `--revoke-auth`, `--size=`, `--skip-repo=`, `--steps=`, `--thin-snapshots` | **nothing.** No gate reads the engine's flag list. The freeze in §3 is a human undertaking |

The Python floor and the lint rule set are settled decisions rather than baselines, and
`docs/standards/coding.md` §1 and §2.1 own them — see §6.3 and §6.4.

## 3. What must not change

These four are frozen for the duration. They are what makes a rewrite of this size
provable rather than hopeful — the existing engine and GUI assertions only keep their power
if the thing under test still presents the same face.

1. **The `@@MARKER@@` protocol** — every marker `docs/reference/marker-protocol.md` §3
   lists, its field order and its meaning.
   Documented in `docs/reference/marker-protocol.md`. **One** deliberate, versioned
   exception, recorded in `docs/reference/marker-protocol.md` §5.1 and sequenced in §5.1
   below: ONEUP-0032's conversion of the `@@HINT@@` and
   `@@REMEDY@@` payloads to codes. The byte counters the engine rewrite makes possible
   (`docs/specs/ONEUP-0054-python-engine.md` §4.3.3) need a marker too, and land **after the
   2.0.0 tag** — not a second exception inside 2.0. See §10.
2. **The engine's command-line surface** — every flag §2 enumerates, its spelling and its
   behaviour.
3. **The five step keys and their order** — `system, flatpak, firmware, orphans, cache`.
4. **The privilege split** — the window never *becomes* root and calls no `sudo`; the work
   of an update run goes through the engine, which authenticates once.
   `docs/standards/security.md` §1.4 owns the exact boundary, including the window's three
   `pkexec` actions; stating it more absolutely than that is the error §9.1 of that standard
   warns about.

A change to any of these is a design decision requiring its own spec section, not an
implementation detail.

## 4. Target shape — one `oneup/` package

Both big items restructure code, so they must agree on where it goes. Today the two files
the *application* is made of both sit at the repo root (the other three root scripts —
`bump.py`, `local-CI.sh`, `release.sh` — are developer tools and stay where they are,
`docs/standards/files-and-naming.md` §7 Trap 5); 2.0 has one package:

```
oneup/
  __init__.py
  engine/          the Python replacement for update_system.sh
    ...            (module split defined in ONEUP-0054's spec)
  gui/             the split-up updater.py
    ...            (module split defined in ONEUP-0034's spec)
  translations/    oneup_<lang>.ts catalogues (ONEUP-0032)
updater.py         thin entry point — kept at the root, because the RPM's
                   /usr/bin/oneup wrapper (which the desktop file's Exec=oneup
                   runs), the AppImage and every user's launcher all name it
update_system.sh   retained through 2.0 as a documented fallback, removed in 2.1
```

**`update_system.sh`'s retirement schedule is this document's**, decided with the user on
2026-07-27: 2.0.0 still ships it, marked as a fallback, and 2.1 removes it — so anyone who
scripted against the engine gets a release's notice, and a real-machine problem with the new
engine has a way back.

**That way back has an expiry, and it is inside 2.0.** ONEUP-0032 converts the `@@HINT@@` and
`@@REMEDY@@` payloads to codes (§5.1) *after* the switch-over, and the retained Bash engine is
not converted with them — it is frozen at the switch. So from 0032 onward the fallback emits
English prose to a window that expects codes: still usable for running an update in a
terminal, no longer a drop-in for the window. Say that in the release notes rather than
discovering it. `ONEUP-0054` §4.7 points here for the schedule and adds only which
stage performs it; `docs/standards/files-and-naming.md` §4 carries the same one line.

**Packaging is affected, in three places, and they must move together** — this is the
part a restructure most easily forgets:

- `packaging/rpm/oneup.spec` installs exactly two files (`updater.py`,
  `update_system.sh`) into `%{_datadir}/oneup/` and launches the first; a package needs a
  directory install and a `Requires` review.
- `packaging/appimage/build-appimage.sh` bundles `update_system.sh` via `--add-data` and
  points PyInstaller at `updater.py`; a package needs the analysis to follow imports.
- `packaging/obs/_service` rolls a tarball whose layout the **RPM spec** expects. (In this
  document "spec" otherwise always means a `docs/specs/` document; this is the one place it
  does not.)

**Constraint carried from the roadmap:** the GUI split must be *behaviour-preserving*.
The window looks and works identically; only the file boundaries move.

## 5. Cross-cutting decisions

### 5.1 Translated text lives in the window, never the engine

**Decision:** the engine emits **stable codes**; all wording — and therefore all
translation — happens in the GUI.

Three reasons, in order of weight:

1. **It keeps translation out of the privileged half.** The engine is the part that calls
   `sudo` (`docs/standards/security.md` §7.2 — it is never run as root in its entirety). Locale files, `gettext`-style catalogue lookup and per-user language settings
   have no business there.
2. **It protects the rewrite's own test gate.** Gate G2 compares v1's and v2's marker
   streams for equality. An engine that emitted translated text would produce a different
   stream on a German desktop, so the comparison would be testing the locale, not the
   rewrite.
3. **The GUI already owns presentation.** It renders badges, banners and hints; wording
   belongs where the widgets are.

**The honest complication:** this is a *contract change*, and §3 froze the contract.
`@@HINT@@` and `@@REMEDY@@` carry English prose today. Resolving it by ordering:

- The engine rewrite ships with the contract **byte-identical**, English prose included.
  It passes its gate against unchanged tests.
- **Then**, as part of ONEUP-0032, the prose payloads become codes in **one deliberate,
  versioned change**, touching every file `docs/reference/marker-protocol.md` §5 lists —
  the engine that emits them included — in the same commit. It is a break, done once, with
  the rewrite already proven, not a break smuggled inside one.

**`docs/reference/marker-protocol.md` §5.1 is canonical for that ordering** — it is rank 1,
and it holds both the rule and the reason. Not restated here.

**How much of this ships in 2.0 — decided by the user, 2026-07-26:** *"I would like to
offer the app in different languages too, however, first point is to get to a working
version first, release and then we can add additional languages."*

So 2.0 ships the **machinery and no second language**:

- every user-facing string wrapped for translation, the catalogue extracted and building,
  and the engine's `@@HINT@@` / `@@REMEDY@@` payloads converted to codes;
- **English only** in the release. No `.ts`/`.qm` locale file for another language is
  written, reviewed or shipped as part of 2.0.

The reason this is the right cut, and not a hedge: wrapping strings is a change to **every
file that shows text**, so it has to happen inside 2.0, while the window is already open —
doing it in 2.1 means a second pass over every one of those files, after they have settled.
Translating strings, by contrast, touches **no code at all**. One is structural and belongs
inside the rewrite; the other is content and can arrive in 2.1 without reopening anything.
Shipping the groundwork also means the first language contributed later is a data file, not
a project.

(This is why 0032 is *inside* 2.0 but *last* within it, §5.2: the redesign rewrites the
wording anyway, so wrapping before it would mean wrapping twice.)

Consequence for §7's gate: "a language is available" is **not** a release condition for
2.0. "Every user-facing string is translatable" is.

**Right-to-left languages are in scope — user's decision, 2026-07-26.** Hebrew and Arabic
read right-to-left, and the whole window must mirror: the toggles sit on the other side,
progress fills the other way, text aligns to the right.

This lands in 2.0 **with the groundwork, not with the languages**, for the same reason the
string-wrapping does — it is structural. A layout built the wrong way must be rebuilt, not
translated. Getting it right while the modules are being written costs almost nothing;
retrofitting it means reopening every one of them.

**Measured at `8d4c93e`, not assumed — the starting position is good, with two known
exceptions.** `docs/standards/ui-and-accessibility.md` §8 owns this survey and its detail;
the summary that bears on 2.0's shape:

| Thing that normally breaks RTL | Count in `updater.py` |
| --- | --- |
| The six directional margin / padding / border properties — Qt does **not** mirror these | **0** |
| `text-align: left` / `right` in `_QSS` — equally unmirrored | **1**: `QPushButton#LinkBtn` (`ui-and-accessibility.md` §8.1) |
| Hard-coded `AlignLeft` / `AlignRight` | **0** |
| Existing RTL/locale handling | **0** — nothing to unpick either |

Qt mirrors widget layouts automatically once the application's layout direction is set, so
every layout built out of Qt's own containers mirrors without being touched. What will not
mirror is what the app draws or aligns by hand: the two `ToggleSwitch` sites below and the
one `text-align` above.

**The place custom painting will not mirror**: `ToggleSwitch` in `updater.py` draws the
switch by hand, and Qt's mirroring cannot see inside a `paintEvent`. There are **two** handed
computations in it, not one — the knob's position and the state shape's centre — and both
belong to **ONEUP-0032**, because mirroring the window for right-to-left is what that item
is. `docs/standards/ui-and-accessibility.md` §8.1 and §8.3 own the detail, name each site,
and explain why fixing only the obvious one is worse than fixing neither.

Two further consequences, both structural:

- **No user-facing sentence may be built by concatenation.** A sentence glued from
  fragments cannot be reordered by a translator, and in RTL the fragments can render in an
  order nobody intended. Whole sentences with named placeholders, always. The sweep is the
  rule, not its current result: measured at `8d4c93e`, `grep -cE '"\s*\+|\+\s*"' updater.py`
  reported **10** matching *lines*. That is a rough upper bound on the work rather than a
  count of sites: it matches any `+` beside a double-quoted string, not only the ones
  building a sentence a user reads, and two on one line count once.
- **RTL is tested, not hoped for.** `tests/gui-smoke.py` gains a pass with the layout
  direction forced right-to-left. Without a test it will regress the first time somebody
  adds a widget, because on an English desktop nobody will ever see it.

### 5.2 Order of work, and why

```
1.4.0 released from main, then main freezes  ← §5.4
        │
        ▼
dependency refresh (0004)      ← first because they set the tooling every later item
   + lint config (0063)          is judged by: adopting the lint config changes what
        │                        the gate accepts, so doing it after the rewrites
        │                        means re-clearing it against far more code. Not
        │                        free — coding.md §2.1.1 measured the clean-up it
        │                        brings with it. Neither moves the Python floor
        │                        (coding.md §1, and §6.3).
        ▼
GUI split (0034)               ← first substantial work on v2, and alone: it is
   + XDG paths (0059)            behaviour-preserving, so the existing GUI
        │                        assertions judge it with nothing else in flight.
        │                        0059 rides with it — same module-level path
        │                        constants, §6.5.
        ▼
interface redesign (0064)      ← after the split, because redesigning a module
        │                        six times the size ceiling while also cutting
        │                        it up makes both changes unreviewable
        ▼
themes (0027)                  ← after the redesign, for the same reason in
        │                        reverse: theming a layout that is about to
        │                        change means doing it twice
        ▼
engine rewrite (0054)          ← the long pole; gate in §7
        │
        ▼
translation (0032)             ← last: wrapping strings before the split means
                                 wrapping them twice, the redesign rewrites
                                 the wording anyway, and §5.1 requires the
                                 rewrite to be proven before the contract moves
```

The double-password investigation (0044) runs alongside the rewrite; see §6.2.

**Why the redesign sits between the split and themes.** All three touch the same
widgets. Doing the split first means the existing GUI assertions judge it with nothing
else in flight (it changes no behaviour); doing the redesign next means themes style the
final layout rather than a doomed one; and leaving translation last means the redesign's
new wording is wrapped once, not twice. The order is a consequence of each item's
verification method, not a preference.

### 5.3 Where each item lands

| Item | Branch | Why |
| --- | --- | --- |
| **The 2.0.0 release itself** | `v2` merges **into** `main` | `release.sh` refuses any branch but `main` and pushes `origin main`, and `docs/standards/workflow.md` §2 otherwise forbids that direction — so the merge is a one-off, taken deliberately once G1–G10 pass, and it is the moment `main` unfreezes. Nothing automates it |
| Documentation (this set) | `main` | The standards govern 1.x maintenance too, and `v2` inherits them by merge. Docs are not a release, so they are unaffected by the freeze. A *later* doc edit that a rule binds to the same commit as 2.0-only code is the one exception, and goes to `v2` — `docs/standards/workflow.md` §9 owns it |
| **Everything in §1** | **`v2`** | Under the freeze (§5.4) `main` takes nothing but qualifying bug fixes, so every 2.0 item — including the GUI split — belongs on the branch |
| The one exception: a behaviour-neutral **test-harness** change | `main` first | `docs/standards/workflow.md` §1.2 defines the exception and its conditions. It exists for exactly one change — the `ONEUP_ENGINE_CMD` indirection (`ONEUP-0054` §4.4) — which must be shown to leave the suite green on `main` before either engine depends on it |

**The GUI split moved.** An earlier revision of this document put it on `main`, for one
reason only: months of 1.x fixes would otherwise collide with files `v2` had moved.
**The freeze removes that reason** — `main` is now near-idle — so the split returns to
`v2`, where it is the first substantial work (§5.2) and everything on the 2.0 list ships
as 2.0. Decided with the user, 2026-07-26, superseding the same day's earlier call.

### 5.4 The v1 freeze

**`main` is frozen at 1.4.0, released at `dbef1a8`.**

**The rule itself is `docs/standards/workflow.md` §1** — what still qualifies for `main`,
the two readings inside the user's definition, the openSUSE-changes-underneath trigger, the
behaviour-neutral test-harness exception, and what does not qualify. It is a standard, so it
outranks this document (`docs/standards/documentation.md` §1.1), and it is where somebody
deciding *which branch does this go on* will look. Deliberately not restated here, so the
two cannot drift; §2 of that standard likewise owns the branch table and the never-rebase
rule.

What belongs *here* is the programme framing — why a freeze, and what it costs:

- **Why 1.4.0 shipped first rather than freezing earlier.** The eight improvements finished
  at `256d0dc` would otherwise have been buried for the whole length of the 2.0 build. The
  version people are frozen on should be the best one available.
- **What the freeze buys 2.0.** Long-branch drift is the standing risk of a rewrite on a
  side branch (§8), and a `main` that takes almost nothing cannot drift far.
- **What it costs.** Every 1.x improvement anybody thinks of now waits for 2.0 — which is
  the pressure §8's "the freeze leaks" risk is about.

## 6. Items without a spec of their own

### 6.1 Why some items get no spec

A spec exists to settle *design* questions before code makes them expensive. An item with
no open design question gets a roadmap bullet and a build plan, not a spec.

### 6.2 The double password box (ONEUP-0044)

**No existing gate can see this bug, and G4 is not the exception it looks like.** The
symptom is *two dialogs from one authentication*: the roadmap bullet measures one engine
invocation, one `sudo -A -p … -v`, and two `ksshaskpass` processes sixteen seconds apart.
G4's scenario counts **authentications** — its mock `sudo` keeps one timestamp file per
parent pid and logs a line only when a call actually has to authenticate — and there is no
real askpass in the sandbox at all. So the suite is green today while the bug is open, and
will stay green if the rewrite reproduces it.

That is why this item is an investigation rather than a fix: the first task is a harness
that reproduces it, which attempts so far have not managed. It gets a diagnosis step in the
engine's build plan. Should the cause need real design — for example a change to how the
engine authenticates — it earns a spec at that point.

**Complete when** the cause is identified and either fixed with a test that fails without
the fix, or recorded as understood-and-accepted with the reason. "We could not reproduce
it" is an acceptable outcome; leaving it unexamined is not.

### 6.3 Dependency refresh (ONEUP-0004)

**Complete when** `release.yml`'s `python-version` reads 3.14 on `v2` and the suites are
green against it.


Governed by `docs/standards/dependencies.md`, which owns the ledger and the 2026-07-26
sweep behind it — including why the Python row was deleted rather than deferred, and why the
`ubuntu-22.04` runner pin stays. Not repeated here.

What belongs to *this* item is the work the sweep left: the one-line bump of
`release.yml`'s `python-version` from 3.13 to 3.14, on `v2`, since `main` is frozen and does
not take it.

**Nothing else here is an open question.** Two that once were are settled, and
`docs/standards/coding.md` owns both:

- **The Python floor is 3.13** (`coding.md` §1) — looked up against what the supported
  openSUSE targets actually ship, not assumed. The 3.14 bump above raises what CI *runs on*;
  it does not raise the floor.
- **A `pyproject.toml` is added in 2.0** (`coding.md` §2.1), carrying the lint rule set, so
  that a bare `ruff check` and the gate agree. That is ONEUP-0063. Until it exists the
  divergence is between `ruff check .` and `./local-CI.sh` — **not** between a developer and
  CI, because GitHub CI runs no lint at all (`workflow.md` §6).

### 6.4 The lint configuration (ONEUP-0063)

`docs/standards/coding.md` §2.1 settled it: 2.0 adds a `pyproject.toml` carrying the rule
set, so a bare `ruff check` and the gate agree and `local-CI.sh` can drop its `--select`
flags.

**It is not a one-line config drop, and §2.1.1 of that standard is why**: adopting the
config reports errors that then have to be cleared, and that standard owns the measurement
and the commit it was taken at. An implementer who adds the file alone turns the gate red
on the next commit.

**Complete when** `pyproject.toml` exists, `local-CI.sh` runs a bare `ruff check`, and that
check is green.

### 6.5 XDG state and config paths (ONEUP-0059)

`docs/standards/files-and-naming.md` §5.2 and §7 Trap 3 settle it: honour `XDG_STATE_HOME`
where it is set, rather than hard-coding `~/.local/state`. (`XDG_CONFIG_HOME` needs no work —
settings go through `QSettings("OneUp", "OneUp")`, which Qt already resolves under it.)

**This is a change to both halves in one commit, and that is the whole risk in it.**
`run.state` and `stop.request` are a contract between the window and the engine — that
standard's §5 says so, and `updater.py`'s `RUN_STATE` carries the comment *"match
`RUN_STATE_FILE` in `update_system.sh`"*. Move one side alone and, on a machine with
`XDG_STATE_HOME` set, the window writes `stop.request` where the engine never looks: Stop
quietly stops working and run-following breaks, with nothing failing anywhere.

It lands with the GUI split (ONEUP-0034), because that is where the window's module-level
path constants move — **and the Bash engine's two lines move in the same commit**, even
though the engine rewrite is still several items away. `ONEUP-0054` §4.1.1 pins the state
files' *layout*; this settles their *location*.

**Complete when** `XDG_STATE_HOME` is honoured where set and the default is unchanged where
it is not, **in both halves**, and a run started with it set can be followed and stopped.

## 7. The gate — what "ready" means

**Nothing ships as 2.0 until it can fully replace v1.** The user's rule, 2026-07-26:
no partial 2.0 releases, no 2.0 beta cut from the branch mid-way. Users stay on frozen
1.4.0 (§5.4) until 2.0.0 arrives complete.

Concretely, all of the following. The **checked by** column is the point: a condition
nothing can check is not a gate.

| # | Condition | Checked by |
| --- | --- | --- |
| **G1** | Engine suite passes with **no existing assertion weakened** — v2 satisfies the tests v1 was measured by. **Additions are permitted; weakening is not.** One existing scenario is *replaced* rather than carried, because it asserts Bash source rather than behaviour (`ONEUP-0054` §4.3.5), and the harness gains the `ONEUP_ENGINE_CMD` indirection (that spec's §4.4, at the two call sites it names). Every other suite change must be a **new scenario or a new assertion** named by a stage in `ONEUP-0054` §4.6 | the suite green against the new engine, plus a review of `git diff` on the suite: one replacement, one harness change, and additions `ONEUP-0054` §4.6 names. Anything else fails the gate |
| **G2** | v1 and v2 emit the **same marker stream** under identical mocks | `tests/differential-test.sh` — new, and `ONEUP-0054` §4.5 owes it |
| **G3** | GUI suite green with the window driving the new engine | `python3 tests/gui-smoke.py` — **but the suite as it stands feeds the window marker lines and never launches an engine at all**, so on its own it proves the window, not the pairing. G3 needs the run under `ONEUP-0054` §4.6 stage 7's environment switch, with the window actually resolving to v2 |
| **G4** | A full run **authenticates** exactly once — not the same as one dialog, see §6.2 | the existing one-prompt scenario |
| **G5** | The engine runs with **PySide6 absent** and imports no Qt — the *dependency direction*, enforced by test. It is half of §3's privilege split, not the whole: `docs/standards/files-and-naming.md` §4.1 rule 2 names what it misses, an engine module importing a Qt-free helper out of `oneup/gui/` | a new scenario with PySide6 hidden from the import path |
| **G6** | A real run on the user's own machine | manual, against the explicit list `ONEUP-0054` §4.5 requires stage 6 to write — the list is a deliverable, not a judgement call |
| **G7** | Every item on the §1 list is complete — those with a spec, by their spec's invariants being covered by tests; those without one, by the **Complete when** line §6 gives each. The rewrite's once-measured invariants (INV-10 *is* G2) are read at the stage that earned them, not re-run here — the closing paragraph says why | **nothing automatic.** It is a release checklist walked by hand, over a list §1 closes at the start of the engine rewrite so that it can be walked at all |
| **G8** | The three packaging paths build from the new layout, and what each delivers launches: the AppImage directly, the RPM and the OBS repository once installed | `./local-CI.sh --full` builds the AppImage — it does not launch it. All three launches are manual, once each. **The OBS leg cannot be met before the tag**: `packaging/obs/_service` pins its `revision` to the release tag, so that build only exists after 2.0.0 is cut. It is the one condition verified immediately *after* the tag and before the release is announced — and if it fails, the fix ships as 2.0.1 rather than by rewriting a released entry (`workflow.md` §5.2) |
| **G9** | Docs current: README, CLAUDE.md, the standards, the marker reference, CHANGELOG — **and this design and every 2.0 spec flipped from `Reviewed` to `Implemented`** (`docs/standards/documentation.md` §3), which is the step that is easiest to forget because nothing reads those headers | `tests/docs-check.py`, plus a `/cold-eyes` pass over anything 2.0 edited |
| **G10** | Every user-facing string is translatable, and the GUI suite passes with the layout direction forced **right-to-left** | the RTL half is a GUI-suite pass forced right-to-left — **new, and ONEUP-0032 owes it** (§5.1). Two of §5.1's three deliverables are gated by nothing here — the catalogue building, and the `@@HINT@@`/`@@REMEDY@@` conversion — and fall to G7 through ONEUP-0032's own spec. The wrapping half has **no automatic check** — `docs/standards/wording-and-translation.md`'s own table records that gap against its §6.1 — so it is a review of `oneup/gui/` against that standard, and it is the weakest gate here |

**G1–G6 are the engine rewrite's**, and each is met at the stage that earns it —
`ONEUP-0054` §4.6's table is the mapping, and this document does not restate it. Stage 9, the switch-over, is the commit they are all measured against. **G7–G10 are the release's**, met at the 2.0.0 tag — except G8's OBS leg, which the tag is a
precondition of, and which is therefore verified immediately after it and before the
release is announced.

**Why that distinction is not pedantry.** ONEUP-0032 lands *after* the engine rewrite
(§5.2) and, by §5.1, converts the `@@HINT@@` and `@@REMEDY@@` payloads to codes — changing
the marker stream and the assertions that read it, in one versioned change touching all four
files (`docs/reference/marker-protocol.md` §5). Re-run at the 2.0.0 tag, G1 and G2 would
then be false by construction. They are gates on the *rewrite*, measured once, at the commit
that switches the engine over — not standing properties of the release.

**G10 deliberately tests the machinery, not a translation.** Since 2.0 ships English only,
nothing else would exercise the wrapping or the mirroring, and untested groundwork is
indistinguishable from no groundwork by the time somebody contributes Hebrew.

## 8. Risks, and permission to fail

- **The branch may be abandoned.** That is what a side branch is for. If the rewrite
  stalls, frozen 1.4.0 keeps working and nothing is lost but the branch. This is stated
  so that abandoning it stays an available, unembarrassing option.
- **Long-branch drift** — mitigated by the freeze itself (§5.4): a `main` that takes only
  qualifying bug fixes cannot drift far, and each one is merged into `v2` on release.
- **The freeze leaks.** The failure mode of any freeze is a slow slide back into 1.x
  work, one "small" fix at a time. §5.4's definition is deliberately testable — *can
  people still install their updates?* — so the answer is a finding, not a preference.
- **A rewrite that buys less than claimed.** The ONEUP-0054 draft is unusually honest
  about this and its §2 should survive review intact: nothing that went wrong in
  ONEUP-0048 was Bash's fault, and Python still cannot kill a root child.
- **Scope growth.** An open list on a long branch is how releases slip forever. Two things
  bound it: each addition is weighed against G7 — *"does this have to be in 2.0, or can it
  be 2.1?"* — and the list closes outright when the engine rewrite starts (§1).

## 9. What governs what

Listed in `docs/standards/documentation.md` §1.1's precedence order, highest first, so the
table answers *which one wins* as well as *which one covers this*:

| Document | Governs |
| --- | --- |
| `docs/reference/marker-protocol.md` | The engine↔window contract frozen by §3 |
| `docs/standards/*.md` | Standing rules — code, security, docs, files, tests, UI, wording, workflow, dependencies |
| **this document** | Decisions the 2.0 items share or contend over |
| `docs/specs/ONEUP-*.md` | One item's design, invariants and tests |
| `docs/plans/ONEUP-*.md` | One item's build steps — written when that item starts, not before |
| `CLAUDE.md` | A map of the above, plus the traps. Where it restates a rule, the rule's owner is canonical |

## 10. Out of scope for 2.0

- Supporting distributions other than openSUSE, and publishing on Flathub. Not merely out
  of scope for 2.0 — declined outright, with the reasoning in
  `docs/standards/workflow.md` §8.1, which owns it. ONEUP-0071.
- Replacing `zypper`/`flatpak`/`fwupd` call-outs with library bindings — 2.0 still shells
  out; only the shelling-out moves language.
- A plugin or extension system.
- Any change to the five steps or their order.
- **The byte-counter marker** the Python engine makes possible
  (`docs/specs/ONEUP-0054-python-engine.md` §4.3.3). It is a protocol change, so it waits
  until after the 2.0.0 tag and arrives on its own.
- **Any actual second language.** The translation *machinery* is in scope (§5.1); a
  translated locale file is not, and arrives after 2.0 is released — user's decision,
  2026-07-26.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-27 | 2 critical, 7 high, 8 medium, 8 low — **23 verified, 2 dismissed** | The two criticals were both claims the code and a higher-ranked standard already contradicted: `_paint_state_shape` called "symmetric by construction" when it is handed the same way the knob is (§5.1), and §6.3 presenting the Python floor and the lint configuration as open when `coding.md` §1 and §2.1 had settled both. §2's baseline table was rebuilt in `documentation.md` §6b.4's measured form with the unit named in every row; §5.4 stopped restating the freeze it says it does not restate; §7's gate gained a **checked by** column, which is what exposed that G1 and G2 cannot hold at the 2.0.0 tag once ONEUP-0032 changes the payloads |
| 2 | 2026-07-27 | 2 critical, 5 high, 7 medium, 7 low — **19 verified, 2 dismissed** | Nothing from loop 1 came back, which is the proof those fixes held. What loop 2 found was largely what loop 1's fixes had *moved*: adding a **checked by** column to §7 made G1's "no assertion touched" newly falsifiable — and it is false, because `ONEUP-0054` plans three deliberate suite changes — and saying G1–G6 are met "at stage 7–8" gave a third answer to a question the spec's own table already answered. Two claims about gates were flattering: the marker count and the flag list were called contract-fixed with a gate behind them, and neither has one. §2 also had the ownership of the privileged-call figure backwards, in the sentence a later editor would trust |
| 3 | 2026-07-27 | 4 high, 7 medium, 8 low — **17 verified, 2 dismissed** | No critical, and nothing structurally wrong — the loop's work was the gate's own wording. G1's "only these three changes" had become a closed list the engine spec's build plan already exceeds; G3 named a suite that never launches an engine at all; G8 said the OBS path "launches". §2's scenario-count command printed **0** rather than 76, because scenarios are `echo "TEST: …"` and the `^` anchor never matched — a figure whose command does not reproduce it being the exact failure §6b exists to stop |
| 4 | 2026-07-27 | 1 critical, 4 high, 6 medium, 6 low — **15 verified, 2 dismissed** | The critical was this document's own G7: it promised a completion bar for the spec-less items and §6 gave one to only two of the three, so ONEUP-0063 sat on the closed §1 list with nothing to complete against — and was missing from §5.2's build order besides. §6.4 and a place beside 0004 close both. The `ToggleSwitch` right-to-left work was assigned here to ONEUP-0064 and by `ui-and-accessibility.md` to ONEUP-0032, in different release slots — the shape of a job that falls through both. It is 0032's: mirroring the window is what that item is |
| 5 | 2026-07-27 | 1 critical, 3 high, 6 medium, 6 low — **14 verified, 2 dismissed** | The critical was §6.2 telling the implementer that ONEUP-0044 is already an acceptance condition of the rewrite, gated by G4. It is not: 0044's symptom is two dialogs from **one** authentication, and G4's scenario counts authentications — its mock keeps one timestamp per parent pid and there is no askpass in the sandbox at all. The suite is green today with the bug open, and would stay green if the rewrite reproduced it. §6.2 now says so and carries its own completion bar. Two more gate rows were overstated the same way: G5 was labelled "the privilege split" when it tests the dependency direction, which is half of it; and G8's OBS leg cannot be met before the tag it gates, because `_service` pins its revision to that tag |
| 6 | 2026-07-27 | 1 critical, 2 high, 6 medium, 9 low — **16 verified, 2 dismissed** | The critical was loop 4's own fix applied to one item and not its neighbour: ONEUP-0059 was added to §1's closed list in loop 5 with no completion bar and no slot in §5.2, which is exactly what loop 4 had just corrected for ONEUP-0063. §6.5 and a place beside the GUI split close it, and §1 now says what the list is *for*, so sub-deliverables of a spec (0058, 0066, 0070) and items riding with other work (0060, 0062) are visibly accounted for rather than silently absent. The 47-error figure was restated here undated, which dates it to this document's own commit and to a tree nobody measured; `coding.md` §2.1.1 owns it and now carries it alone |
| 7 | 2026-07-27 | 1 critical, 3 high, 4 medium, 5 low — **11 verified, 2 dismissed** | The critical was §6.5, added last loop: it called ONEUP-0059 "a path change, not a contract change" and scoped it to the window. `run.state` and `stop.request` are a contract between the two halves — move one side alone and, on a machine with `XDG_STATE_HOME` set, the window writes the stop request where the engine never looks, so Stop silently stops working with nothing failing anywhere. It now moves both halves in one commit. §1's paragraph about items "riding with" other work was itself an unverified coverage claim — G8 does not check a version pin — and now names the five open items no gate can see, so the choice to leave them uncovered is made rather than defaulted into |
| 8 | 2026-07-27 | 1 critical, 3 high, 4 medium, 6 low — **12 verified, 2 dismissed** | The critical was §3 item 4 stating the privilege split in the absolute form `security.md` §9.1 names as dangerous to believe — and it is one of the four things 2.0 *freezes*, so an implementer would build the boundary from it. Two real gaps closed rather than reworded: nothing anywhere said how 2.0.0 actually gets released (`release.sh` refuses any branch but `main`, and §2 forbids merging that way — so the `v2`→`main` merge is a deliberate one-off, now in §5.3), and the retained Bash fallback stops being a drop-in the moment ONEUP-0032 converts the payloads to codes, which is inside 2.0 |
| 9 | 2026-07-27 | **none verified** (one claim raised, dropped: a lane misquoted the engine spec's "G2 is met at stage 6" as "stage 9" — the spec matches its own stage table) | **Converged.** Closing pass, run cheap and narrow after eight full loops: the code facts every earlier lane had re-verified were frozen in the brief, the severity floor was raised to MEDIUM, and the lanes were asked only for contradictions, false coverage claims, exceeded lists and misdirected references — the four classes that produced every critical from loop 5 onward. Nothing came back |
