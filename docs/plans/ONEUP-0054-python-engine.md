# ONEUP-0054 — Python engine — build plan

**Spec:** [docs/specs/ONEUP-0054-python-engine.md](../specs/ONEUP-0054-python-engine.md)
**Status:** in progress — stages 1 and 2 done (2026-08-25); stage 3 next.

## Scope of this file

The spec's §4.6 owns the stage order and why each stage makes the next one safe.
This file holds the build steps, and only for the stage under way.

**Later stages are absent by rule, not by omission.**
`docs/standards/documentation.md` §2: *"A plan: when the item starts, never
before. A plan written months early describes code that does not exist yet — it
is fiction, and it will be wrong."* Stage 5's steps cannot be written before
stage 4 lands. Each stage's steps are appended here when that stage starts, and
the Status line above says which one that is.

## Stage 1 — the `ONEUP_ENGINE_CMD` indirection

**Branch: `main`.** `docs/standards/workflow.md` §9 routes it there, and §1.2
grants it by name as the first of the freeze's named exceptions — *"One named,
behaviour-neutral test-harness change"*. §1.2 calls it behaviour-neutral and,
unlike the second exception, does not say a 1.4.x is owed.

**What it must not become.** §4.4: the override is a **scalar** environment
variable that the suite word-splits into its argv array, because `export` drops
a Bash array. The default is `bash $ENGINE` — the absolute path the suite's existing
`ENGINE=` assignment computes, not the literal string `update_system.sh`, which
would resolve against the caller's working directory. Both are two words, so
§4.4's word-count wording does not separate them. `python3 -m oneup.engine` is
longer by a word. Settle the encoding differently in two readers and gate G2
ends up diffing v1 against v1 and passing.

### Steps

1. **Replace `main`'s §4.4 with `v2`'s §4.4 verbatim, whole.** `main`'s copy
   still reads *"an `ONEUP_ENGINE_CMD` array override"*; the correction making
   it a scalar landed on `v2` with the ONEUP-0127 re-gate and was never merged
   back. Stage 1 is built on `main`, so an implementer reading `main`'s
   contract builds the array the re-gate removed — and §4.4's own warning is
   that the wrong encoding leaves G2 diffing v1 against v1 and passing.
   **Whole, not a patch of the encoding sentence**: the two copies differ well
   beyond that sentence — `v2`'s call-site table carries the `--hold` row and
   the structural-check row, and the stage assignments steps 7 and 10 cite.
   A minimal edit leaves step 9's merge conflicting in this same section with
   no rule for resolving it, and resolving toward `main` would silently revert
   the re-gated contract stage 2 builds from. Documentation lands on `main`
   normally (`docs/standards/workflow.md` §1.2).
   → **verify:** `main`'s §4.4 is byte-identical to `v2`'s, and `python3
   tests/docs-check.py` still passes on `main`. Check for the *presence* of the
   scalar sentence, never the absence of the word *array* — the correct text
   reads *"word-split by the suite into its argv array"*, so a builder told to
   remove that word deletes the sentence that pins the encoding.

2. Build the argv array **once**, at the top of `tests/run-tests.sh` beside the
   existing `ENGINE=` assignment, from `ONEUP_ENGINE_CMD` with `bash $ENGINE` as
   the default. One reader of the variable means the call sites cannot disagree
   with each other about the encoding.
   → **verify:** `bash -n tests/run-tests.sh` parses, and the array holds the
   default's words when the variable is unset.

3. Word-split without globbing. Unquoted expansion inside an array assignment
   globs as well as splits, so a value containing `*` would expand against the
   working directory.
   → **verify:** `ONEUP_ENGINE_CMD='python3 -m oneup.engine'` yields those
   words and no others, and a value containing `*` yields the literal `*`.

4. Point `run_engine` at the array in place of its `bash "$ENGINE"` invocation,
   leaving every environment override and the appended `--log=` untouched.
   → **verify:** `tests/run-tests.sh` green on `main` with the variable unset.

5. Apply the same array by hand at the broken-pipe scenario — the one that
   invokes the engine directly so it can close stdout on it, under the comment
   beginning *"Invoked directly rather than through run_engine"*.
   → **verify:** the only remaining `bash "$ENGINE"` in `tests/run-tests.sh`
   on `main` is step 2's default-array assignment — neither `run_engine` nor
   this scenario invokes it directly any more; both expand `"${ENGINE_CMD[@]}"`.
   **Not** "the scenario still passes": with the variable unset the array
   expands to `bash $ENGINE`, so this scenario behaves identically whether or
   not the step was performed, and its checks pass either way. And **not**
   "the grep returns 0" — the glob-safe default is an array literal that
   contains that string once, legitimately, as an assignment.

6. **Prove the indirection is not inert.** This is the step that makes stage 1
   observable at all: setting a variable nothing reads leaves the suite green
   exactly as it was, so green alone is evidence of nothing.
   → **verify:** point `ONEUP_ENGINE_CMD` at a stub that exits non-zero, run the
   suite, and see it go red. Unset it and see it go green again. **Then, with
   the stub still set, read the broken-pipe scenario's own `check` lines in the
   run and see them FAIL.** The suite takes no arguments and has no per-scenario
   selector, so this is read out of the whole run's output rather than invoked
   on its own. Whole-suite redness is evidence about `run_engine` alone —
   it drives nearly every scenario, so the suite goes red the moment that one
   site is converted, whether or not the other was.

7. Leave the readers that treat `$ENGINE` as a **file** alone — the
   keep-alive `sed`, the privileged-call-site count and the shared-argv check.
   §4.4 — as step 1 brought it across — sends the first to §4.3.5, which stage 2
   discharges, and assigns the other two to stage 5. `main`'s pre-step-1 copy names no stage for the
   keep-alive reader and carries no row at all for the other two.
   → **verify:** none of those three readers appears in
   `git diff -- tests/run-tests.sh` on `main`. Scoped to that file on purpose:
   step 1's §4.4 transplant adds a table row naming two of them, so an
   unscoped diff can never come back clean.

8. Run the full push gate.
   → **verify:** `./local-CI.sh` green on `main`.

9. Commit on `main`, then merge `main` into `v2` (§1.2, §2). Step 1 having
   crossed §4.4 whole, the section is identical on both sides and the merge
   has nothing to resolve there.
   → **verify:** `v2`'s §4.4 after the merge is byte-identical to its
   pre-merge content; `run_engine` on `v2` expands `"${ENGINE_CMD[@]}"`; and
   the stub run turns the suite red on `v2` too. **Green alone will not do**,
   for step 6's reason — and `run_engine` differs between the branches
   (ONEUP-0044 added two environment lines), so a conflict there is likely and
   resolving it toward `v2` silently drops the indirection.

10. Confirm the merge left the `--hold` scenario ONEUP-0044 added to `v2` still
    launching v1 on purpose. §4.4 assigns it to stage 2, alongside the
    `runstate.py` work it exercises.
    → **verify:** that scenario still reads `bash "$ENGINE" --size=system
    --hold` on `v2`, and stage 2's row in §4.6 is what changes it.

### Not a call site

`v2`'s pre-push-hook scenario derives `REPO="$(dirname "$ENGINE")"`. It uses
`$ENGINE` to locate the repository root and neither invokes nor reads the
engine, so it is outside §4.4's table and stage 1 does not touch it. Recorded
here so a later reader does not count it as a site somebody missed.

## Stage 2 — the first Python modules, and the suite work the stage owes

**Branch: `v2` only.** §4.6 ends every stage from 2 onwards with `./local-CI.sh` green on
`v2`, and says outright that *"Nothing in stages 1–8 changes `main`'s behaviour."* That
sentence is what routes step 6's engine fix to `v2` rather than to `main`, against
`docs/standards/workflow.md` §9's default route for a `Kind: fix`; ONEUP-0058's own bullet
says *"Do not fix on `main`"* for the same reason. **Step 13's documentation edits split
by branch and are not covered by this note** — that step routes each one and says why.

**What stage 2 is not.** The Python engine *acts on* `--help`, `--auth-status` and
`--emit-guard` and on nothing else; it parses every other flag and refuses loudly only
when one selects work it has not built (step 8). No run driver, no `--check`, no `--size`,
no steps, no `sudo_init`, no state writes — §4.6's stage-2 row ends *"nothing more"*, and
a module that grows past what the steps below name is stage creep, not thoroughness.

### Steps

1. Create `oneup/engine/`, with an empty `__init__.py` — `python3 -m oneup.engine` needs
   one.
   → **verify:** `python3 -c 'import oneup.engine'` from the repo root exits 0, and
   `tests/imports-test.py`'s INV-3 line stops reading *"the directory does not exist yet"*.

2. `markers.py` — one emitter for the whole protocol, printing `@@NAME@@|payload`, flushed
   on every call. The window reads the engine's stdout line by line through `QProcess`, and
   Python block-buffers a pipe by default, so an unflushed marker arrives late or not at
   all.
   → **verify:** emit a marker from a process that then **stays alive**, and read the
   line out of the pipe before it exits. A one-shot `python3 -c … | cat` proves nothing —
   CPython flushes at interpreter shutdown, so it prints with or without the flush
   (measured). The window reads a *running* engine, which is the case that breaks.

3. `privilege.py` — the single owner of every privileged child
   (`docs/standards/security.md` §2.3). At this stage that is the askpass and prompt
   environment — the `ONEUP_ASKPASS` override, and the two exported variables with the same
   defaults and the same prompt wording the Bash engine sets — plus one runner that is the
   sudo parent for everything. `sudo_init`, the keep-alive, `reap_orphaned_askpass` and
   `cleanup` are stage 5's.
   → **verify:** no module under `oneup/engine/` except `privilege.py` imports
   `subprocess` — **run at step 14**, once the stage's modules exist. At step 3
   `privilege.py` is the only one, so the check cannot fail; `actions.py`, added at step 7,
   is where a stray privileged call would land. Grepping for `"sudo"` is not enough: this
   repository's ruff set selects no quote-style rule, so `['sudo', …]` would pass it.

4. `proc.py` — run a child process and return its status and captured output. Fixed argv,
   never `shell=True` (`docs/standards/coding.md` §5.1), and any `# noqa: S603` says why the
   call is safe rather than which rule it silences (§5.2). The deadline, the incremental
   byte counting and cooperative cancel belong to stages 4 and 5; do not build them now.
   → **verify:** `ruff check .` clean — bandit (`S`) is selected, so a *missing*
   suppression fails here. A **reasonless** one does not: bare `# noqa: S603` comments live
   in `oneup/gui/` today and ruff is green on them (measured). Read every `noqa` this step
   adds against `coding.md` §5.2 by eye; no tool does.

5. `runstate.py` — the four state-file paths, their `ONEUP_*` overrides, and the log paths.
   The engine's log directory is named `USER_LOG_DIR` here from the start (Trap 1, step 9).
   The `XDG_STATE_HOME` rule is ONEUP-0059's and must read the same in the Bash engine,
   the window and `runstate.py`: an **absolute** value wins; unset, empty or relative falls
   back to `~/.local/state/oneup`.
   → **verify:** for each of those four environments, the path `runstate.py` computes for
   `run.state` **equals the one `oneup/gui/paths.py` computes** — an equality against the
   window's own resolution, not against the rule restated in the check. A check that
   re-derives the rule passes a `runstate.py` that got it wrong in the same way, and Stop
   then writes where the engine never looks.

6. **Create the engine's log directory only when the run is about to default into it** —
   `docs/standards/files-and-naming.md` §7 Trap 2, ONEUP-0058. In `runstate.py`, **and** in
   `v2`'s `update_system.sh`, whose logging preamble runs its `mkdir` before it has looked
   at `--log=`. Both halves, because the suite drives the Bash engine on `v2` until the
   engine changes hands at stage 9, so a fix only in Python leaves step 6's own scenario
   red for the whole rewrite.
   → **verify:** a new scenario points `HOME` at a throwaway directory, runs the engine
   through `run_engine` — which always supplies `--log=` — and asserts
   `$HOME/Documents/update-logs` does not exist afterwards. **Not** "the suite is still
   green": the directory today's engine creates is on the developer's own machine, so
   nothing that exists now fails, and the fix and the scenario each prove nothing without
   the other.

7. `actions.py` — `auth_status`, and the four functions it rests on: `auth_cmnds`,
   `download_guard_src`, `guard_current` and `auth_current` — **with the `ONEUP_AUTH_FILE`
   and `ONEUP_GUARD_FILE` overrides those last two read, and the Bash engine's defaults
   behind them.** They are neither state files nor log paths, so step 5 does not cover
   them, and the `--auth-status` scenario drives the engine entirely through them: without
   them stage 2 reads the real `/etc/sudoers.d/` and `/usr/libexec/`, which
   `docs/standards/testing.md` §2 forbids outright. **Also `--emit-guard`**, which
   is stage 2's whether or not §4.6's row names it: the `--auth-status` scenario writes a
   current guard with it, and its last check cannot be reached without one.
   → **verify:** at step 14, once `__main__.py` can answer a flag — `--emit-guard` from
   the two engines, under the same mock `PATH`, is **byte-identical**. This is the one divergence G2 cannot see — the harness compares
   marker streams and `--emit-guard` emits none — and a guard body differing by a byte makes
   every v1-granted guard read as stale to v2, standing every such user's toggle down
   (`docs/standards/security.md` §5.7).

8. `__main__.py` — the argument loop. The same flags with the same spellings, `-h` sharing
   `--help`'s arm, and an unknown flag printing `Unknown option: <arg>` on stderr followed
   by the usage, exit 2. `--help`/`-h` prints the usage and exits 0; `--auth-status` and
   `--emit-guard` do their work. **Every other flag is parsed and stored, never refused** —
   `--log=` above all, which `run_engine` appends to *every* invocation, so an engine that
   rejected it could not reach a single scenario. What exits non-zero is a flag selecting
   **work** stage 2 has not built — the default run, `--check`, `--size=`,
   `--thin-snapshots`, `--grant-auth` and `--revoke-auth` — with a message naming the stage
   that owes it.
   → **verify:** the set of flags the Python parser accepts equals the set of `case`
   patterns in `update_system.sh`'s argument loop, compared mechanically rather than read
   off. And `python3 -m oneup.engine --steps=system` writes **nothing to stdout** and exits
   non-zero — a stage that printed a marker for work it has not built could be read as a
   run that did nothing.

9. **The `LOG_DIR` rename, both halves in one commit** (§4.1, Trap 1). The engine's constant
   is born `USER_LOG_DIR` at step 5; the window's becomes `STATE_LOG_DIR`, every reader
   following. Readers reach it through `paths.` (ONEUP-0034 INV-2), so this is one
   definition plus its call sites and nothing else.
   → **verify:** no bare `LOG_DIR` remains under `oneup/` or in `tests/*.py`.
   `update_system.sh`'s own `LOG_DIR` **stays**: it is Bash, no Python imports it, and it
   retires with the file at stage 9 — Trap 1's collision is between two *Python* names in
   one package. Recorded so a later reader does not count it as a site somebody missed.

10. **Write the four unpinned exit codes down beside §4.1.1**, which §4.1 promises and
    §4.6's stage-2 row repeats. Nothing pins `2`, `130`, `143` or `141` today, so v2 could
    change all four with every gate green. **It does not re-arm the spec's gate:** §4.1
    already freezes the codes, so writing down which they are leaves every conformer
    building the same thing. Say so in the commit body, as rule 14 requires.
    → **verify:** each is read out of `update_system.sh` — `2` from the argument loop's
    `*)` arm, and `130`, `143` and `141` from the three `trap 'exit N'` lines — and the
    table names the construct each comes from, so a later reader can re-take the
    measurement rather than trust it.

11. **Give the `--hold` scenario the `ONEUP_ENGINE_CMD` override** (§4.4's table). Stage 1
    left it launching v1 on purpose; `start_held_engine` is the function that invokes the
    engine.
    → **verify:** `"${ENGINE_CMD[@]}"` appears at that call site, and the only remaining
    `bash "$ENGINE"` in `tests/run-tests.sh` is the default-array assignment at the top —
    **one occurrence, not zero**, for the reason stage 1 step 5 records.

12. **The three suite additions §4.6's stage-2 row names.**

    a. **The replacement keep-alive test** (§4.3.5, INV-7). The existing SIGKILL scenario
       `sed`s the keep-alive loop out of `update_system.sh` and executes that Bash
       fragment, so what it asserts is one engine's implementation — which is why §4.4's
       table gives it no override and calls it replaced outright. The replacement stages a
       held engine, `SIGKILL`s it, and asserts nothing it spawned survives. **Delete the
       existing scenario in the same commit** — leaving both is not the belt-and-braces it
       looks like: G1 permits exactly one replacement and is read off the diff at stage 9,
       and a scenario that greps a retired `update_system.sh` passes about a file nothing
       runs.
       The keep-alive sleeps 50 seconds between checks, so the property is unobservable
       inside a test's patience: give the interval an `ONEUP_KEEPALIVE_SECONDS` override
       defaulting to 50, **in `v2`'s `update_system.sh`** — the Python keep-alive is stage
       5's, so there is no second place to put it yet — the way `ONEUP_STOP_POLL_SECONDS`,
       `ONEUP_HOLD_SECONDS` and `ONEUP_REFRESH_TIMEOUT` already are, and for the same
       stated reason. Then set it in the scenario.
       → **verify:** the replacement identifies a survivor by the `oneup-keepalive` tag
       **and the dead engine's pid**, which the loop carries as its argument: the tag alone
       matches another scenario's keep-alive, and a developer's own. And it must be able to
       fail — delete the loop's `kill -0` guard, re-run, and this scenario's own check lines
       must FAIL while the guard is gone.

    b. **The absent-tool skip test** (INV-9, ONEUP-0070) — the branch neither engine has
       ever run. `run_engine` puts the mock directory *first* on the real `PATH`, so
       deleting the two mocks finds the developer's own `flatpak` instead. The scenario
       therefore supplies a `PATH` of its own: the mock directory, then a directory of
       symlinks to every executable on the real `PATH` except `flatpak` and `fwupdmgr`.
       → **verify:** with both hidden, each of the two steps ends `skip` rather than `fail`
       and the run's verdict is unaffected — **and** the scenario asserts that
       `command -v flatpak` finds nothing under that `PATH`, so a symlink farm that quietly
       kept the real binary cannot pass this as a skip that never happened.

    c. **`run.state`'s fourth line** (INV-13). The existing run-state scenario asserts
       lines 1–3 and the deletion; line 4, the epoch second the run committed, is asserted
       by nothing, so a v2 that dropped it would pass every gate.
       → **verify:** the assertion reads the fourth line of the copy taken *during* the
       run — the scenario already keeps one, so no second run is staged — and requires a
       run of digits. Bump that scenario's staging-failure tally with it: the branch counts
       the field checks that could not run, and states its arithmetic in a comment.

13. **Repair the documentation steps 6, 9 and 12a make false.** Six passages, and they
    split by branch.

    **ONEUP-0058, three passages → `main`, then merge.** `docs/standards/testing.md` states
    it in its exceptions list and again in its *What checks this* table; Trap 2 of
    `docs/standards/files-and-naming.md` states it a third time. **Step 6 falsifies the
    consequence, not the premise:** the suite still does not redirect `HOME` — only the new
    scenario does, for itself — and what stops the directory appearing is the engine no
    longer creating it. An edit claiming the suite redirects `HOME` would assert an
    isolation it does not have, which is the silent exception `testing.md` §2 forbids.
    Word each to hold on **both** branches — created on `main`, no longer on `v2` — and
    `docs/standards/workflow.md` §9 routes them to `main` with no exception needed.

    **The window's constant, two passages → `v2`.** Trap 1 and §5.1's list of the window's
    path constants both name `LOG_DIR`, which exists under that name only on `main`. No
    both-branch wording is possible, and **neither of §9's two named bindings reaches
    this** — §9 says a third *"would need naming here before it counted"*. Do not amend §9
    from inside a build stage — that is a direction change and re-arms §9's own gate.
    **Filed as ONEUP-0130**; put these two on `v2`, where `files-and-naming.md` already
    diverges.

    **The new override, one passage → `v2`.** §5.1 tables the engine's interval overrides,
    `ONEUP_HOLD_SECONDS` and `ONEUP_REFRESH_TIMEOUT` among them, so step 12a's
    `ONEUP_KEEPALIVE_SECONDS` owes a row beside them.
    → **verify:** every passage above is re-read and reads true on the branch it landed on,
    and `python3 tests/docs-check.py` passes on both. **Named, not swept:** a blanket
    `grep -rn ONEUP-0058 docs/standards/` also hits §5's *What checks this* row and two
    historical mentions, all of which stay true, so a sweep demanding a branch of every hit
    could not pass — and docs-check has no check for a claim that has merely gone stale.

14. Run the full push gate.
    → **verify:** `./local-CI.sh` green on `v2`.

15. **Show `--auth-status` working against the Python engine**, which is what §4.6's
    stage-2 row promises and what nothing above measures.
    → **verify:** from the repo root, `ONEUP_ENGINE_CMD='python3 -m oneup.engine' bash
    tests/run-tests.sh`, and read the `--auth-status` scenario's own check lines out of the
    run — every one passes. The rest of the suite is red, which is expected and is not the
    measurement: the suite takes no arguments and has no per-scenario selector, so this is
    read out of the whole run's output the way stage 1 step 6 reads the broken-pipe
    scenario's.

### Not stage 2's

`sudo_init` and the keep-alive, `cleanup` and its traps, and the run-state *writer*.
**§4.6 names none of them in any row; what defers them is its stage-2 row ending
*"enough for `--help` and `--auth-status`, nothing more"***, and the run driver that needs
them arrives at stage 5. `parsers.py` is not in that class — §4.6 gives it to stage 4 by
name. The hold is split: §4.6 names it at stage 4 only to *exclude* its scenario, which
cannot pass before stage 5's run driver, and §4.2 puts the wait in `runstate.py`, the entry
in `actions.py` and the go-ahead re-derivation in `__main__.py`.
`runstate.py` gains the paths at this stage and the writers later;
`privilege.py` gains the runner now and the bootstrap later.
Recorded so a reader does not take a module's presence for its completeness.

## Definition of done

**Stage 1 is done** when `main`'s §4.4 matches `v2`'s; neither call site in
`main`'s `tests/run-tests.sh` invokes `bash "$ENGINE"` directly any more;
`./local-CI.sh` is green on `main` with `ONEUP_ENGINE_CMD` unset and red with it
pointed at a failing stub, the broken-pipe scenario's own checks among the
failures; and the same holds on `v2` after the merge. **On `v2` one direct
invocation remains on purpose** — the `--hold` scenario, which step 10 keeps and
stage 2 converts. `local-CI.sh` runs `bash tests/run-tests.sh` without scrubbing
the environment and ends in `exit $fail`, so the override reaches the suite and
"red" is observable. Nothing about `main`'s behaviour changes.

**Stage 2 is done** when `python3 -m oneup.engine --auth-status` and `--emit-guard`
answer as `update_system.sh` does — the `--auth-status` scenario's own check lines passing
against the Python engine, and the two guard bodies byte-identical; when the suite's last
direct `bash "$ENGINE"` *invocation* is gone; when the three scenarios §4.6's stage-2 row
names exist and can each be made to fail, **the old SIGKILL scenario deleted with them**;
when the ONEUP-0058 scenario goes red against an engine without step 6's fix; when §4.1.1
names the four exit codes and the construct each was read from; when every passage step 13 names
reads true on the branch it landed on; when no bare `LOG_DIR` is left in the package; and when
`./local-CI.sh` is green on `v2` with `ONEUP_ENGINE_CMD` unset. **The middle three are in
this list because nothing else holds them** — no gate can fail on a scenario nobody
wrote, on a table nobody added, or on prose that has merely gone stale. `main`'s behaviour
is unchanged, as it is for every stage up to 8.

**The item is done** at stage 9, when G1–G6 are met. `docs/design/oneup-2.0.md`
§7 owns the gate; spec §4.6 says which stage earns each of them and that stage 9
is the commit they are measured against.

## Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-08-25 | 3 lanes, cold; genre pinned plan; Q1 1 · Q2 0 · Q3 1 · Q4 2 — 4 verified, 0 dismissed, all 4 fixed | First gate on this document. All three lanes independently led with the same two defects, which is the strongest signal the run produced. The worst is that **no clause in stage 1 could distinguish "both call sites converted" from "`run_engine` converted, broken-pipe site missed"**: with the override unset the unconverted site behaves identically, and whole-suite redness against a failing stub is evidence about `run_engine` alone, since it drives nearly every scenario. An implementer would have shipped stage 1 with one site still on v1 and met it at stage 6 as G2 diffing v1 against v1 — the exact failure §4.4 warns of. Step 5 now asserts no `bash "$ENGINE"` invocation remains, and step 6 runs the broken-pipe scenario against the stub in its own right. Second, step 1 said to bring §4.4's *correction* across without saying how much text crossed, and step 9 then merges `main` into `v2` where the same section was rewritten — a minimal edit conflicts there with no stated resolution, and resolving toward `main` silently reverts the re-gated contract stage 2 builds from. Step 1 now crosses §4.4 whole and step 9 verifies `v2`'s copy is byte-identical after the merge; the whole-section crossing was tested against `main`'s docs gate before being prescribed. One lane also caught that step 1's verify — *"no longer contains the word array"* — is falsified by the correct text, which reads *"word-split by the suite into its argv array"*, so a builder satisfying the check would have deleted the sentence that pins the encoding. Three lane open questions settled as non-findings: `local-CI.sh` does propagate the override (it runs `bash tests/run-tests.sh` without scrubbing the environment), the `REPO="$(dirname "$ENGINE")"` reader does belong to the pre-push-hook scenario, and step 7's verify was reworded from an allowlist to a prohibition so the plan's own Status line no longer falls foul of it. |
| 2 | 2026-08-25 | 3 lanes, cold; genre pinned plan; Q1 0 · Q2 2 · Q3 0 · Q4 4 — 6 verified, 0 dismissed, all 6 fixed. Cap reached (2 for a plan); the run files its tail and exits | **A violent cap: five of the six findings landed on text loop 1 itself wrote.** Loop 1 closed the "which call site" hole with `grep -c 'bash "$ENGINE"' … returns 0`, and two lanes independently found that a *correct* implementation returns 1 — the glob-safe default is an array literal `ENGINE_CMD=(bash "$ENGINE")`, which contains that string once as an assignment. A builder would have unquoted `$ENGINE` to satisfy the check, reintroducing exactly the word-splitting hazard step 3 exists to close. **All three lanes found the second**: loop 1's Definition of done said "no `bash "$ENGINE"` invocation remains in `tests/run-tests.sh`" with no branch qualifier, in a sentence ending on `v2` — where step 10 requires the `--hold` scenario to keep one. An implementer working the done-list after the merge would have converted it, pulling stage 2's work onto an engine that does not exist yet. Two more of loop 1's own: step 9's `v2` check was "local-CI green", which step 6 three paragraphs above already calls no evidence at all — and `run_engine` differs between the branches (ONEUP-0044 added two environment lines), so a conflict there is likely and resolving it toward `v2` drops the indirection silently; and step 7's "none of those readers appears in `git diff`" can never come back clean, because step 1's own §4.4 transplant adds a table row naming two of them. The orchestrator found a fifth while verifying: step 6 said to "run the broken-pipe scenario against the same stub", and the suite takes no arguments and has no per-scenario selector. One finding was pre-existing rather than collateral — the plan named the default as `bash update_system.sh` where step 2 says `bash $ENGINE`, and the suite computes that path absolutely on purpose, so the literal form would resolve against the caller's working directory. Three lane open questions settled clean: `v2`'s §4.4 transplanted onto `main` passes `tests/docs-check.py` (tested before the step was prescribed), `main`'s spec carries every section that §4.4 cross-references, and `local-CI.sh` ends in `exit $fail` so "red" is observable. **The cap being violent ends the review, not the shipping** — this plan now routes to implementation, which for a plan is the better third reviewer, and not to a third cold read. |
| 3 | 2026-08-25 | 3 lanes, cold; genre pinned plan; Q1 3 · Q2 2 · Q3 3 · Q4 2 — 10 verified, 1 dismissed, all 10 fixed | Loop 1 of a new run, on stage 2's newly appended steps; stage 1's text was not re-opened. **All three lanes led with the same defect, and it would have made stage 2's headline deliverable unreachable**: step 8 said to dispatch `--auth-status` and `--emit-guard` and have *"every other accepted flag"* exit non-zero — but `--log=` is an accepted flag and `run_engine` appends it to every invocation, so the engine would have refused every call the suite makes, and `--help` fell in the same bucket four lines under a sentence saying the engine answers it. Modifier flags are now parsed and stored, and only a flag selecting unbuilt *work* refuses. Two more were found by all three: the exit-code step named the `--help|-h` arm as a source of one of the four codes, and that arm yields `exit 0`; and step 2's verify ran the whole engine to prove `markers.py` flushes, when `actions.py` is step 7 and `__main__.py` step 8 — a check that cannot be reached where it is written. Step 3's carried the same fault more quietly: at step 3 `privilege.py` is the only module, so *"and no other file"* could not fail, and `actions.py` — added later, and the one place a stray `sudo` would land — was never covered. **The most dangerous single-lane finding was an unowned pair of overrides**: `ONEUP_AUTH_FILE` and `ONEUP_GUARD_FILE` are neither state files nor log paths, so no step claimed them, and the `--auth-status` scenario drives the engine entirely through them — stage 2 would have read the real `/etc/sudoers.d/` and `/usr/libexec/`, which `docs/standards/testing.md` §2 forbids outright. Also: nothing instructed *deleting* the SIGKILL scenario the plan called replaced, so both would have shipped against a G1 that permits exactly one replacement and is read off the diff; the done-list omitted three of the section's own obligations, none of which any gate can fail on; step 13 called `testing.md`'s untracked-`HOME` claim false when only its consequence is, and named neither `files-and-naming.md`'s Trap 2 nor its branch; and *"Not stage 2's"* attributed the deferral to §4.6 rows that name none of it. Dismissed as true-but-immaterial: steps 5 and 9 split the `LOG_DIR` work while step 9 says *"one commit"* — no collision is possible, since the engine's constant is never named `LOG_DIR`, so no line is built differently. **The fix pass caught three false claims of its own before the commit**, all by running them: `tests/docs-check.py` does walk `docs/specs/` (only `docs/plans/` is unwalked, ONEUP-0129); §4.6 does name `parsers.py` and the hold at stage 4, so the blanket deferral was wrong for two of six; and a blanket `grep ONEUP-0058 docs/standards/` hits three passages that stay true, so that verify could not pass. The 4b sweep then found three more pieces of its own collateral in the section header and the done-list. Four lane open questions settled clean: `oneup/gui/paths.py` imports only the standard library so step 5's equality check needs no PySide6; the hold path does spawn a keep-alive (the existing *"a held run leaves no orphaned keep-alive behind"* scenario asserts on it); the engine exports two variables, `SUDO_ASKPASS` and `SUDO_PROMPT`, so step 3's count is right and the lanes' packets simply lacked that window; and every window reader goes through `paths.`, so step 9's blast radius is as stated. |
| 4 | 2026-08-25 | 3 lanes, cold; genre pinned plan; Q1 2 · Q2 2 · Q3 4 · Q4 2 — 10 verified, 0 dismissed, all 10 fixed. Cap reached (2 for a plan); the run files its tail and exits | A calm cap: four of the ten landed on text loop 3 wrote, and the other six were draft defects that loop had not reached — the document held more than the cap held loops, which is the shipping case rather than the oscillating one. **The best finding was a check of my own that could not fail.** Loop 3 replaced step 2's unreachable verify with `python3 -c '…markers…' | cat`, and one lane pointed out that CPython flushes `sys.stdout` at interpreter shutdown, so a one-shot prints with or without the flush. Measured before fixing: the unflushed emitter prints through a pipe when the process exits, and never arrives while it stays alive — which is the only case the window sees. The verify now emits and sleeps. Its twin: step 4 claimed `ruff check .` catches a *reasonless* `# noqa`, and bare `# noqa: S603` comments live in `oneup/gui/` today with ruff green on them, so the step's own §5.2 obligation was discharged by a tool that never looks. And step 3's `grep '\"sudo\"'` matched one quote style against a rule set selecting none, so `['sudo', …]` in `actions.py` would have passed the one check the step says a green suite cannot replace — it now asserts no engine module but `privilege.py` imports `subprocess`. **All three lanes found the same Q2**: step 13's verify enumerated only the ONEUP-0058 passages while its own body named two more that step 9 falsifies, and the done-list counted documents step 13 does not name — a builder would have shipped `files-and-naming.md` still saying *\"Give them distinct names in 2.0\"* after step 9 gave them. **Two lanes found the branch claim**, and it is the one that could not be fixed inside this document: loop 3 said §9 had no `main` edit to route, and §9 names two bindings and closes *\"a third would need naming here before it counted\"*. Step 13 now splits — the ONEUP-0058 passages worded to hold on both branches and routed to `main` as §9 has it, the two naming the window's constant to `v2` because no both-branch wording exists — and the gap is **ONEUP-0130** rather than a standard amended from inside a build stage. Also fixed: *\"Not stage 2's\"* said §4.6 gives the hold to stage 4 by name, where §4.6 names it there only to *exclude* its scenario; step 7's byte-identical guard comparison invokes a flag `__main__.py` cannot answer until step 8; step 12a's new `ONEUP_KEEPALIVE_SECONDS` owed a row in §5.1, which tables the sibling intervals; step 10 never said whether editing the spec re-arms its gate (it does not — §4.1 already freezes the codes); and step 12c adds a field assertion to a scenario whose staging-failure branch states its own arithmetic in a comment. One repair outside this loop's subject, made because it is false and cheap: stage 1 step 7 credited §4.4 with assigning the SIGKILL reader to a stage, and that row names none. |
