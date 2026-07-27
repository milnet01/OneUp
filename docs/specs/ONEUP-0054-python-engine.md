# ONEUP-0054 — a Python engine

**Status:** Draft
**Kind:** implement
**Roadmap:** ONEUP-0054
**Branch:** v2
**Verified at:** `7a7afc1` — every figure below was measured against this tree, not recalled.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** the half of OneUp that actually installs the updates is rewritten from
Bash into Python, saying exactly the same things and taking exactly the same flags, so the
tests that pass today are what prove the new one.

**The programme design owns everything 2.0's items share** — the `oneup/` package layout
(`docs/design/oneup-2.0.md` §4), the decision that the engine emits codes and the window
does the wording (§5.1), the order the items are built in (§5.2), the `main` freeze (§5.4),
and the release gate (§7). This spec settles only what is particular to the engine, and
points at the design for the rest so the two cannot drift.

## 1. Goal

`update_system.sh` is replaced by a Python package under `oneup/engine/`. The
`@@MARKER@@` protocol, the command-line flags, the exit codes and the state files stay
**byte-identical**, so the existing engine test suite proves the rewrite instead of being
rewritten for it. v1 and v2 can be run side by side and compared, and the switch-over is a
one-line change in the window, reversible by reverting it.

## 2. Background

### 2.1 What the Bash engine costs today

Three costs, each measured rather than felt:

- **Every privileged call has to individually observe a rule.** With no terminal, `sudo`
  keys its cached credential to the **parent process id**, and Bash forks a real subshell
  for `$(cmd | other)` — so a `sudo` inside one authenticates again. A full run once
  needed **seven** password prompts. The fix was a discipline, not a mechanism:
  `sudo_capture` writes to a temporary file and reads it back outside any substitution,
  and every privileged call site has to remember to use it.

  The engine had **34** privileged call sites when this was written.
  `docs/standards/security.md` §1.2 owns that figure — the split behind it, what the count
  excludes, and why `grep` alone gets it wrong. It is cited rather than re-derived here on
  purpose: the earlier arrangement, where two documents each stated the split, is what
  produced the contradiction the first review of that standard had to unpick.

- **The engine cannot see a phase that prints no lines.** A zypper metadata refresh emits
  undelimited dots with **no line ending**. Bash reads by lines, so during that phase the
  engine sees nothing at all and has nothing to report. This is what made ONEUP-0048
  possible: one mirror served a repository index at under a kilobyte a second, and the app
  showed no sign of life for minutes.

- **Two external dependencies hold the run together.** The logging `exec` pipes stdout
  through `tee` with `-a -p` (`--output-error=warn-nopipe`) so that a quitting window
  cannot `SIGPIPE` the engine mid-transaction; `-p` is probed rather than assumed, with a
  `trap 'exit 141' PIPE` fallback for a `tee` that lacks it. Separately, a backgrounded
  keep-alive loop re-validates the sudo credential and must poll `kill -0` on the engine's
  own pid to avoid outliving it, because `cleanup`'s trap cannot run on `SIGKILL`.
  Keep-alives were once found still running forty minutes after their run was killed.

### 2.2 What Bash is not to blame for

A spec that oversells its own premise is worse than none. The parts of the ONEUP-0052
investigation that still stand:

- **Nothing that went wrong in ONEUP-0048 was Bash's fault.** zypper's silence, the slow
  mirror, and sudo's per-parent-pid credential cache are all identical from Python — we
  would still be shelling out to `zypper`. The dialog-placement bug (ONEUP-0049) was in
  the Python half already.
- **Python cannot kill a root child either.** The per-repository budget in `refresh_repos`
  is routed through `sudo timeout` because only root can signal a root process. That
  constraint is the kernel's, not Bash's, and it survives the rewrite. What improves is
  the bookkeeping around it (§4.3.2), not the permission.

So the case rests on §4.3 and on nothing else. If §4.3 turns out to be thin in practice,
this branch is allowed to be abandoned — that is what the branch is for.

## 3. Scope decisions (agreed with the user)

| Decision | Who, when | Consequence |
| --- | --- | --- |
| Rewrite the engine in Python rather than keep hardening Bash | the user, 2026-07-25, overruling the ONEUP-0052 recommendation | this spec exists |
| Build it on a long-lived `v2` branch | the user, 2026-07-25 | no delivery risk: if it stalls, frozen 1.4.0 keeps shipping |
| The marker protocol is frozen for the duration | the user, 2026-07-25 | §4.1; the differential harness is only possible because of it |
| The GUI split (ONEUP-0034) is a **separate item** with its own spec | the user, 2026-07-26 | §3.1 |
| `--notify` stays in the engine for now | the user, 2026-07-26 | §10 |

**The user's argument for the branch, which is the reason this is safe:** v1 already exists
and works. *"It is hard"* is a cost, not an objection.

### 3.1 The relationship to the GUI split

`ONEUP-0034` splits `updater.py` into `oneup/gui/`. It shares this rewrite's **package**
(`docs/design/oneup-2.0.md` §4) and its **branch** (§5.3), and it lands **first** (§5.2) —
but it is a separate roadmap item with a separate spec, and it is **not** part of this
spec's gate. It is behaviour-preserving where this is not, so entangling the two would mean
a failing test could not say which change broke it.

An earlier draft of this document said the split lands "in the same package" in a way that
read as one item. It does share the package. It is not one item.

## 4. Design

### 4.1 What does not change

- **The privilege split.** The window never runs as root. The engine is the only thing
  that touches root, and only through `sudo -A` with `SUDO_ASKPASS` and a labelled
  `SUDO_PROMPT`. `docs/standards/security.md` owns this boundary.
- **The marker protocol.** Every marker in `docs/reference/marker-protocol.md` §3 keeps
  its name, field order and semantics. A rewrite that also redesigns its own contract
  cannot be differentially tested, which would throw away the only real safety net this
  project has. The reference's §5.1 records the freeze; protocol changes come *after* the
  switch.
- **The command-line surface.** All thirteen flags the argument loop in `update_system.sh`
  accepts: `--steps=`, `--log=`, `--check`, `--size=`, `--grant-auth`, `--revoke-auth`,
  `--auth-status`, `--import-keys`, `--skip-repo=`, `--auto-skip-repos`,
  `--thin-snapshots`, `--notify`, `--help` — and `-h`, which the same arm accepts as an
  alias for `--help`. `docs/design/oneup-2.0.md` §3 froze this list.
- **The exit codes.** The window takes its verdict from the engine's exit code —
  `Updater.on_finished` sets `ok = exit_code == 0`, with `@@DONE@@` as belt and braces. The
  codes stay identical, and the differential harness asserts it (§4.5).
- **The two state files.** `run.state` and `stop.request` keep their location and their
  `ONEUP_RUN_STATE` / `ONEUP_STOP_FILE` overrides.
  `docs/reference/marker-protocol.md` §8 names them and their purpose, and says plainly that
  their **field layout is pinned nowhere and that this spec has to pin it**. §4.1.1 does.
- **The engine's log directory.** The engine writes each run's log to
  `~/Documents/update-logs/`, where a user can find it. The *directory* has no override;
  the individual run's log file does, via `--log=FILE`, which every test scenario uses.
  `docs/standards/files-and-naming.md` §7 Trap 2 (ONEUP-0058) obliges the rewrite to stop
  creating that directory on the real machine during tests — either honour an override or
  create it only when about to write.
- **Standalone terminal use.** `oneup-engine --steps=system,cache` must be as usable in a
  plain terminal as `./update_system.sh` is today.

**What is *not* an engine contract, though an earlier draft said so:** `history.json` and
`~/.local/state/oneup/logs/` belong to the **window** — `updater.py`'s `HISTORY` and
`LOG_DIR` constants. The engine never touches either. `docs/standards/files-and-naming.md`
§5.1 is the owner of the full path table, and its §7 "Trap 1" is the one this rewrite must
act on: `LOG_DIR` names two different directories in the two programs, which is harmless
only while they are in different languages. Give them distinct names — `USER_LOG_DIR` and
`STATE_LOG_DIR`, or equivalent — before either is imported anywhere.

### 4.1.1 The state-file layout, written down

`docs/reference/marker-protocol.md` §8 records that this layout is pinned nowhere and that
the Python engine "must reproduce it exactly or run-following breaks silently". Measured
from `update_system.sh`'s `RUN_STATE_FILE` writer and `updater.py`'s `_read_run_state` at
`7a7afc1`:

**`run.state`** — plain text, four lines, `\n`-terminated, written in one `printf` when the
run commits and removed by `cleanup` on exit. Only the process that wrote it clears it
(`RUN_STATE_OWNED`), so a `--check` or `--size` run cannot erase a real run's record.

| Line | Field | Example |
| --- | --- | --- |
| 1 | the engine's pid | `48213` |
| 2 | the absolute path of this run's log | `/home/u/Documents/update-logs/2026-07-27_0914.log` |
| 3 | the selected steps, comma-separated, in run order | `system,flatpak,firmware,orphans,cache` |
| 4 | the epoch second the run committed | `1785132758` |

**The window reads the first three and ignores the fourth**, and treats fewer than three
lines, or a non-numeric first line, as no run at all. Lines 1–3 therefore may not be
reordered or dropped. Line 4 is written but unread today; v2 keeps writing it, because a
field nothing reads costs nothing and removing it would silently narrow the file.

**Where the two files live is a separate open question.** They sit under
`~/.local/state/oneup/` and ignore `XDG_STATE_HOME`;
`docs/standards/files-and-naming.md` §5.2 says 2.0 should honour it, and ONEUP-0059 is the
item. That is a *path* change, not a layout change, so it does not touch this contract —
but it must be settled with ONEUP-0059 rather than assumed either way here.

**`stop.request`** — the *window* creates it; the engine only ever reads it, at a safe
boundary. **Its contents are not part of the contract and the engine must not parse them.**
What the engine tests is existence plus modification time: a request whose mtime is not
newer than `run.state`'s is a leftover from a previous run and is ignored. v2 must keep
that comparison, because deleting a stale request at start-up instead would race a stop
clicked in the same moment.

### 4.2 Module layout

Nine modules, each tracing to an existing cluster of the Bash file rather than to a
speculative framework. `docs/standards/coding.md` §4 sets the module-size ceiling, and
`docs/standards/files-and-naming.md` §4.1 sets the naming and one-responsibility rules the
split must obey. Paths are relative to `oneup/engine/`.

| Module | Responsibility | Replaces |
| --- | --- | --- |
| `__main__.py` | drive one run: parse the flags, dispatch the steps in order, summarise | the top-level script body, `step_selected`, `usage` |
| `markers.py` | every marker emitter — the protocol in **one** place | `marker`, `emit_progress`, and every `marker NAME` call site |
| `privilege.py` | become root once, and stay root safely for the run | `sudo_init`, `sudo_capture`, `reap_orphaned_askpass`, `cleanup` |
| `proc.py` | run a child process and stream it — deadline, incremental bytes, cooperative cancel | the ad-hoc pipelines, `progress_filter`, `stop_pending` |
| `runstate.py` | own the two state files and the log paths (§4.1.1) | the logging `exec` preamble and the state writes around it |
| `parsers.py` | turn zypper's text into values — **pure functions, no I/O, no privilege** | `to_bytes`, `lock_holder`'s parsing, the progress and download-size wordings, `lr` output |
| `repos.py` | refresh, skip and disable repositories | `refresh_repos`, `enabled_repo_aliases`, `find_failing_repos`, `disable_repo`, `release_zypper_lock` |
| `steps.py` | run the five steps: `system, flatpak, firmware, orphans, cache` | `begin_step`, `end_step`, `run_system_upgrade`, the per-step bodies |
| `actions.py` | the runs that are not an update: `--check`, `--size=`, the three auth actions, snapshots | `run_check`, `run_size`, `grant_auth`, `revoke_auth`, `auth_status`, `thin_snapshots`, `build_auth_rule` |

**`parsers.py` and `repos.py` are deliberately two modules, not one.** An earlier draft had
a single `zypper.py` holding "pure parsers **plus** the repo refresh/skip/disable logic" —
which `files-and-naming.md` §4.1 rule 4 rejects on sight, and which would defeat §4.3.4:
importing the parsers to table-test them would drag in the code that calls `sudo`.

### 4.3 What the move to Python buys

Each claim is falsifiable and names the test that would falsify it. This section is the
whole justification for the branch — so it matters that **three of the four are demonstrated
by the gate and the fourth is not**: §4.3.3 is deliberately deferred past the switch, which
means the branch may prove it works but 2.0 does not ship it. Weigh the case on §4.3.1,
§4.3.2 and §4.3.5.

#### 4.3.1 The seven-prompt bug class becomes structurally impossible

In Python every privileged child is spawned by the engine process itself, so there is
exactly one parent pid for the life of the run, and sudo's cached credential is keyed to
it. The failure mode described in §2.1 cannot be expressed. This is the single strongest
argument for the rewrite: it converts a rule that must be remembered at every privileged
call site into a property of the design.

*Test:* the existing scenario *"a full run asks for the password exactly once (no per-step
prompts)"*, unchanged — gate G4.

#### 4.3.2 Timeouts and cancellation become bookkeeping, not process trickery

Python still cannot signal a root child (§2.2), so `sudo timeout` and `sudo kill` remain.
What changes is that deadlines, which child owns them, and what to do on expiry live in one
`proc.py` runner with real state, instead of being spread across command lines. The
per-repository budget generalises to any privileged call for free, and stop checks stop
being a `stop_pending &&` sprinkled by hand.

*Test:* a new scenario asserting a per-call deadline fires on a step other than the repo
refresh — behaviour v1 does not have.

#### 4.3.3 The metadata fetch becomes measurable

This is a genuinely new capability, not a tidier version of an old one. Python can read
bytes as they arrive, so the engine itself can count them and report real progress on the
phase that caused ONEUP-0048 — the one that today prints dots with no line ending (§2.1).
Today the window can only infer liveness from raw chunk arrival: `Updater.on_output` stamps
`_activity_at` on the chunk **before** splitting it into lines, precisely so that a stream
of dots still counts as alive.

*Test:* a mock repository whose refresh dribbles dots produces increasing byte figures.

**This lands after the switch, not before it.** It needs a new marker, and §4.1 freezes the
protocol until gate G2 has passed. The branch may prove it works; it must not ship it
early.

#### 4.3.4 Parsers become unit-testable in isolation

`to_bytes`, the zypper progress wordings, the two download-size wordings, `lr` output and
`lock_holder` are today reachable only through a full engine run. As pure functions they
get table-driven tests, which is the right shape for the stale-parser canary — the scenario
*"a transaction with no recognisable progress lines says so (stale-parser canary)"*, which exists to fire when
zypper changes its wording under us.

*Test:* a new `tests/test_parsers.py`, table-driven over real captured zypper output.

#### 4.3.5 Two fragile dependencies disappear

- **`tee -a -p`.** Python writes its own log file and catches `BrokenPipeError` on stdout.
  No external tool, no probe, no fallback trap (§2.1).
- **The orphan-prone keep-alive.** In Python it is a daemon thread, which the kernel reaps
  with the process. No pid polling, and nothing left behind on `SIGKILL`.

*Test:* the existing scenario *"a run survives the GUI going away and still finishes (broken
stdout pipe)"*, unchanged.

**The keep-alive's scenario is the one place G1's "no assertion changed" cannot hold, and
saying so is the point.** *"the keep-alive exits on its own once the engine is gone
(SIGKILL-proof)"* does not run the engine at all: it `sed`s the `setsid bash -c` block out
of `update_system.sh`, substitutes a shorter sleep, and executes that Bash fragment, so what
it asserts is the `kill -0` guard **verbatim** — the exact mechanism this section proposes to
delete. Against a Python engine it fails at its first step, on "could not find the keep-alive
loop in the engine".

So it is **replaced, not carried**, and the replacement is a deliverable of §4.6 stage 2:
start a run, `SIGKILL` the engine, and assert no descendant of it survives — testing the
property (nothing outlives the engine, INV-7) instead of the Bash implementation of it. This
is the single documented exception to G1, it is recorded here rather than discovered during
the rewrite, and the differential harness (§4.5) is what covers the behaviour meanwhile.

### 4.4 Making the test suite engine-agnostic

`run_engine` in `tests/run-tests.sh` invokes `bash "$ENGINE"`. It gains one indirection —
an `ONEUP_ENGINE_CMD` array override, defaulting to the current `bash update_system.sh` —
so the *same* suite runs either engine.

**`run_engine` is not the only place the suite reaches the engine, and the other two are
what make this less trivial than it sounds.** All three must be handled together:

| Call site | What it does | What it needs |
| --- | --- | --- |
| `run_engine` | `bash "$ENGINE" "$@"` — almost every scenario | the `ONEUP_ENGINE_CMD` override |
| the broken-pipe scenario (INV-5) | invokes `bash "$ENGINE" --steps=system` directly, on purpose, so it can close the pipe on it | the same override, applied by hand at that site |
| the SIGKILL keep-alive scenario (INV-7) | reads `$ENGINE` as a **file** and executes a fragment of its Bash | nothing — it is replaced outright, §4.3.5 |

Beyond those, this is the only change permitted to the test file before G1. It lands on
`main` first and is shown to leave the suite green there, so the harness change is proven
independent of `v2`. `main` is frozen — `docs/standards/workflow.md` §1.2 is where that
exception is defined, and this change is the reason it exists.

### 4.5 The differential harness

New `tests/differential.sh`: for each scenario's mock set, run v1 and v2, capture only
`@@MARKER@@` lines, normalise the fields that legitimately vary (`TIMING` seconds, log
paths, pids, snapshot ids), and `diff` the rest along with the exit code. Green means
identical behaviour.

This is what makes the rewrite auditable rather than trusted, and it is the reason the
protocol is frozen. **Any divergence is either a v2 bug or a deliberate improvement that
gets written down here and given its own test.** Divergence is never waved through.

**What it cannot see, stated so that nobody assumes otherwise:** timing-dependent behaviour,
and anything reachable only on a real machine — real sudo, real snapper, real repositories.
Gate G6 is what covers that, and the phase that builds the harness ends by writing the
explicit list of what G6 has to check by hand.

### 4.6 The order the gate is met in

Build steps belong in a plan, written when the item starts
(`docs/standards/documentation.md` §2). This is the ordering the plan must respect, because
each stage is what makes the next one safe to attempt.

| # | Work | What it satisfies |
| --- | --- | --- |
| 1 | `ONEUP_ENGINE_CMD` indirection at all three call sites, on `main` | §4.4 — the suite still green on `main`, unchanged |
| 2 | `markers.py`, `runstate.py`, `proc.py`, `privilege.py`; `--help` and `--auth-status` only. Plus the two new scenarios this stage owes: the replacement keep-alive test (§4.3.5) and the absent-tool skip test (INV-9) | the `--auth-status` scenarios pass against v2; INV-7 and INV-9 stop being untested |
| 3 | `--check` — read-only and needs no root, so the safest real behaviour to build first | every `--check` scenario green against v2 |
| 4 | `parsers.py`, `repos.py` and `--size=`; parser unit tests | §4.3.4; the `--size` scenarios green |
| 5 | The five steps; snapshots, remedies, repo skipping | the remaining scenarios → G1 |
| 6 | The differential harness | G2, and the list of what it cannot see |
| 7 | The window pointed at v2 behind an environment switch | G3, G4, G5 |
| 8 | A real run on the user's machine | G6 |
| 9 | The switch-over: the window defaults to v2, packaging follows the package layout, `update_system.sh` becomes the documented fallback | §4.7 |

Each stage ends with `./local-CI.sh` green on `v2`. Nothing in stages 1–8 changes `main`'s
behaviour except stage 1, which is a no-op there.

**Stage 9 is not the 2.0.0 release.** It is where this item's gate (G1–G6) is met and the
engine changes hands. ONEUP-0032 still follows it (`docs/design/oneup-2.0.md` §5.2), and
2.0.0 ships only when the whole of §7 there is satisfied — which is also why G1 and G2 are
measured **at stage 9** and not re-run at the tag: ONEUP-0032 changes the marker payloads and
the assertions that read them, in one versioned change, by design.

### 4.7 Packaging and the switch

- **Entry points.** `python3 -m oneup.engine` from a checkout; an `oneup-engine` console
  script when installed. The window's six hardcoded `p.start("bash", …)` call sites become
  one helper, and that helper *is* the switch: an `ONEUP_ENGINE=v1|v2` environment variable
  during stages 7–8, then a default flip. The hardcoded `"bash"` is itself the tell — the
  window currently cannot launch a non-Bash engine at all.
- **Resolving the engine.** The helper replaces `_find_engine`, and must **not** reproduce
  it: `docs/standards/files-and-naming.md` §7 Trap 4 records that it returns its first
  candidate path whether or not the file exists, so a packaging mistake surfaces as "the Run
  button did nothing". The 2.0 resolver says which paths it tried.
- **The three packaging paths** — what each does today and what each therefore needs — are
  `docs/design/oneup-2.0.md` §4, which owns them because ONEUP-0034 must move with them.
  Nothing engine-specific to add beyond the entry points above.
- **`update_system.sh` is retired, not deleted**, in stage 9 — kept through 2.0 as a
  documented fallback, then removed in 2.1, so anyone who scripted against it gets a
  release's notice. Confirmed with the user, 2026-07-27; `docs/design/oneup-2.0.md` §4 and
  `docs/standards/files-and-naming.md` §4 record the same schedule.

## 5. Correctness invariants

These encode bugs that cost real time. The **test** is what carries each across the
rewrite; this list is the index, not the mechanism. Scenario names are the ones printed by
`tests/run-tests.sh`.

- **INV-1** A step never claims success, or advises a reboot, that it did not earn.
  *Test:* the scenarios *"up-to-date system does NOT advise a reboot (the original bug)"*,
  *"a FAILED system step does not claim changes / reboot, and gives a hint"* and *"a FAILED
  firmware update is reported as fail, not success, and does NOT reboot"*.

- **INV-2** A failed step is recorded, emits a plain-English hint, and the run continues to
  the next step — so cache cleanup still happens after a failed upgrade.
  *Test:* *"a failed early step still lets a later step run; the run ends in errors"*.

- **INV-3** `--check` is read-only: it needs no root, and never calls `dup` or `update`.
  *Test:* *"--check reports counts read-only and never installs"* — the mock exits 99 if
  violated — and *"--check performs NO privileged auth (never invokes sudo)"*.

- **INV-4** Stopping is **cooperative**, checked only at safe boundaries, never mid-
  transaction. `docs/standards/security.md` §6 owns the rule and why signalling is banned.
  *Test:* *"a stop DURING the run lets the running transaction finish, then stops"* and
  *"Stop is honoured DURING the refresh, before anything is installed"*.

- **INV-5** A run survives the window going away, and still finishes.
  *Test:* *"a run survives the GUI going away and still finishes (broken stdout pipe)"*.

- **INV-6** A full run asks for the password exactly once.
  *Test:* *"a full run asks for the password exactly once (no per-step prompts)"*.

- **INV-7** Nothing the engine spawns outlives it.
  *Test:* *"the sudo keep-alive leaves no orphaned process when a run ends"* and *"an
  orphaned password dialog is reaped when the run ends"*, both unchanged, plus the
  replacement for *"the keep-alive exits on its own once the engine is gone
  (SIGKILL-proof)"* — which asserts the Bash implementation rather than the property and so
  cannot survive the rewrite (§4.3.5). Stage 2 owes the replacement.

- **INV-8** A slow server is never indistinguishable from a hang.
  *Test:* *"a source too slow to refresh is bounded, named, and offers the skip"* and *"the
  download reports bytes and a total, so a slow one is legible (ONEUP-0048)"*.

- **INV-9** A step whose tool is absent is skipped **cleanly**, never errored. The engine
  guards the Flatpak and firmware steps with `command -v flatpak` and `command -v fwupdmgr`.
  *Test:* a new scenario that runs a full pass with `flatpak` and `fwupdmgr` absent from
  `PATH` and asserts each step ends skipped, not failed, and that the run's overall verdict
  is unaffected. **It does not exist yet** — no scenario in `tests/run-tests.sh` arranges an
  absent tool, so this path has never been exercised in either engine. ONEUP-0070 is the
  item, §4.6 stage 2 is where it lands, and it is a condition of G1: v2 must not inherit the
  gap, and v1 should not have had it.

- **INV-10** v2 emits the same marker stream and the same exit code as v1, under identical
  mocks.
  *Test:* `tests/differential.sh` (§4.5) — gate G2. New with this work.

- **INV-11** The engine imports no Qt and runs with PySide6 absent. This is the privilege
  split made testable: the half that becomes root cannot depend on the half that draws
  windows.
  *Test:* a new scenario that runs the engine with PySide6 hidden from the import path —
  gate G5. New with this work.

**Not an invariant of this spec, though an earlier draft listed it:** *tests never depend
on, or damage, machine state*. That is a rule about the suite, and
`docs/standards/testing.md` §2 owns it. It binds the rewrite because the rewrite's tests are
tests, not because the engine enforces it.

## 6. Failure modes

| If this breaks | What happens | What limits the damage |
| --- | --- | --- |
| The rewrite re-introduces a fixed bug | a shipped regression | G1 plus G2: no assertion is rewritten, and the marker streams are diffed |
| A behaviour lives only in Bash's semantics and nobody notices | v2 silently differs | the differential harness is *the* answer; what it cannot cover is listed in §4.5 and lands on G6 |
| The branch stalls half-done | 2.0 never arrives | `main` ships frozen 1.4.0 throughout; abandoning costs nothing but the branch |
| Scope creep — *"while we're rewriting, let's also…"* | the gate recedes | the protocol is frozen (§4.1) and §4.3.3 is explicitly deferred past the switch |
| The GUI split gets entangled with this gate | a failing test cannot say which change broke it | ONEUP-0034 is a separate item, specified and merged separately (§3.1) |
| Python's start-up latency shows on a short `--check` | the check feels slower | measured in stage 3, not assumed. An interpreter start against a multi-second zypper call is expected to be noise — but it is a measurement |
| A privileged call ends up inside a subshell equivalent | the seven-prompt bug returns | it cannot: §4.3.1 removes the mechanism. G4 still asserts it |

## 7. Tests

**The gate is `docs/design/oneup-2.0.md` §7**, which holds the conditions for all of 2.0.
G1–G6 are this item's; G7–G10 belong to the release. Not restated here, so the two cannot
drift. What this spec adds is **how each of its six is checked**:

| # | How it is checked |
| --- | --- |
| **G1** | `ONEUP_ENGINE_CMD=… tests/run-tests.sh` — the same suite, the same assertions, the new engine (§4.4) |
| **G2** | `tests/differential.sh` (§4.5) |
| **G3** | `python3 tests/gui-smoke.py`, with the window driving v2 |
| **G4** | the existing one-prompt scenario, unchanged (INV-6) |
| **G5** | a new scenario, PySide6 hidden from the import path (INV-11) |
| **G6** | manual, with the user: `--check`, a real update, a rollback offer — plus §4.5's list |

`./local-CI.sh` prints the suite tallies; it is the gate for every push
(`docs/standards/workflow.md` §6).

## 8. Docs & release

When the switch lands in stage 9:

- **`docs/reference/marker-protocol.md`** — §5.1 lifts the freeze; the "known drift in the
  engine's own header comment" section (§7) dies with the Bash header it describes.
- **`tests/docs-check.py`** — its marker gate reads `update_system.sh` for `marker NAME`
  call sites. Point it at the Python emitters in the same commit, or the contract stops
  being checked at the moment it is most likely to move.
- **`CLAUDE.md`** — §4's two-file architecture and §5's Bash-specific traps
  (`tee -a -p`, sudo in subshells) are rewritten for the package. The traps do not vanish:
  the sudo one becomes a property (§4.3.1), the `tee` one becomes `BrokenPipeError`
  handling.
- **`README.md`** — the standalone-engine instructions name `update_system.sh`.
- **`CHANGELOG.md`** and the **six version sites** — a major bump to **2.0.0**, which is
  also the honest signal: the engine anyone shelling out to OneUp depended on has changed.
  `docs/standards/workflow.md` §5.1 owns the lockstep.
- **The three packaging paths** — §4.7.

## 9. Alternatives considered (and rejected)

| Alternative | Why not |
| --- | --- |
| Keep hardening the Bash engine | it works, and §2.2 concedes that none of ONEUP-0048's failures were Bash's fault. But §2.1's three costs are structural, and the first one is a rule every privileged call site must each remember — of which there were 34 when this was written (`docs/standards/security.md` §1.2). The user weighed this and chose the rewrite (ONEUP-0052) |
| Rewrite and redesign the protocol in one step | it makes the differential harness impossible, which throws away the only safety net the rewrite has. A failing test could not say which change broke it |
| Rewrite the engine and split the window together | same objection, different pair. The split is behaviour-preserving and the rewrite is not, so they must be separable (§3.1) |
| Use Python bindings instead of shelling out to `zypper` | out of scope for all of 2.0 (`docs/design/oneup-2.0.md` §10). It would replace a proven call surface with an unproven one inside a rewrite that is already unproven |
| Ship v2 as a beta alongside 1.4.0 | the user's rule: no partial 2.0 releases. Two engines in users' hands means bug reports nobody can attribute |
| Rewrite the tests to suit the new engine | it removes the only evidence the rewrite is faithful. G1 requires that no assertion changes |

## 10. Out of scope

- **Any protocol change**, including the byte counters §4.3.3 makes possible. They come
  after G2, on their own change.
- **Turning `@@HINT@@` and `@@REMEDY@@` prose into codes.** That is ONEUP-0032, and
  `docs/design/oneup-2.0.md` §5.1 explains why it must not ride along with the rewrite.
- **Moving `--notify` into the window.** It shells out to `notify-send` from a non-root
  context, so it arguably belongs there. Kept as-is, because moving it would break G2 for
  no gain during the rewrite. Revisit after the switch.
- **Any change to the five steps or their order.**
- **The window's split into modules** — ONEUP-0034 (§3.1).

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-27 | 2 critical, 6 high, 6 medium, 7 low (this document's share of batch 2) | Both criticals were obligations this spec had accepted and not discharged. `docs/reference/marker-protocol.md` §8 says in terms that the state-file layout is pinned nowhere and that *this* spec must pin it; the spec instead cited §8 as the owner, so the contract existed in neither — now §4.1.1. And the SIGKILL keep-alive scenario, named twice as running "unchanged", `sed`s the keep-alive out of `update_system.sh` and executes it: against a Python engine it cannot run at all, so G1's "no assertion changed" had a hole nobody had written down. Also: `zypper.py` became `parsers.py` + `repos.py` (one responsibility each, and importing a parser no longer drags in `sudo`), INV-9's missing test became a stage-2 deliverable rather than an admission, and stage 9 stopped calling itself the 2.0.0 release |
