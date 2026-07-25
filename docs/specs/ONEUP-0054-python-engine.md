# ONEUP-0054 — OneUp 2.0: a Python engine

**Status:** Draft — **not yet run through `/cold-eyes`.** No implementation may
start until it has (global rule 14).
**Roadmap:** ONEUP-0054 (📋) — supersedes the ONEUP-0052 investigation, which is
now decided. (ID 0053 is an unused gap in the allocator, not a missing item.)
**Kind:** implement (engine rewrite + the ONEUP-0034 GUI split landing in the same
package)
**Branch:** `v2` — long-lived. `main` keeps shipping 1.x until the gate in §3 is met.

All citations verified against the tree at commit `ea51adc` (`update_system.sh`
1,486 lines, `updater.py` 3,680, `tests/run-tests.sh` 1,952, `tests/gui-smoke.py`
1,317).

## 1. Goal

Replace the Bash engine (`update_system.sh`) with a Python one, keeping the
`@@MARKER@@` protocol and the CLI surface **byte-identical**, so that:

- the existing 197 engine tests prove the rewrite rather than being rewritten for it;
- v1 and v2 can be run side by side and compared, on the same mocks and on a real machine;
- the switch-over is a one-line change in the GUI, reversible by reverting it.

## 2. The decision, honestly

The user's call (2026-07-25), overruling the recommendation recorded in
ONEUP-0052. Their argument is sound and is the reason this is safe: **v1 already
exists and works.** A long-lived branch means the rewrite carries no delivery
risk — if it stalls, 1.x keeps shipping; if it lands, we switch. "It is hard" is
a cost, not an objection.

For the record, the parts of ONEUP-0052 that still stand — a spec that oversells
its own premise is worse than none:

- **Nothing that went wrong in ONEUP-0048 was Bash's fault.** zypper's silence,
  the mirror serving 18 MB at 930 B/s, and sudo's per-parent-pid credential cache
  are all identical from Python — we would still be shelling out to `zypper`. The
  dialog-placement bug (ONEUP-0049) was in the Python half already.
- **Python does not let us kill a root child.** The per-repository budget in
  `refresh_repos` (`update_system.sh:960`) is routed through `sudo timeout`
  because only root can signal a root process. That constraint is the kernel's,
  not Bash's, and it survives the rewrite. What improves is the bookkeeping
  around it (§5.2), not the permission.

So the case rests on §5 and on nothing else. If §5 turns out to be thin in
practice, this branch is allowed to be abandoned — that is what the branch is for.

## 3. The switch-over gate — what "ready" means

The user asked for "when it is ready to replace the current one, we can simply
switch". This is that definition. **All six must hold.** Until then `main` is
untouched.

| # | Gate | How it is checked |
| --- | --- | --- |
| **G1** | v2 passes **197/197** engine tests, with no change to any assertion | `ONEUP_ENGINE_CMD=… tests/run-tests.sh` (§4.3) |
| **G2** | v1 and v2 emit the **same marker stream** under identical mocks | differential harness, §4.4 |
| **G3** | GUI suite green with the GUI driving v2 | `tests/gui-smoke.py`, 277/277 |
| **G4** | A full run still needs **exactly one** password prompt | the existing sudo-model test (§5.1) |
| **G5** | Engine runs with **PySide6 absent** and imports no Qt | new test, §5.5 |
| **G6** | A real run on the user's Tumbleweed box: `--check`, a real update, a rollback offer | manual, with the user |

G2 deserves emphasis: any divergence is either a v2 bug **or** a deliberate
improvement that gets written down here and given its own test. Divergence is
never waved through.

## 4. Architecture

### 4.1 What does not change

- **The privilege split.** The GUI never runs as root. The engine is the only
  thing that touches root, and only through `sudo -A` with `SUDO_ASKPASS` and a
  labelled `SUDO_PROMPT`.
- **The marker protocol is frozen for the duration.** Every marker in
  `CLAUDE.md`'s list keeps its name, field order and semantics. A rewrite that
  also redesigns its own contract cannot be differentially tested, which would
  throw away the only real safety net this project has. Protocol changes come
  *after* the switch, on `main`, one at a time.
- **The CLI surface.** All 13 flags (`update_system.sh:127-139`): `--steps=`,
  `--log=`, `--check`, `--size=`, `--grant-auth`, `--revoke-auth`,
  `--auth-status`, `--import-keys`, `--skip-repo=`, `--auto-skip-repos`,
  `--thin-snapshots`, `--notify`, `--help`.
- **The file contracts.** `run.state` and `stop.request` keep their format,
  location, and `ONEUP_RUN_STATE` / `ONEUP_STOP_FILE` overrides. So do
  `history.json`, `~/.local/state/oneup/logs/`, and the mirror to
  `~/Documents/update-logs/`.
- **Standalone terminal use.** `oneup-engine --steps=system,cache` must be as
  usable in a plain terminal as `./update_system.sh` is today.

### 4.2 Module layout

Eight modules, each tracing to an existing cluster of the Bash file — not a
speculative framework (global rule 2). Line estimates are budgets, not targets.

| Module | Responsibility | Replaces |
| --- | --- | --- |
| `oneup/engine/__main__.py` | flag parsing, run order, per-step dispatch, final summary | the top-level script body, `step_selected` (`:144`), `usage` (`:90`) |
| `markers.py` | every marker emitter — the protocol in **one** place | `marker` (`:201`), `emit_progress` (`:1028`), 59 call sites |
| `privilege.py` | sudo bootstrap, keep-alive, `run_privileged()` | `sudo_init` (`:456`), `sudo_capture` (`:514`), `reap_orphaned_askpass` (`:546`), `cleanup` (`:570`) |
| `proc.py` | streaming child runner: deadline, incremental bytes, cooperative cancel | the ad-hoc pipelines, `progress_filter` (`:1041`), `stop_pending` (`:279`) |
| `runstate.py` | `run.state`, `stop.request`, log paths, history | the logging `exec` block (`:149-200`), state writes |
| `zypper.py` | **pure** output parsers + the repo refresh/skip/disable logic | `to_bytes` (`:1012`), `refresh_repos` (`:960`), `enabled_repo_aliases` (`:911`), `find_failing_repos` (`:923`), `disable_repo` (`:902`), `lock_holder` (`:622`), `release_zypper_lock` (`:602`) |
| `steps.py` | the five steps: `system, flatpak, firmware, orphans, cache` | `begin_step` (`:295`), `end_step` (`:306`), `run_system_upgrade` (`:1079`), the per-step bodies |
| `actions.py` | `--check`, `--size=`, the three auth actions, snapshots | `run_check` (`:323`), `run_size` (`:383`), `grant_auth` (`:676`), `revoke_auth` (`:703`), `auth_status` (`:714`), `thin_snapshots` (`:732`), `build_auth_rule` (`:653`) |

The **GUI** split (ONEUP-0034) lands as `oneup/gui/` in the same package but is
specified separately — it is behaviour-preserving and independent, and must not
be entangled with the engine gate.

### 4.3 Making the test suite engine-agnostic

`tests/run-tests.sh`'s `run_engine` invokes `bash "$ENGINE"`. It gains one
indirection — an `ONEUP_ENGINE_CMD` array override, defaulting to the current
`bash update_system.sh` — so the *same* suite runs either engine. This is the
only change permitted to the test file before G1, and it must be committed to
`main` first and shown to leave 197/197 green there, so the harness change is
proven independent of v2.

### 4.4 The differential harness

New `tests/differential.sh`: for each scenario's mock set, run v1 and v2, capture
only `@@MARKER@@` lines, normalise the fields that legitimately vary (`TIMING`
seconds, log paths, pids, snapshot ids), and `diff`. Green = identical
behaviour. This is the gate that makes the rewrite auditable rather than trusted.

## 5. What Python actually buys

Each claim below is falsifiable and gets a test. This section is the whole
justification for the branch; if these do not materialise, the branch has failed.

### 5.1 The seven-prompt bug class becomes structurally impossible

Today, with no terminal, sudo keys its cached credential to the **parent process
id**, and Bash forks a real subshell for `$(cmd | other)` — so a `sudo` inside
one authenticates again. A full run once needed **seven** prompts. The mitigation
is a discipline (`sudo_capture`, never `sudo` in a subshell) that all **57**
`sudo` call sites must individually observe, backed by a test that models sudo's
cache.

In Python every privileged child is spawned by the engine process itself, so
there is exactly one parent pid for the life of the run. The failure mode cannot
be expressed. This is the single strongest argument for the rewrite: it converts
a rule that must be remembered at 57 sites into a property of the design.

**Test:** the existing one-prompt scenario, unchanged (G4).

### 5.2 Timeouts and cancellation become bookkeeping, not process trickery

Python still cannot signal a root child (§2), so `sudo timeout` / `sudo kill`
remain. What changes is that deadlines, which child owns them, and what to do on
expiry live in one `proc.py` runner with real state, instead of being spread
across command lines. The per-repository budget generalises to any privileged
call for free, and stop checks stop being a `stop_pending &&` sprinkled by hand.

**Test:** a scenario asserting a per-call deadline fires on a step other than the
repo refresh — behaviour v1 does not have.

### 5.3 The metadata fetch becomes measurable

This is a genuinely new capability, not a tidier version of an old one. A
metadata refresh prints undelimited dots **with no line ending**; Bash reads by
lines, so the engine can see nothing and the GUI has to infer liveness from raw
chunk arrival (`updater.py:2954`, stamping `_activity_at` before line splitting).
Python can read bytes as they arrive, so the engine itself can count them and
report actual progress on the phase that caused ONEUP-0048.

**Test:** a mock repo whose refresh dribbles dots produces increasing byte
figures. **Note:** this needs a new marker, so it lands **after** the switch
(§4.1) — the branch may prove it works, but must not ship it before G2.

### 5.4 Parsers become unit-testable in isolation

`to_bytes`, the three zypper progress wordings, the two download-size wordings,
`lr` output, `lock_holder` — today all reachable only through a full engine run.
As pure functions they get table-driven tests, which is the right shape for the
ONEUP-0047 wording canary.

**Test:** a new `tests/test_parsers.py`, table-driven over real captured zypper
output.

### 5.5 Two fragile dependencies disappear

- **`tee -a -p`.** The logging `exec` uses `tee -a -p`
  (`--output-error=warn-nopipe`, probed not assumed, with a `PIPE` trap fallback
  at `update_system.sh:592`) so that a quitting GUI does not SIGPIPE the engine
  mid-transaction. Python writes its own log file and catches
  `BrokenPipeError` on stdout — no external tool, no probe, no fallback trap.
- **The orphan-prone keep-alive.** Today a background loop re-validates sudo and
  must watch the engine's pid to avoid outliving it (`update_system.sh:483`),
  because `cleanup`'s trap cannot run on SIGKILL. In Python it is a daemon
  thread, which the kernel reaps with the process.

**Test:** the existing broken-pipe and orphaned-keep-alive scenarios, unchanged,
plus G5 (engine imports no Qt, runs with PySide6 absent).

## 6. Invariants carried over

These encode bugs that cost real time. Each keeps its existing test; the test is
what carries it across, not this list.

| Invariant | Origin |
| --- | --- |
| A step never claims success, or advises a reboot, it did not earn | the reason the suite exists |
| A failed step is recorded, hints in plain English, and the run **continues** | so cache cleanup still happens |
| `--check` is read-only, needs no root, never calls `dup`/`update` | mock exits 99 if violated |
| Stop is **cooperative**, checked only at safe boundaries — never mid-transaction | ONEUP-0039/0042 |
| A run survives the GUI going away | the `tee -a -p` reasoning, §5.5 |
| Exactly one password prompt per run | §5.1 |
| Nothing the engine spawns outlives it | §5.5 |
| A slow server is never indistinguishable from a hang | ONEUP-0048 |
| Absent tools (`flatpak`, `fwupd`) are skipped **cleanly**, not errored | — |
| Tests never depend on, or damage, machine state | ONEUP-0045/0050 |

## 7. Phases

Each phase ends with `./local-CI.sh` green on the `v2` branch. No phase is
allowed to leave the branch red.

| # | Work | Verify |
| --- | --- | --- |
| **0** | This spec; `/cold-eyes` to convergence | zero substantive findings |
| **1** | `ONEUP_ENGINE_CMD` indirection, committed to `main` | 197/197 on `main`, unchanged |
| **2** | `markers.py`, `runstate.py`, `proc.py`, `privilege.py`; `--help` and `--auth-status` only | `--auth-status` scenarios pass against v2 |
| **3** | `--check` — read-only, no root, so the safest real behaviour to build first | every `--check` scenario green against v2 |
| **4** | `zypper.py` + `--size=`; parser unit tests | §5.4 tests; size scenarios green |
| **5** | The five steps; snapshots, remedies, repo skipping | remaining scenarios → G1 (197/197) |
| **6** | Differential harness | G2 |
| **7** | GUI pointed at v2 behind an env switch | G3, G4, G5 |
| **8** | Real-machine run with the user | G6 |
| **9** | Switch: bump to 2.0.0, packaging, `update_system.sh` retired | six-site lockstep; release |

Phases 2–5 are the bulk. Nothing in 1–8 changes `main`'s behaviour except phase
1, which is a no-op there by construction.

## 8. Packaging and the switch

- **Entry points.** `python3 -m oneup.engine` from a checkout; an `oneup-engine`
  console script when installed. The GUI resolves the engine the same way
  `_find_engine` (`updater.py:106-116`) does now, and the **six** hardcoded
  `p.start("bash", …)` call sites (`updater.py:2119`, `:2449`, `:2534`, `:2722`,
  `:2832`, `:2952`) become one helper. That helper is the switch: an
  `ONEUP_ENGINE=v1|v2` env var during phases 7–8, then a default flip. The
  hardcoded `"bash"` is itself the tell — the GUI currently cannot launch a
  non-Bash engine at all.
- **RPM** (`packaging/rpm/oneup.spec`) ships the package directory instead of one
  script; `BuildArch: noarch` still holds. **AppImage** already bundles Python.
  **OBS** `_service` needs no structural change.
- **`update_system.sh` is retired, not deleted, in phase 9** — kept one release
  as a documented fallback, then removed in 2.1. Users who scripted against it
  get a release's notice.
- **Version.** The switch is a major bump to **2.0.0** (the six lockstep sites),
  which is also the honest signal: the engine anyone shelling out to OneUp
  depended on has changed.

## 9. Risks

| Risk | Mitigation |
| --- | --- |
| The rewrite re-introduces a fixed bug | G1 + G2: no assertion is rewritten, and the marker streams are diffed |
| The branch stalls half-done | `main` ships 1.x throughout; abandoning costs nothing but the branch |
| A behaviour lives only in Bash's semantics and nobody notices | the differential harness is *the* answer; anything it cannot cover is listed in §10 |
| Scope creep — "while we're rewriting, let's also…" | the protocol is frozen (§4.1); §5.3 is explicitly deferred past the switch |
| `updater.py`'s split gets entangled with the engine gate | ONEUP-0034 is specified and merged separately |
| Python startup latency on a short `--check` | measure in phase 3; ~30 ms interpreter start against a multi-second zypper call is expected to be noise, but it is a measurement, not an assumption |

## 10. Open questions

1. **What can the differential harness not see?** Timing-dependent behaviour and
   anything only reachable on a real machine (real sudo, real snapper). Phase 6
   should end with an explicit list of what G6 has to cover by hand.
2. **Do we keep Bash's exit codes?** The GUI takes its verdict from the engine's
   exit code, with `@@DONE@@` as belt-and-braces. Assume yes — identical codes —
   and assert it in the differential harness.
3. **Does `--notify` stay in the engine?** It shells out to `notify-send` from a
   non-root context; it may belong in the GUI. Not decided; keep as-is for G2 and
   revisit after the switch.
