# ONEUP-0054 — a Python engine

**Status:** Reviewed
**Kind:** implement
**Roadmap:** ONEUP-0054
**Branch:** v2
**Verified at:** `8d4c93e` — every figure below was measured against this tree, not recalled.

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
`@@MARKER@@` protocol and the command-line flags stay **byte-identical**, and the exit codes
and the state-file layout are unchanged, so the existing engine test suite proves the
rewrite instead of being rewritten for it. v1 and v2 can be run side by side and compared, and the switch-over is a
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
(`docs/design/oneup-2.0.md` §4) and its **branch** (that document's §5.3), and it is the first *substantial* work on that branch (its §5.2) —
but it is a separate roadmap item with a separate spec, and it is **not** part of this
spec's gate. It is behaviour-preserving where this is not, so entangling the two would mean
a failing test could not say which change broke it.

An earlier draft of this document said the split lands "in the same package" in a way that
read as one item. It does share the package. It is not one item.

## 4. Design

### 4.1 What does not change

- **The privilege split.** The window process never *becomes* root, and every update runs
  through the engine. `docs/standards/security.md` owns the boundary, and it is more exact
  than a one-line summary can be: §1.4 records the three `pkexec` actions the window may ask
  for (repository edits, service restarts, rollback) and the `systemctl reboot` that goes
  through neither, and §3.1 records that exactly one `sudo` in the engine passes `-A` and
  `-p`, and that the rest are plain `sudo` deliberately — that standard owns the split. The rewrite preserves that shape
  rather than tidying it.
- **The marker protocol.** Every marker in `docs/reference/marker-protocol.md` §3 keeps
  its name, field order and semantics. A rewrite that also redesigns its own contract
  cannot be differentially tested, which would throw away the only real safety net this
  project has. The reference's §5.1 records the freeze. The one change it permits inside
  2.0 is ONEUP-0072's; anything else waits for the 2.0.0 tag
  (`docs/design/oneup-2.0.md` §10).
- **The command-line surface.** Every flag the argument loop in `update_system.sh` accepts,
  with the same spelling and the same behaviour, including the `-h` alias that shares
  `--help`'s arm. `docs/design/oneup-2.0.md` §2 enumerates them and §3 freezes them; not
  repeated here, so the two lists cannot diverge.
- **The exit codes.** The window takes its verdict from the engine's exit code —
  `Updater.on_finished` sets `ok = exit_code == 0`, with `@@DONE@@` as belt and braces. The
  codes stay identical, and the differential harness asserts it (§4.5) — **for the codes a
  scenario reaches**. Nothing pins the full set anywhere, and `exit 2` (unknown flag) and the
  trap codes 130/143/141 are in no scenario, so v2 could change those three with every gate
  green. Stage 2 writes them down beside §4.1.1, the same way and for the same reason.
- **The two state files.** `run.state` and `stop.request` keep their **layout** (§4.1.1) and
  their `ONEUP_RUN_STATE` / `ONEUP_STOP_FILE` overrides — as does every other `ONEUP_*`
  override in `docs/standards/files-and-naming.md` §5.1, several of which the suite depends
  on. Their **location** is not this item's to keep: `docs/design/oneup-2.0.md` §6.5 settles
  it, and ONEUP-0059 has already moved both halves to `XDG_STATE_HOME` several items earlier.
  `runstate.py` inherits wherever that left them.
  `docs/reference/marker-protocol.md` §8 names them and their purpose, and delegates their
  **field layout** to this spec, which pins it in §4.1.1.
- **The engine's log directory.** The engine writes each run's log to
  `~/Documents/update-logs/`, where a user can find it. The *directory* has no override;
  the individual run's log file does, via `--log=FILE`, which every test scenario uses.
  (`docs/standards/files-and-naming.md` §7 Trap 2 obliges the rewrite to stop creating that
  directory on the real machine during tests. That is a change rather than a constant, so it is a §4.6
  stage 2 deliverable — ONEUP-0058 — not part of this list.)
- **Standalone terminal use.** `oneup-engine --steps=system,cache` must be as usable in a
  plain terminal as `./update_system.sh` is today.

**What is *not* an engine contract, though an earlier draft said so:** `history.json` and
`~/.local/state/oneup/logs/` belong to the **window** — `updater.py`'s `HISTORY` and
`LOG_DIR` constants. The engine never *resolves* either path; it writes into that log directory only when the
window's `--log=` points there. `docs/standards/files-and-naming.md`
§5.1 is the owner of the full path table, and its §7 "Trap 1" is the one this rewrite must
act on: `LOG_DIR` names two different directories in the two programs, which is harmless
only while they are in different languages. Give them distinct names — `USER_LOG_DIR` and
`STATE_LOG_DIR`, or equivalent — before either is imported anywhere. **This spec renames
only the engine's**, at §4.6 stage 2 with `runstate.py`; the window's belongs to ONEUP-0034,
which must land the matching name or the collision simply moves.

### 4.1.1 The state-file layout, written down

`docs/reference/marker-protocol.md` §8 delegates this layout here, warning that the Python
engine "must reproduce it exactly or run-following breaks silently". Measured
from `update_system.sh`'s `RUN_STATE_FILE` writer and `updater.py`'s `_read_run_state` at
`8d4c93e`:

**`run.state`** — plain text, four lines, `\n`-terminated, written in one `printf` when the
run commits.

| Line | Field | Example |
| --- | --- | --- |
| 1 | the engine's pid | `48213` |
| 2 | this run's log path — the `--log=` value **verbatim** if one was given, otherwise the absolute default | `/home/u/Documents/update-logs/2026-07-27_0914.log` |
| 3 | the `--steps=` value **as given**, comma-separated — *not* normalised to run order | `system,flatpak,firmware,orphans,cache` |
| 4 | the epoch second the run committed | `1785132758` |

**The window reads the first three and ignores the fourth**, and treats fewer than three
lines, or a non-numeric first line, as no run at all. Lines 1–3 therefore may not be
reordered or dropped. Line 4 is written but unread today; v2 keeps writing it, because a
field nothing reads costs nothing and removing it would silently narrow the file.

**Both halves delete it, under different rules, and v2 must keep both:**

- The **engine** removes `run.state` *and* `stop.request` in `cleanup`, on any exit, but
  only when `RUN_STATE_OWNED` is set — so a `--check` or `--size` run cannot erase a real
  run's record.
- The **window** removes `run.state` when the run it names is gone: `_read_run_state`
  probes the recorded pid with `os.kill(pid, 0)`, unlinks the file on
  `ProcessLookupError`, and on `PermissionError` treats the run as **alive** and keeps it —
  a pid the window may not signal is still somebody's run — and `_poll_attached_run` unlinks it when the run it was following
  ends. That pid-liveness probe is part of the contract: it is what stops a `SIGKILL`ed
  engine leaving a record that makes every later window think a run is in flight.

**`stop.request`** — the *window* creates it (`STOP_REQUEST.touch()`) and never removes it;
the engine reads it at safe boundaries and deletes it in `cleanup` alongside `run.state`.
**Its contents are not part of the contract and the engine must not parse them.** What the
engine tests is `[[ -e run.state && stop.request -nt run.state ]]` — **both halves**. A
request whose mtime is not newer than `run.state`'s is a leftover and is ignored, and with
no `run.state` at all **no stop is ever honoured**, which is what stops a request outliving
the run it was meant for. **The mtime comparison is the load-bearing half**,
and v2 must keep it rather than deleting stale requests at start-up, which would race a stop
clicked in the same moment. `cleanup`'s deletion is tidiness and cannot be relied on: a
`SIGKILL`ed engine never runs it, which is precisely the case the comparison exists for.

### 4.2 Module layout

Nine modules, each tracing to an existing cluster of the Bash file rather than to a
speculative framework. `docs/standards/coding.md` §4 sets the module-size ceiling, and
`docs/standards/files-and-naming.md` §4.1 sets the naming and one-responsibility rules the
split must obey. Paths are relative to `oneup/engine/`.

| Module | Responsibility | Replaces |
| --- | --- | --- |
| `__main__.py` | drive one run: parse the flags, dispatch the steps in order, summarise | the top-level script body, `step_selected`, `usage` |
| `markers.py` | every marker emitter — the protocol in **one** place | `marker`, `emit_progress`, `emit_check`, and every `marker NAME` call site |
| `privilege.py` | become root once, and stay root safely for the run | `sudo_init`, `sudo_capture`, `reap_orphaned_askpass`, `cleanup` |
| `proc.py` | run a child process and stream it — deadline, incremental bytes, cooperative cancel | the ad-hoc pipelines, `progress_filter`, `stop_pending` |
| `runstate.py` | own the two state files and the log paths (§4.1.1) | the logging `exec` preamble and the state writes around it |
| `parsers.py` | turn zypper's text into values — **pure functions, no I/O, no privilege** | `to_bytes`, `lock_holder`'s parsing, the progress and download-size wordings, `lr` output, and `reboot_reason_from_log`'s phrase-building (its log **read** is `steps.py`'s — see the split table) |
| `repos.py` | refresh, skip and disable repositories | `refresh_repos`, `enabled_repo_aliases`, `find_failing_repos`, `disable_repo`, `release_zypper_lock`, `valid_alias`, `repo_scoped_failure` |
| `steps.py` | run the five steps: `system, flatpak, firmware, orphans, cache` | `begin_step`, `end_step`, `run_system_upgrade`, the per-step bodies |
| `actions.py` | the runs that are not an update: `--check`, `--size=`, the three auth actions, `--thin-snapshots`, and `--notify`'s `notify_send` (a desktop notification, not a marker) | `run_check`, `run_size`, `grant_auth`, `revoke_auth`, `auth_status`, `thin_snapshots`, `build_auth_rule` |

The table places every function in `update_system.sh`; it is a map, not a sample. **Five
functions cross a module boundary**, and each split is deliberate:

| Function | Split how |
| --- | --- |
| `lock_holder` | the `$ZYPP_PID_FILE` and `/proc/<pid>/comm` probe → `repos.py`; only the text it parses → `parsers.py` |
| `progress_filter` | the streaming loop → `proc.py`; the wordings it recognises → `parsers.py` |
| `cleanup` | it does four things across three modules: deleting the two state files → `runstate.py`; re-enabling every alias in `DISABLED_REPOS` → `repos.py`; reaping the askpass and killing the keep-alive → `privilege.py`. **The repo re-enable is the one to be careful with** — the scenario *"an interrupted --skip-repo run still re-enables the source (trap restore)"* is what asserts it, and it is easy to lose when one function is split three ways |
| `stop_pending` | the decision (is a stop pending at this boundary?) → `proc.py`; reading the two state files it decides from → `runstate.py` |
| `reboot_reason_from_log` | reading the run's log → `steps.py`; turning the lines it finds into the reason phrase → `parsers.py` |

Keeping I/O out of `parsers.py` is what makes §4.3.4's table-driven tests possible at all.

Two placements are worth calling out because losing them would be a real regression:
`valid_alias` is the engine-side shape guard `docs/standards/security.md` §4 requires before
an alias reaches a privileged command, and `reboot_reason_from_log` builds the optional
reason field of `@@REBOOT@@` (`docs/reference/marker-protocol.md` §4.8) — cosmetic in itself,
but it is the *marker* INV-1 governs, and losing the reason turns a correct verdict into an
unexplained one.
`oneup/engine/__init__.py` exists and is empty — `python3 -m oneup.engine` needs it.

**`parsers.py` and `repos.py` are deliberately two modules, not one.** An earlier draft had
a single `zypper.py` holding "pure parsers **plus** the repo refresh/skip/disable logic" —
which `files-and-naming.md` §4.1 rule 4 rejects on sight, and which would defeat §4.3.4:
importing the parsers to table-test them would drag in the code that calls `sudo`.

### 4.3 What the move to Python buys

Each claim is falsifiable and names the test that would falsify it. This section is the
whole justification for the branch — so it matters that **four of the five are demonstrated
by the gate and the fifth is not**: §4.3.3 is deliberately deferred past the switch, which
means the branch may prove it works but 2.0 does not ship it. Weigh the case on §4.3.1,
§4.3.2, §4.3.4 and §4.3.5.

#### 4.3.1 The seven-prompt bug class becomes structurally impossible

In Python every privileged child is spawned by the engine process itself, so there is
exactly one parent pid for the life of the run, and sudo's cached credential is keyed to
it. The failure mode described in §2.1 cannot be expressed. This is the single strongest
argument for the rewrite: it converts a rule that must be remembered at every privileged
call site into a property of the design.

*Test:* the existing scenario *"a full run asks for the password exactly once (no per-step
prompts)"*, unchanged — gate G4.

#### 4.3.2 Timeouts and cancellation become bookkeeping, not process trickery

Python still cannot signal a root child (§2.2), so the `sudo timeout` wrapper remains, and
anything v2 adds that must stop a root child needs the same shape.
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

**This lands after the 2.0.0 tag**, not inside 2.0 — it needs a new marker, and
`docs/design/oneup-2.0.md` §3 and §10 own that schedule. The branch may prove it works; it
must not ship it early. "After G2" is not the test either: G2 is met at stage 6 and measured
at stage 9, with 2.0 still unreleased either way.

#### 4.3.4 Parsers become unit-testable in isolation

`to_bytes`, the zypper progress wordings, the two download-size wordings, `lr` output and
`lock_holder` are today reachable only through a full engine run. As pure functions they
get table-driven tests, which is the right shape for the stale-parser canary — the scenario
*"a transaction with no recognisable progress lines says so (stale-parser canary)"*, which exists to fire when
zypper changes its wording under us.

*Test:* a new `tests/parsers-test.py`, table-driven over real captured zypper output.

#### 4.3.5 Two fragile dependencies disappear

- **`tee -a -p`.** Python writes its own log file and catches `BrokenPipeError` on stdout.
  No external tool, no probe, no fallback trap (§2.1).
- **The orphan-prone keep-alive.** In Python it is a daemon thread, which the kernel reaps
  with the process. No pid polling, and nothing left behind on `SIGKILL`.

*Test:* the existing scenario *"a run survives the GUI going away and still finishes (broken
stdout pipe)"* — its assertions unchanged; its invocation line takes §4.4's override, since
it calls the engine directly.

**The keep-alive's scenario is the one existing scenario G1 permits to be replaced rather
than carried, and the reason is worth stating.** *"the keep-alive exits on its own once the engine is gone
(SIGKILL-proof)"* does not run the engine at all: it `sed`s the `setsid bash -c` block out
of `update_system.sh`, substitutes a shorter sleep, and executes that Bash fragment, so what
it asserts is the `kill -0` guard **verbatim** — the exact mechanism this section proposes to
delete. Against a Python engine it fails at its first step, on "could not find the keep-alive
loop in the engine".

So it is **replaced, not carried**, and the replacement is a deliverable of §4.6 stage 2:
start a run, `SIGKILL` the engine, and assert no descendant of it survives — testing the
property (nothing outlives the engine, INV-7) instead of the Bash implementation of it. This
is the one replacement G1 permits, and it is recorded here rather than discovered during the
rewrite. Nothing covers the gap in the meantime — the differential harness reads
marker lines, and an orphaned keep-alive emits none — but INV-7's other two scenarios stay
unchanged throughout and catch an orphan left behind by an ordinary exit.

### 4.4 Making the test suite engine-agnostic

`run_engine` in `tests/run-tests.sh` invokes `bash "$ENGINE"`. It gains one indirection —
an `ONEUP_ENGINE_CMD` override, defaulting to the current `bash update_system.sh` — so the
*same* suite runs either engine. **Pin the encoding, because a Bash array cannot cross a
process boundary**: `export` drops it, so a caller that sets one hands the suite nothing.
It is a **scalar environment variable, word-split by the suite into its argv array** — the
default is two words, and `python3 -m oneup.engine` is three. Every reader must agree on
that: `run_engine`, the two scenarios patched by hand below, `tests/differential-test.sh`
(§4.5), which has no other way to select an engine, and the `local-CI.sh` / `release.yml`
wiring (§8). Settle it differently in the harness and in the suite and G2 diffs v1 against
v1 and goes green.

**`run_engine` is not the only place the suite reaches the engine, and the others are
what make this less trivial than it sounds.** All five must be accounted for and none
dropped; they land at stages 1, 2 and 5 as §4.6 has them, not in one pass. The invocation
count differs by branch: `main` has two invocations and `v2` has three, because ONEUP-0044
added the `--hold` scenario after stage 1 was written. Stage 1 lands on `main` and meets
`run_engine` and the broken-pipe scenario; the `--hold` scenario is stage 2's, alongside
the `runstate.py` work it exercises.

| Call site | What it does | What it needs |
| --- | --- | --- |
| `run_engine` | `bash "$ENGINE" "$@"` — almost every scenario | the `ONEUP_ENGINE_CMD` override |
| the broken-pipe scenario (INV-5) | invokes `bash "$ENGINE" --steps=system` directly, on purpose, so it can close the pipe on it | the same override, applied by hand at that site |
| the `--hold` scenario (ONEUP-0044) | invokes `bash "$ENGINE" --size=system --hold` directly and backgrounds it, so it can write `go.request` at the held engine | the same override by hand — **`v2` only**, and stage 2's, since a scenario still launching v1 leaves §4.1.1's hold contract untested against v2 with G1 green |
| the SIGKILL keep-alive scenario (INV-7) | reads `$ENGINE` as a **file** and executes a fragment of its Bash | nothing — it is replaced outright, §4.3.5 |
| the privileged-call-site count and the shared-argv check (`security.md` §5.2) | also read `$ENGINE` as a **file** — one `grep -c`s its `sudo` / `sudo_capture` call sites against a pinned number, the other greps its shared argv arrays | re-expressed against `oneup/engine/` at stage 5, when the last privileged call site moves. Neither is replaced: the guarantee they carry — that a new privileged call without a matching `auth_cmnds` entry cannot land unnoticed — has to survive the rewrite, not lapse with it |

Beyond those, the keep-alive scenario is the only **replacement** permitted to an existing
assertion before G1. The three invocation rows are re-pointings: they change what a
scenario invokes, never what it asserts. The structural-check row is neither — re-expressing
those two against `oneup/engine/` necessarily moves the figure one of them pins, so stage 5
re-measures the count and records it. That is the same guarantee restated against the new
engine, which is what G1 protects; leaving them greping a retired `update_system.sh` is the
weakening, because a check that passes about a file nothing runs has stopped guarding.

**Re-measured and recorded at stage 5.** The Python rows sit *beside* the Bash ones rather
than replacing them: `ENGINE_CMD=(bash "$ENGINE")` is still the suite's default and
`update_system.sh` does not retire until stage 9, so both engines carry the guard until the
Bash one goes. The call-site figure is a **union** — sudo-headed argvs *plus*
`privilege.sudo` call sites — and the union is what makes it a guard at all: `privilege.sudo`
is the Python `sudo_capture` and prefixes `sudo` itself, its callers passing `["zypper", …]`,
so counting sudo-headed argvs alone finds that one prefix line plus a handful of raw sites
and yields a figure that **cannot move when a new privileged call lands**. It stands at 33,
with the two shared argv constants referenced 3 and 4 times; those three figures are pinned
by the checks themselves, so none can go stale unnoticed. Both keep the Bash rows' note of
what they cannot see — an argv assembled in a variable, and two calls on one line.
*Additions* are a different matter and are expected: `docs/design/oneup-2.0.md` §7's G1 row
permits any new scenario a §4.6 stage names, and several stages do — the replacement
keep-alive test, the absent-tool test, the `run.state` fourth-line assertion and the
ONEUP-0058 log-directory scenario at stage 2, the parser unit tests at stage 4, the
per-call deadline test at stage 5, the differential harness at stage 6, the PySide6-absent
test at stage 7. The rule G1 enforces is that **no existing assertion is weakened**, not that
the suite stops growing. It lands on
`main` first and is shown to leave the suite green there, so the harness change is proven
independent of `v2`. `main` is frozen — `docs/standards/workflow.md` §1.2 is where that
exception is defined, and this change is the reason it exists.

### 4.5 The differential harness

New `tests/differential-test.sh` — `<subject>-<kind>`, per `docs/standards/files-and-naming.md` §2.1: for each scenario's mock set, run v1 and v2, capture only
`@@MARKER@@` lines, normalise the fields that legitimately vary (`TIMING` seconds, log
paths, pids, snapshot ids), and `diff` the rest along with the exit code. Green means
identical behaviour.

This is what makes the rewrite auditable rather than trusted, and it is the reason the
protocol is frozen. **Any divergence is either a v2 bug or a deliberate improvement that
gets written down here and given its own test.** Divergence is never waved through.

**Built at stage 6, and wider than the paragraph above describes. Three amendments,
recording what exists rather than changing direction.**

**The subject is whole output, not `@@MARKER@@` lines alone.** A marker-only diff cannot see
console text — which is what a terminal user and the log file get — and cannot see a mode
emitting no marker at all. Both mattered: the divergence the harness found was the banner's
position, console text; and `--emit-guard`, whose body differing by a byte stands every
passwordless user's toggle down (`docs/standards/security.md` §5.7), emits none.

**Two quantities are normalised, not the four named above.** The elapsed seconds are
normalised in both renderings — the `@@TIMING@@` marker and the summary's own column — and
so is the mock directory path, which subsumes the log-path case because the suite writes the
log inside it. Pids and snapshot ids are not: `docs/reference/marker-protocol.md` §3's table
carries no pid field, and the snapshot id and free-space figure come from the suite's own
mocks, so each is fixed and equal for the two sides. Normalising a field that cannot vary
blinds the gate rather than stabilising it.

**An accepted divergence carries a test, not a reason.** *"Given its own test"* is met by
pinning both engines' expected text for the line; a reason alone excuses every later edit to
it, and the harness is that line's only reader. One is accepted: `--help` names the program,
and the program's name changed.

Three divergences were settled rather than accepted — the banner's position, and two places
`--help` had quietly lost text the Bash carries.

**What it cannot see, stated so that nobody assumes otherwise:** timing-dependent behaviour,
and anything reachable only on a real machine — real sudo, real snapper, real repositories.
Gate G6 is what covers that, and the phase that builds the harness ends by writing the
explicit list of what G6 has to check by hand. That list is stage 6's, under *What G2 cannot
see* in `docs/plans/ONEUP-0054-python-engine.md` — it is direction for stage 8, so it lives
in the plan rather than here.

### 4.6 The order the gate is met in

Build steps belong in a plan, written when the item starts
(`docs/standards/documentation.md` §2). This is the ordering the plan must respect, because
each stage is what makes the next one safe to attempt.

| # | Work | What it satisfies |
| --- | --- | --- |
| 1 | `ONEUP_ENGINE_CMD` indirection at the two call sites that keep running the engine, on `main` (the third is replaced outright at stage 2 — §4.4) | §4.4 — the suite still green on `main`, unchanged |
| 2 | `__main__.py`'s flag parsing, plus `markers.py`, `runstate.py`, `proc.py`, `privilege.py`, and `actions.py`'s `auth_status` — enough for `--help` and `--auth-status`, nothing more. `runstate.py` also renames the engine's `LOG_DIR` to `USER_LOG_DIR` (§4.1, Trap 1) and discharges `files-and-naming.md` §7 Trap 2 (ONEUP-0058): create the log directory only when about to write it — with a scenario asserting no directory appears when `--log=` points elsewhere, because a fix nothing checks is a wish. Plus the three suite additions this stage owes: the replacement keep-alive test (§4.3.5), the absent-tool skip test (INV-9), and the assertion on `run.state`'s fourth line that INV-13 records as missing | the `--auth-status` scenario passes against v2; INV-9 gains its first test ever, and INV-7's SIGKILL leg is replaced |
| 3 | `actions.py`'s `--check` — read-only and needs no root, so the safest real behaviour to build first | every `--check` scenario green against v2 |
| 4 | `parsers.py`, `repos.py`, and `actions.py`'s `--size=`; parser unit tests | §4.3.4; the `--size` scenarios green |
| 5 | `__main__.py`'s run driver, pre-flight (`@@DISK@@`, `@@REPO@@`, `@@SNAPSHOTS@@`) and final summary. `steps.py` — the five steps, the pre-update snapshot block, remedies, repo skipping. The rest of `actions.py` (`--grant-auth`, `--revoke-auth`, `thin_snapshots`). Plus §4.3.2's new scenario: a per-call deadline firing on a step other than the repo refresh | the remaining scenarios → G1, and G4 with them — the one-prompt scenario is an engine-suite scenario and needs no window |
| 6 | The differential harness | G2, and the list of what it cannot see |
| 7 | The window pointed at v2 behind an environment switch, plus INV-11's new scenario: the engine run with PySide6 hidden from the import path | G3, G5 |
| 8 | A real run on the user's machine | G6 |
| 9 | The switch-over: the window defaults to v2, packaging follows the package layout, `update_system.sh` becomes the documented fallback | §4.7 |

Every stage from 2 onwards ends with `./local-CI.sh` green on `v2`; stage 1 ends with it green on `main`, which is the whole point of it (§4.4). Nothing in stages 1–8 changes `main`'s behaviour.

**Stage 9 is not the 2.0.0 release.** It is where this item's gate (G1–G6) is met and the
engine changes hands. ONEUP-0032 still follows it (`docs/design/oneup-2.0.md` §5.2), and
2.0.0 ships only when the whole of §7 there is satisfied. Each of G1–G6 is met at the stage above that earns it, and stage 9 is the commit they are measured against — they are **not** re-run at the 2.0.0 tag, because ONEUP-0072 lands in between and changes the marker payloads and the assertions that read them, in one versioned change, by design.

### 4.7 Packaging and the switch

- **Entry points.** `python3 -m oneup.engine` from a checkout; an `oneup-engine` console
  script when installed — created at stage 9, in the RPM's `%files` and the AppImage build
  alongside the existing `oneup` wrapper. Every hardcoded `bash`-plus-`ENGINE` launch in the window becomes
  one helper, and that helper *is* the switch: an `ONEUP_ENGINE=v1|v2` environment variable
  during stages 7–8, then a default flip. **There are eight, not six** — the six `QProcess`
  sites (`.start("bash", …)`) and **two `subprocess.run(["bash", str(ENGINE), …])` calls in
  the headless timer entry points**, `_headless_check` and `_headless_update`. Missing those
  two is the expensive mistake: they are the unattended paths, so a pair still launching v1
  after the switch would go unnoticed longest. The hardcoded `"bash"` is itself the tell —
  the window currently cannot launch a non-Bash engine at all.
- **Resolving the engine.** The helper replaces `_find_engine`, and must **not** reproduce
  it: `docs/standards/files-and-naming.md` §7 Trap 4 records that it returns its first
  candidate path whether or not the file exists — so what a missing engine looks like is
  decided by each caller rather than by the resolver. `Updater.start_run` does check and
  names the file; the tray check does not. The 2.0 resolver reports which paths it tried, so
  no caller has to.
- **What stage 7 actually built** (2026-09-03; recorded here rather than in the plan,
  because §4.7 is what a stage-9 reader opens). The helper is `engine_argv(*args)`,
  returning the whole command program-first: a `QProcess` site takes its head and passes
  the rest, a `subprocess` site passes it whole. **A second helper was needed and this
  section did not predict it** — `engine_available()`, because the guards it replaced ask
  `ENGINE.exists()`, which is a question about a Bash file and answers about the wrong
  engine once the switch is on.

  **The switch is two variables, not one.** `ONEUP_ENGINE=v1|v2` is the window's; §4.4's
  `ONEUP_ENGINE_CMD` stays the suite's. They answer different questions — the harness must
  pin an *arbitrary* command per side, while a scenario or a user switching the window
  names a side — and one name for both would let an export aimed at the suite reach the
  window unasked.

  **The v2 arm is headed by `env` carrying `PYTHONPATH`.** `-m` resolves only from the
  checkout root otherwise, and an argv cannot carry an environment any other way: not by
  mutating `os.environ`, which reaches the v1 `bash` child too, and not by a per-site
  environment, which would change the work at all eight sites to serve one arm of one
  helper.

  **`_find_engine` was NOT replaced, and `ENGINE` stays.** v1 is what an ordinary launch
  resolves until the flip, so the replacement and the path reporting the bullet above
  describes land with stage 9 rather than with the switch.

  **G3's probe is `--auth-status`**, driven through the window's own `_query_auth_status`:
  read-only, and its privileged leg is `sudo` with `-k -n`, which refuses to prompt, so
  the scenario can neither hang nor authenticate on the machine running it. It neutralises
  `_stand_down_autoupdate` for its duration — the finish handler reaches that on an
  explicit `@@AUTH@@|off`, and it opens a modal dialog wherever the weekly timer is on and
  the drop-in is not.
- **The three packaging paths** — what each does today and what each therefore needs — are
  `docs/design/oneup-2.0.md` §4, which owns them because ONEUP-0034 must move with them.
  Nothing engine-specific to add beyond the entry points above.
- **`update_system.sh` is retired, not deleted**, in stage 9. The schedule and the reason
  are `docs/design/oneup-2.0.md` §4's, which owns them; what this spec adds is that stage 9
  is where the retirement happens.

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
  *Test:* `tests/differential-test.sh` (§4.5) — gate G2. New with this work.

- **INV-11** The engine imports no Qt and runs with PySide6 absent. This is the privilege
  split made testable: the half that becomes root cannot depend on the half that draws
  windows.
  *Test:* a new scenario in `tests/run-tests.sh` that runs the engine with PySide6 hidden
  from the import path — gate G5, owed by §4.6 stage 7. New with this work.

- **INV-12** A package-only change offers a service restart, not a reboot. This is the
  third of `docs/standards/testing.md` §5's four floor invariants, and the one the others
  here did not cover.
  *Test:* the scenario *"package-only change offers a SERVICE restart, not a reboot"*,
  whose `@@SERVICES@@` assertion is what proves it.

- **INV-13** The two state files keep the layout §4.1.1 pins, so a window can find and
  follow a run the previous window started.
  *Test:* the scenarios *"a real run records itself in a run-state file and clears it on
  exit"* — which asserts lines 1–3 and the deletion — and *"a read-only --check run does NOT
  touch the run-state file"*, which asserts the `RUN_STATE_OWNED` rule. **Line 4, the epoch
  second, is asserted by nothing today**, so a v2 that dropped it would pass every gate; the
  §4.6 stage 2 work that builds `runstate.py` owes that assertion.

**Not an invariant of this spec, though an earlier draft listed it:** *tests never depend
on, or damage, machine state*. That is a rule about the suite, and
`docs/standards/testing.md` §2 owns it. It binds the rewrite because the rewrite's tests are
tests, not because the engine enforces it.

## 6. Failure modes

| If this breaks | What happens | What limits the damage |
| --- | --- | --- |
| The rewrite re-introduces a fixed bug | a shipped regression | G1 plus G2: no existing assertion is weakened (`docs/design/oneup-2.0.md` §7), and the marker streams are diffed |
| A behaviour lives only in Bash's semantics and nobody notices | v2 silently differs | the differential harness is *the* answer; what it cannot cover is listed in §4.5 and lands on G6 |
| The branch stalls half-done | 2.0 never arrives | `main` ships frozen 1.4.0 throughout; abandoning costs nothing but the branch |
| Scope creep — *"while we're rewriting, let's also…"* | the gate recedes | the protocol is frozen (§4.1) and §4.3.3 is explicitly deferred past the switch |
| The GUI split gets entangled with this gate | a failing test cannot say which change broke it | ONEUP-0034 is a separate item, specified and merged separately (§3.1) |
| Python's start-up latency shows on a short `--check` | the check feels slower | measured in stage 3, not assumed. An interpreter start against a multi-second zypper call is expected to be noise — but it is a measurement |
| A privileged call ends up inside a subshell equivalent | the seven-prompt bug returns | it cannot: §4.3.1 removes the mechanism. G4 still asserts it |

## 7. Tests

**The gate is `docs/design/oneup-2.0.md` §7**, which holds the conditions for all of 2.0 and,
since its own first review, the check behind each one. G1–G6 are this item's; G7–G10 belong
to the release. Not restated here, so the two cannot drift.

What this spec adds is the *content* of the checklist G6 leans on: §4.5 makes "everything
the differential harness cannot see" a deliverable of stage 6, and G6's manual pass works
through it alongside `--check`, a real update and a rollback offer.

`./local-CI.sh` prints the suite tallies; it is the gate for every push
(`docs/standards/workflow.md` §6).

## 8. Docs & release

When the switch lands in stage 9:

- **`docs/reference/marker-protocol.md`** — the "known drift in the engine's own header
  comment" section (§7) dies with the Bash header it describes. **§5.1's freeze survives
  stage 9**: only ONEUP-0072 may move the contract before the 2.0.0 tag, and §5.1 is
  rewritten at the tag, not at the switch-over. That
  section places one obligation on this work, and stage 9 discharges it: **ONEUP-0066** —
  carry the *corrected* marker list into the Python engine's own header, rather than
  copying the stale one forward.
- **`tests/docs-check.py`** — its marker gate reads `update_system.sh` for `marker NAME`
  call sites. Point it at the Python emitters in the same commit, or the contract stops
  being checked at the moment it is most likely to move.
- **`CLAUDE.md`** — §4's two-file architecture and §6's Bash-specific traps
  (`tee -a -p`, sudo in subshells) are rewritten for the package. The traps do not vanish:
  the sudo one becomes a property (§4.3.1), the `tee` one becomes `BrokenPipeError`
  handling.
- **`README.md`** — the standalone-engine instructions name `update_system.sh`.
- **`CHANGELOG.md`** and the **six version sites** — a major bump to **2.0.0**, which is
  also the honest signal: the engine anyone shelling out to OneUp depended on has changed.
  `docs/standards/workflow.md` §5.1 owns the lockstep.
- **The standards that describe the Bash engine as current.** Design §7's G9 requires them
  current at the tag, and this work is what makes them stale: `docs/standards/testing.md` §1,
  §2.3 and §3 (the engine suite asserts on what `update_system.sh` prints; the throwaway-
  directory and mock-`PATH` figures; the keep-alive-guard scenario §4.3.5 replaces);
  `docs/standards/security.md` §1.3, §2.2, §2.4 and §6.3 — the Bash-imports-nothing framing,
  and the three mechanisms this rewrite deletes (`sudo_capture`, the `setsid`
  `oneup-keepalive` loop, and `tee -a -p`); and `docs/standards/files-and-naming.md` §1
  and §7.
- **`local-CI.sh` and `.github/workflows/release.yml`** — both name every suite by hand, so
  the two test programmes this spec commissions (`tests/parsers-test.py` at stage 4,
  `tests/differential-test.sh` at stage 6) run nowhere until they are wired in. **Wiring each
  is part of the stage that creates it**, in *both* files — `docs/standards/workflow.md` §6.1
  step 3 requires it and its §10 names doing only one of them as a trap. `local-CI.sh` also
  shellchecks `update_system.sh` by name and `py_compile`s a two-file list, and
  `docs/standards/testing.md` §1's suite table gains a row for each.
- **The three packaging paths** — §4.7.

## 9. Alternatives considered (and rejected)

| Alternative | Why not |
| --- | --- |
| Keep hardening the Bash engine | it works, and §2.2 concedes that none of ONEUP-0048's failures were Bash's fault. But §2.1's three costs are structural, and the first one is a rule every privileged call site must each remember — of which there were 34 when this was written (`docs/standards/security.md` §1.2). The user weighed this and chose the rewrite (ONEUP-0052) |
| Rewrite and redesign the protocol in one step | it makes the differential harness impossible, which throws away the only safety net the rewrite has. A failing test could not say which change broke it |
| Rewrite the engine and split the window together | same objection, different pair. The split is behaviour-preserving and the rewrite is not, so they must be separable (§3.1) |
| Use Python bindings instead of shelling out to `zypper` | out of scope for all of 2.0 (`docs/design/oneup-2.0.md` §10). It would replace a proven call surface with an unproven one inside a rewrite that is already unproven |
| Ship v2 as a beta alongside 1.4.0 | the user's rule: no partial 2.0 releases. Two engines in users' hands means bug reports nobody can attribute |
| Rewrite the tests to suit the new engine | it removes the only evidence the rewrite is faithful. G1 permits additions and one named replacement, and nothing else (`docs/design/oneup-2.0.md` §7) |

## 10. Out of scope

- **Any protocol change**, including the byte counters §4.3.3 makes possible. They land
  after the 2.0.0 tag, on their own change (`docs/design/oneup-2.0.md` §10).
- **Turning `@@HINT@@` and `@@REMEDY@@` prose into codes.** That is ONEUP-0072, and
  `docs/design/oneup-2.0.md` §5.1 explains why it must not ride along with the rewrite.
- **Moving `--notify` into the window.** It shells out to `notify-send` from a non-root
  context, so it arguably belongs there. Kept as-is, because moving it would break G2 for
  no gain during the rewrite. Revisit after the switch.
- **Any change to the five steps or their order.**
- **The window's split into modules** — ONEUP-0034 (§3.1).

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-27 | 2 critical, 6 high, 6 medium, 7 low — **19 verified, 2 dismissed** | Both criticals were obligations this spec had accepted and not discharged. `docs/reference/marker-protocol.md` §8 says in terms that the state-file layout is pinned nowhere and that *this* spec must pin it; the spec instead cited §8 as the owner, so the contract existed in neither — now §4.1.1. And the SIGKILL keep-alive scenario, named twice as running "unchanged", `sed`s the keep-alive out of `update_system.sh` and executes it: against a Python engine it cannot run at all, so G1's "no assertion changed" had a hole nobody had written down. Also: `zypper.py` became `parsers.py` + `repos.py` (one responsibility each, and importing a parser no longer drags in `sudo`), INV-9's missing test became a stage-2 deliverable rather than an admission, and stage 9 stopped calling itself the 2.0.0 release |
| 2 | 2026-07-27 | 2 critical, 4 high, 5 medium, 6 low — **15 verified, 2 dismissed** | Nothing from loop 1 returned. What loop 2 found was mostly §4.1.1's own blast radius: the subsection written last loop to pin the state-file contract had the engine only *reading* `stop.request` when `cleanup` deletes it, and called line 3 the steps "in run order" when it is the `--steps=` value verbatim. §4.4 also forbade the two new scenarios §4.6 stage 2 commissions. Measured, not recalled: the window has **eight** hardcoded engine launches, not six — the two missed are the unattended headless timers |
| 3 | 2026-07-27 | 4 high, 7 medium, 7 low — **16 verified, 2 dismissed** | Converging: no critical, and no structural claim wrong. The §4.2 module table turned out to be a partial map presented as a complete one — five engine functions had no home, two of them load-bearing (`valid_alias`, the alias guard `security.md` §4 requires, and `reboot_reason_from_log`, which feeds a marker field). §4.1.1 had been pinned as a contract with no invariant and no named test, so INV-13 now names the two scenarios that cover it and states plainly that line 4 is covered by neither. §4.3's own tally said "three of the four" of five |
| 4 | 2026-07-27 | 1 critical, 3 high, 6 medium, 6 low — **14 verified, 2 dismissed** | The critical was one fact with three answers: §4.1 said protocol changes come "after the switch", §4.3.3 said the freeze lifts once G2 passes, and §10 said after the 2.0.0 tag. G2 passes at stage 9 with 2.0 still unreleased, so two of the three would have let the byte-counter marker ship inside a release the design forbids it from. §4.1.1 also stated the stop check as a modification-time comparison alone, where the engine requires `run.state` to exist as well — built to the spec as written, v2 would honour a request left over from a run that no longer exists |
| 5 | 2026-07-27 | 1 high, 4 medium, 8 low — **11 verified, 2 dismissed** | No critical. §8 said stage 9 is where `marker-protocol.md` §5.1 lifts the freeze — a release early, and contradicting what §4.3.3 and §10 had just been corrected to say. The freeze survives the switch-over; only ONEUP-0032 moves the contract before the tag. §4.7 also justified replacing `_find_engine` with a symptom the code contradicts: `Updater.start_run` does check and names the missing file, and it is the tray check that fails silently — the requirement stands, its reason was wrong |
| 6 | 2026-07-27 | 4 high, 5 medium, 8 low — **15 verified, 2 dismissed** | No critical. §4.2 said two functions cross a module boundary; four do, and the one that matters is `cleanup` — it deletes the state files, re-enables every disabled repository and reaps the keep-alive, which is three of this spec's own modules. The repo re-enable has a scenario guarding it and is exactly what gets lost when one function is split three ways. §8 also listed no CI script, so the two test programmes this spec commissions would have run nowhere — `workflow.md` §10 names that as a trap by name. Two passages still described `marker-protocol.md` §8 as pinning the layout nowhere; it now points here |
| 7 | 2026-07-27 | 1 critical, 4 high, 5 medium, 5 low — **13 verified, 2 dismissed** | The critical came from the design's own previous loop: §4.1 still froze the state files' *location* when ONEUP-0059 moves it, in both halves, four items before this one starts. An implementer building `runstate.py` would have hard-coded the path 0059 had just changed. Two module placements were wrong for the same reason — `reboot_reason_from_log` reads a file and `notify_send` emits no marker, so neither belonged where it sat — and `__main__.py`'s run driver and final summary, which emit half the markers INV-1 and INV-2 assert on, were owed by no stage at all |
| 8 | 2026-07-27 | **none verified** (one raised and dropped — see the design's loop 9 row) | **Converged.** `Draft` → `Reviewed`; implementation of ONEUP-0054 is unblocked |
