# OneUp 2.0 — programme design

**Status:** Draft
**Kind:** programme-design — the release as a whole. Each item below has (or gets) its
own spec; this document holds only what the items *share* or *contend over*.
**Roadmap:** ONEUP-0057 (the documentation set this design opens)
**Branch:** `v2` (exists at `6ec47ec`, one commit behind `main`). `main` ships **1.4.0**
and then freezes — see §5.4 for what unfreezes it.
**Verified at:** `256d0dc` — every figure in §2 was measured against that tree on
2026-07-26, not recalled. The earlier draft of `ONEUP-0054` cites figures from `ea51adc`;
where the two disagree, this document is current.

**`Draft` means implementation may not start** (`docs/standards/documentation.md` §3). This
document has not been through `/cold-eyes` as a lane of its own — §11 is the record.

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

The list is **open**: more items may be added while 2.0 is being built. Each addition
gets a roadmap bullet and, if it needs design, a spec — and is judged against §7's gate
like everything else.

## 2. Verified baseline — what 1.3.0 actually is

Measured at `256d0dc`, 2026-07-26. These are the numbers 2.0 is measured against.

| Fact | Value |
| --- | --- |
| Version, in lockstep across all six sites | `1.3.0` |
| `update_system.sh` | 1,558 lines |
| `updater.py` | 3,719 lines |
| `tests/run-tests.sh` | 2,041 lines |
| Engine tests | **76 scenarios, 205 assertions**, all passing |
| GUI smoke tests | **283 passing** |
| `bump.py` tests | **6 passing** |
| Markers in the contract | **23** |
| Engine CLI flags | **13** (`--auth-status`, `--auto-skip-repos`, `--check`, `--grant-auth`, `--help`, `--import-keys`, `--log`, `--notify`, `--revoke-auth`, `--size`, `--skip-repo`, `--steps`, `--thin-snapshots`) |
| Privileged invocations in the engine | **34**, counted at `58ea3bc`. `docs/standards/security.md` §1.2 owns the breakdown and the counting rule |
| Lint gates | `shellcheck`, `ruff --select F,B`, `py_compile` — **no lint config file exists** (see §6.3) |
| Python | CI pins `3.13`; the development machine runs 3.13.14 |

## 3. What must not change

These four are frozen for the duration. They are what makes a rewrite of this size
provable rather than hopeful — the existing 205 engine tests and 283 GUI tests only keep
their power if the thing under test still presents the same face.

1. **The `@@MARKER@@` protocol** — 23 markers, their field order, their meanings.
   Documented in `docs/reference/marker-protocol.md`. One deliberate, versioned exception
   in §5.1.
2. **The engine's command-line surface** — all 13 flags, their spellings and behaviour.
3. **The five step keys and their order** — `system, flatpak, firmware, orphans, cache`.
4. **The privilege split** — the window never runs as root; the engine is the only thing
   that touches it, and authenticates once per run.

A change to any of these is a design decision requiring its own spec section, not an
implementation detail.

## 4. Target shape — one `oneup/` package

Both big items restructure code, so they must agree on where it goes. Today the repo has
two source files at the root; 2.0 has one package:

```
oneup/
  __init__.py
  engine/          the Python replacement for update_system.sh
    ...            (module split defined in ONEUP-0054's spec)
  gui/             the split-up updater.py
    ...            (module split defined in ONEUP-0034's spec)
  translations/    oneup_<lang>.ts catalogues (ONEUP-0032)
updater.py         thin entry point — kept at the root, so the desktop file,
                   RPM, AppImage and every user's launcher still work
update_system.sh   retained until the switch-over gate passes, then removed
```

**Packaging is affected, in three places, and they must move together** — this is the
part a restructure most easily forgets:

- `packaging/rpm/oneup.spec` installs exactly two files (`updater.py`,
  `update_system.sh`) into `%{_datadir}/oneup/` and launches the first; a package needs a
  directory install and a `Requires` review.
- `packaging/appimage/build-appimage.sh` bundles `update_system.sh` via `--add-data` and
  points PyInstaller at `updater.py`; a package needs the analysis to follow imports.
- `packaging/obs/_service` rolls a tarball whose layout the spec expects.

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

**Measured at `ff4f4a7`, not assumed — the starting position is unusually good:**

| Thing that normally breaks RTL | Count in `updater.py` |
| --- | --- |
| Directional stylesheet rules (`margin-left`, `padding-right`, …) — Qt does **not** mirror these | **0** |
| Hard-coded `AlignLeft` / `AlignRight` | **0** |
| Existing RTL/locale handling | **0** — nothing to unpick either |

Qt mirrors widget layouts automatically once the application's layout direction is set, so
with none of the usual hand-written obstacles, most of the window should mirror for free.

**The one place it will not**: `ToggleSwitch.paintEvent` in `updater.py` draws the toggle
switch by hand, and its knob position is computed from the left edge (`x = self._margin +
self._pos * travel`). Custom painting is invisible to Qt's mirroring, so in Hebrew or Arabic
the switch would slide the wrong way while everything around it mirrored correctly. The
painted state *shapes* are safe — `_paint_state_shape` draws a centred bar and a circle,
symmetric by construction — so only the position arithmetic needs the direction applied.

Two further consequences, both structural:

- **No user-facing sentence may be built by concatenation.** There are 10 concatenation
  sites in `updater.py` today. A sentence glued from fragments cannot be reordered by a
  translator, and in RTL the fragments can render in an order nobody intended. Whole
  sentences with named placeholders, always.
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
        │                        behaviour-preserving, so the existing 283 GUI
        │                        tests judge it with nothing else in flight
        ▼
interface redesign (0064)      ← after the split, because redesigning a
        │                        3,719-line module while also cutting it up
        │                        makes both changes unreviewable
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
widgets. Doing the split first means the 283 existing GUI tests judge it with nothing
else in flight (it changes no behaviour); doing the redesign next means themes style the
final layout rather than a doomed one; and leaving translation last means the redesign's
new wording is wrapped once, not twice. The order is a consequence of each item's
verification method, not a preference.

### 5.3 Where each item lands

| Item | Branch | Why |
| --- | --- | --- |
| Documentation (this set) | `main` | The standards govern 1.x maintenance too, and `v2` inherits them by merge. Docs are not a release, so they are unaffected by the freeze |
| **Everything in §1** | **`v2`** | Under the freeze (§5.4) `main` takes nothing but qualifying bug fixes, so every 2.0 item — including the GUI split — belongs on the branch |

**The GUI split moved.** An earlier revision of this document put it on `main`, for one
reason only: months of 1.x fixes would otherwise collide with files `v2` had moved.
**The freeze removes that reason** — `main` is now near-idle — so the split returns to
`v2`, where it is the first substantial work (§5.2) and everything on the 2.0 list ships
as 2.0. Decided with the user, 2026-07-26, superseding the same day's earlier call.

### 5.4 The v1 freeze

**`main` freezes at 1.4.0.** First, 1.4.0 ships the work already finished and unreleased
at `256d0dc` — the Stop button, following a run already in progress, making a slow mirror
legible, Wayland dialog placement, and the false "up to date" fix. Freezing before that
release would bury eight completed improvements for the length of the 2.0 build; the
version people are frozen on should be the best one available.

After that, **`main` takes a change only when 1.x cannot do its job.** The user's
definition, 2026-07-26: *if people can no longer use OneUp to install system updates,
Flatpak updates or firmware updates, we fix it and ship a 1.4.x.*

**`docs/standards/workflow.md` §1 is canonical for that rule** — the two readings inside
it, the openSUSE-changes-underneath trigger, and what does not qualify. It is a standard,
so it outranks this document (`docs/standards/documentation.md` §1.1), and it is where
somebody deciding *which branch does this go on* will look. Not restated here, so the two
cannot drift.

**Merge direction:** `main` is merged into `v2` after any 1.4.x release, never the
reverse. `v2` is not rebased — it is long-lived and shared with the origin remote, so
rewriting its history would break any clone.

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

Governed by `docs/standards/dependencies.md`. **The Python ledger row is gone** — a sweep
on 2026-07-26 found its premise false: PySide6 ships stable-ABI wheels
(`cp310-abi3`, `requires_python <3.15,>=3.10`), so 3.14 was never blocked and nothing
needed waiting for. The one-line bump of `release.yml`'s `python-version` 3.13 → 3.14
belongs to this item, on `v2`; `main` is frozen and does not take it. The CI actions
(`checkout@v7`, `setup-python@v7`, `action-gh-release@v3`) were all verified current in the
same sweep. The `ubuntu-22.04` runner stays pinned — that row is a real, deliberate glibc
compatibility floor, not a suspicion.

Two decisions belong to the coding standard rather than a spec: the
**minimum Python version** OneUp supports — the binding constraint is whatever the
oldest supported openSUSE Leap ships, which must be *looked up*, not assumed — and
whether to add a lint configuration file — there is none today, so
`ruff` runs on defaults and every developer's local run can differ from CI's.

## 7. The gate — what "ready" means

**Nothing ships as 2.0 until it can fully replace v1.** The user's rule, 2026-07-26:
no partial 2.0 releases, no 2.0 beta cut from the branch mid-way. Users stay on frozen
1.4.0 (§5.4) until 2.0.0 arrives complete.

Concretely, all of the following:

| # | Condition |
| --- | --- |
| **G1** | Engine suite passes with **no assertion changed** — v2 satisfies the tests v1 was measured by |
| **G2** | v1 and v2 emit the **same marker stream** under identical mocks (differential harness) |
| **G3** | GUI suite green with the window driving the new engine |
| **G4** | A full run raises **exactly one** password prompt |
| **G5** | The engine runs with **PySide6 absent** and imports no Qt — the privilege split, enforced by test |
| **G6** | A real run on the user's own machine |
| **G7** | Every item in §1 is complete, its spec's invariants covered by tests |
| **G8** | The three packaging paths (RPM, AppImage, OBS) build and launch from the new layout |
| **G9** | Docs current: README, CLAUDE.md, standards, marker reference, CHANGELOG |
| **G10** | Every user-facing string is translatable, and the GUI suite passes with the layout direction forced **right-to-left** — the machinery works even though no second language ships (§5.1) |

G1–G6 come from the ONEUP-0054 draft and are its gate; G7–G10 are the release's.

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
- **Scope growth.** The item list is open (§1), and an open list on a long branch is how
  releases slip forever. Each addition is weighed against G7 — "does this have to be in
  2.0, or can it be 2.1?"

## 9. What governs what

| Document | Governs |
| --- | --- |
| `docs/standards/*.md` | Standing rules — code, security, docs, files, tests, UI, wording, workflow, dependencies |
| `docs/reference/marker-protocol.md` | The engine↔window contract frozen by §3 |
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
| — | — | *not yet run* | Implementation is blocked until a pass returns clean |
