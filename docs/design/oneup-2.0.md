# OneUp 2.0 — programme design

**Status:** Draft — **not yet run through `/cold-eyes`.** No implementation may start
until it has (global rule 14).
**Kind:** programme design — the release as a whole. Each item below has (or gets) its
own spec; this document holds only what the items *share* or *contend over*.
**Branch:** `v2` (exists at `6ec47ec`, one commit behind `main`). `main` keeps shipping
1.x throughout.
**Baseline:** every figure in §2 was measured against commit `256d0dc` on 2026-07-26,
not recalled. The earlier draft of `ONEUP-0054` cites figures from `ea51adc`; where the
two disagree, this document is current.

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
| **ONEUP-0027** | Selectable colour themes beyond follow-the-desktop | `docs/specs/ONEUP-0027-themes.md` *(to be written)* |
| **ONEUP-0032** | Wrap user-facing text for translation | `docs/specs/ONEUP-0032-i18n.md` *(to be written)* |
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
| Engine tests | **205 passing** |
| GUI smoke tests | **283 passing** |
| `bump.py` tests | **6 passing** |
| Markers in the contract | **23** |
| Engine CLI flags | **13** (`--auth-status`, `--auto-skip-repos`, `--check`, `--grant-auth`, `--help`, `--import-keys`, `--log`, `--notify`, `--revoke-auth`, `--size`, `--skip-repo`, `--steps`, `--thin-snapshots`) |
| Privileged invocations in the engine | 34 at command position, of which 21 go through `sudo_capture` |
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

### 5.2 Order of work, and why

```
dependency refresh (0004)      ← first: the Python floor decides what idioms the
        │                        coding standard permits, so it precedes real code
        ▼
GUI split (0034) — on main     ← §5.3
        │
        ├──────────────► themes (0027)   needs the split's theme module
        │
        ▼
engine rewrite (0054) — on v2  ← the long pole; gate in §7
        │
        ▼
translation (0032)             ← last: wrapping strings before the split means
                                 wrapping them twice, and §5.1 requires the
                                 rewrite to be proven before the contract moves
```

The double-password investigation (0044) runs alongside the rewrite; see §6.2.

### 5.3 Where each item lands

| Item | Branch | Why |
| --- | --- | --- |
| Documentation (this set) | `main` | The standards govern 1.x work too |
| Dependency refresh (0004) | `main` | Small, and 1.x benefits |
| **GUI split (0034)** | **`main`** | It changes no behaviour, so it can ship in a 1.x release. Landing it on main first means `v2` branches from already-tidy code — otherwise every 1.x fix for months collides with files `v2` has moved. Decided with the user, 2026-07-26. |
| Engine rewrite (0054) | `v2` | The only item that can't ship incrementally |
| Themes (0027) | `v2` | User-visible; held for the 2.0 release |
| Translation (0032) | `v2` | Requires the contract change of §5.1 |

Landing the split on `main` means one item of the 2.0 list reaches users early — as
invisible plumbing, under a 1.x version number. That is a deliberate trade for mergeable
branches, not a loosening of §7.

### 5.4 Keeping 1.x alive without stranding `v2`

`main` continues to take bug fixes and ship 1.x releases while 2.0 is built. To stop the
branch drifting: **`main` is merged into `v2` after every 1.x release, and never the
reverse.** `v2` is not rebased — it is long-lived and (once work starts) shared with the
origin remote, so rewriting its history would break any clone.

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

Governed by `docs/standards/dependencies.md`, which already carries the ledger row and
its re-test cue. Two decisions belong to the coding standard rather than a spec: the
**minimum Python version** OneUp supports — the binding constraint is whatever the
oldest supported openSUSE Leap ships, which must be *looked up*, not assumed — and
whether to add a lint configuration file — there is none today, so
`ruff` runs on defaults and every developer's local run can differ from CI's.

## 7. The gate — what "ready" means

**Nothing ships as 2.0 until it can fully replace v1.** The user's rule, 2026-07-26:
no partial 2.0 releases, no 2.0 beta cut from the branch mid-way. `main` ships 1.x, and
one day 2.0.0 arrives complete.

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

G1–G6 come from the ONEUP-0054 draft and are its gate; G7–G9 are the release's.

## 8. Risks, and permission to fail

- **The branch may be abandoned.** That is what a side branch is for. If the rewrite
  stalls, 1.x keeps shipping and nothing is lost but the branch. This is stated so that
  abandoning it stays an available, unembarrassing option.
- **Long-branch drift** — mitigated by §5.3 (split lands on main) and §5.4 (merge after
  every release), not by hope.
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

- Supporting distributions other than openSUSE.
- Replacing `zypper`/`flatpak`/`fwupd` call-outs with library bindings — 2.0 still shells
  out; only the shelling-out moves language.
- A plugin or extension system.
- Any change to the five steps or their order.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| — | — | *not yet run* | Implementation is blocked until a pass returns clean |
