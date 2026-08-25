# ONEUP-0054 — Python engine — build plan

**Spec:** [docs/specs/ONEUP-0054-python-engine.md](../specs/ONEUP-0054-python-engine.md)
**Status:** in progress — stages 1–3 done (2026-08-25); stage 4 under way.

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

## Stage 3 — `actions.py`'s `--check`

**Branch: `v2` only**, for stage 2's reason: §4.6 ends every stage from 2 onwards with
`./local-CI.sh` green on `v2` and says outright that *"Nothing in stages 1–8 changes
`main`'s behaviour."* Stage 3 edits no document, so no step splits by branch.

**What stage 3 is.** §4.6's stage-3 row is one line — *"`actions.py`'s `--check` — read-only
and needs no root, so the safest real behaviour to build first"* — and it ends *"every
`--check` scenario green against v2"*, which means the scenarios *Definition of done*
names: ONEUP-0086's opens with a full run, so it goes green at stage 5 with the rest of
it. **It adds no module.** `parsers.py` is stage 4's by
name, and §4.2 routes none of `run_check`'s parsing to it: that table's `parsers.py` row
names `to_bytes`, `lock_holder`'s parsing, the progress and download-size wordings, `lr`
output and `reboot_reason_from_log`'s phrase-building, and the split table names six
crossings, none of them `run_check`. So the zypper and flatpak text this stage reads is
parsed in `actions.py`, where §4.2 puts `run_check` whole.

**The refusal for `--check` is what this stage removes.** Everything else `__main__.main`
refuses stays refused.

### Steps

1. `proc.run` gains an optional environment overlay for one child. The check reads
   `LC_ALL=C zypper … list-updates` so the column layout parses on any locale, and that
   setting must reach that child and no other. Putting `LC_ALL` in the engine's own
   `os.environ` would change every later child's output, which the Bash engine never does —
   there the prefix is per-command.
   → **verify:** with the overlay set, the child process sees `LC_ALL=C`; after the call
   the engine's own `os.environ` has no `LC_ALL` it did not start with.

2. Step selection reaches `actions.py` as an argument, never as an import. §4.2 puts
   `step_selected` in `__main__.py`, and `__main__` already imports `actions` — so
   `actions` importing `__main__` back is a cycle. Give `Options` the predicate
   (`,steps,` contains `,key,`, as the Bash one-liner has it) and pass the `Options`
   object into the check; annotate it under `typing.TYPE_CHECKING` if a type is wanted.
   → **verify:** no module under `oneup/engine/` imports `__main__` **at run time** — a
   `TYPE_CHECKING`-guarded import for the annotation is the point of the clause above and
   creates no cycle — and `python3 -c 'import oneup.engine.actions'` from the repo root
   exits 0.

3. **Wire the dispatch first**, before building anything behind it: `__main__.main`
   sends `--check` to the new entry point and its stage-2 refusal goes; the other
   refusals stay as they are. Every verify from here on invokes `--check`, and against
   an unwired engine each one gets an empty stdout and exit 3 — indistinguishable from a
   wrong emitter. Repair the two module docstrings in the same edit: `__main__.py`'s says
   *"Stage 2 acts on `--help`, `--auth-status` and `--emit-guard` only"* and `actions.py`'s
   says `--check`, `--size=`, the grant/revoke pair and `--thin-snapshots` *"follow at their
   own stages"*, and both are false the moment this step lands.
   → **verify:** `python3 -m oneup.engine --check --steps=orphans` no longer exits 3, and
   `--size=system` still does.

4. The system arm, **and the shared check emitter it is the first user of** — one step,
   because neither can be verified without the other. One read of `zypper --no-refresh
   --non-interactive list-updates` with **stderr merged into stdout** — the merge is not
   tidiness, it is the whole of ONEUP-0056: zypper reports a repository it set aside as a
   warning on stderr and exits 106, and that warning is the only thing separating
   *"nothing to update"* from *"I could not read the repository that had the updates"*.
   Count the rows whose status column is `v`. On a non-zero exit, name the repositories
   zypper said it skipped; when it named none, report the exit status rather than guessing
   a cause. Then one `@@CHECK_ITEM@@|system|name|from|to` per row, each field trimmed.

   The emitter matches `emit_check`: `@@CHECK_UNKNOWN@@|key|reason` **before** `@@CHECK@@`,
   and **`@@CHECK@@` suppressed entirely when the read failed and the count is zero.** A
   confident `@@CHECK@@|system|0` after an unreadable source is the ONEUP-0056 bug itself,
   and the scenario asserts its absence rather than its presence — so an implementation
   that emits it anyway fails on a `check_absent`, which is easy to read as unrelated.
   **One emitter, not one per arm:** step 6 departs from it deliberately and nothing else
   may.
   → **verify:** against `python3 -m oneup.engine`, the two-update mock gives
   `@@CHECK@@|system|2`, the two `@@CHECK_ITEM@@|system|…` lines and no `@@CHECK_UNKNOWN@@`;
   the 106 mock gives `@@CHECK_UNKNOWN@@|system` naming `packman` and no
   `@@CHECK@@|system|0`. The rest of those two scenarios' check lines belong to later steps
   — the total to step 8, the flatpak item to step 5 — and the whole-scenario claim is
   step 10's.

5. The flatpak arm asks **each remote separately**, in both scopes. `flatpak remotes
   <scope> --columns=name,options` first, then `flatpak remote-ls --updates <scope>
   <remote> --columns=application,version` per remote. Never one listing for all remotes:
   that form abandons the whole listing the moment any single remote cannot be summarised,
   which is how six local origins hid a real update for weeks (ONEUP-0056). A remote whose
   listing fails is unreadable **unless its options contain `no-enumerate`** — a local
   origin serves no listing by design, so it is not a failed check. The detail line's
   *from* field is empty: `@@CHECK_ITEM@@|flatpak|app||version`.
   → **verify:** the check lines of *"--check counts Flatpak updates even when one remote
   is unreadable"* all pass, the `check_absent` on `@@CHECK_UNKNOWN@@|flatpak` among them.

6. The firmware arm emits `@@CHECK@@` **directly, not through step 4's emitter.**
   `fwupdmgr get-updates` answers yes or no, there is no unreadable case, and firmware
   reports `firmware|0` — which step 4's suppression rule would swallow if the reason field
   were ever non-empty. Keeping the asymmetry is keeping the Bash behaviour; tidying the
   two into one emitter changes it.
   → **verify:** no suite scenario drives this arm, so drive it by hand against both
   engines with an `fwupdmgr` mock: exiting 0 gives `@@CHECK@@|firmware|1`, exiting
   non-zero gives `@@CHECK@@|firmware|0`, both identically.

7. A step with no check arm, and a step whose tool is absent, emit **nothing at all** —
   no `@@CHECK@@`, and above all no `@@STEP_END@@|…|skip`. `orphans` and `cache` have no
   arm in `run_check`; `flatpak` and `firmware` are each behind a tool probe. The skip
   marker belongs to a *run*, and `run_check` emits none — inventing one here would put a
   marker in the check stream that neither engine has ever produced.
   → **verify:** `--check --steps=orphans,cache` emits no `@@CHECK@@|orphans` or
   `@@CHECK@@|cache` line and no `@@STEP_END@@`. Then a **second** command — `--check
   --steps=flatpak,firmware`, with both binaries hidden from the engine's `PATH` — emits no
   `@@CHECK@@|flatpak`, no `@@CHECK@@|firmware` and no `@@STEP_END@@`. The first selects
   neither tool, so on its own it cannot exercise the absent-tool half at all. Hide them
   the way stage 2 step 12b's scenario does, by supplying a `PATH` of its own: `run_engine`
   puts the mock directory first and `setup_common` ships both binaries, so deleting them
   finds the developer's instead.

8. The total, the exit status and the console summary. `@@CHECK@@|TOTAL|<sum>|updates
   available` last, then `@@DONE@@|ok`, and **exit 0 even when a source could not be
   read** — the incompleteness is carried by `@@CHECK_UNKNOWN@@` and by the console
   wording, never by the status, because an unattended timer treats a non-zero status as a
   failed check rather than an incomplete one. The console lines are part of the contract
   too (the engine is usable in a terminal, `CLAUDE.md` §4), including the *"treat this as
   a floor, not an all-clear"* wording that replaces the plain total when a source was
   unreadable. **A step whose read FAILED still contributes its partial count**: in the
   Bash engine `(( total += n ))` sits outside the failure branch in both arms, and
   `docs/reference/marker-protocol.md` §4.6 gives the reason — knowing about 7 updates
   beats knowing about none while a repository is broken. The natural-looking
   `if rc == 0: total += n` passes every stage-3 check, reports `TOTAL|0` where the Bash
   reports `TOTAL|7`, and silently suppresses step 9's notification.
   → **verify:** under the 106 mock the process exits 0; and both engines' **whole
   output** — marker lines and console lines alike — matches for one mock set, compared by
   hand. Not the console half alone: the scenarios grep substrings, so `emit_check`'s
   `label` strings and the two unreadable-reason sentences are pinned by nothing until
   §4.5's harness diffs them at stage 6, and a paraphrase written here surfaces as a G2
   divergence three stages later. The console half G2 never sees at all, because that
   harness captures `@@MARKER@@` lines and discards the rest — the same blind spot
   `--emit-guard` has.

9. `--notify`. `notify_send` moves into `actions.py` (§4.2) and the check raises one
   notification only when the total is above zero — a timer that pops up "0 updates" every
   morning is the thing `--check --notify` exists to avoid.
   → **verify:** no suite scenario drives `--check --notify` (the notify scenarios all run
   full runs), so drive it by hand **against both engines** with a `notify-send` mock that
   logs its arguments: under the two-update mock each logs one notification and the logged
   arguments are identical; under a zero-update mock neither logs any.

10. Run the whole suite against the Python engine and read the `--check` scenarios' own
    check lines out of it, the same way stage 2 step 15 reads `--auth-status`'s. The suite
    takes no arguments and has no per-scenario selector.
    → **verify:** from the repo root, `ONEUP_ENGINE_CMD='python3 -m oneup.engine' bash
    tests/run-tests.sh` — every check line belonging to the scenarios the done-list names
    passes. The rest of the suite is still red, which is expected and is not the
    measurement. Then `./local-CI.sh` green on `v2` with `ONEUP_ENGINE_CMD` unset.

### Not stage 3's

**Three assertions about `--check` pass against a stage-3 engine without testing anything,
and each is recorded here so its green is not read as evidence.**

- **The log mirror.** `update_system.sh` tees every run to a log file, `--check` included;
  the Python engine still writes none. No `--check` scenario reads a log, so nothing goes
  red — which is exactly why it is written down. §4.2 gives the logging preamble to
  `runstate.py` and §4.6 gives the run driver to stage 5, so **stage 5 must cover `--check`
  as well as a full run**; a tee built inside the run driver alone leaves the check
  unlogged for good. G2 cannot see it either — a log file is not a marker line.
- **The shutdown inhibitor.** ONEUP-0086's scenario asserts that a `--check` takes no
  block-mode lock. Against a stage-3 engine that passes because no engine path takes one,
  and it becomes a real assertion at stage 5. (That scenario's first half is a full run, so
  the scenario as a whole is red at this stage regardless.)
- **The run-state file.** *"a read-only `--check` run does NOT touch the run-state file"*
  passes for the same reason: `runstate.py` has the paths and no writers yet.

`parsers.py`, `repos.py` and `--size=` are stage 4's; the run driver, `steps.py` and the
grant/revoke pair are stage 5's. Neither list is deferred by this stage's judgement — §4.6
names both stages by row. `sudo_init` is the exception and is deferred as stage 2 defers
it: no §4.6 row names it, and what puts it out of reach is the run driver it belongs to.

## Stage 4 — `parsers.py`, `repos.py`, and `--size=`

**Branch: `v2` only**, for stage 2's reason: §4.6 ends every stage from 2 onwards with
`./local-CI.sh` green on `v2` and says outright that *"Nothing in stages 1–8 changes
`main`'s behaviour."* **Stage 4 does edit documents** — step 2 adds a suite file and a
gate, and `docs/standards/workflow.md` §6 and `docs/standards/files-and-naming.md` §1 each
enumerate those closed. Step 11 owns them, and they go to `v2` for §9's second binding:
`workflow.md` §6's table names each gate by its `tests/<file>` path, which
`tests/docs-check.py` §9 refuses on `main` for a file `main` does not have.

**What stage 4 is.** §4.6's stage-4 row names three pieces of work — *"`parsers.py`,
`repos.py`, and `actions.py`'s `--size=`; parser unit tests"* — and ends *"the `--size`
scenarios green **except the `--hold` one**"*. The exception is a family, not a single
scenario: every `--hold` scenario is staged through the suite's `start_held_engine`
helper, which invokes `--size=system --hold` and waits for `hold.state`. **The barrier at
this stage is the hold, not the run**: step 7 refuses `--hold`, so `hold.state` is never
written and the helper reports a staging failure before any assertion runs. Several of the
family go on to a full run once a go-ahead lands, which is stage 5's; several others — a
hold nobody answers, a go-ahead left over from an earlier session, a tampered one, and the
`SIGKILL`ed engine of INV-7 — end at the hold and reach no run at all. Reading the run
driver as the whole barrier would have stage 4 build the hold to turn those green.

**Two dependencies stage 4 pulls in, because `--size` is the engine's first PRIVILEGED
action and repos.py's first caller.** Neither has a §4.6 row of its own, and both are
named here so their arrival is a decision rather than a drift.

- **`sudo_init`'s authenticate half.** Stage 3's *Not stage 3's* deferred `sudo_init`
  entire, on the grounds that what put it out of reach was the run driver. That was true
  while nothing became root; `--size` does. Without it a cancelled password reaches
  `run_size`'s dry run as an ordinary sudo failure and is reported through the `*)` arm,
  where the Bash engine aborts with *"Authentication failed or cancelled"* and exit 1.
  **The keep-alive is NOT part of this** — it is `cleanup`'s to kill, `cleanup` is stage
  5's, and shipping a keep-alive with nothing to kill it is the shape `CLAUDE.md` §6's
  fourth trap names.
- **`stop_pending`.** `refresh_repos` checks it between repositories, which is what makes
  Stop work during the longest phase of a run. §4.2 splits it — the decision to `proc.py`,
  the two state files it reads to `runstate.py` — and neither half exists yet.

**What `--size` does NOT get is `--hold`.** `__main__.main` refuses it as stage 2 refuses
everything unbuilt, **before** the size is quoted rather than after: a `--size --hold`
that priced the transaction and then exited with no `@@DONE@@` is a stream the window's
reader cannot account for, where a refusal on stderr with exit 3 is one it never sees.

### Steps

1. `parsers.py` — the pure module, and nothing else in the package may import into it.
   §4.2 gives it `to_bytes`, `lock_holder`'s text half, the progress wordings, the two
   download-size wordings, `lr` output and `reboot_reason_from_log`'s phrase-building.
   **`to_bytes` is integer arithmetic, and reproducing it exactly is the point**: Bash has
   no floats, so it keeps ONE fractional digit and computes `(whole * 10 + frac) * mult /
   10` with truncating division. A `float(n) * mult` in Python rounds differently on some
   inputs, and the number reaches the window inside `@@PROGRESS@@`. An unparsable figure
   and an unrecognised unit each give 0, and the recognised units are `B`, `KiB`, `MiB`,
   `GiB` and no others — `progress_filter`'s own regex admits `KB`, which must therefore
   come back 0 rather than 1000.
   → **verify:** `python3 -c 'import oneup.engine.parsers'` from the repo root exits 0,
   and the module's import list names neither `subprocess` nor `privilege` nor any sibling
   that reaches them — that isolation is what §4.2 says makes step 2 possible at all.

2. `tests/parsers-test.py`, table-driven, and wired into `local-CI.sh` as its own gate —
   and into `release.yml` and two standards, which step 11 owns and this step is not
   finished without.
   §4.3.4 names the surfaces it covers. Every case's input is real captured output,
   quoted verbatim from `update_system.sh`'s own worked examples and from the mocks the
   engine suite already ships — a table invented from the docstring tests the docstring.
   → **verify:** the file exits 0 on a clean tree, and non-zero with a single expected
   value edited — a table that cannot be made to fail is asserting nothing. `./local-CI.sh`
   shows the new gate by name.

3. `repos.py`'s unprivileged half, which is most of it: `valid_alias`,
   `enabled_repo_aliases`'s `zypper lr -u` invocation, `lock_holder`'s probe,
   `repo_scoped_failure` and `make_cdn_reposd`. **`enabled_repo_aliases` splits like
   `lock_holder`**: the read is here, the table parsing is step 1's, because §4.2's
   `parsers.py` row names `lr` output in its own right. Step 5's no-new-crossing rule does
   not reach it — that rule is about a function §4.2 places whole.
   **`valid_alias` is a FULL match, not an anchored `re.match`.** Bash's `=~
   ^[A-Za-z0-9][A-Za-z0-9:@._+-]*$` rejects a trailing newline; Python's `$` matches
   before one, so `re.match` on the same pattern accepts `oss\n` and `re.fullmatch`
   rejects it (measured). This is the guard `docs/standards/security.md` §4 puts in front
   of a privileged command, so the two must not disagree. **`make_cdn_reposd` carries a trap that nothing in the code
   announces** (`CLAUDE.md` §6, ONEUP-0094 §4.2): libzypp keys its package cache by
   repository ALIAS, an openSUSE alias usually contains the host name, and a blanket
   host substitution therefore renames the alias and discards every package already
   downloaded. The substitution is anchored to `baseurl=` lines and to nothing else.
   `lock_holder` splits as §4.2 says: the `$ZYPP_PID_FILE` read, the `/proc/<pid>` liveness
   test and the self-pid exclusion stay here; only the text it parses is step 1's.
   → **verify:** **`update_system.sh` carries no `BASH_SOURCE` guard, so sourcing it runs
   the engine and none of these functions can be called on its side in isolation.** Compare
   through the surface each one has, and say which comparison is one-sided. Two are
   two-sided: run the Bash engine over the *"the refresh names each source and says how far
   through the list it is"* mock and read its alias list out of the `@@REFRESH@@` payloads,
   then call `repos.enabled_repo_aliases()` over the same mock — the lists match; do the
   same for `lock_holder` against the two lock scenarios' Bash runs, which name the holder
   in their own output, and add the stale-pid, unreadable-file and own-pid cases on the
   Python side, where the Bash arms return non-zero and produce nothing to compare.
   `make_cdn_reposd` has **no v1 surface at all** — its directory is internal and no
   scenario reaches it — so it is checked on the Python side alone: every `baseurl=` is
   rewritten and **every `[alias]` header and `name=` is byte-identical to the input**,
   which is the assertion the trap is about. `valid_alias` and `repo_scoped_failure` are
   checked against the patterns quoted above, `valid_alias` including the `oss\n` case.

4. `stop_pending`, split as §4.2 requires: `proc.py` owns the decision, `runstate.py` the
   file reads it decides from. **It tests three things, and the third is the one a natural
   Python translation inverts.** `stop.request` must exist; `run.state` must **also** exist;
   and `stop.request` must be newer. §4.1.1 states the middle one outright — *"with no
   `run.state` at all **no stop is ever honoured**, which is what stops a request outliving
   the run it was meant for"* — and a `stat()` with a `FileNotFoundError` fallback of `0`
   turns it into its opposite, so a leftover request aborts the next run before it starts.
   The newness test is load-bearing too: the run-state file doubles as the run's start
   stamp, and deleting a leftover request at start-up instead would swallow a stop clicked
   a moment too early. The one-time console block and `@@HINT@@` fire on the first honoured
   stop only.
   → **verify:** with both files staged by hand, a request older than the run-state file
   does not fire and a newer one does; **with `run.state` absent and `stop.request`
   present, it does not fire**; the second call in a process emits no second hint.
   No `--size` scenario reaches this — it is verified here because step 5's caller needs it,
   and its own scenarios are stage 5's.

5. `repos.py`'s privileged half: `release_zypper_lock`, `disable_repo`, `find_failing_repos`
   and `refresh_repos`. `find_failing_repos`' signature/metadata/unreachable classification
   and `repo_scoped_failure`'s pattern **stay in `repos.py`** — §4.2 places both functions
   whole and its split table names neither, so splitting one is a change to the contract
   rather than a reading of it. `disable_repo` is fail-closed and
   runs `valid_alias` first, which is `docs/standards/security.md` §4's shape guard on the
   one path an alias reaches a privileged command. Every privileged call goes through
   `privilege.sudo`; `refresh_repos` uses the `timeout <budget> zypper` argv the drop-in
   grants, and treats exit 124 as a slow server — a `@@HINT@@` and a `@@REMEDY@@|skip-repo`,
   never a disabled repository.
   → **verify:** `python3 -c 'import oneup.engine.repos'` exits 0, and `release_zypper_lock`
   answers identically from both engines under a `systemctl` mock in both its active and
   inactive branches. **The other three are exercised by no scenario at this stage and are
   not claimed to be** — they are reached only through the run driver, and *Not stage 4's*
   records that rather than this list counting it.

6. `privilege.sudo_init` — the authenticate half only. `auth_current` short-circuits it,
   and `auth_current` is `actions.py`'s by §4.2 while `actions` imports `privilege`, so the
   import is deferred into the function body with the cycle named in a comment. **The
   validate carries its own prompt label**, `-p "System Updater: authenticate to update the
   system"` — not the `SUDO_PROMPT` `privilege.py` already exports, which is the label for
   every *other* prompt. Both strings are live: `reap_orphaned_askpass` matches an orphaned
   dialog against either, so collapsing them to one leaves stage 5's reaper with a target
   that never appears. On failure it prints the Bash engine's wording on stderr and exits 1;
   it must not fall through and let the dry run report the cancellation as a package-manager
   error.
   → **verify:** with a sudo mock that refuses `-v`, `--size=system` prints
   *"Authentication failed or cancelled — aborting."* and exits 1 from both engines, with no
   `@@SIZE@@` and no `@@HINT@@` — the failing-dry-run wording is a different answer to a
   different question and its appearance here is the defect.

7. **Wire the dispatch before building `run_size` behind it**, for stage 3 step 3's reason:
   against an unwired engine every verify below returns exit 3 and an empty stdout, which
   reads exactly like a wrong emitter. `__main__.main` sends `--size=` to the new entry point;
   `--hold` keeps a refusal of its own, checked first. Repair the two module docstrings in
   the same edit — `__main__.py`'s list of what is built and `actions.py`'s *"`--size=` …
   follow at their own stages"* are both false the moment this lands. `system_txn_argv` is
   `steps.py`'s by §4.2, so `steps.py` is created here holding that one function and a
   docstring saying so; it is shared rather than copied because ONEUP-0085 INV-5 requires
   the priced argv and the run's argv to be the same one.
   → **verify:** `python3 -m oneup.engine --size=system` no longer exits 3;
   `--size=system --hold` still does, and says stage 5; `--grant-auth` still exits 3.

8. `run_size`. A step other than `system` is refused on stderr with exit 2. Then
   `sudo_init`, `release_zypper_lock`, and one dry run of `system_txn_argv`'s own argv with
   **stderr merged** and the locale pinned **as an argv prefix, not as a child environment**:
   `sudo env LC_ALL=C zypper …`. The prefix is not a style choice — sudo resets the
   environment, so `LC_ALL` set on the child never reaches zypper; and `auth_cmnds` grants
   the literal words `env LC_ALL=C zypper *`, so a passwordless user's grant matches this
   argv and no other. Parse BOTH wordings, `Overall download size:` and `Package download
   size:`, **through `parsers.py`'s download-size function rather than a regex inlined
   here** — §4.2 gives that wording to `parsers.py`, and a second copy in `actions.py`
   leaves step 2's table green while the live path is untested, which is the stale-parser
   shape §4.3.4 exists for. The second wording is what current zypper prints, and a parse
   for the first alone is what reported "nothing to fetch" on a 137-package upgrade. Then the three arms, and the
   middle one is the one that looks droppable: a size found emits `@@SIZE@@|system|<figure>`;
   **no size but exit 0 or 100–103** emits `@@SIZE@@|system|0 B`, because those are zypper's
   informational exits and a definite zero is the answer the window's link is waiting for;
   any other status emits **no `@@SIZE@@` at all**, a `@@HINT@@` naming the cause from
   zypper's own exit code, and returns 1. A confident `0 B` the run did not earn is the
   failure class the suite exists to prevent.
   → **verify:** the check lines of every `--size` scenario *Definition of done* names pass
   against `python3 -m oneup.engine`, the `check_absent` on `@@SIZE@@` under a failed dry
   run among them, and so does *"privileged commands can reach the graphical password
   helper (no tty)"*, which drives `--size` and asserts the askpass export reaches the
   privileged command itself.

9. The console half, and the whole-output comparison that is the only thing pinning it.
   `run_size` prints *"Calculating download size (dry run)…"*, then one of
   *"  Download size: <figure>"*, *"  Download size: nothing to fetch."* or
   *"  Download size: unavailable — <why>"* followed by the last five lines of what zypper
   said, each prefixed `    zypper: `. That tail is not decoration: the output is captured
   into a variable, so without it the log records only "unavailable" and the user has
   nothing to act on. `size_delivered` emits `@@DONE@@|ok` on both successful arms and not
   on the failure arm.
   → **verify:** both engines' **whole output** — marker lines and console lines alike —
   plus exit status match for each `--size` mock set the suite ships, compared by hand. The
   scenarios grep substrings, so every one of these strings is pinned by nothing until
   §4.5's harness diffs them at stage 6 — and that harness captures `@@MARKER@@` lines and
   discards the rest, so the console half it never sees at all.

10. Run the whole suite against the Python engine and read the `--size` scenarios' own check
    lines out of it, as stage 3 step 10 does. The suite takes no arguments and has no
    per-scenario selector.
    → **verify:** from the repo root, `ONEUP_ENGINE_CMD='python3 -m oneup.engine' bash
    tests/run-tests.sh` — every check line belonging to the scenarios the done-list names
    passes. The rest of the suite is still red, which is expected and is not the
    measurement. Then `./local-CI.sh` green on `v2` with `ONEUP_ENGINE_CMD` unset, the new
    `tests/parsers-test.py` gate among its steps.

11. **The documentation step 2 owes, on `v2`.** Adding a gate is not finished when the
    script runs it: `docs/standards/workflow.md` § *Adding a gate* requires a row in §6's
    table naming the gate the way the script labels it and in the position the script runs
    it, and — because this is a *test* gate — an entry in `.github/workflows/release.yml`
    beside the other Python suites. §10 of that standard names the release.yml omission as
    a trap in its own words: *"a test gate that runs only locally catches its first
    regression after the tag is pushed."* `docs/standards/files-and-naming.md` §1's `tests/`
    row enumerates the suite closed and gains the new file. All three edits are `v2`'s:
    §9's second binding routes a document that must name a file 2.0 creates, and `main`
    has neither the file nor the gate.
    → **verify:** `python3 tests/docs-check.py` green on `v2` after the edits; the §6 table
    read against `local-CI.sh` line by line matches, gate for gate and in order; and a
    `grep` of `release.yml` names every Python suite `local-CI.sh` names.

### Not stage 4's

**Three things arrive with `--size`'s Bash twin and deliberately not with this one, and each
is recorded so its absence is not mistaken for parity.**

- **The keep-alive.** `sudo_init` starts one; step 6 does not. Nothing observes it at this
  stage — the scenario that does, *"a held run leaves no orphaned keep-alive behind"*, is
  staged through `start_held_engine` — and building it before `cleanup` exists would ship
  half of the trap `CLAUDE.md` §6 names, where a helper outlives the engine that spawned it.
- **The hold.** `hold_for_go_ahead`, `adopt_go_ahead`, `size_delivered`'s withheld
  `@@DONE@@` and `HOLD_SIZE` are stage 5's. §4.2 splits the pair three ways and gives the
  `RUN_KEYS`/`TOTAL`/`STEP_INDEX` re-derivation to `__main__.py`, which is the run driver.
- **The log mirror.** As at stage 3: `update_system.sh` tees every run to a log file,
  `--size` included, and the Python engine still writes none. No `--size` scenario reads a
  log, so nothing goes red. Stage 5 owes the tee for `--check` and `--size` as well as for a
  full run.

**One question stage 4 does not have to answer, recorded so stage 5 does not answer it by
accident.** §4.2 gives `markers.py` *"every marker emitter"* and names `emit_check` and
`emit_progress` among them, and stage 3 put `_emit_check` in `actions.py` instead. Stage 4
builds only the progress PARSERS, so nothing forces the placement of `emit_progress`; stage
5 builds the streaming loop and must settle both together, either by moving `_emit_check` to
`markers.py` or by amending §4.2.

`steps.py` beyond `system_txn_argv`, the run driver, the pre-flight, the grant/revoke pair
and `--thin-snapshots` are stage 5's by §4.6's row, not by this stage's judgement.

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

**Stage 3 is done** when the three scenarios that actually exercise check output pass
against `python3 -m oneup.engine` — *"--check reports counts read-only and never
installs"*, *"--check reports an unreadable repository instead of claiming up to date"* and
*"--check counts Flatpak updates even when one remote is unreadable"* — and when
*"--check performs NO privileged auth"* passes with its loud sudo mock in place; when the
firmware arm and the `--notify` arm, which no scenario reaches, have each been driven by
hand against both engines and answered identically; when the two engines' **whole output**
matches for one mock set, marker lines and console lines alike; and when `./local-CI.sh`
is green on `v2` with `ONEUP_ENGINE_CMD` unset. **The three vacuous passes are recorded
in *Not stage 3's* rather than counted here** — the log mirror, the shutdown inhibitor
and the run-state file each pass because the code that could break them does not exist yet, and a done-list
that counted them would be counting its own gaps. `main`'s behaviour is unchanged.

**Stage 4 is done** when every `--size` scenario in the suite passes against `python3 -m
oneup.engine` — the two wordings, the failed dry run that reports no size at all, the locked
package manager, zypper's informational exits and the definite `0 B` — and when *"privileged
commands can reach the graphical password helper (no tty)"* passes with them; when the two
engines' **whole output** and exit status match for each of those mock sets, marker lines and
console lines alike; when `tests/parsers-test.py` exists, can be made to fail, and runs as its
own `local-CI.sh` gate; when the alias list and the lock holder answer identically
from both engines, and the CDN rewrite — which has no v1 surface — leaves every alias
byte-identical on the Python side; when the checks no scenario can reach have each been driven by hand — `stop_pending`
with `run.state` absent as well as stale and fresh, `sudo_init`'s cancelled-password abort,
`release_zypper_lock` in both its branches, and `valid_alias` against a trailing newline;
when step 11's three documentation edits have landed on `v2`; and when `./local-CI.sh` is
green on `v2` with `ONEUP_ENGINE_CMD` unset. **The by-hand list is here because nothing else
holds it** — no suite mock set cancels authentication, none reaches `stop_pending`, and a
widened alias guard is invisible until the run driver calls it. **The `--hold` scenarios are
not in this list and do not go green here**: §4.6's own row says so, and each needs
`hold.state`, which step 7 refuses to write. **`refresh_repos`, `find_failing_repos` and `disable_repo` are not in it
either** — they are built at this stage and reached by no scenario until the run driver calls
them, and a done-list that counted an unexercised module would be counting its own gap.
`main`'s behaviour is unchanged.

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
| 5 | 2026-08-25 | 3 lanes, cold; genre pinned plan; Q1 1 · Q2 3 · Q3 3 · Q4 2 — 9 verified, 2 dismissed, all 9 fixed | Loop 1 of a new run, on stage 3's newly appended steps; stages 1 and 2 were not re-opened. **All three lanes led with the same defect**: step 3's verify claimed *every* check line of two whole scenarios passes, and those scenarios assert the TOTAL marker, the flatpak detail line and `@@CHECK_UNKNOWN@@` — work three later steps own. An implementer would have collapsed four steps into one or recorded a correct step as failed. **The worst was the ordering underneath it**, found by one lane: the step that wires `__main__.main` to dispatch `--check` sat *last*, while the verifies of every step above it invoke `--check` — and against an unwired engine that is empty stdout and exit 3 (measured), indistinguishable from a wrong emitter. The wiring is now step 3 and the old last step is deleted rather than moved. **Two lanes found step 2 permitting an import its own verify forbids**: the step offers a `TYPE_CHECKING` annotation of `Options`, which can only be written `from .__main__ import Options`, and the check read *"no module … names `__main__` in an import"* — so one builder deletes the annotation and another invents a stand-in the plan never names. **The most consequential single-lane finding was silence about marker text**: `emit_check`'s `label` strings and the two unreadable-reason sentences are pinned by nothing at this stage, because the scenarios grep substrings (`check()` is `grep -qF`, measured) and step 9's by-hand comparison was scoped to *non-marker* lines — so a paraphrase would ship green and surface as a G2 divergence three stages later. That comparison now covers the whole output. Also fixed: step 8's verify named the TOTAL marker step 9 earns, and required two tools *"off `PATH`"* against a harness whose mock directory ships both — it now names stage 2 step 12b's symlink farm; step 10's notify check was one engine and a count where the done-list asks two engines and identity; *Not stage 3's* credited §4.6 with deferring `sudo_init` by row, and no row names it. Two came from verifying rather than from a lane: the plan said *"Stage 3 edits no document"* and left both engine module docstrings asserting that `--check` *"follow[s] at their own stages"*, which step 3 falsifies the moment it lands; and the 4b sweep caught the done-list still saying *non-marker* after the step-9 fix widened it. Two dismissed as true-but-immaterial, both raised by two lanes and filed by neither: the firmware arm *is* executed by two scenarios (bare `--check` selects all steps and `setup_common` mocks `fwupdmgr`) though none asserts on it, and the intro quotes §4.6's *"every `--check` scenario green"* while the ONEUP-0086 scenario is red as a whole for reasons the done-list already excludes. One out-of-scope finding filed rather than fixed: `docs/reference/marker-protocol.md` §4.6 states the bare-zero withholding rule of `CHECK` generally, and `CHECK\|TOTAL\|0` and `CHECK\|firmware\|0` are both emitted unconditionally — a claim in a document that outranks the engine, so it takes its own item and its own gate. |
| 6 | 2026-08-25 | 3 lanes, cold; genre pinned plan; Q1 0 · Q2 1 · Q3 1 · Q4 2 — 4 verified, 0 dismissed, all 4 fixed. Cap reached (2 for a plan); the run files its tail and exits | Half the loop landed on text loop 5 wrote, and both of that half were the same class — a verify clause that cannot be reached or cannot fail. **All three lanes found the first**: loop 5 scoped step 4's verify to `@@CHECK@@|system|2`, and the emitter that produces `@@CHECK@@` was step 5, whose own verify needed step 4's arm to produce anything — a circular pair in which an implementer either stalls or writes a second emitter inside the system arm, which is the one shape the ONEUP-0056 suppression rule cannot survive. The two are now one step, because a six-line helper and its only callers were never two deliverables. **Two lanes found the second**: loop 5's *"Then the same with `flatpak` and `fwupdmgr` hidden"* took its command from the sentence before, and that command selects `orphans,cache` — so the absent-tool half of the rule was verified by a run that cannot enter it. The second command is now named, and the `PATH` mechanism is described rather than borrowed: stage 2 step 12b supplies a farm inside its own scenario, so *"the symlink farm step 12b built"* implied a reusable artefact that does not exist. **The best finding was a draft gap neither loop had reached, and it is the one that would have shipped**: nothing said whether a step whose read FAILED still contributes its partial count to `@@CHECK@@|TOTAL`. It does — `(( total += n ))` sits outside the failure branch in both arms, measured — and the natural `if rc == 0: total += n` passes every stage-3 check, reports `TOTAL|0` where the Bash reports `TOTAL|7`, silently suppresses the `--notify` popup, and surfaces only as a G2 divergence at stage 6. Also fixed: the intro's quoted §4.6 exit condition (*"every `--check` scenario green"*) and *Not stage 3's* could not both hold, since ONEUP-0086's scenario opens with a full run — raised as an open question by one lane in loop 5 and dismissed, filed by two lanes here, and now glossed to the *Definition of done* list; and step 7's claim that the protocol *"never places"* `@@STEP_END@@` in a check stream rested on the reference's silence, where `run_check` emitting none is measurable and is what the step now says. Three lane open questions settled clean by running rather than reading: a Bash `--check` prints seven deterministic lines with nothing before `run_check`'s first, so step 8's whole-output comparison is exact; no `--notify` scenario in the suite is a `--check` run; and `run_check` contains no `STEP_END`. **A cap between calm and oscillating** — two of four on this run's own text, both in clauses loop 5 rewrote, against two draft defects the cap never reached. The plan routes to implementation, which for a plan is the better third reviewer. |
| 7 | 2026-08-25 | 3 lanes, cold; genre pinned plan; Q1 3 · Q2 2 · Q3 3 · Q4 2 — 10 verified, 1 dismissed, all 10 fixed | Loop 1 of a new run, on stage 4's newly appended steps; stages 1-3 were not re-opened. **The most consequential finding was a premise the section opened with**: *"Stage 4 edits no document, so no step splits by branch."* Step 2 adds a suite file and a gate, and `docs/standards/workflow.md` §6 and `docs/standards/files-and-naming.md` §1 each enumerate those closed — so a builder would have shipped a gate table listing eight while the script ran nine, with no check able to fail on it. The same lane found the omission that standard names a trap in its own words: a *test* gate belongs in `.github/workflows/release.yml` too, or it catches its first regression after the tag. Step 11 now owns all three edits and routes them to `v2` by §9's second binding. **Two lanes found the `--hold` claim**, and the plan's own stage 2 text contradicted it: *"All of them then continue into a full run"* is false of a hold nobody answers, a stale go-ahead, a tampered one and the `SIGKILL`ed engine of INV-7 — an implementer reading the run driver as the whole barrier would build the hold at stage 4 to turn those green, which the paragraph below forbids. The barrier is the hold. **The sharpest single-lane finding was a condition the plan counted as two**: `stop_pending` tests three things, and §4.1.1 states the missing one outright — with no `run.state` at all no stop is ever honoured — so the natural `stat()` with a `FileNotFoundError` fallback of `0` inverts it and a leftover request aborts the next run before it starts. Step 4's own verify staged both files in every case, so it could never fail. **A second lane found a verify that cannot be performed at all**: `update_system.sh` carries no `BASH_SOURCE` guard, so sourcing it runs the engine and `enabled_repo_aliases`, `lock_holder` and `make_cdn_reposd` cannot be called on the v1 side — *"drive each against both engines by hand"* had no mechanism. The step now compares through the surface each function has and says which comparison is one-sided. Also fixed: §4.2 gives `lr` output to `parsers.py` in its own row while step 3 kept `enabled_repo_aliases` whole and step 5 stated a rule reading as a bar on splitting it — two module layouts and two gate files, both defensible from the text; the download-size wordings were not routed through `parsers.py`, which would have left the table green over dead code; `sudo_init`'s `-v` label was unpinned, and it is a second live string that `reap_orphaned_askpass` matches on, so collapsing it into `SUDO_PROMPT` leaves stage 5's reaper a target that never appears; `` `main` `` was written for `__main__.main` twice in a section whose other uses are the git branch; and the done list held none of the checks no scenario can reach, where stage 3's does the opposite for its own. One claim was measured rather than reasoned before it landed: Bash's alias guard rejects `oss\n` and Python's `re.match` on the same anchored pattern accepts it, so `valid_alias` is a full match — the guard `security.md` §4 puts in front of a privileged command. Dismissed as true-but-immaterial: `run_size`'s exit-5 and exit-6 hint arms are reached by no mock set, so step 9's comparison cannot pin their wording — true, and an implementer builds the same arms either way. Four lane open questions settled clean: the `--size` dispatch does propagate `run_size`'s `return 2` as process exit 2; the split table names six crossings of any boundary, which stage 3's text has right; `to_bytes`, the three `--size` arms, the console strings and the `env LC_ALL=C zypper` grant all read true as the plan states them; and the askpass scenario's per-invocation mock means step 9's whole-output comparison pins the sudo call count as well as the text. |
