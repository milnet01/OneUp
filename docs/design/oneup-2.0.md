# OneUp 2.0 — programme design

**Status:** Draft
**Kind:** programme-design — the release as a whole. Each item below has (or gets) its
own spec; this document holds only what the items *share* or *contend over*.
**Roadmap:** ONEUP-0057 (the documentation set this design opens)
**Branch:** `v2` — the branch the *work* lands on. This document itself lands on `main`
(§5.3). `main` released **1.4.0** and is now frozen — see §5.4.
**Verified at:** `7a7afc1` — every figure below was measured against that tree on
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
| **ONEUP-0064** | Redesign the interface for ergonomics, clarity and accessibility — **no focus borders**; the on/off switches stay | `docs/specs/ONEUP-0064-interface-redesign.md` *(to be written)* |
| **ONEUP-0027** | Selectable colour themes beyond follow-the-desktop | `docs/specs/ONEUP-0027-themes.md` *(to be written)* |
| **ONEUP-0032** | Wrap user-facing text for translation, and mirror the window for right-to-left languages — **groundwork only, English alone**, see §5.1 | `docs/specs/ONEUP-0032-i18n.md` *(to be written)* |
| **ONEUP-0044** | The double password box | no spec — see §6.2 |
| **ONEUP-0004** | Dependency refresh, incl. the Python floor | no spec — see §6.3 |

The list is **open, but not forever.** More items may be added while 2.0 is being built;
each addition gets a roadmap bullet and, if it needs design, a spec, and is judged against
§7's gate like everything else. **The list closes when the engine rewrite starts** — the
last-but-one stage of §5.2 — because §7's G7 ("every item on the list is complete") cannot
be satisfied against a list that can still grow. Anything raised after that point is 2.1
unless it is a defect in something already on the list.

## 2. Verified baseline — what 2.0 replaces

**2.0 replaces 1.4.0**, released from `main` at `dbef1a8`, after which `main` froze (§5.4).

This section is the one place in the set that keeps dated measurements, because two
standards point here for them rather than repeat them —
`docs/standards/coding.md` §4.1 for the module sizes and
`docs/standards/security.md` §1.2 for the privileged-call total. Everything here was
**measured at `7a7afc1` on 2026-07-27**, and is written as something that was measured, not
as something that is true (`docs/standards/documentation.md` §6b.4). The unit is named in
every row, because the worst figure error this set has produced was an unnamed one.

| Measured at `7a7afc1` | Value | How it was counted |
| --- | --- | --- |
| `update_system.sh` | 1,558 **lines** | `wc -l` |
| `updater.py` | 3,719 **lines** — more than six times `coding.md` §4.1's 600-line ceiling, which is the whole case for ONEUP-0034 | `wc -l` |
| `tests/run-tests.sh` | 2,041 **lines** | `wc -l` |
| Engine suite | 76 **scenarios**, 205 **assertions**, all passing | `./local-CI.sh` prints the tally on every run |
| GUI smoke suite | 283 **assertions**, all passing | as above |
| `bump.py` functional test | 6 **assertions**, all passing | as above |
| Privileged invocations in the engine | **34** | `docs/standards/security.md` §1.2 owns the breakdown, the exclusions, and why `grep` alone gets it wrong |

Three further figures are **not** measurements — each is fixed by a contract with a gate
that fails when the tree stops matching it (`documentation.md` §6b.5), so they do not rot:

| Fixed by | Value |
| --- | --- |
| §3 below, via `docs/reference/marker-protocol.md` §3 | **23** markers |
| §3 below — the engine's command-line surface | **13** flags: `--auth-status`, `--auto-skip-repos`, `--check`, `--grant-auth`, `--help`, `--import-keys`, `--log=`, `--notify`, `--revoke-auth`, `--size=`, `--skip-repo=`, `--steps=`, `--thin-snapshots` |
| `docs/standards/workflow.md` §5.1 — the six version sites | all six read **1.4.0** |

The Python floor and the lint rule set are settled decisions rather than baselines, and
`docs/standards/coding.md` §1 and §2.1 own them — see §6.3.

## 3. What must not change

These four are frozen for the duration. They are what makes a rewrite of this size
provable rather than hopeful — the existing engine and GUI assertions only keep their power
if the thing under test still presents the same face.

1. **The `@@MARKER@@` protocol** — 23 markers, their field order, their meanings.
   Documented in `docs/reference/marker-protocol.md`. **One** deliberate, versioned
   exception, in §5.1 of *this* document: ONEUP-0032's conversion of the `@@HINT@@` and
   `@@REMEDY@@` payloads to codes. The byte counters the engine rewrite makes possible
   (`docs/specs/ONEUP-0054-python-engine.md` §4.3.3) need a marker too, and are deliberately
   **after 2.0**, not a second exception inside it.
2. **The engine's command-line surface** — all 13 flags, their spellings and behaviour.
3. **The five step keys and their order** — `system, flatpak, firmware, orphans, cache`.
4. **The privilege split** — the window never runs as root; the engine is the only thing
   that touches it, and authenticates once per run.

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
update_system.sh   retained through 2.0 as a documented fallback, removed in
                   2.1 — the schedule and the reason are ONEUP-0054 §4.7
```

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

1. **It keeps translation out of the privileged half.** The engine is the part that runs
   as root. Locale files, `gettext`-style catalogue lookup and per-user language settings
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
  versioned change**, with the marker reference, both suites and the GUI updated in
  lockstep. It is a break, done once, with the rewrite already proven — not a break
  smuggled inside one.

Never both at once: a rewrite and a contract change in the same step means a failing test
can't tell you which one broke it.

**How much of this ships in 2.0 — decided by the user, 2026-07-26:** *"I would like to
offer the app in different languages too, however, first point is to get to a working
version first, release and then we can add additional languages."*

So 2.0 ships the **machinery and no second language**:

- every user-facing string wrapped for translation, the catalogue extracted and building,
  and the engine's `@@HINT@@` / `@@REMEDY@@` payloads converted to codes;
- **English only** in the release. No `.ts`/`.qm` locale file for another language is
  written, reviewed or shipped as part of 2.0.

The reason this is the right cut, and not a hedge: wrapping strings is a change to
**every file that shows text**, so it must happen while the modules are being written —
retrofitting it later means touching all of them twice. Translating strings, by contrast,
touches **no code at all**. One is structural and belongs inside the rewrite; the other is
content and can arrive in 2.1 without reopening anything. Shipping the groundwork also
means the first language contributed later is a data file, not a project.

Consequence for §7's gate: "a language is available" is **not** a release condition for
2.0. "Every user-facing string is translatable" is.

**Right-to-left languages are in scope — user's decision, 2026-07-26.** Hebrew and Arabic
read right-to-left, and the whole window must mirror: the toggles sit on the other side,
progress fills the other way, text aligns to the right.

This lands in 2.0 **with the groundwork, not with the languages**, for the same reason the
string-wrapping does — it is structural. A layout built the wrong way must be rebuilt, not
translated. Getting it right while the modules are being written costs almost nothing;
retrofitting it means reopening every one of them.

**Measured at `7a7afc1`, not assumed — the starting position is good, with two known
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
switch by hand, and Qt's mirroring cannot see inside a `paintEvent`. There are **two**
handed computations in it, not one, and `ui-and-accessibility.md` §8.3 is the owner:

- `ToggleSwitch.paintEvent` computes the knob position from the left edge
  (`x = self._margin + self._pos * travel`).
- `ToggleSwitch._paint_state_shape` derives its centre the same way, from `self._margin` on
  one side and `self.width() - self._margin` on the other.

Both must have the direction applied. Fixing only the knob is the trap: it leaves the
colour-independent on/off cue on the wrong side in Hebrew and Arabic, and looks perfectly
correct in English, so nothing you can see will tell you.

Two further consequences, both structural:

- **No user-facing sentence may be built by concatenation.** A sentence glued from
  fragments cannot be reordered by a translator, and in RTL the fragments can render in an
  order nobody intended. Whole sentences with named placeholders, always. The sweep is the
  rule, not its current result: measured at `7a7afc1`, `grep -cE '"\s*\+|\+\s*"' updater.py`
  reported **10** string-concatenation sites — an upper bound, since it counts every `+` on
  a double-quoted string and not only the ones that build a sentence a user reads.
- **RTL is tested, not hoped for.** `tests/gui-smoke.py` gains a pass with the layout
  direction forced right-to-left. Without a test it will regress the first time somebody
  adds a widget, because on an English desktop nobody will ever see it.

### 5.2 Order of work, and why

```
1.4.0 released from main, then main freezes  ← §5.4
        │
        ▼
dependency refresh (0004)      ← first: the Python floor decides what idioms the
        │                        coding standard permits, so it precedes real code
        ▼
GUI split (0034)               ← first substantial work on v2, and alone: it is
        │                        behaviour-preserving, so the existing GUI
        │                        assertions judge it with nothing else in flight
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
| Documentation (this set) | `main` | The standards govern 1.x maintenance too, and `v2` inherits them by merge. Docs are not a release, so they are unaffected by the freeze |
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

Already an acceptance condition of the rewrite: gate G4 requires a full run to raise
**exactly one** password prompt. It gets a diagnosis step in the engine's build plan.
Should the cause turn out to need real design — for example if it forces a change to how
the engine authenticates — it earns a spec at that point.

### 6.3 Dependency refresh (ONEUP-0004)

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

## 7. The gate — what "ready" means

**Nothing ships as 2.0 until it can fully replace v1.** The user's rule, 2026-07-26:
no partial 2.0 releases, no 2.0 beta cut from the branch mid-way. Users stay on frozen
1.4.0 (§5.4) until 2.0.0 arrives complete.

Concretely, all of the following. The **checked by** column is the point: a condition
nothing can check is not a gate.

| # | Condition | Checked by |
| --- | --- | --- |
| **G1** | Engine suite passes with **no assertion changed** — v2 satisfies the tests v1 was measured by | `ONEUP_ENGINE_CMD=… tests/run-tests.sh`, plus `git diff` on the suite showing no assertion touched |
| **G2** | v1 and v2 emit the **same marker stream** under identical mocks | `tests/differential.sh` (`ONEUP-0054` §4.5) |
| **G3** | GUI suite green with the window driving the new engine | `python3 tests/gui-smoke.py` |
| **G4** | A full run raises **exactly one** password prompt | the existing one-prompt scenario |
| **G5** | The engine runs with **PySide6 absent** and imports no Qt — the privilege split, enforced by test | a new scenario with PySide6 hidden from the import path |
| **G6** | A real run on the user's own machine | manual, against the explicit list `ONEUP-0054` §4.5 requires the differential phase to write — the list is a deliverable, not a judgement call |
| **G7** | Every item on the §1 list is complete, its spec's invariants covered by tests | the §1 list is **closed at the start of the engine rewrite** (§5.2's last-but-one stage); anything raised after that is 2.1 by default |
| **G8** | The three packaging paths (RPM, AppImage, OBS) build and launch from the new layout | `./local-CI.sh --full` for the AppImage; an RPM build and an OBS build, each launched once |
| **G9** | Docs current: README, CLAUDE.md, standards, marker reference, CHANGELOG | `tests/docs-check.py`, plus a `/cold-eyes` pass over anything 2.0 edited |
| **G10** | Every user-facing string is translatable, and the GUI suite passes with the layout direction forced **right-to-left** | the RTL half is a GUI-suite pass. The wrapping half has **no automatic check** — `ui-and-accessibility.md`'s own table records the same gap — so it is a review of `oneup/gui/` against `wording-and-translation.md`, and that is the weakest gate here |

G1–G6 are the engine rewrite's and are met **at the switch-over** (`ONEUP-0054` §4.6
stage 7–8), against the frozen contract. G7–G10 are the release's, met at the 2.0.0 tag.

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

## 10. Out of scope for 2.0

- Supporting distributions other than openSUSE, and publishing on Flathub. Not merely out
  of scope for 2.0 — declined outright, with the reasoning in
  `docs/standards/workflow.md` §8.1, which owns it. ONEUP-0071.
- Replacing `zypper`/`flatpak`/`fwupd` call-outs with library bindings — 2.0 still shells
  out; only the shelling-out moves language.
- A plugin or extension system.
- Any change to the five steps or their order.
- **Any actual second language.** The translation *machinery* is in scope (§5.1); a
  translated locale file is not, and arrives after 2.0 is released — user's decision,
  2026-07-26.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-27 | 2 critical, 7 high, 8 medium, 8 low (this document's share of batch 2) | The two criticals were both claims the code and a higher-ranked standard already contradicted: `_paint_state_shape` called "symmetric by construction" when it is handed the same way the knob is (§5.1), and §6.3 presenting the Python floor and the lint configuration as open when `coding.md` §1 and §2.1 had settled both. §2's baseline table was rebuilt in `documentation.md` §6b.4's measured form with the unit named in every row; §5.4 stopped restating the freeze it says it does not restate; §7's gate gained a **checked by** column, which is what exposed that G1 and G2 cannot hold at the 2.0.0 tag once ONEUP-0032 changes the payloads |
